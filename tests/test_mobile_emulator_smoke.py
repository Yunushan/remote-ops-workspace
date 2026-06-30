from __future__ import annotations

import importlib.util
import subprocess
import sys
from pathlib import Path


def test_open_ios_url_retries_transient_timeout(monkeypatch) -> None:
    smoke = _load_smoke()
    calls: list[list[str]] = []
    open_attempts = 0

    def fake_run(
        args: list[str],
        *,
        check: bool = True,
        text: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        nonlocal open_attempts
        calls.append(args)
        if args[:3] == ["xcrun", "simctl", "openurl"]:
            open_attempts += 1
            if open_attempts == 1:
                return subprocess.CompletedProcess(args, 60, stdout="", stderr="Operation timed out")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(smoke, "run", fake_run)
    monkeypatch.setattr(smoke.time, "sleep", lambda _seconds: None)

    smoke.open_ios_url("SIM-UDID", "http://127.0.0.1:8765/index.html", attempts=2)

    assert [call[:3] for call in calls].count(["xcrun", "simctl", "openurl"]) == 2
    assert ["xcrun", "simctl", "bootstatus", "SIM-UDID", "-b"] in calls
    assert ["xcrun", "simctl", "launch", "SIM-UDID", "com.apple.mobilesafari"] in calls


def test_open_ios_url_reports_exhausted_attempts(monkeypatch) -> None:
    smoke = _load_smoke()

    def fake_run(
        args: list[str],
        *,
        check: bool = True,
        text: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        return subprocess.CompletedProcess(args, 60, stdout="", stderr="Operation timed out")

    monkeypatch.setattr(smoke, "run", fake_run)
    monkeypatch.setattr(smoke.time, "sleep", lambda _seconds: None)

    try:
        smoke.open_ios_url("SIM-UDID", "http://127.0.0.1:8765/index.html", attempts=2)
    except SystemExit as exc:
        assert "after 2 attempts" in str(exc)
    else:
        raise AssertionError("open_ios_url should fail when every attempt times out")


def _load_smoke():
    path = Path("scripts/check_mobile_emulator_smoke.py")
    spec = importlib.util.spec_from_file_location("check_mobile_emulator_smoke_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

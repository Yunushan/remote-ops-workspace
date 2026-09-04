from __future__ import annotations

import importlib.util
import json
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


def test_android_web_response_accepts_expected_page(monkeypatch) -> None:
    smoke = _load_smoke()

    def fake_run(
        args: list[str],
        *,
        check: bool = True,
        text: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["adb", "push"]:
            assert Path(args[2]).read_bytes() == (
                b"GET /index.html HTTP/1.0\r\n"
                b"Host: 127.0.0.1:8765\r\n"
                b"Connection: close\r\n\r\n"
            )
            assert args[3] == smoke.ANDROID_WEB_REQUEST_PATH
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        if args == ["adb", "exec-out", "cat", smoke.ANDROID_WEB_RESPONSE_PATH]:
            return subprocess.CompletedProcess(
                args,
                0,
                stdout=f"{smoke.HTTP_OK_MARKER}\r\n\r\n{smoke.WEB_PWA_RESPONSE_MARKER}",
                stderr="",
            )
        if args[:4] == ["adb", "shell", "rm", "-f"]:
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        assert args == [
            "adb",
            "shell",
            f"(cat {smoke.ANDROID_WEB_REQUEST_PATH}; sleep 1) | toybox nc -w 10 127.0.0.1 8765 "
            f"> {smoke.ANDROID_WEB_RESPONSE_PATH}",
        ]
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(smoke, "run", fake_run)

    smoke.ensure_android_web_response("http://127.0.0.1:8765/index.html")


def test_android_web_response_reports_failed_fetch(monkeypatch) -> None:
    smoke = _load_smoke()

    def fake_run(
        args: list[str],
        *,
        check: bool = True,
        text: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        if args[:2] == ["adb", "push"] or args[:4] == ["adb", "shell", "rm", "-f"]:
            return subprocess.CompletedProcess(args, 0, stdout="", stderr="")
        if args == ["adb", "exec-out", "cat", smoke.ANDROID_WEB_RESPONSE_PATH]:
            return subprocess.CompletedProcess(args, 1, stdout="", stderr="missing response")
        return subprocess.CompletedProcess(args, 1, stdout="", stderr="connection refused")

    monkeypatch.setattr(smoke, "run", fake_run)

    try:
        smoke.ensure_android_web_response("http://127.0.0.1:8765/index.html", attempts=1)
    except SystemExit as exc:
        assert "could not verify the Web/PWA response" in str(exc)
        assert "connection refused" in str(exc)
    else:
        raise AssertionError("failed Web/PWA response fetch should fail the Android smoke")


def test_android_web_response_requires_adb_reversed_loopback() -> None:
    smoke = _load_smoke()

    try:
        smoke.ensure_android_web_response("http://10.0.2.2:8765/index.html", attempts=1)
    except SystemExit as exc:
        assert "adb-reversed emulator loopback" in str(exc)
    else:
        raise AssertionError("Android Web/PWA smoke must require the explicit adb reverse boundary")


def test_android_boot_screenshot_mode_does_not_fetch_web_response(monkeypatch, tmp_path) -> None:
    smoke = _load_smoke()
    calls: list[list[str]] = []

    def fake_run(
        args: list[str],
        *,
        check: bool = True,
        text: bool = True,
    ) -> subprocess.CompletedProcess[str] | subprocess.CompletedProcess[bytes]:
        calls.append(args)
        if args == ["adb", "shell", "getprop", "ro.build.version.sdk"]:
            return subprocess.CompletedProcess(args, 0, stdout="32\n", stderr="")
        if args == ["adb", "exec-out", "screencap", "-p"]:
            return subprocess.CompletedProcess(args, 0, stdout=b"png", stderr=b"")
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr(smoke, "run", fake_run)
    monkeypatch.setattr(smoke, "require_tool", lambda _name: None)
    monkeypatch.setattr(smoke.time, "sleep", lambda _seconds: None)

    assert smoke.check_android(
        api_level=32,
        url="http://127.0.0.1:8765/index.html",
        out_dir=tmp_path,
        verify_web_response=False,
    ) == 0
    assert not any("toybox nc" in " ".join(call) for call in calls)
    assert (tmp_path / "android-api-32-web-pwa.png").read_bytes() == b"png"


def test_latest_ios_runtime_selects_requested_version(monkeypatch) -> None:
    smoke = _load_smoke()
    runtimes = {
        "runtimes": [
            {
                "name": "iOS 26.5",
                "identifier": "com.apple.CoreSimulator.SimRuntime.iOS-26-5",
                "version": "26.5",
                "isAvailable": True,
            },
            {
                "name": "iOS 27.0",
                "identifier": "com.apple.CoreSimulator.SimRuntime.iOS-27-0",
                "version": "27.0",
                "isAvailable": True,
            },
        ]
    }

    def fake_run(args: list[str], *, check: bool = True, text: bool = True):
        assert args == ["xcrun", "simctl", "list", "runtimes", "--json"]
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps(runtimes), stderr="")

    monkeypatch.setattr(smoke, "run", fake_run)

    assert smoke.latest_ios_runtime(required_version="27") == runtimes["runtimes"][1]


def test_latest_ios_runtime_reports_missing_requested_version(monkeypatch) -> None:
    smoke = _load_smoke()
    runtimes = {
        "runtimes": [
            {
                "name": "iOS 26.5",
                "identifier": "com.apple.CoreSimulator.SimRuntime.iOS-26-5",
                "version": "26.5",
                "isAvailable": True,
            }
        ]
    }

    def fake_run(args: list[str], *, check: bool = True, text: bool = True):
        return subprocess.CompletedProcess(args, 0, stdout=json.dumps(runtimes), stderr="")

    monkeypatch.setattr(smoke, "run", fake_run)

    try:
        smoke.latest_ios_runtime(required_version="27")
    except SystemExit as exc:
        assert "required version '27'" in str(exc)
        assert "26.5" in str(exc)
    else:
        raise AssertionError("missing requested iOS runtime should fail closed")


def test_latest_ios_runtime_rejects_empty_requested_version(monkeypatch) -> None:
    smoke = _load_smoke()
    monkeypatch.setattr(
        smoke,
        "run",
        lambda args, *, check=True, text=True: subprocess.CompletedProcess(
            args,
            0,
            stdout=json.dumps({
                "runtimes": [
                    {
                        "name": "iOS 27.0",
                        "identifier": "com.apple.CoreSimulator.SimRuntime.iOS-27-0",
                        "version": "27.0",
                        "isAvailable": True,
                    }
                ]
            }),
            stderr="",
        ),
    )

    try:
        smoke.latest_ios_runtime(required_version="")
    except SystemExit as exc:
        assert "must not be empty" in str(exc)
    else:
        raise AssertionError("empty requested iOS runtime version should fail closed")


def _load_smoke():
    path = Path("scripts/check_mobile_emulator_smoke.py")
    spec = importlib.util.spec_from_file_location("check_mobile_emulator_smoke_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

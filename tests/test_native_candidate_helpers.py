from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_script(name, monkeypatch):
    script_dir = ROOT / "scripts"
    monkeypatch.syspath_prepend(str(script_dir))
    spec = importlib.util.spec_from_file_location(name, script_dir / f"{name}.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    monkeypatch.setitem(sys.modules, name, module)
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def candidate_owned(monkeypatch):
    return _load_script("candidate_windows_owned", monkeypatch)


@pytest.fixture
def candidate_diagnostic(candidate_owned, monkeypatch):
    pytest.importorskip(
        "tomllib",
        reason="candidate diagnostic is a native builder helper requiring CPython 3.14; tomllib unavailable on Python 3.10",
    )
    return _load_script("candidate_windows_diagnostic", monkeypatch)


def _good_result():
    return {
        "child_created": True,
        "job_assigned": True,
        "wait_result": 0,
        "exit_code": 0,
        "owned_parent_cleanup_wait": 0,
        "active_owned_processes_after_cleanup": 0,
        "job_closed": True,
        "cleanup_errors": [],
    }


def test_owned_api_rejects_invalid_timeout_before_native_api_loading(candidate_owned):
    for timeout in (0, -1, 3601, 2**100, True, False, 1.0, "1", None):
        with patch.object(candidate_owned.ctypes, "WinDLL", create=True) as api:
            with pytest.raises(ValueError, match="integer from 1 to 3600"):
                candidate_owned.run_owned(Path("unused.exe"), [], {}, Path("unused.json"), timeout)
            api.assert_not_called()
    for timeout in (1, 600, 1200, 3600):
        assert candidate_owned.validate_timeout(timeout) == timeout


def test_owned_cli_timeout_bounds(candidate_owned):
    for value in ("0", "-1", "3601", str(2**100), "1.5", "invalid"):
        with pytest.raises(argparse.ArgumentTypeError):
            candidate_owned.timeout_argument(value)
    assert candidate_owned.timeout_argument("1200") == 1200


def test_owned_success_requires_every_ownership_cleanup_and_exit_fact(candidate_owned):
    assert candidate_owned.owned_result_succeeded(_good_result())
    changes = {
        "child_created": False,
        "job_assigned": False,
        "wait_result": 258,
        "exit_code": 1,
        "owned_parent_cleanup_wait": 258,
        "active_owned_processes_after_cleanup": 1,
        "job_closed": False,
        "error": "TimeoutError: exceeded budget",
        "cleanup_errors": ["CloseHandle(job): 6"],
    }
    for field, value in changes.items():
        result = _good_result()
        result[field] = value
        assert not candidate_owned.owned_result_succeeded(result), field
    for field in _good_result():
        result = _good_result()
        del result[field]
        assert not candidate_owned.owned_result_succeeded(result), field


@pytest.mark.parametrize(
    "scenario",
    (
        "missing_original",
        "raw_build_timeout",
        "build_failure",
        "build_timeout",
        "launch_failure",
        "launch_timeout",
        "cleanup_failure",
        "missing_report",
        "missing_png",
        "bad_paint",
        "success",
    ),
)
def test_diagnostic_durably_records_build_launch_cleanup_and_report_failures(
    candidate_diagnostic, monkeypatch, tmp_path, capsys, scenario
):
    original = tmp_path / "build/native/windows/pyinstaller-dist/row-gui.exe"
    original.parent.mkdir(parents=True)
    if scenario != "missing_original":
        original.write_bytes(b"fixture original; never executable")
    (tmp_path / "pyproject.toml").write_text('[project]\nversion="test-version"\n')
    calls = []

    def fake_owned(executable, arguments, env, output, timeout):
        calls.append((str(executable), arguments, timeout))
        assert "PYTHONPATH" not in env
        output.with_suffix(".log").write_text(f"mock {output.stem} log\n")
        if output.stem == "build":
            if scenario == "raw_build_timeout":
                raise TimeoutError("mock bounded build timeout")
            result = _good_result()
            if scenario == "build_failure":
                result["exit_code"] = 1
            elif scenario == "build_timeout":
                result.update(wait_result=258, error="TimeoutError: mock build timeout")
            else:
                target = output.parent / "dist/row-gui-diagnostic.exe"
                target.parent.mkdir()
                target.write_bytes(b"fixture diagnostic; never executable")
            return result
        assert "PYTHONPATH" not in env
        assert env["QT_QPA_PLATFORM"] == "windows"
        result = _good_result()
        if scenario == "launch_failure":
            result["exit_code"] = 1
        elif scenario == "launch_timeout":
            result.update(wait_result=258, error="TimeoutError: mock launch timeout")
        elif scenario == "cleanup_failure":
            result["cleanup_errors"] = ["CloseHandle(job): 6"]
        if scenario == "missing_report":
            return result
        home = Path(env["ROW_HOME"])
        image = home / "smoke.png"
        if scenario != "missing_png":
            image.write_bytes(b"fixture screenshot")
        payload = {
            "success": True,
            "frozen": True,
            "qt_platform": "windows",
            "version": "test-version",
            "profile_persisted": True,
            "profile_selected": True,
            "window_visible": True,
            "paint_colour_count": 2 if scenario == "bad_paint" else 7,
            "screenshot_sha256": hashlib.sha256(b"fixture screenshot").hexdigest(),
        }
        (home / "smoke.json").write_text(json.dumps(payload))
        return result

    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PYTHONPATH", "untrusted-path-fixture")
    monkeypatch.setattr(sys, "argv", ["diagnostic.py", "--target", "windows-x64"])
    monkeypatch.setattr(candidate_diagnostic, "run_owned", fake_owned)
    code = candidate_diagnostic.main()
    output = tmp_path / "build/candidate-proof/windows-x64/console-diagnostic"
    record = json.loads((output / "diagnostic.json").read_text())
    assert "started_at_utc" in record and "finished_at_utc" in record
    assert not (output / "diagnostic.json.tmp").exists()
    assert json.loads(capsys.readouterr().out) == record
    if scenario == "success":
        assert code == 0 and record["diagnostic_success"] is True
        assert "error" not in record
    else:
        assert code == 1 and record["diagnostic_success"] is False
        assert "error" in record
    for stem in ("build", "launch"):
        evidence = record[stem]
        if evidence is not None:
            assert json.loads((output / f"{stem}.json").read_text()) == evidence
            assert f"mock {stem} log" in (output / f"{stem}.log").read_text()
    if calls:
        assert calls[0][2] == 600
    if len(calls) > 1:
        assert calls[1][2] == 45
    if scenario in ("build_failure", "build_timeout"):
        assert record["launch"] is None and len(calls) == 1

from __future__ import annotations

import subprocess
from pathlib import Path
from types import SimpleNamespace

import pytest
import windows_native_qt_case as native_case

_NAME = "test_native_windows_ssh_live_tabs_switch_without_miniature_surface"
_CASE = "direct-terminal-tabs"


def _report(case_id: str = _CASE) -> bytes:
    return (
        '<testsuites><testsuite tests="1" failures="0" errors="0" skipped="0">'
        f'<testcase classname="tests.test_windows_ssh_loopback" name="{_NAME}[{case_id}]"/>'
        "</testsuite></testsuites>"
    ).encode()


@pytest.mark.parametrize("case_id", [_CASE, "moba-connected-tabs"])
def test_report_requires_the_exact_successful_case(tmp_path: Path, case_id: str) -> None:
    report = tmp_path / "junit.xml"
    report.write_bytes(_report(case_id))
    native_case.validate_native_case_report(report, case_id)


@pytest.mark.parametrize(
    "data",
    [
        b"",
        b"not XML",
        b"x" * (1024 * 1024 + 1),
        b'<!DOCTYPE testsuites [<!ENTITY x "x">]>' + _report(),
        _report().replace(b'tests="1"', b'tests="0"'),
        _report().replace(b'failures="0"', b'failures="1"'),
        _report().replace(b'errors="0"', b'errors="1"'),
        _report().replace(b'skipped="0"', b'skipped="1"'),
        _report().replace(b"direct-terminal-tabs", b"moba-connected-tabs"),
        _report().replace(b"tests.test_windows_ssh_loopback", b"tests.other"),
        _report().replace(b"</testsuite>", b'<testcase name="extra"/></testsuite>'),
        _report().replace(b"/></testsuite>", b"><skipped/></testcase></testsuite>"),
        _report().replace(b"/></testsuite>", b"><failure/></testcase></testsuite>"),
        _report().replace(b"/></testsuite>", b"><error/></testcase></testsuite>"),
        b"<testsuites/>",
        _report().replace(b"<testsuites>", b"<other>").replace(b"</testsuites>", b"</other>"),
        _report().replace(b"</testsuites>", b"<testsuite/></testsuites>"),
    ],
)
def test_report_rejects_ambiguous_or_unsuccessful_results(tmp_path: Path, data: bytes) -> None:
    report = tmp_path / "junit.xml"
    report.write_bytes(data)
    with pytest.raises((AssertionError, native_case.ET.ParseError)):
        native_case.validate_native_case_report(report, _CASE)


def test_missing_report_cannot_pass(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        native_case.validate_native_case_report(tmp_path / "absent.xml", _CASE)


def test_unknown_case_cannot_start_a_child(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    def forbidden(*args: object, **kwargs: object) -> None:
        pytest.fail("unexpected subprocess creation")

    monkeypatch.setattr(native_case.subprocess, "Popen", forbidden)
    with pytest.raises(ValueError, match="unknown native Qt case"):
        native_case.run_native_qt_case("arbitrary-node", tmp_path)


@pytest.mark.parametrize("return_code", [0, 1])
def test_child_uses_fixed_node_native_environment_and_fresh_report(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, return_code: int,
) -> None:
    observed: dict[str, object] = {}

    def fake_popen(command: list[str], **kwargs: object) -> SimpleNamespace:
        observed.update(command=command, **kwargs)
        report = Path(command[-1].removeprefix("--junitxml="))
        assert not report.exists()
        report.write_bytes(_report())
        return SimpleNamespace(wait=lambda timeout: return_code)

    monkeypatch.setattr(native_case.subprocess, "Popen", fake_popen)
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("PYTEST_ADDOPTS", "--collect-only")
    if return_code:
        with pytest.raises(AssertionError, match="exited with status 1"):
            native_case.run_native_qt_case(_CASE, tmp_path)
    else:
        native_case.run_native_qt_case(_CASE, tmp_path)
    environment = observed["env"]
    assert isinstance(environment, dict)
    assert environment["QT_QPA_PLATFORM"] == "windows"
    assert environment["ROW_REQUIRE_WINDOWS_SSH_LOOPBACK"] == "1"
    assert environment["PYTEST_ADDOPTS"] == ""
    command = observed["command"]
    assert isinstance(command, list)
    assert command[:6] == [native_case.sys.executable, "-m", "pytest", "-q", "-o", "addopts="]
    assert command[6].endswith(f"test_windows_ssh_loopback.py::{_NAME}[{_CASE}]")
    assert observed["shell"] is False
    assert observed["stdin"] == subprocess.DEVNULL
    assert "stdout" not in observed and "stderr" not in observed


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_timeout_never_passes_even_after_direct_child_cleanup(cleanup_fails: bool) -> None:
    calls: list[object] = []

    def wait(timeout: int) -> int:
        calls.append(timeout)
        if timeout == 120 or cleanup_fails:
            raise subprocess.TimeoutExpired("fixed-native-case", timeout)
        return -9

    process = SimpleNamespace(wait=wait, poll=lambda: None, kill=lambda: calls.append("kill"))
    expected = RuntimeError if cleanup_fails else subprocess.TimeoutExpired
    with pytest.raises(expected):
        native_case._wait_for_child(process)
    assert calls == [120, "kill", 5]

"""Run the two native window cases without reusing an offscreen QApplication."""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

_TEST_NAME = "test_native_windows_ssh_live_tabs_switch_without_miniature_surface"
_CASE_IDS = frozenset({"direct-terminal-tabs", "moba-connected-tabs"})
_MAX_REPORT_BYTES = 1024 * 1024


def validate_native_case_report(report: Path, case_id: str) -> None:
    """Accept only the fresh child's single successful, unskipped test case."""
    if case_id not in _CASE_IDS:
        raise ValueError("unknown native Qt case")
    with report.open("rb") as stream:
        data = stream.read(_MAX_REPORT_BYTES + 1)
    if not data or len(data) > _MAX_REPORT_BYTES:
        raise AssertionError("native Qt child report is empty or too large")
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise AssertionError("native Qt child report contains XML declarations")
    root = ET.fromstring(data)
    if root.tag != "testsuites":
        raise AssertionError("native Qt child report has an unexpected root")
    suites = root.findall("testsuite")
    if len(suites) != 1 or len(root) != 1:
        raise AssertionError("native Qt child report must contain one suite")
    suite = suites[0]
    if suite.get("tests") != "1":
        raise AssertionError("native Qt child report must count one test")
    for counter in ("failures", "errors", "skipped"):
        if suite.get(counter) != "0":
            raise AssertionError(f"native Qt child report has a nonzero {counter} count")
    cases = list(root.iter("testcase"))
    if len(cases) != 1 or cases[0] not in list(suite):
        raise AssertionError("native Qt child report must contain one direct test case")
    case = cases[0]
    if case.get("name") != f"{_TEST_NAME}[{case_id}]":
        raise AssertionError("native Qt child report names the wrong case")
    if case.get("classname") != "tests.test_windows_ssh_loopback":
        raise AssertionError("native Qt child report names the wrong test module")
    for element in root.iter():
        if element.tag in {"skipped", "failure", "error"}:
            raise AssertionError("native Qt child did not complete successfully")


def _wait_for_child(process: subprocess.Popen[bytes]) -> int:
    try:
        return process.wait(timeout=120)
    except BaseException:
        # Only the direct child is retained here. Hosted runner disposal owns
        # descendants if native cleanup stalls; a timeout can never be success.
        try:
            if process.poll() is None:
                process.kill()
            process.wait(timeout=5)
        except BaseException as cleanup_error:
            raise RuntimeError("native Qt child cleanup did not finish") from cleanup_error
        raise


def run_native_qt_case(case_id: str, tmp_path: Path) -> None:
    """Invoke exactly one fixed node with a fresh native Windows Qt process."""
    if case_id not in _CASE_IDS:
        raise ValueError("unknown native Qt case")
    test_file = Path(__file__).resolve().with_name("test_windows_ssh_loopback.py")
    run_dir = Path(tempfile.mkdtemp(prefix="native-qt-case-", dir=tmp_path))
    report = run_dir / "junit.xml"
    assert not report.exists(), "native Qt child report must start absent"
    environment = os.environ.copy()
    environment.update(
        QT_QPA_PLATFORM="windows",
        ROW_REQUIRE_WINDOWS_SSH_LOOPBACK="1",
        ROW_WINDOWS_SSH_EVIDENCE_DIR=str(run_dir / "evidence"),
        PYTEST_ADDOPTS="",
    )
    command = [
        sys.executable,
        "-m",
        "pytest",
        "-q",
        "-vv",
        "-o",
        "faulthandler_timeout=60",
        "-o",
        "addopts=",
        f"{test_file}::{_TEST_NAME}[{case_id}]",
        f"--junitxml={report}",
    ]
    process = subprocess.Popen(
        command,
        cwd=test_file.parent.parent,
        env=environment,
        stdin=subprocess.DEVNULL,
        shell=False,
    )
    return_code = _wait_for_child(process)
    if return_code != 0:
        raise AssertionError(f"native Qt child exited with status {return_code}")
    validate_native_case_report(report, case_id)

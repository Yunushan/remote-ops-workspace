"""Run six literal hosted Qt scroll lifetime cases with bounded public evidence."""

from __future__ import annotations

import argparse
import contextlib
import hashlib
import importlib.metadata
import importlib.util
import io
import json
import os
import re
import stat
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

from check_gui_two_window_result import (
    callback_exception_projection,
    host_identity,
    persist_receipt,
    source_pins,
)

ROOT = Path(__file__).resolve().parents[1]
TEST_FILE = "tests/test_gui_terminal_io_edges.py"
TEST_NODES = (
    TEST_FILE + "::test_nonrunning_scroll_timer_dies_with_native_owner[tab]",
    TEST_FILE + "::test_nonrunning_scroll_timer_dies_with_native_owner[window]",
    TEST_FILE + "::test_nonrunning_scroll_timer_dies_with_native_owner[pane]",
    TEST_FILE + "::test_cancelled_running_close_keeps_owned_scroll_live[tab]",
    TEST_FILE + "::test_cancelled_running_close_keeps_owned_scroll_live[window]",
    TEST_FILE + "::test_prepared_scroll_timer_stops_before_delete_and_cannot_restart",
)
STAGES = ("setup", "call", "teardown")
EXTRA_SOURCE_FILES = (
    "scripts/check_gui_two_window_result.py",
    "scripts/check_gui_scroll_lifetime_result.py",
)
PHASES = frozenset({
    "initialized", "host-bound", "source-bound", "before-pytest", "collection-complete",
    "setup-started", "call-started", "teardown-started", "setup-reported", "call-reported",
    "teardown-reported", "report-refused", "unexpected-case", "uncaught-callback-exception",
    "pytest-returned", "completed", "refused",
})
REFUSALS = frozenset({
    "host-identity-refused", "checkout-identity-refused", "run-identity-refused",
    "coverage-python-version-refused", "deterministic-pytest-environment-refused",
    "source-file-bound-or-type", "source-file-changed", "pyqt6-unavailable", "pyqt6-version-refused",
    "six-cases-failed-skipped-or-incomplete", "uncaught-callback-exception-observed",
    "junit-result-refused", "public-receipt-bound",
    "private-junit-location-refused",
})
SCOPE = "six actual Qt cases with controlled no-child processes; no ConPTY/SSH/packaging/approval claim"


class CaseRecorder:
    def __init__(self) -> None:
        self.collected: list[str] = []
        self.collection_count = 0
        self.invalid = False
        self.reports: dict[str, dict[str, str]] = {node: {} for node in TEST_NODES}
        self.started: set[tuple[str, str]] = set()
        self.current_case: str | None = None
        self.checkpoint = None

    def _checkpoint(self, phase: str) -> None:
        if self.checkpoint is not None:
            self.checkpoint(phase)

    def pytest_collection_finish(self, session) -> None:
        self.collection_count = min(len(session.items), 7)
        self.collected = []
        for item in session.items[:7]:
            node = getattr(item, "nodeid", None)
            if type(node) is str and node in TEST_NODES:
                self.collected.append(node)
            else:
                self.invalid = True
        self.invalid |= len(session.items) != 6 or self.collected != list(TEST_NODES)
        self._checkpoint("collection-complete")

    def _stage_started(self, item, stage: str) -> None:
        node = getattr(item, "nodeid", None)
        if type(node) is not str or node not in TEST_NODES or (node, stage) in self.started:
            self.invalid = True
            self._checkpoint("unexpected-case")
            return
        self.current_case = node
        self.started.add((node, stage))
        self._checkpoint(stage + "-started")

    def pytest_runtest_setup(self, item) -> None:
        self._stage_started(item, "setup")

    def pytest_runtest_call(self, item) -> None:
        self._stage_started(item, "call")

    def pytest_runtest_teardown(self, item) -> None:
        self._stage_started(item, "teardown")

    def pytest_runtest_logreport(self, report) -> None:
        node = getattr(report, "nodeid", None)
        stage = getattr(report, "when", None)
        outcome = getattr(report, "outcome", None)
        if type(node) is not str or node not in TEST_NODES or type(stage) is not str or stage not in STAGES or stage in self.reports[node] or type(outcome) is not str or outcome not in {"passed", "skipped", "failed"} or (node, stage) not in self.started:
            self.invalid = True
            self._checkpoint("report-refused")
            return
        self.current_case = node
        self.reports[node][stage] = outcome
        self.invalid |= hasattr(report, "wasxfail")
        self._checkpoint(stage + "-reported")

    def passed(self, exit_code) -> bool:
        return (
            type(exit_code) is int and exit_code == 0 and not self.invalid
            and self.collected == list(TEST_NODES)
            and self.started == {(node, stage) for node in TEST_NODES for stage in STAGES}
            and self.reports == {node: dict.fromkeys(STAGES, "passed") for node in TEST_NODES}
        )


class BoundedOutput(io.TextIOBase):
    def __init__(self) -> None:
        self.raw = bytearray()
        self.exceeded = False

    def write(self, value: str) -> int:
        encoded = value[:65537].encode("utf-8", errors="replace")
        remaining = 65536 - len(self.raw)
        self.raw.extend(encoded[:remaining])
        self.exceeded |= len(value) > 65536 or len(encoded) > remaining
        return len(value)

    def isatty(self) -> bool:
        return False


def read_regular(path: Path, limit: int) -> bytes:
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not 0 < before.st_size <= limit:
        raise ValueError("source-file-bound-or-type")
    fields = ("st_dev", "st_ino", "st_mode", "st_size", "st_nlink", "st_mtime_ns", "st_ctime_ns")
    shared = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
    identity = tuple(getattr(before, field) for field in fields)
    with path.open("rb") as stream:
        opened = os.fstat(stream.fileno())
        if tuple(getattr(opened, field) for field in shared) != tuple(getattr(before, field) for field in shared):
            raise ValueError("source-file-changed")
        raw = stream.read(before.st_size + 1)
        after_fd = os.fstat(stream.fileno())
    after_path = path.lstat()
    if len(raw) != before.st_size or tuple(getattr(after_fd, field) for field in fields) != tuple(getattr(opened, field) for field in fields) or tuple(getattr(after_path, field) for field in fields) != identity:
        raise ValueError("source-file-changed")
    return raw


def source_binding(root: Path) -> dict[str, dict[str, object]]:
    result = source_pins(root)
    for name in EXTRA_SOURCE_FILES:
        raw = read_regular(root / name, 2 * 1024 * 1024)
        result[name] = {"size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    return result


def version_text(value) -> str:
    if type(value) is not str or len(value) > 64 or re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,3}", value) is None:
        raise ValueError("pyqt6-version-refused")
    return value


def pytest_arguments(private_junit: Path) -> list[str]:
    return ["-v", "-rA", "--color=no", "--junitxml=" + str(private_junit), *TEST_NODES]


def validate_junit(raw: bytes) -> dict[str, object]:
    if type(raw) is not bytes or not 0 < len(raw) <= 256 * 1024:
        raise ValueError("junit-result-refused")
    try:
        text = raw.decode("utf-8", errors="strict")
        if "\x00" in text or "<!DOCTYPE" in text.upper() or "<!ENTITY" in text.upper():
            raise ValueError("junit-result-refused")
        root = ET.fromstring(text)
    except (UnicodeError, ET.ParseError, ValueError) as error:
        raise ValueError("junit-result-refused") from error
    if root.tag != "testsuites" or len(root) != 1 or root[0].tag != "testsuite":
        raise ValueError("junit-result-refused")
    suite = root[0]
    if any(suite.get(field) != value for field, value in {"tests": "6", "errors": "0", "failures": "0", "skipped": "0"}.items()) or len(suite) != 6:
        raise ValueError("junit-result-refused")
    expected = {node.split("::", 1)[1] for node in TEST_NODES}
    observed = set()
    for case in suite:
        name = case.get("name")
        if case.tag != "testcase" or case.get("classname") != "tests.test_gui_terminal_io_edges" or name not in expected or name in observed or any(child.tag not in {"system-out", "system-err"} or len(child) != 0 for child in case):
            raise ValueError("junit-result-refused")
        observed.add(name)
    if observed != expected:
        raise ValueError("junit-result-refused")
    return {"validated": True, "cases": 6, "sha256": hashlib.sha256(raw).hexdigest()}


def validate_observation(recorder: CaseRecorder, exit_code, output_exceeded, callback_observed, raw_junit: bytes, before, after) -> dict[str, object]:
    if type(callback_observed) is not bool or callback_observed:
        raise ValueError("uncaught-callback-exception-observed")
    if type(output_exceeded) is not bool or output_exceeded or not recorder.passed(exit_code):
        raise ValueError("six-cases-failed-skipped-or-incomplete")
    junit = validate_junit(raw_junit)
    if before != after:
        raise ValueError("source-file-changed")
    return junit


def safe_refusal(error: BaseException) -> str:
    if isinstance(error, ValueError) and str(error) in REFUSALS:
        return str(error)
    if isinstance(error, (SystemExit, KeyboardInterrupt)):
        return "hosted-six-cases-abnormal-python-exit"
    return "hosted-six-cases-observation-failed"


def runner_temp_root() -> Path:
    value = os.environ.get("RUNNER_TEMP", "")
    if not 0 < len(value) <= 1024:
        raise ValueError("private-junit-location-refused")
    candidate = Path(value)
    if not candidate.is_absolute() or candidate.is_symlink() or not candidate.is_dir():
        raise ValueError("private-junit-location-refused")
    resolved = candidate.resolve(strict=True)
    if resolved.is_relative_to(ROOT.resolve()):
        raise ValueError("private-junit-location-refused")
    return resolved


def _json_pairs(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("six-cases-failed-skipped-or-incomplete")
        result[key] = value
    return result


def _json_constant(_value):
    raise ValueError("six-cases-failed-skipped-or-incomplete")


def parse_receipt(raw: bytes) -> dict[str, object]:
    if type(raw) is not bytes or not 0 < len(raw) <= 16 * 1024:
        raise ValueError("six-cases-failed-skipped-or-incomplete")
    try:
        value = json.loads(raw.decode("utf-8", errors="strict"), object_pairs_hook=_json_pairs, parse_constant=_json_constant)
    except (UnicodeError, ValueError, RecursionError) as error:
        raise ValueError("six-cases-failed-skipped-or-incomplete") from error
    if type(value) is not dict:
        raise ValueError("six-cases-failed-skipped-or-incomplete")
    return value


def same_source_pins(observed, expected) -> bool:
    if type(observed) is not dict or set(observed) != set(expected):
        return False
    for name, value in observed.items():
        if type(name) is not str or type(value) is not dict or set(value) != {"size", "sha256"}:
            return False
        if type(value["size"]) is not int or not 0 < value["size"] <= 2 * 1024 * 1024 or type(value["sha256"]) is not str or re.fullmatch(r"[0-9a-f]{64}", value["sha256"]) is None:
            return False
    return observed == expected


def validate_completed(receipt, identity, sources) -> bool:
    if type(receipt) is not dict:
        return False
    fields = {
        "schema", "passed", "phase", "scope", "tests", "callback_exception_observed", "cases",
        "stage_starts", "collection_count", "collected_exact_cases", "recorder_invalid", "current_case",
        "repository", "source_sha", "run_id", "run_attempt", "producer_python_version", "source_files",
        "pyqt6_distribution_version", "qt_runtime_version", "pyqt_runtime_version", "pytest_exit_code",
        "bounded_pytest_output_sha256", "bounded_pytest_output_exceeded", "private_junit_projection",
        "source_unchanged",
    }
    junit = receipt.get("private_junit_projection")
    if set(receipt) != fields or type(junit) is not dict or set(junit) != {"validated", "cases", "sha256"}:
        return False
    try:
        for field in ("pyqt6_distribution_version", "qt_runtime_version", "pyqt_runtime_version"):
            version_text(receipt.get(field))
    except ValueError:
        return False
    return (
        receipt.get("schema") == "row.gui-scroll-owner-lifetime.v1"
        and receipt.get("passed") is True and receipt.get("phase") == "completed"
        and receipt.get("tests") == list(TEST_NODES)
        and receipt.get("scope") == SCOPE and receipt.get("current_case") in TEST_NODES
        and receipt.get("cases") == {node: dict.fromkeys(STAGES, "passed") for node in TEST_NODES}
        and type(receipt.get("stage_starts")) is int and receipt["stage_starts"] == 18
        and type(receipt.get("collection_count")) is int and receipt["collection_count"] == 6
        and receipt.get("collected_exact_cases") is True and receipt.get("recorder_invalid") is False
        and receipt.get("callback_exception_observed") is False
        and type(receipt.get("pytest_exit_code")) is int and receipt["pytest_exit_code"] == 0
        and receipt.get("bounded_pytest_output_exceeded") is False
        and receipt.get("source_unchanged") is True and same_source_pins(receipt.get("source_files"), sources)
        and all(receipt.get(key) == value for key, value in identity.items())
        and type(receipt.get("producer_python_version")) is str
        and re.fullmatch(r"3\.12\.[0-9]{1,6}", receipt["producer_python_version"]) is not None
        and type(receipt.get("bounded_pytest_output_sha256")) is str
        and re.fullmatch(r"[0-9a-f]{64}", receipt["bounded_pytest_output_sha256"]) is not None
        and junit.get("validated") is True and type(junit.get("cases")) is int and junit["cases"] == 6
        and type(junit.get("sha256")) is str and re.fullmatch(r"[0-9a-f]{64}", junit["sha256"]) is not None
    )


def run_gate(output: Path, private_junit: Path) -> int:
    receipt: dict[str, object] = {
        "schema": "row.gui-scroll-owner-lifetime.v1", "passed": False, "phase": "initialized",
        "scope": SCOPE,
        "tests": list(TEST_NODES), "callback_exception_observed": False,
    }
    recorder = CaseRecorder()

    def checkpoint(phase: str) -> None:
        if phase not in PHASES:
            raise ValueError("public-receipt-bound")
        receipt.update({
            "phase": phase, "cases": {node: dict(reports) for node, reports in recorder.reports.items()},
            "stage_starts": len(recorder.started), "collection_count": recorder.collection_count,
            "collected_exact_cases": recorder.collected == list(TEST_NODES) and not recorder.invalid,
            "recorder_invalid": recorder.invalid, "current_case": recorder.current_case,
        })
        persist_receipt(output, receipt)

    recorder.checkpoint = checkpoint
    try:
        checkpoint("initialized")
        receipt.update(host_identity(dict(os.environ), os.environ.get("GITHUB_SHA", "")))
        if sys.version_info[:2] != (3, 12):
            raise ValueError("coverage-python-version-refused")
        if os.environ.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD") != "1" or not sys.dont_write_bytecode:
            raise ValueError("deterministic-pytest-environment-refused")
        if not private_junit.is_absolute() or private_junit.name != "junit.xml" or not private_junit.parent.resolve(strict=True).is_relative_to(runner_temp_root()):
            raise ValueError("private-junit-location-refused")
        receipt["producer_python_version"] = ".".join(map(str, sys.version_info[:3]))
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=30, check=True).stdout.strip()
        receipt.update(host_identity(dict(os.environ), head))
        checkpoint("host-bound")
        before = source_binding(ROOT)
        receipt["source_files"] = before
        checkpoint("source-bound")
        if importlib.util.find_spec("PyQt6") is None:
            raise ValueError("pyqt6-unavailable")
        receipt["pyqt6_distribution_version"] = version_text(importlib.metadata.version("PyQt6"))
        from PyQt6.QtCore import PYQT_VERSION_STR, qVersion

        receipt["qt_runtime_version"] = version_text(qVersion())
        receipt["pyqt_runtime_version"] = version_text(PYQT_VERSION_STR)
        import pytest

        captured = BoundedOutput()
        original_hook = sys.excepthook

        def exception_hook(kind, value, traceback):
            receipt["callback_exception_observed"] = True
            receipt["callback_observed_phase"] = receipt["phase"]
            receipt["callback_exception"] = callback_exception_projection(kind, traceback)
            checkpoint("uncaught-callback-exception")
            original_hook(kind, value, traceback)

        with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
            checkpoint("before-pytest")
            sys.excepthook = exception_hook
            try:
                raw_exit_code = pytest.main(pytest_arguments(private_junit), plugins=[recorder])
            finally:
                sys.excepthook = original_hook
        if not isinstance(raw_exit_code, int) or isinstance(raw_exit_code, bool) or not 0 <= raw_exit_code <= 5:
            raise ValueError("six-cases-failed-skipped-or-incomplete")
        exit_code = int(raw_exit_code)
        receipt.update({
            "pytest_exit_code": exit_code,
            "bounded_pytest_output_sha256": hashlib.sha256(captured.raw).hexdigest(),
            "bounded_pytest_output_exceeded": captured.exceeded,
        })
        checkpoint("pytest-returned")
        junit = validate_observation(
            recorder, exit_code, captured.exceeded, receipt["callback_exception_observed"],
            read_regular(private_junit, 256 * 1024), before, source_binding(ROOT),
        )
        receipt["private_junit_projection"] = junit
        receipt["source_unchanged"] = True
        receipt["passed"] = True
        checkpoint("completed")
    except (Exception, SystemExit, KeyboardInterrupt) as error:
        receipt["passed"] = False
        receipt["refused_from_phase"] = receipt["phase"]
        receipt["refusal_code"] = safe_refusal(error)
        try:
            checkpoint("refused")
        except (OSError, ValueError):
            print("GUI scroll lifetime: refused (public receipt unavailable)")
            return 1
    print("GUI scroll lifetime: " + ("passed" if receipt["passed"] else "refused"))
    return 0 if receipt["passed"] else 1


def run_owned_gate(output: Path) -> int:
    owned_output = output.with_name(output.stem + "-owned-process.json")
    owned: dict[str, object] = {
        "schema": "row.gui-scroll-owner-lifetime-owned-host.v1", "passed": False,
        "phase": "initialized", "timeout_seconds": 150, "child_os_stdio": "discarded",
    }
    try:
        persist_receipt(owned_output, owned)
        identity = host_identity(dict(os.environ), os.environ.get("GITHUB_SHA", ""))
        owned.update(identity)
        if sys.version_info[:2] != (3, 12):
            raise ValueError("coverage-python-version-refused")
        if os.environ.get("PYTEST_DISABLE_PLUGIN_AUTOLOAD") != "1" or not sys.dont_write_bytecode:
            raise ValueError("deterministic-pytest-environment-refused")
        before = source_binding(ROOT)
        owned["source_files"] = before
        # Replace stale successes before creating the owned Qt process.
        persist_receipt(output, {
            "schema": "row.gui-scroll-owner-lifetime.v1", "tests": list(TEST_NODES),
            "passed": False, "phase": "initialized", "callback_exception_observed": False,
        })
        owned["phase"] = "child-started"
        persist_receipt(owned_output, owned)
        with tempfile.TemporaryDirectory(prefix="row-scroll-junit-", dir=runner_temp_root()) as private_directory:
            private_junit = Path(private_directory) / "junit.xml"
            try:
                result = subprocess.run(
                    [sys.executable, "-B", str(Path(__file__).resolve()), "--out", str(output),
                     "--child", "--private-junit", str(private_junit)],
                    cwd=ROOT, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    timeout=150, check=False,
                )
                owned["returncode"] = result.returncode
                owned["timed_out"] = False
            except subprocess.TimeoutExpired:
                owned["returncode"] = None
                owned["timed_out"] = True
        owned["private_junit_cleanup_completed"] = True
        after = source_binding(ROOT)
        owned["source_unchanged"] = before == after
        raw = read_regular(output, 16 * 1024)
        owned["child_result_sha256"] = hashlib.sha256(raw).hexdigest()
        child_receipt = parse_receipt(raw)
        valid = validate_completed(child_receipt, identity, before)
        owned["child_completed_result_validated"] = valid
        owned["passed"] = owned["returncode"] == 0 and not owned["timed_out"] and before == after and valid
        owned["phase"] = "completed" if owned["passed"] else "refused"
        if not owned["passed"]:
            owned["refusal_code"] = "six-cases-failed-skipped-or-incomplete"
        persist_receipt(owned_output, owned)
    except (Exception, SystemExit, KeyboardInterrupt) as error:
        owned["passed"] = False
        owned["phase"] = "refused"
        owned["refusal_code"] = safe_refusal(error)
        try:
            persist_receipt(owned_output, owned)
        except (OSError, ValueError):
            print("GUI scroll lifetime: refused (owned receipt unavailable)")
            return 1
    print("GUI scroll lifetime: " + ("passed" if owned["passed"] else "refused"))
    return 0 if owned["passed"] else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--child", action="store_true")
    parser.add_argument("--private-junit", type=Path)
    args = parser.parse_args(argv)
    if args.child:
        if args.private_junit is None:
            print("GUI scroll lifetime: refused (private JUnit unavailable)")
            return 1
        return run_gate(args.out, args.private_junit)
    return run_owned_gate(args.out)


if __name__ == "__main__":
    raise SystemExit(main())

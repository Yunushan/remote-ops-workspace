"""Run one hosted Qt ownership case and publish its bounded no-skip result."""

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
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TEST_NODE = "tests/test_gui_terminal_io_edges.py::test_shared_terminal_component_keeps_two_window_ownership_independent"
SOURCE_FILES = (
    "src/remote_ops_workspace/gui.py",
    "src/remote_ops_workspace/gui_workspace.py",
    "src/remote_ops_workspace/gui_terminal.py",
    "src/remote_ops_workspace/gui_processes.py",
    "src/remote_ops_workspace/gui_values.py",
    "src/remote_ops_workspace/terminal_output.py",
    "tests/test_gui_terminal_io_edges.py",
)


class CaseRecorder:
    def __init__(self) -> None:
        self.collected: list[str] = []
        self.reports: dict[str, str] = {}
        self.invalid = False
        self.checkpoint = None

    def pytest_collection_finish(self, session) -> None:
        self.collected = [item.nodeid for item in session.items[:2]]
        self.invalid |= len(session.items) != 1 or self.collected != [TEST_NODE]
        self._checkpoint("collection-complete")

    def pytest_runtest_logreport(self, report) -> None:
        node = getattr(report, "nodeid", None)
        when = getattr(report, "when", None)
        outcome = getattr(report, "outcome", None)
        if node != TEST_NODE or type(when) is not str or when not in {"setup", "call", "teardown"} or when in self.reports or type(outcome) is not str or outcome not in {"passed", "skipped", "failed"}:
            self.invalid = True
            self._checkpoint("report-refused")
            return
        self.reports[when] = outcome
        self.invalid |= hasattr(report, "wasxfail")
        self._checkpoint(when + "-reported")

    def _checkpoint(self, phase):
        if self.checkpoint is not None:
            self.checkpoint(phase)

    def _stage_started(self, item, stage):
        if getattr(item, "nodeid", None) != TEST_NODE:
            self.invalid = True
            self._checkpoint("unexpected-case")
        else:
            if stage == "call":
                item._row_ownership_checkpoint = self._checkpoint
            self._checkpoint(stage + "-started")

    def pytest_runtest_setup(self, item):
        self._stage_started(item, "setup")

    def pytest_runtest_call(self, item):
        self._stage_started(item, "call")

    def pytest_runtest_teardown(self, item):
        self._stage_started(item, "teardown")

    def passed(self, exit_code) -> bool:
        return type(exit_code) is int and exit_code == 0 and not self.invalid and self.collected == [TEST_NODE] and self.reports == dict.fromkeys(("setup", "call", "teardown"), "passed")


class BoundedOutput(io.TextIOBase):
    def __init__(self) -> None:
        self.text = ""
        self.exceeded = False

    def write(self, value: str) -> int:
        remaining = 65536 - len(self.text)
        self.text += value[:max(0, remaining)]
        self.exceeded |= len(value) > remaining
        return len(value)

    def flush(self) -> None:
        pass


def host_identity(environment: dict[str, str], head: str) -> dict[str, str]:
    if environment.get("GITHUB_ACTIONS") != "true" or environment.get("GITHUB_REPOSITORY") != "Yunushan/remote-ops-workspace" or environment.get("RUNNER_ENVIRONMENT") != "github-hosted" or environment.get("RUNNER_OS") != "Windows":
        raise ValueError("host-identity-refused")
    sha = environment.get("GITHUB_SHA", "")
    if re.fullmatch(r"[0-9a-f]{40}", sha) is None or head != sha:
        raise ValueError("checkout-identity-refused")
    for key in ("GITHUB_RUN_ID", "GITHUB_RUN_ATTEMPT"):
        if re.fullmatch(r"[1-9][0-9]{0,19}", environment.get(key, "")) is None:
            raise ValueError("run-identity-refused")
    return {"repository": environment["GITHUB_REPOSITORY"], "source_sha": sha, "run_id": environment["GITHUB_RUN_ID"], "run_attempt": environment["GITHUB_RUN_ATTEMPT"]}


def source_pins(root: Path) -> dict[str, dict[str, object]]:
    import stat

    result = {}
    for name in SOURCE_FILES:
        path = root / name
        before = path.lstat()
        if not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not 0 < before.st_size <= 2 * 1024 * 1024:
            raise ValueError("source-file-bound-or-type")
        fields = ("st_dev", "st_ino", "st_mode", "st_size", "st_nlink", "st_mtime_ns", "st_ctime_ns")
        shared_fields = ("st_dev", "st_ino", "st_size", "st_mtime_ns")
        identity = tuple(getattr(before, key) for key in fields)
        with path.open("rb") as stream:
            opened = os.fstat(stream.fileno())
            if tuple(getattr(opened, key) for key in shared_fields) != tuple(getattr(before, key) for key in shared_fields):
                raise ValueError("source-file-changed")
            raw = stream.read(before.st_size + 1)
            after_fd = os.fstat(stream.fileno())
        if len(raw) != before.st_size or tuple(getattr(after_fd, key) for key in fields) != tuple(getattr(opened, key) for key in fields) or tuple(getattr(path.lstat(), key) for key in fields) != identity:
            raise ValueError("source-file-changed")
        result[name] = {"size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}
    return result


RECEIPT_LIMIT_BYTES = 16 * 1024
RECEIPT_PHASES = frozenset({
    "initialized", "host-bound", "source-bound", "before-pytest",
    "collection-complete", "setup-started", "call-started", "teardown-started",
    "setup-reported", "call-reported", "teardown-reported", "report-refused",
    "unexpected-case", "uncaught-callback-exception", "pytest-returned",
    "completed", "refused",
    "test-before-first-window", "test-first-window-created",
    "test-before-second-window", "test-second-window-created", "test-panes-created",
    "test-before-first-close", "test-first-window-closed",
    "test-before-first-delete", "test-before-first-deferred-delete",
    "test-after-first-deferred-delete", "test-first-delete-events-completed",
    "test-before-first-process-events",
    "test-final-window-close", "test-before-final-deferred-delete",
    "test-after-final-deferred-delete",
})


def persist_receipt(output: Path, receipt: dict[str, object]) -> None:
    """Replace one bounded public checkpoint after flushing its file contents.

    This keeps the last complete checkpoint available after process termination;
    it does not claim power-loss durability or protection against a hostile host.
    """
    import tempfile

    raw = (json.dumps(receipt, indent=2, sort_keys=True) + "\n").encode("utf-8")
    if len(raw) > RECEIPT_LIMIT_BYTES:
        raise ValueError("public-receipt-bound")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="wb", dir=output.parent, prefix=".gui-ownership-", suffix=".partial", delete=False) as stream:
            temporary = Path(stream.name)
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output)
        temporary = None
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def callback_exception_projection(exc_type, traceback) -> dict[str, object]:
    """Publish fixed exception kinds and bound source lines; never messages/locals."""
    allowed = {"NameError", "UnboundLocalError", "AttributeError", "TypeError", "ValueError", "RuntimeError", "AssertionError", "SystemExit", "KeyboardInterrupt"}
    kind = getattr(exc_type, "__name__", None)
    result: dict[str, object] = {"kind": kind if type(kind) is str and kind in allowed else "other", "source_frames": [], "traceback_truncated": False}
    paths = {os.path.normcase(os.path.abspath(ROOT / name)): name for name in SOURCE_FILES}
    count = 0
    while traceback is not None and count < 32:
        filename = traceback.tb_frame.f_code.co_filename
        source = paths.get(os.path.normcase(os.path.abspath(filename))) if type(filename) is str else None
        line = traceback.tb_lineno
        if source is not None and type(line) is int and 1 <= line <= 100000:
            result["source_frames"].append({"source": source, "line": line})
        traceback = traceback.tb_next
        count += 1
    result["traceback_truncated"] = traceback is not None
    return result


def _safe_refusal(exc: BaseException) -> str:
    allowed = {"host-identity-refused", "checkout-identity-refused", "run-identity-refused", "coverage-python-version-refused", "source-file-bound-or-type", "source-file-changed", "pyqt6-unavailable", "pyqt6-version-refused", "selected-case-failed-skipped-or-incomplete", "uncaught-callback-exception-observed", "public-receipt-bound"}
    if isinstance(exc, ValueError) and str(exc) in allowed:
        return str(exc)
    if isinstance(exc, (SystemExit, KeyboardInterrupt)):
        return "hosted-selected-case-abnormal-python-exit"
    return "hosted-selected-case-observation-failed"


def run_gate(output: Path) -> int:
    receipt: dict[str, object] = {"schema": "row.gui-two-window-ownership.v1", "scope": "one actual Qt ownership case with controlled no-child processes; no ConPTY/SSH/packaging/approval claim", "test": TEST_NODE, "passed": False, "phase": "initialized", "callback_exception_observed": False}
    recorder = CaseRecorder()

    def checkpoint(phase):
        if phase not in RECEIPT_PHASES:
            raise ValueError("public-receipt-bound")
        receipt["phase"] = phase
        receipt["stages"] = dict(recorder.reports)
        receipt["collected_exact_case"] = recorder.collected == [TEST_NODE] and not recorder.invalid
        receipt["recorder_invalid"] = recorder.invalid
        persist_receipt(output, receipt)

    recorder.checkpoint = checkpoint
    try:
        # The refused initial checkpoint precedes Git, pytest and all Qt work.
        checkpoint("initialized")
        receipt.update(host_identity(dict(os.environ), os.environ.get("GITHUB_SHA", "")))
        if sys.version_info[:2] != (3, 12):
            raise ValueError("coverage-python-version-refused")
        receipt["producer_python_version"] = ".".join(map(str, sys.version_info[:3]))
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=30, check=True).stdout.strip()
        receipt.update(host_identity(dict(os.environ), head))
        checkpoint("host-bound")
        before = source_pins(ROOT)
        receipt["source_files"] = before
        checkpoint("source-bound")
        if importlib.util.find_spec("PyQt6") is None:
            raise ValueError("pyqt6-unavailable")
        version = importlib.metadata.version("PyQt6")
        if type(version) is not str or len(version) > 64 or re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,3}", version) is None:
            raise ValueError("pyqt6-version-refused")
        receipt["pyqt6_distribution_version"] = version
        import pytest

        captured = BoundedOutput()
        original_exception_hook = sys.excepthook

        def exception_hook(exc_type, exc_value, traceback):
            receipt["callback_exception_observed"] = True
            receipt["callback_observed_phase"] = receipt["phase"]
            receipt["callback_exception"] = callback_exception_projection(exc_type, traceback)
            checkpoint("uncaught-callback-exception")
            # Retain Python's original uncaught-exception behavior. Its raw
            # diagnostic text remains inside the bounded private capture.
            original_exception_hook(exc_type, exc_value, traceback)

        with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
            checkpoint("before-pytest")
            sys.excepthook = exception_hook
            try:
                raw_exit_code = pytest.main(["-q", "-rA", TEST_NODE], plugins=[recorder])
            finally:
                sys.excepthook = original_exception_hook
            if not isinstance(raw_exit_code, int) or isinstance(raw_exit_code, bool) or not 0 <= raw_exit_code <= 5:
                raise ValueError("selected-case-failed-skipped-or-incomplete")
            exit_code = int(raw_exit_code)
        receipt["pytest_exit_code"] = exit_code
        receipt["bounded_pytest_output_sha256"] = hashlib.sha256(captured.text.encode("utf-8")).hexdigest()
        receipt["bounded_pytest_output_exceeded"] = captured.exceeded
        checkpoint("pytest-returned")
        if receipt["callback_exception_observed"]:
            raise ValueError("uncaught-callback-exception-observed")
        if captured.exceeded or not recorder.passed(exit_code):
            raise ValueError("selected-case-failed-skipped-or-incomplete")
        if source_pins(ROOT) != before:
            raise ValueError("source-file-changed")
        receipt["source_unchanged"] = True
        receipt["passed"] = True
        checkpoint("completed")
    except (Exception, SystemExit, KeyboardInterrupt) as exc:
        receipt["passed"] = False
        receipt["refused_from_phase"] = receipt["phase"]
        receipt["refusal_code"] = _safe_refusal(exc)
        try:
            checkpoint("refused")
        except (OSError, ValueError):
            print("GUI two-window ownership: refused (public receipt unavailable)")
            return 1
    print("GUI two-window ownership: " + ("passed" if receipt["passed"] else "refused"))
    return 0 if receipt["passed"] else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    return run_gate(args.out)


if __name__ == "__main__":
    raise SystemExit(main())

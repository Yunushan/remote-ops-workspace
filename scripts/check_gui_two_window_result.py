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

    def pytest_collection_finish(self, session) -> None:
        self.collected = [item.nodeid for item in session.items[:2]]
        self.invalid |= len(session.items) != 1 or self.collected != [TEST_NODE]

    def pytest_runtest_logreport(self, report) -> None:
        node = getattr(report, "nodeid", None)
        when = getattr(report, "when", None)
        outcome = getattr(report, "outcome", None)
        if node != TEST_NODE or type(when) is not str or when not in {"setup", "call", "teardown"} or when in self.reports or type(outcome) is not str or outcome not in {"passed", "skipped", "failed"}:
            self.invalid = True
            return
        self.reports[when] = outcome
        self.invalid |= hasattr(report, "wasxfail")

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


def run_gate(output: Path) -> int:
    receipt: dict[str, object] = {"schema": "row.gui-two-window-ownership.v1", "scope": "one actual Qt ownership case with controlled no-child processes; no ConPTY/SSH/packaging/approval claim", "test": TEST_NODE, "passed": False}
    try:
        # This command runs only on the guarded CI path. subprocess.run owns its leader timeout.
        receipt.update(host_identity(dict(os.environ), os.environ.get("GITHUB_SHA", "")))
        if sys.version_info[:2] != (3, 12):
            raise ValueError("coverage-python-version-refused")
        receipt["producer_python_version"] = ".".join(map(str, sys.version_info[:3]))
        head = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT, capture_output=True, text=True, timeout=30, check=True).stdout.strip()
        receipt.update(host_identity(dict(os.environ), head))
        before = source_pins(ROOT)
        receipt["source_files"] = before
        if importlib.util.find_spec("PyQt6") is None:
            raise ValueError("pyqt6-unavailable")
        version = importlib.metadata.version("PyQt6")
        if type(version) is not str or len(version) > 64 or re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,3}", version) is None:
            raise ValueError("pyqt6-version-refused")
        receipt["pyqt6_distribution_version"] = version
        import pytest

        recorder = CaseRecorder()
        captured = BoundedOutput()
        with contextlib.redirect_stdout(captured), contextlib.redirect_stderr(captured):
            raw_exit_code = pytest.main(["-q", "-rA", TEST_NODE], plugins=[recorder])
            if not isinstance(raw_exit_code, int) or isinstance(raw_exit_code, bool) or not 0 <= raw_exit_code <= 5:
                raise ValueError("selected-case-failed-skipped-or-incomplete")
            exit_code = int(raw_exit_code)
        receipt["pytest_exit_code"] = exit_code
        receipt["stages"] = recorder.reports
        receipt["collected_exact_case"] = recorder.collected == [TEST_NODE] and not recorder.invalid
        receipt["bounded_pytest_output_sha256"] = hashlib.sha256(captured.text.encode("utf-8")).hexdigest()
        receipt["bounded_pytest_output_exceeded"] = captured.exceeded
        if captured.exceeded or not recorder.passed(exit_code):
            raise ValueError("selected-case-failed-skipped-or-incomplete")
        if source_pins(ROOT) != before:
            raise ValueError("source-file-changed")
        receipt["source_unchanged"] = True
        receipt["passed"] = True
    except Exception as exc:
        allowed = {"host-identity-refused", "checkout-identity-refused", "run-identity-refused", "coverage-python-version-refused", "source-file-bound-or-type", "source-file-changed", "pyqt6-unavailable", "pyqt6-version-refused", "selected-case-failed-skipped-or-incomplete"}
        receipt["refusal_code"] = str(exc) if isinstance(exc, ValueError) and str(exc) in allowed else "hosted-selected-case-observation-failed"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print("GUI two-window ownership: " + ("passed" if receipt["passed"] else "refused"))
    return 0 if receipt["passed"] else 1


def main(argv=None) -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args(argv)
    return run_gate(args.out)


if __name__ == "__main__":
    raise SystemExit(main())

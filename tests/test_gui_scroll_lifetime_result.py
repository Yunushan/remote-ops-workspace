from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import stat
import sys
import xml.etree.ElementTree as ET
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def gate(monkeypatch):
    """Load actual stdlib checker definitions; never execute host/Qt paths."""

    project = Path(__file__).resolve().parents[1]
    shared_path = project / "scripts/check_gui_two_window_result.py"
    if not shared_path.exists():
        shared_path = project.parent / "baseline/scripts/check_gui_two_window_result.py"
    shared_spec = importlib.util.spec_from_file_location("check_gui_two_window_result", shared_path)
    shared = importlib.util.module_from_spec(shared_spec)
    monkeypatch.setitem(sys.modules, "check_gui_two_window_result", shared)
    shared_spec.loader.exec_module(shared)
    spec = importlib.util.spec_from_file_location("row_scroll_gate_under_test", project / "scripts/check_gui_scroll_lifetime_result.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _report(node, stage="call", outcome="passed", **extra):
    return SimpleNamespace(nodeid=node, when=stage, outcome=outcome, **extra)


def _complete(gate):
    recorder = gate.CaseRecorder()
    recorder.pytest_collection_finish(SimpleNamespace(items=[SimpleNamespace(nodeid=node) for node in gate.TEST_NODES]))
    for node in gate.TEST_NODES:
        for stage in gate.STAGES:
            getattr(recorder, "pytest_runtest_" + stage)(SimpleNamespace(nodeid=node))
            recorder.pytest_runtest_logreport(_report(node, stage))
    return recorder


def _junit(gate):
    root = ET.Element("testsuites")
    suite = ET.SubElement(root, "testsuite", tests="6", errors="0", failures="0", skipped="0", hostname="private host", timestamp="private timestamp")
    for node in gate.TEST_NODES:
        case = ET.SubElement(suite, "testcase", classname="tests.test_gui_terminal_io_edges", name=node.split("::", 1)[1], file="private absolute path")
        ET.SubElement(case, "system-out").text = "private diagnostic never projected"
    return ET.tostring(root, encoding="utf-8")


def _success(gate):
    identity = {"repository": "Yunushan/remote-ops-workspace", "source_sha": "a" * 40, "run_id": "123", "run_attempt": "1"}
    sources = {"fixed-source": {"size": 50, "sha256": "b" * 64}}
    receipt = {
        "schema": "row.gui-scroll-owner-lifetime.v1", "passed": True, "phase": "completed", "scope": gate.SCOPE,
        "tests": list(gate.TEST_NODES), "cases": copy.deepcopy(_complete(gate).reports),
        "stage_starts": 18, "collection_count": 6, "collected_exact_cases": True,
        "recorder_invalid": False, "current_case": gate.TEST_NODES[-1],
        "callback_exception_observed": False, "pytest_exit_code": 0, "source_unchanged": True,
        "source_files": sources, "producer_python_version": "3.12.10",
        "pyqt6_distribution_version": "6.11.0", "qt_runtime_version": "6.11.0", "pyqt_runtime_version": "6.11.0",
        "bounded_pytest_output_sha256": "c" * 64, "bounded_pytest_output_exceeded": False,
        "private_junit_projection": gate.validate_junit(_junit(gate)), **identity,
    }
    return receipt, identity, sources


def test_recorder_requires_all_eighteen_actual_started_passed_stages(gate):
    recorder = _complete(gate)
    assert recorder.passed(0)
    assert len(recorder.started) == 18
    assert sum(map(len, recorder.reports.values())) == 18


@pytest.mark.parametrize("mutation", ["missing", "extra", "duplicate", "unknown", "reordered"])
def test_collection_refuses_any_nonliteral_or_incomplete_set(gate, mutation):
    nodes = list(gate.TEST_NODES)
    if mutation == "missing":
        nodes.pop()
    elif mutation == "extra":
        nodes.append("private unexpected node")
    elif mutation == "duplicate":
        nodes[-1] = nodes[0]
    elif mutation == "unknown":
        nodes[-1] = "private unexpected node"
    else:
        nodes.reverse()
    recorder = gate.CaseRecorder()
    recorder.pytest_collection_finish(SimpleNamespace(items=[SimpleNamespace(nodeid=node) for node in nodes]))
    assert recorder.invalid
    assert not recorder.passed(0)
    assert "private unexpected node" not in recorder.collected


@pytest.mark.parametrize("mutation", ["missing", "duplicate", "node", "stage", "outcome", "xfail", "without-start", "duplicate-start"])
def test_stage_recorder_refuses_malformed_duplicate_missing_or_xfail(gate, mutation):
    recorder = _complete(gate)
    node = gate.TEST_NODES[0]
    if mutation == "missing":
        del recorder.reports[node]["call"]
    elif mutation == "duplicate-start":
        recorder.pytest_runtest_call(SimpleNamespace(nodeid=node))
    else:
        report = _report(node)
        if mutation == "node":
            report.nodeid = "private unexpected node"
        elif mutation == "stage":
            report.when = "private stage"
        elif mutation == "outcome":
            report.outcome = "private outcome"
        elif mutation == "xfail":
            del recorder.reports[node]["call"]
            report.wasxfail = "private reason"
        elif mutation == "without-start":
            del recorder.reports[node]["call"]
            recorder.started.remove((node, "call"))
        recorder.pytest_runtest_logreport(report)
    assert not recorder.passed(0)
    assert all(stage in gate.STAGES for reports in recorder.reports.values() for stage in reports)


@pytest.mark.parametrize("stage", ["setup", "call", "teardown"])
@pytest.mark.parametrize("outcome", ["skipped", "failed"])
def test_any_nonpassing_stage_refuses_even_exit_zero(gate, stage, outcome):
    recorder = _complete(gate)
    recorder.reports[gate.TEST_NODES[0]][stage] = outcome
    assert not recorder.passed(0)


@pytest.mark.parametrize("exit_code", [True, False, None, "0", 1, 6])
def test_exit_code_must_be_actual_integer_zero(gate, exit_code):
    assert not _complete(gate).passed(exit_code)


def test_junit_public_projection_drops_all_raw_metadata_and_diagnostics(gate):
    raw = _junit(gate)
    projected = gate.validate_junit(raw)
    assert projected == {"validated": True, "cases": 6, "sha256": hashlib.sha256(raw).hexdigest()}
    assert "private" not in json.dumps(projected)


@pytest.mark.parametrize("mutation", ["empty", "size", "utf8", "nul", "doctype", "entity", "syntax"])
def test_junit_refuses_malformed_or_unbounded_input(gate, mutation):
    raw = _junit(gate)
    if mutation == "empty":
        raw = b""
    elif mutation == "size":
        raw += b" " * (256 * 1024)
    elif mutation == "utf8":
        raw += b"\xff"
    elif mutation == "nul":
        raw += b"\x00"
    elif mutation == "doctype":
        raw = b'<!DOCTYPE testsuites [<!ENTITY x "private">]>' + raw
    elif mutation == "entity":
        raw = b'<!-- <!ENTITY x "private"> -->' + raw
    else:
        raw = b"<testsuites>"
    with pytest.raises(ValueError, match="^junit-result-refused$"):
        gate.validate_junit(raw)


@pytest.mark.parametrize("mutation", ["missing", "extra", "duplicate", "failure", "error", "skip", "nested", "classname", "name", "counter", "suite"])
def test_junit_requires_six_unique_matching_cases_without_hidden_failures(gate, mutation):
    root = ET.fromstring(_junit(gate))
    suite = root[0]
    if mutation == "missing":
        suite.remove(suite[-1])
    elif mutation == "extra":
        suite.append(copy.deepcopy(suite[0]))
    elif mutation == "duplicate":
        suite[-1].set("name", suite[0].get("name"))
    elif mutation in {"failure", "error", "skip"}:
        ET.SubElement(suite[0], {"skip": "skipped"}.get(mutation, mutation)).text = "private diagnostic"
    elif mutation == "nested":
        ET.SubElement(suite[0][0], "failure").text = "private hidden failure"
    elif mutation == "classname":
        suite[0].set("classname", "other")
    elif mutation == "name":
        suite[0].set("name", "unknown")
    elif mutation == "counter":
        suite.set("failures", "1")
    else:
        root.append(ET.Element("testsuite"))
    with pytest.raises(ValueError, match="^junit-result-refused$"):
        gate.validate_junit(ET.tostring(root, encoding="utf-8"))


@pytest.mark.parametrize("mutation", ["source", "output", "callback", "callback-type", "output-type", "report"])
def test_observation_refuses_source_drift_output_overflow_or_callback(gate, mutation):
    recorder = _complete(gate)
    before, after = {"pin": "same"}, {"pin": "same"}
    exceeded, callback = False, False
    if mutation == "source":
        after = {"pin": "changed"}
    elif mutation == "output":
        exceeded = True
    elif mutation == "callback":
        callback = True
    elif mutation == "callback-type":
        callback = 0
    elif mutation == "output-type":
        exceeded = 0
    else:
        recorder.reports[gate.TEST_NODES[-1]]["teardown"] = "failed"
    with pytest.raises(ValueError):
        gate.validate_observation(recorder, 0, exceeded, callback, _junit(gate), before, after)


def test_complete_consumer_requires_exact_identity_source_and_six_cases(gate):
    receipt, identity, sources = _success(gate)
    assert gate.validate_completed(receipt, identity, sources)


@pytest.mark.parametrize("mutation", ["passed", "phase", "schema", "extra", "identity", "source", "count", "count-bool", "starts", "stages", "skip", "callback", "exit-bool", "source-flag", "output", "hash", "junit-type", "junit-extra", "junit-count", "junit-hash", "python", "qt", "qt-limit", "scope", "case"])
def test_completed_consumer_refuses_bad_typed_or_unbound_receipts(gate, mutation):
    receipt, identity, sources = _success(gate)
    if mutation == "passed":
        receipt["passed"] = 1
    elif mutation == "phase":
        receipt["phase"] = "call-started"
    elif mutation == "schema":
        receipt["schema"] = "other"
    elif mutation == "extra":
        receipt["private-raw-message"] = "private"
    elif mutation == "identity":
        receipt["run_id"] = "other"
    elif mutation == "source":
        receipt["source_files"] = {}
    elif mutation in {"count", "count-bool"}:
        receipt["collection_count"] = 5 if mutation == "count" else True
    elif mutation == "starts":
        receipt["stage_starts"] = 17
    elif mutation == "stages":
        del receipt["cases"][gate.TEST_NODES[0]]["teardown"]
    elif mutation == "skip":
        receipt["cases"][gate.TEST_NODES[0]]["call"] = "skipped"
    elif mutation == "callback":
        receipt["callback_exception_observed"] = True
    elif mutation == "exit-bool":
        receipt["pytest_exit_code"] = False
    elif mutation == "source-flag":
        receipt["source_unchanged"] = False
    elif mutation == "output":
        receipt["bounded_pytest_output_exceeded"] = True
    elif mutation == "hash":
        receipt["bounded_pytest_output_sha256"] = "bad"
    elif mutation == "junit-type":
        receipt["private_junit_projection"] = None
    elif mutation == "junit-extra":
        receipt["private_junit_projection"]["raw"] = "private"
    elif mutation == "junit-count":
        receipt["private_junit_projection"]["cases"] = 5
    elif mutation == "junit-hash":
        receipt["private_junit_projection"]["sha256"] = "bad"
    elif mutation == "python":
        receipt["producer_python_version"] = "3.14.7"
    elif mutation in {"qt", "qt-limit"}:
        receipt["qt_runtime_version"] = None if mutation == "qt" else "6." + "1" * 100
    elif mutation == "scope":
        receipt["scope"] = "private other scope"
    else:
        receipt["current_case"] = "private unexpected node"
    assert not gate.validate_completed(receipt, identity, sources)


def test_capture_is_bounded_in_utf8_bytes_for_multibyte_and_huge_chunks(gate):
    output = gate.BoundedOutput()
    value = "界" * 30_000
    assert output.write(value) == len(value)
    assert len(output.raw) == 65536 and output.exceeded
    output.write("a" * 100_000)
    assert len(output.raw) == 65536


def test_command_uses_only_six_literal_nodes_verbose_and_private_junit(gate):
    private_junit = Path("/outside-upload/junit.xml")
    arguments = gate.pytest_arguments(private_junit)
    assert arguments[:4] == ["-v", "-rA", "--color=no", "--junitxml=" + str(private_junit)]
    assert arguments[4:] == list(gate.TEST_NODES)
    assert len(set(arguments[4:])) == 6


@pytest.mark.parametrize("value", [None, 6, "6", "6.11.0-private", "6." + "1" * 65])
def test_qt_version_projection_has_strict_type_grammar_and_length(gate, value):
    with pytest.raises(ValueError, match="^pyqt6-version-refused$"):
        gate.version_text(value)


def test_source_binding_adds_both_script_bytes_to_six_shared_pins(gate, monkeypatch):
    shared = {f"gui-{index}": {"size": 1, "sha256": "a" * 64} for index in range(6)}
    reads = []
    monkeypatch.setattr(gate, "source_pins", lambda root: copy.deepcopy(shared))

    def read(path, limit):
        reads.append((str(path), limit))
        return path.name.encode()

    monkeypatch.setattr(gate, "read_regular", read)
    observed = gate.source_binding(Path("/mock-source"))
    assert len(observed) == 8
    assert set(observed) == set(shared) | set(gate.EXTRA_SOURCE_FILES)
    assert len(reads) == 2 and all(limit == 2 * 1024 * 1024 for _, limit in reads)


def _fake_stat(**changes):
    fields = dict(st_dev=1, st_ino=2, st_mode=stat.S_IFREG | 0o600, st_size=3, st_nlink=1, st_mtime_ns=4, st_ctime_ns=5)
    fields.update(changes)
    return SimpleNamespace(**fields)


@pytest.mark.parametrize("mutation", ["none", "api-ctime", "fd-ctime", "path-ctime", "link", "symlink", "bound", "read-length", "cross-inode"])
def test_actual_regular_reader_retains_identity_guards_and_shared_api_fields(gate, monkeypatch, mutation):
    before, opened, after_fd, after_path = (_fake_stat() for _ in range(4))
    raw = b"abc"
    if mutation == "api-ctime":
        opened.st_ctime_ns = after_fd.st_ctime_ns = 99
    elif mutation == "fd-ctime":
        after_fd.st_ctime_ns = 99
    elif mutation == "path-ctime":
        after_path.st_ctime_ns = 99
    elif mutation == "link":
        before.st_nlink = 2
    elif mutation == "symlink":
        before.st_mode = stat.S_IFLNK | 0o777
    elif mutation == "bound":
        before.st_size = 11
    elif mutation == "read-length":
        raw = b"abcd"
    elif mutation == "cross-inode":
        opened.st_ino = 99

    class Stream:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        @staticmethod
        def fileno():
            return 7

        @staticmethod
        def read(size):
            assert size == 4
            return raw

    path_states = iter((before, after_path))
    descriptor_states = iter((opened, after_fd))
    path = SimpleNamespace(lstat=lambda: next(path_states), open=lambda _mode: Stream())
    monkeypatch.setattr(gate.os, "fstat", lambda _fd: next(descriptor_states))
    if mutation in {"none", "api-ctime"}:
        assert gate.read_regular(path, 10) == b"abc"
    else:
        with pytest.raises(ValueError):
            gate.read_regular(path, 10)


@pytest.mark.parametrize("mutation", ["none", "timeout", "exit", "incomplete", "source", "bad-json", "cleanup"])
def test_actual_owned_launcher_enforces_budget_stdio_cleanup_and_validated_child(gate, monkeypatch, mutation):
    child, identity, sources = _success(gate)
    writes, launches, cleanup = [], [], []
    monkeypatch.setattr(gate, "persist_receipt", lambda path, receipt: writes.append((path, copy.deepcopy(receipt))))
    monkeypatch.setattr(gate, "host_identity", lambda *_args: identity)
    monkeypatch.setattr(gate.sys, "version_info", (3, 12, 10))
    monkeypatch.setattr(gate.sys, "dont_write_bytecode", True)
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    bindings = iter((sources, {} if mutation == "source" else sources))
    monkeypatch.setattr(gate, "source_binding", lambda _root: next(bindings))
    monkeypatch.setattr(gate, "runner_temp_root", lambda: Path("/outside-upload"))
    if mutation == "incomplete":
        child["phase"] = "call-started"
        child["passed"] = False
    raw = b"{" if mutation == "bad-json" else json.dumps(child).encode()
    monkeypatch.setattr(gate, "read_regular", lambda _path, _limit: raw)

    class PrivateDirectory:
        def __enter__(self):
            return "/outside-upload/owned-directory"

        def __exit__(self, *_args):
            cleanup.append(True)
            if mutation == "cleanup":
                raise OSError("private cleanup error")
            return False

    monkeypatch.setattr(gate.tempfile, "TemporaryDirectory", lambda **_kwargs: PrivateDirectory())

    def launch(command, **kwargs):
        launches.append((command, kwargs))
        if mutation == "timeout":
            raise gate.subprocess.TimeoutExpired(command, 150)
        return SimpleNamespace(returncode=1 if mutation == "exit" else 0)

    monkeypatch.setattr(gate.subprocess, "run", launch)
    assert gate.run_owned_gate(Path("/mock-artifacts/gui-scroll-lifetime.json")) == (0 if mutation == "none" else 1)
    assert cleanup == [True]
    assert len(launches) == 1
    command, kwargs = launches[0]
    assert "--child" in command and "--private-junit" in command and "-B" in command
    assert command[-1] == str(Path("/outside-upload/owned-directory") / "junit.xml")
    assert kwargs["timeout"] == 150
    assert kwargs["stdin"] == kwargs["stdout"] == kwargs["stderr"] == gate.subprocess.DEVNULL
    assert writes[1][1]["passed"] is False  # stale child successes overwritten before launch
    assert writes[-1][1]["passed"] is (mutation == "none")
    assert "private cleanup error" not in json.dumps(writes[-1][1])


def test_public_refusal_projection_never_emits_exception_messages(gate):
    assert gate.safe_refusal(ValueError("junit-result-refused")) == "junit-result-refused"
    assert gate.safe_refusal(OSError("private absolute path")) == "hosted-six-cases-observation-failed"
    assert gate.safe_refusal(SystemExit("private")) == "hosted-six-cases-abnormal-python-exit"


def test_strict_receipt_parser_accepts_one_unambiguous_complete_object(gate):
    receipt, identity, sources = _success(gate)
    parsed = gate.parse_receipt(json.dumps(receipt).encode())
    assert gate.validate_completed(parsed, identity, sources)


@pytest.mark.parametrize("mutation", ["duplicate-top", "duplicate-nested", "nonfinite", "invalid", "bound", "utf8", "object-type"])
def test_strict_receipt_parser_refuses_ambiguous_or_unbounded_json(gate, mutation):
    payloads = {
        "duplicate-top": b'{"passed": false, "passed": true}',
        "duplicate-nested": b'{"source_files": {"fixed": {"size": 1, "size": 1}}}',
        "nonfinite": b'{"value": NaN}',
        "invalid": b'{',
        "bound": b'{"value": "' + b'a' * (16 * 1024) + b'"}',
        "utf8": b'\xff',
        "object-type": b'[]',
    }
    with pytest.raises(ValueError, match="^six-cases-failed-skipped-or-incomplete$"):
        gate.parse_receipt(payloads[mutation])


@pytest.mark.parametrize("mutation", ["size-float", "size-bool", "hash-subclass"])
def test_completed_consumer_requires_plain_source_pin_types(gate, mutation):
    receipt, identity, sources = _success(gate)
    if mutation == "size-bool":
        sources["fixed-source"]["size"] = 1
    receipt["source_files"] = copy.deepcopy(sources)
    if mutation == "size-float":
        receipt["source_files"]["fixed-source"]["size"] = 50.0
    elif mutation == "size-bool":
        receipt["source_files"]["fixed-source"]["size"] = True
    else:
        class HashString(str):
            pass

        receipt["source_files"]["fixed-source"]["sha256"] = HashString("b" * 64)
    assert receipt["source_files"] == sources  # equality alone would accept each bad type
    assert not gate.validate_completed(receipt, identity, sources)


def test_actual_owned_launcher_refuses_duplicate_success_key_and_cleans(gate, monkeypatch):
    child, identity, sources = _success(gate)
    raw = json.dumps(child).replace('"passed": true', '"passed": false, "passed": true', 1).encode()
    assert json.loads(raw)["passed"] is True  # previous decoder silently accepted this
    writes, cleaned = [], []
    monkeypatch.setattr(gate, "persist_receipt", lambda path, receipt: writes.append(copy.deepcopy(receipt)))
    monkeypatch.setattr(gate, "host_identity", lambda *_args: identity)
    monkeypatch.setattr(gate.sys, "version_info", (3, 12, 10))
    monkeypatch.setattr(gate.sys, "dont_write_bytecode", True)
    monkeypatch.setenv("PYTEST_DISABLE_PLUGIN_AUTOLOAD", "1")
    monkeypatch.setattr(gate, "source_binding", lambda _root: sources)
    monkeypatch.setattr(gate, "runner_temp_root", lambda: Path("/outside-upload"))
    monkeypatch.setattr(gate, "read_regular", lambda _path, _limit: raw)

    class PrivateDirectory:
        def __enter__(self):
            return "/outside-upload/owned-directory"

        def __exit__(self, *_args):
            cleaned.append(True)
            return False

    monkeypatch.setattr(gate.tempfile, "TemporaryDirectory", lambda **_kwargs: PrivateDirectory())
    monkeypatch.setattr(gate.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(returncode=0))
    assert gate.run_owned_gate(Path("/mock-artifacts/gui-scroll-lifetime.json")) == 1
    assert cleaned == [True]
    assert writes[-1]["passed"] is False
    assert writes[-1]["refusal_code"] == "six-cases-failed-skipped-or-incomplete"

from __future__ import annotations

import hashlib
import importlib.util
import json
import types
from pathlib import Path

import pytest


def checker():
    path = Path(__file__).resolve().parents[1] / "scripts/check_gui_two_window_result.py"
    spec = importlib.util.spec_from_file_location("mock_gui_two_window_checker", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def report(module, stage="call", outcome="passed", **extra):
    return types.SimpleNamespace(nodeid=module.TEST_NODE, when=stage, outcome=outcome, **extra)


def passed_recorder(module):
    recorder = module.CaseRecorder()
    recorder.pytest_collection_finish(types.SimpleNamespace(items=[types.SimpleNamespace(nodeid=module.TEST_NODE)]))
    for stage in ("setup", "call", "teardown"):
        recorder.pytest_runtest_logreport(report(module, stage))
    return recorder


def host_environment():
    return {"GITHUB_ACTIONS": "true", "GITHUB_REPOSITORY": "Yunushan/remote-ops-workspace", "RUNNER_ENVIRONMENT": "github-hosted", "RUNNER_OS": "Windows", "GITHUB_SHA": "a" * 40, "GITHUB_RUN_ID": "123", "GITHUB_RUN_ATTEMPT": "1"}


def test_case_recorder_requires_exact_case_and_three_passed_stages():
    module = checker()
    recorder = passed_recorder(module)
    assert recorder.passed(0) is True
    assert recorder.collected == [module.TEST_NODE]
    assert recorder.reports == dict.fromkeys(("setup", "call", "teardown"), "passed")
    for exit_code in (1, -1, False, None, "0"):
        assert recorder.passed(exit_code) is False


@pytest.mark.parametrize("outcome", ["skipped", "failed", "unknown", None, []])
def test_case_recorder_refuses_every_skip_failure_or_unknown_outcome(outcome):
    module = checker()
    recorder = module.CaseRecorder()
    recorder.pytest_collection_finish(types.SimpleNamespace(items=[types.SimpleNamespace(nodeid=module.TEST_NODE)]))
    recorder.pytest_runtest_logreport(report(module, "setup"))
    recorder.pytest_runtest_logreport(report(module, "call", outcome))
    recorder.pytest_runtest_logreport(report(module, "teardown"))
    assert recorder.passed(0) is False


@pytest.mark.parametrize("mutation", ["duplicate-stage", "wrong-node", "unknown-stage", "xfail", "malformed", "missing-stage", "extra-case", "no-case", "wrong-case"])
def test_case_recorder_refuses_duplicate_missing_malformed_or_unexpected_reports(mutation):
    module = checker()
    recorder = passed_recorder(module)
    if mutation == "duplicate-stage":
        recorder.pytest_runtest_logreport(report(module))
    elif mutation == "wrong-node":
        recorder.pytest_runtest_logreport(types.SimpleNamespace(nodeid="private-unexpected-case", when="call", outcome="passed"))
    elif mutation == "unknown-stage":
        recorder.pytest_runtest_logreport(report(module, "unknown"))
    elif mutation == "xfail":
        recorder = module.CaseRecorder()
        recorder.pytest_collection_finish(types.SimpleNamespace(items=[types.SimpleNamespace(nodeid=module.TEST_NODE)]))
        for stage in ("setup", "call", "teardown"):
            recorder.pytest_runtest_logreport(report(module, stage, wasxfail="private-xfail-reason"))
    elif mutation == "malformed":
        recorder.pytest_runtest_logreport(object())
    elif mutation == "missing-stage":
        del recorder.reports["teardown"]
    else:
        names = [module.TEST_NODE, module.TEST_NODE] if mutation == "extra-case" else [] if mutation == "no-case" else ["other-test"]
        recorder.pytest_collection_finish(types.SimpleNamespace(items=[types.SimpleNamespace(nodeid=name) for name in names]))
    assert recorder.passed(0) is False
    assert len(recorder.collected) <= 2
    assert len(recorder.reports) <= 3


@pytest.mark.parametrize("key,value", [("GITHUB_ACTIONS", "false"), ("GITHUB_REPOSITORY", "other/repository"), ("RUNNER_ENVIRONMENT", "self-hosted"), ("RUNNER_OS", "Linux"), ("GITHUB_SHA", "A" * 40), ("GITHUB_RUN_ID", "0"), ("GITHUB_RUN_ID", "1\n"), ("GITHUB_RUN_ATTEMPT", "-1")])
def test_host_identity_rejects_other_hosts_and_malformed_run_identity(key, value):
    module = checker()
    environment = host_environment()
    environment[key] = value
    with pytest.raises(ValueError):
        module.host_identity(environment, environment["GITHUB_SHA"])


def test_host_identity_requires_actual_checkout_sha():
    module = checker()
    result = module.host_identity(host_environment(), "a" * 40)
    assert result == {"repository": "Yunushan/remote-ops-workspace", "source_sha": "a" * 40, "run_id": "123", "run_attempt": "1"}
    with pytest.raises(ValueError, match="checkout-identity-refused"):
        module.host_identity(host_environment(), "b" * 40)


def make_sources(module, root):
    for index, name in enumerate(module.SOURCE_FILES):
        path = root / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(("# inert public fixture " + str(index) + "\n").encode())


def test_source_pins_hash_only_fixed_bounded_regular_files(tmp_path):
    module = checker()
    make_sources(module, tmp_path)
    pins = module.source_pins(tmp_path)
    assert set(pins) == set(module.SOURCE_FILES)
    for name, row in pins.items():
        raw = (tmp_path / name).read_bytes()
        assert row == {"size": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


@pytest.mark.parametrize("mutation", ["empty", "large", "hardlink", "symlink-mode", "changed-fd"])
def test_source_pins_refuse_types_bounds_links_and_read_identity_changes(tmp_path, monkeypatch, mutation):
    import stat

    module = checker()
    make_sources(module, tmp_path)
    path = tmp_path / module.SOURCE_FILES[0]
    if mutation == "empty":
        path.write_bytes(b"")
    elif mutation == "large":
        path.write_bytes(b"x" * (2 * 1024 * 1024 + 1))
    else:
        original = path.lstat()
        fields = ("st_dev", "st_ino", "st_mode", "st_size", "st_nlink", "st_mtime_ns", "st_ctime_ns")
        values = {name: getattr(original, name) for name in fields}
        if mutation == "hardlink":
            values["st_nlink"] = 2
        elif mutation == "symlink-mode":
            values["st_mode"] = stat.S_IFLNK | 0o644
        else:
            values["st_size"] += 1
        if mutation == "changed-fd":
            monkeypatch.setattr(module.os, "fstat", lambda _fd: types.SimpleNamespace(**values))
        else:
            original_lstat = Path.lstat
            monkeypatch.setattr(Path, "lstat", lambda self: types.SimpleNamespace(**values) if self == path else original_lstat(self))
    with pytest.raises(ValueError, match="source-file-"):
        module.source_pins(tmp_path)


def mocked_hosted_gate(module, tmp_path, monkeypatch, behavior="passed"):
    import pytest as pytest_module

    make_sources(module, tmp_path)
    monkeypatch.setattr(module, "ROOT", tmp_path)
    for key, value in host_environment().items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr(module.sys, "version_info", (3, 12, 13))
    monkeypatch.setattr(module.subprocess, "run", lambda *_args, **_kwargs: types.SimpleNamespace(stdout="a" * 40 + "\n"))
    monkeypatch.setattr(module.importlib.util, "find_spec", lambda _name: None if behavior == "no-qt" else object())
    monkeypatch.setattr(module.importlib.metadata, "version", lambda _name: "9" * 65 + ".0" if behavior == "oversized-qt-version" else "6.11.0" if behavior != "bad-qt-version" else "private-version-reason")

    def mocked_main(arguments, *, plugins):
        assert arguments == ["-q", "-rA", module.TEST_NODE]
        assert len(plugins) == 1
        recorder = plugins[0]
        recorder.pytest_collection_finish(types.SimpleNamespace(items=[types.SimpleNamespace(nodeid=module.TEST_NODE)]))
        for stage in ("setup", "call", "teardown"):
            if behavior == "missing-teardown" and stage == "teardown":
                continue
            recorder.pytest_runtest_logreport(report(module, stage, "skipped" if behavior == "skip" and stage == "call" else "passed"))
        if behavior == "excess-output":
            print("x" * 65537)
        else:
            print("private-fixture-diagnostics")
        return 1 if behavior == "nonzero" else 999999999999999999999 if behavior == "oversized-exit" else False if behavior == "bool-exit" else 0

    monkeypatch.setattr(pytest_module, "main", mocked_main)
    return tmp_path / "public-result.json"


def test_source_pins_keep_same_api_ctime_guards_without_equating_stat_apis(tmp_path, monkeypatch):
    module = checker()
    make_sources(module, tmp_path)
    original = module.os.fstat
    fields = ("st_dev", "st_ino", "st_mode", "st_size", "st_nlink", "st_mtime_ns", "st_ctime_ns")

    def different_api(fd):
        row = original(fd)
        values = {field: getattr(row, field) for field in fields}
        values["st_ctime_ns"] += 100
        return types.SimpleNamespace(**values)

    with monkeypatch.context() as scoped:
        scoped.setattr(module.os, "fstat", different_api)
        assert set(module.source_pins(tmp_path)) == set(module.SOURCE_FILES)
    calls = []

    def changed_during_read(fd):
        calls.append(fd)
        row = different_api(fd)
        row.st_ctime_ns += len(calls)
        return row

    with monkeypatch.context() as scoped:
        scoped.setattr(module.os, "fstat", changed_during_read)
        with pytest.raises(ValueError, match="source-file-changed"):
            module.source_pins(tmp_path)


def test_mocked_hosted_gate_publishes_pass_only_for_exact_complete_case(tmp_path, monkeypatch):
    module = checker()
    target = mocked_hosted_gate(module, tmp_path, monkeypatch)
    assert module.run_gate(target) == 0
    receipt = json.loads(target.read_text())
    assert receipt["passed"] is True
    assert receipt["source_unchanged"] is True
    assert receipt["collected_exact_case"] is True
    assert receipt["stages"] == dict.fromkeys(("setup", "call", "teardown"), "passed")
    assert receipt["producer_python_version"] == "3.12.13"
    assert "private-" not in target.read_text()
    assert len(receipt["bounded_pytest_output_sha256"]) == 64


@pytest.mark.parametrize("behavior", ["skip", "nonzero", "bool-exit", "oversized-exit", "missing-teardown", "excess-output", "no-qt", "bad-qt-version", "oversized-qt-version", "changed-source", "wrong-python"])
def test_mocked_hosted_gate_fails_closed_and_does_not_publish_private_diagnostics(tmp_path, monkeypatch, behavior):
    module = checker()
    target = mocked_hosted_gate(module, tmp_path, monkeypatch, behavior)
    if behavior == "changed-source":
        original = module.source_pins
        calls = []

        def changed(root):
            calls.append(root)
            pins = original(root)
            if len(calls) == 2:
                pins[module.SOURCE_FILES[0]]["sha256"] = "b" * 64
            return pins

        monkeypatch.setattr(module, "source_pins", changed)
    elif behavior == "wrong-python":
        monkeypatch.setattr(module.sys, "version_info", (3, 14, 7))
    assert module.run_gate(target) == 1
    receipt = json.loads(target.read_text())
    assert receipt["passed"] is False
    assert "refusal_code" in receipt
    assert "private-" not in target.read_text()


def test_output_capture_is_bounded_and_records_truncation_without_raw_public_text():
    module = checker()
    capture = module.BoundedOutput()
    assert capture.write("x" * 65536) == 65536
    assert capture.exceeded is False
    assert capture.write("private-after-limit") == len("private-after-limit")
    assert capture.exceeded is True
    assert len(capture.text) == 65536


def test_durable_initial_refusal_is_written_before_any_guarded_child_or_pytest(tmp_path, monkeypatch):
    module = checker()
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    calls = []
    monkeypatch.setattr(module.subprocess, "run", lambda *_args, **_kwargs: calls.append("child"))
    target = tmp_path / "receipt.json"
    assert module.run_gate(target) == 1
    record = json.loads(target.read_bytes())
    assert record["phase"] == "refused"
    assert record["refusal_code"] == "host-identity-refused"
    assert record["passed"] is False
    assert calls == []


def test_durable_checkpoints_cover_collection_and_every_stage_start_and_report():
    module = checker()
    recorder = module.CaseRecorder()
    phases = []
    recorder.checkpoint = phases.append
    item = types.SimpleNamespace(nodeid=module.TEST_NODE)
    recorder.pytest_collection_finish(types.SimpleNamespace(items=[item]))
    for stage in ("setup", "call", "teardown"):
        getattr(recorder, "pytest_runtest_" + stage)(item)
        recorder.pytest_runtest_logreport(report(module, stage))
    assert phases == ["collection-complete", "setup-started", "setup-reported", "call-started", "call-reported", "teardown-started", "teardown-reported"]
    assert callable(item._row_ownership_checkpoint)
    item._row_ownership_checkpoint("test-before-first-process-events")
    assert phases[-1] == "test-before-first-process-events"
    assert recorder.passed(0) is True


def test_durable_unexpected_case_and_malformed_reports_cannot_pass():
    module = checker()
    recorder = passed_recorder(module)
    phases = []
    recorder.checkpoint = phases.append
    recorder.pytest_runtest_call(types.SimpleNamespace(nodeid="PRIVATE-other-case"))
    recorder.pytest_runtest_logreport(object())
    assert phases == ["unexpected-case", "report-refused"]
    assert recorder.passed(0) is False
    assert "PRIVATE" not in json.dumps(phases)


def test_durable_atomic_publication_retains_prior_complete_record_on_replace_failure(tmp_path, monkeypatch):
    module = checker()
    target = tmp_path / "receipt.json"
    original = b'{"passed":false,"phase":"initialized"}\n'
    target.write_bytes(original)

    def refused(*_args):
        raise OSError("PRIVATE-replace-error")

    monkeypatch.setattr(module.os, "replace", refused)
    with pytest.raises(OSError):
        module.persist_receipt(target, {"passed": False, "phase": "call-started"})
    assert target.read_bytes() == original
    assert list(tmp_path.glob("*.partial")) == []


def test_durable_public_receipt_has_explicit_byte_bound(tmp_path):
    module = checker()
    target = tmp_path / "receipt.json"
    with pytest.raises(ValueError, match="public-receipt-bound"):
        module.persist_receipt(target, {"padding": "x" * module.RECEIPT_LIMIT_BYTES})
    assert not target.exists()


def test_durable_refuses_unavailable_publication_before_running_pytest(tmp_path, monkeypatch, capsys):
    import pytest as pytest_module

    module = checker()
    target = mocked_hosted_gate(module, tmp_path, monkeypatch)
    calls = []

    def never_run(*_args, **_kwargs):
        calls.append("pytest")

    def publication_failed(*_args):
        raise OSError("PRIVATE-output-path-diagnostic")

    monkeypatch.setattr(pytest_module, "main", never_run)
    monkeypatch.setattr(module, "persist_receipt", publication_failed)
    assert module.run_gate(target) == 1
    assert calls == []
    assert "PRIVATE" not in capsys.readouterr().out


def test_durable_mock_native_like_termination_leaves_source_bound_failed_checkpoint(tmp_path, monkeypatch):
    import pytest as pytest_module

    module = checker()
    target = mocked_hosted_gate(module, tmp_path, monkeypatch)
    original_hook = module.sys.excepthook

    class SimulatedUncatchableTermination(BaseException):
        pass

    def interrupted(_arguments, *, plugins):
        recorder = plugins[0]
        item = types.SimpleNamespace(nodeid=module.TEST_NODE)
        recorder.pytest_collection_finish(types.SimpleNamespace(items=[item]))
        recorder.pytest_runtest_setup(item)
        recorder.pytest_runtest_logreport(report(module, "setup"))
        recorder.pytest_runtest_call(item)
        item._row_ownership_checkpoint("test-before-first-process-events")
        raise SimulatedUncatchableTermination("PRIVATE-native-like-fixture")

    monkeypatch.setattr(pytest_module, "main", interrupted)
    with pytest.raises(SimulatedUncatchableTermination):
        module.run_gate(target)
    record = json.loads(target.read_bytes())
    assert record["passed"] is False
    assert record["phase"] == "test-before-first-process-events"
    assert record["collected_exact_case"] is True
    assert record["stages"] == {"setup": "passed"}
    assert set(record["source_files"]) == set(module.SOURCE_FILES)
    assert record["source_sha"] == "a" * 40
    assert module.sys.excepthook is original_hook
    assert "PRIVATE" not in target.read_text()


def test_durable_callback_exception_projection_never_publishes_message_or_local_values(tmp_path, monkeypatch):
    module = checker()
    monkeypatch.setattr(module, "ROOT", tmp_path)
    filename = str(tmp_path / module.SOURCE_FILES[0])
    try:
        exec(compile("raise NameError('PRIVATE-message-and-value')", filename, "exec"), {})
    except NameError as error:
        projection = module.callback_exception_projection(type(error), error.__traceback__)
    assert projection["kind"] == "NameError"
    assert projection["source_frames"] == [{"source": module.SOURCE_FILES[0], "line": 1}]
    assert "PRIVATE" not in json.dumps(projection)
    private_kind = type("PRIVATE-type-name", (Exception,), {})
    assert module.callback_exception_projection(private_kind, None)["kind"] == "other"


def test_durable_callback_exception_refuses_even_if_mocked_pytest_reports_all_passed(tmp_path, monkeypatch):
    import pytest as pytest_module

    module = checker()
    target = mocked_hosted_gate(module, tmp_path, monkeypatch)
    original_hook = module.sys.excepthook

    def fake_main(_arguments, *, plugins):
        recorder = plugins[0]
        item = types.SimpleNamespace(nodeid=module.TEST_NODE)
        recorder.pytest_collection_finish(types.SimpleNamespace(items=[item]))
        for stage in ("setup", "call", "teardown"):
            getattr(recorder, "pytest_runtest_" + stage)(item)
            recorder.pytest_runtest_logreport(report(module, stage))
        try:
            raise RuntimeError("PRIVATE-callback-diagnostic")
        except RuntimeError as error:
            module.sys.excepthook(type(error), error, error.__traceback__)
        return 0

    monkeypatch.setattr(pytest_module, "main", fake_main)
    assert module.run_gate(target) == 1
    record = json.loads(target.read_bytes())
    assert record["stages"] == dict.fromkeys(("setup", "call", "teardown"), "passed")
    assert record["callback_exception_observed"] is True
    assert record["callback_exception"]["kind"] == "RuntimeError"
    assert record["refusal_code"] == "uncaught-callback-exception-observed"
    assert record["passed"] is False
    assert module.sys.excepthook is original_hook
    assert "PRIVATE" not in target.read_text()


@pytest.mark.parametrize("exception", [SystemExit("PRIVATE-exit-value"), KeyboardInterrupt("PRIVATE-interrupt-value")])
def test_durable_abnormal_python_exit_is_bounded_and_never_passes(tmp_path, monkeypatch, exception):
    import pytest as pytest_module

    module = checker()
    target = mocked_hosted_gate(module, tmp_path, monkeypatch)
    original_hook = module.sys.excepthook

    def fake_main(_arguments, *, plugins):
        raise exception

    monkeypatch.setattr(pytest_module, "main", fake_main)
    assert module.run_gate(target) == 1
    record = json.loads(target.read_bytes())
    assert record["refusal_code"] == "hosted-selected-case-abnormal-python-exit"
    assert record["passed"] is False
    assert module.sys.excepthook is original_hook
    assert "PRIVATE" not in target.read_text()

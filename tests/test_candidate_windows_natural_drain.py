from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest


@pytest.fixture
def helper():
    path = Path(__file__).resolve().parents[1] / "scripts/candidate_windows_owned.py"
    spec = importlib.util.spec_from_file_location("owned_natural_drain", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture
def successful_record():
    return {"child_created": True, "job_assigned": True, "wait_result": 0, "exit_code": 0,
            "owned_parent_cleanup_wait": 0, "active_owned_processes_after_cleanup": 0,
            "job_closed": True, "cleanup_errors": []}


def test_old_default_success_remains_compatible_but_required_drain_cannot_fall_back(helper, successful_record):
    assert helper.owned_result_succeeded(successful_record)
    assert not helper.owned_result_succeeded(successful_record, require_descendant_drain=True)
    successful_record.update(descendant_drain_requested=False, natural_job_drain_confirmed=True,
                             active_owned_processes_after_natural_drain=0)
    assert not helper.owned_result_succeeded(successful_record, require_descendant_drain=True)


@pytest.mark.parametrize("change", [
    {"natural_job_drain_confirmed": False}, {"natural_job_drain_confirmed": None},
    {"active_owned_processes_after_natural_drain": 1}, {"active_owned_processes_after_natural_drain": False},
    {"descendant_drain_requested": "true"}, {"error": "TimeoutError: original deadline"},
    {"exit_code": 1}, {"cleanup_errors": ["query failed"]}, {"job_closed": False},
])
def test_cleanup_zero_does_not_excuse_missing_failed_or_late_natural_completion(helper, successful_record, change):
    successful_record.update(descendant_drain_requested=True, natural_job_drain_confirmed=True,
                             active_owned_processes_after_natural_drain=0)
    assert helper.owned_result_succeeded(successful_record, require_descendant_drain=True)
    successful_record.update(change)
    assert not helper.owned_result_succeeded(successful_record, require_descendant_drain=True)


@pytest.mark.parametrize("value", [None, 0, 1, "true"])
def test_nonbool_drain_option_is_rejected_before_any_windows_api(helper, monkeypatch, tmp_path, value):
    monkeypatch.setattr(helper.ctypes, "WinDLL", lambda *a, **k: pytest.fail("API was opened"), raising=False)
    with pytest.raises(ValueError, match="must be a bool"):
        helper.run_owned(Path("unused"), [], {}, tmp_path / "unused.json", 1, drain_descendants=value)


@pytest.mark.parametrize("value", [0, -1, True, "1", 3601, 2**100])
def test_original_timeout_validation_precedes_any_windows_api(helper, monkeypatch, tmp_path, value):
    monkeypatch.setattr(helper.ctypes, "WinDLL", lambda *a, **k: pytest.fail("API was opened"), raising=False)
    with pytest.raises(ValueError, match="timeout"):
        helper.run_owned(Path("unused"), [], {}, tmp_path / "unused.json", value, drain_descendants=True)


def api_with_counts(helper, monkeypatch, counts, clock, query_delay=0):
    monkeypatch.setattr(helper.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(helper.time, "sleep", lambda delay: clock.__setitem__(0, clock[0] + delay))
    iterator = iter(counts)

    def query(job, info, pointer, size, ignored):
        assert job == "retained-job" and info == 1
        pointer._obj.active = next(iterator)
        clock[0] += query_delay
        return True

    return SimpleNamespace(QueryInformationJobObject=query)


def test_same_owned_job_is_observed_until_zero_within_original_deadline(helper, monkeypatch):
    clock, evidence = [0.0], {}
    api = api_with_counts(helper, monkeypatch, [2, 1, 0], clock)
    helper.wait_natural_job_drain(api, "retained-job", 0.1, evidence)
    assert evidence["natural_job_drain_confirmed"] is True
    assert evidence["active_owned_processes_at_parent_exit"] == 2
    assert evidence["active_owned_processes_after_natural_drain"] == 0
    assert evidence["natural_job_drain_elapsed_seconds"] == pytest.approx(0.04)


def test_natural_wait_uses_only_original_deadline_remainder(helper, monkeypatch):
    clock, evidence = [0.975], {}
    api = api_with_counts(helper, monkeypatch, [1, 1], clock)
    with pytest.raises(TimeoutError, match="original command timeout"):
        helper.wait_natural_job_drain(api, "retained-job", 1.0, evidence)
    assert clock[0] == pytest.approx(1.0)
    assert evidence["natural_job_drain_confirmed"] is False
    assert evidence["active_owned_processes_after_natural_drain"] == 1


def test_late_zero_accounting_query_is_not_confirmed_completion(helper, monkeypatch):
    clock, evidence = [0.99], {}
    api = api_with_counts(helper, monkeypatch, [0], clock, query_delay=0.02)
    with pytest.raises(TimeoutError, match="original command timeout"):
        helper.wait_natural_job_drain(api, "retained-job", 1.0, evidence)
    assert evidence["active_owned_processes_after_natural_drain"] == 0
    assert evidence["natural_job_drain_confirmed"] is False


def test_query_failure_is_execution_failure_not_zero_completion(helper, monkeypatch):
    monkeypatch.setattr(helper.ctypes, "get_last_error", lambda: 5, raising=False)
    monkeypatch.setattr(helper.ctypes, "WinError", lambda code: OSError("owned Job query failed"), raising=False)
    evidence = {}
    with pytest.raises(OSError, match="owned Job query failed"):
        helper.wait_natural_job_drain(SimpleNamespace(QueryInformationJobObject=lambda *a: False),
                                     "retained-job", helper.time.monotonic() + 1, evidence)
    assert evidence["natural_job_drain_confirmed"] is False
    assert "active_owned_processes_after_natural_drain" not in evidence

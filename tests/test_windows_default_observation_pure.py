"""Authored synthetic observer tests; no actual native APIs or storage mutation."""
import importlib.util
from pathlib import Path
from types import SimpleNamespace

import pytest

SPEC = importlib.util.spec_from_file_location("windows_default_observation", Path(__file__).parents[1] / "scripts/observe_windows_default_native.py")
observer = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(observer)


def fake(owner=b"user", attributes=16):
    calls = []
    snapshot = SimpleNamespace(owner=owner, attributes=attributes)
    native = SimpleNamespace(token_user=lambda: calls.append(("token",)) or b"user",
                             open_directory=lambda path: calls.append(("open", path)) or 7,
                             snapshot=lambda handle: calls.append(("snapshot", handle)) or snapshot,
                             close=lambda handle: calls.append(("close", handle)))
    storage = SimpleNamespace(_ancestors=lambda home: ("synthetic-root", "synthetic-parent", home),
                              SYSTEM_SID=b"system", ADMINISTRATORS_SID=b"admins", DIRECTORY=16)
    record = observer.parent_observation()
    return observer.ParentObservation(native, b"user", "synthetic-home", storage, record), record, calls, snapshot


@pytest.mark.parametrize("owner,expected", [(b"user", "current-user"), (b"system", "system"),
                                            (b"admins", "administrators"), (b"secret-other", "other")])
@pytest.mark.parametrize("attributes", [16, 0])
@pytest.mark.parametrize("path,index,role", [("synthetic-root", 0, "volume-root"),
                                           ("synthetic-parent", 1, "parent"), ("synthetic-home", 2, "home")])
def test_delegate_preserves_calls_snapshot_and_fixed_public_classification(owner, expected, attributes, path, index, role):
    delegate, record, calls, snapshot = fake(owner, attributes)
    assert delegate.token_user() == b"user"
    handle = delegate.open_directory(path)
    assert record["observer_live_handle_count"] == 1
    assert delegate.snapshot(handle) is snapshot
    assert record == {"ancestor_index": index, "ancestor_role": role, "snapshot_observed": True,
                      "directory_attribute": bool(attributes & 16), "owner_class": expected,
                      "observer_live_handle_count": 1}
    observer.validate_parent_observation(record)
    delegate.close(handle)
    assert record["observer_live_handle_count"] == 0
    assert calls == [("token",), ("open", path), ("snapshot", 7), ("close", 7)]
    assert repr(owner) not in repr(record)


def test_missing_open_and_failed_snapshot_leave_partial_fixed_evidence():
    delegate, record, calls, _ = fake()
    def fail_open(path):
        calls.append(("open", path))
        raise OSError("private-missing-path")
    delegate.native.open_directory = fail_open
    with pytest.raises(OSError):
        delegate.open_directory("synthetic-parent")
    assert record == {"ancestor_index": 1, "ancestor_role": "parent", "snapshot_observed": False,
                      "directory_attribute": None, "owner_class": None, "observer_live_handle_count": 0}
    observer.validate_parent_observation(record)
    delegate, record, calls, _ = fake()
    handle = delegate.open_directory("synthetic-root")
    def fail_snapshot(handle):
        calls.append(("snapshot", handle))
        raise OSError("private-descriptor")
    delegate.native.snapshot = fail_snapshot
    with pytest.raises(OSError):
        delegate.snapshot(handle)
    assert record["snapshot_observed"] is False and record["owner_class"] is None
    delegate.close(handle)
    assert record["observer_live_handle_count"] == 0
    observer.validate_parent_observation(record)


def test_close_failure_does_not_claim_zero_live_handles():
    delegate, record, calls, _ = fake()
    handle = delegate.open_directory("synthetic-root")
    def fail_close(handle):
        calls.append(("close", handle))
        raise OSError("private-close-failure")
    delegate.native.close = fail_close
    with pytest.raises(OSError):
        delegate.close(handle)
    assert record["observer_live_handle_count"] == 1 and handle in delegate.handles
    observer.validate_parent_observation(record)


@pytest.mark.parametrize("key,value", [("path", "private-path"), ("sid", b"private-sid"), ("sddl", "private-dacl"),
    ("ancestor_index", True), ("ancestor_index", -1), ("ancestor_index", 64), ("ancestor_role", "private-root"),
    ("observer_live_handle_count", True), ("observer_live_handle_count", -1), ("observer_live_handle_count", 65),
    ("observer_live_handle_count", 1),
    ("snapshot_observed", 1), ("owner_class", "private-sid"), ("directory_attribute", 16)])
def test_public_validator_refuses_extra_private_fields_wrong_types_and_bounds(key, value):
    record = observer.parent_observation()
    record[key] = value
    with pytest.raises(ValueError, match="native-observation-input-refused"):
        observer.validate_parent_observation(record)


@pytest.mark.parametrize("record", [
    {"ancestor_index": 1, "ancestor_role": "volume-root", "snapshot_observed": False,
     "directory_attribute": None, "owner_class": None, "observer_live_handle_count": 0},
    {"ancestor_index": 0, "ancestor_role": "parent", "snapshot_observed": False,
     "directory_attribute": None, "owner_class": None, "observer_live_handle_count": 0},
    {"ancestor_index": None, "ancestor_role": None, "snapshot_observed": True,
     "directory_attribute": True, "owner_class": "other", "observer_live_handle_count": 0},
])
def test_public_validator_refuses_inconsistent_role_snapshot_combinations(record):
    with pytest.raises(ValueError):
        observer.validate_parent_observation(record)

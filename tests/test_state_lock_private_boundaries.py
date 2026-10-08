"""Private lock boundary/refusal behavior with explicit fake lease and OS providers."""
from contextlib import contextmanager, nullcontext
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from remote_ops_workspace import state_lock as locking
from remote_ops_workspace import windows_private_storage as storage


def _os_facade(monkeypatch, **changes):
    value = SimpleNamespace(**vars(locking.os))
    vars(value).update(changes)
    monkeypatch.setattr(locking, "os", value)
    return value


@pytest.mark.parametrize(("platform", "shared"), [("posix", False), ("unsupported", False), ("nt", True)])
def test_native_private_lock_rejects_wrong_platform_or_shared_scope_before_acquire(tmp_path, monkeypatch, platform, shared):
    guard = SimpleNamespace(verify=Mock())
    acquire = Mock()
    monkeypatch.setattr(locking, "_thread_lock_for", acquire)
    _os_facade(monkeypatch, name=platform)
    with pytest.raises(OSError, match="^private native state lock boundary refused$"):
        with locking.exclusive_file_lock(tmp_path / "state.json", shared=shared, _private_guard=guard):
            pytest.fail("invalid private boundary entered")
    guard.verify.assert_not_called()
    acquire.assert_not_called()


def test_private_reentry_rejects_different_retained_guard_without_releasing_outer_hold(tmp_path, monkeypatch):
    outer = SimpleNamespace(verify=Mock())
    different = SimpleNamespace(verify=Mock())
    held, private = {"synthetic-key": 1}, {"synthetic-key": outer}
    thread_lock = SimpleNamespace(acquire=Mock(return_value=True), release=Mock())
    monkeypatch.setattr(locking, "_canonical_lock_key", lambda _path: "synthetic-key")
    monkeypatch.setattr(locking, "_thread_lock_for", lambda _key: thread_lock)
    monkeypatch.setattr(locking, "_held_locks", lambda: held)
    monkeypatch.setattr(locking, "_held_private_guards", lambda: private)
    opened = Mock()
    monkeypatch.setattr(locking, "_open_lock_file", opened)
    _os_facade(monkeypatch, name="nt", getpid=lambda: 101)
    with pytest.raises(OSError, match="^private native state lock reentry refused$"):
        with locking.exclusive_file_lock(tmp_path / "state.json", _private_guard=different):
            pytest.fail("different native lease reused")
    assert held == {"synthetic-key": 1} and private == {"synthetic-key": outer}
    different.verify.assert_called_once_with()
    outer.verify.assert_not_called()
    thread_lock.release.assert_called_once_with()
    opened.assert_not_called()


def test_same_private_guard_reentry_initializes_registry_and_releases_one_owned_lease(tmp_path, monkeypatch):
    events = []
    guard = SimpleNamespace(verify=Mock())
    thread_lock = SimpleNamespace(acquire=Mock(return_value=True), release=Mock())
    state = SimpleNamespace()
    monkeypatch.setattr(locking, "_thread_state", state)
    monkeypatch.setattr(locking, "_active_lock_descriptors", set())
    monkeypatch.setattr(locking, "_registry_guard", nullcontext())
    monkeypatch.setattr(locking, "_thread_lock_for", lambda _key: thread_lock)
    monkeypatch.setattr(locking, "_canonical_lock_key", lambda _path: "synthetic-key")
    monkeypatch.setattr(locking, "_acquire_os_lock", lambda descriptor, _path, _deadline: events.append(("acquire", descriptor)))
    monkeypatch.setattr(locking, "_release_os_lock", lambda descriptor: events.append(("release", descriptor)))
    _os_facade(monkeypatch, name="nt", getpid=lambda: 101, close=lambda descriptor: events.append(("close", descriptor)))

    @contextmanager
    def private_lease():
        events.append(("lease-enter", 23))
        try:
            yield
        finally:
            events.append(("lease-exit", 23))

    def opened(_path, *, _private_guard, _private_scope):
        assert _private_guard is guard
        _private_scope.enter_context(private_lease())
        return 23

    open_mock = Mock(side_effect=opened)
    monkeypatch.setattr(locking, "_open_lock_file", open_mock)
    with locking.exclusive_file_lock(tmp_path / "state.json", _private_guard=guard):
        registry = locking._held_private_guards()
        assert registry is state.private_guards and registry == {"synthetic-key": guard}
        with locking.exclusive_file_lock(tmp_path / "state.json", _private_guard=guard):
            assert state.held == {"synthetic-key": 2}
            assert locking._held_private_guards() is registry
        assert state.held == {"synthetic-key": 1} and events[-1] == ("acquire", 23)
    assert state.held == state.private_guards == {} and locking._active_lock_descriptors == set()
    assert events == [("lease-enter", 23), ("acquire", 23), ("release", 23), ("lease-exit", 23), ("close", 23)]
    assert open_mock.call_count == 1 and thread_lock.release.call_count == 2
    assert guard.verify.call_count == 3


@pytest.mark.parametrize("defect", ["links", "size"])
def test_private_lock_metadata_refusal_closes_scope_and_descriptor_before_native_conversion(tmp_path, monkeypatch, defect):
    path = tmp_path / "private.lock"
    path.write_bytes(b"xx" if defect == "size" else b"")
    real_open, real_close, real_fstat = locking.os.open, locking.os.close, locking.os.fstat
    descriptors, closed = [], []

    def opened(*args, **kwargs):
        descriptor = real_open(*args, **kwargs)
        descriptors.append(descriptor)
        return descriptor

    def fstat(descriptor):
        value = real_fstat(descriptor)
        return SimpleNamespace(st_mode=value.st_mode, st_dev=value.st_dev, st_ino=value.st_ino,
            st_size=value.st_size, st_nlink=2 if defect == "links" else value.st_nlink)

    def close(descriptor):
        closed.append(descriptor)
        return real_close(descriptor)

    _os_facade(monkeypatch, name="nt", open=opened, fstat=fstat, close=close)
    native_conversion = Mock(side_effect=AssertionError("unsafe lock reached native conversion"))
    monkeypatch.setattr(storage, "descriptor_handle", native_conversion)
    guard = SimpleNamespace(verify=Mock())
    scope = SimpleNamespace(close=Mock(), enter_context=Mock())
    with pytest.raises(OSError, match="^private native lock file metadata refused$"):
        locking._open_lock_file(path, _private_guard=guard, _private_scope=scope)
    assert len(descriptors) == 1 and closed == descriptors
    with pytest.raises(OSError):
        real_fstat(descriptors[0])
    scope.close.assert_called_once_with()
    scope.enter_context.assert_not_called()
    native_conversion.assert_not_called()
    guard.verify.assert_called_once_with()
    assert path.read_bytes() == (b"xx" if defect == "size" else b"")

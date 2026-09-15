from __future__ import annotations

import errno
import multiprocessing
import os
import queue
import stat
import threading
import time
import traceback
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

import remote_ops_workspace.layouts as layouts_module
import remote_ops_workspace.moba_macros as macros_module
import remote_ops_workspace.snippets as snippets_module
import remote_ops_workspace.state_lock as state_lock_module
import remote_ops_workspace.storage as storage_module
import remote_ops_workspace.vault as vault_module
from remote_ops_workspace.layouts import Layout, LayoutPane, LayoutStore
from remote_ops_workspace.moba_macros import MobaMacroStore, record_typed_macro
from remote_ops_workspace.models import Profile
from remote_ops_workspace.snippets import Snippet, SnippetStore
from remote_ops_workspace.state_lock import (
    FileLockTimeoutError,
    exclusive_file_lock,
    lock_path_for,
)
from remote_ops_workspace.storage import ProfileStore
from remote_ops_workspace.vault import LocalVault

PASSPHRASE = "correct horse battery staple"


def _slow_profile_add_worker(path: str, name: str, start, outcomes) -> None:
    import remote_ops_workspace.storage as storage_module

    original_write = storage_module.write_json_atomic

    def delayed_write(*args, **kwargs):  # type: ignore[no-untyped-def]
        time.sleep(0.15)
        return original_write(*args, **kwargs)

    storage_module.write_json_atomic = delayed_write
    if not start.wait(timeout=10):
        outcomes.put("profile worker timed out waiting to start")
        return
    try:
        ProfileStore(Path(path)).add(
            Profile(name=name, protocol="ssh", host=f"{name}.example.invalid")
        )
    except BaseException:  # pragma: no cover - returned to the parent for diagnosis
        outcomes.put(traceback.format_exc())
    else:
        outcomes.put("")


def _slow_vault_set_worker(path: str, name: str, start, outcomes) -> None:
    import remote_ops_workspace.vault as vault_module

    original_write = vault_module.write_json_atomic

    def delayed_write(*args, **kwargs):  # type: ignore[no-untyped-def]
        time.sleep(0.15)
        return original_write(*args, **kwargs)

    vault_module.write_json_atomic = delayed_write
    if not start.wait(timeout=10):
        outcomes.put("vault worker timed out waiting to start")
        return
    try:
        LocalVault(Path(path)).set(name, f"secret-for-{name}", PASSPHRASE)
    except BaseException:  # pragma: no cover - returned to the parent for diagnosis
        outcomes.put(traceback.format_exc())
    else:
        outcomes.put("")


def _profile_lock_timeout_worker(path: str, outcomes) -> None:
    try:
        ProfileStore(Path(path), lock_timeout_seconds=0.2).add(
            Profile(name="blocked", protocol="ssh", host="blocked.example.invalid")
        )
    except BaseException as exc:  # pragma: no cover - result asserted in parent
        outcomes.put((type(exc).__name__, str(exc)))
    else:
        outcomes.put(("", ""))


def _slow_auxiliary_store_add_worker(path: str, name: str, start, outcomes) -> None:
    import remote_ops_workspace.layouts as layouts_module
    import remote_ops_workspace.moba_macros as macros_module
    import remote_ops_workspace.snippets as snippets_module

    for module in (layouts_module, macros_module, snippets_module):
        original_write = module.write_json_atomic

        def delayed_write(*args, _write=original_write, **kwargs):  # type: ignore[no-untyped-def]
            time.sleep(0.1)
            return _write(*args, **kwargs)

        module.write_json_atomic = delayed_write
    if not start.wait(timeout=10):
        outcomes.put("auxiliary store worker timed out waiting to start")
        return
    root = Path(path)
    try:
        SnippetStore(root / "snippets.json").add(Snippet(name=name, command="uptime"))
        LayoutStore(root / "layouts.json").add(
            Layout(name=name, panes=[LayoutPane(command="uptime")])
        )
        MobaMacroStore(root / "macros.json").add(record_typed_macro(name, "uptime"))
    except BaseException:  # pragma: no cover - returned to the parent for diagnosis
        outcomes.put(traceback.format_exc())
    else:
        outcomes.put("")


def _spawn_workers(target, path: Path, names: list[str]) -> list[str]:  # type: ignore[no-untyped-def]
    context = multiprocessing.get_context("spawn")
    start = context.Event()
    outcomes = context.Queue()
    processes = [
        context.Process(target=target, args=(str(path), name, start, outcomes))
        for name in names
    ]
    for process in processes:
        process.start()
    start.set()
    for process in processes:
        process.join(timeout=30)
    failures = [
        f"worker exit code {process.exitcode}" for process in processes if process.exitcode != 0
    ]
    for _process in processes:
        try:
            outcome = outcomes.get(timeout=5)
        except queue.Empty:
            failures.append("worker did not return an outcome")
        else:
            if outcome:
                failures.append(str(outcome))
    for process in processes:
        if process.is_alive():
            process.terminate()
            process.join(timeout=5)
    outcomes.close()
    outcomes.join_thread()
    return failures


def test_profile_store_preserves_all_concurrent_adds(tmp_path: Path) -> None:
    path = tmp_path / "profiles.json"
    names = [f"worker-{index}" for index in range(6)]

    failures = _spawn_workers(_slow_profile_add_worker, path, names)

    assert failures == []
    assert [profile.name for profile in ProfileStore(path).load(resolve=False)] == names
    assert lock_path_for(path).is_file()


def test_vault_preserves_all_concurrent_sets(tmp_path: Path) -> None:
    pytest.importorskip("cryptography")
    path = tmp_path / "vault.json"
    vault = LocalVault(path)
    vault.init(PASSPHRASE)
    names = [f"secret-{index}" for index in range(4)]

    failures = _spawn_workers(_slow_vault_set_worker, path, names)

    assert failures == []
    assert vault.list() == names
    for name in names:
        assert vault.get(name, PASSPHRASE) == f"secret-for-{name}"


def test_auxiliary_stores_preserve_all_concurrent_adds(tmp_path: Path) -> None:
    names = [f"worker-{index}" for index in range(4)]

    failures = _spawn_workers(_slow_auxiliary_store_add_worker, tmp_path, names)

    assert failures == []
    assert [item.name for item in SnippetStore(tmp_path / "snippets.json").load()] == names
    assert [item.name for item in LayoutStore(tmp_path / "layouts.json").load()] == names
    assert [item.name for item in MobaMacroStore(tmp_path / "macros.json").load()] == names


def test_profile_store_reports_busy_lock_without_mutating_state(tmp_path: Path) -> None:
    path = tmp_path / "profiles.json"
    context = multiprocessing.get_context("spawn")
    outcomes = context.Queue()

    with exclusive_file_lock(path):
        process = context.Process(
            target=_profile_lock_timeout_worker,
            args=(str(path), outcomes),
        )
        process.start()
        kind, message = outcomes.get(timeout=15)
        process.join(timeout=5)

    assert process.exitcode == 0
    assert kind == "ValueError"
    assert "profile store is busy" in message
    assert not path.exists()
    outcomes.close()
    outcomes.join_thread()


def test_state_lock_is_reentrant_and_rejects_invalid_timeout(tmp_path: Path) -> None:
    path = tmp_path / "profiles.json"

    with exclusive_file_lock(path):
        with exclusive_file_lock(path):
            assert lock_path_for(path).is_file()

    with pytest.raises(ValueError, match="finite positive"):
        with exclusive_file_lock(path, timeout_seconds=0):
            pass

    with pytest.raises(ValueError, match="finite positive"):
        with exclusive_file_lock(path, timeout_seconds=object()):  # type: ignore[arg-type]
            pass


def test_state_lock_reports_in_process_timeout(monkeypatch, tmp_path: Path) -> None:
    class BusyThreadLock:
        def acquire(self, *, timeout: float) -> bool:
            assert timeout == 0.1
            return False

        def release(self) -> None:  # pragma: no cover - must not release an unheld lock
            raise AssertionError("unexpected release")

    monkeypatch.setattr(state_lock_module, "_thread_lock_for", lambda _key: BusyThreadLock())

    with pytest.raises(FileLockTimeoutError, match="timed out waiting"):
        with exclusive_file_lock(tmp_path / "state.json", timeout_seconds=0.1):
            pass


def test_state_lock_cleans_up_when_open_or_acquire_fails(monkeypatch, tmp_path: Path) -> None:
    open_failure_path = tmp_path / "open-failure.json"
    monkeypatch.setattr(
        state_lock_module,
        "_open_lock_file",
        lambda _path: (_ for _ in ()).throw(OSError("open failed")),
    )
    with pytest.raises(OSError, match="open failed"):
        with exclusive_file_lock(open_failure_path):
            pass

    descriptor = os.open(tmp_path / "lock-fd", os.O_CREAT | os.O_RDWR)
    monkeypatch.setattr(state_lock_module, "_open_lock_file", lambda _path: descriptor)
    monkeypatch.setattr(
        state_lock_module,
        "_acquire_os_lock",
        lambda *_args: (_ for _ in ()).throw(OSError("acquire failed")),
    )
    with pytest.raises(OSError, match="acquire failed"):
        with exclusive_file_lock(tmp_path / "acquire-failure.json"):
            pass
    with pytest.raises(OSError):
        os.fstat(descriptor)


def test_open_lock_file_rejects_symlink_and_invalid_identity(
    monkeypatch, tmp_path: Path
) -> None:
    target = tmp_path / "target.lock"
    target.write_bytes(b"x")
    link = tmp_path / "linked.lock"
    real_is_symlink = Path.is_symlink
    monkeypatch.setattr(
        Path,
        "is_symlink",
        lambda path: path == link or real_is_symlink(path),
    )
    with pytest.raises(OSError, match="symlinked state lock"):
        state_lock_module._open_lock_file(link)

    real_fstat = os.fstat

    def non_regular(descriptor: int) -> SimpleNamespace:
        opened = real_fstat(descriptor)
        return SimpleNamespace(
            st_mode=stat.S_IFDIR,
            st_dev=opened.st_dev,
            st_ino=opened.st_ino,
            st_size=opened.st_size,
        )

    monkeypatch.setattr(state_lock_module.os, "fstat", non_regular)
    with pytest.raises(OSError, match="regular file"):
        state_lock_module._open_lock_file(tmp_path / "non-regular.lock")

    def changed_identity(descriptor: int) -> SimpleNamespace:
        opened = real_fstat(descriptor)
        return SimpleNamespace(
            st_mode=opened.st_mode,
            st_dev=opened.st_dev + 1,
            st_ino=opened.st_ino,
            st_size=opened.st_size,
        )

    monkeypatch.setattr(state_lock_module.os, "fstat", changed_identity)
    with pytest.raises(OSError, match="changed while opening"):
        state_lock_module._open_lock_file(tmp_path / "changed.lock")


def test_open_lock_file_portable_flag_and_chmod_fallbacks(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "portable.lock"
    path.write_bytes(b"existing-marker")
    monkeypatch.delattr(state_lock_module.os, "O_BINARY", raising=False)
    monkeypatch.setattr(state_lock_module.os, "O_NOFOLLOW", 0, raising=False)
    monkeypatch.delattr(state_lock_module.os, "fchmod", raising=False)

    descriptor = state_lock_module._open_lock_file(path)

    os.close(descriptor)
    assert path.read_bytes() == b"existing-marker"


def test_existing_posix_shared_lock_is_validated_without_fchmod(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    path = tmp_path / "shared.lock"
    calls: list[tuple[int, int]] = []
    opened = SimpleNamespace(st_mode=stat.S_IFREG | 0o660)
    monkeypatch.setattr(state_lock_module.os, "name", "posix")
    monkeypatch.setattr(
        state_lock_module.os,
        "fchmod",
        lambda descriptor, mode: calls.append((descriptor, mode)),
        raising=False,
    )

    state_lock_module._secure_lock_mode(
        17,
        path,
        mode=0o660,
        shared=True,
        created=False,
        opened=opened,
    )

    assert calls == []
    with pytest.raises(OSError, match="permissions must be 0660"):
        state_lock_module._secure_lock_mode(
            17,
            path,
            mode=0o660,
            shared=True,
            created=False,
            opened=SimpleNamespace(st_mode=stat.S_IFREG | 0o666),
        )

    state_lock_module._secure_lock_mode(
        17,
        path,
        mode=0o660,
        shared=True,
        created=True,
        opened=opened,
    )
    assert calls == [(17, 0o660)]


def test_profile_update_serializes_the_entire_read_modify_write(
    tmp_path: Path,
) -> None:
    store = ProfileStore(tmp_path / "profiles.json")
    store.add(Profile(name="base", protocol="ssh", host="base.example.invalid"))
    entered = threading.Event()
    release = threading.Event()
    late_finished = threading.Event()
    errors: queue.Queue[BaseException] = queue.Queue()

    def update() -> None:
        def updater(
            profiles: list[Profile],
            _defaults: dict[str, dict[str, object]],
        ) -> list[Profile]:
            entered.set()
            if not release.wait(timeout=5):
                raise TimeoutError("test updater was not released")
            profiles.append(
                Profile(name="remote", protocol="ssh", host="remote.example.invalid")
            )
            return profiles

        try:
            store.update_profiles(updater, surface="cli", action="team-sync-merge")
        except BaseException as exc:  # pragma: no cover - asserted in parent thread
            errors.put(exc)

    def add_late() -> None:
        try:
            ProfileStore(store.path).add(
                Profile(name="late", protocol="ssh", host="late.example.invalid")
            )
        except BaseException as exc:  # pragma: no cover - asserted in parent thread
            errors.put(exc)
        finally:
            late_finished.set()

    updater_thread = threading.Thread(target=update)
    updater_thread.start()
    assert entered.wait(timeout=2)
    late_thread = threading.Thread(target=add_late)
    late_thread.start()
    assert not late_finished.wait(timeout=0.1)
    release.set()
    updater_thread.join(timeout=5)
    late_thread.join(timeout=5)

    assert not updater_thread.is_alive()
    assert not late_thread.is_alive()
    assert errors.empty()
    assert {profile.name for profile in store.load(resolve=False)} == {
        "base",
        "late",
        "remote",
    }


def test_layout_replace_serializes_read_validation_and_write(tmp_path: Path) -> None:
    path = tmp_path / "layouts.json"
    store = LayoutStore(path)
    store.add(Layout(name="base", panes=[LayoutPane(command="uptime")]))
    entered = threading.Event()
    release = threading.Event()
    late_finished = threading.Event()
    errors: queue.Queue[BaseException] = queue.Queue()
    original_load = store.load

    def delayed_load() -> list[Layout]:
        layouts = original_load()
        entered.set()
        if not release.wait(timeout=5):
            raise TimeoutError("test layout read was not released")
        return layouts

    store.load = delayed_load  # type: ignore[method-assign]

    def replace() -> None:
        try:
            store.replace_named(
                "base",
                Layout(name="renamed", panes=[LayoutPane(command="whoami")]),
            )
        except BaseException as exc:  # pragma: no cover - asserted in parent thread
            errors.put(exc)

    def add_late() -> None:
        try:
            LayoutStore(path).add(
                Layout(name="late", panes=[LayoutPane(command="hostname")])
            )
        except BaseException as exc:  # pragma: no cover - asserted in parent thread
            errors.put(exc)
        finally:
            late_finished.set()

    replace_thread = threading.Thread(target=replace)
    replace_thread.start()
    assert entered.wait(timeout=2)
    late_thread = threading.Thread(target=add_late)
    late_thread.start()
    assert not late_finished.wait(timeout=0.1)
    release.set()
    replace_thread.join(timeout=5)
    late_thread.join(timeout=5)

    assert errors.empty()
    assert {layout.name for layout in LayoutStore(path).load()} == {"late", "renamed"}


def test_os_lock_retry_timeout_and_unexpected_error(monkeypatch, tmp_path: Path) -> None:
    attempts = 0
    sleeps: list[float] = []

    def busy_once(_descriptor: int) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise OSError(errno.EACCES, "busy")

    monkeypatch.setattr(state_lock_module, "_try_os_lock", busy_once)
    monkeypatch.setattr(state_lock_module.time, "sleep", sleeps.append)
    state_lock_module._acquire_os_lock(-1, tmp_path / "state.json", time.monotonic() + 1)
    assert attempts == 2
    assert sleeps and 0 < sleeps[0] <= state_lock_module.LOCK_POLL_INTERVAL_SECONDS

    monkeypatch.setattr(
        state_lock_module,
        "_try_os_lock",
        lambda _descriptor: (_ for _ in ()).throw(OSError(errno.EIO, "broken")),
    )
    with pytest.raises(OSError, match="broken"):
        state_lock_module._acquire_os_lock(-1, tmp_path / "state.json", time.monotonic() + 1)

    monkeypatch.setattr(
        state_lock_module,
        "_try_os_lock",
        lambda _descriptor: (_ for _ in ()).throw(OSError(errno.EACCES, "busy")),
    )
    with pytest.raises(FileLockTimeoutError, match="timed out waiting"):
        state_lock_module._acquire_os_lock(-1, tmp_path / "state.json", 0)


def test_os_lock_platform_dispatch_and_busy_winerror(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "descriptor.lock"
    descriptor = os.open(path, os.O_CREAT | os.O_RDWR)
    calls: list[tuple[int, int]] = []
    fake_fcntl = SimpleNamespace(
        LOCK_EX=1,
        LOCK_NB=2,
        LOCK_UN=4,
        flock=lambda fd, flags: calls.append((fd, flags)),
    )
    try:
        monkeypatch.setattr(state_lock_module.os, "name", "posix")
        monkeypatch.setattr(
            state_lock_module.importlib,
            "import_module",
            lambda name: fake_fcntl if name == "fcntl" else None,
        )
        state_lock_module._try_os_lock(descriptor)
        state_lock_module._release_os_lock(descriptor)
        assert calls == [(descriptor, 3), (descriptor, 4)]

        monkeypatch.setattr(state_lock_module.os, "name", "unsupported")
        with pytest.raises(OSError, match="unsupported"):
            state_lock_module._try_os_lock(descriptor)
        with pytest.raises(OSError, match="unsupported"):
            state_lock_module._release_os_lock(descriptor)
    finally:
        os.close(descriptor)

    winerror = OSError("busy")
    winerror.errno = None
    winerror.winerror = 33  # type: ignore[attr-defined]
    assert state_lock_module._lock_is_busy(winerror) is True


def test_state_lock_resets_inherited_thread_state() -> None:
    state_lock_module._thread_locks["held"] = threading.RLock()
    state_lock_module._thread_state.held = {"held": 1}
    inherited, peer = os.pipe()
    state_lock_module._active_lock_descriptors.add(inherited)

    try:
        state_lock_module._reset_after_fork()

        assert state_lock_module._thread_locks == {}
        assert not hasattr(state_lock_module._thread_state, "held")
        assert state_lock_module._active_lock_descriptors == set()
        with pytest.raises(OSError) as exc_info:
            os.fstat(inherited)
        assert exc_info.value.errno == errno.EBADF
    finally:
        os.close(peer)


@pytest.mark.skipif(not hasattr(os, "fork"), reason="requires POSIX fork")
def test_state_lock_at_fork_hook_closes_the_child_descriptor(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    opened: list[int] = []
    original_open = state_lock_module._open_lock_file

    def recording_open(path: Path, *, shared: bool = False) -> int:
        descriptor = original_open(path, shared=shared)
        opened.append(descriptor)
        return descriptor

    monkeypatch.setattr(state_lock_module, "_open_lock_file", recording_open)
    with exclusive_file_lock(tmp_path / "forked.json", timeout_seconds=1):
        inherited = opened[-1]
        child_pid = os.fork()
        if child_pid == 0:  # pragma: no cover - assertions execute in child
            try:
                try:
                    os.fstat(inherited)
                except OSError as exc:
                    descriptor_closed = exc.errno == errno.EBADF
                else:
                    descriptor_closed = False
                clean_state = (
                    state_lock_module._active_lock_descriptors == set()
                    and state_lock_module._thread_locks == {}
                )
                os._exit(0 if descriptor_closed and clean_state else 1)
            except BaseException:
                os._exit(2)
        waited_pid, status = os.waitpid(child_pid, 0)

    assert waited_pid == child_pid
    assert os.waitstatus_to_exitcode(status) == 0


@contextmanager
def _timed_out_lock(*_args, **_kwargs):  # type: ignore[no-untyped-def]
    raise FileLockTimeoutError("busy")
    yield  # pragma: no cover - contextmanager requires an iterator shape


def test_store_and_vault_translate_lock_timeouts(monkeypatch, tmp_path: Path) -> None:
    store = ProfileStore(tmp_path / "profiles.json")
    store.save([])
    monkeypatch.setattr(storage_module, "exclusive_file_lock", _timed_out_lock)
    with pytest.raises(ValueError, match="profile store is busy"):
        store.save([])

    monkeypatch.setattr(vault_module, "exclusive_file_lock", _timed_out_lock)
    vault = LocalVault(tmp_path / "vault.json")
    with pytest.raises(vault_module.VaultError, match="vault is busy"):
        with vault._transaction():
            pass


@pytest.mark.parametrize(
    ("store_type", "key"),
    [
        (SnippetStore, "snippets"),
        (LayoutStore, "layouts"),
        (MobaMacroStore, "macros"),
    ],
)
def test_auxiliary_stores_reject_future_schema_versions(
    tmp_path: Path, store_type, key: str  # type: ignore[no-untyped-def]
) -> None:
    path = tmp_path / f"{key}.json"
    path.write_text(f'{{"version": 2, "{key}": []}}', encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported .* store version"):
        store_type(path).load()


@pytest.mark.parametrize(
    ("store_module", "store_type", "key"),
    [
        (snippets_module, SnippetStore, "snippets"),
        (layouts_module, LayoutStore, "layouts"),
        (macros_module, MobaMacroStore, "macros"),
    ],
)
def test_auxiliary_store_save_timeout_and_malformed_schema_paths(
    monkeypatch,
    tmp_path: Path,
    store_module,
    store_type,
    key: str,
) -> None:  # type: ignore[no-untyped-def]
    path = tmp_path / f"{key}.json"
    store = store_type(path)
    store.save([])

    monkeypatch.setattr(store_module, "exclusive_file_lock", _timed_out_lock)
    with pytest.raises(ValueError, match="store is busy"):
        store.save([])

    path.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="store root must be a JSON object"):
        store.load()

    path.write_text(f'{{"version": 1, "{key}": [1]}}', encoding="utf-8")
    with pytest.raises(ValueError, match="store records must be JSON objects"):
        store.load()

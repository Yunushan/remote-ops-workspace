from __future__ import annotations

import errno
import importlib
import math
import os
import stat
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from .file_safety import (
    PRIVATE_FILE_MODE,
    SHARED_FILE_MODE,
    ensure_private_dir_required,
    ensure_shared_dir,
    require_shared_dir_metadata,
)

DEFAULT_LOCK_TIMEOUT_SECONDS = 30.0
LOCK_POLL_INTERVAL_SECONDS = 0.05


class FileLockTimeoutError(TimeoutError):
    """A mutable state transaction could not acquire its lock in time."""


_registry_guard = threading.Lock()
_thread_locks: dict[str, threading.RLock] = {}
_thread_state = threading.local()
_active_lock_descriptors: set[int] = set()


def lock_path_for(path: Path) -> Path:
    """Return the stable, adjacent lock file used for a mutable state artifact."""

    return path.with_name(f".{path.name}.lock")


@contextmanager
def exclusive_file_lock(
    path: Path,
    *,
    timeout_seconds: float = DEFAULT_LOCK_TIMEOUT_SECONDS,
    shared: bool = False,
) -> Iterator[None]:
    """Hold an exclusive cross-process lock for a state artifact.

    The lock file remains in place between transactions. Removing advisory lock
    files is unsafe because a waiter can retain a lock on the unlinked inode while
    a new process locks a replacement file. The implementation also serializes
    threads in this process and supports same-thread re-entry.
    """

    timeout_seconds = _validate_timeout(timeout_seconds)
    owner_pid = os.getpid()
    lock_path = lock_path_for(path)
    key = _canonical_lock_key(lock_path)
    deadline = time.monotonic() + timeout_seconds
    thread_lock = _thread_lock_for(key)
    if not thread_lock.acquire(timeout=timeout_seconds):
        raise FileLockTimeoutError(f"timed out waiting for state lock: {path}")

    held = _held_locks()
    if key in held:
        held[key] += 1
        try:
            yield
        finally:
            if os.getpid() == owner_pid:
                held[key] -= 1
                thread_lock.release()
        return

    descriptor: int | None = None
    acquired = False
    try:
        with _registry_guard:
            descriptor = (
                _open_lock_file(lock_path, shared=True)
                if shared
                else _open_lock_file(lock_path)
            )
            _active_lock_descriptors.add(descriptor)
        _acquire_os_lock(descriptor, path, deadline)
        acquired = True
        held[key] = 1
        yield
    finally:
        if os.getpid() == owner_pid:
            held.pop(key, None)
            if descriptor is not None:
                with _registry_guard:
                    try:
                        if acquired:
                            _release_os_lock(descriptor)
                    finally:
                        try:
                            os.close(descriptor)
                        finally:
                            _active_lock_descriptors.discard(descriptor)
            thread_lock.release()


def _validate_timeout(value: float) -> float:
    try:
        timeout = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("state lock timeout must be a finite positive number") from exc
    if not math.isfinite(timeout) or timeout <= 0:
        raise ValueError("state lock timeout must be a finite positive number")
    return timeout


def _canonical_lock_key(path: Path) -> str:
    key = os.path.abspath(os.fspath(path))
    return os.path.normcase(key)


def _thread_lock_for(key: str) -> threading.RLock:
    with _registry_guard:
        return _thread_locks.setdefault(key, threading.RLock())


def _held_locks() -> dict[str, int]:
    held = getattr(_thread_state, "held", None)
    if held is None:
        held = {}
        _thread_state.held = held
    return held


def _open_lock_file(path: Path, *, shared: bool = False) -> int:
    if shared:
        ensure_shared_dir(path.parent)
        shared_parent = path.parent.stat(follow_symlinks=False)
    else:
        ensure_private_dir_required(path.parent)
        shared_parent = None
    if path.is_symlink():
        raise OSError(f"refusing to use symlinked state lock: {path}")
    try:
        initial = path.lstat()
    except FileNotFoundError:
        initial = None
    if initial is not None and (
        stat.S_ISLNK(initial.st_mode) or _is_reparse_point(initial)
    ):
        raise OSError(f"refusing to use symlinked state lock: {path}")
    mode = SHARED_FILE_MODE if shared else PRIVATE_FILE_MODE
    flags = os.O_CREAT | os.O_RDWR
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    created = False
    try:
        descriptor = os.open(path, flags | os.O_EXCL, mode)
        created = True
    except FileExistsError:
        descriptor = os.open(path, flags, mode)
    try:
        named = path.stat(follow_symlinks=False)
        opened = os.fstat(descriptor)
        if (
            stat.S_ISLNK(named.st_mode)
            or _is_reparse_point(named)
            or not stat.S_ISREG(opened.st_mode)
        ):
            raise OSError(f"state lock must be a regular file: {path}")
        if (named.st_dev, named.st_ino) != (opened.st_dev, opened.st_ino):
            raise OSError(f"state lock changed while opening: {path}")
        if shared_parent is not None:
            current_parent = path.parent.stat(follow_symlinks=False)
            require_shared_dir_metadata(path.parent, current_parent)
            if (
                current_parent.st_dev,
                current_parent.st_ino,
                current_parent.st_gid,
            ) != (
                shared_parent.st_dev,
                shared_parent.st_ino,
                shared_parent.st_gid,
            ):
                raise OSError(f"shared state lock directory changed while opening: {path}")
            if os.name == "posix" and opened.st_gid != shared_parent.st_gid:
                raise OSError(
                    "shared state lock group must match its setgid directory "
                    f"({shared_parent.st_gid}), found {opened.st_gid}: {path}"
                )
        _secure_lock_mode(
            descriptor,
            path,
            mode=mode,
            shared=shared,
            created=created,
            opened=opened,
        )
        if opened.st_size == 0:
            os.write(descriptor, b"\0")
            os.fsync(descriptor)
        os.lseek(descriptor, 0, os.SEEK_SET)
        return descriptor
    except Exception:
        os.close(descriptor)
        raise


def _secure_lock_mode(
    descriptor: int,
    path: Path,
    *,
    mode: int,
    shared: bool,
    created: bool,
    opened: os.stat_result,
) -> None:
    """Set a new lock's mode, but only validate an existing shared lock.

    A group member can legitimately open a ``0660`` lock created by another
    account without being allowed to chmod it. Requiring fchmod on every open
    therefore turns the group-shared store into a single-owner store.
    """

    if os.name == "posix":
        if shared and not created:
            actual = stat.S_IMODE(opened.st_mode)
            if actual != mode:
                raise OSError(
                    f"shared state lock permissions must be {mode:04o}, "
                    f"found {actual:04o}: {path}"
                )
            return
        if hasattr(os, "fchmod"):
            os.fchmod(descriptor, mode)
        else:  # pragma: no cover - POSIX implementations normally provide fchmod
            path.chmod(mode)
        return
    if not shared:
        path.chmod(mode)


def _acquire_os_lock(descriptor: int, target: Path, deadline: float) -> None:
    while True:
        try:
            _try_os_lock(descriptor)
            return
        except OSError as exc:
            if not _lock_is_busy(exc):
                raise
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise FileLockTimeoutError(f"timed out waiting for state lock: {target}")
        time.sleep(min(LOCK_POLL_INTERVAL_SECONDS, remaining))


def _try_os_lock(descriptor: int) -> None:
    os.lseek(descriptor, 0, os.SEEK_SET)
    if os.name == "nt":
        msvcrt = importlib.import_module("msvcrt")
        msvcrt.locking(descriptor, msvcrt.LK_NBLCK, 1)
        return
    if os.name == "posix":
        fcntl = importlib.import_module("fcntl")
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        return
    raise OSError(f"cross-process state locking is unsupported on {os.name!r}")


def _release_os_lock(descriptor: int) -> None:
    os.lseek(descriptor, 0, os.SEEK_SET)
    if os.name == "nt":
        msvcrt = importlib.import_module("msvcrt")
        msvcrt.locking(descriptor, msvcrt.LK_UNLCK, 1)
        return
    if os.name == "posix":
        fcntl = importlib.import_module("fcntl")
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        return
    raise OSError(f"cross-process state locking is unsupported on {os.name!r}")


def _lock_is_busy(exc: OSError) -> bool:
    return exc.errno in {errno.EACCES, errno.EAGAIN, errno.EDEADLK} or getattr(
        exc, "winerror", None
    ) in {32, 33, 36}


def _is_reparse_point(path_status: os.stat_result) -> bool:
    attributes = getattr(path_status, "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _prepare_for_fork() -> None:
    _registry_guard.acquire()


def _resume_after_fork() -> None:
    _registry_guard.release()


def _reset_after_fork() -> None:
    global _registry_guard, _thread_locks, _thread_state, _active_lock_descriptors
    for descriptor in tuple(_active_lock_descriptors):
        try:
            os.close(descriptor)
        except OSError:
            pass
    _registry_guard = threading.Lock()
    _thread_locks = {}
    _thread_state = threading.local()
    _active_lock_descriptors = set()


if hasattr(os, "register_at_fork"):  # pragma: no cover - POSIX import-time hook
    os.register_at_fork(
        before=_prepare_for_fork,
        after_in_parent=_resume_after_fork,
        after_in_child=_reset_after_fork,
    )

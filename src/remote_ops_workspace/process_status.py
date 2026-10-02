"""Read process status without signals and stop only a verified process instance.

Persisted PIDs are not identities: the operating system can reuse them. Windows
operations use one process handle; Linux shutdown uses one pidfd. Other POSIX
systems may stop an owned, unreaped ``Popen`` child, but cannot safely stop an
arbitrary persisted PID using the portable APIs.

POSIX owned-child operations require default SIGCHLD handling. Trusted callers
must preserve that setting and reap children only through their Popen objects;
direct waitpid calls or external child reapers bypass the Popen ownership lock.
"""

from __future__ import annotations

import ctypes
import math
import os
import select
import signal
import subprocess
import sys
import threading
import time
import uuid
from collections.abc import Mapping
from ctypes import wintypes
from pathlib import Path
from typing import Any, cast


class ProcessStatusError(RuntimeError):
    """The operating system could not reliably inspect or stop a process."""


class ProcessIdentityError(ProcessStatusError):
    """The saved process identity cannot authorize stopping this instance."""


_QUERY = 0x1000
_SYNCHRONIZE = 0x00100000
_TERMINATE = 0x0001
_WAIT_OBJECT_0 = 0
_WAIT_TIMEOUT = 258
_POLLIN = 0x0001
_POLLHUP = 0x0010
_owned: dict[int, tuple[subprocess.Popen[Any], dict[str, Any]]] = {}
_owned_lock = threading.RLock()


def _pid(value: int) -> int:
    if isinstance(value, bool) or not isinstance(value, int) or not 0 < value <= 0xFFFFFFFF:
        raise ValueError("process PID must be a positive 32-bit integer")
    return value


def _timeout(value: float) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError("process timeout must be a finite positive number of seconds")
    if not math.isfinite(value) or not 0 < value <= 86400:
        raise ValueError("process timeout must be between 0 and 86400 seconds")
    return float(value)


def _windows_api() -> Any:
    api = cast(Any, ctypes).WinDLL("kernel32", use_last_error=True)
    api.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    api.OpenProcess.restype = wintypes.HANDLE
    api.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    api.GetProcessTimes.restype = wintypes.BOOL
    api.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    api.WaitForSingleObject.restype = wintypes.DWORD
    api.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
    api.TerminateProcess.restype = wintypes.BOOL
    api.CloseHandle.argtypes = [wintypes.HANDLE]
    api.CloseHandle.restype = wintypes.BOOL
    return api


def _windows_error(action: str) -> ProcessStatusError:
    return ProcessStatusError(f"{action} failed (Windows error {cast(Any, ctypes).get_last_error()})")


def _open_windows(api: Any, pid: int, *, terminate: bool = False) -> Any:
    access = _QUERY | _SYNCHRONIZE | (_TERMINATE if terminate else 0)
    handle = api.OpenProcess(access, False, pid)
    if not handle:
        if cast(Any, ctypes).get_last_error() == 87:
            raise ProcessLookupError(f"process {pid} has exited")
        raise _windows_error(f"OpenProcess({pid})")
    return handle


def _windows_alive(api: Any, handle: Any, timeout_ms: int = 0) -> bool:
    outcome = api.WaitForSingleObject(handle, timeout_ms)
    if outcome == _WAIT_OBJECT_0:
        return False
    if outcome == _WAIT_TIMEOUT:
        return True
    raise _windows_error("WaitForSingleObject")


def _windows_identity(api: Any, handle: Any, pid: int) -> dict[str, Any]:
    times = [wintypes.FILETIME() for _ in range(4)]
    if not api.GetProcessTimes(handle, *(ctypes.byref(item) for item in times)):
        raise _windows_error("GetProcessTimes")
    birth = (int(times[0].dwHighDateTime) << 32) | int(times[0].dwLowDateTime)
    if birth <= 0:
        raise ProcessStatusError("Windows process birth time is unavailable")
    return {"version": 1, "kind": "windows", "pid": pid, "creation_time": birth}


def _linux_identity(pid: int) -> tuple[dict[str, Any], bool]:
    try:
        stat = Path(f"/proc/{pid}/stat").read_text(encoding="utf-8")
        # A process name can contain spaces and closing parentheses. Fields after
        # the final ')' begin at field 3 (state); starttime is field 22.
        fields = stat[stat.rindex(")") + 2 :].split()
        start_ticks = int(fields[19])
        state = fields[0]
        boot_id = Path("/proc/sys/kernel/random/boot_id").read_text(encoding="ascii").strip()
        if start_ticks <= 0 or not boot_id:
            raise ValueError("missing process birth time or boot identity")
    except FileNotFoundError as exc:
        # Missing /proc data (including hidden processes or a different mount)
        # proves exit only when a nondestructive POSIX probe also finds no PID.
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            raise ProcessLookupError(f"process {pid} has exited") from exc
        except OSError as probe_error:
            raise ProcessStatusError(f"cannot read Linux identity for process {pid}") from probe_error
        raise ProcessStatusError(f"cannot read Linux identity for process {pid}") from exc
    except (OSError, ValueError, IndexError) as exc:
        raise ProcessStatusError(f"cannot read Linux identity for process {pid}") from exc
    return (
        {"version": 1, "kind": "linux", "pid": pid, "start_ticks": start_ticks, "boot_id": boot_id},
        state not in {"Z", "X", "x"},
    )


def capture_process_identity(pid: int) -> dict[str, Any]:
    """Capture a JSON-safe native birth identity for a running process."""
    pid = _pid(pid)
    if os.name == "nt":
        api = _windows_api()
        handle = _open_windows(api, pid)
        try:
            identity = _windows_identity(api, handle, pid)
            alive = _windows_alive(api, handle)
        finally:
            api.CloseHandle(handle)
    elif sys.platform.startswith("linux"):
        identity, alive = _linux_identity(pid)
    else:
        raise ProcessIdentityError("native process identity is unavailable; register an owned child")
    if not alive:
        raise ProcessLookupError(f"process {pid} has exited")
    return identity


def register_process(process: subprocess.Popen[Any]) -> dict[str, Any]:
    """Capture and retain an actual child so shutdown can also reap it."""
    if not isinstance(process, subprocess.Popen):
        raise TypeError("managed process must be an actual subprocess.Popen child")
    pid = _pid(process.pid)
    if os.name == "nt":
        # The owned handle identifies the launched child even if its PID could
        # already refer to another instance. Never register a child by PID alone.
        handle = getattr(process, "_handle", None)
        if not handle:
            raise ProcessIdentityError("safe owned-child registration is unavailable")
        api = _windows_api()
        identity = _windows_identity(api, handle, pid)
        if not _windows_alive(api, handle):
            raise ProcessLookupError(f"process {pid} has exited")
    elif sys.platform.startswith("linux"):
        # Capture while the child cannot be reaped by another Popen waiter. This
        # guarantees /proc refers to our launched child rather than a reused PID.
        wait_lock = getattr(process, "_waitpid_lock", None)
        if wait_lock is None:
            raise ProcessIdentityError("safe owned-child registration is unavailable")
        if not wait_lock.acquire(blocking=False):
            raise ProcessStatusError("owned-child registration is busy; register before starting background waiters")
        try:
            _require_owned_reaping()
            if process.returncode is not None:
                raise ProcessLookupError(f"process {pid} has exited")
            identity = capture_process_identity(pid)
        finally:
            wait_lock.release()
    else:
        _require_owned_reaping()
        if process.poll() is not None:
            raise ProcessLookupError(f"process {pid} has exited")
        identity = {"version": 1, "kind": "owned", "pid": pid, "token": str(uuid.uuid4())}
    with _owned_lock:
        _owned[pid] = (process, identity.copy())
    return identity


def process_is_running(pid: int) -> bool:
    """Inspect status without sending a signal on Windows; raise on uncertainty."""
    pid = _pid(pid)
    try:
        if os.name == "nt":
            api = _windows_api()
            handle = _open_windows(api, pid)
            try:
                return _windows_alive(api, handle)
            finally:
                api.CloseHandle(handle)
        if sys.platform.startswith("linux"):
            return _linux_identity(pid)[1]
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except OSError as exc:
        raise ProcessStatusError(f"cannot inspect process {pid}: {exc}") from exc
    return True


def recorded_process_is_running(pid: int, identity: Mapping[str, Any] | None) -> bool:
    """Report status only for the process instance named by a saved identity.

    Linux birth time and state come from the same /proc stat read, so a reused
    PID cannot borrow the recorded child's running status. This is a status
    snapshot; termination separately requires a stable native process handle.
    """
    pid = _pid(pid)
    identity = _validate_identity(pid, identity)
    try:
        if os.name == "nt" and identity["kind"] == "windows":
            api = _windows_api()
            handle = _open_windows(api, pid)
            try:
                _match_identity(_windows_identity(api, handle, pid), identity)
                return _windows_alive(api, handle)
            finally:
                api.CloseHandle(handle)
        if sys.platform.startswith("linux") and identity["kind"] == "linux":
            actual, alive = _linux_identity(pid)
            _match_identity(actual, identity)
            return alive
        with _owned_lock:
            entry = _owned.get(pid)
        if identity["kind"] != "owned" or entry is None or entry[1] != identity:
            raise ProcessIdentityError("safe status identity is unavailable; use the OS process manager")
        return entry[0].poll() is None
    except ProcessLookupError:
        return False
    except OSError as exc:
        raise ProcessStatusError(f"cannot inspect recorded process {pid}: {exc}") from exc


def _validate_identity(pid: int, identity: Mapping[str, Any] | None) -> Mapping[str, Any]:
    if (
        not isinstance(identity, Mapping)
        or type(identity.get("version")) is not int
        or identity.get("version") != 1
        or type(identity.get("pid")) is not int
        or identity.get("pid") != pid
    ):
        raise ProcessIdentityError("saved process identity is missing or invalid; use the OS process manager")
    kind = identity.get("kind")
    if kind == "windows":
        birth = identity.get("creation_time")
        valid = isinstance(birth, int) and not isinstance(birth, bool) and 0 < birth < 1 << 64
    elif kind == "linux":
        ticks, boot = identity.get("start_ticks"), identity.get("boot_id")
        valid = isinstance(ticks, int) and not isinstance(ticks, bool) and ticks > 0
        valid = valid and isinstance(boot, str) and bool(boot.strip())
    elif kind == "owned":
        valid = isinstance(identity.get("token"), str) and bool(identity.get("token"))
    else:
        valid = False
    if not valid:
        raise ProcessIdentityError("saved process birth identity is invalid; use the OS process manager")
    return identity


def _match_identity(actual: Mapping[str, Any], expected: Mapping[str, Any]) -> None:
    if any(expected.get(key) != value for key, value in actual.items()):
        raise ProcessIdentityError("process identity changed; refusing to use a reused PID")


def _reap_owned(pid: int, identity: Mapping[str, Any]) -> None:
    with _owned_lock:
        entry = _owned.get(pid)
    if entry is not None and entry[1] == identity:
        try:
            entry[0].wait(timeout=0)
        except subprocess.TimeoutExpired as exc:
            raise ProcessStatusError(f"process {pid} exited but owned-child reaping is still busy") from exc
        with _owned_lock:
            if _owned.get(pid) is entry:
                del _owned[pid]


def _terminate_windows(pid: int, identity: Mapping[str, Any], timeout: float) -> None:
    api = _windows_api()
    handle = _open_windows(api, pid, terminate=True)
    try:
        _match_identity(_windows_identity(api, handle, pid), identity)
        if _windows_alive(api, handle):
            if not api.TerminateProcess(handle, 1):
                # Exit racing the request is acceptable only when the same handle
                # proves completion. Access denied on a running process is not.
                if _windows_alive(api, handle):
                    raise _windows_error("TerminateProcess")
            if _windows_alive(api, handle, max(1, math.ceil(timeout * 1000))):
                raise TimeoutError(f"process {pid} did not exit within {timeout:g} seconds")
    finally:
        api.CloseHandle(handle)


def _terminate_linux(pid: int, identity: Mapping[str, Any], timeout: float) -> None:
    open_pidfd = getattr(os, "pidfd_open", None)
    send_signal = getattr(signal, "pidfd_send_signal", None)
    if open_pidfd is None or send_signal is None:
        raise ProcessIdentityError("safe Linux shutdown requires pidfd support; use the OS process manager")
    try:
        descriptor = open_pidfd(pid, 0)
    except ProcessLookupError:
        return
    except OSError as exc:
        raise ProcessStatusError(f"cannot open a stable handle for process {pid}: {exc}") from exc
    try:
        poller = cast(Any, select).poll()
        poller.register(descriptor, _POLLIN)
        if _pidfd_exited(poller, 0):
            return
        actual, alive = _linux_identity(pid)
        _match_identity(actual, identity)
        if not alive:
            return
        try:
            send_signal(descriptor, signal.SIGTERM, None, 0)
        except ProcessLookupError:
            pass
        if not _pidfd_exited(poller, max(1, math.ceil(timeout * 1000))):
            raise TimeoutError(f"process {pid} did not exit within {timeout:g} seconds")
    except ProcessLookupError:
        # The process must also have exited on the stable handle, otherwise a
        # missing /proc entry is uncertainty (for example a changed mount).
        if not _pidfd_exited(poller, 0):
            raise ProcessStatusError(f"cannot verify exit of process {pid}") from None
    except TimeoutError:
        raise
    except OSError as exc:
        raise ProcessStatusError(f"cannot stop process {pid}: {exc}") from exc
    finally:
        os.close(descriptor)


def _pidfd_exited(poller: Any, timeout_ms: int) -> bool:
    events = poller.poll(timeout_ms)
    if any(event & ~(_POLLIN | _POLLHUP) for _descriptor, event in events):
        raise ProcessStatusError("cannot verify exit using the Linux process handle")
    return any(event & (_POLLIN | _POLLHUP) for _descriptor, event in events)


def _remaining_seconds(deadline: float, pid: int) -> float:
    remaining = deadline - time.monotonic()
    if remaining <= 0:
        raise TimeoutError(f"process {pid} did not exit before the shutdown deadline")
    return remaining


def _require_owned_reaping() -> None:
    child_signal = getattr(signal, "SIGCHLD", None)
    try:
        if child_signal is None or signal.getsignal(child_signal) != signal.SIG_DFL:
            raise ProcessIdentityError("owned-child management requires default SIGCHLD and Popen-only reaping")
    except (OSError, ValueError) as exc:
        raise ProcessStatusError("cannot verify the owned-child SIGCHLD configuration") from exc


def _signal_owned(process: subprocess.Popen[Any], *, kill: bool, deadline: float) -> None:
    if os.name == "nt":
        _remaining_seconds(deadline, process.pid)
        action = process.kill if kill else process.terminate
        action()
        return
    # Popen's wait lock prevents its poll/wait methods from reaping the child
    # between the returncode check and signal. An unreaped child retains its PID.
    wait_lock = getattr(process, "_waitpid_lock", None)
    if wait_lock is None:
        raise ProcessIdentityError("safe owned-child shutdown is unavailable; use the OS process manager")
    _require_owned_reaping()
    if not wait_lock.acquire(timeout=_remaining_seconds(deadline, process.pid)):
        raise TimeoutError(f"process {process.pid} did not exit; owned-child wait lock is busy")
    try:
        if process.returncode is None:
            _require_owned_reaping()
            _remaining_seconds(deadline, process.pid)
            action = process.kill if kill else process.terminate
            action()
    finally:
        wait_lock.release()


def terminate_owned_process(process: subprocess.Popen[Any], timeout_seconds: float = 5) -> None:
    """Stop and reap a real owned child, including one whose registration failed."""
    if not isinstance(process, subprocess.Popen):
        raise TypeError("managed process must be an actual subprocess.Popen child")
    timeout = _timeout(timeout_seconds)
    started = time.monotonic()
    deadline = started + timeout
    try:
        _signal_owned(process, kill=False, deadline=deadline)
        try:
            remaining = _remaining_seconds(deadline, process.pid)
            graceful = max(0.0, min(remaining, started + timeout / 2 - time.monotonic()))
            process.wait(timeout=graceful)
        except subprocess.TimeoutExpired:
            _signal_owned(process, kill=True, deadline=deadline)
            process.wait(timeout=_remaining_seconds(deadline, process.pid))
    except TimeoutError:
        raise
    except subprocess.TimeoutExpired as exc:
        raise TimeoutError(f"process {process.pid} did not exit within {timeout:g} seconds") from exc
    except OSError as exc:
        raise ProcessStatusError(f"cannot stop owned process {process.pid}: {exc}") from exc
    with _owned_lock:
        entry = _owned.get(process.pid)
        if entry is not None and entry[0] is process:
            del _owned[process.pid]


def terminate_recorded_process(
    pid: int, identity: Mapping[str, Any] | None, timeout_seconds: float = 5
) -> None:
    """Verify the birth identity and return only after the process has exited."""
    pid, timeout = _pid(pid), _timeout(timeout_seconds)
    identity = _validate_identity(pid, identity)
    try:
        if os.name == "nt" and identity["kind"] == "windows":
            _terminate_windows(pid, identity, timeout)
        elif sys.platform.startswith("linux") and identity["kind"] == "linux":
            _terminate_linux(pid, identity, timeout)
        else:
            with _owned_lock:
                entry = _owned.get(pid)
            if identity["kind"] != "owned" or entry is None or entry[1] != identity:
                raise ProcessIdentityError("safe shutdown identity is unavailable; use the OS process manager")
            terminate_owned_process(entry[0], timeout)
            return
    except ProcessLookupError:
        pass
    _reap_owned(pid, identity)

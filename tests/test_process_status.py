from __future__ import annotations

import ctypes
import json
import os
import signal
import subprocess
import sys
import threading
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from remote_ops_workspace import process_status as status
from remote_ops_workspace.process_launch import popen_hidden

PID = 43210
WINDOWS_ID = {"version": 1, "kind": "windows", "pid": PID, "creation_time": (3 << 32) | 17}
LINUX_ID = {"version": 1, "kind": "linux", "pid": PID, "start_ticks": 123, "boot_id": "boot"}
OWNED_ID = {"version": 1, "kind": "owned", "pid": PID, "token": "owned-token"}


@pytest.fixture(autouse=True)
def clear_registry():
    status._owned.clear()
    yield
    status._owned.clear()


@pytest.fixture
def owned_clock(monkeypatch):
    clock = [100.0]
    monkeypatch.setattr(status, "time", SimpleNamespace(monotonic=lambda: clock[0]))
    return clock


def platform(monkeypatch, name):
    # Avoid changing os.name globally: pathlib/pytest use the actual host OS.
    monkeypatch.setattr(status, "os", SimpleNamespace(name=name))
    monkeypatch.setattr(status, "sys", SimpleNamespace(platform="other"))
    monkeypatch.setattr(status, "signal", SimpleNamespace(SIGCHLD=17, SIG_DFL=0, getsignal=lambda _sig: 0))


class WindowsAPI:
    def __init__(self):
        self.handle = 88
        self.open_calls = []
        self.waits = [status._WAIT_TIMEOUT]
        self.wait_calls = []
        self.closed = []
        self.birth = WINDOWS_ID["creation_time"]
        self.times_ok = True
        self.terminate_ok = True
        self.terminated = []

    def OpenProcess(self, access, inherit, pid):
        self.open_calls.append((access, inherit, pid))
        return self.handle

    def GetProcessTimes(self, handle, creation, *_rest):
        assert handle == self.handle
        creation._obj.dwHighDateTime = self.birth >> 32
        creation._obj.dwLowDateTime = self.birth & 0xFFFFFFFF
        return self.times_ok

    def WaitForSingleObject(self, handle, timeout):
        self.wait_calls.append((handle, timeout))
        if len(self.waits) > 1:
            return self.waits.pop(0)
        return self.waits[0]

    def TerminateProcess(self, handle, code):
        self.terminated.append((handle, code))
        return self.terminate_ok

    def CloseHandle(self, handle):
        self.closed.append(handle)


@pytest.fixture
def windows(monkeypatch):
    platform(monkeypatch, "nt")
    api = WindowsAPI()
    monkeypatch.setattr(status, "_windows_api", lambda: api)
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 5, raising=False)
    return api


@pytest.mark.parametrize("pid", [0, -1, True, 1.5, "5", 0x100000000])
def test_invalid_pid_rejected(pid):
    with pytest.raises(ValueError, match="PID"):
        status.process_is_running(pid)
    with pytest.raises(ValueError, match="PID"):
        status.capture_process_identity(pid)
    with pytest.raises(ValueError, match="PID"):
        status.recorded_process_is_running(pid, None)


@pytest.mark.parametrize("timeout", [True, "5", None, 0, -1, float("nan"), float("inf"), 86401])
def test_invalid_timeout_rejected(timeout):
    with pytest.raises(ValueError, match="timeout"):
        status.terminate_recorded_process(PID, WINDOWS_ID, timeout)


@pytest.mark.parametrize(
    "identity",
    [None, {}, {"version": True, "pid": PID}, {"version": 1, "pid": True},
     {"version": 2, "pid": PID}, {"version": 1, "pid": 9},
     {"version": 1, "pid": PID, "kind": "unknown"},
     {**WINDOWS_ID, "creation_time": 0}, {**WINDOWS_ID, "creation_time": True},
     {**WINDOWS_ID, "creation_time": "1"}, {**WINDOWS_ID, "creation_time": 1 << 64},
     {**LINUX_ID, "start_ticks": 0},
     {**LINUX_ID, "start_ticks": True}, {**LINUX_ID, "start_ticks": "1"},
     {**LINUX_ID, "boot_id": None}, {**LINUX_ID, "boot_id": " "},
     {**OWNED_ID, "token": ""}, {**OWNED_ID, "token": 5}],
)
def test_legacy_or_invalid_identity_never_opens_or_signals(windows, identity):
    with pytest.raises(status.ProcessIdentityError, match="identity"):
        status.terminate_recorded_process(PID, identity)
    with pytest.raises(status.ProcessIdentityError, match="identity"):
        status.recorded_process_is_running(PID, identity)
    assert windows.open_calls == []
    assert windows.terminated == []


def test_windows_status_and_capture_use_query_handle_without_signals(windows):
    assert status.process_is_running(PID) is True
    assert status.capture_process_identity(PID) == WINDOWS_ID
    assert windows.open_calls == [(status._QUERY | status._SYNCHRONIZE, False, PID)] * 2
    assert windows.closed == [88, 88]
    assert windows.terminated == []
    assert json.loads(json.dumps(WINDOWS_ID)) == WINDOWS_ID


def test_windows_recorded_status_verifies_birth_on_same_query_handle(windows):
    assert status.recorded_process_is_running(PID, WINDOWS_ID) is True
    assert windows.open_calls == [(status._QUERY | status._SYNCHRONIZE, False, PID)]
    assert windows.wait_calls == [(88, 0)]
    assert windows.closed == [88]
    assert windows.terminated == []


def test_windows_recorded_status_mismatch_refuses_unrelated_live_pid(windows):
    windows.birth += 1
    with pytest.raises(status.ProcessIdentityError, match="reused PID"):
        status.recorded_process_is_running(PID, WINDOWS_ID)
    assert windows.wait_calls == []
    assert windows.closed == [88]
    assert windows.terminated == []


def test_windows_recorded_status_reports_matching_exit(windows):
    windows.waits = [0]
    assert status.recorded_process_is_running(PID, WINDOWS_ID) is False


def test_windows_recorded_status_missing_is_false_and_denied_is_uncertain(windows, monkeypatch):
    windows.handle = 0
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 87)
    assert status.recorded_process_is_running(PID, WINDOWS_ID) is False
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 5)
    with pytest.raises(status.ProcessStatusError, match="OpenProcess"):
        status.recorded_process_is_running(PID, WINDOWS_ID)


def test_windows_exited_process_status_and_capture(windows):
    windows.waits = [0]
    assert status.process_is_running(PID) is False
    with pytest.raises(ProcessLookupError):
        status.capture_process_identity(PID)
    assert windows.closed == [88, 88]


@pytest.mark.parametrize("action", ["status", "capture", "stop"])
def test_windows_missing_process_is_confirmed(windows, monkeypatch, action):
    windows.handle = 0
    monkeypatch.setattr(ctypes, "get_last_error", lambda: 87)
    if action == "status":
        assert status.process_is_running(PID) is False
    elif action == "capture":
        with pytest.raises(ProcessLookupError):
            status.capture_process_identity(PID)
    else:
        status.terminate_recorded_process(PID, WINDOWS_ID)
    assert windows.closed == []


def test_windows_access_denied_is_uncertainty(windows):
    windows.handle = 0
    with pytest.raises(status.ProcessStatusError, match="Windows error 5"):
        status.process_is_running(PID)
    with pytest.raises(status.ProcessStatusError):
        status.terminate_recorded_process(PID, WINDOWS_ID)


def test_windows_query_failure_closes_handle(windows):
    windows.times_ok = False
    with pytest.raises(status.ProcessStatusError, match="GetProcessTimes"):
        status.capture_process_identity(PID)
    assert windows.closed == [88]


def test_windows_missing_birth_time_fails_closed(windows):
    windows.birth = 0
    with pytest.raises(status.ProcessStatusError, match="birth time"):
        status.capture_process_identity(PID)
    assert windows.closed == [88]


def test_windows_wait_failure_closes_handle(windows):
    windows.waits = [0xFFFFFFFF]
    with pytest.raises(status.ProcessStatusError, match="WaitForSingleObject"):
        status.process_is_running(PID)
    assert windows.closed == [88]


def test_windows_stop_verifies_birth_and_waits_on_same_handle(windows):
    windows.waits = [status._WAIT_TIMEOUT, 0]
    status.terminate_recorded_process(PID, WINDOWS_ID, 0.0012)
    assert windows.open_calls == [(status._QUERY | status._SYNCHRONIZE | status._TERMINATE, False, PID)]
    assert windows.terminated == [(88, 1)]
    assert windows.wait_calls == [(88, 0), (88, 2)]
    assert windows.closed == [88]


def test_windows_mismatch_never_terminates(windows):
    windows.birth += 1
    with pytest.raises(status.ProcessIdentityError, match="reused PID"):
        status.terminate_recorded_process(PID, WINDOWS_ID)
    assert windows.terminated == []
    assert windows.closed == [88]


def test_windows_already_exited_instance_needs_no_termination(windows):
    windows.waits = [0]
    status.terminate_recorded_process(PID, WINDOWS_ID)
    assert windows.terminated == []


def test_windows_failed_termination_requires_exit_confirmation(windows):
    windows.terminate_ok = False
    with pytest.raises(status.ProcessStatusError, match="TerminateProcess"):
        status.terminate_recorded_process(PID, WINDOWS_ID)
    assert windows.closed == [88]


def test_windows_exit_racing_termination_is_confirmed(windows):
    windows.terminate_ok = False
    windows.waits = [258, 0, 0]
    status.terminate_recorded_process(PID, WINDOWS_ID)


def test_windows_timeout_preserves_failure(windows):
    with pytest.raises(TimeoutError, match="did not exit"):
        status.terminate_recorded_process(PID, WINDOWS_ID, 0.01)
    assert windows.closed == [88]


def linux(monkeypatch):
    fake_os = SimpleNamespace(name="posix", kill=lambda *_args: None, close=lambda *_args: None)
    monkeypatch.setattr(status, "os", fake_os)
    monkeypatch.setattr(status, "sys", SimpleNamespace(platform="linux"))
    monkeypatch.setattr(status, "signal", SimpleNamespace(SIGCHLD=17, SIG_DFL=0, getsignal=lambda _sig: 0))
    return fake_os


def proc_stat(state="S", ticks="123"):
    return f"{PID} (process ) strange name) {state} " + " ".join(["0"] * 18 + [ticks])


def test_linux_capture_handles_parentheses_in_name(monkeypatch):
    linux(monkeypatch)
    monkeypatch.setattr(Path, "read_text", lambda path, **_kwargs: " boot\n" if "boot_id" in str(path) else proc_stat())
    assert status.capture_process_identity(PID) == LINUX_ID
    assert status.process_is_running(PID) is True
    assert status.recorded_process_is_running(PID, LINUX_ID) is True


@pytest.mark.parametrize("changed", [{"start_ticks": 124}, {"boot_id": "different-boot"}])
def test_linux_recorded_status_refuses_reused_pid_or_other_boot(monkeypatch, changed):
    fake_os = linux(monkeypatch)
    fake_os.kill = lambda *_args: pytest.fail("recorded status unexpectedly signaled a PID")
    monkeypatch.setattr(status, "_linux_identity", lambda _pid: ({**LINUX_ID, **changed}, True))
    with pytest.raises(status.ProcessIdentityError, match="reused PID"):
        status.recorded_process_is_running(PID, LINUX_ID)


def test_linux_recorded_status_reads_one_birth_and_state_snapshot(monkeypatch):
    linux(monkeypatch)
    calls = []
    def identity(pid):
        calls.append(pid)
        return LINUX_ID.copy(), False
    monkeypatch.setattr(status, "_linux_identity", identity)
    assert status.recorded_process_is_running(PID, LINUX_ID) is False
    assert calls == [PID]


@pytest.mark.parametrize("error", [ProcessLookupError(), PermissionError("denied")])
def test_linux_recorded_status_distinguishes_absence_and_uncertainty(monkeypatch, error):
    linux(monkeypatch)
    def fail(_pid):
        raise error
    monkeypatch.setattr(status, "_linux_identity", fail)
    if isinstance(error, ProcessLookupError):
        assert status.recorded_process_is_running(PID, LINUX_ID) is False
    else:
        with pytest.raises(status.ProcessStatusError, match="cannot inspect recorded process"):
            status.recorded_process_is_running(PID, LINUX_ID)


@pytest.mark.parametrize("state", ["Z", "X", "x"])
def test_linux_zombie_is_exited(monkeypatch, state):
    linux(monkeypatch)
    monkeypatch.setattr(Path, "read_text", lambda path, **_kwargs: "boot" if "boot_id" in str(path) else proc_stat(state))
    assert status.process_is_running(PID) is False
    with pytest.raises(ProcessLookupError):
        status.capture_process_identity(PID)


@pytest.mark.parametrize("stat,boot", [("malformed", "boot"), (proc_stat(ticks="bad"), "boot"), (proc_stat(ticks="0"), "boot"), (proc_stat(), ""), (f"{PID} (name) S", "boot")])
def test_linux_bad_identity_data_is_uncertainty(monkeypatch, stat, boot):
    linux(monkeypatch)
    monkeypatch.setattr(Path, "read_text", lambda path, **_kwargs: boot if "boot_id" in str(path) else stat)
    with pytest.raises(status.ProcessStatusError, match="cannot read Linux identity"):
        status.capture_process_identity(PID)


@pytest.mark.parametrize("error", [PermissionError("denied"), OSError("read failed")])
def test_linux_unreadable_proc_is_uncertainty(monkeypatch, error):
    linux(monkeypatch)
    def fail(*_args, **_kwargs):
        raise error
    monkeypatch.setattr(Path, "read_text", fail)
    with pytest.raises(status.ProcessStatusError):
        status.process_is_running(PID)


@pytest.mark.parametrize("probe", ["missing", "denied", "alive"])
def test_linux_missing_proc_requires_os_exit_proof(monkeypatch, probe):
    fake_os = linux(monkeypatch)
    def missing(*_args, **_kwargs):
        raise FileNotFoundError("missing")
    def kill(pid, sig):
        assert (pid, sig) == (PID, 0)
        if probe == "missing":
            raise ProcessLookupError()
        if probe == "denied":
            raise PermissionError()
    fake_os.kill = kill
    monkeypatch.setattr(Path, "read_text", missing)
    if probe == "missing":
        assert status.process_is_running(PID) is False
    else:
        with pytest.raises(status.ProcessStatusError):
            status.process_is_running(PID)


class Poller:
    def __init__(self):
        self.outcomes = [[], [(71, 1)]]
        self.registered = []
        self.calls = []

    def register(self, *args):
        self.registered.append(args)

    def poll(self, timeout):
        self.calls.append(timeout)
        return self.outcomes.pop(0)


@pytest.fixture
def pidfd(monkeypatch):
    fake_os = linux(monkeypatch)
    calls = {"opens": [], "signals": [], "closes": []}
    def open_pidfd(pid, flags):
        calls["opens"].append((pid, flags))
        return 71
    fake_os.pidfd_open = open_pidfd
    fake_os.close = calls["closes"].append
    monkeypatch.setattr(status, "_linux_identity", lambda _pid: (LINUX_ID.copy(), True))
    poller = Poller()
    monkeypatch.setattr(status, "select", SimpleNamespace(poll=lambda: poller, POLLIN=1, POLLHUP=16))
    fake_signal = SimpleNamespace(SIGTERM=15, pidfd_send_signal=lambda *args: calls["signals"].append(args))
    monkeypatch.setattr(status, "signal", fake_signal)
    return fake_os, fake_signal, poller, calls


def test_linux_termination_uses_pidfd_for_signal_and_exit(pidfd):
    _fake_os, _fake_signal, poller, calls = pidfd
    status.terminate_recorded_process(PID, LINUX_ID, 0.0012)
    assert calls == {"opens": [(PID, 0)], "signals": [(71, 15, None, 0)], "closes": [71]}
    assert poller.registered == [(71, 1)]
    assert poller.calls == [0, 2]


@pytest.mark.parametrize("which", ["open", "signal"])
def test_linux_without_pidfd_support_fails_closed(pidfd, which):
    fake_os, fake_signal, _poller, calls = pidfd
    delattr(fake_os if which == "open" else fake_signal, "pidfd_open" if which == "open" else "pidfd_send_signal")
    with pytest.raises(status.ProcessIdentityError, match="pidfd support"):
        status.terminate_recorded_process(PID, LINUX_ID)
    assert calls["signals"] == []


@pytest.mark.parametrize("error", [ProcessLookupError(), PermissionError("denied")])
def test_linux_pidfd_open_failure_is_safe(pidfd, error):
    fake_os, _fake_signal, _poller, calls = pidfd
    def fail(*_args):
        raise error
    fake_os.pidfd_open = fail
    if isinstance(error, ProcessLookupError):
        status.terminate_recorded_process(PID, LINUX_ID)
    else:
        with pytest.raises(status.ProcessStatusError, match="stable handle"):
            status.terminate_recorded_process(PID, LINUX_ID)
    assert calls["closes"] == []


def test_linux_exit_before_identity_read_needs_no_signal(pidfd):
    _fake_os, _fake_signal, poller, calls = pidfd
    poller.outcomes = [[(71, 16)]]
    status.terminate_recorded_process(PID, LINUX_ID)
    assert calls["signals"] == []
    assert calls["closes"] == [71]


def test_linux_identity_mismatch_never_signals(pidfd, monkeypatch):
    _fake_os, _fake_signal, _poller, calls = pidfd
    monkeypatch.setattr(status, "_linux_identity", lambda _pid: ({**LINUX_ID, "start_ticks": 124}, True))
    with pytest.raises(status.ProcessIdentityError, match="reused PID"):
        status.terminate_recorded_process(PID, LINUX_ID)
    assert calls["signals"] == []
    assert calls["closes"] == [71]


def test_linux_zombie_identity_needs_no_signal(pidfd, monkeypatch):
    _fake_os, _fake_signal, _poller, calls = pidfd
    monkeypatch.setattr(status, "_linux_identity", lambda _pid: (LINUX_ID, False))
    status.terminate_recorded_process(PID, LINUX_ID)
    assert calls["signals"] == []


@pytest.mark.parametrize("error", [ProcessLookupError(), PermissionError("denied")])
def test_linux_signal_failure_needs_exit_proof(pidfd, error):
    _fake_os, fake_signal, _poller, calls = pidfd
    def fail(*_args):
        raise error
    fake_signal.pidfd_send_signal = fail
    if isinstance(error, ProcessLookupError):
        status.terminate_recorded_process(PID, LINUX_ID)
    else:
        with pytest.raises(status.ProcessStatusError, match="cannot stop process"):
            status.terminate_recorded_process(PID, LINUX_ID)
    assert calls["closes"] == [71]


def test_linux_timeout_is_not_reported_as_exit(pidfd):
    _fake_os, _fake_signal, poller, calls = pidfd
    poller.outcomes = [[], []]
    with pytest.raises(TimeoutError, match="did not exit"):
        status.terminate_recorded_process(PID, LINUX_ID)
    assert calls["closes"] == [71]


@pytest.mark.parametrize("exited", [False, True])
def test_linux_proc_disappearing_needs_pidfd_exit_confirmation(pidfd, monkeypatch, exited):
    _fake_os, _fake_signal, poller, calls = pidfd
    def gone(_pid):
        raise ProcessLookupError()
    monkeypatch.setattr(status, "_linux_identity", gone)
    poller.outcomes = [[], [(71, 1)] if exited else []]
    if exited:
        status.terminate_recorded_process(PID, LINUX_ID)
    else:
        with pytest.raises(status.ProcessStatusError, match="cannot verify exit"):
            status.terminate_recorded_process(PID, LINUX_ID)
    assert calls["signals"] == []
    assert calls["closes"] == [71]


def test_linux_invalid_poll_event_does_not_confirm_exit(pidfd):
    _fake_os, _fake_signal, poller, calls = pidfd
    poller.outcomes = [[(71, 32)]]
    with pytest.raises(status.ProcessStatusError, match="Linux process handle"):
        status.terminate_recorded_process(PID, LINUX_ID)
    assert calls["signals"] == []


class OwnedChild(subprocess.Popen):
    def __init__(self):
        self.pid = PID
        self.returncode = None
        self._waitpid_lock = threading.Lock()
        self._handle = 88
        self.actions = []
        self.wait_errors = []
        self.signal_error = None

    def poll(self):
        return self.returncode

    def terminate(self):
        self.actions.append(("terminate", self._waitpid_lock.locked()))
        if self.signal_error:
            raise self.signal_error

    def kill(self):
        self.actions.append(("kill", self._waitpid_lock.locked()))

    def wait(self, timeout=None):
        self.actions.append(("wait", timeout))
        if self.wait_errors:
            raise self.wait_errors.pop(0)
        self.returncode = 0
        return 0

    def __del__(self):
        pass


def test_registration_rejects_non_popen():
    with pytest.raises(TypeError, match="actual subprocess.Popen"):
        status.register_process(SimpleNamespace(pid=PID))
    with pytest.raises(TypeError, match="actual subprocess.Popen"):
        status.terminate_owned_process(SimpleNamespace(pid=PID))


def test_native_registration_keeps_child_and_copy(windows):
    process = OwnedChild()
    identity = status.register_process(process)
    identity["creation_time"] = 99
    assert status._owned[PID] == (process, WINDOWS_ID)
    assert windows.open_calls == []


def test_windows_registration_uses_owned_handle_and_rejects_exited_child(windows):
    process = OwnedChild()
    windows.waits = [0]
    with pytest.raises(ProcessLookupError):
        status.register_process(process)
    del process._handle
    with pytest.raises(status.ProcessIdentityError, match="registration"):
        status.register_process(process)
    assert windows.open_calls == []


def test_linux_registration_holds_wait_lock_during_identity_capture(monkeypatch):
    linux(monkeypatch)
    process = OwnedChild()
    def capture(pid):
        assert pid == PID
        assert process._waitpid_lock.locked()
        return LINUX_ID.copy()
    monkeypatch.setattr(status, "capture_process_identity", capture)
    assert status.register_process(process) == LINUX_ID
    assert not process._waitpid_lock.locked()


def test_linux_registration_rejects_reaped_child_and_missing_wait_lock(monkeypatch):
    linux(monkeypatch)
    process = OwnedChild()
    process.returncode = 0
    with pytest.raises(ProcessLookupError):
        status.register_process(process)
    del process._waitpid_lock
    with pytest.raises(status.ProcessIdentityError, match="registration"):
        status.register_process(process)
    assert status._owned == {}


def test_linux_registration_refuses_waiter_contention_without_waiting(monkeypatch):
    linux(monkeypatch)
    process = OwnedChild()
    process._waitpid_lock.acquire()
    try:
        with pytest.raises(status.ProcessStatusError, match="register before starting background waiters"):
            status.register_process(process)
    finally:
        process._waitpid_lock.release()
    assert status._owned == {}


@pytest.mark.parametrize("host", ["linux", "other"])
@pytest.mark.parametrize("handler", [1, lambda *_args: None])
def test_posix_owned_management_rejects_ignored_or_custom_sigchld(monkeypatch, host, handler):
    if host == "linux":
        linux(monkeypatch)
    else:
        platform(monkeypatch, "posix")
    status.signal.getsignal = lambda _sig: handler
    process = OwnedChild()
    with pytest.raises(status.ProcessIdentityError, match="default SIGCHLD and Popen-only reaping"):
        status.register_process(process)
    with pytest.raises(status.ProcessIdentityError, match="default SIGCHLD and Popen-only reaping"):
        status.terminate_owned_process(process)
    assert process.actions == []
    assert not process._waitpid_lock.locked()
    assert status._owned == {}


def test_posix_owned_management_rejects_unavailable_sigchld(monkeypatch):
    platform(monkeypatch, "posix")
    del status.signal.SIGCHLD
    with pytest.raises(status.ProcessIdentityError, match="default SIGCHLD"):
        status.register_process(OwnedChild())


@pytest.mark.parametrize("error", [PermissionError("denied"), ValueError("unsupported")])
def test_posix_owned_management_rejects_unverifiable_sigchld(monkeypatch, error):
    platform(monkeypatch, "posix")
    def fail(_sig):
        raise error
    status.signal.getsignal = fail
    with pytest.raises(status.ProcessStatusError, match="cannot verify.*SIGCHLD"):
        status.terminate_owned_process(OwnedChild())


def test_posix_owned_signal_rechecks_sigchld_after_wait_lock(monkeypatch):
    platform(monkeypatch, "posix")
    handlers = iter([0, 1])
    status.signal.getsignal = lambda _sig: next(handlers)
    process = OwnedChild()
    with pytest.raises(status.ProcessIdentityError, match="default SIGCHLD"):
        status.terminate_owned_process(process)
    assert process.actions == []
    assert not process._waitpid_lock.locked()


def test_other_posix_capture_fails_closed(monkeypatch):
    platform(monkeypatch, "posix")
    with pytest.raises(status.ProcessIdentityError, match="register an owned child"):
        status.capture_process_identity(PID)


def test_other_posix_registration_stop_uses_retained_child(monkeypatch, owned_clock):
    platform(monkeypatch, "posix")
    process = OwnedChild()
    identity = status.register_process(process)
    assert identity["kind"] == "owned"
    assert isinstance(identity["token"], str)
    status.terminate_recorded_process(PID, identity, 2)
    assert process.actions == [("terminate", True), ("wait", 1)]
    assert status._owned == {}


def test_other_posix_recorded_status_only_polls_matching_owned_child(monkeypatch):
    platform(monkeypatch, "posix")
    process = OwnedChild()
    status._owned[PID] = (process, OWNED_ID.copy())
    assert status.recorded_process_is_running(PID, OWNED_ID) is True
    process.returncode = 0
    assert status.recorded_process_is_running(PID, OWNED_ID) is False
    assert process.actions == []


def test_registration_of_exited_child_is_rejected(monkeypatch):
    platform(monkeypatch, "posix")
    process = OwnedChild()
    process.returncode = 0
    with pytest.raises(ProcessLookupError):
        status.register_process(process)


@pytest.mark.parametrize("identity,entry", [(WINDOWS_ID, None), (OWNED_ID, None), (OWNED_ID, (OwnedChild(), {**OWNED_ID, "token": "different"}))])
def test_other_posix_record_without_matching_owned_child_fails_closed(monkeypatch, identity, entry):
    platform(monkeypatch, "posix")
    if entry:
        status._owned[PID] = entry
    with pytest.raises(status.ProcessIdentityError, match="OS process manager"):
        status.terminate_recorded_process(PID, identity)
    with pytest.raises(status.ProcessIdentityError, match="safe status identity"):
        status.recorded_process_is_running(PID, identity)


@pytest.mark.parametrize("result", ["alive", "missing", "denied"])
def test_other_posix_status_only_sends_signal_zero(monkeypatch, result):
    platform(monkeypatch, "posix")
    def kill(pid, sig):
        assert (pid, sig) == (PID, 0)
        if result == "missing":
            raise ProcessLookupError()
        if result == "denied":
            raise PermissionError("denied")
    status.os.kill = kill
    if result == "denied":
        with pytest.raises(status.ProcessStatusError):
            status.process_is_running(PID)
    else:
        assert status.process_is_running(PID) is (result == "alive")


def test_owned_child_cleanup_escalates_and_reaps(monkeypatch, owned_clock):
    platform(monkeypatch, "posix")
    process = OwnedChild()
    process.wait_errors = [subprocess.TimeoutExpired("child", 1)]
    status._owned[PID] = (process, OWNED_ID)
    status.terminate_owned_process(process, 2)
    assert process.actions == [("terminate", True), ("wait", 1), ("kill", True), ("wait", 2)]
    assert status._owned == {}


def test_owned_child_cleanup_timeout_preserves_registry(monkeypatch):
    platform(monkeypatch, "posix")
    process = OwnedChild()
    process.wait_errors = [subprocess.TimeoutExpired("child", 1)] * 2
    status._owned[PID] = (process, OWNED_ID)
    with pytest.raises(TimeoutError, match="did not exit"):
        status.terminate_owned_process(process, 2)
    assert PID in status._owned


def test_owned_child_cleanup_permission_error(monkeypatch):
    platform(monkeypatch, "posix")
    process = OwnedChild()
    process.signal_error = PermissionError("denied")
    with pytest.raises(status.ProcessStatusError, match="owned process"):
        status.terminate_owned_process(process)


def test_owned_child_without_wait_lock_fails_closed(monkeypatch):
    platform(monkeypatch, "posix")
    process = OwnedChild()
    del process._waitpid_lock
    with pytest.raises(status.ProcessIdentityError, match="safe owned-child"):
        status.terminate_owned_process(process)


def test_owned_child_already_reaped_never_signals(monkeypatch, owned_clock):
    platform(monkeypatch, "posix")
    process = OwnedChild()
    process.returncode = 0
    status.terminate_owned_process(process)
    assert process.actions == [("wait", 2.5)]


def test_owned_windows_child_escalation_uses_process_methods(windows, owned_clock):
    process = OwnedChild()
    process.wait_errors = [subprocess.TimeoutExpired("child", 1)]
    status.terminate_owned_process(process, 2)
    assert process.actions == [("terminate", False), ("wait", 1), ("kill", False), ("wait", 2)]


def test_cleanup_does_not_remove_different_child_registry_entry(monkeypatch):
    platform(monkeypatch, "posix")
    process, other = OwnedChild(), OwnedChild()
    status._owned[PID] = (other, OWNED_ID)
    status.terminate_owned_process(process)
    assert status._owned[PID][0] is other


def test_native_stop_reaps_only_matching_owned_child(windows):
    process = OwnedChild()
    status._owned[PID] = (process, WINDOWS_ID.copy())
    windows.waits = [0]
    status.terminate_recorded_process(PID, WINDOWS_ID)
    assert process.actions == [("wait", 0)]
    assert status._owned == {}
    status._owned[PID] = (process, {**WINDOWS_ID, "creation_time": 99})
    status.terminate_recorded_process(PID, WINDOWS_ID)
    assert PID in status._owned


def test_native_stop_normalizes_owned_reap_contention(windows):
    process = OwnedChild()
    process.wait_errors = [subprocess.TimeoutExpired("child", 0)]
    status._owned[PID] = (process, WINDOWS_ID.copy())
    windows.waits = [0]
    with pytest.raises(status.ProcessStatusError, match="exited but owned-child reaping is still busy"):
        status.terminate_recorded_process(PID, WINDOWS_ID)
    assert status._owned[PID][0] is process


def test_reaping_never_holds_registry_or_removes_replaced_entry(windows, monkeypatch):
    process, replacement = OwnedChild(), OwnedChild()
    status._owned[PID] = (process, WINDOWS_ID.copy())
    def wait(timeout):
        assert timeout == 0
        assert not status._owned_lock._is_owned()
        status._owned[PID] = (replacement, WINDOWS_ID.copy())
        return 0
    monkeypatch.setattr(process, "wait", wait)
    windows.waits = [0]
    status.terminate_recorded_process(PID, WINDOWS_ID)
    assert status._owned[PID][0] is replacement


class TimedWaitLock:
    def __init__(self, clock, *, delays, available=True):
        self.clock = clock
        self.delays = list(delays)
        self.available = available
        self.held = False
        self.timeouts = []

    def acquire(self, timeout):
        self.timeouts.append(timeout)
        self.clock[0] += self.delays.pop(0)
        self.held = self.available
        return self.available

    def release(self):
        self.held = False

    def locked(self):
        return self.held


def test_owned_cleanup_shares_deadline_across_locks_grace_and_kill(monkeypatch, owned_clock):
    platform(monkeypatch, "posix")
    process = OwnedChild()
    lock = TimedWaitLock(owned_clock, delays=[0.75, 0.25])
    process._waitpid_lock = lock
    waits = []
    def wait(timeout):
        assert not status._owned_lock._is_owned()
        waits.append(timeout)
        owned_clock[0] += timeout
        raise subprocess.TimeoutExpired("child", timeout)
    monkeypatch.setattr(process, "wait", wait)
    status._owned[PID] = (process, OWNED_ID.copy())
    with pytest.raises(TimeoutError, match="did not exit within 2 seconds"):
        status.terminate_owned_process(process, 2)
    assert lock.timeouts == [2, 1]
    assert waits == [0.25, 0.75]
    assert owned_clock[0] == 102
    assert process.actions == [("terminate", True), ("kill", True)]
    assert not lock.locked()
    assert status._owned[PID][0] is process


def test_owned_cleanup_contended_lock_consumes_only_remaining_budget(monkeypatch, owned_clock):
    platform(monkeypatch, "posix")
    process = OwnedChild()
    process._waitpid_lock = TimedWaitLock(owned_clock, delays=[2], available=False)
    with pytest.raises(TimeoutError, match="wait lock is busy"):
        status.terminate_owned_process(process, 2)
    assert process._waitpid_lock.timeouts == [2]
    assert process.actions == []
    assert owned_clock[0] == 102


def test_owned_cleanup_never_signals_after_deadline(monkeypatch, owned_clock):
    platform(monkeypatch, "posix")
    process = OwnedChild()
    process._waitpid_lock = TimedWaitLock(owned_clock, delays=[2])
    with pytest.raises(TimeoutError, match="shutdown deadline"):
        status.terminate_owned_process(process, 2)
    assert process.actions == []
    assert not process._waitpid_lock.locked()


def test_owned_cleanup_late_lock_uses_zero_grace_wait_then_remaining_budget(monkeypatch, owned_clock):
    platform(monkeypatch, "posix")
    process = OwnedChild()
    process._waitpid_lock = TimedWaitLock(owned_clock, delays=[1.5, 0])
    process.wait_errors = [subprocess.TimeoutExpired("child", 0)]
    status.terminate_owned_process(process, 2)
    assert process.actions == [("terminate", True), ("wait", 0), ("kill", True), ("wait", 0.5)]


def test_owned_status_and_shutdown_never_hold_registry_during_child_operations(monkeypatch, owned_clock):
    platform(monkeypatch, "posix")
    process = OwnedChild()
    status._owned[PID] = (process, OWNED_ID.copy())
    def poll():
        assert not status._owned_lock._is_owned()
        return None
    def terminate():
        assert not status._owned_lock._is_owned()
    def wait(timeout):
        assert not status._owned_lock._is_owned()
        status._owned[PID] = (OwnedChild(), OWNED_ID.copy())
        return 0
    monkeypatch.setattr(process, "poll", poll)
    monkeypatch.setattr(process, "terminate", terminate)
    monkeypatch.setattr(process, "wait", wait)
    assert status.recorded_process_is_running(PID, OWNED_ID)
    status.terminate_recorded_process(PID, OWNED_ID, 2)
    assert status._owned[PID][0] is not process


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="real POSIX Popen waiter contention proof")
def test_real_linux_waiter_contention_respects_cleanup_deadline():
    child = popen_hidden([sys.executable, "-c", "import time; time.sleep(30)"])
    descriptor = os.pidfd_open(child.pid, 0)
    waiter = threading.Thread(target=child.wait)
    waiter.start()
    try:
        limit = time.monotonic() + 5
        while not child._waitpid_lock.locked():
            assert time.monotonic() < limit
            time.sleep(0.001)
        started = time.monotonic()
        with pytest.raises(status.ProcessStatusError, match="registration is busy"):
            status.register_process(child)
        assert time.monotonic() - started < 0.25
        started = time.monotonic()
        with pytest.raises(TimeoutError, match="wait lock is busy"):
            status.terminate_owned_process(child, timeout_seconds=0.05)
        elapsed = time.monotonic() - started
        assert 0.025 <= elapsed < 0.3
        assert child.poll() is None
    finally:
        try:
            signal.pidfd_send_signal(descriptor, signal.SIGKILL, None, 0)
        except ProcessLookupError:
            pass
        os.close(descriptor)
        waiter.join(5)
        assert not waiter.is_alive()
        child.wait(timeout=1)


@pytest.mark.skipif(os.name != "nt", reason="real Windows process handle proof")
def test_real_windows_status_is_nondestructive_and_shutdown_is_verified():
    child = popen_hidden([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        identity = status.register_process(child)
        assert identity["kind"] == "windows"
        for _ in range(3):
            assert status.process_is_running(child.pid)
            assert status.recorded_process_is_running(child.pid, identity)
            assert child.poll() is None
        with pytest.raises(status.ProcessIdentityError, match="reused PID"):
            status.recorded_process_is_running(child.pid, {**identity, "creation_time": identity["creation_time"] + 1})
        assert child.poll() is None
        with pytest.raises(status.ProcessIdentityError):
            status.terminate_recorded_process(child.pid, {**identity, "creation_time": identity["creation_time"] + 1})
        assert child.poll() is None
        status.terminate_recorded_process(child.pid, identity)
        assert child.poll() is not None
        assert child.pid not in status._owned
        assert status.process_is_running(child.pid) is False
        assert status.recorded_process_is_running(child.pid, identity) is False
    finally:
        if child.poll() is None:
            child.kill()
        child.wait()


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="real Linux pidfd proof")
def test_real_linux_pidfd_shutdown_is_verified():
    child = popen_hidden([sys.executable, "-c", "import time; time.sleep(30)"])
    try:
        identity = status.register_process(child)
        assert status.process_is_running(child.pid)
        assert status.recorded_process_is_running(child.pid, identity)
        with pytest.raises(status.ProcessIdentityError, match="reused PID"):
            status.recorded_process_is_running(child.pid, {**identity, "start_ticks": identity["start_ticks"] + 1})
        assert child.poll() is None
        status.terminate_recorded_process(child.pid, identity)
        assert child.poll() is not None
        assert child.pid not in status._owned
    finally:
        if child.poll() is None:
            child.kill()
        child.wait()

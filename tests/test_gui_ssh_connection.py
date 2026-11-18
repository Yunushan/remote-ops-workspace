from __future__ import annotations

import os
import stat
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

qt = pytest.importorskip("PyQt6.QtCore")
connection = pytest.importorskip("remote_ops_workspace.gui_ssh_connection")


class _Probe:
    ProcessState = qt.QProcess.ProcessState
    ExitStatus = qt.QProcess.ExitStatus
    ProcessError = qt.QProcess.ProcessError

    def __init__(self, _parent):
        self._state = self.ProcessState.NotRunning
        self.finished = SimpleNamespace(connect=Mock())
        self.errorOccurred = SimpleNamespace(connect=Mock())
        self.program = None
        self.arguments = []
        self.stdout = None
        self.stderr = None
        self.starts = 0
        self.kills = 0

    def setProgram(self, program):
        self.program = program

    def setArguments(self, arguments):
        self.arguments = arguments

    def setStandardOutputFile(self, path):
        self.stdout = path

    def setStandardErrorFile(self, path):
        self.stderr = path

    def state(self):
        return self._state

    def start(self):
        self.starts += 1
        self._state = self.ProcessState.Running

    def kill(self):
        self.kills += 1
        self._state = self.ProcessState.NotRunning

    def complete(self, code=0, status=qt.QProcess.ExitStatus.NormalExit):
        self._state = self.ProcessState.NotRunning
        self.finished.connect.call_args.args[0](code, status)


class _Timer:
    def __init__(self, _parent):
        self.timeout = SimpleNamespace(connect=Mock())
        self.interval = 0
        self.active = False

    def setSingleShot(self, _value):
        pass

    def setInterval(self, interval):
        self.interval = interval

    def start(self, interval):
        self.interval = interval
        self.active = True

    def stop(self):
        self.active = False


@pytest.fixture
def lease(monkeypatch):
    socket = Path("/fixture/private/master")
    real_lstat = Path.lstat
    mode = SimpleNamespace(value=None)

    def lstat(path):
        if path != socket:
            return real_lstat(path)
        if mode.value is None:
            raise FileNotFoundError(path)
        return SimpleNamespace(st_mode=mode.value)

    monkeypatch.setattr(Path, "lstat", lstat)
    monkeypatch.setattr(connection, "QProcess", _Probe)
    monkeypatch.setattr(connection, "QTimer", _Timer)
    parent = qt.QObject()
    yield connection.SharedSshConnection(str(socket), "/usr/bin/ssh", parent), mode


def test_shared_ssh_requires_successful_probe_and_clears_metadata_on_restart(lease) -> None:
    session, mode = lease
    events = []
    session.changed.connect(events.append)
    assert session.state.description() == "Shared SSH · Ready to connect"
    session.process_started()
    session._poll_socket()
    session.finish(None, "FailedToStart")
    assert not events

    session.start_attempt()
    session.process_started()
    check = session._check
    assert check.program == "/usr/bin/ssh"
    assert check.stdout == check.stderr == os.devnull
    assert check.arguments == ["-F", os.devnull, "-S", session.socket_path, "-O", "check", "localhost"]
    assert session.state.phase == "authenticating"
    assert check.starts == 0
    mode.value = stat.S_IFLNK
    session._poll_socket()
    assert check.starts == 0
    mode.value = stat.S_IFSOCK
    session._poll_socket()
    session._poll_socket()
    assert check.starts == 1
    assert session._timeout.active
    assert session.state.phase == "authenticating"
    check.complete()
    assert not session._timeout.active
    assert session.state.description() == "Shared SSH · Authenticated"
    session.begin_close("restart-requested")
    session.begin_close("tab-closed")
    session.finish(1, "NormalExit")
    session.finish(2, "NormalExit")
    assert session.state.properties() == {
        "phase": "closed", "attempt": 1, "disconnect_reason": "restart-requested",
        "exit_code": 1, "exit_status": "NormalExit",
    }
    session.start_attempt()
    assert session.state.properties() == {
        "phase": "connecting", "attempt": 2, "disconnect_reason": None,
        "exit_code": None, "exit_status": None,
    }
    assert [state.phase for state in events] == [
        "connecting", "authenticating", "connected", "closing", "closed", "connecting",
    ]


def test_shared_ssh_control_probe_loses_recovers_and_ignores_cancelled_completion(lease) -> None:
    session, mode = lease
    mode.value = stat.S_IFSOCK
    session.start_attempt()
    session.process_started()
    check = session._check
    check.complete(1)
    assert session.state.phase == "authenticating"
    session._poll_socket()
    check.complete(0, qt.QProcess.ExitStatus.CrashExit)
    assert session.state.phase == "authenticating"
    session._poll_socket()
    check.complete()
    session._poll_socket()
    session._check_timed_out()
    assert check.kills == 1
    assert session.state.phase == "connection-lost"
    assert session.state.disconnect_reason == "control-master-lost"
    check.complete()
    assert session.state.phase == "connection-lost"

    session._poll_socket()
    session._check_error(qt.QProcess.ProcessError.FailedToStart)
    session._check_error(qt.QProcess.ProcessError.FailedToStart)
    assert check.kills == 2
    session._poll_socket()
    check.complete()
    assert session.state.phase == "connected"
    mode.value = stat.S_IFREG
    session._poll_socket()
    assert session.state.phase == "connection-lost"
    session.finish(255, "NormalExit")
    assert session.state.disconnect_reason == "control-master-lost"


@pytest.mark.parametrize(
    ("code", "status", "reason"),
    [
        (None, "FailedToStart", "launch-failed"),
        (-9, "CrashExit", "process-crashed"),
        (255, "NormalExit", "ssh-error-or-disconnect"),
        (7, "NormalExit", "remote-command-exited"),
    ],
)
def test_shared_ssh_retains_terminal_exit_reason(lease, code, status, reason) -> None:
    session, _mode = lease
    session.start_attempt()
    session.finish(code, status)
    assert session.state.phase == "closed"
    assert session.state.disconnect_reason == reason
    assert session.state.exit_code == code
    assert session.state.exit_status == status

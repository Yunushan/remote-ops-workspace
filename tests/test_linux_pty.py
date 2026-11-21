from __future__ import annotations

import errno
import os
import struct
import subprocess
import sys
import threading
import time
from types import SimpleNamespace
from unittest.mock import Mock, call

import pytest

from remote_ops_workspace import linux_pty


@pytest.fixture
def kernel(monkeypatch):
    system = SimpleNamespace(
        environ={"PATH": "/usr/bin", "TERM": "dumb"},
        pathsep=":",
        get_exec_path=os.get_exec_path,
        strerror=os.strerror,
        openpty=Mock(return_value=(11, 12)),
        set_blocking=Mock(),
        close=Mock(),
        ttyname=Mock(return_value="/dev/pts/9"),
        posix_spawn=Mock(return_value=123),
        POSIX_SPAWN_OPEN=1,
        POSIX_SPAWN_DUP2=2,
        O_RDWR=2,
        WNOHANG=1,
        read=Mock(side_effect=BlockingIOError),
        write=Mock(side_effect=lambda _fd, data: len(data)),
        waitpid=Mock(return_value=(0, 0)),
        waitstatus_to_exitcode=Mock(side_effect=lambda status: status),
        killpg=Mock(),
        which=Mock(return_value="/usr/bin/ssh"),
        ioctl=Mock(),
    )
    monkeypatch.setattr(linux_pty, "os", system)
    monkeypatch.setattr(linux_pty, "shutil", SimpleNamespace(which=system.which))
    monkeypatch.setattr(linux_pty, "signal", SimpleNamespace(SIGPIPE=13, SIGTERM=15, SIGKILL=9))
    monkeypatch.setitem(sys.modules, "fcntl", SimpleNamespace(ioctl=system.ioctl))
    monkeypatch.setitem(sys.modules, "termios", SimpleNamespace(TIOCSWINSZ=404))
    return system


def test_linux_pty_launch_sets_the_controlling_terminal_and_initial_geometry(kernel) -> None:
    session = linux_pty.LinuxPtyProcess(["ssh", "test"], columns=113, rows=23)
    assert session.poll() is None
    assert session.read_all() == b""
    with pytest.raises(BrokenPipeError):
        session.write(b"early")
    session.resize(80, 24)
    session.start()

    kernel.which.assert_called_once_with("ssh", path="/usr/bin")
    kernel.set_blocking.assert_called_once_with(11, False)
    kernel.ioctl.assert_called_once_with(11, 404, struct.pack("HHHH", 23, 113, 0, 0))
    kernel.posix_spawn.assert_called_once_with(
        "/usr/bin/ssh", ("ssh", "test"), {"PATH": "/usr/bin", "TERM": "xterm-256color"},
        file_actions=[(1, 0, "/dev/pts/9", 2, 0), (2, 0, 1), (2, 0, 2)],
        setsid=True, setsigmask=(), setsigdef=(13,),
    )
    kernel.close.assert_called_once_with(12)
    session.resize(65, 12)
    kernel.ioctl.assert_called_with(11, 404, struct.pack("HHHH", 12, 65, 0, 0))
    assert session.take_resize_error() is None
    assert session.begin_output_shutdown() is None
    session.close(terminate=False)
    assert session.output_eof
    kernel.close.assert_called_with(11)


def test_linux_pty_spawn_failure_releases_both_fds_and_honors_explicit_path(kernel) -> None:
    session = linux_pty.LinuxPtyProcess(
        ["ssh"], columns=80, rows=24, env={"PATH": "/custom/bin", "TERM": "vt100"},
    )
    kernel.which.return_value = None
    with pytest.raises(FileNotFoundError, match="ssh"):
        session.start()
    kernel.openpty.assert_not_called()
    kernel.which.assert_called_once_with("ssh", path="/custom/bin")
    kernel.which.return_value = "/custom/bin/ssh"
    kernel.posix_spawn.side_effect = PermissionError("forbidden")
    with pytest.raises(PermissionError, match="forbidden"):
        session.start()
    assert kernel.posix_spawn.call_args.args[:3] == (
        "/custom/bin/ssh", ("ssh",), {"PATH": "/custom/bin", "TERM": "vt100"},
    )
    assert kernel.close.call_args_list == [call(11), call(12)]
    session.close()


def test_linux_pty_reading_handles_would_block_bounded_reads_and_peer_exit(kernel) -> None:
    session = linux_pty.LinuxPtyProcess(["ssh"], columns=80, rows=24, env={})
    session.start()
    kernel.read.side_effect = [b"abc", BlockingIOError(), b"x" * linux_pty._READ_BUDGET,
                               OSError(errno.EBADF, "broken descriptor"), OSError(errno.EIO, "closed slave")]
    assert session.read_all() == b"abc"
    assert not session.output_eof
    assert len(session.read_all()) == linux_pty._READ_BUDGET
    with pytest.raises(OSError, match="broken descriptor"):
        session.read_all()
    assert session.read_all() == b""
    assert session.output_eof
    assert session.read_all() == b""
    with pytest.raises(BrokenPipeError):
        session.write(b"after exit")
    session.close(terminate=False)


def test_linux_pty_short_writes_are_retried_without_losing_input(kernel) -> None:
    session = linux_pty.LinuxPtyProcess(["ssh"], columns=80, rows=24)
    session.start()
    seen = []

    def write(_fd, data):
        seen.append(bytes(data))
        if len(seen) == 1:
            return 2
        if len(seen) == 2:
            raise BlockingIOError
        return len(data)

    kernel.write.side_effect = write
    assert session.write(b"abcde") == 5
    with pytest.raises(BlockingIOError, match="queue is full"):
        session.write(b"x" * linux_pty._INPUT_LIMIT)
    assert session.poll() is None
    assert session.poll() is None
    session.close_input()
    session.close_input()
    assert seen == [b"abcde", b"cde", b"cde", b"\x04"]
    with pytest.raises(BrokenPipeError):
        session.write(b"after close")
    session.close(terminate=False)


def test_linux_pty_reports_deferred_write_error_and_reaps_each_child_once(kernel) -> None:
    session = linux_pty.LinuxPtyProcess(["ssh"], columns=80, rows=24)
    session.start()
    kernel.write.side_effect = [BlockingIOError(), OSError(errno.EIO, "write failed")]
    assert session.write(b"staged") == 6
    assert session.poll() is None
    assert isinstance(session.io_error, linux_pty.PtyWriteError)
    kernel.killpg.side_effect = [ProcessLookupError(), None]
    session.terminate()
    session.kill()
    assert kernel.killpg.call_args_list == [call(123, 15), call(123, 9)]
    kernel.waitpid.side_effect = [(0, 0), (123, -9)]
    assert session.wait(1) == -9
    assert session.poll() == -9
    session.kill()
    assert kernel.killpg.call_count == 2
    kernel.waitstatus_to_exitcode.assert_called_once_with(-9)
    session.close()


def test_linux_pty_close_reaps_after_timeout_without_leaking_master(kernel, monkeypatch) -> None:
    def finish_in_same_thread(*, target, args, **_kwargs):
        kernel.waitpid.return_value = (123, -9)
        return SimpleNamespace(start=lambda: target(*args))

    monkeypatch.setattr(
        linux_pty, "threading", SimpleNamespace(Event=threading.Event, Thread=finish_in_same_thread),
    )
    session = linux_pty.LinuxPtyProcess(["ssh"], columns=80, rows=24)
    session.start()
    with pytest.raises(subprocess.TimeoutExpired):
        session.wait(0)
    session.close(timeout=0)
    kernel.waitpid.assert_called_with(123, 0)
    assert session.poll() == -9
    assert kernel.close.call_args_list == [call(12), call(11)]
    session.close()
    assert kernel.close.call_count == 2


def test_qt_linux_pty_selection_output_resize_and_exit(kernel, monkeypatch) -> None:
    qt = pytest.importorskip("PyQt6.QtCore")
    from remote_ops_workspace import gui_processes
    from remote_ops_workspace.qt_terminal_process import QtLinuxPtyProcess
    from remote_ops_workspace.terminal import TerminalPanePlan

    app = qt.QCoreApplication.instance() or qt.QCoreApplication(["linux-pty-test"])
    monkeypatch.setattr(gui_processes, "sys", SimpleNamespace(platform="linux"))
    process, warning = gui_processes._terminal_process_backend(
        app, TerminalPanePlan("ssh", ["ssh", "test"], "test"), None,
    )
    assert isinstance(process, QtLinuxPtyProcess)
    assert warning == ""
    assert process.transport_backend == "linux-pty"
    assert process.property("terminalChildWindowPolicy") == "controlling-pty"
    assert process.property("terminalConsoleSuppressed") is False

    results = []
    process.finished.connect(lambda *result: results.append(result))
    process.setTerminalSize(113, 23)
    process.setProgram("ssh")
    process.setArguments(["test"])
    process.start()
    process._start_thread.join(3)
    assert not process.waitForFinished(35)
    assert process.state() == qt.QProcess.ProcessState.Running
    process.setTerminalSize(65, 12)
    assert kernel.ioctl.call_args == call(11, 404, struct.pack("HHHH", 12, 65, 0, 0))

    kernel.read.side_effect = [b"final bytes", OSError(errno.EIO, "closed slave")]
    kernel.waitpid.return_value = (123, -9)
    assert process.waitForFinished(-1)
    assert process.readAllStandardOutput() == b"final bytes"
    assert results == [(-9, qt.QProcess.ExitStatus.CrashExit)]
    kernel.read.side_effect = [b""]
    kernel.waitpid.return_value = (123, 0)
    process.start()
    process._start_thread.join(3)
    assert process.waitForFinished(-1)
    assert results[-1] == (0, qt.QProcess.ExitStatus.NormalExit)


def test_qt_pty_closes_child_when_cancelled_after_spawn_before_adoption(kernel, monkeypatch) -> None:
    qt = pytest.importorskip("PyQt6.QtCore")
    from remote_ops_workspace.qt_terminal_process import QtLinuxPtyProcess

    app = qt.QCoreApplication.instance() or qt.QCoreApplication(["linux-pty-cancel-test"])
    process = QtLinuxPtyProcess(app)
    close = Mock()
    monkeypatch.setattr(process, "_close_session_async", close)
    process.setProgram("ssh")
    process.start()
    process._start_thread.join(3)
    _, session, error = process._pending_start
    assert session.pid == 123
    assert error is None
    process.terminate()
    close.assert_called_once_with(session, terminate=True)
    assert process.state() == qt.QProcess.ProcessState.NotRunning
    assert process._pending_start is None


def test_qt_pty_deferred_linux_write_error_reports_write_failure(kernel) -> None:
    qt = pytest.importorskip("PyQt6.QtCore")
    from remote_ops_workspace.qt_terminal_process import QtLinuxPtyProcess

    app = qt.QCoreApplication.instance() or qt.QCoreApplication(["linux-pty-io-test"])
    process = QtLinuxPtyProcess(app)
    errors = []
    process.errorOccurred.connect(errors.append)
    process.setProgram("ssh")
    process.start()
    process._start_thread.join(3)
    assert not process.waitForFinished(0)
    process._session.io_error = linux_pty.PtyWriteError("blocked terminal write")
    kernel.waitpid.return_value = (123, 0)
    assert process.waitForFinished(500)
    assert errors == [qt.QProcess.ProcessError.WriteError]
    assert process.errorString() == "blocked terminal write"


@pytest.mark.skipif(sys.platform != "linux", reason="requires a native Linux PTY")
def test_linux_pty_child_observes_initial_dimensions_and_sigwinch() -> None:
    child = """
import os, signal, tty
events = []
signal.signal(signal.SIGWINCH, lambda *_: events.append(True))
with open('/dev/tty', 'rb', buffering=0) as terminal:
    assert os.isatty(terminal.fileno())
tty.setraw(0)
def report():
    columns, rows = os.get_terminal_size()
    print(f'SIZE {columns} {rows} {len(events)}', flush=True)
report()
assert os.read(0, 1) == b'x'
report()
"""
    session = linux_pty.LinuxPtyProcess([sys.executable, "-c", child], columns=113, rows=23)
    output = bytearray()

    def read_until(marker: bytes):
        deadline = time.monotonic() + 4
        while marker not in output and time.monotonic() < deadline:
            output.extend(session.read_all())
            session.poll()
            time.sleep(0.01)
        assert marker in output, output

    try:
        session.start()
        read_until(b"SIZE 113 23 0")
        session.resize(65, 12)
        session.write(b"x")
        read_until(b"SIZE 65 12 1")
        assert session.wait(3) == 0
    finally:
        session.close()

from __future__ import annotations

import subprocess
import sys
import threading
import time

import pytest

from remote_ops_workspace.windows_conpty import conpty_support

qt_core = pytest.importorskip("PyQt6.QtCore")
qt_terminal_process = pytest.importorskip("remote_ops_workspace.qt_terminal_process")
QtConPtyProcess = qt_terminal_process.QtConPtyProcess
_CONPTY_SUPPORT = conpty_support()
pytestmark = pytest.mark.skipif(
    not _CONPTY_SUPPORT.supported,
    reason=_CONPTY_SUPPORT.reason,
)


@pytest.fixture(scope="module")
def qt_app():
    existing = qt_core.QCoreApplication.instance()
    if existing is not None:
        return existing
    return qt_core.QCoreApplication(["remote-ops-workspace-conpty-tests"])


def _process_events_until(
    app,
    predicate,
    *,
    timeout: float = 5.0,
) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    app.processEvents()
    assert predicate(), "condition was not reached while processing Qt events"


class _LifecycleSession:
    def __init__(
        self,
        *,
        poll_result: int | None = None,
        poll_error: BaseException | None = None,
        output_eof: bool = False,
        shutdown_error: BaseException | None = None,
        eof_on_shutdown: bool = False,
        output: bytes = b"",
        resize_error: BaseException | None = None,
    ) -> None:
        self.pid = 4242
        self.io_error = None
        self.output_eof = output_eof
        self.output_ready = threading.Event()
        self.poll_result = poll_result
        self.poll_error = poll_error
        self.shutdown_error = shutdown_error
        self.eof_on_shutdown = eof_on_shutdown
        self.resize_error = resize_error
        self.started = False
        self.shutdown_calls = 0
        self.close_calls: list[tuple[bool, float]] = []
        self.kill_calls = 0
        self.writes: list[bytes] = []
        self.close_input_calls = 0
        self.output = bytearray(output)

    def start(self) -> None:
        self.started = True

    def read_all(self) -> bytes:
        payload = bytes(self.output)
        self.output.clear()
        return payload

    def take_resize_error(self):
        error = self.resize_error
        self.resize_error = None
        return error

    def poll(self) -> int | None:
        if self.poll_error is not None:
            raise self.poll_error
        return self.poll_result

    def begin_output_shutdown(self) -> None:
        self.shutdown_calls += 1
        if self.shutdown_error is not None:
            raise self.shutdown_error
        if self.eof_on_shutdown:
            self.output_eof = True

    def write(self, payload: bytes) -> int:
        self.writes.append(bytes(payload))
        return len(payload)

    def close_input(self) -> None:
        self.close_input_calls += 1

    def kill(self) -> None:
        self.kill_calls += 1

    def close(self, *, terminate: bool, timeout: float) -> None:
        self.close_calls.append((terminate, timeout))


def _arm_lifecycle_session(process, session: _LifecycleSession) -> None:
    process._poll_timer.stop()
    process._session = session
    process._state = qt_core.QProcess.ProcessState.Running
    process._pending_returncode = None
    process._output_shutdown_started = False
    process._output_shutdown_deadline = None
    process._forced_termination_deadline = None
    process._finished_emitted = False


def test_conpty_process_publishes_hidden_window_policy() -> None:
    process = QtConPtyProcess()

    assert process.property("terminalTransportStartupAsync") is True
    assert process.property("terminalConsoleSuppressed") is True
    assert process.property("terminalChildWindowPolicy") == "conpty-hidden"
    process.close()


def test_stalled_output_eof_transitions_once_and_forces_bounded_cleanup(qt_app) -> None:
    process = QtConPtyProcess()
    session = _LifecycleSession(poll_result=0)
    errors: list[object] = []
    finished: list[tuple[int, object]] = []
    process.errorOccurred.connect(errors.append)
    process.finished.connect(lambda code, status: finished.append((code, status)))
    _arm_lifecycle_session(process, session)

    process._poll_session()
    assert session.shutdown_calls == 1
    assert process._output_shutdown_deadline is not None
    process._output_shutdown_deadline = time.monotonic() - 1.0
    process._poll_session()
    process._poll_session()

    assert errors == [qt_core.QProcess.ProcessError.ReadError]
    assert finished == [(0, qt_core.QProcess.ExitStatus.CrashExit)]
    assert session.close_calls == [(False, 0.5)]
    assert process.state() == qt_core.QProcess.ProcessState.NotRunning
    assert process._session is None


def test_final_output_is_preserved_when_transport_is_paused(qt_app) -> None:
    process = QtConPtyProcess()
    session = _LifecycleSession(
        poll_result=0,
        output_eof=True,
        output=b"retained terminal tail\r\n",
    )
    finished: list[tuple[int, object]] = []
    process.finished.connect(lambda code, status: finished.append((code, status)))
    _arm_lifecycle_session(process, session)
    process.setOutputPaused(True)

    process._poll_session()

    assert process.readAllStandardOutput() == b"retained terminal tail\r\n"
    assert finished == [(0, qt_core.QProcess.ExitStatus.NormalExit)]
    assert session.close_calls == [(False, 0.5)]
    assert process.state() == qt_core.QProcess.ProcessState.NotRunning
    assert process._session is None


def test_shutdown_failure_completes_once_and_allows_a_fresh_start(
    qt_app,
    monkeypatch,
) -> None:
    process = QtConPtyProcess()
    failed = _LifecycleSession(
        poll_result=0,
        shutdown_error=RuntimeError("controlled shutdown failure"),
    )
    errors: list[object] = []
    finished: list[tuple[int, object]] = []
    process.errorOccurred.connect(errors.append)
    process.finished.connect(lambda code, status: finished.append((code, status)))
    _arm_lifecycle_session(process, failed)

    process._poll_session()

    assert errors == [qt_core.QProcess.ProcessError.UnknownError]
    assert finished == [(0, qt_core.QProcess.ExitStatus.CrashExit)]
    assert failed.close_calls == [(False, 0.5)]
    assert process.state() == qt_core.QProcess.ProcessState.NotRunning

    replacement = _LifecycleSession(poll_result=None)
    monkeypatch.setattr(
        qt_terminal_process,
        "WindowsConPtyProcess",
        lambda *_args, **_kwargs: replacement,
    )
    process.setProgram("cmd.exe")
    process.start()

    _process_events_until(qt_app, lambda: process._session is replacement)
    assert replacement.started is True
    assert process._session is replacement
    assert process.state() == qt_core.QProcess.ProcessState.Running
    process.close()


def test_conpty_startup_does_not_block_the_qt_caller(qt_app, monkeypatch) -> None:
    class SlowSession(_LifecycleSession):
        def start(self) -> None:
            time.sleep(0.2)
            super().start()

    session = SlowSession(poll_result=None)
    monkeypatch.setattr(
        qt_terminal_process,
        "WindowsConPtyProcess",
        lambda *_args, **_kwargs: session,
    )
    process = QtConPtyProcess()
    process.setProgram("cmd.exe")

    try:
        started_at = time.monotonic()
        process.start()
        elapsed = time.monotonic() - started_at

        assert elapsed < 0.1
        assert process.state() == qt_core.QProcess.ProcessState.Starting
        _process_events_until(qt_app, lambda: process._session is session)
        assert process.state() == qt_core.QProcess.ProcessState.Running
    finally:
        process.close()


def test_starting_process_flushes_early_input_and_close_request(
    qt_app,
    monkeypatch,
) -> None:
    class SlowSession(_LifecycleSession):
        def start(self) -> None:
            time.sleep(0.15)
            super().start()

    session = SlowSession(poll_result=None)
    monkeypatch.setattr(
        qt_terminal_process,
        "WindowsConPtyProcess",
        lambda *_args, **_kwargs: session,
    )
    process = QtConPtyProcess()
    process.setProgram("cmd.exe")
    payload = b"exit\r"

    try:
        process.start()
        assert process.state() == qt_core.QProcess.ProcessState.Starting
        assert process.write(payload) == len(payload)
        process.closeWriteChannel()

        _process_events_until(
            qt_app,
            lambda: (
                process._session is session
                and session.writes == [payload]
                and session.close_input_calls == 1
            ),
        )
        assert process.state() == qt_core.QProcess.ProcessState.Running
    finally:
        process.close()


def test_terminate_cancels_slow_conpty_start_without_adopting_session(
    qt_app,
    monkeypatch,
) -> None:
    class SlowSession(_LifecycleSession):
        def start(self) -> None:
            time.sleep(0.15)
            super().start()

    session = SlowSession(poll_result=None)
    monkeypatch.setattr(
        qt_terminal_process,
        "WindowsConPtyProcess",
        lambda *_args, **_kwargs: session,
    )
    process = QtConPtyProcess()
    finished: list[tuple[int, object]] = []
    process.finished.connect(
        lambda exit_code, exit_status: finished.append((exit_code, exit_status))
    )
    process.setProgram("cmd.exe")

    try:
        process.start()
        assert process.state() == qt_core.QProcess.ProcessState.Starting
        process.terminate()

        assert process.state() == qt_core.QProcess.ProcessState.NotRunning
        assert finished == [(-1, qt_core.QProcess.ExitStatus.CrashExit)]
        _process_events_until(qt_app, lambda: bool(session.close_calls))
        assert len(session.close_calls) == 1
        terminate, timeout = session.close_calls[0]
        assert terminate is True
        assert 0 < timeout <= 0.5
        assert process._session is None
    finally:
        process.close()


def test_abrupt_poll_failure_transitions_once_and_releases_session(qt_app) -> None:
    process = QtConPtyProcess()
    session = _LifecycleSession(poll_error=OSError("controlled abrupt poll failure"))
    errors: list[object] = []
    finished: list[tuple[int, object]] = []
    process.errorOccurred.connect(errors.append)
    process.finished.connect(lambda code, status: finished.append((code, status)))
    _arm_lifecycle_session(process, session)

    process._poll_session()
    process._poll_session()

    assert errors == [qt_core.QProcess.ProcessError.UnknownError]
    assert finished == [(-1, qt_core.QProcess.ExitStatus.CrashExit)]
    assert session.close_calls == [(True, 0.5)]
    assert process.state() == qt_core.QProcess.ProcessState.NotRunning
    assert process._session is None


def test_kill_has_a_bounded_fallback_when_exit_poll_stalls(qt_app) -> None:
    process = QtConPtyProcess()
    session = _LifecycleSession(poll_result=None)
    errors: list[object] = []
    finished: list[tuple[int, object]] = []
    process.errorOccurred.connect(errors.append)
    process.finished.connect(lambda code, status: finished.append((code, status)))
    _arm_lifecycle_session(process, session)

    process.kill()
    assert session.kill_calls == 1
    assert process._forced_termination_deadline is not None
    process._forced_termination_deadline = time.monotonic() - 1.0
    process._poll_session()

    assert process.state() == qt_core.QProcess.ProcessState.NotRunning
    assert process._session is None
    assert errors == [qt_core.QProcess.ProcessError.Crashed]
    assert finished == [(-1, qt_core.QProcess.ExitStatus.CrashExit)]
    assert session.close_calls == [(True, 0.5)]


def test_transient_resize_failure_does_not_fail_live_terminal(qt_app) -> None:
    process = QtConPtyProcess()
    session = _LifecycleSession(resize_error=RuntimeError("stale viewport"))
    errors: list[object] = []
    process.errorOccurred.connect(errors.append)
    _arm_lifecycle_session(process, session)

    process._poll_session()

    assert errors == []
    assert process.state() == qt_core.QProcess.ProcessState.Running
    assert process.property("terminalTransportResizeWarning") == "stale viewport"
    assert process.property("terminalTransportResizeWarningCount") == 1

    process._poll_session()
    assert process.property("terminalTransportResizeWarningCount") == 1
    process.close()


def test_real_cmd_round_trips_output_and_input_through_qt_events(
    qt_app,
) -> None:
    process = QtConPtyProcess()
    output = bytearray()
    started: list[bool] = []
    finished: list[tuple[int, object]] = []
    errors: list[object] = []
    process.readyReadStandardOutput.connect(
        lambda: output.extend(process.readAllStandardOutput())
    )
    process.started.connect(lambda: started.append(True))
    process.finished.connect(
        lambda exit_code, exit_status: finished.append((exit_code, exit_status))
    )
    process.errorOccurred.connect(errors.append)
    process.setProgram("cmd.exe")
    process.setArguments(
        [
            "/d",
            "/q",
            "/v:on",
            "/c",
            "echo QT-READY&set /p line=&echo QT-GOT=!line!",
        ]
    )

    try:
        process.start()
        _process_events_until(qt_app, lambda: b"QT-READY" in output)

        assert started == [True]
        assert process.state() == qt_core.QProcess.ProcessState.Running
        assert process.processId() > 0
        assert process.write(b"qt-terminal-input\r") == len(b"qt-terminal-input\r")
        session = process._session
        assert session is not None
        session.flush(timeout=2.0)

        _process_events_until(
            qt_app,
            lambda: b"QT-GOT=qt-terminal-input" in output,
            timeout=10.0,
        )
        _process_events_until(qt_app, lambda: bool(finished))

        assert errors == []
        assert finished == [(0, qt_core.QProcess.ExitStatus.NormalExit)]
        assert process.state() == qt_core.QProcess.ProcessState.NotRunning
    finally:
        process.close()


def test_missing_executable_emits_failed_to_start_with_useful_detail(
    qt_app,
) -> None:
    process = QtConPtyProcess()
    missing_program = "remote-ops-workspace-conpty-missing-command.exe"
    errors: list[object] = []
    process.errorOccurred.connect(errors.append)
    process.setProgram(missing_program)

    try:
        process.start()
        _process_events_until(qt_app, lambda: bool(errors))

        assert errors == [qt_core.QProcess.ProcessError.FailedToStart]
        assert process.state() == qt_core.QProcess.ProcessState.NotRunning
        assert process.processId() == 0
        assert missing_program in process.errorString()
        assert "not found" in process.errorString().lower()
    finally:
        process.close()


def test_start_is_idempotent_and_live_terminal_resize_reaches_conpty(
    qt_app,
) -> None:
    process = QtConPtyProcess()
    output = bytearray()
    started: list[bool] = []
    finished: list[tuple[int, object]] = []
    process.readyReadStandardOutput.connect(
        lambda: output.extend(process.readAllStandardOutput())
    )
    process.started.connect(lambda: started.append(True))
    process.finished.connect(
        lambda exit_code, exit_status: finished.append((exit_code, exit_status))
    )
    process.setTerminalSize(88, 24)
    process.setProgram("cmd.exe")
    process.setArguments(["/d", "/q", "/c", "echo RESIZE-READY&pause >nul"])

    try:
        process.start()
        _process_events_until(qt_app, lambda: b"RESIZE-READY" in output)
        session = process._session
        assert session is not None
        assert (session.columns, session.rows) == (88, 24)
        original_pid = process.processId()

        process.start()
        qt_app.processEvents()
        assert started == [True]
        assert process.processId() == original_pid

        process.setTerminalSize(132, 43)
        assert (session.columns, session.rows) == (132, 43)

        process.terminate()
        _process_events_until(qt_app, lambda: bool(finished))
        assert finished[0][0] != 0
        assert finished[0][1] == qt_core.QProcess.ExitStatus.CrashExit
        assert process.state() == qt_core.QProcess.ProcessState.NotRunning
    finally:
        process.close()


def test_fast_exit_drains_high_volume_tail_before_finished(
    qt_app,
) -> None:
    process = QtConPtyProcess()
    output = bytearray()
    payload_size = 512 * 1024
    tail_marker = b"QT-FAST-EXIT-TAIL-MARKER"
    finished: list[tuple[int, object, int, bool]] = []
    process.readyReadStandardOutput.connect(
        lambda: output.extend(process.readAllStandardOutput())
    )
    process.finished.connect(
        lambda exit_code, exit_status: finished.append(
            (exit_code, exit_status, len(output), tail_marker in output)
        )
    )
    process.setProgram(sys.executable)
    process.setArguments(
        [
            "-c",
            (
                "import sys;"
                f"sys.stdout.buffer.write(b'Q'*{payload_size}"
                f"+{tail_marker!r}+b'\\n');"
                "sys.stdout.buffer.flush()"
            ),
        ]
    )

    try:
        process.start()
        assert process.waitForFinished(15000)
        qt_app.processEvents()

        assert finished == [
            (0, qt_core.QProcess.ExitStatus.NormalExit, len(output), True)
        ]
        assert output.count(b"Q") >= payload_size
        assert tail_marker in output
        assert process.state() == qt_core.QProcess.ProcessState.NotRunning
        assert process._session is None

        # Stale timer callbacks or explicit polls must not report completion
        # for the same process generation a second time.
        process._poll_session()
        process._poll_session()
        qt_app.processEvents()
        assert len(finished) == 1
    finally:
        process.close()


def test_normal_nonzero_exit_is_not_reported_as_crash(
    qt_app,
) -> None:
    process = QtConPtyProcess()
    output = bytearray()
    finished: list[tuple[int, object]] = []
    process.readyReadStandardOutput.connect(
        lambda: output.extend(process.readAllStandardOutput())
    )
    process.finished.connect(
        lambda exit_code, exit_status: finished.append((exit_code, exit_status))
    )
    process.setProgram("cmd.exe")
    process.setArguments(
        ["/d", "/q", "/c", "echo QT-NONZERO-NORMAL&exit /b 7"]
    )

    try:
        process.start()
        _process_events_until(qt_app, lambda: bool(finished))

        assert b"QT-NONZERO-NORMAL" in output
        assert finished == [(7, qt_core.QProcess.ExitStatus.NormalExit)]
        assert process.state() == qt_core.QProcess.ProcessState.NotRunning
    finally:
        process.close()


def test_conpty_accessors_empty_io_and_start_rejections() -> None:
    assert qt_terminal_process._take_buffer_prefix(bytearray(b"abc"), 2) == b"ab"
    process = QtConPtyProcess()
    process.setProgram("cmd.exe")
    process.setArguments(["/c", "exit"])
    assert process.program() == "cmd.exe"
    assert process.arguments() == ["/c", "exit"]
    assert process.readAllStandardError() == b""
    assert process.readStandardError(10) == b""
    assert process.write(b"") == 0

    process._state = qt_core.QProcess.ProcessState.Starting
    process.start()
    assert process.state() == qt_core.QProcess.ProcessState.Starting
    process._state = qt_core.QProcess.ProcessState.NotRunning
    process._program = ""
    process.start()
    assert "empty terminal program" in process.errorString()
    process._disposed = True
    process._program = "cmd.exe"
    process.start()
    assert "disposed" in process.errorString()
    process.close()


def test_conpty_start_worker_and_startup_failure_edges(monkeypatch) -> None:
    process = QtConPtyProcess()
    process._generation = 1
    process._state = qt_core.QProcess.ProcessState.Starting

    class BrokenSession(_LifecycleSession):
        def start(self) -> None:
            raise RuntimeError("start failed")

        def close(self, *, terminate: bool, timeout: float) -> None:
            raise RuntimeError("close failed")

    monkeypatch.setattr(
        qt_terminal_process,
        "WindowsConPtyProcess",
        lambda *_args, **_kwargs: BrokenSession(),
    )
    process._start_session_worker(1, ("cmd.exe",), 80, 24)
    process._poll_startup()
    assert "start failed" in process.errorString()

    class SuccessfulSession(_LifecycleSession):
        closed = threading.Event()

        def close(self, *, terminate: bool, timeout: float) -> None:
            self.closed.set()
            raise OSError("ignored close failure")

    stale = SuccessfulSession()
    process._generation = 3
    process._disposed = False
    monkeypatch.setattr(
        qt_terminal_process,
        "WindowsConPtyProcess",
        lambda *_args, **_kwargs: stale,
    )
    process._start_session_worker(2, ("cmd.exe",), 80, 24)
    assert stale.closed.wait(1.0)


def test_conpty_poll_startup_stale_write_and_resize_failures() -> None:
    process = QtConPtyProcess()
    stale = _LifecycleSession()
    stale_closed = threading.Event()

    def close_stale(*, terminate: bool, timeout: float) -> None:
        stale_closed.set()

    stale.close = close_stale  # type: ignore[method-assign]
    process._generation = 2
    process._state = qt_core.QProcess.ProcessState.Starting
    process._pending_start = (1, stale, None)
    process._poll_startup()
    assert stale_closed.wait(1.0)

    process._generation = 3
    process._state = qt_core.QProcess.ProcessState.Starting
    process._pending_start = (2, None, None)
    process._poll_startup()

    class BrokenAdoption(_LifecycleSession):
        def write(self, payload: bytes) -> int:
            raise BrokenPipeError("early input failed")

    broken = BrokenAdoption()
    process._generation = 3
    process._disposed = False
    process._state = qt_core.QProcess.ProcessState.Starting
    process._finished_emitted = False
    process._pending_start_input.extend(b"early")
    process._pending_start = (3, broken, None)
    process._poll_startup()
    assert process.state() == qt_core.QProcess.ProcessState.NotRunning
    assert "early input failed" in process.errorString()

    class ResizeWarning(_LifecycleSession):
        def resize(self, columns: int, rows: int) -> None:
            raise ValueError("resize failed")

    warning = ResizeWarning()
    process._generation = 4
    process._disposed = False
    process._state = qt_core.QProcess.ProcessState.Starting
    process._finished_emitted = False
    process._pending_start = (4, warning, None)
    process._poll_startup()
    assert process.property("terminalTransportResizeWarning") == "resize failed"
    process.close()


def test_conpty_poll_read_and_io_errors_transition_once() -> None:
    class ReadFailure(_LifecycleSession):
        def read_all(self) -> bytes:
            raise OSError("read failed")

    process = QtConPtyProcess()
    session = ReadFailure()
    _arm_lifecycle_session(process, session)
    process._poll_session()
    assert process.state() == qt_core.QProcess.ProcessState.NotRunning
    assert "read failed" in process.errorString()

    class IoFailure:
        operation = "WriteFile"

        def __str__(self) -> str:
            return "write transport failed"

    process = QtConPtyProcess()
    session = _LifecycleSession()
    session.io_error = IoFailure()
    errors: list[object] = []
    process.errorOccurred.connect(errors.append)
    _arm_lifecycle_session(process, session)
    process._poll_session()
    assert errors == [qt_core.QProcess.ProcessError.WriteError]
    process._poll_session()
    assert len(errors) == 1


def test_conpty_finish_and_failure_guards_ignore_stale_sessions() -> None:
    process = QtConPtyProcess()
    active = _LifecycleSession(poll_result=0, output_eof=True)
    stale = _LifecycleSession(poll_result=0, output_eof=True)
    _arm_lifecycle_session(process, active)
    process._finish_session(stale)
    process._fail_session(
        stale,
        "ignored",
        qt_core.QProcess.ProcessError.Crashed,
        terminate=True,
    )
    assert process.state() == qt_core.QProcess.ProcessState.Running

    process._pending_returncode = None
    process._finish_session(active)
    assert process.state() == qt_core.QProcess.ProcessState.Running
    process._finished_emitted = True
    process._finish_session(active)
    process.close()


def test_conpty_write_close_resize_and_warning_edges() -> None:
    process = QtConPtyProcess()
    process._state = qt_core.QProcess.ProcessState.Starting
    process._pending_start_input.extend(
        b"x" * qt_terminal_process._HIDDEN_INPUT_HIGH_WATER_BYTES
    )
    assert process.write(b"x") == -1
    assert "queue is full" in process.errorString()
    process.closeWriteChannel()
    assert process._pending_start_close_write is True

    process._state = qt_core.QProcess.ProcessState.NotRunning
    assert process.write(b"x") == -1
    process.closeWriteChannel()
    process.setTerminalSize(0, 99999)
    assert (process._columns, process._rows) == (1, 32767)

    class WriteResizeFailure(_LifecycleSession):
        def write(self, payload: bytes) -> int:
            raise RuntimeError("write failed")

        def resize(self, columns: int, rows: int) -> None:
            raise OSError("resize failed")

    session = WriteResizeFailure()
    _arm_lifecycle_session(process, session)
    errors: list[object] = []
    process.errorOccurred.connect(errors.append)
    assert process.write(b"x") == -1
    assert errors == [qt_core.QProcess.ProcessError.WriteError]
    process.closeWriteChannel()
    assert session.close_input_calls == 1
    process.setTerminalSize(80, 24)
    assert process.property("terminalTransportResizeWarning") == "resize failed"
    process._publish_resize_warning(" ")
    assert process.property("terminalTransportResizeWarning") == "terminal viewport resize failed"
    process.close()


def test_conpty_terminate_kill_and_wait_edges(monkeypatch) -> None:
    class ControlSession(_LifecycleSession):
        def __init__(self, *, poll_result=None, wait_result=0, wait_error=None) -> None:
            super().__init__(poll_result=poll_result)
            self.terminate_calls = 0
            self.wait_result = wait_result
            self.wait_error = wait_error

        def terminate(self) -> None:
            self.terminate_calls += 1

        def wait(self, timeout):
            if self.wait_error is not None:
                raise self.wait_error
            return self.wait_result

    process = QtConPtyProcess()
    process.terminate()
    process.kill()

    running = ControlSession(poll_result=None)
    _arm_lifecycle_session(process, running)
    process.terminate()
    assert running.terminate_calls == 1

    exited = ControlSession(poll_result=7)
    _arm_lifecycle_session(process, exited)
    process.terminate()
    assert process._pending_returncode == 7

    failing = ControlSession(poll_result=None)
    failing.poll_error = OSError("poll failed")
    _arm_lifecycle_session(process, failing)
    process.kill()
    assert process.state() == qt_core.QProcess.ProcessState.NotRunning

    failing_terminate = ControlSession(poll_result=None)
    failing_terminate.poll_error = RuntimeError("terminate poll failed")
    _arm_lifecycle_session(process, failing_terminate)
    process.terminate()
    assert process.state() == qt_core.QProcess.ProcessState.NotRunning

    process = QtConPtyProcess()
    process._state = qt_core.QProcess.ProcessState.Starting
    finished: list[tuple[int, object]] = []
    process.finished.connect(lambda code, status: finished.append((code, status)))
    process.kill()
    assert finished == [(-1, qt_core.QProcess.ExitStatus.CrashExit)]

    exited_on_kill = ControlSession(poll_result=4)
    exited_on_kill.output_eof = True
    _arm_lifecycle_session(process, exited_on_kill)
    process.kill()
    assert process.state() == qt_core.QProcess.ProcessState.NotRunning

    process = QtConPtyProcess()
    process._state = qt_core.QProcess.ProcessState.Starting
    assert process.waitForFinished(0) is False
    process._state = qt_core.QProcess.ProcessState.NotRunning
    assert process.waitForFinished(0) is True

    timeout_session = ControlSession(
        wait_error=subprocess.TimeoutExpired(["cmd"], 0.01)
    )
    _arm_lifecycle_session(process, timeout_session)
    assert process.waitForFinished(10) is False

    error_session = ControlSession(wait_error=OSError("wait failed"))
    _arm_lifecycle_session(process, error_session)
    assert process.waitForFinished(10) is True
    assert process.state() == qt_core.QProcess.ProcessState.NotRunning

    drain_session = ControlSession(wait_result=0)
    _arm_lifecycle_session(process, drain_session)
    monkeypatch.setattr(
        qt_terminal_process,
        "_OUTPUT_EOF_DRAIN_TIMEOUT_SECONDS",
        0.0,
    )
    assert process.waitForFinished(100) is True
    assert process.state() == qt_core.QProcess.ProcessState.NotRunning

    shutdown_error = ControlSession(wait_result=0)
    shutdown_error.shutdown_error = RuntimeError("shutdown failed")
    _arm_lifecycle_session(process, shutdown_error)
    assert process.waitForFinished(100) is True
    assert "shutdown failed" in process.errorString()


def test_conpty_wait_final_output_deadline_variants(monkeypatch) -> None:
    class SlowWaitSession(_LifecycleSession):
        def wait(self, _timeout):
            time.sleep(0.01)
            return 0

    process = QtConPtyProcess()
    slow = SlowWaitSession()
    _arm_lifecycle_session(process, slow)
    assert process.waitForFinished(1) is False
    process.close()

    class EofOnWait:
        def __init__(self, session: _LifecycleSession) -> None:
            self.session = session

        def wait(self, _timeout: float) -> bool:
            self.session.output_eof = True
            return True

        def clear(self) -> None:
            return None

    class ImmediateWaitSession(_LifecycleSession):
        def wait(self, _timeout):
            return 0

    process = QtConPtyProcess()
    no_drain_deadline = ImmediateWaitSession()
    no_drain_deadline.output_ready = EofOnWait(no_drain_deadline)
    _arm_lifecycle_session(process, no_drain_deadline)
    monkeypatch.setattr(process, "_begin_output_shutdown", lambda _session: True)
    assert process.waitForFinished(100) is True

    process = QtConPtyProcess()
    unbounded = ImmediateWaitSession()
    unbounded.output_ready = EofOnWait(unbounded)
    _arm_lifecycle_session(process, unbounded)
    assert process.waitForFinished(-1) is True


def test_conpty_async_close_ignores_transport_errors() -> None:
    process = QtConPtyProcess()
    closed = threading.Event()

    class BrokenClose(_LifecycleSession):
        def close(self, *, terminate: bool, timeout: float) -> None:
            closed.set()
            raise OSError("ignored")

    process._close_session_async(BrokenClose(), terminate=True)
    assert closed.wait(1.0)
    process._dispose_session(terminate=True)
    process.deleteLater()

from __future__ import annotations

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

    def close(self, *, terminate: bool, timeout: float) -> None:
        self.close_calls.append((terminate, timeout))


def _arm_lifecycle_session(process, session: _LifecycleSession) -> None:
    process._poll_timer.stop()
    process._session = session
    process._state = qt_core.QProcess.ProcessState.Running
    process._pending_returncode = None
    process._output_shutdown_started = False
    process._output_shutdown_deadline = None
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

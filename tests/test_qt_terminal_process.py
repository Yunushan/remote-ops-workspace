from __future__ import annotations

import sys
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
        qt_app.processEvents()

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

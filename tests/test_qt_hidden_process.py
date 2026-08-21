from __future__ import annotations

import os
import sys
import threading
import time

import pytest

qt_core = pytest.importorskip("PyQt6.QtCore")
qt_terminal_process = pytest.importorskip("remote_ops_workspace.qt_terminal_process")
QtHiddenProcess = qt_terminal_process.QtHiddenProcess
hidden_process_creation_flags = qt_terminal_process.hidden_process_creation_flags


@pytest.fixture(scope="module")
def qt_app():
    existing = qt_core.QCoreApplication.instance()
    if existing is not None:
        return existing
    return qt_core.QCoreApplication(["remote-ops-workspace-hidden-process-tests"])


def _process_events_until(app, predicate, *, timeout: float = 5.0) -> None:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        app.processEvents()
        if predicate():
            return
        time.sleep(0.01)
    app.processEvents()
    assert predicate(), "condition was not reached while processing Qt events"


def test_hidden_process_creation_flags_are_windows_only() -> None:
    assert hidden_process_creation_flags("win32") & 0x08000000
    assert hidden_process_creation_flags("windows") & 0x08000000
    assert hidden_process_creation_flags("posix") == 0


def test_hidden_process_round_trips_input_without_blocking_qt(qt_app) -> None:
    process = QtHiddenProcess()
    output = bytearray()
    finished: list[tuple[int, object]] = []
    errors: list[object] = []
    process.readyReadStandardOutput.connect(lambda: output.extend(process.readAllStandardOutput()))
    process.finished.connect(lambda exit_code, status: finished.append((exit_code, status)))
    process.errorOccurred.connect(errors.append)
    process.setProcessChannelMode(qt_core.QProcess.ProcessChannelMode.MergedChannels)
    process.setProgram(sys.executable)
    process.setArguments(
        [
            "-u",
            "-c",
            (
                "import sys; print('READY', flush=True); "
                "line=sys.stdin.buffer.readline(); "
                "print('GOT:'+line.decode().strip(), flush=True)"
            ),
        ]
    )

    try:
        process.start()
        _process_events_until(qt_app, lambda: b"READY" in output)
        assert process.write(b"background-input\n") == len(b"background-input\n")
        process.closeWriteChannel()
        _process_events_until(qt_app, lambda: bool(finished))

        assert b"GOT:background-input" in output
        assert errors == []
        assert finished == [(0, qt_core.QProcess.ExitStatus.NormalExit)]
        assert process.state() == qt_core.QProcess.ProcessState.NotRunning
        assert process.property("backgroundConsoleSuppressed") is (os.name == "nt")
    finally:
        process.close()


def test_hidden_process_missing_program_reports_failed_start(qt_app) -> None:
    process = QtHiddenProcess()
    errors: list[object] = []
    process.errorOccurred.connect(errors.append)
    process.setProgram("remote-ops-workspace-missing-background-command")

    try:
        process.start()
        qt_app.processEvents()

        assert errors == [qt_core.QProcess.ProcessError.FailedToStart]
        assert process.state() == qt_core.QProcess.ProcessState.NotRunning
        assert process.errorString()
    finally:
        process.close()


def test_hidden_process_threads_tolerate_deleted_qt_owner(qt_app) -> None:
    from PyQt6 import sip

    process = QtHiddenProcess()
    process.setProgram(sys.executable)
    process.setArguments(
        ["-u", "-c", "import time; time.sleep(0.05); print('late output', flush=True)"]
    )
    thread_errors: list[threading.ExceptHookArgs] = []
    original_hook = threading.excepthook
    threading.excepthook = thread_errors.append

    try:
        process.start()
        assert process.state() == qt_core.QProcess.ProcessState.Running
        sip.delete(process)
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and not thread_errors:
            qt_app.processEvents()
            time.sleep(0.01)
        assert thread_errors == []
    finally:
        threading.excepthook = original_hook

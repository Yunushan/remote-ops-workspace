from __future__ import annotations

import os
import sys
import threading
import time

import pytest

qt_core = pytest.importorskip("PyQt6.QtCore")
qt_terminal_process = pytest.importorskip("remote_ops_workspace.qt_terminal_process")
process_launch = pytest.importorskip("remote_ops_workspace.process_launch")
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
    assert hidden_process_creation_flags("win32") == process_launch.hidden_process_options(
        "win32"
    )["creationflags"]


def test_hidden_process_round_trips_input_without_blocking_qt(qt_app) -> None:
    process = QtHiddenProcess()
    output = bytearray()
    finished: list[tuple[int, object]] = []
    errors: list[object] = []
    owner_thread = threading.get_ident()
    callback_threads: list[int] = []

    def collect_output() -> None:
        callback_threads.append(threading.get_ident())
        output.extend(process.readAllStandardOutput())

    def collect_finished(exit_code: int, status: object) -> None:
        callback_threads.append(threading.get_ident())
        finished.append((exit_code, status))

    process.readyReadStandardOutput.connect(collect_output)
    process.finished.connect(collect_finished)
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
        assert callback_threads
        assert set(callback_threads) == {owner_thread}
        assert process.state() == qt_core.QProcess.ProcessState.NotRunning
        assert process.property("backgroundConsoleSuppressed") is (os.name == "nt")
        assert process.property("terminalConsoleSuppressed") is (os.name == "nt")
        assert process.property("terminalChildWindowPolicy") == (
            "create-no-window" if os.name == "nt" else "pipe"
        )
    finally:
        process.close()


def test_hidden_process_start_is_async_and_queues_input(qt_app, monkeypatch) -> None:
    """A slow helper launch must not block the Qt event loop or lose input."""

    original_popen = qt_terminal_process.subprocess.Popen
    entered = threading.Event()
    release = threading.Event()

    def delayed_popen(*args, **kwargs):
        entered.set()
        assert release.wait(2.0)
        return original_popen(*args, **kwargs)

    monkeypatch.setattr(qt_terminal_process.subprocess, "Popen", delayed_popen)
    process = QtHiddenProcess()
    output = bytearray()
    finished: list[tuple[int, object]] = []
    process.readyReadStandardOutput.connect(
        lambda: output.extend(process.readAllStandardOutput())
    )
    process.finished.connect(
        lambda exit_code, exit_status: finished.append((exit_code, exit_status))
    )
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
        started_at = time.monotonic()
        process.start()
        assert time.monotonic() - started_at < 0.25
        assert process.state() == qt_core.QProcess.ProcessState.Starting
        assert process.property("terminalTransportStartupAsync") is True
        assert entered.wait(1.0)
        payload = b"queued-before-start\n"
        assert process.write(payload) == len(payload)
        process.closeWriteChannel()
        release.set()
        _process_events_until(qt_app, lambda: bool(finished), timeout=5.0)

        assert b"GOT:queued-before-start" in output
        assert finished == [(0, qt_core.QProcess.ExitStatus.NormalExit)]
    finally:
        release.set()
        process.close()


def test_hidden_process_write_returns_while_child_stops_reading(qt_app) -> None:
    """A blocked child pipe must not block the GUI thread's input handler."""

    process = QtHiddenProcess()
    process.setProgram(sys.executable)
    process.setArguments(["-u", "-c", "import time; time.sleep(2)"])

    try:
        process.start()
        payload = b"x" * (256 * 1024)
        started = time.monotonic()
        accepted = process.write(payload)
        elapsed = time.monotonic() - started

        assert accepted == len(payload)
        assert elapsed < 0.25
        assert process.property("terminalTransportInputQueuedBytes") == len(payload)
    finally:
        process.close()


def test_hidden_process_kill_releases_paused_reader_and_finishes(qt_app) -> None:
    """Stopping a flood must not wait forever behind the output high-water mark."""

    process = QtHiddenProcess()
    finished: list[tuple[int, object]] = []
    process.finished.connect(
        lambda exit_code, exit_status: finished.append((exit_code, exit_status))
    )
    process.setProcessChannelMode(qt_core.QProcess.ProcessChannelMode.MergedChannels)
    process.setProgram(sys.executable)
    process.setArguments(
        [
            "-u",
            "-c",
            (
                "import sys, time; "
                "sys.stdout.buffer.write(b'x' * (5 * 1024 * 1024)); "
                "sys.stdout.flush(); time.sleep(5)"
            ),
        ]
    )

    try:
        process.start()
        _process_events_until(
            qt_app,
            lambda: process.state() == qt_core.QProcess.ProcessState.Running,
        )
        process.setOutputPaused(True)
        # The pause is checked between bounded reads, so one read-sized chunk
        # is enough to reproduce a reader waiting behind backpressure.
        high_water = qt_terminal_process._OUTPUT_READ_CHUNK_BYTES
        deadline = time.monotonic() + 5.0
        while time.monotonic() < deadline:
            with process._buffer_lock:
                buffered = len(process._stdout)
            if buffered >= high_water:
                break
            qt_app.processEvents()
            time.sleep(0.01)
        assert buffered >= high_water

        process.kill()
        _process_events_until(qt_app, lambda: bool(finished), timeout=3.0)

        assert len(finished) == 1
        assert finished[0][0] != 0
        assert finished[0][1] == qt_core.QProcess.ExitStatus.CrashExit
        assert process.state() == qt_core.QProcess.ProcessState.NotRunning
    finally:
        process.close()


def test_hidden_process_finish_does_not_wait_for_inherited_pipe_handle(
    qt_app,
    tmp_path,
) -> None:
    """A helper child must not freeze tab teardown while a grandchild owns a pipe."""

    marker = tmp_path / "inherited-pipe-child.pid"
    process = QtHiddenProcess()
    finished: list[tuple[int, object]] = []
    process.finished.connect(
        lambda exit_code, exit_status: finished.append((exit_code, exit_status))
    )
    process.setProcessChannelMode(qt_core.QProcess.ProcessChannelMode.MergedChannels)
    process.setProgram(sys.executable)
    process.setArguments(
        [
            "-u",
            "-c",
            (
                "import pathlib, subprocess, sys; "
                "child = subprocess.Popen([sys.executable, '-c', "
                "'import time; time.sleep(5)'], "
                "stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr); "
                f"pathlib.Path({str(marker)!r}).write_text(str(child.pid))"
            ),
        ]
    )

    orphan_pid: int | None = None
    try:
        process.start()
        deadline = time.monotonic() + 2.0
        marker_value = ""
        while time.monotonic() < deadline and not marker_value:
            qt_app.processEvents()
            try:
                marker_value = marker.read_text(encoding="utf-8").strip()
            except FileNotFoundError:
                marker_value = ""
            time.sleep(0.01)
        assert marker_value
        orphan_pid = int(marker_value)

        started = time.monotonic()
        _process_events_until(qt_app, lambda: bool(finished), timeout=2.0)
        assert time.monotonic() - started < 1.0
        assert finished == [(0, qt_core.QProcess.ExitStatus.NormalExit)]
    finally:
        process.close()
        if orphan_pid:
            try:
                os.kill(orphan_pid, 15)
            except (OSError, ProcessLookupError):
                pass


def test_hidden_process_old_generation_cannot_finish_a_restarted_run(
    qt_app,
    monkeypatch,
) -> None:
    """A stale waiter must not wake ``waitForFinished`` for a replacement run."""

    class _ExitedProcess:
        stdin = None

        def wait(self) -> int:
            return 0

    process = QtHiddenProcess()
    old_generation = 7
    old_event = threading.Event()
    replacement_event = threading.Event()
    process._generation = old_generation
    process._state = qt_core.QProcess.ProcessState.Running
    process._finished_event = old_event

    def queue_notification(kind: str, generation: int, *arguments) -> None:
        if kind != "finished":
            return
        # Model a finished callback that immediately starts a replacement
        # process and installs its own completion event.
        process._generation = generation + 1
        process._finished_event = replacement_event

    monkeypatch.setattr(process, "_queue_notification", queue_notification)

    process._wait_for_process(_ExitedProcess(), old_generation, [], old_event)

    assert old_event.is_set()
    assert replacement_event.is_set() is False
    process.close()


def test_hidden_process_missing_program_reports_failed_start(qt_app) -> None:
    process = QtHiddenProcess()
    errors: list[object] = []
    process.errorOccurred.connect(errors.append)
    process.setProgram("remote-ops-workspace-missing-background-command")

    try:
        process.start()
        _process_events_until(qt_app, lambda: bool(errors))

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
        _process_events_until(
            qt_app,
            lambda: process.state() == qt_core.QProcess.ProcessState.Running,
        )
        sip.delete(process)
        deadline = time.monotonic() + 1.0
        while time.monotonic() < deadline and not thread_errors:
            qt_app.processEvents()
            time.sleep(0.01)
        assert thread_errors == []
    finally:
        threading.excepthook = original_hook

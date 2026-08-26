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


class _FakeStream:
    def __init__(
        self,
        *,
        reads: tuple[bytes | BaseException, ...] = (),
        write_error: BaseException | None = None,
        flush_error: BaseException | None = None,
        close_error: BaseException | None = None,
    ) -> None:
        self.reads = list(reads)
        self.write_error = write_error
        self.flush_error = flush_error
        self.close_error = close_error
        self.writes: list[bytes] = []
        self.closed = threading.Event()

    def read(self, _size: int) -> bytes:
        item = self.reads.pop(0) if self.reads else b""
        if isinstance(item, BaseException):
            raise item
        return item

    def write(self, payload: bytes) -> int:
        if self.write_error is not None:
            raise self.write_error
        self.writes.append(bytes(payload))
        return len(payload)

    def flush(self) -> None:
        if self.flush_error is not None:
            raise self.flush_error

    def close(self) -> None:
        self.closed.set()
        if self.close_error is not None:
            raise self.close_error


class _FakeProcess:
    def __init__(
        self,
        *,
        stdin: _FakeStream | None = None,
        stdout: _FakeStream | None = None,
        stderr: _FakeStream | None = None,
        poll_result: int | None = None,
        poll_error: BaseException | None = None,
        wait_result: int = 0,
        wait_error: BaseException | None = None,
        terminate_error: BaseException | None = None,
        kill_error: BaseException | None = None,
    ) -> None:
        self.stdin = stdin
        self.stdout = stdout
        self.stderr = stderr
        self.pid = 31337
        self.poll_result = poll_result
        self.poll_error = poll_error
        self.wait_result = wait_result
        self.wait_error = wait_error
        self.terminate_error = terminate_error
        self.kill_error = kill_error
        self.terminate_calls = 0
        self.kill_calls = 0

    def poll(self) -> int | None:
        if self.poll_error is not None:
            raise self.poll_error
        return self.poll_result

    def wait(self) -> int:
        if self.wait_error is not None:
            raise self.wait_error
        return self.wait_result

    def terminate(self) -> None:
        self.terminate_calls += 1
        if self.terminate_error is not None:
            raise self.terminate_error

    def kill(self) -> None:
        self.kill_calls += 1
        if self.kill_error is not None:
            raise self.kill_error


class _ReaderDouble:
    def __init__(
        self,
        alive_results: tuple[bool, ...],
        *,
        stream: _FakeStream | None = None,
        expose_stream: bool = True,
    ) -> None:
        self._alive_results = list(alive_results)
        self.join_calls = 0
        if expose_stream:
            self._remote_ops_stream = stream

    def join(self, *, timeout: float) -> None:
        assert timeout == qt_terminal_process._HIDDEN_READER_JOIN_TIMEOUT_SECONDS
        self.join_calls += 1

    def is_alive(self) -> bool:
        if len(self._alive_results) > 1:
            return self._alive_results.pop(0)
        return self._alive_results[0]


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


def test_hidden_process_accessors_empty_reads_and_start_guards() -> None:
    process = QtHiddenProcess()
    errors: list[object] = []
    process.errorOccurred.connect(errors.append)

    assert process.program() == ""
    assert process.arguments() == []
    assert process.processId() == 0
    process._stdout.extend(b"stdout")
    process._stderr.extend(b"stderr")
    assert process.readStandardOutput(0) == b""
    assert process.readStandardError(-1) == b""

    process.start()
    assert errors == [qt_core.QProcess.ProcessError.FailedToStart]
    assert process.state() == qt_core.QProcess.ProcessState.NotRunning

    process.setProgram("helper")
    arguments = ["one", "two"]
    process.setArguments(arguments)
    arguments.append("caller-only")
    assert process.program() == "helper"
    assert process.arguments() == ["one", "two"]
    process._state = qt_core.QProcess.ProcessState.Starting
    process.start()
    assert process.state() == qt_core.QProcess.ProcessState.Starting

    fake = _FakeProcess()
    process._process = fake
    assert process.processId() == 31337
    process.close()


def test_hidden_process_worker_and_poll_startup_failure_edges(monkeypatch) -> None:
    process = QtHiddenProcess()
    process._generation = 1
    process._disposed = False

    def reject_popen(*_args, **_kwargs):
        raise ValueError("invalid helper arguments")

    monkeypatch.setattr(qt_terminal_process.subprocess, "Popen", reject_popen)
    process._start_process_worker(1, ("helper",), {})
    assert process._pending_start is not None
    assert isinstance(process._pending_start[2], ValueError)

    process._state = qt_core.QProcess.ProcessState.Starting
    process._poll_startup()
    assert process.state() == qt_core.QProcess.ProcessState.NotRunning
    assert "invalid helper arguments" in process.errorString()

    closed: list[_FakeProcess] = []
    monkeypatch.setattr(process, "_close_process_async", closed.append)
    stale = _FakeProcess()
    process._generation = 3
    process._disposed = False
    process._state = qt_core.QProcess.ProcessState.Starting
    process._pending_start = (2, stale, None)
    process._poll_startup()
    assert closed == [stale]

    process._generation = 4
    process._state = qt_core.QProcess.ProcessState.Starting
    process._pending_start = (3, None, None)
    process._poll_startup()
    assert closed == [stale]

    process._generation = 4
    process._state = qt_core.QProcess.ProcessState.Starting
    process._pending_start = (4, None, None)
    process._poll_startup()
    assert process.state() == qt_core.QProcess.ProcessState.NotRunning
    assert process.errorString() == "process failed to start"
    process.close()


def test_hidden_process_stale_worker_closes_spawned_child(monkeypatch) -> None:
    process = QtHiddenProcess()
    fake = _FakeProcess(stdin=_FakeStream())
    closed: list[_FakeProcess] = []
    monkeypatch.setattr(qt_terminal_process.subprocess, "Popen", lambda *_a, **_k: fake)
    monkeypatch.setattr(process, "_close_process_async", closed.append)

    process._generation = 2
    process._disposed = False
    process._start_process_worker(1, ("helper",), {})
    assert closed == [fake]

    process._disposed = True
    process._start_process_worker(2, ("helper",), {})
    assert closed == [fake, fake]
    process.close()


def test_hidden_process_async_close_tolerates_stream_and_kill_errors() -> None:
    broken_stream = _FakeStream(close_error=OSError("close failed"))
    broken = _FakeProcess(
        stdin=broken_stream,
        poll_result=None,
        kill_error=OSError("kill failed"),
    )
    process = QtHiddenProcess()
    process._close_process_async(broken)
    assert broken_stream.closed.wait(1.0)
    deadline = time.monotonic() + 1.0
    while broken.kill_calls == 0 and time.monotonic() < deadline:
        time.sleep(0.01)
    assert broken.kill_calls == 1

    exited = _FakeProcess(stdin=None, poll_result=0)
    process._close_process_async(exited)
    time.sleep(0.05)
    assert exited.kill_calls == 0
    process.close()


def test_hidden_writer_handles_absent_stale_and_control_items() -> None:
    process = QtHiddenProcess()
    process._generation = 4
    process._disposed = False

    empty_queue = qt_terminal_process.queue.Queue()
    process._write_main(_FakeProcess(stdin=None), 4, empty_queue)

    stale_stream = _FakeStream()
    stale_queue = qt_terminal_process.queue.Queue()
    stale_queue.put_nowait(b"discarded")
    process._pending_write_bytes = len(b"discarded")
    process._write_main(_FakeProcess(stdin=stale_stream), 3, stale_queue)
    assert stale_stream.closed.is_set()
    assert process._pending_write_bytes == 0

    for item in (qt_terminal_process._WRITE_CLOSE, object()):
        stream = _FakeStream()
        write_queue = qt_terminal_process.queue.Queue()
        write_queue.put_nowait(item)
        process._write_main(_FakeProcess(stdin=stream), 4, write_queue)
        assert stream.closed.is_set()

    process._write_close_requested = True
    closing_stream = _FakeStream()
    process._write_main(
        _FakeProcess(stdin=closing_stream, poll_result=None),
        4,
        qt_terminal_process.queue.Queue(),
    )
    assert closing_stream.closed.is_set()

    process._write_close_requested = False
    exited_stream = _FakeStream()
    process._write_main(
        _FakeProcess(stdin=exited_stream, poll_result=0),
        4,
        qt_terminal_process.queue.Queue(),
    )
    assert exited_stream.closed.is_set()
    process.close()


def test_hidden_writer_reports_active_errors_and_drains_queue() -> None:
    process = QtHiddenProcess()
    process._generation = 1
    process._disposed = False
    stream = _FakeStream(write_error=BrokenPipeError("write failed"))
    fake = _FakeProcess(stdin=stream, poll_result=None)
    write_queue = qt_terminal_process.queue.Queue()
    write_queue.put_nowait(b"first")
    write_queue.put_nowait(b"remaining")
    write_queue.put_nowait(qt_terminal_process._WRITE_CLOSE)
    process._pending_write_bytes = len(b"firstremaining")

    process._write_main(fake, 1, write_queue)

    assert process.errorString() == "write failed"
    assert process._pending_errors == [qt_core.QProcess.ProcessError.WriteError]
    assert process._pending_write_bytes == 0
    assert stream.closed.is_set()
    process.close()


def test_hidden_writer_suppresses_exit_errors_and_tolerates_close_failure() -> None:
    process = QtHiddenProcess()
    process._generation = 1
    process._disposed = False
    stream = _FakeStream(
        flush_error=ValueError("flush after exit"),
        close_error=ValueError("already closed"),
    )
    write_queue = qt_terminal_process.queue.Queue()
    write_queue.put_nowait(b"payload")
    process._pending_write_bytes = len(b"payload")

    process._write_main(_FakeProcess(stdin=stream, poll_result=0), 1, write_queue)

    assert process._pending_errors == []
    assert process._pending_write_bytes == 0
    assert stream.closed.is_set()
    process.close()


def test_hidden_reader_handles_missing_stale_and_normal_streams() -> None:
    process = QtHiddenProcess()
    process._generation = 5
    process._disposed = False
    assert process._start_reader(None, bytearray(), "stdout", 5) is None

    stale_stream = _FakeStream(close_error=OSError("stale close"))
    stale_reader = process._start_reader(stale_stream, bytearray(), "stdout", 4)
    assert stale_reader is not None
    stale_reader.join(timeout=1.0)
    assert stale_stream.closed.is_set()

    target = bytearray()
    stream = _FakeStream(reads=(b"chunk", b""))
    reader = process._start_reader(stream, target, "stdout", 5)
    assert reader is not None
    reader.join(timeout=1.0)
    assert bytes(target) == b"chunk"
    assert process._pending_stdout_ready is True
    assert stream.closed.is_set()

    process._disposed = True
    disposed_stream = _FakeStream()
    disposed_reader = process._start_reader(disposed_stream, bytearray(), "stdout", 5)
    assert disposed_reader is not None
    disposed_reader.join(timeout=1.0)
    assert disposed_stream.closed.is_set()
    process.close()


def test_hidden_reader_waits_for_pause_and_buffer_capacity() -> None:
    process = QtHiddenProcess()
    process._generation = 1
    process._disposed = False
    process._output_paused = True
    target = bytearray(b"x" * qt_terminal_process._HIDDEN_OUTPUT_HIGH_WATER_BYTES)
    stream = _FakeStream(reads=(b"released", b""))
    reader = process._start_reader(stream, target, "stdout", 1)
    assert reader is not None
    time.sleep(0.03)
    assert stream.reads

    with process._buffer_lock:
        target.clear()
    process.setOutputPaused(False)
    reader.join(timeout=1.0)

    assert bytes(target) == b"released"
    assert stream.closed.is_set()
    process.close()


def test_hidden_reader_reports_and_suppresses_expected_read_errors() -> None:
    process = QtHiddenProcess()
    process._generation = 1
    process._disposed = False
    failing = _FakeStream(
        reads=(OSError("read failed"),),
        close_error=ValueError("close failed"),
    )
    reader = process._start_reader(failing, bytearray(), "stdout", 1)
    assert reader is not None
    reader.join(timeout=1.0)
    assert process.errorString() == "read failed"
    assert process._pending_errors == [qt_core.QProcess.ProcessError.ReadError]
    assert failing.closed.is_set()

    for forced, shutdown_generation in ((True, None), (False, 1)):
        process._pending_errors.clear()
        process._forced_termination = forced
        process._reader_shutdown_generation = shutdown_generation
        expected = _FakeStream(reads=(OSError("expected shutdown"),))
        reader = process._start_reader(expected, bytearray(), "stdout", 1)
        assert reader is not None
        reader.join(timeout=1.0)
        assert process._pending_errors == []

    class DisposingStream(_FakeStream):
        def read(self, _size: int) -> bytes:
            process._disposed = True
            raise OSError("disposed owner")

    process._disposed = False
    process._forced_termination = False
    process._reader_shutdown_generation = None
    reader = process._start_reader(DisposingStream(), bytearray(), "stdout", 1)
    assert reader is not None
    reader.join(timeout=1.0)
    assert process._pending_errors == []
    process.close()


def test_hidden_waiter_handles_wait_and_stream_close_errors() -> None:
    process = QtHiddenProcess()
    process._generation = 2
    process._disposed = False
    process._state = qt_core.QProcess.ProcessState.Running
    stdin = _FakeStream(close_error=OSError("stdin already closed"))
    fake = _FakeProcess(stdin=stdin, wait_error=OSError("wait failed"))
    finished_event = threading.Event()

    process._wait_for_process(fake, 2, [], finished_event)

    assert process._pending_errors == [qt_core.QProcess.ProcessError.Crashed]
    assert process._pending_finished == (
        -1,
        qt_core.QProcess.ExitStatus.NormalExit,
    )
    assert finished_event.is_set()
    assert stdin.closed.is_set()

    process._pending_errors.clear()
    stale_event = threading.Event()
    process._generation = 4
    process._wait_for_process(
        _FakeProcess(wait_error=OSError("stale wait")),
        3,
        [],
        stale_event,
    )
    assert process._pending_errors == []
    assert stale_event.is_set() is False
    process.close()


def test_hidden_waiter_bounds_inherited_reader_cleanup() -> None:
    process = QtHiddenProcess()
    process._generation = 1
    process._disposed = False
    process._state = qt_core.QProcess.ProcessState.Running
    no_stream = _ReaderDouble((True,), expose_stream=False)
    broken_stream = _FakeStream(close_error=OSError("reader close failed"))
    with_stream = _ReaderDouble((True,), stream=broken_stream)
    finished_event = threading.Event()

    process._wait_for_process(
        _FakeProcess(wait_result=7),
        1,
        [no_stream, with_stream],
        finished_event,
    )

    assert no_stream.join_calls == 2
    assert with_stream.join_calls == 2
    assert broken_stream.closed.wait(1.0)
    assert process._reader_shutdown_generation == 1
    assert process._pending_finished == (
        7,
        qt_core.QProcess.ExitStatus.NormalExit,
    )
    assert finished_event.is_set()

    stale_event = threading.Event()
    process._generation = 3
    process._wait_for_process(_FakeProcess(), 2, [], stale_event)
    assert stale_event.is_set() is False
    process.close()


def test_hidden_notification_dispatch_and_deleted_owner_guards() -> None:
    process = QtHiddenProcess()
    process._generation = 8
    process._disposed = False
    stdout_ready: list[bool] = []
    stderr_ready: list[bool] = []
    errors: list[object] = []
    finished: list[tuple[int, object]] = []
    process.readyReadStandardOutput.connect(lambda: stdout_ready.append(True))
    process.readyReadStandardError.connect(lambda: stderr_ready.append(True))
    process.errorOccurred.connect(errors.append)
    process.finished.connect(lambda code, status: finished.append((code, status)))

    process._queue_notification("stdout", 8)
    process._queue_notification("stderr", 8)
    process._queue_notification("error", 8, qt_core.QProcess.ProcessError.ReadError)
    process._queue_notification(
        "finished",
        8,
        9,
        qt_core.QProcess.ExitStatus.CrashExit,
    )
    process._queue_notification("unknown", 8)
    process._queue_notification("error", 8)
    process._queue_notification("finished", 8, 1)
    process._dispatch_notifications()

    assert stdout_ready == [True]
    assert stderr_ready == [True]
    assert errors == [qt_core.QProcess.ProcessError.ReadError]
    assert finished == [(9, qt_core.QProcess.ExitStatus.CrashExit)]

    process._queue_notification("stdout", 7)
    process._disposed = True
    process._queue_notification("stderr", 8)
    assert process._pending_stdout_ready is False
    assert process._pending_stderr_ready is False

    process._disposed = False
    process._emit_named_signal("missingSignal")
    assert process._disposed is True

    class BrokenSignal:
        def emit(self, *_arguments) -> None:
            raise RuntimeError("Qt owner deleted")

    process._disposed = False
    process._emit_signal(BrokenSignal())
    assert process._disposed is True
    process._emit_signal(BrokenSignal())
    process.close()


def test_hidden_buffer_reads_and_pause_transitions() -> None:
    process = QtHiddenProcess()
    process._stdout.extend(
        b"x" * (qt_terminal_process._HIDDEN_OUTPUT_LOW_WATER_BYTES + 2)
    )
    assert process.readStandardOutput(1) == b"x"
    assert process.readAllStandardOutput().startswith(b"x")

    process._stderr.extend(
        b"y" * (qt_terminal_process._HIDDEN_OUTPUT_LOW_WATER_BYTES + 2)
    )
    assert process.readStandardError(1) == b"y"
    assert process.readAllStandardError().startswith(b"y")

    process.setOutputPaused(True)
    assert process.property("terminalTransportOutputPaused") is True
    process.setOutputPaused(False)
    assert process.property("terminalTransportOutputPaused") is False
    process._resume_output_reader_after_shutdown(publish_property=True)
    assert process.property("terminalTransportOutputPaused") is False
    process.close()


def test_hidden_write_backpressure_and_closed_input_edges() -> None:
    process = QtHiddenProcess()
    assert process.write(b"") == 0

    process._state = qt_core.QProcess.ProcessState.Starting
    process._disposed = True
    assert process.write(b"x") == -1
    assert process.errorString() == "process is not running"

    process._disposed = False
    process._pending_start_input.extend(
        b"x" * qt_terminal_process._HIDDEN_INPUT_HIGH_WATER_BYTES
    )
    assert process.write(b"x") == -1
    assert process.property("terminalTransportInputBackpressure") is True
    process._pending_start_input.clear()
    assert process.write(b"queued") == len(b"queued")
    process.closeWriteChannel()
    assert process._pending_start_close_write is True

    process._state = qt_core.QProcess.ProcessState.Running
    process._process = None
    assert process.write(b"x") == -1
    process.closeWriteChannel()

    process._process = _FakeProcess(stdin=None)
    assert process.write(b"x") == -1

    process._process = _FakeProcess(stdin=_FakeStream())
    process._generation = 3
    process._write_generation = 2
    process._write_close_requested = False
    assert process.write(b"x") == -1
    assert process.errorString() == "process input is closed"

    process._write_generation = 3
    process._write_close_requested = True
    assert process.write(b"x") == -1

    process._write_close_requested = False
    process._pending_write_bytes = qt_terminal_process._HIDDEN_INPUT_HIGH_WATER_BYTES
    assert process.write(b"x") == -1

    process._pending_write_bytes = 0
    process._write_queue = qt_terminal_process.queue.Queue(maxsize=1)
    process._write_queue.put_nowait(b"occupied")
    assert process.write(b"x") == -1

    process._write_queue = qt_terminal_process.queue.Queue(maxsize=2)
    assert process.write(b"accepted") == len(b"accepted")
    assert process.property("terminalTransportInputQueuedBytes") == len(b"accepted")
    process.closeWriteChannel()
    assert process._write_close_requested is True
    process.close()


def test_hidden_terminate_and_kill_control_edges(monkeypatch) -> None:
    process = QtHiddenProcess()
    finished: list[tuple[int, object]] = []
    errors: list[object] = []
    process.finished.connect(lambda code, status: finished.append((code, status)))
    process.errorOccurred.connect(errors.append)
    closed: list[_FakeProcess] = []
    monkeypatch.setattr(process, "_close_process_async", closed.append)

    pending = _FakeProcess()
    process._generation = 1
    process._state = qt_core.QProcess.ProcessState.Starting
    process._pending_start = (1, pending, None)
    process.terminate()
    assert finished == [(-1, qt_core.QProcess.ExitStatus.CrashExit)]
    assert closed == [pending]

    process._state = qt_core.QProcess.ProcessState.Starting
    process._generation = 2
    process.kill()
    assert finished[-1] == (-1, qt_core.QProcess.ExitStatus.CrashExit)

    process._state = qt_core.QProcess.ProcessState.Running
    process._process = None
    process.terminate()
    process.kill()

    exited = _FakeProcess(poll_result=0)
    process._process = exited
    process.terminate()
    process.kill()
    assert exited.terminate_calls == 0
    assert exited.kill_calls == 0

    terminating = _FakeProcess(
        poll_result=None,
        terminate_error=OSError("terminate failed"),
    )
    process._process = terminating
    process._output_paused = True
    process.terminate()
    assert terminating.terminate_calls == 1
    assert errors[-1] == qt_core.QProcess.ProcessError.Crashed
    assert process.property("terminalTransportOutputPaused") is False

    killing = _FakeProcess(poll_result=None, kill_error=OSError("kill failed"))
    process._process = killing
    process._output_paused = True
    process.kill()
    assert killing.kill_calls == 1
    assert errors[-1] == qt_core.QProcess.ProcessError.Crashed

    healthy = _FakeProcess(poll_result=None)
    process._process = healthy
    process.terminate()
    process.kill()
    assert healthy.terminate_calls == 1
    assert healthy.kill_calls == 1
    process.close()


def test_hidden_wait_for_finished_startup_timeout_and_completion() -> None:
    process = QtHiddenProcess()
    process._state = qt_core.QProcess.ProcessState.Starting
    process._generation = 1
    process._finished_event.clear()
    assert process.waitForFinished(0) is False

    process._pending_start = (1, None, ValueError("startup rejected"))
    assert process.waitForFinished(100) is True
    assert process.state() == qt_core.QProcess.ProcessState.NotRunning

    process._state = qt_core.QProcess.ProcessState.NotRunning
    process._finished_event.clear()
    assert process.waitForFinished(0) is False
    process._finished_event.set()
    assert process.waitForFinished(-1) is True
    process.close()

    process = QtHiddenProcess()
    process._state = qt_core.QProcess.ProcessState.Starting
    process._generation = 1
    process._finished_event.clear()

    def complete_after_waits() -> None:
        time.sleep(0.02)
        process._state = qt_core.QProcess.ProcessState.NotRunning
        time.sleep(0.02)
        process._finished_event.set()

    worker = threading.Thread(target=complete_after_waits, daemon=True)
    worker.start()
    assert process.waitForFinished(200) is True
    worker.join(timeout=1.0)
    process.close()

    process = QtHiddenProcess()
    process._finished_event.clear()

    def complete_unbounded_wait() -> None:
        time.sleep(0.02)
        process._finished_event.set()

    worker = threading.Thread(target=complete_unbounded_wait, daemon=True)
    worker.start()
    assert process.waitForFinished(-1) is True
    worker.join(timeout=1.0)
    process.close()


def test_hidden_close_and_cancel_pending_start_cleanup(monkeypatch) -> None:
    process = QtHiddenProcess()
    closed: list[_FakeProcess] = []
    monkeypatch.setattr(process, "_close_process_async", closed.append)
    assert process._cancel_pending_start() is False

    pending = _FakeProcess()
    process._generation = 1
    process._state = qt_core.QProcess.ProcessState.Starting
    process._pending_start = (1, pending, None)
    process._pending_start_input.extend(b"queued")
    process._pending_start_close_write = True
    assert process._cancel_pending_start() is True
    assert closed == [pending]
    assert process.state() == qt_core.QProcess.ProcessState.NotRunning
    assert process._finished_event.is_set()

    pending_on_close = _FakeProcess()
    running_on_close = _FakeProcess()
    process._disposed = False
    process._state = qt_core.QProcess.ProcessState.Starting
    process._pending_start = (process._generation, pending_on_close, None)
    process._process = running_on_close
    process.close()
    assert closed[-2:] == [pending_on_close, running_on_close]


def test_hidden_delete_later_and_conpty_availability(monkeypatch, qt_app) -> None:
    process = QtHiddenProcess()
    process._state = qt_core.QProcess.ProcessState.Starting
    process.deleteLater()
    qt_app.processEvents()
    assert process._disposed is True

    class Support:
        supported = True

    monkeypatch.setattr(qt_terminal_process, "conpty_support", Support)
    assert qt_terminal_process.qt_conpty_available() is True

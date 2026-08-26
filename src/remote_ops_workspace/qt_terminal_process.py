"""Qt signal adapter for the dependency-free Windows ConPTY transport."""

from __future__ import annotations

import os
import queue
import subprocess
import threading
import time
from collections.abc import Sequence
from typing import Any, Final

from PyQt6.QtCore import QObject, QProcess, QTimer, pyqtSignal

from .process_launch import hidden_process_options
from .windows_conpty import (
    ConPtyProcessError,
    WindowsConPtyProcess,
    conpty_support,
)

_OUTPUT_EOF_DRAIN_TIMEOUT_SECONDS = 2.0
_FORCED_TERMINATION_TIMEOUT_SECONDS = 2.0
_SESSION_CLOSE_TIMEOUT_SECONDS = 0.5
_HIDDEN_OUTPUT_HIGH_WATER_BYTES = 4 * 1024 * 1024
_HIDDEN_OUTPUT_LOW_WATER_BYTES = 1 * 1024 * 1024
_HIDDEN_INPUT_HIGH_WATER_BYTES = 1 * 1024 * 1024
_HIDDEN_INPUT_QUEUE_MAX_ITEMS = 128
_OUTPUT_READ_CHUNK_BYTES = 64 * 1024
_HIDDEN_READER_JOIN_TIMEOUT_SECONDS = 0.25


class _WriteClose:
    """Typed sentinel used to stop the hidden-process writer queue."""


_WRITE_CLOSE: Final = _WriteClose()


def _take_buffer_prefix(buffer: bytearray, max_bytes: int) -> bytes:
    """Remove at most ``max_bytes`` while keeping unread transport bytes."""

    limit = max(0, int(max_bytes))
    if limit <= 0 or not buffer:
        return b""
    amount = min(limit, len(buffer))
    payload = bytes(buffer[:amount])
    del buffer[:amount]
    return payload


class QtConPtyProcess(QObject):
    """Expose :class:`WindowsConPtyProcess` through the QProcess subset used by the GUI."""

    readyReadStandardOutput = pyqtSignal()
    readyReadStandardError = pyqtSignal()
    started = pyqtSignal()
    errorOccurred = pyqtSignal(object)
    finished = pyqtSignal(int, object)

    is_pty = True

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._program = ""
        self._arguments: list[str] = []
        self._state = QProcess.ProcessState.NotRunning
        self._session: WindowsConPtyProcess | None = None
        self._stdout = bytearray()
        self._output_paused = False
        self._error_string = ""
        self._reported_io_error: BaseException | None = None
        self._pending_returncode: int | None = None
        self._output_shutdown_started = False
        self._output_shutdown_deadline: float | None = None
        self._forced_termination = False
        self._forced_termination_deadline: float | None = None
        self._finished_emitted = True
        # ConPTY creation and ClosePseudoConsole can block on older Windows
        # builds. Keep both operations out of the Qt event loop so tab changes
        # and terminal input stay responsive while a child starts or exits.
        self._lifecycle_lock = threading.RLock()
        self._generation = 0
        self._disposed = False
        self._pending_start: tuple[
            int,
            WindowsConPtyProcess | None,
            BaseException | None,
        ] | None = None
        self._start_thread: threading.Thread | None = None
        self._pending_start_input = bytearray()
        self._pending_start_close_write = False
        self.setProperty("terminalTransportResizeWarning", "")
        self.setProperty("terminalTransportResizeWarningCount", 0)
        self.setProperty("terminalTransportStartupAsync", True)
        # ConPTY owns the child console surface. Keep the policy explicit so
        # GUI diagnostics and native smoke tests detect a regression to a
        # visible helper window during tab transitions.
        self.setProperty("terminalConsoleSuppressed", True)
        self.setProperty("terminalChildWindowPolicy", "conpty-hidden")
        self._columns = 120
        self._rows = 30
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(15)
        self._poll_timer.timeout.connect(self._poll_session)
        self._startup_timer = QTimer(self)
        self._startup_timer.setInterval(10)
        self._startup_timer.timeout.connect(self._poll_startup)

    def setProcessChannelMode(self, _mode) -> None:  # noqa: N802
        """ConPTY already exposes one merged terminal output stream."""

    def setProgram(self, program: str) -> None:  # noqa: N802
        self._program = str(program)

    def setArguments(self, arguments: Sequence[str]) -> None:  # noqa: N802
        self._arguments = [str(argument) for argument in arguments]

    def program(self) -> str:
        return self._program

    def arguments(self) -> list[str]:
        return list(self._arguments)

    def state(self):
        return self._state

    def processId(self) -> int:  # noqa: N802
        session = self._session
        return int(session.pid or 0) if session is not None else 0

    def errorString(self) -> str:  # noqa: N802
        return self._error_string

    def start(self) -> None:
        if self._state != QProcess.ProcessState.NotRunning:
            return
        if self._disposed:
            self._fail_start("ConPTY process has been disposed")
            return
        if not self._program:
            self._fail_start("empty terminal program")
            return
        self._dispose_session(terminate=True)
        self._stdout.clear()
        self._output_paused = False
        self._error_string = ""
        self._reported_io_error = None
        self._pending_returncode = None
        self._output_shutdown_started = False
        self._output_shutdown_deadline = None
        self._forced_termination = False
        self._forced_termination_deadline = None
        self._finished_emitted = False
        self._state = QProcess.ProcessState.Starting
        with self._lifecycle_lock:
            self._generation += 1
            generation = self._generation
            self._pending_start = None
            self._pending_start_input.clear()
            self._pending_start_close_write = False
        argv = (self._program, *self._arguments)
        columns = self._columns
        rows = self._rows
        self._start_thread = threading.Thread(
            target=self._start_session_worker,
            args=(generation, argv, columns, rows),
            name="remote-ops-conpty-starter",
            daemon=True,
        )
        self._start_thread.start()
        self._startup_timer.start()

    def _start_session_worker(
        self,
        generation: int,
        argv: Sequence[str],
        columns: int,
        rows: int,
    ) -> None:
        session: WindowsConPtyProcess | None = None
        error: BaseException | None = None
        try:
            session = WindowsConPtyProcess(
                argv,
                columns=columns,
                rows=rows,
            )
            session.start()
        except Exception as exc:  # pragma: no cover - platform-specific failure
            error = exc
            if session is not None:
                try:
                    session.close(terminate=True, timeout=0.25)
                except (OSError, RuntimeError):
                    pass
                session = None
        with self._lifecycle_lock:
            stale = generation != self._generation or self._disposed
            if not stale:
                self._pending_start = (generation, session, error)
        if stale and session is not None:
            try:
                session.close(terminate=True, timeout=0.25)
            except (OSError, RuntimeError):
                pass

    def _poll_startup(self) -> None:
        with self._lifecycle_lock:
            result = self._pending_start
            self._pending_start = None
        if result is None:
            return
        generation, session, error = result
        self._startup_timer.stop()
        self._start_thread = None
        if (
            generation != self._generation
            or self._disposed
            or self._state != QProcess.ProcessState.Starting
        ):
            if session is not None:
                self._close_session_async(session, terminate=True)
            return
        if error is not None or session is None:
            self._fail_start(str(error) if error is not None else "ConPTY process failed to start")
            return
        self._session = session
        self._state = QProcess.ProcessState.Running
        with self._lifecycle_lock:
            pending_input = bytes(self._pending_start_input)
            self._pending_start_input.clear()
            close_write = self._pending_start_close_write
            self._pending_start_close_write = False
        try:
            if pending_input:
                session.write(pending_input)
            if close_write:
                session.close_input()
        except (BlockingIOError, BrokenPipeError, ConPtyProcessError, RuntimeError) as exc:
            self._fail_session(
                session,
                str(exc),
                QProcess.ProcessError.WriteError,
                terminate=True,
            )
            return
        # A resize can arrive while CreateProcessW is running. Apply the
        # latest viewport dimensions after adoption without blocking this turn.
        resize = getattr(session, "resize", None)
        if callable(resize):
            try:
                resize(self._columns, self._rows)
            except (OSError, RuntimeError, ValueError) as exc:
                self._publish_resize_warning(str(exc))
        self._poll_timer.start()
        self.started.emit()
        self._poll_session()

    def _fail_start(self, detail: str) -> None:
        self._finished_emitted = True
        self._state = QProcess.ProcessState.NotRunning
        self._error_string = detail or "ConPTY process failed to start"
        self.errorOccurred.emit(QProcess.ProcessError.FailedToStart)

    def _poll_session(self) -> None:
        session = self._session
        if session is None:
            self._poll_timer.stop()
            return
        try:
            self._drain_output(session)
        except (OSError, RuntimeError) as exc:
            self._fail_session(
                session,
                str(exc),
                QProcess.ProcessError.ReadError,
                terminate=True,
            )
            return
        resize_error = session.take_resize_error()
        if resize_error is not None:
            # Resize is advisory.  Keep its diagnostic observable without
            # emitting QProcess.errorOccurred: a tab transition can race a
            # stale viewport, and that must not make a healthy SSH session
            # appear failed or trigger teardown/restart logic.
            self._publish_resize_warning(str(resize_error))
        if self._pending_returncode is None:
            try:
                self._pending_returncode = session.poll()
            except (OSError, RuntimeError) as exc:
                self._fail_session(
                    session,
                    str(exc),
                    QProcess.ProcessError.UnknownError,
                    terminate=True,
                )
                return
        io_error = session.io_error
        if io_error is not None and io_error is not self._reported_io_error:
            self._reported_io_error = io_error
            process_error = (
                QProcess.ProcessError.WriteError
                if io_error.operation.startswith("WriteFile")
                else QProcess.ProcessError.ReadError
            )
            self._fail_session(
                session,
                str(io_error),
                process_error,
                terminate=self._pending_returncode is None,
            )
            return
        if self._pending_returncode is None:
            deadline = self._forced_termination_deadline
            if deadline is not None and time.monotonic() >= deadline:
                self._fail_session(
                    session,
                    "timed out waiting for forced ConPTY termination",
                    QProcess.ProcessError.Crashed,
                    terminate=True,
                )
            return
        self._forced_termination_deadline = None

        # The child handle can signal before the ConPTY reader has copied the
        # final pipe chunks into its queue.  Begin a non-blocking pseudoconsole
        # shutdown while the reader remains active, then keep the session alive
        # until the reader reports EOF and perform one last drain.
        if not self._begin_output_shutdown(session):
            return
        if not session.output_eof:
            deadline = self._output_shutdown_deadline
            if deadline is not None and time.monotonic() >= deadline:
                self._fail_session(
                    session,
                    "timed out while draining final ConPTY output after child exit",
                    QProcess.ProcessError.ReadError,
                    terminate=False,
                )
            return
        self._drain_output(session, force=True)
        self._finish_session(session)

    def _finish_session(self, session: WindowsConPtyProcess) -> None:
        if session is not self._session or self._finished_emitted:
            return
        returncode = self._pending_returncode
        if returncode is None or not session.output_eof:
            return
        self._finished_emitted = True
        self._poll_timer.stop()
        self._state = QProcess.ProcessState.NotRunning
        self._output_shutdown_deadline = None
        self._forced_termination_deadline = None
        exit_status = (
            QProcess.ExitStatus.CrashExit
            if self._forced_termination
            else QProcess.ExitStatus.NormalExit
        )
        self._dispose_session(terminate=False)
        self.finished.emit(int(returncode), exit_status)

    def _fail_session(
        self,
        session: WindowsConPtyProcess,
        detail: str,
        process_error: QProcess.ProcessError,
        *,
        terminate: bool,
    ) -> None:
        """Complete a broken transport once and leave the adapter restartable."""

        if session is not self._session or self._finished_emitted:
            return
        returncode = self._pending_returncode
        self._finished_emitted = True
        self._poll_timer.stop()
        self._state = QProcess.ProcessState.NotRunning
        self._error_string = detail or "ConPTY transport failed"
        self._output_shutdown_deadline = None
        self._forced_termination_deadline = None
        self._dispose_session(terminate=terminate)
        # Dispose and publish NotRunning before signals so a deferred restart
        # cannot inherit handles or state from the failed session.
        self.errorOccurred.emit(process_error)
        self.finished.emit(
            int(returncode) if returncode is not None else -1,
            QProcess.ExitStatus.CrashExit,
        )

    def _begin_output_shutdown(self, session: WindowsConPtyProcess) -> bool:
        if self._output_shutdown_started:
            return True
        try:
            session.begin_output_shutdown()
        except (OSError, RuntimeError) as exc:
            self._fail_session(
                session,
                str(exc),
                QProcess.ProcessError.UnknownError,
                terminate=self._pending_returncode is None,
            )
            return False
        self._output_shutdown_started = True
        self._output_shutdown_deadline = (
            time.monotonic() + _OUTPUT_EOF_DRAIN_TIMEOUT_SECONDS
        )
        return True

    def _drain_output(self, session: WindowsConPtyProcess, *, force: bool = False) -> None:
        if self._output_paused and not force:
            return
        payload = session.read_all()
        if not payload:
            return
        self._stdout.extend(payload)
        self.readyReadStandardOutput.emit()

    def readAllStandardOutput(self) -> bytes:  # noqa: N802
        return self.readStandardOutput(len(self._stdout))

    def readStandardOutput(self, max_bytes: int) -> bytes:  # noqa: N802
        return _take_buffer_prefix(self._stdout, max_bytes)

    def readAllStandardError(self) -> bytes:  # noqa: N802
        return b""

    def readStandardError(self, _max_bytes: int) -> bytes:  # noqa: N802
        return b""

    def setOutputPaused(self, paused: bool) -> None:  # noqa: N802
        """Backpressure the bounded ConPTY queue instead of growing RAM."""

        self._output_paused = bool(paused)
        self.setProperty("terminalTransportOutputPaused", self._output_paused)
        if not self._output_paused:
            self._poll_session()

    def write(self, payload: bytes) -> int:
        data = bytes(payload)
        if not data:
            return 0
        if self._state == QProcess.ProcessState.Starting:
            with self._lifecycle_lock:
                if (
                    len(self._pending_start_input) + len(data)
                    > _HIDDEN_INPUT_HIGH_WATER_BYTES
                ):
                    self._error_string = "terminal input queue is full"
                    self.setProperty("terminalTransportInputBackpressure", True)
                    return -1
                self._pending_start_input.extend(data)
                queued_bytes = len(self._pending_start_input)
            self.setProperty("terminalTransportInputQueuedBytes", queued_bytes)
            self.setProperty("terminalTransportInputBackpressure", False)
            return len(data)
        session = self._session
        if session is None or self._state != QProcess.ProcessState.Running:
            self._error_string = "ConPTY process is not running"
            return -1
        try:
            return session.write(data)
        except (BlockingIOError, BrokenPipeError, ConPtyProcessError, RuntimeError) as exc:
            self._error_string = str(exc)
            self.errorOccurred.emit(QProcess.ProcessError.WriteError)
            return -1

    def closeWriteChannel(self) -> None:  # noqa: N802
        if self._state == QProcess.ProcessState.Starting:
            with self._lifecycle_lock:
                self._pending_start_close_write = True
            return
        session = self._session
        if session is not None:
            session.close_input()

    def setTerminalSize(self, columns: int, rows: int) -> None:  # noqa: N802
        self._columns = max(1, min(32767, int(columns)))
        self._rows = max(1, min(32767, int(rows)))
        session = self._session
        if session is None or self._state == QProcess.ProcessState.NotRunning:
            return
        try:
            session.resize(self._columns, self._rows)
        except (OSError, RuntimeError, ValueError) as exc:
            self._publish_resize_warning(str(exc))

    def _publish_resize_warning(self, detail: str) -> None:
        """Expose geometry diagnostics without changing transport lifecycle."""

        warning = str(detail).strip() or "terminal viewport resize failed"
        self._error_string = warning
        count = int(self.property("terminalTransportResizeWarningCount") or 0) + 1
        self.setProperty("terminalTransportResizeWarning", warning)
        self.setProperty("terminalTransportResizeWarningCount", count)

    def terminate(self) -> None:
        if self._cancel_pending_start():
            self._forced_termination = True
            self.finished.emit(-1, QProcess.ExitStatus.CrashExit)
            return
        session = self._session
        if session is None:
            return
        try:
            returncode = session.poll()
            if returncode is None:
                self._forced_termination = True
                session.terminate()
            else:
                self._pending_returncode = returncode
        except (OSError, RuntimeError) as exc:
            self._fail_session(
                session,
                str(exc),
                QProcess.ProcessError.Crashed,
                terminate=True,
            )
            return
        self._poll_session()

    def kill(self) -> None:
        if self._cancel_pending_start():
            self._forced_termination = True
            self.finished.emit(-1, QProcess.ExitStatus.CrashExit)
            return
        session = self._session
        if session is None:
            return
        try:
            returncode = session.poll()
            if returncode is None:
                self._forced_termination = True
                session.kill()
                self._forced_termination_deadline = (
                    time.monotonic() + _FORCED_TERMINATION_TIMEOUT_SECONDS
                )
                self._poll_timer.start()
            else:
                self._pending_returncode = returncode
        except (OSError, RuntimeError) as exc:
            self._fail_session(
                session,
                str(exc),
                QProcess.ProcessError.Crashed,
                terminate=True,
            )
            return
        self._poll_session()

    def waitForFinished(self, milliseconds: int = 30000) -> bool:  # noqa: N802
        self.setOutputPaused(False)
        timeout = None if milliseconds < 0 else max(0, milliseconds) / 1000
        deadline = None if timeout is None else time.monotonic() + timeout
        while self._state == QProcess.ProcessState.Starting:
            self._poll_startup()
            if self._state != QProcess.ProcessState.Starting:
                break
            if deadline is not None and time.monotonic() >= deadline:
                return False
            time.sleep(0.005)
        session = self._session
        if session is None:
            return True
        deadline = None if timeout is None else time.monotonic() + timeout
        try:
            self._pending_returncode = session.wait(timeout)
        except subprocess.TimeoutExpired:
            return False
        except (OSError, RuntimeError) as exc:
            self._fail_session(
                session,
                str(exc),
                QProcess.ProcessError.UnknownError,
                terminate=True,
            )
            return self._finished_emitted
        if not self._begin_output_shutdown(session):
            return self._finished_emitted
        while not session.output_eof:
            self._drain_output(session)
            drain_deadline = self._output_shutdown_deadline
            if drain_deadline is not None and time.monotonic() >= drain_deadline:
                self._fail_session(
                    session,
                    "timed out while draining final ConPTY output after child exit",
                    QProcess.ProcessError.ReadError,
                    terminate=False,
                )
                return self._finished_emitted
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                if drain_deadline is not None:
                    remaining = min(
                        remaining,
                        max(0.0, drain_deadline - time.monotonic()),
                    )
                session.output_ready.wait(min(0.01, remaining))
                session.output_ready.clear()
            else:
                drain_remaining = (
                    max(0.0, drain_deadline - time.monotonic())
                    if drain_deadline is not None
                    else 0.01
                )
                session.output_ready.wait(min(0.01, drain_remaining))
                session.output_ready.clear()
        self._drain_output(session)
        self._finish_session(session)
        return self._finished_emitted

    def close(self) -> None:
        with self._lifecycle_lock:
            self._generation += 1
            self._pending_start = None
            self._pending_start_input.clear()
            self._pending_start_close_write = False
        self._startup_timer.stop()
        self._poll_timer.stop()
        self._output_paused = False
        self._finished_emitted = True
        self._pending_returncode = None
        self._output_shutdown_started = False
        self._output_shutdown_deadline = None
        self._forced_termination_deadline = None
        self._state = QProcess.ProcessState.NotRunning
        self._dispose_session(terminate=True)

    def _cancel_pending_start(self) -> bool:
        """Cancel a ConPTY creation that has not yet adopted its child."""

        with self._lifecycle_lock:
            if self._state != QProcess.ProcessState.Starting:
                return False
            self._generation += 1
            self._pending_start = None
            self._pending_start_input.clear()
            self._pending_start_close_write = False
        self._startup_timer.stop()
        self._state = QProcess.ProcessState.NotRunning
        self._finished_emitted = True
        return True

    def _dispose_session(self, *, terminate: bool) -> None:
        session = self._session
        self._session = None
        if session is None:
            return
        self._close_session_async(session, terminate=terminate)

    def _close_session_async(
        self,
        session: WindowsConPtyProcess,
        *,
        terminate: bool,
    ) -> None:
        def close_session() -> None:
            try:
                session.close(
                    terminate=terminate,
                    timeout=_SESSION_CLOSE_TIMEOUT_SECONDS,
                )
            except (OSError, RuntimeError):
                pass

        threading.Thread(
            target=close_session,
            name="remote-ops-conpty-closer",
            daemon=True,
        ).start()

    def deleteLater(self) -> None:  # noqa: N802
        self._disposed = True
        self.close()
        super().deleteLater()


def hidden_process_creation_flags(system_name: str | None = None) -> int:
    """Return the Windows flag that prevents helper console windows."""

    return int(hidden_process_options(system_name).get("creationflags", 0))


class QtHiddenProcess(QObject):
    """Small QProcess-compatible adapter for invisible helper commands.

    Qt does not expose ``CREATE_NO_WINDOW`` through PyQt6. Background SFTP,
    monitoring and pipe-fallback commands therefore used to flash a console
    whenever a tab changed. This adapter keeps the familiar signal API while
    running the child through ``subprocess.Popen`` with hidden Windows startup
    flags and off-thread pipe readers.
    """

    readyReadStandardOutput = pyqtSignal()
    readyReadStandardError = pyqtSignal()
    started = pyqtSignal()
    errorOccurred = pyqtSignal(object)
    finished = pyqtSignal(int, object)

    is_pty = False

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._program = ""
        self._arguments: list[str] = []
        self._state = QProcess.ProcessState.NotRunning
        self._process: subprocess.Popen[bytes] | None = None
        self._stdout = bytearray()
        self._stderr = bytearray()
        self._buffer_lock = threading.Lock()
        self._output_pause_condition = threading.Condition()
        self._output_paused = False
        self._write_condition = threading.Condition()
        self._write_queue: queue.Queue[bytes | _WriteClose] = queue.Queue(
            maxsize=_HIDDEN_INPUT_QUEUE_MAX_ITEMS,
        )
        self._write_thread: threading.Thread | None = None
        self._write_generation = 0
        self._pending_write_bytes = 0
        self._write_close_requested = False
        self._merged_channels = False
        self._error_string = ""
        self._forced_termination = False
        self._generation = 0
        # Process creation can block while Windows resolves a helper command
        # or waits on image loading. Keep that work outside the Qt thread so
        # monitoring/SFTP refreshes cannot freeze tab switching.
        self._lifecycle_lock = threading.RLock()
        self._pending_start: tuple[
            int,
            subprocess.Popen[bytes] | None,
            BaseException | None,
        ] | None = None
        self._start_thread: threading.Thread | None = None
        self._pending_start_input = bytearray()
        self._pending_start_close_write = False
        self._reader_shutdown_generation: int | None = None
        self._disposed = False
        self._finished_event = threading.Event()
        self._finished_event.set()
        self._notification_lock = threading.Lock()
        self._pending_stdout_ready = False
        self._pending_stderr_ready = False
        self._pending_errors: list[object] = []
        self._pending_finished: tuple[int, object] | None = None
        self._notification_timer = QTimer(self)
        self._notification_timer.setInterval(10)
        self._notification_timer.timeout.connect(self._dispatch_notifications)
        self._startup_timer = QTimer(self)
        self._startup_timer.setInterval(10)
        self._startup_timer.timeout.connect(self._poll_startup)
        self.setProperty("backgroundConsoleSuppressed", os.name == "nt")
        self.setProperty("terminalConsoleSuppressed", os.name == "nt")
        self.setProperty(
            "terminalChildWindowPolicy",
            "create-no-window" if os.name == "nt" else "pipe",
        )
        self.setProperty("terminalTransportStartupAsync", True)
        self.setProperty(
            "terminalTransportBufferHighWaterBytes",
            _HIDDEN_OUTPUT_HIGH_WATER_BYTES,
        )

    def setProcessChannelMode(self, mode) -> None:  # noqa: N802
        self._merged_channels = mode == QProcess.ProcessChannelMode.MergedChannels

    def setProgram(self, program: str) -> None:  # noqa: N802
        self._program = str(program)

    def setArguments(self, arguments: Sequence[str]) -> None:  # noqa: N802
        self._arguments = [str(argument) for argument in arguments]

    def program(self) -> str:
        return self._program

    def arguments(self) -> list[str]:
        return list(self._arguments)

    def state(self):
        return self._state

    def processId(self) -> int:  # noqa: N802
        process = self._process
        return int(process.pid or 0) if process is not None else 0

    def errorString(self) -> str:  # noqa: N802
        return self._error_string

    def start(self) -> None:
        if self._state != QProcess.ProcessState.NotRunning:
            return
        if not self._program:
            self._fail_start("empty process program")
            return
        self._disposed = False
        with self._output_pause_condition:
            self._output_paused = False
            self._output_pause_condition.notify_all()
        self._stdout.clear()
        self._stderr.clear()
        self._error_string = ""
        self._forced_termination = False
        self._reader_shutdown_generation = None
        with self._notification_lock:
            self._pending_stdout_ready = False
            self._pending_stderr_ready = False
            self._pending_errors.clear()
            self._pending_finished = None
        with self._lifecycle_lock:
            self._generation += 1
            generation = self._generation
            self._pending_start = None
            self._pending_start_input.clear()
            self._pending_start_close_write = False
        self._finished_event = threading.Event()
        self._state = QProcess.ProcessState.Starting
        options: dict[str, Any] = {
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT if self._merged_channels else subprocess.PIPE,
            "bufsize": 0,
        }
        options.update(hidden_process_options())
        argv = (self._program, *self._arguments)
        self._start_thread = threading.Thread(
            target=self._start_process_worker,
            args=(generation, argv, options),
            name="remote-ops-hidden-process-starter",
            daemon=True,
        )
        self._start_thread.start()
        self._startup_timer.start()

    def _start_process_worker(
        self,
        generation: int,
        argv: Sequence[str],
        options: dict[str, Any],
    ) -> None:
        process: subprocess.Popen[bytes] | None = None
        error: BaseException | None = None
        try:
            process = subprocess.Popen(  # noqa: S603
                list(argv),
                **options,
            )
        except (OSError, ValueError) as exc:
            error = exc
        with self._lifecycle_lock:
            stale = generation != self._generation or self._disposed
            if not stale:
                self._pending_start = (generation, process, error)
        if stale and process is not None:
            self._close_process_async(process)

    def _poll_startup(self) -> None:
        with self._lifecycle_lock:
            result = self._pending_start
            self._pending_start = None
        if result is None:
            return
        generation, process, error = result
        self._startup_timer.stop()
        self._start_thread = None
        with self._lifecycle_lock:
            stale = (
                generation != self._generation
                or self._disposed
                or self._state != QProcess.ProcessState.Starting
            )
        if stale:
            if process is not None:
                self._close_process_async(process)
            return
        if error is not None or process is None:
            self._fail_start(
                str(error) if error is not None else "process failed to start"
            )
            return
        self._process = process
        self._state = QProcess.ProcessState.Running
        with self._lifecycle_lock:
            pending_input = bytes(self._pending_start_input)
            self._pending_start_input.clear()
            close_write = self._pending_start_close_write
            self._pending_start_close_write = False
        with self._write_condition:
            self._write_queue = queue.Queue(maxsize=_HIDDEN_INPUT_QUEUE_MAX_ITEMS)
            self._write_generation = generation
            self._pending_write_bytes = len(pending_input)
            self._write_close_requested = close_write
            if pending_input:
                self._write_queue.put_nowait(pending_input)
        self.setProperty("terminalTransportInputQueuedBytes", len(pending_input))
        self._write_thread = threading.Thread(
            target=self._write_main,
            args=(process, generation, self._write_queue),
            name="remote-ops-hidden-process-writer",
            daemon=True,
        )
        self._write_thread.start()
        self._notification_timer.start()
        self.started.emit()
        readers = [
            self._start_reader(
                process.stdout,
                self._stdout,
                "stdout",
                generation,
            )
        ]
        if not self._merged_channels:
            readers.append(
                self._start_reader(
                    process.stderr,
                    self._stderr,
                    "stderr",
                    generation,
                )
            )
        threading.Thread(
            target=self._wait_for_process,
            args=(
                process,
                generation,
                [reader for reader in readers if reader],
                self._finished_event,
            ),
            name="remote-ops-hidden-process-waiter",
            daemon=True,
        ).start()

    def _close_process_async(self, process: subprocess.Popen[bytes]) -> None:
        """Terminate a stale child without making tab teardown wait on it."""

        def close_process() -> None:
            if process.stdin is not None:
                try:
                    process.stdin.close()
                except (OSError, ValueError):
                    pass
            if process.poll() is None:
                try:
                    process.kill()
                except OSError:
                    pass

        threading.Thread(
            target=close_process,
            name="remote-ops-hidden-process-closer",
            daemon=True,
        ).start()

    def _write_main(
        self,
        process: subprocess.Popen[bytes],
        generation: int,
        write_queue: queue.Queue[bytes | _WriteClose],
    ) -> None:
        """Write queued terminal input outside the Qt event loop."""

        stream = process.stdin
        if stream is None:
            return
        try:
            while generation == self._generation and not self._disposed:
                try:
                    item = write_queue.get(timeout=0.1)
                except queue.Empty:
                    with self._write_condition:
                        should_close = (
                            self._write_close_requested
                            and self._pending_write_bytes == 0
                        )
                    if should_close or process.poll() is not None:
                        break
                    continue
                if item is _WRITE_CLOSE:
                    break
                if not isinstance(item, bytes):
                    break
                payload = item
                try:
                    stream.write(payload)
                    stream.flush()
                except (BrokenPipeError, OSError, ValueError) as exc:
                    # A normal child exit closes stdin while the writer may
                    # still be draining. Do not turn that expected teardown
                    # into a second GUI error notification.
                    if (
                        generation == self._generation
                        and not self._disposed
                        and process.poll() is None
                    ):
                        self._error_string = str(exc)
                        self._queue_notification(
                            "error",
                            generation,
                            QProcess.ProcessError.WriteError,
                        )
                    break
                finally:
                    with self._write_condition:
                        self._pending_write_bytes = max(
                            0,
                            self._pending_write_bytes - len(payload),
                        )
                        self._write_condition.notify_all()
        finally:
            try:
                stream.close()
            except (OSError, ValueError):
                pass
            with self._write_condition:
                while True:
                    try:
                        item = write_queue.get_nowait()
                    except queue.Empty:
                        break
                    if isinstance(item, bytes):
                        self._pending_write_bytes = max(
                            0,
                            self._pending_write_bytes - len(item),
                        )
                self._pending_write_bytes = 0
                self._write_condition.notify_all()

    def _fail_start(self, detail: str) -> None:
        self._process = None
        self._state = QProcess.ProcessState.NotRunning
        self._error_string = detail or "process failed to start"
        with self._lifecycle_lock:
            self._pending_start_input.clear()
            self._pending_start_close_write = False
        self.setProperty("terminalTransportInputQueuedBytes", 0)
        self._finished_event.set()
        self.errorOccurred.emit(QProcess.ProcessError.FailedToStart)

    def _start_reader(
        self,
        stream,
        target: bytearray,
        notification: str,
        generation: int,
    ) -> threading.Thread | None:
        if stream is None:
            return None

        def read_stream() -> None:
            try:
                while generation == self._generation:
                    with self._output_pause_condition:
                        while generation == self._generation and not self._disposed:
                            with self._buffer_lock:
                                buffer_full = (
                                    len(target) >= _HIDDEN_OUTPUT_HIGH_WATER_BYTES
                                )
                            if not self._output_paused and not buffer_full:
                                break
                            self._output_pause_condition.wait(timeout=0.1)
                        if generation != self._generation or self._disposed:
                            break
                    payload = stream.read(_OUTPUT_READ_CHUNK_BYTES)
                    if not payload:
                        break
                    with self._buffer_lock:
                        target.extend(payload)
                    self._queue_notification(notification, generation)
            except (OSError, ValueError) as exc:
                if (
                    not self._forced_termination
                    and not self._disposed
                    and generation != self._reader_shutdown_generation
                ):
                    self._error_string = str(exc)
                    self._queue_notification(
                        "error",
                        generation,
                        QProcess.ProcessError.ReadError,
                    )
            finally:
                try:
                    stream.close()
                except (OSError, ValueError):
                    pass

        thread = threading.Thread(
            target=read_stream,
            name="remote-ops-hidden-process-reader",
            daemon=True,
        )
        # The waiter uses this only when an inherited child handle keeps a
        # reader blocked after the parent exits. Normal readers close
        # themselves at EOF.
        thread._remote_ops_stream = stream  # type: ignore[attr-defined]
        thread.start()
        return thread

    def _wait_for_process(
        self,
        process: subprocess.Popen[bytes],
        generation: int,
        readers: list[threading.Thread],
        finished_event: threading.Event,
    ) -> None:
        try:
            return_code = int(process.wait())
        except OSError as exc:
            if generation != self._generation:
                return
            self._error_string = str(exc)
            self._queue_notification(
                "error",
                generation,
                QProcess.ProcessError.Crashed,
            )
            return_code = -1
        # A terminal pane can pause its pipe reader at the bounded high-water
        # mark while a tab is being replaced. Once the child has exited there
        # is no future producer to protect, so release that pause before
        # joining readers; otherwise a stopped process can wait forever for a
        # GUI drain that will never arrive.
        self._resume_output_reader_after_shutdown()
        with self._write_condition:
            self._write_close_requested = True
            self._write_condition.notify_all()
        if process.stdin is not None:
            try:
                process.stdin.close()
            except (OSError, ValueError):
                pass
        for reader in readers:
            reader.join(timeout=_HIDDEN_READER_JOIN_TIMEOUT_SECONDS)
        blocked_readers = [reader for reader in readers if reader.is_alive()]
        if blocked_readers:
            # A helper can spawn a short-lived child that inherits stdout or
            # stderr. The parent has exited, but that inherited handle keeps a
            # reader blocked forever. Closing that stream can itself wait for
            # the blocked Windows read, so perform it on a daemon cleanup
            # thread and keep the waiter bounded as well.
            self._reader_shutdown_generation = generation
            for reader in blocked_readers:
                stream = getattr(reader, "_remote_ops_stream", None)
                if stream is None:
                    continue

                def close_stream(stream=stream) -> None:
                    try:
                        stream.close()
                    except (OSError, ValueError):
                        pass

                threading.Thread(
                    target=close_stream,
                    name="remote-ops-hidden-process-reader-closer",
                    daemon=True,
                ).start()
            for reader in blocked_readers:
                reader.join(timeout=_HIDDEN_READER_JOIN_TIMEOUT_SECONDS)
        if generation != self._generation:
            return
        self._process = None
        self._state = QProcess.ProcessState.NotRunning
        exit_status = (
            QProcess.ExitStatus.CrashExit
            if self._forced_termination
            else QProcess.ExitStatus.NormalExit
        )
        self._queue_notification("finished", generation, return_code, exit_status)
        # A finished callback may synchronously start the same adapter again.
        # Signal the event belonging to this process generation, not whatever
        # event the replacement run has installed on ``self``.
        finished_event.set()

    def _resume_output_reader_after_shutdown(self, *, publish_property: bool = False) -> None:
        """Wake a paused reader so process teardown cannot deadlock on output."""

        with self._output_pause_condition:
            self._output_paused = False
            self._output_pause_condition.notify_all()
        # ``_wait_for_process`` runs on a worker thread; Qt properties must
        # only be touched by the owning GUI thread. The direct stop methods
        # opt in because they are called from that thread.
        if publish_property:
            self.setProperty("terminalTransportOutputPaused", False)

    def _queue_notification(self, kind: str, generation: int, *arguments) -> None:
        """Record worker-thread events for delivery by the Qt event loop."""

        with self._notification_lock:
            if self._disposed or generation != self._generation:
                return
            if kind == "stdout":
                self._pending_stdout_ready = True
            elif kind == "stderr":
                self._pending_stderr_ready = True
            elif kind == "error" and arguments:
                self._pending_errors.append(arguments[0])
            elif kind == "finished" and len(arguments) == 2:
                self._pending_finished = (int(arguments[0]), arguments[1])

    def _dispatch_notifications(self) -> None:
        """Emit queued notifications only from the QObject's GUI thread."""

        with self._notification_lock:
            stdout_ready = self._pending_stdout_ready
            stderr_ready = self._pending_stderr_ready
            errors = tuple(self._pending_errors)
            finished = self._pending_finished
            self._pending_stdout_ready = False
            self._pending_stderr_ready = False
            self._pending_errors.clear()
            self._pending_finished = None
        if finished is not None:
            self._notification_timer.stop()
        if stdout_ready:
            self._emit_named_signal("readyReadStandardOutput")
        if stderr_ready:
            self._emit_named_signal("readyReadStandardError")
        for error in errors:
            self._emit_named_signal("errorOccurred", error)
        if finished is not None:
            self._emit_named_signal("finished", *finished)

    def _emit_named_signal(self, name: str, *arguments) -> None:
        try:
            signal = getattr(self, name)
        except (AttributeError, RuntimeError):
            self._disposed = True
            return
        self._emit_signal(signal, *arguments)

    def _emit_signal(self, signal, *arguments) -> None:
        if self._disposed:
            return
        try:
            signal.emit(*arguments)
        except (AttributeError, RuntimeError):
            self._disposed = True

    def readAllStandardOutput(self) -> bytes:  # noqa: N802
        return self.readStandardOutput(len(self._stdout))

    def readStandardOutput(self, max_bytes: int) -> bytes:  # noqa: N802
        with self._buffer_lock:
            payload = _take_buffer_prefix(self._stdout, max_bytes)
            should_resume = len(self._stdout) <= _HIDDEN_OUTPUT_LOW_WATER_BYTES
        if should_resume:
            with self._output_pause_condition:
                self._output_pause_condition.notify_all()
        return payload

    def readAllStandardError(self) -> bytes:  # noqa: N802
        return self.readStandardError(len(self._stderr))

    def readStandardError(self, max_bytes: int) -> bytes:  # noqa: N802
        with self._buffer_lock:
            payload = _take_buffer_prefix(self._stderr, max_bytes)
            should_resume = len(self._stderr) <= _HIDDEN_OUTPUT_LOW_WATER_BYTES
        if should_resume:
            with self._output_pause_condition:
                self._output_pause_condition.notify_all()
        return payload

    def setOutputPaused(self, paused: bool) -> None:  # noqa: N802
        """Stop pipe readers at a byte-preserving OS backpressure boundary."""

        with self._output_pause_condition:
            self._output_paused = bool(paused)
            if not self._output_paused:
                self._output_pause_condition.notify_all()
        self.setProperty("terminalTransportOutputPaused", self._output_paused)

    def write(self, payload: bytes) -> int:
        data = bytes(payload)
        if not data:
            return 0
        if self._state == QProcess.ProcessState.Starting:
            with self._lifecycle_lock:
                if self._disposed:
                    self._error_string = "process is not running"
                    return -1
                if (
                    len(self._pending_start_input) + len(data)
                    > _HIDDEN_INPUT_HIGH_WATER_BYTES
                ):
                    self._error_string = "terminal input queue is full"
                    self.setProperty("terminalTransportInputBackpressure", True)
                    return -1
                self._pending_start_input.extend(data)
                queued_bytes = len(self._pending_start_input)
            self.setProperty("terminalTransportInputQueuedBytes", queued_bytes)
            self.setProperty("terminalTransportInputBackpressure", False)
            return len(data)
        process = self._process
        if process is None or process.stdin is None or self._state != QProcess.ProcessState.Running:
            self._error_string = "process is not running"
            return -1
        with self._write_condition:
            if self._write_generation != self._generation or self._write_close_requested:
                self._error_string = "process input is closed"
                return -1
            if self._pending_write_bytes + len(data) > _HIDDEN_INPUT_HIGH_WATER_BYTES:
                self._error_string = "terminal input queue is full"
                self.setProperty("terminalTransportInputBackpressure", True)
                return -1
            try:
                self._write_queue.put_nowait(data)
            except queue.Full:
                self._error_string = "terminal input queue is full"
                self.setProperty("terminalTransportInputBackpressure", True)
                return -1
            self._pending_write_bytes += len(data)
            self.setProperty("terminalTransportInputQueuedBytes", self._pending_write_bytes)
            self.setProperty("terminalTransportInputBackpressure", False)
            return len(data)

    def closeWriteChannel(self) -> None:  # noqa: N802
        if self._state == QProcess.ProcessState.Starting:
            with self._lifecycle_lock:
                self._pending_start_close_write = True
            return
        if self._process is None:
            return
        with self._write_condition:
            self._write_close_requested = True
            self._write_condition.notify_all()

    def terminate(self) -> None:
        if self._cancel_pending_start():
            self._forced_termination = True
            self.finished.emit(-1, QProcess.ExitStatus.CrashExit)
            return
        process = self._process
        if process is None or process.poll() is not None:
            return
        self._forced_termination = True
        try:
            process.terminate()
        except OSError as exc:
            self._error_string = str(exc)
            self._emit_signal(self.errorOccurred, QProcess.ProcessError.Crashed)
        finally:
            self._resume_output_reader_after_shutdown(publish_property=True)

    def kill(self) -> None:
        if self._cancel_pending_start():
            self._forced_termination = True
            self.finished.emit(-1, QProcess.ExitStatus.CrashExit)
            return
        process = self._process
        if process is None or process.poll() is not None:
            return
        self._forced_termination = True
        try:
            process.kill()
        except OSError as exc:
            self._error_string = str(exc)
            self._emit_signal(self.errorOccurred, QProcess.ProcessError.Crashed)
        finally:
            self._resume_output_reader_after_shutdown(publish_property=True)

    def waitForFinished(self, milliseconds: int = 30000) -> bool:  # noqa: N802
        timeout = None if milliseconds < 0 else max(0, milliseconds) / 1000
        deadline = None if timeout is None else time.monotonic() + timeout
        while self._state == QProcess.ProcessState.Starting:
            self._poll_startup()
            if self._state != QProcess.ProcessState.Starting:
                break
            if deadline is not None and time.monotonic() >= deadline:
                return False
            time.sleep(0.005)
        while True:
            # This method is normally called by the owning Qt thread during a
            # bounded shutdown. Keep delivering ready notifications so a full
            # adapter buffer can be consumed and its pipe reader can reach EOF.
            self._dispatch_notifications()
            if self._finished_event.is_set():
                self._dispatch_notifications()
                return True
            wait_seconds = 0.01
            if deadline is not None:
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    return False
                wait_seconds = min(wait_seconds, remaining)
            self._finished_event.wait(wait_seconds)

    def close(self) -> None:
        with self._lifecycle_lock:
            self._disposed = True
            self._generation += 1
            pending_start = self._pending_start
            self._pending_start = None
            self._pending_start_input.clear()
            self._pending_start_close_write = False
        with self._output_pause_condition:
            self._output_paused = False
            self._output_pause_condition.notify_all()
        self._notification_timer.stop()
        with self._write_condition:
            self._write_close_requested = True
            self._write_condition.notify_all()
        with self._notification_lock:
            self._pending_stdout_ready = False
            self._pending_stderr_ready = False
            self._pending_errors.clear()
            self._pending_finished = None
        process = self._process
        self._process = None
        self._state = QProcess.ProcessState.NotRunning
        self._finished_event.set()
        self._startup_timer.stop()
        self.setProperty("terminalTransportInputQueuedBytes", 0)
        if pending_start is not None and pending_start[1] is not None:
            self._close_process_async(pending_start[1])
        if process is None:
            return
        self._close_process_async(process)

    def _cancel_pending_start(self) -> bool:
        """Cancel a helper process that has not yet reached the Qt thread."""

        with self._lifecycle_lock:
            if self._state != QProcess.ProcessState.Starting:
                return False
            self._generation += 1
            pending_start = self._pending_start
            self._pending_start = None
            self._pending_start_input.clear()
            self._pending_start_close_write = False
        self._startup_timer.stop()
        self._state = QProcess.ProcessState.NotRunning
        self._finished_event.set()
        self.setProperty("terminalTransportInputQueuedBytes", 0)
        if pending_start is not None and pending_start[1] is not None:
            self._close_process_async(pending_start[1])
        return True

    def deleteLater(self) -> None:  # noqa: N802
        self.close()
        super().deleteLater()


def qt_conpty_available() -> bool:
    return conpty_support().supported


__all__ = [
    "QtConPtyProcess",
    "QtHiddenProcess",
    "hidden_process_creation_flags",
    "qt_conpty_available",
]

"""Qt signal adapter for the dependency-free Windows ConPTY transport."""

from __future__ import annotations

import os
import subprocess
import threading
import time
from collections.abc import Sequence
from typing import Any

from PyQt6.QtCore import QObject, QProcess, QTimer, pyqtSignal

from .windows_conpty import (
    ConPtyProcessError,
    WindowsConPtyProcess,
    conpty_support,
)

_OUTPUT_EOF_DRAIN_TIMEOUT_SECONDS = 2.0
_SESSION_CLOSE_TIMEOUT_SECONDS = 0.5
_HIDDEN_OUTPUT_HIGH_WATER_BYTES = 4 * 1024 * 1024
_HIDDEN_OUTPUT_LOW_WATER_BYTES = 1 * 1024 * 1024
_OUTPUT_READ_CHUNK_BYTES = 64 * 1024


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
        self._finished_emitted = True
        self._columns = 120
        self._rows = 30
        self._poll_timer = QTimer(self)
        self._poll_timer.setInterval(15)
        self._poll_timer.timeout.connect(self._poll_session)

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
        self._finished_emitted = False
        self._state = QProcess.ProcessState.Starting
        session = WindowsConPtyProcess(
            [self._program, *self._arguments],
            columns=self._columns,
            rows=self._rows,
        )
        try:
            session.start()
        except (OSError, RuntimeError, ValueError) as exc:
            session.close()
            self._session = None
            self._fail_start(str(exc))
            return
        self._session = session
        self._state = QProcess.ProcessState.Running
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
            # Resize is advisory: report the failed viewport update once, but
            # keep the live input/output pipes usable for subsequent commands.
            self._error_string = str(resize_error)
            self.errorOccurred.emit(QProcess.ProcessError.UnknownError)
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
            return

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
        session = self._session
        if session is None or self._state != QProcess.ProcessState.Running:
            self._error_string = "ConPTY process is not running"
            return -1
        try:
            return session.write(payload)
        except (BlockingIOError, BrokenPipeError, ConPtyProcessError, RuntimeError) as exc:
            self._error_string = str(exc)
            self.errorOccurred.emit(QProcess.ProcessError.WriteError)
            return -1

    def closeWriteChannel(self) -> None:  # noqa: N802
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
            self._error_string = str(exc)
            self.errorOccurred.emit(QProcess.ProcessError.UnknownError)

    def terminate(self) -> None:
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
        session = self._session
        if session is None:
            return
        try:
            returncode = session.poll()
            if returncode is None:
                self._forced_termination = True
                session.kill()
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
        session = self._session
        if session is None:
            return True
        timeout = None if milliseconds < 0 else max(0, milliseconds) / 1000
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
        self._poll_timer.stop()
        self._output_paused = False
        self._finished_emitted = True
        self._pending_returncode = None
        self._output_shutdown_started = False
        self._output_shutdown_deadline = None
        self._state = QProcess.ProcessState.NotRunning
        self._dispose_session(terminate=True)

    def _dispose_session(self, *, terminate: bool) -> None:
        session = self._session
        self._session = None
        if session is None:
            return
        try:
            session.close(
                terminate=terminate,
                timeout=_SESSION_CLOSE_TIMEOUT_SECONDS,
            )
        except (OSError, RuntimeError):
            pass

    def deleteLater(self) -> None:  # noqa: N802
        self.close()
        super().deleteLater()


def hidden_process_creation_flags(system_name: str | None = None) -> int:
    """Return the Windows flag that prevents helper console windows."""

    native_windows = (system_name or os.name).lower() in {"nt", "windows", "win32"}
    if not native_windows:
        return 0
    return int(getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000))


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
        self._merged_channels = False
        self._error_string = ""
        self._forced_termination = False
        self._generation = 0
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
        self.setProperty("backgroundConsoleSuppressed", os.name == "nt")
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
        with self._notification_lock:
            self._pending_stdout_ready = False
            self._pending_stderr_ready = False
            self._pending_errors.clear()
            self._pending_finished = None
        self._generation += 1
        generation = self._generation
        self._finished_event = threading.Event()
        self._state = QProcess.ProcessState.Starting
        options: dict[str, Any] = {
            "stdin": subprocess.PIPE,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT if self._merged_channels else subprocess.PIPE,
            "bufsize": 0,
        }
        creation_flags = hidden_process_creation_flags()
        if creation_flags:
            options["creationflags"] = creation_flags
            startup_info_factory = getattr(subprocess, "STARTUPINFO", None)
            if startup_info_factory is not None:
                startup_info = startup_info_factory()
                startup_info.dwFlags |= int(getattr(subprocess, "STARTF_USESHOWWINDOW", 0x00000001))
                startup_info.wShowWindow = int(getattr(subprocess, "SW_HIDE", 0))
                options["startupinfo"] = startup_info
        try:
            process = subprocess.Popen(  # noqa: S603
                [self._program, *self._arguments],
                **options,
            )
        except (OSError, ValueError) as exc:
            self._fail_start(str(exc))
            return
        self._process = process
        self._state = QProcess.ProcessState.Running
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
            args=(process, generation, [reader for reader in readers if reader]),
            name="remote-ops-hidden-process-waiter",
            daemon=True,
        ).start()

    def _fail_start(self, detail: str) -> None:
        self._process = None
        self._state = QProcess.ProcessState.NotRunning
        self._error_string = detail or "process failed to start"
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
            except OSError as exc:
                if not self._forced_termination and not self._disposed:
                    self._error_string = str(exc)
                    self._queue_notification(
                        "error",
                        generation,
                        QProcess.ProcessError.ReadError,
                    )
            finally:
                try:
                    stream.close()
                except OSError:
                    pass

        thread = threading.Thread(
            target=read_stream,
            name="remote-ops-hidden-process-reader",
            daemon=True,
        )
        thread.start()
        return thread

    def _wait_for_process(
        self,
        process: subprocess.Popen[bytes],
        generation: int,
        readers: list[threading.Thread],
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
        for reader in readers:
            reader.join()
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
        self._finished_event.set()

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
        process = self._process
        if process is None or process.stdin is None or self._state != QProcess.ProcessState.Running:
            self._error_string = "process is not running"
            return -1
        try:
            accepted = process.stdin.write(bytes(payload))
            process.stdin.flush()
        except (BrokenPipeError, OSError, ValueError) as exc:
            self._error_string = str(exc)
            self._emit_signal(self.errorOccurred, QProcess.ProcessError.WriteError)
            return -1
        return len(payload) if accepted is None else int(accepted)

    def closeWriteChannel(self) -> None:  # noqa: N802
        process = self._process
        if process is None or process.stdin is None:
            return
        try:
            process.stdin.close()
        except OSError:
            pass

    def terminate(self) -> None:
        process = self._process
        if process is None or process.poll() is not None:
            return
        self._forced_termination = True
        try:
            process.terminate()
        except OSError as exc:
            self._error_string = str(exc)
            self._emit_signal(self.errorOccurred, QProcess.ProcessError.Crashed)

    def kill(self) -> None:
        process = self._process
        if process is None or process.poll() is not None:
            return
        self._forced_termination = True
        try:
            process.kill()
        except OSError as exc:
            self._error_string = str(exc)
            self._emit_signal(self.errorOccurred, QProcess.ProcessError.Crashed)

    def waitForFinished(self, milliseconds: int = 30000) -> bool:  # noqa: N802
        timeout = None if milliseconds < 0 else max(0, milliseconds) / 1000
        deadline = None if timeout is None else time.monotonic() + timeout
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
        self._disposed = True
        self._generation += 1
        with self._output_pause_condition:
            self._output_paused = False
            self._output_pause_condition.notify_all()
        self._notification_timer.stop()
        with self._notification_lock:
            self._pending_stdout_ready = False
            self._pending_stderr_ready = False
            self._pending_errors.clear()
            self._pending_finished = None
        process = self._process
        self._process = None
        self._state = QProcess.ProcessState.NotRunning
        self._finished_event.set()
        if process is None:
            return
        if process.stdin is not None:
            try:
                process.stdin.close()
            except OSError:
                pass
        if process.poll() is None:
            try:
                process.kill()
            except OSError:
                pass

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

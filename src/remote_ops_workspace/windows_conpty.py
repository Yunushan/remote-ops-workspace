"""Dependency-free Windows pseudo-console process transport.

``QProcess`` and ``subprocess`` normally connect a child to anonymous pipes.
That is sufficient for line-oriented commands, but it is not a terminal:
interactive programs such as OpenSSH can require a console for host-key,
password, and passphrase prompts.  Windows 10 version 1809 introduced ConPTY,
which provides the missing local pseudo-console without opening a second
window.

This module deliberately has no Qt dependency.  A GUI adapter can poll
``output_ready``/``read()`` from its event loop and forward input through
``write()``.  Blocking Win32 pipe calls run only on daemon worker threads.
"""

from __future__ import annotations

import ctypes
import math
import os
import queue
import shutil
import subprocess
import sys
import threading
import time
from collections.abc import Sequence
from ctypes import wintypes
from dataclasses import dataclass
from pathlib import Path

MINIMUM_CONPTY_BUILD = 17763

_PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE = 0x00020016
_EXTENDED_STARTUPINFO_PRESENT = 0x00080000
_STARTF_USESTDHANDLES = 0x00000100
_HANDLE_FLAG_INHERIT = 0x00000001
_WAIT_OBJECT_0 = 0x00000000
_WAIT_TIMEOUT = 0x00000102
_WAIT_FAILED = 0xFFFFFFFF
_INFINITE = 0xFFFFFFFF
_ERROR_BROKEN_PIPE = 109
_ERROR_NO_DATA = 232
_ERROR_PIPE_NOT_CONNECTED = 233
_ERROR_OPERATION_ABORTED = 995
_PIPE_SHUTDOWN_ERRORS = {
    _ERROR_BROKEN_PIPE,
    _ERROR_NO_DATA,
    _ERROR_PIPE_NOT_CONNECTED,
    _ERROR_OPERATION_ABORTED,
}
_OUTPUT_EOF = object()
_MAX_PIPE_CHUNK = 64 * 1024
_MAX_QUEUED_CHUNKS = 256
_OUTPUT_DRAIN_QUIET_SECONDS = 0.1
_OUTPUT_DRAIN_MAX_WAIT_SECONDS = 1.0


class ConPtyUnavailableError(RuntimeError):
    """Raised when the host cannot provide the Windows ConPTY API."""


class ConPtyProcessError(OSError):
    """A Win32 or ConPTY process operation failed."""

    def __init__(self, operation: str, error_code: int, message: str) -> None:
        super().__init__(error_code, f"{operation}: {message}")
        self.operation = operation
        self.error_code = int(error_code)


@dataclass(frozen=True, slots=True)
class ConPtySupport:
    """Runtime feature-detection result."""

    supported: bool
    reason: str
    windows_build: int | None


class _COORD(ctypes.Structure):
    _fields_ = [
        ("X", wintypes.SHORT),
        ("Y", wintypes.SHORT),
    ]


class _SECURITY_ATTRIBUTES(ctypes.Structure):
    _fields_ = [
        ("nLength", wintypes.DWORD),
        ("lpSecurityDescriptor", wintypes.LPVOID),
        ("bInheritHandle", wintypes.BOOL),
    ]


class _STARTUPINFOW(ctypes.Structure):
    _fields_ = [
        ("cb", wintypes.DWORD),
        ("lpReserved", wintypes.LPWSTR),
        ("lpDesktop", wintypes.LPWSTR),
        ("lpTitle", wintypes.LPWSTR),
        ("dwX", wintypes.DWORD),
        ("dwY", wintypes.DWORD),
        ("dwXSize", wintypes.DWORD),
        ("dwYSize", wintypes.DWORD),
        ("dwXCountChars", wintypes.DWORD),
        ("dwYCountChars", wintypes.DWORD),
        ("dwFillAttribute", wintypes.DWORD),
        ("dwFlags", wintypes.DWORD),
        ("wShowWindow", wintypes.WORD),
        ("cbReserved2", wintypes.WORD),
        ("lpReserved2", ctypes.POINTER(wintypes.BYTE)),
        ("hStdInput", wintypes.HANDLE),
        ("hStdOutput", wintypes.HANDLE),
        ("hStdError", wintypes.HANDLE),
    ]


class _STARTUPINFOEXW(ctypes.Structure):
    _fields_ = [
        ("StartupInfo", _STARTUPINFOW),
        ("lpAttributeList", wintypes.LPVOID),
    ]


class _PROCESS_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("hProcess", wintypes.HANDLE),
        ("hThread", wintypes.HANDLE),
        ("dwProcessId", wintypes.DWORD),
        ("dwThreadId", wintypes.DWORD),
    ]


def _running_on_windows() -> bool:
    return os.name == "nt"


def _windows_build_number() -> int | None:
    if not _running_on_windows() or not hasattr(sys, "getwindowsversion"):
        return None
    return int(sys.getwindowsversion().build)


def _conpty_exports_available() -> bool:
    if not _running_on_windows() or not hasattr(ctypes, "WinDLL"):
        return False
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    except OSError:
        return False
    return all(
        hasattr(kernel32, name)
        for name in (
            "CreatePseudoConsole",
            "ResizePseudoConsole",
            "ClosePseudoConsole",
            "InitializeProcThreadAttributeList",
            "UpdateProcThreadAttribute",
        )
    )


def conpty_support() -> ConPtySupport:
    """Return an evidence-bearing ConPTY feature-detection result."""

    if not _running_on_windows():
        return ConPtySupport(False, "ConPTY is available only on Windows", None)
    build = _windows_build_number()
    if build is None:
        return ConPtySupport(False, "Windows build number is unavailable", None)
    if build < MINIMUM_CONPTY_BUILD:
        return ConPtySupport(
            False,
            (
                f"ConPTY requires Windows 10 version 1809/build {MINIMUM_CONPTY_BUILD} "
                f"or newer; detected build {build}"
            ),
            build,
        )
    if not _conpty_exports_available():
        return ConPtySupport(
            False,
            "Windows reports a compatible build but the ConPTY exports are unavailable",
            build,
        )
    return ConPtySupport(True, "ConPTY is available", build)


def require_conpty_support() -> ConPtySupport:
    """Return supported runtime details or raise a clear compatibility error."""

    support = conpty_support()
    if not support.supported:
        raise ConPtyUnavailableError(support.reason)
    return support


def _validated_windows_argv(argv: Sequence[str]) -> tuple[str, ...]:
    """Validate argv without first coercing a scalar string into characters."""

    if isinstance(argv, (str, bytes)):
        raise ValueError("argv must be a non-empty sequence of strings")
    cleaned: list[str] = []
    try:
        arguments = iter(argv)
    except TypeError as exc:
        raise ValueError("argv must be a non-empty sequence of strings") from exc
    for index, argument in enumerate(arguments):
        if not isinstance(argument, str):
            raise TypeError(f"argv[{index}] must be a string")
        if "\x00" in argument:
            raise ValueError(f"argv[{index}] must not contain NUL")
        cleaned.append(argument)
    if not cleaned:
        raise ValueError("argv must be a non-empty sequence of strings")
    if not cleaned[0]:
        raise ValueError("argv[0] must not be empty")
    return tuple(cleaned)


def quote_windows_argv(argv: Sequence[str]) -> str:
    """Build a CreateProcessW command line without invoking a command shell."""

    return subprocess.list2cmdline(_validated_windows_argv(argv))


def _validate_dimension(value: int, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if not 1 <= value <= 32767:
        raise ValueError(f"{name} must be between 1 and 32767")
    return value


def _validate_cwd(cwd: str | os.PathLike[str] | None) -> str | None:
    if cwd is None:
        return None
    value = os.fspath(cwd)
    if isinstance(value, bytes):
        raise TypeError("cwd must resolve to text, not bytes")
    if "\x00" in value:
        raise ValueError("cwd must not contain NUL")
    return str(Path(value))


def _resolve_windows_executable(executable: str) -> str:
    """Resolve a basename before using it as CreateProcessW.lpApplicationName."""

    resolved = shutil.which(executable)
    if resolved is None:
        raise FileNotFoundError(2, f"executable was not found on PATH: {executable}", executable)
    return str(Path(resolved).resolve())


class _Kernel32Api:
    """Typed kernel32 entry points used by :class:`WindowsConPtyProcess`."""

    def __init__(self) -> None:
        require_conpty_support()
        self.dll = ctypes.WinDLL("kernel32", use_last_error=True)
        self._bind()

    def _bind(self) -> None:
        self.CreatePipe = self.dll.CreatePipe
        self.CreatePipe.argtypes = [
            ctypes.POINTER(wintypes.HANDLE),
            ctypes.POINTER(wintypes.HANDLE),
            ctypes.POINTER(_SECURITY_ATTRIBUTES),
            wintypes.DWORD,
        ]
        self.CreatePipe.restype = wintypes.BOOL

        self.SetHandleInformation = self.dll.SetHandleInformation
        self.SetHandleInformation.argtypes = [
            wintypes.HANDLE,
            wintypes.DWORD,
            wintypes.DWORD,
        ]
        self.SetHandleInformation.restype = wintypes.BOOL

        self.CloseHandle = self.dll.CloseHandle
        self.CloseHandle.argtypes = [wintypes.HANDLE]
        self.CloseHandle.restype = wintypes.BOOL

        self.CreatePseudoConsole = self.dll.CreatePseudoConsole
        self.CreatePseudoConsole.argtypes = [
            _COORD,
            wintypes.HANDLE,
            wintypes.HANDLE,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.HANDLE),
        ]
        self.CreatePseudoConsole.restype = ctypes.c_long

        self.ResizePseudoConsole = self.dll.ResizePseudoConsole
        self.ResizePseudoConsole.argtypes = [wintypes.HANDLE, _COORD]
        self.ResizePseudoConsole.restype = ctypes.c_long

        self.ClosePseudoConsole = self.dll.ClosePseudoConsole
        self.ClosePseudoConsole.argtypes = [wintypes.HANDLE]
        self.ClosePseudoConsole.restype = None

        self.InitializeProcThreadAttributeList = self.dll.InitializeProcThreadAttributeList
        self.InitializeProcThreadAttributeList.argtypes = [
            wintypes.LPVOID,
            wintypes.DWORD,
            wintypes.DWORD,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        self.InitializeProcThreadAttributeList.restype = wintypes.BOOL

        self.UpdateProcThreadAttribute = self.dll.UpdateProcThreadAttribute
        self.UpdateProcThreadAttribute.argtypes = [
            wintypes.LPVOID,
            wintypes.DWORD,
            ctypes.c_size_t,
            wintypes.LPVOID,
            ctypes.c_size_t,
            wintypes.LPVOID,
            ctypes.POINTER(ctypes.c_size_t),
        ]
        self.UpdateProcThreadAttribute.restype = wintypes.BOOL

        self.DeleteProcThreadAttributeList = self.dll.DeleteProcThreadAttributeList
        self.DeleteProcThreadAttributeList.argtypes = [wintypes.LPVOID]
        self.DeleteProcThreadAttributeList.restype = None

        self.CreateProcessW = self.dll.CreateProcessW
        self.CreateProcessW.argtypes = [
            wintypes.LPCWSTR,
            wintypes.LPWSTR,
            wintypes.LPVOID,
            wintypes.LPVOID,
            wintypes.BOOL,
            wintypes.DWORD,
            wintypes.LPVOID,
            wintypes.LPCWSTR,
            ctypes.POINTER(_STARTUPINFOW),
            ctypes.POINTER(_PROCESS_INFORMATION),
        ]
        self.CreateProcessW.restype = wintypes.BOOL

        self.ReadFile = self.dll.ReadFile
        self.ReadFile.argtypes = [
            wintypes.HANDLE,
            wintypes.LPVOID,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            wintypes.LPVOID,
        ]
        self.ReadFile.restype = wintypes.BOOL

        self.WriteFile = self.dll.WriteFile
        self.WriteFile.argtypes = [
            wintypes.HANDLE,
            wintypes.LPCVOID,
            wintypes.DWORD,
            ctypes.POINTER(wintypes.DWORD),
            wintypes.LPVOID,
        ]
        self.WriteFile.restype = wintypes.BOOL

        self.WaitForSingleObject = self.dll.WaitForSingleObject
        self.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        self.WaitForSingleObject.restype = wintypes.DWORD

        self.GetExitCodeProcess = self.dll.GetExitCodeProcess
        self.GetExitCodeProcess.argtypes = [
            wintypes.HANDLE,
            ctypes.POINTER(wintypes.DWORD),
        ]
        self.GetExitCodeProcess.restype = wintypes.BOOL

        self.TerminateProcess = self.dll.TerminateProcess
        self.TerminateProcess.argtypes = [wintypes.HANDLE, wintypes.UINT]
        self.TerminateProcess.restype = wintypes.BOOL


def _last_error(operation: str) -> ConPtyProcessError:
    code = int(ctypes.get_last_error())
    try:
        message = ctypes.WinError(code).strerror
    except (AttributeError, OSError):
        message = f"Win32 error {code}"
    return ConPtyProcessError(operation, code, str(message))


def _hresult_error(operation: str, hresult: int) -> ConPtyProcessError:
    unsigned = int(hresult) & 0xFFFFFFFF
    win32_code = unsigned & 0xFFFF if (unsigned & 0xFFFF0000) == 0x80070000 else unsigned
    try:
        message = ctypes.WinError(win32_code).strerror
    except (AttributeError, OSError):
        message = f"HRESULT 0x{unsigned:08X}"
    return ConPtyProcessError(
        operation,
        win32_code,
        f"{message} (HRESULT 0x{unsigned:08X})",
    )


def _handle_is_open(handle: wintypes.HANDLE | None) -> bool:
    return bool(handle is not None and getattr(handle, "value", handle))


def _configure_conpty_startup_info(startup: _STARTUPINFOEXW) -> None:
    """Prevent redirected parent stdio from bypassing the pseudoconsole."""

    startup.StartupInfo.cb = ctypes.sizeof(_STARTUPINFOEXW)
    # A console child can otherwise receive duplicated redirected standard
    # handles even when bInheritHandles is FALSE, bypassing ConPTY entirely.
    # Microsoft Terminal's maintainer documents the required ConPTY-specific
    # exception: set STARTF_USESTDHANDLES while deliberately leaving hStd*
    # NULL so the pseudoconsole supplies its own handles.
    # https://github.com/microsoft/terminal/issues/11276#issuecomment-923207186
    startup.StartupInfo.hStdInput = wintypes.HANDLE()
    startup.StartupInfo.hStdOutput = wintypes.HANDLE()
    startup.StartupInfo.hStdError = wintypes.HANDLE()
    startup.StartupInfo.dwFlags |= _STARTF_USESTDHANDLES


class WindowsConPtyProcess:
    """Run one argv-defined Windows process inside a ConPTY.

    ``write`` only enqueues bytes; the potentially blocking ``WriteFile`` call
    runs on a worker thread.  ``read`` waits on an in-memory queue, never on the
    Win32 pipe itself.  This makes the public I/O methods safe to call from a
    GUI event loop when ``read(timeout=0)`` is used.
    """

    def __init__(
        self,
        argv: Sequence[str],
        *,
        cwd: str | os.PathLike[str] | None = None,
        columns: int = 120,
        rows: int = 30,
    ) -> None:
        self.argv = _validated_windows_argv(argv)
        self.command_line = subprocess.list2cmdline(self.argv)
        self.application_path: str | None = None
        self.cwd = _validate_cwd(cwd)
        self.columns = _validate_dimension(columns, "columns")
        self.rows = _validate_dimension(rows, "rows")

        self._api: _Kernel32Api | None = None
        self._pseudo_console = wintypes.HANDLE()
        self._process_handle = wintypes.HANDLE()
        self._input_write = wintypes.HANDLE()
        self._output_read = wintypes.HANDLE()
        self._pid: int | None = None
        self._returncode: int | None = None
        self._started = False
        self._closed = False

        self._lifecycle_lock = threading.RLock()
        self._read_lock = threading.Lock()
        self._io_error_lock = threading.Lock()
        self._io_error: ConPtyProcessError | None = None
        self._read_remainder = b""
        self._output_queue: queue.Queue[bytes | object] = queue.Queue(
            maxsize=_MAX_QUEUED_CHUNKS
        )
        self._write_queue: queue.Queue[bytes] = queue.Queue(
            maxsize=_MAX_QUEUED_CHUNKS
        )
        self._reader_thread: threading.Thread | None = None
        self._writer_thread: threading.Thread | None = None
        self._closer_thread: threading.Thread | None = None
        self._closing = threading.Event()
        self._input_closing = threading.Event()
        self._output_eof = threading.Event()
        self._pseudo_console_close_started = threading.Event()
        self._pseudo_console_closed = threading.Event()
        self.output_ready = threading.Event()
        self._output_activity = threading.Condition()
        self._last_output_activity = time.monotonic()
        self._write_condition = threading.Condition()
        self._pending_writes = 0

    @property
    def pid(self) -> int | None:
        return self._pid

    @property
    def started(self) -> bool:
        return self._started

    @property
    def closed(self) -> bool:
        return self._closed

    @property
    def output_eof(self) -> bool:
        return self._output_eof.is_set()

    @property
    def io_error(self) -> ConPtyProcessError | None:
        with self._io_error_lock:
            return self._io_error

    def start(self) -> None:
        """Create the pseudo-console and child process exactly once."""

        with self._lifecycle_lock:
            if self._closed:
                raise RuntimeError("ConPTY process is closed")
            if self._started:
                raise RuntimeError("ConPTY process has already been started")
            try:
                api = _Kernel32Api()
            except Exception:
                self._mark_start_failed()
                raise
            self._api = api
            try:
                self.application_path = _resolve_windows_executable(self.argv[0])
            except Exception:
                self._mark_start_failed()
                raise
            # Microsoft documents the ConPTY launch path with
            # lpApplicationName=NULL.  Resolve argv[0] ourselves, place that
            # absolute path in the safely quoted mutable command line, and let
            # CreateProcessW parse only this trusted first token.
            self.command_line = quote_windows_argv(
                (self.application_path, *self.argv[1:])
            )
            input_read = wintypes.HANDLE()
            input_write = wintypes.HANDLE()
            output_read = wintypes.HANDLE()
            output_write = wintypes.HANDLE()
            pseudo_console = wintypes.HANDLE()
            process_info = _PROCESS_INFORMATION()
            attribute_buffer = None
            attribute_list = wintypes.LPVOID()
            attribute_initialized = False
            try:
                if not api.CreatePipe(
                    ctypes.byref(input_read),
                    ctypes.byref(input_write),
                    None,
                    0,
                ):
                    raise _last_error("CreatePipe(stdin)")
                if not api.CreatePipe(
                    ctypes.byref(output_read),
                    ctypes.byref(output_write),
                    None,
                    0,
                ):
                    raise _last_error("CreatePipe(stdout)")

                hresult = api.CreatePseudoConsole(
                    _COORD(self.columns, self.rows),
                    input_read,
                    output_write,
                    0,
                    ctypes.byref(pseudo_console),
                )
                if hresult < 0:
                    raise _hresult_error("CreatePseudoConsole", hresult)

                attribute_size = ctypes.c_size_t()
                api.InitializeProcThreadAttributeList(
                    None,
                    1,
                    0,
                    ctypes.byref(attribute_size),
                )
                if not attribute_size.value:
                    raise _last_error("InitializeProcThreadAttributeList(size)")
                attribute_buffer = ctypes.create_string_buffer(attribute_size.value)
                attribute_list = ctypes.cast(attribute_buffer, wintypes.LPVOID)
                if not api.InitializeProcThreadAttributeList(
                    attribute_list,
                    1,
                    0,
                    ctypes.byref(attribute_size),
                ):
                    raise _last_error("InitializeProcThreadAttributeList")
                attribute_initialized = True
                if not api.UpdateProcThreadAttribute(
                    attribute_list,
                    0,
                    _PROC_THREAD_ATTRIBUTE_PSEUDOCONSOLE,
                    pseudo_console,
                    ctypes.sizeof(wintypes.HANDLE),
                    None,
                    None,
                ):
                    raise _last_error("UpdateProcThreadAttribute(ConPTY)")

                startup = _STARTUPINFOEXW()
                _configure_conpty_startup_info(startup)
                startup.lpAttributeList = attribute_list
                mutable_command_line = ctypes.create_unicode_buffer(self.command_line)
                if not api.CreateProcessW(
                    None,
                    mutable_command_line,
                    None,
                    None,
                    False,
                    _EXTENDED_STARTUPINFO_PRESENT,
                    None,
                    self.cwd,
                    ctypes.byref(startup.StartupInfo),
                    ctypes.byref(process_info),
                ):
                    raise _last_error("CreateProcessW")

                self._pseudo_console = pseudo_console
                pseudo_console = wintypes.HANDLE()
                self._process_handle = process_info.hProcess
                process_info.hProcess = wintypes.HANDLE()
                self._input_write = input_write
                input_write = wintypes.HANDLE()
                self._output_read = output_read
                output_read = wintypes.HANDLE()
                self._pid = int(process_info.dwProcessId)
                self._started = True
                self._last_output_activity = time.monotonic()
            except Exception:
                self._mark_start_failed()
                raise
            finally:
                if attribute_initialized:
                    api.DeleteProcThreadAttributeList(attribute_list)
                if _handle_is_open(process_info.hThread):
                    api.CloseHandle(process_info.hThread)
                if _handle_is_open(process_info.hProcess):
                    api.CloseHandle(process_info.hProcess)
                if _handle_is_open(input_read):
                    api.CloseHandle(input_read)
                if _handle_is_open(output_write):
                    api.CloseHandle(output_write)
                if _handle_is_open(input_write):
                    api.CloseHandle(input_write)
                if _handle_is_open(output_read):
                    api.CloseHandle(output_read)
                if _handle_is_open(pseudo_console):
                    api.ClosePseudoConsole(pseudo_console)
                # Keep the attribute-list backing allocation alive until after
                # DeleteProcThreadAttributeList and CreateProcessW have returned.
                del attribute_buffer

            self._reader_thread = threading.Thread(
                target=self._reader_main,
                name=f"ConPTY-reader-{self._pid}",
                daemon=True,
            )
            self._writer_thread = threading.Thread(
                target=self._writer_main,
                name=f"ConPTY-writer-{self._pid}",
                daemon=True,
            )
            self._reader_thread.start()
            self._writer_thread.start()

    def _mark_start_failed(self) -> None:
        """Expose one terminal state for every failure before worker startup."""

        self._api = None
        self._pid = None
        self._returncode = None
        self._started = False
        self._closed = True
        self._closing.set()
        self._input_closing.set()
        self._output_eof.set()
        self.output_ready.set()

    def _require_started(self) -> _Kernel32Api:
        if not self._started or self._api is None:
            raise RuntimeError("ConPTY process has not been started")
        return self._api

    def _record_io_error(self, error: ConPtyProcessError) -> None:
        if self._closing.is_set():
            return
        with self._io_error_lock:
            if self._io_error is None:
                self._io_error = error
        self.output_ready.set()
        with self._write_condition:
            self._write_condition.notify_all()

    def raise_for_io_error(self) -> None:
        error = self.io_error
        if error is not None:
            raise error

    def _reader_main(self) -> None:
        api = self._require_started()
        try:
            while not self._closing.is_set():
                buffer = ctypes.create_string_buffer(_MAX_PIPE_CHUNK)
                transferred = wintypes.DWORD()
                if not api.ReadFile(
                    self._output_read,
                    buffer,
                    len(buffer),
                    ctypes.byref(transferred),
                    None,
                ):
                    code = int(ctypes.get_last_error())
                    if code not in _PIPE_SHUTDOWN_ERRORS:
                        self._record_io_error(_last_error("ReadFile(ConPTY)"))
                    break
                if not transferred.value:
                    break
                payload = buffer.raw[: transferred.value]
                while not self._closing.is_set():
                    try:
                        self._output_queue.put(payload, timeout=0.1)
                    except queue.Full:
                        continue
                    self.output_ready.set()
                    with self._output_activity:
                        self._last_output_activity = time.monotonic()
                        self._output_activity.notify_all()
                    break
        finally:
            self._output_eof.set()
            self.output_ready.set()
            with self._output_activity:
                self._output_activity.notify_all()
            if not self._closing.is_set():
                try:
                    self._output_queue.put_nowait(_OUTPUT_EOF)
                except queue.Full:
                    pass

    def _writer_main(self) -> None:
        api = self._require_started()
        try:
            while not self._closing.is_set():
                try:
                    payload = self._write_queue.get(timeout=0.1)
                except queue.Empty:
                    if self._input_closing.is_set():
                        break
                    continue
                try:
                    self._write_all(api, payload)
                except ConPtyProcessError as exc:
                    self._record_io_error(exc)
                    self._input_closing.set()
                    break
                finally:
                    with self._write_condition:
                        self._pending_writes -= 1
                        self._write_condition.notify_all()
        finally:
            self._discard_queued_writes()
            self._close_input_handle()

    def _write_all(self, api: _Kernel32Api, payload: bytes) -> None:
        offset = 0
        while offset < len(payload) and not self._closing.is_set():
            chunk = payload[offset : offset + _MAX_PIPE_CHUNK]
            buffer = ctypes.create_string_buffer(chunk, len(chunk))
            transferred = wintypes.DWORD()
            if not api.WriteFile(
                self._input_write,
                buffer,
                len(chunk),
                ctypes.byref(transferred),
                None,
            ):
                code = int(ctypes.get_last_error())
                if code in _PIPE_SHUTDOWN_ERRORS:
                    raise ConPtyProcessError(
                        "WriteFile(ConPTY)",
                        code,
                        "the terminal input pipe is closed",
                    )
                raise _last_error("WriteFile(ConPTY)")
            if not transferred.value:
                raise ConPtyProcessError(
                    "WriteFile(ConPTY)",
                    0,
                    "the terminal accepted zero input bytes",
                )
            offset += int(transferred.value)

    def _discard_queued_writes(self) -> None:
        discarded = 0
        while True:
            try:
                self._write_queue.get_nowait()
            except queue.Empty:
                break
            discarded += 1
        if discarded:
            with self._write_condition:
                self._pending_writes = max(0, self._pending_writes - discarded)
                self._write_condition.notify_all()

    def write(self, data: bytes | bytearray | memoryview) -> int:
        """Queue terminal input without blocking on the Win32 pipe."""

        self._require_started()
        if self._closed or self._closing.is_set() or self._input_closing.is_set():
            raise BrokenPipeError("ConPTY input is closed")
        payload = bytes(data)
        if not payload:
            return 0
        self.raise_for_io_error()
        if self.poll() is not None:
            raise BrokenPipeError("ConPTY child process has exited")
        with self._write_condition:
            self._pending_writes += 1
        try:
            self._write_queue.put_nowait(payload)
        except queue.Full as exc:
            with self._write_condition:
                self._pending_writes -= 1
                self._write_condition.notify_all()
            raise BlockingIOError("ConPTY input queue is full") from exc
        return len(payload)

    def flush(self, timeout: float | None = None) -> None:
        """Wait until all input queued before this call has reached the pipe."""

        deadline = None if timeout is None else time.monotonic() + max(0.0, timeout)
        with self._write_condition:
            while self._pending_writes:
                self.raise_for_io_error()
                if deadline is None:
                    self._write_condition.wait()
                    continue
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    raise TimeoutError("timed out while flushing ConPTY input")
                self._write_condition.wait(remaining)
        self.raise_for_io_error()

    def close_input(self) -> None:
        """Close stdin after already queued writes have completed."""

        self._require_started()
        self._input_closing.set()

    def begin_output_shutdown(self) -> None:
        """Begin non-blocking pseudoconsole shutdown while output is drained.

        Call this after the root child exits.  On Windows releases before
        11 24H2, ``ClosePseudoConsole`` can wait indefinitely while clients
        emit their final frame.  It therefore runs on a dedicated thread while
        the reader thread remains active until the output pipe reaches EOF.
        Repeated calls are harmless.
        """

        api = self._require_started()
        with self._lifecycle_lock:
            if self._pseudo_console_close_started.is_set():
                return
            self._pseudo_console_close_started.set()
            if not _handle_is_open(self._pseudo_console):
                self._pseudo_console_closed.set()
                return
            # The child handle can signal before ConPTY has rendered output
            # already accepted from that process.  Start the quiet window at
            # this request, not at the last chunk observed before process exit.
            with self._output_activity:
                self._last_output_activity = time.monotonic()
                self._output_activity.notify_all()
            pseudo_console = self._pseudo_console
            self._pseudo_console = wintypes.HANDLE()
            closer = threading.Thread(
                target=self._close_pseudo_console_main,
                args=(api, pseudo_console),
                name=f"ConPTY-closer-{self._pid}",
                daemon=True,
            )
            self._closer_thread = closer
            try:
                closer.start()
            except Exception:
                self._closer_thread = None
                self._pseudo_console = pseudo_console
                self._pseudo_console_close_started.clear()
                raise

    def _close_pseudo_console_main(
        self,
        api: _Kernel32Api,
        pseudo_console: wintypes.HANDLE,
    ) -> None:
        try:
            self._wait_for_output_quiescence()
            api.ClosePseudoConsole(pseudo_console)
        finally:
            self._pseudo_console_closed.set()
            self.output_ready.set()

    def _wait_for_output_quiescence(self) -> None:
        """Give ConPTY a bounded window to render output queued by an exited child."""

        deadline = time.monotonic() + _OUTPUT_DRAIN_MAX_WAIT_SECONDS
        with self._output_activity:
            while not self._output_eof.is_set():
                now = time.monotonic()
                quiet_remaining = (
                    self._last_output_activity + _OUTPUT_DRAIN_QUIET_SECONDS - now
                )
                total_remaining = deadline - now
                if quiet_remaining <= 0 or total_remaining <= 0:
                    return
                self._output_activity.wait(min(quiet_remaining, total_remaining))

    def _close_input_handle(self) -> None:
        with self._lifecycle_lock:
            if self._api is not None and _handle_is_open(self._input_write):
                self._api.CloseHandle(self._input_write)
                self._input_write = wintypes.HANDLE()

    def read(self, max_bytes: int = _MAX_PIPE_CHUNK, timeout: float | None = None) -> bytes:
        """Read one output chunk.

        ``timeout=0`` is non-blocking.  An empty result means no data is
        currently available or EOF; inspect ``output_eof`` to distinguish them.
        """

        self._require_started()
        if isinstance(max_bytes, bool) or not isinstance(max_bytes, int):
            raise TypeError("max_bytes must be an integer")
        if max_bytes < 1:
            raise ValueError("max_bytes must be greater than zero")
        if timeout is not None and timeout < 0:
            raise ValueError("timeout must not be negative")
        with self._read_lock:
            if self._read_remainder:
                return self._take_remainder(max_bytes)
            if self._output_eof.is_set() and self._output_queue.empty():
                return b""
            try:
                item = self._output_queue.get(
                    block=timeout != 0,
                    timeout=timeout if timeout not in {None, 0} else None,
                )
            except queue.Empty:
                return b""
            if item is _OUTPUT_EOF:
                self._output_eof.set()
                return b""
            payload = bytes(item)
            if self._output_queue.empty():
                self.output_ready.clear()
                if self._output_eof.is_set():
                    self.output_ready.set()
            if len(payload) <= max_bytes:
                return payload
            self._read_remainder = payload[max_bytes:]
            return payload[:max_bytes]

    def _take_remainder(self, max_bytes: int) -> bytes:
        payload = self._read_remainder[:max_bytes]
        self._read_remainder = self._read_remainder[max_bytes:]
        return payload

    def read_all(self) -> bytes:
        """Return all output currently queued without waiting for more."""

        chunks: list[bytes] = []
        while True:
            chunk = self.read(timeout=0)
            if not chunk:
                break
            chunks.append(chunk)
        return b"".join(chunks)

    def resize(self, columns: int, rows: int) -> None:
        api = self._require_started()
        columns = _validate_dimension(columns, "columns")
        rows = _validate_dimension(rows, "rows")
        with self._lifecycle_lock:
            if self._closed or not _handle_is_open(self._pseudo_console):
                raise RuntimeError("ConPTY process is closed")
            hresult = api.ResizePseudoConsole(
                self._pseudo_console,
                _COORD(columns, rows),
            )
            if hresult < 0:
                raise _hresult_error("ResizePseudoConsole", hresult)
            self.columns = columns
            self.rows = rows

    def poll(self) -> int | None:
        api = self._require_started()
        if self._returncode is not None:
            return self._returncode
        if not _handle_is_open(self._process_handle):
            return self._returncode
        result = int(api.WaitForSingleObject(self._process_handle, 0))
        if result == _WAIT_TIMEOUT:
            return None
        if result == _WAIT_FAILED:
            raise _last_error("WaitForSingleObject")
        if result != _WAIT_OBJECT_0:
            raise ConPtyProcessError(
                "WaitForSingleObject",
                result,
                f"unexpected wait result 0x{result:08X}",
            )
        exit_code = wintypes.DWORD()
        if not api.GetExitCodeProcess(
            self._process_handle,
            ctypes.byref(exit_code),
        ):
            raise _last_error("GetExitCodeProcess")
        self._returncode = int(exit_code.value)
        return self._returncode

    def wait(self, timeout: float | None = None) -> int:
        api = self._require_started()
        if timeout is not None and timeout < 0:
            raise ValueError("timeout must not be negative")
        if self._returncode is not None:
            return self._returncode
        milliseconds = (
            _INFINITE
            if timeout is None
            else min(0xFFFFFFFE, max(0, math.ceil(timeout * 1000)))
        )
        result = int(api.WaitForSingleObject(self._process_handle, milliseconds))
        if result == _WAIT_TIMEOUT:
            raise subprocess.TimeoutExpired(self.argv, timeout)
        if result == _WAIT_FAILED:
            raise _last_error("WaitForSingleObject")
        if result != _WAIT_OBJECT_0:
            raise ConPtyProcessError(
                "WaitForSingleObject",
                result,
                f"unexpected wait result 0x{result:08X}",
            )
        returncode = self.poll()
        if returncode is None:
            raise ConPtyProcessError(
                "GetExitCodeProcess",
                0,
                "the signaled process did not expose an exit code",
            )
        return returncode

    def terminate(self) -> None:
        """Terminate the child process with a conventional failure status."""

        self._terminate_with_code(1)

    def kill(self) -> None:
        """Force termination of the child process."""

        self._terminate_with_code(137)

    def _terminate_with_code(self, exit_code: int) -> None:
        api = self._require_started()
        with self._lifecycle_lock:
            if self.poll() is not None:
                return
            if not api.TerminateProcess(self._process_handle, exit_code):
                raise _last_error("TerminateProcess")

    def close(self, *, terminate: bool = True, timeout: float = 1.0) -> None:
        """Release process, pipe, thread, and pseudo-console resources."""

        with self._lifecycle_lock:
            if self._closed:
                return
            if not self._started:
                self._closed = True
                return
        if terminate and self.poll() is None:
            try:
                self.terminate()
                self.wait(timeout=timeout)
            except (ConPtyProcessError, subprocess.TimeoutExpired):
                try:
                    self.kill()
                    self.wait(timeout=timeout)
                except (ConPtyProcessError, subprocess.TimeoutExpired):
                    pass

        try:
            self.flush(timeout=timeout)
        except (ConPtyProcessError, TimeoutError):
            pass

        # Keep the reader servicing final ConPTY frames while the closer runs.
        # Before Windows 11 24H2 ClosePseudoConsole may block until clients
        # disconnect; stopping the reader first can deadlock a full output pipe.
        self.begin_output_shutdown()
        reader = self._reader_thread
        if reader is not None and reader is not threading.current_thread():
            reader.join(timeout=max(0.0, timeout))
        closer = self._closer_thread
        if closer is not None and closer is not threading.current_thread():
            closer.join(timeout=max(0.0, timeout))

        self._input_closing.set()
        self._closing.set()
        self._close_input_handle()
        with self._lifecycle_lock:
            api = self._api
            # If EOF did not arrive in time, closing our output side satisfies
            # the documented pre-24H2 escape hatch and lets the closer finish.
            if api is not None and _handle_is_open(self._output_read):
                api.CloseHandle(self._output_read)
                self._output_read = wintypes.HANDLE()

        for thread in (self._writer_thread, self._reader_thread, self._closer_thread):
            if thread is not None and thread is not threading.current_thread():
                thread.join(timeout=max(0.0, timeout))

        with self._lifecycle_lock:
            if self._api is not None and _handle_is_open(self._process_handle):
                self._api.CloseHandle(self._process_handle)
                self._process_handle = wintypes.HANDLE()
            self._closed = True
            self._output_eof.set()
            self.output_ready.set()

    def __enter__(self) -> WindowsConPtyProcess:
        self.start()
        return self

    def __exit__(self, _exc_type, _exc, _traceback) -> None:
        self.close()


__all__ = [
    "MINIMUM_CONPTY_BUILD",
    "ConPtyProcessError",
    "ConPtySupport",
    "ConPtyUnavailableError",
    "WindowsConPtyProcess",
    "conpty_support",
    "quote_windows_argv",
    "require_conpty_support",
]

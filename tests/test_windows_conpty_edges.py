from __future__ import annotations

import ctypes
import os
import queue
import subprocess
import threading
import time
from ctypes import wintypes
from pathlib import Path
from types import SimpleNamespace

import pytest

from remote_ops_workspace import windows_conpty as conpty


def _error(operation: str = "operation", code: int = 5) -> conpty.ConPtyProcessError:
    return conpty.ConPtyProcessError(operation, code, "controlled failure")


def _started_process(api: object | None = None) -> conpty.WindowsConPtyProcess:
    process = conpty.WindowsConPtyProcess(["cmd.exe"])
    process._api = api or SimpleNamespace()
    process._started = True
    process._pid = 42
    process._process_handle = wintypes.HANDLE(101)
    process._pseudo_console = wintypes.HANDLE(102)
    process._input_write = wintypes.HANDLE(103)
    process._output_read = wintypes.HANDLE(104)
    return process


def test_ctypes_support_detection_and_error_objects(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(conpty.ConPtyUnavailableError, match="ctypes.missing"):
        conpty._windows_ctypes_member("missing")

    process_error = _error("ReadFile", 6)
    assert process_error.operation == "ReadFile"
    assert process_error.error_code == 6
    assert "ReadFile" in str(process_error)

    monkeypatch.setattr(conpty, "_running_on_windows", lambda: False)
    assert conpty._windows_build_number() is None
    assert conpty._conpty_exports_available() is False

    monkeypatch.setattr(conpty, "_running_on_windows", lambda: True)
    monkeypatch.setattr(
        conpty.sys,
        "getwindowsversion",
        lambda: SimpleNamespace(build=26100),
        raising=False,
    )
    assert conpty._windows_build_number() == 26100

    monkeypatch.setattr(
        conpty.ctypes,
        "WinDLL",
        lambda *_args, **_kwargs: _raise(OSError("missing DLL")),
        raising=False,
    )
    assert conpty._conpty_exports_available() is False

    exports = {
        name: object()
        for name in (
            "CreatePseudoConsole",
            "ResizePseudoConsole",
            "ClosePseudoConsole",
            "InitializeProcThreadAttributeList",
            "UpdateProcThreadAttribute",
        )
    }
    monkeypatch.setattr(conpty.ctypes, "WinDLL", lambda *_args, **_kwargs: SimpleNamespace(**exports))
    assert conpty._conpty_exports_available() is True
    del exports["ResizePseudoConsole"]
    monkeypatch.setattr(conpty.ctypes, "WinDLL", lambda *_args, **_kwargs: SimpleNamespace(**exports))
    assert conpty._conpty_exports_available() is False


def test_conpty_support_handles_unknown_and_supported_builds(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(conpty, "_running_on_windows", lambda: True)
    monkeypatch.setattr(conpty, "_windows_build_number", lambda: None)
    unknown = conpty.conpty_support()
    assert unknown.supported is False
    assert "build number is unavailable" in unknown.reason

    monkeypatch.setattr(conpty, "_windows_build_number", lambda: 26100)
    monkeypatch.setattr(conpty, "_conpty_exports_available", lambda: True)
    supported = conpty.conpty_support()
    assert supported.supported is True
    assert conpty.require_conpty_support() == supported


def test_argument_cwd_and_dimension_edge_validation(tmp_path: Path) -> None:
    class NotIterable:
        def __iter__(self):
            raise TypeError("not iterable")

    with pytest.raises(ValueError, match="non-empty sequence"):
        conpty._validated_windows_argv(NotIterable())  # type: ignore[arg-type]

    class BytesPath:
        def __fspath__(self) -> bytes:
            return b"path"

    with pytest.raises(TypeError, match="resolve to text"):
        conpty._validate_cwd(BytesPath())

    assert conpty._validate_cwd(tmp_path) == str(tmp_path)
    assert conpty._validate_dimension(80, "columns") == 80


def test_explicit_executable_resolution_and_public_wrapper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("PATHEXT", ".EXE")
    executable = tmp_path / "bin" / "tool.EXE"
    executable.parent.mkdir()
    executable.write_bytes(b"tool")

    assert Path(conpty.resolve_windows_executable("bin/tool")) == executable.resolve()
    assert Path(conpty._resolve_windows_executable(str(executable))) == executable.resolve()
    with pytest.raises(FileNotFoundError, match="was not found"):
        conpty._resolve_windows_executable("bin/missing")


def test_bare_executable_resolution_reports_missing_and_skips_untrusted_entries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    cwd = tmp_path / "cwd"
    cwd.mkdir()
    relative = Path("relative-bin")
    monkeypatch.chdir(cwd)
    monkeypatch.setenv("PATH", os.pathsep.join(("", str(relative), str(cwd))))
    monkeypatch.setattr(conpty, "_windows_system_directories", lambda: ())

    assert conpty._resolve_from_absolute_windows_path("missing.exe") is None
    with pytest.raises(FileNotFoundError, match="not found on PATH"):
        conpty._resolve_windows_executable("missing.exe")


def test_trusted_openssh_falls_through_to_path_after_system_miss(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    missing_system = tmp_path / "Windows" / "System32"
    path_dir = tmp_path / "bin"
    path_dir.mkdir()
    expected = path_dir / "ssh.exe"
    expected.write_bytes(b"ssh")
    monkeypatch.setenv("PATH", str(path_dir))
    monkeypatch.setattr(conpty, "_windows_system_directories", lambda: (missing_system,))

    assert Path(conpty._resolve_windows_executable("ssh.exe")) == expected.resolve()


def test_path_resolution_skips_directories_that_cannot_resolve(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    bad = tmp_path / "bad"
    bad.mkdir()
    original_resolve = Path.resolve

    def resolve(path: Path, *args: object, **kwargs: object) -> Path:
        if path == bad:
            raise OSError("unresolvable")
        return original_resolve(path, *args, **kwargs)

    monkeypatch.setattr(Path, "resolve", resolve)
    monkeypatch.setenv("PATH", str(bad))
    assert conpty._resolve_from_absolute_windows_path("missing.exe") is None


def test_windows_system_directories_cover_api_and_environment_fallback(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    windows = tmp_path / "Windows"
    system = windows / "System32"
    monkeypatch.setenv("PROCESSOR_ARCHITEW6432", "AMD64")
    monkeypatch.setattr(
        conpty,
        "_windows_directory_from_api",
        lambda export: windows if export == "GetWindowsDirectoryW" else system,
    )
    directories = conpty._windows_system_directories()
    assert directories == (windows / "Sysnative", system)

    monkeypatch.delenv("PROCESSOR_ARCHITEW6432", raising=False)
    monkeypatch.setenv("SystemRoot", str(windows))
    monkeypatch.setattr(conpty, "_windows_directory_from_api", lambda _export: None)
    assert conpty._windows_system_directories() == (system,)

    monkeypatch.delenv("SystemRoot")
    monkeypatch.delenv("WINDIR", raising=False)
    assert conpty._windows_system_directories() == ()


def test_windows_directory_api_success_failure_and_invalid_length(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(conpty, "_running_on_windows", lambda: False)
    assert conpty._windows_directory_from_api("GetWindowsDirectoryW") is None

    monkeypatch.setattr(conpty, "_running_on_windows", lambda: True)
    monkeypatch.setattr(
        conpty.ctypes,
        "WinDLL",
        lambda *_args, **_kwargs: SimpleNamespace(),
        raising=False,
    )
    assert conpty._windows_directory_from_api("missing") is None

    class DirectoryCall:
        argtypes = None
        restype = None

        def __init__(self, value: str, length: int | None = None) -> None:
            self.value = value
            self.length = length

        def __call__(self, buffer, _size: int) -> int:
            buffer.value = self.value
            return len(self.value) if self.length is None else self.length

    target = str(tmp_path / "Windows")
    call = DirectoryCall(target)
    monkeypatch.setattr(conpty.ctypes, "WinDLL", lambda *_args, **_kwargs: SimpleNamespace(GetWindowsDirectoryW=call))
    assert conpty._windows_directory_from_api("GetWindowsDirectoryW") == Path(target)

    call.length = 0
    assert conpty._windows_directory_from_api("GetWindowsDirectoryW") is None


def test_windows_executable_extension_contract(monkeypatch: pytest.MonkeyPatch) -> None:
    assert conpty._windows_executable_extensions("tool.exe") == ("",)
    monkeypatch.setenv("PATHEXT", "EXE;.CMD;")
    assert conpty._windows_executable_extensions("tool") == ("", ".EXE", ".CMD")


def test_win32_and_hresult_error_formatting(monkeypatch: pytest.MonkeyPatch) -> None:
    members = {
        "get_last_error": lambda: 5,
        "WinError": lambda code: SimpleNamespace(strerror=f"message {code}"),
    }
    monkeypatch.setattr(conpty, "_windows_ctypes_member", lambda name: members[name])
    last = conpty._last_error("CreatePipe")
    assert last.error_code == 5
    assert "message 5" in str(last)

    hresult = conpty._hresult_error("CreatePseudoConsole", -2147024891)
    assert hresult.error_code == 5
    assert "HRESULT" in str(hresult)

    members["WinError"] = lambda _code: _raise(OSError("format failed"))
    assert "Win32 error 5" in str(conpty._last_error("CreatePipe"))
    assert "HRESULT 0xFFFFFFFF" in str(conpty._hresult_error("CreatePseudoConsole", -1))


def test_start_rejects_duplicate_start(monkeypatch: pytest.MonkeyPatch) -> None:
    process = _started_process()
    with pytest.raises(RuntimeError, match="already been started"):
        process.start()


@pytest.mark.parametrize(
    "failure",
    [
        "stdin-pipe",
        "stdout-pipe",
        "pseudoconsole",
        "attribute-size",
        "attribute-init",
        "attribute-update",
        "create-process",
    ],
)
def test_start_cleans_up_every_native_failure_stage(
    failure: str,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _StartApi(failure)
    monkeypatch.setattr(conpty, "_Kernel32Api", lambda: api)
    monkeypatch.setattr(conpty, "_resolve_windows_executable", lambda _value: "C:/Windows/System32/cmd.exe")
    monkeypatch.setattr(conpty, "_last_error", lambda operation: _error(operation))
    monkeypatch.setattr(conpty, "_hresult_error", lambda operation, _value: _error(operation))
    process = conpty.WindowsConPtyProcess(["cmd.exe"])

    with pytest.raises(conpty.ConPtyProcessError):
        process.start()

    assert process.closed is True
    assert process.started is False


def test_recorded_errors_are_sticky_and_ignored_during_shutdown() -> None:
    process = conpty.WindowsConPtyProcess(["cmd.exe"])
    first = _error("first")
    second = _error("second")
    process._record_io_error(first)
    process._record_io_error(second)
    assert process.io_error is first
    with pytest.raises(conpty.ConPtyProcessError):
        process.raise_for_io_error()

    process._closing.set()
    process._record_io_error(second)
    process._record_resize_error(second)
    assert process.io_error is first
    assert process.take_resize_error() is None

    process._closing.clear()
    process._resize_closing.clear()
    process._record_resize_error(first)
    assert process.take_resize_error() is first
    assert process.take_resize_error() is None


def test_reader_delivers_payload_and_reports_pipe_errors(monkeypatch: pytest.MonkeyPatch) -> None:
    api = _ReadApi([b"payload", 5])
    process = _started_process(api)
    monkeypatch.setattr(conpty, "_windows_ctypes_member", lambda _name: lambda: api.error_code)
    monkeypatch.setattr(conpty, "_last_error", lambda operation: _error(operation, api.error_code))

    process._reader_main()

    assert process.read(timeout=0) == b"payload"
    assert process.output_eof is True
    assert process.io_error is not None

    shutdown_api = _ReadApi([conpty._ERROR_BROKEN_PIPE])
    shutdown = _started_process(shutdown_api)
    monkeypatch.setattr(conpty, "_windows_ctypes_member", lambda _name: lambda: shutdown_api.error_code)
    shutdown._reader_main()
    assert shutdown.io_error is None


def test_reader_handles_zero_length_and_full_queues(monkeypatch: pytest.MonkeyPatch) -> None:
    zero = _started_process(_ReadApi([b""]))
    zero._reader_main()
    assert zero.output_eof is True

    class FullThenAcceptQueue:
        def __init__(self) -> None:
            self.put_calls = 0

        def put(self, _payload: bytes, timeout: float) -> None:
            self.put_calls += 1
            if self.put_calls == 1:
                raise queue.Full

        def put_nowait(self, _payload: object) -> None:
            raise queue.Full

    api = _ReadApi([b"payload", conpty._ERROR_BROKEN_PIPE])
    process = _started_process(api)
    fake_queue = FullThenAcceptQueue()
    process._output_queue = fake_queue  # type: ignore[assignment]
    monkeypatch.setattr(conpty, "_windows_ctypes_member", lambda _name: lambda: api.error_code)
    process._reader_main()
    assert fake_queue.put_calls == 2

    class ClosingFullQueue:
        def put(self, _payload: bytes, timeout: float) -> None:
            closing._closing.set()
            raise queue.Full

        def put_nowait(self, _payload: object) -> None:
            return None

    closing = _started_process(_ReadApi([b"payload"]))
    closing._output_queue = ClosingFullQueue()  # type: ignore[assignment]
    closing._reader_main()
    assert closing.output_eof is True


def test_write_all_reports_closed_unknown_and_zero_byte_writes(monkeypatch: pytest.MonkeyPatch) -> None:
    process = _started_process()

    for code, expected in ((conpty._ERROR_BROKEN_PIPE, "input pipe is closed"), (5, "controlled")):
        api = _WriteApi(result=False, error_code=code)
        monkeypatch.setattr(conpty, "_windows_ctypes_member", lambda _name, api=api: lambda: api.error_code)
        monkeypatch.setattr(conpty, "_last_error", lambda operation: _error(operation))
        with pytest.raises(conpty.ConPtyProcessError, match=expected):
            process._write_all(api, b"payload")  # type: ignore[arg-type]

    with pytest.raises(conpty.ConPtyProcessError, match="zero input bytes"):
        process._write_all(_WriteApi(result=True, transferred=0), b"payload")  # type: ignore[arg-type]


def test_writer_records_errors_discards_queue_and_closes_input() -> None:
    class Api:
        def CloseHandle(self, _handle) -> bool:
            return True

        def WriteFile(self, _handle, _buffer, size, transferred_pointer, _overlapped) -> bool:
            transferred_pointer._obj.value = size
            return True

    process = _started_process(Api())
    process._write_queue.put_nowait(b"payload")
    process._pending_writes = 1
    process._input_closing.set()
    process._writer_main()
    assert process._pending_writes == 0
    assert not conpty._handle_is_open(process._input_write)

    process = _started_process(Api())
    process._write_queue.put_nowait(b"one")
    process._write_queue.put_nowait(b"two")
    process._pending_writes = 2
    process._discard_queued_writes()
    assert process._pending_writes == 0


def test_writer_records_pipe_error_and_workers_honor_closing(monkeypatch: pytest.MonkeyPatch) -> None:
    api = _WriteApi(result=False, error_code=5)
    api.CloseHandle = lambda _handle: True  # type: ignore[attr-defined]
    process = _started_process(api)
    process._write_queue.put_nowait(b"payload")
    process._pending_writes = 1
    monkeypatch.setattr(conpty, "_windows_ctypes_member", lambda _name: lambda: 5)
    monkeypatch.setattr(conpty, "_last_error", lambda operation: _error(operation))

    process._writer_main()

    assert process.io_error is not None
    assert process._input_closing.is_set()
    assert process._pending_writes == 0

    reader = _started_process(_ReadApi([]))
    reader._closing.set()
    reader._reader_main()
    assert reader.output_eof is True

    writer = _started_process(SimpleNamespace(CloseHandle=lambda _handle: True))
    writer._closing.set()
    writer._writer_main()


def test_write_handles_closed_empty_exited_error_and_backpressure(monkeypatch: pytest.MonkeyPatch) -> None:
    process = _started_process()
    process._closed = True
    with pytest.raises(BrokenPipeError, match="input is closed"):
        process.write(b"x")

    process._closed = False
    monkeypatch.setattr(process, "poll", lambda: None)
    assert process.write(b"") == 0

    process._io_error = _error("write")
    with pytest.raises(conpty.ConPtyProcessError):
        process.write(b"x")
    process._io_error = None

    monkeypatch.setattr(process, "poll", lambda: 0)
    with pytest.raises(BrokenPipeError, match="has exited"):
        process.write(b"x")

    monkeypatch.setattr(process, "poll", lambda: None)
    process._write_queue = queue.Queue(maxsize=1)
    process._write_queue.put_nowait(b"existing")
    with pytest.raises(BlockingIOError, match="queue is full"):
        process.write(b"new")
    assert process._pending_writes == 0


def test_flush_timeout_unbounded_wait_and_final_error() -> None:
    process = _started_process()
    process._pending_writes = 1
    with pytest.raises(TimeoutError, match="timed out"):
        process.flush(timeout=0)

    process._pending_writes = 1

    def complete_write() -> None:
        time.sleep(0.02)
        with process._write_condition:
            process._pending_writes = 0
            process._write_condition.notify_all()

    worker = threading.Thread(target=complete_write)
    worker.start()
    process.flush(timeout=None)
    worker.join()

    process._io_error = _error("flush")
    with pytest.raises(conpty.ConPtyProcessError):
        process.flush()


def test_close_input_output_shutdown_and_resize_guards(monkeypatch: pytest.MonkeyPatch) -> None:
    process = _started_process()
    process.close_input()
    assert process._input_closing.is_set()

    process._pseudo_console = wintypes.HANDLE()
    process.begin_output_shutdown()
    assert process._pseudo_console_closed.is_set()
    process.begin_output_shutdown()

    closed = _started_process()
    closed._closed = True
    with pytest.raises(RuntimeError, match="closed"):
        closed.resize(80, 24)

    resizing = _started_process(SimpleNamespace())
    resizing._pending_resize = (80, 24)
    resizing._resize_event.set()
    resizing._closed = True
    resizing._resize_main()

    failing = _started_process()

    class FailingThread:
        def __init__(self, **_kwargs: object) -> None:
            pass

        def start(self) -> None:
            raise RuntimeError("thread failed")

    monkeypatch.setattr(conpty.threading, "Thread", FailingThread)
    with pytest.raises(RuntimeError, match="thread failed"):
        failing.begin_output_shutdown()
    assert conpty._handle_is_open(failing._pseudo_console)
    assert failing._pseudo_console_close_started.is_set() is False


def test_output_quiescence_and_closer_signal() -> None:
    process = _started_process()
    process._output_eof.set()
    process._wait_for_output_quiescence()

    process._output_eof.clear()
    process._last_output_activity = time.monotonic() - 10
    process._wait_for_output_quiescence()

    closed: list[int] = []
    api = SimpleNamespace(ClosePseudoConsole=lambda handle: closed.append(int(handle.value)))
    process._output_eof.set()
    process._close_pseudo_console_main(api, wintypes.HANDLE(44))  # type: ignore[arg-type]
    assert closed == [44]
    assert process._pseudo_console_closed.is_set()


def test_read_validates_shapes_queue_payloads_and_remainders() -> None:
    process = _started_process()
    with pytest.raises(TypeError, match="max_bytes"):
        process.read(True)
    with pytest.raises(ValueError, match="greater than zero"):
        process.read(0)
    with pytest.raises(ValueError, match="must not be negative"):
        process.read(timeout=-1)

    process._read_remainder = b"abcdef"
    assert process.read(2, timeout=0) == b"ab"
    assert process.read(8, timeout=0) == b"cdef"

    assert process.read(timeout=0) == b""
    process._output_queue.put_nowait(conpty._OUTPUT_EOF)
    assert process.read(timeout=0) == b""

    process._output_eof.clear()
    process._output_queue.put_nowait(object())
    with pytest.raises(conpty.ConPtyProcessError, match="invalid payload"):
        process.read(timeout=0)

    process._output_queue.put_nowait(b"abcdefgh")
    assert process.read(3, timeout=0) == b"abc"
    assert process.read_all() == b"defgh"

    process._output_queue.put_nowait(b"final")
    process._output_eof.set()
    assert process.read(timeout=0) == b"final"
    assert process.output_ready.is_set()


@pytest.mark.parametrize(
    ("result", "exit_ok", "expected"),
    [
        (conpty._WAIT_TIMEOUT, True, None),
        (0x55, True, conpty.ConPtyProcessError),
        (conpty._WAIT_OBJECT_0, False, conpty.ConPtyProcessError),
        (conpty._WAIT_OBJECT_0, True, 7),
    ],
)
def test_poll_wait_results(
    result: int,
    exit_ok: bool,
    expected: int | None | type[Exception],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    api = _WaitApi(result=result, exit_ok=exit_ok, exit_code=7)
    process = _started_process(api)
    monkeypatch.setattr(conpty, "_last_error", lambda operation: _error(operation))

    if isinstance(expected, type):
        with pytest.raises(expected):
            process.poll()
    else:
        assert process.poll() == expected


def test_poll_cached_closed_and_wait_failed(monkeypatch: pytest.MonkeyPatch) -> None:
    process = _started_process(_WaitApi(result=conpty._WAIT_TIMEOUT))
    process._returncode = 3
    assert process.poll() == 3

    process._returncode = None
    process._process_handle = wintypes.HANDLE()
    assert process.poll() is None

    process._process_handle = wintypes.HANDLE(1)
    process._api = _WaitApi(result=conpty._WAIT_FAILED)
    monkeypatch.setattr(conpty, "_last_error", lambda operation: _error(operation))
    with pytest.raises(conpty.ConPtyProcessError):
        process.poll()


def test_wait_validation_timeout_errors_and_missing_exit_code(monkeypatch: pytest.MonkeyPatch) -> None:
    process = _started_process(_WaitApi(result=conpty._WAIT_TIMEOUT))
    with pytest.raises(ValueError, match="must not be negative"):
        process.wait(-1)
    with pytest.raises(subprocess.TimeoutExpired):
        process.wait(0.1)
    with pytest.raises(conpty.ConPtyProcessError, match="infinite wait timed out"):
        process.wait(None)

    process._api = _WaitApi(result=conpty._WAIT_FAILED)
    monkeypatch.setattr(conpty, "_last_error", lambda operation: _error(operation))
    with pytest.raises(conpty.ConPtyProcessError):
        process.wait(1)

    process._api = _WaitApi(result=0x55)
    with pytest.raises(conpty.ConPtyProcessError, match="unexpected wait result"):
        process.wait(1)

    process._api = _WaitApi(result=conpty._WAIT_OBJECT_0)
    monkeypatch.setattr(process, "poll", lambda: None)
    with pytest.raises(conpty.ConPtyProcessError, match="did not expose"):
        process.wait(1)

    process._returncode = 9
    assert process.wait() == 9


def test_terminate_kill_and_close_short_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    process = _started_process(_WaitApi(result=conpty._WAIT_TIMEOUT, terminate_ok=False))
    monkeypatch.setattr(process, "poll", lambda: 0)
    process._terminate_with_code(1)

    monkeypatch.setattr(process, "poll", lambda: None)
    monkeypatch.setattr(conpty, "_last_error", lambda operation: _error(operation))
    with pytest.raises(conpty.ConPtyProcessError):
        process._terminate_with_code(1)

    codes: list[int] = []
    monkeypatch.setattr(process, "_terminate_with_code", codes.append)
    process.terminate()
    process.kill()
    assert codes == [1, 137]

    process._closed = True
    process.close()

    never_started = conpty.WindowsConPtyProcess(["cmd.exe"])
    never_started.close()
    assert never_started.closed is True


def test_close_waits_after_terminate_falls_back_to_kill_and_ignores_flush_errors(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class Api:
        def CloseHandle(self, _handle) -> bool:
            return True

    process = _started_process(Api())
    process._pseudo_console = wintypes.HANDLE()
    process._output_read = wintypes.HANDLE()
    monkeypatch.setattr(process, "poll", lambda: None)
    actions: list[str] = []
    monkeypatch.setattr(process, "terminate", lambda: actions.append("terminate"))
    monkeypatch.setattr(process, "wait", lambda timeout=None: actions.append("wait") or 0)
    monkeypatch.setattr(process, "flush", lambda timeout=None: _raise(TimeoutError("flush")))
    process.close(timeout=0)
    assert actions == ["terminate", "wait"]

    fallback = _started_process(Api())
    fallback._pseudo_console = wintypes.HANDLE()
    fallback._output_read = wintypes.HANDLE()
    monkeypatch.setattr(fallback, "poll", lambda: None)
    fallback_actions: list[str] = []
    monkeypatch.setattr(fallback, "terminate", lambda: _raise(_error("terminate")))
    monkeypatch.setattr(fallback, "kill", lambda: fallback_actions.append("kill"))
    monkeypatch.setattr(fallback, "wait", lambda timeout=None: fallback_actions.append("wait") or 0)
    monkeypatch.setattr(fallback, "flush", lambda timeout=None: None)
    fallback.close(timeout=0)
    assert fallback_actions == ["kill", "wait"]

    api_missing = _started_process()
    api_missing._api = None
    api_missing._pseudo_console = wintypes.HANDLE()
    monkeypatch.setattr(api_missing, "poll", lambda: 0)
    monkeypatch.setattr(api_missing, "flush", lambda timeout=None: None)
    monkeypatch.setattr(api_missing, "begin_output_shutdown", lambda: None)
    monkeypatch.setattr(api_missing, "_close_input_handle", lambda: None)
    api_missing.close(timeout=0)
    assert api_missing.closed is True


def test_context_manager_starts_and_closes(monkeypatch: pytest.MonkeyPatch) -> None:
    process = conpty.WindowsConPtyProcess(["cmd.exe"])
    events: list[str] = []
    monkeypatch.setattr(process, "start", lambda: events.append("start"))
    monkeypatch.setattr(process, "close", lambda: events.append("close"))

    with process as entered:
        assert entered is process

    assert events == ["start", "close"]


class _StartApi:
    def __init__(self, failure: str) -> None:
        self.failure = failure
        self.pipe_calls = 0
        self.closed: list[int] = []

    def CreatePipe(self, read_pointer, write_pointer, _attributes, _size) -> bool:
        self.pipe_calls += 1
        stage = "stdin-pipe" if self.pipe_calls == 1 else "stdout-pipe"
        if self.failure == stage:
            return False
        read_pointer._obj.value = 10 + self.pipe_calls * 2
        write_pointer._obj.value = 11 + self.pipe_calls * 2
        return True

    def CreatePseudoConsole(self, _size, _input, _output, _flags, pointer) -> int:
        pointer._obj.value = 20
        return -1 if self.failure == "pseudoconsole" else 0

    def InitializeProcThreadAttributeList(self, target, _count, _flags, size_pointer) -> bool:
        if target is None:
            size_pointer._obj.value = 0 if self.failure == "attribute-size" else 16
            return False
        return self.failure != "attribute-init"

    def UpdateProcThreadAttribute(self, *_args) -> bool:
        return self.failure != "attribute-update"

    def CreateProcessW(self, *_args) -> bool:
        process_pointer = _args[-1]
        process_pointer._obj.hProcess = wintypes.HANDLE(30)
        process_pointer._obj.hThread = wintypes.HANDLE(31)
        process_pointer._obj.dwProcessId = 32
        return self.failure != "create-process"

    def DeleteProcThreadAttributeList(self, _target) -> None:
        return None

    def CloseHandle(self, handle) -> bool:
        self.closed.append(int(getattr(handle, "value", handle)))
        return True

    def ClosePseudoConsole(self, handle) -> None:
        self.closed.append(int(handle.value))


class _ReadApi:
    def __init__(self, outcomes: list[bytes | int]) -> None:
        self.outcomes = outcomes
        self.error_code = 0

    def ReadFile(self, _handle, buffer, _size, transferred_pointer, _overlapped) -> bool:
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, int):
            self.error_code = outcome
            return False
        transferred_pointer._obj.value = len(outcome)
        if outcome:
            ctypes.memmove(buffer, outcome, len(outcome))
        return True


class _WriteApi:
    def __init__(self, *, result: bool, transferred: int = 1, error_code: int = 0) -> None:
        self.result = result
        self.transferred = transferred
        self.error_code = error_code

    def WriteFile(self, _handle, _buffer, _size, transferred_pointer, _overlapped) -> bool:
        transferred_pointer._obj.value = self.transferred
        return self.result


class _WaitApi:
    def __init__(
        self,
        *,
        result: int,
        exit_ok: bool = True,
        exit_code: int = 0,
        terminate_ok: bool = True,
    ) -> None:
        self.result = result
        self.exit_ok = exit_ok
        self.exit_code = exit_code
        self.terminate_ok = terminate_ok

    def WaitForSingleObject(self, _handle, _milliseconds) -> int:
        return self.result

    def GetExitCodeProcess(self, _handle, pointer) -> bool:
        pointer._obj.value = self.exit_code
        return self.exit_ok

    def TerminateProcess(self, _handle, _exit_code) -> bool:
        return self.terminate_ok


def _raise(error: BaseException):
    raise error

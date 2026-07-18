from __future__ import annotations

import ctypes
import os
import subprocess
import sys
import threading
import time
from ctypes import wintypes

import pytest

from remote_ops_workspace import windows_conpty
from remote_ops_workspace.windows_conpty import (
    MINIMUM_CONPTY_BUILD,
    ConPtyUnavailableError,
    WindowsConPtyProcess,
    conpty_support,
    quote_windows_argv,
    require_conpty_support,
)


def test_quote_windows_argv_preserves_argument_boundaries() -> None:
    argv = [
        r"C:\Program Files\Remote Ops\row.exe",
        "plain",
        "two words",
        'embedded"quote',
        "trailing\\",
        "",
    ]

    assert quote_windows_argv(argv) == subprocess.list2cmdline(argv)


@pytest.mark.parametrize(
    "argv, error",
    [
        ([], "non-empty"),
        ("ssh host", "non-empty"),
        ([""], r"argv\[0\]"),
        (["ssh", "bad\x00value"], "NUL"),
    ],
)
def test_quote_windows_argv_rejects_ambiguous_or_invalid_input(
    argv,
    error: str,
) -> None:
    with pytest.raises(ValueError, match=error):
        quote_windows_argv(argv)


def test_quote_windows_argv_rejects_non_text_arguments() -> None:
    with pytest.raises(TypeError, match=r"argv\[1\]"):
        quote_windows_argv(["ssh", 22])  # type: ignore[list-item]


@pytest.mark.parametrize("argv", ["cmd.exe", b"cmd.exe"])
def test_constructor_rejects_scalar_argv_before_tuple_conversion(argv) -> None:
    with pytest.raises(ValueError, match="non-empty sequence"):
        WindowsConPtyProcess(argv)  # type: ignore[arg-type]


def test_conpty_startup_explicitly_blocks_redirected_parent_handles() -> None:
    startup = windows_conpty._STARTUPINFOEXW()

    windows_conpty._configure_conpty_startup_info(startup)

    assert startup.StartupInfo.cb == ctypes.sizeof(windows_conpty._STARTUPINFOEXW)
    assert startup.StartupInfo.dwFlags & windows_conpty._STARTF_USESTDHANDLES
    assert windows_conpty._handle_is_open(startup.StartupInfo.hStdInput) is False
    assert windows_conpty._handle_is_open(startup.StartupInfo.hStdOutput) is False
    assert windows_conpty._handle_is_open(startup.StartupInfo.hStdError) is False


def test_conpty_support_rejects_non_windows(monkeypatch) -> None:
    monkeypatch.setattr(windows_conpty, "_running_on_windows", lambda: False)

    support = conpty_support()

    assert support.supported is False
    assert support.windows_build is None
    assert "only on Windows" in support.reason
    with pytest.raises(ConPtyUnavailableError, match="only on Windows"):
        require_conpty_support()


def test_conpty_support_rejects_windows_before_1809(monkeypatch) -> None:
    monkeypatch.setattr(windows_conpty, "_running_on_windows", lambda: True)
    monkeypatch.setattr(
        windows_conpty,
        "_windows_build_number",
        lambda: MINIMUM_CONPTY_BUILD - 1,
    )

    support = conpty_support()

    assert support.supported is False
    assert support.windows_build == MINIMUM_CONPTY_BUILD - 1
    assert f"build {MINIMUM_CONPTY_BUILD}" in support.reason
    with pytest.raises(ConPtyUnavailableError, match="version 1809"):
        require_conpty_support()


def test_conpty_support_rejects_missing_runtime_exports(monkeypatch) -> None:
    monkeypatch.setattr(windows_conpty, "_running_on_windows", lambda: True)
    monkeypatch.setattr(
        windows_conpty,
        "_windows_build_number",
        lambda: MINIMUM_CONPTY_BUILD,
    )
    monkeypatch.setattr(
        windows_conpty,
        "_conpty_exports_available",
        lambda: False,
    )

    support = conpty_support()

    assert support.supported is False
    assert "exports are unavailable" in support.reason


@pytest.mark.parametrize(
    ("kwargs", "error"),
    [
        ({"columns": 0}, "columns"),
        ({"columns": 32768}, "columns"),
        ({"rows": 0}, "rows"),
        ({"rows": True}, "rows"),
        ({"cwd": "bad\x00path"}, "cwd"),
    ],
)
def test_conpty_process_validates_geometry_and_cwd(kwargs, error: str) -> None:
    with pytest.raises((TypeError, ValueError), match=error):
        WindowsConPtyProcess(["cmd.exe"], **kwargs)


def _read_until(
    process: WindowsConPtyProcess,
    expected: bytes,
    *,
    timeout: float = 5.0,
) -> bytes:
    output = bytearray()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        output.extend(process.read(timeout=0.05))
        if expected in output:
            return bytes(output)
        if process.output_eof and not process.output_ready.is_set():
            break
    output.extend(process.read_all())
    assert expected in output, output.decode(errors="replace")
    return bytes(output)


@pytest.mark.skipif(
    not conpty_support().supported,
    reason=conpty_support().reason,
)
def test_real_conpty_inherits_environment_quotes_argv_and_round_trips_input(
    monkeypatch,
) -> None:
    monkeypatch.setenv("ROW_CONPTY_INHERITED", "present")
    special_argument = 'two words "quoted" trailing\\'
    child = (
        "import os,sys; "
        "print('ENV=' + os.environ.get('ROW_CONPTY_INHERITED', ''), flush=True); "
        "print('ARG=' + sys.argv[1], flush=True); "
        "print('READY', flush=True); "
        "line = sys.stdin.readline(); "
        "print('GOT=' + line.rstrip('\\r\\n'), flush=True)"
    )
    process = WindowsConPtyProcess(
        [sys.executable, "-u", "-c", child, special_argument],
        columns=100,
        rows=28,
    )

    try:
        process.start()
        initial = _read_until(process, b"READY")
        assert b"ENV=present" in initial
        assert f"ARG={special_argument}".encode() in initial
        assert process.pid is not None
        assert process.poll() is None

        process.resize(132, 40)
        assert process.columns == 132
        assert process.rows == 40
        assert process.write(b"terminal-input\r") == len(b"terminal-input\r")
        process.flush(timeout=2.0)

        output = initial + _read_until(process, b"GOT=terminal-input")
        assert b"GOT=terminal-input" in output
        assert process.wait(timeout=5.0) == 0
    finally:
        process.close()

    assert process.closed is True
    assert process.output_eof is True


@pytest.mark.skipif(
    not conpty_support().supported,
    reason=conpty_support().reason,
)
def test_real_conpty_terminate_and_wait_are_bounded() -> None:
    child = "import time; print('READY', flush=True); time.sleep(30)"
    process = WindowsConPtyProcess([sys.executable, "-u", "-c", child])

    try:
        process.start()
        _read_until(process, b"READY")
        with pytest.raises(subprocess.TimeoutExpired):
            process.wait(timeout=0)
        process.terminate()
        assert process.wait(timeout=5.0) != 0
    finally:
        process.close()


@pytest.mark.skipif(
    not conpty_support().supported,
    reason=conpty_support().reason,
)
def test_real_conpty_resolves_a_path_basename_before_create_process() -> None:
    process = WindowsConPtyProcess(["cmd.exe", "/d", "/c", "echo BASENAME-READY"])

    try:
        process.start()
        output = _read_until(process, b"BASENAME-READY")
        assert b"BASENAME-READY" in output
        assert process.application_path is not None
        assert os.path.isabs(process.application_path)
        assert process.application_path.lower().endswith("cmd.exe")
        assert process.wait(timeout=5.0) == 0
    finally:
        process.close()


@pytest.mark.skipif(
    not conpty_support().supported,
    reason=conpty_support().reason,
)
def test_real_conpty_output_shutdown_preserves_tail_and_reaches_eof() -> None:
    marker = b"CONPTY-FINAL-TAIL-MARKER"
    child = (
        "import sys; "
        "sys.stdout.buffer.write(b'x' * (256 * 1024) + b'\\r\\n' + "
        + repr(marker)
        + " + b'\\r\\n'); "
        "sys.stdout.buffer.flush()"
    )
    process = WindowsConPtyProcess([sys.executable, "-c", child])
    output = bytearray()
    shutdown_started = False

    try:
        process.start()
        deadline = time.monotonic() + 10.0
        while time.monotonic() < deadline:
            output.extend(process.read(timeout=0.05))
            if not shutdown_started and process.poll() is not None:
                process.begin_output_shutdown()
                shutdown_started = True
            if shutdown_started and process.output_eof:
                output.extend(process.read_all())
                break

        assert shutdown_started is True
        assert process.output_eof is True
        assert output.count(b"x") >= 256 * 1024
        assert marker in output
        assert process.wait(timeout=1.0) == 0
    finally:
        process.close(terminate=False)


def test_process_start_fails_cleanly_when_conpty_is_unsupported(monkeypatch) -> None:
    monkeypatch.setattr(
        windows_conpty,
        "conpty_support",
        lambda: windows_conpty.ConPtySupport(False, "controlled unsupported host", 0),
    )
    process = WindowsConPtyProcess(["cmd.exe"])

    with pytest.raises(ConPtyUnavailableError, match="controlled unsupported host"):
        process.start()

    assert process.started is False
    assert process.closed is True


def test_executable_resolution_failure_uses_the_same_closed_state(monkeypatch) -> None:
    class _Api:
        pass

    def fail_resolution(_executable: str) -> str:
        raise FileNotFoundError("controlled executable-resolution failure")

    monkeypatch.setattr(windows_conpty, "_Kernel32Api", _Api)
    monkeypatch.setattr(
        windows_conpty,
        "_resolve_windows_executable",
        fail_resolution,
    )
    process = WindowsConPtyProcess(["missing.exe"])

    with pytest.raises(FileNotFoundError, match="controlled"):
        process.start()

    assert process.started is False
    assert process.closed is True
    assert process.pid is None
    assert process.output_eof is True
    assert process._api is None
    with pytest.raises(RuntimeError, match="closed"):
        process.start()


def test_nonblocking_read_requires_a_started_process() -> None:
    process = WindowsConPtyProcess(["cmd.exe"])

    with pytest.raises(RuntimeError, match="has not been started"):
        process.read(timeout=0)


def test_blocking_read_returns_immediately_after_known_eof() -> None:
    process = WindowsConPtyProcess(["cmd.exe"])
    process._api = object()  # type: ignore[assignment]
    process._started = True
    process._output_eof.set()

    started = time.monotonic()
    assert process.read(timeout=None) == b""
    elapsed = time.monotonic() - started

    assert elapsed < 0.1


def test_shutdown_drains_output_while_pre_24h2_close_can_block() -> None:
    events: list[str] = []
    close_entered = threading.Event()
    reader_drained = threading.Event()

    class _BlockingPre24H2Api:
        def ClosePseudoConsole(self, _handle) -> None:
            events.append("close-pseudoconsole-enter")
            assert process._closing.is_set() is False
            assert process._reader_thread is not None
            assert process._reader_thread.is_alive()
            close_entered.set()
            assert reader_drained.wait(1.0)
            events.append("close-pseudoconsole-return")

        def CloseHandle(self, handle) -> bool:
            value = int(getattr(handle, "value", handle))
            if value == 202:
                events.append("close-output-handle")
            elif value == 303:
                events.append("close-process-handle")
            return True

    process = WindowsConPtyProcess(["cmd.exe"])
    process._api = _BlockingPre24H2Api()  # type: ignore[assignment]
    process._started = True
    process._pid = 42
    process._returncode = 0
    process._pseudo_console = wintypes.HANDLE(101)
    process._output_read = wintypes.HANDLE(202)
    process._process_handle = wintypes.HANDLE(303)

    def drain_reader() -> None:
        assert close_entered.wait(1.0)
        events.append("reader-drained-output")
        process._output_eof.set()
        process.output_ready.set()
        reader_drained.set()

    process._reader_thread = threading.Thread(target=drain_reader, daemon=True)
    process._reader_thread.start()

    process.begin_output_shutdown()
    process.begin_output_shutdown()
    process.close(timeout=1.0)

    assert events.count("close-pseudoconsole-enter") == 1
    assert events.index("close-pseudoconsole-enter") < events.index(
        "reader-drained-output"
    )
    assert events.index("reader-drained-output") < events.index(
        "close-pseudoconsole-return"
    )
    assert events.index("close-pseudoconsole-return") < events.index(
        "close-output-handle"
    )


def test_constructor_does_not_mutate_the_parent_environment(monkeypatch) -> None:
    monkeypatch.setenv("ROW_CONPTY_PARENT_SENTINEL", "unchanged")

    WindowsConPtyProcess(["cmd.exe"])

    assert os.environ["ROW_CONPTY_PARENT_SENTINEL"] == "unchanged"

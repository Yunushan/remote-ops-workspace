from __future__ import annotations

import os
import subprocess

from remote_ops_workspace import process_launch
from remote_ops_workspace.process_launch import hidden_process_options


def test_hidden_process_options_are_empty_off_windows() -> None:
    assert hidden_process_options("posix") == {}


def test_hidden_process_options_request_no_console_on_windows() -> None:
    options = hidden_process_options("win32")
    assert options["creationflags"] & 0x08000000
    if os.name == "nt":
        assert "startupinfo" in options


def test_hidden_process_options_support_windows_without_startupinfo(monkeypatch) -> None:
    monkeypatch.setattr(process_launch.subprocess, "STARTUPINFO", None, raising=False)

    assert hidden_process_options("windows") == {"creationflags": 0x08000000}


def test_run_hidden_applies_platform_options(monkeypatch) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []

    def fake_run(argv, **kwargs):
        calls.append((list(argv), dict(kwargs)))
        return subprocess.CompletedProcess(argv, 0)

    monkeypatch.setattr(process_launch.subprocess, "run", fake_run)
    monkeypatch.setattr(
        process_launch,
        "hidden_process_options",
        lambda: {"creationflags": 0x08000000},
    )

    result = process_launch.run_hidden(["tasklist"], capture_output=True, check=False)

    assert result.returncode == 0
    assert calls == [
        (
            ["tasklist"],
            {"creationflags": 0x08000000, "capture_output": True, "check": False},
        )
    ]


def test_run_hidden_cannot_override_windows_console_suppression(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    def fake_run(_argv, **kwargs):
        calls.append(dict(kwargs))
        return subprocess.CompletedProcess(_argv, 0)

    monkeypatch.setattr(process_launch.subprocess, "run", fake_run)
    monkeypatch.setattr(
        process_launch,
        "hidden_process_options",
        lambda: {"creationflags": 0x08000000},
    )

    process_launch.run_hidden(["tasklist"], creationflags=0x00000010, check=False)

    assert calls == [{"creationflags": 0x08000010, "check": False}]


def test_hidden_option_merge_preserves_non_windows_options(monkeypatch) -> None:
    monkeypatch.setattr(process_launch, "hidden_process_options", lambda: {})
    options = {"cwd": "C:/work", "check": False}

    assert process_launch._merge_hidden_process_options(options) is options
    assert options == {"cwd": "C:/work", "check": False}


def test_hidden_option_merge_forces_existing_startup_info_hidden(monkeypatch) -> None:
    class StartupInfo:
        def __init__(self) -> None:
            self.dwFlags = 0x10
            self.wShowWindow = 9

    hidden_startup = StartupInfo()
    caller_startup = StartupInfo()
    monkeypatch.setattr(
        process_launch,
        "hidden_process_options",
        lambda: {"creationflags": 0x08000000, "startupinfo": hidden_startup},
    )
    monkeypatch.setattr(process_launch.subprocess, "STARTF_USESHOWWINDOW", 0x1, raising=False)
    monkeypatch.setattr(process_launch.subprocess, "SW_HIDE", 0, raising=False)

    options = process_launch._merge_hidden_process_options(
        {"creationflags": 0x10, "startupinfo": caller_startup}
    )

    assert options["creationflags"] == 0x08000010
    assert options["startupinfo"] is caller_startup
    assert caller_startup.dwFlags == 0x11
    assert caller_startup.wShowWindow == 0


def test_hidden_option_merge_can_apply_startup_info_without_creation_flags(monkeypatch) -> None:
    class StartupInfo:
        def __init__(self) -> None:
            self.dwFlags = 0
            self.wShowWindow = 9

    startup_info = StartupInfo()
    monkeypatch.setattr(
        process_launch,
        "hidden_process_options",
        lambda: {"startupinfo": startup_info},
    )
    monkeypatch.setattr(process_launch.subprocess, "STARTF_USESHOWWINDOW", 0x1, raising=False)
    monkeypatch.setattr(process_launch.subprocess, "SW_HIDE", 0, raising=False)

    options = process_launch._merge_hidden_process_options({})

    assert options["startupinfo"] is startup_info
    assert startup_info.dwFlags == 0x1
    assert startup_info.wShowWindow == 0


def test_popen_hidden_applies_platform_options(monkeypatch) -> None:
    calls: list[tuple[list[str], dict[str, object]]] = []
    sentinel = object()

    def fake_popen(argv, **kwargs):
        calls.append((list(argv), dict(kwargs)))
        return sentinel

    monkeypatch.setattr(process_launch.subprocess, "Popen", fake_popen)
    monkeypatch.setattr(
        process_launch,
        "hidden_process_options",
        lambda: {"creationflags": 0x08000000},
    )

    result = process_launch.popen_hidden(["ssh", "host"], stdin=subprocess.PIPE)

    assert result is sentinel
    assert calls == [
        (["ssh", "host"], {"creationflags": 0x08000000, "stdin": subprocess.PIPE})
    ]

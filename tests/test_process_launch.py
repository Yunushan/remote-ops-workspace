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

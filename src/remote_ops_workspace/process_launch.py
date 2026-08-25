"""Cross-platform subprocess launch helpers."""

from __future__ import annotations

import os
import subprocess
from collections.abc import Sequence
from typing import Any


def hidden_process_options(system_name: str | None = None) -> dict[str, Any]:
    """Return startup options that prevent helper console windows on Windows."""

    native_windows = (system_name or os.name).lower() in {"nt", "windows", "win32"}
    if not native_windows:
        return {}

    options: dict[str, Any] = {
        "creationflags": int(getattr(subprocess, "CREATE_NO_WINDOW", 0x08000000)),
    }
    startup_info_factory = getattr(subprocess, "STARTUPINFO", None)
    if startup_info_factory is not None:
        startup_info = startup_info_factory()
        startup_info.dwFlags |= int(getattr(subprocess, "STARTF_USESHOWWINDOW", 0x00000001))
        startup_info.wShowWindow = int(getattr(subprocess, "SW_HIDE", 0))
        options["startupinfo"] = startup_info
    return options


def _merge_hidden_process_options(options: dict[str, Any]) -> dict[str, Any]:
    """Keep caller options while making Windows console suppression mandatory."""

    hidden = hidden_process_options()
    if not hidden:
        return options

    if "creationflags" in hidden:
        options["creationflags"] = int(options.get("creationflags", 0)) | int(
            hidden["creationflags"]
        )

    hidden_startup_info = hidden.get("startupinfo")
    if hidden_startup_info is not None:
        startup_info = options.get("startupinfo") or hidden_startup_info
        startup_info.dwFlags |= int(
            getattr(subprocess, "STARTF_USESHOWWINDOW", 0x00000001)
        )
        startup_info.wShowWindow = int(getattr(subprocess, "SW_HIDE", 0))
        options["startupinfo"] = startup_info
    return options


def popen_hidden(argv: Sequence[str], **kwargs: Any) -> subprocess.Popen[Any]:
    """Start an argv-defined helper without opening a Windows console window."""

    options = _merge_hidden_process_options(dict(kwargs))
    return subprocess.Popen(argv, **options)  # noqa: S603 - validated argv, no shell


def run_hidden(argv: Sequence[str], **kwargs: Any) -> subprocess.CompletedProcess[Any]:
    """Run a non-interactive helper without opening a Windows console window."""

    options = _merge_hidden_process_options(dict(kwargs))
    return subprocess.run(argv, **options)  # noqa: S603 - validated argv, no shell


__all__ = [
    "hidden_process_options",
    "popen_hidden",
    "run_hidden",
]

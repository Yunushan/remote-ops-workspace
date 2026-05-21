from __future__ import annotations

import platform
import shutil
import subprocess
from dataclasses import dataclass

from . import command_safety as safe


@dataclass(slots=True)
class XServerPlan:
    command: list[str]
    notes: list[str]

    def printable(self) -> str:
        return " ".join(safe.argv_list(self.command, "x server command"))


def build_x_server_plan(display: str = ":0") -> XServerPlan:
    display = safe.display(display)
    system = platform.system().lower()
    notes: list[str] = []
    if system == "windows":
        executable = _first_available(["vcxsrv", "xlaunch"]) or "vcxsrv"
        notes.append("Uses VcXsrv/XLaunch when available.")
        return XServerPlan([executable, display, "-multiwindow", "-clipboard", "-ac"], notes)
    if system == "darwin":
        notes.append("Starts XQuartz through LaunchServices.")
        return XServerPlan(["open", "-a", "XQuartz"], notes)
    executable = _first_available(["Xorg", "Xnest"]) or "Xorg"
    notes.append("Starts a local X server. Ensure the display is free.")
    return XServerPlan([executable, display], notes)


def run_x_server(plan: XServerPlan, dry_run: bool = False) -> XServerPlan:
    if not dry_run:
        safe.argv_list(plan.command, "x server command")
        subprocess.Popen(plan.command)  # noqa: S603 - argv list, no shell
    return plan


def _first_available(candidates: list[str]) -> str | None:
    for candidate in candidates:
        if shutil.which(candidate):
            return candidate
    return None

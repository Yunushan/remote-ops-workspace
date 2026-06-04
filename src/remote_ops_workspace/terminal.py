from __future__ import annotations

import os
import platform
import shlex
from collections.abc import Mapping
from dataclasses import dataclass, field

from . import command_safety as safe
from .file_transfer import build_sftp_interactive_plan
from .launcher import build_launch_plan
from .models import Profile


@dataclass(slots=True)
class TerminalPanePlan:
    title: str
    command: list[str]
    source: str = "shell"
    notes: list[str] = field(default_factory=list)

    def printable(self) -> str:
        return shlex.join(self.command)


def default_shell_command(
    env: Mapping[str, str] | None = None,
    system: str | None = None,
) -> list[str]:
    env = env or os.environ
    normalized_system = (system or platform.system()).lower()
    if normalized_system == "windows":
        return [env.get("COMSPEC") or "cmd.exe"]
    shell = env.get("SHELL") or "/bin/sh"
    return [shell]


def default_shell_plan(index: int | None = None) -> TerminalPanePlan:
    suffix = f" {index}" if index is not None else ""
    return TerminalPanePlan(title=f"Shell{suffix}", command=default_shell_command(), source="shell")


def split_shell_plans(count: int = 2) -> list[TerminalPanePlan]:
    if count < 1:
        raise ValueError("split pane count must be greater than zero")
    return [default_shell_plan(index) for index in range(1, count + 1)]


def terminal_plan_for_command(command: str, title: str = "Command") -> TerminalPanePlan:
    argv = safe.argv(command, "terminal command")
    return TerminalPanePlan(title=title, command=argv, source="command")


def terminal_plan_for_profile(profile: Profile) -> TerminalPanePlan:
    plan = build_launch_plan(profile)
    return TerminalPanePlan(
        title=profile.name,
        command=plan.command,
        source=f"profile:{profile.name}",
        notes=plan.notes,
    )


def terminal_plan_for_sftp_browser(profile: Profile) -> TerminalPanePlan:
    plan = build_sftp_interactive_plan(profile)
    return TerminalPanePlan(
        title=f"Files: {profile.name}",
        command=plan.command,
        source=f"sftp:{profile.name}",
        notes=["Interactive SFTP browser pane.", *plan.notes],
    )

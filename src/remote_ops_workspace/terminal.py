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
    command = _embedded_terminal_command(profile, plan.command)
    notes = list(plan.notes)
    if _is_embedded_openssh(profile, plan.command):
        if not _ssh_option_is_present(plan.command, "ConnectTimeout"):
            notes.append(
                "Embedded SSH uses a 10 second TCP connection timeout when the profile "
                "does not specify one."
            )
    return TerminalPanePlan(
        title=profile.name,
        command=command,
        source=f"profile:{profile.name}",
        notes=notes,
    )


def _embedded_terminal_command(profile: Profile, command: list[str]) -> list[str]:
    """Adapt external launch argv for the embedded, stdin-backed terminal surface.

    Force a remote TTY for embedded SSH panes and provide a bounded connection
    timeout when the profile did not choose one. Host-key policy stays with the
    profile or OpenSSH's default interactive confirmation; it is never silently
    changed to ``accept-new`` or ``no``.
    """

    if not _is_embedded_openssh(profile, command):
        return list(command)

    adapted = list(command)
    if not any(argument in {"-t", "-tt", "-T"} for argument in adapted[1:]):
        adapted.insert(1, "-tt")

    # LaunchPlan keeps the destination as the last argument.  Insert defaults
    # immediately before it so the destination cannot consume an option value.
    insert_at = max(1, len(adapted) - 1)
    for option_name, value in (("ConnectTimeout", "10"),):
        if _ssh_option_is_present(adapted, option_name):
            continue
        adapted[insert_at:insert_at] = ["-o", f"{option_name}={value}"]
        insert_at += 2
    return adapted


def _is_embedded_openssh(profile: Profile, command: list[str]) -> bool:
    if not command or profile.protocol.lower() not in {"ssh", "ssh1", "sshv1"}:
        return False
    return os.path.basename(command[0]).lower() in {"ssh", "ssh.exe"}


def _ssh_option_is_present(command: list[str], option_name: str) -> bool:
    prefix = f"{option_name.lower()}="
    for argument in command[1:]:
        candidate = argument.strip()
        if candidate.lower().startswith("-o"):
            candidate = candidate[2:].lstrip()
        if candidate.lower().startswith(prefix):
            return True
    return False


def openssh_command_with_overrides(
    command: list[str],
    overrides: Mapping[str, str],
) -> list[str]:
    """Return an argv copy with selected ``-o Name=value`` options replaced.

    The helper handles both ``-o Name=value`` and ``-oName=value`` forms and
    never mutates the stored launch plan.  It is used only for bounded,
    non-interactive runtime copies such as background monitoring and the
    no-ConPTY safety fallback.
    """

    if not command:
        return []
    normalized = {
        str(name).strip().lower(): (str(name).strip(), str(value).strip())
        for name, value in overrides.items()
        if str(name).strip()
    }
    result = [command[0]]
    index = 1
    while index < len(command):
        argument = command[index]
        candidate = ""
        consumed = 1
        if argument == "-o" and index + 1 < len(command):
            candidate = command[index + 1].strip()
            consumed = 2
        elif argument.lower().startswith("-o"):
            candidate = argument[2:].lstrip()
        option_name = candidate.partition("=")[0].strip().lower()
        if option_name in normalized and "=" in candidate:
            index += consumed
            continue
        result.extend(command[index : index + consumed])
        index += consumed
    injected: list[str] = []
    for _key, (name, value) in normalized.items():
        injected.extend(["-o", f"{name}={value}"])
    result[1:1] = injected
    return result


def terminal_plan_for_sftp_browser(profile: Profile) -> TerminalPanePlan:
    plan = build_sftp_interactive_plan(profile)
    return TerminalPanePlan(
        title=f"Files: {profile.name}",
        command=plan.command,
        source=f"sftp:{profile.name}",
        notes=["Interactive SFTP browser pane.", *plan.notes],
    )

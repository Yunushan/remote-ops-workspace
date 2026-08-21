from __future__ import annotations

import hashlib
import os
import platform
import shlex
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

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
    native_command = openssh_command_without_windows_connection_sharing(plan.command)
    command = _embedded_terminal_command(profile, native_command)
    notes = list(plan.notes)
    if native_command != plan.command:
        notes.append(
            "Windows OpenSSH connection sharing options were ignored because "
            "native Windows does not support the required control socket."
        )
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


def openssh_command_without_windows_connection_sharing(
    command: list[str],
) -> list[str]:
    """Remove Unix control-socket options from native Windows OpenSSH argv.

    Older releases could persist ``ControlMaster``/``ControlPath`` options in
    an already-built terminal plan. Merely avoiding new options is therefore
    insufficient: a saved plan can still make Windows OpenSSH fail with
    ``getsockname failed: Not a socket``. Strip only connection-sharing
    options on Windows and preserve every authentication and security option.
    """

    if not command or os.name != "nt":
        return list(command)
    executable = os.path.basename(command[0]).lower()
    if executable not in {"ssh", "ssh.exe", "sftp", "sftp.exe", "scp", "scp.exe"}:
        return list(command)

    unsupported = {"controlmaster", "controlpath", "controlpersist"}
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
        option_name = (
            candidate.replace("=", " ", 1).split(maxsplit=1)[0].lower() if candidate else ""
        )
        if option_name in unsupported:
            index += consumed
            continue
        # ``ssh -M`` and ``ssh -S path`` are short forms for the same Unix
        # multiplexing feature. SFTP uses ``-S`` for a different purpose, so
        # only remove these forms from the ssh executable.
        if executable in {"ssh", "ssh.exe"} and argument == "-M":
            index += 1
            continue
        if executable in {"ssh", "ssh.exe"} and argument == "-S" and index + 1 < len(command):
            index += 2
            continue
        result.extend(command[index : index + consumed])
        index += consumed
    # User-level ssh_config files can still enable multiplexing after command
    # arguments are parsed. Explicit command-line values take precedence and
    # prevent native Windows OpenSSH from attempting a Unix control socket.
    return openssh_command_with_overrides(
        result,
        {
            "ControlMaster": "no",
            "ControlPath": "none",
            "ControlPersist": "no",
        },
    )


def ssh_control_path_for_profile(profile: Profile) -> str:
    """Return a private, stable OpenSSH control-socket path for ``profile``.

    The embedded terminal is the only process allowed to create the shared
    connection.  SFTP and monitoring clients use the socket with
    ``ControlMaster=no`` after the terminal has authenticated, so a password
    prompt is never duplicated or sent to a background process.  Profiles can
    opt out with the explicit multiplexing options below; host-key and crypto
    policy are otherwise left unchanged.

    Native Windows OpenSSH does not support the Unix-domain control sockets
    required by ``ControlPath``.  Keep the regular interactive connection
    path intact there and let background operations use their normal explicit
    authentication rules instead of turning every SSH launch into a socket
    error.
    """

    if profile.protocol.lower().strip() not in {"ssh", "sftp", "ssh1", "sshv1"}:
        return ""
    if os.name == "nt":
        return ""
    normalized = {
        str(key).strip().lower(): str(value).strip()
        for key, value in profile.options.items()
    }
    disabled = {"0", "false", "no", "off", "disabled"}
    for key in (
        "ssh_multiplex",
        "ssh_browser_multiplex",
        "ssh_control_master",
        "controlmaster",
        "control_master",
        "ssh_connection_sharing",
    ):
        if normalized.get(key, "").lower() in disabled:
            return ""
    # Do not override an operator-supplied socket path.  The background
    # runtime cannot safely infer whether that external socket is usable.
    if any(key in normalized for key in ("controlpath", "ssh_control_path")):
        return ""

    identity = str(profile.identity_file or "")
    fingerprint = "\0".join(
        (
            profile.name,
            profile.host or "",
            str(profile.port or 22),
            profile.username or "",
            identity,
            repr(sorted(normalized.items())),
        )
    )
    digest = hashlib.sha256(fingerprint.encode("utf-8")).hexdigest()[:24]
    directory = Path(tempfile.gettempdir()) / "remote-ops-workspace" / "ssh-control"
    try:
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        if os.name != "nt":
            directory.chmod(0o700)
    except OSError:
        return ""
    return str(directory / f"cm-{digest}")


def ssh_command_with_control_path(
    command: list[str],
    control_path: str,
    *,
    master: bool,
) -> list[str]:
    """Add safe OpenSSH connection sharing to an argv copy.

    ``master=True`` is reserved for the interactive terminal.  Background
    clients explicitly use ``ControlMaster=no`` so they can only reuse an
    already-authenticated terminal connection and can never create a hidden
    password prompt of their own.
    """

    if os.name == "nt":
        return openssh_command_without_windows_connection_sharing(command)
    if not command or not control_path:
        return list(command)
    executable = os.path.basename(command[0]).lower()
    if executable not in {"ssh", "ssh.exe", "sftp", "sftp.exe", "scp", "scp.exe"}:
        return list(command)
    return openssh_command_with_overrides(
        list(command),
        {
            "ControlMaster": "auto" if master else "no",
            "ControlPath": control_path,
        },
    )


def terminal_plan_for_sftp_browser(profile: Profile) -> TerminalPanePlan:
    plan = build_sftp_interactive_plan(profile)
    return TerminalPanePlan(
        title=f"Files: {profile.name}",
        command=plan.command,
        source=f"sftp:{profile.name}",
        notes=["Interactive SFTP browser pane.", *plan.notes],
    )

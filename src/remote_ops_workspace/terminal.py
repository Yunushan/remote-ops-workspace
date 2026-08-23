from __future__ import annotations

import hashlib
import ipaddress
import ntpath
import os
import platform
import re
import shlex
import subprocess
import sys
import tempfile
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from . import command_safety as safe
from .file_transfer import build_sftp_interactive_plan
from .launcher import build_launch_plan
from .models import Profile


def _is_native_windows() -> bool:
    return os.name == "nt"


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


_OPENSSH_SHORT_OPTIONS_WITH_VALUE = frozenset("BbcDEeFIiJLlmOoPpQRSWw")


def _openssh_short_argument(
    command: list[str],
    index: int,
) -> tuple[str | None, str | None, int, str]:
    """Describe the first value-taking option in one OpenSSH short cluster.

    The returned prefix contains preceding flag-only options.  A value-taking
    option consumes the rest of its argv item, or the next item when no value
    is attached.  Callers can therefore avoid treating option operands or the
    remote command after the destination as more local OpenSSH options.
    """

    argument = command[index]
    if argument == "-" or not argument.startswith("-") or argument.startswith("--"):
        return None, None, 1, argument
    cluster = argument[1:]
    for position, option in enumerate(cluster):
        if option not in _OPENSSH_SHORT_OPTIONS_WITH_VALUE:
            continue
        prefix = f"-{cluster[:position]}" if position else ""
        attached = cluster[position + 1 :]
        if attached:
            return option, attached, 1, prefix
        if index + 1 < len(command):
            return option, command[index + 1], 2, prefix
        return option, None, 1, prefix
    return None, None, 1, argument


def _ssh_option_is_present(command: list[str], option_name: str) -> bool:
    prefix = f"{option_name.lower()}="
    index = 1
    while index < len(command):
        argument = command[index]
        if argument == "--" or argument == "-" or not argument.startswith("-"):
            break
        option, value, consumed, _option_prefix = _openssh_short_argument(command, index)
        candidate = value.strip() if option == "o" and value is not None else ""
        if candidate.lower().startswith(prefix):
            return True
        index += consumed
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
        if argument == "--" or argument == "-" or not argument.startswith("-"):
            result.extend(command[index:])
            break
        option, value, consumed, option_prefix = _openssh_short_argument(command, index)
        candidate = value.strip() if option == "o" and value is not None else ""
        option_name = candidate.partition("=")[0].strip().lower()
        if option_name in normalized and "=" in candidate:
            if option_prefix:
                result.append(option_prefix)
            index += consumed
            continue
        result.extend(command[index : index + consumed])
        index += consumed
    injected: list[str] = []
    for _key, (name, value) in normalized.items():
        injected.extend(["-o", f"{name}={value}"])
    result[1:1] = injected
    return result


def _windows_proxy_jump_spec(value: str) -> tuple[str, str | None]:
    """Validate one ProxyJump destination before embedding it in ProxyCommand.

    ``-J`` is normally safe because OpenSSH receives the destination as a
    discrete argv item. The Windows hardening path below must place that value
    inside a ProxyCommand string, so it deliberately accepts only the documented
    ``[user@]host[:port]`` token shape. In particular, percent expansion,
    command-shell metacharacters and multi-hop chains are not allowed here.
    """

    candidate = str(value).strip()
    if not candidate or candidate != value or "," in candidate:
        raise ValueError(
            "native Windows OpenSSH supports one hardened proxy_jump hop; "
            "multi-hop chains and surrounding whitespace are not supported"
        )
    match = re.fullmatch(
        r"(?:(?P<user>[A-Za-z0-9][A-Za-z0-9._+\-]*)@)?"
        r"(?:(?P<host>[A-Za-z0-9][A-Za-z0-9._\-]*)|\[(?P<ipv6>[0-9A-Fa-f:.]+)\])"
        r"(?::(?P<port>[0-9]{1,5}))?",
        candidate,
    )
    if match is None:
        raise ValueError(
            "native Windows proxy_jump must use a safe [user@]host[:port] token"
        )
    port = match.group("port")
    if port is not None and not 1 <= int(port) <= 65535:
        raise ValueError("native Windows proxy_jump port must be between 1 and 65535")
    host = match.group("host")
    ipv6 = match.group("ipv6")
    if ipv6 is not None:
        try:
            ipaddress.IPv6Address(ipv6)
        except ipaddress.AddressValueError as exc:
            raise ValueError("native Windows proxy_jump contains an invalid IPv6 host") from exc
        host = ipv6
    if host is None:
        raise ValueError("native Windows proxy_jump host is unavailable")
    user = match.group("user")
    destination = f"{user}@{host}" if user else host
    return destination, port


def _windows_proxy_child_executable(executable: str) -> str:
    """Return the ssh sibling used by an OpenSSH-family Windows executable."""

    directory, filename = ntpath.split(executable)
    child_name = "ssh.exe" if filename.lower().endswith(".exe") else "ssh"
    child = ntpath.join(directory, child_name) if directory else child_name
    if sys.platform == "win32":
        # Resolve the interpreted ProxyCommand child with the same trusted
        # system/PATH policy as CreateProcessW.  A bare ``ssh.exe`` must never
        # fall back to an attacker-controlled executable in the current dir.
        from .windows_conpty import resolve_windows_executable

        child = resolve_windows_executable(child)
    # ProxyCommand is an interpreted command string. Windows paths cannot
    # contain quotes, but other cmd metacharacters can occur in a directory
    # name and subprocess.list2cmdline does not quote all of them. Fail closed
    # instead of turning a custom client path into command text.
    if any(character in child for character in '\r\n\0"&|<>()^%!'):
        raise ValueError("native Windows OpenSSH executable path is unsafe for ProxyCommand")
    return child


def _windows_ssh_config_args(command: list[str]) -> list[str]:
    """Copy explicit ``-F`` selections so jump-host aliases keep working."""

    result: list[str] = []
    index = 1
    while index < len(command):
        argument = command[index]
        if argument == "--" or argument == "-" or not argument.startswith("-"):
            break
        option, value, consumed, _option_prefix = _openssh_short_argument(command, index)
        if option == "F":
            if value is None:
                raise ValueError("OpenSSH -F requires a configuration path")
            path = value
            if any(character in path for character in '\r\n\0"&|<>()^%!'):
                raise ValueError(
                    "native Windows OpenSSH configuration path is unsafe for ProxyCommand"
                )
            result.extend(["-F", path])
        index += consumed
    return result


def _windows_proxy_jump_child_argv(
    executable: str,
    config_args: list[str],
    jump_destination: str,
    jump_port: str | None,
) -> list[str]:
    """Build the standalone ssh child used in a Windows ProxyCommand."""

    return [
        _windows_proxy_child_executable(executable),
        *config_args,
        "-S",
        "none",
        "-o",
        "ControlMaster=no",
        "-o",
        "ControlPersist=no",
        "-o",
        "ControlPath=none",
        # A single supported jump must remain a single hop even when the jump
        # host's ssh_config stanza names another ProxyJump/ProxyCommand.
        "-o",
        "ProxyCommand=none",
        "-o",
        "ProxyJump=none",
        *(["-p", jump_port] if jump_port is not None else []),
        "-W",
        "[%h]:%p",
        "--",
        jump_destination,
    ]


def _windows_command_with_hardened_proxy_jump(
    command: list[str],
    executable: str,
) -> list[str]:
    """Replace an explicit Windows ``-J`` with a hardened ssh child.

    The OpenSSH ``-J`` shortcut synthesizes another ssh process. Parent
    ``ControlMaster``/``ControlPath`` command-line values do not constrain that
    process, so a jump-host config stanza can re-enable the unsupported Win32
    mux path. An explicit ProxyCommand lets us give the child its own
    standalone-transport contract without changing host-key verification.
    """

    rewritten = [command[0]]
    jump_specs: list[str] = []
    proxy_command_present = False
    index = 1
    while index < len(command):
        argument = command[index]
        if argument == "--" or argument == "-" or not argument.startswith("-"):
            rewritten.extend(command[index:])
            break

        option, value, consumed, option_prefix = _openssh_short_argument(command, index)
        candidate = value.strip() if option == "o" and value is not None else ""
        if candidate:
            option_parts = re.split(r"[=\s]+", candidate, maxsplit=1)
            option_name = option_parts[0].lower()
            option_value = option_parts[1] if len(option_parts) == 2 else ""
            if option_name == "proxyjump":
                if not option_value:
                    raise ValueError("OpenSSH ProxyJump requires a destination")
                if option_value.lower() == "none":
                    rewritten.extend(command[index : index + consumed])
                else:
                    jump_specs.append(option_value)
                    if option_prefix:
                        rewritten.append(option_prefix)
                index += consumed
                continue
            if option_name == "proxycommand" and option_value.lower() != "none":
                proxy_command_present = True

        if option == "J":
            if value is None:
                raise ValueError("OpenSSH -J requires a destination")
            if value.lower() == "none":
                # OpenSSH accepts ``-J none`` as the short command-line form
                # for explicitly disabling ProxyJump. Preserve the operator's
                # exact spelling instead of turning ``none`` into a jump host.
                rewritten.extend(command[index : index + consumed])
            else:
                jump_specs.append(value)
                if option_prefix:
                    rewritten.append(option_prefix)
            index += consumed
            continue

        rewritten.extend(command[index : index + consumed])
        index += consumed

    if not jump_specs:
        return list(command)
    if len(jump_specs) != 1:
        raise ValueError("native Windows OpenSSH accepts one explicit proxy_jump option")
    if proxy_command_present:
        raise ValueError("native Windows OpenSSH cannot combine proxy_jump and ProxyCommand")

    jump_destination, jump_port = _windows_proxy_jump_spec(jump_specs[0])
    child = _windows_proxy_jump_child_argv(
        executable,
        _windows_ssh_config_args(command),
        jump_destination,
        jump_port,
    )
    # Keep this option ahead of configuration processing. OpenSSH expands %h
    # and %p at execution time; list2cmdline preserves Windows paths containing
    # spaces without introducing a shell.
    rewritten[1:1] = ["-o", f"ProxyCommand={subprocess.list2cmdline(child)}"]
    return rewritten


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

    if not command or not _is_native_windows():
        return list(command)
    # This path is a native Windows executable even when the behavior is
    # validated from a non-Windows CI host. Use ntpath explicitly so a
    # backslash-delimited path cannot bypass the OpenSSH hardening gate.
    executable = ntpath.basename(command[0]).lower()
    if executable not in {"ssh", "ssh.exe", "sftp", "sftp.exe", "scp", "scp.exe"}:
        return list(command)

    command = _windows_command_with_hardened_proxy_jump(command, command[0])

    unsupported = {"controlmaster", "controlpath", "controlpersist"}
    # OpenSSH accepts short options in clusters.  Options in this set consume
    # the rest of their argument (or the following argv entry), so an ``M`` or
    # ``S`` after one of them is data rather than another option.  Keep that
    # distinction while removing the multiplexing-only ``-M``/``-S`` forms.
    ssh_short_options_with_value = frozenset("BbcDEeFIiJLlmOoPpQRSWw")

    def without_ssh_mux_short_options(argument: str) -> tuple[str | None, bool]:
        """Return ``(replacement, consume_next)`` for one ssh short argv item."""

        if not argument.startswith("-") or argument.startswith("--") or len(argument) < 2:
            return argument, False
        cluster = argument[1:]
        if "M" not in cluster and "S" not in cluster:
            return argument, False

        kept: list[str] = []
        index = 0
        changed = False
        while index < len(cluster):
            option = cluster[index]
            if option == "M":
                changed = True
                index += 1
                continue
            if option == "S":
                # Everything attached after S is its control-path value.  If
                # nothing is attached, discard the following argv item too.
                changed = True
                consume_next = index + 1 == len(cluster)
                replacement = f"-{''.join(kept)}" if kept else None
                return replacement, consume_next
            if option in ssh_short_options_with_value:
                # The remainder belongs to this non-mux option. Preserve it,
                # including any literal M/S characters inside its value.
                kept.extend(cluster[index:])
                break
            kept.append(option)
            index += 1

        if not changed:
            return argument, False
        return (f"-{''.join(kept)}" if kept else None), False

    result = [command[0]]
    index = 1
    while index < len(command):
        argument = command[index]
        if argument == "--" or argument == "-" or not argument.startswith("-"):
            result.extend(command[index:])
            break
        option, value, consumed, option_prefix = _openssh_short_argument(command, index)
        candidate = value.strip() if option == "o" and value is not None else ""
        option_name = (
            candidate.replace("=", " ", 1).split(maxsplit=1)[0].lower() if candidate else ""
        )
        if option_name in unsupported:
            if option_prefix:
                result.append(option_prefix)
            index += consumed
            continue
        # ``ssh -M`` and ``ssh -S path`` are short forms for the same Unix
        # multiplexing feature. OpenSSH also accepts clustered and attached
        # forms (for example ``-MN``, ``-Spath`` and ``-vMSpath``). SFTP uses
        # ``-S`` for a different purpose, so only normalize ssh argv here.
        if executable in {"ssh", "ssh.exe"}:
            replacement, consume_next = without_ssh_mux_short_options(argument)
            if replacement != argument or consume_next:
                if replacement:
                    result.append(replacement)
                if consumed == 2 and not consume_next:
                    result.append(command[index + 1])
                index += consumed
                continue
        result.extend(command[index : index + consumed])
        index += consumed
    # User-level ssh_config files can still enable multiplexing after command
    # arguments are parsed. Explicit command-line values take precedence.  For
    # ssh itself, use the dedicated ``-S none`` switch instead of relying only
    # on ``-o ControlPath=none``.  The Win32 port has shipped releases where a
    # configured control path could still enter the mux-client path and leave
    # the live connection attached to a non-socket handle, producing
    # ``getsockname failed: Not a socket`` immediately after authentication.
    # ``-S none`` is OpenSSH's explicit standalone-transport contract.
    overrides = {
        "ControlMaster": "no",
        "ControlPersist": "no",
    }
    if executable in {"ssh", "ssh.exe"}:
        standalone = openssh_command_with_overrides(result, overrides)
        standalone[1:1] = ["-S", "none"]
        return standalone

    # sftp/scp assign a different meaning to ``-S`` (the ssh program), so use
    # the equivalent configuration option for those executables.
    return openssh_command_with_overrides(
        result,
        {**overrides, "ControlPath": "none"},
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
    if _is_native_windows():
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
        if not _is_native_windows():
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

    if _is_native_windows():
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

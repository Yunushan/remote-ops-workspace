from __future__ import annotations

import ntpath
import sys

from PyQt6.QtCore import QProcess

from .models import Profile
from .terminal import TerminalPanePlan


def _background_process(parent, *, interactive_auth: bool = False):
    """Create a hidden helper process, optionally with a private PTY.

    Native Windows OpenSSH only accepts password input from a console/PTY.
    The normal helper path remains pipe-backed and non-interactive; the
    explicit vault-authenticated Moba tools path opts into a hidden ConPTY
    so a password can be submitted without creating a console window.
    """

    if sys.platform == "win32":
        from .qt_terminal_process import QtConPtyProcess, QtHiddenProcess

        if interactive_auth:
            try:
                from .windows_conpty import conpty_support

                if conpty_support().supported:
                    process = QtConPtyProcess(parent)
                    process.setProperty("backgroundAuthTransport", "windows-conpty")
                    return process
            except (ImportError, OSError, RuntimeError):
                pass

        return QtHiddenProcess(parent)
    return QProcess(parent)


def _terminal_process_backend(
    parent,
    plan: TerminalPanePlan,
    _profile: Profile | None,
):
    """Select a real local pseudo-console for interactive Windows sessions."""

    # Saved Windows profiles can carry an absolute backslash-delimited
    # executable path even when a POSIX-hosted render/evidence check is
    # exercising the native-Windows selection logic.
    program_name = ntpath.basename(plan.command[0]).lower() if plan.command else ""
    openssh_program = program_name in {"ssh", "ssh.exe", "sftp", "sftp.exe"}
    local_shell_program = bool(
        plan.source == "shell"
        and program_name
        in {
            "cmd",
            "cmd.exe",
            "powershell",
            "powershell.exe",
            "pwsh",
            "pwsh.exe",
        }
    )
    use_windows_conpty = bool(sys.platform == "win32" and (openssh_program or local_shell_program))
    if not use_windows_conpty:
        if sys.platform == "win32":
            # Console commands opened from a terminal tab still need the
            # pipe adapter when ConPTY is not appropriate. Plain QProcess
            # can briefly create a visible console during tab activation;
            # use the same hidden startup contract as monitoring/SFTP.
            process = _background_process(parent)
            process.setProperty("terminalWindowsConsoleSuppressed", True)
            return process, ""
        return QProcess(parent), ""
    try:
        from .qt_terminal_process import QtConPtyProcess
        from .windows_conpty import conpty_support

        support = conpty_support()
        if support.supported:
            return QtConPtyProcess(parent), ""
        reason = support.reason
    except (ImportError, OSError, RuntimeError) as exc:
        reason = str(exc)
    if openssh_program:
        return (
            _openssh_pipe_fallback_process(parent),
            (
                "Local ConPTY is unavailable, so this SSH pane is using a pipe fallback. "
                "Interactive prompts are unsupported; this launch is restricted to "
                f"trusted-host key/agent authentication: {reason}"
            ),
        )
    process = _background_process(parent)
    process.setProperty("terminalLineInputFallback", True)
    return (
        process,
        f"Local ConPTY is unavailable, so this shell is using line-oriented input: {reason}",
    )


def _openssh_pipe_fallback_process(parent):
    process = _background_process(parent)
    process.setProperty("terminalOpenSshPipeFallback", True)
    return process

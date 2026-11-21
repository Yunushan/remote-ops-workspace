"""Track the authenticated OpenSSH master associated with a desktop SSH pane."""

from __future__ import annotations

import os
import stat
from dataclasses import asdict, dataclass, replace
from pathlib import Path
from typing import Literal

from PyQt6.QtCore import QObject, QProcess, QTimer, pyqtSignal

SshPhase = Literal["idle", "connecting", "authenticating", "connected", "connection-lost", "closing", "closed"]

_AUTH_CHECK_MS = 250
_HEALTH_CHECK_MS = 2_000
_CHECK_TIMEOUT_MS = 1_000
_PROBE_PHASES = {"authenticating", "connected", "connection-lost"}


@dataclass(frozen=True, slots=True)
class SharedSshConnectionState:
    phase: SshPhase = "idle"
    attempt: int = 0
    disconnect_reason: str | None = None
    exit_code: int | None = None
    exit_status: str | None = None

    def properties(self) -> dict[str, object]:
        return asdict(self)

    def description(self) -> str:
        return {
            "idle": "Shared SSH · Ready to connect",
            "connecting": "Shared SSH · Connecting",
            "authenticating": "Shared SSH · Waiting for authentication",
            "connected": "Shared SSH · Authenticated",
            "connection-lost": "Shared SSH · Control connection lost",
            "closing": "Shared SSH · Closing",
            "closed": "Shared SSH · Closed",
        }[self.phase]


class SharedSshConnection(QObject):
    """Confirm a managed socket via a bounded local OpenSSH control request."""

    changed = pyqtSignal(object)

    def __init__(self, socket_path: str, ssh_executable: str, parent: QObject) -> None:
        super().__init__(parent)
        self.socket_path = socket_path
        self.state = SharedSshConnectionState()
        self._checking = False
        self._check = QProcess(self)
        self._check.setProgram(ssh_executable)
        self._check.setArguments(["-F", os.devnull, "-S", socket_path, "-O", "check", "localhost"])
        self._check.setStandardOutputFile(os.devnull)
        self._check.setStandardErrorFile(os.devnull)
        self._check.finished.connect(self._check_finished)
        self._check.errorOccurred.connect(self._check_error)
        self._timeout = QTimer(self)
        self._timeout.setSingleShot(True)
        self._timeout.timeout.connect(self._check_timed_out)
        self._poll = QTimer(self)
        self._poll.timeout.connect(self._poll_socket)

    def _publish(self, state: SharedSshConnectionState) -> None:
        if state != self.state:
            self.state = state
            self.changed.emit(state)

    def start_attempt(self) -> None:
        self._poll.stop()
        self._cancel_check()
        self._publish(SharedSshConnectionState(phase="connecting", attempt=self.state.attempt + 1))

    def process_started(self) -> None:
        if self.state.phase == "connecting":
            self._publish(replace(self.state, phase="authenticating"))
            self._poll.start(_AUTH_CHECK_MS)
            self._poll_socket()

    def begin_close(self, reason: str) -> None:
        if self.state.phase in {"idle", "closing", "closed"}:
            return
        self._poll.stop()
        self._cancel_check()
        self._publish(replace(self.state, phase="closing", disconnect_reason=reason))

    def finish(self, exit_code: int | None, exit_status: str) -> None:
        if self.state.phase in {"idle", "closed"}:
            return
        reason = self.state.disconnect_reason
        if reason is None:
            if exit_status == "FailedToStart":
                reason = "launch-failed"
            elif exit_status == "CrashExit":
                reason = "process-crashed"
            elif exit_code == 255:
                reason = "ssh-error-or-disconnect"
            else:
                reason = "remote-command-exited"
        self.begin_close(reason)
        self._publish(replace(self.state, phase="closed", exit_code=exit_code, exit_status=exit_status))

    def _poll_socket(self) -> None:
        if self.state.phase not in _PROBE_PHASES or self._check.state() != QProcess.ProcessState.NotRunning:
            return
        try:
            is_socket = stat.S_ISSOCK(Path(self.socket_path).lstat().st_mode)
        except OSError:
            is_socket = False
        if not is_socket:
            if self.state.phase == "connected":
                self._check_failed()
            return
        self._checking = True
        self._timeout.start(_CHECK_TIMEOUT_MS)
        self._check.start()

    def _cancel_check(self) -> None:
        self._checking = False
        self._timeout.stop()
        if self._check.state() != QProcess.ProcessState.NotRunning:
            self._check.kill()

    def _check_finished(self, exit_code: int, exit_status: QProcess.ExitStatus) -> None:
        if not self._checking:
            return
        self._checking = False
        self._timeout.stop()
        if exit_code != 0 or exit_status != QProcess.ExitStatus.NormalExit:
            self._check_failed()
            return
        self._publish(replace(self.state, phase="connected", disconnect_reason=None))
        self._poll.setInterval(_HEALTH_CHECK_MS)

    def _check_error(self, _error: QProcess.ProcessError) -> None:
        if self._checking:
            self._cancel_check()
            self._check_failed()

    def _check_timed_out(self) -> None:
        self._cancel_check()
        self._check_failed()

    def _check_failed(self) -> None:
        if self.state.phase == "connected":
            self._publish(replace(self.state, phase="connection-lost", disconnect_reason="control-master-lost"))
        # A stale control socket can fail repeatedly. Bound local process churn
        # while allowing a later successful authentication to recover the state.
        self._poll.setInterval(_HEALTH_CHECK_MS)

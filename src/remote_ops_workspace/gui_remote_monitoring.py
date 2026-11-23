from __future__ import annotations

import ntpath
import time
from collections.abc import Callable
from typing import TYPE_CHECKING, Any

from PyQt6.QtCore import QProcess, QTimer
from PyQt6.QtWidgets import QAbstractButton

from .gui_designs import gui_design_moba_remote_monitoring_dock_chrome
from .moba_connected import (
    MobaConnectedSessionState,
    RemoteMonitoringSnapshot,
    parse_remote_monitoring_output,
)
from .terminal import (
    openssh_command_with_overrides,
    openssh_command_without_windows_connection_sharing,
    ssh_command_with_control_path,
)

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QFrame as _MonitoringHost

    from .gui_connected import ConnectedMainWindow
else:
    _MonitoringHost = object


class RemoteMonitoringRuntime(_MonitoringHost):
    """Run nonblocking SSH telemetry queries for the connected dock."""

    if TYPE_CHECKING:
        state: MobaConnectedSessionState
        runtime_shutting_down: bool
        monitoring_control_widgets: dict[str, QAbstractButton]
        background_auth_retry_attempt: int
        background_auth_retry_timer: QTimer
        _background_auth_prompt_buffers: dict[str, bytearray]
        _background_auth_prompt_complete: dict[str, bool]

        def main_window(self) -> ConnectedMainWindow | None: ...
        def set_remote_monitoring_expanded(self, expanded: bool) -> None: ...
        def set_remote_monitoring_status(self, message: str, *, state: str) -> None: ...
        def _waiting_for_shared_ssh(self) -> bool: ...
        def ensure_background_authentication_for_request(self, *, allow_prompt: bool = False) -> bool: ...
        def background_ssh_overrides(self) -> dict[str, str]: ...
        def shared_ssh_control_path(self) -> str: ...
        def _submit_background_password_if_prompt(self, process_kind: str, payload: bytes) -> None: ...
        def schedule_background_auth_retry(self, *, waiting_for_smartcard: bool = False) -> None: ...
        def apply_live_remote_monitoring_snapshot(self, snapshot: RemoteMonitoringSnapshot) -> bool: ...

    def initialize_monitoring_runtime(self, process_factory: Callable[..., Any]) -> None:
        self.monitoring_output_buffer = bytearray()
        self.monitoring_generation = 0
        self.monitoring_active_generation = 0
        self._monitoring_manual_request = False
        self.monitoring_refresh_timer = QTimer(self)
        self.monitoring_refresh_timer.setInterval(
            gui_design_moba_remote_monitoring_dock_chrome().refresh_seconds * 1000
        )
        self.monitoring_refresh_timer.timeout.connect(
            self.request_remote_monitoring_refresh
        )
        # Monitoring is periodic and must never open a visible interactive
        # prompt. Reusing the active SSH control path or configured key/
        # agent remains non-interactive; a session-only password may use
        # the hidden PTY transport after an explicit manual auth action.
        self.monitoring_process = process_factory(self, interactive_auth=True)
        self.monitoring_process.setProperty(
            "mobaMonitoringNonInteractive",
            True,
        )
        self.monitoring_process.setProcessChannelMode(
            QProcess.ProcessChannelMode.MergedChannels
        )
        self.monitoring_process.readyReadStandardOutput.connect(
            self.read_remote_monitoring_output
        )
        self.monitoring_process.finished.connect(
            self.handle_remote_monitoring_finished
        )
        self.monitoring_process.errorOccurred.connect(
            self.handle_remote_monitoring_error
        )

    def activate_initial_monitoring_state(self) -> None:
        control = self.monitoring_control_widgets.get("remote-monitoring")
        self.set_remote_monitoring_runtime(
            bool(control is not None and control.isChecked()),
            immediate=True,
        )

    def monitoring_surface_is_current(self) -> bool:
        if self.runtime_shutting_down:
            return False
        main_window = self.main_window()
        if main_window is not None and hasattr(main_window, "moba_connected_dock"):
            return main_window.moba_connected_dock is self
        return True

    def remote_monitoring_request_is_current(self) -> bool:
        control = self.monitoring_control_widgets.get("remote-monitoring")
        return (
            self.monitoring_surface_is_current()
            and self.monitoring_active_generation != 0
            and self.monitoring_active_generation
            == self.monitoring_generation
            and control is not None
            and (control.isChecked() or self._monitoring_manual_request)
        )

    def _invalidate_monitoring_request(self) -> None:
        self.monitoring_generation += 1
        self.monitoring_active_generation = 0
        self._monitoring_manual_request = False

    def set_remote_monitoring_runtime(
        self,
        enabled: bool,
        *,
        immediate: bool,
        start_periodic: bool = True,
    ) -> None:
        active = bool(enabled)
        self.set_remote_monitoring_expanded(active)
        for widget in (
            self,
            getattr(self, "browser", None),
            getattr(self, "remote_monitoring_panel", None),
            getattr(self, "remote_monitoring_controls", None),
        ):
            if widget is not None:
                widget.setProperty(
                    "mobaRemoteMonitoringRuntimeActive",
                    active,
                )
        refresh_button = getattr(self, "monitoring_refresh_button", None)
        if refresh_button is not None:
            # Manual refresh is also the recovery path for password-only
            # SSH on Windows, so it must remain usable while the periodic
            # toggle is paused.
            refresh_button.setEnabled(True)
        if active:
            if start_periodic and not self.monitoring_refresh_timer.isActive():
                self.monitoring_refresh_timer.start()
            self.set_remote_monitoring_status(
                "Monitoring on · waiting for live data",
                state="starting",
            )
            if immediate:
                QTimer.singleShot(0, self.request_remote_monitoring_refresh)
            return
        self._invalidate_monitoring_request()
        self.monitoring_refresh_timer.stop()
        if self.monitoring_process.state() != QProcess.ProcessState.NotRunning:
            self.monitoring_process.kill()
        self.set_remote_monitoring_status("Monitoring off", state="paused")

    def monitoring_runtime_command(self) -> list[str]:
        command = list(self.state.monitoring_plan.command)
        if not command:
            return command
        executable = ntpath.basename(command[0]).lower()
        if executable in {"ssh", "ssh.exe"}:
            command = openssh_command_without_windows_connection_sharing(command)
            command = openssh_command_with_overrides(command, self.background_ssh_overrides())
            control_path = self.shared_ssh_control_path()
            if control_path:
                command = ssh_command_with_control_path(
                    command,
                    control_path,
                    master=False,
                )
        return command

    def request_remote_monitoring_refresh(
        self,
        *_args,
        allow_prompt: bool = False,
    ) -> None:
        if self.runtime_shutting_down or not self.monitoring_surface_is_current():
            return
        control = self.monitoring_control_widgets.get("remote-monitoring")
        manual_request = bool(allow_prompt)
        if control is None or (not control.isChecked() and not manual_request):
            return
        if not manual_request and self._waiting_for_shared_ssh():
            self.set_remote_monitoring_status(
                "Monitoring is waiting for the managed SSH connection",
                state="auth-required",
            )
            return
        if manual_request:
            auth_ready = self.ensure_background_authentication_for_request(
                allow_prompt=True,
            )
        else:
            auth_ready = self.ensure_background_authentication_for_request()
        if not auth_ready:
            if manual_request:
                self.set_remote_monitoring_status(
                    "Monitoring authentication required",
                    state="auth-required",
                )
                return
            self.setProperty("mobaBackgroundSshApplyingAuthGate", True)
            try:
                control.setChecked(False)
            finally:
                self.setProperty("mobaBackgroundSshApplyingAuthGate", False)
            return
        self._monitoring_manual_request = manual_request and not control.isChecked()
        count = int(
            self.property("mobaRemoteMonitoringRefreshRequestCount") or 0
        ) + 1
        for widget in (
            self,
            getattr(self, "remote_monitoring_panel", None),
            control,
        ):
            if widget is not None:
                widget.setProperty(
                    "mobaRemoteMonitoringRefreshRequestCount",
                    count,
                )
        if self.monitoring_process.state() != QProcess.ProcessState.NotRunning:
            self.set_remote_monitoring_status(
                "Monitoring refresh already running",
                state="refreshing",
            )
            return
        command = self.monitoring_runtime_command()
        if not command:
            self.set_remote_monitoring_status(
                "Monitoring unavailable: empty command",
                state="error",
            )
            return
        self.monitoring_output_buffer.clear()
        self.monitoring_generation += 1
        self.monitoring_active_generation = self.monitoring_generation
        self._background_auth_prompt_buffers["monitoring"].clear()
        self._background_auth_prompt_complete["monitoring"] = False
        self.set_remote_monitoring_status(
            "Refreshing live telemetry…",
            state="refreshing",
        )
        self.monitoring_process.setProgram(command[0])
        self.monitoring_process.setArguments(command[1:])
        self.monitoring_process.start()

    def read_remote_monitoring_output(self) -> None:
        payload = bytes(self.monitoring_process.readAllStandardOutput())
        self._submit_background_password_if_prompt("monitoring", payload)
        self.monitoring_output_buffer.extend(payload)

    def handle_remote_monitoring_error(self, error) -> None:
        request_is_current = self.remote_monitoring_request_is_current()
        self.monitoring_active_generation = 0
        self._monitoring_manual_request = False
        if not request_is_current:
            return
        self.set_remote_monitoring_status(
            f"Monitoring error: {error.name}",
            state="error",
        )
        self.setProperty("mobaRemoteMonitoringLastError", error.name)
        self.schedule_background_auth_retry()

    def handle_remote_monitoring_finished(
        self,
        exit_code: int,
        _exit_status: QProcess.ExitStatus,
    ) -> None:
        request_is_current = self.remote_monitoring_request_is_current()
        self.read_remote_monitoring_output()
        output = self.monitoring_output_buffer.decode(errors="replace")
        self.monitoring_active_generation = 0
        self._monitoring_manual_request = False
        if not request_is_current:
            return
        snapshot = parse_remote_monitoring_output(output) if exit_code == 0 else None
        if snapshot is None:
            detail = next(
                (line.strip() for line in reversed(output.splitlines()) if line.strip()),
                f"exit {exit_code}",
            )
            if "permission denied" in detail.lower() and "password" in detail.lower():
                detail = (
                    "password-only SSH cannot run background monitoring; "
                    "configure key or agent authentication"
                )
            elif "host key verification failed" in detail.lower():
                detail = (
                    "host key not trusted; verify it in the terminal, then refresh"
                )
            shared_control = self.shared_ssh_control_path()
            self.set_remote_monitoring_status(
                (
                    f"Waiting for terminal SSH authentication: {detail[:120]}"
                    if shared_control
                    else f"Monitoring unavailable: {detail[:120]}"
                ),
                state="auth-required" if shared_control else "error",
            )
            self.setProperty("mobaRemoteMonitoringLastError", detail)
            self.schedule_background_auth_retry()
            return
        if not self.apply_live_remote_monitoring_snapshot(snapshot):
            return
        refreshed_at = time.strftime("%H:%M:%S")
        last_refresh = getattr(self, "monitoring_last_refresh_label", None)
        if last_refresh is not None:
            last_refresh.setText(refreshed_at)
            last_refresh.setToolTip(f"Last successful refresh: {refreshed_at}")
        self.setProperty("mobaRemoteMonitoringLastRefresh", refreshed_at)
        self.background_auth_retry_attempt = 0
        self.background_auth_retry_timer.stop()
        self.setProperty("mobaBackgroundSshWaitingForTerminalAuth", False)
        self.set_remote_monitoring_status(
            f"Live · {refreshed_at}",
            state="live",
        )

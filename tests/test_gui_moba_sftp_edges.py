from __future__ import annotations

import os
from dataclasses import replace
from types import SimpleNamespace

import pytest

from remote_ops_workspace.models import Profile
from remote_ops_workspace.terminal import TerminalPanePlan


class _FakeProcess:
    def __init__(
        self,
        *,
        running: bool = False,
        output: bytes = b"",
        write_result: int | None = None,
    ) -> None:
        from PyQt6.QtCore import QProcess

        self.process_state = (
            QProcess.ProcessState.Running
            if running
            else QProcess.ProcessState.NotRunning
        )
        self.output = output
        self.write_result = write_result
        self.program = ""
        self.arguments: list[str] = []
        self.start_calls = 0
        self.kill_calls = 0
        self.close_write_calls = 0
        self.close_calls = 0
        self.written = b""
        self.signals_blocked = False

    def state(self):
        return self.process_state

    def setProgram(self, program: str) -> None:  # noqa: N802
        self.program = program

    def setArguments(self, arguments: list[str]) -> None:  # noqa: N802
        self.arguments = list(arguments)

    def start(self) -> None:
        from PyQt6.QtCore import QProcess

        self.start_calls += 1
        self.process_state = QProcess.ProcessState.Running

    def kill(self) -> None:
        from PyQt6.QtCore import QProcess

        self.kill_calls += 1
        self.process_state = QProcess.ProcessState.NotRunning

    def write(self, payload: bytes) -> int:
        self.written += payload
        return len(payload) if self.write_result is None else self.write_result

    def closeWriteChannel(self) -> None:  # noqa: N802
        self.close_write_calls += 1

    def blockSignals(self, blocked: bool) -> None:  # noqa: N802
        self.signals_blocked = bool(blocked)

    def close(self) -> None:
        self.close_calls += 1

    def readAllStandardOutput(self) -> bytes:  # noqa: N802
        payload, self.output = self.output, b""
        return payload


@pytest.fixture
def connected_workspace(monkeypatch, tmp_path):
    if "QT_QPA_PLATFORM" not in os.environ:
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("ROW_HOME", str(tmp_path / "row-home"))
    pytest.importorskip("PyQt6")
    from remote_ops_workspace.gui import create_main_window

    app, window = create_main_window(
        ["gui-moba-sftp-edges"],
        show=False,
        preview_samples=False,
    )
    window.resize(1100, 760)
    window.show()
    design_index = window.design_select.findData("mobaxterm")
    assert design_index >= 0
    window.design_select.setCurrentIndex(design_index)
    profile = Profile(
        name="dock-edge",
        protocol="ssh",
        host="dock-edge.example.invalid",
        username="operator",
    )
    panel = window.open_moba_connected_session_tab(
        profile,
        TerminalPanePlan(title="dock-edge", command=[], source="test"),
    )
    app.processEvents()
    dock = window.moba_connected_dock
    assert dock is not None
    control = dock.monitoring_control_widgets["remote-monitoring"]
    control.blockSignals(True)
    control.setChecked(False)
    control.blockSignals(False)
    dock.set_remote_monitoring_runtime(False, immediate=False)
    yield app, window, panel, dock, profile
    dock.shutdown_runtime()
    window.close()
    app.processEvents()


def _set_checked(control, checked: bool) -> None:
    control.blockSignals(True)
    control.setChecked(checked)
    control.blockSignals(False)


def test_connected_session_falls_back_when_browser_preferences_are_corrupt(
    connected_workspace,
    monkeypatch,
) -> None:
    from remote_ops_workspace import gui

    _app, window, _panel, _dock, profile = connected_workspace
    monkeypatch.setattr(
        gui,
        "load_moba_ssh_browser_preferences",
        lambda: (_ for _ in ()).throw(ValueError("corrupt browser preferences")),
    )
    shown = []
    monkeypatch.setattr(window, "show_moba_connected_dock", shown.append)
    panel = window.open_moba_connected_session_tab(
        profile,
        TerminalPanePlan(title="preference-fallback", command=[], source="test"),
    )
    assert panel.moba_connected_state.profile_name == profile.name
    assert shown and shown[-1] is panel.moba_connected_state
    panel.terminal_pane.prepare_for_close()


def test_monitoring_stale_completion_and_absent_sftp_status_widgets(
    connected_workspace,
    monkeypatch,
) -> None:
    from PyQt6.QtCore import QEvent, QPointF, QProcess, Qt
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtWidgets import QLabel

    from remote_ops_workspace import gui

    _app, window, _panel, dock, _profile = connected_workspace
    runtime_calls: list[tuple[bool, bool]] = []
    monkeypatch.setattr(
        dock,
        "set_remote_monitoring_runtime",
        lambda enabled, *, immediate: runtime_calls.append((enabled, immediate)),
    )
    dock.activate_initial_monitoring_state()
    assert runtime_calls == [(False, True)]

    monkeypatch.setattr(dock, "remote_monitoring_request_is_current", lambda: False)
    monkeypatch.setattr(dock, "read_remote_monitoring_output", lambda: None)
    dock.monitoring_output_buffer = b"stale output"
    dock.monitoring_active_generation = 42
    dock.handle_remote_monitoring_finished(0, QProcess.ExitStatus.NormalExit)
    assert dock.monitoring_active_generation == 0

    snapshot = object()
    monkeypatch.setattr(dock, "remote_monitoring_request_is_current", lambda: True)
    monkeypatch.setattr(gui, "parse_remote_monitoring_output", lambda _output: snapshot)
    monkeypatch.setattr(dock, "apply_live_remote_monitoring_snapshot", lambda value: value is snapshot)
    original_last_refresh_label = dock.monitoring_last_refresh_label
    dock.monitoring_last_refresh_label = None
    dock.monitoring_output_buffer = b"valid"
    dock.handle_remote_monitoring_finished(0, QProcess.ExitStatus.NormalExit)
    assert dock.property("mobaRemoteMonitoringLastRefresh")
    dock.monitoring_last_refresh_label = original_last_refresh_label

    original_badge = dock.sftp_status_badge
    original_browser = dock.browser
    original_table = dock.file_table
    dock.sftp_status_badge = None
    dock.browser = None
    dock.file_table = None
    dock.set_sftp_runtime_status("Detached", state="pending")
    assert dock.property("mobaSftpRuntimeState") == "pending"
    dock.sftp_status_badge = original_badge
    dock.browser = original_browser
    dock.file_table = original_table

    label = next(
        item
        for item in window.findChildren(QLabel, "mobaRailLabel")
        if hasattr(item, "button")
    )
    event = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        QPointF(-5, -5),
        QPointF(-5, -5),
        Qt.MouseButton.RightButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    label.mouseReleaseEvent(event)


def test_background_authentication_and_prompt_submission_edges(
    connected_workspace,
    monkeypatch,
) -> None:
    from PyQt6.QtCore import QProcess
    from PyQt6.QtWidgets import QInputDialog

    from remote_ops_workspace import vault

    app, window, _panel, dock, profile = connected_workspace
    dock.profile_for_sftp_action = lambda: None
    assert dock.authenticate_background_tools() is False

    dock.profile_for_sftp_action = lambda: profile
    dock.background_auth_password_supported = lambda: False
    assert dock.authenticate_background_tools() is False

    dock.background_auth_password_supported = lambda: True
    responses = iter([("", False), ("", True), ("session-secret", True)])
    monkeypatch.setattr(
        QInputDialog,
        "getText",
        staticmethod(lambda *_args, **_kwargs: next(responses)),
    )
    assert dock.authenticate_background_tools() is False
    assert dock.authenticate_background_tools() is False
    activations: list[bool] = []
    dock._apply_initial_background_state = (
        lambda *, start_runtime: activations.append(start_runtime)
    )
    assert dock.authenticate_background_tools() is True
    assert bytes(dock._background_password or b"") == b"session-secret"
    assert dock.property("mobaBackgroundSshCredentialSource") == "session-prompt"
    assert activations == [True]

    vault_profile = replace(profile, credential_ref="vault-key")
    dock.profile_for_sftp_action = lambda: vault_profile
    vault_responses = iter(
        [
            ("", False),
            ("", True),
            ("bad-passphrase", True),
            ("empty-secret", True),
            ("valid-passphrase", True),
        ]
    )
    monkeypatch.setattr(
        QInputDialog,
        "getText",
        staticmethod(lambda *_args, **_kwargs: next(vault_responses)),
    )

    class _Vault:
        calls = 0

        def get(self, _name: str, _prompt: str) -> str:
            type(self).calls += 1
            if self.calls == 1:
                raise ValueError("controlled vault failure")
            if self.calls == 2:
                return ""
            return "vault-secret"

    monkeypatch.setattr(vault, "LocalVault", _Vault)
    assert dock.authenticate_background_tools() is False
    assert dock.authenticate_background_tools() is False
    assert dock.authenticate_background_tools() is False
    assert dock.authenticate_background_tools() is False
    assert dock.authenticate_background_tools() is True
    assert bytes(dock._background_password or b"") == b"vault-secret"
    assert dock.property("mobaBackgroundSshCredentialSource") == "encrypted-vault"

    dock._clear_background_password()
    monitoring = _FakeProcess(running=True, write_result=0)
    sftp = _FakeProcess(running=True)
    dock.monitoring_process = monitoring
    dock.sftp_refresh_process = sftp
    dock._submit_background_password_if_prompt("monitoring", b"password: ")
    dock._background_password = bytearray(b"pw")
    dock._submit_background_password_if_prompt("unknown", b"password: ")
    dock._background_auth_password_sent["monitoring"] = True
    dock._submit_background_password_if_prompt("monitoring", b"password: ")
    dock._background_auth_password_sent["monitoring"] = False
    dock._submit_background_password_if_prompt("monitoring", b"ordinary output")
    dock._submit_background_password_if_prompt("monitoring", b"password: ")
    assert dock._background_auth_password_sent["monitoring"] is False
    monitoring.write_result = None
    dock._submit_background_password_if_prompt("monitoring", b"password: ")
    assert dock._background_auth_password_sent["monitoring"] is True

    forced_batches: list[bool] = []
    dock.write_sftp_refresh_batch = lambda *, force=False: forced_batches.append(force)
    dock._background_auth_password_sent["sftp"] = False
    dock._submit_background_password_if_prompt("sftp", b"Passphrase for key: ")
    app.processEvents()
    assert dock._background_auth_password_sent["sftp"] is True
    assert forced_batches == [True]
    assert monitoring.state() == QProcess.ProcessState.Running


def test_background_auth_capability_gate_and_retry_edges(
    connected_workspace,
    monkeypatch,
    tmp_path,
) -> None:
    _app, _window, _panel, dock, profile = connected_workspace
    dock._clear_background_password()
    monkeypatch.delenv("SSH_AUTH_SOCK", raising=False)
    monkeypatch.setattr(dock, "shared_ssh_control_path", lambda: "")
    monkeypatch.setattr(dock, "background_auth_password_supported", lambda: True)

    assert dock.background_ssh_auth_capability(None) == (
        False,
        "connected profile was not found",
    )
    dock._background_password = bytearray(b"session-secret")
    assert dock.background_ssh_auth_capability(profile)[0] is True
    dock._clear_background_password()

    monkeypatch.setattr(dock, "shared_ssh_control_path", lambda: "control-path")
    assert "shared control socket" in dock.background_ssh_auth_capability(profile)[1]
    monkeypatch.setattr(dock, "shared_ssh_control_path", lambda: "")

    identity = tmp_path / "id_ed25519"
    identity.write_text("test-only-key", encoding="utf-8")
    assert dock.background_ssh_auth_capability(
        replace(profile, identity_file=str(identity))
    )[0] is True
    missing_identity = tmp_path / "missing-key"
    missing = dock.background_ssh_auth_capability(
        replace(profile, identity_file=str(missing_identity))
    )
    assert missing[0] is False
    assert "was not found" in missing[1]

    agent_profile = replace(profile, options={"identity_agent": "agent.sock"})
    assert dock.background_ssh_auth_capability(agent_profile)[0] is True
    monkeypatch.setenv("SSH_AUTH_SOCK", "agent.sock")
    assert dock.background_ssh_auth_capability(profile)[0] is True
    monkeypatch.delenv("SSH_AUTH_SOCK")
    explicit_agent = replace(profile, options={"background_auth": "YES"})
    assert dock.background_ssh_auth_capability(explicit_agent)[0] is True
    unavailable, detail = dock.background_ssh_auth_capability(profile)
    assert unavailable is False
    assert "Authenticate background tools" in detail

    monkeypatch.setattr(dock, "profile_for_sftp_action", lambda: None)
    assert dock.ensure_background_authentication_for_request() is True
    monkeypatch.setattr(dock, "profile_for_sftp_action", lambda: profile)
    monkeypatch.setattr(
        dock,
        "background_ssh_auth_capability",
        lambda _profile: (True, "agent ready"),
    )
    assert dock.ensure_background_authentication_for_request() is True
    prompted: list[str] = []
    monkeypatch.setattr(
        dock,
        "background_ssh_auth_capability",
        lambda _profile: (False, "auth unavailable"),
    )
    monkeypatch.setattr(
        dock,
        "authenticate_background_tools",
        lambda: prompted.append("prompt") or True,
    )
    assert dock.ensure_background_authentication_for_request(allow_prompt=True) is True
    assert prompted == ["prompt"]
    assert dock.ensure_background_authentication_for_request() is False
    assert dock.property("mobaSftpRuntimeState") == "auth-required"

    events: list[tuple[str, object]] = []
    control = dock.monitoring_control_widgets["remote-monitoring"]
    monkeypatch.setattr(dock, "profile_for_sftp_action", lambda: profile)
    monkeypatch.setattr(
        dock,
        "set_sftp_runtime_status",
        lambda message, *, state: events.append(("sftp", (message, state))),
    )
    monkeypatch.setattr(
        dock,
        "set_remote_monitoring_status",
        lambda message, *, state: events.append(("monitor-status", (message, state))),
    )
    monkeypatch.setattr(
        dock,
        "set_remote_monitoring_runtime",
        lambda enabled, **kwargs: events.append(
            ("monitor-runtime", (enabled, kwargs))
        ),
    )
    monkeypatch.setattr(
        dock,
        "request_sftp_refresh",
        lambda *, reason="manual": events.append(("refresh", reason)),
    )
    monkeypatch.setattr(
        dock,
        "activate_initial_monitoring_state",
        lambda: events.append(("monitor-activate", True)),
    )

    dock.runtime_shutting_down = True
    dock._apply_initial_background_state(start_runtime=True)
    assert events == []
    dock.runtime_shutting_down = False

    monkeypatch.setattr(
        dock,
        "background_ssh_auth_capability",
        lambda _profile: (False, "auth unavailable"),
    )
    _set_checked(control, True)
    dock._apply_initial_background_state(start_runtime=True)
    assert control.isChecked() is False
    assert dock.property("mobaBackgroundSshWaitingForTerminalAuth") is True
    assert dock.property("mobaBackgroundSshAuthGateForcedMonitoringOff") is True

    events.clear()
    monkeypatch.setattr(
        dock,
        "background_ssh_auth_capability",
        lambda _profile: (True, "agent ready"),
    )
    dock._apply_initial_background_state(start_runtime=False)
    assert any(key == "monitor-runtime" for key, _value in events)
    assert not any(key == "refresh" for key, _value in events)

    events.clear()
    dock.setProperty("mobaBackgroundSshAuthGateForcedMonitoringOff", True)
    _set_checked(control, False)
    monkeypatch.setattr(dock, "shared_ssh_control_path", lambda: "control-path")
    dock._apply_initial_background_state(start_runtime=True)
    assert control.isChecked() is True
    assert ("refresh", "initial-key-agent-auth") in events
    assert not any(key == "monitor-activate" for key, _value in events)

    events.clear()
    dock.setProperty("mobaBackgroundSshAuthGateForcedMonitoringOff", False)
    monkeypatch.setattr(dock, "shared_ssh_control_path", lambda: "")
    dock._apply_initial_background_state(start_runtime=True)
    assert ("monitor-activate", True) in events

    activations: list[str] = []
    monkeypatch.setattr(
        dock,
        "activate_initial_background_state",
        lambda: activations.append("activate"),
    )
    dock.runtime_shutting_down = True
    dock.retry_background_authentication()
    dock.runtime_shutting_down = False
    dock.setProperty("mobaBackgroundSshWaitingForTerminalAuth", False)
    dock.retry_background_authentication()
    dock.setProperty("mobaBackgroundSshWaitingForTerminalAuth", True)
    dock.retry_background_authentication()
    assert activations == ["activate"]


def test_sftp_navigation_widget_contract_and_reconnect_guards(
    connected_workspace,
    monkeypatch,
) -> None:
    from PyQt6.QtWidgets import QWidget

    from remote_ops_workspace import gui

    app, window, _panel, dock, profile = connected_workspace
    original_browser = dock.browser
    original_table = dock.file_table
    original_queue = dock.sftp_transfer_queue
    _set_checked(dock.monitoring_control_widgets["follow-terminal-folder"], False)

    monkeypatch.setattr(gui, "normalise_remote_path", lambda _path: "relative/path")
    dock.browser = None
    assert dock.navigate_moba_sftp_path("relative/path") is True
    assert dock.active_remote_path == "/relative/path"

    class _SparseTable:
        properties: dict[str, object] = {}

        def setProperty(self, name: str, value: object) -> None:  # noqa: N802
            self.properties[name] = value

        @staticmethod
        def topLevelItemCount() -> int:  # noqa: N802
            return 1

        @staticmethod
        def topLevelItem(_index: int):  # noqa: N802
            return None

    dock.browser = original_browser
    dock.file_table = _SparseTable()
    del dock.sftp_transfer_queue
    assert dock.navigate_moba_sftp_path("/sparse") is True
    dock.file_table = original_table
    dock.sftp_transfer_queue = original_queue

    monkeypatch.setattr(dock, "main_window", lambda: None)
    assert dock.reconnect_moba_sftp_session() is False
    monkeypatch.setattr(dock, "main_window", lambda: window)
    monkeypatch.setattr(window, "terminal_panes_in", lambda _current: [])
    assert dock.reconnect_moba_sftp_session() is False

    output = QWidget(window)
    restart_calls: list[str] = []
    pane = SimpleNamespace(
        profile=profile,
        output=output,
        restart=lambda: restart_calls.append("restart"),
        is_running=lambda: False,
    )
    monkeypatch.setattr(window, "terminal_panes_in", lambda _current: [pane])
    assert dock.reconnect_moba_sftp_session() is True
    app.processEvents()
    assert restart_calls == ["restart"]
    assert output.property("mobaTerminalFocusRequested") is True


def test_monitoring_refresh_generation_and_snapshot_edges(
    connected_workspace,
    monkeypatch,
) -> None:
    from PyQt6.QtCore import QProcess

    from remote_ops_workspace import gui

    _app, window, panel, dock, _profile = connected_workspace
    control = dock.monitoring_control_widgets["remote-monitoring"]
    process = _FakeProcess()
    dock.monitoring_process = process

    dock.runtime_shutting_down = True
    dock.request_remote_monitoring_refresh()
    dock.runtime_shutting_down = False
    dock.monitoring_surface_is_current = lambda: False
    dock.request_remote_monitoring_refresh()
    dock.monitoring_surface_is_current = lambda: True

    saved_control = dock.monitoring_control_widgets.pop("remote-monitoring")
    dock.request_remote_monitoring_refresh()
    dock.monitoring_control_widgets["remote-monitoring"] = saved_control
    _set_checked(control, False)
    dock.request_remote_monitoring_refresh()

    _set_checked(control, True)
    dock.ensure_background_authentication_for_request = lambda **_kwargs: False
    dock.request_remote_monitoring_refresh()
    assert control.isChecked() is False
    assert dock.property("mobaBackgroundSshApplyingAuthGate") is False

    _set_checked(control, True)
    dock.ensure_background_authentication_for_request = lambda **_kwargs: True
    process.process_state = QProcess.ProcessState.Running
    dock.request_remote_monitoring_refresh()
    assert "already running" in dock.monitoring_status_label.text()

    process.process_state = QProcess.ProcessState.NotRunning
    dock.monitoring_runtime_command = lambda: []
    dock.request_remote_monitoring_refresh()
    assert "empty command" in dock.monitoring_status_label.text()

    dock.monitoring_runtime_command = lambda: ["ssh", "monitor.example.invalid", "uptime"]
    dock.request_remote_monitoring_refresh()
    assert process.start_calls == 1
    assert process.program == "ssh"
    assert process.arguments[-1] == "uptime"
    assert dock.monitoring_active_generation == dock.monitoring_generation

    dock.remote_monitoring_request_is_current = lambda: False
    dock.monitoring_active_generation = 1
    dock.handle_remote_monitoring_error(QProcess.ProcessError.Timedout)
    assert dock.monitoring_active_generation == 0

    dock.remote_monitoring_request_is_current = lambda: True
    dock.handle_remote_monitoring_error(QProcess.ProcessError.ReadError)
    assert dock.property("mobaRemoteMonitoringLastError") == "ReadError"

    retries: list[str] = []
    dock.schedule_background_auth_retry = lambda: retries.append("retry")
    monkeypatch.setattr(gui, "parse_remote_monitoring_output", lambda _output: None)
    dock.shared_ssh_control_path = lambda: ""
    process.output = b"Permission denied (password).\n"
    dock.monitoring_output_buffer.clear()
    dock.handle_remote_monitoring_finished(1, QProcess.ExitStatus.CrashExit)
    assert "password-only SSH" in dock.property("mobaRemoteMonitoringLastError")

    dock.shared_ssh_control_path = lambda: "control-path"
    process.output = b"Host key verification failed\n"
    dock.monitoring_output_buffer.clear()
    dock.handle_remote_monitoring_finished(1, QProcess.ExitStatus.CrashExit)
    assert "host key not trusted" in dock.property("mobaRemoteMonitoringLastError")
    assert retries == ["retry", "retry"]

    snapshot = dock.state.monitoring
    monkeypatch.setattr(gui, "parse_remote_monitoring_output", lambda _output: snapshot)
    dock.apply_live_remote_monitoring_snapshot = lambda _snapshot: False
    process.output = b"valid"
    dock.monitoring_output_buffer.clear()
    dock.handle_remote_monitoring_finished(0, QProcess.ExitStatus.NormalExit)

    dock.apply_live_remote_monitoring_snapshot = lambda _snapshot: True
    process.output = b"valid"
    dock.monitoring_output_buffer.clear()
    dock.handle_remote_monitoring_finished(0, QProcess.ExitStatus.NormalExit)
    assert dock.property("mobaRemoteMonitoringLastRefresh")
    assert dock.monitoring_status_label.property("state") == "live"

    real_apply = type(dock).apply_live_remote_monitoring_snapshot
    dock.monitoring_surface_is_current = lambda: False
    assert real_apply(dock, snapshot) is False
    dock.monitoring_surface_is_current = lambda: True
    original_main_window = dock.main_window
    dock.main_window = lambda: None
    assert real_apply(dock, snapshot) is True
    dock.main_window = original_main_window
    window.tabs.setCurrentWidget(panel)
    assert real_apply(dock, snapshot) is True
    assert panel.telemetry_bar.property("mobaTelemetryDataSource") == "live-ssh"

    menu = dock.build_remote_monitoring_context_menu()
    labels = [action.text() for action in menu.actions() if not action.isSeparator()]
    assert "Refresh now" in labels
    assert "Authenticate background tools" in labels
    assert "Copy monitoring command" in labels
    menu.deleteLater()


def test_monitoring_optional_chrome_runtime_and_command_edges(
    connected_workspace,
    monkeypatch,
) -> None:
    from PyQt6.QtCore import QProcess

    _app, _window, _panel, dock, _profile = connected_workspace
    panel = dock.remote_monitoring_panel
    controls = dock.remote_monitoring_controls
    status = dock.monitoring_status_label
    refresh = dock.monitoring_refresh_button
    last_refresh = dock.monitoring_last_refresh_label

    dock.remote_monitoring_panel = None
    dock.set_remote_monitoring_expanded(True)
    dock.remote_monitoring_panel = panel

    dock.monitoring_status_label = None
    dock.monitoring_refresh_button = None
    dock.monitoring_last_refresh_label = None
    dock.remote_monitoring_controls = None
    dock.set_remote_monitoring_expanded(True)
    dock.set_remote_monitoring_runtime(
        True,
        immediate=False,
        start_periodic=False,
    )
    assert panel.property("mobaRemoteMonitoringRuntimeRequested") is True

    dock.monitoring_status_label = status
    dock.monitoring_refresh_button = refresh
    dock.monitoring_last_refresh_label = last_refresh
    dock.remote_monitoring_controls = controls
    process = _FakeProcess(running=True)
    dock.monitoring_process = process
    dock.set_remote_monitoring_runtime(False, immediate=False)
    assert process.kill_calls == 1
    assert process.state() == QProcess.ProcessState.NotRunning

    original_state = dock.state
    empty_plan = replace(original_state.monitoring_plan, command=[])
    dock.state = replace(original_state, monitoring_plan=empty_plan)
    assert dock.monitoring_runtime_command() == []

    custom_plan = replace(
        original_state.monitoring_plan,
        command=["custom-monitor", "--once"],
    )
    dock.state = replace(original_state, monitoring_plan=custom_plan)
    assert dock.monitoring_runtime_command() == ["custom-monitor", "--once"]

    monkeypatch.setattr(dock, "shared_ssh_control_path", lambda: "")
    dock.state = original_state
    assert dock.monitoring_runtime_command()


def test_connected_dock_remaining_auth_monitoring_and_sftp_routes(
    connected_workspace,
    monkeypatch,
) -> None:
    from PyQt6.QtCore import QPoint, QProcess
    from PyQt6.QtWidgets import QTreeWidgetItem

    from remote_ops_workspace import gui
    from remote_ops_workspace.gui_designs import (
        gui_design_moba_monitoring_metrics,
        gui_design_moba_sftp_routed_file_rows,
        gui_design_moba_sftp_toolbar_action_route,
    )

    app, window, panel, dock, profile = connected_workspace
    route = gui_design_moba_sftp_toolbar_action_route()
    assert dock.moba_sftp_toolbar_action_index(route, "missing-action") == 0

    original_main_window = dock.main_window
    monkeypatch.setattr(dock, "main_window", lambda: None)
    assert dock.shared_ssh_control_path() == ""
    no_current = SimpleNamespace(
        tabs=SimpleNamespace(currentWidget=lambda: None),
    )
    monkeypatch.setattr(dock, "main_window", lambda: no_current)
    assert dock.shared_ssh_control_path() == ""

    panes = [
        SimpleNamespace(profile=None, is_running=lambda: True),
        SimpleNamespace(
            profile=Profile(name="other", protocol="ssh", host="other.invalid"),
            is_running=lambda: True,
        ),
        SimpleNamespace(profile=profile, is_running=lambda: False),
        SimpleNamespace(
            profile=profile,
            is_running=lambda: True,
            ssh_control_path="",
        ),
        SimpleNamespace(
            profile=profile,
            is_running=lambda: True,
            ssh_control_path="controlled-path",
        ),
    ]
    shared_window = SimpleNamespace(
        tabs=SimpleNamespace(currentWidget=lambda: panel),
        terminal_panes_in=lambda _current: panes,
    )
    monkeypatch.setattr(dock, "main_window", lambda: shared_window)
    assert dock.shared_ssh_control_path() == "controlled-path"
    monkeypatch.setattr(dock, "main_window", original_main_window)

    dock._background_password = bytearray(b"session-secret")
    overrides = dock.background_ssh_overrides()
    assert overrides["BatchMode"] == "no"
    assert overrides["NumberOfPasswordPrompts"] == "1"
    dock._clear_background_password()

    initialization: list[object] = []
    real_schedule = type(dock).schedule_background_state_activation
    dock.runtime_shutting_down = True
    dock.initialize_background_state()
    real_schedule(dock, 1)
    dock.runtime_shutting_down = False
    monkeypatch.setattr(
        dock,
        "_apply_initial_background_state",
        lambda *, start_runtime: initialization.append(start_runtime),
    )
    monkeypatch.setattr(
        dock,
        "schedule_background_state_activation",
        lambda delay_ms=0: initialization.append(delay_ms),
    )
    dock.initialize_background_state()
    assert initialization == [False, 0]

    original_editor = dock.text_editor
    original_save = dock.text_editor_save_button
    original_diff = dock.text_editor_diff_button
    dock.text_editor = None
    dock.handle_moba_text_editor_changed()
    dock.text_editor_save_button = None
    dock.text_editor_diff_button = None
    dock.capture_moba_text_editor_action("save", status="save-edge")
    dock.text_editor = original_editor
    dock.text_editor_save_button = original_save
    dock.text_editor_diff_button = original_diff

    routed_rows = gui_design_moba_sftp_routed_file_rows()
    renamed = QTreeWidgetItem(["old-name", "", ""])
    dock.apply_sftp_routed_file_row_metadata(
        renamed,
        routed_rows,
        row_index=8,
        name="new-name",
        selected=False,
    )
    assert renamed.text(0) == "new-name"

    dock.monitoring_active_generation = 1
    dock.monitoring_generation = 1
    monitor = dock.monitoring_control_widgets["remote-monitoring"]
    _set_checked(monitor, True)
    dock.monitoring_process = _FakeProcess(output=b"")
    monkeypatch.setattr(dock, "monitoring_surface_is_current", lambda: True)
    monkeypatch.setattr(dock, "shared_ssh_control_path", lambda: "")
    dock.handle_remote_monitoring_finished(7, QProcess.ExitStatus.CrashExit)
    assert dock.property("mobaRemoteMonitoringLastError") == "exit 7"

    missing_cell = SimpleNamespace(
        key="missing-cell",
        display_text="missing",
        label="Missing",
    )
    monkeypatch.setattr(gui, "moba_telemetry_cells", lambda _state: [missing_cell])
    window.tabs.setCurrentWidget(panel)
    assert dock.apply_live_remote_monitoring_snapshot(dock.state.monitoring) is True

    menu_calls: list[str] = []
    fake_menu = SimpleNamespace(
        exec=lambda _position: menu_calls.append("exec"),
        deleteLater=lambda: menu_calls.append("delete"),
    )
    monkeypatch.setattr(dock, "build_remote_monitoring_context_menu", lambda: fake_menu)
    dock.show_remote_monitoring_context_menu(QPoint(1, 1))
    assert menu_calls == ["exec", "delete"]

    original_browser = dock.browser
    original_monitoring_panel = dock.remote_monitoring_panel
    saved_control = dock.monitoring_control_widgets.pop("remote-monitoring")
    dock.browser = None
    dock.remote_monitoring_panel = None
    runtime_calls: list[tuple[bool, bool]] = []
    monkeypatch.setattr(
        dock,
        "set_remote_monitoring_runtime",
        lambda enabled, *, immediate: runtime_calls.append((enabled, immediate)),
    )
    dock.setProperty("mobaBackgroundSshApplyingAuthGate", False)
    dock.setProperty("mobaBackgroundSshAuthGateForcedMonitoringOff", True)
    dock.handle_moba_remote_monitoring_toggled(False)
    assert runtime_calls == [(False, False)]
    assert dock.property("mobaBackgroundSshAuthGateForcedMonitoringOff") is False
    dock.browser = original_browser
    dock.remote_monitoring_panel = original_monitoring_panel
    dock.monitoring_control_widgets["remote-monitoring"] = saved_control

    unknown_control = SimpleNamespace(key="unknown", tooltip="Unknown control")
    assert dock.monitoring_control_tooltip(unknown_control) == "Unknown control"
    unknown_metric = SimpleNamespace(source="unknown", label="Other")
    assert dock.monitoring_metric_text(unknown_metric) == "Other Unavailable"
    process_metric = next(
        metric
        for metric in gui_design_moba_monitoring_metrics()
        if metric.source == "process_count"
    )
    state = dock.state
    dock.state = replace(
        state,
        monitoring=replace(state.monitoring, process_count=None),
    )
    assert "Unavailable" in dock.monitoring_metric_text(process_metric)
    dock.state = state

    copied: list[str] = []
    monkeypatch.setattr(
        gui,
        "_QT_APPLICATION_REF",
        gui._QT_APPLICATION_REF,
    )
    clipboard = SimpleNamespace(setText=copied.append)
    application_clipboard = type(dock).copy_sftp_context_path.__closure__
    assert application_clipboard is not None
    clipboard_index = type(dock).copy_sftp_context_path.__code__.co_freevars.index(
        "_application_clipboard"
    )
    monkeypatch.setattr(
        application_clipboard[clipboard_index],
        "cell_contents",
        lambda: clipboard,
    )
    dock.copy_sftp_context_path(None)
    assert copied == [dock.active_remote_path]

    monkeypatch.setattr(dock, "main_window", lambda: None)
    assert dock.focus_moba_sftp_terminal() is False
    monkeypatch.setattr(dock, "main_window", original_main_window)

    dock.show_moba_sftp_toolbar_action("definitely-missing")
    original_queue = dock.sftp_transfer_queue
    original_toolbar = dock.toolbar
    original_path = dock.path
    original_file_table = dock.file_table
    original_buttons = dock.sftp_action_buttons
    dock.sftp_transfer_queue = None
    dock.toolbar = None
    dock.path = None
    dock.file_table = None
    dock.sftp_action_buttons = {}
    operational = next(
        action.key
        for action in gui.gui_design_moba_sftp_dock_actions()
        if action.key in dock.OPERATIONAL_ACTIONS
    )
    monkeypatch.setattr(dock, "dispatch_moba_sftp_toolbar_action", lambda _key: False)
    dock.show_moba_sftp_toolbar_action(operational)
    dock.sftp_transfer_queue = original_queue
    dock.toolbar = original_toolbar
    dock.path = original_path
    dock.file_table = original_file_table
    dock.sftp_action_buttons = original_buttons
    app.processEvents()


def test_sftp_refresh_and_transfer_workflow_edges(
    connected_workspace,
    monkeypatch,
) -> None:
    from PyQt6.QtCore import QProcess
    from PyQt6.QtWidgets import QDialog, QFileDialog

    from remote_ops_workspace import gui

    app, window, _panel, dock, profile = connected_workspace
    process = _FakeProcess()
    dock.sftp_refresh_process = process
    dock.ensure_background_authentication_for_request = lambda **_kwargs: True
    dock.profile_for_sftp_action = lambda: profile

    dock.runtime_shutting_down = True
    dock.request_sftp_refresh()
    dock.runtime_shutting_down = False
    dock.ensure_background_authentication_for_request = lambda **_kwargs: False
    dock.request_sftp_refresh()
    dock.ensure_background_authentication_for_request = lambda **_kwargs: True

    process.process_state = QProcess.ProcessState.Running
    dock.request_sftp_refresh(reason="queued")
    assert dock.sftp_refresh_pending == (dock.active_remote_path, "queued")

    process.process_state = QProcess.ProcessState.NotRunning
    dock.profile_for_sftp_action = lambda: None
    dock.request_sftp_refresh()
    assert "profile was not found" in window.statusBar().currentMessage()

    dock.profile_for_sftp_action = lambda: profile
    real_builder = gui.build_sftp_list_plan
    monkeypatch.setattr(
        gui,
        "build_sftp_list_plan",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("bad listing")),
    )
    dock.request_sftp_refresh()
    assert "bad listing" in window.statusBar().currentMessage()
    monkeypatch.setattr(gui, "build_sftp_list_plan", real_builder)

    dock.shared_ssh_control_path = lambda: ""
    dock.request_sftp_refresh(reason="manual")
    assert process.start_calls == 1
    assert dock.sftp_refresh_plan is not None
    process.process_state = QProcess.ProcessState.NotRunning
    dock.shared_ssh_control_path = lambda: "control-path"
    dock.request_sftp_refresh(reason="shared")
    assert process.start_calls == 2

    dock.runtime_shutting_down = True
    dock.write_sftp_refresh_batch()
    dock.runtime_shutting_down = False
    dock.sftp_refresh_active_generation = 0
    dock.write_sftp_refresh_batch()
    dock.sftp_refresh_active_generation = dock.sftp_refresh_generation
    dock._background_password = bytearray(b"pw")
    dock.write_sftp_refresh_batch()
    assert dock.sftp_auth_probe_timer.isActive()
    dock._background_password = None
    saved_plan = dock.sftp_refresh_plan
    dock.sftp_refresh_plan = None
    dock.write_sftp_refresh_batch(force=True)
    dock.sftp_refresh_plan = saved_plan
    process.write_result = -1
    dock.write_sftp_refresh_batch(force=True)
    assert "not accepted" in window.statusBar().currentMessage()
    process.write_result = None
    dock.write_sftp_refresh_batch(force=True)
    assert process.close_write_calls >= 2

    pending_calls: list[str] = []
    dock.schedule_pending_sftp_refresh = lambda: pending_calls.append("pending")
    dock.sftp_refresh_request_is_current = lambda: False
    process.output = b"superseded"
    dock.sftp_refresh_output_buffer.clear()
    dock.handle_sftp_refresh_finished(0, QProcess.ExitStatus.NormalExit)
    assert "superseded" in window.statusBar().currentMessage()

    dock.sftp_refresh_request_is_current = lambda: True
    dock.shared_ssh_control_path = lambda: ""
    process.output = b"permission denied"
    dock.sftp_refresh_output_buffer.clear()
    dock.handle_sftp_refresh_finished(1, QProcess.ExitStatus.CrashExit)
    assert dock.property("mobaSftpRefreshLastError") == "permission denied"
    dock.shared_ssh_control_path = lambda: "control-path"
    process.output = b"host key failed"
    dock.sftp_refresh_output_buffer.clear()
    dock.handle_sftp_refresh_finished(1, QProcess.ExitStatus.CrashExit)
    assert "Waiting for terminal SSH authentication" in window.statusBar().currentMessage()

    applied: list[tuple[list[object], str]] = []
    monkeypatch.setattr(gui, "parse_sftp_ls_output", lambda _output: [])
    dock.filtered_sftp_entries = lambda entries: list(entries)
    dock.apply_live_sftp_entries = (
        lambda entries, *, request_path, plan: applied.append(
            (list(entries), request_path)
        )
    )
    process.output = b"listing"
    dock.sftp_refresh_output_buffer.clear()
    dock.handle_sftp_refresh_finished(0, QProcess.ExitStatus.NormalExit)
    assert applied == [([], dock.sftp_refresh_request_path)]
    assert dock.property("mobaSftpRefreshLastError") == ""
    assert pending_calls

    dock.profile_for_sftp_action = lambda: None
    assert dock.open_moba_sftp_transfer_workflow("download") is False
    dock.profile_for_sftp_action = lambda: profile
    dock.selected_sftp_item = lambda: None
    assert dock.open_moba_sftp_transfer_workflow("download") is False

    class _Operations:
        def __init__(self) -> None:
            self.text = ""

        def setPlainText(self, text: str) -> None:  # noqa: N802
            self.text = text

    class _Plan:
        @staticmethod
        def printable() -> str:
            return "queue-plan"

    class _Dialog:
        def __init__(self, result) -> None:
            self.operations = _Operations()
            self.result = result
            self.preview_calls = 0
            self.run_calls = 0

        def refresh_queue_preview(self) -> None:
            self.preview_calls += 1

        def run_queue(self) -> None:
            self.run_calls += 1

        def exec(self):
            return self.result

        @staticmethod
        def queue_plan() -> _Plan:
            return _Plan()

    dialogs = iter(
        [
            _Dialog(QDialog.DialogCode.Rejected),
            _Dialog(QDialog.DialogCode.Accepted),
            _Dialog(QDialog.DialogCode.Accepted),
        ]
    )
    window.create_transfer_queue_dialog = lambda _profile: next(dialogs)
    dock.selected_sftp_item = lambda: ("report.txt", "file")
    assert dock.open_moba_sftp_transfer_workflow("download") is True
    dock.selected_sftp_item = lambda: ("archive", "dir")
    assert dock.open_moba_sftp_transfer_workflow("download") is True

    file_responses = iter([("", ""), ("C:/tmp/upload.txt", "All files (*)")])
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        staticmethod(lambda *_args, **_kwargs: next(file_responses)),
    )
    assert dock.open_moba_sftp_transfer_workflow("upload") is False
    assert dock.open_moba_sftp_transfer_workflow("upload") is True
    app.processEvents()


def test_connected_compatibility_chrome_icons_actions_and_terminal_save(
    connected_workspace,
    monkeypatch,
    tmp_path,
) -> None:
    from PyQt6.QtCore import QSize
    from PyQt6.QtWidgets import QFileDialog, QToolButton

    _app, window, panel, dock, _profile = connected_workspace
    rail = panel.build_right_utility_rail()
    controls = panel.build_session_edge_controls()
    banner_slot = panel.build_ssh_banner_slot()
    banner = panel.build_ssh_banner()

    assert rail.objectName() == "mobaRightUtilityRail"
    assert controls.objectName() == "mobaSessionEdgeControls"
    assert banner_slot.objectName() == "mobaSshBannerSlot"
    assert banner.objectName() == "mobaSshBanner"
    assert banner.findChildren(QToolButton) == []

    for button in rail.findChildren(QToolButton):
        button.click()
    for button in controls.findChildren(QToolButton):
        button.click()
    assert panel.property("mobaConnectedLastActionKey")

    for icon_key in (
        "clip",
        "spark",
        "gear",
        "arrow-left",
        "arrow-right",
        "close",
        "unknown",
    ):
        icon = panel.moba_utility_icon(icon_key, "#44cc88")
        assert not icon.pixmap(QSize(20, 20)).isNull()

    pane = panel.terminal_pane
    cancelled_then_success = iter(
        [
            ("", ""),
            (str(tmp_path / "terminal.txt"), "Text files (*.txt)"),
            (str(tmp_path / "missing" / "terminal.txt"), "Text files (*.txt)"),
        ]
    )
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        staticmethod(lambda *_args, **_kwargs: next(cancelled_then_success)),
    )
    pane.set_terminal_transcript("saved transcript\n")
    panel.save_terminal_to_file(pane)
    panel.save_terminal_to_file(pane)
    saved = tmp_path / "terminal.txt"
    assert saved.read_text(encoding="utf-8") == "saved transcript\n"
    assert panel.property("mobaTerminalSavedPath") == str(saved)
    panel.save_terminal_to_file(pane)
    assert panel.property("mobaTerminalSaveError")

    original_dock = window.moba_connected_dock
    window.moba_connected_dock = None
    assert panel.active_moba_sftp_dock() is None
    window.moba_connected_dock = original_dock
    mismatched = replace(dock.state, profile_name="different")
    dock.state = mismatched
    assert panel.active_moba_sftp_dock() is None
    dock.state = panel.state
    assert panel.active_moba_sftp_dock() is dock

    for widget in (rail, controls, banner_slot, banner):
        widget.deleteLater()


def test_connected_text_editor_open_dirty_save_diff_and_path_edges(
    connected_workspace,
    monkeypatch,
    tmp_path,
) -> None:
    from pathlib import Path

    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication, QMessageBox, QTreeWidgetItem

    from remote_ops_workspace import gui
    from remote_ops_workspace.moba_text import build_moba_text_editor_tab_plan

    _app, _window, _panel, dock, profile = connected_workspace
    cache_path = tmp_path / "service.conf.edit"
    plan = build_moba_text_editor_tab_plan(
        profile,
        "/etc/service.conf",
        local_path=cache_path,
    )
    monkeypatch.setattr(
        gui,
        "build_moba_text_editor_tab_plan",
        lambda *_args, **_kwargs: plan,
    )
    monkeypatch.setattr(dock, "profile_for_sftp_action", lambda: profile)
    monkeypatch.setattr(
        dock,
        "ensure_background_authentication_for_request",
        lambda: True,
    )
    started: list[tuple[str, object]] = []
    monkeypatch.setattr(
        dock,
        "start_text_editor_sftp_operation",
        lambda operation, transfer_plan: started.append((operation, transfer_plan)) or True,
    )
    kind_role = int(Qt.ItemDataRole.UserRole) + 42
    source_path_role = int(Qt.ItemDataRole.UserRole) + 47
    invalid = QTreeWidgetItem(["folder"])
    invalid.setData(0, kind_role, "dir")
    assert dock.text_editor_remote_path_for_item(invalid) == ""
    dock.handle_moba_text_editor_open_from_item(invalid, 0)

    empty = QTreeWidgetItem([""])
    empty.setData(0, kind_role, "file")
    assert dock.text_editor_remote_path_for_item(empty) == ""

    root_file = QTreeWidgetItem(["root.txt"])
    root_file.setData(0, kind_role, "file")
    root_file.setData(0, source_path_role, "/")
    assert dock.text_editor_remote_path_for_item(root_file) == "/root.txt"

    item = QTreeWidgetItem(["service.conf"])
    item.setData(0, kind_role, "file")
    item.setData(0, source_path_role, "/etc")
    assert dock.text_editor_remote_path_for_item(item) == "/etc/service.conf"

    editor = dock.text_editor
    dock.text_editor = None
    dock.handle_moba_text_editor_open_from_item(item, 0)
    dock.handle_moba_text_editor_changed()
    dock.capture_moba_text_editor_action("save", status="missing-editor")
    dock.text_editor = editor

    dock.handle_moba_text_editor_open_from_item(item, 0)
    assert editor.isVisible() is True
    assert editor.property("mobaTextEditorRemotePath") == "/etc/service.conf"
    assert editor.property("mobaTextEditorContentLoaded") is False
    assert dock.text_editor_save_button.isEnabled() is False
    assert started == [("open", plan.download_plan)]
    assert editor.isReadOnly() is True

    cache_path.write_text("line one\nline two\n", encoding="utf-8")
    dock.finish_text_editor_open()
    assert editor.property("mobaTextEditorContentLoaded") is True
    assert editor.isReadOnly() is False
    assert editor.toPlainText() == "line one\nline two\n"

    editor.setPlainText("line one\nline two\nunsaved replacement\n")
    dock.handle_moba_text_editor_changed()
    another_item = QTreeWidgetItem(["other.conf"])
    another_item.setData(0, kind_role, "file")
    another_item.setData(0, source_path_role, "/etc")
    monkeypatch.setattr(
        QMessageBox,
        "exec",
        lambda _self: int(QMessageBox.StandardButton.No),
    )
    started_before_cancelled_open = len(started)
    dock.handle_moba_text_editor_open_from_item(another_item, 0)
    assert len(started) == started_before_cancelled_open
    assert dock.text_editor_remote_path == "/etc/service.conf"
    assert editor.toPlainText() == "line one\nline two\nunsaved replacement\n"

    editor.setPlainText("line one\nline two\nline three\n")
    dock.handle_moba_text_editor_changed()
    assert editor.property("mobaTextEditorDirty") is True
    dock.handle_moba_text_editor_save()
    assert started[1][0] == "save-check"
    assert editor.property("mobaTextEditorDirty") is True

    Path(dock.text_editor_probe_path).write_bytes(
        cache_path.read_bytes()
    )
    dock.finish_text_editor_save_check()
    assert started[2][0] == "upload"
    assert editor.isReadOnly() is True
    assert cache_path.read_text(encoding="utf-8") == "line one\nline two\nline three\n"
    dock.finish_text_editor_upload()
    assert editor.property("mobaTextEditorCapturedSave") is True
    assert editor.property("mobaTextEditorCapturedLineCount") == 3
    assert editor.property("mobaTextEditorDirty") is False

    editor.setPlainText("line one\nline two\nline three\nline four\n")
    dock.handle_moba_text_editor_changed()
    dock.handle_moba_text_editor_save()
    assert started[3][0] == "save-check"
    Path(dock.text_editor_probe_path).write_bytes(b"remote changed\n")
    monkeypatch.setattr(
        QMessageBox,
        "exec",
        lambda _self: int(QMessageBox.StandardButton.No),
    )
    dock.finish_text_editor_save_check()
    assert len(started) == 4
    assert editor.property("mobaTextEditorStatus") == "conflict"
    assert editor.property("mobaTextEditorDirty") is True

    monkeypatch.setattr(QMessageBox, "exec", lambda _self: 0)
    dock.handle_moba_text_editor_diff()
    assert editor.property("mobaTextEditorCapturedDiff") is True
    assert editor.property("mobaTextEditorDiffEqual") is False
    assert "+line four\n" in editor.property("mobaTextEditorDiffText")

    dock.hide_moba_text_editor()
    assert editor.isVisible() is False
    toolbar = dock.text_editor_toolbar
    dock.text_editor_toolbar = None
    dock.text_editor = None
    dock.hide_moba_text_editor()
    dock.text_editor_toolbar = toolbar
    dock.text_editor = editor
    assert dock.text_editor_preview_for_remote_path("/etc/service.conf") == ""
    assert editor.textInteractionFlags() & Qt.TextInteractionFlag.TextEditable


def test_connected_text_editor_refreshes_syntax_for_each_plan(
    connected_workspace,
    tmp_path,
) -> None:
    from remote_ops_workspace.moba_text import build_moba_text_editor_tab_plan

    _app, _window, _panel, dock, profile = connected_workspace
    ini_plan = build_moba_text_editor_tab_plan(
        profile,
        "/etc/service.conf",
        local_path=tmp_path / "service.conf.edit",
    )
    dock.update_text_editor_state_from_plan(
        ini_plan,
        source_row_name="service.conf",
        source_row_index=0,
    )
    assert dock.text_editor_highlighter.syntax == ini_plan.syntax

    json_plan = build_moba_text_editor_tab_plan(
        profile,
        "/etc/settings.json",
        local_path=tmp_path / "settings.json.edit",
    )
    dock.update_text_editor_state_from_plan(
        json_plan,
        source_row_name="settings.json",
        source_row_index=1,
    )
    assert dock.text_editor_highlighter.syntax == "json"
    assert any("true|false|null" in pattern for pattern, _color in dock.text_editor_highlighter.patterns)


def test_connected_text_editor_refuses_binary_content_and_cleans_probe(
    connected_workspace,
    monkeypatch,
    tmp_path,
) -> None:
    from pathlib import Path

    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QTreeWidgetItem

    _app, _window, _panel, dock, profile = connected_workspace
    monkeypatch.setattr(dock, "profile_for_sftp_action", lambda: profile)
    monkeypatch.setattr(
        dock,
        "ensure_background_authentication_for_request",
        lambda: True,
    )
    monkeypatch.setattr(
        dock,
        "start_text_editor_sftp_operation",
        lambda *_args: True,
    )
    item = QTreeWidgetItem(["payload.bin"])
    item.setData(0, int(Qt.ItemDataRole.UserRole) + 42, "file")
    item.setData(0, int(Qt.ItemDataRole.UserRole) + 47, "/tmp")
    dock.handle_moba_text_editor_open_from_item(item, 0)

    cache_path = tmp_path / "payload.bin.edit"
    cache_path.write_bytes(b"binary\x00payload")
    dock.text_editor_local_path = str(cache_path)
    with pytest.raises(ValueError, match="binary"):
        dock.finish_text_editor_open()
    assert dock.text_editor.property("mobaTextEditorContentLoaded") is False
    assert dock.text_editor.isReadOnly() is True

    probe_path = tmp_path / "payload.bin.remote-check"
    probe_path.write_bytes(b"stale")
    dock.text_editor_probe_path = str(probe_path)
    dock.cancel_text_editor_sftp_operation()
    assert dock.text_editor_probe_path == ""
    assert not Path(probe_path).exists()


def test_connected_text_editor_transfer_uses_async_sftp_batch(
    connected_workspace,
    monkeypatch,
    tmp_path,
) -> None:
    from PyQt6.QtCore import QProcess

    from remote_ops_workspace.file_transfer import build_sftp_get_plan

    _app, _window, _panel, dock, profile = connected_workspace
    plan = build_sftp_get_plan(
        profile,
        "/etc/service.conf",
        local_path=tmp_path / "service.conf.edit",
        allow_overwrite=True,
    )
    process = _FakeProcess()
    dock.text_editor_process = process
    dock.text_editor_remote_path = "/etc/service.conf"
    dock.text_editor_local_path = str(tmp_path / "service.conf.edit")
    monkeypatch.setattr(dock, "shared_ssh_control_path", lambda: "")

    assert dock.start_text_editor_sftp_operation("open", plan) is True
    assert process.start_calls == 1
    assert process.program == plan.command[0]
    assert process.arguments
    assert dock.text_editor_active_generation != 0

    dock.write_text_editor_sftp_batch()
    assert process.written == plan.batch_input().encode("utf-8")
    assert process.close_write_calls == 1

    dock.cancel_text_editor_sftp_operation()
    assert dock.text_editor_active_generation == 0
    assert process.kill_calls == 1
    assert dock.text_editor_process.state() == QProcess.ProcessState.NotRunning


def test_sftp_navigation_context_dispatch_and_timeout_edges(
    connected_workspace,
    monkeypatch,
) -> None:
    from PyQt6.QtCore import QProcess, Qt
    from PyQt6.QtWidgets import QTreeWidgetItem

    from remote_ops_workspace.gui_designs import gui_design_moba_sftp_dock_actions

    app, window, _panel, dock, _profile = connected_workspace
    process = _FakeProcess(running=False)
    dock.sftp_refresh_process = process
    pending_calls: list[str] = []
    monkeypatch.setattr(
        dock,
        "schedule_pending_sftp_refresh",
        lambda: pending_calls.append("pending"),
    )
    monkeypatch.setattr(dock, "sftp_refresh_request_is_current", lambda: False)
    dock.sftp_refresh_active_generation = 2
    dock.handle_sftp_refresh_error(QProcess.ProcessError.ReadError)
    assert dock.sftp_refresh_active_generation == 0
    monkeypatch.setattr(dock, "sftp_refresh_request_is_current", lambda: True)
    dock.handle_sftp_refresh_error(QProcess.ProcessError.Timedout)
    assert dock.property("mobaSftpRefreshLastError") == "Timedout"
    assert pending_calls == ["pending", "pending"]

    dock.cancel_sftp_refresh_timeout()
    process.process_state = QProcess.ProcessState.Running
    monkeypatch.setattr(dock, "sftp_refresh_request_is_current", lambda: False)
    dock.cancel_sftp_refresh_timeout()
    assert process.kill_calls == 1
    process.process_state = QProcess.ProcessState.Running
    monkeypatch.setattr(dock, "sftp_refresh_request_is_current", lambda: True)
    dock.cancel_sftp_refresh_timeout()
    assert dock.property("mobaSftpRefreshLastError") == "timeout"

    real_schedule = type(dock).schedule_pending_sftp_refresh
    requested: list[str] = []
    monkeypatch.setattr(
        dock,
        "request_sftp_refresh",
        lambda *, reason="manual": requested.append(reason),
    )
    dock.sftp_refresh_pending = None
    real_schedule(dock)
    dock.sftp_refresh_pending = (dock.active_remote_path, "shutdown")
    dock.runtime_shutting_down = True
    real_schedule(dock)
    dock.runtime_shutting_down = False
    dock.sftp_refresh_pending = (dock.active_remote_path, "same-path")
    real_schedule(dock)
    app.processEvents()
    assert requested == ["same-path"]
    dock.sftp_refresh_pending = ("/different", "different-path")
    real_schedule(dock)
    app.processEvents()
    assert requested == ["same-path"]

    original_path = dock.active_remote_path
    assert dock.navigate_moba_sftp_path("-unsafe") is False
    assert dock.path.text() == original_path
    refresh_reasons: list[str] = []
    monkeypatch.setattr(
        dock,
        "request_sftp_refresh",
        lambda *, reason="manual": refresh_reasons.append(reason),
    )
    follow = dock.monitoring_control_widgets["follow-terminal-folder"]
    _set_checked(follow, True)
    assert dock.navigate_moba_sftp_path("var/log") is True
    assert dock.active_remote_path == "/var/log"
    assert refresh_reasons == ["path-change"]
    _set_checked(follow, False)
    assert dock.navigate_moba_sftp_path("/") is True

    role_kind = int(Qt.ItemDataRole.UserRole) + 42
    dock.file_table.setCurrentItem(None)
    assert dock.selected_sftp_item() is None
    parent = QTreeWidgetItem([".."])
    parent.setData(0, role_kind, "parent-dir")
    dock.file_table.addTopLevelItem(parent)
    dock.file_table.setCurrentItem(parent)
    assert dock.selected_sftp_item() is None
    invalid = QTreeWidgetItem(["socket"])
    invalid.setData(0, role_kind, "socket")
    dock.file_table.addTopLevelItem(invalid)
    dock.file_table.setCurrentItem(invalid)
    assert dock.selected_sftp_item() is None
    remote_file = QTreeWidgetItem(["report.txt"])
    remote_file.setData(0, role_kind, "file")
    dock.file_table.addTopLevelItem(remote_file)
    dock.file_table.setCurrentItem(remote_file)
    assert dock.selected_sftp_item() == ("report.txt", "file")
    assert dock.sftp_remote_path_for_item(None) == "/"
    assert dock.sftp_remote_path_for_item(parent) == "/"
    assert dock.sftp_remote_path_for_item(remote_file) == "/report.txt"

    navigated: list[str] = []
    edited: list[str] = []
    monkeypatch.setattr(
        dock,
        "navigate_moba_sftp_path",
        lambda path: navigated.append(path) or True,
    )
    monkeypatch.setattr(
        dock,
        "handle_moba_text_editor_open_from_item",
        lambda item, _column: edited.append(item.text(0)),
    )
    dock.open_sftp_context_item(None)
    dock.open_sftp_context_item(parent)
    dock.open_sftp_context_item(remote_file)
    assert navigated == ["/"]
    assert edited == ["report.txt"]

    dock.setProperty("mobaSftpToolbarRouteSuppressDialog", True)
    assert dock.dispatch_moba_sftp_toolbar_action("download") is True
    dock.setProperty("mobaSftpToolbarRouteSuppressDialog", False)
    transferred: list[str] = []
    reconnected: list[str] = []
    focused: list[str] = []
    tool_calls: list[str] = []
    monkeypatch.setattr(
        dock,
        "open_moba_sftp_transfer_workflow",
        lambda key: transferred.append(key) or True,
    )
    monkeypatch.setattr(
        dock,
        "reconnect_moba_sftp_session",
        lambda: reconnected.append("connect") or True,
    )
    monkeypatch.setattr(
        dock,
        "focus_moba_sftp_terminal",
        lambda: focused.append("terminal") or True,
    )
    monkeypatch.setattr(window, "show_moba_tools_status", lambda: tool_calls.append("tools"))
    monkeypatch.setattr(dock, "main_window", lambda: None)
    assert dock.dispatch_moba_sftp_toolbar_action("tools") is False
    monkeypatch.setattr(dock, "main_window", lambda: window)
    assert dock.dispatch_moba_sftp_toolbar_action("parent-folder") is True
    assert dock.dispatch_moba_sftp_toolbar_action("download") is True
    assert dock.dispatch_moba_sftp_toolbar_action("upload") is True
    assert dock.dispatch_moba_sftp_toolbar_action("connect") is True
    assert dock.dispatch_moba_sftp_toolbar_action("tools") is True
    assert dock.dispatch_moba_sftp_toolbar_action("terminal") is True
    assert dock.dispatch_moba_sftp_toolbar_action("unknown") is False
    assert transferred == ["download", "upload"]
    assert reconnected == ["connect"]
    assert focused == ["terminal"]
    assert tool_calls == ["tools"]

    dock.show_moba_sftp_toolbar_action("unknown")
    unavailable = next(
        action.key
        for action in gui_design_moba_sftp_dock_actions()
        if action.key not in dock.OPERATIONAL_ACTIONS
    )
    dock.show_moba_sftp_toolbar_action(unavailable)
    assert "unavailable" in window.statusBar().currentMessage()


def test_connected_context_menus_and_workspace_dispatch_edges(
    connected_workspace,
    monkeypatch,
) -> None:
    from PyQt6.QtCore import QPoint, Qt
    from PyQt6.QtWidgets import QTreeWidgetItem

    _app, window, panel, dock, _profile = connected_workspace
    item = QTreeWidgetItem(["context.txt"])
    item.setData(0, int(Qt.ItemDataRole.UserRole) + 42, "file")
    dock.file_table.addTopLevelItem(item)

    class _Menu:
        def __init__(self) -> None:
            self.executed = []
            self.deleted = False

        def exec(self, position) -> None:
            self.executed.append(position)

        def deleteLater(self) -> None:  # noqa: N802
            self.deleted = True

    sftp_menu = _Menu()
    monkeypatch.setattr(dock.file_table, "itemAt", lambda _position: item)
    monkeypatch.setattr(dock, "build_sftp_context_menu", lambda selected: sftp_menu)
    dock.show_sftp_context_menu(QPoint(4, 5))
    assert dock.file_table.currentItem() is item
    assert len(sftp_menu.executed) == 1
    assert sftp_menu.deleted is True

    calls: list[str] = []
    monkeypatch.setattr(window, "controlled_workspace_action", lambda: calls.append("window"), raising=False)
    panel.dispatch_moba_workspace_action("controlled_workspace_action")
    monkeypatch.delattr(window, "controlled_workspace_action", raising=False)
    monkeypatch.setattr(panel, "controlled_workspace_action", lambda: calls.append("panel"), raising=False)
    panel.dispatch_moba_workspace_action("controlled_workspace_action")
    panel.dispatch_moba_workspace_action("missing_workspace_action")
    assert calls == ["window", "panel"]

    terminal_menu = _Menu()
    source = panel.terminal_pane.output
    monkeypatch.setattr(
        panel,
        "build_moba_terminal_context_menu",
        lambda pane: terminal_menu,
    )
    panel.show_moba_terminal_context_menu(source, QPoint(2, 3))
    assert len(terminal_menu.executed) == 1
    assert terminal_menu.deleted is True


def test_follow_folder_cancel_rail_keyboard_and_populated_dock_edges(
    connected_workspace,
    monkeypatch,
) -> None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QLabel

    from remote_ops_workspace.moba_connected import RemoteFileEntry

    _app, window, _panel, dock, _profile = connected_workspace
    original_process = dock.sftp_refresh_process
    process = _FakeProcess(running=True)
    dock.sftp_refresh_process = process
    original_browser = dock.browser
    original_monitoring_panel = dock.remote_monitoring_panel
    dock.browser = None
    dock.remote_monitoring_panel = None
    refreshes: list[str] = []
    monkeypatch.setattr(
        dock,
        "request_sftp_refresh",
        lambda *, reason="manual": refreshes.append(reason),
    )
    dock.handle_moba_follow_terminal_folder_toggled(True)
    assert refreshes == ["follow-enabled"]
    dock.handle_moba_follow_terminal_folder_toggled(False)
    assert process.kill_calls == 1
    assert dock.sftp_refresh_active_generation == 0
    assert dock.sftp_refresh_pending is None
    dock.browser = original_browser
    dock.remote_monitoring_panel = original_monitoring_panel
    dock.sftp_refresh_process = original_process

    labels = [
        label
        for label in window.findChildren(QLabel, "mobaRailLabel")
        if hasattr(label, "button")
    ]
    assert labels
    label = labels[0]
    clicks: list[str] = []
    label.button.clicked.connect(lambda: clicks.append("click"))
    QTest.keyClick(label, Qt.Key.Key_Return)
    QTest.keyClick(label, Qt.Key.Key_Space)
    QTest.keyClick(label, Qt.Key.Key_A)
    assert clicks == ["click", "click"]

    populated_state = replace(
        dock.state,
        file_entries=(
            RemoteFileEntry("edge.log", "file", 7, "Aug 26 12:00"),
        ),
    )
    populated = type(dock)(populated_state)
    names = [
        populated.file_table.topLevelItem(index).text(0)
        for index in range(populated.file_table.topLevelItemCount())
    ]
    assert "edge.log" in names
    populated.shutdown_runtime()
    populated.deleteLater()


def test_connected_workspace_remaining_runtime_and_fallback_edges(
    connected_workspace,
    monkeypatch,
) -> None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QTreeWidgetItem

    from remote_ops_workspace import terminal

    _app, window, panel, dock, _profile = connected_workspace

    monkeypatch.setattr(dock, "main_window", lambda: None)
    assert dock.monitoring_surface_is_current() is True

    monkeypatch.setattr(
        dock,
        "shared_ssh_control_path",
        lambda: "C:/controlled/row-monitor.sock",
    )
    monkeypatch.setattr(terminal, "_is_native_windows", lambda: True)
    runtime_command = dock.monitoring_runtime_command()
    assert "ControlPath=none" in runtime_command

    assert dock.monitoring_control_icon("unknown-control").isNull() is False
    panel.set_telemetry_cell_visible("missing-cell", True)

    monkeypatch.setattr(window, "active_terminal_pane", lambda: None)
    assert panel.moba_terminal_context_pane(panel.telemetry_bar) is panel.terminal_pane

    kind_role = int(Qt.ItemDataRole.UserRole) + 42
    source_path_role = int(Qt.ItemDataRole.UserRole) + 47
    item = QTreeWidgetItem(["runtime.conf"])
    item.setData(0, kind_role, "file")
    item.setData(0, source_path_role, "/etc")
    diff_button = dock.text_editor_diff_button
    monkeypatch.setattr(dock, "profile_for_sftp_action", lambda: _profile)
    monkeypatch.setattr(
        dock,
        "ensure_background_authentication_for_request",
        lambda: False,
    )
    dock.text_editor_diff_button = None
    try:
        dock.handle_moba_text_editor_open_from_item(item, 0)
    finally:
        dock.text_editor_diff_button = diff_button
    assert dock.text_editor.property("mobaTextEditorRemotePath") == "/etc/runtime.conf"


def test_connected_session_context_route_and_sftp_dock_recovery(
    connected_workspace,
) -> None:
    from PyQt6.QtWidgets import QWidget

    _app, window, panel, old_dock, _profile = connected_workspace
    panel_index = window.tabs.indexOf(panel)
    assert panel_index >= 0

    menu = window.build_tab_context_menu(panel_index)
    assert menu is not None
    action_keys = {
        str(action.property("sessionTabContextActionKey") or "")
        for action in menu.actions()
    }
    assert "open-sftp-same-parameters" in action_keys
    menu.deleteLater()

    home_index = window.find_tab_by_role("home")
    assert window.moba_connected_session_action_route_for_tab(home_index) is None
    invalid_role = QWidget()
    invalid_role.moba_connected_state = panel.moba_connected_state
    invalid_index = window.add_workspace_tab(
        invalid_role,
        "Invalid connected role",
        role="session",
    )
    assert window.moba_connected_session_action_route_for_tab(invalid_index) is None

    window.set_workspace_tab_index(panel_index)
    window.moba_connected_dock = None
    window.show_moba_sftp_rail()
    replacement_dock = window.moba_connected_dock
    assert replacement_dock is not None
    assert replacement_dock is not old_dock
    replacement_dock.shutdown_runtime()


def test_connected_optional_surface_and_stale_runtime_branch_outcomes(
    connected_workspace,
    monkeypatch,
) -> None:
    from PyQt6.QtCore import QPoint, QProcess, Qt
    from PyQt6.QtWidgets import QLabel, QTreeWidgetItem

    _app, window, panel, dock, _profile = connected_workspace

    monkeypatch.setattr(dock, "shared_ssh_control_path", lambda: "controlled-path")
    dock.background_auth_retry_timer.start(60_000)
    dock.schedule_background_auth_retry()
    assert dock.background_auth_retry_timer.isActive() is True
    dock.background_auth_retry_timer.stop()

    original_browser = dock.browser
    original_file_table = dock.file_table
    dock.browser = None
    dock.file_table = None
    monkeypatch.setattr(
        dock,
        "background_ssh_auth_capability",
        lambda _profile: (True, "controlled key authentication"),
    )
    monkeypatch.setattr(dock, "set_remote_monitoring_runtime", lambda *_args, **_kwargs: None)
    dock._apply_initial_background_state(start_runtime=False)
    dock.browser = original_browser
    dock.file_table = original_file_table

    kind_role = int(Qt.ItemDataRole.UserRole) + 42
    source_path_role = int(Qt.ItemDataRole.UserRole) + 47
    item = QTreeWidgetItem(["optional.conf"])
    item.setData(0, kind_role, "file")
    item.setData(0, source_path_role, "/etc")
    original_toolbar = dock.text_editor_toolbar
    original_save = dock.text_editor_save_button
    original_diff = dock.text_editor_diff_button
    dock.text_editor_toolbar = None
    dock.text_editor_save_button = None
    dock.handle_moba_text_editor_open_from_item(item, 0)
    dock.text_editor_diff_button = None
    dock.handle_moba_text_editor_changed()
    dock.capture_moba_text_editor_action("close", status="closed")
    dock.text_editor_toolbar = original_toolbar
    dock.text_editor_save_button = original_save
    dock.text_editor_diff_button = original_diff

    original_controls = dock.monitoring_control_widgets
    original_monitoring_panel = dock.remote_monitoring_panel
    dock.monitoring_control_widgets = {}
    dock.remote_monitoring_panel = None
    dock.set_remote_monitoring_status("No optional controls", state="paused")
    no_controls_menu = dock.build_remote_monitoring_context_menu()
    assert no_controls_menu.isEnabled() is True
    no_controls_menu.deleteLater()
    dock.monitoring_control_widgets = original_controls
    dock.remote_monitoring_panel = original_monitoring_panel

    original_monitoring_process = dock.monitoring_process
    dock.remote_monitoring_panel = None
    dock.monitoring_process = _FakeProcess(running=True)
    control = dock.monitoring_control_widgets["remote-monitoring"]
    _set_checked(control, True)
    monkeypatch.setattr(
        dock,
        "ensure_background_authentication_for_request",
        lambda: True,
    )
    dock.request_remote_monitoring_refresh()
    dock.monitoring_process = original_monitoring_process
    dock.remote_monitoring_panel = original_monitoring_panel
    _set_checked(control, False)

    telemetry_frame = next(iter(panel.telemetry_cell_frames.values()))
    telemetry_label = telemetry_frame.findChild(QLabel, "mobaTelemetryItem")
    assert telemetry_label is not None
    telemetry_label.setParent(None)
    assert dock.apply_live_remote_monitoring_snapshot(dock.state.monitoring) is True
    telemetry_label.deleteLater()

    path = dock.path
    del dock.path
    dock.sftp_refresh_process = _FakeProcess(running=False)
    dock.handle_moba_follow_terminal_folder_toggled(False)
    dock.path = path

    original_sftp_process = dock.sftp_refresh_process
    dock.browser = None
    dock.file_table = None
    dock.sftp_refresh_process = _FakeProcess(running=True)
    dock.request_sftp_refresh(reason="optional-widget-edge")
    dock.browser = original_browser
    dock.file_table = original_file_table
    dock.sftp_refresh_process = original_sftp_process

    dock._background_password = bytearray(b"controlled")
    dock.sftp_refresh_active_generation = 1
    dock.sftp_auth_probe_timer.start(60_000)
    dock.write_sftp_refresh_batch()
    assert dock.sftp_auth_probe_timer.isActive() is True
    dock.sftp_auth_probe_timer.stop()
    dock._clear_background_password()
    dock.sftp_refresh_active_generation = 0

    stale_statuses: list[str] = []
    monkeypatch.setattr(dock, "sftp_refresh_request_is_current", lambda: False)
    monkeypatch.setattr(dock, "read_sftp_refresh_output", lambda: None)
    monkeypatch.setattr(dock, "show_sftp_status", stale_statuses.append)
    dock.runtime_shutting_down = True
    dock.handle_sftp_refresh_finished(0, QProcess.ExitStatus.NormalExit)
    assert stale_statuses == []
    dock.runtime_shutting_down = False

    original_transfer_actions = dock.sftp_transfer_menu_actions
    dock.sftp_transfer_menu_actions = {}
    dock.update_sftp_action_states()
    dock.sftp_transfer_menu_actions = original_transfer_actions

    del dock.file_table
    assert dock.navigate_moba_sftp_path("/srv/optional") is True
    dock.file_table = original_file_table

    context_menu = dock.build_sftp_context_menu(None)
    assert context_menu.objectName() == "mobaSftpContextMenu"
    context_menu.deleteLater()

    menu_events: list[object] = []
    fake_menu = SimpleNamespace(
        exec=lambda position: menu_events.append(position),
        deleteLater=lambda: menu_events.append("deleted"),
    )
    fake_viewport = SimpleNamespace(mapToGlobal=lambda position: position)
    context_owner = SimpleNamespace(
        file_table=SimpleNamespace(
            itemAt=lambda _position: None,
            viewport=lambda: fake_viewport,
        ),
        build_sftp_context_menu=lambda item: fake_menu,
    )
    type(dock).show_sftp_context_menu(context_owner, QPoint(1, 1))
    assert menu_events[-1] == "deleted"

    logged: list[str] = []
    no_status_window = SimpleNamespace(
        statusBar=lambda: None,
        log=SimpleNamespace(append=logged.append),
    )
    type(dock).show_sftp_status(
        SimpleNamespace(main_window=lambda: no_status_window),
        "status without bar",
    )
    assert logged == ["status without bar"]

    assert dock.sftp_action_icon("future-action", "#303030").isNull() is False

    shutdown_dock = type(dock)(dock.state)

    class _NoCloseProcess:
        @staticmethod
        def blockSignals(_blocked: bool) -> None:  # noqa: N802
            return None

        @staticmethod
        def state():
            return QProcess.ProcessState.NotRunning

        @staticmethod
        def kill() -> None:
            return None

    shutdown_dock.monitoring_process = _NoCloseProcess()
    shutdown_dock.sftp_refresh_process = _NoCloseProcess()
    shutdown_dock.shutdown_runtime()
    shutdown_dock.deleteLater()


def test_connected_terminal_context_and_statusless_save_branch_outcomes(
    connected_workspace,
    monkeypatch,
    tmp_path,
) -> None:
    from PyQt6.QtWidgets import QFileDialog

    _app, _window, panel, _dock, _profile = connected_workspace
    monkeypatch.setattr(panel, "active_moba_sftp_dock", lambda: None)
    menu = panel.build_moba_terminal_context_menu(panel.terminal_pane)
    assert all(action.text() != "Monitoring" for action in menu.actions())
    menu.deleteLater()

    control_less_dock = SimpleNamespace(monitoring_control_widgets={})
    monkeypatch.setattr(
        panel,
        "active_moba_sftp_dock",
        lambda: control_less_dock,
    )
    menu = panel.build_moba_terminal_context_menu(panel.terminal_pane)
    assert any(action.text() == "Monitoring" for action in menu.actions())
    menu.deleteLater()

    properties: dict[str, object] = {}
    owner = SimpleNamespace(
        setProperty=lambda key, value: properties.__setitem__(key, value),
        window=lambda: SimpleNamespace(statusBar=lambda: None),
    )
    pane = SimpleNamespace(
        plan=SimpleNamespace(title="statusless save"),
        _rendered_terminal_text="saved transcript",
    )
    destination = tmp_path / "terminal.txt"
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *_args, **_kwargs: (str(destination), "Text files (*.txt)"),
    )
    type(panel).save_terminal_to_file(owner, pane)
    assert destination.read_text(encoding="utf-8") == "saved transcript"

    missing_destination = tmp_path / "missing" / "terminal.txt"
    monkeypatch.setattr(
        QFileDialog,
        "getSaveFileName",
        lambda *_args, **_kwargs: (
            str(missing_destination),
            "Text files (*.txt)",
        ),
    )
    type(panel).save_terminal_to_file(owner, pane)
    assert "mobaTerminalSaveError" in properties

    action_properties: dict[str, object] = {}
    action_owner = SimpleNamespace(
        setProperty=lambda key, value: action_properties.__setitem__(key, value),
        window=lambda: SimpleNamespace(statusBar=lambda: None),
    )
    type(panel).record_moba_panel_action(
        action_owner,
        "session-edge",
        "future-action",
    )
    assert action_properties["mobaConnectedLastActionKey"] == "future-action"

    unknown_cell = SimpleNamespace(
        icon_size=14,
        icon_accent="#35d7c7",
        icon_key="future-metric",
    )
    assert panel.telemetry_icon_pixmap(unknown_cell).isNull() is False


def test_connected_terminal_traversal_and_text_editor_guard_edges(
    connected_workspace,
    monkeypatch,
    tmp_path,
) -> None:
    from PyQt6.QtCore import QEvent, Qt
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtWidgets import QApplication, QMessageBox, QTreeWidgetItem

    from remote_ops_workspace import gui
    from remote_ops_workspace.moba_text import build_moba_text_editor_tab_plan

    app, window, panel, dock, profile = connected_workspace
    pane = panel.terminal_pane

    monkeypatch.setattr(window, "terminal_panes_in", lambda _current: [pane])
    monkeypatch.setattr(QApplication, "focusWidget", lambda: pane.output)
    assert window.active_terminal_pane() is pane
    monkeypatch.setattr(QApplication, "focusWidget", lambda: None)
    window._last_terminal_pane = pane
    assert window.active_terminal_pane() is pane

    next_tabs: list[str] = []
    previous_tabs: list[str] = []
    monkeypatch.setattr(window, "activate_next_tab", lambda: next_tabs.append("next"))
    monkeypatch.setattr(window, "activate_previous_tab", lambda: previous_tabs.append("previous"))

    next_event = QKeyEvent(
        QEvent.Type.KeyPress,
        Qt.Key.Key_Tab,
        Qt.KeyboardModifier.ControlModifier,
        "\t",
    )
    assert pane.eventFilter(pane.output, next_event) is True
    previous_event = QKeyEvent(
        QEvent.Type.KeyPress,
        Qt.Key.Key_Tab,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier,
        "\t",
    )
    assert pane.eventFilter(pane.output, previous_event) is True
    assert next_tabs == ["next"]
    assert previous_tabs == ["previous"]

    unhandled_event = QKeyEvent(
        QEvent.Type.KeyPress,
        Qt.Key.Key_A,
        Qt.KeyboardModifier.MetaModifier,
        "a",
    )
    assert pane.eventFilter(pane.output, unhandled_event) is False

    monkeypatch.setattr(pane, "is_running", lambda: True)
    sent: list[bytes] = []
    monkeypatch.setattr(pane, "send_raw_input", sent.append)
    pane.terminal_emulator.feed("\x1b[?2004h")
    pane.paste_text_to_terminal("first\nsecond", gesture="test")
    assert sent == [b"\x1b[200~first\nsecond\x1b[201~"]
    assert pane.output.property("terminalLastPasteWasBracketed") is True

    editor = dock.text_editor
    dock.text_editor = None
    dock.set_text_editor_runtime_state(status="missing-editor")
    dock.text_editor = editor
    save_button = dock.text_editor_save_button
    diff_button = dock.text_editor_diff_button
    dock.text_editor_save_button = None
    dock.text_editor_diff_button = None
    dock.set_text_editor_runtime_state(status="idle")
    dock.text_editor_save_button = save_button
    dock.text_editor_diff_button = diff_button

    kind_role = int(Qt.ItemDataRole.UserRole) + 42
    source_path_role = int(Qt.ItemDataRole.UserRole) + 47
    item = QTreeWidgetItem(["guarded.conf"])
    item.setData(0, kind_role, "file")
    item.setData(0, source_path_role, "/etc")

    monkeypatch.setattr(dock, "profile_for_sftp_action", lambda: None)
    dock.handle_moba_text_editor_open_from_item(item, 0)
    assert "connected profile" in window.statusBar().currentMessage()

    plan = build_moba_text_editor_tab_plan(
        profile,
        "/etc/guarded.conf",
        local_path=tmp_path / "guarded.conf.edit",
    )
    monkeypatch.setattr(dock, "profile_for_sftp_action", lambda: profile)

    def reject_plan(*_args, **_kwargs):
        raise ValueError("invalid editor plan")

    monkeypatch.setattr(gui, "build_moba_text_editor_tab_plan", reject_plan)
    dock.handle_moba_text_editor_open_from_item(item, 0)
    assert "invalid editor plan" in window.statusBar().currentMessage()

    monkeypatch.setattr(gui, "build_moba_text_editor_tab_plan", lambda *_args, **_kwargs: plan)
    monkeypatch.setattr(dock, "ensure_background_authentication_for_request", lambda: True)
    started: list[str] = []
    monkeypatch.setattr(
        dock,
        "start_text_editor_sftp_operation",
        lambda operation, _transfer_plan: started.append(operation) or True,
    )
    dock.text_editor_remote_path = "/etc/old.conf"
    editor.setProperty("mobaTextEditorContentLoaded", True)
    editor.setProperty("mobaTextEditorDirty", True)
    toolbar = dock.text_editor_toolbar
    dock.text_editor_toolbar = None
    monkeypatch.setattr(
        QMessageBox,
        "exec",
        lambda _self: QMessageBox.StandardButton.Yes,
    )
    dock.handle_moba_text_editor_open_from_item(item, 0)
    dock.text_editor_toolbar = toolbar
    assert started == ["open"]

    dock.text_editor = None
    dock.handle_moba_text_editor_save()
    dock.text_editor = editor
    editor.setProperty("mobaTextEditorContentLoaded", False)
    dock.handle_moba_text_editor_save()
    editor.setProperty("mobaTextEditorContentLoaded", True)
    editor.setProperty("mobaTextEditorDirty", False)
    dock.handle_moba_text_editor_save()
    editor.setProperty("mobaTextEditorDirty", True)
    dock.text_editor_active_generation = 1
    dock.handle_moba_text_editor_save()
    dock.text_editor_active_generation = 0

    monkeypatch.setattr(dock, "profile_for_sftp_action", lambda: None)
    dock.handle_moba_text_editor_save()
    monkeypatch.setattr(dock, "profile_for_sftp_action", lambda: profile)
    monkeypatch.setattr(dock, "ensure_background_authentication_for_request", lambda: False)
    dock.handle_moba_text_editor_save()
    monkeypatch.setattr(dock, "ensure_background_authentication_for_request", lambda: True)
    monkeypatch.setattr(gui, "build_sftp_get_plan", reject_plan)
    dock.handle_moba_text_editor_save()
    editor.setProperty("mobaTextEditorContentLoaded", False)
    dock.handle_moba_text_editor_diff()
    assert "not loaded" in window.statusBar().currentMessage()

    dock.text_editor = editor
    app.processEvents()


def test_connected_text_editor_transfer_failure_and_dispatch_edges(
    connected_workspace,
    monkeypatch,
    tmp_path,
) -> None:
    from PyQt6.QtCore import QProcess
    from PyQt6.QtWidgets import QMessageBox

    from remote_ops_workspace import gui
    from remote_ops_workspace.file_transfer import build_sftp_get_plan
    from remote_ops_workspace.moba_text import build_moba_text_editor_tab_plan

    app, window, _panel, dock, profile = connected_workspace
    original_process = dock.text_editor_process
    real_finish_text_editor_save_check = type(dock).finish_text_editor_save_check
    cache_path = tmp_path / "service.conf.edit"
    plan = build_sftp_get_plan(
        profile,
        "/etc/service.conf",
        local_path=cache_path,
        allow_overwrite=True,
    )
    tab_plan = build_moba_text_editor_tab_plan(
        profile,
        "/etc/service.conf",
        local_path=cache_path,
    )

    dock.runtime_shutting_down = True
    assert dock.start_text_editor_sftp_operation("open", plan) is False
    dock.runtime_shutting_down = False

    dock.text_editor_active_generation = 0
    dock.text_editor_generation = 1
    dock.write_text_editor_sftp_batch()

    process = _FakeProcess(running=True)
    dock.text_editor_process = process
    dock.text_editor_remote_path = "/etc/service.conf"
    dock.text_editor_local_path = str(cache_path)
    monkeypatch.setattr(dock, "shared_ssh_control_path", lambda: "")
    assert dock.start_text_editor_sftp_operation("open", plan) is True
    assert process.kill_calls == 1
    assert dock.text_editor_pending_sftp is not None
    dock.text_editor_pending_sftp = None

    monkeypatch.setattr(dock, "shared_ssh_control_path", lambda: "control.sock")
    assert dock.start_text_editor_sftp_operation("open", plan) is True
    assert process.start_calls == 1

    class FailingProcess(_FakeProcess):
        def start(self) -> None:
            raise RuntimeError("start failed")

    failing = FailingProcess()
    dock.text_editor_process = failing
    probe = tmp_path / "service.conf.remote-check"
    probe.write_text("probe", encoding="utf-8")
    dock.text_editor_probe_path = str(probe)
    assert dock.start_text_editor_sftp_operation("save-check", plan) is False
    assert not probe.exists()
    assert dock.start_text_editor_sftp_operation("open", plan) is False

    probe_directory = tmp_path / "probe-directory"
    probe_directory.mkdir()
    dock.text_editor_probe_path = str(probe_directory)
    dock.clear_text_editor_probe_file()
    assert probe_directory.exists()

    process = _FakeProcess()
    dock.text_editor_process = process
    dock.text_editor_generation = 12
    dock.text_editor_active_generation = 12
    dock.text_editor_sftp_plan = plan
    dock._background_password = bytearray(b"session-password")
    dock.text_editor_auth_probe_timer.stop()
    dock.write_text_editor_sftp_batch()
    assert dock.text_editor_auth_probe_timer.isActive() is True
    dock.write_text_editor_sftp_batch()
    dock._clear_background_password()
    dock.text_editor_sftp_plan = None
    dock.text_editor_active_generation = 12
    dock.write_text_editor_sftp_batch()
    dock.text_editor_sftp_plan = plan
    process.write_result = -1
    dock.write_text_editor_sftp_batch()
    process.output = b"editor output"
    dock.text_editor_output_buffer.clear()
    dock.read_text_editor_sftp_output()
    assert bytes(dock.text_editor_output_buffer) == b"editor output"

    auth_process = _FakeProcess()
    dock.text_editor_process = auth_process
    dock._background_password = bytearray(b"session-password")
    dock._background_auth_password_sent["text-editor"] = False
    forced_batches: list[bool] = []
    monkeypatch.setattr(
        dock,
        "write_text_editor_sftp_batch",
        lambda *, force=False: forced_batches.append(force),
    )
    dock._submit_background_password_if_prompt("text-editor", b"Password: ")
    app.processEvents()
    assert forced_batches == [True]
    dock.text_editor_process = None
    dock._background_auth_password_sent["text-editor"] = False
    dock._submit_background_password_if_prompt("text-editor", b"Password: ")
    dock._clear_background_password()
    dock.text_editor_process = process

    dock.text_editor_generation = 20
    dock.text_editor_active_generation = 20
    dock.text_editor_operation = "save-check"
    error_probe = tmp_path / "error.remote-check"
    error_probe.write_text("error", encoding="utf-8")
    dock.text_editor_probe_path = str(error_probe)
    dock.handle_text_editor_sftp_error(SimpleNamespace(name="ReadError"))
    assert not error_probe.exists()
    dock.text_editor_generation = 21
    dock.text_editor_active_generation = 20
    dock.text_editor_operation = "open"
    dock.handle_text_editor_sftp_error(SimpleNamespace(name="StaleError"))

    process.process_state = QProcess.ProcessState.NotRunning
    dock.cancel_text_editor_sftp_timeout()
    process.process_state = QProcess.ProcessState.Running
    dock.text_editor_generation = 30
    dock.text_editor_active_generation = 29
    dock.text_editor_operation = "open"
    dock.cancel_text_editor_sftp_timeout()
    process.process_state = QProcess.ProcessState.Running
    dock.text_editor_generation = 31
    dock.text_editor_active_generation = 31
    dock.text_editor_operation = "save-check"
    timeout_probe = tmp_path / "timeout.remote-check"
    timeout_probe.write_text("timeout", encoding="utf-8")
    dock.text_editor_probe_path = str(timeout_probe)
    dock.cancel_text_editor_sftp_timeout()
    assert not timeout_probe.exists()

    dock.text_editor_process = process
    process.output = b"stale output"
    dock.text_editor_output_buffer.clear()
    dock.text_editor_generation = 40
    dock.text_editor_active_generation = 39
    dock.text_editor_operation = "open"
    dock.handle_text_editor_sftp_finished(0, QProcess.ExitStatus.NormalExit)

    retry_calls: list[str] = []
    monkeypatch.setattr(dock, "schedule_background_auth_retry", lambda: retry_calls.append("retry"))
    process.output = b"remote failure\n"
    failure_probe = tmp_path / "failure.remote-check"
    failure_probe.write_text("failure", encoding="utf-8")
    dock.text_editor_probe_path = str(failure_probe)
    dock.text_editor_generation = 41
    dock.text_editor_active_generation = 41
    dock.text_editor_operation = "save-check"
    dock.handle_text_editor_sftp_finished(1, QProcess.ExitStatus.CrashExit)
    assert not failure_probe.exists()

    process.output = b"open failure\n"
    dock.text_editor_generation = 42
    dock.text_editor_active_generation = 42
    dock.text_editor_operation = "open"
    dock.handle_text_editor_sftp_finished(1, QProcess.ExitStatus.CrashExit)
    assert retry_calls == ["retry", "retry"]

    dispatched: list[str] = []
    monkeypatch.setattr(dock, "finish_text_editor_open", lambda: dispatched.append("open"))
    monkeypatch.setattr(dock, "finish_text_editor_save_check", lambda: dispatched.append("save-check"))
    monkeypatch.setattr(dock, "finish_text_editor_upload", lambda: dispatched.append("upload"))
    for index, operation in enumerate(("open", "save-check", "upload", "unknown"), start=50):
        process.output = b""
        dock.text_editor_generation = index
        dock.text_editor_active_generation = index
        dock.text_editor_operation = operation
        dock.handle_text_editor_sftp_finished(0, QProcess.ExitStatus.NormalExit)
    assert dispatched == ["open", "save-check", "upload"]

    def invalid_result() -> None:
        raise ValueError("invalid result")

    monkeypatch.setattr(dock, "finish_text_editor_open", invalid_result)
    dock.text_editor_generation = 60
    dock.text_editor_active_generation = 60
    dock.text_editor_operation = "open"
    dock.handle_text_editor_sftp_finished(0, QProcess.ExitStatus.NormalExit)
    assert dock.text_editor.property("mobaTextEditorStatus") == "error"

    dock.text_editor_pending_sftp = None
    dock.runtime_shutting_down = False
    dock.schedule_pending_text_editor_sftp()
    dock.text_editor_pending_sftp = ("open", plan, "/etc/a", str(cache_path))
    dock.runtime_shutting_down = True
    dock.schedule_pending_text_editor_sftp()
    dock.runtime_shutting_down = False

    pending_calls: list[tuple[str, str, str]] = []
    monkeypatch.setattr(
        dock,
        "start_text_editor_sftp_operation",
        lambda operation, _plan: pending_calls.append(
            (operation, dock.text_editor_remote_path, dock.text_editor_local_path)
        ) or True,
    )
    dock.text_editor_pending_sftp = ("open", plan, "/etc/deferred", str(cache_path))
    dock.schedule_pending_text_editor_sftp()
    dock.runtime_shutting_down = True
    app.processEvents()
    dock.runtime_shutting_down = False
    dock.text_editor_pending_sftp = ("upload", plan, "/etc/deferred", str(cache_path))
    dock.schedule_pending_text_editor_sftp()
    app.processEvents()
    assert pending_calls == [("upload", "/etc/deferred", str(cache_path))]

    editor = dock.text_editor
    editor.setPlainText("edited\n")
    editor.setProperty("mobaTextEditorContentLoaded", True)
    editor.setProperty("mobaTextEditorDirty", True)
    dock.text_editor_local_path = str(cache_path)
    cache_path.write_text("cached\n", encoding="utf-8")
    dock.text_editor_cache_sha256 = dock.text_editor_file_sha256(cache_path)
    dock.text_editor_original_remote_sha256 = "old-digest"
    conflict_probe = tmp_path / "conflict.remote-check"
    conflict_probe.write_text("remote\n", encoding="utf-8")
    dock.text_editor_probe_path = str(conflict_probe)
    dock.text_editor_tab_plan = tab_plan
    monkeypatch.setattr(
        QMessageBox,
        "exec",
        lambda _self: QMessageBox.StandardButton.Yes,
    )
    monkeypatch.setattr(
        gui,
        "write_text_document",
        lambda *_args, **_kwargs: SimpleNamespace(new_sha256="new-cache-digest"),
    )
    upload_calls: list[str] = []
    monkeypatch.setattr(
        dock,
        "start_text_editor_sftp_operation",
        lambda operation, _plan: upload_calls.append(operation) or True,
    )
    real_finish_text_editor_save_check(dock)
    assert upload_calls == ["upload"]

    clean_probe = tmp_path / "clean.remote-check"
    clean_probe.write_bytes(cache_path.read_bytes())
    dock.text_editor_probe_path = str(clean_probe)
    digest = dock.text_editor_file_sha256(cache_path)
    dock.text_editor_original_remote_sha256 = digest
    dock.text_editor_cache_sha256 = digest

    def reject_cache(*_args, **_kwargs):
        raise OSError("cache unavailable")

    monkeypatch.setattr(gui, "write_text_document", reject_cache)
    real_finish_text_editor_save_check(dock)
    assert dock.text_editor.property("mobaTextEditorStatus") == "error"

    no_plan_probe = tmp_path / "no-plan.remote-check"
    no_plan_probe.write_bytes(cache_path.read_bytes())
    dock.text_editor_probe_path = str(no_plan_probe)
    dock.text_editor_original_remote_sha256 = digest
    monkeypatch.setattr(
        gui,
        "write_text_document",
        lambda *_args, **_kwargs: SimpleNamespace(new_sha256="updated-cache-digest"),
    )
    dock.text_editor_tab_plan = None
    real_finish_text_editor_save_check(dock)
    assert "editor plan is missing" in window.statusBar().currentMessage()

    dock.text_editor_process = original_process

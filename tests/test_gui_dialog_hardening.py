from __future__ import annotations

from dataclasses import dataclass

import pytest

from remote_ops_workspace.gui import _safe_tooltip_html
from remote_ops_workspace.models import Profile
from remote_ops_workspace.profile_importers import ProfileImportResult


def test_safe_tooltip_html_escapes_markup_and_preserves_lines() -> None:
    assert _safe_tooltip_html("<b>literal</b>\nnext & final") == (
        "<qt>&lt;b&gt;literal&lt;/b&gt;<br>next &amp; final</qt>"
    )


def test_main_window_and_application_have_a_visible_product_icon(gui_window) -> None:
    app, window = gui_window

    assert not app.windowIcon().isNull()
    assert not window.windowIcon().isNull()


def test_profile_protocol_is_a_closed_supported_catalog(gui_window) -> None:
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication, QComboBox

    _app, window = gui_window
    observed: dict[str, object] = {}

    def inspect_dialog() -> None:
        dialog = QApplication.activeModalWidget()
        assert dialog is not None
        protocol = dialog.findChild(QComboBox, "profileProtocol")
        assert protocol is not None
        initial = protocol.currentText()
        protocol.setEditText("not-a-supported-protocol")
        observed.update(
            editable=protocol.isEditable(),
            line_edit=protocol.lineEdit(),
            initial=initial,
            after=protocol.currentText(),
            options=[protocol.itemText(index) for index in range(protocol.count())],
        )
        dialog.reject()

    QTimer.singleShot(0, inspect_dialog)
    window.create_profile()

    assert observed["editable"] is False
    assert observed["line_edit"] is None
    assert observed["after"] == observed["initial"]
    assert observed["after"] in observed["options"]


def test_terminal_output_accepts_direct_keys_and_has_operational_context_menu(
    gui_window,
) -> None:
    from PyQt6.QtCore import QEvent, QProcess, Qt
    from PyQt6.QtGui import QInputMethodEvent, QKeyEvent
    from PyQt6.QtTest import QTest

    from remote_ops_workspace.gui_lifecycle import ProcessStopPolicy
    from remote_ops_workspace.terminal import TerminalPanePlan

    app, window = gui_window
    pane = window.new_terminal_pane(
        TerminalPanePlan(title="interaction-test", command=[], source="test")
    )
    process = _FakeProcess(pane)
    process.process_state = QProcess.ProcessState.Running
    process.finished.connect(pane.on_finished)
    pane.process = process
    pane.output.show()
    pane.output.setFocus()

    assert pane.focusProxy() is pane.output
    events = [
        QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_A,
            Qt.KeyboardModifier.NoModifier,
            "a",
        ),
        QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_Left,
            Qt.KeyboardModifier.NoModifier,
        ),
        QKeyEvent(
            QEvent.Type.KeyPress,
            Qt.Key.Key_C,
            Qt.KeyboardModifier.ControlModifier,
        ),
    ]
    for event in events:
        app.sendEvent(pane.output, event)
    assert process.written == b"a\x1b[D\x03"

    altgr_event = QKeyEvent(
        QEvent.Type.KeyPress,
        Qt.Key.Key_Q,
        Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier,
        "@",
    )
    app.sendEvent(pane.output, altgr_event)
    input_method_event = QInputMethodEvent("", [])
    input_method_event.setCommitString("ş")
    app.sendEvent(pane.output, input_method_event)
    assert process.written.endswith("@ş".encode())

    app.clipboard().setText("pasted")
    menu = pane.build_output_context_menu()
    assert [action.text() for action in menu.actions() if not action.isSeparator()] == [
        "Copy",
        "Paste to terminal",
        "Select all",
        "Clear terminal",
        "Restart session",
        "Stop session",
    ]
    pane.paste_to_terminal()
    assert process.written.endswith(b"pasted")

    pane.request_stop(policy=ProcessStopPolicy(terminate_timeout_ms=10, kill_timeout_ms=0))
    assert process.terminated
    assert not process.killed
    QTest.qWait(30)
    assert process.killed
    menu.deleteLater()
    pane.deleteLater()


def test_visible_moba_terminal_routes_keys_from_the_actual_mouse_focus(
    gui_window,
) -> None:
    from PyQt6.QtCore import QProcess, Qt
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication

    from remote_ops_workspace.terminal import TerminalPanePlan

    app, window = gui_window
    moba_index = window.design_select.findData("mobaxterm")
    assert moba_index >= 0
    window.design_select.setCurrentIndex(moba_index)
    profile = Profile(
        name="focus-host",
        protocol="ssh",
        host="focus-host.example.invalid",
        username="operator",
    )
    panel = window.open_moba_connected_session_tab(
        profile,
        TerminalPanePlan(title="focus-host", command=[], source="test"),
    )
    pane = panel.terminal_pane
    process = _FakeProcess(pane)
    process.process_state = QProcess.ProcessState.Running
    process.finished.connect(pane.on_finished)
    pane.process = process

    window.raise_()
    window.activateWindow()
    app.processEvents()
    QTest.mouseClick(
        pane.output.viewport(),
        Qt.MouseButton.LeftButton,
        pos=pane.output.viewport().rect().center(),
    )
    app.processEvents()

    focus = QApplication.focusWidget()
    if focus is not None:
        QTest.keyClicks(focus, "focused")
        QTest.keyClick(focus, Qt.Key.Key_Return)
    written = process.written
    process.finish()

    assert focus is pane.output
    assert written == b"focused\r"

    # Pipe-backed panes retain a visible, reliable line-mode fallback.  The
    # connected-state evidence route must not masquerade as live process output.
    assert pane.input.isVisible()
    transcript = pane.output.toPlainText()
    assert "Last login: Sat Jun  6 05:27:50 2026" not in transcript
    assert "[operator@focus-host ~]$" not in transcript


def test_visible_moba_terminal_writes_through_a_real_qprocess(gui_window) -> None:
    import sys

    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication

    from remote_ops_workspace.terminal import TerminalPanePlan

    app, window = gui_window
    moba_index = window.design_select.findData("mobaxterm")
    assert moba_index >= 0
    window.design_select.setCurrentIndex(moba_index)
    profile = Profile(
        name="real-stdin",
        protocol="ssh",
        host="real-stdin.example.invalid",
        username="operator",
    )
    child = (
        "import sys; "
        "print('READY', flush=True); "
        "payload = sys.stdin.buffer.read(4); "
        "print('RECEIVED:' + payload.hex(), flush=True)"
    )
    panel = window.open_moba_connected_session_tab(
        profile,
        TerminalPanePlan(
            title="real-stdin",
            command=[sys.executable, "-u", "-c", child],
            source="test",
        ),
    )
    pane = panel.terminal_pane

    try:
        for _ in range(100):
            app.processEvents()
            if "READY" in pane.output.toPlainText():
                break
            QTest.qWait(10)
        assert "READY" in pane.output.toPlainText()

        window.raise_()
        window.activateWindow()
        app.processEvents()
        QTest.mouseClick(
            pane.output.viewport(),
            Qt.MouseButton.LeftButton,
            pos=pane.output.viewport().rect().center(),
        )
        app.processEvents()
        focus = QApplication.focusWidget()
        assert focus is pane.output
        QTest.keyClicks(focus, "ping")

        for _ in range(100):
            app.processEvents()
            if "RECEIVED:70696e67" in pane.output.toPlainText():
                break
            QTest.qWait(10)
        assert "RECEIVED:70696e67" in pane.output.toPlainText()
        assert "Last login: Sat Jun  6 05:27:50 2026" not in pane.output.toPlainText()
    finally:
        if pane.is_running():
            pane.process.kill()
            pane.process.waitForFinished(1_000)


def test_visible_moba_line_fallback_completes_a_real_pipe_readline(
    gui_window,
) -> None:
    import sys

    from PyQt6.QtTest import QTest

    from remote_ops_workspace.terminal import TerminalPanePlan

    app, window = gui_window
    moba_index = window.design_select.findData("mobaxterm")
    window.design_select.setCurrentIndex(moba_index)
    profile = Profile(
        name="real-line-stdin",
        protocol="ssh",
        host="real-line-stdin.example.invalid",
        username="operator",
    )
    child = (
        "import sys; "
        "print('READY', flush=True); "
        "payload = sys.stdin.buffer.readline(); "
        "print('LINE:' + payload.hex(), flush=True)"
    )
    panel = window.open_moba_connected_session_tab(
        profile,
        TerminalPanePlan(
            title="real-line-stdin",
            command=[sys.executable, "-u", "-c", child],
            source="test",
        ),
    )
    pane = panel.terminal_pane

    try:
        for _ in range(100):
            app.processEvents()
            if "READY" in pane.output.toPlainText():
                break
            QTest.qWait(10)
        pane.input.setText("line-mode")
        pane.send_input()
        for _ in range(100):
            app.processEvents()
            if "LINE:6c696e652d6d6f64650a" in pane.output.toPlainText():
                break
            QTest.qWait(10)
        assert "LINE:6c696e652d6d6f64650a" in pane.output.toPlainText()
    finally:
        if pane.is_running():
            pane.process.kill()
            pane.process.waitForFinished(1_000)


def test_terminal_surfaces_short_process_writes_instead_of_silently_losing_input(
    gui_window,
) -> None:
    from PyQt6.QtCore import QProcess

    from remote_ops_workspace.terminal import TerminalPanePlan

    _app, window = gui_window
    pane = window.new_terminal_pane(
        TerminalPanePlan(title="short-write", command=[], source="test")
    )
    process = _ShortWriteProcess(pane)
    process.process_state = QProcess.ProcessState.Running
    process.finished.connect(pane.on_finished)
    pane.process = process

    pane.send_raw_input(b"abc")

    assert process.written == b"a"
    assert pane.output.property("terminalLastInputBytesRequested") == 3
    assert pane.output.property("terminalLastInputBytesAccepted") == 1
    assert pane.status.text() == "input error"
    assert pane.status.property("state") == "error"
    assert "did not accept the complete input" in pane.output.toPlainText()
    process.finish()


def test_moba_rail_labels_are_clickable_and_favorites_filter_is_reversible(
    gui_window,
) -> None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QLabel, QToolButton

    _app, window = gui_window
    moba_index = window.design_select.findData("mobaxterm")
    assert moba_index >= 0
    window.design_select.setCurrentIndex(moba_index)
    window.store.save(
        [
            Profile(
                name="favorite-host",
                protocol="ssh",
                host="favorite.example.invalid",
                tags=["favorite"],
            ),
            Profile(
                name="regular-host",
                protocol="ssh",
                host="regular.example.invalid",
            ),
        ]
    )
    window.refresh_profiles()

    sessions_label = next(
        label
        for label in window.findChildren(QLabel, "mobaRailLabel")
        if label.property("mobaRailRole") == "sessions"
    )
    sessions_button = next(
        button
        for button in window.findChildren(QToolButton)
        if button.property("mobaRailRole") == "sessions"
    )
    sessions_button.setChecked(False)
    QTest.mouseClick(sessions_label, Qt.MouseButton.LeftButton)
    assert sessions_button.isChecked()

    window.show_moba_favorites_rail()
    visible_names = {
        item.data(0, Qt.ItemDataRole.UserRole)
        for item in window.iter_profile_tree_items()
        if isinstance(item.data(0, Qt.ItemDataRole.UserRole), str)
        and not item.isHidden()
    }
    assert visible_names == {"favorite-host"}
    window.show_moba_sessions_rail()
    visible_names = {
        item.data(0, Qt.ItemDataRole.UserRole)
        for item in window.iter_profile_tree_items()
        if isinstance(item.data(0, Qt.ItemDataRole.UserRole), str)
        and not item.isHidden()
    }
    assert visible_names == {"favorite-host", "regular-host"}


def test_moba_sessions_rail_preserves_connected_sftp_dock(gui_window) -> None:
    from PyQt6.QtWidgets import QFrame

    _app, window = gui_window
    moba_index = window.design_select.findData("mobaxterm")
    assert moba_index >= 0
    window.design_select.setCurrentIndex(moba_index)
    dock = QFrame()
    dock.setObjectName("testConnectedSftpDock")
    window.moba_left_stack.addWidget(dock)
    window.moba_connected_dock = dock
    window.moba_left_stack.setCurrentWidget(dock)

    window.show_moba_sessions_rail()
    assert window.moba_connected_dock is dock
    assert window.moba_left_stack.currentWidget() is window.profile_list
    window.show_moba_sftp_rail()
    assert window.moba_left_stack.currentWidget() is dock


def _open_moba_interaction_test_dock(window, *, name: str):
    from remote_ops_workspace.terminal import TerminalPanePlan

    moba_index = window.design_select.findData("mobaxterm")
    assert moba_index >= 0
    window.design_select.setCurrentIndex(moba_index)
    profile = Profile(
        name=name,
        protocol="ssh",
        host="example.invalid",
        username="operator",
    )
    window.store.save([profile])
    window.refresh_profiles()
    panel = window.open_moba_connected_session_tab(
        profile,
        TerminalPanePlan(title=profile.name, command=[], source="test"),
        remote_path="/var/log",
    )
    dock = window.moba_connected_dock
    assert dock is not None
    return panel, dock


def test_moba_sftp_file_table_context_menu_routes_safe_actions(gui_window) -> None:
    from PyQt6.QtCore import Qt

    app, window = gui_window
    _panel, dock = _open_moba_interaction_test_dock(
        window,
        name="sftp-context-actions",
    )
    selected_file = next(
        dock.file_table.topLevelItem(index)
        for index in range(dock.file_table.topLevelItemCount())
        if dock.file_table.topLevelItem(index).text(0) == "app.log"
    )
    dock.file_table.setCurrentItem(selected_file)
    app.processEvents()
    calls: list[str] = []
    dock.show_moba_sftp_toolbar_action = lambda action_key: calls.append(action_key)

    assert (
        dock.file_table.contextMenuPolicy()
        == Qt.ContextMenuPolicy.CustomContextMenu
    )
    menu = dock.build_sftp_context_menu(selected_file)
    actions = {
        action.text(): action
        for action in menu.actions()
        if not action.isSeparator()
    }
    assert {
        "Open",
        "Download",
        "Upload here",
        "Copy remote path",
        "Parent folder",
        "Refresh listing",
        "Reconnect",
        "Focus terminal",
    }.issubset(actions)

    actions["Download"].trigger()
    actions["Parent folder"].trigger()
    actions["Reconnect"].trigger()
    assert calls == ["download", "parent-folder", "connect"]
    menu.deleteLater()


def test_moba_monitoring_controls_change_runtime_and_request_follow_refresh(
    gui_window,
) -> None:
    app, window = gui_window
    _panel, dock = _open_moba_interaction_test_dock(
        window,
        name="monitoring-runtime-actions",
    )
    remote_monitoring = dock.monitoring_control_widgets["remote-monitoring"]
    follow_folder = dock.monitoring_control_widgets["follow-terminal-folder"]
    monitoring_panel = dock.remote_monitoring_panel
    expanded_height = monitoring_panel.height()
    monitoring_refreshes: list[str] = []
    dock.request_remote_monitoring_refresh = lambda: monitoring_refreshes.append(
        "refresh"
    )
    app.processEvents()

    assert remote_monitoring.isChecked() is True
    assert dock.monitoring_refresh_timer.isActive() is True
    assert dock.property("mobaRemoteMonitoringRuntimeActive") is True
    assert follow_folder.isVisible() is True

    remote_monitoring.click()
    app.processEvents()
    assert remote_monitoring.isChecked() is False
    assert dock.monitoring_refresh_timer.isActive() is False
    assert dock.property("mobaRemoteMonitoringRuntimeActive") is False
    assert monitoring_panel.height() < expanded_height
    assert follow_folder.isVisible() is False

    remote_monitoring.click()
    app.processEvents()
    assert remote_monitoring.isChecked() is True
    assert dock.monitoring_refresh_timer.isActive() is True
    assert dock.property("mobaRemoteMonitoringRuntimeActive") is True
    assert monitoring_panel.height() == expanded_height
    assert follow_folder.isVisible() is True
    assert monitoring_refreshes

    refresh_reasons: list[str] = []
    dock.request_sftp_refresh = lambda *, reason: refresh_reasons.append(reason)
    follow_folder.click()
    app.processEvents()
    assert follow_folder.isChecked() is False
    assert dock.property("mobaMonitoringFollowEnabled") is False
    follow_folder.click()
    app.processEvents()
    assert follow_folder.isChecked() is True
    assert dock.property("mobaMonitoringFollowEnabled") is True
    assert refresh_reasons
    assert all(reason for reason in refresh_reasons)


def test_moba_runtime_shutdown_invalidates_late_monitoring_results(
    gui_window,
) -> None:
    from PyQt6.QtCore import QProcess

    app, window = gui_window
    _panel_a, dock_a = _open_moba_interaction_test_dock(
        window,
        name="monitoring-session-a",
    )
    control = dock_a.monitoring_control_widgets["remote-monitoring"]
    control.setChecked(False)
    app.processEvents()
    paused_state = dock_a.property("mobaRemoteMonitoringRuntimeState")

    dock_a.handle_remote_monitoring_error(QProcess.ProcessError.Crashed)
    assert dock_a.property("mobaRemoteMonitoringRuntimeState") == paused_state

    _panel_b, dock_b = _open_moba_interaction_test_dock(
        window,
        name="monitoring-session-b",
    )
    assert window.moba_connected_dock is dock_b
    assert dock_a.runtime_shutting_down is True
    assert dock_a.monitoring_refresh_timer.isActive() is False
    assert dock_a.sftp_refresh_timeout.isActive() is False
    assert dock_a.apply_live_remote_monitoring_snapshot(
        dock_a.state.monitoring
    ) is False
    assert dock_b.state.profile_name == "monitoring-session-b"


def test_moba_sftp_supersedes_stale_path_results_and_opens_current_row(
    gui_window,
) -> None:
    from PyQt6.QtCore import QProcess

    _app, window = gui_window
    _panel, dock = _open_moba_interaction_test_dock(
        window,
        name="sftp-path-generation",
    )
    selected_file = next(
        dock.file_table.topLevelItem(index)
        for index in range(dock.file_table.topLevelItemCount())
        if dock.file_table.topLevelItem(index).text(0) == "app.log"
    )
    assert dock.navigate_moba_sftp_path("/new/path")
    assert (
        dock.text_editor_remote_path_for_item(selected_file)
        == "/new/path/app.log"
    )

    original_entries = dock.state.file_entries
    dock.sftp_refresh_output_buffer = bytearray(
        b"-rw-r--r-- 1 root root 5 Jan 1 00:00 stale.log\n"
    )
    dock.sftp_refresh_request_path = "/old/path"
    dock.sftp_refresh_active_generation = 1
    dock.sftp_refresh_generation = 2
    dock.handle_sftp_refresh_finished(
        0,
        QProcess.ExitStatus.NormalExit,
    )

    assert dock.state.file_entries == original_entries
    assert dock.state.remote_path != "/old/path"
    assert "superseded" in window.statusBar().currentMessage().lower()


def test_moba_profile_and_rail_context_menus_expose_workflows(gui_window) -> None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QLabel

    _app, window = gui_window
    moba_index = window.design_select.findData("mobaxterm")
    assert moba_index >= 0
    window.design_select.setCurrentIndex(moba_index)
    profile = Profile(
        name="context-profile",
        protocol="ssh",
        host="context.example.invalid",
    )
    window.store.save([profile])
    window.refresh_profiles()
    window.select_profile(profile.name)
    selected = window.profile_list.currentItem()
    assert selected is not None

    assert (
        window.profile_list.contextMenuPolicy()
        == Qt.ContextMenuPolicy.CustomContextMenu
    )
    profile_menu = window.build_profile_context_menu(selected)
    profile_actions = [
        action.text()
        for action in profile_menu.actions()
        if not action.isSeparator()
    ]
    profile_copy = " ".join(profile_actions).lower()
    for expected in ("connect", "preview", "edit", "remove", "refresh"):
        assert expected in profile_copy
    assert "sftp" in profile_copy or "files" in profile_copy

    rail_targets = [
        *window.moba_rail_buttons,
        *window.findChildren(QLabel, "mobaRailLabel"),
    ]
    assert rail_targets
    assert all(
        target.contextMenuPolicy() == Qt.ContextMenuPolicy.CustomContextMenu
        for target in rail_targets
    )
    rail_menu = window.build_moba_rail_context_menu()
    rail_actions = {
        action.text()
        for action in rail_menu.actions()
        if not action.isSeparator()
    }
    assert {"Sessions", "Favorites", "Tools", "Macros"}.issubset(rail_actions)
    assert any("SFTP" in action for action in rail_actions)
    profile_menu.deleteLater()
    rail_menu.deleteLater()


def test_running_tab_close_is_immediate_and_cancels_pending_restart(gui_window) -> None:
    from PyQt6.QtCore import QProcess
    from PyQt6.QtTest import QTest

    from remote_ops_workspace.gui_lifecycle import ProcessStopPolicy
    from remote_ops_workspace.terminal import TerminalPanePlan

    _app, window = gui_window
    pane = window.new_terminal_pane(
        TerminalPanePlan(title="close-test", command=[], source="test")
    )
    process = _FakeProcess(pane)
    process.process_state = QProcess.ProcessState.Running
    process.finished.connect(pane.on_finished)
    pane.process = process
    pane._restart_after_stop = True
    index = window.add_workspace_tab(pane, "close-test", role="terminal")
    window.CLOSE_STOP_POLICY = ProcessStopPolicy(
        terminate_timeout_ms=10,
        kill_timeout_ms=0,
    )
    window.confirm_stop_processes = lambda *_args: True

    window.close_tab(index)

    assert window.tabs.indexOf(pane) == -1
    assert pane in window._closing_tab_widgets
    assert pane.property("terminalClosing") is True
    assert pane._restart_after_stop is False
    assert process.terminated is True
    QTest.qWait(30)
    assert process.killed is True
    assert pane not in window._closing_tab_widgets
    assert process.process_state == QProcess.ProcessState.NotRunning


def test_moba_sftp_dock_routes_supported_actions_and_disables_stubs(gui_window) -> None:
    from remote_ops_workspace.terminal import TerminalPanePlan

    app, window = gui_window
    moba_index = window.design_select.findData("mobaxterm")
    assert moba_index >= 0
    window.design_select.setCurrentIndex(moba_index)
    profile = Profile(
        name="sftp-actions",
        protocol="ssh",
        host="example.invalid",
        username="operator",
    )
    window.store.save([profile])
    window.refresh_profiles()
    panel = window.open_moba_connected_session_tab(
        profile,
        TerminalPanePlan(title=profile.name, command=[], source="test"),
        remote_path="/var/log",
    )
    dock = window.moba_connected_dock
    assert dock is not None

    for action_key in {"new-folder", "new-file", "delete", "ascii-mode", "split-view"}:
        button = dock.sftp_action_buttons[action_key]
        assert button.isEnabled() is False
        assert button.property("mobaSftpActionOperational") is False

    dock.path.setText("/var/log")
    dock.path.returnPressed.emit()
    assert dock.active_remote_path == "/var/log"
    dock.sftp_action_buttons["parent-folder"].click()
    assert dock.active_remote_path == "/var"
    assert dock.path.text() == "/var"

    selected_file = next(
        dock.file_table.topLevelItem(index)
        for index in range(dock.file_table.topLevelItemCount())
        if dock.file_table.topLevelItem(index).text(0) == "app.log"
    )
    dock.file_table.setCurrentItem(selected_file)
    app.processEvents()
    assert dock.sftp_action_buttons["download"].isEnabled() is True

    calls: list[str] = []
    dock.open_moba_sftp_transfer_workflow = lambda action_key: calls.append(action_key) or True
    dock.sftp_action_buttons["download"].click()
    panel.terminal_pane.restart = lambda *_args: calls.append("connect")
    dock.sftp_action_buttons["connect"].click()
    dock.sftp_action_buttons["terminal"].click()
    app.processEvents()

    assert calls == ["download", "connect"]
    assert panel.terminal_pane.output.property("mobaTerminalFocusRequested") is True


@pytest.fixture
def gui_window(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("ROW_HOME", str(tmp_path / "row-home"))
    pytest.importorskip("PyQt6")
    from remote_ops_workspace.gui import create_main_window

    app, window = create_main_window(["gui-dialog-hardening"], show=False)
    window.resize(800, 600)
    window.move(0, 0)
    window.show()
    app.processEvents()
    yield app, window
    window.close()
    app.processEvents()


def test_dynamic_dialog_labels_are_plain_text_and_frames_stay_on_parent_screen(gui_window) -> None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QDialogButtonBox, QFrame, QLabel

    app, window = gui_window
    profile = Profile(
        name="literal <b>profile</b>",
        protocol="sftp",
        host="example.invalid",
        username="operator",
    )
    result = ProfileImportResult(source_format="row", profiles=[profile])
    dialogs = [
        window.create_profile_import_preview_dialog("C:/<b>literal</b>/profiles.json", result),
        window.create_transfer_queue_dialog(profile),
        window.create_workflow_dialog(
            "<b>literal title</b>",
            "<i>literal subtitle</i>",
            [("workflow", "ready", "literal")],
            "detail",
        ),
    ]

    for dialog in dialogs:
        dialog.show()
        app.processEvents()
        app.processEvents()
        available = dialog.screen().availableGeometry()
        assert available.contains(dialog.frameGeometry())

    import_source = dialogs[0].findChild(QLabel, "profileImportSource")
    transfer_subtitle = dialogs[1].findChild(QLabel, "workflowSubtitle")
    workflow_title = dialogs[2].findChild(QLabel, "workflowTitle")
    workflow_subtitle = dialogs[2].findChild(QLabel, "workflowSubtitle")
    assert import_source.textFormat() == Qt.TextFormat.PlainText
    assert "<b>literal</b>" in import_source.text()
    assert transfer_subtitle.textFormat() == Qt.TextFormat.PlainText
    assert "<b>profile</b>" in transfer_subtitle.text()
    assert workflow_title.textFormat() == Qt.TextFormat.PlainText
    assert workflow_title.text() == "<b>literal title</b>"
    assert workflow_subtitle.textFormat() == Qt.TextFormat.PlainText
    assert workflow_subtitle.text() == "<i>literal subtitle</i>"

    assert dialogs[0].findChild(QDialogButtonBox, "profileImportDialogButtons").isVisible()
    assert dialogs[1].findChild(QDialogButtonBox, "transferQueueDialogButtons").isVisible()
    assert dialogs[2].findChild(QFrame, "workflowFooter").isVisible()
    for dialog in dialogs:
        dialog.close()


class _Signal:
    def __init__(self) -> None:
        self.callbacks = []

    def connect(self, callback) -> None:
        self.callbacks.append(callback)

    def emit(self, *args) -> None:
        for callback in tuple(self.callbacks):
            callback(*args)


@dataclass
class _FakeProcessOptions:
    fail_to_start: bool = False


class _FakeProcess:
    def __init__(self, parent, *, options: _FakeProcessOptions | None = None) -> None:
        from PyQt6.QtCore import QProcess

        self.parent = parent
        self.options = options or _FakeProcessOptions()
        self.readyReadStandardOutput = _Signal()
        self.readyReadStandardError = _Signal()
        self.started = _Signal()
        self.finished = _Signal()
        self.errorOccurred = _Signal()
        self.process_state = QProcess.ProcessState.NotRunning
        self.program = ""
        self.arguments = []
        self.written = b""
        self.stdout = b""
        self.stderr = b""
        self.terminated = False
        self.killed = False
        self.deleted = False

    def setProgram(self, program: str) -> None:
        self.program = program

    def setArguments(self, arguments: list[str]) -> None:
        self.arguments = arguments

    def start(self) -> None:
        from PyQt6.QtCore import QProcess

        if self.options.fail_to_start:
            self.process_state = QProcess.ProcessState.NotRunning
            self.errorOccurred.emit(QProcess.ProcessError.FailedToStart)
            return
        self.process_state = QProcess.ProcessState.Running
        self.started.emit()

    def state(self):
        return self.process_state

    def write(self, data: bytes) -> int:
        self.written += data
        return len(data)

    def closeWriteChannel(self) -> None:
        return None

    def readAllStandardOutput(self) -> bytes:
        output = self.stdout
        self.stdout = b""
        return output

    def readAllStandardError(self) -> bytes:
        output = self.stderr
        self.stderr = b""
        return output

    def errorString(self) -> str:
        return "controlled start failure"

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        from PyQt6.QtCore import QProcess

        self.killed = True
        self.process_state = QProcess.ProcessState.NotRunning
        self.finished.emit(-1, QProcess.ExitStatus.CrashExit)

    def finish(self, exit_code: int = 0) -> None:
        from PyQt6.QtCore import QProcess

        self.process_state = QProcess.ProcessState.NotRunning
        status = QProcess.ExitStatus.NormalExit if exit_code == 0 else QProcess.ExitStatus.CrashExit
        self.finished.emit(exit_code, status)

    def deleteLater(self) -> None:
        self.deleted = True


class _ShortWriteProcess(_FakeProcess):
    def write(self, data: bytes) -> int:
        accepted = data[:1]
        self.written += accepted
        return len(accepted)


def test_transfer_queue_owns_process_lifecycle_until_completion_and_cancel(gui_window) -> None:
    from PyQt6.QtGui import QCloseEvent
    from PyQt6.QtWidgets import QDialogButtonBox

    _app, window = gui_window
    profile = Profile(name="queue", protocol="sftp", host="example.invalid", username="operator")
    processes: list[_FakeProcess] = []

    def process_factory(parent):
        process = _FakeProcess(parent)
        processes.append(process)
        return process

    dialog = window.create_transfer_queue_dialog(profile, process_factory=process_factory)
    dialog.operations.setPlainText("get /remote/file ./local-file")
    dialog.run_queue()
    process = processes[-1]
    process.stdout = b"<b>literal stdout</b>"
    process.stderr = b"<i>literal stderr</i>"
    process.readyReadStandardOutput.emit()
    process.readyReadStandardError.emit()
    assert "<b>literal stdout</b>" in dialog.preview.toPlainText()
    assert "<i>literal stderr</i>" in dialog.preview.toPlainText()
    assert dialog.queue_is_active()
    assert not dialog.operations.isEnabled()
    assert not dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()
    assert not dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel).isEnabled()
    assert dialog.cancel_queue_button.isEnabled()

    dialog.accept()
    dialog.reject()
    assert dialog.result() == 0
    active_close = QCloseEvent()
    dialog.closeEvent(active_close)
    assert not active_close.isAccepted()
    process.finish(0)
    assert not dialog.queue_is_active()
    assert dialog.operations.isEnabled()
    assert dialog.run_button.isEnabled()
    assert "queue completed" in dialog.preview.toPlainText()
    assert process.deleted
    inactive_close = QCloseEvent()
    dialog.closeEvent(inactive_close)
    assert inactive_close.isAccepted()

    dialog.operations.setPlainText("get /remote/file ./local-file")
    dialog.run_queue()
    process = processes[-1]
    dialog.cancel_queue()
    assert process.terminated
    assert dialog.queue_is_active()
    assert not dialog.cancel_queue_button.isEnabled()
    dialog.kill_cancelled_queue_process()
    assert process.killed
    assert not dialog.queue_is_active()
    assert "queue cancelled" in dialog.preview.toPlainText()


def test_transfer_queue_failed_to_start_resets_all_controls(gui_window) -> None:
    _app, window = gui_window
    profile = Profile(name="queue", protocol="sftp", host="example.invalid", username="operator")

    def process_factory(parent):
        return _FakeProcess(parent, options=_FakeProcessOptions(fail_to_start=True))

    dialog = window.create_transfer_queue_dialog(profile, process_factory=process_factory)
    dialog.operations.setPlainText("get /remote/file ./local-file")
    dialog.run_queue()

    assert not dialog.queue_is_active()
    assert dialog.operations.isEnabled()
    assert dialog.run_button.isEnabled()
    assert not dialog.cancel_queue_button.isEnabled()
    assert "controlled start failure" in dialog.preview.toPlainText()
    assert "queue stopped after failure" in dialog.preview.toPlainText()


def test_activity_log_append_preserves_markup_like_text_literally(gui_window) -> None:
    _app, window = gui_window
    window.log.append("profile <b>literal</b> & remote")
    assert "profile <b>literal</b> & remote" in window.log.toPlainText()


def test_tab_tooltip_preserves_raw_text_but_escapes_qt_rich_text(gui_window) -> None:
    from PyQt6.QtWidgets import QWidget

    _app, window = gui_window
    widget = QWidget()
    index = window.add_workspace_tab(widget, "profile <b>literal</b> & remote")

    assert widget.property("tabTooltipBaseText") == "profile <b>literal</b> & remote"
    assert widget.property("tabTooltipPlainText") == (
        "profile <b>literal</b> & remote: running"
    )
    assert window.tabs.tabToolTip(index) == (
        "<qt>profile &lt;b&gt;literal&lt;/b&gt; &amp; remote: running</qt>"
    )

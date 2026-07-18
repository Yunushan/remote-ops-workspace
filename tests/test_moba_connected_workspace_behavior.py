from __future__ import annotations

import pytest

from remote_ops_workspace.models import Profile
from remote_ops_workspace.terminal import TerminalPanePlan


@pytest.fixture
def gui_window(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("ROW_HOME", str(tmp_path / "row-home"))
    pytest.importorskip("PyQt6")
    from remote_ops_workspace.gui import create_main_window

    app, window = create_main_window(["moba-connected-workspace-behavior"], show=False)
    window.resize(1280, 800)
    window.move(0, 0)
    window.show()
    app.processEvents()
    yield app, window
    window.close()
    app.processEvents()


def _open_connected_panel(gui_window):
    app, window = gui_window
    index = window.design_select.findData("mobaxterm")
    assert index >= 0
    window.design_select.setCurrentIndex(index)
    panel = window.open_moba_connected_session_tab(
        Profile(
            name="moba-behavior",
            protocol="ssh",
            host="moba-behavior.example.invalid",
            username="operator",
        ),
        TerminalPanePlan(
            title="moba-behavior",
            command=[],
            source="test",
        ),
    )
    app.processEvents()
    dock = window.moba_connected_dock
    assert dock is not None
    dock.monitoring_control_widgets["remote-monitoring"].setChecked(False)
    app.processEvents()
    return app, window, panel, dock


def test_moba_connected_terminal_uses_truthful_scrollable_preamble_and_pty_input(
    gui_window,
) -> None:
    from PyQt6.QtWidgets import QFrame

    _app, _window, panel, _dock = _open_connected_panel(gui_window)
    pane = panel.terminal_pane
    transcript = pane.output.toPlainText()

    assert panel.findChild(QFrame, "mobaSshBannerSlot") is None
    assert panel.findChild(QFrame, "mobaRightUtilityRail") is None
    assert pane.output.property("terminalStartupPreambleScrollable") is True
    assert "$ " not in transcript
    assert "Waiting for authentication and server output." in transcript
    assert transcript.count("* Direct SSH:") == 1
    assert transcript.count("* SSH compression:") == 1
    assert transcript.count("* SSH browser:") == 1
    assert transcript.count("* X11 forwarding:") == 1
    assert "Last login:" not in transcript
    assert pane.input.isVisible() is True

    pane.process.is_pty = True
    panel.apply_moba_plain_terminal_mode(pane)
    assert pane.input.isVisible() is False
    assert pane.property("mobaTerminalInputMode") == "native-pty-direct"
    assert pane.output.property("mobaTerminalLineInputFallback") is False


def test_moba_terminal_and_telemetry_share_operational_context_actions(
    gui_window,
) -> None:
    from PyQt6.QtCore import Qt

    _app, _window, panel, _dock = _open_connected_panel(gui_window)
    menu = panel.build_moba_terminal_context_menu(panel.terminal_pane)
    labels = [action.text() for action in menu.actions() if not action.isSeparator()]

    assert menu.objectName() == "mobaTerminalContextMenu"
    assert "Copy" in labels
    assert "Save to file" in labels
    assert "Paste" in labels
    assert "Display host information" in labels
    host_action = next(
        action for action in menu.actions() if action.text() == "Display host information"
    )
    assert host_action.isCheckable()
    host_action.setChecked(False)
    assert panel.telemetry_cell_frames["target"].isVisible() is False
    assert (
        panel.telemetry_bar.contextMenuPolicy()
        == Qt.ContextMenuPolicy.CustomContextMenu
    )
    assert panel.telemetry_bar.property("mobaTelemetryVisibilityChangedKey") == "target"
    menu.deleteLater()


def test_moba_terminal_context_routes_to_originating_or_active_split(
    gui_window,
) -> None:
    from PyQt6.QtCore import Qt

    _app, window, panel, _dock = _open_connected_panel(gui_window)
    second = window.new_terminal_pane(
        TerminalPanePlan(title="second", command=[], source="test")
    )
    panel.add_terminal_split(second, Qt.Orientation.Horizontal)

    assert panel.moba_terminal_context_pane(second.output) is second
    window._last_terminal_pane = second
    assert panel.moba_terminal_context_pane(panel.telemetry_bar) is second


def test_terminal_key_payload_covers_common_interactive_terminal_keys(
    gui_window,
) -> None:
    from PyQt6.QtCore import Qt

    _app, _window, panel, _dock = _open_connected_panel(gui_window)

    class KeyEvent:
        def __init__(self, key, modifiers=Qt.KeyboardModifier.NoModifier, text=""):
            self._key = key
            self._modifiers = modifiers
            self._text = text

        def key(self):
            return self._key

        def modifiers(self):
            return self._modifiers

        def text(self):
            return self._text

    payload = panel.terminal_pane.terminal_key_payload
    assert payload(KeyEvent(Qt.Key.Key_F1)) == b"\x1bOP"
    assert payload(KeyEvent(Qt.Key.Key_F12)) == b"\x1b[24~"
    assert payload(KeyEvent(Qt.Key.Key_Insert)) == b"\x1b[2~"
    assert (
        payload(KeyEvent(Qt.Key.Key_Tab, Qt.KeyboardModifier.ShiftModifier, "\t"))
        == b"\x1b[Z"
    )
    assert (
        payload(KeyEvent(Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier, " "))
        == b"\x00"
    )
    assert (
        payload(KeyEvent(Qt.Key.Key_Up, Qt.KeyboardModifier.ShiftModifier))
        == b"\x1b[1;2A"
    )
    assert (
        payload(KeyEvent(Qt.Key.Key_End, Qt.KeyboardModifier.ControlModifier))
        == b"\x1b[1;5F"
    )
    assert (
        payload(KeyEvent(Qt.Key.Key_PageDown, Qt.KeyboardModifier.AltModifier))
        == b"\x1b[6;3~"
    )


def test_moba_sftp_editor_and_monitoring_remain_compact_and_non_synthetic(
    gui_window,
) -> None:
    from remote_ops_workspace.gui_designs import (
        gui_design_moba_remote_monitoring_dock_chrome,
    )

    _app, _window, _panel, dock = _open_connected_panel(gui_window)
    names = [
        dock.file_table.topLevelItem(row).text(0)
        for row in range(dock.file_table.topLevelItemCount())
    ]

    assert names.count("..") == 1
    assert "." not in names
    assert dock.text_editor_toolbar.isVisible() is False
    assert dock.text_editor.isVisible() is False
    assert dock.text_editor.property("mobaTextEditorContentLoaded") is False
    assert dock.text_editor.toPlainText() == ""
    assert (
        dock.remote_monitoring_panel.height()
        == gui_design_moba_remote_monitoring_dock_chrome().static_height
    )
    assert dock.monitoring_control_widgets["remote-monitoring"].isVisible() is True
    assert (
        dock.monitoring_control_widgets["follow-terminal-folder"].isVisible()
        is True
    )
    assert dock.monitoring_status_label.isVisible() is False
    assert dock.monitoring_refresh_button.isVisible() is False
    assert dock.monitoring_last_refresh_label.isVisible() is False


def test_background_sftp_is_auth_gated_and_compact_status_is_visible(
    gui_window,
    monkeypatch,
    tmp_path,
) -> None:
    _app, _window, _panel, dock = _open_connected_panel(gui_window)

    assert dock.property("mobaBackgroundSshAuthAvailable") is False
    assert dock.property("mobaSftpRuntimeState") == "auth-required"
    assert (
        dock.sftp_status_badge.property("mobaSftpStatusBadgeState")
        == "auth-required"
    )
    assert "separate non-interactive" in dock.sftp_status_badge.toolTip()
    assert dock.monitoring_control_widgets["remote-monitoring"].isChecked() is False
    assert not int(dock.property("mobaSftpRefreshRequestCount") or 0)

    identity = tmp_path / "id_test"
    identity.write_text("test-only-key-placeholder", encoding="utf-8")
    profile = Profile(
        name="key-auth",
        protocol="ssh",
        host="key-auth.example.invalid",
        username="operator",
        identity_file=str(identity),
    )
    refresh_reasons = []
    monitoring_starts = []
    monkeypatch.setattr(dock, "profile_for_sftp_action", lambda: profile)
    monkeypatch.setattr(
        dock,
        "request_sftp_refresh",
        lambda *, reason="manual": refresh_reasons.append(reason),
    )
    monkeypatch.setattr(
        dock,
        "activate_initial_monitoring_state",
        lambda: monitoring_starts.append(True),
    )

    dock.activate_initial_background_state()

    assert refresh_reasons == ["initial-key-agent-auth"]
    assert monitoring_starts == [True]
    assert dock.property("mobaBackgroundSshAuthAvailable") is True
    assert dock.property("mobaSftpRuntimeState") == "pending"


def test_moba_special_tabs_stay_anchored_and_plus_acts_without_selection(
    gui_window,
    monkeypatch,
) -> None:
    _app, window, _panel, _dock = _open_connected_panel(gui_window)
    tab_bar = window.tabs.tabBar()
    original_index = window.tabs.currentIndex()
    original_count = window.tabs.count()
    opened = []
    monkeypatch.setattr(window, "open_local_terminal_tab", lambda: opened.append(True))

    plus_index = window.find_tab_by_role("new-session")
    assert plus_index == window.tabs.count() - 1
    assert tab_bar.activate_special_tab(plus_index) is True
    assert opened == [True]
    assert window.tabs.currentIndex() == original_index
    assert window.tabs.count() == original_count

    home_index = window.find_tab_by_role("home")
    tab_bar.moveTab(home_index, min(2, tab_bar.count() - 1))
    tab_bar.moveTab(window.find_tab_by_role("new-session"), 0)
    assert window.find_tab_by_role("home") == 0
    assert window.find_tab_by_role("new-session") == window.tabs.count() - 1


def test_moba_tab_and_vertical_rail_use_measured_dpi_aware_chrome(
    gui_window,
) -> None:
    from PyQt6.QtWidgets import QLabel

    _app, window, _panel, _dock = _open_connected_panel(gui_window)
    tab_bar = window.tabs.tabBar()
    index = window.tabs.currentIndex()
    tab_widget = window.tabs.widget(index)
    assert tab_widget is not None

    assert tab_bar.property("mobaCompactTabWidths") is True
    assert tab_bar.tabSizeHint(index).width() == tab_widget.property(
        "mobaTabStaticWidth"
    )
    labels = window.findChildren(QLabel, "mobaRailLabel")
    assert labels
    assert all(
        label.property("mobaRailTextRenderMode")
        == "device-pixel-pixmap"
        for label in labels
    )
    assert all(label.property("mobaRailTextTransformation") == "none" for label in labels)
    for label in labels:
        pixmap = label.rail_text_pixmap()
        assert not pixmap.isNull()
        assert label.property("mobaRailTextPixmapReady") is True
        assert float(label.property("mobaRailTextPixmapDevicePixelRatio")) >= 1.0
        assert label.property("mobaRailTextPixmapRenderMode") == "dpr-aware-rotated-pixmap"
        assert label.property("mobaRailTextPixmapPhysicalSize")
        assert label.property("mobaRailTextPixmapLogicalSize")

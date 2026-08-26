from __future__ import annotations

import os

import pytest

from remote_ops_workspace.models import Profile
from remote_ops_workspace.terminal import TerminalPanePlan


@pytest.fixture
def gui_window(monkeypatch, tmp_path):
    if "QT_QPA_PLATFORM" not in os.environ:
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("ROW_HOME", str(tmp_path / "row-home"))
    pytest.importorskip("PyQt6")
    from remote_ops_workspace.gui import create_main_window

    app, window = create_main_window(
        ["moba-connected-workspace-behavior"],
        show=False,
        preview_samples=True,
    )
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
    panel.terminal_pane.output.selectAll()
    selected = panel.terminal_pane.output.textCursor().selectedText()
    menu = panel.build_moba_terminal_context_menu(panel.terminal_pane)
    labels = [action.text() for action in menu.actions() if not action.isSeparator()]

    assert menu.objectName() == "mobaTerminalContextMenu"
    assert "Copy" in labels
    assert "Save to file" in labels
    assert "Paste" in labels
    assert "Display host information" in labels
    copy_action = next(action for action in menu.actions() if action.text() == "Copy")
    assert copy_action.isEnabled()
    copy_action.trigger()
    assert panel.terminal_pane.output.property("terminalLastCopiedText") == selected.replace(
        "\u2029", "\n"
    )
    assert panel.terminal_pane.output.textCursor().selectedText() == selected
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
    monkeypatch,
) -> None:
    from PyQt6.QtCore import Qt

    _app, window, panel, _dock = _open_connected_panel(gui_window)
    second = window.new_terminal_pane(
        TerminalPanePlan(title="second", command=[], source="test")
    )
    panel.add_terminal_split(second, Qt.Orientation.Horizontal)

    assert panel.moba_terminal_context_pane(second.output) is second
    monkeypatch.setattr(window, "active_terminal_pane", lambda: second)
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
        payload(KeyEvent(Qt.Key.Key_BracketLeft, Qt.KeyboardModifier.ControlModifier, "["))
        == b"\x1b"
    )
    assert payload(KeyEvent(0x5B, Qt.KeyboardModifier.ControlModifier)) == b"\x1b"
    assert (
        payload(KeyEvent(Qt.Key.Key_Question, Qt.KeyboardModifier.ControlModifier, "?"))
        is None
    )
    assert (
        payload(KeyEvent(Qt.Key.Key_A, Qt.KeyboardModifier.MetaModifier, "a"))
        is None
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
    panel.terminal_pane.terminal_emulator.feed("\x1b[?1h")
    assert payload(KeyEvent(Qt.Key.Key_Up)) == b"\x1bOA"
    assert payload(KeyEvent(Qt.Key.Key_Home)) == b"\x1bOH"
    assert (
        payload(KeyEvent(Qt.Key.Key_Left, Qt.KeyboardModifier.ControlModifier))
        == b"\x1b[1;5D"
    )
    panel.terminal_pane.terminal_emulator.feed("\x1b[?1l")
    assert payload(KeyEvent(Qt.Key.Key_Up)) == b"\x1b[A"


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
    # The compact dock keeps status and the manual refresh affordance visible
    # even while monitoring is paused, so auth-gated/unavailable states are
    # explainable instead of looking like a dead footer.
    assert dock.monitoring_status_label.isVisible() is True
    assert dock.monitoring_refresh_button.isVisible() is True
    # The timestamp is rendered inline in the status label so it does not
    # overlap the fixed follow-folder control in the compact footer.
    assert dock.monitoring_last_refresh_label.isVisible() is False
    assert dock.sftp_transfer_menu_button.objectName() == "mobaSftpTransferMenu"
    assert set(dock.sftp_transfer_menu_actions) >= {"download", "upload", "refresh"}


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


def test_background_auth_uses_vault_credential_for_session_only(
    gui_window,
    monkeypatch,
) -> None:
    from PyQt6.QtWidgets import QInputDialog

    _app, _window, _panel, dock = _open_connected_panel(gui_window)
    profile = Profile(
        name="vault-auth",
        protocol="ssh",
        host="vault-auth.example.invalid",
        username="operator",
        credential_ref="prod/vault-auth-password",
    )
    activated: list[bool] = []
    monkeypatch.setattr(dock, "profile_for_sftp_action", lambda: profile)
    monkeypatch.setattr(
        dock,
        "_apply_initial_background_state",
        lambda *, start_runtime: activated.append(start_runtime),
    )
    monkeypatch.setattr(
        QInputDialog,
        "getText",
        staticmethod(lambda *_args, **_kwargs: ("vault-passphrase", True)),
    )

    from remote_ops_workspace.vault import LocalVault

    monkeypatch.setattr(
        LocalVault,
        "get",
        lambda _vault, name, passphrase: (
            "ssh-password"
            if name == profile.credential_ref and passphrase == "vault-passphrase"
            else (_ for _ in ()).throw(AssertionError("unexpected vault lookup"))
        ),
    )

    assert dock.authenticate_background_tools() is True
    assert dock.property("mobaBackgroundSshCredentialRef") == profile.credential_ref
    assert dock.property("mobaBackgroundSshCredentialLoaded") is True
    assert dock._background_password == bytearray(b"ssh-password")
    assert activated == [True]
    assert dock.background_ssh_auth_capability(profile)[0] is True

    dock.shutdown_runtime()
    assert dock._background_password is None
    assert dock.property("mobaBackgroundSshCredentialLoaded") is False


def test_background_auth_can_use_direct_password_for_password_only_profile(
    gui_window,
    monkeypatch,
) -> None:
    from PyQt6.QtWidgets import QInputDialog

    _app, _window, _panel, dock = _open_connected_panel(gui_window)
    profile = Profile(
        name="password-only-auth",
        protocol="ssh",
        host="password-only.example.invalid",
        username="operator",
    )
    activated: list[bool] = []
    monkeypatch.setattr(dock, "profile_for_sftp_action", lambda: profile)
    monkeypatch.setattr(
        dock,
        "_apply_initial_background_state",
        lambda *, start_runtime: activated.append(start_runtime),
    )
    monkeypatch.setattr(
        QInputDialog,
        "getText",
        staticmethod(lambda *_args, **_kwargs: ("ssh-password", True)),
    )

    assert dock.authenticate_background_tools() is True
    assert dock.property("mobaBackgroundSshCredentialSource") == "session-prompt"
    assert dock.property("mobaBackgroundSshCredentialLoaded") is True
    assert dock._background_password == bytearray(b"ssh-password")
    assert activated == [True]
    assert "password entered" in dock.background_ssh_auth_detail()

    dock.shutdown_runtime()
    assert dock._background_password is None
    assert dock.property("mobaBackgroundSshCredentialSource") == ""


def test_background_state_activation_is_parented_and_cancelled_on_shutdown(
    gui_window,
) -> None:
    _app, _window, _panel, dock = _open_connected_panel(gui_window)

    timer = dock.background_state_activation_timer
    assert timer.parent() is dock
    assert timer.isSingleShot() is True

    _window.refresh_moba_background_after_terminal_start(_panel.terminal_pane)
    assert timer.isActive() is True

    dock.shutdown_runtime()
    assert timer.isActive() is False


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


def test_compact_text_and_icons_keep_device_pixel_rendering(
    gui_window,
) -> None:
    from PyQt6.QtCore import QSize
    from PyQt6.QtGui import QFont
    from PyQt6.QtWidgets import QLabel

    app, window, panel, _dock = _open_connected_panel(gui_window)

    assert app.font().hintingPreference() == QFont.HintingPreference.PreferFullHinting
    assert (
        panel.terminal_pane.output.font().hintingPreference()
        == QFont.HintingPreference.PreferFullHinting
    )
    telemetry_label = panel.telemetry_bar.findChild(QLabel, "mobaTelemetryItem")
    assert telemetry_label is not None
    assert telemetry_label.font().hintingPreference() == QFont.HintingPreference.PreferFullHinting

    icons = (
        panel.moba_utility_icon("clip", "#f4c430"),
        window.mremoteng_document_control_icon("ssh", size=16),
        window.securecrt_session_manager_action_icon("folder", size=16),
    )
    for icon in icons:
        pixmap = icon.pixmap(QSize(20, 20))
        assert not pixmap.isNull()
        assert float(pixmap.devicePixelRatio()) >= 1.0

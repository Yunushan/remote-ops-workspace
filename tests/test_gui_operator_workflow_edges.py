from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from remote_ops_workspace.models import Profile
from remote_ops_workspace.terminal import TerminalPanePlan


def _set_closure_value(monkeypatch, function, name: str, value) -> None:
    index = function.__code__.co_freevars.index(name)
    closure = function.__closure__
    assert closure is not None
    monkeypatch.setattr(closure[index], "cell_contents", value)


@pytest.fixture
def gui_window(monkeypatch, tmp_path):
    if "QT_QPA_PLATFORM" not in os.environ:
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("ROW_HOME", str(tmp_path / "row-home"))
    pytest.importorskip("PyQt6")
    from remote_ops_workspace.gui import create_main_window

    app, window = create_main_window(
        ["gui-operator-workflow-edges"],
        show=False,
        preview_samples=False,
    )
    window.resize(1180, 760)
    window.show()
    app.processEvents()
    yield app, window
    window.close()
    app.processEvents()


def test_quick_connect_suggestions_execution_and_status_surfaces(
    gui_window,
    monkeypatch,
) -> None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QTreeWidgetItem

    from remote_ops_workspace.gui import QuickConnectCandidate
    from remote_ops_workspace.gui_designs import gui_design_moba_quick_connect_chrome

    _app, window = gui_window
    saved = Profile(
        name="saved-edge",
        protocol="ssh",
        host="saved.example.invalid",
        username="operator",
    )

    class _Store:
        profiles = [saved]

        def load(self, *_args, **_kwargs):
            return list(self.profiles)

        def get(self, name: str):
            if name == saved.name:
                return saved
            raise KeyError(name)

    window.store = _Store()
    monkeypatch.setattr(window, "current_design_is_moba", lambda: False)
    window.quick_connect.setText("saved-edge")
    window.update_quick_connect_suggestions()
    assert window.quick_connect_suggestions.isHidden() is True

    monkeypatch.setattr(window, "current_design_is_moba", lambda: True)
    idle_calls: list[str] = []
    monkeypatch.setattr(
        window,
        "current_moba_connected_dock_is_active",
        lambda: True,
    )
    monkeypatch.setattr(
        window,
        "set_moba_quick_connect_connected_idle",
        lambda: idle_calls.append("idle"),
    )
    window.quick_connect.setText(
        gui_design_moba_quick_connect_chrome().connected_idle_query
    )
    window.update_quick_connect_suggestions()
    assert idle_calls

    monkeypatch.setattr(
        window,
        "current_moba_connected_dock_is_active",
        lambda: False,
    )
    launched: list[tuple[str, str]] = []
    selected: list[str] = []
    connected: list[bool] = []
    monkeypatch.setattr(
        window,
        "launch_profile",
        lambda profile, **kwargs: launched.append(
            (profile.name, str(kwargs["prefix"]))
        ),
    )
    monkeypatch.setattr(window, "select_profile", selected.append)
    monkeypatch.setattr(window, "connect_selected", connected.append)

    window.quick_connect.setText("ssh operator@direct.example.invalid:2222")
    window.update_quick_connect_suggestions()
    assert window.quick_connect_suggestions.topLevelItemCount() == 1
    direct_item = window.quick_connect_suggestions.topLevelItem(0)
    assert direct_item.data(0, Qt.ItemDataRole.UserRole).kind == "direct"
    window.run_quick_connect()
    assert launched and launched[-1][1] == "QUICK CONNECT"

    window.quick_connect.setText("saved-edge")
    window.update_quick_connect_suggestions()
    window.run_quick_connect()
    assert selected == ["saved-edge"]
    assert connected == [False]

    invalid_item = QTreeWidgetItem(["invalid"])
    invalid_item.setData(0, Qt.ItemDataRole.UserRole, "not-a-candidate")
    window.run_quick_connect_candidate(invalid_item)
    inert = QuickConnectCandidate("other", "Other", "No launch target")
    window.run_quick_connect_candidate_value(inert)

    window.quick_connect_suggestions.clear()
    window.quick_connect.setText("definitely not a valid endpoint")
    window.run_quick_connect()
    assert "QUICK CONNECT MISS" in window.log.toPlainText()
    window.quick_connect.clear()
    window.run_quick_connect()

    workflows: list[tuple[str, object, object]] = []
    monkeypatch.setattr(
        window,
        "show_workflow_dialog",
        lambda title, _subtitle, rows, detail, **_kwargs: workflows.append(
            (title, rows, detail)
        ),
    )
    window.show_moba_servers_status()
    assert window.property("mobaEmbeddedServerGuiConfigSchema")

    monkeypatch.setattr(window, "selected_profile_for_workflow", lambda: None)
    window.show_moba_smartcards_status()
    assert window.property("mobaSmartcardGuiCertificateCount") == 0

    smartcard = Profile(
        name="smartcard-edge",
        protocol="ssh",
        host="card.example.invalid",
        username="operator",
        options={
            "smartcard_certificate_id": "cert-1",
            "smartcard_certificate_label": "Operator Card",
            "smartcard_provider": "windows-capi",
            "smartcard_public_key": "ssh-rsa AAAA operator-card",
            "smartcard_fingerprint_sha256": "b" * 64,
            "add_smartcard_to_mobagent": "true",
        },
    )
    monkeypatch.setattr(
        window,
        "selected_profile_for_workflow",
        lambda: smartcard,
    )
    window.show_moba_smartcards_status()
    assert window.property("mobaSmartcardGuiCertificateCount") == 1
    assert window.property("mobaSmartcardGuiProvider") == "microsoft-capi"

    window.store.profiles = []
    window.show_moba_multiexec_status()
    window.store.profiles = [
        Profile(
            name=f"ssh-{index}",
            protocol="ssh",
            host=f"ssh-{index}.example.invalid",
        )
        for index in range(5)
    ]
    window.show_moba_multiexec_status()
    assert {title for title, _rows, _detail in workflows} >= {
        "Servers",
        "Smart cards",
        "MultiExec",
    }


def test_tab_context_securecrt_product_host_and_toolbar_edges(
    gui_window,
    monkeypatch,
) -> None:
    from PyQt6.QtCore import QPoint, Qt
    from PyQt6.QtWidgets import QFrame, QLineEdit, QMenu, QTreeWidgetItem

    from remote_ops_workspace.gui_designs import (
        gui_design_preset_reference_session_action_route,
        gui_design_securecrt_command_window_send_route,
    )

    app, window = gui_window
    assert window.build_tab_context_menu(-1) is None
    plain_menu = window.build_tab_context_menu(window.find_tab_by_role("home"))
    assert isinstance(plain_menu, QMenu)
    assert plain_menu.objectName() == "sessionTabContextMenu"

    route = gui_design_preset_reference_session_action_route("securecrt")
    monkeypatch.setattr(window, "current_design_id", lambda: "securecrt")
    monkeypatch.setattr(window, "current_design_is_moba", lambda: False)
    reference = QFrame()
    reference_index = window.add_workspace_tab(
        reference,
        route.active_tab_label,
        role=route.reference_tab_role,
    )
    route_menu = window.build_tab_context_menu(reference_index)
    assert route_menu.property(route.captured_property) is True
    assert route_menu.property(route.captured_action_count_property) >= 7
    assert route_menu.objectName() == "presetReferenceSessionTabContextMenu"

    captured: list[object] = []

    class _Menu:
        def exec(self, position) -> None:
            captured.append(position)

        def deleteLater(self) -> None:
            captured.append("deleted")

    monkeypatch.setattr(window, "build_tab_context_menu", lambda _index: _Menu())
    window.show_tab_context_menu(QPoint(-20, -20))
    tab_position = window.moba_tab_bar.tabRect(reference_index).center()
    window.show_tab_context_menu(tab_position)
    assert captured[-1] == "deleted"

    panel = window.build_securecrt_command_window_evidence()
    window.securecrt_command_input.clear()
    window.handle_securecrt_command_window_send()
    send_route = gui_design_securecrt_command_window_send_route()
    assert panel.property(send_route.captured_property) is True
    assert window.securecrt_command_status.text() == "sent"
    assert window.securecrt_command_input.text()

    window.securecrt_command_window = None
    window.securecrt_command_target = None
    window.securecrt_command_input = None
    window.securecrt_command_send = None
    window.securecrt_command_status = None
    window.handle_securecrt_command_window_send()

    profile = Profile(
        name="product-edge",
        protocol="ssh",
        host="product.example.invalid",
    )
    visible = QTreeWidgetItem(["Product edge product.example.invalid"])
    visible.setData(0, Qt.ItemDataRole.UserRole, profile.name)
    hidden = QTreeWidgetItem(["Hidden edge"])
    hidden.setData(0, Qt.ItemDataRole.UserRole, "hidden")
    hidden.setHidden(True)
    monkeypatch.setattr(
        window,
        "iter_profile_tree_items",
        lambda: iter([hidden, visible]),
    )
    monkeypatch.setattr(
        window,
        "profile_by_name",
        lambda name: profile if name == profile.name else None,
    )
    connect_calls: list[bool] = []
    monkeypatch.setattr(window, "connect_selected", connect_calls.append)
    window.connect_from_product_host("")
    window.connect_from_product_host("product.example")
    window.connect_from_product_host("missing-host")
    assert connect_calls == [False, False]
    assert "PRODUCT HOST MISS" in window.log.toPlainText()

    window.securecrt_host_input = QLineEdit("host")
    window.securecrt_keyword_input = QLineEdit("keyword")
    window.focus_securecrt_host()
    assert window.securecrt_host_input.selectedText() == "host"
    window.focus_securecrt_keyword()
    assert window.securecrt_keyword_input.selectedText() == "keyword"
    searches: list[str] = []
    monkeypatch.setattr(window, "find_log_text", lambda: searches.append("find"))
    window.find_product_keyword("  needle  ")
    assert window.search_input.text() == "needle"
    assert searches == ["find"]

    for product_id in ("securecrt", "mremoteng", "termius"):
        monkeypatch.setattr(
            window,
            "current_design_id",
            lambda value=product_id: value,
        )
        for widget in (window.layout_label, window.layout_select, window.view_label):
            window.set_toolbar_widget_visible(widget, True)
        for button in window.layout_toolbar_buttons:
            window.set_toolbar_widget_visible(button, True)
        window.set_toolbar_widget_visible(window.design_select, False)
        window.set_toolbar_widget_visible(window.search_input, False)
        window.set_toolbar_widget_visible(window.find_button, False)
        window.resize(1000, 720)
        app.processEvents()
        window.configure_responsive_layout_toolbar()
        assert all(
            button.toolButtonStyle() == Qt.ToolButtonStyle.ToolButtonIconOnly
            for button in window.main_toolbar_buttons
        )
        assert all(
            not widget.isVisibleTo(window)
            for widget in (
                window.layout_label,
                window.layout_select,
                window.view_label,
                *window.layout_toolbar_buttons,
            )
        )
        assert all(
            widget.isVisibleTo(window)
            for widget in (window.design_select, window.search_input, window.find_button)
        )
        assert window.search_input.minimumWidth() == 138
        assert window.search_input.maximumWidth() == 210

    monkeypatch.setattr(window, "current_design_id", lambda: "native")
    monkeypatch.setattr(window, "current_design_is_moba", lambda: False)
    for width in (1000, 1900):
        window.resize(width, 720)
        window.main_toolbar.resize(width, window.main_toolbar.height())
        app.processEvents()
        window.configure_responsive_layout_toolbar()
    monkeypatch.setattr(window, "current_design_is_moba", lambda: True)
    window.configure_responsive_layout_toolbar()


def test_style_selector_stays_in_shared_toolbar_for_every_preset(gui_window) -> None:
    app, window = gui_window

    for preset_id in ("native", "mobaxterm", "remmina", "mremoteng"):
        window.set_design_preset(preset_id)
        app.processEvents()
        assert window.layout_toolbar.isVisible() is True
        assert window.design_select.isVisibleTo(window) is True
        assert window.design_select.parentWidget() is window.layout_toolbar
        assert window.layout_toolbar.property("styleSelectorPersistent") is True
        assert window.design_select.property("styleSelectorLocation") == "layout-toolbar"
        assert window.property("designTransitionActive") is False

    window.set_design_preset("mobaxterm")
    app.processEvents()
    assert all(not button.isVisibleTo(window) for button in window.layout_toolbar_buttons)
    assert window.view_label.isVisibleTo(window) is True


def test_design_transition_depth_and_empty_workspace_are_safe(gui_window) -> None:
    _app, window = gui_window

    window.finish_design_transition()
    window.begin_design_transition()
    window.begin_design_transition()
    assert window._design_transition_depth == 2
    window.finish_design_transition()
    assert window._design_transition_depth == 1

    window.tabs.clear()
    window.finish_design_transition()
    assert window._design_transition_depth == 0
    assert window.tabs.currentWidget() is None
    assert window.property("designTransitionActive") is False


def test_launch_files_find_and_recover_session_edges(gui_window, monkeypatch) -> None:
    from PyQt6.QtWidgets import QMessageBox, QTextEdit

    from remote_ops_workspace import gui

    _app, window = gui_window
    messages: list[str] = []

    def fake_message_box(_parent, _icon, _title, text, **_kwargs):
        messages.append(str(text))
        return QMessageBox.StandardButton.Ok

    _set_closure_value(
        monkeypatch,
        type(window).connect_selected,
        "_literal_message_box",
        fake_message_box,
    )

    custom = Profile(
        name="custom-edge",
        protocol="custom",
        command="echo ready",
    )
    ssh = Profile(
        name="ssh-edge",
        protocol="ssh",
        host="ssh-edge.example.invalid",
        username="operator",
    )

    class _Store:
        value: object = custom

        def get(self, name: str):
            if isinstance(self.value, Exception):
                raise self.value
            if name not in {custom.name, ssh.name}:
                raise KeyError(name)
            return self.value

    store = _Store()
    window.store = store
    selected_name: list[str | None] = [None]
    monkeypatch.setattr(window, "selected_profile_name", lambda: selected_name[0])
    window.connect_selected(False)
    selected_name[0] = "missing"
    store.value = KeyError("missing")
    window.connect_selected(False)
    assert messages

    launched_from_selection: list[tuple[str, bool]] = []
    original_launch = window.launch_profile
    monkeypatch.setattr(
        window,
        "launch_profile",
        lambda profile, **kwargs: launched_from_selection.append(
            (profile.name, bool(kwargs["dry_run"]))
        ),
    )
    selected_name[0] = custom.name
    store.value = custom
    window.connect_selected(True)
    assert launched_from_selection == [(custom.name, True)]
    monkeypatch.setattr(window, "launch_profile", original_launch)

    terminal_opens: list[tuple[str, str | None]] = []
    connected_opens: list[str] = []
    monkeypatch.setattr(
        window,
        "open_terminal_tab",
        lambda plan, **kwargs: terminal_opens.append(
            (plan.source, kwargs.get("tab_title"))
        ),
    )
    monkeypatch.setattr(
        window,
        "open_moba_connected_session_tab",
        lambda profile, *_args, **_kwargs: connected_opens.append(profile.name),
    )
    monkeypatch.setattr(
        window,
        "moba_connected_profile_supported",
        lambda _profile: False,
    )
    window.launch_profile(custom, dry_run=True, prefix="DRY RUN")
    window.launch_profile(custom, dry_run=False, prefix="LAUNCHED")
    monkeypatch.setattr(
        window,
        "moba_connected_profile_supported",
        lambda _profile: True,
    )
    window.launch_profile(ssh, dry_run=False, prefix="LAUNCHED")
    assert terminal_opens
    assert connected_opens == [ssh.name]

    selected_name[0] = None
    window.open_files_selected()
    selected_name[0] = ssh.name
    store.value = ssh
    window.open_files_selected()
    monkeypatch.setattr(
        window,
        "moba_connected_profile_supported",
        lambda _profile: False,
    )
    window.open_files_selected()
    store.value = ValueError("blocked profile")
    window.open_files_selected()
    assert len(connected_opens) == 2
    assert len(terminal_opens) >= 2
    assert any("blocked profile" in message for message in messages)

    window.search_input.clear()
    window.find_log_text()
    terminal_text = QTextEdit()
    terminal_text.setPlainText("alpha terminal needle omega")
    pane = SimpleNamespace(output=terminal_text)
    monkeypatch.setattr(window, "active_terminal_pane", lambda: pane)
    window.search_input.setText("needle")
    window.find_log_text()
    assert "active terminal" in window.statusBar().currentMessage()

    monkeypatch.setattr(window, "active_terminal_pane", lambda: None)
    window.log.append("activity-only-value")
    window.search_input.setText("activity-only-value")
    window.find_log_text()
    assert "activity log" in window.statusBar().currentMessage()
    window.search_input.setText("absent-value")
    window.find_log_text()
    assert window.statusBar().currentMessage() == "Not found: absent-value"
    window.search_input.clear()
    window.focus_find_control()
    assert "Type search text" in window.statusBar().currentMessage()
    window.search_input.setText("activity-only-value")
    window.focus_find_control()

    window.recent_terminal_plans = []
    window.recover_previous_sessions()
    assert "No previous session" in window.statusBar().currentMessage()
    recovered_terminal: list[tuple[str, str | None]] = []
    recovered_moba: list[str] = []
    monkeypatch.setattr(
        window,
        "open_terminal_tab",
        lambda plan, **kwargs: recovered_terminal.append(
            (plan.title, kwargs.get("tab_title"))
        ),
    )
    monkeypatch.setattr(
        window,
        "open_moba_connected_session_tab",
        lambda profile, *_args, **_kwargs: recovered_moba.append(profile.name),
    )
    monkeypatch.setattr(window, "current_design_is_moba", lambda: False)
    window.recent_terminal_plans = [
        (
            TerminalPanePlan(
                title="profile-plan",
                command=["echo", "profile"],
                source=f"profile:{custom.name}",
            ),
            custom,
        ),
        (
            TerminalPanePlan(
                title="tool-plan",
                command=["echo", "tool"],
                source="tool",
            ),
            custom,
        ),
        (
            TerminalPanePlan(
                title="plain-plan",
                command=["echo", "plain"],
                source="tool",
            ),
            None,
        ),
    ]
    window.recover_previous_sessions()
    assert len(recovered_terminal) == 3

    monkeypatch.setattr(window, "current_design_is_moba", lambda: True)
    monkeypatch.setattr(
        window,
        "moba_connected_profile_supported",
        lambda _profile: True,
    )
    window.recent_terminal_plans = [
        (
            TerminalPanePlan(
                title="moba-plan",
                command=["ssh", ssh.host],
                source=f"profile:{ssh.name}",
            ),
            ssh,
        )
    ]
    window.recover_previous_sessions()
    assert recovered_moba == [ssh.name]
    assert "RECOVERED" in window.log.toPlainText()
    monkeypatch.setattr(gui, "run_doctor", lambda: SimpleNamespace(to_json=lambda: "{}"))
    window.show_doctor()
    assert window.log.toPlainText().endswith("{}")


def test_profile_context_menu_activation_and_visibility_edges(
    gui_window,
    monkeypatch,
) -> None:
    from PyQt6.QtCore import QPoint, Qt
    from PyQt6.QtWidgets import QTreeWidgetItem

    _app, window = gui_window
    parent = QTreeWidgetItem(["group"])
    profile_item = QTreeWidgetItem(["profile"])
    parent.addChild(profile_item)
    window.profile_list.addTopLevelItem(parent)

    class _Menu:
        def __init__(self) -> None:
            self.executed = []
            self.deleted = False

        def exec(self, position) -> None:
            self.executed.append(position)

        def deleteLater(self) -> None:  # noqa: N802
            self.deleted = True

    menu = _Menu()
    monkeypatch.setattr(
        window.profile_list,
        "itemAt",
        lambda _position: profile_item,
    )
    monkeypatch.setattr(
        window,
        "build_profile_context_menu",
        lambda selected: menu,
    )
    window.show_profile_context_menu(QPoint(3, 4))
    assert window.profile_list.currentItem() is profile_item
    assert len(menu.executed) == 1
    assert menu.deleted is True

    connects: list[bool] = []
    monkeypatch.setattr(window, "connect_selected", connects.append)
    window.activate_profile_item(profile_item)
    assert connects == []
    profile_item.setData(0, Qt.ItemDataRole.UserRole, "profile-edge")
    window.activate_profile_item(profile_item)
    assert connects == [False]

    assert window.profile_tree_item_is_visible(profile_item) is True
    parent.setHidden(True)
    assert window.profile_tree_item_is_visible(profile_item) is False


def test_registered_action_dispatch_success_and_missing_edges(
    gui_window,
) -> None:
    _app, window = gui_window
    calls: list[str] = []
    window.product_menu_callbacks["controlled-family"] = {
        "controlled": lambda: calls.append("menu")
    }
    window.product_toolbar_callbacks["controlled"] = lambda: calls.append("product")
    window.layout_toolbar_callbacks["controlled"] = lambda: calls.append("layout")
    window.moba_ribbon_callbacks["controlled"] = lambda: calls.append("ribbon")
    window.home_action_callbacks["controlled"] = lambda: calls.append("home")

    window.run_product_menu_action("controlled-family", "controlled")
    window.run_product_toolbar_action("controlled")
    window.run_layout_toolbar_action("controlled")
    window.run_moba_ribbon_action("controlled")
    window.run_home_action("controlled")
    assert calls == ["menu", "product", "layout", "ribbon", "home"]

    with pytest.raises(RuntimeError, match="missing missing-family menu callback"):
        window.run_product_menu_action("missing-family", "missing")
    with pytest.raises(RuntimeError, match="missing controlled-family menu callback"):
        window.run_product_menu_action("controlled-family", "missing")
    with pytest.raises(RuntimeError, match="missing product toolbar callback"):
        window.run_product_toolbar_action("missing")
    with pytest.raises(RuntimeError, match="missing layout toolbar callback"):
        window.run_layout_toolbar_action("missing")
    with pytest.raises(RuntimeError, match="missing Moba ribbon callback"):
        window.run_moba_ribbon_action("missing")
    with pytest.raises(RuntimeError, match="missing home action callback"):
        window.run_home_action("missing")


def test_welcome_resize_guards_and_toolbar_action_contracts(
    gui_window,
    monkeypatch,
) -> None:
    from remote_ops_workspace import gui
    from remote_ops_workspace.gui_designs import get_gui_design_preset

    _app, window = gui_window
    original_scroll = window.welcome_scroll
    original_panel = window.welcome_panel

    window.welcome_scroll = None
    window.configure_welcome_responsiveness()

    window.welcome_scroll = SimpleNamespace(widget=lambda: SimpleNamespace(layout=lambda: None))
    window.configure_welcome_responsiveness()

    margins = SimpleNamespace(left=lambda: 0, right=lambda: 0)
    layout = SimpleNamespace(contentsMargins=lambda: margins)
    content = SimpleNamespace(layout=lambda: layout)
    viewport = SimpleNamespace(width=lambda: 8)
    window.welcome_scroll = SimpleNamespace(
        widget=lambda: content,
        viewport=lambda: viewport,
    )
    window.configure_welcome_responsiveness()
    window.welcome_scroll = original_scroll
    window.welcome_panel = original_panel

    preset = get_gui_design_preset("mobaxterm")
    monkeypatch.setattr(
        gui,
        "gui_design_toolbar_actions",
        lambda _preset_id: [
            ("refresh", "Refresh", "Refresh"),
            ("refresh", "Again", "Duplicate"),
        ],
    )
    with pytest.raises(RuntimeError, match="duplicate toolbar action keys"):
        window.configure_toolbar_copy_for_design(preset)

    monkeypatch.setattr(
        gui,
        "gui_design_toolbar_actions",
        lambda _preset_id: [("unexpected", "Unexpected", "Unexpected")],
    )
    with pytest.raises(RuntimeError, match="toolbar action contract mismatch"):
        window.configure_toolbar_copy_for_design(preset)


def test_moba_workspace_tabs_resize_with_mouse_and_prepare_keyboard_switch(
    gui_window,
) -> None:
    from PyQt6.QtCore import QEvent, QPoint, Qt
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QWidget

    app, window = gui_window
    window.set_design_preset("mobaxterm")
    page = QWidget(window.tabs)
    index = window.add_workspace_tab(page, "Resizable edge", role="tool")
    bar = window.tabs.tabBar()
    bar.setProperty("mobaCompactTabWidths", True)
    data = bar.tabData(index)
    data = dict(data) if isinstance(data, dict) else {}
    data.update(moba_key="session", moba_width=220, moba_height=28)
    bar.setTabData(index, data)
    bar._refresh_tab_layout(index)
    app.processEvents()

    rect = bar.tabRect(index)
    assert bar._tab_resize_target(QPoint(rect.right(), rect.center().y())) == (
        index,
        "right",
    )
    QTest.mousePress(
        bar,
        Qt.MouseButton.LeftButton,
        pos=QPoint(rect.right(), rect.center().y()),
    )
    QTest.mouseMove(bar, QPoint(rect.right() + 45, rect.center().y()))
    QTest.mouseRelease(
        bar,
        Qt.MouseButton.LeftButton,
        pos=QPoint(rect.right() + 45, rect.center().y()),
    )
    assert bar.property("mobaLastResizedTabIndex") == index
    assert int(bar.tabData(index)["moba_width"]) > 220

    prepared: list[int] = []
    bar.tab_switch_prepare_handler = prepared.append
    QTest.keyClick(bar, Qt.Key.Key_Left)
    assert prepared == [-1]

    bar._tab_resize_index = -1
    bar._resize_tab_width(10)
    bar._tab_resize_index = index
    bar._tab_resize_start_x = 10
    bar._tab_resize_start_width = 200
    bar.setTabData(index, "invalid")
    bar._resize_tab_width(30)

    bar._pressed_special_key = "new-session"
    move = QMouseEvent(
        QEvent.Type.MouseMove,
        rect.center().toPointF(),
        rect.center().toPointF(),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    bar.mouseMoveEvent(move)
    assert move.isAccepted() is True

    standalone = type(bar)()
    standalone.addTab("Detached")
    standalone._refresh_tab_layout(0)
    standalone.deleteLater()


def test_moba_workspace_tab_bar_special_resize_and_hint_contracts(gui_window) -> None:
    from PyQt6.QtCore import QEvent, QPoint, Qt
    from PyQt6.QtGui import QMouseEvent
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QWidget

    app, window = gui_window
    window.set_design_preset("mobaxterm")
    bar_type = type(window.tabs.tabBar())
    bar = bar_type()
    bar.resize(760, 42)
    session_index = bar.addTab("Session")
    new_index = bar.addTab("+")
    home_index = bar.addTab("Home")
    bar.setTabData(session_index, {"moba_key": "session", "moba_width": 220, "moba_height": 30})
    bar.setTabData(new_index, {"moba_key": "new-session", "moba_width": 42, "moba_height": 30})
    bar.setTabData(home_index, {"moba_key": "home", "moba_width": 70, "moba_height": 30})
    bar.show()
    app.processEvents()

    bar._stabilizing_special_tabs = True
    bar.stabilize_special_tabs()
    bar._stabilizing_special_tabs = False
    bar.stabilize_special_tabs()
    assert bar.moba_tab_key(0) == "home"
    assert bar.moba_tab_key(bar.count() - 1) == "new-session"
    session_index = next(
        index for index in range(bar.count()) if bar.moba_tab_key(index) == "session"
    )
    new_index = next(
        index for index in range(bar.count()) if bar.moba_tab_key(index) == "new-session"
    )

    assert bar.activate_special_tab(0) is False
    assert bar.activate_special_tab(new_index) is False
    activated: list[int] = []
    bar.special_tab_handler = activated.append
    assert bar.activate_special_tab(new_index) is True
    assert activated == [new_index]

    bar.setProperty("mobaCompactTabWidths", False)
    assert bar._tab_resize_target(QPoint(0, 0)) is None
    bar.setProperty("mobaCompactTabWidths", True)
    bar._refresh_tab_layout(session_index)
    app.processEvents()
    rect = bar.tabRect(session_index)
    assert bar._tab_resize_target(QPoint(-100, -100)) is None
    assert bar._tab_resize_target(QPoint(rect.left(), rect.center().y())) == (
        session_index,
        "left",
    )

    hover = QMouseEvent(
        QEvent.Type.MouseMove,
        QPoint(rect.left(), rect.center().y()).toPointF(),
        QPoint(rect.left(), rect.center().y()).toPointF(),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    bar.mouseMoveEvent(hover)
    assert bar.cursor().shape() == Qt.CursorShape.SizeHorCursor
    away = QMouseEvent(
        QEvent.Type.MouseMove,
        rect.center().toPointF(),
        rect.center().toPointF(),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    bar.mouseMoveEvent(away)

    QTest.mousePress(
        bar,
        Qt.MouseButton.LeftButton,
        pos=QPoint(rect.left(), rect.center().y()),
    )
    QTest.mouseMove(bar, QPoint(rect.left() - 900, rect.center().y()))
    QTest.mouseRelease(
        bar,
        Qt.MouseButton.LeftButton,
        pos=QPoint(rect.left() - 900, rect.center().y()),
    )
    assert bar.tabData(session_index)["moba_width"] == bar.TAB_RESIZE_MAX_WIDTH

    bar._tab_resize_index = session_index
    bar._tab_resize_edge = "left"
    bar._tab_resize_start_x = 0
    bar._tab_resize_start_width = 200
    bar._resize_tab_width(900)
    assert bar.tabData(session_index)["moba_width"] == bar.TAB_RESIZE_MIN_WIDTH
    bar._resize_tab_width(900)
    bar._tab_resize_index = bar.count()
    bar._resize_tab_width(0)

    special_rect = bar.tabRect(new_index)
    QTest.mousePress(
        bar,
        Qt.MouseButton.LeftButton,
        pos=special_rect.center(),
    )
    QTest.mouseRelease(
        bar,
        Qt.MouseButton.LeftButton,
        pos=special_rect.center(),
    )
    assert activated[-1] == new_index

    bar._pressed_special_key = "home"
    move = QMouseEvent(
        QEvent.Type.MouseMove,
        rect.center().toPointF(),
        rect.center().toPointF(),
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    bar.mouseMoveEvent(move)
    assert move.isAccepted() is True

    leave = QEvent(QEvent.Type.Leave)
    bar._tab_resize_index = -1
    bar.leaveEvent(leave)
    bar._tab_resize_index = session_index
    bar.leaveEvent(QEvent(QEvent.Type.Leave))
    bar._tab_resize_index = -1

    bar.setProperty("mobaCompactTabWidths", False)
    default_hint = bar.tabSizeHint(session_index)
    bar.setProperty("mobaCompactTabWidths", True)
    bar.setTabData(session_index, "invalid")
    assert bar.tabSizeHint(session_index) == default_hint
    bar.setTabData(session_index, {"moba_key": "session", "moba_width": 0})
    assert bar.tabSizeHint(session_index) == default_hint
    bar.setTabData(
        session_index,
        {"moba_key": "session", "moba_width": 222, "moba_height": 33},
    )
    assert bar.tabSizeHint(session_index).width() == 222
    assert bar.tabSizeHint(session_index).height() == 33
    bar.setTabData(
        session_index,
        {"moba_key": "session", "moba_width": 222, "moba_height": 0},
    )
    assert bar.tabSizeHint(session_index).height() == default_hint.height()

    parent = QWidget()
    child_bar = bar_type(parent)
    child_bar.addTab("No layout")
    child_bar._refresh_tab_layout(0)
    child_bar.deleteLater()
    parent.deleteLater()

    from PyQt6.QtWidgets import QVBoxLayout

    layout_parent = QWidget()
    layout = QVBoxLayout(layout_parent)
    layout_bar = bar_type()
    layout.addWidget(layout_bar)
    layout_bar.addTab("Layout-backed")
    layout_bar._refresh_tab_layout(0)
    layout_bar.deleteLater()
    layout_parent.deleteLater()

    special_release = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        special_rect.center().toPointF(),
        special_rect.center().toPointF(),
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    bar._pressed_special_key = "new-session"
    bar.mouseReleaseEvent(special_release)
    assert special_release.isAccepted() is True

    tabs_type = type(window.tabs)
    tabs = tabs_type()
    first = QWidget()
    second = QWidget()
    tabs.addTab(first, "First")
    tabs.addTab(second, "Second")
    prepared: list[int] = []
    tabs.tab_switch_prepare_handler = prepared.append
    tabs.setCurrentIndex(tabs.currentIndex())
    tabs.setCurrentIndex(1)
    tabs.setCurrentWidget(None)
    tabs.setCurrentWidget(first)
    assert 1 in prepared
    assert 0 in prepared
    tabs.deleteLater()
    bar.deleteLater()


def test_product_menu_signals_status_workflows_and_design_fallback(
    gui_window,
    monkeypatch,
) -> None:
    from PyQt6.QtWidgets import QWidget

    app, window = gui_window
    menu_calls: list[tuple[str, str]] = []
    monkeypatch.setattr(
        window,
        "run_product_menu_action",
        lambda family, key: menu_calls.append((family, key)),
    )
    for family, menus in (
        ("mobaxterm", window.moba_top_menus),
        ("securecrt", window.securecrt_top_menus),
        ("mremoteng", window.mremoteng_top_menus),
    ):
        action = next(
            action
            for menu in menus
            for action in menu.actions()
            if action.property("menuActionFamily") == family
        )
        action.trigger()
    assert [family for family, _key in menu_calls] == [
        "mobaxterm",
        "securecrt",
        "mremoteng",
    ]

    workflows: list[tuple[str, object, str]] = []
    monkeypatch.setattr(
        window,
        "show_workflow_dialog",
        lambda title, _subtitle, rows, detail, **_kwargs: workflows.append(
            (title, rows, detail)
        ),
    )
    monkeypatch.setattr(window.store, "load", lambda: [])
    monkeypatch.setattr(window.layout_store, "load", lambda: [])
    monkeypatch.setattr(window, "selected_profile_for_workflow", lambda: None)
    window.show_moba_session_attachment()
    window.show_moba_session_settings()
    window.show_moba_games_status()
    window.show_moba_settings_status()
    window.show_securecrt_script_status()
    window.show_key_manager_status()
    window.show_external_tools_status()
    window.show_moba_tools_status()
    window.show_moba_x_server_status()
    window.show_moba_macros_status()
    window.show_moba_help_dialog()

    configured = Profile(
        name="configured-status-edge",
        protocol="ssh",
        host="status.example.invalid",
        identity_file="C:/keys/operator-ed25519",
        credential_ref="vault://operator/status",
        options={"x11": "trusted"},
    )
    monkeypatch.setattr(window.store, "load", lambda: [configured])
    monkeypatch.setattr(
        window,
        "selected_profile_for_workflow",
        lambda: configured,
    )
    window.show_securecrt_script_status()
    window.show_key_manager_status()
    window.show_moba_x_server_status()
    titles = [title for title, _rows, _detail in workflows]
    assert {
        "Session attachment",
        "Session settings",
        "Games",
        "Settings",
        "Run Script",
        "Key Manager",
        "External Tools",
        "Tools",
        "X server",
        "Macros",
        "Help",
    }.issubset(titles)

    window.design_select.addItem("Invalid design", "removed-design-plugin")
    invalid_index = window.design_select.findData("removed-design-plugin")
    signals_were_blocked = window.design_select.blockSignals(True)
    window.design_select.setCurrentIndex(invalid_index)
    window.design_select.blockSignals(signals_were_blocked)
    window.apply_selected_design()
    app.processEvents()
    assert window.current_design_id() == "native"
    assert window.statusBar().currentMessage() == "View: Native"

    tool = QWidget()
    window.add_workspace_tab(tool, "Recovery tool", role="tool")
    home_index = window.find_tab_by_role("home")
    home = window.tabs.widget(home_index)
    window.tabs.removeTab(home_index)
    assert home is not None
    home.deleteLater()
    window.configure_workspace_tabs_for_design(False)
    assert window.find_tab_by_role("home") == -1

    moba_index = window.design_select.findData("mobaxterm")
    signals_were_blocked = window.design_select.blockSignals(True)
    window.design_select.setCurrentIndex(moba_index)
    window.design_select.blockSignals(signals_were_blocked)
    window.moba_tab_guard = True
    window.configure_workspace_tabs_for_design(True)
    assert window.moba_tab_guard is True
    assert window.find_tab_by_role("home") >= 0
    assert window.find_tab_by_role("new-session") >= 0


def test_navigation_dialog_search_and_connected_chrome_edges(
    gui_window,
    monkeypatch,
) -> None:
    from dataclasses import replace

    from PyQt6.QtCore import QPoint, Qt
    from PyQt6.QtWidgets import QLineEdit, QTabWidget, QTreeWidgetItem

    from remote_ops_workspace.gui_designs import (
        gui_design_preset_focus_interaction_route,
        gui_design_preset_home_search_route,
        gui_design_preset_reference_tab_route,
    )

    _app, window = gui_window

    class _Menu:
        def __init__(self) -> None:
            self.positions = []
            self.deleted = False

        def exec(self, position) -> None:
            self.positions.append(position)

        def deleteLater(self) -> None:  # noqa: N802
            self.deleted = True

    menu = _Menu()
    source = SimpleNamespace(mapToGlobal=lambda position: position + QPoint(4, 5))
    monkeypatch.setattr(window, "build_moba_rail_context_menu", lambda: menu)
    window.show_moba_rail_context_menu(source, QPoint(1, 2))
    assert menu.positions == [QPoint(5, 7)]
    assert menu.deleted is True

    executions: list[str] = []
    fake_dialog = SimpleNamespace(exec=lambda: executions.append("exec"))
    monkeypatch.setattr(window, "create_workflow_dialog", lambda *_args, **_kwargs: fake_dialog)
    type(window).show_workflow_dialog(
        window,
        "Controlled workflow",
        "subtitle",
        [("row", "ready", "detail")],
        "body",
    )
    assert executions == ["exec"]
    assert window.statusBar().currentMessage() == "Workflow: Controlled workflow"

    assert window.tab_position_for_design("south") == QTabWidget.TabPosition.South
    assert window.tab_position_for_design("east") == QTabWidget.TabPosition.East

    launched = []
    monkeypatch.setattr(window, "run_quick_connect_candidate_value", launched.append)
    window.quick_connect.setText("ssh operator@fallback.example.invalid:2222")
    window.quick_connect_suggestions.clear()
    invalid = QTreeWidgetItem(["invalid"])
    invalid.setData(0, Qt.ItemDataRole.UserRole, "invalid-candidate")
    window.quick_connect_suggestions.addTopLevelItem(invalid)
    window.quick_connect_suggestions.setCurrentItem(invalid)
    window.run_quick_connect()
    assert launched and launched[0].kind == "direct"

    route = gui_design_preset_home_search_route("securecrt")
    duplicate_search = QLineEdit(window)
    duplicate_search.setObjectName("duplicateHomeSearchEdge")
    duplicate_route = replace(
        route,
        container_object="missingHomeContainerEdge",
        home_search_object="duplicateHomeSearchEdge",
        entry_search_object="duplicateHomeSearchEdge",
    )
    widgets = window.home_search_route_widgets(duplicate_route)
    assert widgets.count(duplicate_search) == 1

    focus_route = gui_design_preset_focus_interaction_route("securecrt")
    window.statusBar().clearMessage()
    window.apply_focus_interaction_route_for_design(focus_route, "securecrt")
    assert window.property(focus_route.captured_status_message_property) == (
        f"securecrt: {focus_route.status_note}"
    )

    class _Visible:
        def __init__(self) -> None:
            self.values: list[bool] = []

        def setVisible(self, visible: bool) -> None:  # noqa: N802
            self.values.append(visible)

    class _Workspace:
        def __init__(self) -> None:
            self.sizes: list[list[int]] = []

        def setSizes(self, sizes: list[int]) -> None:  # noqa: N802
            self.sizes.append(list(sizes))

    class _Tabs:
        def __init__(self, *, index: int, text: str) -> None:
            self.index = index
            self.text = text

        def currentIndex(self) -> int:  # noqa: N802
            return self.index

        def tabText(self, _index: int) -> str:  # noqa: N802
            return self.text

        @staticmethod
        def tabBar():  # noqa: N802
            return None

    termius_route = gui_design_preset_reference_tab_route("termius")
    properties: dict[str, object] = {}
    sidebar_widths: list[tuple[int, bool]] = []
    connected_owner = SimpleNamespace(
        current_design_id=lambda: "termius",
        tabs=_Tabs(index=0, text=termius_route.active_tab_label),
        tab_role=lambda _index: termius_route.reference_tab_role,
        setProperty=lambda key, value: properties.__setitem__(key, value),
        left_panel=_Visible(),
        main_toolbar=_Visible(),
        layout_toolbar=_Visible(),
        log=_Visible(),
        set_root_sidebar_width=lambda width, collapsed=False: sidebar_widths.append(
            (width, collapsed)
        ),
        workspace=_Workspace(),
        height=lambda: 700,
        preferred_sidebar_width=lambda width: width,
    )
    configure_connected = type(window).configure_product_connected_chrome
    configure_connected(connected_owner)
    assert properties["termiusConnectedChromeActive"] is True
    assert sidebar_widths[-1] == (0, True)

    connected_owner.current_design_id = lambda: "removed-product-design"
    connected_owner.tabs = _Tabs(index=-1, text="")
    configure_connected(connected_owner)
    assert properties["termiusConnectedChromeActive"] is False
    assert sidebar_widths[-1] == (300, False)

    reference_owner = SimpleNamespace(
        current_design_id=lambda: "termius",
        tabs=SimpleNamespace(tabText=lambda _index: "Wrong title"),
        tab_role=lambda _index: termius_route.reference_tab_role,
    )
    reference_for_tab = type(window).reference_session_action_route_for_tab
    assert reference_for_tab(reference_owner, 0) is None
    reference_owner.tabs = SimpleNamespace(
        tabText=lambda _index: termius_route.active_tab_label
    )
    reference_owner.tab_role = lambda _index: "wrong-role"
    assert reference_for_tab(reference_owner, 0) is None

    added: list[bool] = []
    rebuild_owner = SimpleNamespace(
        find_tab_by_role=lambda _role: -1,
        add_welcome_tab=lambda *, select: added.append(select),
    )
    rebuild = type(window).rebuild_welcome_tab
    rebuild(rebuild_owner, select=True)
    assert added == [True]

    removed: list[int] = []
    rebuild_owner = SimpleNamespace(
        find_tab_by_role=lambda _role: 2,
        tabs=SimpleNamespace(
            widget=lambda _index: None,
            removeTab=removed.append,
        ),
        clear_deleted_tab_object_names=lambda _widget: None,
        add_welcome_tab=lambda *, select: added.append(select),
    )
    rebuild(rebuild_owner, select=False)
    assert removed == [2]
    assert added[-1] is False


def test_profile_filter_adjacent_tab_and_missing_dock_edges(
    gui_window,
    monkeypatch,
) -> None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QTreeWidgetItem, QWidget

    _app, window = gui_window
    root = QTreeWidgetItem(["Controlled group"])
    profile_item = QTreeWidgetItem(["Visible profile"])
    profile_item.setData(0, Qt.ItemDataRole.UserRole, "visible-profile")
    root.addChild(profile_item)
    window.profile_list.addTopLevelItem(root)
    root.setExpanded(True)
    window.profile_list.setCurrentItem(profile_item)
    window.filter_profile_tree("does-not-match")
    assert window.profile_list.currentItem() is None

    window.filter_profile_tree("")
    window.profile_list.setCurrentItem(profile_item)
    window.filter_profile_tree_names(set())
    assert window.profile_list.currentItem() is None

    selected: list[int] = []
    adjacent = type(window).activate_adjacent_tab
    adjacent_owner = SimpleNamespace(
        tabs=SimpleNamespace(count=lambda: 1, currentIndex=lambda: 0),
        tab_role=lambda _index: "session",
        set_workspace_tab_index=selected.append,
    )
    adjacent(adjacent_owner, 1)
    adjacent_owner.tabs = SimpleNamespace(count=lambda: 3, currentIndex=lambda: 0)
    adjacent_owner.tab_role = lambda _index: "home"
    adjacent(adjacent_owner, 1)
    assert selected == []
    adjacent_owner.tab_role = lambda index: "session" if index == 2 else "home"
    adjacent(adjacent_owner, 1)
    assert selected == [2]

    page = QWidget()
    tooltip_index = window.add_workspace_tab(page, "Tooltip fallback", role="tool")
    page.setProperty("tabTooltipPlainText", None)
    assert window.literal_tab_tooltip(tooltip_index) == "Tooltip fallback"
    assert window.literal_tab_tooltip(-1) == ""

    show_profile_tree = type(window).show_moba_profile_tree
    show_connected_dock = type(window).show_moba_connected_dock
    owner_without_stack = SimpleNamespace()
    show_profile_tree(owner_without_stack)
    show_connected_dock(owner_without_stack, object())

    quick_runs: list[str] = []
    monkeypatch.setattr(window, "run_quick_connect", lambda: quick_runs.append("run"))
    window.run_home_search("ssh operator@home.example.invalid")
    assert window.quick_connect.text() == "ssh operator@home.example.invalid"
    assert quick_runs == ["run"]


def test_toolbar_shortcut_profile_and_context_contract_edges(
    gui_window,
    monkeypatch,
) -> None:
    from PyQt6.QtWidgets import QWidget

    from remote_ops_workspace.gui_designs import gui_design_interaction_state

    _app, window = gui_window
    monkeypatch.setattr(
        window,
        "keyboard_shortcut_specs",
        lambda: [
            {
                "key": "invalid-callback",
                "sequence": "Ctrl+Alt+9",
                "action_label": "Invalid callback",
                "callback": "not-callable",
            }
        ],
    )
    with pytest.raises(RuntimeError, match="keyboard shortcut callback is unavailable"):
        window.create_keyboard_shortcuts()

    unregistered = QWidget()
    unregistered.setObjectName("unregisteredToolbarEdge")
    with pytest.raises(RuntimeError, match="toolbar widget is not registered"):
        window.set_toolbar_widget_visible(unregistered, True)
    with pytest.raises(RuntimeError, match="toolbar widget is not registered"):
        window.toolbar_widget_action(unregistered)

    apply_tab_status = type(window).apply_interaction_state_tab_status
    apply_tab_status(
        SimpleNamespace(tabs=SimpleNamespace(count=lambda: 0)),
        object(),
        object(),
    )
    state = gui_design_interaction_state("mobaxterm")
    assert window.toolbar_interaction_state(state.disabled_toolbar_key, state) == "disabled"

    type(window).clear_moba_quick_connect_connected_idle(SimpleNamespace())
    assert window.profile_group_parts("team\\production") == ["team", "production"]
    assert window.profile_icon_for_protocol("serial").isNull() is False

    layouts = [SimpleNamespace(name="alpha"), SimpleNamespace(name="beta")]
    monkeypatch.setattr(window.layout_store, "load", lambda: layouts)
    window.refresh_layouts()
    assert [window.layout_select.itemText(index) for index in range(2)] == [
        "alpha",
        "beta",
    ]

    geometry_owner = SimpleNamespace(findChild=lambda *_args: None)
    type(window).enforce_product_reference_filter_geometry(
        geometry_owner,
        "securecrt",
    )

    expected_profile = Profile(
        name="lookup-edge",
        protocol="ssh",
        host="lookup.example.invalid",
    )
    monkeypatch.setattr(window.store, "get", lambda _name: expected_profile)
    assert window.profile_by_name("lookup-edge") is expected_profile

    workflows: list[str] = []
    monkeypatch.setattr(
        window,
        "show_workflow_dialog",
        lambda title, *_args, **_kwargs: workflows.append(title),
    )
    window.show_moba_clipboard_hints()
    window.show_moba_terminal_settings()
    assert workflows == ["Clipboard and transfer hints", "Terminal settings"]

    default_page = QWidget()
    default_index = window.tabs.addTab(default_page, "Default role")
    assert window.tab_role(default_index) == "session"

    opened: list[str] = []
    special_owner = SimpleNamespace(
        moba_tab_guard=False,
        current_design_is_moba=lambda: True,
        open_local_terminal_tab=lambda: opened.append("terminal"),
    )
    type(window).activate_moba_special_tab(special_owner, 0)
    assert opened == ["terminal"]
    assert special_owner.moba_tab_guard is False

    session_index = window.add_workspace_tab(QWidget(), "Context edge", role="session")
    closed_others: list[int] = []
    monkeypatch.setattr(window, "close_other_tabs", closed_others.append)
    menu = window.build_tab_context_menu(session_index)
    assert menu is not None
    close_others = next(
        action
        for action in menu.actions()
        if action.property("sessionTabContextActionKey") == "close-other-tabs"
    )
    close_others.trigger()
    assert closed_others == [session_index]
    menu.deleteLater()

    window.filter_remmina_profile_rows("no matching remmina row")


def test_menu_bar_rejects_unregistered_product_items(gui_window, monkeypatch) -> None:
    from dataclasses import replace

    from remote_ops_workspace import gui
    from remote_ops_workspace.gui_designs import (
        gui_design_moba_top_menu_geometry_for,
        gui_design_moba_top_menu_items,
        gui_design_mremoteng_top_chrome,
        gui_design_securecrt_top_chrome,
    )

    _app, window = gui_window
    original_moba_items = gui_design_moba_top_menu_items
    original_moba_geometry = gui_design_moba_top_menu_geometry_for
    original_securecrt = gui_design_securecrt_top_chrome
    original_mremoteng = gui_design_mremoteng_top_chrome

    moba_item = original_moba_items()[0]
    moba_geometry = original_moba_geometry(moba_item.key)
    monkeypatch.setattr(
        gui,
        "gui_design_moba_top_menu_items",
        lambda: (replace(moba_item, key="unregistered-moba"),),
    )
    monkeypatch.setattr(
        gui,
        "gui_design_moba_top_menu_geometry_for",
        lambda _key: moba_geometry,
    )
    with pytest.raises(RuntimeError, match="missing Moba top-menu handler"):
        window.build_menu_bar()

    monkeypatch.setattr(gui, "gui_design_moba_top_menu_items", original_moba_items)
    monkeypatch.setattr(gui, "gui_design_moba_top_menu_geometry_for", original_moba_geometry)
    securecrt = original_securecrt()
    monkeypatch.setattr(
        gui,
        "gui_design_securecrt_top_chrome",
        lambda: replace(
            securecrt,
            menu_items=(replace(securecrt.menu_items[0], key="unregistered-securecrt"),),
        ),
    )
    with pytest.raises(RuntimeError, match="missing SecureCRT top-menu handler"):
        window.build_menu_bar()

    monkeypatch.setattr(gui, "gui_design_securecrt_top_chrome", original_securecrt)
    mremoteng = original_mremoteng()
    monkeypatch.setattr(
        gui,
        "gui_design_mremoteng_top_chrome",
        lambda: replace(
            mremoteng,
            menu_items=(replace(mremoteng.menu_items[0], key="unregistered-mremoteng"),),
        ),
    )
    with pytest.raises(RuntimeError, match="missing mRemoteNG top-menu handler"):
        window.build_menu_bar()


def test_remaining_operator_tab_and_reference_route_guards(
    gui_window,
    monkeypatch,
) -> None:
    from PyQt6.QtWidgets import QLineEdit, QWidget

    from remote_ops_workspace.moba_connected import (
        build_moba_connected_session_state,
    )

    _app, window = gui_window
    profile = Profile(
        name="nested-connected-edge",
        protocol="ssh",
        host="nested-connected.example.invalid",
        options={"remote_path": "/srv/operator"},
    )
    state = build_moba_connected_session_state(profile)
    parent = QWidget()
    child = QWidget(parent)
    child.moba_connected_state = state
    assert window.moba_connected_state_in_widget(parent) is state

    assert window.profile_by_name(None) is None
    monkeypatch.setattr(window, "selected_profile_name", lambda: profile.name)
    monkeypatch.setattr(window, "profile_by_name", lambda _name: profile)
    assert window.selected_profile_for_workflow() is profile
    assert window.tab_role(window.tabs.count() + 100) == ""

    opened: list[str] = []
    guarded_owner = SimpleNamespace(
        moba_tab_guard=True,
        current_design_is_moba=lambda: True,
        open_local_terminal_tab=lambda: opened.append("opened"),
    )
    type(window).activate_moba_special_tab(guarded_owner, 0)
    guarded_owner.moba_tab_guard = False
    guarded_owner.current_design_is_moba = lambda: False
    type(window).activate_moba_special_tab(guarded_owner, 0)
    assert opened == []

    window.apply_moba_tab_chrome(
        -1,
        key="missing",
        icon_key="plus",
        tooltip="Missing tab",
        closeable=False,
    )
    window.prepare_tab_transition(window.tabs.currentIndex())

    type(window).filter_remmina_profile_rows(SimpleNamespace(), "edge")
    active_owner = SimpleNamespace(tabs=SimpleNamespace(currentWidget=lambda: None))
    assert type(window).active_terminal_pane(active_owner) is None

    pane = QWidget()
    type(window).configure_product_reference_terminal_pane(pane, "native")
    original_current_design_id = window.current_design_id
    original_current_design_is_moba = window.current_design_is_moba
    monkeypatch.setattr(window, "current_design_id", lambda: "securecrt")
    window.apply_reference_tab_route_to_terminal_tab(pane, "wrong-title")
    window.apply_reference_tab_chrome_route_to_terminal_tab(
        pane,
        "wrong-title",
        -1,
    )
    window.apply_reference_status_bar_route_to_terminal_tab(pane, "wrong-title")
    window.apply_reference_session_action_route_to_terminal_tab(
        pane,
        "wrong-title",
        -1,
    )
    window.apply_moba_connected_session_action_route_to_tab(
        pane,
        state,
        "wrong-title",
        -1,
    )

    monkeypatch.setattr(window, "current_design_is_moba", lambda: True)
    assert window.moba_connected_profile_supported(profile) is True
    assert window.moba_connected_remote_path_for_profile(profile) == "/srv/operator"

    monkeypatch.setattr(window, "current_design_id", original_current_design_id)
    monkeypatch.setattr(
        window,
        "current_design_is_moba",
        original_current_design_is_moba,
    )

    design_index = window.design_select.findData("mremoteng")
    assert design_index >= 0
    window.design_select.setCurrentIndex(design_index)
    document_filter = window.findChild(QLineEdit, "mRemoteNgDocumentFilter")
    assert document_filter is not None
    document_filter.setText("nested")
    window.refresh_profiles()
    assert document_filter.text() == "nested"

    parent.deleteLater()
    pane.deleteLater()


def test_moba_welcome_tab_applies_non_closeable_home_chrome(gui_window) -> None:
    _app, window = gui_window
    design_index = window.design_select.findData("mobaxterm")
    assert design_index >= 0
    window.design_select.setCurrentIndex(design_index)
    existing_widgets = {
        id(window.tabs.widget(index))
        for index in range(window.tabs.count())
    }
    previous_count = window.tabs.count()

    window.add_welcome_tab(select=False)

    assert window.tabs.count() == previous_count + 1
    new_index = next(
        index
        for index in range(window.tabs.count())
        if id(window.tabs.widget(index)) not in existing_widgets
    )
    assert window.tab_role(new_index) == "home"
    widget = window.tabs.widget(new_index)
    assert widget is not None
    assert widget.property("mobaTabChromeKey") == "home"
    assert "Home" in window.literal_tab_tooltip(new_index)


def test_remaining_optional_design_surface_branches(
    gui_window,
    monkeypatch,
) -> None:
    from PyQt6.QtGui import QResizeEvent
    from PyQt6.QtWidgets import QLineEdit, QToolButton, QWidget

    from remote_ops_workspace.gui_designs import gui_design_preset_home_search_route
    from remote_ops_workspace.moba_connected import build_moba_connected_session_state

    app, window = gui_window

    original_design_index = window.design_select.currentIndex()
    window.set_design_preset("missing-design")
    assert window.design_select.currentIndex() == original_design_index

    toolbar_buttons = window.layout_toolbar_buttons
    welcome_scroll = window.welcome_scroll
    del window.layout_toolbar_buttons
    del window.welcome_scroll
    try:
        event = QResizeEvent(window.size(), window.size())
        type(window).resizeEvent(window, event)
    finally:
        window.layout_toolbar_buttons = toolbar_buttons
        window.welcome_scroll = welcome_scroll

    unregistered = QToolButton(window)
    unregistered.setProperty("productToolbarKey", "unregistered-edge")
    window.set_interaction_state(unregistered, "disabled")
    assert unregistered.isEnabled() is False

    window.set_design_preset("mobaxterm")
    stale_profile_dock = QWidget()
    window.moba_left_stack.addWidget(stale_profile_dock)
    window.moba_connected_dock = stale_profile_dock
    window.show_moba_profile_tree()
    assert window.moba_connected_dock is None

    profile = Profile(
        name="optional-dock-edge",
        protocol="ssh",
        host="optional-dock.example.invalid",
    )
    state = build_moba_connected_session_state(profile)
    stale_connected_dock = QWidget()
    window.moba_left_stack.addWidget(stale_connected_dock)
    window.moba_connected_dock = stale_connected_dock

    class _Dock(QWidget):
        def __init__(self, dock_state) -> None:
            super().__init__()
            self.state = dock_state
            self.initialized = False

        def initialize_background_state(self) -> None:
            self.initialized = True

    _set_closure_value(
        monkeypatch,
        type(window).show_moba_connected_dock,
        "MobaSftpDock",
        _Dock,
    )
    window.show_moba_connected_dock(state)
    assert isinstance(window.moba_connected_dock, _Dock)
    assert window.moba_connected_dock.initialized is True

    window.set_design_preset("securecrt")
    session_filter = window.findChild(QLineEdit, "secureCrtSessionFilter")
    assert session_filter is not None
    session_filter.setObjectName("temporarilyMissingSecureCrtSessionFilter")
    try:
        window.refresh_profiles()
    finally:
        session_filter.setObjectName("secureCrtSessionFilter")

    route = gui_design_preset_home_search_route("securecrt")
    home_search = window.findChild(QLineEdit, route.home_search_object)
    entry_search = window.findChild(QLineEdit, route.entry_search_object)
    assert home_search is not None
    assert entry_search is session_filter
    home_search.setObjectName("temporarilyMissingHomeSearch")
    try:
        window.apply_home_search_route_for_design(route)
    finally:
        home_search.setObjectName(route.home_search_object)
    entry_search.setObjectName("temporarilyMissingEntrySearch")
    try:
        window.apply_home_search_route_for_design(route)
    finally:
        entry_search.setObjectName(route.entry_search_object)

    window.set_design_preset("termius")
    host_search = window.findChild(QLineEdit, "termiusHostSearch")
    assert host_search is not None
    host_search.setObjectName("temporarilyMissingTermiusHostSearch")
    try:
        window.refresh_profiles()
    finally:
        host_search.setObjectName("termiusHostSearch")

    window.set_design_preset("native")
    native_index = window.design_select.findData("native")
    assert native_index == window.design_select.currentIndex()
    window.design_select.setItemData(native_index, "unknown-current-preset")
    try:
        assert window.current_design_id() == "native"
        window.apply_selected_design()
    finally:
        window.design_select.setItemData(native_index, "native")
        window.apply_selected_design()

    unregistered.deleteLater()
    app.processEvents()


def test_remaining_tab_bar_context_and_workflow_branch_outcomes(
    gui_window,
    monkeypatch,
) -> None:
    from PyQt6.QtCore import QPoint, Qt
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QWidget

    from remote_ops_workspace import gui
    from remote_ops_workspace.gui import QuickConnectCandidate

    app, window = gui_window
    window.set_design_preset("mobaxterm")

    regular = QWidget()
    regular_index = window.add_workspace_tab(
        regular,
        "Resizable edge",
        select=False,
        role="terminal",
    )
    window.apply_moba_tab_chrome(
        regular_index,
        key="inactive-session",
        icon_key="session",
        tooltip="Resizable edge",
        closeable=True,
    )
    app.processEvents()
    tab_bar = window.moba_tab_bar
    rect = tab_bar.tabRect(regular_index)
    edge = QPoint(rect.right(), rect.center().y())
    QTest.mousePress(tab_bar, Qt.MouseButton.LeftButton, pos=edge)
    assert tab_bar._tab_resize_index >= 0
    QTest.mouseMove(tab_bar, QPoint(edge.x() + 24, edge.y()))
    QTest.mouseRelease(
        tab_bar,
        Qt.MouseButton.LeftButton,
        pos=QPoint(edge.x() + 24, edge.y()),
    )
    assert tab_bar._tab_resize_index == -1

    prepared: list[int] = []
    tab_bar.tab_switch_prepare_handler = prepared.append
    window.set_workspace_tab_index(window.find_tab_by_role("home"))
    rect = tab_bar.tabRect(regular_index)
    QTest.mouseClick(tab_bar, Qt.MouseButton.RightButton, pos=rect.center())
    QTest.mouseClick(tab_bar, Qt.MouseButton.LeftButton, pos=rect.center())
    assert regular_index in prepared
    QTest.keyClick(tab_bar, Qt.Key.Key_Right)
    assert -1 in prepared
    tab_bar.tab_switch_prepare_handler = None
    QTest.mouseClick(tab_bar, Qt.MouseButton.LeftButton, pos=rect.center())
    QTest.keyClick(tab_bar, Qt.Key.Key_A)

    plus_index = window.find_tab_by_role("new-session")
    assert plus_index >= 0
    selected: list[int] = []
    monkeypatch.setattr(window, "set_workspace_tab_index", selected.append)
    monkeypatch.setattr(window, "build_tab_context_menu", lambda _index: None)
    window.show_tab_context_menu(tab_bar.tabRect(plus_index).center())
    assert selected == []

    activated: list[int] = []
    tab_bar.special_tab_handler = activated.append
    QTest.mouseClick(
        tab_bar,
        Qt.MouseButton.LeftButton,
        pos=tab_bar.tabRect(plus_index).center(),
    )
    assert activated == [plus_index]

    window.set_literal_tab_tooltip(-1, "missing tab")
    assert window.base_tab_tooltip(-1) == ""

    monkeypatch.setattr(window, "current_design_is_moba", lambda: True)
    monkeypatch.setattr(window, "current_moba_connected_dock_is_active", lambda: False)
    missing = QuickConnectCandidate(
        "saved",
        "Missing profile",
        "Missing profile edge",
        profile_name="does-not-exist",
    )
    monkeypatch.setattr(gui, "quick_connect_candidates", lambda *_args, **_kwargs: [missing])
    monkeypatch.setattr(window, "profile_by_name", lambda _name: None)
    window.quick_connect.setText("missing profile")
    window.update_quick_connect_suggestions()
    assert window.quick_connect_suggestions.topLevelItemCount() == 1

    workflows: list[tuple[str, object]] = []
    monkeypatch.setattr(
        window,
        "show_workflow_dialog",
        lambda title, _subtitle, _rows, detail, **_kwargs: workflows.append(
            (title, detail)
        ),
    )
    no_certificate = Profile(
        name="smartcard-without-selection",
        protocol="ssh",
        host="smartcard-none.example.invalid",
        options={"smartcard_provider": "windows-capi"},
    )
    monkeypatch.setattr(window, "selected_profile_for_workflow", lambda: no_certificate)
    window.show_moba_smartcards_status()
    assert window.property("mobaSmartcardGuiCertificateCount") == 0

    compact_profiles = [
        Profile(
            name=f"compact-{index}",
            protocol="ssh",
            host=f"compact-{index}.example.invalid",
        )
        for index in range(2)
    ]
    monkeypatch.setattr(window.store, "load", lambda: compact_profiles)
    window.show_moba_multiexec_status()
    multiexec_detail = next(detail for title, detail in workflows if title == "MultiExec")
    assert "more broadcast target" not in str(multiexec_detail)

    window.profile_list.setCurrentItem(None)
    profile_menu = window.build_profile_context_menu(None)
    profile_menu.deleteLater()

    menu_events: list[object] = []

    class _Menu:
        def exec(self, position) -> None:
            menu_events.append(position)

        def deleteLater(self) -> None:
            menu_events.append("deleted")

    monkeypatch.setattr(window, "build_profile_context_menu", lambda _item: _Menu())
    window.show_profile_context_menu(QPoint(-100, -100))
    assert menu_events[-1] == "deleted"

    monkeypatch.setattr(window, "current_design_is_moba", lambda: True)
    chrome_calls: list[tuple[object, object]] = []
    real_apply_moba_tab_chrome = window.apply_moba_tab_chrome

    def apply_moba_tab_chrome(index, **kwargs) -> None:
        chrome_calls.append((index, kwargs.get("key")))
        real_apply_moba_tab_chrome(index, **kwargs)

    monkeypatch.setattr(window, "apply_moba_tab_chrome", apply_moba_tab_chrome)
    previous_count = window.tabs.count()
    window.add_welcome_tab(select=False)
    assert window.tabs.count() == previous_count + 1
    assert chrome_calls[-1][1] == "home"


def test_securecrt_empty_metadata_without_command_input_is_safe(
    gui_window,
    monkeypatch,
) -> None:
    from dataclasses import replace

    from remote_ops_workspace import gui
    from remote_ops_workspace.gui_designs import gui_design_securecrt_command_window_chrome

    _app, window = gui_window
    chrome = gui_design_securecrt_command_window_chrome()
    monkeypatch.setattr(
        gui,
        "gui_design_securecrt_command_window_chrome",
        lambda: replace(chrome, command=""),
    )
    window.securecrt_command_window = None
    window.securecrt_command_target = None
    window.securecrt_command_input = None
    window.securecrt_command_send = None
    window.securecrt_command_status = None

    window.handle_securecrt_command_window_send()

    assert window.statusBar().currentMessage().endswith(": ")

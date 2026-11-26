from __future__ import annotations

import os
import sys
import time
from dataclasses import replace

import pytest

from remote_ops_workspace.models import Profile
from remote_ops_workspace.terminal import TerminalPanePlan


@pytest.fixture
def workspace(monkeypatch, tmp_path):
    pytest.importorskip("PyQt6")
    from PyQt6 import sip

    from remote_ops_workspace.gui import create_main_window

    monkeypatch.setenv("QT_QPA_PLATFORM", os.getenv("QT_QPA_PLATFORM", "offscreen"))
    monkeypatch.setenv("ROW_HOME", str(tmp_path / "workspace"))
    app, window = create_main_window(["mremoteng-workflows"], show=True)
    window.store.save([
        Profile(name="Alpha", protocol="ssh", host="alpha.example.invalid", group="Ops"),
        Profile(name="Beta", protocol="rdp", host="beta.example.invalid", port=3391, group="Ops"),
    ])
    window.store.set_group_defaults("Ops", {"username": "inherited", "options": {"example": "one"}})
    window.set_design_preset("mremoteng")
    window.resize(1180, 820)
    app.processEvents()
    yield app, window
    if not sip.isdeleted(window):
        window.close()
    app.processEvents()


def test_duplicate_saved_connection_from_menu_and_tree_shortcut(workspace):
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest

    app, window = workspace
    tree = window.profile_list
    window.select_profile("Alpha")
    original = window.store.get("Alpha", resolve=False)
    menu = window.build_profile_context_menu(tree.currentItem())
    action = next(action for action in menu.actions() if action.text() == "Duplicate connection")
    assert action.isEnabled()
    action.trigger()
    assert window.selected_profile_name() == "Alpha (copy)"
    clone = window.store.get("Alpha (copy)", resolve=False)
    assert clone.to_dict() == replace(original, name="Alpha (copy)").to_dict()
    assert window.store.get("Alpha (copy)").username == "inherited"

    window.select_profile("Alpha")
    window.activateWindow()
    tree.setFocus()
    app.processEvents()
    QTest.keyClick(tree, Qt.Key.Key_D, Qt.KeyboardModifier.ControlModifier)
    assert window.selected_profile_name() == "Alpha (copy 2)"
    window.store.set_group_defaults("Ops", {"username": "new-default"})
    assert window.store.get("Alpha (copy 2)").username == "new-default"
    assert window.store.get("Alpha", resolve=False) == original

    tree.setCurrentItem(tree.currentItem().parent())
    folder_menu = window.build_profile_context_menu(tree.currentItem())
    assert not next(action for action in folder_menu.actions() if action.text() == "Duplicate connection").isEnabled()
    window.duplicate_mremoteng_connection()
    assert len(window.store.load()) == 4
    window.set_design_preset("native")
    window.select_profile("Alpha")
    assert "Duplicate connection" not in {action.text() for action in window.build_profile_context_menu().actions()}
    tree.setFocus()
    QTest.keyClick(tree, Qt.Key.Key_D, Qt.KeyboardModifier.ControlModifier)
    assert window.selected_profile_name() == "Alpha"
    assert len(window.store.load()) == 4
    window.set_design_preset("mremoteng")
    window.select_profile("Alpha")
    tree.setFocus()
    app.processEvents()
    QTest.keyClick(tree, Qt.Key.Key_D, Qt.KeyboardModifier.ControlModifier)
    assert window.selected_profile_name() == "Alpha (copy 3)"
    assert len(window.store.load()) == 5


def test_duplicate_connection_handles_profile_removed_by_another_writer(workspace):
    _, window = workspace
    window.select_profile("Alpha")
    menu = window.build_profile_context_menu(window.profile_list.currentItem())
    action = next(action for action in menu.actions() if action.text() == "Duplicate connection")
    assert action.isEnabled()
    window.store.remove("Alpha")
    action.trigger()
    assert "Cannot duplicate connection" in window.statusBar().currentMessage()
    assert [row.name for row in window.store.load()] == ["Beta"]


def test_tree_config_edit_preserves_inheritance_and_dock_choice(workspace):
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QLabel, QToolButton, QTreeWidget

    app, window = workspace
    dock = window.mremoteng_left_property_grid_panel
    editor_button = dock.findChild(QToolButton)
    grid = dock.findChild(QTreeWidget, "mRemoteNgConnectionProperties")
    tree = window.profile_list

    def select(name):
        item = next(item for item in window.iter_profile_tree_items() if item.data(0, Qt.ItemDataRole.UserRole) == name)
        QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton, pos=tree.visualItemRect(item).center())
        return {grid.topLevelItem(i).text(0): grid.topLevelItem(i).text(1) for i in range(grid.topLevelItemCount())}

    assert select("Alpha")["Username"] == "inherited"
    assert window.mremoteng_protocol_label.text() == "SSH"
    assert select("Beta") == {
        "Name": "Beta", "Protocol": "RDP", "Hostname": "beta.example.invalid",
        "Port": "3391", "Username": "inherited", "Group": "Ops",
    }
    observed = {}

    def edit_host():
        dialog = app.activeModalWidget()
        observed["username"] = dialog.fields["username"].text()
        dialog.fields["host"].setText("updated.example.invalid")
        dialog.save_button.click()

    QTimer.singleShot(0, edit_host)
    QTest.mouseClick(editor_button, Qt.MouseButton.LeftButton)
    assert observed == {"username": ""}
    assert window.store.get("Beta").host == "updated.example.invalid"
    assert window.store.get("Beta", resolve=False).username is None
    window.store.set_group_defaults("Ops", {"username": "changed", "options": {"example": "two"}})
    window.refresh_profiles()
    assert select("Beta")["Username"] == "changed"
    assert window.store.get("Beta").options["example"] == "two"
    window.mremoteng_document_filter.setText("alpha")
    assert grid.isHidden() and not editor_button.isEnabled()
    assert window.selected_profile_name() is None
    assert not window.mremoteng_protocol_label.text()
    assert window.findChildren(QLabel, "mRemoteNgRuntimeNotification") == []
    window.mremoteng_document_control_buttons["dock-view"].click()
    assert not dock.isVisible()
    window.set_design_preset("native")
    window.set_design_preset("mremoteng")
    assert not dock.isVisible()
    button = window.mremoteng_document_control_buttons["dock-view"]
    assert not button.isChecked()
    button.click()
    assert dock.isVisible()
    assert select("Alpha")["Hostname"] == "alpha.example.invalid"


def test_connections_tree_f2_renames_raw_profile_and_updates_config(workspace, monkeypatch):
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QLineEdit, QTreeWidget

    app, window = workspace
    tree = window.profile_list
    grid = window.mremoteng_left_property_grid_panel.findChild(QTreeWidget, "mRemoteNgConnectionProperties")
    connections = []
    monkeypatch.setattr(window, "connect_selected", lambda _dry_run: connections.append(window.selected_profile_name()))
    window.select_profile("Beta")
    tree.setFocus()
    app.processEvents()
    original = window.store.get("Beta", resolve=False)

    def edit(value, key=Qt.Key.Key_Return):
        QTest.keyClick(tree, Qt.Key.Key_F2)
        cell = tree.indexWidget(tree.currentIndex())
        assert isinstance(cell, QLineEdit) and cell.selectedText() == "Beta"
        if value is not None:
            QTest.keyClicks(cell, value)
        QTest.keyClick(cell, key)
        app.processEvents()
        app.processEvents()

    edit("Cancelled", Qt.Key.Key_Escape)
    assert window.store.get("Beta", resolve=False) == original
    assert tree.currentItem().text(0) == grid.topLevelItem(0).text(1) == "Beta"
    edit(None)
    assert tree.currentItem().text(0) == "Beta"
    edit("Alpha")
    assert "already exists" in window.statusBar().currentMessage()
    assert tree.currentItem().text(0) == "Beta"
    window.statusBar().clearMessage()
    edit(" ")
    assert "Cannot save name" in window.statusBar().currentMessage()
    assert window.store.get("Beta", resolve=False) == original
    edit("Desk Renamed")
    assert tree.currentItem().text(0) == grid.topLevelItem(0).text(1) == "Desk Renamed"
    assert window.selected_profile_name() == "Desk Renamed"
    assert window.store.get("Desk Renamed", resolve=False) == replace(original, name="Desk Renamed")
    assert window.store.get("Desk Renamed").username == "inherited"
    assert [p.name for p in window.store.load()] == ["Alpha", "Desk Renamed"]
    assert connections == []
    position = tree.visualItemRect(tree.currentItem()).center()
    QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton, pos=position)
    QTest.mouseDClick(tree.viewport(), Qt.MouseButton.LeftButton, pos=position)
    app.processEvents()
    assert connections == ["Desk Renamed"] and tree.indexWidget(tree.currentIndex()) is None

    tree.setCurrentItem(tree.currentItem().parent())
    QTest.keyClick(tree, Qt.Key.Key_F2)
    assert tree.indexWidget(tree.currentIndex()) is None
    window.set_design_preset("native")
    window.select_profile("Desk Renamed")
    QTest.keyClick(tree, Qt.Key.Key_F2)
    assert tree.indexWidget(tree.currentIndex()) is None


@pytest.fixture
def config_cells(workspace):
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QTreeWidget

    app, window = workspace
    window.select_profile("Beta")
    grid = window.mremoteng_left_property_grid_panel.findChild(QTreeWidget, "mRemoteNgConnectionProperties")

    def open_cell(label, *, click=False):
        row = grid.findItems(label, Qt.MatchFlag.MatchExactly)[0]
        if click:
            assert grid.currentItem() is not row
            position = grid.visualRect(grid.indexFromItem(row, 1)).center()
            QTest.mouseClick(grid.viewport(), Qt.MouseButton.LeftButton, pos=position)
        else:
            grid.setCurrentItem(row, 1)
            grid.setFocus()
            QTest.keyClick(grid, Qt.Key.Key_Return)
        editor = grid.indexWidget(grid.indexFromItem(row, 1))
        assert editor is not None and app.activeModalWidget() is None
        return editor

    def finish(editor, value=None, *, cancel=False):
        if value is not None:
            editor.selectAll()
            QTest.keyClick(editor, Qt.Key.Key_Backspace)
            QTest.keyClicks(editor, value)
        QTest.keyClick(editor, Qt.Key.Key_Escape if cancel else Qt.Key.Key_Return)
        app.processEvents()  # Qt commits the native editor on the next event turn.
        app.processEvents()  # Then the profile tree refreshes from the store.

    return window, grid, open_cell, finish


def test_config_inline_commit_cancel_and_inheritance(config_cells):
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest

    window, grid, open_cell, finish = config_cells
    before = window.store.get("Beta", resolve=False)
    host = open_cell("Hostname", click=True)
    assert host.text() == before.host
    finish(host, "cancel.example.invalid", cancel=True)
    assert window.store.get("Beta", resolve=False) == before

    host = open_cell("Hostname")
    concurrent = replace(before, description="Changed elsewhere", tags=["one,two"])
    window.store.replace_named("Beta", concurrent)
    finish(host, "edited.example.invalid")
    assert window.store.get("Beta", resolve=False) == replace(concurrent, host="edited.example.invalid")
    assert grid.topLevelItem(2).text(1) == "edited.example.invalid"
    assert grid.currentItem().text(0) == "Hostname"
    QTest.keyClick(grid, Qt.Key.Key_Down)
    assert grid.currentItem().text(0) == "Port"
    assert window.store.get("Alpha").host == "alpha.example.invalid"

    username = open_cell("Username")
    assert username.text() == "inherited"
    finish(username)
    assert window.store.get("Beta", resolve=False).username is None
    window.store.set_group_defaults("Ops", {"username": "changed"})
    window.refresh_profiles()
    username = open_cell("Username")
    assert username.text() == "changed"
    finish(username, "override")
    assert window.store.get("Beta", resolve=False).username == "override"
    finish(open_cell("Username"), "")
    assert window.store.get("Beta", resolve=False).username is None
    assert grid.topLevelItem(4).text(1) == "changed"


def test_config_first_value_click_in_single_activation_style(config_cells):
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QProxyStyle, QStyle

    class SingleClickStyle(QProxyStyle):
        def styleHint(self, hint, option=None, widget=None, returnData=None):
            if hint == QStyle.StyleHint.SH_ItemView_ActivateItemOnSingleClick:
                return 1
            return super().styleHint(hint, option, widget, returnData)

    _window, grid, open_cell, finish = config_cells
    style = SingleClickStyle("Fusion")
    style.setParent(grid)
    grid.setStyle(style)
    name_label = grid.indexFromItem(grid.topLevelItem(0), 0)
    QTest.mouseClick(grid.viewport(), Qt.MouseButton.LeftButton, pos=grid.visualRect(name_label).center())
    assert grid.indexWidget(name_label) is None
    assert grid.indexWidget(grid.indexFromItem(grid.topLevelItem(0), 1)) is None
    host = open_cell("Hostname", click=True)
    assert host.text() == "beta.example.invalid"
    finish(host, cancel=True)


@pytest.mark.parametrize(("first", "new_value", "saved_name"), [
    ("Hostname", "two-edits.example.invalid", "Beta"), ("Name", "New name", "New name"),
])
def test_leaving_dirty_cell_preserves_the_next_inline_editor(config_cells, first, new_value, saved_name):
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication

    window, grid, open_cell, finish = config_cells
    previous = open_cell(first)
    previous.selectAll()
    QTest.keyClicks(previous, new_value)
    port = open_cell("Port", click=True)
    port.selectAll()
    QTest.keyClicks(port, "2200")
    port.setSelection(1, 2)
    QApplication.processEvents()
    QApplication.processEvents()
    assert grid.indexWidget(grid.currentIndex()) is port
    assert port.text() == "2200" and port.selectedText() == "20"
    assert window.selected_profile_name() == saved_name
    assert grid.findItems(first, Qt.MatchFlag.MatchExactly)[0].text(1) == new_value
    finish(port)
    assert window.store.get(saved_name).port == 2200


def test_pending_config_refresh_ends_with_window(config_cells):
    from PyQt6 import sip
    from PyQt6.QtCore import QCoreApplication, QEvent, QTimer
    from PyQt6.QtTest import QTest

    window, grid, open_cell, _finish = config_cells
    store = window.store
    host = open_cell("Hostname")
    host.selectAll()
    QTest.keyClicks(host, "before-close.example.invalid")
    open_cell("Port", click=True)
    timer = grid.findChild(QTimer)
    assert timer.isActive()
    window.deleteLater()
    QCoreApplication.sendPostedEvents(window, QEvent.Type.DeferredDelete)
    assert sip.isdeleted(timer)
    QCoreApplication.processEvents()
    assert store.get("Beta").host == "before-close.example.invalid"


def test_config_inline_protocol_validation_and_rename(config_cells):
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QSignalSpy, QTest
    from PyQt6.QtWidgets import QApplication, QComboBox

    window, grid, open_cell, finish = config_cells
    finish(open_cell("Port"), "65536")
    assert "between 1 and 65535" in window.statusBar().currentMessage()
    assert window.store.get("Beta").port == 3391
    assert grid.topLevelItem(3).text(1) == "3391"

    protocol = open_cell("Protocol")
    assert isinstance(protocol, QComboBox) and protocol.currentText() == "RDP"
    assert not protocol.isEditable()
    activated = QSignalSpy(protocol.activated)
    protocol.showPopup()
    QTest.keyClick(protocol.view(), Qt.Key.Key_Home)
    QTest.keyClick(protocol.view(), Qt.Key.Key_Escape)
    assert window.store.get("Beta").protocol == "rdp"
    protocol.showPopup()
    options = protocol.view()
    choice = protocol.model().index(protocol.findText("SSH"), 0)
    options.scrollTo(choice)
    QApplication.processEvents()
    QTest.mouseMove(options.viewport(), options.visualRect(choice).center())
    QTest.mouseClick(
        options.viewport(), Qt.MouseButton.LeftButton, pos=options.visualRect(choice).center(),
        delay=QApplication.doubleClickInterval() + 50,
    )
    QApplication.processEvents()
    QApplication.processEvents()
    assert len(activated) == 1
    assert window.store.get("Beta").protocol == "ssh"
    assert window.mremoteng_protocol_label.text() == "SSH"

    finish(open_cell("Name"), " Alpha ")
    assert "already exists" in window.statusBar().currentMessage()
    assert [profile.name for profile in window.store.load()] == ["Alpha", "Beta"]
    finish(open_cell("Name"), "Renamed")
    assert window.selected_profile_name() == "Renamed"
    assert window.store.get("Renamed").host == "beta.example.invalid"


def test_config_inline_selection_and_store_conflicts(config_cells):
    from PyQt6.QtTest import QTest

    window, grid, open_cell, finish = config_cells
    before = window.store.get("Beta", resolve=False)
    host = open_cell("Hostname")
    host.selectAll()
    QTest.keyClicks(host, "stale.example.invalid")
    window.select_profile("Alpha")
    QTest.qWait(20)
    assert window.store.get("Beta", resolve=False) == before
    assert grid.topLevelItem(2).text(1) == window.store.get("Alpha").host == "alpha.example.invalid"

    window.select_profile("Beta")
    host = open_cell("Hostname")
    selected = window.profile_list.currentItem()
    selected.setHidden(True)
    finish(host, "hidden.example.invalid")
    assert window.store.get("Beta", resolve=False) == before
    selected.setHidden(False)
    host = open_cell("Hostname")
    window.store.replace_named("Beta", replace(before, host="external.example.invalid"))
    finish(host, "conflict.example.invalid")
    assert "changed since editing began" in window.statusBar().currentMessage()
    assert grid.topLevelItem(2).text(1) == window.store.get("Beta").host == "external.example.invalid"
    host = open_cell("Hostname")
    window.store.remove("Beta")
    finish(host, "deleted.example.invalid")
    assert [profile.name for profile in window.store.load()] == ["Alpha"]
    assert "Cannot save host" in window.statusBar().currentMessage()
    assert grid.isHidden()


def test_config_edit_key_during_popup_window_focus_restore(config_cells):
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication, QWidget

    window, grid, open_cell, finish = config_cells
    other = QWidget()
    try:
        protocol = open_cell("Protocol")
        protocol.showPopup()
        QTest.keyClick(protocol.view(), Qt.Key.Key_Escape)
        finish(protocol, cancel=True)
        other.show()
        other.activateWindow()
        QApplication.processEvents()
        assert QApplication.activeWindow() is other
        row = grid.topLevelItem(0)
        grid.setCurrentItem(row, 1)
        grid.setFocus()
        window.activateWindow()
        QTest.keyClick(grid, Qt.Key.Key_Return)
        editor = grid.indexWidget(grid.indexFromItem(row, 1))
        assert editor is not None
        finish(editor, "After popup")
        assert window.store.get("After popup").host == "beta.example.invalid"
    finally:
        other.close()


def test_config_keypad_edit_preserves_active_input_method(config_cells):
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QInputMethodEvent
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication

    window, grid, _open_cell, finish = config_cells
    row = grid.topLevelItem(4)
    grid.setCurrentItem(row, 1)
    grid.setFocus()
    index = grid.currentIndex()
    QTest.keyClick(grid, Qt.Key.Key_F2, Qt.KeyboardModifier.ShiftModifier)
    assert grid.indexWidget(index) is None
    QTest.keyClick(grid, Qt.Key.Key_Enter, Qt.KeyboardModifier.KeypadModifier)
    editor = grid.indexWidget(index)
    assert editor is not None
    editor.selectAll()
    QTest.keyClicks(editor, "user")
    QApplication.sendEvent(editor, QInputMethodEvent("名", []))
    QTest.keyClick(grid, Qt.Key.Key_F2)
    assert grid.indexWidget(index) is editor
    commit = QInputMethodEvent()
    commit.setCommitString("名")
    QApplication.sendEvent(editor, commit)
    assert editor.text() == "user名"
    finish(editor)
    assert window.store.get("Beta", resolve=False).username == "user名"


def test_reconnect_restarts_only_the_selected_open_document(workspace, tmp_path):
    from PyQt6.QtTest import QTest

    from remote_ops_workspace.gui_designs import gui_design_mremoteng_connection_document_route

    _app, window = workspace
    window.select_profile("Beta")
    button = window.mremoteng_document_control_buttons["reconnect"]
    button.click()
    assert window.all_terminal_panes() == []
    assert "Open a connection" in window.statusBar().currentMessage()
    log = tmp_path / "starts.txt"
    command = [sys.executable, "-c", "import pathlib,sys; pathlib.Path(sys.argv[1]).open('ab').write(b'x')", str(log)]
    window.open_terminal_tab(
        TerminalPanePlan(title="Beta test transport", command=command, source="profile"),
        profile=window.store.get("Beta"), tab_title="Beta [RDP]",
    )
    pane = window.active_terminal_pane()

    def wait_for_starts(count):
        deadline = time.monotonic() + 10
        while time.monotonic() < deadline:
            QTest.qWait(10)
            if log.is_file() and log.read_bytes() == b"x" * count and not pane.is_running():
                return
        pytest.fail(f"Expected {count} completed launches of the local test process")

    wait_for_starts(1)
    home = window.find_tab_by_role("home")
    window.tabs.setCurrentIndex(home)
    window.select_profile("Alpha")
    button.click()
    assert window.all_terminal_panes() == [pane] and log.read_bytes() == b"x"
    assert "Open a connection" in window.statusBar().currentMessage()
    window.select_profile("Beta")
    button.click()
    assert window.statusBar().currentMessage() == "Reconnect requested for Beta"
    wait_for_starts(2)
    route = gui_design_mremoteng_connection_document_route()
    assert button.property(route.live_profile_property) == "Beta"
    window.tabs.setCurrentIndex(window.tabs.indexOf(pane))
    window.select_profile("Alpha")
    window.handle_mremoteng_document_reconnect()
    wait_for_starts(3)
    assert button.property(route.live_profile_property) == "Beta"
    assert window.all_terminal_panes() == [pane]


def test_connections_tree_switches_to_matching_live_tab(workspace, monkeypatch):
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest

    app, window = workspace
    tab = window.tabs
    tree = window.profile_list
    profile = window.store.get("Beta")
    plan = TerminalPanePlan("Beta", [sys.executable, "-c", "import sys; sys.stdin.read(1)"], "profile:Beta")
    window.open_terminal_tab(plan, profile=profile)
    pane = window.active_terminal_pane()
    deadline = time.monotonic() + 10
    while not pane.is_running() and time.monotonic() < deadline:
        QTest.qWait(10)
    assert pane.is_running()
    monkeypatch.setattr(window, "confirm_stop_processes", lambda *_args: True)

    launched = []
    monkeypatch.setattr(window, "connect_selected", lambda _dry_run: launched.append(window.selected_profile_name()))
    home = window.find_tab_by_role("home")
    window.select_profile("Beta")
    item = tree.currentItem()
    tab.setCurrentIndex(home)
    tree.itemActivated.emit(item, 0)
    assert tab.currentWidget() is pane and not launched

    tab.setCurrentIndex(home)
    def click():
        QTest.mouseClick(tree.viewport(), Qt.MouseButton.LeftButton, pos=tree.visualItemRect(item).center())

    click()
    assert tab.currentIndex() == home
    window.mremoteng_switch_on_tree_click.trigger()
    click()
    app.processEvents()
    assert tab.currentWidget() is pane and not launched
    assert pane.is_running() and window.all_terminal_panes() == [pane]
    widget_at = tab.widget
    with monkeypatch.context() as patches:
        patches.setattr(tab, "widget", lambda index: None if index == home else widget_at(index))
        assert window.switch_to_mremoteng_open_connection("Beta")

    def unavailable(_name):
        raise OSError("profile store unavailable")

    with monkeypatch.context() as patches:
        patches.setattr(window, "profile_by_name", unavailable)
        assert not window.switch_to_mremoteng_open_connection("Beta")
    window.store.remove("Beta")
    assert not window.switch_to_mremoteng_open_connection("Beta")
    window.store.add(profile)

    tab.setCurrentIndex(home)
    window.store.replace_named("Beta", replace(profile, host="new-beta.example.invalid"))
    window.refresh_profiles()
    window.select_profile("Beta")
    item = tree.currentItem()
    click()
    assert tab.currentIndex() == home and not launched
    window.activate_profile_item(item)
    assert launched == ["Beta"]

    window.store.replace_named("Beta", profile)
    window.refresh_profiles()
    window.set_design_preset("native")
    window.select_profile("Beta")
    window.activate_profile_item(tree.currentItem())
    assert launched == ["Beta", "Beta"]


def test_mremoteng_double_click_closes_only_the_clicked_connection(workspace):
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QMessageBox

    app, window = workspace
    tabs = window.tabs
    bar = tabs.tabBar()
    left = Qt.MouseButton.LeftButton
    buttons = QMessageBox.StandardButton
    prompts = []

    def double_click(index, button=left, answer=buttons.No):
        point = bar.tabRect(index).center()
        QTimer.singleShot(0, lambda: reply(answer))
        QTest.mouseDClick(bar, button, pos=point)
        QTest.mouseRelease(bar, button, pos=point)
        app.processEvents()

    def reply(button):
        dialog = app.activeModalWidget()
        if isinstance(dialog, QMessageBox):
            prompts.append((dialog.windowTitle(), dialog.text(), dialog.standardButtons(),
                            dialog.standardButton(dialog.defaultButton())))
            if button == buttons.Yes:
                # A prompt runs a nested event loop. Session tabs may move before the reply.
                bar.moveTab(window.find_tab_by_label("Alpha"), window.find_tab_by_label("Beta"))
            QTest.mouseClick(dialog.button(button), left)

    try:
        for name in ("Alpha", "Beta"):
            window.open_terminal_tab(
                TerminalPanePlan(name, [sys.executable, "-c", "import time; time.sleep(60)"], "profile"),
                profile=window.store.get(name),
            )
            pane = window.active_terminal_pane()
            deadline = time.monotonic() + 10
            while not pane.is_running() and time.monotonic() < deadline:
                QTest.qWait(10)
            assert pane.is_running()

        home = window.find_tab_by_role("home")
        double_click(home)
        assert window.find_tab_by_role("home") == home
        window.set_design_preset("securecrt")
        double_click(window.find_tab_by_label("Alpha"))
        assert len(window.running_terminal_panes()) == 2
        window.set_design_preset("mremoteng")
        bar.moveTab(window.find_tab_by_label("Beta"), window.find_tab_by_label("Alpha"))
        alpha = window.find_tab_by_label("Alpha")
        double_click(alpha, Qt.MouseButton.RightButton)
        window.mremoteng_double_click_close.trigger()
        double_click(alpha)
        window.mremoteng_double_click_close.trigger()
        assert prompts == []
        assert len(window.running_terminal_panes()) == 2

        for answer in (buttons.No, buttons.Yes):
            window.set_workspace_tab_index(window.find_tab_by_label("Beta"))
            double_click(alpha, answer=answer)
            # QMessageBox ignores setWindowTitle on macOS, including with offscreen Qt.
            title = "" if sys.platform == "darwin" else "Close tab"
            assert prompts[-1:] == [(title, "Stop 1 running process pane(s)?", buttons.Yes | buttons.No, buttons.No)]
            if answer == buttons.No:
                assert window.find_tab_by_label("Alpha") == alpha
                assert len(window.running_terminal_panes()) == 2
        assert len(prompts) == 2
        assert window.find_tab_by_label("Alpha") == -1
        assert [p.profile.name for p in window.running_terminal_panes()] == ["Beta"]
    finally:
        # The fixture closes any remaining local child when the window exits.
        window.confirm_stop_processes = lambda *_args: True


@pytest.mark.parametrize(("label", "default"), [
    ("Double click on tab closes it", True),
    ("Switch to open connection on click", False),
])
def test_mremoteng_tools_option_persists_between_windows(workspace, label, default):
    from PyQt6.QtCore import QPoint, Qt
    from PyQt6.QtTest import QTest

    from remote_ops_workspace.gui import create_main_window

    app, window = workspace

    def click_option(owner, expected):
        tools = next(menu for menu in owner.mremoteng_top_menus if menu.title() == "Tools")
        assert tools.actions()[0].text() == "External Tools"
        options = next(action.menu() for action in tools.actions() if action.text() == "Options")
        action = next(action for action in options.actions() if action.text() == label)
        assert action.isCheckable() and action.isChecked() is expected
        options.popup(owner.mapToGlobal(QPoint(80, 80)))
        app.processEvents()
        QTest.mouseClick(options, Qt.MouseButton.LeftButton, pos=options.actionGeometry(action).center())
        assert action.isChecked() is not expected

    click_option(window, default)
    _, second = create_main_window(["mremoteng-option-reopen"], show=True)
    try:
        second.set_design_preset("mremoteng")
        click_option(second, not default)
    finally:
        second.close()


def test_finished_shell_disappearing_during_close_confirmation_keeps_its_neighbour(workspace, monkeypatch):
    from PyQt6.QtTest import QTest

    _app, window = workspace
    plan = TerminalPanePlan("Transient shell", [sys.executable, "-c", "import sys; sys.stdin.buffer.read(1)"])
    window.open_terminal_tab(plan)
    pane = window.active_terminal_pane()
    deadline = time.monotonic() + 10
    while not pane.is_running() and time.monotonic() < deadline:
        QTest.qWait(10)
    assert pane.is_running()

    def finish_while_waiting(_title, _count):
        pane.process.write(b"x")
        deadline = time.monotonic() + 10
        while window.find_tab_by_label(plan.title) >= 0 and time.monotonic() < deadline:
            QTest.qWait(10)
        assert window.find_tab_by_label(plan.title) == -1
        return True

    monkeypatch.setattr(window, "confirm_stop_processes", finish_while_waiting)
    try:
        window.close_tab(window.find_tab_by_label(plan.title))
        assert window.tabs.count() == 1
        assert window.tab_role(0) == "home"
    finally:
        window.confirm_stop_processes = lambda *_args: True


def test_mremoteng_unreadable_option_disables_gesture_and_write_failure_retains_choice(workspace, tmp_path, monkeypatch):
    from PyQt6.QtWidgets import QMenu

    from remote_ops_workspace import gui_mremoteng

    _app, window = workspace
    path = tmp_path / "workspace" / "mremoteng-double-click-closes-tab.json"
    for contents in ('"false"', " " * 65):
        path.write_text(contents, encoding="utf-8")
        window.add_mremoteng_tab_options(QMenu(window))
        assert not window.mremoteng_double_click_close.isChecked()
        assert "Cannot read" in window.statusBar().currentMessage()
    path.unlink()
    path.mkdir()
    window.add_mremoteng_tab_options(QMenu(window))
    action = window.mremoteng_double_click_close
    assert not action.isChecked()
    assert "Cannot read" in window.statusBar().currentMessage()

    def fail_write(*args, **kwargs):
        raise OSError("fixture write error")

    monkeypatch.setattr(gui_mremoteng, "write_json_atomic", fail_write)
    action.trigger()
    assert not action.isChecked()
    assert "Cannot save" in window.statusBar().currentMessage()

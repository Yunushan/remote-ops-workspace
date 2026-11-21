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

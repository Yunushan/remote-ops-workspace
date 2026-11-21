from __future__ import annotations

import os
import sys
import time

import pytest

from remote_ops_workspace.models import Profile
from remote_ops_workspace.terminal import TerminalPanePlan


@pytest.fixture
def workspace(monkeypatch, tmp_path):
    pytest.importorskip("PyQt6")
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

from __future__ import annotations

import json
import os

import pytest


@pytest.fixture
def clean_gui_window(monkeypatch, tmp_path):
    if "QT_QPA_PLATFORM" not in os.environ:
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("ROW_HOME", str(tmp_path / "row-home"))
    pytest.importorskip("PyQt6")
    from remote_ops_workspace.gui import create_main_window

    app, window = create_main_window(["gui-profile-startup"], show=False)
    window.show()
    app.processEvents()
    yield app, window
    window.close()
    app.processEvents()


def test_normal_gui_startup_does_not_seed_sample_profiles(clean_gui_window) -> None:
    _app, window = clean_gui_window

    assert window.property("guiPreviewSamples") is False
    assert window.store.load(resolve=False) == []


@pytest.mark.parametrize(("preset", "sidebar_filter"), [
    ("native", None),
    ("securecrt", "secureCrtSessionFilter"),
    ("termius", "termiusHostSearch"),
    ("remmina", "remminaProfileFilter"),
])
def test_home_shows_real_connections_and_filters_without_launching(clean_gui_window, preset, sidebar_filter) -> None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QFrame, QLabel, QLineEdit, QWidget

    from remote_ops_workspace.models import Profile

    app, window = clean_gui_window
    window.store.save([
        Profile(name="North server", protocol="ssh", host="north.example.invalid"),
        Profile(name="South server", protocol="rdp", host="south.example.invalid", description="Rack on Bergstraße"),
    ])
    window.set_design_preset(preset)
    window.refresh_profiles()
    app.processEvents()
    home = window.tabs.widget(window.find_tab_by_role("home"))
    assert home.findChild(QWidget, "productWorkspaceSurface") is None
    assert home.findChild(QWidget, "productReferenceState") is None
    for label in home.findChildren(QLabel):
        assert all(name not in label.text() for name in ("edge-prod", "win-admin", "files-prod"))
    assert not window.remmina_profile_list_chrome.findChildren(QFrame, "remminaProfileListRow")
    search = home.findChild(QLineEdit, "homeSearch")
    search.setText("south.example.invalid")
    tree_items = {
        item.data(0, Qt.ItemDataRole.UserRole): item
        for item in window.iter_profile_tree_items()
        if item.data(0, Qt.ItemDataRole.UserRole)
    }
    assert tree_items["North server"].isHidden()
    assert not tree_items["South server"].isHidden()
    profile_filter = window.findChild(QLineEdit, sidebar_filter) if sidebar_filter else search
    profile_filter.setText("Target:")
    assert all(row.isHidden() for row in tree_items.values())
    profile_filter.clear()
    QTest.keyClicks(profile_filter, "BERGSTRASSE")
    assert search.text() == "BERGSTRASSE"
    assert tree_items["North server"].isHidden()
    assert not tree_items["South server"].isHidden()
    window.refresh_profiles()
    QTest.keyClick(search, Qt.Key.Key_Return)
    assert window.selected_profile_name() == "South server"
    assert window.all_terminal_panes() == []
    QTest.keyClick(search, Qt.Key.Key_Return)
    assert window.selected_profile_name() == "South server"
    search.setText("absent.example.invalid")
    QTest.keyClick(search, Qt.Key.Key_Return)
    assert window.selected_profile_name() is None
    assert window.all_terminal_panes() == []
    search.clear()
    assert all(not item.isHidden() for item in window.iter_profile_tree_items())


@pytest.mark.parametrize(("preset", "prefix"), [
    ("native", ""), ("securecrt", "Folder: "), ("termius", "Vault / "), ("remmina", ""),
])
def test_saved_group_navigation_and_search(clean_gui_window, preset, prefix) -> None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QLineEdit

    app, window = clean_gui_window
    profiles = [
        {"name": "prod-cluster", "protocol": "ssh", "host": "a.invalid", "group": "Field/Primary"},
        {"name": "jump-host", "protocol": "rdp", "host": "b.invalid", "group": r"Field\Standby"},
        {"name": "legacy", "protocol": "vnc", "host": "c.invalid"},
    ]
    window.store.path.write_text(json.dumps({"version": 1, "profiles": profiles}), encoding="utf-8")
    window.set_design_preset(preset)
    window.refresh_profiles()
    app.processEvents()
    rows = {
        item.data(0, Qt.ItemDataRole.UserRole): item
        for item in window.iter_profile_tree_items()
        if item.data(0, Qt.ItemDataRole.UserRole)
    }
    primary = rows["prod-cluster"].parent()
    standby = rows["jump-host"].parent()
    assert primary.text(0) == prefix + "Primary"
    assert standby.text(0) == prefix + "Standby"
    assert primary.parent() is standby.parent() and primary.parent().text(0) == prefix + "Field"
    assert rows["legacy"].parent().text(0) == prefix + "default"

    tree = window.profile_list
    tree.setCurrentItem(standby)
    QTest.keyClick(tree, Qt.Key.Key_Left)
    assert not standby.isExpanded()
    QTest.keyClick(tree, Qt.Key.Key_Right)
    QTest.keyClick(tree, Qt.Key.Key_Down)
    assert window.selected_profile_name() == "jump-host"
    home = window.tabs.widget(window.find_tab_by_role("home"))
    search = home.findChild(QLineEdit, "homeSearch")
    for query, expected in [
        ("field", {"prod-cluster", "jump-host"}), ("FIELD/STANDBY", {"jump-host"}), ("vnc", {"legacy"}),
    ]:
        search.setText(query)
        assert {name for name, item in rows.items() if not item.isHidden()} == expected
    assert json.loads(window.store.path.read_text(encoding="utf-8"))["profiles"] == profiles


@pytest.mark.parametrize(("design", "search_name"), [
    ("mremoteng", "mRemoteNgDocumentFilter"),
    ("securecrt", "secureCrtSessionFilter"),
    ("termius", "termiusHostSearch"),
])
def test_saved_search_restores_collapsed_folders(clean_gui_window, design, search_name):
    from PyQt6.QtWidgets import QLineEdit

    from remote_ops_workspace.models import Profile

    _app, window = clean_gui_window
    window.store.save([
        Profile("Primary server", "ssh", "primary.example.invalid", group="Ops/Primary"),
        Profile("Standby server", "ssh", "standby.example.invalid", group="Ops/Standby"),
    ])
    window.set_design_preset(design)
    tree = window.profile_list
    search = window.findChild(QLineEdit, search_name)
    assert search is not None

    def folders():
        ops = tree.topLevelItem(0).child(0)
        return ops.child(0), ops.child(1)

    primary, standby = folders()
    primary.setExpanded(False)
    standby.setExpanded(False)
    search.setText("Primary server")
    assert primary.isExpanded()
    assert standby.isHidden() and not standby.isExpanded()
    search.setText("Standby server")
    assert primary.isHidden() and standby.isExpanded()
    search.clear()
    assert all(not folder.isHidden() and not folder.isExpanded() for folder in folders())
    search.setText("Primary server")
    window.refresh_profiles()
    primary, standby = folders()
    assert primary.isExpanded() and standby.isHidden()
    search.clear()
    assert all(not folder.isHidden() and not folder.isExpanded() for folder in folders())
    search.setText("Primary server")
    window.select_profile("Primary server")
    search.clear()
    assert primary.isExpanded() and not standby.isExpanded()
    assert window.selected_profile_name() == "Primary server"


def test_remmina_search_switches_between_folder_tree_and_flat_results(clean_gui_window, monkeypatch):
    from unittest.mock import Mock

    from PyQt6.QtCore import QEvent, Qt
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtTest import QTest

    from remote_ops_workspace.models import Profile

    app, window = clean_gui_window
    window.store.save([
        Profile("North database", "rdp", "north.example.invalid", group="Field/Primary", tags=["alpha"]),
        Profile("Night desk", "rdp", "standby.example.invalid", group="Field/Standby", tags=["beta"]),
        Profile("Home desk", "vnc", "home.example.invalid", group="Home"),
        Profile("Z Field overview", "ssh", "overview.example.invalid", group="Field"),
    ])
    window.set_design_preset("remmina")
    tree = window.profile_list
    search = window.remmina_profile_filter
    rows_removed = Mock()
    tree.model().rowsRemoved.connect(rows_removed)

    def top_rows():
        items = (tree.topLevelItem(i) for i in range(tree.topLevelItemCount()))
        return [item.text(0) for item in items if not item.isHidden()]

    assert top_rows() == ["Field", "Home"]
    tree.topLevelItem(1).setExpanded(False)
    window.select_profile("North database")
    opened = []
    monkeypatch.setattr(window, "launch_profile", lambda profile, **kwargs: opened.append(profile.name))
    load_profiles = Mock(wraps=window.store.load)
    monkeypatch.setattr(window.store, "load", load_profiles)
    for query, expected in [
        ("Field", ["Night desk", "North database", "Z Field overview"]), ("FIELD/STANDBY", ["Night desk"]),
        ("vnc", ["Home desk"]), ("north.example.invalid", ["North database"]), ("beta", ["Night desk"]), ("absent", []),
    ]:
        search.setText(query)
        assert top_rows() == expected
        assert tree.topLevelItemCount() == 4  # The flat model contains profile rows only.
        assert rows_removed.call_count == 1
    load_profiles.assert_not_called()
    assert window.selected_profile_name() is None
    window.refresh_profiles()
    rows_removed.reset_mock()
    search.clear()
    assert rows_removed.call_count == 1
    assert top_rows() == ["Field", "Home"]
    assert not tree.topLevelItem(1).isExpanded()
    assert window.selected_profile_name() == "North database"

    search.setText("Field")
    tree.setFocus()
    QTest.keyClick(tree, Qt.Key.Key_Up)
    assert window.selected_profile_name() == "Night desk"
    QTest.keyClick(tree, Qt.Key.Key_Return)
    app.processEvents()
    assert opened == ["Night desk"]
    QTest.keyClick(tree, Qt.Key.Key_Enter, Qt.KeyboardModifier.KeypadModifier)
    assert opened == ["Night desk", "Night desk"]
    app.sendEvent(tree, QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier, "", True))
    assert opened == ["Night desk", "Night desk"]
    search.clear()
    assert window.selected_profile_name() == "Night desk"
    assert tree.currentItem().parent().text(0) == "Standby"
    tree.setCurrentItem(tree.currentItem().parent())
    QTest.keyClick(tree, Qt.Key.Key_Return)
    assert opened == ["Night desk", "Night desk"]
    tree.setCurrentItem(None)
    QTest.keyClick(tree, Qt.Key.Key_Return)
    assert opened == ["Night desk", "Night desk"]
    assert [item.text(0) for item in window.iter_profile_tree_items()] == [
        "Field", "Z Field overview", "Primary", "North database", "Standby", "Night desk", "Home", "Home desk",
    ]
    folder = tree.topLevelItem(0)
    tree.setCurrentItem(folder)
    search.setText("north")
    assert tree.currentItem() is None and folder.treeWidget() is None
    search.clear()
    assert tree.currentItem() is folder and tree.topLevelItem(0) is folder
    search.setText("north")
    window.refresh_profiles()
    search.clear()
    assert tree.currentItem() is tree.topLevelItem(0)
    assert tree.currentItem().text(0) == "Field"
    window.set_design_preset("native")
    window.select_profile("Night desk")
    key = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Return, Qt.KeyboardModifier.NoModifier)
    assert not window._remmina_open_keys.eventFilter(tree, key)
    assert opened == ["Night desk", "Night desk"]


def test_mremoteng_tree_shows_stored_names_and_routes_duplicate_imports(clean_gui_window, tmp_path, monkeypatch):
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QTreeWidget

    from remote_ops_workspace.profile_importers import import_profiles

    _app, window = clean_gui_window
    source = tmp_path / "connections.xml"
    source.write_text(
        '<Connections><Node Name="Ops" Type="Container">'
        '<Node Name="Synthetic QA" Type="Connection" Protocol="RDP" Hostname="one.invalid"/>'
        '</Node><Node Name="Support" Type="Container">'
        '<Node Name="Synthetic QA" Type="Connection" Protocol="SSH2" Hostname="two.invalid"/>'
        '</Node></Connections>', encoding="utf-8",
    )
    window.store.add_many(import_profiles(source, "mremoteng").profiles)
    window.set_design_preset("mremoteng")
    rows = {item.data(0, Qt.ItemDataRole.UserRole): item for item in window.iter_profile_tree_items()}
    grid = window.findChild(QTreeWidget, "mRemoteNgConnectionProperties")
    activations = []
    monkeypatch.setattr(window, "connect_selected", lambda _dry: activations.append(window.selected_profile_name()))
    for name, folder, protocol, host in (
        ("Synthetic QA", "Ops", "RDP", "one.invalid"),
        ("Synthetic QA-2", "Support", "SSH", "two.invalid"),
    ):
        row = rows[name]
        assert (row.text(0), row.parent().text(0)) == (name, folder)
        window.mremoteng_document_filter.setText(protocol)
        assert [key for key, item in rows.items() if key and not item.isHidden()] == [name]
        window.select_profile(name)
        assert [grid.topLevelItem(i).text(1) for i in range(3)] == [name, protocol, host]
        window.profile_list.itemActivated.emit(row, 0)
        window.mremoteng_document_filter.clear()
    assert activations == ["Synthetic QA", "Synthetic QA-2"]


@pytest.mark.parametrize(("preset", "ssh_icon"), [
    ("native", "ssh"), ("mobaxterm", "ssh"), ("securecrt", "ssh2"),
    ("termius", "host"), ("remmina", "ssh"), ("mremoteng", "ssh"),
])
def test_saved_profile_icons_follow_protocol_even_with_misleading_names(clean_gui_window, preset, ssh_icon):
    from PyQt6.QtCore import Qt

    from remote_ops_workspace.gui_profile_tree import TREE_ICON_KEY_ROLE
    from remote_ops_workspace.models import Profile

    _app, window = clean_gui_window
    window.store.save([
        Profile(name="rdp-gateway", protocol="ssh", host="vnc.invalid", group="vault.xml"),
        Profile(name="deploy-files", protocol="vnc", host="rdp.invalid", group="vault.xml"),
        Profile(name="local-shell", protocol="sftp", host="rdp.invalid", group="vault.xml"),
        Profile(name="jump-host", protocol="local", group="vault.xml"),
        Profile(name="www", protocol="https", url="https://files.invalid", group="vault.xml"),
    ])
    window.set_design_preset(preset)
    window.refresh_profiles()
    rows = {item.data(0, Qt.ItemDataRole.UserRole): item for item in window.iter_profile_tree_items()}
    assert {key: item.data(0, TREE_ICON_KEY_ROLE) for key, item in rows.items() if key} == {
        "rdp-gateway": ssh_icon, "deploy-files": "vnc", "local-shell": "sftp", "jump-host": "shell", "www": "host",
    }
    assert rows["rdp-gateway"].parent().data(0, TREE_ICON_KEY_ROLE) == "folder"


def test_gui_sample_rows_require_explicit_preview_opt_in(monkeypatch, tmp_path) -> None:
    if "QT_QPA_PLATFORM" not in os.environ:
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("ROW_HOME", str(tmp_path / "row-home"))
    pytest.importorskip("PyQt6")
    from remote_ops_workspace.gui import create_main_window

    app, window = create_main_window(
        ["gui-profile-preview"],
        show=False,
        preview_samples=True,
    )
    try:
        assert window.property("guiPreviewSamples") is True
        for preset, name, expected_folder in [
            ("securecrt", "jump-host", "Folder: Pinned"),
            ("termius", "prod-cluster", "Vault / Teams"),
            ("remmina", "win-admin", "Group: RDP"),
            ("mremoteng", "edge-prod", "Container: prod"),
        ]:
            window.set_design_preset(preset)
            window.select_profile(name)
            assert window.selected_profile_name() == name
            assert window.profile_list.currentItem().parent().text(0) == expected_folder
            if preset == "mremoteng":
                assert window.profile_list.currentItem().text(0) == "edge-prod [SSH]"
    finally:
        window.close()
        app.processEvents()


def test_preset_change_during_startup_repaints_the_new_page(monkeypatch, tmp_path) -> None:
    pytest.importorskip("PyQt6")
    from PyQt6.QtCore import QEvent, QObject
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QLineEdit

    from remote_ops_workspace.gui import create_main_window

    class PaintCounter(QObject):
        paints = 0

        def eventFilter(self, watched, event):  # noqa: N802
            if event.type() == QEvent.Type.Paint:
                self.paints += 1
            return False

    monkeypatch.setenv("QT_QPA_PLATFORM", os.environ.get("QT_QPA_PLATFORM", "offscreen"))
    monkeypatch.setenv("ROW_HOME", str(tmp_path / "row-home"))
    app, window = create_main_window(["startup-repaint"], show=True)
    try:
        # Select a preset before delivering startup's queued currentChanged work.
        window.set_design_preset("mremoteng")
        app.processEvents()
        search = window.mremoteng_document_filter
        assert isinstance(search, QLineEdit)
        assert window.tabs.updatesEnabled() and search.updatesEnabled()
        events = PaintCounter()
        search.installEventFilter(events)
        QTest.keyClicks(search, "Ops")
        search.update()
        QTest.qWait(50)
        assert search.text() == "Ops" and events.paints > 0
        search.removeEventFilter(events)

        # An explicitly disabled page retains that setting across the preset.
        window.tabs.setUpdatesEnabled(False)
        window.set_design_preset("native")
        app.processEvents()
        assert not window.tabs.updatesEnabled()
        window.tabs.setUpdatesEnabled(True)
    finally:
        window.close()
        app.processEvents()

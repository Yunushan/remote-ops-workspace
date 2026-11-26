from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from remote_ops_workspace.models import Profile


@pytest.fixture
def gui_window(monkeypatch, tmp_path):
    if "QT_QPA_PLATFORM" not in os.environ:
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("ROW_HOME", str(tmp_path / "row-home"))
    pytest.importorskip("PyQt6")
    from remote_ops_workspace.gui import create_main_window

    app, window = create_main_window(
        ["gui-sidebar-rail-edges"],
        show=False,
        preview_samples=False,
    )
    window.resize(1180, 760)
    window.show()
    app.processEvents()
    yield app, window
    window.close()
    app.processEvents()


def test_sidebar_resize_memory_toggle_and_profile_label_edges(
    gui_window,
    monkeypatch,
) -> None:
    app, window = gui_window
    monkeypatch.setattr(window, "current_design_id", lambda: "native")
    monkeypatch.setattr(window, "current_design_is_moba", lambda: False)

    window._setting_root_splitter_sizes = True
    window.remember_user_sidebar_width(300, 1)
    window._setting_root_splitter_sizes = False
    window.remember_user_sidebar_width(300, 2)

    window.left_panel.setVisible(False)
    window.remember_user_sidebar_width(300, 1)
    window.left_panel.setVisible(True)
    window._sidebar_width_by_design.clear()
    real_splitter = window.root_splitter

    class _NarrowSplitter:
        @staticmethod
        def sizes():
            return [100, 900]

        @staticmethod
        def setProperty(_name: str, _value) -> None:  # noqa: N802
            raise AssertionError("a rejected width must not be persisted")

    window.root_splitter = _NarrowSplitter()
    window.remember_user_sidebar_width(100, 1)
    assert "native" not in window._sidebar_width_by_design
    window.root_splitter = real_splitter

    window.root_splitter.setSizes([340, 660])
    app.processEvents()
    window.remember_user_sidebar_width(340, 1)
    remembered = window._sidebar_width_by_design["native"]
    assert remembered >= window.sidebar_minimum_width_for_design("native")
    assert window.root_splitter.property("rememberedSidebarWidth") == remembered

    window.set_root_sidebar_width(360)
    assert window.root_splitter.property("userResizableSidebar") is True
    window.toggle_moba_session_panel()
    assert "collapsed" in window.statusBar().currentMessage()

    invalid_index = window.design_select.findData("invalid-preset")
    if invalid_index < 0:
        window.design_select.addItem("Invalid", "invalid-preset")
        invalid_index = window.design_select.findData("invalid-preset")
    window.design_select.blockSignals(True)
    window.design_select.setCurrentIndex(invalid_index)
    window.design_select.blockSignals(False)
    window.toggle_moba_session_panel()
    assert "restored" in window.statusBar().currentMessage()

    native_index = window.design_select.findData("native")
    window.design_select.blockSignals(True)
    window.design_select.setCurrentIndex(native_index)
    window.design_select.blockSignals(False)
    window.toggle_moba_session_panel()
    window.toggle_moba_session_panel()
    assert "restored" in window.statusBar().currentMessage()

    window.update_profile_tree_indentation(280)
    assert window.profile_list.indentation() == 11
    window.update_profile_tree_indentation(340)
    assert window.profile_list.indentation() == 13
    window.update_profile_tree_indentation(420)
    assert window.profile_list.indentation() == 15
    monkeypatch.setattr(window, "current_design_is_moba", lambda: True)
    window.update_profile_tree_indentation(200)
    assert window.profile_list.indentation() > 0

    ssh = Profile(name="label-edge", protocol="ssh", host="label.example.invalid")
    sftp = Profile(name="sftp-edge", protocol="sftp", host="sftp.example.invalid")
    rdp = Profile(name="rdp-edge", protocol="rdp", host="rdp.example.invalid")
    expected_fragments = {
        "securecrt": "SSH2",
        "remmina": "RDP -",
        "mremoteng": "[RDP]",
        "mobaxterm": "label.example.invalid",
        "native": "label-edge",
    }
    for design_id, fragment in expected_fragments.items():
        monkeypatch.setattr(
            window,
            "current_design_id",
            lambda value=design_id: value,
        )
        profile = ssh if design_id in {"securecrt", "mobaxterm", "native"} else rdp
        assert fragment in window.profile_tab_label(profile)
    monkeypatch.setattr(window, "current_design_id", lambda: "remmina")
    assert window.profile_tab_label(sftp) == sftp.name


def test_moba_favorites_track_saved_tags_through_a_tree_refresh(gui_window) -> None:
    from PyQt6.QtCore import Qt

    _app, window = gui_window
    window.set_design_preset("mobaxterm")
    previous = Profile(name="previous", protocol="ssh", host="previous.invalid", tags=["Starred"])
    current = Profile(name="current", protocol="ssh", host="current.invalid")
    other = Profile(name="other", protocol="ssh", host="other.invalid")
    window.store.save([previous, current, other])
    window.refresh_profiles()
    buttons = {button.property("mobaRailRole"): button for button in window.moba_rail_buttons}

    def visible_profiles():
        return {
            item.data(0, Qt.ItemDataRole.UserRole)
            for item in window.iter_profile_tree_items()
            if item.data(0, Qt.ItemDataRole.UserRole) and window.profile_tree_item_is_visible(item)
        }

    def refresh_from_menu():
        menu = window.build_profile_context_menu(window.profile_list.currentItem())
        next(action for action in menu.actions() if action.text() == "Refresh profiles").trigger()

    def favorites_menu_action():
        menu = window.build_moba_rail_context_menu()
        return next(action for action in menu.actions() if action.text() == "Favorites")

    star = buttons["favorites"]
    star.click()
    assert visible_profiles() == {"previous", "current", "other"}
    assert star.isChecked()
    assert not favorites_menu_action().isChecked()
    favorites_menu_action().trigger()
    assert visible_profiles() == {"previous"}
    assert window.selected_profile_name() == "previous"
    previous.tags = []
    current.tags = ["Favorites"]
    window.store.save([previous, current, other])
    refresh_from_menu()
    assert visible_profiles() == {"current"}
    assert window.selected_profile_name() is None
    assert favorites_menu_action().isChecked()

    window.set_design_preset("mremoteng")
    assert visible_profiles() == {"previous", "current", "other"}
    window.set_design_preset("mobaxterm")
    assert visible_profiles() == {"current"}
    assert favorites_menu_action().isChecked()

    window.select_profile("current")
    refresh_from_menu()
    assert window.selected_profile_name() == "current"
    current.tags = []
    window.store.save([previous, current, other])
    refresh_from_menu()
    assert visible_profiles() == set()
    assert window.selected_profile_name() is None

    favorites_menu_action().trigger()
    assert visible_profiles() == {"previous", "current", "other"}
    assert not favorites_menu_action().isChecked()
    assert buttons["sessions"].isChecked()
    favorites_menu_action().trigger()
    star.click()
    assert visible_profiles() == {"previous", "current", "other"}
    assert not favorites_menu_action().isChecked()
    assert star.isChecked()


def test_moba_workflow_and_sftp_rail_routing_edges(
    gui_window,
    monkeypatch,
) -> None:
    from PyQt6.QtWidgets import QFrame

    _app, window = gui_window
    ssh = Profile(
        name="rail-ssh",
        protocol="ssh",
        host="rail.example.invalid",
        options={"x11": "trusted", "agent_forward": "true"},
    )
    rdp = Profile(
        name="rail-rdp",
        protocol="rdp",
        host="rdp.example.invalid",
    )
    workflows: list[tuple[str, object]] = []
    monkeypatch.setattr(
        window,
        "show_workflow_dialog",
        lambda title, _subtitle, rows, _detail, **_kwargs: workflows.append(
            (title, rows)
        ),
    )
    selected: list[Profile | None] = [None]
    monkeypatch.setattr(
        window,
        "selected_profile_for_workflow",
        lambda: selected[0],
    )

    window.show_moba_tunneling_status()
    window.show_moba_packages_dialog()
    selected[0] = ssh
    window.show_moba_tunneling_status()
    window.show_moba_packages_dialog()
    assert [title for title, _rows in workflows].count("Tunneling") == 2
    assert [title for title, _rows in workflows].count("Packages") == 2

    class _Store:
        profiles: list[Profile] = []

        def load(self):
            return list(self.profiles)

    window.store = _Store()
    favorites: list[set[str] | None] = []
    selections: list[str] = []
    monkeypatch.setattr(window, "show_moba_profile_tree", lambda **_kwargs: None)
    monkeypatch.setattr(window, "filter_profile_tree_names", favorites.append)
    monkeypatch.setattr(window, "select_profile", selections.append)
    window.show_moba_sessions_rail()
    window.show_moba_favorites_rail()
    window.store.profiles = [
        Profile(
            name="favorite-edge",
            protocol="ssh",
            host="favorite.example.invalid",
            tags=["Starred"],
        )
    ]
    window.show_moba_favorites_rail()
    assert favorites[-1] == {"favorite-edge"}
    assert selections == ["favorite-edge"]

    original_dock = getattr(window, "moba_connected_dock", None)
    monkeypatch.setattr(window, "moba_connected_state_in_widget", lambda _widget: None)
    window.moba_connected_dock = None
    selected[0] = None
    window.show_moba_sftp_rail()
    assert workflows[-1][0] == "SFTP browser"

    opened_files: list[str] = []
    monkeypatch.setattr(window, "open_files_selected", lambda: opened_files.append("files"))
    selected[0] = ssh
    window.show_moba_sftp_rail()
    assert opened_files == ["files"]
    selected[0] = rdp
    window.show_moba_sftp_rail()
    assert workflows[-1][0] == "SFTP browser"

    dock = QFrame()
    window.moba_left_stack.addWidget(dock)
    window.moba_connected_dock = dock
    window.show_moba_sftp_rail()
    assert window.moba_left_stack.currentWidget() is dock

    state = SimpleNamespace(
        target="operator@rail.example.invalid:22",
        remote_path="/srv/app",
    )
    rail_calls: list[str] = []
    dock_calls: list[object] = []
    status_calls: list[str] = []
    window.moba_connected_dock = None
    monkeypatch.setattr(
        window,
        "moba_connected_state_in_widget",
        lambda _widget: None,
    )
    monkeypatch.setattr(window, "show_moba_sftp_rail", lambda: rail_calls.append("rail"))
    window.open_moba_sftp_same_parameters(-1)
    assert rail_calls == ["rail"]

    monkeypatch.setattr(
        window,
        "moba_connected_state_in_widget",
        lambda _widget: state,
    )
    monkeypatch.setattr(
        window,
        "show_moba_connected_dock",
        lambda value: dock_calls.append(value),
    )
    monkeypatch.setattr(
        window,
        "show_transient_status_message",
        status_calls.append,
    )
    window.open_moba_sftp_same_parameters(-1)
    assert dock_calls == [state]
    assert rail_calls == ["rail", "rail"]
    assert "operator@rail.example.invalid" in status_calls[-1]
    window.moba_connected_dock = original_dock

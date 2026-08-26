from __future__ import annotations

import os

import pytest

from remote_ops_workspace.layouts import Layout, LayoutPane
from remote_ops_workspace.models import Profile
from remote_ops_workspace.terminal import TerminalPanePlan


def _set_closure_value(monkeypatch, function, name: str, value) -> None:
    index = function.__code__.co_freevars.index(name)
    closure = function.__closure__
    assert closure is not None
    monkeypatch.setattr(closure[index], "cell_contents", value)


def _closure_value(function, name: str):
    index = function.__code__.co_freevars.index(name)
    closure = function.__closure__
    assert closure is not None
    return closure[index].cell_contents


@pytest.fixture
def gui_window(monkeypatch, tmp_path):
    if "QT_QPA_PLATFORM" not in os.environ:
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("ROW_HOME", str(tmp_path / "row-home"))
    pytest.importorskip("PyQt6")
    from remote_ops_workspace.gui import create_main_window

    app, window = create_main_window(
        ["gui-layout-workflow-edges"],
        show=False,
        preview_samples=False,
    )
    window.resize(1100, 760)
    window.show()
    app.processEvents()
    yield app, window
    window.close()
    app.processEvents()


def test_layout_create_edit_remove_save_and_open_workflow_edges(
    gui_window,
    monkeypatch,
) -> None:
    from PyQt6.QtWidgets import QDialog, QMessageBox, QWidget

    from remote_ops_workspace import gui

    _app, window = gui_window
    original = Layout(
        name="existing",
        panes=[LayoutPane(command="echo existing")],
    )
    created = Layout(
        name="created",
        orientation="horizontal",
        panes=[
            LayoutPane(command="echo left"),
            LayoutPane(command="echo right"),
        ],
    )
    renamed = Layout(
        name="renamed",
        panes=[LayoutPane(command="echo renamed")],
    )

    class _LayoutStore:
        def __init__(self) -> None:
            self.layouts = [original]
            self.get_value: object = original
            self.add_calls: list[str] = []
            self.remove_calls: list[str] = []
            self.save_calls: list[list[str]] = []
            self.fail_next_add = False
            self.fail_remove = False

        def add(self, layout: Layout) -> None:
            self.add_calls.append(layout.name)
            if self.fail_next_add:
                self.fail_next_add = False
                raise ValueError("layout already exists")

        def get(self, _name: str):
            if isinstance(self.get_value, Exception):
                raise self.get_value
            return self.get_value

        def remove(self, name: str) -> None:
            self.remove_calls.append(name)
            if self.fail_remove:
                raise KeyError(name)

        def load(self):
            return list(self.layouts)

        def save(self, layouts) -> None:
            self.layouts = list(layouts)
            self.save_calls.append([layout.name for layout in self.layouts])

    store = _LayoutStore()
    window.layout_store = store
    refreshes: list[str] = []
    monkeypatch.setattr(window, "refresh_layouts", lambda: refreshes.append("refresh"))

    class _Dialog:
        def __init__(self, results, layouts) -> None:
            self.results = iter(results)
            self.layouts = iter(layouts)
            self.validation_errors: list[str] = []

        def exec(self):
            return next(self.results)

        def workspace_layout(self):
            value = next(self.layouts)
            if isinstance(value, Exception):
                raise value
            return value

        def show_validation_error(self, message: str) -> None:
            self.validation_errors.append(message)

    dialogs: list[_Dialog] = []

    def dialog_factory(*_args, **_kwargs):
        return dialogs.pop(0)

    _set_closure_value(
        monkeypatch,
        type(window).create_layout,
        "LayoutDialog",
        dialog_factory,
    )
    create_dialog = _Dialog(
        [QDialog.DialogCode.Accepted, QDialog.DialogCode.Accepted],
        [original, created],
    )
    dialogs.append(create_dialog)
    store.fail_next_add = True
    window.create_layout()
    assert create_dialog.validation_errors == ["layout already exists"]
    assert store.add_calls == ["existing", "created"]

    messages: list[str] = []
    remove_answers = iter(
        [
            QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
            QMessageBox.StandardButton.Yes,
        ]
    )

    def fake_message_box(_parent, _icon, title, text, **_kwargs):
        messages.append(str(text))
        if title == "Remove layout":
            return next(remove_answers)
        return QMessageBox.StandardButton.Ok

    _set_closure_value(
        monkeypatch,
        type(window).edit_selected_layout,
        "_literal_message_box",
        fake_message_box,
    )

    window.layout_select.clear()
    window.edit_selected_layout()
    assert "No saved layout" in messages[-1]
    window.layout_select.addItem("missing")
    store.get_value = KeyError("missing")
    window.edit_selected_layout()
    assert "missing" in messages[-1]

    window.layout_select.clear()
    window.layout_select.addItem(original.name)
    store.get_value = original
    edit_dialog = _Dialog(
        [QDialog.DialogCode.Accepted, QDialog.DialogCode.Accepted],
        [renamed, renamed],
    )
    dialogs.append(edit_dialog)
    save_attempts: list[tuple[str, str]] = []

    def save_with_retry(layout: Layout, original_name: str) -> None:
        save_attempts.append((layout.name, original_name))
        if len(save_attempts) == 1:
            raise ValueError("invalid edit")

    original_save_layout = window.save_layout
    monkeypatch.setattr(window, "save_layout", save_with_retry)
    window.edit_selected_layout()
    assert edit_dialog.validation_errors == ["invalid edit"]
    assert save_attempts == [("renamed", "existing"), ("renamed", "existing")]

    rejected_edit_dialog = _Dialog([QDialog.DialogCode.Rejected], [])
    dialogs.append(rejected_edit_dialog)
    window.edit_selected_layout()
    assert save_attempts == [("renamed", "existing"), ("renamed", "existing")]
    monkeypatch.setattr(window, "save_layout", original_save_layout)

    window.layout_select.clear()
    window.remove_selected_layout()
    window.layout_select.addItem(original.name)
    window.remove_selected_layout()
    assert store.remove_calls == []
    window.remove_selected_layout()
    assert store.remove_calls == [original.name]
    store.fail_remove = True
    window.remove_selected_layout()
    assert store.remove_calls == [original.name, original.name]

    store.fail_remove = False
    store.layouts = [
        original,
        Layout(name="taken", panes=[LayoutPane(command="echo taken")]),
    ]
    with pytest.raises(ValueError, match="layout already exists"):
        window.save_layout(
            Layout(name="taken", panes=[LayoutPane(command="echo duplicate")]),
            original_name=original.name,
        )
    retargets: list[tuple[str, str]] = []
    monkeypatch.setattr(
        window,
        "retarget_open_layout_instances",
        lambda old, new: retargets.append((old, new)),
    )
    window.save_layout(original, original_name=original.name)
    window.save_layout(renamed, original_name=original.name)
    assert retargets == [(original.name, renamed.name)]
    assert store.save_calls

    window.layout_select.clear()
    window.open_selected_layout()
    window.layout_select.addItem("missing")
    store.get_value = KeyError("missing")
    window.open_selected_layout()

    window.layout_select.clear()
    window.layout_select.addItem(created.name)
    store.get_value = created
    profiles = [
        Profile(name="left", protocol="custom", command="echo left"),
        Profile(name="right", protocol="custom", command="echo right"),
    ]
    plans = [
        TerminalPanePlan(title="left", command=["echo", "left"], source="test"),
        TerminalPanePlan(title="right", command=["echo", "right"], source="test"),
    ]
    layout_widget = QWidget()
    bindings: list[str] = []
    remembered: list[str] = []
    started: list[tuple[object, int]] = []
    original_layout_launch_profiles = window.layout_launch_profiles
    original_build_layout_terminal_plans = gui.build_layout_terminal_plans
    original_layout_widget = window.layout_widget
    original_bind_layout_resize_persistence = window.bind_layout_resize_persistence
    original_remember_terminal_plan = window.remember_terminal_plan
    original_add_workspace_tab = window.add_workspace_tab
    original_update_session_status = window.update_session_status
    original_terminal_panes_in = window.terminal_panes_in
    original_start_terminal_pane = window.start_terminal_pane_when_active
    monkeypatch.setattr(window, "layout_launch_profiles", lambda _layout: profiles)
    monkeypatch.setattr(gui, "build_layout_terminal_plans", lambda *_args: plans)
    monkeypatch.setattr(
        window,
        "layout_widget",
        lambda *_args: layout_widget,
    )
    monkeypatch.setattr(
        window,
        "bind_layout_resize_persistence",
        lambda name, _widget: bindings.append(name),
    )
    monkeypatch.setattr(
        window,
        "remember_terminal_plan",
        lambda plan, **_kwargs: remembered.append(plan.title),
    )
    monkeypatch.setattr(window, "add_workspace_tab", lambda *_args, **_kwargs: 7)
    monkeypatch.setattr(window, "update_session_status", lambda: None)
    monkeypatch.setattr(window, "terminal_panes_in", lambda _widget: ["pane"])
    monkeypatch.setattr(
        window,
        "start_terminal_pane_when_active",
        lambda pane, index: started.append((pane, index)),
    )
    window.open_selected_layout()
    assert bindings == [created.name]
    assert remembered == ["left", "right"]
    assert started == [("pane", 7)]
    monkeypatch.setattr(
        window,
        "layout_launch_profiles",
        original_layout_launch_profiles,
    )
    monkeypatch.setattr(
        gui,
        "build_layout_terminal_plans",
        original_build_layout_terminal_plans,
    )
    monkeypatch.setattr(window, "layout_widget", original_layout_widget)
    monkeypatch.setattr(
        window,
        "bind_layout_resize_persistence",
        original_bind_layout_resize_persistence,
    )
    monkeypatch.setattr(
        window,
        "remember_terminal_plan",
        original_remember_terminal_plan,
    )
    monkeypatch.setattr(window, "add_workspace_tab", original_add_workspace_tab)
    monkeypatch.setattr(
        window,
        "update_session_status",
        original_update_session_status,
    )
    monkeypatch.setattr(window, "terminal_panes_in", original_terminal_panes_in)
    monkeypatch.setattr(
        window,
        "start_terminal_pane_when_active",
        original_start_terminal_pane,
    )

    actual_layout = Layout(
        name="launch-profiles",
        panes=[
            LayoutPane(profile="saved-profile"),
            LayoutPane(command="echo generated"),
        ],
    )
    saved_profile = Profile(
        name="saved-profile",
        protocol="ssh",
        host="saved.example.invalid",
    )

    class _ProfileStore:
        @staticmethod
        def get(name: str):
            assert name == saved_profile.name
            return saved_profile

    window.store = _ProfileStore()
    allowed: list[str] = []
    monkeypatch.setattr(
        gui,
        "assert_profile_launch_allowed",
        lambda profile, **_kwargs: allowed.append(profile.name),
    )
    launched_profiles = type(window).layout_launch_profiles(window, actual_layout)
    assert launched_profiles[0] is saved_profile
    assert launched_profiles[1].group == "layout"
    assert allowed == ["saved-profile", "layout-launch-profiles-2"]


def test_layout_resize_persistence_edges(gui_window) -> None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QSplitter, QWidget

    app, window = gui_window
    window.persist_layout_resize_state("missing", QWidget())

    splitter = QSplitter(Qt.Orientation.Horizontal)
    splitter.addWidget(QWidget())
    splitter.addWidget(QWidget())
    splitter.resize(700, 300)
    splitter.setSizes([250, 450])
    splitter.show()
    app.processEvents()
    sizes = [
        [max(1, int(size)) for size in current.sizes()]
        for current in window.layout_splitters(splitter)
    ]
    persisted = Layout(
        name="persisted",
        orientation="horizontal",
        panes=[
            LayoutPane(command="echo left"),
            LayoutPane(command="echo right"),
        ],
        splitter_sizes=[list(value) for value in sizes],
    )

    class _Store:
        def __init__(self) -> None:
            self.layouts = [persisted]
            self.saved: list[list[list[int]]] = []

        def load(self):
            return self.layouts

        def save(self, layouts) -> None:
            self.saved.append(
                [list(value) for value in layouts[0].splitter_sizes]
            )

    store = _Store()
    window.layout_store = store
    window.persist_layout_resize_state(persisted.name, splitter)
    assert store.saved == []
    persisted.splitter_sizes = []
    window.persist_layout_resize_state(persisted.name, splitter)
    assert store.saved == [sizes]
    window.persist_layout_resize_state("not-present", splitter)
    assert store.saved == [sizes]
    splitter.close()


def test_layout_dialog_validation_and_splitter_preservation_edges(gui_window) -> None:
    from PyQt6.QtWidgets import QDialog

    app, window = gui_window
    dialog_type = _closure_value(type(window).create_layout, "LayoutDialog")
    original = Layout(
        name="dialog-layout",
        orientation="horizontal",
        panes=[
            LayoutPane(command="echo left", title="Left"),
            LayoutPane(command="echo right", title="Right"),
        ],
        splitter_sizes=[[260, 540]],
    )
    dialog = dialog_type(original, window)
    dialog.show()
    app.processEvents()

    dialog.name.clear()
    dialog.submit()
    assert dialog.result() == QDialog.DialogCode.Rejected
    assert dialog._validated_layout is None
    assert "layout name" in dialog.validation_error.text()
    assert dialog.focusWidget() is dialog.name

    dialog.show_validation_error("layout orientation is unsupported")
    assert dialog.focusWidget() is dialog.orientation
    dialog.show_validation_error("layout requires at least one pane")
    assert dialog.focusWidget() is dialog.panes

    dialog.name.setText("dialog-layout-updated")
    dialog.orientation.setCurrentText("horizontal")
    dialog.panes.setPlainText(
        "command:echo updated-left | Updated left\n"
        "command:echo updated-right | Updated right"
    )
    parsed = dialog.parsed_layout()
    assert parsed.splitter_sizes == [[260, 540]]
    assert dialog.workspace_layout().splitter_sizes == [[260, 540]]
    dialog.submit()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert dialog.workspace_layout().name == "dialog-layout-updated"

    fresh = dialog_type(parent=window)
    fresh.name.setText("fresh-layout")
    fresh.orientation.setCurrentText("vertical")
    fresh.panes.setPlainText("command:echo fresh")
    assert fresh.parsed_layout().splitter_sizes == []
    fresh.deleteLater()
    dialog.deleteLater()

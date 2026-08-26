from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from remote_ops_workspace.layouts import Layout, LayoutPane
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
        ["gui-split-layout-edges"],
        show=False,
        preview_samples=False,
    )
    window.resize(1180, 760)
    window.show()
    app.processEvents()
    yield app, window
    window.close()
    app.processEvents()


def _pane(window, title: str = "pane", *, profile: Profile | None = None):
    return window.new_terminal_pane(
        TerminalPanePlan(
            title=title,
            command=["ssh", f"{title}.example.invalid"],
            source="test",
        ),
        profile=profile,
        autostart=False,
    )


def test_add_split_covers_connected_existing_wrapped_and_fallback_tabs(
    gui_window,
    monkeypatch,
) -> None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QSplitter

    app, window = gui_window
    started: list[tuple[object, int]] = []
    monkeypatch.setattr(
        window,
        "start_terminal_pane_when_active",
        lambda pane, index: started.append((pane, index)),
    )

    design_index = window.design_select.findData("mobaxterm")
    assert design_index >= 0
    window.design_select.setCurrentIndex(design_index)
    profile = Profile(
        name="split-edge",
        protocol="ssh",
        host="split-edge.example.invalid",
        username="operator",
    )
    panel = window.open_moba_connected_session_tab(
        profile,
        TerminalPanePlan(title="split-edge", command=[], source="test"),
    )
    app.processEvents()
    window.add_split("horizontal")
    window.add_split("vertical")
    assert panel.terminal_splitter.count() == 3
    assert panel.terminal_splitter.orientation() == Qt.Orientation.Vertical
    assert all(
        not panel.terminal_splitter.isCollapsible(index)
        for index in range(panel.terminal_splitter.count())
    )

    existing = QSplitter(Qt.Orientation.Horizontal)
    existing.addWidget(_pane(window, "existing"))
    existing_index = window.add_workspace_tab(existing, "Existing split", role="split")
    window.set_workspace_tab_index(existing_index)
    window.add_split("vertical")
    assert existing.orientation() == Qt.Orientation.Vertical
    assert existing.count() == 2
    assert window.tabs.tabText(existing_index) == "Split V 2"

    terminal = _pane(window, "wrapped")
    terminal_index = window.add_workspace_tab(terminal, "Wrapped", role="terminal")
    window.set_workspace_tab_index(terminal_index)
    window.add_split("horizontal")
    wrapped = window.tabs.currentWidget()
    assert isinstance(wrapped, QSplitter)
    assert wrapped.count() == 2
    assert window.tab_role(window.tabs.currentIndex()) == "split"

    monkeypatch.setattr(type(window), "active_terminal_pane", lambda _self: None)
    neutral_index = window.find_tab_by_role("home")
    assert neutral_index >= 0
    window.set_workspace_tab_index(neutral_index)
    window.add_split("vertical")
    fallback = window.tabs.currentWidget()
    assert isinstance(fallback, QSplitter)
    assert fallback.count() == 2
    assert window.tab_role(window.tabs.currentIndex()) == "split"

    active = _pane(window, "active-fallback", profile=profile)
    monkeypatch.setattr(
        type(window),
        "active_terminal_pane",
        lambda _self: active,
    )
    window.set_workspace_tab_index(neutral_index)
    window.add_split("horizontal")
    active_fallback = window.tabs.currentWidget()
    assert isinstance(active_fallback, QSplitter)
    assert active_fallback.count() == 2
    assert any(
        pane.plan == active.plan
        for pane in window.terminal_panes_in(active_fallback)
    )
    assert started


def test_duplicate_tab_and_splitter_clone_edges(gui_window, monkeypatch) -> None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QLabel, QSplitter, QWidget

    app, window = gui_window
    monkeypatch.setattr(window, "start_terminal_pane_when_active", lambda *_args: None)
    local_requests: list[str] = []
    monkeypatch.setattr(
        window,
        "open_local_terminal_tab",
        lambda: local_requests.append("local"),
    )

    new_session = window.find_tab_by_role("new-session")
    window.set_workspace_tab_index(new_session)
    window.duplicate_current_tab()
    assert local_requests == ["local"]

    direct = _pane(window, "direct")
    direct_index = window.add_workspace_tab(direct, "Direct", role="terminal")
    window.set_workspace_tab_index(direct_index)
    opened: list[dict[str, object]] = []
    monkeypatch.setattr(
        window,
        "open_terminal_tab",
        lambda plan, **kwargs: opened.append({"plan": plan, **kwargs}),
    )
    window.duplicate_current_tab()
    assert opened[0]["tab_title"] == "Direct copy"

    empty = QWidget()
    empty_index = window.add_workspace_tab(empty, "Empty", role="tool")
    window.set_workspace_tab_index(empty_index)
    window.duplicate_current_tab()
    assert local_requests == ["local", "local"]

    source = QSplitter(Qt.Orientation.Horizontal)
    source.setProperty("savedLayoutName", "saved")
    source.addWidget(_pane(window, "left"))
    nested = QSplitter(Qt.Orientation.Vertical)
    nested.addWidget(_pane(window, "nested"))
    source.addWidget(nested)
    source.setSizes([320, 680])
    assert window.terminal_splitter_clone_supported(source) is True
    clone = window.clone_terminal_splitter(source)
    assert clone.count() == 2
    assert clone.property("savedLayoutName") == "saved"
    assert isinstance(clone.widget(1), QSplitter)
    assert all(not clone.isCollapsible(index) for index in range(clone.count()))

    source_index = window.add_workspace_tab(source, "Clone source", role="layout")
    window.set_workspace_tab_index(source_index)
    before = window.tabs.count()
    window.duplicate_current_tab()
    assert window.tabs.count() == before + 1
    assert window.tab_role(window.tabs.currentIndex()) == "layout"

    unsupported = QSplitter(Qt.Orientation.Horizontal)
    unsupported.addWidget(_pane(window, "supported-child"))
    unsupported.addWidget(QLabel("unsupported"))
    assert window.terminal_splitter_clone_supported(unsupported) is False
    with pytest.raises(RuntimeError, match="unsupported child"):
        window.clone_terminal_splitter(unsupported)
    unsupported_index = window.add_workspace_tab(
        unsupported,
        "Fallback clone",
        role="split",
    )
    window.set_workspace_tab_index(unsupported_index)
    window.duplicate_current_tab()
    fallback_clone = window.tabs.currentWidget()
    assert isinstance(fallback_clone, QSplitter)
    assert fallback_clone.count() == 1

    design_index = window.design_select.findData("mobaxterm")
    window.design_select.setCurrentIndex(design_index)
    profile = Profile(
        name="duplicate-connected",
        protocol="ssh",
        host="duplicate.example.invalid",
        username="operator",
    )
    panel = window.open_moba_connected_session_tab(
        profile,
        TerminalPanePlan(title="duplicate", command=[], source="test"),
    )
    panel.add_terminal_split(_pane(window, "second", profile=profile), Qt.Orientation.Horizontal)
    app.processEvents()
    window.duplicate_current_tab()
    duplicate = window.tabs.currentWidget()
    assert duplicate is not panel
    assert len(window.terminal_panes_in(duplicate)) == 2
    assert "TAB DUPLICATED" in window.log.toPlainText()

    panel_index = window.tabs.indexOf(panel)
    assert panel_index >= 0
    window.set_workspace_tab_index(panel_index)
    monkeypatch.setattr(window, "moba_connected_state_in_widget", lambda _widget: None)
    before = window.tabs.count()
    window.duplicate_current_tab()
    assert window.tabs.count() == before + 1
    assert isinstance(window.tabs.currentWidget(), QSplitter)


def test_layout_widget_resize_restore_retarget_and_dialog_construction(
    gui_window,
) -> None:
    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtWidgets import QApplication, QDialog, QSplitter

    app, window = gui_window
    profile = Profile(
        name="layout-edge",
        protocol="custom",
        command="echo layout",
    )
    plans = [
        TerminalPanePlan(title=f"layout-{index}", command=["echo", str(index)], source="test")
        for index in range(4)
    ]
    profiles = [profile] * 4

    solo = Layout(name="solo", panes=[LayoutPane(command="echo one")])
    solo_widget = window.layout_widget(solo, plans[:1], profiles[:1])
    assert solo_widget.objectName() == "terminalPane"

    vertical = Layout(
        name="vertical",
        orientation="vertical",
        panes=[LayoutPane(command="echo one"), LayoutPane(command="echo two")],
        splitter_sizes=[[300, 700]],
    )
    vertical_widget = window.layout_widget(vertical, plans[:2], profiles[:2])
    assert isinstance(vertical_widget, QSplitter)
    assert vertical_widget.orientation() == Qt.Orientation.Vertical
    window.restore_layout_splitter_sizes(vertical_widget, [[0, 100]])

    horizontal = Layout(
        name="horizontal",
        orientation="horizontal",
        panes=[LayoutPane(command="echo one"), LayoutPane(command="echo two")],
        splitter_sizes=[[400, 600]],
    )
    horizontal_widget = window.layout_widget(horizontal, plans[:2], profiles[:2])
    assert isinstance(horizontal_widget, QSplitter)
    assert horizontal_widget.orientation() == Qt.Orientation.Horizontal

    grid = Layout(
        name="grid",
        orientation="grid",
        panes=[LayoutPane(command=f"echo {index}") for index in range(4)],
    )
    grid_widget = window.layout_widget(grid, plans, profiles)
    splitters = window.layout_splitters(grid_widget)
    assert len(splitters) == 3
    assert window.layout_splitters(solo_widget) == []
    window.restore_layout_splitter_sizes(solo_widget, [])
    window.restore_layout_splitter_sizes(grid_widget, [[1, 2]])
    window.restore_layout_splitter_sizes(
        grid_widget,
        [[500, 500], [200, 800], [700, 300]],
    )
    assert all(
        not splitter.isCollapsible(index)
        for splitter in splitters
        for index in range(splitter.count())
    )

    grid_widget.setProperty("savedLayoutName", "grid")
    tab_index = window.add_workspace_tab(grid_widget, "grid · live", role="layout")
    window.set_literal_tab_tooltip(tab_index, "grid: active")
    window.retarget_open_layout_instances("grid", "renamed")
    assert grid_widget.property("savedLayoutName") == "renamed"
    assert window.tabs.tabText(tab_index) == "renamed · live"
    assert window.literal_tab_tooltip(tab_index) == "renamed: active"
    window.retarget_open_layout_instances("missing", "ignored")

    grid_widget.setProperty("savedLayoutName", "renamed")
    window.tabs.setTabText(tab_index, "unrelated title")
    window.set_literal_tab_tooltip(tab_index, "renamed")
    window.set_literal_tab_tooltip(
        tab_index,
        "renamed: active",
        update_base=False,
    )
    window.retarget_open_layout_instances("renamed", "final")
    assert window.tabs.tabText(tab_index) == "unrelated title"
    assert window.literal_tab_tooltip(tab_index) == "final: active"

    grid_widget.setProperty("savedLayoutName", "final")
    window.tabs.setTabText(tab_index, "final custom suffix")
    window.retarget_open_layout_instances("final", "ignored")
    assert window.tabs.tabText(tab_index) == "final custom suffix"

    retarget = type(window).retarget_open_layout_instances
    missing_root_owner = SimpleNamespace(
        tabs=SimpleNamespace(
            count=lambda: 1,
            widget=lambda _index: None,
        )
    )
    retarget(missing_root_owner, "missing", "ignored")

    observed: list[object] = []

    def reject_layout_dialog() -> None:
        dialog = QApplication.activeModalWidget()
        observed.append(dialog)
        assert isinstance(dialog, QDialog)
        dialog.reject()

    QTimer.singleShot(0, reject_layout_dialog)
    window.create_layout()
    app.processEvents()
    assert observed

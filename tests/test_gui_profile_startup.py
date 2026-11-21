from __future__ import annotations

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


@pytest.mark.parametrize("preset", ["native", "securecrt", "termius", "remmina"])
def test_home_shows_real_connections_and_filters_without_launching(clean_gui_window, preset) -> None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QFrame, QLabel, QLineEdit, QWidget

    from remote_ops_workspace.models import Profile

    app, window = clean_gui_window
    window.store.save([
        Profile(name="North server", protocol="ssh", host="north.example.invalid"),
        Profile(name="South server", protocol="rdp", host="south.example.invalid"),
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
        assert {profile.name for profile in window.store.load(resolve=False)}
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

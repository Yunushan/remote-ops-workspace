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

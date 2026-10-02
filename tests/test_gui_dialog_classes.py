from __future__ import annotations

import os
from dataclasses import replace

import pytest

from remote_ops_workspace.layouts import Layout, LayoutPane
from remote_ops_workspace.models import Profile
from remote_ops_workspace.profile_importers import ProfileImportResult


@pytest.fixture
def gui_window(monkeypatch, tmp_path):
    pytest.importorskip("PyQt6")
    if "QT_QPA_PLATFORM" not in os.environ:
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("ROW_HOME", str(tmp_path / "row-home"))
    from remote_ops_workspace.gui import create_main_window

    app, window = create_main_window(["gui-dialog-classes"], show=False)
    yield app, window
    window.close()
    app.processEvents()


@pytest.mark.parametrize("protocol", ["ssh1", "sshv1"])
def test_legacy_protocol_choices_explain_required_security_opt_ins(gui_window, protocol):
    from PyQt6.QtCore import Qt

    _app, window = gui_window
    dialog = window.create_profile_dialog()
    try:
        choices = dialog.fields["protocol"]
        index = choices.findText(protocol)
        assert index >= 0
        warning = choices.itemData(index, Qt.ItemDataRole.ToolTipRole)
        for required in (
            "allow_insecure_sshv1=true",
            "legacy_target=windows-xp-32",
            "windows-xp-64",
            "allow_legacy_crypto=true",
            "isolated legacy systems",
        ):
            assert required in warning
    finally:
        dialog.deleteLater()


def test_window_factories_keep_module_class_identity_across_windows(gui_window) -> None:
    from remote_ops_workspace.gui import create_main_window
    from remote_ops_workspace.gui_dialogs import (
        LayoutDialog,
        ProfileDialog,
        ProfileImportPreviewDialog,
    )

    app, first = gui_window
    _app, second = create_main_window(["gui-dialog-classes-second"], show=False)
    result = ProfileImportResult("row", [Profile(name="host", protocol="ssh", host="example.invalid")])
    try:
        for window in (first, second):
            dialogs = [
                window.create_profile_dialog(),
                window.create_layout_dialog(),
                window.create_profile_import_preview_dialog("profiles.json", result),
            ]
            assert [type(dialog) for dialog in dialogs] == [ProfileDialog, LayoutDialog, ProfileImportPreviewDialog]
            assert all(dialog.parentWidget() is window for dialog in dialogs)
            for dialog in dialogs:
                dialog.deleteLater()
    finally:
        second.close()
        app.processEvents()


@pytest.mark.parametrize("with_warnings", [False, True])
def test_direct_dialogs_use_injected_screen_services_and_literal_preview(gui_window, with_warnings) -> None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QLabel, QTextEdit, QTreeWidget

    from remote_ops_workspace.gui_dialogs import (
        LayoutDialog,
        ProfileDialog,
        ProfileImportPreviewDialog,
    )

    app, window = gui_window
    factory_dialog = window.create_profile_dialog()
    sizes = []
    clamped = []

    def size_dialog(dialog, parent, **bounds):
        sizes.append((dialog, parent, bounds))
        dialog.resize(bounds["maximum_width"], bounds["maximum_height"])

    services = replace(factory_dialog.services, size_for_screen=size_dialog, clamp_to_screen=clamped.append)
    profile = Profile(name="<b>literal host</b>", protocol="ssh", host="literal.example.invalid")
    layout = Layout(name="two panes", orientation="horizontal", panes=[LayoutPane(command="echo first"), LayoutPane(command="echo second")])
    result = ProfileImportResult("row", [profile], ["<b>literal warning</b>"] if with_warnings else [])
    dialogs = [
        ProfileDialog(profile, window, services=services),
        LayoutDialog(layout, window, services=services),
        ProfileImportPreviewDialog("<b>literal source</b>.json", result, window, services=services),
    ]
    try:
        assert [(parent, bounds["maximum_width"], bounds["maximum_height"]) for _dialog, parent, bounds in sizes] == [
            (window, 560, 720), (window, 560, 660), (window, 660, 480),
        ]
        assert clamped == []
        for dialog in dialogs:
            dialog.show()
            app.processEvents()
        assert clamped == dialogs
        assert dialogs[0].profile() == profile
        assert dialogs[1].workspace_layout() == layout
        preview = dialogs[2]
        label = preview.findChild(QLabel, "profileImportSource")
        assert label is not None
        assert label.textFormat() == Qt.TextFormat.PlainText
        assert "<b>literal source</b>.json" in label.text()
        tree = preview.findChild(QTreeWidget, "profileImportPreview")
        assert tree is not None
        assert tree.topLevelItem(0).text(0) == profile.name
        warnings = preview.findChild(QTextEdit, "profileImportWarnings")
        if with_warnings:
            assert warnings is not None
            assert warnings.toPlainText() == "warning: <b>literal warning</b>"
        else:
            assert warnings is None
    finally:
        for dialog in [factory_dialog, *dialogs]:
            dialog.close()
            dialog.deleteLater()
        app.processEvents()


def test_confirmation_seam_has_safe_default_and_literal_text(gui_window, monkeypatch) -> None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QMessageBox

    _app, window = gui_window
    observed = []
    answers = iter([QMessageBox.StandardButton.No.value, QMessageBox.StandardButton.Yes.value])

    def answer(dialog):
        observed.append((dialog.windowTitle(), dialog.text(), dialog.textFormat(), dialog.standardButton(dialog.defaultButton()), dialog.standardButtons()))
        return next(answers)

    monkeypatch.setattr(QMessageBox, "exec", answer)
    for expected in (False, True):
        assert window.confirm_action("Remove profile", "Remove <b>literal profile</b>?") is expected
    assert observed == [
        ("Remove profile", "Remove <b>literal profile</b>?", Qt.TextFormat.PlainText, QMessageBox.StandardButton.No, QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No),
    ] * 2

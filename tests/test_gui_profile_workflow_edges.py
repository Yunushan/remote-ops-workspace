from __future__ import annotations

import os

import pytest

from remote_ops_workspace.models import Profile
from remote_ops_workspace.profile_importers import ProfileImportResult


def _set_closure_value(monkeypatch, function, name: str, value) -> None:
    index = function.__code__.co_freevars.index(name)
    closure = function.__closure__
    assert closure is not None
    monkeypatch.setattr(closure[index], "cell_contents", value)


@pytest.fixture
def gui_window(monkeypatch, tmp_path):
    if "QT_QPA_PLATFORM" not in os.environ:
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("ROW_HOME", str(tmp_path / "row-home"))
    pytest.importorskip("PyQt6")
    from remote_ops_workspace.gui import create_main_window

    app, window = create_main_window(
        ["gui-profile-workflow-edges"],
        show=False,
        preview_samples=False,
    )
    window.resize(1000, 720)
    window.show()
    app.processEvents()
    yield app, window
    window.close()
    app.processEvents()


def test_profile_dialog_defaults_editor_validation_and_submit_edges(gui_window) -> None:
    from PyQt6.QtCore import QTimer
    from PyQt6.QtWidgets import QApplication, QComboBox, QLineEdit, QPlainTextEdit

    app, window = gui_window
    observed: list[object] = []

    def capture_dialog() -> None:
        dialog = QApplication.activeModalWidget()
        assert dialog is not None
        observed.append(dialog)
        dialog.reject()

    QTimer.singleShot(0, capture_dialog)
    window.create_profile()
    dialog = observed[0]

    protocol = dialog.fields["protocol"]
    assert isinstance(protocol, QComboBox)
    original_protocol = protocol
    dialog.fields["protocol"] = QLineEdit("ssh")
    dialog.apply_protocol_preset()
    dialog.fields["protocol"] = original_protocol

    protocol.setCurrentText("ssh")
    dialog.apply_protocol_preset()
    port = dialog.fields["port"]
    options = dialog.fields["options"]
    assert isinstance(port, QLineEdit)
    assert isinstance(options, QPlainTextEdit)
    assert port.text() == "22"
    assert "Applied SSH defaults" in dialog.preset_note.text()

    original_port = port
    original_options = options
    dialog.fields["port"] = QPlainTextEdit()
    dialog.fields["options"] = QLineEdit()
    dialog.apply_protocol_preset()
    dialog.fields["port"] = original_port
    dialog.fields["options"] = original_options

    data = dialog.editor_data()
    assert data["protocol"] == "ssh"
    assert data["port"] == "22"
    assert "options" in data

    for message in (
        "profile name is required",
        "profile already exists",
        "unsupported protocol",
        "host is required",
        "port is invalid",
        "url is invalid",
        "command is required",
        "identity file invalid",
        "credential missing",
        "tunnel invalid",
        "option invalid",
        "unclassified validation",
    ):
        dialog.show_validation_error(message)
        assert dialog.validation_error.isHidden() is False
        assert message in dialog.validation_error.text()
        assert dialog._validated_profile is None

    original_name = dialog.fields["name"]
    dialog.fields["name"] = object()
    dialog.show_validation_error("unclassified validation")
    dialog.fields["name"] = original_name

    name = dialog.fields["name"]
    command = dialog.fields["command"]
    assert isinstance(name, QLineEdit)
    assert isinstance(command, QLineEdit)
    name.clear()
    protocol.setCurrentText("custom")
    command.setText("echo ready")
    dialog.submit()
    assert dialog.validation_error.isHidden() is False

    name.setText("dialog-edge")
    dialog.submit()
    assert dialog.result() == dialog.DialogCode.Accepted
    assert dialog.profile().name == "dialog-edge"
    app.processEvents()


def test_profile_dialog_preserves_protocol_missing_from_current_registry(gui_window) -> None:
    from PyQt6.QtWidgets import QComboBox

    _app, window = gui_window
    create_profile = type(window).create_profile
    index = create_profile.__code__.co_freevars.index("ProfileDialog")
    closure = create_profile.__closure__
    assert closure is not None
    dialog_type = closure[index].cell_contents
    profile = Profile(
        name="retired-plugin-profile",
        protocol="retired-plugin-protocol",
        host="retired-plugin.example.invalid",
    )
    dialog = dialog_type(profile, window)
    protocol = dialog.fields["protocol"]
    assert isinstance(protocol, QComboBox)
    assert protocol.currentText() == "retired-plugin-protocol"
    assert protocol.findText("retired-plugin-protocol") >= 0
    dialog.deleteLater()


def test_profile_create_edit_remove_and_import_workflow_edges(
    gui_window,
    monkeypatch,
) -> None:
    from PyQt6.QtWidgets import QDialog, QFileDialog, QMessageBox

    from remote_ops_workspace import gui

    _app, window = gui_window
    first = Profile(
        name="first",
        protocol="ssh",
        host="first.example.invalid",
        username="operator",
    )
    second = Profile(
        name="second",
        protocol="rdp",
        host="second.example.invalid",
        username="operator",
    )

    class _Dialog:
        def __init__(self, results, profiles) -> None:
            self.results = iter(results)
            self.profiles = iter(profiles)
            self.validation_errors: list[str] = []

        def exec(self):
            return next(self.results)

        def profile(self):
            value = next(self.profiles)
            if isinstance(value, Exception):
                raise value
            return value

        def show_validation_error(self, message: str) -> None:
            self.validation_errors.append(message)

    dialog_queue: list[_Dialog] = []

    def dialog_factory(*_args, **_kwargs):
        return dialog_queue.pop(0)

    _set_closure_value(
        monkeypatch,
        type(window).create_profile,
        "ProfileDialog",
        dialog_factory,
    )

    class _Store:
        def __init__(self) -> None:
            self.add_calls: list[str] = []
            self.remove_calls: list[str] = []
            self.get_value: object = first
            self.fail_next_add = False
            self.fail_remove = False

        def add(self, profile: Profile, **_kwargs) -> None:
            self.add_calls.append(profile.name)
            if self.fail_next_add:
                self.fail_next_add = False
                raise ValueError("duplicate profile")

        def get(self, _name: str):
            if isinstance(self.get_value, Exception):
                raise self.get_value
            return self.get_value

        def remove(self, name: str, **_kwargs) -> None:
            self.remove_calls.append(name)
            if self.fail_remove:
                raise KeyError(name)

    store = _Store()
    window.store = store
    refreshes: list[str] = []
    selections: list[str] = []
    monkeypatch.setattr(window, "refresh_profiles", lambda: refreshes.append("refresh"))
    monkeypatch.setattr(window, "select_profile", lambda name: selections.append(name))

    create_dialog = _Dialog(
        [QDialog.DialogCode.Accepted, QDialog.DialogCode.Accepted],
        [first, second],
    )
    dialog_queue.append(create_dialog)
    store.fail_next_add = True
    window.create_profile()
    assert create_dialog.validation_errors == ["duplicate profile"]
    assert store.add_calls == ["first", "second"]
    assert selections == ["second"]

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
        if title == "Remove profile":
            return next(remove_answers)
        return QMessageBox.StandardButton.Ok

    _set_closure_value(
        monkeypatch,
        type(window).edit_selected_profile,
        "_literal_message_box",
        fake_message_box,
    )
    monkeypatch.setattr(window, "selected_profile_name", lambda: None)
    window.edit_selected_profile()
    assert "Select a profile first" in messages[-1]

    monkeypatch.setattr(window, "selected_profile_name", lambda: first.name)
    store.get_value = KeyError(first.name)
    window.edit_selected_profile()
    assert first.name in messages[-1]

    store.get_value = first
    edit_dialog = _Dialog(
        [QDialog.DialogCode.Accepted, QDialog.DialogCode.Accepted],
        [ValueError("invalid edit"), second],
    )
    dialog_queue.append(edit_dialog)
    saved: list[tuple[str, str]] = []
    monkeypatch.setattr(
        window,
        "save_profile",
        lambda profile, original_name: saved.append((profile.name, original_name)),
    )
    window.edit_selected_profile()
    assert edit_dialog.validation_errors == ["invalid edit"]
    assert saved == [("second", "first")]

    rejected_edit_dialog = _Dialog([QDialog.DialogCode.Rejected], [])
    dialog_queue.append(rejected_edit_dialog)
    window.edit_selected_profile()
    assert saved == [("second", "first")]

    monkeypatch.setattr(window, "selected_profile_name", lambda: None)
    window.remove_selected_profile()
    monkeypatch.setattr(window, "selected_profile_name", lambda: first.name)
    window.remove_selected_profile()
    assert store.remove_calls == []
    window.remove_selected_profile()
    assert store.remove_calls == ["first"]
    store.fail_remove = True
    window.remove_selected_profile()
    assert store.remove_calls == ["first", "first"]

    import_dialog_results = iter(
        [
            QDialog.DialogCode.Rejected,
            QDialog.DialogCode.Accepted,
            QDialog.DialogCode.Accepted,
        ]
    )

    class _ImportDialog:
        def __init__(self, *_args, **_kwargs) -> None:
            pass

        def exec(self):
            return next(import_dialog_results)

    _set_closure_value(
        monkeypatch,
        type(window).import_profiles_with_preview,
        "ProfileImportPreviewDialog",
        _ImportDialog,
    )
    file_responses = iter(
        [
            ("", ""),
            ("bad.json", ""),
            ("empty.json", ""),
            ("cancel.json", ""),
            ("import.json", ""),
            ("clean.json", ""),
        ]
    )
    monkeypatch.setattr(
        QFileDialog,
        "getOpenFileName",
        staticmethod(lambda *_args, **_kwargs: next(file_responses)),
    )
    import_results = iter(
        [
            ValueError("invalid import"),
            ProfileImportResult("row", []),
            ProfileImportResult("row", [first]),
            ProfileImportResult("row", [first, second], ["warning"]),
            ProfileImportResult("row", [second]),
        ]
    )

    def fake_import(*_args, **_kwargs):
        value = next(import_results)
        if isinstance(value, Exception):
            raise value
        return value

    monkeypatch.setattr(gui, "import_profiles", fake_import)
    store.fail_next_add = True
    for _index in range(6):
        window.import_profiles_with_preview()
    assert store.add_calls[-3:] == ["first", "second", "second"]
    assert any("Some profiles were skipped" in message for message in messages)


def test_profile_save_order_duplicates_and_import_warning_dialog_edges(
    gui_window,
) -> None:
    from PyQt6.QtWidgets import QTextEdit

    _app, window = gui_window
    first = Profile(
        name="first",
        protocol="ssh",
        host="first.example.invalid",
        group="zeta",
    )
    replacement = Profile(
        name="replacement",
        protocol="ssh",
        host="replacement.example.invalid",
        group="alpha",
    )
    duplicate = Profile(
        name="duplicate",
        protocol="ssh",
        host="duplicate.example.invalid",
        group="beta",
    )

    class _Store:
        def __init__(self) -> None:
            self.profiles = [first, duplicate]
            self.saved: list[list[str]] = []

        def load(self, *, resolve: bool):
            assert resolve is False
            return list(self.profiles)

        def save(self, profiles, *, surface: str) -> None:
            assert surface == "profile-editor"
            self.profiles = list(profiles)
            self.saved.append([profile.name for profile in self.profiles])

    store = _Store()
    window.store = store
    with pytest.raises(ValueError, match="profile already exists"):
        window.save_profile(duplicate, original_name=first.name)
    window.save_profile(replacement, original_name=first.name)
    assert store.saved == [["replacement", "duplicate"]]

    result = ProfileImportResult(
        "row",
        [replacement],
        ["controlled warning"],
    )
    dialog = window.create_profile_import_preview_dialog("profiles.json", result)
    warnings = dialog.findChild(QTextEdit, "profileImportWarnings")
    assert warnings is not None
    assert "controlled warning" in warnings.toPlainText()
    dialog.deleteLater()


def test_profile_dialog_can_materialize_unsubmitted_editor_data(gui_window) -> None:
    _app, window = gui_window
    create_profile = type(window).create_profile
    index = create_profile.__code__.co_freevars.index("ProfileDialog")
    closure = create_profile.__closure__
    assert closure is not None
    dialog_type = closure[index].cell_contents
    profile = Profile(
        name="editor-materialized",
        protocol="ssh",
        host="editor-materialized.example.invalid",
    )
    dialog = dialog_type(profile, window)

    materialized = dialog.profile()

    assert materialized.name == profile.name
    assert materialized.host == profile.host
    dialog.deleteLater()

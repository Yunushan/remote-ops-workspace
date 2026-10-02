from __future__ import annotations

import errno
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from remote_ops_workspace import file_safety, gui
from remote_ops_workspace.layouts import Layout, LayoutPane
from remote_ops_workspace.models import Profile


@pytest.fixture
def workspace(monkeypatch, tmp_path):
    pytest.importorskip("PyQt6")
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("ROW_HOME", str(tmp_path / "workspace"))
    app, window = gui.create_main_window(["gui-io-regression"], show=False)
    window.store.add(Profile(name="existing", protocol="ssh", host="old.example.invalid"))
    window.layout_store.add(Layout(name="existing-layout", panes=[LayoutPane(command="echo old")]))
    window.refresh_profiles()
    window.refresh_layouts()
    messages = []

    from PyQt6.QtWidgets import QMessageBox

    requested_titles = {}
    set_window_title = QMessageBox.setWindowTitle

    def record_title(dialog, title):
        # Qt ignores QMessageBox window titles on macOS; verify the setter call.
        requested_titles[dialog] = title
        set_window_title(dialog, title)

    def message(dialog):
        messages.append((requested_titles[dialog], dialog.text()))
        return QMessageBox.StandardButton.Yes.value

    monkeypatch.setattr(QMessageBox, "setWindowTitle", record_title)
    monkeypatch.setattr(QMessageBox, "exec", message)
    yield app, window, messages
    window.close()
    app.processEvents()


def _deny_replace(_source, destination):
    raise PermissionError(errno.EACCES, "Permission denied", str(destination))


@pytest.mark.parametrize("operation", ["create", "edit"])
def test_profile_save_error_preserves_store_dialog_input_and_selection(workspace, monkeypatch, operation) -> None:
    from PyQt6.QtWidgets import QDialog

    _app, window, _messages = workspace
    before = window.store.path.read_bytes()
    candidate = Profile(name="new", protocol="ssh", host="typed.example.invalid")
    dialog = window.create_profile_dialog(candidate)
    results = iter([QDialog.DialogCode.Accepted, QDialog.DialogCode.Rejected])
    monkeypatch.setattr(dialog, "exec", lambda: next(results))
    monkeypatch.setattr(window, "create_profile_dialog", lambda *_args, **_kwargs: dialog)
    monkeypatch.setattr(window, "selected_profile_name", lambda: "existing")
    monkeypatch.setattr(file_safety.os, "replace", _deny_replace)

    (window.create_profile if operation == "create" else window.edit_selected_profile)()

    assert window.store.path.read_bytes() == before
    assert dialog.profile().name == "new"
    assert dialog.profile().host == "typed.example.invalid"
    assert "Permission denied" in dialog.validation_error.text()
    assert window.selected_profile_name() == "existing"
    assert "PROFILE SAVED" not in window.log.toPlainText()
    assert "PROFILE UPDATED" not in window.log.toPlainText()
    dialog.deleteLater()


@pytest.mark.parametrize("operation", ["create", "edit"])
def test_layout_save_error_preserves_store_and_dialog_input(workspace, monkeypatch, operation) -> None:
    from PyQt6.QtWidgets import QDialog

    _app, window, _messages = workspace
    before = window.layout_store.path.read_bytes()
    candidate = Layout(name="new-layout", panes=[LayoutPane(command="echo typed")])
    dialog = window.create_layout_dialog(candidate)
    results = iter([QDialog.DialogCode.Accepted, QDialog.DialogCode.Rejected])
    monkeypatch.setattr(dialog, "exec", lambda: next(results))
    monkeypatch.setattr(window, "create_layout_dialog", lambda *_args, **_kwargs: dialog)
    window.layout_select.setCurrentText("existing-layout")
    monkeypatch.setattr(file_safety.os, "replace", _deny_replace)

    (window.create_layout if operation == "create" else window.edit_selected_layout)()

    assert window.layout_store.path.read_bytes() == before
    assert dialog.workspace_layout().name == "new-layout"
    assert "Permission denied" in dialog.validation_error.text()
    assert window.layout_select.currentText() == "existing-layout"
    dialog.deleteLater()


def test_refresh_errors_preserve_visible_profile_and_layout_rows(workspace, monkeypatch) -> None:
    _app, window, messages = workspace
    profile_rows = [item.text(0) for item in window.iter_profile_tree_items()]
    layout_rows = [window.layout_select.itemText(index) for index in range(window.layout_select.count())]

    def denied(*_args, **_kwargs):
        raise PermissionError("Cannot read workspace files")

    monkeypatch.setattr(window.store, "load", denied)
    monkeypatch.setattr(window.layout_store, "load", denied)
    window.refresh_profiles()
    window.refresh_layouts()

    assert [item.text(0) for item in window.iter_profile_tree_items()] == profile_rows
    assert [window.layout_select.itemText(index) for index in range(window.layout_select.count())] == layout_rows
    assert messages[-2:] == [("Profile refresh failed", "Cannot read workspace files"), ("Layout refresh failed", "Cannot read workspace files")]


@pytest.mark.parametrize("kind", ["profile", "layout"])
def test_remove_error_preserves_visible_and_persisted_records(workspace, monkeypatch, kind) -> None:
    _app, window, messages = workspace
    store = window.store if kind == "profile" else window.layout_store
    before = store.path.read_bytes()
    monkeypatch.setattr(window, "selected_profile_name", lambda: "existing")
    window.layout_select.setCurrentText("existing-layout")
    monkeypatch.setattr(file_safety.os, "replace", _deny_replace)

    (window.remove_selected_profile if kind == "profile" else window.remove_selected_layout)()

    assert store.path.read_bytes() == before
    assert "Permission denied" in messages[-1][1]
    assert "REMOVED:" not in window.log.toPlainText()


def test_preview_import_save_failure_commits_no_rows_and_keeps_preview_available(workspace, monkeypatch, tmp_path) -> None:
    from PyQt6.QtWidgets import QDialog, QFileDialog

    _app, window, messages = workspace
    before = window.store.path.read_bytes()
    source = tmp_path / "import.json"
    source.write_text(json.dumps({"profiles": [Profile(name=name, protocol="ssh", host="new.example.invalid").to_dict() for name in ("first", "second")]}), encoding="utf-8")
    attempts = []
    responses = iter([QDialog.DialogCode.Accepted, QDialog.DialogCode.Rejected])

    class Preview:
        def __init__(self, *_args, **_kwargs):
            pass

        def exec(self):
            attempts.append("preview")
            return next(responses)

    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_args, **_kwargs: (str(source), ""))
    monkeypatch.setattr(window, "create_profile_import_preview_dialog", Preview)
    monkeypatch.setattr(file_safety.os, "replace", _deny_replace)
    window.import_profiles_with_preview()

    assert attempts == ["preview", "preview"]
    assert window.store.path.read_bytes() == before
    assert messages[-1][0] == "Profile import failed"
    assert "Permission denied" in messages[-1][1]
    assert "PROFILE IMPORTED" not in window.log.toPlainText()


@pytest.mark.parametrize("surface", ["toolbar", "menu", "layout", "ribbon", "home"])
def test_operator_callback_handles_io_errors_and_propagates_programming_errors(workspace, surface) -> None:
    _app, window, messages = workspace

    def denied():
        raise PermissionError("Cannot access profile data")

    if surface == "toolbar":
        window.product_toolbar_callbacks["controlled"] = denied
        window.run_product_toolbar_action("controlled")
    elif surface == "menu":
        window.product_menu_callbacks["controlled"] = {"controlled": denied}
        window.run_product_menu_action("controlled", "controlled")
    elif surface == "layout":
        window.layout_toolbar_callbacks["controlled"] = denied
        window.run_layout_toolbar_action("controlled")
    elif surface == "ribbon":
        window.moba_ribbon_callbacks["controlled"] = denied
        window.run_moba_ribbon_action("controlled")
    else:
        window.home_action_callbacks["controlled"] = denied
        window.run_home_action("controlled")
    assert messages[-1] == ("Workspace operation failed", "Cannot access profile data")

    def unexpected():
        raise RuntimeError("unexpected callback failure")

    with pytest.raises(RuntimeError, match="unexpected callback failure"):
        window.run_operator_action(unexpected)


@pytest.mark.parametrize("operation", ["edit_selected_profile", "connect_selected", "open_files_selected", "open_transfer_queue_selected", "edit_selected_layout", "open_selected_layout"])
def test_profile_and_layout_read_denial_does_not_change_selection_or_open_tabs(workspace, monkeypatch, operation) -> None:
    _app, window, messages = workspace
    monkeypatch.setattr(window, "selected_profile_name", lambda: "existing")
    window.layout_select.setCurrentText("existing-layout")
    tab_count = window.tabs.count()
    original_read = Path.read_text

    def denied_read(path, *args, **kwargs):
        if path in {window.store.path, window.layout_store.path}:
            raise PermissionError("Cannot read selected workspace record")
        return original_read(path, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", denied_read)
    if operation == "connect_selected":
        window.connect_selected(False)
    else:
        getattr(window, operation)()
    assert "Cannot read selected workspace record" in messages[-1][1]
    assert window.selected_profile_name() == "existing"
    assert window.layout_select.currentText() == "existing-layout"
    assert window.tabs.count() == tab_count


@pytest.mark.parametrize("collision", [False, True])
def test_gui_import_commits_all_accepted_rows_and_preserves_existing_on_skip(workspace, monkeypatch, tmp_path, collision) -> None:
    from PyQt6.QtWidgets import QDialog, QFileDialog

    _app, window, messages = workspace
    source = tmp_path / "import.json"
    profiles = [Profile(name="first", protocol="ssh", host="first.example.invalid"), Profile(name="existing" if collision else "second", protocol="ssh", host="second.example.invalid")]
    source.write_text(json.dumps({"profiles": [profile.to_dict() for profile in profiles]}), encoding="utf-8")

    class Preview:
        def __init__(self, *_args, **_kwargs):
            pass

        def exec(self):
            return QDialog.DialogCode.Accepted

    monkeypatch.setattr(QFileDialog, "getOpenFileName", lambda *_args, **_kwargs: (str(source), ""))
    monkeypatch.setattr(window, "create_profile_import_preview_dialog", Preview)
    window.import_profiles_with_preview()
    assert window.store.get("existing").host == "old.example.invalid"
    assert window.store.get("first").host == "first.example.invalid"
    assert f"PROFILE IMPORTED: {1 if collision else 2}" in window.log.toPlainText()
    if collision:
        assert "existing: profile already exists" in messages[-1][1]
    else:
        assert window.store.get("second").host == "second.example.invalid"


def test_quick_connect_io_failures_preserve_query_and_existing_suggestions(workspace, monkeypatch) -> None:
    from PyQt6.QtWidgets import QTreeWidgetItem

    _app, window, messages = workspace
    monkeypatch.setattr(window, "current_design_is_moba", lambda: True)
    monkeypatch.setattr(window, "current_moba_connected_dock_is_active", lambda: False)
    blocked = window.quick_connect.blockSignals(True)
    window.quick_connect.setText("typed.example.invalid")
    window.quick_connect.blockSignals(blocked)
    window.quick_connect_suggestions.clear()
    window.quick_connect_suggestions.addTopLevelItem(QTreeWidgetItem(["preserved suggestion"]))
    window.quick_connect_suggestions.setCurrentItem(None)

    def denied(*_args, **_kwargs):
        raise PermissionError("Cannot read quick connect profiles")

    monkeypatch.setattr(window.store, "load", denied)
    window.update_quick_connect_suggestions()
    assert window.quick_connect_suggestions.topLevelItem(0).text(0) == "preserved suggestion"
    assert window.statusBar().currentMessage() == "Quick connect unavailable: Cannot read quick connect profiles"
    window.run_quick_connect()
    assert messages[-1] == ("Quick connect failed", "Cannot read quick connect profiles")
    assert window.quick_connect.text() == "typed.example.invalid"

    candidate = gui.QuickConnectCandidate("target", "typed host", "SSH", profile=Profile(name="typed", protocol="ssh", host="typed.example.invalid"))
    monkeypatch.setattr(window, "launch_profile", denied)
    window.run_quick_connect_candidate_value(candidate)
    assert messages[-1] == ("Quick connect failed", "Cannot read quick connect profiles")
    assert window.quick_connect.text() == "typed.example.invalid"
    assert window.quick_connect_suggestions.topLevelItem(0).text(0) == "preserved suggestion"


@pytest.mark.parametrize("failure_kind", ["io", "status", "identity", "timeout"])
def test_workflow_io_error_keeps_dialog_open_and_programming_errors_visible(workspace, monkeypatch, failure_kind) -> None:
    from remote_ops_workspace.process_status import ProcessIdentityError, ProcessStatusError

    _app, window, messages = workspace
    dialog = window.create_workflow_dialog("Workflow", "Test", [], "Typed context")
    accepted = []
    monkeypatch.setattr(dialog, "accept", lambda: accepted.append(True))

    def denied():
        error_type = {"io": PermissionError, "status": ProcessStatusError, "identity": ProcessIdentityError, "timeout": TimeoutError}[failure_kind]
        raise error_type("Cannot read workflow files")

    dialog.workflow_action(denied)()
    assert accepted == []
    assert messages[-1] == ("Workspace operation failed", "Cannot read workflow files")
    dialog.workflow_action(lambda: None)()
    assert accepted == [True]

    def unexpected():
        raise RuntimeError("unexpected workflow failure")

    with pytest.raises(RuntimeError, match="unexpected workflow failure"):
        dialog.workflow_action(unexpected)()
    dialog.deleteLater()


@pytest.mark.parametrize("error_type", ["status", "identity", "timeout"])
def test_operator_action_reports_expected_process_failures_through_message_seam(workspace, monkeypatch, error_type) -> None:
    from PyQt6.QtWidgets import QMessageBox

    from remote_ops_workspace.process_status import ProcessIdentityError, ProcessStatusError

    _app, window, _messages = workspace
    reported = []
    monkeypatch.setattr(window, "show_message", lambda *args: reported.append(args))
    failure = {"status": ProcessStatusError, "identity": ProcessIdentityError, "timeout": TimeoutError}[error_type]

    def unavailable():
        raise failure("Managed helper could not be stopped")

    window.run_operator_action(unavailable)
    assert reported == [(QMessageBox.Icon.Warning, "Workspace operation failed", "Managed helper could not be stopped")]


def test_layout_resize_permission_failure_keeps_layout_and_reports_status(workspace, monkeypatch) -> None:
    _app, window, _messages = workspace
    before = window.layout_store.path.read_bytes()
    monkeypatch.setattr(window, "layout_splitters", lambda _widget: [SimpleNamespace(sizes=lambda: [200, 300])])
    monkeypatch.setattr(file_safety.os, "replace", _deny_replace)
    window.persist_layout_resize_state("existing-layout", window)
    assert "Layout resize could not be saved" in window.statusBar().currentMessage()
    assert window.layout_store.path.read_bytes() == before


def test_gui_startup_reports_expected_workspace_errors_without_masking_bugs(monkeypatch, capsys) -> None:
    shown = []
    monkeypatch.setattr(gui, "_show_gui_startup_error", shown.append)

    def denied(*_args, **_kwargs):
        raise PermissionError("Cannot open profiles.json")

    monkeypatch.setattr(gui, "create_main_window", denied)
    assert gui.main() == 1
    assert capsys.readouterr().err.strip() == "Unable to open workspace: Cannot open profiles.json"
    assert shown == ["Unable to open workspace: Cannot open profiles.json"]

    def unexpected(*_args, **_kwargs):
        raise RuntimeError("unexpected startup failure")

    monkeypatch.setattr(gui, "create_main_window", unexpected)
    with pytest.raises(RuntimeError, match="unexpected startup failure"):
        gui.main()


def test_startup_error_is_visible_and_literal_when_qt_application_exists(workspace, monkeypatch) -> None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication, QMessageBox

    _app, _window, _messages = workspace
    dialogs = []
    monkeypatch.setattr(QMessageBox, "exec", lambda dialog: dialogs.append((dialog.text(), dialog.textFormat())))
    gui._show_gui_startup_error("Cannot open <b>profiles</b>.json")
    assert dialogs == [("Cannot open <b>profiles</b>.json", Qt.TextFormat.PlainText)]
    monkeypatch.setattr(QApplication, "instance", lambda: None)
    gui._show_gui_startup_error("No application yet")
    assert len(dialogs) == 1

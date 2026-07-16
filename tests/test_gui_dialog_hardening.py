from __future__ import annotations

from dataclasses import dataclass

import pytest

from remote_ops_workspace.gui import _safe_tooltip_html
from remote_ops_workspace.models import Profile
from remote_ops_workspace.profile_importers import ProfileImportResult


def test_safe_tooltip_html_escapes_markup_and_preserves_lines() -> None:
    assert _safe_tooltip_html("<b>literal</b>\nnext & final") == (
        "<qt>&lt;b&gt;literal&lt;/b&gt;<br>next &amp; final</qt>"
    )


def test_main_window_and_application_have_a_visible_product_icon(gui_window) -> None:
    app, window = gui_window

    assert not app.windowIcon().isNull()
    assert not window.windowIcon().isNull()


@pytest.fixture
def gui_window(monkeypatch, tmp_path):
    monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("ROW_HOME", str(tmp_path / "row-home"))
    pytest.importorskip("PyQt6")
    from remote_ops_workspace.gui import create_main_window

    app, window = create_main_window(["gui-dialog-hardening"], show=False)
    window.resize(800, 600)
    window.move(0, 0)
    window.show()
    app.processEvents()
    yield app, window
    window.close()
    app.processEvents()


def test_dynamic_dialog_labels_are_plain_text_and_frames_stay_on_parent_screen(gui_window) -> None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QDialogButtonBox, QFrame, QLabel

    app, window = gui_window
    profile = Profile(
        name="literal <b>profile</b>",
        protocol="sftp",
        host="example.invalid",
        username="operator",
    )
    result = ProfileImportResult(source_format="row", profiles=[profile])
    dialogs = [
        window.create_profile_import_preview_dialog("C:/<b>literal</b>/profiles.json", result),
        window.create_transfer_queue_dialog(profile),
        window.create_workflow_dialog(
            "<b>literal title</b>",
            "<i>literal subtitle</i>",
            [("workflow", "ready", "literal")],
            "detail",
        ),
    ]

    for dialog in dialogs:
        dialog.show()
        app.processEvents()
        app.processEvents()
        available = dialog.screen().availableGeometry()
        assert available.contains(dialog.frameGeometry())

    import_source = dialogs[0].findChild(QLabel, "profileImportSource")
    transfer_subtitle = dialogs[1].findChild(QLabel, "workflowSubtitle")
    workflow_title = dialogs[2].findChild(QLabel, "workflowTitle")
    workflow_subtitle = dialogs[2].findChild(QLabel, "workflowSubtitle")
    assert import_source.textFormat() == Qt.TextFormat.PlainText
    assert "<b>literal</b>" in import_source.text()
    assert transfer_subtitle.textFormat() == Qt.TextFormat.PlainText
    assert "<b>profile</b>" in transfer_subtitle.text()
    assert workflow_title.textFormat() == Qt.TextFormat.PlainText
    assert workflow_title.text() == "<b>literal title</b>"
    assert workflow_subtitle.textFormat() == Qt.TextFormat.PlainText
    assert workflow_subtitle.text() == "<i>literal subtitle</i>"

    assert dialogs[0].findChild(QDialogButtonBox, "profileImportDialogButtons").isVisible()
    assert dialogs[1].findChild(QDialogButtonBox, "transferQueueDialogButtons").isVisible()
    assert dialogs[2].findChild(QFrame, "workflowFooter").isVisible()
    for dialog in dialogs:
        dialog.close()


class _Signal:
    def __init__(self) -> None:
        self.callbacks = []

    def connect(self, callback) -> None:
        self.callbacks.append(callback)

    def emit(self, *args) -> None:
        for callback in tuple(self.callbacks):
            callback(*args)


@dataclass
class _FakeProcessOptions:
    fail_to_start: bool = False


class _FakeProcess:
    def __init__(self, parent, *, options: _FakeProcessOptions | None = None) -> None:
        from PyQt6.QtCore import QProcess

        self.parent = parent
        self.options = options or _FakeProcessOptions()
        self.readyReadStandardOutput = _Signal()
        self.readyReadStandardError = _Signal()
        self.started = _Signal()
        self.finished = _Signal()
        self.errorOccurred = _Signal()
        self.process_state = QProcess.ProcessState.NotRunning
        self.program = ""
        self.arguments = []
        self.written = b""
        self.stdout = b""
        self.stderr = b""
        self.terminated = False
        self.killed = False
        self.deleted = False

    def setProgram(self, program: str) -> None:
        self.program = program

    def setArguments(self, arguments: list[str]) -> None:
        self.arguments = arguments

    def start(self) -> None:
        from PyQt6.QtCore import QProcess

        if self.options.fail_to_start:
            self.process_state = QProcess.ProcessState.NotRunning
            self.errorOccurred.emit(QProcess.ProcessError.FailedToStart)
            return
        self.process_state = QProcess.ProcessState.Running
        self.started.emit()

    def state(self):
        return self.process_state

    def write(self, data: bytes) -> None:
        self.written += data

    def closeWriteChannel(self) -> None:
        return None

    def readAllStandardOutput(self) -> bytes:
        output = self.stdout
        self.stdout = b""
        return output

    def readAllStandardError(self) -> bytes:
        output = self.stderr
        self.stderr = b""
        return output

    def errorString(self) -> str:
        return "controlled start failure"

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        from PyQt6.QtCore import QProcess

        self.killed = True
        self.process_state = QProcess.ProcessState.NotRunning
        self.finished.emit(-1, QProcess.ExitStatus.CrashExit)

    def finish(self, exit_code: int = 0) -> None:
        from PyQt6.QtCore import QProcess

        self.process_state = QProcess.ProcessState.NotRunning
        status = QProcess.ExitStatus.NormalExit if exit_code == 0 else QProcess.ExitStatus.CrashExit
        self.finished.emit(exit_code, status)

    def deleteLater(self) -> None:
        self.deleted = True


def test_transfer_queue_owns_process_lifecycle_until_completion_and_cancel(gui_window) -> None:
    from PyQt6.QtGui import QCloseEvent
    from PyQt6.QtWidgets import QDialogButtonBox

    _app, window = gui_window
    profile = Profile(name="queue", protocol="sftp", host="example.invalid", username="operator")
    processes: list[_FakeProcess] = []

    def process_factory(parent):
        process = _FakeProcess(parent)
        processes.append(process)
        return process

    dialog = window.create_transfer_queue_dialog(profile, process_factory=process_factory)
    dialog.operations.setPlainText("get /remote/file ./local-file")
    dialog.run_queue()
    process = processes[-1]
    process.stdout = b"<b>literal stdout</b>"
    process.stderr = b"<i>literal stderr</i>"
    process.readyReadStandardOutput.emit()
    process.readyReadStandardError.emit()
    assert "<b>literal stdout</b>" in dialog.preview.toPlainText()
    assert "<i>literal stderr</i>" in dialog.preview.toPlainText()
    assert dialog.queue_is_active()
    assert not dialog.operations.isEnabled()
    assert not dialog.buttons.button(QDialogButtonBox.StandardButton.Ok).isEnabled()
    assert not dialog.buttons.button(QDialogButtonBox.StandardButton.Cancel).isEnabled()
    assert dialog.cancel_queue_button.isEnabled()

    dialog.accept()
    dialog.reject()
    assert dialog.result() == 0
    active_close = QCloseEvent()
    dialog.closeEvent(active_close)
    assert not active_close.isAccepted()
    process.finish(0)
    assert not dialog.queue_is_active()
    assert dialog.operations.isEnabled()
    assert dialog.run_button.isEnabled()
    assert "queue completed" in dialog.preview.toPlainText()
    assert process.deleted
    inactive_close = QCloseEvent()
    dialog.closeEvent(inactive_close)
    assert inactive_close.isAccepted()

    dialog.operations.setPlainText("get /remote/file ./local-file")
    dialog.run_queue()
    process = processes[-1]
    dialog.cancel_queue()
    assert process.terminated
    assert dialog.queue_is_active()
    assert not dialog.cancel_queue_button.isEnabled()
    dialog.kill_cancelled_queue_process()
    assert process.killed
    assert not dialog.queue_is_active()
    assert "queue cancelled" in dialog.preview.toPlainText()


def test_transfer_queue_failed_to_start_resets_all_controls(gui_window) -> None:
    _app, window = gui_window
    profile = Profile(name="queue", protocol="sftp", host="example.invalid", username="operator")

    def process_factory(parent):
        return _FakeProcess(parent, options=_FakeProcessOptions(fail_to_start=True))

    dialog = window.create_transfer_queue_dialog(profile, process_factory=process_factory)
    dialog.operations.setPlainText("get /remote/file ./local-file")
    dialog.run_queue()

    assert not dialog.queue_is_active()
    assert dialog.operations.isEnabled()
    assert dialog.run_button.isEnabled()
    assert not dialog.cancel_queue_button.isEnabled()
    assert "controlled start failure" in dialog.preview.toPlainText()
    assert "queue stopped after failure" in dialog.preview.toPlainText()


def test_activity_log_append_preserves_markup_like_text_literally(gui_window) -> None:
    _app, window = gui_window
    window.log.append("profile <b>literal</b> & remote")
    assert "profile <b>literal</b> & remote" in window.log.toPlainText()


def test_tab_tooltip_preserves_raw_text_but_escapes_qt_rich_text(gui_window) -> None:
    from PyQt6.QtWidgets import QWidget

    _app, window = gui_window
    widget = QWidget()
    index = window.add_workspace_tab(widget, "profile <b>literal</b> & remote")

    assert widget.property("tabTooltipBaseText") == "profile <b>literal</b> & remote"
    assert widget.property("tabTooltipPlainText") == (
        "profile <b>literal</b> & remote: running"
    )
    assert window.tabs.tabToolTip(index) == (
        "<qt>profile &lt;b&gt;literal&lt;/b&gt; &amp; remote: running</qt>"
    )

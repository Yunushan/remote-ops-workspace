from __future__ import annotations

import os

import pytest

from remote_ops_workspace.models import Profile


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
        ["gui-workflow-dialog-edges"],
        show=False,
        preview_samples=False,
    )
    window.resize(1000, 700)
    window.show()
    app.processEvents()
    yield app, window
    window.close()
    app.processEvents()


def test_transfer_queue_local_and_remote_preview_edges(
    gui_window,
    monkeypatch,
) -> None:
    from remote_ops_workspace import gui

    _app, window = gui_window
    profile = Profile(
        name="queue-edge",
        protocol="sftp",
        host="queue.example.invalid",
        username="operator",
    )
    dialog = window.create_transfer_queue_dialog(profile)

    monkeypatch.setattr(
        gui,
        "preview_local_path",
        lambda _path: (_ for _ in ()).throw(ValueError("invalid local path")),
    )
    dialog.local_preview_path.setText("invalid")
    dialog.refresh_local_preview()
    assert dialog.preview.toPlainText() == "error: invalid local path"

    class _Preview:
        def __init__(self, data: dict[str, object]) -> None:
            self.data = data

        def to_dict(self) -> dict[str, object]:
            return self.data

    rich_preview = {
        "path": "C:/tmp/example.bin",
        "kind": "file",
        "size": 42,
        "children": ["first", "second"],
        "binary": True,
        "truncated": True,
        "text": "preview text",
        "error": "controlled read warning",
    }
    monkeypatch.setattr(
        gui,
        "preview_local_path",
        lambda _path: _Preview(rich_preview),
    )
    dialog.refresh_local_preview()
    rendered = dialog.preview.toPlainText()
    assert "size: 42" in rendered
    assert "  first" in rendered
    assert "binary: true" in rendered
    assert "truncated: true" in rendered
    assert "preview text" in rendered
    assert "controlled read warning" in rendered

    sparse_preview = {
        "path": "C:/tmp/empty",
        "kind": "directory",
        "size": None,
        "children": None,
        "binary": False,
        "truncated": False,
        "text": "",
        "error": "",
    }
    monkeypatch.setattr(
        gui,
        "preview_local_path",
        lambda _path: _Preview(sparse_preview),
    )
    dialog.refresh_local_preview()
    assert dialog.preview.toPlainText() == "C:/tmp/empty: directory"

    dialog.operations.setPlainText("not-a-transfer-action")
    dialog.refresh_queue_preview()
    assert dialog.preview.toPlainText().startswith("error:")
    dialog.operations.setPlainText(
        "# comment\n\nget /etc/hosts ./hosts.copy\nmkdir /tmp/release"
    )
    dialog.refresh_queue_preview()
    queue_preview = dialog.preview.toPlainText()
    assert "queue:" in queue_preview
    assert "1." in queue_preview
    assert "2." in queue_preview
    dialog.deleteLater()


def test_open_transfer_queue_selected_handles_selection_cancel_success_and_errors(
    gui_window,
    monkeypatch,
) -> None:
    from PyQt6.QtWidgets import QDialog

    from remote_ops_workspace import gui

    _app, window = gui_window
    messages: list[tuple[object, ...]] = []
    _set_closure_value(
        monkeypatch,
        type(window).open_transfer_queue_selected,
        "_literal_message_box",
        lambda *args, **_kwargs: messages.append(args),
    )
    monkeypatch.setattr(window, "selected_profile_name", lambda: None)
    window.open_transfer_queue_selected()
    assert messages

    profile = Profile(
        name="queue-selected",
        protocol="sftp",
        host="queue-selected.example.invalid",
        username="operator",
    )

    class _Store:
        def __init__(self, value) -> None:
            self.value = value

        def get(self, _name: str):
            if isinstance(self.value, Exception):
                raise self.value
            return self.value

    monkeypatch.setattr(window, "selected_profile_name", lambda: profile.name)
    window.store = _Store(KeyError("missing profile"))
    window.open_transfer_queue_selected()
    assert len(messages) == 2

    window.store = _Store(profile)
    monkeypatch.setattr(
        gui,
        "assert_profile_launch_allowed",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("policy blocked")),
    )
    window.open_transfer_queue_selected()
    assert len(messages) == 3

    monkeypatch.setattr(gui, "assert_profile_launch_allowed", lambda *_args, **_kwargs: None)

    class _Plan:
        batch_commands = ["get /remote /local"]
        notes = ["controlled note"]

        @staticmethod
        def printable() -> str:
            return "sftp queue-selected"

    class _Dialog:
        def __init__(self, result) -> None:
            self.result = result

        def exec(self):
            return self.result

        @staticmethod
        def queue_plan() -> _Plan:
            return _Plan()

    dialogs = iter(
        [
            _Dialog(QDialog.DialogCode.Rejected),
            _Dialog(QDialog.DialogCode.Accepted),
        ]
    )
    monkeypatch.setattr(
        window,
        "create_transfer_queue_dialog",
        lambda _profile: next(dialogs),
    )
    before = window.log.toPlainText()
    window.open_transfer_queue_selected()
    assert window.log.toPlainText() == before
    window.open_transfer_queue_selected()
    transcript = window.log.toPlainText()
    assert "QUEUE: sftp queue-selected" in transcript
    assert "get /remote /local" in transcript
    assert "controlled note" in transcript


def test_transfer_queue_guard_failure_and_callback_edges(
    gui_window,
    monkeypatch,
) -> None:
    from types import SimpleNamespace

    from PyQt6.QtCore import QProcess

    from remote_ops_workspace import gui

    _app, window = gui_window
    profile = Profile(
        name="queue-callback-edge",
        protocol="sftp",
        host="queue-callback.example.invalid",
        username="operator",
    )

    class _Signal:
        def __init__(self) -> None:
            self.callbacks = []

        def connect(self, callback) -> None:
            self.callbacks.append(callback)

    class _Process:
        def __init__(self, state=QProcess.ProcessState.Running) -> None:
            self.process_state = state
            self.readyReadStandardOutput = _Signal()
            self.readyReadStandardError = _Signal()
            self.started = _Signal()
            self.finished = _Signal()
            self.errorOccurred = _Signal()
            self.deleted = False
            self.terminated = False
            self.killed = False
            self.program = ""
            self.arguments: list[str] = []

        def state(self):
            return self.process_state

        def setProgram(self, program: str) -> None:  # noqa: N802
            self.program = program

        def setArguments(self, arguments: list[str]) -> None:  # noqa: N802
            self.arguments = list(arguments)

        def start(self) -> None:
            self.process_state = QProcess.ProcessState.Running

        @staticmethod
        def write(_payload: bytes) -> int:
            return 1

        @staticmethod
        def closeWriteChannel() -> None:  # noqa: N802
            return None

        def deleteLater(self) -> None:  # noqa: N802
            self.deleted = True

        def terminate(self) -> None:
            self.terminated = True

        def kill(self) -> None:
            self.killed = True
            self.process_state = QProcess.ProcessState.NotRunning

        @staticmethod
        def errorString() -> str:  # noqa: N802
            return "controlled start failure"

        @staticmethod
        def readAllStandardOutput() -> bytes:  # noqa: N802
            return b""

        @staticmethod
        def readAllStandardError() -> bytes:  # noqa: N802
            return b""

    invalid = window.create_transfer_queue_dialog(profile)
    invalid.operations.setPlainText("invalid transfer operation")
    invalid.run_queue()
    assert invalid.preview.toPlainText().startswith("error:")

    original_policy = gui.assert_profile_launch_allowed
    monkeypatch.setattr(
        gui,
        "assert_profile_launch_allowed",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("policy denied")),
    )
    invalid.operations.setPlainText("get /remote/file ./local-file")
    invalid.run_queue()
    assert invalid.preview.toPlainText() == "error: policy denied"
    monkeypatch.setattr(gui, "assert_profile_launch_allowed", original_policy)

    destructive = window.create_transfer_queue_dialog(profile)
    destructive.operations.setPlainText("rm /remote/old.txt")
    destructive.run_queue()
    assert "require Force destructive" in destructive.preview.toPlainText()

    processes: list[_Process] = []

    def process_factory(_parent):
        process = _Process()
        processes.append(process)
        return process

    dialog = window.create_transfer_queue_dialog(
        profile,
        process_factory=process_factory,
    )
    dialog.operations.setPlainText("get /remote/file ./local-file")
    dialog.run_queue()
    process = processes[-1]
    assert dialog.queue_is_active() is True
    dialog.run_queue()
    assert len(processes) == 1

    stale = _Process()
    dialog.finish_queue_item(stale, 0, 0)
    dialog.handle_queue_process_error(stale, 0, QProcess.ProcessError.FailedToStart)
    assert dialog.active_queue_process is process

    dialog.handle_queue_process_error(process, 0, QProcess.ProcessError.ReadError)
    assert dialog.queue_is_active() is True
    dialog.handle_queue_process_error(process, 0, QProcess.ProcessError.FailedToStart)
    assert dialog.queue_is_active() is False
    assert "controlled start failure" in dialog.preview.toPlainText()

    cancelled_error = _Process(QProcess.ProcessState.NotRunning)
    dialog.active_queue_plan = dialog.queue_plan()
    dialog.active_queue_process = cancelled_error
    dialog.queue_cancel_requested = True
    dialog.handle_queue_process_error(
        cancelled_error,
        0,
        QProcess.ProcessError.ReadError,
    )
    assert dialog.queue_is_active() is False
    assert "queue cancelled" in dialog.preview.toPlainText()

    stopping_error = _Process(QProcess.ProcessState.Running)
    dialog.active_queue_plan = dialog.queue_plan()
    dialog.active_queue_process = stopping_error
    dialog.queue_cancel_requested = True
    dialog.handle_queue_process_error(
        stopping_error,
        0,
        QProcess.ProcessError.ReadError,
    )
    assert dialog.active_queue_process is stopping_error
    dialog.queue_cancel_requested = False

    plan = dialog.queue_plan()
    failed = _Process()
    dialog.active_queue_plan = plan
    dialog.active_queue_process = failed
    dialog.finish_queue_item(failed, 0, 9)
    assert "failed (exit 9)" in dialog.preview.toPlainText()
    assert dialog.queue_is_active() is False

    cancelled = _Process()
    dialog.active_queue_plan = plan
    dialog.active_queue_process = cancelled
    dialog.queue_cancel_requested = True
    dialog.finish_queue_item(cancelled, 0, 0)
    assert "queue cancelled" in dialog.preview.toPlainText()

    completed = _Process()
    dialog.active_queue_plan = plan
    dialog.active_queue_process = completed
    dialog.queue_cancel_requested = False
    dialog.active_queue_index = 0
    dialog.finish_queue_item(completed, 0, 0)
    assert "queue completed" in dialog.preview.toPlainText()

    dialog.cancel_queue()
    dialog.active_queue_plan = plan
    dialog.queue_cancel_requested = True
    dialog.cancel_queue()
    dialog.queue_cancel_requested = False
    dialog.active_queue_process = None
    dialog.cancel_queue()
    assert dialog.queue_is_active() is False

    running = _Process()
    dialog.active_queue_plan = plan
    dialog.active_queue_process = running
    dialog.queue_cancel_requested = False
    dialog.cancel_queue()
    assert running.terminated is True
    assert dialog.queue_cancel_timer.isActive() is True
    dialog.kill_cancelled_queue_process()
    assert running.killed is True

    dialog.active_queue_plan = plan
    dialog.active_queue_process = SimpleNamespace(
        state=lambda: QProcess.ProcessState.NotRunning,
        deleteLater=lambda: None,
    )
    dialog.queue_cancel_requested = True
    dialog.kill_cancelled_queue_process()
    assert dialog.queue_is_active() is False
    dialog.kill_cancelled_queue_process()

    for item in (invalid, destructive, dialog):
        item.deleteLater()


def test_transfer_queue_completion_controls_and_modal_guards(gui_window) -> None:
    from types import SimpleNamespace

    from PyQt6.QtGui import QCloseEvent
    from PyQt6.QtWidgets import QDialog, QDialogButtonBox

    _app, window = gui_window
    profile = Profile(
        name="queue-modal-edge",
        protocol="sftp",
        host="queue-modal.example.invalid",
        username="operator",
    )
    dialog = window.create_transfer_queue_dialog(profile)
    dialog.operations.setPlainText("get /remote/file ./local-file")

    dialog.run_next_queue_item()
    plan = dialog.queue_plan()
    dialog.active_queue_plan = plan
    dialog.active_queue_index = len(plan.items)
    dialog.run_next_queue_item()
    assert dialog.queue_is_active() is False
    assert "queue completed" in dialog.preview.toPlainText()

    deleted: list[bool] = []
    dialog.active_queue_process = SimpleNamespace(
        deleteLater=lambda: deleted.append(True),
    )
    dialog.finish_queue_execution("")
    assert deleted == [True]

    requested_buttons: list[QDialogButtonBox.StandardButton] = []
    original_buttons = dialog.buttons
    dialog.buttons = SimpleNamespace(
        button=lambda standard: requested_buttons.append(standard),
    )
    dialog.set_queue_controls_active(True)
    assert requested_buttons == [
        QDialogButtonBox.StandardButton.Ok,
        QDialogButtonBox.StandardButton.Cancel,
    ]
    dialog.buttons = original_buttons

    dialog.active_queue_plan = plan
    initial_result = dialog.result()
    dialog.accept()
    dialog.reject()
    assert dialog.result() == initial_result
    close_event = QCloseEvent()
    dialog.closeEvent(close_event)
    assert close_event.isAccepted() is False

    dialog.active_queue_plan = None
    dialog.accept()
    assert dialog.result() == QDialog.DialogCode.Accepted
    dialog.deleteLater()


def test_transfer_queue_process_callbacks_forward_output_and_command(gui_window) -> None:
    from PyQt6.QtCore import QProcess

    _app, window = gui_window
    profile = Profile(
        name="queue-signal-edge",
        protocol="sftp",
        host="queue-signal.example.invalid",
        username="operator",
    )

    class _Signal:
        def __init__(self) -> None:
            self.callbacks = []

        def connect(self, callback) -> None:
            self.callbacks.append(callback)

    class _Process:
        def __init__(self) -> None:
            self.readyReadStandardOutput = _Signal()
            self.readyReadStandardError = _Signal()
            self.started = _Signal()
            self.finished = _Signal()
            self.errorOccurred = _Signal()
            self.program = ""
            self.arguments: list[str] = []
            self.writes: list[bytes] = []
            self.closed = False
            self.deleted = False

        def setProgram(self, program: str) -> None:  # noqa: N802
            self.program = program

        def setArguments(self, arguments: list[str]) -> None:  # noqa: N802
            self.arguments = list(arguments)

        @staticmethod
        def start() -> None:
            return None

        @staticmethod
        def readAllStandardOutput() -> bytes:  # noqa: N802
            return b"controlled stdout\n"

        @staticmethod
        def readAllStandardError() -> bytes:  # noqa: N802
            return b"controlled stderr\n"

        def write(self, payload: bytes) -> int:
            self.writes.append(payload)
            return len(payload)

        def closeWriteChannel(self) -> None:  # noqa: N802
            self.closed = True

        def deleteLater(self) -> None:  # noqa: N802
            self.deleted = True

    process = _Process()
    dialog = window.create_transfer_queue_dialog(
        profile,
        process_factory=lambda _parent: process,
    )
    dialog.operations.setPlainText("get /remote/file ./local-file")
    dialog.run_queue()

    process.readyReadStandardOutput.callbacks[0]()
    process.readyReadStandardError.callbacks[0]()
    process.started.callbacks[0]()
    transcript = dialog.preview.toPlainText()
    assert "controlled stdout" in transcript
    assert "controlled stderr" in transcript
    assert process.writes and process.writes[0].endswith(b"\n")
    assert process.closed is True

    process.finished.callbacks[0](0, QProcess.ExitStatus.NormalExit)
    assert process.deleted is True
    assert dialog.queue_is_active() is False
    assert "queue completed" in dialog.preview.toPlainText()
    dialog.deleteLater()


def test_workflow_dialog_action_closes_then_runs_callback(gui_window) -> None:
    from PyQt6.QtWidgets import QDialog, QToolButton

    _app, window = gui_window
    calls: list[str] = []
    dialog = window.create_workflow_dialog(
        "Workflow edge",
        "Operator action",
        [("Check", "ready", "controlled")],
        "literal detail",
        actions=[("Run controlled action", lambda: calls.append("run"))],
    )
    action = next(
        button
        for button in dialog.findChildren(QToolButton, "workflowAction")
        if button.text() == "Run controlled action"
    )
    action.click()
    assert dialog.result() == QDialog.DialogCode.Accepted
    assert calls == ["run"]
    dialog.deleteLater()

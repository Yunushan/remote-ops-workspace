from __future__ import annotations

import os

import pytest

from remote_ops_workspace.models import Profile
from remote_ops_workspace.terminal import TerminalPanePlan


class _FakeProcess:
    def __init__(self, *, running: bool = False, pipe_fallback: bool = False) -> None:
        from PyQt6.QtCore import QProcess

        self.process_state = (
            QProcess.ProcessState.Running
            if running
            else QProcess.ProcessState.NotRunning
        )
        self.is_pty = False
        self.pipe_fallback = pipe_fallback
        self.program = ""
        self.arguments: list[str] = []
        self.start_calls = 0
        self.terminate_calls = 0
        self.kill_calls = 0
        self.written = b""
        self.stdout = b""
        self.stderr = b""
        self.terminal_sizes: list[tuple[int, int]] = []

    def state(self):
        return self.process_state

    def property(self, name: str):
        if name == "terminalOpenSshPipeFallback":
            return self.pipe_fallback
        return None

    def setProgram(self, program: str) -> None:  # noqa: N802
        self.program = program

    def setArguments(self, arguments: list[str]) -> None:  # noqa: N802
        self.arguments = list(arguments)

    def setTerminalSize(self, columns: int, rows: int) -> None:  # noqa: N802
        self.terminal_sizes.append((columns, rows))

    def start(self) -> None:
        from PyQt6.QtCore import QProcess

        self.start_calls += 1
        self.process_state = QProcess.ProcessState.Running

    def terminate(self) -> None:
        self.terminate_calls += 1

    def kill(self) -> None:
        self.kill_calls += 1

    def write(self, payload: bytes) -> int:
        self.written += payload
        return len(payload)

    def readAllStandardOutput(self) -> bytes:  # noqa: N802
        payload, self.stdout = self.stdout, b""
        return payload

    def readAllStandardError(self) -> bytes:  # noqa: N802
        payload, self.stderr = self.stderr, b""
        return payload


@pytest.fixture
def gui_window(monkeypatch, tmp_path):
    if "QT_QPA_PLATFORM" not in os.environ:
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("ROW_HOME", str(tmp_path / "row-home"))
    pytest.importorskip("PyQt6")
    from remote_ops_workspace.gui import create_main_window

    app, window = create_main_window(
        ["gui-terminal-edges"],
        show=False,
        preview_samples=False,
    )
    window.resize(1024, 720)
    window.show()
    app.processEvents()
    yield app, window
    window.close()
    app.processEvents()


def _new_pane(window, *, command: list[str] | None = None):
    return window.new_terminal_pane(
        TerminalPanePlan(
            title="edge-terminal",
            command=list(command or []),
            source="test",
            notes=["controlled test note"],
        ),
        autostart=False,
    )


def test_managed_ssh_pane_tracks_start_stop_exit_and_launch_failure(gui_window, monkeypatch) -> None:
    from PyQt6.QtCore import QProcess

    from remote_ops_workspace import gui_terminal
    from remote_ops_workspace.gui_lifecycle import ProcessStopResult

    _app, window = gui_window
    profile = Profile(name="managed", protocol="ssh", host="managed.example.invalid")
    monkeypatch.setattr(gui_terminal, "ssh_control_path_for_profile", lambda _profile: "/managed/socket")
    monkeypatch.setattr(
        gui_terminal, "ssh_command_with_control_path",
        lambda command, _path, **_kwargs: [*command, "-managed"],
    )
    pane = window.new_terminal_pane(
        TerminalPanePlan("managed", ["ssh", "managed.example.invalid"], "test"),
        profile=profile,
        autostart=False,
    )
    session = pane.ssh_connection
    assert session is not None
    assert pane.status.property("sshConnectionState")["phase"] == "idle"
    assert "Ready to connect" in pane.status.toolTip()
    process = _FakeProcess()
    pane.process = process
    pane.start()
    pane.on_started()
    assert session.state.phase == "authenticating"
    assert pane.request_stop(restart=True)
    assert session.state.disconnect_reason == "restart-requested"
    pane._restart_after_stop = False
    process.process_state = QProcess.ProcessState.NotRunning
    pane.on_finished(-15, QProcess.ExitStatus.CrashExit)
    assert pane.output.property("sshConnectionState")["exit_code"] == -15
    assert session.state.phase == "closed"

    pane.start()
    process.process_state = QProcess.ProcessState.NotRunning
    process.errorString = lambda: "controlled missing executable"
    pane.on_error(QProcess.ProcessError.FailedToStart)
    assert session.state.disconnect_reason == "launch-failed"
    assert session.state.exit_code is None

    pane.start()
    monkeypatch.setattr(
        gui_terminal, "stop_process",
        lambda *_args, **_kwargs: ProcessStopResult(
            was_running=True, terminate_requested=True, kill_requested=False, finished=True,
        ),
    )
    pane.stop()
    assert session.state.disconnect_reason == "operator-stop"
    pane.prepare_for_close()
    assert session.state.disconnect_reason == "operator-stop"
    process.process_state = QProcess.ProcessState.NotRunning

    sftp = window.new_terminal_pane(
        TerminalPanePlan("managed SFTP", ["sftp", "managed.example.invalid"], "test"),
        profile=profile,
        autostart=False,
    )
    assert sftp.ssh_connection is not None
    assert sftp.ssh_connection._check.program() == "ssh"


def test_terminal_start_restart_and_nonblocking_stop_edges(
    gui_window,
    monkeypatch,
) -> None:
    from PyQt6.QtCore import QProcess

    from remote_ops_workspace import gui_terminal
    from remote_ops_workspace.gui_lifecycle import ProcessStopPolicy, ProcessStopResult

    _app, window = gui_window
    pane = _new_pane(window)
    process = _FakeProcess(running=True)
    pane.process = process

    pane.start()
    assert process.start_calls == 0

    process.process_state = QProcess.ProcessState.NotRunning
    pane.start()
    assert "empty terminal command" in pane.output.toPlainText()

    pane.plan = TerminalPanePlan(
        title="edge-terminal",
        command=["ssh", "original.example.invalid"],
        source="test",
    )
    pane._process_output_buffer.append(b"tail")
    pane.start()
    assert pane._restart_when_output_drained is True
    assert pane.status.text() == "draining output"
    pane.reset_process_output_pipeline()

    pane.profile = Profile(
        name="blocked",
        protocol="ssh",
        host="blocked.example.invalid",
        username="operator",
    )
    monkeypatch.setattr(
        gui_terminal,
        "assert_profile_launch_allowed",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("controlled policy")),
    )
    pane.start()
    assert pane.status.text() == "policy blocked"
    assert "controlled policy" in pane.output.toPlainText()

    monkeypatch.setattr(gui_terminal, "assert_profile_launch_allowed", lambda *_args, **_kwargs: None)
    process.pipe_fallback = True
    pane.setProperty(
        "terminalRuntimeCommand",
        ["ssh", "runtime.example.invalid"],
    )
    pane.start()
    assert process.start_calls == 1
    assert process.program == "ssh"
    assert "runtime.example.invalid" in process.arguments
    assert "BatchMode=yes" in process.arguments
    pane.flush_terminal_resize()
    assert process.terminal_sizes
    pane.flush_terminal_resize()

    restart_requests: list[bool] = []
    pane.request_stop = lambda *_args, restart=False, **_kwargs: restart_requests.append(
        restart
    )
    pane.restart()
    assert restart_requests == [True]
    process.process_state = QProcess.ProcessState.NotRunning
    starts: list[str] = []
    pane.start = lambda: starts.append("start")
    pane.restart()
    assert starts == ["start"]

    pane = _new_pane(window, command=["ssh", "stop.example.invalid"])
    process = _FakeProcess(running=False)
    pane.process = process
    deferred_starts: list[str] = []
    pane.start = lambda: deferred_starts.append("start")
    pane.setProperty("terminalClosing", True)
    assert pane.request_stop(restart=True) is False
    assert pane._restart_after_stop is False
    pane.setProperty("terminalClosing", False)
    assert pane.request_stop(restart=True) is False
    _app.processEvents()
    assert deferred_starts == ["start"]

    process.process_state = QProcess.ProcessState.Running
    assert pane.request_stop(
        policy=ProcessStopPolicy(terminate_timeout_ms=7, kill_timeout_ms=0)
    ) is True
    assert process.terminate_calls == 1
    assert pane._stop_timer.interval() == 7
    pane.kill_after_stop_timeout()
    assert process.kill_calls == 1
    process.process_state = QProcess.ProcessState.NotRunning
    pane.kill_after_stop_timeout()

    non_running = pane.stop()
    assert non_running.was_running is False

    outcomes = iter(
        [
            ProcessStopResult(True, True, True, False),
            ProcessStopResult(True, True, False, True),
        ]
    )
    monkeypatch.setattr(gui_terminal, "stop_process", lambda *_args, **_kwargs: next(outcomes))
    process.process_state = QProcess.ProcessState.Running
    first = pane.stop()
    second = pane.stop()
    assert first.kill_requested is True and first.finished is False
    assert second.kill_requested is False and second.finished is True
    transcript = pane.output.toPlainText()
    assert "killed after graceful stop timeout" in transcript
    assert "did not exit after kill request" in transcript


@pytest.fixture
def macro_workspace(gui_window, monkeypatch):
    from remote_ops_workspace.moba_macros import MobaMacroStore

    _app, window = gui_window
    pane = _new_pane(window)
    pane.process = _FakeProcess(running=True)
    pane.update_process_actions()
    active = [pane]
    monkeypatch.setattr(window, "active_terminal_pane", lambda: active[0])
    menu = next(menu for menu in window.moba_top_menus if menu.property("mobaTopMenuKey") == "macros")

    def popup():
        menu.aboutToShow.emit()
        return {action.text(): action for action in menu.actions() if not action.isSeparator()}

    return window, pane, active, popup, MobaMacroStore()


def test_moba_quick_macro_keyboard_filter_and_guarded_replay(macro_workspace, monkeypatch):
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication, QLineEdit, QListWidget

    from remote_ops_workspace.moba_macros import record_typed_macro

    window, pane, active, _menu, store = macro_workspace
    window.set_design_preset("mobaxterm")
    window.add_workspace_tab(pane, "quick macro test")
    window.activateWindow()
    store.add(record_typed_macro("01 apple", "first"))
    store.add(record_typed_macro("02 PEAR", "second"))
    reviewed = []
    accept = [False]

    def review(recording):
        reviewed.append(recording.name)
        return accept[0]

    monkeypatch.setattr(pane, "confirm_macro_replay", review)

    def show():
        pane.output.setFocus()
        QTest.keyClick(pane.output, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)
        popup = QApplication.activePopupWidget()
        assert popup.objectName() == "mobaQuickMacroPopup"
        search = popup.findChild(QLineEdit, "mobaQuickMacroFilter")
        assert popup.focusWidget() is search
        return search, popup.findChild(QListWidget, "mobaQuickMacroNames")

    search, names = show()
    assert search.placeholderText() == "Search macro"
    assert [names.item(row).text() for row in range(names.count())] == [
        "01 apple", "02 PEAR", "Record new macro...",
    ]
    initial_height = search.window().height()
    assert names.currentItem().text() == "01 apple"
    QTest.keyClick(search, Qt.Key.Key_Down)
    assert names.currentItem().text() == "02 PEAR"
    QTest.keyClick(search, Qt.Key.Key_Up)
    assert names.currentItem().text() == "01 apple"
    QTest.keyClicks(search, "absent")
    assert names.count() == 0
    assert search.window().height() < initial_height
    QTest.keyClick(search, Qt.Key.Key_Return)
    assert QApplication.activePopupWidget() is not None
    QTest.keyClick(search, Qt.Key.Key_Escape)
    assert QApplication.activePopupWidget() is None
    assert not reviewed and pane.process.written == b""

    search, names = show()
    QTest.keyClicks(search, "ear")
    assert names.count() == 1 and names.currentItem().text() == "02 PEAR"
    QTest.keyClick(search, Qt.Key.Key_Return)
    QTest.qWait(5)
    assert reviewed == ["02 PEAR"] and pane.process.written == b""

    accept[0] = True
    search, names = show()
    active[0] = None
    QTest.keyClick(search, Qt.Key.Key_Return)
    QTest.qWait(5)
    assert reviewed == ["02 PEAR"] and pane.process.written == b""
    active[0] = pane
    _search, names = show()
    point = names.visualItemRect(names.item(0)).center()
    QTest.mouseClick(names.viewport(), Qt.MouseButton.LeftButton, pos=point)
    QTest.qWait(20)
    assert reviewed == ["02 PEAR", "01 apple"] and pane.process.written == b"first\n"
    window.tabs.removeTab(window.tabs.indexOf(pane))


def test_quick_macro_command_and_identically_named_recording_are_distinct(macro_workspace, monkeypatch):
    from PyQt6.QtCore import Qt
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication, QLineEdit, QListWidget

    from remote_ops_workspace.moba_macros import record_typed_macro

    window, pane, _active, _menu, store = macro_workspace
    window.set_design_preset("mobaxterm")
    window.add_workspace_tab(pane, "recording origin")
    window.activateWindow()

    def chooser():
        pane.output.setFocus()
        QTest.keyClick(pane.output, Qt.Key.Key_Space, Qt.KeyboardModifier.ControlModifier)
        popup = QApplication.activePopupWidget()
        search = popup.findChild(QLineEdit, "mobaQuickMacroFilter")
        QTest.keyClicks(search, "REC")
        return search, popup.findChild(QListWidget, "mobaQuickMacroNames")

    search, names = chooser()
    label = "Record new macro..."
    assert names.count() == 1 and names.currentItem().text() == label
    QTest.keyClick(search, Qt.Key.Key_Return)
    QTest.qWait(5)
    assert pane.macro_capture_state.active and pane.process.written == b""
    pane.cancel_macro_capture()

    store.add(record_typed_macro(label, "idle"))
    search, names = chooser()
    assert [names.item(i).text() for i in range(2)] == [label, label]
    reviewed = []
    monkeypatch.setattr(pane, "confirm_macro_replay", lambda recording: reviewed.append(recording.name) or False)
    item = names.currentItem()
    # These signals can both be emitted by a Qt style for one activation.
    names.itemClicked.emit(item)
    names.itemActivated.emit(item)
    QTest.qWait(5)
    assert reviewed == [label] and pane.macro_capture_state is None
    window.tabs.removeTab(window.tabs.indexOf(pane))


def test_quick_macro_key_is_local_only_to_moba_terminal_output(macro_workspace):
    from PyQt6.QtCore import QEvent, Qt
    from PyQt6.QtGui import QKeyEvent
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication

    window, pane, active, _menu, _store = macro_workspace
    ctrl = Qt.KeyboardModifier.ControlModifier
    # A standalone pane and other presets still use the conventional TTY mapping.
    assert pane.output.terminal_cursor_rect().width() > 0
    QTest.keyClick(pane.output, Qt.Key.Key_Space, ctrl)
    window.set_design_preset("native")
    window.add_workspace_tab(pane, "key scope test")
    QTest.keyClick(pane.output, Qt.Key.Key_Space, ctrl)
    window.set_design_preset("mobaxterm")
    active[0] = None
    assert not window.open_moba_quick_macros(pane)
    active[0] = pane
    event = QKeyEvent(QEvent.Type.KeyPress, Qt.Key.Key_Space, ctrl | Qt.KeyboardModifier.AltModifier, " ")
    QApplication.sendEvent(pane.output, event)
    assert pane.process.written == b"\x00\x00 "
    QTest.keyClick(window.quick_connect, Qt.Key.Key_Space, ctrl)
    assert QApplication.activePopupWidget() is None
    window.tabs.removeTab(window.tabs.indexOf(pane))


def test_moba_recording_ribbon_follows_the_active_terminal(macro_workspace, monkeypatch):
    from PyQt6.QtWidgets import QInputDialog

    window, pane, active, popup, store = macro_workspace
    window.set_design_preset("mobaxterm")
    popup()["Record new macro"].trigger()
    assert window.moba_recording_label.isVisible() and window.moba_recording_stop.isVisible()
    assert not window.moba_x_server_button.isVisible()

    active[0] = None
    window.refresh_moba_recording_ribbon()
    assert not window.moba_recording_stop.isVisible()
    assert window.moba_x_server_button.isVisible()
    active[0] = pane
    window.refresh_moba_recording_ribbon()
    pane.capture_macro_input("recorded", enter=False)
    monkeypatch.setattr(QInputDialog, "getText", lambda *_args: ("ribbon", True))
    window.moba_recording_stop.click()
    assert store.get("ribbon").input_text == "recorded"
    assert not window.moba_recording_label.isVisible()
    assert window.moba_x_server_button.isVisible()


def test_moba_macros_menu_records_names_and_replays_the_current_session(macro_workspace, monkeypatch):
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QInputDialog

    window, pane, active, popup, store = macro_workspace
    actions = popup()
    assert not actions["Saved macros"].isEnabled()
    actions["Record new macro"].trigger()
    pane.capture_macro_input("unlisted input", enter=False)
    pane.macro_capture_state.events[0].delay_ms = 0
    names = iter([(" ", True), ("alpha&beta", True)])
    monkeypatch.setattr(QInputDialog, "getText", lambda *_: next(names))
    popup()["Stop recording"].trigger()
    assert store.get("alpha&beta").input_text == "unlisted input"
    before = pane.macro_last_recording
    actions = popup()
    assert "alpha&&beta" in actions and "unlisted input" not in str(actions)

    monkeypatch.setattr(pane, "confirm_macro_replay", lambda _record: False)
    actions["alpha&&beta"].trigger()
    assert pane.macro_last_recording is before and pane.process.written == b""
    monkeypatch.setattr(pane, "confirm_macro_replay", lambda _record: True)
    actions["alpha&&beta"].trigger()
    assert popup()["Cancel replay"].isEnabled()
    QTest.qWait(10)
    assert pane.process.written == b"unlisted input"

    popup()["Record new macro"].trigger()
    pane.capture_macro_input("another recording")
    names = iter([("alpha&beta", True), ("", False)])
    popup()["Stop recording"].trigger()
    assert pane.macro_last_recording is before and store.get("alpha&beta").input_text == "unlisted input"
    popup()["Record new macro"].trigger()
    popup()["Cancel recording"].trigger()
    assert pane.macro_capture_state is None
    action = popup()["alpha&&beta"]
    active[0] = None
    action.trigger()
    assert pane.process.written == b"unlisted input"
    assert not popup()["Record new macro"].isEnabled()
    assert not popup()["alpha&&beta"].isEnabled()

    active[0] = pane
    popup()["Record new macro"].trigger()
    pane.capture_macro_input("discard")

    def switch(*_args):
        active[0] = None
        return "wrong tab", True

    monkeypatch.setattr(QInputDialog, "getText", switch)
    popup()["Stop recording"].trigger()
    assert [record.name for record in store.load()] == ["alpha&beta"]
    assert pane.macro_last_recording is before
    active[0] = pane
    monkeypatch.setattr(pane, "confirm_macro_replay", lambda _: switch()[1])
    popup()["alpha&&beta"].trigger()
    QTest.qWait(10)
    assert pane.process.written == b"unlisted input"


def test_moba_macros_dialog_selects_saved_entries_and_preserves_private_input(macro_workspace, monkeypatch):
    from remote_ops_workspace.moba_macros import record_typed_macro

    window, pane, _active, popup, store = macro_workspace
    store.add(record_typed_macro("first", "private first"))
    store.add(record_typed_macro("second", "private second"))
    reviewed = []
    monkeypatch.setattr(pane, "confirm_macro_replay", lambda record: reviewed.append(record.name))

    def choose(title, subtitle, rows, detail, *, actions, prepare):
        dialog = window.create_workflow_dialog(title, subtitle, rows, detail, actions=actions)
        prepare(dialog)
        assert "private" not in str(rows) + dialog.detail.toPlainText()
        dialog.rows.setCurrentItem(dialog.rows.topLevelItem(1))
        dict(actions)["Replay selected"]()
        dialog.rows.clear()
        dialog.close()

    monkeypatch.setattr(window, "show_workflow_dialog", choose)
    window.show_moba_macros_status()
    assert reviewed == ["second"]
    pane.start_macro_capture()
    pane.capture_macro_input("volatile")
    pane.stop_macro_capture()
    popup()["Replay last recording"].trigger()
    assert reviewed[-1] == pane.macro_last_recording.name


def test_moba_macros_rejects_unreadable_removed_or_invalid_recordings(macro_workspace, monkeypatch):
    from PyQt6.QtWidgets import QInputDialog

    from remote_ops_workspace.moba_macros import record_typed_macro

    window, pane, active, popup, store = macro_workspace
    recording = record_typed_macro("stale", "private event")
    store.add(recording)
    stale = popup()["stale"]
    store.remove("stale")
    stale.trigger()
    assert "could not be replayed" in window.statusBar().currentMessage()
    recording.events[0].delay_ms = -1
    store.add(recording)
    popup()["stale"].trigger()
    assert pane.process.written == b""
    store.path.write_text('{"macros":[{"events":[{"text":"private event"}]}]}', encoding="utf-8")
    actions = popup()
    assert "could not be read" in window.statusBar().currentMessage()
    actions["Record new macro"].trigger()
    pane.capture_macro_input("private event")
    monkeypatch.setattr(QInputDialog, "getText", lambda *_: ("save", True))
    popup()["Stop recording"].trigger()
    assert "could not be updated" in window.statusBar().currentMessage()
    assert pane.macro_last_recording is None
    controls = window.moba_macro_controls()
    active[0] = None
    controls.record()
    controls.stop()
    controls.cancel()
    controls.replay_last()
    assert controls.save(recording) is None
    assert pane.macro_capture_state is None


def test_closing_the_macro_destination_during_naming_discards_the_new_recording(macro_workspace, monkeypatch):
    from PyQt6.QtWidgets import QInputDialog

    _window, pane, _active, popup, store = macro_workspace
    popup()["Record new macro"].trigger()
    pane.capture_macro_input("discard")

    def close_during_naming(*_args):
        pane.prepare_for_close()
        return "abandoned", True

    monkeypatch.setattr(QInputDialog, "getText", close_during_naming)
    popup()["Stop recording"].trigger()
    assert not store.path.exists()
    assert pane.macro_last_recording is None
    assert not popup()["Record new macro"].isEnabled()


def test_terminal_macro_capture_replay_and_cancel_edges(
    gui_window,
    monkeypatch,
) -> None:
    from PyQt6.QtCore import QProcess
    from PyQt6.QtTest import QTest

    from remote_ops_workspace import gui_terminal
    from remote_ops_workspace.moba_macros import MobaMacroEvent, MobaMacroRecording

    _app, window = gui_window
    pane = _new_pane(window, command=["ssh", "macro.example.invalid"])
    process = _FakeProcess(running=False)
    pane.process = process

    pane._secret_prompt_active = True
    pane.start_macro_capture()
    pane.replay_macro_capture()
    assert "unavailable during secret input" in pane.output.toPlainText()

    pane._secret_prompt_active = False
    pane.replay_macro_capture()
    assert "no recorded macro" in pane.output.toPlainText()

    pane.start_macro_capture()
    state = pane.macro_capture_state
    assert state is not None and state.active
    pane.start_macro_capture()
    pane.capture_macro_input("echo ready")
    assert len(state.events) == 1
    pane.stop_macro_capture()
    assert pane.macro_last_recording is not None

    pane.start_macro_capture()
    pane.stop_macro_capture()
    assert "recording ignored" in pane.output.toPlainText()
    pane.stop_macro_capture()

    pane.start_macro_capture()
    pane.cancel_macro_capture()
    assert pane.macro_capture_state is None
    pane.macro_replay_active = True
    pane.cancel_macro_capture()
    assert pane.macro_replay_cancelled is True
    pane.cancel_macro_capture()

    pane.macro_last_event_at = None
    first_delay = pane.macro_event_delay_ms()
    pane.macro_last_event_at = 10.0
    values = iter([9.0, 12.5])
    monkeypatch.setattr(gui_terminal.time, "monotonic", lambda: next(values))
    second_delay = pane.macro_event_delay_ms()
    assert first_delay >= 0
    assert second_delay == 0

    pane.macro_last_recording = MobaMacroRecording(
        name="edge-replay",
        events=[MobaMacroEvent(index=1, text="uptime", enter=True, delay_ms=3)],
    )
    pane.replay_macro_capture()
    assert "process is not running" in pane.output.toPlainText()

    process.process_state = QProcess.ProcessState.Running
    monkeypatch.setattr(pane, "confirm_macro_replay", lambda _recording: True)
    pane.replay_macro_capture()
    assert pane.macro_replay_active is True
    QTest.qWait(20)
    _app.processEvents()
    assert process.written.endswith(b"uptime\n")
    assert pane.macro_replay_active is False

    sequence = pane.macro_replay_sequence
    before = process.written
    pane.write_macro_replay_payload("ignored", sequence + 1)
    pane.macro_replay_cancelled = True
    pane.write_macro_replay_payload("ignored", sequence)
    assert process.written == before

    pane.macro_replay_cancelled = False
    process.process_state = QProcess.ProcessState.NotRunning
    pane.macro_replay_active = True
    pane.write_macro_replay_payload("stopped", sequence)
    assert pane.macro_replay_active is False

    process.process_state = QProcess.ProcessState.Running
    pane.write_macro_replay_payload("accepted", sequence)
    assert process.written.endswith(b"accepted")
    pane.macro_replay_active = True
    pane.finish_macro_replay_queue(sequence + 1)
    assert pane.macro_replay_active is True
    pane.finish_macro_replay_queue(sequence)
    assert pane.macro_replay_active is False


def test_macro_record_button_returns_focus_to_terminal_and_replay_preserves_bytes(gui_window, tmp_path) -> None:
    import sys

    from PyQt6.QtCore import Qt, QTimer
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QApplication, QMessageBox

    app, window = gui_window
    received = tmp_path / "received.bin"
    child = """
import pathlib
import sys

sink = pathlib.Path(sys.argv[1])
for line in sys.stdin.buffer:
    with sink.open("ab") as out:
        out.write(line)
"""
    plan = TerminalPanePlan(title="Local macro fixture", command=[sys.executable, "-u", "-c", child, str(received)], source="test")
    window.set_design_preset("mobaxterm")
    window.open_terminal_tab(plan)
    pane = window.active_terminal_pane()
    def wait_for(predicate):
        for _ in range(200):
            if predicate():
                return
            QTest.qWait(10)
        assert predicate()

    try:
        wait_for(lambda: pane.is_running() and pane.macro_record_button.isEnabled())
        window.activateWindow()
        pane.macro_record_button.setFocus()
        QTest.keyClick(pane.macro_record_button, Qt.Key.Key_Space)
        app.processEvents()
        assert app.focusWidget() is pane.output
        QTest.keyClicks(app.focusWidget(), "typed")
        QTest.keyClick(app.focusWidget(), Qt.Key.Key_Tab)
        QTest.keyClicks(app.focusWidget(), "42")
        QTest.keyClick(app.focusWidget(), Qt.Key.Key_Return)
        QTest.mouseClick(pane.macro_stop_button, Qt.MouseButton.LeftButton)
        wait_for(received.exists)
        assert received.read_bytes() == b"typed\t42\n"
        saved = pane.macro_last_recording
        assert saved is not None and saved.input_text == "typed\t42\n"
        QTest.mouseClick(pane.macro_record_button, Qt.MouseButton.LeftButton)
        QTest.keyClicks(app.focusWidget(), "undo")
        QTest.keyClick(app.focusWidget(), Qt.Key.Key_Return)
        QTest.mouseClick(pane.macro_cancel_button, Qt.MouseButton.LeftButton)
        assert pane.macro_last_recording is saved
        wait_for(lambda: received.read_bytes() == b"typed\t42\nundo\n")

        def answer(review_button):
            box = QApplication.activeModalWidget()
            assert isinstance(box, QMessageBox)
            assert box.defaultButton() is box.button(QMessageBox.StandardButton.Cancel)
            QTest.mouseClick(box.button(review_button), Qt.MouseButton.LeftButton)

        for choice in (QMessageBox.StandardButton.Cancel, QMessageBox.StandardButton.Yes):
            QTimer.singleShot(0, lambda button=choice: answer(button))
            QTest.mouseClick(pane.macro_replay_button, Qt.MouseButton.LeftButton)
            if choice == QMessageBox.StandardButton.Cancel:
                assert not pane.macro_replay_active
                assert received.read_bytes() == b"typed\t42\nundo\n"
        wait_for(lambda: received.read_bytes() == b"typed\t42\nundo\ntyped\t42\n")
    finally:
        pane.process.kill()
        wait_for(lambda: not pane.is_running())


def test_terminal_macro_review_guards_ordered_keys_and_session_changes(gui_window, monkeypatch) -> None:
    from PyQt6.QtCore import QTimer
    from PyQt6.QtTest import QTest
    from PyQt6.QtWidgets import QMessageBox

    app, window = gui_window
    pane = _new_pane(window, command=["ssh", "macro.example.invalid"])
    process = _FakeProcess(running=True)
    pane.process = process
    pane.start_macro_capture()
    pane.send_raw_input(b"a", record_macro=True)
    pane.send_raw_input(b"\n", record_macro=True)
    pane.stop_macro_capture()
    assert pane.macro_last_recording is not None
    recording = pane.macro_last_recording
    assert [(event.text, event.enter) for event in recording.events] == [("a", False), ("", True)]
    process.written = b""

    observed_defaults = []

    def choose(button):
        dialog = app.activeModalWidget()
        assert isinstance(dialog, QMessageBox)
        observed_defaults.append(dialog.defaultButton() is dialog.button(QMessageBox.StandardButton.Cancel))
        dialog.button(button).click()

    QTimer.singleShot(0, lambda: choose(QMessageBox.StandardButton.Cancel))
    pane.replay_macro_capture()
    QTest.qWait(15)
    assert process.written == b""

    process.is_pty = True
    QTimer.singleShot(0, lambda: choose(QMessageBox.StandardButton.Yes))
    pane.replay_macro_capture()
    assert not pane.macro_replay_button.isEnabled()
    pane.replay_macro_capture()
    QTest.qWait(35)
    assert observed_defaults == [True, True]
    assert process.written == b"a\r"
    process.written = b""

    def change_during_review(_recording):
        pane.invalidate_macro_session()
        return True

    monkeypatch.setattr(pane, "confirm_macro_replay", change_during_review)
    pane.replay_macro_capture()
    assert process.written == b""
    assert "session changed during review" in pane.output.toPlainText()

    recording.events[0].delay_ms = 55
    monkeypatch.setattr(pane, "confirm_macro_replay", lambda _recording: True)
    pane.replay_macro_capture()
    pane.refresh_terminal_input_security("Password: ")
    QTest.qWait(80)
    assert pane._secret_prompt_active and pane.macro_replay_cancelled
    assert process.written == b""
    pane.refresh_terminal_input_security("")

    pane.replay_macro_capture()
    pane._secret_prompt_active = True
    pane.write_macro_replay_payload("not sent", pane.macro_replay_sequence)
    assert process.written == b"" and not pane.macro_replay_active
    pane.refresh_terminal_input_security("")

    pane.start_macro_capture()
    pane.send_raw_input(b"\x7f", record_macro=True)
    assert pane.macro_capture_state is None
    assert "unsupported terminal key" in pane.output.toPlainText()

    recording.events[0].delay_ms = 0
    monkeypatch.setattr(process, "write", lambda _payload: 0)
    pane.start_macro_capture()
    pane.send_raw_input(b"partial", record_macro=True)
    assert pane.macro_capture_state is None
    pane.replay_macro_capture()
    QTest.qWait(30)
    assert "did not accept the complete event" in pane.output.toPlainText()

    def close_during_review(_recording):
        pane.prepare_for_close()
        return True

    monkeypatch.setattr(pane, "confirm_macro_replay", close_during_review)
    prior_input = process.written
    pane.replay_macro_capture()
    assert not pane.macro_replay_active and process.written == prior_input


def test_terminal_finished_restart_waits_for_ordered_output_tail(
    gui_window,
) -> None:
    from PyQt6.QtCore import QProcess

    _app, window = gui_window
    pane = _new_pane(window, command=["ssh", "finish.example.invalid"])
    process = _FakeProcess(running=False)
    pane.process = process
    starts: list[str] = []
    pane.start = lambda: starts.append("start")
    flush_now = pane.flush_process_output_now
    pane.flush_process_output_now = lambda: setattr(
        pane,
        "_process_output_flush_scheduled",
        True,
    )
    pane._restart_after_stop = True
    pane.on_finished(0, QProcess.ExitStatus.NormalExit)
    assert pane._restart_when_output_drained is True
    assert starts == []

    pane.reset_process_output_pipeline()
    pane.flush_process_output_now = flush_now
    pane._restart_when_output_drained = False
    pane._restart_after_stop = False
    pane._restart_after_stop = True
    pane.on_finished(7, QProcess.ExitStatus.CrashExit)
    assert pane.status.property("state") == "error"
    _app.processEvents()
    assert starts == ["start"]

    pane.setProperty("terminalClosing", True)
    pane._restart_after_stop = True
    pane.on_finished(0, QProcess.ExitStatus.NormalExit)
    assert pane._restart_after_stop is True

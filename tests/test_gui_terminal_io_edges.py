from __future__ import annotations

import os
from types import SimpleNamespace

import pytest

from remote_ops_workspace.terminal import TerminalPanePlan


def _closure_value(function, name: str):
    index = function.__code__.co_freevars.index(name)
    closure = function.__closure__
    assert closure is not None
    return closure[index].cell_contents


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
        ["gui-terminal-io-edges"],
        show=False,
        preview_samples=False,
    )
    window.resize(1024, 720)
    window.show()
    app.processEvents()
    yield app, window
    window.close()
    app.processEvents()


def _new_pane(window):
    return window.new_terminal_pane(
        TerminalPanePlan(
            title="terminal-io-edge",
            command=["ssh", "edge.example.invalid"],
            source="test",
            notes=["controlled test note"],
        ),
        autostart=False,
    )


def test_terminal_auth_prompt_transitions_are_notified_once(gui_window) -> None:
    _app, window = gui_window
    pane = _new_pane(window)
    transitions: list[bool] = []
    pane.set_terminal_authentication_change_handler(
        lambda _pane, prompt_active: transitions.append(prompt_active)
    )

    pane.refresh_terminal_input_security("password: ")
    pane.refresh_terminal_input_security("password: ")
    pane.refresh_terminal_input_security("root@host:~$ ")
    pane.refresh_terminal_input_security("root@host:~$ ")

    assert transitions == [True, False]


class _Process:
    def __init__(self, state, *, accepted: int | None = 0) -> None:
        self.process_state = state
        self.accepted = accepted
        self.writes: list[bytes] = []

    def state(self):
        return self.process_state

    def write(self, payload: bytes):
        self.writes.append(payload)
        return self.accepted


def test_terminal_response_forwarding_clear_link_and_deferred_output_edges(
    gui_window,
    monkeypatch,
) -> None:
    from PyQt6.QtCore import QProcess

    app, window = gui_window
    pane = _new_pane(window)
    process = _Process(QProcess.ProcessState.NotRunning)
    pane.process = process

    class _Desktop:
        opened: list[str] = []

        @classmethod
        def openUrl(cls, url):  # noqa: N802
            cls.opened.append(url.toString())
            return True

    _set_closure_value(
        monkeypatch,
        type(pane).open_terminal_link,
        "QDesktopServices",
        _Desktop,
    )
    assert pane.open_terminal_link("javascript:alert(1)") is False
    assert pane.output.property("terminalLastRejectedLink") == "javascript:alert(1)"
    assert pane.open_terminal_link("https://example.invalid/path") is True
    assert _Desktop.opened == ["https://example.invalid/path"]

    responses = iter(
        [
            [],
            [b"\x1b[0n"],
            [b"\x1b[1;1R", b"\x1b[?1;2c"],
            [b"\x1b[6n"],
        ]
    )
    monkeypatch.setattr(
        type(pane.terminal_emulator),
        "take_pending_responses",
        lambda _self: next(responses),
    )
    pane.forward_terminal_emulator_responses()
    pane.forward_terminal_emulator_responses()
    assert process.writes == []

    process.process_state = QProcess.ProcessState.Running
    process.accepted = None
    pane.forward_terminal_emulator_responses()
    assert process.writes[-1] == b"\x1b[1;1R\x1b[?1;2c"
    process.accepted = 1
    pane.forward_terminal_emulator_responses()
    assert pane.status.property("state") == "error"
    assert pane.output.property("terminalEmulatorResponseCount") == 4

    pane.set_startup_preamble("Session context", inject_current=False)
    pane.show_launch_command = True
    pane._restart_when_output_drained = True
    pane.clear_output()
    transcript = pane.output.toPlainText()
    assert "Session context" in transcript
    assert pane.plan.printable() in transcript
    assert pane._restart_when_output_drained is False
    pane.startup_preamble = ""
    pane.show_launch_command = False
    pane.clear_output()
    assert pane.output.toPlainText() == ""

    pane.queue_process_output_trailer("immediate trailer")
    assert "immediate trailer" in pane.output.toPlainText()
    pane._process_output_buffer.append(b"queued")
    pane.finish_deferred_process_output()
    assert pane._process_output_buffer
    pane._process_output_buffer.clear()

    scheduled: list[bool] = []
    monkeypatch.setattr(
        pane,
        "schedule_process_output_flush",
        lambda **kwargs: scheduled.append(bool(kwargs.get("backlog"))),
    )
    pane._process_output_source_end_pending = True
    pane._process_output_source_drained = False
    monkeypatch.setattr(
        pane,
        "pull_ended_process_output",
        lambda: pane._process_output_buffer.append(b"tail"),
    )
    pane.finish_deferred_process_output()
    assert scheduled == [True]
    pane._process_output_buffer.clear()
    monkeypatch.setattr(pane, "pull_ended_process_output", lambda: None)
    pane.finish_deferred_process_output()
    assert scheduled == [True, True]

    starts: list[str] = []
    pane._process_output_source_end_pending = False
    pane._process_output_source_drained = True
    pane._process_output_decode_final_pending = False
    pane._process_output_end_pending = False
    pane._restart_when_output_drained = True
    pane.setProperty("terminalClosing", False)
    monkeypatch.setattr(pane, "start", lambda: starts.append("start"))
    pane.finish_deferred_process_output()
    app.processEvents()
    assert starts == ["start"]

    monkeypatch.setattr(
        type(pane.terminal_emulator),
        "take_pending_responses",
        lambda _self: [],
    )
    monkeypatch.setattr(
        type(pane.terminal_emulator),
        "feed",
        lambda _self, _text: "\n\nvisible",
    )
    monkeypatch.setattr(pane, "terminal_startup_context_text", lambda: "")
    monkeypatch.setattr(
        pane,
        "normalized_initial_prompt_transcript",
        lambda text: text,
    )
    normalized: list[str] = []
    monkeypatch.setattr(pane, "set_terminal_transcript", normalized.append)
    pane._pty_initial_clear_pending = True
    pane.append_process_text("visible")
    assert normalized == ["visible"]
    pane.append_process_text("")


def test_terminal_backend_fallback_and_literal_message_box_edges(
    gui_window,
    monkeypatch,
) -> None:
    from PyQt6.QtCore import QProcess
    from PyQt6.QtWidgets import QMessageBox

    from remote_ops_workspace import gui, windows_conpty

    _app, window = gui_window
    pane = _new_pane(window)
    backend = _closure_value(type(pane).__init__, "_terminal_process_backend")
    original_platform = gui.sys.platform

    monkeypatch.setattr(gui.sys, "platform", "linux")
    linux_process, warning = backend(
        window,
        TerminalPanePlan(
            title="linux",
            command=["ssh", "linux.example.invalid"],
            source="test",
        ),
        None,
    )
    assert isinstance(linux_process, QProcess)
    assert warning == ""

    monkeypatch.setattr(gui.sys, "platform", "win32")
    monkeypatch.setattr(
        windows_conpty,
        "conpty_support",
        lambda: SimpleNamespace(supported=False, reason="controlled unsupported"),
    )
    plain_process, warning = backend(
        window,
        TerminalPanePlan(
            title="plain",
            command=["python", "-V"],
            source="test",
        ),
        None,
    )
    assert plain_process.property("terminalWindowsConsoleSuppressed") is True
    assert warning == ""

    ssh_process, ssh_warning = backend(
        window,
        TerminalPanePlan(
            title="ssh fallback",
            command=["ssh", "fallback.example.invalid"],
            source="test",
        ),
        None,
    )
    assert ssh_process.property("terminalOpenSshPipeFallback") is True
    assert "trusted-host key/agent" in ssh_warning

    shell_process, shell_warning = backend(
        window,
        TerminalPanePlan(
            title="shell fallback",
            command=["powershell.exe"],
            source="shell",
        ),
        None,
    )
    assert shell_process.property("terminalLineInputFallback") is True
    assert "line-oriented input" in shell_warning

    monkeypatch.setattr(
        windows_conpty,
        "conpty_support",
        lambda: (_ for _ in ()).throw(OSError("probe failed")),
    )
    _failed_process, failed_warning = backend(
        window,
        TerminalPanePlan(
            title="probe failure",
            command=["ssh.exe", "fallback.example.invalid"],
            source="test",
        ),
        None,
    )
    assert "probe failed" in failed_warning
    monkeypatch.setattr(gui.sys, "platform", original_platform)

    literal_message_box = _closure_value(
        type(window).connect_selected,
        "_literal_message_box",
    )

    class _MessageBox:
        StandardButton = QMessageBox.StandardButton

        def __init__(self, parent) -> None:
            self.parent = parent
            self.values: dict[str, object] = {}

        def setIcon(self, value) -> None:  # noqa: N802
            self.values["icon"] = value

        def setWindowTitle(self, value: str) -> None:  # noqa: N802
            self.values["title"] = value

        def setTextFormat(self, value) -> None:  # noqa: N802
            self.values["format"] = value

        def setText(self, value: str) -> None:  # noqa: N802
            self.values["text"] = value

        def setStandardButtons(self, value) -> None:  # noqa: N802
            self.values["buttons"] = value

        def setDefaultButton(self, value) -> None:  # noqa: N802
            self.values["default"] = value

        @staticmethod
        def exec() -> int:
            return int(QMessageBox.StandardButton.Yes.value)

    _set_closure_value(
        monkeypatch,
        literal_message_box,
        "QMessageBox",
        _MessageBox,
    )
    result = literal_message_box(
        window,
        QMessageBox.Icon.Question,
        "Literal title",
        "<b>literal body</b>",
        buttons=QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        default_button=QMessageBox.StandardButton.No,
    )
    assert result == QMessageBox.StandardButton.Yes


def test_tab_shutdown_status_and_deferred_start_edges(
    gui_window,
    monkeypatch,
) -> None:
    from PyQt6.QtWidgets import QWidget

    app, window = gui_window
    assert window.close_tab(-1) is None

    home_index = window.find_tab_by_role("home")
    assert home_index >= 0
    window.close_tab(home_index)
    assert window.statusBar().currentMessage() == "Home tab stays open"

    opened: list[str] = []
    original_open_local = window.open_local_terminal_tab
    monkeypatch.setattr(window, "open_local_terminal_tab", lambda: opened.append("local"))
    new_session_index = window.add_workspace_tab(
        QWidget(),
        "+",
        role="new-session",
    )
    opened.clear()
    window.close_tab(new_session_index)
    assert opened == ["local"]
    monkeypatch.setattr(window, "open_local_terminal_tab", original_open_local)

    class _Signal:
        def __init__(self) -> None:
            self.callbacks = []

        def connect(self, callback) -> None:
            self.callbacks.append(callback)

    class _Pane:
        def __init__(self) -> None:
            self.running = True
            self.prepared = False
            self.process = SimpleNamespace(finished=_Signal())

        def is_running(self) -> bool:
            return self.running

        def prepare_for_close(self) -> None:
            self.prepared = True

    fake_pane = _Pane()
    denied_widget = QWidget()
    denied_index = window.add_workspace_tab(denied_widget, "denied", role="session")
    original_terminal_panes_in = window.terminal_panes_in
    original_confirm = window.confirm_stop_processes
    monkeypatch.setattr(
        window,
        "terminal_panes_in",
        lambda widget: [fake_pane] if widget is denied_widget else [],
    )
    monkeypatch.setattr(window, "confirm_stop_processes", lambda *_args: False)
    window.close_tab(denied_index)
    assert window.tabs.indexOf(denied_widget) == denied_index

    stopped: list[object] = []
    monkeypatch.setattr(window, "confirm_stop_processes", lambda *_args: True)

    def stop_running(panes) -> None:
        stopped.extend(panes)
        fake_pane.running = False

    monkeypatch.setattr(window, "stop_terminal_panes", stop_running)
    window.close_tab(denied_index)
    assert fake_pane.prepared is True
    assert stopped == [fake_pane]
    assert denied_widget not in window._closing_tab_widgets
    monkeypatch.setattr(window, "terminal_panes_in", original_terminal_panes_in)
    monkeypatch.setattr(window, "confirm_stop_processes", original_confirm)

    window.expire_transient_status_message()
    window.show_transient_status_message("Completed edge", timeout_ms=60_000)
    window.update_session_status()
    assert window.statusBar().currentMessage() == "Completed edge"
    window.expire_transient_status_message()
    assert window._status_message_override == "Completed edge"
    window._status_message_override_deadline = 0.0
    window.expire_transient_status_message()
    assert window._status_message_override is None

    original_running = window.running_terminal_panes
    monkeypatch.setattr(window, "running_terminal_panes", lambda: [object()])
    window.update_session_status()
    assert window.statusBar().currentMessage() == "Running process panes: 1"
    monkeypatch.setattr(window, "running_terminal_panes", lambda: [])
    window.update_session_status()
    assert window.statusBar().currentMessage() == "No running process panes"
    monkeypatch.setattr(
        window,
        "running_terminal_panes",
        lambda: (_ for _ in ()).throw(RuntimeError("disposed")),
    )
    window.update_session_status()
    monkeypatch.setattr(window, "running_terminal_panes", original_running)

    pane = _new_pane(window)
    pane_index = window.add_workspace_tab(pane, "deferred", role="terminal")
    starts: list[str] = []
    monkeypatch.setattr(pane, "start", lambda: starts.append("start"))
    monkeypatch.setattr(pane, "is_running", lambda: False)
    window.start_deferred_terminal_pane_if_current(
        pane,
        pane_index,
        window._tab_transition_generation + 1,
    )
    pane.setProperty("terminalClosing", True)
    window.start_deferred_terminal_pane_if_current(pane, pane_index)
    pane.setProperty("terminalClosing", False)
    monkeypatch.setattr(pane, "is_running", lambda: True)
    window.start_deferred_terminal_pane_if_current(pane, pane_index)
    monkeypatch.setattr(pane, "is_running", lambda: False)
    window.start_deferred_terminal_pane_if_current(pane, -1)
    window.set_workspace_tab_index(home_index)
    window.start_deferred_terminal_pane_if_current(pane, pane_index)
    window.set_workspace_tab_index(pane_index)
    window.tabs.setProperty("terminalTabTransitionActive", True)
    window.start_deferred_terminal_pane_if_current(pane, pane_index)
    assert starts == []
    window.tabs.setProperty("terminalTabTransitionActive", False)
    window.tabs.setProperty("terminalTabPrepaintGuardActive", False)
    app.processEvents()
    assert starts == ["start"]
    assert pane.property("terminalStartDeferredUntilTabReady") is False


def test_background_refresh_callback_and_main_edges(gui_window, monkeypatch, capsys) -> None:
    from remote_ops_workspace import gui

    _app, window = gui_window
    pane = SimpleNamespace(profile=None)
    original_dock = window.moba_connected_dock
    window.moba_connected_dock = None
    window.refresh_moba_background_after_terminal_start(pane)

    pane.profile = SimpleNamespace(name="profile-a")
    window.moba_connected_dock = SimpleNamespace(
        state=SimpleNamespace(profile_name="profile-b")
    )
    window.refresh_moba_background_after_terminal_start(pane)

    window.moba_connected_dock = SimpleNamespace(
        state=SimpleNamespace(profile_name="profile-a"),
        schedule_background_state_activation=None,
    )
    window.refresh_moba_background_after_terminal_start(pane)
    scheduled: list[int] = []
    window.moba_connected_dock = SimpleNamespace(
        state=SimpleNamespace(profile_name="profile-a"),
        schedule_background_state_activation=scheduled.append,
    )
    window.refresh_moba_background_after_terminal_start(pane)
    assert scheduled == [1_500]
    window.refresh_moba_background_after_terminal_auth(pane, True)
    window.refresh_moba_background_after_terminal_auth(pane, False)
    assert scheduled == [1_500, 250]
    window.moba_connected_dock = SimpleNamespace(
        state=SimpleNamespace(profile_name="profile-a"),
        schedule_background_state_activation=lambda _delay: (_ for _ in ()).throw(
            RuntimeError("deleted")
        ),
    )
    window.refresh_moba_background_after_terminal_start(pane)

    class _DisposedDock:
        @property
        def state(self):
            raise RuntimeError("deleted")

    window.moba_connected_dock = _DisposedDock()
    window.refresh_moba_background_after_terminal_start(pane)
    window.moba_connected_dock = original_dock

    class _App:
        @staticmethod
        def exec() -> int:
            return 17

    monkeypatch.setattr(gui, "create_main_window", lambda *_args, **_kwargs: (_App(), object()))
    assert gui.main() == 17

    def fail_create(*_args, **_kwargs):
        try:
            raise OSError("missing platform plugin")
        except OSError as cause:
            raise gui.GuiDependencyError("GUI unavailable") from cause

    monkeypatch.setattr(gui, "create_main_window", fail_create)
    assert gui.main() == 2
    output = capsys.readouterr().out
    assert "GUI unavailable" in output
    assert "missing platform plugin" in output


def test_terminal_scroll_follows_normal_output_but_not_vim_edges(gui_window) -> None:
    app, window = gui_window
    pane = _new_pane(window)
    pane.output.setPlainText("line\n" * 200)
    scroll_bar = pane.output.verticalScrollBar()

    pane.terminal_emulator._alternate_screen = True
    scroll_bar.setValue(scroll_bar.maximum())
    pane.scroll_terminal_to_end()
    assert scroll_bar.value() == 0
    assert pane.output.property("terminalFollowOutput") is False

    pane.terminal_emulator._alternate_screen = False
    pane.scroll_terminal_to_end()
    first_generation = pane._terminal_scroll_generation
    pane.scroll_terminal_to_end()
    assert pane._terminal_scroll_generation == first_generation + 1
    app.processEvents()
    assert pane.output.property("terminalFollowOutput") is True
    assert scroll_bar.value() == scroll_bar.maximum()


def test_terminal_submitted_line_restores_live_tail_but_alt_screen_keeps_its_view(
    gui_window,
) -> None:
    from PyQt6.QtCore import QProcess

    _app, window = gui_window
    pane = _new_pane(window)
    pane.set_terminal_transcript("line\n" * 300)
    scroll_bar = pane.output.verticalScrollBar()
    scroll_bar.setValue(0)
    assert pane.output.property("terminalFollowOutput") is False

    process = _Process(QProcess.ProcessState.Running, accepted=1)
    pane.process = process
    pane.send_raw_input(b"ls\n")
    assert process.writes == [b"ls\n"]
    assert pane.output.property("terminalFollowOutput") is True
    assert pane.output.property("terminalInputRequestedLiveTail") is True
    assert scroll_bar.value() == scroll_bar.maximum()

    pane.terminal_emulator._alternate_screen = True
    pane._terminal_follow_output = False
    pane.output.setProperty("terminalFollowOutput", False)
    scroll_bar.setValue(0)
    pane.send_raw_input(b"\x1b[A")
    assert pane.output.property("terminalFollowOutput") is False
    assert pane.output.property("terminalInputRequestedLiveTail") is False


def test_terminal_output_flush_latency_and_atomic_frame_edges(gui_window) -> None:
    _app, window = gui_window
    pane = _new_pane(window)

    pane.schedule_process_output_flush()
    assert pane.output.property("terminalOutputFlushDelayMs") == 0
    assert pane.output.property("terminalOutputFlushMode") == "next-event-turn"
    pane._process_output_timer.start(1000)
    pane.schedule_process_output_flush()
    assert pane._process_output_flush_scheduled is True
    pane._process_output_timer.stop()
    pane._process_output_flush_scheduled = False

    pane.terminal_emulator._alternate_screen = True
    pane.schedule_process_output_flush()
    assert pane.output.property("terminalOutputFlushDelayMs") == 16
    assert pane.output.property("terminalOutputFlushMode") == "alternate-screen-coalesced"
    pane._process_output_timer.stop()
    pane._process_output_flush_scheduled = False
    pane.schedule_process_output_flush(backlog=True)
    assert pane.output.property("terminalOutputFlushDelayMs") == 0
    pane._process_output_timer.stop()
    pane._process_output_flush_scheduled = False

    pane.render_terminal_transcript("one frame")
    assert pane.output.toPlainText() == "one frame"
    assert pane.output.updatesEnabled() is True
    assert pane.output.property("terminalAlternateScreenRedraw") is False
    pane.render_terminal_transcript("one frame")
    assert pane.output.toPlainText() == "one frame"


def test_terminal_render_preserves_manual_scrollback_and_ignores_stale_ansi_ranges(
    gui_window,
    monkeypatch,
) -> None:
    from remote_ops_workspace.terminal_emulation import (
        AnsiTerminalFragment,
        AnsiTextStyle,
    )

    app, window = gui_window
    pane = _new_pane(window)
    window.add_workspace_tab(pane, "render-edge", role="terminal")
    pane.set_terminal_transcript("line\n" * 300)
    app.processEvents()
    scroll_bar = pane.output.verticalScrollBar()
    assert scroll_bar.maximum() > 2
    scroll_bar.setValue(0)

    transcript = pane.terminal_emulator.feed("tail\n")
    pane.render_terminal_transcript(transcript)
    assert scroll_bar.value() == 0

    stale_fragment = AnsiTerminalFragment(
        start=len(transcript) + 10,
        end=len(transcript) + 20,
        text="stale",
        style=AnsiTextStyle(bold=True),
    )
    monkeypatch.setattr(
        type(pane.terminal_emulator),
        "styled_fragments",
        lambda _emulator, **_kwargs: [stale_fragment],
    )
    pane._rendered_terminal_text = ""
    pane.render_terminal_transcript("current")
    assert pane._rendered_terminal_text == "current"


def test_terminal_event_filter_handles_empty_ime_paste_and_missing_tab_route(
    gui_window,
    monkeypatch,
) -> None:
    from PyQt6.QtCore import QEvent, QPointF, QProcess, Qt
    from PyQt6.QtGui import QInputMethodEvent, QKeyEvent, QMouseEvent

    _app, window = gui_window
    pane = _new_pane(window)
    process = _Process(QProcess.ProcessState.Running, accepted=None)
    pane.process = process

    clipboard = SimpleNamespace(text=lambda *_args: "paste-edge")
    pane._terminal_clipboard_provider = lambda: clipboard
    paste = QKeyEvent(
        QEvent.Type.KeyPress,
        Qt.Key.Key_V,
        Qt.KeyboardModifier.ControlModifier,
        "v",
    )
    assert pane.eventFilter(pane.output, paste) is True
    assert process.writes[-1] == b"paste-edge"

    empty_ime = QInputMethodEvent("", [])
    assert pane.eventFilter(pane.output, empty_ime) is False

    monkeypatch.setattr(pane, "window", lambda: SimpleNamespace())
    control_tab = QKeyEvent(
        QEvent.Type.KeyPress,
        Qt.Key.Key_Tab,
        Qt.KeyboardModifier.ControlModifier,
        "\t",
    )
    assert pane.eventFilter(pane.output, control_tab) is True
    assert process.writes[-1] == b"\t"

    position = QPointF(2, 2)
    release = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        position,
        position,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.ControlModifier,
    )
    assert pane.eventFilter(pane.output_viewport, release) is False


def test_main_window_close_confirms_detached_running_panes(gui_window, monkeypatch) -> None:
    _app, window = gui_window

    class _ProcessHandle:
        def __init__(self) -> None:
            self.killed = False
            self.closed = False

        def kill(self) -> None:
            self.killed = True

        def close(self) -> None:
            self.closed = True

    process = _ProcessHandle()
    pane = SimpleNamespace(
        is_running=lambda: True,
        prepare_for_close=lambda: None,
        process=process,
    )
    detached = object()
    window._closing_tab_widgets = [detached]
    monkeypatch.setattr(window, "running_terminal_panes", lambda: [])
    monkeypatch.setattr(window, "terminal_panes_in", lambda widget: [pane] if widget is detached else [])

    denied = SimpleNamespace(
        accepted=False,
        ignored=False,
        accept=lambda: setattr(denied, "accepted", True),
        ignore=lambda: setattr(denied, "ignored", True),
    )
    monkeypatch.setattr(window, "confirm_stop_processes", lambda *_args: False)
    window.closeEvent(denied)
    assert denied.ignored is True
    assert process.killed is False

    accepted = SimpleNamespace(
        accepted=False,
        ignored=False,
        accept=lambda: setattr(accepted, "accepted", True),
        ignore=lambda: setattr(accepted, "ignored", True),
    )
    original_dock = window.moba_connected_dock
    window.moba_connected_dock = None
    monkeypatch.setattr(window, "confirm_stop_processes", lambda *_args: True)
    window.closeEvent(accepted)
    window.moba_connected_dock = original_dock
    assert accepted.accepted is True
    assert process.killed is True
    assert process.closed is True


def test_terminal_fallback_io_clipboard_and_empty_pipeline_edges(
    gui_window,
    monkeypatch,
) -> None:
    from PyQt6.QtCore import QProcess

    _app, window = gui_window
    pane = _new_pane(window)

    pane.process = _Process(QProcess.ProcessState.NotRunning)
    pane.paste_text_to_terminal("", gesture="action")
    pane.paste_text_to_terminal("offline paste", gesture="action")
    assert pane.input.text() == "offline paste"
    pane.input.setText("offline command")
    pane.send_input()
    assert "process is not running" in pane.output.toPlainText()

    notices: list[str] = []
    monkeypatch.setattr(pane, "append_text", notices.append)
    pane._secret_prompt_active = True
    pane.replay_macro_capture()
    assert "secret input" in notices[-1]
    pane._secret_prompt_active = False

    class _GenericReader:
        def __init__(self) -> None:
            self.channels = []
            self.payload: bytes | None = None

        def setReadChannel(self, channel) -> None:  # noqa: N802
            self.channels.append(channel)

        def read(self, _max_bytes: int):
            return self.payload

    generic = _GenericReader()
    pane.process = generic
    assert pane.read_process_output_chunk("stderr", 32) == b""
    generic.payload = b"generic"
    assert pane.read_process_output_chunk("stdout", 32) == b"generic"
    assert generic.channels == [
        QProcess.ProcessChannel.StandardError,
        QProcess.ProcessChannel.StandardOutput,
    ]

    class _FallbackReader:
        @staticmethod
        def readAllStandardOutput() -> bytes:  # noqa: N802
            return b"fallback"

    pane.process = _FallbackReader()
    assert pane.read_process_output_chunk("stdout", 32) == b"fallback"

    pane.reset_process_output_pipeline()
    pane._process_output_source_end_pending = False
    pane.pull_ended_process_output()
    pane._process_output_source_end_pending = True
    pane._process_output_buffer.append(
        b"x" * (pane.OUTPUT_BUFFER_LOW_WATER_BYTES + 1)
    )
    pane.pull_ended_process_output()

    pane.reset_process_output_pipeline()
    refill_calls: list[str] = []
    finish_calls: list[str] = []
    monkeypatch.setattr(pane, "refill_process_output", lambda: refill_calls.append("refill"))
    monkeypatch.setattr(
        pane,
        "finish_deferred_process_output",
        lambda: finish_calls.append("finish"),
    )
    pane.flush_process_output()
    assert refill_calls == ["refill"]
    assert finish_calls == ["finish"]

    rendered: list[str] = []
    monkeypatch.setattr(pane, "render_terminal_transcript", rendered.append)
    pane.append_terminal_notice("")
    pane.terminal_emulator._alternate_screen = True
    pane.append_terminal_notice("literal notice")
    assert rendered[-1] == pane.terminal_emulator.screen_text()

    class _RetryClipboard:
        def __init__(self) -> None:
            self.writes: list[str] = []

        def setText(self, text: str) -> None:  # noqa: N802
            self.writes.append(text)

        @staticmethod
        def text() -> str:
            return "held by another process"

    clipboard = _RetryClipboard()
    pane._terminal_clipboard_provider = lambda: clipboard
    pane.copy_command()
    assert len(clipboard.writes) == 2
    assert pane.output.property("terminalClipboardWriteRetried") is True


def test_gui_low_level_platform_dialog_and_cursor_edges(
    gui_window,
    monkeypatch,
) -> None:
    import ctypes

    from PyQt6.QtGui import QPaintEvent
    from PyQt6.QtWidgets import QApplication, QMessageBox

    from remote_ops_workspace import gui, windows_conpty
    from remote_ops_workspace.models import Profile

    app, window = gui_window
    queue = gui._ByteChunkQueue()
    queue.append(b"")
    assert queue.take(1) == b""

    monkeypatch.setattr(gui.sys, "platform", "linux")
    gui.set_windows_taskbar_app_id()
    monkeypatch.setattr(gui.sys, "platform", "win32")

    def reject_taskbar_id(_app_id: str) -> None:
        raise OSError("shell policy")

    monkeypatch.setattr(
        ctypes,
        "windll",
        SimpleNamespace(
            shell32=SimpleNamespace(
                SetCurrentProcessExplicitAppUserModelID=reject_taskbar_id,
            )
        ),
        raising=False,
    )
    gui.set_windows_taskbar_app_id()

    pane = _new_pane(window)
    application_instance = _closure_value(
        type(pane).copy_command,
        "_application_instance",
    )
    with monkeypatch.context() as context:
        context.setattr(QApplication, "instance", staticmethod(lambda: None))
        with pytest.raises(RuntimeError, match="Qt application"):
            application_instance()

    profile = Profile(
        name="background-process-edge",
        protocol="sftp",
        host="background.example.invalid",
    )
    dialog = window.create_transfer_queue_dialog(profile)
    background_process = _closure_value(
        type(dialog).__init__,
        "_background_process",
    )
    monkeypatch.setattr(gui.sys, "platform", "non-windows")
    generic_process = background_process(window)
    assert generic_process.parent() is window
    generic_process.deleteLater()

    monkeypatch.setattr(gui.sys, "platform", "win32")
    monkeypatch.setattr(
        windows_conpty,
        "conpty_support",
        lambda: (_ for _ in ()).throw(OSError("controlled ConPTY probe failure")),
    )
    hidden_process = background_process(window, interactive_auth=True)
    assert type(hidden_process).__name__ == "QtHiddenProcess"
    hidden_process.deleteLater()

    literal_message_box = _closure_value(
        type(window).confirm_stop_processes,
        "_literal_message_box",
    )
    with monkeypatch.context() as context:
        context.setattr(
            QMessageBox,
            "exec",
            lambda _box: int(QMessageBox.StandardButton.Ok),
        )
        assert literal_message_box(
            window,
            QMessageBox.Icon.Information,
            "Literal",
            "<b>not markup</b>",
        ) == QMessageBox.StandardButton.Ok

    clamp_dialog = _closure_value(
        type(dialog).showEvent,
        "_clamp_dialog_frame_to_parent_screen",
    )
    dialog_screen = _closure_value(clamp_dialog, "_dialog_screen")
    assert dialog_screen(None) is QApplication.primaryScreen()
    assert dialog_screen(SimpleNamespace(screen=lambda: None)) is QApplication.primaryScreen()
    with monkeypatch.context() as context:
        _set_closure_value(context, clamp_dialog, "_dialog_screen", lambda _parent: None)
        clamp_dialog(dialog)

    dialog.resize(100_000, 100_000)
    clamp_dialog(dialog)
    available = QApplication.primaryScreen().availableGeometry()
    assert dialog.width() <= available.width()
    assert dialog.height() <= available.height()

    event = QPaintEvent(pane.output.rect())
    pane.output.setProperty("terminalTabPaintFrozen", True)
    pane.output.paintEvent(event)
    pane.output.setProperty("terminalTabPaintFrozen", False)
    pane.output.set_remote_cursor_state(0, visible=False)
    pane.output.paintEvent(event)
    pane.output.resize(240, 80)
    pane.output.setPlainText("line\n" * 500)
    pane.output.verticalScrollBar().setValue(0)
    pane.output.set_remote_cursor_state(
        pane.output.document().characterCount() - 1,
        visible=True,
    )
    pane.output.paintEvent(event)
    app.processEvents()
    dialog.deleteLater()


def test_terminal_remaining_operator_io_and_lifecycle_edges(
    gui_window,
    monkeypatch,
) -> None:
    from PyQt6.QtCore import QProcess
    from PyQt6.QtWidgets import QMenu

    from remote_ops_workspace import gui
    from remote_ops_workspace.models import Profile

    _app, window = gui_window
    profile = Profile(
        name="shared-command-edge",
        protocol="ssh",
        host="shared.example.invalid",
        username="operator",
    )
    monkeypatch.setattr(
        gui,
        "ssh_control_path_for_profile",
        lambda _profile: "controlled-socket",
    )
    monkeypatch.setattr(
        gui,
        "ssh_command_with_control_path",
        lambda command, _path, **_kwargs: [*command, "-o", "ControlMaster=auto"],
    )
    pane = window.new_terminal_pane(
        TerminalPanePlan(
            title="remaining-terminal-edge",
            command=["ssh", "shared.example.invalid"],
            source="test",
            notes=["startup note"],
        ),
        profile=profile,
        autostart=False,
    )
    assert pane.ssh_control_path == "controlled-socket"
    assert pane.plan.command[-1] == "ControlMaster=auto"

    pane._terminal_right_click_paste_generation = 9
    pane._terminal_right_click_paste_pending = True
    pane._clear_right_click_paste_suppression(9)
    assert pane._terminal_right_click_paste_pending is False

    process = _Process(QProcess.ProcessState.Running, accepted=None)
    pane.process = process

    class _SelectionClipboard:
        @staticmethod
        def supportsSelection() -> bool:  # noqa: N802
            return True

        @staticmethod
        def text(mode=None) -> str:
            return "selection-edge" if mode is not None else "clipboard-edge"

    pane._terminal_clipboard_provider = _SelectionClipboard
    pane.paste_middle_click_selection()
    assert process.writes[-1] == b"selection-edge"

    custom_menu = QMenu(pane.output)
    pane.output_context_menu_builder = lambda _pane: custom_menu
    assert pane.build_output_context_menu() is custom_menu
    assert custom_menu.property("terminalMousePasteMenuAdded") is True

    menu_calls: list[str] = []
    fake_menu = SimpleNamespace(
        exec=lambda _position: menu_calls.append("exec"),
        deleteLater=lambda: menu_calls.append("delete"),
    )
    monkeypatch.setattr(pane, "build_output_context_menu", lambda: fake_menu)
    pane.show_output_context_menu(pane.output_viewport.rect().center())
    assert menu_calls == ["exec", "delete"]

    pane.set_launch_command_echo_visible(True)
    pane.set_launch_command_echo_visible(False, rewrite_current=False)
    pane._rendered_terminal_text = "no command line here"
    pane.set_launch_command_echo_visible(False)

    pane.set_startup_preamble("", inject_current=True)
    pane.set_startup_preamble("Stable preamble", inject_current=False)
    pane._rendered_terminal_text = pane.startup_preamble + "body"
    pane.set_startup_preamble("Stable preamble", inject_current=True)
    pane._terminal_backend_warning = "controlled backend warning"
    assert "controlled backend warning" in pane.terminal_startup_context_text()

    class _StderrReader:
        @staticmethod
        def readStandardError(_max_bytes: int) -> bytes:  # noqa: N802
            return b"stderr-edge"

    pane.process = _StderrReader()
    pulled: list[tuple[str, int]] = []
    monkeypatch.setattr(
        pane,
        "pull_process_output_channel",
        lambda channel: pulled.append((channel, 1)) or (1, False),
    )
    pane.read_stderr()
    assert pulled == [("stderr", 1)]

    ended: list[str] = []
    pane._process_output_source_end_pending = True
    pane._process_output_buffer.clear()
    monkeypatch.setattr(
        pane,
        "pull_ended_process_output",
        lambda: ended.append("ended"),
    )
    pane.refill_process_output()
    assert ended == ["ended"]

    pane.setProperty("terminalClosing", True)
    pane.queue_process_output(b"ignored while closing")
    assert not pane._process_output_buffer
    pane.setProperty("terminalClosing", False)
    pane.queue_process_output_trailer("")

    monkeypatch.setattr(pane, "terminal_startup_context_text", lambda: "")
    assert pane.normalized_initial_pty_transcript("\n\nvisible") == "visible"
    assert pane.normalized_initial_prompt_transcript("ordinary transcript") == (
        "ordinary transcript"
    )
    pane.append_text("")

    class _RunningErrorProcess:
        @staticmethod
        def state():
            return QProcess.ProcessState.Running

        @staticmethod
        def errorString() -> str:  # noqa: N802
            return "controlled detail"

    pane.process = _RunningErrorProcess()
    marked: list[str] = []
    trailers: list[str] = []
    monkeypatch.setattr(pane, "mark_process_output_end", lambda: marked.append("end"))
    monkeypatch.setattr(pane, "queue_process_output_trailer", trailers.append)
    monkeypatch.setattr(pane, "flush_process_output_now", lambda: None)
    pane.on_error(QProcess.ProcessError.ReadError)
    assert marked == []
    assert "controlled detail" in trailers[-1]
    custom_menu.deleteLater()


def test_terminal_raw_input_cursor_paint_and_syntax_highlighter_edges(
    gui_window,
    monkeypatch,
) -> None:
    from PyQt6.QtCore import QProcess

    from remote_ops_workspace.models import Profile

    app, window = gui_window
    pane = _new_pane(window)
    window.add_workspace_tab(pane, "paint-edge", role="terminal")
    process = _Process(QProcess.ProcessState.NotRunning)
    pane.process = process
    appended: list[str] = []
    monkeypatch.setattr(pane, "append_text", appended.append)

    pane.send_raw_input(b"")
    pane.send_raw_input(b"ignored")
    assert "not running" in appended[-1]

    process.process_state = QProcess.ProcessState.Running
    process.accepted = None
    pane.send_raw_input(b"complete")
    assert pane.output.property("terminalLastInputBytesAccepted") == len(b"complete")
    process.accepted = 2
    pane.send_raw_input(b"partial")
    assert pane.status.property("state") == "error"
    assert "did not accept" in appended[-1]
    process.process_state = QProcess.ProcessState.NotRunning

    pane.output.setPlainText("cursor paint edge")
    pane.output.setProperty("terminalTabPaintFrozen", True)
    pane.output.viewport().update()
    app.processEvents()
    pane.output.setProperty("terminalTabPaintFrozen", False)
    pane.output.set_remote_cursor_state(1, trailing_cells=2, visible=True)
    pane.output.viewport().update()
    app.processEvents()
    pane.output.set_remote_cursor_state(0, visible=False)
    pane.output.viewport().update()
    app.processEvents()

    highlighter = type(
        window.moba_connected_dock.text_editor_highlighter
    ) if window.moba_connected_dock is not None else None
    if highlighter is None:
        window.set_design_preset("mobaxterm")
        profile = Profile(
            name="syntax-edge",
            protocol="ssh",
            host="syntax.example.invalid",
            username="operator",
        )
        panel = window.open_moba_connected_session_tab(
            profile,
            TerminalPanePlan(title="syntax-edge", command=[], source="test"),
        )
        dock = window.moba_connected_dock
        assert dock is not None
        highlighter_instance = dock.text_editor_highlighter
    else:
        panel = None
        dock = window.moba_connected_dock
        assert dock is not None
        highlighter_instance = dock.text_editor_highlighter
    highlighter_type = type(highlighter_instance)
    for syntax in (
        "json",
        "javascript",
        "typescript",
        "shell",
        "powershell",
        "ssh-config",
        "ini",
        "systemd",
        "nginx",
        "log",
        "plain",
    ):
        assert highlighter_type.patterns_for_syntax(syntax)
    highlighter_instance.patterns = highlighter_type.patterns_for_syntax("log")
    highlighter_instance.highlightBlock("error 42")
    if panel is not None:
        dock.shutdown_runtime()


def test_close_other_tabs_preserves_special_and_selected_tabs(gui_window, monkeypatch) -> None:
    from PyQt6.QtWidgets import QWidget

    _app, window = gui_window
    monkeypatch.setattr(window, "open_local_terminal_tab", lambda: None)
    keep = window.add_workspace_tab(QWidget(), "keep", role="session")
    close_a = window.add_workspace_tab(QWidget(), "close-a", role="session")
    window.add_workspace_tab(QWidget(), "+", role="new-session")
    close_b = window.add_workspace_tab(QWidget(), "close-b", role="terminal")
    closed: list[int] = []
    monkeypatch.setattr(window, "close_tab", closed.append)
    window.close_other_tabs(keep)
    assert closed == [close_b, close_a]


def test_tab_transition_cycle_and_finished_shell_lifecycle_edges(
    gui_window,
) -> None:
    from PyQt6.QtWidgets import QSplitter

    app, window = gui_window

    class _Selector:
        def __init__(self, count: int, current: int = 0) -> None:
            self._count = count
            self._current = current
            self.selected: list[int] = []

        def count(self) -> int:
            return self._count

        def currentIndex(self) -> int:  # noqa: N802
            return self._current

        def setCurrentIndex(self, index: int) -> None:  # noqa: N802
            self.selected.append(index)

    cycle_design_preset = type(window).cycle_design_preset
    empty_selector = _Selector(0)
    cycle_design_preset(SimpleNamespace(design_select=empty_selector))
    assert empty_selector.selected == []
    populated_selector = _Selector(3, 1)
    cycle_design_preset(SimpleNamespace(design_select=populated_selector))
    assert populated_selector.selected == [2]

    closed: list[int] = []
    close_current_tab = type(window).close_current_tab
    close_current_tab(
        SimpleNamespace(
            tabs=SimpleNamespace(currentIndex=lambda: -1),
            close_tab=closed.append,
        )
    )
    close_current_tab(
        SimpleNamespace(
            tabs=SimpleNamespace(currentIndex=lambda: 4),
            close_tab=closed.append,
        )
    )
    assert closed == [4]

    class _BrokenPane:
        @staticmethod
        def is_running() -> bool:
            raise RuntimeError("deleted pane")

    close_finished_shell_tab = type(window).close_finished_shell_tab
    close_owner = SimpleNamespace(
        tabs=SimpleNamespace(indexOf=lambda _pane: 2),
        tab_role=lambda _index: "tool",
        close_tab=closed.append,
    )
    close_finished_shell_tab(close_owner, _BrokenPane())

    class _Pane:
        def __init__(self, *, running: bool, closing: bool = False) -> None:
            self.running = running
            self.closing = closing

        def is_running(self) -> bool:
            return self.running

        def property(self, _key: str) -> bool:
            return self.closing

    close_finished_shell_tab(close_owner, _Pane(running=True))
    close_finished_shell_tab(close_owner, _Pane(running=False, closing=True))
    close_finished_shell_tab(close_owner, _Pane(running=False))
    assert closed == [4]
    close_owner.tab_role = lambda _index: "terminal"
    close_finished_shell_tab(close_owner, _Pane(running=False))
    assert closed == [4, 2]

    class _Layout:
        def __init__(self) -> None:
            self.activations = 0

        def activate(self) -> None:
            self.activations += 1

    class _Tabs:
        def __init__(self, current) -> None:
            self.current = current
            self.layout_object = _Layout()
            self.properties: dict[str, object] = {}
            self.updates: list[bool] = []

        def currentWidget(self):  # noqa: N802
            return self.current

        def layout(self):
            return self.layout_object

        @staticmethod
        def updateGeometry() -> None:  # noqa: N802
            return None

        def setProperty(self, key: str, value: object) -> None:  # noqa: N802
            self.properties[key] = value

        def setUpdatesEnabled(self, enabled: bool) -> None:  # noqa: N802
            self.updates.append(enabled)

    transition = 7
    fake_tabs = _Tabs(None)
    frozen: list[bool] = []
    transition_owner = SimpleNamespace(
        _tab_transition_generation=transition,
        tabs=fake_tabs,
        configure_product_connected_chrome=lambda: None,
        refresh_moba_left_dock_for_current_tab=lambda: None,
        terminal_panes_in=lambda _widget: [],
        set_terminal_tab_paint_frozen=frozen.append,
    )
    finish_tab_transition = type(window).finish_tab_transition
    finish_tab_transition(transition_owner, transition - 1)
    assert fake_tabs.layout_object.activations == 0
    finish_tab_transition(transition_owner, transition)
    assert fake_tabs.layout_object.activations == 1
    assert fake_tabs.properties["terminalTabGeometryStabilized"] is False

    splitter = QSplitter()
    splitter.resize(320, 180)
    splitter.show()
    app.processEvents()
    fake_tabs.current = splitter
    transition_owner.terminal_panes_in = lambda _widget: [splitter]
    finish_tab_transition(transition_owner, transition)
    assert fake_tabs.properties["terminalTabGeometryStabilized"] is True
    assert frozen == [False, False]
    assert fake_tabs.updates == [True, True]
    splitter.deleteLater()


def test_open_sftp_context_item_handles_empty_and_detached_rows(gui_window) -> None:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QFrame, QTreeWidgetItem

    _app, window = gui_window
    window.open_sftp_context_item(None)
    blank = QTreeWidgetItem(["   "])
    window.open_sftp_context_item(blank)
    assert window.property("termiusNativeSftpOpenedItem") is None

    detached = QTreeWidgetItem(["detached.log"])
    detached.setData(0, Qt.ItemDataRole.UserRole, "file")
    window.open_sftp_context_item(detached)
    assert window.property("termiusNativeSftpOpenedItem") == "detached.log"
    assert window.property("termiusNativeSftpOpenedKind") == "file"

    surface = QFrame(window)
    surface.setObjectName("termiusNativeSftpSurface")
    attached = QTreeWidgetItem(["attached"])
    attached.setData(0, Qt.ItemDataRole.UserRole, "directory")
    window.open_sftp_context_item(attached)
    assert surface.property("termiusNativeSftpOpenedItem") == "attached"
    assert surface.property("termiusNativeSftpOpenedKind") == "directory"


def test_process_finish_confirmation_and_expired_status_edges(
    gui_window,
    monkeypatch,
) -> None:
    import time

    from PyQt6.QtWidgets import QMessageBox

    _app, window = gui_window
    status_updates: list[str] = []

    class _Pane:
        def __init__(self, *, auto_close: bool, closing: bool) -> None:
            self.auto_close = auto_close
            self.closing = closing

        def property(self, key: str):
            if key == "terminalAutoCloseOnCleanExit":
                return self.auto_close
            if key == "terminalClosing":
                return self.closing
            return None

    owner = SimpleNamespace(update_session_status=lambda: status_updates.append("status"))
    process_finished = type(window).handle_terminal_process_finished
    process_finished(owner, _Pane(auto_close=True, closing=False), 1)
    process_finished(owner, _Pane(auto_close=False, closing=False), 0)
    process_finished(owner, _Pane(auto_close=True, closing=True), 0)
    assert status_updates == ["status", "status", "status"]

    answers = iter(
        [
            QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        ]
    )
    prompts: list[tuple[str, str]] = []

    def message_box(_parent, _icon, title, text, **_kwargs):
        prompts.append((title, text))
        return next(answers)

    _set_closure_value(
        monkeypatch,
        type(window).confirm_stop_processes,
        "_literal_message_box",
        message_box,
    )
    assert window.confirm_stop_processes("Controlled close", 2) is False
    assert window.confirm_stop_processes("Controlled close", 2) is True
    assert prompts == [
        ("Controlled close", "Stop 2 running process pane(s)?"),
        ("Controlled close", "Stop 2 running process pane(s)?"),
    ]

    messages: list[str] = []
    status_bar = SimpleNamespace(showMessage=lambda message, *_args: messages.append(message))
    update_owner = SimpleNamespace(
        _status_message_override="expired",
        _status_message_override_deadline=time.monotonic() - 1,
        statusBar=lambda: status_bar,
        running_terminal_panes=lambda: [object()],
    )
    update_status = type(window).update_session_status
    update_status(update_owner)
    assert update_owner._status_message_override is None
    assert messages[-1] == "Running process panes: 1"
    update_owner.running_terminal_panes = lambda: []
    update_status(update_owner)
    assert messages[-1] == "No running process panes"


def test_terminal_output_backpressure_empty_payload_and_initial_transcript_edges(
    gui_window,
    monkeypatch,
) -> None:
    _app, window = gui_window
    pane = _new_pane(window)
    pause_calls: list[bool] = []
    monkeypatch.setattr(
        pane,
        "set_process_output_read_paused",
        pause_calls.append,
    )
    pane._process_output_buffer.append(
        b"x" * (pane.OUTPUT_BUFFER_LOW_WATER_BYTES + 1)
    )

    pane.refill_process_output()

    assert pause_calls == []
    pane._process_output_buffer.clear()
    pane.queue_process_output(b"")
    assert not pane._process_output_buffer

    monkeypatch.setattr(
        pane,
        "terminal_startup_context_text",
        lambda: "controlled startup context",
    )
    assert pane.normalized_initial_pty_transcript("\n\nvisible output") == (
        "visible output"
    )


def test_empty_decoded_process_output_is_ignored(gui_window, monkeypatch) -> None:
    _app, window = gui_window
    pane = _new_pane(window)
    appended: list[str] = []
    monkeypatch.setattr(pane, "append_process_text", appended.append)

    type(pane).append_decoded_process_output(pane, b"")

    assert appended == []


def test_remaining_terminal_window_lifecycle_and_deferred_transition_edges(
    gui_window,
    monkeypatch,
) -> None:
    from PyQt6.QtWidgets import QWidget

    _app, window = gui_window

    class _Signal:
        def __init__(self) -> None:
            self.callbacks: list[object] = []

        def connect(self, callback) -> None:
            self.callbacks.append(callback)

    class _ErrorProcess:
        def __init__(self) -> None:
            self.started = _Signal()
            self.errorOccurred = _Signal()
            self.finished = _Signal()

        @staticmethod
        def errorString() -> str:  # noqa: N802
            return "controlled synchronous startup failure"

    class _FakePane:
        def __init__(self, _plan, *, profile=None, autostart=True) -> None:
            self.profile = profile
            self.autostart = autostart
            self.process = _ErrorProcess()
            self.properties: dict[str, object] = {}

        def setProperty(self, key: str, value) -> None:  # noqa: N802
            self.properties[key] = value

        @staticmethod
        def is_running() -> bool:
            return False

    status_updates: list[str] = []
    monkeypatch.setattr(
        window,
        "apply_terminal_mouse_paste_policy_for_design",
        lambda *_args: None,
    )
    monkeypatch.setattr(
        window,
        "update_session_status",
        lambda: status_updates.append("updated"),
    )
    with monkeypatch.context() as scoped:
        _set_closure_value(
            scoped,
            type(window).new_terminal_pane,
            "TerminalPane",
            _FakePane,
        )
        fake_pane = window.new_terminal_pane(
            TerminalPanePlan(title="startup-error", command=[], source="test"),
            autostart=False,
        )
    assert fake_pane.process.errorString()
    assert status_updates == ["updated"]

    class _DisposedPane:
        @staticmethod
        def property(_key: str):
            raise RuntimeError("deleted")

    type(window).handle_terminal_process_finished(
        SimpleNamespace(update_session_status=lambda: None),
        _DisposedPane(),
        0,
    )

    missing_widget_owner = SimpleNamespace(
        tabs=SimpleNamespace(count=lambda: 1, widget=lambda _index: None),
        terminal_panes_in=lambda _widget: [],
    )
    assert type(window).all_terminal_panes(missing_widget_owner) == []
    window.finish_closing_tab(QWidget())

    scheduled: list[object] = []

    class _TransitionTabs:
        def __init__(self) -> None:
            self.properties: dict[str, object] = {}

        def setProperty(self, key: str, value) -> None:  # noqa: N802
            self.properties[key] = value

        @staticmethod
        def setUpdatesEnabled(_enabled: bool) -> None:  # noqa: N802
            return None

        @staticmethod
        def currentIndex() -> int:  # noqa: N802
            return 2

        @staticmethod
        def currentWidget():  # noqa: N802
            return QWidget()

    deferred_pane = QWidget()
    deferred_pane.setProperty("terminalStartDeferredUntilTabReady", True)
    transition_owner = SimpleNamespace(
        _tab_transition_generation=0,
        tabs=_TransitionTabs(),
        moba_tab_guard=False,
        set_terminal_tab_paint_frozen=lambda _frozen: None,
        configure_product_connected_chrome=lambda: None,
        refresh_moba_left_dock_for_current_tab=lambda: None,
        active_terminal_pane=lambda: deferred_pane,
        tab_role=lambda _index: "terminal",
        current_design_id=lambda: "native",
        apply_interaction_state_tab_status=lambda *_args: None,
        finish_tab_transition=lambda _transition: None,
        start_deferred_terminal_pane_if_current=lambda *_args: None,
    )
    fake_timer = SimpleNamespace(
        singleShot=lambda _delay, callback: scheduled.append(callback),
    )
    with monkeypatch.context() as scoped:
        _set_closure_value(
            scoped,
            type(window).handle_tab_changed,
            "QTimer",
            fake_timer,
        )
        type(window).handle_tab_changed(transition_owner, 2)
    assert len(scheduled) == 3

    unrelated = QWidget()
    start_owner = SimpleNamespace(
        _tab_transition_generation=transition_owner._tab_transition_generation,
        tabs=SimpleNamespace(
            currentIndex=lambda: 2,
            currentWidget=lambda: unrelated,
        ),
    )
    deferred_pane.setProperty("terminalClosing", False)
    deferred_pane.is_running = lambda: False
    type(window).start_deferred_terminal_pane_if_current(
        start_owner,
        deferred_pane,
        2,
    )


def test_terminal_tab_status_non_moba_connected_refresh_and_home_recovery(
    gui_window,
    monkeypatch,
) -> None:
    from remote_ops_workspace.models import Profile

    _app, window = gui_window
    monkeypatch.setattr(
        window,
        "start_terminal_pane_when_active",
        lambda *_args: None,
    )
    window.open_terminal_tab(
        TerminalPanePlan(title="status-edge", command=[], source="test"),
        tab_title="Status edge",
        tab_status="connected",
    )
    status_index = window.find_tab_by_label("Status edge")
    assert status_index >= 0
    assert "connected" in window.literal_tab_tooltip(status_index)

    refreshed: list[str] = []
    monkeypatch.setattr(
        window,
        "refresh_moba_left_dock_for_current_tab",
        lambda: refreshed.append("refresh"),
    )
    profile = Profile(
        name="non-moba-connected",
        protocol="ssh",
        host="non-moba-connected.example.invalid",
    )
    panel = window.open_moba_connected_session_tab(
        profile,
        TerminalPanePlan(title="non-moba-connected", command=[], source="test"),
    )
    assert panel.moba_connected_state.profile_name == profile.name
    assert refreshed

    home_index = window.find_tab_by_role("home")
    assert home_index >= 0
    home = window.tabs.widget(home_index)
    window.tabs.removeTab(home_index)
    added_home: list[bool | None] = []
    monkeypatch.setattr(
        window,
        "add_welcome_tab",
        lambda *, select=None: added_home.append(select),
    )
    monkeypatch.setattr(window, "current_design_is_moba", lambda: True)
    window.close_tab(status_index if status_index < window.tabs.count() else 0)
    assert added_home == [None]
    if home is not None:
        home.deleteLater()


def test_remaining_terminal_pipeline_branch_outcomes(
    gui_window,
    monkeypatch,
) -> None:
    from remote_ops_workspace import gui, windows_conpty
    from remote_ops_workspace.models import Profile

    _app, window = gui_window
    profile = Profile(
        name="background-fallback-edge",
        protocol="sftp",
        host="background-fallback.example.invalid",
    )
    dialog = window.create_transfer_queue_dialog(profile)
    background_process = _closure_value(
        type(dialog).__init__,
        "_background_process",
    )
    with monkeypatch.context() as scoped:
        scoped.setattr(gui.sys, "platform", "win32")
        scoped.setattr(
            windows_conpty,
            "conpty_support",
            lambda: SimpleNamespace(supported=False),
        )
        process = background_process(window, interactive_auth=True)
    assert type(process).__name__ == "QtHiddenProcess"
    process.deleteLater()
    dialog.deleteLater()

    pane = _new_pane(window)
    pane.output.setTextCursor(pane.output.textCursor())
    pane.copy_terminal_selection()
    assert pane.output.property("terminalLastCopiedText") is None

    pane.reset_process_output_pipeline()
    pane._process_output_source_end_pending = True
    pane._process_output_source_drained = False
    channel_results = iter([(0, True), (1, False)])
    monkeypatch.setattr(
        pane,
        "pull_process_output_channel",
        lambda _channel: next(channel_results),
    )
    pane.pull_ended_process_output()
    assert pane._process_output_source_drained is False

    pane.reset_process_output_pipeline()
    pane._process_output_buffer.append(
        b"x"
        * (
            pane.OUTPUT_BUFFER_LOW_WATER_BYTES
            + pane.OUTPUT_SYNC_DRAIN_BUDGET_BYTES
            + 1
        )
    )
    refills: list[str] = []
    scheduled: list[bool] = []
    monkeypatch.setattr(pane, "append_decoded_process_output", lambda _payload: None)
    monkeypatch.setattr(pane, "refill_process_output", lambda: refills.append("refill"))
    monkeypatch.setattr(
        pane,
        "schedule_process_output_flush",
        lambda *, backlog=False: scheduled.append(backlog),
    )
    pane.flush_process_output_now()
    assert refills == []
    assert scheduled == [True]

    pane.reset_process_output_pipeline()
    decoded: list[str] = []
    with monkeypatch.context() as scoped:
        scoped.setattr(pane, "append_process_text", decoded.append)
        pane.append_decoded_process_output(b"\xc5")
    assert decoded == []
    pane.reset_process_output_pipeline()

    pane._process_output_source_end_pending = True
    pane._process_output_source_drained = False

    def mark_drained() -> None:
        pane._process_output_source_drained = True

    monkeypatch.setattr(pane, "pull_ended_process_output", mark_drained)
    pane.finish_deferred_process_output()
    assert pane._process_output_source_drained is True

    rendered: list[str] = []
    pane._pty_initial_clear_pending = True
    pane.terminal_emulator._alternate_screen = False
    monkeypatch.setattr(
        type(pane.terminal_emulator),
        "feed",
        lambda _self, _text: "visible",
    )
    monkeypatch.setattr(pane, "is_initial_conpty_screen_clear", lambda _text: False)
    monkeypatch.setattr(pane, "terminal_startup_context_text", lambda: "")
    monkeypatch.setattr(pane, "normalized_initial_pty_transcript", lambda text: text)
    monkeypatch.setattr(pane, "normalized_initial_prompt_transcript", lambda text: text)
    monkeypatch.setattr(pane, "render_terminal_transcript", rendered.append)
    pane.append_process_text("visible")
    assert rendered == ["visible"]
    rendered.clear()
    type(pane).append_decoded_process_output(pane, b"")
    assert rendered == []


def test_stop_and_window_close_process_optional_close_edges(
    gui_window,
    monkeypatch,
) -> None:
    from types import SimpleNamespace

    from PyQt6.QtWidgets import QWidget

    _app, window = gui_window

    class _StoppedPane:
        @staticmethod
        def request_stop(*, policy) -> bool:
            assert policy == window.CLOSE_STOP_POLICY
            return False

    before = window.log.toPlainText()
    window.stop_terminal_panes([_StoppedPane()])
    assert window.log.toPlainText() == before

    background_tab = QWidget()
    background_index = window.add_workspace_tab(
        background_tab,
        "Background close edge",
        select=False,
        role="session",
    )
    assert background_index != window.tabs.currentIndex()
    window.close_tab(background_index)
    assert window.tabs.indexOf(background_tab) == -1

    killed: list[str] = []
    prepared: list[str] = []
    pane = SimpleNamespace(
        process=SimpleNamespace(
            kill=lambda: killed.append("kill"),
            close="not-callable",
        ),
        prepare_for_close=lambda: prepared.append("prepare"),
    )
    original_running = window.running_terminal_panes
    original_confirm = window.confirm_stop_processes
    monkeypatch.setattr(window, "running_terminal_panes", lambda: [pane])
    monkeypatch.setattr(window, "confirm_stop_processes", lambda *_args: True)

    class _Event:
        accepted = False

        def accept(self) -> None:
            self.accepted = True

        @staticmethod
        def ignore() -> None:
            raise AssertionError("close should not be ignored")

    event = _Event()
    window.closeEvent(event)
    assert event.accepted is True
    assert prepared == ["prepare"]
    assert killed == ["kill"]
    monkeypatch.setattr(window, "running_terminal_panes", original_running)
    monkeypatch.setattr(window, "confirm_stop_processes", original_confirm)

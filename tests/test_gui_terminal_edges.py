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


def test_terminal_start_restart_and_nonblocking_stop_edges(
    gui_window,
    monkeypatch,
) -> None:
    from PyQt6.QtCore import QProcess

    from remote_ops_workspace import gui
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
        gui,
        "assert_profile_launch_allowed",
        lambda *_args, **_kwargs: (_ for _ in ()).throw(ValueError("controlled policy")),
    )
    pane.start()
    assert pane.status.text() == "policy blocked"
    assert "controlled policy" in pane.output.toPlainText()

    monkeypatch.setattr(gui, "assert_profile_launch_allowed", lambda *_args, **_kwargs: None)
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
    monkeypatch.setattr(gui, "stop_process", lambda *_args, **_kwargs: next(outcomes))
    process.process_state = QProcess.ProcessState.Running
    first = pane.stop()
    second = pane.stop()
    assert first.kill_requested is True and first.finished is False
    assert second.kill_requested is False and second.finished is True
    transcript = pane.output.toPlainText()
    assert "killed after graceful stop timeout" in transcript
    assert "did not exit after kill request" in transcript


def test_terminal_macro_capture_replay_and_cancel_edges(
    gui_window,
    monkeypatch,
) -> None:
    from PyQt6.QtCore import QProcess
    from PyQt6.QtTest import QTest

    from remote_ops_workspace import gui
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
    monkeypatch.setattr(gui.time, "monotonic", lambda: next(values))
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

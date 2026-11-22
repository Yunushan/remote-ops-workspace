"""Moba menu and rail actions for the current terminal session."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from functools import partial
from typing import TYPE_CHECKING

from PyQt6.QtCore import QProcess
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QInputDialog, QMenu

from .command_safety import option_value
from .moba_macros import MacroNameExistsError, MobaMacroRecording, MobaMacroStore

if TYPE_CHECKING:
    from .gui_terminal import TerminalPane


class TerminalMacroControls:
    def __init__(self, active: Callable[[], TerminalPane | None], notify: Callable[[str], None]) -> None:
        self.active = active
        self.notify = notify
        self.pane = active()
        self.sequence = self.pane.macro_replay_sequence if self.pane is not None else None
        self.saved: dict[str, int] = {}
        try:
            self.saved = {record.name: len(record.events) for record in MobaMacroStore().load()}
        except (OSError, ValueError):
            self.notify("The workspace macro store could not be read.")

    def current(self) -> bool:
        pane = self.pane
        return (
            pane is not None and self.active() is pane and not pane.property("terminalClosing")
            and pane.process.state() == QProcess.ProcessState.Running
            and pane.macro_replay_sequence == self.sequence
        )

    def ready(self) -> bool:
        return self.current() and self.pane is not None and self.pane.macro_record_button.isEnabled()

    def actions(self) -> list[tuple[str, bool, Callable[[], None]]]:
        pane = self.pane
        if pane is not None and self.current() and pane.macro_stop_button.isEnabled():
            return [("Stop recording", True, self.stop), ("Cancel recording", True, self.cancel)]
        if pane is not None and self.current() and pane.macro_replay_active:
            return [("Cancel replay", True, self.cancel)]
        actions = [("Record new macro", self.ready(), self.record)]
        if pane is not None and pane.macro_last_recording is not None and pane.macro_last_recording.name not in self.saved:
            actions.append(("Replay last recording", self.ready(), self.replay_last))
        return actions

    def record(self) -> None:
        if self.pane is not None and self.ready():
            self.pane.start_macro_capture()
            self.pane.output.setFocus()

    def cancel(self) -> None:
        if self.pane is not None and self.current() and self.pane.macro_cancel_button.isEnabled():
            self.pane.cancel_macro_capture()

    def replay_last(self) -> None:
        if self.pane is not None and self.ready():
            self.pane.replay_macro_capture(still_current=self.ready)

    def stop(self) -> None:
        if self.pane is not None and self.current() and self.pane.macro_stop_button.isEnabled():
            self.pane.stop_macro_capture(save=self.save)

    def save(self, recording: MobaMacroRecording) -> MobaMacroRecording | None:
        prompt = "Please enter a name for this macro"
        while self.current():
            name, ok = QInputDialog.getText(self.pane, "Save terminal macro", prompt)
            if not ok or not self.current():
                return None
            try:
                named = replace(recording, name=option_value(name.strip(), "macro name"))
            except ValueError:
                prompt = "Enter a nonempty macro name without control characters or a leading dash."
                continue
            try:
                MobaMacroStore().add(named)
            except MacroNameExistsError:
                prompt = "That macro name already exists. Please choose another name."
                continue
            except (OSError, ValueError):
                self.notify("The workspace macro store could not be updated.")
                return None
            return named
        return None

    def replay(self, name: str) -> None:
        if self.pane is None or not self.ready():
            return
        try:
            recording = MobaMacroStore().get(name)
            if not recording.events or any(not 0 <= event.delay_ms <= 2_147_483_647 for event in recording.events):
                raise ValueError("invalid replay timing or empty recording")
        except (OSError, ValueError, KeyError):
            self.notify("This saved macro could not be replayed.")
            return
        self.pane.replay_macro_capture(saved=recording, still_current=self.ready)

    def populate(self, menu: QMenu) -> None:
        # Keep the preset's primary action and its metadata for the Macros dialog.
        primary, = (action for action in menu.actions() if action.property("menuActionKey") == "macros")
        for action in menu.actions():
            if action is not primary:
                menu.removeAction(action)
                action.deleteLater()

        def insert(label: str, enabled: bool, callback: Callable[[], None] | None = None) -> None:
            action = QAction(label.replace("&", "&&"), menu)
            action.setEnabled(enabled)
            if callback is not None:
                # Qt weakly references a bound Python method. Keep these
                # per-popup controls alive for the lifetime of their actions.
                action.triggered.connect(lambda _checked=False: callback())
            menu.insertAction(primary, action)

        for label, enabled, callback in self.actions():
            insert(label, enabled, callback)
        menu.insertSeparator(primary)
        insert("Saved macros", False)
        ready = self.ready()
        for name, count in self.saved.items():
            insert(name, ready and count > 0, partial(self.replay, name))
        menu.insertSeparator(primary)

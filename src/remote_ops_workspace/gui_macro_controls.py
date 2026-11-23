"""Moba menu and rail actions for the current terminal session."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from functools import partial
from typing import TYPE_CHECKING

from PyQt6.QtCore import QPoint, QProcess, Qt, QTimer
from PyQt6.QtGui import QAction, QKeySequence, QShortcut
from PyQt6.QtWidgets import (
    QDialog,
    QInputDialog,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMenu,
    QVBoxLayout,
)

from .command_safety import option_value
from .gui_values import _required_gui_value
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

    def show_chooser(self, pane: TerminalPane) -> None:
        popup = QDialog(pane, Qt.WindowType.Popup)
        popup.setObjectName("mobaQuickMacroPopup")
        popup.setWindowTitle("Quick macros")
        popup.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        layout = QVBoxLayout(popup)
        layout.setContentsMargins(2, 2, 2, 2)
        layout.setSpacing(0)
        search = QLineEdit()
        search.setObjectName("mobaQuickMacroFilter")
        search.setAccessibleName("Search macro")
        search.setPlaceholderText("Search macro")
        layout.addWidget(search)
        names = QListWidget()
        names.setObjectName("mobaQuickMacroNames")
        names.setAccessibleName("Saved macros")
        names.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        layout.addWidget(names)
        viewport = pane.output_viewport
        caret = pane.output.terminal_cursor_rect()
        anchor = viewport.mapToGlobal(caret.topLeft())
        bounds = _required_gui_value(viewport.screen(), "terminal screen").availableGeometry()
        width = min(bounds.width(), max(204, 20 * names.fontMetrics().horizontalAdvance("M")))
        record_label = "Record new macro..."
        chosen = False

        def filter_names(text: str) -> None:
            query = text.casefold()
            names.clear()
            names.addItems([name for name, count in self.saved.items() if count and query in name.casefold()])
            if query in record_label.casefold():
                record = QListWidgetItem(record_label, names)
                record.setData(Qt.ItemDataRole.UserRole, True)
            names.setCurrentRow(0)
            names.setVisible(names.count() > 0)
            height = search.sizeHint().height() + 4
            if names.count():
                height += min(8, names.count()) * names.sizeHintForRow(0) + 2 * names.frameWidth()
            popup.setFixedSize(width, height)
            x = max(bounds.left(), min(anchor.x(), bounds.right() - width + 1))
            y = max(bounds.top(), min(anchor.y(), bounds.bottom() - height + 1))
            popup.move(QPoint(x, y))

        def choose() -> None:
            nonlocal chosen
            # Some Qt styles emit both itemClicked and itemActivated for one click.
            if chosen:
                return
            item = names.currentItem()
            if item is not None:
                chosen = True
                name = item.text()
                record = item.data(Qt.ItemDataRole.UserRole)
                # Return to the Qt input handler before a replay opens a modal
                # review. Closing the pane also cancels this pending action.
                dispatch = QTimer(pane)
                dispatch.setSingleShot(True)
                dispatch.timeout.connect(lambda: self.record() if record else self.replay(name))
                dispatch.timeout.connect(dispatch.deleteLater)
                popup.accept()
                dispatch.start(0)

        search.textChanged.connect(filter_names)
        search.returnPressed.connect(choose)
        names.itemClicked.connect(choose)
        names.itemActivated.connect(choose)
        for key, step in ((Qt.Key.Key_Up, -1), (Qt.Key.Key_Down, 1)):
            shortcut = QShortcut(QKeySequence(key), search, context=Qt.ShortcutContext.WidgetShortcut)
            shortcut.activated.connect(lambda step=step: names.setCurrentRow(
                max(0, min(names.count() - 1, names.currentRow() + step))
            ))
        filter_names("")
        popup.show()
        search.setFocus()

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

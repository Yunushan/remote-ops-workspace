"""Drive the release wheel's visible Moba macro controls in a disposable SSH workspace."""

from __future__ import annotations

import time
from dataclasses import replace

from PyQt6.QtCore import Qt, QTimer
from PyQt6.QtTest import QTest
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QDialogButtonBox,
    QInputDialog,
    QLineEdit,
    QMessageBox,
)

from remote_ops_workspace.gui import create_main_window
from remote_ops_workspace.models import Profile
from remote_ops_workspace.terminal import terminal_plan_for_profile
from scripts.check_moba_macro_live_evidence import TRANSCRIPT_BYTE, TRANSCRIPT_READY
from scripts.qt_release_capture import FIXTURE, HOST, MACRO_INACTIVE_USER, MACRO_USER, PORT

MACRO_NAME = "Timed workspace macro"
PROFILE = "Macro release capture receiver"
INACTIVE_PROFILE = "Inactive receiver"
RECEIVER = "/usr/local/lib/row-macro-receiver.py"
LEFT = Qt.MouseButton.LeftButton


def wait_for(predicate, label: str) -> None:
    deadline = time.monotonic() + 12
    while time.monotonic() < deadline:
        if predicate():
            return
        QTest.qWait(10)
    raise TimeoutError(f"the macro fixture did not observe {label}")


def click(button) -> None:
    if not button or not button.isVisible() or not button.isEnabled():
        raise ValueError("a required macro control is unavailable")
    QTest.mouseClick(button, LEFT)


def receiver(pane) -> int:
    rows = TRANSCRIPT_READY.findall(pane.output.toPlainText())
    return int(rows[0][0]) if len(rows) == 1 else 0


def count(pane) -> int:
    return len(TRANSCRIPT_BYTE.findall(pane.output.toPlainText()))


def in_dialog(trigger, respond):
    # A modal dialog starts a nested event loop during the physical click.
    # Reject any unexpected dialog and propagate the original failure outside Qt.
    result, errors = [], []
    timer = QTimer()
    deadline = time.monotonic() + 8

    def answer():
        dialog = QApplication.activeModalWidget()
        if dialog is None and time.monotonic() < deadline:
            return
        timer.stop()
        try:
            if not isinstance(dialog, QDialog) or not dialog.isVisible():
                raise ValueError("macro interaction did not open a visible dialog")
            result.append(respond(dialog))
        except Exception as error:
            errors.append(error)
            if isinstance(dialog, QDialog):
                dialog.reject()

    timer.timeout.connect(answer)
    timer.start(20)
    try:
        trigger()
        wait_for(lambda: result or errors, "macro dialog completion")
    finally:
        timer.stop()
    if errors:
        raise errors[0]
    return result[0]


class MacroWorkspace:
    def __init__(self):
        self.app, self.window = create_main_window(["macro-release-capture"], show=False, preview_samples=False)
        self.window.resize(1440, 900)
        self.window.show()
        self.window.set_design_preset("mobaxterm")
        self.window.activateWindow()
        self.app.processEvents()
        self.panes = []

    def save_profiles(self):
        self.window.store.save([
            Profile(name=name, protocol="ssh", host=HOST, port=PORT, username=user,
                    identity_file=str(FIXTURE / "identity"), options={
                        "strict_host_key_checking": "yes", "user_known_hosts_file": str(FIXTURE / "known_hosts"),
                        "identity_agent": "none", "ssh_multiplex": "false",
                    })
            for name, user in ((PROFILE, MACRO_USER), (INACTIVE_PROFILE, MACRO_INACTIVE_USER))
        ])

    def open_receiver(self, name, *, reopened=False):
        profile = self.window.store.get(name)
        plan = terminal_plan_for_profile(profile)
        plan = replace(plan, command=[
            plan.command[0], "-oBatchMode=yes", "-oIdentitiesOnly=yes", *plan.command[1:],
            "/usr/local/bin/python", "-I", "-u", RECEIVER, *(["reopened"] if reopened else []),
        ])
        panel = self.window.open_moba_connected_session_tab(profile, plan, remote_path=f"/home/{profile.username}")
        pane = panel.terminal_pane
        self.panes.append(pane)
        wait_for(lambda: receiver(pane), f"{name} SSH receiver")
        if (self.window.active_terminal_pane() is not pane or pane.header.isVisible()
                or pane.macro_record_button.isVisible() or not self.window.tabs.property("mobaConnectedRouteKey")):
            raise ValueError("macro capture requires the active Moba connected session with its toolbar hidden")
        return pane, self.window.tabs.indexOf(panel)

    def select_tab(self, index, pane):
        bar = self.window.tabs.tabBar()
        point = bar.tabRect(index).center()
        if not bar.isVisible() or bar.tabAt(point) != index:
            raise ValueError("the requested SSH destination tab is unavailable")
        QTest.mouseClick(bar, LEFT, pos=point)
        wait_for(lambda: self.window.active_terminal_pane() is pane, "active saved SSH profile")

    def menu_action(self, label, *, saved=False):
        bar = self.window.menuBar()
        top, = [item for item in bar.actions() if item.isVisible() and item.text() == "Macros"]
        point = bar.actionGeometry(top).center()
        if not bar.isVisible() or bar.actionAt(point) is not top or not top.isEnabled():
            raise ValueError("the visible Macros menu is unavailable")
        QTest.mouseClick(bar, LEFT, pos=point)
        menu = top.menu()
        wait_for(menu.isVisible, "visible Macros dropdown")
        entries = [item for item in menu.actions() if item.isVisible() and not item.isSeparator()]
        section, = [item for item in entries if item.text() == "Saved macros" and not item.isEnabled()]
        selected, = [item for item in entries if item.text() == label and item.isEnabled()]
        point = menu.actionGeometry(selected).center()
        if menu.actionAt(point) is not selected or (saved and entries.index(selected) <= entries.index(section)):
            raise ValueError("the saved macro did not appear in the visible menu section")
        route = {"menu": top.text(), "saved_section": section.text(), "selected_entry": selected.text()}
        QTest.mouseClick(menu, LEFT, pos=point)
        return route

    def record(self, pane):
        self.window.raise_()
        self.window.activateWindow()
        if not QTest.qWaitForWindowActive(self.window, 2500):
            raise ValueError("the macro workspace did not become active")
        QTest.mouseClick(pane.output.viewport(), LEFT)
        route = self.menu_action("Record new macro")
        stop = self.window.moba_recording_stop
        wait_for(lambda: pane.macro_capture_state and pane.macro_capture_state.active, "capture after Record new macro")
        wait_for(stop.isVisible, "visible recording ribbon Stop")
        wait_for(pane.output.hasFocus, "terminal keyboard focus after opening the Macros menu")
        result = {"preset": self.window.current_design_id(), "menu": route["menu"], "record": route["selected_entry"],
                  "stop": stop.text(), "stop_object": stop.objectName(), "focused_output": pane.output.objectName()}
        QTest.keyClicks(pane.output, "a")
        QTest.qWait(420)
        QTest.keyClicks(pane.output, "b")
        QTest.qWait(330)
        QTest.keyClick(pane.output, Qt.Key.Key_Return)
        wait_for(lambda: count(pane) == 3, "three typed SSH bytes")

        def name(dialog):
            if not isinstance(dialog, QInputDialog):
                raise ValueError("Stop recording did not open the macro naming dialog")
            edit, = [item for item in dialog.findChildren(QLineEdit) if item.isVisible() and item.isEnabled()]
            click(edit)
            QTest.keyClicks(edit, MACRO_NAME)
            result.update(prompt=dialog.labelText(), accepted_name=edit.text())
            click(dialog.findChild(QDialogButtonBox).button(QDialogButtonBox.StandardButton.Ok))

        in_dialog(lambda: click(stop), name)
        return result

    def review(self, pane, button, *, inactive=None, before_answer=None):
        route = {}
        result = {"before": count(pane)}
        if inactive is not None:
            result["inactive_before"] = count(inactive)

        def respond(dialog):
            if not isinstance(dialog, QMessageBox):
                raise ValueError("the selected saved macro did not open a replay review")
            result.update(text=dialog.text(), decision=button.name,
                          default_is_cancel=dialog.defaultButton() is dialog.button(QMessageBox.StandardButton.Cancel))
            if not result["default_is_cancel"]:
                raise ValueError("the replay review did not default to Cancel")
            if before_answer is not None:
                before_answer()
            click(dialog.button(button))

        in_dialog(lambda: route.update(self.menu_action(MACRO_NAME, saved=True)), respond)
        return result, route

    def close(self):
        for pane in self.panes:
            pane.stop()
        self.window.close()
        self.app.processEvents()

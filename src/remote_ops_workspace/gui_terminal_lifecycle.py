from __future__ import annotations

import time
from typing import TYPE_CHECKING, ClassVar

from PyQt6.QtCore import QTimer

from .gui_designs import (
    PRODUCT_REFERENCE_TAB_PRESET_IDS,
    gui_design_interaction_state,
    gui_design_preset_reference_tab_route,
)
from .gui_terminal import TerminalPane
from .terminal import default_shell_plan

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QStatusBar, QTabWidget, QTextEdit, QWidget

    from .gui_connected import ConnectedSftpDock
    from .gui_lifecycle import ProcessStopPolicy
    from .gui_ssh_connection import SharedSshConnectionState
    from .models import Profile
    from .terminal import TerminalPanePlan


class TerminalLifecycle:
    """Open, track, and close terminal panes in the desktop workspace."""

    if TYPE_CHECKING:
        CLOSE_FORCE_CLOSE_DELAY_MS: ClassVar[int]
        CLOSE_STOP_POLICY: ClassVar[ProcessStopPolicy]
        _closing_tab_widgets: list[QWidget]
        _status_message_override: str | None
        _status_message_override_deadline: float
        log: QTextEdit
        moba_connected_dock: ConnectedSftpDock | None
        tabs: QTabWidget

        def add_welcome_tab(self, *, select: bool | None = None) -> None: ...
        def add_workspace_tab(self, widget: QWidget, title: str, *, select: bool = True, role: str = "session") -> int: ...
        def all_terminal_panes(self) -> list[TerminalPane]: ...
        def apply_reference_session_action_route_to_terminal_tab(self, pane: QWidget, tab_title: str, index: int) -> None: ...
        def apply_reference_status_bar_route_to_terminal_tab(self, pane: QWidget, tab_title: str) -> None: ...
        def apply_reference_tab_chrome_route_to_terminal_tab(self, pane: QWidget, tab_title: str, index: int) -> None: ...
        def apply_reference_tab_route_to_terminal_tab(self, pane: QWidget, tab_title: str) -> None: ...
        def apply_terminal_mouse_paste_policy_for_design(self, pane: TerminalPane, preset_id: str) -> None: ...
        def build_product_reference_tab_surface(self, pane: TerminalPane) -> QWidget: ...
        def confirm_stop_processes(self, title: str, count: int) -> bool: ...
        def current_design_id(self) -> str: ...
        def current_design_is_moba(self) -> bool: ...
        def find_tab_by_role(self, role: str) -> int: ...
        def prepare_tab_transition(self, index: int) -> None: ...
        def refresh_moba_left_dock_for_current_tab(self) -> None: ...
        def refresh_special_tab_buttons(self) -> None: ...
        def remember_terminal_plan(self, plan: TerminalPanePlan, *, profile: Profile | None = None) -> None: ...
        def running_terminal_panes(self) -> list[TerminalPane]: ...
        def set_literal_tab_tooltip(self, index: int, text: object, *, update_base: bool = True) -> None: ...
        def set_workspace_tab_index(self, index: int) -> None: ...
        def start_deferred_terminal_pane_if_current(
            self, pane: TerminalPane, index: int, transition: int | None = None,
        ) -> None: ...
        def statusBar(self) -> QStatusBar: ...
        def tab_role(self, index: int) -> str: ...
        def terminal_panes_in(self, widget: QWidget) -> list[TerminalPane]: ...

    def open_local_terminal_tab(self) -> None:
        self.open_terminal_tab(default_shell_plan(self.next_shell_index()))

    def next_shell_index(self) -> int:
        count = sum(1 for pane in self.all_terminal_panes() if pane.plan.source == "shell")
        return count + 1

    def profile_tab_status(self) -> str:
        return gui_design_interaction_state(self.current_design_id()).active_tab_status

    def open_terminal_tab(
        self,
        plan: TerminalPanePlan,
        *,
        profile: Profile | None = None,
        tab_title: str | None = None,
        tab_status: str | None = None,
    ) -> None:
        # Construct the pane before inserting the tab, but start the child
        # only after Qt has selected and laid out the page. This prevents a
        # transient unparented terminal surface from flashing during tab
        # changes and gives ConPTY its final viewport dimensions.
        pane = self.new_terminal_pane(plan, profile=profile, autostart=False)
        self.remember_terminal_plan(plan, profile=profile)
        tab_content: QWidget = pane
        reference_label = tab_title or plan.title
        reference_route = (
            gui_design_preset_reference_tab_route(self.current_design_id())
            if self.current_design_id() in PRODUCT_REFERENCE_TAB_PRESET_IDS
            else None
        )
        if reference_route is not None and reference_label == reference_route.active_tab_label:
            tab_content = self.build_product_reference_tab_surface(pane)
        index = self.add_workspace_tab(tab_content, reference_label, role="terminal")
        if tab_content is not pane:
            # Route metadata is asserted on the tab's root widget as well
            # as on the embedded TerminalPane.  Preserve both surfaces so
            # the connected document wrapper remains fully inspectable.
            self.apply_reference_tab_route_to_terminal_tab(tab_content, reference_label)
            self.apply_reference_tab_chrome_route_to_terminal_tab(tab_content, reference_label, index)
            self.apply_reference_status_bar_route_to_terminal_tab(tab_content, reference_label)
            self.apply_reference_session_action_route_to_terminal_tab(tab_content, reference_label, index)
        self.apply_reference_tab_route_to_terminal_tab(pane, tab_title or plan.title)
        if tab_status:
            self.set_literal_tab_tooltip(
                index,
                f"{tab_title or plan.title}: {tab_status}",
                update_base=False,
            )
        self.apply_reference_tab_chrome_route_to_terminal_tab(pane, tab_title or plan.title, index)
        self.update_session_status()
        self.apply_reference_status_bar_route_to_terminal_tab(pane, tab_title or plan.title)
        self.apply_reference_session_action_route_to_terminal_tab(pane, tab_title or plan.title, index)
        self.start_terminal_pane_when_active(pane, index)

    def start_terminal_pane_when_active(self, pane: TerminalPane, index: int) -> None:
        """Start a deferred pane after its tab has a stable parent/layout."""

        pane.setProperty("terminalStartDeferredUntilTabReady", True)

        def start_if_current() -> None:
            self.start_deferred_terminal_pane_if_current(pane, index)

        QTimer.singleShot(0, start_if_current)

    def new_terminal_pane(
        self,
        plan: TerminalPanePlan,
        *,
        profile: Profile | None = None,
        autostart: bool = True,
    ) -> TerminalPane:
        # Keep the normal launch path explicit for the source-policy
        # guard, while allowing reference-render harnesses to opt into
        # deferred startup without changing production defaults.
        if autostart:
            pane = TerminalPane(plan, profile=profile)
        else:
            pane = TerminalPane(plan, profile=profile, autostart=False)
        set_authentication_handler = getattr(
            pane,
            "set_terminal_authentication_change_handler",
            None,
        )
        if callable(set_authentication_handler):
            set_authentication_handler(
                self.refresh_moba_background_after_terminal_auth
            )
        ssh_connection = getattr(pane, "ssh_connection", None)
        if ssh_connection is not None:
            ssh_connection.changed.connect(
                lambda state, terminal_pane=pane: self.refresh_moba_shared_ssh_state(terminal_pane, state),
            )
        self.apply_terminal_mouse_paste_policy_for_design(
            pane,
            self.current_design_id(),
        )
        pane.setProperty("terminalAutoCloseOnCleanExit", plan.source == "shell")
        pane.process.started.connect(self.update_session_status)
        pane.process.started.connect(
            lambda terminal_pane=pane: self.refresh_moba_background_after_terminal_start(
                terminal_pane
            )
        )
        pane.process.errorOccurred.connect(
            lambda _error: self.update_session_status()
        )
        if pane.is_running():
            # Immediate-start panes emit ``started`` during construction,
            # before the window can attach the signal above.
            self.refresh_moba_background_after_terminal_start(pane)
        pane.process.finished.connect(
            lambda exit_code, _exit_status, terminal_pane=pane: self.handle_terminal_process_finished(
                terminal_pane,
                exit_code,
            )
        )
        # Hidden-process startup can fail synchronously (for example when
        # an executable is missing), before the signal connections above
        # exist. Publish that failure immediately so the status bar cannot
        # remain stale after an SSH or helper launch error.
        error_string_getter = getattr(pane.process, "errorString", None)
        if callable(error_string_getter) and error_string_getter():
            self.update_session_status()
        return pane

    def refresh_moba_shared_ssh_state(
        self, pane: TerminalPane, state: SharedSshConnectionState,
    ) -> None:
        dock = self.moba_connected_dock
        if dock is None or dock.state.ssh_connection_key != pane.ssh_connection_key:
            return
        selected = dock.sync_shared_ssh_connection()
        if state == selected and state.phase in {"connected", "connection-lost", "closing", "closed"}:
            dock.schedule_background_state_activation()

    def refresh_moba_background_after_terminal_start(self, pane: TerminalPane) -> None:
        """Give an interactive SSH prompt time to authenticate before reuse."""

        try:
            dock = self.moba_connected_dock
            profile = getattr(pane, "profile", None)
            if dock is None or profile is None:
                return
            if profile.name != dock.state.profile_name:
                return
            schedule_activation = getattr(
                dock,
                "schedule_background_state_activation",
                None,
            )
        except RuntimeError:
            # A tab replacement can delete the dock between a process
            # signal and this deferred refresh callback.
            return
        if callable(schedule_activation):
            try:
                schedule_activation(1_500)
            except RuntimeError:
                return

    def refresh_moba_background_after_terminal_auth(
        self,
        pane: TerminalPane,
        prompt_active: bool,
    ) -> None:
        """Recheck background SSH after the terminal password prompt closes."""

        if prompt_active:
            return
        try:
            dock = self.moba_connected_dock
            profile = getattr(pane, "profile", None)
            if dock is None or profile is None:
                return
            if profile.name != dock.state.profile_name:
                return
            schedule_activation = getattr(
                dock,
                "schedule_background_state_activation",
                None,
            )
        except RuntimeError:
            return
        if callable(schedule_activation):
            try:
                # OpenSSH may need one event-loop turn to create a shared
                # control connection after accepting the password.
                schedule_activation(250)
            except RuntimeError:
                return

    def handle_terminal_process_finished(
        self,
        pane: TerminalPane,
        exit_code: int,
    ) -> None:
        self.update_session_status()
        try:
            auto_close = bool(pane.property("terminalAutoCloseOnCleanExit"))
            closing = bool(pane.property("terminalClosing"))
        except RuntimeError:
            return
        if exit_code != 0 or not auto_close or closing:
            return
        QTimer.singleShot(
            0,
            lambda terminal_pane=pane: self.close_finished_shell_tab(
                terminal_pane
            ),
        )

    def close_finished_shell_tab(self, pane: TerminalPane) -> None:
        """Close a standalone shell tab after its shell exits successfully."""

        try:
            if pane.is_running() or bool(pane.property("terminalClosing")):
                return
            index = self.tabs.indexOf(pane)
        except RuntimeError:
            return
        if index >= 0 and self.tab_role(index) == "terminal":
            self.close_tab(index)

    def close_tab(self, index: int) -> None:
        widget = self.tabs.widget(index)
        if widget is None:
            return
        role = self.tab_role(index)
        if role == "home":
            self.set_workspace_tab_index(index)
            self.statusBar().showMessage("Home tab stays open")
            return
        if role == "new-session":
            self.open_local_terminal_tab()
            return
        running = [pane for pane in self.terminal_panes_in(widget) if pane.is_running()]
        if running and not self.confirm_stop_processes("Close tab", len(running)):
            return
        title = self.tabs.tabText(index)
        if index == self.tabs.currentIndex() and self.tabs.count() > 1:
            successor_index = index + 1 if index + 1 < self.tabs.count() else index - 1
            self.prepare_tab_transition(successor_index)
            self.tabs.setProperty(
                "terminalActiveTabClosePrepaintGuarded",
                bool(self.tabs.property("terminalTabPrepaintGuardActive"))
                or bool(self.tabs.property("terminalTabTransitionActive")),
            )
        self.tabs.removeTab(index)
        if running:
            self._closing_tab_widgets.append(widget)
            for pane in running:
                pane.prepare_for_close()
                pane.process.finished.connect(
                    lambda *_args, closing_widget=widget: self.finish_closing_tab(
                        closing_widget
                    )
                )
            self.stop_terminal_panes(running)
            self.finish_closing_tab(widget)
            QTimer.singleShot(
                self.CLOSE_FORCE_CLOSE_DELAY_MS,
                lambda closing_widget=widget: self.force_finish_closing_tab(
                    closing_widget
                ),
            )
        else:
            widget.deleteLater()
        self.log.append(f"TAB CLOSED: {title}")
        if self.current_design_is_moba() and self.find_tab_by_role("home") < 0:
            self.add_welcome_tab()
        self.refresh_special_tab_buttons()
        self.refresh_moba_left_dock_for_current_tab()
        self.update_session_status()

    def stop_terminal_panes(self, panes: list[TerminalPane]) -> None:
        requested = 0
        for pane in panes:
            if pane.request_stop(policy=self.CLOSE_STOP_POLICY):
                requested += 1
        if requested:
            self.log.append(f"STOP REQUESTED: {requested} process pane(s)")

    def finish_closing_tab(self, widget: QWidget) -> None:
        if widget not in self._closing_tab_widgets:
            return
        if any(pane.is_running() for pane in self.terminal_panes_in(widget)):
            return
        self._closing_tab_widgets.remove(widget)
        widget.deleteLater()

    def force_finish_closing_tab(self, widget: QWidget) -> None:
        """Finish a closed tab when a transport ignores terminate/kill."""

        if widget not in self._closing_tab_widgets:
            return
        for pane in self.terminal_panes_in(widget):
            if not pane.is_running():
                continue
            pane.process.kill()
            close_process = getattr(pane.process, "close", None)
            if callable(close_process):
                close_process()
        self.finish_closing_tab(widget)

    def show_transient_status_message(
        self,
        message: str,
        timeout_ms: int = 1800,
    ) -> None:
        """Keep a completed workflow result visible across late process signals."""

        timeout_ms = max(1, int(timeout_ms))
        self._status_message_override = message
        self._status_message_override_deadline = (
            time.monotonic() + timeout_ms / 1000
        )
        self.statusBar().showMessage(message, timeout_ms)
        QTimer.singleShot(timeout_ms, self.expire_transient_status_message)

    def expire_transient_status_message(self) -> None:
        if self._status_message_override is None:
            return
        if time.monotonic() < self._status_message_override_deadline:
            return
        self._status_message_override = None
        self._status_message_override_deadline = 0.0
        self.update_session_status()

    def update_session_status(self) -> None:
        try:
            if self._status_message_override is not None:
                remaining_ms = int(
                    (self._status_message_override_deadline - time.monotonic())
                    * 1000
                )
                if remaining_ms > 0:
                    self.statusBar().showMessage(
                        self._status_message_override,
                        max(1, remaining_ms),
                    )
                    return
                self._status_message_override = None
                self._status_message_override_deadline = 0.0
            running = len(self.running_terminal_panes())
            if running:
                self.statusBar().showMessage(f"Running process panes: {running}")
            else:
                self.statusBar().showMessage("No running process panes")
        except RuntimeError:
            # Ignore late process signals after Qt has disposed of the window.
            return

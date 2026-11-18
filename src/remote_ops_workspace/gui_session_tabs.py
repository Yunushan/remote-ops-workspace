from __future__ import annotations

from typing import TYPE_CHECKING, ClassVar

from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QSplitter, QWidget

from .gui_designs import get_gui_design_preset, gui_design_interaction_state
from .gui_terminal import TerminalPane
from .gui_values import _required_gui_value
from .terminal import default_shell_plan, split_shell_plans

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QStatusBar, QTabWidget, QTextEdit

    from .gui_connected import ConnectedSessionPanel
    from .gui_designs import GuiDesignPreset, GuiInteractionState
    from .moba_connected import MobaConnectedSessionState
    from .models import Profile
    from .terminal import TerminalPanePlan


class SessionTabActions:
    """Split, duplicate, navigate, and recover terminal sessions in the workspace."""

    if TYPE_CHECKING:
        _connected_session_panel_type: ClassVar[type[ConnectedSessionPanel]]
        tabs: QTabWidget
        log: QTextEdit
        moba_tab_guard: bool
        recent_terminal_plans: list[tuple[TerminalPanePlan, Profile | None]]

        def tab_role(self, index: int) -> str: ...
        def new_terminal_pane(
            self, plan: TerminalPanePlan, *, profile: Profile | None = None, autostart: bool = True,
        ) -> TerminalPane: ...
        def set_literal_tab_tooltip(self, index: int, text: object, *, update_base: bool = True) -> None: ...
        def base_tab_tooltip(self, index: int) -> str: ...
        def set_workspace_tab_index(self, index: int) -> None: ...
        def refresh_moba_left_dock_for_current_tab(self) -> None: ...
        def update_session_status(self) -> None: ...
        def start_terminal_pane_when_active(self, pane: TerminalPane, index: int) -> None: ...
        def current_design_id(self) -> str: ...
        def apply_interaction_state_tab_status(self, preset: GuiDesignPreset, state: GuiInteractionState) -> None: ...
        def refresh_special_tab_buttons(self) -> None: ...
        def active_terminal_pane(self) -> TerminalPane | None: ...
        def add_workspace_tab(self, widget: QWidget, title: str, *, select: bool = True, role: str = "session") -> int: ...
        def count_closeable_tabs(self, *, except_index: int | None = None) -> int: ...
        def open_local_terminal_tab(self) -> None: ...
        def moba_connected_state_in_widget(self, widget: QWidget | None) -> MobaConnectedSessionState | None: ...
        def open_moba_connected_session_tab(
            self, profile: Profile, plan: TerminalPanePlan, *, remote_path: str = "/",
            tab_title: str | None = None, tab_status: str | None = None,
        ) -> ConnectedSessionPanel: ...
        def open_terminal_tab(
            self, plan: TerminalPanePlan, *, profile: Profile | None = None,
            tab_title: str | None = None, tab_status: str | None = None,
        ) -> None: ...
        def bind_cloned_layout_persistence(self, root: QWidget) -> None: ...
        def close_tab(self, index: int) -> None: ...
        def current_design_is_moba(self) -> bool: ...
        def moba_connected_profile_supported(self, profile: Profile) -> bool: ...
        def moba_connected_remote_path_for_profile(self, profile: Profile) -> str: ...
        def profile_tab_label(self, profile: Profile) -> str: ...
        def statusBar(self) -> QStatusBar: ...

    def add_split(self, direction: str) -> None:
        orientation = (
            Qt.Orientation.Horizontal if direction == "horizontal" else Qt.Orientation.Vertical
        )
        current = self.tabs.currentWidget()
        current_index = self.tabs.currentIndex()
        current_role = self.tab_role(current_index)
        label = "Split H" if direction == "horizontal" else "Split V"

        if isinstance(current, self._connected_session_panel_type) and current_role == "terminal":
            source_pane = current.terminal_pane
            plan = source_pane.plan
            profile = source_pane.profile
            pane = self.new_terminal_pane(
                plan,
                profile=profile,
                autostart=False,
            )
            current.add_terminal_split(pane, orientation)
            self.remember_terminal_plan(plan, profile=profile)
            self.set_literal_tab_tooltip(
                current_index,
                f"{self.tabs.tabText(current_index)}: {label}, "
                f"{current.terminal_splitter.count()} active panes",
            )
            self.refresh_moba_left_dock_for_current_tab()
            self.update_session_status()
            self.start_terminal_pane_when_active(pane, current_index)
            return

        if (
            isinstance(current, QSplitter)
            and current_role == "split"
            and self.terminal_panes_in(current)
        ):
            current.setOrientation(orientation)
            plan = default_shell_plan()
            pane = self.new_terminal_pane(plan, autostart=False)
            current.addWidget(pane)
            self.remember_terminal_plan(plan)
            self.equalize_ad_hoc_splitter(current)
            self.tabs.setTabText(current_index, f"{label} {current.count()}")
            self.set_literal_tab_tooltip(
                current_index,
                f"{label}: {current.count()} active panes",
            )
            self.update_session_status()
            self.start_terminal_pane_when_active(pane, current_index)
            return

        splitter = QSplitter(orientation)
        if (
            current is not None
            and current_index >= 0
            and (
                isinstance(current, TerminalPane)
                or current_role == "layout"
                or (
                    current_role == "terminal"
                    and bool(self.terminal_panes_in(current))
                )
            )
        ):
            title = self.tabs.tabText(current_index)
            tooltip = self.base_tab_tooltip(current_index) or title
            previous_guard = self.moba_tab_guard
            self.moba_tab_guard = True
            try:
                self.tabs.removeTab(current_index)
                splitter.addWidget(current)
                plan = default_shell_plan()
                pane = self.new_terminal_pane(plan, autostart=False)
                splitter.addWidget(pane)
                self.remember_terminal_plan(plan)
                splitter.setProperty("tabRole", "split")
                new_index = self.tabs.insertTab(
                    current_index,
                    splitter,
                    f"{title} · {label}",
                )
                self.set_literal_tab_tooltip(new_index, f"{tooltip} · {label}")
                self.set_workspace_tab_index(new_index)
            finally:
                self.moba_tab_guard = previous_guard
            preset = get_gui_design_preset(self.current_design_id())
            self.apply_interaction_state_tab_status(
                preset,
                gui_design_interaction_state(preset.id),
            )
            self.equalize_ad_hoc_splitter(splitter)
            self.refresh_special_tab_buttons()
            self.refresh_moba_left_dock_for_current_tab()
            self.update_session_status()
            self.start_terminal_pane_when_active(pane, new_index)
            return

        active = self.active_terminal_pane()
        sessions = (
            [(active.plan, active.profile), (default_shell_plan(), None)]
            if active is not None
            else [(plan, None) for plan in split_shell_plans(2)]
        )
        new_panes: list[TerminalPane] = []
        for plan, profile in sessions:
            pane = self.new_terminal_pane(
                plan,
                profile=profile,
                autostart=False,
            )
            splitter.addWidget(pane)
            new_panes.append(pane)
            self.remember_terminal_plan(plan, profile=profile)
        new_index = self.add_workspace_tab(
            splitter, f"{label} {self.count_closeable_tabs() + 1}", role="split"
        )
        self.equalize_ad_hoc_splitter(splitter)
        self.update_session_status()
        for pane in new_panes:
            self.start_terminal_pane_when_active(pane, new_index)

    @staticmethod
    def equalize_ad_hoc_splitter(splitter: QSplitter) -> None:
        splitter.setChildrenCollapsible(False)
        for index in range(splitter.count()):
            child = _required_gui_value(
                splitter.widget(index),
                "ad-hoc splitter child",
            )
            child.show()
            splitter.setCollapsible(index, False)
            splitter.setStretchFactor(index, 1)
        splitter.setSizes([1000] * splitter.count())

    def remember_terminal_plan(
        self,
        plan: TerminalPanePlan,
        *,
        profile: Profile | None = None,
    ) -> None:
        self.recent_terminal_plans.append((plan, profile))
        self.recent_terminal_plans = self.recent_terminal_plans[-8:]

    def duplicate_current_tab(self) -> None:
        index = self.tabs.currentIndex()
        if index < 0 or self.tab_role(index) in {"home", "new-session"}:
            self.open_local_terminal_tab()
            return
        widget = self.tabs.widget(index)
        title = self.tabs.tabText(index)
        if isinstance(widget, self._connected_session_panel_type):
            state = self.moba_connected_state_in_widget(widget)
            source_panes = self.terminal_panes_in(widget)
            if state is not None and source_panes and source_panes[0].profile is not None:
                duplicate = self.open_moba_connected_session_tab(
                    source_panes[0].profile,
                    source_panes[0].plan,
                    remote_path=state.remote_path,
                    tab_title=f"{title} copy",
                    tab_status="duplicated",
                )
                orientation = widget.terminal_splitter.orientation()
                for source_pane in source_panes[1:]:
                    duplicate_pane = self.new_terminal_pane(
                        source_pane.plan,
                        profile=source_pane.profile,
                        autostart=False,
                    )
                    duplicate.add_terminal_split(
                        duplicate_pane,
                        orientation,
                    )
                    self.remember_terminal_plan(
                        source_pane.plan,
                        profile=source_pane.profile,
                    )
                duplicate_index = self.tabs.indexOf(duplicate)
                for duplicate_pane in self.terminal_panes_in(duplicate):
                    self.start_terminal_pane_when_active(
                        duplicate_pane,
                        duplicate_index,
                    )
                source_sizes = [max(1, int(size)) for size in widget.terminal_splitter.sizes()]
                duplicate.terminal_splitter.setSizes(source_sizes)
                self.log.append(f"TAB DUPLICATED: {title}")
                return
        if isinstance(widget, TerminalPane):
            self.open_terminal_tab(
                widget.plan,
                profile=widget.profile,
                tab_title=f"{title} copy",
                tab_status="duplicated",
            )
            self.log.append(f"TAB DUPLICATED: {title}")
            return
        panes = self.terminal_panes_in(widget) if widget is not None else []
        if not panes:
            self.open_local_terminal_tab()
            return
        if isinstance(widget, QSplitter) and self.terminal_splitter_clone_supported(widget):
            splitter = self.clone_terminal_splitter(widget)
        else:
            splitter = QSplitter(Qt.Orientation.Horizontal)
            for pane in panes:
                splitter.addWidget(
                    self.new_terminal_pane(
                        pane.plan,
                        profile=pane.profile,
                        autostart=False,
                    )
                )
                self.remember_terminal_plan(pane.plan, profile=pane.profile)
            self.equalize_ad_hoc_splitter(splitter)
        source_role = self.tab_role(index)
        duplicate_role = source_role if source_role in {"layout", "split"} else "split"
        duplicate_index = self.add_workspace_tab(
            splitter,
            f"{title} copy",
            role=duplicate_role,
        )
        self.bind_cloned_layout_persistence(splitter)
        self.log.append(f"TAB DUPLICATED: {title}")
        self.update_session_status()
        for duplicate_pane in self.terminal_panes_in(splitter):
            self.start_terminal_pane_when_active(duplicate_pane, duplicate_index)

    def terminal_splitter_clone_supported(self, source: QSplitter) -> bool:
        for index in range(source.count()):
            child = source.widget(index)
            if isinstance(child, TerminalPane):
                continue
            if isinstance(child, QSplitter) and self.terminal_splitter_clone_supported(
                child
            ):
                continue
            return False
        return True

    def clone_terminal_splitter(self, source: QSplitter) -> QSplitter:
        clone = QSplitter(source.orientation())
        clone.setChildrenCollapsible(False)
        saved_layout_name = source.property("savedLayoutName")
        if isinstance(saved_layout_name, str) and saved_layout_name:
            clone.setProperty("savedLayoutName", saved_layout_name)
        for index in range(source.count()):
            child = source.widget(index)
            duplicate: QWidget
            if isinstance(child, TerminalPane):
                duplicate = self.new_terminal_pane(
                    child.plan,
                    profile=child.profile,
                    autostart=False,
                )
                self.remember_terminal_plan(child.plan, profile=child.profile)
            elif isinstance(child, QSplitter):
                duplicate = self.clone_terminal_splitter(child)
            else:
                raise RuntimeError(
                    "cannot duplicate split tab with unsupported child: "
                    f"{type(child).__name__}"
                )
            clone.addWidget(duplicate)
            clone.setCollapsible(index, False)
            clone.setStretchFactor(index, 1)
        sizes = [max(1, int(size)) for size in source.sizes()]
        clone.setSizes(sizes)
        return clone

    def close_current_tab(self) -> None:
        index = self.tabs.currentIndex()
        if index >= 0:
            self.close_tab(index)

    def activate_previous_tab(self) -> None:
        self.activate_adjacent_tab(-1)

    def activate_next_tab(self) -> None:
        self.activate_adjacent_tab(1)

    def activate_adjacent_tab(self, step: int) -> None:
        count = self.tabs.count()
        if count <= 1:
            return
        current = self.tabs.currentIndex()
        for offset in range(1, count + 1):
            index = (current + step * offset) % count
            if self.tab_role(index) not in {"home", "new-session"}:
                self.set_workspace_tab_index(index)
                return

    def close_other_tabs(self, keep_index: int) -> None:
        for index in range(self.tabs.count() - 1, -1, -1):
            if index == keep_index or self.tab_role(index) in {"home", "new-session"}:
                continue
            self.close_tab(index)

    def recover_previous_sessions(self) -> None:
        if not self.recent_terminal_plans:
            self.log.append("RECOVER: no saved live session state")
            self.statusBar().showMessage("No previous session state to recover")
            return
        sessions = list(self.recent_terminal_plans[-3:])
        for plan, profile in sessions:
            if (
                self.current_design_is_moba()
                and profile is not None
                and self.moba_connected_profile_supported(profile)
            ):
                self.open_moba_connected_session_tab(
                    profile,
                    plan,
                    remote_path=self.moba_connected_remote_path_for_profile(profile),
                    tab_title=self.profile_tab_label(profile),
                    tab_status="recovered",
                )
            else:
                is_profile_terminal = (
                    profile is not None
                    and plan.source == f"profile:{profile.name}"
                )
                self.open_terminal_tab(
                    plan,
                    profile=profile,
                    tab_title=(
                        self.profile_tab_label(profile)
                        if profile is not None and is_profile_terminal
                        else plan.title
                    ),
                    tab_status="recovered",
                )
        self.log.append(f"RECOVERED: {len(sessions)} recent session pane(s)")


    def terminal_panes_in(self, widget: QWidget) -> list[TerminalPane]:
        panes: list[TerminalPane] = []
        if isinstance(widget, TerminalPane):
            panes.append(widget)
        panes.extend(widget.findChildren(TerminalPane))
        return panes

    def all_terminal_panes(self) -> list[TerminalPane]:
        panes: list[TerminalPane] = []
        seen: set[int] = set()
        try:
            for index in range(self.tabs.count()):
                widget = self.tabs.widget(index)
                if widget is None:
                    continue
                for pane in self.terminal_panes_in(widget):
                    key = id(pane)
                    if key in seen:
                        continue
                    seen.add(key)
                    panes.append(pane)
        except RuntimeError:
            # A QProcess may emit finished while Qt is deleting the main window's tabs.
            return []
        return panes

    def running_terminal_panes(self) -> list[TerminalPane]:
        return [pane for pane in self.all_terminal_panes() if pane.is_running()]

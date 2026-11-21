from __future__ import annotations

from typing import TYPE_CHECKING, cast

from PyQt6.QtCore import QSize, QTimer
from PyQt6.QtGui import QAction
from PyQt6.QtWidgets import QMenu, QSizePolicy, QSplitter, QTabBar, QTabWidget, QWidget

from . import gui_preset_properties
from .gui_designs import (
    PRODUCT_REFERENCE_TAB_PRESET_IDS,
    get_gui_design_preset,
    gui_design_home_tab_label,
    gui_design_interaction_state,
    gui_design_preset_reference_session_action_route,
)
from .gui_values import _required_gui_value, _safe_tooltip_html
from .gui_workspace import MobaWorkspaceTabBar
from .moba_connected import (
    moba_connected_session_action_route,
    moba_connected_tab_chrome_geometry_for,
    moba_connected_tab_chrome_geometry_items,
)

if TYPE_CHECKING:
    from PyQt6.QtCore import QPoint
    from PyQt6.QtGui import QIcon
    from PyQt6.QtWidgets import QComboBox

    from .gui_designs import GuiDesignPreset, GuiInteractionState
    from .gui_terminal import TerminalPane
    from .moba_connected import MobaConnectedSessionState


class WorkspaceTabs:
    """Workspace page selection, terminal transitions, and tab context menus."""

    if TYPE_CHECKING:
        tabs: QTabWidget
        design_select: QComboBox
        moba_tab_bar: MobaWorkspaceTabBar
        moba_tab_guard: bool
        _tab_transition_generation: int
        _tab_prepaint_guard_generation: int

        def current_design_id(self) -> str: ...
        def add_welcome_tab(self, *, select: bool | None = None) -> None: ...
        def open_local_terminal_tab(self) -> None: ...
        def moba_ribbon_icon(self, icon_key: str, fill: str, *, size: int = 32) -> QIcon: ...
        def active_terminal_pane(self) -> TerminalPane | None: ...
        def all_terminal_panes(self) -> list[TerminalPane]: ...
        def terminal_panes_in(self, widget: QWidget) -> list[TerminalPane]: ...
        def configure_product_connected_chrome(self) -> None: ...
        def refresh_moba_left_dock_for_current_tab(self) -> None: ...
        def apply_interaction_state_tab_status(self, preset: GuiDesignPreset, state: GuiInteractionState) -> None: ...
        def add_split(self, direction: str) -> None: ...
        def duplicate_current_tab(self) -> None: ...
        def open_moba_sftp_same_parameters(self, index: int | None = None) -> None: ...
        def close_current_tab(self) -> None: ...
        def close_other_tabs(self, keep_index: int) -> None: ...
        def recover_previous_sessions(self) -> None: ...

        @staticmethod
        def moba_connected_state_in_widget(widget: QWidget | None) -> MobaConnectedSessionState | None: ...

    def tab_position_for_design(self, value: str):
        if value == "west":
            return QTabWidget.TabPosition.West
        if value == "south":
            return QTabWidget.TabPosition.South
        if value == "east":
            return QTabWidget.TabPosition.East
        return QTabWidget.TabPosition.North

    def configure_workspace_tabs_for_design(self, is_moba: bool) -> None:
        tab_bar = self.moba_tab_bar
        tab_bar.setProperty("mobaCompactTabWidths", bool(is_moba))
        tab_bar.setProperty(
            "mobaCompactTabWidthSource",
            "moba-connected-tab-chrome" if is_moba else "",
        )
        tab_bar.updateGeometry()
        previous_guard = self.moba_tab_guard
        self.moba_tab_guard = True
        try:
            home_index = self.find_tab_by_role("home")
            home_label = gui_design_home_tab_label(self.current_design_id())
            if home_index >= 0:
                was_current = self.tabs.currentIndex() == home_index
                home_widget = self.tabs.widget(home_index)
                home_widget_preset = (
                    str(home_widget.property("designPreset") or "")
                    if home_widget is not None
                    else ""
                )
                if home_widget_preset != self.current_design_id():
                    self.rebuild_welcome_tab(select=was_current)
            elif is_moba or self.tabs.count() == 0:
                self.add_welcome_tab(select=self.tabs.count() == 0)
            home_index = self.find_tab_by_role("home")
            if home_index >= 0:
                self.tabs.setTabText(home_index, home_label)
                self.set_literal_tab_tooltip(
                    home_index, f"{home_label}: {self.current_design_id()} preset home tab"
                )
                if is_moba:
                    self.apply_moba_tab_chrome(
                        home_index,
                        key="home",
                        icon_key="home",
                        tooltip="Home",
                        closeable=False,
                    )
            if is_moba:
                self.ensure_new_session_tab()
            else:
                self.remove_new_session_tab()
            self.refresh_special_tab_buttons()
        finally:
            self.moba_tab_guard = previous_guard
        self.refresh_moba_left_dock_for_current_tab()

    def rebuild_welcome_tab(self, *, select: bool) -> None:
        home_index = self.find_tab_by_role("home")
        if home_index < 0:
            self.add_welcome_tab(select=select)
            return
        widget = self.tabs.widget(home_index)
        self.tabs.removeTab(home_index)
        if widget is not None:
            self.clear_deleted_tab_object_names(widget)
            widget.deleteLater()
        self.add_welcome_tab(select=select)

    @staticmethod
    def clear_deleted_tab_object_names(widget: QWidget) -> None:
        widget.setObjectName("")
        for child in widget.findChildren(QWidget):
            child.setObjectName("")

    def current_design_is_moba(self) -> bool:
        return (self.design_select.currentData() or "native") == "mobaxterm"

    def tab_role(self, index: int) -> str:
        widget = self.tabs.widget(index)
        if widget is None:
            return ""
        return str(widget.property("tabRole") or "session")

    def find_tab_by_role(self, role: str) -> int:
        for index in range(self.tabs.count()):
            if self.tab_role(index) == role:
                return index
        return -1

    def find_tab_by_label(self, label: str) -> int:
        for index in range(self.tabs.count()):
            if self.tabs.tabText(index) == label:
                return index
        return -1

    def set_workspace_tab_index(self, index: int) -> None:
        """Select a workspace page only after arming the paint guard."""

        if index < 0 or index >= self.tabs.count():
            return
        if index != self.tabs.currentIndex():
            self.prepare_tab_transition(index)
        self.tabs.setCurrentIndex(index)

    def add_workspace_tab(self, widget: QWidget, title: str, *, select: bool = True, role: str = "session") -> int:
        widget.setProperty("tabRole", role)
        if role in {"terminal", "split"}:
            # Keep the page root independent of its content size hint.
            # This matters for a newly inserted Moba wrapper: until its
            # first layout pass, a preferred-size child can otherwise
            # flash at its minimum geometry during tab activation.
            widget.setMinimumSize(0, 0)
            widget.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding,
            )
        new_index = self.find_tab_by_role("new-session")
        self.tabs.setUpdatesEnabled(False)
        try:
            if new_index >= 0:
                index = self.tabs.insertTab(new_index, widget, title)
            else:
                index = self.tabs.addTab(widget, title)
            self.set_literal_tab_tooltip(index, title)
            if select:
                self.set_workspace_tab_index(index)
        finally:
            # A selected tab may have emitted currentChanged above and
            # entered the guarded transition.  Keep the tab widget
            # frozen until finish_tab_transition applies final geometry;
            # otherwise the insert helper would immediately re-enable the
            # very intermediate paint we are suppressing.
            if not bool(self.tabs.property("terminalTabTransitionActive")):
                self.tabs.setUpdatesEnabled(True)
        self.refresh_special_tab_buttons()
        return index

    def set_literal_tab_tooltip(
        self,
        index: int,
        text: object,
        *,
        update_base: bool = True,
    ) -> None:
        plain_text = str(text)
        widget = self.tabs.widget(index)
        if widget is not None:
            widget.setProperty("tabTooltipPlainText", plain_text)
            if update_base:
                widget.setProperty("tabTooltipBaseText", plain_text)
        self.tabs.setTabToolTip(index, _safe_tooltip_html(plain_text))

    def literal_tab_tooltip(self, index: int) -> str:
        widget = self.tabs.widget(index)
        if widget is not None:
            value = widget.property("tabTooltipPlainText")
            if isinstance(value, str):
                return value
        return self.tabs.tabText(index)

    def base_tab_tooltip(self, index: int) -> str:
        widget = self.tabs.widget(index)
        if widget is not None:
            value = widget.property("tabTooltipBaseText")
            if isinstance(value, str):
                return value
        return self.tabs.tabText(index)

    def ensure_new_session_tab(self) -> None:
        if self.find_tab_by_role("new-session") >= 0:
            self.refresh_special_tab_buttons()
            return
        new_tab = QWidget()
        new_tab.setObjectName("newSessionTab")
        index = self.add_workspace_tab(new_tab, "+", select=False, role="new-session")
        self.apply_moba_tab_chrome(
            index,
            key="new-session",
            icon_key="plus",
            tooltip="Open a new local terminal",
            closeable=False,
        )

    def activate_moba_special_tab(self, _index: int) -> None:
        """Treat the plus chrome as an action without selecting its placeholder page."""

        if self.moba_tab_guard or not self.current_design_is_moba():
            return
        self.moba_tab_guard = True
        try:
            self.open_local_terminal_tab()
        finally:
            self.moba_tab_guard = False

    def remove_new_session_tab(self) -> None:
        index = self.find_tab_by_role("new-session")
        if index < 0:
            return
        widget = _required_gui_value(
            self.tabs.widget(index),
            "new-session tab widget",
        )
        self.tabs.removeTab(index)
        self.clear_deleted_tab_object_names(widget)
        widget.deleteLater()

    def refresh_special_tab_buttons(self) -> None:
        tab_bar = self.moba_tab_bar
        for role in ["home", "new-session"]:
            index = self.find_tab_by_role(role)
            if index < 0:
                continue
            self.tabs.setTabText(index, "+" if role == "new-session" else self.tabs.tabText(index))
            for position in [QTabBar.ButtonPosition.LeftSide, QTabBar.ButtonPosition.RightSide]:
                tab_bar.setTabButton(index, position, None)
        new_index = self.find_tab_by_role("new-session")
        if new_index >= 0 and new_index != self.tabs.count() - 1:
            widget = _required_gui_value(
                self.tabs.widget(new_index),
                "new-session tab widget",
            )
            self.tabs.removeTab(new_index)
            self.tabs.addTab(widget, "+")
            self.set_literal_tab_tooltip(
                self.tabs.count() - 1,
                "Open a new local terminal",
            )
        new_index = self.find_tab_by_role("new-session")
        if new_index >= 0:
            self.apply_moba_tab_chrome(
                new_index,
                key="new-session",
                icon_key="plus",
                tooltip="Open a new local terminal",
                closeable=False,
            )
            for position in [QTabBar.ButtonPosition.LeftSide, QTabBar.ButtonPosition.RightSide]:
                tab_bar.setTabButton(new_index, position, None)
        tab_bar.stabilize_special_tabs()

    def apply_moba_tab_chrome(
        self,
        index: int,
        *,
        key: str,
        icon_key: str,
        tooltip: str,
        closeable: bool,
    ) -> None:
        if index < 0:
            return
        widget = _required_gui_value(
            self.tabs.widget(index),
            "Moba workspace tab widget",
        )
        geometry = moba_connected_tab_chrome_geometry_for(key)
        tab_bar = self.moba_tab_bar
        previous_data = tab_bar.tabData(index)
        custom_width = (
            previous_data.get("moba_width")
            if isinstance(previous_data, dict)
            and previous_data.get("moba_user_width") is True
            else None
        )
        width = (
            max(
                MobaWorkspaceTabBar.TAB_RESIZE_MIN_WIDTH,
                min(MobaWorkspaceTabBar.TAB_RESIZE_MAX_WIDTH, int(custom_width)),
            )
            if isinstance(custom_width, int)
            and key not in {"home", "new-session"}
            else geometry.width
        )
        tab_bar.setTabData(
            index,
            {
                "moba_key": key,
                "moba_width": width,
                "moba_height": geometry.height,
                "moba_user_width": width != geometry.width,
            },
        )
        tab_bar.setProperty("mobaCompactTabWidths", True)
        tab_bar._refresh_tab_layout(index)
        self.tabs.setProperty(
            "mobaTabChromeGeometryKeys",
            [item.key for item in moba_connected_tab_chrome_geometry_items()],
        )
        widget.setProperty("mobaTabChromeKey", key)
        widget.setProperty("mobaTabIconKey", icon_key)
        widget.setProperty("mobaTabCloseable", closeable)
        widget.setProperty("mobaTabStaticWidth", width)
        widget.setProperty("mobaTabUserWidth", width != geometry.width)
        widget.setProperty(
            "mobaTabResizeRange",
            [
                MobaWorkspaceTabBar.TAB_RESIZE_MIN_WIDTH,
                MobaWorkspaceTabBar.TAB_RESIZE_MAX_WIDTH,
            ],
        )
        widget.setProperty("mobaTabStaticHeight", geometry.height)
        widget.setProperty("mobaTabCornerRadius", geometry.corner_radius)
        widget.setProperty("mobaTabIconX", geometry.icon_x)
        widget.setProperty("mobaTabIconY", geometry.icon_y)
        widget.setProperty("mobaTabIconSize", geometry.icon_size)
        widget.setProperty("mobaTabLabelX", geometry.label_x)
        widget.setProperty("mobaTabLabelY", geometry.label_y)
        widget.setProperty("mobaTabCloseRightOffset", geometry.close_right_offset)
        widget.setProperty("mobaTabCloseY", geometry.close_y)
        widget.setProperty("mobaTabPlusX", geometry.plus_x)
        widget.setProperty("mobaTabPlusY", geometry.plus_y)
        widget.setProperty("mobaTabGapAfter", geometry.gap_after)
        self.tabs.setIconSize(QSize(16, 16))
        self.tabs.setTabIcon(index, self.moba_ribbon_icon(icon_key, "#d6a72d", size=18))
        self.set_literal_tab_tooltip(index, tooltip)
        if not closeable:
            for position in [QTabBar.ButtonPosition.LeftSide, QTabBar.ButtonPosition.RightSide]:
                tab_bar.setTabButton(index, position, None)
        tab_bar.updateGeometry()

    def set_terminal_tab_paint_frozen(self, frozen: bool) -> None:
        """Freeze every embedded terminal while a workspace page changes."""

        frozen = bool(frozen)
        self.tabs.setProperty("terminalTabPaintFrozen", frozen)
        for pane in self.all_terminal_panes():
            pane.set_terminal_paint_frozen(frozen)

    def prepare_tab_transition(self, index: int) -> None:
        """Freeze terminal painting before Qt activates a different page."""

        if index >= 0 and index == self.tabs.currentIndex():
            return
        if bool(self.tabs.property("terminalTabTransitionActive")):
            return
        if bool(self.tabs.property("terminalTabPrepaintGuardActive")):
            return
        self._tab_prepaint_guard_generation += 1
        generation = self._tab_prepaint_guard_generation
        current_index = self.tabs.currentIndex()
        self.tabs.setProperty("terminalTabPrepaintGuardActive", True)
        self.tabs.setProperty("terminalTabPrepaintTargetIndex", index)
        self.set_terminal_tab_paint_frozen(True)
        self.tabs.setUpdatesEnabled(False)
        # A click on a disabled/current tab or an intercepted keyboard
        # navigation event may not produce currentChanged.  Release that
        # speculative guard on the next event-loop turn.
        QTimer.singleShot(
            0,
            lambda generation=generation, current_index=current_index: (
                self.release_tab_prepaint_guard_if_idle(
                    generation,
                    current_index,
                )
            ),
        )

    def release_tab_prepaint_guard_if_idle(
        self,
        generation: int,
        previous_index: int,
    ) -> None:
        if generation != self._tab_prepaint_guard_generation:
            return
        if bool(self.tabs.property("terminalTabTransitionActive")):
            return
        self.tabs.setProperty(
            "terminalTabPrepaintGuardRecoveredWithoutTransition",
            self.tabs.currentIndex() != previous_index,
        )
        self.tabs.setUpdatesEnabled(True)
        # The terminal output can be nested under this tab widget. Enable
        # the ancestor before flushing a deferred transcript; otherwise
        # QTextEdit observes effective updates as disabled and preserves
        # that state after the tab is shown, leaving a black page behind.
        self.set_terminal_tab_paint_frozen(False)
        self.tabs.setProperty("terminalTabPrepaintGuardActive", False)
        self.tabs.setProperty("terminalTabPrepaintTargetIndex", -1)

    def handle_tab_changed(self, index: int) -> None:
        self._tab_transition_generation += 1
        transition = self._tab_transition_generation
        self.tabs.setProperty("terminalTabTransitionGeneration", transition)
        self.tabs.setProperty("terminalTabTransitionActive", True)
        # QTabWidget can paint the page once before its new splitter/layout
        # geometry is settled.  Suppress that one intermediate frame so a
        # tiny, unconfigured terminal surface cannot flash in the middle
        # of the workspace during a tab switch.
        self.set_terminal_tab_paint_frozen(True)
        self.tabs.setUpdatesEnabled(False)
        if self.moba_tab_guard or index < 0:
            self.configure_product_connected_chrome()
            self.refresh_moba_left_dock_for_current_tab()
            self.set_terminal_tab_paint_frozen(False)
            self.tabs.setUpdatesEnabled(True)
            self.tabs.setProperty("terminalTabTransitionActive", False)
            self.tabs.setProperty("terminalTabPrepaintGuardActive", False)
            self.tabs.setProperty("terminalTabPrepaintTargetIndex", -1)
            return
        # QTabWidget may finish laying out the newly selected page after
        # emitting currentChanged.  Re-apply once the splitter has its
        # final geometry so the activity pane and side chrome cannot stay
        # collapsed after returning from a connected Termius document.
        QTimer.singleShot(
            0,
            lambda transition=transition: self.finish_tab_transition(transition),
        )
        # A newly inserted pane deliberately waits for its first selected
        # layout before starting.  If the user changes tabs in the same
        # event-loop turn, the original one-shot sees the pane as hidden;
        # retry when its tab becomes active instead of leaving it stopped.
        pane = self.active_terminal_pane()
        if (
            pane is not None
            and bool(pane.property("terminalStartDeferredUntilTabReady"))
        ):
            QTimer.singleShot(
                0,
                lambda pane=pane, transition=transition, index=index: (
                    self.start_deferred_terminal_pane_if_current(
                        pane,
                        index,
                        transition,
                    )
                ),
            )
        if self.tab_role(index) != "new-session":
            preset = get_gui_design_preset(self.current_design_id())
            self.apply_interaction_state_tab_status(
                preset,
                gui_design_interaction_state(preset.id),
            )
            pane = self.active_terminal_pane()
            if pane is not None:
                def focus_if_current(pane=pane, transition=transition) -> None:
                    if transition != self._tab_transition_generation:
                        return
                    current = self.tabs.currentWidget()
                    if current is not None and (current is pane or current.isAncestorOf(pane)):
                        pane.focus_terminal_input()

                QTimer.singleShot(0, focus_if_current)
            return
        self.moba_tab_guard = True
        try:
            self.open_local_terminal_tab()
        finally:
            self.moba_tab_guard = False
        self.refresh_moba_left_dock_for_current_tab()

    def finish_tab_transition(self, transition: int) -> None:
        """Apply deferred chrome only for the still-active tab transition."""

        if transition != self._tab_transition_generation:
            return
        self.configure_product_connected_chrome()
        self.refresh_moba_left_dock_for_current_tab()
        current = self.tabs.currentWidget()
        if current is not None:
            # Activate the page and its embedded splitters while paints
            # are still frozen.  Releasing updates before this synchronous
            # layout pass is what allows Qt to expose a one-frame tiny
            # terminal surface on fast tab changes.
            current.setMinimumSize(0, 0)
            current.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding,
            )
            current.updateGeometry()
            current_layout = current.layout()
            if current_layout is not None:
                current_layout.activate()
            layout_widgets: list[QWidget] = []
            if isinstance(current, QSplitter):
                layout_widgets.append(current)
            layout_widgets.extend(current.findChildren(QSplitter))
            layout_widgets.extend(self.terminal_panes_in(current))
            seen_layout_widgets: set[int] = set()
            for child in layout_widgets:
                identity = id(child)
                if identity in seen_layout_widgets:
                    continue
                seen_layout_widgets.add(identity)
                child_layout = child.layout()
                if child_layout is not None:
                    child_layout.activate()
                child.updateGeometry()
        tabs_layout = self.tabs.layout()
        if tabs_layout is not None:
            tabs_layout.activate()
        self.tabs.updateGeometry()
        self.tabs.setProperty(
            "terminalTabGeometryStabilized",
            bool(
                current is not None
                and current.width() > 0
                and current.height() > 0
            ),
        )
        self.tabs.setUpdatesEnabled(True)
        # The terminal output can be nested under this tab widget. Enable
        # the ancestor before flushing a deferred transcript; otherwise
        # QTextEdit observes effective updates as disabled and preserves
        # that state after the tab is shown, leaving a black page behind.
        self.set_terminal_tab_paint_frozen(False)
        if current is not None:
            current.update()
        self.tabs.setProperty("terminalTabTransitionActive", False)
        self.tabs.setProperty("terminalTabPrepaintGuardActive", False)
        self.tabs.setProperty("terminalTabPrepaintTargetIndex", -1)
        if current is not None:
            # Native Windows can expose the newly selected page before a
            # queued update reaches QTextEdit's viewport. Present the
            # already-rendered frame synchronously at this boundary so a
            # programmatic tab switch never leaves a black page visible.
            current.repaint()

    def start_deferred_terminal_pane_if_current(
        self,
        pane: TerminalPane,
        index: int,
        transition: int | None = None,
    ) -> None:
        """Start a pane once its selected page has stable geometry."""

        if transition is not None and transition != self._tab_transition_generation:
            return
        if pane.property("terminalClosing") or pane.is_running():
            return
        if index < 0 or self.tabs.currentIndex() != index:
            return
        current = self.tabs.currentWidget()
        if current is None or not (current is pane or current.isAncestorOf(pane)):
            return
        # A newly selected page can still be inside the one-event-turn
        # transition guard even when it already has its final tab index.
        # Defer the child launch until that guard releases so ConPTY (or
        # the hidden pipe fallback) never paints a transient tiny surface.
        if (
            bool(cast(QWidget, self).property("designTransitionActive"))
            or bool(self.tabs.property("terminalTabTransitionActive"))
            or bool(self.tabs.property("terminalTabPrepaintGuardActive"))
        ):
            QTimer.singleShot(
                0,
                lambda pane=pane, index=index, transition=transition: (
                    self.start_deferred_terminal_pane_if_current(
                        pane,
                        index,
                        transition,
                    )
                ),
            )
            return
        pane.start()
        pane.setProperty("terminalStartDeferredUntilTabReady", False)

    def tab_context_session_action_specs(self, index: int) -> list[dict[str, object]]:
        role = self.tab_role(index)
        is_closeable_session = role not in {"home", "new-session"}
        specs = [
            {"key": "new-local-terminal", "label": "New local terminal", "enabled": True},
            {"key": "split-horizontal", "label": "Split horizontal", "enabled": True},
            {"key": "split-vertical", "label": "Split vertical", "enabled": True},
            {"key": "duplicate-tab", "label": "Duplicate tab", "enabled": is_closeable_session},
            {"key": "close-tab", "label": "Close tab", "enabled": is_closeable_session},
            {
                "key": "close-other-tabs",
                "label": "Close other tabs",
                "enabled": self.count_closeable_tabs(except_index=index) > 0,
            },
            {"key": "recover-previous-sessions", "label": "Recover previous sessions", "enabled": True},
        ]
        if self.moba_connected_session_action_route_for_tab(index) is not None:
            specs.insert(
                4,
                {
                    "key": "open-sftp-same-parameters",
                    "label": "Open SFTP with same parameters",
                    "enabled": True,
                },
            )
        return specs

    def reference_session_action_route_for_tab(self, index: int):
        preset_id = self.current_design_id()
        if preset_id not in PRODUCT_REFERENCE_TAB_PRESET_IDS or index < 0 or not cast(QWidget, self).property("guiPreviewSamples"):
            return None
        route = gui_design_preset_reference_session_action_route(preset_id)
        if self.tabs.tabText(index) != route.active_tab_label:
            return None
        if self.tab_role(index) != route.reference_tab_role:
            return None
        return route

    def moba_connected_session_action_route_for_tab(self, index: int):
        if not self.current_design_is_moba() or index < 0:
            return None
        widget = self.tabs.widget(index)
        state = self.moba_connected_state_in_widget(widget)
        if state is None:
            return None
        route = moba_connected_session_action_route(state)
        role = self.tab_role(index)
        if role not in {route.reference_tab_role, "split"}:
            return None
        return route

    def session_action_route_for_tab(self, index: int):
        return self.moba_connected_session_action_route_for_tab(index) or self.reference_session_action_route_for_tab(
            index
        )

    @staticmethod
    def session_action_capture_from_specs(
        specs: list[dict[str, object]],
    ) -> tuple[list[str], list[str], list[str], list[str]]:
        action_keys = [str(spec["key"]) for spec in specs]
        action_labels = [str(spec["label"]) for spec in specs]
        enabled_keys = [str(spec["key"]) for spec in specs if bool(spec["enabled"])]
        disabled_keys = [str(spec["key"]) for spec in specs if not bool(spec["enabled"])]
        return action_keys, action_labels, enabled_keys, disabled_keys

    def apply_session_action_spec_properties(self, action, spec: dict[str, object], route) -> None:
        action.setObjectName(route.action_object if route is not None else "sessionTabContextAction")
        action.setProperty("sessionTabContextActionKey", str(spec["key"]))
        action.setProperty("sessionTabContextActionLabel", str(spec["label"]))
        action.setProperty("sessionTabContextActionEnabled", bool(spec["enabled"]))
        if route is not None:
            if hasattr(route, "profile_name"):
                gui_preset_properties.apply_moba_connected_session_action_route_properties(action, route)
            else:
                gui_preset_properties.apply_preset_reference_session_action_route_properties(action, route)

    @staticmethod
    def session_action_menu_object_name(route) -> str:
        if route is None:
            return "sessionTabContextMenu"
        return str(getattr(route, "menu_object", "presetReferenceSessionTabContextMenu"))

    def apply_session_action_menu_capture(
        self,
        menu,
        route,
        tab_title: str,
        actions: list[QAction],
    ) -> None:
        if route is None:
            return
        if hasattr(route, "profile_name"):
            gui_preset_properties.apply_moba_connected_session_action_route_properties(menu, route)
        else:
            gui_preset_properties.apply_preset_reference_session_action_route_properties(menu, route)
        action_keys = [str(action.property(route.action_key_property) or "") for action in actions]
        action_labels = [str(action.property(route.action_label_property) or "") for action in actions]
        enabled_keys = [
            str(action.property(route.action_key_property) or "")
            for action in actions
            if bool(action.property(route.action_enabled_property))
        ]
        disabled_keys = [
            str(action.property(route.action_key_property) or "")
            for action in actions
            if not bool(action.property(route.action_enabled_property))
        ]
        menu.setProperty(route.captured_property, True)
        menu.setProperty(route.captured_tab_property, tab_title)
        menu.setProperty(route.captured_action_keys_property, action_keys)
        menu.setProperty(route.captured_action_labels_property, action_labels)
        menu.setProperty(route.captured_action_count_property, len(action_keys))
        menu.setProperty(route.captured_enabled_keys_property, enabled_keys)
        menu.setProperty(route.captured_disabled_keys_property, disabled_keys)

    def build_tab_context_menu(self, index: int):
        if index < 0:
            return None
        route = self.session_action_route_for_tab(index)
        specs = {str(spec["key"]): spec for spec in self.tab_context_session_action_specs(index)}
        menu = QMenu(cast(QWidget, self))
        menu.setObjectName(self.session_action_menu_object_name(route))
        context_actions: list[QAction] = []

        def add_context_action(key: str, callback) -> None:
            spec = specs[key]
            action = _required_gui_value(
                menu.addAction(str(spec["label"]), callback),
                f"tab context action for {key}",
            )
            action.setEnabled(bool(spec["enabled"]))
            self.apply_session_action_spec_properties(action, spec, route)
            context_actions.append(action)

        add_context_action("new-local-terminal", self.open_local_terminal_tab)
        add_context_action("split-horizontal", lambda: self.add_split("horizontal"))
        add_context_action("split-vertical", lambda: self.add_split("vertical"))
        menu.addSeparator()
        add_context_action("duplicate-tab", self.duplicate_current_tab)
        if "open-sftp-same-parameters" in specs:
            add_context_action("open-sftp-same-parameters", lambda: self.open_moba_sftp_same_parameters(index))
        add_context_action("close-tab", self.close_current_tab)
        add_context_action("close-other-tabs", lambda: self.close_other_tabs(index))
        menu.addSeparator()
        add_context_action("recover-previous-sessions", self.recover_previous_sessions)
        self.apply_session_action_menu_capture(menu, route, self.tabs.tabText(index), context_actions)
        return menu

    def show_tab_context_menu(self, position: QPoint) -> None:
        index = self.moba_tab_bar.tabAt(position)
        if index < 0:
            return
        if self.tab_role(index) != "new-session":
            self.set_workspace_tab_index(index)
        menu = self.build_tab_context_menu(index)
        if menu is not None:
            try:
                menu.exec(self.moba_tab_bar.mapToGlobal(position))
            finally:
                menu.deleteLater()

    def count_closeable_tabs(self, *, except_index: int | None = None) -> int:
        count = 0
        for index in range(self.tabs.count()):
            if index == except_index:
                continue
            if self.tab_role(index) not in {"home", "new-session"}:
                count += 1
        return count

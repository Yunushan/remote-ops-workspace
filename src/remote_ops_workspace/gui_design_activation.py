from __future__ import annotations

from typing import TYPE_CHECKING, cast

from PyQt6.QtCore import QSize, QTimer
from PyQt6.QtWidgets import QLineEdit, QSizePolicy, QWidget

from . import gui_preset_properties
from .gui_designs import (
    PRODUCT_GUI_PRESET_IDS,
    PRODUCT_REFERENCE_TAB_PRESET_IDS,
    get_gui_design_preset,
    gui_design_interaction_state,
    gui_design_moba_connected_dock_frame,
    gui_design_mremoteng_document_toolbar_chrome,
    gui_design_preset_catalog_route,
    gui_design_preset_command_surface_route,
    gui_design_preset_home_search_route,
    gui_design_preset_isolation_route,
    gui_design_preset_keyboard_shortcut_route,
    gui_design_preset_selection_route,
    gui_design_preset_transition_route,
    gui_design_preset_visual_signature,
    gui_design_securecrt_session_manager_chrome,
)
from .gui_terminal import TerminalPane
from .gui_values import _required_gui_value

if TYPE_CHECKING:
    from PyQt6.QtWidgets import (
        QComboBox,
        QFrame,
        QLabel,
        QSplitter,
        QStatusBar,
        QTabWidget,
        QTextEdit,
        QToolBar,
        QTreeWidget,
    )

    from .gui_designs import (
        GuiDesignPreset,
        GuiInteractionState,
        GuiPresetCommandSurfaceRoute,
        GuiPresetHomeSearchRoute,
        GuiPresetKeyboardShortcutRoute,
    )
    from .gui_workspace import MobaWorkspaceTabBar


class WindowDesign:
    """Apply desktop presets and coordinate paint guards during transitions."""

    if TYPE_CHECKING:
        design_select: QComboBox
        layout_toolbar: QToolBar
        left_panel: QWidget
        left_panel_header: QFrame
        log: QTextEdit
        main_toolbar: QToolBar
        moba_quick_connect_chrome: QFrame
        moba_rail: QWidget
        moba_tab_bar: MobaWorkspaceTabBar
        mremoteng_left_property_grid_panel: QFrame
        profile_list: QTreeWidget
        quick_connect: QLineEdit
        remmina_profile_filter: QLineEdit
        remmina_profile_list_chrome: QFrame
        status_notice_label: QLabel
        status_segment_labels: list[QLabel]
        tabs: QTabWidget
        workspace: QSplitter

        def apply_command_surface_route_for_design(self, route: GuiPresetCommandSurfaceRoute | None) -> None: ...
        def apply_home_search_route_for_design(self, route: GuiPresetHomeSearchRoute | None) -> None: ...
        def apply_interaction_state_tab_status(self, preset: GuiDesignPreset, state: GuiInteractionState) -> None: ...
        def apply_keyboard_shortcut_route_for_design(self, route: GuiPresetKeyboardShortcutRoute | None) -> None: ...
        def apply_moba_top_stack_geometry(self) -> None: ...
        def configure_interaction_states_for_design(self, preset: GuiDesignPreset) -> None: ...
        def configure_left_panel_header_for_design(self, preset: GuiDesignPreset, is_moba: bool) -> None: ...
        def configure_menu_bar_for_design(self, preset: GuiDesignPreset) -> None: ...
        def configure_product_connected_chrome(self) -> None: ...
        def configure_profile_tree_for_design(self, is_moba: bool, list_spacing: int) -> None: ...
        def configure_status_bar_for_design(self, preset: GuiDesignPreset) -> None: ...
        def configure_toolbar_copy_for_design(self, preset: GuiDesignPreset) -> None: ...
        def configure_toolbar_for_design(self, preset: GuiDesignPreset, is_moba: bool, icon_size: int) -> None: ...
        def configure_workspace_tabs_for_design(self, is_moba: bool) -> None: ...
        def filter_remmina_profile_rows(self, text: str) -> None: ...
        def preferred_sidebar_width(self, default_width: int) -> int: ...
        def refresh_moba_left_dock_for_current_tab(self) -> None: ...
        def refresh_profiles(self) -> None: ...
        def set_root_sidebar_width(self, width: int) -> None: ...
        def set_terminal_tab_paint_frozen(self, frozen: bool) -> None: ...
        @staticmethod
        def sidebar_minimum_width_for_design(preset_id: str) -> int: ...
        def statusBar(self) -> QStatusBar: ...  # noqa: N802
        def tab_position_for_design(self, value: str) -> QTabWidget.TabPosition: ...
        def update_layout_action_states(self) -> None: ...
        def update_profile_action_states(self) -> None: ...
        def update_quick_connect_suggestions(self) -> None: ...

    def initialize_design_transition(self) -> None:
        self._design_transition_depth = 0
        self._design_transition_generation = 0
        self._design_transition_restore_window_updates = True
        self._design_transition_restore_tabs_updates = True

    def current_design_id(self) -> str:
        preset_id = str(self.design_select.currentData() or "native")
        try:
            get_gui_design_preset(preset_id)
        except ValueError:
            return "native"
        return preset_id

    def begin_design_transition(self) -> None:
        """Freeze the full chrome while a visual preset is being applied."""

        window = cast(QWidget, self)
        if self._design_transition_depth == 0:
            self._design_transition_generation += 1
            self._design_transition_restore_window_updates = window.updatesEnabled()
            self._design_transition_restore_tabs_updates = self.tabs.updatesEnabled()
            window.setProperty("designTransitionActive", True)
            window.setProperty(
                "designTransitionGeneration",
                self._design_transition_generation,
            )
            window.setUpdatesEnabled(False)
            self.tabs.setUpdatesEnabled(False)
            self.set_terminal_tab_paint_frozen(True)
        self._design_transition_depth += 1

    def finish_design_transition(self) -> None:
        """Restore chrome only after the selected page has stable geometry."""

        window = cast(QWidget, self)
        if self._design_transition_depth <= 0:
            return
        self._design_transition_depth -= 1
        if self._design_transition_depth:
            return
        current = self.tabs.currentWidget()
        if current is not None:
            current.setMinimumSize(0, 0)
            current.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Expanding,
            )
            current.updateGeometry()
            current_layout = current.layout()
            if current_layout is not None:
                current_layout.activate()
        tabs_are_transitioning = bool(
            self.tabs.property("terminalTabTransitionActive")
            or self.tabs.property("terminalTabPrepaintGuardActive")
        )
        if not tabs_are_transitioning:
            self.set_terminal_tab_paint_frozen(False)
        window.setProperty("designTransitionActive", False)
        self.tabs.setUpdatesEnabled(
            self._design_transition_restore_tabs_updates
            and not tabs_are_transitioning
        )
        window.setUpdatesEnabled(self._design_transition_restore_window_updates)
        if current is not None:
            current.update()
            self.tabs.update()

    def apply_selected_design(self, *_args) -> None:
        self.begin_design_transition()
        try:
            self._apply_selected_design(*_args)
        finally:
            self.finish_design_transition()

    def _apply_selected_design(self, *_args) -> None:
        window = cast(QWidget, self)
        preset_id = self.design_select.currentData() or "native"
        try:
            preset = get_gui_design_preset(str(preset_id))
        except ValueError:
            preset = get_gui_design_preset("native")
            native_index = self.design_select.findData(preset.id)
            signals_were_blocked = self.design_select.blockSignals(True)
            try:
                self.design_select.setCurrentIndex(native_index)
            finally:
                self.design_select.blockSignals(signals_were_blocked)
        catalog_route = gui_design_preset_catalog_route()
        isolation_route = gui_design_preset_isolation_route(preset.id)
        selection_route = gui_design_preset_selection_route(preset.id)
        transition_route = gui_design_preset_transition_route(preset.id)
        visual_signature = gui_design_preset_visual_signature(preset.id)
        keyboard_shortcut_route = (
            gui_design_preset_keyboard_shortcut_route(preset.id)
            if preset.id in PRODUCT_GUI_PRESET_IDS
            else None
        )
        command_surface_route = (
            gui_design_preset_command_surface_route(preset.id)
            if preset.id in PRODUCT_GUI_PRESET_IDS
            else None
        )
        home_search_route = (
            gui_design_preset_home_search_route(preset.id)
            if preset.id in PRODUCT_GUI_PRESET_IDS
            else None
        )
        reference_routes = gui_preset_properties.ReferencePresetRoutes.for_preset(preset.id)
        is_moba = preset.id == "mobaxterm"
        self.synchronize_terminal_mouse_paste_policy_for_design(preset.id)
        window.setStyleSheet(preset.stylesheet)
        for catalog_widget in (window, self.design_select, self.main_toolbar):
            gui_preset_properties.apply_preset_catalog_route_properties(catalog_widget, catalog_route)
            gui_preset_properties.apply_preset_isolation_route_properties(
                catalog_widget,
                isolation_route,
            )
            gui_preset_properties.apply_preset_transition_route_properties(
                catalog_widget,
                transition_route,
            )
        self.apply_keyboard_shortcut_route_for_design(keyboard_shortcut_route)
        for reference_widget in (window, self.tabs):
            gui_preset_properties.apply_reference_preset_routes(reference_widget, reference_routes)
        for visual_widget in (
            window,
            self.main_toolbar,
            self.layout_toolbar,
            self.left_panel,
            self.profile_list,
            self.tabs,
            self.log,
            self.statusBar(),
        ):
            gui_preset_properties.apply_preset_visual_signature_properties(
                visual_widget,
                visual_signature,
            )
        gui_preset_properties.apply_preset_selection_route_properties(window, selection_route)
        for selection_widget in (
            self.design_select,
            self.main_toolbar,
            self.layout_toolbar,
            self.left_panel_header,
            self.profile_list,
            self.tabs,
            self.statusBar(),
        ):
            gui_preset_properties.apply_preset_selection_route_properties(
                selection_widget,
                selection_route,
            )
        self.configure_menu_bar_for_design(preset)
        self.moba_quick_connect_chrome.setVisible(is_moba)
        self.quick_connect.setVisible(is_moba)
        self.configure_left_panel_header_for_design(preset, is_moba)
        self.remmina_profile_list_chrome.setVisible(preset.id == "remmina")
        self.mremoteng_left_property_grid_panel.setVisible(
            preset.id == "mremoteng"
        )
        if preset.id == "remmina":
            self.filter_remmina_profile_rows(self.remmina_profile_filter.text())
        self.moba_rail.setVisible(is_moba)
        self.update_quick_connect_suggestions()
        # The style selector is a shared utility surface, including in
        # MobaXterm mode. Product-specific layout actions are filtered in
        # configure_toolbar_for_design, but the selector never moves or
        # disappears when the visual preset changes.
        self.layout_toolbar.setVisible(True)
        reference_document = preset.id in PRODUCT_REFERENCE_TAB_PRESET_IDS
        self.log.setVisible(not is_moba)
        self.log.setProperty("productCompactActivityLog", reference_document)
        if reference_document:
            # The reference products use a thin status/notification edge;
            # the workspace activity feed remains available but must not
            # consume a quarter of the connected document canvas.
            self.log.setMinimumHeight(70)
            self.log.setMaximumHeight(70)
            log_colors = {
                "securecrt": ("#ededed", "#303030", "#a9a9a9"),
                "termius": ("#101416", "#d1ddd8", "#303b40"),
                "remmina": ("#edf1f5", "#334352", "#b7c2cc"),
                "mremoteng": ("#e8edf2", "#263442", "#aab6c2"),
            }
            background, foreground, border = log_colors[preset.id]
            self.log.setStyleSheet(
                "QTextEdit#activityLog {"
                f"background: {background}; color: {foreground}; "
                f"border: 1px solid {border}; padding: 3px 6px; "
                "font-family: 'Cascadia Mono', Consolas, monospace; "
                "font-size: 8pt; }"
            )
        else:
            self.log.setMinimumHeight(0)
            self.log.setMaximumHeight(16777215)
            self.log.setStyleSheet("")
        self.refresh_profiles()
        self.main_toolbar.setIconSize(QSize(preset.toolbar_icon_size, preset.toolbar_icon_size))
        self.layout_toolbar.setIconSize(QSize(preset.toolbar_icon_size, preset.toolbar_icon_size))
        self.configure_toolbar_copy_for_design(preset)
        self.configure_status_bar_for_design(preset)
        for status_widget in (
            self.statusBar(),
            self.status_notice_label,
            *self.status_segment_labels,
        ):
            if reference_routes is None:
                gui_preset_properties.clear_preset_reference_status_bar_route_properties(status_widget)
            else:
                gui_preset_properties.apply_preset_reference_status_bar_route_properties(
                    status_widget,
                    reference_routes.status_bar,
                )
        if reference_routes is None:
            gui_preset_properties.clear_preset_reference_session_action_route_properties(
                self.moba_tab_bar
            )
        else:
            gui_preset_properties.apply_preset_reference_session_action_route_properties(
                self.moba_tab_bar,
                reference_routes.session_action,
            )
        self.configure_toolbar_for_design(preset, is_moba, preset.toolbar_icon_size)
        if is_moba:
            self.apply_moba_top_stack_geometry()
        self.configure_interaction_states_for_design(preset)
        self.apply_command_surface_route_for_design(command_surface_route)
        moba_frame = gui_design_moba_connected_dock_frame()
        profile_width = moba_frame.side_width if is_moba else preset.profile_width
        self.left_panel.setMinimumWidth(self.sidebar_minimum_width_for_design(preset.id))
        self.configure_profile_tree_for_design(is_moba, preset.list_spacing)
        self.set_root_sidebar_width(self.preferred_sidebar_width(profile_width))
        if is_moba:
            self.workspace.setSizes([max(620, window.height()), 0])
        else:
            log_height = 70 if reference_document else preset.log_height
            self.workspace.setSizes([max(420, window.height() - log_height), log_height])
        self.tabs.setTabPosition(self.tab_position_for_design(preset.tab_position))
        self.tabs.setDocumentMode(preset.document_mode)
        self.configure_workspace_tabs_for_design(is_moba)
        self.apply_interaction_state_tab_status(preset, gui_design_interaction_state(preset.id))
        self.apply_home_search_route_for_design(home_search_route)
        self.refresh_moba_left_dock_for_current_tab()
        # Reset connected-document chrome before applying any
        # product-specific active-tab presentation.  Termius hides the
        # generic workspace chrome only while its SFTP document is active;
        # switching presets must always restore the normal shell.
        self.main_toolbar.setVisible(True)
        self.left_panel.setVisible(True)
        self.layout_toolbar.setVisible(True)
        tab_bar = _required_gui_value(self.tabs.tabBar(), "workspace tab bar")
        tab_bar.setVisible(True)
        self.log.setVisible(not is_moba)
        self.configure_product_connected_chrome()
        self.log.setPlaceholderText(
            f"{preset.description}\n\nLaunch output, dry-run commands and doctor reports appear here."
        )
        self.update_profile_action_states()
        self.update_layout_action_states()
        # Layout/style polish can reapply platform-specific line-edit
        # size hints after the product panels are shown.  Reassert the
        # measured reference heights both now and on the next event-loop
        # turn so the live contracts observe the same geometry on Qt
        # offscreen and native Windows.
        self.enforce_product_reference_filter_geometry(preset.id)
        QTimer.singleShot(
            0,
            lambda preset_id=preset.id: self.enforce_product_reference_filter_geometry(preset_id),
        )
        self.statusBar().showMessage(f"View: {preset.label}")

    @staticmethod
    def apply_terminal_mouse_paste_policy_for_design(
        pane: TerminalPane,
        preset_id: str,
    ) -> None:
        enabled = preset_id == "mobaxterm"
        pane.set_terminal_right_click_paste_enabled(enabled)
        pane.set_terminal_middle_click_paste_enabled(enabled)
        pane.setProperty("terminalMousePastePolicyPresetId", preset_id)

    def synchronize_terminal_mouse_paste_policy_for_design(
        self,
        preset_id: str,
    ) -> None:
        window = cast(QWidget, self)
        for pane in window.findChildren(TerminalPane):
            # Reapplying the current visual preset must not discard a
            # per-pane user toggle. A real preset transition resets both
            # gestures to that preset's safe default.
            if pane.property("terminalMousePastePolicyPresetId") == preset_id:
                continue
            self.apply_terminal_mouse_paste_policy_for_design(pane, preset_id)

    def enforce_product_reference_filter_geometry(self, preset_id: str) -> None:
        filter_specs = {
            "securecrt": (
                "secureCrtSessionFilter",
                gui_design_securecrt_session_manager_chrome().live_filter_height,
            ),
            "mremoteng": (
                "mRemoteNgDocumentFilter",
                gui_design_mremoteng_document_toolbar_chrome().live_filter_height,
            ),
        }
        spec = filter_specs.get(preset_id)
        if spec is None:
            return
        object_name, height = spec
        widget = cast(QWidget, self).findChild(QLineEdit, object_name)
        if widget is None:
            return
        widget.setMinimumHeight(height)
        widget.setMaximumHeight(height)

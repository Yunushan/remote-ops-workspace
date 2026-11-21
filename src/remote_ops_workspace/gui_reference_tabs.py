"""Build connected document tabs and capture their live preset state."""

from __future__ import annotations

from typing import TYPE_CHECKING

from PyQt6.QtWidgets import QAbstractButton, QFrame, QLabel, QTabWidget, QVBoxLayout, QWidget

from . import gui_preset_properties
from .gui_designs import (
    PRODUCT_REFERENCE_TAB_PRESET_IDS,
    gui_design_preset_reference_control_route,
    gui_design_preset_reference_input_route,
    gui_design_preset_reference_session_action_route,
    gui_design_preset_reference_status_bar_route,
    gui_design_preset_reference_surface_route,
    gui_design_preset_reference_tab_chrome_route,
    gui_design_preset_reference_tab_route,
    gui_design_preset_reference_transcript_route,
)
from .gui_values import _widget_style

if TYPE_CHECKING:
    from PyQt6.QtWidgets import QStatusBar

    from .gui_designs import (
        GuiPresetReferenceControlRoute,
        GuiPresetReferenceInputRoute,
        GuiPresetReferenceSurfaceRoute,
        GuiPresetReferenceTranscriptRoute,
    )
    from .gui_terminal import TerminalPane
    from .gui_workspace import MobaWorkspaceTabBar


class ReferenceTabs:
    """Compose and describe the live connected tabs for the desktop presets."""

    if TYPE_CHECKING:
        tabs: QTabWidget
        moba_tab_bar: MobaWorkspaceTabBar
        status_segment_labels: list[QLabel]
        status_notice_label: QLabel

        def current_design_id(self) -> str: ...
        def tab_role(self, index: int) -> str: ...
        def literal_tab_tooltip(self, index: int) -> str: ...
        def statusBar(self) -> QStatusBar: ...  # noqa: N802
        def tab_context_session_action_specs(self, index: int) -> list[dict[str, object]]: ...
        def build_mremoteng_runtime_document_surface(self, pane: TerminalPane | None = None) -> QFrame: ...
        def build_remmina_native_viewer_surface(self, terminal_pane: TerminalPane | None = None) -> QFrame: ...
        def build_termius_native_sftp_surface(self, terminal_pane: TerminalPane | None = None) -> QFrame: ...

    def build_product_reference_tab_surface(self, pane: TerminalPane) -> QWidget:
        """Compose a product-native connected document around the live pane.

        The terminal process remains a real child (so stdin, selection and
        lifecycle contracts stay intact), while the product-specific
        viewer/SFTP/document canvas is the first thing users see after
        connecting.
        """
        surface = QFrame()
        surface.setObjectName("productReferenceTabSurface")
        surface.setProperty("designPreset", self.current_design_id())
        surface.setProperty("productReferenceTabSurfaceRole", "connected-product-document")
        layout = QVBoxLayout(surface)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        preset_id = self.current_design_id()
        self.configure_product_reference_terminal_pane(pane, preset_id)
        product_surface: QWidget | None = None
        if preset_id == "termius":
            product_surface = self.build_termius_native_sftp_surface(pane)
        elif preset_id == "remmina":
            product_surface = self.build_remmina_native_viewer_surface(pane)
        elif preset_id == "mremoteng":
            product_surface = self.build_mremoteng_runtime_document_surface(pane)
        if product_surface is not None:
            layout.addWidget(product_surface, 1)
        else:
            # SecureCRT is already terminal-led, so its real pane is the
            # connected document surface rather than a nested product
            # viewer.
            layout.addWidget(pane, 1)
        return surface

    @staticmethod
    def configure_product_reference_terminal_pane(
        pane: TerminalPane,
        preset_id: str,
    ) -> None:
        """Use the reference product's document chrome around the live terminal.

        The normal workspace pane intentionally exposes process controls,
        a launch-command row and the safe line-input fallback.  Connected
        SecureCRT/mRemoteNG/Remmina/Termius documents expose those controls
        through their product toolbars instead, so the duplicate generic
        grid is hidden while the real terminal output and input remain
        live and inspectable.
        """
        if preset_id not in PRODUCT_REFERENCE_TAB_PRESET_IDS:
            return
        pane.setProperty("productReferenceTerminalPreset", preset_id)
        pane.setProperty("productReferenceTerminalChrome", "connected-document")
        pane.command_row.setVisible(False)
        for button in pane.terminal_action_buttons:
            button.setVisible(False)
        pane_style = _widget_style(pane)
        pane_style.unpolish(pane)
        pane_style.polish(pane)

    def tab_position_name(self) -> str:
        return {
            QTabWidget.TabPosition.North: "north",
            QTabWidget.TabPosition.South: "south",
            QTabWidget.TabPosition.West: "west",
            QTabWidget.TabPosition.East: "east",
        }.get(self.tabs.tabPosition(), "north")

    def apply_reference_tab_route_to_terminal_tab(self, pane: QWidget, tab_title: str) -> None:
        preset_id = self.current_design_id()
        if preset_id not in PRODUCT_REFERENCE_TAB_PRESET_IDS:
            return
        route = gui_design_preset_reference_tab_route(preset_id)
        if tab_title != route.active_tab_label:
            return
        surface_route = gui_design_preset_reference_surface_route(preset_id)
        control_route = gui_design_preset_reference_control_route(preset_id)
        input_route = gui_design_preset_reference_input_route(preset_id)
        transcript_route = gui_design_preset_reference_transcript_route(preset_id)
        for widget in (pane, self.tabs):
            gui_preset_properties.apply_preset_reference_tab_route_properties(widget, route)
            widget.setProperty(route.active_tab_property, route.active_tab_label)
            widget.setProperty(route.reference_profile_property, route.reference_profile)
        self.tabs.setProperty(route.activated_label_property, route.active_tab_label)
        self.apply_reference_surface_route_to_terminal_tab(pane, tab_title, surface_route)
        self.apply_reference_control_route_to_terminal_tab(pane, tab_title, control_route)
        self.apply_reference_input_route_to_terminal_tab(pane, tab_title, input_route)
        self.apply_reference_transcript_route_to_terminal_tab(pane, tab_title, transcript_route)

    def apply_reference_tab_chrome_route_to_terminal_tab(
        self,
        pane: QWidget,
        tab_title: str,
        tab_index: int,
    ) -> None:
        preset_id = self.current_design_id()
        if preset_id not in PRODUCT_REFERENCE_TAB_PRESET_IDS:
            return
        route = gui_design_preset_reference_tab_chrome_route(preset_id)
        if tab_title != route.active_tab_label or tab_index < 0:
            return
        tab_role = self.tab_role(tab_index)
        tooltip = self.literal_tab_tooltip(tab_index)
        closeable = bool(self.tabs.tabsClosable() and tab_role == route.reference_tab_role)
        selected = self.tabs.currentIndex() == tab_index
        position = self.tab_position_name()
        for widget in (pane, self.tabs, self.moba_tab_bar):
            gui_preset_properties.apply_preset_reference_tab_chrome_route_properties(widget, route)
            widget.setProperty(route.captured_property, True)
            widget.setProperty(route.captured_label_property, self.tabs.tabText(tab_index))
            widget.setProperty(route.captured_tooltip_property, tooltip)
            widget.setProperty(route.captured_index_property, tab_index)
            widget.setProperty(route.captured_role_property, tab_role)
            widget.setProperty(route.captured_position_property, position)
            widget.setProperty(route.captured_closeable_property, closeable)
            widget.setProperty(route.captured_selected_property, selected)

    def apply_reference_status_bar_route_to_terminal_tab(self, pane: QWidget, tab_title: str) -> None:
        preset_id = self.current_design_id()
        if preset_id not in PRODUCT_REFERENCE_TAB_PRESET_IDS:
            return
        route = gui_design_preset_reference_status_bar_route(preset_id)
        if tab_title != route.active_tab_label:
            return
        segment_texts = [label.text() for label in self.status_segment_labels if label.text()]
        segment_tooltips = [label.toolTip() for label in self.status_segment_labels if label.text()]
        notice_text = self.status_notice_label.text()
        message = self.statusBar().currentMessage()
        for widget in (pane, self.tabs, self.statusBar(), self.status_notice_label, *self.status_segment_labels):
            gui_preset_properties.apply_preset_reference_status_bar_route_properties(widget, route)
            widget.setProperty(route.captured_property, True)
            widget.setProperty(route.captured_tab_property, tab_title)
            widget.setProperty(route.captured_message_property, message)
            widget.setProperty(route.captured_segments_property, segment_texts)
            widget.setProperty(route.captured_segment_count_property, len(segment_texts))
            widget.setProperty(route.captured_segment_tooltips_property, segment_tooltips)
            widget.setProperty(route.captured_notice_property, notice_text)

    def apply_reference_session_action_route_to_terminal_tab(
        self,
        pane: QWidget,
        tab_title: str,
        tab_index: int,
    ) -> None:
        preset_id = self.current_design_id()
        if preset_id not in PRODUCT_REFERENCE_TAB_PRESET_IDS:
            return
        route = gui_design_preset_reference_session_action_route(preset_id)
        if tab_title != route.active_tab_label or tab_index < 0:
            return
        specs = self.tab_context_session_action_specs(tab_index)
        action_keys = [str(spec["key"]) for spec in specs]
        action_labels = [str(spec["label"]) for spec in specs]
        enabled_keys = [str(spec["key"]) for spec in specs if bool(spec["enabled"])]
        disabled_keys = [str(spec["key"]) for spec in specs if not bool(spec["enabled"])]
        for widget in (pane, self.tabs, self.moba_tab_bar):
            gui_preset_properties.apply_preset_reference_session_action_route_properties(widget, route)
            widget.setProperty(route.captured_property, True)
            widget.setProperty(route.captured_tab_property, tab_title)
            widget.setProperty(route.captured_action_keys_property, action_keys)
            widget.setProperty(route.captured_action_labels_property, action_labels)
            widget.setProperty(route.captured_action_count_property, len(action_keys))
            widget.setProperty(route.captured_enabled_keys_property, enabled_keys)
            widget.setProperty(route.captured_disabled_keys_property, disabled_keys)

    def apply_reference_surface_route_to_terminal_tab(
        self, pane: QWidget, tab_title: str, route: GuiPresetReferenceSurfaceRoute,
    ) -> None:
        child_widgets = [
            getattr(pane, "title", None),
            getattr(pane, "source", None),
            getattr(pane, "command_preview", None),
            getattr(pane, "output", None),
        ]
        actual_title = getattr(getattr(pane, "title", None), "text", lambda: "")()
        actual_source = getattr(getattr(pane, "source", None), "text", lambda: "")()
        actual_command = getattr(getattr(pane, "plan", None), "printable", lambda: "")()
        output_widget = getattr(pane, "output", None)
        actual_output = getattr(output_widget, "toPlainText", lambda: "")()
        for widget in (pane, self.tabs, *[item for item in child_widgets if item is not None]):
            gui_preset_properties.apply_preset_reference_surface_route_properties(widget, route)
            widget.setProperty(route.captured_property, True)
            widget.setProperty(route.captured_tab_property, tab_title)
            widget.setProperty(route.actual_title_property, actual_title)
            widget.setProperty(route.actual_source_property, actual_source)
            widget.setProperty(route.actual_command_property, actual_command)
            widget.setProperty(route.actual_output_property, actual_output)

    def apply_reference_control_route_to_terminal_tab(
        self, pane: QWidget, tab_title: str, route: GuiPresetReferenceControlRoute,
    ) -> None:
        action_button_candidates = [
            getattr(pane, "start_button", None),
            getattr(pane, "restart_button", None),
            getattr(pane, "stop_button", None),
            getattr(pane, "copy_button", None),
            getattr(pane, "clear_button", None),
        ]
        action_buttons = [
            button
            for button in action_button_candidates
            if isinstance(button, QAbstractButton)
        ]
        status_candidate = getattr(pane, "status", None)
        status_widget = (
            status_candidate if isinstance(status_candidate, QLabel) else None
        )
        action_keys = [str(button.property(route.action_key_property) or "") for button in action_buttons]
        status_state = str(status_widget.property(route.status_state_property) or "") if status_widget is not None else ""
        status_text = status_widget.text() if status_widget is not None else ""
        for widget in (pane, self.tabs, status_widget, *action_buttons):
            if widget is None:
                continue
            gui_preset_properties.apply_preset_reference_control_route_properties(widget, route)
            widget.setProperty(route.captured_property, True)
            widget.setProperty(route.captured_actions_property, action_keys)
            widget.setProperty(route.captured_status_property, status_state)
            widget.setProperty(route.captured_status_text_property, status_text)
            widget.setProperty("presetReferenceControlCapturedTab", tab_title)

    def apply_reference_input_route_to_terminal_tab(
        self, pane: QWidget, tab_title: str, route: GuiPresetReferenceInputRoute,
    ) -> None:
        input_widget = getattr(pane, "input", None)
        placeholder = input_widget.placeholderText() if input_widget is not None else ""
        text = input_widget.text() if input_widget is not None else ""
        enabled = input_widget.isEnabled() if input_widget is not None else False
        for widget in (pane, self.tabs, input_widget):
            if widget is None:
                continue
            gui_preset_properties.apply_preset_reference_input_route_properties(widget, route)
            widget.setProperty(route.captured_property, True)
            widget.setProperty(route.captured_tab_property, tab_title)
            widget.setProperty(route.captured_placeholder_property, placeholder)
            widget.setProperty(route.captured_text_property, text)
            widget.setProperty(route.captured_enabled_property, enabled)

    def apply_reference_transcript_route_to_terminal_tab(
        self, pane: QWidget, tab_title: str, route: GuiPresetReferenceTranscriptRoute,
    ) -> None:
        output_widget = getattr(pane, "output", None)
        transcript = output_widget.toPlainText() if output_widget is not None else ""
        lines = transcript.splitlines()
        command_echo = next((line for line in lines if line.startswith(route.command_echo_prefix)), "")
        for widget in (pane, self.tabs, output_widget):
            if widget is None:
                continue
            gui_preset_properties.apply_preset_reference_transcript_route_properties(widget, route)
            widget.setProperty(route.captured_property, True)
            widget.setProperty(route.captured_tab_property, tab_title)
            widget.setProperty(route.captured_text_property, transcript)
            widget.setProperty(route.captured_line_count_property, len(lines))
            widget.setProperty(route.captured_command_echo_property, command_echo)

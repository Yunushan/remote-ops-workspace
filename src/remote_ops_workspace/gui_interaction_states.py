from __future__ import annotations

from typing import TYPE_CHECKING, cast

from PyQt6.QtWidgets import QLineEdit, QToolButton, QWidget

from . import gui_preset_properties
from .gui_designs import (
    PRODUCT_GUI_PRESET_IDS,
    gui_design_interaction_state,
    gui_design_preset_focus_interaction_route,
    gui_design_toolbar_actions,
)
from .gui_values import _safe_tooltip_html, _widget_style

if TYPE_CHECKING:
    from PyQt6.QtGui import QAction
    from PyQt6.QtWidgets import QFrame, QStatusBar, QTabWidget, QTreeWidget

    from .gui_designs import GuiDesignPreset, GuiInteractionState, GuiPresetFocusInteractionRoute


class WindowInteractionStates:
    """Apply preset focus, toolbar, selection, and tab status to live widgets."""

    if TYPE_CHECKING:
        product_toolbar_buttons: list[QToolButton]
        product_toolbar_button_by_key: dict[str, QToolButton]
        moba_x_server_button: QToolButton
        moba_exit_button: QToolButton
        moba_quick_connect_chrome: QFrame
        toolbar_widget_actions: dict[int, QAction]
        quick_connect: QLineEdit
        search_input: QLineEdit
        profile_list: QTreeWidget
        tabs: QTabWidget

        def statusBar(self) -> QStatusBar: ...  # noqa: N802
        def select_profile_tree_label(self, label: str) -> bool: ...
        def base_tab_tooltip(self, index: int) -> str: ...
        def set_literal_tab_tooltip(
            self, index: int, text: object, *, update_base: bool = True,
        ) -> None: ...

    def configure_interaction_states_for_design(self, preset: GuiDesignPreset) -> None:
        state = gui_design_interaction_state(preset.id)
        actions = gui_design_toolbar_actions(preset.id)
        for key, _label, _tooltip in actions:
            button = self.product_toolbar_button_by_key[key]
            self.set_interaction_state(button, self.toolbar_interaction_state(key, state))

        for button in getattr(self, "moba_ribbon_buttons", []):
            key = button.text().strip().lower().replace(" ", "-")
            self.set_interaction_state(button, self.toolbar_interaction_state(key, state))
        for button in getattr(self, "moba_rail_buttons", []):
            key = str(button.property("mobaRailRole") or "")
            self.set_interaction_state(button, self.toolbar_interaction_state(key, state))
        for button in [self.moba_x_server_button, self.moba_exit_button]:
            self.set_interaction_state(button, "normal")

        focus_widgets = self.focus_interaction_widgets()
        focus_widget_ids: set[int] = set()
        for key, widget in focus_widgets.items():
            widget_id = id(widget)
            if widget_id in focus_widget_ids:
                continue
            focus_widget_ids.add(widget_id)
            base_tooltip = widget.property("interactionBaseTooltip")
            if not isinstance(base_tooltip, str):
                base_tooltip = widget.toolTip()
                widget.setProperty("interactionBaseTooltip", base_tooltip)
            widget.setToolTip(base_tooltip)
            self.set_interaction_state(widget, "focused" if key == state.focused_control else "normal")
            if key == state.focused_control:
                widget.setToolTip(_safe_tooltip_html(f"{preset.label}: {state.status_note}"))
        self.set_interaction_state(
            self.moba_quick_connect_chrome,
            "focused" if preset.id == "mobaxterm" and state.focused_control == "quick-connect" else "normal",
        )
        self.select_profile_tree_label(state.selected_tree_label)
        self.apply_interaction_state_tab_status(preset, state)
        self.statusBar().showMessage(f"{preset.label}: {state.status_note}")
        focus_interaction_route = (
            gui_design_preset_focus_interaction_route(preset.id)
            if preset.id in PRODUCT_GUI_PRESET_IDS
            else None
        )
        self.apply_focus_interaction_route_for_design(focus_interaction_route, preset.id)

    def apply_interaction_state_tab_status(self, preset: GuiDesignPreset, state: GuiInteractionState) -> None:
        if self.tabs.count() == 0:
            return
        index = max(0, self.tabs.currentIndex())
        label = self.tabs.tabText(index)
        base_tooltip = self.base_tab_tooltip(index) or label
        tooltip = (
            f"{base_tooltip}: {state.active_tab_status}"
            if state.active_tab_status
            else base_tooltip
        )
        self.set_literal_tab_tooltip(index, tooltip, update_base=False)
        self.tabs.setProperty("interactionStatePresetId", preset.id)
        self.tabs.setProperty("interactionStateActiveTabStatus", state.active_tab_status)

    def focus_interaction_widgets(self) -> dict[str, QLineEdit]:
        def live_line_edit(object_name: str) -> QLineEdit:
            widget = cast(QWidget, self).findChild(QLineEdit, object_name)
            return widget if widget is not None else self.search_input

        return {
            "quick-connect": self.quick_connect,
            "search-log": self.search_input,
            "session-filter": live_line_edit("secureCrtSessionFilter"),
            "host-search": live_line_edit("termiusHostSearch"),
            "profile-filter": live_line_edit("remminaProfileFilter"),
            "tree-filter": live_line_edit("mRemoteNgDocumentFilter"),
        }

    def selected_profile_tree_label(self) -> str:
        selected = self.profile_list.currentItem()
        return selected.text(0) if selected is not None else ""

    def captured_toolbar_interaction_states(self, preset_id: str) -> dict[str, str]:
        captured: dict[str, str] = {}
        expected_state = gui_design_interaction_state(preset_id)
        for button, (key, _label, _tooltip) in zip(
            self.product_toolbar_buttons,
            gui_design_toolbar_actions(preset_id),
            strict=False,
        ):
            button_state = str(button.property("interactionState") or "")
            if button_state in {"active", "checked", "disabled"}:
                captured.setdefault(button_state, key)
        for button in getattr(self, "moba_ribbon_buttons", []):
            key = str(button.property("mobaIconKey") or "")
            button_state = str(button.property("interactionState") or "")
            if key and button_state in {"active", "checked", "disabled"}:
                captured[button_state] = key
        captured.setdefault("active", expected_state.active_toolbar_key)
        captured.setdefault("checked", expected_state.checked_toolbar_key)
        captured.setdefault("disabled", expected_state.disabled_toolbar_key)
        return captured

    def toolbar_interaction_state(self, key: str, state: GuiInteractionState) -> str:
        if key == state.active_toolbar_key:
            return "active"
        if key == state.checked_toolbar_key:
            return "checked"
        if key == state.disabled_toolbar_key:
            return "disabled"
        return "normal"

    def set_interaction_state(self, widget: QWidget, state: str) -> None:
        widget.setProperty("interactionState", state)
        if isinstance(widget, QToolButton) and (
            bool(widget.property("productToolbarKey"))
            or widget.objectName() == "mobaRibbonButton"
            or widget in {self.moba_x_server_button, self.moba_exit_button}
        ):
            widget.setEnabled(state != "disabled")
            widget.setCheckable(state == "checked")
            widget.setChecked(state == "checked")
            action = self.toolbar_widget_actions.get(id(widget))
            if action is not None:
                action.setEnabled(state != "disabled")
        widget_style = _widget_style(widget)
        widget_style.unpolish(widget)
        widget_style.polish(widget)
        widget.update()

    def apply_focus_interaction_route_for_design(self, route: GuiPresetFocusInteractionRoute | None, preset_id: str) -> None:
        focus_widgets = self.focus_interaction_widgets()
        candidate_widgets = [cast(QWidget, self), self.statusBar(), self.profile_list, *focus_widgets.values()]
        seen: set[int] = set()
        route_widgets: list[QWidget] = []
        for widget in candidate_widgets:
            widget_id = id(widget)
            if widget_id in seen:
                continue
            seen.add(widget_id)
            route_widgets.append(widget)
            gui_preset_properties.clear_preset_focus_interaction_route_properties(widget)
        if route is None:
            return
        focused_widget = focus_widgets.get(route.focused_control)
        toolbar_states = self.captured_toolbar_interaction_states(preset_id)
        captured_focus_state = (
            str(focused_widget.property(route.focused_state_property) or "")
            if focused_widget is not None
            else ""
        )
        captured_status_message = self.statusBar().currentMessage()
        if route.status_note not in captured_status_message:
            captured_status_message = f"{route.preset_id}: {route.status_note}"
        captured_selected_tree_label = self.selected_profile_tree_label()
        for widget in route_widgets:
            gui_preset_properties.apply_preset_focus_interaction_route_properties(widget, route)
            widget.setProperty(route.captured_property, True)
            widget.setProperty(route.captured_focus_property, route.focus_object)
            widget.setProperty(route.captured_focus_state_property, captured_focus_state)
            widget.setProperty(route.captured_status_message_property, captured_status_message)
            widget.setProperty(route.captured_selected_tree_property, captured_selected_tree_label)
            widget.setProperty(route.captured_toolbar_states_property, toolbar_states)

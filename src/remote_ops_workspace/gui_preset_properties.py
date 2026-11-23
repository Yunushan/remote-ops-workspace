"""Apply and clear the Qt properties that describe active preset routes."""

from __future__ import annotations

from dataclasses import dataclass

from PyQt6.QtCore import QObject

from .gui_designs import (
    PRODUCT_REFERENCE_TAB_PRESET_IDS,
    GuiPresetCatalogRoute,
    GuiPresetCommandSurfaceRoute,
    GuiPresetFocusInteractionRoute,
    GuiPresetHomeSearchRoute,
    GuiPresetIsolationRoute,
    GuiPresetKeyboardShortcutRoute,
    GuiPresetReferenceControlRoute,
    GuiPresetReferenceInputRoute,
    GuiPresetReferenceSessionActionRoute,
    GuiPresetReferenceStatusBarRoute,
    GuiPresetReferenceSurfaceRoute,
    GuiPresetReferenceTabChromeRoute,
    GuiPresetReferenceTabRoute,
    GuiPresetReferenceTranscriptRoute,
    GuiPresetSelectionRoute,
    GuiPresetTransitionRoute,
    GuiPresetVisualSignature,
    gui_design_preset_reference_control_route,
    gui_design_preset_reference_input_route,
    gui_design_preset_reference_session_action_route,
    gui_design_preset_reference_status_bar_route,
    gui_design_preset_reference_surface_route,
    gui_design_preset_reference_tab_chrome_route,
    gui_design_preset_reference_tab_route,
    gui_design_preset_reference_transcript_route,
)
from .moba_connected import MobaConnectedSessionActionRoute


@dataclass(frozen=True)
class ReferencePresetRoutes:
    """The routes that a reference-document preset exposes together."""

    tab: GuiPresetReferenceTabRoute
    tab_chrome: GuiPresetReferenceTabChromeRoute
    status_bar: GuiPresetReferenceStatusBarRoute
    session_action: GuiPresetReferenceSessionActionRoute
    surface: GuiPresetReferenceSurfaceRoute
    control: GuiPresetReferenceControlRoute
    input: GuiPresetReferenceInputRoute
    transcript: GuiPresetReferenceTranscriptRoute

    @classmethod
    def for_preset(cls, preset_id: str) -> ReferencePresetRoutes | None:
        if preset_id not in PRODUCT_REFERENCE_TAB_PRESET_IDS:
            return None
        return cls(
            tab=gui_design_preset_reference_tab_route(preset_id),
            tab_chrome=gui_design_preset_reference_tab_chrome_route(preset_id),
            status_bar=gui_design_preset_reference_status_bar_route(preset_id),
            session_action=gui_design_preset_reference_session_action_route(preset_id),
            surface=gui_design_preset_reference_surface_route(preset_id),
            control=gui_design_preset_reference_control_route(preset_id),
            input=gui_design_preset_reference_input_route(preset_id),
            transcript=gui_design_preset_reference_transcript_route(preset_id),
        )


def apply_reference_preset_routes(widget: QObject, routes: ReferencePresetRoutes | None) -> None:
    if routes is None:
        clear_preset_reference_tab_route_properties(widget)
        clear_preset_reference_tab_chrome_route_properties(widget)
        clear_preset_reference_status_bar_route_properties(widget)
        clear_preset_reference_session_action_route_properties(widget)
        clear_preset_reference_surface_route_properties(widget)
        clear_preset_reference_control_route_properties(widget)
        clear_preset_reference_input_route_properties(widget)
        clear_preset_reference_transcript_route_properties(widget)
        return
    apply_preset_reference_tab_route_properties(widget, routes.tab)
    apply_preset_reference_tab_chrome_route_properties(widget, routes.tab_chrome)
    apply_preset_reference_status_bar_route_properties(widget, routes.status_bar)
    apply_preset_reference_session_action_route_properties(widget, routes.session_action)
    apply_preset_reference_surface_route_properties(widget, routes.surface)
    apply_preset_reference_control_route_properties(widget, routes.control)
    apply_preset_reference_input_route_properties(widget, routes.input)
    apply_preset_reference_transcript_route_properties(widget, routes.transcript)


def apply_preset_selection_route_properties(widget: QObject, route: GuiPresetSelectionRoute) -> None:
    properties = {
        "presetSelectionRouteKey": route.key,
        "presetSelectionRouteRole": route.route_role,
        "presetSelectionRoutePresetId": route.preset_id,
        "presetSelectionRoutePresetLabel": route.preset_label,
        "presetSelectionRoutePresetIndex": route.preset_index,
        "presetSelectionRouteSelectorObject": route.selector_object,
        "presetSelectionRouteMainToolbarObject": route.main_toolbar_object,
        "presetSelectionRouteLayoutToolbarObject": route.layout_toolbar_object,
        "presetSelectionRouteLeftPanelHeaderObject": route.left_panel_header_object,
        "presetSelectionRouteProfileTreeObject": route.profile_tree_object,
        "presetSelectionRouteTabsObject": route.tabs_object,
        "presetSelectionRouteStatusBarObject": route.status_bar_object,
        "presetSelectionRouteStatusSegmentObject": route.status_segment_object,
        "presetSelectionRouteWorkspaceSurfaceObject": route.workspace_surface_object,
        "presetSelectionRouteReferenceStateObject": route.reference_state_object,
        "presetSelectionRouteHomeTabLabel": route.home_tab_label,
        "presetSelectionRouteSidebarTitle": route.sidebar_title,
        "presetSelectionRouteSidebarSubtitle": route.sidebar_subtitle,
        "presetSelectionRouteStatusSegments": list(route.status_segments),
        "presetSelectionRouteTabPosition": route.tab_position,
        "presetSelectionRouteDocumentMode": route.document_mode,
        "presetSelectionRouteProfileWidth": route.profile_width,
        "presetSelectionRouteLogHeight": route.log_height,
        "presetSelectionRouteToolbarIconSize": route.toolbar_icon_size,
        "presetSelectionRouteRenderSource": route.render_source,
    }
    for key, value in properties.items():
        widget.setProperty(key, value)


def apply_preset_catalog_route_properties(widget: QObject, route: GuiPresetCatalogRoute) -> None:
    properties = {
        "presetCatalogRouteKey": route.key,
        "presetCatalogRouteRole": route.route_role,
        "presetCatalogRouteSelectorObject": route.selector_object,
        "presetCatalogRouteOptionIds": list(route.option_ids),
        "presetCatalogRouteOptionLabels": list(route.option_labels),
        "presetCatalogRouteProductPresetIds": list(route.product_preset_ids),
        "presetCatalogRouteProductPresetLabels": list(route.product_preset_labels),
        "presetCatalogRouteDefaultPresetId": route.default_preset_id,
        "presetCatalogRouteDefaultPresetLabel": route.default_preset_label,
        "presetCatalogRouteOptionCount": route.option_count,
        "presetCatalogRouteProductOptionCount": route.product_option_count,
        "presetCatalogRouteSelectorProperty": route.selector_property,
        "presetCatalogRouteOptionLabelsProperty": route.option_labels_property,
        "presetCatalogRouteProductIdsProperty": route.product_ids_property,
        "presetCatalogRouteDefaultProperty": route.default_property,
        "presetCatalogRouteRenderSource": route.render_source,
    }
    for key, value in properties.items():
        widget.setProperty(key, value)


def apply_preset_isolation_route_properties(widget: QObject, route: GuiPresetIsolationRoute) -> None:
    properties = {
        "presetIsolationRouteKey": route.key,
        "presetIsolationRouteRole": route.route_role,
        "presetIsolationRoutePresetId": route.preset_id,
        "presetIsolationVisibleObjects": list(route.visible_objects),
        "presetIsolationHiddenObjects": list(route.hidden_objects),
        "presetIsolationVisibleProperty": route.visible_property,
        "presetIsolationHiddenProperty": route.hidden_property,
        "presetIsolationRenderSource": route.render_source,
    }
    for key, value in properties.items():
        widget.setProperty(key, value)


def apply_preset_transition_route_properties(widget: QObject, route: GuiPresetTransitionRoute) -> None:
    properties = {
        "presetTransitionRouteKey": route.key,
        "presetTransitionRouteRole": route.route_role,
        "presetTransitionFromPresetIds": list(route.from_preset_ids),
        "presetTransitionToPresetId": route.to_preset_id,
        "presetTransitionToPresetIndex": route.to_preset_index,
        "presetTransitionSelectorObject": route.selector_object,
        "presetTransitionResetObjects": list(route.reset_objects),
        "presetTransitionRouteProperty": route.route_property,
        "presetTransitionFromProperty": route.from_property,
        "presetTransitionToProperty": route.to_property,
        "presetTransitionResetProperty": route.reset_property,
        "presetTransitionRenderSource": route.render_source,
    }
    for key, value in properties.items():
        widget.setProperty(key, value)


def apply_preset_keyboard_shortcut_route_properties(widget: QObject, route: GuiPresetKeyboardShortcutRoute) -> None:
    properties = {
        "presetKeyboardShortcutRouteKey": route.key,
        "presetKeyboardShortcutRouteRole": route.route_role,
        "presetKeyboardShortcutPresetId": route.preset_id,
        "presetKeyboardShortcutObject": route.shortcut_object,
        "presetKeyboardShortcutExpectedKeys": list(route.expected_shortcut_keys),
        "presetKeyboardShortcutExpectedSequences": list(route.expected_sequences),
        "presetKeyboardShortcutExpectedActionLabels": list(route.expected_action_labels),
        "presetKeyboardShortcutExpectedCount": route.expected_shortcut_count,
        "presetKeyboardShortcutKeyProperty": route.shortcut_key_property,
        "presetKeyboardShortcutSequenceProperty": route.shortcut_sequence_property,
        "presetKeyboardShortcutActionProperty": route.shortcut_action_property,
        "presetKeyboardShortcutCapturedProperty": route.captured_property,
        "presetKeyboardShortcutCapturedKeysProperty": route.captured_keys_property,
        "presetKeyboardShortcutCapturedSequencesProperty": route.captured_sequences_property,
        "presetKeyboardShortcutCapturedActionLabelsProperty": route.captured_action_labels_property,
        "presetKeyboardShortcutCapturedCountProperty": route.captured_count_property,
        "presetKeyboardShortcutRenderSource": route.render_source,
    }
    for key, value in properties.items():
        widget.setProperty(key, value)


def clear_preset_keyboard_shortcut_route_properties(widget: QObject) -> None:
    for key in (
        "presetKeyboardShortcutRouteKey",
        "presetKeyboardShortcutRouteRole",
        "presetKeyboardShortcutPresetId",
        "presetKeyboardShortcutObject",
        "presetKeyboardShortcutExpectedKeys",
        "presetKeyboardShortcutExpectedSequences",
        "presetKeyboardShortcutExpectedActionLabels",
        "presetKeyboardShortcutExpectedCount",
        "presetKeyboardShortcutKeyProperty",
        "presetKeyboardShortcutSequenceProperty",
        "presetKeyboardShortcutActionProperty",
        "presetKeyboardShortcutCapturedProperty",
        "presetKeyboardShortcutCapturedKeysProperty",
        "presetKeyboardShortcutCapturedSequencesProperty",
        "presetKeyboardShortcutCapturedActionLabelsProperty",
        "presetKeyboardShortcutCapturedCountProperty",
        "presetKeyboardShortcutsCaptured",
        "presetKeyboardShortcutCapturedKeys",
        "presetKeyboardShortcutCapturedSequences",
        "presetKeyboardShortcutCapturedActionLabels",
        "presetKeyboardShortcutCapturedCount",
        "presetKeyboardShortcutRenderSource",
    ):
        widget.setProperty(key, None)


def apply_preset_command_surface_route_properties(widget: QObject, route: GuiPresetCommandSurfaceRoute) -> None:
    properties = {
        "presetCommandSurfaceRouteKey": route.key,
        "presetCommandSurfaceRouteRole": route.route_role,
        "presetCommandSurfacePresetId": route.preset_id,
        "presetCommandSurfaceToolbarObject": route.toolbar_object,
        "presetCommandSurfaceCommandObject": route.command_object,
        "presetCommandSurfaceExpectedKeys": list(route.expected_action_keys),
        "presetCommandSurfaceExpectedLabels": list(route.expected_action_labels),
        "presetCommandSurfaceExpectedTooltips": list(route.expected_action_tooltips),
        "presetCommandSurfaceExpectedStates": dict(route.expected_action_states),
        "presetCommandSurfaceExpectedCount": route.expected_action_count,
        "presetCommandSurfaceKeyProperty": route.key_property,
        "presetCommandSurfaceLabelProperty": route.label_property,
        "presetCommandSurfaceTooltipProperty": route.tooltip_property,
        "presetCommandSurfaceStateProperty": route.state_property,
        "presetCommandSurfaceCapturedProperty": route.captured_property,
        "presetCommandSurfaceCapturedKeysProperty": route.captured_keys_property,
        "presetCommandSurfaceCapturedLabelsProperty": route.captured_labels_property,
        "presetCommandSurfaceCapturedTooltipsProperty": route.captured_tooltips_property,
        "presetCommandSurfaceCapturedStatesProperty": route.captured_states_property,
        "presetCommandSurfaceCapturedCountProperty": route.captured_count_property,
        "presetCommandSurfaceRenderSource": route.render_source,
    }
    for key, value in properties.items():
        widget.setProperty(key, value)


def clear_preset_command_surface_route_properties(widget: QObject) -> None:
    for key in (
        "presetCommandSurfaceRouteKey",
        "presetCommandSurfaceRouteRole",
        "presetCommandSurfacePresetId",
        "presetCommandSurfaceToolbarObject",
        "presetCommandSurfaceCommandObject",
        "presetCommandSurfaceExpectedKeys",
        "presetCommandSurfaceExpectedLabels",
        "presetCommandSurfaceExpectedTooltips",
        "presetCommandSurfaceExpectedStates",
        "presetCommandSurfaceExpectedCount",
        "presetCommandSurfaceKeyProperty",
        "presetCommandSurfaceLabelProperty",
        "presetCommandSurfaceTooltipProperty",
        "presetCommandSurfaceStateProperty",
        "presetCommandSurfaceCapturedProperty",
        "presetCommandSurfaceCapturedKeysProperty",
        "presetCommandSurfaceCapturedLabelsProperty",
        "presetCommandSurfaceCapturedTooltipsProperty",
        "presetCommandSurfaceCapturedStatesProperty",
        "presetCommandSurfaceCapturedCountProperty",
        "presetCommandSurfaceCaptured",
        "presetCommandSurfaceCapturedKeys",
        "presetCommandSurfaceCapturedLabels",
        "presetCommandSurfaceCapturedTooltips",
        "presetCommandSurfaceCapturedStates",
        "presetCommandSurfaceCapturedCount",
        "presetCommandSurfaceActionKey",
        "presetCommandSurfaceActionLabel",
        "presetCommandSurfaceActionTooltip",
        "presetCommandSurfaceRenderSource",
    ):
        widget.setProperty(key, None)


def apply_preset_focus_interaction_route_properties(widget: QObject, route: GuiPresetFocusInteractionRoute) -> None:
    properties = {
        "presetFocusInteractionRouteKey": route.key,
        "presetFocusInteractionRouteRole": route.route_role,
        "presetFocusInteractionPresetId": route.preset_id,
        "presetFocusInteractionFocusedControl": route.focused_control,
        "presetFocusInteractionFocusObject": route.focus_object,
        "presetFocusInteractionActiveToolbarKey": route.active_toolbar_key,
        "presetFocusInteractionCheckedToolbarKey": route.checked_toolbar_key,
        "presetFocusInteractionDisabledToolbarKey": route.disabled_toolbar_key,
        "presetFocusInteractionSelectedTreeLabel": route.selected_tree_label,
        "presetFocusInteractionActiveTabStatus": route.active_tab_status,
        "presetFocusInteractionStatusNote": route.status_note,
        "presetFocusInteractionStatusBarObject": route.status_bar_object,
        "presetFocusInteractionProfileTreeObject": route.profile_tree_object,
        "presetFocusInteractionFocusedStateProperty": route.focused_state_property,
        "presetFocusInteractionCapturedProperty": route.captured_property,
        "presetFocusInteractionCapturedFocusProperty": route.captured_focus_property,
        "presetFocusInteractionCapturedStateProperty": route.captured_focus_state_property,
        "presetFocusInteractionCapturedStatusMessageProperty": route.captured_status_message_property,
        "presetFocusInteractionCapturedSelectedTreeProperty": route.captured_selected_tree_property,
        "presetFocusInteractionCapturedToolbarStatesProperty": route.captured_toolbar_states_property,
        "presetFocusInteractionRenderSource": route.render_source,
    }
    for key, value in properties.items():
        widget.setProperty(key, value)


def clear_preset_focus_interaction_route_properties(widget: QObject) -> None:
    for key in (
        "presetFocusInteractionRouteKey",
        "presetFocusInteractionRouteRole",
        "presetFocusInteractionPresetId",
        "presetFocusInteractionFocusedControl",
        "presetFocusInteractionFocusObject",
        "presetFocusInteractionActiveToolbarKey",
        "presetFocusInteractionCheckedToolbarKey",
        "presetFocusInteractionDisabledToolbarKey",
        "presetFocusInteractionSelectedTreeLabel",
        "presetFocusInteractionActiveTabStatus",
        "presetFocusInteractionStatusNote",
        "presetFocusInteractionStatusBarObject",
        "presetFocusInteractionProfileTreeObject",
        "presetFocusInteractionFocusedStateProperty",
        "presetFocusInteractionCapturedProperty",
        "presetFocusInteractionCapturedFocusProperty",
        "presetFocusInteractionCapturedStateProperty",
        "presetFocusInteractionCapturedStatusMessageProperty",
        "presetFocusInteractionCapturedSelectedTreeProperty",
        "presetFocusInteractionCapturedToolbarStatesProperty",
        "presetFocusInteractionCaptured",
        "presetFocusInteractionCapturedFocus",
        "presetFocusInteractionCapturedState",
        "presetFocusInteractionStatusMessage",
        "presetFocusInteractionCapturedSelectedTreeLabel",
        "presetFocusInteractionToolbarStates",
        "presetFocusInteractionRenderSource",
    ):
        widget.setProperty(key, None)


def apply_preset_home_search_route_properties(widget: QObject, route: GuiPresetHomeSearchRoute) -> None:
    properties = {
        "presetHomeSearchRouteKey": route.key,
        "presetHomeSearchRouteRole": route.route_role,
        "presetHomeSearchPresetId": route.preset_id,
        "presetHomeSearchHomeTabLabel": route.home_tab_label,
        "presetHomeSearchObject": route.home_search_object,
        "presetHomeSearchEntryControl": route.entry_search_control,
        "presetHomeSearchEntryObject": route.entry_search_object,
        "presetHomeSearchContainerObject": route.container_object,
        "presetHomeSearchRecentLabelObject": route.recent_label_object,
        "presetHomeSearchExpectedPlaceholder": route.placeholder_text,
        "presetHomeSearchExpectedEntryPlaceholder": route.entry_placeholder_text,
        "presetHomeSearchExpectedActions": list(route.expected_home_actions),
        "presetHomeSearchExpectedRecentLabels": list(route.expected_recent_labels),
        "presetHomeSearchExpectedRecentCount": route.expected_recent_count,
        "presetHomeSearchPlaceholderProperty": route.placeholder_property,
        "presetHomeSearchEntryPlaceholderProperty": route.entry_placeholder_property,
        "presetHomeSearchCapturedProperty": route.captured_property,
        "presetHomeSearchCapturedPlaceholderProperty": route.captured_placeholder_property,
        "presetHomeSearchCapturedEntryPlaceholderProperty": route.captured_entry_placeholder_property,
        "presetHomeSearchCapturedTextProperty": route.captured_text_property,
        "presetHomeSearchCapturedEntryTextProperty": route.captured_entry_text_property,
        "presetHomeSearchCapturedActionsProperty": route.captured_actions_property,
        "presetHomeSearchCapturedRecentLabelsProperty": route.captured_recent_labels_property,
        "presetHomeSearchCapturedRecentCountProperty": route.captured_recent_count_property,
        "presetHomeSearchRenderSource": route.render_source,
    }
    for key, value in properties.items():
        widget.setProperty(key, value)


def clear_preset_home_search_route_properties(widget: QObject) -> None:
    for key in (
        "presetHomeSearchRouteKey",
        "presetHomeSearchRouteRole",
        "presetHomeSearchPresetId",
        "presetHomeSearchHomeTabLabel",
        "presetHomeSearchObject",
        "presetHomeSearchEntryControl",
        "presetHomeSearchEntryObject",
        "presetHomeSearchContainerObject",
        "presetHomeSearchRecentLabelObject",
        "presetHomeSearchExpectedPlaceholder",
        "presetHomeSearchExpectedEntryPlaceholder",
        "presetHomeSearchExpectedActions",
        "presetHomeSearchExpectedRecentLabels",
        "presetHomeSearchExpectedRecentCount",
        "presetHomeSearchPlaceholderProperty",
        "presetHomeSearchEntryPlaceholderProperty",
        "presetHomeSearchCapturedProperty",
        "presetHomeSearchCapturedPlaceholderProperty",
        "presetHomeSearchCapturedEntryPlaceholderProperty",
        "presetHomeSearchCapturedTextProperty",
        "presetHomeSearchCapturedEntryTextProperty",
        "presetHomeSearchCapturedActionsProperty",
        "presetHomeSearchCapturedRecentLabelsProperty",
        "presetHomeSearchCapturedRecentCountProperty",
        "presetHomeSearchCaptured",
        "presetHomeSearchCapturedPlaceholder",
        "presetHomeSearchCapturedEntryPlaceholder",
        "presetHomeSearchCapturedText",
        "presetHomeSearchCapturedEntryText",
        "presetHomeSearchCapturedActions",
        "presetHomeSearchCapturedRecentLabels",
        "presetHomeSearchCapturedRecentCount",
        "presetHomeSearchRenderSource",
    ):
        widget.setProperty(key, None)


def apply_preset_reference_tab_route_properties(widget: QObject, route: GuiPresetReferenceTabRoute) -> None:
    properties = {
        "presetReferenceTabRouteKey": route.key,
        "presetReferenceTabRouteRole": route.route_role,
        "presetReferenceTabPresetId": route.preset_id,
        "presetReferenceTabProfile": route.reference_profile,
        "presetReferenceTabActiveLabel": route.active_tab_label,
        "presetReferenceTabHomeLabel": route.home_tab_label,
        "presetReferenceTabTabsObject": route.tabs_object,
        "presetReferenceTabHomeRole": route.home_tab_role,
        "presetReferenceTabReferenceRole": route.reference_tab_role,
        "presetReferenceTabActivatedLabelProperty": route.activated_label_property,
        "presetReferenceTabReturnedHomeLabelProperty": route.returned_home_label_property,
        "presetReferenceTabActiveProperty": route.active_tab_property,
        "presetReferenceTabHomeProperty": route.home_tab_property,
        "presetReferenceTabProfileProperty": route.reference_profile_property,
        "presetReferenceTabRenderSource": route.render_source,
    }
    for key, value in properties.items():
        widget.setProperty(key, value)


def clear_preset_reference_tab_route_properties(widget: QObject) -> None:
    for key in (
        "presetReferenceTabRouteKey",
        "presetReferenceTabRouteRole",
        "presetReferenceTabPresetId",
        "presetReferenceTabProfile",
        "presetReferenceTabActiveLabel",
        "presetReferenceTabHomeLabel",
        "presetReferenceTabTabsObject",
        "presetReferenceTabHomeRole",
        "presetReferenceTabReferenceRole",
        "presetReferenceTabActivatedLabelProperty",
        "presetReferenceTabReturnedHomeLabelProperty",
        "presetReferenceTabActiveProperty",
        "presetReferenceTabHomeProperty",
        "presetReferenceTabProfileProperty",
        "presetReferenceTabActivatedLabel",
        "presetReferenceTabReturnedHomeLabel",
        "presetReferenceTabRenderSource",
    ):
        widget.setProperty(key, None)


def apply_preset_reference_tab_chrome_route_properties(widget: QObject, route: GuiPresetReferenceTabChromeRoute) -> None:
    properties = {
        "presetReferenceTabChromeRouteKey": route.key,
        "presetReferenceTabChromeRouteRole": route.route_role,
        "presetReferenceTabChromePresetId": route.preset_id,
        "presetReferenceTabChromeProfile": route.reference_profile,
        "presetReferenceTabChromeActiveLabel": route.active_tab_label,
        "presetReferenceTabChromeHomeLabel": route.home_tab_label,
        "presetReferenceTabChromeTabsObject": route.tabs_object,
        "presetReferenceTabChromeTabBarObject": route.tab_bar_object,
        "presetReferenceTabChromeReferenceRole": route.reference_tab_role,
        "presetReferenceTabChromeNewSessionRole": route.new_session_tab_role,
        "presetReferenceTabChromeExpectedPosition": route.expected_tab_position,
        "presetReferenceTabChromeExpectedTooltip": route.expected_tooltip,
        "presetReferenceTabChromeExpectedCloseable": route.expected_closeable,
        "presetReferenceTabChromeExpectedSelectedDuringCapture": route.expected_selected_during_capture,
        "presetReferenceTabChromeCapturedProperty": route.captured_property,
        "presetReferenceTabChromeCapturedLabelProperty": route.captured_label_property,
        "presetReferenceTabChromeCapturedTooltipProperty": route.captured_tooltip_property,
        "presetReferenceTabChromeCapturedIndexProperty": route.captured_index_property,
        "presetReferenceTabChromeCapturedRoleProperty": route.captured_role_property,
        "presetReferenceTabChromeCapturedPositionProperty": route.captured_position_property,
        "presetReferenceTabChromeCapturedCloseableProperty": route.captured_closeable_property,
        "presetReferenceTabChromeCapturedSelectedProperty": route.captured_selected_property,
        "presetReferenceTabChromeRenderSource": route.render_source,
    }
    for key, value in properties.items():
        widget.setProperty(key, value)


def clear_preset_reference_tab_chrome_route_properties(widget: QObject) -> None:
    for key in (
        "presetReferenceTabChromeRouteKey",
        "presetReferenceTabChromeRouteRole",
        "presetReferenceTabChromePresetId",
        "presetReferenceTabChromeProfile",
        "presetReferenceTabChromeActiveLabel",
        "presetReferenceTabChromeHomeLabel",
        "presetReferenceTabChromeTabsObject",
        "presetReferenceTabChromeTabBarObject",
        "presetReferenceTabChromeReferenceRole",
        "presetReferenceTabChromeNewSessionRole",
        "presetReferenceTabChromeExpectedPosition",
        "presetReferenceTabChromeExpectedTooltip",
        "presetReferenceTabChromeExpectedCloseable",
        "presetReferenceTabChromeExpectedSelectedDuringCapture",
        "presetReferenceTabChromeCapturedProperty",
        "presetReferenceTabChromeCapturedLabelProperty",
        "presetReferenceTabChromeCapturedTooltipProperty",
        "presetReferenceTabChromeCapturedIndexProperty",
        "presetReferenceTabChromeCapturedRoleProperty",
        "presetReferenceTabChromeCapturedPositionProperty",
        "presetReferenceTabChromeCapturedCloseableProperty",
        "presetReferenceTabChromeCapturedSelectedProperty",
        "presetReferenceTabChromeCaptured",
        "presetReferenceTabChromeLabel",
        "presetReferenceTabChromeTooltip",
        "presetReferenceTabChromeIndex",
        "presetReferenceTabChromeRole",
        "presetReferenceTabChromePosition",
        "presetReferenceTabChromeCloseable",
        "presetReferenceTabChromeSelected",
        "presetReferenceTabChromeRenderSource",
    ):
        widget.setProperty(key, None)


def apply_preset_reference_status_bar_route_properties(widget: QObject, route: GuiPresetReferenceStatusBarRoute) -> None:
    properties = {
        "presetReferenceStatusRouteKey": route.key,
        "presetReferenceStatusRouteRole": route.route_role,
        "presetReferenceStatusPresetId": route.preset_id,
        "presetReferenceStatusProfile": route.reference_profile,
        "presetReferenceStatusActiveTab": route.active_tab_label,
        "presetReferenceStatusBarObject": route.status_bar_object,
        "presetReferenceStatusNoticeObject": route.status_notice_object,
        "presetReferenceStatusSegmentObject": route.status_segment_object,
        "presetReferenceStatusExpectedMessage": route.expected_status_message,
        "presetReferenceStatusExpectedSegments": list(route.expected_status_segments),
        "presetReferenceStatusExpectedSegmentCount": route.expected_segment_count,
        "presetReferenceStatusCapturedProperty": route.captured_property,
        "presetReferenceStatusCapturedTabProperty": route.captured_tab_property,
        "presetReferenceStatusCapturedMessageProperty": route.captured_message_property,
        "presetReferenceStatusCapturedSegmentsProperty": route.captured_segments_property,
        "presetReferenceStatusCapturedSegmentCountProperty": route.captured_segment_count_property,
        "presetReferenceStatusCapturedSegmentTooltipsProperty": route.captured_segment_tooltips_property,
        "presetReferenceStatusCapturedNoticeProperty": route.captured_notice_property,
        "presetReferenceStatusRenderSource": route.render_source,
    }
    for key, value in properties.items():
        widget.setProperty(key, value)


def clear_preset_reference_status_bar_route_properties(widget: QObject) -> None:
    for key in (
        "presetReferenceStatusRouteKey",
        "presetReferenceStatusRouteRole",
        "presetReferenceStatusPresetId",
        "presetReferenceStatusProfile",
        "presetReferenceStatusActiveTab",
        "presetReferenceStatusBarObject",
        "presetReferenceStatusNoticeObject",
        "presetReferenceStatusSegmentObject",
        "presetReferenceStatusExpectedMessage",
        "presetReferenceStatusExpectedSegments",
        "presetReferenceStatusExpectedSegmentCount",
        "presetReferenceStatusCapturedProperty",
        "presetReferenceStatusCapturedTabProperty",
        "presetReferenceStatusCapturedMessageProperty",
        "presetReferenceStatusCapturedSegmentsProperty",
        "presetReferenceStatusCapturedSegmentCountProperty",
        "presetReferenceStatusCapturedSegmentTooltipsProperty",
        "presetReferenceStatusCapturedNoticeProperty",
        "presetReferenceStatusCaptured",
        "presetReferenceStatusCapturedTab",
        "presetReferenceStatusMessage",
        "presetReferenceStatusSegments",
        "presetReferenceStatusSegmentCount",
        "presetReferenceStatusSegmentTooltips",
        "presetReferenceStatusNotice",
        "presetReferenceStatusRenderSource",
    ):
        widget.setProperty(key, None)


def apply_preset_reference_session_action_route_properties(widget: QObject, route: GuiPresetReferenceSessionActionRoute) -> None:
    properties = {
        "presetReferenceSessionActionRouteKey": route.key,
        "presetReferenceSessionActionRouteRole": route.route_role,
        "presetReferenceSessionActionPresetId": route.preset_id,
        "presetReferenceSessionActionProfile": route.reference_profile,
        "presetReferenceSessionActionActiveTab": route.active_tab_label,
        "presetReferenceSessionActionTabsObject": route.tabs_object,
        "presetReferenceSessionActionTabBarObject": route.tab_bar_object,
        "presetReferenceSessionActionReferenceRole": route.reference_tab_role,
        "presetReferenceSessionActionObject": route.action_object,
        "presetReferenceSessionActionExpectedKeys": list(route.expected_action_keys),
        "presetReferenceSessionActionExpectedLabels": list(route.expected_action_labels),
        "presetReferenceSessionActionExpectedCount": route.expected_action_count,
        "presetReferenceSessionActionAlwaysEnabledKeys": list(route.always_enabled_action_keys),
        "presetReferenceSessionActionConditionalEnabledKeys": list(route.conditional_enabled_action_keys),
        "presetReferenceSessionActionActionKeyProperty": route.action_key_property,
        "presetReferenceSessionActionActionLabelProperty": route.action_label_property,
        "presetReferenceSessionActionActionEnabledProperty": route.action_enabled_property,
        "presetReferenceSessionActionCapturedProperty": route.captured_property,
        "presetReferenceSessionActionCapturedTabProperty": route.captured_tab_property,
        "presetReferenceSessionActionCapturedKeysProperty": route.captured_action_keys_property,
        "presetReferenceSessionActionCapturedLabelsProperty": route.captured_action_labels_property,
        "presetReferenceSessionActionCapturedCountProperty": route.captured_action_count_property,
        "presetReferenceSessionActionCapturedEnabledKeysProperty": route.captured_enabled_keys_property,
        "presetReferenceSessionActionCapturedDisabledKeysProperty": route.captured_disabled_keys_property,
        "presetReferenceSessionActionRenderSource": route.render_source,
    }
    for key, value in properties.items():
        widget.setProperty(key, value)


def clear_preset_reference_session_action_route_properties(widget: QObject) -> None:
    for key in (
        "presetReferenceSessionActionRouteKey",
        "presetReferenceSessionActionRouteRole",
        "presetReferenceSessionActionPresetId",
        "presetReferenceSessionActionProfile",
        "presetReferenceSessionActionActiveTab",
        "presetReferenceSessionActionTabsObject",
        "presetReferenceSessionActionTabBarObject",
        "presetReferenceSessionActionReferenceRole",
        "presetReferenceSessionActionObject",
        "presetReferenceSessionActionExpectedKeys",
        "presetReferenceSessionActionExpectedLabels",
        "presetReferenceSessionActionExpectedCount",
        "presetReferenceSessionActionAlwaysEnabledKeys",
        "presetReferenceSessionActionConditionalEnabledKeys",
        "presetReferenceSessionActionActionKeyProperty",
        "presetReferenceSessionActionActionLabelProperty",
        "presetReferenceSessionActionActionEnabledProperty",
        "presetReferenceSessionActionCapturedProperty",
        "presetReferenceSessionActionCapturedTabProperty",
        "presetReferenceSessionActionCapturedKeysProperty",
        "presetReferenceSessionActionCapturedLabelsProperty",
        "presetReferenceSessionActionCapturedCountProperty",
        "presetReferenceSessionActionCapturedEnabledKeysProperty",
        "presetReferenceSessionActionCapturedDisabledKeysProperty",
        "presetReferenceSessionActionsCaptured",
        "presetReferenceSessionActionsCapturedTab",
        "presetReferenceSessionActionKeys",
        "presetReferenceSessionActionLabels",
        "presetReferenceSessionActionCount",
        "presetReferenceSessionActionEnabledKeys",
        "presetReferenceSessionActionDisabledKeys",
        "presetReferenceSessionActionRenderSource",
    ):
        widget.setProperty(key, None)


def apply_moba_connected_session_action_route_properties(widget: QObject, route: MobaConnectedSessionActionRoute) -> None:
    properties = {
        "mobaConnectedSessionActionRouteKey": route.key,
        "mobaConnectedSessionActionRouteRole": route.route_role,
        "mobaConnectedSessionActionProfile": route.profile_name,
        "mobaConnectedSessionActionTarget": route.target,
        "mobaConnectedSessionActionActiveTabKey": route.active_tab_key,
        "mobaConnectedSessionActionActiveTab": route.active_tab_label,
        "mobaConnectedSessionActionReferenceTab": route.reference_tab_label,
        "mobaConnectedSessionActionTabsObject": route.tabs_object,
        "mobaConnectedSessionActionTabBarObject": route.tab_bar_object,
        "mobaConnectedSessionActionReferenceRole": route.reference_tab_role,
        "mobaConnectedSessionActionMenuObject": route.menu_object,
        "mobaConnectedSessionActionObject": route.action_object,
        "mobaConnectedSessionActionExpectedKeys": list(route.expected_action_keys),
        "mobaConnectedSessionActionExpectedLabels": list(route.expected_action_labels),
        "mobaConnectedSessionActionExpectedCount": route.expected_action_count,
        "mobaConnectedSessionActionAlwaysEnabledKeys": list(route.always_enabled_action_keys),
        "mobaConnectedSessionActionConditionalEnabledKeys": list(route.conditional_enabled_action_keys),
        "mobaConnectedSessionActionActionKeyProperty": route.action_key_property,
        "mobaConnectedSessionActionActionLabelProperty": route.action_label_property,
        "mobaConnectedSessionActionActionEnabledProperty": route.action_enabled_property,
        "mobaConnectedSessionActionCapturedProperty": route.captured_property,
        "mobaConnectedSessionActionCapturedTabProperty": route.captured_tab_property,
        "mobaConnectedSessionActionCapturedKeysProperty": route.captured_action_keys_property,
        "mobaConnectedSessionActionCapturedLabelsProperty": route.captured_action_labels_property,
        "mobaConnectedSessionActionCapturedCountProperty": route.captured_action_count_property,
        "mobaConnectedSessionActionCapturedEnabledKeysProperty": route.captured_enabled_keys_property,
        "mobaConnectedSessionActionCapturedDisabledKeysProperty": route.captured_disabled_keys_property,
        "mobaConnectedSessionActionRenderSource": route.render_source,
    }
    for key, value in properties.items():
        widget.setProperty(key, value)


def apply_preset_reference_surface_route_properties(widget: QObject, route: GuiPresetReferenceSurfaceRoute) -> None:
    properties = {
        "presetReferenceSurfaceRouteKey": route.key,
        "presetReferenceSurfaceRouteRole": route.route_role,
        "presetReferenceSurfacePresetId": route.preset_id,
        "presetReferenceSurfaceProfile": route.reference_profile,
        "presetReferenceSurfaceActiveTab": route.active_tab_label,
        "presetReferenceSurfaceExpectedTitle": route.expected_title,
        "presetReferenceSurfaceExpectedSource": route.expected_source,
        "presetReferenceSurfaceCommandExecutables": list(route.command_executables),
        "presetReferenceSurfaceCommandExecutableChoices": "|".join(route.command_executables),
        "presetReferenceSurfaceCommandTargetFragment": route.command_target_fragment,
        "presetReferenceSurfaceTerminalPaneObject": route.terminal_pane_object,
        "presetReferenceSurfaceTitleObject": route.terminal_title_object,
        "presetReferenceSurfaceSourceObject": route.terminal_source_object,
        "presetReferenceSurfaceCommandObject": route.terminal_command_object,
        "presetReferenceSurfaceOutputObject": route.terminal_output_object,
        "presetReferenceSurfaceCapturedProperty": route.captured_property,
        "presetReferenceSurfaceCapturedTabProperty": route.captured_tab_property,
        "presetReferenceSurfaceActualTitleProperty": route.actual_title_property,
        "presetReferenceSurfaceActualSourceProperty": route.actual_source_property,
        "presetReferenceSurfaceActualCommandProperty": route.actual_command_property,
        "presetReferenceSurfaceActualOutputProperty": route.actual_output_property,
        "presetReferenceSurfaceRenderSource": route.render_source,
    }
    for key, value in properties.items():
        widget.setProperty(key, value)


def clear_preset_reference_surface_route_properties(widget: QObject) -> None:
    for key in (
        "presetReferenceSurfaceRouteKey",
        "presetReferenceSurfaceRouteRole",
        "presetReferenceSurfacePresetId",
        "presetReferenceSurfaceProfile",
        "presetReferenceSurfaceActiveTab",
        "presetReferenceSurfaceExpectedTitle",
        "presetReferenceSurfaceExpectedSource",
        "presetReferenceSurfaceCommandExecutables",
        "presetReferenceSurfaceCommandExecutableChoices",
        "presetReferenceSurfaceCommandTargetFragment",
        "presetReferenceSurfaceTerminalPaneObject",
        "presetReferenceSurfaceTitleObject",
        "presetReferenceSurfaceSourceObject",
        "presetReferenceSurfaceCommandObject",
        "presetReferenceSurfaceOutputObject",
        "presetReferenceSurfaceCapturedProperty",
        "presetReferenceSurfaceCapturedTabProperty",
        "presetReferenceSurfaceActualTitleProperty",
        "presetReferenceSurfaceActualSourceProperty",
        "presetReferenceSurfaceActualCommandProperty",
        "presetReferenceSurfaceActualOutputProperty",
        "presetReferenceSurfaceCaptured",
        "presetReferenceSurfaceCapturedTab",
        "presetReferenceSurfaceActualTitle",
        "presetReferenceSurfaceActualSource",
        "presetReferenceSurfaceActualCommand",
        "presetReferenceSurfaceActualOutput",
        "presetReferenceSurfaceRenderSource",
    ):
        widget.setProperty(key, None)


def apply_preset_reference_control_route_properties(widget: QObject, route: GuiPresetReferenceControlRoute) -> None:
    properties = {
        "presetReferenceControlRouteKey": route.key,
        "presetReferenceControlRouteRole": route.route_role,
        "presetReferenceControlPresetId": route.preset_id,
        "presetReferenceControlProfile": route.reference_profile,
        "presetReferenceControlActiveTab": route.active_tab_label,
        "presetReferenceControlTerminalPaneObject": route.terminal_pane_object,
        "presetReferenceControlStatusObject": route.terminal_status_object,
        "presetReferenceControlActionObject": route.terminal_action_object,
        "presetReferenceControlActionKeys": list(route.action_keys),
        "presetReferenceControlActionLabels": list(route.action_labels),
        "presetReferenceControlActionTooltips": list(route.action_tooltips),
        "presetReferenceControlAllowedStatusStates": list(route.allowed_status_states),
        "presetReferenceControlActionKeyProperty": route.action_key_property,
        "presetReferenceControlActionLabelProperty": route.action_label_property,
        "presetReferenceControlActionTooltipProperty": route.action_tooltip_property,
        "presetReferenceControlStatusStateProperty": route.status_state_property,
        "presetReferenceControlCapturedProperty": route.captured_property,
        "presetReferenceControlCapturedActionsProperty": route.captured_actions_property,
        "presetReferenceControlCapturedStatusProperty": route.captured_status_property,
        "presetReferenceControlCapturedStatusTextProperty": route.captured_status_text_property,
        "presetReferenceControlRenderSource": route.render_source,
    }
    for key, value in properties.items():
        widget.setProperty(key, value)


def clear_preset_reference_control_route_properties(widget: QObject) -> None:
    for key in (
        "presetReferenceControlRouteKey",
        "presetReferenceControlRouteRole",
        "presetReferenceControlPresetId",
        "presetReferenceControlProfile",
        "presetReferenceControlActiveTab",
        "presetReferenceControlTerminalPaneObject",
        "presetReferenceControlStatusObject",
        "presetReferenceControlActionObject",
        "presetReferenceControlActionKeys",
        "presetReferenceControlActionLabels",
        "presetReferenceControlActionTooltips",
        "presetReferenceControlAllowedStatusStates",
        "presetReferenceControlActionKeyProperty",
        "presetReferenceControlActionLabelProperty",
        "presetReferenceControlActionTooltipProperty",
        "presetReferenceControlStatusStateProperty",
        "presetReferenceControlCapturedProperty",
        "presetReferenceControlCapturedActionsProperty",
        "presetReferenceControlCapturedStatusProperty",
        "presetReferenceControlCapturedStatusTextProperty",
        "presetReferenceControlsCaptured",
        "presetReferenceControlCapturedActionKeys",
        "presetReferenceControlStatusState",
        "presetReferenceControlStatusText",
        "presetReferenceControlRenderSource",
    ):
        widget.setProperty(key, None)


def apply_preset_reference_input_route_properties(widget: QObject, route: GuiPresetReferenceInputRoute) -> None:
    properties = {
        "presetReferenceInputRouteKey": route.key,
        "presetReferenceInputRouteRole": route.route_role,
        "presetReferenceInputPresetId": route.preset_id,
        "presetReferenceInputProfile": route.reference_profile,
        "presetReferenceInputActiveTab": route.active_tab_label,
        "presetReferenceInputTerminalPaneObject": route.terminal_pane_object,
        "presetReferenceInputObject": route.terminal_input_object,
        "presetReferenceInputExpectedPlaceholder": route.placeholder_text,
        "presetReferenceInputExpectedInitialText": route.expected_initial_text,
        "presetReferenceInputAllowedEnabledStates": list(route.allowed_enabled_states),
        "presetReferenceInputCapturedProperty": route.captured_property,
        "presetReferenceInputCapturedTabProperty": route.captured_tab_property,
        "presetReferenceInputCapturedPlaceholderProperty": route.captured_placeholder_property,
        "presetReferenceInputCapturedTextProperty": route.captured_text_property,
        "presetReferenceInputCapturedEnabledProperty": route.captured_enabled_property,
        "presetReferenceInputRenderSource": route.render_source,
    }
    for key, value in properties.items():
        widget.setProperty(key, value)


def clear_preset_reference_input_route_properties(widget: QObject) -> None:
    for key in (
        "presetReferenceInputRouteKey",
        "presetReferenceInputRouteRole",
        "presetReferenceInputPresetId",
        "presetReferenceInputProfile",
        "presetReferenceInputActiveTab",
        "presetReferenceInputTerminalPaneObject",
        "presetReferenceInputObject",
        "presetReferenceInputExpectedPlaceholder",
        "presetReferenceInputExpectedInitialText",
        "presetReferenceInputAllowedEnabledStates",
        "presetReferenceInputCapturedProperty",
        "presetReferenceInputCapturedTabProperty",
        "presetReferenceInputCapturedPlaceholderProperty",
        "presetReferenceInputCapturedTextProperty",
        "presetReferenceInputCapturedEnabledProperty",
        "presetReferenceInputCaptured",
        "presetReferenceInputCapturedTab",
        "presetReferenceInputPlaceholder",
        "presetReferenceInputText",
        "presetReferenceInputEnabled",
        "presetReferenceInputRenderSource",
    ):
        widget.setProperty(key, None)


def apply_preset_reference_transcript_route_properties(widget: QObject, route: GuiPresetReferenceTranscriptRoute) -> None:
    properties = {
        "presetReferenceTranscriptRouteKey": route.key,
        "presetReferenceTranscriptRouteRole": route.route_role,
        "presetReferenceTranscriptPresetId": route.preset_id,
        "presetReferenceTranscriptProfile": route.reference_profile,
        "presetReferenceTranscriptActiveTab": route.active_tab_label,
        "presetReferenceTranscriptTerminalPaneObject": route.terminal_pane_object,
        "presetReferenceTranscriptOutputObject": route.terminal_output_object,
        "presetReferenceTranscriptCommandEchoPrefix": route.command_echo_prefix,
        "presetReferenceTranscriptRequiredFragments": list(route.required_fragments),
        "presetReferenceTranscriptMinimumLineCount": route.minimum_line_count,
        "presetReferenceTranscriptCapturedProperty": route.captured_property,
        "presetReferenceTranscriptCapturedTabProperty": route.captured_tab_property,
        "presetReferenceTranscriptCapturedTextProperty": route.captured_text_property,
        "presetReferenceTranscriptCapturedLineCountProperty": route.captured_line_count_property,
        "presetReferenceTranscriptCapturedCommandEchoProperty": route.captured_command_echo_property,
        "presetReferenceTranscriptRenderSource": route.render_source,
    }
    for key, value in properties.items():
        widget.setProperty(key, value)


def clear_preset_reference_transcript_route_properties(widget: QObject) -> None:
    for key in (
        "presetReferenceTranscriptRouteKey",
        "presetReferenceTranscriptRouteRole",
        "presetReferenceTranscriptPresetId",
        "presetReferenceTranscriptProfile",
        "presetReferenceTranscriptActiveTab",
        "presetReferenceTranscriptTerminalPaneObject",
        "presetReferenceTranscriptOutputObject",
        "presetReferenceTranscriptCommandEchoPrefix",
        "presetReferenceTranscriptRequiredFragments",
        "presetReferenceTranscriptMinimumLineCount",
        "presetReferenceTranscriptCapturedProperty",
        "presetReferenceTranscriptCapturedTabProperty",
        "presetReferenceTranscriptCapturedTextProperty",
        "presetReferenceTranscriptCapturedLineCountProperty",
        "presetReferenceTranscriptCapturedCommandEchoProperty",
        "presetReferenceTranscriptCaptured",
        "presetReferenceTranscriptCapturedTab",
        "presetReferenceTranscriptText",
        "presetReferenceTranscriptLineCount",
        "presetReferenceTranscriptCommandEcho",
        "presetReferenceTranscriptRenderSource",
    ):
        widget.setProperty(key, None)


def apply_preset_visual_signature_properties(widget: QObject, signature: GuiPresetVisualSignature) -> None:
    properties = {
        "presetVisualSignatureKey": signature.key,
        "presetVisualSignatureRole": signature.route_role,
        "presetVisualSignaturePresetId": signature.preset_id,
        "presetVisualSignaturePresetLabel": signature.preset_label,
        "presetVisualSignatureDensity": signature.density,
        "presetVisualSignatureTabPosition": signature.tab_position,
        "presetVisualSignatureDocumentMode": signature.document_mode,
        "presetVisualSignatureProfileWidth": signature.profile_width,
        "presetVisualSignatureLogHeight": signature.log_height,
        "presetVisualSignatureToolbarIconSize": signature.toolbar_icon_size,
        "presetVisualSignatureListSpacing": signature.list_spacing,
        "presetVisualSignaturePalette": dict(signature.palette_items()),
        "presetVisualSignatureWindowObject": signature.window_object,
        "presetVisualSignatureMainToolbarObject": signature.main_toolbar_object,
        "presetVisualSignatureLayoutToolbarObject": signature.layout_toolbar_object,
        "presetVisualSignatureLeftPanelObject": signature.left_panel_object,
        "presetVisualSignatureProfileTreeObject": signature.profile_tree_object,
        "presetVisualSignatureTabsObject": signature.tabs_object,
        "presetVisualSignatureActivityLogObject": signature.activity_log_object,
        "presetVisualSignatureStatusBarObject": signature.status_bar_object,
        "presetVisualSignatureDensityProperty": signature.density_property,
        "presetVisualSignaturePaletteProperty": signature.palette_property,
        "presetVisualSignatureRenderSource": signature.render_source,
    }
    for key, value in properties.items():
        widget.setProperty(key, value)

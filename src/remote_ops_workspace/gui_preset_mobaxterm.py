"""Design data for the MobaXterm workspace preset."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class GuiMobaRibbonAction:
    icon_key: str
    label: str
    color: str


@dataclass(frozen=True)
class GuiMobaRibbonEdgeAction:
    key: str
    label: str
    icon_key: str
    color: str
    tooltip: str


@dataclass(frozen=True)
class GuiMobaRibbonEdgeActionRoute:
    key: str
    route_role: str
    toolbar_object: str
    spacer_object: str
    xserver_action_key: str
    xserver_action_label: str
    xserver_action_object: str
    xserver_icon_key: str
    xserver_handler: str
    xserver_dialog_title: str
    xserver_dialog_detail: str
    exit_action_key: str
    exit_action_label: str
    exit_action_object: str
    exit_icon_key: str
    exit_handler: str
    route_key_property: str
    action_key_property: str
    action_label_property: str
    action_object_property: str
    icon_key_property: str
    handler_property: str
    action_keys_property: str
    render_source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "route_role": self.route_role,
            "toolbar_object": self.toolbar_object,
            "spacer_object": self.spacer_object,
            "xserver_action_key": self.xserver_action_key,
            "xserver_action_label": self.xserver_action_label,
            "xserver_action_object": self.xserver_action_object,
            "xserver_icon_key": self.xserver_icon_key,
            "xserver_handler": self.xserver_handler,
            "xserver_dialog_title": self.xserver_dialog_title,
            "xserver_dialog_detail": self.xserver_dialog_detail,
            "exit_action_key": self.exit_action_key,
            "exit_action_label": self.exit_action_label,
            "exit_action_object": self.exit_action_object,
            "exit_icon_key": self.exit_icon_key,
            "exit_handler": self.exit_handler,
            "route_key_property": self.route_key_property,
            "action_key_property": self.action_key_property,
            "action_label_property": self.action_label_property,
            "action_object_property": self.action_object_property,
            "icon_key_property": self.icon_key_property,
            "handler_property": self.handler_property,
            "action_keys_property": self.action_keys_property,
            "render_source": self.render_source,
        }


@dataclass(frozen=True)
class GuiMobaRibbonActionGeometry:
    key: str
    static_x: int
    width: int
    icon_x: int
    icon_y: int
    icon_size: int
    label_x: int
    label_y: int
    label_font_size: int
    separator_before: bool
    separator_x: int
    separator_top: int
    separator_bottom: int
    active_outline_x: int
    active_outline_y: int
    active_outline_width: int
    active_outline_height: int

    def to_dict(self) -> dict[str, int | str | bool]:
        return {
            "key": self.key,
            "static_x": self.static_x,
            "width": self.width,
            "icon_x": self.icon_x,
            "icon_y": self.icon_y,
            "icon_size": self.icon_size,
            "label_x": self.label_x,
            "label_y": self.label_y,
            "label_font_size": self.label_font_size,
            "separator_before": self.separator_before,
            "separator_x": self.separator_x,
            "separator_top": self.separator_top,
            "separator_bottom": self.separator_bottom,
            "active_outline_x": self.active_outline_x,
            "active_outline_y": self.active_outline_y,
            "active_outline_width": self.active_outline_width,
            "active_outline_height": self.active_outline_height,
        }


@dataclass(frozen=True)
class GuiMobaTopMenuItem:
    key: str
    label: str
    primary_action: str
    tooltip: str


@dataclass(frozen=True)
class GuiMobaTopMenuGeometry:
    key: str
    static_x: int
    width: int
    label_y: int
    label_font_size: int
    gap_after: int

    def to_dict(self) -> dict[str, int | str]:
        return {
            "key": self.key,
            "static_x": self.static_x,
            "width": self.width,
            "label_y": self.label_y,
            "label_font_size": self.label_font_size,
            "gap_after": self.gap_after,
        }


@dataclass(frozen=True)
class GuiMobaTitlebarChrome:
    icon_key: str
    static_height: int
    icon_left: int
    icon_size: int
    title_left: int
    control_keys: tuple[str, ...]
    control_width: int
    control_right_inset: int


@dataclass(frozen=True)
class GuiMobaQuickConnectChrome:
    placeholder: str
    dropdown_marker: str
    static_height: int
    marker_width: int
    input_left: int
    input_padding: str
    connected_idle_query: str
    connected_suggestions_visible: bool


@dataclass(frozen=True)
class GuiMobaTopStackGeometry:
    titlebar_height: int
    menu_y: int
    menu_height: int
    ribbon_y: int
    ribbon_height: int
    quick_connect_y: int
    quick_connect_height: int
    left_dock_y: int
    tab_y: int
    tab_height: int
    terminal_content_y: int
    status_height: int
    side_width: int
    rail_width: int


@dataclass(frozen=True)
class GuiMobaQuickConnectSuggestionChrome:
    preview_query: str
    expected_kinds: tuple[str, ...]
    max_visible_rows: int
    row_height: int
    static_width: int
    detail_separator: str


@dataclass(frozen=True)
class GuiMobaHomeWelcomeChrome:
    title: str
    subtitle: str
    icon_key: str
    primary_action_icon_key: str
    secondary_action_icon_key: str
    search_width: int
    action_spacing: int
    recent_title: str
    surface_width: int


@dataclass(frozen=True)
class GuiMobaHomeWelcomeGeometry:
    center_side_margin: int
    hero_min_y: int
    hero_height: int
    logo_size: int
    logo_inner_padding: int
    logo_icon_size: int
    logo_cluster_width: int
    title_gap: int
    title_y_offset: int
    title_font_size: int
    subtitle_y_offset: int
    subtitle_font_size: int
    button_y_offset: int
    primary_width: int
    secondary_width: int
    action_gap: int
    button_height: int
    button_icon_x: int
    button_icon_y: int
    button_icon_size: int
    button_label_x: int
    button_label_y: int
    button_font_size: int
    search_y_gap: int
    search_height: int
    search_text_x: int
    search_text_y: int
    search_font_size: int
    recent_y_gap: int
    recent_title_font_size: int
    recent_item_y_offset: int
    recent_item_step: int
    recent_column_padding: int
    footer_y_offset: int
    footer_font_size: int
    live_max_extra_width: int
    live_layout_spacing: int
    live_title_row_spacing: int
    live_title_column_spacing: int
    live_logo_box_width: int
    live_logo_box_height: int
    live_logo_pixmap_size: int
    live_recent_title_top_margin: int
    live_recent_column_spacing: int
    live_recent_row_spacing: int
    live_footer_top_margin: int
    render_source: str


@dataclass(frozen=True)
class GuiMobaRailItem:
    role: str
    label: str
    object_name: str
    icon_key: str
    rail_icon_key: str
    color: str
    tooltip: str


@dataclass(frozen=True)
class GuiMobaRailChrome:
    rail_width: int
    icon_x: int
    static_icon_size: int
    live_icon_size: int
    generated_icon_size: int
    button_width: int
    button_height: int
    active_x: int
    active_y_offset: int
    active_width: int
    active_height: int
    label_width: int
    label_height: int
    label_step: int
    unlabeled_gap_after: int
    label_font_size: int
    render_source: str


@dataclass(frozen=True)
class GuiMobaRailItemGeometry:
    role: str
    static_icon_y: int
    static_label_y: int


@dataclass(frozen=True)
class GuiMobaRightUtilityAction:
    key: str
    icon_key: str
    label: str
    color: str
    tooltip: str
    static_x: int
    static_y: int
    static_size: int
    live_icon_size: int
    button_size: int
    render_source: str


@dataclass(frozen=True)
class GuiMobaRightUtilityActionRoute:
    key: str
    route_role: str
    rail_object: str
    action_object: str
    action_keys: tuple[str, ...]
    action_labels: tuple[str, ...]
    action_icon_keys: tuple[str, ...]
    action_handlers: tuple[str, ...]
    route_key_property: str
    action_key_property: str
    action_label_property: str
    action_object_property: str
    icon_key_property: str
    handler_property: str
    action_keys_property: str
    render_source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "route_role": self.route_role,
            "rail_object": self.rail_object,
            "action_object": self.action_object,
            "action_keys": list(self.action_keys),
            "action_labels": list(self.action_labels),
            "action_icon_keys": list(self.action_icon_keys),
            "action_handlers": list(self.action_handlers),
            "route_key_property": self.route_key_property,
            "action_key_property": self.action_key_property,
            "action_label_property": self.action_label_property,
            "action_object_property": self.action_object_property,
            "icon_key_property": self.icon_key_property,
            "handler_property": self.handler_property,
            "action_keys_property": self.action_keys_property,
            "render_source": self.render_source,
        }


@dataclass(frozen=True)
class GuiMobaRightUtilityRailChrome:
    static_width: int
    live_width: int
    margin_left: int
    margin_top: int
    margin_right: int
    margin_bottom: int
    action_spacing: int
    session_edge_top_y: int
    session_edge_height: int
    session_edge_icon_x: int
    session_edge_icon_size: int


@dataclass(frozen=True)
class GuiMobaSessionEdgeAction:
    key: str
    icon_key: str
    label: str
    color: str
    tooltip: str
    static_y: int
    static_size: int
    live_icon_size: int
    button_size: int
    render_source: str

    def relative_y(self, top_y: int) -> int:
        return self.static_y - top_y


@dataclass(frozen=True)
class GuiMobaSessionEdgeActionRoute:
    key: str
    route_role: str
    controls_object: str
    action_object: str
    placement: str
    action_keys: tuple[str, ...]
    action_labels: tuple[str, ...]
    action_icon_keys: tuple[str, ...]
    action_handlers: tuple[str, ...]
    route_key_property: str
    action_key_property: str
    action_label_property: str
    action_object_property: str
    icon_key_property: str
    handler_property: str
    action_keys_property: str
    render_source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "route_role": self.route_role,
            "controls_object": self.controls_object,
            "action_object": self.action_object,
            "placement": self.placement,
            "action_keys": list(self.action_keys),
            "action_labels": list(self.action_labels),
            "action_icon_keys": list(self.action_icon_keys),
            "action_handlers": list(self.action_handlers),
            "route_key_property": self.route_key_property,
            "action_key_property": self.action_key_property,
            "action_label_property": self.action_label_property,
            "action_object_property": self.action_object_property,
            "icon_key_property": self.icon_key_property,
            "handler_property": self.handler_property,
            "action_keys_property": self.action_keys_property,
            "render_source": self.render_source,
        }


@dataclass(frozen=True)
class GuiMobaSftpDockAction:
    key: str
    icon_key: str
    label: str
    color: str
    tooltip: str
    group_key: str = "file"
    separator_after: bool = False


@dataclass(frozen=True)
class GuiMobaSftpToolbarActionGeometry:
    key: str
    button_x: int
    button_y: int
    button_size: int
    icon_x: int
    icon_y: int
    icon_size: int
    separator_after: bool
    separator_x: int


@dataclass(frozen=True)
class GuiMobaSftpToolbarActionRoute:
    key: str
    route_role: str
    toolbar_object: str
    action_object: str
    target_browser_object: str
    target_path_object: str
    target_table_object: str
    queue_object: str
    action_keys: tuple[str, ...]
    action_labels: tuple[str, ...]
    action_icon_keys: tuple[str, ...]
    action_group_keys: tuple[str, ...]
    action_tooltips: tuple[str, ...]
    action_handlers: tuple[str, ...]
    action_statuses: tuple[str, ...]
    signal: str
    route_key_property: str
    action_key_property: str
    action_label_property: str
    action_object_property: str
    icon_key_property: str
    group_key_property: str
    tooltip_property: str
    signal_property: str
    handler_property: str
    action_keys_property: str
    action_groups_property: str
    captured_property: str
    captured_action_property: str
    captured_status_property: str
    live_triggered_property: str
    live_action_property: str
    live_status_property: str
    render_source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "route_role": self.route_role,
            "toolbar_object": self.toolbar_object,
            "action_object": self.action_object,
            "target_browser_object": self.target_browser_object,
            "target_path_object": self.target_path_object,
            "target_table_object": self.target_table_object,
            "queue_object": self.queue_object,
            "action_keys": list(self.action_keys),
            "action_labels": list(self.action_labels),
            "action_icon_keys": list(self.action_icon_keys),
            "action_group_keys": list(self.action_group_keys),
            "action_tooltips": list(self.action_tooltips),
            "action_handlers": list(self.action_handlers),
            "action_statuses": list(self.action_statuses),
            "signal": self.signal,
            "route_key_property": self.route_key_property,
            "action_key_property": self.action_key_property,
            "action_label_property": self.action_label_property,
            "action_object_property": self.action_object_property,
            "icon_key_property": self.icon_key_property,
            "group_key_property": self.group_key_property,
            "tooltip_property": self.tooltip_property,
            "signal_property": self.signal_property,
            "handler_property": self.handler_property,
            "action_keys_property": self.action_keys_property,
            "action_groups_property": self.action_groups_property,
            "captured_property": self.captured_property,
            "captured_action_property": self.captured_action_property,
            "captured_status_property": self.captured_status_property,
            "live_triggered_property": self.live_triggered_property,
            "live_action_property": self.live_action_property,
            "live_status_property": self.live_status_property,
            "render_source": self.render_source,
        }


@dataclass(frozen=True)
class GuiMobaSftpTableColumn:
    key: str
    label: str
    static_x: int
    static_width: int


@dataclass(frozen=True)
class GuiMobaSftpBrowserChrome:
    path_placeholder: str
    dropdown_marker: str
    parent_row_label: str
    parent_row_kind: str
    selected_row_kind: str
    columns: tuple[GuiMobaSftpTableColumn, ...]
    path_text_x: int
    path_text_y: int
    path_font_size: int
    dropdown_right_offset: int
    dropdown_y: int
    dropdown_font_size: int
    header_label_y: int
    header_font_size: int
    row_top_offset: int
    row_icon_x: int
    row_icon_y_offset: int
    row_name_x: int
    row_size_x: int
    row_modified_x: int
    row_text_y_offset: int
    row_text_font_size: int
    row_modified_font_size: int

    def geometry_dict(self) -> dict[str, int]:
        return {
            "path_text_x": self.path_text_x,
            "path_text_y": self.path_text_y,
            "path_font_size": self.path_font_size,
            "dropdown_right_offset": self.dropdown_right_offset,
            "dropdown_y": self.dropdown_y,
            "dropdown_font_size": self.dropdown_font_size,
            "header_label_y": self.header_label_y,
            "header_font_size": self.header_font_size,
            "row_top_offset": self.row_top_offset,
            "row_icon_x": self.row_icon_x,
            "row_icon_y_offset": self.row_icon_y_offset,
            "row_name_x": self.row_name_x,
            "row_size_x": self.row_size_x,
            "row_modified_x": self.row_modified_x,
            "row_text_y_offset": self.row_text_y_offset,
            "row_text_font_size": self.row_text_font_size,
            "row_modified_font_size": self.row_modified_font_size,
        }


@dataclass(frozen=True)
class GuiMobaSftpFileRowIcon:
    kind: str
    icon_key: str
    row_kind: str
    static_size: int
    render_source: str


@dataclass(frozen=True)
class GuiMobaSftpRoutedFileRows:
    key: str
    route_role: str
    follow_route_key: str
    target_table_object: str
    row_contract_property: str
    row_route_property: str
    row_path_property: str
    row_index_property: str
    row_selected_property: str
    parent_row_name: str
    selected_row_kind: str
    render_source: str


@dataclass(frozen=True)
class GuiMobaSftpDockLayout:
    inner_margin: int
    toolbar_height: int
    toolbar_icon_size: int
    toolbar_icon_left_inset: int
    toolbar_icon_step: int
    toolbar_separator_width: int
    path_gap: int
    path_height: int
    table_header_gap: int
    table_header_height: int
    file_row_gap: int
    file_row_height: int
    static_max_rows: int
    monitoring_height: int
    monitoring_divider_offset: int
    monitoring_left_inset: int
    monitoring_content_left: int
    monitoring_icon_center_x: int
    monitoring_metric_row_gap: int


@dataclass(frozen=True)
class GuiMobaConnectedDockFrame:
    side_width: int
    rail_width: int
    dock_x: int
    dock_y: int
    dock_width: int
    dock_height: int
    workspace_x: int
    quick_connect_y: int
    quick_connect_height: int
    status_y: int


@dataclass(frozen=True)
class GuiMobaMonitoringMetric:
    key: str
    label: str
    source: str


@dataclass(frozen=True)
class GuiMobaMonitoringControl:
    key: str
    icon_key: str
    label: str
    control_type: str
    checked: bool
    tooltip: str


@dataclass(frozen=True)
class GuiMobaMonitoringControlGeometry:
    key: str
    anchor_x: int
    static_y: int
    icon_x: int
    icon_size: int
    label_x: int
    label_y_offset: int
    label_font_size: int
    label_bold: bool
    check_size: int
    check_y_offset: int
    checkmark_points: tuple[tuple[int, int], ...]
    row_height: int
    live_width: int


@dataclass(frozen=True)
class GuiMobaRemoteMonitoringDockChrome:
    title_control_key: str
    follow_control_key: str
    telemetry_surface: str
    visible_metric_keys: tuple[str, ...]
    refresh_seconds: int
    compact: bool
    static_height: int
    divider_offset: int
    divider_left_inset: int
    divider_right_inset: int
    content_left: int
    icon_center_x: int
    metric_row_gap: int
    live_controls_width: int


@dataclass(frozen=True)
class GuiMobaMonitoringTelemetryRoute:
    key: str
    route_role: str
    source_panel_object: str
    source_control_key: str
    source_metric_keys: tuple[str, ...]
    visible_dock_metric_keys: tuple[str, ...]
    telemetry_surface: str
    target_bar_object: str
    target_cell_object: str
    target_identity_cell_key: str
    target_metric_cell_keys: tuple[str, ...]
    render_source: str


@dataclass(frozen=True)
class GuiMobaRemoteMonitoringControlRoute:
    key: str
    route_role: str
    source_panel_object: str
    source_control_object: str
    source_control_key: str
    source_control_label: str
    source_control_type: str
    expected_checked: bool
    command_property: str
    refresh_seconds_property: str
    checked_property: str
    telemetry_route_key: str
    telemetry_surface: str
    target_bar_object: str
    target_metric_cell_keys: tuple[str, ...]
    captured_property: str
    captured_checked_property: str
    captured_command_property: str
    captured_refresh_seconds_property: str
    signal: str
    handler: str
    signal_property: str
    handler_property: str
    live_checked_property: str
    render_source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "route_role": self.route_role,
            "source_panel_object": self.source_panel_object,
            "source_control_object": self.source_control_object,
            "source_control_key": self.source_control_key,
            "source_control_label": self.source_control_label,
            "source_control_type": self.source_control_type,
            "expected_checked": self.expected_checked,
            "command_property": self.command_property,
            "refresh_seconds_property": self.refresh_seconds_property,
            "checked_property": self.checked_property,
            "telemetry_route_key": self.telemetry_route_key,
            "telemetry_surface": self.telemetry_surface,
            "target_bar_object": self.target_bar_object,
            "target_metric_cell_keys": list(self.target_metric_cell_keys),
            "captured_property": self.captured_property,
            "captured_checked_property": self.captured_checked_property,
            "captured_command_property": self.captured_command_property,
            "captured_refresh_seconds_property": self.captured_refresh_seconds_property,
            "signal": self.signal,
            "handler": self.handler,
            "signal_property": self.signal_property,
            "handler_property": self.handler_property,
            "live_checked_property": self.live_checked_property,
            "render_source": self.render_source,
        }


@dataclass(frozen=True)
class GuiMobaFollowTerminalFolderControlRoute:
    key: str
    route_role: str
    source_panel_object: str
    source_control_object: str
    source_control_key: str
    source_control_label: str
    source_control_type: str
    expected_checked: bool
    source_path_property: str
    source_plan_property: str
    source_enabled_property: str
    target_browser_object: str
    target_path_object: str
    target_table_object: str
    target_path_property: str
    target_plan_property: str
    target_enabled_property: str
    captured_property: str
    captured_checked_property: str
    captured_path_property: str
    captured_plan_property: str
    signal: str
    handler: str
    signal_property: str
    handler_property: str
    live_checked_property: str
    live_path_property: str
    live_plan_property: str
    render_source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "route_role": self.route_role,
            "source_panel_object": self.source_panel_object,
            "source_control_object": self.source_control_object,
            "source_control_key": self.source_control_key,
            "source_control_label": self.source_control_label,
            "source_control_type": self.source_control_type,
            "expected_checked": self.expected_checked,
            "source_path_property": self.source_path_property,
            "source_plan_property": self.source_plan_property,
            "source_enabled_property": self.source_enabled_property,
            "target_browser_object": self.target_browser_object,
            "target_path_object": self.target_path_object,
            "target_table_object": self.target_table_object,
            "target_path_property": self.target_path_property,
            "target_plan_property": self.target_plan_property,
            "target_enabled_property": self.target_enabled_property,
            "captured_property": self.captured_property,
            "captured_checked_property": self.captured_checked_property,
            "captured_path_property": self.captured_path_property,
            "captured_plan_property": self.captured_plan_property,
            "signal": self.signal,
            "handler": self.handler,
            "signal_property": self.signal_property,
            "handler_property": self.handler_property,
            "live_checked_property": self.live_checked_property,
            "live_path_property": self.live_path_property,
            "live_plan_property": self.live_plan_property,
            "render_source": self.render_source,
        }


@dataclass(frozen=True)
class GuiMobaSftpFollowFolderRoute:
    key: str
    route_role: str
    source_control_key: str
    source_control_object: str
    source_path_property: str
    source_plan_property: str
    source_enabled_property: str
    target_browser_object: str
    target_path_object: str
    target_table_object: str
    target_path_property: str
    target_plan_property: str
    target_enabled_property: str
    render_source: str


@dataclass(frozen=True)
class GuiMobaStatusSegment:
    key: str
    text: str
    tooltip: str


@dataclass(frozen=True)
class GuiMobaStatusBarChrome:
    notice: str
    product_note: str
    right_marker: str
    right_marker_tooltip: str
    static_height: int
    notice_x: int
    notice_y: int
    product_note_x: int
    product_note_y: int
    text_font_size: int
    segment_start_right_offset: int
    marker_right_inset: int
    marker_y: int
    marker_width: int
    marker_height: int


@dataclass(frozen=True)
class GuiMobaBottomEdgeControl:
    key: str
    icon_key: str
    label: str
    color: str
    tooltip: str
    static_x: int


@dataclass(frozen=True)
class GuiMobaSshBannerChrome:
    title: str
    subtitle: str
    heading_prefix: str
    heading_suffix: str
    target_intro: str
    capability_label_width: int
    footer_prefix: str
    help_link_label: str
    website_link_label: str
    static_left_offset: int
    static_top_offset: int
    static_width: int
    static_height: int
    body_top_offset: int
    terminal_gap: int


@dataclass(frozen=True)
class GuiMobaSshBannerRowGeometry:
    key: str
    object_name: str
    static_x: int
    static_y: int
    static_width: int
    static_height: int
    centered: bool = False


@dataclass(frozen=True)
class GuiMobaTerminalTranscriptRowGeometry:
    key: str
    static_x: int
    static_y: int
    row_height: int
    font_size: int


GUI_DESIGN_MOBA_RIBBON_ACTIONS: tuple[GuiMobaRibbonAction, ...] = (
    GuiMobaRibbonAction("session", "Session", "#44a6ff"),
    GuiMobaRibbonAction("servers", "Servers", "#26c6c9"),
    GuiMobaRibbonAction("tools", "Tools", "#e45d3f"),
    GuiMobaRibbonAction("games", "Games", "#f5c242"),
    GuiMobaRibbonAction("sessions", "Sessions", "#f5d000"),
    GuiMobaRibbonAction("view", "View", "#5da7ff"),
    GuiMobaRibbonAction("split", "Split", "#4db6e8"),
    GuiMobaRibbonAction("multiexec", "MultiExec", "#446ee8"),
    GuiMobaRibbonAction("tunneling", "Tunneling", "#55cc7a"),
    GuiMobaRibbonAction("packages", "Packages", "#7587e8"),
    GuiMobaRibbonAction("settings", "Settings", "#4573c4"),
    GuiMobaRibbonAction("help", "Help", "#1c9ef1"),
)


GUI_DESIGN_MOBA_RIBBON_TOOLTIPS: dict[str, str] = {
    "session": "Create a new saved session",
    "servers": "Refresh saved sessions",
    "tools": "Edit selected profile",
    "games": "Show optional tool status",
    "sessions": "Connect selected profile",
    "view": "Cycle to the next visual preset",
    "split": "Open a horizontal split",
    "multiexec": "Preview broadcast command plans for SSH profiles",
    "tunneling": "Show tunneling workflow status",
    "packages": "Show package and file-transfer workflows",
    "settings": "Edit selected profile",
    "help": "Show help and diagnostics workflows",
}


GUI_DESIGN_MOBA_RIBBON_EDGE_ACTIONS: tuple[GuiMobaRibbonEdgeAction, ...] = (
    GuiMobaRibbonEdgeAction("xserver", "X server", "xserver", "#1a1a1a", "Show X server workflow status"),
    GuiMobaRibbonEdgeAction("exit", "Exit", "exit", "#e2473f", "Close Remote Ops Workspace"),
)


GUI_DESIGN_MOBA_RIBBON_EDGE_ACTION_ROUTE = GuiMobaRibbonEdgeActionRoute(
    key="moba-ribbon-edge-action-route",
    route_role="far-right-ribbon-edge-actions-to-workflow-controls",
    toolbar_object="mainToolbar",
    spacer_object="mobaToolbarSpacer",
    xserver_action_key="xserver",
    xserver_action_label="X server",
    xserver_action_object="mobaXServerAction",
    xserver_icon_key="xserver",
    xserver_handler="show_moba_x_server_status",
    xserver_dialog_title="X server",
    xserver_dialog_detail="X server workflow",
    exit_action_key="exit",
    exit_action_label="Exit",
    exit_action_object="mobaExitAction",
    exit_icon_key="exit",
    exit_handler="close",
    route_key_property="mobaRibbonEdgeRouteKey",
    action_key_property="mobaRibbonEdgeRouteActionKey",
    action_label_property="mobaRibbonEdgeRouteActionLabel",
    action_object_property="mobaRibbonEdgeRouteActionObject",
    icon_key_property="mobaRibbonEdgeRouteIconKey",
    handler_property="mobaRibbonEdgeRouteHandler",
    action_keys_property="mobaRibbonEdgeRouteActionKeys",
    render_source="gui-design-moba-ribbon-edge-route",
)


GUI_DESIGN_MOBA_RIBBON_ACTION_GEOMETRY: tuple[GuiMobaRibbonActionGeometry, ...] = (
    GuiMobaRibbonActionGeometry(
        "session", 8, 58, 26, 4, 22, 16, 33, 10, False, 0, 5, 49, 22, 2, 30, 27
    ),
    GuiMobaRibbonActionGeometry(
        "servers", 66, 58, 84, 4, 22, 74, 33, 10, True, 62, 5, 49, 80, 2, 30, 27
    ),
    GuiMobaRibbonActionGeometry(
        "tools", 124, 54, 140, 4, 22, 136, 33, 10, False, 0, 5, 49, 136, 2, 30, 27
    ),
    GuiMobaRibbonActionGeometry(
        "games", 178, 54, 194, 4, 22, 187, 33, 10, False, 0, 5, 49, 190, 2, 30, 27
    ),
    GuiMobaRibbonActionGeometry(
        "sessions", 232, 60, 251, 4, 22, 238, 33, 10, True, 228, 5, 49, 247, 2, 30, 27
    ),
    GuiMobaRibbonActionGeometry(
        "view", 292, 54, 308, 4, 22, 307, 33, 10, False, 0, 5, 49, 304, 2, 30, 27
    ),
    GuiMobaRibbonActionGeometry(
        "split", 346, 54, 362, 4, 22, 358, 33, 10, False, 0, 5, 49, 358, 2, 30, 27
    ),
    GuiMobaRibbonActionGeometry(
        "multiexec", 400, 62, 420, 4, 22, 407, 33, 10, True, 396, 5, 49, 416, 2, 30, 27
    ),
    GuiMobaRibbonActionGeometry(
        "tunneling", 462, 62, 482, 4, 22, 466, 33, 10, False, 0, 5, 49, 478, 2, 30, 27
    ),
    GuiMobaRibbonActionGeometry(
        "packages", 524, 58, 542, 4, 22, 529, 33, 10, False, 0, 5, 49, 538, 2, 30, 27
    ),
    GuiMobaRibbonActionGeometry(
        "settings", 582, 58, 600, 4, 22, 587, 33, 10, True, 578, 5, 49, 596, 2, 30, 27
    ),
    GuiMobaRibbonActionGeometry(
        "help", 640, 54, 656, 4, 22, 655, 33, 10, False, 0, 5, 49, 652, 2, 30, 27
    ),
    GuiMobaRibbonActionGeometry(
        "xserver", 1152, 70, 1173, 4, 26, 1152, 33, 10, True, 1140, 5, 49, 1171, 2, 30, 27
    ),
    GuiMobaRibbonActionGeometry(
        "exit", 1230, 42, 1239, 5, 23, 1230, 33, 10, False, 0, 5, 49, 1235, 2, 30, 27
    ),
)


GUI_DESIGN_MOBA_TOP_MENU_ITEMS: tuple[GuiMobaTopMenuItem, ...] = (
    GuiMobaTopMenuItem(
        "terminal", "Terminal", "Start local terminal", "Local terminal and split-pane commands"
    ),
    GuiMobaTopMenuItem(
        "sessions", "Sessions", "Connect selected", "Saved session and connection commands"
    ),
    GuiMobaTopMenuItem("view", "View", "Refresh sessions", "View preset and refresh commands"),
    GuiMobaTopMenuItem(
        "x-server", "X server", "X server workflow", "External X server workflow status"
    ),
    GuiMobaTopMenuItem("tools", "Tools", "Tools status", "Diagnostics and helper tools"),
    GuiMobaTopMenuItem(
        "games", "Games", "Games status", "Explicit compatibility and support status"
    ),
    GuiMobaTopMenuItem("settings", "Settings", "Settings status", "Workspace settings commands"),
    GuiMobaTopMenuItem("macros", "Macros", "Manage macros…", "Record and replay terminal macros"),
    GuiMobaTopMenuItem("help", "Help", "Run doctor", "Help and doctor commands"),
)


GUI_DESIGN_MOBA_TOP_MENU_GEOMETRY: tuple[GuiMobaTopMenuGeometry, ...] = (
    GuiMobaTopMenuGeometry("terminal", 8, 58, 5, 11, 8),
    GuiMobaTopMenuGeometry("sessions", 66, 60, 5, 11, 8),
    GuiMobaTopMenuGeometry("view", 126, 40, 5, 11, 8),
    GuiMobaTopMenuGeometry("x-server", 166, 60, 5, 11, 8),
    GuiMobaTopMenuGeometry("tools", 226, 44, 5, 11, 8),
    GuiMobaTopMenuGeometry("games", 270, 46, 5, 11, 8),
    GuiMobaTopMenuGeometry("settings", 316, 58, 5, 11, 8),
    GuiMobaTopMenuGeometry("macros", 374, 50, 5, 11, 8),
    GuiMobaTopMenuGeometry("help", 424, 38, 5, 11, 8),
)


GUI_DESIGN_MOBA_RAIL_ITEMS: tuple[GuiMobaRailItem, ...] = (
    GuiMobaRailItem(
        role="collapse",
        label="",
        object_name="mobaRailButton",
        icon_key="session",
        rail_icon_key="collapse",
        color="#44a6ff",
        tooltip="Collapse or restore the sessions panel",
    ),
    GuiMobaRailItem(
        role="sessions",
        label="Sessions",
        object_name="mobaRailButton",
        icon_key="session",
        rail_icon_key="session",
        color="#44a6ff",
        tooltip="Show saved sessions",
    ),
    GuiMobaRailItem(
        role="favorites",
        label="",
        object_name="mobaRailAccent",
        icon_key="sessions",
        rail_icon_key="star",
        color="#f5d000",
        tooltip="Show all saved user sessions",
    ),
    GuiMobaRailItem(
        role="tools",
        label="Tools",
        object_name="mobaRailButton",
        icon_key="tools",
        rail_icon_key="tools",
        color="#e45d3f",
        tooltip="Show tools status",
    ),
    GuiMobaRailItem(
        role="macros",
        label="Macros",
        object_name="mobaRailButton",
        icon_key="multiexec",
        rail_icon_key="macros",
        color="#446ee8",
        tooltip="Manage terminal macro recordings",
    ),
    GuiMobaRailItem(
        role="sftp",
        label="SFTP",
        object_name="mobaRailButton",
        icon_key="packages",
        rail_icon_key="sftp",
        color="#f4a742",
        tooltip="Show connected SFTP browser",
    ),
)


GUI_DESIGN_MOBA_RAIL_CHROME = GuiMobaRailChrome(
    rail_width=28,
    icon_x=6,
    static_icon_size=16,
    live_icon_size=20,
    generated_icon_size=22,
    button_width=28,
    button_height=26,
    active_x=2,
    active_y_offset=-3,
    active_width=24,
    active_height=30,
    label_width=28,
    label_height=54,
    label_step=58,
    unlabeled_gap_after=8,
    label_font_size=12,
    render_source="generated-pixmap",
)


GUI_DESIGN_MOBA_RAIL_ITEM_GEOMETRY: tuple[GuiMobaRailItemGeometry, ...] = (
    GuiMobaRailItemGeometry("collapse", 8, 0),
    GuiMobaRailItemGeometry("sessions", 42, 68),
    GuiMobaRailItemGeometry("favorites", 126, 0),
    GuiMobaRailItemGeometry("tools", 160, 186),
    GuiMobaRailItemGeometry("macros", 244, 270),
    GuiMobaRailItemGeometry("sftp", 328, 354),
)


GUI_DESIGN_MOBA_SSH_BANNER_CHROME = GuiMobaSshBannerChrome(
    title="Remote Ops Workspace",
    subtitle="(SSH client, SFTP browser and remote tools)",
    heading_prefix="* ",
    heading_suffix=" *",
    target_intro="SSH session to",
    capability_label_width=15,
    footer_prefix="For more info, ctrl+click on",
    help_link_label="help",
    website_link_label="website",
    static_left_offset=40,
    static_top_offset=10,
    static_width=570,
    static_height=166,
    body_top_offset=54,
    terminal_gap=18,
)


GUI_DESIGN_MOBA_SSH_BANNER_CAPABILITY_KEYS = (
    "direct-ssh",
    "ssh-compression",
    "smartcard-auth",
    "ssh-browser",
    "x11-forwarding",
)


GUI_DESIGN_MOBA_SSH_BANNER_VISIBLE_CAPABILITY_KEYS = (
    "direct-ssh",
    "ssh-compression",
    "ssh-browser",
    "x11-forwarding",
)


def _build_moba_ssh_banner_row_geometry() -> tuple[GuiMobaSshBannerRowGeometry, ...]:
    chrome = GUI_DESIGN_MOBA_SSH_BANNER_CHROME
    body_x = 14
    body_width = chrome.static_width - body_x * 2
    line_height = 16
    rows: list[GuiMobaSshBannerRowGeometry] = [
        GuiMobaSshBannerRowGeometry("title", "mobaSshBannerTitle", 0, 10, chrome.static_width, line_height, True),
        GuiMobaSshBannerRowGeometry(
            "subtitle",
            "mobaSshBannerSubtitle",
            0,
            27,
            chrome.static_width,
            line_height,
            True,
        ),
        GuiMobaSshBannerRowGeometry(
            "target",
            "mobaSshBannerTargetLine",
            body_x,
            chrome.body_top_offset,
            body_width,
            line_height,
        ),
    ]
    capability_y = chrome.body_top_offset + line_height
    for key in GUI_DESIGN_MOBA_SSH_BANNER_CAPABILITY_KEYS:
        if key not in GUI_DESIGN_MOBA_SSH_BANNER_VISIBLE_CAPABILITY_KEYS:
            rows.append(
                GuiMobaSshBannerRowGeometry(
                    key,
                    "mobaSshBannerCapability",
                    0,
                    0,
                    0,
                    0,
                )
            )
            continue
        index = GUI_DESIGN_MOBA_SSH_BANNER_VISIBLE_CAPABILITY_KEYS.index(key)
        rows.append(
            GuiMobaSshBannerRowGeometry(
                key,
                "mobaSshBannerCapability",
                body_x,
                capability_y + index * line_height,
                body_width,
                line_height,
            )
        )
    rows.append(
        GuiMobaSshBannerRowGeometry(
            "footer",
            "mobaSshBannerFooter",
            body_x,
            capability_y
            + len(GUI_DESIGN_MOBA_SSH_BANNER_VISIBLE_CAPABILITY_KEYS) * line_height
            + 4,
            body_width,
            line_height,
        )
    )
    return tuple(rows)


GUI_DESIGN_MOBA_SSH_BANNER_ROW_GEOMETRY = _build_moba_ssh_banner_row_geometry()


GUI_DESIGN_MOBA_TERMINAL_TRANSCRIPT_ROW_GEOMETRY: tuple[GuiMobaTerminalTranscriptRowGeometry, ...] = (
    GuiMobaTerminalTranscriptRowGeometry("web-console", 14, 0, 20, 13),
    GuiMobaTerminalTranscriptRowGeometry("spacer", 14, 20, 20, 13),
    GuiMobaTerminalTranscriptRowGeometry("last-login", 14, 40, 20, 13),
    GuiMobaTerminalTranscriptRowGeometry("prompt-ready", 14, 60, 20, 13),
)


GUI_DESIGN_MOBA_RIGHT_UTILITY_ACTIONS: tuple[GuiMobaRightUtilityAction, ...] = (
    GuiMobaRightUtilityAction(
        key="clip",
        icon_key="clip",
        label="Clipboard and transfer hints",
        color="#2f8cff",
        tooltip="Show clipboard and transfer hints",
        static_x=7,
        static_y=13,
        static_size=16,
        live_icon_size=18,
        button_size=22,
        render_source="generated-pixmap",
    ),
    GuiMobaRightUtilityAction(
        key="settings",
        icon_key="gear",
        label="Terminal settings",
        color="#38bdf8",
        tooltip="Show terminal settings",
        static_x=7,
        static_y=49,
        static_size=16,
        live_icon_size=18,
        button_size=22,
        render_source="generated-pixmap",
    ),
    GuiMobaRightUtilityAction(
        key="tools",
        icon_key="spark",
        label="Terminal tools",
        color="#38bdf8",
        tooltip="Show terminal tools",
        static_x=7,
        static_y=85,
        static_size=16,
        live_icon_size=18,
        button_size=22,
        render_source="generated-pixmap",
    ),
)


GUI_DESIGN_MOBA_RIGHT_UTILITY_ACTION_ROUTE = GuiMobaRightUtilityActionRoute(
    key="moba-right-utility-action-route",
    route_role="right-utility-rail-actions-to-terminal-workflows",
    rail_object="mobaRightUtilityRail",
    action_object="mobaRightUtilityAction",
    action_keys=tuple(action.key for action in GUI_DESIGN_MOBA_RIGHT_UTILITY_ACTIONS),
    action_labels=tuple(action.label for action in GUI_DESIGN_MOBA_RIGHT_UTILITY_ACTIONS),
    action_icon_keys=tuple(action.icon_key for action in GUI_DESIGN_MOBA_RIGHT_UTILITY_ACTIONS),
    action_handlers=("show_moba_clipboard_hints", "show_moba_terminal_settings", "show_moba_tools_status"),
    route_key_property="mobaRightUtilityRouteKey",
    action_key_property="mobaRightUtilityRouteActionKey",
    action_label_property="mobaRightUtilityRouteActionLabel",
    action_object_property="mobaRightUtilityRouteActionObject",
    icon_key_property="mobaRightUtilityRouteIconKey",
    handler_property="mobaRightUtilityRouteHandler",
    action_keys_property="mobaRightUtilityRouteActionKeys",
    render_source="gui-design-moba-right-utility-route",
)


GUI_DESIGN_MOBA_RIGHT_UTILITY_RAIL_CHROME = GuiMobaRightUtilityRailChrome(
    static_width=0,
    live_width=0,
    margin_left=2,
    margin_top=2,
    margin_right=2,
    margin_bottom=2,
    action_spacing=8,
    session_edge_top_y=108,
    session_edge_height=50,
    session_edge_icon_x=9,
    session_edge_icon_size=16,
)


GUI_DESIGN_MOBA_SESSION_EDGE_ACTIONS: tuple[GuiMobaSessionEdgeAction, ...] = (
    GuiMobaSessionEdgeAction(
        key="attachment",
        icon_key="clip",
        label="Session attachment",
        color="#2f8cff",
        tooltip="Show attached session tools",
        static_y=112,
        static_size=16,
        live_icon_size=16,
        button_size=22,
        render_source="generated-pixmap",
    ),
    GuiMobaSessionEdgeAction(
        key="settings",
        icon_key="gear",
        label="Session settings",
        color="#38bdf8",
        tooltip="Show session settings",
        static_y=130,
        static_size=16,
        live_icon_size=16,
        button_size=22,
        render_source="generated-pixmap",
    ),
)


GUI_DESIGN_MOBA_SESSION_EDGE_ACTION_ROUTE = GuiMobaSessionEdgeActionRoute(
    key="moba-session-edge-action-route",
    route_role="session-edge-shortcuts-to-active-tab-workflows",
    controls_object="mobaSessionEdgeControls",
    action_object="mobaSessionEdgeAction",
    placement="tab-strip-overlay",
    action_keys=tuple(action.key for action in GUI_DESIGN_MOBA_SESSION_EDGE_ACTIONS),
    action_labels=tuple(action.label for action in GUI_DESIGN_MOBA_SESSION_EDGE_ACTIONS),
    action_icon_keys=tuple(action.icon_key for action in GUI_DESIGN_MOBA_SESSION_EDGE_ACTIONS),
    action_handlers=("show_moba_session_attachment", "show_moba_session_settings"),
    route_key_property="mobaSessionEdgeRouteKey",
    action_key_property="mobaSessionEdgeRouteActionKey",
    action_label_property="mobaSessionEdgeRouteActionLabel",
    action_object_property="mobaSessionEdgeRouteActionObject",
    icon_key_property="mobaSessionEdgeRouteIconKey",
    handler_property="mobaSessionEdgeRouteHandler",
    action_keys_property="mobaSessionEdgeRouteActionKeys",
    render_source="gui-design-moba-session-edge-route",
)


GUI_DESIGN_MOBA_TITLEBAR_CHROME = GuiMobaTitlebarChrome(
    icon_key="moba-window",
    static_height=22,
    icon_left=5,
    icon_size=12,
    title_left=24,
    control_keys=("minimize", "maximize", "close"),
    control_width=24,
    control_right_inset=8,
)


GUI_DESIGN_MOBA_QUICK_CONNECT_CHROME = GuiMobaQuickConnectChrome(
    placeholder="Quick connect...",
    dropdown_marker="v",
    static_height=24,
    marker_width=24,
    input_left=0,
    input_padding="4px 8px",
    connected_idle_query="",
    connected_suggestions_visible=False,
)


GUI_DESIGN_MOBA_TOP_STACK_GEOMETRY = GuiMobaTopStackGeometry(
    titlebar_height=GUI_DESIGN_MOBA_TITLEBAR_CHROME.static_height,
    menu_y=GUI_DESIGN_MOBA_TITLEBAR_CHROME.static_height,
    menu_height=22,
    ribbon_y=44,
    ribbon_height=54,
    quick_connect_y=98,
    quick_connect_height=GUI_DESIGN_MOBA_QUICK_CONNECT_CHROME.static_height,
    left_dock_y=122,
    tab_y=98,
    tab_height=24,
    terminal_content_y=122,
    status_height=18,
    side_width=394,
    rail_width=28,
)


GUI_DESIGN_MOBA_QUICK_CONNECT_SUGGESTION_CHROME = GuiMobaQuickConnectSuggestionChrome(
    preview_query="edge-prod.example.invalid",
    expected_kinds=("profile", "direct"),
    max_visible_rows=4,
    row_height=22,
    static_width=394,
    detail_separator="    ",
)


GUI_DESIGN_MOBA_HOME_WELCOME_CHROME = GuiMobaHomeWelcomeChrome(
    title="Remote Ops Workspace",
    subtitle="Moba-style SSH client, SFTP browser and monitoring tools",
    icon_key="session",
    primary_action_icon_key="session",
    secondary_action_icon_key="tunneling",
    search_width=405,
    action_spacing=62,
    recent_title="Recent sessions",
    surface_width=640,
)


GUI_DESIGN_MOBA_HOME_WELCOME_GEOMETRY = GuiMobaHomeWelcomeGeometry(
    center_side_margin=80,
    hero_min_y=115,
    hero_height=330,
    logo_size=46,
    logo_inner_padding=7,
    logo_icon_size=32,
    logo_cluster_width=360,
    title_gap=28,
    title_y_offset=9,
    title_font_size=28,
    subtitle_y_offset=57,
    subtitle_font_size=12,
    button_y_offset=94,
    primary_width=206,
    secondary_width=220,
    action_gap=GUI_DESIGN_MOBA_HOME_WELCOME_CHROME.action_spacing,
    button_height=28,
    button_icon_x=13,
    button_icon_y=6,
    button_icon_size=16,
    button_label_x=40,
    button_label_y=8,
    button_font_size=11,
    search_y_gap=45,
    search_height=25,
    search_text_x=10,
    search_text_y=6,
    search_font_size=12,
    recent_y_gap=52,
    recent_title_font_size=12,
    recent_item_y_offset=28,
    recent_item_step=22,
    recent_column_padding=12,
    footer_y_offset=120,
    footer_font_size=10,
    live_max_extra_width=120,
    live_layout_spacing=13,
    live_title_row_spacing=18,
    live_title_column_spacing=3,
    live_logo_box_width=64,
    live_logo_box_height=56,
    live_logo_pixmap_size=56,
    live_recent_title_top_margin=9,
    live_recent_column_spacing=44,
    live_recent_row_spacing=5,
    live_footer_top_margin=12,
    render_source="generated-pixmap",
)


GUI_DESIGN_MOBA_SFTP_DOCK_ACTIONS: tuple[GuiMobaSftpDockAction, ...] = (
    GuiMobaSftpDockAction(
        "parent-folder",
        "parent-folder",
        "Parent folder",
        "#f4c430",
        "Go to parent directory",
        "navigation",
        True,
    ),
    GuiMobaSftpDockAction("download", "download", "Download", "#5da7ff", "Download selected remote item", "transfer"),
    GuiMobaSftpDockAction("upload", "upload", "Upload", "#35d7c7", "Upload local item", "transfer", True),
    GuiMobaSftpDockAction("connect", "connect", "Reconnect", "#6ac76a", "Reconnect SFTP browser", "manage"),
    GuiMobaSftpDockAction("new-folder", "new-folder", "New folder", "#6ac76a", "Create remote folder", "manage"),
    GuiMobaSftpDockAction("new-file", "new-file", "New file", "#d7dde5", "Create remote file", "manage"),
    GuiMobaSftpDockAction("delete", "delete", "Delete", "#bf3d36", "Delete selected remote item", "manage", True),
    GuiMobaSftpDockAction("ascii-mode", "ascii-mode", "ASCII", "#b580ff", "Toggle text transfer mode", "mode"),
    GuiMobaSftpDockAction("split-view", "split-view", "Split", "#7db4ff", "Toggle split file view", "mode"),
    GuiMobaSftpDockAction("tools", "tools", "Tools", "#9ca3af", "Show SFTP tools", "mode", True),
    GuiMobaSftpDockAction("terminal", "terminal", "Terminal", "#303030", "Open terminal at remote folder", "terminal"),
)


GUI_DESIGN_MOBA_SFTP_BROWSER_CHROME = GuiMobaSftpBrowserChrome(
    path_placeholder="/",
    dropdown_marker="v",
    parent_row_label="..",
    parent_row_kind="parent-dir",
    selected_row_kind="parent-dir",
    columns=(
        GuiMobaSftpTableColumn("name", "Name", 38, 182),
        GuiMobaSftpTableColumn("size", "Size (KB)", 188, 78),
        GuiMobaSftpTableColumn("modified", "Last modified", 266, 94),
    ),
    path_text_x=14,
    path_text_y=6,
    path_font_size=11,
    dropdown_right_offset=18,
    dropdown_y=6,
    dropdown_font_size=10,
    header_label_y=7,
    header_font_size=10,
    row_top_offset=0,
    row_icon_x=14,
    row_icon_y_offset=-1,
    row_name_x=38,
    row_size_x=202,
    row_modified_x=278,
    row_text_y_offset=0,
    row_text_font_size=10,
    row_modified_font_size=9,
)


GUI_DESIGN_MOBA_SFTP_FILE_ROW_ICONS: tuple[GuiMobaSftpFileRowIcon, ...] = (
    GuiMobaSftpFileRowIcon("parent-dir", "folder-up", "parent-dir", 14, "generated-pixmap"),
    GuiMobaSftpFileRowIcon("dir", "folder", "dir", 14, "generated-pixmap"),
    GuiMobaSftpFileRowIcon("file", "file", "file", 14, "generated-pixmap"),
)


GUI_DESIGN_MOBA_SFTP_ROUTED_FILE_ROWS = GuiMobaSftpRoutedFileRows(
    key="sftp-follow-folder-file-rows",
    route_role="follow-folder-visible-file-list",
    follow_route_key="sftp-follow-terminal-folder-route",
    target_table_object="mobaSftpFileTable",
    row_contract_property="mobaSftpRowContractKey",
    row_route_property="mobaSftpRowFollowRouteKey",
    row_path_property="mobaSftpRowSourcePath",
    row_index_property="mobaSftpRowIndex",
    row_selected_property="mobaSftpRowSelectedByRoute",
    parent_row_name=GUI_DESIGN_MOBA_SFTP_BROWSER_CHROME.parent_row_label,
    selected_row_kind=GUI_DESIGN_MOBA_SFTP_BROWSER_CHROME.selected_row_kind,
    render_source="state-file-entries",
)


GUI_DESIGN_MOBA_SFTP_DOCK_LAYOUT = GuiMobaSftpDockLayout(
    inner_margin=0,
    toolbar_height=30,
    toolbar_icon_size=16,
    toolbar_icon_left_inset=7,
    toolbar_icon_step=24,
    toolbar_separator_width=7,
    path_gap=0,
    path_height=22,
    table_header_gap=0,
    table_header_height=24,
    file_row_gap=1,
    file_row_height=21,
    static_max_rows=9,
    monitoring_height=78,
    monitoring_divider_offset=10,
    monitoring_left_inset=18,
    monitoring_content_left=42,
    monitoring_icon_center_x=104,
    monitoring_metric_row_gap=21,
)


def _build_moba_sftp_toolbar_action_geometry() -> tuple[GuiMobaSftpToolbarActionGeometry, ...]:
    layout = GUI_DESIGN_MOBA_SFTP_DOCK_LAYOUT
    icon_x = layout.toolbar_icon_left_inset
    icon_y = (layout.toolbar_height - layout.toolbar_icon_size) // 2
    button_icon_inset = (layout.toolbar_icon_step - layout.toolbar_icon_size) // 2
    button_y = (layout.toolbar_height - layout.toolbar_icon_step) // 2
    geometry: list[GuiMobaSftpToolbarActionGeometry] = []
    for action in GUI_DESIGN_MOBA_SFTP_DOCK_ACTIONS:
        separator_x = (
            icon_x + layout.toolbar_icon_step + layout.toolbar_separator_width // 2
            if action.separator_after
            else 0
        )
        geometry.append(
            GuiMobaSftpToolbarActionGeometry(
                key=action.key,
                button_x=icon_x - button_icon_inset,
                button_y=button_y,
                button_size=layout.toolbar_icon_step,
                icon_x=icon_x,
                icon_y=icon_y,
                icon_size=layout.toolbar_icon_size,
                separator_after=action.separator_after,
                separator_x=separator_x,
            )
        )
        icon_x += layout.toolbar_icon_step
        if action.separator_after:
            icon_x += layout.toolbar_separator_width
    return tuple(geometry)


GUI_DESIGN_MOBA_SFTP_TOOLBAR_ACTION_GEOMETRY = _build_moba_sftp_toolbar_action_geometry()


GUI_DESIGN_MOBA_SFTP_TOOLBAR_ACTION_ROUTE = GuiMobaSftpToolbarActionRoute(
    key="moba-sftp-toolbar-action-route",
    route_role="sftp-toolbar-actions-to-file-transfer-workflows",
    toolbar_object="mobaSftpToolbar",
    action_object="mobaSftpAction",
    target_browser_object="mobaSftpBrowser",
    target_path_object="mobaSftpPath",
    target_table_object="mobaSftpFileTable",
    queue_object="mobaSftpTransferQueue",
    action_keys=tuple(action.key for action in GUI_DESIGN_MOBA_SFTP_DOCK_ACTIONS),
    action_labels=tuple(action.label for action in GUI_DESIGN_MOBA_SFTP_DOCK_ACTIONS),
    action_icon_keys=tuple(action.icon_key for action in GUI_DESIGN_MOBA_SFTP_DOCK_ACTIONS),
    action_group_keys=tuple(action.group_key for action in GUI_DESIGN_MOBA_SFTP_DOCK_ACTIONS),
    action_tooltips=tuple(action.tooltip for action in GUI_DESIGN_MOBA_SFTP_DOCK_ACTIONS),
    action_handlers=tuple("show_moba_sftp_toolbar_action" for _action in GUI_DESIGN_MOBA_SFTP_DOCK_ACTIONS),
    action_statuses=(
        "navigated",
        "queued",
        "queued",
        "reconnected",
        "prepared",
        "prepared",
        "prepared",
        "toggled",
        "toggled",
        "opened",
        "opened",
    ),
    signal="clicked",
    route_key_property="mobaSftpToolbarRouteKey",
    action_key_property="mobaSftpToolbarRouteActionKey",
    action_label_property="mobaSftpToolbarRouteActionLabel",
    action_object_property="mobaSftpToolbarRouteActionObject",
    icon_key_property="mobaSftpToolbarRouteIconKey",
    group_key_property="mobaSftpToolbarRouteGroupKey",
    tooltip_property="mobaSftpToolbarRouteTooltip",
    signal_property="mobaSftpToolbarRouteSignal",
    handler_property="mobaSftpToolbarRouteHandler",
    action_keys_property="mobaSftpToolbarRouteActionKeys",
    action_groups_property="mobaSftpToolbarRouteActionGroups",
    captured_property="mobaSftpToolbarRouteCaptured",
    captured_action_property="mobaSftpToolbarRouteCapturedAction",
    captured_status_property="mobaSftpToolbarRouteCapturedStatus",
    live_triggered_property="mobaSftpToolbarRouteLiveTriggered",
    live_action_property="mobaSftpToolbarRouteLiveAction",
    live_status_property="mobaSftpToolbarRouteLiveStatus",
    render_source="gui-design-moba-sftp-toolbar-route",
)


GUI_DESIGN_MOBA_CONNECTED_DOCK_FRAME = GuiMobaConnectedDockFrame(
    side_width=394,
    rail_width=28,
    dock_x=28,
    dock_y=122,
    dock_width=366,
    dock_height=620,
    workspace_x=394,
    quick_connect_y=98,
    quick_connect_height=24,
    status_y=742,
)


GUI_DESIGN_MOBA_MONITORING_METRICS: tuple[GuiMobaMonitoringMetric, ...] = (
    GuiMobaMonitoringMetric("cpu", "CPU", "cpu_percent"),
    GuiMobaMonitoringMetric("memory", "RAM", "memory_label"),
    GuiMobaMonitoringMetric("disk", "Disk", "disk_label"),
    GuiMobaMonitoringMetric("network", "Net", "network_pair"),
    GuiMobaMonitoringMetric("load", "Load", "load_average"),
    GuiMobaMonitoringMetric("processes", "Proc", "process_count"),
)


GUI_DESIGN_MOBA_MONITORING_CONTROLS: tuple[GuiMobaMonitoringControl, ...] = (
    GuiMobaMonitoringControl(
        key="remote-monitoring",
        icon_key="monitor",
        label="Remote monitoring",
        control_type="toggle",
        checked=True,
        tooltip="Show agentless SSH telemetry in the connected-session dock",
    ),
    GuiMobaMonitoringControl(
        key="follow-terminal-folder",
        icon_key="follow-folder",
        label="Follow terminal folder",
        control_type="checkbox",
        checked=True,
        tooltip=(
            "Keep the SFTP browser on its selected remote path; automatic shell "
            "working-directory detection is not available"
        ),
    ),
)


GUI_DESIGN_MOBA_MONITORING_CONTROL_GEOMETRY: tuple[GuiMobaMonitoringControlGeometry, ...] = (
    GuiMobaMonitoringControlGeometry(
        key="remote-monitoring",
        anchor_x=104,
        static_y=1,
        icon_x=104,
        icon_size=20,
        label_x=132,
        label_y_offset=2,
        label_font_size=12,
        label_bold=True,
        check_size=0,
        check_y_offset=0,
        checkmark_points=(),
        row_height=22,
        live_width=146,
    ),
    GuiMobaMonitoringControlGeometry(
        key="follow-terminal-folder",
        anchor_x=42,
        static_y=50,
        icon_x=60,
        icon_size=16,
        label_x=80,
        label_y_offset=3,
        label_font_size=11,
        label_bold=False,
        check_size=10,
        check_y_offset=3,
        checkmark_points=((2, 5), (5, 9), (10, 1)),
        row_height=19,
        live_width=208,
    ),
)


GUI_DESIGN_MOBA_REMOTE_MONITORING_DOCK_CHROME = GuiMobaRemoteMonitoringDockChrome(
    title_control_key="remote-monitoring",
    follow_control_key="follow-terminal-folder",
    telemetry_surface="bottom-telemetry-bar",
    visible_metric_keys=(),
    refresh_seconds=5,
    compact=True,
    static_height=78,
    divider_offset=10,
    divider_left_inset=18,
    divider_right_inset=194,
    content_left=42,
    icon_center_x=104,
    metric_row_gap=21,
    live_controls_width=260,
)


GUI_DESIGN_MOBA_MONITORING_TELEMETRY_ROUTE = GuiMobaMonitoringTelemetryRoute(
    key="remote-monitoring-to-bottom-telemetry",
    route_role="compact-dock-bottom-telemetry",
    source_panel_object="mobaRemoteMonitoring",
    source_control_key=GUI_DESIGN_MOBA_REMOTE_MONITORING_DOCK_CHROME.title_control_key,
    source_metric_keys=tuple(metric.key for metric in GUI_DESIGN_MOBA_MONITORING_METRICS),
    visible_dock_metric_keys=GUI_DESIGN_MOBA_REMOTE_MONITORING_DOCK_CHROME.visible_metric_keys,
    telemetry_surface=GUI_DESIGN_MOBA_REMOTE_MONITORING_DOCK_CHROME.telemetry_surface,
    target_bar_object="mobaTelemetryBar",
    target_cell_object="mobaTelemetryCell",
    target_identity_cell_key="target",
    target_metric_cell_keys=("cpu", "memory", "disk", "net-up", "net-down", "connections", "processes"),
    render_source="generated-pixmap",
)


GUI_DESIGN_MOBA_REMOTE_MONITORING_CONTROL_ROUTE = GuiMobaRemoteMonitoringControlRoute(
    key="moba-remote-monitoring-control-route",
    route_role="remote-monitoring-control-to-telemetry-refresh",
    source_panel_object=GUI_DESIGN_MOBA_MONITORING_TELEMETRY_ROUTE.source_panel_object,
    source_control_object="mobaMonitoringControl",
    source_control_key=GUI_DESIGN_MOBA_REMOTE_MONITORING_DOCK_CHROME.title_control_key,
    source_control_label=GUI_DESIGN_MOBA_MONITORING_CONTROLS[0].label,
    source_control_type=GUI_DESIGN_MOBA_MONITORING_CONTROLS[0].control_type,
    expected_checked=GUI_DESIGN_MOBA_MONITORING_CONTROLS[0].checked,
    command_property="mobaMonitoringCommand",
    refresh_seconds_property="mobaMonitoringRefreshSeconds",
    checked_property="mobaMonitoringControlChecked",
    telemetry_route_key=GUI_DESIGN_MOBA_MONITORING_TELEMETRY_ROUTE.key,
    telemetry_surface=GUI_DESIGN_MOBA_MONITORING_TELEMETRY_ROUTE.telemetry_surface,
    target_bar_object=GUI_DESIGN_MOBA_MONITORING_TELEMETRY_ROUTE.target_bar_object,
    target_metric_cell_keys=GUI_DESIGN_MOBA_MONITORING_TELEMETRY_ROUTE.target_metric_cell_keys,
    captured_property="mobaRemoteMonitoringControlCaptured",
    captured_checked_property="mobaRemoteMonitoringControlCapturedChecked",
    captured_command_property="mobaRemoteMonitoringControlCapturedCommand",
    captured_refresh_seconds_property="mobaRemoteMonitoringControlCapturedRefreshSeconds",
    signal="toggled",
    handler="handle_moba_remote_monitoring_toggled",
    signal_property="mobaRemoteMonitoringControlSignal",
    handler_property="mobaRemoteMonitoringControlHandler",
    live_checked_property="mobaRemoteMonitoringControlLiveChecked",
    render_source="state-model",
)


GUI_DESIGN_MOBA_FOLLOW_TERMINAL_FOLDER_CONTROL_ROUTE = GuiMobaFollowTerminalFolderControlRoute(
    key="moba-follow-terminal-folder-control-route",
    route_role="follow-terminal-folder-control-to-sftp-browser-sync",
    source_panel_object="mobaRemoteMonitoring",
    source_control_object="mobaFollowTerminalFolder",
    source_control_key=GUI_DESIGN_MOBA_REMOTE_MONITORING_DOCK_CHROME.follow_control_key,
    source_control_label=GUI_DESIGN_MOBA_MONITORING_CONTROLS[1].label,
    source_control_type=GUI_DESIGN_MOBA_MONITORING_CONTROLS[1].control_type,
    expected_checked=GUI_DESIGN_MOBA_MONITORING_CONTROLS[1].checked,
    source_path_property="mobaMonitoringFollowPath",
    source_plan_property="mobaMonitoringFollowPlan",
    source_enabled_property="mobaMonitoringFollowEnabled",
    target_browser_object="mobaSftpBrowser",
    target_path_object="mobaSftpPath",
    target_table_object="mobaSftpFileTable",
    target_path_property="mobaSftpFollowRoutePath",
    target_plan_property="mobaSftpFollowRoutePlan",
    target_enabled_property="mobaSftpFollowRouteEnabled",
    captured_property="mobaFollowTerminalFolderControlCaptured",
    captured_checked_property="mobaFollowTerminalFolderControlCapturedChecked",
    captured_path_property="mobaFollowTerminalFolderControlCapturedPath",
    captured_plan_property="mobaFollowTerminalFolderControlCapturedPlan",
    signal="toggled",
    handler="handle_moba_follow_terminal_folder_toggled",
    signal_property="mobaFollowTerminalFolderControlSignal",
    handler_property="mobaFollowTerminalFolderControlHandler",
    live_checked_property="mobaFollowTerminalFolderControlLiveChecked",
    live_path_property="mobaFollowTerminalFolderControlLivePath",
    live_plan_property="mobaFollowTerminalFolderControlLivePlan",
    render_source="state-model",
)


GUI_DESIGN_MOBA_SFTP_FOLLOW_FOLDER_ROUTE = GuiMobaSftpFollowFolderRoute(
    key="sftp-follow-terminal-folder-route",
    route_role="terminal-cwd-to-sftp-browser",
    source_control_key=GUI_DESIGN_MOBA_REMOTE_MONITORING_DOCK_CHROME.follow_control_key,
    source_control_object="mobaFollowTerminalFolder",
    source_path_property="mobaMonitoringFollowPath",
    source_plan_property="mobaMonitoringFollowPlan",
    source_enabled_property="mobaMonitoringFollowEnabled",
    target_browser_object="mobaSftpBrowser",
    target_path_object="mobaSftpPath",
    target_table_object="mobaSftpFileTable",
    target_path_property="mobaSftpFollowRoutePath",
    target_plan_property="mobaSftpFollowRoutePlan",
    target_enabled_property="mobaSftpFollowRouteEnabled",
    render_source="state-model",
)


GUI_DESIGN_MOBA_STATUS_SEGMENTS: tuple[GuiMobaStatusSegment, ...] = (
    GuiMobaStatusSegment("sftp-ready", "SFTP ready", "Connected SSH browser is ready"),
    GuiMobaStatusSegment("cpu-monitor", "CPU monitor", "Remote monitoring strip is visible"),
    GuiMobaStatusSegment("ssh-browser", "SSH browser", "Follow-folder SFTP browser is available"),
)


GUI_DESIGN_MOBA_STATUS_BAR_CHROME = GuiMobaStatusBarChrome(
    notice="REMOTE OPS WORKSPACE",
    product_note="open-protocol operator shell",
    right_marker="[]",
    right_marker_tooltip="Compact status marker",
    static_height=18,
    notice_x=6,
    notice_y=4,
    product_note_x=142,
    product_note_y=4,
    text_font_size=10,
    segment_start_right_offset=480,
    marker_right_inset=4,
    marker_y=4,
    marker_width=9,
    marker_height=10,
)


GUI_DESIGN_MOBA_BOTTOM_EDGE_CONTROLS: tuple[GuiMobaBottomEdgeControl, ...] = (
    GuiMobaBottomEdgeControl(
        key="tab-left",
        icon_key="arrow-left",
        label="Previous tab",
        color="#4da3ff",
        tooltip="Select previous session tab",
        static_x=1204,
    ),
    GuiMobaBottomEdgeControl(
        key="tab-right",
        icon_key="arrow-right",
        label="Next tab",
        color="#4da3ff",
        tooltip="Select next session tab",
        static_x=1224,
    ),
    GuiMobaBottomEdgeControl(
        key="close-active",
        icon_key="close",
        label="Close active tab",
        color="#ff4d4d",
        tooltip="Close active session tab",
        static_x=1244,
    ),
)


@dataclass(frozen=True)
class GuiMobaSessionTreeChrome:
    header_height: int
    header_icon_x: int
    header_icon_y: int
    header_icon_size: int
    header_text_x: int
    header_text_y: int
    header_font_size: int
    row_start_y: int
    indentation: int
    root_row_height: int
    group_row_height: int
    profile_row_height: int
    group_arrow_x: int
    group_arrow_y_offset: int
    group_icon_x: int
    group_icon_y_offset: int
    group_label_x: int
    group_label_y_offset: int
    group_font_size: int
    profile_icon_x: int
    profile_icon_y_offset: int
    profile_label_x: int
    profile_label_y_offset: int
    profile_label_font_size: int
    profile_target_x: int
    profile_target_y_offset: int
    profile_target_font_size: int
    selected_left: int
    selected_top_offset: int
    selected_right_inset: int
    selected_height: int
    root_is_decorated: bool
    animated: bool
    uniform_row_heights: bool
    render_source: str


GUI_DESIGN_MOBA_SESSION_TREE_CHROME = GuiMobaSessionTreeChrome(
    header_height=28,
    header_icon_x=9,
    header_icon_y=7,
    header_icon_size=14,
    header_text_x=31,
    header_text_y=8,
    header_font_size=10,
    row_start_y=38,
    indentation=16,
    root_row_height=28,
    group_row_height=24,
    profile_row_height=34,
    group_arrow_x=13,
    group_arrow_y_offset=2,
    group_icon_x=29,
    group_icon_y_offset=1,
    group_label_x=51,
    group_label_y_offset=1,
    group_font_size=10,
    profile_icon_x=39,
    profile_icon_y_offset=1,
    profile_label_x=61,
    profile_label_y_offset=0,
    profile_label_font_size=10,
    profile_target_x=61,
    profile_target_y_offset=14,
    profile_target_font_size=8,
    selected_left=28,
    selected_top_offset=-3,
    selected_right_inset=8,
    selected_height=34,
    root_is_decorated=True,
    animated=True,
    uniform_row_heights=True,
    render_source="generated-pixmap",
)


def gui_design_moba_ribbon_actions() -> tuple[GuiMobaRibbonAction, ...]:
    return GUI_DESIGN_MOBA_RIBBON_ACTIONS


def gui_design_moba_ribbon_tooltips() -> dict[str, str]:
    return dict(GUI_DESIGN_MOBA_RIBBON_TOOLTIPS)


def gui_design_moba_ribbon_edge_actions() -> tuple[GuiMobaRibbonEdgeAction, ...]:
    return GUI_DESIGN_MOBA_RIBBON_EDGE_ACTIONS


def gui_design_moba_ribbon_edge_action_route() -> GuiMobaRibbonEdgeActionRoute:
    return GUI_DESIGN_MOBA_RIBBON_EDGE_ACTION_ROUTE


def gui_design_moba_ribbon_action_geometry() -> tuple[GuiMobaRibbonActionGeometry, ...]:
    return GUI_DESIGN_MOBA_RIBBON_ACTION_GEOMETRY


def gui_design_moba_ribbon_action_geometry_for(key: str) -> GuiMobaRibbonActionGeometry:
    for geometry in GUI_DESIGN_MOBA_RIBBON_ACTION_GEOMETRY:
        if geometry.key == key:
            return geometry
    raise KeyError(key)


def gui_design_moba_top_menu_items() -> tuple[GuiMobaTopMenuItem, ...]:
    return GUI_DESIGN_MOBA_TOP_MENU_ITEMS


def gui_design_moba_top_menu_geometry() -> tuple[GuiMobaTopMenuGeometry, ...]:
    return GUI_DESIGN_MOBA_TOP_MENU_GEOMETRY


def gui_design_moba_top_menu_geometry_for(key: str) -> GuiMobaTopMenuGeometry:
    for geometry in GUI_DESIGN_MOBA_TOP_MENU_GEOMETRY:
        if geometry.key == key:
            return geometry
    raise KeyError(key)


def gui_design_moba_titlebar_chrome() -> GuiMobaTitlebarChrome:
    return GUI_DESIGN_MOBA_TITLEBAR_CHROME


def gui_design_moba_quick_connect_chrome() -> GuiMobaQuickConnectChrome:
    return GUI_DESIGN_MOBA_QUICK_CONNECT_CHROME


def gui_design_moba_top_stack_geometry() -> GuiMobaTopStackGeometry:
    return GUI_DESIGN_MOBA_TOP_STACK_GEOMETRY


def gui_design_moba_quick_connect_suggestion_chrome() -> GuiMobaQuickConnectSuggestionChrome:
    return GUI_DESIGN_MOBA_QUICK_CONNECT_SUGGESTION_CHROME


def gui_design_moba_home_welcome_chrome() -> GuiMobaHomeWelcomeChrome:
    return GUI_DESIGN_MOBA_HOME_WELCOME_CHROME


def gui_design_moba_home_welcome_geometry() -> GuiMobaHomeWelcomeGeometry:
    return GUI_DESIGN_MOBA_HOME_WELCOME_GEOMETRY


def gui_design_moba_rail_items() -> tuple[GuiMobaRailItem, ...]:
    return GUI_DESIGN_MOBA_RAIL_ITEMS


def gui_design_moba_rail_chrome() -> GuiMobaRailChrome:
    return GUI_DESIGN_MOBA_RAIL_CHROME


def gui_design_moba_rail_item_geometry() -> tuple[GuiMobaRailItemGeometry, ...]:
    return GUI_DESIGN_MOBA_RAIL_ITEM_GEOMETRY


def gui_design_moba_rail_item_geometry_for(role: str) -> GuiMobaRailItemGeometry:
    for geometry in GUI_DESIGN_MOBA_RAIL_ITEM_GEOMETRY:
        if geometry.role == role:
            return geometry
    raise KeyError(role)


def gui_design_moba_right_utility_actions() -> tuple[GuiMobaRightUtilityAction, ...]:
    return GUI_DESIGN_MOBA_RIGHT_UTILITY_ACTIONS


def gui_design_moba_right_utility_action_route() -> GuiMobaRightUtilityActionRoute:
    return GUI_DESIGN_MOBA_RIGHT_UTILITY_ACTION_ROUTE


def gui_design_moba_right_utility_rail_chrome() -> GuiMobaRightUtilityRailChrome:
    return GUI_DESIGN_MOBA_RIGHT_UTILITY_RAIL_CHROME


def gui_design_moba_session_edge_actions() -> tuple[GuiMobaSessionEdgeAction, ...]:
    return GUI_DESIGN_MOBA_SESSION_EDGE_ACTIONS


def gui_design_moba_session_edge_action_route() -> GuiMobaSessionEdgeActionRoute:
    return GUI_DESIGN_MOBA_SESSION_EDGE_ACTION_ROUTE


def gui_design_moba_sftp_dock_actions() -> tuple[GuiMobaSftpDockAction, ...]:
    return GUI_DESIGN_MOBA_SFTP_DOCK_ACTIONS


def gui_design_moba_sftp_toolbar_action_route() -> GuiMobaSftpToolbarActionRoute:
    return GUI_DESIGN_MOBA_SFTP_TOOLBAR_ACTION_ROUTE


def gui_design_moba_sftp_toolbar_action_geometry() -> tuple[GuiMobaSftpToolbarActionGeometry, ...]:
    return GUI_DESIGN_MOBA_SFTP_TOOLBAR_ACTION_GEOMETRY


def gui_design_moba_sftp_toolbar_action_geometry_for(key: str) -> GuiMobaSftpToolbarActionGeometry:
    for geometry in GUI_DESIGN_MOBA_SFTP_TOOLBAR_ACTION_GEOMETRY:
        if geometry.key == key:
            return geometry
    raise KeyError(key)


def gui_design_moba_sftp_browser_chrome() -> GuiMobaSftpBrowserChrome:
    return GUI_DESIGN_MOBA_SFTP_BROWSER_CHROME


def gui_design_moba_sftp_file_row_icons() -> tuple[GuiMobaSftpFileRowIcon, ...]:
    return GUI_DESIGN_MOBA_SFTP_FILE_ROW_ICONS


def gui_design_moba_sftp_file_row_icon(kind: str) -> GuiMobaSftpFileRowIcon:
    for row_icon in GUI_DESIGN_MOBA_SFTP_FILE_ROW_ICONS:
        if row_icon.kind == kind:
            return row_icon
    return GUI_DESIGN_MOBA_SFTP_FILE_ROW_ICONS[-1]


def gui_design_moba_sftp_routed_file_rows() -> GuiMobaSftpRoutedFileRows:
    return GUI_DESIGN_MOBA_SFTP_ROUTED_FILE_ROWS


def gui_design_moba_sftp_dock_layout() -> GuiMobaSftpDockLayout:
    return GUI_DESIGN_MOBA_SFTP_DOCK_LAYOUT


def gui_design_moba_connected_dock_frame() -> GuiMobaConnectedDockFrame:
    return GUI_DESIGN_MOBA_CONNECTED_DOCK_FRAME


def gui_design_moba_monitoring_metrics() -> tuple[GuiMobaMonitoringMetric, ...]:
    return GUI_DESIGN_MOBA_MONITORING_METRICS


def gui_design_moba_monitoring_controls() -> tuple[GuiMobaMonitoringControl, ...]:
    return GUI_DESIGN_MOBA_MONITORING_CONTROLS


def gui_design_moba_monitoring_control_geometry() -> tuple[GuiMobaMonitoringControlGeometry, ...]:
    return GUI_DESIGN_MOBA_MONITORING_CONTROL_GEOMETRY


def gui_design_moba_monitoring_control_geometry_for(key: str) -> GuiMobaMonitoringControlGeometry:
    for item in GUI_DESIGN_MOBA_MONITORING_CONTROL_GEOMETRY:
        if item.key == key:
            return item
    raise KeyError(key)


def gui_design_moba_remote_monitoring_dock_chrome() -> GuiMobaRemoteMonitoringDockChrome:
    return GUI_DESIGN_MOBA_REMOTE_MONITORING_DOCK_CHROME


def gui_design_moba_monitoring_telemetry_route() -> GuiMobaMonitoringTelemetryRoute:
    return GUI_DESIGN_MOBA_MONITORING_TELEMETRY_ROUTE


def gui_design_moba_remote_monitoring_control_route() -> GuiMobaRemoteMonitoringControlRoute:
    return GUI_DESIGN_MOBA_REMOTE_MONITORING_CONTROL_ROUTE


def gui_design_moba_follow_terminal_folder_control_route() -> GuiMobaFollowTerminalFolderControlRoute:
    return GUI_DESIGN_MOBA_FOLLOW_TERMINAL_FOLDER_CONTROL_ROUTE


def gui_design_moba_sftp_follow_folder_route() -> GuiMobaSftpFollowFolderRoute:
    return GUI_DESIGN_MOBA_SFTP_FOLLOW_FOLDER_ROUTE


def gui_design_moba_status_segments() -> tuple[GuiMobaStatusSegment, ...]:
    return GUI_DESIGN_MOBA_STATUS_SEGMENTS


def gui_design_moba_status_bar_chrome() -> GuiMobaStatusBarChrome:
    return GUI_DESIGN_MOBA_STATUS_BAR_CHROME


def gui_design_moba_bottom_edge_controls() -> tuple[GuiMobaBottomEdgeControl, ...]:
    return GUI_DESIGN_MOBA_BOTTOM_EDGE_CONTROLS


def gui_design_moba_ssh_banner_chrome() -> GuiMobaSshBannerChrome:
    return GUI_DESIGN_MOBA_SSH_BANNER_CHROME


def gui_design_moba_ssh_banner_row_geometry() -> tuple[GuiMobaSshBannerRowGeometry, ...]:
    return GUI_DESIGN_MOBA_SSH_BANNER_ROW_GEOMETRY


def gui_design_moba_ssh_banner_row_geometry_for(key: str) -> GuiMobaSshBannerRowGeometry:
    for geometry in GUI_DESIGN_MOBA_SSH_BANNER_ROW_GEOMETRY:
        if geometry.key == key:
            return geometry
    raise KeyError(key)


def gui_design_moba_terminal_transcript_row_geometry() -> tuple[GuiMobaTerminalTranscriptRowGeometry, ...]:
    return GUI_DESIGN_MOBA_TERMINAL_TRANSCRIPT_ROW_GEOMETRY


def gui_design_moba_terminal_transcript_row_geometry_for(key: str) -> GuiMobaTerminalTranscriptRowGeometry:
    for geometry in GUI_DESIGN_MOBA_TERMINAL_TRANSCRIPT_ROW_GEOMETRY:
        if geometry.key == key:
            return geometry
    raise KeyError(key)


def gui_design_moba_session_tree_chrome() -> GuiMobaSessionTreeChrome:
    return GUI_DESIGN_MOBA_SESSION_TREE_CHROME

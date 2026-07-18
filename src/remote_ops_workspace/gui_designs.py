from __future__ import annotations

from dataclasses import dataclass

DEFAULT_GUI_DESIGN_ID = "native"


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


@dataclass(frozen=True)
class GuiSecureCrtCommandWindowChrome:
    key: str
    title: str
    helper: str
    target_scope: str
    command: str
    send_label: str
    status: str
    static_header_height: int
    static_title_x: int
    static_title_y: int
    static_helper_x: int
    static_helper_y: int
    static_control_y: int
    static_control_bottom_margin: int
    static_target_x: int
    static_target_width: int
    static_target_icon_x: int
    static_target_icon_y: int
    static_target_icon_size: int
    static_target_label_x: int
    static_target_label_y: int
    static_input_x: int
    static_input_text_x: int
    static_input_text_y: int
    static_send_width: int
    static_send_right_margin: int
    static_send_input_gap: int
    static_send_label_x: int
    static_send_label_y: int
    live_margin_left: int
    live_margin_top: int
    live_margin_right: int
    live_margin_bottom: int
    live_spacing: int
    live_header_spacing: int
    live_row_spacing: int
    live_target_min_width: int
    live_send_min_width: int


@dataclass(frozen=True)
class GuiSecureCrtCommandWindowSendRoute:
    key: str
    route_role: str
    source_window_object: str
    target_scope_object: str
    command_input_object: str
    send_control_object: str
    status_object: str
    command_property: str
    target_scope_property: str
    send_label_property: str
    status_property: str
    captured_property: str
    captured_command_property: str
    captured_target_scope_property: str
    captured_status_property: str
    signal: str
    secondary_signal: str
    handler: str
    signal_property: str
    secondary_signal_property: str
    handler_property: str
    live_submitted_property: str
    live_command_property: str
    live_target_scope_property: str
    live_status_property: str
    render_source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "route_role": self.route_role,
            "source_window_object": self.source_window_object,
            "target_scope_object": self.target_scope_object,
            "command_input_object": self.command_input_object,
            "send_control_object": self.send_control_object,
            "status_object": self.status_object,
            "command_property": self.command_property,
            "target_scope_property": self.target_scope_property,
            "send_label_property": self.send_label_property,
            "status_property": self.status_property,
            "captured_property": self.captured_property,
            "captured_command_property": self.captured_command_property,
            "captured_target_scope_property": self.captured_target_scope_property,
            "captured_status_property": self.captured_status_property,
            "signal": self.signal,
            "secondary_signal": self.secondary_signal,
            "handler": self.handler,
            "signal_property": self.signal_property,
            "secondary_signal_property": self.secondary_signal_property,
            "handler_property": self.handler_property,
            "live_submitted_property": self.live_submitted_property,
            "live_command_property": self.live_command_property,
            "live_target_scope_property": self.live_target_scope_property,
            "live_status_property": self.live_status_property,
            "render_source": self.render_source,
        }


@dataclass(frozen=True)
class GuiSecureCrtSessionStatusField:
    key: str
    label: str
    value: str
    tooltip: str
    static_width: int
    role: str
    static_y: int
    static_height: int
    static_label_x: int
    static_label_y: int
    static_value_x: int
    static_value_y: int
    live_min_width: int
    live_cell_height: int


@dataclass(frozen=True)
class GuiSecureCrtSessionStatusStrip:
    title: str
    fields: tuple[GuiSecureCrtSessionStatusField, ...]
    title_width: int
    static_title_x: int
    static_title_y: int
    static_cell_start_x: int
    static_cell_gap: int
    live_margin_left: int
    live_margin_top: int
    live_margin_right: int
    live_margin_bottom: int
    live_spacing: int


@dataclass(frozen=True)
class GuiSecureCrtSessionManagerAction:
    key: str
    icon_key: str
    label: str
    tooltip: str
    static_x: int
    static_y: int
    static_button_size: int
    static_icon_x: int
    static_icon_y: int
    static_icon_size: int
    live_icon_size: int
    live_button_size: int
    render_source: str


@dataclass(frozen=True)
class GuiSecureCrtSessionManagerChrome:
    title: str
    filter_placeholder: str
    actions: tuple[GuiSecureCrtSessionManagerAction, ...]
    static_title_x: int
    static_title_y: int
    static_filter_y: int
    static_filter_x_margin: int
    static_filter_height: int
    static_filter_placeholder_x: int
    static_filter_placeholder_y: int
    live_max_height: int
    live_margin_left: int
    live_margin_top: int
    live_margin_right: int
    live_margin_bottom: int
    live_spacing: int
    live_title_spacing: int
    live_filter_height: int


@dataclass(frozen=True)
class GuiSecureCrtSessionManagerRoute:
    key: str
    route_role: str
    selected_profile_name: str
    selected_tree_label: str
    selected_tree_object: str
    session_manager_object: str
    session_manager_action_key: str
    session_manager_action_object: str
    status_strip_object: str
    status_field_key: str
    status_field_object: str
    active_tab_label: str
    target_value: str
    protocol_value: str
    session_value: str
    selected_tree_property: str
    action_active_property: str
    tab_label_property: str
    status_value_property: str
    render_source: str


@dataclass(frozen=True)
class GuiSecureCrtSessionManagerFilterRoute:
    key: str
    route_role: str
    session_manager_object: str
    filter_object: str
    selected_tree_object: str
    selected_profile_name: str
    selected_tree_label: str
    expected_query: str
    expected_placeholder: str
    matched_result_label: str
    filter_route_property: str
    filter_query_property: str
    filter_placeholder_property: str
    matched_result_property: str
    change_signal: str
    handler_name: str
    render_source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "route_role": self.route_role,
            "session_manager_object": self.session_manager_object,
            "filter_object": self.filter_object,
            "selected_tree_object": self.selected_tree_object,
            "selected_profile_name": self.selected_profile_name,
            "selected_tree_label": self.selected_tree_label,
            "expected_query": self.expected_query,
            "expected_placeholder": self.expected_placeholder,
            "matched_result_label": self.matched_result_label,
            "filter_route_property": self.filter_route_property,
            "filter_query_property": self.filter_query_property,
            "filter_placeholder_property": self.filter_placeholder_property,
            "matched_result_property": self.matched_result_property,
            "change_signal": self.change_signal,
            "handler_name": self.handler_name,
            "render_source": self.render_source,
        }


@dataclass(frozen=True)
class GuiSecureCrtSftpTabRoute:
    key: str
    route_role: str
    workflow_card_key: str
    workflow_card_object: str
    workflow_title_object: str
    workflow_primary_object: str
    workflow_secondary_object: str
    session_manager_object: str
    selected_tree_object: str
    selected_profile_name: str
    selected_tree_label: str
    active_tab_label: str
    sftp_tab_label: str
    status_strip_object: str
    status_field_key: str
    status_field_object: str
    status_value: str
    transfer_state: str
    workflow_title: str
    workflow_primary: str
    workflow_secondary: str
    workflow_key_property: str
    tab_label_property: str
    status_property: str
    transfer_state_property: str
    render_source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "route_role": self.route_role,
            "workflow_card_key": self.workflow_card_key,
            "workflow_card_object": self.workflow_card_object,
            "workflow_title_object": self.workflow_title_object,
            "workflow_primary_object": self.workflow_primary_object,
            "workflow_secondary_object": self.workflow_secondary_object,
            "session_manager_object": self.session_manager_object,
            "selected_tree_object": self.selected_tree_object,
            "selected_profile_name": self.selected_profile_name,
            "selected_tree_label": self.selected_tree_label,
            "active_tab_label": self.active_tab_label,
            "sftp_tab_label": self.sftp_tab_label,
            "status_strip_object": self.status_strip_object,
            "status_field_key": self.status_field_key,
            "status_field_object": self.status_field_object,
            "status_value": self.status_value,
            "transfer_state": self.transfer_state,
            "workflow_title": self.workflow_title,
            "workflow_primary": self.workflow_primary,
            "workflow_secondary": self.workflow_secondary,
            "workflow_key_property": self.workflow_key_property,
            "tab_label_property": self.tab_label_property,
            "status_property": self.status_property,
            "transfer_state_property": self.transfer_state_property,
            "render_source": self.render_source,
        }


@dataclass(frozen=True)
class GuiSecureCrtSftpBrowserRow:
    key: str
    kind: str
    name: str
    size: str
    modified: str
    selected: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "kind": self.kind,
            "name": self.name,
            "size": self.size,
            "modified": self.modified,
            "selected": self.selected,
        }


@dataclass(frozen=True)
class GuiSecureCrtSftpBrowserRoute:
    key: str
    route_role: str
    sftp_tab_route_key: str
    browser_object: str
    toolbar_object: str
    path_object: str
    table_object: str
    row_object: str
    queue_object: str
    selected_profile_name: str
    selected_tree_label: str
    sftp_tab_label: str
    remote_path: str
    toolbar_actions: tuple[str, ...]
    file_rows: tuple[GuiSecureCrtSftpBrowserRow, ...]
    active_row_name: str
    transfer_queue_label: str
    transfer_status: str
    path_property: str
    toolbar_actions_property: str
    row_name_property: str
    row_kind_property: str
    row_selected_property: str
    queue_state_property: str
    action_object: str
    action_key: str
    action_label: str
    action_status: str
    signal: str
    handler: str
    signal_property: str
    handler_property: str
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
            "sftp_tab_route_key": self.sftp_tab_route_key,
            "browser_object": self.browser_object,
            "toolbar_object": self.toolbar_object,
            "path_object": self.path_object,
            "table_object": self.table_object,
            "row_object": self.row_object,
            "queue_object": self.queue_object,
            "selected_profile_name": self.selected_profile_name,
            "selected_tree_label": self.selected_tree_label,
            "sftp_tab_label": self.sftp_tab_label,
            "remote_path": self.remote_path,
            "toolbar_actions": list(self.toolbar_actions),
            "file_rows": [row.to_dict() for row in self.file_rows],
            "active_row_name": self.active_row_name,
            "transfer_queue_label": self.transfer_queue_label,
            "transfer_status": self.transfer_status,
            "path_property": self.path_property,
            "toolbar_actions_property": self.toolbar_actions_property,
            "row_name_property": self.row_name_property,
            "row_kind_property": self.row_kind_property,
            "row_selected_property": self.row_selected_property,
            "queue_state_property": self.queue_state_property,
            "action_object": self.action_object,
            "action_key": self.action_key,
            "action_label": self.action_label,
            "action_status": self.action_status,
            "signal": self.signal,
            "handler": self.handler,
            "signal_property": self.signal_property,
            "handler_property": self.handler_property,
            "captured_property": self.captured_property,
            "captured_action_property": self.captured_action_property,
            "captured_status_property": self.captured_status_property,
            "live_triggered_property": self.live_triggered_property,
            "live_action_property": self.live_action_property,
            "live_status_property": self.live_status_property,
            "render_source": self.render_source,
        }


@dataclass(frozen=True)
class GuiSecureCrtTopMenuItem:
    key: str
    label: str
    primary_action: str
    tooltip: str


@dataclass(frozen=True)
class GuiSecureCrtTopToolbarAction:
    key: str
    icon_key: str
    label: str
    tooltip: str
    static_x: int
    static_width: int


@dataclass(frozen=True)
class GuiSecureCrtTopChrome:
    window_title: str
    menu_height: int
    toolbar_height: int
    menu_items: tuple[GuiSecureCrtTopMenuItem, ...]
    toolbar_actions: tuple[GuiSecureCrtTopToolbarAction, ...]


@dataclass(frozen=True)
class GuiMRemoteNgTopMenuItem:
    key: str
    label: str
    primary_action: str
    tooltip: str


@dataclass(frozen=True)
class GuiMRemoteNgTopToolbarAction:
    key: str
    icon_key: str
    label: str
    tooltip: str
    static_x: int
    static_width: int


@dataclass(frozen=True)
class GuiMRemoteNgTopChrome:
    window_title: str
    menu_height: int
    toolbar_height: int
    menu_items: tuple[GuiMRemoteNgTopMenuItem, ...]
    toolbar_actions: tuple[GuiMRemoteNgTopToolbarAction, ...]


@dataclass(frozen=True)
class GuiRemminaViewerControl:
    key: str
    icon_key: str
    standard_icon: str
    label: str
    tooltip: str
    static_width: int
    static_step: int
    static_y: int
    static_height: int
    static_icon_x: int
    static_icon_size: int
    static_label_x: int
    live_icon_size: int
    live_min_width: int
    live_button_height: int
    render_source: str


@dataclass(frozen=True)
class GuiRemminaProfileColumn:
    key: str
    label: str
    static_width: int
    live_min_width: int


@dataclass(frozen=True)
class GuiRemminaProfileRow:
    key: str
    name: str
    protocol: str
    server: str
    status: str
    selected: bool


@dataclass(frozen=True)
class GuiRemminaProfileListChrome:
    title: str
    filter_placeholder: str
    columns: tuple[GuiRemminaProfileColumn, ...]
    rows: tuple[GuiRemminaProfileRow, ...]
    static_title_x: int
    static_title_y: int
    static_filter_x: int
    static_filter_y: int
    static_filter_height: int
    static_filter_right_margin: int
    static_filter_placeholder_x: int
    static_filter_placeholder_y: int
    static_header_y: int
    static_column_start_x: int
    static_row_start_y: int
    static_row_x_margin: int
    static_row_height: int
    static_row_step: int
    static_cell_start_x: int
    static_cell_y: int
    static_status_y: int
    live_max_height: int
    live_margin_left: int
    live_margin_top: int
    live_margin_right: int
    live_margin_bottom: int
    live_spacing: int
    live_title_spacing: int
    live_filter_width: int
    live_header_spacing: int
    live_row_margin_left: int
    live_row_margin_top: int
    live_row_margin_right: int
    live_row_margin_bottom: int
    live_row_spacing: int
    live_row_min_height: int


@dataclass(frozen=True)
class GuiRemminaProfileViewerRoute:
    key: str
    route_role: str
    selected_profile_key: str
    selected_profile_object: str
    viewer_controls_object: str
    viewer_control_key: str
    viewer_control_object: str
    active_tab_label: str
    protocol: str
    profile_status: str
    selected_row_property: str
    control_active_property: str
    tab_label_property: str
    render_source: str


@dataclass(frozen=True)
class GuiRemminaProfileFilterRoute:
    key: str
    route_role: str
    profile_list_object: str
    filter_object: str
    selected_profile_key: str
    selected_profile_object: str
    matched_profile_name: str
    matched_protocol: str
    matched_status: str
    expected_query: str
    expected_placeholder: str
    active_tab_label: str
    filter_route_property: str
    filter_query_property: str
    filter_placeholder_property: str
    matched_profile_property: str
    matched_protocol_property: str
    active_tab_property: str
    change_signal: str
    handler_name: str
    render_source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "route_role": self.route_role,
            "profile_list_object": self.profile_list_object,
            "filter_object": self.filter_object,
            "selected_profile_key": self.selected_profile_key,
            "selected_profile_object": self.selected_profile_object,
            "matched_profile_name": self.matched_profile_name,
            "matched_protocol": self.matched_protocol,
            "matched_status": self.matched_status,
            "expected_query": self.expected_query,
            "expected_placeholder": self.expected_placeholder,
            "active_tab_label": self.active_tab_label,
            "filter_route_property": self.filter_route_property,
            "filter_query_property": self.filter_query_property,
            "filter_placeholder_property": self.filter_placeholder_property,
            "matched_profile_property": self.matched_profile_property,
            "matched_protocol_property": self.matched_protocol_property,
            "active_tab_property": self.active_tab_property,
            "change_signal": self.change_signal,
            "handler_name": self.handler_name,
            "render_source": self.render_source,
        }


@dataclass(frozen=True)
class GuiRemminaClipboardRoute:
    key: str
    route_role: str
    viewer_controls_object: str
    viewer_control_key: str
    viewer_control_object: str
    active_tab_label: str
    protocol: str
    clipboard_state: str
    status_segment: str
    detail_line: str
    activity_line: str
    control_active_property: str
    tab_label_property: str
    clipboard_state_property: str
    render_source: str


@dataclass(frozen=True)
class GuiRemminaScreenshotRoute:
    key: str
    route_role: str
    viewer_controls_object: str
    viewer_control_key: str
    viewer_control_object: str
    active_tab_label: str
    protocol: str
    capture_state: str
    capture_artifact: str
    status_segment: str
    detail_line: str
    activity_line: str
    control_active_property: str
    tab_label_property: str
    capture_state_property: str
    capture_artifact_property: str
    signal: str
    handler: str
    signal_property: str
    handler_property: str
    captured_property: str
    captured_state_property: str
    captured_artifact_property: str
    live_triggered_property: str
    live_capture_state_property: str
    live_capture_artifact_property: str
    render_source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "route_role": self.route_role,
            "viewer_controls_object": self.viewer_controls_object,
            "viewer_control_key": self.viewer_control_key,
            "viewer_control_object": self.viewer_control_object,
            "active_tab_label": self.active_tab_label,
            "protocol": self.protocol,
            "capture_state": self.capture_state,
            "capture_artifact": self.capture_artifact,
            "status_segment": self.status_segment,
            "detail_line": self.detail_line,
            "activity_line": self.activity_line,
            "control_active_property": self.control_active_property,
            "tab_label_property": self.tab_label_property,
            "capture_state_property": self.capture_state_property,
            "capture_artifact_property": self.capture_artifact_property,
            "signal": self.signal,
            "handler": self.handler,
            "signal_property": self.signal_property,
            "handler_property": self.handler_property,
            "captured_property": self.captured_property,
            "captured_state_property": self.captured_state_property,
            "captured_artifact_property": self.captured_artifact_property,
            "live_triggered_property": self.live_triggered_property,
            "live_capture_state_property": self.live_capture_state_property,
            "live_capture_artifact_property": self.live_capture_artifact_property,
            "render_source": self.render_source,
        }


@dataclass(frozen=True)
class GuiRemminaSftpTransferRow:
    key: str
    kind: str
    name: str
    size: str
    modified: str
    selected: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "kind": self.kind,
            "name": self.name,
            "size": self.size,
            "modified": self.modified,
            "selected": self.selected,
        }


@dataclass(frozen=True)
class GuiRemminaSftpTransferRoute:
    key: str
    route_role: str
    profile_list_object: str
    selected_profile_key: str
    selected_profile_name: str
    selected_profile_protocol: str
    selected_profile_status: str
    selected_profile_object: str
    selected_tree_label: str
    toolbar_action_key: str
    toolbar_action_label: str
    toolbar_action_object: str
    active_tab_label: str
    transfer_panel_object: str
    toolbar_object: str
    path_object: str
    table_object: str
    row_object: str
    queue_object: str
    remote_path: str
    toolbar_actions: tuple[str, ...]
    file_rows: tuple[GuiRemminaSftpTransferRow, ...]
    active_row_name: str
    transfer_queue_label: str
    transfer_status: str
    detail_line: str
    activity_line: str
    selected_profile_property: str
    toolbar_active_property: str
    tab_label_property: str
    path_property: str
    toolbar_actions_property: str
    row_name_property: str
    row_kind_property: str
    row_selected_property: str
    queue_state_property: str
    action_object: str
    action_key: str
    action_label: str
    action_status: str
    signal: str
    handler: str
    signal_property: str
    handler_property: str
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
            "profile_list_object": self.profile_list_object,
            "selected_profile_key": self.selected_profile_key,
            "selected_profile_name": self.selected_profile_name,
            "selected_profile_protocol": self.selected_profile_protocol,
            "selected_profile_status": self.selected_profile_status,
            "selected_profile_object": self.selected_profile_object,
            "selected_tree_label": self.selected_tree_label,
            "toolbar_action_key": self.toolbar_action_key,
            "toolbar_action_label": self.toolbar_action_label,
            "toolbar_action_object": self.toolbar_action_object,
            "active_tab_label": self.active_tab_label,
            "transfer_panel_object": self.transfer_panel_object,
            "toolbar_object": self.toolbar_object,
            "path_object": self.path_object,
            "table_object": self.table_object,
            "row_object": self.row_object,
            "queue_object": self.queue_object,
            "remote_path": self.remote_path,
            "toolbar_actions": list(self.toolbar_actions),
            "file_rows": [row.to_dict() for row in self.file_rows],
            "active_row_name": self.active_row_name,
            "transfer_queue_label": self.transfer_queue_label,
            "transfer_status": self.transfer_status,
            "detail_line": self.detail_line,
            "activity_line": self.activity_line,
            "selected_profile_property": self.selected_profile_property,
            "toolbar_active_property": self.toolbar_active_property,
            "tab_label_property": self.tab_label_property,
            "path_property": self.path_property,
            "toolbar_actions_property": self.toolbar_actions_property,
            "row_name_property": self.row_name_property,
            "row_kind_property": self.row_kind_property,
            "row_selected_property": self.row_selected_property,
            "queue_state_property": self.queue_state_property,
            "action_object": self.action_object,
            "action_key": self.action_key,
            "action_label": self.action_label,
            "action_status": self.action_status,
            "signal": self.signal,
            "handler": self.handler,
            "signal_property": self.signal_property,
            "handler_property": self.handler_property,
            "captured_property": self.captured_property,
            "captured_action_property": self.captured_action_property,
            "captured_status_property": self.captured_status_property,
            "live_triggered_property": self.live_triggered_property,
            "live_action_property": self.live_action_property,
            "live_status_property": self.live_status_property,
            "render_source": self.render_source,
        }


@dataclass(frozen=True)
class GuiTermiusHeaderChip:
    key: str
    label: str
    tooltip: str


@dataclass(frozen=True)
class GuiTermiusHostsAction:
    key: str
    icon_key: str
    label: str
    tooltip: str
    static_x: int


@dataclass(frozen=True)
class GuiTermiusHostsChrome:
    title: str
    filter_placeholder: str
    actions: tuple[GuiTermiusHostsAction, ...]


@dataclass(frozen=True)
class GuiTermiusHostIdentityField:
    key: str
    label: str
    value: str
    tooltip: str
    static_width: int
    role: str
    static_y: int
    static_height: int
    static_label_x: int
    static_label_y: int
    static_value_x: int
    static_value_y: int
    live_min_width: int
    live_cell_height: int


@dataclass(frozen=True)
class GuiTermiusHostIdentityStrip:
    title: str
    fields: tuple[GuiTermiusHostIdentityField, ...]
    title_width: int
    static_title_x: int
    static_title_y: int
    static_cell_start_x: int
    static_cell_gap: int
    live_margin_left: int
    live_margin_top: int
    live_margin_right: int
    live_margin_bottom: int
    live_spacing: int


@dataclass(frozen=True)
class GuiTermiusSyncRoute:
    key: str
    route_role: str
    hosts_action_key: str
    hosts_action_object: str
    header_chip_key: str
    header_chip_object: str
    identity_field_key: str
    identity_cell_object: str
    sync_state: str
    action_label_property: str
    chip_label_property: str
    identity_value_property: str
    status_property: str
    render_source: str


@dataclass(frozen=True)
class GuiTermiusHostSelectionRoute:
    key: str
    route_role: str
    selected_profile_name: str
    selected_tree_label: str
    selected_tree_object: str
    hosts_panel_object: str
    host_identity_object: str
    identity_field_key: str
    identity_cell_object: str
    active_tab_label: str
    target_value: str
    protocol_value: str
    host_value: str
    selected_tree_property: str
    tab_label_property: str
    identity_value_property: str
    render_source: str


@dataclass(frozen=True)
class GuiTermiusPortForwardRoute:
    key: str
    route_role: str
    header_chip_key: str
    header_chip_object: str
    host_identity_object: str
    identity_field_key: str
    identity_cell_object: str
    active_tab_label: str
    selected_profile_name: str
    forward_value: str
    forward_state: str
    local_port: int
    remote_host: str
    remote_port: int
    status_segment: str
    chip_label_property: str
    identity_value_property: str
    active_tab_property: str
    status_property: str
    render_source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "route_role": self.route_role,
            "header_chip_key": self.header_chip_key,
            "header_chip_object": self.header_chip_object,
            "host_identity_object": self.host_identity_object,
            "identity_field_key": self.identity_field_key,
            "identity_cell_object": self.identity_cell_object,
            "active_tab_label": self.active_tab_label,
            "selected_profile_name": self.selected_profile_name,
            "forward_value": self.forward_value,
            "forward_state": self.forward_state,
            "local_port": self.local_port,
            "remote_host": self.remote_host,
            "remote_port": self.remote_port,
            "status_segment": self.status_segment,
            "chip_label_property": self.chip_label_property,
            "identity_value_property": self.identity_value_property,
            "active_tab_property": self.active_tab_property,
            "status_property": self.status_property,
            "render_source": self.render_source,
        }


@dataclass(frozen=True)
class GuiTermiusSnippetRoute:
    key: str
    route_role: str
    workflow_card_key: str
    workflow_card_object: str
    workflow_title_object: str
    workflow_primary_object: str
    workflow_secondary_object: str
    action_object: str
    shortcut_object: str
    host_identity_object: str
    identity_field_key: str
    identity_cell_object: str
    active_tab_label: str
    selected_profile_name: str
    workflow_title: str
    snippet_command: str
    snippet_state: str
    detail_line: str
    action_label: str
    shortcut_sequence: str
    workflow_key_property: str
    command_property: str
    identity_value_property: str
    active_tab_property: str
    status_property: str
    captured_property: str
    captured_command_property: str
    captured_target_profile_property: str
    captured_status_property: str
    signal: str
    secondary_signal: str
    handler: str
    signal_property: str
    secondary_signal_property: str
    handler_property: str
    live_triggered_property: str
    live_command_property: str
    live_target_profile_property: str
    live_status_property: str
    render_source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "route_role": self.route_role,
            "workflow_card_key": self.workflow_card_key,
            "workflow_card_object": self.workflow_card_object,
            "workflow_title_object": self.workflow_title_object,
            "workflow_primary_object": self.workflow_primary_object,
            "workflow_secondary_object": self.workflow_secondary_object,
            "action_object": self.action_object,
            "shortcut_object": self.shortcut_object,
            "host_identity_object": self.host_identity_object,
            "identity_field_key": self.identity_field_key,
            "identity_cell_object": self.identity_cell_object,
            "active_tab_label": self.active_tab_label,
            "selected_profile_name": self.selected_profile_name,
            "workflow_title": self.workflow_title,
            "snippet_command": self.snippet_command,
            "snippet_state": self.snippet_state,
            "detail_line": self.detail_line,
            "action_label": self.action_label,
            "shortcut_sequence": self.shortcut_sequence,
            "workflow_key_property": self.workflow_key_property,
            "command_property": self.command_property,
            "identity_value_property": self.identity_value_property,
            "active_tab_property": self.active_tab_property,
            "status_property": self.status_property,
            "captured_property": self.captured_property,
            "captured_command_property": self.captured_command_property,
            "captured_target_profile_property": self.captured_target_profile_property,
            "captured_status_property": self.captured_status_property,
            "signal": self.signal,
            "secondary_signal": self.secondary_signal,
            "handler": self.handler,
            "signal_property": self.signal_property,
            "secondary_signal_property": self.secondary_signal_property,
            "handler_property": self.handler_property,
            "live_triggered_property": self.live_triggered_property,
            "live_command_property": self.live_command_property,
            "live_target_profile_property": self.live_target_profile_property,
            "live_status_property": self.live_status_property,
            "render_source": self.render_source,
        }


@dataclass(frozen=True)
class GuiTermiusFilesBrowserRow:
    key: str
    kind: str
    name: str
    size: str
    modified: str
    selected: bool

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "kind": self.kind,
            "name": self.name,
            "size": self.size,
            "modified": self.modified,
            "selected": self.selected,
        }


@dataclass(frozen=True)
class GuiTermiusFilesBrowserRoute:
    key: str
    route_role: str
    host_selection_route_key: str
    host_identity_object: str
    identity_field_key: str
    identity_cell_object: str
    files_browser_object: str
    toolbar_object: str
    path_object: str
    table_object: str
    row_object: str
    queue_object: str
    active_tab_label: str
    selected_profile_name: str
    selected_tree_label: str
    files_state: str
    remote_path: str
    toolbar_actions: tuple[str, ...]
    file_rows: tuple[GuiTermiusFilesBrowserRow, ...]
    active_row_name: str
    transfer_queue_label: str
    transfer_status: str
    identity_value_property: str
    active_tab_property: str
    path_property: str
    toolbar_actions_property: str
    row_name_property: str
    row_kind_property: str
    row_selected_property: str
    queue_state_property: str
    action_object: str
    action_key: str
    action_label: str
    action_status: str
    signal: str
    handler: str
    signal_property: str
    handler_property: str
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
            "host_selection_route_key": self.host_selection_route_key,
            "host_identity_object": self.host_identity_object,
            "identity_field_key": self.identity_field_key,
            "identity_cell_object": self.identity_cell_object,
            "files_browser_object": self.files_browser_object,
            "toolbar_object": self.toolbar_object,
            "path_object": self.path_object,
            "table_object": self.table_object,
            "row_object": self.row_object,
            "queue_object": self.queue_object,
            "active_tab_label": self.active_tab_label,
            "selected_profile_name": self.selected_profile_name,
            "selected_tree_label": self.selected_tree_label,
            "files_state": self.files_state,
            "remote_path": self.remote_path,
            "toolbar_actions": list(self.toolbar_actions),
            "file_rows": [row.to_dict() for row in self.file_rows],
            "active_row_name": self.active_row_name,
            "transfer_queue_label": self.transfer_queue_label,
            "transfer_status": self.transfer_status,
            "identity_value_property": self.identity_value_property,
            "active_tab_property": self.active_tab_property,
            "path_property": self.path_property,
            "toolbar_actions_property": self.toolbar_actions_property,
            "row_name_property": self.row_name_property,
            "row_kind_property": self.row_kind_property,
            "row_selected_property": self.row_selected_property,
            "queue_state_property": self.queue_state_property,
            "action_object": self.action_object,
            "action_key": self.action_key,
            "action_label": self.action_label,
            "action_status": self.action_status,
            "signal": self.signal,
            "handler": self.handler,
            "signal_property": self.signal_property,
            "handler_property": self.handler_property,
            "captured_property": self.captured_property,
            "captured_action_property": self.captured_action_property,
            "captured_status_property": self.captured_status_property,
            "live_triggered_property": self.live_triggered_property,
            "live_action_property": self.live_action_property,
            "live_status_property": self.live_status_property,
            "render_source": self.render_source,
        }


@dataclass(frozen=True)
class GuiMRemoteNgDocumentControl:
    key: str
    icon_key: str
    label: str
    tooltip: str
    static_width: int
    static_y: int
    static_height: int
    static_icon_x: int
    static_icon_y: int
    static_icon_size: int
    static_label_x: int
    static_label_y: int
    live_icon_size: int
    live_min_width: int
    live_button_height: int
    render_source: str


@dataclass(frozen=True)
class GuiMRemoteNgDocumentToolbarChrome:
    title: str
    filter_placeholder: str
    title_width: int
    static_height: int
    static_margin_x: int
    static_button_start_x: int
    static_button_gap: int
    static_filter_width: int
    static_filter_y: int
    static_filter_height: int
    live_margin_left: int
    live_margin_top: int
    live_margin_right: int
    live_margin_bottom: int
    live_spacing: int
    live_filter_width: int
    live_filter_height: int


@dataclass(frozen=True)
class GuiMRemoteNgPropertyColumn:
    key: str
    label: str
    static_width: int


@dataclass(frozen=True)
class GuiMRemoteNgPropertyRow:
    key: str
    property_label: str
    inherited_from: str
    effective_value: str
    source: str
    inherited: bool


@dataclass(frozen=True)
class GuiMRemoteNgPropertyGridChrome:
    title: str
    scope_label: str
    inheritance_label: str
    columns: tuple[GuiMRemoteNgPropertyColumn, ...]
    rows: tuple[GuiMRemoteNgPropertyRow, ...]


@dataclass(frozen=True)
class GuiMRemoteNgConnectionDocumentRoute:
    key: str
    route_role: str
    selected_profile_name: str
    selected_tree_label: str
    selected_tree_object: str
    document_controls_object: str
    document_control_key: str
    document_control_object: str
    property_grid_object: str
    property_row_key: str
    property_cell_object: str
    active_tab_label: str
    protocol: str
    workspace_state: str
    property_value: str
    selected_tree_property: str
    control_active_property: str
    tab_label_property: str
    property_value_property: str
    signal: str
    handler: str
    reconnect_state: str
    signal_property: str
    handler_property: str
    captured_property: str
    captured_state_property: str
    captured_profile_property: str
    live_triggered_property: str
    live_state_property: str
    live_profile_property: str
    render_source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "route_role": self.route_role,
            "selected_profile_name": self.selected_profile_name,
            "selected_tree_label": self.selected_tree_label,
            "selected_tree_object": self.selected_tree_object,
            "document_controls_object": self.document_controls_object,
            "document_control_key": self.document_control_key,
            "document_control_object": self.document_control_object,
            "property_grid_object": self.property_grid_object,
            "property_row_key": self.property_row_key,
            "property_cell_object": self.property_cell_object,
            "active_tab_label": self.active_tab_label,
            "protocol": self.protocol,
            "workspace_state": self.workspace_state,
            "property_value": self.property_value,
            "selected_tree_property": self.selected_tree_property,
            "control_active_property": self.control_active_property,
            "tab_label_property": self.tab_label_property,
            "property_value_property": self.property_value_property,
            "signal": self.signal,
            "handler": self.handler,
            "reconnect_state": self.reconnect_state,
            "signal_property": self.signal_property,
            "handler_property": self.handler_property,
            "captured_property": self.captured_property,
            "captured_state_property": self.captured_state_property,
            "captured_profile_property": self.captured_profile_property,
            "live_triggered_property": self.live_triggered_property,
            "live_state_property": self.live_state_property,
            "live_profile_property": self.live_profile_property,
            "render_source": self.render_source,
        }


@dataclass(frozen=True)
class GuiMRemoteNgDocumentFilterRoute:
    key: str
    route_role: str
    document_controls_object: str
    filter_object: str
    selected_tree_object: str
    selected_profile_name: str
    selected_tree_label: str
    matched_protocol: str
    matched_state: str
    expected_query: str
    expected_placeholder: str
    active_tab_label: str
    filter_route_property: str
    filter_query_property: str
    filter_placeholder_property: str
    matched_tree_property: str
    matched_protocol_property: str
    active_tab_property: str
    change_signal: str
    handler_name: str
    render_source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "route_role": self.route_role,
            "document_controls_object": self.document_controls_object,
            "filter_object": self.filter_object,
            "selected_tree_object": self.selected_tree_object,
            "selected_profile_name": self.selected_profile_name,
            "selected_tree_label": self.selected_tree_label,
            "matched_protocol": self.matched_protocol,
            "matched_state": self.matched_state,
            "expected_query": self.expected_query,
            "expected_placeholder": self.expected_placeholder,
            "active_tab_label": self.active_tab_label,
            "filter_route_property": self.filter_route_property,
            "filter_query_property": self.filter_query_property,
            "filter_placeholder_property": self.filter_placeholder_property,
            "matched_tree_property": self.matched_tree_property,
            "matched_protocol_property": self.matched_protocol_property,
            "active_tab_property": self.active_tab_property,
            "change_signal": self.change_signal,
            "handler_name": self.handler_name,
            "render_source": self.render_source,
        }


@dataclass(frozen=True)
class GuiMRemoteNgInheritanceRoute:
    key: str
    route_role: str
    workflow_card_key: str
    workflow_card_object: str
    workflow_title_object: str
    workflow_primary_object: str
    workflow_secondary_object: str
    property_grid_object: str
    property_row_key: str
    property_cell_object: str
    active_tab_label: str
    selected_profile_name: str
    selected_tree_label: str
    workflow_title: str
    inherited_property_label: str
    inherited_value: str
    inherited_source: str
    inheritance_state: str
    workflow_key_property: str
    inherited_value_property: str
    active_tab_property: str
    status_property: str
    render_source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "route_role": self.route_role,
            "workflow_card_key": self.workflow_card_key,
            "workflow_card_object": self.workflow_card_object,
            "workflow_title_object": self.workflow_title_object,
            "workflow_primary_object": self.workflow_primary_object,
            "workflow_secondary_object": self.workflow_secondary_object,
            "property_grid_object": self.property_grid_object,
            "property_row_key": self.property_row_key,
            "property_cell_object": self.property_cell_object,
            "active_tab_label": self.active_tab_label,
            "selected_profile_name": self.selected_profile_name,
            "selected_tree_label": self.selected_tree_label,
            "workflow_title": self.workflow_title,
            "inherited_property_label": self.inherited_property_label,
            "inherited_value": self.inherited_value,
            "inherited_source": self.inherited_source,
            "inheritance_state": self.inheritance_state,
            "workflow_key_property": self.workflow_key_property,
            "inherited_value_property": self.inherited_value_property,
            "active_tab_property": self.active_tab_property,
            "status_property": self.status_property,
            "render_source": self.render_source,
        }


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
        "session", 12, 61, 26, 6, 24, 21, 40, 10, False, 0, 7, 56, 22, 3, 32, 31
    ),
    GuiMobaRibbonActionGeometry(
        "servers", 73, 61, 87, 6, 24, 82, 40, 10, True, 67, 7, 56, 83, 3, 32, 31
    ),
    GuiMobaRibbonActionGeometry(
        "tools", 134, 58, 148, 6, 24, 148, 40, 10, False, 0, 7, 56, 144, 3, 32, 31
    ),
    GuiMobaRibbonActionGeometry(
        "games", 192, 58, 206, 6, 24, 206, 40, 10, False, 0, 7, 56, 202, 3, 32, 31
    ),
    GuiMobaRibbonActionGeometry(
        "sessions", 250, 68, 264, 6, 24, 260, 40, 10, True, 244, 7, 56, 260, 3, 32, 31
    ),
    GuiMobaRibbonActionGeometry(
        "view", 318, 58, 332, 6, 24, 335, 40, 10, False, 0, 7, 56, 328, 3, 32, 31
    ),
    GuiMobaRibbonActionGeometry(
        "split", 376, 58, 390, 6, 24, 390, 40, 10, False, 0, 7, 56, 386, 3, 32, 31
    ),
    GuiMobaRibbonActionGeometry(
        "multiexec", 434, 75, 448, 6, 24, 444, 40, 10, True, 428, 7, 56, 444, 3, 32, 31
    ),
    GuiMobaRibbonActionGeometry(
        "tunneling", 509, 75, 523, 6, 24, 519, 40, 10, False, 0, 7, 56, 519, 3, 32, 31
    ),
    GuiMobaRibbonActionGeometry(
        "packages", 584, 68, 598, 6, 24, 594, 40, 10, False, 0, 7, 56, 594, 3, 32, 31
    ),
    GuiMobaRibbonActionGeometry(
        "settings", 652, 68, 666, 6, 24, 662, 40, 10, True, 646, 7, 56, 662, 3, 32, 31
    ),
    GuiMobaRibbonActionGeometry(
        "help", 720, 58, 734, 6, 24, 737, 40, 10, False, 0, 7, 56, 730, 3, 32, 31
    ),
    GuiMobaRibbonActionGeometry(
        "xserver", 1152, 70, 1158, 6, 28, 1152, 42, 10, True, 1140, 7, 56, 1158, 3, 32, 31
    ),
    GuiMobaRibbonActionGeometry(
        "exit", 1230, 42, 1232, 7, 25, 1230, 42, 10, False, 0, 7, 56, 1232, 3, 32, 31
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
    GuiMobaTopMenuItem("macros", "Macros", "Macros status", "Macro and multiexec workflow status"),
    GuiMobaTopMenuItem("help", "Help", "Run doctor", "Help and doctor commands"),
)

GUI_DESIGN_MOBA_TOP_MENU_GEOMETRY: tuple[GuiMobaTopMenuGeometry, ...] = (
    GuiMobaTopMenuGeometry("terminal", 8, 74, 5, 11, 18),
    GuiMobaTopMenuGeometry("sessions", 82, 74, 5, 11, 18),
    GuiMobaTopMenuGeometry("view", 156, 46, 5, 11, 18),
    GuiMobaTopMenuGeometry("x-server", 202, 74, 5, 11, 18),
    GuiMobaTopMenuGeometry("tools", 276, 53, 5, 11, 18),
    GuiMobaTopMenuGeometry("games", 329, 53, 5, 11, 18),
    GuiMobaTopMenuGeometry("settings", 382, 74, 5, 11, 18),
    GuiMobaTopMenuGeometry("macros", 456, 60, 5, 11, 18),
    GuiMobaTopMenuGeometry("help", 516, 46, 5, 11, 18),
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
        tooltip="Show favorite sessions status",
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
        tooltip="Show macros status",
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
    rail_width=24,
    icon_x=5,
    static_icon_size=16,
    live_icon_size=20,
    generated_icon_size=22,
    button_width=24,
    button_height=26,
    active_x=2,
    active_y_offset=-3,
    active_width=20,
    active_height=30,
    label_width=24,
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
    title="Remote Ops Workspace Personal Edition v1.0",
    subtitle="(SSH client, SFTP browser and remote tools)",
    heading_prefix="* ",
    heading_suffix=" *",
    target_intro="SSH session to",
    capability_label_width=15,
    footer_prefix="For more info, ctrl+click on",
    help_link_label="help",
    website_link_label="website",
    static_left_offset=42,
    static_top_offset=12,
    static_width=570,
    static_height=182,
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
    for index, key in enumerate(GUI_DESIGN_MOBA_SSH_BANNER_CAPABILITY_KEYS):
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
            capability_y + len(GUI_DESIGN_MOBA_SSH_BANNER_CAPABILITY_KEYS) * line_height + 4,
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
    static_width=30,
    live_width=30,
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
    ribbon_height=64,
    quick_connect_y=108,
    quick_connect_height=GUI_DESIGN_MOBA_QUICK_CONNECT_CHROME.static_height,
    left_dock_y=132,
    tab_y=108,
    tab_height=28,
    terminal_content_y=136,
    status_height=22,
    side_width=390,
    rail_width=24,
)
GUI_DESIGN_MOBA_QUICK_CONNECT_SUGGESTION_CHROME = GuiMobaQuickConnectSuggestionChrome(
    preview_query="edge-prod.example.invalid",
    expected_kinds=("profile", "direct"),
    max_visible_rows=4,
    row_height=22,
    static_width=390,
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
    row_top_offset=-4,
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
    inner_margin=6,
    toolbar_height=26,
    toolbar_icon_size=16,
    toolbar_icon_left_inset=7,
    toolbar_icon_step=24,
    toolbar_separator_width=7,
    path_gap=7,
    path_height=24,
    table_header_gap=8,
    table_header_height=24,
    file_row_gap=7,
    file_row_height=21,
    static_max_rows=9,
    monitoring_height=116,
    monitoring_divider_offset=14,
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
    side_width=390,
    rail_width=24,
    dock_x=24,
    dock_y=132,
    dock_width=366,
    dock_height=606,
    workspace_x=390,
    quick_connect_y=108,
    quick_connect_height=24,
    status_y=738,
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
        tooltip="Keep the SFTP browser path synced to the terminal working directory",
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
        static_y=76,
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
    static_height=116,
    divider_offset=14,
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
    static_height=22,
    notice_x=6,
    notice_y=6,
    product_note_x=142,
    product_note_y=6,
    text_font_size=10,
    segment_start_right_offset=480,
    marker_right_inset=4,
    marker_y=6,
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


GUI_DESIGN_SECURECRT_COMMAND_WINDOW_CHROME = GuiSecureCrtCommandWindowChrome(
    key="send-to-all-sessions",
    title="Command Window",
    helper="send command to active tab or all sessions",
    target_scope="All Sessions",
    command="$ row doctor --json",
    send_label="Send",
    status="ready",
    static_header_height=25,
    static_title_x=10,
    static_title_y=8,
    static_helper_x=138,
    static_helper_y=8,
    static_control_y=31,
    static_control_bottom_margin=8,
    static_target_x=10,
    static_target_width=112,
    static_target_icon_x=18,
    static_target_icon_y=6,
    static_target_icon_size=13,
    static_target_label_x=38,
    static_target_label_y=7,
    static_input_x=132,
    static_input_text_x=10,
    static_input_text_y=7,
    static_send_width=58,
    static_send_right_margin=10,
    static_send_input_gap=18,
    static_send_label_x=15,
    static_send_label_y=7,
    live_margin_left=8,
    live_margin_top=7,
    live_margin_right=8,
    live_margin_bottom=7,
    live_spacing=5,
    live_header_spacing=8,
    live_row_spacing=8,
    live_target_min_width=112,
    live_send_min_width=48,
)

GUI_DESIGN_SECURECRT_COMMAND_WINDOW_SEND_ROUTE = GuiSecureCrtCommandWindowSendRoute(
    key="securecrt-command-window-send-route",
    route_role="command-input-to-active-sessions",
    source_window_object="secureCrtCommandWindow",
    target_scope_object="secureCrtCommandTarget",
    command_input_object="secureCrtCommandInput",
    send_control_object="secureCrtCommandSend",
    status_object="secureCrtCommandStatus",
    command_property="secureCrtCommandRouteCommand",
    target_scope_property="secureCrtCommandRouteTargetScope",
    send_label_property="secureCrtCommandRouteSendLabel",
    status_property="secureCrtCommandRouteStatus",
    captured_property="secureCrtCommandRouteCaptured",
    captured_command_property="secureCrtCommandRouteCapturedCommand",
    captured_target_scope_property="secureCrtCommandRouteCapturedTargetScope",
    captured_status_property="secureCrtCommandRouteCapturedStatus",
    signal="clicked",
    secondary_signal="returnPressed",
    handler="handle_securecrt_command_window_send",
    signal_property="secureCrtCommandRouteSignal",
    secondary_signal_property="secureCrtCommandRouteSecondarySignal",
    handler_property="secureCrtCommandRouteHandler",
    live_submitted_property="secureCrtCommandRouteLiveSubmitted",
    live_command_property="secureCrtCommandRouteLiveCommand",
    live_target_scope_property="secureCrtCommandRouteLiveTargetScope",
    live_status_property="secureCrtCommandRouteLiveStatus",
    render_source="state-model",
)

GUI_DESIGN_SECURECRT_SESSION_STATUS_STRIP = GuiSecureCrtSessionStatusStrip(
    title="Session status",
    fields=(
        GuiSecureCrtSessionStatusField(
            "session",
            "Session",
            "edge-prod (SSH2)",
            "Active SecureCRT-style terminal session tab",
            132,
            "normal",
            5,
            20,
            6,
            9,
            48,
            9,
            132,
            22,
        ),
        GuiSecureCrtSessionStatusField(
            "target",
            "Target",
            "edge-prod.example.invalid:22",
            "Generic example target endpoint",
            174,
            "normal",
            5,
            20,
            6,
            9,
            48,
            9,
            170,
            22,
        ),
        GuiSecureCrtSessionStatusField(
            "protocol",
            "Protocol",
            "SSH2 + SFTP",
            "Terminal protocol and attached file-transfer tab",
            102,
            "normal",
            5,
            20,
            6,
            9,
            48,
            9,
            102,
            22,
        ),
        GuiSecureCrtSessionStatusField(
            "cipher",
            "Cipher",
            "chacha20-poly1305",
            "Reference SSH cipher label",
            122,
            "normal",
            5,
            20,
            6,
            9,
            48,
            9,
            122,
            22,
        ),
        GuiSecureCrtSessionStatusField(
            "sftp",
            "SFTP",
            "files-prod tab",
            "Attached SFTP tab state",
            102,
            "normal",
            5,
            20,
            6,
            9,
            48,
            9,
            102,
            22,
        ),
        GuiSecureCrtSessionStatusField(
            "log",
            "Log",
            "session.log",
            "Session logging state",
            90,
            "normal",
            5,
            20,
            6,
            9,
            48,
            9,
            90,
            22,
        ),
        GuiSecureCrtSessionStatusField(
            "state",
            "State",
            "connected",
            "Active connected-session state",
            82,
            "status",
            5,
            20,
            6,
            9,
            48,
            9,
            84,
            22,
        ),
    ),
    title_width=86,
    static_title_x=9,
    static_title_y=10,
    static_cell_start_x=96,
    static_cell_gap=6,
    live_margin_left=7,
    live_margin_top=5,
    live_margin_right=7,
    live_margin_bottom=5,
    live_spacing=6,
)

GUI_DESIGN_SECURECRT_SESSION_MANAGER_CHROME = GuiSecureCrtSessionManagerChrome(
    title="Session Manager",
    filter_placeholder="Filter sessions",
    actions=(
        GuiSecureCrtSessionManagerAction(
            "connect",
            "connect",
            "Connect",
            "Open selected Session Manager entry",
            34,
            5,
            20,
            7,
            3,
            10,
            14,
            24,
            "generated-pixmap",
        ),
        GuiSecureCrtSessionManagerAction(
            "new-folder",
            "folder",
            "New Folder",
            "Create a new Session Manager folder",
            60,
            5,
            20,
            5,
            5,
            10,
            14,
            24,
            "generated-pixmap",
        ),
        GuiSecureCrtSessionManagerAction(
            "properties",
            "properties",
            "Properties",
            "Edit selected Session Manager entry",
            86,
            5,
            20,
            6,
            4,
            9,
            14,
            24,
            "generated-pixmap",
        ),
    ),
    static_title_x=8,
    static_title_y=8,
    static_filter_y=35,
    static_filter_x_margin=8,
    static_filter_height=24,
    static_filter_placeholder_x=17,
    static_filter_placeholder_y=7,
    live_max_height=94,
    live_margin_left=7,
    live_margin_top=6,
    live_margin_right=7,
    live_margin_bottom=6,
    live_spacing=5,
    live_title_spacing=5,
    live_filter_height=24,
)

GUI_DESIGN_SECURECRT_SESSION_MANAGER_ROUTE = GuiSecureCrtSessionManagerRoute(
    key="securecrt-session-manager-route",
    route_role="session-manager-selection-to-active-tab",
    selected_profile_name="edge-prod",
    selected_tree_label="edge-prod (SSH2)",
    selected_tree_object="profileTree",
    session_manager_object="secureCrtSessionManagerChrome",
    session_manager_action_key="connect",
    session_manager_action_object="secureCrtSessionManagerAction",
    status_strip_object="secureCrtSessionStatusStrip",
    status_field_key="target",
    status_field_object="secureCrtSessionStatusCell",
    active_tab_label="edge-prod (SSH2)",
    target_value="edge-prod.example.invalid:22",
    protocol_value="SSH2",
    session_value="edge-prod",
    selected_tree_property="secureCrtSessionRouteSelected",
    action_active_property="secureCrtSessionRouteActive",
    tab_label_property="secureCrtSessionRouteActiveTab",
    status_value_property="secureCrtSessionRouteStatusValue",
    render_source="session-manager-state",
)

GUI_DESIGN_SECURECRT_SESSION_MANAGER_FILTER_ROUTE = GuiSecureCrtSessionManagerFilterRoute(
    key="securecrt-session-manager-filter-route",
    route_role="session-manager-filter-to-visible-session-row",
    session_manager_object="secureCrtSessionManagerChrome",
    filter_object="secureCrtSessionFilter",
    selected_tree_object="profileTree",
    selected_profile_name=GUI_DESIGN_SECURECRT_SESSION_MANAGER_ROUTE.selected_profile_name,
    selected_tree_label=GUI_DESIGN_SECURECRT_SESSION_MANAGER_ROUTE.selected_tree_label,
    expected_query="edge",
    expected_placeholder=GUI_DESIGN_SECURECRT_SESSION_MANAGER_CHROME.filter_placeholder,
    matched_result_label=GUI_DESIGN_SECURECRT_SESSION_MANAGER_ROUTE.selected_tree_label,
    filter_route_property="secureCrtSessionFilterRouteKey",
    filter_query_property="secureCrtSessionFilterRouteQuery",
    filter_placeholder_property="secureCrtSessionFilterRoutePlaceholder",
    matched_result_property="secureCrtSessionFilterRouteMatchedLabel",
    change_signal="textChanged",
    handler_name="filter_profile_tree",
    render_source="session-manager-filter-state",
)

GUI_DESIGN_SECURECRT_SFTP_TAB_ROUTE = GuiSecureCrtSftpTabRoute(
    key="securecrt-sftp-tab-route",
    route_role="workflow-card-to-sftp-tab-status",
    workflow_card_key="sftp-tab",
    workflow_card_object="productWorkflowCard",
    workflow_title_object="productWorkflowTitle",
    workflow_primary_object="productWorkflowPrimary",
    workflow_secondary_object="productWorkflowSecondary",
    session_manager_object=GUI_DESIGN_SECURECRT_SESSION_MANAGER_ROUTE.session_manager_object,
    selected_tree_object=GUI_DESIGN_SECURECRT_SESSION_MANAGER_ROUTE.selected_tree_object,
    selected_profile_name="files-prod",
    selected_tree_label="files-prod (SFTP)",
    active_tab_label=GUI_DESIGN_SECURECRT_SESSION_MANAGER_ROUTE.active_tab_label,
    sftp_tab_label="files-prod",
    status_strip_object=GUI_DESIGN_SECURECRT_SESSION_MANAGER_ROUTE.status_strip_object,
    status_field_key="sftp",
    status_field_object=GUI_DESIGN_SECURECRT_SESSION_MANAGER_ROUTE.status_field_object,
    status_value="files-prod tab",
    transfer_state="files-prod attached",
    workflow_title="SFTP tab",
    workflow_primary="files-prod attached",
    workflow_secondary="terminal plus transfer workflow",
    workflow_key_property="secureCrtSftpTabRouteWorkflowKey",
    tab_label_property="secureCrtSftpTabRouteTabLabel",
    status_property="secureCrtSftpTabRouteStatus",
    transfer_state_property="secureCrtSftpTabRouteTransferState",
    render_source="sftp-tab-status-state",
)

GUI_DESIGN_SECURECRT_SFTP_BROWSER_ROUTE = GuiSecureCrtSftpBrowserRoute(
    key="securecrt-sftp-browser-route",
    route_role="sftp-tab-to-transfer-browser",
    sftp_tab_route_key=GUI_DESIGN_SECURECRT_SFTP_TAB_ROUTE.key,
    browser_object="secureCrtSftpBrowser",
    toolbar_object="secureCrtSftpToolbar",
    path_object="secureCrtSftpPath",
    table_object="secureCrtSftpTable",
    row_object="secureCrtSftpRow",
    queue_object="secureCrtSftpQueue",
    selected_profile_name=GUI_DESIGN_SECURECRT_SFTP_TAB_ROUTE.selected_profile_name,
    selected_tree_label=GUI_DESIGN_SECURECRT_SFTP_TAB_ROUTE.selected_tree_label,
    sftp_tab_label=GUI_DESIGN_SECURECRT_SFTP_TAB_ROUTE.sftp_tab_label,
    remote_path="/srv/files",
    toolbar_actions=("upload", "download", "refresh"),
    file_rows=(
        GuiSecureCrtSftpBrowserRow("parent", "folder", "..", "", "parent", False),
        GuiSecureCrtSftpBrowserRow("releases", "folder", "releases", "-", "2026-06-06", False),
        GuiSecureCrtSftpBrowserRow("deploy-log", "file", "deploy.log", "14 KB", "2026-06-06", True),
    ),
    active_row_name="deploy.log",
    transfer_queue_label="1 queued",
    transfer_status="ready",
    path_property="secureCrtSftpBrowserPath",
    toolbar_actions_property="secureCrtSftpBrowserToolbarActions",
    row_name_property="secureCrtSftpBrowserRowName",
    row_kind_property="secureCrtSftpBrowserRowKind",
    row_selected_property="secureCrtSftpBrowserRowSelected",
    queue_state_property="secureCrtSftpBrowserQueueState",
    action_object="secureCrtSftpAction",
    action_key="refresh",
    action_label="Refresh",
    action_status="refreshed",
    signal="clicked",
    handler="handle_securecrt_sftp_browser_action",
    signal_property="secureCrtSftpBrowserRouteSignal",
    handler_property="secureCrtSftpBrowserRouteHandler",
    captured_property="secureCrtSftpBrowserRouteCaptured",
    captured_action_property="secureCrtSftpBrowserRouteCapturedAction",
    captured_status_property="secureCrtSftpBrowserRouteCapturedStatus",
    live_triggered_property="secureCrtSftpBrowserRouteLiveTriggered",
    live_action_property="secureCrtSftpBrowserRouteLiveAction",
    live_status_property="secureCrtSftpBrowserRouteLiveStatus",
    render_source="sftp-browser-state",
)

GUI_DESIGN_SECURECRT_TOP_CHROME = GuiSecureCrtTopChrome(
    window_title="edge-prod (SSH2) - Remote Ops Workspace",
    menu_height=22,
    toolbar_height=54,
    menu_items=(
        GuiSecureCrtTopMenuItem("file", "File", "Connect...", "Open, clone or save a session"),
        GuiSecureCrtTopMenuItem("edit", "Edit", "Find...", "Find text and edit terminal selection"),
        GuiSecureCrtTopMenuItem("view", "View", "Session Manager", "Show Session Manager and toolbar panes"),
        GuiSecureCrtTopMenuItem("options", "Options", "Session Options", "Edit terminal and session options"),
        GuiSecureCrtTopMenuItem("transfer", "Transfer", "Open SFTP", "Open file-transfer tools for the active session"),
        GuiSecureCrtTopMenuItem("script", "Script", "Run Script", "Run a script against active sessions"),
        GuiSecureCrtTopMenuItem("tools", "Tools", "Key Manager", "Open terminal and key-management tools"),
        GuiSecureCrtTopMenuItem("window", "Window", "Tile Sessions", "Arrange session tabs and split panes"),
        GuiSecureCrtTopMenuItem("help", "Help", "Help Topics", "Open diagnostics and product help"),
    ),
    toolbar_actions=(
        GuiSecureCrtTopToolbarAction("refresh", "session-manager", "Refresh", "Refresh Session Manager", 14, 58),
        GuiSecureCrtTopToolbarAction("new", "new-session", "New Session", "Create a terminal session", 82, 88),
        GuiSecureCrtTopToolbarAction("import", "import-session", "Import", "Import terminal sessions", 180, 68),
        GuiSecureCrtTopToolbarAction("edit", "properties", "Properties", "Edit session properties", 258, 82),
        GuiSecureCrtTopToolbarAction("remove", "delete", "Delete", "Delete selected session", 350, 62),
        GuiSecureCrtTopToolbarAction("connect", "connect", "Connect", "Open selected terminal session", 422, 70),
        GuiSecureCrtTopToolbarAction("files", "sftp", "SFTP", "Open SFTP tab", 502, 54),
        GuiSecureCrtTopToolbarAction("queue", "transfer", "Transfer", "Preview transfer queue", 566, 70),
        GuiSecureCrtTopToolbarAction("dry-run", "command", "Command", "Show launch command", 646, 74),
        GuiSecureCrtTopToolbarAction("doctor", "tools", "Tools", "Run tool diagnostics", 730, 54),
        GuiSecureCrtTopToolbarAction("split-h", "tile-h", "Tile H", "Tile terminal panes horizontally", 794, 58),
        GuiSecureCrtTopToolbarAction("split-v", "tile-v", "Tile V", "Tile terminal panes vertically", 862, 58),
    ),
)

GUI_DESIGN_MREMOTENG_TOP_CHROME = GuiMRemoteNgTopChrome(
    window_title="Connections.xml - Remote Ops Workspace",
    menu_height=22,
    toolbar_height=50,
    menu_items=(
        GuiMRemoteNgTopMenuItem("file", "File", "New Connection", "Create, save or import connection files"),
        GuiMRemoteNgTopMenuItem("view", "View", "Connections", "Show connection tree, panels and toolbars"),
        GuiMRemoteNgTopMenuItem("connections", "Connections", "Connect", "Connect, reconnect or organize entries"),
        GuiMRemoteNgTopMenuItem("tools", "Tools", "External Tools", "Open external tools and diagnostics"),
        GuiMRemoteNgTopMenuItem("window", "Window", "Tile", "Arrange open connection documents"),
        GuiMRemoteNgTopMenuItem("help", "Help", "Help", "Open help and diagnostics"),
    ),
    toolbar_actions=(
        GuiMRemoteNgTopToolbarAction("refresh", "refresh-tree", "Refresh", "Refresh connection tree", 14, 58),
        GuiMRemoteNgTopToolbarAction("new", "new-connection", "New Conn", "Create connection", 80, 74),
        GuiMRemoteNgTopToolbarAction("import", "import-connections", "Import", "Import connection files", 164, 62),
        GuiMRemoteNgTopToolbarAction("edit", "config", "Config", "Edit connection configuration", 236, 62),
        GuiMRemoteNgTopToolbarAction("remove", "delete", "Delete", "Delete connection", 308, 58),
        GuiMRemoteNgTopToolbarAction("connect", "open-connection", "Open", "Open selected connection", 376, 54),
        GuiMRemoteNgTopToolbarAction("files", "external-tool", "External", "Open external file workflow", 440, 74),
        GuiMRemoteNgTopToolbarAction("queue", "transfer", "Transfer", "Preview transfer workflow", 524, 70),
        GuiMRemoteNgTopToolbarAction("dry-run", "script", "Script", "Show launch script", 604, 58),
        GuiMRemoteNgTopToolbarAction("doctor", "tools", "Tools", "Run client tools check", 672, 54),
        GuiMRemoteNgTopToolbarAction("split-h", "tile-h", "Tile H", "Tile connection panes horizontally", 736, 58),
        GuiMRemoteNgTopToolbarAction("split-v", "tile-v", "Tile V", "Tile connection panes vertically", 804, 58),
    ),
)

GUI_DESIGN_REMMINA_VIEWER_CONTROLS: tuple[GuiRemminaViewerControl, ...] = (
    GuiRemminaViewerControl(
        "fit",
        "fit",
        "SP_TitleBarMaxButton",
        "Fit",
        "Fit remote desktop to the viewer",
        74,
        78,
        7,
        20,
        6,
        12,
        22,
        14,
        74,
        26,
        "generated-pixmap",
    ),
    GuiRemminaViewerControl(
        "scale-100",
        "scale",
        "SP_ComputerIcon",
        "Scale 100%",
        "Use exact 100% viewer scale",
        74,
        78,
        7,
        20,
        6,
        12,
        22,
        14,
        74,
        26,
        "generated-pixmap",
    ),
    GuiRemminaViewerControl(
        "clipboard",
        "clipboard",
        "SP_FileDialogDetailedView",
        "Clipboard",
        "Toggle clipboard sync",
        74,
        78,
        7,
        20,
        6,
        12,
        22,
        14,
        74,
        26,
        "generated-pixmap",
    ),
    GuiRemminaViewerControl(
        "fullscreen",
        "fullscreen",
        "SP_TitleBarShadeButton",
        "Fullscreen",
        "Enter fullscreen viewer mode",
        74,
        78,
        7,
        20,
        6,
        12,
        22,
        14,
        74,
        26,
        "generated-pixmap",
    ),
    GuiRemminaViewerControl(
        "screenshot",
        "screenshot",
        "SP_FileDialogContentsView",
        "Screenshot",
        "Capture the remote viewer",
        74,
        78,
        7,
        20,
        6,
        12,
        22,
        14,
        74,
        26,
        "generated-pixmap",
    ),
)

GUI_DESIGN_REMMINA_PROFILE_LIST_CHROME = GuiRemminaProfileListChrome(
    title="Connection list",
    filter_placeholder="Filter by name or protocol",
    columns=(
        GuiRemminaProfileColumn("name", "Name", 98, 98),
        GuiRemminaProfileColumn("protocol", "Protocol", 58, 58),
        GuiRemminaProfileColumn("server", "Server", 104, 104),
    ),
    rows=(
        GuiRemminaProfileRow(
            "win-admin",
            "win-admin",
            "RDP",
            "admin-win.example.invalid",
            "scale 100%",
            True,
        ),
        GuiRemminaProfileRow(
            "linux-console",
            "linux-console",
            "VNC",
            "linux-console.example.invalid",
            "fit window",
            False,
        ),
        GuiRemminaProfileRow(
            "sftp-ops",
            "sftp-ops",
            "SFTP",
            "files.example.invalid",
            "file sharing",
            False,
        ),
    ),
    static_title_x=8,
    static_title_y=8,
    static_filter_x=110,
    static_filter_y=5,
    static_filter_height=20,
    static_filter_right_margin=7,
    static_filter_placeholder_x=7,
    static_filter_placeholder_y=10,
    static_header_y=33,
    static_column_start_x=8,
    static_row_start_y=48,
    static_row_x_margin=6,
    static_row_height=22,
    static_row_step=24,
    static_cell_start_x=12,
    static_cell_y=6,
    static_status_y=16,
    live_max_height=166,
    live_margin_left=7,
    live_margin_top=6,
    live_margin_right=7,
    live_margin_bottom=6,
    live_spacing=5,
    live_title_spacing=6,
    live_filter_width=142,
    live_header_spacing=4,
    live_row_margin_left=5,
    live_row_margin_top=3,
    live_row_margin_right=5,
    live_row_margin_bottom=3,
    live_row_spacing=4,
    live_row_min_height=24,
)


GUI_DESIGN_REMMINA_PROFILE_VIEWER_ROUTE = GuiRemminaProfileViewerRoute(
    key="remmina-selected-profile-viewer-route",
    route_role="selected-profile-to-viewer-tab",
    selected_profile_key="win-admin",
    selected_profile_object="remminaProfileListRow",
    viewer_controls_object="remminaViewerControls",
    viewer_control_key="scale-100",
    viewer_control_object="remminaViewerControl",
    active_tab_label="RDP - win-admin",
    protocol="RDP",
    profile_status="scale 100%",
    selected_row_property="selectedRow",
    control_active_property="remminaProfileViewerRouteActive",
    tab_label_property="remminaProfileViewerRouteActiveTab",
    render_source="profile-list-state",
)

GUI_DESIGN_REMMINA_PROFILE_FILTER_ROUTE = GuiRemminaProfileFilterRoute(
    key="remmina-profile-filter-route",
    route_role="profile-filter-to-visible-viewer-row",
    profile_list_object="remminaProfileListChrome",
    filter_object="remminaProfileFilter",
    selected_profile_key=GUI_DESIGN_REMMINA_PROFILE_VIEWER_ROUTE.selected_profile_key,
    selected_profile_object=GUI_DESIGN_REMMINA_PROFILE_VIEWER_ROUTE.selected_profile_object,
    matched_profile_name="win-admin",
    matched_protocol=GUI_DESIGN_REMMINA_PROFILE_VIEWER_ROUTE.protocol,
    matched_status=GUI_DESIGN_REMMINA_PROFILE_VIEWER_ROUTE.profile_status,
    expected_query="rdp",
    expected_placeholder=GUI_DESIGN_REMMINA_PROFILE_LIST_CHROME.filter_placeholder,
    active_tab_label=GUI_DESIGN_REMMINA_PROFILE_VIEWER_ROUTE.active_tab_label,
    filter_route_property="remminaProfileFilterRouteKey",
    filter_query_property="remminaProfileFilterRouteQuery",
    filter_placeholder_property="remminaProfileFilterRoutePlaceholder",
    matched_profile_property="remminaProfileFilterRouteMatchedProfile",
    matched_protocol_property="remminaProfileFilterRouteMatchedProtocol",
    active_tab_property="remminaProfileFilterRouteActiveTab",
    change_signal="textChanged",
    handler_name="filter_remmina_profile_rows",
    render_source="profile-filter-state",
)

GUI_DESIGN_REMMINA_CLIPBOARD_ROUTE = GuiRemminaClipboardRoute(
    key="remmina-clipboard-sync-route",
    route_role="viewer-control-to-clipboard-state",
    viewer_controls_object="remminaViewerControls",
    viewer_control_key="clipboard",
    viewer_control_object="remminaViewerControl",
    active_tab_label="RDP - win-admin",
    protocol="RDP",
    clipboard_state="clipboard on",
    status_segment="Clipboard on",
    detail_line="Clipboard: enabled",
    activity_line="Clipboard: on",
    control_active_property="remminaClipboardRouteActive",
    tab_label_property="remminaClipboardRouteActiveTab",
    clipboard_state_property="remminaClipboardRouteState",
    render_source="viewer-control-state",
)

GUI_DESIGN_REMMINA_SCREENSHOT_ROUTE = GuiRemminaScreenshotRoute(
    key="remmina-screenshot-capture-route",
    route_role="viewer-control-to-screenshot-capture",
    viewer_controls_object=GUI_DESIGN_REMMINA_PROFILE_VIEWER_ROUTE.viewer_controls_object,
    viewer_control_key="screenshot",
    viewer_control_object=GUI_DESIGN_REMMINA_PROFILE_VIEWER_ROUTE.viewer_control_object,
    active_tab_label=GUI_DESIGN_REMMINA_PROFILE_VIEWER_ROUTE.active_tab_label,
    protocol=GUI_DESIGN_REMMINA_PROFILE_VIEWER_ROUTE.protocol,
    capture_state="screenshot ready",
    capture_artifact="win-admin-rdp-screenshot.png",
    status_segment="RDP/VNC ready",
    detail_line="Screenshot: win-admin-rdp-screenshot.png",
    activity_line="Screenshot: capture ready",
    control_active_property="remminaScreenshotRouteActive",
    tab_label_property="remminaScreenshotRouteActiveTab",
    capture_state_property="remminaScreenshotRouteState",
    capture_artifact_property="remminaScreenshotRouteArtifact",
    signal="clicked",
    handler="handle_remmina_screenshot_capture",
    signal_property="remminaScreenshotRouteSignal",
    handler_property="remminaScreenshotRouteHandler",
    captured_property="remminaScreenshotRouteCaptured",
    captured_state_property="remminaScreenshotRouteCapturedState",
    captured_artifact_property="remminaScreenshotRouteCapturedArtifact",
    live_triggered_property="remminaScreenshotRouteLiveTriggered",
    live_capture_state_property="remminaScreenshotRouteLiveState",
    live_capture_artifact_property="remminaScreenshotRouteLiveArtifact",
    render_source="viewer-control-state",
)

GUI_DESIGN_REMMINA_SFTP_TRANSFER_ROUTE = GuiRemminaSftpTransferRoute(
    key="remmina-sftp-transfer-route",
    route_role="transfer-toolbar-to-sftp-profile-browser",
    profile_list_object="remminaProfileListChrome",
    selected_profile_key="sftp-ops",
    selected_profile_name="sftp-ops",
    selected_profile_protocol="SFTP",
    selected_profile_status="file sharing",
    selected_profile_object="remminaProfileListRow",
    selected_tree_label="sftp-ops",
    toolbar_action_key="queue",
    toolbar_action_label="Transfer",
    toolbar_action_object="productToolbarButton",
    active_tab_label="sftp-ops",
    transfer_panel_object="remminaSftpTransferPanel",
    toolbar_object="remminaSftpTransferToolbar",
    path_object="remminaSftpTransferPath",
    table_object="remminaSftpTransferTable",
    row_object="remminaSftpTransferRow",
    queue_object="remminaSftpTransferQueue",
    remote_path="/var/log",
    toolbar_actions=("upload", "download", "queue"),
    file_rows=(
        GuiRemminaSftpTransferRow("parent", "folder", "..", "", "parent", False),
        GuiRemminaSftpTransferRow("logs", "folder", "logs", "-", "2026-06-06", False),
        GuiRemminaSftpTransferRow("app-log", "file", "app.log", "12 KB", "2026-06-06", True),
    ),
    active_row_name="app.log",
    transfer_queue_label="1 queued",
    transfer_status="ready",
    detail_line="Shared   : file workflow ready",
    activity_line="SFTP transfer: queue ready",
    selected_profile_property="remminaSftpTransferRouteSelectedProfile",
    toolbar_active_property="remminaSftpTransferRouteActive",
    tab_label_property="remminaSftpTransferRouteActiveTab",
    path_property="remminaSftpTransferRoutePath",
    toolbar_actions_property="remminaSftpTransferRouteToolbarActions",
    row_name_property="remminaSftpTransferRouteRowName",
    row_kind_property="remminaSftpTransferRouteRowKind",
    row_selected_property="remminaSftpTransferRouteRowSelected",
    queue_state_property="remminaSftpTransferRouteQueueState",
    action_object="remminaSftpTransferAction",
    action_key="queue",
    action_label="Queue",
    action_status="queued",
    signal="clicked",
    handler="handle_remmina_sftp_transfer_action",
    signal_property="remminaSftpTransferRouteSignal",
    handler_property="remminaSftpTransferRouteHandler",
    captured_property="remminaSftpTransferRouteCaptured",
    captured_action_property="remminaSftpTransferRouteCapturedAction",
    captured_status_property="remminaSftpTransferRouteCapturedStatus",
    live_triggered_property="remminaSftpTransferRouteLiveTriggered",
    live_action_property="remminaSftpTransferRouteLiveAction",
    live_status_property="remminaSftpTransferRouteLiveStatus",
    render_source="sftp-transfer-state",
)

GUI_DESIGN_TERMIUS_HEADER_CHIPS: tuple[GuiTermiusHeaderChip, ...] = (
    GuiTermiusHeaderChip("vault-unlocked", "Vault unlocked", "Vault identity is available for this host"),
    GuiTermiusHeaderChip("sync-current", "Sync current", "Host inventory and settings are current"),
    GuiTermiusHeaderChip("port-forward-ready", "Port fwd ready", "Port forwarding workflow is ready"),
)

GUI_DESIGN_TERMIUS_HOSTS_CHROME = GuiTermiusHostsChrome(
    title="Hosts",
    filter_placeholder="Search hosts",
    actions=(
        GuiTermiusHostsAction("new-host", "plus", "Add Host", "Create a vault host entry", 34),
        GuiTermiusHostsAction("keychain", "key", "Keychain", "Open vault keychain", 60),
        GuiTermiusHostsAction("sync-hosts", "sync", "Sync", "Sync host inventory", 86),
    ),
)

GUI_DESIGN_TERMIUS_HOST_IDENTITY_STRIP = GuiTermiusHostIdentityStrip(
    title="Host identity",
    fields=(
        GuiTermiusHostIdentityField(
            "host",
            "Host",
            "edge-prod",
            "Active SSH host profile",
            92,
            "normal",
            5,
            20,
            6,
            9,
            42,
            9,
            92,
            22,
        ),
        GuiTermiusHostIdentityField(
            "identity",
            "Identity",
            "prod-ed25519",
            "Vault identity assigned to this host",
            112,
            "normal",
            5,
            20,
            6,
            9,
            42,
            9,
            112,
            22,
        ),
        GuiTermiusHostIdentityField(
            "chain",
            "Chain",
            "direct",
            "Host chain or jump state",
            82,
            "normal",
            5,
            20,
            6,
            9,
            42,
            9,
            82,
            22,
        ),
        GuiTermiusHostIdentityField(
            "files",
            "Files",
            "SFTP ready",
            "Attached file workflow state",
            92,
            "normal",
            5,
            20,
            6,
            9,
            42,
            9,
            92,
            22,
        ),
        GuiTermiusHostIdentityField(
            "forward",
            "Forward",
            "8080 -> localhost:80",
            "Port forwarding state",
            132,
            "normal",
            5,
            20,
            6,
            9,
            42,
            9,
            132,
            22,
        ),
        GuiTermiusHostIdentityField(
            "snippet",
            "Snippet",
            "row vault status",
            "Pinned command snippet",
            122,
            "normal",
            5,
            20,
            6,
            9,
            42,
            9,
            122,
            22,
        ),
        GuiTermiusHostIdentityField(
            "sync",
            "Sync",
            "current",
            "Host inventory sync state",
            82,
            "status",
            5,
            20,
            6,
            9,
            42,
            9,
            82,
            22,
        ),
    ),
    title_width=88,
    static_title_x=9,
    static_title_y=10,
    static_cell_start_x=80,
    static_cell_gap=6,
    live_margin_left=7,
    live_margin_top=5,
    live_margin_right=7,
    live_margin_bottom=5,
    live_spacing=6,
)

GUI_DESIGN_TERMIUS_SYNC_ROUTE = GuiTermiusSyncRoute(
    key="termius-host-sync-route",
    route_role="hosts-sync-to-identity-status",
    hosts_action_key="sync-hosts",
    hosts_action_object="termiusHostsAction",
    header_chip_key="sync-current",
    header_chip_object="termiusHeaderChip",
    identity_field_key="sync",
    identity_cell_object="termiusHostIdentityCell",
    sync_state="current",
    action_label_property="termiusSyncRouteActionLabel",
    chip_label_property="termiusSyncRouteChipLabel",
    identity_value_property="termiusSyncRouteIdentityValue",
    status_property="termiusSyncRouteState",
    render_source="state-model",
)

GUI_DESIGN_TERMIUS_HOST_SELECTION_ROUTE = GuiTermiusHostSelectionRoute(
    key="termius-host-selection-route",
    route_role="host-list-selection-to-active-tab",
    selected_profile_name="edge-prod",
    selected_tree_label="edge-prod  ssh host",
    selected_tree_object="profileTree",
    hosts_panel_object="termiusHostsChrome",
    host_identity_object="termiusHostIdentityStrip",
    identity_field_key="host",
    identity_cell_object="termiusHostIdentityCell",
    active_tab_label="edge-prod",
    target_value="edge-prod.example.invalid:22",
    protocol_value="SSH + Vault",
    host_value="edge-prod",
    selected_tree_property="termiusHostRouteSelected",
    tab_label_property="termiusHostRouteActiveTab",
    identity_value_property="termiusHostRouteIdentityValue",
    render_source="host-list-state",
)

GUI_DESIGN_TERMIUS_PORT_FORWARD_ROUTE = GuiTermiusPortForwardRoute(
    key="termius-port-forward-route",
    route_role="port-forward-chip-to-host-identity-forward",
    header_chip_key="port-forward-ready",
    header_chip_object="termiusHeaderChip",
    host_identity_object=GUI_DESIGN_TERMIUS_HOST_SELECTION_ROUTE.host_identity_object,
    identity_field_key="forward",
    identity_cell_object=GUI_DESIGN_TERMIUS_HOST_SELECTION_ROUTE.identity_cell_object,
    active_tab_label=GUI_DESIGN_TERMIUS_HOST_SELECTION_ROUTE.active_tab_label,
    selected_profile_name=GUI_DESIGN_TERMIUS_HOST_SELECTION_ROUTE.selected_profile_name,
    forward_value="8080 -> localhost:80",
    forward_state="ready",
    local_port=8080,
    remote_host="localhost",
    remote_port=80,
    status_segment="Port fwd ready",
    chip_label_property="termiusPortForwardRouteChipLabel",
    identity_value_property="termiusPortForwardRouteIdentityValue",
    active_tab_property="termiusPortForwardRouteActiveTab",
    status_property="termiusPortForwardRouteState",
    render_source="state-model",
)

GUI_DESIGN_TERMIUS_SNIPPET_ROUTE = GuiTermiusSnippetRoute(
    key="termius-snippet-route",
    route_role="workflow-card-to-host-identity-snippet",
    workflow_card_key="snippet",
    workflow_card_object="productWorkflowCard",
    workflow_title_object="productWorkflowTitle",
    workflow_primary_object="productWorkflowPrimary",
    workflow_secondary_object="productWorkflowSecondary",
    action_object="termiusSnippetRunAction",
    shortcut_object="termiusSnippetRunShortcut",
    host_identity_object=GUI_DESIGN_TERMIUS_HOST_SELECTION_ROUTE.host_identity_object,
    identity_field_key="snippet",
    identity_cell_object=GUI_DESIGN_TERMIUS_HOST_SELECTION_ROUTE.identity_cell_object,
    active_tab_label=GUI_DESIGN_TERMIUS_HOST_SELECTION_ROUTE.active_tab_label,
    selected_profile_name=GUI_DESIGN_TERMIUS_HOST_SELECTION_ROUTE.selected_profile_name,
    workflow_title="Snippet",
    snippet_command="row vault status",
    snippet_state="one-click command",
    detail_line="Snippet  : row vault status",
    action_label="Run",
    shortcut_sequence="Return",
    workflow_key_property="termiusSnippetRouteWorkflowKey",
    command_property="termiusSnippetRouteCommand",
    identity_value_property="termiusSnippetRouteIdentityValue",
    active_tab_property="termiusSnippetRouteActiveTab",
    status_property="termiusSnippetRouteState",
    captured_property="termiusSnippetRouteCaptured",
    captured_command_property="termiusSnippetRouteCapturedCommand",
    captured_target_profile_property="termiusSnippetRouteCapturedTargetProfile",
    captured_status_property="termiusSnippetRouteCapturedStatus",
    signal="clicked",
    secondary_signal="activated",
    handler="handle_termius_snippet_run",
    signal_property="termiusSnippetRouteSignal",
    secondary_signal_property="termiusSnippetRouteSecondarySignal",
    handler_property="termiusSnippetRouteHandler",
    live_triggered_property="termiusSnippetRouteLiveTriggered",
    live_command_property="termiusSnippetRouteLiveCommand",
    live_target_profile_property="termiusSnippetRouteLiveTargetProfile",
    live_status_property="termiusSnippetRouteLiveStatus",
    render_source="state-model",
)

GUI_DESIGN_TERMIUS_FILES_BROWSER_ROUTE = GuiTermiusFilesBrowserRoute(
    key="termius-files-browser-route",
    route_role="host-files-tab-to-sftp-browser",
    host_selection_route_key=GUI_DESIGN_TERMIUS_HOST_SELECTION_ROUTE.key,
    host_identity_object=GUI_DESIGN_TERMIUS_HOST_SELECTION_ROUTE.host_identity_object,
    identity_field_key="files",
    identity_cell_object=GUI_DESIGN_TERMIUS_HOST_SELECTION_ROUTE.identity_cell_object,
    files_browser_object="termiusFilesBrowser",
    toolbar_object="termiusFilesToolbar",
    path_object="termiusFilesPath",
    table_object="termiusFilesTable",
    row_object="termiusFilesRow",
    queue_object="termiusFilesQueue",
    active_tab_label=GUI_DESIGN_TERMIUS_HOST_SELECTION_ROUTE.active_tab_label,
    selected_profile_name=GUI_DESIGN_TERMIUS_HOST_SELECTION_ROUTE.selected_profile_name,
    selected_tree_label=GUI_DESIGN_TERMIUS_HOST_SELECTION_ROUTE.selected_tree_label,
    files_state="SFTP ready",
    remote_path="/workspace",
    toolbar_actions=("upload", "download", "sync"),
    file_rows=(
        GuiTermiusFilesBrowserRow("parent", "folder", "..", "", "parent", False),
        GuiTermiusFilesBrowserRow("src", "folder", "src", "-", "2026-06-06", False),
        GuiTermiusFilesBrowserRow("deploy-yml", "file", "deploy.yml", "3 KB", "2026-06-06", True),
    ),
    active_row_name="deploy.yml",
    transfer_queue_label="sync idle",
    transfer_status="ready",
    identity_value_property="termiusFilesRouteIdentityValue",
    active_tab_property="termiusFilesRouteActiveTab",
    path_property="termiusFilesRoutePath",
    toolbar_actions_property="termiusFilesRouteToolbarActions",
    row_name_property="termiusFilesRouteRowName",
    row_kind_property="termiusFilesRouteRowKind",
    row_selected_property="termiusFilesRouteRowSelected",
    queue_state_property="termiusFilesRouteQueueState",
    action_object="termiusFilesAction",
    action_key="sync",
    action_label="Sync",
    action_status="synced",
    signal="clicked",
    handler="handle_termius_files_sync",
    signal_property="termiusFilesRouteSignal",
    handler_property="termiusFilesRouteHandler",
    captured_property="termiusFilesRouteCaptured",
    captured_action_property="termiusFilesRouteCapturedAction",
    captured_status_property="termiusFilesRouteCapturedStatus",
    live_triggered_property="termiusFilesRouteLiveTriggered",
    live_action_property="termiusFilesRouteLiveAction",
    live_status_property="termiusFilesRouteLiveStatus",
    render_source="files-browser-state",
)

GUI_DESIGN_MREMOTENG_DOCUMENT_TOOLBAR_CHROME = GuiMRemoteNgDocumentToolbarChrome(
    title="Connections.xml",
    filter_placeholder="Filter connection tree",
    title_width=112,
    static_height=28,
    static_margin_x=10,
    static_button_start_x=128,
    static_button_gap=8,
    static_filter_width=178,
    static_filter_y=5,
    static_filter_height=18,
    live_margin_left=7,
    live_margin_top=5,
    live_margin_right=7,
    live_margin_bottom=5,
    live_spacing=7,
    live_filter_width=178,
    live_filter_height=24,
)

GUI_DESIGN_MREMOTENG_DOCUMENT_CONTROLS: tuple[GuiMRemoteNgDocumentControl, ...] = (
    GuiMRemoteNgDocumentControl(
        "save",
        "database",
        "Save",
        "Save the connection document",
        56,
        4,
        20,
        8,
        7,
        13,
        27,
        8,
        14,
        56,
        26,
        "generated-pixmap",
    ),
    GuiMRemoteNgDocumentControl(
        "reconnect",
        "ssh",
        "Reconnect",
        "Reconnect active document",
        88,
        4,
        20,
        8,
        7,
        13,
        27,
        8,
        14,
        88,
        26,
        "generated-pixmap",
    ),
    GuiMRemoteNgDocumentControl(
        "external-tool",
        "external",
        "External tool",
        "Open the external tool for this connection",
        104,
        4,
        20,
        8,
        7,
        13,
        27,
        8,
        14,
        104,
        26,
        "generated-pixmap",
    ),
    GuiMRemoteNgDocumentControl(
        "dock-view",
        "rdp",
        "Dock view",
        "Toggle the docked viewer",
        84,
        4,
        20,
        8,
        7,
        13,
        27,
        8,
        14,
        84,
        26,
        "generated-pixmap",
    ),
)

GUI_DESIGN_MREMOTENG_PROPERTY_GRID_CHROME = GuiMRemoteNgPropertyGridChrome(
    title="Config / Inheritance",
    scope_label="edge-prod [SSH]",
    inheritance_label="inherited",
    columns=(
        GuiMRemoteNgPropertyColumn("property", "Property", 155),
        GuiMRemoteNgPropertyColumn("inherited", "Inherited", 150),
        GuiMRemoteNgPropertyColumn("effective", "Effective value", 270),
        GuiMRemoteNgPropertyColumn("source", "Source", 245),
    ),
    rows=(
        GuiMRemoteNgPropertyRow("protocol", "Protocol", "container prod", "SSH", "Connections.xml/prod", True),
        GuiMRemoteNgPropertyRow(
            "hostname",
            "Hostname",
            "connection node",
            "edge-prod.example.invalid",
            "Connections.xml/prod/edge-prod",
            False,
        ),
        GuiMRemoteNgPropertyRow("credential", "Credential", "group default", "operator key reference", "Connections.xml/prod", True),
        GuiMRemoteNgPropertyRow("external", "External", "files group", "SFTP ready", "Connections.xml/files", True),
        GuiMRemoteNgPropertyRow("inheritance", "Inheritance", "enabled", "credentials on", "connection node", False),
    ),
)


GUI_DESIGN_MREMOTENG_CONNECTION_DOCUMENT_ROUTE = GuiMRemoteNgConnectionDocumentRoute(
    key="mremoteng-selected-connection-document-route",
    route_role="connection-tree-to-document-workspace",
    selected_profile_name="edge-prod",
    selected_tree_label="edge-prod [SSH]",
    selected_tree_object="profileTree",
    document_controls_object="mRemoteNgDocumentControls",
    document_control_key="reconnect",
    document_control_object="mRemoteNgDocumentControl",
    property_grid_object="mRemoteNgPropertyGrid",
    property_row_key="protocol",
    property_cell_object="mRemoteNgPropertyGridCell",
    active_tab_label="edge-prod [SSH]",
    protocol="SSH",
    workspace_state="document open",
    property_value="SSH",
    selected_tree_property="mRemoteNgConnectionRouteSelected",
    control_active_property="mRemoteNgConnectionRouteActive",
    tab_label_property="mRemoteNgConnectionRouteActiveTab",
    property_value_property="mRemoteNgConnectionRoutePropertyValue",
    signal="clicked",
    handler="handle_mremoteng_document_reconnect",
    reconnect_state="reconnected",
    signal_property="mRemoteNgConnectionRouteSignal",
    handler_property="mRemoteNgConnectionRouteHandler",
    captured_property="mRemoteNgConnectionRouteCaptured",
    captured_state_property="mRemoteNgConnectionRouteCapturedState",
    captured_profile_property="mRemoteNgConnectionRouteCapturedProfile",
    live_triggered_property="mRemoteNgConnectionRouteLiveTriggered",
    live_state_property="mRemoteNgConnectionRouteLiveState",
    live_profile_property="mRemoteNgConnectionRouteLiveProfile",
    render_source="connection-tree-state",
)


GUI_DESIGN_MREMOTENG_DOCUMENT_FILTER_ROUTE = GuiMRemoteNgDocumentFilterRoute(
    key="mremoteng-document-filter-route",
    route_role="document-filter-to-selected-connection-row",
    document_controls_object=GUI_DESIGN_MREMOTENG_CONNECTION_DOCUMENT_ROUTE.document_controls_object,
    filter_object="mRemoteNgDocumentFilter",
    selected_tree_object=GUI_DESIGN_MREMOTENG_CONNECTION_DOCUMENT_ROUTE.selected_tree_object,
    selected_profile_name=GUI_DESIGN_MREMOTENG_CONNECTION_DOCUMENT_ROUTE.selected_profile_name,
    selected_tree_label=GUI_DESIGN_MREMOTENG_CONNECTION_DOCUMENT_ROUTE.selected_tree_label,
    matched_protocol=GUI_DESIGN_MREMOTENG_CONNECTION_DOCUMENT_ROUTE.protocol,
    matched_state=GUI_DESIGN_MREMOTENG_CONNECTION_DOCUMENT_ROUTE.workspace_state,
    expected_query="edge",
    expected_placeholder=GUI_DESIGN_MREMOTENG_DOCUMENT_TOOLBAR_CHROME.filter_placeholder,
    active_tab_label=GUI_DESIGN_MREMOTENG_CONNECTION_DOCUMENT_ROUTE.active_tab_label,
    filter_route_property="mRemoteNgDocumentFilterRouteKey",
    filter_query_property="mRemoteNgDocumentFilterRouteQuery",
    filter_placeholder_property="mRemoteNgDocumentFilterRoutePlaceholder",
    matched_tree_property="mRemoteNgDocumentFilterRouteMatchedTreeLabel",
    matched_protocol_property="mRemoteNgDocumentFilterRouteMatchedProtocol",
    active_tab_property="mRemoteNgDocumentFilterRouteActiveTab",
    change_signal="textChanged",
    handler_name="filter_profile_tree",
    render_source="connection-tree-filter-state",
)


GUI_DESIGN_MREMOTENG_INHERITANCE_ROUTE = GuiMRemoteNgInheritanceRoute(
    key="mremoteng-inheritance-route",
    route_role="workflow-card-to-property-grid-inheritance",
    workflow_card_key="inheritance-grid",
    workflow_card_object="productWorkflowCard",
    workflow_title_object="productWorkflowTitle",
    workflow_primary_object="productWorkflowPrimary",
    workflow_secondary_object="productWorkflowSecondary",
    property_grid_object=GUI_DESIGN_MREMOTENG_CONNECTION_DOCUMENT_ROUTE.property_grid_object,
    property_row_key="credential",
    property_cell_object=GUI_DESIGN_MREMOTENG_CONNECTION_DOCUMENT_ROUTE.property_cell_object,
    active_tab_label=GUI_DESIGN_MREMOTENG_CONNECTION_DOCUMENT_ROUTE.active_tab_label,
    selected_profile_name=GUI_DESIGN_MREMOTENG_CONNECTION_DOCUMENT_ROUTE.selected_profile_name,
    selected_tree_label=GUI_DESIGN_MREMOTENG_CONNECTION_DOCUMENT_ROUTE.selected_tree_label,
    workflow_title="Config inheritance",
    inherited_property_label="Credential",
    inherited_value="operator key reference",
    inherited_source="Connections.xml/prod",
    inheritance_state="credentials inherited",
    workflow_key_property="mRemoteNgInheritanceRouteWorkflowKey",
    inherited_value_property="mRemoteNgInheritanceRouteInheritedValue",
    active_tab_property="mRemoteNgInheritanceRouteActiveTab",
    status_property="mRemoteNgInheritanceRouteState",
    render_source="property-grid-state",
)


GUI_DESIGN_SIDEBAR_COPY: dict[str, tuple[str, str]] = {
    DEFAULT_GUI_DESIGN_ID: ("Profiles", "Saved sessions and local layouts"),
    "mobaxterm": ("User sessions", "Quick connect and session tree"),
    "securecrt": ("Session Manager", "Folders, sessions and terminal tabs"),
    "termius": ("Hosts", "Vault-backed SSH inventory"),
    "remmina": ("Connection Profiles", "RDP, VNC, SSH and SFTP targets"),
    "mremoteng": ("Connections", "Nested groups and saved targets"),
}
GUI_DESIGN_TOOLBAR_COPY: dict[str, tuple[tuple[str, str, str], ...]] = {
    DEFAULT_GUI_DESIGN_ID: (
        ("refresh", "Refresh", "Reload profiles"),
        ("new", "New", "Create profile"),
        ("import", "Import", "Preview and import profiles"),
        ("edit", "Edit", "Edit selected profile"),
        ("remove", "Remove", "Remove selected profile"),
        ("connect", "Connect", "Open selected profile"),
        ("files", "Files", "Open SFTP browser"),
        ("queue", "Queue", "Preview transfer queue"),
        ("dry-run", "Dry Run", "Show launch command"),
        ("doctor", "Doctor", "Run doctor checks"),
        ("split-h", "Split H", "Open horizontal split"),
        ("split-v", "Split V", "Open vertical split"),
    ),
    "securecrt": (
        ("refresh", "Refresh", "Refresh Session Manager"),
        ("new", "New Session", "Create a terminal session"),
        ("import", "Import", "Import session definitions"),
        ("edit", "Properties", "Edit session properties"),
        ("remove", "Delete", "Delete selected session"),
        ("connect", "Connect", "Open selected terminal session"),
        ("files", "SFTP", "Open SFTP tab"),
        ("queue", "Transfer", "Preview transfer queue"),
        ("dry-run", "Command", "Show launch command"),
        ("doctor", "Tools", "Run tool diagnostics"),
        ("split-h", "Tile H", "Tile terminal panes horizontally"),
        ("split-v", "Tile V", "Tile terminal panes vertically"),
    ),
    "termius": (
        ("refresh", "Sync", "Sync host inventory"),
        ("new", "New Host", "Create SSH host"),
        ("import", "Import", "Import host profiles"),
        ("edit", "Edit Host", "Edit selected host"),
        ("remove", "Remove", "Remove selected host"),
        ("connect", "Connect", "Open selected SSH host"),
        ("files", "SFTP", "Open SFTP workflow"),
        ("queue", "Port Fwd", "Preview forwarding workflow"),
        ("dry-run", "Snippet", "Show command snippet"),
        ("doctor", "Vault", "Check vault and client status"),
        ("split-h", "Split H", "Split terminal horizontally"),
        ("split-v", "Split V", "Split terminal vertically"),
    ),
    "remmina": (
        ("refresh", "Refresh", "Refresh connection profiles"),
        ("new", "New Profile", "Create connection profile"),
        ("import", "Import", "Import connection profiles"),
        ("edit", "Edit", "Edit connection profile"),
        ("remove", "Delete", "Delete connection profile"),
        ("connect", "Connect", "Open selected remote desktop profile"),
        ("files", "Shared", "Open file sharing workflow"),
        ("queue", "Transfer", "Preview transfer workflow"),
        ("dry-run", "Preview", "Preview launch command"),
        ("doctor", "Prefs", "Check client preferences and availability"),
        ("split-h", "Tile H", "Tile viewer panes horizontally"),
        ("split-v", "Tile V", "Tile viewer panes vertically"),
    ),
    "mremoteng": (
        ("refresh", "Refresh", "Refresh connection tree"),
        ("new", "New Conn", "Create connection"),
        ("import", "Import", "Import connection definitions"),
        ("edit", "Config", "Edit connection configuration"),
        ("remove", "Delete", "Delete connection"),
        ("connect", "Open", "Open selected connection"),
        ("files", "External", "Open external file workflow"),
        ("queue", "Transfer", "Preview transfer workflow"),
        ("dry-run", "Script", "Show launch script"),
        ("doctor", "Tools", "Run client tools check"),
        ("split-h", "Tile H", "Tile connection panes horizontally"),
        ("split-v", "Tile V", "Tile connection panes vertically"),
    ),
}
GUI_DESIGN_STATUS_COPY: dict[str, tuple[str, ...]] = {
    DEFAULT_GUI_DESIGN_ID: ("profiles ready", "2 panes", "tabs north"),
    "mobaxterm": tuple(segment.text for segment in GUI_DESIGN_MOBA_STATUS_SEGMENTS),
    "securecrt": ("SSH2", "Session Manager", "2 active tabs"),
    "termius": ("Vault unlocked", "Port fwd ready", "Sync current"),
    "remmina": ("RDP/VNC ready", "Scale 100%", "Clipboard on"),
    "mremoteng": ("Connections.xml", "Inheritance on", "2 open panes"),
}
GUI_DESIGN_TREE_ROOT_COPY: dict[str, tuple[str, str]] = {
    DEFAULT_GUI_DESIGN_ID: ("Profiles", "Saved Remote Ops Workspace sessions"),
    "mobaxterm": ("User sessions", "MobaXterm-style saved user sessions"),
    "securecrt": ("Session Database", "SecureCRT-style foldered terminal sessions"),
    "termius": ("Personal Vault", "Termius-style encrypted host inventory"),
    "remmina": ("Profile Groups", "Remmina-style protocol connection profiles"),
    "mremoteng": ("Connections", "mRemoteNG-style nested connection tree"),
}


@dataclass(frozen=True)
class GuiDesignTreeRowIcon:
    label: str
    icon_key: str
    row_kind: str
    static_size: int


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


GUI_DESIGN_TREE_ROOT_ICONS: dict[str, GuiDesignTreeRowIcon] = {
    DEFAULT_GUI_DESIGN_ID: GuiDesignTreeRowIcon("Profiles", "folder", "root", 16),
    "mobaxterm": GuiDesignTreeRowIcon("User sessions", "folder", "root", 16),
    "securecrt": GuiDesignTreeRowIcon("Session Database", "database", "root", 16),
    "termius": GuiDesignTreeRowIcon("Personal Vault", "database", "root", 16),
    "remmina": GuiDesignTreeRowIcon("Profile Groups", "folder", "root", 16),
    "mremoteng": GuiDesignTreeRowIcon("Connections", "database", "root", 16),
}


GUI_DESIGN_TREE_ROW_ICONS: dict[str, tuple[GuiDesignTreeRowIcon, ...]] = {
    "mobaxterm": (
        GuiDesignTreeRowIcon("default", "folder", "group", 15),
        GuiDesignTreeRowIcon("example.jump-ssh", "pin", "profile", 14),
        GuiDesignTreeRowIcon("example.rdp", "rdp", "profile", 14),
        GuiDesignTreeRowIcon("prod", "folder", "group", 15),
        GuiDesignTreeRowIcon("edge-prod", "ssh", "profile", 14),
        GuiDesignTreeRowIcon("win-admin", "rdp", "profile", 14),
        GuiDesignTreeRowIcon("files", "folder", "group", 15),
        GuiDesignTreeRowIcon("sftp-ops", "sftp", "profile", 14),
        GuiDesignTreeRowIcon("sync-stage", "ssh", "profile", 14),
    ),
    "securecrt": (
        GuiDesignTreeRowIcon("Sessions", "folder", "group", 14),
        GuiDesignTreeRowIcon("edge-prod (SSH2)", "ssh2", "profile", 14),
        GuiDesignTreeRowIcon("files-prod (SFTP)", "sftp", "profile", 14),
        GuiDesignTreeRowIcon("Local Shells", "folder", "group", 14),
        GuiDesignTreeRowIcon("PowerShell", "shell", "profile", 14),
        GuiDesignTreeRowIcon("Net tools", "command", "profile", 14),
        GuiDesignTreeRowIcon("Pinned", "folder", "group", 14),
        GuiDesignTreeRowIcon("jump-host (SSH2)", "pin", "profile", 14),
    ),
    "termius": (
        GuiDesignTreeRowIcon("Personal", "folder", "group", 14),
        GuiDesignTreeRowIcon("edge-prod", "host", "profile", 14),
        GuiDesignTreeRowIcon("jump-host", "pin", "profile", 14),
        GuiDesignTreeRowIcon("Teams", "folder", "group", 14),
        GuiDesignTreeRowIcon("prod-cluster", "host", "profile", 14),
        GuiDesignTreeRowIcon("Snippets", "folder", "group", 14),
        GuiDesignTreeRowIcon("deploy-check", "snippet", "profile", 14),
    ),
    "remmina": (
        GuiDesignTreeRowIcon("RDP", "folder", "group", 14),
        GuiDesignTreeRowIcon("win-admin", "rdp", "profile", 14),
        GuiDesignTreeRowIcon("lab-desktop", "rdp", "profile", 14),
        GuiDesignTreeRowIcon("VNC", "folder", "group", 14),
        GuiDesignTreeRowIcon("linux-console", "vnc", "profile", 14),
        GuiDesignTreeRowIcon("SSH/SFTP", "folder", "group", 14),
        GuiDesignTreeRowIcon("sftp-ops", "sftp", "profile", 14),
    ),
    "mremoteng": (
        GuiDesignTreeRowIcon("Connections.xml", "database", "group", 14),
        GuiDesignTreeRowIcon("prod", "folder", "group", 14),
        GuiDesignTreeRowIcon("edge-prod [SSH]", "ssh", "profile", 14),
        GuiDesignTreeRowIcon("win-admin [RDP]", "rdp", "profile", 14),
        GuiDesignTreeRowIcon("files", "folder", "group", 14),
        GuiDesignTreeRowIcon("sftp-ops [SFTP]", "sftp", "profile", 14),
        GuiDesignTreeRowIcon("tools", "folder", "group", 14),
        GuiDesignTreeRowIcon("net-tools [SSH]", "ssh", "profile", 14),
    ),
}

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
GUI_DESIGN_TREE_ROWS: dict[str, tuple[tuple[str, str, bool], ...]] = {
    DEFAULT_GUI_DESIGN_ID: (
        ("default", "", True),
        ("  example.jump-ssh", "ssh jump.example", False),
        ("  example.rdp", "rdp win-lab.example", False),
        ("prod", "", True),
        ("  edge-prod", "ssh edge-prod.example", False),
        ("  win-admin", "rdp admin-win.example", False),
        ("files", "", True),
        ("  sftp-ops", "sftp logs.example", False),
        ("  sync-stage", "sync staging-share", False),
    ),
    "mobaxterm": (
        ("default", "", True),
        ("  example.jump-ssh", "ssh jump.example", False),
        ("  example.rdp", "rdp win-lab.example", False),
        ("prod", "", True),
        ("  edge-prod", "ssh edge-prod.example", False),
        ("  win-admin", "rdp admin-win.example", False),
        ("files", "", True),
        ("  sftp-ops", "sftp logs.example", False),
        ("  sync-stage", "sync staging-share", False),
    ),
    "securecrt": (
        ("Sessions", "", True),
        ("  edge-prod (SSH2)", "terminal profile, compression on", False),
        ("  files-prod (SFTP)", "file transfer session", False),
        ("Local Shells", "", True),
        ("  PowerShell", "local terminal", False),
        ("  Net tools", "command tab", False),
        ("Pinned", "", True),
        ("  jump-host (SSH2)", "session manager favorite", False),
    ),
    "termius": (
        ("Personal", "", True),
        ("  edge-prod", "ssh / vault key", False),
        ("  jump-host", "ssh / port forwarding", False),
        ("Teams", "", True),
        ("  prod-cluster", "shared host chain", False),
        ("Snippets", "", True),
        ("  deploy-check", "row vault status", False),
    ),
    "remmina": (
        ("RDP", "", True),
        ("  win-admin", "rdp / scale 100%", False),
        ("  lab-desktop", "rdp / clipboard on", False),
        ("VNC", "", True),
        ("  linux-console", "vnc / fit window", False),
        ("SSH/SFTP", "", True),
        ("  sftp-ops", "ssh file sharing", False),
    ),
    "mremoteng": (
        ("Connections.xml", "", True),
        ("  prod", "", True),
        ("    edge-prod [SSH]", "inherits prod credentials", False),
        ("    win-admin [RDP]", "external app ready", False),
        ("  files", "", True),
        ("    sftp-ops [SFTP]", "nested group item", False),
        ("  tools", "", True),
        ("    net-tools [SSH]", "open in document tab", False),
    ),
}
GUI_DESIGN_HOME_TAB_COPY: dict[str, str] = {
    DEFAULT_GUI_DESIGN_ID: "Welcome",
    "mobaxterm": "Home",
    "securecrt": "Start Page",
    "termius": "Hosts",
    "remmina": "Quick Connect",
    "mremoteng": "Start Page",
}
GUI_DESIGN_TAB_COPY: dict[str, tuple[tuple[str, str, bool], ...]] = {
    DEFAULT_GUI_DESIGN_ID: (
        ("edge-prod", "ssh", True),
        ("files-prod", "sftp", False),
        ("Split 3", "layout", False),
        ("Welcome", "home", False),
    ),
    "securecrt": (
        ("edge-prod", "SSH2", True),
        ("files-prod", "SFTP", False),
        ("PowerShell", "Local", False),
        ("Start Page", "home", False),
    ),
    "termius": (
        ("edge-prod", "SSH", True),
        ("files", "SFTP", False),
        ("vault", "Keys", False),
        ("+", "New", False),
    ),
    "remmina": (
        ("win-admin", "RDP", True),
        ("linux-console", "VNC", False),
        ("sftp-ops", "SFTP", False),
        ("Quick Connect", "home", False),
    ),
    "mremoteng": (
        ("edge-prod [SSH]", "doc", True),
        ("win-admin [RDP]", "doc", False),
        ("sftp-ops", "external", False),
        ("Start Page", "home", False),
    ),
}


@dataclass(frozen=True)
class GuiInteractionState:
    active_toolbar_key: str
    checked_toolbar_key: str
    disabled_toolbar_key: str
    focused_control: str
    active_tab_status: str
    selected_tree_label: str
    status_note: str


GUI_DESIGN_INTERACTION_STATES: dict[str, GuiInteractionState] = {
    DEFAULT_GUI_DESIGN_ID: GuiInteractionState(
        active_toolbar_key="connect",
        checked_toolbar_key="files",
        disabled_toolbar_key="",
        focused_control="search-log",
        active_tab_status="running",
        selected_tree_label="edge-prod",
        status_note="focused search, active connect, checked files; destructive actions follow selection",
    ),
    "mobaxterm": GuiInteractionState(
        active_toolbar_key="sessions",
        checked_toolbar_key="sftp",
        disabled_toolbar_key="",
        focused_control="quick-connect",
        active_tab_status="SSH direct",
        selected_tree_label="sftp-ops",
        status_note="quick connect focus, SFTP rail checked, explicit games support status available",
    ),
    "securecrt": GuiInteractionState(
        active_toolbar_key="connect",
        checked_toolbar_key="files",
        disabled_toolbar_key="",
        focused_control="session-filter",
        active_tab_status="SSH2 connected",
        selected_tree_label="edge-prod (SSH2)",
        status_note="Session Manager focus, SFTP checked, delete follows selection",
    ),
    "termius": GuiInteractionState(
        active_toolbar_key="connect",
        checked_toolbar_key="doctor",
        disabled_toolbar_key="",
        focused_control="host-search",
        active_tab_status="vault unlocked",
        selected_tree_label="edge-prod  ssh host",
        status_note="host search focus, vault checked, remove follows selection",
    ),
    "remmina": GuiInteractionState(
        active_toolbar_key="connect",
        checked_toolbar_key="queue",
        disabled_toolbar_key="",
        focused_control="profile-filter",
        active_tab_status="viewer scaled",
        selected_tree_label="linux-console",
        status_note="profile filter focus, transfer checked, delete follows selection",
    ),
    "mremoteng": GuiInteractionState(
        active_toolbar_key="connect",
        checked_toolbar_key="files",
        disabled_toolbar_key="",
        focused_control="tree-filter",
        active_tab_status="document open",
        selected_tree_label="edge-prod [SSH]",
        status_note="connection tree focus, external tool checked, delete follows selection",
    ),
}


@dataclass(frozen=True)
class GuiDesignColors:
    window: str
    toolbar: str
    toolbar_border: str
    control: str
    control_text: str
    control_border: str
    control_hover: str
    primary: str
    primary_text: str
    danger: str
    danger_text: str
    sidebar: str
    sidebar_text: str
    sidebar_muted: str
    sidebar_selected: str
    sidebar_selected_text: str
    pane: str
    pane_border: str
    tab: str
    tab_selected: str
    tab_text: str
    tab_selected_text: str
    terminal: str
    terminal_text: str
    terminal_accent: str
    log: str
    log_text: str
    status: str


@dataclass(frozen=True)
class GuiDesignPreset:
    id: str
    label: str
    description: str
    profile_width: int
    log_height: int
    tab_position: str
    density: str
    toolbar_icon_size: int
    list_spacing: int
    document_mode: bool
    colors: GuiDesignColors
    stylesheet: str


@dataclass(frozen=True)
class GuiWorkspaceSurface:
    title: str
    subtitle: str
    primary_title: str
    primary_state: str
    command_line: str
    secondary_title: str
    secondary_state: str
    detail_lines: tuple[str, ...]
    activity_lines: tuple[str, ...]
    home_actions: tuple[str, ...]
    home_search_placeholder: str
    recent_columns: tuple[tuple[str, ...], ...]
    footer: str


@dataclass(frozen=True)
class GuiProductWorkflowCard:
    key: str
    title: str
    primary: str
    secondary: str


@dataclass(frozen=True)
class GuiProductReferenceState:
    profile_name: str
    target_label: str
    protocol_label: str
    active_tab_label: str
    sidebar_label: str
    workspace_state: str
    status_segments: tuple[str, ...]

    def items(self) -> tuple[tuple[str, str], ...]:
        return (
            ("profile", self.profile_name),
            ("target", self.target_label),
            ("protocol", self.protocol_label),
            ("active-tab", self.active_tab_label),
            ("sidebar", self.sidebar_label),
            ("state", self.workspace_state),
        )


@dataclass(frozen=True)
class GuiProductIdentityRoute:
    key: str
    route_role: str
    preset_id: str
    selected_profile_name: str
    selected_tree_label: str
    target_label: str
    protocol_label: str
    active_tab_label: str
    sidebar_label: str
    workspace_state: str
    status_segments: tuple[str, ...]
    reference_state_object: str
    reference_item_object: str
    tree_object: str
    tabs_object: str
    status_segment_object: str
    workspace_surface_object: str
    profile_property: str
    target_property: str
    protocol_property: str
    active_tab_property: str
    sidebar_property: str
    workspace_state_property: str
    status_segments_property: str
    render_source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "route_role": self.route_role,
            "preset_id": self.preset_id,
            "selected_profile_name": self.selected_profile_name,
            "selected_tree_label": self.selected_tree_label,
            "target_label": self.target_label,
            "protocol_label": self.protocol_label,
            "active_tab_label": self.active_tab_label,
            "sidebar_label": self.sidebar_label,
            "workspace_state": self.workspace_state,
            "status_segments": list(self.status_segments),
            "reference_state_object": self.reference_state_object,
            "reference_item_object": self.reference_item_object,
            "tree_object": self.tree_object,
            "tabs_object": self.tabs_object,
            "status_segment_object": self.status_segment_object,
            "workspace_surface_object": self.workspace_surface_object,
            "profile_property": self.profile_property,
            "target_property": self.target_property,
            "protocol_property": self.protocol_property,
            "active_tab_property": self.active_tab_property,
            "sidebar_property": self.sidebar_property,
            "workspace_state_property": self.workspace_state_property,
            "status_segments_property": self.status_segments_property,
            "render_source": self.render_source,
        }


@dataclass(frozen=True)
class GuiPresetReferenceTabRoute:
    key: str
    route_role: str
    preset_id: str
    reference_profile: str
    active_tab_label: str
    home_tab_label: str
    tabs_object: str
    home_tab_role: str
    reference_tab_role: str
    activated_label_property: str
    returned_home_label_property: str
    active_tab_property: str
    home_tab_property: str
    reference_profile_property: str
    render_source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "route_role": self.route_role,
            "preset_id": self.preset_id,
            "reference_profile": self.reference_profile,
            "active_tab_label": self.active_tab_label,
            "home_tab_label": self.home_tab_label,
            "tabs_object": self.tabs_object,
            "home_tab_role": self.home_tab_role,
            "reference_tab_role": self.reference_tab_role,
            "activated_label_property": self.activated_label_property,
            "returned_home_label_property": self.returned_home_label_property,
            "active_tab_property": self.active_tab_property,
            "home_tab_property": self.home_tab_property,
            "reference_profile_property": self.reference_profile_property,
            "render_source": self.render_source,
        }


@dataclass(frozen=True)
class GuiPresetReferenceTabChromeRoute:
    key: str
    route_role: str
    preset_id: str
    reference_profile: str
    active_tab_label: str
    home_tab_label: str
    tabs_object: str
    tab_bar_object: str
    reference_tab_role: str
    new_session_tab_role: str
    expected_tab_position: str
    expected_tooltip: str
    expected_closeable: bool
    expected_selected_during_capture: bool
    captured_property: str
    captured_label_property: str
    captured_tooltip_property: str
    captured_index_property: str
    captured_role_property: str
    captured_position_property: str
    captured_closeable_property: str
    captured_selected_property: str
    render_source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "route_role": self.route_role,
            "preset_id": self.preset_id,
            "reference_profile": self.reference_profile,
            "active_tab_label": self.active_tab_label,
            "home_tab_label": self.home_tab_label,
            "tabs_object": self.tabs_object,
            "tab_bar_object": self.tab_bar_object,
            "reference_tab_role": self.reference_tab_role,
            "new_session_tab_role": self.new_session_tab_role,
            "expected_tab_position": self.expected_tab_position,
            "expected_tooltip": self.expected_tooltip,
            "expected_closeable": self.expected_closeable,
            "expected_selected_during_capture": self.expected_selected_during_capture,
            "captured_property": self.captured_property,
            "captured_label_property": self.captured_label_property,
            "captured_tooltip_property": self.captured_tooltip_property,
            "captured_index_property": self.captured_index_property,
            "captured_role_property": self.captured_role_property,
            "captured_position_property": self.captured_position_property,
            "captured_closeable_property": self.captured_closeable_property,
            "captured_selected_property": self.captured_selected_property,
            "render_source": self.render_source,
        }


@dataclass(frozen=True)
class GuiPresetReferenceStatusBarRoute:
    key: str
    route_role: str
    preset_id: str
    reference_profile: str
    active_tab_label: str
    status_bar_object: str
    status_notice_object: str
    status_segment_object: str
    expected_status_message: str
    expected_status_segments: tuple[str, ...]
    expected_segment_count: int
    captured_property: str
    captured_tab_property: str
    captured_message_property: str
    captured_segments_property: str
    captured_segment_count_property: str
    captured_segment_tooltips_property: str
    captured_notice_property: str
    render_source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "route_role": self.route_role,
            "preset_id": self.preset_id,
            "reference_profile": self.reference_profile,
            "active_tab_label": self.active_tab_label,
            "status_bar_object": self.status_bar_object,
            "status_notice_object": self.status_notice_object,
            "status_segment_object": self.status_segment_object,
            "expected_status_message": self.expected_status_message,
            "expected_status_segments": list(self.expected_status_segments),
            "expected_segment_count": self.expected_segment_count,
            "captured_property": self.captured_property,
            "captured_tab_property": self.captured_tab_property,
            "captured_message_property": self.captured_message_property,
            "captured_segments_property": self.captured_segments_property,
            "captured_segment_count_property": self.captured_segment_count_property,
            "captured_segment_tooltips_property": self.captured_segment_tooltips_property,
            "captured_notice_property": self.captured_notice_property,
            "render_source": self.render_source,
        }


@dataclass(frozen=True)
class GuiPresetReferenceSessionActionRoute:
    key: str
    route_role: str
    preset_id: str
    reference_profile: str
    active_tab_label: str
    tabs_object: str
    tab_bar_object: str
    reference_tab_role: str
    action_object: str
    expected_action_keys: tuple[str, ...]
    expected_action_labels: tuple[str, ...]
    expected_action_count: int
    always_enabled_action_keys: tuple[str, ...]
    conditional_enabled_action_keys: tuple[str, ...]
    action_key_property: str
    action_label_property: str
    action_enabled_property: str
    captured_property: str
    captured_tab_property: str
    captured_action_keys_property: str
    captured_action_labels_property: str
    captured_action_count_property: str
    captured_enabled_keys_property: str
    captured_disabled_keys_property: str
    render_source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "route_role": self.route_role,
            "preset_id": self.preset_id,
            "reference_profile": self.reference_profile,
            "active_tab_label": self.active_tab_label,
            "tabs_object": self.tabs_object,
            "tab_bar_object": self.tab_bar_object,
            "reference_tab_role": self.reference_tab_role,
            "action_object": self.action_object,
            "expected_action_keys": list(self.expected_action_keys),
            "expected_action_labels": list(self.expected_action_labels),
            "expected_action_count": self.expected_action_count,
            "always_enabled_action_keys": list(self.always_enabled_action_keys),
            "conditional_enabled_action_keys": list(self.conditional_enabled_action_keys),
            "action_key_property": self.action_key_property,
            "action_label_property": self.action_label_property,
            "action_enabled_property": self.action_enabled_property,
            "captured_property": self.captured_property,
            "captured_tab_property": self.captured_tab_property,
            "captured_action_keys_property": self.captured_action_keys_property,
            "captured_action_labels_property": self.captured_action_labels_property,
            "captured_action_count_property": self.captured_action_count_property,
            "captured_enabled_keys_property": self.captured_enabled_keys_property,
            "captured_disabled_keys_property": self.captured_disabled_keys_property,
            "render_source": self.render_source,
        }


@dataclass(frozen=True)
class GuiPresetReferenceSurfaceRoute:
    key: str
    route_role: str
    preset_id: str
    reference_profile: str
    active_tab_label: str
    expected_title: str
    expected_source: str
    command_executables: tuple[str, ...]
    command_target_fragment: str
    terminal_pane_object: str
    terminal_title_object: str
    terminal_source_object: str
    terminal_command_object: str
    terminal_output_object: str
    captured_property: str
    captured_tab_property: str
    actual_title_property: str
    actual_source_property: str
    actual_command_property: str
    actual_output_property: str
    render_source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "route_role": self.route_role,
            "preset_id": self.preset_id,
            "reference_profile": self.reference_profile,
            "active_tab_label": self.active_tab_label,
            "expected_title": self.expected_title,
            "expected_source": self.expected_source,
            "command_executables": list(self.command_executables),
            "command_target_fragment": self.command_target_fragment,
            "terminal_pane_object": self.terminal_pane_object,
            "terminal_title_object": self.terminal_title_object,
            "terminal_source_object": self.terminal_source_object,
            "terminal_command_object": self.terminal_command_object,
            "terminal_output_object": self.terminal_output_object,
            "captured_property": self.captured_property,
            "captured_tab_property": self.captured_tab_property,
            "actual_title_property": self.actual_title_property,
            "actual_source_property": self.actual_source_property,
            "actual_command_property": self.actual_command_property,
            "actual_output_property": self.actual_output_property,
            "render_source": self.render_source,
        }


@dataclass(frozen=True)
class GuiPresetReferenceControlRoute:
    key: str
    route_role: str
    preset_id: str
    reference_profile: str
    active_tab_label: str
    terminal_pane_object: str
    terminal_status_object: str
    terminal_action_object: str
    action_keys: tuple[str, ...]
    action_labels: tuple[str, ...]
    action_tooltips: tuple[str, ...]
    allowed_status_states: tuple[str, ...]
    action_key_property: str
    action_label_property: str
    action_tooltip_property: str
    status_state_property: str
    captured_property: str
    captured_actions_property: str
    captured_status_property: str
    captured_status_text_property: str
    render_source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "route_role": self.route_role,
            "preset_id": self.preset_id,
            "reference_profile": self.reference_profile,
            "active_tab_label": self.active_tab_label,
            "terminal_pane_object": self.terminal_pane_object,
            "terminal_status_object": self.terminal_status_object,
            "terminal_action_object": self.terminal_action_object,
            "action_keys": list(self.action_keys),
            "action_labels": list(self.action_labels),
            "action_tooltips": list(self.action_tooltips),
            "allowed_status_states": list(self.allowed_status_states),
            "action_key_property": self.action_key_property,
            "action_label_property": self.action_label_property,
            "action_tooltip_property": self.action_tooltip_property,
            "status_state_property": self.status_state_property,
            "captured_property": self.captured_property,
            "captured_actions_property": self.captured_actions_property,
            "captured_status_property": self.captured_status_property,
            "captured_status_text_property": self.captured_status_text_property,
            "render_source": self.render_source,
        }


@dataclass(frozen=True)
class GuiPresetReferenceInputRoute:
    key: str
    route_role: str
    preset_id: str
    reference_profile: str
    active_tab_label: str
    terminal_pane_object: str
    terminal_input_object: str
    placeholder_text: str
    expected_initial_text: str
    allowed_enabled_states: tuple[bool, ...]
    captured_property: str
    captured_tab_property: str
    captured_placeholder_property: str
    captured_text_property: str
    captured_enabled_property: str
    render_source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "route_role": self.route_role,
            "preset_id": self.preset_id,
            "reference_profile": self.reference_profile,
            "active_tab_label": self.active_tab_label,
            "terminal_pane_object": self.terminal_pane_object,
            "terminal_input_object": self.terminal_input_object,
            "placeholder_text": self.placeholder_text,
            "expected_initial_text": self.expected_initial_text,
            "allowed_enabled_states": list(self.allowed_enabled_states),
            "captured_property": self.captured_property,
            "captured_tab_property": self.captured_tab_property,
            "captured_placeholder_property": self.captured_placeholder_property,
            "captured_text_property": self.captured_text_property,
            "captured_enabled_property": self.captured_enabled_property,
            "render_source": self.render_source,
        }


@dataclass(frozen=True)
class GuiPresetReferenceTranscriptRoute:
    key: str
    route_role: str
    preset_id: str
    reference_profile: str
    active_tab_label: str
    terminal_pane_object: str
    terminal_output_object: str
    command_echo_prefix: str
    required_fragments: tuple[str, ...]
    minimum_line_count: int
    captured_property: str
    captured_tab_property: str
    captured_text_property: str
    captured_line_count_property: str
    captured_command_echo_property: str
    render_source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "route_role": self.route_role,
            "preset_id": self.preset_id,
            "reference_profile": self.reference_profile,
            "active_tab_label": self.active_tab_label,
            "terminal_pane_object": self.terminal_pane_object,
            "terminal_output_object": self.terminal_output_object,
            "command_echo_prefix": self.command_echo_prefix,
            "required_fragments": list(self.required_fragments),
            "minimum_line_count": self.minimum_line_count,
            "captured_property": self.captured_property,
            "captured_tab_property": self.captured_tab_property,
            "captured_text_property": self.captured_text_property,
            "captured_line_count_property": self.captured_line_count_property,
            "captured_command_echo_property": self.captured_command_echo_property,
            "render_source": self.render_source,
        }


@dataclass(frozen=True)
class GuiPresetSelectionRoute:
    key: str
    route_role: str
    preset_id: str
    preset_label: str
    preset_index: int
    selector_object: str
    main_toolbar_object: str
    layout_toolbar_object: str
    left_panel_header_object: str
    profile_tree_object: str
    tabs_object: str
    status_bar_object: str
    status_segment_object: str
    workspace_surface_object: str
    reference_state_object: str
    home_tab_label: str
    sidebar_title: str
    sidebar_subtitle: str
    status_segments: tuple[str, ...]
    tab_position: str
    document_mode: bool
    profile_width: int
    log_height: int
    toolbar_icon_size: int
    selector_property: str
    preset_label_property: str
    home_tab_property: str
    sidebar_title_property: str
    status_segments_property: str
    render_source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "route_role": self.route_role,
            "preset_id": self.preset_id,
            "preset_label": self.preset_label,
            "preset_index": self.preset_index,
            "selector_object": self.selector_object,
            "main_toolbar_object": self.main_toolbar_object,
            "layout_toolbar_object": self.layout_toolbar_object,
            "left_panel_header_object": self.left_panel_header_object,
            "profile_tree_object": self.profile_tree_object,
            "tabs_object": self.tabs_object,
            "status_bar_object": self.status_bar_object,
            "status_segment_object": self.status_segment_object,
            "workspace_surface_object": self.workspace_surface_object,
            "reference_state_object": self.reference_state_object,
            "home_tab_label": self.home_tab_label,
            "sidebar_title": self.sidebar_title,
            "sidebar_subtitle": self.sidebar_subtitle,
            "status_segments": list(self.status_segments),
            "tab_position": self.tab_position,
            "document_mode": self.document_mode,
            "profile_width": self.profile_width,
            "log_height": self.log_height,
            "toolbar_icon_size": self.toolbar_icon_size,
            "selector_property": self.selector_property,
            "preset_label_property": self.preset_label_property,
            "home_tab_property": self.home_tab_property,
            "sidebar_title_property": self.sidebar_title_property,
            "status_segments_property": self.status_segments_property,
            "render_source": self.render_source,
        }


@dataclass(frozen=True)
class GuiPresetCatalogRoute:
    key: str
    route_role: str
    selector_object: str
    option_ids: tuple[str, ...]
    option_labels: tuple[str, ...]
    product_preset_ids: tuple[str, ...]
    product_preset_labels: tuple[str, ...]
    default_preset_id: str
    default_preset_label: str
    option_count: int
    product_option_count: int
    selector_property: str
    option_labels_property: str
    product_ids_property: str
    default_property: str
    render_source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "route_role": self.route_role,
            "selector_object": self.selector_object,
            "option_ids": list(self.option_ids),
            "option_labels": list(self.option_labels),
            "product_preset_ids": list(self.product_preset_ids),
            "product_preset_labels": list(self.product_preset_labels),
            "default_preset_id": self.default_preset_id,
            "default_preset_label": self.default_preset_label,
            "option_count": self.option_count,
            "product_option_count": self.product_option_count,
            "selector_property": self.selector_property,
            "option_labels_property": self.option_labels_property,
            "product_ids_property": self.product_ids_property,
            "default_property": self.default_property,
            "render_source": self.render_source,
        }


@dataclass(frozen=True)
class GuiPresetVisualSignature:
    key: str
    route_role: str
    preset_id: str
    preset_label: str
    density: str
    tab_position: str
    document_mode: bool
    profile_width: int
    log_height: int
    toolbar_icon_size: int
    list_spacing: int
    window_color: str
    toolbar_color: str
    toolbar_border_color: str
    control_color: str
    control_text_color: str
    primary_color: str
    sidebar_color: str
    sidebar_selected_color: str
    pane_color: str
    pane_border_color: str
    tab_color: str
    tab_selected_color: str
    terminal_color: str
    terminal_text_color: str
    terminal_accent_color: str
    status_color: str
    window_object: str
    main_toolbar_object: str
    layout_toolbar_object: str
    left_panel_object: str
    profile_tree_object: str
    tabs_object: str
    activity_log_object: str
    status_bar_object: str
    density_property: str
    palette_property: str
    render_source: str

    def palette_items(self) -> tuple[tuple[str, str], ...]:
        return (
            ("window", self.window_color),
            ("toolbar", self.toolbar_color),
            ("toolbar_border", self.toolbar_border_color),
            ("control", self.control_color),
            ("control_text", self.control_text_color),
            ("primary", self.primary_color),
            ("sidebar", self.sidebar_color),
            ("sidebar_selected", self.sidebar_selected_color),
            ("pane", self.pane_color),
            ("pane_border", self.pane_border_color),
            ("tab", self.tab_color),
            ("tab_selected", self.tab_selected_color),
            ("terminal", self.terminal_color),
            ("terminal_text", self.terminal_text_color),
            ("terminal_accent", self.terminal_accent_color),
            ("status", self.status_color),
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "route_role": self.route_role,
            "preset_id": self.preset_id,
            "preset_label": self.preset_label,
            "density": self.density,
            "tab_position": self.tab_position,
            "document_mode": self.document_mode,
            "profile_width": self.profile_width,
            "log_height": self.log_height,
            "toolbar_icon_size": self.toolbar_icon_size,
            "list_spacing": self.list_spacing,
            "palette": dict(self.palette_items()),
            "window_object": self.window_object,
            "main_toolbar_object": self.main_toolbar_object,
            "layout_toolbar_object": self.layout_toolbar_object,
            "left_panel_object": self.left_panel_object,
            "profile_tree_object": self.profile_tree_object,
            "tabs_object": self.tabs_object,
            "activity_log_object": self.activity_log_object,
            "status_bar_object": self.status_bar_object,
            "density_property": self.density_property,
            "palette_property": self.palette_property,
            "render_source": self.render_source,
        }


@dataclass(frozen=True)
class GuiPresetIsolationRoute:
    key: str
    route_role: str
    preset_id: str
    visible_objects: tuple[str, ...]
    hidden_objects: tuple[str, ...]
    visible_property: str
    hidden_property: str
    render_source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "route_role": self.route_role,
            "preset_id": self.preset_id,
            "visible_objects": list(self.visible_objects),
            "hidden_objects": list(self.hidden_objects),
            "visible_property": self.visible_property,
            "hidden_property": self.hidden_property,
            "render_source": self.render_source,
        }


@dataclass(frozen=True)
class GuiPresetKeyboardShortcutRoute:
    key: str
    route_role: str
    preset_id: str
    shortcut_object: str
    expected_shortcut_keys: tuple[str, ...]
    expected_sequences: tuple[str, ...]
    expected_action_labels: tuple[str, ...]
    expected_shortcut_count: int
    shortcut_key_property: str
    shortcut_sequence_property: str
    shortcut_action_property: str
    captured_property: str
    captured_keys_property: str
    captured_sequences_property: str
    captured_action_labels_property: str
    captured_count_property: str
    render_source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "route_role": self.route_role,
            "preset_id": self.preset_id,
            "shortcut_object": self.shortcut_object,
            "expected_shortcut_keys": list(self.expected_shortcut_keys),
            "expected_sequences": list(self.expected_sequences),
            "expected_action_labels": list(self.expected_action_labels),
            "expected_shortcut_count": self.expected_shortcut_count,
            "shortcut_key_property": self.shortcut_key_property,
            "shortcut_sequence_property": self.shortcut_sequence_property,
            "shortcut_action_property": self.shortcut_action_property,
            "captured_property": self.captured_property,
            "captured_keys_property": self.captured_keys_property,
            "captured_sequences_property": self.captured_sequences_property,
            "captured_action_labels_property": self.captured_action_labels_property,
            "captured_count_property": self.captured_count_property,
            "render_source": self.render_source,
        }


@dataclass(frozen=True)
class GuiPresetCommandSurfaceRoute:
    key: str
    route_role: str
    preset_id: str
    toolbar_object: str
    command_object: str
    expected_action_keys: tuple[str, ...]
    expected_action_labels: tuple[str, ...]
    expected_action_tooltips: tuple[str, ...]
    expected_action_states: tuple[tuple[str, str], ...]
    expected_action_count: int
    key_property: str
    label_property: str
    tooltip_property: str
    state_property: str
    captured_property: str
    captured_keys_property: str
    captured_labels_property: str
    captured_tooltips_property: str
    captured_states_property: str
    captured_count_property: str
    render_source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "route_role": self.route_role,
            "preset_id": self.preset_id,
            "toolbar_object": self.toolbar_object,
            "command_object": self.command_object,
            "expected_action_keys": list(self.expected_action_keys),
            "expected_action_labels": list(self.expected_action_labels),
            "expected_action_tooltips": list(self.expected_action_tooltips),
            "expected_action_states": {key: state for key, state in self.expected_action_states},
            "expected_action_count": self.expected_action_count,
            "key_property": self.key_property,
            "label_property": self.label_property,
            "tooltip_property": self.tooltip_property,
            "state_property": self.state_property,
            "captured_property": self.captured_property,
            "captured_keys_property": self.captured_keys_property,
            "captured_labels_property": self.captured_labels_property,
            "captured_tooltips_property": self.captured_tooltips_property,
            "captured_states_property": self.captured_states_property,
            "captured_count_property": self.captured_count_property,
            "render_source": self.render_source,
        }


@dataclass(frozen=True)
class GuiPresetFocusInteractionRoute:
    key: str
    route_role: str
    preset_id: str
    focused_control: str
    focus_object: str
    active_toolbar_key: str
    checked_toolbar_key: str
    disabled_toolbar_key: str
    selected_tree_label: str
    active_tab_status: str
    status_note: str
    status_bar_object: str
    profile_tree_object: str
    focused_state_property: str
    captured_property: str
    captured_focus_property: str
    captured_focus_state_property: str
    captured_status_message_property: str
    captured_selected_tree_property: str
    captured_toolbar_states_property: str
    render_source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "route_role": self.route_role,
            "preset_id": self.preset_id,
            "focused_control": self.focused_control,
            "focus_object": self.focus_object,
            "active_toolbar_key": self.active_toolbar_key,
            "checked_toolbar_key": self.checked_toolbar_key,
            "disabled_toolbar_key": self.disabled_toolbar_key,
            "selected_tree_label": self.selected_tree_label,
            "active_tab_status": self.active_tab_status,
            "status_note": self.status_note,
            "status_bar_object": self.status_bar_object,
            "profile_tree_object": self.profile_tree_object,
            "focused_state_property": self.focused_state_property,
            "captured_property": self.captured_property,
            "captured_focus_property": self.captured_focus_property,
            "captured_focus_state_property": self.captured_focus_state_property,
            "captured_status_message_property": self.captured_status_message_property,
            "captured_selected_tree_property": self.captured_selected_tree_property,
            "captured_toolbar_states_property": self.captured_toolbar_states_property,
            "render_source": self.render_source,
        }


@dataclass(frozen=True)
class GuiPresetHomeSearchRoute:
    key: str
    route_role: str
    preset_id: str
    home_tab_label: str
    home_search_object: str
    entry_search_control: str
    entry_search_object: str
    container_object: str
    recent_label_object: str
    placeholder_text: str
    entry_placeholder_text: str
    expected_home_actions: tuple[str, ...]
    expected_recent_labels: tuple[str, ...]
    expected_recent_count: int
    placeholder_property: str
    entry_placeholder_property: str
    captured_property: str
    captured_placeholder_property: str
    captured_entry_placeholder_property: str
    captured_text_property: str
    captured_entry_text_property: str
    captured_actions_property: str
    captured_recent_labels_property: str
    captured_recent_count_property: str
    render_source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "route_role": self.route_role,
            "preset_id": self.preset_id,
            "home_tab_label": self.home_tab_label,
            "home_search_object": self.home_search_object,
            "entry_search_control": self.entry_search_control,
            "entry_search_object": self.entry_search_object,
            "container_object": self.container_object,
            "recent_label_object": self.recent_label_object,
            "placeholder_text": self.placeholder_text,
            "entry_placeholder_text": self.entry_placeholder_text,
            "expected_home_actions": list(self.expected_home_actions),
            "expected_recent_labels": list(self.expected_recent_labels),
            "expected_recent_count": self.expected_recent_count,
            "placeholder_property": self.placeholder_property,
            "entry_placeholder_property": self.entry_placeholder_property,
            "captured_property": self.captured_property,
            "captured_placeholder_property": self.captured_placeholder_property,
            "captured_entry_placeholder_property": self.captured_entry_placeholder_property,
            "captured_text_property": self.captured_text_property,
            "captured_entry_text_property": self.captured_entry_text_property,
            "captured_actions_property": self.captured_actions_property,
            "captured_recent_labels_property": self.captured_recent_labels_property,
            "captured_recent_count_property": self.captured_recent_count_property,
            "render_source": self.render_source,
        }


@dataclass(frozen=True)
class GuiPresetTransitionRoute:
    key: str
    route_role: str
    from_preset_ids: tuple[str, ...]
    to_preset_id: str
    to_preset_index: int
    selector_object: str
    reset_objects: tuple[str, ...]
    route_property: str
    from_property: str
    to_property: str
    reset_property: str
    render_source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "route_role": self.route_role,
            "from_preset_ids": list(self.from_preset_ids),
            "to_preset_id": self.to_preset_id,
            "to_preset_index": self.to_preset_index,
            "selector_object": self.selector_object,
            "reset_objects": list(self.reset_objects),
            "route_property": self.route_property,
            "from_property": self.from_property,
            "to_property": self.to_property,
            "reset_property": self.reset_property,
            "render_source": self.render_source,
        }


GUI_DESIGN_WORKSPACE_SURFACES: dict[str, GuiWorkspaceSurface] = {
    DEFAULT_GUI_DESIGN_ID: GuiWorkspaceSurface(
        title="Remote Ops Workspace",
        subtitle="Profiles, terminal panes and transfer workflows",
        primary_title="edge-prod",
        primary_state="running",
        command_line="$ ssh -p 22 operator@edge-prod.example",
        secondary_title="net-tools",
        secondary_state="ready",
        detail_lines=(
            "$ row vault status",
            "initialized: yes",
            "$ row doctor --json",
            "ssh: true  rdp: true",
        ),
        activity_lines=(
            "View: Native",
            "LAUNCHED: ssh -p 22 operator@edge-prod.example",
            "FILES: sftp -P 22 operator@logs.example",
            "Running process panes: 2",
        ),
        home_actions=("Start local terminal", "Recover previous sessions"),
        home_search_placeholder="Find existing profile or server name...",
        recent_columns=(
            ("[ssh] edge-prod", "[sftp] files-prod", "..."),
            ("[rdp] win-admin", "[vnc] linux-console", "..."),
            ("[https] example-web", "[ssh] jump-host", "..."),
        ),
        footer="Open protocols and local profiles stay portable across CLI, GUI and Web/PWA.",
    ),
    "mobaxterm": GuiWorkspaceSurface(
        title="Remote Ops Workspace",
        subtitle="SSH client, SFTP browser and monitoring tools",
        primary_title="example.internal",
        primary_state="SSH direct",
        command_line="[operator@example ~]$ tail -f deploy.log",
        secondary_title="SSH-browser",
        secondary_state="follow folder",
        detail_lines=(
            "Direct SSH      : yes",
            "SSH compression: yes",
            "SSH-browser    : yes",
            "X11-forwarding : disabled",
        ),
        activity_lines=(
            "Remote monitoring: CPU 7%",
            "SFTP browser: /var/log",
            "Follow terminal folder: on",
            "Conn 1  Proc 158",
        ),
        home_actions=("Start local terminal", "Recover previous sessions"),
        home_search_placeholder="Find existing session or server name...",
        recent_columns=(
            ("[ssh] edge-linux-02", "[ssh] lab-sftp-01", "..."),
            ("[rdp] lab-admin", "[vnc] lab-view", "..."),
            ("[ssh] example-ssh", "[https] example-web", "..."),
        ),
        footer="Use open protocols and local profiles with Remote Ops Workspace.",
    ),
    "securecrt": GuiWorkspaceSurface(
        title="Session Manager terminal workspace",
        subtitle="SSH2/SFTP/local shell tabs with command-window style terminal focus",
        primary_title="edge-prod (SSH2)",
        primary_state="connected",
        command_line="$ ssh -p 22 operator@edge-prod.example",
        secondary_title="SFTP tab - files-prod",
        secondary_state="ready",
        detail_lines=(
            "Protocol : SSH2",
            "Cipher   : chacha20-poly1305",
            "SFTP     : tab attached",
            "Log file : session.log",
        ),
        activity_lines=(
            "Session Manager: folder Sessions/edge-prod",
            "Tab: edge-prod (SSH2)",
            "Command window: enabled",
            "SFTP tab: files-prod",
        ),
        home_actions=("Connect", "New Session"),
        home_search_placeholder="Search Session Manager...",
        recent_columns=(
            ("edge-prod (SSH2)", "jump-host (SSH2)", "..."),
            ("files-prod (SFTP)", "PowerShell", "..."),
            ("Start Page", "Net tools", "..."),
        ),
        footer="Terminal-first workflow with foldered sessions, SFTP tabs and local shell entries.",
    ),
    "termius": GuiWorkspaceSurface(
        title="Host terminal workspace",
        subtitle="Vault-backed SSH host with files, snippets and port-forward state",
        primary_title="edge-prod",
        primary_state="connected",
        command_line="$ ssh edge-prod",
        secondary_title="Vault and snippets",
        secondary_state="unlocked",
        detail_lines=(
            "Identity : prod-ed25519",
            "Port fwd : 8080 -> localhost:80",
            "Files    : SFTP ready",
            "Snippet  : row vault status",
        ),
        activity_lines=(
            "Sync: current",
            "Vault: unlocked",
            "Host chain: direct",
            "Port forwarding: ready",
        ),
        home_actions=("Connect Host", "New Host"),
        home_search_placeholder="Search hosts, groups or snippets...",
        recent_columns=(
            ("edge-prod", "jump-host", "..."),
            ("prod-cluster", "deploy-check", "..."),
            ("vault", "files", "..."),
        ),
        footer="SSH hosts, vault keys, snippets and files stay one vertical workflow.",
    ),
    "remmina": GuiWorkspaceSurface(
        title="Remote desktop viewer",
        subtitle="RDP/VNC/SFTP viewer tabs with scaling, clipboard and sharing controls",
        primary_title="win-admin (RDP)",
        primary_state="scale 100%",
        command_line="mstsc /v:admin-win.example:3389",
        secondary_title="Connection options",
        secondary_state="clipboard on",
        detail_lines=(
            "Protocol : RDP",
            "Scale    : 100%",
            "Clipboard: enabled",
            "Screenshot: win-admin-rdp-screenshot.png",
            "Shared   : file workflow ready",
        ),
        activity_lines=(
            "Viewer tab: win-admin",
            "Protocol group: RDP",
            "Scale mode: 100%",
            "Clipboard: on",
            "Screenshot: capture ready",
            "SFTP transfer: queue ready",
        ),
        home_actions=("Connect", "New Profile"),
        home_search_placeholder="Search connection profiles...",
        recent_columns=(
            ("win-admin", "lab-desktop", "..."),
            ("linux-console", "sftp-ops", "..."),
            ("Quick Connect", "Preferences", "..."),
        ),
        footer="Remote desktop profiles keep viewer controls, protocol grouping and import-friendly metadata.",
    ),
    "mremoteng": GuiWorkspaceSurface(
        title="Connection manager document workspace",
        subtitle="Nested connection tree with document tabs, inheritance and external-tool state",
        primary_title="edge-prod [SSH]",
        primary_state="open",
        command_line="$ ssh -p 22 operator@edge-prod.example",
        secondary_title="Config and inheritance",
        secondary_state="inherited",
        detail_lines=(
            "Container : prod",
            "Protocol  : SSH",
            "External  : SFTP ready",
            "Inheritance: credentials on",
        ),
        activity_lines=(
            "Connections.xml: loaded",
            "Document tab: edge-prod [SSH]",
            "Inheritance: on",
            "External tool: sftp-ops",
        ),
        home_actions=("Open", "New Conn"),
        home_search_placeholder="Filter connection tree...",
        recent_columns=(
            ("prod/edge-prod [SSH]", "prod/win-admin [RDP]", "..."),
            ("files/sftp-ops", "tools/net-tools", "..."),
            ("Start Page", "Connections.xml", "..."),
        ),
        footer="Document tabs, nested containers and inherited connection settings stay visible together.",
    ),
}


GUI_DESIGN_WORKFLOW_CARDS: dict[str, tuple[GuiProductWorkflowCard, ...]] = {
    DEFAULT_GUI_DESIGN_ID: (
        GuiProductWorkflowCard("terminal", "Terminal panes", "split and tabbed", "local or remote commands"),
        GuiProductWorkflowCard("files", "File workflow", "SFTP ready", "portable external clients"),
        GuiProductWorkflowCard("doctor", "Client status", "doctor checks", "protocol availability"),
    ),
    "mobaxterm": (
        GuiProductWorkflowCard("sftp-browser", "SFTP browser", "/var/log attached", "follow terminal folder"),
        GuiProductWorkflowCard("remote-monitoring", "Remote monitoring", "CPU and process state", "SSH telemetry snapshot"),
        GuiProductWorkflowCard("bottom-telemetry", "Bottom telemetry", "connection strip visible", "network and process counters"),
    ),
    "securecrt": (
        GuiProductWorkflowCard("command-window", "Command Window", "send to all sessions", "targeted terminal input"),
        GuiProductWorkflowCard("session-manager", "Session Manager", "foldered SSH2/SFTP tabs", "persistent session database"),
        GuiProductWorkflowCard("sftp-tab", "SFTP tab", "files-prod attached", "terminal plus transfer workflow"),
    ),
    "termius": (
        GuiProductWorkflowCard("vault", "Vault identity", "prod-ed25519 unlocked", "host key chain ready"),
        GuiProductWorkflowCard("port-forward", "Port forward", "8080 -> localhost:80", "local tunnel ready"),
        GuiProductWorkflowCard("snippet", "Snippet", "row vault status", "one-click command"),
    ),
    "remmina": (
        GuiProductWorkflowCard("protocol", "Protocol viewer", "RDP/VNC tabs ready", "viewer protocol groups"),
        GuiProductWorkflowCard("scale", "Scaling controls", "fit and 100%", "fullscreen and screenshot"),
        GuiProductWorkflowCard("clipboard", "Clipboard sync", "enabled", "shared file workflow"),
    ),
    "mremoteng": (
        GuiProductWorkflowCard("document-toolbar", "Document toolbar", "Connections.xml loaded", "filter and reconnect actions"),
        GuiProductWorkflowCard("rdp-document", "RDP document", "embedded viewer pane", "dockable session surface"),
        GuiProductWorkflowCard("inheritance-grid", "Config inheritance", "credentials inherited", "property grid visible"),
    ),
}


GUI_DESIGN_REFERENCE_STATES: dict[str, GuiProductReferenceState] = {
    DEFAULT_GUI_DESIGN_ID: GuiProductReferenceState(
        profile_name="edge-prod",
        target_label="edge-prod.example.invalid:22",
        protocol_label="SSH",
        active_tab_label="edge-prod",
        sidebar_label="Profiles",
        workspace_state="running",
        status_segments=GUI_DESIGN_STATUS_COPY[DEFAULT_GUI_DESIGN_ID],
    ),
    "mobaxterm": GuiProductReferenceState(
        profile_name="edge-prod",
        target_label="edge-prod.example.invalid:22",
        protocol_label="SSH/SFTP",
        active_tab_label="edge-prod.example.invalid (operator)",
        sidebar_label="SFTP browser",
        workspace_state="connected monitoring",
        status_segments=GUI_DESIGN_STATUS_COPY["mobaxterm"],
    ),
    "securecrt": GuiProductReferenceState(
        profile_name="edge-prod",
        target_label="edge-prod.example.invalid:22",
        protocol_label="SSH2 + SFTP",
        active_tab_label="edge-prod (SSH2)",
        sidebar_label="Session Manager",
        workspace_state="connected",
        status_segments=GUI_DESIGN_STATUS_COPY["securecrt"],
    ),
    "termius": GuiProductReferenceState(
        profile_name="edge-prod",
        target_label="edge-prod.example.invalid:22",
        protocol_label="SSH + Vault",
        active_tab_label="edge-prod",
        sidebar_label="Hosts",
        workspace_state="vault unlocked",
        status_segments=GUI_DESIGN_STATUS_COPY["termius"],
    ),
    "remmina": GuiProductReferenceState(
        profile_name="win-admin",
        target_label="admin-win.example.invalid:3389",
        protocol_label="RDP viewer",
        active_tab_label="RDP - win-admin",
        sidebar_label="Connection Profiles",
        workspace_state="scale 100%",
        status_segments=GUI_DESIGN_STATUS_COPY["remmina"],
    ),
    "mremoteng": GuiProductReferenceState(
        profile_name="edge-prod",
        target_label="edge-prod.example.invalid:22",
        protocol_label="SSH document",
        active_tab_label="edge-prod [SSH]",
        sidebar_label="Connections",
        workspace_state="document open",
        status_segments=GUI_DESIGN_STATUS_COPY["mremoteng"],
    ),
}


GUI_DESIGN_PRODUCT_IDENTITY_TREE_LABELS = {
    DEFAULT_GUI_DESIGN_ID: "edge-prod",
    "securecrt": "edge-prod (SSH2)",
    "termius": "edge-prod  ssh host",
    "remmina": "RDP - win-admin",
    "mremoteng": "edge-prod [SSH]",
}
PRODUCT_REFERENCE_TAB_PRESET_IDS = ("securecrt", "termius", "remmina", "mremoteng")
PRODUCT_GUI_PRESET_IDS = ("mobaxterm", *PRODUCT_REFERENCE_TAB_PRESET_IDS)
GUI_DESIGN_KEYBOARD_SHORTCUTS = (
    ("refresh-profiles", "Ctrl+R", "Refresh profiles"),
    ("new-profile", "Ctrl+N", "New profile"),
    ("edit-profile", "Ctrl+E", "Edit selected profile"),
    ("connect-selected", "Ctrl+Return", "Connect selected profile"),
    ("new-local-terminal", "Ctrl+T", "New local terminal"),
    ("close-current-tab", "Ctrl+W", "Close current tab"),
    ("recover-previous-sessions", "Ctrl+Shift+T", "Recover previous sessions"),
    ("split-horizontal", "Ctrl+Shift+H", "Split horizontal"),
    ("split-vertical", "Ctrl+Shift+V", "Split vertical"),
    ("open-selected-layout", "Ctrl+L", "Open selected layout"),
    ("find-log-text", "Ctrl+F", "Find log text"),
)


def _stylesheet(
    colors: GuiDesignColors,
    *,
    radius: int,
    control_padding: str,
    tab_padding: str,
    tree_padding: str,
) -> str:
    return f"""
QMainWindow#remoteOpsMain {{
  background: {colors.window};
}}
QToolBar#mainToolbar, QToolBar#layoutToolbar {{
  background: {colors.toolbar};
  border-bottom: 1px solid {colors.toolbar_border};
  spacing: 5px;
  padding: 5px 7px;
}}
QMenuBar {{
  background: {colors.toolbar};
  color: {colors.control_text};
  border-bottom: 1px solid {colors.toolbar_border};
  padding: 2px 6px;
}}
QMenuBar#mobaTopMenuBar {{
  background: {colors.window};
}}
QMenuBar#secureCrtMenuBar {{
  background: {colors.window};
  border-bottom: 1px solid {colors.toolbar_border};
  padding: 2px 7px;
}}
QMenuBar#mRemoteNgMenuBar {{
  background: {colors.toolbar};
  border-bottom: 1px solid {colors.toolbar_border};
  padding: 2px 7px;
}}
QMenuBar::item {{
  padding: 3px 8px;
  background: transparent;
}}
QMenuBar::item:selected {{
  background: {colors.control};
}}
QLabel#toolbarLabel {{
  color: {colors.sidebar_muted};
  padding-left: 8px;
  padding-right: 2px;
}}
QFrame#leftPanelHeader {{
  background: {colors.sidebar};
  border-bottom: 1px solid {colors.pane_border};
}}
QLabel#leftPanelTitle {{
  color: {colors.sidebar_text};
  font-size: 13px;
  font-weight: 700;
}}
QLabel#leftPanelSubtitle {{
  color: {colors.sidebar_muted};
  font-size: 10px;
}}
QPushButton, QToolButton, QComboBox, QLineEdit {{
  background: {colors.control};
  color: {colors.control_text};
  border: 1px solid {colors.control_border};
  border-radius: {radius}px;
  padding: {control_padding};
}}
QPushButton:hover, QToolButton:hover, QComboBox:hover, QLineEdit:hover {{
  border-color: {colors.control_hover};
}}
QComboBox QAbstractItemView {{
  background: {colors.control};
  color: {colors.control_text};
  border: 1px solid {colors.control_border};
  selection-background-color: {colors.sidebar_selected};
  selection-color: {colors.sidebar_selected_text};
  outline: 0;
}}
QPushButton:disabled, QToolButton:disabled {{
  color: {colors.sidebar_muted};
  background: {colors.pane};
}}
QPushButton[interactionState="active"], QToolButton[interactionState="active"] {{
  background: {colors.primary};
  color: {colors.primary_text};
  border-color: {colors.primary};
  font-weight: 700;
}}
QPushButton[interactionState="checked"], QToolButton[interactionState="checked"] {{
  background: {colors.sidebar_selected};
  color: {colors.sidebar_selected_text};
  border-color: {colors.control_hover};
  font-weight: 700;
}}
QPushButton[interactionState="disabled"], QToolButton[interactionState="disabled"] {{
  background: {colors.pane};
  color: {colors.sidebar_muted};
  border-color: {colors.toolbar_border};
}}
QLineEdit[interactionState="focused"], QComboBox[interactionState="focused"] {{
  border: 2px solid {colors.control_hover};
  padding: {control_padding};
}}
QPushButton#primaryAction, QToolButton#primaryAction {{
  background: {colors.primary};
  color: {colors.primary_text};
  border-color: {colors.primary};
  font-weight: 600;
}}
QPushButton#primaryAction:hover, QToolButton#primaryAction:hover {{
  border-color: {colors.control_hover};
}}
QPushButton#dangerAction, QToolButton#dangerAction {{
  color: {colors.danger_text};
  border-color: {colors.danger};
}}
QToolButton#mobaRibbonButton {{
  background: transparent;
  color: {colors.control_text};
  border: 1px solid transparent;
  border-radius: 0;
  padding: 4px 5px;
  font-size: 10px;
  font-weight: 500;
}}
QToolButton#mobaRibbonButton:hover {{
  background: {colors.control};
  border-color: {colors.control_border};
}}
QToolButton#mobaXServerAction {{
  background: transparent;
  color: {colors.primary};
  border: 1px solid transparent;
  border-radius: 0;
  padding: 4px 5px;
  font-size: 10px;
  font-weight: 600;
}}
QToolButton#mobaXServerAction:hover {{
  background: {colors.control};
  border-color: {colors.control_border};
}}
QToolButton#mobaExitAction {{
  background: transparent;
  color: {colors.danger_text};
  border: 1px solid transparent;
  border-radius: 0;
  padding: 4px 5px;
  font-size: 10px;
  font-weight: 600;
}}
QToolButton#mobaExitAction:hover {{
  background: {colors.control};
  border-color: {colors.danger};
}}
QLineEdit#toolbarSearch {{
  min-width: 150px;
}}
QLineEdit#quickConnect {{
  background: {colors.control};
  color: {colors.control_text};
  border: 0;
  border-radius: 0;
  padding: {GUI_DESIGN_MOBA_QUICK_CONNECT_CHROME.input_padding};
}}
QFrame#mobaQuickConnectChrome {{
  background: {colors.control};
  border: 1px solid {colors.toolbar_border};
  border-radius: 0;
}}
QFrame#mobaQuickConnectChrome[interactionState="focused"] {{
  border: 2px solid {colors.control_hover};
}}
QLabel#mobaQuickConnectDropdown {{
  background: {colors.control};
  color: {colors.sidebar_muted};
  border-left: 1px solid {colors.toolbar_border};
  font-weight: 700;
}}
QTreeWidget#quickConnectSuggestions {{
  background: {colors.sidebar};
  color: {colors.sidebar_text};
  border: 1px solid {colors.toolbar_border};
  border-top: 0;
  padding: 3px;
  outline: 0;
  font-family: "Segoe UI", Arial, sans-serif;
}}
QTreeWidget#quickConnectSuggestions::item {{
  padding: 3px 5px;
  border-radius: {radius}px;
  min-height: {GUI_DESIGN_MOBA_QUICK_CONNECT_SUGGESTION_CHROME.row_height}px;
}}
QTreeWidget#quickConnectSuggestions::item:selected {{
  background: {colors.sidebar_selected};
  color: {colors.sidebar_selected_text};
}}
QWidget#mobaRail {{
  background: {colors.window};
  border-right: 1px solid {colors.toolbar_border};
}}
QLabel#mobaRailLabel {{
  color: {colors.sidebar_text};
  background: transparent;
  border: 0;
  border-bottom: 1px solid {colors.toolbar_border};
  font-size: {GUI_DESIGN_MOBA_RAIL_CHROME.label_font_size}px;
  font-weight: 700;
}}
QLabel#mobaRailButton, QToolButton#mobaRailButton {{
  color: {colors.sidebar_text};
  padding: 7px 3px;
  background: transparent;
  border: 0;
  border-bottom: 1px solid {colors.toolbar_border};
  font-weight: 600;
}}
QLabel#mobaRailButton:hover, QToolButton#mobaRailButton:hover {{
  background: {colors.control};
  border-color: {colors.toolbar_border};
}}
QLabel#mobaRailButton:checked, QToolButton#mobaRailButton:checked {{
  color: {colors.primary};
  background: {colors.sidebar};
}}
QLabel#mobaRailAccent, QToolButton#mobaRailAccent {{
  color: {colors.status};
  padding: 7px 3px;
  background: transparent;
  border: 0;
  border-bottom: 1px solid {colors.toolbar_border};
  font-weight: 700;
}}
QLabel#mobaRailAccent:hover, QToolButton#mobaRailAccent:hover {{
  background: {colors.control};
}}
QLabel#mobaRailAccent:checked, QToolButton#mobaRailAccent:checked {{
  background: {colors.sidebar};
}}
QTreeWidget#profileTree {{
  background: {colors.sidebar};
  color: {colors.sidebar_text};
  border: 0;
  border-right: 1px solid {colors.pane_border};
  padding: 5px;
  outline: 0;
  font-family: "Segoe UI", Arial, sans-serif;
}}
QTreeWidget#profileTree::item {{
  padding: {tree_padding};
  border-radius: {radius}px;
}}
QTreeWidget#profileTree::item:hover {{
  background: {colors.control};
}}
QTreeWidget#profileTree::item:selected {{
  background: {colors.sidebar_selected};
  color: {colors.sidebar_selected_text};
}}
QTreeWidget#profileTree::branch {{
  background: transparent;
}}
QTabWidget#sessionTabs::pane {{
  background: {colors.pane};
  border: 1px solid {colors.pane_border};
}}
QTabBar::tab {{
  background: {colors.tab};
  color: {colors.tab_text};
  padding: {tab_padding};
  border: 1px solid {colors.pane_border};
  margin-right: 2px;
}}
QTabBar::tab:selected {{
  background: {colors.tab_selected};
  color: {colors.tab_selected_text};
  border-bottom-color: {colors.tab_selected};
  font-weight: 600;
}}
QTabBar::tab:hover {{
  background: {colors.control};
  color: {colors.control_text};
}}
QWidget#terminalPane {{
  background: {colors.pane};
}}
QFrame#terminalHeader {{
  background: {colors.toolbar};
  border: 1px solid {colors.pane_border};
  border-bottom: 0;
}}
QFrame#terminalCommandRow {{
  background: {colors.control};
  border-left: 1px solid {colors.pane_border};
  border-right: 1px solid {colors.pane_border};
  border-bottom: 1px solid {colors.pane_border};
}}
QLabel#terminalTitle {{
  color: {colors.control_text};
  font-weight: 700;
}}
QLabel#terminalSource {{
  color: {colors.sidebar_muted};
}}
QLabel#terminalCommand {{
  color: {colors.terminal_accent};
  font-family: "Cascadia Mono", Consolas, monospace;
}}
QToolButton#terminalAction {{
  background: {colors.control};
  color: {colors.control_text};
  border: 1px solid {colors.control_border};
  border-radius: {radius}px;
  padding: 3px 6px;
}}
QToolButton#terminalAction:hover {{
  border-color: {colors.control_hover};
}}
QToolButton#terminalAction:disabled {{
  color: {colors.sidebar_muted};
  background: {colors.pane};
}}
QDialog#workflowDialog {{
  background: {colors.pane};
  color: {colors.control_text};
}}
QDialog#workflowDialog QScrollArea#profileFormScroll,
QDialog#workflowDialog QWidget#profileFormBody,
QDialog#workflowDialog QScrollArea#layoutFormScroll,
QDialog#workflowDialog QWidget#layoutFormBody {{
  background: {colors.pane};
  color: {colors.control_text};
  border: 0;
}}
QDialog#workflowDialog QWidget#profileFormBody QLabel,
QDialog#workflowDialog QWidget#layoutFormBody QLabel {{
  background: transparent;
  color: {colors.control_text};
}}
QDialog#workflowDialog QLabel#workflowTitle {{
  color: {colors.control_text};
  font-size: 18px;
  font-weight: 700;
}}
QDialog#workflowDialog QLabel#workflowSubtitle {{
  color: {colors.sidebar_muted};
}}
QDialog#workflowDialog QLabel#profileValidationError,
QDialog#workflowDialog QLabel#layoutValidationError {{
  background: {colors.danger};
  color: {colors.primary_text};
  border-radius: {radius}px;
  padding: 7px 9px;
  font-weight: 600;
}}
QDialog#workflowDialog QLineEdit,
QDialog#workflowDialog QComboBox,
QDialog#workflowDialog QPlainTextEdit {{
  background: {colors.control};
  color: {colors.control_text};
  border: 1px solid {colors.control_border};
  border-radius: {radius}px;
  padding: {control_padding};
}}
QDialog#workflowDialog QTreeWidget#workflowRows {{
  background: {colors.sidebar};
  color: {colors.sidebar_text};
  border: 1px solid {colors.pane_border};
  outline: 0;
}}
QDialog#workflowDialog QTreeWidget#workflowRows::item {{
  padding: 5px;
}}
QDialog#workflowDialog QTreeWidget#workflowRows::item:selected {{
  background: {colors.sidebar_selected};
  color: {colors.sidebar_selected_text};
}}
QDialog#workflowDialog QTextEdit#workflowPreview {{
  background: {colors.terminal};
  color: {colors.terminal_text};
  border: 1px solid {colors.pane_border};
  font-family: "Cascadia Mono", Consolas, monospace;
}}
QDialog#workflowDialog QToolButton#workflowAction {{
  background: {colors.control};
  color: {colors.control_text};
  border: 1px solid {colors.control_border};
  border-radius: {radius}px;
  padding: 4px 9px;
  font-weight: 600;
}}
QDialog#workflowDialog QToolButton#workflowAction:hover {{
  border-color: {colors.control_hover};
}}
QWidget#newSessionTab {{
  background: {colors.pane};
}}
QWidget#welcomeHome {{
  background: {colors.pane};
}}
QFrame#welcomePanel {{
  background: {colors.pane};
  border: 0;
}}
QLabel#welcomeLogo {{
  background: {colors.control};
  color: {colors.terminal_accent};
  border: 2px solid {colors.sidebar_muted};
  font-family: "Cascadia Mono", Consolas, monospace;
  font-size: 21px;
  font-weight: 700;
  padding: 6px;
}}
QLabel#welcomeTitle {{
  color: {colors.control_text};
  font-size: 30px;
  font-weight: 600;
}}
QLabel#welcomeSubtitle, QLabel#workspaceSurfaceSubtitle, QLabel#recentSessionsLabel {{
  color: {colors.sidebar_muted};
}}
QLabel#recentSessionsTitle {{
  color: {colors.control_text};
  font-weight: 700;
}}
QLineEdit#homeSearch {{
  background: {colors.control};
  color: {colors.control_text};
  border: 1px solid {colors.sidebar_muted};
  border-radius: 0;
  padding: 4px 7px;
}}
QFrame#mobaHomeWelcomeSurface {{
  background: transparent;
  border: 0;
}}
QLabel#mobaHomeTitle {{
  color: {colors.control_text};
  font-size: 30px;
  font-weight: 600;
}}
QLabel#mobaHomeSubtitle, QLabel#mobaRecentSession {{
  color: {colors.control_text};
}}
QLabel#mobaHomeFooter {{
  color: {colors.control_hover};
}}
QPushButton#mobaHomePrimaryAction {{
  background: {colors.control};
  color: {colors.control_text};
  border: 1px solid {colors.control_hover};
  border-radius: 0;
  padding: 7px 20px;
}}
QPushButton#mobaHomeAction {{
  background: {colors.control};
  color: {colors.control_text};
  border: 1px solid {colors.control_border};
  border-radius: 0;
  padding: 7px 20px;
}}
QPushButton#mobaHomePrimaryAction:hover, QPushButton#mobaHomeAction:hover {{
  border-color: {colors.terminal_accent};
}}
QLabel#homePromo {{
  color: {colors.control_hover};
}}
QFrame#productWorkflowEvidence {{
  background: {colors.control};
  border: 1px solid {colors.pane_border};
  border-radius: {radius}px;
  padding: 6px;
}}
QFrame#productWorkflowCard {{
  background: {colors.pane};
  border: 1px solid {colors.control_border};
  border-radius: {radius}px;
  padding: 6px;
}}
QLabel#productWorkflowTitle {{
  color: {colors.control_text};
  font-weight: 700;
}}
QLabel#productWorkflowPrimary {{
  color: {colors.terminal_accent};
  font-family: "Cascadia Mono", Consolas, monospace;
}}
QLabel#productWorkflowSecondary {{
  color: {colors.sidebar_muted};
}}
QFrame#productWorkspaceSurface {{
  background: {colors.control};
  border: 1px solid {colors.pane_border};
  border-radius: {radius}px;
  padding: 6px;
}}
QFrame#productReferenceState {{
  background: {colors.pane};
  border: 1px solid {colors.control_border};
  border-radius: {radius}px;
  padding: 4px;
}}
QLabel#productReferenceStateItem {{
  color: {colors.control_text};
  font-size: 10px;
  font-weight: 600;
}}
QFrame#productWorkspacePrimaryPane, QFrame#productWorkspaceSecondaryPane {{
  background: {colors.terminal};
  border: 1px solid {colors.control_border};
  border-radius: {radius}px;
  padding: 6px;
}}
QFrame#secureCrtCommandWindow {{
  background: {colors.log};
  border: 1px solid {colors.control_border};
  border-radius: {radius}px;
  padding: 6px;
}}
QFrame#secureCrtSessionStatusStrip {{
  background: {colors.pane};
  border: 1px solid {colors.control_border};
  border-radius: {radius}px;
  padding: 5px;
}}
QFrame#secureCrtSessionManagerChrome {{
  background: {colors.pane};
  border: 1px solid {colors.control_border};
  border-radius: {radius}px;
  padding: 5px;
}}
QLabel#secureCrtSessionManagerTitle {{
  color: {colors.control_text};
  font-weight: 700;
}}
QLineEdit#secureCrtSessionFilter {{
  background: {colors.terminal};
  border: 1px solid {colors.primary};
  color: {colors.control_text};
  padding: 3px 5px;
}}
QToolButton#secureCrtSessionManagerAction {{
  background: {colors.control};
  border: 1px solid {colors.control_border};
  color: {colors.control_text};
  padding: 3px 6px;
}}
QToolButton#secureCrtSessionManagerAction:hover {{
  border-color: {colors.primary};
}}
QToolButton#secureCrtSessionManagerAction[secureCrtSessionRouteActive="true"] {{
  border-color: {colors.primary};
  background: {colors.control};
}}
QLabel#secureCrtSessionStatusTitle {{
  color: {colors.sidebar_muted};
  font-weight: 700;
}}
QLabel#secureCrtSessionStatusCell {{
  background: {colors.terminal};
  border: 1px solid {colors.control_border};
  color: {colors.control_text};
  font-family: "Cascadia Mono", Consolas, monospace;
  padding: 4px 7px;
}}
QFrame#remminaViewerControls {{
  background: {colors.toolbar};
  border: 1px solid {colors.control_border};
  border-radius: {radius}px;
  padding: 5px;
}}
QToolButton#remminaViewerControl {{
  background: {colors.control};
  border: 1px solid {colors.control_border};
  border-radius: {radius}px;
  color: {colors.control_text};
  padding: 4px 8px;
  font-weight: 600;
}}
QToolButton#remminaViewerControl:hover {{
  border-color: {colors.primary};
}}
QToolButton#remminaViewerControl[remminaProfileViewerRouteActive="true"] {{
  border-color: {colors.primary};
  background: {colors.toolbar};
}}
QFrame#remminaProfileListChrome {{
  background: {colors.pane};
  border: 1px solid {colors.pane_border};
  border-radius: {radius}px;
  padding: 5px;
}}
QLineEdit#remminaProfileFilter {{
  background: {colors.control};
  border: 1px solid {colors.control_border};
  color: {colors.control_text};
  padding: 3px 5px;
}}
QLabel#remminaProfileListTitle {{
  color: {colors.control_text};
  font-weight: 700;
}}
QLabel#remminaProfileListColumn {{
  color: {colors.sidebar_muted};
  font-weight: 700;
}}
QFrame#remminaProfileListRow {{
  background: {colors.control};
  border: 1px solid {colors.control_border};
  border-radius: {radius}px;
}}
QFrame#remminaProfileListRow[selectedRow="true"] {{
  background: {colors.sidebar_selected};
  border-color: {colors.primary};
}}
QLabel#remminaProfileListCell {{
  color: {colors.control_text};
}}
QFrame#termiusHeaderChips {{
  background: {colors.toolbar};
  border: 1px solid {colors.control_border};
  border-radius: {radius}px;
  padding: 5px;
}}
QFrame#termiusHostsChrome {{
  background: {colors.pane};
  border: 1px solid {colors.control_border};
  border-radius: {radius}px;
  padding: 5px;
}}
QLabel#termiusHostsTitle {{
  color: {colors.control_text};
  font-weight: 700;
}}
QLineEdit#termiusHostSearch {{
  background: {colors.terminal};
  border: 1px solid {colors.primary};
  border-radius: {radius}px;
  color: {colors.control_text};
  padding: 3px 5px;
}}
QToolButton#termiusHostsAction {{
  background: {colors.control};
  border: 1px solid {colors.control_border};
  border-radius: {radius}px;
  color: {colors.control_text};
  padding: 3px;
}}
QToolButton#termiusHostsAction:hover {{
  border-color: {colors.control_hover};
}}
QFrame#termiusHostIdentityStrip {{
  background: {colors.pane};
  border: 1px solid {colors.control_border};
  border-radius: {radius}px;
  padding: 5px;
}}
QLabel#termiusHeaderChip {{
  background: {colors.control};
  border: 1px solid {colors.control_border};
  border-radius: 12px;
  color: {colors.terminal_accent};
  font-weight: 700;
  padding: 5px 11px;
}}
QLabel#termiusHostIdentityTitle {{
  color: {colors.sidebar_muted};
  font-weight: 700;
}}
QLabel#termiusHostIdentityCell {{
  background: {colors.terminal};
  border: 1px solid {colors.control_border};
  color: {colors.control_text};
  font-family: "Cascadia Mono", Consolas, monospace;
  padding: 4px 7px;
}}
QFrame#mRemoteNgDocumentControls {{
  background: {colors.control};
  border: 1px solid {colors.control_border};
  border-radius: {radius}px;
  padding: 0px;
}}
QLabel#mRemoteNgDocumentTitle {{
  color: {colors.control_text};
  font-weight: 700;
}}
QToolButton#mRemoteNgDocumentControl {{
  background: {colors.toolbar};
  border: 1px solid {colors.control_border};
  border-radius: {radius}px;
  color: {colors.control_text};
  padding: 4px 8px;
}}
QToolButton#mRemoteNgDocumentControl:hover {{
  border-color: {colors.primary};
}}
QToolButton#mRemoteNgDocumentControl[mRemoteNgConnectionRouteActive="true"] {{
  border-color: {colors.primary};
  background: {colors.control};
}}
QLineEdit#mRemoteNgDocumentFilter {{
  background: {colors.window};
  border: 1px solid {colors.control_border};
  color: {colors.control_text};
  padding: 4px 8px;
}}
QFrame#mRemoteNgPropertyGrid {{
  background: {colors.log};
  border: 1px solid {colors.control_border};
  border-radius: {radius}px;
  padding: 5px;
}}
QLabel#mRemoteNgPropertyGridTitle {{
  color: {colors.control_text};
  font-weight: 700;
}}
QLabel#mRemoteNgPropertyGridScope {{
  color: {colors.status};
  font-weight: 700;
}}
QLabel#mRemoteNgPropertyGridColumn {{
  background: {colors.toolbar};
  border: 1px solid {colors.control_border};
  color: {colors.control_text};
  font-weight: 700;
  padding: 3px 6px;
}}
QFrame#mRemoteNgPropertyGridRow {{
  background: {colors.window};
  border: 1px solid {colors.control_border};
}}
QFrame#mRemoteNgPropertyGridRow[inherited="true"] {{
  background: {colors.log};
}}
QLabel#mRemoteNgPropertyGridCell {{
  color: {colors.log_text};
  font-family: "Cascadia Mono", Consolas, monospace;
  padding: 3px 6px;
}}
QLabel#secureCrtCommandTitle, QLabel#secureCrtCommandTarget, QLabel#secureCrtCommandSend {{
  color: {colors.control_text};
  font-weight: 700;
}}
QLabel#secureCrtCommandHelper, QLabel#secureCrtCommandStatus {{
  color: {colors.sidebar_muted};
}}
QLabel#secureCrtCommandInput {{
  background: {colors.terminal};
  border: 1px solid {colors.primary};
  color: {colors.terminal_accent};
  font-family: "Cascadia Mono", Consolas, monospace;
  padding: 4px 8px;
}}
QLabel#productWorkspaceTitle, QLabel#productWorkspacePaneTitle {{
  color: {colors.control_text};
  font-weight: 700;
}}
QLabel#productWorkspaceState, QLabel#productWorkspaceLead {{
  color: {colors.terminal_accent};
  font-family: "Cascadia Mono", Consolas, monospace;
}}
QLabel#productWorkspaceLine {{
  color: {colors.terminal_text};
  font-family: "Cascadia Mono", Consolas, monospace;
}}
QWidget#mobaConnectedSession, QWidget#mobaTerminalArea {{
  background: {colors.pane};
}}
QStackedWidget#mobaLeftStack {{
  background: {colors.sidebar};
  border: 0;
}}
QFrame#mobaSftpBrowser, QFrame#mobaConnectedLeftDock {{
  background: {colors.sidebar};
  border-right: 1px solid {colors.pane_border};
}}
QFrame#mobaSftpToolbar {{
  background: {colors.control};
  border: 1px solid {colors.pane_border};
}}
QToolButton#mobaSftpAction {{
  background: transparent;
  color: {colors.control_text};
  border: 1px solid transparent;
  border-radius: 0;
  padding: 2px;
}}
QToolButton#mobaSftpAction:hover {{
  border-color: {colors.terminal_accent};
  background: {colors.pane};
}}
QFrame#mobaSftpToolbarSeparator {{
  color: {colors.pane_border};
  background: transparent;
}}
QLineEdit#mobaSftpPath {{
  background: {colors.control};
  color: {colors.control_text};
  border: 1px solid {colors.pane_border};
  border-radius: 0;
  padding: 3px 6px;
  font-family: "Cascadia Mono", Consolas, monospace;
}}
QTreeWidget#mobaSftpFileTable {{
  background: {colors.sidebar};
  color: {colors.sidebar_text};
  border: 1px solid {colors.pane_border};
  outline: 0;
  font-size: 11px;
}}
QTreeWidget#mobaSftpFileTable::item {{
  padding: 2px 4px;
}}
QTreeWidget#mobaSftpFileTable::item:selected {{
  background: {colors.sidebar_selected};
  color: {colors.sidebar_selected_text};
}}
QFrame#mobaRemoteMonitoring {{
  background: {colors.window};
  border-top: 1px solid {colors.sidebar_muted};
}}
QFrame#mobaMonitoringControls {{
  background: transparent;
}}
QToolButton#mobaMonitoringControl {{
  background: transparent;
  border: 1px solid transparent;
  color: {colors.control_text};
  font-size: 12px;
  font-weight: 600;
  padding: 2px 4px;
}}
QToolButton#mobaMonitoringControl:checked {{
  border-color: {colors.terminal_accent};
}}
QToolButton#mobaMonitoringControl:hover {{
  background: {colors.control};
  border-color: {colors.control_hover};
}}
QLabel#mobaMonitoringMetric, QCheckBox#mobaFollowTerminalFolder {{
  color: {colors.control_text};
  font-size: 11px;
}}
QFrame#mobaSshBanner {{
  background: {colors.terminal};
  border: 1px solid {colors.terminal_accent};
  margin: 0;
}}
QLabel#mobaSshBannerLine, QLabel#mobaSshBannerTargetLine, QLabel#mobaSshBannerCapability {{
  color: {colors.terminal_text};
  font-family: "Cascadia Mono", Consolas, monospace;
  font-size: 12px;
}}
QLabel#mobaSshBannerCapability[capabilityStatus="ok"] {{
  color: {colors.control_text};
}}
QLabel#mobaSshBannerCapability[capabilityStatus="disabled"] {{
  color: {colors.status};
}}
QLabel#mobaSshBannerFooter {{
  color: {colors.control_text};
  font-family: "Cascadia Mono", Consolas, monospace;
  font-size: 12px;
}}
QLabel#mobaSshBannerTitle {{
  color: {colors.status};
  font-family: "Cascadia Mono", Consolas, monospace;
  font-size: 14px;
  font-weight: 700;
}}
QLabel#mobaSshBannerSubtitle {{
  color: {colors.status};
  font-family: "Cascadia Mono", Consolas, monospace;
  font-size: 12px;
}}
QFrame#mobaRightUtilityRail {{
  background: {colors.pane};
  border-left: 1px solid {colors.toolbar_border};
}}
QToolButton#mobaRightUtilityAction {{
  background: transparent;
  color: {colors.control_hover};
  border: 1px solid transparent;
  border-radius: 0;
  padding: 3px;
}}
QToolButton#mobaRightUtilityAction:hover {{
  background: {colors.control};
  border-color: {colors.control_hover};
}}
QFrame#mobaSessionEdgeControls {{
  background: transparent;
  border: 0;
}}
QToolButton#mobaSessionEdgeAction {{
  background: transparent;
  color: {colors.control_hover};
  border: 1px solid transparent;
  border-radius: 0;
  padding: 2px;
}}
QToolButton#mobaSessionEdgeAction:hover {{
  background: {colors.control};
  border-color: {colors.control_hover};
}}
QFrame#mobaTelemetryBar {{
  background: {colors.toolbar};
  border-top: 1px solid {colors.pane_border};
}}
QLabel#mobaTelemetryItem {{
  color: {colors.control_text};
  font-size: 11px;
}}
QLabel#mobaTelemetryIcon {{
  color: {colors.terminal_accent};
  font-weight: 700;
  font-size: 11px;
  padding-left: 2px;
}}
QLabel#paneStatus {{
  color: {colors.status};
  font-weight: 600;
  padding: 2px 7px;
  border: 1px solid {colors.status};
  border-radius: {radius}px;
}}
QLabel#paneStatus[state="running"] {{
  color: {colors.primary_text};
  background: {colors.primary};
  border-color: {colors.primary};
}}
QLabel#paneStatus[state="starting"], QLabel#paneStatus[state="stopping"] {{
  color: {colors.terminal_accent};
  border-color: {colors.terminal_accent};
}}
QLabel#paneStatus[state="error"], QLabel#paneStatus[state="blocked"] {{
  color: {colors.danger_text};
  border-color: {colors.danger};
}}
QTextEdit#terminalOutput, QPlainTextEdit {{
  background: {colors.terminal};
  color: {colors.terminal_text};
  border: 1px solid {colors.pane_border};
  border-top: 0;
  font-family: "Cascadia Mono", Consolas, monospace;
}}
QLineEdit#terminalInput {{
  background: {colors.terminal};
  color: {colors.terminal_text};
  border-color: {colors.primary};
  font-family: "Cascadia Mono", Consolas, monospace;
}}
QTextEdit#activityLog {{
  background: {colors.log};
  color: {colors.log_text};
  border: 1px solid {colors.pane_border};
  font-family: "Cascadia Mono", Consolas, monospace;
}}
QSplitter::handle {{
  background: {colors.toolbar_border};
}}
QStatusBar {{
  background: {colors.toolbar};
  color: {colors.sidebar_muted};
  border-top: 1px solid {colors.toolbar_border};
}}
QStatusBar QLabel#productStatusNotice {{
  color: {colors.control_text};
  font-weight: 700;
  padding: 0 6px;
}}
QStatusBar QLabel#productStatusMarker {{
  color: {colors.sidebar_muted};
  border: 1px solid {colors.toolbar_border};
  padding: 0 4px;
}}
QFrame#mobaBottomEdgeControls {{
  background: transparent;
  border: 0;
}}
QToolButton#mobaBottomEdgeControl {{
  background: transparent;
  border: 1px solid transparent;
  border-radius: 0;
  padding: 1px;
}}
QToolButton#mobaBottomEdgeControl:hover {{
  background: {colors.control};
  border-color: {colors.control_hover};
}}
QStatusBar QLabel#productStatusSegment {{
  color: {colors.sidebar_muted};
  border-left: 1px solid {colors.toolbar_border};
  padding: 0 8px;
}}
QLabel {{
  color: {colors.control_text};
}}
"""


def _preset(
    *,
    id: str,
    label: str,
    description: str,
    profile_width: int,
    log_height: int,
    tab_position: str,
    density: str,
    toolbar_icon_size: int,
    list_spacing: int,
    document_mode: bool,
    colors: GuiDesignColors,
    radius: int,
    control_padding: str,
    tab_padding: str,
    tree_padding: str,
) -> GuiDesignPreset:
    return GuiDesignPreset(
        id=id,
        label=label,
        description=description,
        profile_width=profile_width,
        log_height=log_height,
        tab_position=tab_position,
        density=density,
        toolbar_icon_size=toolbar_icon_size,
        list_spacing=list_spacing,
        document_mode=document_mode,
        colors=colors,
        stylesheet=_stylesheet(
            colors,
            radius=radius,
            control_padding=control_padding,
            tab_padding=tab_padding,
            tree_padding=tree_padding,
        ),
    )


NATIVE_COLORS = GuiDesignColors(
    window="#f4f6f9",
    toolbar="#ffffff",
    toolbar_border="#d8dee8",
    control="#ffffff",
    control_text="#1f2937",
    control_border="#c4ccd8",
    control_hover="#2563eb",
    primary="#2563eb",
    primary_text="#ffffff",
    danger="#c2410c",
    danger_text="#7c2d12",
    sidebar="#f8fafc",
    sidebar_text="#1f2937",
    sidebar_muted="#64748b",
    sidebar_selected="#dbeafe",
    sidebar_selected_text="#0f172a",
    pane="#ffffff",
    pane_border="#d8dee8",
    tab="#eef2f7",
    tab_selected="#ffffff",
    tab_text="#334155",
    tab_selected_text="#0f172a",
    terminal="#111827",
    terminal_text="#e5edf6",
    terminal_accent="#38bdf8",
    log="#fbfdff",
    log_text="#243244",
    status="#2563eb",
)

MOBAXTERM_COLORS = GuiDesignColors(
    window="#101010",
    toolbar="#171717",
    toolbar_border="#454545",
    control="#222222",
    control_text="#f0f0f0",
    control_border="#5a5a5a",
    control_hover="#2f84d8",
    primary="#2d6ebd",
    primary_text="#ffffff",
    danger="#d73737",
    danger_text="#ffd0d0",
    sidebar="#151515",
    sidebar_text="#e8e8e8",
    sidebar_muted="#a6a6a6",
    sidebar_selected="#2b2b2b",
    sidebar_selected_text="#ffffff",
    pane="#202020",
    pane_border="#545454",
    tab="#1a1a1a",
    tab_selected="#242424",
    tab_text="#cfcfcf",
    tab_selected_text="#ffffff",
    terminal="#1f1f1f",
    terminal_text="#e9e9e9",
    terminal_accent="#f2cc00",
    log="#151515",
    log_text="#d9d9d9",
    status="#f2cc00",
)

SECURECRT_COLORS = GuiDesignColors(
    window="#f8f8f8",
    toolbar="#ffffff",
    toolbar_border="#c9c9c9",
    control="#ffffff",
    control_text="#202020",
    control_border="#b7b7b7",
    control_hover="#3c78b4",
    primary="#3c78b4",
    primary_text="#ffffff",
    danger="#c74848",
    danger_text="#8c1f1f",
    sidebar="#f4f4f4",
    sidebar_text="#222222",
    sidebar_muted="#666666",
    sidebar_selected="#d9e9f8",
    sidebar_selected_text="#172535",
    pane="#ffffff",
    pane_border="#bcbcbc",
    tab="#ededed",
    tab_selected="#ffffff",
    tab_text="#303030",
    tab_selected_text="#111111",
    terminal="#003b45",
    terminal_text="#d9f1ee",
    terminal_accent="#fff45a",
    log="#ffffff",
    log_text="#202020",
    status="#3c78b4",
)

TERMIUS_COLORS = GuiDesignColors(
    window="#111315",
    toolbar="#191d20",
    toolbar_border="#30363a",
    control="#22282c",
    control_text="#edf3f0",
    control_border="#3a4449",
    control_hover="#61d394",
    primary="#61d394",
    primary_text="#06120c",
    danger="#d46a6a",
    danger_text="#ffd2d2",
    sidebar="#15191c",
    sidebar_text="#e7eeeb",
    sidebar_muted="#9aa8a4",
    sidebar_selected="#23342c",
    sidebar_selected_text="#ffffff",
    pane="#121719",
    pane_border="#2d383d",
    tab="#1d2326",
    tab_selected="#25392f",
    tab_text="#d8e2df",
    tab_selected_text="#ffffff",
    terminal="#0a0e10",
    terminal_text="#d9f7e3",
    terminal_accent="#61d394",
    log="#101416",
    log_text="#d1ddd8",
    status="#61d394",
)

REMMINA_COLORS = GuiDesignColors(
    window="#eef2f5",
    toolbar="#ffffff",
    toolbar_border="#c8d0d8",
    control="#ffffff",
    control_text="#20262d",
    control_border="#b6c0ca",
    control_hover="#2c7be5",
    primary="#2c7be5",
    primary_text="#ffffff",
    danger="#ba4a31",
    danger_text="#8a2f1e",
    sidebar="#f7f9fb",
    sidebar_text="#1d252d",
    sidebar_muted="#687682",
    sidebar_selected="#d6e9ff",
    sidebar_selected_text="#0f253f",
    pane="#ffffff",
    pane_border="#c8d0d8",
    tab="#e6ebf0",
    tab_selected="#ffffff",
    tab_text="#26323d",
    tab_selected_text="#111820",
    terminal="#fbfcfd",
    terminal_text="#17212b",
    terminal_accent="#1a7f64",
    log="#ffffff",
    log_text="#1f2b36",
    status="#2c7be5",
)

MREMOTENG_COLORS = GuiDesignColors(
    window="#dfe5eb",
    toolbar="#f4f7fa",
    toolbar_border="#aab6c2",
    control="#ffffff",
    control_text="#1b2733",
    control_border="#99a8b6",
    control_hover="#3b6ea8",
    primary="#3b6ea8",
    primary_text="#ffffff",
    danger="#9f3d35",
    danger_text="#7a2c26",
    sidebar="#edf2f6",
    sidebar_text="#1b2733",
    sidebar_muted="#687887",
    sidebar_selected="#c9d8e8",
    sidebar_selected_text="#0f1b26",
    pane="#f8fafc",
    pane_border="#aab6c2",
    tab="#e8edf2",
    tab_selected="#ffffff",
    tab_text="#263442",
    tab_selected_text="#111820",
    terminal="#ffffff",
    terminal_text="#102030",
    terminal_accent="#315f8f",
    log="#ffffff",
    log_text="#1d2a36",
    status="#315f8f",
)


GUI_DESIGN_PRESETS: tuple[GuiDesignPreset, ...] = (
    _preset(
        id=DEFAULT_GUI_DESIGN_ID,
        label="Native",
        description="System-friendly Windows layout with quiet chrome and readable terminal panes.",
        profile_width=305,
        log_height=165,
        tab_position="north",
        density="comfortable",
        toolbar_icon_size=16,
        list_spacing=2,
        document_mode=True,
        colors=NATIVE_COLORS,
        radius=4,
        control_padding="5px 9px",
        tab_padding="7px 13px",
        tree_padding="6px 7px",
    ),
    _preset(
        id="mobaxterm",
        label="MobaXterm-style",
        description="MobaXterm-like dark shell with quick connect, session tree, home tab and large ribbon actions.",
        profile_width=395,
        log_height=120,
        tab_position="north",
        density="moba-shell",
        toolbar_icon_size=24,
        list_spacing=1,
        document_mode=True,
        colors=MOBAXTERM_COLORS,
        radius=2,
        control_padding="4px 8px",
        tab_padding="4px 13px",
        tree_padding="3px 5px",
    ),
    _preset(
        id="securecrt",
        label="SecureCRT-style",
        description="Native Windows terminal workspace with menu chrome, command dock and compact session tabs.",
        profile_width=270,
        log_height=118,
        tab_position="north",
        density="terminal",
        toolbar_icon_size=15,
        list_spacing=1,
        document_mode=False,
        colors=SECURECRT_COLORS,
        radius=2,
        control_padding="4px 8px",
        tab_padding="6px 14px",
        tree_padding="5px 6px",
    ),
    _preset(
        id="termius",
        label="Termius-style",
        description="Dark SSH-focused workspace with compact hosts, vault cues and vertical session tabs.",
        profile_width=292,
        log_height=136,
        tab_position="west",
        density="focused",
        toolbar_icon_size=16,
        list_spacing=2,
        document_mode=True,
        colors=TERMIUS_COLORS,
        radius=5,
        control_padding="5px 9px",
        tab_padding="8px 12px",
        tree_padding="6px 7px",
    ),
    _preset(
        id="remmina",
        label="Remmina-style",
        description="Light remote-desktop workspace with clear protocol profiles and viewer tabs.",
        profile_width=320,
        log_height=158,
        tab_position="north",
        density="comfortable",
        toolbar_icon_size=16,
        list_spacing=2,
        document_mode=True,
        colors=REMMINA_COLORS,
        radius=4,
        control_padding="5px 9px",
        tab_padding="7px 13px",
        tree_padding="6px 7px",
    ),
    _preset(
        id="mremoteng",
        label="mRemoteNG-style",
        description="Classic docked connection manager with tree, config, document tabs and notifications.",
        profile_width=355,
        log_height=145,
        tab_position="north",
        density="classic",
        toolbar_icon_size=15,
        list_spacing=1,
        document_mode=True,
        colors=MREMOTENG_COLORS,
        radius=2,
        control_padding="4px 8px",
        tab_padding="6px 11px",
        tree_padding="5px 6px",
    ),
)


def gui_design_preset_ids() -> list[str]:
    return [preset.id for preset in GUI_DESIGN_PRESETS]


def gui_design_preset_labels() -> list[str]:
    return [preset.label for preset in GUI_DESIGN_PRESETS]


def gui_design_preset_catalog_route() -> GuiPresetCatalogRoute:
    option_ids = tuple(gui_design_preset_ids())
    option_labels = tuple(gui_design_preset_labels())
    product_presets = tuple(preset for preset in GUI_DESIGN_PRESETS if preset.id != DEFAULT_GUI_DESIGN_ID)
    default_preset = next(preset for preset in GUI_DESIGN_PRESETS if preset.id == DEFAULT_GUI_DESIGN_ID)
    return GuiPresetCatalogRoute(
        key="gui-preset-selector-catalog-route",
        route_role="preset-catalog-to-design-selector-options",
        selector_object="designSelect",
        option_ids=option_ids,
        option_labels=option_labels,
        product_preset_ids=tuple(preset.id for preset in product_presets),
        product_preset_labels=tuple(preset.label for preset in product_presets),
        default_preset_id=default_preset.id,
        default_preset_label=default_preset.label,
        option_count=len(option_ids),
        product_option_count=len(product_presets),
        selector_property="presetCatalogRouteOptionIds",
        option_labels_property="presetCatalogRouteOptionLabels",
        product_ids_property="presetCatalogRouteProductPresetIds",
        default_property="presetCatalogRouteDefaultPresetId",
        render_source="gui-design-preset-catalog",
    )


def gui_design_preset_visual_signature(preset_id: str) -> GuiPresetVisualSignature:
    preset = get_gui_design_preset(preset_id)
    colors = preset.colors
    return GuiPresetVisualSignature(
        key=f"{preset.id}-visual-signature",
        route_role="preset-palette-density-to-live-static-style",
        preset_id=preset.id,
        preset_label=preset.label,
        density=preset.density,
        tab_position=preset.tab_position,
        document_mode=preset.document_mode,
        profile_width=preset.profile_width,
        log_height=preset.log_height,
        toolbar_icon_size=preset.toolbar_icon_size,
        list_spacing=preset.list_spacing,
        window_color=colors.window,
        toolbar_color=colors.toolbar,
        toolbar_border_color=colors.toolbar_border,
        control_color=colors.control,
        control_text_color=colors.control_text,
        primary_color=colors.primary,
        sidebar_color=colors.sidebar,
        sidebar_selected_color=colors.sidebar_selected,
        pane_color=colors.pane,
        pane_border_color=colors.pane_border,
        tab_color=colors.tab,
        tab_selected_color=colors.tab_selected,
        terminal_color=colors.terminal,
        terminal_text_color=colors.terminal_text,
        terminal_accent_color=colors.terminal_accent,
        status_color=colors.status,
        window_object="remoteOpsMain",
        main_toolbar_object="mainToolbar",
        layout_toolbar_object="layoutToolbar",
        left_panel_object="leftPanel",
        profile_tree_object="profileTree",
        tabs_object="sessionTabs",
        activity_log_object="activityLog",
        status_bar_object="statusBar",
        density_property="presetVisualSignatureDensity",
        palette_property="presetVisualSignaturePalette",
        render_source="gui-design-preset-style",
    )


def gui_design_preset_keyboard_shortcut_route(preset_id: str) -> GuiPresetKeyboardShortcutRoute:
    if preset_id not in PRODUCT_GUI_PRESET_IDS:
        raise ValueError(f"preset has no product keyboard shortcut route: {preset_id}")
    shortcut_keys = tuple(item[0] for item in GUI_DESIGN_KEYBOARD_SHORTCUTS)
    sequences = tuple(item[1] for item in GUI_DESIGN_KEYBOARD_SHORTCUTS)
    action_labels = tuple(item[2] for item in GUI_DESIGN_KEYBOARD_SHORTCUTS)
    return GuiPresetKeyboardShortcutRoute(
        key=f"{preset_id}-keyboard-shortcut-route",
        route_role="product-preset-keyboard-shortcuts",
        preset_id=preset_id,
        shortcut_object="presetKeyboardShortcut",
        expected_shortcut_keys=shortcut_keys,
        expected_sequences=sequences,
        expected_action_labels=action_labels,
        expected_shortcut_count=len(shortcut_keys),
        shortcut_key_property="presetKeyboardShortcutKey",
        shortcut_sequence_property="presetKeyboardShortcutSequence",
        shortcut_action_property="presetKeyboardShortcutActionLabel",
        captured_property="presetKeyboardShortcutsCaptured",
        captured_keys_property="presetKeyboardShortcutCapturedKeys",
        captured_sequences_property="presetKeyboardShortcutCapturedSequences",
        captured_action_labels_property="presetKeyboardShortcutCapturedActionLabels",
        captured_count_property="presetKeyboardShortcutCapturedCount",
        render_source="gui-design-keyboard-shortcuts",
    )


def gui_design_command_surface_actions(preset_id: str) -> tuple[tuple[str, str, str], ...]:
    if preset_id == "mobaxterm":
        tooltips = gui_design_moba_ribbon_tooltips()
        return tuple(
            (action.icon_key, action.label, tooltips[action.icon_key])
            for action in gui_design_moba_ribbon_actions()
        )
    return gui_design_toolbar_actions(preset_id)


def gui_design_preset_command_surface_route(preset_id: str) -> GuiPresetCommandSurfaceRoute:
    if preset_id not in PRODUCT_GUI_PRESET_IDS:
        raise ValueError(f"preset has no product command surface route: {preset_id}")
    state = gui_design_interaction_state(preset_id)
    actions = gui_design_command_surface_actions(preset_id)
    action_states: list[tuple[str, str]] = []
    for key, _label, _tooltip in actions:
        action_state = "normal"
        if key == state.active_toolbar_key:
            action_state = "active"
        elif key == state.checked_toolbar_key:
            action_state = "checked"
        elif key == state.disabled_toolbar_key:
            action_state = "disabled"
        action_states.append((key, action_state))
    return GuiPresetCommandSurfaceRoute(
        key=f"{preset_id}-command-surface-route",
        route_role="product-preset-command-surface-route",
        preset_id=preset_id,
        toolbar_object="mainToolbar",
        command_object="mobaRibbonButton" if preset_id == "mobaxterm" else "productToolbarButton",
        expected_action_keys=tuple(key for key, _label, _tooltip in actions),
        expected_action_labels=tuple(label for _key, label, _tooltip in actions),
        expected_action_tooltips=tuple(tooltip for _key, _label, tooltip in actions),
        expected_action_states=tuple(action_states),
        expected_action_count=len(actions),
        key_property="presetCommandSurfaceActionKey",
        label_property="presetCommandSurfaceActionLabel",
        tooltip_property="presetCommandSurfaceActionTooltip",
        state_property="interactionState",
        captured_property="presetCommandSurfaceCaptured",
        captured_keys_property="presetCommandSurfaceCapturedKeys",
        captured_labels_property="presetCommandSurfaceCapturedLabels",
        captured_tooltips_property="presetCommandSurfaceCapturedTooltips",
        captured_states_property="presetCommandSurfaceCapturedStates",
        captured_count_property="presetCommandSurfaceCapturedCount",
        render_source="gui-design-command-surface-route",
    )


GUI_DESIGN_FOCUS_INTERACTION_OBJECTS: dict[str, str] = {
    "quick-connect": "quickConnect",
    "search-log": "toolbarSearch",
    "session-filter": "secureCrtSessionFilter",
    "host-search": "termiusHostSearch",
    "profile-filter": "remminaProfileFilter",
    "tree-filter": "mRemoteNgDocumentFilter",
}


def gui_design_home_search_entry_placeholder(preset_id: str, entry_search_control: str) -> str:
    if preset_id == "mobaxterm":
        return gui_design_moba_quick_connect_chrome().placeholder
    if preset_id == "securecrt":
        return gui_design_securecrt_session_manager_chrome().filter_placeholder
    if preset_id == "termius":
        return gui_design_termius_hosts_chrome().filter_placeholder
    if preset_id == "remmina":
        return gui_design_remmina_profile_list_chrome().filter_placeholder
    if preset_id == "mremoteng":
        return gui_design_mremoteng_document_toolbar_chrome().filter_placeholder
    raise ValueError(f"preset has no product home/search entry placeholder: {entry_search_control}")


def gui_design_preset_home_search_route(preset_id: str) -> GuiPresetHomeSearchRoute:
    if preset_id not in PRODUCT_GUI_PRESET_IDS:
        raise ValueError(f"preset has no product home/search route: {preset_id}")
    surface = gui_design_workspace_surface(preset_id)
    state = gui_design_interaction_state(preset_id)
    entry_search_object = GUI_DESIGN_FOCUS_INTERACTION_OBJECTS[state.focused_control]
    recent_labels = tuple(item for column in surface.recent_columns for item in column)
    return GuiPresetHomeSearchRoute(
        key=f"{preset_id}-home-search-route",
        route_role="product-preset-home-search-entry-route",
        preset_id=preset_id,
        home_tab_label=gui_design_home_tab_label(preset_id),
        home_search_object="homeSearch",
        entry_search_control=state.focused_control,
        entry_search_object=entry_search_object,
        container_object="mobaHomeWelcomeSurface" if preset_id == "mobaxterm" else "welcomePanel",
        recent_label_object="mobaRecentSession" if preset_id == "mobaxterm" else "recentSessionsLabel",
        placeholder_text=surface.home_search_placeholder,
        entry_placeholder_text=gui_design_home_search_entry_placeholder(preset_id, state.focused_control),
        expected_home_actions=surface.home_actions,
        expected_recent_labels=recent_labels,
        expected_recent_count=len(recent_labels),
        placeholder_property="presetHomeSearchPlaceholder",
        entry_placeholder_property="presetHomeSearchEntryPlaceholder",
        captured_property="presetHomeSearchCaptured",
        captured_placeholder_property="presetHomeSearchCapturedPlaceholder",
        captured_entry_placeholder_property="presetHomeSearchCapturedEntryPlaceholder",
        captured_text_property="presetHomeSearchCapturedText",
        captured_entry_text_property="presetHomeSearchCapturedEntryText",
        captured_actions_property="presetHomeSearchCapturedActions",
        captured_recent_labels_property="presetHomeSearchCapturedRecentLabels",
        captured_recent_count_property="presetHomeSearchCapturedRecentCount",
        render_source="gui-design-home-search-route",
    )


def gui_design_preset_focus_interaction_route(preset_id: str) -> GuiPresetFocusInteractionRoute:
    if preset_id not in PRODUCT_GUI_PRESET_IDS:
        raise ValueError(f"preset has no product focus interaction route: {preset_id}")
    state = gui_design_interaction_state(preset_id)
    return GuiPresetFocusInteractionRoute(
        key=f"{preset_id}-focus-interaction-route",
        route_role="product-preset-focus-interaction-route",
        preset_id=preset_id,
        focused_control=state.focused_control,
        focus_object=GUI_DESIGN_FOCUS_INTERACTION_OBJECTS[state.focused_control],
        active_toolbar_key=state.active_toolbar_key,
        checked_toolbar_key=state.checked_toolbar_key,
        disabled_toolbar_key=state.disabled_toolbar_key,
        selected_tree_label=state.selected_tree_label,
        active_tab_status=state.active_tab_status,
        status_note=state.status_note,
        status_bar_object="statusBar",
        profile_tree_object="profileTree",
        focused_state_property="interactionState",
        captured_property="presetFocusInteractionCaptured",
        captured_focus_property="presetFocusInteractionCapturedFocus",
        captured_focus_state_property="presetFocusInteractionCapturedState",
        captured_status_message_property="presetFocusInteractionStatusMessage",
        captured_selected_tree_property="presetFocusInteractionCapturedSelectedTreeLabel",
        captured_toolbar_states_property="presetFocusInteractionToolbarStates",
        render_source="gui-design-focus-interaction-route",
    )


PRESET_ISOLATION_PRODUCT_OBJECTS: tuple[str, ...] = (
    "mobaQuickConnectChrome",
    "quickConnect",
    "mobaRail",
    "mobaConnectedLeftDock",
    "mobaSftpBrowser",
    "mobaRemoteMonitoring",
    "mobaSshBanner",
    "mobaTelemetryBar",
    "mobaBottomEdgeControls",
    "secureCrtMenuBar",
    "secureCrtSessionManagerChrome",
    "secureCrtSessionStatusStrip",
    "secureCrtCommandWindow",
    "termiusHostsChrome",
    "termiusHeaderChips",
    "termiusHostIdentityStrip",
    "remminaProfileListChrome",
    "remminaViewerControls",
    "mRemoteNgMenuBar",
    "mRemoteNgDocumentControls",
    "mRemoteNgPropertyGrid",
)

PRESET_ISOLATION_VISIBLE_OBJECTS: dict[str, tuple[str, ...]] = {
    DEFAULT_GUI_DESIGN_ID: (
        "mainToolbar",
        "layoutToolbar",
        "leftPanelHeader",
        "profileTree",
        "sessionTabs",
        "activityLog",
        "productWorkflowEvidence",
        "productWorkspaceSurface",
        "productReferenceState",
    ),
    "mobaxterm": (
        "mainToolbar",
        "sessionTabs",
        "mobaQuickConnectChrome",
        "quickConnect",
        "mobaRail",
        "mobaConnectedLeftDock",
        "mobaSftpBrowser",
        "mobaRemoteMonitoring",
        "mobaSshBanner",
        "mobaTelemetryBar",
        "mobaBottomEdgeControls",
    ),
    "securecrt": (
        "mainToolbar",
        "layoutToolbar",
        "leftPanelHeader",
        "profileTree",
        "sessionTabs",
        "activityLog",
        "productWorkflowEvidence",
        "productWorkspaceSurface",
        "productReferenceState",
        "secureCrtMenuBar",
        "secureCrtSessionManagerChrome",
        "secureCrtSessionStatusStrip",
        "secureCrtCommandWindow",
    ),
    "termius": (
        "mainToolbar",
        "layoutToolbar",
        "leftPanelHeader",
        "profileTree",
        "sessionTabs",
        "activityLog",
        "productWorkflowEvidence",
        "productWorkspaceSurface",
        "productReferenceState",
        "termiusHostsChrome",
        "termiusHeaderChips",
        "termiusHostIdentityStrip",
    ),
    "remmina": (
        "mainToolbar",
        "layoutToolbar",
        "leftPanelHeader",
        "profileTree",
        "sessionTabs",
        "activityLog",
        "productWorkflowEvidence",
        "productWorkspaceSurface",
        "productReferenceState",
        "remminaProfileListChrome",
        "remminaViewerControls",
    ),
    "mremoteng": (
        "mainToolbar",
        "layoutToolbar",
        "leftPanelHeader",
        "profileTree",
        "sessionTabs",
        "activityLog",
        "productWorkflowEvidence",
        "productWorkspaceSurface",
        "productReferenceState",
        "mRemoteNgMenuBar",
        "mRemoteNgDocumentControls",
        "mRemoteNgPropertyGrid",
    ),
}


def gui_design_preset_isolation_route(preset_id: str) -> GuiPresetIsolationRoute:
    preset = get_gui_design_preset(preset_id)
    visible_objects = PRESET_ISOLATION_VISIBLE_OBJECTS[preset.id]
    hidden_objects = tuple(
        object_name
        for object_name in (
            "layoutToolbar",
            "leftPanelHeader",
            "activityLog",
            "productWorkflowEvidence",
            "productWorkspaceSurface",
            "productReferenceState",
            *PRESET_ISOLATION_PRODUCT_OBJECTS,
        )
        if object_name not in visible_objects
    )
    return GuiPresetIsolationRoute(
        key=f"{preset.id}-preset-isolation-route",
        route_role="active-preset-visible-hidden-widget-isolation",
        preset_id=preset.id,
        visible_objects=visible_objects,
        hidden_objects=hidden_objects,
        visible_property="presetIsolationVisibleObjects",
        hidden_property="presetIsolationHiddenObjects",
        render_source="gui-design-preset-visibility",
    )


def gui_design_preset_transition_route(preset_id: str) -> GuiPresetTransitionRoute:
    preset = get_gui_design_preset(preset_id)
    preset_ids = gui_design_preset_ids()
    source_ids = tuple(source_id for source_id in preset_ids if source_id != preset.id)
    isolation_route = gui_design_preset_isolation_route(preset.id)
    return GuiPresetTransitionRoute(
        key=f"{preset.id}-preset-transition-route",
        route_role="selector-style-switch-resets-inactive-product-chrome",
        from_preset_ids=source_ids,
        to_preset_id=preset.id,
        to_preset_index=preset_ids.index(preset.id),
        selector_object="designSelect",
        reset_objects=isolation_route.hidden_objects,
        route_property="presetTransitionRouteKey",
        from_property="presetTransitionFromPresetIds",
        to_property="presetTransitionToPresetId",
        reset_property="presetTransitionResetObjects",
        render_source="gui-design-preset-transition",
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


def gui_design_securecrt_command_window_chrome() -> GuiSecureCrtCommandWindowChrome:
    return GUI_DESIGN_SECURECRT_COMMAND_WINDOW_CHROME


def gui_design_securecrt_command_window_send_route() -> GuiSecureCrtCommandWindowSendRoute:
    return GUI_DESIGN_SECURECRT_COMMAND_WINDOW_SEND_ROUTE


def gui_design_securecrt_session_status_strip() -> GuiSecureCrtSessionStatusStrip:
    return GUI_DESIGN_SECURECRT_SESSION_STATUS_STRIP


def gui_design_securecrt_session_manager_chrome() -> GuiSecureCrtSessionManagerChrome:
    return GUI_DESIGN_SECURECRT_SESSION_MANAGER_CHROME


def gui_design_securecrt_session_manager_route() -> GuiSecureCrtSessionManagerRoute:
    return GUI_DESIGN_SECURECRT_SESSION_MANAGER_ROUTE


def gui_design_securecrt_session_manager_filter_route() -> GuiSecureCrtSessionManagerFilterRoute:
    return GUI_DESIGN_SECURECRT_SESSION_MANAGER_FILTER_ROUTE


def gui_design_securecrt_sftp_tab_route() -> GuiSecureCrtSftpTabRoute:
    return GUI_DESIGN_SECURECRT_SFTP_TAB_ROUTE


def gui_design_securecrt_sftp_browser_route() -> GuiSecureCrtSftpBrowserRoute:
    return GUI_DESIGN_SECURECRT_SFTP_BROWSER_ROUTE


def gui_design_securecrt_top_chrome() -> GuiSecureCrtTopChrome:
    return GUI_DESIGN_SECURECRT_TOP_CHROME


def gui_design_mremoteng_top_chrome() -> GuiMRemoteNgTopChrome:
    return GUI_DESIGN_MREMOTENG_TOP_CHROME


def gui_design_remmina_viewer_controls() -> tuple[GuiRemminaViewerControl, ...]:
    return GUI_DESIGN_REMMINA_VIEWER_CONTROLS


def gui_design_remmina_profile_list_chrome() -> GuiRemminaProfileListChrome:
    return GUI_DESIGN_REMMINA_PROFILE_LIST_CHROME


def gui_design_remmina_profile_viewer_route() -> GuiRemminaProfileViewerRoute:
    return GUI_DESIGN_REMMINA_PROFILE_VIEWER_ROUTE


def gui_design_remmina_profile_filter_route() -> GuiRemminaProfileFilterRoute:
    return GUI_DESIGN_REMMINA_PROFILE_FILTER_ROUTE


def gui_design_remmina_clipboard_route() -> GuiRemminaClipboardRoute:
    return GUI_DESIGN_REMMINA_CLIPBOARD_ROUTE


def gui_design_remmina_screenshot_route() -> GuiRemminaScreenshotRoute:
    return GUI_DESIGN_REMMINA_SCREENSHOT_ROUTE


def gui_design_remmina_sftp_transfer_route() -> GuiRemminaSftpTransferRoute:
    return GUI_DESIGN_REMMINA_SFTP_TRANSFER_ROUTE


def gui_design_termius_header_chips() -> tuple[GuiTermiusHeaderChip, ...]:
    return GUI_DESIGN_TERMIUS_HEADER_CHIPS


def gui_design_termius_hosts_chrome() -> GuiTermiusHostsChrome:
    return GUI_DESIGN_TERMIUS_HOSTS_CHROME


def gui_design_termius_host_identity_strip() -> GuiTermiusHostIdentityStrip:
    return GUI_DESIGN_TERMIUS_HOST_IDENTITY_STRIP


def gui_design_termius_sync_route() -> GuiTermiusSyncRoute:
    return GUI_DESIGN_TERMIUS_SYNC_ROUTE


def gui_design_termius_host_selection_route() -> GuiTermiusHostSelectionRoute:
    return GUI_DESIGN_TERMIUS_HOST_SELECTION_ROUTE


def gui_design_termius_port_forward_route() -> GuiTermiusPortForwardRoute:
    return GUI_DESIGN_TERMIUS_PORT_FORWARD_ROUTE


def gui_design_termius_snippet_route() -> GuiTermiusSnippetRoute:
    return GUI_DESIGN_TERMIUS_SNIPPET_ROUTE


def gui_design_termius_files_browser_route() -> GuiTermiusFilesBrowserRoute:
    return GUI_DESIGN_TERMIUS_FILES_BROWSER_ROUTE


def gui_design_mremoteng_document_toolbar_chrome() -> GuiMRemoteNgDocumentToolbarChrome:
    return GUI_DESIGN_MREMOTENG_DOCUMENT_TOOLBAR_CHROME


def gui_design_mremoteng_document_controls() -> tuple[GuiMRemoteNgDocumentControl, ...]:
    return GUI_DESIGN_MREMOTENG_DOCUMENT_CONTROLS


def gui_design_mremoteng_property_grid_chrome() -> GuiMRemoteNgPropertyGridChrome:
    return GUI_DESIGN_MREMOTENG_PROPERTY_GRID_CHROME


def gui_design_mremoteng_connection_document_route() -> GuiMRemoteNgConnectionDocumentRoute:
    return GUI_DESIGN_MREMOTENG_CONNECTION_DOCUMENT_ROUTE


def gui_design_mremoteng_document_filter_route() -> GuiMRemoteNgDocumentFilterRoute:
    return GUI_DESIGN_MREMOTENG_DOCUMENT_FILTER_ROUTE


def gui_design_mremoteng_inheritance_route() -> GuiMRemoteNgInheritanceRoute:
    return GUI_DESIGN_MREMOTENG_INHERITANCE_ROUTE


def gui_design_sidebar_copy(preset_id: str) -> tuple[str, str]:
    return GUI_DESIGN_SIDEBAR_COPY.get(preset_id, GUI_DESIGN_SIDEBAR_COPY[DEFAULT_GUI_DESIGN_ID])


def gui_design_toolbar_actions(preset_id: str) -> tuple[tuple[str, str, str], ...]:
    return GUI_DESIGN_TOOLBAR_COPY.get(preset_id, GUI_DESIGN_TOOLBAR_COPY[DEFAULT_GUI_DESIGN_ID])


def gui_design_status_segments(preset_id: str) -> tuple[str, ...]:
    return GUI_DESIGN_STATUS_COPY.get(preset_id, GUI_DESIGN_STATUS_COPY[DEFAULT_GUI_DESIGN_ID])


def gui_design_tree_root_copy(preset_id: str) -> tuple[str, str]:
    return GUI_DESIGN_TREE_ROOT_COPY.get(preset_id, GUI_DESIGN_TREE_ROOT_COPY[DEFAULT_GUI_DESIGN_ID])


def gui_design_tree_root_icon(preset_id: str) -> GuiDesignTreeRowIcon:
    return GUI_DESIGN_TREE_ROOT_ICONS.get(preset_id, GUI_DESIGN_TREE_ROOT_ICONS[DEFAULT_GUI_DESIGN_ID])


def gui_design_tree_rows(preset_id: str) -> tuple[tuple[str, str, bool], ...]:
    return GUI_DESIGN_TREE_ROWS.get(preset_id, GUI_DESIGN_TREE_ROWS[DEFAULT_GUI_DESIGN_ID])


def gui_design_tree_row_icons(preset_id: str) -> tuple[GuiDesignTreeRowIcon, ...]:
    explicit = GUI_DESIGN_TREE_ROW_ICONS.get(preset_id)
    if explicit is not None:
        return explicit
    return tuple(_tree_row_icon_from_values(preset_id, name, target, group) for name, target, group in gui_design_tree_rows(preset_id))


def gui_design_tree_row_icon(preset_id: str, name: str, target: str, group: bool) -> GuiDesignTreeRowIcon:
    label = name.strip()
    for row_icon in gui_design_tree_row_icons(preset_id):
        if row_icon.label == label:
            return row_icon
    return _tree_row_icon_from_values(preset_id, name, target, group)


def gui_design_tree_row_icon_key(preset_id: str, name: str, target: str, group: bool) -> str:
    return gui_design_tree_row_icon(preset_id, name, target, group).icon_key


def gui_design_moba_session_tree_chrome() -> GuiMobaSessionTreeChrome:
    return GUI_DESIGN_MOBA_SESSION_TREE_CHROME


def _tree_row_icon_from_values(preset_id: str, name: str, target: str, group: bool) -> GuiDesignTreeRowIcon:
    label = name.strip()
    value = f"{name} {target}".lower()
    if group:
        icon_key = "database" if any(token in value for token in ("xml", "database", "vault")) else "folder"
        return GuiDesignTreeRowIcon(label, icon_key, "group", 14)
    if "rdp" in value:
        icon_key = "rdp"
    elif "vnc" in value:
        icon_key = "vnc"
    elif "sftp" in value or "file" in value:
        icon_key = "sftp"
    elif "local" in value or "powershell" in value:
        icon_key = "shell"
    elif "snippet" in value or "deploy" in value:
        icon_key = "snippet"
    elif "jump" in value or "pinned" in value:
        icon_key = "pin"
    elif preset_id == "termius":
        icon_key = "host"
    elif "ssh2" in value:
        icon_key = "ssh2"
    else:
        icon_key = "ssh"
    return GuiDesignTreeRowIcon(label, icon_key, "profile", 14)


def gui_design_home_tab_label(preset_id: str) -> str:
    return GUI_DESIGN_HOME_TAB_COPY.get(preset_id, GUI_DESIGN_HOME_TAB_COPY[DEFAULT_GUI_DESIGN_ID])


def gui_design_tab_items(preset_id: str) -> tuple[tuple[str, str, bool], ...]:
    return GUI_DESIGN_TAB_COPY.get(preset_id, GUI_DESIGN_TAB_COPY[DEFAULT_GUI_DESIGN_ID])


def gui_design_workspace_surface(preset_id: str) -> GuiWorkspaceSurface:
    return GUI_DESIGN_WORKSPACE_SURFACES.get(preset_id, GUI_DESIGN_WORKSPACE_SURFACES[DEFAULT_GUI_DESIGN_ID])


def gui_design_workflow_cards(preset_id: str) -> tuple[GuiProductWorkflowCard, ...]:
    return GUI_DESIGN_WORKFLOW_CARDS.get(preset_id, GUI_DESIGN_WORKFLOW_CARDS[DEFAULT_GUI_DESIGN_ID])


def gui_design_reference_state(preset_id: str) -> GuiProductReferenceState:
    return GUI_DESIGN_REFERENCE_STATES.get(preset_id, GUI_DESIGN_REFERENCE_STATES[DEFAULT_GUI_DESIGN_ID])


def gui_design_product_identity_route(preset_id: str) -> GuiProductIdentityRoute:
    reference = gui_design_reference_state(preset_id)
    selected_tree_label = GUI_DESIGN_PRODUCT_IDENTITY_TREE_LABELS.get(preset_id, reference.active_tab_label)
    return GuiProductIdentityRoute(
        key=f"{preset_id}-product-identity-route",
        route_role="tree-tab-reference-status-workspace-identity",
        preset_id=preset_id,
        selected_profile_name=reference.profile_name,
        selected_tree_label=selected_tree_label,
        target_label=reference.target_label,
        protocol_label=reference.protocol_label,
        active_tab_label=reference.active_tab_label,
        sidebar_label=reference.sidebar_label,
        workspace_state=reference.workspace_state,
        status_segments=reference.status_segments,
        reference_state_object="productReferenceState",
        reference_item_object="productReferenceStateItem",
        tree_object="profileTree",
        tabs_object="sessionTabs",
        status_segment_object="productStatusSegment",
        workspace_surface_object="productWorkspaceSurface",
        profile_property="productIdentityProfile",
        target_property="productIdentityTarget",
        protocol_property="productIdentityProtocol",
        active_tab_property="productIdentityActiveTab",
        sidebar_property="productIdentitySidebar",
        workspace_state_property="productIdentityWorkspaceState",
        status_segments_property="productIdentityStatusSegments",
        render_source="gui-design-reference-state",
    )


def gui_design_preset_reference_tab_route(preset_id: str) -> GuiPresetReferenceTabRoute:
    if preset_id not in PRODUCT_REFERENCE_TAB_PRESET_IDS:
        raise ValueError(f"preset has no product reference tab activation route: {preset_id}")
    identity_route = gui_design_product_identity_route(preset_id)
    return GuiPresetReferenceTabRoute(
        key=f"{preset_id}-reference-tab-activation-route",
        route_role="reference-profile-tab-can-be-active-surface",
        preset_id=preset_id,
        reference_profile=identity_route.selected_profile_name,
        active_tab_label=identity_route.active_tab_label,
        home_tab_label=gui_design_home_tab_label(preset_id),
        tabs_object=identity_route.tabs_object,
        home_tab_role="home",
        reference_tab_role="terminal",
        activated_label_property="presetReferenceTabActivatedLabel",
        returned_home_label_property="presetReferenceTabReturnedHomeLabel",
        active_tab_property="presetReferenceTabActiveLabel",
        home_tab_property="presetReferenceTabHomeLabel",
        reference_profile_property="presetReferenceTabProfile",
        render_source="gui-design-reference-tab-route",
    )


def gui_design_preset_reference_tab_chrome_route(preset_id: str) -> GuiPresetReferenceTabChromeRoute:
    if preset_id not in PRODUCT_REFERENCE_TAB_PRESET_IDS:
        raise ValueError(f"preset has no active reference tab chrome route: {preset_id}")
    tab_route = gui_design_preset_reference_tab_route(preset_id)
    interaction = gui_design_interaction_state(preset_id)
    preset = get_gui_design_preset(preset_id)
    return GuiPresetReferenceTabChromeRoute(
        key=f"{preset_id}-reference-tab-chrome-evidence-route",
        route_role="active-reference-tab-chrome-evidence",
        preset_id=preset_id,
        reference_profile=tab_route.reference_profile,
        active_tab_label=tab_route.active_tab_label,
        home_tab_label=tab_route.home_tab_label,
        tabs_object=tab_route.tabs_object,
        tab_bar_object="sessionTabBar",
        reference_tab_role=tab_route.reference_tab_role,
        new_session_tab_role="new-session",
        expected_tab_position=preset.tab_position,
        expected_tooltip=f"{tab_route.active_tab_label}: {interaction.active_tab_status}",
        expected_closeable=True,
        expected_selected_during_capture=True,
        captured_property="presetReferenceTabChromeCaptured",
        captured_label_property="presetReferenceTabChromeLabel",
        captured_tooltip_property="presetReferenceTabChromeTooltip",
        captured_index_property="presetReferenceTabChromeIndex",
        captured_role_property="presetReferenceTabChromeRole",
        captured_position_property="presetReferenceTabChromePosition",
        captured_closeable_property="presetReferenceTabChromeCloseable",
        captured_selected_property="presetReferenceTabChromeSelected",
        render_source="gui-design-reference-tab-chrome",
    )


def gui_design_preset_reference_status_bar_route(preset_id: str) -> GuiPresetReferenceStatusBarRoute:
    if preset_id not in PRODUCT_REFERENCE_TAB_PRESET_IDS:
        raise ValueError(f"preset has no active reference status-bar route: {preset_id}")
    tab_route = gui_design_preset_reference_tab_route(preset_id)
    identity_route = gui_design_product_identity_route(preset_id)
    expected_status_segments = identity_route.status_segments
    expected_status_message = "Running process panes: 2" if preset_id == "remmina" else "Running process panes: 1"
    return GuiPresetReferenceStatusBarRoute(
        key=f"{preset_id}-reference-status-bar-evidence-route",
        route_role="active-reference-status-bar-evidence",
        preset_id=preset_id,
        reference_profile=tab_route.reference_profile,
        active_tab_label=tab_route.active_tab_label,
        status_bar_object="statusBar",
        status_notice_object="productStatusNotice",
        status_segment_object=identity_route.status_segment_object,
        expected_status_message=expected_status_message,
        expected_status_segments=expected_status_segments,
        expected_segment_count=len(expected_status_segments),
        captured_property="presetReferenceStatusCaptured",
        captured_tab_property="presetReferenceStatusCapturedTab",
        captured_message_property="presetReferenceStatusMessage",
        captured_segments_property="presetReferenceStatusSegments",
        captured_segment_count_property="presetReferenceStatusSegmentCount",
        captured_segment_tooltips_property="presetReferenceStatusSegmentTooltips",
        captured_notice_property="presetReferenceStatusNotice",
        render_source="gui-design-reference-status-bar",
    )


def gui_design_preset_reference_session_action_route(preset_id: str) -> GuiPresetReferenceSessionActionRoute:
    if preset_id not in PRODUCT_REFERENCE_TAB_PRESET_IDS:
        raise ValueError(f"preset has no active reference session-action route: {preset_id}")
    tab_route = gui_design_preset_reference_tab_route(preset_id)
    action_keys = (
        "new-local-terminal",
        "split-horizontal",
        "split-vertical",
        "duplicate-tab",
        "close-tab",
        "close-other-tabs",
        "recover-previous-sessions",
    )
    action_labels = (
        "New local terminal",
        "Split horizontal",
        "Split vertical",
        "Duplicate tab",
        "Close tab",
        "Close other tabs",
        "Recover previous sessions",
    )
    return GuiPresetReferenceSessionActionRoute(
        key=f"{preset_id}-reference-session-actions-route",
        route_role="active-reference-session-actions",
        preset_id=preset_id,
        reference_profile=tab_route.reference_profile,
        active_tab_label=tab_route.active_tab_label,
        tabs_object=tab_route.tabs_object,
        tab_bar_object="sessionTabBar",
        reference_tab_role=tab_route.reference_tab_role,
        action_object="sessionTabContextAction",
        expected_action_keys=action_keys,
        expected_action_labels=action_labels,
        expected_action_count=len(action_keys),
        always_enabled_action_keys=tuple(key for key in action_keys if key != "close-other-tabs"),
        conditional_enabled_action_keys=("close-other-tabs",),
        action_key_property="sessionTabContextActionKey",
        action_label_property="sessionTabContextActionLabel",
        action_enabled_property="sessionTabContextActionEnabled",
        captured_property="presetReferenceSessionActionsCaptured",
        captured_tab_property="presetReferenceSessionActionsCapturedTab",
        captured_action_keys_property="presetReferenceSessionActionKeys",
        captured_action_labels_property="presetReferenceSessionActionLabels",
        captured_action_count_property="presetReferenceSessionActionCount",
        captured_enabled_keys_property="presetReferenceSessionActionEnabledKeys",
        captured_disabled_keys_property="presetReferenceSessionActionDisabledKeys",
        render_source="gui-design-reference-session-actions",
    )


def gui_design_preset_reference_surface_route(preset_id: str) -> GuiPresetReferenceSurfaceRoute:
    if preset_id not in PRODUCT_REFERENCE_TAB_PRESET_IDS:
        raise ValueError(f"preset has no active reference tab surface route: {preset_id}")
    tab_route = gui_design_preset_reference_tab_route(preset_id)
    identity_route = gui_design_product_identity_route(preset_id)
    command_executables = ("mstsc", "xfreerdp", "wlfreerdp") if preset_id == "remmina" else ("ssh",)
    command_target = identity_route.target_label.rsplit(":", 1)[0]
    return GuiPresetReferenceSurfaceRoute(
        key=f"{preset_id}-reference-surface-evidence-route",
        route_role="active-reference-tab-surface-evidence",
        preset_id=preset_id,
        reference_profile=tab_route.reference_profile,
        active_tab_label=tab_route.active_tab_label,
        expected_title=tab_route.reference_profile,
        expected_source=f"profile:{tab_route.reference_profile}",
        command_executables=command_executables,
        command_target_fragment=command_target,
        terminal_pane_object="terminalPane",
        terminal_title_object="terminalTitle",
        terminal_source_object="terminalSource",
        terminal_command_object="terminalCommand",
        terminal_output_object="terminalOutput",
        captured_property="presetReferenceSurfaceCaptured",
        captured_tab_property="presetReferenceSurfaceCapturedTab",
        actual_title_property="presetReferenceSurfaceActualTitle",
        actual_source_property="presetReferenceSurfaceActualSource",
        actual_command_property="presetReferenceSurfaceActualCommand",
        actual_output_property="presetReferenceSurfaceActualOutput",
        render_source="gui-design-reference-surface",
    )


def gui_design_preset_reference_control_route(preset_id: str) -> GuiPresetReferenceControlRoute:
    if preset_id not in PRODUCT_REFERENCE_TAB_PRESET_IDS:
        raise ValueError(f"preset has no active reference tab control route: {preset_id}")
    surface_route = gui_design_preset_reference_surface_route(preset_id)
    return GuiPresetReferenceControlRoute(
        key=f"{preset_id}-reference-control-evidence-route",
        route_role="active-reference-tab-terminal-controls",
        preset_id=preset_id,
        reference_profile=surface_route.reference_profile,
        active_tab_label=surface_route.active_tab_label,
        terminal_pane_object=surface_route.terminal_pane_object,
        terminal_status_object="paneStatus",
        terminal_action_object="terminalAction",
        action_keys=(
            "start",
            "restart",
            "stop",
            "copy",
            "clear",
            "macro-rec",
            "macro-stop",
            "macro-cancel",
            "macro-replay",
        ),
        action_labels=(
            "Start",
            "Restart",
            "Stop",
            "Copy",
            "Clear",
            "Macro Rec",
            "Macro Stop",
            "Macro Cancel",
            "Macro Replay",
        ),
        action_tooltips=(
            "Start process",
            "Restart process",
            "Stop process",
            "Copy selected terminal output, or the launch command when nothing is selected",
            "Clear terminal output",
            "Record terminal macro",
            "Stop terminal macro",
            "Cancel macro",
            "Replay terminal macro",
        ),
        allowed_status_states=("ready", "starting", "running", "stopping", "error", "blocked"),
        action_key_property="terminalActionKey",
        action_label_property="terminalActionLabel",
        action_tooltip_property="terminalActionTooltip",
        status_state_property="state",
        captured_property="presetReferenceControlsCaptured",
        captured_actions_property="presetReferenceControlCapturedActionKeys",
        captured_status_property="presetReferenceControlStatusState",
        captured_status_text_property="presetReferenceControlStatusText",
        render_source="gui-design-reference-controls",
    )


def gui_design_preset_reference_input_route(preset_id: str) -> GuiPresetReferenceInputRoute:
    if preset_id not in PRODUCT_REFERENCE_TAB_PRESET_IDS:
        raise ValueError(f"preset has no active reference tab input route: {preset_id}")
    surface_route = gui_design_preset_reference_surface_route(preset_id)
    return GuiPresetReferenceInputRoute(
        key=f"{preset_id}-reference-input-evidence-route",
        route_role="active-reference-tab-terminal-input",
        preset_id=preset_id,
        reference_profile=surface_route.reference_profile,
        active_tab_label=surface_route.active_tab_label,
        terminal_pane_object=surface_route.terminal_pane_object,
        terminal_input_object="terminalInput",
        placeholder_text="stdin, shell command or interactive input",
        expected_initial_text="",
        allowed_enabled_states=(True, False),
        captured_property="presetReferenceInputCaptured",
        captured_tab_property="presetReferenceInputCapturedTab",
        captured_placeholder_property="presetReferenceInputPlaceholder",
        captured_text_property="presetReferenceInputText",
        captured_enabled_property="presetReferenceInputEnabled",
        render_source="gui-design-reference-input",
    )


def gui_design_preset_reference_transcript_route(preset_id: str) -> GuiPresetReferenceTranscriptRoute:
    if preset_id not in PRODUCT_REFERENCE_TAB_PRESET_IDS:
        raise ValueError(f"preset has no active reference tab transcript route: {preset_id}")
    surface_route = gui_design_preset_reference_surface_route(preset_id)
    return GuiPresetReferenceTranscriptRoute(
        key=f"{preset_id}-reference-transcript-evidence-route",
        route_role="active-reference-tab-terminal-transcript",
        preset_id=preset_id,
        reference_profile=surface_route.reference_profile,
        active_tab_label=surface_route.active_tab_label,
        terminal_pane_object=surface_route.terminal_pane_object,
        terminal_output_object=surface_route.terminal_output_object,
        command_echo_prefix="$ ",
        required_fragments=(surface_route.command_target_fragment,),
        minimum_line_count=1,
        captured_property="presetReferenceTranscriptCaptured",
        captured_tab_property="presetReferenceTranscriptCapturedTab",
        captured_text_property="presetReferenceTranscriptText",
        captured_line_count_property="presetReferenceTranscriptLineCount",
        captured_command_echo_property="presetReferenceTranscriptCommandEcho",
        render_source="gui-design-reference-transcript",
    )


def gui_design_preset_selection_route(preset_id: str) -> GuiPresetSelectionRoute:
    preset = get_gui_design_preset(preset_id)
    sidebar_title, sidebar_subtitle = gui_design_sidebar_copy(preset.id)
    preset_ids = gui_design_preset_ids()
    return GuiPresetSelectionRoute(
        key=f"{preset.id}-preset-selection-route",
        route_role="selector-to-toolbar-sidebar-tabs-status-workspace",
        preset_id=preset.id,
        preset_label=preset.label,
        preset_index=preset_ids.index(preset.id),
        selector_object="designSelect",
        main_toolbar_object="mainToolbar",
        layout_toolbar_object="layoutToolbar",
        left_panel_header_object="leftPanelHeader",
        profile_tree_object="profileTree",
        tabs_object="sessionTabs",
        status_bar_object="statusBar",
        status_segment_object="productStatusSegment",
        workspace_surface_object="productWorkspaceSurface",
        reference_state_object="productReferenceState",
        home_tab_label=gui_design_home_tab_label(preset.id),
        sidebar_title=sidebar_title,
        sidebar_subtitle=sidebar_subtitle,
        status_segments=gui_design_status_segments(preset.id),
        tab_position=preset.tab_position,
        document_mode=preset.document_mode,
        profile_width=preset.profile_width,
        log_height=preset.log_height,
        toolbar_icon_size=preset.toolbar_icon_size,
        selector_property="presetSelectionRoutePresetId",
        preset_label_property="presetSelectionRoutePresetLabel",
        home_tab_property="presetSelectionRouteHomeTabLabel",
        sidebar_title_property="presetSelectionRouteSidebarTitle",
        status_segments_property="presetSelectionRouteStatusSegments",
        render_source="gui-design-preset-metadata",
    )


def gui_design_interaction_state(preset_id: str) -> GuiInteractionState:
    return GUI_DESIGN_INTERACTION_STATES.get(preset_id, GUI_DESIGN_INTERACTION_STATES[DEFAULT_GUI_DESIGN_ID])


def get_gui_design_preset(preset_id: str) -> GuiDesignPreset:
    for preset in GUI_DESIGN_PRESETS:
        if preset.id == preset_id:
            return preset
    raise ValueError(f"unknown GUI design preset: {preset_id}")

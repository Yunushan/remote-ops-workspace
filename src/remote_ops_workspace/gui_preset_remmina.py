"""Design data for the Remmina workspace preset."""

from __future__ import annotations

from dataclasses import dataclass


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

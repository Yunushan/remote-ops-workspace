"""Design data for the SecureCRT workspace preset."""

from __future__ import annotations

from dataclasses import dataclass


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

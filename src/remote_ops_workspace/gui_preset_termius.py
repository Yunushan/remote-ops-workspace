"""Design data for the Termius workspace preset."""

from __future__ import annotations

from dataclasses import dataclass


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
    live_spacing=3,
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

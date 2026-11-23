"""Design data for the mRemoteNG workspace preset."""

from __future__ import annotations

from dataclasses import dataclass


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
    reconnect_state="reconnect requested",
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


def gui_design_mremoteng_top_chrome() -> GuiMRemoteNgTopChrome:
    return GUI_DESIGN_MREMOTENG_TOP_CHROME


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

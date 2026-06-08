from __future__ import annotations

from dataclasses import dataclass

DEFAULT_GUI_DESIGN_ID = "native"


@dataclass(frozen=True)
class GuiMobaRibbonAction:
    icon_key: str
    label: str
    color: str


@dataclass(frozen=True)
class GuiMobaTopMenuItem:
    key: str
    label: str
    primary_action: str
    tooltip: str


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
class GuiMobaRailItem:
    role: str
    label: str
    object_name: str
    icon_key: str
    color: str
    tooltip: str


@dataclass(frozen=True)
class GuiMobaRightUtilityAction:
    key: str
    icon_key: str
    label: str
    color: str
    tooltip: str


@dataclass(frozen=True)
class GuiMobaSessionEdgeAction:
    key: str
    icon_key: str
    label: str
    color: str
    tooltip: str
    static_y: int


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
class GuiMobaSftpTableColumn:
    key: str
    label: str
    static_x: int


@dataclass(frozen=True)
class GuiMobaSftpBrowserChrome:
    path_placeholder: str
    dropdown_marker: str
    parent_row_label: str
    parent_row_kind: str
    selected_row_kind: str
    columns: tuple[GuiMobaSftpTableColumn, ...]


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
class GuiMobaRemoteMonitoringDockChrome:
    title_control_key: str
    follow_control_key: str
    telemetry_surface: str
    visible_metric_keys: tuple[str, ...]
    refresh_seconds: int
    compact: bool


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
class GuiSecureCrtCommandWindowChrome:
    key: str
    title: str
    helper: str
    target_scope: str
    command: str
    send_label: str
    status: str


@dataclass(frozen=True)
class GuiSecureCrtSessionStatusField:
    key: str
    label: str
    value: str
    tooltip: str
    static_width: int


@dataclass(frozen=True)
class GuiSecureCrtSessionStatusStrip:
    title: str
    fields: tuple[GuiSecureCrtSessionStatusField, ...]


@dataclass(frozen=True)
class GuiSecureCrtSessionManagerAction:
    key: str
    icon_key: str
    label: str
    tooltip: str
    static_x: int


@dataclass(frozen=True)
class GuiSecureCrtSessionManagerChrome:
    title: str
    filter_placeholder: str
    actions: tuple[GuiSecureCrtSessionManagerAction, ...]


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


@dataclass(frozen=True)
class GuiRemminaProfileColumn:
    key: str
    label: str
    static_width: int


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


@dataclass(frozen=True)
class GuiTermiusHostIdentityStrip:
    title: str
    fields: tuple[GuiTermiusHostIdentityField, ...]


@dataclass(frozen=True)
class GuiMRemoteNgDocumentControl:
    key: str
    icon_key: str
    standard_icon: str
    label: str
    tooltip: str
    static_width: int


@dataclass(frozen=True)
class GuiMRemoteNgDocumentToolbarChrome:
    title: str
    filter_placeholder: str


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

GUI_DESIGN_MOBA_TOP_MENU_ITEMS: tuple[GuiMobaTopMenuItem, ...] = (
    GuiMobaTopMenuItem("terminal", "Terminal", "Start local terminal", "Local terminal and split-pane commands"),
    GuiMobaTopMenuItem("sessions", "Sessions", "Connect selected", "Saved session and connection commands"),
    GuiMobaTopMenuItem("view", "View", "Refresh sessions", "View preset and refresh commands"),
    GuiMobaTopMenuItem("x-server", "X server", "X server workflow", "External X server workflow status"),
    GuiMobaTopMenuItem("tools", "Tools", "Tools status", "Diagnostics and helper tools"),
    GuiMobaTopMenuItem("games", "Games", "Games disabled", "Disabled sample menu entry"),
    GuiMobaTopMenuItem("settings", "Settings", "Settings status", "Workspace settings commands"),
    GuiMobaTopMenuItem("macros", "Macros", "Macros status", "Macro and multiexec workflow status"),
    GuiMobaTopMenuItem("help", "Help", "Run doctor", "Help and doctor commands"),
)

GUI_DESIGN_MOBA_RAIL_ITEMS: tuple[GuiMobaRailItem, ...] = (
    GuiMobaRailItem(
        role="collapse",
        label="",
        object_name="mobaRailButton",
        icon_key="session",
        color="#44a6ff",
        tooltip="Collapse or restore the sessions panel",
    ),
    GuiMobaRailItem(
        role="sessions",
        label="Sessions",
        object_name="mobaRailButton",
        icon_key="session",
        color="#44a6ff",
        tooltip="Show saved sessions",
    ),
    GuiMobaRailItem(
        role="favorites",
        label="",
        object_name="mobaRailAccent",
        icon_key="sessions",
        color="#f5d000",
        tooltip="Show favorite sessions status",
    ),
    GuiMobaRailItem(
        role="tools",
        label="Tools",
        object_name="mobaRailButton",
        icon_key="tools",
        color="#e45d3f",
        tooltip="Show tools status",
    ),
    GuiMobaRailItem(
        role="macros",
        label="Macros",
        object_name="mobaRailButton",
        icon_key="multiexec",
        color="#446ee8",
        tooltip="Show macros status",
    ),
    GuiMobaRailItem(
        role="sftp",
        label="SFTP",
        object_name="mobaRailButton",
        icon_key="packages",
        color="#f4a742",
        tooltip="Show connected SFTP browser",
    ),
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
    static_height=166,
    body_top_offset=54,
    terminal_gap=18,
)


GUI_DESIGN_MOBA_RIGHT_UTILITY_ACTIONS: tuple[GuiMobaRightUtilityAction, ...] = (
    GuiMobaRightUtilityAction(
        key="clip",
        icon_key="clip",
        label="Clipboard and transfer hints",
        color="#2f8cff",
        tooltip="Show clipboard and transfer hints",
    ),
    GuiMobaRightUtilityAction(
        key="settings",
        icon_key="gear",
        label="Terminal settings",
        color="#38bdf8",
        tooltip="Show terminal settings",
    ),
    GuiMobaRightUtilityAction(
        key="tools",
        icon_key="spark",
        label="Terminal tools",
        color="#38bdf8",
        tooltip="Show terminal tools",
    ),
)


GUI_DESIGN_MOBA_SESSION_EDGE_ACTIONS: tuple[GuiMobaSessionEdgeAction, ...] = (
    GuiMobaSessionEdgeAction(
        key="attachment",
        icon_key="clip",
        label="Session attachment",
        color="#2f8cff",
        tooltip="Show attached session tools",
        static_y=112,
    ),
    GuiMobaSessionEdgeAction(
        key="settings",
        icon_key="gear",
        label="Session settings",
        color="#38bdf8",
        tooltip="Show session settings",
        static_y=130,
    ),
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
    action_spacing=96,
    recent_title="Recent sessions",
    surface_width=640,
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
        GuiMobaSftpTableColumn("name", "Name", 38),
        GuiMobaSftpTableColumn("size", "Size (KB)", 188),
        GuiMobaSftpTableColumn("modified", "Last modified", 266),
    ),
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

GUI_DESIGN_MOBA_REMOTE_MONITORING_DOCK_CHROME = GuiMobaRemoteMonitoringDockChrome(
    title_control_key="remote-monitoring",
    follow_control_key="follow-terminal-folder",
    telemetry_surface="bottom-telemetry-bar",
    visible_metric_keys=(),
    refresh_seconds=5,
    compact=True,
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
        ),
        GuiSecureCrtSessionStatusField(
            "target",
            "Target",
            "edge-prod.example.invalid:22",
            "Generic example target endpoint",
            174,
        ),
        GuiSecureCrtSessionStatusField(
            "protocol",
            "Protocol",
            "SSH2 + SFTP",
            "Terminal protocol and attached file-transfer tab",
            102,
        ),
        GuiSecureCrtSessionStatusField(
            "cipher",
            "Cipher",
            "chacha20-poly1305",
            "Reference SSH cipher label",
            122,
        ),
        GuiSecureCrtSessionStatusField(
            "sftp",
            "SFTP",
            "files-prod tab",
            "Attached SFTP tab state",
            102,
        ),
        GuiSecureCrtSessionStatusField(
            "log",
            "Log",
            "session.log",
            "Session logging state",
            90,
        ),
        GuiSecureCrtSessionStatusField(
            "state",
            "State",
            "connected",
            "Active connected-session state",
            82,
        ),
    ),
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
        ),
        GuiSecureCrtSessionManagerAction(
            "new-folder",
            "folder",
            "New Folder",
            "Create a new Session Manager folder",
            60,
        ),
        GuiSecureCrtSessionManagerAction(
            "properties",
            "properties",
            "Properties",
            "Edit selected Session Manager entry",
            86,
        ),
    ),
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
        GuiSecureCrtTopToolbarAction("edit", "properties", "Properties", "Edit session properties", 180, 82),
        GuiSecureCrtTopToolbarAction("remove", "delete", "Delete", "Delete selected session", 272, 62),
        GuiSecureCrtTopToolbarAction("connect", "connect", "Connect", "Open selected terminal session", 344, 70),
        GuiSecureCrtTopToolbarAction("files", "sftp", "SFTP", "Open SFTP tab", 424, 54),
        GuiSecureCrtTopToolbarAction("queue", "transfer", "Transfer", "Preview transfer queue", 488, 70),
        GuiSecureCrtTopToolbarAction("dry-run", "command", "Command", "Show launch command", 568, 74),
        GuiSecureCrtTopToolbarAction("doctor", "tools", "Tools", "Run tool diagnostics", 652, 54),
        GuiSecureCrtTopToolbarAction("split-h", "tile-h", "Tile H", "Tile terminal panes horizontally", 716, 58),
        GuiSecureCrtTopToolbarAction("split-v", "tile-v", "Tile V", "Tile terminal panes vertically", 784, 58),
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
        GuiMRemoteNgTopToolbarAction("edit", "config", "Config", "Edit connection configuration", 164, 62),
        GuiMRemoteNgTopToolbarAction("remove", "delete", "Delete", "Delete connection", 236, 58),
        GuiMRemoteNgTopToolbarAction("connect", "open-connection", "Open", "Open selected connection", 304, 54),
        GuiMRemoteNgTopToolbarAction("files", "external-tool", "External", "Open external file workflow", 368, 74),
        GuiMRemoteNgTopToolbarAction("queue", "transfer", "Transfer", "Preview transfer workflow", 452, 70),
        GuiMRemoteNgTopToolbarAction("dry-run", "script", "Script", "Show launch script", 532, 58),
        GuiMRemoteNgTopToolbarAction("doctor", "tools", "Tools", "Run client tools check", 600, 54),
        GuiMRemoteNgTopToolbarAction("split-h", "tile-h", "Tile H", "Tile connection panes horizontally", 664, 58),
        GuiMRemoteNgTopToolbarAction("split-v", "tile-v", "Tile V", "Tile connection panes vertically", 732, 58),
    ),
)

GUI_DESIGN_REMMINA_VIEWER_CONTROLS: tuple[GuiRemminaViewerControl, ...] = (
    GuiRemminaViewerControl("fit", "fit", "SP_TitleBarMaxButton", "Fit", "Fit remote desktop to the viewer"),
    GuiRemminaViewerControl("scale-100", "scale", "SP_ComputerIcon", "Scale 100%", "Use exact 100% viewer scale"),
    GuiRemminaViewerControl("clipboard", "clipboard", "SP_FileDialogDetailedView", "Clipboard", "Toggle clipboard sync"),
    GuiRemminaViewerControl("fullscreen", "fullscreen", "SP_TitleBarShadeButton", "Fullscreen", "Enter fullscreen viewer mode"),
    GuiRemminaViewerControl("screenshot", "screenshot", "SP_FileDialogContentsView", "Screenshot", "Capture the remote viewer"),
)

GUI_DESIGN_REMMINA_PROFILE_LIST_CHROME = GuiRemminaProfileListChrome(
    title="Connection list",
    filter_placeholder="Filter by name or protocol",
    columns=(
        GuiRemminaProfileColumn("name", "Name", 98),
        GuiRemminaProfileColumn("protocol", "Protocol", 58),
        GuiRemminaProfileColumn("server", "Server", 104),
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
        GuiTermiusHostIdentityField("host", "Host", "edge-prod", "Active SSH host profile", 92),
        GuiTermiusHostIdentityField(
            "identity",
            "Identity",
            "prod-ed25519",
            "Vault identity assigned to this host",
            112,
        ),
        GuiTermiusHostIdentityField("chain", "Chain", "direct", "Host chain or jump state", 82),
        GuiTermiusHostIdentityField("files", "Files", "SFTP ready", "Attached file workflow state", 92),
        GuiTermiusHostIdentityField(
            "forward",
            "Forward",
            "8080 -> localhost:80",
            "Port forwarding state",
            132,
        ),
        GuiTermiusHostIdentityField("snippet", "Snippet", "row vault status", "Pinned command snippet", 122),
        GuiTermiusHostIdentityField("sync", "Sync", "current", "Host inventory sync state", 82),
    ),
)

GUI_DESIGN_MREMOTENG_DOCUMENT_TOOLBAR_CHROME = GuiMRemoteNgDocumentToolbarChrome(
    title="Connections.xml",
    filter_placeholder="Filter connection tree",
)

GUI_DESIGN_MREMOTENG_DOCUMENT_CONTROLS: tuple[GuiMRemoteNgDocumentControl, ...] = (
    GuiMRemoteNgDocumentControl("save", "database", "SP_DialogSaveButton", "Save", "Save the connection document", 56),
    GuiMRemoteNgDocumentControl("reconnect", "ssh", "SP_BrowserReload", "Reconnect", "Reconnect active document", 88),
    GuiMRemoteNgDocumentControl(
        "external-tool",
        "external",
        "SP_FileDialogDetailedView",
        "External tool",
        "Open the external tool for this connection",
        104,
    ),
    GuiMRemoteNgDocumentControl("dock-view", "rdp", "SP_ComputerIcon", "Dock view", "Toggle the docked viewer", 84),
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
        disabled_toolbar_key="remove",
        focused_control="search-log",
        active_tab_status="running",
        selected_tree_label="edge-prod",
        status_note="focused search, active connect, checked files",
    ),
    "mobaxterm": GuiInteractionState(
        active_toolbar_key="sessions",
        checked_toolbar_key="sftp",
        disabled_toolbar_key="games",
        focused_control="quick-connect",
        active_tab_status="SSH direct",
        selected_tree_label="sftp-ops",
        status_note="quick connect focus, SFTP rail checked, games disabled",
    ),
    "securecrt": GuiInteractionState(
        active_toolbar_key="connect",
        checked_toolbar_key="files",
        disabled_toolbar_key="remove",
        focused_control="session-filter",
        active_tab_status="SSH2 connected",
        selected_tree_label="edge-prod (SSH2)",
        status_note="Session Manager focus, SFTP checked, delete guarded",
    ),
    "termius": GuiInteractionState(
        active_toolbar_key="connect",
        checked_toolbar_key="doctor",
        disabled_toolbar_key="remove",
        focused_control="host-search",
        active_tab_status="vault unlocked",
        selected_tree_label="prod-cluster",
        status_note="host search focus, vault checked, remove guarded",
    ),
    "remmina": GuiInteractionState(
        active_toolbar_key="connect",
        checked_toolbar_key="queue",
        disabled_toolbar_key="remove",
        focused_control="profile-filter",
        active_tab_status="viewer scaled",
        selected_tree_label="linux-console",
        status_note="profile filter focus, transfer checked, delete guarded",
    ),
    "mremoteng": GuiInteractionState(
        active_toolbar_key="connect",
        checked_toolbar_key="files",
        disabled_toolbar_key="remove",
        focused_control="tree-filter",
        active_tab_status="document open",
        selected_tree_label="edge-prod [SSH]",
        status_note="connection tree focus, external tool checked, delete guarded",
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
            "Shared   : file workflow ready",
        ),
        activity_lines=(
            "Viewer tab: win-admin",
            "Protocol group: RDP",
            "Scale mode: 100%",
            "Clipboard: on",
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
  font-size: 10px;
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
QDialog#workflowDialog QLabel#workflowTitle {{
  color: {colors.control_text};
  font-size: 18px;
  font-weight: 700;
}}
QDialog#workflowDialog QLabel#workflowSubtitle {{
  color: {colors.sidebar_muted};
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
  padding: 5px;
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
  font-size: 11px;
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
  margin: 12px 36px 8px 36px;
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
  font-size: 12px;
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
QLabel#paneStatus[state="error"] {{
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
    window="#151515",
    toolbar="#242424",
    toolbar_border="#3a3a3a",
    control="#303030",
    control_text="#eeeeee",
    control_border="#575757",
    control_hover="#d7a84a",
    primary="#d7a84a",
    primary_text="#17130b",
    danger="#b85c5c",
    danger_text="#f4caca",
    sidebar="#1b1b1b",
    sidebar_text="#e8e8e8",
    sidebar_muted="#9a9a9a",
    sidebar_selected="#3a3325",
    sidebar_selected_text="#fff4d6",
    pane="#090909",
    pane_border="#383838",
    tab="#2a2a2a",
    tab_selected="#101010",
    tab_text="#d8d8d8",
    tab_selected_text="#ffffff",
    terminal="#000000",
    terminal_text="#dcdcdc",
    terminal_accent="#72d572",
    log="#101010",
    log_text="#d0d0d0",
    status="#d7a84a",
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
        description="Terminal-first workspace with restrained dark chrome and wide session tabs.",
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
        description="Classic connection-manager workspace with a persistent tree and document tabs.",
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


def gui_design_moba_ribbon_actions() -> tuple[GuiMobaRibbonAction, ...]:
    return GUI_DESIGN_MOBA_RIBBON_ACTIONS


def gui_design_moba_top_menu_items() -> tuple[GuiMobaTopMenuItem, ...]:
    return GUI_DESIGN_MOBA_TOP_MENU_ITEMS


def gui_design_moba_titlebar_chrome() -> GuiMobaTitlebarChrome:
    return GUI_DESIGN_MOBA_TITLEBAR_CHROME


def gui_design_moba_quick_connect_chrome() -> GuiMobaQuickConnectChrome:
    return GUI_DESIGN_MOBA_QUICK_CONNECT_CHROME


def gui_design_moba_quick_connect_suggestion_chrome() -> GuiMobaQuickConnectSuggestionChrome:
    return GUI_DESIGN_MOBA_QUICK_CONNECT_SUGGESTION_CHROME


def gui_design_moba_home_welcome_chrome() -> GuiMobaHomeWelcomeChrome:
    return GUI_DESIGN_MOBA_HOME_WELCOME_CHROME


def gui_design_moba_rail_items() -> tuple[GuiMobaRailItem, ...]:
    return GUI_DESIGN_MOBA_RAIL_ITEMS


def gui_design_moba_right_utility_actions() -> tuple[GuiMobaRightUtilityAction, ...]:
    return GUI_DESIGN_MOBA_RIGHT_UTILITY_ACTIONS


def gui_design_moba_session_edge_actions() -> tuple[GuiMobaSessionEdgeAction, ...]:
    return GUI_DESIGN_MOBA_SESSION_EDGE_ACTIONS


def gui_design_moba_sftp_dock_actions() -> tuple[GuiMobaSftpDockAction, ...]:
    return GUI_DESIGN_MOBA_SFTP_DOCK_ACTIONS


def gui_design_moba_sftp_browser_chrome() -> GuiMobaSftpBrowserChrome:
    return GUI_DESIGN_MOBA_SFTP_BROWSER_CHROME


def gui_design_moba_sftp_dock_layout() -> GuiMobaSftpDockLayout:
    return GUI_DESIGN_MOBA_SFTP_DOCK_LAYOUT


def gui_design_moba_monitoring_metrics() -> tuple[GuiMobaMonitoringMetric, ...]:
    return GUI_DESIGN_MOBA_MONITORING_METRICS


def gui_design_moba_monitoring_controls() -> tuple[GuiMobaMonitoringControl, ...]:
    return GUI_DESIGN_MOBA_MONITORING_CONTROLS


def gui_design_moba_remote_monitoring_dock_chrome() -> GuiMobaRemoteMonitoringDockChrome:
    return GUI_DESIGN_MOBA_REMOTE_MONITORING_DOCK_CHROME


def gui_design_moba_status_segments() -> tuple[GuiMobaStatusSegment, ...]:
    return GUI_DESIGN_MOBA_STATUS_SEGMENTS


def gui_design_moba_status_bar_chrome() -> GuiMobaStatusBarChrome:
    return GUI_DESIGN_MOBA_STATUS_BAR_CHROME


def gui_design_moba_bottom_edge_controls() -> tuple[GuiMobaBottomEdgeControl, ...]:
    return GUI_DESIGN_MOBA_BOTTOM_EDGE_CONTROLS


def gui_design_moba_ssh_banner_chrome() -> GuiMobaSshBannerChrome:
    return GUI_DESIGN_MOBA_SSH_BANNER_CHROME


def gui_design_securecrt_command_window_chrome() -> GuiSecureCrtCommandWindowChrome:
    return GUI_DESIGN_SECURECRT_COMMAND_WINDOW_CHROME


def gui_design_securecrt_session_status_strip() -> GuiSecureCrtSessionStatusStrip:
    return GUI_DESIGN_SECURECRT_SESSION_STATUS_STRIP


def gui_design_securecrt_session_manager_chrome() -> GuiSecureCrtSessionManagerChrome:
    return GUI_DESIGN_SECURECRT_SESSION_MANAGER_CHROME


def gui_design_securecrt_top_chrome() -> GuiSecureCrtTopChrome:
    return GUI_DESIGN_SECURECRT_TOP_CHROME


def gui_design_mremoteng_top_chrome() -> GuiMRemoteNgTopChrome:
    return GUI_DESIGN_MREMOTENG_TOP_CHROME


def gui_design_remmina_viewer_controls() -> tuple[GuiRemminaViewerControl, ...]:
    return GUI_DESIGN_REMMINA_VIEWER_CONTROLS


def gui_design_remmina_profile_list_chrome() -> GuiRemminaProfileListChrome:
    return GUI_DESIGN_REMMINA_PROFILE_LIST_CHROME


def gui_design_termius_header_chips() -> tuple[GuiTermiusHeaderChip, ...]:
    return GUI_DESIGN_TERMIUS_HEADER_CHIPS


def gui_design_termius_hosts_chrome() -> GuiTermiusHostsChrome:
    return GUI_DESIGN_TERMIUS_HOSTS_CHROME


def gui_design_termius_host_identity_strip() -> GuiTermiusHostIdentityStrip:
    return GUI_DESIGN_TERMIUS_HOST_IDENTITY_STRIP


def gui_design_mremoteng_document_toolbar_chrome() -> GuiMRemoteNgDocumentToolbarChrome:
    return GUI_DESIGN_MREMOTENG_DOCUMENT_TOOLBAR_CHROME


def gui_design_mremoteng_document_controls() -> tuple[GuiMRemoteNgDocumentControl, ...]:
    return GUI_DESIGN_MREMOTENG_DOCUMENT_CONTROLS


def gui_design_mremoteng_property_grid_chrome() -> GuiMRemoteNgPropertyGridChrome:
    return GUI_DESIGN_MREMOTENG_PROPERTY_GRID_CHROME


def gui_design_sidebar_copy(preset_id: str) -> tuple[str, str]:
    return GUI_DESIGN_SIDEBAR_COPY.get(preset_id, GUI_DESIGN_SIDEBAR_COPY[DEFAULT_GUI_DESIGN_ID])


def gui_design_toolbar_actions(preset_id: str) -> tuple[tuple[str, str, str], ...]:
    return GUI_DESIGN_TOOLBAR_COPY.get(preset_id, GUI_DESIGN_TOOLBAR_COPY[DEFAULT_GUI_DESIGN_ID])


def gui_design_status_segments(preset_id: str) -> tuple[str, ...]:
    return GUI_DESIGN_STATUS_COPY.get(preset_id, GUI_DESIGN_STATUS_COPY[DEFAULT_GUI_DESIGN_ID])


def gui_design_tree_root_copy(preset_id: str) -> tuple[str, str]:
    return GUI_DESIGN_TREE_ROOT_COPY.get(preset_id, GUI_DESIGN_TREE_ROOT_COPY[DEFAULT_GUI_DESIGN_ID])


def gui_design_tree_rows(preset_id: str) -> tuple[tuple[str, str, bool], ...]:
    return GUI_DESIGN_TREE_ROWS.get(preset_id, GUI_DESIGN_TREE_ROWS[DEFAULT_GUI_DESIGN_ID])


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


def gui_design_interaction_state(preset_id: str) -> GuiInteractionState:
    return GUI_DESIGN_INTERACTION_STATES.get(preset_id, GUI_DESIGN_INTERACTION_STATES[DEFAULT_GUI_DESIGN_ID])


def get_gui_design_preset(preset_id: str) -> GuiDesignPreset:
    for preset in GUI_DESIGN_PRESETS:
        if preset.id == preset_id:
            return preset
    raise ValueError(f"unknown GUI design preset: {preset_id}")

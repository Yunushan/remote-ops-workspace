from remote_ops_workspace.gui_designs import (
    DEFAULT_GUI_DESIGN_ID,
    GUI_DESIGN_PRESETS,
    get_gui_design_preset,
    gui_design_interaction_state,
    gui_design_moba_bottom_edge_controls,
    gui_design_moba_home_welcome_chrome,
    gui_design_moba_monitoring_controls,
    gui_design_moba_monitoring_metrics,
    gui_design_moba_quick_connect_chrome,
    gui_design_moba_quick_connect_suggestion_chrome,
    gui_design_moba_rail_items,
    gui_design_moba_remote_monitoring_dock_chrome,
    gui_design_moba_ribbon_actions,
    gui_design_moba_right_utility_actions,
    gui_design_moba_session_edge_actions,
    gui_design_moba_sftp_browser_chrome,
    gui_design_moba_sftp_dock_actions,
    gui_design_moba_sftp_dock_layout,
    gui_design_moba_ssh_banner_chrome,
    gui_design_moba_status_bar_chrome,
    gui_design_moba_status_segments,
    gui_design_moba_titlebar_chrome,
    gui_design_moba_top_menu_items,
    gui_design_mremoteng_document_controls,
    gui_design_mremoteng_document_toolbar_chrome,
    gui_design_mremoteng_property_grid_chrome,
    gui_design_mremoteng_top_chrome,
    gui_design_preset_ids,
    gui_design_preset_labels,
    gui_design_reference_state,
    gui_design_remmina_profile_list_chrome,
    gui_design_remmina_viewer_controls,
    gui_design_securecrt_command_window_chrome,
    gui_design_securecrt_session_manager_chrome,
    gui_design_securecrt_session_status_strip,
    gui_design_securecrt_top_chrome,
    gui_design_termius_header_chips,
    gui_design_termius_host_identity_strip,
    gui_design_termius_hosts_chrome,
    gui_design_workflow_cards,
)


def test_gui_design_presets_include_requested_product_styles() -> None:
    ids = set(gui_design_preset_ids())
    assert {
        DEFAULT_GUI_DESIGN_ID,
        "mobaxterm",
        "securecrt",
        "termius",
        "remmina",
        "mremoteng",
    }.issubset(ids)


def test_gui_design_presets_have_valid_layout_metadata() -> None:
    labels = gui_design_preset_labels()
    assert len(labels) == len(set(labels))
    for preset in GUI_DESIGN_PRESETS:
        assert preset.id
        assert preset.label
        assert preset.description
        assert preset.profile_width >= 240
        assert preset.log_height >= 100
        assert preset.tab_position in {"north", "south", "east", "west"}
        assert preset.density
        assert 12 <= preset.toolbar_icon_size <= 24
        assert preset.list_spacing >= 0
        assert preset.colors.primary.startswith("#")
        assert "QMainWindow#remoteOpsMain" in preset.stylesheet
        assert "QMenuBar#mobaTopMenuBar" in preset.stylesheet
        assert "QMenuBar#secureCrtMenuBar" in preset.stylesheet
        assert "QMenuBar#mRemoteNgMenuBar" in preset.stylesheet
        assert "QToolBar#mainToolbar" in preset.stylesheet
        assert "QToolBar#layoutToolbar" in preset.stylesheet
        assert "QTabWidget#sessionTabs" in preset.stylesheet
        assert "QTreeWidget#profileTree" in preset.stylesheet
        assert "QPushButton#primaryAction" in preset.stylesheet
        assert "QTextEdit#activityLog" in preset.stylesheet
        assert "QWidget#terminalPane" in preset.stylesheet
        assert "QFrame#terminalHeader" in preset.stylesheet
        assert "QToolButton#terminalAction" in preset.stylesheet
        assert "QDialog#workflowDialog" in preset.stylesheet
        assert "QTreeWidget#workflowRows" in preset.stylesheet
        assert "QToolButton#workflowAction" in preset.stylesheet
        assert "QFrame#productWorkflowEvidence" in preset.stylesheet
        assert "QLabel#productWorkflowTitle" in preset.stylesheet
        assert "QFrame#productWorkspaceSurface" in preset.stylesheet
        assert "QFrame#productReferenceState" in preset.stylesheet
        assert "QLabel#productReferenceStateItem" in preset.stylesheet
        assert "QFrame#secureCrtCommandWindow" in preset.stylesheet
        assert "QFrame#secureCrtSessionManagerChrome" in preset.stylesheet
        assert "QLineEdit#secureCrtSessionFilter" in preset.stylesheet
        assert "QToolButton#secureCrtSessionManagerAction" in preset.stylesheet
        assert "QFrame#secureCrtSessionStatusStrip" in preset.stylesheet
        assert "QLabel#secureCrtSessionStatusCell" in preset.stylesheet
        assert "QLabel#secureCrtCommandInput" in preset.stylesheet
        assert "QFrame#remminaViewerControls" in preset.stylesheet
        assert "QToolButton#remminaViewerControl" in preset.stylesheet
        assert "QFrame#remminaProfileListChrome" in preset.stylesheet
        assert "QLabel#remminaProfileListCell" in preset.stylesheet
        assert "QFrame#termiusHeaderChips" in preset.stylesheet
        assert "QLabel#termiusHeaderChip" in preset.stylesheet
        assert "QFrame#termiusHostsChrome" in preset.stylesheet
        assert "QLineEdit#termiusHostSearch" in preset.stylesheet
        assert "QToolButton#termiusHostsAction" in preset.stylesheet
        assert "QFrame#termiusHostIdentityStrip" in preset.stylesheet
        assert "QLabel#termiusHostIdentityCell" in preset.stylesheet
        assert "QFrame#mRemoteNgDocumentControls" in preset.stylesheet
        assert "QToolButton#mRemoteNgDocumentControl" in preset.stylesheet
        assert "QFrame#mRemoteNgPropertyGrid" in preset.stylesheet
        assert "QLabel#mRemoteNgPropertyGridCell" in preset.stylesheet
        assert "QFrame#mobaMonitoringControls" in preset.stylesheet
        assert "QToolButton#mobaMonitoringControl" in preset.stylesheet
        assert "QCheckBox#mobaFollowTerminalFolder" in preset.stylesheet
        assert "QLabel#mobaRailLabel" in preset.stylesheet
        assert "QFrame#mobaQuickConnectChrome" in preset.stylesheet
        assert "QLabel#mobaQuickConnectDropdown" in preset.stylesheet
        assert "QFrame#mobaRightUtilityRail" in preset.stylesheet
        assert "QToolButton#mobaRightUtilityAction" in preset.stylesheet
        assert "QFrame#mobaSessionEdgeControls" in preset.stylesheet
        assert "QToolButton#mobaSessionEdgeAction" in preset.stylesheet
        assert "QLabel#mobaSshBannerTitle" in preset.stylesheet
        assert "QLabel#mobaSshBannerSubtitle" in preset.stylesheet
        assert "QLabel#mobaSshBannerTargetLine" in preset.stylesheet
        assert "QLabel#mobaSshBannerCapability" in preset.stylesheet
        assert "QLabel#mobaSshBannerFooter" in preset.stylesheet
        assert "QStatusBar QLabel#productStatusNotice" in preset.stylesheet
        assert "QStatusBar QLabel#productStatusMarker" in preset.stylesheet
        assert "QFrame#mobaBottomEdgeControls" in preset.stylesheet
        assert "QToolButton#mobaBottomEdgeControl" in preset.stylesheet
        assert "QFrame#productWorkspacePrimaryPane" in preset.stylesheet
        assert "QLabel#productWorkspaceTitle" in preset.stylesheet
        assert "QSplitter::handle" in preset.stylesheet


def test_gui_design_presets_are_not_only_recolored_clones() -> None:
    signatures = {
        (
            preset.profile_width,
            preset.log_height,
            preset.tab_position,
            preset.density,
            preset.toolbar_icon_size,
            preset.colors.window,
            preset.colors.primary,
            preset.colors.terminal,
        )
        for preset in GUI_DESIGN_PRESETS
    }
    assert len(signatures) == len(GUI_DESIGN_PRESETS)


def test_mobaxterm_ribbon_actions_are_shared_metadata() -> None:
    actions = gui_design_moba_ribbon_actions()

    assert [action.label for action in actions[:5]] == ["Session", "Servers", "Tools", "Games", "Sessions"]
    assert [action.icon_key for action in actions] == [
        "session",
        "servers",
        "tools",
        "games",
        "sessions",
        "view",
        "split",
        "multiexec",
        "tunneling",
        "packages",
        "settings",
        "help",
    ]
    assert all(action.color.startswith("#") for action in actions)


def test_mobaxterm_top_menu_items_are_shared_metadata() -> None:
    items = gui_design_moba_top_menu_items()

    assert [item.key for item in items] == [
        "terminal",
        "sessions",
        "view",
        "x-server",
        "tools",
        "games",
        "settings",
        "macros",
        "help",
    ]
    assert [item.label for item in items] == [
        "Terminal",
        "Sessions",
        "View",
        "X server",
        "Tools",
        "Games",
        "Settings",
        "Macros",
        "Help",
    ]
    assert items[0].primary_action == "Start local terminal"
    assert items[-1].primary_action == "Run doctor"
    assert all(item.tooltip for item in items)


def test_mobaxterm_titlebar_chrome_is_shared_metadata() -> None:
    chrome = gui_design_moba_titlebar_chrome()

    assert chrome.icon_key == "moba-window"
    assert chrome.static_height == 22
    assert chrome.icon_left == 5
    assert chrome.icon_size == 12
    assert chrome.title_left == 24
    assert chrome.control_keys == ("minimize", "maximize", "close")
    assert chrome.control_width == 24


def test_mobaxterm_quick_connect_chrome_is_shared_metadata() -> None:
    chrome = gui_design_moba_quick_connect_chrome()

    assert chrome.placeholder == "Quick connect..."
    assert chrome.dropdown_marker == "v"
    assert chrome.static_height == 24
    assert chrome.marker_width == 24
    assert chrome.input_left == 0
    assert chrome.input_padding == "4px 8px"
    assert chrome.connected_idle_query == ""
    assert chrome.connected_suggestions_visible is False


def test_mobaxterm_quick_connect_suggestion_chrome_is_shared_metadata() -> None:
    chrome = gui_design_moba_quick_connect_suggestion_chrome()

    assert chrome.preview_query == "edge-prod.example.invalid"
    assert chrome.expected_kinds == ("profile", "direct")
    assert chrome.max_visible_rows == 4
    assert chrome.row_height == 22
    assert chrome.static_width == 390
    assert chrome.detail_separator == "    "


def test_mobaxterm_home_welcome_chrome_is_shared_metadata() -> None:
    chrome = gui_design_moba_home_welcome_chrome()

    assert chrome.title == "Remote Ops Workspace"
    assert chrome.subtitle == "Moba-style SSH client, SFTP browser and monitoring tools"
    assert chrome.icon_key == "session"
    assert chrome.primary_action_icon_key == "session"
    assert chrome.secondary_action_icon_key == "tunneling"
    assert chrome.search_width == 405
    assert chrome.action_spacing == 96
    assert chrome.recent_title == "Recent sessions"
    assert chrome.surface_width == 640


def test_mobaxterm_rail_items_include_vertical_reference_labels() -> None:
    items = gui_design_moba_rail_items()

    assert [item.role for item in items] == ["collapse", "sessions", "favorites", "tools", "macros", "sftp"]
    assert {item.role: item.label for item in items if item.label} == {
        "sessions": "Sessions",
        "tools": "Tools",
        "macros": "Macros",
        "sftp": "SFTP",
    }
    assert all(item.icon_key for item in items)
    assert all(item.color.startswith("#") for item in items)


def test_mobaxterm_connected_interaction_state_checks_sftp_rail() -> None:
    state = gui_design_interaction_state("mobaxterm")

    assert state.focused_control == "quick-connect"
    assert state.checked_toolbar_key == "sftp"
    assert "SFTP rail checked" in state.status_note


def test_mobaxterm_right_utility_actions_are_shared_metadata() -> None:
    actions = gui_design_moba_right_utility_actions()

    assert [action.key for action in actions] == ["clip", "settings", "tools"]
    assert [action.icon_key for action in actions] == ["clip", "gear", "spark"]
    assert [action.label for action in actions] == [
        "Clipboard and transfer hints",
        "Terminal settings",
        "Terminal tools",
    ]
    assert all(action.tooltip for action in actions)
    assert all(action.color.startswith("#") for action in actions)


def test_mobaxterm_session_edge_actions_are_shared_metadata() -> None:
    actions = gui_design_moba_session_edge_actions()

    assert [action.key for action in actions] == ["attachment", "settings"]
    assert [action.icon_key for action in actions] == ["clip", "gear"]
    assert [action.label for action in actions] == ["Session attachment", "Session settings"]
    assert [action.static_y for action in actions] == [112, 130]
    assert all(action.tooltip for action in actions)
    assert all(action.color.startswith("#") for action in actions)


def test_mobaxterm_sftp_dock_actions_are_shared_metadata() -> None:
    actions = gui_design_moba_sftp_dock_actions()

    assert [action.key for action in actions] == [
        "parent-folder",
        "download",
        "upload",
        "connect",
        "new-folder",
        "new-file",
        "delete",
        "ascii-mode",
        "split-view",
        "tools",
        "terminal",
    ]
    assert all(action.icon_key for action in actions)
    assert all(action.tooltip for action in actions)
    assert all(action.color.startswith("#") for action in actions)
    assert [action.group_key for action in actions] == [
        "navigation",
        "transfer",
        "transfer",
        "manage",
        "manage",
        "manage",
        "manage",
        "mode",
        "mode",
        "mode",
        "terminal",
    ]
    assert [action.key for action in actions if action.separator_after] == [
        "parent-folder",
        "upload",
        "delete",
        "tools",
    ]


def test_mobaxterm_sftp_browser_chrome_is_shared_metadata() -> None:
    chrome = gui_design_moba_sftp_browser_chrome()

    assert chrome.path_placeholder == "/"
    assert chrome.dropdown_marker == "v"
    assert chrome.parent_row_label == ".."
    assert chrome.parent_row_kind == "parent-dir"
    assert chrome.selected_row_kind == "parent-dir"
    assert [column.key for column in chrome.columns] == ["name", "size", "modified"]
    assert [column.label for column in chrome.columns] == ["Name", "Size (KB)", "Last modified"]
    assert [column.static_x for column in chrome.columns] == [38, 188, 266]


def test_mobaxterm_sftp_dock_layout_is_shared_density_metadata() -> None:
    layout = gui_design_moba_sftp_dock_layout()

    assert layout.inner_margin == 6
    assert layout.toolbar_height == 26
    assert layout.toolbar_icon_size == 16
    assert layout.toolbar_icon_step == 24
    assert layout.toolbar_separator_width == 7
    assert layout.path_height == 24
    assert layout.table_header_height == 24
    assert layout.file_row_height == 21
    assert layout.static_max_rows == 9
    assert layout.monitoring_height == 116
    assert layout.monitoring_divider_offset == 14


def test_mobaxterm_monitoring_metrics_are_shared_metadata() -> None:
    metrics = gui_design_moba_monitoring_metrics()

    assert [metric.key for metric in metrics] == ["cpu", "memory", "disk", "network", "load", "processes"]
    assert [metric.label for metric in metrics[:4]] == ["CPU", "RAM", "Disk", "Net"]
    assert all(metric.source for metric in metrics)


def test_mobaxterm_monitoring_controls_are_shared_metadata() -> None:
    controls = gui_design_moba_monitoring_controls()

    assert [control.key for control in controls] == ["remote-monitoring", "follow-terminal-folder"]
    assert [control.icon_key for control in controls] == ["monitor", "follow-folder"]
    assert [control.label for control in controls] == ["Remote monitoring", "Follow terminal folder"]
    assert [control.control_type for control in controls] == ["toggle", "checkbox"]
    assert [control.checked for control in controls] == [True, True]
    assert all(control.tooltip for control in controls)


def test_mobaxterm_remote_monitoring_dock_chrome_is_compact_shared_metadata() -> None:
    chrome = gui_design_moba_remote_monitoring_dock_chrome()

    assert chrome.title_control_key == "remote-monitoring"
    assert chrome.follow_control_key == "follow-terminal-folder"
    assert chrome.telemetry_surface == "bottom-telemetry-bar"
    assert chrome.visible_metric_keys == ()
    assert chrome.refresh_seconds == 5
    assert chrome.compact is True


def test_mobaxterm_status_bar_chrome_is_shared_metadata() -> None:
    chrome = gui_design_moba_status_bar_chrome()
    segments = gui_design_moba_status_segments()

    assert chrome.notice == "REMOTE OPS WORKSPACE"
    assert chrome.product_note == "open-protocol operator shell"
    assert chrome.right_marker == "[]"
    assert [segment.key for segment in segments] == ["sftp-ready", "cpu-monitor", "ssh-browser"]
    assert [segment.text for segment in segments] == ["SFTP ready", "CPU monitor", "SSH browser"]
    assert all(segment.tooltip for segment in segments)


def test_mobaxterm_bottom_edge_controls_are_shared_metadata() -> None:
    controls = gui_design_moba_bottom_edge_controls()

    assert [control.key for control in controls] == ["tab-left", "tab-right", "close-active"]
    assert [control.icon_key for control in controls] == ["arrow-left", "arrow-right", "close"]
    assert [control.label for control in controls] == ["Previous tab", "Next tab", "Close active tab"]
    assert [control.static_x for control in controls] == [1204, 1224, 1244]
    assert all(control.tooltip for control in controls)
    assert all(control.color.startswith("#") for control in controls)


def test_mobaxterm_ssh_banner_chrome_is_shared_metadata() -> None:
    chrome = gui_design_moba_ssh_banner_chrome()

    assert chrome.title == "Remote Ops Workspace Personal Edition v1.0"
    assert chrome.subtitle == "(SSH client, SFTP browser and remote tools)"
    assert chrome.heading_prefix == "* "
    assert chrome.heading_suffix == " *"
    assert chrome.target_intro == "SSH session to"
    assert chrome.capability_label_width == 15
    assert chrome.footer_prefix == "For more info, ctrl+click on"
    assert chrome.help_link_label == "help"
    assert chrome.website_link_label == "website"
    assert chrome.static_left_offset == 42
    assert chrome.static_top_offset == 12
    assert chrome.static_width == 570
    assert chrome.static_height == 166
    assert chrome.body_top_offset < chrome.static_height
    assert chrome.terminal_gap > 0


def test_securecrt_command_window_chrome_is_shared_metadata() -> None:
    chrome = gui_design_securecrt_command_window_chrome()

    assert chrome.key == "send-to-all-sessions"
    assert chrome.title == "Command Window"
    assert chrome.helper == "send command to active tab or all sessions"
    assert chrome.target_scope == "All Sessions"
    assert chrome.command == "$ row doctor --json"
    assert chrome.send_label == "Send"
    assert chrome.status == "ready"


def test_securecrt_session_status_strip_is_shared_metadata() -> None:
    strip = gui_design_securecrt_session_status_strip()

    assert strip.title == "Session status"
    assert [field.key for field in strip.fields] == [
        "session",
        "target",
        "protocol",
        "cipher",
        "sftp",
        "log",
        "state",
    ]
    assert [field.label for field in strip.fields] == [
        "Session",
        "Target",
        "Protocol",
        "Cipher",
        "SFTP",
        "Log",
        "State",
    ]
    assert strip.fields[1].value == "edge-prod.example.invalid:22"
    assert strip.fields[3].value == "chacha20-poly1305"
    assert strip.fields[-1].value == "connected"
    assert [field.static_width for field in strip.fields] == [132, 174, 102, 122, 102, 90, 82]
    assert all(field.tooltip for field in strip.fields)


def test_securecrt_session_manager_chrome_is_shared_metadata() -> None:
    chrome = gui_design_securecrt_session_manager_chrome()

    assert chrome.title == "Session Manager"
    assert chrome.filter_placeholder == "Filter sessions"
    assert [action.key for action in chrome.actions] == ["connect", "new-folder", "properties"]
    assert [action.icon_key for action in chrome.actions] == ["connect", "folder", "properties"]
    assert [action.label for action in chrome.actions] == ["Connect", "New Folder", "Properties"]
    assert [action.static_x for action in chrome.actions] == [34, 60, 86]
    assert all(action.tooltip for action in chrome.actions)


def test_securecrt_top_chrome_is_shared_metadata() -> None:
    chrome = gui_design_securecrt_top_chrome()

    assert chrome.window_title == "edge-prod (SSH2) - Remote Ops Workspace"
    assert chrome.menu_height == 22
    assert chrome.toolbar_height == 54
    assert [item.key for item in chrome.menu_items] == [
        "file",
        "edit",
        "view",
        "options",
        "transfer",
        "script",
        "tools",
        "window",
        "help",
    ]
    assert [item.label for item in chrome.menu_items] == [
        "File",
        "Edit",
        "View",
        "Options",
        "Transfer",
        "Script",
        "Tools",
        "Window",
        "Help",
    ]
    assert [action.key for action in chrome.toolbar_actions] == [
        "refresh",
        "new",
        "edit",
        "remove",
        "connect",
        "files",
        "queue",
        "dry-run",
        "doctor",
        "split-h",
        "split-v",
    ]
    assert [action.icon_key for action in chrome.toolbar_actions[:5]] == [
        "session-manager",
        "new-session",
        "properties",
        "delete",
        "connect",
    ]
    assert [action.static_x for action in chrome.toolbar_actions[:4]] == [14, 82, 180, 272]
    assert all(action.static_width >= 54 for action in chrome.toolbar_actions)
    assert all(item.primary_action for item in chrome.menu_items)
    assert all(action.tooltip for action in chrome.toolbar_actions)


def test_remmina_viewer_controls_are_shared_metadata() -> None:
    controls = gui_design_remmina_viewer_controls()

    assert [control.key for control in controls] == [
        "fit",
        "scale-100",
        "clipboard",
        "fullscreen",
        "screenshot",
    ]
    assert [control.icon_key for control in controls] == [
        "fit",
        "scale",
        "clipboard",
        "fullscreen",
        "screenshot",
    ]
    assert [control.label for control in controls] == [
        "Fit",
        "Scale 100%",
        "Clipboard",
        "Fullscreen",
        "Screenshot",
    ]
    assert all(control.standard_icon.startswith("SP_") for control in controls)
    assert all(control.tooltip for control in controls)


def test_remmina_profile_list_chrome_is_shared_metadata() -> None:
    chrome = gui_design_remmina_profile_list_chrome()

    assert chrome.title == "Connection list"
    assert chrome.filter_placeholder == "Filter by name or protocol"
    assert [column.key for column in chrome.columns] == ["name", "protocol", "server"]
    assert [column.label for column in chrome.columns] == ["Name", "Protocol", "Server"]
    assert [column.static_width for column in chrome.columns] == [98, 58, 104]
    assert [row.key for row in chrome.rows] == ["win-admin", "linux-console", "sftp-ops"]
    assert [row.protocol for row in chrome.rows] == ["RDP", "VNC", "SFTP"]
    assert chrome.rows[0].selected is True
    assert chrome.rows[0].server == "admin-win.example.invalid"
    assert chrome.rows[-1].status == "file sharing"


def test_termius_header_chips_are_shared_metadata() -> None:
    chips = gui_design_termius_header_chips()

    assert [chip.key for chip in chips] == ["vault-unlocked", "sync-current", "port-forward-ready"]
    assert [chip.label for chip in chips] == ["Vault unlocked", "Sync current", "Port fwd ready"]
    assert all(chip.tooltip for chip in chips)


def test_termius_hosts_chrome_is_shared_metadata() -> None:
    chrome = gui_design_termius_hosts_chrome()

    assert chrome.title == "Hosts"
    assert chrome.filter_placeholder == "Search hosts"
    assert [action.key for action in chrome.actions] == ["new-host", "keychain", "sync-hosts"]
    assert [action.icon_key for action in chrome.actions] == ["plus", "key", "sync"]
    assert [action.label for action in chrome.actions] == ["Add Host", "Keychain", "Sync"]
    assert [action.static_x for action in chrome.actions] == [34, 60, 86]
    assert all(action.tooltip for action in chrome.actions)


def test_termius_host_identity_strip_is_shared_metadata() -> None:
    strip = gui_design_termius_host_identity_strip()

    assert strip.title == "Host identity"
    assert [field.key for field in strip.fields] == [
        "host",
        "identity",
        "chain",
        "files",
        "forward",
        "snippet",
        "sync",
    ]
    assert [field.value for field in strip.fields] == [
        "edge-prod",
        "prod-ed25519",
        "direct",
        "SFTP ready",
        "8080 -> localhost:80",
        "row vault status",
        "current",
    ]
    assert [field.static_width for field in strip.fields] == [92, 112, 82, 92, 132, 122, 82]
    assert all(field.tooltip for field in strip.fields)


def test_mremoteng_document_controls_are_shared_metadata() -> None:
    chrome = gui_design_mremoteng_document_toolbar_chrome()
    controls = gui_design_mremoteng_document_controls()

    assert chrome.title == "Connections.xml"
    assert chrome.filter_placeholder == "Filter connection tree"
    assert [control.key for control in controls] == ["save", "reconnect", "external-tool", "dock-view"]
    assert [control.icon_key for control in controls] == ["database", "ssh", "external", "rdp"]
    assert [control.label for control in controls] == ["Save", "Reconnect", "External tool", "Dock view"]
    assert all(control.standard_icon.startswith("SP_") for control in controls)
    assert all(control.tooltip for control in controls)
    assert [control.static_width for control in controls] == [56, 88, 104, 84]


def test_mremoteng_top_chrome_is_shared_metadata() -> None:
    chrome = gui_design_mremoteng_top_chrome()

    assert chrome.window_title == "Connections.xml - Remote Ops Workspace"
    assert chrome.menu_height == 22
    assert chrome.toolbar_height == 50
    assert [item.key for item in chrome.menu_items] == [
        "file",
        "view",
        "connections",
        "tools",
        "window",
        "help",
    ]
    assert [item.label for item in chrome.menu_items] == [
        "File",
        "View",
        "Connections",
        "Tools",
        "Window",
        "Help",
    ]
    assert [action.key for action in chrome.toolbar_actions] == [
        "refresh",
        "new",
        "edit",
        "remove",
        "connect",
        "files",
        "queue",
        "dry-run",
        "doctor",
        "split-h",
        "split-v",
    ]
    assert [action.icon_key for action in chrome.toolbar_actions[:6]] == [
        "refresh-tree",
        "new-connection",
        "config",
        "delete",
        "open-connection",
        "external-tool",
    ]
    assert [action.label for action in chrome.toolbar_actions[:6]] == [
        "Refresh",
        "New Conn",
        "Config",
        "Delete",
        "Open",
        "External",
    ]
    assert [action.static_width for action in chrome.toolbar_actions] == [58, 74, 62, 58, 54, 74, 70, 58, 54, 58, 58]
    assert all(item.tooltip for item in chrome.menu_items)
    assert all(action.tooltip for action in chrome.toolbar_actions)


def test_mremoteng_property_grid_is_shared_metadata() -> None:
    chrome = gui_design_mremoteng_property_grid_chrome()

    assert chrome.title == "Config / Inheritance"
    assert chrome.scope_label == "edge-prod [SSH]"
    assert chrome.inheritance_label == "inherited"
    assert [column.key for column in chrome.columns] == ["property", "inherited", "effective", "source"]
    assert [column.label for column in chrome.columns] == ["Property", "Inherited", "Effective value", "Source"]
    assert [column.static_width for column in chrome.columns] == [155, 150, 270, 245]
    assert [row.key for row in chrome.rows] == ["protocol", "hostname", "credential", "external", "inheritance"]
    assert [row.inherited for row in chrome.rows] == [True, False, True, True, False]
    assert chrome.rows[1].effective_value == "edge-prod.example.invalid"
    assert chrome.rows[2].source == "Connections.xml/prod"


def test_gui_design_workflow_cards_are_shared_metadata() -> None:
    for preset in GUI_DESIGN_PRESETS:
        cards = gui_design_workflow_cards(preset.id)
        assert len(cards) == 3
        assert all(card.key for card in cards)
        assert all(card.title for card in cards)
        assert all(card.primary for card in cards)
        assert all(card.secondary for card in cards)

    assert [card.title for card in gui_design_workflow_cards("securecrt")] == [
        "Command Window",
        "Session Manager",
        "SFTP tab",
    ]
    assert [card.title for card in gui_design_workflow_cards("termius")] == [
        "Vault identity",
        "Port forward",
        "Snippet",
    ]


def test_gui_design_reference_states_are_shared_metadata() -> None:
    expected = {
        "securecrt": ("edge-prod", "SSH2 + SFTP", "edge-prod (SSH2)", "Session Manager"),
        "termius": ("edge-prod", "SSH + Vault", "edge-prod", "Hosts"),
        "remmina": ("win-admin", "RDP viewer", "RDP - win-admin", "Connection Profiles"),
        "mremoteng": ("edge-prod", "SSH document", "edge-prod [SSH]", "Connections"),
    }
    for preset_id, (profile, protocol, tab, sidebar) in expected.items():
        reference = gui_design_reference_state(preset_id)

        assert reference.profile_name == profile
        assert reference.protocol_label == protocol
        assert reference.active_tab_label == tab
        assert reference.sidebar_label == sidebar
        assert reference.status_segments
        assert {key for key, _value in reference.items()} == {
            "profile",
            "target",
            "protocol",
            "active-tab",
            "sidebar",
            "state",
        }


def test_gui_design_styles_avoid_fragile_decoration_patterns() -> None:
    for preset in GUI_DESIGN_PRESETS:
        stylesheet = preset.stylesheet.lower()
        assert "gradient" not in stylesheet
        assert "letter-spacing" not in stylesheet
        assert "border-radius: 9" not in stylesheet
        assert "border-radius: 10" not in stylesheet


def test_get_gui_design_preset_rejects_unknown_id() -> None:
    assert get_gui_design_preset("termius").label == "Termius-style"
    try:
        get_gui_design_preset("unknown")
    except ValueError as exc:
        assert "unknown GUI design preset" in str(exc)
    else:
        raise AssertionError("unknown GUI design preset should be rejected")

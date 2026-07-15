from remote_ops_workspace.gui_designs import (
    DEFAULT_GUI_DESIGN_ID,
    GUI_DESIGN_PRESETS,
    PRODUCT_GUI_PRESET_IDS,
    PRODUCT_REFERENCE_TAB_PRESET_IDS,
    get_gui_design_preset,
    gui_design_command_surface_actions,
    gui_design_home_tab_label,
    gui_design_interaction_state,
    gui_design_moba_bottom_edge_controls,
    gui_design_moba_connected_dock_frame,
    gui_design_moba_follow_terminal_folder_control_route,
    gui_design_moba_home_welcome_chrome,
    gui_design_moba_home_welcome_geometry,
    gui_design_moba_monitoring_control_geometry,
    gui_design_moba_monitoring_controls,
    gui_design_moba_monitoring_metrics,
    gui_design_moba_monitoring_telemetry_route,
    gui_design_moba_quick_connect_chrome,
    gui_design_moba_quick_connect_suggestion_chrome,
    gui_design_moba_rail_chrome,
    gui_design_moba_rail_item_geometry,
    gui_design_moba_rail_items,
    gui_design_moba_remote_monitoring_control_route,
    gui_design_moba_remote_monitoring_dock_chrome,
    gui_design_moba_ribbon_action_geometry,
    gui_design_moba_ribbon_action_geometry_for,
    gui_design_moba_ribbon_actions,
    gui_design_moba_ribbon_edge_action_route,
    gui_design_moba_ribbon_edge_actions,
    gui_design_moba_ribbon_tooltips,
    gui_design_moba_right_utility_action_route,
    gui_design_moba_right_utility_actions,
    gui_design_moba_right_utility_rail_chrome,
    gui_design_moba_session_edge_action_route,
    gui_design_moba_session_edge_actions,
    gui_design_moba_session_tree_chrome,
    gui_design_moba_sftp_browser_chrome,
    gui_design_moba_sftp_dock_actions,
    gui_design_moba_sftp_dock_layout,
    gui_design_moba_sftp_file_row_icon,
    gui_design_moba_sftp_file_row_icons,
    gui_design_moba_sftp_follow_folder_route,
    gui_design_moba_sftp_routed_file_rows,
    gui_design_moba_sftp_toolbar_action_geometry,
    gui_design_moba_sftp_toolbar_action_geometry_for,
    gui_design_moba_sftp_toolbar_action_route,
    gui_design_moba_ssh_banner_chrome,
    gui_design_moba_ssh_banner_row_geometry,
    gui_design_moba_ssh_banner_row_geometry_for,
    gui_design_moba_status_bar_chrome,
    gui_design_moba_status_segments,
    gui_design_moba_terminal_transcript_row_geometry,
    gui_design_moba_terminal_transcript_row_geometry_for,
    gui_design_moba_titlebar_chrome,
    gui_design_moba_top_menu_geometry,
    gui_design_moba_top_menu_geometry_for,
    gui_design_moba_top_menu_items,
    gui_design_moba_top_stack_geometry,
    gui_design_mremoteng_connection_document_route,
    gui_design_mremoteng_document_controls,
    gui_design_mremoteng_document_filter_route,
    gui_design_mremoteng_document_toolbar_chrome,
    gui_design_mremoteng_inheritance_route,
    gui_design_mremoteng_property_grid_chrome,
    gui_design_mremoteng_top_chrome,
    gui_design_preset_catalog_route,
    gui_design_preset_command_surface_route,
    gui_design_preset_focus_interaction_route,
    gui_design_preset_home_search_route,
    gui_design_preset_ids,
    gui_design_preset_isolation_route,
    gui_design_preset_keyboard_shortcut_route,
    gui_design_preset_labels,
    gui_design_preset_reference_control_route,
    gui_design_preset_reference_input_route,
    gui_design_preset_reference_session_action_route,
    gui_design_preset_reference_status_bar_route,
    gui_design_preset_reference_surface_route,
    gui_design_preset_reference_tab_chrome_route,
    gui_design_preset_reference_tab_route,
    gui_design_preset_reference_transcript_route,
    gui_design_preset_selection_route,
    gui_design_preset_transition_route,
    gui_design_preset_visual_signature,
    gui_design_product_identity_route,
    gui_design_reference_state,
    gui_design_remmina_clipboard_route,
    gui_design_remmina_profile_filter_route,
    gui_design_remmina_profile_list_chrome,
    gui_design_remmina_profile_viewer_route,
    gui_design_remmina_screenshot_route,
    gui_design_remmina_sftp_transfer_route,
    gui_design_remmina_viewer_controls,
    gui_design_securecrt_command_window_chrome,
    gui_design_securecrt_command_window_send_route,
    gui_design_securecrt_session_manager_chrome,
    gui_design_securecrt_session_manager_filter_route,
    gui_design_securecrt_session_manager_route,
    gui_design_securecrt_session_status_strip,
    gui_design_securecrt_sftp_browser_route,
    gui_design_securecrt_sftp_tab_route,
    gui_design_securecrt_top_chrome,
    gui_design_status_segments,
    gui_design_tab_items,
    gui_design_termius_files_browser_route,
    gui_design_termius_header_chips,
    gui_design_termius_host_identity_strip,
    gui_design_termius_host_selection_route,
    gui_design_termius_hosts_chrome,
    gui_design_termius_port_forward_route,
    gui_design_termius_snippet_route,
    gui_design_termius_sync_route,
    gui_design_toolbar_actions,
    gui_design_tree_root_icon,
    gui_design_tree_row_icon,
    gui_design_tree_row_icons,
    gui_design_tree_rows,
    gui_design_workflow_cards,
    gui_design_workspace_surface,
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
        assert "QComboBox QAbstractItemView" in preset.stylesheet
        assert "QScrollArea#profileFormScroll" in preset.stylesheet
        assert "QWidget#profileFormBody" in preset.stylesheet
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


def test_gui_design_product_toolbar_actions_have_complete_unique_stable_keys() -> None:
    expected = (
        "refresh",
        "new",
        "import",
        "edit",
        "remove",
        "connect",
        "files",
        "queue",
        "dry-run",
        "doctor",
        "split-h",
        "split-v",
    )

    for preset_id in ("native", "securecrt", "termius", "remmina", "mremoteng"):
        actions = gui_design_toolbar_actions(preset_id)
        keys = tuple(key for key, _label, _tooltip in actions)
        assert keys == expected
        assert len(keys) == len(set(keys))
        assert all(label and tooltip for _key, label, tooltip in actions)


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
    edge_actions = gui_design_moba_ribbon_edge_actions()

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
    assert [action.label for action in edge_actions] == ["X server", "Exit"]
    assert [action.icon_key for action in edge_actions] == ["xserver", "exit"]
    assert all(action.color.startswith("#") for action in actions)
    assert all(action.color.startswith("#") for action in edge_actions)


def test_mobaxterm_ribbon_edge_action_route_is_shared_metadata() -> None:
    route = gui_design_moba_ribbon_edge_action_route()
    edge_actions = {action.key: action for action in gui_design_moba_ribbon_edge_actions()}

    assert route.key == "moba-ribbon-edge-action-route"
    assert route.route_role == "far-right-ribbon-edge-actions-to-workflow-controls"
    assert route.toolbar_object == "mainToolbar"
    assert route.spacer_object == "mobaToolbarSpacer"
    assert route.xserver_action_key == "xserver"
    assert route.xserver_action_label == edge_actions["xserver"].label == "X server"
    assert route.xserver_action_object == "mobaXServerAction"
    assert route.xserver_icon_key == edge_actions["xserver"].icon_key == "xserver"
    assert route.xserver_handler == "show_moba_x_server_status"
    assert route.xserver_dialog_detail == "X server workflow"
    assert route.exit_action_key == "exit"
    assert route.exit_action_label == edge_actions["exit"].label == "Exit"
    assert route.exit_action_object == "mobaExitAction"
    assert route.exit_icon_key == edge_actions["exit"].icon_key == "exit"
    assert route.exit_handler == "close"
    assert route.route_key_property == "mobaRibbonEdgeRouteKey"
    assert route.action_keys_property == "mobaRibbonEdgeRouteActionKeys"
    assert route.handler_property == "mobaRibbonEdgeRouteHandler"
    assert route.to_dict()["xserver_action_label"] == "X server"
    assert route.to_dict()["exit_action_label"] == "Exit"


def test_mobaxterm_ribbon_action_geometry_tracks_reference_offsets() -> None:
    geometry = gui_design_moba_ribbon_action_geometry()

    assert [item.key for item in geometry] == [
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
        "xserver",
        "exit",
    ]
    assert [item.static_x for item in geometry] == [12, 73, 134, 192, 250, 318, 376, 434, 509, 584, 652, 720, 1152, 1230]
    assert [item.width for item in geometry] == [61, 61, 58, 58, 68, 58, 58, 75, 75, 68, 68, 58, 70, 42]
    assert [item.separator_x for item in geometry if item.separator_before] == [67, 244, 428, 646, 1140]
    assert {item.icon_y for item in geometry[:12]} == {6}
    assert {item.icon_size for item in geometry[:12]} == {24}
    assert {item.label_y for item in geometry[:12]} == {40}
    assert {item.label_font_size for item in geometry} == {10}
    assert {item.separator_top for item in geometry} == {7}
    assert {item.separator_bottom for item in geometry} == {56}
    assert gui_design_moba_ribbon_action_geometry_for("xserver").icon_size == 28
    assert gui_design_moba_ribbon_action_geometry_for("exit").icon_x == 1232


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


def test_mobaxterm_top_menu_geometry_tracks_reference_offsets() -> None:
    geometry = gui_design_moba_top_menu_geometry()

    assert [item.key for item in geometry] == [
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
    assert [item.static_x for item in geometry] == [8, 82, 156, 202, 276, 329, 382, 456, 516]
    assert [item.width for item in geometry] == [74, 74, 46, 74, 53, 53, 74, 60, 46]
    assert {item.label_y for item in geometry} == {5}
    assert {item.label_font_size for item in geometry} == {11}
    assert {item.gap_after for item in geometry} == {18}
    assert gui_design_moba_top_menu_geometry_for("x-server").static_x == 202


def test_mobaxterm_titlebar_chrome_is_shared_metadata() -> None:
    chrome = gui_design_moba_titlebar_chrome()

    assert chrome.icon_key == "moba-window"
    assert chrome.static_height == 22
    assert chrome.icon_left == 5
    assert chrome.icon_size == 12
    assert chrome.title_left == 24
    assert chrome.control_keys == ("minimize", "maximize", "close")
    assert chrome.control_width == 24


def test_mobaxterm_top_stack_geometry_is_shared_metadata() -> None:
    stack = gui_design_moba_top_stack_geometry()

    assert stack.titlebar_height == gui_design_moba_titlebar_chrome().static_height
    assert stack.menu_y == 22
    assert stack.menu_height == 22
    assert stack.ribbon_y == 44
    assert stack.ribbon_height == 64
    assert stack.quick_connect_y == 108
    assert stack.quick_connect_height == gui_design_moba_quick_connect_chrome().static_height
    assert stack.left_dock_y == 132
    assert stack.tab_y == 108
    assert stack.tab_height == 28
    assert stack.terminal_content_y == 136
    assert stack.status_height == 22
    assert stack.side_width == 390
    assert stack.rail_width == 24


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
    assert chrome.action_spacing == 62
    assert chrome.recent_title == "Recent sessions"
    assert chrome.surface_width == 640


def test_mobaxterm_home_welcome_geometry_is_shared_metadata() -> None:
    chrome = gui_design_moba_home_welcome_chrome()
    geometry = gui_design_moba_home_welcome_geometry()

    assert geometry.center_side_margin == 80
    assert geometry.hero_min_y == 115
    assert geometry.hero_height == 330
    assert geometry.logo_size == 46
    assert geometry.logo_inner_padding == 7
    assert geometry.logo_icon_size == 32
    assert geometry.logo_cluster_width == 360
    assert geometry.title_gap == 28
    assert geometry.title_y_offset == 9
    assert geometry.title_font_size == 28
    assert geometry.subtitle_y_offset == 57
    assert geometry.subtitle_font_size == 12
    assert geometry.button_y_offset == 94
    assert geometry.primary_width == 206
    assert geometry.secondary_width == 220
    assert geometry.action_gap == chrome.action_spacing == 62
    assert geometry.button_height == 28
    assert geometry.search_y_gap == 45
    assert geometry.search_height == 25
    assert geometry.recent_y_gap == 52
    assert geometry.recent_item_step == 22
    assert geometry.footer_y_offset == 120
    assert geometry.live_logo_box_width == 64
    assert geometry.live_logo_box_height == 56
    assert geometry.live_logo_pixmap_size == 56
    assert geometry.render_source == "generated-pixmap"


def test_mobaxterm_rail_items_include_vertical_reference_labels() -> None:
    items = gui_design_moba_rail_items()

    assert [item.role for item in items] == ["collapse", "sessions", "favorites", "tools", "macros", "sftp"]
    assert [item.rail_icon_key for item in items] == ["collapse", "session", "star", "tools", "macros", "sftp"]
    assert {item.role: item.label for item in items if item.label} == {
        "sessions": "Sessions",
        "tools": "Tools",
        "macros": "Macros",
        "sftp": "SFTP",
    }
    assert all(item.icon_key for item in items)
    assert all(item.color.startswith("#") for item in items)


def test_mobaxterm_rail_geometry_is_shared_metadata() -> None:
    chrome = gui_design_moba_rail_chrome()
    geometry = gui_design_moba_rail_item_geometry()

    assert chrome.rail_width == 24
    assert chrome.icon_x == 5
    assert chrome.static_icon_size == 16
    assert chrome.live_icon_size == 20
    assert chrome.generated_icon_size == 22
    assert (chrome.button_width, chrome.button_height) == (24, 26)
    assert (chrome.active_x, chrome.active_y_offset, chrome.active_width, chrome.active_height) == (2, -3, 20, 30)
    assert (chrome.label_width, chrome.label_height, chrome.label_step) == (24, 54, 58)
    assert chrome.unlabeled_gap_after == 8
    assert chrome.label_font_size == 10
    assert chrome.render_source == "generated-pixmap"
    assert [(item.role, item.static_icon_y, item.static_label_y) for item in geometry] == [
        ("collapse", 8, 0),
        ("sessions", 42, 68),
        ("favorites", 126, 0),
        ("tools", 160, 186),
        ("macros", 244, 270),
        ("sftp", 328, 354),
    ]


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
    assert [action.static_x for action in actions] == [7, 7, 7]
    assert [action.static_y for action in actions] == [13, 49, 85]
    assert [action.static_size for action in actions] == [16, 16, 16]
    assert [action.live_icon_size for action in actions] == [18, 18, 18]
    assert [action.button_size for action in actions] == [22, 22, 22]
    assert [action.render_source for action in actions] == ["generated-pixmap"] * 3
    assert all(action.tooltip for action in actions)
    assert all(action.color.startswith("#") for action in actions)


def test_mobaxterm_right_utility_action_route_is_shared_metadata() -> None:
    route = gui_design_moba_right_utility_action_route()
    actions = gui_design_moba_right_utility_actions()

    assert route.key == "moba-right-utility-action-route"
    assert route.route_role == "right-utility-rail-actions-to-terminal-workflows"
    assert route.rail_object == "mobaRightUtilityRail"
    assert route.action_object == "mobaRightUtilityAction"
    assert route.action_keys == tuple(action.key for action in actions)
    assert route.action_labels == tuple(action.label for action in actions)
    assert route.action_icon_keys == tuple(action.icon_key for action in actions)
    assert route.action_handlers == (
        "show_moba_clipboard_hints",
        "show_moba_terminal_settings",
        "show_moba_tools_status",
    )
    assert route.route_key_property == "mobaRightUtilityRouteKey"
    assert route.handler_property == "mobaRightUtilityRouteHandler"
    assert route.action_keys_property == "mobaRightUtilityRouteActionKeys"
    assert route.render_source == "gui-design-moba-right-utility-route"


def test_mobaxterm_right_utility_rail_chrome_is_shared_metadata() -> None:
    chrome = gui_design_moba_right_utility_rail_chrome()

    assert chrome.static_width == 30
    assert chrome.live_width == 30
    assert (chrome.margin_left, chrome.margin_top, chrome.margin_right, chrome.margin_bottom) == (2, 2, 2, 2)
    assert chrome.action_spacing == 8
    assert chrome.session_edge_top_y == 108
    assert chrome.session_edge_height == 50
    assert chrome.session_edge_icon_x == 9
    assert chrome.session_edge_icon_size == 16


def test_mobaxterm_session_edge_actions_are_shared_metadata() -> None:
    actions = gui_design_moba_session_edge_actions()

    assert [action.key for action in actions] == ["attachment", "settings"]
    assert [action.icon_key for action in actions] == ["clip", "gear"]
    assert [action.label for action in actions] == ["Session attachment", "Session settings"]
    assert [action.static_y for action in actions] == [112, 130]
    assert [action.relative_y(108) for action in actions] == [4, 22]
    assert [action.static_size for action in actions] == [16, 16]
    assert [action.live_icon_size for action in actions] == [16, 16]
    assert [action.button_size for action in actions] == [22, 22]
    assert [action.render_source for action in actions] == ["generated-pixmap", "generated-pixmap"]
    assert all(action.tooltip for action in actions)
    assert all(action.color.startswith("#") for action in actions)


def test_mobaxterm_session_edge_action_route_is_shared_metadata() -> None:
    route = gui_design_moba_session_edge_action_route()
    actions = gui_design_moba_session_edge_actions()

    assert route.key == "moba-session-edge-action-route"
    assert route.route_role == "session-edge-shortcuts-to-active-tab-workflows"
    assert route.controls_object == "mobaSessionEdgeControls"
    assert route.action_object == "mobaSessionEdgeAction"
    assert route.placement == "tab-strip-overlay"
    assert route.action_keys == tuple(action.key for action in actions)
    assert route.action_labels == tuple(action.label for action in actions)
    assert route.action_icon_keys == tuple(action.icon_key for action in actions)
    assert route.action_handlers == ("show_moba_session_attachment", "show_moba_session_settings")
    assert route.route_key_property == "mobaSessionEdgeRouteKey"
    assert route.handler_property == "mobaSessionEdgeRouteHandler"
    assert route.action_keys_property == "mobaSessionEdgeRouteActionKeys"
    assert route.render_source == "gui-design-moba-session-edge-route"


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


def test_mobaxterm_sftp_toolbar_action_route_is_shared_metadata() -> None:
    route = gui_design_moba_sftp_toolbar_action_route()
    actions = gui_design_moba_sftp_dock_actions()

    assert route.key == "moba-sftp-toolbar-action-route"
    assert route.route_role == "sftp-toolbar-actions-to-file-transfer-workflows"
    assert route.toolbar_object == "mobaSftpToolbar"
    assert route.action_object == "mobaSftpAction"
    assert route.target_browser_object == "mobaSftpBrowser"
    assert route.target_path_object == "mobaSftpPath"
    assert route.target_table_object == "mobaSftpFileTable"
    assert route.queue_object == "mobaSftpTransferQueue"
    assert route.action_keys == tuple(action.key for action in actions)
    assert route.action_labels == tuple(action.label for action in actions)
    assert route.action_icon_keys == tuple(action.icon_key for action in actions)
    assert route.action_group_keys == tuple(action.group_key for action in actions)
    assert route.action_tooltips == tuple(action.tooltip for action in actions)
    assert set(route.action_handlers) == {"show_moba_sftp_toolbar_action"}
    assert route.action_statuses == (
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
    )
    assert route.signal == "clicked"
    assert route.route_key_property == "mobaSftpToolbarRouteKey"
    assert route.signal_property == "mobaSftpToolbarRouteSignal"
    assert route.handler_property == "mobaSftpToolbarRouteHandler"
    assert route.action_groups_property == "mobaSftpToolbarRouteActionGroups"
    assert route.captured_action_property == "mobaSftpToolbarRouteCapturedAction"
    assert route.captured_status_property == "mobaSftpToolbarRouteCapturedStatus"
    assert route.live_action_property == "mobaSftpToolbarRouteLiveAction"
    assert route.live_status_property == "mobaSftpToolbarRouteLiveStatus"
    assert route.render_source == "gui-design-moba-sftp-toolbar-route"


def test_mobaxterm_sftp_toolbar_geometry_is_shared_metadata() -> None:
    geometry = gui_design_moba_sftp_toolbar_action_geometry()

    assert [item.key for item in geometry] == [
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
    assert [item.button_x for item in geometry] == [3, 34, 58, 89, 113, 137, 161, 192, 216, 240, 271]
    assert {item.button_y for item in geometry} == {1}
    assert {item.button_size for item in geometry} == {24}
    assert [item.icon_x for item in geometry] == [7, 38, 62, 93, 117, 141, 165, 196, 220, 244, 275]
    assert {item.icon_y for item in geometry} == {5}
    assert {item.icon_size for item in geometry} == {16}
    assert [item.separator_x for item in geometry if item.separator_after] == [34, 89, 192, 271]
    assert gui_design_moba_sftp_toolbar_action_geometry_for("ascii-mode").icon_x == 196


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
    assert [column.static_width for column in chrome.columns] == [182, 78, 94]
    assert chrome.geometry_dict() == {
        "path_text_x": 14,
        "path_text_y": 6,
        "path_font_size": 11,
        "dropdown_right_offset": 18,
        "dropdown_y": 6,
        "dropdown_font_size": 10,
        "header_label_y": 7,
        "header_font_size": 10,
        "row_top_offset": -4,
        "row_icon_x": 14,
        "row_icon_y_offset": -1,
        "row_name_x": 38,
        "row_size_x": 202,
        "row_modified_x": 278,
        "row_text_y_offset": 0,
        "row_text_font_size": 10,
        "row_modified_font_size": 9,
    }


def test_mobaxterm_sftp_follow_folder_route_is_shared_metadata() -> None:
    route = gui_design_moba_sftp_follow_folder_route()

    assert route.key == "sftp-follow-terminal-folder-route"
    assert route.route_role == "terminal-cwd-to-sftp-browser"
    assert route.source_control_key == "follow-terminal-folder"
    assert route.source_control_object == "mobaFollowTerminalFolder"
    assert route.source_path_property == "mobaMonitoringFollowPath"
    assert route.source_plan_property == "mobaMonitoringFollowPlan"
    assert route.source_enabled_property == "mobaMonitoringFollowEnabled"
    assert route.target_browser_object == "mobaSftpBrowser"
    assert route.target_path_object == "mobaSftpPath"
    assert route.target_table_object == "mobaSftpFileTable"
    assert route.target_path_property == "mobaSftpFollowRoutePath"
    assert route.target_plan_property == "mobaSftpFollowRoutePlan"
    assert route.target_enabled_property == "mobaSftpFollowRouteEnabled"
    assert route.render_source == "state-model"


def test_mobaxterm_sftp_file_row_icons_are_shared_metadata() -> None:
    row_icons = gui_design_moba_sftp_file_row_icons()

    assert [(item.kind, item.icon_key, item.row_kind) for item in row_icons] == [
        ("parent-dir", "folder-up", "parent-dir"),
        ("dir", "folder", "dir"),
        ("file", "file", "file"),
    ]
    assert [item.static_size for item in row_icons] == [14, 14, 14]
    assert [item.render_source for item in row_icons] == ["generated-pixmap"] * 3
    assert gui_design_moba_sftp_file_row_icon("parent-dir").icon_key == "folder-up"
    assert gui_design_moba_sftp_file_row_icon("unknown").icon_key == "file"


def test_mobaxterm_sftp_routed_file_rows_are_shared_metadata() -> None:
    route = gui_design_moba_sftp_follow_folder_route()
    rows = gui_design_moba_sftp_routed_file_rows()
    chrome = gui_design_moba_sftp_browser_chrome()

    assert rows.key == "sftp-follow-folder-file-rows"
    assert rows.route_role == "follow-folder-visible-file-list"
    assert rows.follow_route_key == route.key
    assert rows.target_table_object == route.target_table_object == "mobaSftpFileTable"
    assert rows.row_contract_property == "mobaSftpRowContractKey"
    assert rows.row_route_property == "mobaSftpRowFollowRouteKey"
    assert rows.row_path_property == "mobaSftpRowSourcePath"
    assert rows.row_index_property == "mobaSftpRowIndex"
    assert rows.row_selected_property == "mobaSftpRowSelectedByRoute"
    assert rows.parent_row_name == chrome.parent_row_label == ".."
    assert rows.selected_row_kind == chrome.selected_row_kind == "parent-dir"
    assert rows.render_source == "state-file-entries"


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


def test_mobaxterm_connected_dock_frame_is_shared_geometry_metadata() -> None:
    frame = gui_design_moba_connected_dock_frame()

    assert frame.side_width == 390
    assert frame.rail_width == 24
    assert frame.dock_x == 24
    assert frame.dock_y == 132
    assert frame.dock_width == 366
    assert frame.dock_height == 606
    assert frame.workspace_x == 390
    assert frame.quick_connect_y == 108
    assert frame.quick_connect_height == 24
    assert frame.status_y == 738


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


def test_mobaxterm_monitoring_control_geometry_is_shared_metadata() -> None:
    geometry = gui_design_moba_monitoring_control_geometry()

    assert [item.key for item in geometry] == ["remote-monitoring", "follow-terminal-folder"]
    assert [(item.anchor_x, item.static_y) for item in geometry] == [(104, 1), (42, 76)]
    assert [item.icon_x for item in geometry] == [104, 60]
    assert [item.icon_size for item in geometry] == [20, 16]
    assert [item.label_x for item in geometry] == [132, 80]
    assert [item.label_y_offset for item in geometry] == [2, 3]
    assert [item.label_font_size for item in geometry] == [12, 11]
    assert [item.label_bold for item in geometry] == [True, False]
    assert [item.check_size for item in geometry] == [0, 10]
    assert [item.check_y_offset for item in geometry] == [0, 3]
    assert [item.checkmark_points for item in geometry] == [(), ((2, 5), (5, 9), (10, 1))]
    assert [item.row_height for item in geometry] == [22, 19]
    assert [item.live_width for item in geometry] == [146, 208]


def test_mobaxterm_remote_monitoring_dock_chrome_is_compact_shared_metadata() -> None:
    chrome = gui_design_moba_remote_monitoring_dock_chrome()
    layout = gui_design_moba_sftp_dock_layout()

    assert chrome.title_control_key == "remote-monitoring"
    assert chrome.follow_control_key == "follow-terminal-folder"
    assert chrome.telemetry_surface == "bottom-telemetry-bar"
    assert chrome.visible_metric_keys == ()
    assert chrome.refresh_seconds == 5
    assert chrome.compact is True
    assert chrome.static_height == 116
    assert chrome.static_height == layout.monitoring_height
    assert chrome.divider_offset == layout.monitoring_divider_offset
    assert chrome.divider_left_inset == layout.monitoring_left_inset
    assert chrome.divider_right_inset == 194
    assert chrome.content_left == layout.monitoring_content_left
    assert chrome.icon_center_x == layout.monitoring_icon_center_x
    assert chrome.metric_row_gap == layout.monitoring_metric_row_gap
    assert chrome.live_controls_width == 260


def test_mobaxterm_monitoring_telemetry_route_is_shared_metadata() -> None:
    chrome = gui_design_moba_remote_monitoring_dock_chrome()
    metrics = gui_design_moba_monitoring_metrics()
    route = gui_design_moba_monitoring_telemetry_route()

    assert route.key == "remote-monitoring-to-bottom-telemetry"
    assert route.route_role == "compact-dock-bottom-telemetry"
    assert route.source_panel_object == "mobaRemoteMonitoring"
    assert route.source_control_key == chrome.title_control_key == "remote-monitoring"
    assert route.source_metric_keys == tuple(metric.key for metric in metrics)
    assert route.visible_dock_metric_keys == chrome.visible_metric_keys == ()
    assert route.telemetry_surface == chrome.telemetry_surface == "bottom-telemetry-bar"
    assert route.target_bar_object == "mobaTelemetryBar"
    assert route.target_cell_object == "mobaTelemetryCell"
    assert route.target_identity_cell_key == "target"
    assert route.target_metric_cell_keys == (
        "cpu",
        "memory",
        "disk",
        "net-up",
        "net-down",
        "connections",
        "processes",
    )
    assert route.render_source == "generated-pixmap"


def test_mobaxterm_remote_monitoring_control_route_is_shared_metadata() -> None:
    chrome = gui_design_moba_remote_monitoring_dock_chrome()
    telemetry_route = gui_design_moba_monitoring_telemetry_route()
    control = next(item for item in gui_design_moba_monitoring_controls() if item.key == "remote-monitoring")
    route = gui_design_moba_remote_monitoring_control_route()

    assert route.key == "moba-remote-monitoring-control-route"
    assert route.route_role == "remote-monitoring-control-to-telemetry-refresh"
    assert route.source_panel_object == "mobaRemoteMonitoring"
    assert route.source_control_object == "mobaMonitoringControl"
    assert route.source_control_key == chrome.title_control_key == control.key
    assert route.source_control_label == control.label == "Remote monitoring"
    assert route.source_control_type == control.control_type == "toggle"
    assert route.expected_checked is control.checked is True
    assert route.command_property == "mobaMonitoringCommand"
    assert route.refresh_seconds_property == "mobaMonitoringRefreshSeconds"
    assert route.checked_property == "mobaMonitoringControlChecked"
    assert route.telemetry_route_key == telemetry_route.key
    assert route.telemetry_surface == telemetry_route.telemetry_surface
    assert route.target_bar_object == telemetry_route.target_bar_object
    assert route.target_metric_cell_keys == telemetry_route.target_metric_cell_keys
    assert route.captured_command_property == "mobaRemoteMonitoringControlCapturedCommand"
    assert route.captured_refresh_seconds_property == "mobaRemoteMonitoringControlCapturedRefreshSeconds"
    assert route.signal == "toggled"
    assert route.handler == "handle_moba_remote_monitoring_toggled"
    assert route.signal_property == "mobaRemoteMonitoringControlSignal"
    assert route.handler_property == "mobaRemoteMonitoringControlHandler"
    assert route.live_checked_property == "mobaRemoteMonitoringControlLiveChecked"
    assert route.to_dict()["target_metric_cell_keys"] == list(telemetry_route.target_metric_cell_keys)
    assert route.render_source == "state-model"


def test_mobaxterm_follow_terminal_folder_control_route_is_shared_metadata() -> None:
    chrome = gui_design_moba_remote_monitoring_dock_chrome()
    follow_route = gui_design_moba_sftp_follow_folder_route()
    control = next(item for item in gui_design_moba_monitoring_controls() if item.key == "follow-terminal-folder")
    route = gui_design_moba_follow_terminal_folder_control_route()

    assert route.key == "moba-follow-terminal-folder-control-route"
    assert route.route_role == "follow-terminal-folder-control-to-sftp-browser-sync"
    assert route.source_panel_object == "mobaRemoteMonitoring"
    assert route.source_control_object == follow_route.source_control_object == "mobaFollowTerminalFolder"
    assert route.source_control_key == chrome.follow_control_key == control.key
    assert route.source_control_label == control.label == "Follow terminal folder"
    assert route.source_control_type == control.control_type == "checkbox"
    assert route.expected_checked is control.checked is True
    assert route.source_path_property == follow_route.source_path_property == "mobaMonitoringFollowPath"
    assert route.source_plan_property == follow_route.source_plan_property == "mobaMonitoringFollowPlan"
    assert route.source_enabled_property == follow_route.source_enabled_property == "mobaMonitoringFollowEnabled"
    assert route.target_browser_object == follow_route.target_browser_object == "mobaSftpBrowser"
    assert route.target_path_object == follow_route.target_path_object == "mobaSftpPath"
    assert route.target_table_object == follow_route.target_table_object == "mobaSftpFileTable"
    assert route.target_plan_property == follow_route.target_plan_property == "mobaSftpFollowRoutePlan"
    assert route.captured_checked_property == "mobaFollowTerminalFolderControlCapturedChecked"
    assert route.captured_path_property == "mobaFollowTerminalFolderControlCapturedPath"
    assert route.captured_plan_property == "mobaFollowTerminalFolderControlCapturedPlan"
    assert route.signal == "toggled"
    assert route.handler == "handle_moba_follow_terminal_folder_toggled"
    assert route.signal_property == "mobaFollowTerminalFolderControlSignal"
    assert route.handler_property == "mobaFollowTerminalFolderControlHandler"
    assert route.live_checked_property == "mobaFollowTerminalFolderControlLiveChecked"
    assert route.live_path_property == "mobaFollowTerminalFolderControlLivePath"
    assert route.live_plan_property == "mobaFollowTerminalFolderControlLivePlan"
    assert route.to_dict()["source_control_label"] == "Follow terminal folder"
    assert route.render_source == "state-model"


def test_mobaxterm_status_bar_chrome_is_shared_metadata() -> None:
    chrome = gui_design_moba_status_bar_chrome()
    segments = gui_design_moba_status_segments()

    assert chrome.notice == "REMOTE OPS WORKSPACE"
    assert chrome.product_note == "open-protocol operator shell"
    assert chrome.right_marker == "[]"
    assert chrome.static_height == 22
    assert chrome.notice_x == 6
    assert chrome.notice_y == 6
    assert chrome.product_note_x == 142
    assert chrome.product_note_y == 6
    assert chrome.text_font_size == 10
    assert chrome.segment_start_right_offset == 480
    assert chrome.marker_right_inset == 4
    assert chrome.marker_y == 6
    assert chrome.marker_width == 9
    assert chrome.marker_height == 10
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
    assert chrome.static_height == 182
    assert chrome.body_top_offset < chrome.static_height
    assert chrome.terminal_gap > 0


def test_mobaxterm_ssh_banner_row_geometry_is_shared_metadata() -> None:
    geometry = gui_design_moba_ssh_banner_row_geometry()

    assert [item.key for item in geometry] == [
        "title",
        "subtitle",
        "target",
        "direct-ssh",
        "ssh-compression",
        "smartcard-auth",
        "ssh-browser",
        "x11-forwarding",
        "footer",
    ]
    assert [item.object_name for item in geometry] == [
        "mobaSshBannerTitle",
        "mobaSshBannerSubtitle",
        "mobaSshBannerTargetLine",
        "mobaSshBannerCapability",
        "mobaSshBannerCapability",
        "mobaSshBannerCapability",
        "mobaSshBannerCapability",
        "mobaSshBannerCapability",
        "mobaSshBannerFooter",
    ]
    assert [item.static_x for item in geometry] == [0, 0, 14, 14, 14, 14, 14, 14, 14]
    assert [item.static_y for item in geometry] == [10, 27, 54, 70, 86, 102, 118, 134, 154]
    assert [item.static_width for item in geometry] == [570, 570, 542, 542, 542, 542, 542, 542, 542]
    assert {item.static_height for item in geometry} == {16}
    assert [item.key for item in geometry if item.centered] == ["title", "subtitle"]
    assert gui_design_moba_ssh_banner_row_geometry_for("footer").static_y == 154


def test_mobaxterm_terminal_transcript_row_geometry_is_shared_metadata() -> None:
    geometry = gui_design_moba_terminal_transcript_row_geometry()

    assert [item.key for item in geometry] == [
        "web-console",
        "spacer",
        "last-login",
        "prompt-ready",
    ]
    assert [item.static_x for item in geometry] == [14, 14, 14, 14]
    assert [item.static_y for item in geometry] == [0, 20, 40, 60]
    assert [item.row_height for item in geometry] == [20, 20, 20, 20]
    assert [item.font_size for item in geometry] == [13, 13, 13, 13]
    assert gui_design_moba_terminal_transcript_row_geometry_for("prompt-ready").static_y == 60


def test_securecrt_command_window_chrome_is_shared_metadata() -> None:
    chrome = gui_design_securecrt_command_window_chrome()

    assert chrome.key == "send-to-all-sessions"
    assert chrome.title == "Command Window"
    assert chrome.helper == "send command to active tab or all sessions"
    assert chrome.target_scope == "All Sessions"
    assert chrome.command == "$ row doctor --json"
    assert chrome.send_label == "Send"
    assert chrome.status == "ready"
    assert chrome.static_header_height == 25
    assert chrome.static_control_y == 31
    assert chrome.static_target_width == 112
    assert chrome.static_target_icon_size == 13
    assert chrome.static_input_x == 132
    assert chrome.static_input_text_x == 10
    assert chrome.static_input_text_y == 7
    assert chrome.static_send_width == 58
    assert chrome.static_send_right_margin == 10
    assert chrome.live_target_min_width == 112
    assert chrome.live_send_min_width == 48


def test_securecrt_command_window_send_route_is_shared_metadata() -> None:
    chrome = gui_design_securecrt_command_window_chrome()
    route = gui_design_securecrt_command_window_send_route()

    assert route.key == "securecrt-command-window-send-route"
    assert route.route_role == "command-input-to-active-sessions"
    assert route.source_window_object == "secureCrtCommandWindow"
    assert route.target_scope_object == "secureCrtCommandTarget"
    assert route.command_input_object == "secureCrtCommandInput"
    assert route.send_control_object == "secureCrtCommandSend"
    assert route.status_object == "secureCrtCommandStatus"
    assert route.command_property == "secureCrtCommandRouteCommand"
    assert route.target_scope_property == "secureCrtCommandRouteTargetScope"
    assert route.send_label_property == "secureCrtCommandRouteSendLabel"
    assert route.status_property == "secureCrtCommandRouteStatus"
    assert route.captured_property == "secureCrtCommandRouteCaptured"
    assert route.captured_command_property == "secureCrtCommandRouteCapturedCommand"
    assert route.captured_target_scope_property == "secureCrtCommandRouteCapturedTargetScope"
    assert route.captured_status_property == "secureCrtCommandRouteCapturedStatus"
    assert route.signal == "clicked"
    assert route.secondary_signal == "returnPressed"
    assert route.handler == "handle_securecrt_command_window_send"
    assert route.signal_property == "secureCrtCommandRouteSignal"
    assert route.secondary_signal_property == "secureCrtCommandRouteSecondarySignal"
    assert route.handler_property == "secureCrtCommandRouteHandler"
    assert route.live_submitted_property == "secureCrtCommandRouteLiveSubmitted"
    assert route.live_command_property == "secureCrtCommandRouteLiveCommand"
    assert route.live_target_scope_property == "secureCrtCommandRouteLiveTargetScope"
    assert route.live_status_property == "secureCrtCommandRouteLiveStatus"
    assert route.render_source == "state-model"
    assert route.to_dict()["handler"] == route.handler
    assert route.to_dict()["live_command_property"] == route.live_command_property
    assert chrome.command == "$ row doctor --json"
    assert chrome.target_scope == "All Sessions"
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
    assert [field.role for field in strip.fields] == ["normal", "normal", "normal", "normal", "normal", "normal", "status"]
    assert {field.static_y for field in strip.fields} == {5}
    assert {field.static_height for field in strip.fields} == {20}
    assert {field.static_label_x for field in strip.fields} == {6}
    assert {field.static_label_y for field in strip.fields} == {9}
    assert {field.static_value_x for field in strip.fields} == {48}
    assert {field.static_value_y for field in strip.fields} == {9}
    assert [field.live_min_width for field in strip.fields] == [132, 170, 102, 122, 102, 90, 84]
    assert {field.live_cell_height for field in strip.fields} == {22}
    assert strip.title_width == 86
    assert strip.static_title_x == 9
    assert strip.static_title_y == 10
    assert strip.static_cell_start_x == 96
    assert strip.static_cell_gap == 6
    assert strip.live_spacing == 6
    assert all(field.tooltip for field in strip.fields)


def test_securecrt_session_manager_chrome_is_shared_metadata() -> None:
    chrome = gui_design_securecrt_session_manager_chrome()

    assert chrome.title == "Session Manager"
    assert chrome.filter_placeholder == "Filter sessions"
    assert [action.key for action in chrome.actions] == ["connect", "new-folder", "properties"]
    assert [action.icon_key for action in chrome.actions] == ["connect", "folder", "properties"]
    assert [action.label for action in chrome.actions] == ["Connect", "New Folder", "Properties"]
    assert [action.static_x for action in chrome.actions] == [34, 60, 86]
    assert [action.static_y for action in chrome.actions] == [5, 5, 5]
    assert [action.static_button_size for action in chrome.actions] == [20, 20, 20]
    assert [action.static_icon_size for action in chrome.actions] == [10, 10, 9]
    assert [action.live_icon_size for action in chrome.actions] == [14, 14, 14]
    assert [action.live_button_size for action in chrome.actions] == [24, 24, 24]
    assert {action.render_source for action in chrome.actions} == {"generated-pixmap"}
    assert chrome.static_title_x == 8
    assert chrome.static_title_y == 8
    assert chrome.static_filter_y == 35
    assert chrome.static_filter_x_margin == 8
    assert chrome.static_filter_height == 24
    assert chrome.static_filter_placeholder_x == 17
    assert chrome.static_filter_placeholder_y == 7
    assert chrome.live_max_height == 94
    assert chrome.live_spacing == 5
    assert chrome.live_title_spacing == 5
    assert chrome.live_filter_height == 24
    assert all(action.tooltip for action in chrome.actions)


def test_securecrt_session_manager_route_is_shared_metadata() -> None:
    route = gui_design_securecrt_session_manager_route()
    manager = gui_design_securecrt_session_manager_chrome()
    strip = gui_design_securecrt_session_status_strip()
    reference = gui_design_reference_state("securecrt")

    assert route.key == "securecrt-session-manager-route"
    assert route.route_role == "session-manager-selection-to-active-tab"
    assert route.selected_profile_name == "edge-prod"
    assert route.selected_tree_label == "edge-prod (SSH2)"
    assert route.selected_tree_object == "profileTree"
    assert route.session_manager_object == "secureCrtSessionManagerChrome"
    assert route.session_manager_action_key == "connect"
    assert route.session_manager_action_object == "secureCrtSessionManagerAction"
    assert route.status_strip_object == "secureCrtSessionStatusStrip"
    assert route.status_field_key == "target"
    assert route.status_field_object == "secureCrtSessionStatusCell"
    assert route.active_tab_label == reference.active_tab_label == "edge-prod (SSH2)"
    assert route.target_value == reference.target_label == "edge-prod.example.invalid:22"
    assert route.protocol_value == "SSH2"
    assert route.session_value == "edge-prod"
    assert route.selected_tree_property == "secureCrtSessionRouteSelected"
    assert route.action_active_property == "secureCrtSessionRouteActive"
    assert route.tab_label_property == "secureCrtSessionRouteActiveTab"
    assert route.status_value_property == "secureCrtSessionRouteStatusValue"
    assert route.render_source == "session-manager-state"
    assert any(
        action.key == route.session_manager_action_key and action.label == "Connect"
        for action in manager.actions
    )
    assert any(
        field.key == route.status_field_key and field.value == route.target_value
        for field in strip.fields
    )


def test_securecrt_session_manager_filter_route_is_shared_metadata() -> None:
    route = gui_design_securecrt_session_manager_filter_route()
    session_route = gui_design_securecrt_session_manager_route()
    manager = gui_design_securecrt_session_manager_chrome()

    assert route.key == "securecrt-session-manager-filter-route"
    assert route.route_role == "session-manager-filter-to-visible-session-row"
    assert route.session_manager_object == session_route.session_manager_object
    assert route.filter_object == "secureCrtSessionFilter"
    assert route.selected_tree_object == session_route.selected_tree_object
    assert route.selected_profile_name == session_route.selected_profile_name
    assert route.selected_tree_label == session_route.selected_tree_label
    assert route.expected_query == "edge"
    assert route.expected_placeholder == manager.filter_placeholder
    assert route.matched_result_label == "edge-prod (SSH2)"
    assert route.filter_route_property == "secureCrtSessionFilterRouteKey"
    assert route.filter_query_property == "secureCrtSessionFilterRouteQuery"
    assert route.filter_placeholder_property == "secureCrtSessionFilterRoutePlaceholder"
    assert route.matched_result_property == "secureCrtSessionFilterRouteMatchedLabel"
    assert route.change_signal == "textChanged"
    assert route.handler_name == "filter_profile_tree"
    assert route.render_source == "session-manager-filter-state"
    assert route.to_dict()["matched_result_label"] == route.matched_result_label


def test_securecrt_sftp_tab_route_is_shared_metadata() -> None:
    route = gui_design_securecrt_sftp_tab_route()
    cards = {card.key: card for card in gui_design_workflow_cards("securecrt")}
    strip = gui_design_securecrt_session_status_strip()
    tabs = {label for label, _status, _active in gui_design_tab_items("securecrt")}
    tree_rows = {name.strip() for name, _target, _group in gui_design_tree_rows("securecrt")}

    assert route.key == "securecrt-sftp-tab-route"
    assert route.route_role == "workflow-card-to-sftp-tab-status"
    assert route.workflow_card_key == "sftp-tab"
    assert route.selected_profile_name == "files-prod"
    assert route.selected_tree_label == "files-prod (SFTP)"
    assert route.sftp_tab_label == "files-prod"
    assert route.status_field_key == "sftp"
    assert route.status_value == "files-prod tab"
    assert route.transfer_state == "files-prod attached"
    assert cards[route.workflow_card_key].title == route.workflow_title == "SFTP tab"
    assert cards[route.workflow_card_key].primary == route.transfer_state
    assert cards[route.workflow_card_key].secondary == route.workflow_secondary
    assert any(
        field.key == route.status_field_key and field.value == route.status_value
        for field in strip.fields
    )
    assert route.sftp_tab_label in tabs
    assert route.selected_tree_label in tree_rows
    assert route.workflow_key_property == "secureCrtSftpTabRouteWorkflowKey"
    assert route.to_dict()["status_value"] == route.status_value


def test_securecrt_sftp_browser_route_is_shared_metadata() -> None:
    tab_route = gui_design_securecrt_sftp_tab_route()
    route = gui_design_securecrt_sftp_browser_route()
    rows = {row.name: row for row in route.file_rows}

    assert route.key == "securecrt-sftp-browser-route"
    assert route.route_role == "sftp-tab-to-transfer-browser"
    assert route.sftp_tab_route_key == tab_route.key
    assert route.selected_profile_name == tab_route.selected_profile_name
    assert route.selected_tree_label == tab_route.selected_tree_label
    assert route.sftp_tab_label == tab_route.sftp_tab_label
    assert route.remote_path == "/srv/files"
    assert route.toolbar_actions == ("upload", "download", "refresh")
    assert route.active_row_name == "deploy.log"
    assert route.transfer_queue_label == "1 queued"
    assert route.transfer_status == "ready"
    assert rows[route.active_row_name].selected is True
    assert rows[route.active_row_name].kind == "file"
    assert route.path_property == "secureCrtSftpBrowserPath"
    assert route.queue_state_property == "secureCrtSftpBrowserQueueState"
    assert route.action_object == "secureCrtSftpAction"
    assert route.action_key == "refresh"
    assert route.action_label == "Refresh"
    assert route.action_status == "refreshed"
    assert route.signal == "clicked"
    assert route.handler == "handle_securecrt_sftp_browser_action"
    assert route.signal_property == "secureCrtSftpBrowserRouteSignal"
    assert route.handler_property == "secureCrtSftpBrowserRouteHandler"
    assert route.captured_property == "secureCrtSftpBrowserRouteCaptured"
    assert route.captured_action_property == "secureCrtSftpBrowserRouteCapturedAction"
    assert route.captured_status_property == "secureCrtSftpBrowserRouteCapturedStatus"
    assert route.live_triggered_property == "secureCrtSftpBrowserRouteLiveTriggered"
    assert route.live_action_property == "secureCrtSftpBrowserRouteLiveAction"
    assert route.live_status_property == "secureCrtSftpBrowserRouteLiveStatus"
    assert route.to_dict()["toolbar_actions"] == ["upload", "download", "refresh"]
    assert route.to_dict()["handler"] == "handle_securecrt_sftp_browser_action"
    assert route.to_dict()["live_triggered_property"] == "secureCrtSftpBrowserRouteLiveTriggered"
    assert route.to_dict()["file_rows"][2]["name"] == route.active_row_name


def test_securecrt_session_tree_icons_are_shared_metadata() -> None:
    root = gui_design_tree_root_icon("securecrt")
    rows = gui_design_tree_row_icons("securecrt")

    assert root.label == "Session Database"
    assert root.icon_key == "database"
    assert root.row_kind == "root"
    assert root.static_size == 16
    assert [(row.label, row.icon_key, row.row_kind) for row in rows] == [
        ("Sessions", "folder", "group"),
        ("edge-prod (SSH2)", "ssh2", "profile"),
        ("files-prod (SFTP)", "sftp", "profile"),
        ("Local Shells", "folder", "group"),
        ("PowerShell", "shell", "profile"),
        ("Net tools", "command", "profile"),
        ("Pinned", "folder", "group"),
        ("jump-host (SSH2)", "pin", "profile"),
    ]
    assert gui_design_tree_row_icon("securecrt", "edge-prod (SSH2)", "", False).icon_key == "ssh2"
    assert gui_design_tree_row_icon("securecrt", "files-prod (SFTP)", "", False).icon_key == "sftp"
    assert gui_design_tree_row_icon("securecrt", "jump-host (SSH2)", "", False).icon_key == "pin"


def test_product_session_tree_icons_are_shared_metadata() -> None:
    assert [(row.label, row.icon_key, row.row_kind, row.static_size) for row in gui_design_tree_row_icons("mobaxterm")] == [
        ("default", "folder", "group", 15),
        ("example.jump-ssh", "pin", "profile", 14),
        ("example.rdp", "rdp", "profile", 14),
        ("prod", "folder", "group", 15),
        ("edge-prod", "ssh", "profile", 14),
        ("win-admin", "rdp", "profile", 14),
        ("files", "folder", "group", 15),
        ("sftp-ops", "sftp", "profile", 14),
        ("sync-stage", "ssh", "profile", 14),
    ]
    assert [(row.label, row.icon_key, row.row_kind) for row in gui_design_tree_row_icons("termius")] == [
        ("Personal", "folder", "group"),
        ("edge-prod", "host", "profile"),
        ("jump-host", "pin", "profile"),
        ("Teams", "folder", "group"),
        ("prod-cluster", "host", "profile"),
        ("Snippets", "folder", "group"),
        ("deploy-check", "snippet", "profile"),
    ]
    assert [(row.label, row.icon_key, row.row_kind) for row in gui_design_tree_row_icons("remmina")] == [
        ("RDP", "folder", "group"),
        ("win-admin", "rdp", "profile"),
        ("lab-desktop", "rdp", "profile"),
        ("VNC", "folder", "group"),
        ("linux-console", "vnc", "profile"),
        ("SSH/SFTP", "folder", "group"),
        ("sftp-ops", "sftp", "profile"),
    ]
    assert [(row.label, row.icon_key, row.row_kind) for row in gui_design_tree_row_icons("mremoteng")] == [
        ("Connections.xml", "database", "group"),
        ("prod", "folder", "group"),
        ("edge-prod [SSH]", "ssh", "profile"),
        ("win-admin [RDP]", "rdp", "profile"),
        ("files", "folder", "group"),
        ("sftp-ops [SFTP]", "sftp", "profile"),
        ("tools", "folder", "group"),
        ("net-tools [SSH]", "ssh", "profile"),
    ]
    assert gui_design_tree_root_icon("termius").icon_key == "database"
    assert gui_design_tree_root_icon("mobaxterm").icon_key == "folder"
    assert gui_design_tree_row_icon("remmina", "linux-console", "", False).icon_key == "vnc"
    assert gui_design_tree_row_icon("mremoteng", "win-admin [RDP]", "", False).icon_key == "rdp"


def test_mobaxterm_session_tree_chrome_is_shared_metadata() -> None:
    chrome = gui_design_moba_session_tree_chrome()

    assert chrome.header_height == 28
    assert chrome.header_icon_x == 9
    assert chrome.header_text_x == 31
    assert chrome.row_start_y == 38
    assert chrome.indentation == 16
    assert chrome.root_row_height == 28
    assert chrome.group_row_height == 24
    assert chrome.profile_row_height == 34
    assert chrome.group_icon_x == 29
    assert chrome.group_label_x == 51
    assert chrome.profile_icon_x == 39
    assert chrome.profile_label_x == 61
    assert chrome.profile_target_x == 61
    assert chrome.selected_left == 28
    assert chrome.selected_height == 34
    assert chrome.root_is_decorated is True
    assert chrome.animated is True
    assert chrome.uniform_row_heights is True
    assert chrome.render_source == "generated-pixmap"


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
        "import",
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
        "import-session",
        "properties",
        "delete",
    ]
    assert [action.static_x for action in chrome.toolbar_actions[:4]] == [14, 82, 180, 258]
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
    assert [control.static_width for control in controls] == [74] * 5
    assert [control.static_step for control in controls] == [78] * 5
    assert [control.static_y for control in controls] == [7] * 5
    assert [control.static_height for control in controls] == [20] * 5
    assert [control.static_icon_x for control in controls] == [6] * 5
    assert [control.static_icon_size for control in controls] == [12] * 5
    assert [control.static_label_x for control in controls] == [22] * 5
    assert [control.live_icon_size for control in controls] == [14] * 5
    assert [control.live_min_width for control in controls] == [74] * 5
    assert [control.live_button_height for control in controls] == [26] * 5
    assert [control.render_source for control in controls] == ["generated-pixmap"] * 5
    assert all(control.tooltip for control in controls)


def test_remmina_profile_list_chrome_is_shared_metadata() -> None:
    chrome = gui_design_remmina_profile_list_chrome()

    assert chrome.title == "Connection list"
    assert chrome.filter_placeholder == "Filter by name or protocol"
    assert [column.key for column in chrome.columns] == ["name", "protocol", "server"]
    assert [column.label for column in chrome.columns] == ["Name", "Protocol", "Server"]
    assert [column.static_width for column in chrome.columns] == [98, 58, 104]
    assert [column.live_min_width for column in chrome.columns] == [98, 58, 104]
    assert [row.key for row in chrome.rows] == ["win-admin", "linux-console", "sftp-ops"]
    assert [row.protocol for row in chrome.rows] == ["RDP", "VNC", "SFTP"]
    assert chrome.rows[0].selected is True
    assert chrome.rows[0].server == "admin-win.example.invalid"
    assert chrome.rows[-1].status == "file sharing"
    assert chrome.static_filter_x == 110
    assert chrome.static_filter_y == 5
    assert chrome.static_filter_height == 20
    assert chrome.static_header_y == 33
    assert chrome.static_row_start_y == 48
    assert chrome.static_row_height == 22
    assert chrome.static_row_step == 24
    assert chrome.static_cell_start_x == 12
    assert chrome.static_cell_y == 6
    assert chrome.static_status_y == 16
    assert chrome.live_max_height == 166
    assert chrome.live_filter_width == 142
    assert chrome.live_row_min_height == 24


def test_remmina_profile_viewer_route_is_shared_metadata() -> None:
    route = gui_design_remmina_profile_viewer_route()
    chrome = gui_design_remmina_profile_list_chrome()
    controls = gui_design_remmina_viewer_controls()

    assert route.key == "remmina-selected-profile-viewer-route"
    assert route.route_role == "selected-profile-to-viewer-tab"
    assert route.selected_profile_key == "win-admin"
    assert route.selected_profile_object == "remminaProfileListRow"
    assert route.viewer_controls_object == "remminaViewerControls"
    assert route.viewer_control_key == "scale-100"
    assert route.viewer_control_object == "remminaViewerControl"
    assert route.active_tab_label == "RDP - win-admin"
    assert route.protocol == "RDP"
    assert route.profile_status == "scale 100%"
    assert route.selected_row_property == "selectedRow"
    assert route.control_active_property == "remminaProfileViewerRouteActive"
    assert route.tab_label_property == "remminaProfileViewerRouteActiveTab"
    assert route.render_source == "profile-list-state"
    assert any(row.key == route.selected_profile_key and row.selected for row in chrome.rows)
    assert any(control.key == route.viewer_control_key and control.label == "Scale 100%" for control in controls)


def test_remmina_profile_filter_route_is_shared_metadata() -> None:
    route = gui_design_remmina_profile_filter_route()
    viewer_route = gui_design_remmina_profile_viewer_route()
    chrome = gui_design_remmina_profile_list_chrome()

    assert route.key == "remmina-profile-filter-route"
    assert route.route_role == "profile-filter-to-visible-viewer-row"
    assert route.profile_list_object == "remminaProfileListChrome"
    assert route.filter_object == "remminaProfileFilter"
    assert route.selected_profile_key == viewer_route.selected_profile_key
    assert route.selected_profile_object == viewer_route.selected_profile_object
    assert route.matched_profile_name == "win-admin"
    assert route.matched_protocol == viewer_route.protocol == "RDP"
    assert route.matched_status == viewer_route.profile_status == "scale 100%"
    assert route.expected_query == "rdp"
    assert route.expected_placeholder == chrome.filter_placeholder
    assert route.active_tab_label == viewer_route.active_tab_label
    assert route.filter_route_property == "remminaProfileFilterRouteKey"
    assert route.filter_query_property == "remminaProfileFilterRouteQuery"
    assert route.filter_placeholder_property == "remminaProfileFilterRoutePlaceholder"
    assert route.matched_profile_property == "remminaProfileFilterRouteMatchedProfile"
    assert route.matched_protocol_property == "remminaProfileFilterRouteMatchedProtocol"
    assert route.active_tab_property == "remminaProfileFilterRouteActiveTab"
    assert route.change_signal == "textChanged"
    assert route.handler_name == "filter_remmina_profile_rows"
    assert route.render_source == "profile-filter-state"
    assert route.to_dict()["expected_query"] == "rdp"


def test_remmina_clipboard_route_is_shared_metadata() -> None:
    route = gui_design_remmina_clipboard_route()
    controls = gui_design_remmina_viewer_controls()
    reference = gui_design_reference_state("remmina")
    surface = gui_design_workspace_surface("remmina")

    assert route.key == "remmina-clipboard-sync-route"
    assert route.route_role == "viewer-control-to-clipboard-state"
    assert route.viewer_controls_object == "remminaViewerControls"
    assert route.viewer_control_key == "clipboard"
    assert route.viewer_control_object == "remminaViewerControl"
    assert route.active_tab_label == "RDP - win-admin"
    assert route.protocol == "RDP"
    assert route.clipboard_state == "clipboard on"
    assert route.status_segment == "Clipboard on"
    assert route.detail_line == "Clipboard: enabled"
    assert route.activity_line == "Clipboard: on"
    assert route.control_active_property == "remminaClipboardRouteActive"
    assert route.tab_label_property == "remminaClipboardRouteActiveTab"
    assert route.clipboard_state_property == "remminaClipboardRouteState"
    assert route.render_source == "viewer-control-state"
    assert route.active_tab_label == reference.active_tab_label
    assert route.status_segment in reference.status_segments
    assert route.clipboard_state == surface.secondary_state
    assert route.detail_line in surface.detail_lines
    assert route.activity_line in surface.activity_lines
    assert any(control.key == route.viewer_control_key and control.label == "Clipboard" for control in controls)


def test_remmina_screenshot_route_is_shared_metadata() -> None:
    route = gui_design_remmina_screenshot_route()
    viewer_route = gui_design_remmina_profile_viewer_route()
    controls = gui_design_remmina_viewer_controls()
    reference = gui_design_reference_state("remmina")
    surface = gui_design_workspace_surface("remmina")

    assert route.key == "remmina-screenshot-capture-route"
    assert route.route_role == "viewer-control-to-screenshot-capture"
    assert route.viewer_controls_object == viewer_route.viewer_controls_object == "remminaViewerControls"
    assert route.viewer_control_key == "screenshot"
    assert route.viewer_control_object == viewer_route.viewer_control_object == "remminaViewerControl"
    assert route.active_tab_label == viewer_route.active_tab_label == "RDP - win-admin"
    assert route.protocol == viewer_route.protocol == "RDP"
    assert route.capture_state == "screenshot ready"
    assert route.capture_artifact == "win-admin-rdp-screenshot.png"
    assert route.status_segment == "RDP/VNC ready"
    assert route.detail_line == "Screenshot: win-admin-rdp-screenshot.png"
    assert route.activity_line == "Screenshot: capture ready"
    assert route.control_active_property == "remminaScreenshotRouteActive"
    assert route.tab_label_property == "remminaScreenshotRouteActiveTab"
    assert route.capture_state_property == "remminaScreenshotRouteState"
    assert route.capture_artifact_property == "remminaScreenshotRouteArtifact"
    assert route.signal == "clicked"
    assert route.handler == "handle_remmina_screenshot_capture"
    assert route.signal_property == "remminaScreenshotRouteSignal"
    assert route.handler_property == "remminaScreenshotRouteHandler"
    assert route.captured_property == "remminaScreenshotRouteCaptured"
    assert route.captured_state_property == "remminaScreenshotRouteCapturedState"
    assert route.captured_artifact_property == "remminaScreenshotRouteCapturedArtifact"
    assert route.live_triggered_property == "remminaScreenshotRouteLiveTriggered"
    assert route.live_capture_state_property == "remminaScreenshotRouteLiveState"
    assert route.live_capture_artifact_property == "remminaScreenshotRouteLiveArtifact"
    assert route.render_source == "viewer-control-state"
    assert route.to_dict()["capture_artifact"] == "win-admin-rdp-screenshot.png"
    assert route.to_dict()["handler"] == "handle_remmina_screenshot_capture"
    assert route.to_dict()["live_triggered_property"] == "remminaScreenshotRouteLiveTriggered"
    assert route.active_tab_label == reference.active_tab_label
    assert route.status_segment in reference.status_segments
    assert route.detail_line in surface.detail_lines
    assert route.activity_line in surface.activity_lines
    assert any(control.key == route.viewer_control_key and control.label == "Screenshot" for control in controls)


def test_remmina_sftp_transfer_route_is_shared_metadata() -> None:
    route = gui_design_remmina_sftp_transfer_route()
    chrome = gui_design_remmina_profile_list_chrome()
    surface = gui_design_workspace_surface("remmina")
    rows = {row.key: row for row in chrome.rows}
    file_rows = {row.name: row for row in route.file_rows}

    assert route.key == "remmina-sftp-transfer-route"
    assert route.route_role == "transfer-toolbar-to-sftp-profile-browser"
    assert route.profile_list_object == "remminaProfileListChrome"
    assert route.selected_profile_key == "sftp-ops"
    assert rows[route.selected_profile_key].name == route.selected_profile_name == "sftp-ops"
    assert rows[route.selected_profile_key].protocol == route.selected_profile_protocol == "SFTP"
    assert rows[route.selected_profile_key].status == route.selected_profile_status == "file sharing"
    assert route.selected_tree_label == "sftp-ops"
    assert route.toolbar_action_key == "queue"
    assert route.toolbar_action_label == "Transfer"
    assert route.toolbar_action_object == "productToolbarButton"
    assert route.active_tab_label == "sftp-ops"
    assert route.remote_path == "/var/log"
    assert route.toolbar_actions == ("upload", "download", "queue")
    assert route.active_row_name == "app.log"
    assert file_rows[route.active_row_name].selected is True
    assert route.transfer_queue_label == "1 queued"
    assert route.transfer_status == "ready"
    assert route.detail_line in surface.detail_lines
    assert route.activity_line in surface.activity_lines
    assert route.path_property == "remminaSftpTransferRoutePath"
    assert route.queue_state_property == "remminaSftpTransferRouteQueueState"
    assert route.action_object == "remminaSftpTransferAction"
    assert route.action_key == "queue"
    assert route.action_label == "Queue"
    assert route.action_status == "queued"
    assert route.signal == "clicked"
    assert route.handler == "handle_remmina_sftp_transfer_action"
    assert route.signal_property == "remminaSftpTransferRouteSignal"
    assert route.handler_property == "remminaSftpTransferRouteHandler"
    assert route.captured_property == "remminaSftpTransferRouteCaptured"
    assert route.captured_action_property == "remminaSftpTransferRouteCapturedAction"
    assert route.captured_status_property == "remminaSftpTransferRouteCapturedStatus"
    assert route.live_triggered_property == "remminaSftpTransferRouteLiveTriggered"
    assert route.live_action_property == "remminaSftpTransferRouteLiveAction"
    assert route.live_status_property == "remminaSftpTransferRouteLiveStatus"
    assert route.to_dict()["toolbar_actions"] == ["upload", "download", "queue"]
    assert route.to_dict()["file_rows"][2]["name"] == route.active_row_name
    assert route.to_dict()["handler"] == "handle_remmina_sftp_transfer_action"
    assert route.to_dict()["live_triggered_property"] == "remminaSftpTransferRouteLiveTriggered"


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
    assert [field.role for field in strip.fields] == ["normal", "normal", "normal", "normal", "normal", "normal", "status"]
    assert {field.static_y for field in strip.fields} == {5}
    assert {field.static_height for field in strip.fields} == {20}
    assert {field.static_label_x for field in strip.fields} == {6}
    assert {field.static_label_y for field in strip.fields} == {9}
    assert {field.static_value_x for field in strip.fields} == {42}
    assert {field.static_value_y for field in strip.fields} == {9}
    assert [field.live_min_width for field in strip.fields] == [92, 112, 82, 92, 132, 122, 82]
    assert {field.live_cell_height for field in strip.fields} == {22}
    assert strip.title_width == 88
    assert strip.static_title_x == 9
    assert strip.static_title_y == 10
    assert strip.static_cell_start_x == 80
    assert strip.static_cell_gap == 6
    assert strip.live_spacing == 6
    assert all(field.tooltip for field in strip.fields)


def test_termius_sync_route_is_shared_metadata() -> None:
    route = gui_design_termius_sync_route()
    hosts = gui_design_termius_hosts_chrome()
    chips = gui_design_termius_header_chips()
    strip = gui_design_termius_host_identity_strip()

    assert route.key == "termius-host-sync-route"
    assert route.route_role == "hosts-sync-to-identity-status"
    assert route.hosts_action_key == "sync-hosts"
    assert route.hosts_action_object == "termiusHostsAction"
    assert route.header_chip_key == "sync-current"
    assert route.header_chip_object == "termiusHeaderChip"
    assert route.identity_field_key == "sync"
    assert route.identity_cell_object == "termiusHostIdentityCell"
    assert route.sync_state == "current"
    assert route.action_label_property == "termiusSyncRouteActionLabel"
    assert route.chip_label_property == "termiusSyncRouteChipLabel"
    assert route.identity_value_property == "termiusSyncRouteIdentityValue"
    assert route.status_property == "termiusSyncRouteState"
    assert route.render_source == "state-model"
    assert any(action.key == route.hosts_action_key and action.label == "Sync" for action in hosts.actions)
    assert any(chip.key == route.header_chip_key and chip.label == "Sync current" for chip in chips)
    assert any(field.key == route.identity_field_key and field.value == route.sync_state for field in strip.fields)


def test_termius_host_selection_route_is_shared_metadata() -> None:
    route = gui_design_termius_host_selection_route()
    strip = gui_design_termius_host_identity_strip()
    reference = gui_design_reference_state("termius")

    assert route.key == "termius-host-selection-route"
    assert route.route_role == "host-list-selection-to-active-tab"
    assert route.selected_profile_name == reference.profile_name == "edge-prod"
    assert route.selected_tree_label == "edge-prod  ssh host"
    assert route.selected_tree_object == "profileTree"
    assert route.hosts_panel_object == "termiusHostsChrome"
    assert route.host_identity_object == "termiusHostIdentityStrip"
    assert route.identity_field_key == "host"
    assert route.identity_cell_object == "termiusHostIdentityCell"
    assert route.active_tab_label == reference.active_tab_label == "edge-prod"
    assert route.target_value == reference.target_label == "edge-prod.example.invalid:22"
    assert route.protocol_value == reference.protocol_label == "SSH + Vault"
    assert route.host_value == "edge-prod"
    assert route.selected_tree_property == "termiusHostRouteSelected"
    assert route.tab_label_property == "termiusHostRouteActiveTab"
    assert route.identity_value_property == "termiusHostRouteIdentityValue"
    assert route.render_source == "host-list-state"
    assert any(field.key == route.identity_field_key and field.value == route.host_value for field in strip.fields)


def test_termius_port_forward_route_is_shared_metadata() -> None:
    route = gui_design_termius_port_forward_route()
    chips = gui_design_termius_header_chips()
    strip = gui_design_termius_host_identity_strip()
    reference = gui_design_reference_state("termius")
    host_route = gui_design_termius_host_selection_route()

    assert route.key == "termius-port-forward-route"
    assert route.route_role == "port-forward-chip-to-host-identity-forward"
    assert route.header_chip_key == "port-forward-ready"
    assert route.header_chip_object == "termiusHeaderChip"
    assert route.host_identity_object == "termiusHostIdentityStrip"
    assert route.identity_field_key == "forward"
    assert route.identity_cell_object == "termiusHostIdentityCell"
    assert route.active_tab_label == host_route.active_tab_label == "edge-prod"
    assert route.selected_profile_name == reference.profile_name == "edge-prod"
    assert route.forward_value == "8080 -> localhost:80"
    assert route.forward_state == "ready"
    assert route.local_port == 8080
    assert route.remote_host == "localhost"
    assert route.remote_port == 80
    assert route.status_segment == "Port fwd ready"
    assert route.chip_label_property == "termiusPortForwardRouteChipLabel"
    assert route.identity_value_property == "termiusPortForwardRouteIdentityValue"
    assert route.active_tab_property == "termiusPortForwardRouteActiveTab"
    assert route.status_property == "termiusPortForwardRouteState"
    assert route.render_source == "state-model"
    assert any(chip.key == route.header_chip_key and chip.label == route.status_segment for chip in chips)
    assert any(field.key == route.identity_field_key and field.value == route.forward_value for field in strip.fields)
    assert route.status_segment in reference.status_segments
    assert route.to_dict()["forward_value"] == route.forward_value


def test_termius_snippet_route_is_shared_metadata() -> None:
    route = gui_design_termius_snippet_route()
    cards = gui_design_workflow_cards("termius")
    strip = gui_design_termius_host_identity_strip()
    reference = gui_design_reference_state("termius")
    surface = gui_design_workspace_surface("termius")
    host_route = gui_design_termius_host_selection_route()

    assert route.key == "termius-snippet-route"
    assert route.route_role == "workflow-card-to-host-identity-snippet"
    assert route.workflow_card_key == "snippet"
    assert route.workflow_card_object == "productWorkflowCard"
    assert route.workflow_title_object == "productWorkflowTitle"
    assert route.workflow_primary_object == "productWorkflowPrimary"
    assert route.workflow_secondary_object == "productWorkflowSecondary"
    assert route.action_object == "termiusSnippetRunAction"
    assert route.shortcut_object == "termiusSnippetRunShortcut"
    assert route.host_identity_object == "termiusHostIdentityStrip"
    assert route.identity_field_key == "snippet"
    assert route.identity_cell_object == "termiusHostIdentityCell"
    assert route.active_tab_label == host_route.active_tab_label == "edge-prod"
    assert route.selected_profile_name == reference.profile_name == "edge-prod"
    assert route.workflow_title == "Snippet"
    assert route.snippet_command == "row vault status"
    assert route.snippet_state == "one-click command"
    assert route.detail_line == "Snippet  : row vault status"
    assert route.action_label == "Run"
    assert route.shortcut_sequence == "Return"
    assert route.workflow_key_property == "termiusSnippetRouteWorkflowKey"
    assert route.command_property == "termiusSnippetRouteCommand"
    assert route.identity_value_property == "termiusSnippetRouteIdentityValue"
    assert route.active_tab_property == "termiusSnippetRouteActiveTab"
    assert route.status_property == "termiusSnippetRouteState"
    assert route.captured_property == "termiusSnippetRouteCaptured"
    assert route.captured_command_property == "termiusSnippetRouteCapturedCommand"
    assert route.captured_target_profile_property == "termiusSnippetRouteCapturedTargetProfile"
    assert route.captured_status_property == "termiusSnippetRouteCapturedStatus"
    assert route.signal == "clicked"
    assert route.secondary_signal == "activated"
    assert route.handler == "handle_termius_snippet_run"
    assert route.signal_property == "termiusSnippetRouteSignal"
    assert route.secondary_signal_property == "termiusSnippetRouteSecondarySignal"
    assert route.handler_property == "termiusSnippetRouteHandler"
    assert route.live_triggered_property == "termiusSnippetRouteLiveTriggered"
    assert route.live_command_property == "termiusSnippetRouteLiveCommand"
    assert route.live_target_profile_property == "termiusSnippetRouteLiveTargetProfile"
    assert route.live_status_property == "termiusSnippetRouteLiveStatus"
    assert route.render_source == "state-model"
    assert any(
        card.key == route.workflow_card_key
        and card.title == route.workflow_title
        and card.primary == route.snippet_command
        and card.secondary == route.snippet_state
        for card in cards
    )
    assert any(field.key == route.identity_field_key and field.value == route.snippet_command for field in strip.fields)
    assert route.detail_line in surface.detail_lines
    assert route.to_dict()["snippet_command"] == route.snippet_command
    assert route.to_dict()["action_object"] == route.action_object
    assert route.to_dict()["handler"] == route.handler


def test_termius_files_browser_route_is_shared_metadata() -> None:
    route = gui_design_termius_files_browser_route()
    host_route = gui_design_termius_host_selection_route()
    strip = gui_design_termius_host_identity_strip()
    fields = {field.key: field for field in strip.fields}
    rows = {row.name: row for row in route.file_rows}

    assert route.key == "termius-files-browser-route"
    assert route.route_role == "host-files-tab-to-sftp-browser"
    assert route.host_selection_route_key == host_route.key
    assert route.host_identity_object == host_route.host_identity_object
    assert route.identity_field_key == "files"
    assert fields[route.identity_field_key].value == route.files_state == "SFTP ready"
    assert route.active_tab_label == host_route.active_tab_label == "edge-prod"
    assert route.selected_profile_name == host_route.selected_profile_name == "edge-prod"
    assert route.selected_tree_label == host_route.selected_tree_label
    assert route.remote_path == "/workspace"
    assert route.toolbar_actions == ("upload", "download", "sync")
    assert route.active_row_name == "deploy.yml"
    assert rows[route.active_row_name].selected is True
    assert route.transfer_queue_label == "sync idle"
    assert route.transfer_status == "ready"
    assert route.path_property == "termiusFilesRoutePath"
    assert route.queue_state_property == "termiusFilesRouteQueueState"
    assert route.action_object == "termiusFilesAction"
    assert route.action_key == "sync"
    assert route.action_label == "Sync"
    assert route.action_status == "synced"
    assert route.signal == "clicked"
    assert route.handler == "handle_termius_files_sync"
    assert route.signal_property == "termiusFilesRouteSignal"
    assert route.handler_property == "termiusFilesRouteHandler"
    assert route.captured_property == "termiusFilesRouteCaptured"
    assert route.captured_action_property == "termiusFilesRouteCapturedAction"
    assert route.captured_status_property == "termiusFilesRouteCapturedStatus"
    assert route.live_triggered_property == "termiusFilesRouteLiveTriggered"
    assert route.live_action_property == "termiusFilesRouteLiveAction"
    assert route.live_status_property == "termiusFilesRouteLiveStatus"
    assert route.to_dict()["toolbar_actions"] == ["upload", "download", "sync"]
    assert route.to_dict()["file_rows"][2]["name"] == route.active_row_name
    assert route.to_dict()["action_key"] == route.action_key
    assert route.to_dict()["handler"] == route.handler


def test_mremoteng_document_controls_are_shared_metadata() -> None:
    chrome = gui_design_mremoteng_document_toolbar_chrome()
    controls = gui_design_mremoteng_document_controls()

    assert chrome.title == "Connections.xml"
    assert chrome.filter_placeholder == "Filter connection tree"
    assert [control.key for control in controls] == ["save", "reconnect", "external-tool", "dock-view"]
    assert [control.icon_key for control in controls] == ["database", "ssh", "external", "rdp"]
    assert [control.label for control in controls] == ["Save", "Reconnect", "External tool", "Dock view"]
    assert all(control.tooltip for control in controls)
    assert [control.static_width for control in controls] == [56, 88, 104, 84]
    assert {control.static_y for control in controls} == {4}
    assert {control.static_height for control in controls} == {20}
    assert {control.static_icon_x for control in controls} == {8}
    assert {control.static_icon_y for control in controls} == {7}
    assert {control.static_icon_size for control in controls} == {13}
    assert {control.static_label_x for control in controls} == {27}
    assert {control.static_label_y for control in controls} == {8}
    assert [control.live_min_width for control in controls] == [56, 88, 104, 84]
    assert {control.live_icon_size for control in controls} == {14}
    assert {control.live_button_height for control in controls} == {26}
    assert {control.render_source for control in controls} == {"generated-pixmap"}
    assert chrome.title_width == 112
    assert chrome.static_height == 28
    assert chrome.static_button_start_x == 128
    assert chrome.static_button_gap == 8
    assert chrome.static_filter_width == 178
    assert chrome.live_filter_width == 178


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
        "import",
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
        "import-connections",
        "config",
        "delete",
        "open-connection",
    ]
    assert [action.label for action in chrome.toolbar_actions[:6]] == [
        "Refresh",
        "New Conn",
        "Import",
        "Config",
        "Delete",
        "Open",
    ]
    assert [action.static_width for action in chrome.toolbar_actions] == [
        58,
        74,
        62,
        62,
        58,
        54,
        74,
        70,
        58,
        54,
        58,
        58,
    ]
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


def test_mremoteng_connection_document_route_is_shared_metadata() -> None:
    route = gui_design_mremoteng_connection_document_route()
    controls = gui_design_mremoteng_document_controls()
    chrome = gui_design_mremoteng_property_grid_chrome()
    reference = gui_design_reference_state("mremoteng")

    assert route.key == "mremoteng-selected-connection-document-route"
    assert route.route_role == "connection-tree-to-document-workspace"
    assert route.selected_profile_name == "edge-prod"
    assert route.selected_tree_label == "edge-prod [SSH]"
    assert route.selected_tree_object == "profileTree"
    assert route.document_controls_object == "mRemoteNgDocumentControls"
    assert route.document_control_key == "reconnect"
    assert route.document_control_object == "mRemoteNgDocumentControl"
    assert route.property_grid_object == "mRemoteNgPropertyGrid"
    assert route.property_row_key == "protocol"
    assert route.property_cell_object == "mRemoteNgPropertyGridCell"
    assert route.active_tab_label == reference.active_tab_label == "edge-prod [SSH]"
    assert route.protocol == "SSH"
    assert route.workspace_state == reference.workspace_state == "document open"
    assert route.property_value == "SSH"
    assert route.selected_tree_property == "mRemoteNgConnectionRouteSelected"
    assert route.control_active_property == "mRemoteNgConnectionRouteActive"
    assert route.tab_label_property == "mRemoteNgConnectionRouteActiveTab"
    assert route.property_value_property == "mRemoteNgConnectionRoutePropertyValue"
    assert route.signal == "clicked"
    assert route.handler == "handle_mremoteng_document_reconnect"
    assert route.reconnect_state == "reconnected"
    assert route.signal_property == "mRemoteNgConnectionRouteSignal"
    assert route.handler_property == "mRemoteNgConnectionRouteHandler"
    assert route.captured_property == "mRemoteNgConnectionRouteCaptured"
    assert route.captured_state_property == "mRemoteNgConnectionRouteCapturedState"
    assert route.captured_profile_property == "mRemoteNgConnectionRouteCapturedProfile"
    assert route.live_triggered_property == "mRemoteNgConnectionRouteLiveTriggered"
    assert route.live_state_property == "mRemoteNgConnectionRouteLiveState"
    assert route.live_profile_property == "mRemoteNgConnectionRouteLiveProfile"
    assert route.render_source == "connection-tree-state"
    assert route.to_dict()["handler"] == "handle_mremoteng_document_reconnect"
    assert route.to_dict()["live_triggered_property"] == "mRemoteNgConnectionRouteLiveTriggered"
    assert any(control.key == route.document_control_key and control.label == "Reconnect" for control in controls)
    assert any(row.key == route.property_row_key and row.effective_value == route.property_value for row in chrome.rows)


def test_mremoteng_document_filter_route_is_shared_metadata() -> None:
    route = gui_design_mremoteng_document_filter_route()
    connection_route = gui_design_mremoteng_connection_document_route()
    chrome = gui_design_mremoteng_document_toolbar_chrome()

    assert route.key == "mremoteng-document-filter-route"
    assert route.route_role == "document-filter-to-selected-connection-row"
    assert route.document_controls_object == connection_route.document_controls_object
    assert route.filter_object == "mRemoteNgDocumentFilter"
    assert route.selected_tree_object == connection_route.selected_tree_object
    assert route.selected_profile_name == connection_route.selected_profile_name
    assert route.selected_tree_label == connection_route.selected_tree_label == "edge-prod [SSH]"
    assert route.matched_protocol == connection_route.protocol == "SSH"
    assert route.matched_state == connection_route.workspace_state == "document open"
    assert route.expected_query == "edge"
    assert route.expected_placeholder == chrome.filter_placeholder
    assert route.active_tab_label == connection_route.active_tab_label
    assert route.filter_route_property == "mRemoteNgDocumentFilterRouteKey"
    assert route.filter_query_property == "mRemoteNgDocumentFilterRouteQuery"
    assert route.filter_placeholder_property == "mRemoteNgDocumentFilterRoutePlaceholder"
    assert route.matched_tree_property == "mRemoteNgDocumentFilterRouteMatchedTreeLabel"
    assert route.matched_protocol_property == "mRemoteNgDocumentFilterRouteMatchedProtocol"
    assert route.active_tab_property == "mRemoteNgDocumentFilterRouteActiveTab"
    assert route.change_signal == "textChanged"
    assert route.handler_name == "filter_profile_tree"
    assert route.render_source == "connection-tree-filter-state"
    assert route.to_dict()["expected_query"] == "edge"


def test_mremoteng_document_filter_chrome_does_not_double_apply_layout_insets() -> None:
    stylesheet = get_gui_design_preset("mremoteng").stylesheet
    controls_block = stylesheet.split("QFrame#mRemoteNgDocumentControls {", 1)[1].split("}", 1)[0]

    assert "padding: 0px;" in controls_block


def test_mremoteng_inheritance_route_is_shared_metadata() -> None:
    route = gui_design_mremoteng_inheritance_route()
    connection_route = gui_design_mremoteng_connection_document_route()
    chrome = gui_design_mremoteng_property_grid_chrome()
    cards = gui_design_workflow_cards("mremoteng")

    assert route.key == "mremoteng-inheritance-route"
    assert route.route_role == "workflow-card-to-property-grid-inheritance"
    assert route.workflow_card_key == "inheritance-grid"
    assert route.workflow_card_object == "productWorkflowCard"
    assert route.workflow_title_object == "productWorkflowTitle"
    assert route.workflow_primary_object == "productWorkflowPrimary"
    assert route.workflow_secondary_object == "productWorkflowSecondary"
    assert route.property_grid_object == connection_route.property_grid_object == "mRemoteNgPropertyGrid"
    assert route.property_row_key == "credential"
    assert route.property_cell_object == connection_route.property_cell_object == "mRemoteNgPropertyGridCell"
    assert route.active_tab_label == connection_route.active_tab_label == "edge-prod [SSH]"
    assert route.selected_profile_name == connection_route.selected_profile_name == "edge-prod"
    assert route.selected_tree_label == connection_route.selected_tree_label == "edge-prod [SSH]"
    assert route.workflow_title == "Config inheritance"
    assert route.inherited_property_label == "Credential"
    assert route.inherited_value == "operator key reference"
    assert route.inherited_source == "Connections.xml/prod"
    assert route.inheritance_state == "credentials inherited"
    assert route.workflow_key_property == "mRemoteNgInheritanceRouteWorkflowKey"
    assert route.inherited_value_property == "mRemoteNgInheritanceRouteInheritedValue"
    assert route.active_tab_property == "mRemoteNgInheritanceRouteActiveTab"
    assert route.status_property == "mRemoteNgInheritanceRouteState"
    assert route.render_source == "property-grid-state"
    assert any(
        card.key == route.workflow_card_key
        and card.title == route.workflow_title
        and card.primary == route.inheritance_state
        and card.secondary == "property grid visible"
        for card in cards
    )
    assert any(
        row.key == route.property_row_key
        and row.property_label == route.inherited_property_label
        and row.effective_value == route.inherited_value
        and row.source == route.inherited_source
        and row.inherited
        for row in chrome.rows
    )
    assert route.to_dict()["inherited_value"] == route.inherited_value


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
        route = gui_design_product_identity_route(preset_id)

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
        assert route.key == f"{preset_id}-product-identity-route"
        assert route.route_role == "tree-tab-reference-status-workspace-identity"
        assert route.selected_profile_name == profile
        assert route.active_tab_label == tab
        assert route.sidebar_label == sidebar
        assert route.status_segments == reference.status_segments
        assert route.reference_state_object == "productReferenceState"
        assert route.reference_item_object == "productReferenceStateItem"
        assert route.tree_object == "profileTree"
        assert route.tabs_object == "sessionTabs"
        assert route.status_segment_object == "productStatusSegment"
        assert route.workspace_surface_object == "productWorkspaceSurface"
        assert route.active_tab_property == "productIdentityActiveTab"
        assert route.status_segments_property == "productIdentityStatusSegments"
    assert gui_design_product_identity_route("securecrt").selected_tree_label == "edge-prod (SSH2)"
    assert gui_design_product_identity_route("termius").selected_tree_label == "edge-prod  ssh host"
    assert gui_design_product_identity_route("remmina").selected_tree_label == "RDP - win-admin"
    assert gui_design_product_identity_route("mremoteng").selected_tree_label == "edge-prod [SSH]"


def test_gui_design_preset_reference_tab_routes_are_shared_metadata() -> None:
    assert PRODUCT_REFERENCE_TAB_PRESET_IDS == ("securecrt", "termius", "remmina", "mremoteng")

    for preset_id in PRODUCT_REFERENCE_TAB_PRESET_IDS:
        route = gui_design_preset_reference_tab_route(preset_id)
        identity_route = gui_design_product_identity_route(preset_id)

        assert route.key == f"{preset_id}-reference-tab-activation-route"
        assert route.route_role == "reference-profile-tab-can-be-active-surface"
        assert route.preset_id == preset_id
        assert route.reference_profile == identity_route.selected_profile_name
        assert route.active_tab_label == identity_route.active_tab_label
        assert route.home_tab_label == gui_design_home_tab_label(preset_id)
        assert route.tabs_object == "sessionTabs"
        assert route.home_tab_role == "home"
        assert route.reference_tab_role == "terminal"
        assert route.activated_label_property == "presetReferenceTabActivatedLabel"
        assert route.returned_home_label_property == "presetReferenceTabReturnedHomeLabel"
        assert route.active_tab_property == "presetReferenceTabActiveLabel"
        assert route.home_tab_property == "presetReferenceTabHomeLabel"
        assert route.reference_profile_property == "presetReferenceTabProfile"
        assert route.render_source == "gui-design-reference-tab-route"

    assert gui_design_preset_reference_tab_route("securecrt").active_tab_label == "edge-prod (SSH2)"
    assert gui_design_preset_reference_tab_route("termius").active_tab_label == "edge-prod"
    assert gui_design_preset_reference_tab_route("remmina").reference_profile == "win-admin"
    assert gui_design_preset_reference_tab_route("mremoteng").home_tab_label == "Start Page"


def test_gui_design_preset_keyboard_shortcut_routes_are_shared_metadata() -> None:
    assert PRODUCT_GUI_PRESET_IDS == ("mobaxterm", "securecrt", "termius", "remmina", "mremoteng")

    for preset_id in PRODUCT_GUI_PRESET_IDS:
        route = gui_design_preset_keyboard_shortcut_route(preset_id)

        assert route.key == f"{preset_id}-keyboard-shortcut-route"
        assert route.route_role == "product-preset-keyboard-shortcuts"
        assert route.preset_id == preset_id
        assert route.shortcut_object == "presetKeyboardShortcut"
        assert route.expected_shortcut_keys == (
            "refresh-profiles",
            "new-profile",
            "edit-profile",
            "connect-selected",
            "new-local-terminal",
            "close-current-tab",
            "recover-previous-sessions",
            "split-horizontal",
            "split-vertical",
            "open-selected-layout",
            "find-log-text",
        )
        assert route.expected_sequences == (
            "Ctrl+R",
            "Ctrl+N",
            "Ctrl+E",
            "Ctrl+Return",
            "Ctrl+T",
            "Ctrl+W",
            "Ctrl+Shift+T",
            "Ctrl+Shift+H",
            "Ctrl+Shift+V",
            "Ctrl+L",
            "Ctrl+F",
        )
        assert route.expected_action_labels == (
            "Refresh profiles",
            "New profile",
            "Edit selected profile",
            "Connect selected profile",
            "New local terminal",
            "Close current tab",
            "Recover previous sessions",
            "Split horizontal",
            "Split vertical",
            "Open selected layout",
            "Find log text",
        )
        assert route.expected_shortcut_count == 11
        assert route.shortcut_key_property == "presetKeyboardShortcutKey"
        assert route.shortcut_sequence_property == "presetKeyboardShortcutSequence"
        assert route.shortcut_action_property == "presetKeyboardShortcutActionLabel"
        assert route.captured_property == "presetKeyboardShortcutsCaptured"
        assert route.captured_keys_property == "presetKeyboardShortcutCapturedKeys"
        assert route.captured_sequences_property == "presetKeyboardShortcutCapturedSequences"
        assert route.captured_action_labels_property == "presetKeyboardShortcutCapturedActionLabels"
        assert route.captured_count_property == "presetKeyboardShortcutCapturedCount"
        assert route.render_source == "gui-design-keyboard-shortcuts"

    assert "Ctrl+T" in gui_design_preset_keyboard_shortcut_route("mobaxterm").expected_sequences
    assert "Ctrl+Shift+T" in gui_design_preset_keyboard_shortcut_route("securecrt").expected_sequences


def test_gui_design_preset_command_surface_routes_are_shared_metadata() -> None:
    expected_objects = {
        "mobaxterm": ("mobaRibbonButton", 12, "sessions", ""),
        "securecrt": ("productToolbarButton", 12, "connect", ""),
        "termius": ("productToolbarButton", 12, "connect", ""),
        "remmina": ("productToolbarButton", 12, "connect", ""),
        "mremoteng": ("productToolbarButton", 12, "connect", ""),
    }

    for preset_id in PRODUCT_GUI_PRESET_IDS:
        route = gui_design_preset_command_surface_route(preset_id)
        state = gui_design_interaction_state(preset_id)
        actions = gui_design_command_surface_actions(preset_id)
        command_object, expected_count, active_key, disabled_key = expected_objects[preset_id]

        assert route.key == f"{preset_id}-command-surface-route"
        assert route.route_role == "product-preset-command-surface-route"
        assert route.preset_id == preset_id
        assert route.toolbar_object == "mainToolbar"
        assert route.command_object == command_object
        assert route.expected_action_keys == tuple(key for key, _label, _tooltip in actions)
        assert route.expected_action_labels == tuple(label for _key, label, _tooltip in actions)
        assert route.expected_action_tooltips == tuple(tooltip for _key, _label, tooltip in actions)
        assert route.expected_action_count == expected_count == len(actions)
        states = dict(route.expected_action_states)
        assert states[active_key] == "active"
        if disabled_key:
            assert states[disabled_key] == "disabled"
        else:
            assert "disabled" not in states.values()
        if state.checked_toolbar_key in states:
            assert states[state.checked_toolbar_key] == "checked"
        assert route.key_property == "presetCommandSurfaceActionKey"
        assert route.label_property == "presetCommandSurfaceActionLabel"
        assert route.tooltip_property == "presetCommandSurfaceActionTooltip"
        assert route.state_property == "interactionState"
        assert route.captured_property == "presetCommandSurfaceCaptured"
        assert route.captured_keys_property == "presetCommandSurfaceCapturedKeys"
        assert route.captured_labels_property == "presetCommandSurfaceCapturedLabels"
        assert route.captured_tooltips_property == "presetCommandSurfaceCapturedTooltips"
        assert route.captured_states_property == "presetCommandSurfaceCapturedStates"
        assert route.captured_count_property == "presetCommandSurfaceCapturedCount"
        assert route.render_source == "gui-design-command-surface-route"

    moba_tooltips = gui_design_moba_ribbon_tooltips()
    assert gui_design_command_surface_actions("mobaxterm")[0] == (
        "session",
        "Session",
        moba_tooltips["session"],
    )
    assert gui_design_command_surface_actions("securecrt") == gui_design_toolbar_actions("securecrt")


def test_gui_design_preset_focus_interaction_routes_are_shared_metadata() -> None:
    expected_focus_objects = {
        "mobaxterm": ("quick-connect", "quickConnect", "sessions", "sftp", ""),
        "securecrt": ("session-filter", "secureCrtSessionFilter", "connect", "files", ""),
        "termius": ("host-search", "termiusHostSearch", "connect", "doctor", ""),
        "remmina": ("profile-filter", "remminaProfileFilter", "connect", "queue", ""),
        "mremoteng": ("tree-filter", "mRemoteNgDocumentFilter", "connect", "files", ""),
    }

    for preset_id in PRODUCT_GUI_PRESET_IDS:
        route = gui_design_preset_focus_interaction_route(preset_id)
        state = gui_design_interaction_state(preset_id)
        focused_control, focus_object, active_key, checked_key, disabled_key = expected_focus_objects[preset_id]

        assert route.key == f"{preset_id}-focus-interaction-route"
        assert route.route_role == "product-preset-focus-interaction-route"
        assert route.preset_id == preset_id
        assert route.focused_control == focused_control == state.focused_control
        assert route.focus_object == focus_object
        assert route.active_toolbar_key == active_key == state.active_toolbar_key
        assert route.checked_toolbar_key == checked_key == state.checked_toolbar_key
        assert route.disabled_toolbar_key == disabled_key == state.disabled_toolbar_key
        assert route.selected_tree_label == state.selected_tree_label
        assert route.active_tab_status == state.active_tab_status
        assert route.status_note == state.status_note
        assert route.status_bar_object == "statusBar"
        assert route.profile_tree_object == "profileTree"
        assert route.focused_state_property == "interactionState"
        assert route.captured_property == "presetFocusInteractionCaptured"
        assert route.captured_focus_property == "presetFocusInteractionCapturedFocus"
        assert route.captured_focus_state_property == "presetFocusInteractionCapturedState"
        assert route.captured_status_message_property == "presetFocusInteractionStatusMessage"
        assert route.captured_selected_tree_property == "presetFocusInteractionCapturedSelectedTreeLabel"
        assert route.captured_toolbar_states_property == "presetFocusInteractionToolbarStates"
        assert route.render_source == "gui-design-focus-interaction-route"

    assert gui_design_preset_focus_interaction_route("mobaxterm").status_note.startswith("quick connect")
    assert gui_design_preset_focus_interaction_route("mremoteng").focus_object == "mRemoteNgDocumentFilter"


def test_gui_design_preset_home_search_routes_are_shared_metadata() -> None:
    expected_entry = {
        "mobaxterm": (
            "quick-connect",
            "quickConnect",
            "mobaHomeWelcomeSurface",
            "mobaRecentSession",
            "Quick connect...",
        ),
        "securecrt": ("session-filter", "secureCrtSessionFilter", "welcomePanel", "recentSessionsLabel", "Filter sessions"),
        "termius": ("host-search", "termiusHostSearch", "welcomePanel", "recentSessionsLabel", "Search hosts"),
        "remmina": (
            "profile-filter",
            "remminaProfileFilter",
            "welcomePanel",
            "recentSessionsLabel",
            "Filter by name or protocol",
        ),
        "mremoteng": (
            "tree-filter",
            "mRemoteNgDocumentFilter",
            "welcomePanel",
            "recentSessionsLabel",
            "Filter connection tree",
        ),
    }

    for preset_id in PRODUCT_GUI_PRESET_IDS:
        route = gui_design_preset_home_search_route(preset_id)
        surface = gui_design_workspace_surface(preset_id)
        focused_control, entry_object, container, recent_object, entry_placeholder = expected_entry[preset_id]

        assert route.key == f"{preset_id}-home-search-route"
        assert route.route_role == "product-preset-home-search-entry-route"
        assert route.preset_id == preset_id
        assert route.home_search_object == "homeSearch"
        assert route.entry_search_control == focused_control
        assert route.entry_search_object == entry_object
        assert route.container_object == container
        assert route.recent_label_object == recent_object
        assert route.placeholder_text == surface.home_search_placeholder
        assert route.entry_placeholder_text == entry_placeholder
        assert route.expected_home_actions == surface.home_actions
        assert route.expected_recent_labels == tuple(item for column in surface.recent_columns for item in column)
        assert route.expected_recent_count == len(route.expected_recent_labels)
        assert route.placeholder_property == "presetHomeSearchPlaceholder"
        assert route.entry_placeholder_property == "presetHomeSearchEntryPlaceholder"
        assert route.captured_property == "presetHomeSearchCaptured"
        assert route.captured_placeholder_property == "presetHomeSearchCapturedPlaceholder"
        assert route.captured_entry_placeholder_property == "presetHomeSearchCapturedEntryPlaceholder"
        assert route.captured_recent_labels_property == "presetHomeSearchCapturedRecentLabels"
        assert route.render_source == "gui-design-home-search-route"

    assert gui_design_preset_home_search_route("mobaxterm").placeholder_text == "Find existing session or server name..."
    assert gui_design_preset_home_search_route("securecrt").entry_placeholder_text == "Filter sessions"


def test_gui_design_preset_reference_tab_chrome_routes_are_shared_metadata() -> None:
    for preset_id in PRODUCT_REFERENCE_TAB_PRESET_IDS:
        route = gui_design_preset_reference_tab_chrome_route(preset_id)
        tab_route = gui_design_preset_reference_tab_route(preset_id)
        preset = get_gui_design_preset(preset_id)

        assert route.key == f"{preset_id}-reference-tab-chrome-evidence-route"
        assert route.route_role == "active-reference-tab-chrome-evidence"
        assert route.preset_id == preset_id
        assert route.reference_profile == tab_route.reference_profile
        assert route.active_tab_label == tab_route.active_tab_label
        assert route.home_tab_label == tab_route.home_tab_label
        assert route.tabs_object == "sessionTabs"
        assert route.tab_bar_object == "sessionTabBar"
        assert route.reference_tab_role == "terminal"
        assert route.new_session_tab_role == "new-session"
        assert route.expected_tab_position == preset.tab_position
        assert route.expected_tooltip.startswith(f"{tab_route.active_tab_label}: ")
        assert route.expected_closeable is True
        assert route.expected_selected_during_capture is True
        assert route.captured_property == "presetReferenceTabChromeCaptured"
        assert route.captured_label_property == "presetReferenceTabChromeLabel"
        assert route.captured_tooltip_property == "presetReferenceTabChromeTooltip"
        assert route.captured_index_property == "presetReferenceTabChromeIndex"
        assert route.captured_role_property == "presetReferenceTabChromeRole"
        assert route.captured_position_property == "presetReferenceTabChromePosition"
        assert route.captured_closeable_property == "presetReferenceTabChromeCloseable"
        assert route.captured_selected_property == "presetReferenceTabChromeSelected"
        assert route.render_source == "gui-design-reference-tab-chrome"

    assert gui_design_preset_reference_tab_chrome_route("securecrt").expected_tooltip.endswith("SSH2 connected")
    assert gui_design_preset_reference_tab_chrome_route("termius").expected_tab_position == "west"


def test_gui_design_preset_reference_status_bar_routes_are_shared_metadata() -> None:
    for preset_id in PRODUCT_REFERENCE_TAB_PRESET_IDS:
        route = gui_design_preset_reference_status_bar_route(preset_id)
        tab_route = gui_design_preset_reference_tab_route(preset_id)
        identity_route = gui_design_product_identity_route(preset_id)

        assert route.key == f"{preset_id}-reference-status-bar-evidence-route"
        assert route.route_role == "active-reference-status-bar-evidence"
        assert route.preset_id == preset_id
        assert route.reference_profile == tab_route.reference_profile
        assert route.active_tab_label == tab_route.active_tab_label
        assert route.status_bar_object == "statusBar"
        assert route.status_notice_object == "productStatusNotice"
        assert route.status_segment_object == "productStatusSegment"
        expected_message = "Running process panes: 2" if preset_id == "remmina" else "Running process panes: 1"
        assert route.expected_status_message == expected_message
        assert route.expected_status_segments == identity_route.status_segments
        assert route.expected_segment_count == len(identity_route.status_segments)
        assert route.captured_property == "presetReferenceStatusCaptured"
        assert route.captured_tab_property == "presetReferenceStatusCapturedTab"
        assert route.captured_message_property == "presetReferenceStatusMessage"
        assert route.captured_segments_property == "presetReferenceStatusSegments"
        assert route.captured_segment_count_property == "presetReferenceStatusSegmentCount"
        assert route.captured_segment_tooltips_property == "presetReferenceStatusSegmentTooltips"
        assert route.captured_notice_property == "presetReferenceStatusNotice"
        assert route.render_source == "gui-design-reference-status-bar"

    assert "Session Manager" in gui_design_preset_reference_status_bar_route("securecrt").expected_status_segments
    assert "Clipboard on" in gui_design_preset_reference_status_bar_route("remmina").expected_status_segments


def test_gui_design_preset_reference_session_action_routes_are_shared_metadata() -> None:
    for preset_id in PRODUCT_REFERENCE_TAB_PRESET_IDS:
        route = gui_design_preset_reference_session_action_route(preset_id)
        tab_route = gui_design_preset_reference_tab_route(preset_id)

        assert route.key == f"{preset_id}-reference-session-actions-route"
        assert route.route_role == "active-reference-session-actions"
        assert route.preset_id == preset_id
        assert route.reference_profile == tab_route.reference_profile
        assert route.active_tab_label == tab_route.active_tab_label
        assert route.tabs_object == "sessionTabs"
        assert route.tab_bar_object == "sessionTabBar"
        assert route.reference_tab_role == "terminal"
        assert route.action_object == "sessionTabContextAction"
        assert route.expected_action_keys == (
            "new-local-terminal",
            "split-horizontal",
            "split-vertical",
            "duplicate-tab",
            "close-tab",
            "close-other-tabs",
            "recover-previous-sessions",
        )
        assert route.expected_action_labels == (
            "New local terminal",
            "Split horizontal",
            "Split vertical",
            "Duplicate tab",
            "Close tab",
            "Close other tabs",
            "Recover previous sessions",
        )
        assert route.expected_action_count == len(route.expected_action_keys)
        assert route.always_enabled_action_keys == tuple(
            key for key in route.expected_action_keys if key != "close-other-tabs"
        )
        assert route.conditional_enabled_action_keys == ("close-other-tabs",)
        assert route.action_key_property == "sessionTabContextActionKey"
        assert route.action_label_property == "sessionTabContextActionLabel"
        assert route.action_enabled_property == "sessionTabContextActionEnabled"
        assert route.captured_property == "presetReferenceSessionActionsCaptured"
        assert route.captured_tab_property == "presetReferenceSessionActionsCapturedTab"
        assert route.captured_action_keys_property == "presetReferenceSessionActionKeys"
        assert route.captured_action_labels_property == "presetReferenceSessionActionLabels"
        assert route.captured_action_count_property == "presetReferenceSessionActionCount"
        assert route.captured_enabled_keys_property == "presetReferenceSessionActionEnabledKeys"
        assert route.captured_disabled_keys_property == "presetReferenceSessionActionDisabledKeys"
        assert route.render_source == "gui-design-reference-session-actions"

    assert "close-other-tabs" in gui_design_preset_reference_session_action_route("securecrt").expected_action_keys
    assert "recover-previous-sessions" in gui_design_preset_reference_session_action_route("termius").expected_action_keys


def test_gui_design_preset_reference_surface_routes_are_shared_metadata() -> None:
    for preset_id in PRODUCT_REFERENCE_TAB_PRESET_IDS:
        route = gui_design_preset_reference_surface_route(preset_id)
        tab_route = gui_design_preset_reference_tab_route(preset_id)
        identity_route = gui_design_product_identity_route(preset_id)

        assert route.key == f"{preset_id}-reference-surface-evidence-route"
        assert route.route_role == "active-reference-tab-surface-evidence"
        assert route.preset_id == preset_id
        assert route.reference_profile == tab_route.reference_profile
        assert route.active_tab_label == tab_route.active_tab_label
        assert route.expected_title == tab_route.reference_profile
        assert route.expected_source == f"profile:{tab_route.reference_profile}"
        assert route.command_target_fragment in identity_route.target_label
        assert route.terminal_pane_object == "terminalPane"
        assert route.terminal_title_object == "terminalTitle"
        assert route.terminal_source_object == "terminalSource"
        assert route.terminal_command_object == "terminalCommand"
        assert route.terminal_output_object == "terminalOutput"
        assert route.captured_property == "presetReferenceSurfaceCaptured"
        assert route.captured_tab_property == "presetReferenceSurfaceCapturedTab"
        assert route.actual_command_property == "presetReferenceSurfaceActualCommand"
        assert route.actual_output_property == "presetReferenceSurfaceActualOutput"
        assert route.render_source == "gui-design-reference-surface"

    assert gui_design_preset_reference_surface_route("securecrt").command_executables == ("ssh",)
    assert gui_design_preset_reference_surface_route("termius").command_target_fragment == "edge-prod.example.invalid"
    assert gui_design_preset_reference_surface_route("remmina").command_executables == (
        "mstsc",
        "xfreerdp",
        "wlfreerdp",
    )
    assert gui_design_preset_reference_surface_route("mremoteng").expected_title == "edge-prod"


def test_gui_design_preset_reference_control_routes_are_shared_metadata() -> None:
    for preset_id in PRODUCT_REFERENCE_TAB_PRESET_IDS:
        route = gui_design_preset_reference_control_route(preset_id)
        surface_route = gui_design_preset_reference_surface_route(preset_id)

        assert route.key == f"{preset_id}-reference-control-evidence-route"
        assert route.route_role == "active-reference-tab-terminal-controls"
        assert route.preset_id == preset_id
        assert route.reference_profile == surface_route.reference_profile
        assert route.active_tab_label == surface_route.active_tab_label
        assert route.terminal_pane_object == "terminalPane"
        assert route.terminal_status_object == "paneStatus"
        assert route.terminal_action_object == "terminalAction"
        assert route.action_keys == (
            "start",
            "restart",
            "stop",
            "copy",
            "clear",
            "macro-rec",
            "macro-stop",
            "macro-cancel",
            "macro-replay",
        )
        assert route.action_labels == (
            "Start",
            "Restart",
            "Stop",
            "Copy",
            "Clear",
            "Macro Rec",
            "Macro Stop",
            "Macro Cancel",
            "Macro Replay",
        )
        assert route.action_tooltips == (
            "Start process",
            "Restart process",
            "Stop process",
            "Copy selected terminal output, or the launch command when nothing is selected",
            "Clear terminal output",
            "Record terminal macro",
            "Stop terminal macro",
            "Cancel macro",
            "Replay terminal macro",
        )
        assert route.allowed_status_states == (
            "ready",
            "starting",
            "running",
            "stopping",
            "error",
            "blocked",
        )
        assert route.action_key_property == "terminalActionKey"
        assert route.action_label_property == "terminalActionLabel"
        assert route.action_tooltip_property == "terminalActionTooltip"
        assert route.status_state_property == "state"
        assert route.captured_property == "presetReferenceControlsCaptured"
        assert route.captured_actions_property == "presetReferenceControlCapturedActionKeys"
        assert route.captured_status_property == "presetReferenceControlStatusState"
        assert route.captured_status_text_property == "presetReferenceControlStatusText"
        assert route.render_source == "gui-design-reference-controls"

    assert gui_design_preset_reference_control_route("securecrt").reference_profile == "edge-prod"
    assert gui_design_preset_reference_control_route("remmina").active_tab_label == "RDP - win-admin"


def test_gui_design_preset_reference_input_routes_are_shared_metadata() -> None:
    for preset_id in PRODUCT_REFERENCE_TAB_PRESET_IDS:
        route = gui_design_preset_reference_input_route(preset_id)
        surface_route = gui_design_preset_reference_surface_route(preset_id)

        assert route.key == f"{preset_id}-reference-input-evidence-route"
        assert route.route_role == "active-reference-tab-terminal-input"
        assert route.preset_id == preset_id
        assert route.reference_profile == surface_route.reference_profile
        assert route.active_tab_label == surface_route.active_tab_label
        assert route.terminal_pane_object == "terminalPane"
        assert route.terminal_input_object == "terminalInput"
        assert route.placeholder_text == "stdin, shell command or interactive input"
        assert route.expected_initial_text == ""
        assert route.allowed_enabled_states == (True, False)
        assert route.captured_property == "presetReferenceInputCaptured"
        assert route.captured_tab_property == "presetReferenceInputCapturedTab"
        assert route.captured_placeholder_property == "presetReferenceInputPlaceholder"
        assert route.captured_text_property == "presetReferenceInputText"
        assert route.captured_enabled_property == "presetReferenceInputEnabled"
        assert route.render_source == "gui-design-reference-input"

    assert gui_design_preset_reference_input_route("termius").active_tab_label == "edge-prod"
    assert gui_design_preset_reference_input_route("mremoteng").reference_profile == "edge-prod"


def test_gui_design_preset_reference_transcript_routes_are_shared_metadata() -> None:
    for preset_id in PRODUCT_REFERENCE_TAB_PRESET_IDS:
        route = gui_design_preset_reference_transcript_route(preset_id)
        surface_route = gui_design_preset_reference_surface_route(preset_id)

        assert route.key == f"{preset_id}-reference-transcript-evidence-route"
        assert route.route_role == "active-reference-tab-terminal-transcript"
        assert route.preset_id == preset_id
        assert route.reference_profile == surface_route.reference_profile
        assert route.active_tab_label == surface_route.active_tab_label
        assert route.terminal_pane_object == "terminalPane"
        assert route.terminal_output_object == "terminalOutput"
        assert route.command_echo_prefix == "$ "
        assert route.required_fragments == (surface_route.command_target_fragment,)
        assert route.minimum_line_count == 1
        assert route.captured_property == "presetReferenceTranscriptCaptured"
        assert route.captured_tab_property == "presetReferenceTranscriptCapturedTab"
        assert route.captured_text_property == "presetReferenceTranscriptText"
        assert route.captured_line_count_property == "presetReferenceTranscriptLineCount"
        assert route.captured_command_echo_property == "presetReferenceTranscriptCommandEcho"
        assert route.render_source == "gui-design-reference-transcript"

    assert gui_design_preset_reference_transcript_route("securecrt").required_fragments == (
        "edge-prod.example.invalid",
    )
    assert gui_design_preset_reference_transcript_route("remmina").required_fragments == (
        "admin-win.example.invalid",
    )


def test_gui_design_preset_catalog_route_tracks_selector_options() -> None:
    route = gui_design_preset_catalog_route()
    product_presets = tuple(preset for preset in GUI_DESIGN_PRESETS if preset.id != DEFAULT_GUI_DESIGN_ID)

    assert route.key == "gui-preset-selector-catalog-route"
    assert route.route_role == "preset-catalog-to-design-selector-options"
    assert route.selector_object == "designSelect"
    assert route.option_ids == tuple(gui_design_preset_ids())
    assert route.option_labels == tuple(gui_design_preset_labels())
    assert route.product_preset_ids == tuple(preset.id for preset in product_presets)
    assert route.product_preset_labels == tuple(preset.label for preset in product_presets)
    assert route.default_preset_id == DEFAULT_GUI_DESIGN_ID
    assert route.default_preset_label == get_gui_design_preset(DEFAULT_GUI_DESIGN_ID).label
    assert route.option_count == len(GUI_DESIGN_PRESETS)
    assert route.product_option_count == len(product_presets)
    assert route.selector_property == "presetCatalogRouteOptionIds"
    assert route.option_labels_property == "presetCatalogRouteOptionLabels"
    assert route.product_ids_property == "presetCatalogRouteProductPresetIds"
    assert route.default_property == "presetCatalogRouteDefaultPresetId"
    assert route.render_source == "gui-design-preset-catalog"


def test_gui_design_preset_isolation_routes_are_shared_metadata() -> None:
    for preset in GUI_DESIGN_PRESETS:
        route = gui_design_preset_isolation_route(preset.id)

        assert route.key == f"{preset.id}-preset-isolation-route"
        assert route.route_role == "active-preset-visible-hidden-widget-isolation"
        assert route.preset_id == preset.id
        assert route.visible_objects
        assert "mainToolbar" in route.visible_objects
        assert "sessionTabs" in route.visible_objects
        assert not (set(route.visible_objects) & set(route.hidden_objects))
        assert route.visible_property == "presetIsolationVisibleObjects"
        assert route.hidden_property == "presetIsolationHiddenObjects"
        assert route.render_source == "gui-design-preset-visibility"

    assert "mobaQuickConnectChrome" in gui_design_preset_isolation_route("mobaxterm").visible_objects
    assert "layoutToolbar" in gui_design_preset_isolation_route("mobaxterm").hidden_objects
    assert "mobaRail" in gui_design_preset_isolation_route("securecrt").hidden_objects
    assert "secureCrtSessionManagerChrome" in gui_design_preset_isolation_route("securecrt").visible_objects
    assert "termiusHostsChrome" in gui_design_preset_isolation_route("termius").visible_objects
    assert "remminaProfileListChrome" in gui_design_preset_isolation_route("remmina").visible_objects
    assert "mRemoteNgPropertyGrid" in gui_design_preset_isolation_route("mremoteng").visible_objects


def test_gui_design_preset_transition_routes_are_shared_metadata() -> None:
    ids = gui_design_preset_ids()

    for preset in GUI_DESIGN_PRESETS:
        route = gui_design_preset_transition_route(preset.id)
        isolation_route = gui_design_preset_isolation_route(preset.id)

        assert route.key == f"{preset.id}-preset-transition-route"
        assert route.route_role == "selector-style-switch-resets-inactive-product-chrome"
        assert route.to_preset_id == preset.id
        assert route.to_preset_index == ids.index(preset.id)
        assert route.selector_object == "designSelect"
        assert route.from_preset_ids == tuple(source_id for source_id in ids if source_id != preset.id)
        assert preset.id not in route.from_preset_ids
        assert set(route.reset_objects) == set(isolation_route.hidden_objects)
        assert route.route_property == "presetTransitionRouteKey"
        assert route.from_property == "presetTransitionFromPresetIds"
        assert route.to_property == "presetTransitionToPresetId"
        assert route.reset_property == "presetTransitionResetObjects"
        assert route.render_source == "gui-design-preset-transition"

    assert "native" in gui_design_preset_transition_route("mobaxterm").from_preset_ids
    assert "mobaRail" in gui_design_preset_transition_route("securecrt").reset_objects
    assert "secureCrtMenuBar" in gui_design_preset_transition_route("termius").reset_objects
    assert "termiusHostsChrome" in gui_design_preset_transition_route("remmina").reset_objects
    assert "remminaProfileListChrome" in gui_design_preset_transition_route("mremoteng").reset_objects


def test_gui_design_preset_selection_routes_are_shared_metadata() -> None:
    ids = gui_design_preset_ids()

    for preset in GUI_DESIGN_PRESETS:
        route = gui_design_preset_selection_route(preset.id)

        assert route.key == f"{preset.id}-preset-selection-route"
        assert route.route_role == "selector-to-toolbar-sidebar-tabs-status-workspace"
        assert route.preset_id == preset.id
        assert route.preset_label == preset.label
        assert route.preset_index == ids.index(preset.id)
        assert route.selector_object == "designSelect"
        assert route.main_toolbar_object == "mainToolbar"
        assert route.layout_toolbar_object == "layoutToolbar"
        assert route.left_panel_header_object == "leftPanelHeader"
        assert route.profile_tree_object == "profileTree"
        assert route.tabs_object == "sessionTabs"
        assert route.status_bar_object == "statusBar"
        assert route.status_segment_object == "productStatusSegment"
        assert route.workspace_surface_object == "productWorkspaceSurface"
        assert route.reference_state_object == "productReferenceState"
        assert route.home_tab_label == gui_design_home_tab_label(preset.id)
        assert route.sidebar_title
        assert route.status_segments == gui_design_status_segments(preset.id)
        assert route.tab_position == preset.tab_position
        assert route.document_mode is preset.document_mode
        assert route.profile_width == preset.profile_width
        assert route.log_height == preset.log_height
        assert route.toolbar_icon_size == preset.toolbar_icon_size
        assert route.selector_property == "presetSelectionRoutePresetId"
        assert route.preset_label_property == "presetSelectionRoutePresetLabel"
        assert route.home_tab_property == "presetSelectionRouteHomeTabLabel"
        assert route.sidebar_title_property == "presetSelectionRouteSidebarTitle"
        assert route.status_segments_property == "presetSelectionRouteStatusSegments"
        assert route.render_source == "gui-design-preset-metadata"


def test_gui_design_preset_visual_signatures_are_shared_metadata() -> None:
    for preset in GUI_DESIGN_PRESETS:
        signature = gui_design_preset_visual_signature(preset.id)

        assert signature.key == f"{preset.id}-visual-signature"
        assert signature.route_role == "preset-palette-density-to-live-static-style"
        assert signature.preset_id == preset.id
        assert signature.preset_label == preset.label
        assert signature.density == preset.density
        assert signature.tab_position == preset.tab_position
        assert signature.document_mode is preset.document_mode
        assert signature.profile_width == preset.profile_width
        assert signature.log_height == preset.log_height
        assert signature.toolbar_icon_size == preset.toolbar_icon_size
        assert signature.list_spacing == preset.list_spacing
        assert dict(signature.palette_items()) == {
            "window": preset.colors.window,
            "toolbar": preset.colors.toolbar,
            "toolbar_border": preset.colors.toolbar_border,
            "control": preset.colors.control,
            "control_text": preset.colors.control_text,
            "primary": preset.colors.primary,
            "sidebar": preset.colors.sidebar,
            "sidebar_selected": preset.colors.sidebar_selected,
            "pane": preset.colors.pane,
            "pane_border": preset.colors.pane_border,
            "tab": preset.colors.tab,
            "tab_selected": preset.colors.tab_selected,
            "terminal": preset.colors.terminal,
            "terminal_text": preset.colors.terminal_text,
            "terminal_accent": preset.colors.terminal_accent,
            "status": preset.colors.status,
        }
        assert signature.window_object == "remoteOpsMain"
        assert signature.main_toolbar_object == "mainToolbar"
        assert signature.layout_toolbar_object == "layoutToolbar"
        assert signature.left_panel_object == "leftPanel"
        assert signature.profile_tree_object == "profileTree"
        assert signature.tabs_object == "sessionTabs"
        assert signature.activity_log_object == "activityLog"
        assert signature.status_bar_object == "statusBar"
        assert signature.density_property == "presetVisualSignatureDensity"
        assert signature.palette_property == "presetVisualSignaturePalette"
        assert signature.render_source == "gui-design-preset-style"


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

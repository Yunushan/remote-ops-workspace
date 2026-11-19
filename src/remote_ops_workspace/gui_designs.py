from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from importlib.resources import files
from string import Template

# Re-export the preset definitions through the shared design API.
# isort: off
from .gui_preset_mobaxterm import (
    GUI_DESIGN_MOBA_BOTTOM_EDGE_CONTROLS as GUI_DESIGN_MOBA_BOTTOM_EDGE_CONTROLS,
    GUI_DESIGN_MOBA_CONNECTED_DOCK_FRAME as GUI_DESIGN_MOBA_CONNECTED_DOCK_FRAME,
    GUI_DESIGN_MOBA_FOLLOW_TERMINAL_FOLDER_CONTROL_ROUTE as GUI_DESIGN_MOBA_FOLLOW_TERMINAL_FOLDER_CONTROL_ROUTE,
    GUI_DESIGN_MOBA_HOME_WELCOME_CHROME as GUI_DESIGN_MOBA_HOME_WELCOME_CHROME,
    GUI_DESIGN_MOBA_HOME_WELCOME_GEOMETRY as GUI_DESIGN_MOBA_HOME_WELCOME_GEOMETRY,
    GUI_DESIGN_MOBA_MONITORING_CONTROL_GEOMETRY as GUI_DESIGN_MOBA_MONITORING_CONTROL_GEOMETRY,
    GUI_DESIGN_MOBA_MONITORING_CONTROLS as GUI_DESIGN_MOBA_MONITORING_CONTROLS,
    GUI_DESIGN_MOBA_MONITORING_METRICS as GUI_DESIGN_MOBA_MONITORING_METRICS,
    GUI_DESIGN_MOBA_MONITORING_TELEMETRY_ROUTE as GUI_DESIGN_MOBA_MONITORING_TELEMETRY_ROUTE,
    GUI_DESIGN_MOBA_QUICK_CONNECT_CHROME,
    GUI_DESIGN_MOBA_QUICK_CONNECT_SUGGESTION_CHROME,
    GUI_DESIGN_MOBA_RAIL_CHROME,
    GUI_DESIGN_MOBA_STATUS_SEGMENTS,
    gui_design_moba_quick_connect_chrome,
    gui_design_moba_ribbon_actions,
    gui_design_moba_ribbon_tooltips,
    GUI_DESIGN_MOBA_RAIL_ITEM_GEOMETRY as GUI_DESIGN_MOBA_RAIL_ITEM_GEOMETRY,
    GUI_DESIGN_MOBA_RAIL_ITEMS as GUI_DESIGN_MOBA_RAIL_ITEMS,
    GUI_DESIGN_MOBA_REMOTE_MONITORING_CONTROL_ROUTE as GUI_DESIGN_MOBA_REMOTE_MONITORING_CONTROL_ROUTE,
    GUI_DESIGN_MOBA_REMOTE_MONITORING_DOCK_CHROME as GUI_DESIGN_MOBA_REMOTE_MONITORING_DOCK_CHROME,
    GUI_DESIGN_MOBA_RIBBON_ACTION_GEOMETRY as GUI_DESIGN_MOBA_RIBBON_ACTION_GEOMETRY,
    GUI_DESIGN_MOBA_RIBBON_ACTIONS as GUI_DESIGN_MOBA_RIBBON_ACTIONS,
    GUI_DESIGN_MOBA_RIBBON_EDGE_ACTION_ROUTE as GUI_DESIGN_MOBA_RIBBON_EDGE_ACTION_ROUTE,
    GUI_DESIGN_MOBA_RIBBON_EDGE_ACTIONS as GUI_DESIGN_MOBA_RIBBON_EDGE_ACTIONS,
    GUI_DESIGN_MOBA_RIBBON_TOOLTIPS as GUI_DESIGN_MOBA_RIBBON_TOOLTIPS,
    GUI_DESIGN_MOBA_RIGHT_UTILITY_ACTION_ROUTE as GUI_DESIGN_MOBA_RIGHT_UTILITY_ACTION_ROUTE,
    GUI_DESIGN_MOBA_RIGHT_UTILITY_ACTIONS as GUI_DESIGN_MOBA_RIGHT_UTILITY_ACTIONS,
    GUI_DESIGN_MOBA_RIGHT_UTILITY_RAIL_CHROME as GUI_DESIGN_MOBA_RIGHT_UTILITY_RAIL_CHROME,
    GUI_DESIGN_MOBA_SESSION_EDGE_ACTION_ROUTE as GUI_DESIGN_MOBA_SESSION_EDGE_ACTION_ROUTE,
    GUI_DESIGN_MOBA_SESSION_EDGE_ACTIONS as GUI_DESIGN_MOBA_SESSION_EDGE_ACTIONS,
    GUI_DESIGN_MOBA_SESSION_TREE_CHROME as GUI_DESIGN_MOBA_SESSION_TREE_CHROME,
    GUI_DESIGN_MOBA_SFTP_BROWSER_CHROME as GUI_DESIGN_MOBA_SFTP_BROWSER_CHROME,
    GUI_DESIGN_MOBA_SFTP_DOCK_ACTIONS as GUI_DESIGN_MOBA_SFTP_DOCK_ACTIONS,
    GUI_DESIGN_MOBA_SFTP_DOCK_LAYOUT as GUI_DESIGN_MOBA_SFTP_DOCK_LAYOUT,
    GUI_DESIGN_MOBA_SFTP_FILE_ROW_ICONS as GUI_DESIGN_MOBA_SFTP_FILE_ROW_ICONS,
    GUI_DESIGN_MOBA_SFTP_FOLLOW_FOLDER_ROUTE as GUI_DESIGN_MOBA_SFTP_FOLLOW_FOLDER_ROUTE,
    GUI_DESIGN_MOBA_SFTP_ROUTED_FILE_ROWS as GUI_DESIGN_MOBA_SFTP_ROUTED_FILE_ROWS,
    GUI_DESIGN_MOBA_SFTP_TOOLBAR_ACTION_GEOMETRY as GUI_DESIGN_MOBA_SFTP_TOOLBAR_ACTION_GEOMETRY,
    GUI_DESIGN_MOBA_SFTP_TOOLBAR_ACTION_ROUTE as GUI_DESIGN_MOBA_SFTP_TOOLBAR_ACTION_ROUTE,
    GUI_DESIGN_MOBA_SSH_BANNER_CAPABILITY_KEYS as GUI_DESIGN_MOBA_SSH_BANNER_CAPABILITY_KEYS,
    GUI_DESIGN_MOBA_SSH_BANNER_CHROME as GUI_DESIGN_MOBA_SSH_BANNER_CHROME,
    GUI_DESIGN_MOBA_SSH_BANNER_ROW_GEOMETRY as GUI_DESIGN_MOBA_SSH_BANNER_ROW_GEOMETRY,
    GUI_DESIGN_MOBA_SSH_BANNER_VISIBLE_CAPABILITY_KEYS as GUI_DESIGN_MOBA_SSH_BANNER_VISIBLE_CAPABILITY_KEYS,
    GUI_DESIGN_MOBA_STATUS_BAR_CHROME as GUI_DESIGN_MOBA_STATUS_BAR_CHROME,
    GUI_DESIGN_MOBA_TERMINAL_TRANSCRIPT_ROW_GEOMETRY as GUI_DESIGN_MOBA_TERMINAL_TRANSCRIPT_ROW_GEOMETRY,
    GUI_DESIGN_MOBA_TITLEBAR_CHROME as GUI_DESIGN_MOBA_TITLEBAR_CHROME,
    GUI_DESIGN_MOBA_TOP_MENU_GEOMETRY as GUI_DESIGN_MOBA_TOP_MENU_GEOMETRY,
    GUI_DESIGN_MOBA_TOP_MENU_ITEMS as GUI_DESIGN_MOBA_TOP_MENU_ITEMS,
    GUI_DESIGN_MOBA_TOP_STACK_GEOMETRY as GUI_DESIGN_MOBA_TOP_STACK_GEOMETRY,
    GuiMobaBottomEdgeControl as GuiMobaBottomEdgeControl,
    GuiMobaConnectedDockFrame as GuiMobaConnectedDockFrame,
    GuiMobaFollowTerminalFolderControlRoute as GuiMobaFollowTerminalFolderControlRoute,
    GuiMobaHomeWelcomeChrome as GuiMobaHomeWelcomeChrome,
    GuiMobaHomeWelcomeGeometry as GuiMobaHomeWelcomeGeometry,
    GuiMobaMonitoringControl as GuiMobaMonitoringControl,
    GuiMobaMonitoringControlGeometry as GuiMobaMonitoringControlGeometry,
    GuiMobaMonitoringMetric as GuiMobaMonitoringMetric,
    GuiMobaMonitoringTelemetryRoute as GuiMobaMonitoringTelemetryRoute,
    GuiMobaQuickConnectChrome as GuiMobaQuickConnectChrome,
    GuiMobaQuickConnectSuggestionChrome as GuiMobaQuickConnectSuggestionChrome,
    GuiMobaRailChrome as GuiMobaRailChrome,
    GuiMobaRailItem as GuiMobaRailItem,
    GuiMobaRailItemGeometry as GuiMobaRailItemGeometry,
    GuiMobaRemoteMonitoringControlRoute as GuiMobaRemoteMonitoringControlRoute,
    GuiMobaRemoteMonitoringDockChrome as GuiMobaRemoteMonitoringDockChrome,
    GuiMobaRibbonAction as GuiMobaRibbonAction,
    GuiMobaRibbonActionGeometry as GuiMobaRibbonActionGeometry,
    GuiMobaRibbonEdgeAction as GuiMobaRibbonEdgeAction,
    GuiMobaRibbonEdgeActionRoute as GuiMobaRibbonEdgeActionRoute,
    GuiMobaRightUtilityAction as GuiMobaRightUtilityAction,
    GuiMobaRightUtilityActionRoute as GuiMobaRightUtilityActionRoute,
    GuiMobaRightUtilityRailChrome as GuiMobaRightUtilityRailChrome,
    GuiMobaSessionEdgeAction as GuiMobaSessionEdgeAction,
    GuiMobaSessionEdgeActionRoute as GuiMobaSessionEdgeActionRoute,
    GuiMobaSessionTreeChrome as GuiMobaSessionTreeChrome,
    GuiMobaSftpBrowserChrome as GuiMobaSftpBrowserChrome,
    GuiMobaSftpDockAction as GuiMobaSftpDockAction,
    GuiMobaSftpDockLayout as GuiMobaSftpDockLayout,
    GuiMobaSftpFileRowIcon as GuiMobaSftpFileRowIcon,
    GuiMobaSftpFollowFolderRoute as GuiMobaSftpFollowFolderRoute,
    GuiMobaSftpRoutedFileRows as GuiMobaSftpRoutedFileRows,
    GuiMobaSftpTableColumn as GuiMobaSftpTableColumn,
    GuiMobaSftpToolbarActionGeometry as GuiMobaSftpToolbarActionGeometry,
    GuiMobaSftpToolbarActionRoute as GuiMobaSftpToolbarActionRoute,
    GuiMobaSshBannerChrome as GuiMobaSshBannerChrome,
    GuiMobaSshBannerRowGeometry as GuiMobaSshBannerRowGeometry,
    GuiMobaStatusBarChrome as GuiMobaStatusBarChrome,
    GuiMobaStatusSegment as GuiMobaStatusSegment,
    GuiMobaTerminalTranscriptRowGeometry as GuiMobaTerminalTranscriptRowGeometry,
    GuiMobaTitlebarChrome as GuiMobaTitlebarChrome,
    GuiMobaTopMenuGeometry as GuiMobaTopMenuGeometry,
    GuiMobaTopMenuItem as GuiMobaTopMenuItem,
    GuiMobaTopStackGeometry as GuiMobaTopStackGeometry,
    gui_design_moba_bottom_edge_controls as gui_design_moba_bottom_edge_controls,
    gui_design_moba_connected_dock_frame as gui_design_moba_connected_dock_frame,
    gui_design_moba_follow_terminal_folder_control_route as gui_design_moba_follow_terminal_folder_control_route,
    gui_design_moba_home_welcome_chrome as gui_design_moba_home_welcome_chrome,
    gui_design_moba_home_welcome_geometry as gui_design_moba_home_welcome_geometry,
    gui_design_moba_monitoring_control_geometry as gui_design_moba_monitoring_control_geometry,
    gui_design_moba_monitoring_control_geometry_for as gui_design_moba_monitoring_control_geometry_for,
    gui_design_moba_monitoring_controls as gui_design_moba_monitoring_controls,
    gui_design_moba_monitoring_metrics as gui_design_moba_monitoring_metrics,
    gui_design_moba_monitoring_telemetry_route as gui_design_moba_monitoring_telemetry_route,
    gui_design_moba_quick_connect_suggestion_chrome as gui_design_moba_quick_connect_suggestion_chrome,
    gui_design_moba_rail_chrome as gui_design_moba_rail_chrome,
    gui_design_moba_rail_item_geometry as gui_design_moba_rail_item_geometry,
    gui_design_moba_rail_item_geometry_for as gui_design_moba_rail_item_geometry_for,
    gui_design_moba_rail_items as gui_design_moba_rail_items,
    gui_design_moba_remote_monitoring_control_route as gui_design_moba_remote_monitoring_control_route,
    gui_design_moba_remote_monitoring_dock_chrome as gui_design_moba_remote_monitoring_dock_chrome,
    gui_design_moba_ribbon_action_geometry as gui_design_moba_ribbon_action_geometry,
    gui_design_moba_ribbon_action_geometry_for as gui_design_moba_ribbon_action_geometry_for,
    gui_design_moba_ribbon_edge_action_route as gui_design_moba_ribbon_edge_action_route,
    gui_design_moba_ribbon_edge_actions as gui_design_moba_ribbon_edge_actions,
    gui_design_moba_right_utility_action_route as gui_design_moba_right_utility_action_route,
    gui_design_moba_right_utility_actions as gui_design_moba_right_utility_actions,
    gui_design_moba_right_utility_rail_chrome as gui_design_moba_right_utility_rail_chrome,
    gui_design_moba_session_edge_action_route as gui_design_moba_session_edge_action_route,
    gui_design_moba_session_edge_actions as gui_design_moba_session_edge_actions,
    gui_design_moba_session_tree_chrome as gui_design_moba_session_tree_chrome,
    gui_design_moba_sftp_browser_chrome as gui_design_moba_sftp_browser_chrome,
    gui_design_moba_sftp_dock_actions as gui_design_moba_sftp_dock_actions,
    gui_design_moba_sftp_dock_layout as gui_design_moba_sftp_dock_layout,
    gui_design_moba_sftp_file_row_icon as gui_design_moba_sftp_file_row_icon,
    gui_design_moba_sftp_file_row_icons as gui_design_moba_sftp_file_row_icons,
    gui_design_moba_sftp_follow_folder_route as gui_design_moba_sftp_follow_folder_route,
    gui_design_moba_sftp_routed_file_rows as gui_design_moba_sftp_routed_file_rows,
    gui_design_moba_sftp_toolbar_action_geometry as gui_design_moba_sftp_toolbar_action_geometry,
    gui_design_moba_sftp_toolbar_action_geometry_for as gui_design_moba_sftp_toolbar_action_geometry_for,
    gui_design_moba_sftp_toolbar_action_route as gui_design_moba_sftp_toolbar_action_route,
    gui_design_moba_ssh_banner_chrome as gui_design_moba_ssh_banner_chrome,
    gui_design_moba_ssh_banner_row_geometry as gui_design_moba_ssh_banner_row_geometry,
    gui_design_moba_ssh_banner_row_geometry_for as gui_design_moba_ssh_banner_row_geometry_for,
    gui_design_moba_status_bar_chrome as gui_design_moba_status_bar_chrome,
    gui_design_moba_status_segments as gui_design_moba_status_segments,
    gui_design_moba_terminal_transcript_row_geometry as gui_design_moba_terminal_transcript_row_geometry,
    gui_design_moba_terminal_transcript_row_geometry_for as gui_design_moba_terminal_transcript_row_geometry_for,
    gui_design_moba_titlebar_chrome as gui_design_moba_titlebar_chrome,
    gui_design_moba_top_menu_geometry as gui_design_moba_top_menu_geometry,
    gui_design_moba_top_menu_geometry_for as gui_design_moba_top_menu_geometry_for,
    gui_design_moba_top_menu_items as gui_design_moba_top_menu_items,
    gui_design_moba_top_stack_geometry as gui_design_moba_top_stack_geometry,
)
from .gui_preset_mremoteng import (
    GUI_DESIGN_MREMOTENG_CONNECTION_DOCUMENT_ROUTE as GUI_DESIGN_MREMOTENG_CONNECTION_DOCUMENT_ROUTE,
    GUI_DESIGN_MREMOTENG_DOCUMENT_CONTROLS as GUI_DESIGN_MREMOTENG_DOCUMENT_CONTROLS,
    GUI_DESIGN_MREMOTENG_DOCUMENT_FILTER_ROUTE as GUI_DESIGN_MREMOTENG_DOCUMENT_FILTER_ROUTE,
    GUI_DESIGN_MREMOTENG_DOCUMENT_TOOLBAR_CHROME as GUI_DESIGN_MREMOTENG_DOCUMENT_TOOLBAR_CHROME,
    GUI_DESIGN_MREMOTENG_INHERITANCE_ROUTE as GUI_DESIGN_MREMOTENG_INHERITANCE_ROUTE,
    GUI_DESIGN_MREMOTENG_PROPERTY_GRID_CHROME as GUI_DESIGN_MREMOTENG_PROPERTY_GRID_CHROME,
    GUI_DESIGN_MREMOTENG_TOP_CHROME as GUI_DESIGN_MREMOTENG_TOP_CHROME,
    GuiMRemoteNgConnectionDocumentRoute as GuiMRemoteNgConnectionDocumentRoute,
    GuiMRemoteNgDocumentControl as GuiMRemoteNgDocumentControl,
    GuiMRemoteNgDocumentFilterRoute as GuiMRemoteNgDocumentFilterRoute,
    GuiMRemoteNgDocumentToolbarChrome as GuiMRemoteNgDocumentToolbarChrome,
    GuiMRemoteNgInheritanceRoute as GuiMRemoteNgInheritanceRoute,
    GuiMRemoteNgPropertyColumn as GuiMRemoteNgPropertyColumn,
    GuiMRemoteNgPropertyGridChrome as GuiMRemoteNgPropertyGridChrome,
    GuiMRemoteNgPropertyRow as GuiMRemoteNgPropertyRow,
    GuiMRemoteNgTopChrome as GuiMRemoteNgTopChrome,
    GuiMRemoteNgTopMenuItem as GuiMRemoteNgTopMenuItem,
    GuiMRemoteNgTopToolbarAction as GuiMRemoteNgTopToolbarAction,
    gui_design_mremoteng_connection_document_route as gui_design_mremoteng_connection_document_route,
    gui_design_mremoteng_document_controls as gui_design_mremoteng_document_controls,
    gui_design_mremoteng_document_filter_route as gui_design_mremoteng_document_filter_route,
    gui_design_mremoteng_document_toolbar_chrome,
    gui_design_mremoteng_inheritance_route as gui_design_mremoteng_inheritance_route,
    gui_design_mremoteng_property_grid_chrome as gui_design_mremoteng_property_grid_chrome,
    gui_design_mremoteng_top_chrome as gui_design_mremoteng_top_chrome,
)
from .gui_preset_remmina import (
    GUI_DESIGN_REMMINA_CLIPBOARD_ROUTE as GUI_DESIGN_REMMINA_CLIPBOARD_ROUTE,
    GUI_DESIGN_REMMINA_PROFILE_FILTER_ROUTE as GUI_DESIGN_REMMINA_PROFILE_FILTER_ROUTE,
    GUI_DESIGN_REMMINA_PROFILE_LIST_CHROME as GUI_DESIGN_REMMINA_PROFILE_LIST_CHROME,
    GUI_DESIGN_REMMINA_PROFILE_VIEWER_ROUTE as GUI_DESIGN_REMMINA_PROFILE_VIEWER_ROUTE,
    GUI_DESIGN_REMMINA_SCREENSHOT_ROUTE as GUI_DESIGN_REMMINA_SCREENSHOT_ROUTE,
    GUI_DESIGN_REMMINA_SFTP_TRANSFER_ROUTE as GUI_DESIGN_REMMINA_SFTP_TRANSFER_ROUTE,
    GUI_DESIGN_REMMINA_VIEWER_CONTROLS as GUI_DESIGN_REMMINA_VIEWER_CONTROLS,
    GuiRemminaClipboardRoute as GuiRemminaClipboardRoute,
    GuiRemminaProfileColumn as GuiRemminaProfileColumn,
    GuiRemminaProfileFilterRoute as GuiRemminaProfileFilterRoute,
    GuiRemminaProfileListChrome as GuiRemminaProfileListChrome,
    GuiRemminaProfileRow as GuiRemminaProfileRow,
    GuiRemminaProfileViewerRoute as GuiRemminaProfileViewerRoute,
    GuiRemminaScreenshotRoute as GuiRemminaScreenshotRoute,
    GuiRemminaSftpTransferRoute as GuiRemminaSftpTransferRoute,
    GuiRemminaSftpTransferRow as GuiRemminaSftpTransferRow,
    GuiRemminaViewerControl as GuiRemminaViewerControl,
    gui_design_remmina_clipboard_route as gui_design_remmina_clipboard_route,
    gui_design_remmina_profile_filter_route as gui_design_remmina_profile_filter_route,
    gui_design_remmina_profile_list_chrome,
    gui_design_remmina_profile_viewer_route as gui_design_remmina_profile_viewer_route,
    gui_design_remmina_screenshot_route as gui_design_remmina_screenshot_route,
    gui_design_remmina_sftp_transfer_route as gui_design_remmina_sftp_transfer_route,
    gui_design_remmina_viewer_controls as gui_design_remmina_viewer_controls,
)
from .gui_preset_securecrt import (
    GUI_DESIGN_SECURECRT_COMMAND_WINDOW_CHROME as GUI_DESIGN_SECURECRT_COMMAND_WINDOW_CHROME,
    GUI_DESIGN_SECURECRT_COMMAND_WINDOW_SEND_ROUTE as GUI_DESIGN_SECURECRT_COMMAND_WINDOW_SEND_ROUTE,
    GUI_DESIGN_SECURECRT_SESSION_MANAGER_CHROME as GUI_DESIGN_SECURECRT_SESSION_MANAGER_CHROME,
    GUI_DESIGN_SECURECRT_SESSION_MANAGER_FILTER_ROUTE as GUI_DESIGN_SECURECRT_SESSION_MANAGER_FILTER_ROUTE,
    GUI_DESIGN_SECURECRT_SESSION_MANAGER_ROUTE as GUI_DESIGN_SECURECRT_SESSION_MANAGER_ROUTE,
    GUI_DESIGN_SECURECRT_SESSION_STATUS_STRIP as GUI_DESIGN_SECURECRT_SESSION_STATUS_STRIP,
    GUI_DESIGN_SECURECRT_SFTP_BROWSER_ROUTE as GUI_DESIGN_SECURECRT_SFTP_BROWSER_ROUTE,
    GUI_DESIGN_SECURECRT_SFTP_TAB_ROUTE as GUI_DESIGN_SECURECRT_SFTP_TAB_ROUTE,
    GUI_DESIGN_SECURECRT_TOP_CHROME as GUI_DESIGN_SECURECRT_TOP_CHROME,
    GuiSecureCrtCommandWindowChrome as GuiSecureCrtCommandWindowChrome,
    GuiSecureCrtCommandWindowSendRoute as GuiSecureCrtCommandWindowSendRoute,
    GuiSecureCrtSessionManagerAction as GuiSecureCrtSessionManagerAction,
    GuiSecureCrtSessionManagerChrome as GuiSecureCrtSessionManagerChrome,
    GuiSecureCrtSessionManagerFilterRoute as GuiSecureCrtSessionManagerFilterRoute,
    GuiSecureCrtSessionManagerRoute as GuiSecureCrtSessionManagerRoute,
    GuiSecureCrtSessionStatusField as GuiSecureCrtSessionStatusField,
    GuiSecureCrtSessionStatusStrip as GuiSecureCrtSessionStatusStrip,
    GuiSecureCrtSftpBrowserRoute as GuiSecureCrtSftpBrowserRoute,
    GuiSecureCrtSftpBrowserRow as GuiSecureCrtSftpBrowserRow,
    GuiSecureCrtSftpTabRoute as GuiSecureCrtSftpTabRoute,
    GuiSecureCrtTopChrome as GuiSecureCrtTopChrome,
    GuiSecureCrtTopMenuItem as GuiSecureCrtTopMenuItem,
    GuiSecureCrtTopToolbarAction as GuiSecureCrtTopToolbarAction,
    gui_design_securecrt_command_window_chrome as gui_design_securecrt_command_window_chrome,
    gui_design_securecrt_command_window_send_route as gui_design_securecrt_command_window_send_route,
    gui_design_securecrt_session_manager_chrome,
    gui_design_securecrt_session_manager_filter_route as gui_design_securecrt_session_manager_filter_route,
    gui_design_securecrt_session_manager_route as gui_design_securecrt_session_manager_route,
    gui_design_securecrt_session_status_strip as gui_design_securecrt_session_status_strip,
    gui_design_securecrt_sftp_browser_route as gui_design_securecrt_sftp_browser_route,
    gui_design_securecrt_sftp_tab_route as gui_design_securecrt_sftp_tab_route,
    gui_design_securecrt_top_chrome as gui_design_securecrt_top_chrome,
)
from .gui_preset_termius import (
    GUI_DESIGN_TERMIUS_FILES_BROWSER_ROUTE as GUI_DESIGN_TERMIUS_FILES_BROWSER_ROUTE,
    GUI_DESIGN_TERMIUS_HEADER_CHIPS as GUI_DESIGN_TERMIUS_HEADER_CHIPS,
    GUI_DESIGN_TERMIUS_HOST_IDENTITY_STRIP as GUI_DESIGN_TERMIUS_HOST_IDENTITY_STRIP,
    GUI_DESIGN_TERMIUS_HOST_SELECTION_ROUTE as GUI_DESIGN_TERMIUS_HOST_SELECTION_ROUTE,
    GUI_DESIGN_TERMIUS_HOSTS_CHROME as GUI_DESIGN_TERMIUS_HOSTS_CHROME,
    GUI_DESIGN_TERMIUS_PORT_FORWARD_ROUTE as GUI_DESIGN_TERMIUS_PORT_FORWARD_ROUTE,
    GUI_DESIGN_TERMIUS_SNIPPET_ROUTE as GUI_DESIGN_TERMIUS_SNIPPET_ROUTE,
    GUI_DESIGN_TERMIUS_SYNC_ROUTE as GUI_DESIGN_TERMIUS_SYNC_ROUTE,
    GuiTermiusFilesBrowserRoute as GuiTermiusFilesBrowserRoute,
    GuiTermiusFilesBrowserRow as GuiTermiusFilesBrowserRow,
    GuiTermiusHeaderChip as GuiTermiusHeaderChip,
    GuiTermiusHostIdentityField as GuiTermiusHostIdentityField,
    GuiTermiusHostIdentityStrip as GuiTermiusHostIdentityStrip,
    GuiTermiusHostsAction as GuiTermiusHostsAction,
    GuiTermiusHostsChrome as GuiTermiusHostsChrome,
    GuiTermiusHostSelectionRoute as GuiTermiusHostSelectionRoute,
    GuiTermiusPortForwardRoute as GuiTermiusPortForwardRoute,
    GuiTermiusSnippetRoute as GuiTermiusSnippetRoute,
    GuiTermiusSyncRoute as GuiTermiusSyncRoute,
    gui_design_termius_files_browser_route as gui_design_termius_files_browser_route,
    gui_design_termius_header_chips as gui_design_termius_header_chips,
    gui_design_termius_host_identity_strip as gui_design_termius_host_identity_strip,
    gui_design_termius_host_selection_route as gui_design_termius_host_selection_route,
    gui_design_termius_hosts_chrome,
    gui_design_termius_port_forward_route as gui_design_termius_port_forward_route,
    gui_design_termius_snippet_route as gui_design_termius_snippet_route,
    gui_design_termius_sync_route as gui_design_termius_sync_route,
)
# isort: on

DEFAULT_GUI_DESIGN_ID = "native"


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


_WORKSPACE_ASSETS = files("remote_ops_workspace").joinpath("assets")
_WORKSPACE_STYLESHEET = Template(
    _WORKSPACE_ASSETS.joinpath("workspace.qss").read_text(encoding="utf-8")
)
_PRESET_STYLES = json.loads(
    _WORKSPACE_ASSETS.joinpath("workspace-styles.json").read_text(encoding="utf-8")
)


def _stylesheet(
    colors: GuiDesignColors,
    *,
    radius: int,
    control_padding: str,
    tab_padding: str,
    tree_padding: str,
) -> str:
    return _WORKSPACE_STYLESHEET.substitute(
        asdict(colors),
        radius=radius,
        control_padding=control_padding,
        tab_padding=tab_padding,
        tree_padding=tree_padding,
        quick_connect_input_padding=GUI_DESIGN_MOBA_QUICK_CONNECT_CHROME.input_padding,
        quick_connect_suggestion_row_height=GUI_DESIGN_MOBA_QUICK_CONNECT_SUGGESTION_CHROME.row_height,
        rail_label_font_size=GUI_DESIGN_MOBA_RAIL_CHROME.label_font_size,
    )


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
) -> GuiDesignPreset:
    style = _PRESET_STYLES[id]
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
            radius=style["radius"],
            control_padding=style["control_padding"],
            tab_padding=style["tab_padding"],
            tree_padding=style["tree_padding"],
        ),
    )


NATIVE_COLORS = GuiDesignColors(**_PRESET_STYLES[DEFAULT_GUI_DESIGN_ID]["colors"])
MOBAXTERM_COLORS = GuiDesignColors(**_PRESET_STYLES["mobaxterm"]["colors"])
SECURECRT_COLORS = GuiDesignColors(**_PRESET_STYLES["securecrt"]["colors"])
TERMIUS_COLORS = GuiDesignColors(**_PRESET_STYLES["termius"]["colors"])
REMMINA_COLORS = GuiDesignColors(**_PRESET_STYLES["remmina"]["colors"])
MREMOTENG_COLORS = GuiDesignColors(**_PRESET_STYLES["mremoteng"]["colors"])


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
    ),
    _preset(
        id="securecrt",
        label="SecureCRT-style",
        description="Native Windows terminal workspace with menu chrome, Session Manager tree and compact session tabs.",
        profile_width=270,
        log_height=118,
        tab_position="north",
        density="terminal",
        toolbar_icon_size=15,
        list_spacing=1,
        document_mode=False,
        colors=SECURECRT_COLORS,
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
        "layoutToolbar",
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

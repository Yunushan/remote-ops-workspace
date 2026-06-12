from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from remote_ops_workspace.gui_designs import (  # noqa: E402
    GUI_DESIGN_PRESETS,
    gui_design_home_tab_label,
    gui_design_interaction_state,
    gui_design_moba_bottom_edge_controls,
    gui_design_moba_connected_dock_frame,
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
    gui_design_moba_remote_monitoring_dock_chrome,
    gui_design_moba_ribbon_action_geometry,
    gui_design_moba_ribbon_actions,
    gui_design_moba_ribbon_edge_actions,
    gui_design_moba_right_utility_actions,
    gui_design_moba_right_utility_rail_chrome,
    gui_design_moba_session_edge_actions,
    gui_design_moba_session_tree_chrome,
    gui_design_moba_sftp_browser_chrome,
    gui_design_moba_sftp_dock_actions,
    gui_design_moba_sftp_dock_layout,
    gui_design_moba_sftp_file_row_icons,
    gui_design_moba_sftp_follow_folder_route,
    gui_design_moba_sftp_routed_file_rows,
    gui_design_moba_sftp_toolbar_action_geometry,
    gui_design_moba_ssh_banner_chrome,
    gui_design_moba_ssh_banner_row_geometry,
    gui_design_moba_status_bar_chrome,
    gui_design_moba_status_segments,
    gui_design_moba_terminal_transcript_row_geometry,
    gui_design_moba_titlebar_chrome,
    gui_design_moba_top_menu_geometry,
    gui_design_moba_top_menu_items,
    gui_design_moba_top_stack_geometry,
    gui_design_mremoteng_connection_document_route,
    gui_design_mremoteng_document_controls,
    gui_design_mremoteng_document_toolbar_chrome,
    gui_design_mremoteng_property_grid_chrome,
    gui_design_mremoteng_top_chrome,
    gui_design_reference_state,
    gui_design_remmina_clipboard_route,
    gui_design_remmina_profile_list_chrome,
    gui_design_remmina_profile_viewer_route,
    gui_design_remmina_viewer_controls,
    gui_design_securecrt_command_window_chrome,
    gui_design_securecrt_command_window_send_route,
    gui_design_securecrt_session_manager_chrome,
    gui_design_securecrt_session_manager_route,
    gui_design_securecrt_session_status_strip,
    gui_design_securecrt_top_chrome,
    gui_design_sidebar_copy,
    gui_design_status_segments,
    gui_design_termius_header_chips,
    gui_design_termius_host_identity_strip,
    gui_design_termius_host_selection_route,
    gui_design_termius_hosts_chrome,
    gui_design_termius_sync_route,
    gui_design_toolbar_actions,
    gui_design_tree_root_icon,
    gui_design_tree_row_icon,
    gui_design_workflow_cards,
    gui_design_workspace_surface,
)
from remote_ops_workspace.launcher import LauncherError  # noqa: E402
from remote_ops_workspace.moba_connected import (  # noqa: E402
    build_moba_connected_session_state,
    build_moba_terminal_transcript,
    build_ssh_connection_banner,
    moba_connected_session_identity_route,
    moba_connected_session_route,
    moba_connected_tab_chrome_geometry_items,
    moba_telemetry_cell_geometry,
    moba_telemetry_cells,
)
from remote_ops_workspace.models import Profile  # noqa: E402

REQUESTED_SIZE = (1420, 820)
MIN_CAPTURE_SIZE = (1100, 680)
MANIFEST_NAME = "real-gui-render-manifest.json"
PRESET_REFERENCE_PROFILES = {
    "mobaxterm": "edge-prod",
    "securecrt": "edge-prod",
    "termius": "edge-prod",
    "remmina": "win-admin",
    "mremoteng": "edge-prod",
}
EXPECTED_LIVE_TREE_LABELS = {
    "mobaxterm": {"prod", "edge-prod", "win-admin", "files", "sftp-ops"},
    "securecrt": {"Folder: Sessions", "edge-prod (SSH2)", "files-prod (SFTP)", "jump-host (SSH2)"},
    "termius": {"Vault / Personal", "edge-prod  ssh host", "jump-host  ssh host", "Vault / Teams", "prod-cluster  ssh host"},
    "remmina": {"Group: RDP", "RDP - win-admin", "Group: VNC", "VNC - linux-console", "Group: SSH/SFTP", "SFTP - sftp-ops"},
    "mremoteng": {"Container: prod", "edge-prod [SSH]", "win-admin [RDP]", "Container: files", "sftp-ops [SFTP]"},
}
EXPECTED_LIVE_REFERENCE_TAB_LABELS = {
    "mobaxterm": "edge-prod.example.invalid (operator)",
    "securecrt": "edge-prod (SSH2)",
    "termius": "edge-prod",
    "remmina": "RDP - win-admin",
    "mremoteng": "edge-prod [SSH]",
}
EXPECTED_MOBA_TELEMETRY_KEYS = {
    "target",
    "cpu",
    "memory",
    "disk",
    "net-up",
    "net-down",
    "connections",
    "processes",
}
EXPECTED_MOBA_TOP_MENU_ITEMS = tuple(gui_design_moba_top_menu_items())
EXPECTED_MOBA_TOP_MENU_KEYS = [item.key for item in EXPECTED_MOBA_TOP_MENU_ITEMS]
EXPECTED_MOBA_TOP_MENU_LABELS = [item.label for item in EXPECTED_MOBA_TOP_MENU_ITEMS]
EXPECTED_MOBA_TOP_MENU_GEOMETRY = tuple(gui_design_moba_top_menu_geometry())
EXPECTED_MOBA_TOP_MENU_GEOMETRY_BY_KEY = {geometry.key: geometry for geometry in EXPECTED_MOBA_TOP_MENU_GEOMETRY}
EXPECTED_MOBA_TITLEBAR_CHROME = gui_design_moba_titlebar_chrome()
EXPECTED_MOBA_TOP_STACK_GEOMETRY = gui_design_moba_top_stack_geometry()
EXPECTED_MOBA_CONNECTED_DOCK_FRAME = gui_design_moba_connected_dock_frame()
EXPECTED_MOBA_QUICK_CONNECT_CHROME = gui_design_moba_quick_connect_chrome()
EXPECTED_MOBA_QUICK_CONNECT_SUGGESTION_CHROME = gui_design_moba_quick_connect_suggestion_chrome()
EXPECTED_MOBA_HOME_WELCOME_CHROME = gui_design_moba_home_welcome_chrome()
EXPECTED_MOBA_HOME_WELCOME_GEOMETRY = gui_design_moba_home_welcome_geometry()
EXPECTED_MOBA_CONNECTED_STATE = build_moba_connected_session_state(
    Profile(
        name="edge-prod",
        protocol="ssh",
        host="edge-prod.example.invalid",
        port=22,
        username="operator",
    ),
    remote_path="/var/log",
    terminal_cwd="/var/log",
    monitoring_output=(
        "cpu=7 mem_mb=410/7680 disk_mb=2867/49152 users=1 processes=158 "
        "net_up_mbps=0.01 net_down_mbps=0.01"
    ),
)
EXPECTED_MOBA_CONNECTED_SESSION_ROUTE = moba_connected_session_route(EXPECTED_MOBA_CONNECTED_STATE)
EXPECTED_MOBA_CONNECTED_SESSION_IDENTITY_ROUTE = moba_connected_session_identity_route(EXPECTED_MOBA_CONNECTED_STATE)
EXPECTED_MOBA_TERMINAL_TRANSCRIPT = build_moba_terminal_transcript(
    Profile(
        name="edge-prod",
        protocol="ssh",
        host="edge-prod.example.invalid",
        port=22,
        username="operator",
    ),
    "/var/log",
)
EXPECTED_MOBA_TERMINAL_TRANSCRIPT_KEYS = [line.key for line in EXPECTED_MOBA_TERMINAL_TRANSCRIPT]
EXPECTED_MOBA_TERMINAL_TRANSCRIPT_TONES = [line.tone for line in EXPECTED_MOBA_TERMINAL_TRANSCRIPT]
EXPECTED_MOBA_TERMINAL_TRANSCRIPT_ROW_GEOMETRY = tuple(gui_design_moba_terminal_transcript_row_geometry())
EXPECTED_MOBA_TERMINAL_TRANSCRIPT_ROW_GEOMETRY_KEYS = [
    row.key for row in EXPECTED_MOBA_TERMINAL_TRANSCRIPT_ROW_GEOMETRY
]
EXPECTED_MOBA_TELEMETRY_CELLS = moba_telemetry_cells(
    build_moba_connected_session_state(
        Profile(
            name="edge-prod",
            protocol="ssh",
            host="edge-prod.example.invalid",
            port=22,
            username="operator",
        ),
        remote_path="/var/log",
        terminal_cwd="/var/log",
        monitoring_output=(
            "cpu=7 mem_mb=410/7680 disk_mb=2867/49152 users=1 processes=158 "
            "net_up_mbps=0.01 net_down_mbps=0.01"
        ),
    )
)
EXPECTED_MOBA_TELEMETRY_CELL_KEYS = [cell.key for cell in EXPECTED_MOBA_TELEMETRY_CELLS]
EXPECTED_MOBA_TELEMETRY_CELL_WIDTHS = [cell.width for cell in EXPECTED_MOBA_TELEMETRY_CELLS]
EXPECTED_MOBA_TELEMETRY_CELL_GEOMETRY = tuple(moba_telemetry_cell_geometry())
EXPECTED_MOBA_TELEMETRY_CELL_GEOMETRY_BY_KEY = {
    geometry.key: geometry for geometry in EXPECTED_MOBA_TELEMETRY_CELL_GEOMETRY
}
EXPECTED_MOBA_RIBBON_ACTION_GEOMETRY = tuple(gui_design_moba_ribbon_action_geometry())
EXPECTED_MOBA_RIBBON_ACTION_GEOMETRY_BY_KEY = {
    geometry.key: geometry for geometry in EXPECTED_MOBA_RIBBON_ACTION_GEOMETRY
}
EXPECTED_MOBA_RIBBON_EDGE_ACTIONS = tuple(gui_design_moba_ribbon_edge_actions())
EXPECTED_MOBA_TAB_CHROME_KEYS = {"home", "active-session", "new-session"}
EXPECTED_MOBA_STATIC_TAB_CHROME_KEYS = {"home", "inactive-session", "active-session", "new-session"}
EXPECTED_MOBA_TAB_CHROME_GEOMETRY = tuple(moba_connected_tab_chrome_geometry_items())
EXPECTED_MOBA_TAB_CHROME_GEOMETRY_BY_KEY = {item.key: item for item in EXPECTED_MOBA_TAB_CHROME_GEOMETRY}
EXPECTED_MOBA_RIGHT_UTILITY_KEYS = {action.key for action in gui_design_moba_right_utility_actions()}
EXPECTED_MOBA_RIGHT_UTILITY_ICON_KEYS = {action.key: action.icon_key for action in gui_design_moba_right_utility_actions()}
EXPECTED_MOBA_RIGHT_UTILITY_ACTIONS = tuple(gui_design_moba_right_utility_actions())
EXPECTED_MOBA_RIGHT_UTILITY_BY_KEY = {action.key: action for action in EXPECTED_MOBA_RIGHT_UTILITY_ACTIONS}
EXPECTED_MOBA_RIGHT_UTILITY_RAIL_CHROME = gui_design_moba_right_utility_rail_chrome()
EXPECTED_MOBA_SESSION_EDGE_ACTIONS = tuple(gui_design_moba_session_edge_actions())
EXPECTED_MOBA_SESSION_EDGE_KEYS = {action.key for action in EXPECTED_MOBA_SESSION_EDGE_ACTIONS}
EXPECTED_MOBA_SESSION_EDGE_ICON_KEYS = {action.key: action.icon_key for action in EXPECTED_MOBA_SESSION_EDGE_ACTIONS}
EXPECTED_MOBA_SESSION_EDGE_BY_KEY = {action.key: action for action in EXPECTED_MOBA_SESSION_EDGE_ACTIONS}
EXPECTED_MOBA_SSH_BANNER_CHROME = gui_design_moba_ssh_banner_chrome()
EXPECTED_MOBA_SSH_BANNER = build_ssh_connection_banner(
    Profile(
        name="edge-prod",
        protocol="ssh",
        host="edge-prod.example.invalid",
        port=22,
        username="operator",
    )
)
EXPECTED_MOBA_SSH_BANNER_CAPABILITIES = EXPECTED_MOBA_SSH_BANNER.capability_rows()
EXPECTED_MOBA_SSH_BANNER_CAPABILITY_KEYS = [row.key for row in EXPECTED_MOBA_SSH_BANNER_CAPABILITIES]
EXPECTED_MOBA_SSH_BANNER_FOOTER_LINKS = list(EXPECTED_MOBA_SSH_BANNER.footer_links())
EXPECTED_MOBA_SSH_BANNER_ROW_GEOMETRY = tuple(gui_design_moba_ssh_banner_row_geometry())
EXPECTED_MOBA_SSH_BANNER_ROW_GEOMETRY_BY_KEY = {
    geometry.key: geometry for geometry in EXPECTED_MOBA_SSH_BANNER_ROW_GEOMETRY
}
EXPECTED_MOBA_SFTP_BROWSER_CHROME = gui_design_moba_sftp_browser_chrome()
EXPECTED_MOBA_SFTP_DOCK_LAYOUT = gui_design_moba_sftp_dock_layout()
EXPECTED_MOBA_SFTP_COLUMN_KEYS = [column.key for column in EXPECTED_MOBA_SFTP_BROWSER_CHROME.columns]
EXPECTED_MOBA_SFTP_COLUMN_LABELS = [column.label for column in EXPECTED_MOBA_SFTP_BROWSER_CHROME.columns]
EXPECTED_MOBA_SFTP_COLUMN_WIDTHS = [column.static_width for column in EXPECTED_MOBA_SFTP_BROWSER_CHROME.columns]
EXPECTED_MOBA_SFTP_ACTIONS = tuple(gui_design_moba_sftp_dock_actions())
EXPECTED_MOBA_SFTP_ACTION_KEYS = {action.key for action in EXPECTED_MOBA_SFTP_ACTIONS}
EXPECTED_MOBA_SFTP_SEPARATOR_AFTER_KEYS = [action.key for action in EXPECTED_MOBA_SFTP_ACTIONS if action.separator_after]
EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_GEOMETRY = tuple(gui_design_moba_sftp_toolbar_action_geometry())
EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_GEOMETRY_BY_KEY = {
    geometry.key: geometry for geometry in EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_GEOMETRY
}
EXPECTED_MOBA_SFTP_FILE_ROW_ICONS = tuple(gui_design_moba_sftp_file_row_icons())
EXPECTED_MOBA_SFTP_FILE_ROW_ICON_KEYS = {row_icon.kind: row_icon.icon_key for row_icon in EXPECTED_MOBA_SFTP_FILE_ROW_ICONS}
EXPECTED_MOBA_SFTP_FILE_ROW_RENDER_SOURCES = {
    row_icon.kind: row_icon.render_source for row_icon in EXPECTED_MOBA_SFTP_FILE_ROW_ICONS
}
EXPECTED_MOBA_SFTP_FILE_ROW_ICON_SIZES = {
    row_icon.kind: row_icon.static_size for row_icon in EXPECTED_MOBA_SFTP_FILE_ROW_ICONS
}
EXPECTED_MOBA_MONITORING_METRIC_KEYS = {metric.key for metric in gui_design_moba_monitoring_metrics()}
EXPECTED_MOBA_MONITORING_CONTROLS = tuple(gui_design_moba_monitoring_controls())
EXPECTED_MOBA_MONITORING_CONTROL_KEYS = {control.key for control in EXPECTED_MOBA_MONITORING_CONTROLS}
EXPECTED_MOBA_MONITORING_CONTROL_GEOMETRY = tuple(gui_design_moba_monitoring_control_geometry())
EXPECTED_MOBA_MONITORING_CONTROL_GEOMETRY_BY_KEY = {
    geometry.key: geometry for geometry in EXPECTED_MOBA_MONITORING_CONTROL_GEOMETRY
}
EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME = gui_design_moba_remote_monitoring_dock_chrome()
EXPECTED_MOBA_MONITORING_TELEMETRY_ROUTE = gui_design_moba_monitoring_telemetry_route()
EXPECTED_MOBA_SFTP_FOLLOW_FOLDER_ROUTE = gui_design_moba_sftp_follow_folder_route()
EXPECTED_MOBA_SFTP_ROUTED_FILE_ROWS = gui_design_moba_sftp_routed_file_rows()
EXPECTED_MOBA_STATUS_KEYS = {segment.key for segment in gui_design_moba_status_segments()}
EXPECTED_MOBA_STATUS_CHROME = gui_design_moba_status_bar_chrome()
EXPECTED_MOBA_BOTTOM_EDGE_CONTROLS = tuple(gui_design_moba_bottom_edge_controls())
EXPECTED_MOBA_BOTTOM_EDGE_KEYS = {control.key for control in EXPECTED_MOBA_BOTTOM_EDGE_CONTROLS}
EXPECTED_MOBA_BOTTOM_EDGE_ICON_KEYS = {control.key: control.icon_key for control in EXPECTED_MOBA_BOTTOM_EDGE_CONTROLS}
EXPECTED_SECURECRT_COMMAND_WINDOW_CHROME = gui_design_securecrt_command_window_chrome()
EXPECTED_SECURECRT_COMMAND_WINDOW_SEND_ROUTE = gui_design_securecrt_command_window_send_route()
EXPECTED_SECURECRT_SESSION_STATUS_STRIP = gui_design_securecrt_session_status_strip()
EXPECTED_SECURECRT_SESSION_STATUS_KEYS = [field.key for field in EXPECTED_SECURECRT_SESSION_STATUS_STRIP.fields]
EXPECTED_SECURECRT_SESSION_MANAGER_CHROME = gui_design_securecrt_session_manager_chrome()
EXPECTED_SECURECRT_SESSION_MANAGER_ROUTE = gui_design_securecrt_session_manager_route()
EXPECTED_SECURECRT_SESSION_MANAGER_ACTION_KEYS = [action.key for action in EXPECTED_SECURECRT_SESSION_MANAGER_CHROME.actions]
EXPECTED_SECURECRT_SESSION_MANAGER_ICON_KEYS = {
    action.key: action.icon_key for action in EXPECTED_SECURECRT_SESSION_MANAGER_CHROME.actions
}
EXPECTED_MOBA_SESSION_TREE_ICON_ROWS = (
    ("User sessions", gui_design_tree_root_icon("mobaxterm")),
    ("default", gui_design_tree_row_icon("mobaxterm", "default", "", True)),
    ("example.jump-ssh", gui_design_tree_row_icon("mobaxterm", "example.jump-ssh", "", False)),
    ("example.rdp", gui_design_tree_row_icon("mobaxterm", "example.rdp", "", False)),
    ("prod", gui_design_tree_row_icon("mobaxterm", "prod", "", True)),
    ("edge-prod", gui_design_tree_row_icon("mobaxterm", "edge-prod", "", False)),
    ("win-admin", gui_design_tree_row_icon("mobaxterm", "win-admin", "", False)),
    ("files", gui_design_tree_row_icon("mobaxterm", "files", "", True)),
    ("sftp-ops", gui_design_tree_row_icon("mobaxterm", "sftp-ops", "", False)),
    ("sync-stage", gui_design_tree_row_icon("mobaxterm", "sync-stage", "", False)),
)
EXPECTED_SECURECRT_TREE_ICON_ROWS = (
    ("Session Database", gui_design_tree_root_icon("securecrt")),
    ("Folder: Sessions", gui_design_tree_row_icon("securecrt", "Sessions", "", True)),
    ("edge-prod (SSH2)", gui_design_tree_row_icon("securecrt", "edge-prod (SSH2)", "", False)),
    ("files-prod (SFTP)", gui_design_tree_row_icon("securecrt", "files-prod (SFTP)", "", False)),
    ("Folder: Pinned", gui_design_tree_row_icon("securecrt", "Pinned", "", True)),
    ("jump-host (SSH2)", gui_design_tree_row_icon("securecrt", "jump-host (SSH2)", "", False)),
)
EXPECTED_PRODUCT_TREE_ICON_ROWS = {
    "mobaxterm": EXPECTED_MOBA_SESSION_TREE_ICON_ROWS,
    "securecrt": EXPECTED_SECURECRT_TREE_ICON_ROWS,
    "termius": (
        ("Personal Vault", gui_design_tree_root_icon("termius")),
        ("Vault / Personal", gui_design_tree_row_icon("termius", "Personal", "", True)),
        ("edge-prod  ssh host", gui_design_tree_row_icon("termius", "edge-prod", "", False)),
        ("jump-host  ssh host", gui_design_tree_row_icon("termius", "jump-host", "", False)),
        ("Vault / Teams", gui_design_tree_row_icon("termius", "Teams", "", True)),
        ("prod-cluster  ssh host", gui_design_tree_row_icon("termius", "prod-cluster", "", False)),
    ),
    "remmina": (
        ("Profile Groups", gui_design_tree_root_icon("remmina")),
        ("Group: RDP", gui_design_tree_row_icon("remmina", "RDP", "", True)),
        ("RDP - win-admin", gui_design_tree_row_icon("remmina", "win-admin", "", False)),
        ("Group: VNC", gui_design_tree_row_icon("remmina", "VNC", "", True)),
        ("VNC - linux-console", gui_design_tree_row_icon("remmina", "linux-console", "", False)),
        ("Group: SSH/SFTP", gui_design_tree_row_icon("remmina", "SSH/SFTP", "", True)),
        ("SFTP - sftp-ops", gui_design_tree_row_icon("remmina", "sftp-ops", "", False)),
    ),
    "mremoteng": (
        ("Connections", gui_design_tree_root_icon("mremoteng")),
        ("Container: prod", gui_design_tree_row_icon("mremoteng", "prod", "", True)),
        ("edge-prod [SSH]", gui_design_tree_row_icon("mremoteng", "edge-prod [SSH]", "", False)),
        ("win-admin [RDP]", gui_design_tree_row_icon("mremoteng", "win-admin [RDP]", "", False)),
        ("Container: files", gui_design_tree_row_icon("mremoteng", "files", "", True)),
        ("sftp-ops [SFTP]", gui_design_tree_row_icon("mremoteng", "sftp-ops [SFTP]", "", False)),
    ),
}
EXPECTED_PRODUCT_TREE_ICON_KEYS = {
    preset_id: {label: row.icon_key for label, row in rows}
    for preset_id, rows in EXPECTED_PRODUCT_TREE_ICON_ROWS.items()
}
EXPECTED_PRODUCT_TREE_ROW_KINDS = {
    preset_id: {label: row.row_kind for label, row in rows}
    for preset_id, rows in EXPECTED_PRODUCT_TREE_ICON_ROWS.items()
}
EXPECTED_PRODUCT_TREE_ICON_SIZES = {
    preset_id: {label: row.static_size for label, row in rows}
    for preset_id, rows in EXPECTED_PRODUCT_TREE_ICON_ROWS.items()
}
EXPECTED_SECURECRT_TREE_ICON_KEYS = EXPECTED_PRODUCT_TREE_ICON_KEYS["securecrt"]
EXPECTED_SECURECRT_TREE_ROW_KINDS = EXPECTED_PRODUCT_TREE_ROW_KINDS["securecrt"]
EXPECTED_SECURECRT_TREE_ICON_SIZES = EXPECTED_PRODUCT_TREE_ICON_SIZES["securecrt"]
EXPECTED_MOBA_SESSION_TREE_CHROME = gui_design_moba_session_tree_chrome()
EXPECTED_SECURECRT_TOP_CHROME = gui_design_securecrt_top_chrome()
EXPECTED_SECURECRT_TOP_MENU_KEYS = [item.key for item in EXPECTED_SECURECRT_TOP_CHROME.menu_items]
EXPECTED_SECURECRT_TOP_MENU_LABELS = [item.label for item in EXPECTED_SECURECRT_TOP_CHROME.menu_items]
EXPECTED_SECURECRT_TOP_TOOLBAR_KEYS = [action.key for action in EXPECTED_SECURECRT_TOP_CHROME.toolbar_actions]
EXPECTED_SECURECRT_TOP_TOOLBAR_ICON_KEYS = {
    action.key: action.icon_key for action in EXPECTED_SECURECRT_TOP_CHROME.toolbar_actions
}
EXPECTED_REMMINA_VIEWER_CONTROL_KEYS = [control.key for control in gui_design_remmina_viewer_controls()]
EXPECTED_REMMINA_PROFILE_LIST_CHROME = gui_design_remmina_profile_list_chrome()
EXPECTED_REMMINA_PROFILE_COLUMN_KEYS = [column.key for column in EXPECTED_REMMINA_PROFILE_LIST_CHROME.columns]
EXPECTED_REMMINA_PROFILE_ROW_KEYS = [row.key for row in EXPECTED_REMMINA_PROFILE_LIST_CHROME.rows]
EXPECTED_REMMINA_PROFILE_VIEWER_ROUTE = gui_design_remmina_profile_viewer_route()
EXPECTED_REMMINA_CLIPBOARD_ROUTE = gui_design_remmina_clipboard_route()
EXPECTED_TERMIUS_HEADER_CHIP_KEYS = [chip.key for chip in gui_design_termius_header_chips()]
EXPECTED_TERMIUS_HOSTS_CHROME = gui_design_termius_hosts_chrome()
EXPECTED_TERMIUS_HOSTS_ACTION_KEYS = [action.key for action in EXPECTED_TERMIUS_HOSTS_CHROME.actions]
EXPECTED_TERMIUS_HOSTS_ICON_KEYS = {action.key: action.icon_key for action in EXPECTED_TERMIUS_HOSTS_CHROME.actions}
EXPECTED_TERMIUS_HOST_IDENTITY_STRIP = gui_design_termius_host_identity_strip()
EXPECTED_TERMIUS_HOST_IDENTITY_KEYS = [field.key for field in EXPECTED_TERMIUS_HOST_IDENTITY_STRIP.fields]
EXPECTED_TERMIUS_SYNC_ROUTE = gui_design_termius_sync_route()
EXPECTED_TERMIUS_HOST_SELECTION_ROUTE = gui_design_termius_host_selection_route()
EXPECTED_MREMOTENG_TOP_CHROME = gui_design_mremoteng_top_chrome()
EXPECTED_MREMOTENG_TOP_MENU_KEYS = [item.key for item in EXPECTED_MREMOTENG_TOP_CHROME.menu_items]
EXPECTED_MREMOTENG_TOP_MENU_LABELS = [item.label for item in EXPECTED_MREMOTENG_TOP_CHROME.menu_items]
EXPECTED_MREMOTENG_TOP_TOOLBAR_KEYS = [action.key for action in EXPECTED_MREMOTENG_TOP_CHROME.toolbar_actions]
EXPECTED_MREMOTENG_TOP_TOOLBAR_ICON_KEYS = {
    action.key: action.icon_key for action in EXPECTED_MREMOTENG_TOP_CHROME.toolbar_actions
}
EXPECTED_MREMOTENG_DOCUMENT_CONTROL_KEYS = [control.key for control in gui_design_mremoteng_document_controls()]
EXPECTED_MREMOTENG_DOCUMENT_TOOLBAR_CHROME = gui_design_mremoteng_document_toolbar_chrome()
EXPECTED_MREMOTENG_PROPERTY_GRID_CHROME = gui_design_mremoteng_property_grid_chrome()
EXPECTED_MREMOTENG_CONNECTION_DOCUMENT_ROUTE = gui_design_mremoteng_connection_document_route()
EXPECTED_MREMOTENG_PROPERTY_COLUMN_KEYS = [column.key for column in EXPECTED_MREMOTENG_PROPERTY_GRID_CHROME.columns]
EXPECTED_MREMOTENG_PROPERTY_ROW_KEYS = [row.key for row in EXPECTED_MREMOTENG_PROPERTY_GRID_CHROME.rows]
COMMON_REQUIRED_WIDGETS = {
    "profileTree": "profile tree",
    "sessionTabs": "session tabs",
    "mainToolbar": "main toolbar",
    "productWorkflowEvidence": "product workflow evidence strip",
    "productWorkspaceSurface": "product workspace evidence surface",
}
MOBA_CONNECTED_REQUIRED_WIDGETS = {
    "mobaConnectedLeftDock": "Moba connected SFTP/monitoring dock",
    "mobaSftpBrowser": "Moba SFTP browser",
    "mobaSftpFileTable": "Moba SFTP file table",
    "mobaRemoteMonitoring": "Moba remote monitoring panel",
    "mobaFollowTerminalFolder": "Moba follow terminal folder control",
    "mobaSshBanner": "Moba SSH connection banner",
    "mobaSessionEdgeControls": "Moba session edge shortcut controls",
    "mobaRightUtilityRail": "Moba right terminal utility rail",
    "mobaTelemetryBar": "Moba bottom telemetry bar",
}
NON_MOBA_REQUIRED_WIDGETS = {
    "layoutToolbar": "layout toolbar",
    "activityLog": "activity log",
}
SECURECRT_REQUIRED_WIDGETS = {
    "secureCrtMenuBar": "SecureCRT top menu bar",
    "secureCrtSessionStatusStrip": "SecureCRT session status strip",
    "secureCrtSessionManagerChrome": "SecureCRT Session Manager filter/action chrome",
}
TERMIUS_REQUIRED_WIDGETS = {
    "termiusHostsChrome": "Termius Hosts search/action chrome",
    "termiusHostIdentityStrip": "Termius host identity strip",
}
REMMINA_REQUIRED_WIDGETS = {
    "remminaProfileListChrome": "Remmina profile list chrome",
}
MREMOTENG_REQUIRED_WIDGETS = {
    "mRemoteNgMenuBar": "mRemoteNG top menu bar",
    "mRemoteNgPropertyGrid": "mRemoteNG property inheritance grid",
}
NON_MOBA_PRESENT_WIDGETS = {
    "designSelect": "view preset selector",
    "toolbarSearch": "toolbar search",
}
PRODUCT_STYLE_PRESETS = {"mobaxterm", "securecrt", "termius", "remmina", "mremoteng"}
EXPECTED_MOBA_RAIL_ROLES = {"collapse", "sessions", "favorites", "tools", "macros", "sftp"}
EXPECTED_MOBA_RAIL_LABELS = {item.role: item.label for item in gui_design_moba_rail_items() if item.label}
EXPECTED_MOBA_RAIL_ITEMS = tuple(gui_design_moba_rail_items())
EXPECTED_MOBA_RAIL_ITEM_BY_ROLE = {item.role: item for item in EXPECTED_MOBA_RAIL_ITEMS}
EXPECTED_MOBA_RAIL_CHROME = gui_design_moba_rail_chrome()
EXPECTED_MOBA_RAIL_ITEM_GEOMETRY = tuple(gui_design_moba_rail_item_geometry())
EXPECTED_MOBA_RAIL_ITEM_GEOMETRY_BY_ROLE = {geometry.role: geometry for geometry in EXPECTED_MOBA_RAIL_ITEM_GEOMETRY}
MOBA_REQUIRED_WIDGETS = {
    "mobaQuickConnectChrome": "Moba quick connect chrome",
    "quickConnect": "Moba quick connect field",
    "mobaRail": "Moba side rail",
    "mobaRibbonButton": "Moba ribbon action",
    "mobaXServerAction": "Moba X server action",
    "mobaBottomEdgeControls": "Moba bottom-edge navigation controls",
}
REQUIRED_WIDGETS = {
    **COMMON_REQUIRED_WIDGETS,
    **NON_MOBA_REQUIRED_WIDGETS,
    **NON_MOBA_PRESENT_WIDGETS,
}
LIVE_LAYOUT_CONTRACTS: dict[str, list[dict[str, object]]] = {
    "mobaxterm": [
        {
            "id": "quick-connect-top-strip",
            "object_name": "mobaQuickConnectChrome",
            "label": "Moba quick connect top strip",
            "min_width": 240,
            "min_height": 20,
            "max_y": 150,
            "max_x": 90,
        },
        {
            "id": "rail-left-edge",
            "object_name": "mobaRail",
            "label": "Moba narrow vertical rail",
            "min_width": EXPECTED_MOBA_CONNECTED_DOCK_FRAME.rail_width,
            "max_width": EXPECTED_MOBA_CONNECTED_DOCK_FRAME.rail_width + 4,
            "min_height": 280,
            "max_x": 4,
        },
        {
            "id": "connected-left-dock",
            "object_name": "mobaConnectedLeftDock",
            "label": "Moba connected SFTP/monitoring dock",
            "min_x": EXPECTED_MOBA_CONNECTED_DOCK_FRAME.dock_x - 4,
            "max_x": EXPECTED_MOBA_CONNECTED_DOCK_FRAME.dock_x + 12,
            "min_width": EXPECTED_MOBA_CONNECTED_DOCK_FRAME.dock_width - 24,
            "max_width": EXPECTED_MOBA_CONNECTED_DOCK_FRAME.dock_width + 32,
            "min_height": EXPECTED_MOBA_CONNECTED_DOCK_FRAME.dock_height - 80,
        },
        {
            "id": "sftp-file-table",
            "object_name": "mobaSftpFileTable",
            "label": "Moba connected SFTP file table",
            "min_width": 180,
            "min_height": 150,
            "max_x": 520,
        },
        {
            "id": "ssh-banner-workspace",
            "object_name": "mobaSshBanner",
            "label": "Moba SSH banner in connected workspace",
            "min_width": 420,
            "min_height": 70,
            "min_x": 300,
        },
        {
            "id": "right-utility-rail",
            "object_name": "mobaRightUtilityRail",
            "label": "Moba right terminal utility rail",
            "min_width": 18,
            "max_width": 60,
            "min_height": 300,
            "min_x": 900,
        },
        {
            "id": "session-edge-controls",
            "object_name": "mobaSessionEdgeControls",
            "label": "Moba session edge shortcut controls",
            "min_width": 18,
            "max_width": 60,
            "min_height": 40,
            "min_x": 900,
        },
        {
            "id": "bottom-telemetry",
            "object_name": "mobaTelemetryBar",
            "label": "Moba bottom telemetry strip",
            "min_width": 420,
            "max_height": 90,
            "min_x": 300,
        },
        {
            "id": "bottom-edge-controls",
            "object_name": "mobaBottomEdgeControls",
            "label": "Moba bottom-edge navigation controls",
            "min_width": 45,
            "max_width": 100,
            "max_height": 40,
            "min_x": 900,
        },
    ],
    "securecrt": [
        {"id": "session-manager-width", "object_name": "leftPanel", "label": "Session Manager sidebar", "min_width": 220, "max_width": 360, "max_x": 90},
        {
            "id": "session-manager-chrome",
            "object_name": "secureCrtSessionManagerChrome",
            "label": "SecureCRT Session Manager filter/action chrome",
            "min_width": 180,
            "min_height": 48,
            "max_x": 120,
            "max_y": 210,
        },
        {"id": "terminal-tabs-workspace", "object_name": "sessionTabs", "label": "SecureCRT terminal tabs", "min_width": 620, "min_height": 360, "min_x": 220},
        {"id": "command-log-bottom", "object_name": "activityLog", "label": "SecureCRT session log", "min_width": 620, "min_height": 70},
        {"id": "workflow-evidence", "object_name": "productWorkflowEvidence", "label": "SecureCRT workflow evidence cards", "min_width": 400, "min_height": 35},
        {"id": "session-status-strip", "object_name": "secureCrtSessionStatusStrip", "label": "SecureCRT session status strip", "min_width": 520, "min_height": 24, "min_x": 220},
        {"id": "toolbar-search", "object_name": "toolbarSearch", "label": "SecureCRT toolbar search", "min_width": 100, "max_y": 130},
    ],
    "termius": [
        {"id": "hosts-sidebar-width", "object_name": "leftPanel", "label": "Termius Hosts sidebar", "min_width": 230, "max_width": 380, "max_x": 90},
        {"id": "hosts-sidebar-chrome", "object_name": "termiusHostsChrome", "label": "Termius Hosts search/action chrome", "min_width": 180, "min_height": 48, "max_x": 120, "max_y": 210},
        {"id": "west-tab-workspace", "object_name": "sessionTabs", "label": "Termius west-tab workspace", "min_width": 620, "min_height": 360, "min_x": 230},
        {"id": "sync-activity-bottom", "object_name": "activityLog", "label": "Termius sync activity log", "min_width": 620, "min_height": 70},
        {"id": "workflow-evidence", "object_name": "productWorkflowEvidence", "label": "Termius workflow evidence cards", "min_width": 400, "min_height": 35},
        {"id": "host-identity-strip", "object_name": "termiusHostIdentityStrip", "label": "Termius host identity strip", "min_width": 520, "min_height": 24, "min_x": 230},
        {"id": "toolbar-search", "object_name": "toolbarSearch", "label": "Termius host/search control", "min_width": 100, "max_y": 130},
    ],
    "remmina": [
        {"id": "connection-profile-width", "object_name": "leftPanel", "label": "Remmina Connection Profiles sidebar", "min_width": 260, "max_width": 410, "max_x": 90},
        {"id": "profile-list-chrome", "object_name": "remminaProfileListChrome", "label": "Remmina profile list chrome", "min_width": 180, "min_height": 90, "max_x": 120, "max_y": 320},
        {"id": "viewer-tabs-workspace", "object_name": "sessionTabs", "label": "Remmina viewer tabs", "min_width": 620, "min_height": 360, "min_x": 260},
        {"id": "connection-activity-bottom", "object_name": "activityLog", "label": "Remmina connection activity log", "min_width": 620, "min_height": 70},
        {"id": "workflow-evidence", "object_name": "productWorkflowEvidence", "label": "Remmina workflow evidence cards", "min_width": 400, "min_height": 35},
        {"id": "toolbar-search", "object_name": "toolbarSearch", "label": "Remmina toolbar search", "min_width": 100, "max_y": 130},
    ],
    "mremoteng": [
        {"id": "connections-tree-width", "object_name": "leftPanel", "label": "mRemoteNG Connections sidebar", "min_width": 300, "max_width": 450, "max_x": 90},
        {"id": "document-tabs-workspace", "object_name": "sessionTabs", "label": "mRemoteNG document tabs", "min_width": 620, "min_height": 360, "min_x": 300},
        {"id": "connection-log-bottom", "object_name": "activityLog", "label": "mRemoteNG connection log", "min_width": 620, "min_height": 70},
        {"id": "workflow-evidence", "object_name": "productWorkflowEvidence", "label": "mRemoteNG workflow evidence cards", "min_width": 400, "min_height": 35},
        {"id": "property-grid", "object_name": "mRemoteNgPropertyGrid", "label": "mRemoteNG property inheritance grid", "min_width": 520, "min_height": 90, "min_x": 300},
        {
            "id": "document-tree-filter",
            "object_name": "mRemoteNgDocumentFilter",
            "label": "mRemoteNG document tree filter",
            "min_width": 150,
            "min_x": 300,
            "max_y": 360,
        },
    ],
}
LIVE_TOPOLOGY_CONTRACTS: dict[str, list[dict[str, object]]] = {
    "mobaxterm": [
        {"id": "quick-connect-above-dock", "from": "mobaQuickConnectChrome", "relation": "above", "to": "mobaConnectedLeftDock", "max_gap": 90},
        {"id": "rail-left-of-dock", "from": "mobaRail", "relation": "left_of", "to": "mobaConnectedLeftDock", "max_gap": 80},
        {"id": "dock-left-of-ssh-banner", "from": "mobaConnectedLeftDock", "relation": "left_of", "to": "mobaSshBanner", "max_gap": 120},
        {"id": "ssh-banner-left-of-right-utility", "from": "mobaSshBanner", "relation": "left_of", "to": "mobaRightUtilityRail", "min_gap": 20},
        {"id": "sftp-table-inside-dock", "from": "mobaSftpFileTable", "relation": "inside", "to": "mobaConnectedLeftDock"},
        {"id": "ssh-banner-above-telemetry", "from": "mobaSshBanner", "relation": "above", "to": "mobaTelemetryBar", "min_gap": 80},
    ],
    "securecrt": [
        {"id": "toolbar-above-tabs", "from": "layoutToolbar", "relation": "above", "to": "sessionTabs", "max_gap": 120},
        {"id": "sidebar-left-of-tabs", "from": "leftPanel", "relation": "left_of", "to": "sessionTabs", "max_gap": 80},
        {"id": "workflow-above-workspace-surface", "from": "productWorkflowEvidence", "relation": "above", "to": "productWorkspaceSurface", "max_gap": 50},
        {"id": "workspace-surface-above-log", "from": "productWorkspaceSurface", "relation": "above", "to": "activityLog", "max_gap": 180},
        {"id": "workspace-primary-left-of-secondary", "from": "productWorkspacePrimaryPane", "relation": "left_of", "to": "productWorkspaceSecondaryPane", "max_gap": 40},
    ],
    "termius": [
        {"id": "toolbar-above-tabs", "from": "layoutToolbar", "relation": "above", "to": "sessionTabs", "max_gap": 120},
        {"id": "hosts-sidebar-left-of-west-tabs", "from": "leftPanel", "relation": "left_of", "to": "sessionTabs", "max_gap": 80},
        {"id": "workflow-above-workspace-surface", "from": "productWorkflowEvidence", "relation": "above", "to": "productWorkspaceSurface", "max_gap": 50},
        {"id": "workspace-surface-above-log", "from": "productWorkspaceSurface", "relation": "above", "to": "activityLog", "max_gap": 180},
        {"id": "workspace-primary-left-of-secondary", "from": "productWorkspacePrimaryPane", "relation": "left_of", "to": "productWorkspaceSecondaryPane", "max_gap": 40},
    ],
    "remmina": [
        {"id": "toolbar-above-viewer-tabs", "from": "layoutToolbar", "relation": "above", "to": "sessionTabs", "max_gap": 120},
        {"id": "profiles-left-of-viewer-tabs", "from": "leftPanel", "relation": "left_of", "to": "sessionTabs", "max_gap": 80},
        {"id": "workflow-above-workspace-surface", "from": "productWorkflowEvidence", "relation": "above", "to": "productWorkspaceSurface", "max_gap": 50},
        {"id": "workspace-surface-above-activity", "from": "productWorkspaceSurface", "relation": "above", "to": "activityLog", "max_gap": 180},
        {"id": "workspace-primary-left-of-secondary", "from": "productWorkspacePrimaryPane", "relation": "left_of", "to": "productWorkspaceSecondaryPane", "max_gap": 40},
    ],
    "mremoteng": [
        {"id": "toolbar-above-document-tabs", "from": "layoutToolbar", "relation": "above", "to": "sessionTabs", "max_gap": 120},
        {"id": "connections-left-of-document-tabs", "from": "leftPanel", "relation": "left_of", "to": "sessionTabs", "max_gap": 80},
        {"id": "workflow-above-workspace-surface", "from": "productWorkflowEvidence", "relation": "above", "to": "productWorkspaceSurface", "max_gap": 50},
        {"id": "document-controls-above-property-grid", "from": "mRemoteNgDocumentControls", "relation": "above", "to": "mRemoteNgPropertyGrid", "max_gap": 40},
        {"id": "workspace-surface-above-log", "from": "productWorkspaceSurface", "relation": "above", "to": "activityLog", "max_gap": 180},
        {"id": "workspace-primary-left-of-secondary", "from": "productWorkspacePrimaryPane", "relation": "left_of", "to": "productWorkspaceSecondaryPane", "max_gap": 40},
    ],
}
MIN_DISTINCT_COLORS = 18
MIN_LUMINANCE_RANGE = 40
MIN_NON_BACKGROUND_RATIO = 0.08


@dataclass(frozen=True)
class RenderMetrics:
    width: int
    height: int
    sampled_pixels: int
    distinct_colors: int
    luminance_range: int
    non_background_ratio: float

    def to_dict(self) -> dict[str, object]:
        return {
            "width": self.width,
            "height": self.height,
            "sampled_pixels": self.sampled_pixels,
            "distinct_colors": self.distinct_colors,
            "luminance_range": self.luminance_range,
            "non_background_ratio": round(self.non_background_ratio, 4),
        }


@dataclass(frozen=True)
class CaptureResult:
    preset_id: str
    preset_label: str
    metrics: RenderMetrics
    path: str | None = None
    size_bytes: int | None = None
    sha256: str | None = None
    contract_evidence: dict[str, object] | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "preset_id": self.preset_id,
            "preset_label": self.preset_label,
            "metrics": self.metrics.to_dict(),
        }
        if self.path is not None:
            payload["path"] = self.path
        if self.size_bytes is not None:
            payload["size_bytes"] = self.size_bytes
        if self.sha256 is not None:
            payload["sha256"] = self.sha256
        if self.contract_evidence is not None:
            payload["contract_evidence"] = self.contract_evidence
        return payload


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check that the real PyQt6 GUI renders visible pixels.")
    parser.add_argument(
        "--preset",
        action="append",
        choices=[preset.id for preset in GUI_DESIGN_PRESETS],
        help="Preset id to capture. Can be passed more than once. Defaults to every preset.",
    )
    parser.add_argument(
        "--out-dir",
        type=Path,
        help="Write live PyQt6 screenshots and a manifest to this directory.",
    )
    parser.add_argument(
        "--require-pyqt6",
        action="store_true",
        help="Fail instead of using the fail-closed branch when PyQt6 is not installed.",
    )
    args = parser.parse_args(argv)

    selected = select_presets(args.preset)
    errors, messages = check_real_gui_render(
        selected,
        out_dir=args.out_dir,
        require_pyqt6=args.require_pyqt6,
    )
    for message in messages:
        print(f"real GUI render: {message}")
    if errors:
        for error in errors:
            print(f"real GUI render: {error}", file=sys.stderr)
        return 1
    print("real GUI render check passed")
    return 0


def select_presets(ids: list[str] | None) -> list[str]:
    if not ids:
        return [preset.id for preset in GUI_DESIGN_PRESETS]
    seen: set[str] = set()
    selected: list[str] = []
    for preset_id in ids:
        if preset_id not in seen:
            selected.append(preset_id)
            seen.add(preset_id)
    return selected


def check_real_gui_render(
    preset_ids: list[str] | None = None,
    *,
    out_dir: Path | None = None,
    require_pyqt6: bool = False,
) -> tuple[list[str], list[str]]:
    from remote_ops_workspace import gui

    selected = preset_ids or [preset.id for preset in GUI_DESIGN_PRESETS]
    if not module_available("PyQt6"):
        try:
            gui.create_main_window(["row-real-gui-render-check"], show=False)
        except gui.GuiDependencyError:
            message = "PyQt6 unavailable; GUI factory fail-closed path verified"
            if require_pyqt6:
                return ["PyQt6 is required for live GUI render capture"], [message]
            return [], [message]
        return ["GUI factory must raise GuiDependencyError when PyQt6 is unavailable"], []

    return capture_live_gui(selected, out_dir=out_dir)


def capture_live_gui(
    preset_ids: list[str],
    *,
    out_dir: Path | None = None,
) -> tuple[list[str], list[str]]:
    old_qpa = os.environ.get("QT_QPA_PLATFORM")
    old_home = os.environ.get("ROW_HOME")
    os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    captures: list[CaptureResult] = []
    errors: list[str] = []
    messages: list[str] = []
    try:
        with tempfile.TemporaryDirectory(prefix="row-real-gui-") as raw_tmp:
            os.environ["ROW_HOME"] = str(Path(raw_tmp) / "row-home")
            captures, errors, messages = _capture_live_gui(preset_ids, out_dir=out_dir)
    finally:
        restore_env("QT_QPA_PLATFORM", old_qpa)
        restore_env("ROW_HOME", old_home)

    if not errors:
        errors.extend(measured_contract_evidence_errors(captures))
    if out_dir is not None and not errors:
        write_manifest(out_dir, captures, preset_ids)
        messages.append(f"wrote live screenshot manifest to {display(out_dir / MANIFEST_NAME)}")
    return errors, messages


def _capture_live_gui(
    preset_ids: list[str],
    *,
    out_dir: Path | None,
) -> tuple[list[CaptureResult], list[str], list[str]]:
    from PyQt6.QtCore import QCoreApplication
    from PyQt6.QtWidgets import QComboBox

    from remote_ops_workspace import gui

    app, window = gui.create_main_window(["row-real-gui-render-check"], show=True)
    captures: list[CaptureResult] = []
    errors: list[str] = []
    messages: list[str] = []
    try:
        window.resize(*REQUESTED_SIZE)
        window.show()
        process_events(app)

        widget_errors = check_required_widgets(window, COMMON_REQUIRED_WIDGETS)
        if widget_errors:
            return captures, widget_errors, messages

        design_select = window.findChild(QComboBox, "designSelect")
        if design_select is None:
            return captures, ["real GUI render could not locate design selector"], messages

        for preset_id in preset_ids:
            preset = next((item for item in GUI_DESIGN_PRESETS if item.id == preset_id), None)
            if preset is None:
                errors.append(f"unknown GUI preset requested: {preset_id}")
                continue
            index = design_select.findData(preset.id)
            if index < 0:
                errors.append(f"live GUI design selector missing preset: {preset.id}")
                continue
            design_select.setCurrentIndex(index)
            window.resize(*REQUESTED_SIZE)
            process_events(app)
            preset_state_errors = prepare_preset_live_state(window, preset.id)
            process_events(app)

            preset_widget_errors = preset_state_errors
            preset_widget_errors.extend(
                check_required_widgets(
                    window,
                    required_widgets_for_preset(preset.id),
                    context=f"{preset.id} live GUI",
                )
            )
            preset_widget_errors.extend(
                check_present_widgets(
                    window,
                    present_widgets_for_preset(preset.id),
                    context=f"{preset.id} live GUI",
                )
            )
            preset_widget_errors.extend(check_preset_live_contract(window, preset.id))
            preset_widget_errors.extend(check_live_layout_contracts(window, preset.id))
            preset_widget_errors.extend(check_live_topology_contracts(window, preset.id))
            if preset_widget_errors:
                errors.extend(preset_widget_errors)
                continue

            pixmap = window.grab()
            metrics = metrics_from_qimage(pixmap.toImage())
            errors.extend(validate_metrics(preset.id, metrics))
            contract_evidence = collect_live_contract_evidence(window, preset.id)

            artifact = artifact_metadata(out_dir, pixmap, preset.id) if out_dir is not None else {}
            captures.append(
                CaptureResult(
                    preset_id=preset.id,
                    preset_label=preset.label,
                    metrics=metrics,
                    path=artifact.get("path"),
                    size_bytes=artifact.get("size_bytes"),
                    sha256=artifact.get("sha256"),
                    contract_evidence=contract_evidence,
                )
            )
            messages.append(
                f"{preset.id} captured {metrics.width}x{metrics.height}, "
                f"{metrics.distinct_colors} sampled colors"
            )
    finally:
        window.close()
        process_events(app)
        QCoreApplication.processEvents()
    return captures, errors, messages


def process_events(app: Any) -> None:
    for _ in range(4):
        app.processEvents()


def required_widgets_for_preset(preset_id: str) -> dict[str, str]:
    if preset_id == "mobaxterm":
        return {
            "sessionTabs": COMMON_REQUIRED_WIDGETS["sessionTabs"],
            "mainToolbar": COMMON_REQUIRED_WIDGETS["mainToolbar"],
            **MOBA_REQUIRED_WIDGETS,
            **MOBA_CONNECTED_REQUIRED_WIDGETS,
        }
    return {
        **COMMON_REQUIRED_WIDGETS,
        **NON_MOBA_REQUIRED_WIDGETS,
        **(SECURECRT_REQUIRED_WIDGETS if preset_id == "securecrt" else {}),
        **(TERMIUS_REQUIRED_WIDGETS if preset_id == "termius" else {}),
        **(REMMINA_REQUIRED_WIDGETS if preset_id == "remmina" else {}),
        **(MREMOTENG_REQUIRED_WIDGETS if preset_id == "mremoteng" else {}),
    }


def present_widgets_for_preset(preset_id: str) -> dict[str, str]:
    if preset_id == "mobaxterm":
        return {}
    return NON_MOBA_PRESENT_WIDGETS


def prepare_preset_live_state(window: Any, preset_id: str) -> list[str]:
    if preset_id != "mobaxterm":
        return prepare_product_reference_tab(window, preset_id)
    return prepare_moba_connected_reference(window)


def prepare_moba_connected_reference(window: Any) -> list[str]:
    try:
        profile = window.store.get(PRESET_REFERENCE_PROFILES["mobaxterm"])
        window.launch_profile(profile, dry_run=False, prefix="CI CONNECTED")
    except (KeyError, LauncherError, ValueError) as exc:
        return [f"mobaxterm live GUI could not open connected reference profile: {exc}"]
    return []


def prepare_product_reference_tab(window: Any, preset_id: str) -> list[str]:
    profile_name = PRESET_REFERENCE_PROFILES.get(preset_id)
    if profile_name is None:
        return []
    try:
        profile = window.store.get(profile_name)
        window.launch_profile(profile, dry_run=False, prefix="CI REFERENCE")
    except (KeyError, LauncherError, ValueError) as exc:
        return [f"{preset_id} live GUI could not open reference profile {profile_name}: {exc}"]
    home_index = window.find_tab_by_role("home")
    if home_index >= 0:
        window.tabs.setCurrentIndex(home_index)
    return []


def check_preset_live_contract(window: Any, preset_id: str) -> list[str]:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import (
        QCheckBox,
        QFrame,
        QLabel,
        QLineEdit,
        QTabWidget,
        QTextEdit,
        QToolButton,
        QTreeWidget,
        QWidget,
    )

    errors: list[str] = []
    preset = next((item for item in GUI_DESIGN_PRESETS if item.id == preset_id), None)
    if preset is None:
        return [f"unknown GUI preset requested: {preset_id}"]

    tabs = window.findChild(QTabWidget, "sessionTabs")
    if tabs is None:
        return [f"{preset_id} live GUI missing session tabs for preset contract"]
    expected_tab_position = tab_position_name(preset.tab_position)
    actual_tab_position = tabs.tabPosition().name.lower()
    if expected_tab_position not in actual_tab_position:
        errors.append(
            f"{preset_id} live GUI tab position {actual_tab_position} must include {expected_tab_position}"
        )
    home_label = gui_design_home_tab_label(preset_id)
    tab_labels = live_tab_labels(tabs)
    if tabs.count() > 0 and home_label not in tab_labels:
        errors.append(f"{preset_id} live GUI tabs must include home tab label: {home_label}")
    expected_reference_tab = EXPECTED_LIVE_REFERENCE_TAB_LABELS.get(preset_id)
    if expected_reference_tab is not None and expected_reference_tab not in tab_labels:
        errors.append(f"{preset_id} live GUI tabs must include reference tab label: {expected_reference_tab}")

    if preset_id != "mobaxterm":
        title, subtitle = gui_design_sidebar_copy(preset_id)
        errors.extend(check_label_text(window, "leftPanelTitle", title, preset_id))
        errors.extend(check_label_text(window, "leftPanelSubtitle", subtitle, preset_id))
        toolbar_labels = {button.text() for button in window.findChildren(QToolButton)}
        for _key, label, _tooltip in gui_design_toolbar_actions(preset_id)[:6]:
            if label not in toolbar_labels:
                errors.append(f"{preset_id} live GUI toolbar missing action label: {label}")
    else:
        errors.extend(check_live_moba_quick_connect_chrome(window))
        quick_connect = window.findChild(QLineEdit, "quickConnect")
        if quick_connect is None or not quick_connect.isVisible():
            errors.append("mobaxterm live GUI quick connect field must be visible")
        expected_stack_properties = {
            "mobaTopStackTitlebarHeight": EXPECTED_MOBA_TOP_STACK_GEOMETRY.titlebar_height,
            "mobaTopStackMenuY": EXPECTED_MOBA_TOP_STACK_GEOMETRY.menu_y,
            "mobaTopStackMenuHeight": EXPECTED_MOBA_TOP_STACK_GEOMETRY.menu_height,
            "mobaTopStackRibbonY": EXPECTED_MOBA_TOP_STACK_GEOMETRY.ribbon_y,
            "mobaTopStackRibbonHeight": EXPECTED_MOBA_TOP_STACK_GEOMETRY.ribbon_height,
            "mobaTopStackQuickConnectY": EXPECTED_MOBA_TOP_STACK_GEOMETRY.quick_connect_y,
            "mobaTopStackQuickConnectHeight": EXPECTED_MOBA_TOP_STACK_GEOMETRY.quick_connect_height,
            "mobaTopStackLeftDockY": EXPECTED_MOBA_TOP_STACK_GEOMETRY.left_dock_y,
            "mobaTopStackTabY": EXPECTED_MOBA_TOP_STACK_GEOMETRY.tab_y,
            "mobaTopStackTabHeight": EXPECTED_MOBA_TOP_STACK_GEOMETRY.tab_height,
            "mobaTopStackTerminalContentY": EXPECTED_MOBA_TOP_STACK_GEOMETRY.terminal_content_y,
            "mobaTopStackStatusHeight": EXPECTED_MOBA_TOP_STACK_GEOMETRY.status_height,
            "mobaTopStackSideWidth": EXPECTED_MOBA_TOP_STACK_GEOMETRY.side_width,
            "mobaTopStackRailWidth": EXPECTED_MOBA_TOP_STACK_GEOMETRY.rail_width,
        }
        for property_name, expected_value in expected_stack_properties.items():
            if int(window.property(property_name) or 0) != expected_value:
                errors.append(f"mobaxterm live GUI top-stack property {property_name} drifted")
        menu_bar = window.menuBar()
        if int(menu_bar.property("mobaTopStackMenuY") or 0) != EXPECTED_MOBA_TOP_STACK_GEOMETRY.menu_y:
            errors.append("mobaxterm live GUI menu row y metadata drifted")
        if int(menu_bar.property("mobaTopStackMenuHeight") or 0) != EXPECTED_MOBA_TOP_STACK_GEOMETRY.menu_height:
            errors.append("mobaxterm live GUI menu row height metadata drifted")
        main_toolbar = window.findChild(QWidget, "mainToolbar")
        if main_toolbar is None:
            errors.append("mobaxterm live GUI missing main toolbar for top-stack geometry")
        else:
            if int(main_toolbar.property("mobaTopStackRibbonY") or 0) != EXPECTED_MOBA_TOP_STACK_GEOMETRY.ribbon_y:
                errors.append("mobaxterm live GUI ribbon y metadata drifted")
            if int(main_toolbar.property("mobaTopStackRibbonHeight") or 0) != (
                EXPECTED_MOBA_TOP_STACK_GEOMETRY.ribbon_height
            ):
                errors.append("mobaxterm live GUI ribbon height metadata drifted")
            if main_toolbar.minimumHeight() != EXPECTED_MOBA_TOP_STACK_GEOMETRY.ribbon_height:
                errors.append("mobaxterm live GUI ribbon minimum height drifted")
            if main_toolbar.maximumHeight() != EXPECTED_MOBA_TOP_STACK_GEOMETRY.ribbon_height:
                errors.append("mobaxterm live GUI ribbon maximum height drifted")
        quick_panel = window.findChild(QWidget, "mobaQuickConnectChrome")
        if quick_panel is not None:
            if int(quick_panel.property("mobaTopStackQuickConnectY") or 0) != (
                EXPECTED_MOBA_TOP_STACK_GEOMETRY.quick_connect_y
            ):
                errors.append("mobaxterm live GUI quick-connect y metadata drifted")
            if int(quick_panel.property("mobaTopStackQuickConnectHeight") or 0) != (
                EXPECTED_MOBA_TOP_STACK_GEOMETRY.quick_connect_height
            ):
                errors.append("mobaxterm live GUI quick-connect stack height metadata drifted")
        tabs_widget = window.findChild(QWidget, "sessionTabs")
        if tabs_widget is not None:
            if int(tabs_widget.property("mobaTopStackTabY") or 0) != EXPECTED_MOBA_TOP_STACK_GEOMETRY.tab_y:
                errors.append("mobaxterm live GUI tab-strip y metadata drifted")
            if int(tabs_widget.property("mobaTopStackTabHeight") or 0) != EXPECTED_MOBA_TOP_STACK_GEOMETRY.tab_height:
                errors.append("mobaxterm live GUI tab-strip height metadata drifted")
        connected_dock = window.findChild(QFrame, "mobaConnectedLeftDock")
        sftp_browser = window.findChild(QFrame, "mobaSftpBrowser")
        expected_connected_frame_properties = {
            "mobaConnectedDockSideWidth": EXPECTED_MOBA_CONNECTED_DOCK_FRAME.side_width,
            "mobaConnectedDockRailWidth": EXPECTED_MOBA_CONNECTED_DOCK_FRAME.rail_width,
            "mobaConnectedDockX": EXPECTED_MOBA_CONNECTED_DOCK_FRAME.dock_x,
            "mobaConnectedDockY": EXPECTED_MOBA_CONNECTED_DOCK_FRAME.dock_y,
            "mobaConnectedDockWidth": EXPECTED_MOBA_CONNECTED_DOCK_FRAME.dock_width,
            "mobaConnectedDockHeight": EXPECTED_MOBA_CONNECTED_DOCK_FRAME.dock_height,
            "mobaConnectedDockWorkspaceX": EXPECTED_MOBA_CONNECTED_DOCK_FRAME.workspace_x,
            "mobaConnectedDockQuickConnectY": EXPECTED_MOBA_CONNECTED_DOCK_FRAME.quick_connect_y,
            "mobaConnectedDockQuickConnectHeight": EXPECTED_MOBA_CONNECTED_DOCK_FRAME.quick_connect_height,
            "mobaConnectedDockStatusY": EXPECTED_MOBA_CONNECTED_DOCK_FRAME.status_y,
        }
        for widget_name, widget in [
            ("connected left dock", connected_dock),
            ("SFTP browser", sftp_browser),
        ]:
            if widget is None:
                errors.append(f"mobaxterm live GUI missing {widget_name} frame for connected-dock metadata")
                continue
            for property_name, expected_value in expected_connected_frame_properties.items():
                if int(widget.property(property_name) or 0) != expected_value:
                    errors.append(
                        f"mobaxterm live GUI {widget_name} connected-dock frame property "
                        f"{property_name} drifted"
                    )
        top_menu_actions = [action for action in window.menuBar().actions() if action.isVisible()]
        top_menu_labels = [action.text() for action in top_menu_actions]
        top_menu_keys = [str(action.property("mobaTopMenuKey") or "") for action in top_menu_actions]
        if top_menu_labels != EXPECTED_MOBA_TOP_MENU_LABELS:
            errors.append(
                f"mobaxterm live GUI top menu labels {top_menu_labels!r} "
                f"must equal {EXPECTED_MOBA_TOP_MENU_LABELS!r}"
            )
        if top_menu_keys != EXPECTED_MOBA_TOP_MENU_KEYS:
            errors.append(
                f"mobaxterm live GUI top menu keys {top_menu_keys!r} "
                f"must equal {EXPECTED_MOBA_TOP_MENU_KEYS!r}"
            )
        for action in top_menu_actions:
            key = str(action.property("mobaTopMenuKey") or "")
            if key not in EXPECTED_MOBA_TOP_MENU_GEOMETRY_BY_KEY:
                continue
            expected_geometry = EXPECTED_MOBA_TOP_MENU_GEOMETRY_BY_KEY[key]
            actual_geometry_keys = list(action.property("mobaTopMenuGeometryKeys") or [])
            if actual_geometry_keys and actual_geometry_keys != [item.key for item in EXPECTED_MOBA_TOP_MENU_GEOMETRY]:
                errors.append(f"mobaxterm live GUI top menu {key!r} geometry key order drifted")
            geometry_properties = {
                "mobaTopMenuStaticX": expected_geometry.static_x,
                "mobaTopMenuWidth": expected_geometry.width,
                "mobaTopMenuLabelY": expected_geometry.label_y,
                "mobaTopMenuLabelFontSize": expected_geometry.label_font_size,
                "mobaTopMenuGapAfter": expected_geometry.gap_after,
            }
            for property_name, expected_value in geometry_properties.items():
                if action.property(property_name) != expected_value:
                    errors.append(f"mobaxterm live GUI top menu {key!r} property {property_name} drifted")
        moba_buttons = {button.text(): button for button in window.findChildren(QToolButton)}
        for label in ["Session", "Servers", "Tools", "Sessions", "Tunneling"]:
            if label not in moba_buttons:
                errors.append(f"mobaxterm live GUI ribbon missing action label: {label}")
        expected_icons = {action.label: action.icon_key for action in gui_design_moba_ribbon_actions()}
        expected_icons.update({action.label: action.icon_key for action in EXPECTED_MOBA_RIBBON_EDGE_ACTIONS})
        for label, icon_key in expected_icons.items():
            button = moba_buttons.get(label)
            if button is None:
                errors.append(f"mobaxterm live GUI generated icon button missing: {label}")
                continue
            actual_icon_key = str(button.property("mobaIconKey") or "")
            if actual_icon_key != icon_key:
                errors.append(
                    f"mobaxterm live GUI {label} mobaIconKey {actual_icon_key!r} must equal {icon_key!r}"
            )
            if button.icon().isNull():
                errors.append(f"mobaxterm live GUI {label} must use a generated ribbon icon")
            expected_geometry = EXPECTED_MOBA_RIBBON_ACTION_GEOMETRY_BY_KEY[icon_key]
            actual_geometry_keys = list(button.property("mobaRibbonActionGeometryKeys") or [])
            if actual_geometry_keys and actual_geometry_keys != [item.key for item in EXPECTED_MOBA_RIBBON_ACTION_GEOMETRY]:
                errors.append(f"mobaxterm live GUI {label} ribbon geometry key order drifted")
            geometry_properties = {
                "mobaRibbonStaticX": expected_geometry.static_x,
                "mobaRibbonStaticWidth": expected_geometry.width,
                "mobaRibbonIconX": expected_geometry.icon_x,
                "mobaRibbonIconY": expected_geometry.icon_y,
                "mobaRibbonIconSize": expected_geometry.icon_size,
                "mobaRibbonLabelX": expected_geometry.label_x,
                "mobaRibbonLabelY": expected_geometry.label_y,
                "mobaRibbonLabelFontSize": expected_geometry.label_font_size,
                "mobaRibbonSeparatorBefore": expected_geometry.separator_before,
                "mobaRibbonSeparatorX": expected_geometry.separator_x,
                "mobaRibbonSeparatorTop": expected_geometry.separator_top,
                "mobaRibbonSeparatorBottom": expected_geometry.separator_bottom,
                "mobaRibbonActiveOutlineX": expected_geometry.active_outline_x,
                "mobaRibbonActiveOutlineY": expected_geometry.active_outline_y,
                "mobaRibbonActiveOutlineWidth": expected_geometry.active_outline_width,
                "mobaRibbonActiveOutlineHeight": expected_geometry.active_outline_height,
            }
            for property_name, expected_value in geometry_properties.items():
                if button.property(property_name) != expected_value:
                    errors.append(f"mobaxterm live GUI {label} ribbon property {property_name} drifted")
        rail_widget = window.findChild(QWidget, "mobaRail")
        if rail_widget is not None:
            rail_properties = {
                "mobaRailStaticWidth": EXPECTED_MOBA_RAIL_CHROME.rail_width,
                "mobaRailIconX": EXPECTED_MOBA_RAIL_CHROME.icon_x,
                "mobaRailStaticIconSize": EXPECTED_MOBA_RAIL_CHROME.static_icon_size,
                "mobaRailLiveIconSize": EXPECTED_MOBA_RAIL_CHROME.live_icon_size,
                "mobaRailButtonHeight": EXPECTED_MOBA_RAIL_CHROME.button_height,
                "mobaRailLabelHeight": EXPECTED_MOBA_RAIL_CHROME.label_height,
            }
            for property_name, expected_value in rail_properties.items():
                if int(rail_widget.property(property_name) or -1) != expected_value:
                    errors.append(f"mobaxterm live GUI rail property {property_name} drifted")
            if str(rail_widget.property("mobaRailRenderSource") or "") != EXPECTED_MOBA_RAIL_CHROME.render_source:
                errors.append("mobaxterm live GUI rail render source drifted")
            if rail_widget.width() != EXPECTED_MOBA_RAIL_CHROME.rail_width:
                errors.append("mobaxterm live GUI rail live width drifted")
        rail_buttons = [
            button
            for button in window.findChildren(QToolButton)
            if button.objectName() in {"mobaRailButton", "mobaRailAccent"}
        ]
        rail_roles = {str(button.property("mobaRailRole") or "") for button in rail_buttons}
        missing_roles = sorted(EXPECTED_MOBA_RAIL_ROLES - rail_roles)
        if missing_roles:
            errors.append(f"mobaxterm live GUI rail missing roles: {missing_roles}")
        for button in rail_buttons:
            role = str(button.property("mobaRailRole") or "")
            if "\n" in button.text():
                errors.append(f"mobaxterm live GUI rail role {role!r} must not use stacked text")
            if button.icon().isNull():
                errors.append(f"mobaxterm live GUI rail role {role!r} must use a generated icon")
            expected_item = EXPECTED_MOBA_RAIL_ITEM_BY_ROLE.get(role)
            expected_geometry = EXPECTED_MOBA_RAIL_ITEM_GEOMETRY_BY_ROLE.get(role)
            if expected_item is not None:
                if str(button.property("mobaRailIconKey") or "") != expected_item.icon_key:
                    errors.append(f"mobaxterm live GUI rail role {role!r} icon key drifted")
                if str(button.property("mobaRailStaticIconKey") or "") != expected_item.rail_icon_key:
                    errors.append(f"mobaxterm live GUI rail role {role!r} static icon key drifted")
            if expected_geometry is not None:
                geometry_properties = {
                    "mobaRailStaticIconX": EXPECTED_MOBA_RAIL_CHROME.icon_x,
                    "mobaRailStaticIconY": expected_geometry.static_icon_y,
                    "mobaRailStaticIconSize": EXPECTED_MOBA_RAIL_CHROME.static_icon_size,
                    "mobaRailLiveIconSize": EXPECTED_MOBA_RAIL_CHROME.live_icon_size,
                    "mobaRailButtonWidth": EXPECTED_MOBA_RAIL_CHROME.button_width,
                    "mobaRailButtonHeight": EXPECTED_MOBA_RAIL_CHROME.button_height,
                    "mobaRailActiveX": EXPECTED_MOBA_RAIL_CHROME.active_x,
                    "mobaRailActiveYOffset": EXPECTED_MOBA_RAIL_CHROME.active_y_offset,
                    "mobaRailActiveWidth": EXPECTED_MOBA_RAIL_CHROME.active_width,
                    "mobaRailActiveHeight": EXPECTED_MOBA_RAIL_CHROME.active_height,
                }
                for property_name, expected_value in geometry_properties.items():
                    if int(button.property(property_name) or -1) != expected_value:
                        errors.append(f"mobaxterm live GUI rail role {role!r} property {property_name} drifted")
                if str(button.property("mobaRailRenderSource") or "") != EXPECTED_MOBA_RAIL_CHROME.render_source:
                    errors.append(f"mobaxterm live GUI rail role {role!r} render source drifted")
                if button.iconSize().width() != EXPECTED_MOBA_RAIL_CHROME.live_icon_size:
                    errors.append(f"mobaxterm live GUI rail role {role!r} icon size drifted")
                if button.width() != EXPECTED_MOBA_RAIL_CHROME.button_width:
                    errors.append(f"mobaxterm live GUI rail role {role!r} button width drifted")
                if button.height() != EXPECTED_MOBA_RAIL_CHROME.button_height:
                    errors.append(f"mobaxterm live GUI rail role {role!r} button height drifted")
        rail_labels = {
            str(label.property("mobaRailRole") or ""): label
            for label in window.findChildren(QLabel, "mobaRailLabel")
        }
        for role, expected_label in EXPECTED_MOBA_RAIL_LABELS.items():
            label = rail_labels.get(role)
            if label is None or label.text() != expected_label:
                errors.append(f"mobaxterm live GUI rail role {role!r} missing vertical label: {expected_label}")
                continue
            expected_geometry = EXPECTED_MOBA_RAIL_ITEM_GEOMETRY_BY_ROLE.get(role)
            if expected_geometry is None:
                continue
            label_properties = {
                "mobaRailStaticLabelY": expected_geometry.static_label_y,
                "mobaRailLabelWidth": EXPECTED_MOBA_RAIL_CHROME.label_width,
                "mobaRailLabelHeight": EXPECTED_MOBA_RAIL_CHROME.label_height,
                "mobaRailLabelFontSize": EXPECTED_MOBA_RAIL_CHROME.label_font_size,
            }
            for property_name, expected_value in label_properties.items():
                if int(label.property(property_name) or -1) != expected_value:
                    errors.append(f"mobaxterm live GUI rail label {role!r} property {property_name} drifted")
            if label.width() != EXPECTED_MOBA_RAIL_CHROME.label_width:
                errors.append(f"mobaxterm live GUI rail label {role!r} width drifted")
            if label.height() != EXPECTED_MOBA_RAIL_CHROME.label_height:
                errors.append(f"mobaxterm live GUI rail label {role!r} height drifted")
        sftp_buttons = window.findChildren(QToolButton, "mobaSftpAction")
        sftp_action_keys = {str(button.property("mobaSftpActionKey") or "") for button in sftp_buttons}
        missing_sftp_actions = sorted(EXPECTED_MOBA_SFTP_ACTION_KEYS - sftp_action_keys)
        if missing_sftp_actions:
            errors.append(f"mobaxterm live GUI SFTP dock missing action keys: {missing_sftp_actions}")
        for button in sftp_buttons:
            key = str(button.property("mobaSftpActionKey") or "")
            icon_key = str(button.property("mobaSftpIconKey") or "")
            expected_action = next((action for action in EXPECTED_MOBA_SFTP_ACTIONS if action.key == key), None)
            expected_geometry = EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_GEOMETRY_BY_KEY.get(key)
            if key in EXPECTED_MOBA_SFTP_ACTION_KEYS and not icon_key:
                errors.append(f"mobaxterm live GUI SFTP action {key!r} missing icon key")
            if expected_action is not None:
                group_key = str(button.property("mobaSftpActionGroupKey") or "")
                separator_after = bool(button.property("mobaSftpActionSeparatorAfter"))
                if group_key != expected_action.group_key:
                    errors.append(f"mobaxterm live GUI SFTP action {key!r} group key drifted")
                if separator_after != expected_action.separator_after:
                    errors.append(f"mobaxterm live GUI SFTP action {key!r} separator flag drifted")
            if expected_geometry is not None:
                property_checks = {
                    "mobaSftpActionStaticX": expected_geometry.button_x,
                    "mobaSftpActionStaticY": expected_geometry.button_y,
                    "mobaSftpActionButtonSize": expected_geometry.button_size,
                    "mobaSftpActionIconX": expected_geometry.icon_x,
                    "mobaSftpActionIconY": expected_geometry.icon_y,
                    "mobaSftpActionIconSize": expected_geometry.icon_size,
                    "mobaSftpActionSeparatorX": expected_geometry.separator_x,
                }
                for property_name, expected_value in property_checks.items():
                    actual_value = int(button.property(property_name) or 0)
                    if actual_value != expected_value:
                        errors.append(
                            f"mobaxterm live GUI SFTP action {key!r} "
                            f"{property_name} drifted: {actual_value}"
                        )
            if int(button.property("mobaSftpActionButtonSize") or 0) != EXPECTED_MOBA_SFTP_DOCK_LAYOUT.toolbar_icon_step:
                errors.append(f"mobaxterm live GUI SFTP action {key!r} button size metadata drifted")
            if int(button.property("mobaSftpActionIconSize") or 0) != EXPECTED_MOBA_SFTP_DOCK_LAYOUT.toolbar_icon_size:
                errors.append(f"mobaxterm live GUI SFTP action {key!r} icon size metadata drifted")
            if button.icon().isNull():
                errors.append(f"mobaxterm live GUI SFTP action {key!r} must use a generated icon")
        sftp_separators = window.findChildren(QFrame, "mobaSftpToolbarSeparator")
        separator_keys = [str(separator.property("mobaSftpSeparatorAfterActionKey") or "") for separator in sftp_separators]
        if separator_keys != EXPECTED_MOBA_SFTP_SEPARATOR_AFTER_KEYS:
            errors.append(f"mobaxterm live GUI SFTP toolbar separator order drifted: {separator_keys}")
        for separator in sftp_separators:
            if int(separator.property("mobaSftpSeparatorWidth") or 0) != (
                EXPECTED_MOBA_SFTP_DOCK_LAYOUT.toolbar_separator_width
            ):
                errors.append("mobaxterm live GUI SFTP toolbar separator width metadata drifted")
        sftp_path = window.findChild(QLineEdit, "mobaSftpPath")
        if sftp_path is None:
            errors.append("mobaxterm live GUI SFTP dock missing remote path strip")
        else:
            if not sftp_path.text().startswith("/"):
                errors.append("mobaxterm live GUI SFTP path strip must show a remote absolute path")
            if sftp_path.placeholderText() != EXPECTED_MOBA_SFTP_BROWSER_CHROME.path_placeholder:
                errors.append("mobaxterm live GUI SFTP path placeholder drifted")
            dropdown_marker = str(sftp_path.property("mobaSftpPathDropdownMarker") or "")
            if dropdown_marker != EXPECTED_MOBA_SFTP_BROWSER_CHROME.dropdown_marker:
                errors.append(
                    f"mobaxterm live GUI SFTP path dropdown marker {dropdown_marker!r} "
                    f"must equal {EXPECTED_MOBA_SFTP_BROWSER_CHROME.dropdown_marker!r}"
                )
            if int(sftp_path.property("mobaSftpPathHeight") or 0) != EXPECTED_MOBA_SFTP_DOCK_LAYOUT.path_height:
                errors.append("mobaxterm live GUI SFTP path height metadata drifted")
            path_properties = {
                "mobaSftpPathTextX": EXPECTED_MOBA_SFTP_BROWSER_CHROME.path_text_x,
                "mobaSftpPathTextY": EXPECTED_MOBA_SFTP_BROWSER_CHROME.path_text_y,
                "mobaSftpPathFontSize": EXPECTED_MOBA_SFTP_BROWSER_CHROME.path_font_size,
                "mobaSftpDropdownRightOffset": EXPECTED_MOBA_SFTP_BROWSER_CHROME.dropdown_right_offset,
                "mobaSftpDropdownY": EXPECTED_MOBA_SFTP_BROWSER_CHROME.dropdown_y,
                "mobaSftpDropdownFontSize": EXPECTED_MOBA_SFTP_BROWSER_CHROME.dropdown_font_size,
            }
            for property_name, expected_value in path_properties.items():
                if sftp_path.property(property_name) != expected_value:
                    errors.append(f"mobaxterm live GUI SFTP path property {property_name} drifted")
        sftp_table = window.findChild(QTreeWidget, "mobaSftpFileTable")
        if sftp_table is None:
            errors.append("mobaxterm live GUI SFTP dock missing file table")
        else:
            header = sftp_table.headerItem()
            headers = [header.text(index) for index in range(sftp_table.columnCount())]
            if headers != EXPECTED_MOBA_SFTP_COLUMN_LABELS:
                errors.append(f"mobaxterm live GUI SFTP file table headers drifted: {headers}")
            column_keys = list(sftp_table.property("mobaSftpColumnKeys") or [])
            if column_keys != EXPECTED_MOBA_SFTP_COLUMN_KEYS:
                errors.append(f"mobaxterm live GUI SFTP file table column keys drifted: {column_keys}")
            column_widths = list(sftp_table.property("mobaSftpColumnWidths") or [])
            if column_widths != EXPECTED_MOBA_SFTP_COLUMN_WIDTHS:
                errors.append(f"mobaxterm live GUI SFTP file table column width metadata drifted: {column_widths}")
            actual_column_widths = [sftp_table.columnWidth(index) for index in range(sftp_table.columnCount())]
            if actual_column_widths[: len(EXPECTED_MOBA_SFTP_COLUMN_WIDTHS)] != EXPECTED_MOBA_SFTP_COLUMN_WIDTHS:
                errors.append(f"mobaxterm live GUI SFTP file table column widths drifted: {actual_column_widths}")
            if str(sftp_table.property("mobaSftpParentRowLabel") or "") != (
                EXPECTED_MOBA_SFTP_BROWSER_CHROME.parent_row_label
            ):
                errors.append("mobaxterm live GUI SFTP parent-row label metadata drifted")
            if str(sftp_table.property("mobaSftpParentRowKind") or "") != (
                EXPECTED_MOBA_SFTP_BROWSER_CHROME.parent_row_kind
            ):
                errors.append("mobaxterm live GUI SFTP parent-row kind metadata drifted")
            if str(sftp_table.property("mobaSftpSelectedRowKind") or "") != (
                EXPECTED_MOBA_SFTP_BROWSER_CHROME.selected_row_kind
            ):
                errors.append("mobaxterm live GUI SFTP selected-row kind metadata drifted")
            if int(sftp_table.property("mobaSftpHeaderHeight") or 0) != EXPECTED_MOBA_SFTP_DOCK_LAYOUT.table_header_height:
                errors.append("mobaxterm live GUI SFTP file table header height metadata drifted")
            table_properties = {
                "mobaSftpHeaderLabelY": EXPECTED_MOBA_SFTP_BROWSER_CHROME.header_label_y,
                "mobaSftpHeaderFontSize": EXPECTED_MOBA_SFTP_BROWSER_CHROME.header_font_size,
                "mobaSftpRowTopOffset": EXPECTED_MOBA_SFTP_BROWSER_CHROME.row_top_offset,
                "mobaSftpRowIconX": EXPECTED_MOBA_SFTP_BROWSER_CHROME.row_icon_x,
                "mobaSftpRowIconYOffset": EXPECTED_MOBA_SFTP_BROWSER_CHROME.row_icon_y_offset,
                "mobaSftpRowNameX": EXPECTED_MOBA_SFTP_BROWSER_CHROME.row_name_x,
                "mobaSftpRowSizeX": EXPECTED_MOBA_SFTP_BROWSER_CHROME.row_size_x,
                "mobaSftpRowModifiedX": EXPECTED_MOBA_SFTP_BROWSER_CHROME.row_modified_x,
                "mobaSftpRowTextYOffset": EXPECTED_MOBA_SFTP_BROWSER_CHROME.row_text_y_offset,
                "mobaSftpRowTextFontSize": EXPECTED_MOBA_SFTP_BROWSER_CHROME.row_text_font_size,
                "mobaSftpRowModifiedFontSize": EXPECTED_MOBA_SFTP_BROWSER_CHROME.row_modified_font_size,
            }
            for property_name, expected_value in table_properties.items():
                if sftp_table.property(property_name) != expected_value:
                    errors.append(f"mobaxterm live GUI SFTP file table property {property_name} drifted")
            if int(sftp_table.property("mobaSftpRowHeight") or 0) != EXPECTED_MOBA_SFTP_DOCK_LAYOUT.file_row_height:
                errors.append("mobaxterm live GUI SFTP file row height metadata drifted")
            if list(sftp_table.property("mobaSftpFileRowIconKinds") or []) != [
                row_icon.kind for row_icon in EXPECTED_MOBA_SFTP_FILE_ROW_ICONS
            ]:
                errors.append("mobaxterm live GUI SFTP file row icon-kind metadata drifted")
            if list(sftp_table.property("mobaSftpFileRowIconKeys") or []) != [
                row_icon.icon_key for row_icon in EXPECTED_MOBA_SFTP_FILE_ROW_ICONS
            ]:
                errors.append("mobaxterm live GUI SFTP file row icon-key metadata drifted")
            routed_row_properties = {
                "mobaSftpRoutedRowsKey": EXPECTED_MOBA_SFTP_ROUTED_FILE_ROWS.key,
                "mobaSftpRoutedRowsRole": EXPECTED_MOBA_SFTP_ROUTED_FILE_ROWS.route_role,
                "mobaSftpRoutedRowsFollowRouteKey": EXPECTED_MOBA_SFTP_ROUTED_FILE_ROWS.follow_route_key,
                "mobaSftpRoutedRowsTargetTableObject": EXPECTED_MOBA_SFTP_ROUTED_FILE_ROWS.target_table_object,
                "mobaSftpRoutedRowsContractProperty": EXPECTED_MOBA_SFTP_ROUTED_FILE_ROWS.row_contract_property,
                "mobaSftpRoutedRowsRouteProperty": EXPECTED_MOBA_SFTP_ROUTED_FILE_ROWS.row_route_property,
                "mobaSftpRoutedRowsPathProperty": EXPECTED_MOBA_SFTP_ROUTED_FILE_ROWS.row_path_property,
                "mobaSftpRoutedRowsIndexProperty": EXPECTED_MOBA_SFTP_ROUTED_FILE_ROWS.row_index_property,
                "mobaSftpRoutedRowsSelectedProperty": EXPECTED_MOBA_SFTP_ROUTED_FILE_ROWS.row_selected_property,
                "mobaSftpRoutedRowsParentRowName": EXPECTED_MOBA_SFTP_ROUTED_FILE_ROWS.parent_row_name,
                "mobaSftpRoutedRowsSelectedRowKind": EXPECTED_MOBA_SFTP_ROUTED_FILE_ROWS.selected_row_kind,
                "mobaSftpRoutedRowsRenderSource": EXPECTED_MOBA_SFTP_ROUTED_FILE_ROWS.render_source,
                "mobaSftpRoutedRowsRoutePathProperty": EXPECTED_MOBA_SFTP_FOLLOW_FOLDER_ROUTE.target_path_property,
            }
            for property_name, expected_value in routed_row_properties.items():
                if str(sftp_table.property(property_name) or "") != expected_value:
                    errors.append(f"mobaxterm live GUI SFTP routed-row table property {property_name} drifted")
            routed_rows_source_path = str(sftp_table.property("mobaSftpRoutedRowsSourcePath") or "")
            if not routed_rows_source_path.startswith("/"):
                errors.append("mobaxterm live GUI SFTP routed-row table missing absolute source path")
            elif sftp_path is not None and routed_rows_source_path != sftp_path.text():
                errors.append("mobaxterm live GUI SFTP routed-row table source path must match SFTP path")
            if not bool(sftp_table.property("mobaSftpRoutedRowsEnabled")):
                errors.append("mobaxterm live GUI SFTP routed-row table must be enabled by follow-folder state")
            routed_rows_plan = str(sftp_table.property("mobaSftpRoutedRowsPlan") or "")
            if "ls -la /" not in routed_rows_plan:
                errors.append("mobaxterm live GUI SFTP routed-row table missing follow-folder list plan")
            if sftp_table.topLevelItemCount() < 4:
                errors.append("mobaxterm live GUI SFTP file table must expose multiple reference rows")
            elif (parent_item := sftp_table.topLevelItem(0)) is None:
                errors.append("mobaxterm live GUI SFTP file table missing parent row")
            else:
                if parent_item.text(0) != EXPECTED_MOBA_SFTP_BROWSER_CHROME.parent_row_label:
                    errors.append("mobaxterm live GUI SFTP first file row must be the parent-folder entry")
                parent_kind = str(parent_item.data(0, Qt.ItemDataRole.UserRole) or "")
                if parent_kind != EXPECTED_MOBA_SFTP_BROWSER_CHROME.parent_row_kind:
                    errors.append("mobaxterm live GUI SFTP parent row kind metadata drifted")
                current_parent_row = sftp_table.indexOfTopLevelItem(sftp_table.currentItem())
                if not parent_item.isSelected() or current_parent_row != 0:
                    errors.append("mobaxterm live GUI SFTP parent row must be selected by default")
                if parent_item.icon(0).isNull():
                    errors.append("mobaxterm live GUI SFTP parent row must use a generated folder-up icon")
            user_role = int(Qt.ItemDataRole.UserRole)
            icon_key_role = user_role + 41
            row_kind_role = user_role + 42
            icon_size_role = user_role + 43
            icon_render_role = user_role + 44
            row_contract_key_role = user_role + 45
            row_route_key_role = user_role + 46
            row_source_path_role = user_role + 47
            row_index_role = user_role + 48
            row_selected_by_route_role = user_role + 49
            routed_row_paths: list[str] = []
            for row_index in range(sftp_table.topLevelItemCount()):
                item = sftp_table.topLevelItem(row_index)
                if item is None:
                    continue
                row_kind = str(item.data(0, row_kind_role) or item.data(0, Qt.ItemDataRole.UserRole) or "")
                expected_icon_key = EXPECTED_MOBA_SFTP_FILE_ROW_ICON_KEYS.get(row_kind)
                if expected_icon_key is None:
                    errors.append(f"mobaxterm live GUI SFTP row {item.text(0)!r} has unknown row kind {row_kind!r}")
                    continue
                icon_key = str(item.data(0, icon_key_role) or "")
                icon_render = str(item.data(0, icon_render_role) or "")
                icon_size = int(item.data(0, icon_size_role) or 0)
                if icon_key != expected_icon_key:
                    errors.append(
                        f"mobaxterm live GUI SFTP row {item.text(0)!r} icon key "
                        f"{icon_key!r} must equal {expected_icon_key!r}"
                    )
                if icon_render != EXPECTED_MOBA_SFTP_FILE_ROW_RENDER_SOURCES[row_kind]:
                    errors.append(f"mobaxterm live GUI SFTP row {item.text(0)!r} must use generated-pixmap icon")
                if icon_size != EXPECTED_MOBA_SFTP_FILE_ROW_ICON_SIZES[row_kind]:
                    errors.append(f"mobaxterm live GUI SFTP row {item.text(0)!r} icon size drifted")
                if item.icon(0).isNull():
                    errors.append(f"mobaxterm live GUI SFTP row {item.text(0)!r} must expose a generated icon")
                row_contract_key = str(item.data(0, row_contract_key_role) or "")
                if row_contract_key != EXPECTED_MOBA_SFTP_ROUTED_FILE_ROWS.key:
                    errors.append(f"mobaxterm live GUI SFTP row {item.text(0)!r} routed-row contract key drifted")
                row_route_key = str(item.data(0, row_route_key_role) or "")
                if row_route_key != EXPECTED_MOBA_SFTP_ROUTED_FILE_ROWS.follow_route_key:
                    errors.append(f"mobaxterm live GUI SFTP row {item.text(0)!r} follow-folder route key drifted")
                row_source_path = str(item.data(0, row_source_path_role) or "")
                routed_row_paths.append(row_source_path)
                if not row_source_path.startswith("/"):
                    errors.append(f"mobaxterm live GUI SFTP row {item.text(0)!r} missing absolute source path")
                row_route_index = int(item.data(0, row_index_role) or -1)
                if row_route_index != row_index:
                    errors.append(f"mobaxterm live GUI SFTP row {item.text(0)!r} routed-row index drifted")
                selected_by_route = bool(item.data(0, row_selected_by_route_role))
                if selected_by_route != (row_index == 0):
                    errors.append(f"mobaxterm live GUI SFTP row {item.text(0)!r} selected-by-route metadata drifted")
            if routed_row_paths and len(set(routed_row_paths)) != 1:
                errors.append(f"mobaxterm live GUI SFTP routed row paths diverged: {routed_row_paths}")
            if sftp_path is not None and routed_row_paths and any(path != sftp_path.text() for path in routed_row_paths):
                errors.append("mobaxterm live GUI SFTP routed row paths must match the active SFTP path")
        sftp_dock = window.findChild(QFrame, "mobaSftpBrowser")
        if sftp_dock is None:
            errors.append("mobaxterm live GUI SFTP dock missing density container")
        else:
            expected_dock_properties = {
                "mobaSftpDockInnerMargin": EXPECTED_MOBA_SFTP_DOCK_LAYOUT.inner_margin,
                "mobaSftpToolbarHeight": EXPECTED_MOBA_SFTP_DOCK_LAYOUT.toolbar_height,
                "mobaSftpPathHeight": EXPECTED_MOBA_SFTP_DOCK_LAYOUT.path_height,
                "mobaSftpHeaderHeight": EXPECTED_MOBA_SFTP_DOCK_LAYOUT.table_header_height,
                "mobaSftpRowHeight": EXPECTED_MOBA_SFTP_DOCK_LAYOUT.file_row_height,
                "mobaSftpMonitoringHeight": EXPECTED_MOBA_SFTP_DOCK_LAYOUT.monitoring_height,
                "mobaSftpStaticMaxRows": EXPECTED_MOBA_SFTP_DOCK_LAYOUT.static_max_rows,
            }
            for property_name, expected_value in expected_dock_properties.items():
                if int(sftp_dock.property(property_name) or 0) != expected_value:
                    errors.append(f"mobaxterm live GUI SFTP dock density property {property_name} drifted")
        sftp_toolbar = window.findChild(QFrame, "mobaSftpToolbar")
        if sftp_toolbar is None:
            errors.append("mobaxterm live GUI SFTP toolbar missing density container")
        elif int(sftp_toolbar.property("mobaSftpToolbarHeight") or 0) != EXPECTED_MOBA_SFTP_DOCK_LAYOUT.toolbar_height:
            errors.append("mobaxterm live GUI SFTP toolbar height metadata drifted")
        monitoring_panel = window.findChild(QFrame, "mobaRemoteMonitoring")
        if monitoring_panel is None:
            errors.append("mobaxterm live GUI monitoring panel missing density container")
        else:
            if int(monitoring_panel.property("mobaSftpMonitoringHeight") or 0) != (
                EXPECTED_MOBA_SFTP_DOCK_LAYOUT.monitoring_height
            ):
                errors.append("mobaxterm live GUI monitoring panel height metadata drifted")
            if int(monitoring_panel.property("mobaSftpMonitoringDividerOffset") or 0) != (
                EXPECTED_MOBA_SFTP_DOCK_LAYOUT.monitoring_divider_offset
            ):
                errors.append("mobaxterm live GUI monitoring divider offset metadata drifted")
            if int(monitoring_panel.property("mobaSftpMonitoringMetricRowGap") or 0) != (
                EXPECTED_MOBA_SFTP_DOCK_LAYOUT.monitoring_metric_row_gap
            ):
                errors.append("mobaxterm live GUI monitoring metric row gap metadata drifted")
            monitoring_footer_properties = {
                "mobaRemoteMonitoringStaticHeight": EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME.static_height,
                "mobaRemoteMonitoringDividerOffset": EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME.divider_offset,
                "mobaRemoteMonitoringDividerLeftInset": (
                    EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME.divider_left_inset
                ),
                "mobaRemoteMonitoringDividerRightInset": (
                    EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME.divider_right_inset
                ),
                "mobaRemoteMonitoringContentLeft": EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME.content_left,
                "mobaRemoteMonitoringIconCenterX": EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME.icon_center_x,
                "mobaRemoteMonitoringMetricRowGap": EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME.metric_row_gap,
                "mobaRemoteMonitoringLiveControlsWidth": (
                    EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME.live_controls_width
                ),
            }
            for property_name, expected_value in monitoring_footer_properties.items():
                if int(monitoring_panel.property(property_name) or 0) != expected_value:
                    errors.append(f"mobaxterm live GUI monitoring footer property {property_name} drifted")
            if monitoring_panel.height() != EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME.static_height:
                errors.append("mobaxterm live GUI monitoring footer live height drifted")
            if bool(monitoring_panel.property("mobaRemoteMonitoringCompact")) != (
                EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME.compact
            ):
                errors.append("mobaxterm live GUI monitoring compact mode metadata drifted")
            if str(monitoring_panel.property("mobaRemoteMonitoringTelemetrySurface") or "") != (
                EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME.telemetry_surface
            ):
                errors.append("mobaxterm live GUI monitoring telemetry surface metadata drifted")
            monitoring_route_properties = {
                "mobaMonitoringTelemetryRouteKey": EXPECTED_MOBA_MONITORING_TELEMETRY_ROUTE.key,
                "mobaMonitoringTelemetryRouteRole": EXPECTED_MOBA_MONITORING_TELEMETRY_ROUTE.route_role,
                "mobaMonitoringTelemetryTargetBarObject": EXPECTED_MOBA_MONITORING_TELEMETRY_ROUTE.target_bar_object,
                "mobaMonitoringTelemetryTargetCellObject": EXPECTED_MOBA_MONITORING_TELEMETRY_ROUTE.target_cell_object,
                "mobaMonitoringTelemetryIdentityCellKey": EXPECTED_MOBA_MONITORING_TELEMETRY_ROUTE.target_identity_cell_key,
            }
            for property_name, expected_value in monitoring_route_properties.items():
                if str(monitoring_panel.property(property_name) or "") != expected_value:
                    errors.append(f"mobaxterm live GUI monitoring route property {property_name} drifted")
            if list(monitoring_panel.property("mobaMonitoringTelemetryMetricCellKeys") or []) != list(
                EXPECTED_MOBA_MONITORING_TELEMETRY_ROUTE.target_metric_cell_keys
            ):
                errors.append("mobaxterm live GUI monitoring route metric-cell keys drifted")
            if sorted(monitoring_panel.property("mobaRemoteMonitoringMetricKeys") or []) != sorted(
                EXPECTED_MOBA_MONITORING_METRIC_KEYS
            ):
                errors.append("mobaxterm live GUI monitoring metric-key metadata drifted")
            if list(monitoring_panel.property("mobaRemoteMonitoringVisibleMetricKeys") or []) != list(
                EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME.visible_metric_keys
            ):
                errors.append("mobaxterm live GUI monitoring visible metric policy drifted")
            if int(monitoring_panel.property("mobaRemoteMonitoringRefreshSeconds") or 0) != (
                EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME.refresh_seconds
            ):
                errors.append("mobaxterm live GUI monitoring refresh cadence metadata drifted")
            if list(monitoring_panel.property("mobaMonitoringControlGeometryKeys") or []) != [
                geometry.key for geometry in EXPECTED_MOBA_MONITORING_CONTROL_GEOMETRY
            ]:
                errors.append("mobaxterm live GUI monitoring control geometry sequence drifted")
            command = str(monitoring_panel.property("mobaRemoteMonitoringCommand") or "")
            if "sh -lc" not in command or "/proc" not in command:
                errors.append("mobaxterm live GUI monitoring panel must expose SSH telemetry command evidence")
            follow_plan = str(monitoring_panel.property("mobaRemoteMonitoringFollowPlan") or "")
            if "ls -la /" not in follow_plan:
                errors.append("mobaxterm live GUI monitoring panel must expose follow-folder SFTP plan evidence")
            controls_frame = monitoring_panel.findChild(QFrame, "mobaMonitoringControls")
            if controls_frame is None:
                errors.append("mobaxterm live GUI monitoring footer missing controls frame")
            else:
                if int(controls_frame.property("mobaRemoteMonitoringLiveControlsWidth") or 0) != (
                    EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME.live_controls_width
                ):
                    errors.append("mobaxterm live GUI monitoring controls width metadata drifted")
                if int(controls_frame.property("mobaRemoteMonitoringStaticHeight") or 0) != (
                    EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME.static_height
                ):
                    errors.append("mobaxterm live GUI monitoring controls height metadata drifted")
                if controls_frame.width() != EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME.live_controls_width:
                    errors.append("mobaxterm live GUI monitoring controls frame width drifted")
                if controls_frame.height() != EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME.static_height:
                    errors.append("mobaxterm live GUI monitoring controls frame height drifted")
        monitoring_labels = window.findChildren(QLabel, "mobaMonitoringMetric")
        monitoring_keys = {str(label.property("mobaMonitoringMetricKey") or "") for label in monitoring_labels}
        missing_monitoring_keys = sorted(EXPECTED_MOBA_MONITORING_METRIC_KEYS - monitoring_keys)
        if missing_monitoring_keys:
            errors.append(f"mobaxterm live GUI monitoring dock missing metric keys: {missing_monitoring_keys}")
        visible_metric_keys = sorted(
            str(label.property("mobaMonitoringMetricKey") or "")
            for label in monitoring_labels
            if bool(label.property("mobaMonitoringMetricVisibleInDock"))
        )
        if visible_metric_keys != sorted(EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME.visible_metric_keys):
            errors.append(f"mobaxterm live GUI monitoring visible metric keys drifted: {visible_metric_keys}")
        for label in monitoring_labels:
            telemetry_surface = str(label.property("mobaMonitoringMetricTelemetrySurface") or "")
            if telemetry_surface != EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME.telemetry_surface:
                errors.append("mobaxterm live GUI monitoring metric telemetry surface metadata drifted")
            if str(label.property("mobaMonitoringTelemetryRouteKey") or "") != (
                EXPECTED_MOBA_MONITORING_TELEMETRY_ROUTE.key
            ):
                errors.append("mobaxterm live GUI monitoring metric route metadata drifted")
        monitoring_controls = [
            *window.findChildren(QToolButton, "mobaMonitoringControl"),
            *window.findChildren(QCheckBox, "mobaFollowTerminalFolder"),
        ]
        monitoring_control_by_key = {
            str(widget.property("mobaMonitoringControlKey") or ""): widget for widget in monitoring_controls
        }
        missing_monitoring_controls = sorted(
            EXPECTED_MOBA_MONITORING_CONTROL_KEYS - set(monitoring_control_by_key)
        )
        if missing_monitoring_controls:
            errors.append(f"mobaxterm live GUI monitoring dock missing control keys: {missing_monitoring_controls}")
        for control in EXPECTED_MOBA_MONITORING_CONTROLS:
            widget = monitoring_control_by_key.get(control.key)
            if widget is None:
                continue
            icon_key = str(widget.property("mobaMonitoringControlIconKey") or "")
            control_type = str(widget.property("mobaMonitoringControlType") or "")
            default_checked = bool(widget.property("mobaMonitoringControlDefaultChecked"))
            if widget.text() != control.label:
                errors.append(
                    f"mobaxterm live GUI monitoring control {control.key!r} label "
                    f"{widget.text()!r} must equal {control.label!r}"
                )
            if icon_key != control.icon_key:
                errors.append(
                    f"mobaxterm live GUI monitoring control {control.key!r} icon key "
                    f"{icon_key!r} must equal {control.icon_key!r}"
                )
            if control_type != control.control_type:
                errors.append(
                    f"mobaxterm live GUI monitoring control {control.key!r} type "
                    f"{control_type!r} must equal {control.control_type!r}"
                )
            if default_checked != control.checked:
                errors.append(f"mobaxterm live GUI monitoring control {control.key!r} default checked drifted")
            if widget.isChecked() != control.checked:
                errors.append(f"mobaxterm live GUI monitoring control {control.key!r} checked state drifted")
            if widget.icon().isNull():
                errors.append(f"mobaxterm live GUI monitoring control {control.key!r} must expose an icon")
            geometry = EXPECTED_MOBA_MONITORING_CONTROL_GEOMETRY_BY_KEY.get(control.key)
            if geometry is None:
                errors.append(f"mobaxterm live GUI monitoring control {control.key!r} missing geometry reference")
            else:
                geometry_properties = {
                    "mobaMonitoringControlStaticX": geometry.anchor_x,
                    "mobaMonitoringControlStaticY": geometry.static_y,
                    "mobaMonitoringControlIconX": geometry.icon_x,
                    "mobaMonitoringControlIconSize": geometry.icon_size,
                    "mobaMonitoringControlLabelX": geometry.label_x,
                    "mobaMonitoringControlLabelYOffset": geometry.label_y_offset,
                    "mobaMonitoringControlLabelFontSize": geometry.label_font_size,
                    "mobaMonitoringControlCheckSize": geometry.check_size,
                    "mobaMonitoringControlCheckYOffset": geometry.check_y_offset,
                    "mobaMonitoringControlRowHeight": geometry.row_height,
                    "mobaMonitoringControlLiveWidth": geometry.live_width,
                }
                for property_name, expected_value in geometry_properties.items():
                    if int(widget.property(property_name) or -1) != expected_value:
                        errors.append(
                            f"mobaxterm live GUI monitoring control {control.key!r} "
                            f"{property_name} drifted"
                        )
                if bool(widget.property("mobaMonitoringControlLabelBold")) != geometry.label_bold:
                    errors.append(
                        f"mobaxterm live GUI monitoring control {control.key!r} "
                        "mobaMonitoringControlLabelBold drifted"
                    )
                if [tuple(point) for point in (widget.property("mobaMonitoringControlCheckmarkPoints") or [])] != list(
                    geometry.checkmark_points
                ):
                    errors.append(
                        f"mobaxterm live GUI monitoring control {control.key!r} "
                        "mobaMonitoringControlCheckmarkPoints drifted"
                    )
                if widget.width() != geometry.live_width:
                    errors.append(f"mobaxterm live GUI monitoring control {control.key!r} live width drifted")
                if widget.font().pointSize() != geometry.label_font_size:
                    errors.append(f"mobaxterm live GUI monitoring control {control.key!r} font size drifted")
                if widget.font().bold() != geometry.label_bold:
                    errors.append(f"mobaxterm live GUI monitoring control {control.key!r} font weight drifted")
                if widget.iconSize().width() != geometry.icon_size or widget.iconSize().height() != geometry.icon_size:
                    errors.append(f"mobaxterm live GUI monitoring control {control.key!r} icon size drifted")
            if str(widget.property("mobaMonitoringTelemetrySurface") or "") != (
                EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME.telemetry_surface
            ):
                errors.append(f"mobaxterm live GUI monitoring control {control.key!r} telemetry surface drifted")
            if str(widget.property("mobaMonitoringTelemetryRouteKey") or "") != (
                EXPECTED_MOBA_MONITORING_TELEMETRY_ROUTE.key
            ):
                errors.append(f"mobaxterm live GUI monitoring control {control.key!r} telemetry route drifted")
            if control.key == "remote-monitoring":
                command = str(widget.property("mobaMonitoringCommand") or "")
                if "sh -lc" not in command or "/proc" not in command:
                    errors.append("mobaxterm live GUI remote-monitoring control missing command evidence")
                if int(widget.property("mobaMonitoringRefreshSeconds") or 0) != (
                    EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME.refresh_seconds
                ):
                    errors.append("mobaxterm live GUI remote-monitoring control refresh cadence drifted")
            if control.key == "follow-terminal-folder":
                follow_plan = str(widget.property("mobaMonitoringFollowPlan") or "")
                if "ls -la /" not in follow_plan:
                    errors.append("mobaxterm live GUI follow-terminal-folder control missing SFTP plan evidence")
                if not str(widget.property("mobaMonitoringFollowPath") or "").startswith("/"):
                    errors.append("mobaxterm live GUI follow-terminal-folder control missing remote path metadata")
        follow_route = EXPECTED_MOBA_SFTP_FOLLOW_FOLDER_ROUTE
        follow_widget = monitoring_control_by_key.get(follow_route.source_control_key)
        route_widgets = (
            ("SFTP browser", sftp_dock),
            ("SFTP path", sftp_path),
            ("SFTP table", sftp_table),
            ("monitoring panel", monitoring_panel),
            ("follow control", follow_widget),
        )
        route_paths: list[str] = []
        route_plans: list[str] = []
        route_enabled: list[bool] = []
        route_identity_properties = {
            "mobaSftpFollowRouteKey": follow_route.key,
            "mobaSftpFollowRouteRole": follow_route.route_role,
            "mobaSftpFollowRouteSourceControlKey": follow_route.source_control_key,
            "mobaSftpFollowRouteSourceControlObject": follow_route.source_control_object,
            "mobaSftpFollowRouteSourcePathProperty": follow_route.source_path_property,
            "mobaSftpFollowRouteSourcePlanProperty": follow_route.source_plan_property,
            "mobaSftpFollowRouteSourceEnabledProperty": follow_route.source_enabled_property,
            "mobaSftpFollowRouteTargetBrowserObject": follow_route.target_browser_object,
            "mobaSftpFollowRouteTargetPathObject": follow_route.target_path_object,
            "mobaSftpFollowRouteTargetTableObject": follow_route.target_table_object,
            "mobaSftpFollowRouteTargetPathProperty": follow_route.target_path_property,
            "mobaSftpFollowRouteTargetPlanProperty": follow_route.target_plan_property,
            "mobaSftpFollowRouteTargetEnabledProperty": follow_route.target_enabled_property,
            "mobaSftpFollowRouteRenderSource": follow_route.render_source,
        }
        for label, widget in route_widgets:
            if widget is None:
                errors.append(f"mobaxterm live GUI follow-folder route missing {label}")
                continue
            for property_name, expected_value in route_identity_properties.items():
                if str(widget.property(property_name) or "") != expected_value:
                    errors.append(
                        f"mobaxterm live GUI follow-folder route {label} "
                        f"property {property_name} drifted"
                    )
            route_path = str(widget.property(follow_route.target_path_property) or "")
            route_plan = str(widget.property(follow_route.target_plan_property) or "")
            route_paths.append(route_path)
            route_plans.append(route_plan)
            route_enabled.append(bool(widget.property(follow_route.target_enabled_property)))
        if route_paths and (not all(path.startswith("/") for path in route_paths) or len(set(route_paths)) != 1):
            errors.append(f"mobaxterm live GUI follow-folder route path metadata diverged: {route_paths}")
        if sftp_path is not None and route_paths and any(path != sftp_path.text() for path in route_paths):
            errors.append("mobaxterm live GUI follow-folder route path must match SFTP path strip text")
        if route_plans and any(
            route_path not in plan or "ls -la " not in plan
            for route_path, plan in zip(route_paths, route_plans, strict=False)
        ):
            errors.append("mobaxterm live GUI follow-folder route plan must list the routed SFTP path")
        if follow_widget is not None:
            source_path = str(follow_widget.property(follow_route.source_path_property) or "")
            source_plan = str(follow_widget.property(follow_route.source_plan_property) or "")
            source_enabled = bool(follow_widget.property(follow_route.source_enabled_property))
            if route_paths and source_path != route_paths[0]:
                errors.append("mobaxterm live GUI follow-folder route source path drifted")
            if route_plans and source_plan != route_plans[0]:
                errors.append("mobaxterm live GUI follow-folder route source plan drifted")
            if route_enabled and (source_enabled != follow_widget.isChecked() or any(value != source_enabled for value in route_enabled)):
                errors.append("mobaxterm live GUI follow-folder route enabled state drifted")
        expected_title = EXPECTED_LIVE_REFERENCE_TAB_LABELS["mobaxterm"]
        if window.windowTitle() != expected_title:
            errors.append(f"mobaxterm live GUI window title must be connected target label: {expected_title}")
        if str(window.property("mobaTitlebarTitle") or "") != expected_title:
            errors.append("mobaxterm live GUI titlebar title metadata drifted")
        if str(window.property("mobaTitlebarIconKey") or "") != EXPECTED_MOBA_TITLEBAR_CHROME.icon_key:
            errors.append("mobaxterm live GUI titlebar icon metadata drifted")
        if int(window.property("mobaTitlebarHeight") or 0) != EXPECTED_MOBA_TITLEBAR_CHROME.static_height:
            errors.append("mobaxterm live GUI titlebar height metadata drifted")
        if int(window.property("mobaTitlebarTitleLeft") or 0) != EXPECTED_MOBA_TITLEBAR_CHROME.title_left:
            errors.append("mobaxterm live GUI titlebar title offset metadata drifted")
        if list(window.property("mobaTitlebarControlKeys") or []) != list(EXPECTED_MOBA_TITLEBAR_CHROME.control_keys):
            errors.append("mobaxterm live GUI titlebar control sequence drifted")
        if int(window.property("mobaTitlebarControlWidth") or 0) != EXPECTED_MOBA_TITLEBAR_CHROME.control_width:
            errors.append("mobaxterm live GUI titlebar control width metadata drifted")
        banner_titles = {label.text() for label in window.findChildren(QLabel, "mobaSshBannerTitle")}
        expected_banner_title = f"* {EXPECTED_MOBA_SSH_BANNER_CHROME.title} *"
        if expected_banner_title not in banner_titles:
            errors.append(f"mobaxterm live GUI SSH banner missing centered title: {expected_banner_title}")
        banner_subtitles = {label.text() for label in window.findChildren(QLabel, "mobaSshBannerSubtitle")}
        if EXPECTED_MOBA_SSH_BANNER_CHROME.subtitle not in banner_subtitles:
            errors.append(
                f"mobaxterm live GUI SSH banner missing subtitle: {EXPECTED_MOBA_SSH_BANNER_CHROME.subtitle}"
            )
        banner = window.findChild(QLabel, "mobaSshBannerTitle")
        if banner is not None:
            parent = banner.parent()
            if parent is not None:
                width = int(parent.property("mobaBannerWidth") or 0)
                height = int(parent.property("mobaBannerHeight") or 0)
                if width != EXPECTED_MOBA_SSH_BANNER_CHROME.static_width:
                    errors.append("mobaxterm live GUI SSH banner width metadata drifted")
                if height != EXPECTED_MOBA_SSH_BANNER_CHROME.static_height:
                    errors.append("mobaxterm live GUI SSH banner height metadata drifted")
        banner_frame = window.findChild(QFrame, "mobaSshBanner")
        banner_slot = window.findChild(QFrame, "mobaSshBannerSlot")
        if banner_slot is None:
            errors.append("mobaxterm live GUI SSH banner slot is missing")
        else:
            expected_slot_properties = {
                "mobaBannerLeftOffset": EXPECTED_MOBA_SSH_BANNER_CHROME.static_left_offset,
                "mobaBannerTopOffset": EXPECTED_MOBA_SSH_BANNER_CHROME.static_top_offset,
                "mobaBannerTerminalGap": EXPECTED_MOBA_SSH_BANNER_CHROME.terminal_gap,
            }
            for property_name, expected_value in expected_slot_properties.items():
                if int(banner_slot.property(property_name) or 0) != expected_value:
                    errors.append(f"mobaxterm live GUI SSH banner slot {property_name} drifted")
        if banner_frame is None:
            errors.append("mobaxterm live GUI SSH banner card is missing")
        else:
            expected_frame_properties = {
                "mobaBannerLeftOffset": EXPECTED_MOBA_SSH_BANNER_CHROME.static_left_offset,
                "mobaBannerTopOffset": EXPECTED_MOBA_SSH_BANNER_CHROME.static_top_offset,
                "mobaBannerTerminalGap": EXPECTED_MOBA_SSH_BANNER_CHROME.terminal_gap,
            }
            for property_name, expected_value in expected_frame_properties.items():
                if int(banner_frame.property(property_name) or 0) != expected_value:
                    errors.append(f"mobaxterm live GUI SSH banner frame {property_name} drifted")
            if str(banner_frame.property("mobaBannerTargetIntro") or "") != (
                EXPECTED_MOBA_SSH_BANNER_CHROME.target_intro
            ):
                errors.append("mobaxterm live GUI SSH banner target intro metadata drifted")
            if int(banner_frame.property("mobaBannerCapabilityLabelWidth") or 0) != (
                EXPECTED_MOBA_SSH_BANNER_CHROME.capability_label_width
            ):
                errors.append("mobaxterm live GUI SSH banner capability label width drifted")
            capability_keys = list(banner_frame.property("mobaBannerCapabilityKeys") or [])
            if capability_keys != EXPECTED_MOBA_SSH_BANNER_CAPABILITY_KEYS:
                errors.append(f"mobaxterm live GUI SSH banner capability key order drifted: {capability_keys}")
            footer_links = list(banner_frame.property("mobaBannerFooterLinks") or [])
            if footer_links != EXPECTED_MOBA_SSH_BANNER_FOOTER_LINKS:
                errors.append(f"mobaxterm live GUI SSH banner footer links drifted: {footer_links}")
            row_geometry_keys = list(banner_frame.property("mobaSshBannerRowGeometryKeys") or [])
            expected_row_geometry_keys = [geometry.key for geometry in EXPECTED_MOBA_SSH_BANNER_ROW_GEOMETRY]
            if row_geometry_keys != expected_row_geometry_keys:
                errors.append(f"mobaxterm live GUI SSH banner row geometry order drifted: {row_geometry_keys}")
        target_lines = window.findChildren(QLabel, "mobaSshBannerTargetLine")
        if not target_lines:
            errors.append("mobaxterm live GUI SSH banner target line is missing")
        elif str(target_lines[0].property("mobaSshBannerTarget") or "") != EXPECTED_MOBA_SSH_BANNER.title:
            errors.append("mobaxterm live GUI SSH banner target metadata drifted")
        banner_row_labels = [
            *window.findChildren(QLabel, "mobaSshBannerTitle"),
            *window.findChildren(QLabel, "mobaSshBannerSubtitle"),
            *target_lines,
            *window.findChildren(QLabel, "mobaSshBannerCapability"),
            *window.findChildren(QLabel, "mobaSshBannerFooter"),
        ]
        for label in banner_row_labels:
            row_key = str(label.property("mobaSshBannerRowKey") or "")
            expected_geometry = EXPECTED_MOBA_SSH_BANNER_ROW_GEOMETRY_BY_KEY.get(row_key)
            if expected_geometry is None:
                errors.append(f"mobaxterm live GUI SSH banner row has unexpected geometry key: {row_key!r}")
                continue
            expected_properties = {
                "mobaSshBannerRowX": expected_geometry.static_x,
                "mobaSshBannerRowY": expected_geometry.static_y,
                "mobaSshBannerRowWidth": expected_geometry.static_width,
                "mobaSshBannerRowHeight": expected_geometry.static_height,
            }
            for property_name, expected_value in expected_properties.items():
                if int(label.property(property_name) or 0) != expected_value:
                    errors.append(
                        f"mobaxterm live GUI SSH banner row {row_key!r} {property_name} drifted"
                    )
            if bool(label.property("mobaSshBannerRowCentered")) != expected_geometry.centered:
                errors.append(f"mobaxterm live GUI SSH banner row {row_key!r} centered flag drifted")
        capability_labels = window.findChildren(QLabel, "mobaSshBannerCapability")
        actual_capabilities = [
            {
                "key": str(label.property("mobaSshBannerCapabilityKey") or ""),
                "label": str(label.property("mobaSshBannerCapabilityLabel") or ""),
                "value": str(label.property("mobaSshBannerCapabilityValue") or ""),
                "status": str(label.property("mobaSshBannerCapabilityStatus") or ""),
            }
            for label in capability_labels
        ]
        expected_capabilities = [
            {"key": row.key, "label": row.label, "value": row.value, "status": row.status}
            for row in EXPECTED_MOBA_SSH_BANNER_CAPABILITIES
        ]
        if actual_capabilities != expected_capabilities:
            errors.append("mobaxterm live GUI SSH banner capability-card rows drifted")
        footer_labels = window.findChildren(QLabel, "mobaSshBannerFooter")
        if not footer_labels:
            errors.append("mobaxterm live GUI SSH banner footer is missing")
        elif list(footer_labels[0].property("mobaSshBannerFooterLinks") or []) != (
            EXPECTED_MOBA_SSH_BANNER_FOOTER_LINKS
        ):
            errors.append("mobaxterm live GUI SSH banner footer metadata drifted")
        terminal_output = window.findChild(QTextEdit, "terminalOutput")
        terminal_pane = window.findChild(QWidget, "terminalPane")
        if terminal_pane is None:
            errors.append("mobaxterm live GUI terminal pane is missing")
        else:
            if bool(terminal_pane.property("mobaPlainTerminalMode")) is not True:
                errors.append("mobaxterm live GUI terminal pane must use Moba plain terminal mode")
            expected_visibility = {
                "mobaTerminalHeaderVisible": False,
                "mobaTerminalCommandRowVisible": False,
                "mobaTerminalInputVisible": False,
            }
            for property_name, expected_value in expected_visibility.items():
                if bool(terminal_pane.property(property_name)) != expected_value:
                    errors.append(f"mobaxterm live GUI terminal pane {property_name} drifted")
        if terminal_output is None:
            errors.append("mobaxterm live GUI terminal transcript output is missing")
        else:
            transcript_keys = list(terminal_output.property("mobaTerminalTranscriptKeys") or [])
            transcript_tones = list(terminal_output.property("mobaTerminalTranscriptTones") or [])
            if transcript_keys != EXPECTED_MOBA_TERMINAL_TRANSCRIPT_KEYS:
                errors.append(f"mobaxterm live GUI terminal transcript keys drifted: {transcript_keys}")
            if transcript_tones != EXPECTED_MOBA_TERMINAL_TRANSCRIPT_TONES:
                errors.append(f"mobaxterm live GUI terminal transcript tones drifted: {transcript_tones}")
            transcript_text = terminal_output.toPlainText()
            for line in EXPECTED_MOBA_TERMINAL_TRANSCRIPT:
                if line.text and line.text not in transcript_text:
                    errors.append(f"mobaxterm live GUI terminal transcript missing line: {line.key}")
            if bool(terminal_output.property("mobaPlainTerminalMode")) is not True:
                errors.append("mobaxterm live GUI terminal output must be marked as Moba plain terminal mode")
            geometry_keys = list(terminal_output.property("mobaTerminalTranscriptGeometryKeys") or [])
            if geometry_keys != EXPECTED_MOBA_TERMINAL_TRANSCRIPT_ROW_GEOMETRY_KEYS:
                errors.append(f"mobaxterm live GUI terminal transcript geometry key order drifted: {geometry_keys}")
            geometry_property_checks = {
                "mobaTerminalTranscriptX": [row.static_x for row in EXPECTED_MOBA_TERMINAL_TRANSCRIPT_ROW_GEOMETRY],
                "mobaTerminalTranscriptY": [row.static_y for row in EXPECTED_MOBA_TERMINAL_TRANSCRIPT_ROW_GEOMETRY],
                "mobaTerminalTranscriptRowHeight": [
                    row.row_height for row in EXPECTED_MOBA_TERMINAL_TRANSCRIPT_ROW_GEOMETRY
                ],
                "mobaTerminalTranscriptFontSize": [
                    row.font_size for row in EXPECTED_MOBA_TERMINAL_TRANSCRIPT_ROW_GEOMETRY
                ],
            }
            for property_name, expected_values in geometry_property_checks.items():
                if list(terminal_output.property(property_name) or []) != expected_values:
                    errors.append(f"mobaxterm live GUI terminal transcript {property_name} drifted")
        telemetry_labels = window.findChildren(QLabel, "mobaTelemetryItem")
        telemetry_icons = window.findChildren(QLabel, "mobaTelemetryIcon")
        telemetry_cells = window.findChildren(QFrame, "mobaTelemetryCell")
        telemetry_bar = window.findChild(QFrame, "mobaTelemetryBar")
        if telemetry_bar is None:
            errors.append("mobaxterm live GUI telemetry bar is missing")
        else:
            telemetry_geometry_keys = list(telemetry_bar.property("mobaTelemetryGeometryKeys") or [])
            expected_telemetry_geometry_keys = [geometry.key for geometry in EXPECTED_MOBA_TELEMETRY_CELL_GEOMETRY]
            if telemetry_geometry_keys != expected_telemetry_geometry_keys:
                errors.append(f"mobaxterm live GUI telemetry geometry key order drifted: {telemetry_geometry_keys}")
            if int(telemetry_bar.property("mobaTelemetryStartX") or 0) != (
                EXPECTED_MOBA_TELEMETRY_CELL_GEOMETRY[0].static_x
            ):
                errors.append("mobaxterm live GUI telemetry start-x metadata drifted")
            if int(telemetry_bar.property("mobaTelemetryBarHeight") or 0) != 24:
                errors.append("mobaxterm live GUI telemetry bar height metadata drifted")
            telemetry_route_properties = {
                "mobaMonitoringTelemetryRouteKey": EXPECTED_MOBA_MONITORING_TELEMETRY_ROUTE.key,
                "mobaMonitoringTelemetryRouteRole": EXPECTED_MOBA_MONITORING_TELEMETRY_ROUTE.route_role,
                "mobaMonitoringTelemetrySourcePanelObject": (
                    EXPECTED_MOBA_MONITORING_TELEMETRY_ROUTE.source_panel_object
                ),
                "mobaMonitoringTelemetrySourceControl": EXPECTED_MOBA_MONITORING_TELEMETRY_ROUTE.source_control_key,
                "mobaMonitoringTelemetrySurface": EXPECTED_MOBA_MONITORING_TELEMETRY_ROUTE.telemetry_surface,
                "mobaMonitoringTelemetryIdentityCellKey": (
                    EXPECTED_MOBA_MONITORING_TELEMETRY_ROUTE.target_identity_cell_key
                ),
            }
            for property_name, expected_value in telemetry_route_properties.items():
                if str(telemetry_bar.property(property_name) or "") != expected_value:
                    errors.append(f"mobaxterm live GUI telemetry route property {property_name} drifted")
            if list(telemetry_bar.property("mobaMonitoringTelemetryMetricCellKeys") or []) != list(
                EXPECTED_MOBA_MONITORING_TELEMETRY_ROUTE.target_metric_cell_keys
            ):
                errors.append("mobaxterm live GUI telemetry route metric-cell keys drifted")
        telemetry_keys = {
            str(widget.property("mobaTelemetryKey") or "")
            for widget in [*telemetry_labels, *telemetry_icons, *telemetry_cells]
        }
        missing_telemetry_keys = sorted(EXPECTED_MOBA_TELEMETRY_KEYS - telemetry_keys)
        if missing_telemetry_keys:
            errors.append(f"mobaxterm live GUI telemetry missing segment keys: {missing_telemetry_keys}")
        cell_keys = [str(cell.property("mobaTelemetryKey") or "") for cell in telemetry_cells]
        if cell_keys != EXPECTED_MOBA_TELEMETRY_CELL_KEYS:
            errors.append(f"mobaxterm live GUI telemetry cell order drifted: {cell_keys}")
        cell_widths = [int(cell.property("mobaTelemetryCellWidth") or 0) for cell in telemetry_cells]
        if cell_widths != EXPECTED_MOBA_TELEMETRY_CELL_WIDTHS:
            errors.append(f"mobaxterm live GUI telemetry cell widths drifted: {cell_widths}")
        cell_by_key = {str(cell.property("mobaTelemetryKey") or ""): cell for cell in telemetry_cells}
        icons_by_key = {str(icon.property("mobaTelemetryKey") or ""): icon for icon in telemetry_icons}
        labels_by_key = {str(label.property("mobaTelemetryKey") or ""): label for label in telemetry_labels}
        for expected_cell in EXPECTED_MOBA_TELEMETRY_CELLS:
            live_cell = cell_by_key.get(expected_cell.key)
            live_icon = icons_by_key.get(expected_cell.key)
            live_label = labels_by_key.get(expected_cell.key)
            if live_cell is None or live_icon is None or live_label is None:
                continue
            expected_routed = expected_cell.key in EXPECTED_MOBA_MONITORING_TELEMETRY_ROUTE.target_metric_cell_keys
            if bool(live_cell.property("mobaMonitoringTelemetryRouted")) != expected_routed:
                errors.append(f"mobaxterm live GUI telemetry cell {expected_cell.key!r} route flag drifted")
            if str(live_cell.property("mobaTelemetryIconKey") or "") != expected_cell.icon_key:
                errors.append(f"mobaxterm live GUI telemetry cell {expected_cell.key!r} icon key drifted")
            if str(live_cell.property("mobaTelemetryIconAccent") or "") != expected_cell.icon_accent:
                errors.append(f"mobaxterm live GUI telemetry cell {expected_cell.key!r} icon accent drifted")
            if int(live_cell.property("mobaTelemetryIconSize") or 0) != expected_cell.icon_size:
                errors.append(f"mobaxterm live GUI telemetry cell {expected_cell.key!r} icon size drifted")
            if str(live_cell.property("mobaTelemetryDisplayText") or "") != expected_cell.display_text:
                errors.append(f"mobaxterm live GUI telemetry cell {expected_cell.key!r} display text drifted")
            expected_geometry = EXPECTED_MOBA_TELEMETRY_CELL_GEOMETRY_BY_KEY[expected_cell.key]
            cell_geometry_properties = {
                "mobaTelemetryCellStaticX": expected_geometry.static_x,
                "mobaTelemetryCellStaticY": expected_geometry.static_y,
                "mobaTelemetryCellWidth": expected_geometry.width,
                "mobaTelemetryCellHeight": expected_geometry.height,
                "mobaTelemetrySeparatorTop": expected_geometry.separator_top,
                "mobaTelemetrySeparatorBottom": expected_geometry.separator_bottom,
            }
            for property_name, expected_value in cell_geometry_properties.items():
                if int(live_cell.property(property_name) or 0) != expected_value:
                    errors.append(
                        f"mobaxterm live GUI telemetry cell {expected_cell.key!r} {property_name} drifted"
                    )
            if str(live_icon.property("mobaTelemetryIconKey") or "") != expected_cell.icon_key:
                errors.append(f"mobaxterm live GUI telemetry icon {expected_cell.key!r} icon key drifted")
            if str(live_icon.property("mobaTelemetryIconAccent") or "") != expected_cell.icon_accent:
                errors.append(f"mobaxterm live GUI telemetry icon {expected_cell.key!r} accent drifted")
            if int(live_icon.property("mobaTelemetryIconSize") or 0) != expected_cell.icon_size:
                errors.append(f"mobaxterm live GUI telemetry icon {expected_cell.key!r} size drifted")
            if int(live_icon.property("mobaTelemetryIconX") or 0) != expected_geometry.icon_x:
                errors.append(f"mobaxterm live GUI telemetry icon {expected_cell.key!r} x offset drifted")
            if int(live_icon.property("mobaTelemetryIconY") or 0) != expected_geometry.icon_y:
                errors.append(f"mobaxterm live GUI telemetry icon {expected_cell.key!r} y offset drifted")
            if str(live_icon.property("mobaTelemetryIconRender") or "") != "generated-pixmap":
                errors.append(f"mobaxterm live GUI telemetry icon {expected_cell.key!r} must use generated pixmap")
            if live_icon.text().strip():
                errors.append(f"mobaxterm live GUI telemetry icon {expected_cell.key!r} must not be a text placeholder")
            pixmap = live_icon.pixmap()
            if pixmap is None or pixmap.isNull():
                errors.append(f"mobaxterm live GUI telemetry icon {expected_cell.key!r} pixmap is missing")
            if int(live_label.property("mobaTelemetryLabelX") or 0) != expected_geometry.label_x:
                errors.append(f"mobaxterm live GUI telemetry label {expected_cell.key!r} x offset drifted")
            if int(live_label.property("mobaTelemetryLabelY") or 0) != expected_geometry.label_y:
                errors.append(f"mobaxterm live GUI telemetry label {expected_cell.key!r} y offset drifted")
            if int(live_label.property("mobaTelemetryLabelFontSize") or 0) != expected_geometry.label_font_size:
                errors.append(f"mobaxterm live GUI telemetry label {expected_cell.key!r} font size drifted")
            if live_label.text() != expected_cell.display_text:
                errors.append(f"mobaxterm live GUI telemetry label {expected_cell.key!r} text drifted")
        tab_chrome: dict[str, Any] = {}
        actual_tab_geometry_keys = list(tabs.property("mobaTabChromeGeometryKeys") or [])
        if actual_tab_geometry_keys and actual_tab_geometry_keys != [item.key for item in EXPECTED_MOBA_TAB_CHROME_GEOMETRY]:
            errors.append("mobaxterm live GUI tab chrome geometry key order drifted")
        for index in range(tabs.count()):
            widget = tabs.widget(index)
            if widget is None:
                continue
            chrome_key = str(widget.property("mobaTabChromeKey") or "")
            if not chrome_key:
                continue
            tab_chrome[chrome_key] = widget
            if tabs.tabIcon(index).isNull():
                errors.append(f"mobaxterm live GUI tab chrome {chrome_key!r} must use a generated icon")
        missing_tab_chrome = sorted(EXPECTED_MOBA_TAB_CHROME_KEYS - set(tab_chrome))
        if missing_tab_chrome:
            errors.append(f"mobaxterm live GUI connected tab chrome missing keys: {missing_tab_chrome}")
        for key, widget in tab_chrome.items():
            icon_key = str(widget.property("mobaTabIconKey") or "")
            closeable = bool(widget.property("mobaTabCloseable"))
            if key in EXPECTED_MOBA_TAB_CHROME_KEYS and not icon_key:
                errors.append(f"mobaxterm live GUI tab chrome {key!r} missing mobaTabIconKey")
            if key == "active-session" and not closeable:
                errors.append("mobaxterm live GUI active connected tab must be closeable")
            expected_geometry = EXPECTED_MOBA_TAB_CHROME_GEOMETRY_BY_KEY.get(key)
            if expected_geometry is None:
                continue
            geometry_properties = {
                "mobaTabStaticWidth": expected_geometry.width,
                "mobaTabStaticHeight": expected_geometry.height,
                "mobaTabCornerRadius": expected_geometry.corner_radius,
                "mobaTabIconX": expected_geometry.icon_x,
                "mobaTabIconY": expected_geometry.icon_y,
                "mobaTabIconSize": expected_geometry.icon_size,
                "mobaTabLabelX": expected_geometry.label_x,
                "mobaTabLabelY": expected_geometry.label_y,
                "mobaTabCloseRightOffset": expected_geometry.close_right_offset,
                "mobaTabCloseY": expected_geometry.close_y,
                "mobaTabPlusX": expected_geometry.plus_x,
                "mobaTabPlusY": expected_geometry.plus_y,
                "mobaTabGapAfter": expected_geometry.gap_after,
            }
            for property_name, expected_value in geometry_properties.items():
                if int(widget.property(property_name) or -1) != expected_value:
                    errors.append(f"mobaxterm live GUI tab chrome {key!r} {property_name} drifted")
        utility_rail = window.findChild(QFrame, "mobaRightUtilityRail")
        if utility_rail is None:
            errors.append("mobaxterm live GUI missing right utility rail")
        else:
            rail_properties = {
                "mobaRightUtilityRailStaticWidth": EXPECTED_MOBA_RIGHT_UTILITY_RAIL_CHROME.static_width,
                "mobaRightUtilityRailLiveWidth": EXPECTED_MOBA_RIGHT_UTILITY_RAIL_CHROME.live_width,
                "mobaRightUtilityRailActionSpacing": EXPECTED_MOBA_RIGHT_UTILITY_RAIL_CHROME.action_spacing,
                "mobaRightUtilityRailSessionEdgeTopY": EXPECTED_MOBA_RIGHT_UTILITY_RAIL_CHROME.session_edge_top_y,
                "mobaRightUtilityRailSessionEdgeHeight": EXPECTED_MOBA_RIGHT_UTILITY_RAIL_CHROME.session_edge_height,
                "mobaRightUtilityRailSessionEdgeIconX": EXPECTED_MOBA_RIGHT_UTILITY_RAIL_CHROME.session_edge_icon_x,
                "mobaRightUtilityRailSessionEdgeIconSize": EXPECTED_MOBA_RIGHT_UTILITY_RAIL_CHROME.session_edge_icon_size,
            }
            for property_name, expected_value in rail_properties.items():
                if int(utility_rail.property(property_name) or -1) != expected_value:
                    errors.append(f"mobaxterm live GUI right utility rail {property_name} drifted")
            if list(utility_rail.property("mobaRightUtilityRailMargins") or []) != [
                EXPECTED_MOBA_RIGHT_UTILITY_RAIL_CHROME.margin_left,
                EXPECTED_MOBA_RIGHT_UTILITY_RAIL_CHROME.margin_top,
                EXPECTED_MOBA_RIGHT_UTILITY_RAIL_CHROME.margin_right,
                EXPECTED_MOBA_RIGHT_UTILITY_RAIL_CHROME.margin_bottom,
            ]:
                errors.append("mobaxterm live GUI right utility rail margins drifted")
            if utility_rail.width() != EXPECTED_MOBA_RIGHT_UTILITY_RAIL_CHROME.live_width:
                errors.append("mobaxterm live GUI right utility rail live width drifted")
        utility_buttons = window.findChildren(QToolButton, "mobaRightUtilityAction")
        utility_keys = {str(button.property("mobaRightUtilityKey") or "") for button in utility_buttons}
        missing_utility_keys = sorted(EXPECTED_MOBA_RIGHT_UTILITY_KEYS - utility_keys)
        if missing_utility_keys:
            errors.append(f"mobaxterm live GUI right utility rail missing keys: {missing_utility_keys}")
        for button in utility_buttons:
            key = str(button.property("mobaRightUtilityKey") or "")
            icon_key = str(button.property("mobaRightUtilityIconKey") or "")
            if key in EXPECTED_MOBA_RIGHT_UTILITY_KEYS and not icon_key:
                errors.append(f"mobaxterm live GUI right utility action {key!r} missing icon key")
            expected_icon_key = EXPECTED_MOBA_RIGHT_UTILITY_ICON_KEYS.get(key)
            if expected_icon_key is not None and icon_key != expected_icon_key:
                errors.append(
                    f"mobaxterm live GUI right utility action {key!r} icon key {icon_key!r} "
                    f"must equal {expected_icon_key!r}"
                )
            expected_action = EXPECTED_MOBA_RIGHT_UTILITY_BY_KEY.get(key)
            if expected_action is not None:
                geometry_properties = {
                    "mobaRightUtilityStaticX": expected_action.static_x,
                    "mobaRightUtilityStaticY": expected_action.static_y,
                    "mobaRightUtilityStaticSize": expected_action.static_size,
                    "mobaRightUtilityLiveIconSize": expected_action.live_icon_size,
                    "mobaRightUtilityButtonSize": expected_action.button_size,
                }
                for property_name, expected_value in geometry_properties.items():
                    if int(button.property(property_name) or -1) != expected_value:
                        errors.append(
                            f"mobaxterm live GUI right utility action {key!r} "
                            f"{property_name} drifted"
                        )
                if str(button.property("mobaRightUtilityRenderSource") or "") != expected_action.render_source:
                    errors.append(f"mobaxterm live GUI right utility action {key!r} render source drifted")
                if button.iconSize().width() != expected_action.live_icon_size:
                    errors.append(f"mobaxterm live GUI right utility action {key!r} icon size drifted")
                if button.width() != expected_action.button_size or button.height() != expected_action.button_size:
                    errors.append(f"mobaxterm live GUI right utility action {key!r} button size drifted")
            if button.icon().isNull():
                errors.append(f"mobaxterm live GUI right utility action {key!r} must use a generated icon")
        edge_controls = window.findChild(QFrame, "mobaSessionEdgeControls")
        if edge_controls is not None:
            control_properties = {
                "mobaSessionEdgeTopY": EXPECTED_MOBA_RIGHT_UTILITY_RAIL_CHROME.session_edge_top_y,
                "mobaSessionEdgeStaticHeight": EXPECTED_MOBA_RIGHT_UTILITY_RAIL_CHROME.session_edge_height,
                "mobaSessionEdgeIconX": EXPECTED_MOBA_RIGHT_UTILITY_RAIL_CHROME.session_edge_icon_x,
                "mobaSessionEdgeIconSize": EXPECTED_MOBA_RIGHT_UTILITY_RAIL_CHROME.session_edge_icon_size,
            }
            for property_name, expected_value in control_properties.items():
                if int(edge_controls.property(property_name) or -1) != expected_value:
                    errors.append(f"mobaxterm live GUI session edge controls {property_name} drifted")
            if str(edge_controls.property("mobaSessionEdgePlacement") or "") != "tab-strip-overlay":
                errors.append("mobaxterm live GUI session edge controls placement drifted")
            expected_relative_y = [
                action.relative_y(EXPECTED_MOBA_RIGHT_UTILITY_RAIL_CHROME.session_edge_top_y)
                for action in EXPECTED_MOBA_SESSION_EDGE_ACTIONS
            ]
            if list(edge_controls.property("mobaSessionEdgeRelativeY") or []) != expected_relative_y:
                errors.append("mobaxterm live GUI session edge controls relative y offsets drifted")
        edge_buttons = window.findChildren(QToolButton, "mobaSessionEdgeAction")
        edge_keys = {str(button.property("mobaSessionEdgeKey") or "") for button in edge_buttons}
        missing_edge_keys = sorted(EXPECTED_MOBA_SESSION_EDGE_KEYS - edge_keys)
        if missing_edge_keys:
            errors.append(f"mobaxterm live GUI session edge shortcuts missing keys: {missing_edge_keys}")
        for button in edge_buttons:
            key = str(button.property("mobaSessionEdgeKey") or "")
            icon_key = str(button.property("mobaSessionEdgeIconKey") or "")
            if key in EXPECTED_MOBA_SESSION_EDGE_KEYS and not icon_key:
                errors.append(f"mobaxterm live GUI session edge shortcut {key!r} missing icon key")
            expected_icon_key = EXPECTED_MOBA_SESSION_EDGE_ICON_KEYS.get(key)
            if expected_icon_key is not None and icon_key != expected_icon_key:
                errors.append(
                    f"mobaxterm live GUI session edge shortcut {key!r} icon key {icon_key!r} "
                    f"must equal {expected_icon_key!r}"
                )
            if button.icon().isNull():
                errors.append(f"mobaxterm live GUI session edge shortcut {key!r} must use a generated icon")
            expected_action = EXPECTED_MOBA_SESSION_EDGE_BY_KEY.get(key)
            if expected_action is not None:
                relative_y = expected_action.relative_y(EXPECTED_MOBA_RIGHT_UTILITY_RAIL_CHROME.session_edge_top_y)
                geometry_properties = {
                    "mobaSessionEdgeStaticY": expected_action.static_y,
                    "mobaSessionEdgeRelativeY": relative_y,
                    "mobaSessionEdgeStaticSize": expected_action.static_size,
                    "mobaSessionEdgeLiveIconSize": expected_action.live_icon_size,
                    "mobaSessionEdgeButtonSize": expected_action.button_size,
                }
                for property_name, expected_value in geometry_properties.items():
                    if int(button.property(property_name) or -1) != expected_value:
                        errors.append(f"mobaxterm live GUI session edge shortcut {key!r} {property_name} drifted")
                if str(button.property("mobaSessionEdgeRenderSource") or "") != expected_action.render_source:
                    errors.append(f"mobaxterm live GUI session edge shortcut {key!r} render source drifted")
                if button.y() != relative_y:
                    errors.append(f"mobaxterm live GUI session edge shortcut {key!r} relative placement drifted")
                if button.width() != expected_action.button_size or button.height() != expected_action.button_size:
                    errors.append(f"mobaxterm live GUI session edge shortcut {key!r} button size drifted")
                if button.iconSize().width() != expected_action.live_icon_size:
                    errors.append(f"mobaxterm live GUI session edge shortcut {key!r} live icon size drifted")
            if int(button.property("mobaSessionEdgeIconX") or -1) != EXPECTED_MOBA_RIGHT_UTILITY_RAIL_CHROME.session_edge_icon_x:
                errors.append(f"mobaxterm live GUI session edge shortcut {key!r} icon x drifted")
            if (
                int(button.property("mobaSessionEdgeIconSize") or -1)
                != EXPECTED_MOBA_RIGHT_UTILITY_RAIL_CHROME.session_edge_icon_size
            ):
                errors.append(f"mobaxterm live GUI session edge shortcut {key!r} icon size metadata drifted")
            if button.iconSize().width() != EXPECTED_MOBA_RIGHT_UTILITY_RAIL_CHROME.session_edge_icon_size:
                errors.append(f"mobaxterm live GUI session edge shortcut {key!r} icon size drifted")
        status_notice = window.findChild(QLabel, "productStatusNotice")
        if status_notice is None:
            errors.append("mobaxterm live GUI missing bottom status notice")
        elif EXPECTED_MOBA_STATUS_CHROME.notice not in status_notice.text():
            errors.append("mobaxterm live GUI bottom status notice text drifted")
        else:
            notice_properties = {
                "mobaStatusNoticeX": EXPECTED_MOBA_STATUS_CHROME.notice_x,
                "mobaStatusNoticeY": EXPECTED_MOBA_STATUS_CHROME.notice_y,
                "mobaStatusProductNoteX": EXPECTED_MOBA_STATUS_CHROME.product_note_x,
                "mobaStatusProductNoteY": EXPECTED_MOBA_STATUS_CHROME.product_note_y,
                "mobaStatusTextFontSize": EXPECTED_MOBA_STATUS_CHROME.text_font_size,
            }
            for property_name, expected_value in notice_properties.items():
                if status_notice.property(property_name) != expected_value:
                    errors.append(f"mobaxterm live GUI bottom status notice property {property_name} drifted")
        status_bar = window.statusBar()
        status_bar_properties = {
            "mobaStatusStaticHeight": EXPECTED_MOBA_STATUS_CHROME.static_height,
            "mobaStatusSegmentStartRightOffset": EXPECTED_MOBA_STATUS_CHROME.segment_start_right_offset,
        }
        for property_name, expected_value in status_bar_properties.items():
            if status_bar.property(property_name) != expected_value:
                errors.append(f"mobaxterm live GUI status bar property {property_name} drifted")
        status_marker = window.findChild(QLabel, "productStatusMarker")
        if status_marker is None:
            errors.append("mobaxterm live GUI missing bottom status right marker")
        elif status_marker.text() != EXPECTED_MOBA_STATUS_CHROME.right_marker:
            errors.append("mobaxterm live GUI bottom status marker drifted")
        else:
            marker_properties = {
                "mobaStatusMarkerRightInset": EXPECTED_MOBA_STATUS_CHROME.marker_right_inset,
                "mobaStatusMarkerY": EXPECTED_MOBA_STATUS_CHROME.marker_y,
                "mobaStatusMarkerWidth": EXPECTED_MOBA_STATUS_CHROME.marker_width,
                "mobaStatusMarkerHeight": EXPECTED_MOBA_STATUS_CHROME.marker_height,
            }
            for property_name, expected_value in marker_properties.items():
                if status_marker.property(property_name) != expected_value:
                    errors.append(f"mobaxterm live GUI bottom status marker property {property_name} drifted")
        bottom_buttons = window.findChildren(QToolButton, "mobaBottomEdgeControl")
        bottom_keys = {str(button.property("mobaBottomEdgeKey") or "") for button in bottom_buttons}
        missing_bottom_keys = sorted(EXPECTED_MOBA_BOTTOM_EDGE_KEYS - bottom_keys)
        if missing_bottom_keys:
            errors.append(f"mobaxterm live GUI bottom-edge controls missing keys: {missing_bottom_keys}")
        for button in bottom_buttons:
            key = str(button.property("mobaBottomEdgeKey") or "")
            icon_key = str(button.property("mobaBottomEdgeIconKey") or "")
            if key in EXPECTED_MOBA_BOTTOM_EDGE_KEYS and not icon_key:
                errors.append(f"mobaxterm live GUI bottom-edge control {key!r} missing icon key")
            expected_icon_key = EXPECTED_MOBA_BOTTOM_EDGE_ICON_KEYS.get(key)
            if expected_icon_key is not None and icon_key != expected_icon_key:
                errors.append(
                    f"mobaxterm live GUI bottom-edge control {key!r} icon key {icon_key!r} "
                    f"must equal {expected_icon_key!r}"
                )
            if button.icon().isNull():
                errors.append(f"mobaxterm live GUI bottom-edge control {key!r} must use a generated icon")
        status_keys = {
            str(label.property("productStatusKey") or "")
            for label in window.findChildren(QLabel, "productStatusSegment")
        }
        missing_status_keys = sorted(EXPECTED_MOBA_STATUS_KEYS - status_keys)
        if missing_status_keys:
            errors.append(f"mobaxterm live GUI status bar missing keyed segments: {missing_status_keys}")

    errors.extend(check_live_tree_content(window, preset_id))
    status_texts = {label.text() for label in window.findChildren(QLabel, "productStatusSegment")}
    for text in gui_design_status_segments(preset_id):
        if text not in status_texts:
            errors.append(f"{preset_id} live GUI status segment missing text: {text}")

    if preset_id == "mobaxterm":
        errors.extend(check_live_moba_connected_session_route(window))
        errors.extend(check_live_moba_connected_session_identity_route(window))
        errors.extend(check_live_moba_home_welcome(window))
    else:
        errors.extend(check_live_workflow_cards(window, preset_id))
        errors.extend(check_live_workspace_surface(window, preset_id))
        errors.extend(check_live_reference_state(window, preset_id))
        if preset_id == "securecrt":
            errors.extend(check_live_securecrt_top_chrome(window))
            errors.extend(check_live_securecrt_session_manager_chrome(window))
            errors.extend(check_live_securecrt_session_status_strip(window))
            errors.extend(check_live_securecrt_session_manager_route(window))
            errors.extend(check_live_securecrt_command_window(window))
        if preset_id == "remmina":
            errors.extend(check_live_remmina_profile_list_chrome(window))
            errors.extend(check_live_remmina_viewer_controls(window))
            errors.extend(check_live_remmina_profile_viewer_route(window))
            errors.extend(check_live_remmina_clipboard_route(window))
        if preset_id == "termius":
            errors.extend(check_live_termius_hosts_chrome(window))
            errors.extend(check_live_termius_header_chips(window))
            errors.extend(check_live_termius_host_identity_strip(window))
            errors.extend(check_live_termius_host_selection_route(window))
            errors.extend(check_live_termius_sync_route(window))
        if preset_id == "mremoteng":
            errors.extend(check_live_mremoteng_top_chrome(window))
            errors.extend(check_live_mremoteng_document_controls(window))
            errors.extend(check_live_mremoteng_property_grid(window))
            errors.extend(check_live_mremoteng_connection_document_route(window))
    errors.extend(check_live_interaction_state(window, preset_id))
    return errors


def live_tab_labels(tabs: Any) -> set[str]:
    return {tabs.tabText(index) for index in range(tabs.count())}


def check_live_moba_connected_session_route(window: Any) -> list[str]:
    from PyQt6.QtWidgets import QLineEdit, QTabWidget, QTextEdit, QWidget

    route = EXPECTED_MOBA_CONNECTED_SESSION_ROUTE
    errors: list[str] = []
    tabs = window.findChild(QTabWidget, route.active_tab_object)
    if tabs is None:
        return ["mobaxterm live GUI connected-session route missing session tabs"]
    if route.active_tab_label not in live_tab_labels(tabs):
        errors.append(f"mobaxterm live GUI connected-session route missing active tab {route.active_tab_label!r}")

    route_widgets = [
        ("tabs", tabs),
        ("connected-panel", window.findChild(QWidget, route.connected_panel_object)),
        ("left-dock", window.findChild(QWidget, route.left_dock_object)),
        ("sftp-browser", window.findChild(QWidget, route.sftp_browser_object)),
        ("sftp-path", window.findChild(QWidget, route.sftp_path_object)),
        ("sftp-table", window.findChild(QWidget, route.sftp_table_object)),
        ("ssh-banner", window.findChild(QWidget, route.ssh_banner_object)),
        ("terminal-area", window.findChild(QWidget, route.terminal_area_object)),
        ("terminal-output", window.findChild(QWidget, route.terminal_output_object)),
        ("telemetry-bar", window.findChild(QWidget, route.telemetry_bar_object)),
    ]
    route_properties = {
        "mobaConnectedRouteKey": route.key,
        "mobaConnectedRouteRole": route.route_role,
        "mobaConnectedRouteActiveTabKey": route.active_tab_key,
        route.tab_label_property: route.active_tab_label,
        "mobaConnectedRouteReferenceTabLabel": route.reference_tab_label,
        "mobaConnectedRouteActiveTabObject": route.active_tab_object,
        "mobaConnectedRouteConnectedPanelObject": route.connected_panel_object,
        "mobaConnectedRouteLeftDockObject": route.left_dock_object,
        "mobaConnectedRouteSftpBrowserObject": route.sftp_browser_object,
        "mobaConnectedRouteSftpPathObject": route.sftp_path_object,
        "mobaConnectedRouteSftpTableObject": route.sftp_table_object,
        "mobaConnectedRouteSshBannerObject": route.ssh_banner_object,
        "mobaConnectedRouteTerminalAreaObject": route.terminal_area_object,
        "mobaConnectedRouteTerminalOutputObject": route.terminal_output_object,
        "mobaConnectedRouteTelemetryBarObject": route.telemetry_bar_object,
        "mobaConnectedRouteTelemetryIdentityCellKey": route.telemetry_identity_cell_key,
        route.target_property: route.target,
        route.remote_path_property: route.remote_path,
        "mobaConnectedRouteRenderSource": route.render_source,
    }
    for label, widget in route_widgets:
        if widget is None:
            errors.append(f"mobaxterm live GUI connected-session route missing {label}")
            continue
        for property_name, expected_value in route_properties.items():
            actual_value = str(widget.property(property_name) or "")
            if actual_value != expected_value:
                errors.append(
                    f"mobaxterm live GUI connected-session route {label} property "
                    f"{property_name} {actual_value!r} must equal {expected_value!r}"
                )

    path = window.findChild(QLineEdit, route.sftp_path_object)
    if path is not None and path.text() != route.remote_path:
        errors.append("mobaxterm live GUI connected-session route SFTP path text drifted")
    terminal_output = window.findChild(QTextEdit, route.terminal_output_object)
    if terminal_output is not None and not bool(terminal_output.property("mobaPlainTerminalMode")):
        errors.append("mobaxterm live GUI connected-session route terminal output must be plain Moba mode")
    telemetry_identity_cells = [
        widget
        for widget in window.findChildren(QWidget, "mobaTelemetryCell")
        if str(widget.property("mobaTelemetryKey") or "") == route.telemetry_identity_cell_key
    ]
    if len(telemetry_identity_cells) != 1:
        errors.append("mobaxterm live GUI connected-session route must expose one telemetry identity cell")
    elif str(telemetry_identity_cells[0].property("mobaTelemetryDisplayText") or "") != (
        EXPECTED_MOBA_TELEMETRY_CELLS[0].display_text
    ):
        errors.append("mobaxterm live GUI connected-session route telemetry identity target drifted")
    return errors


def check_live_moba_connected_session_identity_route(window: Any) -> list[str]:
    from PyQt6.QtWidgets import QLabel, QTabWidget, QTextEdit, QWidget

    route = EXPECTED_MOBA_CONNECTED_SESSION_IDENTITY_ROUTE
    errors: list[str] = []
    tabs = window.findChild(QTabWidget, "sessionTabs")
    banner_target = window.findChild(QLabel, "mobaSshBannerTargetLine")
    terminal_output = window.findChild(QTextEdit, "terminalOutput")
    telemetry_identity_cells = [
        widget
        for widget in window.findChildren(QWidget, "mobaTelemetryCell")
        if str(widget.property("mobaTelemetryKey") or "") == "target"
    ]
    identity_widgets = [
        ("window", window),
        ("tabs", tabs),
        ("banner-target", banner_target),
        ("terminal-output", terminal_output),
        ("telemetry-target", telemetry_identity_cells[0] if telemetry_identity_cells else None),
    ]
    identity_properties = {
        "mobaConnectedIdentityRouteKey": route.key,
        "mobaConnectedIdentityRouteRole": route.route_role,
        route.window_title_property: route.window_title,
        "mobaConnectedIdentityActiveTabLabel": route.active_tab_label,
        "mobaConnectedIdentityReferenceTabLabel": route.reference_tab_label,
        route.banner_target_property: route.banner_target,
        "mobaConnectedIdentityWebConsoleLine": route.web_console_line,
        route.terminal_prompt_property: route.terminal_prompt,
        route.telemetry_target_property: route.telemetry_target,
        "mobaConnectedIdentityTargetEndpoint": route.target_endpoint,
        "mobaConnectedIdentityRemotePath": route.remote_path,
        "mobaConnectedIdentityRenderSource": route.render_source,
    }
    if window.windowTitle() != route.window_title:
        errors.append("mobaxterm live GUI connected identity window title drifted")
    if tabs is None or route.active_tab_label not in live_tab_labels(tabs):
        errors.append("mobaxterm live GUI connected identity active tab label drifted")
    if banner_target is None or banner_target.text() != f"> SSH session to {route.banner_target}":
        errors.append("mobaxterm live GUI connected identity banner target drifted")
    if terminal_output is None:
        errors.append("mobaxterm live GUI connected identity missing terminal output")
    else:
        terminal_text = terminal_output.toPlainText()
        if route.web_console_line not in terminal_text:
            errors.append("mobaxterm live GUI connected identity web console line drifted")
        if route.terminal_prompt not in terminal_text:
            errors.append("mobaxterm live GUI connected identity terminal prompt drifted")
    if len(telemetry_identity_cells) != 1:
        errors.append("mobaxterm live GUI connected identity must expose one target telemetry cell")
    elif str(telemetry_identity_cells[0].property("mobaTelemetryDisplayText") or "") != route.telemetry_target:
        errors.append("mobaxterm live GUI connected identity telemetry target drifted")

    for label, widget in identity_widgets:
        if widget is None:
            errors.append(f"mobaxterm live GUI connected identity route missing {label}")
            continue
        for property_name, expected_value in identity_properties.items():
            actual_value = str(widget.property(property_name) or "")
            if actual_value != expected_value:
                errors.append(
                    f"mobaxterm live GUI connected identity {label} property "
                    f"{property_name} {actual_value!r} must equal {expected_value!r}"
                )
    return errors


def check_live_tree_content(window: Any, preset_id: str) -> list[str]:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QTreeWidget

    tree = window.findChild(QTreeWidget, "profileTree")
    if tree is None:
        return [f"{preset_id} live GUI missing profile tree for content contract"]
    errors: list[str] = []
    labels = collect_tree_labels(tree)
    expected = EXPECTED_LIVE_TREE_LABELS.get(preset_id, set())
    missing = sorted(expected - labels)
    if missing:
        errors.append(f"{preset_id} live GUI profile tree missing expected labels: {missing}")
    if preset_id in EXPECTED_PRODUCT_TREE_ICON_ROWS:
        user_role = int(Qt.ItemDataRole.UserRole)
        errors.extend(check_product_tree_icon_metadata(tree, preset_id, user_role))
        if preset_id == "mobaxterm":
            errors.extend(check_moba_session_tree_geometry(tree, user_role))
    return errors


def collect_tree_labels(tree: Any) -> set[str]:
    labels: set[str] = set()

    def walk(item: Any) -> None:
        labels.add(item.text(0))
        for child_index in range(item.childCount()):
            walk(item.child(child_index))

    for index in range(tree.topLevelItemCount()):
        walk(tree.topLevelItem(index))
    return labels


def check_product_tree_icon_metadata(tree: Any, preset_id: str, user_role: int) -> list[str]:
    errors: list[str] = []
    rows = collect_tree_icon_metadata(tree, user_role)
    expected_icon_keys = EXPECTED_PRODUCT_TREE_ICON_KEYS[preset_id]
    expected_row_kinds = EXPECTED_PRODUCT_TREE_ROW_KINDS[preset_id]
    expected_icon_sizes = EXPECTED_PRODUCT_TREE_ICON_SIZES[preset_id]
    for label, expected_icon_key in expected_icon_keys.items():
        metadata = rows.get(label)
        if metadata is None:
            errors.append(f"{preset_id} live GUI profile tree missing icon metadata row: {label}")
            continue
        if metadata["icon_key"] != expected_icon_key:
            errors.append(
                f"{preset_id} live GUI profile tree row {label!r} icon key {metadata['icon_key']!r} "
                f"must equal {expected_icon_key!r}"
            )
        expected_kind = expected_row_kinds[label]
        if metadata["row_kind"] != expected_kind:
            errors.append(
                f"{preset_id} live GUI profile tree row {label!r} kind {metadata['row_kind']!r} "
                f"must equal {expected_kind!r}"
            )
        expected_size = expected_icon_sizes[label]
        if metadata["icon_size"] != expected_size:
            errors.append(
                f"{preset_id} live GUI profile tree row {label!r} icon size {metadata['icon_size']!r} "
                f"must equal {expected_size!r}"
            )
        if metadata["icon_render"] != "generated-pixmap":
            errors.append(f"{preset_id} live GUI profile tree row {label!r} must use generated-pixmap icon render")
        if not metadata["has_icon"]:
            errors.append(f"{preset_id} live GUI profile tree row {label!r} must expose a non-null icon")
    return errors


def check_securecrt_tree_icon_metadata(tree: Any, user_role: int) -> list[str]:
    return check_product_tree_icon_metadata(tree, "securecrt", user_role)


def check_moba_session_tree_geometry(tree: Any, user_role: int) -> list[str]:
    errors: list[str] = []
    chrome = EXPECTED_MOBA_SESSION_TREE_CHROME
    expected_properties = {
        "mobaSessionTreeHeaderHeight": chrome.header_height,
        "mobaSessionTreeHeaderIconX": chrome.header_icon_x,
        "mobaSessionTreeHeaderTextX": chrome.header_text_x,
        "mobaSessionTreeRowStartY": chrome.row_start_y,
        "mobaSessionTreeIndentation": chrome.indentation,
        "mobaSessionTreeRootRowHeight": chrome.root_row_height,
        "mobaSessionTreeGroupRowHeight": chrome.group_row_height,
        "mobaSessionTreeProfileRowHeight": chrome.profile_row_height,
        "mobaSessionTreeGroupIconX": chrome.group_icon_x,
        "mobaSessionTreeGroupLabelX": chrome.group_label_x,
        "mobaSessionTreeProfileIconX": chrome.profile_icon_x,
        "mobaSessionTreeProfileLabelX": chrome.profile_label_x,
        "mobaSessionTreeProfileTargetX": chrome.profile_target_x,
        "mobaSessionTreeSelectedLeft": chrome.selected_left,
        "mobaSessionTreeSelectedHeight": chrome.selected_height,
        "mobaSessionTreeRenderSource": chrome.render_source,
    }
    for property_name, expected_value in expected_properties.items():
        if tree.property(property_name) != expected_value:
            errors.append(f"mobaxterm live GUI session tree property {property_name} drifted")
    if tree.indentation() != chrome.indentation:
        errors.append("mobaxterm live GUI session tree indentation drifted")
    if tree.isAnimated() != chrome.animated:
        errors.append("mobaxterm live GUI session tree animation state drifted")
    if tree.uniformRowHeights() != chrome.uniform_row_heights:
        errors.append("mobaxterm live GUI session tree uniform-row-height state drifted")

    rows = collect_tree_icon_metadata(tree, user_role)
    expected_row_geometry = {
        "User sessions": (chrome.root_row_height, chrome.header_icon_x, chrome.header_text_x, 0),
        "default": (chrome.group_row_height, chrome.group_icon_x, chrome.group_label_x, 0),
        "prod": (chrome.group_row_height, chrome.group_icon_x, chrome.group_label_x, 0),
        "files": (chrome.group_row_height, chrome.group_icon_x, chrome.group_label_x, 0),
        "edge-prod": (chrome.profile_row_height, chrome.profile_icon_x, chrome.profile_label_x, chrome.profile_target_x),
        "sftp-ops": (chrome.profile_row_height, chrome.profile_icon_x, chrome.profile_label_x, chrome.profile_target_x),
    }
    for label, (row_height, icon_x, label_x, target_x) in expected_row_geometry.items():
        metadata = rows.get(label)
        if metadata is None:
            errors.append(f"mobaxterm live GUI session tree missing geometry row: {label}")
            continue
        expected = {
            "row_height": row_height,
            "static_icon_x": icon_x,
            "static_label_x": label_x,
            "static_target_x": target_x,
        }
        for key, expected_value in expected.items():
            if metadata[key] != expected_value:
                errors.append(f"mobaxterm live GUI session tree row {label!r} {key} drifted")
    return errors


def collect_tree_icon_metadata(tree: Any, user_role: int) -> dict[str, dict[str, object]]:
    rows: dict[str, dict[str, object]] = {}

    def walk(item: Any) -> None:
        label = item.text(0)
        rows[label] = {
            "icon_key": str(item.data(0, user_role + 31) or ""),
            "row_kind": str(item.data(0, user_role + 32) or ""),
            "icon_size": int(item.data(0, user_role + 33) or 0),
            "icon_render": str(item.data(0, user_role + 34) or ""),
            "row_height": int(item.data(0, user_role + 35) or 0),
            "static_icon_x": int(item.data(0, user_role + 36) or 0),
            "static_label_x": int(item.data(0, user_role + 37) or 0),
            "static_target_x": int(item.data(0, user_role + 38) or 0),
            "has_icon": not item.icon(0).isNull(),
        }
        for child_index in range(item.childCount()):
            walk(item.child(child_index))

    for index in range(tree.topLevelItemCount()):
        walk(tree.topLevelItem(index))
    return rows


def check_live_layout_contracts(window: Any, preset_id: str) -> list[str]:
    errors: list[str] = []
    for contract in live_layout_contracts_for_preset(preset_id):
        object_name = str(contract["object_name"])
        bounds = live_widget_bounds(window, object_name)
        if bounds is None:
            errors.append(f"{preset_id} live GUI missing layout contract widget: {object_name}")
            continue
        errors.extend(validate_live_layout_contract(preset_id, contract, bounds))
    return errors


def check_live_topology_contracts(window: Any, preset_id: str) -> list[str]:
    errors: list[str] = []
    for contract in live_topology_contracts_for_preset(preset_id):
        first_name = str(contract["from"])
        second_name = str(contract["to"])
        first_bounds = live_widget_bounds(window, first_name)
        second_bounds = live_widget_bounds(window, second_name)
        if first_bounds is None:
            errors.append(f"{preset_id} live GUI missing topology widget: {first_name}")
            continue
        if second_bounds is None:
            errors.append(f"{preset_id} live GUI missing topology widget: {second_name}")
            continue
        errors.extend(validate_live_topology_contract(preset_id, contract, first_bounds, second_bounds))
    return errors


def collect_live_contract_evidence(window: Any, preset_id: str) -> dict[str, object]:
    return {
        "layout_measurements": collect_live_layout_measurements(window, preset_id),
        "topology_measurements": collect_live_topology_measurements(window, preset_id),
    }


def collect_live_layout_measurements(window: Any, preset_id: str) -> list[dict[str, object]]:
    measurements: list[dict[str, object]] = []
    for contract in live_layout_contracts_for_preset(preset_id):
        object_name = str(contract["object_name"])
        bounds = live_widget_bounds(window, object_name)
        measurements.append(layout_contract_measurement(preset_id, contract, bounds))
    return measurements


def collect_live_topology_measurements(window: Any, preset_id: str) -> list[dict[str, object]]:
    measurements: list[dict[str, object]] = []
    for contract in live_topology_contracts_for_preset(preset_id):
        first_name = str(contract["from"])
        second_name = str(contract["to"])
        measurements.append(
            topology_contract_measurement(
                preset_id,
                contract,
                live_widget_bounds(window, first_name),
                live_widget_bounds(window, second_name),
            )
        )
    return measurements


def layout_contract_measurement(
    preset_id: str,
    contract: dict[str, object],
    bounds: dict[str, int] | None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": str(contract["id"]),
        "widget": str(contract["object_name"]),
        "bounds": bounds,
    }
    if bounds is None:
        payload["passed"] = False
        payload["errors"] = [f"{preset_id} live GUI missing layout contract widget: {contract['object_name']}"]
        return payload
    errors = validate_live_layout_contract(preset_id, contract, bounds)
    payload["passed"] = not errors
    if errors:
        payload["errors"] = errors
    return payload


def topology_contract_measurement(
    preset_id: str,
    contract: dict[str, object],
    first_bounds: dict[str, int] | None,
    second_bounds: dict[str, int] | None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": str(contract["id"]),
        "from": str(contract["from"]),
        "to": str(contract["to"]),
        "relation": str(contract["relation"]),
        "from_bounds": first_bounds,
        "to_bounds": second_bounds,
    }
    if first_bounds is None or second_bounds is None:
        payload["passed"] = False
        missing = []
        if first_bounds is None:
            missing.append(str(contract["from"]))
        if second_bounds is None:
            missing.append(str(contract["to"]))
        payload["missing_widgets"] = missing
        return payload
    payload.update(topology_measurement_values(contract, first_bounds, second_bounds))
    errors = validate_live_topology_contract(preset_id, contract, first_bounds, second_bounds)
    payload["passed"] = not errors
    if errors:
        payload["errors"] = errors
    return payload


def topology_measurement_values(
    contract: dict[str, object],
    first_bounds: dict[str, int],
    second_bounds: dict[str, int],
) -> dict[str, object]:
    relation = str(contract["relation"])
    if relation == "left_of":
        return {"gap": second_bounds["x"] - (first_bounds["x"] + first_bounds["width"])}
    if relation == "right_of":
        return {"gap": first_bounds["x"] - (second_bounds["x"] + second_bounds["width"])}
    if relation == "above":
        return {"gap": second_bounds["y"] - (first_bounds["y"] + first_bounds["height"])}
    if relation == "below":
        return {"gap": first_bounds["y"] - (second_bounds["y"] + second_bounds["height"])}
    if relation == "inside":
        contained = (
            first_bounds["x"] >= second_bounds["x"]
            and first_bounds["y"] >= second_bounds["y"]
            and first_bounds["x"] + first_bounds["width"] <= second_bounds["x"] + second_bounds["width"]
            and first_bounds["y"] + first_bounds["height"] <= second_bounds["y"] + second_bounds["height"]
        )
        return {"contained": contained}
    if relation == "overlaps_x":
        return {
            "overlap": min(first_bounds["x"] + first_bounds["width"], second_bounds["x"] + second_bounds["width"])
            - max(first_bounds["x"], second_bounds["x"])
        }
    if relation == "overlaps_y":
        return {
            "overlap": min(first_bounds["y"] + first_bounds["height"], second_bounds["y"] + second_bounds["height"])
            - max(first_bounds["y"], second_bounds["y"])
        }
    return {}


def live_widget_bounds(window: Any, object_name: str) -> dict[str, int] | None:
    from PyQt6.QtCore import QPoint
    from PyQt6.QtWidgets import QWidget

    widget = window.findChild(QWidget, object_name)
    if widget is None:
        return None
    position = widget.mapTo(window, QPoint(0, 0))
    geometry = widget.geometry()
    return {
        "x": int(position.x()),
        "y": int(position.y()),
        "width": int(geometry.width()),
        "height": int(geometry.height()),
    }


def live_layout_contracts_for_preset(preset_id: str) -> list[dict[str, object]]:
    return list(LIVE_LAYOUT_CONTRACTS.get(preset_id, []))


def live_topology_contracts_for_preset(preset_id: str) -> list[dict[str, object]]:
    return list(LIVE_TOPOLOGY_CONTRACTS.get(preset_id, []))


def validate_live_layout_contract(
    preset_id: str,
    contract: dict[str, object],
    bounds: dict[str, int],
) -> list[str]:
    errors: list[str] = []
    label = str(contract.get("label") or contract.get("id") or contract.get("object_name"))
    for key, comparison in [
        ("min_x", "at least"),
        ("min_y", "at least"),
        ("min_width", "at least"),
        ("min_height", "at least"),
    ]:
        if key in contract and bounds[metric_name(key)] < int(contract[key]):
            errors.append(
                f"{preset_id} live GUI {label} {metric_name(key)} {bounds[metric_name(key)]} "
                f"must be {comparison} {contract[key]}"
            )
    for key, comparison in [
        ("max_x", "at most"),
        ("max_y", "at most"),
        ("max_width", "at most"),
        ("max_height", "at most"),
    ]:
        if key in contract and bounds[metric_name(key)] > int(contract[key]):
            errors.append(
                f"{preset_id} live GUI {label} {metric_name(key)} {bounds[metric_name(key)]} "
                f"must be {comparison} {contract[key]}"
            )
    return errors


def validate_live_topology_contract(
    preset_id: str,
    contract: dict[str, object],
    first_bounds: dict[str, int],
    second_bounds: dict[str, int],
) -> list[str]:
    contract_id = str(contract.get("id") or f"{contract.get('from')}->{contract.get('to')}")
    relation = str(contract["relation"])
    if relation == "left_of":
        return validate_live_gap_contract(
            preset_id,
            contract_id,
            contract,
            second_bounds["x"] - (first_bounds["x"] + first_bounds["width"]),
        )
    if relation == "right_of":
        return validate_live_gap_contract(
            preset_id,
            contract_id,
            contract,
            first_bounds["x"] - (second_bounds["x"] + second_bounds["width"]),
        )
    if relation == "above":
        return validate_live_gap_contract(
            preset_id,
            contract_id,
            contract,
            second_bounds["y"] - (first_bounds["y"] + first_bounds["height"]),
        )
    if relation == "below":
        return validate_live_gap_contract(
            preset_id,
            contract_id,
            contract,
            first_bounds["y"] - (second_bounds["y"] + second_bounds["height"]),
        )
    if relation == "inside":
        if (
            first_bounds["x"] < second_bounds["x"]
            or first_bounds["y"] < second_bounds["y"]
            or first_bounds["x"] + first_bounds["width"] > second_bounds["x"] + second_bounds["width"]
            or first_bounds["y"] + first_bounds["height"] > second_bounds["y"] + second_bounds["height"]
        ):
            return [
                (
                    f"{preset_id} live GUI topology {contract_id} expected {contract['from']} "
                    f"inside {contract['to']}"
                )
            ]
        return []
    if relation == "overlaps_x":
        overlap = min(first_bounds["x"] + first_bounds["width"], second_bounds["x"] + second_bounds["width"]) - max(
            first_bounds["x"], second_bounds["x"]
        )
        return validate_live_overlap_contract(preset_id, contract_id, contract, overlap)
    if relation == "overlaps_y":
        overlap = min(first_bounds["y"] + first_bounds["height"], second_bounds["y"] + second_bounds["height"]) - max(
            first_bounds["y"], second_bounds["y"]
        )
        return validate_live_overlap_contract(preset_id, contract_id, contract, overlap)
    return [f"{preset_id} live GUI topology {contract_id} has unsupported relation: {relation}"]


def validate_live_gap_contract(
    preset_id: str,
    contract_id: str,
    contract: dict[str, object],
    gap: int,
) -> list[str]:
    minimum = int(contract.get("min_gap", 0))
    if gap < minimum:
        return [f"{preset_id} live GUI topology {contract_id} gap {gap} below expected {minimum}"]
    maximum = contract.get("max_gap")
    if isinstance(maximum, int) and gap > maximum:
        return [f"{preset_id} live GUI topology {contract_id} gap {gap} above expected {maximum}"]
    return []


def validate_live_overlap_contract(
    preset_id: str,
    contract_id: str,
    contract: dict[str, object],
    overlap: int,
) -> list[str]:
    minimum = int(contract.get("min_overlap", 1))
    if overlap < minimum:
        return [f"{preset_id} live GUI topology {contract_id} overlap {overlap} below expected {minimum}"]
    return []


def metric_name(contract_key: str) -> str:
    return contract_key.split("_", 1)[1]


def check_live_workflow_cards(window: Any, preset_id: str) -> list[str]:
    from PyQt6.QtWidgets import QLabel, QWidget

    panel = window.findChild(QWidget, "productWorkflowEvidence")
    if panel is None:
        return [f"{preset_id} live GUI missing product workflow evidence strip"]
    actual_preset = str(panel.property("designPreset") or "")
    if actual_preset != preset_id:
        return [f"{preset_id} live GUI product workflow strip designPreset {actual_preset!r} must equal {preset_id!r}"]
    titles = {label.text() for label in panel.findChildren(QLabel, "productWorkflowTitle")}
    errors: list[str] = []
    for card in gui_design_workflow_cards(preset_id):
        if card.title not in titles:
            errors.append(f"{preset_id} live GUI workflow card missing title: {card.title}")
    return errors


def check_live_moba_home_welcome(window: Any) -> list[str]:
    from PyQt6.QtWidgets import QFrame, QLabel, QLineEdit, QPushButton

    chrome = EXPECTED_MOBA_HOME_WELCOME_CHROME
    geometry = EXPECTED_MOBA_HOME_WELCOME_GEOMETRY
    surface = gui_design_workspace_surface("mobaxterm")
    panel = window.findChild(QFrame, "mobaHomeWelcomeSurface")
    if panel is None:
        return ["mobaxterm live GUI missing Moba home welcome surface"]

    errors: list[str] = []
    if str(panel.property("designPreset") or "") != "mobaxterm":
        errors.append("mobaxterm home welcome designPreset metadata drifted")
    expected_panel_properties = {
        "mobaHomeTitle": chrome.title,
        "mobaHomeSubtitle": chrome.subtitle,
        "mobaHomeRecentTitle": chrome.recent_title,
    }
    for property_name, expected_value in expected_panel_properties.items():
        if str(panel.property(property_name) or "") != expected_value:
            errors.append(f"mobaxterm home welcome {property_name} metadata drifted")
    if int(panel.property("mobaHomeSearchWidth") or 0) != chrome.search_width:
        errors.append("mobaxterm home welcome search width metadata drifted")
    if int(panel.property("mobaHomeActionSpacing") or 0) != chrome.action_spacing:
        errors.append("mobaxterm home welcome action spacing metadata drifted")
    expected_geometry_properties = {
        "mobaHomeGeometryRenderSource": geometry.render_source,
        "mobaHomeCenterSideMargin": geometry.center_side_margin,
        "mobaHomeHeroMinY": geometry.hero_min_y,
        "mobaHomeHeroHeight": geometry.hero_height,
        "mobaHomeLogoSize": geometry.logo_size,
        "mobaHomeTitleGap": geometry.title_gap,
        "mobaHomeTitleYOffset": geometry.title_y_offset,
        "mobaHomeSubtitleYOffset": geometry.subtitle_y_offset,
        "mobaHomeButtonYOffset": geometry.button_y_offset,
        "mobaHomePrimaryActionWidth": geometry.primary_width,
        "mobaHomeSecondaryActionWidth": geometry.secondary_width,
        "mobaHomeActionGap": geometry.action_gap,
        "mobaHomeButtonHeight": geometry.button_height,
        "mobaHomeSearchYGap": geometry.search_y_gap,
        "mobaHomeSearchHeight": geometry.search_height,
        "mobaHomeRecentYGap": geometry.recent_y_gap,
        "mobaHomeRecentItemStep": geometry.recent_item_step,
        "mobaHomeFooterYOffset": geometry.footer_y_offset,
    }
    for property_name, expected_value in expected_geometry_properties.items():
        if panel.property(property_name) != expected_value:
            errors.append(f"mobaxterm home welcome geometry property {property_name} drifted")

    title = panel.findChild(QLabel, "mobaHomeTitle")
    subtitle = panel.findChild(QLabel, "mobaHomeSubtitle")
    logo = panel.findChild(QLabel, "mobaHomeLogo")
    if title is None or title.text() != chrome.title:
        errors.append("mobaxterm home welcome title text drifted")
    if subtitle is None or subtitle.text() != chrome.subtitle:
        errors.append("mobaxterm home welcome subtitle text drifted")
    if logo is None:
        errors.append("mobaxterm home welcome missing generated logo")
    elif str(logo.property("mobaHomeIconKey") or "") != chrome.icon_key:
        errors.append("mobaxterm home welcome logo icon key drifted")
    elif (
        int(logo.property("mobaHomeLogoSize") or 0) != geometry.logo_size
        or int(logo.property("mobaHomeLogoBoxWidth") or 0) != geometry.live_logo_box_width
        or int(logo.property("mobaHomeLogoBoxHeight") or 0) != geometry.live_logo_box_height
        or int(logo.property("mobaHomeLogoPixmapSize") or 0) != geometry.live_logo_pixmap_size
    ):
        errors.append("mobaxterm home welcome logo geometry metadata drifted")
    if title is not None:
        if int(title.property("mobaHomeTitleFontSize") or 0) != geometry.title_font_size:
            errors.append("mobaxterm home welcome title font metadata drifted")
        if int(title.property("mobaHomeTitleYOffset") or 0) != geometry.title_y_offset:
            errors.append("mobaxterm home welcome title y-offset metadata drifted")
    if subtitle is not None:
        if int(subtitle.property("mobaHomeSubtitleFontSize") or 0) != geometry.subtitle_font_size:
            errors.append("mobaxterm home welcome subtitle font metadata drifted")
        if int(subtitle.property("mobaHomeSubtitleYOffset") or 0) != geometry.subtitle_y_offset:
            errors.append("mobaxterm home welcome subtitle y-offset metadata drifted")

    action_buttons = panel.findChildren(QPushButton)
    action_by_key = {str(button.property("mobaHomeActionKey") or ""): button for button in action_buttons}
    expected_actions = {
        "primary": (surface.home_actions[0], chrome.primary_action_icon_key, geometry.primary_width),
        "secondary": (surface.home_actions[1], chrome.secondary_action_icon_key, geometry.secondary_width),
    }
    for key, (expected_text, expected_icon_key, expected_width) in expected_actions.items():
        button = action_by_key.get(key)
        if button is None:
            errors.append(f"mobaxterm home welcome missing {key} action")
            continue
        if button.text() != expected_text:
            errors.append(f"mobaxterm home welcome {key} action text drifted")
        if str(button.property("mobaHomeActionIconKey") or "") != expected_icon_key:
            errors.append(f"mobaxterm home welcome {key} action icon key drifted")
        if button.icon().isNull():
            errors.append(f"mobaxterm home welcome {key} action must use a generated icon")
        action_properties = {
            "mobaHomeActionStaticWidth": expected_width,
            "mobaHomeActionStaticHeight": geometry.button_height,
            "mobaHomeActionIconX": geometry.button_icon_x,
            "mobaHomeActionIconY": geometry.button_icon_y,
            "mobaHomeActionIconSize": geometry.button_icon_size,
        }
        for property_name, expected_value in action_properties.items():
            if int(button.property(property_name) or 0) != expected_value:
                errors.append(f"mobaxterm home welcome {key} action property {property_name} drifted")

    search = panel.findChild(QLineEdit, "homeSearch")
    if search is None:
        errors.append("mobaxterm home welcome missing search field")
    else:
        if search.placeholderText() != surface.home_search_placeholder:
            errors.append("mobaxterm home welcome search placeholder drifted")
        if str(search.property("mobaHomeSearchPlaceholder") or "") != surface.home_search_placeholder:
            errors.append("mobaxterm home welcome search placeholder metadata drifted")
        if int(search.property("mobaHomeSearchWidth") or 0) != chrome.search_width:
            errors.append("mobaxterm home welcome search field width metadata drifted")
        search_properties = {
            "mobaHomeSearchHeight": geometry.search_height,
            "mobaHomeSearchTextX": geometry.search_text_x,
            "mobaHomeSearchTextY": geometry.search_text_y,
            "mobaHomeSearchFontSize": geometry.search_font_size,
        }
        for property_name, expected_value in search_properties.items():
            if int(search.property(property_name) or 0) != expected_value:
                errors.append(f"mobaxterm home welcome search property {property_name} drifted")

    recent_title = panel.findChild(QLabel, "recentSessionsTitle")
    if recent_title is None or recent_title.text() != chrome.recent_title:
        errors.append("mobaxterm home welcome recent title drifted")
    elif (
        int(recent_title.property("mobaHomeRecentTitleFontSize") or 0) != geometry.recent_title_font_size
        or int(recent_title.property("mobaHomeRecentTitleTopMargin") or 0) != geometry.live_recent_title_top_margin
    ):
        errors.append("mobaxterm home welcome recent title geometry metadata drifted")
    recent_labels = panel.findChildren(QLabel, "mobaRecentSession")
    expected_recent = [item for column in surface.recent_columns for item in column]
    actual_recent = [label.text() for label in recent_labels]
    if actual_recent != expected_recent:
        errors.append("mobaxterm home welcome recent session labels drifted")
    for label in recent_labels:
        if label.property("mobaHomeRecentColumn") is None or label.property("mobaHomeRecentRow") is None:
            errors.append("mobaxterm home welcome recent label missing grid metadata")
            break
        if int(label.property("mobaHomeRecentItemStep") or 0) != geometry.recent_item_step:
            errors.append("mobaxterm home welcome recent item step metadata drifted")
            break
        if int(label.property("mobaHomeRecentColumnPadding") or 0) != geometry.recent_column_padding:
            errors.append("mobaxterm home welcome recent column padding metadata drifted")
            break

    footer = panel.findChild(QLabel, "mobaHomeFooter")
    if footer is None or footer.text() != surface.footer:
        errors.append("mobaxterm home welcome footer drifted")
    elif str(footer.property("mobaHomeFooter") or "") != surface.footer:
        errors.append("mobaxterm home welcome footer metadata drifted")
    elif (
        int(footer.property("mobaHomeFooterYOffset") or 0) != geometry.footer_y_offset
        or int(footer.property("mobaHomeFooterFontSize") or 0) != geometry.footer_font_size
        or int(footer.property("mobaHomeFooterTopMargin") or 0) != geometry.live_footer_top_margin
    ):
        errors.append("mobaxterm home welcome footer geometry metadata drifted")
    return errors


def check_live_workspace_surface(window: Any, preset_id: str) -> list[str]:
    from PyQt6.QtWidgets import QLabel, QWidget

    panel = window.findChild(QWidget, "productWorkspaceSurface")
    if panel is None:
        return [f"{preset_id} live GUI missing product workspace evidence surface"]
    actual_preset = str(panel.property("designPreset") or "")
    if actual_preset != preset_id:
        return [f"{preset_id} live GUI product workspace designPreset {actual_preset!r} must equal {preset_id!r}"]
    labels = {label.text() for label in panel.findChildren(QLabel)}
    missing = sorted(required_workspace_surface_texts(preset_id) - labels)
    if missing:
        return [f"{preset_id} live GUI product workspace missing text: {missing}"]
    return []


def check_live_reference_state(window: Any, preset_id: str) -> list[str]:
    from PyQt6.QtWidgets import QLabel, QWidget

    panel = window.findChild(QWidget, "productReferenceState")
    if panel is None:
        return [f"{preset_id} live GUI missing product reference state strip"]
    actual_preset = str(panel.property("designPreset") or "")
    if actual_preset != preset_id:
        return [f"{preset_id} live GUI product reference designPreset {actual_preset!r} must equal {preset_id!r}"]
    labels = {label.text() for label in panel.findChildren(QLabel, "productReferenceStateItem")}
    missing = sorted(required_reference_state_texts(preset_id) - labels)
    if missing:
        return [f"{preset_id} live GUI product reference state missing text: {missing}"]
    keys = {str(label.property("referenceKey") or "") for label in panel.findChildren(QLabel, "productReferenceStateItem")}
    expected_keys = {key for key, _value in gui_design_reference_state(preset_id).items()}
    missing_keys = sorted(expected_keys - keys)
    if missing_keys:
        return [f"{preset_id} live GUI product reference state missing keys: {missing_keys}"]
    return []


def required_reference_state_texts(preset_id: str) -> set[str]:
    reference = gui_design_reference_state(preset_id)
    return {f"{key}: {value}" for key, value in reference.items()}


def required_workspace_surface_texts(preset_id: str) -> set[str]:
    surface = gui_design_workspace_surface(preset_id)
    required = {
        surface.title,
        surface.primary_title,
        surface.primary_state,
        surface.command_line,
        surface.secondary_title,
        surface.secondary_state,
    }
    required.update(surface.detail_lines)
    required.update(surface.activity_lines)
    return required


def required_securecrt_command_window_texts() -> set[str]:
    chrome = gui_design_securecrt_command_window_chrome()
    return {
        chrome.title,
        chrome.helper,
        chrome.target_scope,
        chrome.command,
        chrome.send_label,
        chrome.status,
    }


def required_securecrt_session_status_texts() -> set[str]:
    chrome = gui_design_securecrt_session_status_strip()
    return {chrome.title, *{f"{field.label}: {field.value}" for field in chrome.fields}}


def required_securecrt_session_manager_texts() -> set[str]:
    chrome = gui_design_securecrt_session_manager_chrome()
    return {chrome.title}


def required_securecrt_top_chrome_texts() -> set[str]:
    chrome = gui_design_securecrt_top_chrome()
    return {
        chrome.window_title,
        *{item.label for item in chrome.menu_items},
        *{action.label for action in chrome.toolbar_actions},
    }


def required_mremoteng_top_chrome_texts() -> set[str]:
    chrome = gui_design_mremoteng_top_chrome()
    return {
        chrome.window_title,
        *{item.label for item in chrome.menu_items},
        *{action.label for action in chrome.toolbar_actions},
    }


def check_live_securecrt_top_chrome(window: Any) -> list[str]:
    from PyQt6.QtWidgets import QToolButton

    errors: list[str] = []
    chrome = gui_design_securecrt_top_chrome()
    menu_bar = window.menuBar()
    if menu_bar is None:
        return ["securecrt live GUI missing top menu bar"]
    if menu_bar.objectName() != "secureCrtMenuBar":
        errors.append(f"securecrt live GUI top menu bar objectName {menu_bar.objectName()!r} must equal 'secureCrtMenuBar'")
    if str(menu_bar.property("designPreset") or "") != "securecrt":
        errors.append("securecrt live GUI top menu bar designPreset metadata drifted")
    if str(menu_bar.property("secureCrtWindowTitle") or "") != chrome.window_title:
        errors.append("securecrt live GUI top menu window title metadata drifted")
    if list(menu_bar.property("secureCrtTopMenuKeys") or []) != EXPECTED_SECURECRT_TOP_MENU_KEYS:
        errors.append("securecrt live GUI top menu key metadata drifted")
    if list(menu_bar.property("secureCrtTopMenuLabels") or []) != EXPECTED_SECURECRT_TOP_MENU_LABELS:
        errors.append("securecrt live GUI top menu label metadata drifted")

    visible_actions = [action for action in menu_bar.actions() if action.isVisible()]
    actual_menu_keys = [str(action.property("secureCrtTopMenuKey") or "") for action in visible_actions]
    actual_menu_labels = [str(action.property("secureCrtTopMenuLabel") or action.text()) for action in visible_actions]
    if actual_menu_keys != EXPECTED_SECURECRT_TOP_MENU_KEYS:
        errors.append(
            f"securecrt live GUI top menu keys {actual_menu_keys!r} must equal {EXPECTED_SECURECRT_TOP_MENU_KEYS!r}"
        )
    if actual_menu_labels != EXPECTED_SECURECRT_TOP_MENU_LABELS:
        errors.append(
            f"securecrt live GUI top menu labels {actual_menu_labels!r} must equal {EXPECTED_SECURECRT_TOP_MENU_LABELS!r}"
        )

    toolbar_buttons = [
        button
        for button in window.findChildren(QToolButton)
        if str(button.property("secureCrtTopToolbarKey") or "")
    ]
    actual_toolbar_keys = [str(button.property("secureCrtTopToolbarKey") or "") for button in toolbar_buttons]
    if actual_toolbar_keys != EXPECTED_SECURECRT_TOP_TOOLBAR_KEYS:
        errors.append(
            f"securecrt live GUI top toolbar keys {actual_toolbar_keys!r} "
            f"must equal {EXPECTED_SECURECRT_TOP_TOOLBAR_KEYS!r}"
        )

    expected_by_key = {action.key: action for action in chrome.toolbar_actions}
    for button in toolbar_buttons:
        key = str(button.property("secureCrtTopToolbarKey") or "")
        expected = expected_by_key.get(key)
        if expected is None:
            errors.append(f"securecrt live GUI unexpected top toolbar key: {key!r}")
            continue
        if button.text() != expected.label:
            errors.append(f"securecrt live GUI top toolbar {key!r} label drifted")
        if str(button.property("secureCrtTopToolbarIconKey") or "") != expected.icon_key:
            errors.append(f"securecrt live GUI top toolbar {key!r} icon key drifted")
        if int(button.property("secureCrtTopToolbarStaticX") or 0) != expected.static_x:
            errors.append(f"securecrt live GUI top toolbar {key!r} static x drifted")
        if int(button.property("secureCrtTopToolbarStaticWidth") or 0) != expected.static_width:
            errors.append(f"securecrt live GUI top toolbar {key!r} static width drifted")
    return errors


def check_live_mremoteng_top_chrome(window: Any) -> list[str]:
    from PyQt6.QtWidgets import QToolButton

    errors: list[str] = []
    chrome = gui_design_mremoteng_top_chrome()
    menu_bar = window.menuBar()
    if menu_bar is None:
        return ["mremoteng live GUI missing top menu bar"]
    if menu_bar.objectName() != "mRemoteNgMenuBar":
        errors.append(
            f"mremoteng live GUI top menu bar objectName {menu_bar.objectName()!r} "
            "must equal 'mRemoteNgMenuBar'"
        )
    if str(menu_bar.property("designPreset") or "") != "mremoteng":
        errors.append("mremoteng live GUI top menu bar designPreset metadata drifted")
    if str(menu_bar.property("mRemoteNgWindowTitle") or "") != chrome.window_title:
        errors.append("mremoteng live GUI top menu window title metadata drifted")
    if list(menu_bar.property("mRemoteNgTopMenuKeys") or []) != EXPECTED_MREMOTENG_TOP_MENU_KEYS:
        errors.append("mremoteng live GUI top menu key metadata drifted")
    if list(menu_bar.property("mRemoteNgTopMenuLabels") or []) != EXPECTED_MREMOTENG_TOP_MENU_LABELS:
        errors.append("mremoteng live GUI top menu label metadata drifted")

    visible_actions = [action for action in menu_bar.actions() if action.isVisible()]
    actual_menu_keys = [str(action.property("mRemoteNgTopMenuKey") or "") for action in visible_actions]
    actual_menu_labels = [str(action.property("mRemoteNgTopMenuLabel") or action.text()) for action in visible_actions]
    if actual_menu_keys != EXPECTED_MREMOTENG_TOP_MENU_KEYS:
        errors.append(
            f"mremoteng live GUI top menu keys {actual_menu_keys!r} "
            f"must equal {EXPECTED_MREMOTENG_TOP_MENU_KEYS!r}"
        )
    if actual_menu_labels != EXPECTED_MREMOTENG_TOP_MENU_LABELS:
        errors.append(
            f"mremoteng live GUI top menu labels {actual_menu_labels!r} "
            f"must equal {EXPECTED_MREMOTENG_TOP_MENU_LABELS!r}"
        )

    toolbar_buttons = [
        button
        for button in window.findChildren(QToolButton)
        if str(button.property("mRemoteNgTopToolbarKey") or "")
    ]
    actual_toolbar_keys = [str(button.property("mRemoteNgTopToolbarKey") or "") for button in toolbar_buttons]
    if actual_toolbar_keys != EXPECTED_MREMOTENG_TOP_TOOLBAR_KEYS:
        errors.append(
            f"mremoteng live GUI top toolbar keys {actual_toolbar_keys!r} "
            f"must equal {EXPECTED_MREMOTENG_TOP_TOOLBAR_KEYS!r}"
        )

    expected_by_key = {action.key: action for action in chrome.toolbar_actions}
    for button in toolbar_buttons:
        key = str(button.property("mRemoteNgTopToolbarKey") or "")
        expected = expected_by_key.get(key)
        if expected is None:
            errors.append(f"mremoteng live GUI unexpected top toolbar key: {key!r}")
            continue
        if button.text() != expected.label:
            errors.append(f"mremoteng live GUI top toolbar {key!r} label drifted")
        if str(button.property("mRemoteNgTopToolbarIconKey") or "") != expected.icon_key:
            errors.append(f"mremoteng live GUI top toolbar {key!r} icon key drifted")
        if int(button.property("mRemoteNgTopToolbarStaticX") or 0) != expected.static_x:
            errors.append(f"mremoteng live GUI top toolbar {key!r} static x drifted")
        if int(button.property("mRemoteNgTopToolbarStaticWidth") or 0) != expected.static_width:
            errors.append(f"mremoteng live GUI top toolbar {key!r} static width drifted")
    return errors


def check_live_securecrt_session_manager_chrome(window: Any) -> list[str]:
    from PyQt6.QtWidgets import QLabel, QLineEdit, QToolButton, QWidget

    chrome = gui_design_securecrt_session_manager_chrome()
    panel = window.findChild(QWidget, "secureCrtSessionManagerChrome")
    if panel is None:
        return ["securecrt live GUI missing Session Manager filter/action chrome"]
    actual_preset = str(panel.property("designPreset") or "")
    if actual_preset != "securecrt":
        return [f"securecrt live GUI Session Manager chrome designPreset {actual_preset!r} must equal 'securecrt'"]
    expected_panel_geometry = {
        "secureCrtSessionManagerStaticTitleX": chrome.static_title_x,
        "secureCrtSessionManagerStaticTitleY": chrome.static_title_y,
        "secureCrtSessionManagerStaticFilterY": chrome.static_filter_y,
        "secureCrtSessionManagerStaticFilterXMargin": chrome.static_filter_x_margin,
        "secureCrtSessionManagerStaticFilterHeight": chrome.static_filter_height,
        "secureCrtSessionManagerStaticFilterPlaceholderX": chrome.static_filter_placeholder_x,
        "secureCrtSessionManagerStaticFilterPlaceholderY": chrome.static_filter_placeholder_y,
        "secureCrtSessionManagerLiveMaxHeight": chrome.live_max_height,
        "secureCrtSessionManagerLiveSpacing": chrome.live_spacing,
        "secureCrtSessionManagerLiveTitleSpacing": chrome.live_title_spacing,
        "secureCrtSessionManagerLiveFilterHeight": chrome.live_filter_height,
    }
    for property_name, expected_value in expected_panel_geometry.items():
        if int(panel.property(property_name) or 0) != expected_value:
            return [f"securecrt live GUI Session Manager chrome {property_name} metadata drifted"]
    if panel.maximumHeight() != chrome.live_max_height:
        return ["securecrt live GUI Session Manager chrome maximum height drifted"]

    actual_panel_keys = list(panel.property("secureCrtSessionManagerActionKeys") or [])
    if actual_panel_keys != EXPECTED_SECURECRT_SESSION_MANAGER_ACTION_KEYS:
        return [
            f"securecrt live GUI Session Manager action keys {actual_panel_keys!r} "
            f"must equal {EXPECTED_SECURECRT_SESSION_MANAGER_ACTION_KEYS!r}"
        ]

    labels = {label.text() for label in panel.findChildren(QLabel)}
    missing = sorted(required_securecrt_session_manager_texts() - labels)
    if missing:
        return [f"securecrt live GUI Session Manager chrome missing text: {missing}"]

    filter_input = panel.findChild(QLineEdit, "secureCrtSessionFilter")
    if filter_input is None:
        return ["securecrt live GUI missing Session Manager filter field"]
    if filter_input.placeholderText() != chrome.filter_placeholder:
        return ["securecrt live GUI Session Manager filter placeholder drifted"]
    if str(filter_input.property("interactionState") or "") != "focused":
        return ["securecrt live GUI Session Manager filter must expose focused interactionState"]
    if int(filter_input.property("secureCrtSessionManagerLiveFilterHeight") or 0) != chrome.live_filter_height:
        return ["securecrt live GUI Session Manager filter live height metadata drifted"]
    if filter_input.minimumHeight() != chrome.live_filter_height:
        return ["securecrt live GUI Session Manager filter minimum height drifted"]

    buttons = panel.findChildren(QToolButton, "secureCrtSessionManagerAction")
    actual_button_keys = [str(button.property("secureCrtSessionManagerActionKey") or "") for button in buttons]
    if actual_button_keys != EXPECTED_SECURECRT_SESSION_MANAGER_ACTION_KEYS:
        return [
            f"securecrt live GUI Session Manager button keys {actual_button_keys!r} "
            f"must equal {EXPECTED_SECURECRT_SESSION_MANAGER_ACTION_KEYS!r}"
        ]
    expected_labels = {action.key: action.label for action in chrome.actions}
    expected_static_x = {action.key: action.static_x for action in chrome.actions}
    expected_actions = {action.key: action for action in chrome.actions}
    for button in buttons:
        key = str(button.property("secureCrtSessionManagerActionKey") or "")
        label = str(button.property("secureCrtSessionManagerActionLabel") or "")
        icon_key = str(button.property("secureCrtSessionManagerIconKey") or "")
        static_x = int(button.property("secureCrtSessionManagerStaticX") or 0)
        expected_action = expected_actions.get(key)
        if expected_action is None:
            return [f"securecrt live GUI Session Manager action {key!r} is not expected"]
        if label != expected_labels.get(key):
            return [f"securecrt live GUI Session Manager action {key!r} label drifted"]
        if icon_key != EXPECTED_SECURECRT_SESSION_MANAGER_ICON_KEYS.get(key):
            return [f"securecrt live GUI Session Manager action {key!r} icon key drifted"]
        if static_x != expected_static_x.get(key):
            return [f"securecrt live GUI Session Manager action {key!r} static position drifted"]
        expected_button_geometry = {
            "secureCrtSessionManagerStaticY": expected_action.static_y,
            "secureCrtSessionManagerStaticButtonSize": expected_action.static_button_size,
            "secureCrtSessionManagerStaticIconX": expected_action.static_icon_x,
            "secureCrtSessionManagerStaticIconY": expected_action.static_icon_y,
            "secureCrtSessionManagerStaticIconSize": expected_action.static_icon_size,
            "secureCrtSessionManagerLiveIconSize": expected_action.live_icon_size,
            "secureCrtSessionManagerLiveButtonSize": expected_action.live_button_size,
        }
        for property_name, expected_value in expected_button_geometry.items():
            if int(button.property(property_name) or 0) != expected_value:
                return [f"securecrt live GUI Session Manager action {key!r} {property_name} metadata drifted"]
        render_source = str(button.property("secureCrtSessionManagerRenderSource") or "")
        if render_source != expected_action.render_source:
            return [f"securecrt live GUI Session Manager action {key!r} render source drifted"]
        icon_size = button.iconSize()
        if icon_size.width() != expected_action.live_icon_size or icon_size.height() != expected_action.live_icon_size:
            return [f"securecrt live GUI Session Manager action {key!r} live icon size drifted"]
        if (
            button.minimumWidth() != expected_action.live_button_size
            or button.maximumWidth() != expected_action.live_button_size
            or button.minimumHeight() != expected_action.live_button_size
            or button.maximumHeight() != expected_action.live_button_size
        ):
            return [f"securecrt live GUI Session Manager action {key!r} live button size drifted"]
        if button.icon().isNull():
            return [f"securecrt live GUI Session Manager action {key!r} must use an icon"]
    return []


def required_termius_host_identity_texts() -> set[str]:
    strip = gui_design_termius_host_identity_strip()
    return {strip.title, *{f"{field.label}: {field.value}" for field in strip.fields}}


def required_termius_hosts_chrome_texts() -> set[str]:
    chrome = gui_design_termius_hosts_chrome()
    return {chrome.title}


def check_live_moba_quick_connect_chrome(window: Any) -> list[str]:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QFrame, QLabel, QLineEdit, QTreeWidget

    chrome = gui_design_moba_quick_connect_chrome()
    suggestions = EXPECTED_MOBA_QUICK_CONNECT_SUGGESTION_CHROME
    panel = window.findChild(QFrame, "mobaQuickConnectChrome")
    if panel is None:
        return ["mobaxterm live GUI missing quick-connect chrome"]
    actual_preset = str(panel.property("designPreset") or "")
    if actual_preset != "mobaxterm":
        return [f"mobaxterm live GUI quick-connect chrome designPreset {actual_preset!r} must equal 'mobaxterm'"]
    if int(panel.property("mobaQuickConnectHeight") or 0) != chrome.static_height:
        return ["mobaxterm live GUI quick-connect chrome height metadata drifted"]
    if int(panel.property("mobaQuickConnectMarkerWidth") or 0) != chrome.marker_width:
        return ["mobaxterm live GUI quick-connect marker width metadata drifted"]
    if str(panel.property("interactionState") or "") != "focused":
        return ["mobaxterm live GUI quick-connect chrome must carry focused interaction state"]

    field = panel.findChild(QLineEdit, "quickConnect")
    if field is None:
        return ["mobaxterm live GUI quick-connect chrome missing input field"]
    if field.placeholderText() != chrome.placeholder:
        return [
            f"mobaxterm live GUI quick-connect placeholder {field.placeholderText()!r} "
            f"must equal {chrome.placeholder!r}"
        ]
    if str(field.property("mobaQuickConnectPlaceholder") or "") != chrome.placeholder:
        return ["mobaxterm live GUI quick-connect field placeholder metadata drifted"]
    if int(field.property("mobaQuickConnectInputLeft") or 0) != chrome.input_left:
        return ["mobaxterm live GUI quick-connect input-left metadata drifted"]

    dropdown = panel.findChild(QLabel, "mobaQuickConnectDropdown")
    if dropdown is None:
        return ["mobaxterm live GUI quick-connect chrome missing dropdown marker"]
    if dropdown.text() != chrome.dropdown_marker:
        return ["mobaxterm live GUI quick-connect dropdown text drifted"]
    if str(dropdown.property("mobaQuickConnectDropdownMarker") or "") != chrome.dropdown_marker:
        return ["mobaxterm live GUI quick-connect dropdown metadata drifted"]

    errors: list[str] = []
    tree = window.findChild(QTreeWidget, "quickConnectSuggestions")
    if tree is None:
        return ["mobaxterm live GUI missing quick-connect suggestion dropdown"]
    if field.text() != chrome.connected_idle_query:
        errors.append("mobaxterm live GUI connected quick-connect field must start in idle placeholder state")
    if str(panel.property("mobaQuickConnectConnectedMode") or "") != "idle":
        errors.append("mobaxterm live GUI quick-connect chrome must expose connected idle mode")
    if str(field.property("mobaQuickConnectConnectedMode") or "") != "idle":
        errors.append("mobaxterm live GUI quick-connect field must expose connected idle mode")
    if str(tree.property("mobaQuickConnectConnectedMode") or "") != "idle":
        errors.append("mobaxterm live GUI quick-connect suggestions must expose connected idle mode")
    if bool(panel.property("mobaQuickConnectConnectedSuggestionVisible")) != chrome.connected_suggestions_visible:
        errors.append("mobaxterm live GUI quick-connect chrome connected suggestion visibility drifted")
    if bool(tree.property("mobaQuickConnectConnectedSuggestionVisible")) != chrome.connected_suggestions_visible:
        errors.append("mobaxterm live GUI quick-connect connected idle suggestion visibility metadata drifted")
    if tree.isVisible() != chrome.connected_suggestions_visible:
        errors.append("mobaxterm live GUI connected quick-connect suggestions must stay hidden until typed")
    if list(tree.property("mobaQuickConnectSuggestionKinds") or []):
        errors.append("mobaxterm live GUI connected quick-connect idle state must not carry suggestion rows")

    previous_text = field.text()
    try:
        field.setText(suggestions.preview_query)
        update_suggestions = getattr(window, "update_quick_connect_suggestions", None)
        if callable(update_suggestions):
            update_suggestions()

        if not tree.isVisible():
            errors.append("mobaxterm live GUI quick-connect suggestion dropdown must become visible for a match")
        if str(tree.property("mobaQuickConnectSuggestionQuery") or "") != suggestions.preview_query:
            errors.append("mobaxterm live GUI quick-connect suggestion query metadata drifted")
        if list(tree.property("mobaQuickConnectSuggestionExpectedKinds") or []) != list(suggestions.expected_kinds):
            errors.append("mobaxterm live GUI quick-connect suggestion expected-kind metadata drifted")
        if int(tree.property("mobaQuickConnectSuggestionMaxRows") or 0) != suggestions.max_visible_rows:
            errors.append("mobaxterm live GUI quick-connect suggestion max-row metadata drifted")
        if int(tree.property("mobaQuickConnectSuggestionRowHeight") or 0) != suggestions.row_height:
            errors.append("mobaxterm live GUI quick-connect suggestion row-height metadata drifted")
        if int(tree.property("mobaQuickConnectSuggestionStaticWidth") or 0) != suggestions.static_width:
            errors.append("mobaxterm live GUI quick-connect suggestion static-width metadata drifted")

        actual_kinds = list(tree.property("mobaQuickConnectSuggestionKinds") or [])
        actual_labels = list(tree.property("mobaQuickConnectSuggestionLabels") or [])
        actual_details = list(tree.property("mobaQuickConnectSuggestionDetails") or [])
        for expected_kind in suggestions.expected_kinds:
            if expected_kind not in actual_kinds:
                errors.append(f"mobaxterm live GUI quick-connect suggestions missing {expected_kind!r} candidate")
        if not any("edge-prod" in label for label in actual_labels):
            errors.append("mobaxterm live GUI quick-connect suggestions must include saved edge-prod profile")
        if suggestions.preview_query not in " ".join(actual_details + actual_labels):
            errors.append("mobaxterm live GUI quick-connect suggestions must include the typed target")
        if not any(label.startswith("DIRECT SSH") for label in actual_labels):
            errors.append("mobaxterm live GUI quick-connect suggestions must include a direct SSH fallback")
        if tree.topLevelItemCount() < len(suggestions.expected_kinds):
            errors.append("mobaxterm live GUI quick-connect suggestions must expose multiple candidate rows")

        user_role = int(Qt.ItemDataRole.UserRole)
        for row_index in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(row_index)
            row_kind = str(item.data(0, user_role + 1) or "")
            row_label = str(item.data(0, user_role + 2) or "")
            row_detail = str(item.data(0, user_role + 3) or "")
            if row_kind and row_kind not in actual_kinds:
                errors.append(f"mobaxterm live GUI quick-connect row {row_index} kind metadata is detached")
            if row_label and row_label not in actual_labels:
                errors.append(f"mobaxterm live GUI quick-connect row {row_index} label metadata is detached")
            if row_detail and row_detail not in actual_details:
                errors.append(f"mobaxterm live GUI quick-connect row {row_index} detail metadata is detached")
            if suggestions.detail_separator not in item.text(0):
                errors.append(f"mobaxterm live GUI quick-connect row {row_index} missing detail separator")
    finally:
        field.setText(previous_text)
        update_suggestions = getattr(window, "update_quick_connect_suggestions", None)
        if callable(update_suggestions):
            update_suggestions()

    if previous_text == chrome.connected_idle_query and tree.isVisible() != chrome.connected_suggestions_visible:
        errors.append("mobaxterm live GUI quick-connect suggestions must return to connected idle visibility")

    return errors


def check_live_securecrt_session_status_strip(window: Any) -> list[str]:
    from PyQt6.QtWidgets import QLabel, QWidget

    chrome = gui_design_securecrt_session_status_strip()
    panel = window.findChild(QWidget, "secureCrtSessionStatusStrip")
    if panel is None:
        return ["securecrt live GUI missing session-status evidence strip"]
    actual_preset = str(panel.property("designPreset") or "")
    if actual_preset != "securecrt":
        return [f"securecrt live GUI session-status designPreset {actual_preset!r} must equal 'securecrt'"]
    expected_panel_props = {
        "secureCrtSessionStatusTitleWidth": chrome.title_width,
        "secureCrtSessionStatusStaticTitleX": chrome.static_title_x,
        "secureCrtSessionStatusStaticTitleY": chrome.static_title_y,
        "secureCrtSessionStatusStaticCellStartX": chrome.static_cell_start_x,
        "secureCrtSessionStatusStaticCellGap": chrome.static_cell_gap,
        "secureCrtSessionStatusLiveSpacing": chrome.live_spacing,
    }
    for prop_name, expected_value in expected_panel_props.items():
        actual_value = int(panel.property(prop_name) or 0)
        if actual_value != expected_value:
            return [
                f"securecrt live GUI session-status {prop_name} "
                f"{actual_value!r} must equal {expected_value!r}"
            ]
    actual_panel_keys = list(panel.property("secureCrtSessionStatusFieldKeys") or [])
    expected_keys = [field.key for field in chrome.fields]
    if actual_panel_keys != expected_keys:
        return [f"securecrt live GUI session-status field keys {actual_panel_keys!r} must equal {expected_keys!r}"]
    title = panel.findChild(QLabel, "secureCrtSessionStatusTitle")
    if title is None:
        return ["securecrt live GUI session-status missing title label"]
    if title.minimumWidth() != chrome.title_width or title.maximumWidth() != chrome.title_width:
        return ["securecrt live GUI session-status title width drifted"]
    labels = {label.text() for label in panel.findChildren(QLabel)}
    missing = sorted(required_securecrt_session_status_texts() - labels)
    if missing:
        return [f"securecrt live GUI session-status missing text: {missing}"]
    status_cells = panel.findChildren(QLabel, "secureCrtSessionStatusCell")
    actual_keys = [str(label.property("secureCrtSessionStatusKey") or "") for label in status_cells]
    if actual_keys != expected_keys:
        return [f"securecrt live GUI session-status label keys {actual_keys!r} must equal {expected_keys!r}"]
    actual_widths = [int(label.property("secureCrtSessionStatusWidth") or 0) for label in status_cells]
    expected_widths = [field.static_width for field in chrome.fields]
    if actual_widths != expected_widths:
        return [f"securecrt live GUI session-status widths {actual_widths!r} must equal {expected_widths!r}"]
    for cell, field in zip(status_cells, chrome.fields, strict=False):
        expected_props = {
            "secureCrtSessionStatusStaticY": field.static_y,
            "secureCrtSessionStatusStaticHeight": field.static_height,
            "secureCrtSessionStatusStaticLabelX": field.static_label_x,
            "secureCrtSessionStatusStaticLabelY": field.static_label_y,
            "secureCrtSessionStatusStaticValueX": field.static_value_x,
            "secureCrtSessionStatusStaticValueY": field.static_value_y,
            "secureCrtSessionStatusLiveMinWidth": field.live_min_width,
            "secureCrtSessionStatusLiveCellHeight": field.live_cell_height,
        }
        actual_role = str(cell.property("secureCrtSessionStatusRole") or "")
        if actual_role != field.role:
            return [
                f"securecrt live GUI session-status field {field.key!r} role "
                f"{actual_role!r} must equal {field.role!r}"
            ]
        for prop_name, expected_value in expected_props.items():
            actual_value = int(cell.property(prop_name) or 0)
            if actual_value != expected_value:
                return [
                    f"securecrt live GUI session-status field {field.key!r} {prop_name} "
                    f"{actual_value!r} must equal {expected_value!r}"
                ]
        if cell.minimumWidth() != field.live_min_width:
            return [f"securecrt live GUI session-status field {field.key!r} minimum width drifted"]
        if cell.minimumHeight() != field.live_cell_height:
            return [f"securecrt live GUI session-status field {field.key!r} height drifted"]
    return []


def check_live_securecrt_session_manager_route(window: Any) -> list[str]:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QLabel, QTabWidget, QToolButton, QTreeWidget, QWidget

    route = EXPECTED_SECURECRT_SESSION_MANAGER_ROUTE
    tree = window.findChild(QTreeWidget, route.selected_tree_object)
    manager_panel = window.findChild(QWidget, route.session_manager_object)
    status_panel = window.findChild(QWidget, route.status_strip_object)
    tabs = window.findChild(QTabWidget, "sessionTabs")
    errors: list[str] = []
    if tree is None:
        errors.append("securecrt live GUI session-manager route missing profile tree")
    if manager_panel is None:
        errors.append("securecrt live GUI session-manager route missing Session Manager panel")
    if status_panel is None:
        errors.append("securecrt live GUI session-manager route missing status strip")
    if tabs is None:
        errors.append("securecrt live GUI session-manager route missing session tabs")
    if errors:
        return errors

    common_route_props = {
        "secureCrtSessionRouteKey": route.key,
        "secureCrtSessionRouteRole": route.route_role,
        "secureCrtSessionRouteSelectedProfile": route.selected_profile_name,
        "secureCrtSessionRouteSelectedTreeLabel": route.selected_tree_label,
        "secureCrtSessionRouteSessionManagerObject": route.session_manager_object,
        "secureCrtSessionRouteActionKey": route.session_manager_action_key,
        "secureCrtSessionRouteActionObject": route.session_manager_action_object,
        "secureCrtSessionRouteStatusStripObject": route.status_strip_object,
        "secureCrtSessionRouteStatusFieldKey": route.status_field_key,
        "secureCrtSessionRouteStatusFieldObject": route.status_field_object,
        route.tab_label_property: route.active_tab_label,
        "secureCrtSessionRouteTarget": route.target_value,
        "secureCrtSessionRouteProtocol": route.protocol_value,
        "secureCrtSessionRouteSession": route.session_value,
        route.status_value_property: route.target_value,
        "secureCrtSessionRouteRenderSource": route.render_source,
    }
    for label, widget in (
        ("profile-tree", tree),
        ("session-manager", manager_panel),
        ("status-strip", status_panel),
    ):
        for property_name, expected_value in common_route_props.items():
            actual_value = str(widget.property(property_name) or "")
            if actual_value != expected_value:
                errors.append(
                    f"securecrt live GUI session-manager route {label} property "
                    f"{property_name} {actual_value!r} must equal {expected_value!r}"
                )

    tab_route_props = {
        "secureCrtSessionRouteKey": route.key,
        "secureCrtSessionRouteRole": route.route_role,
        "secureCrtSessionRouteSelectedProfile": route.selected_profile_name,
        "secureCrtSessionRouteSelectedTreeLabel": route.selected_tree_label,
        route.tab_label_property: route.active_tab_label,
        "secureCrtSessionRouteTarget": route.target_value,
        "secureCrtSessionRouteProtocol": route.protocol_value,
        "secureCrtSessionRouteSession": route.session_value,
        "secureCrtSessionRouteRenderSource": route.render_source,
    }
    for property_name, expected_value in tab_route_props.items():
        actual_value = str(tabs.property(property_name) or "")
        if actual_value != expected_value:
            errors.append(
                f"securecrt live GUI session-manager route tabs property "
                f"{property_name} {actual_value!r} must equal {expected_value!r}"
            )
    if route.active_tab_label not in live_tab_labels(tabs):
        errors.append(f"securecrt live GUI session-manager route missing active tab {route.active_tab_label!r}")

    selected = tree.currentItem()
    if selected is None:
        errors.append("securecrt live GUI session-manager route missing selected tree item")
    else:
        base_role = int(Qt.ItemDataRole.UserRole)
        expected_item_data = {
            base_role: route.selected_profile_name,
            base_role + 71: route.key,
            base_role + 72: route.route_role,
            base_role + 73: route.selected_profile_name,
            base_role + 74: route.active_tab_label,
            base_role + 75: route.target_value,
            base_role + 76: route.protocol_value,
        }
        if route.selected_tree_label not in selected.text(0):
            errors.append("securecrt live GUI session-manager route selected tree label drifted")
        for role, expected_value in expected_item_data.items():
            actual_value = str(selected.data(0, role) or "")
            if actual_value != expected_value:
                errors.append(f"securecrt live GUI session-manager route tree role {role} drifted")
        if selected.data(0, base_role + 77) is not True:
            errors.append("securecrt live GUI session-manager route tree item is not marked selected")

    buttons = manager_panel.findChildren(QToolButton, route.session_manager_action_object)
    target_buttons = [
        button
        for button in buttons
        if str(button.property("secureCrtSessionManagerActionKey") or "") == route.session_manager_action_key
    ]
    if len(target_buttons) != 1:
        errors.append("securecrt live GUI session-manager route must expose one target Session Manager action")
    else:
        target_button = target_buttons[0]
        expected_button_props = {
            "secureCrtSessionRouteKey": route.key,
            "secureCrtSessionRouteRole": route.route_role,
            "secureCrtSessionRouteSelectedProfile": route.selected_profile_name,
            "secureCrtSessionRouteSelectedTreeLabel": route.selected_tree_label,
            route.tab_label_property: route.active_tab_label,
            "secureCrtSessionRouteTarget": route.target_value,
            "secureCrtSessionRouteProtocol": route.protocol_value,
            "secureCrtSessionRouteSession": route.session_value,
            route.status_value_property: route.target_value,
            "secureCrtSessionRouteRenderSource": route.render_source,
            route.action_active_property: "true",
        }
        for property_name, expected_value in expected_button_props.items():
            actual_value = str(target_button.property(property_name) or "")
            if actual_value != expected_value:
                errors.append(f"securecrt live GUI session-manager route action property {property_name} drifted")
        if target_button.text() and target_button.text() != "Connect":
            errors.append("securecrt live GUI session-manager route target action text drifted")
    for button in buttons:
        if str(button.property("secureCrtSessionManagerActionKey") or "") == route.session_manager_action_key:
            continue
        if str(button.property(route.action_active_property) or "") != "false":
            errors.append("securecrt live GUI session-manager route non-target action must not be active")

    status_cells = status_panel.findChildren(QLabel, route.status_field_object)
    target_cells = [
        cell for cell in status_cells if str(cell.property("secureCrtSessionStatusKey") or "") == route.status_field_key
    ]
    if len(target_cells) != 1:
        errors.append("securecrt live GUI session-manager route must expose one target status cell")
    else:
        target_cell = target_cells[0]
        expected_status_props = {
            "secureCrtSessionRouteKey": route.key,
            "secureCrtSessionRouteRole": route.route_role,
            "secureCrtSessionRouteSelectedProfile": route.selected_profile_name,
            route.tab_label_property: route.active_tab_label,
            "secureCrtSessionRouteTarget": route.target_value,
            "secureCrtSessionRouteProtocol": route.protocol_value,
            "secureCrtSessionRouteSession": route.session_value,
            route.status_value_property: route.target_value,
            "secureCrtSessionRouteRenderSource": route.render_source,
            "secureCrtSessionStatusValue": route.target_value,
        }
        for property_name, expected_value in expected_status_props.items():
            actual_value = str(target_cell.property(property_name) or "")
            if actual_value != expected_value:
                errors.append(f"securecrt live GUI session-manager route status property {property_name} drifted")
        if route.target_value not in target_cell.text():
            errors.append("securecrt live GUI session-manager route target status text drifted")
    return errors


def check_live_securecrt_command_window(window: Any) -> list[str]:
    from PyQt6.QtWidgets import QLabel, QWidget

    chrome = gui_design_securecrt_command_window_chrome()
    panel = window.findChild(QWidget, "secureCrtCommandWindow")
    if panel is None:
        return ["securecrt live GUI missing command-window evidence strip"]
    actual_key = str(panel.property("secureCrtCommandWindowKey") or "")
    if actual_key != chrome.key:
        return [f"securecrt live GUI command-window key {actual_key!r} must equal {chrome.key!r}"]
    expected_panel_props = {
        "secureCrtCommandStaticHeaderHeight": chrome.static_header_height,
        "secureCrtCommandStaticTitleX": chrome.static_title_x,
        "secureCrtCommandStaticTitleY": chrome.static_title_y,
        "secureCrtCommandStaticHelperX": chrome.static_helper_x,
        "secureCrtCommandStaticHelperY": chrome.static_helper_y,
        "secureCrtCommandStaticControlY": chrome.static_control_y,
        "secureCrtCommandStaticTargetWidth": chrome.static_target_width,
        "secureCrtCommandStaticInputX": chrome.static_input_x,
        "secureCrtCommandStaticSendWidth": chrome.static_send_width,
        "secureCrtCommandLiveTargetMinWidth": chrome.live_target_min_width,
        "secureCrtCommandLiveSendMinWidth": chrome.live_send_min_width,
    }
    for prop_name, expected_value in expected_panel_props.items():
        actual_value = int(panel.property(prop_name) or 0)
        if actual_value != expected_value:
            return [
                f"securecrt live GUI command-window {prop_name} "
                f"{actual_value!r} must equal {expected_value!r}"
            ]
    labels = {label.text() for label in panel.findChildren(QLabel)}
    missing = sorted(required_securecrt_command_window_texts() - labels)
    if missing:
        return [f"securecrt live GUI command-window missing text: {missing}"]
    keyed_labels = panel.findChildren(QLabel, "secureCrtCommandTarget")
    keyed_labels.extend(panel.findChildren(QLabel, "secureCrtCommandSend"))
    keyed_labels.extend(panel.findChildren(QLabel, "secureCrtCommandStatus"))
    for label in keyed_labels:
        label_key = str(label.property("secureCrtCommandWindowKey") or "")
        if label_key != chrome.key:
            return [f"securecrt live GUI command-window label key {label_key!r} must equal {chrome.key!r}"]
    target = panel.findChild(QLabel, "secureCrtCommandTarget")
    if target is None:
        return ["securecrt live GUI command-window missing target label"]
    target_static_width = int(target.property("secureCrtCommandStaticTargetWidth") or 0)
    target_live_width = int(target.property("secureCrtCommandLiveTargetMinWidth") or 0)
    if target_static_width != chrome.static_target_width:
        return ["securecrt live GUI command-window target static width drifted"]
    if target_live_width != chrome.live_target_min_width or target.minimumWidth() != chrome.live_target_min_width:
        return ["securecrt live GUI command-window target live width drifted"]
    command_input = panel.findChild(QLabel, "secureCrtCommandInput")
    if command_input is None:
        return ["securecrt live GUI command-window missing command input"]
    expected_input_props = {
        "secureCrtCommandStaticInputX": chrome.static_input_x,
        "secureCrtCommandStaticInputTextX": chrome.static_input_text_x,
        "secureCrtCommandStaticInputTextY": chrome.static_input_text_y,
    }
    for prop_name, expected_value in expected_input_props.items():
        actual_value = int(command_input.property(prop_name) or 0)
        if actual_value != expected_value:
            return [
                f"securecrt live GUI command-window input {prop_name} "
                f"{actual_value!r} must equal {expected_value!r}"
            ]
    send = panel.findChild(QLabel, "secureCrtCommandSend")
    if send is None:
        return ["securecrt live GUI command-window missing send label"]
    send_static_width = int(send.property("secureCrtCommandStaticSendWidth") or 0)
    send_live_width = int(send.property("secureCrtCommandLiveSendMinWidth") or 0)
    if send_static_width != chrome.static_send_width:
        return ["securecrt live GUI command-window send static width drifted"]
    if send_live_width != chrome.live_send_min_width or send.minimumWidth() != chrome.live_send_min_width:
        return ["securecrt live GUI command-window send live width drifted"]
    status = panel.findChild(QLabel, "secureCrtCommandStatus")
    if status is None:
        return ["securecrt live GUI command-window missing status label"]
    route_errors = check_securecrt_command_window_send_route(panel, target, command_input, send, status)
    if route_errors:
        return route_errors
    return []


def check_securecrt_command_window_send_route(panel: Any, target: Any, command_input: Any, send: Any, status: Any) -> list[str]:
    route = EXPECTED_SECURECRT_COMMAND_WINDOW_SEND_ROUTE
    chrome = EXPECTED_SECURECRT_COMMAND_WINDOW_CHROME
    expected_texts = {
        route.target_scope_object: chrome.target_scope,
        route.command_input_object: chrome.command,
        route.send_control_object: chrome.send_label,
        route.status_object: chrome.status,
    }
    if panel.objectName() != route.source_window_object:
        return [
            f"securecrt live GUI command-window send route source "
            f"{panel.objectName()!r} must equal {route.source_window_object!r}"
        ]
    route_widgets = {
        route.source_window_object: panel,
        route.target_scope_object: target,
        route.command_input_object: command_input,
        route.send_control_object: send,
        route.status_object: status,
    }
    for object_name, widget in route_widgets.items():
        if widget.objectName() != object_name:
            return [
                f"securecrt live GUI command-window send route widget "
                f"{widget.objectName()!r} must equal {object_name!r}"
            ]
        expected_route_props = {
            "secureCrtCommandRouteKey": route.key,
            "secureCrtCommandRouteRole": route.route_role,
            "secureCrtCommandRouteSourceWindowObject": route.source_window_object,
            "secureCrtCommandRouteTargetScopeObject": route.target_scope_object,
            "secureCrtCommandRouteCommandInputObject": route.command_input_object,
            "secureCrtCommandRouteSendControlObject": route.send_control_object,
            "secureCrtCommandRouteStatusObject": route.status_object,
            "secureCrtCommandRouteCommand": chrome.command,
            "secureCrtCommandRouteTargetScope": chrome.target_scope,
            "secureCrtCommandRouteSendLabel": chrome.send_label,
            "secureCrtCommandRouteStatus": chrome.status,
            "secureCrtCommandRouteRenderSource": route.render_source,
        }
        for prop_name, expected_value in expected_route_props.items():
            actual_value = str(widget.property(prop_name) or "")
            if actual_value != expected_value:
                return [
                    f"securecrt live GUI command-window send route {object_name}.{prop_name} "
                    f"{actual_value!r} must equal {expected_value!r}"
                ]
    for object_name, expected_text in expected_texts.items():
        actual_text = route_widgets[object_name].text()
        if actual_text != expected_text:
            return [
                f"securecrt live GUI command-window send route {object_name} text "
                f"{actual_text!r} must equal {expected_text!r}"
            ]
    return []


def check_live_remmina_viewer_controls(window: Any) -> list[str]:
    from PyQt6.QtWidgets import QToolButton, QWidget

    panel = window.findChild(QWidget, "remminaViewerControls")
    if panel is None:
        return ["remmina live GUI missing viewer-controls evidence strip"]
    actual_preset = str(panel.property("designPreset") or "")
    if actual_preset != "remmina":
        return [f"remmina live GUI viewer-controls designPreset {actual_preset!r} must equal 'remmina'"]
    buttons = panel.findChildren(QToolButton, "remminaViewerControl")
    expected = list(gui_design_remmina_viewer_controls())
    actual_keys = [str(button.property("remminaViewerControlKey") or "") for button in buttons]
    expected_keys = [control.key for control in expected]
    if actual_keys != expected_keys:
        return [f"remmina live GUI viewer-control keys {actual_keys!r} must equal {expected_keys!r}"]
    actual_labels = [button.text() for button in buttons]
    expected_labels = [control.label for control in expected]
    if actual_labels != expected_labels:
        return [f"remmina live GUI viewer-control labels {actual_labels!r} must equal {expected_labels!r}"]
    for button, control in zip(buttons, expected, strict=False):
        icon_key = str(button.property("remminaViewerIconKey") or "")
        if icon_key != control.icon_key:
            return [f"remmina live GUI viewer-control icon key {icon_key!r} must equal {control.icon_key!r}"]
        expected_properties = {
            "remminaViewerControlStaticWidth": control.static_width,
            "remminaViewerControlStaticStep": control.static_step,
            "remminaViewerControlStaticY": control.static_y,
            "remminaViewerControlStaticHeight": control.static_height,
            "remminaViewerControlStaticIconX": control.static_icon_x,
            "remminaViewerControlStaticIconSize": control.static_icon_size,
            "remminaViewerControlStaticLabelX": control.static_label_x,
            "remminaViewerControlLiveIconSize": control.live_icon_size,
            "remminaViewerControlLiveMinWidth": control.live_min_width,
            "remminaViewerControlLiveButtonHeight": control.live_button_height,
        }
        for property_name, expected_value in expected_properties.items():
            if int(button.property(property_name) or -1) != expected_value:
                return [f"remmina live GUI viewer-control {control.key!r} {property_name} drifted"]
        render_source = str(button.property("remminaViewerControlRenderSource") or "")
        if render_source != control.render_source:
            return [
                f"remmina live GUI viewer-control {control.key!r} render source "
                f"{render_source!r} must equal {control.render_source!r}"
            ]
        if button.iconSize().width() != control.live_icon_size or button.iconSize().height() != control.live_icon_size:
            return [f"remmina live GUI viewer-control {control.key!r} icon size drifted"]
        if button.minimumWidth() != control.live_min_width or button.minimumHeight() != control.live_button_height:
            return [f"remmina live GUI viewer-control {control.key!r} live geometry drifted"]
        if button.icon().isNull():
            return [f"remmina live GUI viewer-control {control.key!r} must use an icon"]
    return []


def check_live_remmina_profile_list_chrome(window: Any) -> list[str]:
    from PyQt6.QtWidgets import QFrame, QLabel, QLineEdit, QWidget

    chrome = gui_design_remmina_profile_list_chrome()
    panel = window.findChild(QWidget, "remminaProfileListChrome")
    if panel is None:
        return ["remmina live GUI missing profile-list chrome"]
    actual_preset = str(panel.property("designPreset") or "")
    if actual_preset != "remmina":
        return [f"remmina live GUI profile-list designPreset {actual_preset!r} must equal 'remmina'"]
    expected_panel_props = {
        "remminaProfileStaticFilterX": chrome.static_filter_x,
        "remminaProfileStaticFilterY": chrome.static_filter_y,
        "remminaProfileStaticFilterHeight": chrome.static_filter_height,
        "remminaProfileStaticHeaderY": chrome.static_header_y,
        "remminaProfileStaticRowStartY": chrome.static_row_start_y,
        "remminaProfileStaticRowHeight": chrome.static_row_height,
        "remminaProfileStaticRowStep": chrome.static_row_step,
        "remminaProfileStaticCellStartX": chrome.static_cell_start_x,
        "remminaProfileStaticCellY": chrome.static_cell_y,
        "remminaProfileStaticStatusY": chrome.static_status_y,
        "remminaProfileLiveMaxHeight": chrome.live_max_height,
        "remminaProfileLiveSpacing": chrome.live_spacing,
        "remminaProfileLiveRowMinHeight": chrome.live_row_min_height,
    }
    for prop_name, expected_value in expected_panel_props.items():
        actual_value = int(panel.property(prop_name) or 0)
        if actual_value != expected_value:
            return [
                f"remmina live GUI profile-list {prop_name} "
                f"{actual_value!r} must equal {expected_value!r}"
            ]
    if panel.maximumHeight() != chrome.live_max_height:
        return ["remmina live GUI profile-list maximum height drifted"]
    filter_input = panel.findChild(QLineEdit, "remminaProfileFilter")
    if filter_input is None or filter_input.placeholderText() != chrome.filter_placeholder:
        actual_placeholder = None if filter_input is None else filter_input.placeholderText()
        return [
            f"remmina live GUI profile filter placeholder {actual_placeholder!r} "
            f"must equal {chrome.filter_placeholder!r}"
        ]
    filter_width = int(filter_input.property("remminaProfileFilterWidth") or 0)
    if filter_width != chrome.live_filter_width or filter_input.minimumWidth() != chrome.live_filter_width:
        return ["remmina live GUI profile filter width drifted"]
    if not filter_input.isReadOnly():
        return ["remmina live GUI profile filter must remain read-only evidence"]
    if str(filter_input.property("interactionState") or "") != "focused":
        return ["remmina live GUI profile filter must expose focused interactionState"]
    actual_column_keys = list(panel.property("remminaProfileColumnKeys") or [])
    expected_column_keys = [column.key for column in chrome.columns]
    if actual_column_keys != expected_column_keys:
        return [f"remmina live GUI profile column keys {actual_column_keys!r} must equal {expected_column_keys!r}"]
    actual_row_keys = list(panel.property("remminaProfileRowKeys") or [])
    expected_row_keys = [row.key for row in chrome.rows]
    if actual_row_keys != expected_row_keys:
        return [f"remmina live GUI profile row keys {actual_row_keys!r} must equal {expected_row_keys!r}"]
    title = panel.findChild(QLabel, "remminaProfileListTitle")
    if title is None or title.text() != chrome.title:
        actual_title = None if title is None else title.text()
        return [f"remmina live GUI profile-list title {actual_title!r} must equal {chrome.title!r}"]
    columns = panel.findChildren(QLabel, "remminaProfileListColumn")
    actual_header_keys = [str(label.property("remminaProfileColumnKey") or "") for label in columns]
    if actual_header_keys != expected_column_keys:
        return [f"remmina live GUI profile header keys {actual_header_keys!r} must equal {expected_column_keys!r}"]
    expected_column_widths = [column.static_width for column in chrome.columns]
    actual_column_widths = [int(label.property("remminaProfileColumnWidth") or 0) for label in columns]
    if actual_column_widths != expected_column_widths:
        return [
            f"remmina live GUI profile header widths {actual_column_widths!r} "
            f"must equal {expected_column_widths!r}"
        ]
    expected_live_widths = [column.live_min_width for column in chrome.columns]
    actual_live_widths = [int(label.property("remminaProfileColumnLiveMinWidth") or 0) for label in columns]
    if actual_live_widths != expected_live_widths:
        return [
            f"remmina live GUI profile header live widths {actual_live_widths!r} "
            f"must equal {expected_live_widths!r}"
        ]
    actual_header_min_widths = [label.minimumWidth() for label in columns]
    if actual_header_min_widths != expected_live_widths:
        return ["remmina live GUI profile header minimum widths drifted"]
    rows = panel.findChildren(QFrame, "remminaProfileListRow")
    live_rows = {str(row.property("remminaProfileRowKey") or ""): row for row in rows}
    missing_rows = sorted(set(expected_row_keys) - set(live_rows))
    if missing_rows:
        return [f"remmina live GUI profile-list missing rows: {missing_rows}"]
    for row in chrome.rows:
        live_row = live_rows[row.key]
        selected = str(live_row.property("selectedRow") or "")
        expected_selected = "true" if row.selected else "false"
        if selected != expected_selected:
            return [f"remmina live GUI profile row {row.key!r} selected state drifted"]
        expected_row_props = {
            "remminaProfileStaticRowHeight": chrome.static_row_height,
            "remminaProfileStaticRowStep": chrome.static_row_step,
            "remminaProfileLiveRowMinHeight": chrome.live_row_min_height,
        }
        for prop_name, expected_value in expected_row_props.items():
            actual_value = int(live_row.property(prop_name) or 0)
            if actual_value != expected_value:
                return [
                    f"remmina live GUI profile row {row.key!r} {prop_name} "
                    f"{actual_value!r} must equal {expected_value!r}"
                ]
        if live_row.minimumHeight() != chrome.live_row_min_height:
            return [f"remmina live GUI profile row {row.key!r} minimum height drifted"]
        cell_values = {
            str(cell.property("remminaProfileColumnKey") or ""): str(cell.property("remminaProfileCellValue") or "")
            for cell in live_row.findChildren(QLabel, "remminaProfileListCell")
        }
        expected_values = {
            "name": row.name,
            "protocol": row.protocol,
            "server": row.server,
            "status": row.status,
        }
        for key, expected_value in expected_values.items():
            if cell_values.get(key) != expected_value:
                return [
                    f"remmina live GUI profile row {row.key!r} {key} "
                    f"{cell_values.get(key)!r} must equal {expected_value!r}"
                ]
        cells = live_row.findChildren(QLabel, "remminaProfileListCell")
        for column in chrome.columns:
            matching = [
                cell for cell in cells if str(cell.property("remminaProfileColumnKey") or "") == column.key
            ]
            if not matching:
                return [f"remmina live GUI profile row {row.key!r} missing {column.key!r} cell"]
            cell = matching[0]
            column_width = int(cell.property("remminaProfileColumnWidth") or 0)
            live_width = int(cell.property("remminaProfileColumnLiveMinWidth") or 0)
            if column_width != column.static_width:
                return [f"remmina live GUI profile row {row.key!r} {column.key!r} static width drifted"]
            if live_width != column.live_min_width or cell.minimumWidth() != column.live_min_width:
                return [f"remmina live GUI profile row {row.key!r} {column.key!r} live width drifted"]
        status_cells = [
            cell for cell in cells if str(cell.property("remminaProfileColumnKey") or "") == "status"
        ]
        if not status_cells:
            return [f"remmina live GUI profile row {row.key!r} missing status cell"]
        status_y = int(status_cells[0].property("remminaProfileStaticStatusY") or 0)
        if status_y != chrome.static_status_y:
            return [f"remmina live GUI profile row {row.key!r} status y drifted"]
    return []


def check_live_remmina_profile_viewer_route(window: Any) -> list[str]:
    from PyQt6.QtWidgets import QFrame, QLabel, QTabWidget, QToolButton, QWidget

    route = EXPECTED_REMMINA_PROFILE_VIEWER_ROUTE
    profile_panel = window.findChild(QWidget, "remminaProfileListChrome")
    viewer_panel = window.findChild(QWidget, route.viewer_controls_object)
    tabs = window.findChild(QTabWidget, "sessionTabs")
    errors: list[str] = []
    if profile_panel is None:
        errors.append("remmina live GUI profile-viewer route missing profile-list panel")
    if viewer_panel is None:
        errors.append("remmina live GUI profile-viewer route missing viewer controls panel")
    if tabs is None:
        errors.append("remmina live GUI profile-viewer route missing session tabs")
    if errors:
        return errors

    common_route_props = {
        "remminaProfileViewerRouteKey": route.key,
        "remminaProfileViewerRouteRole": route.route_role,
        "remminaProfileViewerSelectedProfileKey": route.selected_profile_key,
        "remminaProfileViewerSelectedProfileObject": route.selected_profile_object,
        "remminaProfileViewerControlsObject": route.viewer_controls_object,
        "remminaProfileViewerControlKey": route.viewer_control_key,
        "remminaProfileViewerControlObject": route.viewer_control_object,
        route.tab_label_property: route.active_tab_label,
        "remminaProfileViewerProtocol": route.protocol,
        "remminaProfileViewerStatus": route.profile_status,
        "remminaProfileViewerRenderSource": route.render_source,
    }
    for label, widget in (("profile-list", profile_panel), ("viewer-controls", viewer_panel)):
        for property_name, expected_value in common_route_props.items():
            actual_value = str(widget.property(property_name) or "")
            if actual_value != expected_value:
                errors.append(
                    f"remmina live GUI profile-viewer route {label} property "
                    f"{property_name} {actual_value!r} must equal {expected_value!r}"
                )

    if route.active_tab_label not in live_tab_labels(tabs):
        errors.append(f"remmina live GUI profile-viewer route missing active tab {route.active_tab_label!r}")

    rows = profile_panel.findChildren(QFrame, route.selected_profile_object)
    selected_rows = [row for row in rows if str(row.property("remminaProfileRowKey") or "") == route.selected_profile_key]
    if len(selected_rows) != 1:
        errors.append("remmina live GUI profile-viewer route must expose one selected profile row")
    else:
        selected_row = selected_rows[0]
        selected = str(selected_row.property(route.selected_row_property) or "")
        if selected != "true":
            errors.append("remmina live GUI profile-viewer route selected profile row is not selected")
        row_route_props = {
            "remminaProfileViewerRouteKey": route.key,
            "remminaProfileViewerRouteRole": route.route_role,
            "remminaProfileViewerControlKey": route.viewer_control_key,
            route.tab_label_property: route.active_tab_label,
            "remminaProfileViewerProtocol": route.protocol,
            "remminaProfileViewerStatus": route.profile_status,
        }
        for property_name, expected_value in row_route_props.items():
            actual_value = str(selected_row.property(property_name) or "")
            if actual_value != expected_value:
                errors.append(f"remmina live GUI selected profile route property {property_name} drifted")
        status_cells = [
            cell
            for cell in selected_row.findChildren(QLabel, "remminaProfileListCell")
            if str(cell.property("remminaProfileColumnKey") or "") == "status"
        ]
        if not status_cells:
            errors.append("remmina live GUI profile-viewer route selected row missing status cell")
        elif str(status_cells[0].property("remminaProfileCellValue") or "") != route.profile_status:
            errors.append("remmina live GUI profile-viewer route selected row status drifted")

    buttons = viewer_panel.findChildren(QToolButton, route.viewer_control_object)
    target_buttons = [
        button for button in buttons if str(button.property("remminaViewerControlKey") or "") == route.viewer_control_key
    ]
    if len(target_buttons) != 1:
        errors.append("remmina live GUI profile-viewer route must expose one target viewer control")
    else:
        button = target_buttons[0]
        expected_control_props = {
            "remminaProfileViewerRouteKey": route.key,
            "remminaProfileViewerRouteRole": route.route_role,
            "remminaProfileViewerSelectedProfileKey": route.selected_profile_key,
            route.tab_label_property: route.active_tab_label,
            "remminaProfileViewerStatus": route.profile_status,
            route.control_active_property: "true",
        }
        for property_name, expected_value in expected_control_props.items():
            actual_value = str(button.property(property_name) or "")
            if actual_value != expected_value:
                errors.append(f"remmina live GUI routed viewer control property {property_name} drifted")
        if button.text() != "Scale 100%":
            errors.append("remmina live GUI routed viewer control label must be Scale 100%")

    inactive_route_states = [
        str(button.property(route.control_active_property) or "")
        for button in buttons
        if str(button.property("remminaViewerControlKey") or "") != route.viewer_control_key
    ]
    if any(state != "false" for state in inactive_route_states):
        errors.append("remmina live GUI non-routed viewer controls must not expose active route state")
    return errors


def check_live_remmina_clipboard_route(window: Any) -> list[str]:
    from PyQt6.QtWidgets import QTabWidget, QToolButton, QWidget

    route = EXPECTED_REMMINA_CLIPBOARD_ROUTE
    viewer_panel = window.findChild(QWidget, route.viewer_controls_object)
    tabs = window.findChild(QTabWidget, "sessionTabs")
    errors: list[str] = []
    if viewer_panel is None:
        errors.append("remmina live GUI clipboard route missing viewer controls panel")
    if tabs is None:
        errors.append("remmina live GUI clipboard route missing session tabs")
    if errors:
        return errors

    common_route_props = {
        "remminaClipboardRouteKey": route.key,
        "remminaClipboardRouteRole": route.route_role,
        "remminaClipboardViewerControlsObject": route.viewer_controls_object,
        "remminaClipboardViewerControlKey": route.viewer_control_key,
        "remminaClipboardViewerControlObject": route.viewer_control_object,
        route.tab_label_property: route.active_tab_label,
        "remminaClipboardRouteProtocol": route.protocol,
        route.clipboard_state_property: route.clipboard_state,
        "remminaClipboardRouteStatusSegment": route.status_segment,
        "remminaClipboardRouteDetailLine": route.detail_line,
        "remminaClipboardRouteActivityLine": route.activity_line,
        "remminaClipboardRouteRenderSource": route.render_source,
    }
    for property_name, expected_value in common_route_props.items():
        actual_value = str(viewer_panel.property(property_name) or "")
        if actual_value != expected_value:
            errors.append(
                f"remmina live GUI clipboard route panel property "
                f"{property_name} {actual_value!r} must equal {expected_value!r}"
            )

    if route.active_tab_label not in live_tab_labels(tabs):
        errors.append(f"remmina live GUI clipboard route missing active tab {route.active_tab_label!r}")

    buttons = viewer_panel.findChildren(QToolButton, route.viewer_control_object)
    target_buttons = [
        button for button in buttons if str(button.property("remminaViewerControlKey") or "") == route.viewer_control_key
    ]
    if len(target_buttons) != 1:
        errors.append("remmina live GUI clipboard route must expose one Clipboard viewer control")
    else:
        button = target_buttons[0]
        button_route_props = dict(common_route_props)
        button_route_props.pop("remminaClipboardViewerControlsObject")
        button_route_props.pop("remminaClipboardViewerControlKey")
        button_route_props.pop("remminaClipboardViewerControlObject")
        button_route_props[route.control_active_property] = "true"
        for property_name, expected_value in button_route_props.items():
            actual_value = str(button.property(property_name) or "")
            if actual_value != expected_value:
                errors.append(f"remmina live GUI clipboard routed control property {property_name} drifted")
        if button.text() != "Clipboard":
            errors.append("remmina live GUI clipboard routed control label must be Clipboard")

    inactive_route_states = [
        str(button.property(route.control_active_property) or "")
        for button in buttons
        if str(button.property("remminaViewerControlKey") or "") != route.viewer_control_key
    ]
    if any(state != "false" for state in inactive_route_states):
        errors.append("remmina live GUI non-clipboard viewer controls must not expose active clipboard route")
    return errors


def check_live_termius_header_chips(window: Any) -> list[str]:
    from PyQt6.QtWidgets import QLabel, QWidget

    panel = window.findChild(QWidget, "termiusHeaderChips")
    if panel is None:
        return ["termius live GUI missing header-chip evidence strip"]
    actual_preset = str(panel.property("designPreset") or "")
    if actual_preset != "termius":
        return [f"termius live GUI header-chip designPreset {actual_preset!r} must equal 'termius'"]
    labels = panel.findChildren(QLabel, "termiusHeaderChip")
    expected = list(gui_design_termius_header_chips())
    actual_keys = [str(label.property("termiusHeaderChipKey") or "") for label in labels]
    expected_keys = [chip.key for chip in expected]
    if actual_keys != expected_keys:
        return [f"termius live GUI header-chip keys {actual_keys!r} must equal {expected_keys!r}"]
    actual_labels = [label.text() for label in labels]
    expected_labels = [chip.label for chip in expected]
    if actual_labels != expected_labels:
        return [f"termius live GUI header-chip labels {actual_labels!r} must equal {expected_labels!r}"]
    return []


def check_live_termius_hosts_chrome(window: Any) -> list[str]:
    from PyQt6.QtWidgets import QLabel, QLineEdit, QToolButton, QWidget

    chrome = gui_design_termius_hosts_chrome()
    panel = window.findChild(QWidget, "termiusHostsChrome")
    if panel is None:
        return ["termius live GUI missing Hosts search/action chrome"]
    actual_preset = str(panel.property("designPreset") or "")
    if actual_preset != "termius":
        return [f"termius live GUI Hosts chrome designPreset {actual_preset!r} must equal 'termius'"]

    actual_panel_keys = list(panel.property("termiusHostsActionKeys") or [])
    if actual_panel_keys != EXPECTED_TERMIUS_HOSTS_ACTION_KEYS:
        return [
            f"termius live GUI Hosts action keys {actual_panel_keys!r} "
            f"must equal {EXPECTED_TERMIUS_HOSTS_ACTION_KEYS!r}"
        ]

    labels = {label.text() for label in panel.findChildren(QLabel)}
    missing = sorted(required_termius_hosts_chrome_texts() - labels)
    if missing:
        return [f"termius live GUI Hosts chrome missing text: {missing}"]

    search = panel.findChild(QLineEdit, "termiusHostSearch")
    if search is None:
        return ["termius live GUI missing Hosts search field"]
    if search.placeholderText() != chrome.filter_placeholder:
        return [
            f"termius live GUI Hosts search placeholder {search.placeholderText()!r} "
            f"must equal {chrome.filter_placeholder!r}"
        ]
    if str(search.property("interactionState") or "") != "focused":
        return ["termius live GUI Hosts search must carry focused interaction state"]

    buttons = panel.findChildren(QToolButton, "termiusHostsAction")
    actual_button_keys = [str(button.property("termiusHostsActionKey") or "") for button in buttons]
    if actual_button_keys != EXPECTED_TERMIUS_HOSTS_ACTION_KEYS:
        return [
            f"termius live GUI Hosts button keys {actual_button_keys!r} "
            f"must equal {EXPECTED_TERMIUS_HOSTS_ACTION_KEYS!r}"
        ]
    expected_labels = {action.key: action.label for action in chrome.actions}
    expected_static_x = {action.key: action.static_x for action in chrome.actions}
    for button in buttons:
        key = str(button.property("termiusHostsActionKey") or "")
        label = str(button.property("termiusHostsActionLabel") or "")
        icon_key = str(button.property("termiusHostsIconKey") or "")
        static_x = int(button.property("termiusHostsStaticX") or 0)
        if label != expected_labels.get(key):
            return [f"termius live GUI Hosts action {key!r} label drifted"]
        if icon_key != EXPECTED_TERMIUS_HOSTS_ICON_KEYS.get(key):
            return [f"termius live GUI Hosts action {key!r} icon key drifted"]
        if static_x != expected_static_x.get(key):
            return [f"termius live GUI Hosts action {key!r} static position drifted"]
        if button.icon().isNull():
            return [f"termius live GUI Hosts action {key!r} must use an icon"]
    return []


def check_live_termius_host_identity_strip(window: Any) -> list[str]:
    from PyQt6.QtWidgets import QLabel, QWidget

    strip = gui_design_termius_host_identity_strip()
    panel = window.findChild(QWidget, "termiusHostIdentityStrip")
    if panel is None:
        return ["termius live GUI missing host-identity evidence strip"]
    actual_preset = str(panel.property("designPreset") or "")
    if actual_preset != "termius":
        return [f"termius live GUI host-identity designPreset {actual_preset!r} must equal 'termius'"]
    expected_panel_props = {
        "termiusHostIdentityTitleWidth": strip.title_width,
        "termiusHostIdentityStaticTitleX": strip.static_title_x,
        "termiusHostIdentityStaticTitleY": strip.static_title_y,
        "termiusHostIdentityStaticCellStartX": strip.static_cell_start_x,
        "termiusHostIdentityStaticCellGap": strip.static_cell_gap,
        "termiusHostIdentityLiveSpacing": strip.live_spacing,
    }
    for prop_name, expected_value in expected_panel_props.items():
        actual_value = int(panel.property(prop_name) or 0)
        if actual_value != expected_value:
            return [
                f"termius live GUI host-identity {prop_name} "
                f"{actual_value!r} must equal {expected_value!r}"
            ]
    actual_panel_keys = list(panel.property("termiusHostIdentityFieldKeys") or [])
    expected_keys = [field.key for field in strip.fields]
    if actual_panel_keys != expected_keys:
        return [f"termius live GUI host-identity field keys {actual_panel_keys!r} must equal {expected_keys!r}"]
    title = panel.findChild(QLabel, "termiusHostIdentityTitle")
    if title is None:
        return ["termius live GUI host-identity missing title label"]
    if title.minimumWidth() != strip.title_width or title.maximumWidth() != strip.title_width:
        return ["termius live GUI host-identity title width drifted"]
    labels = {label.text() for label in panel.findChildren(QLabel)}
    missing = sorted(required_termius_host_identity_texts() - labels)
    if missing:
        return [f"termius live GUI host-identity missing text: {missing}"]
    cells = panel.findChildren(QLabel, "termiusHostIdentityCell")
    actual_keys = [str(label.property("termiusHostIdentityKey") or "") for label in cells]
    if actual_keys != expected_keys:
        return [f"termius live GUI host-identity label keys {actual_keys!r} must equal {expected_keys!r}"]
    actual_widths = [int(label.property("termiusHostIdentityWidth") or 0) for label in cells]
    expected_widths = [field.static_width for field in strip.fields]
    if actual_widths != expected_widths:
        return [f"termius live GUI host-identity widths {actual_widths!r} must equal {expected_widths!r}"]
    for cell, field in zip(cells, strip.fields, strict=False):
        expected_props = {
            "termiusHostIdentityStaticY": field.static_y,
            "termiusHostIdentityStaticHeight": field.static_height,
            "termiusHostIdentityStaticLabelX": field.static_label_x,
            "termiusHostIdentityStaticLabelY": field.static_label_y,
            "termiusHostIdentityStaticValueX": field.static_value_x,
            "termiusHostIdentityStaticValueY": field.static_value_y,
            "termiusHostIdentityLiveMinWidth": field.live_min_width,
            "termiusHostIdentityLiveCellHeight": field.live_cell_height,
        }
        actual_role = str(cell.property("termiusHostIdentityRole") or "")
        if actual_role != field.role:
            return [
                f"termius live GUI host-identity field {field.key!r} role "
                f"{actual_role!r} must equal {field.role!r}"
            ]
        for prop_name, expected_value in expected_props.items():
            actual_value = int(cell.property(prop_name) or 0)
            if actual_value != expected_value:
                return [
                    f"termius live GUI host-identity field {field.key!r} {prop_name} "
                    f"{actual_value!r} must equal {expected_value!r}"
                ]
        if cell.minimumWidth() != field.live_min_width:
            return [f"termius live GUI host-identity field {field.key!r} minimum width drifted"]
        if cell.minimumHeight() != field.live_cell_height:
            return [f"termius live GUI host-identity field {field.key!r} height drifted"]
    return []


def check_live_termius_host_selection_route(window: Any) -> list[str]:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QLabel, QTabWidget, QTreeWidget, QWidget

    route = EXPECTED_TERMIUS_HOST_SELECTION_ROUTE
    tree = window.findChild(QTreeWidget, route.selected_tree_object)
    hosts_panel = window.findChild(QWidget, route.hosts_panel_object)
    identity_panel = window.findChild(QWidget, route.host_identity_object)
    tabs = window.findChild(QTabWidget, "sessionTabs")
    errors: list[str] = []
    if tree is None:
        errors.append("termius live GUI host-selection route missing profile tree")
    if hosts_panel is None:
        errors.append("termius live GUI host-selection route missing Hosts panel")
    if identity_panel is None:
        errors.append("termius live GUI host-selection route missing Host identity strip")
    if tabs is None:
        errors.append("termius live GUI host-selection route missing session tabs")
    if errors:
        return errors

    common_route_props = {
        "termiusHostRouteKey": route.key,
        "termiusHostRouteRole": route.route_role,
        "termiusHostRouteSelectedProfile": route.selected_profile_name,
        "termiusHostRouteSelectedTreeLabel": route.selected_tree_label,
        "termiusHostRouteHostsPanelObject": route.hosts_panel_object,
        "termiusHostRouteIdentityObject": route.host_identity_object,
        "termiusHostRouteIdentityFieldKey": route.identity_field_key,
        "termiusHostRouteIdentityCellObject": route.identity_cell_object,
        route.tab_label_property: route.active_tab_label,
        "termiusHostRouteTarget": route.target_value,
        "termiusHostRouteProtocol": route.protocol_value,
        route.identity_value_property: route.host_value,
        "termiusHostRouteRenderSource": route.render_source,
    }
    for label, widget in (
        ("profile-tree", tree),
        ("hosts-panel", hosts_panel),
        ("identity-strip", identity_panel),
    ):
        for property_name, expected_value in common_route_props.items():
            actual_value = str(widget.property(property_name) or "")
            if actual_value != expected_value:
                errors.append(
                    f"termius live GUI host-selection route {label} property "
                    f"{property_name} {actual_value!r} must equal {expected_value!r}"
                )

    tab_route_props = {
        "termiusHostRouteKey": route.key,
        "termiusHostRouteRole": route.route_role,
        "termiusHostRouteSelectedProfile": route.selected_profile_name,
        "termiusHostRouteSelectedTreeLabel": route.selected_tree_label,
        route.tab_label_property: route.active_tab_label,
        "termiusHostRouteTarget": route.target_value,
        "termiusHostRouteProtocol": route.protocol_value,
        route.identity_value_property: route.host_value,
        "termiusHostRouteRenderSource": route.render_source,
    }
    for property_name, expected_value in tab_route_props.items():
        actual_value = str(tabs.property(property_name) or "")
        if actual_value != expected_value:
            errors.append(
                f"termius live GUI host-selection route tabs property "
                f"{property_name} {actual_value!r} must equal {expected_value!r}"
            )
    if route.active_tab_label not in live_tab_labels(tabs):
        errors.append(f"termius live GUI host-selection route missing active tab {route.active_tab_label!r}")

    selected = tree.currentItem()
    if selected is None:
        errors.append("termius live GUI host-selection route missing selected tree item")
    else:
        base_role = int(Qt.ItemDataRole.UserRole)
        expected_item_data = {
            base_role: route.selected_profile_name,
            base_role + 81: route.key,
            base_role + 82: route.route_role,
            base_role + 83: route.selected_profile_name,
            base_role + 84: route.active_tab_label,
            base_role + 85: route.target_value,
            base_role + 86: route.protocol_value,
        }
        if route.selected_tree_label not in selected.text(0):
            errors.append("termius live GUI host-selection route selected tree label drifted")
        for role, expected_value in expected_item_data.items():
            actual_value = str(selected.data(0, role) or "")
            if actual_value != expected_value:
                errors.append(f"termius live GUI host-selection route tree role {role} drifted")
        if selected.data(0, base_role + 87) is not True:
            errors.append("termius live GUI host-selection route tree item is not marked selected")

    identity_cells = identity_panel.findChildren(QLabel, route.identity_cell_object)
    target_cells = [
        cell for cell in identity_cells if str(cell.property("termiusHostIdentityKey") or "") == route.identity_field_key
    ]
    if len(target_cells) != 1:
        errors.append("termius live GUI host-selection route must expose one Host identity cell")
    else:
        target_cell = target_cells[0]
        expected_cell_props = {
            "termiusHostRouteKey": route.key,
            "termiusHostRouteRole": route.route_role,
            "termiusHostRouteSelectedProfile": route.selected_profile_name,
            "termiusHostRouteSelectedTreeLabel": route.selected_tree_label,
            route.tab_label_property: route.active_tab_label,
            "termiusHostRouteTarget": route.target_value,
            "termiusHostRouteProtocol": route.protocol_value,
            route.identity_value_property: route.host_value,
            "termiusHostRouteRenderSource": route.render_source,
            "termiusHostIdentityValue": route.host_value,
        }
        for property_name, expected_value in expected_cell_props.items():
            actual_value = str(target_cell.property(property_name) or "")
            if actual_value != expected_value:
                errors.append(f"termius live GUI host-selection route identity property {property_name} drifted")
        if target_cell.text() != f"Host: {route.host_value}":
            errors.append("termius live GUI host-selection route Host identity text drifted")
    return errors


def check_live_termius_sync_route(window: Any) -> list[str]:
    from PyQt6.QtWidgets import QLabel, QToolButton

    route = EXPECTED_TERMIUS_SYNC_ROUTE
    expected_action = next(action for action in EXPECTED_TERMIUS_HOSTS_CHROME.actions if action.key == route.hosts_action_key)
    expected_chip = next(chip for chip in gui_design_termius_header_chips() if chip.key == route.header_chip_key)
    expected_field = next(field for field in EXPECTED_TERMIUS_HOST_IDENTITY_STRIP.fields if field.key == route.identity_field_key)
    sync_button = next(
        (
            button
            for button in window.findChildren(QToolButton, route.hosts_action_object)
            if str(button.property("termiusHostsActionKey") or "") == route.hosts_action_key
        ),
        None,
    )
    sync_chip = next(
        (
            label
            for label in window.findChildren(QLabel, route.header_chip_object)
            if str(label.property("termiusHeaderChipKey") or "") == route.header_chip_key
        ),
        None,
    )
    sync_cell = next(
        (
            label
            for label in window.findChildren(QLabel, route.identity_cell_object)
            if str(label.property("termiusHostIdentityKey") or "") == route.identity_field_key
        ),
        None,
    )
    route_widgets = {
        route.hosts_action_object: sync_button,
        route.header_chip_object: sync_chip,
        route.identity_cell_object: sync_cell,
    }
    missing = [object_name for object_name, widget in route_widgets.items() if widget is None]
    if missing:
        return [f"termius live GUI sync route missing widget(s): {missing}"]
    expected_common_props = {
        "termiusSyncRouteKey": route.key,
        "termiusSyncRouteRole": route.route_role,
        "termiusSyncRouteHostsActionKey": route.hosts_action_key,
        "termiusSyncRouteHostsActionObject": route.hosts_action_object,
        "termiusSyncRouteHeaderChipKey": route.header_chip_key,
        "termiusSyncRouteHeaderChipObject": route.header_chip_object,
        "termiusSyncRouteIdentityFieldKey": route.identity_field_key,
        "termiusSyncRouteIdentityCellObject": route.identity_cell_object,
        "termiusSyncRouteState": route.sync_state,
        "termiusSyncRouteRenderSource": route.render_source,
    }
    for object_name, widget in route_widgets.items():
        if widget is None:
            continue
        if widget.objectName() != object_name:
            return [f"termius live GUI sync route object {widget.objectName()!r} must equal {object_name!r}"]
        for prop_name, expected_value in expected_common_props.items():
            actual_value = str(widget.property(prop_name) or "")
            if actual_value != expected_value:
                return [
                    f"termius live GUI sync route {object_name}.{prop_name} "
                    f"{actual_value!r} must equal {expected_value!r}"
                ]
    if str(sync_button.property(route.action_label_property) or "") != expected_action.label:
        return ["termius live GUI sync route action label drifted"]
    if str(sync_chip.property(route.chip_label_property) or "") != expected_chip.label or sync_chip.text() != expected_chip.label:
        return ["termius live GUI sync route header chip label drifted"]
    if (
        str(sync_cell.property(route.identity_value_property) or "") != expected_field.value
        or sync_cell.text() != f"{expected_field.label}: {expected_field.value}"
    ):
        return ["termius live GUI sync route identity value drifted"]
    if expected_field.value != route.sync_state:
        return ["termius live GUI sync route expected field value must equal route state"]
    return []


def check_live_mremoteng_document_controls(window: Any) -> list[str]:
    from PyQt6.QtWidgets import QLabel, QLineEdit, QToolButton, QWidget

    chrome = gui_design_mremoteng_document_toolbar_chrome()
    panel = window.findChild(QWidget, "mRemoteNgDocumentControls")
    if panel is None:
        return ["mremoteng live GUI missing document-control evidence strip"]
    actual_preset = str(panel.property("designPreset") or "")
    if actual_preset != "mremoteng":
        return [f"mremoteng live GUI document-control designPreset {actual_preset!r} must equal 'mremoteng'"]
    expected_panel_props = {
        "mRemoteNgDocumentTitleWidth": chrome.title_width,
        "mRemoteNgDocumentStaticHeight": chrome.static_height,
        "mRemoteNgDocumentStaticButtonStartX": chrome.static_button_start_x,
        "mRemoteNgDocumentStaticButtonGap": chrome.static_button_gap,
        "mRemoteNgDocumentStaticFilterWidth": chrome.static_filter_width,
        "mRemoteNgDocumentStaticFilterY": chrome.static_filter_y,
        "mRemoteNgDocumentStaticFilterHeight": chrome.static_filter_height,
        "mRemoteNgDocumentLiveSpacing": chrome.live_spacing,
    }
    for prop_name, expected_value in expected_panel_props.items():
        actual_value = int(panel.property(prop_name) or 0)
        if actual_value != expected_value:
            return [
                f"mremoteng live GUI document-control {prop_name} "
                f"{actual_value!r} must equal {expected_value!r}"
            ]
    title = panel.findChild(QLabel, "mRemoteNgDocumentTitle")
    if title is None or title.text() != chrome.title:
        actual_title = None if title is None else title.text()
        return [f"mremoteng live GUI document toolbar title {actual_title!r} must equal {chrome.title!r}"]
    if title.minimumWidth() != chrome.title_width or title.maximumWidth() != chrome.title_width:
        return ["mremoteng live GUI document toolbar title width drifted"]
    filter_input = panel.findChild(QLineEdit, "mRemoteNgDocumentFilter")
    if filter_input is None or filter_input.placeholderText() != chrome.filter_placeholder:
        actual_placeholder = None if filter_input is None else filter_input.placeholderText()
        return [
            f"mremoteng live GUI document filter placeholder {actual_placeholder!r} "
            f"must equal {chrome.filter_placeholder!r}"
        ]
    filter_width = int(filter_input.property("mRemoteNgDocumentFilterWidth") or 0)
    filter_height = int(filter_input.property("mRemoteNgDocumentFilterHeight") or 0)
    if filter_width != chrome.live_filter_width or filter_input.minimumWidth() != chrome.live_filter_width:
        return ["mremoteng live GUI document filter width drifted"]
    if filter_input.maximumWidth() != chrome.live_filter_width:
        return ["mremoteng live GUI document filter maximum width drifted"]
    if filter_height != chrome.live_filter_height or filter_input.minimumHeight() != chrome.live_filter_height:
        return ["mremoteng live GUI document filter height drifted"]

    if str(filter_input.property("interactionState") or "") != "focused":
        return ["mremoteng live GUI document filter must expose focused interactionState"]

    buttons = panel.findChildren(QToolButton, "mRemoteNgDocumentControl")
    expected = list(gui_design_mremoteng_document_controls())
    actual_keys = [str(button.property("mRemoteNgDocumentControlKey") or "") for button in buttons]
    expected_keys = [control.key for control in expected]
    if actual_keys != expected_keys:
        return [f"mremoteng live GUI document-control keys {actual_keys!r} must equal {expected_keys!r}"]
    actual_labels = [button.text() for button in buttons]
    expected_labels = [control.label for control in expected]
    if actual_labels != expected_labels:
        return [f"mremoteng live GUI document-control labels {actual_labels!r} must equal {expected_labels!r}"]
    for button, control in zip(buttons, expected, strict=False):
        icon_key = str(button.property("mRemoteNgDocumentIconKey") or "")
        if icon_key != control.icon_key:
            return [f"mremoteng live GUI document-control icon key {icon_key!r} must equal {control.icon_key!r}"]
        expected_props = {
            "mRemoteNgDocumentStaticWidth": control.static_width,
            "mRemoteNgDocumentStaticY": control.static_y,
            "mRemoteNgDocumentStaticHeight": control.static_height,
            "mRemoteNgDocumentStaticIconX": control.static_icon_x,
            "mRemoteNgDocumentStaticIconY": control.static_icon_y,
            "mRemoteNgDocumentStaticIconSize": control.static_icon_size,
            "mRemoteNgDocumentStaticLabelX": control.static_label_x,
            "mRemoteNgDocumentStaticLabelY": control.static_label_y,
            "mRemoteNgDocumentLiveIconSize": control.live_icon_size,
            "mRemoteNgDocumentLiveMinWidth": control.live_min_width,
            "mRemoteNgDocumentLiveButtonHeight": control.live_button_height,
        }
        for prop_name, expected_value in expected_props.items():
            actual_value = int(button.property(prop_name) or 0)
            if actual_value != expected_value:
                return [
                    f"mremoteng live GUI document-control {control.key!r} {prop_name} "
                    f"{actual_value!r} must equal {expected_value!r}"
                ]
        render_source = str(button.property("mRemoteNgDocumentRenderSource") or "")
        if render_source != control.render_source:
            return [
                f"mremoteng live GUI document-control {control.key!r} render source "
                f"{render_source!r} must equal {control.render_source!r}"
            ]
        expected_state = "checked" if control.key == "external-tool" else "normal"
        actual_state = str(button.property("interactionState") or "")
        if actual_state != expected_state:
            return [
                f"mremoteng live GUI document-control {control.key!r} interactionState "
                f"{actual_state!r} must equal {expected_state!r}"
            ]
        if button.icon().isNull():
            return [f"mremoteng live GUI document-control {control.key!r} must use an icon"]
        if button.iconSize().width() != control.live_icon_size or button.iconSize().height() != control.live_icon_size:
            return [f"mremoteng live GUI document-control {control.key!r} icon size drifted"]
        if button.minimumWidth() != control.live_min_width:
            return [f"mremoteng live GUI document-control {control.key!r} minimum width drifted"]
        if button.minimumHeight() != control.live_button_height:
            return [f"mremoteng live GUI document-control {control.key!r} height drifted"]
    return []


def check_live_mremoteng_property_grid(window: Any) -> list[str]:
    from PyQt6.QtWidgets import QLabel, QWidget

    chrome = gui_design_mremoteng_property_grid_chrome()
    panel = window.findChild(QWidget, "mRemoteNgPropertyGrid")
    if panel is None:
        return ["mremoteng live GUI missing property-grid evidence panel"]
    actual_preset = str(panel.property("designPreset") or "")
    if actual_preset != "mremoteng":
        return [f"mremoteng live GUI property-grid designPreset {actual_preset!r} must equal 'mremoteng'"]
    actual_column_keys = list(panel.property("mRemoteNgPropertyColumnKeys") or [])
    if actual_column_keys != EXPECTED_MREMOTENG_PROPERTY_COLUMN_KEYS:
        return [
            f"mremoteng live GUI property-grid column keys {actual_column_keys!r} "
            f"must equal {EXPECTED_MREMOTENG_PROPERTY_COLUMN_KEYS!r}"
        ]
    actual_row_keys = list(panel.property("mRemoteNgPropertyRowKeys") or [])
    if actual_row_keys != EXPECTED_MREMOTENG_PROPERTY_ROW_KEYS:
        return [
            f"mremoteng live GUI property-grid row keys {actual_row_keys!r} "
            f"must equal {EXPECTED_MREMOTENG_PROPERTY_ROW_KEYS!r}"
        ]

    labels = {label.text() for label in panel.findChildren(QLabel)}
    required_texts = {chrome.title, chrome.scope_label, chrome.inheritance_label}
    required_texts.update(column.label for column in chrome.columns)
    for row in chrome.rows:
        required_texts.update((row.property_label, row.inherited_from, row.effective_value, row.source))
    missing = sorted(required_texts - labels)
    if missing:
        return [f"mremoteng live GUI property-grid missing text: {missing}"]

    row_frames = panel.findChildren(QWidget, "mRemoteNgPropertyGridRow")
    actual_frame_keys = [str(row.property("mRemoteNgPropertyRowKey") or "") for row in row_frames]
    if actual_frame_keys != EXPECTED_MREMOTENG_PROPERTY_ROW_KEYS:
        return [
            f"mremoteng live GUI property-grid frame row keys {actual_frame_keys!r} "
            f"must equal {EXPECTED_MREMOTENG_PROPERTY_ROW_KEYS!r}"
        ]
    actual_inherited = [str(row.property("mRemoteNgPropertyInherited") or "") for row in row_frames]
    expected_inherited = ["true" if row.inherited else "false" for row in chrome.rows]
    if actual_inherited != expected_inherited:
        return [
            f"mremoteng live GUI property-grid inherited flags {actual_inherited!r} "
            f"must equal {expected_inherited!r}"
        ]

    cells = panel.findChildren(QLabel, "mRemoteNgPropertyGridCell")
    actual_cells = {
        (
            str(cell.property("mRemoteNgPropertyRowKey") or ""),
            str(cell.property("mRemoteNgPropertyColumnKey") or ""),
        ): str(cell.property("mRemoteNgPropertyCellValue") or "")
        for cell in cells
    }
    expected_cells: dict[tuple[str, str], str] = {}
    for row in chrome.rows:
        values = {
            "property": row.property_label,
            "inherited": row.inherited_from,
            "effective": row.effective_value,
            "source": row.source,
        }
        for column in chrome.columns:
            expected_cells[(row.key, column.key)] = values[column.key]
    if actual_cells != expected_cells:
        return ["mremoteng live GUI property-grid cell metadata drifted"]
    return []


def check_live_mremoteng_connection_document_route(window: Any) -> list[str]:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QLabel, QTabWidget, QToolButton, QTreeWidget, QWidget

    route = EXPECTED_MREMOTENG_CONNECTION_DOCUMENT_ROUTE
    tree = window.findChild(QTreeWidget, route.selected_tree_object)
    controls_panel = window.findChild(QWidget, route.document_controls_object)
    property_grid = window.findChild(QWidget, route.property_grid_object)
    tabs = window.findChild(QTabWidget, "sessionTabs")
    errors: list[str] = []
    if tree is None:
        errors.append("mremoteng live GUI connection-document route missing connection tree")
    if controls_panel is None:
        errors.append("mremoteng live GUI connection-document route missing document controls")
    if property_grid is None:
        errors.append("mremoteng live GUI connection-document route missing property grid")
    if tabs is None:
        errors.append("mremoteng live GUI connection-document route missing session tabs")
    if errors:
        return errors

    common_route_props = {
        "mRemoteNgConnectionRouteKey": route.key,
        "mRemoteNgConnectionRouteRole": route.route_role,
        "mRemoteNgConnectionRouteSelectedProfile": route.selected_profile_name,
        "mRemoteNgConnectionRouteSelectedTreeLabel": route.selected_tree_label,
        "mRemoteNgConnectionRouteDocumentControlsObject": route.document_controls_object,
        "mRemoteNgConnectionRouteDocumentControlKey": route.document_control_key,
        "mRemoteNgConnectionRouteDocumentControlObject": route.document_control_object,
        "mRemoteNgConnectionRoutePropertyGridObject": route.property_grid_object,
        "mRemoteNgConnectionRoutePropertyRowKey": route.property_row_key,
        "mRemoteNgConnectionRoutePropertyCellObject": route.property_cell_object,
        route.tab_label_property: route.active_tab_label,
        "mRemoteNgConnectionRouteProtocol": route.protocol,
        "mRemoteNgConnectionRouteState": route.workspace_state,
        route.property_value_property: route.property_value,
        "mRemoteNgConnectionRouteRenderSource": route.render_source,
    }
    for label, widget in (
        ("connection-tree", tree),
        ("document-controls", controls_panel),
        ("property-grid", property_grid),
    ):
        for property_name, expected_value in common_route_props.items():
            actual_value = str(widget.property(property_name) or "")
            if actual_value != expected_value:
                errors.append(
                    f"mremoteng live GUI connection-document route {label} property "
                    f"{property_name} {actual_value!r} must equal {expected_value!r}"
                )

    if route.active_tab_label not in live_tab_labels(tabs):
        errors.append(f"mremoteng live GUI connection-document route missing active tab {route.active_tab_label!r}")

    selected = tree.currentItem()
    if selected is None:
        errors.append("mremoteng live GUI connection-document route missing selected tree item")
    else:
        base_role = int(Qt.ItemDataRole.UserRole)
        expected_item_data = {
            base_role: route.selected_profile_name,
            base_role + 61: route.key,
            base_role + 62: route.route_role,
            base_role + 63: route.selected_profile_name,
            base_role + 64: route.active_tab_label,
            base_role + 65: route.protocol,
            base_role + 66: route.workspace_state,
        }
        if route.selected_tree_label not in selected.text(0):
            errors.append("mremoteng live GUI connection-document route selected tree label drifted")
        for role, expected_value in expected_item_data.items():
            actual_value = str(selected.data(0, role) or "")
            if actual_value != expected_value:
                errors.append(f"mremoteng live GUI connection-document route tree role {role} drifted")
        if selected.data(0, base_role + 67) is not True:
            errors.append("mremoteng live GUI connection-document route tree item is not marked selected")

    buttons = controls_panel.findChildren(QToolButton, route.document_control_object)
    target_buttons = [
        button
        for button in buttons
        if str(button.property("mRemoteNgDocumentControlKey") or "") == route.document_control_key
    ]
    if len(target_buttons) != 1:
        errors.append("mremoteng live GUI connection-document route must expose one target document control")
    else:
        target_button = target_buttons[0]
        expected_button_props = {
            "mRemoteNgConnectionRouteKey": route.key,
            "mRemoteNgConnectionRouteRole": route.route_role,
            "mRemoteNgConnectionRouteSelectedProfile": route.selected_profile_name,
            "mRemoteNgConnectionRouteSelectedTreeLabel": route.selected_tree_label,
            route.tab_label_property: route.active_tab_label,
            "mRemoteNgConnectionRouteProtocol": route.protocol,
            "mRemoteNgConnectionRouteState": route.workspace_state,
            "mRemoteNgConnectionRoutePropertyRowKey": route.property_row_key,
            route.property_value_property: route.property_value,
            route.control_active_property: "true",
        }
        for property_name, expected_value in expected_button_props.items():
            actual_value = str(target_button.property(property_name) or "")
            if actual_value != expected_value:
                errors.append(f"mremoteng live GUI routed document control property {property_name} drifted")
        if target_button.text() != "Reconnect":
            errors.append("mremoteng live GUI routed document control label must be Reconnect")

    inactive_route_states = [
        str(button.property(route.control_active_property) or "")
        for button in buttons
        if str(button.property("mRemoteNgDocumentControlKey") or "") != route.document_control_key
    ]
    if any(state != "false" for state in inactive_route_states):
        errors.append("mremoteng live GUI non-routed document controls must not expose active route state")

    row_frames = property_grid.findChildren(QWidget, "mRemoteNgPropertyGridRow")
    route_rows = [row for row in row_frames if str(row.property("mRemoteNgPropertyRowKey") or "") == route.property_row_key]
    if len(route_rows) != 1:
        errors.append("mremoteng live GUI connection-document route must expose one property-grid route row")
    else:
        route_row = route_rows[0]
        expected_row_props = {
            "mRemoteNgConnectionRouteKey": route.key,
            "mRemoteNgConnectionRouteRole": route.route_role,
            "mRemoteNgConnectionRouteSelectedProfile": route.selected_profile_name,
            route.tab_label_property: route.active_tab_label,
            "mRemoteNgConnectionRouteProtocol": route.protocol,
            "mRemoteNgConnectionRouteState": route.workspace_state,
            "mRemoteNgConnectionRoutePropertyRowKey": route.property_row_key,
            "mRemoteNgConnectionRoutePropertyCellObject": route.property_cell_object,
            route.property_value_property: route.property_value,
            "mRemoteNgConnectionRouteRenderSource": route.render_source,
        }
        for property_name, expected_value in expected_row_props.items():
            actual_value = str(route_row.property(property_name) or "")
            if actual_value != expected_value:
                errors.append(f"mremoteng live GUI property-grid route row property {property_name} drifted")

    route_cells = [
        cell
        for cell in property_grid.findChildren(QLabel, route.property_cell_object)
        if str(cell.property("mRemoteNgPropertyRowKey") or "") == route.property_row_key
        and str(cell.property("mRemoteNgPropertyColumnKey") or "") == "effective"
    ]
    if len(route_cells) != 1:
        errors.append("mremoteng live GUI connection-document route must expose one effective-value route cell")
    else:
        route_cell = route_cells[0]
        if str(route_cell.property("mRemoteNgPropertyCellValue") or "") != route.property_value:
            errors.append("mremoteng live GUI connection-document route property effective value drifted")
        if str(route_cell.property(route.property_value_property) or "") != route.property_value:
            errors.append("mremoteng live GUI connection-document route property value metadata drifted")
    return errors


def live_contract_checks_for_preset(preset_id: str) -> list[str]:
    checks = [
        "required-widget-visibility",
        "session-tabs",
        "home-tab-label",
        "profile-tree-content",
        "status-segments",
        "interaction-state",
    ]
    if preset_id == "mobaxterm":
        checks.extend(["moba-home-welcome", "moba-home-welcome-geometry"])
    else:
        checks.append("workflow-cards")
    if live_layout_contracts_for_preset(preset_id):
        checks.append("layout-geometry")
    if live_topology_contracts_for_preset(preset_id):
        checks.append("live-topology")
    if preset_id == "mobaxterm":
        checks.extend(
            [
                "quick-connect-strip",
                "quick-connect-chrome",
                "quick-connect-suggestions",
                "connected-quick-connect-idle",
                "moba-session-tree-icons",
                "moba-session-tree-geometry",
                "top-stack-geometry",
                "titlebar-chrome",
                "top-menu-chrome",
                "top-menu-geometry",
                "ribbon-actions",
                "ribbon-geometry",
                "generated-ribbon-icons",
                "moba-rail-roles",
                "moba-rail-labels",
                "moba-rail-geometry",
                "connected-tab-chrome",
                "connected-tab-geometry",
                "connected-dock-frame",
                "session-edge-controls",
                "session-edge-geometry",
                "right-utility-rail",
                "right-utility-rail-chrome",
                "right-utility-rail-geometry",
                "connected-sftp-dock",
                "sftp-toolbar-groups",
                "sftp-toolbar-geometry",
                "sftp-file-row-icons",
                "sftp-routed-file-rows",
                "sftp-dock-density",
                "sftp-browser-chrome",
                "sftp-browser-geometry",
                "sftp-follow-folder-route",
                "sftp-dock-chrome",
                "remote-monitoring-dock",
                "remote-monitoring-footer-geometry",
                "monitoring-telemetry-route",
                "moba-monitoring-controls",
                "moba-monitoring-control-geometry",
                "ssh-banner",
                "ssh-banner-chrome",
                "ssh-banner-capability-card",
                "ssh-banner-row-geometry",
                "terminal-transcript",
                "terminal-transcript-geometry",
                "bottom-telemetry",
                "bottom-telemetry-geometry",
                "bottom-status-chrome",
                "bottom-status-geometry",
                "bottom-edge-controls",
                "connected-session-route",
                "connected-session-identity-route",
            ]
        )
    else:
        checks.extend(
            [
                "preset-selector-visible",
                "toolbar-search-visible",
                "sidebar-copy",
                "toolbar-actions",
                "workspace-surface",
                "reference-state",
            ]
        )
        if preset_id == "securecrt":
            checks.append("securecrt-top-chrome")
            checks.append("securecrt-session-manager-chrome")
            checks.append("securecrt-session-manager-geometry")
            checks.append("securecrt-session-manager-route")
            checks.append("securecrt-tree-icons")
            checks.append("securecrt-session-status-strip")
            checks.append("securecrt-session-status-geometry")
            checks.append("securecrt-command-window")
            checks.append("securecrt-command-window-geometry")
            checks.append("securecrt-command-window-send-route")
        if preset_id == "remmina":
            checks.append("remmina-tree-icons")
            checks.append("remmina-profile-list-chrome")
            checks.append("remmina-profile-list-geometry")
            checks.append("remmina-viewer-controls")
            checks.append("remmina-viewer-control-geometry")
            checks.append("remmina-profile-viewer-route")
            checks.append("remmina-clipboard-route")
        if preset_id == "termius":
            checks.append("termius-tree-icons")
            checks.append("termius-hosts-chrome")
            checks.append("termius-header-chips")
            checks.append("termius-host-identity-strip")
            checks.append("termius-host-identity-geometry")
            checks.append("termius-host-selection-route")
            checks.append("termius-sync-route")
        if preset_id == "mremoteng":
            checks.append("mremoteng-tree-icons")
            checks.append("mremoteng-top-chrome")
            checks.append("mremoteng-document-controls")
            checks.append("mremoteng-document-control-geometry")
            checks.append("mremoteng-property-grid")
            checks.append("mremoteng-connection-document-route")
    return checks


def product_tree_icon_summary(preset_id: str) -> list[dict[str, object]]:
    return [
        {
            "label": label,
            "icon_key": row.icon_key,
            "row_kind": row.row_kind,
            "static_size": row.static_size,
        }
        for label, row in EXPECTED_PRODUCT_TREE_ICON_ROWS.get(preset_id, ())
    ]


def live_contract_summary_for_preset(preset_id: str) -> dict[str, object]:
    layout_contracts = live_layout_contracts_for_preset(preset_id)
    topology_contracts = live_topology_contracts_for_preset(preset_id)
    workspace_texts: list[str] = []
    if preset_id != "mobaxterm":
        workspace_texts = sorted(required_workspace_surface_texts(preset_id))
    reference_texts: list[str] = []
    if preset_id != "mobaxterm":
        reference_texts = sorted(required_reference_state_texts(preset_id))
    return {
        "required_widgets": required_widgets_for_preset(preset_id),
        "present_widgets": present_widgets_for_preset(preset_id),
        "contract_checks": live_contract_checks_for_preset(preset_id),
        "expected_home_tab_label": gui_design_home_tab_label(preset_id),
        "reference_profile": PRESET_REFERENCE_PROFILES.get(preset_id),
        "expected_reference_tab_label": EXPECTED_LIVE_REFERENCE_TAB_LABELS.get(preset_id),
        "expected_tree_labels": sorted(EXPECTED_LIVE_TREE_LABELS.get(preset_id, set())),
        "expected_product_tree_icons": product_tree_icon_summary(preset_id),
        "expected_moba_session_tree_chrome": (
            {
                "header_height": EXPECTED_MOBA_SESSION_TREE_CHROME.header_height,
                "header_icon_x": EXPECTED_MOBA_SESSION_TREE_CHROME.header_icon_x,
                "header_text_x": EXPECTED_MOBA_SESSION_TREE_CHROME.header_text_x,
                "row_start_y": EXPECTED_MOBA_SESSION_TREE_CHROME.row_start_y,
                "indentation": EXPECTED_MOBA_SESSION_TREE_CHROME.indentation,
                "root_row_height": EXPECTED_MOBA_SESSION_TREE_CHROME.root_row_height,
                "group_row_height": EXPECTED_MOBA_SESSION_TREE_CHROME.group_row_height,
                "profile_row_height": EXPECTED_MOBA_SESSION_TREE_CHROME.profile_row_height,
                "group_icon_x": EXPECTED_MOBA_SESSION_TREE_CHROME.group_icon_x,
                "group_label_x": EXPECTED_MOBA_SESSION_TREE_CHROME.group_label_x,
                "profile_icon_x": EXPECTED_MOBA_SESSION_TREE_CHROME.profile_icon_x,
                "profile_label_x": EXPECTED_MOBA_SESSION_TREE_CHROME.profile_label_x,
                "profile_target_x": EXPECTED_MOBA_SESSION_TREE_CHROME.profile_target_x,
                "selected_left": EXPECTED_MOBA_SESSION_TREE_CHROME.selected_left,
                "selected_height": EXPECTED_MOBA_SESSION_TREE_CHROME.selected_height,
                "render_source": EXPECTED_MOBA_SESSION_TREE_CHROME.render_source,
            }
            if preset_id == "mobaxterm"
            else {}
        ),
        "expected_status_segments": list(gui_design_status_segments(preset_id)),
        "expected_moba_rail_labels": EXPECTED_MOBA_RAIL_LABELS if preset_id == "mobaxterm" else {},
        "expected_moba_rail_chrome": (
            {
                "rail_width": EXPECTED_MOBA_RAIL_CHROME.rail_width,
                "icon_x": EXPECTED_MOBA_RAIL_CHROME.icon_x,
                "static_icon_size": EXPECTED_MOBA_RAIL_CHROME.static_icon_size,
                "live_icon_size": EXPECTED_MOBA_RAIL_CHROME.live_icon_size,
                "generated_icon_size": EXPECTED_MOBA_RAIL_CHROME.generated_icon_size,
                "button_width": EXPECTED_MOBA_RAIL_CHROME.button_width,
                "button_height": EXPECTED_MOBA_RAIL_CHROME.button_height,
                "active_x": EXPECTED_MOBA_RAIL_CHROME.active_x,
                "active_y_offset": EXPECTED_MOBA_RAIL_CHROME.active_y_offset,
                "active_width": EXPECTED_MOBA_RAIL_CHROME.active_width,
                "active_height": EXPECTED_MOBA_RAIL_CHROME.active_height,
                "label_width": EXPECTED_MOBA_RAIL_CHROME.label_width,
                "label_height": EXPECTED_MOBA_RAIL_CHROME.label_height,
                "label_step": EXPECTED_MOBA_RAIL_CHROME.label_step,
                "unlabeled_gap_after": EXPECTED_MOBA_RAIL_CHROME.unlabeled_gap_after,
                "label_font_size": EXPECTED_MOBA_RAIL_CHROME.label_font_size,
                "render_source": EXPECTED_MOBA_RAIL_CHROME.render_source,
            }
            if preset_id == "mobaxterm"
            else {}
        ),
        "expected_moba_rail_items": (
            [
                {
                    "role": item.role,
                    "label": item.label,
                    "icon_key": item.icon_key,
                    "rail_icon_key": item.rail_icon_key,
                    "object_name": item.object_name,
                }
                for item in EXPECTED_MOBA_RAIL_ITEMS
            ]
            if preset_id == "mobaxterm"
            else []
        ),
        "expected_moba_rail_item_geometry": (
            [
                {
                    "role": geometry.role,
                    "static_icon_y": geometry.static_icon_y,
                    "static_label_y": geometry.static_label_y,
                }
                for geometry in EXPECTED_MOBA_RAIL_ITEM_GEOMETRY
            ]
            if preset_id == "mobaxterm"
            else []
        ),
        "expected_moba_top_menu": (
            [{"key": item.key, "label": item.label, "primary_action": item.primary_action} for item in EXPECTED_MOBA_TOP_MENU_ITEMS]
            if preset_id == "mobaxterm"
            else []
        ),
        "expected_moba_top_menu_geometry": (
            [geometry.to_dict() for geometry in EXPECTED_MOBA_TOP_MENU_GEOMETRY]
            if preset_id == "mobaxterm"
            else []
        ),
        "expected_moba_ribbon_action_geometry": (
            [geometry.to_dict() for geometry in EXPECTED_MOBA_RIBBON_ACTION_GEOMETRY]
            if preset_id == "mobaxterm"
            else []
        ),
        "expected_moba_titlebar_chrome": (
            {
                "icon_key": EXPECTED_MOBA_TITLEBAR_CHROME.icon_key,
                "static_height": EXPECTED_MOBA_TITLEBAR_CHROME.static_height,
                "icon_left": EXPECTED_MOBA_TITLEBAR_CHROME.icon_left,
                "icon_size": EXPECTED_MOBA_TITLEBAR_CHROME.icon_size,
                "title_left": EXPECTED_MOBA_TITLEBAR_CHROME.title_left,
                "control_keys": list(EXPECTED_MOBA_TITLEBAR_CHROME.control_keys),
                "control_width": EXPECTED_MOBA_TITLEBAR_CHROME.control_width,
            }
            if preset_id == "mobaxterm"
            else {}
        ),
        "expected_moba_top_stack_geometry": (
            {
                "titlebar_height": EXPECTED_MOBA_TOP_STACK_GEOMETRY.titlebar_height,
                "menu_y": EXPECTED_MOBA_TOP_STACK_GEOMETRY.menu_y,
                "menu_height": EXPECTED_MOBA_TOP_STACK_GEOMETRY.menu_height,
                "ribbon_y": EXPECTED_MOBA_TOP_STACK_GEOMETRY.ribbon_y,
                "ribbon_height": EXPECTED_MOBA_TOP_STACK_GEOMETRY.ribbon_height,
                "quick_connect_y": EXPECTED_MOBA_TOP_STACK_GEOMETRY.quick_connect_y,
                "quick_connect_height": EXPECTED_MOBA_TOP_STACK_GEOMETRY.quick_connect_height,
                "left_dock_y": EXPECTED_MOBA_TOP_STACK_GEOMETRY.left_dock_y,
                "tab_y": EXPECTED_MOBA_TOP_STACK_GEOMETRY.tab_y,
                "tab_height": EXPECTED_MOBA_TOP_STACK_GEOMETRY.tab_height,
                "terminal_content_y": EXPECTED_MOBA_TOP_STACK_GEOMETRY.terminal_content_y,
                "status_height": EXPECTED_MOBA_TOP_STACK_GEOMETRY.status_height,
                "side_width": EXPECTED_MOBA_TOP_STACK_GEOMETRY.side_width,
                "rail_width": EXPECTED_MOBA_TOP_STACK_GEOMETRY.rail_width,
            }
            if preset_id == "mobaxterm"
            else {}
        ),
        "expected_moba_connected_dock_frame": (
            {
                "side_width": EXPECTED_MOBA_CONNECTED_DOCK_FRAME.side_width,
                "rail_width": EXPECTED_MOBA_CONNECTED_DOCK_FRAME.rail_width,
                "dock_x": EXPECTED_MOBA_CONNECTED_DOCK_FRAME.dock_x,
                "dock_y": EXPECTED_MOBA_CONNECTED_DOCK_FRAME.dock_y,
                "dock_width": EXPECTED_MOBA_CONNECTED_DOCK_FRAME.dock_width,
                "dock_height": EXPECTED_MOBA_CONNECTED_DOCK_FRAME.dock_height,
                "workspace_x": EXPECTED_MOBA_CONNECTED_DOCK_FRAME.workspace_x,
                "quick_connect_y": EXPECTED_MOBA_CONNECTED_DOCK_FRAME.quick_connect_y,
                "quick_connect_height": EXPECTED_MOBA_CONNECTED_DOCK_FRAME.quick_connect_height,
                "status_y": EXPECTED_MOBA_CONNECTED_DOCK_FRAME.status_y,
            }
            if preset_id == "mobaxterm"
            else {}
        ),
        "expected_moba_connected_session_route": (
            EXPECTED_MOBA_CONNECTED_SESSION_ROUTE.to_dict()
            if preset_id == "mobaxterm"
            else {}
        ),
        "expected_moba_connected_session_identity_route": (
            EXPECTED_MOBA_CONNECTED_SESSION_IDENTITY_ROUTE.to_dict()
            if preset_id == "mobaxterm"
            else {}
        ),
        "expected_moba_quick_connect_chrome": (
            {
                "placeholder": EXPECTED_MOBA_QUICK_CONNECT_CHROME.placeholder,
                "dropdown_marker": EXPECTED_MOBA_QUICK_CONNECT_CHROME.dropdown_marker,
                "static_height": EXPECTED_MOBA_QUICK_CONNECT_CHROME.static_height,
                "marker_width": EXPECTED_MOBA_QUICK_CONNECT_CHROME.marker_width,
                "input_left": EXPECTED_MOBA_QUICK_CONNECT_CHROME.input_left,
                "connected_idle_query": EXPECTED_MOBA_QUICK_CONNECT_CHROME.connected_idle_query,
                "connected_suggestions_visible": EXPECTED_MOBA_QUICK_CONNECT_CHROME.connected_suggestions_visible,
            }
            if preset_id == "mobaxterm"
            else {}
        ),
        "expected_moba_connected_quick_connect_idle": (
            {
                "query": EXPECTED_MOBA_QUICK_CONNECT_CHROME.connected_idle_query,
                "suggestions_visible": EXPECTED_MOBA_QUICK_CONNECT_CHROME.connected_suggestions_visible,
            }
            if preset_id == "mobaxterm"
            else {}
        ),
        "expected_moba_quick_connect_suggestion_chrome": (
            {
                "preview_query": EXPECTED_MOBA_QUICK_CONNECT_SUGGESTION_CHROME.preview_query,
                "expected_kinds": list(EXPECTED_MOBA_QUICK_CONNECT_SUGGESTION_CHROME.expected_kinds),
                "max_visible_rows": EXPECTED_MOBA_QUICK_CONNECT_SUGGESTION_CHROME.max_visible_rows,
                "row_height": EXPECTED_MOBA_QUICK_CONNECT_SUGGESTION_CHROME.row_height,
                "static_width": EXPECTED_MOBA_QUICK_CONNECT_SUGGESTION_CHROME.static_width,
                "detail_separator": EXPECTED_MOBA_QUICK_CONNECT_SUGGESTION_CHROME.detail_separator,
            }
            if preset_id == "mobaxterm"
            else {}
        ),
        "expected_moba_home_welcome_chrome": (
            {
                "title": EXPECTED_MOBA_HOME_WELCOME_CHROME.title,
                "subtitle": EXPECTED_MOBA_HOME_WELCOME_CHROME.subtitle,
                "icon_key": EXPECTED_MOBA_HOME_WELCOME_CHROME.icon_key,
                "primary_action_icon_key": EXPECTED_MOBA_HOME_WELCOME_CHROME.primary_action_icon_key,
                "secondary_action_icon_key": EXPECTED_MOBA_HOME_WELCOME_CHROME.secondary_action_icon_key,
                "search_width": EXPECTED_MOBA_HOME_WELCOME_CHROME.search_width,
                "action_spacing": EXPECTED_MOBA_HOME_WELCOME_CHROME.action_spacing,
                "recent_title": EXPECTED_MOBA_HOME_WELCOME_CHROME.recent_title,
                "surface_width": EXPECTED_MOBA_HOME_WELCOME_CHROME.surface_width,
            }
            if preset_id == "mobaxterm"
            else {}
        ),
        "expected_moba_home_welcome_geometry": (
            {
                "center_side_margin": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.center_side_margin,
                "hero_min_y": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.hero_min_y,
                "hero_height": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.hero_height,
                "logo_size": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.logo_size,
                "logo_inner_padding": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.logo_inner_padding,
                "logo_icon_size": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.logo_icon_size,
                "logo_cluster_width": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.logo_cluster_width,
                "title_gap": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.title_gap,
                "title_y_offset": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.title_y_offset,
                "title_font_size": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.title_font_size,
                "subtitle_y_offset": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.subtitle_y_offset,
                "subtitle_font_size": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.subtitle_font_size,
                "button_y_offset": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.button_y_offset,
                "primary_width": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.primary_width,
                "secondary_width": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.secondary_width,
                "action_gap": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.action_gap,
                "button_height": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.button_height,
                "button_icon_x": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.button_icon_x,
                "button_icon_y": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.button_icon_y,
                "button_icon_size": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.button_icon_size,
                "button_label_x": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.button_label_x,
                "button_label_y": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.button_label_y,
                "button_font_size": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.button_font_size,
                "search_y_gap": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.search_y_gap,
                "search_height": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.search_height,
                "search_text_x": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.search_text_x,
                "search_text_y": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.search_text_y,
                "search_font_size": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.search_font_size,
                "recent_y_gap": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.recent_y_gap,
                "recent_title_font_size": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.recent_title_font_size,
                "recent_item_y_offset": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.recent_item_y_offset,
                "recent_item_step": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.recent_item_step,
                "recent_column_padding": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.recent_column_padding,
                "footer_y_offset": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.footer_y_offset,
                "footer_font_size": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.footer_font_size,
                "live_max_extra_width": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.live_max_extra_width,
                "live_layout_spacing": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.live_layout_spacing,
                "live_title_row_spacing": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.live_title_row_spacing,
                "live_title_column_spacing": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.live_title_column_spacing,
                "live_logo_box_width": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.live_logo_box_width,
                "live_logo_box_height": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.live_logo_box_height,
                "live_logo_pixmap_size": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.live_logo_pixmap_size,
                "live_recent_title_top_margin": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.live_recent_title_top_margin,
                "live_recent_column_spacing": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.live_recent_column_spacing,
                "live_recent_row_spacing": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.live_recent_row_spacing,
                "live_footer_top_margin": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.live_footer_top_margin,
                "render_source": EXPECTED_MOBA_HOME_WELCOME_GEOMETRY.render_source,
            }
            if preset_id == "mobaxterm"
            else {}
        ),
        "expected_moba_tab_chrome_keys": sorted(EXPECTED_MOBA_TAB_CHROME_KEYS) if preset_id == "mobaxterm" else [],
        "expected_moba_static_tab_chrome_keys": (
            sorted(EXPECTED_MOBA_STATIC_TAB_CHROME_KEYS) if preset_id == "mobaxterm" else []
        ),
        "expected_moba_tab_chrome_geometry": (
            [geometry.to_dict() for geometry in EXPECTED_MOBA_TAB_CHROME_GEOMETRY]
            if preset_id == "mobaxterm"
            else []
        ),
        "expected_moba_right_utility_keys": sorted(EXPECTED_MOBA_RIGHT_UTILITY_KEYS)
        if preset_id == "mobaxterm"
        else [],
        "expected_moba_right_utility_rail_chrome": (
            {
                "static_width": EXPECTED_MOBA_RIGHT_UTILITY_RAIL_CHROME.static_width,
                "live_width": EXPECTED_MOBA_RIGHT_UTILITY_RAIL_CHROME.live_width,
                "margin_left": EXPECTED_MOBA_RIGHT_UTILITY_RAIL_CHROME.margin_left,
                "margin_top": EXPECTED_MOBA_RIGHT_UTILITY_RAIL_CHROME.margin_top,
                "margin_right": EXPECTED_MOBA_RIGHT_UTILITY_RAIL_CHROME.margin_right,
                "margin_bottom": EXPECTED_MOBA_RIGHT_UTILITY_RAIL_CHROME.margin_bottom,
                "action_spacing": EXPECTED_MOBA_RIGHT_UTILITY_RAIL_CHROME.action_spacing,
                "session_edge_top_y": EXPECTED_MOBA_RIGHT_UTILITY_RAIL_CHROME.session_edge_top_y,
                "session_edge_height": EXPECTED_MOBA_RIGHT_UTILITY_RAIL_CHROME.session_edge_height,
                "session_edge_icon_x": EXPECTED_MOBA_RIGHT_UTILITY_RAIL_CHROME.session_edge_icon_x,
                "session_edge_icon_size": EXPECTED_MOBA_RIGHT_UTILITY_RAIL_CHROME.session_edge_icon_size,
            }
            if preset_id == "mobaxterm"
            else {}
        ),
        "expected_moba_right_utility_actions": (
            [
                {
                    "key": action.key,
                    "icon_key": action.icon_key,
                    "label": action.label,
                    "static_x": action.static_x,
                    "static_y": action.static_y,
                    "static_size": action.static_size,
                    "live_icon_size": action.live_icon_size,
                    "button_size": action.button_size,
                    "render_source": action.render_source,
                }
                for action in EXPECTED_MOBA_RIGHT_UTILITY_ACTIONS
            ]
            if preset_id == "mobaxterm"
            else []
        ),
        "expected_moba_session_edge_actions": (
            [
                {
                    "key": action.key,
                    "icon_key": action.icon_key,
                    "label": action.label,
                    "static_y": action.static_y,
                    "relative_y": action.relative_y(EXPECTED_MOBA_RIGHT_UTILITY_RAIL_CHROME.session_edge_top_y),
                    "static_size": action.static_size,
                    "live_icon_size": action.live_icon_size,
                    "button_size": action.button_size,
                    "render_source": action.render_source,
                }
                for action in EXPECTED_MOBA_SESSION_EDGE_ACTIONS
            ]
            if preset_id == "mobaxterm"
            else []
        ),
        "expected_moba_sftp_action_keys": sorted(EXPECTED_MOBA_SFTP_ACTION_KEYS)
        if preset_id == "mobaxterm"
        else [],
        "expected_moba_sftp_toolbar_groups": (
            [
                {
                    "key": action.key,
                    "group_key": action.group_key,
                    "separator_after": action.separator_after,
                }
                for action in EXPECTED_MOBA_SFTP_ACTIONS
            ]
            if preset_id == "mobaxterm"
            else []
        ),
        "expected_moba_sftp_separator_after_keys": (
            EXPECTED_MOBA_SFTP_SEPARATOR_AFTER_KEYS if preset_id == "mobaxterm" else []
        ),
        "expected_moba_sftp_toolbar_action_geometry": (
            [
                {
                    "key": geometry.key,
                    "button_x": geometry.button_x,
                    "button_y": geometry.button_y,
                    "button_size": geometry.button_size,
                    "icon_x": geometry.icon_x,
                    "icon_y": geometry.icon_y,
                    "icon_size": geometry.icon_size,
                    "separator_after": geometry.separator_after,
                    "separator_x": geometry.separator_x,
                }
                for geometry in EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_GEOMETRY
            ]
            if preset_id == "mobaxterm"
            else []
        ),
        "expected_moba_sftp_file_row_icons": (
            [
                {
                    "kind": row_icon.kind,
                    "icon_key": row_icon.icon_key,
                    "row_kind": row_icon.row_kind,
                    "static_size": row_icon.static_size,
                    "render_source": row_icon.render_source,
                }
                for row_icon in EXPECTED_MOBA_SFTP_FILE_ROW_ICONS
            ]
            if preset_id == "mobaxterm"
            else []
        ),
        "expected_moba_sftp_routed_file_rows": (
            {
                "key": EXPECTED_MOBA_SFTP_ROUTED_FILE_ROWS.key,
                "route_role": EXPECTED_MOBA_SFTP_ROUTED_FILE_ROWS.route_role,
                "follow_route_key": EXPECTED_MOBA_SFTP_ROUTED_FILE_ROWS.follow_route_key,
                "target_table_object": EXPECTED_MOBA_SFTP_ROUTED_FILE_ROWS.target_table_object,
                "row_contract_property": EXPECTED_MOBA_SFTP_ROUTED_FILE_ROWS.row_contract_property,
                "row_route_property": EXPECTED_MOBA_SFTP_ROUTED_FILE_ROWS.row_route_property,
                "row_path_property": EXPECTED_MOBA_SFTP_ROUTED_FILE_ROWS.row_path_property,
                "row_index_property": EXPECTED_MOBA_SFTP_ROUTED_FILE_ROWS.row_index_property,
                "row_selected_property": EXPECTED_MOBA_SFTP_ROUTED_FILE_ROWS.row_selected_property,
                "parent_row_name": EXPECTED_MOBA_SFTP_ROUTED_FILE_ROWS.parent_row_name,
                "selected_row_kind": EXPECTED_MOBA_SFTP_ROUTED_FILE_ROWS.selected_row_kind,
                "render_source": EXPECTED_MOBA_SFTP_ROUTED_FILE_ROWS.render_source,
            }
            if preset_id == "mobaxterm"
            else {}
        ),
        "expected_moba_sftp_browser_chrome": (
            {
                "path_placeholder": EXPECTED_MOBA_SFTP_BROWSER_CHROME.path_placeholder,
                "dropdown_marker": EXPECTED_MOBA_SFTP_BROWSER_CHROME.dropdown_marker,
                "parent_row_label": EXPECTED_MOBA_SFTP_BROWSER_CHROME.parent_row_label,
                "parent_row_kind": EXPECTED_MOBA_SFTP_BROWSER_CHROME.parent_row_kind,
                "selected_row_kind": EXPECTED_MOBA_SFTP_BROWSER_CHROME.selected_row_kind,
                "columns": [
                    {
                        "key": column.key,
                        "label": column.label,
                        "static_x": column.static_x,
                        "static_width": column.static_width,
                    }
                    for column in EXPECTED_MOBA_SFTP_BROWSER_CHROME.columns
                ],
            }
            if preset_id == "mobaxterm"
            else {}
        ),
        "expected_moba_sftp_browser_geometry": (
            EXPECTED_MOBA_SFTP_BROWSER_CHROME.geometry_dict() if preset_id == "mobaxterm" else {}
        ),
        "expected_moba_sftp_dock_layout": (
            {
                "inner_margin": EXPECTED_MOBA_SFTP_DOCK_LAYOUT.inner_margin,
                "toolbar_height": EXPECTED_MOBA_SFTP_DOCK_LAYOUT.toolbar_height,
                "toolbar_icon_size": EXPECTED_MOBA_SFTP_DOCK_LAYOUT.toolbar_icon_size,
                "toolbar_icon_step": EXPECTED_MOBA_SFTP_DOCK_LAYOUT.toolbar_icon_step,
                "toolbar_separator_width": EXPECTED_MOBA_SFTP_DOCK_LAYOUT.toolbar_separator_width,
                "path_height": EXPECTED_MOBA_SFTP_DOCK_LAYOUT.path_height,
                "table_header_height": EXPECTED_MOBA_SFTP_DOCK_LAYOUT.table_header_height,
                "file_row_height": EXPECTED_MOBA_SFTP_DOCK_LAYOUT.file_row_height,
                "static_max_rows": EXPECTED_MOBA_SFTP_DOCK_LAYOUT.static_max_rows,
                "monitoring_height": EXPECTED_MOBA_SFTP_DOCK_LAYOUT.monitoring_height,
                "monitoring_divider_offset": EXPECTED_MOBA_SFTP_DOCK_LAYOUT.monitoring_divider_offset,
            }
            if preset_id == "mobaxterm"
            else {}
        ),
        "expected_moba_terminal_transcript": (
            [line.to_dict() for line in EXPECTED_MOBA_TERMINAL_TRANSCRIPT]
            if preset_id == "mobaxterm"
            else []
        ),
        "expected_moba_terminal_transcript_row_geometry": (
            [
                {
                    "key": row.key,
                    "static_x": row.static_x,
                    "static_y": row.static_y,
                    "row_height": row.row_height,
                    "font_size": row.font_size,
                }
                for row in EXPECTED_MOBA_TERMINAL_TRANSCRIPT_ROW_GEOMETRY
            ]
            if preset_id == "mobaxterm"
            else []
        ),
        "expected_moba_telemetry_cells": (
            [cell.to_dict() for cell in EXPECTED_MOBA_TELEMETRY_CELLS]
            if preset_id == "mobaxterm"
            else []
        ),
        "expected_moba_telemetry_cell_geometry": (
            [geometry.to_dict() for geometry in EXPECTED_MOBA_TELEMETRY_CELL_GEOMETRY]
            if preset_id == "mobaxterm"
            else []
        ),
        "expected_moba_monitoring_metric_keys": sorted(EXPECTED_MOBA_MONITORING_METRIC_KEYS)
        if preset_id == "mobaxterm"
        else [],
        "expected_moba_remote_monitoring_dock_chrome": (
            {
                "title_control_key": EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME.title_control_key,
                "follow_control_key": EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME.follow_control_key,
                "telemetry_surface": EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME.telemetry_surface,
                "visible_metric_keys": list(EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME.visible_metric_keys),
                "refresh_seconds": EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME.refresh_seconds,
                "compact": EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME.compact,
                "static_height": EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME.static_height,
                "divider_offset": EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME.divider_offset,
                "divider_left_inset": EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME.divider_left_inset,
                "divider_right_inset": EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME.divider_right_inset,
                "content_left": EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME.content_left,
                "icon_center_x": EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME.icon_center_x,
                "metric_row_gap": EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME.metric_row_gap,
                "live_controls_width": EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME.live_controls_width,
            }
            if preset_id == "mobaxterm"
            else {}
        ),
        "expected_moba_monitoring_telemetry_route": (
            {
                "key": EXPECTED_MOBA_MONITORING_TELEMETRY_ROUTE.key,
                "route_role": EXPECTED_MOBA_MONITORING_TELEMETRY_ROUTE.route_role,
                "source_panel_object": EXPECTED_MOBA_MONITORING_TELEMETRY_ROUTE.source_panel_object,
                "source_control_key": EXPECTED_MOBA_MONITORING_TELEMETRY_ROUTE.source_control_key,
                "source_metric_keys": list(EXPECTED_MOBA_MONITORING_TELEMETRY_ROUTE.source_metric_keys),
                "visible_dock_metric_keys": list(
                    EXPECTED_MOBA_MONITORING_TELEMETRY_ROUTE.visible_dock_metric_keys
                ),
                "telemetry_surface": EXPECTED_MOBA_MONITORING_TELEMETRY_ROUTE.telemetry_surface,
                "target_bar_object": EXPECTED_MOBA_MONITORING_TELEMETRY_ROUTE.target_bar_object,
                "target_cell_object": EXPECTED_MOBA_MONITORING_TELEMETRY_ROUTE.target_cell_object,
                "target_identity_cell_key": EXPECTED_MOBA_MONITORING_TELEMETRY_ROUTE.target_identity_cell_key,
                "target_metric_cell_keys": list(EXPECTED_MOBA_MONITORING_TELEMETRY_ROUTE.target_metric_cell_keys),
                "render_source": EXPECTED_MOBA_MONITORING_TELEMETRY_ROUTE.render_source,
            }
            if preset_id == "mobaxterm"
            else {}
        ),
        "expected_moba_sftp_follow_folder_route": (
            {
                "key": EXPECTED_MOBA_SFTP_FOLLOW_FOLDER_ROUTE.key,
                "route_role": EXPECTED_MOBA_SFTP_FOLLOW_FOLDER_ROUTE.route_role,
                "source_control_key": EXPECTED_MOBA_SFTP_FOLLOW_FOLDER_ROUTE.source_control_key,
                "source_control_object": EXPECTED_MOBA_SFTP_FOLLOW_FOLDER_ROUTE.source_control_object,
                "source_path_property": EXPECTED_MOBA_SFTP_FOLLOW_FOLDER_ROUTE.source_path_property,
                "source_plan_property": EXPECTED_MOBA_SFTP_FOLLOW_FOLDER_ROUTE.source_plan_property,
                "source_enabled_property": EXPECTED_MOBA_SFTP_FOLLOW_FOLDER_ROUTE.source_enabled_property,
                "target_browser_object": EXPECTED_MOBA_SFTP_FOLLOW_FOLDER_ROUTE.target_browser_object,
                "target_path_object": EXPECTED_MOBA_SFTP_FOLLOW_FOLDER_ROUTE.target_path_object,
                "target_table_object": EXPECTED_MOBA_SFTP_FOLLOW_FOLDER_ROUTE.target_table_object,
                "target_path_property": EXPECTED_MOBA_SFTP_FOLLOW_FOLDER_ROUTE.target_path_property,
                "target_plan_property": EXPECTED_MOBA_SFTP_FOLLOW_FOLDER_ROUTE.target_plan_property,
                "target_enabled_property": EXPECTED_MOBA_SFTP_FOLLOW_FOLDER_ROUTE.target_enabled_property,
                "render_source": EXPECTED_MOBA_SFTP_FOLLOW_FOLDER_ROUTE.render_source,
            }
            if preset_id == "mobaxterm"
            else {}
        ),
        "expected_moba_monitoring_controls": (
            [
                {
                    "key": control.key,
                    "icon_key": control.icon_key,
                    "label": control.label,
                    "control_type": control.control_type,
                    "checked": control.checked,
                }
                for control in EXPECTED_MOBA_MONITORING_CONTROLS
            ]
            if preset_id == "mobaxterm"
            else []
        ),
        "expected_moba_monitoring_control_geometry": (
            [
                {
                    "key": geometry.key,
                    "anchor_x": geometry.anchor_x,
                    "static_y": geometry.static_y,
                    "icon_x": geometry.icon_x,
                    "icon_size": geometry.icon_size,
                    "label_x": geometry.label_x,
                    "label_y_offset": geometry.label_y_offset,
                    "label_font_size": geometry.label_font_size,
                    "label_bold": geometry.label_bold,
                    "check_size": geometry.check_size,
                    "check_y_offset": geometry.check_y_offset,
                    "checkmark_points": [list(point) for point in geometry.checkmark_points],
                    "row_height": geometry.row_height,
                    "live_width": geometry.live_width,
                }
                for geometry in EXPECTED_MOBA_MONITORING_CONTROL_GEOMETRY
            ]
            if preset_id == "mobaxterm"
            else []
        ),
        "expected_moba_status_keys": sorted(EXPECTED_MOBA_STATUS_KEYS) if preset_id == "mobaxterm" else [],
        "expected_moba_status_chrome": (
            {
                "notice": EXPECTED_MOBA_STATUS_CHROME.notice,
                "product_note": EXPECTED_MOBA_STATUS_CHROME.product_note,
                "right_marker": EXPECTED_MOBA_STATUS_CHROME.right_marker,
                "static_height": EXPECTED_MOBA_STATUS_CHROME.static_height,
                "notice_x": EXPECTED_MOBA_STATUS_CHROME.notice_x,
                "notice_y": EXPECTED_MOBA_STATUS_CHROME.notice_y,
                "product_note_x": EXPECTED_MOBA_STATUS_CHROME.product_note_x,
                "product_note_y": EXPECTED_MOBA_STATUS_CHROME.product_note_y,
                "text_font_size": EXPECTED_MOBA_STATUS_CHROME.text_font_size,
                "segment_start_right_offset": EXPECTED_MOBA_STATUS_CHROME.segment_start_right_offset,
                "marker_right_inset": EXPECTED_MOBA_STATUS_CHROME.marker_right_inset,
                "marker_y": EXPECTED_MOBA_STATUS_CHROME.marker_y,
                "marker_width": EXPECTED_MOBA_STATUS_CHROME.marker_width,
                "marker_height": EXPECTED_MOBA_STATUS_CHROME.marker_height,
            }
            if preset_id == "mobaxterm"
            else {}
        ),
        "expected_moba_bottom_edge_controls": (
            [
                {
                    "key": control.key,
                    "icon_key": control.icon_key,
                    "label": control.label,
                    "static_x": control.static_x,
                }
                for control in EXPECTED_MOBA_BOTTOM_EDGE_CONTROLS
            ]
            if preset_id == "mobaxterm"
            else []
        ),
        "expected_moba_ssh_banner_chrome": (
            {
                "title": EXPECTED_MOBA_SSH_BANNER_CHROME.title,
                "subtitle": EXPECTED_MOBA_SSH_BANNER_CHROME.subtitle,
                "heading_prefix": EXPECTED_MOBA_SSH_BANNER_CHROME.heading_prefix,
                "heading_suffix": EXPECTED_MOBA_SSH_BANNER_CHROME.heading_suffix,
                "target_intro": EXPECTED_MOBA_SSH_BANNER_CHROME.target_intro,
                "capability_label_width": EXPECTED_MOBA_SSH_BANNER_CHROME.capability_label_width,
                "footer_prefix": EXPECTED_MOBA_SSH_BANNER_CHROME.footer_prefix,
                "static_left_offset": EXPECTED_MOBA_SSH_BANNER_CHROME.static_left_offset,
                "static_top_offset": EXPECTED_MOBA_SSH_BANNER_CHROME.static_top_offset,
                "static_width": EXPECTED_MOBA_SSH_BANNER_CHROME.static_width,
                "static_height": EXPECTED_MOBA_SSH_BANNER_CHROME.static_height,
                "body_top_offset": EXPECTED_MOBA_SSH_BANNER_CHROME.body_top_offset,
                "terminal_gap": EXPECTED_MOBA_SSH_BANNER_CHROME.terminal_gap,
            }
            if preset_id == "mobaxterm"
            else {}
        ),
        "expected_moba_ssh_banner_row_geometry": (
            [
                {
                    "key": geometry.key,
                    "object_name": geometry.object_name,
                    "static_x": geometry.static_x,
                    "static_y": geometry.static_y,
                    "static_width": geometry.static_width,
                    "static_height": geometry.static_height,
                    "centered": geometry.centered,
                }
                for geometry in EXPECTED_MOBA_SSH_BANNER_ROW_GEOMETRY
            ]
            if preset_id == "mobaxterm"
            else []
        ),
        "expected_moba_ssh_banner_capability_card": (
            {
                "target": EXPECTED_MOBA_SSH_BANNER.title,
                "capabilities": [row.to_dict() for row in EXPECTED_MOBA_SSH_BANNER_CAPABILITIES],
                "footer_links": EXPECTED_MOBA_SSH_BANNER_FOOTER_LINKS,
            }
            if preset_id == "mobaxterm"
            else {}
        ),
        "expected_workflow_card_titles": []
        if preset_id == "mobaxterm"
        else [card.title for card in gui_design_workflow_cards(preset_id)],
        "expected_workspace_surface_texts": workspace_texts,
        "expected_reference_state_texts": reference_texts,
        "expected_reference_status_segments": list(gui_design_reference_state(preset_id).status_segments),
        "expected_securecrt_top_chrome": (
            {
                "window_title": EXPECTED_SECURECRT_TOP_CHROME.window_title,
                "menu_height": EXPECTED_SECURECRT_TOP_CHROME.menu_height,
                "toolbar_height": EXPECTED_SECURECRT_TOP_CHROME.toolbar_height,
                "menu_items": [
                    {"key": item.key, "label": item.label, "primary_action": item.primary_action}
                    for item in EXPECTED_SECURECRT_TOP_CHROME.menu_items
                ],
                "toolbar_actions": [
                    {
                        "key": action.key,
                        "icon_key": action.icon_key,
                        "label": action.label,
                        "static_x": action.static_x,
                        "static_width": action.static_width,
                    }
                    for action in EXPECTED_SECURECRT_TOP_CHROME.toolbar_actions
                ],
            }
            if preset_id == "securecrt"
            else {}
        ),
        "expected_securecrt_session_manager_chrome": (
            {
                "title": EXPECTED_SECURECRT_SESSION_MANAGER_CHROME.title,
                "filter_placeholder": EXPECTED_SECURECRT_SESSION_MANAGER_CHROME.filter_placeholder,
                "static_title_x": EXPECTED_SECURECRT_SESSION_MANAGER_CHROME.static_title_x,
                "static_title_y": EXPECTED_SECURECRT_SESSION_MANAGER_CHROME.static_title_y,
                "static_filter_y": EXPECTED_SECURECRT_SESSION_MANAGER_CHROME.static_filter_y,
                "static_filter_x_margin": EXPECTED_SECURECRT_SESSION_MANAGER_CHROME.static_filter_x_margin,
                "static_filter_height": EXPECTED_SECURECRT_SESSION_MANAGER_CHROME.static_filter_height,
                "static_filter_placeholder_x": (
                    EXPECTED_SECURECRT_SESSION_MANAGER_CHROME.static_filter_placeholder_x
                ),
                "static_filter_placeholder_y": (
                    EXPECTED_SECURECRT_SESSION_MANAGER_CHROME.static_filter_placeholder_y
                ),
                "live_max_height": EXPECTED_SECURECRT_SESSION_MANAGER_CHROME.live_max_height,
                "live_spacing": EXPECTED_SECURECRT_SESSION_MANAGER_CHROME.live_spacing,
                "live_title_spacing": EXPECTED_SECURECRT_SESSION_MANAGER_CHROME.live_title_spacing,
                "live_filter_height": EXPECTED_SECURECRT_SESSION_MANAGER_CHROME.live_filter_height,
                "actions": [
                    {
                        "key": action.key,
                        "icon_key": action.icon_key,
                        "label": action.label,
                        "static_x": action.static_x,
                        "static_y": action.static_y,
                        "static_button_size": action.static_button_size,
                        "static_icon_x": action.static_icon_x,
                        "static_icon_y": action.static_icon_y,
                        "static_icon_size": action.static_icon_size,
                        "live_icon_size": action.live_icon_size,
                        "live_button_size": action.live_button_size,
                        "render_source": action.render_source,
                    }
                    for action in EXPECTED_SECURECRT_SESSION_MANAGER_CHROME.actions
                ],
            }
            if preset_id == "securecrt"
            else {}
        ),
        "expected_securecrt_session_manager_route": (
            {
                "key": EXPECTED_SECURECRT_SESSION_MANAGER_ROUTE.key,
                "route_role": EXPECTED_SECURECRT_SESSION_MANAGER_ROUTE.route_role,
                "selected_profile_name": EXPECTED_SECURECRT_SESSION_MANAGER_ROUTE.selected_profile_name,
                "selected_tree_label": EXPECTED_SECURECRT_SESSION_MANAGER_ROUTE.selected_tree_label,
                "selected_tree_object": EXPECTED_SECURECRT_SESSION_MANAGER_ROUTE.selected_tree_object,
                "session_manager_object": EXPECTED_SECURECRT_SESSION_MANAGER_ROUTE.session_manager_object,
                "session_manager_action_key": EXPECTED_SECURECRT_SESSION_MANAGER_ROUTE.session_manager_action_key,
                "session_manager_action_object": (
                    EXPECTED_SECURECRT_SESSION_MANAGER_ROUTE.session_manager_action_object
                ),
                "status_strip_object": EXPECTED_SECURECRT_SESSION_MANAGER_ROUTE.status_strip_object,
                "status_field_key": EXPECTED_SECURECRT_SESSION_MANAGER_ROUTE.status_field_key,
                "status_field_object": EXPECTED_SECURECRT_SESSION_MANAGER_ROUTE.status_field_object,
                "active_tab_label": EXPECTED_SECURECRT_SESSION_MANAGER_ROUTE.active_tab_label,
                "target_value": EXPECTED_SECURECRT_SESSION_MANAGER_ROUTE.target_value,
                "protocol_value": EXPECTED_SECURECRT_SESSION_MANAGER_ROUTE.protocol_value,
                "session_value": EXPECTED_SECURECRT_SESSION_MANAGER_ROUTE.session_value,
                "selected_tree_property": EXPECTED_SECURECRT_SESSION_MANAGER_ROUTE.selected_tree_property,
                "action_active_property": EXPECTED_SECURECRT_SESSION_MANAGER_ROUTE.action_active_property,
                "tab_label_property": EXPECTED_SECURECRT_SESSION_MANAGER_ROUTE.tab_label_property,
                "status_value_property": EXPECTED_SECURECRT_SESSION_MANAGER_ROUTE.status_value_property,
                "render_source": EXPECTED_SECURECRT_SESSION_MANAGER_ROUTE.render_source,
            }
            if preset_id == "securecrt"
            else {}
        ),
        "expected_securecrt_tree_icons": (
            product_tree_icon_summary("securecrt")
            if preset_id == "securecrt"
            else []
        ),
        "expected_securecrt_command_window": (
            {
                "key": EXPECTED_SECURECRT_COMMAND_WINDOW_CHROME.key,
                "title": EXPECTED_SECURECRT_COMMAND_WINDOW_CHROME.title,
                "target_scope": EXPECTED_SECURECRT_COMMAND_WINDOW_CHROME.target_scope,
                "command": EXPECTED_SECURECRT_COMMAND_WINDOW_CHROME.command,
                "send_label": EXPECTED_SECURECRT_COMMAND_WINDOW_CHROME.send_label,
                "status": EXPECTED_SECURECRT_COMMAND_WINDOW_CHROME.status,
                "static_header_height": EXPECTED_SECURECRT_COMMAND_WINDOW_CHROME.static_header_height,
                "static_control_y": EXPECTED_SECURECRT_COMMAND_WINDOW_CHROME.static_control_y,
                "static_target_width": EXPECTED_SECURECRT_COMMAND_WINDOW_CHROME.static_target_width,
                "static_input_x": EXPECTED_SECURECRT_COMMAND_WINDOW_CHROME.static_input_x,
                "static_input_text_x": EXPECTED_SECURECRT_COMMAND_WINDOW_CHROME.static_input_text_x,
                "static_input_text_y": EXPECTED_SECURECRT_COMMAND_WINDOW_CHROME.static_input_text_y,
                "static_send_width": EXPECTED_SECURECRT_COMMAND_WINDOW_CHROME.static_send_width,
                "static_send_right_margin": EXPECTED_SECURECRT_COMMAND_WINDOW_CHROME.static_send_right_margin,
                "live_target_min_width": EXPECTED_SECURECRT_COMMAND_WINDOW_CHROME.live_target_min_width,
                "live_send_min_width": EXPECTED_SECURECRT_COMMAND_WINDOW_CHROME.live_send_min_width,
            }
            if preset_id == "securecrt"
            else {}
        ),
        "expected_securecrt_command_window_send_route": (
            {
                "key": EXPECTED_SECURECRT_COMMAND_WINDOW_SEND_ROUTE.key,
                "route_role": EXPECTED_SECURECRT_COMMAND_WINDOW_SEND_ROUTE.route_role,
                "source_window_object": EXPECTED_SECURECRT_COMMAND_WINDOW_SEND_ROUTE.source_window_object,
                "target_scope_object": EXPECTED_SECURECRT_COMMAND_WINDOW_SEND_ROUTE.target_scope_object,
                "command_input_object": EXPECTED_SECURECRT_COMMAND_WINDOW_SEND_ROUTE.command_input_object,
                "send_control_object": EXPECTED_SECURECRT_COMMAND_WINDOW_SEND_ROUTE.send_control_object,
                "status_object": EXPECTED_SECURECRT_COMMAND_WINDOW_SEND_ROUTE.status_object,
                "command_property": EXPECTED_SECURECRT_COMMAND_WINDOW_SEND_ROUTE.command_property,
                "target_scope_property": EXPECTED_SECURECRT_COMMAND_WINDOW_SEND_ROUTE.target_scope_property,
                "send_label_property": EXPECTED_SECURECRT_COMMAND_WINDOW_SEND_ROUTE.send_label_property,
                "status_property": EXPECTED_SECURECRT_COMMAND_WINDOW_SEND_ROUTE.status_property,
                "render_source": EXPECTED_SECURECRT_COMMAND_WINDOW_SEND_ROUTE.render_source,
            }
            if preset_id == "securecrt"
            else {}
        ),
        "expected_securecrt_session_status_strip": (
            {
                "title": EXPECTED_SECURECRT_SESSION_STATUS_STRIP.title,
                "title_width": EXPECTED_SECURECRT_SESSION_STATUS_STRIP.title_width,
                "static_title_x": EXPECTED_SECURECRT_SESSION_STATUS_STRIP.static_title_x,
                "static_title_y": EXPECTED_SECURECRT_SESSION_STATUS_STRIP.static_title_y,
                "static_cell_start_x": EXPECTED_SECURECRT_SESSION_STATUS_STRIP.static_cell_start_x,
                "static_cell_gap": EXPECTED_SECURECRT_SESSION_STATUS_STRIP.static_cell_gap,
                "live_spacing": EXPECTED_SECURECRT_SESSION_STATUS_STRIP.live_spacing,
                "fields": [
                    {
                        "key": field.key,
                        "label": field.label,
                        "value": field.value,
                        "static_width": field.static_width,
                        "role": field.role,
                        "static_y": field.static_y,
                        "static_height": field.static_height,
                        "static_label_x": field.static_label_x,
                        "static_label_y": field.static_label_y,
                        "static_value_x": field.static_value_x,
                        "static_value_y": field.static_value_y,
                        "live_min_width": field.live_min_width,
                        "live_cell_height": field.live_cell_height,
                    }
                    for field in EXPECTED_SECURECRT_SESSION_STATUS_STRIP.fields
                ],
            }
            if preset_id == "securecrt"
            else {}
        ),
        "expected_remmina_viewer_controls": (
            [
                {
                    "key": control.key,
                    "icon_key": control.icon_key,
                    "label": control.label,
                    "static_width": control.static_width,
                    "static_step": control.static_step,
                    "static_y": control.static_y,
                    "static_height": control.static_height,
                    "static_icon_x": control.static_icon_x,
                    "static_icon_size": control.static_icon_size,
                    "static_label_x": control.static_label_x,
                    "live_icon_size": control.live_icon_size,
                    "live_min_width": control.live_min_width,
                    "live_button_height": control.live_button_height,
                    "render_source": control.render_source,
                }
                for control in gui_design_remmina_viewer_controls()
            ]
            if preset_id == "remmina"
            else []
        ),
        "expected_remmina_profile_list_chrome": (
            {
                "title": EXPECTED_REMMINA_PROFILE_LIST_CHROME.title,
                "filter_placeholder": EXPECTED_REMMINA_PROFILE_LIST_CHROME.filter_placeholder,
                "static_filter_x": EXPECTED_REMMINA_PROFILE_LIST_CHROME.static_filter_x,
                "static_filter_y": EXPECTED_REMMINA_PROFILE_LIST_CHROME.static_filter_y,
                "static_filter_height": EXPECTED_REMMINA_PROFILE_LIST_CHROME.static_filter_height,
                "static_header_y": EXPECTED_REMMINA_PROFILE_LIST_CHROME.static_header_y,
                "static_row_start_y": EXPECTED_REMMINA_PROFILE_LIST_CHROME.static_row_start_y,
                "static_row_height": EXPECTED_REMMINA_PROFILE_LIST_CHROME.static_row_height,
                "static_row_step": EXPECTED_REMMINA_PROFILE_LIST_CHROME.static_row_step,
                "static_cell_start_x": EXPECTED_REMMINA_PROFILE_LIST_CHROME.static_cell_start_x,
                "static_cell_y": EXPECTED_REMMINA_PROFILE_LIST_CHROME.static_cell_y,
                "static_status_y": EXPECTED_REMMINA_PROFILE_LIST_CHROME.static_status_y,
                "live_max_height": EXPECTED_REMMINA_PROFILE_LIST_CHROME.live_max_height,
                "live_filter_width": EXPECTED_REMMINA_PROFILE_LIST_CHROME.live_filter_width,
                "live_row_min_height": EXPECTED_REMMINA_PROFILE_LIST_CHROME.live_row_min_height,
                "columns": [
                    {
                        "key": column.key,
                        "label": column.label,
                        "static_width": column.static_width,
                        "live_min_width": column.live_min_width,
                    }
                    for column in EXPECTED_REMMINA_PROFILE_LIST_CHROME.columns
                ],
                "rows": [
                    {
                        "key": row.key,
                        "name": row.name,
                        "protocol": row.protocol,
                        "server": row.server,
                        "status": row.status,
                        "selected": row.selected,
                    }
                    for row in EXPECTED_REMMINA_PROFILE_LIST_CHROME.rows
                ],
            }
            if preset_id == "remmina"
            else {}
        ),
        "expected_remmina_profile_viewer_route": (
            {
                "key": EXPECTED_REMMINA_PROFILE_VIEWER_ROUTE.key,
                "route_role": EXPECTED_REMMINA_PROFILE_VIEWER_ROUTE.route_role,
                "selected_profile_key": EXPECTED_REMMINA_PROFILE_VIEWER_ROUTE.selected_profile_key,
                "selected_profile_object": EXPECTED_REMMINA_PROFILE_VIEWER_ROUTE.selected_profile_object,
                "viewer_controls_object": EXPECTED_REMMINA_PROFILE_VIEWER_ROUTE.viewer_controls_object,
                "viewer_control_key": EXPECTED_REMMINA_PROFILE_VIEWER_ROUTE.viewer_control_key,
                "viewer_control_object": EXPECTED_REMMINA_PROFILE_VIEWER_ROUTE.viewer_control_object,
                "active_tab_label": EXPECTED_REMMINA_PROFILE_VIEWER_ROUTE.active_tab_label,
                "protocol": EXPECTED_REMMINA_PROFILE_VIEWER_ROUTE.protocol,
                "profile_status": EXPECTED_REMMINA_PROFILE_VIEWER_ROUTE.profile_status,
                "selected_row_property": EXPECTED_REMMINA_PROFILE_VIEWER_ROUTE.selected_row_property,
                "control_active_property": EXPECTED_REMMINA_PROFILE_VIEWER_ROUTE.control_active_property,
                "tab_label_property": EXPECTED_REMMINA_PROFILE_VIEWER_ROUTE.tab_label_property,
                "render_source": EXPECTED_REMMINA_PROFILE_VIEWER_ROUTE.render_source,
            }
            if preset_id == "remmina"
            else {}
        ),
        "expected_remmina_clipboard_route": (
            {
                "key": EXPECTED_REMMINA_CLIPBOARD_ROUTE.key,
                "route_role": EXPECTED_REMMINA_CLIPBOARD_ROUTE.route_role,
                "viewer_controls_object": EXPECTED_REMMINA_CLIPBOARD_ROUTE.viewer_controls_object,
                "viewer_control_key": EXPECTED_REMMINA_CLIPBOARD_ROUTE.viewer_control_key,
                "viewer_control_object": EXPECTED_REMMINA_CLIPBOARD_ROUTE.viewer_control_object,
                "active_tab_label": EXPECTED_REMMINA_CLIPBOARD_ROUTE.active_tab_label,
                "protocol": EXPECTED_REMMINA_CLIPBOARD_ROUTE.protocol,
                "clipboard_state": EXPECTED_REMMINA_CLIPBOARD_ROUTE.clipboard_state,
                "status_segment": EXPECTED_REMMINA_CLIPBOARD_ROUTE.status_segment,
                "detail_line": EXPECTED_REMMINA_CLIPBOARD_ROUTE.detail_line,
                "activity_line": EXPECTED_REMMINA_CLIPBOARD_ROUTE.activity_line,
                "control_active_property": EXPECTED_REMMINA_CLIPBOARD_ROUTE.control_active_property,
                "tab_label_property": EXPECTED_REMMINA_CLIPBOARD_ROUTE.tab_label_property,
                "clipboard_state_property": EXPECTED_REMMINA_CLIPBOARD_ROUTE.clipboard_state_property,
                "render_source": EXPECTED_REMMINA_CLIPBOARD_ROUTE.render_source,
            }
            if preset_id == "remmina"
            else {}
        ),
        "expected_termius_header_chips": (
            [
                {
                    "key": chip.key,
                    "label": chip.label,
                }
                for chip in gui_design_termius_header_chips()
            ]
            if preset_id == "termius"
            else []
        ),
        "expected_termius_hosts_chrome": (
            {
                "title": EXPECTED_TERMIUS_HOSTS_CHROME.title,
                "filter_placeholder": EXPECTED_TERMIUS_HOSTS_CHROME.filter_placeholder,
                "actions": [
                    {
                        "key": action.key,
                        "icon_key": action.icon_key,
                        "label": action.label,
                        "static_x": action.static_x,
                    }
                    for action in EXPECTED_TERMIUS_HOSTS_CHROME.actions
                ],
            }
            if preset_id == "termius"
            else {}
        ),
        "expected_termius_host_identity_strip": (
            {
                "title": EXPECTED_TERMIUS_HOST_IDENTITY_STRIP.title,
                "title_width": EXPECTED_TERMIUS_HOST_IDENTITY_STRIP.title_width,
                "static_title_x": EXPECTED_TERMIUS_HOST_IDENTITY_STRIP.static_title_x,
                "static_title_y": EXPECTED_TERMIUS_HOST_IDENTITY_STRIP.static_title_y,
                "static_cell_start_x": EXPECTED_TERMIUS_HOST_IDENTITY_STRIP.static_cell_start_x,
                "static_cell_gap": EXPECTED_TERMIUS_HOST_IDENTITY_STRIP.static_cell_gap,
                "live_spacing": EXPECTED_TERMIUS_HOST_IDENTITY_STRIP.live_spacing,
                "fields": [
                    {
                        "key": field.key,
                        "label": field.label,
                        "value": field.value,
                        "static_width": field.static_width,
                        "role": field.role,
                        "static_y": field.static_y,
                        "static_height": field.static_height,
                        "static_label_x": field.static_label_x,
                        "static_label_y": field.static_label_y,
                        "static_value_x": field.static_value_x,
                        "static_value_y": field.static_value_y,
                        "live_min_width": field.live_min_width,
                        "live_cell_height": field.live_cell_height,
                    }
                    for field in EXPECTED_TERMIUS_HOST_IDENTITY_STRIP.fields
                ],
            }
            if preset_id == "termius"
            else {}
        ),
        "expected_termius_host_selection_route": (
            {
                "key": EXPECTED_TERMIUS_HOST_SELECTION_ROUTE.key,
                "route_role": EXPECTED_TERMIUS_HOST_SELECTION_ROUTE.route_role,
                "selected_profile_name": EXPECTED_TERMIUS_HOST_SELECTION_ROUTE.selected_profile_name,
                "selected_tree_label": EXPECTED_TERMIUS_HOST_SELECTION_ROUTE.selected_tree_label,
                "selected_tree_object": EXPECTED_TERMIUS_HOST_SELECTION_ROUTE.selected_tree_object,
                "hosts_panel_object": EXPECTED_TERMIUS_HOST_SELECTION_ROUTE.hosts_panel_object,
                "host_identity_object": EXPECTED_TERMIUS_HOST_SELECTION_ROUTE.host_identity_object,
                "identity_field_key": EXPECTED_TERMIUS_HOST_SELECTION_ROUTE.identity_field_key,
                "identity_cell_object": EXPECTED_TERMIUS_HOST_SELECTION_ROUTE.identity_cell_object,
                "active_tab_label": EXPECTED_TERMIUS_HOST_SELECTION_ROUTE.active_tab_label,
                "target_value": EXPECTED_TERMIUS_HOST_SELECTION_ROUTE.target_value,
                "protocol_value": EXPECTED_TERMIUS_HOST_SELECTION_ROUTE.protocol_value,
                "host_value": EXPECTED_TERMIUS_HOST_SELECTION_ROUTE.host_value,
                "selected_tree_property": EXPECTED_TERMIUS_HOST_SELECTION_ROUTE.selected_tree_property,
                "tab_label_property": EXPECTED_TERMIUS_HOST_SELECTION_ROUTE.tab_label_property,
                "identity_value_property": EXPECTED_TERMIUS_HOST_SELECTION_ROUTE.identity_value_property,
                "render_source": EXPECTED_TERMIUS_HOST_SELECTION_ROUTE.render_source,
            }
            if preset_id == "termius"
            else {}
        ),
        "expected_termius_sync_route": (
            {
                "key": EXPECTED_TERMIUS_SYNC_ROUTE.key,
                "route_role": EXPECTED_TERMIUS_SYNC_ROUTE.route_role,
                "hosts_action_key": EXPECTED_TERMIUS_SYNC_ROUTE.hosts_action_key,
                "hosts_action_object": EXPECTED_TERMIUS_SYNC_ROUTE.hosts_action_object,
                "header_chip_key": EXPECTED_TERMIUS_SYNC_ROUTE.header_chip_key,
                "header_chip_object": EXPECTED_TERMIUS_SYNC_ROUTE.header_chip_object,
                "identity_field_key": EXPECTED_TERMIUS_SYNC_ROUTE.identity_field_key,
                "identity_cell_object": EXPECTED_TERMIUS_SYNC_ROUTE.identity_cell_object,
                "sync_state": EXPECTED_TERMIUS_SYNC_ROUTE.sync_state,
                "action_label_property": EXPECTED_TERMIUS_SYNC_ROUTE.action_label_property,
                "chip_label_property": EXPECTED_TERMIUS_SYNC_ROUTE.chip_label_property,
                "identity_value_property": EXPECTED_TERMIUS_SYNC_ROUTE.identity_value_property,
                "status_property": EXPECTED_TERMIUS_SYNC_ROUTE.status_property,
                "render_source": EXPECTED_TERMIUS_SYNC_ROUTE.render_source,
            }
            if preset_id == "termius"
            else {}
        ),
        "expected_mremoteng_top_chrome": (
            {
                "window_title": EXPECTED_MREMOTENG_TOP_CHROME.window_title,
                "menu_height": EXPECTED_MREMOTENG_TOP_CHROME.menu_height,
                "toolbar_height": EXPECTED_MREMOTENG_TOP_CHROME.toolbar_height,
                "menu_items": [
                    {"key": item.key, "label": item.label, "primary_action": item.primary_action}
                    for item in EXPECTED_MREMOTENG_TOP_CHROME.menu_items
                ],
                "toolbar_actions": [
                    {
                        "key": action.key,
                        "icon_key": action.icon_key,
                        "label": action.label,
                        "static_x": action.static_x,
                        "static_width": action.static_width,
                    }
                    for action in EXPECTED_MREMOTENG_TOP_CHROME.toolbar_actions
                ],
            }
            if preset_id == "mremoteng"
            else {}
        ),
        "expected_mremoteng_document_controls": (
            {
                "title": EXPECTED_MREMOTENG_DOCUMENT_TOOLBAR_CHROME.title,
                "filter_placeholder": EXPECTED_MREMOTENG_DOCUMENT_TOOLBAR_CHROME.filter_placeholder,
                "title_width": EXPECTED_MREMOTENG_DOCUMENT_TOOLBAR_CHROME.title_width,
                "static_height": EXPECTED_MREMOTENG_DOCUMENT_TOOLBAR_CHROME.static_height,
                "static_button_start_x": EXPECTED_MREMOTENG_DOCUMENT_TOOLBAR_CHROME.static_button_start_x,
                "static_button_gap": EXPECTED_MREMOTENG_DOCUMENT_TOOLBAR_CHROME.static_button_gap,
                "static_filter_width": EXPECTED_MREMOTENG_DOCUMENT_TOOLBAR_CHROME.static_filter_width,
                "static_filter_y": EXPECTED_MREMOTENG_DOCUMENT_TOOLBAR_CHROME.static_filter_y,
                "static_filter_height": EXPECTED_MREMOTENG_DOCUMENT_TOOLBAR_CHROME.static_filter_height,
                "live_filter_width": EXPECTED_MREMOTENG_DOCUMENT_TOOLBAR_CHROME.live_filter_width,
                "live_filter_height": EXPECTED_MREMOTENG_DOCUMENT_TOOLBAR_CHROME.live_filter_height,
                "controls": [
                    {
                        "key": control.key,
                        "icon_key": control.icon_key,
                        "label": control.label,
                        "static_width": control.static_width,
                        "static_y": control.static_y,
                        "static_height": control.static_height,
                        "static_icon_x": control.static_icon_x,
                        "static_icon_y": control.static_icon_y,
                        "static_icon_size": control.static_icon_size,
                        "static_label_x": control.static_label_x,
                        "static_label_y": control.static_label_y,
                        "live_icon_size": control.live_icon_size,
                        "live_min_width": control.live_min_width,
                        "live_button_height": control.live_button_height,
                        "render_source": control.render_source,
                    }
                    for control in gui_design_mremoteng_document_controls()
                ],
            }
            if preset_id == "mremoteng"
            else {}
        ),
        "expected_mremoteng_property_grid": (
            {
                "title": EXPECTED_MREMOTENG_PROPERTY_GRID_CHROME.title,
                "scope_label": EXPECTED_MREMOTENG_PROPERTY_GRID_CHROME.scope_label,
                "inheritance_label": EXPECTED_MREMOTENG_PROPERTY_GRID_CHROME.inheritance_label,
                "columns": [
                    {
                        "key": column.key,
                        "label": column.label,
                        "static_width": column.static_width,
                    }
                    for column in EXPECTED_MREMOTENG_PROPERTY_GRID_CHROME.columns
                ],
                "rows": [
                    {
                        "key": row.key,
                        "property_label": row.property_label,
                        "inherited_from": row.inherited_from,
                        "effective_value": row.effective_value,
                        "source": row.source,
                        "inherited": row.inherited,
                    }
                    for row in EXPECTED_MREMOTENG_PROPERTY_GRID_CHROME.rows
                ],
            }
            if preset_id == "mremoteng"
            else {}
        ),
        "expected_mremoteng_connection_document_route": (
            {
                "key": EXPECTED_MREMOTENG_CONNECTION_DOCUMENT_ROUTE.key,
                "route_role": EXPECTED_MREMOTENG_CONNECTION_DOCUMENT_ROUTE.route_role,
                "selected_profile_name": EXPECTED_MREMOTENG_CONNECTION_DOCUMENT_ROUTE.selected_profile_name,
                "selected_tree_label": EXPECTED_MREMOTENG_CONNECTION_DOCUMENT_ROUTE.selected_tree_label,
                "selected_tree_object": EXPECTED_MREMOTENG_CONNECTION_DOCUMENT_ROUTE.selected_tree_object,
                "document_controls_object": EXPECTED_MREMOTENG_CONNECTION_DOCUMENT_ROUTE.document_controls_object,
                "document_control_key": EXPECTED_MREMOTENG_CONNECTION_DOCUMENT_ROUTE.document_control_key,
                "document_control_object": EXPECTED_MREMOTENG_CONNECTION_DOCUMENT_ROUTE.document_control_object,
                "property_grid_object": EXPECTED_MREMOTENG_CONNECTION_DOCUMENT_ROUTE.property_grid_object,
                "property_row_key": EXPECTED_MREMOTENG_CONNECTION_DOCUMENT_ROUTE.property_row_key,
                "property_cell_object": EXPECTED_MREMOTENG_CONNECTION_DOCUMENT_ROUTE.property_cell_object,
                "active_tab_label": EXPECTED_MREMOTENG_CONNECTION_DOCUMENT_ROUTE.active_tab_label,
                "protocol": EXPECTED_MREMOTENG_CONNECTION_DOCUMENT_ROUTE.protocol,
                "workspace_state": EXPECTED_MREMOTENG_CONNECTION_DOCUMENT_ROUTE.workspace_state,
                "property_value": EXPECTED_MREMOTENG_CONNECTION_DOCUMENT_ROUTE.property_value,
                "selected_tree_property": EXPECTED_MREMOTENG_CONNECTION_DOCUMENT_ROUTE.selected_tree_property,
                "control_active_property": EXPECTED_MREMOTENG_CONNECTION_DOCUMENT_ROUTE.control_active_property,
                "tab_label_property": EXPECTED_MREMOTENG_CONNECTION_DOCUMENT_ROUTE.tab_label_property,
                "property_value_property": EXPECTED_MREMOTENG_CONNECTION_DOCUMENT_ROUTE.property_value_property,
                "render_source": EXPECTED_MREMOTENG_CONNECTION_DOCUMENT_ROUTE.render_source,
            }
            if preset_id == "mremoteng"
            else {}
        ),
        "layout_contract_count": len(layout_contracts),
        "layout_contract_ids": [str(contract["id"]) for contract in layout_contracts],
        "layout_contract_widgets": [str(contract["object_name"]) for contract in layout_contracts],
        "topology_contract_count": len(topology_contracts),
        "topology_contract_ids": [str(contract["id"]) for contract in topology_contracts],
        "topology_contract_widgets": [
            [str(contract["from"]), str(contract["to"])] for contract in topology_contracts
        ],
    }


def live_contract_summaries_for_presets(preset_ids: list[str]) -> dict[str, dict[str, object]]:
    return {preset_id: live_contract_summary_for_preset(preset_id) for preset_id in preset_ids}


def check_label_text(window: Any, object_name: str, expected: str, preset_id: str) -> list[str]:
    from PyQt6.QtWidgets import QLabel

    label = window.findChild(QLabel, object_name)
    if label is None:
        return [f"{preset_id} live GUI missing label: {object_name}"]
    if label.text() != expected:
        return [f"{preset_id} live GUI {object_name} text {label.text()!r} must equal {expected!r}"]
    return []


def check_live_interaction_state(window: Any, preset_id: str) -> list[str]:
    from PyQt6.QtWidgets import QLineEdit, QTabWidget, QToolButton, QTreeWidget

    state = gui_design_interaction_state(preset_id)
    errors: list[str] = []
    buttons = {button.text().strip(): button for button in window.findChildren(QToolButton)}
    for key, expected_state in [
        (state.active_toolbar_key, "active"),
        (state.checked_toolbar_key, "checked"),
        (state.disabled_toolbar_key, "disabled"),
    ]:
        label = interaction_label_for_key(preset_id, key)
        button = buttons.get(label)
        if button is None:
            errors.append(f"{preset_id} live GUI interaction button missing: {label}")
            continue
        actual = str(button.property("interactionState") or "")
        if actual != expected_state:
            errors.append(
                f"{preset_id} live GUI {label} interactionState {actual!r} must equal {expected_state!r}"
            )

    focus_widgets = {
        "quick-connect": "quickConnect",
        "search-log": "toolbarSearch",
        "session-filter": "secureCrtSessionFilter",
        "host-search": "termiusHostSearch",
        "profile-filter": "remminaProfileFilter",
        "tree-filter": "mRemoteNgDocumentFilter",
    }
    focus_object = focus_widgets.get(state.focused_control)
    if focus_object is not None:
        focused = window.findChild(QLineEdit, focus_object)
        if focused is None:
            errors.append(f"{preset_id} live GUI focused control missing: {focus_object}")
        elif str(focused.property("interactionState") or "") != "focused":
            errors.append(f"{preset_id} live GUI {focus_object} must have focused interactionState")
    tabs = window.findChild(QTabWidget, "sessionTabs")
    if tabs is None:
        errors.append(f"{preset_id} live GUI missing session tabs for active tab status")
    elif state.active_tab_status and not any(
        state.active_tab_status in tabs.tabToolTip(index) for index in range(tabs.count())
    ):
        errors.append(
            f"{preset_id} live GUI tabs must expose active tab status: {state.active_tab_status}"
        )
    tree = window.findChild(QTreeWidget, "profileTree")
    if tree is None:
        errors.append(f"{preset_id} live GUI missing profile tree for selected interaction state")
    else:
        selected = tree.currentItem()
        selected_text = selected.text(0) if selected is not None else ""
        if state.selected_tree_label not in selected_text:
            errors.append(
                f"{preset_id} live GUI selected tree row {selected_text!r} must include "
                f"{state.selected_tree_label!r}"
            )
    return errors


def interaction_label_for_key(preset_id: str, key: str) -> str:
    if preset_id == "mobaxterm":
        return {
            "sessions": "Sessions",
            "tools": "Tools",
            "games": "Games",
        }.get(key, key)
    for action_key, label, _tooltip in gui_design_toolbar_actions(preset_id):
        if action_key == key:
            return label
    return key


def tab_position_name(tab_position: str) -> str:
    return {
        "north": "north",
        "south": "south",
        "west": "west",
        "east": "east",
    }.get(tab_position, "north")


def check_required_widgets(
    window: Any,
    required_widgets: dict[str, str] | None = None,
    *,
    context: str = "live GUI",
) -> list[str]:
    from PyQt6.QtWidgets import QWidget

    errors: list[str] = []
    widgets = required_widgets or REQUIRED_WIDGETS
    for object_name, label in widgets.items():
        widget = window.findChild(QWidget, object_name)
        if widget is None:
            errors.append(f"{context} missing {label}: {object_name}")
            continue
        geometry = widget.geometry()
        if geometry.width() <= 0 or geometry.height() <= 0:
            errors.append(f"{context} {label} has empty geometry: {object_name}")
        if hasattr(widget, "isVisible") and not widget.isVisible():
            errors.append(f"{context} {label} is not visible: {object_name}")
    return errors


def check_present_widgets(
    window: Any,
    present_widgets: dict[str, str] | None = None,
    *,
    context: str = "live GUI",
) -> list[str]:
    from PyQt6.QtWidgets import QWidget

    errors: list[str] = []
    for object_name, label in (present_widgets or {}).items():
        widget = window.findChild(QWidget, object_name)
        if widget is None:
            errors.append(f"{context} missing {label}: {object_name}")
    return errors


def metrics_from_qimage(image: Any) -> RenderMetrics:
    width = int(image.width())
    height = int(image.height())
    samples: list[tuple[int, int, int]] = []
    x_step = max(1, width // 48)
    y_step = max(1, height // 36)
    for y in range(0, height, y_step):
        for x in range(0, width, x_step):
            color = image.pixelColor(x, y)
            samples.append((int(color.red()), int(color.green()), int(color.blue())))
    return metrics_from_samples(width, height, samples)


def metrics_from_samples(
    width: int,
    height: int,
    samples: list[tuple[int, int, int]],
) -> RenderMetrics:
    if not samples:
        return RenderMetrics(width, height, 0, 0, 0, 0.0)
    distinct = len(set(samples))
    luminance_values = [int(round((red * 0.2126) + (green * 0.7152) + (blue * 0.0722))) for red, green, blue in samples]
    background = most_common_color(samples)
    non_background = sum(1 for color in samples if color_distance(color, background) > 6)
    return RenderMetrics(
        width=width,
        height=height,
        sampled_pixels=len(samples),
        distinct_colors=distinct,
        luminance_range=max(luminance_values) - min(luminance_values),
        non_background_ratio=non_background / len(samples),
    )


def validate_metrics(preset_id: str, metrics: RenderMetrics) -> list[str]:
    errors: list[str] = []
    if metrics.width < MIN_CAPTURE_SIZE[0] or metrics.height < MIN_CAPTURE_SIZE[1]:
        errors.append(
            f"{preset_id} live GUI capture dimensions {(metrics.width, metrics.height)} "
            f"must be at least {MIN_CAPTURE_SIZE}"
        )
    if metrics.distinct_colors < MIN_DISTINCT_COLORS:
        errors.append(f"{preset_id} live GUI capture has too few sampled colors: {metrics.distinct_colors}")
    if metrics.luminance_range < MIN_LUMINANCE_RANGE:
        errors.append(f"{preset_id} live GUI capture luminance range is too small: {metrics.luminance_range}")
    if metrics.non_background_ratio < MIN_NON_BACKGROUND_RATIO:
        errors.append(
            f"{preset_id} live GUI capture non-background ratio is too small: "
            f"{metrics.non_background_ratio:.4f}"
        )
    return errors


def most_common_color(samples: list[tuple[int, int, int]]) -> tuple[int, int, int]:
    counts: dict[tuple[int, int, int], int] = {}
    for color in samples:
        counts[color] = counts.get(color, 0) + 1
    return max(counts, key=counts.get)


def color_distance(left: tuple[int, int, int], right: tuple[int, int, int]) -> int:
    return abs(left[0] - right[0]) + abs(left[1] - right[1]) + abs(left[2] - right[2])


def artifact_metadata(out_dir: Path, pixmap: Any, preset_id: str) -> dict[str, Any]:
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{preset_id}-live.png"
    if not pixmap.save(str(path), "PNG"):
        raise RuntimeError(f"failed to save GUI screenshot: {display(path)}")
    data = path.read_bytes()
    return {
        "path": path.name,
        "size_bytes": len(data),
        "sha256": hashlib.sha256(data).hexdigest(),
    }


def measured_contract_evidence_audit(captures: list[CaptureResult]) -> dict[str, object]:
    required_preset_ids: list[str] = []
    missing_preset_ids: list[str] = []
    incomplete_preset_ids: list[str] = []
    failed_preset_ids: list[str] = []
    for capture in captures:
        expected_layout_ids = contract_ids(live_layout_contracts_for_preset(capture.preset_id))
        expected_topology_ids = contract_ids(live_topology_contracts_for_preset(capture.preset_id))
        if not expected_layout_ids and not expected_topology_ids:
            continue
        required_preset_ids.append(capture.preset_id)
        evidence = capture.contract_evidence
        if not isinstance(evidence, dict):
            missing_preset_ids.append(capture.preset_id)
            continue
        layout_measurements = measurement_list(evidence.get("layout_measurements"))
        topology_measurements = measurement_list(evidence.get("topology_measurements"))
        if layout_measurements is None or topology_measurements is None:
            incomplete_preset_ids.append(capture.preset_id)
            continue
        if (
            sorted(measurement_ids(layout_measurements)) != sorted(expected_layout_ids)
            or sorted(measurement_ids(topology_measurements)) != sorted(expected_topology_ids)
        ):
            incomplete_preset_ids.append(capture.preset_id)
        if any(measurement.get("passed") is not True for measurement in [*layout_measurements, *topology_measurements]):
            failed_preset_ids.append(capture.preset_id)
    return {
        "required_preset_ids": required_preset_ids,
        "complete": not missing_preset_ids and not incomplete_preset_ids and not failed_preset_ids,
        "missing_preset_ids": missing_preset_ids,
        "incomplete_preset_ids": incomplete_preset_ids,
        "failed_preset_ids": failed_preset_ids,
    }


def measured_contract_evidence_errors(captures: list[CaptureResult]) -> list[str]:
    audit = measured_contract_evidence_audit(captures)
    if audit["complete"]:
        return []
    errors: list[str] = []
    for key, label in [
        ("missing_preset_ids", "missing"),
        ("incomplete_preset_ids", "incomplete"),
        ("failed_preset_ids", "failed"),
    ]:
        preset_ids = audit[key]
        if isinstance(preset_ids, list) and preset_ids:
            errors.append(f"live GUI measured contract evidence {label} for presets: {', '.join(preset_ids)}")
    return errors


def contract_ids(contracts: list[dict[str, object]]) -> list[str]:
    return [str(contract["id"]) for contract in contracts]


def measurement_list(value: object) -> list[dict[str, object]] | None:
    if not isinstance(value, list):
        return None
    if not all(isinstance(item, dict) for item in value):
        return None
    return value


def measurement_ids(measurements: list[dict[str, object]]) -> list[str]:
    return [str(measurement.get("id", "")) for measurement in measurements]


def write_manifest(out_dir: Path, captures: list[CaptureResult], expected_preset_ids: list[str]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    captured_preset_ids = [capture.preset_id for capture in captures]
    missing_preset_ids = [preset_id for preset_id in expected_preset_ids if preset_id not in captured_preset_ids]
    extra_preset_ids = [preset_id for preset_id in captured_preset_ids if preset_id not in expected_preset_ids]
    evidence_audit = measured_contract_evidence_audit(captures)
    manifest = {
        "schema_version": 1,
        "renderer": "scripts/check_real_gui_render.py",
        "capture_mode": "live-pyqt6-offscreen",
        "requested_window_size": {"width": REQUESTED_SIZE[0], "height": REQUESTED_SIZE[1]},
        "minimum_capture_size": {"width": MIN_CAPTURE_SIZE[0], "height": MIN_CAPTURE_SIZE[1]},
        "selected_preset_ids": expected_preset_ids,
        "captured_preset_ids": captured_preset_ids,
        "expected_capture_count": len(expected_preset_ids),
        "actual_capture_count": len(captures),
        "complete_preset_capture": captured_preset_ids == expected_preset_ids,
        "missing_capture_preset_ids": missing_preset_ids,
        "extra_capture_preset_ids": extra_preset_ids,
        "measured_contract_evidence_required_preset_ids": evidence_audit["required_preset_ids"],
        "measured_contract_evidence_complete": evidence_audit["complete"],
        "missing_contract_evidence_preset_ids": evidence_audit["missing_preset_ids"],
        "incomplete_contract_evidence_preset_ids": evidence_audit["incomplete_preset_ids"],
        "failed_contract_evidence_preset_ids": evidence_audit["failed_preset_ids"],
        "required_widgets": REQUIRED_WIDGETS,
        "common_required_widgets": COMMON_REQUIRED_WIDGETS,
        "product_style_presets": sorted(PRODUCT_STYLE_PRESETS),
        "preset_required_widgets": {
            "default": NON_MOBA_REQUIRED_WIDGETS,
            "mobaxterm": {
                **MOBA_REQUIRED_WIDGETS,
                **MOBA_CONNECTED_REQUIRED_WIDGETS,
            },
        },
        "preset_present_widgets": {
            "default": NON_MOBA_PRESENT_WIDGETS,
            "mobaxterm": {},
        },
        "live_layout_contracts": LIVE_LAYOUT_CONTRACTS,
        "live_topology_contracts": LIVE_TOPOLOGY_CONTRACTS,
        "preset_live_contracts": live_contract_summaries_for_presets(expected_preset_ids),
        "preset_reference_profiles": PRESET_REFERENCE_PROFILES,
        "expected_live_reference_tab_labels": EXPECTED_LIVE_REFERENCE_TAB_LABELS,
        "expected_live_tree_labels": {key: sorted(value) for key, value in EXPECTED_LIVE_TREE_LABELS.items()},
        "captures": [capture.to_dict() for capture in captures],
    }
    (out_dir / MANIFEST_NAME).write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def module_available(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def restore_env(name: str, old_value: str | None) -> None:
    if old_value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = old_value


def display(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
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
    PRODUCT_GUI_PRESET_IDS,
    PRODUCT_REFERENCE_TAB_PRESET_IDS,
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
    gui_design_moba_ribbon_actions,
    gui_design_moba_ribbon_edge_action_route,
    gui_design_moba_ribbon_edge_actions,
    gui_design_moba_right_utility_action_route,
    gui_design_moba_right_utility_actions,
    gui_design_moba_right_utility_rail_chrome,
    gui_design_moba_session_edge_action_route,
    gui_design_moba_session_edge_actions,
    gui_design_moba_session_tree_chrome,
    gui_design_moba_sftp_browser_chrome,
    gui_design_moba_sftp_dock_actions,
    gui_design_moba_sftp_dock_layout,
    gui_design_moba_sftp_file_row_icons,
    gui_design_moba_sftp_follow_folder_route,
    gui_design_moba_sftp_routed_file_rows,
    gui_design_moba_sftp_toolbar_action_geometry,
    gui_design_moba_sftp_toolbar_action_route,
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
    gui_design_mremoteng_document_filter_route,
    gui_design_mremoteng_document_toolbar_chrome,
    gui_design_mremoteng_inheritance_route,
    gui_design_mremoteng_property_grid_chrome,
    gui_design_mremoteng_top_chrome,
    gui_design_preset_catalog_route,
    gui_design_preset_command_surface_route,
    gui_design_preset_focus_interaction_route,
    gui_design_preset_home_search_route,
    gui_design_preset_isolation_route,
    gui_design_preset_keyboard_shortcut_route,
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
    gui_design_sidebar_copy,
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
    gui_design_workflow_cards,
    gui_design_workspace_surface,
)
from remote_ops_workspace.launcher import LauncherError  # noqa: E402
from remote_ops_workspace.moba_connected import (  # noqa: E402
    build_moba_connected_session_state,
    build_moba_terminal_transcript,
    build_ssh_connection_banner,
    moba_connected_session_action_route,
    moba_connected_session_identity_route,
    moba_connected_session_route,
    moba_connected_tab_chrome_geometry_items,
    moba_sftp_terminal_folder_route,
    moba_telemetry_cell_geometry,
    moba_telemetry_cells,
)
from remote_ops_workspace.models import Profile  # noqa: E402

REQUESTED_SIZE = (1420, 820)
MIN_CAPTURE_SIZE = (1100, 680)
DEFAULT_RENDER_TIMEOUT_SECONDS = 240
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
EXPECTED_PRODUCT_IDENTITY_ROUTES = {
    preset_id: gui_design_product_identity_route(preset_id)
    for preset_id in ("securecrt", "termius", "remmina", "mremoteng")
}
EXPECTED_PRESET_REFERENCE_TAB_ROUTES = {
    preset_id: gui_design_preset_reference_tab_route(preset_id)
    for preset_id in PRODUCT_REFERENCE_TAB_PRESET_IDS
}
EXPECTED_PRESET_REFERENCE_TAB_CHROME_ROUTES = {
    preset_id: gui_design_preset_reference_tab_chrome_route(preset_id)
    for preset_id in PRODUCT_REFERENCE_TAB_PRESET_IDS
}
EXPECTED_PRESET_REFERENCE_STATUS_BAR_ROUTES = {
    preset_id: gui_design_preset_reference_status_bar_route(preset_id)
    for preset_id in PRODUCT_REFERENCE_TAB_PRESET_IDS
}
EXPECTED_PRESET_REFERENCE_SESSION_ACTION_ROUTES = {
    preset_id: gui_design_preset_reference_session_action_route(preset_id)
    for preset_id in PRODUCT_REFERENCE_TAB_PRESET_IDS
}
EXPECTED_PRESET_REFERENCE_SURFACE_ROUTES = {
    preset_id: gui_design_preset_reference_surface_route(preset_id)
    for preset_id in PRODUCT_REFERENCE_TAB_PRESET_IDS
}
EXPECTED_PRESET_REFERENCE_CONTROL_ROUTES = {
    preset_id: gui_design_preset_reference_control_route(preset_id)
    for preset_id in PRODUCT_REFERENCE_TAB_PRESET_IDS
}
EXPECTED_PRESET_REFERENCE_INPUT_ROUTES = {
    preset_id: gui_design_preset_reference_input_route(preset_id)
    for preset_id in PRODUCT_REFERENCE_TAB_PRESET_IDS
}
EXPECTED_PRESET_REFERENCE_TRANSCRIPT_ROUTES = {
    preset_id: gui_design_preset_reference_transcript_route(preset_id)
    for preset_id in PRODUCT_REFERENCE_TAB_PRESET_IDS
}
EXPECTED_PRESET_CATALOG_ROUTE = gui_design_preset_catalog_route()
EXPECTED_PRESET_ISOLATION_ROUTES = {
    preset.id: gui_design_preset_isolation_route(preset.id)
    for preset in GUI_DESIGN_PRESETS
}
EXPECTED_PRESET_SELECTION_ROUTES = {
    preset.id: gui_design_preset_selection_route(preset.id)
    for preset in GUI_DESIGN_PRESETS
}
EXPECTED_PRESET_TRANSITION_ROUTES = {
    preset.id: gui_design_preset_transition_route(preset.id)
    for preset in GUI_DESIGN_PRESETS
}
EXPECTED_PRESET_VISUAL_SIGNATURES = {
    preset.id: gui_design_preset_visual_signature(preset.id)
    for preset in GUI_DESIGN_PRESETS
}
EXPECTED_PRESET_KEYBOARD_SHORTCUT_ROUTES = {
    preset_id: gui_design_preset_keyboard_shortcut_route(preset_id)
    for preset_id in PRODUCT_GUI_PRESET_IDS
}
EXPECTED_PRESET_COMMAND_SURFACE_ROUTES = {
    preset_id: gui_design_preset_command_surface_route(preset_id)
    for preset_id in PRODUCT_GUI_PRESET_IDS
}
EXPECTED_PRESET_FOCUS_INTERACTION_ROUTES = {
    preset_id: gui_design_preset_focus_interaction_route(preset_id)
    for preset_id in PRODUCT_GUI_PRESET_IDS
}
EXPECTED_PRESET_HOME_SEARCH_ROUTES = {
    preset_id: gui_design_preset_home_search_route(preset_id)
    for preset_id in PRODUCT_GUI_PRESET_IDS
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
EXPECTED_MOBA_CONNECTED_SESSION_ACTION_ROUTE = moba_connected_session_action_route(EXPECTED_MOBA_CONNECTED_STATE)
EXPECTED_MOBA_SFTP_TERMINAL_FOLDER_ROUTE = moba_sftp_terminal_folder_route(EXPECTED_MOBA_CONNECTED_STATE)
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
EXPECTED_MOBA_RIBBON_EDGE_ACTION_ROUTE = gui_design_moba_ribbon_edge_action_route()
EXPECTED_MOBA_TAB_CHROME_KEYS = {"home", "active-session", "new-session"}
EXPECTED_MOBA_STATIC_TAB_CHROME_KEYS = {"home", "inactive-session", "active-session", "new-session"}
EXPECTED_MOBA_TAB_CHROME_GEOMETRY = tuple(moba_connected_tab_chrome_geometry_items())
EXPECTED_MOBA_TAB_CHROME_GEOMETRY_BY_KEY = {item.key: item for item in EXPECTED_MOBA_TAB_CHROME_GEOMETRY}
EXPECTED_MOBA_RIGHT_UTILITY_KEYS = {action.key for action in gui_design_moba_right_utility_actions()}
EXPECTED_MOBA_RIGHT_UTILITY_ICON_KEYS = {action.key: action.icon_key for action in gui_design_moba_right_utility_actions()}
EXPECTED_MOBA_RIGHT_UTILITY_ACTIONS = tuple(gui_design_moba_right_utility_actions())
EXPECTED_MOBA_RIGHT_UTILITY_BY_KEY = {action.key: action for action in EXPECTED_MOBA_RIGHT_UTILITY_ACTIONS}
EXPECTED_MOBA_RIGHT_UTILITY_ACTION_ROUTE = gui_design_moba_right_utility_action_route()
EXPECTED_MOBA_RIGHT_UTILITY_RAIL_CHROME = gui_design_moba_right_utility_rail_chrome()
EXPECTED_MOBA_SESSION_EDGE_ACTIONS = tuple(gui_design_moba_session_edge_actions())
EXPECTED_MOBA_SESSION_EDGE_KEYS = {action.key for action in EXPECTED_MOBA_SESSION_EDGE_ACTIONS}
EXPECTED_MOBA_SESSION_EDGE_ICON_KEYS = {action.key: action.icon_key for action in EXPECTED_MOBA_SESSION_EDGE_ACTIONS}
EXPECTED_MOBA_SESSION_EDGE_BY_KEY = {action.key: action for action in EXPECTED_MOBA_SESSION_EDGE_ACTIONS}
EXPECTED_MOBA_SESSION_EDGE_ACTION_ROUTE = gui_design_moba_session_edge_action_route()
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
EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE = gui_design_moba_sftp_toolbar_action_route()
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
EXPECTED_MOBA_REMOTE_MONITORING_CONTROL_ROUTE = gui_design_moba_remote_monitoring_control_route()
EXPECTED_MOBA_FOLLOW_TERMINAL_FOLDER_CONTROL_ROUTE = gui_design_moba_follow_terminal_folder_control_route()
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
EXPECTED_SECURECRT_SESSION_MANAGER_FILTER_ROUTE = gui_design_securecrt_session_manager_filter_route()
EXPECTED_SECURECRT_SFTP_TAB_ROUTE = gui_design_securecrt_sftp_tab_route()
EXPECTED_SECURECRT_SFTP_BROWSER_ROUTE = gui_design_securecrt_sftp_browser_route()
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
EXPECTED_REMMINA_PROFILE_FILTER_ROUTE = gui_design_remmina_profile_filter_route()
EXPECTED_REMMINA_CLIPBOARD_ROUTE = gui_design_remmina_clipboard_route()
EXPECTED_REMMINA_SCREENSHOT_ROUTE = gui_design_remmina_screenshot_route()
EXPECTED_REMMINA_SFTP_TRANSFER_ROUTE = gui_design_remmina_sftp_transfer_route()
EXPECTED_TERMIUS_HEADER_CHIP_KEYS = [chip.key for chip in gui_design_termius_header_chips()]
EXPECTED_TERMIUS_HOSTS_CHROME = gui_design_termius_hosts_chrome()
EXPECTED_TERMIUS_HOSTS_ACTION_KEYS = [action.key for action in EXPECTED_TERMIUS_HOSTS_CHROME.actions]
EXPECTED_TERMIUS_HOSTS_ICON_KEYS = {action.key: action.icon_key for action in EXPECTED_TERMIUS_HOSTS_CHROME.actions}
EXPECTED_TERMIUS_HOST_IDENTITY_STRIP = gui_design_termius_host_identity_strip()
EXPECTED_TERMIUS_HOST_IDENTITY_KEYS = [field.key for field in EXPECTED_TERMIUS_HOST_IDENTITY_STRIP.fields]
EXPECTED_TERMIUS_SYNC_ROUTE = gui_design_termius_sync_route()
EXPECTED_TERMIUS_HOST_SELECTION_ROUTE = gui_design_termius_host_selection_route()
EXPECTED_TERMIUS_PORT_FORWARD_ROUTE = gui_design_termius_port_forward_route()
EXPECTED_TERMIUS_SNIPPET_ROUTE = gui_design_termius_snippet_route()
EXPECTED_TERMIUS_FILES_BROWSER_ROUTE = gui_design_termius_files_browser_route()
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
EXPECTED_MREMOTENG_DOCUMENT_FILTER_ROUTE = gui_design_mremoteng_document_filter_route()
EXPECTED_MREMOTENG_INHERITANCE_ROUTE = gui_design_mremoteng_inheritance_route()
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
    "secureCrtCommandInput": "SecureCRT live command-window input",
    "secureCrtCommandSend": "SecureCRT live command-window Send control",
}
TERMIUS_REQUIRED_WIDGETS = {
    "termiusHostsChrome": "Termius Hosts search/action chrome",
    "termiusHostIdentityStrip": "Termius host identity strip",
}
REMMINA_REQUIRED_WIDGETS = {
    "remminaProfileListChrome": "Remmina profile list chrome",
    "remminaSftpTransferPanel": "Remmina SFTP transfer panel",
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
        {
            "id": "quick-connect-above-dock",
            "from": "mobaQuickConnectChrome",
            "relation": "above",
            "to": "mobaConnectedLeftDock",
            "max_gap": 90,
        },
        {
            "id": "rail-left-of-dock",
            "from": "mobaRail",
            "relation": "left_of",
            "to": "mobaConnectedLeftDock",
            "max_gap": 80,
        },
        {
            "id": "dock-left-of-ssh-banner",
            "from": "mobaConnectedLeftDock",
            "relation": "left_of",
            "to": "mobaSshBanner",
            "max_gap": 120,
        },
        {
            "id": "ssh-banner-left-of-right-utility",
            "from": "mobaSshBanner",
            "relation": "left_of",
            "to": "mobaRightUtilityRail",
            "min_gap": 20,
        },
        {
            "id": "sftp-table-inside-dock",
            "from": "mobaSftpFileTable",
            "relation": "inside",
            "to": "mobaConnectedLeftDock",
        },
        {
            "id": "ssh-banner-above-telemetry",
            "from": "mobaSshBanner",
            "relation": "above",
            "to": "mobaTelemetryBar",
            "min_gap": 80,
        },
    ],
    "securecrt": [
        {
            "id": "toolbar-above-tabs",
            "from": "layoutToolbar",
            "relation": "above",
            "to": "sessionTabs",
            "max_gap": 120,
        },
        {
            "id": "sidebar-left-of-tabs",
            "from": "leftPanel",
            "relation": "left_of",
            "to": "sessionTabs",
            "max_gap": 80,
        },
        {
            "id": "workflow-above-workspace-surface",
            "from": "productWorkflowEvidence",
            "relation": "above",
            "to": "productWorkspaceSurface",
            "max_gap": 50,
        },
        {
            "id": "welcome-scroll-above-log",
            "from": "welcomeScroll",
            "relation": "above",
            "to": "activityLog",
            "max_gap": 196,
        },
        {
            "id": "workspace-primary-left-of-secondary",
            "from": "productWorkspacePrimaryPane",
            "relation": "left_of",
            "to": "productWorkspaceSecondaryPane",
            "max_gap": 40,
        },
    ],
    "termius": [
        {
            "id": "toolbar-above-tabs",
            "from": "layoutToolbar",
            "relation": "above",
            "to": "sessionTabs",
            "max_gap": 120,
        },
        {
            "id": "hosts-sidebar-left-of-west-tabs",
            "from": "leftPanel",
            "relation": "left_of",
            "to": "sessionTabs",
            "max_gap": 80,
        },
        {
            "id": "workflow-above-workspace-surface",
            "from": "productWorkflowEvidence",
            "relation": "above",
            "to": "productWorkspaceSurface",
            "max_gap": 50,
        },
        {
            "id": "welcome-scroll-above-log",
            "from": "welcomeScroll",
            "relation": "above",
            "to": "activityLog",
            "max_gap": 196,
        },
        {
            "id": "workspace-primary-left-of-secondary",
            "from": "productWorkspacePrimaryPane",
            "relation": "left_of",
            "to": "productWorkspaceSecondaryPane",
            "max_gap": 40,
        },
    ],
    "remmina": [
        {
            "id": "toolbar-above-viewer-tabs",
            "from": "layoutToolbar",
            "relation": "above",
            "to": "sessionTabs",
            "max_gap": 120,
        },
        {
            "id": "profiles-left-of-viewer-tabs",
            "from": "leftPanel",
            "relation": "left_of",
            "to": "sessionTabs",
            "max_gap": 80,
        },
        {
            "id": "workflow-above-workspace-surface",
            "from": "productWorkflowEvidence",
            "relation": "above",
            "to": "productWorkspaceSurface",
            "max_gap": 50,
        },
        {
            "id": "welcome-scroll-above-activity",
            "from": "welcomeScroll",
            "relation": "above",
            "to": "activityLog",
            "max_gap": 196,
        },
        {
            "id": "workspace-primary-left-of-secondary",
            "from": "productWorkspacePrimaryPane",
            "relation": "left_of",
            "to": "productWorkspaceSecondaryPane",
            "max_gap": 40,
        },
    ],
    "mremoteng": [
        {
            "id": "toolbar-above-document-tabs",
            "from": "layoutToolbar",
            "relation": "above",
            "to": "sessionTabs",
            "max_gap": 120,
        },
        {
            "id": "connections-left-of-document-tabs",
            "from": "leftPanel",
            "relation": "left_of",
            "to": "sessionTabs",
            "max_gap": 80,
        },
        {
            "id": "workspace-surface-above-workflow",
            "from": "productWorkspaceSurface",
            "relation": "above",
            "to": "productWorkflowEvidence",
            "max_gap": 110,
        },
        {
            "id": "document-controls-above-property-grid",
            "from": "mRemoteNgDocumentControls",
            "relation": "above",
            "to": "mRemoteNgPropertyGrid",
            "max_gap": 40,
        },
        {
            "id": "welcome-scroll-above-log",
            "from": "welcomeScroll",
            "relation": "above",
            "to": "activityLog",
            "max_gap": 196,
        },
        {
            "id": "workspace-primary-left-of-secondary",
            "from": "productWorkspacePrimaryPane",
            "relation": "left_of",
            "to": "productWorkspaceSecondaryPane",
            "max_gap": 40,
        },
    ],
}
MIN_DISTINCT_COLORS = 18
MIN_LUMINANCE_RANGE = 40
MIN_NON_BACKGROUND_RATIO = 0.08
FONT_PROBE_TEXT = "RemoteOps0123456789"
MIN_FONT_RENDER_INK_PIXELS = 40
MIN_DISTINCT_FONT_GLYPHS = 12


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
    font_render_evidence: FontRenderEvidence | None = None

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
        if self.font_render_evidence is not None:
            payload["font_render_evidence"] = self.font_render_evidence.to_dict()
        return payload


@dataclass(frozen=True)
class FontRenderEvidence:
    platform_name: str
    family_count: int
    selected_family: str
    raw_font_valid: bool
    glyph_indexes: tuple[int, ...]
    rendered_ink_pixels: int

    def to_dict(self) -> dict[str, object]:
        return {
            "platform_name": self.platform_name,
            "family_count": self.family_count,
            "selected_family": self.selected_family,
            "raw_font_valid": self.raw_font_valid,
            "probe_text": FONT_PROBE_TEXT,
            "glyph_indexes": list(self.glyph_indexes),
            "distinct_glyph_count": len(set(self.glyph_indexes)),
            "rendered_ink_pixels": self.rendered_ink_pixels,
        }


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
    parser.add_argument(
        "--timeout-seconds",
        type=int,
        default=DEFAULT_RENDER_TIMEOUT_SECONDS,
        help="Hard timeout for the live render process; use 0 to disable.",
    )
    parser.add_argument(
        "--render-child",
        action="store_true",
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args(argv)

    if args.timeout_seconds and not args.render_child:
        return run_render_child(args)

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


def run_render_child(args: argparse.Namespace) -> int:
    command = render_child_command(args)
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=os.environ.copy(),
            text=True,
            capture_output=True,
            timeout=args.timeout_seconds,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        if exc.stdout:
            print(exc.stdout, end="" if exc.stdout.endswith("\n") else "\n")
        if exc.stderr:
            print(exc.stderr, file=sys.stderr, end="" if exc.stderr.endswith("\n") else "\n")
        print(f"real GUI render: timed out after {args.timeout_seconds} seconds", file=sys.stderr)
        return 124
    if result.stdout:
        print(result.stdout, end="" if result.stdout.endswith("\n") else "\n")
    if result.stderr:
        print(result.stderr, file=sys.stderr, end="" if result.stderr.endswith("\n") else "\n")
    return int(result.returncode)


def render_child_command(args: argparse.Namespace) -> list[str]:
    command = [
        sys.executable,
        str(Path(__file__).resolve()),
        "--render-child",
        "--timeout-seconds",
        "0",
    ]
    for preset_id in args.preset or []:
        command.extend(["--preset", preset_id])
    if args.out_dir is not None:
        command.extend(["--out-dir", str(args.out_dir)])
    if args.require_pyqt6:
        command.append("--require-pyqt6")
    return command


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
    selected = preset_ids or [preset.id for preset in GUI_DESIGN_PRESETS]
    if not module_available("PyQt6"):
        from remote_ops_workspace import gui

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
    old_scale_factor = os.environ.get("QT_SCALE_FACTOR")
    old_home = os.environ.get("ROW_HOME")
    os.environ.setdefault("QT_QPA_PLATFORM", default_qt_platform())
    if (scale_factor := default_qt_scale_factor()) is not None:
        os.environ["QT_SCALE_FACTOR"] = scale_factor
    captures: list[CaptureResult] = []
    errors: list[str] = []
    messages: list[str] = []
    try:
        with tempfile.TemporaryDirectory(prefix="row-real-gui-") as raw_tmp:
            os.environ["ROW_HOME"] = str(Path(raw_tmp) / "row-home")
            captures, errors, messages = _capture_live_gui(preset_ids, out_dir=out_dir)
    finally:
        restore_env("QT_QPA_PLATFORM", old_qpa)
        restore_env("QT_SCALE_FACTOR", old_scale_factor)
        restore_env("ROW_HOME", old_home)

    if not errors:
        errors.extend(measured_contract_evidence_errors(captures))
    if out_dir is not None and not errors:
        write_manifest(out_dir, captures, preset_ids)
        messages.append(f"wrote live screenshot manifest to {display(out_dir / MANIFEST_NAME)}")
    return errors, messages


def default_qt_platform(platform: str | None = None) -> str:
    resolved = platform or sys.platform
    if resolved.startswith("win"):
        return "windows"
    if resolved == "darwin":
        return "cocoa"
    return "offscreen"


def default_qt_scale_factor(platform: str | None = None) -> str | None:
    resolved = platform or sys.platform
    return "1" if resolved.startswith("win") else None


def _capture_live_gui(
    preset_ids: list[str],
    *,
    out_dir: Path | None,
) -> tuple[list[CaptureResult], list[str], list[str]]:
    from PyQt6.QtCore import QCoreApplication
    from PyQt6.QtWidgets import QApplication, QComboBox

    from remote_ops_workspace import gui

    captures: list[CaptureResult] = []
    errors: list[str] = []
    messages: list[str] = []
    app = QApplication.instance()
    if app is None:
        app = QApplication(["row-real-gui-render-font-preflight"])
    font_evidence = collect_qt_font_render_evidence(app)
    font_errors = validate_qt_font_render_evidence(font_evidence)
    if font_errors:
        errors.extend(font_errors)
        messages.append(
            f"Qt font preflight failed on {font_evidence.platform_name}: "
            f"{font_evidence.family_count} families, "
            f"{font_evidence.rendered_ink_pixels} rendered ink pixels"
        )
        return captures, errors, messages
    messages.append(
        f"Qt font preflight passed on {font_evidence.platform_name}: "
        f"{font_evidence.selected_family}, {len(font_evidence.glyph_indexes)} glyphs, "
        f"{font_evidence.rendered_ink_pixels} rendered ink pixels"
    )
    for preset_id in preset_ids:
        preset = next((item for item in GUI_DESIGN_PRESETS if item.id == preset_id), None)
        if preset is None:
            errors.append(f"unknown GUI preset requested: {preset_id}")
            continue
        app, window = gui.create_main_window(["row-real-gui-render-check", preset.id], show=True)
        window.resize(*REQUESTED_SIZE)
        window.show()
        process_events(app)

        widget_errors = check_required_widgets(window, COMMON_REQUIRED_WIDGETS)
        if widget_errors:
            errors.extend(widget_errors)
            close_live_render_window(window, app)
            QCoreApplication.processEvents()
            continue

        design_select = window.findChild(QComboBox, "designSelect")
        if design_select is None:
            errors.append("real GUI render could not locate design selector")
            close_live_render_window(window, app)
            QCoreApplication.processEvents()
            continue
        try:
            index = design_select.findData(preset.id)
            if index < 0:
                errors.append(f"live GUI design selector missing preset: {preset.id}")
                continue
            transition_route = EXPECTED_PRESET_TRANSITION_ROUTES[preset.id]
            source_index = design_select.findData(transition_route.from_preset_ids[0])
            if source_index < 0:
                errors.append(f"live GUI design selector missing transition source: {transition_route.from_preset_ids[0]}")
                continue
            if source_index != index:
                design_select.setCurrentIndex(source_index)
                window.resize(*REQUESTED_SIZE)
                process_events(app)
            design_select.setCurrentIndex(index)
            window.resize(*REQUESTED_SIZE)
            process_events(app)
            preset_state_errors = prepare_preset_live_state(window, preset.id)
            window.resize(*REQUESTED_SIZE)
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
            actual_window_size = (window.width(), window.height())
            if actual_window_size != REQUESTED_SIZE:
                errors.append(
                    f"{preset.id} live GUI window size {actual_window_size} "
                    f"must equal requested size {REQUESTED_SIZE}"
                )

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
                    font_render_evidence=font_evidence,
                )
            )
            messages.append(
                f"{preset.id} captured {metrics.width}x{metrics.height}, "
                f"{metrics.distinct_colors} sampled colors"
            )
        finally:
            close_live_render_window(window, app)
            QCoreApplication.processEvents()
    return captures, errors, messages


def collect_qt_font_render_evidence(app: Any) -> FontRenderEvidence:
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import (
        QColor,
        QFont,
        QFontDatabase,
        QGuiApplication,
        QImage,
        QPainter,
        QRawFont,
    )

    families = tuple(str(family) for family in QFontDatabase.families())
    selected_font: Any | None = None
    selected_raw_font: Any | None = None
    selected_glyph_indexes: tuple[int, ...] = ()
    candidates = [QFont(app.font())]
    candidates.extend(QFont(family) for family in families)
    for candidate in candidates:
        raw_font = QRawFont.fromFont(candidate)
        if not raw_font.isValid():
            continue
        glyph_indexes = tuple(int(index) for index in raw_font.glyphIndexesForString(FONT_PROBE_TEXT))
        if not usable_font_probe_glyphs(glyph_indexes):
            continue
        selected_font = candidate
        selected_raw_font = raw_font
        selected_glyph_indexes = glyph_indexes
        break

    rendered_ink_pixels = 0
    if selected_font is not None:
        if selected_font.family() != app.font().family():
            app.setFont(selected_font)
        probe_font = QFont(selected_font)
        probe_font.setPointSize(14)
        image = QImage(360, 72, QImage.Format.Format_ARGB32_Premultiplied)
        background = QColor("#ffffff")
        image.fill(background)
        painter = QPainter(image)
        try:
            painter.setFont(probe_font)
            painter.setPen(QColor("#000000"))
            painter.drawText(image.rect(), Qt.AlignmentFlag.AlignCenter, FONT_PROBE_TEXT)
        finally:
            painter.end()
        rendered_ink_pixels = sum(
            1
            for y in range(image.height())
            for x in range(image.width())
            if image.pixelColor(x, y) != background
        )

    return FontRenderEvidence(
        platform_name=str(QGuiApplication.platformName()),
        family_count=len(families),
        selected_family=selected_font.family() if selected_font is not None else "",
        raw_font_valid=bool(selected_raw_font is not None and selected_raw_font.isValid()),
        glyph_indexes=selected_glyph_indexes,
        rendered_ink_pixels=rendered_ink_pixels,
    )


def usable_font_probe_glyphs(glyph_indexes: tuple[int, ...]) -> bool:
    return (
        len(glyph_indexes) == len(FONT_PROBE_TEXT)
        and all(index > 0 for index in glyph_indexes)
        and len(set(glyph_indexes)) >= MIN_DISTINCT_FONT_GLYPHS
    )


def validate_qt_font_render_evidence(evidence: FontRenderEvidence) -> list[str]:
    errors: list[str] = []
    if evidence.family_count <= 0:
        errors.append(
            f"Qt platform {evidence.platform_name!r} exposes no usable font families; "
            "install fontconfig and a TrueType font (Linux CI requires fontconfig and fonts-dejavu-core)"
        )
    if not evidence.raw_font_valid or not evidence.selected_family:
        errors.append(
            f"Qt platform {evidence.platform_name!r} could not resolve a valid raw font for the GUI"
        )
    if len(evidence.glyph_indexes) != len(FONT_PROBE_TEXT) or any(
        index <= 0 for index in evidence.glyph_indexes
    ):
        errors.append(
            f"Qt platform {evidence.platform_name!r} could not resolve every required GUI probe glyph"
        )
    elif len(set(evidence.glyph_indexes)) < MIN_DISTINCT_FONT_GLYPHS:
        errors.append(
            f"Qt platform {evidence.platform_name!r} resolved only "
            f"{len(set(evidence.glyph_indexes))} distinct GUI probe glyphs; tofu substitution is not accepted"
        )
    if evidence.rendered_ink_pixels < MIN_FONT_RENDER_INK_PIXELS:
        errors.append(
            f"Qt platform {evidence.platform_name!r} rendered only "
            f"{evidence.rendered_ink_pixels} font-probe ink pixels; readable glyph rendering is required"
        )
    return errors


def close_live_render_window(window: Any, app: Any) -> None:
    if hasattr(window, "confirm_stop_processes"):
        window.confirm_stop_processes = lambda _title, _count: True
    window.close()
    process_events(app)


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
    route = EXPECTED_PRESET_REFERENCE_TAB_ROUTES.get(preset_id)
    if route is None:
        return []
    tab_chrome_route = EXPECTED_PRESET_REFERENCE_TAB_CHROME_ROUTES.get(preset_id)
    status_route = EXPECTED_PRESET_REFERENCE_STATUS_BAR_ROUTES.get(preset_id)
    session_action_route = EXPECTED_PRESET_REFERENCE_SESSION_ACTION_ROUTES.get(preset_id)
    surface_route = EXPECTED_PRESET_REFERENCE_SURFACE_ROUTES.get(preset_id)
    control_route = EXPECTED_PRESET_REFERENCE_CONTROL_ROUTES.get(preset_id)
    input_route = EXPECTED_PRESET_REFERENCE_INPUT_ROUTES.get(preset_id)
    transcript_route = EXPECTED_PRESET_REFERENCE_TRANSCRIPT_ROUTES.get(preset_id)
    try:
        profile = window.store.get(profile_name)
        window.launch_profile(profile, dry_run=False, prefix="CI REFERENCE")
    except (KeyError, LauncherError, ValueError) as exc:
        return [f"{preset_id} live GUI could not open reference profile {profile_name}: {exc}"]
    if hasattr(window, "select_profile"):
        window.select_profile(profile_name)
    if preset_id == "remmina":
        transfer_route = EXPECTED_REMMINA_SFTP_TRANSFER_ROUTE
        try:
            transfer_profile = window.store.get(transfer_route.selected_profile_name)
            window.launch_profile(transfer_profile, dry_run=False, prefix="CI TRANSFER")
        except (KeyError, LauncherError, ValueError) as exc:
            return [f"remmina live GUI could not open SFTP transfer profile: {exc}"]
        if hasattr(window, "select_profile"):
            window.select_profile(profile_name)
    errors: list[str] = []
    if profile_name != route.reference_profile:
        errors.append(f"{preset_id} live GUI reference profile {profile_name!r} drifted from route")
    reference_index = find_live_tab_index(window.tabs, route.active_tab_label)
    if reference_index < 0:
        errors.append(f"{preset_id} live GUI could not activate reference tab: {route.active_tab_label}")
    else:
        window.tabs.setCurrentIndex(reference_index)
        window.tabs.setProperty(route.activated_label_property, route.active_tab_label)
        window.tabs.setProperty(route.active_tab_property, route.active_tab_label)
        window.tabs.setProperty(route.reference_profile_property, route.reference_profile)
        if tab_chrome_route is not None:
            errors.extend(capture_product_reference_tab_chrome(window, preset_id, reference_index))
        if surface_route is not None:
            errors.extend(capture_product_reference_surface(window, preset_id, reference_index))
        if control_route is not None:
            errors.extend(capture_product_reference_controls(window, preset_id, reference_index))
        if input_route is not None:
            errors.extend(capture_product_reference_input(window, preset_id, reference_index))
        if transcript_route is not None:
            errors.extend(capture_product_reference_transcript(window, preset_id, reference_index))
        if status_route is not None:
            errors.extend(capture_product_reference_status_bar(window, preset_id, reference_index))
        if session_action_route is not None:
            errors.extend(capture_product_reference_session_actions(window, preset_id, reference_index))
    home_index = window.find_tab_by_role(route.home_tab_role)
    if home_index >= 0:
        window.tabs.setCurrentIndex(home_index)
        window.tabs.setProperty(route.returned_home_label_property, route.home_tab_label)
        window.tabs.setProperty(route.home_tab_property, route.home_tab_label)
    else:
        errors.append(f"{preset_id} live GUI could not return to home tab: {route.home_tab_label}")
    state = gui_design_interaction_state(preset_id)
    if hasattr(window, "select_profile_tree_label"):
        window.select_profile_tree_label(state.selected_tree_label)
    focus_route = (
        gui_design_preset_focus_interaction_route(preset_id)
        if preset_id in PRODUCT_GUI_PRESET_IDS
        else None
    )
    if focus_route is not None and hasattr(window, "apply_focus_interaction_route_for_design"):
        window.apply_focus_interaction_route_for_design(focus_route, preset_id)
    return errors


def find_live_tab_index(tabs: Any, label: str) -> int:
    for index in range(tabs.count()):
        if tabs.tabText(index) == label:
            return index
    return -1


def live_tab_plain_tooltip(tabs: Any, index: int) -> str:
    widget = tabs.widget(index)
    if widget is not None:
        value = widget.property("tabTooltipPlainText")
        if isinstance(value, str):
            return value
    return tabs.tabToolTip(index)


def capture_product_reference_tab_chrome(window: Any, preset_id: str, reference_index: int) -> list[str]:
    route = EXPECTED_PRESET_REFERENCE_TAB_CHROME_ROUTES.get(preset_id)
    if route is None:
        return []
    tabs = window.tabs
    reference_widget = tabs.widget(reference_index)
    if reference_widget is None:
        return [f"{preset_id} live GUI reference tab chrome missing active tab widget"]
    tab_bar = tabs.tabBar()
    tab_role = str(reference_widget.property("tabRole") or "")
    closeable = bool(tabs.tabsClosable() and tab_role == route.reference_tab_role)
    selected = tabs.currentIndex() == reference_index
    tab_position = tabs.tabPosition().name.lower()
    properties = {
        route.captured_property: True,
        route.captured_label_property: tabs.tabText(reference_index),
        route.captured_tooltip_property: live_tab_plain_tooltip(tabs, reference_index),
        route.captured_index_property: reference_index,
        route.captured_role_property: tab_role,
        route.captured_position_property: tab_position,
        route.captured_closeable_property: closeable,
        route.captured_selected_property: selected,
    }
    for widget in (tabs, reference_widget, tab_bar):
        if widget is None:
            continue
        for property_name, value in properties.items():
            widget.setProperty(property_name, value)
    return []


def capture_product_reference_status_bar(window: Any, preset_id: str, reference_index: int) -> list[str]:
    from PyQt6.QtWidgets import QLabel

    route = EXPECTED_PRESET_REFERENCE_STATUS_BAR_ROUTES.get(preset_id)
    if route is None:
        return []
    tabs = window.tabs
    reference_widget = tabs.widget(reference_index)
    if reference_widget is None:
        return [f"{preset_id} live GUI reference status-bar route missing active tab widget"]
    status_bar = window.statusBar()
    notice = window.findChild(QLabel, route.status_notice_object)
    segment_labels = window.findChildren(QLabel, route.status_segment_object)
    segment_texts = [label.text() for label in segment_labels if label.text()]
    segment_tooltips = [label.toolTip() for label in segment_labels if label.text()]
    properties = {
        route.captured_property: True,
        route.captured_tab_property: tabs.tabText(reference_index),
        route.captured_message_property: status_bar.currentMessage(),
        route.captured_segments_property: segment_texts,
        route.captured_segment_count_property: len(segment_texts),
        route.captured_segment_tooltips_property: segment_tooltips,
        route.captured_notice_property: notice.text() if notice is not None else "",
    }
    for widget in (tabs, reference_widget, status_bar, notice, *segment_labels):
        if widget is None:
            continue
        for property_name, value in properties.items():
            widget.setProperty(property_name, value)
    return []


def capture_product_reference_session_actions(window: Any, preset_id: str, reference_index: int) -> list[str]:
    route = EXPECTED_PRESET_REFERENCE_SESSION_ACTION_ROUTES.get(preset_id)
    if route is None:
        return []
    tabs = window.tabs
    reference_widget = tabs.widget(reference_index)
    if reference_widget is None:
        return [f"{preset_id} live GUI reference session action route missing active tab widget"]
    tab_bar = tabs.tabBar()
    if not hasattr(window, "tab_context_session_action_specs"):
        return [f"{preset_id} live GUI reference session action route missing action spec helper"]
    specs = window.tab_context_session_action_specs(reference_index)
    action_keys = [str(spec["key"]) for spec in specs]
    action_labels = [str(spec["label"]) for spec in specs]
    enabled_keys = [str(spec["key"]) for spec in specs if bool(spec["enabled"])]
    disabled_keys = [str(spec["key"]) for spec in specs if not bool(spec["enabled"])]
    properties = {
        route.captured_property: True,
        route.captured_tab_property: tabs.tabText(reference_index),
        route.captured_action_keys_property: action_keys,
        route.captured_action_labels_property: action_labels,
        route.captured_action_count_property: len(action_keys),
        route.captured_enabled_keys_property: enabled_keys,
        route.captured_disabled_keys_property: disabled_keys,
    }
    for widget in (tabs, reference_widget, tab_bar):
        if widget is None:
            continue
        for property_name, value in properties.items():
            widget.setProperty(property_name, value)
    return []


def capture_product_reference_surface(window: Any, preset_id: str, reference_index: int) -> list[str]:
    from PyQt6.QtWidgets import QLabel, QTextEdit, QWidget

    route = EXPECTED_PRESET_REFERENCE_SURFACE_ROUTES.get(preset_id)
    if route is None:
        return []
    tabs = window.tabs
    errors: list[str] = []
    reference_widget = tabs.widget(reference_index)
    if reference_widget is None:
        return [f"{preset_id} live GUI reference surface missing active tab widget"]
    pane = reference_widget
    if str(pane.objectName()) != route.terminal_pane_object:
        pane = reference_widget.findChild(QWidget, route.terminal_pane_object)
    if pane is None:
        return [f"{preset_id} live GUI reference surface missing terminal pane"]
    title = pane.findChild(QLabel, route.terminal_title_object)
    source = pane.findChild(QLabel, route.terminal_source_object)
    command = pane.findChild(QLabel, route.terminal_command_object)
    output = pane.findChild(QTextEdit, route.terminal_output_object)
    actual_title = title.text() if title is not None else ""
    actual_source = source.text() if source is not None else ""
    actual_command = command.text() if command is not None else ""
    actual_output = output.toPlainText() if output is not None else ""
    if not actual_command and hasattr(pane, "plan"):
        actual_command = pane.plan.printable()
    properties = {
        route.captured_property: True,
        route.captured_tab_property: tabs.tabText(reference_index),
        route.actual_title_property: actual_title,
        route.actual_source_property: actual_source,
        route.actual_command_property: actual_command,
        route.actual_output_property: actual_output,
    }
    for widget in (tabs, pane, title, source, command, output):
        if widget is None:
            continue
        for property_name, value in properties.items():
            widget.setProperty(property_name, value)
    return errors


def capture_product_reference_controls(window: Any, preset_id: str, reference_index: int) -> list[str]:
    from PyQt6.QtWidgets import QLabel, QToolButton, QWidget

    route = EXPECTED_PRESET_REFERENCE_CONTROL_ROUTES.get(preset_id)
    if route is None:
        return []
    tabs = window.tabs
    reference_widget = tabs.widget(reference_index)
    if reference_widget is None:
        return [f"{preset_id} live GUI reference controls missing active tab widget"]
    pane = reference_widget
    if str(pane.objectName()) != route.terminal_pane_object:
        pane = reference_widget.findChild(QWidget, route.terminal_pane_object)
    if pane is None:
        return [f"{preset_id} live GUI reference controls missing terminal pane"]
    status = pane.findChild(QLabel, route.terminal_status_object)
    buttons = pane.findChildren(QToolButton, route.terminal_action_object)
    action_keys = [str(button.property(route.action_key_property) or "") for button in buttons]
    status_state = str(status.property(route.status_state_property) or "") if status is not None else ""
    status_text = status.text() if status is not None else ""
    properties = {
        route.captured_property: True,
        route.captured_actions_property: action_keys,
        route.captured_status_property: status_state,
        route.captured_status_text_property: status_text,
        "presetReferenceControlCapturedTab": tabs.tabText(reference_index),
    }
    for widget in (tabs, pane, status, *buttons):
        if widget is None:
            continue
        for property_name, value in properties.items():
            widget.setProperty(property_name, value)
    return []


def capture_product_reference_input(window: Any, preset_id: str, reference_index: int) -> list[str]:
    from PyQt6.QtWidgets import QLineEdit, QWidget

    route = EXPECTED_PRESET_REFERENCE_INPUT_ROUTES.get(preset_id)
    if route is None:
        return []
    tabs = window.tabs
    reference_widget = tabs.widget(reference_index)
    if reference_widget is None:
        return [f"{preset_id} live GUI reference input missing active tab widget"]
    pane = reference_widget
    if str(pane.objectName()) != route.terminal_pane_object:
        pane = reference_widget.findChild(QWidget, route.terminal_pane_object)
    if pane is None:
        return [f"{preset_id} live GUI reference input missing terminal pane"]
    input_widget = pane.findChild(QLineEdit, route.terminal_input_object)
    if input_widget is None:
        return [f"{preset_id} live GUI reference input widget missing"]
    properties = {
        route.captured_property: True,
        route.captured_tab_property: tabs.tabText(reference_index),
        route.captured_placeholder_property: input_widget.placeholderText(),
        route.captured_text_property: input_widget.text(),
        route.captured_enabled_property: input_widget.isEnabled(),
    }
    for widget in (tabs, pane, input_widget):
        for property_name, value in properties.items():
            widget.setProperty(property_name, value)
    return []


def capture_product_reference_transcript(window: Any, preset_id: str, reference_index: int) -> list[str]:
    from PyQt6.QtWidgets import QTextEdit, QWidget

    route = EXPECTED_PRESET_REFERENCE_TRANSCRIPT_ROUTES.get(preset_id)
    if route is None:
        return []
    tabs = window.tabs
    reference_widget = tabs.widget(reference_index)
    if reference_widget is None:
        return [f"{preset_id} live GUI reference transcript missing active tab widget"]
    pane = reference_widget
    if str(pane.objectName()) != route.terminal_pane_object:
        pane = reference_widget.findChild(QWidget, route.terminal_pane_object)
    if pane is None:
        return [f"{preset_id} live GUI reference transcript missing terminal pane"]
    output_widget = pane.findChild(QTextEdit, route.terminal_output_object)
    if output_widget is None:
        return [f"{preset_id} live GUI reference transcript output widget missing"]
    transcript = output_widget.toPlainText()
    lines = transcript.splitlines()
    command_echo = next((line for line in lines if line.startswith(route.command_echo_prefix)), "")
    properties = {
        route.captured_property: True,
        route.captured_tab_property: tabs.tabText(reference_index),
        route.captured_text_property: transcript,
        route.captured_line_count_property: len(lines),
        route.captured_command_echo_property: command_echo,
    }
    for widget in (tabs, pane, output_widget):
        for property_name, value in properties.items():
            widget.setProperty(property_name, value)
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
        moba_buttons: dict[str, Any] = {}
        for button in window.findChildren(QToolButton):
            label = button.text()
            if not label:
                continue
            if label not in moba_buttons or (
                button.isVisible()
                and str(button.property("mobaIconKey") or "")
                and not moba_buttons[label].isVisible()
            ):
                moba_buttons[label] = button
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
        edge_route = EXPECTED_MOBA_RIBBON_EDGE_ACTION_ROUTE
        edge_action_keys = [edge_route.xserver_action_key, edge_route.exit_action_key]
        edge_common_properties = {
            edge_route.route_key_property: edge_route.key,
            "mobaRibbonEdgeRouteRole": edge_route.route_role,
            "mobaRibbonEdgeRouteToolbarObject": edge_route.toolbar_object,
            "mobaRibbonEdgeRouteSpacerObject": edge_route.spacer_object,
            "mobaRibbonEdgeRouteRenderSource": edge_route.render_source,
        }
        for object_name in [edge_route.toolbar_object, edge_route.spacer_object]:
            widget = window.findChild(QWidget, object_name)
            if widget is None:
                errors.append(f"mobaxterm live GUI ribbon edge route missing {object_name}")
                continue
            for property_name, expected_value in edge_common_properties.items():
                if str(widget.property(property_name) or "") != expected_value:
                    errors.append(f"mobaxterm live GUI ribbon edge route {object_name}.{property_name} drifted")
            if list(widget.property(edge_route.action_keys_property) or []) != edge_action_keys:
                errors.append(f"mobaxterm live GUI ribbon edge route {object_name} action keys drifted")
        edge_buttons = {
            edge_route.xserver_action_object: (
                edge_route.xserver_action_key,
                edge_route.xserver_action_label,
                edge_route.xserver_icon_key,
                edge_route.xserver_handler,
            ),
            edge_route.exit_action_object: (
                edge_route.exit_action_key,
                edge_route.exit_action_label,
                edge_route.exit_icon_key,
                edge_route.exit_handler,
            ),
        }
        for object_name, (action_key, label, icon_key, handler) in edge_buttons.items():
            button = window.findChild(QToolButton, object_name)
            if button is None:
                errors.append(f"mobaxterm live GUI ribbon edge route missing {object_name}")
                continue
            if button.text() != label:
                errors.append(f"mobaxterm live GUI ribbon edge route {object_name} label drifted")
            expected_properties = {
                **edge_common_properties,
                edge_route.action_key_property: action_key,
                edge_route.action_label_property: label,
                edge_route.action_object_property: object_name,
                edge_route.icon_key_property: icon_key,
                edge_route.handler_property: handler,
                "mobaIconKey": icon_key,
            }
            for property_name, expected_value in expected_properties.items():
                if str(button.property(property_name) or "") != expected_value:
                    errors.append(f"mobaxterm live GUI ribbon edge route {object_name}.{property_name} drifted")
            if list(button.property(edge_route.action_keys_property) or []) != edge_action_keys:
                errors.append(f"mobaxterm live GUI ribbon edge route {object_name} action keys drifted")
            if action_key == edge_route.xserver_action_key:
                if str(button.property("mobaRibbonEdgeRouteDialogTitle") or "") != edge_route.xserver_dialog_title:
                    errors.append("mobaxterm live GUI ribbon edge route X server dialog title drifted")
                if str(button.property("mobaRibbonEdgeRouteDialogDetail") or "") != edge_route.xserver_dialog_detail:
                    errors.append("mobaxterm live GUI ribbon edge route X server dialog detail drifted")
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
        sftp_toolbar = window.findChild(QFrame, "mobaSftpToolbar")
        sftp_queue = window.findChild(QLabel, EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE.queue_object)
        if sftp_toolbar is None:
            errors.append("mobaxterm live GUI missing SFTP toolbar")
        else:
            route_properties = {
                "mobaSftpToolbarRouteKey": EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE.key,
                "mobaSftpToolbarRouteRole": EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE.route_role,
                "mobaSftpToolbarRouteToolbarObject": EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE.toolbar_object,
                "mobaSftpToolbarRouteActionObject": EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE.action_object,
                "mobaSftpToolbarRouteTargetBrowserObject": (
                    EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE.target_browser_object
                ),
                "mobaSftpToolbarRouteTargetPathObject": EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE.target_path_object,
                "mobaSftpToolbarRouteTargetTableObject": EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE.target_table_object,
                "mobaSftpToolbarRouteQueueObject": EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE.queue_object,
                EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE.signal_property: EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE.signal,
                "mobaSftpToolbarRouteRenderSource": EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE.render_source,
            }
            for property_name, expected_value in route_properties.items():
                if str(sftp_toolbar.property(property_name) or "") != expected_value:
                    errors.append(f"mobaxterm live GUI SFTP toolbar route {property_name} drifted")
            if list(sftp_toolbar.property(EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE.action_keys_property) or []) != list(
                EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE.action_keys
            ):
                errors.append("mobaxterm live GUI SFTP toolbar route action keys drifted")
            if list(sftp_toolbar.property(EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE.action_groups_property) or []) != list(
                EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE.action_group_keys
            ):
                errors.append("mobaxterm live GUI SFTP toolbar route action groups drifted")
            if list(sftp_toolbar.property("mobaSftpToolbarRouteActionStatuses") or []) != list(
                EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE.action_statuses
            ):
                errors.append("mobaxterm live GUI SFTP toolbar route action statuses drifted")
        if sftp_queue is None:
            errors.append("mobaxterm live GUI missing SFTP transfer queue route object")
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
                expected_index = EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE.action_keys.index(key)
                route_properties = {
                    "mobaSftpToolbarRouteKey": EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE.key,
                    "mobaSftpToolbarRouteRole": EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE.route_role,
                    EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE.action_key_property: key,
                    EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE.action_label_property: expected_action.label,
                    EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE.action_object_property: (
                        EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE.action_object
                    ),
                    EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE.icon_key_property: expected_action.icon_key,
                    EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE.group_key_property: expected_action.group_key,
                    EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE.tooltip_property: expected_action.tooltip,
                    EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE.signal_property: (
                        EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE.signal
                    ),
                    EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE.handler_property: (
                        EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE.action_handlers[expected_index]
                    ),
                    "mobaSftpToolbarRouteRenderSource": EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE.render_source,
                }
                for property_name, expected_value in route_properties.items():
                    if str(button.property(property_name) or "") != expected_value:
                        errors.append(f"mobaxterm live GUI SFTP action {key!r} route {property_name} drifted")
                if list(button.property(EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE.action_keys_property) or []) != list(
                    EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE.action_keys
                ):
                    errors.append(f"mobaxterm live GUI SFTP action {key!r} route keys drifted")
                if list(button.property(EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE.action_groups_property) or []) != list(
                    EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE.action_group_keys
                ):
                    errors.append(f"mobaxterm live GUI SFTP action {key!r} route groups drifted")
                if list(button.property("mobaSftpToolbarRouteActionStatuses") or []) != list(
                    EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE.action_statuses
                ):
                    errors.append(f"mobaxterm live GUI SFTP action {key!r} route statuses drifted")
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
                raw_row_route_index = item.data(0, row_index_role)
                row_route_index = -1 if raw_row_route_index is None else int(raw_row_route_index)
                if row_route_index != row_index:
                    errors.append(f"mobaxterm live GUI SFTP row {item.text(0)!r} routed-row index drifted")
                selected_by_route = bool(item.data(0, row_selected_by_route_role))
                if selected_by_route != (row_index == 0):
                    errors.append(f"mobaxterm live GUI SFTP row {item.text(0)!r} selected-by-route metadata drifted")
            if routed_row_paths and len(set(routed_row_paths)) != 1:
                errors.append(f"mobaxterm live GUI SFTP routed row paths diverged: {routed_row_paths}")
            if sftp_path is not None and routed_row_paths and any(path != sftp_path.text() for path in routed_row_paths):
                errors.append("mobaxterm live GUI SFTP routed row paths must match the active SFTP path")
        errors.extend(
            check_live_moba_sftp_toolbar_action_route(
                connected_dock,
                sftp_browser,
                sftp_toolbar,
                sftp_path,
                sftp_table,
                sftp_queue,
                sftp_buttons,
            )
        )
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
            control_route = EXPECTED_MOBA_REMOTE_MONITORING_CONTROL_ROUTE
            if control_route.signal != "toggled":
                errors.append("mobaxterm live GUI monitoring control route signal drifted")
            if control_route.handler != "handle_moba_remote_monitoring_toggled":
                errors.append("mobaxterm live GUI monitoring control route handler drifted")
            if control_route.live_checked_property != "mobaRemoteMonitoringControlLiveChecked":
                errors.append("mobaxterm live GUI monitoring control route live checked property drifted")
            control_route_properties = {
                "mobaRemoteMonitoringControlRouteKey": control_route.key,
                "mobaRemoteMonitoringControlRouteRole": control_route.route_role,
                "mobaRemoteMonitoringControlSourcePanelObject": control_route.source_panel_object,
                "mobaRemoteMonitoringControlSourceObject": control_route.source_control_object,
                "mobaRemoteMonitoringControlSourceKey": control_route.source_control_key,
                "mobaRemoteMonitoringControlSourceLabel": control_route.source_control_label,
                "mobaRemoteMonitoringControlSourceType": control_route.source_control_type,
                "mobaRemoteMonitoringControlCommandProperty": control_route.command_property,
                "mobaRemoteMonitoringControlRefreshProperty": control_route.refresh_seconds_property,
                "mobaRemoteMonitoringControlCheckedProperty": control_route.checked_property,
                "mobaRemoteMonitoringControlTelemetryRouteKey": control_route.telemetry_route_key,
                "mobaRemoteMonitoringControlTelemetrySurface": control_route.telemetry_surface,
                "mobaRemoteMonitoringControlTargetBarObject": control_route.target_bar_object,
                control_route.signal_property: control_route.signal,
                control_route.handler_property: control_route.handler,
                "mobaRemoteMonitoringControlRenderSource": control_route.render_source,
            }
            for property_name, expected_value in control_route_properties.items():
                if str(monitoring_panel.property(property_name) or "") != expected_value:
                    errors.append(f"mobaxterm live GUI monitoring control route panel {property_name} drifted")
            if bool(monitoring_panel.property("mobaRemoteMonitoringControlExpectedChecked")) != (
                control_route.expected_checked
            ):
                errors.append("mobaxterm live GUI monitoring control route panel expected checked state drifted")
            if list(monitoring_panel.property("mobaRemoteMonitoringControlTargetMetricCellKeys") or []) != list(
                control_route.target_metric_cell_keys
            ):
                errors.append("mobaxterm live GUI monitoring control route panel target metric cells drifted")
            if bool(monitoring_panel.property(control_route.captured_property)) is not True:
                errors.append("mobaxterm live GUI monitoring control route panel captured flag missing")
            if bool(monitoring_panel.property(control_route.captured_checked_property)) != control_route.expected_checked:
                errors.append("mobaxterm live GUI monitoring control route panel captured checked state drifted")
            if bool(monitoring_panel.property(control_route.live_checked_property)) != control_route.expected_checked:
                errors.append("mobaxterm live GUI monitoring control route panel live checked state drifted")
            captured_command = str(monitoring_panel.property(control_route.captured_command_property) or "")
            if captured_command != command:
                errors.append("mobaxterm live GUI monitoring control route panel captured command drifted")
            if int(monitoring_panel.property(control_route.captured_refresh_seconds_property) or 0) != (
                EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME.refresh_seconds
            ):
                errors.append("mobaxterm live GUI monitoring control route panel captured refresh cadence drifted")
            follow_control_route = EXPECTED_MOBA_FOLLOW_TERMINAL_FOLDER_CONTROL_ROUTE
            if follow_control_route.signal != "toggled":
                errors.append("mobaxterm live GUI follow-folder control route signal drifted")
            if follow_control_route.handler != "handle_moba_follow_terminal_folder_toggled":
                errors.append("mobaxterm live GUI follow-folder control route handler drifted")
            if follow_control_route.live_checked_property != "mobaFollowTerminalFolderControlLiveChecked":
                errors.append("mobaxterm live GUI follow-folder control route live checked property drifted")
            follow_control_route_properties = {
                "mobaFollowTerminalFolderControlRouteKey": follow_control_route.key,
                "mobaFollowTerminalFolderControlRouteRole": follow_control_route.route_role,
                "mobaFollowTerminalFolderControlSourcePanelObject": follow_control_route.source_panel_object,
                "mobaFollowTerminalFolderControlSourceObject": follow_control_route.source_control_object,
                "mobaFollowTerminalFolderControlSourceKey": follow_control_route.source_control_key,
                "mobaFollowTerminalFolderControlSourceLabel": follow_control_route.source_control_label,
                "mobaFollowTerminalFolderControlSourceType": follow_control_route.source_control_type,
                "mobaFollowTerminalFolderControlSourcePathProperty": follow_control_route.source_path_property,
                "mobaFollowTerminalFolderControlSourcePlanProperty": follow_control_route.source_plan_property,
                "mobaFollowTerminalFolderControlSourceEnabledProperty": follow_control_route.source_enabled_property,
                "mobaFollowTerminalFolderControlTargetBrowserObject": follow_control_route.target_browser_object,
                "mobaFollowTerminalFolderControlTargetPathObject": follow_control_route.target_path_object,
                "mobaFollowTerminalFolderControlTargetTableObject": follow_control_route.target_table_object,
                "mobaFollowTerminalFolderControlTargetPathProperty": follow_control_route.target_path_property,
                "mobaFollowTerminalFolderControlTargetPlanProperty": follow_control_route.target_plan_property,
                "mobaFollowTerminalFolderControlTargetEnabledProperty": follow_control_route.target_enabled_property,
                follow_control_route.signal_property: follow_control_route.signal,
                follow_control_route.handler_property: follow_control_route.handler,
                "mobaFollowTerminalFolderControlRenderSource": follow_control_route.render_source,
            }
            for property_name, expected_value in follow_control_route_properties.items():
                if str(monitoring_panel.property(property_name) or "") != expected_value:
                    errors.append(f"mobaxterm live GUI follow-folder control route panel {property_name} drifted")
            if bool(monitoring_panel.property("mobaFollowTerminalFolderControlExpectedChecked")) != (
                follow_control_route.expected_checked
            ):
                errors.append("mobaxterm live GUI follow-folder control route panel expected checked state drifted")
            if bool(monitoring_panel.property(follow_control_route.captured_property)) is not True:
                errors.append("mobaxterm live GUI follow-folder control route panel captured flag missing")
            if bool(monitoring_panel.property(follow_control_route.captured_checked_property)) != (
                follow_control_route.expected_checked
            ):
                errors.append("mobaxterm live GUI follow-folder control route panel captured checked state drifted")
            if bool(monitoring_panel.property(follow_control_route.live_checked_property)) != (
                follow_control_route.expected_checked
            ):
                errors.append("mobaxterm live GUI follow-folder control route panel live checked state drifted")
            captured_follow_path = str(monitoring_panel.property(follow_control_route.captured_path_property) or "")
            if not captured_follow_path.startswith("/"):
                errors.append("mobaxterm live GUI follow-folder control route panel captured path missing")
            captured_follow_plan = str(monitoring_panel.property(follow_control_route.captured_plan_property) or "")
            if captured_follow_path not in captured_follow_plan or "ls -la " not in captured_follow_plan:
                errors.append("mobaxterm live GUI follow-folder control route panel captured plan drifted")
            if str(monitoring_panel.property(follow_control_route.live_path_property) or "") != captured_follow_path:
                errors.append("mobaxterm live GUI follow-folder control route panel live path drifted")
            if str(monitoring_panel.property(follow_control_route.live_plan_property) or "") != captured_follow_plan:
                errors.append("mobaxterm live GUI follow-folder control route panel live plan drifted")
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
                    actual_property_value = widget.property(property_name)
                    actual_value = -1 if actual_property_value is None else int(actual_property_value)
                    if actual_value != expected_value:
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
                actual_font_size = widget.font().pointSize()
                if actual_font_size < 0:
                    actual_font_size = widget.font().pixelSize()
                if actual_font_size != geometry.label_font_size:
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
                control_route = EXPECTED_MOBA_REMOTE_MONITORING_CONTROL_ROUTE
                if control_route.signal != "toggled":
                    errors.append("mobaxterm live GUI remote-monitoring control route signal drifted")
                if control_route.handler != "handle_moba_remote_monitoring_toggled":
                    errors.append("mobaxterm live GUI remote-monitoring control route handler drifted")
                if control_route.live_checked_property != "mobaRemoteMonitoringControlLiveChecked":
                    errors.append("mobaxterm live GUI remote-monitoring control route live checked property drifted")
                control_route_properties = {
                    "mobaRemoteMonitoringControlRouteKey": control_route.key,
                    "mobaRemoteMonitoringControlRouteRole": control_route.route_role,
                    "mobaRemoteMonitoringControlSourcePanelObject": control_route.source_panel_object,
                    "mobaRemoteMonitoringControlSourceObject": control_route.source_control_object,
                    "mobaRemoteMonitoringControlSourceKey": control_route.source_control_key,
                    "mobaRemoteMonitoringControlSourceLabel": control_route.source_control_label,
                    "mobaRemoteMonitoringControlSourceType": control_route.source_control_type,
                    "mobaRemoteMonitoringControlCommandProperty": control_route.command_property,
                    "mobaRemoteMonitoringControlRefreshProperty": control_route.refresh_seconds_property,
                    "mobaRemoteMonitoringControlCheckedProperty": control_route.checked_property,
                    "mobaRemoteMonitoringControlTelemetryRouteKey": control_route.telemetry_route_key,
                    "mobaRemoteMonitoringControlTelemetrySurface": control_route.telemetry_surface,
                    "mobaRemoteMonitoringControlTargetBarObject": control_route.target_bar_object,
                    control_route.signal_property: control_route.signal,
                    control_route.handler_property: control_route.handler,
                    "mobaRemoteMonitoringControlRenderSource": control_route.render_source,
                }
                for property_name, expected_value in control_route_properties.items():
                    if str(widget.property(property_name) or "") != expected_value:
                        errors.append(f"mobaxterm live GUI remote-monitoring control route {property_name} drifted")
                if bool(widget.property("mobaRemoteMonitoringControlExpectedChecked")) != control_route.expected_checked:
                    errors.append("mobaxterm live GUI remote-monitoring control route expected checked state drifted")
                if list(widget.property("mobaRemoteMonitoringControlTargetMetricCellKeys") or []) != list(
                    control_route.target_metric_cell_keys
                ):
                    errors.append("mobaxterm live GUI remote-monitoring control route target metric cells drifted")
                if bool(widget.property(control_route.checked_property)) != widget.isChecked():
                    errors.append("mobaxterm live GUI remote-monitoring control route checked property drifted")
                if bool(widget.property(control_route.captured_property)) is not True:
                    errors.append("mobaxterm live GUI remote-monitoring control route captured flag missing")
                if bool(widget.property(control_route.captured_checked_property)) != widget.isChecked():
                    errors.append("mobaxterm live GUI remote-monitoring control route captured checked state drifted")
                if bool(widget.property(control_route.live_checked_property)) != widget.isChecked():
                    errors.append("mobaxterm live GUI remote-monitoring control route live checked state drifted")
                command = str(widget.property("mobaMonitoringCommand") or "")
                if "sh -lc" not in command or "/proc" not in command:
                    errors.append("mobaxterm live GUI remote-monitoring control missing command evidence")
                if int(widget.property("mobaMonitoringRefreshSeconds") or 0) != (
                    EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME.refresh_seconds
                ):
                    errors.append("mobaxterm live GUI remote-monitoring control refresh cadence drifted")
                if str(widget.property(control_route.captured_command_property) or "") != command:
                    errors.append("mobaxterm live GUI remote-monitoring control route captured command drifted")
                if int(widget.property(control_route.captured_refresh_seconds_property) or 0) != (
                    EXPECTED_MOBA_REMOTE_MONITORING_DOCK_CHROME.refresh_seconds
                ):
                    errors.append("mobaxterm live GUI remote-monitoring control route captured refresh cadence drifted")
                original_checked = widget.isChecked()
                widget.setChecked(not original_checked)
                if bool(widget.property(control_route.live_checked_property)) != (not original_checked):
                    errors.append("mobaxterm live GUI remote-monitoring control route toggled state did not update")
                widget.setChecked(original_checked)
                if bool(widget.property(control_route.live_checked_property)) != original_checked:
                    errors.append("mobaxterm live GUI remote-monitoring control route restored state did not update")
            if control.key == "follow-terminal-folder":
                follow_control_route = EXPECTED_MOBA_FOLLOW_TERMINAL_FOLDER_CONTROL_ROUTE
                if follow_control_route.signal != "toggled":
                    errors.append("mobaxterm live GUI follow-folder control route signal drifted")
                if follow_control_route.handler != "handle_moba_follow_terminal_folder_toggled":
                    errors.append("mobaxterm live GUI follow-folder control route handler drifted")
                if follow_control_route.live_checked_property != "mobaFollowTerminalFolderControlLiveChecked":
                    errors.append("mobaxterm live GUI follow-folder control route live checked property drifted")
                follow_control_route_properties = {
                    "mobaFollowTerminalFolderControlRouteKey": follow_control_route.key,
                    "mobaFollowTerminalFolderControlRouteRole": follow_control_route.route_role,
                    "mobaFollowTerminalFolderControlSourcePanelObject": follow_control_route.source_panel_object,
                    "mobaFollowTerminalFolderControlSourceObject": follow_control_route.source_control_object,
                    "mobaFollowTerminalFolderControlSourceKey": follow_control_route.source_control_key,
                    "mobaFollowTerminalFolderControlSourceLabel": follow_control_route.source_control_label,
                    "mobaFollowTerminalFolderControlSourceType": follow_control_route.source_control_type,
                    "mobaFollowTerminalFolderControlSourcePathProperty": follow_control_route.source_path_property,
                    "mobaFollowTerminalFolderControlSourcePlanProperty": follow_control_route.source_plan_property,
                    "mobaFollowTerminalFolderControlSourceEnabledProperty": follow_control_route.source_enabled_property,
                    "mobaFollowTerminalFolderControlTargetBrowserObject": follow_control_route.target_browser_object,
                    "mobaFollowTerminalFolderControlTargetPathObject": follow_control_route.target_path_object,
                    "mobaFollowTerminalFolderControlTargetTableObject": follow_control_route.target_table_object,
                    "mobaFollowTerminalFolderControlTargetPathProperty": follow_control_route.target_path_property,
                    "mobaFollowTerminalFolderControlTargetPlanProperty": follow_control_route.target_plan_property,
                    "mobaFollowTerminalFolderControlTargetEnabledProperty": follow_control_route.target_enabled_property,
                    follow_control_route.signal_property: follow_control_route.signal,
                    follow_control_route.handler_property: follow_control_route.handler,
                    "mobaFollowTerminalFolderControlRenderSource": follow_control_route.render_source,
                }
                for property_name, expected_value in follow_control_route_properties.items():
                    if str(widget.property(property_name) or "") != expected_value:
                        errors.append(f"mobaxterm live GUI follow-folder control route {property_name} drifted")
                if bool(widget.property("mobaFollowTerminalFolderControlExpectedChecked")) != (
                    follow_control_route.expected_checked
                ):
                    errors.append("mobaxterm live GUI follow-folder control route expected checked state drifted")
                if bool(widget.property(follow_control_route.captured_property)) is not True:
                    errors.append("mobaxterm live GUI follow-folder control route captured flag missing")
                if bool(widget.property(follow_control_route.captured_checked_property)) != widget.isChecked():
                    errors.append("mobaxterm live GUI follow-folder control route captured checked state drifted")
                if bool(widget.property(follow_control_route.live_checked_property)) != widget.isChecked():
                    errors.append("mobaxterm live GUI follow-folder control route live checked state drifted")
                follow_plan = str(widget.property("mobaMonitoringFollowPlan") or "")
                if "ls -la /" not in follow_plan:
                    errors.append("mobaxterm live GUI follow-terminal-folder control missing SFTP plan evidence")
                follow_path = str(widget.property("mobaMonitoringFollowPath") or "")
                if not follow_path.startswith("/"):
                    errors.append("mobaxterm live GUI follow-terminal-folder control missing remote path metadata")
                if str(widget.property(follow_control_route.captured_path_property) or "") != follow_path:
                    errors.append("mobaxterm live GUI follow-folder control route captured path drifted")
                if str(widget.property(follow_control_route.captured_plan_property) or "") != follow_plan:
                    errors.append("mobaxterm live GUI follow-folder control route captured plan drifted")
                if str(widget.property(follow_control_route.live_path_property) or "") != follow_path:
                    errors.append("mobaxterm live GUI follow-folder control route live path drifted")
                if str(widget.property(follow_control_route.live_plan_property) or "") != follow_plan:
                    errors.append("mobaxterm live GUI follow-folder control route live plan drifted")
                original_checked = widget.isChecked()
                widget.setChecked(not original_checked)
                if bool(widget.property(follow_control_route.live_checked_property)) != (not original_checked):
                    errors.append("mobaxterm live GUI follow-folder control route toggled state did not update")
                widget.setChecked(original_checked)
                if bool(widget.property(follow_control_route.live_checked_property)) != original_checked:
                    errors.append("mobaxterm live GUI follow-folder control route restored state did not update")
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
        if telemetry_cells:
            telemetry_geometry_errors = live_widget_non_overlap_errors(
                "mobaxterm live GUI telemetry cells",
                telemetry_cells,
            )
            errors.extend(telemetry_geometry_errors)
        for cell, preferred_width in zip(
            telemetry_cells,
            EXPECTED_MOBA_TELEMETRY_CELL_WIDTHS,
            strict=False,
        ):
            live_preferred = int(
                cell.property("mobaTelemetryLivePreferredWidth") or 0
            )
            if live_preferred != preferred_width:
                errors.append(
                    "mobaxterm live GUI telemetry preferred-width metadata drifted"
                )
            if cell.minimumWidth() != 0 or cell.width() <= 0:
                errors.append(
                    "mobaxterm live GUI telemetry compact cell geometry drifted"
                )
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
            route_properties = {
                "mobaRightUtilityRouteKey": EXPECTED_MOBA_RIGHT_UTILITY_ACTION_ROUTE.key,
                "mobaRightUtilityRouteRole": EXPECTED_MOBA_RIGHT_UTILITY_ACTION_ROUTE.route_role,
                "mobaRightUtilityRouteRailObject": EXPECTED_MOBA_RIGHT_UTILITY_ACTION_ROUTE.rail_object,
                "mobaRightUtilityRouteActionObject": EXPECTED_MOBA_RIGHT_UTILITY_ACTION_ROUTE.action_object,
                "mobaRightUtilityRouteRenderSource": EXPECTED_MOBA_RIGHT_UTILITY_ACTION_ROUTE.render_source,
            }
            for property_name, expected_value in route_properties.items():
                if str(utility_rail.property(property_name) or "") != expected_value:
                    errors.append(f"mobaxterm live GUI right utility action route rail {property_name} drifted")
            if list(utility_rail.property(EXPECTED_MOBA_RIGHT_UTILITY_ACTION_ROUTE.action_keys_property) or []) != list(
                EXPECTED_MOBA_RIGHT_UTILITY_ACTION_ROUTE.action_keys
            ):
                errors.append("mobaxterm live GUI right utility action route rail keys drifted")
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
                expected_index = EXPECTED_MOBA_RIGHT_UTILITY_ACTION_ROUTE.action_keys.index(key)
                route_properties = {
                    "mobaRightUtilityRouteKey": EXPECTED_MOBA_RIGHT_UTILITY_ACTION_ROUTE.key,
                    "mobaRightUtilityRouteRole": EXPECTED_MOBA_RIGHT_UTILITY_ACTION_ROUTE.route_role,
                    EXPECTED_MOBA_RIGHT_UTILITY_ACTION_ROUTE.action_key_property: key,
                    EXPECTED_MOBA_RIGHT_UTILITY_ACTION_ROUTE.action_label_property: expected_action.label,
                    EXPECTED_MOBA_RIGHT_UTILITY_ACTION_ROUTE.action_object_property: (
                        EXPECTED_MOBA_RIGHT_UTILITY_ACTION_ROUTE.action_object
                    ),
                    EXPECTED_MOBA_RIGHT_UTILITY_ACTION_ROUTE.icon_key_property: expected_action.icon_key,
                    EXPECTED_MOBA_RIGHT_UTILITY_ACTION_ROUTE.handler_property: (
                        EXPECTED_MOBA_RIGHT_UTILITY_ACTION_ROUTE.action_handlers[expected_index]
                    ),
                    "mobaRightUtilityRouteRenderSource": EXPECTED_MOBA_RIGHT_UTILITY_ACTION_ROUTE.render_source,
                }
                for property_name, expected_value in route_properties.items():
                    if str(button.property(property_name) or "") != expected_value:
                        errors.append(f"mobaxterm live GUI right utility action {key!r} route {property_name} drifted")
                if list(button.property(EXPECTED_MOBA_RIGHT_UTILITY_ACTION_ROUTE.action_keys_property) or []) != list(
                    EXPECTED_MOBA_RIGHT_UTILITY_ACTION_ROUTE.action_keys
                ):
                    errors.append(f"mobaxterm live GUI right utility action {key!r} route keys drifted")
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
            route_properties = {
                "mobaSessionEdgeRouteKey": EXPECTED_MOBA_SESSION_EDGE_ACTION_ROUTE.key,
                "mobaSessionEdgeRouteRole": EXPECTED_MOBA_SESSION_EDGE_ACTION_ROUTE.route_role,
                "mobaSessionEdgeRouteControlsObject": EXPECTED_MOBA_SESSION_EDGE_ACTION_ROUTE.controls_object,
                "mobaSessionEdgeRouteActionObject": EXPECTED_MOBA_SESSION_EDGE_ACTION_ROUTE.action_object,
                "mobaSessionEdgeRoutePlacement": EXPECTED_MOBA_SESSION_EDGE_ACTION_ROUTE.placement,
                "mobaSessionEdgeRouteRenderSource": EXPECTED_MOBA_SESSION_EDGE_ACTION_ROUTE.render_source,
            }
            for property_name, expected_value in route_properties.items():
                if str(edge_controls.property(property_name) or "") != expected_value:
                    errors.append(f"mobaxterm live GUI session edge action route controls {property_name} drifted")
            if list(edge_controls.property(EXPECTED_MOBA_SESSION_EDGE_ACTION_ROUTE.action_keys_property) or []) != list(
                EXPECTED_MOBA_SESSION_EDGE_ACTION_ROUTE.action_keys
            ):
                errors.append("mobaxterm live GUI session edge action route controls keys drifted")
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
                expected_index = EXPECTED_MOBA_SESSION_EDGE_ACTION_ROUTE.action_keys.index(key)
                route_properties = {
                    "mobaSessionEdgeRouteKey": EXPECTED_MOBA_SESSION_EDGE_ACTION_ROUTE.key,
                    "mobaSessionEdgeRouteRole": EXPECTED_MOBA_SESSION_EDGE_ACTION_ROUTE.route_role,
                    EXPECTED_MOBA_SESSION_EDGE_ACTION_ROUTE.action_key_property: key,
                    EXPECTED_MOBA_SESSION_EDGE_ACTION_ROUTE.action_label_property: expected_action.label,
                    EXPECTED_MOBA_SESSION_EDGE_ACTION_ROUTE.action_object_property: (
                        EXPECTED_MOBA_SESSION_EDGE_ACTION_ROUTE.action_object
                    ),
                    EXPECTED_MOBA_SESSION_EDGE_ACTION_ROUTE.icon_key_property: expected_action.icon_key,
                    EXPECTED_MOBA_SESSION_EDGE_ACTION_ROUTE.handler_property: (
                        EXPECTED_MOBA_SESSION_EDGE_ACTION_ROUTE.action_handlers[expected_index]
                    ),
                    "mobaSessionEdgeRouteRenderSource": EXPECTED_MOBA_SESSION_EDGE_ACTION_ROUTE.render_source,
                }
                for property_name, expected_value in route_properties.items():
                    if str(button.property(property_name) or "") != expected_value:
                        errors.append(f"mobaxterm live GUI session edge shortcut {key!r} route {property_name} drifted")
                if list(button.property(EXPECTED_MOBA_SESSION_EDGE_ACTION_ROUTE.action_keys_property) or []) != list(
                    EXPECTED_MOBA_SESSION_EDGE_ACTION_ROUTE.action_keys
                ):
                    errors.append(f"mobaxterm live GUI session edge shortcut {key!r} route keys drifted")
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
        errors.extend(check_live_moba_connected_session_action_route(window))
        errors.extend(check_live_moba_connected_session_identity_route(window))
        errors.extend(check_live_moba_sftp_terminal_folder_route(window))
        errors.extend(check_live_moba_home_welcome(window))
    else:
        errors.extend(check_live_preset_catalog_route(window))
        errors.extend(check_live_preset_isolation_route(window, preset_id))
        errors.extend(check_live_preset_transition_route(window, preset_id))
        errors.extend(check_live_preset_selection_route(window, preset_id))
        errors.extend(check_live_preset_visual_signature(window, preset_id))
        errors.extend(check_live_preset_keyboard_shortcut_route(window, preset_id))
        errors.extend(check_live_preset_command_surface_route(window, preset_id))
        errors.extend(check_live_preset_focus_interaction_route(window, preset_id))
        errors.extend(check_live_preset_home_search_route(window, preset_id))
        errors.extend(check_live_workflow_cards(window, preset_id))
        errors.extend(check_live_workspace_surface(window, preset_id))
        errors.extend(check_live_reference_state(window, preset_id))
        errors.extend(check_live_product_identity_route(window, preset_id))
        errors.extend(check_live_preset_reference_tab_route(window, preset_id))
        errors.extend(check_live_preset_reference_tab_chrome_route(window, preset_id))
        errors.extend(check_live_preset_reference_status_bar_route(window, preset_id))
        errors.extend(check_live_preset_reference_session_action_route(window, preset_id))
        errors.extend(check_live_preset_reference_surface_route(window, preset_id))
        errors.extend(check_live_preset_reference_control_route(window, preset_id))
        errors.extend(check_live_preset_reference_input_route(window, preset_id))
        errors.extend(check_live_preset_reference_transcript_route(window, preset_id))
        if preset_id == "securecrt":
            errors.extend(check_live_securecrt_top_chrome(window))
            errors.extend(check_live_securecrt_session_manager_chrome(window))
            errors.extend(check_live_securecrt_session_status_strip(window))
            errors.extend(check_live_securecrt_session_manager_route(window))
            errors.extend(check_live_securecrt_session_manager_filter_route(window))
            errors.extend(check_live_securecrt_sftp_tab_route(window))
            errors.extend(check_live_securecrt_sftp_browser_route(window))
            errors.extend(check_live_securecrt_command_window(window))
        if preset_id == "remmina":
            errors.extend(check_live_remmina_profile_list_chrome(window))
            errors.extend(check_live_remmina_viewer_controls(window))
            errors.extend(check_live_remmina_profile_viewer_route(window))
            errors.extend(check_live_remmina_profile_filter_route(window))
            errors.extend(check_live_remmina_clipboard_route(window))
            errors.extend(check_live_remmina_screenshot_route(window))
            errors.extend(check_live_remmina_sftp_transfer_route(window))
        if preset_id == "termius":
            errors.extend(check_live_termius_hosts_chrome(window))
            errors.extend(check_live_termius_header_chips(window))
            errors.extend(check_live_termius_host_identity_strip(window))
            errors.extend(check_live_termius_host_selection_route(window))
            errors.extend(check_live_termius_sync_route(window))
            errors.extend(check_live_termius_port_forward_route(window))
            errors.extend(check_live_termius_snippet_route(window))
            errors.extend(check_live_termius_files_browser_route(window))
        if preset_id == "mremoteng":
            errors.extend(check_live_mremoteng_top_chrome(window))
            errors.extend(check_live_mremoteng_document_controls(window))
            errors.extend(check_live_mremoteng_property_grid(window))
            errors.extend(check_live_mremoteng_connection_document_route(window))
            errors.extend(check_live_mremoteng_document_filter_route(window))
            errors.extend(check_live_mremoteng_inheritance_route(window))
    if preset_id == "mobaxterm":
        errors.extend(check_live_preset_catalog_route(window))
        errors.extend(check_live_preset_isolation_route(window, preset_id))
        errors.extend(check_live_preset_transition_route(window, preset_id))
        errors.extend(check_live_preset_selection_route(window, preset_id))
        errors.extend(check_live_preset_visual_signature(window, preset_id))
        errors.extend(check_live_preset_keyboard_shortcut_route(window, preset_id))
        errors.extend(check_live_preset_command_surface_route(window, preset_id))
        errors.extend(check_live_preset_focus_interaction_route(window, preset_id))
        errors.extend(check_live_preset_home_search_route(window, preset_id))
    errors.extend(check_live_interaction_state(window, preset_id))
    return errors


def live_tab_labels(tabs: Any) -> set[str]:
    return {tabs.tabText(index) for index in range(tabs.count())}


def check_live_preset_catalog_route(window: Any) -> list[str]:
    from PyQt6.QtWidgets import QComboBox, QWidget

    route = EXPECTED_PRESET_CATALOG_ROUTE
    errors: list[str] = []
    selector = window.findChild(QComboBox, route.selector_object)
    route_widgets: list[tuple[str, Any]] = [
        ("window", window),
        ("selector", selector),
        ("main-toolbar", window.findChild(QWidget, "mainToolbar")),
    ]
    route_properties = {
        "presetCatalogRouteKey": route.key,
        "presetCatalogRouteRole": route.route_role,
        "presetCatalogRouteSelectorObject": route.selector_object,
        "presetCatalogRouteDefaultPresetId": route.default_preset_id,
        "presetCatalogRouteDefaultPresetLabel": route.default_preset_label,
        "presetCatalogRouteSelectorProperty": route.selector_property,
        "presetCatalogRouteOptionLabelsProperty": route.option_labels_property,
        "presetCatalogRouteProductIdsProperty": route.product_ids_property,
        "presetCatalogRouteDefaultProperty": route.default_property,
        "presetCatalogRouteRenderSource": route.render_source,
    }
    route_value_properties = {
        "presetCatalogRouteOptionCount": route.option_count,
        "presetCatalogRouteProductOptionCount": route.product_option_count,
    }
    route_list_properties = {
        "presetCatalogRouteOptionIds": list(route.option_ids),
        "presetCatalogRouteOptionLabels": list(route.option_labels),
        "presetCatalogRouteProductPresetIds": list(route.product_preset_ids),
        "presetCatalogRouteProductPresetLabels": list(route.product_preset_labels),
    }
    for label, widget in route_widgets:
        if widget is None:
            errors.append(f"live GUI preset catalog route missing {label}")
            continue
        for property_name, expected_value in route_properties.items():
            actual_value = str(widget.property(property_name) or "")
            if actual_value != expected_value:
                errors.append(
                    f"live GUI preset catalog {label} property "
                    f"{property_name} {actual_value!r} must equal {expected_value!r}"
                )
        for property_name, expected_value in route_value_properties.items():
            actual_value = widget.property(property_name)
            if actual_value != expected_value:
                errors.append(
                    f"live GUI preset catalog {label} property "
                    f"{property_name} {actual_value!r} must equal {expected_value!r}"
                )
        for property_name, expected_value in route_list_properties.items():
            actual_value = list(widget.property(property_name) or [])
            if actual_value != expected_value:
                errors.append(f"live GUI preset catalog {label} property {property_name} drifted")

    if selector is None:
        errors.append("live GUI preset catalog missing selector")
    else:
        option_ids = [selector.itemData(index) for index in range(selector.count())]
        option_labels = [selector.itemText(index) for index in range(selector.count())]
        if option_ids != list(route.option_ids):
            errors.append(f"live GUI preset catalog option ids drifted: {option_ids!r}")
        if option_labels != list(route.option_labels):
            errors.append(f"live GUI preset catalog option labels drifted: {option_labels!r}")
        if selector.count() != route.option_count:
            errors.append("live GUI preset catalog option count drifted")
        if selector.findData(route.default_preset_id) != 0:
            errors.append("live GUI preset catalog default preset must remain first")
    return errors


def check_live_preset_isolation_route(window: Any, preset_id: str) -> list[str]:
    from PyQt6.QtWidgets import QWidget

    route = EXPECTED_PRESET_ISOLATION_ROUTES[preset_id]
    errors: list[str] = []
    route_widgets: list[tuple[str, Any]] = [
        ("window", window),
        ("selector", window.findChild(QWidget, "designSelect")),
        ("main-toolbar", window.findChild(QWidget, "mainToolbar")),
    ]
    route_properties = {
        "presetIsolationRouteKey": route.key,
        "presetIsolationRouteRole": route.route_role,
        "presetIsolationRoutePresetId": route.preset_id,
        "presetIsolationVisibleProperty": route.visible_property,
        "presetIsolationHiddenProperty": route.hidden_property,
        "presetIsolationRenderSource": route.render_source,
    }
    route_list_properties = {
        route.visible_property: list(route.visible_objects),
        route.hidden_property: list(route.hidden_objects),
    }
    for label, widget in route_widgets:
        if widget is None:
            errors.append(f"{preset_id} live GUI preset isolation route missing {label}")
            continue
        for property_name, expected_value in route_properties.items():
            actual_value = str(widget.property(property_name) or "")
            if actual_value != expected_value:
                errors.append(
                    f"{preset_id} live GUI preset isolation {label} property "
                    f"{property_name} {actual_value!r} must equal {expected_value!r}"
                )
        for property_name, expected_value in route_list_properties.items():
            actual_value = list(widget.property(property_name) or [])
            if actual_value != expected_value:
                errors.append(f"{preset_id} live GUI preset isolation {label} property {property_name} drifted")

    overlap = set(route.visible_objects) & set(route.hidden_objects)
    if overlap:
        errors.append(f"{preset_id} live GUI preset isolation has overlapping objects: {sorted(overlap)}")
    for object_name in route.visible_objects:
        widget = visible_child(window, QWidget, object_name)
        if widget is None:
            errors.append(f"{preset_id} live GUI preset isolation missing visible object {object_name}")
        elif not widget.isVisible():
            errors.append(f"{preset_id} live GUI preset isolation visible object is hidden: {object_name}")
    for object_name in route.hidden_objects:
        visible_matches = [widget for widget in window.findChildren(QWidget, object_name) if widget.isVisible()]
        if visible_matches:
            errors.append(f"{preset_id} live GUI preset isolation hidden object is visible: {object_name}")
    return errors


def visible_child(window: Any, widget_type: Any, object_name: str) -> Any | None:
    matches = window.findChildren(widget_type, object_name)
    visible_matches = [widget for widget in matches if widget.isVisible()]
    return visible_matches[0] if visible_matches else (matches[0] if matches else None)


def check_live_preset_transition_route(window: Any, preset_id: str) -> list[str]:
    from PyQt6.QtWidgets import QComboBox, QWidget

    route = EXPECTED_PRESET_TRANSITION_ROUTES[preset_id]
    errors: list[str] = []
    selector = window.findChild(QComboBox, route.selector_object)
    route_widgets: list[tuple[str, Any]] = [
        ("window", window),
        ("selector", selector),
        ("main-toolbar", window.findChild(QWidget, "mainToolbar")),
    ]
    route_properties = {
        "presetTransitionRouteKey": route.key,
        "presetTransitionRouteRole": route.route_role,
        "presetTransitionToPresetId": route.to_preset_id,
        "presetTransitionToPresetIndex": route.to_preset_index,
        "presetTransitionSelectorObject": route.selector_object,
        "presetTransitionRouteProperty": route.route_property,
        "presetTransitionFromProperty": route.from_property,
        "presetTransitionToProperty": route.to_property,
        "presetTransitionResetProperty": route.reset_property,
        "presetTransitionRenderSource": route.render_source,
    }
    route_list_properties = {
        route.from_property: list(route.from_preset_ids),
        route.reset_property: list(route.reset_objects),
    }
    for label, widget in route_widgets:
        if widget is None:
            errors.append(f"{preset_id} live GUI preset transition route missing {label}")
            continue
        for property_name, expected_value in route_properties.items():
            actual_value = widget.property(property_name)
            if actual_value != expected_value:
                errors.append(
                    f"{preset_id} live GUI preset transition {label} property "
                    f"{property_name} drifted: {actual_value!r} != {expected_value!r}"
                )
        for property_name, expected_values in route_list_properties.items():
            actual_values = list(widget.property(property_name) or [])
            if actual_values != expected_values:
                errors.append(
                    f"{preset_id} live GUI preset transition {label} property "
                    f"{property_name} drifted: {actual_values!r} != {expected_values!r}"
                )
    if selector is not None:
        if selector.currentData() != route.to_preset_id:
            errors.append(f"{preset_id} live GUI preset transition selector target drifted")
        if selector.currentIndex() != route.to_preset_index:
            errors.append(f"{preset_id} live GUI preset transition selector index drifted")
        for source_id in route.from_preset_ids:
            if selector.findData(source_id) < 0:
                errors.append(f"{preset_id} live GUI preset transition missing source preset: {source_id}")
    if route.to_preset_id in route.from_preset_ids:
        errors.append(f"{preset_id} live GUI preset transition contains active preset as source")
    if set(route.reset_objects) != set(EXPECTED_PRESET_ISOLATION_ROUTES[preset_id].hidden_objects):
        errors.append(f"{preset_id} live GUI preset transition reset object set drifted from isolation")
    for object_name in route.reset_objects:
        widget = window.findChild(QWidget, object_name)
        if widget is not None and widget.isVisible():
            errors.append(f"{preset_id} live GUI preset transition reset object is visible: {object_name}")
    return errors


def check_live_preset_selection_route(window: Any, preset_id: str) -> list[str]:
    from PyQt6.QtWidgets import QComboBox, QLabel, QTabWidget, QWidget

    route = EXPECTED_PRESET_SELECTION_ROUTES[preset_id]
    errors: list[str] = []
    selector = window.findChild(QComboBox, route.selector_object)
    tabs = window.findChild(QTabWidget, route.tabs_object)
    status_bar = window.findChild(QWidget, route.status_bar_object)
    route_widgets: list[tuple[str, Any]] = [
        ("window", window),
        ("selector", selector),
        ("main-toolbar", window.findChild(QWidget, route.main_toolbar_object)),
        ("layout-toolbar", window.findChild(QWidget, route.layout_toolbar_object)),
        ("left-panel-header", window.findChild(QWidget, route.left_panel_header_object)),
        ("profile-tree", window.findChild(QWidget, route.profile_tree_object)),
        ("tabs", tabs),
        ("status-bar", status_bar),
    ]
    if preset_id != "mobaxterm":
        route_widgets.extend(
            [
                ("workspace-surface", window.findChild(QWidget, route.workspace_surface_object)),
                ("reference-state", window.findChild(QWidget, route.reference_state_object)),
            ]
        )
    route_properties = {
        "presetSelectionRouteKey": route.key,
        "presetSelectionRouteRole": route.route_role,
        "presetSelectionRoutePresetId": route.preset_id,
        "presetSelectionRoutePresetLabel": route.preset_label,
        "presetSelectionRouteSelectorObject": route.selector_object,
        "presetSelectionRouteMainToolbarObject": route.main_toolbar_object,
        "presetSelectionRouteLayoutToolbarObject": route.layout_toolbar_object,
        "presetSelectionRouteLeftPanelHeaderObject": route.left_panel_header_object,
        "presetSelectionRouteProfileTreeObject": route.profile_tree_object,
        "presetSelectionRouteTabsObject": route.tabs_object,
        "presetSelectionRouteStatusBarObject": route.status_bar_object,
        "presetSelectionRouteStatusSegmentObject": route.status_segment_object,
        "presetSelectionRouteWorkspaceSurfaceObject": route.workspace_surface_object,
        "presetSelectionRouteReferenceStateObject": route.reference_state_object,
        "presetSelectionRouteHomeTabLabel": route.home_tab_label,
        "presetSelectionRouteSidebarTitle": route.sidebar_title,
        "presetSelectionRouteSidebarSubtitle": route.sidebar_subtitle,
        "presetSelectionRouteTabPosition": route.tab_position,
        "presetSelectionRouteRenderSource": route.render_source,
    }
    route_value_properties = {
        "presetSelectionRoutePresetIndex": route.preset_index,
        "presetSelectionRouteDocumentMode": route.document_mode,
        "presetSelectionRouteProfileWidth": route.profile_width,
        "presetSelectionRouteLogHeight": route.log_height,
        "presetSelectionRouteToolbarIconSize": route.toolbar_icon_size,
    }
    for label, widget in route_widgets:
        if widget is None:
            errors.append(f"{preset_id} live GUI preset-selection route missing {label}")
            continue
        for property_name, expected_value in route_properties.items():
            actual_value = str(widget.property(property_name) or "")
            if actual_value != expected_value:
                errors.append(
                    f"{preset_id} live GUI preset-selection {label} property "
                    f"{property_name} {actual_value!r} must equal {expected_value!r}"
                )
        for property_name, expected_value in route_value_properties.items():
            actual_value = widget.property(property_name)
            if actual_value != expected_value:
                errors.append(
                    f"{preset_id} live GUI preset-selection {label} property "
                    f"{property_name} {actual_value!r} must equal {expected_value!r}"
                )
        actual_status_segments = list(widget.property("presetSelectionRouteStatusSegments") or [])
        if actual_status_segments != list(route.status_segments):
            errors.append(f"{preset_id} live GUI preset-selection {label} status segment metadata drifted")

    if selector is None:
        errors.append(f"{preset_id} live GUI preset-selection missing selector")
    else:
        if selector.currentData() != route.preset_id:
            errors.append(f"{preset_id} live GUI preset-selection current data drifted")
        if selector.currentIndex() != route.preset_index:
            errors.append(f"{preset_id} live GUI preset-selection current index drifted")
    if tabs is None:
        errors.append(f"{preset_id} live GUI preset-selection missing tabs")
    else:
        if route.home_tab_label not in live_tab_labels(tabs):
            errors.append(f"{preset_id} live GUI preset-selection home tab label drifted")
        if tabs.documentMode() != route.document_mode:
            errors.append(f"{preset_id} live GUI preset-selection tab document mode drifted")
    left_title = window.findChild(QLabel, "leftPanelTitle")
    if left_title is not None and left_title.text() != route.sidebar_title:
        errors.append(f"{preset_id} live GUI preset-selection sidebar title drifted")
    status_texts = {label.text() for label in window.findChildren(QLabel, route.status_segment_object)}
    missing_status = sorted(set(route.status_segments) - status_texts)
    if missing_status:
        errors.append(f"{preset_id} live GUI preset-selection status text drifted: {missing_status}")
    return errors


def check_live_preset_visual_signature(window: Any, preset_id: str) -> list[str]:
    from PyQt6.QtWidgets import QTabWidget, QWidget

    signature = EXPECTED_PRESET_VISUAL_SIGNATURES[preset_id]
    errors: list[str] = []
    route_widgets: list[tuple[str, Any]] = [
        ("window", window),
        ("main-toolbar", window.findChild(QWidget, signature.main_toolbar_object)),
        ("layout-toolbar", window.findChild(QWidget, signature.layout_toolbar_object)),
        ("left-panel", window.findChild(QWidget, signature.left_panel_object)),
        ("profile-tree", window.findChild(QWidget, signature.profile_tree_object)),
        ("tabs", window.findChild(QWidget, signature.tabs_object)),
        ("activity-log", window.findChild(QWidget, signature.activity_log_object)),
        ("status-bar", window.findChild(QWidget, signature.status_bar_object)),
    ]
    string_properties = {
        "presetVisualSignatureKey": signature.key,
        "presetVisualSignatureRole": signature.route_role,
        "presetVisualSignaturePresetId": signature.preset_id,
        "presetVisualSignaturePresetLabel": signature.preset_label,
        signature.density_property: signature.density,
        "presetVisualSignatureTabPosition": signature.tab_position,
        "presetVisualSignatureWindowObject": signature.window_object,
        "presetVisualSignatureMainToolbarObject": signature.main_toolbar_object,
        "presetVisualSignatureLayoutToolbarObject": signature.layout_toolbar_object,
        "presetVisualSignatureLeftPanelObject": signature.left_panel_object,
        "presetVisualSignatureProfileTreeObject": signature.profile_tree_object,
        "presetVisualSignatureTabsObject": signature.tabs_object,
        "presetVisualSignatureActivityLogObject": signature.activity_log_object,
        "presetVisualSignatureStatusBarObject": signature.status_bar_object,
        "presetVisualSignatureDensityProperty": signature.density_property,
        "presetVisualSignaturePaletteProperty": signature.palette_property,
        "presetVisualSignatureRenderSource": signature.render_source,
    }
    value_properties = {
        "presetVisualSignatureDocumentMode": signature.document_mode,
        "presetVisualSignatureProfileWidth": signature.profile_width,
        "presetVisualSignatureLogHeight": signature.log_height,
        "presetVisualSignatureToolbarIconSize": signature.toolbar_icon_size,
        "presetVisualSignatureListSpacing": signature.list_spacing,
    }
    expected_palette = dict(signature.palette_items())
    for label, widget in route_widgets:
        if widget is None:
            errors.append(f"{preset_id} live GUI visual signature missing {label}")
            continue
        for property_name, expected_value in string_properties.items():
            actual_value = str(widget.property(property_name) or "")
            if actual_value != expected_value:
                errors.append(
                    f"{preset_id} live GUI visual signature {label} property "
                    f"{property_name} {actual_value!r} must equal {expected_value!r}"
                )
        for property_name, expected_value in value_properties.items():
            actual_value = widget.property(property_name)
            if actual_value != expected_value:
                errors.append(
                    f"{preset_id} live GUI visual signature {label} property "
                    f"{property_name} {actual_value!r} must equal {expected_value!r}"
                )
        actual_palette = dict(widget.property(signature.palette_property) or {})
        if actual_palette != expected_palette:
            errors.append(f"{preset_id} live GUI visual signature {label} palette drifted")

    stylesheet = window.styleSheet()
    for color in (
        signature.window_color,
        signature.toolbar_color,
        signature.primary_color,
        signature.sidebar_color,
        signature.terminal_color,
        signature.status_color,
    ):
        if color not in stylesheet:
            errors.append(f"{preset_id} live GUI stylesheet missing visual signature color {color}")
    tabs = window.findChild(QTabWidget, signature.tabs_object)
    if tabs is not None and tabs.documentMode() != signature.document_mode:
        errors.append(f"{preset_id} live GUI visual signature tab document mode drifted")
    return errors


def check_live_preset_keyboard_shortcut_route(window: Any, preset_id: str) -> list[str]:
    from PyQt6.QtGui import QShortcut

    route = EXPECTED_PRESET_KEYBOARD_SHORTCUT_ROUTES.get(preset_id)
    if route is None:
        return []
    errors: list[str] = []
    shortcuts = window.findChildren(QShortcut, route.shortcut_object)
    expected_properties = {
        "presetKeyboardShortcutRouteKey": route.key,
        "presetKeyboardShortcutRouteRole": route.route_role,
        "presetKeyboardShortcutPresetId": route.preset_id,
        "presetKeyboardShortcutObject": route.shortcut_object,
        "presetKeyboardShortcutKeyProperty": route.shortcut_key_property,
        "presetKeyboardShortcutSequenceProperty": route.shortcut_sequence_property,
        "presetKeyboardShortcutActionProperty": route.shortcut_action_property,
        "presetKeyboardShortcutCapturedProperty": route.captured_property,
        "presetKeyboardShortcutCapturedKeysProperty": route.captured_keys_property,
        "presetKeyboardShortcutCapturedSequencesProperty": route.captured_sequences_property,
        "presetKeyboardShortcutCapturedActionLabelsProperty": route.captured_action_labels_property,
        "presetKeyboardShortcutCapturedCountProperty": route.captured_count_property,
        "presetKeyboardShortcutRenderSource": route.render_source,
    }
    for property_name, expected_value in expected_properties.items():
        actual_value = str(window.property(property_name) or "")
        if actual_value != expected_value:
            errors.append(
                f"{preset_id} live GUI keyboard shortcut route property "
                f"{property_name} {actual_value!r} must equal {expected_value!r}"
            )
    expected_lists = {
        "presetKeyboardShortcutExpectedKeys": list(route.expected_shortcut_keys),
        "presetKeyboardShortcutExpectedSequences": list(route.expected_sequences),
        "presetKeyboardShortcutExpectedActionLabels": list(route.expected_action_labels),
    }
    for property_name, expected_value in expected_lists.items():
        if list(window.property(property_name) or []) != expected_value:
            errors.append(f"{preset_id} live GUI keyboard shortcut route {property_name} drifted")
    if int(window.property("presetKeyboardShortcutExpectedCount") or -1) != route.expected_shortcut_count:
        errors.append(f"{preset_id} live GUI keyboard shortcut route expected count drifted")
    if bool(window.property(route.captured_property)) is not True:
        errors.append(f"{preset_id} live GUI keyboard shortcut route captured flag missing")
    captured_keys = list(window.property(route.captured_keys_property) or [])
    captured_sequences = list(window.property(route.captured_sequences_property) or [])
    captured_action_labels = list(window.property(route.captured_action_labels_property) or [])
    if captured_keys != list(route.expected_shortcut_keys):
        errors.append(f"{preset_id} live GUI keyboard shortcut route captured keys drifted")
    if captured_sequences != list(route.expected_sequences):
        errors.append(f"{preset_id} live GUI keyboard shortcut route captured sequences drifted")
    if captured_action_labels != list(route.expected_action_labels):
        errors.append(f"{preset_id} live GUI keyboard shortcut route captured labels drifted")
    if int(window.property(route.captured_count_property) or -1) != route.expected_shortcut_count:
        errors.append(f"{preset_id} live GUI keyboard shortcut route captured count drifted")
    if len(shortcuts) != route.expected_shortcut_count:
        errors.append(
            f"{preset_id} live GUI keyboard shortcut count {len(shortcuts)} "
            f"must equal {route.expected_shortcut_count}"
        )
    by_key = {str(shortcut.property(route.shortcut_key_property) or ""): shortcut for shortcut in shortcuts}
    missing_keys = sorted(set(route.expected_shortcut_keys) - set(by_key))
    if missing_keys:
        errors.append(f"{preset_id} live GUI keyboard shortcut route missing keys: {missing_keys}")
    for key, sequence, action_label in zip(
        route.expected_shortcut_keys,
        route.expected_sequences,
        route.expected_action_labels,
        strict=True,
    ):
        shortcut = by_key.get(key)
        if shortcut is None:
            continue
        if str(shortcut.property("presetKeyboardShortcutRouteKey") or "") != route.key:
            errors.append(f"{preset_id} live GUI keyboard shortcut {key!r} missing route key")
        if str(shortcut.property(route.shortcut_sequence_property) or "") != sequence:
            errors.append(f"{preset_id} live GUI keyboard shortcut {key!r} sequence drifted")
        if str(shortcut.property(route.shortcut_action_property) or "") != action_label:
            errors.append(f"{preset_id} live GUI keyboard shortcut {key!r} action label drifted")
        if not shortcut.isEnabled():
            errors.append(f"{preset_id} live GUI keyboard shortcut {key!r} is disabled")
    return errors


def check_live_preset_command_surface_route(window: Any, preset_id: str) -> list[str]:
    from PyQt6.QtWidgets import QToolBar, QToolButton

    route = EXPECTED_PRESET_COMMAND_SURFACE_ROUTES.get(preset_id)
    if route is None:
        return []
    errors: list[str] = []
    toolbar = window.findChild(QToolBar, route.toolbar_object)
    buttons = window.findChildren(QToolButton, route.command_object)
    route_widgets: list[tuple[str, Any]] = [
        ("window", window),
        ("toolbar", toolbar),
        *[(f"command-{index}", button) for index, button in enumerate(buttons)],
    ]
    expected_properties = {
        "presetCommandSurfaceRouteKey": route.key,
        "presetCommandSurfaceRouteRole": route.route_role,
        "presetCommandSurfacePresetId": route.preset_id,
        "presetCommandSurfaceToolbarObject": route.toolbar_object,
        "presetCommandSurfaceCommandObject": route.command_object,
        "presetCommandSurfaceKeyProperty": route.key_property,
        "presetCommandSurfaceLabelProperty": route.label_property,
        "presetCommandSurfaceTooltipProperty": route.tooltip_property,
        "presetCommandSurfaceStateProperty": route.state_property,
        "presetCommandSurfaceCapturedProperty": route.captured_property,
        "presetCommandSurfaceCapturedKeysProperty": route.captured_keys_property,
        "presetCommandSurfaceCapturedLabelsProperty": route.captured_labels_property,
        "presetCommandSurfaceCapturedTooltipsProperty": route.captured_tooltips_property,
        "presetCommandSurfaceCapturedStatesProperty": route.captured_states_property,
        "presetCommandSurfaceCapturedCountProperty": route.captured_count_property,
        "presetCommandSurfaceRenderSource": route.render_source,
    }
    expected_lists = {
        "presetCommandSurfaceExpectedKeys": list(route.expected_action_keys),
        "presetCommandSurfaceExpectedLabels": list(route.expected_action_labels),
        "presetCommandSurfaceExpectedTooltips": list(route.expected_action_tooltips),
    }
    expected_states = dict(route.expected_action_states)
    for label, widget in route_widgets:
        if widget is None:
            errors.append(f"{preset_id} live GUI command surface route missing {label}")
            continue
        for property_name, expected_value in expected_properties.items():
            actual_value = str(widget.property(property_name) or "")
            if actual_value != expected_value:
                errors.append(
                    f"{preset_id} live GUI command surface route {label} property "
                    f"{property_name} {actual_value!r} must equal {expected_value!r}"
                )
        for property_name, expected_value in expected_lists.items():
            if list(widget.property(property_name) or []) != expected_value:
                errors.append(f"{preset_id} live GUI command surface route {label} {property_name} drifted")
        if dict(widget.property("presetCommandSurfaceExpectedStates") or {}) != expected_states:
            errors.append(f"{preset_id} live GUI command surface route {label} expected states drifted")
        if int(widget.property("presetCommandSurfaceExpectedCount") or -1) != route.expected_action_count:
            errors.append(f"{preset_id} live GUI command surface route {label} expected count drifted")
        if bool(widget.property(route.captured_property)) is not True:
            errors.append(f"{preset_id} live GUI command surface route {label} capture flag missing")
        if list(widget.property(route.captured_keys_property) or []) != list(route.expected_action_keys):
            errors.append(f"{preset_id} live GUI command surface route {label} captured keys drifted")
        if list(widget.property(route.captured_labels_property) or []) != list(route.expected_action_labels):
            errors.append(f"{preset_id} live GUI command surface route {label} captured labels drifted")
        if list(widget.property(route.captured_tooltips_property) or []) != list(route.expected_action_tooltips):
            errors.append(f"{preset_id} live GUI command surface route {label} captured tooltips drifted")
        if dict(widget.property(route.captured_states_property) or {}) != expected_states:
            errors.append(f"{preset_id} live GUI command surface route {label} captured states drifted")
        if int(widget.property(route.captured_count_property) or -1) != route.expected_action_count:
            errors.append(f"{preset_id} live GUI command surface route {label} captured count drifted")

    if len(buttons) != route.expected_action_count:
        errors.append(
            f"{preset_id} live GUI command surface action count {len(buttons)} "
            f"must equal {route.expected_action_count}"
        )
    by_key = {str(button.property(route.key_property) or ""): button for button in buttons}
    missing_keys = sorted(set(route.expected_action_keys) - set(by_key))
    if missing_keys:
        errors.append(f"{preset_id} live GUI command surface route missing keys: {missing_keys}")
    for key, label, tooltip in zip(
        route.expected_action_keys,
        route.expected_action_labels,
        route.expected_action_tooltips,
        strict=True,
    ):
        button = by_key.get(key)
        if button is None:
            continue
        if button.text() != label:
            errors.append(f"{preset_id} live GUI command surface {key!r} label drifted")
        if button.toolTip() != tooltip:
            errors.append(f"{preset_id} live GUI command surface {key!r} tooltip drifted")
        if str(button.property(route.label_property) or "") != label:
            errors.append(f"{preset_id} live GUI command surface {key!r} label property drifted")
        if str(button.property(route.tooltip_property) or "") != tooltip:
            errors.append(f"{preset_id} live GUI command surface {key!r} tooltip property drifted")
        if str(button.property(route.state_property) or "normal") != expected_states[key]:
            errors.append(f"{preset_id} live GUI command surface {key!r} state drifted")
    return errors


def check_live_preset_focus_interaction_route(window: Any, preset_id: str) -> list[str]:
    from PyQt6.QtWidgets import QLineEdit, QStatusBar, QTreeWidget

    route = EXPECTED_PRESET_FOCUS_INTERACTION_ROUTES.get(preset_id)
    if route is None:
        return []
    errors: list[str] = []
    focused = window.findChild(QLineEdit, route.focus_object)
    status_bar = window.findChild(QStatusBar, route.status_bar_object)
    tree = window.findChild(QTreeWidget, route.profile_tree_object)
    route_widgets: list[tuple[str, Any]] = [
        ("window", window),
        ("focused-control", focused),
        ("status-bar", status_bar),
        ("profile-tree", tree),
    ]
    expected_properties = {
        "presetFocusInteractionRouteKey": route.key,
        "presetFocusInteractionRouteRole": route.route_role,
        "presetFocusInteractionPresetId": route.preset_id,
        "presetFocusInteractionFocusedControl": route.focused_control,
        "presetFocusInteractionFocusObject": route.focus_object,
        "presetFocusInteractionActiveToolbarKey": route.active_toolbar_key,
        "presetFocusInteractionCheckedToolbarKey": route.checked_toolbar_key,
        "presetFocusInteractionDisabledToolbarKey": route.disabled_toolbar_key,
        "presetFocusInteractionSelectedTreeLabel": route.selected_tree_label,
        "presetFocusInteractionActiveTabStatus": route.active_tab_status,
        "presetFocusInteractionStatusNote": route.status_note,
        "presetFocusInteractionStatusBarObject": route.status_bar_object,
        "presetFocusInteractionProfileTreeObject": route.profile_tree_object,
        "presetFocusInteractionFocusedStateProperty": route.focused_state_property,
        "presetFocusInteractionCapturedProperty": route.captured_property,
        "presetFocusInteractionCapturedFocusProperty": route.captured_focus_property,
        "presetFocusInteractionCapturedStateProperty": route.captured_focus_state_property,
        "presetFocusInteractionCapturedStatusMessageProperty": route.captured_status_message_property,
        "presetFocusInteractionCapturedSelectedTreeProperty": route.captured_selected_tree_property,
        "presetFocusInteractionCapturedToolbarStatesProperty": route.captured_toolbar_states_property,
        "presetFocusInteractionRenderSource": route.render_source,
    }
    for label, widget in route_widgets:
        if widget is None:
            errors.append(f"{preset_id} live GUI focus interaction route missing {label}")
            continue
        for property_name, expected_value in expected_properties.items():
            actual_value = str(widget.property(property_name) or "")
            if actual_value != expected_value:
                errors.append(
                    f"{preset_id} live GUI focus interaction route {label} property "
                    f"{property_name} {actual_value!r} must equal {expected_value!r}"
                )
        if bool(widget.property(route.captured_property)) is not True:
            errors.append(f"{preset_id} live GUI focus interaction route {label} capture flag missing")
        if str(widget.property(route.captured_focus_property) or "") != route.focus_object:
            errors.append(f"{preset_id} live GUI focus interaction route {label} captured focus drifted")
        if str(widget.property(route.captured_focus_state_property) or "") != "focused":
            errors.append(f"{preset_id} live GUI focus interaction route {label} captured state drifted")
        captured_message = str(widget.property(route.captured_status_message_property) or "")
        if route.status_note not in captured_message:
            errors.append(f"{preset_id} live GUI focus interaction route {label} status capture drifted")
        captured_tree = str(widget.property(route.captured_selected_tree_property) or "")
        if route.selected_tree_label not in captured_tree:
            errors.append(f"{preset_id} live GUI focus interaction route {label} tree capture drifted")
        toolbar_states = dict(widget.property(route.captured_toolbar_states_property) or {})
        expected_toolbar_states = {
            "active": route.active_toolbar_key,
            "checked": route.checked_toolbar_key,
            "disabled": route.disabled_toolbar_key,
        }
        if toolbar_states != expected_toolbar_states:
            errors.append(
                f"{preset_id} live GUI focus interaction route {label} toolbar states "
                f"{toolbar_states!r} must equal {expected_toolbar_states!r}"
            )
    if focused is not None and str(focused.property(route.focused_state_property) or "") != "focused":
        errors.append(f"{preset_id} live GUI focus interaction route focused widget must be focused")
    return errors


def check_live_preset_home_search_route(window: Any, preset_id: str) -> list[str]:
    from PyQt6.QtWidgets import QLabel, QLineEdit, QPushButton, QTabWidget, QWidget

    route = EXPECTED_PRESET_HOME_SEARCH_ROUTES.get(preset_id)
    if route is None:
        return []
    errors: list[str] = []
    tabs = window.findChild(QTabWidget, "sessionTabs")
    home_search = window.findChild(QLineEdit, route.home_search_object)
    entry_search = window.findChild(QLineEdit, route.entry_search_object)
    container = window.findChild(QWidget, route.container_object)
    recent_labels = container.findChildren(QLabel, route.recent_label_object) if container is not None else []
    route_widgets: list[tuple[str, Any]] = [
        ("window", window),
        ("tabs", tabs),
        ("home-search", home_search),
        ("entry-search", entry_search),
        ("container", container),
        *[(f"recent-label-{index}", label) for index, label in enumerate(recent_labels)],
    ]
    expected_properties = {
        "presetHomeSearchRouteKey": route.key,
        "presetHomeSearchRouteRole": route.route_role,
        "presetHomeSearchPresetId": route.preset_id,
        "presetHomeSearchHomeTabLabel": route.home_tab_label,
        "presetHomeSearchObject": route.home_search_object,
        "presetHomeSearchEntryControl": route.entry_search_control,
        "presetHomeSearchEntryObject": route.entry_search_object,
        "presetHomeSearchContainerObject": route.container_object,
        "presetHomeSearchRecentLabelObject": route.recent_label_object,
        "presetHomeSearchExpectedPlaceholder": route.placeholder_text,
        "presetHomeSearchExpectedEntryPlaceholder": route.entry_placeholder_text,
        "presetHomeSearchPlaceholderProperty": route.placeholder_property,
        "presetHomeSearchEntryPlaceholderProperty": route.entry_placeholder_property,
        "presetHomeSearchCapturedProperty": route.captured_property,
        "presetHomeSearchCapturedPlaceholderProperty": route.captured_placeholder_property,
        "presetHomeSearchCapturedEntryPlaceholderProperty": route.captured_entry_placeholder_property,
        "presetHomeSearchCapturedTextProperty": route.captured_text_property,
        "presetHomeSearchCapturedEntryTextProperty": route.captured_entry_text_property,
        "presetHomeSearchCapturedActionsProperty": route.captured_actions_property,
        "presetHomeSearchCapturedRecentLabelsProperty": route.captured_recent_labels_property,
        "presetHomeSearchCapturedRecentCountProperty": route.captured_recent_count_property,
        "presetHomeSearchRenderSource": route.render_source,
    }
    expected_lists = {
        "presetHomeSearchExpectedActions": list(route.expected_home_actions),
        "presetHomeSearchExpectedRecentLabels": list(route.expected_recent_labels),
    }
    expected_values = {
        "presetHomeSearchExpectedRecentCount": route.expected_recent_count,
    }
    for label, widget in route_widgets:
        if widget is None:
            errors.append(f"{preset_id} live GUI home search route missing {label}")
            continue
        for property_name, expected_value in expected_properties.items():
            actual_value = str(widget.property(property_name) or "")
            if actual_value != expected_value:
                errors.append(
                    f"{preset_id} live GUI home search route {label} property "
                    f"{property_name} {actual_value!r} must equal {expected_value!r}"
                )
        for property_name, expected_value in expected_lists.items():
            if list(widget.property(property_name) or []) != expected_value:
                errors.append(f"{preset_id} live GUI home search route {label} {property_name} drifted")
        for property_name, expected_value in expected_values.items():
            if widget.property(property_name) != expected_value:
                errors.append(f"{preset_id} live GUI home search route {label} {property_name} drifted")
        if bool(widget.property(route.captured_property)) is not True:
            errors.append(f"{preset_id} live GUI home search route {label} capture flag missing")
        if str(widget.property(route.captured_placeholder_property) or "") != route.placeholder_text:
            errors.append(f"{preset_id} live GUI home search route {label} captured placeholder drifted")
        if str(widget.property(route.captured_entry_placeholder_property) or "") != route.entry_placeholder_text:
            errors.append(f"{preset_id} live GUI home search route {label} captured entry placeholder drifted")
        if str(widget.property(route.captured_text_property) or ""):
            errors.append(f"{preset_id} live GUI home search route {label} captured home search text must start empty")
        if str(widget.property(route.captured_entry_text_property) or ""):
            errors.append(f"{preset_id} live GUI home search route {label} captured entry search text must start empty")
        if list(widget.property(route.captured_actions_property) or []) != list(route.expected_home_actions):
            errors.append(f"{preset_id} live GUI home search route {label} captured actions drifted")
        if list(widget.property(route.captured_recent_labels_property) or []) != list(route.expected_recent_labels):
            errors.append(f"{preset_id} live GUI home search route {label} captured recent labels drifted")
        if int(widget.property(route.captured_recent_count_property) or -1) != route.expected_recent_count:
            errors.append(f"{preset_id} live GUI home search route {label} captured recent count drifted")

    if tabs is not None and route.home_tab_label not in live_tab_labels(tabs):
        errors.append(f"{preset_id} live GUI home search route missing home tab {route.home_tab_label!r}")
    if home_search is not None:
        if home_search.placeholderText() != route.placeholder_text:
            errors.append(f"{preset_id} live GUI home search placeholder drifted")
        if str(home_search.property(route.placeholder_property) or "") != route.placeholder_text:
            errors.append(f"{preset_id} live GUI home search placeholder metadata drifted")
    if entry_search is not None:
        if entry_search.placeholderText() != route.entry_placeholder_text:
            errors.append(f"{preset_id} live GUI entry search placeholder drifted")
        if str(entry_search.property(route.entry_placeholder_property) or "") != route.entry_placeholder_text:
            errors.append(f"{preset_id} live GUI entry search placeholder metadata drifted")
    if container is not None:
        action_labels = [
            button.text()
            for button in container.findChildren(QPushButton)
            if button.text() in route.expected_home_actions
        ]
        if action_labels != list(route.expected_home_actions):
            errors.append(f"{preset_id} live GUI home search action labels drifted")
        actual_recent = [label.text() for label in recent_labels]
        if actual_recent != list(route.expected_recent_labels):
            errors.append(f"{preset_id} live GUI home search recent labels drifted")
    return errors


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


def check_live_moba_connected_session_action_route(window: Any) -> list[str]:
    from PyQt6.QtWidgets import QTabBar, QTabWidget, QWidget

    route = EXPECTED_MOBA_CONNECTED_SESSION_ACTION_ROUTE
    errors: list[str] = []
    tabs = window.findChild(QTabWidget, route.tabs_object)
    tab_bar = window.findChild(QTabBar, route.tab_bar_object)
    connected_panel = window.findChild(QWidget, "mobaConnectedSession")
    if tabs is None:
        return ["mobaxterm live GUI connected session action route missing tabs widget"]
    if tab_bar is None:
        errors.append("mobaxterm live GUI connected session action route missing tab bar")
    if connected_panel is None:
        errors.append("mobaxterm live GUI connected session action route missing connected panel")
    if route.active_tab_label not in live_tab_labels(tabs):
        errors.append(
            f"mobaxterm live GUI connected session action route missing active tab {route.active_tab_label!r}"
        )
    expected_properties = {
        "mobaConnectedSessionActionRouteKey": route.key,
        "mobaConnectedSessionActionRouteRole": route.route_role,
        "mobaConnectedSessionActionProfile": route.profile_name,
        "mobaConnectedSessionActionTarget": route.target,
        "mobaConnectedSessionActionActiveTabKey": route.active_tab_key,
        "mobaConnectedSessionActionActiveTab": route.active_tab_label,
        "mobaConnectedSessionActionReferenceTab": route.reference_tab_label,
        "mobaConnectedSessionActionTabsObject": route.tabs_object,
        "mobaConnectedSessionActionTabBarObject": route.tab_bar_object,
        "mobaConnectedSessionActionReferenceRole": route.reference_tab_role,
        "mobaConnectedSessionActionMenuObject": route.menu_object,
        "mobaConnectedSessionActionObject": route.action_object,
        "mobaConnectedSessionActionActionKeyProperty": route.action_key_property,
        "mobaConnectedSessionActionActionLabelProperty": route.action_label_property,
        "mobaConnectedSessionActionActionEnabledProperty": route.action_enabled_property,
        "mobaConnectedSessionActionRenderSource": route.render_source,
        route.captured_tab_property: route.active_tab_label,
    }
    route_widgets = [("tabs", tabs), ("connected-panel", connected_panel)]
    if tab_bar is not None:
        route_widgets.append(("tab-bar", tab_bar))
    for label, widget in route_widgets:
        if widget is None:
            continue
        for property_name, expected_value in expected_properties.items():
            actual_value = str(widget.property(property_name) or "")
            if actual_value != expected_value:
                errors.append(
                    f"mobaxterm live GUI connected session action route {label} property "
                    f"{property_name} {actual_value!r} must equal {expected_value!r}"
                )
        if list(widget.property("mobaConnectedSessionActionExpectedKeys") or []) != list(route.expected_action_keys):
            errors.append(f"mobaxterm live GUI connected session action route {label} expected keys drifted")
        if list(widget.property("mobaConnectedSessionActionExpectedLabels") or []) != list(
            route.expected_action_labels
        ):
            errors.append(f"mobaxterm live GUI connected session action route {label} expected labels drifted")
        if int(widget.property("mobaConnectedSessionActionExpectedCount") or -1) != route.expected_action_count:
            errors.append(f"mobaxterm live GUI connected session action route {label} expected count drifted")
        if list(widget.property("mobaConnectedSessionActionAlwaysEnabledKeys") or []) != list(
            route.always_enabled_action_keys
        ):
            errors.append(f"mobaxterm live GUI connected session action route {label} always-enabled keys drifted")
        if list(widget.property("mobaConnectedSessionActionConditionalEnabledKeys") or []) != list(
            route.conditional_enabled_action_keys
        ):
            errors.append(f"mobaxterm live GUI connected session action route {label} conditional keys drifted")
        if bool(widget.property(route.captured_property)) is not True:
            errors.append(f"mobaxterm live GUI connected session action route {label} captured flag missing")
        captured_keys = list(widget.property(route.captured_action_keys_property) or [])
        captured_labels = list(widget.property(route.captured_action_labels_property) or [])
        captured_enabled_keys = list(widget.property(route.captured_enabled_keys_property) or [])
        captured_disabled_keys = list(widget.property(route.captured_disabled_keys_property) or [])
        if captured_keys != list(route.expected_action_keys):
            errors.append(f"mobaxterm live GUI connected session action route {label} captured keys drifted")
        if captured_labels != list(route.expected_action_labels):
            errors.append(f"mobaxterm live GUI connected session action route {label} captured labels drifted")
        if int(widget.property(route.captured_action_count_property) or -1) != route.expected_action_count:
            errors.append(f"mobaxterm live GUI connected session action route {label} captured count drifted")
        missing_required_enabled = sorted(set(route.always_enabled_action_keys) - set(captured_enabled_keys))
        if missing_required_enabled:
            errors.append(
                "mobaxterm live GUI connected session action route "
                f"{label} required enabled keys missing: {missing_required_enabled}"
            )
        unexpected_enabled = sorted(set(captured_enabled_keys) - set(route.expected_action_keys))
        if unexpected_enabled:
            errors.append(
                "mobaxterm live GUI connected session action route "
                f"{label} has unexpected enabled keys: {unexpected_enabled}"
            )
        if sorted(set(captured_enabled_keys) | set(captured_disabled_keys)) != sorted(route.expected_action_keys):
            errors.append(
                f"mobaxterm live GUI connected session action route {label} enabled/disabled partition drifted"
            )
        if set(captured_enabled_keys) & set(captured_disabled_keys):
            errors.append(f"mobaxterm live GUI connected session action route {label} enabled/disabled keys overlap")

    reference_index = find_live_tab_index(tabs, route.active_tab_label)
    if reference_index < 0:
        errors.append("mobaxterm live GUI connected session action route active tab missing")
    else:
        reference_widget = tabs.widget(reference_index)
        if reference_widget is None:
            errors.append("mobaxterm live GUI connected session action route active tab widget missing")
        elif str(reference_widget.property("mobaConnectedSessionActionRouteKey") or "") != route.key:
            errors.append("mobaxterm live GUI connected session action route widget missing route key")
        if not hasattr(window, "build_tab_context_menu"):
            errors.append("mobaxterm live GUI connected session action menu builder missing")
        else:
            menu = window.build_tab_context_menu(reference_index)
            if menu is None:
                errors.append("mobaxterm live GUI connected session action menu builder returned no menu")
            else:
                if menu.objectName() != route.menu_object:
                    errors.append(
                        "mobaxterm live GUI connected session action menu object "
                        f"{menu.objectName()!r} must equal {route.menu_object!r}"
                    )
                for property_name, expected_value in expected_properties.items():
                    actual_value = str(menu.property(property_name) or "")
                    if actual_value != expected_value:
                        errors.append(
                            "mobaxterm live GUI connected session action menu property "
                            f"{property_name} {actual_value!r} must equal {expected_value!r}"
                        )
                menu_actions = [action for action in menu.actions() if not action.isSeparator()]
                action_keys = [str(action.property(route.action_key_property) or "") for action in menu_actions]
                action_labels = [str(action.property(route.action_label_property) or "") for action in menu_actions]
                enabled_keys = [
                    str(action.property(route.action_key_property) or "")
                    for action in menu_actions
                    if action.isEnabled()
                ]
                disabled_keys = [
                    str(action.property(route.action_key_property) or "")
                    for action in menu_actions
                    if not action.isEnabled()
                ]
                if len(menu_actions) != route.expected_action_count:
                    errors.append("mobaxterm live GUI connected session action menu action count drifted")
                if action_keys != list(route.expected_action_keys):
                    errors.append("mobaxterm live GUI connected session action menu action keys drifted")
                if action_labels != list(route.expected_action_labels):
                    errors.append("mobaxterm live GUI connected session action menu action labels drifted")
                if list(menu.property(route.captured_action_keys_property) or []) != list(route.expected_action_keys):
                    errors.append("mobaxterm live GUI connected session action menu captured keys drifted")
                if list(menu.property(route.captured_action_labels_property) or []) != list(
                    route.expected_action_labels
                ):
                    errors.append("mobaxterm live GUI connected session action menu captured labels drifted")
                if int(menu.property(route.captured_action_count_property) or -1) != route.expected_action_count:
                    errors.append("mobaxterm live GUI connected session action menu captured count drifted")
                if list(menu.property(route.captured_enabled_keys_property) or []) != enabled_keys:
                    errors.append("mobaxterm live GUI connected session action menu enabled capture drifted")
                if list(menu.property(route.captured_disabled_keys_property) or []) != disabled_keys:
                    errors.append("mobaxterm live GUI connected session action menu disabled capture drifted")
                for action, expected_key, expected_label in zip(
                    menu_actions, route.expected_action_keys, route.expected_action_labels, strict=False
                ):
                    if action.objectName() != route.action_object:
                        errors.append(
                            "mobaxterm live GUI connected session action menu action object "
                            f"{action.objectName()!r} must equal {route.action_object!r}"
                        )
                    if action.text() != expected_label:
                        errors.append(
                            "mobaxterm live GUI connected session action menu action text "
                            f"{action.text()!r} must equal {expected_label!r}"
                        )
                    if str(action.property("mobaConnectedSessionActionRouteKey") or "") != route.key:
                        errors.append(
                            "mobaxterm live GUI connected session action menu action missing route key "
                            f"for {expected_key!r}"
                        )
                    if str(action.property(route.action_key_property) or "") != expected_key:
                        errors.append(
                            "mobaxterm live GUI connected session action menu action key "
                            f"drifted for {expected_key!r}"
                        )
                    if str(action.property(route.action_label_property) or "") != expected_label:
                        errors.append(
                            "mobaxterm live GUI connected session action menu action label "
                            f"drifted for {expected_key!r}"
                        )
                    if bool(action.property(route.action_enabled_property)) != action.isEnabled():
                        errors.append(
                            "mobaxterm live GUI connected session action menu enabled property "
                            f"drifted for {expected_key!r}"
                        )
                missing_required_enabled = sorted(set(route.always_enabled_action_keys) - set(enabled_keys))
                if missing_required_enabled:
                    errors.append(
                        "mobaxterm live GUI connected session action menu required enabled keys missing: "
                        f"{missing_required_enabled}"
                    )
                if sorted(set(enabled_keys) | set(disabled_keys)) != sorted(route.expected_action_keys):
                    errors.append("mobaxterm live GUI connected session action menu enabled/disabled partition drifted")
                if set(enabled_keys) & set(disabled_keys):
                    errors.append("mobaxterm live GUI connected session action menu enabled/disabled keys overlap")
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


def check_live_moba_sftp_terminal_folder_route(window: Any) -> list[str]:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QCheckBox, QLineEdit, QTextEdit, QTreeWidget, QWidget

    route = EXPECTED_MOBA_SFTP_TERMINAL_FOLDER_ROUTE
    errors: list[str] = []
    terminal_area = window.findChild(QWidget, route.terminal_area_object)
    terminal_output = window.findChild(QTextEdit, route.terminal_output_object)
    source_control = window.findChild(QCheckBox, route.source_control_object)
    browser = window.findChild(QWidget, route.target_browser_object)
    path = window.findChild(QLineEdit, route.target_path_object)
    table = window.findChild(QTreeWidget, route.target_table_object)
    route_widgets = [
        ("terminal-area", terminal_area),
        ("terminal-output", terminal_output),
        ("follow-control", source_control),
        ("sftp-browser", browser),
        ("sftp-path", path),
        ("sftp-table", table),
    ]
    route_properties = {
        "mobaSftpTerminalFolderRouteKey": route.key,
        "mobaSftpTerminalFolderRouteRole": route.route_role,
        "mobaSftpTerminalFolderRouteTerminalAreaObject": route.terminal_area_object,
        "mobaSftpTerminalFolderRouteTerminalOutputObject": route.terminal_output_object,
        "mobaSftpTerminalFolderRouteSourceControlObject": route.source_control_object,
        "mobaSftpTerminalFolderRouteTargetBrowserObject": route.target_browser_object,
        "mobaSftpTerminalFolderRouteTargetPathObject": route.target_path_object,
        "mobaSftpTerminalFolderRouteTargetTableObject": route.target_table_object,
        "mobaSftpTerminalFolderRouteParentRowLabel": route.parent_row_label,
        "mobaSftpTerminalFolderRouteSelectedRowKind": route.selected_row_kind,
        route.path_property: route.remote_path,
        route.plan_property: route.list_command,
        "mobaSftpTerminalFolderRouteRowRouteProperty": route.row_route_property,
        "mobaSftpTerminalFolderRouteRenderSource": route.render_source,
    }
    for label, widget in route_widgets:
        if widget is None:
            errors.append(f"mobaxterm live GUI SFTP terminal-folder route missing {label}")
            continue
        for property_name, expected_value in route_properties.items():
            actual_value = str(widget.property(property_name) or "")
            if actual_value != expected_value:
                errors.append(
                    f"mobaxterm live GUI SFTP terminal-folder route {label} property "
                    f"{property_name} {actual_value!r} must equal {expected_value!r}"
                )
        if bool(widget.property(route.enabled_property)) != route.follow_enabled:
            errors.append(f"mobaxterm live GUI SFTP terminal-folder route {label} enabled state drifted")

    if source_control is not None and source_control.isChecked() != route.follow_enabled:
        errors.append("mobaxterm live GUI SFTP terminal-folder follow checkbox state drifted")
    if path is not None and path.text() != route.remote_path:
        errors.append("mobaxterm live GUI SFTP terminal-folder path text drifted")
    if table is not None:
        if str(table.property(route.path_property) or "") != route.remote_path:
            errors.append("mobaxterm live GUI SFTP terminal-folder table path property drifted")
        if str(table.property(route.plan_property) or "") != route.list_command:
            errors.append("mobaxterm live GUI SFTP terminal-folder table list command drifted")
        if table.topLevelItemCount() == 0:
            errors.append("mobaxterm live GUI SFTP terminal-folder table missing rows")
        else:
            parent_item = table.topLevelItem(0)
            if parent_item.text(0) != route.parent_row_label:
                errors.append("mobaxterm live GUI SFTP terminal-folder parent row label drifted")
            parent_kind = str(parent_item.data(0, Qt.ItemDataRole.UserRole) or "")
            if parent_kind != route.selected_row_kind:
                errors.append("mobaxterm live GUI SFTP terminal-folder selected row kind drifted")
            terminal_route_role = int(Qt.ItemDataRole.UserRole) + 50
            row_route_keys = [
                str(table.topLevelItem(index).data(0, terminal_route_role) or "")
                for index in range(table.topLevelItemCount())
            ]
            if any(key != route.key for key in row_route_keys):
                errors.append("mobaxterm live GUI SFTP terminal-folder row route keys drifted")
    return errors


def check_live_moba_sftp_toolbar_action_route(
    dock: Any,
    browser: Any,
    toolbar: Any,
    path: Any,
    table: Any,
    queue: Any,
    buttons: list[Any],
) -> list[str]:
    route = EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE
    target_action_key = "download"
    target_index = route.action_keys.index(target_action_key)
    target_status = route.action_statuses[target_index]
    target_label = route.action_labels[target_index]
    target_group = route.action_group_keys[target_index]
    target_tooltip = route.action_tooltips[target_index]
    target_button = next(
        (
            button
            for button in buttons
            if str(button.property(route.action_key_property) or "") == target_action_key
        ),
        None,
    )
    route_widgets = {
        "dock": dock,
        "browser": browser,
        "toolbar": toolbar,
        "path": path,
        "table": table,
        "queue": queue,
        "target-action": target_button,
    }
    missing = [label for label, widget in route_widgets.items() if widget is None]
    if missing:
        return [f"mobaxterm live GUI SFTP toolbar action route missing widget(s): {missing}"]

    expected_initial_props = {
        route.route_key_property: route.key,
        "mobaSftpToolbarRouteRole": route.route_role,
        "mobaSftpToolbarRouteToolbarObject": route.toolbar_object,
        "mobaSftpToolbarRouteActionObject": route.action_object,
        "mobaSftpToolbarRouteTargetBrowserObject": route.target_browser_object,
        "mobaSftpToolbarRouteTargetPathObject": route.target_path_object,
        "mobaSftpToolbarRouteTargetTableObject": route.target_table_object,
        "mobaSftpToolbarRouteQueueObject": route.queue_object,
        route.action_key_property: target_action_key,
        route.action_label_property: target_label,
        route.action_object_property: route.action_object,
        route.icon_key_property: route.action_icon_keys[target_index],
        route.group_key_property: target_group,
        route.tooltip_property: target_tooltip,
        route.signal_property: route.signal,
        route.handler_property: route.action_handlers[target_index],
        route.captured_action_property: "",
        route.captured_status_property: "",
        route.live_action_property: target_action_key,
        route.live_status_property: target_status,
        "mobaSftpToolbarRouteRenderSource": route.render_source,
    }
    errors: list[str] = []
    for label, widget in route_widgets.items():
        for property_name, expected_value in expected_initial_props.items():
            actual_value = str(widget.property(property_name) or "")
            if actual_value != expected_value:
                errors.append(
                    f"mobaxterm live GUI SFTP toolbar action route {label}.{property_name} "
                    f"{actual_value!r} must equal {expected_value!r}"
                )
        if list(widget.property(route.action_keys_property) or []) != list(route.action_keys):
            errors.append(f"mobaxterm live GUI SFTP toolbar action route {label} action keys drifted")
        if list(widget.property(route.action_groups_property) or []) != list(route.action_group_keys):
            errors.append(f"mobaxterm live GUI SFTP toolbar action route {label} action groups drifted")
        if list(widget.property("mobaSftpToolbarRouteActionStatuses") or []) != list(route.action_statuses):
            errors.append(f"mobaxterm live GUI SFTP toolbar action route {label} action statuses drifted")
        if bool(widget.property(route.captured_property)):
            errors.append(f"mobaxterm live GUI SFTP toolbar action route {label} must start uncaptured")
        if bool(widget.property(route.live_triggered_property)):
            errors.append(f"mobaxterm live GUI SFTP toolbar action route {label} live trigger must start false")
    if route.signal != "clicked":
        errors.append("mobaxterm live GUI SFTP toolbar action route signal drifted")
    if route.action_handlers[target_index] != "show_moba_sftp_toolbar_action":
        errors.append("mobaxterm live GUI SFTP toolbar action route handler drifted")
    if errors:
        return errors

    dock.setProperty("mobaSftpToolbarRouteSuppressDialog", True)
    target_button.click()
    return check_moba_sftp_toolbar_live_action(route_widgets, route, target_action_key, target_status)


def check_moba_sftp_toolbar_live_action(
    route_widgets: dict[str, Any],
    route: Any,
    action_key: str,
    action_status: str,
) -> list[str]:
    action_index = route.action_keys.index(action_key)
    expected_live_props = {
        route.action_key_property: action_key,
        route.action_label_property: route.action_labels[action_index],
        route.action_object_property: route.action_object,
        route.icon_key_property: route.action_icon_keys[action_index],
        route.group_key_property: route.action_group_keys[action_index],
        route.tooltip_property: route.action_tooltips[action_index],
        route.signal_property: route.signal,
        route.handler_property: route.action_handlers[action_index],
        route.captured_action_property: action_key,
        route.captured_status_property: action_status,
        "mobaSftpToolbarRouteLiveAction": action_key,
        route.live_status_property: action_status,
        "mobaSftpToolbarRouteRenderSource": route.render_source,
        "mobaSftpToolbarRouteLastActionKey": action_key,
    }
    for object_name, widget in route_widgets.items():
        if bool(widget.property(route.captured_property)) is not True:
            return [
                f"mobaxterm live GUI SFTP toolbar action {object_name} "
                f"{route.captured_property} was not captured"
            ]
        if bool(widget.property(route.live_triggered_property)) is not True:
            return [
                f"mobaxterm live GUI SFTP toolbar action {object_name} "
                f"{route.live_triggered_property} was not triggered"
            ]
        for property_name, expected_value in expected_live_props.items():
            actual_value = str(widget.property(property_name) or "")
            if actual_value != expected_value:
                return [
                    f"mobaxterm live GUI SFTP toolbar action {object_name}.{property_name} "
                    f"{actual_value!r} must equal {expected_value!r}"
                ]
        if object_name == "queue":
            queue_text = widget.text()
            if action_status not in queue_text or route.action_labels[action_index] not in queue_text:
                return ["mobaxterm live GUI SFTP toolbar queue text did not show clicked action status"]
    return []


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


def collect_tree_items_by_label(tree: Any) -> dict[str, Any]:
    items: dict[str, Any] = {}

    def walk(item: Any) -> None:
        items[item.text(0)] = item
        for child_index in range(item.childCount()):
            walk(item.child(child_index))

    for index in range(tree.topLevelItemCount()):
        walk(tree.topLevelItem(index))
    return items


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

    matches = window.findChildren(QWidget, object_name)
    if not matches:
        return None
    visible_matches = [widget for widget in matches if widget.isVisible()]
    widget = visible_matches[0] if visible_matches else matches[0]
    position = widget.mapTo(window, QPoint(0, 0))
    geometry = widget.geometry()
    return {
        "x": int(position.x()),
        "y": int(position.y()),
        "width": int(geometry.width()),
        "height": int(geometry.height()),
    }


def live_widget_non_overlap_errors(context: str, widgets: list[Any]) -> list[str]:
    if not widgets:
        return [f"{context} must expose at least one widget"]
    parent = widgets[0].parentWidget()
    if parent is None or any(widget.parentWidget() is not parent for widget in widgets):
        return [f"{context} must share one parent for measurable geometry"]
    content = parent.contentsRect()
    bounds = []
    for index, widget in enumerate(widgets):
        geometry = widget.geometry()
        bounds.append(
            {
                "id": f"{widget.objectName()}[{index}]",
                "x": int(geometry.x()),
                "y": int(geometry.y()),
                "width": int(geometry.width()),
                "height": int(geometry.height()),
            }
        )
    container = {
        "x": int(content.x()),
        "y": int(content.y()),
        "width": int(content.width()),
        "height": int(content.height()),
    }
    return validate_non_overlapping_bounds(context, bounds, container)


def validate_non_overlapping_bounds(
    context: str,
    bounds: list[dict[str, int | str]],
    container: dict[str, int],
) -> list[str]:
    errors: list[str] = []
    container_right = container["x"] + container["width"]
    container_bottom = container["y"] + container["height"]
    for item in bounds:
        label = str(item["id"])
        x = int(item["x"])
        y = int(item["y"])
        width = int(item["width"])
        height = int(item["height"])
        if width <= 0 or height <= 0:
            errors.append(f"{context} {label} has empty geometry")
            continue
        if (
            x < container["x"]
            or y < container["y"]
            or x + width > container_right
            or y + height > container_bottom
        ):
            errors.append(f"{context} {label} extends outside its parent content rect")
    for index, left in enumerate(bounds):
        left_right = int(left["x"]) + int(left["width"])
        left_bottom = int(left["y"]) + int(left["height"])
        for right in bounds[index + 1 :]:
            overlap_width = min(left_right, int(right["x"]) + int(right["width"])) - max(
                int(left["x"]), int(right["x"])
            )
            overlap_height = min(
                left_bottom,
                int(right["y"]) + int(right["height"]),
            ) - max(int(left["y"]), int(right["y"]))
            if overlap_width > 0 and overlap_height > 0:
                errors.append(
                    f"{context} {left['id']} overlaps {right['id']} by "
                    f"{overlap_width}x{overlap_height} pixels"
                )
    return errors


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


def check_live_product_identity_route(window: Any, preset_id: str) -> list[str]:
    from PyQt6.QtWidgets import QLabel, QTabWidget, QTreeWidget, QWidget

    route = EXPECTED_PRODUCT_IDENTITY_ROUTES.get(preset_id)
    if route is None:
        return []
    errors: list[str] = []
    panel = window.findChild(QWidget, route.reference_state_object)
    if panel is None:
        return [f"{preset_id} live GUI product identity route missing reference state panel"]
    route_properties = {
        "productIdentityRouteKey": route.key,
        "productIdentityRouteRole": route.route_role,
        "productIdentityPreset": route.preset_id,
        "productIdentitySelectedTreeLabel": route.selected_tree_label,
        "productIdentityReferenceStateObject": route.reference_state_object,
        "productIdentityReferenceItemObject": route.reference_item_object,
        "productIdentityTreeObject": route.tree_object,
        "productIdentityTabsObject": route.tabs_object,
        "productIdentityStatusSegmentObject": route.status_segment_object,
        "productIdentityWorkspaceSurfaceObject": route.workspace_surface_object,
        "productIdentityProfile": route.selected_profile_name,
        "productIdentityTarget": route.target_label,
        "productIdentityProtocol": route.protocol_label,
        "productIdentityActiveTab": route.active_tab_label,
        "productIdentitySidebar": route.sidebar_label,
        "productIdentityWorkspaceState": route.workspace_state,
        "productIdentityRenderSource": route.render_source,
    }
    identity_widgets: list[tuple[str, Any]] = [
        ("reference-state", panel),
        *[
            (f"reference-item:{str(label.property('referenceKey') or '')}", label)
            for label in panel.findChildren(QLabel, route.reference_item_object)
        ],
    ]
    for label, widget in identity_widgets:
        for property_name, expected_value in route_properties.items():
            actual_value = str(widget.property(property_name) or "")
            if actual_value != expected_value:
                errors.append(
                    f"{preset_id} live GUI product identity {label} property "
                    f"{property_name} {actual_value!r} must equal {expected_value!r}"
                )
        actual_status_segments = list(widget.property("productIdentityStatusSegments") or [])
        if actual_status_segments != list(route.status_segments):
            errors.append(f"{preset_id} live GUI product identity {label} status segments drifted")

    reference_texts = {label.text() for _label, label in identity_widgets if isinstance(label, QLabel)}
    for key, value in gui_design_reference_state(preset_id).items():
        if f"{key}: {value}" not in reference_texts:
            errors.append(f"{preset_id} live GUI product identity reference item drifted: {key}")

    tabs = window.findChild(QTabWidget, route.tabs_object)
    if tabs is None or route.active_tab_label not in live_tab_labels(tabs):
        errors.append(f"{preset_id} live GUI product identity active tab label drifted")
    tree = window.findChild(QTreeWidget, route.tree_object)
    if tree is None:
        errors.append(f"{preset_id} live GUI product identity missing profile tree")
    else:
        tree_labels = collect_tree_labels(tree)
        if route.selected_tree_label not in tree_labels:
            errors.append(f"{preset_id} live GUI product identity selected tree label drifted")
    status_texts = {label.text() for label in window.findChildren(QLabel, route.status_segment_object)}
    missing_status = sorted(set(route.status_segments) - status_texts)
    if missing_status:
        errors.append(f"{preset_id} live GUI product identity status segments drifted: {missing_status}")
    workspace = window.findChild(QWidget, route.workspace_surface_object)
    if workspace is None:
        errors.append(f"{preset_id} live GUI product identity missing workspace surface")
    return errors


def check_live_preset_reference_tab_route(window: Any, preset_id: str) -> list[str]:
    from PyQt6.QtWidgets import QTabWidget

    route = EXPECTED_PRESET_REFERENCE_TAB_ROUTES.get(preset_id)
    if route is None:
        return []
    errors: list[str] = []
    tabs = window.findChild(QTabWidget, route.tabs_object)
    if tabs is None:
        return [f"{preset_id} live GUI reference tab route missing tabs widget"]
    expected_properties = {
        "presetReferenceTabRouteKey": route.key,
        "presetReferenceTabRouteRole": route.route_role,
        "presetReferenceTabPresetId": route.preset_id,
        "presetReferenceTabProfile": route.reference_profile,
        "presetReferenceTabActiveLabel": route.active_tab_label,
        "presetReferenceTabHomeLabel": route.home_tab_label,
        "presetReferenceTabTabsObject": route.tabs_object,
        "presetReferenceTabHomeRole": route.home_tab_role,
        "presetReferenceTabReferenceRole": route.reference_tab_role,
        "presetReferenceTabActivatedLabelProperty": route.activated_label_property,
        "presetReferenceTabReturnedHomeLabelProperty": route.returned_home_label_property,
        "presetReferenceTabActiveProperty": route.active_tab_property,
        "presetReferenceTabHomeProperty": route.home_tab_property,
        "presetReferenceTabProfileProperty": route.reference_profile_property,
        "presetReferenceTabRenderSource": route.render_source,
        route.activated_label_property: route.active_tab_label,
        route.returned_home_label_property: route.home_tab_label,
        route.active_tab_property: route.active_tab_label,
        route.home_tab_property: route.home_tab_label,
        route.reference_profile_property: route.reference_profile,
    }
    for property_name, expected_value in expected_properties.items():
        actual_value = str(tabs.property(property_name) or "")
        if actual_value != expected_value:
            errors.append(
                f"{preset_id} live GUI reference tab route property "
                f"{property_name} {actual_value!r} must equal {expected_value!r}"
            )
    tab_labels = live_tab_labels(tabs)
    if route.active_tab_label not in tab_labels:
        errors.append(f"{preset_id} live GUI reference tab route active tab label missing")
    if route.home_tab_label not in tab_labels:
        errors.append(f"{preset_id} live GUI reference tab route home tab label missing")
    current_index = tabs.currentIndex()
    if current_index < 0 or tabs.tabText(current_index) != route.home_tab_label:
        errors.append(f"{preset_id} live GUI reference tab route must return to home tab before capture")
    reference_index = find_live_tab_index(tabs, route.active_tab_label)
    if reference_index >= 0:
        reference_widget = tabs.widget(reference_index)
        if str(reference_widget.property("tabRole") or "") != route.reference_tab_role:
            errors.append(f"{preset_id} live GUI reference tab route tab role drifted")
        if str(reference_widget.property("presetReferenceTabRouteKey") or "") != route.key:
            errors.append(f"{preset_id} live GUI reference tab widget missing route key")
    home_index = find_live_tab_index(tabs, route.home_tab_label)
    if home_index >= 0:
        home_widget = tabs.widget(home_index)
        if str(home_widget.property("tabRole") or "") != route.home_tab_role:
            errors.append(f"{preset_id} live GUI reference tab route home role drifted")
    return errors


def check_live_preset_reference_tab_chrome_route(window: Any, preset_id: str) -> list[str]:
    from PyQt6.QtWidgets import QTabBar, QTabWidget

    route = EXPECTED_PRESET_REFERENCE_TAB_CHROME_ROUTES.get(preset_id)
    if route is None:
        return []
    errors: list[str] = []
    tabs = window.findChild(QTabWidget, route.tabs_object)
    tab_bar = window.findChild(QTabBar, route.tab_bar_object)
    if tabs is None:
        return [f"{preset_id} live GUI reference tab chrome missing tabs widget"]
    if tab_bar is None:
        errors.append(f"{preset_id} live GUI reference tab chrome missing tab bar")
    expected_properties = {
        "presetReferenceTabChromeRouteKey": route.key,
        "presetReferenceTabChromeRouteRole": route.route_role,
        "presetReferenceTabChromePresetId": route.preset_id,
        "presetReferenceTabChromeProfile": route.reference_profile,
        "presetReferenceTabChromeActiveLabel": route.active_tab_label,
        "presetReferenceTabChromeHomeLabel": route.home_tab_label,
        "presetReferenceTabChromeTabsObject": route.tabs_object,
        "presetReferenceTabChromeTabBarObject": route.tab_bar_object,
        "presetReferenceTabChromeReferenceRole": route.reference_tab_role,
        "presetReferenceTabChromeNewSessionRole": route.new_session_tab_role,
        "presetReferenceTabChromeExpectedPosition": route.expected_tab_position,
        "presetReferenceTabChromeExpectedTooltip": route.expected_tooltip,
        "presetReferenceTabChromeRenderSource": route.render_source,
        route.captured_label_property: route.active_tab_label,
        route.captured_tooltip_property: route.expected_tooltip,
        route.captured_role_property: route.reference_tab_role,
    }
    for property_name, expected_value in expected_properties.items():
        actual_value = str(tabs.property(property_name) or "")
        if actual_value != expected_value:
            errors.append(
                f"{preset_id} live GUI reference tab chrome property "
                f"{property_name} {actual_value!r} must equal {expected_value!r}"
            )
    expected_bool_properties = {
        "presetReferenceTabChromeExpectedCloseable": route.expected_closeable,
        "presetReferenceTabChromeExpectedSelectedDuringCapture": route.expected_selected_during_capture,
        route.captured_closeable_property: route.expected_closeable,
        route.captured_selected_property: route.expected_selected_during_capture,
        route.captured_property: True,
    }
    for property_name, expected_value in expected_bool_properties.items():
        if bool(tabs.property(property_name)) is not expected_value:
            errors.append(f"{preset_id} live GUI reference tab chrome boolean {property_name} drifted")
    captured_position = str(tabs.property(route.captured_position_property) or "")
    if tab_position_name(route.expected_tab_position) not in captured_position:
        errors.append(f"{preset_id} live GUI reference tab chrome captured tab position drifted")
    reference_index = int(tabs.property(route.captured_index_property) or -1)
    actual_reference_index = find_live_tab_index(tabs, route.active_tab_label)
    if reference_index != actual_reference_index:
        errors.append(f"{preset_id} live GUI reference tab chrome captured index drifted")
    if actual_reference_index < 0:
        return [*errors, f"{preset_id} live GUI reference tab chrome active tab missing"]
    reference_widget = tabs.widget(actual_reference_index)
    if reference_widget is None:
        return [*errors, f"{preset_id} live GUI reference tab chrome active tab widget missing"]
    if str(reference_widget.property("presetReferenceTabChromeRouteKey") or "") != route.key:
        errors.append(f"{preset_id} live GUI reference tab chrome widget missing route key")
    if tabs.tabText(actual_reference_index) != route.active_tab_label:
        errors.append(f"{preset_id} live GUI reference tab chrome label drifted")
    if live_tab_plain_tooltip(tabs, actual_reference_index) != route.expected_tooltip:
        errors.append(f"{preset_id} live GUI reference tab chrome tooltip drifted")
    if str(reference_widget.property("tabRole") or "") != route.reference_tab_role:
        errors.append(f"{preset_id} live GUI reference tab chrome role drifted")
    new_session_index = find_live_tab_index(tabs, "+")
    if new_session_index >= 0 and actual_reference_index >= new_session_index:
        errors.append(f"{preset_id} live GUI reference tab chrome must appear before new-session tab")
    return errors


def check_live_preset_reference_status_bar_route(window: Any, preset_id: str) -> list[str]:
    from PyQt6.QtWidgets import QLabel, QStatusBar, QTabWidget

    route = EXPECTED_PRESET_REFERENCE_STATUS_BAR_ROUTES.get(preset_id)
    if route is None:
        return []
    errors: list[str] = []
    tabs = window.findChild(QTabWidget, "sessionTabs")
    status_bar = window.findChild(QStatusBar, route.status_bar_object)
    notice = window.findChild(QLabel, route.status_notice_object)
    segment_labels = window.findChildren(QLabel, route.status_segment_object)
    if tabs is None:
        return [f"{preset_id} live GUI reference status-bar route missing tabs widget"]
    if status_bar is None:
        return [f"{preset_id} live GUI reference status-bar route missing status bar"]
    if notice is None:
        errors.append(f"{preset_id} live GUI reference status-bar route missing notice label")
    if len(segment_labels) < route.expected_segment_count:
        errors.append(f"{preset_id} live GUI reference status-bar route missing segment labels")
    expected_properties = {
        "presetReferenceStatusRouteKey": route.key,
        "presetReferenceStatusRouteRole": route.route_role,
        "presetReferenceStatusPresetId": route.preset_id,
        "presetReferenceStatusProfile": route.reference_profile,
        "presetReferenceStatusActiveTab": route.active_tab_label,
        "presetReferenceStatusBarObject": route.status_bar_object,
        "presetReferenceStatusNoticeObject": route.status_notice_object,
        "presetReferenceStatusSegmentObject": route.status_segment_object,
        "presetReferenceStatusExpectedMessage": route.expected_status_message,
        "presetReferenceStatusRenderSource": route.render_source,
        route.captured_tab_property: route.active_tab_label,
        route.captured_message_property: route.expected_status_message,
    }
    for property_name, expected_value in expected_properties.items():
        actual_value = str(status_bar.property(property_name) or "")
        if actual_value != expected_value:
            errors.append(
                f"{preset_id} live GUI reference status-bar property "
                f"{property_name} {actual_value!r} must equal {expected_value!r}"
            )
    if list(status_bar.property("presetReferenceStatusExpectedSegments") or []) != list(route.expected_status_segments):
        errors.append(f"{preset_id} live GUI reference status-bar expected segments drifted")
    if int(status_bar.property("presetReferenceStatusExpectedSegmentCount") or -1) != route.expected_segment_count:
        errors.append(f"{preset_id} live GUI reference status-bar expected segment count drifted")
    if bool(status_bar.property(route.captured_property)) is not True:
        errors.append(f"{preset_id} live GUI reference status-bar captured flag missing")
    captured_segments = list(status_bar.property(route.captured_segments_property) or [])
    if captured_segments != list(route.expected_status_segments):
        errors.append(f"{preset_id} live GUI reference status-bar captured segments drifted")
    if int(status_bar.property(route.captured_segment_count_property) or -1) != route.expected_segment_count:
        errors.append(f"{preset_id} live GUI reference status-bar captured segment count drifted")
    captured_tooltips = list(status_bar.property(route.captured_segment_tooltips_property) or [])
    for segment in route.expected_status_segments:
        if not any(segment in tooltip for tooltip in captured_tooltips):
            errors.append(f"{preset_id} live GUI reference status-bar tooltip missing segment: {segment}")
    notice_text = str(status_bar.property(route.captured_notice_property) or "")
    if notice_text != "Remote Ops Workspace":
        errors.append(f"{preset_id} live GUI reference status-bar notice drifted")
    # QStatusBar.currentMessage() reflects the latest tab transition; the captured property above
    # preserves the reference status message at the moment the route is exercised.
    reference_index = find_live_tab_index(tabs, route.active_tab_label)
    if reference_index < 0:
        errors.append(f"{preset_id} live GUI reference status-bar active tab missing")
    else:
        reference_widget = tabs.widget(reference_index)
        if reference_widget is None:
            errors.append(f"{preset_id} live GUI reference status-bar active tab widget missing")
        elif str(reference_widget.property("presetReferenceStatusRouteKey") or "") != route.key:
            errors.append(f"{preset_id} live GUI reference status-bar widget missing route key")
    for label in segment_labels[: route.expected_segment_count]:
        if str(label.property("presetReferenceStatusRouteKey") or "") != route.key:
            errors.append(f"{preset_id} live GUI reference status-bar segment missing route key")
            break
    return errors


def check_live_preset_reference_session_action_route(window: Any, preset_id: str) -> list[str]:
    from PyQt6.QtWidgets import QTabBar, QTabWidget

    route = EXPECTED_PRESET_REFERENCE_SESSION_ACTION_ROUTES.get(preset_id)
    if route is None:
        return []
    errors: list[str] = []
    tabs = window.findChild(QTabWidget, route.tabs_object)
    tab_bar = window.findChild(QTabBar, route.tab_bar_object)
    if tabs is None:
        return [f"{preset_id} live GUI reference session action route missing tabs widget"]
    if tab_bar is None:
        errors.append(f"{preset_id} live GUI reference session action route missing tab bar")
    expected_properties = {
        "presetReferenceSessionActionRouteKey": route.key,
        "presetReferenceSessionActionRouteRole": route.route_role,
        "presetReferenceSessionActionPresetId": route.preset_id,
        "presetReferenceSessionActionProfile": route.reference_profile,
        "presetReferenceSessionActionActiveTab": route.active_tab_label,
        "presetReferenceSessionActionTabsObject": route.tabs_object,
        "presetReferenceSessionActionTabBarObject": route.tab_bar_object,
        "presetReferenceSessionActionReferenceRole": route.reference_tab_role,
        "presetReferenceSessionActionObject": route.action_object,
        "presetReferenceSessionActionActionKeyProperty": route.action_key_property,
        "presetReferenceSessionActionActionLabelProperty": route.action_label_property,
        "presetReferenceSessionActionActionEnabledProperty": route.action_enabled_property,
        "presetReferenceSessionActionRenderSource": route.render_source,
        route.captured_tab_property: route.active_tab_label,
    }
    for property_name, expected_value in expected_properties.items():
        actual_value = str(tabs.property(property_name) or "")
        if actual_value != expected_value:
            errors.append(
                f"{preset_id} live GUI reference session action property "
                f"{property_name} {actual_value!r} must equal {expected_value!r}"
            )
    if list(tabs.property("presetReferenceSessionActionExpectedKeys") or []) != list(route.expected_action_keys):
        errors.append(f"{preset_id} live GUI reference session action expected keys drifted")
    if list(tabs.property("presetReferenceSessionActionExpectedLabels") or []) != list(route.expected_action_labels):
        errors.append(f"{preset_id} live GUI reference session action expected labels drifted")
    if int(tabs.property("presetReferenceSessionActionExpectedCount") or -1) != route.expected_action_count:
        errors.append(f"{preset_id} live GUI reference session action expected count drifted")
    if list(tabs.property("presetReferenceSessionActionAlwaysEnabledKeys") or []) != list(
        route.always_enabled_action_keys
    ):
        errors.append(f"{preset_id} live GUI reference session action always-enabled keys drifted")
    if list(tabs.property("presetReferenceSessionActionConditionalEnabledKeys") or []) != list(
        route.conditional_enabled_action_keys
    ):
        errors.append(f"{preset_id} live GUI reference session action conditional keys drifted")
    if bool(tabs.property(route.captured_property)) is not True:
        errors.append(f"{preset_id} live GUI reference session action captured flag missing")
    captured_keys = list(tabs.property(route.captured_action_keys_property) or [])
    captured_labels = list(tabs.property(route.captured_action_labels_property) or [])
    captured_enabled_keys = list(tabs.property(route.captured_enabled_keys_property) or [])
    captured_disabled_keys = list(tabs.property(route.captured_disabled_keys_property) or [])
    if captured_keys != list(route.expected_action_keys):
        errors.append(f"{preset_id} live GUI reference session action captured keys drifted")
    if captured_labels != list(route.expected_action_labels):
        errors.append(f"{preset_id} live GUI reference session action captured labels drifted")
    if int(tabs.property(route.captured_action_count_property) or -1) != route.expected_action_count:
        errors.append(f"{preset_id} live GUI reference session action captured count drifted")
    missing_required_enabled = sorted(set(route.always_enabled_action_keys) - set(captured_enabled_keys))
    if missing_required_enabled:
        errors.append(
            f"{preset_id} live GUI reference session action required enabled keys missing: {missing_required_enabled}"
        )
    unexpected_enabled = sorted(set(captured_enabled_keys) - set(route.expected_action_keys))
    if unexpected_enabled:
        errors.append(f"{preset_id} live GUI reference session action has unexpected enabled keys: {unexpected_enabled}")
    if sorted(set(captured_enabled_keys) | set(captured_disabled_keys)) != sorted(route.expected_action_keys):
        errors.append(f"{preset_id} live GUI reference session action enabled/disabled partition drifted")
    if set(captured_enabled_keys) & set(captured_disabled_keys):
        errors.append(f"{preset_id} live GUI reference session action enabled/disabled keys overlap")
    reference_index = find_live_tab_index(tabs, route.active_tab_label)
    if reference_index < 0:
        errors.append(f"{preset_id} live GUI reference session action active tab missing")
    else:
        reference_widget = tabs.widget(reference_index)
        if reference_widget is None:
            errors.append(f"{preset_id} live GUI reference session action active tab widget missing")
        elif str(reference_widget.property("presetReferenceSessionActionRouteKey") or "") != route.key:
            errors.append(f"{preset_id} live GUI reference session action widget missing route key")
    if tab_bar is not None and str(tab_bar.property("presetReferenceSessionActionRouteKey") or "") != route.key:
        errors.append(f"{preset_id} live GUI reference session action tab bar missing route key")
    return errors


def check_live_preset_reference_surface_route(window: Any, preset_id: str) -> list[str]:
    from PyQt6.QtWidgets import QLabel, QTabWidget, QTextEdit, QWidget

    route = EXPECTED_PRESET_REFERENCE_SURFACE_ROUTES.get(preset_id)
    if route is None:
        return []
    errors: list[str] = []
    tabs = window.findChild(QTabWidget, "sessionTabs")
    if tabs is None:
        return [f"{preset_id} live GUI reference surface route missing tabs widget"]
    expected_properties = {
        "presetReferenceSurfaceRouteKey": route.key,
        "presetReferenceSurfaceRouteRole": route.route_role,
        "presetReferenceSurfacePresetId": route.preset_id,
        "presetReferenceSurfaceProfile": route.reference_profile,
        "presetReferenceSurfaceActiveTab": route.active_tab_label,
        "presetReferenceSurfaceExpectedTitle": route.expected_title,
        "presetReferenceSurfaceExpectedSource": route.expected_source,
        "presetReferenceSurfaceCommandExecutableChoices": "|".join(route.command_executables),
        "presetReferenceSurfaceCommandTargetFragment": route.command_target_fragment,
        "presetReferenceSurfaceTerminalPaneObject": route.terminal_pane_object,
        "presetReferenceSurfaceTitleObject": route.terminal_title_object,
        "presetReferenceSurfaceSourceObject": route.terminal_source_object,
        "presetReferenceSurfaceCommandObject": route.terminal_command_object,
        "presetReferenceSurfaceOutputObject": route.terminal_output_object,
        "presetReferenceSurfaceCapturedProperty": route.captured_property,
        "presetReferenceSurfaceCapturedTabProperty": route.captured_tab_property,
        "presetReferenceSurfaceActualTitleProperty": route.actual_title_property,
        "presetReferenceSurfaceActualSourceProperty": route.actual_source_property,
        "presetReferenceSurfaceActualCommandProperty": route.actual_command_property,
        "presetReferenceSurfaceActualOutputProperty": route.actual_output_property,
        "presetReferenceSurfaceRenderSource": route.render_source,
        route.captured_tab_property: route.active_tab_label,
        route.actual_title_property: route.expected_title,
        route.actual_source_property: route.expected_source,
    }
    for property_name, expected_value in expected_properties.items():
        actual_value = str(tabs.property(property_name) or "")
        if actual_value != expected_value:
            errors.append(
                f"{preset_id} live GUI reference surface route property "
                f"{property_name} {actual_value!r} must equal {expected_value!r}"
            )
    if not bool(tabs.property(route.captured_property)):
        errors.append(f"{preset_id} live GUI reference surface route was not captured")

    actual_command = str(tabs.property(route.actual_command_property) or "")
    actual_output = str(tabs.property(route.actual_output_property) or "")
    command_executable = command_executable_name(actual_command)
    if command_executable not in route.command_executables:
        errors.append(
            f"{preset_id} live GUI reference surface command executable "
            f"{command_executable!r} must be one of {route.command_executables!r}"
        )
    if route.command_target_fragment not in actual_command:
        errors.append(f"{preset_id} live GUI reference surface command target fragment drifted")
    if actual_command and actual_command not in actual_output:
        errors.append(f"{preset_id} live GUI reference surface output did not echo command")

    reference_index = find_live_tab_index(tabs, route.active_tab_label)
    if reference_index < 0:
        return [*errors, f"{preset_id} live GUI reference surface active tab missing"]
    reference_widget = tabs.widget(reference_index)
    pane = reference_widget
    if str(pane.objectName()) != route.terminal_pane_object:
        pane = reference_widget.findChild(QWidget, route.terminal_pane_object)
    if pane is None:
        return [*errors, f"{preset_id} live GUI reference surface missing terminal pane"]
    if str(pane.property("presetReferenceSurfaceRouteKey") or "") != route.key:
        errors.append(f"{preset_id} live GUI reference surface pane missing route key")

    title = pane.findChild(QLabel, route.terminal_title_object)
    source = pane.findChild(QLabel, route.terminal_source_object)
    command = pane.findChild(QLabel, route.terminal_command_object)
    output = pane.findChild(QTextEdit, route.terminal_output_object)
    if title is None or title.text() != route.expected_title:
        errors.append(f"{preset_id} live GUI reference surface title drifted")
    if source is None or source.text() != route.expected_source:
        errors.append(f"{preset_id} live GUI reference surface source drifted")
    if command is None or command.text() != actual_command:
        errors.append(f"{preset_id} live GUI reference surface command label drifted")
    if output is None or actual_command not in output.toPlainText():
        errors.append(f"{preset_id} live GUI reference surface terminal output drifted")
    return errors


def command_executable_name(command: str) -> str:
    executable = command.strip().split(" ", 1)[0].strip("'\"")
    executable = executable.rsplit("\\", 1)[-1].rsplit("/", 1)[-1]
    return executable.lower()


def check_live_preset_reference_control_route(window: Any, preset_id: str) -> list[str]:
    from PyQt6.QtWidgets import QLabel, QTabWidget, QToolButton, QWidget

    route = EXPECTED_PRESET_REFERENCE_CONTROL_ROUTES.get(preset_id)
    if route is None:
        return []
    errors: list[str] = []
    tabs = window.findChild(QTabWidget, "sessionTabs")
    if tabs is None:
        return [f"{preset_id} live GUI reference control route missing tabs widget"]
    expected_properties = {
        "presetReferenceControlRouteKey": route.key,
        "presetReferenceControlRouteRole": route.route_role,
        "presetReferenceControlPresetId": route.preset_id,
        "presetReferenceControlProfile": route.reference_profile,
        "presetReferenceControlActiveTab": route.active_tab_label,
        "presetReferenceControlTerminalPaneObject": route.terminal_pane_object,
        "presetReferenceControlStatusObject": route.terminal_status_object,
        "presetReferenceControlActionObject": route.terminal_action_object,
        "presetReferenceControlActionKeyProperty": route.action_key_property,
        "presetReferenceControlActionLabelProperty": route.action_label_property,
        "presetReferenceControlActionTooltipProperty": route.action_tooltip_property,
        "presetReferenceControlStatusStateProperty": route.status_state_property,
        "presetReferenceControlCapturedProperty": route.captured_property,
        "presetReferenceControlCapturedActionsProperty": route.captured_actions_property,
        "presetReferenceControlCapturedStatusProperty": route.captured_status_property,
        "presetReferenceControlCapturedStatusTextProperty": route.captured_status_text_property,
        "presetReferenceControlRenderSource": route.render_source,
        "presetReferenceControlCapturedTab": route.active_tab_label,
    }
    for property_name, expected_value in expected_properties.items():
        actual_value = str(tabs.property(property_name) or "")
        if actual_value != expected_value:
            errors.append(
                f"{preset_id} live GUI reference control route property "
                f"{property_name} {actual_value!r} must equal {expected_value!r}"
            )
    if list(tabs.property("presetReferenceControlActionKeys") or []) != list(route.action_keys):
        errors.append(f"{preset_id} live GUI reference control route expected action keys drifted")
    if list(tabs.property("presetReferenceControlActionLabels") or []) != list(route.action_labels):
        errors.append(f"{preset_id} live GUI reference control route expected action labels drifted")
    if sorted(tabs.property(route.captured_actions_property) or []) != sorted(route.action_keys):
        errors.append(f"{preset_id} live GUI reference control route captured action keys drifted")
    status_state = str(tabs.property(route.captured_status_property) or "")
    if status_state not in route.allowed_status_states:
        errors.append(f"{preset_id} live GUI reference control route captured invalid status state: {status_state}")
    if not str(tabs.property(route.captured_status_text_property) or ""):
        errors.append(f"{preset_id} live GUI reference control route captured empty status text")
    if not bool(tabs.property(route.captured_property)):
        errors.append(f"{preset_id} live GUI reference control route was not captured")

    reference_index = find_live_tab_index(tabs, route.active_tab_label)
    if reference_index < 0:
        return [*errors, f"{preset_id} live GUI reference control active tab missing"]
    reference_widget = tabs.widget(reference_index)
    pane = reference_widget
    if str(pane.objectName()) != route.terminal_pane_object:
        pane = reference_widget.findChild(QWidget, route.terminal_pane_object)
    if pane is None:
        return [*errors, f"{preset_id} live GUI reference control terminal pane missing"]
    status = pane.findChild(QLabel, route.terminal_status_object)
    if status is None:
        errors.append(f"{preset_id} live GUI reference control status widget missing")
    elif str(status.property(route.status_state_property) or "") not in route.allowed_status_states:
        errors.append(f"{preset_id} live GUI reference control status state drifted")
    buttons = pane.findChildren(QToolButton, route.terminal_action_object)
    by_key = {str(button.property(route.action_key_property) or ""): button for button in buttons}
    for key, label, tooltip in zip(route.action_keys, route.action_labels, route.action_tooltips, strict=True):
        button = by_key.get(key)
        if button is None:
            errors.append(f"{preset_id} live GUI reference control missing action: {key}")
            continue
        if button.text() != label:
            errors.append(f"{preset_id} live GUI reference control action label drifted: {key}")
        if button.toolTip() != tooltip:
            errors.append(f"{preset_id} live GUI reference control action tooltip drifted: {key}")
        if str(button.property(route.action_label_property) or "") != label:
            errors.append(f"{preset_id} live GUI reference control action label property drifted: {key}")
        if str(button.property(route.action_tooltip_property) or "") != tooltip:
            errors.append(f"{preset_id} live GUI reference control action tooltip property drifted: {key}")
    return errors


def check_live_preset_reference_input_route(window: Any, preset_id: str) -> list[str]:
    from PyQt6.QtWidgets import QLineEdit, QTabWidget, QWidget

    route = EXPECTED_PRESET_REFERENCE_INPUT_ROUTES.get(preset_id)
    if route is None:
        return []
    errors: list[str] = []
    tabs = window.findChild(QTabWidget, "sessionTabs")
    if tabs is None:
        return [f"{preset_id} live GUI reference input route missing tabs widget"]
    expected_properties = {
        "presetReferenceInputRouteKey": route.key,
        "presetReferenceInputRouteRole": route.route_role,
        "presetReferenceInputPresetId": route.preset_id,
        "presetReferenceInputProfile": route.reference_profile,
        "presetReferenceInputActiveTab": route.active_tab_label,
        "presetReferenceInputTerminalPaneObject": route.terminal_pane_object,
        "presetReferenceInputObject": route.terminal_input_object,
        "presetReferenceInputExpectedPlaceholder": route.placeholder_text,
        "presetReferenceInputExpectedInitialText": route.expected_initial_text,
        "presetReferenceInputCapturedProperty": route.captured_property,
        "presetReferenceInputCapturedTabProperty": route.captured_tab_property,
        "presetReferenceInputCapturedPlaceholderProperty": route.captured_placeholder_property,
        "presetReferenceInputCapturedTextProperty": route.captured_text_property,
        "presetReferenceInputCapturedEnabledProperty": route.captured_enabled_property,
        "presetReferenceInputRenderSource": route.render_source,
        route.captured_tab_property: route.active_tab_label,
        route.captured_placeholder_property: route.placeholder_text,
        route.captured_text_property: route.expected_initial_text,
    }
    for property_name, expected_value in expected_properties.items():
        actual_value = str(tabs.property(property_name) or "")
        if actual_value != expected_value:
            errors.append(
                f"{preset_id} live GUI reference input route property "
                f"{property_name} {actual_value!r} must equal {expected_value!r}"
            )
    if list(tabs.property("presetReferenceInputAllowedEnabledStates") or []) != list(route.allowed_enabled_states):
        errors.append(f"{preset_id} live GUI reference input route allowed enabled states drifted")
    captured_enabled = tabs.property(route.captured_enabled_property)
    if captured_enabled not in route.allowed_enabled_states:
        errors.append(f"{preset_id} live GUI reference input route captured invalid enabled state")
    if not bool(tabs.property(route.captured_property)):
        errors.append(f"{preset_id} live GUI reference input route was not captured")

    reference_index = find_live_tab_index(tabs, route.active_tab_label)
    if reference_index < 0:
        return [*errors, f"{preset_id} live GUI reference input active tab missing"]
    reference_widget = tabs.widget(reference_index)
    pane = reference_widget
    if str(pane.objectName()) != route.terminal_pane_object:
        pane = reference_widget.findChild(QWidget, route.terminal_pane_object)
    if pane is None:
        return [*errors, f"{preset_id} live GUI reference input terminal pane missing"]
    input_widget = pane.findChild(QLineEdit, route.terminal_input_object)
    if input_widget is None:
        return [*errors, f"{preset_id} live GUI reference input widget missing"]
    if input_widget.placeholderText() != route.placeholder_text:
        errors.append(f"{preset_id} live GUI reference input placeholder drifted")
    if input_widget.text() != route.expected_initial_text:
        errors.append(f"{preset_id} live GUI reference input initial text drifted")
    if input_widget.isEnabled() not in route.allowed_enabled_states:
        errors.append(f"{preset_id} live GUI reference input enabled state drifted")
    if str(input_widget.property("presetReferenceInputRouteKey") or "") != route.key:
        errors.append(f"{preset_id} live GUI reference input widget missing route key")
    return errors


def check_live_preset_reference_transcript_route(window: Any, preset_id: str) -> list[str]:
    from PyQt6.QtWidgets import QTabWidget, QTextEdit, QWidget

    route = EXPECTED_PRESET_REFERENCE_TRANSCRIPT_ROUTES.get(preset_id)
    if route is None:
        return []
    errors: list[str] = []
    tabs = window.findChild(QTabWidget, "sessionTabs")
    if tabs is None:
        return [f"{preset_id} live GUI reference transcript route missing tabs widget"]
    expected_properties = {
        "presetReferenceTranscriptRouteKey": route.key,
        "presetReferenceTranscriptRouteRole": route.route_role,
        "presetReferenceTranscriptPresetId": route.preset_id,
        "presetReferenceTranscriptProfile": route.reference_profile,
        "presetReferenceTranscriptActiveTab": route.active_tab_label,
        "presetReferenceTranscriptTerminalPaneObject": route.terminal_pane_object,
        "presetReferenceTranscriptOutputObject": route.terminal_output_object,
        "presetReferenceTranscriptCommandEchoPrefix": route.command_echo_prefix,
        "presetReferenceTranscriptCapturedProperty": route.captured_property,
        "presetReferenceTranscriptCapturedTabProperty": route.captured_tab_property,
        "presetReferenceTranscriptCapturedTextProperty": route.captured_text_property,
        "presetReferenceTranscriptCapturedLineCountProperty": route.captured_line_count_property,
        "presetReferenceTranscriptCapturedCommandEchoProperty": route.captured_command_echo_property,
        "presetReferenceTranscriptRenderSource": route.render_source,
        route.captured_tab_property: route.active_tab_label,
    }
    for property_name, expected_value in expected_properties.items():
        actual_value = str(tabs.property(property_name) or "")
        if actual_value != expected_value:
            errors.append(
                f"{preset_id} live GUI reference transcript route property "
                f"{property_name} {actual_value!r} must equal {expected_value!r}"
            )
    if list(tabs.property("presetReferenceTranscriptRequiredFragments") or []) != list(route.required_fragments):
        errors.append(f"{preset_id} live GUI reference transcript required fragments drifted")
    if int(tabs.property("presetReferenceTranscriptMinimumLineCount") or 0) != route.minimum_line_count:
        errors.append(f"{preset_id} live GUI reference transcript minimum line count drifted")
    captured_line_count = int(tabs.property(route.captured_line_count_property) or 0)
    if captured_line_count < route.minimum_line_count:
        errors.append(f"{preset_id} live GUI reference transcript captured too few lines")
    transcript = str(tabs.property(route.captured_text_property) or "")
    for fragment in route.required_fragments:
        if fragment not in transcript:
            errors.append(f"{preset_id} live GUI reference transcript missing fragment: {fragment}")
    command_echo = str(tabs.property(route.captured_command_echo_property) or "")
    if not command_echo.startswith(route.command_echo_prefix):
        errors.append(f"{preset_id} live GUI reference transcript missing command echo")
    if not bool(tabs.property(route.captured_property)):
        errors.append(f"{preset_id} live GUI reference transcript route was not captured")

    reference_index = find_live_tab_index(tabs, route.active_tab_label)
    if reference_index < 0:
        return [*errors, f"{preset_id} live GUI reference transcript active tab missing"]
    reference_widget = tabs.widget(reference_index)
    pane = reference_widget
    if str(pane.objectName()) != route.terminal_pane_object:
        pane = reference_widget.findChild(QWidget, route.terminal_pane_object)
    if pane is None:
        return [*errors, f"{preset_id} live GUI reference transcript terminal pane missing"]
    output_widget = pane.findChild(QTextEdit, route.terminal_output_object)
    if output_widget is None:
        return [*errors, f"{preset_id} live GUI reference transcript output widget missing"]
    output_text = output_widget.toPlainText()
    if str(output_widget.property("presetReferenceTranscriptRouteKey") or "") != route.key:
        errors.append(f"{preset_id} live GUI reference transcript output missing route key")
    if command_echo and command_echo not in output_text:
        errors.append(f"{preset_id} live GUI reference transcript command echo drifted")
    for fragment in route.required_fragments:
        if fragment not in output_text:
            errors.append(f"{preset_id} live GUI reference transcript output fragment drifted: {fragment}")
    return errors


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
    from PyQt6.QtCore import QCoreApplication, Qt
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
        # Showing the suggestion tree invalidates the parent layout.  Hiding it
        # again restores the idle state immediately, but Qt defers the dock's
        # geometry update until the event queue is serviced.  Settle that
        # production transition before later topology checks measure it.
        app = QCoreApplication.instance()
        if app is not None:
            process_events(app)

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
    status_cells = panel.findChildren(QLabel, "secureCrtSessionStatusCell")
    geometry_errors = live_widget_non_overlap_errors(
        "securecrt live GUI session-status cells",
        [title, *status_cells],
    )
    if geometry_errors:
        return geometry_errors
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
        full_text = f"{field.label}: {field.value}"
        tooltip_text = f"{full_text}\n{field.tooltip}"
        compact_width = int(cell.property("secureCrtSessionStatusCompactMinWidth") or 0)
        if str(cell.property("secureCrtSessionStatusLabel") or "") != field.label:
            return [f"securecrt live GUI session-status field {field.key!r} label metadata drifted"]
        if str(cell.property("secureCrtSessionStatusValue") or "") != field.value:
            return [f"securecrt live GUI session-status field {field.key!r} value metadata drifted"]
        if str(cell.property("secureCrtSessionStatusFullText") or "") != full_text:
            return [f"securecrt live GUI session-status field {field.key!r} full text metadata drifted"]
        if str(cell.property("secureCrtSessionStatusDisplayText") or "") != cell.text() or not cell.text().strip():
            return [f"securecrt live GUI session-status field {field.key!r} compact display text drifted"]
        if str(cell.property("secureCrtSessionStatusTooltipText") or "") != tooltip_text:
            return [f"securecrt live GUI session-status field {field.key!r} tooltip metadata drifted"]
        if cell.accessibleName() != full_text or not cell.toolTip():
            return [f"securecrt live GUI session-status field {field.key!r} full accessible text drifted"]
        if compact_width <= 0 or compact_width > field.live_min_width:
            return [f"securecrt live GUI session-status field {field.key!r} compact width is invalid"]
        if cell.minimumWidth() != compact_width:
            return [f"securecrt live GUI session-status field {field.key!r} compact minimum width drifted"]
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
        full_text = str(target_cell.property("secureCrtSessionStatusFullText") or "")
        if route.target_value not in full_text or target_cell.accessibleName() != full_text:
            errors.append("securecrt live GUI session-manager route target full status text drifted")
    return errors


def check_live_securecrt_session_manager_filter_route(window: Any) -> list[str]:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QLineEdit, QTreeWidget, QWidget

    route = EXPECTED_SECURECRT_SESSION_MANAGER_FILTER_ROUTE
    panel = window.findChild(QWidget, route.session_manager_object)
    filter_input = window.findChild(QLineEdit, route.filter_object)
    tree = window.findChild(QTreeWidget, route.selected_tree_object)
    errors: list[str] = []
    if panel is None:
        errors.append("securecrt live GUI session-manager filter route missing Session Manager panel")
    if filter_input is None:
        errors.append("securecrt live GUI session-manager filter route missing filter input")
    if tree is None:
        errors.append("securecrt live GUI session-manager filter route missing profile tree")
    if errors:
        return errors

    route_props = {
        route.filter_route_property: route.key,
        "secureCrtSessionFilterRouteRole": route.route_role,
        "secureCrtSessionFilterRouteSessionManagerObject": route.session_manager_object,
        "secureCrtSessionFilterRouteFilterObject": route.filter_object,
        "secureCrtSessionFilterRouteSelectedTreeObject": route.selected_tree_object,
        "secureCrtSessionFilterRouteSelectedProfile": route.selected_profile_name,
        "secureCrtSessionFilterRouteSelectedTreeLabel": route.selected_tree_label,
        route.filter_query_property: route.expected_query,
        route.filter_placeholder_property: route.expected_placeholder,
        route.matched_result_property: route.matched_result_label,
        "secureCrtSessionFilterRouteSignal": route.change_signal,
        "secureCrtSessionFilterRouteHandler": route.handler_name,
        "secureCrtSessionFilterRouteRenderSource": route.render_source,
    }
    for label, widget in (
        ("session-manager", panel),
        ("filter-input", filter_input),
        ("profile-tree", tree),
    ):
        for property_name, expected_value in route_props.items():
            actual_value = str(widget.property(property_name) or "")
            if actual_value != expected_value:
                errors.append(
                    f"securecrt live GUI session-manager filter route {label} property "
                    f"{property_name} {actual_value!r} must equal {expected_value!r}"
                )

    if filter_input.placeholderText() != route.expected_placeholder:
        errors.append("securecrt live GUI session-manager filter route placeholder text drifted")
    if route.expected_query.lower() not in route.matched_result_label.lower():
        errors.append("securecrt live GUI session-manager filter route query no longer matches selected row")

    selected = tree.currentItem()
    if selected is None:
        errors.append("securecrt live GUI session-manager filter route missing selected tree item")
        return errors
    if route.matched_result_label not in selected.text(0):
        errors.append("securecrt live GUI session-manager filter route selected row label drifted")
    base_role = int(Qt.ItemDataRole.UserRole)
    expected_item_data = {
        base_role + 81: route.key,
        base_role + 82: route.route_role,
        base_role + 83: route.expected_query,
        base_role + 84: route.selected_profile_name,
        base_role + 85: route.matched_result_label,
        base_role + 87: route.render_source,
    }
    for role, expected_value in expected_item_data.items():
        actual_value = str(selected.data(0, role) or "")
        if actual_value != expected_value:
            errors.append(f"securecrt live GUI session-manager filter route tree role {role} drifted")
    if selected.data(0, base_role + 86) is not True:
        errors.append("securecrt live GUI session-manager filter route selected row is not marked matched")
    return errors


def check_live_securecrt_sftp_tab_route(window: Any) -> list[str]:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QLabel, QTabWidget, QTreeWidget, QWidget

    route = EXPECTED_SECURECRT_SFTP_TAB_ROUTE
    workflow_panel = window.findChild(QWidget, "productWorkflowEvidence")
    tree = window.findChild(QTreeWidget, route.selected_tree_object)
    manager_panel = window.findChild(QWidget, route.session_manager_object)
    status_panel = window.findChild(QWidget, route.status_strip_object)
    tabs = window.findChild(QTabWidget, "sessionTabs")
    errors: list[str] = []
    if workflow_panel is None:
        errors.append("securecrt live GUI SFTP tab route missing workflow evidence panel")
    if tree is None:
        errors.append("securecrt live GUI SFTP tab route missing profile tree")
    if manager_panel is None:
        errors.append("securecrt live GUI SFTP tab route missing Session Manager panel")
    if status_panel is None:
        errors.append("securecrt live GUI SFTP tab route missing status strip")
    if tabs is None:
        errors.append("securecrt live GUI SFTP tab route missing session tabs")
    if errors:
        return errors

    panel_route_props = {
        "secureCrtSftpTabRouteKey": route.key,
        "secureCrtSftpTabRouteRole": route.route_role,
        route.workflow_key_property: route.workflow_card_key,
        "secureCrtSftpTabRouteWorkflowCardObject": route.workflow_card_object,
        "secureCrtSftpTabRouteTitleObject": route.workflow_title_object,
        "secureCrtSftpTabRoutePrimaryObject": route.workflow_primary_object,
        "secureCrtSftpTabRouteSecondaryObject": route.workflow_secondary_object,
        "secureCrtSftpTabRouteSessionManagerObject": route.session_manager_object,
        "secureCrtSftpTabRouteSelectedTreeObject": route.selected_tree_object,
        "secureCrtSftpTabRouteSelectedProfile": route.selected_profile_name,
        "secureCrtSftpTabRouteSelectedTreeLabel": route.selected_tree_label,
        "secureCrtSftpTabRouteActiveTab": route.active_tab_label,
        route.tab_label_property: route.sftp_tab_label,
        "secureCrtSftpTabRouteStatusStripObject": route.status_strip_object,
        "secureCrtSftpTabRouteStatusFieldKey": route.status_field_key,
        "secureCrtSftpTabRouteStatusFieldObject": route.status_field_object,
        route.status_property: route.status_value,
        route.transfer_state_property: route.transfer_state,
        "secureCrtSftpTabRouteRenderSource": route.render_source,
    }
    shared_route_props = {
        "secureCrtSftpTabRouteKey": route.key,
        "secureCrtSftpTabRouteRole": route.route_role,
        route.workflow_key_property: route.workflow_card_key,
        "secureCrtSftpTabRouteSelectedProfile": route.selected_profile_name,
        "secureCrtSftpTabRouteSelectedTreeLabel": route.selected_tree_label,
        "secureCrtSftpTabRouteActiveTab": route.active_tab_label,
        route.tab_label_property: route.sftp_tab_label,
        "secureCrtSftpTabRouteStatusStripObject": route.status_strip_object,
        "secureCrtSftpTabRouteStatusFieldKey": route.status_field_key,
        "secureCrtSftpTabRouteStatusFieldObject": route.status_field_object,
        route.status_property: route.status_value,
        route.transfer_state_property: route.transfer_state,
        "secureCrtSftpTabRouteRenderSource": route.render_source,
    }
    tree_tab_props = {
        **shared_route_props,
        "secureCrtSftpTabRouteWorkflowCardObject": route.workflow_card_object,
        "secureCrtSftpTabRouteSessionManagerObject": route.session_manager_object,
        "secureCrtSftpTabRouteSelectedTreeObject": route.selected_tree_object,
    }
    for label, widget, route_props in (
        ("workflow-panel", workflow_panel, panel_route_props),
        ("profile-tree", tree, tree_tab_props),
        ("session-manager", manager_panel, shared_route_props),
        ("status-strip", status_panel, shared_route_props),
        ("tabs", tabs, tree_tab_props),
    ):
        for property_name, expected_value in route_props.items():
            actual_value = str(widget.property(property_name) or "")
            if actual_value != expected_value:
                errors.append(
                    f"securecrt live GUI SFTP tab route {label} property "
                    f"{property_name} {actual_value!r} must equal {expected_value!r}"
                )

    workflow_cards = [
        widget
        for widget in workflow_panel.findChildren(QWidget, route.workflow_card_object)
        if str(widget.property("workflowKey") or "") == route.workflow_card_key
    ]
    if len(workflow_cards) != 1:
        errors.append("securecrt live GUI SFTP tab route must expose one workflow card")
    else:
        workflow_card = workflow_cards[0]
        card_route_props = {
            "secureCrtSftpTabRouteKey": route.key,
            "secureCrtSftpTabRouteRole": route.route_role,
            route.workflow_key_property: route.workflow_card_key,
            "secureCrtSftpTabRouteWorkflowCardObject": route.workflow_card_object,
            "secureCrtSftpTabRouteStatusStripObject": route.status_strip_object,
            "secureCrtSftpTabRouteStatusFieldKey": route.status_field_key,
            "secureCrtSftpTabRouteActiveTab": route.active_tab_label,
            route.tab_label_property: route.sftp_tab_label,
            route.status_property: route.status_value,
            route.transfer_state_property: route.transfer_state,
            "secureCrtSftpTabRouteRenderSource": route.render_source,
        }
        for property_name, expected_value in card_route_props.items():
            actual_value = str(workflow_card.property(property_name) or "")
            if actual_value != expected_value:
                errors.append(f"securecrt live GUI SFTP tab workflow-card property {property_name} drifted")
        card_labels = {label.objectName(): label for label in workflow_card.findChildren(QLabel)}
        expected_card_text = {
            route.workflow_title_object: route.workflow_title,
            route.workflow_primary_object: route.workflow_primary,
            route.workflow_secondary_object: route.workflow_secondary,
        }
        for object_name, expected_text in expected_card_text.items():
            label = card_labels.get(object_name)
            if label is None or label.text() != expected_text:
                errors.append(f"securecrt live GUI SFTP tab workflow label {object_name} drifted")
        title = card_labels.get(route.workflow_title_object)
        primary = card_labels.get(route.workflow_primary_object)
        secondary = card_labels.get(route.workflow_secondary_object)
        if title is not None and str(title.property("secureCrtSftpTabRouteTitle") or "") != route.workflow_title:
            errors.append("securecrt live GUI SFTP tab workflow title property drifted")
        if primary is not None and str(primary.property(route.transfer_state_property) or "") != route.transfer_state:
            errors.append("securecrt live GUI SFTP tab workflow transfer-state property drifted")
        if secondary is not None and str(secondary.property(route.status_property) or "") != route.status_value:
            errors.append("securecrt live GUI SFTP tab workflow status property drifted")

    matched_items = [
        item
        for item_label, item in collect_tree_items_by_label(tree).items()
        if item_label == route.selected_tree_label
    ]
    if len(matched_items) != 1:
        errors.append("securecrt live GUI SFTP tab route must expose one SFTP tree row")
    else:
        matched_item = matched_items[0]
        base_role = int(Qt.ItemDataRole.UserRole)
        expected_item_data = {
            base_role: route.selected_profile_name,
            base_role + 101: route.key,
            base_role + 102: route.route_role,
            base_role + 103: route.selected_profile_name,
            base_role + 104: route.selected_tree_label,
            base_role + 105: route.sftp_tab_label,
            base_role + 106: route.status_value,
            base_role + 107: route.transfer_state,
        }
        for role, expected_value in expected_item_data.items():
            actual_value = str(matched_item.data(0, role) or "")
            if actual_value != expected_value:
                errors.append(f"securecrt live GUI SFTP tab route tree role {role} drifted")

    status_cells = status_panel.findChildren(QLabel, route.status_field_object)
    target_cells = [
        cell for cell in status_cells if str(cell.property("secureCrtSessionStatusKey") or "") == route.status_field_key
    ]
    if len(target_cells) != 1:
        errors.append("securecrt live GUI SFTP tab route must expose one SFTP status cell")
    else:
        target_cell = target_cells[0]
        for property_name, expected_value in shared_route_props.items():
            actual_value = str(target_cell.property(property_name) or "")
            if actual_value != expected_value:
                errors.append(f"securecrt live GUI SFTP tab status-cell property {property_name} drifted")
        if str(target_cell.property("secureCrtSessionStatusValue") or "") != route.status_value:
            errors.append("securecrt live GUI SFTP tab status cell value metadata drifted")
        full_text = str(target_cell.property("secureCrtSessionStatusFullText") or "")
        if route.status_value not in full_text or target_cell.accessibleName() != full_text:
            errors.append("securecrt live GUI SFTP tab full status text drifted")

    static_tab_labels = {label for label, _status, _active in gui_design_tab_items("securecrt")}
    if route.sftp_tab_label not in static_tab_labels:
        errors.append("securecrt SFTP tab route static tab label drifted from shared metadata")
    if route.active_tab_label not in live_tab_labels(tabs):
        errors.append(f"securecrt live GUI SFTP tab route missing active SSH tab {route.active_tab_label!r}")
    return errors


def check_live_securecrt_sftp_browser_route(window: Any) -> list[str]:
    from PyQt6.QtWidgets import QFrame, QLabel, QToolButton, QWidget

    route = EXPECTED_SECURECRT_SFTP_BROWSER_ROUTE
    tab_route = EXPECTED_SECURECRT_SFTP_TAB_ROUTE
    browser = window.findChild(QWidget, route.browser_object)
    toolbar = window.findChild(QWidget, route.toolbar_object)
    path = window.findChild(QLabel, route.path_object)
    table = window.findChild(QWidget, route.table_object)
    queue = window.findChild(QLabel, route.queue_object)
    errors: list[str] = []
    if route.sftp_tab_route_key != tab_route.key:
        errors.append("securecrt SFTP browser route tab key drifted from SFTP tab route")
    if route.selected_profile_name != tab_route.selected_profile_name:
        errors.append("securecrt SFTP browser route profile drifted from SFTP tab route")
    if route.selected_tree_label != tab_route.selected_tree_label:
        errors.append("securecrt SFTP browser route tree label drifted from SFTP tab route")
    if route.sftp_tab_label != tab_route.sftp_tab_label:
        errors.append("securecrt SFTP browser route tab label drifted from SFTP tab route")
    if browser is None:
        errors.append("securecrt live GUI missing SFTP browser route panel")
    if toolbar is None:
        errors.append("securecrt live GUI missing SFTP browser toolbar")
    if path is None:
        errors.append("securecrt live GUI missing SFTP browser path")
    if table is None:
        errors.append("securecrt live GUI missing SFTP browser table")
    if queue is None:
        errors.append("securecrt live GUI missing SFTP browser queue")
    if errors:
        return errors

    actions_value = "|".join(route.toolbar_actions)
    route_props = {
        "secureCrtSftpBrowserRouteKey": route.key,
        "secureCrtSftpBrowserRouteRole": route.route_role,
        "secureCrtSftpBrowserTabRouteKey": route.sftp_tab_route_key,
        "secureCrtSftpBrowserObject": route.browser_object,
        "secureCrtSftpBrowserToolbarObject": route.toolbar_object,
        "secureCrtSftpBrowserPathObject": route.path_object,
        "secureCrtSftpBrowserTableObject": route.table_object,
        "secureCrtSftpBrowserRowObject": route.row_object,
        "secureCrtSftpBrowserQueueObject": route.queue_object,
        "secureCrtSftpBrowserSelectedProfile": route.selected_profile_name,
        "secureCrtSftpBrowserSelectedTreeLabel": route.selected_tree_label,
        "secureCrtSftpBrowserTabLabel": route.sftp_tab_label,
        route.path_property: route.remote_path,
        route.toolbar_actions_property: actions_value,
        "secureCrtSftpBrowserActiveRowName": route.active_row_name,
        "secureCrtSftpBrowserQueueLabel": route.transfer_queue_label,
        route.queue_state_property: route.transfer_status,
        "secureCrtSftpBrowserActionObject": route.action_object,
        "secureCrtSftpBrowserActionKey": route.action_key,
        "secureCrtSftpBrowserActionLabel": route.action_label,
        route.signal_property: route.signal,
        route.handler_property: route.handler,
        route.captured_action_property: "",
        route.captured_status_property: "",
        route.live_action_property: route.action_key,
        route.live_status_property: route.transfer_status,
        "secureCrtSftpBrowserRenderSource": route.render_source,
    }
    route_widgets = {
        "browser": browser,
        "toolbar": toolbar,
        "path": path,
        "table": table,
        "queue": queue,
    }
    for label, widget in (
        ("browser", browser),
        ("toolbar", toolbar),
        ("path", path),
        ("table", table),
        ("queue", queue),
    ):
        for property_name, expected_value in route_props.items():
            actual_value = str(widget.property(property_name) or "")
            if actual_value != expected_value:
                errors.append(
                    f"securecrt live GUI SFTP browser {label} property "
                    f"{property_name} {actual_value!r} must equal {expected_value!r}"
                )
        if bool(widget.property(route.captured_property)):
            errors.append(f"securecrt live GUI SFTP browser {label} action route must start uncaptured")
        if bool(widget.property(route.live_triggered_property)):
            errors.append(f"securecrt live GUI SFTP browser {label} live trigger must start false")

    if route.remote_path not in path.text():
        errors.append("securecrt live GUI SFTP browser path text drifted")
    if route.transfer_queue_label not in queue.text() or route.transfer_status not in queue.text():
        errors.append("securecrt live GUI SFTP browser queue text drifted")

    action_widgets = toolbar.findChildren(QToolButton, route.action_object)
    action_keys = [str(action.property("secureCrtSftpBrowserActionKey") or "") for action in action_widgets]
    if action_keys != list(route.toolbar_actions):
        errors.append(f"securecrt live GUI SFTP browser toolbar actions {action_keys!r} drifted")
    target_actions = [
        action
        for action in action_widgets
        if str(action.property("secureCrtSftpBrowserActionKey") or "") == route.action_key
    ]
    if len(target_actions) != 1:
        errors.append("securecrt live GUI SFTP browser must expose one routed Refresh action")
    else:
        target_action = target_actions[0]
        route_widgets["refresh-action"] = target_action
        if target_action.text() != route.action_label:
            errors.append("securecrt live GUI SFTP browser routed action label drifted")
        expected_action_props = {
            "secureCrtSftpBrowserRouteKey": route.key,
            "secureCrtSftpBrowserActionKey": route.action_key,
            route.toolbar_actions_property: actions_value,
            "secureCrtSftpBrowserActionObject": route.action_object,
            "secureCrtSftpBrowserActionLabel": route.action_label,
            route.signal_property: route.signal,
            route.handler_property: route.handler,
            route.captured_action_property: "",
            route.captured_status_property: "",
            route.live_action_property: route.action_key,
            route.live_status_property: route.transfer_status,
        }
        for property_name, expected_value in expected_action_props.items():
            actual_value = str(target_action.property(property_name) or "")
            if actual_value != expected_value:
                errors.append(f"securecrt live GUI SFTP routed action property {property_name} drifted")
        if bool(target_action.property(route.captured_property)):
            errors.append("securecrt live GUI SFTP routed action must start uncaptured")
        if bool(target_action.property(route.live_triggered_property)):
            errors.append("securecrt live GUI SFTP routed action live trigger must start false")
        if route.signal != "clicked":
            errors.append("securecrt live GUI SFTP browser action signal drifted")
        if route.handler != "handle_securecrt_sftp_browser_action":
            errors.append("securecrt live GUI SFTP browser action handler drifted")

    rows = table.findChildren(QFrame, route.row_object)
    expected_rows_by_name = {row.name: row for row in route.file_rows}
    if len(rows) != len(route.file_rows):
        errors.append("securecrt live GUI SFTP browser row count drifted")
    selected_rows: list[str] = []
    for row_widget in rows:
        row_name = str(row_widget.property(route.row_name_property) or "")
        expected_row = expected_rows_by_name.get(row_name)
        if expected_row is None:
            errors.append(f"securecrt live GUI SFTP browser unexpected row {row_name!r}")
            continue
        actual_kind = str(row_widget.property(route.row_kind_property) or "")
        if actual_kind != expected_row.kind:
            errors.append(f"securecrt live GUI SFTP browser row {row_name!r} kind drifted")
        actual_selected = bool(row_widget.property(route.row_selected_property))
        if actual_selected != expected_row.selected:
            errors.append(f"securecrt live GUI SFTP browser row {row_name!r} selection drifted")
        if str(row_widget.property("secureCrtSftpBrowserRowKey") or "") != expected_row.key:
            errors.append(f"securecrt live GUI SFTP browser row {row_name!r} key drifted")
        if str(row_widget.property("secureCrtSftpBrowserRowSize") or "") != expected_row.size:
            errors.append(f"securecrt live GUI SFTP browser row {row_name!r} size drifted")
        if str(row_widget.property("secureCrtSftpBrowserRowModified") or "") != expected_row.modified:
            errors.append(f"securecrt live GUI SFTP browser row {row_name!r} modified time drifted")
        if actual_selected:
            selected_rows.append(row_name)
            route_widgets["active-row"] = row_widget
    if selected_rows != [route.active_row_name]:
        errors.append(f"securecrt live GUI SFTP browser selected row {selected_rows!r} drifted")
    if errors:
        return errors
    target_actions[0].click()
    return check_securecrt_sftp_browser_live_action(route_widgets, route)


def check_securecrt_sftp_browser_live_action(route_widgets: dict[str, Any], route: Any) -> list[str]:
    expected_live_props = {
        "secureCrtSftpBrowserActionObject": route.action_object,
        "secureCrtSftpBrowserActionKey": route.action_key,
        "secureCrtSftpBrowserActionLabel": route.action_label,
        route.signal_property: route.signal,
        route.handler_property: route.handler,
        route.captured_action_property: route.action_key,
        route.captured_status_property: route.action_status,
        route.live_action_property: route.action_key,
        route.live_status_property: route.action_status,
        "secureCrtSftpBrowserRenderSource": route.render_source,
    }
    for object_name, widget in route_widgets.items():
        if bool(widget.property(route.captured_property)) is not True:
            return [
                f"securecrt live GUI SFTP browser action {object_name} "
                f"{route.captured_property} was not captured"
            ]
        if bool(widget.property(route.live_triggered_property)) is not True:
            return [
                f"securecrt live GUI SFTP browser action {object_name} "
                f"{route.live_triggered_property} was not triggered"
            ]
        for property_name, expected_value in expected_live_props.items():
            actual_value = str(widget.property(property_name) or "")
            if actual_value != expected_value:
                return [
                    f"securecrt live GUI SFTP browser action {object_name}.{property_name} "
                    f"{actual_value!r} must equal {expected_value!r}"
                ]
        if object_name == "queue" and route.action_status not in widget.text():
            return ["securecrt live GUI SFTP browser queue text did not show refreshed action status"]
    return []


def check_live_securecrt_command_window(window: Any) -> list[str]:
    from PyQt6.QtWidgets import QLabel, QLineEdit, QPushButton, QWidget

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
    target = panel.findChild(QLabel, "secureCrtCommandTarget")
    if target is None:
        return ["securecrt live GUI command-window missing target label"]
    command_input = panel.findChild(QLineEdit, "secureCrtCommandInput")
    if command_input is None:
        return ["securecrt live GUI command-window missing command input"]
    send = panel.findChild(QPushButton, "secureCrtCommandSend")
    if send is None:
        return ["securecrt live GUI command-window missing send button"]
    status = panel.findChild(QLabel, "secureCrtCommandStatus")
    if status is None:
        return ["securecrt live GUI command-window missing status label"]
    visible_texts = {label.text() for label in panel.findChildren(QLabel)}
    visible_texts.add(command_input.text())
    visible_texts.add(send.text())
    missing = sorted(required_securecrt_command_window_texts() - visible_texts)
    if missing:
        return [f"securecrt live GUI command-window missing text: {missing}"]
    for widget in (target, command_input, send, status):
        widget_key = str(widget.property("secureCrtCommandWindowKey") or "")
        if widget_key != chrome.key:
            return [f"securecrt live GUI command-window widget key {widget_key!r} must equal {chrome.key!r}"]
    target_static_width = int(target.property("secureCrtCommandStaticTargetWidth") or 0)
    target_live_width = int(target.property("secureCrtCommandLiveTargetMinWidth") or 0)
    if target_static_width != chrome.static_target_width:
        return ["securecrt live GUI command-window target static width drifted"]
    if target_live_width != chrome.live_target_min_width or target.minimumWidth() != chrome.live_target_min_width:
        return ["securecrt live GUI command-window target live width drifted"]
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
    send_static_width = int(send.property("secureCrtCommandStaticSendWidth") or 0)
    send_live_width = int(send.property("secureCrtCommandLiveSendMinWidth") or 0)
    if send_static_width != chrome.static_send_width:
        return ["securecrt live GUI command-window send static width drifted"]
    if send_live_width != chrome.live_send_min_width or send.minimumWidth() != chrome.live_send_min_width:
        return ["securecrt live GUI command-window send live width drifted"]
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
            route.captured_command_property: "",
            route.captured_target_scope_property: "",
            route.captured_status_property: "",
            route.signal_property: route.signal,
            route.secondary_signal_property: route.secondary_signal,
            route.handler_property: route.handler,
            route.live_command_property: chrome.command,
            route.live_target_scope_property: chrome.target_scope,
            route.live_status_property: chrome.status,
            "secureCrtCommandRouteRenderSource": route.render_source,
        }
        for prop_name, expected_value in expected_route_props.items():
            actual_value = str(widget.property(prop_name) or "")
            if actual_value != expected_value:
                return [
                    f"securecrt live GUI command-window send route {object_name}.{prop_name} "
                    f"{actual_value!r} must equal {expected_value!r}"
                ]
        if bool(widget.property(route.captured_property)):
            return [
                f"securecrt live GUI command-window send route {object_name}.{route.captured_property} "
                "must start false"
            ]
        if bool(widget.property(route.live_submitted_property)):
            return [
                f"securecrt live GUI command-window send route {object_name}.{route.live_submitted_property} "
                "must start false"
            ]
    for object_name, expected_text in expected_texts.items():
        actual_text = route_widgets[object_name].text()
        if actual_text != expected_text:
            return [
                f"securecrt live GUI command-window send route {object_name} text "
                f"{actual_text!r} must equal {expected_text!r}"
            ]
    if route.signal != "clicked":
        return ["securecrt live GUI command-window send route primary signal drifted"]
    if route.secondary_signal != "returnPressed":
        return ["securecrt live GUI command-window send route secondary signal drifted"]
    if route.handler != "handle_securecrt_command_window_send":
        return ["securecrt live GUI command-window send route handler drifted"]

    click_command = "$ uptime"
    command_input.setText(click_command)
    send.click()
    click_errors = check_securecrt_command_window_live_submission(
        route_widgets,
        route,
        click_command,
        trigger="clicked",
    )
    if click_errors:
        return click_errors

    enter_command = "$ whoami"
    command_input.setText(enter_command)
    command_input.returnPressed.emit()
    return check_securecrt_command_window_live_submission(
        route_widgets,
        route,
        enter_command,
        trigger="returnPressed",
    )


def check_securecrt_command_window_live_submission(
    route_widgets: dict[str, Any],
    route: Any,
    expected_command: str,
    *,
    trigger: str,
) -> list[str]:
    chrome = EXPECTED_SECURECRT_COMMAND_WINDOW_CHROME
    expected_status = "sent"
    expected_live_props = {
        route.command_property: expected_command,
        route.target_scope_property: chrome.target_scope,
        route.captured_command_property: expected_command,
        route.captured_target_scope_property: chrome.target_scope,
        route.live_command_property: expected_command,
        route.live_target_scope_property: chrome.target_scope,
        route.status_property: expected_status,
        route.captured_status_property: expected_status,
        route.live_status_property: expected_status,
        route.signal_property: route.signal,
        route.secondary_signal_property: route.secondary_signal,
        route.handler_property: route.handler,
    }
    for object_name, widget in route_widgets.items():
        if bool(widget.property(route.captured_property)) is not True:
            return [
                f"securecrt live GUI command-window {trigger} route {object_name} "
                f"{route.captured_property} was not captured"
            ]
        if bool(widget.property(route.live_submitted_property)) is not True:
            return [
                f"securecrt live GUI command-window {trigger} route {object_name} "
                f"{route.live_submitted_property} was not submitted"
            ]
        for prop_name, expected_value in expected_live_props.items():
            actual_value = str(widget.property(prop_name) or "")
            if actual_value != expected_value:
                return [
                    f"securecrt live GUI command-window {trigger} route {object_name}.{prop_name} "
                    f"{actual_value!r} must equal {expected_value!r}"
                ]
    status = route_widgets[route.status_object]
    if status.text() != expected_status:
        return [
            f"securecrt live GUI command-window {trigger} status text "
            f"{status.text()!r} must equal {expected_status!r}"
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
    if filter_input.isReadOnly():
        return ["remmina live GUI profile filter must be editable for profile-filter route"]
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
    actual_header_compact_widths = [
        int(label.property("remminaProfileColumnCompactMinWidth") or 0)
        for label in columns
    ]
    if any(
        compact <= 0 or compact > preferred
        for compact, preferred in zip(
            actual_header_compact_widths,
            expected_live_widths,
            strict=True,
        )
    ):
        return ["remmina live GUI profile header compact widths are invalid"]
    if [label.minimumWidth() for label in columns] != actual_header_compact_widths:
        return ["remmina live GUI profile header compact minimum widths drifted"]
    geometry_errors = live_widget_non_overlap_errors(
        "remmina live GUI profile headers",
        columns,
    )
    if geometry_errors:
        return geometry_errors
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
            if len(matching) != 1:
                return [
                    f"remmina live GUI profile row {row.key!r} must expose exactly one "
                    f"{column.key!r} cell, found {len(matching)}"
                ]
            cell = matching[0]
            column_width = int(cell.property("remminaProfileColumnWidth") or 0)
            live_width = int(cell.property("remminaProfileColumnLiveMinWidth") or 0)
            compact_width = int(cell.property("remminaProfileColumnCompactMinWidth") or 0)
            if column_width != column.static_width:
                return [f"remmina live GUI profile row {row.key!r} {column.key!r} static width drifted"]
            if live_width != column.live_min_width:
                return [f"remmina live GUI profile row {row.key!r} {column.key!r} preferred width metadata drifted"]
            if compact_width <= 0 or compact_width > live_width or cell.minimumWidth() != compact_width:
                return [f"remmina live GUI profile row {row.key!r} {column.key!r} compact width drifted"]
            full_text = f"{column.label}: {expected_values[column.key]}"
            if str(cell.property("remminaProfileCellFullText") or "") != full_text:
                return [f"remmina live GUI profile row {row.key!r} {column.key!r} full text metadata drifted"]
            if str(cell.property("remminaProfileCellDisplayText") or "") != cell.text() or not cell.text().strip():
                return [f"remmina live GUI profile row {row.key!r} {column.key!r} compact display text drifted"]
            if cell.accessibleName() != full_text or not cell.toolTip():
                return [f"remmina live GUI profile row {row.key!r} {column.key!r} accessible full value drifted"]
        status_cells = [
            cell for cell in cells if str(cell.property("remminaProfileColumnKey") or "") == "status"
        ]
        if len(status_cells) != 1:
            return [
                f"remmina live GUI profile row {row.key!r} must expose exactly one "
                f"status cell, found {len(status_cells)}"
            ]
        status_y = int(status_cells[0].property("remminaProfileStaticStatusY") or 0)
        if status_y != chrome.static_status_y:
            return [f"remmina live GUI profile row {row.key!r} status y drifted"]
        status = status_cells[0]
        status_full_text = f"Status: {row.status}"
        status_compact_width = int(
            status.property("remminaProfileColumnCompactMinWidth") or 0
        )
        if str(status.property("remminaProfileCellFullText") or "") != status_full_text:
            return [f"remmina live GUI profile row {row.key!r} status full text metadata drifted"]
        if str(status.property("remminaProfileCellDisplayText") or "") != status.text() or not status.text().strip():
            return [f"remmina live GUI profile row {row.key!r} status compact display text drifted"]
        if status.accessibleName() != status_full_text or not status.toolTip():
            return [f"remmina live GUI profile row {row.key!r} status accessible full value drifted"]
        if status_compact_width <= 0 or status.minimumWidth() != status_compact_width:
            return [f"remmina live GUI profile row {row.key!r} status compact width drifted"]
        geometry_errors = live_widget_non_overlap_errors(
            f"remmina live GUI profile row {row.key!r} cells",
            cells,
        )
        if geometry_errors:
            return geometry_errors
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


def check_live_remmina_profile_filter_route(window: Any) -> list[str]:
    from PyQt6.QtWidgets import QApplication, QFrame, QLineEdit, QTabWidget, QWidget

    route = EXPECTED_REMMINA_PROFILE_FILTER_ROUTE
    panel = window.findChild(QWidget, route.profile_list_object)
    filter_input = window.findChild(QLineEdit, route.filter_object)
    tabs = window.findChild(QTabWidget, "sessionTabs")
    errors: list[str] = []
    if panel is None:
        errors.append("remmina live GUI profile-filter route missing profile list panel")
    if filter_input is None:
        errors.append("remmina live GUI profile-filter route missing filter input")
    if tabs is None:
        errors.append("remmina live GUI profile-filter route missing session tabs")
    if errors:
        return errors

    route_props = {
        route.filter_route_property: route.key,
        "remminaProfileFilterRouteRole": route.route_role,
        "remminaProfileFilterRouteProfileListObject": route.profile_list_object,
        "remminaProfileFilterRouteFilterObject": route.filter_object,
        "remminaProfileFilterRouteSelectedProfileKey": route.selected_profile_key,
        "remminaProfileFilterRouteSelectedProfileObject": route.selected_profile_object,
        route.matched_profile_property: route.matched_profile_name,
        route.matched_protocol_property: route.matched_protocol,
        "remminaProfileFilterRouteMatchedStatus": route.matched_status,
        route.filter_query_property: route.expected_query,
        route.filter_placeholder_property: route.expected_placeholder,
        route.active_tab_property: route.active_tab_label,
        "remminaProfileFilterRouteSignal": route.change_signal,
        "remminaProfileFilterRouteHandler": route.handler_name,
        "remminaProfileFilterRouteRenderSource": route.render_source,
    }
    for label, widget in (("profile-list", panel), ("filter-input", filter_input)):
        for property_name, expected_value in route_props.items():
            actual_value = str(widget.property(property_name) or "")
            if actual_value != expected_value:
                errors.append(
                    f"remmina live GUI profile-filter route {label} property "
                    f"{property_name} {actual_value!r} must equal {expected_value!r}"
                )
    if filter_input.placeholderText() != route.expected_placeholder:
        errors.append("remmina live GUI profile-filter placeholder text drifted")
    if filter_input.isReadOnly():
        errors.append("remmina live GUI profile-filter input must be editable")
    if route.active_tab_label not in live_tab_labels(tabs):
        errors.append(f"remmina live GUI profile-filter route missing active tab {route.active_tab_label!r}")

    rows = panel.findChildren(QFrame, route.selected_profile_object)
    rows_by_key = {str(row.property("remminaProfileRowKey") or ""): row for row in rows}
    target_row = rows_by_key.get(route.selected_profile_key)
    if target_row is None:
        errors.append("remmina live GUI profile-filter route missing selected profile row")
    else:
        target_props = {
            route.filter_route_property: route.key,
            "remminaProfileFilterRouteRole": route.route_role,
            route.filter_query_property: route.expected_query,
            "remminaProfileFilterRouteMatched": "true",
            "remminaProfileFilterRouteSelectedProfileKey": route.selected_profile_key,
            route.matched_profile_property: route.matched_profile_name,
            route.matched_protocol_property: route.matched_protocol,
            "remminaProfileFilterRouteMatchedStatus": route.matched_status,
            route.active_tab_property: route.active_tab_label,
            "remminaProfileFilterRouteRenderSource": route.render_source,
        }
        for property_name, expected_value in target_props.items():
            actual_value = str(target_row.property(property_name) or "")
            if actual_value != expected_value:
                errors.append(f"remmina live GUI profile-filter selected row property {property_name} drifted")
        if str(target_row.property("remminaProfileProtocol") or "") != route.matched_protocol:
            errors.append("remmina live GUI profile-filter selected row protocol drifted")

    original_text = filter_input.text()
    try:
        filter_input.setText(route.expected_query)
        QApplication.processEvents()
        for key, row in rows_by_key.items():
            values = [
                str(row.property("remminaProfileRowKey") or ""),
                str(row.property("remminaProfileName") or ""),
                str(row.property("remminaProfileProtocol") or ""),
                str(row.property("remminaProfileServer") or ""),
                str(row.property("remminaProfileStatus") or ""),
            ]
            should_match = any(route.expected_query.lower() in value.lower() for value in values)
            if should_match and row.isHidden():
                errors.append(f"remmina live GUI profile-filter hid matching row {key!r}")
            if not should_match and not row.isHidden():
                errors.append(f"remmina live GUI profile-filter left non-matching row {key!r} visible")
    finally:
        filter_input.setText(original_text)
        QApplication.processEvents()
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


def check_live_remmina_screenshot_route(window: Any) -> list[str]:
    from PyQt6.QtWidgets import QTabWidget, QToolButton, QWidget

    route = EXPECTED_REMMINA_SCREENSHOT_ROUTE
    viewer_panel = window.findChild(QWidget, route.viewer_controls_object)
    tabs = window.findChild(QTabWidget, "sessionTabs")
    errors: list[str] = []
    if viewer_panel is None:
        errors.append("remmina live GUI screenshot route missing viewer controls panel")
    if tabs is None:
        errors.append("remmina live GUI screenshot route missing session tabs")
    if errors:
        return errors

    common_route_props = {
        "remminaScreenshotRouteKey": route.key,
        "remminaScreenshotRouteRole": route.route_role,
        "remminaScreenshotViewerControlsObject": route.viewer_controls_object,
        "remminaScreenshotViewerControlKey": route.viewer_control_key,
        "remminaScreenshotViewerControlObject": route.viewer_control_object,
        route.tab_label_property: route.active_tab_label,
        "remminaScreenshotRouteProtocol": route.protocol,
        route.capture_state_property: route.capture_state,
        route.capture_artifact_property: route.capture_artifact,
        "remminaScreenshotRouteStatusSegment": route.status_segment,
        "remminaScreenshotRouteDetailLine": route.detail_line,
        "remminaScreenshotRouteActivityLine": route.activity_line,
        route.signal_property: route.signal,
        route.handler_property: route.handler,
        route.captured_state_property: "",
        route.captured_artifact_property: "",
        route.live_capture_state_property: route.capture_state,
        route.live_capture_artifact_property: route.capture_artifact,
        "remminaScreenshotRouteRenderSource": route.render_source,
    }
    route_widgets = {"viewer-controls": viewer_panel}
    for property_name, expected_value in common_route_props.items():
        actual_value = str(viewer_panel.property(property_name) or "")
        if actual_value != expected_value:
            errors.append(
                f"remmina live GUI screenshot route panel property "
                f"{property_name} {actual_value!r} must equal {expected_value!r}"
            )
    if bool(viewer_panel.property(route.captured_property)):
        errors.append(f"remmina live GUI screenshot route panel {route.captured_property} must start false")
    if bool(viewer_panel.property(route.live_triggered_property)):
        errors.append(f"remmina live GUI screenshot route panel {route.live_triggered_property} must start false")

    if route.active_tab_label not in live_tab_labels(tabs):
        errors.append(f"remmina live GUI screenshot route missing active tab {route.active_tab_label!r}")

    buttons = viewer_panel.findChildren(QToolButton, route.viewer_control_object)
    target_buttons = [
        button for button in buttons if str(button.property("remminaViewerControlKey") or "") == route.viewer_control_key
    ]
    if len(target_buttons) != 1:
        errors.append("remmina live GUI screenshot route must expose one Screenshot viewer control")
    else:
        button = target_buttons[0]
        route_widgets["screenshot-button"] = button
        button_route_props = dict(common_route_props)
        button_route_props[route.control_active_property] = "true"
        for property_name, expected_value in button_route_props.items():
            actual_value = str(button.property(property_name) or "")
            if actual_value != expected_value:
                errors.append(f"remmina live GUI screenshot routed control property {property_name} drifted")
        if bool(button.property(route.captured_property)):
            errors.append(f"remmina live GUI screenshot route button {route.captured_property} must start false")
        if bool(button.property(route.live_triggered_property)):
            errors.append(f"remmina live GUI screenshot route button {route.live_triggered_property} must start false")
        if button.text() != "Screenshot":
            errors.append("remmina live GUI screenshot routed control label must be Screenshot")
        if route.signal != "clicked":
            errors.append("remmina live GUI screenshot route signal drifted")
        if route.handler != "handle_remmina_screenshot_capture":
            errors.append("remmina live GUI screenshot route handler drifted")

    inactive_route_states = [
        str(button.property(route.control_active_property) or "")
        for button in buttons
        if str(button.property("remminaViewerControlKey") or "") != route.viewer_control_key
    ]
    if any(state != "false" for state in inactive_route_states):
        errors.append("remmina live GUI non-screenshot viewer controls must not expose active screenshot route")
    if errors:
        return errors
    target_buttons[0].click()
    return check_remmina_screenshot_live_capture(route_widgets, route)


def check_remmina_screenshot_live_capture(route_widgets: dict[str, Any], route: Any) -> list[str]:
    expected_state = "captured"
    expected_live_props = {
        route.capture_state_property: route.capture_state,
        route.capture_artifact_property: route.capture_artifact,
        route.captured_state_property: expected_state,
        route.captured_artifact_property: route.capture_artifact,
        route.signal_property: route.signal,
        route.handler_property: route.handler,
        route.live_capture_state_property: expected_state,
        route.live_capture_artifact_property: route.capture_artifact,
    }
    for object_name, widget in route_widgets.items():
        if bool(widget.property(route.captured_property)) is not True:
            return [
                f"remmina live GUI screenshot click route {object_name} "
                f"{route.captured_property} was not captured"
            ]
        if bool(widget.property(route.live_triggered_property)) is not True:
            return [
                f"remmina live GUI screenshot click route {object_name} "
                f"{route.live_triggered_property} was not triggered"
            ]
        for prop_name, expected_value in expected_live_props.items():
            actual_value = str(widget.property(prop_name) or "")
            if actual_value != expected_value:
                return [
                    f"remmina live GUI screenshot click route {object_name}.{prop_name} "
                    f"{actual_value!r} must equal {expected_value!r}"
                ]
        artifact_errors = validate_remmina_screenshot_capture_artifact(
            object_name,
            widget.property("remminaScreenshotCapturePath"),
            widget.property("remminaScreenshotCaptureBytes"),
            route.capture_artifact,
        )
        if artifact_errors:
            return artifact_errors
    return []


def validate_remmina_screenshot_capture_artifact(
    object_name: str,
    path_value: Any,
    bytes_value: Any,
    expected_name: str,
) -> list[str]:
    context = f"remmina live GUI screenshot click route {object_name}"
    if not isinstance(path_value, str) or not path_value:
        return [f"{context}.remminaScreenshotCapturePath must be a non-empty string"]
    artifact_path = Path(path_value)
    if not artifact_path.is_absolute():
        return [f"{context}.remminaScreenshotCapturePath must be absolute"]
    if artifact_path.name != expected_name:
        return [
            f"{context}.remminaScreenshotCapturePath basename {artifact_path.name!r} "
            f"must equal {expected_name!r}"
        ]
    try:
        payload = artifact_path.read_bytes()
    except OSError as exc:
        return [f"{context}.remminaScreenshotCapturePath is not readable: {exc}"]
    if not payload.startswith(b"\x89PNG\r\n\x1a\n"):
        return [f"{context}.remminaScreenshotCapturePath must contain a PNG artifact"]
    if not isinstance(bytes_value, int) or isinstance(bytes_value, bool) or bytes_value <= 0:
        return [f"{context}.remminaScreenshotCaptureBytes must be a positive integer"]
    if bytes_value != len(payload):
        return [
            f"{context}.remminaScreenshotCaptureBytes {bytes_value} "
            f"must equal artifact size {len(payload)}"
        ]
    return []


def check_live_remmina_sftp_transfer_route(window: Any) -> list[str]:
    from PyQt6.QtWidgets import QFrame, QLabel, QTabWidget, QToolButton, QWidget

    route = EXPECTED_REMMINA_SFTP_TRANSFER_ROUTE
    profile_panel = window.findChild(QWidget, route.profile_list_object)
    transfer_panel = window.findChild(QWidget, route.transfer_panel_object)
    toolbar = window.findChild(QWidget, route.toolbar_object)
    path = window.findChild(QLabel, route.path_object)
    table = window.findChild(QWidget, route.table_object)
    queue = window.findChild(QLabel, route.queue_object)
    tabs = window.findChild(QTabWidget, "sessionTabs")
    errors: list[str] = []
    missing = [
        object_name
        for object_name, widget in {
            route.profile_list_object: profile_panel,
            route.transfer_panel_object: transfer_panel,
            route.toolbar_object: toolbar,
            route.path_object: path,
            route.table_object: table,
            route.queue_object: queue,
        }.items()
        if widget is None
    ]
    if tabs is None:
        missing.append("sessionTabs")
    if missing:
        return [f"remmina live GUI SFTP transfer route missing widget(s): {missing}"]

    route_widgets = {
        "profile-panel": profile_panel,
        "transfer-panel": transfer_panel,
        "toolbar": toolbar,
        "path": path,
        "table": table,
        "queue": queue,
    }
    rows_by_key = {
        row.key: row
        for row in EXPECTED_REMMINA_PROFILE_LIST_CHROME.rows
    }
    expected_profile_row = rows_by_key.get(route.selected_profile_key)
    if expected_profile_row is None:
        errors.append("remmina live GUI SFTP transfer route selected profile model row missing")
    else:
        if expected_profile_row.name != route.selected_profile_name:
            errors.append("remmina live GUI SFTP transfer route selected profile name drifted")
        if expected_profile_row.protocol != route.selected_profile_protocol:
            errors.append("remmina live GUI SFTP transfer route selected profile protocol drifted")
        if expected_profile_row.status != route.selected_profile_status:
            errors.append("remmina live GUI SFTP transfer route selected profile status drifted")

    toolbar_actions = {key: label for key, label, _tooltip in gui_design_toolbar_actions("remmina")}
    if toolbar_actions.get(route.toolbar_action_key) != route.toolbar_action_label:
        errors.append("remmina live GUI SFTP transfer route toolbar action metadata drifted")

    actions_value = "|".join(route.toolbar_actions)
    expected_common_props = {
        "remminaSftpTransferRouteKey": route.key,
        "remminaSftpTransferRouteRole": route.route_role,
        "remminaSftpTransferRouteSelectedProfileKey": route.selected_profile_key,
        route.selected_profile_property: route.selected_profile_name,
        "remminaSftpTransferRouteProtocol": route.selected_profile_protocol,
        "remminaSftpTransferRouteStatus": route.selected_profile_status,
        route.tab_label_property: route.active_tab_label,
        route.path_property: route.remote_path,
        route.queue_state_property: route.transfer_status,
        "remminaSftpTransferRouteQueueLabel": route.transfer_queue_label,
        "remminaSftpTransferRouteActionObject": route.action_object,
        "remminaSftpTransferRouteActionKey": route.action_key,
        "remminaSftpTransferRouteActionLabel": route.action_label,
        route.signal_property: route.signal,
        route.handler_property: route.handler,
        route.captured_action_property: "",
        route.captured_status_property: "",
        route.live_action_property: route.action_key,
        route.live_status_property: route.transfer_status,
        "remminaSftpTransferRouteRenderSource": route.render_source,
    }
    expected_panel_props = {
        **expected_common_props,
        "remminaSftpTransferRouteProfileListObject": route.profile_list_object,
        "remminaSftpTransferRouteSelectedProfileObject": route.selected_profile_object,
        "remminaSftpTransferRouteSelectedTreeLabel": route.selected_tree_label,
        "remminaSftpTransferRouteToolbarActionKey": route.toolbar_action_key,
        "remminaSftpTransferRouteToolbarActionLabel": route.toolbar_action_label,
        "remminaSftpTransferRouteToolbarActionObject": route.toolbar_action_object,
        "remminaSftpTransferRoutePanelObject": route.transfer_panel_object,
        "remminaSftpTransferRouteToolbarObject": route.toolbar_object,
        "remminaSftpTransferRoutePathObject": route.path_object,
        "remminaSftpTransferRouteTableObject": route.table_object,
        "remminaSftpTransferRouteRowObject": route.row_object,
        "remminaSftpTransferRouteQueueObject": route.queue_object,
        route.toolbar_actions_property: actions_value,
        "remminaSftpTransferRouteActiveRowName": route.active_row_name,
        "remminaSftpTransferRouteDetailLine": route.detail_line,
        "remminaSftpTransferRouteActivityLine": route.activity_line,
    }
    for object_name, widget in {
        route.transfer_panel_object: transfer_panel,
        route.toolbar_object: toolbar,
        route.path_object: path,
        route.table_object: table,
        route.queue_object: queue,
    }.items():
        if widget is None:
            continue
        for prop_name, expected_value in expected_panel_props.items():
            actual_value = str(widget.property(prop_name) or "")
            if actual_value != expected_value:
                errors.append(
                    f"remmina live GUI SFTP transfer route {object_name}.{prop_name} "
                    f"{actual_value!r} must equal {expected_value!r}"
                )
        if bool(widget.property(route.captured_property)):
            errors.append(f"remmina live GUI SFTP transfer route {object_name} must start uncaptured")
        if bool(widget.property(route.live_triggered_property)):
            errors.append(f"remmina live GUI SFTP transfer route {object_name} live trigger must start false")

    if profile_panel is not None:
        for prop_name, expected_value in {
            **expected_common_props,
            "remminaSftpTransferRouteProfileListObject": route.profile_list_object,
            "remminaSftpTransferRouteSelectedProfileObject": route.selected_profile_object,
            "remminaSftpTransferRouteSelectedTreeLabel": route.selected_tree_label,
            "remminaSftpTransferRouteToolbarActionKey": route.toolbar_action_key,
            "remminaSftpTransferRouteToolbarActionLabel": route.toolbar_action_label,
        }.items():
            actual_value = str(profile_panel.property(prop_name) or "")
            if actual_value != expected_value:
                errors.append(f"remmina live GUI SFTP transfer profile panel property {prop_name} drifted")
        if bool(profile_panel.property(route.captured_property)):
            errors.append("remmina live GUI SFTP transfer profile panel must start uncaptured")
        if bool(profile_panel.property(route.live_triggered_property)):
            errors.append("remmina live GUI SFTP transfer profile panel live trigger must start false")

    profile_rows = window.findChildren(QFrame, route.selected_profile_object)
    routed_rows = [
        row
        for row in profile_rows
        if str(row.property("remminaProfileRowKey") or "") == route.selected_profile_key
    ]
    if len(routed_rows) != 1:
        errors.append("remmina live GUI SFTP transfer route must expose one selected SFTP profile row")
    else:
        row = routed_rows[0]
        route_widgets["profile-row"] = row
        for prop_name, expected_value in expected_common_props.items():
            actual_value = str(row.property(prop_name) or "")
            if actual_value != expected_value:
                errors.append(f"remmina live GUI SFTP transfer profile row property {prop_name} drifted")
        if bool(row.property(route.captured_property)):
            errors.append("remmina live GUI SFTP transfer profile row must start uncaptured")
        if bool(row.property(route.live_triggered_property)):
            errors.append("remmina live GUI SFTP transfer profile row live trigger must start false")

    toolbar_buttons = window.findChildren(QToolButton, route.toolbar_action_object)
    target_buttons = [
        button
        for button in toolbar_buttons
        if str(button.property("productToolbarKey") or "") == route.toolbar_action_key
    ]
    if len(target_buttons) != 1:
        errors.append("remmina live GUI SFTP transfer route must expose one Transfer toolbar button")
    else:
        button = target_buttons[0]
        expected_button_props = {
            **expected_common_props,
            "remminaSftpTransferRouteToolbarActionKey": route.toolbar_action_key,
            "remminaSftpTransferRouteToolbarActionLabel": route.toolbar_action_label,
            "remminaSftpTransferRouteToolbarActionObject": route.toolbar_action_object,
            route.toolbar_active_property: "true",
        }
        for prop_name, expected_value in expected_button_props.items():
            actual_value = str(button.property(prop_name) or "")
            if actual_value != expected_value:
                errors.append(f"remmina live GUI SFTP transfer toolbar button property {prop_name} drifted")
        if button.text() != route.toolbar_action_label:
            errors.append("remmina live GUI SFTP transfer toolbar button label drifted")
        if bool(button.property(route.captured_property)):
            errors.append("remmina live GUI SFTP transfer toolbar button must start uncaptured")
        if bool(button.property(route.live_triggered_property)):
            errors.append("remmina live GUI SFTP transfer toolbar button live trigger must start false")

    if path is not None and route.remote_path not in path.text():
        errors.append("remmina live GUI SFTP transfer route path label drifted")
    if queue is not None:
        if route.transfer_queue_label not in queue.text() or route.transfer_status not in queue.text():
            errors.append("remmina live GUI SFTP transfer route queue label drifted")

    action_buttons = [] if toolbar is None else toolbar.findChildren(QToolButton, route.action_object)
    actual_action_keys = [str(action.property("remminaSftpTransferRouteActionKey") or "") for action in action_buttons]
    expected_action_keys = list(route.toolbar_actions)
    if actual_action_keys != expected_action_keys:
        errors.append(
            f"remmina live GUI SFTP transfer action keys {actual_action_keys!r} "
            f"must equal {expected_action_keys!r}"
        )
    for action, action_key in zip(action_buttons, route.toolbar_actions, strict=False):
        if action.text() != action_key.title():
            errors.append(f"remmina live GUI SFTP transfer action label {action.text()!r} drifted")
        if str(action.property(route.toolbar_actions_property) or "") != actions_value:
            errors.append("remmina live GUI SFTP transfer action list property drifted")
    target_actions = [
        action
        for action in action_buttons
        if str(action.property("remminaSftpTransferRouteActionKey") or "") == route.action_key
    ]
    if len(target_actions) != 1:
        errors.append("remmina live GUI SFTP transfer route must expose one routed Queue action")
    else:
        target_action = target_actions[0]
        route_widgets["queue-action"] = target_action
        expected_action_props = {
            "remminaSftpTransferRouteKey": route.key,
            "remminaSftpTransferRouteActionObject": route.action_object,
            "remminaSftpTransferRouteActionKey": route.action_key,
            "remminaSftpTransferRouteActionLabel": route.action_label,
            route.toolbar_actions_property: actions_value,
            route.signal_property: route.signal,
            route.handler_property: route.handler,
            route.captured_action_property: "",
            route.captured_status_property: "",
            route.live_action_property: route.action_key,
            route.live_status_property: route.transfer_status,
        }
        for prop_name, expected_value in expected_action_props.items():
            actual_value = str(target_action.property(prop_name) or "")
            if actual_value != expected_value:
                errors.append(f"remmina live GUI SFTP transfer routed action property {prop_name} drifted")
        if target_action.text() != route.action_label:
            errors.append("remmina live GUI SFTP transfer routed action label drifted")
        if bool(target_action.property(route.captured_property)):
            errors.append("remmina live GUI SFTP transfer routed action must start uncaptured")
        if bool(target_action.property(route.live_triggered_property)):
            errors.append("remmina live GUI SFTP transfer routed action live trigger must start false")
        if route.signal != "clicked":
            errors.append("remmina live GUI SFTP transfer route signal drifted")
        if route.handler != "handle_remmina_sftp_transfer_action":
            errors.append("remmina live GUI SFTP transfer route handler drifted")

    row_widgets = [] if table is None else table.findChildren(QFrame, route.row_object)
    if len(row_widgets) != len(route.file_rows):
        errors.append(
            f"remmina live GUI SFTP transfer row count {len(row_widgets)!r} "
            f"must equal {len(route.file_rows)!r}"
        )
    for row_widget, expected_row in zip(row_widgets, route.file_rows, strict=False):
        expected_row_props = {
            route.row_name_property: expected_row.name,
            route.row_kind_property: expected_row.kind,
            "remminaSftpTransferRouteRowKey": expected_row.key,
            "remminaSftpTransferRouteRowSize": expected_row.size,
            "remminaSftpTransferRouteRowModified": expected_row.modified,
        }
        for prop_name, expected_value in expected_row_props.items():
            actual_value = str(row_widget.property(prop_name) or "")
            if actual_value != expected_value:
                errors.append(
                    f"remmina live GUI SFTP transfer row {expected_row.key}.{prop_name} "
                    f"{actual_value!r} must equal {expected_value!r}"
                )
        actual_selected = bool(row_widget.property(route.row_selected_property))
        if actual_selected != expected_row.selected:
            errors.append(
                f"remmina live GUI SFTP transfer row {expected_row.key} selected "
                f"{actual_selected!r} must equal {expected_row.selected!r}"
            )
        if expected_row.name == route.active_row_name:
            route_widgets["active-row"] = row_widget
    selected_names = [
        str(row_widget.property(route.row_name_property) or "")
        for row_widget in row_widgets
        if bool(row_widget.property(route.row_selected_property))
    ]
    if selected_names != [route.active_row_name]:
        errors.append(
            f"remmina live GUI SFTP transfer selected rows {selected_names!r} "
            f"must equal {[route.active_row_name]!r}"
        )
    if tabs is not None and route.active_tab_label not in live_tab_labels(tabs):
        errors.append(f"remmina live GUI SFTP transfer route missing tab {route.active_tab_label!r}")
    if errors:
        return errors
    target_actions[0].click()
    return check_remmina_sftp_transfer_live_action(route_widgets, route)


def check_remmina_sftp_transfer_live_action(route_widgets: dict[str, Any], route: Any) -> list[str]:
    expected_live_props = {
        "remminaSftpTransferRouteActionObject": route.action_object,
        "remminaSftpTransferRouteActionKey": route.action_key,
        "remminaSftpTransferRouteActionLabel": route.action_label,
        route.signal_property: route.signal,
        route.handler_property: route.handler,
        route.captured_action_property: route.action_key,
        route.captured_status_property: route.action_status,
        route.live_action_property: route.action_key,
        route.live_status_property: route.action_status,
        "remminaSftpTransferRouteRenderSource": route.render_source,
    }
    for object_name, widget in route_widgets.items():
        if bool(widget.property(route.captured_property)) is not True:
            return [
                f"remmina live GUI SFTP transfer action {object_name} "
                f"{route.captured_property} was not captured"
            ]
        if bool(widget.property(route.live_triggered_property)) is not True:
            return [
                f"remmina live GUI SFTP transfer action {object_name} "
                f"{route.live_triggered_property} was not triggered"
            ]
        for prop_name, expected_value in expected_live_props.items():
            actual_value = str(widget.property(prop_name) or "")
            if actual_value != expected_value:
                return [
                    f"remmina live GUI SFTP transfer action {object_name}.{prop_name} "
                    f"{actual_value!r} must equal {expected_value!r}"
                ]
        if object_name == "queue" and route.action_status not in widget.text():
            return ["remmina live GUI SFTP transfer queue text did not show queued action status"]
    return []


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
    cells = panel.findChildren(QLabel, "termiusHostIdentityCell")
    geometry_errors = live_widget_non_overlap_errors(
        "termius live GUI host-identity cells",
        [title, *cells],
    )
    if geometry_errors:
        return geometry_errors
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
        full_text = f"{field.label}: {field.value}"
        tooltip_text = f"{full_text}\n{field.tooltip}"
        compact_width = int(cell.property("termiusHostIdentityCompactMinWidth") or 0)
        if str(cell.property("termiusHostIdentityLabel") or "") != field.label:
            return [f"termius live GUI host-identity field {field.key!r} label metadata drifted"]
        if str(cell.property("termiusHostIdentityValue") or "") != field.value:
            return [f"termius live GUI host-identity field {field.key!r} value metadata drifted"]
        if str(cell.property("termiusHostIdentityFullText") or "") != full_text:
            return [f"termius live GUI host-identity field {field.key!r} full text metadata drifted"]
        if str(cell.property("termiusHostIdentityDisplayText") or "") != cell.text() or not cell.text().strip():
            return [f"termius live GUI host-identity field {field.key!r} compact display text drifted"]
        if str(cell.property("termiusHostIdentityTooltipText") or "") != tooltip_text:
            return [f"termius live GUI host-identity field {field.key!r} tooltip metadata drifted"]
        if cell.accessibleName() != full_text or not cell.toolTip():
            return [f"termius live GUI host-identity field {field.key!r} full accessible text drifted"]
        if compact_width <= 0 or compact_width > field.live_min_width:
            return [f"termius live GUI host-identity field {field.key!r} compact width is invalid"]
        if cell.minimumWidth() != compact_width:
            return [f"termius live GUI host-identity field {field.key!r} compact minimum width drifted"]
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
        full_text = f"Host: {route.host_value}"
        if (
            str(target_cell.property("termiusHostIdentityFullText") or "") != full_text
            or target_cell.accessibleName() != full_text
        ):
            errors.append("termius live GUI host-selection route Host full identity text drifted")
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
        or str(sync_cell.property("termiusHostIdentityFullText") or "")
        != f"{expected_field.label}: {expected_field.value}"
        or sync_cell.accessibleName()
        != f"{expected_field.label}: {expected_field.value}"
    ):
        return ["termius live GUI sync route identity value drifted"]
    if expected_field.value != route.sync_state:
        return ["termius live GUI sync route expected field value must equal route state"]
    return []


def check_live_termius_port_forward_route(window: Any) -> list[str]:
    from PyQt6.QtWidgets import QLabel, QTabWidget, QWidget

    route = EXPECTED_TERMIUS_PORT_FORWARD_ROUTE
    expected_chip = next(chip for chip in gui_design_termius_header_chips() if chip.key == route.header_chip_key)
    expected_field = next(field for field in EXPECTED_TERMIUS_HOST_IDENTITY_STRIP.fields if field.key == route.identity_field_key)
    header_panel = window.findChild(QWidget, "termiusHeaderChips")
    identity_panel = window.findChild(QWidget, route.host_identity_object)
    tabs = window.findChild(QTabWidget, "sessionTabs")
    port_chip = next(
        (
            label
            for label in window.findChildren(QLabel, route.header_chip_object)
            if str(label.property("termiusHeaderChipKey") or "") == route.header_chip_key
        ),
        None,
    )
    port_cell = next(
        (
            label
            for label in window.findChildren(QLabel, route.identity_cell_object)
            if str(label.property("termiusHostIdentityKey") or "") == route.identity_field_key
        ),
        None,
    )
    errors: list[str] = []
    route_widgets = {
        "header-panel": header_panel,
        route.header_chip_object: port_chip,
        route.host_identity_object: identity_panel,
        route.identity_cell_object: port_cell,
    }
    missing = [object_name for object_name, widget in route_widgets.items() if widget is None]
    if tabs is None:
        missing.append("sessionTabs")
    if missing:
        return [f"termius live GUI port-forward route missing widget(s): {missing}"]

    expected_common_props = {
        "termiusPortForwardRouteKey": route.key,
        "termiusPortForwardRouteRole": route.route_role,
        "termiusPortForwardRouteHeaderChipKey": route.header_chip_key,
        "termiusPortForwardRouteHeaderChipObject": route.header_chip_object,
        "termiusPortForwardRouteIdentityObject": route.host_identity_object,
        "termiusPortForwardRouteIdentityFieldKey": route.identity_field_key,
        "termiusPortForwardRouteIdentityCellObject": route.identity_cell_object,
        route.active_tab_property: route.active_tab_label,
        "termiusPortForwardRouteSelectedProfile": route.selected_profile_name,
        "termiusPortForwardRouteForwardValue": route.forward_value,
        route.status_property: route.forward_state,
        "termiusPortForwardRouteRemoteHost": route.remote_host,
        "termiusPortForwardRouteStatusSegment": route.status_segment,
        "termiusPortForwardRouteRenderSource": route.render_source,
    }
    expected_int_props = {
        "termiusPortForwardRouteLocalPort": route.local_port,
        "termiusPortForwardRouteRemotePort": route.remote_port,
    }
    for object_name, widget in route_widgets.items():
        if widget is None:
            continue
        for prop_name, expected_value in expected_common_props.items():
            actual_value = str(widget.property(prop_name) or "")
            if actual_value != expected_value:
                errors.append(
                    f"termius live GUI port-forward route {object_name}.{prop_name} "
                    f"{actual_value!r} must equal {expected_value!r}"
                )
        for prop_name, expected_value in expected_int_props.items():
            actual_value = int(widget.property(prop_name) or 0)
            if actual_value != expected_value:
                errors.append(
                    f"termius live GUI port-forward route {object_name}.{prop_name} "
                    f"{actual_value!r} must equal {expected_value!r}"
                )

    if port_chip is not None:
        if str(port_chip.property(route.chip_label_property) or "") != expected_chip.label:
            errors.append("termius live GUI port-forward route header chip label property drifted")
        if port_chip.text() != expected_chip.label or expected_chip.label != route.status_segment:
            errors.append("termius live GUI port-forward route header chip text drifted")
    if port_cell is not None:
        if str(port_cell.property(route.identity_value_property) or "") != expected_field.value:
            errors.append("termius live GUI port-forward route identity value property drifted")
        full_text = f"{expected_field.label}: {expected_field.value}"
        if (
            str(port_cell.property("termiusHostIdentityFullText") or "") != full_text
            or port_cell.accessibleName() != full_text
        ):
            errors.append("termius live GUI port-forward route full identity text drifted")
        if expected_field.value != route.forward_value:
            errors.append("termius live GUI port-forward route expected field value must equal route forward value")
    if route.status_segment not in {label.text() for label in window.findChildren(QLabel, "productStatusSegment")}:
        errors.append("termius live GUI port-forward route status segment is missing")
    if tabs is not None and route.active_tab_label not in live_tab_labels(tabs):
        errors.append(f"termius live GUI port-forward route missing active tab {route.active_tab_label!r}")
    return errors


def check_live_termius_snippet_route(window: Any) -> list[str]:
    from PyQt6.QtGui import QShortcut
    from PyQt6.QtWidgets import QLabel, QTabWidget, QToolButton, QWidget

    route = EXPECTED_TERMIUS_SNIPPET_ROUTE
    expected_card = next(card for card in gui_design_workflow_cards("termius") if card.key == route.workflow_card_key)
    expected_field = next(field for field in EXPECTED_TERMIUS_HOST_IDENTITY_STRIP.fields if field.key == route.identity_field_key)
    workflow_panel = window.findChild(QWidget, "productWorkflowEvidence")
    identity_panel = window.findChild(QWidget, route.host_identity_object)
    tabs = window.findChild(QTabWidget, "sessionTabs")
    snippet_card = next(
        (
            card
            for card in window.findChildren(QWidget, route.workflow_card_object)
            if str(card.property("workflowKey") or "") == route.workflow_card_key
        ),
        None,
    )
    snippet_action = window.findChild(QToolButton, route.action_object)
    snippet_shortcut = window.findChild(QShortcut, route.shortcut_object)
    snippet_cell = next(
        (
            label
            for label in window.findChildren(QLabel, route.identity_cell_object)
            if str(label.property("termiusHostIdentityKey") or "") == route.identity_field_key
        ),
        None,
    )
    errors: list[str] = []
    route_widgets = {
        "workflow-panel": workflow_panel,
        route.workflow_card_object: snippet_card,
        route.action_object: snippet_action,
        route.shortcut_object: snippet_shortcut,
        route.host_identity_object: identity_panel,
        route.identity_cell_object: snippet_cell,
    }
    missing = [object_name for object_name, widget in route_widgets.items() if widget is None]
    if tabs is None:
        missing.append("sessionTabs")
    if missing:
        return [f"termius live GUI snippet route missing widget(s): {missing}"]

    expected_common_props = {
        "termiusSnippetRouteKey": route.key,
        "termiusSnippetRouteRole": route.route_role,
        route.workflow_key_property: route.workflow_card_key,
        "termiusSnippetRouteWorkflowCardObject": route.workflow_card_object,
        "termiusSnippetRouteActionObject": route.action_object,
        "termiusSnippetRouteShortcutObject": route.shortcut_object,
        "termiusSnippetRouteIdentityObject": route.host_identity_object,
        "termiusSnippetRouteIdentityFieldKey": route.identity_field_key,
        "termiusSnippetRouteIdentityCellObject": route.identity_cell_object,
        route.active_tab_property: route.active_tab_label,
        "termiusSnippetRouteSelectedProfile": route.selected_profile_name,
        "termiusSnippetRouteTitle": route.workflow_title,
        route.command_property: route.snippet_command,
        route.status_property: route.snippet_state,
        "termiusSnippetRouteDetailLine": route.detail_line,
        "termiusSnippetRouteActionLabel": route.action_label,
        "termiusSnippetRouteShortcutSequence": route.shortcut_sequence,
        route.captured_command_property: "",
        route.captured_target_profile_property: "",
        route.captured_status_property: "",
        route.signal_property: route.signal,
        route.secondary_signal_property: route.secondary_signal,
        route.handler_property: route.handler,
        route.live_command_property: route.snippet_command,
        route.live_target_profile_property: route.selected_profile_name,
        route.live_status_property: route.snippet_state,
        "termiusSnippetRouteRenderSource": route.render_source,
    }
    for object_name, widget in route_widgets.items():
        if widget is None:
            continue
        for prop_name, expected_value in expected_common_props.items():
            actual_value = str(widget.property(prop_name) or "")
            if actual_value != expected_value:
                errors.append(
                    f"termius live GUI snippet route {object_name}.{prop_name} "
                    f"{actual_value!r} must equal {expected_value!r}"
                )
        if bool(widget.property(route.captured_property)):
            errors.append(f"termius live GUI snippet route {object_name}.{route.captured_property} must start false")
        if bool(widget.property(route.live_triggered_property)):
            errors.append(
                f"termius live GUI snippet route {object_name}.{route.live_triggered_property} must start false"
            )

    if snippet_card is not None:
        title = snippet_card.findChild(QLabel, route.workflow_title_object)
        primary = snippet_card.findChild(QLabel, route.workflow_primary_object)
        secondary = snippet_card.findChild(QLabel, route.workflow_secondary_object)
        if title is None or title.text() != expected_card.title or expected_card.title != route.workflow_title:
            errors.append("termius live GUI snippet route workflow title drifted")
        if primary is None or primary.text() != expected_card.primary or expected_card.primary != route.snippet_command:
            errors.append("termius live GUI snippet route workflow command drifted")
        if secondary is None or secondary.text() != expected_card.secondary or expected_card.secondary != route.snippet_state:
            errors.append("termius live GUI snippet route workflow state drifted")
    if snippet_cell is not None:
        if str(snippet_cell.property(route.identity_value_property) or "") != expected_field.value:
            errors.append("termius live GUI snippet route identity value property drifted")
        full_text = f"{expected_field.label}: {expected_field.value}"
        if (
            str(snippet_cell.property("termiusHostIdentityFullText") or "") != full_text
            or snippet_cell.accessibleName() != full_text
        ):
            errors.append("termius live GUI snippet route full identity text drifted")
        if expected_field.value != route.snippet_command:
            errors.append("termius live GUI snippet route expected field value must equal route command")
    workspace_lines = {label.text() for label in window.findChildren(QLabel, "productWorkspaceLine")}
    if route.detail_line not in workspace_lines:
        errors.append("termius live GUI snippet route detail line is missing")
    if tabs is not None and route.active_tab_label not in live_tab_labels(tabs):
        errors.append(f"termius live GUI snippet route missing active tab {route.active_tab_label!r}")
    if snippet_action is not None:
        if snippet_action.text() != route.action_label:
            errors.append("termius live GUI snippet route action label drifted")
        if route.signal != "clicked":
            errors.append("termius live GUI snippet route primary signal drifted")
    if snippet_shortcut is not None:
        if str(snippet_shortcut.key().toString()) != route.shortcut_sequence:
            errors.append("termius live GUI snippet route shortcut sequence drifted")
        if route.secondary_signal != "activated":
            errors.append("termius live GUI snippet route secondary signal drifted")
    if route.handler != "handle_termius_snippet_run":
        errors.append("termius live GUI snippet route handler drifted")
    if errors:
        return errors
    if snippet_action is not None:
        snippet_action.click()
        click_errors = check_termius_snippet_live_run(route_widgets, route, trigger="clicked")
        if click_errors:
            return click_errors
    if snippet_shortcut is not None:
        snippet_shortcut.activated.emit()
        return check_termius_snippet_live_run(route_widgets, route, trigger="activated")
    return errors


def check_termius_snippet_live_run(route_widgets: dict[str, Any], route: Any, *, trigger: str) -> list[str]:
    expected_status = "ran"
    expected_live_props = {
        route.command_property: route.snippet_command,
        route.status_property: expected_status,
        route.captured_command_property: route.snippet_command,
        route.captured_target_profile_property: route.selected_profile_name,
        route.captured_status_property: expected_status,
        route.signal_property: route.signal,
        route.secondary_signal_property: route.secondary_signal,
        route.handler_property: route.handler,
        route.live_command_property: route.snippet_command,
        route.live_target_profile_property: route.selected_profile_name,
        route.live_status_property: expected_status,
    }
    for object_name, widget in route_widgets.items():
        if widget is None:
            continue
        if bool(widget.property(route.captured_property)) is not True:
            return [
                f"termius live GUI snippet {trigger} route {object_name} "
                f"{route.captured_property} was not captured"
            ]
        if bool(widget.property(route.live_triggered_property)) is not True:
            return [
                f"termius live GUI snippet {trigger} route {object_name} "
                f"{route.live_triggered_property} was not triggered"
            ]
        for prop_name, expected_value in expected_live_props.items():
            actual_value = str(widget.property(prop_name) or "")
            if actual_value != expected_value:
                return [
                    f"termius live GUI snippet {trigger} route {object_name}.{prop_name} "
                    f"{actual_value!r} must equal {expected_value!r}"
                ]
    return []


def check_live_termius_files_browser_route(window: Any) -> list[str]:
    from PyQt6.QtWidgets import QFrame, QLabel, QTabWidget, QToolButton, QWidget

    route = EXPECTED_TERMIUS_FILES_BROWSER_ROUTE
    host_route = EXPECTED_TERMIUS_HOST_SELECTION_ROUTE
    expected_field = next(field for field in EXPECTED_TERMIUS_HOST_IDENTITY_STRIP.fields if field.key == route.identity_field_key)
    browser = window.findChild(QWidget, route.files_browser_object)
    toolbar = window.findChild(QWidget, route.toolbar_object)
    path = window.findChild(QLabel, route.path_object)
    table = window.findChild(QWidget, route.table_object)
    queue = window.findChild(QLabel, route.queue_object)
    identity_panel = window.findChild(QWidget, route.host_identity_object)
    tabs = window.findChild(QTabWidget, "sessionTabs")
    files_cell = next(
        (
            label
            for label in window.findChildren(QLabel, route.identity_cell_object)
            if str(label.property("termiusHostIdentityKey") or "") == route.identity_field_key
        ),
        None,
    )
    errors: list[str] = []
    missing = [
        object_name
        for object_name, widget in {
            route.files_browser_object: browser,
            route.toolbar_object: toolbar,
            route.path_object: path,
            route.table_object: table,
            route.queue_object: queue,
            route.host_identity_object: identity_panel,
            route.identity_cell_object: files_cell,
        }.items()
        if widget is None
    ]
    if tabs is None:
        missing.append("sessionTabs")
    if missing:
        return [f"termius live GUI files browser route missing widget(s): {missing}"]
    route_widgets = {
        "browser": browser,
        "toolbar": toolbar,
        "path": path,
        "table": table,
        "queue": queue,
        "identity-panel": identity_panel,
        "identity-cell": files_cell,
    }

    if route.host_selection_route_key != host_route.key:
        errors.append("termius live GUI files browser route host-selection key drifted")
    if route.active_tab_label != host_route.active_tab_label:
        errors.append("termius live GUI files browser route active tab drifted from host route")
    if route.selected_profile_name != host_route.selected_profile_name:
        errors.append("termius live GUI files browser route selected profile drifted from host route")
    if route.selected_tree_label != host_route.selected_tree_label:
        errors.append("termius live GUI files browser route selected tree label drifted from host route")
    if expected_field.value != route.files_state:
        errors.append("termius live GUI files browser route identity field value must equal route state")

    actions_value = "|".join(route.toolbar_actions)
    expected_common_props = {
        "termiusFilesRouteKey": route.key,
        "termiusFilesRouteRole": route.route_role,
        "termiusFilesRouteHostSelectionKey": route.host_selection_route_key,
        "termiusFilesRouteIdentityObject": route.host_identity_object,
        "termiusFilesRouteIdentityFieldKey": route.identity_field_key,
        "termiusFilesRouteIdentityCellObject": route.identity_cell_object,
        "termiusFilesRouteBrowserObject": route.files_browser_object,
        route.active_tab_property: route.active_tab_label,
        "termiusFilesRouteSelectedProfile": route.selected_profile_name,
        "termiusFilesRouteSelectedTreeLabel": route.selected_tree_label,
        route.identity_value_property: route.files_state,
        "termiusFilesRouteState": route.files_state,
        route.path_property: route.remote_path,
        "termiusFilesRouteQueueState": route.transfer_status,
        "termiusFilesRouteActionObject": route.action_object,
        "termiusFilesRouteActionKey": route.action_key,
        "termiusFilesRouteActionLabel": route.action_label,
        route.signal_property: route.signal,
        route.handler_property: route.handler,
        route.captured_action_property: "",
        route.captured_status_property: "",
        route.live_action_property: route.action_key,
        route.live_status_property: route.transfer_status,
        "termiusFilesRouteRenderSource": route.render_source,
    }
    expected_browser_props = {
        **expected_common_props,
        "termiusFilesRouteToolbarObject": route.toolbar_object,
        "termiusFilesRoutePathObject": route.path_object,
        "termiusFilesRouteTableObject": route.table_object,
        "termiusFilesRouteRowObject": route.row_object,
        "termiusFilesRouteQueueObject": route.queue_object,
        route.toolbar_actions_property: actions_value,
        "termiusFilesRouteActiveRowName": route.active_row_name,
        "termiusFilesRouteQueueLabel": route.transfer_queue_label,
    }
    for object_name, widget in {
        route.files_browser_object: browser,
        route.toolbar_object: toolbar,
        route.path_object: path,
        route.table_object: table,
        route.queue_object: queue,
    }.items():
        if widget is None:
            continue
        for prop_name, expected_value in expected_browser_props.items():
            actual_value = str(widget.property(prop_name) or "")
            if actual_value != expected_value:
                errors.append(
                    f"termius live GUI files browser route {object_name}.{prop_name} "
                    f"{actual_value!r} must equal {expected_value!r}"
                )
        if bool(widget.property(route.captured_property)):
            errors.append(f"termius live GUI files browser route {object_name} must start uncaptured")
        if bool(widget.property(route.live_triggered_property)):
            errors.append(f"termius live GUI files browser route {object_name} live trigger must start false")

    for object_name, widget in {
        route.host_identity_object: identity_panel,
        route.identity_cell_object: files_cell,
    }.items():
        if widget is None:
            continue
        for prop_name, expected_value in expected_common_props.items():
            actual_value = str(widget.property(prop_name) or "")
            if actual_value != expected_value:
                errors.append(
                    f"termius live GUI files browser route {object_name}.{prop_name} "
                    f"{actual_value!r} must equal {expected_value!r}"
                )
        if bool(widget.property(route.captured_property)):
            errors.append(f"termius live GUI files browser route {object_name} must start uncaptured")
        if bool(widget.property(route.live_triggered_property)):
            errors.append(f"termius live GUI files browser route {object_name} live trigger must start false")

    if path is not None and route.remote_path not in path.text():
        errors.append("termius live GUI files browser route path label drifted")
    if queue is not None:
        if route.transfer_queue_label not in queue.text() or route.transfer_status not in queue.text():
            errors.append("termius live GUI files browser route queue label drifted")
    if files_cell is not None:
        if str(files_cell.property(route.identity_value_property) or "") != expected_field.value:
            errors.append("termius live GUI files browser route identity value property drifted")
        full_text = f"{expected_field.label}: {expected_field.value}"
        if (
            str(files_cell.property("termiusHostIdentityFullText") or "") != full_text
            or files_cell.accessibleName() != full_text
        ):
            errors.append("termius live GUI files browser route full identity text drifted")

    action_labels = [] if toolbar is None else toolbar.findChildren(QToolButton, route.action_object)
    actual_action_keys = [str(action.property("termiusFilesRouteActionKey") or "") for action in action_labels]
    expected_action_keys = list(route.toolbar_actions)
    if actual_action_keys != expected_action_keys:
        errors.append(
            f"termius live GUI files browser route action keys {actual_action_keys!r} "
            f"must equal {expected_action_keys!r}"
        )
    for action, action_key in zip(action_labels, route.toolbar_actions, strict=False):
        if action.text() != action_key.title():
            errors.append(f"termius live GUI files browser route action label {action.text()!r} drifted")
        if str(action.property(route.toolbar_actions_property) or "") != actions_value:
            errors.append("termius live GUI files browser route action list property drifted")
    target_actions = [
        action
        for action in action_labels
        if str(action.property("termiusFilesRouteActionKey") or "") == route.action_key
    ]
    if len(target_actions) != 1:
        errors.append("termius live GUI files browser route must expose one routed Sync action")
    else:
        target_action = target_actions[0]
        route_widgets["sync-action"] = target_action
        expected_action_props = {
            "termiusFilesRouteKey": route.key,
            "termiusFilesRouteActionObject": route.action_object,
            "termiusFilesRouteActionKey": route.action_key,
            "termiusFilesRouteActionLabel": route.action_label,
            route.toolbar_actions_property: actions_value,
            route.signal_property: route.signal,
            route.handler_property: route.handler,
            route.captured_action_property: "",
            route.captured_status_property: "",
            route.live_action_property: route.action_key,
            route.live_status_property: route.transfer_status,
        }
        for prop_name, expected_value in expected_action_props.items():
            actual_value = str(target_action.property(prop_name) or "")
            if actual_value != expected_value:
                errors.append(f"termius live GUI files routed action property {prop_name} drifted")
        if target_action.text() != route.action_label:
            errors.append("termius live GUI files routed action label drifted")
        if bool(target_action.property(route.captured_property)):
            errors.append("termius live GUI files routed action must start uncaptured")
        if bool(target_action.property(route.live_triggered_property)):
            errors.append("termius live GUI files routed action live trigger must start false")
        if route.signal != "clicked":
            errors.append("termius live GUI files browser action signal drifted")
        if route.handler != "handle_termius_files_sync":
            errors.append("termius live GUI files browser action handler drifted")

    row_widgets = [] if table is None else table.findChildren(QFrame, route.row_object)
    if len(row_widgets) != len(route.file_rows):
        errors.append(
            f"termius live GUI files browser route row count {len(row_widgets)!r} "
            f"must equal {len(route.file_rows)!r}"
        )
    for row_widget, expected_row in zip(row_widgets, route.file_rows, strict=False):
        expected_row_props = {
            route.row_name_property: expected_row.name,
            route.row_kind_property: expected_row.kind,
            "termiusFilesRouteRowKey": expected_row.key,
            "termiusFilesRouteRowSize": expected_row.size,
            "termiusFilesRouteRowModified": expected_row.modified,
        }
        for prop_name, expected_value in expected_row_props.items():
            actual_value = str(row_widget.property(prop_name) or "")
            if actual_value != expected_value:
                errors.append(
                    f"termius live GUI files browser route row {expected_row.key}.{prop_name} "
                    f"{actual_value!r} must equal {expected_value!r}"
                )
        actual_selected = bool(row_widget.property(route.row_selected_property))
        if actual_selected != expected_row.selected:
            errors.append(
                f"termius live GUI files browser route row {expected_row.key} selected "
                f"{actual_selected!r} must equal {expected_row.selected!r}"
            )
        if expected_row.name == route.active_row_name:
            route_widgets["active-row"] = row_widget
    selected_names = [
        str(row_widget.property(route.row_name_property) or "")
        for row_widget in row_widgets
        if bool(row_widget.property(route.row_selected_property))
    ]
    if selected_names != [route.active_row_name]:
        errors.append(
            f"termius live GUI files browser route selected rows {selected_names!r} "
            f"must equal {[route.active_row_name]!r}"
        )
    if tabs is not None and route.active_tab_label not in live_tab_labels(tabs):
        errors.append(f"termius live GUI files browser route missing active tab {route.active_tab_label!r}")
    if errors:
        return errors
    target_actions[0].click()
    return check_termius_files_sync_live_action(route_widgets, route)


def check_termius_files_sync_live_action(route_widgets: dict[str, Any], route: Any) -> list[str]:
    expected_live_props = {
        "termiusFilesRouteActionObject": route.action_object,
        "termiusFilesRouteActionKey": route.action_key,
        "termiusFilesRouteActionLabel": route.action_label,
        route.signal_property: route.signal,
        route.handler_property: route.handler,
        route.captured_action_property: route.action_key,
        route.captured_status_property: route.action_status,
        route.live_action_property: route.action_key,
        route.live_status_property: route.action_status,
        "termiusFilesRouteRenderSource": route.render_source,
    }
    for object_name, widget in route_widgets.items():
        if bool(widget.property(route.captured_property)) is not True:
            return [
                f"termius live GUI files sync action {object_name} "
                f"{route.captured_property} was not captured"
            ]
        if bool(widget.property(route.live_triggered_property)) is not True:
            return [
                f"termius live GUI files sync action {object_name} "
                f"{route.live_triggered_property} was not triggered"
            ]
        for prop_name, expected_value in expected_live_props.items():
            actual_value = str(widget.property(prop_name) or "")
            if actual_value != expected_value:
                return [
                    f"termius live GUI files sync action {object_name}.{prop_name} "
                    f"{actual_value!r} must equal {expected_value!r}"
                ]
        if object_name == "queue" and route.action_status not in widget.text():
            return ["termius live GUI files sync queue text did not show synced action status"]
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
        expected_state = (
            "checked" if control.key in {"external-tool", "dock-view"} else "normal"
        )
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

    headers = panel.findChildren(QLabel, "mRemoteNgPropertyGridColumn")
    if [str(label.property("mRemoteNgPropertyColumnKey") or "") for label in headers] != (
        EXPECTED_MREMOTENG_PROPERTY_COLUMN_KEYS
    ):
        return ["mremoteng live GUI property-grid header keys drifted"]
    header_geometry_errors = live_widget_non_overlap_errors(
        "mremoteng live GUI property-grid headers",
        headers,
    )
    if header_geometry_errors:
        return header_geometry_errors
    for header, column in zip(headers, chrome.columns, strict=True):
        preferred_width = int(
            header.property("mRemoteNgPropertyLivePreferredWidth") or 0
        )
        compact_width = int(
            header.property("mRemoteNgPropertyLiveCompactMinWidth") or 0
        )
        expected_preferred = max(72, min(column.static_width, 190))
        if preferred_width != expected_preferred:
            return [f"mremoteng live GUI property-grid header {column.key!r} preferred width drifted"]
        if compact_width <= 0 or compact_width > preferred_width:
            return [f"mremoteng live GUI property-grid header {column.key!r} compact width is invalid"]
        if header.minimumWidth() != compact_width:
            return [f"mremoteng live GUI property-grid header {column.key!r} compact minimum width drifted"]

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
    for row_frame, row in zip(row_frames, chrome.rows, strict=True):
        row_cells = row_frame.findChildren(QLabel, "mRemoteNgPropertyGridCell")
        row_keys = [
            str(cell.property("mRemoteNgPropertyColumnKey") or "")
            for cell in row_cells
        ]
        if row_keys != EXPECTED_MREMOTENG_PROPERTY_COLUMN_KEYS:
            return [f"mremoteng live GUI property-grid row {row.key!r} cell keys drifted"]
        geometry_errors = live_widget_non_overlap_errors(
            f"mremoteng live GUI property-grid row {row.key!r} cells",
            row_cells,
        )
        if geometry_errors:
            return geometry_errors
        values = {
            "property": row.property_label,
            "inherited": row.inherited_from,
            "effective": row.effective_value,
            "source": row.source,
        }
        for cell, column in zip(row_cells, chrome.columns, strict=True):
            full_text = f"{column.label}: {values[column.key]}"
            preferred_width = int(
                cell.property("mRemoteNgPropertyLivePreferredWidth") or 0
            )
            compact_width = int(
                cell.property("mRemoteNgPropertyLiveCompactMinWidth") or 0
            )
            expected_preferred = max(72, min(column.static_width, 190))
            if str(cell.property("mRemoteNgPropertyCellFullText") or "") != full_text:
                return [f"mremoteng live GUI property-grid row {row.key!r} {column.key!r} full text drifted"]
            if cell.accessibleName() != full_text or not cell.toolTip():
                return [f"mremoteng live GUI property-grid row {row.key!r} {column.key!r} accessible value drifted"]
            if preferred_width != expected_preferred:
                return [f"mremoteng live GUI property-grid row {row.key!r} {column.key!r} preferred width drifted"]
            if compact_width <= 0 or compact_width > preferred_width or cell.minimumWidth() != compact_width:
                return [f"mremoteng live GUI property-grid row {row.key!r} {column.key!r} compact width drifted"]
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
        route.signal_property: route.signal,
        route.handler_property: route.handler,
        route.captured_state_property: "",
        route.captured_profile_property: "",
        route.live_state_property: route.workspace_state,
        route.live_profile_property: route.selected_profile_name,
        "mRemoteNgConnectionRouteRenderSource": route.render_source,
    }
    route_widgets = {
        "connection-tree": tree,
        "document-controls": controls_panel,
        "property-grid": property_grid,
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
        if bool(widget.property(route.captured_property)):
            errors.append(f"mremoteng live GUI connection-document route {label} must start uncaptured")
        if bool(widget.property(route.live_triggered_property)):
            errors.append(f"mremoteng live GUI connection-document route {label} live trigger must start false")

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
        route_widgets["reconnect-button"] = target_button
        expected_button_props = {
            "mRemoteNgConnectionRouteKey": route.key,
            "mRemoteNgConnectionRouteRole": route.route_role,
            "mRemoteNgConnectionRouteSelectedProfile": route.selected_profile_name,
            "mRemoteNgConnectionRouteSelectedTreeLabel": route.selected_tree_label,
            "mRemoteNgConnectionRouteDocumentControlsObject": route.document_controls_object,
            "mRemoteNgConnectionRouteDocumentControlKey": route.document_control_key,
            "mRemoteNgConnectionRouteDocumentControlObject": route.document_control_object,
            "mRemoteNgConnectionRoutePropertyGridObject": route.property_grid_object,
            route.tab_label_property: route.active_tab_label,
            "mRemoteNgConnectionRouteProtocol": route.protocol,
            "mRemoteNgConnectionRouteState": route.workspace_state,
            "mRemoteNgConnectionRoutePropertyRowKey": route.property_row_key,
            "mRemoteNgConnectionRoutePropertyCellObject": route.property_cell_object,
            route.property_value_property: route.property_value,
            route.signal_property: route.signal,
            route.handler_property: route.handler,
            route.captured_state_property: "",
            route.captured_profile_property: "",
            route.live_state_property: route.workspace_state,
            route.live_profile_property: route.selected_profile_name,
            "mRemoteNgConnectionRouteRenderSource": route.render_source,
            route.control_active_property: "true",
        }
        for property_name, expected_value in expected_button_props.items():
            actual_value = str(target_button.property(property_name) or "")
            if actual_value != expected_value:
                errors.append(f"mremoteng live GUI routed document control property {property_name} drifted")
        if bool(target_button.property(route.captured_property)):
            errors.append("mremoteng live GUI routed Reconnect control must start uncaptured")
        if bool(target_button.property(route.live_triggered_property)):
            errors.append("mremoteng live GUI routed Reconnect control live trigger must start false")
        if target_button.text() != "Reconnect":
            errors.append("mremoteng live GUI routed document control label must be Reconnect")
        if route.signal != "clicked":
            errors.append("mremoteng live GUI reconnect route signal drifted")
        if route.handler != "handle_mremoteng_document_reconnect":
            errors.append("mremoteng live GUI reconnect route handler drifted")

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
        route_widgets["property-row"] = route_row
        expected_row_props = {
            "mRemoteNgConnectionRouteKey": route.key,
            "mRemoteNgConnectionRouteRole": route.route_role,
            "mRemoteNgConnectionRouteSelectedProfile": route.selected_profile_name,
            "mRemoteNgConnectionRouteSelectedTreeLabel": route.selected_tree_label,
            "mRemoteNgConnectionRouteDocumentControlsObject": route.document_controls_object,
            "mRemoteNgConnectionRouteDocumentControlKey": route.document_control_key,
            "mRemoteNgConnectionRouteDocumentControlObject": route.document_control_object,
            "mRemoteNgConnectionRoutePropertyGridObject": route.property_grid_object,
            route.tab_label_property: route.active_tab_label,
            "mRemoteNgConnectionRouteProtocol": route.protocol,
            "mRemoteNgConnectionRouteState": route.workspace_state,
            "mRemoteNgConnectionRoutePropertyRowKey": route.property_row_key,
            "mRemoteNgConnectionRoutePropertyCellObject": route.property_cell_object,
            route.property_value_property: route.property_value,
            route.signal_property: route.signal,
            route.handler_property: route.handler,
            route.captured_state_property: "",
            route.captured_profile_property: "",
            route.live_state_property: route.workspace_state,
            route.live_profile_property: route.selected_profile_name,
            "mRemoteNgConnectionRouteRenderSource": route.render_source,
        }
        for property_name, expected_value in expected_row_props.items():
            actual_value = str(route_row.property(property_name) or "")
            if actual_value != expected_value:
                errors.append(f"mremoteng live GUI property-grid route row property {property_name} drifted")
        if bool(route_row.property(route.captured_property)):
            errors.append("mremoteng live GUI property-grid route row must start uncaptured")
        if bool(route_row.property(route.live_triggered_property)):
            errors.append("mremoteng live GUI property-grid route row live trigger must start false")

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
        route_widgets["property-effective-cell"] = route_cell
        if str(route_cell.property("mRemoteNgPropertyCellValue") or "") != route.property_value:
            errors.append("mremoteng live GUI connection-document route property effective value drifted")
        if str(route_cell.property(route.property_value_property) or "") != route.property_value:
            errors.append("mremoteng live GUI connection-document route property value metadata drifted")
        if bool(route_cell.property(route.captured_property)):
            errors.append("mremoteng live GUI property effective route cell must start uncaptured")
        if bool(route_cell.property(route.live_triggered_property)):
            errors.append("mremoteng live GUI property effective route cell live trigger must start false")
    if errors:
        return errors
    target_buttons[0].click()
    return check_mremoteng_reconnect_live_route(route_widgets, route)


def check_mremoteng_reconnect_live_route(route_widgets: dict[str, Any], route: Any) -> list[str]:
    expected_live_props = {
        "mRemoteNgConnectionRouteState": route.workspace_state,
        route.property_value_property: route.property_value,
        route.signal_property: route.signal,
        route.handler_property: route.handler,
        route.captured_state_property: route.reconnect_state,
        route.captured_profile_property: route.selected_profile_name,
        route.live_state_property: route.reconnect_state,
        route.live_profile_property: route.selected_profile_name,
        "mRemoteNgConnectionRouteRenderSource": route.render_source,
    }
    for object_name, widget in route_widgets.items():
        if bool(widget.property(route.captured_property)) is not True:
            return [
                f"mremoteng live GUI reconnect route {object_name} "
                f"{route.captured_property} was not captured"
            ]
        if bool(widget.property(route.live_triggered_property)) is not True:
            return [
                f"mremoteng live GUI reconnect route {object_name} "
                f"{route.live_triggered_property} was not triggered"
            ]
        for prop_name, expected_value in expected_live_props.items():
            actual_value = str(widget.property(prop_name) or "")
            if actual_value != expected_value:
                return [
                    f"mremoteng live GUI reconnect route {object_name}.{prop_name} "
                    f"{actual_value!r} must equal {expected_value!r}"
                ]
    return []


def check_live_mremoteng_document_filter_route(window: Any) -> list[str]:
    from PyQt6.QtCore import Qt
    from PyQt6.QtWidgets import QApplication, QLineEdit, QTabWidget, QTreeWidget, QWidget

    route = EXPECTED_MREMOTENG_DOCUMENT_FILTER_ROUTE
    tree = window.findChild(QTreeWidget, route.selected_tree_object)
    controls_panel = window.findChild(QWidget, route.document_controls_object)
    filter_input = window.findChild(QLineEdit, route.filter_object)
    tabs = window.findChild(QTabWidget, "sessionTabs")
    errors: list[str] = []
    if tree is None:
        errors.append("mremoteng live GUI document-filter route missing connection tree")
    if controls_panel is None:
        errors.append("mremoteng live GUI document-filter route missing document controls")
    if filter_input is None:
        errors.append("mremoteng live GUI document-filter route missing filter input")
    if tabs is None:
        errors.append("mremoteng live GUI document-filter route missing session tabs")
    if errors:
        return errors

    route_props = {
        route.filter_route_property: route.key,
        "mRemoteNgDocumentFilterRouteRole": route.route_role,
        "mRemoteNgDocumentFilterRouteDocumentControlsObject": route.document_controls_object,
        "mRemoteNgDocumentFilterRouteFilterObject": route.filter_object,
        "mRemoteNgDocumentFilterRouteSelectedTreeObject": route.selected_tree_object,
        "mRemoteNgDocumentFilterRouteSelectedProfile": route.selected_profile_name,
        route.matched_tree_property: route.selected_tree_label,
        route.matched_protocol_property: route.matched_protocol,
        "mRemoteNgDocumentFilterRouteMatchedState": route.matched_state,
        route.filter_query_property: route.expected_query,
        route.filter_placeholder_property: route.expected_placeholder,
        route.active_tab_property: route.active_tab_label,
        "mRemoteNgDocumentFilterRouteSignal": route.change_signal,
        "mRemoteNgDocumentFilterRouteHandler": route.handler_name,
        "mRemoteNgDocumentFilterRouteRenderSource": route.render_source,
    }
    for widget_label, widget in (
        ("connection-tree", tree),
        ("document-controls", controls_panel),
        ("filter", filter_input),
    ):
        for property_name, expected_value in route_props.items():
            actual_value = str(widget.property(property_name) or "")
            if actual_value != expected_value:
                errors.append(
                    f"mremoteng live GUI document-filter route {widget_label} property "
                    f"{property_name} {actual_value!r} must equal {expected_value!r}"
                )

    if filter_input.placeholderText() != route.expected_placeholder:
        errors.append("mremoteng live GUI document-filter route placeholder drifted")
    if filter_input.isReadOnly():
        errors.append("mremoteng live GUI document-filter route input must be editable")
    if route.active_tab_label not in live_tab_labels(tabs):
        errors.append(f"mremoteng live GUI document-filter route missing active tab {route.active_tab_label!r}")

    def tree_items() -> list[Any]:
        items: list[Any] = []

        def walk(item: Any) -> None:
            items.append(item)
            for child_index in range(item.childCount()):
                walk(item.child(child_index))

        for index in range(tree.topLevelItemCount()):
            walk(tree.topLevelItem(index))
        return items

    items = tree_items()
    matched_items = [item for item in items if item.text(0) == route.selected_tree_label]
    if len(matched_items) != 1:
        errors.append("mremoteng live GUI document-filter route must expose one matched tree row")
    else:
        matched_item = matched_items[0]
        base_role = int(Qt.ItemDataRole.UserRole)
        expected_item_data = {
            base_role: route.selected_profile_name,
            base_role + 91: route.key,
            base_role + 92: route.route_role,
            base_role + 93: route.expected_query,
            base_role + 94: route.selected_profile_name,
            base_role + 95: route.selected_tree_label,
            base_role + 97: route.render_source,
        }
        for role, expected_value in expected_item_data.items():
            actual_value = str(matched_item.data(0, role) or "")
            if actual_value != expected_value:
                errors.append(f"mremoteng live GUI document-filter route tree role {role} drifted")
        if matched_item.data(0, base_role + 96) is not True:
            errors.append("mremoteng live GUI document-filter route matched row is not marked")

    original_text = filter_input.text()
    try:
        filter_input.setText(route.expected_query)
        QApplication.processEvents()
        items_after_filter = tree_items()
        matched_after_filter = [item for item in items_after_filter if item.text(0) == route.selected_tree_label]
        if not matched_after_filter or matched_after_filter[0].isHidden():
            errors.append("mremoteng live GUI document-filter route hides the matched selected row")
        profile_items = [item for item in items_after_filter if item.data(0, int(Qt.ItemDataRole.UserRole))]
        nonmatching_items = [
            item
            for item in profile_items
            if route.expected_query.lower() not in item.text(0).lower()
            and route.expected_query.lower() not in item.toolTip(0).lower()
        ]
        if not nonmatching_items:
            errors.append("mremoteng live GUI document-filter route needs at least one nonmatching row")
        elif not any(item.isHidden() for item in nonmatching_items):
            errors.append("mremoteng live GUI document-filter route does not hide nonmatching rows")
    finally:
        filter_input.setText(original_text)
        QApplication.processEvents()
    return errors


def check_live_mremoteng_inheritance_route(window: Any) -> list[str]:
    from PyQt6.QtWidgets import QLabel, QTabWidget, QWidget

    route = EXPECTED_MREMOTENG_INHERITANCE_ROUTE
    workflow_panel = window.findChild(QWidget, "productWorkflowEvidence")
    property_grid = window.findChild(QWidget, route.property_grid_object)
    tabs = window.findChild(QTabWidget, "sessionTabs")
    errors: list[str] = []
    if workflow_panel is None:
        errors.append("mremoteng live GUI inheritance route missing workflow evidence panel")
    if property_grid is None:
        errors.append("mremoteng live GUI inheritance route missing property grid")
    if tabs is None:
        errors.append("mremoteng live GUI inheritance route missing session tabs")
    if errors:
        return errors

    common_route_props = {
        "mRemoteNgInheritanceRouteKey": route.key,
        "mRemoteNgInheritanceRouteRole": route.route_role,
        route.workflow_key_property: route.workflow_card_key,
        "mRemoteNgInheritanceRouteWorkflowCardObject": route.workflow_card_object,
        "mRemoteNgInheritanceRouteTitleObject": route.workflow_title_object,
        "mRemoteNgInheritanceRoutePrimaryObject": route.workflow_primary_object,
        "mRemoteNgInheritanceRouteSecondaryObject": route.workflow_secondary_object,
        "mRemoteNgInheritanceRoutePropertyGridObject": route.property_grid_object,
        "mRemoteNgInheritanceRoutePropertyRowKey": route.property_row_key,
        "mRemoteNgInheritanceRoutePropertyCellObject": route.property_cell_object,
        route.active_tab_property: route.active_tab_label,
        "mRemoteNgInheritanceRouteSelectedProfile": route.selected_profile_name,
        "mRemoteNgInheritanceRouteSelectedTreeLabel": route.selected_tree_label,
        "mRemoteNgInheritanceRouteTitle": route.workflow_title,
        "mRemoteNgInheritanceRouteInheritedPropertyLabel": route.inherited_property_label,
        route.inherited_value_property: route.inherited_value,
        "mRemoteNgInheritanceRouteInheritedSource": route.inherited_source,
        route.status_property: route.inheritance_state,
        "mRemoteNgInheritanceRouteRenderSource": route.render_source,
    }
    panel_props = dict(common_route_props)
    panel_props.pop(route.workflow_key_property)
    panel_props["mRemoteNgInheritanceRouteWorkflowKey"] = route.workflow_card_key
    panel_props.pop(route.inherited_value_property)
    panel_props["mRemoteNgInheritanceRouteInheritedValue"] = route.inherited_value
    panel_props.pop(route.active_tab_property)
    panel_props["mRemoteNgInheritanceRouteActiveTab"] = route.active_tab_label
    panel_props.pop(route.status_property)
    panel_props["mRemoteNgInheritanceRouteState"] = route.inheritance_state

    for label, widget, route_props in (
        ("workflow-panel", workflow_panel, panel_props),
        ("property-grid", property_grid, panel_props),
    ):
        for property_name, expected_value in route_props.items():
            actual_value = str(widget.property(property_name) or "")
            if actual_value != expected_value:
                errors.append(
                    f"mremoteng live GUI inheritance route {label} property "
                    f"{property_name} {actual_value!r} must equal {expected_value!r}"
                )

    workflow_cards = [
        widget
        for widget in workflow_panel.findChildren(QWidget, route.workflow_card_object)
        if str(widget.property("workflowKey") or "") == route.workflow_card_key
    ]
    if len(workflow_cards) != 1:
        errors.append("mremoteng live GUI inheritance route must expose one workflow card")
    else:
        workflow_card = workflow_cards[0]
        for property_name, expected_value in panel_props.items():
            actual_value = str(workflow_card.property(property_name) or "")
            if actual_value != expected_value:
                errors.append(f"mremoteng live GUI inheritance workflow card property {property_name} drifted")
        card_labels = {label.objectName(): label.text() for label in workflow_card.findChildren(QLabel)}
        expected_card_text = {
            route.workflow_title_object: route.workflow_title,
            route.workflow_primary_object: route.inheritance_state,
            route.workflow_secondary_object: "property grid visible",
        }
        for object_name, expected_text in expected_card_text.items():
            if card_labels.get(object_name) != expected_text:
                errors.append(f"mremoteng live GUI inheritance workflow label {object_name} drifted")

    row_frames = property_grid.findChildren(QWidget, "mRemoteNgPropertyGridRow")
    route_rows = [row for row in row_frames if str(row.property("mRemoteNgPropertyRowKey") or "") == route.property_row_key]
    if len(route_rows) != 1:
        errors.append("mremoteng live GUI inheritance route must expose one inherited property row")
    else:
        route_row = route_rows[0]
        for property_name, expected_value in common_route_props.items():
            actual_value = str(route_row.property(property_name) or "")
            if actual_value != expected_value:
                errors.append(f"mremoteng live GUI inheritance property-row property {property_name} drifted")
        if str(route_row.property("mRemoteNgPropertyInherited") or "") != "true":
            errors.append("mremoteng live GUI inheritance property row must remain inherited")

    routed_cells = [
        cell
        for cell in property_grid.findChildren(QLabel, route.property_cell_object)
        if str(cell.property("mRemoteNgPropertyRowKey") or "") == route.property_row_key
    ]
    cells_by_column = {str(cell.property("mRemoteNgPropertyColumnKey") or ""): cell for cell in routed_cells}
    for column_key, expected_value in {
        "property": route.inherited_property_label,
        "effective": route.inherited_value,
        "source": route.inherited_source,
    }.items():
        cell = cells_by_column.get(column_key)
        if cell is None:
            errors.append(f"mremoteng live GUI inheritance route missing {column_key!r} cell")
            continue
        if str(cell.property("mRemoteNgPropertyCellValue") or "") != expected_value:
            errors.append(f"mremoteng live GUI inheritance route {column_key!r} cell value drifted")
        for property_name, expected_route_value in common_route_props.items():
            actual_value = str(cell.property(property_name) or "")
            if actual_value != expected_route_value:
                errors.append(f"mremoteng live GUI inheritance cell property {property_name} drifted")

    if route.active_tab_label not in live_tab_labels(tabs):
        errors.append(f"mremoteng live GUI inheritance route missing active tab {route.active_tab_label!r}")
    return errors


def live_contract_checks_for_preset(preset_id: str) -> list[str]:
    checks = [
        "required-widget-visibility",
        "preset-catalog-route",
        "preset-isolation-route",
        "preset-selection-route",
        "preset-transition-route",
        "preset-visual-signature",
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
    if preset_id in EXPECTED_PRESET_REFERENCE_TAB_ROUTES:
        checks.append("reference-tab-activation-route")
    if preset_id in EXPECTED_PRESET_REFERENCE_TAB_CHROME_ROUTES:
        checks.append("reference-tab-chrome-evidence-route")
    if preset_id in EXPECTED_PRESET_REFERENCE_STATUS_BAR_ROUTES:
        checks.append("reference-status-bar-evidence-route")
    if preset_id in EXPECTED_PRESET_REFERENCE_SESSION_ACTION_ROUTES:
        checks.append("reference-session-actions-route")
    if preset_id in EXPECTED_PRESET_REFERENCE_SURFACE_ROUTES:
        checks.append("reference-surface-evidence-route")
    if preset_id in EXPECTED_PRESET_REFERENCE_CONTROL_ROUTES:
        checks.append("reference-control-evidence-route")
    if preset_id in EXPECTED_PRESET_REFERENCE_INPUT_ROUTES:
        checks.append("reference-input-evidence-route")
    if preset_id in EXPECTED_PRESET_REFERENCE_TRANSCRIPT_ROUTES:
        checks.append("reference-transcript-evidence-route")
    if preset_id in EXPECTED_PRESET_KEYBOARD_SHORTCUT_ROUTES:
        checks.append("preset-keyboard-shortcut-route")
    if preset_id in EXPECTED_PRESET_COMMAND_SURFACE_ROUTES:
        checks.append("preset-command-surface-route")
    if preset_id in EXPECTED_PRESET_FOCUS_INTERACTION_ROUTES:
        checks.append("preset-focus-interaction-route")
    if preset_id in EXPECTED_PRESET_HOME_SEARCH_ROUTES:
        checks.append("preset-home-search-route")
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
                "ribbon-edge-action-route",
                "generated-ribbon-icons",
                "moba-rail-roles",
                "moba-rail-labels",
                "moba-rail-geometry",
                "connected-tab-chrome",
                "connected-tab-geometry",
                "connected-session-actions-route",
                "connected-dock-frame",
                "session-edge-controls",
                "session-edge-geometry",
                "session-edge-action-route",
                "right-utility-rail",
                "right-utility-rail-chrome",
                "right-utility-rail-geometry",
                "right-utility-action-route",
                "connected-sftp-dock",
                "sftp-toolbar-groups",
                "sftp-toolbar-geometry",
                "sftp-toolbar-action-route",
                "sftp-file-row-icons",
                "sftp-routed-file-rows",
                "sftp-dock-density",
                "sftp-browser-chrome",
                "sftp-browser-geometry",
                "sftp-follow-folder-route",
                "sftp-terminal-folder-route",
                "sftp-dock-chrome",
                "remote-monitoring-dock",
                "remote-monitoring-footer-geometry",
                "monitoring-telemetry-route",
                "remote-monitoring-control-route",
                "follow-terminal-folder-control-route",
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
                "product-identity-route",
            ]
        )
        if preset_id == "securecrt":
            checks.append("securecrt-top-chrome")
            checks.append("securecrt-session-manager-chrome")
            checks.append("securecrt-session-manager-geometry")
            checks.append("securecrt-session-manager-route")
            checks.append("securecrt-session-manager-filter-route")
            checks.append("securecrt-sftp-tab-route")
            checks.append("securecrt-sftp-browser-route")
            checks.append("securecrt-sftp-browser-live-action-route")
            checks.append("securecrt-tree-icons")
            checks.append("securecrt-session-status-strip")
            checks.append("securecrt-session-status-geometry")
            checks.append("securecrt-command-window")
            checks.append("securecrt-command-window-geometry")
            checks.append("securecrt-command-window-send-route")
            checks.append("securecrt-command-window-live-send-route")
        if preset_id == "remmina":
            checks.append("remmina-tree-icons")
            checks.append("remmina-profile-list-chrome")
            checks.append("remmina-profile-list-geometry")
            checks.append("remmina-viewer-controls")
            checks.append("remmina-viewer-control-geometry")
            checks.append("remmina-profile-viewer-route")
            checks.append("remmina-profile-filter-route")
            checks.append("remmina-clipboard-route")
            checks.append("remmina-screenshot-route")
            checks.append("remmina-screenshot-live-capture-route")
            checks.append("remmina-sftp-transfer-route")
            checks.append("remmina-sftp-transfer-live-queue-route")
        if preset_id == "termius":
            checks.append("termius-tree-icons")
            checks.append("termius-hosts-chrome")
            checks.append("termius-header-chips")
            checks.append("termius-host-identity-strip")
            checks.append("termius-host-identity-geometry")
            checks.append("termius-host-selection-route")
            checks.append("termius-sync-route")
            checks.append("termius-port-forward-route")
            checks.append("termius-snippet-route")
            checks.append("termius-snippet-live-run-route")
            checks.append("termius-files-browser-route")
            checks.append("termius-files-browser-live-sync-route")
        if preset_id == "mremoteng":
            checks.append("mremoteng-tree-icons")
            checks.append("mremoteng-top-chrome")
            checks.append("mremoteng-document-controls")
            checks.append("mremoteng-document-control-geometry")
            checks.append("mremoteng-property-grid")
            checks.append("mremoteng-connection-document-route")
            checks.append("mremoteng-connection-reconnect-live-route")
            checks.append("mremoteng-document-filter-route")
            checks.append("mremoteng-inheritance-route")
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
        "expected_moba_ribbon_edge_action_route": (
            EXPECTED_MOBA_RIBBON_EDGE_ACTION_ROUTE.to_dict()
            if preset_id == "mobaxterm"
            else {}
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
        "expected_moba_connected_session_action_route": (
            EXPECTED_MOBA_CONNECTED_SESSION_ACTION_ROUTE.to_dict()
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
        "expected_moba_right_utility_action_route": (
            EXPECTED_MOBA_RIGHT_UTILITY_ACTION_ROUTE.to_dict()
            if preset_id == "mobaxterm"
            else {}
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
        "expected_moba_session_edge_action_route": (
            EXPECTED_MOBA_SESSION_EDGE_ACTION_ROUTE.to_dict()
            if preset_id == "mobaxterm"
            else {}
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
        "expected_moba_sftp_toolbar_action_route": (
            EXPECTED_MOBA_SFTP_TOOLBAR_ACTION_ROUTE.to_dict()
            if preset_id == "mobaxterm"
            else {}
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
        "expected_moba_remote_monitoring_control_route": (
            EXPECTED_MOBA_REMOTE_MONITORING_CONTROL_ROUTE.to_dict() if preset_id == "mobaxterm" else {}
        ),
        "expected_moba_follow_terminal_folder_control_route": (
            EXPECTED_MOBA_FOLLOW_TERMINAL_FOLDER_CONTROL_ROUTE.to_dict()
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
        "expected_moba_sftp_terminal_folder_route": (
            EXPECTED_MOBA_SFTP_TERMINAL_FOLDER_ROUTE.to_dict() if preset_id == "mobaxterm" else {}
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
        "expected_product_identity_route": (
            EXPECTED_PRODUCT_IDENTITY_ROUTES[preset_id].to_dict()
            if preset_id in EXPECTED_PRODUCT_IDENTITY_ROUTES
            else {}
        ),
        "expected_preset_reference_tab_route": (
            EXPECTED_PRESET_REFERENCE_TAB_ROUTES[preset_id].to_dict()
            if preset_id in EXPECTED_PRESET_REFERENCE_TAB_ROUTES
            else {}
        ),
        "expected_preset_reference_tab_chrome_route": (
            EXPECTED_PRESET_REFERENCE_TAB_CHROME_ROUTES[preset_id].to_dict()
            if preset_id in EXPECTED_PRESET_REFERENCE_TAB_CHROME_ROUTES
            else {}
        ),
        "expected_preset_reference_status_bar_route": (
            EXPECTED_PRESET_REFERENCE_STATUS_BAR_ROUTES[preset_id].to_dict()
            if preset_id in EXPECTED_PRESET_REFERENCE_STATUS_BAR_ROUTES
            else {}
        ),
        "expected_preset_reference_session_action_route": (
            EXPECTED_PRESET_REFERENCE_SESSION_ACTION_ROUTES[preset_id].to_dict()
            if preset_id in EXPECTED_PRESET_REFERENCE_SESSION_ACTION_ROUTES
            else {}
        ),
        "expected_preset_reference_surface_route": (
            EXPECTED_PRESET_REFERENCE_SURFACE_ROUTES[preset_id].to_dict()
            if preset_id in EXPECTED_PRESET_REFERENCE_SURFACE_ROUTES
            else {}
        ),
        "expected_preset_reference_control_route": (
            EXPECTED_PRESET_REFERENCE_CONTROL_ROUTES[preset_id].to_dict()
            if preset_id in EXPECTED_PRESET_REFERENCE_CONTROL_ROUTES
            else {}
        ),
        "expected_preset_reference_input_route": (
            EXPECTED_PRESET_REFERENCE_INPUT_ROUTES[preset_id].to_dict()
            if preset_id in EXPECTED_PRESET_REFERENCE_INPUT_ROUTES
            else {}
        ),
        "expected_preset_reference_transcript_route": (
            EXPECTED_PRESET_REFERENCE_TRANSCRIPT_ROUTES[preset_id].to_dict()
            if preset_id in EXPECTED_PRESET_REFERENCE_TRANSCRIPT_ROUTES
            else {}
        ),
        "expected_preset_keyboard_shortcut_route": (
            EXPECTED_PRESET_KEYBOARD_SHORTCUT_ROUTES[preset_id].to_dict()
            if preset_id in EXPECTED_PRESET_KEYBOARD_SHORTCUT_ROUTES
            else {}
        ),
        "expected_preset_command_surface_route": (
            EXPECTED_PRESET_COMMAND_SURFACE_ROUTES[preset_id].to_dict()
            if preset_id in EXPECTED_PRESET_COMMAND_SURFACE_ROUTES
            else {}
        ),
        "expected_preset_focus_interaction_route": (
            EXPECTED_PRESET_FOCUS_INTERACTION_ROUTES[preset_id].to_dict()
            if preset_id in EXPECTED_PRESET_FOCUS_INTERACTION_ROUTES
            else {}
        ),
        "expected_preset_home_search_route": (
            EXPECTED_PRESET_HOME_SEARCH_ROUTES[preset_id].to_dict()
            if preset_id in EXPECTED_PRESET_HOME_SEARCH_ROUTES
            else {}
        ),
        "expected_preset_catalog_route": EXPECTED_PRESET_CATALOG_ROUTE.to_dict(),
        "expected_preset_isolation_route": EXPECTED_PRESET_ISOLATION_ROUTES[preset_id].to_dict(),
        "expected_preset_selection_route": EXPECTED_PRESET_SELECTION_ROUTES[preset_id].to_dict(),
        "expected_preset_transition_route": EXPECTED_PRESET_TRANSITION_ROUTES[preset_id].to_dict(),
        "expected_preset_visual_signature": EXPECTED_PRESET_VISUAL_SIGNATURES[preset_id].to_dict(),
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
        "expected_securecrt_session_manager_filter_route": (
            EXPECTED_SECURECRT_SESSION_MANAGER_FILTER_ROUTE.to_dict()
            if preset_id == "securecrt"
            else {}
        ),
        "expected_securecrt_sftp_tab_route": (
            EXPECTED_SECURECRT_SFTP_TAB_ROUTE.to_dict()
            if preset_id == "securecrt"
            else {}
        ),
        "expected_securecrt_sftp_browser_route": (
            EXPECTED_SECURECRT_SFTP_BROWSER_ROUTE.to_dict()
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
                "captured_property": EXPECTED_SECURECRT_COMMAND_WINDOW_SEND_ROUTE.captured_property,
                "captured_command_property": (
                    EXPECTED_SECURECRT_COMMAND_WINDOW_SEND_ROUTE.captured_command_property
                ),
                "captured_target_scope_property": (
                    EXPECTED_SECURECRT_COMMAND_WINDOW_SEND_ROUTE.captured_target_scope_property
                ),
                "captured_status_property": EXPECTED_SECURECRT_COMMAND_WINDOW_SEND_ROUTE.captured_status_property,
                "signal": EXPECTED_SECURECRT_COMMAND_WINDOW_SEND_ROUTE.signal,
                "secondary_signal": EXPECTED_SECURECRT_COMMAND_WINDOW_SEND_ROUTE.secondary_signal,
                "handler": EXPECTED_SECURECRT_COMMAND_WINDOW_SEND_ROUTE.handler,
                "signal_property": EXPECTED_SECURECRT_COMMAND_WINDOW_SEND_ROUTE.signal_property,
                "secondary_signal_property": (
                    EXPECTED_SECURECRT_COMMAND_WINDOW_SEND_ROUTE.secondary_signal_property
                ),
                "handler_property": EXPECTED_SECURECRT_COMMAND_WINDOW_SEND_ROUTE.handler_property,
                "live_submitted_property": EXPECTED_SECURECRT_COMMAND_WINDOW_SEND_ROUTE.live_submitted_property,
                "live_command_property": EXPECTED_SECURECRT_COMMAND_WINDOW_SEND_ROUTE.live_command_property,
                "live_target_scope_property": (
                    EXPECTED_SECURECRT_COMMAND_WINDOW_SEND_ROUTE.live_target_scope_property
                ),
                "live_status_property": EXPECTED_SECURECRT_COMMAND_WINDOW_SEND_ROUTE.live_status_property,
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
        "expected_remmina_profile_filter_route": (
            EXPECTED_REMMINA_PROFILE_FILTER_ROUTE.to_dict()
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
        "expected_remmina_screenshot_route": (
            EXPECTED_REMMINA_SCREENSHOT_ROUTE.to_dict()
            if preset_id == "remmina"
            else {}
        ),
        "expected_remmina_sftp_transfer_route": (
            EXPECTED_REMMINA_SFTP_TRANSFER_ROUTE.to_dict()
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
        "expected_termius_port_forward_route": (
            EXPECTED_TERMIUS_PORT_FORWARD_ROUTE.to_dict()
            if preset_id == "termius"
            else {}
        ),
        "expected_termius_snippet_route": (
            EXPECTED_TERMIUS_SNIPPET_ROUTE.to_dict()
            if preset_id == "termius"
            else {}
        ),
        "expected_termius_files_browser_route": (
            EXPECTED_TERMIUS_FILES_BROWSER_ROUTE.to_dict()
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
            EXPECTED_MREMOTENG_CONNECTION_DOCUMENT_ROUTE.to_dict()
            if preset_id == "mremoteng"
            else {}
        ),
        "expected_mremoteng_document_filter_route": (
            EXPECTED_MREMOTENG_DOCUMENT_FILTER_ROUTE.to_dict()
            if preset_id == "mremoteng"
            else {}
        ),
        "expected_mremoteng_inheritance_route": (
            EXPECTED_MREMOTENG_INHERITANCE_ROUTE.to_dict()
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
    buttons_by_key: dict[str, Any] = {}
    for button in window.findChildren(QToolButton):
        for property_name in ("productToolbarKey", "mobaIconKey", "mobaRailRole"):
            key = str(button.property(property_name) or "")
            if key:
                buttons_by_key[key] = button
    for key, expected_state in [
        (state.active_toolbar_key, "active"),
        (state.checked_toolbar_key, "checked"),
        (state.disabled_toolbar_key, "disabled"),
    ]:
        if not key:
            continue
        label = interaction_label_for_key(preset_id, key)
        button = buttons_by_key.get(key) or buttons.get(label)
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
        state.active_tab_status in live_tab_plain_tooltip(tabs, index)
        for index in range(tabs.count())
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
        matches = window.findChildren(QWidget, object_name)
        visible_matches = [widget for widget in matches if widget.isVisible()]
        widget = visible_matches[0] if visible_matches else (matches[0] if matches else None)
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
    if metrics.width > REQUESTED_SIZE[0] or metrics.height > REQUESTED_SIZE[1]:
        errors.append(
            f"{preset_id} live GUI capture dimensions {(metrics.width, metrics.height)} "
            f"must not exceed requested size {REQUESTED_SIZE}"
        )
    if metrics.distinct_colors < MIN_DISTINCT_COLORS:
        errors.append(
            f"{preset_id} live GUI capture has too few sampled colors: {metrics.distinct_colors}"
        )
    if metrics.luminance_range < MIN_LUMINANCE_RANGE:
        errors.append(
            f"{preset_id} live GUI capture luminance range is too small: {metrics.luminance_range}"
        )
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
        "capture_mode": capture_mode_for_captures(captures),
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


def capture_mode_for_captures(captures: list[CaptureResult]) -> str:
    evidence_platforms = {
        capture.font_render_evidence.platform_name
        for capture in captures
        if capture.font_render_evidence is not None
    }
    if len(evidence_platforms) == 1:
        platform_name = next(iter(evidence_platforms))
    else:
        platform_name = os.environ.get("QT_QPA_PLATFORM", default_qt_platform())
    return f"live-pyqt6-{platform_name.lower()}"


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

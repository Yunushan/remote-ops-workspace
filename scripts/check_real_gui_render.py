Warning: truncated output (original token count: 172068)
Total output lines: 12472

from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
import time
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
from remote_ops_workspace.terminal import TerminalPanePlan  # noqa: E402

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
    preview_sample_data=False,
)
EXPECTED_MOBA_CONNECTED_SESSION_ROUTE = moba_connected_session_route(EXPECTED_MOBA_CONNECTED_STATE)
EXPECTED_MOBA_CONNECTED_SESSION_IDENTITY_ROUTE = moba_connected_session_identity_route(EXPECTED_MOBA_CONNECTED_STATE)
EXPECTED_MOBA_CONNECTED_SESSION_ACTION_ROUTE = moba_connected_session_action_route(EXPECTED_MOBA_CONNECTED_STATE)
EXPECTED_MOBA_SFTP_TERMINAL_FOLDER_ROUTE = moba_sftp_terminal_folder_route(EXPECTED_MOBA_CONNECTED_STATE)
EXPECTED_MOBA_TERMINAL_TRANSCRIPT = EXPECTED_MOBA_CONNECTED_STATE.terminal_transcript
EXPECTED_MOBA_TERMINAL_TRANSCRIPT_KEYS = [line.key for line in EXPECTED_MOBA_TERMINAL_TRANSCRIPT]
EXPECTED_MOBA_TERMINAL_TRANSCRIPT_TONES = [line.tone for line in EXPECTED_MOBA_TERMINAL_TRANSCRIPT]
EXPECTED_MOBA_TERMINAL_TRANSCRIPT_ROW_GEOMETRY: tuple[Any, ...] = ()
EXPECTED_MOBA_TERMINAL_TRANSCRIPT_ROW_GEOMETRY_KEYS: list[str] = []
EXPECTED_MOBA_TELEMETRY_CELLS = moba_telemetry_cells(EXPECTED_MOBA_CONNECTED_STATE)
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
    "terminalPane": "Moba native terminal pane",
    "terminalOutput": "Moba native terminal output",
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
            "id": "native-terminal-workspace",
            "object_name": "terminalOutput",
            "label": "Moba native terminal workspace",
            "min_width": 420,
            "min_height": 300,
            "min_x": 300,
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
            "id": "dock-left-of-native-terminal",
            "from": "mobaConnectedLeftDock",
            "relation": "left_of",
            "to": "terminalOutput",
            "max_gap": 160,
        },
        {
            "id": "sftp-table-inside-dock",
            "from": "mobaSftpFileTable",
            "relation": "inside",
            "to": "mobaConnectedLeftDock",
        },
        {
            "id": "native-terminal-above-telemetry",
            "from": "terminalOutput",
            "relation": "above",
            "to": "mobaTelemetryBar",
            "max_gap": 40,
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
            "id": "workspace-surface-above-workflow",
            "from": "productWorkspaceSurface",
            "relation": "above",
            "to": "productWorkflowEvidence",
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
            "id": "workspace-surface-above-workflow",
            "from": "productWorkspaceSurface",
            "relation": "above",
            "to": "productWorkflowEvidence",
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
            "id": "workspace-surface-above-workflow",
            "from": "productWorkspaceSurface",
            "relation": "above",
            "to": "productWorkflowEvidence",
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
    if (scale_factor := effective_qt_scale_factor(old_scale_factor)) is not None:
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


def effective_qt_scale_factor(
    explicit_scale_factor: str | None,
    platform: str | None = None,
) -> str | None:
    """Preserve an explicit DPI test leg while retaining deterministic defaults."""

    if explicit_scale_factor is not None:
        return explicit_scale_factor
    return default_qt_scale_factor(platform)


def logical_capture_size(width: int, height: int, device_pixel_ratio: float) -> tuple[int, int]:
    """Return logical screenshot dimensions for a Qt high-DPI pixmap."""

    if device_pixel_ratio <= 0:
        return width, height
    return round(width / device_pixel_ratio), round(height / device_pixel_ratio)


def normalize_capture_pixmap(pixmap: Any) -> Any:
    """Downsample high-DPI grabs so metrics and artifacts use logical window pixels."""

    device_pixel_ratio = float(pixmap.devicePixelRatio())
    width, height = logical_capture_size(pixmap.width(), pixmap.height(), device_pixel_ratio)
    if (width, height) == (pixmap.width(), pixmap.height()):
        return pixmap

    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QPixmap

    image = pixmap.toImage().scaled(
        width,
        height,
        Qt.AspectRatioMode.IgnoreAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )
    return QPixmap.fromImage(image)


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

            # Capture the connected product document rather than the generic
            # welcome card.  prepare_product_reference_tab intentionally
            # returns home so route contracts can verify the recovery path;
            # temporarily selecting the reference tab here makes the evidence
            # image represent the actual SecureCRT/Termius/Remmina/mRemoteNG
            # connected workspace users see after opening a session.
            capture_index = -1
            reference_route = EXPECTED_PRESET_REFERENCE_TAB_ROUTES.get(preset.id)
            if reference_route is not None:
                capture_index = find_live_tab_index(window.tabs, reference_route.active_tab_label)
                if capture_index >= 0:
                    window.tabs.setCurrentIndex(capture_index)
                    process_events(app)
                    if window.tabs.currentIndex() != capture_index:
                        errors.append(
                            f"{preset.id} live GUI could not select connected capture tab: "
                            f"expected {capture_index}, got {window.tabs.currentIndex()}"
                        )
            pixmap = normalize_capture_pixmap(window.grab())
            if capture_index >= 0 and reference_route is not None:
                home_index = window.find_tab_by_role(reference_route.home_tab_role)
                if home_index >= 0:
                    window.tabs.setCurrentIndex(home_index)
                    window.tabs.setProperty(reference_route.home_tab_property, reference_route.home_tab_label)
                    window.tabs.setProperty(reference_route.returned_home_label_property, reference_route.home_tab_label)
                    process_events(app)
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


def expected_moba_monitoring_checked(background_auth_available: bool) -> bool:
    return bool(
        background_auth_available
        and EXPECTED_MOBA_REMOTE_MONITORING_CONTROL_ROUTE.expected_checked
    )


def prepare_preset_live_state(window: Any, preset_id: str) -> list[str]:
    if preset_id == "native":
        state = gui_design_interaction_state(preset_id)
        if not hasattr(window, "select_profile_tree_label"):
            return ["native live GUI cannot select its reference profile tree row"]
        if not window.select_profile_tree_label(state.selected_tree_label):
            return [
                "native live GUI could not select reference profile tree row: "
                f"{state.selected_tree_label}"
            ]
        return []
    if preset_id != "mobaxterm":
        return prepare_product_reference_tab(window, preset_id)
    return prepare_moba_connected_reference(window)


def prepare_moba_connected_reference(window: Any) -> list[str]:
    try:
        profile = window.store.get(PRESET_REFERENCE_PROFILES["mobaxterm"])
        profile_data = profile.to_dict()
        profile_options = dict(profile_data.get("options") or {})
        profile_options.pop("moba_monitoring_output", None)
        profile_data["options"] = profile_options
        profile = Profile.from_dict(profile_data)
        # The render gate must not race DNS or an unavailable SSH endpoint.
        # Keep a real local transport alive so focus and runtime output are
        # measured deterministically without fabricating remote SSH output.
        transport_harness = (
            "import sys\n"
            "print('REFERENCE TRANSPORT READY', flush=True)\n"
            "for line in sys.stdin:\n"
            "    print(line, end='', flush=True)\n"
        )
        window.open_moba_connected_session_tab(
            profile,
            TerminalPanePlan(
                title=profile.name,
                command=[
                    sys.executable,
                    "-u",
                    "-c",
                    transport_harness,
                ],
                source="real-gui-render-local-transport",
            ),
            remote_path="/var/log",
            tab_status="CI CONNECTED",
        )
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
        # open_terminal_tab deliberately defers process startup until the
        # connected tab has a parent and stable geometry.  Settle that queued
        # transition before capturing evidence; otherwise the contract sees
        # the pre-start "No running process panes" state and an empty
        # transcript even though the user-facing tab starts correctly.
        settle_live_reference_runtime(window, preset_id)
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


def settle_live_reference_runtime(window: Any, preset_id: str, *, timeout_seconds: float = 1.5) -> None:
    """Drain the deferred tab-start path before collecting live evidence.

    Reference tabs use a real child process, but startup is queued until Qt
    has laid out the selected page. A bounded event-loop wait keeps this gate
    deterministic while allowing both the process-start signal and the
    coalesced output timer to run on Windows and offscreen Qt.
    """

    from PyQt6.QtWidgets import QApplication, QTabWidget, QWidget

    route = EXPECTED_PRESET_REFERENCE_TAB_ROUTES.get(preset_id)
    if route is None:
        return
    tabs = window.findChild(QTabWidget, "sessionTabs")
    if tabs is None:
        return
    reference_index = find_live_tab_index(tabs, route.active_tab_label)
    if reference_index < 0:
        return
    reference_widget = tabs.widget(reference_index)
    if reference_widget is None:
        return
    pane = reference_widget
    if str(pane.objectName()) != "terminalPane":
        pane = reference_widget.findChild(QWidget, "terminalPane")
    if pane is None:
        return

    app = QApplication.instance()
    if app is None:
        return
    expected_fragment = ""
    surface_route = EXPECTED_PRESET_REFERENCE_SURFACE_ROUTES.get(preset_id)
    if surface_route is not None:
        expected_fragment = surface_route.command_target_fragment
    deadline = time.monotonic() + timeout_seconds
    while time.monotonic() < deadline:
        process_events(app)
        flush = getattr(pane, "flush_process_output_now", None)
        if callable(flush):
            flush()
        output = getattr(pane, "output", None)
        transcript = output.toPlainText() if output is not None else ""
        command = getattr(getattr(pane, "plan", None), "printable", lambda: "")()
        if command and command in transcript and (
            not expected_fragment or expected_fragment in transcript
        ):
            break
        time.sleep(0.01)
    process_events(app)
    flush = getattr(pane, "flush_process_output_now", None)
    if callable(flush):
        flush()


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
    from PyQt6.QtGui import QFont
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
        background_auth_value = (
            connected_dock.property("mobaBackgroundSshAuthAvailable")
            if connected_dock is not None
            else None
        )
        if background_auth_value is None:
            errors.append("mobaxterm live GUI background SSH auth capability is missing")
        background_auth_available = bool(background_auth_value)
        expected_monitoring_checked = expected_moba_monitoring_checked(
            background_auth_available
        )
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
        if EXPECTED_MOBA_RAIL_CHROME.label_font_size != 12:
            errors.append("mobaxterm live GUI rail crisp font size must be 12 pixels")
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
            if label.font().pixelSize() != 12:
                errors.append(f"mobaxterm live GUI rail label {role!r} must render at 12 pixels")
            if label.font().hintingPreference() != QFont.HintingPreference.PreferFullHinting:
                errors.append(f"mobaxterm live GUI rail label {role!r} must use full font hinting")
            if str(label.property("mobaRailTextRenderMode") or "") != "device-pixel-pixmap":
                errors.append(
                    f"mobaxterm live GUI rail label {role!r} must use device-pixel-pixmap rendering"
                )
            try:
                rendered_dpr = float(label.property("mobaRailTextDevicePixelRatio"))
            except (TypeError, ValueError):
                rendered_dpr = 0.0
            if abs(rendered_dpr - float(label.devicePixelRatioF())) > 0.001:
                errors.append(
                    f"mobaxterm live GUI rail label {role!r} device-pixel ratio drifted"
                )
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
        transfer_button = window.findChild(QToolButton, "mobaSftpTransferMenu")
        if transfer_button is None:
            errors.append("mobaxterm live GUI SFTP transfer selector is missing")
        else:
            if transfer_button.text() != "Transfer":
                errors.append("mobaxterm live GUI SFTP transfer selector label drifted")
            if transfer_button.menu() is None:
                errors.append("mobaxterm live GUI SFTP transfer selector menu is missing")
            else:
                transfer_labels = {
                    action.text() for action in transfer_button.menu().actions() if not action.isSeparator…112068 tokens truncated…   if str(cell.property("mRemoteNgPropertyCellFullText") or "") != full_text:
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
                "remote-monitoring-compact",
                "monitoring-telemetry-route",
                "remote-monitoring-control-route",
                "follow-terminal-folder-control-route",
                "moba-monitoring-controls",
                "moba-monitoring-control-geometry",
                "terminal-runtime-output",
                "truthful-terminal-preamble",
                "native-pty-input-visibility",
                "terminal-context-menu",
                "telemetry-context-menu",
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
        "expected_moba_right_utility_keys": [],
        "expected_moba_right_utility_rail_chrome": {},
        "expected_moba_right_utility_actions": [],
        "expected_moba_right_utility_action_route": {},
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
        "expected_moba_ssh_banner_chrome": {},
        "expected_moba_ssh_banner_row_geometry": [],
        "expected_moba_ssh_banner_capability_card": {},
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
        "expected_preset_isolation_route": live_preset_isolation_route_dict(preset_id),
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

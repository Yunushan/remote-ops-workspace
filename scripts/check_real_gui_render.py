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
    gui_design_moba_monitoring_controls,
    gui_design_moba_monitoring_metrics,
    gui_design_moba_rail_items,
    gui_design_moba_ribbon_actions,
    gui_design_moba_right_utility_actions,
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
    gui_design_reference_state,
    gui_design_remmina_profile_list_chrome,
    gui_design_remmina_viewer_controls,
    gui_design_securecrt_command_window_chrome,
    gui_design_securecrt_session_status_strip,
    gui_design_sidebar_copy,
    gui_design_status_segments,
    gui_design_termius_header_chips,
    gui_design_termius_host_identity_strip,
    gui_design_toolbar_actions,
    gui_design_workflow_cards,
    gui_design_workspace_surface,
)
from remote_ops_workspace.launcher import LauncherError  # noqa: E402
from remote_ops_workspace.moba_connected import (  # noqa: E402
    build_moba_connected_session_state,
    build_moba_terminal_transcript,
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
EXPECTED_MOBA_TITLEBAR_CHROME = gui_design_moba_titlebar_chrome()
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
EXPECTED_MOBA_TAB_CHROME_KEYS = {"home", "active-session", "new-session"}
EXPECTED_MOBA_STATIC_TAB_CHROME_KEYS = {"home", "inactive-session", "active-session", "new-session"}
EXPECTED_MOBA_RIGHT_UTILITY_KEYS = {action.key for action in gui_design_moba_right_utility_actions()}
EXPECTED_MOBA_RIGHT_UTILITY_ICON_KEYS = {action.key: action.icon_key for action in gui_design_moba_right_utility_actions()}
EXPECTED_MOBA_SSH_BANNER_CHROME = gui_design_moba_ssh_banner_chrome()
EXPECTED_MOBA_SFTP_BROWSER_CHROME = gui_design_moba_sftp_browser_chrome()
EXPECTED_MOBA_SFTP_DOCK_LAYOUT = gui_design_moba_sftp_dock_layout()
EXPECTED_MOBA_SFTP_COLUMN_KEYS = [column.key for column in EXPECTED_MOBA_SFTP_BROWSER_CHROME.columns]
EXPECTED_MOBA_SFTP_COLUMN_LABELS = [column.label for column in EXPECTED_MOBA_SFTP_BROWSER_CHROME.columns]
EXPECTED_MOBA_SFTP_ACTIONS = tuple(gui_design_moba_sftp_dock_actions())
EXPECTED_MOBA_SFTP_ACTION_KEYS = {action.key for action in EXPECTED_MOBA_SFTP_ACTIONS}
EXPECTED_MOBA_SFTP_SEPARATOR_AFTER_KEYS = [action.key for action in EXPECTED_MOBA_SFTP_ACTIONS if action.separator_after]
EXPECTED_MOBA_MONITORING_METRIC_KEYS = {metric.key for metric in gui_design_moba_monitoring_metrics()}
EXPECTED_MOBA_MONITORING_CONTROLS = tuple(gui_design_moba_monitoring_controls())
EXPECTED_MOBA_MONITORING_CONTROL_KEYS = {control.key for control in EXPECTED_MOBA_MONITORING_CONTROLS}
EXPECTED_MOBA_STATUS_KEYS = {segment.key for segment in gui_design_moba_status_segments()}
EXPECTED_MOBA_STATUS_CHROME = gui_design_moba_status_bar_chrome()
EXPECTED_SECURECRT_COMMAND_WINDOW_CHROME = gui_design_securecrt_command_window_chrome()
EXPECTED_SECURECRT_SESSION_STATUS_STRIP = gui_design_securecrt_session_status_strip()
EXPECTED_SECURECRT_SESSION_STATUS_KEYS = [field.key for field in EXPECTED_SECURECRT_SESSION_STATUS_STRIP.fields]
EXPECTED_REMMINA_VIEWER_CONTROL_KEYS = [control.key for control in gui_design_remmina_viewer_controls()]
EXPECTED_REMMINA_PROFILE_LIST_CHROME = gui_design_remmina_profile_list_chrome()
EXPECTED_REMMINA_PROFILE_COLUMN_KEYS = [column.key for column in EXPECTED_REMMINA_PROFILE_LIST_CHROME.columns]
EXPECTED_REMMINA_PROFILE_ROW_KEYS = [row.key for row in EXPECTED_REMMINA_PROFILE_LIST_CHROME.rows]
EXPECTED_TERMIUS_HEADER_CHIP_KEYS = [chip.key for chip in gui_design_termius_header_chips()]
EXPECTED_TERMIUS_HOST_IDENTITY_STRIP = gui_design_termius_host_identity_strip()
EXPECTED_TERMIUS_HOST_IDENTITY_KEYS = [field.key for field in EXPECTED_TERMIUS_HOST_IDENTITY_STRIP.fields]
EXPECTED_MREMOTENG_DOCUMENT_CONTROL_KEYS = [control.key for control in gui_design_mremoteng_document_controls()]
EXPECTED_MREMOTENG_DOCUMENT_TOOLBAR_CHROME = gui_design_mremoteng_document_toolbar_chrome()
EXPECTED_MREMOTENG_PROPERTY_GRID_CHROME = gui_design_mremoteng_property_grid_chrome()
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
    "mobaRightUtilityRail": "Moba right terminal utility rail",
    "mobaTelemetryBar": "Moba bottom telemetry bar",
}
NON_MOBA_REQUIRED_WIDGETS = {
    "layoutToolbar": "layout toolbar",
    "activityLog": "activity log",
}
SECURECRT_REQUIRED_WIDGETS = {
    "secureCrtSessionStatusStrip": "SecureCRT session status strip",
}
TERMIUS_REQUIRED_WIDGETS = {
    "termiusHostIdentityStrip": "Termius host identity strip",
}
REMMINA_REQUIRED_WIDGETS = {
    "remminaProfileListChrome": "Remmina profile list chrome",
}
MREMOTENG_REQUIRED_WIDGETS = {
    "mRemoteNgPropertyGrid": "mRemoteNG property inheritance grid",
}
NON_MOBA_PRESENT_WIDGETS = {
    "designSelect": "view preset selector",
    "toolbarSearch": "toolbar search",
}
PRODUCT_STYLE_PRESETS = {"mobaxterm", "securecrt", "termius", "remmina", "mremoteng"}
EXPECTED_MOBA_RAIL_ROLES = {"collapse", "sessions", "favorites", "tools", "macros", "sftp"}
EXPECTED_MOBA_RAIL_LABELS = {item.role: item.label for item in gui_design_moba_rail_items() if item.label}
MOBA_REQUIRED_WIDGETS = {
    "quickConnect": "Moba quick connect field",
    "mobaRail": "Moba side rail",
    "mobaRibbonButton": "Moba ribbon action",
    "mobaXServerAction": "Moba X server action",
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
            "object_name": "quickConnect",
            "label": "Moba quick connect top strip",
            "min_width": 240,
            "max_y": 150,
            "max_x": 90,
        },
        {
            "id": "rail-left-edge",
            "object_name": "mobaRail",
            "label": "Moba narrow vertical rail",
            "max_width": 90,
            "min_height": 280,
            "max_x": 90,
        },
        {
            "id": "connected-left-dock",
            "object_name": "mobaConnectedLeftDock",
            "label": "Moba connected SFTP/monitoring dock",
            "min_width": 240,
            "max_width": 520,
            "min_height": 330,
            "max_x": 110,
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
            "id": "bottom-telemetry",
            "object_name": "mobaTelemetryBar",
            "label": "Moba bottom telemetry strip",
            "min_width": 420,
            "max_height": 90,
            "min_x": 300,
        },
    ],
    "securecrt": [
        {"id": "session-manager-width", "object_name": "leftPanel", "label": "Session Manager sidebar", "min_width": 220, "max_width": 360, "max_x": 90},
        {"id": "terminal-tabs-workspace", "object_name": "sessionTabs", "label": "SecureCRT terminal tabs", "min_width": 620, "min_height": 360, "min_x": 220},
        {"id": "command-log-bottom", "object_name": "activityLog", "label": "SecureCRT session log", "min_width": 620, "min_height": 70},
        {"id": "workflow-evidence", "object_name": "productWorkflowEvidence", "label": "SecureCRT workflow evidence cards", "min_width": 400, "min_height": 35},
        {"id": "session-status-strip", "object_name": "secureCrtSessionStatusStrip", "label": "SecureCRT session status strip", "min_width": 520, "min_height": 24, "min_x": 220},
        {"id": "toolbar-search", "object_name": "toolbarSearch", "label": "SecureCRT toolbar search", "min_width": 100, "max_y": 130},
    ],
    "termius": [
        {"id": "hosts-sidebar-width", "object_name": "leftPanel", "label": "Termius Hosts sidebar", "min_width": 230, "max_width": 380, "max_x": 90},
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
        {"id": "toolbar-search", "object_name": "toolbarSearch", "label": "mRemoteNG tree filter/search", "min_width": 100, "max_y": 130},
    ],
}
LIVE_TOPOLOGY_CONTRACTS: dict[str, list[dict[str, object]]] = {
    "mobaxterm": [
        {"id": "quick-connect-above-dock", "from": "quickConnect", "relation": "above", "to": "mobaConnectedLeftDock", "max_gap": 90},
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
    from PyQt6.QtWidgets import (
        QCheckBox,
        QFrame,
        QLabel,
        QLineEdit,
        QTabWidget,
        QTextEdit,
        QToolButton,
        QTreeWidget,
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
        quick_connect = window.findChild(QLineEdit, "quickConnect")
        if quick_connect is None or not quick_connect.isVisible():
            errors.append("mobaxterm live GUI quick connect field must be visible")
        top_menu_actions = window.menuBar().actions()
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
        moba_buttons = {button.text(): button for button in window.findChildren(QToolButton)}
        for label in ["Session", "Servers", "Tools", "Sessions", "Tunneling"]:
            if label not in moba_buttons:
                errors.append(f"mobaxterm live GUI ribbon missing action label: {label}")
        expected_icons = {action.label: action.icon_key for action in gui_design_moba_ribbon_actions()}
        expected_icons.update({"X server": "xserver", "Exit": "exit"})
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
        rail_labels = {
            str(label.property("mobaRailRole") or ""): label.text()
            for label in window.findChildren(QLabel, "mobaRailLabel")
        }
        for role, expected_label in EXPECTED_MOBA_RAIL_LABELS.items():
            if rail_labels.get(role) != expected_label:
                errors.append(f"mobaxterm live GUI rail role {role!r} missing vertical label: {expected_label}")
        sftp_buttons = window.findChildren(QToolButton, "mobaSftpAction")
        sftp_action_keys = {str(button.property("mobaSftpActionKey") or "") for button in sftp_buttons}
        missing_sftp_actions = sorted(EXPECTED_MOBA_SFTP_ACTION_KEYS - sftp_action_keys)
        if missing_sftp_actions:
            errors.append(f"mobaxterm live GUI SFTP dock missing action keys: {missing_sftp_actions}")
        for button in sftp_buttons:
            key = str(button.property("mobaSftpActionKey") or "")
            icon_key = str(button.property("mobaSftpIconKey") or "")
            expected_action = next((action for action in EXPECTED_MOBA_SFTP_ACTIONS if action.key == key), None)
            if key in EXPECTED_MOBA_SFTP_ACTION_KEYS and not icon_key:
                errors.append(f"mobaxterm live GUI SFTP action {key!r} missing icon key")
            if expected_action is not None:
                group_key = str(button.property("mobaSftpActionGroupKey") or "")
                separator_after = bool(button.property("mobaSftpActionSeparatorAfter"))
                if group_key != expected_action.group_key:
                    errors.append(f"mobaxterm live GUI SFTP action {key!r} group key drifted")
                if separator_after != expected_action.separator_after:
                    errors.append(f"mobaxterm live GUI SFTP action {key!r} separator flag drifted")
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
            if int(sftp_table.property("mobaSftpHeaderHeight") or 0) != EXPECTED_MOBA_SFTP_DOCK_LAYOUT.table_header_height:
                errors.append("mobaxterm live GUI SFTP file table header height metadata drifted")
            if int(sftp_table.property("mobaSftpRowHeight") or 0) != EXPECTED_MOBA_SFTP_DOCK_LAYOUT.file_row_height:
                errors.append("mobaxterm live GUI SFTP file row height metadata drifted")
            if sftp_table.topLevelItemCount() < 4:
                errors.append("mobaxterm live GUI SFTP file table must expose multiple reference rows")
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
        monitoring_labels = window.findChildren(QLabel, "mobaMonitoringMetric")
        monitoring_keys = {str(label.property("mobaMonitoringMetricKey") or "") for label in monitoring_labels}
        missing_monitoring_keys = sorted(EXPECTED_MOBA_MONITORING_METRIC_KEYS - monitoring_keys)
        if missing_monitoring_keys:
            errors.append(f"mobaxterm live GUI monitoring dock missing metric keys: {missing_monitoring_keys}")
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
        terminal_output = window.findChild(QTextEdit, "terminalOutput")
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
        telemetry_labels = window.findChildren(QLabel, "mobaTelemetryItem")
        telemetry_icons = window.findChildren(QLabel, "mobaTelemetryIcon")
        telemetry_cells = window.findChildren(QFrame, "mobaTelemetryCell")
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
        labels_by_key = {str(label.property("mobaTelemetryKey") or ""): label for label in telemetry_labels}
        for expected_cell in EXPECTED_MOBA_TELEMETRY_CELLS:
            live_cell = cell_by_key.get(expected_cell.key)
            live_label = labels_by_key.get(expected_cell.key)
            if live_cell is None or live_label is None:
                continue
            if str(live_cell.property("mobaTelemetryIconKey") or "") != expected_cell.icon_key:
                errors.append(f"mobaxterm live GUI telemetry cell {expected_cell.key!r} icon key drifted")
            if str(live_cell.property("mobaTelemetryDisplayText") or "") != expected_cell.display_text:
                errors.append(f"mobaxterm live GUI telemetry cell {expected_cell.key!r} display text drifted")
            if live_label.text() != expected_cell.display_text:
                errors.append(f"mobaxterm live GUI telemetry label {expected_cell.key!r} text drifted")
        tab_chrome: dict[str, tuple[str, bool]] = {}
        for index in range(tabs.count()):
            widget = tabs.widget(index)
            if widget is None:
                continue
            chrome_key = str(widget.property("mobaTabChromeKey") or "")
            if not chrome_key:
                continue
            tab_chrome[chrome_key] = (
                str(widget.property("mobaTabIconKey") or ""),
                bool(widget.property("mobaTabCloseable")),
            )
            if tabs.tabIcon(index).isNull():
                errors.append(f"mobaxterm live GUI tab chrome {chrome_key!r} must use a generated icon")
        missing_tab_chrome = sorted(EXPECTED_MOBA_TAB_CHROME_KEYS - set(tab_chrome))
        if missing_tab_chrome:
            errors.append(f"mobaxterm live GUI connected tab chrome missing keys: {missing_tab_chrome}")
        for key, (icon_key, closeable) in tab_chrome.items():
            if key in EXPECTED_MOBA_TAB_CHROME_KEYS and not icon_key:
                errors.append(f"mobaxterm live GUI tab chrome {key!r} missing mobaTabIconKey")
            if key == "active-session" and not closeable:
                errors.append("mobaxterm live GUI active connected tab must be closeable")
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
            if button.icon().isNull():
                errors.append(f"mobaxterm live GUI right utility action {key!r} must use a generated icon")
        status_notice = window.findChild(QLabel, "productStatusNotice")
        if status_notice is None:
            errors.append("mobaxterm live GUI missing bottom status notice")
        elif EXPECTED_MOBA_STATUS_CHROME.notice not in status_notice.text():
            errors.append("mobaxterm live GUI bottom status notice text drifted")
        status_marker = window.findChild(QLabel, "productStatusMarker")
        if status_marker is None:
            errors.append("mobaxterm live GUI missing bottom status right marker")
        elif status_marker.text() != EXPECTED_MOBA_STATUS_CHROME.right_marker:
            errors.append("mobaxterm live GUI bottom status marker drifted")
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

    errors.extend(check_live_workflow_cards(window, preset_id))
    if preset_id != "mobaxterm":
        errors.extend(check_live_workspace_surface(window, preset_id))
        errors.extend(check_live_reference_state(window, preset_id))
        if preset_id == "securecrt":
            errors.extend(check_live_securecrt_session_status_strip(window))
            errors.extend(check_live_securecrt_command_window(window))
        if preset_id == "remmina":
            errors.extend(check_live_remmina_profile_list_chrome(window))
            errors.extend(check_live_remmina_viewer_controls(window))
        if preset_id == "termius":
            errors.extend(check_live_termius_header_chips(window))
            errors.extend(check_live_termius_host_identity_strip(window))
        if preset_id == "mremoteng":
            errors.extend(check_live_mremoteng_document_controls(window))
            errors.extend(check_live_mremoteng_property_grid(window))
    errors.extend(check_live_interaction_state(window, preset_id))
    return errors


def live_tab_labels(tabs: Any) -> set[str]:
    return {tabs.tabText(index) for index in range(tabs.count())}


def check_live_tree_content(window: Any, preset_id: str) -> list[str]:
    from PyQt6.QtWidgets import QTreeWidget

    tree = window.findChild(QTreeWidget, "profileTree")
    if tree is None:
        return [f"{preset_id} live GUI missing profile tree for content contract"]
    labels = collect_tree_labels(tree)
    expected = EXPECTED_LIVE_TREE_LABELS.get(preset_id, set())
    missing = sorted(expected - labels)
    if missing:
        return [f"{preset_id} live GUI profile tree missing expected labels: {missing}"]
    return []


def collect_tree_labels(tree: Any) -> set[str]:
    labels: set[str] = set()

    def walk(item: Any) -> None:
        labels.add(item.text(0))
        for child_index in range(item.childCount()):
            walk(item.child(child_index))

    for index in range(tree.topLevelItemCount()):
        walk(tree.topLevelItem(index))
    return labels


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


def required_termius_host_identity_texts() -> set[str]:
    strip = gui_design_termius_host_identity_strip()
    return {strip.title, *{f"{field.label}: {field.value}" for field in strip.fields}}


def check_live_securecrt_session_status_strip(window: Any) -> list[str]:
    from PyQt6.QtWidgets import QLabel, QWidget

    chrome = gui_design_securecrt_session_status_strip()
    panel = window.findChild(QWidget, "secureCrtSessionStatusStrip")
    if panel is None:
        return ["securecrt live GUI missing session-status evidence strip"]
    actual_preset = str(panel.property("designPreset") or "")
    if actual_preset != "securecrt":
        return [f"securecrt live GUI session-status designPreset {actual_preset!r} must equal 'securecrt'"]
    actual_panel_keys = list(panel.property("secureCrtSessionStatusFieldKeys") or [])
    expected_keys = [field.key for field in chrome.fields]
    if actual_panel_keys != expected_keys:
        return [f"securecrt live GUI session-status field keys {actual_panel_keys!r} must equal {expected_keys!r}"]
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
    return []


def check_live_securecrt_command_window(window: Any) -> list[str]:
    from PyQt6.QtWidgets import QLabel, QWidget

    chrome = gui_design_securecrt_command_window_chrome()
    panel = window.findChild(QWidget, "secureCrtCommandWindow")
    if panel is None:
        return ["securecrt live GUI missing command-window evidence strip"]
    actual_key = str(panel.property("secureCrtCommandWindowKey") or "")
    if actual_key != chrome.key:
        return [f"securecrt live GUI command-window key {actual_key!r} must equal {chrome.key!r}"]
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
    filter_input = panel.findChild(QLineEdit, "remminaProfileFilter")
    if filter_input is None or filter_input.placeholderText() != chrome.filter_placeholder:
        actual_placeholder = None if filter_input is None else filter_input.placeholderText()
        return [
            f"remmina live GUI profile filter placeholder {actual_placeholder!r} "
            f"must equal {chrome.filter_placeholder!r}"
        ]
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


def check_live_termius_host_identity_strip(window: Any) -> list[str]:
    from PyQt6.QtWidgets import QLabel, QWidget

    strip = gui_design_termius_host_identity_strip()
    panel = window.findChild(QWidget, "termiusHostIdentityStrip")
    if panel is None:
        return ["termius live GUI missing host-identity evidence strip"]
    actual_preset = str(panel.property("designPreset") or "")
    if actual_preset != "termius":
        return [f"termius live GUI host-identity designPreset {actual_preset!r} must equal 'termius'"]
    actual_panel_keys = list(panel.property("termiusHostIdentityFieldKeys") or [])
    expected_keys = [field.key for field in strip.fields]
    if actual_panel_keys != expected_keys:
        return [f"termius live GUI host-identity field keys {actual_panel_keys!r} must equal {expected_keys!r}"]
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
    title = panel.findChild(QLabel, "mRemoteNgDocumentTitle")
    if title is None or title.text() != chrome.title:
        actual_title = None if title is None else title.text()
        return [f"mremoteng live GUI document toolbar title {actual_title!r} must equal {chrome.title!r}"]
    filter_input = panel.findChild(QLineEdit, "mRemoteNgDocumentFilter")
    if filter_input is None or filter_input.placeholderText() != chrome.filter_placeholder:
        actual_placeholder = None if filter_input is None else filter_input.placeholderText()
        return [
            f"mremoteng live GUI document filter placeholder {actual_placeholder!r} "
            f"must equal {chrome.filter_placeholder!r}"
        ]

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
        if button.icon().isNull():
            return [f"mremoteng live GUI document-control {control.key!r} must use an icon"]
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


def live_contract_checks_for_preset(preset_id: str) -> list[str]:
    checks = [
        "required-widget-visibility",
        "session-tabs",
        "home-tab-label",
        "profile-tree-content",
        "status-segments",
        "workflow-cards",
        "interaction-state",
    ]
    if live_layout_contracts_for_preset(preset_id):
        checks.append("layout-geometry")
    if live_topology_contracts_for_preset(preset_id):
        checks.append("live-topology")
    if preset_id == "mobaxterm":
        checks.extend(
            [
                "quick-connect-strip",
                "titlebar-chrome",
                "top-menu-chrome",
                "ribbon-actions",
                "generated-ribbon-icons",
                "moba-rail-roles",
                "moba-rail-labels",
                "connected-tab-chrome",
                "right-utility-rail",
                "connected-sftp-dock",
                "sftp-toolbar-groups",
                "sftp-dock-density",
                "sftp-browser-chrome",
                "sftp-dock-chrome",
                "remote-monitoring-dock",
                "moba-monitoring-controls",
                "ssh-banner",
                "ssh-banner-chrome",
                "terminal-transcript",
                "bottom-telemetry",
                "bottom-status-chrome",
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
            checks.append("securecrt-session-status-strip")
            checks.append("securecrt-command-window")
        if preset_id == "remmina":
            checks.append("remmina-profile-list-chrome")
            checks.append("remmina-viewer-controls")
        if preset_id == "termius":
            checks.append("termius-header-chips")
            checks.append("termius-host-identity-strip")
        if preset_id == "mremoteng":
            checks.append("mremoteng-document-controls")
            checks.append("mremoteng-property-grid")
    return checks


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
        "expected_status_segments": list(gui_design_status_segments(preset_id)),
        "expected_moba_rail_labels": EXPECTED_MOBA_RAIL_LABELS if preset_id == "mobaxterm" else {},
        "expected_moba_top_menu": (
            [{"key": item.key, "label": item.label, "primary_action": item.primary_action} for item in EXPECTED_MOBA_TOP_MENU_ITEMS]
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
        "expected_moba_tab_chrome_keys": sorted(EXPECTED_MOBA_TAB_CHROME_KEYS) if preset_id == "mobaxterm" else [],
        "expected_moba_static_tab_chrome_keys": (
            sorted(EXPECTED_MOBA_STATIC_TAB_CHROME_KEYS) if preset_id == "mobaxterm" else []
        ),
        "expected_moba_right_utility_keys": sorted(EXPECTED_MOBA_RIGHT_UTILITY_KEYS)
        if preset_id == "mobaxterm"
        else [],
        "expected_moba_right_utility_actions": (
            [
                {
                    "key": action.key,
                    "icon_key": action.icon_key,
                    "label": action.label,
                }
                for action in gui_design_moba_right_utility_actions()
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
        "expected_moba_sftp_browser_chrome": (
            {
                "path_placeholder": EXPECTED_MOBA_SFTP_BROWSER_CHROME.path_placeholder,
                "dropdown_marker": EXPECTED_MOBA_SFTP_BROWSER_CHROME.dropdown_marker,
                "columns": [
                    {"key": column.key, "label": column.label, "static_x": column.static_x}
                    for column in EXPECTED_MOBA_SFTP_BROWSER_CHROME.columns
                ],
            }
            if preset_id == "mobaxterm"
            else {}
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
        "expected_moba_telemetry_cells": (
            [cell.to_dict() for cell in EXPECTED_MOBA_TELEMETRY_CELLS]
            if preset_id == "mobaxterm"
            else []
        ),
        "expected_moba_monitoring_metric_keys": sorted(EXPECTED_MOBA_MONITORING_METRIC_KEYS)
        if preset_id == "mobaxterm"
        else [],
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
        "expected_moba_status_keys": sorted(EXPECTED_MOBA_STATUS_KEYS) if preset_id == "mobaxterm" else [],
        "expected_moba_status_chrome": (
            {
                "notice": EXPECTED_MOBA_STATUS_CHROME.notice,
                "product_note": EXPECTED_MOBA_STATUS_CHROME.product_note,
                "right_marker": EXPECTED_MOBA_STATUS_CHROME.right_marker,
            }
            if preset_id == "mobaxterm"
            else {}
        ),
        "expected_moba_ssh_banner_chrome": (
            {
                "title": EXPECTED_MOBA_SSH_BANNER_CHROME.title,
                "subtitle": EXPECTED_MOBA_SSH_BANNER_CHROME.subtitle,
                "static_width": EXPECTED_MOBA_SSH_BANNER_CHROME.static_width,
                "static_height": EXPECTED_MOBA_SSH_BANNER_CHROME.static_height,
            }
            if preset_id == "mobaxterm"
            else {}
        ),
        "expected_workflow_card_titles": [card.title for card in gui_design_workflow_cards(preset_id)],
        "expected_workspace_surface_texts": workspace_texts,
        "expected_reference_state_texts": reference_texts,
        "expected_reference_status_segments": list(gui_design_reference_state(preset_id).status_segments),
        "expected_securecrt_command_window": (
            {
                "key": EXPECTED_SECURECRT_COMMAND_WINDOW_CHROME.key,
                "title": EXPECTED_SECURECRT_COMMAND_WINDOW_CHROME.title,
                "target_scope": EXPECTED_SECURECRT_COMMAND_WINDOW_CHROME.target_scope,
                "command": EXPECTED_SECURECRT_COMMAND_WINDOW_CHROME.command,
                "send_label": EXPECTED_SECURECRT_COMMAND_WINDOW_CHROME.send_label,
                "status": EXPECTED_SECURECRT_COMMAND_WINDOW_CHROME.status,
            }
            if preset_id == "securecrt"
            else {}
        ),
        "expected_securecrt_session_status_strip": (
            {
                "title": EXPECTED_SECURECRT_SESSION_STATUS_STRIP.title,
                "fields": [
                    {
                        "key": field.key,
                        "label": field.label,
                        "value": field.value,
                        "static_width": field.static_width,
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
                "columns": [
                    {
                        "key": column.key,
                        "label": column.label,
                        "static_width": column.static_width,
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
        "expected_termius_host_identity_strip": (
            {
                "title": EXPECTED_TERMIUS_HOST_IDENTITY_STRIP.title,
                "fields": [
                    {
                        "key": field.key,
                        "label": field.label,
                        "value": field.value,
                        "static_width": field.static_width,
                    }
                    for field in EXPECTED_TERMIUS_HOST_IDENTITY_STRIP.fields
                ],
            }
            if preset_id == "termius"
            else {}
        ),
        "expected_mremoteng_document_controls": (
            {
                "title": EXPECTED_MREMOTENG_DOCUMENT_TOOLBAR_CHROME.title,
                "filter_placeholder": EXPECTED_MREMOTENG_DOCUMENT_TOOLBAR_CHROME.filter_placeholder,
                "controls": [
                    {
                        "key": control.key,
                        "icon_key": control.icon_key,
                        "label": control.label,
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
        "session-filter": "toolbarSearch",
        "host-search": "toolbarSearch",
        "profile-filter": "toolbarSearch",
        "tree-filter": "toolbarSearch",
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

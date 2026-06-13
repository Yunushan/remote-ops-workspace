from __future__ import annotations

import shlex
from dataclasses import dataclass, field
from dataclasses import replace as replace_dataclass
from pathlib import PurePosixPath

from . import command_safety as safe
from .file_transfer import SftpBatchPlan, build_sftp_list_plan
from .launcher import build_launch_plan
from .models import Profile

REMOTE_MONITORING_SCRIPT = (
    "cpu=$(awk 'NR==1{print int(($2+$4)*100/($2+$4+$5+1))}' /proc/stat 2>/dev/null || echo 0); "
    "mem=$(awk '/MemTotal/{t=$2}/MemAvailable/{a=$2}END{print int((t-a)/1024)\"/\"int(t/1024)}' "
    "/proc/meminfo 2>/dev/null || echo 0/0); "
    "disk=$(df -Pk / 2>/dev/null | awk 'NR==2{print int($3/1024)\"/\"int($2/1024)}'); "
    "load=$(cut -d' ' -f1 /proc/loadavg 2>/dev/null || echo 0); "
    "users=$(who 2>/dev/null | wc -l); "
    "processes=$(ps -e 2>/dev/null | wc -l); "
    "printf 'cpu=%s mem_mb=%s disk_mb=%s load=%s users=%s processes=%s\\n' "
    "\"$cpu\" \"$mem\" \"$disk\" \"$load\" \"$users\" \"$processes\""
)

MOBA_TELEMETRY_ICON_SIZE = 12
MOBA_TELEMETRY_ICON_ACCENTS = {
    "host": "#35d7c7",
    "cpu": "#f4c430",
    "memory": "#6ac76a",
    "disk": "#6ac76a",
    "upload": "#4da3ff",
    "download": "#4da3ff",
    "connection": "#35d7c7",
    "process": "#f4c430",
}
MOBA_TELEMETRY_CELL_WIDTHS = {
    "target": 165,
    "cpu": 60,
    "memory": 125,
    "disk": 124,
    "net-up": 88,
    "net-down": 88,
    "connections": 145,
    "processes": 77,
}
MOBA_TELEMETRY_BAR_HEIGHT = 24
MOBA_TELEMETRY_START_X = 10
MOBA_TELEMETRY_CELL_Y = 1
MOBA_TELEMETRY_CELL_HEIGHT = 22
MOBA_TELEMETRY_SEPARATOR_TOP = 2
MOBA_TELEMETRY_SEPARATOR_BOTTOM = 22
MOBA_TELEMETRY_ICON_X = 5
MOBA_TELEMETRY_ICON_Y = 5
MOBA_TELEMETRY_LABEL_X = 22
MOBA_TELEMETRY_LABEL_Y = 6
MOBA_TELEMETRY_LABEL_FONT_SIZE = 9


@dataclass(frozen=True, slots=True)
class RemoteFileEntry:
    name: str
    kind: str
    size_kb: int
    modified: str

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "kind": self.kind,
            "size_kb": self.size_kb,
            "modified": self.modified,
        }


@dataclass(frozen=True, slots=True)
class SshConnectionCapability:
    key: str
    label: str
    value: str
    status: str
    note: str = ""

    def line(self, *, label_width: int = 15) -> str:
        return f"{self.label:<{label_width}}: {self.value}"

    def to_dict(self) -> dict[str, str]:
        return {
            "key": self.key,
            "label": self.label,
            "value": self.value,
            "status": self.status,
            "note": self.note,
            "line": self.line(),
        }


@dataclass(frozen=True, slots=True)
class SshConnectionBanner:
    title: str
    direct_ssh: bool
    ssh_compression: bool
    ssh_browser: bool
    x11_forwarding: str

    def target_line(self) -> str:
        return f"SSH session to {self.title}"

    def capability_rows(self) -> tuple[SshConnectionCapability, ...]:
        x11_disabled = self.x11_forwarding.startswith("disabled")
        return (
            SshConnectionCapability("direct-ssh", "Direct SSH", checkmark(self.direct_ssh), bool_status(self.direct_ssh)),
            SshConnectionCapability(
                "ssh-compression",
                "SSH compression",
                checkmark(self.ssh_compression),
                bool_status(self.ssh_compression),
            ),
            SshConnectionCapability(
                "ssh-browser",
                "SSH-browser",
                checkmark(self.ssh_browser),
                bool_status(self.ssh_browser),
            ),
            SshConnectionCapability(
                "x11-forwarding",
                "X11-forwarding",
                self.x11_forwarding,
                "disabled" if x11_disabled else "ok",
                "server-disabled" if x11_disabled else "",
            ),
        )

    def footer_links(self) -> tuple[str, str]:
        return ("help", "website")

    def lines(self) -> list[str]:
        return [
            self.target_line(),
            *(row.line() for row in self.capability_rows()),
        ]

    def to_dict(self) -> dict[str, object]:
        return {
            "title": self.title,
            "direct_ssh": self.direct_ssh,
            "ssh_compression": self.ssh_compression,
            "ssh_browser": self.ssh_browser,
            "x11_forwarding": self.x11_forwarding,
            "lines": self.lines(),
            "capabilities": [row.to_dict() for row in self.capability_rows()],
            "footer_links": list(self.footer_links()),
        }


@dataclass(frozen=True, slots=True)
class RemoteMonitoringPlan:
    profile_name: str
    command: list[str]
    notes: list[str] = field(default_factory=list)

    def printable(self) -> str:
        return shlex.join(self.command)

    def to_dict(self) -> dict[str, object]:
        return {
            "profile_name": self.profile_name,
            "command": self.command,
            "notes": self.notes,
        }


@dataclass(frozen=True, slots=True)
class RemoteMonitoringSnapshot:
    cpu_percent: int
    memory_used_gb: float
    memory_total_gb: float
    disk_used_gb: float
    disk_total_gb: float
    net_up_mbps: float
    net_down_mbps: float
    connection_count: int
    process_count: int
    load_average: str = "0.00"

    @property
    def memory_label(self) -> str:
        return f"{self.memory_used_gb:.1f} GB / {self.memory_total_gb:.1f} GB"

    @property
    def disk_label(self) -> str:
        return f"{self.disk_used_gb:.1f} GB / {self.disk_total_gb:.1f} GB"

    @property
    def network_label(self) -> str:
        return f"{self.net_up_mbps:.2f} Mb/s up, {self.net_down_mbps:.2f} Mb/s down"

    def to_dict(self) -> dict[str, object]:
        return {
            "cpu_percent": self.cpu_percent,
            "memory_used_gb": self.memory_used_gb,
            "memory_total_gb": self.memory_total_gb,
            "disk_used_gb": self.disk_used_gb,
            "disk_total_gb": self.disk_total_gb,
            "net_up_mbps": self.net_up_mbps,
            "net_down_mbps": self.net_down_mbps,
            "connection_count": self.connection_count,
            "process_count": self.process_count,
            "load_average": self.load_average,
        }


@dataclass(frozen=True, slots=True)
class MobaTelemetrySegment:
    key: str
    icon_key: str
    label: str
    value: str

    def to_dict(self) -> dict[str, str]:
        return {
            "key": self.key,
            "icon_key": self.icon_key,
            "label": self.label,
            "value": self.value,
        }


@dataclass(frozen=True, slots=True)
class MobaTelemetryCell:
    key: str
    icon_key: str
    icon_accent: str
    icon_size: int
    label: str
    value: str
    display_text: str
    width: int

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "icon_key": self.icon_key,
            "icon_accent": self.icon_accent,
            "icon_size": self.icon_size,
            "label": self.label,
            "value": self.value,
            "display_text": self.display_text,
            "width": self.width,
        }


@dataclass(frozen=True, slots=True)
class MobaTelemetryCellGeometry:
    key: str
    static_x: int
    static_y: int
    width: int
    height: int
    icon_x: int
    icon_y: int
    icon_size: int
    label_x: int
    label_y: int
    label_font_size: int
    separator_top: int
    separator_bottom: int

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "static_x": self.static_x,
            "static_y": self.static_y,
            "width": self.width,
            "height": self.height,
            "icon_x": self.icon_x,
            "icon_y": self.icon_y,
            "icon_size": self.icon_size,
            "label_x": self.label_x,
            "label_y": self.label_y,
            "label_font_size": self.label_font_size,
            "separator_top": self.separator_top,
            "separator_bottom": self.separator_bottom,
        }


@dataclass(frozen=True, slots=True)
class MobaConnectedTabChromeItem:
    key: str
    label: str
    icon_key: str
    active: bool
    closeable: bool
    width: int
    tooltip: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "label": self.label,
            "icon_key": self.icon_key,
            "active": self.active,
            "closeable": self.closeable,
            "width": self.width,
            "tooltip": self.tooltip,
        }


@dataclass(frozen=True, slots=True)
class MobaConnectedTabChromeGeometry:
    key: str
    width: int
    height: int
    corner_radius: int
    icon_x: int
    icon_y: int
    icon_size: int
    label_x: int
    label_y: int
    close_right_offset: int
    close_y: int
    plus_x: int
    plus_y: int
    gap_after: int

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "width": self.width,
            "height": self.height,
            "corner_radius": self.corner_radius,
            "icon_x": self.icon_x,
            "icon_y": self.icon_y,
            "icon_size": self.icon_size,
            "label_x": self.label_x,
            "label_y": self.label_y,
            "close_right_offset": self.close_right_offset,
            "close_y": self.close_y,
            "plus_x": self.plus_x,
            "plus_y": self.plus_y,
            "gap_after": self.gap_after,
        }


@dataclass(frozen=True, slots=True)
class MobaTerminalTranscriptLine:
    key: str
    text: str
    tone: str

    def to_dict(self) -> dict[str, str]:
        return {
            "key": self.key,
            "text": self.text,
            "tone": self.tone,
        }


@dataclass(frozen=True, slots=True)
class MobaConnectedSessionState:
    profile_name: str
    target: str
    connection_label: str
    remote_path: str
    follow_terminal_folder: bool
    file_entries: tuple[RemoteFileEntry, ...]
    sftp_list_plan: SftpBatchPlan
    follow_folder_plan: SftpBatchPlan
    monitoring_plan: RemoteMonitoringPlan
    monitoring: RemoteMonitoringSnapshot
    banner: SshConnectionBanner
    terminal_transcript: tuple[MobaTerminalTranscriptLine, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "profile_name": self.profile_name,
            "target": self.target,
            "connection_label": self.connection_label,
            "remote_path": self.remote_path,
            "follow_terminal_folder": self.follow_terminal_folder,
            "file_entries": [item.to_dict() for item in self.file_entries],
            "sftp_list_plan": {
                "command": self.sftp_list_plan.command,
                "batch_commands": self.sftp_list_plan.batch_commands,
            },
            "follow_folder_plan": {
                "command": self.follow_folder_plan.command,
                "batch_commands": self.follow_folder_plan.batch_commands,
            },
            "monitoring_plan": self.monitoring_plan.to_dict(),
            "monitoring": self.monitoring.to_dict(),
            "telemetry_cells": [cell.to_dict() for cell in moba_telemetry_cells(self)],
            "connected_route": moba_connected_session_route(self).to_dict(),
            "identity_route": moba_connected_session_identity_route(self).to_dict(),
            "session_action_route": moba_connected_session_action_route(self).to_dict(),
            "sftp_terminal_folder_route": moba_sftp_terminal_folder_route(self).to_dict(),
            "banner": self.banner.to_dict(),
            "terminal_transcript": [line.to_dict() for line in self.terminal_transcript],
        }


@dataclass(frozen=True, slots=True)
class MobaConnectedSessionRoute:
    key: str
    route_role: str
    active_tab_key: str
    active_tab_label: str
    reference_tab_label: str
    active_tab_object: str
    connected_panel_object: str
    left_dock_object: str
    sftp_browser_object: str
    sftp_path_object: str
    sftp_table_object: str
    ssh_banner_object: str
    terminal_area_object: str
    terminal_output_object: str
    telemetry_bar_object: str
    telemetry_identity_cell_key: str
    target: str
    remote_path: str
    tab_label_property: str
    target_property: str
    remote_path_property: str
    render_source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "route_role": self.route_role,
            "active_tab_key": self.active_tab_key,
            "active_tab_label": self.active_tab_label,
            "reference_tab_label": self.reference_tab_label,
            "active_tab_object": self.active_tab_object,
            "connected_panel_object": self.connected_panel_object,
            "left_dock_object": self.left_dock_object,
            "sftp_browser_object": self.sftp_browser_object,
            "sftp_path_object": self.sftp_path_object,
            "sftp_table_object": self.sftp_table_object,
            "ssh_banner_object": self.ssh_banner_object,
            "terminal_area_object": self.terminal_area_object,
            "terminal_output_object": self.terminal_output_object,
            "telemetry_bar_object": self.telemetry_bar_object,
            "telemetry_identity_cell_key": self.telemetry_identity_cell_key,
            "target": self.target,
            "remote_path": self.remote_path,
            "tab_label_property": self.tab_label_property,
            "target_property": self.target_property,
            "remote_path_property": self.remote_path_property,
            "render_source": self.render_source,
        }


@dataclass(frozen=True, slots=True)
class MobaConnectedSessionIdentityRoute:
    key: str
    route_role: str
    window_title: str
    active_tab_label: str
    reference_tab_label: str
    banner_target: str
    web_console_line: str
    terminal_prompt: str
    telemetry_target: str
    target_endpoint: str
    remote_path: str
    window_title_property: str
    banner_target_property: str
    terminal_prompt_property: str
    telemetry_target_property: str
    render_source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "route_role": self.route_role,
            "window_title": self.window_title,
            "active_tab_label": self.active_tab_label,
            "reference_tab_label": self.reference_tab_label,
            "banner_target": self.banner_target,
            "web_console_line": self.web_console_line,
            "terminal_prompt": self.terminal_prompt,
            "telemetry_target": self.telemetry_target,
            "target_endpoint": self.target_endpoint,
            "remote_path": self.remote_path,
            "window_title_property": self.window_title_property,
            "banner_target_property": self.banner_target_property,
            "terminal_prompt_property": self.terminal_prompt_property,
            "telemetry_target_property": self.telemetry_target_property,
            "render_source": self.render_source,
        }


@dataclass(frozen=True, slots=True)
class MobaConnectedSessionActionRoute:
    key: str
    route_role: str
    profile_name: str
    target: str
    active_tab_key: str
    active_tab_label: str
    reference_tab_label: str
    tabs_object: str
    tab_bar_object: str
    reference_tab_role: str
    menu_object: str
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
            "profile_name": self.profile_name,
            "target": self.target,
            "active_tab_key": self.active_tab_key,
            "active_tab_label": self.active_tab_label,
            "reference_tab_label": self.reference_tab_label,
            "tabs_object": self.tabs_object,
            "tab_bar_object": self.tab_bar_object,
            "reference_tab_role": self.reference_tab_role,
            "menu_object": self.menu_object,
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


@dataclass(frozen=True, slots=True)
class MobaSftpTerminalFolderRoute:
    key: str
    route_role: str
    terminal_area_object: str
    terminal_output_object: str
    source_control_object: str
    target_browser_object: str
    target_path_object: str
    target_table_object: str
    parent_row_label: str
    selected_row_kind: str
    remote_path: str
    list_command: str
    follow_enabled: bool
    path_property: str
    plan_property: str
    enabled_property: str
    row_route_property: str
    render_source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "route_role": self.route_role,
            "terminal_area_object": self.terminal_area_object,
            "terminal_output_object": self.terminal_output_object,
            "source_control_object": self.source_control_object,
            "target_browser_object": self.target_browser_object,
            "target_path_object": self.target_path_object,
            "target_table_object": self.target_table_object,
            "parent_row_label": self.parent_row_label,
            "selected_row_kind": self.selected_row_kind,
            "remote_path": self.remote_path,
            "list_command": self.list_command,
            "follow_enabled": self.follow_enabled,
            "path_property": self.path_property,
            "plan_property": self.plan_property,
            "enabled_property": self.enabled_property,
            "row_route_property": self.row_route_property,
            "render_source": self.render_source,
        }


def build_moba_connected_session_state(
    profile: Profile,
    *,
    remote_path: str = "/",
    terminal_cwd: str | None = None,
    follow_terminal_folder: bool = True,
    sftp_listing: str = "",
    monitoring_output: str = "",
) -> MobaConnectedSessionState:
    _require_ssh_browser_profile(profile)
    selected_path = normalise_remote_path(terminal_cwd if follow_terminal_folder and terminal_cwd else remote_path)
    entries = tuple(parse_sftp_ls_output(sftp_listing) or default_remote_file_entries(selected_path))
    return MobaConnectedSessionState(
        profile_name=profile.name,
        target=profile.display_target,
        connection_label=moba_connected_profile_label(profile),
        remote_path=selected_path,
        follow_terminal_folder=follow_terminal_folder,
        file_entries=entries,
        sftp_list_plan=build_sftp_list_plan(profile, selected_path),
        follow_folder_plan=build_follow_terminal_folder_plan(profile, selected_path),
        monitoring_plan=build_remote_monitoring_plan(profile),
        monitoring=parse_remote_monitoring_output(monitoring_output) or default_remote_monitoring_snapshot(profile),
        banner=build_ssh_connection_banner(profile),
        terminal_transcript=build_moba_terminal_transcript(profile, selected_path),
    )


def moba_connected_profile_label(profile: Profile) -> str:
    target = moba_connected_profile_target(profile)
    if profile.username:
        return f"{target} ({profile.username})"
    return target


def moba_connected_profile_target(profile: Profile) -> str:
    if profile.host:
        if profile.port and profile.port not in {22}:
            return f"{profile.host}:{profile.port}"
        return profile.host
    return profile.display_target


def moba_connected_tab_label(state: MobaConnectedSessionState, *, ordinal: int | None = None) -> str:
    if ordinal is None:
        return state.connection_label
    return f"{ordinal}. {state.connection_label}"


def moba_connected_window_title(state: MobaConnectedSessionState) -> str:
    return state.connection_label


def moba_connected_session_route(state: MobaConnectedSessionState) -> MobaConnectedSessionRoute:
    return MobaConnectedSessionRoute(
        key="moba-active-connected-session-route",
        route_role="active-tab-to-connected-workspace",
        active_tab_key="active-session",
        active_tab_label=moba_connected_tab_label(state),
        reference_tab_label=moba_connected_tab_label(state, ordinal=7),
        active_tab_object="sessionTabs",
        connected_panel_object="mobaConnectedSession",
        left_dock_object="mobaConnectedLeftDock",
        sftp_browser_object="mobaSftpBrowser",
        sftp_path_object="mobaSftpPath",
        sftp_table_object="mobaSftpFileTable",
        ssh_banner_object="mobaSshBanner",
        terminal_area_object="mobaTerminalArea",
        terminal_output_object="terminalOutput",
        telemetry_bar_object="mobaTelemetryBar",
        telemetry_identity_cell_key="target",
        target=state.target,
        remote_path=state.remote_path,
        tab_label_property="mobaConnectedRouteActiveTabLabel",
        target_property="mobaConnectedRouteTarget",
        remote_path_property="mobaConnectedRouteRemotePath",
        render_source="connected-session-state",
    )


def moba_connected_session_identity_route(state: MobaConnectedSessionState) -> MobaConnectedSessionIdentityRoute:
    transcript_by_key = {line.key: line.text for line in state.terminal_transcript}
    telemetry_by_key = {cell.key: cell.display_text for cell in moba_telemetry_cells(state)}
    return MobaConnectedSessionIdentityRoute(
        key="moba-connected-session-identity-route",
        route_role="title-tab-banner-terminal-telemetry-identity",
        window_title=moba_connected_window_title(state),
        active_tab_label=moba_connected_tab_label(state),
        reference_tab_label=moba_connected_tab_label(state, ordinal=7),
        banner_target=state.banner.title,
        web_console_line=transcript_by_key.get("web-console", ""),
        terminal_prompt=transcript_by_key.get("prompt-ready", ""),
        telemetry_target=telemetry_by_key.get("target", ""),
        target_endpoint=state.target,
        remote_path=state.remote_path,
        window_title_property="mobaConnectedIdentityWindowTitle",
        banner_target_property="mobaConnectedIdentityBannerTarget",
        terminal_prompt_property="mobaConnectedIdentityTerminalPrompt",
        telemetry_target_property="mobaConnectedIdentityTelemetryTarget",
        render_source="connected-session-state",
    )


MOBA_CONNECTED_SESSION_ACTION_KEYS = (
    "new-local-terminal",
    "split-horizontal",
    "split-vertical",
    "duplicate-tab",
    "close-tab",
    "close-other-tabs",
    "recover-previous-sessions",
)
MOBA_CONNECTED_SESSION_ACTION_LABELS = (
    "New local terminal",
    "Split horizontal",
    "Split vertical",
    "Duplicate tab",
    "Close tab",
    "Close other tabs",
    "Recover previous sessions",
)
MOBA_CONNECTED_SESSION_ALWAYS_ENABLED_ACTION_KEYS = (
    "new-local-terminal",
    "split-horizontal",
    "split-vertical",
    "duplicate-tab",
    "close-tab",
    "recover-previous-sessions",
)
MOBA_CONNECTED_SESSION_CONDITIONAL_ENABLED_ACTION_KEYS = ("close-other-tabs",)


def moba_connected_session_action_route(state: MobaConnectedSessionState) -> MobaConnectedSessionActionRoute:
    return MobaConnectedSessionActionRoute(
        key="moba-connected-session-actions-route",
        route_role="active-connected-tab-context-session-actions",
        profile_name=state.profile_name,
        target=state.target,
        active_tab_key="active-session",
        active_tab_label=moba_connected_tab_label(state),
        reference_tab_label=moba_connected_tab_label(state, ordinal=7),
        tabs_object="sessionTabs",
        tab_bar_object="sessionTabBar",
        reference_tab_role="terminal",
        menu_object="mobaConnectedSessionTabContextMenu",
        action_object="mobaConnectedSessionTabContextAction",
        expected_action_keys=MOBA_CONNECTED_SESSION_ACTION_KEYS,
        expected_action_labels=MOBA_CONNECTED_SESSION_ACTION_LABELS,
        expected_action_count=len(MOBA_CONNECTED_SESSION_ACTION_KEYS),
        always_enabled_action_keys=MOBA_CONNECTED_SESSION_ALWAYS_ENABLED_ACTION_KEYS,
        conditional_enabled_action_keys=MOBA_CONNECTED_SESSION_CONDITIONAL_ENABLED_ACTION_KEYS,
        action_key_property="sessionTabContextActionKey",
        action_label_property="sessionTabContextActionLabel",
        action_enabled_property="sessionTabContextActionEnabled",
        captured_property="mobaConnectedSessionActionCaptured",
        captured_tab_property="mobaConnectedSessionActionCapturedTab",
        captured_action_keys_property="mobaConnectedSessionActionKeys",
        captured_action_labels_property="mobaConnectedSessionActionLabels",
        captured_action_count_property="mobaConnectedSessionActionCount",
        captured_enabled_keys_property="mobaConnectedSessionActionEnabledKeys",
        captured_disabled_keys_property="mobaConnectedSessionActionDisabledKeys",
        render_source="connected-session-state",
    )


def moba_sftp_terminal_folder_route(state: MobaConnectedSessionState) -> MobaSftpTerminalFolderRoute:
    return MobaSftpTerminalFolderRoute(
        key="moba-sftp-terminal-folder-route",
        route_role="terminal-cwd-follow-checkbox-to-sftp-path-and-rows",
        terminal_area_object="mobaTerminalArea",
        terminal_output_object="terminalOutput",
        source_control_object="mobaFollowTerminalFolder",
        target_browser_object="mobaSftpBrowser",
        target_path_object="mobaSftpPath",
        target_table_object="mobaSftpFileTable",
        parent_row_label="..",
        selected_row_kind="parent-dir",
        remote_path=state.remote_path,
        list_command=state.follow_folder_plan.printable_batch(),
        follow_enabled=state.follow_terminal_folder,
        path_property="mobaSftpTerminalFolderRoutePath",
        plan_property="mobaSftpTerminalFolderRoutePlan",
        enabled_property="mobaSftpTerminalFolderRouteEnabled",
        row_route_property="mobaSftpTerminalFolderRouteKey",
        render_source="connected-session-state",
    )


def build_moba_terminal_transcript(profile: Profile, remote_path: str) -> tuple[MobaTerminalTranscriptLine, ...]:
    target = moba_connected_profile_target(profile)
    username = profile.username or "operator"
    host_alias = target.split(":", maxsplit=1)[0].split(".", maxsplit=1)[0] or "remote"
    _normalized_path = normalise_remote_path(remote_path)
    return (
        MobaTerminalTranscriptLine("web-console", f"Web console: https://{target}:9090/ or https://192.0.2.10:9090/", "info"),
        MobaTerminalTranscriptLine("spacer", "", "spacer"),
        MobaTerminalTranscriptLine("last-login", "Last login: Sat Jun  6 05:27:50 2026", "info"),
        MobaTerminalTranscriptLine("prompt-ready", f"[{username}@{host_alias} ~]$ ", "command"),
        )


MOBA_CONNECTED_TAB_CHROME_GEOMETRY: tuple[MobaConnectedTabChromeGeometry, ...] = (
    MobaConnectedTabChromeGeometry(
        key="home",
        width=42,
        height=22,
        corner_radius=2,
        icon_x=8,
        icon_y=5,
        icon_size=12,
        label_x=26,
        label_y=7,
        close_right_offset=16,
        close_y=6,
        plus_x=11,
        plus_y=3,
        gap_after=4,
    ),
    MobaConnectedTabChromeGeometry(
        key="inactive-session",
        width=226,
        height=22,
        corner_radius=2,
        icon_x=8,
        icon_y=5,
        icon_size=12,
        label_x=26,
        label_y=7,
        close_right_offset=16,
        close_y=6,
        plus_x=11,
        plus_y=3,
        gap_after=4,
    ),
    MobaConnectedTabChromeGeometry(
        key="active-session",
        width=258,
        height=22,
        corner_radius=2,
        icon_x=8,
        icon_y=5,
        icon_size=12,
        label_x=26,
        label_y=7,
        close_right_offset=16,
        close_y=6,
        plus_x=11,
        plus_y=3,
        gap_after=4,
    ),
    MobaConnectedTabChromeGeometry(
        key="new-session",
        width=32,
        height=22,
        corner_radius=2,
        icon_x=8,
        icon_y=5,
        icon_size=12,
        label_x=26,
        label_y=7,
        close_right_offset=16,
        close_y=6,
        plus_x=11,
        plus_y=3,
        gap_after=4,
    ),
)


def moba_connected_tab_chrome_geometry_items() -> tuple[MobaConnectedTabChromeGeometry, ...]:
    return MOBA_CONNECTED_TAB_CHROME_GEOMETRY


def moba_connected_tab_chrome_geometry_for(key: str) -> MobaConnectedTabChromeGeometry:
    for geometry in MOBA_CONNECTED_TAB_CHROME_GEOMETRY:
        if geometry.key == key:
            return geometry
    raise KeyError(key)


def moba_connected_tab_chrome_items(state: MobaConnectedSessionState) -> tuple[MobaConnectedTabChromeItem, ...]:
    home = moba_connected_tab_chrome_geometry_for("home")
    inactive = moba_connected_tab_chrome_geometry_for("inactive-session")
    active = moba_connected_tab_chrome_geometry_for("active-session")
    new_session = moba_connected_tab_chrome_geometry_for("new-session")
    return (
        MobaConnectedTabChromeItem(
            key="home",
            label="",
            icon_key="home",
            active=False,
            closeable=False,
            width=home.width,
            tooltip="Home",
        ),
        MobaConnectedTabChromeItem(
            key="inactive-session",
            label="6. jump.example.invalid (operator)",
            icon_key="terminal-key",
            active=False,
            closeable=True,
            width=inactive.width,
            tooltip="Inactive connected SSH tab",
        ),
        MobaConnectedTabChromeItem(
            key="active-session",
            label=moba_connected_tab_label(state, ordinal=7),
            icon_key="terminal-key",
            active=True,
            closeable=True,
            width=active.width,
            tooltip="Active connected SSH tab with SFTP browser",
        ),
        MobaConnectedTabChromeItem(
            key="new-session",
            label="+",
            icon_key="plus",
            active=False,
            closeable=False,
            width=new_session.width,
            tooltip="Open a new local terminal",
        ),
    )


def moba_telemetry_segments(state: MobaConnectedSessionState) -> tuple[MobaTelemetrySegment, ...]:
    monitoring = state.monitoring
    return (
        MobaTelemetrySegment("target", "host", "Connected target", state.target),
        MobaTelemetrySegment("cpu", "cpu", "CPU usage", f"{monitoring.cpu_percent}%"),
        MobaTelemetrySegment("memory", "memory", "Memory usage", monitoring.memory_label),
        MobaTelemetrySegment("disk", "disk", "Disk usage", monitoring.disk_label),
        MobaTelemetrySegment("net-up", "upload", "Network upload", f"{monitoring.net_up_mbps:.2f} Mb/s"),
        MobaTelemetrySegment("net-down", "download", "Network download", f"{monitoring.net_down_mbps:.2f} Mb/s"),
        MobaTelemetrySegment("connections", "connection", "Open connections", str(monitoring.connection_count)),
        MobaTelemetrySegment("processes", "process", "Remote processes", str(monitoring.process_count)),
    )


def moba_telemetry_cells(state: MobaConnectedSessionState) -> tuple[MobaTelemetryCell, ...]:
    display_by_key = {
        "target": moba_telemetry_target_display(state),
        "connections": f"Connections: {state.monitoring.connection_count} (port {moba_telemetry_port(state)})",
        "processes": f"{max(1, state.monitoring.connection_count + 1)}/{state.monitoring.process_count}",
    }
    return tuple(
        MobaTelemetryCell(
            key=segment.key,
            icon_key=segment.icon_key,
            icon_accent=MOBA_TELEMETRY_ICON_ACCENTS[segment.icon_key],
            icon_size=MOBA_TELEMETRY_ICON_SIZE,
            label=segment.label,
            value=segment.value,
            display_text=display_by_key.get(segment.key, segment.value),
            width=MOBA_TELEMETRY_CELL_WIDTHS[segment.key],
        )
        for segment in moba_telemetry_segments(state)
    )


def moba_telemetry_cell_geometry() -> tuple[MobaTelemetryCellGeometry, ...]:
    x = MOBA_TELEMETRY_START_X
    geometry: list[MobaTelemetryCellGeometry] = []
    for key, width in MOBA_TELEMETRY_CELL_WIDTHS.items():
        geometry.append(
            MobaTelemetryCellGeometry(
                key=key,
                static_x=x,
                static_y=MOBA_TELEMETRY_CELL_Y,
                width=width,
                height=MOBA_TELEMETRY_CELL_HEIGHT,
                icon_x=MOBA_TELEMETRY_ICON_X,
                icon_y=MOBA_TELEMETRY_ICON_Y,
                icon_size=MOBA_TELEMETRY_ICON_SIZE,
                label_x=MOBA_TELEMETRY_LABEL_X,
                label_y=MOBA_TELEMETRY_LABEL_Y,
                label_font_size=MOBA_TELEMETRY_LABEL_FONT_SIZE,
                separator_top=MOBA_TELEMETRY_SEPARATOR_TOP,
                separator_bottom=MOBA_TELEMETRY_SEPARATOR_BOTTOM,
            )
        )
        x += width
    return tuple(geometry)


def moba_telemetry_cell_geometry_for(key: str) -> MobaTelemetryCellGeometry:
    for geometry in moba_telemetry_cell_geometry():
        if geometry.key == key:
            return geometry
    raise KeyError(key)


def moba_telemetry_port(state: MobaConnectedSessionState) -> str:
    _prefix, separator, suffix = state.target.rpartition(":")
    if separator and suffix.isdigit():
        return suffix
    return "22"


def moba_telemetry_target_display(state: MobaConnectedSessionState) -> str:
    _prefix, separator, suffix = state.target.rpartition(":")
    if separator and suffix.isdigit():
        return state.target
    return f"{state.target}:{moba_telemetry_port(state)}"


def build_follow_terminal_folder_plan(profile: Profile, terminal_cwd: str) -> SftpBatchPlan:
    _require_ssh_browser_profile(profile)
    return build_sftp_list_plan(profile, normalise_remote_path(terminal_cwd))


def build_remote_monitoring_plan(profile: Profile) -> RemoteMonitoringPlan:
    _require_ssh_browser_profile(profile)
    ssh_profile = replace_dataclass(profile, protocol="ssh")
    plan = build_launch_plan(ssh_profile)
    return RemoteMonitoringPlan(
        profile_name=profile.name,
        command=[*plan.command, "sh", "-lc", REMOTE_MONITORING_SCRIPT],
        notes=[
            "Agentless remote monitoring uses the existing SSH transport.",
            "The command reads standard Linux /proc and df data when available.",
            *plan.notes,
        ],
    )


def build_ssh_connection_banner(profile: Profile) -> SshConnectionBanner:
    _require_ssh_browser_profile(profile)
    options = {key.lower(): value.lower() for key, value in profile.options.items()}
    direct_ssh = not any(key in options for key in ("proxy_jump", "proxy_command", "jump_host"))
    compression = options.get("compression", "true") not in {"0", "false", "no", "off"}
    browser = options.get("ssh_browser", "true") not in {"0", "false", "no", "off"}
    x11_value = options.get("x11", "false")
    if x11_value in {"1", "true", "yes", "on"}:
        x11 = "enabled"
    elif x11_value in {"trusted", "yes-trusted"}:
        x11 = "trusted"
    else:
        x11 = "disabled or not supported by server"
    return SshConnectionBanner(
        title=moba_connected_profile_target(profile),
        direct_ssh=direct_ssh,
        ssh_compression=compression,
        ssh_browser=browser,
        x11_forwarding=x11,
    )


def parse_sftp_ls_output(text: str) -> list[RemoteFileEntry]:
    rows: list[RemoteFileEntry] = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("total "):
            continue
        parts = line.split(maxsplit=8)
        if len(parts) < 9:
            continue
        permissions = parts[0]
        size = int(parts[4]) if parts[4].isdigit() else 0
        modified = " ".join(parts[5:8])
        rows.append(
            RemoteFileEntry(
                name=parts[8],
                kind="dir" if permissions.startswith("d") else "file",
                size_kb=max(1, size // 1024) if size else 0,
                modified=modified,
            )
        )
    return rows


def parse_remote_monitoring_output(text: str) -> RemoteMonitoringSnapshot | None:
    values: dict[str, str] = {}
    for token in text.replace("\n", " ").split():
        key, separator, value = token.partition("=")
        if separator:
            values[key] = value
    if not values:
        return None
    mem_used, mem_total = parse_pair_mb(values.get("mem_mb", "0/0"))
    disk_used, disk_total = parse_pair_mb(values.get("disk_mb", "0/0"))
    return RemoteMonitoringSnapshot(
        cpu_percent=clamp_int(values.get("cpu"), 0, 100),
        memory_used_gb=round(mem_used / 1024, 1),
        memory_total_gb=round(mem_total / 1024, 1),
        disk_used_gb=round(disk_used / 1024, 1),
        disk_total_gb=round(disk_total / 1024, 1),
        net_up_mbps=float(values.get("net_up_mbps", "0.01")),
        net_down_mbps=float(values.get("net_down_mbps", "0.01")),
        connection_count=clamp_int(values.get("connections", values.get("users")), 0, 9999),
        process_count=clamp_int(values.get("processes"), 0, 99999),
        load_average=values.get("load", "0.00"),
    )


def default_remote_monitoring_snapshot(profile: Profile) -> RemoteMonitoringSnapshot:
    seed = sum(ord(char) for char in f"{profile.name}:{profile.display_target}")
    cpu = 1 + (seed % 18)
    processes = 120 + (seed % 85)
    return RemoteMonitoringSnapshot(
        cpu_percent=cpu,
        memory_used_gb=0.4 + ((seed % 4) * 0.1),
        memory_total_gb=7.5,
        disk_used_gb=2.2 + ((seed % 7) * 0.2),
        disk_total_gb=48.0,
        net_up_mbps=0.01,
        net_down_mbps=0.01,
        connection_count=1,
        process_count=processes,
        load_average=f"0.{cpu:02d}",
    )


def default_remote_file_entries(remote_path: str) -> list[RemoteFileEntry]:
    if normalise_remote_path(remote_path) == "/":
        return [
            RemoteFileEntry("..", "dir", 0, "2026-06-06"),
            RemoteFileEntry("apps", "dir", 0, "2026-06-06"),
            RemoteFileEntry("logs", "dir", 0, "2026-06-06"),
            RemoteFileEntry("releases", "dir", 0, "2026-06-06"),
            RemoteFileEntry(".bash_history", "file", 2, "2026-06-05"),
            RemoteFileEntry(".profile", "file", 1, "2026-06-05"),
            RemoteFileEntry("README.txt", "file", 3, "2026-06-04"),
        ]
    return [
        RemoteFileEntry("..", "dir", 0, "2026-06-06"),
        RemoteFileEntry("current", "dir", 0, "2026-06-06"),
        RemoteFileEntry("archive", "dir", 0, "2026-06-05"),
        RemoteFileEntry("app.log", "file", 64, "2026-06-06"),
        RemoteFileEntry("health.json", "file", 4, "2026-06-06"),
    ]


def normalise_remote_path(path: str | None) -> str:
    raw = safe.path_arg(path or "/", "remote path")
    if raw.startswith("-"):
        raise ValueError("remote path must not start with '-'")
    if "\n" in raw or "\r" in raw:
        raise ValueError("remote path must be a single line")
    normalized = PurePosixPath(raw)
    if not normalized.is_absolute():
        normalized = PurePosixPath("/") / normalized
    return normalized.as_posix()


def parse_pair_mb(value: str) -> tuple[int, int]:
    left, separator, right = value.partition("/")
    if not separator:
        return 0, 0
    return clamp_int(left, 0, 10_000_000), clamp_int(right, 0, 10_000_000)


def clamp_int(value: str | None, lower: int, upper: int) -> int:
    try:
        parsed = int(float(value or "0"))
    except ValueError:
        return lower
    return max(lower, min(upper, parsed))


def checkmark(enabled: bool) -> str:
    return "yes" if enabled else "no"


def bool_status(enabled: bool) -> str:
    return "ok" if enabled else "disabled"


def _require_ssh_browser_profile(profile: Profile) -> None:
    if profile.protocol.lower() not in {"ssh", "sftp"}:
        raise ValueError(f"Moba connected-session workspace requires an SSH/SFTP profile: {profile.name}")

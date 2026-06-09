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
            "banner": self.banner.to_dict(),
            "terminal_transcript": [line.to_dict() for line in self.terminal_transcript],
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


def moba_connected_tab_chrome_items(state: MobaConnectedSessionState) -> tuple[MobaConnectedTabChromeItem, ...]:
    return (
        MobaConnectedTabChromeItem(
            key="home",
            label="",
            icon_key="home",
            active=False,
            closeable=False,
            width=42,
            tooltip="Home",
        ),
        MobaConnectedTabChromeItem(
            key="inactive-session",
            label="6. jump.example.invalid (operator)",
            icon_key="terminal-key",
            active=False,
            closeable=True,
            width=226,
            tooltip="Inactive connected SSH tab",
        ),
        MobaConnectedTabChromeItem(
            key="active-session",
            label=moba_connected_tab_label(state, ordinal=7),
            icon_key="terminal-key",
            active=True,
            closeable=True,
            width=258,
            tooltip="Active connected SSH tab with SFTP browser",
        ),
        MobaConnectedTabChromeItem(
            key="new-session",
            label="+",
            icon_key="plus",
            active=False,
            closeable=False,
            width=32,
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

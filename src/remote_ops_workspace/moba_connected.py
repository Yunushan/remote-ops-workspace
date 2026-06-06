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
class SshConnectionBanner:
    title: str
    direct_ssh: bool
    ssh_compression: bool
    ssh_browser: bool
    x11_forwarding: str

    def lines(self) -> list[str]:
        return [
            f"SSH session to {self.title}",
            f"Direct SSH      : {checkmark(self.direct_ssh)}",
            f"SSH compression: {checkmark(self.ssh_compression)}",
            f"SSH-browser    : {checkmark(self.ssh_browser)}",
            f"X11-forwarding : {self.x11_forwarding}",
        ]

    def to_dict(self) -> dict[str, object]:
        return {
            "title": self.title,
            "direct_ssh": self.direct_ssh,
            "ssh_compression": self.ssh_compression,
            "ssh_browser": self.ssh_browser,
            "x11_forwarding": self.x11_forwarding,
            "lines": self.lines(),
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
class MobaConnectedSessionState:
    profile_name: str
    target: str
    remote_path: str
    follow_terminal_folder: bool
    file_entries: tuple[RemoteFileEntry, ...]
    sftp_list_plan: SftpBatchPlan
    follow_folder_plan: SftpBatchPlan
    monitoring_plan: RemoteMonitoringPlan
    monitoring: RemoteMonitoringSnapshot
    banner: SshConnectionBanner

    def to_dict(self) -> dict[str, object]:
        return {
            "profile_name": self.profile_name,
            "target": self.target,
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
            "banner": self.banner.to_dict(),
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
        remote_path=selected_path,
        follow_terminal_folder=follow_terminal_folder,
        file_entries=entries,
        sftp_list_plan=build_sftp_list_plan(profile, selected_path),
        follow_folder_plan=build_follow_terminal_folder_plan(profile, selected_path),
        monitoring_plan=build_remote_monitoring_plan(profile),
        monitoring=parse_remote_monitoring_output(monitoring_output) or default_remote_monitoring_snapshot(profile),
        banner=build_ssh_connection_banner(profile),
    )


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
        title=profile.display_target,
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


def _require_ssh_browser_profile(profile: Profile) -> None:
    if profile.protocol.lower() not in {"ssh", "sftp"}:
        raise ValueError(f"Moba connected-session workspace requires an SSH/SFTP profile: {profile.name}")

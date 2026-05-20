from __future__ import annotations

import os
import platform
import shlex
import shutil
import subprocess
import sys
from dataclasses import dataclass
from typing import Iterable

from .models import Profile, Tunnel


@dataclass(slots=True)
class LaunchPlan:
    protocol: str
    command: list[str]
    notes: list[str]

    def printable(self) -> str:
        return " ".join(shlex.quote(part) for part in self.command)


class LauncherError(RuntimeError):
    pass


DEFAULT_PORTS: dict[str, int] = {
    "ssh": 22,
    "sftp": 22,
    "scp": 22,
    "mosh": 22,
    "telnet": 23,
    "rlogin": 513,
    "rsh": 514,
    "ftp": 21,
    "rdp": 3389,
    "vnc": 5900,
    "spice": 5900,
    "x2go": 22,
    "xdmcp": 177,
    "ica": 1494,
    "http": 80,
    "https": 443,
    "raw": 0,
    "serial": 0,
    "local-shell": 0,
}


def build_launch_plan(profile: Profile) -> LaunchPlan:
    protocol = profile.protocol.lower().strip()
    notes: list[str] = []

    if protocol in {"ssh", "sftp", "scp"}:
        return _build_ssh_family(profile, protocol)
    if protocol == "mosh":
        return _build_mosh(profile)
    if protocol == "rdp":
        return _build_rdp(profile)
    if protocol == "vnc":
        return _build_vnc(profile)
    if protocol == "spice":
        return _build_spice(profile)
    if protocol == "x2go":
        return _build_x2go(profile)
    if protocol == "xdmcp":
        return _build_xdmcp(profile)
    if protocol == "ica":
        return _build_ica(profile)
    if protocol in {"telnet", "rlogin", "rsh", "ftp"}:
        port = profile.port or DEFAULT_PORTS[protocol]
        target = _host(profile)
        return LaunchPlan(protocol, [protocol, target, str(port)], notes)
    if protocol in {"http", "https", "www"}:
        return _build_url(profile, protocol)
    if protocol == "raw":
        executable = _first_available(["nc", "ncat", "netcat"])
        if not executable:
            executable = "nc"
            notes.append("Install nc/ncat/netcat for raw socket profiles.")
        return LaunchPlan(protocol, [executable, _host(profile), str(profile.port or 0)], notes)
    if protocol == "serial":
        return _build_serial(profile)
    if protocol in {"local", "local-shell", "shell"}:
        shell = os.environ.get("SHELL") or os.environ.get("COMSPEC") or ("cmd.exe" if _is_windows() else "/bin/sh")
        return LaunchPlan("local-shell", [shell], notes)
    if protocol == "custom":
        if not profile.command:
            raise LauncherError("custom profile requires command")
        return LaunchPlan(protocol, shlex.split(profile.command), ["Custom command profile."])

    raise LauncherError(f"unsupported protocol: {protocol}")


def launch(profile: Profile, dry_run: bool = False) -> LaunchPlan:
    plan = build_launch_plan(profile)
    if dry_run:
        return plan
    subprocess.Popen(plan.command)  # noqa: S603 - command is built as an argv list, not shell=True
    return plan


def protocol_clients() -> dict[str, list[str]]:
    return {
        "ssh": ["ssh"],
        "sftp": ["sftp"],
        "scp": ["scp"],
        "mosh": ["mosh"],
        "rdp": ["mstsc", "xfreerdp", "wlfreerdp"],
        "vnc": ["vncviewer", "tigervnc", "realvnc-vnc-viewer"],
        "spice": ["remote-viewer", "virt-viewer"],
        "x2go": ["x2goclient"],
        "xdmcp": ["Xorg", "Xquartz", "vcxsrv", "xnest"],
        "ica": ["wfica"],
        "telnet": ["telnet"],
        "rlogin": ["rlogin"],
        "rsh": ["rsh"],
        "ftp": ["ftp", "lftp"],
        "raw": ["nc", "ncat", "netcat"],
        "serial": ["screen", "cu", "putty"],
    }


def _build_ssh_family(profile: Profile, protocol: str) -> LaunchPlan:
    host = _host(profile)
    port = profile.port or DEFAULT_PORTS[protocol]
    target = f"{profile.username}@{host}" if profile.username else host
    notes: list[str] = []

    if protocol == "ssh":
        cmd = ["ssh", "-p", str(port)]
        if profile.identity_file:
            cmd.extend(["-i", profile.identity_file])
        cmd.extend(_ssh_tunnel_args(profile.tunnels))
        if profile.options.get("x11", "").lower() in {"1", "true", "yes", "trusted"}:
            cmd.append("-Y" if profile.options.get("x11") == "trusted" else "-X")
            notes.append("X11 forwarding requested. Ensure XQuartz, Xorg or VcXsrv is running locally.")
        if profile.options.get("agent_forward", "").lower() in {"1", "true", "yes"}:
            cmd.append("-A")
        cmd.append(target)
        return LaunchPlan(protocol, cmd, notes)

    if protocol == "sftp":
        cmd = ["sftp", "-P", str(port)]
        if profile.identity_file:
            cmd.extend(["-i", profile.identity_file])
        cmd.append(target)
        return LaunchPlan(protocol, cmd, notes)

    cmd = ["scp", "-P", str(port)]
    if profile.identity_file:
        cmd.extend(["-i", profile.identity_file])
    cmd.append(target)
    return LaunchPlan(protocol, cmd, ["SCP profile needs source/destination arguments for real transfer."])


def _ssh_tunnel_args(tunnels: Iterable[Tunnel]) -> list[str]:
    args: list[str] = []
    for tunnel in tunnels:
        mode = tunnel.mode.lower()
        if mode == "local":
            args.extend(["-L", f"{tunnel.local_host}:{tunnel.local_port}:{tunnel.remote_host}:{tunnel.remote_port}"])
        elif mode == "remote":
            args.extend(["-R", f"{tunnel.local_host}:{tunnel.local_port}:{tunnel.remote_host}:{tunnel.remote_port}"])
        elif mode == "dynamic":
            args.extend(["-D", f"{tunnel.local_host}:{tunnel.local_port}"])
    return args


def _build_mosh(profile: Profile) -> LaunchPlan:
    host = _host(profile)
    port = profile.port or DEFAULT_PORTS["mosh"]
    target = f"{profile.username}@{host}" if profile.username else host
    return LaunchPlan("mosh", ["mosh", "--ssh", f"ssh -p {port}", target], [])


def _build_rdp(profile: Profile) -> LaunchPlan:
    host = _host(profile)
    port = profile.port or DEFAULT_PORTS["rdp"]
    notes: list[str] = []
    if _is_windows():
        return LaunchPlan("rdp", ["mstsc", f"/v:{host}:{port}"], ["Uses Windows MSTSC."])
    executable = _first_available(["xfreerdp", "wlfreerdp"]) or "xfreerdp"
    cmd = [executable, f"/v:{host}:{port}"]
    if profile.username:
        cmd.append(f"/u:{profile.username}")
    if profile.options.get("dynamic_resolution", "true").lower() in {"1", "true", "yes"}:
        cmd.append("/dynamic-resolution")
    notes.append("Install FreeRDP for non-Windows RDP sessions.")
    return LaunchPlan("rdp", cmd, notes)


def _build_vnc(profile: Profile) -> LaunchPlan:
    host = _host(profile)
    port = profile.port or DEFAULT_PORTS["vnc"]
    executable = _first_available(["vncviewer", "tigervnc", "realvnc-vnc-viewer"]) or "vncviewer"
    return LaunchPlan("vnc", [executable, f"{host}:{port}"], [])


def _build_spice(profile: Profile) -> LaunchPlan:
    host = _host(profile)
    port = profile.port or DEFAULT_PORTS["spice"]
    executable = _first_available(["remote-viewer", "virt-viewer"]) or "remote-viewer"
    return LaunchPlan("spice", [executable, f"spice://{host}:{port}"], ["Install virt-viewer for SPICE sessions."])


def _build_x2go(profile: Profile) -> LaunchPlan:
    cmd = ["x2goclient"]
    if profile.host:
        cmd.extend(["--server", profile.host])
    if profile.username:
        cmd.extend(["--user", profile.username])
    if profile.port:
        cmd.extend(["--ssh-port", str(profile.port)])
    return LaunchPlan("x2go", cmd, ["Install x2goclient for X2Go sessions."])


def _build_xdmcp(profile: Profile) -> LaunchPlan:
    host = _host(profile)
    executable = _first_available(["xnest", "Xorg", "Xquartz"]) or "xnest"
    return LaunchPlan("xdmcp", [executable, "-query", host], ["XDMCP requires a local X server and a remote XDMCP service."])


def _build_ica(profile: Profile) -> LaunchPlan:
    target = profile.path or profile.url or _host(profile)
    return LaunchPlan("ica", ["wfica", target], ["Requires Citrix Workspace/Receiver command-line client."])


def _build_url(profile: Profile, protocol: str) -> LaunchPlan:
    url = profile.url
    if not url:
        host = _host(profile)
        scheme = "http" if protocol in {"http", "www"} else "https"
        port = profile.port or DEFAULT_PORTS[scheme]
        url = f"{scheme}://{host}:{port}"
    if _is_windows():
        return LaunchPlan(protocol, ["cmd", "/c", "start", "", url], ["Opens default browser."])
    if sys.platform == "darwin":
        return LaunchPlan(protocol, ["open", url], ["Opens default browser."])
    return LaunchPlan(protocol, ["xdg-open", url], ["Opens default browser."])


def _build_serial(profile: Profile) -> LaunchPlan:
    path = profile.path or profile.options.get("device")
    if not path:
        raise LauncherError("serial profile requires --path or option device=...")
    baud = profile.options.get("baud", "115200")
    if _is_windows():
        return LaunchPlan("serial", ["putty", "-serial", path, "-sercfg", f"{baud},8,n,1,N"], ["Install PuTTY for serial sessions on Windows."])
    executable = _first_available(["screen", "cu"]) or "screen"
    if executable == "cu":
        return LaunchPlan("serial", ["cu", "-l", path, "-s", baud], [])
    return LaunchPlan("serial", ["screen", path, baud], [])


def _host(profile: Profile) -> str:
    if not profile.host:
        raise LauncherError(f"{profile.protocol} profile requires host")
    return profile.host


def _first_available(candidates: list[str]) -> str | None:
    for candidate in candidates:
        if shutil.which(candidate):
            return candidate
    return None


def _is_windows() -> bool:
    return platform.system().lower() == "windows"

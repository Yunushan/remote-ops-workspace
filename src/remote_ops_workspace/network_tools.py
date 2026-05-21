from __future__ import annotations

import platform
import socket
import subprocess
from dataclasses import dataclass

from . import command_safety as safe


@dataclass(slots=True)
class NetworkToolPlan:
    command: list[str]

    def printable(self) -> str:
        return " ".join(safe.argv_list(self.command, "network tool command"))


def build_network_tool_plan(tool: str, target: str, count: int = 4) -> NetworkToolPlan:
    normalized = tool.lower()
    system = platform.system().lower()
    target = safe.host(target, "network target")
    if normalized == "ping":
        if count < 1:
            raise ValueError("ping count must be greater than zero")
        flag = "-n" if system == "windows" else "-c"
        return NetworkToolPlan(["ping", flag, str(count), target])
    if normalized in {"trace", "traceroute"}:
        executable = "tracert" if system == "windows" else "traceroute"
        return NetworkToolPlan([executable, target])
    if normalized in {"dns", "lookup", "nslookup"}:
        return NetworkToolPlan(["nslookup", target])
    if normalized == "whois":
        return NetworkToolPlan(["whois", target])
    raise ValueError(f"unsupported network tool: {tool}")


def run_network_tool(plan: NetworkToolPlan, dry_run: bool = False) -> NetworkToolPlan:
    if not dry_run:
        safe.argv_list(plan.command, "network tool command")
        subprocess.run(plan.command, check=True)  # noqa: S603 - argv list, no shell
    return plan


def check_tcp_port(host: str, port: int, timeout: float = 3.0) -> bool:
    host = safe.host(host, "tcp host")
    port = safe.port(port, "tcp port")
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(timeout)
        return sock.connect_ex((host, port)) == 0

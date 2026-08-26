from __future__ import annotations

from typing import Any

import pytest

from remote_ops_workspace import network_tools
from remote_ops_workspace.network_tools import NetworkToolPlan


@pytest.mark.parametrize(
    ("system", "tool", "count", "expected"),
    [
        ("Windows", "PING", 2, ["ping", "-n", "2", "example.com"]),
        ("Linux", "ping", 3, ["ping", "-c", "3", "example.com"]),
        ("Windows", "trace", 4, ["tracert", "example.com"]),
        ("Darwin", "traceroute", 4, ["traceroute", "example.com"]),
        ("Linux", "dns", 4, ["nslookup", "example.com"]),
        ("Linux", "lookup", 4, ["nslookup", "example.com"]),
        ("Linux", "nslookup", 4, ["nslookup", "example.com"]),
        ("Linux", "whois", 4, ["whois", "example.com"]),
    ],
)
def test_network_tool_plan_covers_supported_tools(
    monkeypatch: pytest.MonkeyPatch,
    system: str,
    tool: str,
    count: int,
    expected: list[str],
) -> None:
    monkeypatch.setattr(network_tools.platform, "system", lambda: system)

    plan = network_tools.build_network_tool_plan(tool, "example.com", count=count)

    assert plan.command == expected
    assert plan.printable() == " ".join(expected)


def test_network_tool_plan_rejects_invalid_count_and_unknown_tool() -> None:
    with pytest.raises(ValueError, match="ping count must be greater than zero"):
        network_tools.build_network_tool_plan("ping", "example.com", count=0)
    with pytest.raises(ValueError, match="unsupported network tool: netcat"):
        network_tools.build_network_tool_plan("netcat", "example.com")


def test_run_network_tool_honors_dry_run_and_uses_checked_argv(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], bool]] = []
    monkeypatch.setattr(
        network_tools.subprocess,
        "run",
        lambda command, *, check: calls.append((command, check)),
    )
    plan = NetworkToolPlan(["ping", "-c", "1", "example.com"])

    assert network_tools.run_network_tool(plan, dry_run=True) is plan
    assert calls == []
    assert network_tools.run_network_tool(plan) is plan
    assert calls == [(plan.command, True)]


@pytest.mark.parametrize(("connect_result", "expected"), [(0, True), (10061, False)])
def test_check_tcp_port_configures_socket_and_reports_connect_result(
    monkeypatch: pytest.MonkeyPatch,
    connect_result: int,
    expected: bool,
) -> None:
    class FakeSocket:
        def __init__(self) -> None:
            self.timeout: float | None = None
            self.address: tuple[str, int] | None = None

        def __enter__(self) -> FakeSocket:
            return self

        def __exit__(self, *_args: Any) -> None:
            return None

        def settimeout(self, timeout: float) -> None:
            self.timeout = timeout

        def connect_ex(self, address: tuple[str, int]) -> int:
            self.address = address
            return connect_result

    fake_socket = FakeSocket()
    monkeypatch.setattr(network_tools.socket, "socket", lambda *_args: fake_socket)

    assert network_tools.check_tcp_port("127.0.0.1", 443, timeout=1.25) is expected
    assert fake_socket.timeout == 1.25
    assert fake_socket.address == ("127.0.0.1", 443)


from remote_ops_workspace.launcher import build_launch_plan
from remote_ops_workspace.models import Profile, Tunnel


def test_ssh_command_builder() -> None:
    profile = Profile(name="lab", protocol="ssh", host="192.0.2.10", port=2222, username="admin")
    plan = build_launch_plan(profile)
    assert plan.command == ["ssh", "-p", "2222", "admin@192.0.2.10"]


def test_ssh_tunnel_builder() -> None:
    profile = Profile(
        name="tunnel",
        protocol="ssh",
        host="192.0.2.10",
        username="admin",
        tunnels=[Tunnel(mode="local", local_port=15432, remote_host="127.0.0.1", remote_port=5432)],
    )
    plan = build_launch_plan(profile)
    assert "-L" in plan.command
    assert "127.0.0.1:15432:127.0.0.1:5432" in plan.command


def test_rdp_command_builder_is_safe_list() -> None:
    profile = Profile(name="win", protocol="rdp", host="192.0.2.20", username="administrator")
    plan = build_launch_plan(profile)
    assert isinstance(plan.command, list)
    assert any("192.0.2.20" in part for part in plan.command)


def test_https_command_builder() -> None:
    profile = Profile(name="web", protocol="https", url="https://example.com")
    plan = build_launch_plan(profile)
    assert "https://example.com" in plan.command

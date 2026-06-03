from remote_ops_workspace.launcher import LauncherError, build_launch_plan
from remote_ops_workspace.models import Profile, Tunnel


def test_ssh_command_builder() -> None:
    profile = Profile(name="lab", protocol="ssh", host="192.0.2.10", port=2222, username="admin")
    plan = build_launch_plan(profile)
    assert plan.command == ["ssh", "-p", "2222", "admin@192.0.2.10"]


def test_sshv1_requires_explicit_insecure_opt_in() -> None:
    profile = Profile(name="legacy", protocol="ssh1", host="192.0.2.10", username="admin")
    try:
        build_launch_plan(profile)
    except LauncherError as exc:
        assert "allow_insecure_sshv1=true" in str(exc)
    else:
        raise AssertionError("SSHv1 launch should require explicit insecure opt-in")


def test_sshv1_command_builder_is_explicit_legacy_mode() -> None:
    profile = Profile(
        name="legacy",
        protocol="ssh1",
        host="192.0.2.10",
        username="admin",
        options={"allow_insecure_sshv1": "true"},
    )
    plan = build_launch_plan(profile)
    assert plan.command == ["ssh", "-1", "-p", "22", "admin@192.0.2.10"]
    assert any("allow_insecure_sshv1=true" in note for note in plan.notes)
    assert any("protocol v1 cannot provide modern SSH security" in note for note in plan.notes)


def test_sshv1_alias_command_builder() -> None:
    profile = Profile(
        name="legacy",
        protocol="sshv1",
        host="192.0.2.10",
        options={"allow_unsafe_sshv1": "yes"},
    )
    plan = build_launch_plan(profile)
    assert plan.command[:3] == ["ssh", "-1", "-p"]


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

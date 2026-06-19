import pytest

from remote_ops_workspace.moba_multiexec import build_moba_multiexec_plan
from remote_ops_workspace.models import Profile


def test_moba_multiexec_plan_builds_broadcast_commands_for_ssh_profiles() -> None:
    plan = build_moba_multiexec_plan(
        [
            Profile(name="edge-a", protocol="ssh", host="192.0.2.10", username="admin"),
            Profile(name="edge-b", protocol="ssh", host="192.0.2.11", username="admin"),
        ],
        "hostname",
    )

    assert plan.command == "hostname"
    assert plan.profiles == ("edge-a", "edge-b")
    assert plan.profile_count == 2
    assert [broadcast.command[-1] for broadcast in plan.broadcast_plans] == ["hostname", "hostname"]
    assert plan.broadcast_plans[0].command[-2:] == ["admin@192.0.2.10", "hostname"]
    assert plan.route.key == "moba-multiexec-broadcast-route"
    assert plan.route.ribbon_action_key == "multiexec"
    assert plan.route.handler == "show_moba_multiexec_status"
    assert plan.route.profile_names == ("edge-a", "edge-b")
    assert plan.route.profile_count == 2
    assert plan.route.broadcast_commands[0][-1] == "hostname"
    assert "ssh -p 22 admin@192.0.2.10 hostname" in plan.route.command_preview[0]
    assert plan.to_dict()["route"]["route_role"] == "ribbon-multiexec-to-ssh-broadcast"


def test_moba_multiexec_plan_requires_ssh_profiles() -> None:
    with pytest.raises(ValueError, match="broadcast currently supports ssh profiles"):
        build_moba_multiexec_plan([Profile(name="files", protocol="sftp", host="192.0.2.10")], "hostname")


def test_moba_multiexec_plan_rejects_empty_profile_list() -> None:
    with pytest.raises(ValueError, match="at least one SSH profile"):
        build_moba_multiexec_plan([], "hostname")


def test_moba_multiexec_plan_rejects_multiline_commands() -> None:
    with pytest.raises(ValueError, match="control characters|single line"):
        build_moba_multiexec_plan([Profile(name="edge", protocol="ssh", host="192.0.2.10")], "hostname\nwhoami")

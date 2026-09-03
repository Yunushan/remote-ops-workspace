from row_demo_plugin.plugin import Plugin
from remote_ops_workspace.launcher import LaunchPlan
from remote_ops_workspace.models import Profile


def test_plugin_builds_launch_plan() -> None:
    plugin = Plugin()
    plan = plugin.build(Profile(name="sample", protocol="demo", host="plugin.example"))

    assert isinstance(plan, LaunchPlan)
    assert plan.protocol == "demo"
    assert plan.command == ["demo-client", "plugin.example"]

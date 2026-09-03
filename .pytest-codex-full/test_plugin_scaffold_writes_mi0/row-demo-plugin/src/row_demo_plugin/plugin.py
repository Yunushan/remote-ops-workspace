from __future__ import annotations

from remote_ops_workspace.launcher import LaunchPlan
from remote_ops_workspace.models import Profile


class Plugin:
    name = "demo protocol plugin"
    protocols = ("demo",)
    executables = ("demo-client",)

    def build(self, profile: Profile) -> LaunchPlan:
        target = profile.host or profile.url or profile.path or profile.name
        command = ["demo-client", str(target)]
        if profile.username:
            command.extend(["--user", profile.username])
        if profile.port:
            command.extend(["--port", str(profile.port)])
        return LaunchPlan(profile.protocol, command, ["Built by demo protocol plugin."])

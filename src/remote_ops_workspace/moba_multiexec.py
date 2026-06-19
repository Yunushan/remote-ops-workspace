from __future__ import annotations

import shlex
from dataclasses import dataclass

from .broadcast import BroadcastPlan, build_broadcast_plans
from .models import Profile

DEFAULT_MOBA_MULTIEXEC_COMMAND = "hostname"


@dataclass(frozen=True, slots=True)
class MobaMultiExecRoute:
    key: str
    route_role: str
    ribbon_action_key: str
    ribbon_action_label: str
    action_object: str
    handler: str
    command: str
    target_protocol: str
    profile_names: tuple[str, ...]
    profile_count: int
    broadcast_commands: tuple[tuple[str, ...], ...]
    command_preview: tuple[str, ...]
    render_source: str

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "route_role": self.route_role,
            "ribbon_action_key": self.ribbon_action_key,
            "ribbon_action_label": self.ribbon_action_label,
            "action_object": self.action_object,
            "handler": self.handler,
            "command": self.command,
            "target_protocol": self.target_protocol,
            "profile_names": list(self.profile_names),
            "profile_count": self.profile_count,
            "broadcast_commands": [list(command) for command in self.broadcast_commands],
            "command_preview": list(self.command_preview),
            "render_source": self.render_source,
        }


@dataclass(frozen=True, slots=True)
class MobaMultiExecPlan:
    command: str
    profiles: tuple[str, ...]
    broadcast_plans: tuple[BroadcastPlan, ...]
    route: MobaMultiExecRoute

    @property
    def profile_count(self) -> int:
        return len(self.profiles)

    def printable_commands(self) -> tuple[str, ...]:
        return tuple(shlex.join(plan.command) for plan in self.broadcast_plans)

    def to_dict(self) -> dict[str, object]:
        return {
            "command": self.command,
            "profiles": list(self.profiles),
            "profile_count": self.profile_count,
            "broadcast_plans": [
                {
                    "profile": plan.profile_name,
                    "command": plan.command,
                    "printable": shlex.join(plan.command),
                    "notes": plan.notes,
                }
                for plan in self.broadcast_plans
            ],
            "route": self.route.to_dict(),
        }


def build_moba_multiexec_plan(
    profiles: list[Profile],
    command: str = DEFAULT_MOBA_MULTIEXEC_COMMAND,
) -> MobaMultiExecPlan:
    if not profiles:
        raise ValueError("Moba MultiExec requires at least one SSH profile")
    broadcast_plans = tuple(build_broadcast_plans(profiles, command))
    profile_names = tuple(plan.profile_name for plan in broadcast_plans)
    broadcast_commands = tuple(tuple(plan.command) for plan in broadcast_plans)
    route = MobaMultiExecRoute(
        key="moba-multiexec-broadcast-route",
        route_role="ribbon-multiexec-to-ssh-broadcast",
        ribbon_action_key="multiexec",
        ribbon_action_label="MultiExec",
        action_object="mobaRibbonButton",
        handler="show_moba_multiexec_status",
        command=command,
        target_protocol="ssh",
        profile_names=profile_names,
        profile_count=len(profile_names),
        broadcast_commands=broadcast_commands,
        command_preview=tuple(shlex.join(plan.command) for plan in broadcast_plans),
        render_source="broadcast.build_broadcast_plans",
    )
    return MobaMultiExecPlan(
        command=command,
        profiles=profile_names,
        broadcast_plans=broadcast_plans,
        route=route,
    )

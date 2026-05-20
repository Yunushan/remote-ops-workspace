from __future__ import annotations

from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import Protocol

from .models import Profile
from .launcher import LaunchPlan


class ProtocolPlugin(Protocol):
    name: str
    protocols: tuple[str, ...]

    def build(self, profile: Profile) -> LaunchPlan:
        ...


@dataclass(slots=True)
class LoadedPlugin:
    name: str
    protocols: tuple[str, ...]
    object: ProtocolPlugin


def load_plugins() -> list[LoadedPlugin]:
    loaded: list[LoadedPlugin] = []
    eps = entry_points()
    for ep in eps.select(group="remote_ops_workspace.plugins"):
        plugin = ep.load()
        instance = plugin() if isinstance(plugin, type) else plugin
        loaded.append(
            LoadedPlugin(
                name=getattr(instance, "name", ep.name),
                protocols=tuple(getattr(instance, "protocols", ())),
                object=instance,
            )
        )
    return loaded

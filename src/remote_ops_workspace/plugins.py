from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import TYPE_CHECKING, Any, Protocol

from .models import Profile
from .profile_validation import SUPPORTED_PROFILE_PROTOCOLS

if TYPE_CHECKING:
    from .launcher import LaunchPlan


class ProtocolPlugin(Protocol):
    name: str
    protocols: tuple[str, ...]
    executables: tuple[str, ...]

    def build(self, profile: Profile) -> LaunchPlan:
        ...


@dataclass(slots=True)
class LoadedPlugin:
    name: str
    protocols: tuple[str, ...]
    executables: tuple[str, ...]
    object: ProtocolPlugin
    entry_point: str

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "protocols": list(self.protocols),
            "executables": list(self.executables),
            "entry_point": self.entry_point,
        }


@dataclass(slots=True)
class PluginLoadFailure:
    name: str
    entry_point: str
    error: str

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "entry_point": self.entry_point,
            "error": self.error,
        }


@dataclass(slots=True)
class PluginRegistry:
    loaded: list[LoadedPlugin]
    failures: list[PluginLoadFailure]

    @property
    def protocols(self) -> set[str]:
        return {protocol for plugin in self.loaded for protocol in plugin.protocols}

    def plugin_for_protocol(self, protocol: str) -> LoadedPlugin | None:
        normalized = protocol.strip().lower()
        for plugin in self.loaded:
            if normalized in plugin.protocols:
                return plugin
        return None

    def protocol_clients(self) -> dict[str, list[str]]:
        clients: dict[str, list[str]] = {}
        for plugin in self.loaded:
            for protocol in plugin.protocols:
                clients.setdefault(protocol, [])
                for executable in plugin.executables:
                    if executable not in clients[protocol]:
                        clients[protocol].append(executable)
        return clients

    def to_dict(self) -> dict[str, object]:
        return {
            "loaded": [plugin.to_dict() for plugin in self.loaded],
            "failures": [failure.to_dict() for failure in self.failures],
        }


EntryPointsProvider = Callable[[], Any]


def load_plugin_registry(*, entry_points_provider: EntryPointsProvider | None = None) -> PluginRegistry:
    loaded: list[LoadedPlugin] = []
    failures: list[PluginLoadFailure] = []
    eps = (entry_points_provider or entry_points)()
    for ep in eps.select(group="remote_ops_workspace.plugins"):
        try:
            plugin = ep.load()
            instance = plugin() if isinstance(plugin, type) else plugin
            protocols = normalize_plugin_protocols(getattr(instance, "protocols", ()))
            if not protocols:
                raise ValueError("plugin must declare at least one protocol")
            plugin_name = str(getattr(instance, "name", ep.name)).strip()
            if not plugin_name:
                raise ValueError("plugin name must not be empty")
            if not callable(getattr(instance, "build", None)):
                raise ValueError("plugin must implement build(profile) -> LaunchPlan")
            collisions = sorted(set(protocols) & SUPPORTED_PROFILE_PROTOCOLS)
            if collisions:
                raise ValueError(
                    "plugin protocol collides with built-in protocol: " + ", ".join(collisions)
                )
            loaded.append(
                LoadedPlugin(
                    name=plugin_name,
                    protocols=protocols,
                    executables=normalize_plugin_executables(getattr(instance, "executables", ())),
                    object=instance,
                    entry_point=f"{ep.module}:{ep.attr}" if getattr(ep, "attr", None) else str(ep),
                )
            )
        except Exception as exc:  # pragma: no cover - exercised through direct tests with fake entry points
            failures.append(
                PluginLoadFailure(
                    name=str(getattr(ep, "name", "unknown")),
                    entry_point=str(ep),
                    error=str(exc),
                )
            )
    return PluginRegistry(loaded=loaded, failures=failures)


def load_plugins() -> list[LoadedPlugin]:
    return load_plugin_registry().loaded


def plugin_protocols() -> set[str]:
    return load_plugin_registry().protocols


def plugin_clients() -> dict[str, list[str]]:
    return load_plugin_registry().protocol_clients()


def normalize_plugin_protocols(values: object) -> tuple[str, ...]:
    if isinstance(values, str):
        raw_values = (values,)
    else:
        raw_values = tuple(values or ())  # type: ignore[arg-type]
    result: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        protocol = str(value).strip().lower()
        if not protocol:
            continue
        if any(char.isspace() for char in protocol):
            raise ValueError("plugin protocol must not contain whitespace")
        if protocol.startswith("-"):
            raise ValueError("plugin protocol must not start with '-'")
        if protocol not in seen:
            seen.add(protocol)
            result.append(protocol)
    return tuple(result)


def normalize_plugin_executables(values: object) -> tuple[str, ...]:
    if isinstance(values, str):
        raw_values = (values,)
    else:
        raw_values = tuple(values or ())  # type: ignore[arg-type]
    result: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        executable = str(value).strip()
        if not executable or executable in seen:
            continue
        seen.add(executable)
        result.append(executable)
    return tuple(result)

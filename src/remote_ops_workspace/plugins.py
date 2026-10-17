from __future__ import annotations

import builtins
import os
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from importlib.metadata import entry_points
from typing import TYPE_CHECKING, Any, Protocol

from .models import Profile
from .profile_validation import SUPPORTED_PROFILE_PROTOCOLS

if TYPE_CHECKING:
    from .launcher import LaunchPlan

PLUGIN_ENTRY_POINT_GROUP = "remote_ops_workspace.plugins"
PLUGIN_ENABLE_ENV = "ROW_ENABLE_PLUGINS"
PLUGIN_ALLOWLIST_ENV = "ROW_PLUGIN_ALLOWLIST"
_TRUTHY_ENV_VALUES = frozenset({"1", "true", "yes", "on"})


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

    def to_dict(self) -> dict[str, builtins.object]:
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


def plugins_enabled_from_environment() -> bool:
    """Third-party plugin code loads only after an explicit opt-in (default off)."""
    return os.environ.get(PLUGIN_ENABLE_ENV, "").strip().lower() in _TRUTHY_ENV_VALUES


def plugin_allowlist_from_environment() -> frozenset[str] | None:
    """Optional comma-separated entry-point names that may load; empty means all."""
    raw = os.environ.get(PLUGIN_ALLOWLIST_ENV, "").strip()
    if not raw:
        return None
    return frozenset(part.strip().lower() for part in raw.split(",") if part.strip())


def load_plugin_registry(
    *,
    entry_points_provider: EntryPointsProvider | None = None,
    allow_plugins: bool | None = None,
) -> PluginRegistry:
    if allow_plugins is None:
        allow_plugins = entry_points_provider is not None or plugins_enabled_from_environment()
    if not allow_plugins:
        return PluginRegistry(
            loaded=[],
            failures=[
                PluginLoadFailure(
                    name="plugins-disabled",
                    entry_point=PLUGIN_ENTRY_POINT_GROUP,
                    error=(
                        "third-party plugin loading is disabled by default; "
                        f"set {PLUGIN_ENABLE_ENV}=1 to opt in"
                    ),
                )
            ],
        )
    allowlist = plugin_allowlist_from_environment()
    loaded: list[LoadedPlugin] = []
    failures: list[PluginLoadFailure] = []
    try:
        eps = (entry_points_provider or entry_points)()
        selected = eps.select(group=PLUGIN_ENTRY_POINT_GROUP)
    except Exception as exc:
        failures.append(
            PluginLoadFailure(
                name="entry-point-discovery",
                entry_point=PLUGIN_ENTRY_POINT_GROUP,
                error=str(exc),
            )
        )
        return PluginRegistry(loaded=loaded, failures=failures)
    for ep in selected:
        if allowlist is not None and str(getattr(ep, "name", "")).lower() not in allowlist:
            continue
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
    raw_values = _plugin_values(values, "protocols")
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
    raw_values = _plugin_values(values, "executables")
    result: list[str] = []
    seen: set[str] = set()
    for value in raw_values:
        executable = str(value).strip()
        if not executable or executable in seen:
            continue
        seen.add(executable)
        result.append(executable)
    return tuple(result)


def _plugin_values(values: object, label: str) -> tuple[object, ...]:
    if isinstance(values, str):
        return (values,)
    if values is None:
        return ()
    if not isinstance(values, Iterable):
        raise TypeError(f"plugin {label} must be a string or iterable")
    return tuple(values)

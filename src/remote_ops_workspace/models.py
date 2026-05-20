from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(slots=True)
class Tunnel:
    """SSH tunnel or port-forwarding rule."""

    mode: str  # local, remote, dynamic
    local_host: str = "127.0.0.1"
    local_port: int | None = None
    remote_host: str | None = None
    remote_port: int | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Tunnel":
        return cls(
            mode=str(data.get("mode", "local")),
            local_host=str(data.get("local_host", "127.0.0.1")),
            local_port=_optional_int(data.get("local_port")),
            remote_host=_optional_str(data.get("remote_host")),
            remote_port=_optional_int(data.get("remote_port")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "local_host": self.local_host,
            "local_port": self.local_port,
            "remote_host": self.remote_host,
            "remote_port": self.remote_port,
        }


@dataclass(slots=True)
class Profile:
    """A connection profile.

    The model deliberately supports protocol-specific options without hard-coding every
    vendor behavior. New protocol engines can use `options` without schema churn.
    """

    name: str
    protocol: str
    host: str | None = None
    port: int | None = None
    username: str | None = None
    group: str = "default"
    tags: list[str] = field(default_factory=list)
    description: str = ""
    path: str | None = None
    url: str | None = None
    command: str | None = None
    credential_ref: str | None = None
    identity_file: str | None = None
    tunnels: list[Tunnel] = field(default_factory=list)
    options: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Profile":
        raw_options = data.get("options") or {}
        if not isinstance(raw_options, dict):
            raw_options = {}
        return cls(
            name=str(data["name"]),
            protocol=str(data["protocol"]).lower(),
            host=_optional_str(data.get("host")),
            port=_optional_int(data.get("port")),
            username=_optional_str(data.get("username")),
            group=str(data.get("group", "default")),
            tags=[str(x) for x in data.get("tags", [])],
            description=str(data.get("description", "")),
            path=_optional_str(data.get("path")),
            url=_optional_str(data.get("url")),
            command=_optional_str(data.get("command")),
            credential_ref=_optional_str(data.get("credential_ref")),
            identity_file=_optional_str(data.get("identity_file")),
            tunnels=[Tunnel.from_dict(x) for x in data.get("tunnels", [])],
            options={str(k): str(v) for k, v in raw_options.items()},
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "protocol": self.protocol,
            "host": self.host,
            "port": self.port,
            "username": self.username,
            "group": self.group,
            "tags": self.tags,
            "description": self.description,
            "path": self.path,
            "url": self.url,
            "command": self.command,
            "credential_ref": self.credential_ref,
            "identity_file": self.identity_file,
            "tunnels": [x.to_dict() for x in self.tunnels],
            "options": self.options,
        }

    @property
    def display_target(self) -> str:
        if self.url:
            return self.url
        if self.path:
            return self.path
        if self.host and self.port:
            return f"{self.host}:{self.port}"
        return self.host or self.command or "local"


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value)
    return value if value else None


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)

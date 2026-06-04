from __future__ import annotations

from collections.abc import Mapping

from . import command_safety as safe
from .layouts import Layout, LayoutPane, parse_layout_pane, validate_layout
from .models import Profile, Tunnel
from .plugins import plugin_protocols
from .profile_validation import prepare_profile

PROFILE_EDITOR_FIELDS = {
    "command",
    "credential_ref",
    "description",
    "group",
    "host",
    "identity_file",
    "name",
    "options",
    "path",
    "port",
    "protocol",
    "tags",
    "tunnels",
    "url",
    "username",
}


def profile_to_editor_data(profile: Profile | None = None) -> dict[str, str]:
    if profile is None:
        return {
            "name": "",
            "protocol": "ssh",
            "host": "",
            "port": "",
            "username": "",
            "group": "default",
            "tags": "",
            "description": "",
            "path": "",
            "url": "",
            "command": "",
            "identity_file": "",
            "credential_ref": "",
            "options": "",
            "tunnels": "",
        }
    return {
        "name": profile.name,
        "protocol": profile.protocol,
        "host": profile.host or "",
        "port": str(profile.port) if profile.port is not None else "",
        "username": profile.username or "",
        "group": profile.group,
        "tags": ", ".join(profile.tags),
        "description": profile.description,
        "path": profile.path or "",
        "url": profile.url or "",
        "command": profile.command or "",
        "identity_file": profile.identity_file or "",
        "credential_ref": profile.credential_ref or "",
        "options": format_key_value_text(profile.options),
        "tunnels": format_tunnels_text(profile.tunnels),
    }


def profile_from_editor_data(data: Mapping[str, str]) -> Profile:
    name = _required(data.get("name"), "profile name")
    protocol = _required(data.get("protocol"), "protocol").lower()
    port = _optional_port(data.get("port"), protocol)
    return prepare_profile(
        Profile(
            name=name,
            protocol=protocol,
            host=_optional_clean(data.get("host"), "host"),
            port=port,
            username=_optional_clean(data.get("username"), "username"),
            group=_optional_clean(data.get("group"), "group") or "default",
            tags=parse_tags(data.get("tags", "")),
            description=safe.clean_text(data.get("description") or "", "description", allow_empty=True),
            path=_optional_clean(data.get("path"), "path"),
            url=_optional_clean(data.get("url"), "url"),
            command=_optional_clean(data.get("command"), "command"),
            identity_file=_optional_clean(data.get("identity_file"), "identity file"),
            credential_ref=_optional_clean(data.get("credential_ref"), "credential ref"),
            tunnels=parse_tunnels_text(data.get("tunnels", "")),
            options=parse_key_value_text(data.get("options", "")),
        ),
        extra_protocols=plugin_protocols(),
    )


def layout_to_editor_data(layout: Layout | None = None) -> dict[str, str]:
    if layout is None:
        return {"name": "", "orientation": "grid", "description": "", "panes": ""}
    return {
        "name": layout.name,
        "orientation": layout.orientation,
        "description": layout.description,
        "panes": format_layout_panes_text(layout.panes),
    }


def layout_from_editor_data(data: Mapping[str, str]) -> Layout:
    layout = Layout(
        name=_required(data.get("name"), "layout name"),
        orientation=_required(data.get("orientation"), "layout orientation").lower(),
        panes=parse_layout_panes_text(data.get("panes", "")),
        description=safe.clean_text(data.get("description") or "", "layout description", allow_empty=True),
    )
    validate_layout(layout)
    return layout


def parse_key_value_text(text: str) -> dict[str, str]:
    options: dict[str, str] = {}
    for line_number, line in enumerate(text.splitlines(), start=1):
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        if "=" not in raw:
            raise ValueError(f"option line {line_number} must be key=value")
        key, value = raw.split("=", 1)
        key = safe.clean_text(key.strip(), f"option line {line_number} key")
        if any(char.isspace() for char in key):
            raise ValueError(f"option line {line_number} key must not contain whitespace")
        options[key] = safe.clean_text(value.strip(), f"option line {line_number} value", allow_empty=True)
    return options


def format_key_value_text(options: Mapping[str, str]) -> str:
    return "\n".join(f"{key}={value}" for key, value in sorted(options.items()))


def parse_tags(text: str) -> list[str]:
    tags: list[str] = []
    seen: set[str] = set()
    for item in text.replace("\n", ",").split(","):
        tag = safe.clean_text(item.strip(), "tag", allow_empty=True)
        if tag and tag not in seen:
            seen.add(tag)
            tags.append(tag)
    return tags


def parse_tunnels_text(text: str) -> list[Tunnel]:
    tunnels: list[Tunnel] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        tunnels.append(_parse_tunnel(raw, line_number))
    return tunnels


def format_tunnels_text(tunnels: list[Tunnel]) -> str:
    lines: list[str] = []
    for tunnel in tunnels:
        if tunnel.mode == "dynamic":
            lines.append(f"dynamic:{tunnel.local_port}")
        elif tunnel.local_host and tunnel.local_host != "127.0.0.1":
            lines.append(
                f"{tunnel.mode}:{tunnel.local_port}:{tunnel.remote_host}:{tunnel.remote_port}:{tunnel.local_host}"
            )
        else:
            lines.append(f"{tunnel.mode}:{tunnel.local_port}:{tunnel.remote_host}:{tunnel.remote_port}")
    return "\n".join(lines)


def parse_layout_panes_text(text: str) -> list[LayoutPane]:
    panes: list[LayoutPane] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        raw = line.strip()
        if not raw or raw.startswith("#"):
            continue
        pane_text, separator, title = raw.partition(" | ")
        pane = parse_layout_pane(pane_text.strip())
        if separator:
            pane.title = safe.clean_text(title.strip(), f"layout pane {line_number} title")
        panes.append(pane)
    return panes


def format_layout_panes_text(panes: list[LayoutPane]) -> str:
    lines: list[str] = []
    for pane in panes:
        if pane.profile:
            base = f"profile:{pane.profile}"
        elif pane.command:
            base = f"command:{pane.command}"
        else:
            base = ""
        if pane.title:
            base = f"{base} | {pane.title}"
        lines.append(base)
    return "\n".join(lines)


def _parse_tunnel(raw: str, line_number: int) -> Tunnel:
    parts = raw.split(":")
    mode = safe.clean_text(parts[0], f"tunnel line {line_number} mode").lower()
    if mode == "dynamic" and len(parts) == 2:
        return Tunnel(mode=mode, local_port=safe.port(_int(parts[1], line_number), "tunnel local port"))
    if mode in {"local", "remote"} and len(parts) in {4, 5}:
        local_port = safe.port(_int(parts[1], line_number), "tunnel local port")
        remote_host = safe.host(parts[2], "tunnel remote host")
        remote_port = safe.port(_int(parts[3], line_number), "tunnel remote port")
        local_host = safe.host(parts[4], "tunnel local host") if len(parts) == 5 else "127.0.0.1"
        return Tunnel(
            mode=mode,
            local_host=local_host,
            local_port=local_port,
            remote_host=remote_host,
            remote_port=remote_port,
        )
    raise ValueError(f"invalid tunnel line {line_number}: {raw}")


def _required(value: str | None, label: str) -> str:
    return safe.clean_text((value or "").strip(), label)


def _optional_clean(value: str | None, label: str) -> str | None:
    text = safe.clean_text((value or "").strip(), label, allow_empty=True)
    return text or None


def _optional_port(value: str | None, protocol: str) -> int | None:
    text = safe.clean_text((value or "").strip(), f"{protocol} port", allow_empty=True)
    if not text:
        return None
    return safe.port(_int(text, 0), f"{protocol} port")


def _int(value: str, line_number: int) -> int:
    try:
        return int(value)
    except ValueError as exc:
        label = "value" if line_number == 0 else f"line {line_number} value"
        raise ValueError(f"{label} must be an integer: {value}") from exc

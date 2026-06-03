from __future__ import annotations

from collections.abc import Mapping
from dataclasses import replace
from typing import Any, Iterable

from . import command_safety as safe
from .models import Profile, Tunnel

SUPPORTED_PROFILE_PROTOCOLS = frozenset(
    {
        "custom",
        "ftp",
        "http",
        "https",
        "ica",
        "local",
        "local-shell",
        "mosh",
        "raw",
        "rdp",
        "rlogin",
        "rsh",
        "scp",
        "serial",
        "sftp",
        "shell",
        "spice",
        "ssh",
        "ssh1",
        "sshv1",
        "telnet",
        "vnc",
        "www",
        "x2go",
        "xdmcp",
    }
)

HOST_TARGET_PROTOCOLS = frozenset(
    {
        "ftp",
        "mosh",
        "raw",
        "rdp",
        "rlogin",
        "rsh",
        "scp",
        "sftp",
        "spice",
        "ssh",
        "ssh1",
        "sshv1",
        "telnet",
        "vnc",
        "xdmcp",
    }
)

URL_PROTOCOLS = frozenset({"http", "https", "www"})
LOCAL_PROTOCOLS = frozenset({"local", "local-shell", "shell"})
BOOL_TRUE_VALUES = frozenset({"1", "true", "yes"})


class ProfileValidationError(ValueError):
    pass


def prepare_profile(
    profile: Profile,
    *,
    require_target: bool = True,
    extra_protocols: Iterable[str] = (),
) -> Profile:
    normalized = normalize_profile(profile, extra_protocols=extra_protocols)
    validate_profile(normalized, require_target=require_target, extra_protocols=extra_protocols)
    return normalized


def normalize_profile(profile: Profile, *, extra_protocols: Iterable[str] = ()) -> Profile:
    protocol = _profile_protocol(profile.protocol, extra_protocols=extra_protocols)
    return replace(
        profile,
        name=safe.clean_text(str(profile.name).strip(), "profile name"),
        protocol=protocol,
        host=_optional_host(profile.host, protocol),
        port=safe.port(profile.port, f"{protocol} port") if profile.port is not None else None,
        username=_optional_clean(profile.username, "username"),
        group=_optional_clean(profile.group, "group") or "default",
        tags=_clean_tags(profile.tags),
        description=safe.clean_text(profile.description or "", "description", allow_empty=True),
        path=_optional_clean(profile.path, "path"),
        url=_optional_url(profile.url, protocol),
        command=_optional_clean(profile.command, "command"),
        credential_ref=_optional_clean(profile.credential_ref, "credential ref"),
        identity_file=_optional_clean(profile.identity_file, "identity file"),
        tunnels=[normalize_tunnel(tunnel) for tunnel in profile.tunnels],
        options=_clean_options(profile.options),
    )


def validate_profile(
    profile: Profile,
    *,
    require_target: bool = True,
    extra_protocols: Iterable[str] = (),
) -> None:
    protocol = _profile_protocol(profile.protocol, extra_protocols=extra_protocols)
    if protocol != profile.protocol:
        raise ProfileValidationError("profile protocol must be normalized before validation")
    if protocol not in _supported_protocols(extra_protocols):
        raise ProfileValidationError(f"unsupported profile protocol: {protocol}")
    if require_target and protocol in SUPPORTED_PROFILE_PROTOCOLS:
        _require_target(profile)


def normalize_tunnel(tunnel: Tunnel) -> Tunnel:
    mode = safe.clean_text(tunnel.mode, "tunnel mode").strip().lower()
    if mode == "dynamic":
        return replace(
            tunnel,
            mode=mode,
            local_host=safe.host(tunnel.local_host, "tunnel local host"),
            local_port=safe.port(tunnel.local_port, "tunnel local port"),
            remote_host=None,
            remote_port=None,
        )
    if mode in {"local", "remote"}:
        return replace(
            tunnel,
            mode=mode,
            local_host=safe.host(tunnel.local_host, "tunnel local host"),
            local_port=safe.port(tunnel.local_port, "tunnel local port"),
            remote_host=safe.host(tunnel.remote_host, "tunnel remote host"),
            remote_port=safe.port(tunnel.remote_port, "tunnel remote port"),
        )
    raise ProfileValidationError(f"unsupported tunnel mode: {tunnel.mode}")


def normalize_group_name(group: str | None) -> str:
    return safe.clean_text((group or "default").strip(), "group")


def normalize_group_defaults(defaults: Mapping[str, Any] | None) -> dict[str, object]:
    if defaults is None:
        return {}
    if not isinstance(defaults, Mapping):
        raise ProfileValidationError("group defaults must be an object")
    normalized: dict[str, object] = {}
    username = _optional_clean(defaults.get("username"), "group default username")
    if username:
        normalized["username"] = username
    identity_file = _optional_clean(defaults.get("identity_file"), "group default identity file")
    if identity_file:
        normalized["identity_file"] = identity_file
    credential_ref = _optional_clean(defaults.get("credential_ref"), "group default credential ref")
    if credential_ref:
        normalized["credential_ref"] = credential_ref
    options = defaults.get("options")
    if isinstance(options, Mapping):
        cleaned_options = _clean_options(options)
        if cleaned_options:
            normalized["options"] = cleaned_options
    elif options not in (None, "", {}, []):
        raise ProfileValidationError("group default options must be an object")
    return normalized


def normalize_group_defaults_map(defaults: Any) -> dict[str, dict[str, object]]:
    if defaults in (None, ""):
        return {}
    if not isinstance(defaults, Mapping):
        raise ProfileValidationError("group_defaults must be an object")
    return {
        normalize_group_name(str(group)): normalize_group_defaults(value)
        for group, value in defaults.items()
    }


def _profile_protocol(value: str, *, extra_protocols: Iterable[str] = ()) -> str:
    protocol = safe.clean_text(str(value).strip().lower(), "protocol")
    if any(char.isspace() for char in protocol):
        raise ProfileValidationError("protocol must not contain whitespace")
    if protocol.startswith("-"):
        raise ProfileValidationError("protocol must not start with '-'")
    if protocol not in _supported_protocols(extra_protocols):
        raise ProfileValidationError(f"unsupported profile protocol: {protocol}")
    return protocol


def _supported_protocols(extra_protocols: Iterable[str]) -> frozenset[str]:
    return SUPPORTED_PROFILE_PROTOCOLS | frozenset(str(protocol).strip().lower() for protocol in extra_protocols)


def _require_target(profile: Profile) -> None:
    protocol = profile.protocol
    if protocol in HOST_TARGET_PROTOCOLS and not profile.host:
        raise ProfileValidationError(f"{protocol} profile requires host")
    if protocol == "raw" and profile.port is None:
        raise ProfileValidationError("raw profile requires explicit port")
    if protocol in URL_PROTOCOLS and not (profile.url or profile.host):
        raise ProfileValidationError(f"{protocol} profile requires url or host")
    if protocol == "serial" and not (profile.path or profile.options.get("device")):
        raise ProfileValidationError("serial profile requires path or option device")
    if protocol == "custom" and not profile.command:
        raise ProfileValidationError("custom profile requires command")
    if protocol == "ica" and not (profile.path or profile.url or profile.host):
        raise ProfileValidationError("ica profile requires path, url, or host")
    if protocol == "x2go" and not (profile.host or profile.options.get("session") or profile.options.get("session_name")):
        raise ProfileValidationError("x2go profile requires host or option session")


def _optional_host(value: str | None, protocol: str) -> str | None:
    text = _optional_clean(value, f"{protocol} host")
    if text is None:
        return None
    return safe.host(text, f"{protocol} host")


def _optional_url(value: str | None, protocol: str) -> str | None:
    text = _optional_clean(value, "url")
    if text is None:
        return None
    if protocol in URL_PROTOCOLS:
        return safe.url(text)
    return text


def _optional_clean(value: Any, label: str) -> str | None:
    text = safe.clean_text("" if value is None else str(value).strip(), label, allow_empty=True)
    return text or None


def _clean_tags(tags: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for tag in tags:
        text = safe.clean_text(str(tag).strip(), "tag", allow_empty=True)
        if text and text not in seen:
            seen.add(text)
            result.append(text)
    return result


def _clean_options(options: Mapping[str, Any]) -> dict[str, str]:
    result: dict[str, str] = {}
    for key, value in options.items():
        clean_key = safe.clean_text(str(key).strip(), "option key")
        if any(char.isspace() for char in clean_key):
            raise ProfileValidationError("option key must not contain whitespace")
        if clean_key.startswith("-"):
            raise ProfileValidationError("option key must not start with '-'")
        result[clean_key] = safe.clean_text(
            "" if value is None else str(value).strip(),
            f"option {clean_key}",
            allow_empty=True,
        )
    return result

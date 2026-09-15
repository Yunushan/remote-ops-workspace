from __future__ import annotations

from collections.abc import Mapping
from urllib.parse import urlsplit, urlunsplit

from .models import Profile
from .profile_validation import prepare_profile
from .redaction import is_share_sensitive_key, redact_text

# Shared catalogues are a deliberately narrower trust boundary than the local
# profile store. Only options with non-secret, declarative values cross it.
SHAREABLE_OPTION_KEYS = frozenset(
    {
        "agent_forward",
        "audio",
        "baud",
        "baud_rate",
        "bind_server",
        "clipboard",
        "compression",
        "connect_timeout",
        "connection_timeout",
        "container",
        "data_bits",
        "dynamic_resolution",
        "encoding",
        "flow_control",
        "forward_agent",
        "fullscreen",
        "geometry",
        "jump_host",
        "keepalive_count",
        "keepalive_interval",
        "kube_container",
        "kube_context",
        "kube_namespace",
        "link",
        "log_level",
        "mosh_bind_server",
        "mosh_port",
        "mosh_ports",
        "mosh_predict",
        "namespace",
        "pack",
        "parity",
        "predict",
        "proxy_jump",
        "quality",
        "rdp_security",
        "resolution",
        "scale",
        "security",
        "server_alive_count_max",
        "server_alive_interval",
        "session",
        "session_name",
        "session_type",
        "shared",
        "smartcard_auth",
        "ssh_browser",
        "stop_bits",
        "strict_host_key_checking",
        "transport",
        "view_only",
        "viewonly",
        "winrm_transport",
        "x11",
        "zoom",
    }
)

LOCAL_ONLY_PROTOCOLS = frozenset({"custom", "local", "local-shell", "serial", "shell"})
SHAREABLE_URL_SCHEMES = frozenset({"http", "https"})
UNSHAREABLE_OPTION_KEYS = frozenset({"agent_forward", "forward_agent", "x11"})
INHERITED_LOCAL_CAPABILITY_OPTION_KEYS = frozenset(
    {
        "agent_forward",
        "forward_agent",
        "jump_host",
        "proxy_command",
        "proxy_jump",
        "smartcard_auth",
        "x11",
    }
)
SHARED_PROFILE_FIELDS = frozenset(
    {
        "name",
        "protocol",
        "host",
        "port",
        "username",
        "group",
        "tags",
        "description",
        "url",
        "tunnels",
        "options",
    }
)
SHARED_TUNNEL_FIELDS = frozenset(
    {"mode", "local_host", "local_port", "remote_host", "remote_port"}
)


def is_shareable_option_key(key: object) -> bool:
    normalized = str(key).strip().replace("-", "_").lower()
    return (
        normalized in SHAREABLE_OPTION_KEYS
        and normalized not in UNSHAREABLE_OPTION_KEYS
        and not is_share_sensitive_key(normalized)
    )


def is_shareable_option(key: object, value: object) -> bool:
    normalized = str(key).strip().replace("-", "_").lower()
    text = str(value)
    if not is_shareable_option_key(normalized) or redact_text(text) != text:
        return False
    # A catalogue row must never be able to silently disable SSH host identity
    # verification. The safer explicit modes remain shareable.
    if normalized == "strict_host_key_checking" and text.strip().lower() == "no":
        return False
    return True


def shareable_options(options: dict[str, str]) -> dict[str, str]:
    shared: dict[str, str] = {}
    for key, value in options.items():
        text = str(value)
        if is_shareable_option(key, text):
            shared[key] = text
    return shared


def sanitize_shared_url(value: str | None) -> str | None:
    """Return a navigation URL without credentials or request-specific data."""
    if not value:
        return None
    try:
        parsed = urlsplit(value)
        hostname = parsed.hostname
        port = parsed.port
    except ValueError:
        return None
    if parsed.scheme.lower() not in SHAREABLE_URL_SCHEMES or not hostname:
        return None
    display_host = f"[{hostname}]" if ":" in hostname else hostname
    netloc = f"{display_host}:{port}" if port is not None else display_host
    # URL paths frequently embed password-reset/capability tokens that cannot
    # be identified reliably by key-name redaction. Share only the origin.
    return urlunsplit((parsed.scheme.lower(), netloc, "", "", ""))


def profile_is_shareable(profile: Profile) -> bool:
    if profile.protocol in LOCAL_ONLY_PROTOCOLS:
        return False
    if secret_bearing_public_fields(profile):
        return False
    if profile.protocol == "ica" and not (profile.host or sanitize_shared_url(profile.url)):
        return False
    return True


def public_profile_dict(profile: Profile) -> dict[str, object]:
    """Serialize connection metadata without local paths or executable content."""
    return {
        "name": redact_text(profile.name),
        "protocol": profile.protocol,
        "host": redact_text(profile.host) if profile.host is not None else None,
        "port": profile.port,
        "username": redact_text(profile.username) if profile.username is not None else None,
        "group": redact_text(profile.group),
        "tags": [redact_text(tag) for tag in profile.tags],
        "description": redact_text(profile.description),
        "url": sanitize_shared_url(profile.url),
        # Forward definitions can expose local services or create listening
        # sockets. They remain local even when the connection itself is shared.
        "tunnels": [],
        "options": shareable_options(profile.options),
    }


def public_profile_binding(profile: Profile) -> tuple[object, ...]:
    """Identify the public endpoint to which local credentials were bound."""

    public = public_profile_dict(profile)
    public_options = public["options"]
    if not isinstance(public_options, dict):  # pragma: no cover - serializer invariant
        raise TypeError("public profile options must be an object")
    return (
        public["protocol"],
        public["host"],
        public["port"],
        public["username"],
        public["url"],
        tuple(sorted(public_options.items())),
    )


def inherited_local_capabilities(
    profile: Profile,
    group_defaults: Mapping[str, Mapping[str, object]],
) -> tuple[str, ...]:
    """Return local credential/routing capabilities an ingress row would inherit.

    Unknown local-only options are included so a newly introduced executable or
    credential-bearing option cannot cross the Web/team trust boundary by
    default. Explicit profile options override group options and are separately
    constrained by the public wire schema.
    """

    defaults = group_defaults.get(profile.group, {})
    blocked = {
        key
        for key in ("credential_ref", "identity_file")
        if defaults.get(key) not in (None, "", [], {}) and not getattr(profile, key)
    }
    raw_options = defaults.get("options", {})
    if isinstance(raw_options, Mapping):
        explicit = {
            str(key).strip().replace("-", "_").lower()
            for key in profile.options
        }
        for key, value in raw_options.items():
            normalized = str(key).strip().replace("-", "_").lower()
            if normalized in explicit or value in (None, "", [], {}):
                continue
            if (
                normalized in INHERITED_LOCAL_CAPABILITY_OPTION_KEYS
                or not is_shareable_option(key, value)
            ):
                blocked.add(f"options.{normalized}")
    return tuple(sorted(blocked))


def assert_untrusted_profile_defaults_safe(
    profile: Profile,
    existing: Profile | None,
    group_defaults: Mapping[str, Mapping[str, object]],
    *,
    boundary: str,
) -> bool:
    """Reject a new binding to local capabilities; return endpoint continuity."""

    same_binding = (
        existing is not None
        and public_profile_binding(existing) == public_profile_binding(profile)
    )
    inherited = inherited_local_capabilities(profile, group_defaults)
    if inherited and not (
        same_binding and existing is not None and existing.group == profile.group
    ):
        raise ValueError(
            f"{boundary} refuses to attach local group credentials or forwarding "
            f"settings to changed or new profile {profile.name!r}: "
            + ", ".join(inherited)
        )
    return same_binding


def secret_bearing_public_fields(profile: Profile) -> tuple[str, ...]:
    """Return public metadata fields whose text redaction would change them."""

    values: list[tuple[str, str | None]] = [
        ("name", profile.name),
        ("host", profile.host),
        ("username", profile.username),
        ("group", profile.group),
        ("description", profile.description),
    ]
    values.extend(("tags", tag) for tag in profile.tags)
    return tuple(
        key
        for key, value in values
        if value is not None and redact_text(value) != value
    )


def shared_profile_from_dict(data: object) -> Profile:
    """Parse one untrusted shared-catalogue row using the public wire schema.

    Team-sync files live on mounted/shared storage and must not gain the wider
    trust of the local profile store. Requiring the exact serializer output
    prevents a tampered record from injecting local paths, credentials,
    executable fields, unsafe options, or non-Web URL schemes.
    """

    if not isinstance(data, dict) or any(not isinstance(key, str) for key in data):
        raise ValueError("shared profile must be a JSON object with string keys")
    unsupported = sorted(set(data) - SHARED_PROFILE_FIELDS)
    missing = sorted(SHARED_PROFILE_FIELDS - set(data))
    if unsupported or missing:
        details: list[str] = []
        if unsupported:
            details.append("unsupported fields: " + ", ".join(unsupported))
        if missing:
            details.append("missing fields: " + ", ".join(missing))
        raise ValueError("shared profile schema mismatch (" + "; ".join(details) + ")")

    for key in ("name", "protocol", "group", "description"):
        if not isinstance(data[key], str):
            raise ValueError(f"shared profile {key} must be text")
    raw_protocol = data["protocol"].strip().lower()
    if raw_protocol in LOCAL_ONLY_PROTOCOLS:
        raise ValueError(f"shared profile protocol is local or executable: {raw_protocol}")
    for key in ("host", "username", "url"):
        if data[key] is not None and not isinstance(data[key], str):
            raise ValueError(f"shared profile {key} must be text or null")
    port = data["port"]
    if port is not None and (type(port) is not int or not 1 <= port <= 65535):
        raise ValueError("shared profile port must be an integer between 1 and 65535 or null")
    tags = data["tags"]
    if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
        raise ValueError("shared profile tags must be an array of strings")
    options = data["options"]
    if not isinstance(options, dict) or any(
        not isinstance(key, str) or not isinstance(value, str)
        for key, value in options.items()
    ):
        raise ValueError("shared profile options must be a string-to-string object")
    blocked_options = sorted(
        key
        for key, value in options.items()
        if not is_shareable_option(key, value)
    )
    if blocked_options:
        raise ValueError("shared profile contains unsafe options: " + ", ".join(blocked_options))
    raw_url = data["url"]
    if raw_url is not None and sanitize_shared_url(raw_url) != raw_url:
        raise ValueError("shared profile URL must be a sanitized HTTP(S) URL")

    tunnels = data["tunnels"]
    if not isinstance(tunnels, list):
        raise ValueError("shared profile tunnels must be an array")
    if tunnels:
        raise ValueError("shared profiles must not contain port forwards")
    for tunnel in tunnels:
        if (
            not isinstance(tunnel, dict)
            or any(not isinstance(key, str) for key in tunnel)
            or set(tunnel) != SHARED_TUNNEL_FIELDS
        ):
            raise ValueError("shared profile tunnels must use the exact public tunnel schema")

    try:
        profile = prepare_profile(Profile.from_dict(data))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"shared profile is invalid: {exc}") from exc
    if not profile_is_shareable(profile):
        unsafe_text = secret_bearing_public_fields(profile)
        if unsafe_text:
            raise ValueError(
                "shared profile contains secret-bearing public fields: "
                + ", ".join(sorted(set(unsafe_text)))
            )
        raise ValueError(f"shared profile protocol is local or executable: {profile.protocol}")
    if public_profile_dict(profile) != data:
        raise ValueError("shared profile is not canonical public metadata")
    return profile

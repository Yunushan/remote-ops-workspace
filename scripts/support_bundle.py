#!/usr/bin/env python3
from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any

from remote_ops_workspace.doctor import run_doctor
from remote_ops_workspace.paths import data_dir
from remote_ops_workspace.profile_validation import SUPPORTED_PROFILE_PROTOCOLS
from remote_ops_workspace.redaction import is_sensitive_key

SUPPORT_BUNDLE_NOTE = (
    "Review before sharing. This bundle excludes vault.json, private keys, and raw profile data."
)
DIAGNOSTIC_OPTION_KEYS = frozenset({
    "agent_forward", "allow_unsafe_proxy_command", "compression", "connect_timeout",
    "device", "forward_agent", "jump_host", "proxy_command", "proxy_jump",
    "server_alive_interval", "strict_host_key_checking", "x11",
})
TUNNEL_MODES = frozenset({"dynamic", "local", "remote"})
URL_SCHEMES = frozenset({"http", "https"})


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    report = _sanitized_doctor_report(run_doctor(include_plugins=False).to_dict())
    try:
        summary = _profile_summary(data_dir() / "profiles.json")
    except FileNotFoundError:
        summary = None
    except (OSError, ValueError, RecursionError):
        summary = {"status": "unavailable", "raw_profiles_included": False}
    output = NamedTemporaryFile(dir=Path.cwd(), prefix=f"support-bundle-{stamp}-", suffix=".zip", delete=False)
    out = Path(output.name)
    try:
        with output, zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as zf:
            zf.writestr("doctor.json", json.dumps(report, indent=2))
            if summary is not None:
                zf.writestr("profiles.summary.json", json.dumps(summary, indent=2))
    except BaseException:
        out.unlink(missing_ok=True)
        raise
    print(out)
    return 0


def _sanitized_doctor_report(report: dict[str, Any]) -> dict[str, Any]:
    sanitized = dict(report)
    if "data_dir" in sanitized:
        sanitized["data_dir"] = "<redacted-data-dir>"
    sanitized["note"] = SUPPORT_BUNDLE_NOTE
    sanitized["raw_profiles_included"] = False
    return sanitized


def _profile_summary(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Profile store must be a JSON object")
    profiles = data.get("profiles", [])
    if not isinstance(profiles, list):
        profiles = []
    version = data.get("version", 1)
    return {
        "version": version if type(version) is int else None,
        "raw_profiles_included": False,
        "profile_count": len(profiles),
        "protocol_counts": _protocol_counts(profiles),
        "profiles": [_summarize_profile(index, profile) for index, profile in enumerate(profiles, start=1)],
        "group_defaults": _summarize_group_defaults(data.get("group_defaults", {})),
    }


def _protocol_counts(profiles: list[Any]) -> dict[str, int]:
    counts: dict[str, int] = {}
    for profile in profiles:
        if not isinstance(profile, dict):
            continue
        protocol = _known_label(profile.get("protocol"), SUPPORTED_PROFILE_PROTOCOLS) or "<missing>"
        counts[protocol] = counts.get(protocol, 0) + 1
    return dict(sorted(counts.items()))


def _summarize_profile(index: int, profile: Any) -> dict[str, Any]:
    if not isinstance(profile, dict):
        return {"index": index, "invalid": True}
    options = profile.get("options", {})
    tunnels = profile.get("tunnels", [])
    tags = profile.get("tags", [])
    option_keys, sensitive_option_key_count, unrecognized_option_key_count = _summarize_option_keys(options)
    return {
        "index": index,
        "protocol": _known_label(profile.get("protocol"), SUPPORTED_PROFILE_PROTOCOLS),
        "has_host": bool(profile.get("host")),
        "has_port": profile.get("port") not in (None, ""),
        "has_username": bool(profile.get("username")),
        "has_identity_file": bool(profile.get("identity_file")),
        "has_credential_ref": bool(profile.get("credential_ref")),
        "has_command": bool(profile.get("command")),
        "has_path": bool(profile.get("path")),
        "has_description": bool(profile.get("description")),
        "url_scheme": _url_scheme(profile.get("url")),
        "tag_count": len(tags) if isinstance(tags, list) else 0,
        "option_keys": option_keys,
        "sensitive_option_key_count": sensitive_option_key_count,
        "unrecognized_option_key_count": unrecognized_option_key_count,
        "tunnel_modes": _tunnel_modes(tunnels),
    }


def _summarize_group_defaults(defaults: Any) -> dict[str, Any]:
    if not isinstance(defaults, dict):
        return {"group_count": 0, "groups": []}
    groups = []
    for index, value in enumerate(defaults.values(), start=1):
        if not isinstance(value, dict):
            groups.append({"index": index, "invalid": True})
            continue
        options = value.get("options", {})
        option_keys, sensitive_option_key_count, unrecognized_option_key_count = _summarize_option_keys(options)
        groups.append(
            {
                "index": index,
                "has_username": bool(value.get("username")),
                "has_identity_file": bool(value.get("identity_file")),
                "has_credential_ref": bool(value.get("credential_ref")),
                "option_keys": option_keys,
                "sensitive_option_key_count": sensitive_option_key_count,
                "unrecognized_option_key_count": unrecognized_option_key_count,
            }
        )
    return {"group_count": len(defaults), "groups": groups}


def _summarize_option_keys(options: Any) -> tuple[list[str], int, int]:
    if not isinstance(options, dict):
        return [], 0, 0
    public_keys = []
    sensitive_count = 0
    for key in options:
        if is_sensitive_key(key):
            sensitive_count += 1
        elif key in DIAGNOSTIC_OPTION_KEYS:
            public_keys.append(key)
    return sorted(public_keys), sensitive_count, len(options) - len(public_keys) - sensitive_count


def _tunnel_modes(tunnels: Any) -> list[str]:
    if not isinstance(tunnels, list):
        return []
    modes = {
        _known_label(tunnel["mode"], TUNNEL_MODES)
        for tunnel in tunnels
        if isinstance(tunnel, dict) and tunnel.get("mode")
    }
    return sorted(modes)


def _url_scheme(value: Any) -> str:
    if not isinstance(value, str):
        return ""
    scheme, separator, _ = value.partition(":")
    return _known_label(scheme.lower(), URL_SCHEMES) if separator else ""


def _known_label(value: Any, allowed: frozenset[str]) -> str:
    if not value:
        return ""
    return value if isinstance(value, str) and value in allowed else "<other>"


if __name__ == "__main__":
    raise SystemExit(main())

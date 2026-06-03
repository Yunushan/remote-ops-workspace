#!/usr/bin/env python3
from __future__ import annotations

import json
import zipfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from remote_ops_workspace.doctor import run_doctor
from remote_ops_workspace.paths import data_dir

SUPPORT_BUNDLE_NOTE = (
    "Review before sharing. This bundle excludes vault.json, private keys, and raw profile data."
)


def main() -> int:
    stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
    out = Path.cwd() / f"support-bundle-{stamp}.zip"
    report = _sanitized_doctor_report(run_doctor().to_dict())
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("doctor.json", json.dumps(report, indent=2))
        profiles = data_dir() / "profiles.json"
        if profiles.exists():
            zf.writestr("profiles.summary.json", json.dumps(_profile_summary(profiles), indent=2))
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
    profiles = data.get("profiles", [])
    if not isinstance(profiles, list):
        profiles = []
    return {
        "version": data.get("version", 1),
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
        protocol = str(profile.get("protocol") or "<missing>")
        counts[protocol] = counts.get(protocol, 0) + 1
    return dict(sorted(counts.items()))


def _summarize_profile(index: int, profile: Any) -> dict[str, Any]:
    if not isinstance(profile, dict):
        return {"index": index, "invalid": True}
    options = profile.get("options", {})
    tunnels = profile.get("tunnels", [])
    tags = profile.get("tags", [])
    return {
        "index": index,
        "protocol": str(profile.get("protocol") or ""),
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
        "option_keys": sorted(str(key) for key in options) if isinstance(options, dict) else [],
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
        groups.append(
            {
                "index": index,
                "has_username": bool(value.get("username")),
                "has_identity_file": bool(value.get("identity_file")),
                "has_credential_ref": bool(value.get("credential_ref")),
                "option_keys": sorted(str(key) for key in options) if isinstance(options, dict) else [],
            }
        )
    return {"group_count": len(defaults), "groups": groups}


def _tunnel_modes(tunnels: Any) -> list[str]:
    if not isinstance(tunnels, list):
        return []
    modes = {
        str(tunnel.get("mode"))
        for tunnel in tunnels
        if isinstance(tunnel, dict) and tunnel.get("mode")
    }
    return sorted(modes)


def _url_scheme(value: Any) -> str:
    if not value:
        return ""
    return urlparse(str(value)).scheme


if __name__ == "__main__":
    raise SystemExit(main())

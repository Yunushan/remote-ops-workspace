from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from .file_safety import write_json_atomic
from .models import Profile
from .paths import ensure_data_dir
from .plugins import plugin_protocols
from .profile_validation import (
    normalize_group_defaults,
    normalize_group_defaults_map,
    normalize_group_name,
    prepare_profile,
)


class ProfileStore:
    """Small JSON profile store.

    The store is intentionally simple so it works on Windows, Windows Server,
    Linux, Unix, BSD, Solaris, macOS, Android/Termux and containerized web backends.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (ensure_data_dir() / "profiles.json")

    def init(self, with_examples: bool = True) -> None:
        if self.path.exists():
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        profiles = example_profiles() if with_examples else []
        self.save(profiles)

    def load(self, resolve: bool = True) -> list[Profile]:
        data = self._load_data()
        extra_protocols = plugin_protocols()
        if not resolve:
            return [
                prepare_profile(Profile.from_dict(item), extra_protocols=extra_protocols)
                for item in data.get("profiles", [])
            ]
        defaults = data.get("group_defaults", {})
        return [
            prepare_profile(
                Profile.from_dict(_apply_group_defaults(item, defaults.get(item.get("group", "default"), {}))),
                extra_protocols=extra_protocols,
            )
            for item in data.get("profiles", [])
        ]

    def save(self, profiles: Iterable[Profile]) -> None:
        extra_protocols = plugin_protocols()
        prepared = [prepare_profile(profile, extra_protocols=extra_protocols) for profile in profiles]
        data = self._load_data()
        data["version"] = 1
        data["profiles"] = [profile.to_dict() for profile in prepared]
        write_json_atomic(self.path, data, private=True)

    def add(self, profile: Profile, replace: bool = False) -> None:
        profile = prepare_profile(profile, extra_protocols=plugin_protocols())
        profiles = self.load(resolve=False)
        names = {p.name for p in profiles}
        if profile.name in names and not replace:
            raise ValueError(f"profile already exists: {profile.name}")
        profiles = [p for p in profiles if p.name != profile.name]
        profiles.append(profile)
        self.save(sorted(profiles, key=lambda p: (p.group, p.name)))

    def remove(self, name: str) -> None:
        profiles = self.load(resolve=False)
        remaining = [p for p in profiles if p.name != name]
        if len(remaining) == len(profiles):
            raise KeyError(name)
        self.save(remaining)

    def get(self, name: str) -> Profile:
        for profile in self.load():
            if profile.name == name:
                return profile
        raise KeyError(name)

    def export_to(self, path: Path) -> None:
        data = self._load_data()
        data["profiles"] = [p.to_dict() for p in self.load(resolve=False)]
        write_json_atomic(path, data, private=True)

    def import_from(self, path: Path, replace: bool = False) -> int:
        data = json.loads(path.read_text(encoding="utf-8"))
        if replace and "group_defaults" in data:
            current = self._load_data()
            current["group_defaults"] = normalize_group_defaults_map(data["group_defaults"])
            write_json_atomic(self.path, current, private=True)
        count = 0
        for item in data.get("profiles", []):
            self.add(Profile.from_dict(item), replace=replace)
            count += 1
        return count

    def group_defaults(self) -> dict[str, dict[str, object]]:
        return normalize_group_defaults_map(self._load_data().get("group_defaults", {}))

    def set_group_defaults(self, group: str, defaults: dict[str, object], replace: bool = False) -> None:
        data = self._load_data()
        group = normalize_group_name(group)
        defaults = normalize_group_defaults(defaults)
        group_defaults = data.setdefault("group_defaults", {})
        existing = {} if replace else dict(group_defaults.get(group, {}))
        existing.update({key: value for key, value in defaults.items() if value not in (None, "", [], {})})
        group_defaults[group] = existing
        write_json_atomic(self.path, data, private=True)

    def _load_data(self) -> dict[str, object]:
        if not self.path.exists():
            return {"version": 1, "profiles": [], "group_defaults": {}}
        data = json.loads(self.path.read_text(encoding="utf-8"))
        data.setdefault("version", 1)
        data.setdefault("profiles", [])
        data["group_defaults"] = normalize_group_defaults_map(data.get("group_defaults", {}))
        return data


def example_profiles() -> list[Profile]:
    return [
        Profile(
            name="example-ssh",
            protocol="ssh",
            host="ssh.example.invalid",
            port=22,
            username="admin",
            group="examples",
            tags=["ssh", "demo"],
            description="Example OpenSSH profile using a non-routable example hostname.",
        ),
        Profile(
            name="example-rdp",
            protocol="rdp",
            host="rdp.example.invalid",
            port=3389,
            username="administrator",
            group="examples",
            tags=["rdp", "windows"],
            description="Example RDP profile using a non-routable example hostname.",
        ),
        Profile(
            name="example-web",
            protocol="https",
            url="https://example.com",
            group="examples",
            tags=["web"],
            description="Example web profile.",
        ),
    ]


def _apply_group_defaults(item: dict[str, object], defaults: dict[str, object]) -> dict[str, object]:
    if not defaults:
        return item
    merged = dict(defaults)
    merged.update({key: value for key, value in item.items() if value not in (None, "", [], {})})
    default_options = defaults.get("options", {})
    item_options = item.get("options", {})
    if isinstance(default_options, dict) and isinstance(item_options, dict):
        merged["options"] = {**default_options, **item_options}
    return merged

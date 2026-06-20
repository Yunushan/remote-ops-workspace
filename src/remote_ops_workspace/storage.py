from __future__ import annotations

import json
from collections.abc import Iterable
from pathlib import Path

from .enterprise_policy import (
    assert_profile_collection_change_allowed,
    assert_profile_write_allowed,
    assert_settings_write_allowed,
    enterprise_policy_path,
)
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

    def __init__(self, path: Path | None = None, *, policy_path: Path | None = None) -> None:
        self.path = path or (ensure_data_dir() / "profiles.json")
        self.policy_path = policy_path or enterprise_policy_path(self.path.parent)

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

    def save(self, profiles: Iterable[Profile], *, surface: str = "profile-editor") -> None:
        extra_protocols = plugin_protocols()
        prepared = [prepare_profile(profile, extra_protocols=extra_protocols) for profile in profiles]
        for profile in prepared:
            assert_profile_write_allowed(
                profile,
                surface=surface,
                action="profile-editor",
                policy_path=self.policy_path,
            )
        data = self._load_data()
        data["version"] = 1
        data["profiles"] = [profile.to_dict() for profile in prepared]
        write_json_atomic(self.path, data, private=True)

    def add(self, profile: Profile, replace: bool = False, *, surface: str = "cli") -> None:
        profile = prepare_profile(profile, extra_protocols=plugin_protocols())
        profiles = self.load(resolve=False)
        names = {p.name for p in profiles}
        if profile.name in names and not replace:
            raise ValueError(f"profile already exists: {profile.name}")
        assert_profile_write_allowed(
            profile,
            surface=surface,
            action="replace" if profile.name in names else "add",
            policy_path=self.policy_path,
        )
        profiles = [p for p in profiles if p.name != profile.name]
        profiles.append(profile)
        self.save(sorted(profiles, key=lambda p: (p.group, p.name)), surface=surface)

    def remove(self, name: str, *, surface: str = "cli") -> None:
        assert_profile_collection_change_allowed(
            surface=surface,
            action="remove",
            policy_path=self.policy_path,
        )
        assert_settings_write_allowed(
            {"profile_remove": name},
            surface=surface,
            action="remove",
            policy_path=self.policy_path,
        )
        profiles = self.load(resolve=False)
        remaining = [p for p in profiles if p.name != name]
        if len(remaining) == len(profiles):
            raise KeyError(name)
        self.save(remaining, surface=surface)

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
            assert_profile_collection_change_allowed(
                surface="cli",
                action="profile-defaults",
                policy_path=self.policy_path,
            )
            current = self._load_data()
            group_defaults = normalize_group_defaults_map(data["group_defaults"])
            for defaults in group_defaults.values():
                assert_settings_write_allowed(
                    defaults,
                    surface="cli",
                    action="profile-defaults",
                    policy_path=self.policy_path,
                )
            current["group_defaults"] = group_defaults
            write_json_atomic(self.path, current, private=True)
        count = 0
        for item in data.get("profiles", []):
            self.add(Profile.from_dict(item), replace=replace)
            count += 1
        return count

    def group_defaults(self) -> dict[str, dict[str, object]]:
        return normalize_group_defaults_map(self._load_data().get("group_defaults", {}))

    def set_group_defaults(
        self,
        group: str,
        defaults: dict[str, object],
        replace: bool = False,
        *,
        surface: str = "cli",
    ) -> None:
        data = self._load_data()
        group = normalize_group_name(group)
        defaults = normalize_group_defaults(defaults)
        assert_profile_collection_change_allowed(
            surface=surface,
            action="profile-defaults",
            policy_path=self.policy_path,
        )
        assert_settings_write_allowed(
            defaults,
            surface=surface,
            action="profile-defaults",
            policy_path=self.policy_path,
        )
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
            name="example.jump-ssh",
            protocol="ssh",
            host="jump-ssh.example.invalid",
            port=22,
            username="operator",
            group="default",
            tags=["ssh", "jump", "demo"],
            description="Generic imported jump SSH profile for MobaXterm-style session tree references.",
        ),
        Profile(
            name="example.rdp",
            protocol="rdp",
            host="desktop.example.invalid",
            port=3389,
            username="operator",
            group="default",
            tags=["rdp", "demo"],
            description="Generic imported RDP profile for MobaXterm-style session tree references.",
        ),
        Profile(
            name="example-web",
            protocol="https",
            url="https://example.com",
            group="examples",
            tags=["web"],
            description="Example web profile.",
        ),
        Profile(
            name="edge-prod",
            protocol="ssh",
            host="edge-prod.example.invalid",
            port=22,
            username="operator",
            group="prod",
            tags=["ssh", "demo", "favorite"],
            options={
                "moba_remote_path": "/var/log",
                "moba_monitoring_output": (
                    "cpu=7 mem_mb=410/7680 disk_mb=2867/49152 users=1 processes=158 "
                    "net_up_mbps=0.01 net_down_mbps=0.01"
                ),
            },
            description="Generic SSH demo profile for product-style GUI references.",
        ),
        Profile(
            name="files-prod",
            protocol="sftp",
            host="files-prod.example.invalid",
            port=22,
            username="operator",
            group="files",
            tags=["sftp", "demo"],
            description="Generic SFTP demo profile for file-transfer GUI references.",
        ),
        Profile(
            name="win-admin",
            protocol="rdp",
            host="admin-win.example.invalid",
            port=3389,
            username="administrator",
            group="prod",
            tags=["rdp", "demo"],
            description="Generic RDP demo profile for remote-desktop GUI references.",
        ),
        Profile(
            name="linux-console",
            protocol="vnc",
            host="linux-console.example.invalid",
            port=5900,
            group="lab",
            tags=["vnc", "demo"],
            description="Generic VNC demo profile for remote-console GUI references.",
        ),
        Profile(
            name="sftp-ops",
            protocol="sftp",
            host="logs.example.invalid",
            port=22,
            username="operator",
            path="/var/log",
            group="files",
            tags=["sftp", "demo"],
            description="Generic SFTP operations profile for MobaXterm-style file-browser references.",
        ),
        Profile(
            name="sync-stage",
            protocol="ssh",
            host="sync-stage.example.invalid",
            port=22,
            username="operator",
            group="files",
            tags=["ssh", "sync", "demo"],
            description="Generic sync staging profile for MobaXterm-style session tree references.",
        ),
        Profile(
            name="jump-host",
            protocol="ssh",
            host="jump.example.invalid",
            port=22,
            username="operator",
            group="prod",
            tags=["ssh", "demo", "favorite"],
            description="Generic jump host demo profile for pinned/favorite session references.",
        ),
        Profile(
            name="prod-cluster",
            protocol="ssh",
            host="cluster.example.invalid",
            port=22,
            username="operator",
            group="teams",
            tags=["ssh", "team", "demo"],
            description="Generic team SSH cluster profile for Termius-style shared host references.",
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

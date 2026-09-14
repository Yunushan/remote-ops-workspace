from __future__ import annotations

import json
import os
import threading
from collections.abc import Callable, Iterable, Iterator
from contextlib import contextmanager
from pathlib import Path
from typing import Any

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
from .state_lock import DEFAULT_LOCK_TIMEOUT_SECONDS, FileLockTimeoutError, exclusive_file_lock

ProfileUpdater = Callable[
    [list[Profile], dict[str, dict[str, object]]],
    Iterable[Profile],
]
ProfileWriteGuard = Callable[
    [Profile, Profile | None, dict[str, dict[str, object]]],
    None,
]
_mutation_state = threading.local()


class ProfileStore:
    """Small JSON profile store.

    The store is intentionally simple so it works on Windows, Windows Server,
    Linux, Unix, BSD, Solaris, macOS, Android/Termux and containerized web backends.
    """

    def __init__(
        self,
        path: Path | None = None,
        *,
        policy_path: Path | None = None,
        lock_timeout_seconds: float = DEFAULT_LOCK_TIMEOUT_SECONDS,
    ) -> None:
        self.path = path or (ensure_data_dir() / "profiles.json")
        self.policy_path = policy_path or enterprise_policy_path(self.path.parent)
        self.lock_timeout_seconds = lock_timeout_seconds

    def init(
        self,
        with_examples: bool = True,
        *,
        purge_examples: bool | None = None,
        surface: str = "cli",
    ) -> None:
        if purge_examples is None:
            purge_examples = not with_examples
        with self._transaction():
            if not self.path.exists():
                profiles = example_profiles() if with_examples else []
                self._save_data(
                    {"version": 1, "profiles": [], "group_defaults": {}},
                    profiles,
                    surface=surface,
                )
                return
        if purge_examples:
            self.purge_seeded_examples(surface=surface)

    def purge_seeded_examples(self, *, surface: str = "cli") -> list[str]:
        """Remove only unchanged profiles created by :func:`example_profiles`.

        Release upgrades may reuse an existing profile store that was initialized
        by an older build.  Matching the complete normalized profile record keeps
        user-edited rows, including rows with an example-like name, intact.
        """

        with self._transaction():
            assert_profile_collection_change_allowed(
                surface=surface,
                action="purge-seeded-examples",
                policy_path=self.policy_path,
            )
            data = self._load_data()
            profiles = self._profiles_from_data(data, resolve=False)
            seeded = {_profile_fingerprint(profile) for profile in example_profiles()}
            removable = [profile for profile in profiles if _profile_fingerprint(profile) in seeded]
            if not removable:
                return []
            names = [profile.name for profile in removable]
            assert_settings_write_allowed(
                {"profile_purge_seeded_examples": names},
                surface=surface,
                action="purge-seeded-examples",
                policy_path=self.policy_path,
            )
            remaining = [profile for profile in profiles if profile not in removable]
            self._save_data(data, remaining, surface=surface)
            return names

    def load(self, resolve: bool = True) -> list[Profile]:
        return self._profiles_from_data(self._load_data(), resolve=resolve)

    def _profiles_from_data(self, data: dict[str, Any], *, resolve: bool) -> list[Profile]:
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
        with self._transaction():
            assert_profile_collection_change_allowed(
                surface=surface,
                action="replace-all",
                policy_path=self.policy_path,
            )
            self._save_data(self._load_data(), profiles, surface=surface)

    def update_profiles(
        self,
        updater: ProfileUpdater,
        *,
        surface: str = "profile-editor",
        action: str = "update",
    ) -> list[Profile]:
        """Atomically read, validate, and replace the profile collection.

        The updater runs while the store lock is held and receives unresolved
        profiles plus an isolated normalized snapshot of group defaults. This is
        the transaction boundary for compound GUI and team-sync changes.
        """

        with self._transaction():
            assert_profile_collection_change_allowed(
                surface=surface,
                action=action,
                policy_path=self.policy_path,
            )
            data = self._load_data()
            current = self._profiles_from_data(data, resolve=False)
            defaults = normalize_group_defaults_map(data.get("group_defaults", {}))
            replacement = list(updater(current, defaults))
            return self._save_data(data, replacement, surface=surface)

    def replace_named(
        self,
        original_name: str,
        profile: Profile,
        *,
        surface: str = "profile-editor",
    ) -> Profile:
        profile = prepare_profile(profile, extra_protocols=plugin_protocols())

        def replace(
            profiles: list[Profile],
            _group_defaults: dict[str, dict[str, object]],
        ) -> Iterable[Profile]:
            if not any(item.name == original_name for item in profiles):
                raise KeyError(original_name)
            if profile.name != original_name and any(
                item.name == profile.name for item in profiles
            ):
                raise ValueError(f"profile already exists: {profile.name}")
            remaining = [item for item in profiles if item.name != original_name]
            remaining.append(profile)
            return sorted(remaining, key=lambda item: (item.group, item.name))

        stored = self.update_profiles(
            replace,
            surface=surface,
            action="replace",
        )
        return next(item for item in stored if item.name == profile.name)

    def _save_data(
        self,
        data: dict[str, Any],
        profiles: Iterable[Profile],
        *,
        surface: str,
    ) -> list[Profile]:
        extra_protocols = plugin_protocols()
        prepared = [prepare_profile(profile, extra_protocols=extra_protocols) for profile in profiles]
        for profile in prepared:
            assert_profile_write_allowed(
                profile,
                surface=surface,
                action="profile-editor",
                policy_path=self.policy_path,
            )
        data["version"] = 1
        data["profiles"] = [profile.to_dict() for profile in prepared]
        write_json_atomic(self.path, data, private=True)
        return prepared

    def add(
        self,
        profile: Profile,
        replace: bool = False,
        *,
        surface: str = "cli",
        guard: ProfileWriteGuard | None = None,
    ) -> Profile:
        profile = prepare_profile(profile, extra_protocols=plugin_protocols())
        with self._transaction():
            data = self._load_data()
            profiles = self._profiles_from_data(data, resolve=False)
            names = {p.name for p in profiles}
            if profile.name in names and not replace:
                raise ValueError(f"profile already exists: {profile.name}")
            existing = next((item for item in profiles if item.name == profile.name), None)
            if guard is not None:
                guard(
                    profile,
                    existing,
                    normalize_group_defaults_map(data.get("group_defaults", {})),
                )
            assert_profile_write_allowed(
                profile,
                surface=surface,
                action="replace" if profile.name in names else "add",
                policy_path=self.policy_path,
            )
            profiles = [p for p in profiles if p.name != profile.name]
            profiles.append(profile)
            self._save_data(
                data,
                sorted(profiles, key=lambda p: (p.group, p.name)),
                surface=surface,
            )
            return profile

    def remove(self, name: str, *, surface: str = "cli") -> None:
        with self._transaction():
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
            data = self._load_data()
            profiles = self._profiles_from_data(data, resolve=False)
            remaining = [p for p in profiles if p.name != name]
            if len(remaining) == len(profiles):
                raise KeyError(name)
            self._save_data(data, remaining, surface=surface)

    def get(self, name: str) -> Profile:
        for profile in self.load():
            if profile.name == name:
                return profile
        raise KeyError(name)

    def export_to(self, path: Path) -> None:
        with self._transaction():
            data = self._load_data()
            data["profiles"] = [
                profile.to_dict() for profile in self._profiles_from_data(data, resolve=False)
            ]
        write_json_atomic(path, data, private=True)

    def import_from(self, path: Path, replace: bool = False) -> int:
        try:
            raw_data = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise ValueError(f"profile import is not valid JSON: {path}") from exc
        if not isinstance(raw_data, dict):
            raise ValueError(f"profile import root must be a JSON object: {path}")
        data: dict[str, Any] = raw_data
        rows = _profile_rows(data.get("profiles", []), source=f"profile import {path}")
        extra_protocols = plugin_protocols()
        imported: list[Profile] = []
        for index, item in enumerate(rows):
            try:
                imported.append(
                    prepare_profile(Profile.from_dict(item), extra_protocols=extra_protocols)
                )
            except (KeyError, TypeError, ValueError) as exc:
                raise ValueError(
                    f"profile import {path} profile at index {index} is invalid: {exc}"
                ) from exc

        imported_names = [profile.name for profile in imported]
        if len(set(imported_names)) != len(imported_names):
            raise ValueError("profile import contains duplicate normalized profile names")

        with self._transaction():
            current = self._load_data()
            existing = self._profiles_from_data(current, resolve=False)
            existing_names = {profile.name for profile in existing}
            collisions = [name for name in imported_names if name in existing_names]
            if collisions and not replace:
                raise ValueError(f"profile already exists: {collisions[0]}")

            for profile in imported:
                assert_profile_write_allowed(
                    profile,
                    surface="cli",
                    action="replace" if profile.name in existing_names else "add",
                    policy_path=self.policy_path,
                )

            if replace and "group_defaults" in data:
                assert_profile_collection_change_allowed(
                    surface="cli",
                    action="profile-defaults",
                    policy_path=self.policy_path,
                )
                group_defaults = normalize_group_defaults_map(data["group_defaults"])
                for defaults in group_defaults.values():
                    assert_settings_write_allowed(
                        defaults,
                        surface="cli",
                        action="profile-defaults",
                        policy_path=self.policy_path,
                    )
                current["group_defaults"] = group_defaults

            merged = {profile.name: profile for profile in existing}
            merged.update({profile.name: profile for profile in imported})
            final_profiles = sorted(
                merged.values(), key=lambda profile: (profile.group, profile.name)
            )
            self._save_data(current, final_profiles, surface="cli")
            return len(imported)

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
        group = normalize_group_name(group)
        defaults = normalize_group_defaults(defaults)
        with self._transaction():
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
            data = self._load_data()
            group_defaults = normalize_group_defaults_map(data.get("group_defaults", {}))
            data["group_defaults"] = group_defaults
            existing = {} if replace else dict(group_defaults.get(group, {}))
            existing.update(
                {key: value for key, value in defaults.items() if value not in (None, "", [], {})}
            )
            group_defaults[group] = existing
            write_json_atomic(self.path, data, private=True)

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        key = os.path.normcase(os.path.abspath(self.path))
        process_id = os.getpid()
        if getattr(_mutation_state, "process_id", None) != process_id:
            _mutation_state.process_id = process_id
            _mutation_state.paths = set()
        active_paths: set[str] = _mutation_state.paths
        if key in active_paths:
            raise ValueError(
                "reentrant profile store mutation is not allowed; callbacks may "
                f"read but must not mutate the same store: {self.path}"
            )
        try:
            with exclusive_file_lock(self.path, timeout_seconds=self.lock_timeout_seconds):
                active_paths.add(key)
                try:
                    yield
                finally:
                    active_paths.remove(key)
        except FileLockTimeoutError as exc:
            raise ValueError(f"profile store is busy; retry after the current update: {self.path}") from exc

    def _load_data(self) -> dict[str, Any]:
        if not self.path.exists():
            return {"version": 1, "profiles": [], "group_defaults": {}}
        raw_data = json.loads(self.path.read_text(encoding="utf-8"))
        if not isinstance(raw_data, dict):
            raise ValueError(f"profile store root must be a JSON object: {self.path}")
        data: dict[str, Any] = raw_data
        version = data.get("version", 1)
        if type(version) is not int or version != 1:
            raise ValueError(f"unsupported profile store version: {version!r}")
        data["version"] = version
        data["profiles"] = _profile_rows(data.get("profiles", []), source=f"profile store {self.path}")
        data["group_defaults"] = normalize_group_defaults_map(data.get("group_defaults", {}))
        return data


def _profile_rows(value: object, *, source: str) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        raise ValueError(f"{source} profiles must be a JSON array")
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            raise ValueError(f"{source} profile at index {index} must be a JSON object")
        row: dict[str, Any] = {}
        for key, field_value in item.items():
            if not isinstance(key, str):
                raise ValueError(f"{source} profile at index {index} contains a non-string key")
            row[key] = field_value
        rows.append(row)
    return rows


def _profile_fingerprint(profile: Profile) -> str:
    return json.dumps(
        profile.to_dict(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    )


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

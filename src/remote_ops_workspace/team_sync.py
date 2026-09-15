from __future__ import annotations

import json
import os
import re
import stat
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .file_safety import (
    ensure_shared_dir,
    require_shared_dir_metadata,
    require_shared_file_metadata,
    write_json_shared_atomic,
)
from .models import Profile
from .profile_sharing import (
    assert_untrusted_profile_defaults_safe,
    profile_is_shareable,
    public_profile_dict,
    shared_profile_from_dict,
)
from .profile_validation import prepare_profile
from .state_lock import FileLockTimeoutError, exclusive_file_lock
from .storage import ProfileStore

TEAM_ID_RE = re.compile(r"[a-z0-9][a-z0-9_.-]{0,63}")
TEAM_SYNC_FIELDS = frozenset(
    {"schema_version", "team", "version", "updated_at", "profiles"}
)
MAX_TEAM_SYNC_BYTES = 4 * 1024 * 1024


class TeamSyncConflictError(ValueError):
    """The shared team state changed since a client read its version."""


class TeamSyncBusyError(ValueError):
    """Another client is publishing the same team record."""


@dataclass(frozen=True, slots=True)
class TeamSyncSnapshot:
    team: str
    version: int
    updated_at: str
    profiles: tuple[Profile, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "team": self.team,
            "version": self.version,
            "updated_at": self.updated_at,
            "profiles": [team_profile_dict(profile) for profile in self.profiles],
        }


class TeamSyncBackend:
    """Versioned file-backed team catalogue for a mounted, shared directory.

    This proof-of-concept intentionally syncs connection metadata only. It never
    publishes credential references, private-key paths, or sensitive options.
    """

    def __init__(self, root: Path, *, lock_timeout_seconds: float = 5.0) -> None:
        # Resolve an intentional symlink/mount alias once. Individual shared
        # records and locks still reject final-component link indirection.
        self.root = root.expanduser().resolve(strict=False)
        self.lock_timeout_seconds = lock_timeout_seconds
        ensure_shared_dir(self.root)

    def read(self, team: str) -> TeamSyncSnapshot:
        team = validate_team_id(team)
        ensure_shared_dir(self.root)
        path = self._path(team)
        payload = _read_team_sync_bytes(path, root=self.root)
        if payload is None:
            return TeamSyncSnapshot(team=team, version=0, updated_at="", profiles=())
        raw = json.loads(payload.decode("utf-8"))
        if (
            not isinstance(raw, dict)
            or any(not isinstance(key, str) for key in raw)
            or set(raw) != TEAM_SYNC_FIELDS
            or type(raw.get("schema_version")) is not int
            or raw.get("schema_version") != 1
        ):
            raise ValueError(f"invalid team sync record: {path}")
        if raw.get("team") != team:
            raise ValueError(f"team sync record does not match requested team: {team}")
        version = raw.get("version")
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise ValueError("team sync version must be a positive integer")
        profiles = raw.get("profiles")
        if not isinstance(profiles, list):
            raise ValueError("team sync profiles must be a list")
        if any(not isinstance(item, dict) for item in profiles):
            raise ValueError("team sync profiles must contain JSON objects")
        try:
            parsed = tuple(shared_profile_from_dict(item) for item in profiles)
        except ValueError as exc:
            raise ValueError(f"invalid team sync shared profile: {exc}") from exc
        names = [profile.name for profile in parsed]
        if len(set(names)) != len(names):
            raise ValueError("team sync profile names must be unique")
        updated_at = _validate_updated_at(raw.get("updated_at"))
        return TeamSyncSnapshot(
            team=team,
            version=version,
            updated_at=updated_at,
            profiles=parsed,
        )

    def write(self, team: str, profiles: list[Profile], *, expected_version: int) -> TeamSyncSnapshot:
        team = validate_team_id(team)
        if not isinstance(expected_version, int) or isinstance(expected_version, bool) or expected_version < 0:
            raise ValueError("expected team sync version must be a non-negative integer")
        with self._write_lock(team):
            current = self.read(team)
            if current.version != expected_version:
                raise TeamSyncConflictError(
                    f"team {team} changed from version {expected_version} to {current.version}; pull before pushing"
                )
            canonical = sorted(
                (prepare_profile(profile) for profile in profiles),
                key=lambda item: (item.group, item.name),
            )
            names = [profile.name for profile in canonical]
            if len(set(names)) != len(names):
                raise ValueError("team sync profile names must be unique")
            shared_profiles = tuple(
                shared_profile_from_dict(public_profile_dict(profile))
                for profile in canonical
                if profile_is_shareable(profile)
            )
            snapshot = TeamSyncSnapshot(
                team=team,
                version=current.version + 1,
                updated_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                profiles=shared_profiles,
            )
            payload = {"schema_version": 1, **snapshot.to_dict()}
            write_json_shared_atomic(self._path(team), payload)
        return snapshot

    def _path(self, team: str) -> Path:
        return self.root / f"{team}.team-sync.json"

    @contextmanager
    def _write_lock(self, team: str) -> Iterator[None]:
        if self.lock_timeout_seconds <= 0:
            raise ValueError("team sync lock timeout must be positive")
        try:
            with exclusive_file_lock(
                self._path(team),
                timeout_seconds=self.lock_timeout_seconds,
                shared=True,
            ):
                yield
        except FileLockTimeoutError as exc:
            raise TeamSyncBusyError(
                f"team {team} is busy; retry after the current publish finishes"
            ) from exc


class TeamSyncClient:
    def __init__(self, store: ProfileStore, backend: TeamSyncBackend) -> None:
        self.store = store
        self.backend = backend

    def push(self, team: str, *, expected_version: int) -> TeamSyncSnapshot:
        return self.backend.write(team, self.store.load(resolve=False), expected_version=expected_version)

    def pull(self, team: str, *, replace: bool = False) -> TeamSyncSnapshot:
        snapshot = self.backend.read(team)
        incoming = tuple(
            prepare_profile(Profile.from_dict(remote.to_dict()))
            for remote in snapshot.profiles
        )

        def merge(
            current: list[Profile],
            group_defaults: dict[str, dict[str, object]],
        ) -> list[Profile]:
            local = {profile.name: profile for profile in current}
            received = [
                prepare_profile(Profile.from_dict(remote.to_dict()))
                for remote in incoming
            ]
            for remote in received:
                existing = local.get(remote.name)
                same_binding = assert_untrusted_profile_defaults_safe(
                    remote,
                    existing,
                    group_defaults,
                    boundary="team sync",
                )
                if same_binding and existing is not None:
                    remote.credential_ref = existing.credential_ref
                    remote.identity_file = existing.identity_file
            if replace:
                return received
            merged = dict(local)
            for remote in received:
                merged[remote.name] = remote
            return sorted(merged.values(), key=lambda item: (item.group, item.name))

        self.store.update_profiles(
            merge,
            surface="cli",
            action="team-sync-replace" if replace else "team-sync-merge",
        )
        return snapshot


def validate_team_id(value: str) -> str:
    team = str(value).strip().lower()
    if not TEAM_ID_RE.fullmatch(team):
        raise ValueError("team id must use 1-64 lowercase letters, numbers, dots, underscores or hyphens")
    return team


def team_profile_dict(profile: Profile) -> dict[str, object]:
    """Serialize shareable metadata only; secrets and machine-local paths stay local."""
    return public_profile_dict(profile)


def _read_team_sync_bytes(path: Path, *, root: Path) -> bytes | None:
    """Read one bounded regular file without following a final symlink."""

    root_status = root.stat(follow_symlinks=False)
    try:
        initial = path.lstat()
    except FileNotFoundError:
        return None
    if stat.S_ISLNK(initial.st_mode) or _is_reparse_point(initial):
        raise ValueError(f"team sync record must not be a symbolic link: {path}")
    if not stat.S_ISREG(initial.st_mode):
        raise ValueError(f"team sync record must be a regular file: {path}")
    require_shared_file_metadata(
        path,
        initial,
        root_status,
    )
    if initial.st_size > MAX_TEAM_SYNC_BYTES:
        raise ValueError(f"team sync record exceeds {MAX_TEAM_SYNC_BYTES} bytes: {path}")

    flags = os.O_RDONLY
    if hasattr(os, "O_BINARY"):
        flags |= os.O_BINARY
    if hasattr(os, "O_NOFOLLOW"):
        flags |= os.O_NOFOLLOW
    descriptor = os.open(path, flags)
    try:
        opened = os.fstat(descriptor)
        named = path.stat(follow_symlinks=False)
        if (
            not stat.S_ISREG(opened.st_mode)
            or stat.S_ISLNK(named.st_mode)
            or _is_reparse_point(named)
            or (named.st_dev, named.st_ino) != (opened.st_dev, opened.st_ino)
        ):
            raise ValueError(f"team sync record changed or is not a regular file: {path}")
        require_shared_file_metadata(path, opened, root_status)
        with os.fdopen(descriptor, "rb", closefd=False) as handle:
            payload = handle.read(MAX_TEAM_SYNC_BYTES + 1)
        if len(payload) > MAX_TEAM_SYNC_BYTES:
            raise ValueError(f"team sync record exceeds {MAX_TEAM_SYNC_BYTES} bytes: {path}")
        final = path.stat(follow_symlinks=False)
        final_root = root.stat(follow_symlinks=False)
        require_shared_dir_metadata(root, final_root)
        if (
            stat.S_ISLNK(final.st_mode)
            or _is_reparse_point(final)
            or (final.st_dev, final.st_ino) != (opened.st_dev, opened.st_ino)
            or (final_root.st_dev, final_root.st_ino, final_root.st_gid)
            != (root_status.st_dev, root_status.st_ino, root_status.st_gid)
        ):
            raise ValueError(f"team sync record changed while reading: {path}")
        require_shared_file_metadata(path, final, final_root)
        return payload
    finally:
        os.close(descriptor)


def _validate_updated_at(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("team sync updated_at must be a UTC ISO-8601 timestamp")
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError as exc:
        raise ValueError("team sync updated_at must be a UTC ISO-8601 timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise ValueError("team sync updated_at must be a UTC ISO-8601 timestamp")
    canonical = parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat()
    if value != canonical:
        raise ValueError("team sync updated_at must be a canonical UTC timestamp")
    return value


def _is_reparse_point(path_status: os.stat_result) -> bool:
    attributes = getattr(path_status, "st_file_attributes", 0)
    return bool(attributes & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))

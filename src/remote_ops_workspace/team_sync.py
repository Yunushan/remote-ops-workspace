from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from .file_safety import write_json_atomic
from .models import Profile
from .profile_validation import prepare_profile
from .storage import ProfileStore

TEAM_ID_RE = re.compile(r"[a-z0-9][a-z0-9_.-]{0,63}")
SENSITIVE_OPTION_TOKENS = ("password", "passphrase", "secret", "token", "credential", "private_key")


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
        self.root = root
        self.lock_timeout_seconds = lock_timeout_seconds

    def read(self, team: str) -> TeamSyncSnapshot:
        team = validate_team_id(team)
        path = self._path(team)
        if not path.exists():
            return TeamSyncSnapshot(team=team, version=0, updated_at="", profiles=())
        raw = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict) or raw.get("schema_version") != 1:
            raise ValueError(f"invalid team sync record: {path}")
        if raw.get("team") != team:
            raise ValueError(f"team sync record does not match requested team: {team}")
        version = raw.get("version")
        if not isinstance(version, int) or isinstance(version, bool) or version < 1:
            raise ValueError("team sync version must be a positive integer")
        profiles = raw.get("profiles")
        if not isinstance(profiles, list):
            raise ValueError("team sync profiles must be a list")
        parsed = tuple(prepare_profile(Profile.from_dict(item)) for item in profiles if isinstance(item, dict))
        if len(parsed) != len(profiles):
            raise ValueError("team sync profiles must contain JSON objects")
        return TeamSyncSnapshot(
            team=team,
            version=version,
            updated_at=str(raw.get("updated_at", "")),
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
            canonical = sorted((prepare_profile(profile) for profile in profiles), key=lambda item: (item.group, item.name))
            names = [profile.name for profile in canonical]
            if len(set(names)) != len(names):
                raise ValueError("team sync profile names must be unique")
            snapshot = TeamSyncSnapshot(
                team=team,
                version=current.version + 1,
                updated_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
                profiles=tuple(canonical),
            )
            payload = {"schema_version": 1, **snapshot.to_dict()}
            write_json_atomic(self._path(team), payload, private=True)
        return self.read(team)

    def _path(self, team: str) -> Path:
        return self.root / f"{team}.team-sync.json"

    @contextmanager
    def _write_lock(self, team: str) -> Iterator[None]:
        if self.lock_timeout_seconds <= 0:
            raise ValueError("team sync lock timeout must be positive")
        self.root.mkdir(parents=True, exist_ok=True)
        lock_path = self.root / f"{team}.team-sync.lock"
        deadline = time.monotonic() + self.lock_timeout_seconds
        descriptor: int | None = None
        while descriptor is None:
            try:
                descriptor = os.open(lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
                os.write(descriptor, b"remote-ops-workspace team sync write lock\n")
            except FileExistsError:
                if time.monotonic() >= deadline:
                    raise TeamSyncBusyError(f"team {team} is busy; retry after the current publish finishes") from None
                time.sleep(0.05)
        try:
            yield
        finally:
            if descriptor is not None:
                os.close(descriptor)
            try:
                lock_path.unlink()
            except FileNotFoundError:  # pragma: no cover - defensive shared-volume race handling
                pass


class TeamSyncClient:
    def __init__(self, store: ProfileStore, backend: TeamSyncBackend) -> None:
        self.store = store
        self.backend = backend

    def push(self, team: str, *, expected_version: int) -> TeamSyncSnapshot:
        return self.backend.write(team, self.store.load(resolve=False), expected_version=expected_version)

    def pull(self, team: str, *, replace: bool = False) -> TeamSyncSnapshot:
        snapshot = self.backend.read(team)
        if replace:
            self.store.save(snapshot.profiles, surface="cli")
            return snapshot
        local = {profile.name: profile for profile in self.store.load(resolve=False)}
        merged = dict(local)
        for remote in snapshot.profiles:
            existing = local.get(remote.name)
            if existing is not None:
                remote.credential_ref = existing.credential_ref
                remote.identity_file = existing.identity_file
            merged[remote.name] = remote
        self.store.save(merged.values(), surface="cli")
        return snapshot


def validate_team_id(value: str) -> str:
    team = str(value).strip().lower()
    if not TEAM_ID_RE.fullmatch(team):
        raise ValueError("team id must use 1-64 lowercase letters, numbers, dots, underscores or hyphens")
    return team


def team_profile_dict(profile: Profile) -> dict[str, object]:
    """Serialize shareable metadata only; secrets and machine-local paths stay local."""
    options = {
        key: value
        for key, value in profile.options.items()
        if not any(token in key.lower() for token in SENSITIVE_OPTION_TOKENS)
    }
    return {
        "name": profile.name,
        "protocol": profile.protocol,
        "host": profile.host,
        "port": profile.port,
        "username": profile.username,
        "group": profile.group,
        "tags": profile.tags,
        "description": profile.description,
        "path": profile.path,
        "url": profile.url,
        "command": profile.command,
        "tunnels": [tunnel.to_dict() for tunnel in profile.tunnels],
        "options": options,
    }

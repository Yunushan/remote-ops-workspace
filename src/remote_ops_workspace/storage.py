from __future__ import annotations

import json
from pathlib import Path
from typing import Iterable

from .models import Profile
from .paths import ensure_data_dir


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

    def load(self) -> list[Profile]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return [Profile.from_dict(item) for item in data.get("profiles", [])]

    def save(self, profiles: Iterable[Profile]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"version": 1, "profiles": [profile.to_dict() for profile in profiles]}
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    def add(self, profile: Profile, replace: bool = False) -> None:
        profiles = self.load()
        names = {p.name for p in profiles}
        if profile.name in names and not replace:
            raise ValueError(f"profile already exists: {profile.name}")
        profiles = [p for p in profiles if p.name != profile.name]
        profiles.append(profile)
        self.save(sorted(profiles, key=lambda p: (p.group, p.name)))

    def remove(self, name: str) -> None:
        profiles = self.load()
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
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps({"version": 1, "profiles": [p.to_dict() for p in self.load()]}, indent=2), encoding="utf-8")

    def import_from(self, path: Path, replace: bool = False) -> int:
        data = json.loads(path.read_text(encoding="utf-8"))
        count = 0
        for item in data.get("profiles", []):
            self.add(Profile.from_dict(item), replace=replace)
            count += 1
        return count


def example_profiles() -> list[Profile]:
    return [
        Profile(
            name="example-ssh",
            protocol="ssh",
            host="192.0.2.10",
            port=22,
            username="admin",
            group="examples",
            tags=["ssh", "demo"],
            description="Example OpenSSH profile using documentation IP address.",
        ),
        Profile(
            name="example-rdp",
            protocol="rdp",
            host="192.0.2.20",
            port=3389,
            username="administrator",
            group="examples",
            tags=["rdp", "windows"],
            description="Example RDP profile. Uses MSTSC on Windows or FreeRDP elsewhere.",
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

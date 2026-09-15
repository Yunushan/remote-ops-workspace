from __future__ import annotations

import json
import subprocess
from collections.abc import Iterable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import command_safety as safe
from .enterprise_policy import assert_profile_launch_allowed
from .file_safety import write_json_atomic
from .models import Profile
from .paths import ensure_data_dir
from .state_lock import DEFAULT_LOCK_TIMEOUT_SECONDS, FileLockTimeoutError, exclusive_file_lock


@dataclass(slots=True)
class Snippet:
    name: str
    command: str
    description: str = ""
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Snippet:
        return cls(
            name=str(data["name"]),
            command=str(data["command"]),
            description=str(data.get("description", "")),
            tags=[str(tag) for tag in data.get("tags", [])],
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "command": self.command,
            "description": self.description,
            "tags": self.tags,
        }

    @property
    def argv(self) -> list[str]:
        return safe.argv(self.command, f"snippet {self.name}")


class SnippetStore:
    def __init__(
        self,
        path: Path | None = None,
        *,
        lock_timeout_seconds: float = DEFAULT_LOCK_TIMEOUT_SECONDS,
    ) -> None:
        self.path = path or (ensure_data_dir() / "snippets.json")
        self.lock_timeout_seconds = lock_timeout_seconds

    def load(self) -> list[Snippet]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        rows = _snippet_rows(data, self.path)
        return [Snippet.from_dict(item) for item in rows]

    def save(self, snippets: Iterable[Snippet]) -> None:
        with self._transaction():
            self._save_unlocked(snippets)

    def add(self, snippet: Snippet, replace: bool = False) -> None:
        with self._transaction():
            snippets = self.load()
            names = {item.name for item in snippets}
            if snippet.name in names and not replace:
                raise ValueError(f"snippet already exists: {snippet.name}")
            snippets = [item for item in snippets if item.name != snippet.name]
            snippets.append(snippet)
            self._save_unlocked(sorted(snippets, key=lambda item: item.name))

    def get(self, name: str) -> Snippet:
        for snippet in self.load():
            if snippet.name == name:
                return snippet
        raise KeyError(name)

    def remove(self, name: str) -> None:
        with self._transaction():
            snippets = self.load()
            remaining = [item for item in snippets if item.name != name]
            if len(remaining) == len(snippets):
                raise KeyError(name)
            self._save_unlocked(remaining)

    def _save_unlocked(self, snippets: Iterable[Snippet]) -> None:
        data = {"version": 1, "snippets": [snippet.to_dict() for snippet in snippets]}
        write_json_atomic(self.path, data, private=True)

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        try:
            with exclusive_file_lock(self.path, timeout_seconds=self.lock_timeout_seconds):
                yield
        except FileLockTimeoutError as exc:
            raise ValueError(f"snippet store is busy; retry after the current update: {self.path}") from exc


def _snippet_rows(data: object, path: Path) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        raise ValueError(f"snippet store root must be a JSON object: {path}")
    version = data.get("version", 1)
    if type(version) is not int or version != 1:
        raise ValueError(f"unsupported snippet store version: {version!r}")
    rows = data.get("snippets", [])
    if not isinstance(rows, list) or any(not isinstance(item, dict) for item in rows):
        raise ValueError("snippet store records must be JSON objects")
    return rows


def run_snippet(
    snippet: Snippet,
    dry_run: bool = False,
    *,
    policy_path: Path | None = None,
) -> list[str]:
    assert_profile_launch_allowed(
        Profile(
            name=f"snippet-{snippet.name}",
            protocol="custom",
            command=snippet.command,
            group="snippets",
        ),
        surface="launcher",
        policy_path=policy_path,
    )
    argv = snippet.argv
    safe.argv_list(argv, f"snippet {snippet.name}")
    if not dry_run:
        subprocess.run(argv, check=True)  # noqa: S603 - user-owned snippet, argv list, no shell
    return argv

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

from . import command_safety as safe
from .paths import ensure_data_dir


@dataclass(slots=True)
class Snippet:
    name: str
    command: str
    description: str = ""
    tags: list[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Snippet":
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
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (ensure_data_dir() / "snippets.json")

    def load(self) -> list[Snippet]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return [Snippet.from_dict(item) for item in data.get("snippets", [])]

    def save(self, snippets: Iterable[Snippet]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        data = {"version": 1, "snippets": [snippet.to_dict() for snippet in snippets]}
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    def add(self, snippet: Snippet, replace: bool = False) -> None:
        snippets = self.load()
        names = {item.name for item in snippets}
        if snippet.name in names and not replace:
            raise ValueError(f"snippet already exists: {snippet.name}")
        snippets = [item for item in snippets if item.name != snippet.name]
        snippets.append(snippet)
        self.save(sorted(snippets, key=lambda item: item.name))

    def get(self, name: str) -> Snippet:
        for snippet in self.load():
            if snippet.name == name:
                return snippet
        raise KeyError(name)

    def remove(self, name: str) -> None:
        snippets = self.load()
        remaining = [item for item in snippets if item.name != name]
        if len(remaining) == len(snippets):
            raise KeyError(name)
        self.save(remaining)


def run_snippet(snippet: Snippet, dry_run: bool = False) -> list[str]:
    argv = snippet.argv
    safe.argv_list(argv, f"snippet {snippet.name}")
    if not dry_run:
        subprocess.run(argv, check=True)  # noqa: S603 - user-owned snippet, argv list, no shell
    return argv

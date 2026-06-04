from __future__ import annotations

import json
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import command_safety as safe
from .file_safety import write_json_atomic
from .paths import ensure_data_dir
from .storage import ProfileStore
from .terminal import TerminalPanePlan, terminal_plan_for_command, terminal_plan_for_profile

LAYOUT_ORIENTATIONS = {"grid", "horizontal", "vertical"}


@dataclass(slots=True)
class LayoutPane:
    profile: str | None = None
    command: str | None = None
    title: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LayoutPane:
        return cls(
            profile=_optional_str(data.get("profile")),
            command=_optional_str(data.get("command")),
            title=str(data.get("title", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {"profile": self.profile, "command": self.command, "title": self.title}


@dataclass(slots=True)
class Layout:
    name: str
    orientation: str = "grid"
    panes: list[LayoutPane] = field(default_factory=list)
    description: str = ""

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Layout:
        return cls(
            name=str(data["name"]),
            orientation=str(data.get("orientation", "grid")),
            panes=[LayoutPane.from_dict(item) for item in data.get("panes", [])],
            description=str(data.get("description", "")),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "orientation": self.orientation,
            "panes": [pane.to_dict() for pane in self.panes],
            "description": self.description,
        }


class LayoutStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (ensure_data_dir() / "layouts.json")

    def load(self) -> list[Layout]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return [Layout.from_dict(item) for item in data.get("layouts", [])]

    def save(self, layouts: Iterable[Layout]) -> None:
        data = {"version": 1, "layouts": [layout.to_dict() for layout in layouts]}
        write_json_atomic(self.path, data, private=True)

    def add(self, layout: Layout, replace: bool = False) -> None:
        validate_layout(layout)
        layouts = self.load()
        names = {item.name for item in layouts}
        if layout.name in names and not replace:
            raise ValueError(f"layout already exists: {layout.name}")
        layouts = [item for item in layouts if item.name != layout.name]
        layouts.append(layout)
        self.save(sorted(layouts, key=lambda item: item.name))

    def get(self, name: str) -> Layout:
        for layout in self.load():
            if layout.name == name:
                return layout
        raise KeyError(name)

    def remove(self, name: str) -> None:
        layouts = self.load()
        remaining = [item for item in layouts if item.name != name]
        if len(remaining) == len(layouts):
            raise KeyError(name)
        self.save(remaining)


def parse_layout_pane(raw: str) -> LayoutPane:
    raw = safe.clean_text(raw, "layout pane")
    if raw.startswith("profile:"):
        return LayoutPane(profile=safe.clean_text(raw.split(":", 1)[1], "layout profile"))
    if raw.startswith("command:"):
        return LayoutPane(command=safe.shellish_text(raw.split(":", 1)[1], "layout command"))
    return LayoutPane(profile=safe.clean_text(raw, "layout profile"))


@dataclass(slots=True)
class LayoutRunResult:
    title: str
    command: list[str]
    pid: int | None = None
    dry_run: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "title": self.title,
            "command": self.command,
            "pid": self.pid,
            "dry_run": self.dry_run,
        }


def validate_layout(layout: Layout) -> None:
    if layout.orientation not in LAYOUT_ORIENTATIONS:
        raise ValueError(f"layout orientation must be one of: {', '.join(sorted(LAYOUT_ORIENTATIONS))}")
    if not layout.panes:
        raise ValueError("layout requires at least one pane")
    for pane in layout.panes:
        if bool(pane.profile) == bool(pane.command):
            raise ValueError("each layout pane must define exactly one of profile or command")
        if pane.profile:
            safe.clean_text(pane.profile, "layout profile")
        if pane.command:
            safe.argv(pane.command, "layout command")
        if pane.title:
            safe.clean_text(pane.title, "layout pane title")


def build_layout_terminal_plans(
    layout: Layout,
    store: ProfileStore | None = None,
) -> list[TerminalPanePlan]:
    validate_layout(layout)
    store = store or ProfileStore()
    plans: list[TerminalPanePlan] = []
    for index, pane in enumerate(layout.panes, start=1):
        if pane.profile:
            plan = terminal_plan_for_profile(store.get(pane.profile))
        elif pane.command:
            plan = terminal_plan_for_command(pane.command, title=pane.title or f"Command {index}")
        else:  # pragma: no cover - validate_layout covers this
            raise ValueError("layout pane is missing profile or command")
        if pane.title:
            plan.title = pane.title
        plans.append(plan)
    return plans


def run_layout_terminal_plans(
    plans: list[TerminalPanePlan],
    dry_run: bool = False,
) -> list[LayoutRunResult]:
    results: list[LayoutRunResult] = []
    for plan in plans:
        safe.argv_list(plan.command, f"layout pane {plan.title}")
        if dry_run:
            results.append(LayoutRunResult(title=plan.title, command=plan.command, dry_run=True))
            continue
        process = subprocess.Popen(plan.command)  # noqa: S603 - argv list, no shell
        results.append(LayoutRunResult(title=plan.title, command=plan.command, pid=process.pid))
    return results


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    value = str(value)
    return value if value else None

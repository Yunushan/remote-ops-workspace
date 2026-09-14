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
    splitter_sizes: list[list[int]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Layout:
        return cls(
            name=str(data["name"]),
            orientation=str(data.get("orientation", "grid")),
            panes=[LayoutPane.from_dict(item) for item in data.get("panes", [])],
            description=str(data.get("description", "")),
            splitter_sizes=_splitter_sizes(data.get("splitter_sizes", [])),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "orientation": self.orientation,
            "panes": [pane.to_dict() for pane in self.panes],
            "description": self.description,
            "splitter_sizes": self.splitter_sizes,
        }


class LayoutStore:
    def __init__(
        self,
        path: Path | None = None,
        *,
        lock_timeout_seconds: float = DEFAULT_LOCK_TIMEOUT_SECONDS,
    ) -> None:
        self.path = path or (ensure_data_dir() / "layouts.json")
        self.lock_timeout_seconds = lock_timeout_seconds

    def load(self) -> list[Layout]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        rows = _versioned_store_rows(data, "layouts", self.path)
        return [Layout.from_dict(item) for item in rows]

    def save(self, layouts: Iterable[Layout]) -> None:
        with self._transaction():
            self._save_unlocked(layouts)

    def add(self, layout: Layout, replace: bool = False) -> None:
        validate_layout(layout)
        with self._transaction():
            layouts = self.load()
            names = {item.name for item in layouts}
            if layout.name in names and not replace:
                raise ValueError(f"layout already exists: {layout.name}")
            layouts = [item for item in layouts if item.name != layout.name]
            layouts.append(layout)
            self._save_unlocked(sorted(layouts, key=lambda item: item.name))

    def get(self, name: str) -> Layout:
        for layout in self.load():
            if layout.name == name:
                return layout
        raise KeyError(name)

    def remove(self, name: str) -> None:
        with self._transaction():
            layouts = self.load()
            remaining = [item for item in layouts if item.name != name]
            if len(remaining) == len(layouts):
                raise KeyError(name)
            self._save_unlocked(remaining)

    def replace_named(self, original_name: str, layout: Layout) -> Layout:
        validate_layout(layout)
        with self._transaction():
            layouts = self.load()
            if not any(item.name == original_name for item in layouts):
                raise KeyError(original_name)
            if layout.name != original_name and any(
                item.name == layout.name for item in layouts
            ):
                raise ValueError(f"layout already exists: {layout.name}")
            remaining = [item for item in layouts if item.name != original_name]
            remaining.append(layout)
            self._save_unlocked(sorted(remaining, key=lambda item: item.name))
        return layout

    def update_splitter_sizes(self, name: str, sizes: list[list[int]]) -> bool:
        normalized_sizes = _splitter_sizes(sizes)
        with self._transaction():
            layouts = self.load()
            for layout in layouts:
                if layout.name != name:
                    continue
                if layout.splitter_sizes == normalized_sizes:
                    return False
                layout.splitter_sizes = normalized_sizes
                validate_layout(layout)
                self._save_unlocked(layouts)
                return True
        return False

    def _save_unlocked(self, layouts: Iterable[Layout]) -> None:
        data = {"version": 1, "layouts": [layout.to_dict() for layout in layouts]}
        write_json_atomic(self.path, data, private=True)

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        try:
            with exclusive_file_lock(self.path, timeout_seconds=self.lock_timeout_seconds):
                yield
        except FileLockTimeoutError as exc:
            raise ValueError(f"layout store is busy; retry after the current update: {self.path}") from exc


def _versioned_store_rows(data: object, key: str, path: Path) -> list[dict[str, Any]]:
    if not isinstance(data, dict):
        raise ValueError(f"{key} store root must be a JSON object: {path}")
    version = data.get("version", 1)
    if type(version) is not int or version != 1:
        raise ValueError(f"unsupported {key} store version: {version!r}")
    rows = data.get(key, [])
    if not isinstance(rows, list) or any(not isinstance(item, dict) for item in rows):
        raise ValueError(f"{key} store records must be JSON objects")
    return rows


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
    expected_sizes = layout_splitter_size_lengths(layout)
    if layout.splitter_sizes:
        if len(layout.splitter_sizes) != len(expected_sizes):
            raise ValueError(
                f"layout splitter_sizes must contain {len(expected_sizes)} splitter entries for this layout"
            )
        for index, (sizes, expected_length) in enumerate(
            zip(layout.splitter_sizes, expected_sizes, strict=True), start=1
        ):
            if len(sizes) != expected_length:
                raise ValueError(f"layout splitter_sizes entry {index} must contain {expected_length} positive sizes")
            if any(not isinstance(size, int) or isinstance(size, bool) or size <= 0 for size in sizes):
                raise ValueError(f"layout splitter_sizes entry {index} must contain positive integers")


def layout_splitter_size_lengths(layout: Layout) -> list[int]:
    """Return pre-order QSplitter child counts for a saved layout."""
    pane_count = len(layout.panes)
    if pane_count <= 1:
        return []
    if layout.orientation in {"horizontal", "vertical"}:
        return [pane_count]
    row_lengths = [min(2, pane_count - offset) for offset in range(0, pane_count, 2)]
    return [len(row_lengths), *row_lengths]


def build_layout_terminal_plans(
    layout: Layout,
    store: ProfileStore | None = None,
) -> list[TerminalPanePlan]:
    """Build plans from one consistent profile-store snapshot."""

    return [
        plan
        for plan, _profile in build_layout_terminal_sessions(
            layout,
            store,
            surface="launcher",
        )
    ]


def build_layout_terminal_sessions(
    layout: Layout,
    store: ProfileStore | None = None,
    *,
    surface: str = "launcher",
) -> list[tuple[TerminalPanePlan, Profile]]:
    """Resolve each layout pane to a plan/profile pair from one snapshot."""

    validate_layout(layout)
    store = store or ProfileStore()
    profiles = store.load() if any(pane.profile for pane in layout.panes) else []
    sessions: list[tuple[TerminalPanePlan, Profile]] = []
    for index, pane in enumerate(layout.panes, start=1):
        if pane.profile:
            try:
                profile = next(
                    profile for profile in profiles if profile.name == pane.profile
                )
            except StopIteration as exc:
                raise KeyError(pane.profile) from exc
        elif pane.command:
            profile = Profile(
                name=f"layout-{layout.name}-{index}",
                protocol="custom",
                command=pane.command,
                group="layout",
            )
        else:  # pragma: no cover - validate_layout covers this
            raise ValueError("layout pane is missing profile or command")
        assert_profile_launch_allowed(
            profile,
            surface=surface,
            policy_path=getattr(store, "policy_path", None),
        )
        plan = (
            terminal_plan_for_profile(profile)
            if pane.profile
            else terminal_plan_for_command(
                pane.command or "",
                title=pane.title or f"Command {index}",
            )
        )
        if pane.title:
            plan.title = pane.title
        sessions.append((plan, profile))
    return sessions


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


def _splitter_sizes(value: Any) -> list[list[int]]:
    if value in (None, ""):
        return []
    if not isinstance(value, list):
        raise ValueError("layout splitter_sizes must be a list")
    sizes: list[list[int]] = []
    for entry in value:
        if not isinstance(entry, list):
            raise ValueError("layout splitter_sizes entries must be lists")
        sizes.append(list(entry))
    return sizes

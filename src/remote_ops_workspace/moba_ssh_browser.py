from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import command_safety as safe
from .file_safety import write_json_atomic
from .launcher import LaunchPlan
from .moba_connected import build_same_parameters_sftp_plan
from .models import Profile
from .paths import ensure_data_dir

MOBA_SSH_BROWSER_LOCATIONS = {"side-by-side", "below-terminal", "hidden"}
MOBA_SSH_BROWSER_DEFAULT_LOCATION = "side-by-side"
MOBA_SSH_BROWSER_DEFAULT_COLUMNS = {
    "name": 182,
    "size": 78,
    "modified": 94,
}
MOBA_SSH_BROWSER_MIN_COLUMN_WIDTH = 48
MOBA_SSH_BROWSER_MAX_COLUMN_WIDTH = 640


@dataclass(slots=True)
class MobaSshBrowserPreferences:
    location: str
    column_widths: dict[str, int]
    overwrite_confirmation: bool
    updated_at: str

    @classmethod
    def default(cls) -> MobaSshBrowserPreferences:
        return cls(
            location=MOBA_SSH_BROWSER_DEFAULT_LOCATION,
            column_widths=dict(MOBA_SSH_BROWSER_DEFAULT_COLUMNS),
            overwrite_confirmation=True,
            updated_at=_now(),
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MobaSshBrowserPreferences:
        preferences = cls.default()
        location = _location(str(data.get("location") or preferences.location))
        raw_columns = data.get("column_widths") or {}
        if not isinstance(raw_columns, dict):
            raise ValueError("ssh-browser column_widths must be an object")
        column_widths = dict(preferences.column_widths)
        for key, value in raw_columns.items():
            column_widths[_column_key(str(key))] = _column_width(int(value))
        return cls(
            location=location,
            column_widths=column_widths,
            overwrite_confirmation=bool(data.get("overwrite_confirmation", True)),
            updated_at=safe.clean_text(str(data.get("updated_at") or _now()), "ssh-browser updated_at"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "location": self.location,
            "column_widths": dict(self.column_widths),
            "overwrite_confirmation": self.overwrite_confirmation,
            "updated_at": self.updated_at,
        }


@dataclass(slots=True)
class MobaSshBrowserOpenPlan:
    profile_name: str
    location: str
    terminal_visible: bool
    browser_visible: bool
    command: list[str]
    column_widths: dict[str, int]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile_name,
            "location": self.location,
            "terminal_visible": self.terminal_visible,
            "browser_visible": self.browser_visible,
            "command": self.command,
            "column_widths": dict(self.column_widths),
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobaSshBrowserOverwriteReview:
    action: str
    source_path: str
    destination_path: str
    destination_exists: bool
    force: bool
    confirmation_required: bool
    allowed: bool
    prompt: str
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "source_path": self.source_path,
            "destination_path": self.destination_path,
            "destination_exists": self.destination_exists,
            "force": self.force,
            "confirmation_required": self.confirmation_required,
            "allowed": self.allowed,
            "prompt": self.prompt,
            "notes": self.notes,
        }


def load_moba_ssh_browser_preferences(path: Path | None = None) -> MobaSshBrowserPreferences:
    state_path = moba_ssh_browser_state_path(path)
    if not state_path.exists():
        return MobaSshBrowserPreferences.default()
    data = json.loads(state_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"ssh-browser state must be a JSON object: {state_path}")
    return MobaSshBrowserPreferences.from_dict(data)


def save_moba_ssh_browser_preferences(
    preferences: MobaSshBrowserPreferences,
    path: Path | None = None,
) -> MobaSshBrowserPreferences:
    state_path = moba_ssh_browser_state_path(path)
    preferences.updated_at = _now()
    write_json_atomic(state_path, preferences.to_dict(), private=True)
    return preferences


def update_moba_ssh_browser_location(
    location: str,
    *,
    path: Path | None = None,
) -> MobaSshBrowserPreferences:
    preferences = load_moba_ssh_browser_preferences(path)
    preferences.location = _location(location)
    return save_moba_ssh_browser_preferences(preferences, path)


def update_moba_ssh_browser_columns(
    widths: dict[str, int],
    *,
    path: Path | None = None,
) -> MobaSshBrowserPreferences:
    preferences = load_moba_ssh_browser_preferences(path)
    for key, value in widths.items():
        preferences.column_widths[_column_key(key)] = _column_width(int(value))
    return save_moba_ssh_browser_preferences(preferences, path)


def build_moba_ssh_browser_open_plan(
    profile: Profile,
    *,
    preferences: MobaSshBrowserPreferences | None = None,
) -> MobaSshBrowserOpenPlan:
    prefs = preferences or load_moba_ssh_browser_preferences()
    plan: LaunchPlan = build_same_parameters_sftp_plan(profile)
    browser_visible = prefs.location != "hidden"
    terminal_visible = prefs.location in {"side-by-side", "below-terminal", "hidden"}
    notes = [
        "MobaXterm 26.4-style SSH-browser open plan using the same SSH/SFTP parameters.",
        "Side-by-side location keeps the terminal and SSH-browser visible at the same time.",
        *plan.notes,
    ]
    if prefs.location == "below-terminal":
        notes.append("Legacy below-terminal browser placement requested.")
    if prefs.location == "hidden":
        notes.append("SSH-browser starts hidden but same-parameter SFTP plan is still available.")
    return MobaSshBrowserOpenPlan(
        profile_name=profile.name,
        location=prefs.location,
        terminal_visible=terminal_visible,
        browser_visible=browser_visible,
        command=plan.command,
        column_widths=dict(prefs.column_widths),
        notes=notes,
    )


def review_moba_ssh_browser_overwrite(
    action: str,
    source_path: str,
    destination_path: str,
    *,
    destination_exists: bool,
    force: bool = False,
    preferences: MobaSshBrowserPreferences | None = None,
) -> MobaSshBrowserOverwriteReview:
    action_key = safe.option_value(action, "ssh-browser transfer action").lower()
    if action_key not in {"upload", "download"}:
        raise ValueError("ssh-browser overwrite review action must be upload or download")
    source = safe.path_arg(source_path, "ssh-browser transfer source")
    destination = safe.path_arg(destination_path, "ssh-browser transfer destination")
    prefs = preferences or load_moba_ssh_browser_preferences()
    confirmation_required = bool(destination_exists and prefs.overwrite_confirmation and not force)
    allowed = not confirmation_required
    prompt = ""
    if confirmation_required:
        prompt = f"{action_key} would overwrite {destination}; confirm before continuing"
    notes = ["MobaXterm 26.4-style SSH-browser overwrite confirmation review."]
    if force:
        notes.append("Overwrite force flag supplied; confirmation is treated as accepted.")
    elif confirmation_required:
        notes.append("Overwrite confirmation is required before running the transfer.")
    return MobaSshBrowserOverwriteReview(
        action=action_key,
        source_path=source,
        destination_path=destination,
        destination_exists=bool(destination_exists),
        force=bool(force),
        confirmation_required=confirmation_required,
        allowed=allowed,
        prompt=prompt,
        notes=notes,
    )


def moba_ssh_browser_state_path(path: Path | None = None) -> Path:
    return path or (ensure_data_dir() / "moba-ssh-browser-state.json")


def _location(value: str) -> str:
    location = safe.option_value(value, "ssh-browser location").lower()
    if location not in MOBA_SSH_BROWSER_LOCATIONS:
        allowed = ", ".join(sorted(MOBA_SSH_BROWSER_LOCATIONS))
        raise ValueError(f"ssh-browser location must be one of: {allowed}")
    return location


def _column_key(value: str) -> str:
    key = safe.option_value(value, "ssh-browser column key").lower()
    if key not in MOBA_SSH_BROWSER_DEFAULT_COLUMNS:
        allowed = ", ".join(MOBA_SSH_BROWSER_DEFAULT_COLUMNS)
        raise ValueError(f"ssh-browser column key must be one of: {allowed}")
    return key


def _column_width(value: int) -> int:
    width = int(value)
    if not MOBA_SSH_BROWSER_MIN_COLUMN_WIDTH <= width <= MOBA_SSH_BROWSER_MAX_COLUMN_WIDTH:
        raise ValueError(
            "ssh-browser column width must be between "
            f"{MOBA_SSH_BROWSER_MIN_COLUMN_WIDTH} and {MOBA_SSH_BROWSER_MAX_COLUMN_WIDTH}"
        )
    return width


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

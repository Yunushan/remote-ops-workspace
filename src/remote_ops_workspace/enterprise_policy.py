from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import command_safety as safe
from .models import Profile
from .paths import data_dir

PROFILE_FIELD_KEYS = {
    "name",
    "protocol",
    "host",
    "port",
    "username",
    "group",
    "tags",
    "description",
    "path",
    "url",
    "command",
    "credential_ref",
    "identity_file",
}
PROFILE_SURFACES = {"cli", "gui", "profile-editor", "quick-connect", "launcher", "web"}


@dataclass(frozen=True, slots=True)
class LockedSetting:
    key: str
    value: str

    def to_dict(self) -> dict[str, str]:
        return {"key": self.key, "value": self.value}


@dataclass(frozen=True, slots=True)
class EnterprisePolicy:
    path: Path
    active: bool = False
    allow_user_profiles: bool = True
    allow_custom_commands: bool = False
    locked_settings: tuple[LockedSetting, ...] = ()
    schema_version: int = 1

    def locked_value(self, key: str) -> str | None:
        for item in self.locked_settings:
            if item.key == key:
                return item.value
        return None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "active": self.active,
            "path": str(self.path),
            "allow_user_profiles": self.allow_user_profiles,
            "allow_custom_commands": self.allow_custom_commands,
            "locked_settings": [item.to_dict() for item in self.locked_settings],
            "surfaces": sorted(PROFILE_SURFACES),
        }

    def to_public_dict(self) -> dict[str, Any]:
        payload = self.to_dict()
        payload.pop("path", None)
        return payload


@dataclass(frozen=True, slots=True)
class EnterprisePolicyReview:
    surface: str
    action: str
    allowed: bool
    blocked: tuple[str, ...] = ()
    enforced_settings: tuple[LockedSetting, ...] = ()
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "surface": self.surface,
            "action": self.action,
            "allowed": self.allowed,
            "blocked": list(self.blocked),
            "enforced_settings": [item.to_dict() for item in self.enforced_settings],
            "notes": list(self.notes),
        }


def enterprise_policy_path(root: Path | None = None) -> Path:
    return (root or data_dir()) / "policy.json"


def load_enterprise_policy(path: Path | None = None) -> EnterprisePolicy:
    policy_path = Path(path) if path is not None else enterprise_policy_path()
    if not policy_path.exists():
        return EnterprisePolicy(path=policy_path)
    data = json.loads(policy_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"enterprise policy must be a JSON object: {policy_path}")
    locked_settings = tuple(_locked_settings(data.get("locked_settings", [])))
    return EnterprisePolicy(
        path=policy_path,
        active=True,
        allow_user_profiles=bool(data.get("allow_user_profiles", True)),
        allow_custom_commands=bool(data.get("allow_custom_commands", False)),
        locked_settings=locked_settings,
        schema_version=int(data.get("schema_version", 1)),
    )


def review_profile_write(
    profile: Profile,
    *,
    surface: str,
    action: str,
    policy: EnterprisePolicy | None = None,
    policy_path: Path | None = None,
) -> EnterprisePolicyReview:
    policy = policy or load_enterprise_policy(policy_path)
    surface = _surface(surface)
    action = safe.option_value(action, "policy action")
    if not policy.active:
        return EnterprisePolicyReview(surface=surface, action=action, allowed=True)

    blocked: list[str] = []
    notes: list[str] = []
    if not policy.allow_user_profiles and action in {"add", "replace", "import", "profile-editor", "quick-connect"}:
        blocked.append("user profile changes are disabled by enterprise policy")
    if profile.command and not policy.allow_custom_commands:
        blocked.append("custom command profiles are disabled by enterprise policy")
    blocked.extend(_locked_profile_mismatches(profile, policy, surface=surface))
    if policy.locked_settings:
        notes.append(f"{len(policy.locked_settings)} locked enterprise settings loaded")
    return EnterprisePolicyReview(
        surface=surface,
        action=action,
        allowed=not blocked,
        blocked=tuple(blocked),
        enforced_settings=policy.locked_settings,
        notes=tuple(notes),
    )


def review_profile_launch(
    profile: Profile,
    *,
    surface: str = "launcher",
    policy: EnterprisePolicy | None = None,
    policy_path: Path | None = None,
) -> EnterprisePolicyReview:
    policy = policy or load_enterprise_policy(policy_path)
    surface = _surface(surface)
    if not policy.active:
        return EnterprisePolicyReview(surface=surface, action="launch", allowed=True)
    blocked: list[str] = []
    if profile.command and not policy.allow_custom_commands:
        blocked.append("custom command profiles are disabled by enterprise policy")
    blocked.extend(_locked_profile_mismatches(profile, policy, surface=surface))
    return EnterprisePolicyReview(
        surface=surface,
        action="launch",
        allowed=not blocked,
        blocked=tuple(blocked),
        enforced_settings=policy.locked_settings,
    )


def review_settings_write(
    settings: dict[str, Any],
    *,
    surface: str,
    action: str,
    policy: EnterprisePolicy | None = None,
    policy_path: Path | None = None,
) -> EnterprisePolicyReview:
    policy = policy or load_enterprise_policy(policy_path)
    surface = _surface(surface)
    action = safe.option_value(action, "policy action")
    if not policy.active:
        return EnterprisePolicyReview(surface=surface, action=action, allowed=True)

    blocked: list[str] = []
    flat = _flatten_settings(settings)
    for item in policy.locked_settings:
        if item.key in flat and flat[item.key] != item.value:
            blocked.append(
                f"{surface} cannot set locked enterprise setting {item.key}={flat[item.key]!r}; required {item.value!r}"
            )
    return EnterprisePolicyReview(
        surface=surface,
        action=action,
        allowed=not blocked,
        blocked=tuple(blocked),
        enforced_settings=policy.locked_settings,
    )


def review_profile_collection_change(
    *,
    surface: str,
    action: str,
    policy: EnterprisePolicy | None = None,
    policy_path: Path | None = None,
) -> EnterprisePolicyReview:
    policy = policy or load_enterprise_policy(policy_path)
    surface = _surface(surface)
    action = safe.option_value(action, "policy action")
    if not policy.active:
        return EnterprisePolicyReview(surface=surface, action=action, allowed=True)
    blocked: list[str] = []
    if not policy.allow_user_profiles:
        blocked.append("user profile changes are disabled by enterprise policy")
    return EnterprisePolicyReview(
        surface=surface,
        action=action,
        allowed=not blocked,
        blocked=tuple(blocked),
        enforced_settings=policy.locked_settings,
    )


def assert_profile_write_allowed(
    profile: Profile,
    *,
    surface: str,
    action: str,
    policy_path: Path | None = None,
) -> None:
    review = review_profile_write(profile, surface=surface, action=action, policy_path=policy_path)
    _raise_if_blocked(review)


def assert_profile_launch_allowed(
    profile: Profile,
    *,
    surface: str = "launcher",
    policy_path: Path | None = None,
) -> None:
    review = review_profile_launch(profile, surface=surface, policy_path=policy_path)
    _raise_if_blocked(review)


def assert_settings_write_allowed(
    settings: dict[str, Any],
    *,
    surface: str,
    action: str,
    policy_path: Path | None = None,
) -> None:
    review = review_settings_write(settings, surface=surface, action=action, policy_path=policy_path)
    _raise_if_blocked(review)


def assert_profile_collection_change_allowed(
    *,
    surface: str,
    action: str,
    policy_path: Path | None = None,
) -> None:
    review = review_profile_collection_change(surface=surface, action=action, policy_path=policy_path)
    _raise_if_blocked(review)


def _locked_settings(raw: Any) -> list[LockedSetting]:
    if not isinstance(raw, list):
        raise ValueError("enterprise policy locked_settings must be a list")
    locked: list[LockedSetting] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict) or "key" not in item or "value" not in item:
            raise ValueError("enterprise policy locked_settings entries must contain key and value")
        key = safe.option_value(str(item["key"]), "locked setting key")
        value = safe.clean_text(str(item["value"]), "locked setting value", allow_empty=True)
        if key in seen:
            raise ValueError(f"duplicate locked enterprise setting: {key}")
        locked.append(LockedSetting(key=key, value=value))
        seen.add(key)
    return locked


def _surface(value: str) -> str:
    surface = safe.option_value(value, "policy surface").lower()
    if surface not in PROFILE_SURFACES:
        raise ValueError(f"unsupported enterprise policy surface: {surface}")
    return surface


def _locked_profile_mismatches(profile: Profile, policy: EnterprisePolicy, *, surface: str) -> list[str]:
    blocked: list[str] = []
    for item in policy.locked_settings:
        current = _profile_policy_value(profile, item.key)
        if current is None:
            continue
        if current != item.value:
            blocked.append(
                f"{surface} cannot use locked enterprise setting {item.key}={current!r}; required {item.value!r}"
            )
    return blocked


def _profile_policy_value(profile: Profile, key: str) -> str | None:
    if key.startswith("options."):
        return profile.options.get(key.removeprefix("options."))
    if key.startswith("option."):
        return profile.options.get(key.removeprefix("option."))
    if key in profile.options:
        return profile.options.get(key)
    if key not in PROFILE_FIELD_KEYS:
        return None
    value = getattr(profile, key)
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, list):
        return ",".join(str(item) for item in value)
    return str(value)


def _flatten_settings(settings: dict[str, Any]) -> dict[str, str]:
    flat: dict[str, str] = {}
    for key, value in settings.items():
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                flat[f"{key}.{child_key}"] = _setting_value(child_value)
                if key == "options":
                    flat[str(child_key)] = _setting_value(child_value)
            continue
        flat[str(key)] = _setting_value(value)
    return flat


def _setting_value(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, list):
        return ",".join(str(item) for item in value)
    return str(value)


def _raise_if_blocked(review: EnterprisePolicyReview) -> None:
    if review.allowed:
        return
    message = "; ".join(review.blocked) or "blocked by enterprise policy"
    raise ValueError(f"enterprise policy blocked {review.surface} {review.action}: {message}")

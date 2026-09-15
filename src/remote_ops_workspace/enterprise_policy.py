from __future__ import annotations

import json
import os
import re
import stat
import sys
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
# Historical policies used these unqualified option names. New or plugin-owned
# profile options must use the explicit ``options.<name>`` extension namespace,
# which the profile gate can enforce even when the option is absent.
DIRECT_OPTION_LOCK_KEYS = frozenset({"jump_host", "proxy_jump"})
POLICY_SCHEMA_VERSION = 1
POLICY_KEYS = {
    "schema_version",
    "allow_user_profiles",
    "allow_custom_commands",
    "allow_unsafe_proxy_command",
    "locked_settings",
}
LOCKED_SETTING_KEY_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}")
# The unauthenticated Web/PWA policy hint needs only the protocol lock. Other
# lock names and values can expose internal hosts, local paths, credential
# references, or future extension data and therefore stay inside the trusted
# policy-enforcement boundary.
PUBLIC_LOCK_VALUE_KEYS = frozenset({"protocol"})


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
    allow_unsafe_proxy_command: bool = False
    locked_settings: tuple[LockedSetting, ...] = ()
    schema_version: int = POLICY_SCHEMA_VERSION
    machine_enforced: bool = False

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
            "allow_unsafe_proxy_command": self.allow_unsafe_proxy_command,
            "locked_settings": [item.to_dict() for item in self.locked_settings],
            "machine_enforced": self.machine_enforced,
            "surfaces": sorted(PROFILE_SURFACES),
        }

    def to_public_dict(self) -> dict[str, Any]:
        payload = self.to_dict()
        payload.pop("path", None)
        payload["has_restricted_locks"] = any(
            item.key not in PUBLIC_LOCK_VALUE_KEYS for item in self.locked_settings
        )
        payload["locked_settings"] = [
            item.to_dict()
            for item in self.locked_settings
            if item.key in PUBLIC_LOCK_VALUE_KEYS
        ]
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


def machine_enterprise_policy_path() -> Path:
    """Return the OS-owned policy location, independent of user environment overrides."""

    if os.name == "nt":
        return _windows_common_app_data() / "RemoteOpsWorkspace" / "policy.json"
    if sys.platform == "darwin":
        return Path("/Library/Application Support/RemoteOpsWorkspace/policy.json")
    return Path("/etc/remote-ops-workspace/policy.json")


def enterprise_policy_path(root: Path | None = None) -> Path:
    """Prefer an administrator-controlled policy over the user/portable policy.

    ``ROW_HOME`` remains useful for portable workspaces, but it must not be able
    to shadow a machine policy.  An explicitly supplied ``root`` controls only
    the fallback location and is primarily used by isolated stores and tests.
    """

    machine_path = machine_enterprise_policy_path()
    if _path_entry_exists(machine_path):
        return machine_path
    return (root or data_dir()) / "policy.json"


def load_enterprise_policy(path: Path | None = None) -> EnterprisePolicy:
    policy_path = Path(path) if path is not None else enterprise_policy_path()
    try:
        policy_status = policy_path.lstat()
    except FileNotFoundError:
        return EnterprisePolicy(path=policy_path)
    if stat.S_ISLNK(policy_status.st_mode) or _is_windows_reparse_point(policy_status):
        raise ValueError(f"enterprise policy must not be a symbolic link: {policy_path}")
    if not stat.S_ISREG(policy_status.st_mode):
        raise ValueError(f"enterprise policy must be a regular file: {policy_path}")
    machine_enforced = _same_path(policy_path, machine_enterprise_policy_path())
    if machine_enforced:
        machine_enforced = _require_machine_policy_permissions(policy_path)
    data = json.loads(policy_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"enterprise policy must be a JSON object: {policy_path}")
    unknown = sorted(set(data) - POLICY_KEYS)
    if unknown:
        raise ValueError(f"enterprise policy contains unknown fields: {', '.join(unknown)}")
    schema_version = data.get("schema_version", POLICY_SCHEMA_VERSION)
    if type(schema_version) is not int or schema_version != POLICY_SCHEMA_VERSION:
        raise ValueError(
            f"enterprise policy schema_version must be {POLICY_SCHEMA_VERSION}"
        )
    allow_user_profiles = _policy_bool(data, "allow_user_profiles", default=True)
    allow_custom_commands = _policy_bool(data, "allow_custom_commands", default=False)
    allow_unsafe_proxy_command = _policy_bool(
        data,
        "allow_unsafe_proxy_command",
        default=False,
    )
    locked_settings = tuple(validate_locked_settings(data.get("locked_settings", [])))
    return EnterprisePolicy(
        path=policy_path,
        active=True,
        allow_user_profiles=allow_user_profiles,
        allow_custom_commands=allow_custom_commands,
        allow_unsafe_proxy_command=allow_unsafe_proxy_command,
        locked_settings=locked_settings,
        schema_version=schema_version,
        machine_enforced=machine_enforced,
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
    if profile.options.get("proxy_command") and not policy.allow_unsafe_proxy_command:
        blocked.append("unsafe SSH proxy commands are disabled by enterprise policy")
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
    if profile.options.get("proxy_command") and not policy.allow_unsafe_proxy_command:
        blocked.append("unsafe SSH proxy commands are disabled by enterprise policy")
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
        elif action == "settings" and item.key not in flat:
            blocked.append(
                f"{surface} settings must include locked enterprise setting {item.key}={item.value!r}"
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


def validate_locked_settings(raw: Any) -> list[LockedSetting]:
    if not isinstance(raw, list):
        raise ValueError("enterprise policy locked_settings must be a list")
    locked: list[LockedSetting] = []
    seen: set[str] = set()
    for item in raw:
        if not isinstance(item, dict) or "key" not in item or "value" not in item:
            raise ValueError("enterprise policy locked_settings entries must contain key and value")
        if set(item) != {"key", "value"}:
            raise ValueError("enterprise policy locked_settings entries may contain only key and value")
        if not isinstance(item["key"], str) or not isinstance(item["value"], str):
            raise ValueError("enterprise policy locked_settings key and value must be strings")
        key = safe.option_value(item["key"], "locked setting key")
        value = safe.clean_text(item["value"], "locked setting value", allow_empty=True)
        if not LOCKED_SETTING_KEY_RE.fullmatch(key):
            raise ValueError(
                "enterprise policy locked setting key must use 1-128 letters, numbers, "
                "dots, underscores or hyphens"
            )
        if not _supported_locked_setting_key(key):
            raise ValueError(
                f"unsupported enterprise policy locked setting key: {key}; "
                "profile option extensions must use options.<name>"
            )
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
            blocked.append(
                f"{surface} cannot enforce unsupported enterprise setting {item.key!r}"
            )
            continue
        if current != item.value:
            blocked.append(
                f"{surface} cannot use locked enterprise setting {item.key}={current!r}; required {item.value!r}"
            )
    return blocked


def _profile_policy_value(profile: Profile, key: str) -> str | None:
    if key.startswith("options."):
        return profile.options.get(key.removeprefix("options."), "")
    if key.startswith("option."):
        return profile.options.get(key.removeprefix("option."), "")
    if key in DIRECT_OPTION_LOCK_KEYS:
        return profile.options.get(key, "")
    if key not in PROFILE_FIELD_KEYS:
        return None
    value = getattr(profile, key)
    if value in (None, "", [], {}):
        return ""
    if isinstance(value, list):
        return ",".join(str(item) for item in value)
    return str(value)


def _supported_locked_setting_key(key: str) -> bool:
    if key in PROFILE_FIELD_KEYS or key in DIRECT_OPTION_LOCK_KEYS:
        return True
    for prefix in ("options.", "option."):
        if key.startswith(prefix):
            suffix = key.removeprefix(prefix)
            return bool(suffix and LOCKED_SETTING_KEY_RE.fullmatch(suffix))
    return False


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


def _policy_bool(data: dict[str, Any], key: str, *, default: bool) -> bool:
    value = data.get(key, default)
    if type(value) is not bool:
        raise ValueError(f"enterprise policy {key} must be a boolean")
    return value


def _same_path(left: Path, right: Path) -> bool:
    try:
        return left.resolve(strict=False) == right.resolve(strict=False)
    except OSError:
        return False


def _path_entry_exists(path: Path) -> bool:
    """Return false only for a definitely absent path.

    Permission and type errors must select the machine location so loading it
    fails closed instead of silently consulting a user-controlled fallback.
    """

    try:
        path.lstat()
    except FileNotFoundError:
        return False
    except OSError:
        return True
    return True


def _is_windows_reparse_point(path_status: os.stat_result) -> bool:
    attributes = getattr(path_status, "st_file_attributes", 0)
    reparse_flag = getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
    return bool(attributes & reparse_flag)


def _require_machine_policy_permissions(path: Path) -> bool:
    """Reject mutable POSIX policies and report verified enforcement status.

    POSIX ownership/mode is available through the standard library. Python's
    portable APIs cannot prove a Windows file's owner and effective DACL, so a
    Common AppData policy remains active there but is explicitly *not* reported
    as machine-enforced until an installer/runtime supplies verifiable ACL
    evidence. Merely assuming inherited ProgramData ACLs would be fail-open.
    """

    if os.name == "nt":
        return False
    mode = path.stat().st_mode
    if mode & (stat.S_IWGRP | stat.S_IWOTH):
        raise ValueError(f"machine enterprise policy must not be group/world writable: {path}")
    if hasattr(os, "getuid") and path.stat().st_uid != 0:
        raise ValueError(f"machine enterprise policy must be owned by root: {path}")
    return True


def _windows_common_app_data() -> Path:
    if os.name != "nt":
        raise RuntimeError("Windows Common AppData is only available on Windows")
    import ctypes

    buffer = ctypes.create_unicode_buffer(32768)
    # CSIDL_COMMON_APPDATA is resolved by the shell and cannot be redirected by
    # changing PROGRAMDATA in the child process environment.
    windll = getattr(ctypes, "windll", None)
    if windll is None:  # pragma: no cover - guarded by os.name, defensive for exotic runtimes
        raise OSError("Windows Shell API is unavailable")
    result = windll.shell32.SHGetFolderPathW(None, 35, None, 0, buffer)
    if result != 0 or not buffer.value:
        raise OSError(result, "unable to resolve Windows Common AppData")
    return Path(buffer.value)


def _raise_if_blocked(review: EnterprisePolicyReview) -> None:
    if review.allowed:
        return
    message = "; ".join(review.blocked) or "blocked by enterprise policy"
    raise ValueError(f"enterprise policy blocked {review.surface} {review.action}: {message}")

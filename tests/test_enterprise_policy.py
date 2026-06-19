from __future__ import annotations

import json
import os
from pathlib import Path

from remote_ops_workspace.enterprise_policy import (
    load_enterprise_policy,
    review_profile_launch,
    review_profile_write,
    review_settings_write,
)
from remote_ops_workspace.launcher import launch
from remote_ops_workspace.models import Profile
from remote_ops_workspace.storage import ProfileStore


def test_enterprise_policy_loads_locked_settings(tmp_path: Path) -> None:
    policy_path = _write_policy(
        tmp_path,
        locked_settings=[{"key": "protocol", "value": "ssh"}],
        allow_user_profiles=True,
    )

    policy = load_enterprise_policy(policy_path)

    assert policy.active is True
    assert policy.locked_value("protocol") == "ssh"
    assert policy.to_public_dict()["surfaces"] == ["cli", "gui", "launcher", "profile-editor", "quick-connect", "web"]


def test_profile_store_blocks_locked_profile_edits(tmp_path: Path) -> None:
    policy_path = _write_policy(tmp_path, locked_settings=[{"key": "protocol", "value": "ssh"}])
    store = ProfileStore(tmp_path / "profiles.json", policy_path=policy_path)

    try:
        store.add(Profile(name="legacy", protocol="telnet", host="192.0.2.10"), surface="cli")
    except ValueError as exc:
        assert "enterprise policy blocked cli add" in str(exc)
        assert "protocol='telnet'" in str(exc)
    else:
        raise AssertionError("locked protocol policy should block conflicting profile add")

    store.add(Profile(name="edge", protocol="ssh", host="192.0.2.10"), surface="cli")
    assert store.get("edge").protocol == "ssh"


def test_enterprise_policy_blocks_profile_collection_changes(tmp_path: Path) -> None:
    policy_path = _write_policy(tmp_path, locked_settings=[], allow_user_profiles=False)
    store = ProfileStore(tmp_path / "profiles.json", policy_path=policy_path)

    try:
        store.add(Profile(name="edge", protocol="ssh", host="192.0.2.10"), surface="cli")
    except ValueError as exc:
        assert "user profile changes are disabled" in str(exc)
    else:
        raise AssertionError("allow_user_profiles=false should block profile add")

    try:
        store.set_group_defaults("prod", {"username": "admin"}, surface="cli")
    except ValueError as exc:
        assert "user profile changes are disabled" in str(exc)
    else:
        raise AssertionError("allow_user_profiles=false should block group defaults")


def test_enterprise_policy_blocks_locked_group_default_options(tmp_path: Path) -> None:
    policy_path = _write_policy(tmp_path, locked_settings=[{"key": "options.proxy_jump", "value": "bastion"}])

    review = review_settings_write(
        {"options": {"proxy_jump": "other"}},
        surface="cli",
        action="profile-defaults",
        policy=load_enterprise_policy(policy_path),
    )

    assert review.allowed is False
    assert "options.proxy_jump" in review.blocked[0]


def test_enterprise_policy_blocks_custom_command_launch(tmp_path: Path) -> None:
    policy_path = _write_policy(tmp_path, locked_settings=[], allow_custom_commands=False)
    profile = Profile(name="script", protocol="custom", command="echo ok")

    review = review_profile_launch(profile, policy=load_enterprise_policy(policy_path))

    assert review.allowed is False
    assert "custom command profiles are disabled" in review.blocked[0]

    old_home = os.environ.get("ROW_HOME")
    os.environ["ROW_HOME"] = str(tmp_path)
    try:
        try:
            launch(profile, dry_run=True)
        except ValueError:
            pass
        else:
            raise AssertionError("launcher should enforce enterprise policy before dry-run plans")
    finally:
        if old_home is None:
            os.environ.pop("ROW_HOME", None)
        else:
            os.environ["ROW_HOME"] = old_home


def test_enterprise_policy_allows_matching_profile_option_lock(tmp_path: Path) -> None:
    policy_path = _write_policy(tmp_path, locked_settings=[{"key": "proxy_jump", "value": "bastion"}])
    profile = Profile(
        name="edge",
        protocol="ssh",
        host="192.0.2.10",
        options={"proxy_jump": "bastion"},
    )

    review = review_profile_write(profile, surface="profile-editor", action="profile-editor", policy=load_enterprise_policy(policy_path))

    assert review.allowed is True


def _write_policy(
    root: Path,
    *,
    locked_settings: list[dict[str, str]],
    allow_user_profiles: bool = True,
    allow_custom_commands: bool = False,
) -> Path:
    path = root / "policy.json"
    path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "allow_user_profiles": allow_user_profiles,
                "allow_custom_commands": allow_custom_commands,
                "locked_settings": locked_settings,
            }
        ),
        encoding="utf-8",
    )
    return path

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from remote_ops_workspace.enterprise_policy import (
    EnterprisePolicy,
    LockedSetting,
    assert_settings_write_allowed,
    load_enterprise_policy,
    review_profile_collection_change,
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
    assert policy.locked_value("missing") is None
    assert policy.to_public_dict()["surfaces"] == ["cli", "gui", "launcher", "profile-editor", "quick-connect", "web"]

    review = review_profile_write(
        Profile(name="edge", protocol="ssh", host="192.0.2.10"),
        surface="cli",
        action="replace",
        policy=policy,
    )
    assert review.to_dict() == {
        "surface": "cli",
        "action": "replace",
        "allowed": True,
        "blocked": [],
        "enforced_settings": [{"key": "protocol", "value": "ssh"}],
        "notes": ["1 locked enterprise settings loaded"],
    }


@pytest.mark.parametrize(
    "payload, message",
    [
        ([], "must be a JSON object"),
        ({"locked_settings": {}}, "locked_settings must be a list"),
        ({"locked_settings": [{}]}, "entries must contain key and value"),
        (
            {"locked_settings": [{"key": "host", "value": "one"}, {"key": "host", "value": "two"}]},
            "duplicate locked enterprise setting",
        ),
    ],
)
def test_enterprise_policy_rejects_malformed_documents(tmp_path: Path, payload: object, message: str) -> None:
    policy_path = tmp_path / "policy.json"
    policy_path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        load_enterprise_policy(policy_path)


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


def test_enterprise_policy_reviews_custom_commands_and_collection_changes(tmp_path: Path) -> None:
    profile = Profile(name="script", protocol="custom", command="echo ok")
    blocked_policy = load_enterprise_policy(
        _write_policy(tmp_path, locked_settings=[], allow_user_profiles=False, allow_custom_commands=False)
    )

    write_review = review_profile_write(profile, surface="cli", action="add", policy=blocked_policy)
    assert write_review.allowed is False
    assert len(write_review.blocked) == 2

    collection_review = review_profile_collection_change(
        surface="gui",
        action="remove",
        policy=blocked_policy,
    )
    assert collection_review.allowed is False

    allowed_policy = EnterprisePolicy(path=tmp_path / "allow.json", active=True, allow_custom_commands=True)
    assert review_profile_launch(profile, policy=allowed_policy).allowed is True
    assert review_profile_collection_change(
        surface="web",
        action="replace",
        policy=allowed_policy,
    ).allowed is True


def test_enterprise_policy_rejects_unknown_surface(tmp_path: Path) -> None:
    policy = EnterprisePolicy(path=tmp_path / "policy.json", active=True)

    with pytest.raises(ValueError, match="unsupported enterprise policy surface"):
        review_profile_launch(Profile(name="edge", protocol="ssh", host="192.0.2.10"), surface="desktop", policy=policy)


def test_enterprise_policy_reads_all_profile_lock_shapes(tmp_path: Path) -> None:
    profile = Profile(
        name="edge",
        protocol="ssh",
        host=None,
        port=22,
        tags=["prod", "edge"],
        options={"proxy_jump": "bastion"},
    )
    policy = EnterprisePolicy(
        path=tmp_path / "policy.json",
        active=True,
        locked_settings=(
            LockedSetting("options.proxy_jump", "bastion"),
            LockedSetting("option.proxy_jump", "bastion"),
            LockedSetting("proxy_jump", "bastion"),
            LockedSetting("unknown", "ignored"),
            LockedSetting("host", ""),
            LockedSetting("tags", "prod,edge"),
            LockedSetting("port", "22"),
        ),
    )

    review = review_profile_write(profile, surface="quick-connect", action="replace", policy=policy)

    assert review.allowed is True


def test_enterprise_policy_flattens_nested_and_scalar_settings(tmp_path: Path) -> None:
    policy = EnterprisePolicy(
        path=tmp_path / "policy.json",
        active=True,
        locked_settings=(
            LockedSetting("options.proxy_jump", "bastion"),
            LockedSetting("proxy_jump", "bastion"),
            LockedSetting("ui.columns", "host,port"),
            LockedSetting("ui.empty", ""),
            LockedSetting("theme", "dark"),
        ),
    )

    review = review_settings_write(
        {
            "options": {"proxy_jump": "bastion", "keepalive": 30},
            "ui": {"columns": ["host", "port"], "empty": None},
            "theme": "dark",
        },
        surface="gui",
        action="settings",
        policy=policy,
    )

    assert review.allowed is True


def test_inactive_policy_allows_launch_settings_and_collection_changes(tmp_path: Path) -> None:
    policy = EnterprisePolicy(path=tmp_path / "missing-policy.json")
    profile = Profile(name="edge", protocol="ssh", host="192.0.2.10")

    assert review_profile_launch(profile, policy=policy).allowed is True
    assert review_settings_write({}, surface="gui", action="settings", policy=policy).allowed is True
    assert review_profile_collection_change(surface="cli", action="remove", policy=policy).allowed is True


def test_settings_assertion_enforces_locked_values(tmp_path: Path) -> None:
    policy_path = _write_policy(tmp_path, locked_settings=[{"key": "theme", "value": "dark"}])

    assert_settings_write_allowed({"theme": "dark"}, surface="gui", action="settings", policy_path=policy_path)
    with pytest.raises(ValueError, match="enterprise policy blocked gui settings"):
        assert_settings_write_allowed({"theme": "light"}, surface="gui", action="settings", policy_path=policy_path)


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

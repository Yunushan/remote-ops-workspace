from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

import remote_ops_workspace.enterprise_policy as policy_module
from remote_ops_workspace.enterprise_policy import (
    EnterprisePolicy,
    LockedSetting,
    assert_settings_write_allowed,
    enterprise_policy_path,
    load_enterprise_policy,
    review_profile_collection_change,
    review_profile_launch,
    review_profile_write,
    review_settings_write,
)
from remote_ops_workspace.launcher import build_launch_plan, launch
from remote_ops_workspace.layouts import Layout, LayoutPane, build_layout_terminal_plans
from remote_ops_workspace.models import Profile
from remote_ops_workspace.snippets import Snippet, run_snippet
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
        ({"schema_version": True}, "schema_version must be 1"),
        ({"schema_version": 2}, "schema_version must be 1"),
        ({"allow_user_profiles": "false"}, "allow_user_profiles must be a boolean"),
        ({"allow_custom_commands": 0}, "allow_custom_commands must be a boolean"),
        ({"allow_unsafe_proxy_command": "no"}, "allow_unsafe_proxy_command must be a boolean"),
        ({"unknown": True}, "contains unknown fields"),
        (
            {"locked_settings": [{"key": "host", "value": "one", "note": "extra"}]},
            "may contain only key and value",
        ),
        (
            {"locked_settings": [{"key": "host", "value": 22}]},
            "key and value must be strings",
        ),
        (
            {"locked_settings": [{"key": "host", "value": "one"}, {"key": "host", "value": "two"}]},
            "duplicate locked enterprise setting",
        ),
        (
            {"locked_settings": [{"key": "credential=embedded-secret", "value": "value"}]},
            "locked setting key must use",
        ),
        (
            {"locked_settings": [{"key": "protcol", "value": "ssh"}]},
            "unsupported enterprise policy locked setting key: protcol",
        ),
        (
            {"locked_settings": [{"key": "theme", "value": "dark"}]},
            "unsupported enterprise policy locked setting key: theme",
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


def test_enterprise_policy_blocks_empty_wholesale_profile_replacement(
    tmp_path: Path,
) -> None:
    store_path = tmp_path / "profiles.json"
    seed = ProfileStore(store_path, policy_path=tmp_path / "no-policy.json")
    seed.add(Profile(name="edge", protocol="ssh", host="192.0.2.10"))
    original = store_path.read_bytes()
    policy_path = _write_policy(
        tmp_path,
        locked_settings=[],
        allow_user_profiles=False,
    )
    blocked = ProfileStore(store_path, policy_path=policy_path)

    with pytest.raises(ValueError, match="user profile changes are disabled"):
        blocked.save([], surface="cli")
    with pytest.raises(ValueError, match="user profile changes are disabled"):
        blocked.update_profiles(
            lambda _profiles, _defaults: [],
            surface="cli",
            action="team-sync-replace",
        )

    assert store_path.read_bytes() == original
    assert blocked.get("edge").host == "192.0.2.10"


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


def test_launch_plan_builder_and_cli_layout_plans_cannot_bypass_policy(tmp_path: Path) -> None:
    policy_path = _write_policy(tmp_path, locked_settings=[], allow_custom_commands=False)
    profile = Profile(name="script", protocol="custom", command="echo policy-bypass")

    with pytest.raises(ValueError, match="custom command profiles are disabled"):
        build_launch_plan(profile, policy_path=policy_path)

    store = ProfileStore(tmp_path / "profiles.json", policy_path=policy_path)
    layout = Layout(name="commands", panes=[LayoutPane(command="echo policy-bypass")])
    with pytest.raises(ValueError, match="custom command profiles are disabled"):
        build_layout_terminal_plans(layout, store)

    with pytest.raises(ValueError, match="custom command profiles are disabled"):
        run_snippet(Snippet(name="script", command="echo policy-bypass"), True, policy_path=policy_path)


def test_enterprise_policy_blocks_profile_level_proxy_command_opt_in(tmp_path: Path) -> None:
    policy_path = _write_policy(tmp_path, locked_settings=[])
    profile = Profile(
        name="proxy",
        protocol="ssh",
        host="192.0.2.10",
        options={"proxy_command": "nc %h %p", "allow_unsafe_proxy_command": "true"},
    )

    write_review = review_profile_write(
        profile,
        surface="cli",
        action="add",
        policy=load_enterprise_policy(policy_path),
    )
    launch_review = review_profile_launch(profile, policy=load_enterprise_policy(policy_path))

    assert write_review.allowed is False
    assert launch_review.allowed is False
    assert "unsafe SSH proxy commands are disabled" in write_review.blocked[0]


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


def test_enterprise_policy_requires_historical_direct_option_lock_to_be_present(
    tmp_path: Path,
) -> None:
    policy_path = _write_policy(
        tmp_path,
        locked_settings=[{"key": "proxy_jump", "value": "bastion"}],
    )

    review = review_profile_write(
        Profile(name="edge", protocol="ssh", host="192.0.2.10"),
        surface="profile-editor",
        action="profile-editor",
        policy=load_enterprise_policy(policy_path),
    )

    assert review.allowed is False
    assert "proxy_jump=''" in review.blocked[0]


def test_enterprise_policy_requires_locked_profile_option_to_be_present(tmp_path: Path) -> None:
    policy_path = _write_policy(
        tmp_path,
        locked_settings=[{"key": "options.proxy_jump", "value": "bastion"}],
    )
    profile = Profile(name="edge", protocol="ssh", host="192.0.2.10")

    review = review_profile_write(
        profile,
        surface="profile-editor",
        action="profile-editor",
        policy=load_enterprise_policy(policy_path),
    )

    assert review.allowed is False
    assert "options.proxy_jump=''" in review.blocked[0]


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
            LockedSetting("tags", "prod,edge"),
            LockedSetting("path", ""),
            LockedSetting("port", "22"),
        ),
    )

    review = review_settings_write(
        {
            "options": {"proxy_jump": "bastion", "keepalive": 30},
            "tags": ["prod", "edge"],
            "path": None,
            "port": 22,
        },
        surface="gui",
        action="settings",
        policy=policy,
    )

    assert review.allowed is True


def test_enterprise_policy_requires_locks_in_complete_settings_document(tmp_path: Path) -> None:
    policy = EnterprisePolicy(
        path=tmp_path / "policy.json",
        active=True,
        locked_settings=(LockedSetting("options.proxy_jump", "bastion"),),
    )

    review = review_settings_write({}, surface="gui", action="settings", policy=policy)

    assert review.allowed is False
    assert "must include locked enterprise setting" in review.blocked[0]


def test_inactive_policy_allows_launch_settings_and_collection_changes(tmp_path: Path) -> None:
    policy = EnterprisePolicy(path=tmp_path / "missing-policy.json")
    profile = Profile(name="edge", protocol="ssh", host="192.0.2.10")

    assert review_profile_launch(profile, policy=policy).allowed is True
    assert review_settings_write({}, surface="gui", action="settings", policy=policy).allowed is True
    assert review_profile_collection_change(surface="cli", action="remove", policy=policy).allowed is True


def test_settings_assertion_enforces_locked_values(tmp_path: Path) -> None:
    policy_path = _write_policy(
        tmp_path,
        locked_settings=[{"key": "options.proxy_jump", "value": "bastion"}],
    )

    assert_settings_write_allowed(
        {"options": {"proxy_jump": "bastion"}},
        surface="gui",
        action="settings",
        policy_path=policy_path,
    )
    with pytest.raises(ValueError, match="enterprise policy blocked gui settings"):
        assert_settings_write_allowed(
            {"options": {"proxy_jump": "other"}},
            surface="gui",
            action="settings",
            policy_path=policy_path,
        )


def test_machine_policy_cannot_be_shadowed_by_portable_root(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    machine = tmp_path / "machine" / "policy.json"
    machine.parent.mkdir()
    machine.write_text("{}", encoding="utf-8")
    portable = tmp_path / "portable"
    portable.mkdir()
    (portable / "policy.json").write_text("{}", encoding="utf-8")
    monkeypatch.setattr(policy_module, "machine_enterprise_policy_path", lambda: machine)

    assert enterprise_policy_path(portable) == machine


def test_non_regular_machine_policy_path_fails_closed_instead_of_using_portable_policy(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    machine = tmp_path / "machine" / "policy.json"
    machine.mkdir(parents=True)
    portable = tmp_path / "portable"
    portable.mkdir()
    (portable / "policy.json").write_text(
        json.dumps({"schema_version": 1, "locked_settings": []}),
        encoding="utf-8",
    )
    monkeypatch.setattr(policy_module, "machine_enterprise_policy_path", lambda: machine)

    assert enterprise_policy_path(portable) == machine
    with pytest.raises(ValueError, match="must be a regular file"):
        load_enterprise_policy()


def test_public_policy_omits_local_sensitive_and_unknown_locks(tmp_path: Path) -> None:
    policy = EnterprisePolicy(
        path=tmp_path / "policy.json",
        active=True,
        locked_settings=(
            LockedSetting("protocol", "ssh"),
            LockedSetting("identity_file", "/srv/private/id_ed25519"),
            LockedSetting("options.api_token", "do-not-disclose"),
            LockedSetting("future_extension", "opaque-admin-value"),
        ),
    )

    public = policy.to_public_dict()

    assert public["locked_settings"] == [{"key": "protocol", "value": "ssh"}]
    assert public["has_restricted_locks"] is True
    serialized = json.dumps(public)
    assert "identity_file" not in serialized
    assert "api_token" not in serialized
    assert "future_extension" not in serialized
    assert "/srv/private" not in serialized
    assert "do-not-disclose" not in serialized
    assert "opaque-admin-value" not in serialized


def test_programmatic_unknown_lock_fails_closed_even_without_loader_validation(
    tmp_path: Path,
) -> None:
    policy = EnterprisePolicy(
        path=tmp_path / "policy.json",
        active=True,
        locked_settings=(LockedSetting("future_extension", "opaque"),),
    )

    review = review_profile_launch(
        Profile(name="edge", protocol="ssh", host="edge.example.invalid"),
        policy=policy,
    )

    assert review.allowed is False
    assert "cannot enforce unsupported enterprise setting" in review.blocked[0]


def test_machine_policy_is_marked_as_enforced(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    machine = _write_policy(tmp_path, locked_settings=[])
    monkeypatch.setattr(policy_module, "machine_enterprise_policy_path", lambda: machine)
    monkeypatch.setattr(policy_module, "_require_machine_policy_permissions", lambda _path: True)

    policy = load_enterprise_policy()

    assert policy.machine_enforced is True
    assert policy.to_public_dict()["machine_enforced"] is True


def test_windows_machine_policy_is_not_claimed_enforced_without_dacl_proof(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(policy_module.os, "name", "nt")

    assert policy_module._require_machine_policy_permissions(tmp_path / "policy.json") is False


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

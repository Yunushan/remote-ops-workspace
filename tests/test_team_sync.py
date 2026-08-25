import json
from pathlib import Path

import pytest

from remote_ops_workspace.models import Profile
from remote_ops_workspace.storage import ProfileStore
from remote_ops_workspace.team_sync import (
    TeamSyncBackend,
    TeamSyncBusyError,
    TeamSyncClient,
    TeamSyncConflictError,
    team_profile_dict,
)


def test_team_sync_push_pull_preserves_local_credential_references(tmp_path: Path) -> None:
    backend = TeamSyncBackend(tmp_path / "team")
    source_store = ProfileStore(tmp_path / "source.json")
    source_store.add(
        Profile(
            name="edge",
            protocol="ssh",
            host="edge.example.invalid",
            credential_ref="vault:edge",
            identity_file="/private/id_ed25519",
            options={"keepalive_interval": "30", "api_token": "never-share"},
        )
    )
    published = TeamSyncClient(source_store, backend).push("operators", expected_version=0)

    assert published.version == 1
    assert published.profiles[0].credential_ref is None
    assert published.profiles[0].identity_file is None
    assert "api_token" not in published.profiles[0].options

    target_store = ProfileStore(tmp_path / "target.json")
    target_store.add(Profile(name="edge", protocol="ssh", host="old.example.invalid", credential_ref="vault:local"))
    pulled = TeamSyncClient(target_store, backend).pull("operators")

    assert pulled.version == 1
    assert target_store.get("edge").host == "edge.example.invalid"
    assert target_store.get("edge").credential_ref == "vault:local"


def test_team_sync_filters_secret_aliases_without_dropping_auth_metadata() -> None:
    shared = team_profile_dict(
        Profile(
            name="edge",
            protocol="ssh",
            options={
                "api_key": "api-secret",
                "Authorization": "Bearer secret",
                "cookie": "session=secret",
                "identity-file": "/private/id_ed25519",
                "smartcard_auth": "true",
                "keepalive_interval": "30",
            },
        )
    )

    assert shared["options"] == {"smartcard_auth": "true", "keepalive_interval": "30"}


def test_team_sync_rejects_stale_optimistic_concurrency_version(tmp_path: Path) -> None:
    backend = TeamSyncBackend(tmp_path / "team")
    first = ProfileStore(tmp_path / "first.json")
    second = ProfileStore(tmp_path / "second.json")
    first.add(Profile(name="one", protocol="ssh", host="one.example.invalid"))
    second.add(Profile(name="two", protocol="ssh", host="two.example.invalid"))

    TeamSyncClient(first, backend).push("ops", expected_version=0)
    try:
        TeamSyncClient(second, backend).push("ops", expected_version=0)
    except TeamSyncConflictError as exc:
        assert "pull before pushing" in str(exc)
    else:
        raise AssertionError("stale team writes must fail instead of overwriting shared state")


def test_team_sync_rejects_unsafe_team_identifiers(tmp_path: Path) -> None:
    backend = TeamSyncBackend(tmp_path)
    try:
        backend.read("../other")
    except ValueError as exc:
        assert "team id" in str(exc)
    else:
        raise AssertionError("unsafe team identifiers must be rejected")


def test_team_sync_refuses_concurrent_writer_lock(tmp_path: Path) -> None:
    backend = TeamSyncBackend(tmp_path, lock_timeout_seconds=0.01)
    (tmp_path / "ops.team-sync.lock").write_text("held", encoding="utf-8")
    try:
        backend.write("ops", [Profile(name="edge", protocol="ssh", host="edge.example.invalid")], expected_version=0)
    except TeamSyncBusyError as exc:
        assert "busy" in str(exc)
    else:
        raise AssertionError("a held team lock must prevent concurrent writes")


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ({"schema_version": 2}, "invalid team sync record"),
        (
            {"schema_version": 1, "team": "other", "version": 1, "profiles": []},
            "does not match requested team",
        ),
        (
            {"schema_version": 1, "team": "ops", "version": 0, "profiles": []},
            "version must be a positive integer",
        ),
        (
            {"schema_version": 1, "team": "ops", "version": True, "profiles": []},
            "version must be a positive integer",
        ),
        (
            {"schema_version": 1, "team": "ops", "version": 1, "profiles": {}},
            "profiles must be a list",
        ),
        (
            {"schema_version": 1, "team": "ops", "version": 1, "profiles": ["bad"]},
            "profiles must contain JSON objects",
        ),
    ],
)
def test_team_sync_rejects_corrupt_shared_records(
    tmp_path: Path,
    payload: dict[str, object],
    message: str,
) -> None:
    path = tmp_path / "ops.team-sync.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(ValueError, match=message):
        TeamSyncBackend(tmp_path).read("ops")


@pytest.mark.parametrize("version", [-1, True, 1.5])
def test_team_sync_rejects_invalid_expected_versions(tmp_path: Path, version: object) -> None:
    with pytest.raises(ValueError, match="non-negative integer"):
        TeamSyncBackend(tmp_path).write("ops", [], expected_version=version)  # type: ignore[arg-type]


def test_team_sync_rejects_duplicate_profile_names_and_invalid_lock_timeout(tmp_path: Path) -> None:
    duplicate = Profile(name="edge", protocol="ssh", host="edge.example.invalid")
    with pytest.raises(ValueError, match="profile names must be unique"):
        TeamSyncBackend(tmp_path / "duplicates").write(
            "ops",
            [duplicate, duplicate],
            expected_version=0,
        )

    with pytest.raises(ValueError, match="lock timeout must be positive"):
        TeamSyncBackend(tmp_path / "timeout", lock_timeout_seconds=0).write(
            "ops",
            [],
            expected_version=0,
        )


def test_team_sync_pull_supports_replace_and_new_profile_merge(tmp_path: Path) -> None:
    backend = TeamSyncBackend(tmp_path / "team")
    backend.write(
        "ops",
        [Profile(name="remote", protocol="ssh", host="remote.example.invalid")],
        expected_version=0,
    )

    merged_store = ProfileStore(tmp_path / "merged.json")
    merged_store.add(Profile(name="local", protocol="ssh", host="local.example.invalid"))
    TeamSyncClient(merged_store, backend).pull("ops")
    assert [profile.name for profile in merged_store.load()] == ["local", "remote"]

    replaced_store = ProfileStore(tmp_path / "replaced.json")
    replaced_store.add(Profile(name="local", protocol="ssh", host="local.example.invalid"))
    TeamSyncClient(replaced_store, backend).pull("ops", replace=True)
    assert [profile.name for profile in replaced_store.load()] == ["remote"]

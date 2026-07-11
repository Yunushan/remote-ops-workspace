from pathlib import Path

from remote_ops_workspace.models import Profile
from remote_ops_workspace.storage import ProfileStore
from remote_ops_workspace.team_sync import (
    TeamSyncBackend,
    TeamSyncBusyError,
    TeamSyncClient,
    TeamSyncConflictError,
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

import json
import os
import stat
import threading
from pathlib import Path

import pytest

from remote_ops_workspace import team_sync
from remote_ops_workspace.file_safety import SHARED_DIR_MODE, SHARED_FILE_MODE
from remote_ops_workspace.models import Profile, Tunnel
from remote_ops_workspace.state_lock import exclusive_file_lock, lock_path_for
from remote_ops_workspace.storage import ProfileStore
from remote_ops_workspace.team_sync import (
    TeamSyncBackend,
    TeamSyncBusyError,
    TeamSyncClient,
    TeamSyncConflictError,
    team_profile_dict,
)


def _shared_root(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    if os.name == "posix":
        path.chmod(SHARED_DIR_MODE)
    return path


def _backend(path: Path, **kwargs) -> TeamSyncBackend:
    return TeamSyncBackend(_shared_root(path), **kwargs)


def _write_shared_text(path: Path, text: str) -> None:
    _shared_root(path.parent)
    path.write_text(text, encoding="utf-8")
    if os.name == "posix":
        path.chmod(SHARED_FILE_MODE)


def test_team_sync_pull_does_not_rebind_local_credentials_to_a_changed_endpoint(
    tmp_path: Path,
) -> None:
    backend = _backend(tmp_path / "team")
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
    assert target_store.get("edge").credential_ref is None


def test_team_sync_pull_preserves_local_credentials_for_the_same_public_binding(
    tmp_path: Path,
) -> None:
    backend = _backend(tmp_path / "team")
    backend.write(
        "ops",
        [
            Profile(
                name="edge",
                protocol="ssh",
                host="edge.example.invalid",
                username="operator",
                options={"keepalive_interval": "30"},
            )
        ],
        expected_version=0,
    )
    store = ProfileStore(tmp_path / "profiles.json")
    store.add(
        Profile(
            name="edge",
            protocol="ssh",
            host="edge.example.invalid",
            username="operator",
            credential_ref="vault:local",
            identity_file="/private/id_ed25519",
            options={"keepalive_interval": "30", "api_token": "local-only"},
        )
    )

    TeamSyncClient(store, backend).pull("ops")

    assert store.get("edge").credential_ref == "vault:local"
    assert store.get("edge").identity_file == "/private/id_ed25519"


def test_team_sync_pull_refuses_new_endpoint_with_secret_bearing_group_defaults(
    tmp_path: Path,
) -> None:
    backend = _backend(tmp_path / "team")
    backend.write(
        "ops",
        [Profile(name="remote", protocol="ssh", host="attacker.example.invalid", group="prod")],
        expected_version=0,
    )
    store = ProfileStore(tmp_path / "profiles.json")
    store.set_group_defaults(
        "prod",
        {"credential_ref": "vault:prod", "identity_file": "/private/prod-key"},
    )

    with pytest.raises(ValueError, match="refuses to attach local group credentials"):
        TeamSyncClient(store, backend).pull("ops")

    with pytest.raises(KeyError):
        store.get("remote")


def test_team_sync_pull_atomically_rejects_inherited_forwarding_defaults(
    tmp_path: Path,
) -> None:
    backend = _backend(tmp_path / "team")
    backend.write(
        "ops",
        [Profile(name="remote", protocol="ssh", host="remote.example.invalid", group="prod")],
        expected_version=0,
    )
    store = ProfileStore(tmp_path / "profiles.json")
    store.add(Profile(name="local", protocol="ssh", host="local.example.invalid"))
    store.set_group_defaults(
        "prod",
        {
            "options": {
                "agent_forward": "true",
                "proxy_jump": "bastion.example.invalid",
            }
        },
    )
    original = store.path.read_bytes()

    with pytest.raises(ValueError, match="credentials or forwarding settings") as error:
        TeamSyncClient(store, backend).pull("ops")

    assert "options.agent_forward" in str(error.value)
    assert "options.proxy_jump" in str(error.value)
    assert store.path.read_bytes() == original
    assert [profile.name for profile in store.load(resolve=False)] == ["local"]


def test_team_sync_pull_uses_one_store_transaction_for_read_and_write(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    backend = _backend(tmp_path / "team")
    backend.write(
        "ops",
        [Profile(name="remote", protocol="ssh", host="remote.example.invalid")],
        expected_version=0,
    )
    path = tmp_path / "profiles.json"
    store = ProfileStore(path)
    store.add(Profile(name="local", protocol="ssh", host="local.example.invalid"))

    def split_read_forbidden(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("team pull must not read outside the update transaction")

    monkeypatch.setattr(store, "load", split_read_forbidden)
    monkeypatch.setattr(store, "group_defaults", split_read_forbidden)

    TeamSyncClient(store, backend).pull("ops")

    assert {profile.name for profile in ProfileStore(path).load(resolve=False)} == {
        "local",
        "remote",
    }


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
                "unknown_metadata": "may-contain-a-secret",
                "title": "password=do-not-share",
                "smartcard_auth": "true",
                "keepalive_interval": "30",
            },
            path="C:/Users/operator/private/session.rdp",
            command="sshpass -p do-not-share ssh edge",
            url="https://operator:secret@example.invalid/path?token=secret#private",
        )
    )

    assert shared["options"] == {"smartcard_auth": "true", "keepalive_interval": "30"}
    assert "path" not in shared
    assert "command" not in shared
    assert shared["url"] == "https://example.invalid"


def test_team_sync_redacts_free_form_metadata_and_keeps_forwards_local() -> None:
    profile = Profile(
        name="edge",
        protocol="ssh",
        host="edge.example.invalid",
        group="password=group-secret",
        tags=["token=tag-secret"],
        description="Authorization: Bearer description-secret",
        options={
            "agent_forward": "true",
            "x11": "trusted",
            "strict_host_key_checking": "no",
            "keepalive_interval": "30",
        },
    )
    profile.tunnels = [
        Tunnel(
            mode="remote",
            local_host="127.0.0.1",
            local_port=22,
            remote_host="0.0.0.0",
            remote_port=2222,
        )
    ]

    shared = team_profile_dict(profile)
    serialized = json.dumps(shared)

    assert shared["tunnels"] == []
    assert shared["options"] == {"keepalive_interval": "30"}
    for secret in ("group-secret", "tag-secret", "description-secret"):
        assert secret not in serialized


@pytest.mark.parametrize(
    "unsafe_url",
    [
        "file://fileserver/private/share",
        "javascript://example.invalid/alert(1)",
        "data://example.invalid/text/plain,payload",
    ],
)
def test_team_sync_drops_urls_with_non_web_schemes(unsafe_url: str) -> None:
    shared = team_profile_dict(
        Profile(name="unsafe-url", protocol="ica", url=unsafe_url)
    )

    assert shared["url"] is None


def test_team_sync_keeps_local_and_executable_profiles_out_of_shared_record(tmp_path: Path) -> None:
    backend = _backend(tmp_path / "team")
    snapshot = backend.write(
        "ops",
        [
            Profile(name="remote", protocol="ssh", host="remote.example.invalid"),
            Profile(name="local", protocol="local", command="pwsh"),
            Profile(name="serial", protocol="serial", path="COM7"),
            Profile(name="custom", protocol="custom", command="tool --password secret"),
        ],
        expected_version=0,
    )

    assert [profile.name for profile in snapshot.profiles] == ["remote"]
    serialized = (tmp_path / "team" / "ops.team-sync.json").read_text(encoding="utf-8")
    assert "pwsh" not in serialized
    assert "COM7" not in serialized
    assert "password" not in serialized


def test_team_sync_rejects_stale_optimistic_concurrency_version(tmp_path: Path) -> None:
    backend = _backend(tmp_path / "team")
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
    backend = _backend(tmp_path)
    try:
        backend.read("../other")
    except ValueError as exc:
        assert "team id" in str(exc)
    else:
        raise AssertionError("unsafe team identifiers must be rejected")


def test_team_sync_refuses_a_concurrent_advisory_writer_lock(tmp_path: Path) -> None:
    backend = _backend(tmp_path, lock_timeout_seconds=0.1)
    acquired = threading.Event()
    release = threading.Event()

    def hold_lock() -> None:
        with exclusive_file_lock(backend._path("ops"), timeout_seconds=2, shared=True):
            acquired.set()
            release.wait(timeout=5)

    holder = threading.Thread(target=hold_lock)
    holder.start()
    assert acquired.wait(timeout=2)
    try:
        with pytest.raises(TeamSyncBusyError, match="busy"):
            backend.write(
                "ops",
                [Profile(name="edge", protocol="ssh", host="edge.example.invalid")],
                expected_version=0,
            )
    finally:
        release.set()
        holder.join(timeout=5)
    assert not holder.is_alive()


def test_team_sync_ignores_a_stale_persistent_lock_file_after_process_exit(
    tmp_path: Path,
) -> None:
    backend = _backend(tmp_path)
    lock_path = lock_path_for(backend._path("ops"))
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    _write_shared_text(lock_path, "stale")

    snapshot = backend.write("ops", [], expected_version=0)

    assert snapshot.version == 1
    assert lock_path.is_file()


@pytest.mark.skipif(os.name != "posix", reason="POSIX group-inheritance contract")
def test_team_sync_requires_preprovisioned_setgid_root_and_preserves_group(
    tmp_path: Path,
) -> None:
    with pytest.raises(OSError, match="must be pre-provisioned"):
        TeamSyncBackend(tmp_path / "missing")

    insecure_root = tmp_path / "insecure"
    insecure_root.mkdir(mode=0o770)
    insecure_root.chmod(0o770)
    with pytest.raises(OSError, match="user/group-rwx, setgid"):
        TeamSyncBackend(insecure_root)

    world_root = tmp_path / "world"
    world_root.mkdir(mode=0o2775)
    world_root.chmod(0o2775)
    with pytest.raises(OSError, match="not world-accessible"):
        TeamSyncBackend(world_root)

    shared_root = _shared_root(tmp_path / "shared")
    backend = TeamSyncBackend(shared_root)
    backend.write("ops", [], expected_version=0)
    backend.write("ops", [], expected_version=1)

    record = backend._path("ops")
    lock = lock_path_for(record)
    root_status = shared_root.stat()
    assert stat.S_IMODE(root_status.st_mode) == SHARED_DIR_MODE
    assert stat.S_IMODE(record.stat().st_mode) == SHARED_FILE_MODE
    assert stat.S_IMODE(lock.stat().st_mode) == SHARED_FILE_MODE
    assert record.stat().st_gid == root_status.st_gid
    assert lock.stat().st_gid == root_status.st_gid


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        (
            {"schema_version": 2, "team": "ops", "version": 1, "updated_at": "2026-09-14T00:00:00+00:00", "profiles": []},
            "invalid team sync record",
        ),
        (
            {"schema_version": 1, "team": "other", "version": 1, "updated_at": "2026-09-14T00:00:00+00:00", "profiles": []},
            "does not match requested team",
        ),
        (
            {"schema_version": 1, "team": "ops", "version": 0, "updated_at": "2026-09-14T00:00:00+00:00", "profiles": []},
            "version must be a positive integer",
        ),
        (
            {"schema_version": 1, "team": "ops", "version": True, "updated_at": "2026-09-14T00:00:00+00:00", "profiles": []},
            "version must be a positive integer",
        ),
        (
            {"schema_version": 1, "team": "ops", "version": 1, "updated_at": "2026-09-14T00:00:00+00:00", "profiles": {}},
            "profiles must be a list",
        ),
        (
            {"schema_version": 1, "team": "ops", "version": 1, "updated_at": "2026-09-14T00:00:00+00:00", "profiles": ["bad"]},
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
    _write_shared_text(path, json.dumps(payload))

    with pytest.raises(ValueError, match=message):
        _backend(tmp_path).read("ops")


@pytest.mark.parametrize(
    ("mutation", "message"),
    [
        (("command", "tool --password injected"), "unsupported fields: command"),
        (("path", "C:/private/session.rdp"), "unsupported fields: path"),
        (("credential_ref", "vault:stolen"), "unsupported fields: credential_ref"),
        (("identity_file", "/private/id_ed25519"), "unsupported fields: identity_file"),
        (("protocol", "custom"), "local or executable"),
        (("options", {"proxy_command": "sh -c injected"}), "unsafe options"),
        (("options", {"strict_host_key_checking": "no"}), "unsafe options"),
        (("options", {"agent_forward": "true"}), "unsafe options"),
        (("description", "password=shared-secret"), "secret-bearing public fields"),
        (
            (
                "tunnels",
                [
                    {
                        "mode": "remote",
                        "local_host": "127.0.0.1",
                        "local_port": 22,
                        "remote_host": "0.0.0.0",
                        "remote_port": 2222,
                    }
                ],
            ),
            "must not contain port forwards",
        ),
        (("url", "javascript://example.invalid/alert(1)"), "sanitized HTTP"),
    ],
)
def test_team_sync_read_rejects_tampered_shared_profile_ingress(
    tmp_path: Path,
    mutation: tuple[str, object],
    message: str,
) -> None:
    profile = team_profile_dict(
        Profile(name="edge", protocol="ssh", host="edge.example.invalid")
    )
    profile[mutation[0]] = mutation[1]
    payload = {
        "schema_version": 1,
        "team": "ops",
        "version": 1,
        "updated_at": "2026-09-14T00:00:00+00:00",
        "profiles": [profile],
    }
    _write_shared_text(tmp_path / "ops.team-sync.json", json.dumps(payload))

    with pytest.raises(ValueError, match=message):
        _backend(tmp_path).read("ops")


def test_team_sync_read_rejects_duplicate_profile_names(tmp_path: Path) -> None:
    profile = team_profile_dict(
        Profile(name="edge", protocol="ssh", host="edge.example.invalid")
    )
    payload = {
        "schema_version": 1,
        "team": "ops",
        "version": 1,
        "updated_at": "2026-09-14T00:00:00+00:00",
        "profiles": [profile, dict(profile)],
    }
    _write_shared_text(tmp_path / "ops.team-sync.json", json.dumps(payload))

    with pytest.raises(ValueError, match="profile names must be unique"):
        _backend(tmp_path).read("ops")


@pytest.mark.parametrize(
    "mutation",
    [
        {"schema_version": True},
        {"updated_at": "2026-09-14T00:00:00+00:00\x1b]0;forged-title\x07"},
        {"updated_at": "2026-09-14T03:00:00+03:00"},
        {"unexpected": "ignored-data"},
    ],
)
def test_team_sync_rejects_noncanonical_container_metadata(
    tmp_path: Path,
    mutation: dict[str, object],
) -> None:
    payload: dict[str, object] = {
        "schema_version": 1,
        "team": "ops",
        "version": 1,
        "updated_at": "2026-09-14T00:00:00+00:00",
        "profiles": [],
    }
    payload.update(mutation)
    _write_shared_text(tmp_path / "ops.team-sync.json", json.dumps(payload))

    with pytest.raises(ValueError):
        _backend(tmp_path).read("ops")


def test_team_sync_read_rejects_symlinked_and_oversized_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _shared_root(tmp_path)
    target = tmp_path / "target.json"
    target.write_text("{}", encoding="utf-8")
    link = tmp_path / "ops.team-sync.json"
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")
    with pytest.raises(ValueError, match="must not be a symbolic link"):
        _backend(tmp_path).read("ops")

    link.unlink()
    monkeypatch.setattr(team_sync, "MAX_TEAM_SYNC_BYTES", 8)
    _write_shared_text(link, "{" + " " * 8 + "}")
    with pytest.raises(ValueError, match="exceeds 8 bytes"):
        _backend(tmp_path).read("ops")


@pytest.mark.parametrize("version", [-1, True, 1.5])
def test_team_sync_rejects_invalid_expected_versions(tmp_path: Path, version: object) -> None:
    with pytest.raises(ValueError, match="non-negative integer"):
        _backend(tmp_path).write("ops", [], expected_version=version)  # type: ignore[arg-type]


def test_team_sync_rejects_duplicate_profile_names_and_invalid_lock_timeout(tmp_path: Path) -> None:
    duplicate = Profile(name="edge", protocol="ssh", host="edge.example.invalid")
    with pytest.raises(ValueError, match="profile names must be unique"):
        _backend(tmp_path / "duplicates").write(
            "ops",
            [duplicate, duplicate],
            expected_version=0,
        )

    with pytest.raises(ValueError, match="lock timeout must be positive"):
        _backend(tmp_path / "timeout", lock_timeout_seconds=0).write(
            "ops",
            [],
            expected_version=0,
        )


def test_team_sync_pull_supports_replace_and_new_profile_merge(tmp_path: Path) -> None:
    backend = _backend(tmp_path / "team")
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

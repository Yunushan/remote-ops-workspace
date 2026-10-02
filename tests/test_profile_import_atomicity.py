from __future__ import annotations

import errno
import json
from pathlib import Path

import pytest

from remote_ops_workspace import cli, file_safety
from remote_ops_workspace.models import Profile
from remote_ops_workspace.profile_importers import import_profiles_into_store
from remote_ops_workspace.storage import ProfileStore


def _bundle(path: Path, *profiles: Profile) -> Path:
    path.write_text(json.dumps({"profiles": [profile.to_dict() for profile in profiles]}), encoding="utf-8")
    return path


def test_cli_import_late_collision_preserves_entire_store(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("ROW_HOME", str(tmp_path))
    store = ProfileStore()
    existing = Profile(name="existing", protocol="ssh", host="old.example.invalid")
    store.add(existing)
    before = store.path.read_bytes()
    source = _bundle(
        tmp_path / "import.json",
        Profile(name="new", protocol="ssh", host="new.example.invalid"),
        Profile(name="existing", protocol="ssh", host="replacement.example.invalid"),
    )

    assert cli.main(["import", "--in", str(source)]) == 1

    assert "profile already exists: existing" in capsys.readouterr().err
    assert store.path.read_bytes() == before
    assert [profile.name for profile in store.load()] == ["existing"]


def test_import_late_policy_rejection_preserves_entire_store(tmp_path) -> None:
    policy = tmp_path / "policy.json"
    policy.write_text(json.dumps({"locked_settings": [{"key": "protocol", "value": "ssh"}]}), encoding="utf-8")
    store = ProfileStore(tmp_path / "stored.json", policy_path=policy)
    store.add(Profile(name="existing", protocol="ssh", host="old.example.invalid"))
    before = store.path.read_bytes()
    source = _bundle(
        tmp_path / "import.json",
        Profile(name="allowed", protocol="ssh", host="allowed.example.invalid"),
        Profile(name="blocked", protocol="rdp", host="blocked.example.invalid"),
    )

    with pytest.raises(ValueError, match="locked enterprise setting protocol"):
        import_profiles_into_store(source, store)

    assert store.path.read_bytes() == before


def test_import_final_permission_failure_restores_old_store_bytes(monkeypatch, tmp_path) -> None:
    store = ProfileStore(tmp_path / "stored.json")
    store.add(Profile(name="existing", protocol="ssh", host="old.example.invalid"))
    before = store.path.read_bytes()
    source = _bundle(tmp_path / "import.json", Profile(name="new", protocol="ssh", host="new.example.invalid"))
    original_chmod = file_safety._chmod_required

    def denied_final_permissions(path, mode):
        if path == store.path:
            raise PermissionError("final profile permissions denied")
        original_chmod(path, mode)

    monkeypatch.setattr(file_safety, "_chmod_required", denied_final_permissions)
    with pytest.raises(PermissionError, match="final profile permissions denied"):
        import_profiles_into_store(source, store)
    assert store.path.read_bytes() == before
    assert [profile.name for profile in store.load()] == ["existing"]
    assert not list(tmp_path.glob(".stored.json.*.tmp"))


@pytest.mark.parametrize("replace", [False, True])
def test_import_replace_failure_preserves_store_and_cleans_staging(monkeypatch, tmp_path, replace) -> None:
    store = ProfileStore(tmp_path / "stored.json")
    store.add(Profile(name="existing", protocol="ssh", host="old.example.invalid"))
    before = store.path.read_bytes()
    source = _bundle(
        tmp_path / "import.json",
        Profile(name="new", protocol="ssh", host="new.example.invalid"),
        Profile(name="existing" if replace else "other", protocol="ssh", host="other.example.invalid"),
    )

    def denied(_source, destination):
        raise PermissionError(errno.EACCES, "Permission denied", str(destination))

    monkeypatch.setattr(file_safety.os, "replace", denied)
    with pytest.raises(PermissionError, match="Permission denied"):
        import_profiles_into_store(source, store, replace=replace)

    assert store.path.read_bytes() == before
    assert list(tmp_path.glob(".stored.json.*.tmp")) == []


def test_batch_import_commits_once_preserves_defaults_and_skips_existing(monkeypatch, tmp_path) -> None:
    store = ProfileStore(tmp_path / "stored.json")
    store.add(Profile(name="existing", protocol="ssh", host="old.example.invalid"))
    store.set_group_defaults("operators", {"username": "operator"})
    calls = []
    original_replace = file_safety.os.replace

    def replace(source, destination):
        calls.append(destination)
        original_replace(source, destination)

    monkeypatch.setattr(file_safety.os, "replace", replace)
    accepted = store.add_many(
        [
            Profile(name="new", protocol="ssh", host="new.example.invalid", group="operators"),
            Profile(name="existing", protocol="ssh", host="ignored.example.invalid"),
        ],
        skip_existing=True,
        surface="profile-editor",
    )

    assert [profile.name for profile in accepted] == ["new"]
    assert len(calls) == 1
    assert store.get("existing").host == "old.example.invalid"
    assert store.get("new").username == "operator"
    assert store.group_defaults() == {"operators": {"username": "operator"}}
    before = store.path.read_bytes()
    assert store.add_many([accepted[0]], skip_existing=True) == []
    assert store.add_many([]) == []
    assert len(calls) == 1
    assert store.path.read_bytes() == before


def test_batch_import_rejects_duplicate_names_and_invalid_late_profile(tmp_path) -> None:
    store = ProfileStore(tmp_path / "stored.json")
    existing = Profile(name="existing", protocol="ssh", host="old.example.invalid")
    store.add(existing)
    before = store.path.read_bytes()
    with pytest.raises(ValueError, match="duplicate normalized profile names"):
        store.add_many([existing, existing], replace=True)
    with pytest.raises(ValueError, match="requires host"):
        store.add_many([Profile(name="new", protocol="ssh", host="new.example.invalid"), Profile(name="invalid", protocol="ssh")])
    assert store.path.read_bytes() == before


def test_cli_reports_read_and_write_permission_errors_without_traceback(monkeypatch, tmp_path, capsys) -> None:
    monkeypatch.setenv("ROW_HOME", str(tmp_path))
    store = ProfileStore()
    store.add(Profile(name="existing", protocol="ssh", host="old.example.invalid"))
    before = store.path.read_bytes()
    original_read = Path.read_text

    def denied_read(path, *args, **kwargs):
        if path == store.path:
            raise PermissionError(errno.EACCES, "Permission denied", str(path))
        return original_read(path, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(Path, "read_text", denied_read)
        assert cli.main(["profile", "list", "--json"]) == 1
    read_error = capsys.readouterr().err
    assert "Permission denied" in read_error
    assert repr(str(store.path)) in read_error
    assert "Traceback" not in read_error

    def denied_replace(_source, destination):
        raise PermissionError(errno.EACCES, "Permission denied", str(destination))

    monkeypatch.setattr(file_safety.os, "replace", denied_replace)
    assert cli.main(["profile", "add", "--name", "new", "--protocol", "ssh", "--host", "new.example.invalid"]) == 1
    write_error = capsys.readouterr().err
    assert "Permission denied" in write_error
    assert "Traceback" not in write_error
    assert store.path.read_bytes() == before


def test_cli_keeps_unexpected_programming_errors_visible(monkeypatch) -> None:
    def unexpected(_args):
        raise RuntimeError("unexpected implementation failure")

    monkeypatch.setattr(cli, "cmd_welcome", unexpected)
    with pytest.raises(RuntimeError, match="unexpected implementation failure"):
        cli.main(["welcome"])

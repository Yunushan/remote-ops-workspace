from __future__ import annotations

import argparse
import json

import pytest

from remote_ops_workspace import cli
from remote_ops_workspace.models import Profile
from remote_ops_workspace.storage import ProfileStore


def test_backup_passphrase_prompt_confirms_without_printing(monkeypatch, capsys):
    prompts = []

    def prompt(label):
        prompts.append(label)
        return "isolated recovery passphrase"

    monkeypatch.setattr(cli, "getpass", prompt)
    args = argparse.Namespace(passphrase_env=None)
    assert cli._workspace_backup_passphrase(args, confirm=True) == "isolated recovery passphrase"
    assert prompts == ["Backup passphrase: ", "Confirm backup passphrase: "]
    assert capsys.readouterr().out == ""
    prompts.clear()
    assert cli._workspace_backup_passphrase(args, confirm=False) == "isolated recovery passphrase"
    assert prompts == ["Backup passphrase: "]


def test_backup_rejects_mismatched_confirmation(monkeypatch):
    values = iter(["first recovery passphrase", "different recovery passphrase"])
    monkeypatch.setattr(cli, "getpass", lambda _label: next(values))
    with pytest.raises(ValueError, match="do not match"):
        cli._workspace_backup_passphrase(argparse.Namespace(passphrase_env=None), confirm=True)


@pytest.mark.parametrize("action", ["backup", "restore"])
def test_workspace_cli_requires_explicit_offline_prerequisite(action, tmp_path):
    options = ["--out", str(tmp_path / "backup.rowbak")] if action == "backup" else [
        "--backup", str(tmp_path / "backup.rowbak"), "--destination", str(tmp_path / "restored"),
    ]
    with pytest.raises(SystemExit) as error:
        cli.main(["workspace", action, *options])
    assert error.value.code == 2
    assert list(tmp_path.iterdir()) == []


def test_workspace_cli_full_state_roundtrip_and_secret_safe_output(tmp_path, monkeypatch, capsys):
    pytest.importorskip("cryptography")
    original = tmp_path / "original"
    backup = tmp_path / "snapshot.rowbak"
    restored = tmp_path / "restored"
    monkeypatch.setenv("ROW_HOME", str(original))
    monkeypatch.setenv("ROW_TEST_BACKUP_PASSPHRASE", "isolated recovery passphrase")
    store = ProfileStore()
    store.init(with_examples=False)
    store.add(Profile(name="recovery profile", protocol="ssh", host="127.0.0.1"))
    plugin = original / "plugin-state" / "future-state.bin"
    plugin.parent.mkdir()
    secret = b"dummy opaque plugin secret\x00\xff"
    plugin.write_bytes(secret)
    profile_bytes = store.path.read_bytes()

    assert cli.main([
        "workspace", "backup", "--out", str(backup), "--offline",
        "--passphrase-env", "ROW_TEST_BACKUP_PASSPHRASE",
    ]) == 0
    first_output = capsys.readouterr()
    assert isinstance(json.loads(first_output.out), dict)
    assert secret not in backup.read_bytes()
    assert "isolated recovery passphrase" not in first_output.out + first_output.err
    plugin.write_bytes(b"new state after snapshot")

    assert cli.main([
        "workspace", "restore", "--backup", str(backup), "--destination", str(restored),
        "--offline", "--passphrase-env", "ROW_TEST_BACKUP_PASSPHRASE",
    ]) == 0
    second_output = capsys.readouterr()
    assert isinstance(json.loads(second_output.out), dict)
    assert "dummy opaque plugin secret" not in second_output.out + second_output.err
    assert "isolated recovery passphrase" not in second_output.out + second_output.err
    assert (restored / "profiles.json").read_bytes() == profile_bytes
    assert (restored / "plugin-state" / "future-state.bin").read_bytes() == secret
    assert plugin.read_bytes() == b"new state after snapshot"
    assert ProfileStore(restored / "profiles.json").get("recovery profile").host == "127.0.0.1"


def test_workspace_cli_reports_invalid_backup_without_touching_original(tmp_path, monkeypatch, capsys):
    original = tmp_path / "original"
    original.mkdir()
    sentinel = original / "operator-state"
    sentinel.write_bytes(b"retain original")
    backup = tmp_path / "invalid.rowbak"
    backup.write_text("{}", encoding="utf-8")
    destination = tmp_path / "restored"
    monkeypatch.setenv("ROW_HOME", str(original))
    monkeypatch.setenv("ROW_TEST_BACKUP_PASSPHRASE", "isolated recovery passphrase")

    assert cli.main([
        "workspace", "restore", "--backup", str(backup), "--destination", str(destination),
        "--offline", "--passphrase-env", "ROW_TEST_BACKUP_PASSPHRASE",
    ]) == 1
    assert capsys.readouterr().err.startswith("error: ")
    assert sentinel.read_bytes() == b"retain original"
    assert not destination.exists()

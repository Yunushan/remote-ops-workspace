from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import qualify_windows_msi_upgrade as upgrade
from scripts import windows_msi_workspace_recovery as recovery_source


def test_signed_workflow_recovery_uses_real_encrypted_cli_and_preserves_both_trees(monkeypatch, tmp_path):
    monkeypatch.setattr(recovery_source, "private_parent", lambda path: path.mkdir())
    # Run the real CLI and encryption backend in isolated subprocesses. The
    # separate launcher marker makes the fixture independent of native builds.
    row = tmp_path / "row.exe"
    row.write_bytes(b"launcher marker")
    sha256 = upgrade.fingerprint(row)
    source = Path(__file__).resolve().parents[1] / "src"
    launcher = ("import sys; sys.path.insert(0, " + repr(str(source)) + "); "
                "from remote_ops_workspace.cli import main; raise SystemExit(main())")
    original = subprocess.run

    held = set()

    def hold(path, *, read_only):
        assert path == str(row) and read_only and not held
        held.add(path)
        return path

    def run(command, **options):
        assert command[0] == str(row) and held == {str(row)}
        assert options["env"].get("GITHUB_TOKEN") is None
        return original([sys.executable, "-I", "-c", launcher, *command[1:]], **options)

    monkeypatch.setenv("GITHUB_TOKEN", "synthetic-token")
    monkeypatch.setattr(recovery_source.subprocess, "run", run)
    storage = SimpleNamespace(open_file=hold, close=held.remove)
    recovery = recovery_source.WorkspaceRecovery(tmp_path / "recovery", storage=storage)
    recovery.seed_and_backup(row, sha256)
    recovery.verify_original(row, sha256)
    archived = json.loads(recovery.archive.read_bytes())
    assert archived["token"]
    assert recovery_source.SECRET.encode() not in recovery.archive.read_bytes()
    assert recovery.secret.encode() not in recovery.archive.read_bytes()
    recovery.restore_with_candidate(row, sha256)
    report = recovery.verify_restored(row, sha256)
    assert report["predecessor_decrypted_restored_vault"] is True
    assert report["upgraded_workspace_unchanged"] is True
    assert recovery_source._tree_summary(recovery.restored) == report["pre_upgrade_inventory"]
    assert recovery_source._tree_summary(recovery.home) == report["upgraded_inventory"]
    assert recovery_source.UPGRADE_SECRET.encode() not in (recovery.restored / "profiles.json").read_bytes()
    assert not list(recovery.root.glob("vault-probe-*")) and not held

    with pytest.raises(ValueError, match="registered launcher bytes differ"):
        recovery.command(row, "0" * 64, recovery.home, "profile", "list")
    assert not held

    (recovery.home / "unexpected-write").write_bytes(b"unexpected")
    with pytest.raises(ValueError, match="changed the upgraded workspace"):
        recovery.verify_restored(row, sha256)

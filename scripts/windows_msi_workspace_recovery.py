"""Exercise encrypted workspace recovery through the signed native CLI."""

from __future__ import annotations

import json
import secrets
import subprocess
from contextlib import contextmanager
from pathlib import Path
from tempfile import TemporaryDirectory

from inspect_windows_msi import fingerprint, require
from native_installer_recovery import clean_environment, private_parent
from smoke_workspace_recovery import _tree_summary

from remote_ops_workspace.windows_private_storage import _Native, private_stage_guard
from remote_ops_workspace.workspace_backup import create_workspace_backup

PROFILE = "rollback-profile"
SECRET = "rollback-vault-entry"
UPGRADE_PROFILE = "upgrade-only-profile"
UPGRADE_SECRET = "upgrade-only-vault-entry"


@contextmanager
def locked_launcher(storage: _Native, row: Path, sha256: str):
    held = storage.open_file(str(row), read_only=True)
    try:
        require(fingerprint(row) == sha256, "registered launcher bytes differ from the exact MSI payload")
        yield
        require(fingerprint(row) == sha256, "registered launcher changed during execution")
    finally:
        storage.close(held)


class WorkspaceRecovery:
    def __init__(self, root: Path, *, storage: _Native) -> None:
        private_parent(root)
        self.root = root
        self.storage = storage
        self.home = root / "workspace"
        with private_stage_guard(self.home, create=True, _native=storage):
            pass
        self.restored = root / "restored"
        self.archive = root / "previous.rowbackup"
        self.password = secrets.token_urlsafe(32)
        self.backup_password = secrets.token_urlsafe(32)
        self.secret = secrets.token_urlsafe(48)
        self.upgraded_secret = secrets.token_urlsafe(48)

    def command(self, row: Path, sha256: str, home: Path, *args: str, value: str | None = None) -> str:
        with locked_launcher(self.storage, row, sha256):
            result = subprocess.run(
                [str(row), *args], cwd=self.root,
                env=clean_environment(home, self.password, self.backup_password),
                input=value or "", capture_output=True, text=True, encoding="utf-8", timeout=180, check=False,
            )
            require(result.returncode == 0, "signed launcher failed a workspace recovery command")
        return result.stdout

    def verify_state(self, row: Path, sha256: str, home: Path, *, upgraded=False) -> None:
        expected_profiles = {PROFILE: ("ssh", "rollback.invalid", SECRET)}
        expected_secrets = {SECRET: self.secret}
        if upgraded:
            expected_profiles[UPGRADE_PROFILE] = ("ssh", "upgrade.invalid", UPGRADE_SECRET)
            expected_secrets[UPGRADE_SECRET] = self.upgraded_secret
        profiles = json.loads(self.command(row, sha256, home, "profile", "list", "--json"))
        observed = {item["name"]: (item["protocol"], item["host"], item["credential_ref"]) for item in profiles}
        require(len(profiles) == len(expected_profiles) and observed == expected_profiles,
                "signed launcher workspace profile records differ from the fixture")
        actual = self.command(row, sha256, home, "vault", "list").splitlines()
        require(actual == sorted(expected_secrets), "signed launcher vault labels differ from the fixture")
        with TemporaryDirectory(prefix="vault-probe-", dir=self.root) as directory:
            for index, (label, secret) in enumerate(expected_secrets.items()):
                output = Path(directory) / f"secret-{index}.txt"
                self.command(row, sha256, home, "vault", "get", label, "--out", str(output))
                require(output.read_text(encoding="utf-8") == secret,
                        "signed launcher decrypted a different vault value")

    def seed_and_backup(self, row: Path, sha256: str) -> None:
        self.command(row, sha256, self.home, "init", "--no-examples", "--quiet")
        self.command(row, sha256, self.home, "vault", "init")
        self.command(row, sha256, self.home, "vault", "set", SECRET, "--stdin", value=self.secret)
        self.command(row, sha256, self.home, "profile", "add", "--name", PROFILE, "--protocol", "ssh",
                     "--host", "rollback.invalid", "--credential-ref", SECRET)
        opaque = self.home / "plugins" / "fixture"
        opaque.mkdir(parents=True)
        (opaque / "state.bin").write_bytes(b"opaque-workspace-fixture\0")
        (opaque / "empty").mkdir()
        self.verify_state(row, sha256, self.home)
        self.previous_tree = _tree_summary(self.home)
        create_workspace_backup(self.home, self.archive, self.backup_password, offline_confirmed=True)
        self.archive_sha256 = fingerprint(self.archive)
        self.verify_original(row, sha256)

    def verify_original(self, row: Path, sha256: str) -> None:
        self.verify_state(row, sha256, self.home)
        require(_tree_summary(self.home) == self.previous_tree, "original workspace changed during the installer transition")
        require(fingerprint(self.archive) == self.archive_sha256, "encrypted pre-upgrade backup changed")

    def restore_with_candidate(self, row: Path, sha256: str) -> None:
        self.verify_original(row, sha256)
        self.command(row, sha256, self.home, "vault", "set", UPGRADE_SECRET, "--stdin", value=self.upgraded_secret)
        self.command(row, sha256, self.home, "profile", "add", "--name", UPGRADE_PROFILE, "--protocol", "ssh",
                     "--host", "upgrade.invalid", "--credential-ref", UPGRADE_SECRET)
        self.verify_state(row, sha256, self.home, upgraded=True)
        self.upgraded_tree = _tree_summary(self.home)
        require(self.upgraded_tree != self.previous_tree, "candidate did not create newer workspace state")
        self.command(row, sha256, self.home, "workspace", "restore", "--offline", "--backup", str(self.archive),
                     "--destination", str(self.restored), "--passphrase-env", "ROW_RECOVERY_PASSWORD")
        require(_tree_summary(self.restored) == self.previous_tree, "restored workspace inventory differs from the backup")

    def verify_restored(self, row: Path, sha256: str) -> dict:
        self.verify_state(row, sha256, self.restored)
        require(_tree_summary(self.restored) == self.previous_tree, "restored workspace changed during predecessor validation")
        require(_tree_summary(self.home) == self.upgraded_tree, "restore or rollback changed the upgraded workspace")
        require(fingerprint(self.archive) == self.archive_sha256, "encrypted pre-upgrade backup changed")
        return {"encrypted_backup_sha256": self.archive_sha256, "pre_upgrade_inventory": self.previous_tree,
                "upgraded_inventory": self.upgraded_tree, "restored_matches_pre_upgrade": True,
                "upgraded_workspace_unchanged": True, "predecessor_decrypted_restored_vault": True}

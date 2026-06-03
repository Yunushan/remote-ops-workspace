from __future__ import annotations

import io
import json
import os
from pathlib import Path

from remote_ops_workspace.cli import build_parser, cmd_vault_delete
from remote_ops_workspace.cli import _strip_one_trailing_newline, _vault_secret_value
from remote_ops_workspace.vault import LocalVault, VaultError, validate_secret_name


def test_validate_secret_name_allows_grouped_references() -> None:
    assert validate_secret_name(" prod/router-password ") == "prod/router-password"
    assert validate_secret_name("team/db:password@primary") == "team/db:password@primary"


def test_validate_secret_name_rejects_unsafe_names() -> None:
    for name in ["", " ", "-bad", "bad name", "bad\nname", "../secret", "prod/../secret"]:
        try:
            validate_secret_name(name)
        except VaultError as exc:
            assert "secret name" in str(exc)
        else:
            raise AssertionError(f"unsafe vault secret name should be rejected: {name!r}")


def test_vault_status_reports_metadata_without_secret_values(tmp_path: Path) -> None:
    path = tmp_path / "vault.json"
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "kdf": "scrypt",
                "salt": "not-used-by-status",
                "items": {"prod/router-password": "token", "team/db": "token"},
            }
        ),
        encoding="utf-8",
    )

    status = LocalVault(path).status()
    payload = status.to_dict()

    assert status.initialized is True
    assert status.item_count == 2
    assert status.version == 1
    assert status.kdf == "scrypt"
    assert payload["path"] == str(path)
    assert "prod/router-password" not in json.dumps(payload)


def test_vault_status_reports_missing_vault(tmp_path: Path) -> None:
    status = LocalVault(tmp_path / "missing-vault.json").status()

    assert status.initialized is False
    assert status.item_count is None


def test_vault_secret_value_reads_from_environment() -> None:
    old = os.environ.get("ROW_TEST_SECRET")
    os.environ["ROW_TEST_SECRET"] = "top-secret"
    try:
        args = build_parser().parse_args(["vault", "set", "prod/router-password", "--secret-env", "ROW_TEST_SECRET"])
        assert _vault_secret_value(args) == "top-secret"
    finally:
        if old is None:
            os.environ.pop("ROW_TEST_SECRET", None)
        else:
            os.environ["ROW_TEST_SECRET"] = old


def test_vault_secret_value_reads_from_stdin_and_strips_one_newline() -> None:
    args = build_parser().parse_args(["vault", "set", "prod/router-password", "--stdin"])

    assert _vault_secret_value(args, io.StringIO("top-secret\n")) == "top-secret"
    assert _vault_secret_value(args, io.StringIO("top-secret\r\n")) == "top-secret"
    assert _vault_secret_value(args, io.StringIO("top-secret\n\n")) == "top-secret\n"


def test_strip_one_trailing_newline_leaves_other_text_intact() -> None:
    assert _strip_one_trailing_newline("secret") == "secret"
    assert _strip_one_trailing_newline("secret\n") == "secret"
    assert _strip_one_trailing_newline("secret\r") == "secret"


def test_vault_delete_requires_force_before_backend_access() -> None:
    args = build_parser().parse_args(["vault", "delete", "prod/router-password"])
    try:
        cmd_vault_delete(args)
    except ValueError as exc:
        assert "--force" in str(exc)
    else:
        raise AssertionError("vault delete should require --force")

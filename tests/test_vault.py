from __future__ import annotations

import base64
import io
import json
import os
from pathlib import Path

import pytest

import remote_ops_workspace.vault as vault_module
from remote_ops_workspace.cli import (
    _strip_one_trailing_newline,
    _vault_secret_value,
    build_parser,
    cmd_vault_delete,
)
from remote_ops_workspace.vault import (
    VAULT_VERSION,
    LocalVault,
    VaultError,
    prompt_passphrase,
    validate_new_passphrase,
    validate_secret_name,
)

PASSPHRASE = "correct horse battery staple"


def test_validate_secret_name_allows_grouped_references() -> None:
    assert validate_secret_name(" prod/router-password ") == "prod/router-password"
    assert validate_secret_name("team/db:password@primary") == "team/db:password@primary"


def test_validate_secret_name_rejects_unsafe_names() -> None:
    for name in [
        "",
        " ",
        "-bad",
        "bad name",
        "bad\nname",
        "../secret",
        "prod/../secret",
        "x" * 201,
    ]:
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
                "salt": base64.b64encode(b"0123456789abcdef").decode("ascii"),
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


def test_vault_roundtrip_authenticates_every_encrypted_write(tmp_path: Path) -> None:
    pytest.importorskip("cryptography")
    path = tmp_path / "vault.json"
    vault = LocalVault(path)

    vault.init(PASSPHRASE)
    initialized = json.loads(path.read_text(encoding="utf-8"))
    assert initialized["version"] == VAULT_VERSION
    assert initialized["verifier"]

    vault.set("prod/router-password", "top-secret", PASSPHRASE)
    assert vault.get("prod/router-password", PASSPHRASE) == "top-secret"
    assert vault.list() == ["prod/router-password"]

    before = path.read_bytes()
    with pytest.raises(VaultError, match="invalid vault passphrase"):
        vault.set("team/db", "must-not-persist", "incorrect passphrase")
    assert path.read_bytes() == before
    assert vault.list() == ["prod/router-password"]

    with pytest.raises(VaultError, match="invalid vault passphrase"):
        vault.get("prod/router-password", "incorrect passphrase")
    vault.delete("prod/router-password")
    assert vault.list() == []


def test_vault_rejects_weak_new_passphrases_and_empty_secrets(tmp_path: Path) -> None:
    pytest.importorskip("cryptography")
    for passphrase in ("", "too-short", "long-enough\n"):
        with pytest.raises(VaultError, match="passphrase"):
            validate_new_passphrase(passphrase)
    with pytest.raises(VaultError, match="1024"):
        validate_new_passphrase("x" * 1025)
    with pytest.raises(VaultError, match="must be text"):
        validate_new_passphrase(None)  # type: ignore[arg-type]

    vault = LocalVault(tmp_path / "vault.json")
    vault.init(PASSPHRASE)
    with pytest.raises(VaultError, match="must not be empty"):
        vault.set("empty", "", PASSPHRASE)
    with pytest.raises(VaultError, match="must not be empty"):
        vault.set("none", None, PASSPHRASE)  # type: ignore[arg-type]


def test_vault_migrates_authenticated_legacy_payload_on_write(tmp_path: Path) -> None:
    pytest.importorskip("cryptography")
    path = tmp_path / "vault.json"
    vault = LocalVault(path)
    salt = base64.b64encode(b"0123456789abcdef").decode("ascii")
    fernet = vault._fernet(PASSPHRASE, salt)
    legacy_token = fernet.encrypt(b"legacy-secret").decode("ascii")
    path.write_text(
        json.dumps(
            {
                "version": 1,
                "kdf": "scrypt",
                "salt": salt,
                "items": {"legacy": legacy_token},
            }
        ),
        encoding="utf-8",
    )

    before = path.read_bytes()
    with pytest.raises(VaultError, match="invalid vault passphrase"):
        vault.set("new", "secret", "incorrect passphrase")
    assert path.read_bytes() == before

    vault.set("new", "new-secret", PASSPHRASE)
    migrated = json.loads(path.read_text(encoding="utf-8"))
    assert migrated["version"] == VAULT_VERSION
    assert migrated["verifier"]
    assert vault.get("legacy", PASSPHRASE) == "legacy-secret"
    assert vault.get("new", PASSPHRASE) == "new-secret"


def test_empty_legacy_vault_establishes_verifier_on_first_write(tmp_path: Path) -> None:
    pytest.importorskip("cryptography")
    path = tmp_path / "vault.json"
    salt = base64.b64encode(b"0123456789abcdef").decode("ascii")
    path.write_text(
        json.dumps({"version": 1, "kdf": "scrypt", "salt": salt, "items": {}}),
        encoding="utf-8",
    )
    vault = LocalVault(path)

    vault.set("first", "secret", PASSPHRASE)

    migrated = json.loads(path.read_text(encoding="utf-8"))
    assert migrated["version"] == VAULT_VERSION
    assert migrated["verifier"]
    assert vault.get("first", PASSPHRASE) == "secret"


def test_vault_rejects_wrong_verifier_plaintext_and_non_utf8_secret(tmp_path: Path) -> None:
    pytest.importorskip("cryptography")
    path = tmp_path / "vault.json"
    vault = LocalVault(path)
    salt = base64.b64encode(b"0123456789abcdef").decode("ascii")
    fernet = vault._fernet(PASSPHRASE, salt)
    payload = {
        "version": VAULT_VERSION,
        "kdf": "scrypt",
        "salt": salt,
        "verifier": fernet.encrypt(b"not-the-vault-verifier").decode("ascii"),
        "items": {},
    }
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(VaultError, match="invalid vault passphrase"):
        vault.set("blocked", "secret", PASSPHRASE)

    payload["verifier"] = fernet.encrypt(vault_module.VAULT_VERIFIER_PLAINTEXT).decode("ascii")
    payload["items"] = {"binary": fernet.encrypt(b"\xff").decode("ascii")}
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(VaultError, match="corrupted vault data"):
        vault.get("binary", PASSPHRASE)


@pytest.mark.parametrize(
    ("payload", "message"),
    [
        ([], "root must be a JSON object"),
        ({"version": True, "kdf": "scrypt", "salt": "", "items": {}}, "version"),
        ({"version": 3, "kdf": "scrypt", "salt": "", "items": {}}, "version"),
        (
            {"version": 1, "kdf": "pbkdf2", "salt": "", "items": {}},
            "KDF",
        ),
        ({"version": 1, "kdf": "scrypt", "salt": "%%%", "items": {}}, "base64"),
        ({"version": 1, "kdf": "scrypt", "salt": None, "items": {}}, "base64 text"),
        (
            {
                "version": 1,
                "kdf": "scrypt",
                "salt": base64.b64encode(b"short").decode("ascii"),
                "items": {},
            },
            "16 bytes",
        ),
        (
            {
                "version": 1,
                "kdf": "scrypt",
                "salt": base64.b64encode(b"0123456789abcdef").decode("ascii"),
                "items": [],
            },
            "items must be",
        ),
        (
            {
                "version": 1,
                "kdf": "scrypt",
                "salt": base64.b64encode(b"0123456789abcdef").decode("ascii"),
                "items": {"bad name": "token"},
            },
            "secret name",
        ),
        (
            {
                "version": 1,
                "kdf": "scrypt",
                "salt": base64.b64encode(b"0123456789abcdef").decode("ascii"),
                "items": {"valid": ""},
            },
            "non-empty token",
        ),
        (
            {
                "version": VAULT_VERSION,
                "kdf": "scrypt",
                "salt": base64.b64encode(b"0123456789abcdef").decode("ascii"),
                "items": {},
            },
            "verifier",
        ),
        (
            {
                "version": VAULT_VERSION,
                "kdf": "scrypt",
                "salt": base64.b64encode(b"0123456789abcdef").decode("ascii"),
                "verifier": "not-ascii-\u00e9",
                "items": {},
            },
            "ASCII token",
        ),
    ],
)
def test_vault_rejects_malformed_schema(tmp_path: Path, payload: object, message: str) -> None:
    path = tmp_path / "vault.json"
    path.write_text(json.dumps(payload), encoding="utf-8")

    with pytest.raises(VaultError, match=message):
        LocalVault(path).status()


def test_vault_schema_rejects_nontext_item_names_and_accepts_legacy_verifier() -> None:
    payload: dict[str, object] = {
        "version": 1,
        "kdf": "scrypt",
        "salt": base64.b64encode(b"0123456789abcdef").decode("ascii"),
        "items": {1: "token"},
    }
    with pytest.raises(VaultError, match="item names must be text"):
        vault_module._validate_vault_payload(payload, Path("vault.json"))

    payload["items"] = {}
    payload["verifier"] = "legacy-token"
    assert vault_module._validate_vault_payload(payload, Path("vault.json")) == payload


def test_vault_reports_invalid_json_and_missing_or_duplicate_operations(tmp_path: Path) -> None:
    pytest.importorskip("cryptography")
    path = tmp_path / "vault.json"
    path.write_text("{", encoding="utf-8")
    with pytest.raises(VaultError, match="not valid JSON"):
        LocalVault(path).status()

    missing = LocalVault(tmp_path / "missing.json")
    with pytest.raises(VaultError, match="not initialized"):
        missing.list()

    vault = LocalVault(tmp_path / "initialized.json")
    vault.init(PASSPHRASE)
    with pytest.raises(VaultError, match="already exists"):
        vault.init(PASSPHRASE)
    with pytest.raises(VaultError, match="secret not found"):
        vault.get("missing", PASSPHRASE)
    with pytest.raises(VaultError, match="secret not found"):
        vault.delete("missing")


def test_prompt_passphrase_confirms_or_rejects(monkeypatch) -> None:
    answers = iter([PASSPHRASE, PASSPHRASE])
    monkeypatch.setattr(vault_module, "getpass", lambda _prompt: next(answers))
    assert prompt_passphrase(confirm=True) == PASSPHRASE

    mismatched = iter([PASSPHRASE, "different passphrase"])
    monkeypatch.setattr(vault_module, "getpass", lambda _prompt: next(mismatched))
    with pytest.raises(VaultError, match="do not match"):
        prompt_passphrase(confirm=True)

    monkeypatch.setattr(vault_module, "getpass", lambda _prompt: PASSPHRASE)
    assert prompt_passphrase(confirm=False) == PASSPHRASE


def test_vault_wraps_file_read_failures(monkeypatch, tmp_path: Path) -> None:
    path = tmp_path / "vault.json"
    path.write_text("{}", encoding="utf-8")

    def deny_read(_path: Path, *args, **kwargs):
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "read_text", deny_read)
    with pytest.raises(VaultError, match="unable to read vault file"):
        LocalVault(path).status()


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

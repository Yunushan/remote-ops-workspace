from __future__ import annotations

import base64
import binascii
import importlib.util
import json
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from getpass import getpass
from pathlib import Path
from typing import Any

from .file_safety import write_json_atomic
from .paths import ensure_data_dir
from .state_lock import DEFAULT_LOCK_TIMEOUT_SECONDS, FileLockTimeoutError, exclusive_file_lock

VAULT_VERSION = 3
VAULT_KDF = "scrypt"
VAULT_MIN_PASSPHRASE_LENGTH = 12
VAULT_VERIFIER_PLAINTEXT = b"remote-ops-workspace vault verifier v1"
VAULT_LEGACY_SCRYPT_PARAMS = {"n": 2**14, "r": 8, "p": 1}
# OWASP's minimum-equivalent scrypt sets include N=2^15, r=8, p=3. Keeping
# the parameters in the payload lets a future version raise the cost without
# silently changing how existing ciphertext is derived.
VAULT_SCRYPT_PARAMS = {"n": 2**15, "r": 8, "p": 3}
VAULT_SUPPORTED_VERSIONS = frozenset({1, 2, VAULT_VERSION})


class VaultBackendUnavailable(RuntimeError):
    pass


class VaultError(RuntimeError):
    pass


@dataclass(frozen=True, slots=True)
class VaultStatus:
    path: Path
    initialized: bool
    backend_available: bool
    item_count: int | None = None
    version: int | None = None
    kdf: str | None = None
    kdf_params: dict[str, int] | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "initialized": self.initialized,
            "backend_available": self.backend_available,
            "item_count": self.item_count,
            "version": self.version,
            "kdf": self.kdf,
            "kdf_params": dict(self.kdf_params) if self.kdf_params is not None else None,
        }


class LocalVault:
    """Local encrypted vault using cryptography/Fernet + Scrypt.

    The module imports cryptography lazily. Vault commands fail closed when the
    dependency is not installed.
    """

    def __init__(
        self,
        path: Path | None = None,
        *,
        lock_timeout_seconds: float = DEFAULT_LOCK_TIMEOUT_SECONDS,
    ) -> None:
        self.path = path or (ensure_data_dir() / "vault.json")
        self.lock_timeout_seconds = lock_timeout_seconds

    def init(self, passphrase: str) -> None:
        self._require_crypto()
        passphrase = validate_new_passphrase(passphrase)
        with self._transaction():
            if self.path.exists():
                raise VaultError(f"vault already exists: {self.path}")
            data = self._empty(passphrase)
            write_json_atomic(self.path, data, private=True, sort_keys=False)

    def set(self, name: str, secret: str, passphrase: str) -> None:
        name = validate_secret_name(name)
        if not isinstance(secret, str) or secret == "":
            raise VaultError("secret value must not be empty")
        with self._transaction():
            data = self._load()
            fernet = self._authenticate(passphrase, data)
            fernet = self._upgrade_payload(data, passphrase, fernet)
            token = fernet.encrypt(secret.encode("utf-8")).decode("ascii")
            data["items"][name] = token
            self._save(data)

    def get(self, name: str, passphrase: str) -> str:
        name = validate_secret_name(name)
        data = self._load()
        items = data["items"]
        if name not in items:
            raise VaultError(f"secret not found: {name}")
        token = items[name]
        fernet = self._authenticate(passphrase, data, candidate_token=token)
        try:
            return self._decrypt_token(fernet, token).decode("utf-8")
        except UnicodeDecodeError as exc:
            raise VaultError("invalid vault passphrase or corrupted vault data") from exc

    def delete(self, name: str, passphrase: str) -> None:
        name = validate_secret_name(name)
        with self._transaction():
            data = self._load()
            fernet = self._authenticate(passphrase, data)
            self._upgrade_payload(data, passphrase, fernet)
            items = data["items"]
            if name not in items:
                raise VaultError(f"secret not found: {name}")
            del items[name]
            self._save(data)

    def list(self) -> list[str]:
        data = self._load()
        return sorted(data["items"].keys())

    def status(self) -> VaultStatus:
        if not self.path.exists():
            return VaultStatus(
                path=self.path,
                initialized=False,
                backend_available=self.crypto_available(),
            )
        data = self._read_payload()
        items = data["items"]
        return VaultStatus(
            path=self.path,
            initialized=True,
            backend_available=self.crypto_available(),
            item_count=len(items),
            version=data["version"],
            kdf=data["kdf"],
            kdf_params=dict(data["kdf_params"]) if "kdf_params" in data else None,
        )

    def _load(self) -> dict[str, Any]:
        self._require_crypto()
        if not self.path.exists():
            raise VaultError("vault not initialized; run `row vault init`")
        return self._read_payload()

    def _read_payload(self) -> dict[str, Any]:
        try:
            raw = json.loads(self.path.read_text(encoding="utf-8"))
        except OSError as exc:
            raise VaultError(f"unable to read vault file: {self.path}: {exc}") from exc
        except json.JSONDecodeError as exc:
            raise VaultError(f"vault file is not valid JSON: {self.path}") from exc
        return _validate_vault_payload(raw, self.path)

    def _save(self, data: dict[str, Any]) -> None:
        _validate_vault_payload(data, self.path)
        write_json_atomic(self.path, data, private=True)

    @contextmanager
    def _transaction(self) -> Iterator[None]:
        try:
            with exclusive_file_lock(self.path, timeout_seconds=self.lock_timeout_seconds):
                yield
        except FileLockTimeoutError as exc:
            raise VaultError(f"vault is busy; retry after the current update: {self.path}") from exc

    def _empty(self, passphrase: str) -> dict[str, Any]:
        import os

        salt = base64.b64encode(os.urandom(16)).decode("ascii")
        fernet = self._fernet(passphrase, salt, VAULT_SCRYPT_PARAMS)
        verifier = fernet.encrypt(VAULT_VERIFIER_PLAINTEXT).decode("ascii")
        return {
            "version": VAULT_VERSION,
            "kdf": VAULT_KDF,
            "kdf_params": dict(VAULT_SCRYPT_PARAMS),
            "salt": salt,
            "verifier": verifier,
            "items": {},
        }

    def _authenticate(
        self,
        passphrase: str,
        data: dict[str, Any],
        *,
        candidate_token: str | None = None,
    ):  # type: ignore[no-untyped-def]
        fernet = self._fernet(
            passphrase,
            data["salt"],
            data.get("kdf_params", VAULT_LEGACY_SCRYPT_PARAMS),
        )
        verifier = data.get("verifier")
        if verifier is not None:
            plaintext = self._decrypt_token(fernet, verifier)
            if plaintext != VAULT_VERIFIER_PLAINTEXT:
                raise VaultError("invalid vault passphrase or corrupted vault data")
            return fernet

        legacy_token = candidate_token
        if legacy_token is None and data["items"]:
            legacy_token = next(iter(data["items"].values()))
        if legacy_token is not None:
            self._decrypt_token(fernet, legacy_token)
        return fernet

    def _upgrade_payload(
        self,
        data: dict[str, Any],
        passphrase: str,
        fernet,
    ):  # type: ignore[no-untyped-def]
        if data["version"] >= VAULT_VERSION:
            return fernet
        plaintext_items = {
            name: self._decrypt_token(fernet, token)
            for name, token in data["items"].items()
        }
        import os

        salt = base64.b64encode(os.urandom(16)).decode("ascii")
        upgraded_fernet = self._fernet(passphrase, salt, VAULT_SCRYPT_PARAMS)
        data["version"] = VAULT_VERSION
        data["salt"] = salt
        data["kdf_params"] = dict(VAULT_SCRYPT_PARAMS)
        data["verifier"] = upgraded_fernet.encrypt(VAULT_VERIFIER_PLAINTEXT).decode("ascii")
        data["items"] = {
            name: upgraded_fernet.encrypt(value).decode("ascii")
            for name, value in plaintext_items.items()
        }
        return upgraded_fernet

    @staticmethod
    def _decrypt_token(fernet, token: str) -> bytes:  # type: ignore[no-untyped-def]
        from cryptography.fernet import InvalidToken

        try:
            return fernet.decrypt(token.encode("ascii"))
        except (InvalidToken, UnicodeEncodeError, ValueError) as exc:
            raise VaultError("invalid vault passphrase or corrupted vault data") from exc

    def _fernet(
        self,
        passphrase: str,
        salt_b64: str,
        params: dict[str, int] | None = None,
    ):  # type: ignore[no-untyped-def]
        self._require_crypto()
        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

        salt = base64.b64decode(salt_b64.encode("ascii"))
        selected = params or VAULT_LEGACY_SCRYPT_PARAMS
        kdf = Scrypt(
            salt=salt,
            length=32,
            n=selected["n"],
            r=selected["r"],
            p=selected["p"],
        )
        key = base64.urlsafe_b64encode(kdf.derive(passphrase.encode("utf-8")))
        return Fernet(key)

    @staticmethod
    def _require_crypto() -> None:
        try:
            import cryptography  # noqa: F401
        except Exception as exc:  # pragma: no cover - depends on optional package
            raise VaultBackendUnavailable("install with: pip install -e '.[security]'") from exc

    @staticmethod
    def crypto_available() -> bool:
        return importlib.util.find_spec("cryptography") is not None


def validate_secret_name(name: str) -> str:
    cleaned = str(name).strip()
    if not cleaned:
        raise VaultError("secret name is required")
    if len(cleaned) > 200:
        raise VaultError("secret name must be 200 characters or fewer")
    if cleaned.startswith("-"):
        raise VaultError("secret name must not start with '-'")
    if any(char.isspace() or ord(char) < 32 or ord(char) == 127 for char in cleaned):
        raise VaultError("secret name must not contain whitespace or control characters")
    if cleaned in {".", ".."} or "/../" in f"/{cleaned}/":
        raise VaultError("secret name must not contain parent-directory segments")
    return cleaned


def validate_new_passphrase(passphrase: str) -> str:
    if not isinstance(passphrase, str):
        raise VaultError("vault passphrase must be text")
    if len(passphrase) < VAULT_MIN_PASSPHRASE_LENGTH:
        raise VaultError(
            f"vault passphrase must contain at least {VAULT_MIN_PASSPHRASE_LENGTH} characters"
        )
    if len(passphrase) > 1024:
        raise VaultError("vault passphrase must contain 1024 characters or fewer")
    if any(ord(char) < 32 or ord(char) == 127 for char in passphrase):
        raise VaultError("vault passphrase must not contain control characters")
    return passphrase


def _validate_vault_payload(raw: object, path: Path) -> dict[str, Any]:
    if not isinstance(raw, dict):
        raise VaultError(f"vault root must be a JSON object: {path}")
    version = raw.get("version")
    if type(version) is not int or version not in VAULT_SUPPORTED_VERSIONS:
        raise VaultError(f"unsupported vault version: {version!r}")
    if raw.get("kdf") != VAULT_KDF:
        raise VaultError(f"unsupported vault KDF: {raw.get('kdf')!r}")

    salt = raw.get("salt")
    if not isinstance(salt, str):
        raise VaultError("vault salt must be base64 text")
    try:
        decoded_salt = base64.b64decode(salt.encode("ascii"), validate=True)
    except (UnicodeEncodeError, binascii.Error, ValueError) as exc:
        raise VaultError("vault salt must be valid base64 text") from exc
    if len(decoded_salt) != 16:
        raise VaultError("vault salt must decode to 16 bytes")

    if version == VAULT_VERSION:
        _validate_current_kdf_params(raw.get("kdf_params"))
    elif "kdf_params" in raw:
        raise VaultError("legacy vault versions must not contain kdf_params")

    items = raw.get("items")
    if not isinstance(items, dict):
        raise VaultError("vault items must be a JSON object")
    for name, token in items.items():
        if not isinstance(name, str):
            raise VaultError("vault item names must be text")
        validate_secret_name(name)
        _validate_token_text(token, f"vault item {name}")

    verifier = raw.get("verifier")
    if version >= 2:
        _validate_token_text(verifier, "vault verifier")
    elif verifier is not None:
        _validate_token_text(verifier, "vault verifier")
    return raw


def _validate_current_kdf_params(value: object) -> None:
    if not isinstance(value, dict):
        raise VaultError("vault kdf_params must be an object")
    if set(value) != set(VAULT_SCRYPT_PARAMS):
        raise VaultError("vault kdf_params must contain exactly n, r and p")
    for key, expected in VAULT_SCRYPT_PARAMS.items():
        actual = value.get(key)
        if type(actual) is not int or actual != expected:
            raise VaultError(
                f"vault kdf_params.{key} must be the supported value {expected}"
            )


def _validate_token_text(value: object, label: str) -> None:
    if not isinstance(value, str) or not value:
        raise VaultError(f"{label} must be non-empty token text")
    try:
        value.encode("ascii")
    except UnicodeEncodeError as exc:
        raise VaultError(f"{label} must contain ASCII token text") from exc


def prompt_passphrase(confirm: bool = False) -> str:
    first = getpass("Vault passphrase: ")
    if confirm:
        second = getpass("Confirm passphrase: ")
        if first != second:
            raise VaultError("passphrases do not match")
    return first

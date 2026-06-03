from __future__ import annotations

import base64
import importlib.util
import json
from dataclasses import dataclass
from getpass import getpass
from pathlib import Path
from typing import Any

from .file_safety import write_json_atomic
from .paths import ensure_data_dir


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

    def to_dict(self) -> dict[str, object]:
        return {
            "path": str(self.path),
            "initialized": self.initialized,
            "backend_available": self.backend_available,
            "item_count": self.item_count,
            "version": self.version,
            "kdf": self.kdf,
        }


class LocalVault:
    """Local encrypted vault using cryptography/Fernet + Scrypt.

    The module imports cryptography lazily. Vault commands fail closed when the
    dependency is not installed.
    """

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (ensure_data_dir() / "vault.json")

    def init(self, passphrase: str) -> None:
        self._require_crypto()
        if self.path.exists():
            raise VaultError(f"vault already exists: {self.path}")
        data = self._empty(passphrase)
        write_json_atomic(self.path, data, private=True, sort_keys=False)

    def set(self, name: str, secret: str, passphrase: str) -> None:
        name = validate_secret_name(name)
        if secret == "":
            raise VaultError("secret value must not be empty")
        data = self._load()
        fernet = self._fernet(passphrase, data["salt"])
        token = fernet.encrypt(secret.encode("utf-8")).decode("ascii")
        data.setdefault("items", {})[name] = token
        self._save(data)

    def get(self, name: str, passphrase: str) -> str:
        name = validate_secret_name(name)
        data = self._load()
        try:
            token = data.get("items", {})[name]
        except KeyError as exc:
            raise VaultError(f"secret not found: {name}") from exc
        fernet = self._fernet(passphrase, data["salt"])
        return fernet.decrypt(token.encode("ascii")).decode("utf-8")

    def delete(self, name: str) -> None:
        name = validate_secret_name(name)
        data = self._load()
        items = data.setdefault("items", {})
        if name not in items:
            raise VaultError(f"secret not found: {name}")
        del items[name]
        self._save(data)

    def list(self) -> list[str]:
        data = self._load()
        return sorted(data.get("items", {}).keys())

    def status(self) -> VaultStatus:
        if not self.path.exists():
            return VaultStatus(
                path=self.path,
                initialized=False,
                backend_available=self.crypto_available(),
            )
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise VaultError(f"vault file is not valid JSON: {self.path}") from exc
        items = data.get("items", {})
        return VaultStatus(
            path=self.path,
            initialized=True,
            backend_available=self.crypto_available(),
            item_count=len(items) if isinstance(items, dict) else None,
            version=data.get("version") if isinstance(data.get("version"), int) else None,
            kdf=data.get("kdf") if isinstance(data.get("kdf"), str) else None,
        )

    def _load(self) -> dict[str, Any]:
        self._require_crypto()
        if not self.path.exists():
            raise VaultError("vault not initialized; run `row vault init`")
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, data: dict[str, Any]) -> None:
        write_json_atomic(self.path, data, private=True)

    def _empty(self, passphrase: str) -> dict[str, Any]:
        import os

        salt = base64.b64encode(os.urandom(16)).decode("ascii")
        # Derive once to validate passphrase/crypto path.
        self._fernet(passphrase, salt)
        return {"version": 1, "kdf": "scrypt", "salt": salt, "items": {}}

    def _fernet(self, passphrase: str, salt_b64: str):  # type: ignore[no-untyped-def]
        self._require_crypto()
        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

        salt = base64.b64decode(salt_b64.encode("ascii"))
        kdf = Scrypt(salt=salt, length=32, n=2**14, r=8, p=1)
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


def prompt_passphrase(confirm: bool = False) -> str:
    first = getpass("Vault passphrase: ")
    if confirm:
        second = getpass("Confirm passphrase: ")
        if first != second:
            raise VaultError("passphrases do not match")
    return first

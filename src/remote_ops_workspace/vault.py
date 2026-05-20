from __future__ import annotations

import base64
import json
from getpass import getpass
from pathlib import Path
from typing import Any

from .paths import ensure_data_dir


class VaultBackendUnavailable(RuntimeError):
    pass


class VaultError(RuntimeError):
    pass


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
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(data, indent=2), encoding="utf-8")

    def set(self, name: str, secret: str, passphrase: str) -> None:
        data = self._load()
        fernet = self._fernet(passphrase, data["salt"])
        token = fernet.encrypt(secret.encode("utf-8")).decode("ascii")
        data.setdefault("items", {})[name] = token
        self._save(data)

    def get(self, name: str, passphrase: str) -> str:
        data = self._load()
        try:
            token = data.get("items", {})[name]
        except KeyError as exc:
            raise VaultError(f"secret not found: {name}") from exc
        fernet = self._fernet(passphrase, data["salt"])
        return fernet.decrypt(token.encode("ascii")).decode("utf-8")

    def list(self) -> list[str]:
        data = self._load()
        return sorted(data.get("items", {}).keys())

    def _load(self) -> dict[str, Any]:
        self._require_crypto()
        if not self.path.exists():
            raise VaultError("vault not initialized; run `row vault init`")
        return json.loads(self.path.read_text(encoding="utf-8"))

    def _save(self, data: dict[str, Any]) -> None:
        self.path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

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


def prompt_passphrase(confirm: bool = False) -> str:
    first = getpass("Vault passphrase: ")
    if confirm:
        second = getpass("Confirm passphrase: ")
        if first != second:
            raise VaultError("passphrases do not match")
    return first

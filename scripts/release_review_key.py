"""Load a release reviewer's Ed25519 PEM from an interactive workstation."""

from __future__ import annotations

import getpass
import sys
import warnings
from pathlib import Path

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives.serialization import load_pem_private_key


def load_review_key(path: Path, *, role: str) -> Ed25519PrivateKey:
    if path.is_symlink() or not path.is_file():
        raise ValueError(f"{role}'s private key must be a regular file")
    key_bytes = path.read_bytes()
    password = None
    if key_bytes.lstrip().startswith(b"-----BEGIN ENCRYPTED PRIVATE KEY-----"):
        if not sys.stdin.isatty():
            raise ValueError(f"open an interactive terminal to unlock the {role}'s key")
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("error", getpass.GetPassWarning)
                password = getpass.getpass(f"{role.capitalize()} key passphrase: ").encode("utf-8")
        except (EOFError, getpass.GetPassWarning) as exc:
            raise ValueError(f"could not read the {role}'s key passphrase without echo") from exc
    try:
        key = load_pem_private_key(key_bytes, password=password)
    except (ValueError, TypeError) as exc:
        raise ValueError("could not unlock an Ed25519 PKCS#8 PEM key") from exc
    if not isinstance(key, Ed25519PrivateKey):
        raise ValueError(f"the {role} key must be Ed25519")
    return key

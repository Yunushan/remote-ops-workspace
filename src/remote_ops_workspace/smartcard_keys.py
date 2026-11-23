from __future__ import annotations

import base64
import hashlib
import re
from pathlib import Path

from .command_safety import clean_text
from .file_safety import write_bytes_atomic
from .paths import ensure_data_dir

PINNED_SMARTCARD_KEY = "smartcard_pinned_public_key"


def smartcard_public_keys(output: bytes) -> list[tuple[str, str]]:
    """Return the OpenSSH fingerprints and public records printed by ssh-keygen."""
    keys: dict[str, str] = {}
    for line in output.splitlines():
        fields = line.split(maxsplit=2)
        if len(fields) < 2 or not re.fullmatch(rb"(?:ssh|ecdsa|sk)-[A-Za-z0-9@_.+-]+", fields[0]):
            continue
        algorithm, encoded = fields[:2]
        try:
            blob = base64.b64decode(encoded, validate=True)
        except ValueError:
            continue
        header = len(algorithm).to_bytes(4, "big") + algorithm
        if not blob.startswith(header) or len(blob) <= len(header):
            continue
        fingerprint = base64.b64encode(hashlib.sha256(blob).digest()).decode("ascii").rstrip("=")
        keys[f"SHA256:{fingerprint}"] = b" ".join((algorithm, encoded)).decode("ascii")
    return list(keys.items())


def parse_pinned_smartcard_key(public_key: str) -> tuple[str, str]:
    record = clean_text(public_key, "smart-card public key").strip().encode("ascii")
    keys = smartcard_public_keys(record)
    if len(keys) != 1 or keys[0][1].encode("ascii") != record:
        raise ValueError("The saved smart-card key must be a single OpenSSH public key.")
    return keys[0]


def materialize_pinned_smartcard_key(public_key: str) -> Path:
    """Create the local public IdentityFile for a portable saved selection."""
    _, canonical = parse_pinned_smartcard_key(public_key)
    content = canonical.encode("ascii") + b"\n"
    path = ensure_data_dir() / "smartcard-identities" / f"{hashlib.sha256(content).hexdigest()}.pub"
    if "${" in str(path):
        raise ValueError("The workspace path contains an OpenSSH environment expansion.")
    write_bytes_atomic(path, content, private=True)
    return path

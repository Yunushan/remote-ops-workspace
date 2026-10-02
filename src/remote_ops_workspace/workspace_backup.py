"""Encrypted offline ROW_HOME recovery, bounded to 64 MiB and 10,000 entries.

Stop other ROW GUI, Web and CLI processes before use. The known store locks and two
inventories detect cooperating writers and source drift, but do not make an
online snapshot safe. Files outside ROW_HOME (SSH keys, served roots, machine
policy and host runtimes) remain external recovery dependencies. File bytes,
empty directories and, on POSIX, the owner executable bit are preserved; other filesystem
metadata is normalized to private permissions. Restores go into a new sibling
directory and never replace the original ROW_HOME.
On Windows, choose an operator-secured destination parent: chmod cannot verify
the inherited DACL of the new sibling or its plaintext staging directory.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import json
import os
import re
import secrets
import shutil
import stat
import tempfile
import unicodedata
from contextlib import ExitStack
from pathlib import Path
from typing import Any

from .file_safety import (
    _require_no_linked_path_components,
    ensure_private_dir_required,
    write_bytes_atomic,
    write_json_atomic,
)
from .state_lock import DEFAULT_LOCK_TIMEOUT_SECONDS, exclusive_file_lock

MAX_TOTAL_BYTES = 64 * 1024 * 1024
MAX_FILES = 10_000
SCHEMA = "row.workspace-backup"
KDF = {"name": "scrypt", "n": 2**15, "r": 8, "p": 3, "length": 32}
KNOWN_STORES = ("profiles.json", "vault.json", "layouts.json", "snippets.json", "moba-macros.json")
MANAGED_RECORDS = {"xserver-state.json", *(f"servers/{service}-server-state.json" for service in ("http", "ftp", "tftp", "ssh", "sftp", "telnet", "vnc", "nfs"))}
KNOWN_ATOMIC_PATHS = {*KNOWN_STORES, *MANAGED_RECORDS}
_RESERVED_NAMES = {"con", "prn", "aux", "nul", "conin$", "conout$", *(f"com{number}" for number in "123456789¹²³"), *(f"lpt{number}" for number in "123456789¹²³")}


class WorkspaceBackupError(ValueError):
    """Recovery refused an unsafe, changing or unauthenticated archive."""


def create_workspace_backup(
    source_home: Path,
    output_path: Path,
    passphrase: str,
    *,
    offline_confirmed: bool = False,
    lock_timeout_seconds: float = DEFAULT_LOCK_TIMEOUT_SECONDS,
    max_total_bytes: int = MAX_TOTAL_BYTES,
    max_files: int = MAX_FILES,
) -> dict[str, Any]:
    """Encrypt every regular user-state file; plaintext remains in memory."""
    _preconditions(passphrase, offline_confirmed, max_total_bytes, max_files)
    source = _checked_absolute(source_home)
    output = _checked_absolute(output_path)
    if not source.is_dir():
        raise WorkspaceBackupError("ROW_HOME must be an existing regular directory")
    if output.is_relative_to(source):
        raise WorkspaceBackupError("backup output must be outside ROW_HOME")
    salt = secrets.token_bytes(16)
    cipher = _cipher(passphrase, salt)
    with ExitStack() as locks:
        lock_names = {*KNOWN_STORES, *(name for name in MANAGED_RECORDS if (source / name).exists())}
        for name in sorted(lock_names):
            locks.enter_context(exclusive_file_lock(source / name, timeout_seconds=lock_timeout_seconds))
        manifest, fingerprint = _inventory(source, max_total_bytes, max_files)
        token = cipher.encrypt(_json_bytes(manifest)).decode("ascii")
        _current, observed = _inventory(source, max_total_bytes, max_files)
        if observed != fingerprint:
            raise WorkspaceBackupError("ROW_HOME changed during backup; stop all writers and retry")
        outer = {"schema": SCHEMA, "version": 1, "salt": base64.b64encode(salt).decode("ascii"), "kdf": KDF, "token": token}
        write_json_atomic(output, outer, private=True)
    return _summary(manifest, output)


def restore_workspace_backup(
    backup_path: Path,
    destination: Path,
    passphrase: str,
    *,
    current_home: Path,
    offline_confirmed: bool = False,
    max_total_bytes: int = MAX_TOTAL_BYTES,
    max_files: int = MAX_FILES,
) -> dict[str, Any]:
    """Validate the entire authenticated archive before creating a new home."""
    _preconditions(passphrase, offline_confirmed, max_total_bytes, max_files)
    original = _checked_absolute(current_home)
    target = _checked_absolute(destination)
    backup = _checked_absolute(backup_path)
    if target == original or target.parent != original.parent:
        raise WorkspaceBackupError("restore destination must be a new direct sibling of ROW_HOME")
    if target.exists():
        raise WorkspaceBackupError("restore destination must not already exist")
    if not target.parent.is_dir():
        raise WorkspaceBackupError("restore destination parent must be an existing directory")
    envelope_limit = max_total_bytes * 2 + max_files * 4096 + 4096
    raw, _status = _read_regular(backup, envelope_limit)
    outer = _load_json(raw)
    if not isinstance(outer, dict) or set(outer) != {"schema", "version", "salt", "kdf", "token"} or outer["schema"] != SCHEMA or type(outer["version"]) is not int or outer["version"] != 1 or _json_bytes(outer["kdf"]) != _json_bytes(KDF):
        raise WorkspaceBackupError("unsupported workspace backup envelope or KDF")
    salt = _decode(outer["salt"])
    if len(salt) != 16 or not isinstance(outer["token"], str):
        raise WorkspaceBackupError("invalid workspace backup salt or token")
    cipher = _cipher(passphrase, salt)
    try:
        plaintext = cipher.decrypt(outer["token"].encode("ascii"))
    except Exception as exc:
        raise WorkspaceBackupError("invalid backup passphrase or corrupted workspace backup") from exc
    manifest, contents = _validate_manifest(_load_json(plaintext), max_total_bytes, max_files)
    stage = Path(tempfile.mkdtemp(prefix=f".{target.name}.row-restore-", suffix=".tmp", dir=target.parent))
    installed = False
    try:
        ensure_private_dir_required(stage)
        for name in sorted(manifest["directories"], key=lambda item: (item.count("/"), item)):
            ensure_private_dir_required(stage / name)
        expected_exec = {row["filename"]: row["executable"] for row in manifest["files"]}
        for name, payload in contents.items():
            write_bytes_atomic(stage / name, payload, private=True)
            if expected_exec[name]:
                (stage / name).chmod(0o700)
        verified, _fingerprint = _inventory(stage, max_total_bytes, max_files)
        if not _owner_exec_supported():
            # Windows chmod does not represent POSIX owner execution bits.
            # Verify all file bytes and paths while reporting that limitation.
            for row in verified["files"]:
                row["executable"] = expected_exec.get(row["filename"], row["executable"])
        if verified != manifest:
            raise WorkspaceBackupError("restored workspace bytes differ from the authenticated manifest")
        _checked_absolute(target)
        if target.exists():
            raise WorkspaceBackupError("restore destination appeared while staging")
        os.rename(stage, target)
        installed = True
    finally:
        if not installed:
            shutil.rmtree(stage)
    return _summary(manifest, target)


def _preconditions(passphrase: str, offline: bool, max_bytes: int, max_files: int) -> None:
    if offline is not True:
        raise WorkspaceBackupError("offline confirmation is required; stop other ROW GUI, Web and CLI processes")
    if not isinstance(passphrase, str) or len(passphrase) < 12 or not passphrase.strip():
        raise WorkspaceBackupError("backup passphrase must contain at least 12 characters")
    if type(max_bytes) is not int or not 1 <= max_bytes <= MAX_TOTAL_BYTES or type(max_files) is not int or not 1 <= max_files <= MAX_FILES:
        raise WorkspaceBackupError("backup limits must be positive and at most 64 MiB / 10000 entries")


def _checked_absolute(path: Path) -> Path:
    absolute = Path(os.path.abspath(path.expanduser()))
    _require_no_linked_path_components(absolute)
    return absolute


def _cipher(passphrase: str, salt: bytes) -> Any:
    try:
        from cryptography.fernet import Fernet
        from cryptography.hazmat.primitives.kdf.scrypt import Scrypt

        key = Scrypt(salt=salt, length=32, n=2**15, r=8, p=3).derive(passphrase.encode("utf-8"))
        return Fernet(base64.urlsafe_b64encode(key))
    except Exception as exc:
        raise WorkspaceBackupError("encrypted workspace recovery requires the security extra (cryptography)") from exc


def _json_bytes(value: Any) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def _load_json(payload: bytes) -> Any:
    try:
        return json.loads(payload, object_pairs_hook=_unique_object)
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise WorkspaceBackupError("workspace backup contains invalid or ambiguous JSON") from exc


def _unique_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result = {}
    for key, value in pairs:
        if key in result:
            raise WorkspaceBackupError("duplicate workspace backup field")
        result[key] = value
    return result


def _decode(value: Any) -> bytes:
    try:
        if not isinstance(value, str):
            raise ValueError("base64 value must be text")
        return base64.b64decode(value.encode("ascii"), validate=True)
    except (ValueError, UnicodeError, binascii.Error) as exc:
        raise WorkspaceBackupError("workspace backup contains invalid base64") from exc


def _metadata(status: os.stat_result) -> tuple[int, ...]:
    return (status.st_dev, status.st_ino, status.st_mode, status.st_nlink, status.st_size, status.st_mtime_ns, status.st_ctime_ns)


def _linked(status: os.stat_result) -> bool:
    return stat.S_ISLNK(status.st_mode) or bool(getattr(status, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))


def _read_regular(path: Path, limit: int) -> tuple[bytes, tuple[int, ...]]:
    _checked_absolute(path)
    initial = path.lstat()
    if _linked(initial) or not stat.S_ISREG(initial.st_mode) or initial.st_nlink != 1:
        raise WorkspaceBackupError("workspace recovery refuses linked or special files")
    if initial.st_size > limit:
        raise WorkspaceBackupError("workspace backup exceeds its byte limit")
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0)
    descriptor = os.open(path, flags)
    with os.fdopen(descriptor, "rb") as source:
        opened = os.fstat(source.fileno())
        # CPython Windows lstat and fstat disagree on ctime (birth time versus
        # change time). Compare identities across APIs, and timestamps within
        # the same API below; preserve both snapshots for the later inventory.
        if _metadata(opened)[:-1] != _metadata(initial)[:-1]:
            raise WorkspaceBackupError("workspace file changed while opening")
        payload = source.read(limit + 1)
        if len(payload) > limit:
            raise WorkspaceBackupError("workspace backup exceeds its byte limit")
        if _metadata(os.fstat(source.fileno())) != _metadata(opened) or _metadata(path.lstat()) != _metadata(initial):
            raise WorkspaceBackupError("workspace file changed while reading")
    return payload, (*_metadata(initial), *_metadata(opened))


def _excluded(relative: str) -> bool:
    relative = unicodedata.normalize("NFC", relative).casefold()
    path = Path(relative)
    name = path.name
    if relative in {(Path(known).parent / f".{Path(known).name}.lock").as_posix() for known in KNOWN_ATOMIC_PATHS}:
        return True
    # A retained rollback copy can be the only verified predecessor after a
    # failed write and rollback; include its bytes as opaque recovery state.
    return any(path.parent == Path(known).parent and re.fullmatch(rf"\.{re.escape(Path(known).name)}\.[A-Za-z0-9_-]+\.tmp", name) for known in KNOWN_ATOMIC_PATHS)


def _offline_record(name: str, payload: bytes) -> None:
    if unicodedata.normalize("NFC", name).casefold() not in MANAGED_RECORDS:
        return
    record = _load_json(payload)
    if not isinstance(record, dict) or "pid" not in record or record["pid"] is not None or record.get("state") not in ("stopped", "dry-run") or (record.get("running") is not None and record.get("running") is not False):
        raise WorkspaceBackupError("managed runtime record is active or ambiguous; stop it and clear stale PID records before offline recovery")


def _inventory(root: Path, max_bytes: int, max_files: int) -> tuple[dict[str, Any], dict[str, Any]]:
    _checked_absolute(root)
    directories: list[str] = []
    files: list[dict[str, Any]] = []
    fingerprint: dict[str, Any] = {"": _metadata(root.lstat())}
    total = 0

    def visit(directory: Path) -> None:
        nonlocal total
        for path in sorted(directory.iterdir()):
            relative = path.relative_to(root).as_posix()
            status = path.lstat()
            if _linked(status):
                raise WorkspaceBackupError("ROW_HOME contains a linked or reparse path")
            _path_key(relative)
            if stat.S_ISDIR(status.st_mode):
                directories.append(relative)
                fingerprint[relative] = _metadata(status)
                if len(directories) + len(files) > max_files:
                    raise WorkspaceBackupError("workspace backup exceeds its entry limit")
                visit(path)
            elif stat.S_ISREG(status.st_mode):
                if status.st_nlink != 1:
                    raise WorkspaceBackupError("ROW_HOME contains a hard-linked file")
                if _excluded(relative):
                    continue
                if len(directories) + len(files) >= max_files:
                    raise WorkspaceBackupError("workspace backup exceeds its entry limit")
                payload, identity = _read_regular(path, max_bytes - total)
                _offline_record(relative, payload)
                digest = hashlib.sha256(payload).hexdigest()
                files.append({"filename": relative, "size": len(payload), "sha256": digest, "executable": bool(status.st_mode & stat.S_IXUSR), "bytes": base64.b64encode(payload).decode("ascii")})
                fingerprint[relative] = (identity, digest)
                total += len(payload)
            else:
                raise WorkspaceBackupError("ROW_HOME contains a special filesystem entry")

    visit(root)
    manifest = {"schema": SCHEMA, "version": 1, "directories": sorted(directories), "files": sorted(files, key=lambda row: row["filename"])}
    validated, _contents = _validate_manifest(manifest, max_bytes, max_files)
    return validated, fingerprint


def _path_key(name: Any) -> str:
    if not isinstance(name, str) or not name:
        raise WorkspaceBackupError("invalid workspace manifest filename")
    try:
        encoded = name.encode("utf-8")
    except UnicodeError as exc:
        raise WorkspaceBackupError("invalid workspace manifest filename encoding") from exc
    if len(encoded) > 1024 or len(name.split("/")) > 32:
        raise WorkspaceBackupError("workspace manifest path exceeds its length or depth limit")
    for component in name.split("/"):
        if component in {"", ".", ".."} or len(component.encode("utf-8")) > 255 or not re.fullmatch(r'[^\x00-\x1f\x7f\\:*?"<>|]+', component) or component.endswith((".", " ")) or component.split(".")[0].rstrip(" ").casefold() in _RESERVED_NAMES:
            raise WorkspaceBackupError("workspace manifest contains an unsafe or nonportable path")
    return unicodedata.normalize("NFC", name).casefold()


def _validate_manifest(raw: Any, max_bytes: int, max_files: int) -> tuple[dict[str, Any], dict[str, bytes]]:
    if not isinstance(raw, dict) or set(raw) != {"schema", "version", "directories", "files"} or raw["schema"] != SCHEMA or type(raw["version"]) is not int or raw["version"] != 1 or not isinstance(raw["directories"], list) or not isinstance(raw["files"], list):
        raise WorkspaceBackupError("unsupported workspace backup manifest")
    if len(raw["directories"]) + len(raw["files"]) > max_files:
        raise WorkspaceBackupError("workspace backup exceeds its entry limit")
    names: set[str] = set()
    directories: set[str] = set()
    contents: dict[str, bytes] = {}
    total = 0
    for name in raw["directories"]:
        key = _path_key(name)
        if key in names:
            raise WorkspaceBackupError("workspace manifest contains duplicate or case-colliding paths")
        names.add(key)
        directories.add(name)
    for row in raw["files"]:
        if not isinstance(row, dict) or set(row) != {"filename", "size", "sha256", "executable", "bytes"} or type(row["size"]) is not int or row["size"] < 0 or type(row["executable"]) is not bool or not isinstance(row["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", row["sha256"]):
            raise WorkspaceBackupError("invalid workspace file manifest")
        name = row["filename"]
        key = _path_key(name)
        if key in names or _excluded(name):
            raise WorkspaceBackupError("workspace manifest contains duplicate, case-colliding or transient paths")
        names.add(key)
        total += row["size"]
        if total > max_bytes:
            raise WorkspaceBackupError("workspace backup exceeds its byte limit")
        payload = _decode(row["bytes"])
        if len(payload) != row["size"] or hashlib.sha256(payload).hexdigest() != row["sha256"]:
            raise WorkspaceBackupError("workspace manifest bytes do not match their size or SHA256")
        _offline_record(name, payload)
        contents[name] = payload
    for name in (*directories, *contents):
        for parent in Path(name).parents:
            if parent.as_posix() != "." and parent.as_posix() not in directories:
                raise WorkspaceBackupError("workspace manifest has a missing or conflicting parent directory")
    canonical = {"schema": SCHEMA, "version": 1, "directories": sorted(directories), "files": sorted(raw["files"], key=lambda row: row["filename"])}
    return canonical, contents


def _summary(manifest: dict[str, Any], path: Path) -> dict[str, Any]:
    return {"schema": SCHEMA, "version": 1, "path": str(path), "file_count": len(manifest["files"]), "directory_count": len(manifest["directories"]), "total_bytes": sum(row["size"] for row in manifest["files"]), "offline_only": True, "owner_executable_bit_supported": _owner_exec_supported(), "windows_acl_verified": False}


def _owner_exec_supported() -> bool:
    return os.name == "posix"

from __future__ import annotations

import base64
import builtins
import hashlib
import json
import os
import stat
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from types import SimpleNamespace

import pytest

from remote_ops_workspace import workspace_backup as recovery
from remote_ops_workspace.state_lock import FileLockTimeoutError, exclusive_file_lock

PASSPHRASE = "synthetic recovery passphrase"


def test_known_managed_record_locks_are_excluded_and_unknown_plugin_locks_restored(tmp_path):
    source = tmp_path / "home"
    servers = source / "servers"
    servers.mkdir(parents=True)
    payload = json.dumps({"state": "stopped", "pid": None, "running": False})
    records = [source / "xserver-state.json", servers / "http-server-state.json"]
    for record in records:
        record.write_text(payload, encoding="utf-8")
        with exclusive_file_lock(record):
            pass
    unknown = servers / ".plugin.lock"
    unknown.write_bytes(b"persistent unknown plugin lock state")
    archive = tmp_path / "archive.json"
    recovery.create_workspace_backup(source, archive, PASSPHRASE, offline_confirmed=True)
    restored = tmp_path / "restored"
    recovery.restore_workspace_backup(archive, restored, PASSPHRASE, current_home=source, offline_confirmed=True)
    assert not (restored / ".xserver-state.json.lock").exists()
    assert not (restored / "servers/.http-server-state.json.lock").exists()
    assert (restored / "servers/.plugin.lock").read_bytes() == unknown.read_bytes()
    assert (restored / "xserver-state.json").read_bytes() == records[0].read_bytes()
    assert (restored / "servers/http-server-state.json").read_bytes() == records[1].read_bytes()


def test_existing_managed_record_lock_contention_refuses_backup_and_preserves_output(tmp_path):
    source = tmp_path / "home"
    source.mkdir()
    state = source / "xserver-state.json"
    state.write_text(json.dumps({"state": "stopped", "pid": None, "running": False}), encoding="utf-8")
    acquired, release = threading.Event(), threading.Event()

    def hold_record():
        with exclusive_file_lock(state):
            acquired.set()
            assert release.wait(5)

    archive = tmp_path / "archive.json"
    prior = b"previous backup must survive lock contention"
    archive.write_bytes(prior)
    with ThreadPoolExecutor(max_workers=1) as workers:
        owner = workers.submit(hold_record)
        try:
            assert acquired.wait(5)
            with pytest.raises(FileLockTimeoutError):
                recovery.create_workspace_backup(source, archive, PASSPHRASE, offline_confirmed=True, lock_timeout_seconds=0.05)
            assert archive.read_bytes() == prior
        finally:
            release.set()
        owner.result(timeout=5)


def test_backup_missing_managed_records_does_not_create_servers_directory(tmp_path):
    source = tmp_path / "home"
    source.mkdir()
    recovery.create_workspace_backup(source, tmp_path / "archive.json", PASSPHRASE, offline_confirmed=True)
    assert not (source / "servers").exists()
    assert not (source / ".xserver-state.json.lock").exists()


def _file(name="unknown.bin", payload=b"opaque plugin state", **changes):
    return {"filename": name, "size": len(payload), "sha256": hashlib.sha256(payload).hexdigest(), "executable": False, "bytes": base64.b64encode(payload).decode("ascii"), **changes}


def _manifest(files=None, directories=None, **changes):
    return {"schema": recovery.SCHEMA, "version": 1, "files": [_file()] if files is None else files, "directories": [] if directories is None else directories, **changes}


def _write_archive(path, manifest, *, token=None, crypto_salt=b"s" * 16, **changes):
    encrypted = recovery._cipher(PASSPHRASE, crypto_salt).encrypt(recovery._json_bytes(manifest)).decode("ascii") if token is None else token
    path.write_text(json.dumps({"schema": recovery.SCHEMA, "version": 1, "salt": base64.b64encode(crypto_salt).decode("ascii"), "kdf": recovery.KDF, "token": encrypted, **changes}), encoding="utf-8")
    return path


@pytest.fixture
def home(tmp_path):
    source = tmp_path / "original"
    source.mkdir()
    (source / "profiles.json").write_bytes(b'{"version":1,"profiles":[]}')
    (source / "vault.json").write_bytes(b"opaque already encrypted vault")
    (source / "plugins" / "unknown" / "empty").mkdir(parents=True)
    (source / "plugins" / "unknown" / "state.bin").write_bytes(bytes(range(256)))
    (source / "plugins" / ".profiles.json.unknown.tmp").write_bytes(b"real unknown plugin state")
    (source / "unknown.tmp").write_bytes(b"not a known transaction temporary")
    (source / ".profiles.json.transaction.tmp").write_bytes(b"known staging")
    (source / ".vault.json.rollback.predecessor.tmp").write_bytes(b"known recovery")
    (source / ".plugin.lock").write_bytes(b"stable lock")
    return source


def test_real_full_home_roundtrip_preserves_unknown_bytes_and_empty_directories(home, tmp_path):
    output = tmp_path / "recovery.json"
    report = recovery.create_workspace_backup(home, output, PASSPHRASE, offline_confirmed=True)
    assert report["file_count"] == 7 and report["directory_count"] == 3
    assert report["offline_only"] is True
    encrypted = output.read_bytes()
    assert b"opaque" not in encrypted and b"state.bin" not in encrypted and PASSPHRASE.encode() not in encrypted
    outer = json.loads(encrypted)
    assert outer["kdf"] == {"name": "scrypt", "n": 32768, "r": 8, "p": 3, "length": 32}
    assert len(base64.b64decode(outer["salt"])) == 16
    target = tmp_path / "restored"
    restored = recovery.restore_workspace_backup(output, target, PASSPHRASE, current_home=home, offline_confirmed=True)
    assert restored["total_bytes"] == report["total_bytes"]
    for relative in ("profiles.json", "vault.json", "plugins/unknown/state.bin", "plugins/.profiles.json.unknown.tmp", "unknown.tmp", ".plugin.lock", ".vault.json.rollback.predecessor.tmp"):
        assert (target / relative).read_bytes() == (home / relative).read_bytes()
    assert (target / "plugins/unknown/empty").is_dir()
    assert not (target / ".profiles.json.lock").exists()
    assert not (target / ".profiles.json.transaction.tmp").exists()
    assert (home / ".profiles.json.transaction.tmp").read_bytes() == b"known staging"


def test_empty_home_and_explicit_executable_archive_roundtrip(tmp_path, monkeypatch):
    home = tmp_path / "home"
    home.mkdir()
    output = tmp_path / "empty.json"
    result = recovery.create_workspace_backup(home, output, PASSPHRASE, offline_confirmed=True)
    assert result["file_count"] == 0
    recovery.restore_workspace_backup(output, tmp_path / "empty", PASSPHRASE, current_home=home, offline_confirmed=True)
    monkeypatch.setattr(recovery, "_owner_exec_supported", lambda: True)
    recovery.restore_workspace_backup(output, tmp_path / "empty-posix-metadata", PASSPHRASE, current_home=home, offline_confirmed=True)
    _write_archive(output, _manifest([_file("plugin.sh", b"#!/bin/sh\nexit 0\n", executable=True)]))
    monkeypatch.setattr(recovery, "_owner_exec_supported", lambda: os.name == "posix")
    recovery.restore_workspace_backup(output, tmp_path / "executable", PASSPHRASE, current_home=home, offline_confirmed=True)
    if os.name == "posix":
        assert stat.S_IMODE((tmp_path / "executable/plugin.sh").stat().st_mode) == 0o700
    # Exercise byte validation on a platform without POSIX executable metadata.
    monkeypatch.setattr(recovery, "_owner_exec_supported", lambda: False)
    recovery.restore_workspace_backup(output, tmp_path / "portable", PASSPHRASE, current_home=home, offline_confirmed=True)


@pytest.mark.parametrize("options", [
    {"offline_confirmed": False}, {"passphrase": None}, {"passphrase": "short"}, {"passphrase": " " * 12},
    {"max_total_bytes": True}, {"max_total_bytes": 0}, {"max_total_bytes": recovery.MAX_TOTAL_BYTES + 1},
    {"max_files": True}, {"max_files": 0}, {"max_files": recovery.MAX_FILES + 1},
])
def test_backup_requires_offline_valid_passphrase_and_bounded_limits(home, tmp_path, options):
    arguments = {"offline_confirmed": True, **options}
    passphrase = arguments.pop("passphrase", PASSPHRASE)
    with pytest.raises(recovery.WorkspaceBackupError):
        recovery.create_workspace_backup(home, tmp_path / "backup.json", passphrase, **arguments)
    assert not (tmp_path / "backup.json").exists()


def test_backup_requires_existing_home_and_external_output(tmp_path):
    with pytest.raises(recovery.WorkspaceBackupError, match="existing"):
        recovery.create_workspace_backup(tmp_path / "missing", tmp_path / "backup", PASSPHRASE, offline_confirmed=True)
    with pytest.raises(recovery.WorkspaceBackupError, match="outside"):
        recovery.create_workspace_backup(tmp_path, tmp_path / "backup", PASSPHRASE, offline_confirmed=True)


@pytest.mark.parametrize("kind", ["same", "nested", "existing", "missing-parent"])
def test_restore_requires_new_direct_sibling(home, tmp_path, kind):
    target = {"same": home, "nested": home / "nested", "existing": tmp_path / "existing", "missing-parent": tmp_path / "absent" / "restore"}[kind]
    if kind == "existing":
        target.mkdir()
    original = tmp_path / "absent" / "home" if kind == "missing-parent" else home
    with pytest.raises(recovery.WorkspaceBackupError):
        recovery.restore_workspace_backup(tmp_path / "unused", target, PASSPHRASE, current_home=original, offline_confirmed=True)
    assert (home / "vault.json").read_bytes() == b"opaque already encrypted vault"


def test_known_writer_lock_timeout_is_real_and_does_not_create_backup(home, tmp_path):
    held = threading.Event()
    release = threading.Event()

    def writer():
        with exclusive_file_lock(home / "profiles.json"):
            held.set()
            assert release.wait(5)

    worker = threading.Thread(target=writer)
    worker.start()
    assert held.wait(5)
    try:
        with pytest.raises(FileLockTimeoutError):
            recovery.create_workspace_backup(home, tmp_path / "backup.json", PASSPHRASE, offline_confirmed=True, lock_timeout_seconds=0.05)
    finally:
        release.set()
        worker.join(5)
    assert not worker.is_alive() and not (tmp_path / "backup.json").exists()


def test_source_drift_refuses_encrypted_commit_and_preserves_previous_backup(home, tmp_path, monkeypatch):
    output = tmp_path / "backup.json"
    output.write_bytes(b"previous encrypted backup")
    inventory = recovery._inventory
    calls = 0

    def changing_inventory(root, *limits):
        nonlocal calls
        calls += 1
        if calls == 2:
            (root / "new-plugin.bin").write_bytes(b"concurrent unknown writer")
        return inventory(root, *limits)

    monkeypatch.setattr(recovery, "_inventory", changing_inventory)
    with pytest.raises(recovery.WorkspaceBackupError, match="changed during"):
        recovery.create_workspace_backup(home, output, PASSPHRASE, offline_confirmed=True)
    assert output.read_bytes() == b"previous encrypted backup"


@pytest.mark.parametrize("record", [
    {}, [], {"state": "stopped"}, {"state": "stopped", "pid": ""}, {"state": "stopped", "pid": 0},
    {"state": "stopped", "pid": 123}, {"state": "started", "pid": None},
    {"state": "unknown", "pid": None}, {"state": "stopped", "pid": None, "running": True},
    {"state": "stopped", "pid": None, "running": []}, {"state": [], "pid": None},
])
def test_managed_runtime_record_fails_closed_on_active_or_ambiguous_state(record):
    with pytest.raises(recovery.WorkspaceBackupError, match="active or ambiguous"):
        recovery._offline_record("xserver-state.json", json.dumps(record).encode())


def test_known_stopped_record_is_preserved_and_malformed_record_refused(home, tmp_path):
    record = b'{"state":"stopped","pid":null,"running":false}'
    (home / "xserver-state.json").write_bytes(record)
    backup = tmp_path / "backup.json"
    recovery.create_workspace_backup(home, backup, PASSPHRASE, offline_confirmed=True)
    target = tmp_path / "restored"
    recovery.restore_workspace_backup(backup, target, PASSPHRASE, current_home=home, offline_confirmed=True)
    assert (target / "xserver-state.json").read_bytes() == record
    (home / "xserver-state.json").write_bytes(b"not JSON")
    with pytest.raises(recovery.WorkspaceBackupError, match="JSON"):
        recovery.create_workspace_backup(home, backup, PASSPHRASE, offline_confirmed=True)
    recovery._offline_record("servers/ftp-server-state.json", b'{"state":"dry-run","pid":null}')


@pytest.mark.parametrize("mutation", ["wrong-passphrase", "token-tamper", "non-ascii-token"])
def test_actual_encryption_rejects_wrong_passphrase_or_tamper(home, tmp_path, mutation):
    output = tmp_path / "backup.json"
    recovery.create_workspace_backup(home, output, PASSPHRASE, offline_confirmed=True)
    passphrase = "different wrong passphrase" if mutation == "wrong-passphrase" else PASSPHRASE
    if mutation != "wrong-passphrase":
        outer = json.loads(output.read_text())
        outer["token"] = "not a Fernet token" if mutation == "token-tamper" else "not ASCII é"
        output.write_text(json.dumps(outer))
    target = tmp_path / "restore"
    with pytest.raises(recovery.WorkspaceBackupError, match="passphrase or corrupted"):
        recovery.restore_workspace_backup(output, target, passphrase, current_home=home, offline_confirmed=True)
    assert not target.exists()


@pytest.mark.parametrize("changes", [
    {"schema": "foreign"}, {"version": 2}, {"version": True}, {"extra": 1}, {"kdf": {}},
    {"kdf": {**recovery.KDF, "n": 32768.0}}, {"salt": "!!"}, {"salt": 12},
    {"salt": base64.b64encode(b"short").decode()}, {"token": 12},
])
def test_envelope_exact_schema_kdf_salt_and_token_required(home, tmp_path, changes):
    output = _write_archive(tmp_path / "backup.json", _manifest(), **changes)
    with pytest.raises(recovery.WorkspaceBackupError):
        recovery.restore_workspace_backup(output, tmp_path / "restore", PASSPHRASE, current_home=home, offline_confirmed=True)
    assert not (tmp_path / "restore").exists()


def test_outer_type_and_json_validation_before_restore(home, tmp_path):
    for payload in (b"[]", b"{", b'{"a":1,"a":2}', b"\xff", b"[" * 2000):
        output = tmp_path / "bad.json"
        output.write_bytes(payload)
        with pytest.raises(recovery.WorkspaceBackupError):
            recovery.restore_workspace_backup(output, tmp_path / "restore", PASSPHRASE, current_home=home, offline_confirmed=True)


@pytest.mark.parametrize("manifest", [
    [], {}, _manifest(schema="foreign"), _manifest(version=True), _manifest(version=2),
    _manifest(extra="field"), _manifest(files={}), _manifest(directories={}),
    _manifest(files=[[]]), _manifest(files=[{"filename": "incomplete"}]),
    _manifest(files=[_file(size=True)]), _manifest(files=[_file(size=-1)]),
    _manifest(files=[_file(executable=1)]), _manifest(files=[_file(sha256=123)]),
    _manifest(files=[_file(sha256="not a hash")]), _manifest(files=[_file(bytes="!!")]),
    _manifest(files=[_file(bytes="é")]), _manifest(files=[_file(bytes=1)]),
    _manifest(files=[_file(size=0)]), _manifest(files=[_file(sha256="0" * 64)]),
    _manifest(files=[_file("../outside")]), _manifest(files=[_file("C:/outside")]),
    _manifest(files=[_file("/absolute")]), _manifest(files=[_file("nested\\outside")]),
    _manifest(files=[_file("a", b"one"), _file("A", b"two")]),
    _manifest(files=[_file("plugin/state")]), _manifest(files=[_file("plugin")], directories=["plugin"]),
    _manifest(files=[], directories=["a", "A"]), _manifest(files=[], directories=["a/b"]),
    _manifest(files=[_file(".profiles.json.lock")]), _manifest(files=[_file(".vault.json.writer.tmp")]),
    _manifest(files=[_file("xserver-state.json", b'{"state":"started","pid":123}')]),
])
def test_complete_manifest_prevalidation_rejects_bad_paths_collisions_and_bytes(manifest):
    with pytest.raises(recovery.WorkspaceBackupError):
        recovery._validate_manifest(manifest, recovery.MAX_TOTAL_BYTES, recovery.MAX_FILES)


@pytest.mark.parametrize("name", [
    None, "", "a" * 1025, "/".join(["a"] * 33), "a" * 256, "\ud800",
    "..", "a/./b", "a//b", "a\n", "a.", "a ", "NUL.txt", "COM1", "LPT9.txt",
    "COM¹", "LPT².txt", "CONIN$", "CONOUT$", "CON .txt", "COM1 .txt", "LPT¹ .txt", "a:stream", "a?b", "a<b", "a|b", 'a"b',
])
def test_manifest_portable_path_validation_includes_all_windows_devices(name):
    with pytest.raises(recovery.WorkspaceBackupError):
        recovery._path_key(name)


def test_authenticated_bad_inner_manifest_creates_no_restore_directory(home, tmp_path):
    backup = _write_archive(tmp_path / "backup.json", _manifest([_file("../escape")]))
    with pytest.raises(recovery.WorkspaceBackupError):
        recovery.restore_workspace_backup(backup, tmp_path / "restored", PASSPHRASE, current_home=home, offline_confirmed=True)
    assert not (tmp_path / "restored").exists() and not list(tmp_path.glob(".restored.row-restore-*"))


@pytest.mark.parametrize("name", ["XSERVER-STATE.JSON", "SERVERS/HTTP-SERVER-STATE.JSON"])
def test_managed_state_case_aliases_are_refused_in_source_and_authenticated_restore(home, tmp_path, name):
    payload = b'{"state":"started","pid":424242,"running":true}'
    path = home / name
    path.parent.mkdir(exist_ok=True)
    path.write_bytes(payload)
    with pytest.raises(recovery.WorkspaceBackupError, match="active or ambiguous"):
        recovery.create_workspace_backup(home, tmp_path / "backup", PASSPHRASE, offline_confirmed=True)
    directories = ["SERVERS"] if name.startswith("SERVERS/") else []
    archive = _write_archive(tmp_path / "forged.json", _manifest([_file(name, payload)], directories=directories))
    with pytest.raises(recovery.WorkspaceBackupError, match="active or ambiguous"):
        recovery.restore_workspace_backup(archive, tmp_path / "restore", PASSPHRASE, current_home=home, offline_confirmed=True)
    assert not (tmp_path / "restore").exists()
    assert recovery._excluded(".PROFILES.JSON.LOCK") is True
    assert recovery._excluded(".PROFILES.JSON.TRANSACTION.TMP") is True
    assert recovery._excluded(".PROFILES.JSON.ROLLBACK.ORIGINAL.TMP") is False


def test_bounds_apply_to_manifest_total_files_bytes_and_envelope_before_json(home, tmp_path):
    with pytest.raises(recovery.WorkspaceBackupError, match="entry"):
        recovery._validate_manifest(_manifest([_file("one"), _file("two")]), 1000, 1)
    with pytest.raises(recovery.WorkspaceBackupError, match="byte"):
        recovery._validate_manifest(_manifest(), 1, 100)
    with pytest.raises(recovery.WorkspaceBackupError, match="entry"):
        recovery._inventory(home, recovery.MAX_TOTAL_BYTES, 1)
    empty = tmp_path / "directories"
    (empty / "one" / "two").mkdir(parents=True)
    with pytest.raises(recovery.WorkspaceBackupError, match="entry"):
        recovery._inventory(empty, 1000, 1)
    oversized = tmp_path / "oversized.json"
    with oversized.open("wb") as output:
        output.truncate(1 * 2 + 1 * 4096 + 4096 + 1)
    with pytest.raises(recovery.WorkspaceBackupError, match="byte"):
        recovery.restore_workspace_backup(oversized, tmp_path / "restore", PASSPHRASE, current_home=home, offline_confirmed=True, max_total_bytes=1, max_files=1)
    with pytest.raises(recovery.WorkspaceBackupError, match="byte"):
        recovery.create_workspace_backup(home, tmp_path / "bounded", PASSPHRASE, offline_confirmed=True, max_total_bytes=1)


def test_crypto_dependency_failure_is_wrapped_without_writing_plaintext(home, tmp_path, monkeypatch):
    original = builtins.__import__

    def unavailable(name, *args, **kwargs):
        if name.startswith("cryptography"):
            raise ImportError("synthetic optional dependency unavailable")
        return original(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", unavailable)
    with pytest.raises(recovery.WorkspaceBackupError, match="cryptography"):
        recovery.create_workspace_backup(home, tmp_path / "backup", PASSPHRASE, offline_confirmed=True)
    assert not (tmp_path / "backup").exists()


def test_hardlinked_user_file_is_refused(home, tmp_path):
    os.link(home / "vault.json", tmp_path / "outside-alias")
    with pytest.raises(recovery.WorkspaceBackupError, match="hard-linked"):
        recovery.create_workspace_backup(home, tmp_path / "backup", PASSPHRASE, offline_confirmed=True)
    with pytest.raises(recovery.WorkspaceBackupError, match="linked or special"):
        recovery._read_regular(home / "vault.json", 1000)


def test_reparse_and_special_entries_are_refused_before_capture(home, tmp_path, monkeypatch):
    victim = home / "vault.json"
    original = Path.lstat

    def fake_reparse(path, *args, **kwargs):
        if path == victim:
            return SimpleNamespace(st_mode=stat.S_IFREG | 0o600, st_file_attributes=0x400)
        return original(path, *args, **kwargs)

    monkeypatch.setattr(Path, "lstat", fake_reparse)
    with pytest.raises(recovery.WorkspaceBackupError, match="reparse"):
        recovery._inventory(home, 1000, 100)
    assert recovery._linked(SimpleNamespace(st_mode=stat.S_IFLNK)) is True
    monkeypatch.setattr(Path, "lstat", lambda path, *args, **kwargs: SimpleNamespace(st_mode=stat.S_IFIFO) if path == victim else original(path, *args, **kwargs))
    with pytest.raises(recovery.WorkspaceBackupError, match="special"):
        recovery._inventory(home, 1000, 100)
    with pytest.raises(recovery.WorkspaceBackupError, match="linked or special"):
        recovery._read_regular(victim, 1000)


def test_real_symlink_is_rejected_by_existing_private_path_boundary(home, tmp_path):
    link = home / "external-link"
    try:
        link.symlink_to(tmp_path / "external")
    except OSError:
        pytest.skip("host does not grant symlink creation")
    with pytest.raises(recovery.WorkspaceBackupError, match="linked"):
        recovery._inventory(home, 1000, 100)
    with pytest.raises(OSError, match="linked"):
        recovery._checked_absolute(link)


def test_file_changed_between_lstat_and_open_is_detected(tmp_path, monkeypatch):
    victim = tmp_path / "state"
    victim.write_bytes(b"old")
    original = os.open

    def changed_open(path, flags, *args, **kwargs):
        if Path(path) == victim:
            victim.write_bytes(b"changed source bytes")
        return original(path, flags, *args, **kwargs)

    monkeypatch.setattr(os, "open", changed_open)
    with pytest.raises(recovery.WorkspaceBackupError, match="changed while opening"):
        recovery._read_regular(victim, 1000)


@pytest.mark.parametrize("kind", ["growing", "same-size", "named-path-swapped"])
def test_file_changes_during_opened_read_are_detected(tmp_path, monkeypatch, kind):
    victim = tmp_path / "state"
    victim.write_bytes(b"old")
    original = os.fdopen

    class ChangingReader:
        def __init__(self, descriptor, mode):
            self.stream = original(descriptor, mode)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def fileno(self):
            return self.stream.fileno()

        def read(self, size):
            payload = self.stream.read(size)
            if kind == "growing":
                with victim.open("ab") as output:
                    output.write(b"new bytes")
                self.stream.seek(0)
                return self.stream.read(size)
            if kind == "named-path-swapped":
                replacement = victim.with_suffix(".replacement")
                replacement.write_bytes(b"new")
                os.replace(replacement, victim)
            else:
                victim.write_bytes(b"new")
            return payload

    monkeypatch.setattr(os, "fdopen", ChangingReader)
    expected = (recovery.WorkspaceBackupError, OSError) if kind == "named-path-swapped" and os.name == "nt" else recovery.WorkspaceBackupError
    match = None if expected is not recovery.WorkspaceBackupError else "byte limit" if kind == "growing" else "changed while reading"
    with pytest.raises(expected, match=match):
        recovery._read_regular(victim, 3 if kind == "growing" else 1000)


@pytest.mark.parametrize("before,after", [
    (b"unchanged" * 10000 + b"old", b"unchanged" * 10000 + b"new"),
    (b"unchanged" * 10000 + b"old", b"unchanged" * 10000),
    (b"unchanged" * 10000 + b"old", b"unchanged" * 10000 + b"old-extra"),
    (b"", b"new"),
], ids=["same-size", "truncated", "extended", "empty-became-nonempty"])
def test_changed_bytes_are_rejected_when_windows_metadata_observations_are_unchanged(
    tmp_path, monkeypatch, before, after,
):
    victim = tmp_path / "state"
    victim.write_bytes(before)
    initial = victim.lstat()
    original_fdopen, original_fstat, original_lstat = os.fdopen, os.fstat, Path.lstat
    snapshots = {}

    class ChangingReader:
        def __init__(self, descriptor, mode):
            self.stream = original_fdopen(descriptor, mode)
            snapshots[descriptor] = original_fstat(descriptor)

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return self.stream.__exit__(*args)

        def fileno(self):
            return self.stream.fileno()

        def read(self, size):
            payload = self.stream.read(size)
            victim.write_bytes(after)
            return payload

    # Model Windows timestamp granularity/deferred updates across an open read
    # handle. The bytes really change; both metadata APIs retain their own
    # original snapshots, including their platform-specific ctime semantics.
    monkeypatch.setattr(os, "fdopen", ChangingReader)
    monkeypatch.setattr(os, "fstat", lambda descriptor: snapshots.get(descriptor) or original_fstat(descriptor))
    monkeypatch.setattr(Path, "lstat", lambda path, *args, **kwargs: initial if path == victim else original_lstat(path, *args, **kwargs))
    with pytest.raises(recovery.WorkspaceBackupError, match="changed while reading"):
        recovery._read_regular(victim, 200000)
    assert victim.read_bytes() == after


def test_metadata_change_after_content_reinspection_still_refuses_read(tmp_path, monkeypatch):
    victim = tmp_path / "state"
    payload = b"unchanged file bytes"
    victim.write_bytes(payload)
    initial = victim.lstat()
    original_read = os.read

    def changed_metadata(descriptor, size):
        block = original_read(descriptor, size)
        if not block:
            # Explicitly advance the real timestamp after the second content
            # pass; identical bytes must not discard the metadata guard.
            os.utime(victim, ns=(initial.st_atime_ns, initial.st_mtime_ns + 2_000_000_000))
        return block

    monkeypatch.setattr(os, "read", changed_metadata)
    with pytest.raises(recovery.WorkspaceBackupError, match="changed while reading"):
        recovery._read_regular(victim, 1000)
    assert victim.read_bytes() == payload
    assert victim.lstat().st_mtime_ns != initial.st_mtime_ns


@pytest.mark.parametrize("payload", [b"", b"stable bytes" * 10000], ids=["empty", "multiple-partial-reads"])
def test_content_reinspection_accepts_stable_empty_and_partial_os_reads(tmp_path, monkeypatch, payload):
    victim = tmp_path / "state"
    victim.write_bytes(payload)
    original_read = os.read
    requests = []

    def partial_read(descriptor, size):
        requests.append(size)
        return original_read(descriptor, min(size, 4093))

    monkeypatch.setattr(os, "read", partial_read)
    observed, _identity = recovery._read_regular(victim, len(payload))
    assert observed == payload
    assert all(1 <= size <= 64 * 1024 for size in requests)
    assert len(requests) > 2 if payload else requests == [1]


@pytest.mark.parametrize("kind", ["write-denied", "chmod-denied", "rename-denied", "bytes-corrupt", "destination-appeared"])
def test_restore_io_failure_preserves_original_and_cleans_private_stage(home, tmp_path, monkeypatch, kind):
    backup = _write_archive(tmp_path / "backup.json", _manifest())
    target = tmp_path / "restored"
    writer = recovery.write_bytes_atomic
    inventory = recovery._inventory
    directory = recovery.ensure_private_dir_required

    def write(path, payload, **kwargs):
        if kind == "write-denied":
            raise PermissionError("synthetic restore write denied")
        writer(path, payload + b"corrupted" if kind == "bytes-corrupt" else payload, **kwargs)

    def ensure(path):
        if kind == "chmod-denied":
            raise PermissionError("synthetic restore permission denied")
        directory(path)

    def inspect(root, *limits):
        result = inventory(root, *limits)
        if kind == "destination-appeared":
            target.mkdir()
        return result

    monkeypatch.setattr(recovery, "write_bytes_atomic", write)
    monkeypatch.setattr(recovery, "ensure_private_dir_required", ensure)
    monkeypatch.setattr(recovery, "_inventory", inspect)
    if kind == "rename-denied":
        monkeypatch.setattr(os, "rename", lambda *_args: (_ for _ in ()).throw(PermissionError("synthetic rename denied")))
    with pytest.raises((OSError, recovery.WorkspaceBackupError)):
        recovery.restore_workspace_backup(backup, target, PASSPHRASE, current_home=home, offline_confirmed=True)
    assert (home / "vault.json").read_bytes() == b"opaque already encrypted vault"
    assert not list(tmp_path.glob(".restored.row-restore-*"))
    assert target.exists() is (kind == "destination-appeared")

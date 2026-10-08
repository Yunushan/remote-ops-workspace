"""Behavioral staging boundaries; portable temporary files and explicit mock metadata."""
import hashlib
import json
import stat
from contextlib import contextmanager
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from remote_ops_workspace import update_staging as staging

MANIFEST = b"synthetic manifest"
ASSET = b"synthetic asset"
DIGEST = hashlib.sha256(MANIFEST).hexdigest()
ASSET_DIGEST = hashlib.sha256(ASSET).hexdigest()


def _binding():
    return staging.AssetSetBinding(
        DIGEST, (staging.StageBinding(DIGEST, "asset.bin", ASSET_DIGEST, len(ASSET)),)
    )


def _transaction(tmp_path, monkeypatch):
    root = tmp_path / "stage"
    root.mkdir(mode=0o700)
    leases = []

    @contextmanager
    def lease(path):
        assert path == root / staging.JOURNAL
        leases.append("enter")
        try:
            yield
        finally:
            leases.append("exit")

    operation = staging.AssetSetTransaction(root, _binding(), exclusive_lease=lease)
    # Root qualification is tested independently below. These cases concern
    # staging byte/identity behavior and make no Windows ACL qualification claim.
    monkeypatch.setattr(operation, "_root", Mock())
    return operation, leases


def _os_facade(monkeypatch, **changes):
    value = SimpleNamespace(**vars(staging.os))
    vars(value).update(changes)
    monkeypatch.setattr(staging, "os", value)
    return value


def _status(value, **changes):
    fields = ("st_dev", "st_ino", "st_mode", "st_size", "st_nlink", "st_mtime_ns", "st_ctime_ns")
    result = {field: getattr(value, field) for field in fields}
    result.update(st_uid=getattr(value, "st_uid", 0), st_file_attributes=0)
    result.update(changes)
    return SimpleNamespace(**result)


def _files(root):
    return {path.name: path.read_bytes() for path in root.iterdir()}


@pytest.mark.parametrize("size", [-1, True, staging.MAX_ARTIFACT_BYTES + 1])
def test_binding_refuses_non_integer_negative_or_oversize_artifact(size):
    with pytest.raises(staging.StagingError, match="^invalid-binding$"):
        staging.StageBinding(DIGEST, "asset.bin", ASSET_DIGEST, size)


@pytest.mark.parametrize("defect", ["digest-type", "digest-text", "list", "empty", "too-many"])
def test_asset_set_refuses_invalid_manifest_or_unbounded_shape(defect):
    artifact = _binding().artifacts[0]
    digest, artifacts = DIGEST, (artifact,)
    if defect == "digest-type":
        digest = None
    elif defect == "digest-text":
        digest = "not-a-digest"
    elif defect == "list":
        artifacts = [artifact]
    elif defect == "empty":
        artifacts = ()
    else:
        artifacts = (artifact,) * (staging.MAX_ASSETS + 1)
    with pytest.raises(staging.StagingError, match="^invalid-binding$"):
        staging.AssetSetBinding(digest, artifacts)


@pytest.mark.parametrize("defect", ["foreign-object", "different-manifest", "zero-bytes"])
def test_asset_set_refuses_unbound_or_empty_member(defect):
    if defect == "foreign-object":
        artifact = object()
    else:
        artifact = staging.StageBinding(
            "b" * 64 if defect == "different-manifest" else DIGEST,
            "asset.bin", ASSET_DIGEST, 0 if defect == "zero-bytes" else len(ASSET),
        )
    with pytest.raises(staging.StagingError, match="^invalid-binding$"):
        staging.AssetSetBinding(DIGEST, (artifact,))


def test_asset_set_refuses_case_alias_and_enforces_aggregate_limit(monkeypatch):
    artifact = _binding().artifacts[0]
    alias = staging.StageBinding(DIGEST, "ASSET.bin", ASSET_DIGEST, len(ASSET))
    with pytest.raises(staging.StagingError, match="^invalid-binding$"):
        staging.AssetSetBinding(DIGEST, (artifact, alias))
    # A lower explicit policy ceiling exercises the aggregate constraint without
    # allocating huge payloads or constructing invalid individual members.
    monkeypatch.setattr(staging, "MAX_ASSET_SET_BYTES", len(ASSET))
    assert staging.AssetSetBinding(DIGEST, (artifact,)).artifacts == (artifact,)
    other = staging.StageBinding(DIGEST, "other.bin", ASSET_DIGEST, len(ASSET))
    with pytest.raises(staging.StagingError, match="^invalid-binding$"):
        staging.AssetSetBinding(DIGEST, (artifact, other))


@pytest.mark.parametrize("defect", ["binding", "lease", "checkpoint"])
def test_transaction_refuses_invalid_boundary_before_path_coercion(defect):
    accesses = []

    class UnreadPath:
        def __fspath__(self):
            accesses.append(True)
            raise AssertionError("invalid request touched root")

    root = UnreadPath()
    options = {"exclusive_lease": lambda _path: None, "checkpoint": None}
    binding = _binding()
    if defect == "binding":
        binding = object()
    elif defect == "lease":
        options["exclusive_lease"] = None
    else:
        options["checkpoint"] = 3
    with pytest.raises(staging.StagingError, match="^invalid-binding$"):
        staging.AssetSetTransaction(root, binding, **options)
    assert accesses == []


def test_windows_root_requires_explicit_private_guard_before_path_read(monkeypatch):
    operation = staging._StageFiles()
    operation.root = SimpleNamespace(parents=(), lstat=Mock())
    operation.private_guard = None
    _os_facade(monkeypatch, name="nt")
    with pytest.raises(staging.StagingError, match="^private-staging-platform-unqualified$"):
        operation._root()
    operation.root.lstat.assert_not_called()


def test_windows_root_verifies_guard_before_every_ordinary_ancestor(monkeypatch):
    events = []
    observed = SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_file_attributes=0)
    parent = SimpleNamespace(lstat=lambda: events.append("parent") or observed)
    operation = staging._StageFiles()
    operation.root = SimpleNamespace(parents=(parent,), lstat=lambda: events.append("root") or observed)
    operation.private_guard = SimpleNamespace(verify=lambda: events.append("guard"))
    _os_facade(monkeypatch, name="nt")
    operation._root()
    assert events == ["guard", "parent", "root", "root"]


@pytest.mark.parametrize("defect", ["symlink", "reparse", "regular-file"])
def test_root_refuses_unsafe_ancestor_before_child_metadata(monkeypatch, defect):
    mode = stat.S_IFLNK if defect == "symlink" else stat.S_IFREG if defect == "regular-file" else stat.S_IFDIR
    observed = SimpleNamespace(st_mode=mode | 0o700, st_file_attributes=0x400 if defect == "reparse" else 0)
    operation = staging._StageFiles()
    operation.root = SimpleNamespace(parents=(SimpleNamespace(lstat=lambda: observed),), lstat=Mock())
    operation.private_guard = None
    _os_facade(monkeypatch, name="posix", getuid=lambda: 7)
    with pytest.raises(staging.StagingError, match="^unsafe-root$"):
        operation._root()
    operation.root.lstat.assert_not_called()


@pytest.mark.parametrize("defect", ["permissions", "owner"])
def test_posix_root_requires_private_mode_and_current_owner(monkeypatch, defect):
    observed = SimpleNamespace(st_mode=stat.S_IFDIR | 0o700, st_file_attributes=0, st_uid=7)
    operation = staging._StageFiles()
    operation.root = SimpleNamespace(parents=(), lstat=lambda: observed)
    operation.private_guard = None
    _os_facade(monkeypatch, name="posix", getuid=lambda: 7)
    operation._root()
    if defect == "permissions":
        observed.st_mode = stat.S_IFDIR | 0o710
    else:
        observed.st_uid = 8
    with pytest.raises(staging.StagingError, match="^private-root-required$"):
        operation._root()


def test_absent_private_boundary_keeps_file_contexts_neutral(monkeypatch):
    operation = staging._StageFiles()
    operation.private_guard = None
    monkeypatch.setattr(operation, "_root", Mock())
    with operation._private_file(19, "synthetic-file") as writer:
        assert writer is None
    with operation._named_file("synthetic-file") as named:
        assert named is None
    with operation._verified_files():
        operation._root.assert_called_once_with()
    assert operation._root.call_count == 2


@pytest.mark.parametrize("defect", ["type", "chunk-size", "chunk-count"])
def test_atomic_refuses_unbounded_chunks_keeps_prefix_and_closes_descriptor(tmp_path, monkeypatch, defect):
    operation, _leases = _transaction(tmp_path, monkeypatch)
    real_open, real_fstat = staging.os.open, staging.os.fstat
    descriptors = []

    def opened(*args, **kwargs):
        descriptor = real_open(*args, **kwargs)
        descriptors.append(descriptor)
        return descriptor

    _os_facade(monkeypatch, open=opened)
    chunks, prefix = [bytearray(b"x")], b""
    if defect == "chunk-size":
        monkeypatch.setattr(staging, "MAX_CHUNK_BYTES", 1)
        chunks = [b"xx"]
    elif defect == "chunk-count":
        monkeypatch.setattr(staging, "MAX_CHUNKS", 1)
        chunks, prefix = [b"a", b"b"], b"a"
    with pytest.raises(staging.StagingError, match="^invalid-or-unbounded-chunk$"):
        operation._atomic("asset.bin", chunks, expected_size=10)
    assert (operation.root / ".asset.bin.partial").read_bytes() == prefix
    assert not (operation.root / "asset.bin").exists()
    assert len(descriptors) == 1
    with pytest.raises(OSError):
        real_fstat(descriptors[0])
    operation._root.assert_not_called()


@pytest.mark.parametrize("expected_size", [None, 1])
def test_atomic_byte_bound_refuses_before_writing_or_publishing(tmp_path, monkeypatch, expected_size):
    operation, _leases = _transaction(tmp_path, monkeypatch)
    monkeypatch.setattr(staging, "JOURNAL_BYTES", 1)
    with pytest.raises(staging.StagingError, match="^stage-byte-bound$"):
        operation._atomic("asset.bin", [b"ab"], expected_size=expected_size)
    assert _files(operation.root) == {".asset.bin.partial": b""}
    operation._root.assert_not_called()


@pytest.mark.parametrize("defect", ["symlink", "reparse", "directory", "links", "oversize", "negative-size"])
def test_scan_rejects_unsafe_named_metadata_before_open(tmp_path, monkeypatch, defect):
    operation, _leases = _transaction(tmp_path, monkeypatch)
    path = operation.root / "asset.bin"
    path.write_bytes(ASSET)
    real_lstat, real_open = type(path).lstat, type(path).open
    changes = {"symlink": {"st_mode": stat.S_IFLNK}, "reparse": {"st_file_attributes": 0x400},
        "directory": {"st_mode": stat.S_IFDIR}, "links": {"st_nlink": 2},
        "oversize": {"st_size": len(ASSET) + 1}, "negative-size": {"st_size": -1}}[defect]
    opened = []

    def lstat(selected):
        value = real_lstat(selected)
        return _status(value, **changes) if selected == path else value

    def open_path(selected, *args, **kwargs):
        opened.append(selected)
        return real_open(selected, *args, **kwargs)

    with monkeypatch.context() as patch:
        patch.setattr(type(path), "lstat", lstat)
        patch.setattr(type(path), "open", open_path)
        with pytest.raises(staging.StagingError, match="^unsafe-stage-entry$"):
            operation._scan(path.name, len(ASSET), collect=True)
    assert opened == [] and path.read_bytes() == ASSET


def test_scan_refuses_descriptor_for_different_named_object(tmp_path, monkeypatch):
    operation, _leases = _transaction(tmp_path, monkeypatch)
    path = operation.root / "asset.bin"
    path.write_bytes(ASSET)
    real_fstat = staging.os.fstat

    def changed(descriptor):
        value = real_fstat(descriptor)
        return _status(value, st_ino=value.st_ino + 1)

    _os_facade(monkeypatch, fstat=changed)
    with pytest.raises(staging.StagingError, match="^stage-changed$"):
        operation._scan(path.name, len(ASSET), collect=True)
    assert path.read_bytes() == ASSET


def test_scan_refuses_growth_beyond_the_named_size(tmp_path, monkeypatch):
    operation, _leases = _transaction(tmp_path, monkeypatch)
    path = operation.root / "asset.bin"
    path.write_bytes(b"ab")
    real_lstat, real_fstat = type(path).lstat, staging.os.fstat
    monkeypatch.setattr(type(path), "lstat", lambda selected: _status(real_lstat(selected), st_size=1)
        if selected == path else real_lstat(selected))
    _os_facade(monkeypatch, fstat=lambda descriptor: _status(real_fstat(descriptor), st_size=1))
    with pytest.raises(staging.StagingError, match="^stage-changed$"):
        operation._scan(path.name, 2, collect=True)
    assert path.read_bytes() == b"ab"


@pytest.mark.parametrize("defect", ["short-read", "descriptor-changed", "name-changed"])
def test_scan_refuses_incomplete_or_changed_final_identity(tmp_path, monkeypatch, defect):
    operation, _leases = _transaction(tmp_path, monkeypatch)
    path = operation.root / "asset.bin"
    path.write_bytes(b"ab")
    real_lstat, real_fstat = type(path).lstat, staging.os.fstat
    path_calls, descriptor_calls = [], []

    def lstat(selected):
        value = real_lstat(selected)
        if selected != path:
            return value
        path_calls.append(selected)
        changes = {"st_size": 3} if defect == "short-read" else {}
        if defect == "name-changed" and len(path_calls) == 2:
            changes["st_ino"] = value.st_ino + 1
        return _status(value, **changes)

    def fstat(descriptor):
        value = real_fstat(descriptor)
        descriptor_calls.append(descriptor)
        changes = {"st_size": 3} if defect == "short-read" else {}
        if defect == "descriptor-changed" and len(descriptor_calls) == 2:
            changes["st_nlink"] = 2
        return _status(value, **changes)

    monkeypatch.setattr(type(path), "lstat", lstat)
    _os_facade(monkeypatch, fstat=fstat)
    with pytest.raises(staging.StagingError, match="^stage-changed$"):
        operation._scan(path.name, 3, collect=True)
    assert len(path_calls) == len(descriptor_calls) == 2
    assert path.read_bytes() == b"ab"


def test_inventory_stops_at_its_finite_entry_limit_before_metadata(tmp_path, monkeypatch):
    operation, _leases = _transaction(tmp_path, monkeypatch)
    # One artifact means four expected names plus three possible partial names.
    entries = iter(SimpleNamespace(name=f"unknown-{index}") for index in range(9))
    operation.root = SimpleNamespace(iterdir=lambda: entries)
    monkeypatch.setattr(operation, "_named_file", Mock())
    with pytest.raises(staging.StagingError, match="^unexpected-stage-entry$"):
        operation._inventory()
    assert next(entries).name == "unknown-8"
    operation._named_file.assert_not_called()


@pytest.mark.parametrize("defect", ["reparse", "directory", "links", "permissions", "owner"])
def test_inventory_refuses_unsafe_or_non_private_entry_without_mutating_it(tmp_path, monkeypatch, defect):
    operation, _leases = _transaction(tmp_path, monkeypatch)
    path = operation.root / "asset.bin"
    path.write_bytes(ASSET)
    real_lstat = type(path).lstat
    changes = {"reparse": {"st_file_attributes": 0x400}, "directory": {"st_mode": stat.S_IFDIR},
        "links": {"st_nlink": 2}, "permissions": {"st_mode": stat.S_IFREG | 0o640, "st_uid": 7},
        "owner": {"st_mode": stat.S_IFREG | 0o600, "st_uid": 8}}[defect]
    monkeypatch.setattr(type(path), "lstat", lambda selected: _status(real_lstat(selected), **changes)
        if selected == path else real_lstat(selected))
    _os_facade(monkeypatch, name="posix", getuid=lambda: 7)
    expected = "private-file-required" if defect in ("permissions", "owner") else "unsafe-stage-entry"
    with pytest.raises(staging.StagingError, match="^" + expected + "$"):
        operation._inventory()
    assert path.read_bytes() == ASSET


def test_oversize_phase_record_is_not_written(tmp_path, monkeypatch):
    operation, _leases = _transaction(tmp_path, monkeypatch)
    monkeypatch.setattr(staging, "SET_JOURNAL_BYTES", 1)
    monkeypatch.setattr(operation, "_atomic", Mock())
    with pytest.raises(staging.StagingError, match="^stage-byte-bound$"):
        operation._publish_phase("receiving")
    operation._atomic.assert_not_called()
    assert _files(operation.root) == {}


def test_prepare_refuses_existing_stage_and_keeps_every_existing_byte(tmp_path, monkeypatch):
    operation, leases = _transaction(tmp_path, monkeypatch)
    path = operation.root / "asset.bin"
    path.write_bytes(ASSET)
    path.chmod(0o600)
    before = _files(operation.root)
    with pytest.raises(staging.StagingError, match="^stage-already-started$"):
        operation.prepare(MANIFEST, {"asset.bin": [ASSET]})
    assert _files(operation.root) == before and leases == ["enter", "exit"]


@pytest.mark.parametrize("streams", [None, {}, {"wrong.bin": [ASSET]}, {"asset.bin": [ASSET], "extra.bin": []}])
def test_prepare_refuses_incomplete_or_extra_stream_set_before_journal(tmp_path, monkeypatch, streams):
    operation, leases = _transaction(tmp_path, monkeypatch)
    with pytest.raises(staging.StagingError, match="^invalid-binding$"):
        operation.prepare(MANIFEST, streams)
    assert _files(operation.root) == {} and leases == ["enter", "exit"]


@pytest.mark.parametrize("defect", ["type", "empty", "size", "digest"])
def test_prepare_refuses_invalid_manifest_before_journal(tmp_path, monkeypatch, defect):
    operation, leases = _transaction(tmp_path, monkeypatch)
    manifest = {"type": bytearray(MANIFEST), "empty": b"", "size": MANIFEST, "digest": b"changed"}[defect]
    if defect == "size":
        monkeypatch.setattr(staging, "MAX_MANIFEST_BYTES", len(MANIFEST) - 1)
    with pytest.raises(staging.StagingError, match="^manifest-byte-mismatch$"):
        operation.prepare(manifest, {"asset.bin": [ASSET]})
    assert _files(operation.root) == {} and leases == ["enter", "exit"]


@pytest.mark.parametrize("defect", ["root-kind", "phase-kind", "phase-value", "binding"])
def test_recovery_refuses_wrong_journal_binding_before_payload_validation(tmp_path, monkeypatch, defect):
    operation, leases = _transaction(tmp_path, monkeypatch)
    operation.prepare(MANIFEST, {"asset.bin": [ASSET]})
    record = operation._record("staged")
    if defect == "root-kind":
        record = []
    elif defect == "phase-kind":
        record["phase"] = 3
    elif defect == "phase-value":
        record["phase"] = "installed"
    else:
        record["transaction_id"] = "b" * 64
    (operation.root / staging.JOURNAL).write_bytes(json.dumps(record).encode())
    before = _files(operation.root)
    monkeypatch.setattr(operation, "_check_inputs", Mock())
    with pytest.raises(staging.StagingError, match="^journal-binding-mismatch$"):
        operation.recover()
    operation._check_inputs.assert_not_called()
    assert _files(operation.root) == before and leases == ["enter", "exit", "enter", "exit"]


def test_recovery_maps_io_failure_and_retains_complete_stage(tmp_path, monkeypatch):
    operation, leases = _transaction(tmp_path, monkeypatch)
    operation.prepare(MANIFEST, {"asset.bin": [ASSET]})
    before = _files(operation.root)
    refusal = OSError("private filesystem detail")
    monkeypatch.setattr(operation, "_read", Mock(side_effect=refusal))
    with pytest.raises(staging.StagingError, match="^stage-io-refused$") as found:
        operation.recover()
    assert found.value.__cause__ is refusal
    assert str(found.value) == "stage-io-refused"
    assert _files(operation.root) == before and leases == ["enter", "exit", "enter", "exit"]

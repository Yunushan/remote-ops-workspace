"""Externally bound whole-set staging; no publisher or installer authority.

Required helpers are source-derived from frozen8d26; unused single-input API is
not shipped. Partial files are retained; real leases are injected by the caller.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import stat
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager, ExitStack, contextmanager, nullcontext
from dataclasses import asdict, dataclass
from pathlib import Path

MAX_MANIFEST_BYTES = 1024 * 1024
MAX_ARTIFACT_BYTES = 512 * 1024 * 1024
MAX_CHUNK_BYTES = 1024 * 1024
MAX_CHUNKS = 65536
JOURNAL_BYTES = 4096
JOURNAL = "transaction.json"
MANIFEST = "manifest.json"
LOCK = ".transaction.json.lock"

class StagingError(ValueError):
    """A fixed refusal code; never raw filesystem or manifest diagnostics."""

@dataclass(frozen=True)
class StageBinding:
    manifest_sha256: str
    artifact_name: str
    artifact_sha256: str
    artifact_size: int

    def __post_init__(self):
        for digest in (self.manifest_sha256, self.artifact_sha256):
            if type(digest) is not str or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
                raise StagingError("invalid-binding")
        name = self.artifact_name
        reserved = {"con", "prn", "aux", "nul", *(f"com{i}" for i in range(1, 10)), *(f"lpt{i}" for i in range(1, 10))}
        if type(name) is not str or re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,98}[A-Za-z0-9]", name) is None or name.casefold() in {JOURNAL, MANIFEST} or name.split(".")[0].casefold() in reserved:
            raise StagingError("invalid-binding")
        if type(self.artifact_size) is not int or not 0 <= self.artifact_size <= MAX_ARTIFACT_BYTES:
            raise StagingError("invalid-binding")

def _json(value):
    return (json.dumps(value, sort_keys=True, separators=(",", ":")) + "\n").encode()

def _unique(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise StagingError("ambiguous-journal")
        result[key] = value
    return result

def _linked(status):
    return stat.S_ISLNK(status.st_mode) or bool(getattr(status, "st_file_attributes", 0) & getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400))

def _identity(status):
    return (status.st_dev, status.st_ino, status.st_mode, status.st_size, status.st_nlink, status.st_mtime_ns, status.st_ctime_ns)

def _shared_identity(status):
    # Windows pathname and descriptor APIs differ in ctime semantics.
    return (status.st_dev, status.st_ino, status.st_size, status.st_mtime_ns)

class _StageFiles:
    def _root(self):
        if os.name == "nt":
            if self.private_guard is None:
                raise StagingError("private-staging-platform-unqualified")
            self.private_guard.verify()
        for path in (*reversed(self.root.parents), self.root):
            status = path.lstat()
            if _linked(status) or not stat.S_ISDIR(status.st_mode):
                raise StagingError("unsafe-root")
        status = self.root.lstat()
        if os.name == "posix" and (stat.S_IMODE(status.st_mode) & 0o077 or status.st_uid != os.getuid()):
            raise StagingError("private-root-required")

    def _private_file(self, descriptor, path):
        if self.private_guard is None:
            return nullcontext(None)
        from .windows_private_storage import descriptor_handle

        return self.private_guard.private_file(descriptor_handle(descriptor), path)

    def _named_file(self, path, *, expected_identity=None):
        if self.private_guard is None:
            return nullcontext(None)
        return self.private_guard.named_file(path, expected_identity=expected_identity)

    @contextmanager
    def _verified_files(self):
        # Keep all final names non-delete-shared through the full validator.
        # The journal is finalized before entering this read-only scope.
        self._root()
        with ExitStack() as scope:
            if self.private_guard is not None:
                for name in (JOURNAL, MANIFEST, *(row.artifact_name for row in self.binding.artifacts)):
                    scope.enter_context(self._named_file(self.root / name))
            yield
            self._root()

    def _read(self, name, limit):
        return self._scan(name, limit, collect=True)[2]

    def _atomic(self, name, chunks, expected_size=None, expected_digest=None):
        path = self.root / name
        temporary = self.root / f".{name}.partial"
        digest = hashlib.sha256()
        total = 0
        # Exclusive create retains an interrupted partial for explicit refusal.
        descriptor = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
        try:
            # This function owns the raw descriptor until the one finally close.
            # The stream explicitly never owns it, including failed wrapping.
            with self._private_file(descriptor, temporary) as written:
                with os.fdopen(descriptor, "wb", closefd=False) as stream:
                    # The native named lease also covers automatic close/flush
                    # on body refusal, before native post-check and release.
                    for count, chunk in enumerate(chunks, 1):
                        if count > MAX_CHUNKS or type(chunk) is not bytes or len(chunk) > MAX_CHUNK_BYTES:
                            raise StagingError("invalid-or-unbounded-chunk")
                        total += len(chunk)
                        limit = expected_size if expected_size is not None else JOURNAL_BYTES
                        if total > limit:
                            raise StagingError("stage-byte-bound")
                        stream.write(chunk)
                        digest.update(chunk)
                    if expected_size is not None and total != expected_size or expected_digest is not None and digest.hexdigest() != expected_digest:
                        raise StagingError("staged-byte-mismatch")
                    stream.flush()
                    os.fsync(descriptor)
        finally:
            # The raw handle remains valid through stream close and native
            # identity verification; exactly this owner closes it once.
            os.close(descriptor)
        # All temporary named handles are closed before atomic replacement.
        # Existing targets are validated, never overwritten through unknown ACLs.
        try:
            path.lstat()
        except FileNotFoundError:
            pass
        else:
            with self._named_file(path):
                pass
        self._root()
        os.replace(temporary, path)
        with self._named_file(path, expected_identity=None if written is None else written.identity):
            pass
        self._root()


# Whole-set binding retains every original signed file; no entry is cut.
MAX_ASSETS = 64
MAX_ASSET_SET_BYTES = MAX_ARTIFACT_BYTES * MAX_ASSETS
SET_JOURNAL_BYTES = 65536


@dataclass(frozen=True)
class AssetSetBinding:
    manifest_sha256: str
    artifacts: tuple[StageBinding, ...]

    def __post_init__(self):
        if (type(self.manifest_sha256) is not str
                or re.fullmatch(r"[0-9a-f]{64}", self.manifest_sha256) is None
                or type(self.artifacts) is not tuple or not 1 <= len(self.artifacts) <= MAX_ASSETS):
            raise StagingError("invalid-binding")
        names = set()
        total = 0
        for artifact in self.artifacts:
            if type(artifact) is not StageBinding or artifact.manifest_sha256 != self.manifest_sha256 or artifact.artifact_size <= 0:
                raise StagingError("invalid-binding")
            folded = artifact.artifact_name.casefold()
            if folded in names:
                raise StagingError("invalid-binding")
            names.add(folded)
            total += artifact.artifact_size
        if total > MAX_ASSET_SET_BYTES:
            raise StagingError("invalid-binding")

    @property
    def transaction_id(self):
        return hashlib.sha256(_json(asdict(self))).hexdigest()


class AssetSetTransaction(_StageFiles):
    """Stage the complete externally bound set; still supplies no authority."""

    def __init__(self, root: Path, binding: AssetSetBinding, *, exclusive_lease: Callable[[Path], AbstractContextManager], checkpoint: Callable[[], None] | None = None, private_guard=None):
        if type(binding) is not AssetSetBinding or not callable(exclusive_lease) or checkpoint is not None and not callable(checkpoint):
            raise StagingError("invalid-binding")
        self.root = Path(os.path.abspath(root))
        self.binding = binding
        self.exclusive_lease = exclusive_lease
        self.checkpoint = checkpoint
        self.private_guard = private_guard

    def _tick(self):
        if self.checkpoint is not None:
            self.checkpoint()

    def _scan(self, name, limit, *, collect):
        self._tick()
        path = self.root / name
        before = path.lstat()
        if _linked(before) or not stat.S_ISREG(before.st_mode) or before.st_nlink != 1 or not 0 <= before.st_size <= limit:
            raise StagingError("unsafe-stage-entry")
        with path.open("rb") as stream:
            with self._private_file(stream.fileno(), path):
                opened = os.fstat(stream.fileno())
                if _shared_identity(opened) != _shared_identity(before):
                    raise StagingError("stage-changed")
                digest, parts, total = hashlib.sha256(), [], 0
                while True:
                    self._tick()
                    chunk = stream.read(min(MAX_CHUNK_BYTES, before.st_size - total + 1))
                    self._tick()
                    if not chunk:
                        break
                    total += len(chunk)
                    if total > before.st_size:
                        raise StagingError("stage-changed")
                    digest.update(chunk)
                    if collect:
                        parts.append(chunk)
                after = os.fstat(stream.fileno())
        after_path = path.lstat()
        if total != before.st_size or _identity(opened) != _identity(after) or _identity(after_path) != _identity(before):
            raise StagingError("stage-changed")
        self._tick()
        return total, digest.hexdigest(), b"".join(parts) if collect else None

    def _atomic(self, name, chunks, expected_size=None, expected_digest=None):
        def checked():
            for chunk in chunks:
                self._tick()
                yield chunk
                self._tick()
        self._tick()
        super()._atomic(name, checked(), expected_size, expected_digest)
        self._tick()

    def _inventory(self):
        expected = {JOURNAL, MANIFEST, LOCK, *(row.artifact_name for row in self.binding.artifacts)}
        partials = {f".{name}.partial" for name in expected - {LOCK}}
        names = set()
        for entry in self.root.iterdir():
            names.add(entry.name)
            if len(names) > len(expected) + len(partials):
                raise StagingError("unexpected-stage-entry")
        if names - expected - partials:
            raise StagingError("unexpected-stage-entry")
        for name in names:
            with self._named_file(self.root / name):
                pass
            status = (self.root / name).lstat()
            if _linked(status) or not stat.S_ISREG(status.st_mode) or status.st_nlink != 1:
                raise StagingError("unsafe-stage-entry")
            if os.name == "posix" and (stat.S_IMODE(status.st_mode) & 0o077 or status.st_uid != os.getuid()):
                raise StagingError("private-file-required")
        if names & partials:
            raise StagingError("interrupted-partial-stage")
        return names

    def _record(self, phase):
        return {"schema": "row.update-asset-set-stage.v1", "phase": phase,
                "binding": asdict(self.binding), "transaction_id": self.binding.transaction_id}

    def _publish_phase(self, phase):
        raw = _json(self._record(phase))
        if len(raw) > SET_JOURNAL_BYTES:
            raise StagingError("stage-byte-bound")
        self._atomic(JOURNAL, [raw], len(raw), hashlib.sha256(raw).hexdigest())

    def _check_inputs(self):
        raw = self._read(MANIFEST, MAX_MANIFEST_BYTES)
        if not raw or hashlib.sha256(raw).hexdigest() != self.binding.manifest_sha256:
            raise StagingError("staged-byte-mismatch")
        for artifact in self.binding.artifacts:
            size, digest, _ = self._scan(artifact.artifact_name, artifact.artifact_size, collect=False)
            if size != artifact.artifact_size or digest != artifact.artifact_sha256:
                raise StagingError("staged-byte-mismatch")

    def _status(self):
        return {"transaction_id": self.binding.transaction_id,
                "manifest_sha256": self.binding.manifest_sha256,
                "artifact_count": len(self.binding.artifacts),
                "artifact_total_bytes": sum(row.artifact_size for row in self.binding.artifacts),
                "phase": "staged", "authenticity_checked": False, "install_permitted": False}

    def prepare(self, manifest: bytes, streams: dict[str, Iterable[bytes]]):
        try:
            self._root()
            with self.exclusive_lease(self.root / JOURNAL):
                self._root()
                if self._inventory() - {LOCK}:
                    raise StagingError("stage-already-started")
                expected = {row.artifact_name for row in self.binding.artifacts}
                if type(streams) is not dict or set(streams) != expected:
                    raise StagingError("invalid-binding")
                if type(manifest) is not bytes or not 0 < len(manifest) <= MAX_MANIFEST_BYTES or hashlib.sha256(manifest).hexdigest() != self.binding.manifest_sha256:
                    raise StagingError("manifest-byte-mismatch")
                self._publish_phase("receiving")
                self._atomic(MANIFEST, [manifest], len(manifest), self.binding.manifest_sha256)
                for artifact in self.binding.artifacts:
                    self._atomic(artifact.artifact_name, streams[artifact.artifact_name], artifact.artifact_size, artifact.artifact_sha256)
                self._inventory()
                self._check_inputs()
                self._publish_phase("staged")
                return self._status()
        except OSError as exc:
            raise StagingError("stage-io-refused") from exc

    def recover(self):
        try:
            self._root()
            with self.exclusive_lease(self.root / JOURNAL):
                self._root()
                expected = {JOURNAL, MANIFEST, *(row.artifact_name for row in self.binding.artifacts)}
                if self._inventory() - {LOCK} != expected:
                    raise StagingError("incomplete-stage")
                raw = self._read(JOURNAL, SET_JOURNAL_BYTES)
                try:
                    record = json.loads(raw, object_pairs_hook=_unique)
                except (ValueError, UnicodeError, RecursionError) as exc:
                    raise StagingError("ambiguous-journal") from exc
                if (type(record) is not dict or type(record.get("phase")) is not str
                        or record["phase"] not in {"receiving", "staged"}
                        or _json(record) != _json(self._record(record["phase"]))):
                    raise StagingError("journal-binding-mismatch")
                self._check_inputs()
                if record["phase"] == "receiving":
                    self._publish_phase("staged")
                return self._status()
        except OSError as exc:
            raise StagingError("stage-io-refused") from exc

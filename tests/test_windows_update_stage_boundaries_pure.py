"""Unexecuted explicit mock fixtures; never genuine Windows privacy authority.

These exercise selected actual source functions with mocked filesystem/native
providers. They do not invoke DLLs, ctypes, real processes, live TLS or settings.
No existing successful fixture or native host receipt is rerun or transferred.
"""
from __future__ import annotations

import hashlib
import stat
from contextlib import ExitStack, contextmanager
from dataclasses import replace
from types import SimpleNamespace

import pytest

from remote_ops_workspace import state_lock as locks
from remote_ops_workspace import update_channel as channel
from remote_ops_workspace import update_staging as staging
from remote_ops_workspace import windows_private_storage as storage

USER = bytes.fromhex("01020000000000051500000064000000")
OTHER = bytes.fromhex("01020000000000051500000065000000")
EVERYONE = bytes.fromhex("010100000000000100000000")
ROAMING = r"C:\Users\Synthetic\AppData\Roaming"
LOCAL = r"C:\Users\Synthetic\AppData\Local"
HOME = ROAMING + r"\RemoteOpsWorkspace"
STAGE = r"C:\SyntheticStage"


def private(index, *, directory):
    return storage.Snapshot((1, 0, index), storage.DIRECTORY if directory else 0x20, 1, USER,
                            storage.DACL_PRESENT | storage.DACL_PROTECTED,
                            (storage.Ace(0, 3 if directory else 16, storage.FILE_ALL_ACCESS, USER),), "a" * 64)


def parent(index):
    return storage.Snapshot((1, 0, index), storage.DIRECTORY, 1, storage.SYSTEM_SID, storage.DACL_PRESENT,
                            (storage.Ace(0, 3, storage.FILE_ALL_ACCESS, USER),
                             storage.Ace(0, 0, 0x80000000, EVERYONE)), "b" * 64)


class MockNative:
    def __init__(self, *, missing=(), private_roots=(HOME, STAGE)):
        self.missing, self.private_roots = set(missing), set(private_roots)
        self.events, self.handles, self.ids, self.observations = [], {}, {}, {}
        self.user = USER
        self.entries = []
        self.known = {("roaming", False): ROAMING, ("roaming", True): ROAMING,
                      ("local", False): LOCAL, ("local", True): LOCAL}

    @contextmanager
    def directory_entries(self, path):
        assert path == STAGE
        self.events.append(("metadata-enumeration", path))
        try:
            yield iter(self.entries)
        finally:
            self.events.append(("metadata-enumeration-close", path))

    def token_user(self):
        self.events.append(("token",))
        return self.user

    def known_folder(self, role, *, default=False):
        self.events.append(("known", role, default))
        return self.known[(role, default)]

    def open_directory(self, path):
        self.events.append(("open-directory", path))
        if any(path == missing or path.startswith(missing + "\\") for missing in self.missing):
            raise storage.PrivatePathMissing("native-directory-missing")
        handle = len(self.handles) + 1
        self.handles[handle] = path
        self.ids.setdefault(path, len(self.ids) + 1)
        self.observations.setdefault(path, private(self.ids[path], directory=True)
                                     if path in self.private_roots else parent(self.ids[path]))
        return handle

    def snapshot(self, handle):
        self.events.append(("snapshot", self.handles[handle]))
        return self.observations[self.handles[handle]]

    def open_file(self, path):
        self.events.append(("open-file", path))
        handle = len(self.handles) + 1
        self.handles[handle] = path
        self.ids.setdefault(path, len(self.ids) + 1)
        self.observations.setdefault(path, private(self.ids[path], directory=False))
        return handle

    def identity(self, handle):
        observed = self.observations[self.handles[handle]]
        return observed.identity, observed.attributes, observed.links

    def create_private_directory(self, path, user):
        assert user == USER and path in self.missing
        self.events.append(("create-private", path))
        self.missing.remove(path)
        self.private_roots.add(path)

    def close(self, handle):
        self.events.append(("close", handle))


def test_default_home_binds_both_actual_known_folders_and_never_creates_current_home():
    native = MockNative(missing=(HOME, STAGE))
    with storage.windows_update_boundary(STAGE, HOME, create=True, _native=native,
                                         _environment={"APPDATA": ROAMING}) as guard:
        assert guard.path == STAGE
        assert ("create-private", STAGE) in native.events
        assert ("create-private", HOME) not in native.events
        assert [(row[1], row[2]) for row in native.events if row[0] == "known"] == [
            ("roaming", False), ("roaming", True), ("local", False), ("local", True)]
        creation = native.events.index(("create-private", STAGE))
        assert ("snapshot", "C:\\") in native.events[:creation]
    opened = [row for row in native.events if row[0] in ("open-directory", "open-file")
              and row[1] not in (HOME, STAGE)]
    closed = [row for row in native.events if row[0] == "close"]
    # Missing observations have no handle and are not counted as owned opens.
    assert len(closed) >= 7 and opened


@pytest.mark.parametrize("defect", ["appdata", "redirected-roaming", "redirected-local", "current-home"])
def test_default_selection_refusals_happen_before_stage_creation_or_payload(defect):
    native = MockNative(missing=(STAGE,))
    environment, selected = {"APPDATA": ROAMING}, HOME
    if defect == "appdata":
        environment["APPDATA"] = r"C:\AttackerSelected"
    elif defect == "redirected-roaming":
        native.known[("roaming", True)] = r"C:\OtherRoaming"
    elif defect == "redirected-local":
        native.known[("local", True)] = r"C:\OtherLocal"
    else:
        selected = r"C:\OtherHome"
    with pytest.raises(storage.PrivateStorageError):
        with storage.windows_update_boundary(STAGE, selected, create=True, _native=native,
                                             _environment=environment):
            pytest.fail("unbound Windows data_dir selection accepted")
    assert not any(row[0] in ("create-private", "open-file") for row in native.events)


@pytest.mark.parametrize("override", ["relative", r"C:\Users\Synthetic\..\Home", r"C:\AliasHome", r"C:\Home:stream"])
def test_row_home_original_selection_is_bound_without_resolve_or_expansion(override):
    native = MockNative(missing=(STAGE,))
    with pytest.raises(storage.PrivateStorageError):
        with storage.windows_update_boundary(STAGE, HOME, create=True, _native=native,
                                             _environment={"ROW_HOME": override}):
            pytest.fail("aliased/unbound ROW_HOME accepted")
    assert not any(row[0] in ("known", "create-private", "open-file") for row in native.events)


def test_existing_wrong_current_home_acl_refuses_before_selected_stage_creation():
    native = MockNative(missing=(STAGE,))
    native.observations[HOME] = replace(private(80, directory=True), owner=OTHER)
    with pytest.raises(storage.PrivateStorageError, match="private-owner-mismatch"):
        with storage.windows_update_boundary(STAGE, HOME, create=True, _native=native,
                                             _environment={"ROW_HOME": HOME}):
            pytest.fail("unprivate current home accepted")
    assert not any(row[0] in ("create-private", "open-file") for row in native.events)
    assert [row[1] for row in native.events if row[0] == "close"] == list(range(6, 0, -1))


def test_non_missing_native_open_error_never_triggers_private_directory_creation():
    class Denied(MockNative):
        def open_directory(self, path):
            if path == STAGE:
                raise storage.PrivateStorageError("native-directory-open-refused")
            return super().open_directory(path)

    native = Denied(missing=(STAGE,))
    with pytest.raises(storage.PrivateStorageError, match="native-directory-open-refused"):
        with storage.private_stage_guard(STAGE, create_if_missing=True, _native=native):
            pytest.fail("access-denied interpreted as absence")
    assert not any(row[0] == "create-private" for row in native.events)


def test_first_use_current_home_changes_refuse_without_rewriting_either_root():
    native = MockNative(missing=(HOME,))
    with pytest.raises(storage.PrivateStorageError, match="native-missing-boundary-changed"):
        with storage.private_home_guard(HOME, _native=native):
            native.missing.remove(HOME)
    assert not any(row[0] == "create-private" for row in native.events)


def test_final_native_file_binding_refuses_the_wrong_replacement_identity():
    native = MockNative()
    with storage.private_stage_guard(STAGE, _native=native) as guard:
        with pytest.raises(storage.PrivateStorageError, match="private-final-identity-mismatch"):
            with guard.named_file(STAGE + r"\manifest.json", expected_identity=(1, 0, 999)):
                pytest.fail("unexpected replacement object accepted")
    assert native.events[-2:] == [("close", 2), ("close", 1)]


class Scene:
    def __init__(self):
        self.events, self.data, self.ids, self.descriptors = [], {}, {}, {}
        self.next_descriptor, self.next_identity = 100, 20

    def path(self, name):
        return MockPath(self, name)

    def status(self, name):
        if name not in self.data:
            raise FileNotFoundError
        return SimpleNamespace(st_dev=1, st_ino=self.ids[name], st_mode=stat.S_IFREG | 0o600,
                               st_nlink=1, st_size=len(self.data[name]), st_mtime_ns=2, st_ctime_ns=2)

    def open(self, path, flags, _mode=0o600):
        name = str(path)
        self.events.append(("open", name, flags))
        if flags & 128 and name in self.data:
            raise FileExistsError
        if name not in self.data:
            self.next_identity += 1
            self.data[name], self.ids[name] = b"", self.next_identity
        self.next_descriptor += 1
        self.descriptors[self.next_descriptor] = name
        return self.next_descriptor

    def close(self, descriptor):
        self.events.append(("close-crt", descriptor))

    def write(self, descriptor, data):
        self.events.append(("write", self.descriptors[descriptor], data))
        self.data[self.descriptors[descriptor]] += data
        return len(data)

    def fstat(self, descriptor):
        return self.status(self.descriptors[descriptor])

    def replace(self, old, new):
        self.events.append(("replace", str(old), str(new)))
        self.data[str(new)] = self.data.pop(str(old))
        self.ids[str(new)] = self.ids.pop(str(old))

    def namespace(self):
        return SimpleNamespace(name="nt", O_WRONLY=1, O_RDWR=2, O_CREAT=64, O_EXCL=128, O_BINARY=32768, SEEK_SET=0,
                               open=self.open, close=self.close, write=self.write, fstat=self.fstat,
                               fdopen=lambda descriptor, _mode, **kwargs: MockStream(self, descriptor, closefd=kwargs.get("closefd", True)),
                               fsync=lambda descriptor: self.events.append(("fsync", descriptor)),
                               lseek=lambda descriptor, *_args: self.events.append(("seek", descriptor)),
                               replace=self.replace)


class MockPath:
    def __init__(self, scene, name):
        self.scene, self.name = scene, name

    def __str__(self):
        return self.name

    def __truediv__(self, child):
        return MockPath(self.scene, self.name + "\\" + child)

    @property
    def parent(self):
        return MockPath(self.scene, self.name.rsplit("\\", 1)[0])

    def lstat(self):
        return self.scene.status(self.name)

    def stat(self, **_kwargs):
        return self.lstat()

    def is_symlink(self):
        return False

    def open(self, _mode):
        descriptor = self.scene.open(self, 2)
        return MockStream(self.scene, descriptor)


class MockStream:
    def __init__(self, scene, descriptor, *, closefd=True):
        self.scene, self.descriptor, self.offset = scene, descriptor, 0
        self.closefd = closefd

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        self.scene.events.append(("stream-close", self.descriptor))
        if self.closefd:
            self.scene.close(self.descriptor)

    def fileno(self):
        return self.descriptor

    def write(self, raw):
        return self.scene.write(self.descriptor, raw)

    def read(self, size):
        name = self.scene.descriptors[self.descriptor]
        self.scene.events.append(("read", name, size))
        raw = self.scene.data[name][self.offset:self.offset + size]
        self.offset += len(raw)
        return raw

    def flush(self):
        self.scene.events.append(("flush", self.descriptor))


class RecordingGuard:
    def __init__(self, scene, *, refuse=False, wrong_final=False):
        self.scene, self.refuse, self.wrong_final = scene, refuse, wrong_final

    def verify(self):
        self.scene.events.append(("verify-root",))

    @contextmanager
    def private_file(self, descriptor, path):
        name = str(path)
        self.scene.events.append(("private-enter", name, descriptor))
        if self.refuse:
            raise storage.PrivateStorageError("private-dacl-not-exact")
        try:
            yield SimpleNamespace(identity=(1, 0, self.scene.ids[name]))
            self.scene.events.append(("private-verified", name))
        finally:
            self.scene.events.append(("private-close", name))

    @contextmanager
    def named_file(self, path, *, expected_identity=None):
        name = str(path)
        self.scene.events.append(("named-enter", name, expected_identity))
        if self.wrong_final or expected_identity is not None and expected_identity != (1, 0, self.scene.ids[name]):
            raise storage.PrivateStorageError("private-final-identity-mismatch")
        try:
            yield SimpleNamespace(identity=(1, 0, self.scene.ids[name]))
        finally:
            self.scene.events.append(("named-close", name))


def staging_fixture(monkeypatch, *, refuse=False, wrong_final=False):
    scene = Scene()
    guard = RecordingGuard(scene, refuse=refuse, wrong_final=wrong_final)
    monkeypatch.setattr(staging, "os", scene.namespace())
    monkeypatch.setattr(storage, "descriptor_handle", lambda descriptor: descriptor)
    operation = object.__new__(staging.AssetSetTransaction)
    operation.root, operation.private_guard, operation.checkpoint = scene.path(STAGE), guard, None
    monkeypatch.setattr(operation, "_root", guard.verify)
    return scene, guard, operation


def test_actual_atomic_writer_checks_private_empty_file_before_first_generator_byte(monkeypatch):
    scene, _guard, operation = staging_fixture(monkeypatch)

    def chunks():
        scene.events.append(("generator-first-byte",))
        yield b"actual mock payload"

    body = b"actual mock payload"
    operation._atomic("manifest.json", chunks(), len(body), hashlib.sha256(body).hexdigest())
    labels = [row[0] for row in scene.events]
    assert labels.index("private-enter") < labels.index("generator-first-byte") < labels.index("write")
    assert labels.index("fsync") < labels.index("private-close") < labels.index("close-crt") < labels.index("replace")
    assert labels.index("replace") < labels.index("named-enter") < labels.index("named-close")
    assert scene.data[STAGE + r"\manifest.json"] == body


def test_temporary_acl_refusal_consumes_no_payload_and_retains_only_empty_partial(monkeypatch):
    scene, _guard, operation = staging_fixture(monkeypatch, refuse=True)

    def chunks():
        pytest.fail("generator requested before Windows DACL verification")
        yield b"never consumed"

    with pytest.raises(storage.PrivateStorageError, match="private-dacl-not-exact"):
        operation._atomic("manifest.json", chunks(), 1, "a" * 64)
    assert scene.data == {STAGE + r"\.manifest.json.partial": b""}
    assert not any(row[0] in ("write", "replace", "read") for row in scene.events)
    assert any(row[0] == "close-crt" for row in scene.events)


def test_existing_predecessor_is_verified_before_replace_and_final_identity_is_checked(monkeypatch):
    scene, _guard, operation = staging_fixture(monkeypatch)
    name = STAGE + r"\transaction.json"
    scene.data[name], scene.ids[name] = b"old", 10
    body = b"new"
    operation._atomic("transaction.json", [body], len(body), hashlib.sha256(body).hexdigest())
    predecessor = scene.events.index(("named-enter", name, None))
    replace_at = next(index for index, row in enumerate(scene.events) if row[0] == "replace")
    final_at = next(index for index, row in enumerate(scene.events) if row[0] == "named-enter" and row[2] is not None)
    assert predecessor < replace_at < final_at
    assert scene.data[name] == body


def test_postreplace_private_identity_refusal_never_returns_success(monkeypatch):
    scene, _guard, operation = staging_fixture(monkeypatch, wrong_final=True)
    body = b"retained failed final evidence"
    with pytest.raises(storage.PrivateStorageError, match="private-final-identity-mismatch"):
        operation._atomic("manifest.json", [body], len(body), hashlib.sha256(body).hexdigest())
    assert scene.data[STAGE + r"\manifest.json"] == body
    assert any(row[0] == "replace" for row in scene.events)


def test_recovery_actual_file_descriptor_is_guarded_before_first_read(monkeypatch):
    scene, _guard, operation = staging_fixture(monkeypatch)
    name = STAGE + r"\manifest.json"
    scene.data[name], scene.ids[name] = b"recovery original bytes", 10
    size, digest, body = operation._scan("manifest.json", 1024, collect=True)
    assert size == len(body) and digest == hashlib.sha256(body).hexdigest()
    labels = [row[0] for row in scene.events]
    assert labels.index("private-enter") < labels.index("read") < labels.index("private-close") < labels.index("close-crt")


def test_recovery_private_acl_refusal_does_not_read_existing_plaintext(monkeypatch):
    scene, _guard, operation = staging_fixture(monkeypatch, refuse=True)
    name = STAGE + r"\manifest.json"
    scene.data[name], scene.ids[name] = b"secret synthetic bytes", 10
    with pytest.raises(storage.PrivateStorageError):
        operation._scan("manifest.json", 1024, collect=True)
    assert not any(row[0] == "read" for row in scene.events)
    assert any(row[0] == "close-crt" for row in scene.events)


def lock_fixture(monkeypatch, *, refuse=False):
    scene = Scene()
    guard = RecordingGuard(scene, refuse=refuse)
    monkeypatch.setattr(locks, "os", scene.namespace())
    monkeypatch.setattr(storage, "descriptor_handle", lambda descriptor: descriptor)
    monkeypatch.setattr(locks, "ensure_private_dir_required", lambda *_args: pytest.fail("Windows guarded lock used chmod/mkdir"))
    monkeypatch.setattr(locks, "_secure_lock_mode", lambda *_args, **_kwargs: pytest.fail("native privacy inferred from chmod"))
    return scene, guard


def test_actual_lock_nul_is_after_private_reader_writer_binding_and_lease_retained(monkeypatch):
    scene, guard = lock_fixture(monkeypatch)
    path = scene.path(STAGE + r"\.transaction.json.lock")
    with ExitStack() as scope:
        descriptor = locks._open_lock_file(path, _private_guard=guard, _private_scope=scope)
        labels = [row[0] for row in scene.events]
        assert labels.index("private-enter") < labels.index("write") < labels.index("fsync")
        assert "private-close" not in labels
        assert scene.data[str(path)] == b"\0"
    assert scene.events[-2:] == [("private-verified", str(path)), ("private-close", str(path))]
    scene.close(descriptor)


def test_actual_lock_acl_refusal_precedes_first_nul_and_closes_empty_descriptor(monkeypatch):
    scene, guard = lock_fixture(monkeypatch, refuse=True)
    with ExitStack() as scope:
        with pytest.raises(storage.PrivateStorageError, match="private-dacl-not-exact"):
            locks._open_lock_file(scene.path(STAGE + r"\.transaction.json.lock"),
                                  _private_guard=guard, _private_scope=scope)
    assert list(scene.data.values()) == [b""]
    assert not any(row[0] in ("write", "fsync") for row in scene.events)
    assert any(row[0] == "close-crt" for row in scene.events)


@pytest.mark.parametrize("failure", ["unlock", "native-close", "crt-close"])
def test_owned_lock_cleanup_attempts_all_remaining_resources_on_refusal(monkeypatch, failure):
    events = []

    def step(role):
        events.append(role)
        if role == failure:
            raise OSError("synthetic cleanup refusal")

    @contextmanager
    def registry():
        yield

    monkeypatch.setattr(locks, "_registry_guard", registry())
    monkeypatch.setattr(locks, "_active_lock_descriptors", {17})
    monkeypatch.setattr(locks, "_release_os_lock", lambda *_args: step("unlock"))
    monkeypatch.setattr(locks, "os", SimpleNamespace(close=lambda *_args: step("crt-close")))
    with pytest.raises(OSError):
        locks._close_owned_lock(17, True, SimpleNamespace(close=lambda: step("native-close")))
    assert events == ["unlock", "native-close", "crt-close"] and not locks._active_lock_descriptors


def test_whole_exclusive_lock_releases_thread_state_when_native_cleanup_refuses(monkeypatch):
    events, held, held_guards = [], {}, {}

    class Scope:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

    class ThreadLease:
        def acquire(self, **_kwargs):
            events.append("thread-acquire")
            return True

        def release(self):
            events.append("thread-release")

    def native_close():
        events.append("native-close")
        raise storage.PrivateStorageError("native-handle-cleanup-refused")

    def opened(_path, **kwargs):
        kwargs["_private_scope"].callback(native_close)
        return 17

    monkeypatch.setattr(locks, "os", SimpleNamespace(name="nt", getpid=lambda: 1,
                                                   close=lambda *_args: events.append("crt-close")))
    monkeypatch.setattr(locks, "time", SimpleNamespace(monotonic=lambda: 0))
    monkeypatch.setattr(locks, "_registry_guard", Scope())
    monkeypatch.setattr(locks, "_active_lock_descriptors", set())
    monkeypatch.setattr(locks, "lock_path_for", lambda path: path)
    monkeypatch.setattr(locks, "_canonical_lock_key", lambda _path: "fixed-key")
    monkeypatch.setattr(locks, "_thread_lock_for", lambda _key: ThreadLease())
    monkeypatch.setattr(locks, "_held_locks", lambda: held)
    monkeypatch.setattr(locks, "_held_private_guards", lambda: held_guards)
    monkeypatch.setattr(locks, "_open_lock_file", opened)
    monkeypatch.setattr(locks, "_acquire_os_lock", lambda *_args: events.append("os-lock"))
    monkeypatch.setattr(locks, "_release_os_lock", lambda *_args: events.append("os-unlock"))
    guard = SimpleNamespace(verify=lambda: events.append("root-verify"))
    with pytest.raises(storage.PrivateStorageError, match="native-handle-cleanup-refused"):
        with locks.exclusive_file_lock("synthetic journal", _private_guard=guard):
            events.append("body")
    assert events[-4:] == ["os-unlock", "native-close", "crt-close", "thread-release"]
    assert not held and not held_guards and not locks._active_lock_descriptors


def test_private_lock_reentry_refuses_different_guard_before_file_open(monkeypatch):
    events = []
    first = object()
    second = SimpleNamespace(verify=lambda: events.append("verify"))
    monkeypatch.setattr(locks, "os", SimpleNamespace(name="nt", getpid=lambda: 1))
    monkeypatch.setattr(locks, "time", SimpleNamespace(monotonic=lambda: 0))
    monkeypatch.setattr(locks, "lock_path_for", lambda path: path)
    monkeypatch.setattr(locks, "_canonical_lock_key", lambda _path: "same")
    monkeypatch.setattr(locks, "_thread_lock_for", lambda _key: SimpleNamespace(
        acquire=lambda **_kwargs: True, release=lambda: events.append("release")))
    monkeypatch.setattr(locks, "_held_locks", lambda: {"same": 1})
    monkeypatch.setattr(locks, "_held_private_guards", lambda: {"same": first})
    monkeypatch.setattr(locks, "_open_lock_file", lambda *_args, **_kwargs: pytest.fail("reentry opened a different file"))
    with pytest.raises(OSError, match="reentry refused"):
        with locks.exclusive_file_lock("synthetic journal", _private_guard=second):
            pytest.fail("different native boundary accepted on reentry")
    assert events == ["verify", "release"]


def test_windows_false_qualification_refuses_before_policy_file_or_native_loading(monkeypatch):
    monkeypatch.setattr(channel, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(channel, "_WINDOWS_PRIVATE_STAGE_QUALIFIED", False)
    monkeypatch.setattr(channel, "_read_regular", lambda *_args, **_kwargs: pytest.fail("unqualified Windows policy consumed"))
    with pytest.raises(channel.UpdateError, match="private-staging-platform-unqualified"):
        channel.load_update_policy("synthetic policy path")
    with pytest.raises(channel.UpdateError, match="private-staging-platform-unqualified"):
        with channel._stage_boundary(STAGE, HOME):
            pytest.fail("unqualified native stage opened")


def test_actual_policy_reader_native_refusal_precedes_policy_bytes(monkeypatch):
    scene, _guard, _operation = staging_fixture(monkeypatch, refuse=True)
    path = scene.path(STAGE + r"\operator-policy.json")
    scene.data[str(path)], scene.ids[str(path)] = b"synthetic public-key policy", 10
    monkeypatch.setattr(channel, "Path", lambda value: value)
    fake_os = scene.namespace()
    fake_os.path = SimpleNamespace(abspath=lambda value: value)
    monkeypatch.setattr(channel, "os", fake_os)
    monkeypatch.setattr(channel, "_no_links", lambda *_args: None)
    guard = RecordingGuard(scene, refuse=True)
    with pytest.raises(storage.PrivateStorageError):
        channel._read_regular(path, 1024, private_guard=guard)
    assert not any(row[0] == "read" for row in scene.events)


def test_policy_loader_retains_exact_private_parent_through_policy_decoding(monkeypatch):
    events, selected = [], SimpleNamespace(parent="synthetic parent")
    guard = object()

    @contextmanager
    def private_parent(path):
        assert path == selected.parent
        events.append("parent-enter")
        try:
            yield guard
        finally:
            events.append("parent-close")

    def read(path, maximum, *, private_guard):
        assert path is selected and maximum == channel.POLICY_BYTES and private_guard is guard
        events.append("guarded-read")
        return b"synthetic operator policy"

    def decode(raw):
        assert raw == b"synthetic operator policy" and events == ["parent-enter", "guarded-read"]
        events.append("policy-decode")
        return "synthetic parsed policy"

    monkeypatch.setattr(channel, "os", SimpleNamespace(name="nt", path=SimpleNamespace(abspath=lambda path: path)))
    monkeypatch.setattr(channel, "Path", lambda _value: selected)
    monkeypatch.setattr(channel, "_WINDOWS_PRIVATE_STAGE_QUALIFIED", True)
    monkeypatch.setattr(storage, "private_stage_guard", private_parent)
    monkeypatch.setattr(channel, "_read_regular", read)
    monkeypatch.setattr(channel, "UpdatePolicy", decode)
    assert channel.load_update_policy("synthetic") == "synthetic parsed policy"
    assert events == ["parent-enter", "guarded-read", "policy-decode", "parent-close"]


def test_complete_validator_is_called_with_all_final_names_retained(monkeypatch):
    scene, guard, operation = staging_fixture(monkeypatch)
    raw = b"mock original manifest"
    digest = hashlib.sha256(raw).hexdigest()
    operation.binding = staging.AssetSetBinding(digest, (staging.StageBinding(digest, "release.zip", "a" * 64, 1),))
    names = ["transaction.json", "manifest.json", "release.zip"]
    for index, name in enumerate(names):
        scene.data[STAGE + "\\" + name], scene.ids[STAGE + "\\" + name] = b"x", index + 1

    def verify_held(*_args):
        scene.events.append(("full-validator",))
        assert len([row for row in scene.events if row[0] == "named-enter"]) == 3
        assert not any(row[0] == "named-close" for row in scene.events)
        return {"install_permitted": False}

    monkeypatch.setattr(channel, "_verify_complete_held", verify_held)
    assert channel._verify_complete(operation, None, None, 0) == {"install_permitted": False}
    labels = [row[0] for row in scene.events]
    assert labels.count("named-close") == 3 and labels.index("full-validator") < labels.index("named-close")
    assert operation.private_guard is guard


def test_nested_transaction_lease_uses_exact_outer_guard_and_no_authority(monkeypatch):
    selected_guard, calls = object(), []

    def acquire(path, **kwargs):
        calls.append((path, kwargs))
        return SimpleNamespace()

    monkeypatch.setattr(channel, "exclusive_file_lock", acquire)
    result = channel._stage_lease("synthetic journal", 12, selected_guard)
    assert result is not None
    assert calls == [("synthetic journal", {"timeout_seconds": 12, "_private_guard": selected_guard})]


@pytest.mark.parametrize("interrupt", [KeyboardInterrupt, SystemExit])
def test_lock_open_interrupt_before_return_closes_local_descriptor_without_nul(monkeypatch, interrupt):
    scene, guard = lock_fixture(monkeypatch)
    fake_os = scene.namespace()

    def interrupted(_descriptor):
        raise interrupt

    fake_os.fstat = interrupted
    monkeypatch.setattr(locks, "os", fake_os)
    with ExitStack() as scope:
        with pytest.raises(interrupt):
            locks._open_lock_file(scene.path(STAGE + r"\.transaction.json.lock"),
                                  _private_guard=guard, _private_scope=scope)
    assert list(scene.data.values()) == [b""]
    assert not any(row[0] in ("write", "fsync", "private-enter") for row in scene.events)
    assert len([row for row in scene.events if row[0] == "close-crt"]) == 1


def test_stream_constructor_refusal_closes_raw_writer_before_any_payload_request(monkeypatch):
    scene, _guard, operation = staging_fixture(monkeypatch)
    fake_os = scene.namespace()

    def refused(*_args, **kwargs):
        assert kwargs == {"closefd": False}
        raise OSError("synthetic fdopen construction refusal")

    fake_os.fdopen = refused
    monkeypatch.setattr(staging, "os", fake_os)

    def payload():
        pytest.fail("fdopen failure consumed a generator byte")
        yield b"never requested"

    with pytest.raises(OSError, match="synthetic fdopen"):
        operation._atomic("manifest.json", payload(), 1, "a" * 64)
    assert scene.data == {STAGE + r"\.manifest.json.partial": b""}
    assert len([row for row in scene.events if row[0] == "close-crt"]) == 1
    assert not any(row[0] in ("write", "replace") for row in scene.events)
    assert [row[0] for row in scene.events].count("private-enter") == 1
    assert [row[0] for row in scene.events].index("private-close") < [row[0] for row in scene.events].index("close-crt")


def test_unsafe_existing_receiving_journal_refuses_before_first_lock_or_payload_byte():
    native = MockNative()
    path = STAGE + r"\transaction.json"
    native.entries = [path]
    native.observations[path] = replace(private(80, directory=False), owner=OTHER)
    with pytest.raises(storage.PrivateStorageError, match="private-owner-mismatch"):
        with storage.windows_update_boundary(STAGE, HOME, _native=native,
                                             _environment={"ROW_HOME": HOME}):
            native.events.append(("first-lock-nul-or-payload",))
    assert not any(row[0] in ("first-lock-nul-or-payload", "create-private") for row in native.events)
    assert ("metadata-enumeration-close", STAGE) in native.events
    assert len([row for row in native.events if row[0] == "close"]) == len(native.handles)


def test_direct_child_metadata_enumeration_bound_refuses_before_first_new_byte():
    native = MockNative()
    native.entries = [STAGE + rf"\synthetic-{index}.zip" for index in range(135)]
    with pytest.raises(storage.PrivateStorageError, match="private-entry-bound"):
        with storage.windows_update_boundary(STAGE, HOME, _native=native,
                                             _environment={"ROW_HOME": HOME}):
            native.events.append(("first-lock-nul-or-payload",))
    assert not any(row[0] == "first-lock-nul-or-payload" for row in native.events)
    assert len([row for row in native.events if row[0] == "open-file"]) == 134
    assert len([row for row in native.events if row[0] == "close"]) == len(native.handles)


def test_metadata_enumerator_failure_closes_every_native_ancestor_and_consumes_no_payload():
    class FailedEnumeration(MockNative):
        @contextmanager
        def directory_entries(self, _path):
            raise OSError("synthetic enumeration refusal")
            yield

    native = FailedEnumeration()
    with pytest.raises(OSError, match="synthetic enumeration"):
        with storage.windows_update_boundary(STAGE, HOME, _native=native,
                                             _environment={"ROW_HOME": HOME}):
            native.events.append(("first-lock-nul-or-payload",))
    assert not any(row[0] in ("first-lock-nul-or-payload", "open-file") for row in native.events)
    assert len([row for row in native.events if row[0] == "close"]) == len(native.handles)


def test_raw_writer_ownership_is_explicit_and_native_check_precedes_one_raw_close(monkeypatch):
    scene, _guard, operation = staging_fixture(monkeypatch)
    fake_os = scene.namespace()

    def stream(descriptor, mode, **kwargs):
        assert mode == "wb" and kwargs == {"closefd": False}
        scene.events.append(("explicit-closefd-false",))
        return MockStream(scene, descriptor, closefd=False)

    fake_os.fdopen = stream
    monkeypatch.setattr(staging, "os", fake_os)
    operation._atomic("manifest.json", [b"x"], 1, hashlib.sha256(b"x").hexdigest())
    labels = [row[0] for row in scene.events]
    assert labels.index("private-enter") < labels.index("explicit-closefd-false")
    assert labels.index("stream-close") < labels.index("private-verified") < labels.index("private-close") < labels.index("close-crt")
    assert labels.count("close-crt") == 1


def test_buffered_failure_close_flush_stays_inside_native_named_lease(monkeypatch):
    scene, _guard, operation = staging_fixture(monkeypatch)
    fake_os = scene.namespace()

    class Buffered(MockStream):
        def __init__(self, descriptor):
            super().__init__(scene, descriptor, closefd=False)
            self.pending = []

        def write(self, raw):
            self.pending.append(raw)
            return len(raw)

        def __exit__(self, *_args):
            labels = [row[0] for row in scene.events]
            assert "private-enter" in labels and "private-close" not in labels
            scene.events.append(("failure-close-flush",))
            for raw in self.pending:
                scene.write(self.descriptor, raw)
            super().__exit__()

    fake_os.fdopen = lambda descriptor, _mode, **kwargs: Buffered(descriptor) if kwargs == {"closefd": False} else pytest.fail("raw ownership transferred")
    monkeypatch.setattr(staging, "os", fake_os)
    with pytest.raises(staging.StagingError, match="staged-byte-mismatch"):
        operation._atomic("manifest.json", [b"private interrupted bytes"], 30, "a" * 64)
    labels = [row[0] for row in scene.events]
    assert labels.index("failure-close-flush") < labels.index("write") < labels.index("stream-close") < labels.index("private-close") < labels.index("close-crt")
    assert labels.count("close-crt") == 1 and "replace" not in labels

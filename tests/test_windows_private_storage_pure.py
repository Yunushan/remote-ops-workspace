"""Authored unexecuted fixtures. Explicit mock provider; never ctypes/security APIs."""
from dataclasses import replace

import pytest

from remote_ops_workspace import windows_private_storage as storage

USER = bytes.fromhex("01020000000000051500000064000000")
OTHER = bytes.fromhex("01020000000000051500000065000000")
EVERYONE = bytes.fromhex("010100000000000100000000")
ROOT = "C:\\Users\\Synthetic\\Stage"


def private(index=4, *, directory=True):
    return storage.Snapshot((1, 0, index), storage.DIRECTORY if directory else 0x20, 1, USER,
                            storage.DACL_PRESENT | storage.DACL_PROTECTED,
                            (storage.Ace(0, 3 if directory else 16, storage.FILE_ALL_ACCESS, USER),), "a" * 64)


def parent(index):
    return storage.Snapshot((1, 0, index), storage.DIRECTORY, 1, storage.SYSTEM_SID, storage.DACL_PRESENT,
                            (storage.Ace(0, 3, storage.FILE_ALL_ACCESS, USER),
                             storage.Ace(0, 0, 0x80000000, EVERYONE)), "b" * 64)


class MockNative:
    def __init__(self, *, exists=True):
        self.exists, self.opened, self.closed, self.created = exists, [], [], []
        self.snapshots, self.token = {}, USER
        self.writer_identity = None

    def token_user(self):
        return self.token

    def open_directory(self, path):
        if path == ROOT and not self.exists:
            raise storage.PrivateStorageError("mock-not-found")
        handle = len(self.opened) + 1
        self.opened.append((path, handle))
        self.snapshots.setdefault(handle, private() if path == ROOT else parent(handle))
        return handle

    def create_private_directory(self, path, user):
        assert path == ROOT and user == USER
        if self.exists:
            raise storage.PrivateStorageError("mock-already-exists")
        self.created.append(path)
        self.exists = True

    def open_file(self, path):
        handle = len(self.opened) + 1
        self.opened.append((path, handle))
        self.snapshots[handle] = private(5, directory=False)
        return handle

    def snapshot(self, handle):
        return self.snapshots[handle]

    def identity(self, _handle):
        snapshot = private(5, directory=False)
        return self.writer_identity or (snapshot.identity, snapshot.attributes, snapshot.links)

    def close(self, handle):
        self.closed.append(handle)


def test_actual_guard_orders_parent_checks_exclusive_creation_and_prewrite_file_check():
    native = MockNative(exists=False)
    with storage.private_stage_guard(ROOT, create=True, _native=native) as guard:
        assert native.created == [ROOT] and native.closed == []
        with guard.private_file(99, ROOT + "\\.transaction.json.partial"):
            assert len(native.opened) == 5
        assert native.closed == [5]
    assert native.closed == [5, 4, 3, 2, 1]


def test_existing_root_is_verified_and_never_rewritten():
    native = MockNative()
    with storage.private_stage_guard(ROOT, _native=native):
        assert native.created == []
    assert native.closed == [4, 3, 2, 1]


def test_create_refusal_retains_existing_root_and_releases_every_parent():
    native = MockNative()
    with pytest.raises(storage.PrivateStorageError, match="mock-already-exists"):
        with storage.private_stage_guard(ROOT, create=True, _native=native):
            pytest.fail("existing root accepted for creation")
    assert native.created == [] and native.closed == [3, 2, 1]


@pytest.mark.parametrize("mask", [2, 4, 16, 64, 256, 0x10000, 0x40000, 0x80000, 0x40000000, 0x10000000])
def test_parent_rejects_other_allow_write_even_with_preceding_deny(mask):
    observed = replace(parent(1), aces=(storage.Ace(1, 0, mask, OTHER), storage.Ace(0, 0, mask, OTHER)))
    with pytest.raises(storage.PrivateStorageError, match="untrusted-parent-write-access"):
        storage.require_parent(observed, USER)


def test_parent_read_traverse_grants_do_not_grant_mutation():
    storage.require_parent(parent(1), USER)
    storage.require_parent(replace(parent(1), aces=(storage.Ace(0, 8, storage.FILE_ALL_ACCESS, OTHER),)), USER)


@pytest.mark.parametrize("defect", ["owner", "broad", "unprotected", "inherited", "inherit-only", "null", "reparse", "hardlink", "callback", "unknown-mask"])
def test_private_guard_refuses_unqualified_descriptor_before_payload(defect):
    observed = private()
    if defect == "owner":
        observed = replace(observed, owner=OTHER)
    elif defect == "broad":
        observed = replace(observed, aces=(*observed.aces, storage.Ace(0, 0, 0x80000000, OTHER)))
    elif defect == "unprotected":
        observed = replace(observed, control=storage.DACL_PRESENT)
    elif defect in ("inherited", "inherit-only"):
        observed = replace(observed, aces=(replace(observed.aces[0], flags=19 if defect == "inherited" else 11),))
    elif defect == "null":
        observed = replace(observed, aces=())
    elif defect == "reparse":
        observed = replace(observed, attributes=storage.DIRECTORY | storage.REPARSE)
    elif defect == "hardlink":
        observed = replace(observed, links=2)
    elif defect == "callback":
        observed = replace(observed, aces=(replace(observed.aces[0], kind=9),))
    else:
        observed = replace(observed, aces=(replace(observed.aces[0], mask=0x02000000),))
    with pytest.raises(storage.PrivateStorageError):
        storage.require_private(observed, USER, directory=True)


def test_bad_parent_refuses_before_new_private_directory_creation():
    class BadParent(MockNative):
        def snapshot(self, handle):
            result = super().snapshot(handle)
            return replace(result, owner=OTHER) if handle == 2 else result

    native = BadParent(exists=False)
    with pytest.raises(storage.PrivateStorageError, match="unqualified-parent-owner"):
        with storage.private_stage_guard(ROOT, create=True, _native=native):
            pytest.fail("unsafe parent accepted")
    assert native.created == [] and native.closed == [2, 1]


@pytest.mark.parametrize("path", ["C:relative", "\\\\server\\share\\stage", "\\\\?\\C:\\stage", "C:\\safe\\..\\stage",
                               "C:\\safe\\CON", "C:\\stage:stream", "C:\\stage.", "C:\\stage "])
def test_alias_remote_device_and_alternate_stream_paths_refused(path):
    with pytest.raises(storage.PrivateStorageError):
        storage._ancestors(path)


def test_pre_payload_writer_handle_must_match_retained_named_file():
    native = MockNative()
    native.writer_identity = ((1, 0, 999), 0x20, 1)
    with storage.private_stage_guard(ROOT, _native=native) as guard:
        with pytest.raises(storage.PrivateStorageError, match="private-writer-handle-mismatch"):
            with guard.private_file(99, ROOT + "\\private.tmp"):
                pytest.fail("wrong writer handle accepted")
    assert native.closed == [5, 4, 3, 2, 1]


def test_different_or_unicode_casefold_parent_is_not_a_containment_proof():
    native = MockNative()
    with storage.private_stage_guard(ROOT, _native=native) as guard:
        for path in ("C:\\Users\\Synthetic\\Other\\private.tmp", "C:\\Users\\synthetic\\Stage\\private.tmp"):
            with pytest.raises(storage.PrivateStorageError, match="private-child-containment-refused"):
                with guard.private_file(99, path):
                    pytest.fail("different lexical parent accepted")
    assert native.closed == [4, 3, 2, 1]


def test_postwrite_descriptor_change_refuses_success_and_closes_owned_handles():
    native = MockNative()
    with pytest.raises(storage.PrivateStorageError, match="native-private-boundary-changed"):
        with storage.private_stage_guard(ROOT, _native=native):
            native.snapshots[4] = replace(native.snapshots[4], descriptor_sha256="c" * 64)
    assert native.closed == [4, 3, 2, 1]


def test_token_scope_change_refuses_success_and_releases_handles():
    native = MockNative()
    with pytest.raises(storage.PrivateStorageError, match="native-token-changed"):
        with storage.private_stage_guard(ROOT, _native=native):
            native.token = OTHER
    assert native.closed == [4, 3, 2, 1]


def test_failed_handle_close_does_not_skip_other_owned_handles():
    class BadClose(MockNative):
        def close(self, handle):
            super().close(handle)
            if handle == 4:
                raise storage.PrivateStorageError("mock-close-failed")

    native = BadClose()
    with pytest.raises(storage.PrivateStorageError, match="native-handle-cleanup-refused"):
        with storage.private_stage_guard(ROOT, _native=native):
            pass
    assert native.closed == [4, 3, 2, 1]

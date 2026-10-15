"""Candidate policy fixtures using inert providers, never Win32 or credentials.

These describe selected-edge, missing-name and exclusive-birth behavior. They
cannot establish genuine namespace/share/DACL custody or other-token denial.
"""
from dataclasses import replace

import pytest

from remote_ops_workspace import windows_private_storage as storage

USER = bytes.fromhex("01020000000000051500000064000000")
OTHER = bytes.fromhex("01020000000000051500000065000000")
EVERYONE = bytes.fromhex("010100000000000100000000")
TI = bytes.fromhex("010600000000000550000000b589fb381984c2cb5c6c236d5700776ec0026487")
ROOT = "C:\\"
PARENT = r"C:\Users\Synthetic"
HOME = PARENT + r"\Home"
STAGE = PARENT + r"\Stage"


def ordinary(index, *, owner=storage.SYSTEM_SID, mask=0):
    return storage.Snapshot(
        (1, 0, index), storage.DIRECTORY, 1, owner, storage.DACL_PRESENT,
        (storage.Ace(0, 3, storage.FILE_ALL_ACCESS, USER),
         storage.Ace(0, 0, mask, EVERYONE)), "a" * 64,
    )


def private(index):
    return storage.Snapshot(
        (1, 0, index), storage.DIRECTORY, 1, USER,
        storage.DACL_PRESENT | storage.DACL_PROTECTED,
        (storage.Ace(0, 3, storage.FILE_ALL_ACCESS, USER),), "b" * 64,
    )


class SelectedNative:
    def __init__(self, *, missing=(), root_owner=TI, root_mask=4):
        self.missing = set(missing)
        self.user = USER
        self.events, self.handles, self.closed = [], {}, []
        self.observed = {
            ROOT: ordinary(1, owner=root_owner, mask=root_mask),
            r"C:\Users": ordinary(2, mask=4),
            PARENT: ordinary(3), HOME: private(4), STAGE: private(5),
        }

    def token_user(self):
        return self.user

    def open_directory(self, path):
        self.events.append(("open", path))
        if path in self.missing:
            raise storage.PrivatePathMissing("native-directory-missing")
        handle = len(self.handles) + 1
        self.handles[handle] = path
        return handle

    def snapshot(self, handle):
        path = self.handles[handle]
        self.events.append(("snapshot", path))
        return self.observed[path]

    def create_private_directory(self, path, user):
        self.events.append(("create", path))
        assert user == USER
        if path not in self.missing:
            raise storage.PrivateStorageError("native-private-storage-refused")
        self.missing.remove(path)
        self.observed[path] = private(10)

    def close(self, handle):
        self.closed.append(handle)


def assert_closed(native):
    assert native.closed == list(reversed(native.handles))
    assert len(set(native.closed)) == len(native.closed)


@pytest.mark.parametrize("guard_name", ["private_home_guard", "private_stage_guard"])
@pytest.mark.parametrize("owner", [TI, storage.SYSTEM_SID, storage.ADMINISTRATORS_SID, USER])
def test_existing_successor_completes_creation_only_parent_before_use(guard_name, owner):
    native = SelectedNative(root_owner=owner)
    with getattr(storage, guard_name)(STAGE, _native=native) as guard:
        assert guard.path == STAGE and not native.closed
        guard.verify()
    assert not any(event[0] == "create" for event in native.events)
    assert_closed(native)


def test_root_owner_authority_does_not_change_standalone_strict_parent_policy():
    with pytest.raises(storage.PrivateStorageError, match="unqualified-parent-owner"):
        storage.require_parent(ordinary(1, owner=TI, mask=4), USER)
    with pytest.raises(storage.PrivateStorageError, match="untrusted-parent-write-access"):
        storage.require_parent(ordinary(1, mask=4), USER)


@pytest.mark.parametrize("mask", [2, 16, 64, 256, 0x10000, 0x40000, 0x80000, 0x10000000, 0x40000000])
@pytest.mark.parametrize("add_subdirectory", [0, 4])
def test_every_other_mutation_allow_refuses_before_next_child_or_creation(mask, add_subdirectory):
    native = SelectedNative(missing=(STAGE,), root_mask=mask | add_subdirectory)
    root = native.observed[ROOT]
    native.observed[ROOT] = replace(root, aces=(
        storage.Ace(1, 0, mask, OTHER), storage.Ace(0, 0, mask | add_subdirectory, OTHER),
    ))
    with pytest.raises(storage.PrivateStorageError, match="untrusted-parent-write-access"):
        with storage.private_stage_guard(STAGE, create_if_missing=True, _native=native):
            pytest.fail("mutation grant admitted")
    assert native.events == [("open", ROOT), ("snapshot", ROOT)]
    assert_closed(native)


def test_ti_owner_does_not_exempt_ti_trustee_security_allow():
    native = SelectedNative()
    native.observed[ROOT] = replace(native.observed[ROOT], aces=(storage.Ace(0, 0, 0x40000, TI),))
    with pytest.raises(storage.PrivateStorageError, match="untrusted-parent-write-access"):
        with storage.private_home_guard(HOME, _native=native):
            pytest.fail("TI trustee grant exempted")
    assert_closed(native)


def test_inherit_only_and_deny_aces_do_not_grant_current_parent_mutation():
    native = SelectedNative()
    native.observed[ROOT] = replace(native.observed[ROOT], aces=(
        storage.Ace(0, 8, storage.FILE_ALL_ACCESS, OTHER), storage.Ace(1, 0, 0x40000, OTHER),
    ))
    with storage.private_home_guard(HOME, _native=native):
        pass
    assert_closed(native)


@pytest.mark.parametrize("path,owner,code", [
    (ROOT, OTHER, "unqualified-parent-owner"),
    (r"C:\Users", TI, "unqualified-parent-owner"),
    (STAGE, TI, "private-owner-mismatch"),
])
def test_root_exception_does_not_admit_other_owner_lower_ti_or_private_ti(path, owner, code):
    native = SelectedNative()
    native.observed[path] = replace(native.observed[path], owner=owner)
    with pytest.raises(storage.PrivateStorageError, match=code):
        with storage.private_stage_guard(STAGE, _native=native):
            pytest.fail("incorrect owner role admitted")
    assert not any(event[0] == "create" for event in native.events)
    assert_closed(native)


def test_missing_home_keeps_safe_immediate_parent_and_does_not_create_it():
    native = SelectedNative(missing=(HOME,))
    with storage.private_home_guard(HOME, _native=native) as guard:
        assert guard.missing_path == HOME and guard.path == PARENT
        assert len(guard.opened) == 3
    assert not any(event[0] == "create" for event in native.events)
    assert_closed(native)


@pytest.mark.parametrize("missing,unsafe_parent", [(HOME, PARENT), (r"C:\Users", ROOT)])
def test_missing_edge_cannot_borrow_existing_successor_authority(missing, unsafe_parent):
    native = SelectedNative(missing=(missing,))
    native.observed[unsafe_parent] = replace(
        native.observed[unsafe_parent], aces=(storage.Ace(0, 0, 4, OTHER),),
    )
    with pytest.raises(storage.PrivateStorageError):
        with storage.private_home_guard(HOME, _native=native):
            pytest.fail("absent name treated as held successor")
    assert not any(event[0] == "create" for event in native.events)
    assert_closed(native)


def test_missing_home_name_arrival_refuses_and_releases_observation_handle():
    native = SelectedNative(missing=(HOME,))
    with pytest.raises(storage.PrivateStorageError, match="native-missing-boundary-changed"):
        with storage.private_home_guard(HOME, _native=native):
            native.missing.remove(HOME)
    assert_closed(native)


def test_missing_probe_token_change_refuses_before_yield():
    class ChangedToken(SelectedNative):
        def open_directory(self, path):
            if path == HOME and self.events.count(("open", HOME)) == 1:
                self.user = OTHER
            return super().open_directory(path)

    native = ChangedToken(missing=(HOME,))
    with pytest.raises(storage.PrivateStorageError, match="native-token-changed"):
        with storage.private_home_guard(HOME, _native=native):
            pytest.fail("changed token accepted")
    assert_closed(native)


@pytest.mark.parametrize("mode", ["create", "create_if_missing"])
def test_exclusive_creation_under_held_successor_precedes_private_use(mode):
    native = SelectedNative(missing=(STAGE,))
    native.observed[PARENT] = ordinary(3, mask=4)
    with storage.private_stage_guard(STAGE, **{mode: True}, _native=native) as guard:
        creation = native.events.index(("create", STAGE))
        assert ("snapshot", PARENT) in native.events[:creation]
        assert native.observed[STAGE] == guard.opened[-1][2]
    assert [event for event in native.events if event[0] == "create"] == [("create", STAGE)]
    assert_closed(native)


@pytest.mark.parametrize("mode", ["create", "create_if_missing"])
def test_missing_direct_ti_root_stage_refuses_before_creation(mode):
    direct = r"C:\Stage"
    native = SelectedNative(missing=(direct,))
    with pytest.raises(storage.PrivateStorageError, match="unqualified-parent-owner"):
        with storage.private_stage_guard(direct, **{mode: True}, _native=native):
            pytest.fail("planned child authorized TI root")
    assert not any(event[0] == "create" for event in native.events)
    assert_closed(native)


def test_missing_direct_original_trusted_root_can_create_private_stage():
    direct = r"C:\Stage"
    native = SelectedNative(missing=(direct,), root_owner=storage.SYSTEM_SID)
    with storage.private_stage_guard(direct, create_if_missing=True, _native=native):
        pass
    assert ("create", direct) in native.events
    assert_closed(native)


def test_existing_direct_ti_root_private_leaf_has_actual_held_successor():
    direct = r"C:\Stage"
    native = SelectedNative()
    native.observed[direct] = private(6)
    with storage.private_stage_guard(direct, _native=native):
        pass
    assert not any(event[0] == "create" for event in native.events)
    assert_closed(native)


@pytest.mark.parametrize("defect", ["descriptor", "token"])
def test_changes_during_absence_detection_refuse_before_exclusive_birth(defect):
    class ChangedParent(SelectedNative):
        def open_directory(self, path):
            if path == STAGE:
                if defect == "descriptor":
                    self.observed[PARENT] = replace(self.observed[PARENT], descriptor_sha256="c" * 64)
                else:
                    self.user = OTHER
            return super().open_directory(path)

    native = ChangedParent(missing=(STAGE,))
    with pytest.raises(storage.PrivateStorageError):
        with storage.private_stage_guard(STAGE, create_if_missing=True, _native=native):
            pytest.fail("changed ancestor created private child")
    assert not any(event[0] == "create" for event in native.events)
    assert_closed(native)


def test_precreator_wins_refuses_without_opening_or_adopting_its_leaf():
    class Precreator(SelectedNative):
        def create_private_directory(self, path, user):
            self.missing.remove(path)
            self.observed[path] = ordinary(9, owner=OTHER, mask=4)
            super().create_private_directory(path, user)

    native = Precreator(missing=(STAGE,))
    with pytest.raises(storage.PrivateStorageError, match="native-private-storage-refused"):
        with storage.private_stage_guard(STAGE, create_if_missing=True, _native=native):
            pytest.fail("precreator adopted")
    assert [event for event in native.events if event == ("open", STAGE)] == [("open", STAGE)]
    assert_closed(native)


def test_open_after_birth_failure_never_yields_or_retries_creation():
    class BirthOpenFailure(SelectedNative):
        def open_directory(self, path):
            if path == STAGE and ("create", STAGE) in self.events:
                raise storage.PrivateStorageError("native-directory-open-refused")
            return super().open_directory(path)

    native = BirthOpenFailure(missing=(STAGE,))
    with pytest.raises(storage.PrivateStorageError, match="native-directory-open-refused"):
        with storage.private_stage_guard(STAGE, create_if_missing=True, _native=native):
            pytest.fail("unopened birth used")
    assert native.events.count(("create", STAGE)) == 1
    assert_closed(native)


@pytest.mark.parametrize("mode", ["create", "create_if_missing"])
@pytest.mark.parametrize("failure_type", [MemoryError, OSError, KeyboardInterrupt, SystemExit])
def test_prebirth_snapshot_failure_releases_all_ancestors_without_creation(mode, failure_type):
    class PrebirthFailure(SelectedNative):
        def snapshot(self, handle):
            observed = super().snapshot(handle)
            if self.events.count(("snapshot", PARENT)) == 2:
                raise failure_type("synthetic prebirth refusal")
            return observed

    native = PrebirthFailure(missing=(STAGE,))
    with pytest.raises(failure_type, match="synthetic prebirth refusal"):
        with storage.private_stage_guard(STAGE, **{mode: True}, _native=native):
            pytest.fail("failed prebirth snapshot accepted")
    assert not any(event[0] == "create" for event in native.events)
    assert_closed(native)


@pytest.mark.parametrize("defect", ["private-owner", "broad-private", "reparse", "links", "volume", "duplicate"])
def test_created_child_must_bind_actual_private_descriptor_and_identity(defect):
    class BadBirth(SelectedNative):
        def create_private_directory(self, path, user):
            super().create_private_directory(path, user)
            observed = self.observed[path]
            changes = {
                "private-owner": {"owner": OTHER},
                "broad-private": {"aces": (*observed.aces, storage.Ace(0, 0, 0x80000000, OTHER))},
                "reparse": {"attributes": storage.DIRECTORY | storage.REPARSE},
                "links": {"links": 2}, "volume": {"identity": (2, 0, 10)},
                "duplicate": {"identity": (1, 0, 2)},
            }
            self.observed[path] = replace(observed, **changes[defect])

    native = BadBirth(missing=(STAGE,))
    with pytest.raises(storage.PrivateStorageError):
        with storage.private_stage_guard(STAGE, create_if_missing=True, _native=native):
            pytest.fail("unqualified born child used")
    assert_closed(native)


@pytest.mark.parametrize("defect", ["handle", "snapshot", "path", "role", "duplicate", "volume", "root", "missing-path"])
def test_each_verify_revalidates_held_edge_roles_and_exact_chain(defect):
    native = SelectedNative()
    with storage.private_home_guard(HOME, _native=native) as guard:
        rows = [list(row) for row in guard.opened]
        missing = None
        if defect == "handle":
            rows[1][1] = None
        elif defect == "snapshot":
            rows[1][2] = None
        elif defect == "path":
            rows[1][0] = r"C:\Other\Users"
        elif defect == "role":
            rows[1][3] = True
        elif defect in ("duplicate", "volume"):
            identity = rows[0][2].identity if defect == "duplicate" else (2, 0, 2)
            rows[1][2] = replace(rows[1][2], identity=identity)
        elif defect == "root":
            rows[0][0] = "c:\\"
        else:
            rows = rows[:-1]
            missing = r"C:\Other\Home"
        altered = storage.PrivateDirectoryGuard(native, USER, rows, missing_path=missing)
        with pytest.raises(storage.PrivateStorageError, match="native-held-edge-refused"):
            altered.verify()
    assert_closed(native)


@pytest.mark.parametrize("tail,count", [("unknown", 1), ("private", 0), ("private", 65)])
def test_invalid_or_unbounded_chain_is_refused_before_native_observation(tail, count):
    native = SelectedNative()
    rows = [[ROOT, 1, ordinary(1), False] for _ in range(count)]
    with pytest.raises(storage.PrivateStorageError, match="native-held-edge-refused"):
        storage._verify_directory_chain(native, USER, rows, tail=tail)
    assert native.events == []


def test_token_change_during_snapshot_readback_refuses_before_yield():
    class LateToken(SelectedNative):
        def snapshot(self, handle):
            observed = super().snapshot(handle)
            if self.events.count(("snapshot", STAGE)) == 2:
                self.user = OTHER
            return observed

    native = LateToken()
    with pytest.raises(storage.PrivateStorageError, match="native-token-changed"):
        with storage.private_stage_guard(STAGE, _native=native):
            pytest.fail("token drift during edge readback accepted")
    assert_closed(native)


@pytest.mark.parametrize("where", [ROOT, r"C:\Users", PARENT, STAGE])
def test_descriptor_changes_during_use_refuse_and_close_all_registered_handles(where):
    native = SelectedNative()
    with pytest.raises(storage.PrivateStorageError, match="native-private-boundary-changed"):
        with storage.private_stage_guard(STAGE, _native=native):
            native.observed[where] = replace(native.observed[where], descriptor_sha256="d" * 64)
    assert_closed(native)

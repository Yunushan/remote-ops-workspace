"""Pure provider tests: private-home cleanup refuses success but attempts every close."""
import pytest

from remote_ops_workspace import windows_private_storage as storage

USER = bytes.fromhex("01020000000000051500000064000000")
EVERYONE = bytes.fromhex("010100000000000100000000")
HOME = "C:\\Users\\Synthetic\\Home"


class HomeNative:
    def __init__(self, *, failed_handle=None, error_type=OSError):
        self.failed_handle, self.error_type = failed_handle, error_type
        self.opened, self.closed, self.snapshots = [], [], {}

    def token_user(self):
        return USER

    def open_directory(self, path):
        handle = len(self.opened) + 1
        self.opened.append((path, handle))
        private = path == HOME
        self.snapshots[handle] = storage.Snapshot(
            (1, 0, handle), storage.DIRECTORY, 1, USER if private else storage.SYSTEM_SID,
            storage.DACL_PRESENT | (storage.DACL_PROTECTED if private else 0),
            (storage.Ace(0, 3, storage.FILE_ALL_ACCESS, USER),) if private else (
                storage.Ace(0, 3, storage.FILE_ALL_ACCESS, USER), storage.Ace(0, 0, 0x80000000, EVERYONE)),
            ("a" if private else "b") * 64,
        )
        return handle

    def snapshot(self, handle):
        return self.snapshots[handle]

    def close(self, handle):
        self.closed.append(handle)
        if handle == self.failed_handle:
            raise self.error_type("synthetic private close detail")


@pytest.mark.parametrize("error_type", [OSError, storage.PrivateStorageError])
@pytest.mark.parametrize("failed_handle", [4, 2])
def test_home_cleanup_failure_refuses_success_and_attempts_remaining_ancestors(error_type, failed_handle):
    native = HomeNative(failed_handle=failed_handle, error_type=error_type)
    entered = []
    with pytest.raises(storage.PrivateStorageError, match="^native-handle-cleanup-refused$"):
        with storage.private_home_guard(HOME, _native=native) as guard:
            entered.append(guard.path)
            assert native.closed == []
    assert entered == [HOME]
    assert [path for path, _handle in native.opened] == ["C:\\", "C:\\Users", "C:\\Users\\Synthetic", HOME]
    assert native.closed == [4, 3, 2, 1]


def test_home_success_closes_each_retained_handle_once():
    native = HomeNative()
    with storage.private_home_guard(HOME, _native=native) as guard:
        assert guard.path == HOME and native.closed == []
    assert native.closed == [4, 3, 2, 1]

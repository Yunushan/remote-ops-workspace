from __future__ import annotations

import ctypes
import stat
from pathlib import Path
from types import SimpleNamespace

import pytest

import remote_ops_workspace.enterprise_policy as policy
import remote_ops_workspace.file_safety as file_safety
import remote_ops_workspace.layouts as layouts
import remote_ops_workspace.moba_text as moba_text
import remote_ops_workspace.profile_sharing as sharing
import remote_ops_workspace.state_lock as state_lock
import remote_ops_workspace.team_sync as team_sync
from remote_ops_workspace.layouts import Layout, LayoutPane, LayoutStore
from remote_ops_workspace.models import Profile
from remote_ops_workspace.profile_sharing import public_profile_dict


def _status(
    mode: int,
    *,
    dev: int = 1,
    ino: int = 1,
    gid: int = 1,
    uid: int = 0,
    size: int = 0,
    attributes: int = 0,
) -> SimpleNamespace:
    return SimpleNamespace(
        st_mode=mode,
        st_dev=dev,
        st_ino=ino,
        st_gid=gid,
        st_uid=uid,
        st_size=size,
        st_file_attributes=attributes,
    )


def _module_copy(module: object, **overrides: object) -> SimpleNamespace:
    """Copy a stdlib module before changing platform markers in a test.

    Mutating ``os.name`` on the real module changes pathlib's process-wide
    platform selection and can corrupt pytest's own teardown on POSIX hosts.
    A shallow module copy keeps platform-branch tests isolated while retaining
    the real stdlib functions and constants.
    """

    values = dict(vars(module))
    values.update(overrides)
    return SimpleNamespace(**values)


def test_enterprise_policy_platform_and_fail_closed_edges(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_windows_common_app_data = policy._windows_common_app_data
    policy_os = policy.os
    policy_sys = policy.sys
    monkeypatch.setattr(policy, "os", _module_copy(policy_os, name="nt"))
    monkeypatch.setattr(policy, "_windows_common_app_data", lambda: tmp_path / "common")
    assert policy.machine_enterprise_policy_path() == (
        tmp_path / "common" / "RemoteOpsWorkspace" / "policy.json"
    )

    monkeypatch.setattr(policy, "os", _module_copy(policy_os, name="posix", getuid=lambda: 0))
    monkeypatch.setattr(policy, "sys", _module_copy(policy_sys, platform="darwin"))
    assert policy.machine_enterprise_policy_path() == Path(
        "/Library/Application Support/RemoteOpsWorkspace/policy.json"
    )
    policy.sys.platform = "linux"
    assert policy.machine_enterprise_policy_path() == Path(
        "/etc/remote-ops-workspace/policy.json"
    )

    class Missing:
        def lstat(self) -> None:
            raise FileNotFoundError

    class Inaccessible:
        def lstat(self) -> None:
            raise OSError("permission denied")

    assert policy._path_entry_exists(Missing()) is False  # type: ignore[arg-type]
    assert policy._path_entry_exists(Inaccessible()) is True  # type: ignore[arg-type]

    class Unresolvable:
        def resolve(self, *, strict: bool = False) -> Path:
            del strict
            raise OSError("unavailable")

    assert policy._same_path(Unresolvable(), Path("other")) is False  # type: ignore[arg-type]
    assert policy._flatten_settings(
        {"options": {"keepalive": 30}, "metadata": {"owner": "ops"}}
    ) == {
        "options.keepalive": "30",
        "keepalive": "30",
        "metadata.owner": "ops",
    }

    class PolicyPath:
        def __init__(self, status: SimpleNamespace) -> None:
            self.status = status

        def stat(self) -> SimpleNamespace:
            return self.status

        def __str__(self) -> str:
            return "machine-policy"

    assert policy._require_machine_policy_permissions(
        PolicyPath(_status(stat.S_IFREG | 0o640, uid=0))  # type: ignore[arg-type]
    ) is True
    with pytest.raises(ValueError, match="group/world writable"):
        policy._require_machine_policy_permissions(
            PolicyPath(_status(stat.S_IFREG | 0o660, uid=0))  # type: ignore[arg-type]
        )
    with pytest.raises(ValueError, match="owned by root"):
        policy._require_machine_policy_permissions(
            PolicyPath(_status(stat.S_IFREG | 0o640, uid=1000))  # type: ignore[arg-type]
        )

    monkeypatch.setattr(policy, "_windows_common_app_data", original_windows_common_app_data)
    policy.os.name = "posix"
    with pytest.raises(RuntimeError, match="only available on Windows"):
        policy._windows_common_app_data()
    policy.os.name = "nt"
    fake_shell = SimpleNamespace(
        shell32=SimpleNamespace(
            SHGetFolderPathW=lambda *_args: 1,
        )
    )
    monkeypatch.setattr(ctypes, "windll", fake_shell, raising=False)
    with pytest.raises(OSError, match="unable to resolve"):
        policy._windows_common_app_data()

    def fill_common_data(_shell, _csidl, _token, _flags, buffer) -> int:
        buffer.value = r"C:\ProgramData"
        return 0

    monkeypatch.setattr(
        ctypes,
        "windll",
        SimpleNamespace(shell32=SimpleNamespace(SHGetFolderPathW=fill_common_data)),
        raising=False,
    )
    assert policy._windows_common_app_data() == Path(r"C:\ProgramData")

    link_status = _status(stat.S_IFLNK)
    monkeypatch.setattr(policy.Path, "lstat", lambda _path: link_status)
    with pytest.raises(ValueError, match="must not be a symbolic link"):
        policy.load_enterprise_policy(tmp_path / "linked-policy.json")


def test_file_safety_validation_and_append_edges(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file_safety_os = _module_copy(file_safety.os, name="posix")
    monkeypatch.setattr(file_safety, "os", file_safety_os)

    class NonDirectory:
        def mkdir(self, *, parents: bool, exist_ok: bool) -> None:
            del parents, exist_ok

        def is_dir(self) -> bool:
            return False

        def __str__(self) -> str:
            return "not-a-directory"

    monkeypatch.setattr(file_safety, "_require_no_linked_path_components", lambda _path: None)
    with pytest.raises(OSError, match="must be a directory"):
        file_safety.ensure_private_dir_required(NonDirectory())  # type: ignore[arg-type]

    class MissingShared:
        def lstat(self) -> None:
            raise FileNotFoundError

        def __str__(self) -> str:
            return "missing-shared"

    with pytest.raises(OSError, match="pre-provisioned"):
        file_safety.ensure_shared_dir(MissingShared())  # type: ignore[arg-type]
    with pytest.raises(OSError, match="symbolic link"):
        file_safety.require_shared_dir_metadata(
            Path("link"), _status(stat.S_IFLNK)
        )
    with pytest.raises(OSError, match="must be a directory"):
        file_safety.require_shared_dir_metadata(
            Path("file"), _status(stat.S_IFREG)
        )
    with pytest.raises(OSError, match="setgid"):
        file_safety.require_shared_dir_metadata(
            Path("insecure"), _status(stat.S_IFDIR | 0o755)
        )
    file_safety.require_shared_dir_metadata(
        Path("shared"), _status(stat.S_IFDIR | file_safety.SHARED_DIR_MODE)
    )

    file_safety.os.name = "nt"
    path = tmp_path / "audit" / "events.jsonl"
    monkeypatch.setattr(file_safety, "ensure_private_dir_required", lambda _path: None)
    monkeypatch.setattr(file_safety, "_path_is_link_or_reparse", lambda _path: True)
    with pytest.raises(OSError, match="symlinked private artifact"):
        file_safety.append_jsonl_private(path, {"event": "blocked"})

    monkeypatch.setattr(file_safety, "_path_is_link_or_reparse", lambda _path: False)
    monkeypatch.setattr(file_safety.os, "open", lambda *_args, **_kwargs: 41)
    monkeypatch.setattr(file_safety, "_require_open_path_identity", lambda *_args: None)
    monkeypatch.setattr(file_safety.os, "write", lambda *_args: 0)
    monkeypatch.setattr(file_safety.os, "fsync", lambda _fd: None)
    monkeypatch.setattr(file_safety.os, "close", lambda _fd: None)
    monkeypatch.setattr(file_safety, "_chmod_required", lambda *_args: None)
    monkeypatch.delattr(file_safety.os, "O_BINARY", raising=False)
    monkeypatch.delattr(file_safety.os, "fchmod", raising=False)
    monkeypatch.setattr(file_safety.os, "O_NOFOLLOW", 0, raising=False)
    with pytest.raises(OSError, match="short private audit append"):
        file_safety.append_jsonl_private(path, {"event": "short"})


def test_file_safety_shared_atomic_and_metadata_edges(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    file_safety_os = _module_copy(file_safety.os, name="posix")
    monkeypatch.setattr(file_safety, "os", file_safety_os)

    original_guard = file_safety._require_replaceable_shared_target
    original_metadata = file_safety.require_shared_file_metadata
    shared = tmp_path / "shared"
    shared.mkdir()
    target = shared / "record.json"
    monkeypatch.setattr(file_safety, "ensure_shared_dir", lambda _path: None)
    monkeypatch.setattr(file_safety, "_require_replaceable_shared_target", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(file_safety, "_chmod_required", lambda *_args: None)
    monkeypatch.setattr(file_safety, "require_shared_file_metadata", lambda *_args: None)
    monkeypatch.setattr(file_safety, "require_shared_dir_metadata", lambda *_args: None)
    file_safety.write_json_shared_atomic(target, {"ok": True})
    assert target.exists()

    original_stat = file_safety.Path.stat
    calls = 0

    def changed_parent_stat(path: Path, *args, **kwargs):
        nonlocal calls
        if path == shared:
            calls += 1
            status = original_stat(path, *args, **kwargs)
            if calls >= 2:
                return _status(
                    status.st_mode,
                    dev=status.st_dev + 1,
                    ino=status.st_ino,
                    gid=getattr(status, "st_gid", 0),
                    size=getattr(status, "st_size", 0),
                )
        return original_stat(path, *args, **kwargs)

    monkeypatch.setattr(file_safety.Path, "stat", changed_parent_stat)
    with pytest.raises(OSError, match="directory changed"):
        file_safety.write_json_shared_atomic(shared / "changed.json", {"changed": True})

    monkeypatch.setattr(file_safety.Path, "stat", original_stat)
    guard_calls = 0

    def fail_on_second_guard(*_args, **_kwargs) -> None:
        nonlocal guard_calls
        guard_calls += 1
        if guard_calls == 2:
            raise OSError("target changed")

    monkeypatch.setattr(file_safety, "_require_replaceable_shared_target", fail_on_second_guard)
    file_safety.os.name = "nt"
    with pytest.raises(OSError, match="target changed"):
        file_safety.write_json_shared_atomic(shared / "cleanup.json", {"cleanup": True})
    assert not list(shared.glob(".cleanup.json.*.tmp"))

    guard_calls = 0

    def fail_on_second_guard_with_cleanup_error(*_args, **_kwargs) -> None:
        nonlocal guard_calls
        guard_calls += 1
        if guard_calls == 2:
            raise OSError("target changed")

    original_unlink = file_safety.Path.unlink
    monkeypatch.setattr(
        file_safety,
        "_require_replaceable_shared_target",
        fail_on_second_guard_with_cleanup_error,
    )
    monkeypatch.setattr(
        file_safety.Path,
        "unlink",
        lambda path, *args, **kwargs: (
            (_ for _ in ()).throw(OSError("cleanup denied"))
            if path.parent == shared and path.name.startswith(".cleanup-fail.json.")
            else original_unlink(path, *args, **kwargs)
        ),
    )
    with pytest.raises(OSError, match="target changed"):
        file_safety.write_json_shared_atomic(
            shared / "cleanup-fail.json", {"cleanup": True}
        )
    monkeypatch.setattr(file_safety.Path, "unlink", original_unlink)
    for leftover in shared.glob(".cleanup-fail.json.*.tmp"):
        leftover.unlink()
    monkeypatch.setattr(file_safety, "_require_replaceable_shared_target", original_guard)
    monkeypatch.setattr(file_safety, "require_shared_file_metadata", original_metadata)

    class FakePath:
        def __init__(self, status: SimpleNamespace) -> None:
            self.status = status

        def lstat(self) -> SimpleNamespace:
            return self.status

        def __str__(self) -> str:
            return "shared-target"

    with pytest.raises(OSError, match="symlinked shared artifact"):
        file_safety._require_replaceable_shared_target(
            FakePath(_status(stat.S_IFLNK))  # type: ignore[arg-type]
        )
    with pytest.raises(OSError, match="regular file"):
        file_safety._require_replaceable_shared_target(
            FakePath(_status(stat.S_IFDIR))  # type: ignore[arg-type]
        )

    checked: list[tuple[object, ...]] = []
    monkeypatch.setattr(file_safety, "require_shared_file_metadata", lambda *args: checked.append(args))
    file_safety._require_replaceable_shared_target(
        FakePath(_status(stat.S_IFREG)),
        parent_status=_status(stat.S_IFDIR | file_safety.SHARED_DIR_MODE),
    )  # type: ignore[arg-type]
    assert checked
    file_safety._require_replaceable_shared_target(
        FakePath(_status(stat.S_IFREG))
    )  # type: ignore[arg-type]

    monkeypatch.setattr(file_safety, "require_shared_file_metadata", original_metadata)
    file_safety.os.name = "posix"
    good_parent = _status(stat.S_IFDIR | file_safety.SHARED_DIR_MODE, gid=7)
    with pytest.raises(OSError, match="permissions must be"):
        file_safety.require_shared_file_metadata(
            Path("bad-mode"), _status(stat.S_IFREG | 0o600, gid=7), good_parent
        )
    with pytest.raises(OSError, match="group must match"):
        file_safety.require_shared_file_metadata(
            Path("bad-group"), _status(stat.S_IFREG | file_safety.SHARED_FILE_MODE, gid=8), good_parent
        )
    file_safety.require_shared_file_metadata(
        Path("good"), _status(stat.S_IFREG | file_safety.SHARED_FILE_MODE, gid=7), good_parent
    )


def test_file_safety_linked_ancestors_and_open_identity_edges(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ancestor = tmp_path / "ancestor"
    target = ancestor / "secret.json"
    link_status = _status(stat.S_IFLNK)
    regular_status = _status(stat.S_IFREG)

    def linked_lstat(path: Path):
        if path == ancestor:
            return link_status
        raise FileNotFoundError

    monkeypatch.setattr(file_safety.Path, "lstat", linked_lstat)
    with pytest.raises(OSError, match="linked private directory ancestor"):
        file_safety._require_no_linked_path_components(target)

    monkeypatch.setattr(
        file_safety.Path,
        "lstat",
        lambda path: regular_status if path == ancestor else (_ for _ in ()).throw(FileNotFoundError),
    )
    with pytest.raises(OSError, match="ancestor must be a directory"):
        file_safety._require_no_linked_path_components(target)

    class IdentityPath:
        def __init__(self, status: SimpleNamespace) -> None:
            self.status = status

        def stat(self, *, follow_symlinks: bool = False) -> SimpleNamespace:
            del follow_symlinks
            return self.status

        def __str__(self) -> str:
            return "audit-record"

    monkeypatch.setattr(file_safety.os, "fstat", lambda _fd: _status(stat.S_IFREG, dev=1, ino=2))
    with pytest.raises(OSError, match="symlinked private artifact"):
        file_safety._require_open_path_identity(
            IdentityPath(_status(stat.S_IFLNK, dev=1, ino=2)), 3  # type: ignore[arg-type]
        )
    monkeypatch.setattr(file_safety.os, "fstat", lambda _fd: _status(stat.S_IFDIR, dev=1, ino=2))
    with pytest.raises(OSError, match="regular file"):
        file_safety._require_open_path_identity(
            IdentityPath(_status(stat.S_IFREG, dev=1, ino=2)), 3  # type: ignore[arg-type]
        )

    monkeypatch.setattr(file_safety.os, "fstat", lambda _fd: _status(stat.S_IFREG, dev=1, ino=3))
    with pytest.raises(OSError, match="changed while opening"):
        file_safety._require_open_path_identity(
            IdentityPath(_status(stat.S_IFREG, dev=1, ino=2)), 3  # type: ignore[arg-type]
        )


def test_layout_store_replace_and_missing_session_edges(tmp_path: Path) -> None:
    store = LayoutStore(tmp_path / "layouts.json")
    first = Layout(name="first", panes=[LayoutPane(command="true")])
    second = Layout(name="second", panes=[LayoutPane(command="false")])
    store.add(first)
    store.add(second)
    renamed = Layout(
        name="renamed",
        orientation="horizontal",
        panes=[LayoutPane(command="whoami"), LayoutPane(command="hostname")],
    )
    assert store.replace_named("first", renamed) == renamed
    with pytest.raises(KeyError, match="missing"):
        store.replace_named("missing", renamed)
    with pytest.raises(ValueError, match="already exists"):
        store.replace_named("renamed", second)

    assert store.update_splitter_sizes("missing", [[100, 100]]) is False
    assert store.update_splitter_sizes("renamed", [[100, 100]]) is True
    assert store.update_splitter_sizes("renamed", [[100, 100]]) is False

    class EmptyStore:
        def load(self) -> list[Profile]:
            return []

    with pytest.raises(KeyError, match="missing-profile"):
        layouts.build_layout_terminal_sessions(
            Layout(name="missing", panes=[LayoutPane(profile="missing-profile")]),
            EmptyStore(),  # type: ignore[arg-type]
        )


def test_managed_edit_cache_rejects_symlink_root_and_targets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / moba_text.MANAGED_EDIT_CACHE_DIR
    root.mkdir()
    monkeypatch.setattr(moba_text, "ensure_data_dir", lambda: tmp_path)
    monkeypatch.setattr(moba_text, "ensure_private_dir_required", lambda _path: None)
    original_is_symlink = moba_text.Path.is_symlink

    monkeypatch.setattr(
        moba_text.Path,
        "is_symlink",
        lambda path: path == root or original_is_symlink(path),
    )
    with pytest.raises(OSError, match="symlinked remote edit cache"):
        moba_text.prepare_managed_edit_cache(root / "one.edit")

    monkeypatch.setattr(
        moba_text.Path,
        "is_symlink",
        lambda path: original_is_symlink(path),
    )
    symlink_target = root / "symlink.edit"
    monkeypatch.setattr(
        moba_text.Path,
        "is_symlink",
        lambda path: path == symlink_target or original_is_symlink(path),
    )
    with pytest.raises(OSError, match="symlinked remote edit cache file"):
        moba_text.prepare_managed_edit_cache(symlink_target)

    directory_target = root / "directory.edit"
    directory_target.mkdir()
    monkeypatch.setattr(
        moba_text.Path,
        "is_symlink",
        lambda path: original_is_symlink(path),
    )
    with pytest.raises(OSError, match="must be a regular file"):
        moba_text.prepare_managed_edit_cache(directory_target)


def test_profile_sharing_ingress_schema_and_policy_edges(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    profile = Profile(name="edge", protocol="ssh", host="edge.example.invalid")
    base = public_profile_dict(profile)
    assert sharing.sanitize_shared_url("https://example.invalid:bad") is None
    assert sharing.profile_is_shareable(Profile(name="ica", protocol="ica")) is False

    inherited = sharing.inherited_local_capabilities(
        Profile(name="edge", protocol="ssh", host="edge.example.invalid", group="ops", options={"explicit": "yes"}),
        {
            "ops": {
                "options": {
                    "explicit": "inherited-but-overridden",
                    "proxy_jump": "bastion.example.invalid",
                    "keepalive_interval": "30",
                    "empty": "",
                }
            }
        },
    )
    assert inherited == ("options.proxy_jump",)
    assert sharing.inherited_local_capabilities(profile, {"default": {"options": []}}) == ()

    class FalseList(list):
        def __bool__(self) -> bool:
            return False

    def expect_invalid(mutation: dict[str, object], message: str) -> None:
        data = dict(base)
        data["options"] = dict(base["options"])
        data.update(mutation)
        with pytest.raises(ValueError, match=message):
            sharing.shared_profile_from_dict(data)

    with pytest.raises(ValueError, match="JSON object"):
        sharing.shared_profile_from_dict([])
    with pytest.raises(ValueError, match="string keys"):
        sharing.shared_profile_from_dict({1: "bad"})
    expect_invalid({"extra": True}, "schema mismatch")
    missing_host = dict(base)
    missing_host.pop("host")
    with pytest.raises(ValueError, match="missing fields"):
        sharing.shared_profile_from_dict(missing_host)
    expect_invalid({"name": 1}, "name must be text")
    expect_invalid({"host": 1}, "host must be text")
    expect_invalid({"port": 0}, "port must be an integer")
    expect_invalid({"tags": [1]}, "tags must be an array")
    expect_invalid({"options": {"keepalive": 1}}, "options must be a string")
    expect_invalid({"tunnels": {}}, "tunnels must be an array")
    expect_invalid({"tunnels": [{"bad": True}]}, "must not contain port forwards")
    expect_invalid({"tunnels": FalseList([{}])}, "exact public tunnel schema")
    empty_false_list = dict(base)
    empty_false_list["tunnels"] = FalseList()
    assert sharing.shared_profile_from_dict(empty_false_list).name == "edge"
    valid_tunnel = {
        "mode": "local",
        "local_host": "127.0.0.1",
        "local_port": 2200,
        "remote_host": "edge.example.invalid",
        "remote_port": 22,
    }
    valid_false_list = dict(base)
    valid_false_list["tunnels"] = FalseList([valid_tunnel, dict(valid_tunnel)])
    with pytest.raises(ValueError, match="not canonical"):
        sharing.shared_profile_from_dict(valid_false_list)
    expect_invalid({"host": None}, "shared profile is invalid")

    ica_data = dict(base)
    ica_data["protocol"] = "ica"
    ica_data["host"] = None
    ica_data["url"] = None
    monkeypatch.setattr(
        sharing,
        "prepare_profile",
        lambda _profile: Profile(name="ica", protocol="ica"),
    )
    with pytest.raises(ValueError, match="local or executable"):
        sharing.shared_profile_from_dict(ica_data)

    monkeypatch.setattr(
        sharing,
        "prepare_profile",
        lambda _profile: Profile(
            name="password=secret",
            protocol="ssh",
            host="edge.example.invalid",
        ),
    )
    with pytest.raises(ValueError, match="secret-bearing public fields"):
        sharing.shared_profile_from_dict(base)

    monkeypatch.setattr(
        sharing,
        "prepare_profile",
        lambda _profile: Profile(
            name="edge",
            protocol="ssh",
            host="other.example.invalid",
        ),
    )
    with pytest.raises(ValueError, match="not canonical"):
        sharing.shared_profile_from_dict(base)


def test_state_lock_open_and_fork_defensive_edges(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    state_lock_os = _module_copy(state_lock.os)
    monkeypatch.setattr(state_lock, "os", state_lock_os)

    class Parent:
        def __init__(self, statuses: list[SimpleNamespace]) -> None:
            self.statuses = iter(statuses)

        def stat(self, *, follow_symlinks: bool = False) -> SimpleNamespace:
            del follow_symlinks
            return next(self.statuses)

    class LockPath:
        def __init__(self, parent: Parent, *, initial, named: SimpleNamespace) -> None:
            self.parent = parent
            self.initial = initial
            self.named = named

        def is_symlink(self) -> bool:
            return False

        def lstat(self):
            if isinstance(self.initial, BaseException):
                raise self.initial
            return self.initial

        def stat(self, *, follow_symlinks: bool = False) -> SimpleNamespace:
            del follow_symlinks
            return self.named

        def __fspath__(self) -> str:
            return "state.lock"

        def __str__(self) -> str:
            return "state.lock"

    monkeypatch.setattr(state_lock, "ensure_private_dir_required", lambda _path: None)
    with pytest.raises(OSError, match="symlinked state lock"):
        state_lock._open_lock_file(
            LockPath(
                Parent([]),
                initial=_status(stat.S_IFLNK),
                named=_status(stat.S_IFREG),
            )  # type: ignore[arg-type]
        )

    opened = _status(stat.S_IFREG, dev=1, ino=2, gid=1)
    named = _status(stat.S_IFREG, dev=1, ino=2, gid=1)
    monkeypatch.setattr(state_lock, "ensure_shared_dir", lambda _path: None)
    monkeypatch.setattr(state_lock, "require_shared_dir_metadata", lambda *_args: None)
    monkeypatch.setattr(state_lock, "_secure_lock_mode", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(state_lock.os, "open", lambda *_args, **_kwargs: 55)
    monkeypatch.setattr(state_lock.os, "fstat", lambda _fd: opened)
    monkeypatch.setattr(state_lock.os, "close", lambda _fd: None)
    monkeypatch.setattr(state_lock.os, "write", lambda *_args: 1)
    monkeypatch.setattr(state_lock.os, "fsync", lambda _fd: None)
    monkeypatch.setattr(state_lock.os, "lseek", lambda *_args: 0)
    with pytest.raises(OSError, match="directory changed"):
        state_lock._open_lock_file(
            LockPath(
                Parent([_status(stat.S_IFDIR, dev=1, ino=1, gid=1), _status(stat.S_IFDIR, dev=2, ino=1, gid=1)]),
                initial=FileNotFoundError(),
                named=named,
            ),
            shared=True,
        )  # type: ignore[arg-type]

    state_lock.os.name = "posix"
    monkeypatch.setattr(state_lock.os, "fstat", lambda _fd: _status(stat.S_IFREG, dev=1, ino=2, gid=2))
    with pytest.raises(OSError, match="group must match"):
        state_lock._open_lock_file(
            LockPath(
                Parent([_status(stat.S_IFDIR, dev=1, ino=1, gid=1), _status(stat.S_IFDIR, dev=1, ino=1, gid=1)]),
                initial=FileNotFoundError(),
                named=named,
            ),
            shared=True,
        )  # type: ignore[arg-type]

    state_lock._prepare_for_fork()
    state_lock._resume_after_fork()
    monkeypatch.setattr(
        state_lock.os,
        "close",
        lambda _fd: (_ for _ in ()).throw(OSError("already closed")),
    )
    state_lock._active_lock_descriptors = {99}
    state_lock._reset_after_fork()

    class FakeThreadLock:
        def acquire(self, *, timeout: float) -> bool:
            del timeout
            return True

        def release(self) -> None:
            return None

    fake_thread_lock = FakeThreadLock()
    held: dict[str, int] = {}
    monkeypatch.setattr(state_lock, "_thread_lock_for", lambda _key: fake_thread_lock)
    monkeypatch.setattr(state_lock, "_held_locks", lambda: held)
    monkeypatch.setattr(state_lock, "_open_lock_file", lambda *_args, **_kwargs: 77)
    monkeypatch.setattr(state_lock, "_acquire_os_lock", lambda *_args: None)
    monkeypatch.setattr(state_lock, "_release_os_lock", lambda _fd: None)
    monkeypatch.setattr(state_lock.os, "close", lambda _fd: None)
    pids = iter([100, 100, 999, 100])
    monkeypatch.setattr(state_lock.os, "getpid", lambda: next(pids))
    lock_path = tmp_path / "reentrant-state.json"
    with state_lock.exclusive_file_lock(lock_path):
        with state_lock.exclusive_file_lock(lock_path):
            pass
    held.clear()

    pids = iter([100, 999])
    monkeypatch.setattr(state_lock.os, "getpid", lambda: next(pids))
    with state_lock.exclusive_file_lock(tmp_path / "non-owner-state.json"):
        pass
    held.clear()
    state_lock._active_lock_descriptors.clear()


def test_team_sync_reader_and_timestamp_defensive_edges(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    root = tmp_path / "shared"
    root.mkdir()
    path = root / "record.json"
    path.write_bytes(b"ok")
    monkeypatch.setattr(team_sync, "require_shared_file_metadata", lambda *_args: None)
    monkeypatch.setattr(team_sync, "require_shared_dir_metadata", lambda *_args: None)
    monkeypatch.delattr(team_sync.os, "O_BINARY", raising=False)
    monkeypatch.setattr(team_sync.os, "O_NOFOLLOW", 0, raising=False)

    class FakeRecord:
        def __init__(self, status: SimpleNamespace) -> None:
            self.status = status

        def lstat(self) -> SimpleNamespace:
            return self.status

        def __str__(self) -> str:
            return "team-record"

    with pytest.raises(ValueError, match="symbolic link"):
        team_sync._read_team_sync_bytes(FakeRecord(_status(stat.S_IFLNK)), root=root)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="regular file"):
        team_sync._read_team_sync_bytes(FakeRecord(_status(stat.S_IFDIR)), root=root)  # type: ignore[arg-type]
    with pytest.raises(ValueError, match="exceeds"):
        team_sync._read_team_sync_bytes(
            FakeRecord(_status(stat.S_IFREG, size=team_sync.MAX_TEAM_SYNC_BYTES + 1)),
            root=root,
        )  # type: ignore[arg-type]

    assert team_sync._read_team_sync_bytes(path, root=root) == b"ok"

    monkeypatch.setattr(team_sync.os, "fstat", lambda _fd: _status(stat.S_IFDIR))
    with pytest.raises(ValueError, match="changed or is not a regular"):
        team_sync._read_team_sync_bytes(path, root=root)

    # Reuse one real named-file status for the descriptor and the first named
    # check.  Windows can report platform-specific values for a real
    # ``os.fstat`` call, which would otherwise trip the earlier identity guard
    # before the final post-read replacement check is exercised.
    stable_status = team_sync.Path.stat(path, follow_symlinks=False)
    monkeypatch.setattr(team_sync.os, "fstat", lambda _fd: stable_status)

    class OversizedHandle:
        def __enter__(self):
            return self

        def __exit__(self, *_args) -> bool:
            return False

        def read(self, _limit: int) -> bytes:
            return b"x" * (team_sync.MAX_TEAM_SYNC_BYTES + 1)

    original_fdopen = team_sync.os.fdopen
    monkeypatch.setattr(team_sync.os, "fdopen", lambda *_args, **_kwargs: OversizedHandle())
    with pytest.raises(ValueError, match="exceeds"):
        team_sync._read_team_sync_bytes(path, root=root)

    monkeypatch.setattr(team_sync.os, "fdopen", original_fdopen)

    # Use a concrete path subclass so only this record's post-open identity
    # changes.  Patching pathlib.Path.stat globally is process-wide and can
    # make platform-specific pytest internals observe the synthetic inode.
    altered_status = _status(
        stat.S_IFREG,
        dev=stable_status.st_dev,
        ino=stable_status.st_ino + 1,
        gid=getattr(stable_status, "st_gid", 0),
        size=getattr(stable_status, "st_size", 0),
    )
    path_type = type(path)

    class ChangedRecordPath(path_type):
        _stat_calls = 0

        def lstat(self):
            return path_type.lstat(self)

        def stat(self, *args, **kwargs):
            self._stat_calls += 1
            if self._stat_calls == 1:
                return stable_status
            return altered_status

    changed_path = ChangedRecordPath(path)
    with pytest.raises(ValueError, match="changed while reading"):
        team_sync._read_team_sync_bytes(changed_path, root=root)

    with pytest.raises(ValueError, match="UTC ISO-8601"):
        team_sync._validate_updated_at(None)
    with pytest.raises(ValueError, match="canonical UTC"):
        team_sync._validate_updated_at("2026-09-14T00:00:00.123456+00:00")

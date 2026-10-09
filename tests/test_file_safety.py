import os
import stat

import pytest

from remote_ops_workspace import file_safety
from remote_ops_workspace.file_safety import (
    PRIVATE_FILE_MODE,
    append_jsonl_private,
    chmod_best_effort,
    write_bytes_atomic,
    write_json_atomic,
    write_text_atomic,
)


def test_write_json_atomic_replaces_content_and_cleans_temporary_files(tmp_path) -> None:
    path = tmp_path / "profiles.json"

    write_json_atomic(path, {"version": 1, "profiles": []}, private=True)
    write_json_atomic(path, {"version": 2, "profiles": [{"name": "edge"}]}, private=True)

    assert '"version": 2' in path.read_text(encoding="utf-8")
    assert not list(tmp_path.glob(".profiles.json.*.tmp"))
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == PRIVATE_FILE_MODE


def test_write_text_atomic_uses_owner_only_mode_for_private_files(tmp_path) -> None:
    path = tmp_path / "secret.txt"

    write_text_atomic(path, "top-secret", private=True)

    assert path.read_text(encoding="utf-8") == "top-secret"
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == PRIVATE_FILE_MODE


def test_private_atomic_write_rejects_a_symlinked_destination(tmp_path) -> None:
    target = tmp_path / "outside.png"
    target.write_bytes(b"preserve-me")
    link = tmp_path / "capture.png"
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    with pytest.raises(OSError, match="symlinked private artifact"):
        write_bytes_atomic(link, b"private-png", private=True)

    assert target.read_bytes() == b"preserve-me"
    assert link.is_symlink()


def test_private_atomic_write_rejects_symlinked_directory_ancestor(tmp_path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    linked = tmp_path / "state"
    try:
        linked.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink creation unavailable: {exc}")

    destination = linked / "nested" / "secret.json"
    with pytest.raises(OSError, match="linked private directory ancestor"):
        write_json_atomic(destination, {"secret": "must-not-write"}, private=True)

    assert not (outside / "nested" / "secret.json").exists()


def test_private_atomic_write_fails_closed_when_permissions_cannot_be_set(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "capture.png"

    def reject_permissions(_path, _mode) -> None:
        raise OSError("permissions denied")

    monkeypatch.setattr(file_safety, "_chmod_required", reject_permissions)

    with pytest.raises(OSError, match="permissions denied"):
        write_bytes_atomic(path, b"private-png", private=True)

    assert not path.exists()


def test_private_atomic_write_removes_final_artifact_when_final_mode_fails(
    tmp_path, monkeypatch
) -> None:
    path = tmp_path / "capture.png"
    chmod_calls = 0
    original = file_safety._chmod_required

    def fail_after_replace(target, mode) -> None:
        nonlocal chmod_calls
        chmod_calls += 1
        if chmod_calls == 3:
            raise OSError("final permissions denied")
        original(target, mode)

    monkeypatch.setattr(file_safety, "_chmod_required", fail_after_replace)

    with pytest.raises(OSError, match="final permissions denied"):
        write_bytes_atomic(path, b"private-png", private=True)

    assert chmod_calls == 3
    assert not path.exists()


def test_private_atomic_write_restores_old_bytes_after_final_permission_failure(tmp_path, monkeypatch) -> None:
    path = tmp_path / "profiles.json"
    write_bytes_atomic(path, b"old-private-state", private=True)
    original_chmod = file_safety._chmod_required

    def denied_final_permissions(target, mode):
        if target == path:
            raise PermissionError("final permissions denied")
        original_chmod(target, mode)

    monkeypatch.setattr(file_safety, "_chmod_required", denied_final_permissions)
    with pytest.raises(PermissionError, match="final permissions denied"):
        write_bytes_atomic(path, b"new-private-state", private=True)

    assert path.read_bytes() == b"old-private-state"
    assert not list(tmp_path.glob(".*.tmp"))
    if os.name == "posix":
        assert stat.S_IMODE(path.stat().st_mode) == PRIVATE_FILE_MODE


def test_private_write_retains_secure_recovery_copy_when_restore_is_denied(tmp_path, monkeypatch) -> None:
    path = tmp_path / "profiles.json"
    write_bytes_atomic(path, b"old-private-state", private=True)
    original_chmod = file_safety._chmod_required
    original_replace = file_safety.os.replace

    def denied_final_permissions(target, mode):
        if target == path:
            raise PermissionError("final permissions denied")
        original_chmod(target, mode)

    def denied_restore(source, destination):
        if ".rollback." in str(source):
            raise PermissionError("recovery replace denied")
        original_replace(source, destination)

    monkeypatch.setattr(file_safety, "_chmod_required", denied_final_permissions)
    monkeypatch.setattr(file_safety.os, "replace", denied_restore)
    with pytest.raises(OSError, match="original private file preserved for recovery at") as failure:
        write_bytes_atomic(path, b"new-private-state", private=True)

    recovery = list(tmp_path.glob(".*.rollback.*.tmp"))
    assert len(recovery) == 1
    assert recovery[0].read_bytes() == b"old-private-state"
    assert str(recovery[0]) in str(failure.value)
    assert "recovery replace denied" in str(failure.value)
    if os.name == "posix":
        assert stat.S_IMODE(recovery[0].stat().st_mode) == PRIVATE_FILE_MODE


def test_private_write_rejects_recovery_after_destination_identity_changes(tmp_path, monkeypatch) -> None:
    path = tmp_path / "profiles.json"
    replacement = tmp_path / "other.json"
    write_bytes_atomic(path, b"old-private-state", private=True)
    write_bytes_atomic(replacement, b"independent-state", private=True)
    original_chmod = file_safety._chmod_required

    def replace_identity_before_failure(target, mode):
        if target == path:
            file_safety.os.replace(replacement, path)
            raise PermissionError("final permissions denied")
        original_chmod(target, mode)

    monkeypatch.setattr(file_safety, "_chmod_required", replace_identity_before_failure)
    with pytest.raises(OSError, match="private artifact changed before rollback"):
        write_bytes_atomic(path, b"new-private-state", private=True)

    assert path.read_bytes() == b"independent-state"
    recovery = list(tmp_path.glob(".*.rollback.*.tmp"))
    assert len(recovery) == 1
    assert recovery[0].read_bytes() == b"old-private-state"


def test_private_write_rejects_changed_recovery_copy(tmp_path, monkeypatch) -> None:
    path = tmp_path / "profiles.json"
    write_bytes_atomic(path, b"old-private-state", private=True)
    original_chmod = file_safety._chmod_required

    def replace_recovery_before_failure(target, mode):
        if target == path:
            recovery = next(tmp_path.glob(".*.rollback.*.tmp"))
            replacement = tmp_path / "replacement"
            replacement.write_bytes(b"foreign-state")
            file_safety.os.replace(replacement, recovery)
            raise PermissionError("final permissions denied")
        original_chmod(target, mode)

    monkeypatch.setattr(file_safety, "_chmod_required", replace_recovery_before_failure)
    with pytest.raises(OSError, match="private recovery file changed before rollback"):
        write_bytes_atomic(path, b"new-private-state", private=True)
    assert path.read_bytes() == b"new-private-state"


def test_backup_permission_failure_preserves_original_error_and_old_file(tmp_path, monkeypatch) -> None:
    path = tmp_path / "profiles.json"
    write_bytes_atomic(path, b"old-private-state", private=True)
    original_chmod = file_safety._chmod_required
    original_unlink = file_safety.Path.unlink

    def denied_backup_permissions(target, mode):
        if ".rollback." in target.name:
            raise PermissionError("backup permissions denied")
        original_chmod(target, mode)

    def denied_backup_cleanup(target, *args, **kwargs):
        if ".rollback." in target.name:
            raise PermissionError("backup cleanup denied")
        original_unlink(target, *args, **kwargs)

    monkeypatch.setattr(file_safety, "_chmod_required", denied_backup_permissions)
    monkeypatch.setattr(file_safety.Path, "unlink", denied_backup_cleanup)
    with pytest.raises(PermissionError, match="backup permissions denied"):
        write_bytes_atomic(path, b"new-private-state", private=True)
    assert path.read_bytes() == b"old-private-state"
    assert next(tmp_path.glob(".*.rollback.*.tmp")).read_bytes() == b""


def test_successful_private_write_keeps_secured_backup_if_cleanup_is_denied(tmp_path, monkeypatch) -> None:
    path = tmp_path / "profiles.json"
    write_bytes_atomic(path, b"old-private-state", private=True)
    original_unlink = file_safety.Path.unlink

    def denied_backup_cleanup(target, *args, **kwargs):
        if ".rollback." in target.name:
            raise PermissionError("backup cleanup denied")
        original_unlink(target, *args, **kwargs)

    monkeypatch.setattr(file_safety.Path, "unlink", denied_backup_cleanup)
    write_bytes_atomic(path, b"new-private-state", private=True)
    assert path.read_bytes() == b"new-private-state"
    backup = next(tmp_path.glob(".*.rollback.*.tmp"))
    assert backup.read_bytes() == b"old-private-state"
    if os.name == "posix":
        assert stat.S_IMODE(backup.stat().st_mode) == PRIVATE_FILE_MODE


def test_backup_copy_failure_aborts_before_replacing_original(tmp_path, monkeypatch) -> None:
    path = tmp_path / "profiles.json"
    write_bytes_atomic(path, b"old-private-state", private=True)

    def denied_copy(*_args):
        raise OSError("backup copy failed")

    monkeypatch.setattr(file_safety.shutil, "copyfileobj", denied_copy)
    with pytest.raises(OSError, match="backup copy failed"):
        write_bytes_atomic(path, b"new-private-state", private=True)
    assert path.read_bytes() == b"old-private-state"
    assert not list(tmp_path.glob(".*.tmp"))


def test_chmod_best_effort_ignores_unsupported_permissions() -> None:
    class UnsupportedPath:
        def chmod(self, _mode: int) -> None:
            raise OSError("permissions unsupported")

    chmod_best_effort(UnsupportedPath(), PRIVATE_FILE_MODE)  # type: ignore[arg-type]


def test_append_jsonl_private_writes_one_record_per_line(tmp_path) -> None:
    path = tmp_path / "audit" / "events.jsonl"

    append_jsonl_private(path, {"event": "connected"})
    append_jsonl_private(path, {"event": "closed"})

    assert path.read_text(encoding="utf-8").splitlines() == [
        '{"event": "connected"}',
        '{"event": "closed"}',
    ]
    if os.name != "nt":
        assert stat.S_IMODE(path.stat().st_mode) == PRIVATE_FILE_MODE


def test_private_jsonl_append_rejects_symlinked_destination(tmp_path) -> None:
    target = tmp_path / "outside.jsonl"
    target.write_text("preserve-me\n", encoding="utf-8")
    link = tmp_path / "audit.jsonl"
    try:
        link.symlink_to(target)
    except OSError as exc:
        pytest.skip(f"symlink creation unavailable: {exc}")

    with pytest.raises(OSError, match="symlinked private artifact"):
        append_jsonl_private(link, {"event": "secret"})

    assert target.read_text(encoding="utf-8") == "preserve-me\n"


def test_private_jsonl_append_rejects_symlinked_directory_ancestor(tmp_path) -> None:
    outside = tmp_path / "outside"
    outside.mkdir()
    linked = tmp_path / "state"
    try:
        linked.symlink_to(outside, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlink creation unavailable: {exc}")

    with pytest.raises(OSError, match="linked private directory ancestor"):
        append_jsonl_private(linked / "audit" / "events.jsonl", {"event": "secret"})

    assert not (outside / "audit" / "events.jsonl").exists()


def test_private_jsonl_append_fails_closed_when_permissions_cannot_be_set(
    tmp_path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    path = tmp_path / "audit" / "events.jsonl"

    def reject_permissions(_path, _mode) -> None:
        raise OSError("permissions denied")

    monkeypatch.setattr(file_safety, "_chmod_required", reject_permissions)

    with pytest.raises(OSError, match="permissions denied"):
        append_jsonl_private(path, {"event": "secret"})

    assert not path.exists()


def test_private_atomic_write_rejects_reported_symlink_without_platform_support(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "capture.png"
    original_is_symlink = file_safety.Path.is_symlink

    def report_destination_symlink(target) -> bool:
        return target == path or original_is_symlink(target)

    monkeypatch.setattr(file_safety.Path, "is_symlink", report_destination_symlink)

    with pytest.raises(OSError, match="symlinked private artifact"):
        write_bytes_atomic(path, b"private-png", private=True)


def test_private_atomic_write_rechecks_destination_before_replace(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "capture.png"
    original_is_symlink = file_safety.Path.is_symlink
    destination_checks = 0

    def becomes_symlink(target) -> bool:
        nonlocal destination_checks
        if target == path:
            destination_checks += 1
            return destination_checks > 1
        return original_is_symlink(target)

    monkeypatch.setattr(file_safety.Path, "is_symlink", becomes_symlink)

    with pytest.raises(OSError, match="symlinked private artifact"):
        write_bytes_atomic(path, b"private-png", private=True)

    assert not path.exists()
    assert not list(tmp_path.glob(".capture.png.*.tmp"))


def test_private_atomic_write_preserves_original_error_when_cleanup_fails(
    tmp_path, monkeypatch: pytest.MonkeyPatch
) -> None:
    path = tmp_path / "capture.png"
    original_chmod = file_safety._chmod_required
    original_unlink = file_safety.Path.unlink
    chmod_calls = 0

    def fail_final_permissions(target, mode) -> None:
        nonlocal chmod_calls
        chmod_calls += 1
        if chmod_calls == 3:
            raise OSError("final permissions denied")
        original_chmod(target, mode)

    def fail_final_cleanup(target, *args, **kwargs) -> None:
        if target == path:
            raise OSError("cleanup denied")
        original_unlink(target, *args, **kwargs)

    monkeypatch.setattr(file_safety, "_chmod_required", fail_final_permissions)
    monkeypatch.setattr(file_safety.Path, "unlink", fail_final_cleanup)

    with pytest.raises(OSError, match="final permissions denied"):
        write_bytes_atomic(path, b"private-png", private=True)

    assert path.read_bytes() == b"private-png"

    monkeypatch.setattr(file_safety.Path, "unlink", original_unlink)
    path.unlink()

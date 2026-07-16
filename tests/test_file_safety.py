import os
import stat

import pytest

from remote_ops_workspace import file_safety
from remote_ops_workspace.file_safety import (
    PRIVATE_FILE_MODE,
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

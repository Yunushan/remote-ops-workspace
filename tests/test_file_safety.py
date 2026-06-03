import os
import stat

from remote_ops_workspace.file_safety import (
    PRIVATE_FILE_MODE,
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

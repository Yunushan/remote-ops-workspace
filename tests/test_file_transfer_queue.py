import contextlib
import io
import json
import os
from pathlib import Path

from remote_ops_workspace.cli import main
from remote_ops_workspace.file_transfer import (
    build_sftp_queue_plan,
    build_sftp_remote_preview_plan,
    parse_transfer_item_spec,
    preview_local_path,
    run_sftp_queue,
)
from remote_ops_workspace.models import Profile
from remote_ops_workspace.storage import ProfileStore


def test_sftp_queue_plan_builds_batch_commands() -> None:
    profile = Profile(name="files", protocol="ssh", host="192.0.2.10", username="admin")
    items = [
        parse_transfer_item_spec("get /etc/hosts ./hosts.copy"),
        parse_transfer_item_spec("put --recursive ./build /tmp/build"),
        parse_transfer_item_spec("mkdir /tmp/releases"),
        parse_transfer_item_spec("rename /tmp/old /tmp/new"),
    ]

    plan = build_sftp_queue_plan(profile, items)
    result = run_sftp_queue(plan, dry_run=True)

    assert plan.command[:3] == ["sftp", "-b", "-"]
    assert plan.command[-1] == "admin@192.0.2.10"
    assert plan.batch_commands == [
        "get /etc/hosts ./hosts.copy",
        "put -r ./build /tmp/build",
        "mkdir /tmp/releases",
        "rename /tmp/old /tmp/new",
    ]
    assert result.ok is True
    assert result.dry_run is True
    assert result.to_dict()["items"][0]["action"] == "get"


def test_sftp_queue_rejects_option_like_remote_path() -> None:
    profile = Profile(name="files", protocol="ssh", host="192.0.2.10")
    try:
        build_sftp_queue_plan(profile, [parse_transfer_item_spec("get -bad ./local")])
    except ValueError as exc:
        assert "remote path must not start with '-'" in str(exc)
    else:
        raise AssertionError("queue remote paths should reject option-like values")


def test_sftp_remote_preview_plan_uses_ls_batch() -> None:
    profile = Profile(name="files", protocol="sftp", host="192.0.2.10")
    plan = build_sftp_remote_preview_plan(profile, "/var/log")
    assert plan.command[:3] == ["sftp", "-b", "-"]
    assert plan.batch_commands == ["ls -la /var/log"]


def test_local_file_preview_text_and_directory(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    text_file = tmp_path / "report.txt"
    text_file.write_text("hello world", encoding="utf-8")
    (tmp_path / "child.txt").write_text("child", encoding="utf-8")

    file_preview = preview_local_path(text_file, max_bytes=5)
    dir_preview = preview_local_path(tmp_path)

    assert file_preview.kind == "file"
    assert file_preview.text == "hello"
    assert file_preview.truncated is True
    assert file_preview.binary is False
    assert dir_preview.kind == "directory"
    assert "child.txt" in dir_preview.children


def test_local_file_preview_detects_binary(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    binary_file = tmp_path / "blob.bin"
    binary_file.write_bytes(b"\x00\x01\x02")
    preview = preview_local_path(binary_file)
    assert preview.kind == "file"
    assert preview.binary is True
    assert preview.text == ""


def test_cli_files_queue_dry_run_json(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    old_home = os.environ.get("ROW_HOME")
    os.environ["ROW_HOME"] = str(tmp_path / "row-home")
    try:
        store = ProfileStore(Path(os.environ["ROW_HOME"]) / "profiles.json")
        store.add(Profile(name="files", protocol="ssh", host="192.0.2.10"))
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rc = main(
                [
                    "files",
                    "queue",
                    "files",
                    "--op",
                    "get /etc/hosts ./hosts.copy",
                    "--op",
                    "mkdir /tmp/releases",
                    "--dry-run",
                    "--json",
                ]
            )
        payload = json.loads(stdout.getvalue())
    finally:
        if old_home is None:
            os.environ.pop("ROW_HOME", None)
        else:
            os.environ["ROW_HOME"] = old_home
    assert rc == 0
    assert payload["dry_run"] is True
    assert payload["batch_commands"] == ["get /etc/hosts ./hosts.copy", "mkdir /tmp/releases"]


def test_cli_preview_local_json(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    target = tmp_path / "note.txt"
    target.write_text("hello", encoding="utf-8")
    stdout = io.StringIO()
    with contextlib.redirect_stdout(stdout):
        rc = main(["files", "preview-local", str(target), "--json"])
    payload = json.loads(stdout.getvalue())
    assert rc == 0
    assert payload["kind"] == "file"
    assert payload["text"] == "hello"

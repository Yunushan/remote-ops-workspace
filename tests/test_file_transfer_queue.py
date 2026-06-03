import contextlib
import io
import json
import os
from pathlib import Path

from remote_ops_workspace.cli import main
from remote_ops_workspace.file_transfer import (
    build_sftp_get_plan,
    build_sftp_put_plan,
    build_sftp_queue_plan,
    build_sftp_remote_preview_plan,
    build_sftp_rm_plan,
    parse_transfer_item_spec,
    preview_local_path,
    run_sftp_batch,
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
    assert result.destructive is True
    assert result.force is False
    assert result.to_dict()["items"][0]["action"] == "get"


def test_sftp_queue_refuses_destructive_execution_without_force() -> None:
    profile = Profile(name="files", protocol="ssh", host="192.0.2.10")
    plan = build_sftp_queue_plan(profile, [parse_transfer_item_spec("rm /tmp/old.txt")])

    assert plan.destructive is True
    try:
        run_sftp_queue(plan, dry_run=False)
    except ValueError as exc:
        assert "requires --force" in str(exc)
        assert "rm deletes remote path" in str(exc)
    else:
        raise AssertionError("destructive SFTP queue should require --force")


def test_sftp_queue_force_allows_destructive_dry_run() -> None:
    profile = Profile(name="files", protocol="ssh", host="192.0.2.10")
    plan = build_sftp_queue_plan(profile, [parse_transfer_item_spec("rm /tmp/old.txt")], force=True)
    result = run_sftp_queue(plan, dry_run=True)

    assert plan.force is True
    assert result.ok is True
    assert result.force is True


def test_sftp_put_refuses_execution_without_force() -> None:
    profile = Profile(name="files", protocol="sftp", host="192.0.2.10")
    plan = build_sftp_put_plan(profile, "build.tar.gz", remote_path="/tmp/build.tar.gz")

    assert plan.destructive is True
    assert "put can overwrite remote files" in plan.safety_warnings[0]
    try:
        run_sftp_batch(plan, dry_run=False)
    except ValueError as exc:
        assert "requires --force" in str(exc)
    else:
        raise AssertionError("overwrite-prone SFTP put should require --force")


def test_sftp_get_existing_local_target_requires_force(tmp_path: Path) -> None:
    profile = Profile(name="files", protocol="ssh", host="192.0.2.10")
    target = tmp_path / "hosts.copy"
    target.write_text("old", encoding="utf-8")

    plan = build_sftp_get_plan(profile, "/etc/hosts", local_path=target)

    assert plan.destructive is True
    assert str(target) in plan.safety_warnings[0]
    try:
        run_sftp_batch(plan, dry_run=False)
    except ValueError as exc:
        assert "requires --force" in str(exc)
    else:
        raise AssertionError("local-overwrite SFTP get should require --force")


def test_sftp_delete_rejects_broad_remote_paths_even_with_force() -> None:
    profile = Profile(name="files", protocol="ssh", host="192.0.2.10")
    for remote in ["/", ".", "~", "../old", "/tmp/*"]:
        try:
            build_sftp_rm_plan(profile, remote, allow_delete=True)
        except ValueError:
            pass
        else:
            raise AssertionError(f"broad destructive remote path should be rejected: {remote}")


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
    assert payload["destructive"] is False


def test_cli_files_rm_requires_force_before_execution(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    old_home = os.environ.get("ROW_HOME")
    os.environ["ROW_HOME"] = str(tmp_path / "row-home")
    try:
        store = ProfileStore(Path(os.environ["ROW_HOME"]) / "profiles.json")
        store.add(Profile(name="files", protocol="ssh", host="192.0.2.10"))
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            rc = main(["files", "rm", "files", "/tmp/old.txt"])
    finally:
        if old_home is None:
            os.environ.pop("ROW_HOME", None)
        else:
            os.environ["ROW_HOME"] = old_home

    assert rc == 1
    assert "requires --force" in stderr.getvalue()


def test_cli_files_rm_dry_run_can_preview_without_force(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    old_home = os.environ.get("ROW_HOME")
    os.environ["ROW_HOME"] = str(tmp_path / "row-home")
    try:
        store = ProfileStore(Path(os.environ["ROW_HOME"]) / "profiles.json")
        store.add(Profile(name="files", protocol="ssh", host="192.0.2.10"))
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rc = main(["files", "rm", "files", "/tmp/old.txt", "--dry-run"])
    finally:
        if old_home is None:
            os.environ.pop("ROW_HOME", None)
        else:
            os.environ["ROW_HOME"] = old_home

    output = stdout.getvalue()
    assert rc == 0
    assert "rm /tmp/old.txt" in output
    assert "unless --force is set" in output


def test_cli_files_put_requires_force_before_execution(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    old_home = os.environ.get("ROW_HOME")
    os.environ["ROW_HOME"] = str(tmp_path / "row-home")
    try:
        store = ProfileStore(Path(os.environ["ROW_HOME"]) / "profiles.json")
        store.add(Profile(name="files", protocol="ssh", host="192.0.2.10"))
        stderr = io.StringIO()
        with contextlib.redirect_stderr(stderr):
            rc = main(["files", "put", "files", str(tmp_path / "build.tar.gz"), "--remote", "/tmp/build.tar.gz"])
    finally:
        if old_home is None:
            os.environ.pop("ROW_HOME", None)
        else:
            os.environ["ROW_HOME"] = old_home

    assert rc == 1
    assert "put can overwrite remote files" in stderr.getvalue()


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

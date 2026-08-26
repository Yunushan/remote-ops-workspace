from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

import remote_ops_workspace.file_transfer as transfer
from remote_ops_workspace.file_transfer import (
    SftpQueueItem,
    SftpQueuePlan,
    SftpSafetyReview,
    build_sftp_get_plan,
    build_sftp_mkdir_plan,
    build_sftp_put_plan,
    build_sftp_queue_plan,
    build_sftp_rename_plan,
    build_sftp_rmdir_plan,
    preview_local_path,
    run_sftp_batch,
    run_sftp_interactive,
    run_sftp_queue,
)
from remote_ops_workspace.launcher import LaunchPlan
from remote_ops_workspace.models import Profile


def _profile() -> Profile:
    return Profile(name="files", protocol="ssh", host="files.example", username="operator")


def test_sftp_queue_plan_serializers_and_safety_property() -> None:
    plan = build_sftp_queue_plan(_profile(), [SftpQueueItem(action="mkdir", remote_path="/tmp/new")])

    assert SftpSafetyReview(("warning",)).destructive is True
    assert SftpSafetyReview().destructive is False
    assert plan.batch_input() == "mkdir /tmp/new\n"
    assert plan.printable().startswith("sftp -b -")
    assert plan.printable_batch() == "mkdir /tmp/new"
    assert plan.to_dict()["items"] == [
        {
            "action": "mkdir",
            "remote_path": "/tmp/new",
            "local_path": None,
            "new_remote_path": None,
            "recursive": False,
        }
    ]


def test_sftp_interactive_runner_supports_dry_run_and_checked_execution(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[tuple[list[str], bool]] = []
    monkeypatch.setattr(
        transfer.subprocess,
        "run",
        lambda command, *, check: calls.append((command, check)),
    )
    plan = LaunchPlan("sftp", ["sftp", "operator@files.example"], [])

    assert run_sftp_interactive(plan, dry_run=True) is plan
    assert calls == []
    assert run_sftp_interactive(plan) is plan
    assert calls == [(["sftp", "operator@files.example"], True)]


def test_sftp_batch_builders_cover_recursive_optional_and_destructive_actions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    get_plan = build_sftp_get_plan(_profile(), "/logs/*.txt", recursive=True)
    put_plan = build_sftp_put_plan(_profile(), "build", recursive=True, allow_overwrite=True)
    single_file_put_plan = build_sftp_put_plan(_profile(), "release.txt")
    mkdir_plan = build_sftp_mkdir_plan(_profile(), "/tmp/release")
    rmdir_plan = build_sftp_rmdir_plan(_profile(), "/tmp/old", allow_delete=True)
    rename_plan = build_sftp_rename_plan(
        _profile(),
        "/tmp/current",
        "/tmp/archive",
        allow_rename=True,
    )

    assert get_plan.batch_commands == ["get -r '/logs/*.txt'"]
    assert "remote glob" in get_plan.safety_warnings[0]
    assert put_plan.batch_commands == ["put -r build"]
    assert single_file_put_plan.printable_batch() == "put release.txt"
    assert mkdir_plan.batch_commands == ["mkdir /tmp/release"]
    assert rmdir_plan.batch_commands == ["rmdir /tmp/old"]
    assert rename_plan.batch_commands == ["rename /tmp/current /tmp/archive"]

    calls: list[dict[str, object]] = []

    def fake_run(command: list[str], **kwargs: object) -> None:
        calls.append({"command": command, **kwargs})

    monkeypatch.setattr(transfer.subprocess, "run", fake_run)
    assert run_sftp_batch(put_plan) is put_plan
    assert calls[0]["input"] == "put -r build\n"
    assert calls[0]["text"] is True
    assert calls[0]["check"] is True


def test_sftp_queue_rejects_empty_items() -> None:
    with pytest.raises(ValueError, match="at least one item"):
        build_sftp_queue_plan(_profile(), [])


def test_sftp_queue_dry_run_reports_planned_progress_to_callback() -> None:
    plan = build_sftp_queue_plan(
        _profile(),
        [
            SftpQueueItem(action="mkdir", remote_path="/tmp/one"),
            SftpQueueItem(action="mkdir", remote_path="/tmp/two"),
        ],
    )
    states: list[str] = []

    result = run_sftp_queue(plan, dry_run=True, on_progress=lambda event: states.append(event.state))

    assert states == ["planned", "planned"]
    assert [event.state for event in result.progress] == states


def test_sftp_queue_handles_empty_plan_and_success_without_callback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    empty = SftpQueuePlan(
        profile_name="files",
        command=["sftp", "-b", "-", "operator@files.example"],
        items=[],
        batch_commands=[],
        notes=[],
    )
    empty_result = run_sftp_queue(empty)
    assert empty_result.ok is True
    assert empty_result.progress == []

    monkeypatch.setattr(
        transfer.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=0, stdout="done\n", stderr=""),
    )
    plan = build_sftp_queue_plan(_profile(), [SftpQueueItem(action="mkdir", remote_path="/tmp/new")])
    result = run_sftp_queue(plan)

    assert result.ok is True
    assert result.stdout == "done\n"
    assert [event.state for event in result.progress] == ["completed"]


@pytest.mark.parametrize("with_callback", [False, True])
def test_sftp_queue_marks_all_remaining_items_skipped_after_command_failure(
    monkeypatch: pytest.MonkeyPatch,
    with_callback: bool,
) -> None:
    plan = build_sftp_queue_plan(
        _profile(),
        [
            SftpQueueItem(action="mkdir", remote_path="/tmp/one"),
            SftpQueueItem(action="mkdir", remote_path="/tmp/two"),
            SftpQueueItem(action="mkdir", remote_path="/tmp/three"),
        ],
    )
    monkeypatch.setattr(
        transfer.subprocess,
        "run",
        lambda *_args, **_kwargs: SimpleNamespace(returncode=7, stdout="", stderr="failed\n"),
    )
    states: list[str] = []
    callback = (lambda event: states.append(event.state)) if with_callback else None

    result = run_sftp_queue(plan, on_progress=callback)

    assert result.returncode == 7
    assert [event.state for event in result.progress] == ["failed", "skipped", "skipped"]
    if with_callback:
        assert states == ["running", "failed", "skipped", "skipped"]


def test_sftp_queue_start_failure_supports_no_callback(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = build_sftp_queue_plan(
        _profile(),
        [
            SftpQueueItem(action="mkdir", remote_path="/tmp/one"),
            SftpQueueItem(action="mkdir", remote_path="/tmp/two"),
        ],
    )

    def fail_to_start(*_args: object, **_kwargs: object) -> None:
        raise OSError("missing executable")

    monkeypatch.setattr(transfer.subprocess, "run", fail_to_start)
    result = run_sftp_queue(plan)

    assert [event.state for event in result.progress] == ["failed", "skipped"]


def test_local_preview_rejects_invalid_limits_and_reports_missing(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="max_bytes must be positive"):
        preview_local_path(tmp_path, max_bytes=0)
    with pytest.raises(ValueError, match="max_entries must be positive"):
        preview_local_path(tmp_path, max_entries=0)

    missing = preview_local_path(tmp_path / "missing")
    assert missing.exists is False
    assert missing.kind == "missing"


def test_local_preview_reports_special_invalid_utf8_and_os_errors(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    invalid_utf8 = tmp_path / "invalid.bin"
    invalid_utf8.write_bytes(b"\xff\xfe")
    decoded = preview_local_path(invalid_utf8)
    assert decoded.binary is True
    assert decoded.text == ""

    special = tmp_path / "special"
    special.write_text("content", encoding="utf-8")
    original_is_file = Path.is_file
    monkeypatch.setattr(Path, "is_file", lambda _path: False)
    special_preview = preview_local_path(special)
    assert special_preview.kind == "special"
    monkeypatch.setattr(Path, "is_file", original_is_file)

    def fail_is_dir(_path: Path) -> bool:
        raise OSError("cannot inspect")

    monkeypatch.setattr(Path, "is_dir", fail_is_dir)
    error_preview = preview_local_path(special)
    assert error_preview.kind == "error"
    assert "cannot inspect" in error_preview.error


@pytest.mark.parametrize(
    "item",
    [
        SftpQueueItem(action="get"),
        SftpQueueItem(action="put"),
        SftpQueueItem(action="mkdir"),
        SftpQueueItem(action="rm"),
        SftpQueueItem(action="rmdir"),
        SftpQueueItem(action="rename", remote_path="/tmp/old"),
        SftpQueueItem(action="unsupported"),
    ],
)
def test_sftp_queue_rejects_incomplete_or_unknown_items(item: SftpQueueItem) -> None:
    with pytest.raises(ValueError):
        build_sftp_queue_plan(_profile(), [item])


def test_sftp_queue_builds_recursive_items_without_optional_destinations() -> None:
    plan = build_sftp_queue_plan(
        _profile(),
        [
            SftpQueueItem(action="get", remote_path="/logs", recursive=True),
            SftpQueueItem(action="put", local_path="build", recursive=True),
            SftpQueueItem(action="put", local_path="release.txt"),
            SftpQueueItem(action="rmdir", remote_path="/tmp/old"),
        ],
        force=True,
    )

    assert plan.batch_commands == [
        "get -r /logs",
        "put -r build",
        "put release.txt",
        "rmdir /tmp/old",
    ]


def test_get_safety_without_explicit_local_path_handles_basenames() -> None:
    safe_plan = build_sftp_get_plan(_profile(), ".")
    named_plan = build_sftp_get_plan(_profile(), "/etc/hosts")

    assert safe_plan.destructive is False
    assert named_plan.destructive is False

from __future__ import annotations

import hashlib
import json
from pathlib import Path

from remote_ops_workspace.cli import build_parser
from remote_ops_workspace.moba_text import (
    build_moba_text_editor_tab_plan,
    build_moba_text_release_evidence_bundle_plan,
    build_remote_text_edit_plan,
    diff_text_documents,
    preview_text_document,
    review_moba_remote_text_save,
    validate_moba_text_release_evidence,
    write_moba_text_release_evidence_bundle,
    write_text_document,
)
from remote_ops_workspace.models import Profile


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_moba_text_preview_reports_hash_and_line_count(tmp_path: Path) -> None:
    document = tmp_path / "notes.txt"
    document.write_text("alpha\nbeta\n", encoding="utf-8")

    preview = preview_text_document(document)

    assert preview.exists is True
    assert preview.binary is False
    assert preview.line_count == 2
    assert preview.text.splitlines() == ["alpha", "beta"]
    assert len(preview.sha256) == 64
    assert "MobaTextEditor-style" in preview.notes[0]


def test_moba_text_preview_suppresses_binary_payload(tmp_path: Path) -> None:
    document = tmp_path / "payload.bin"
    document.write_bytes(b"abc\x00def")

    preview = preview_text_document(document)

    assert preview.binary is True
    assert preview.text == ""
    assert any("binary" in note for note in preview.notes)


def test_moba_text_write_requires_force_or_expected_hash_for_existing_file(tmp_path: Path) -> None:
    document = tmp_path / "notes.txt"
    document.write_text("old\n", encoding="utf-8")

    try:
        write_text_document(document, "new\n")
    except ValueError as exc:
        assert "--force or --expected-sha256" in str(exc)
    else:
        raise AssertionError("existing text modifications must be guarded")


def test_moba_text_write_with_expected_hash_creates_backup(tmp_path: Path) -> None:
    document = tmp_path / "notes.txt"
    document.write_text("old\n", encoding="utf-8")
    expected = preview_text_document(document).sha256

    result = write_text_document(document, "new\n", expected_sha256=expected)

    assert result.changed is True
    assert result.previous_sha256 == expected
    assert result.backup_path.endswith("notes.txt.bak")
    assert document.read_text(encoding="utf-8") == "new\n"
    assert Path(result.backup_path).read_text(encoding="utf-8") == "old\n"


def test_moba_diff_reports_unified_diff_stats(tmp_path: Path) -> None:
    left = tmp_path / "left.txt"
    right = tmp_path / "right.txt"
    left.write_text("alpha\nbeta\n", encoding="utf-8")
    right.write_text("alpha\ngamma\n", encoding="utf-8")

    result = diff_text_documents(left, right)

    assert result.equal is False
    assert result.added_lines == 1
    assert result.removed_lines == 1
    assert result.hunk_count == 1
    assert "+gamma" in result.unified_diff
    assert "-beta" in result.unified_diff


def test_moba_remote_text_edit_plan_reuses_sftp_get_and_put() -> None:
    profile = Profile(name="edge", protocol="ssh", host="example.invalid", username="ops")
    plan = build_remote_text_edit_plan(profile, "/etc/app.conf", local_path="app.conf.edit")

    assert plan.profile_name == "edge"
    assert plan.remote_path == "/etc/app.conf"
    assert plan.local_path == "app.conf.edit"
    assert plan.download_plan.batch_commands == ["get /etc/app.conf app.conf.edit"]
    assert plan.upload_plan.batch_commands == ["put app.conf.edit /etc/app.conf"]
    assert plan.upload_plan.force is True


def test_moba_text_editor_tab_plan_tracks_direct_sftp_open_and_save() -> None:
    profile = Profile(name="edge", protocol="ssh", host="example.invalid", username="ops")
    digest = "a" * 64

    plan = build_moba_text_editor_tab_plan(
        profile,
        "/etc/app.conf",
        local_path="app.conf.edit",
        remote_sha256=digest,
    )

    assert plan.schema == "row.moba-text.editor-tab.v1"
    assert plan.profile_name == "edge"
    assert plan.opened_from_sftp_browser is True
    assert plan.syntax == "ini"
    assert plan.remote_sha256 == digest
    assert plan.download_plan.batch_commands == ["get /etc/app.conf app.conf.edit"]
    assert plan.save_plan.batch_commands == ["put app.conf.edit /etc/app.conf"]
    assert plan.conflict_policy == "sha256-match-or-force"


def test_moba_remote_text_save_review_blocks_conflicts_without_force(tmp_path: Path) -> None:
    profile = Profile(name="edge", protocol="ssh", host="example.invalid", username="ops")
    local = tmp_path / "app.conf.edit"
    local.write_text("setting=true\n", encoding="utf-8")

    review = review_moba_remote_text_save(
        profile,
        "/etc/app.conf",
        local,
        original_remote_sha256="a" * 64,
        current_remote_sha256="b" * 64,
    )
    forced = review_moba_remote_text_save(
        profile,
        "/etc/app.conf",
        local,
        original_remote_sha256="a" * 64,
        current_remote_sha256="b" * 64,
        force=True,
    )

    assert review.allowed is False
    assert review.conflict is True
    assert review.confirmation_required is True
    assert "Remote file changed" in review.prompt
    assert forced.allowed is True
    assert forced.confirmation_required is False


def test_moba_text_release_evidence_validation_accepts_connected_remote_edit_bundle(tmp_path: Path) -> None:
    open_log = tmp_path / "open.txt"
    save_review_log = tmp_path / "save-review.txt"
    save_log = tmp_path / "save.txt"
    connected_log = tmp_path / "connected.txt"
    open_log.write_text("sftp get /etc/app.conf app.conf.edit\n", encoding="utf-8")
    save_review_log.write_text("row text save-review edge /etc/app.conf\n", encoding="utf-8")
    save_log.write_text("sftp put app.conf.edit /etc/app.conf\n", encoding="utf-8")
    connected_log.write_text("real connected SFTP browser editor tab visible\n", encoding="utf-8")
    evidence = tmp_path / "moba-text-remote-edit.json"
    evidence.write_text(
        json.dumps(
            {
                "schema": "row.moba-text.remote-edit-evidence.v1",
                "release_target": "windows-x64",
                "profile": "edge",
                "remote_path": "/etc/app.conf",
                "editor_tab": {
                    "schema": "row.moba-text.editor-tab.v1",
                    "opened_from_sftp_browser": True,
                    "syntax": "ini",
                    "local_path": "app.conf.edit",
                    "remote_sha256": "a" * 64,
                },
                "open_action": {
                    "status": "passed",
                    "command": "sftp get /etc/app.conf app.conf.edit",
                    "evidence_file": "open.txt",
                    "evidence_sha256": _sha256(open_log),
                },
                "save_review": {
                    "status": "passed",
                    "conflict_checked": True,
                    "command": "row text save-review edge /etc/app.conf",
                    "evidence_file": "save-review.txt",
                    "evidence_sha256": _sha256(save_review_log),
                },
                "save_action": {
                    "status": "passed",
                    "command": "sftp put app.conf.edit /etc/app.conf",
                    "evidence_file": "save.txt",
                    "evidence_sha256": _sha256(save_log),
                },
                "connected_session": {
                    "real_connected_session": True,
                    "sftp_browser_open": True,
                    "editor_tab_visible": True,
                    "evidence_file": "connected.txt",
                    "evidence_sha256": _sha256(connected_log),
                },
            }
        ),
        encoding="utf-8",
    )

    result = validate_moba_text_release_evidence(evidence, assets_dir=tmp_path)

    assert result.passed is True
    assert result.errors == []
    assert result.summary["syntax"] == "ini"


def test_moba_text_release_evidence_rejects_missing_connected_session(tmp_path: Path) -> None:
    action = tmp_path / "action.txt"
    connected = tmp_path / "connected.txt"
    action.write_text("passed\n", encoding="utf-8")
    connected.write_text("connected proof\n", encoding="utf-8")
    evidence = tmp_path / "moba-text-remote-edit.json"
    passed_action = {
        "status": "passed",
        "command": "action",
        "evidence_file": "action.txt",
        "evidence_sha256": _sha256(action),
    }
    evidence.write_text(
        json.dumps(
            {
                "schema": "row.moba-text.remote-edit-evidence.v1",
                "release_target": "windows-x64",
                "profile": "edge",
                "remote_path": "/etc/app.conf",
                "editor_tab": {
                    "schema": "row.moba-text.editor-tab.v1",
                    "opened_from_sftp_browser": True,
                    "syntax": "ini",
                    "local_path": "app.conf.edit",
                    "remote_sha256": "a" * 64,
                },
                "open_action": passed_action,
                "save_review": {**passed_action, "conflict_checked": True},
                "save_action": passed_action,
                "connected_session": {
                    "real_connected_session": False,
                    "sftp_browser_open": True,
                    "editor_tab_visible": True,
                    "evidence_file": "connected.txt",
                    "evidence_sha256": _sha256(connected),
                },
            }
        ),
        encoding="utf-8",
    )

    result = validate_moba_text_release_evidence(evidence, assets_dir=tmp_path)

    assert result.passed is False
    assert "connected_session.real_connected_session must be true" in result.errors


def test_moba_text_release_evidence_bundle_writer_creates_valid_bundle(tmp_path: Path) -> None:
    profile = Profile(name="edge", protocol="ssh", host="example.invalid", username="ops")
    open_log = tmp_path / "source-open.txt"
    save_review_log = tmp_path / "source-save-review.txt"
    save_log = tmp_path / "source-save.txt"
    connected_log = tmp_path / "source-connected.txt"
    open_log.write_text("sftp get /etc/app.conf app.conf.edit\n", encoding="utf-8")
    save_review_log.write_text("row text save-review edge /etc/app.conf\n", encoding="utf-8")
    save_log.write_text("sftp put app.conf.edit /etc/app.conf\n", encoding="utf-8")
    connected_log.write_text("real connected SFTP browser editor tab visible\n", encoding="utf-8")

    plan = build_moba_text_release_evidence_bundle_plan(
        profile,
        "/etc/app.conf",
        out_dir=tmp_path / "bundle",
        local_path="app.conf.edit",
        remote_sha256="a" * 64,
        open_evidence=open_log,
        save_review_evidence=save_review_log,
        save_evidence=save_log,
        connected_evidence=connected_log,
        release_target="windows-x64",
        real_connected_session=True,
        sftp_browser_open=True,
        editor_tab_visible=True,
    )
    result = write_moba_text_release_evidence_bundle(plan, profile=profile)

    assert result.validation.passed is True
    assert result.validation.errors == []
    assert "moba-text-remote-edit.json" in result.files
    assert "evidence/connected-session.txt" in result.files
    assert Path(result.evidence_path).is_file()


def test_moba_text_cli_commands_are_registered() -> None:
    parser = build_parser()
    preview = parser.parse_args(["text", "preview", "README.md", "--json"])
    write = parser.parse_args(["text", "write", "note.txt", "--text", "hello", "--create"])
    diff = parser.parse_args(["text", "diff", "left.txt", "right.txt", "--json"])
    remote = parser.parse_args(["text", "remote-plan", "edge", "/etc/app.conf", "--json"])
    open_remote = parser.parse_args(["text", "open-remote", "edge", "/etc/app.conf", "--json"])
    save_review = parser.parse_args(
        [
            "text",
            "save-review",
            "edge",
            "/etc/app.conf",
            "--local",
            "app.conf.edit",
            "--original-remote-sha256",
            "a" * 64,
            "--current-remote-sha256",
            "a" * 64,
            "--json",
        ]
    )
    evidence_bundle = parser.parse_args(
        [
            "text",
            "evidence-bundle",
            "edge",
            "/etc/app.conf",
            "--out-dir",
            "artifact",
            "--local",
            "app.conf.edit",
            "--remote-sha256",
            "a" * 64,
            "--open-evidence",
            "open.txt",
            "--save-review-evidence",
            "save-review.txt",
            "--save-evidence",
            "save.txt",
            "--connected-evidence",
            "connected.txt",
            "--real-connected-session",
            "--sftp-browser-open",
            "--editor-tab-visible",
            "--json",
        ]
    )
    evidence = parser.parse_args(
        ["text", "evidence-verify", "--evidence", "moba-text-remote-edit.json", "--json"]
    )

    assert preview.func.__name__ == "cmd_text_preview"
    assert write.func.__name__ == "cmd_text_write"
    assert diff.func.__name__ == "cmd_text_diff"
    assert remote.func.__name__ == "cmd_text_remote_plan"
    assert open_remote.func.__name__ == "cmd_text_open_remote"
    assert save_review.func.__name__ == "cmd_text_save_review"
    assert evidence_bundle.func.__name__ == "cmd_text_evidence_bundle"
    assert evidence.func.__name__ == "cmd_text_evidence_verify"

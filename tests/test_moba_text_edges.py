from __future__ import annotations

import json
from pathlib import Path

import pytest

import remote_ops_workspace.moba_text as moba_text
from remote_ops_workspace.models import Profile


def _profile() -> Profile:
    return Profile(name="edge", protocol="ssh", host="edge.example", username="operator")


def test_text_value_objects_serialize(tmp_path: Path) -> None:
    missing_preview = moba_text.preview_text_document(tmp_path / "missing.txt")
    assert missing_preview.to_dict()["exists"] is False

    document = tmp_path / "document.txt"
    edit = moba_text.write_text_document(document, "created\n", create=True)
    assert edit.to_dict()["created"] is True

    other = tmp_path / "other.txt"
    other.write_text("other\n", encoding="utf-8")
    diff = moba_text.diff_text_documents(document, other)
    assert diff.to_dict()["equal"] is False

    remote = moba_text.build_remote_text_edit_plan(_profile(), "/etc/app.conf")
    assert remote.to_dict()["download"]["batch_commands"]

    digest = moba_text.preview_text_document(document).sha256
    review = moba_text.review_moba_remote_text_save(
        _profile(),
        "/etc/app.conf",
        document,
        original_remote_sha256=digest,
        current_remote_sha256=digest,
    )
    assert review.to_dict()["allowed"] is True

    validation = moba_text.MobaTextReleaseEvidenceValidation(
        evidence_path="evidence.json",
        assets_dir=".",
        passed=False,
        errors=["missing"],
        warnings=[],
        summary={},
    )
    assert validation.to_dict()["errors"] == ["missing"]

    bundle = moba_text.build_moba_text_release_evidence_bundle_plan(
        _profile(),
        "/etc/app.conf",
        out_dir=tmp_path / "bundle",
        local_path=document,
        remote_sha256=digest,
        open_evidence=tmp_path / "open.txt",
        save_review_evidence=tmp_path / "review.txt",
        save_evidence=tmp_path / "save.txt",
        connected_evidence=tmp_path / "connected.txt",
    )
    assert "flags are incomplete" in " ".join(bundle.notes)
    assert bundle.to_dict()["profile"] == "edge"
    result = moba_text.MobaTextReleaseEvidenceBundleResult(
        plan=bundle,
        evidence_path=bundle.evidence_path,
        files=("evidence.json",),
        validation=validation,
        notes=[],
    )
    assert result.to_dict()["validation"]["passed"] is False


def test_preview_rejects_invalid_limits_missing_files_and_directories(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="max_bytes must be positive"):
        moba_text.preview_text_document(tmp_path, max_bytes=0)
    with pytest.raises(ValueError, match="max_lines must be positive"):
        moba_text.preview_text_document(tmp_path, max_lines=0)
    with pytest.raises(ValueError, match="not a regular file"):
        moba_text.preview_text_document(tmp_path)


def test_preview_marks_invalid_utf8_and_line_limited_content(tmp_path: Path) -> None:
    invalid = tmp_path / "invalid.txt"
    invalid.write_bytes(b"\xff\xfe")
    preview = moba_text.preview_text_document(invalid)
    assert preview.binary is True
    assert preview.text == ""

    lines = tmp_path / "lines.txt"
    lines.write_text("one\ntwo\nthree\n", encoding="utf-8")
    limited = moba_text.preview_text_document(lines, max_lines=2)
    assert limited.text == "one\ntwo\n"
    assert limited.truncated is True


def test_write_rejects_unsafe_targets_and_hash_mismatch(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="NUL bytes"):
        moba_text.write_text_document(tmp_path / "nul.txt", "bad\x00text", create=True)
    with pytest.raises(ValueError, match="not a regular file"):
        moba_text.write_text_document(tmp_path, "text", force=True)
    with pytest.raises(ValueError, match="does not exist"):
        moba_text.write_text_document(tmp_path / "missing.txt", "text")

    document = tmp_path / "document.txt"
    document.write_text("old\n", encoding="utf-8")
    with pytest.raises(ValueError, match="expected sha256 does not match"):
        moba_text.write_text_document(document, "new\n", expected_sha256="a" * 64)


def test_write_supports_no_backup_and_unchanged_content(tmp_path: Path) -> None:
    document = tmp_path / "document.txt"
    document.write_text("old\n", encoding="utf-8")

    changed = moba_text.write_text_document(document, "new\n", force=True, backup=False)
    assert changed.changed is True
    assert changed.backup_path == ""
    unchanged = moba_text.write_text_document(document, "new\n")
    assert unchanged.changed is False
    assert any("unchanged" in note for note in unchanged.notes)


def test_diff_rejects_negative_context(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="must not be negative"):
        moba_text.diff_text_documents(tmp_path / "left", tmp_path / "right", context=-1)


def test_remote_save_review_records_matching_baseline(tmp_path: Path) -> None:
    local = tmp_path / "app.conf"
    local.write_text("enabled=true\n", encoding="utf-8")
    digest = "a" * 64
    review = moba_text.review_moba_remote_text_save(
        _profile(),
        "/etc/app.conf",
        local,
        original_remote_sha256=digest,
        current_remote_sha256=digest,
    )
    assert review.conflict is False
    assert any("still matches" in note for note in review.notes)


def test_bundle_writer_rejects_wrong_schema(tmp_path: Path) -> None:
    local = tmp_path / "local.txt"
    local.write_text("text\n", encoding="utf-8")
    plan = moba_text.build_moba_text_release_evidence_bundle_plan(
        _profile(),
        "/etc/app.conf",
        out_dir=tmp_path,
        local_path=local,
        remote_sha256="a" * 64,
        open_evidence=tmp_path / "open.txt",
        save_review_evidence=tmp_path / "review.txt",
        save_evidence=tmp_path / "save.txt",
        connected_evidence=tmp_path / "connected.txt",
    )
    plan.schema = "wrong"
    with pytest.raises(ValueError, match="bundle schema"):
        moba_text.write_moba_text_release_evidence_bundle(plan, profile=_profile())


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("{", "not valid JSON"),
        ("[]", "root must be a JSON object"),
    ],
)
def test_evidence_validator_rejects_malformed_roots(
    tmp_path: Path,
    content: str,
    message: str,
) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(content, encoding="utf-8")
    result = moba_text.validate_moba_text_release_evidence(evidence)
    assert any(message in error for error in result.errors)


def test_evidence_validator_reports_missing_contract_fields(tmp_path: Path) -> None:
    result = moba_text.validate_moba_text_release_evidence(tmp_path / "missing.json")
    assert result.passed is False
    assert any("cannot be read" in error for error in result.errors)
    assert any("editor_tab.schema" in error for error in result.errors)
    assert any("opened_from_sftp_browser" in error for error in result.errors)
    assert any("save_review.conflict_checked" in error for error in result.errors)
    assert any("connected_session.sftp_browser_open" in error for error in result.errors)
    assert any("connected_session.editor_tab_visible" in error for error in result.errors)


def test_invalid_evidence_document_exercises_action_contracts(tmp_path: Path) -> None:
    evidence = tmp_path / "invalid.json"
    evidence.write_text(
        json.dumps(
            {
                "schema": "wrong",
                "release_target": "target",
                "profile": "edge",
                "remote_path": "/etc/app.conf",
                "editor_tab": {},
                "open_action": {},
                "save_review": {},
                "save_action": {},
                "connected_session": {},
            }
        ),
        encoding="utf-8",
    )
    result = moba_text.validate_moba_text_release_evidence(evidence, assets_dir=tmp_path)
    assert result.passed is False
    assert len(result.errors) > 15


def test_cache_path_and_syntax_detection_cover_special_names() -> None:
    assert moba_text._remote_cache_path(_profile(), "/", None) == Path("edge-remote.txt.edit")
    assert moba_text._syntax_for_remote_path("/etc/sshd_config") == "ssh-config"
    assert moba_text._syntax_for_remote_path("/etc/site.nginx.conf") == "nginx"


def test_digest_mapping_and_text_helpers_fail_closed() -> None:
    errors: list[str] = []
    assert moba_text._optional_sha256("", "digest") == ""
    assert moba_text._required_sha256("\n", "digest", errors) == "\n"
    with pytest.raises(ValueError, match="control characters"):
        moba_text._required_sha256("\n", "digest")
    with pytest.raises(ValueError, match="lowercase 64-character"):
        moba_text._required_sha256("bad", "digest")
    assert moba_text._required_sha256("bad", "digest", errors) == "bad"
    assert moba_text._required_mapping({"item": []}, "item", errors) == {}
    assert moba_text._required_text({"item": "bad\ntext"}, "item", errors) == "bad\ntext"
    assert moba_text._required_text({}, "item", errors) == ""


def test_action_and_asset_evidence_fail_closed(tmp_path: Path) -> None:
    errors: list[str] = []
    moba_text._validate_action_evidence({}, tmp_path, errors, "action")
    assert "action.status must be passed" in errors
    assert "action.command must record the executed action" in errors

    absolute = tmp_path / "absolute.txt"
    moba_text._validate_asset_hash(tmp_path, str(absolute), "a" * 64, errors, "absolute")
    moba_text._validate_asset_hash(tmp_path, "missing.txt", "a" * 64, errors, "missing")
    directory = tmp_path / "directory"
    directory.mkdir()
    moba_text._validate_asset_hash(tmp_path, "directory", "a" * 64, errors, "directory")
    asset = tmp_path / "asset.txt"
    asset.write_text("content", encoding="utf-8")
    moba_text._validate_asset_hash(tmp_path, "asset.txt", "a" * 64, errors, "mismatch")

    assert any("absolute.evidence_file is invalid" in error for error in errors)
    assert any("missing.evidence_file does not exist" in error for error in errors)
    assert any("directory.evidence_file is not a file" in error for error in errors)
    assert any("mismatch.evidence_sha256 does not match" in error for error in errors)
    with pytest.raises(ValueError, match="inside assets_dir"):
        moba_text._resolve_evidence_asset(tmp_path, "../escape.txt")


def test_evidence_copy_rejects_missing_and_accepts_existing_target(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    with pytest.raises(ValueError, match="evidence file is missing"):
        moba_text._copy_evidence_asset(tmp_path / "missing.txt", evidence_dir, "open-action", tmp_path)

    target = evidence_dir / "open-action.txt"
    target.write_text("already present", encoding="utf-8")
    assert (
        moba_text._copy_evidence_asset(target, evidence_dir, "open-action", tmp_path)
        == "evidence/open-action.txt"
    )


def test_read_text_rejects_missing_directory_binary_and_invalid_utf8(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="does not exist"):
        moba_text._read_text(tmp_path / "missing.txt", encoding="utf-8")
    with pytest.raises(ValueError, match="not a regular file"):
        moba_text._read_text(tmp_path, encoding="utf-8")

    binary = tmp_path / "binary.txt"
    binary.write_bytes(b"a\x00b")
    with pytest.raises(ValueError, match="appears to be binary"):
        moba_text._read_text(binary, encoding="utf-8")

    invalid = tmp_path / "invalid.txt"
    invalid.write_bytes(b"\xff\xfe")
    with pytest.raises(ValueError, match="not utf-8 decodable"):
        moba_text._read_text(invalid, encoding="utf-8")

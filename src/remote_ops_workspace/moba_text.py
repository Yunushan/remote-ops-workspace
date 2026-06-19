from __future__ import annotations

import difflib
import hashlib
import json
import re
import shutil
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from typing import Any

from . import command_safety as safe
from .file_safety import write_json_atomic, write_text_atomic
from .file_transfer import SftpBatchPlan, build_sftp_get_plan, build_sftp_put_plan
from .models import Profile

MOBA_TEXT_EDITOR_TAB_SCHEMA = "row.moba-text.editor-tab.v1"
MOBA_TEXT_RELEASE_EVIDENCE_BUNDLE_SCHEMA = "row.moba-text.remote-edit-evidence-bundle.v1"
MOBA_TEXT_RELEASE_EVIDENCE_SCHEMA = "row.moba-text.remote-edit-evidence.v1"


@dataclass(slots=True)
class MobaTextPreview:
    path: str
    exists: bool
    size: int
    encoding: str
    line_count: int
    sha256: str
    text: str
    binary: bool
    truncated: bool
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "exists": self.exists,
            "size": self.size,
            "encoding": self.encoding,
            "line_count": self.line_count,
            "sha256": self.sha256,
            "text": self.text,
            "binary": self.binary,
            "truncated": self.truncated,
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobaTextEditResult:
    path: str
    created: bool
    changed: bool
    backup_path: str
    previous_sha256: str
    new_sha256: str
    line_count: int
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "created": self.created,
            "changed": self.changed,
            "backup_path": self.backup_path,
            "previous_sha256": self.previous_sha256,
            "new_sha256": self.new_sha256,
            "line_count": self.line_count,
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobaDiffResult:
    left_path: str
    right_path: str
    equal: bool
    left_sha256: str
    right_sha256: str
    unified_diff: str
    added_lines: int
    removed_lines: int
    hunk_count: int
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "left_path": self.left_path,
            "right_path": self.right_path,
            "equal": self.equal,
            "left_sha256": self.left_sha256,
            "right_sha256": self.right_sha256,
            "unified_diff": self.unified_diff,
            "added_lines": self.added_lines,
            "removed_lines": self.removed_lines,
            "hunk_count": self.hunk_count,
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobaRemoteTextEditPlan:
    profile_name: str
    remote_path: str
    local_path: str
    download_plan: SftpBatchPlan
    upload_plan: SftpBatchPlan
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile_name,
            "remote_path": self.remote_path,
            "local_path": self.local_path,
            "download": _batch_plan_dict(self.download_plan),
            "upload": _batch_plan_dict(self.upload_plan),
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobaTextEditorTabPlan:
    schema: str
    profile_name: str
    remote_path: str
    local_path: str
    syntax: str
    encoding: str
    remote_sha256: str
    opened_from_sftp_browser: bool
    download_plan: SftpBatchPlan
    save_plan: SftpBatchPlan
    conflict_policy: str
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "profile": self.profile_name,
            "remote_path": self.remote_path,
            "local_path": self.local_path,
            "syntax": self.syntax,
            "encoding": self.encoding,
            "remote_sha256": self.remote_sha256,
            "opened_from_sftp_browser": self.opened_from_sftp_browser,
            "download": _batch_plan_dict(self.download_plan),
            "save": _batch_plan_dict(self.save_plan),
            "conflict_policy": self.conflict_policy,
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobaRemoteTextSaveReview:
    profile_name: str
    remote_path: str
    local_path: str
    allowed: bool
    conflict: bool
    confirmation_required: bool
    prompt: str
    original_remote_sha256: str
    current_remote_sha256: str
    local_sha256: str
    upload_plan: SftpBatchPlan
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile_name,
            "remote_path": self.remote_path,
            "local_path": self.local_path,
            "allowed": self.allowed,
            "conflict": self.conflict,
            "confirmation_required": self.confirmation_required,
            "prompt": self.prompt,
            "original_remote_sha256": self.original_remote_sha256,
            "current_remote_sha256": self.current_remote_sha256,
            "local_sha256": self.local_sha256,
            "upload": _batch_plan_dict(self.upload_plan),
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobaTextReleaseEvidenceValidation:
    evidence_path: str
    assets_dir: str
    passed: bool
    errors: list[str]
    warnings: list[str]
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_path": self.evidence_path,
            "assets_dir": self.assets_dir,
            "passed": self.passed,
            "errors": self.errors,
            "warnings": self.warnings,
            "summary": self.summary,
        }


@dataclass(slots=True)
class MobaTextReleaseEvidenceBundlePlan:
    schema: str
    out_dir: str
    evidence_path: str
    release_target: str
    profile_name: str
    remote_path: str
    local_path: str
    remote_sha256: str
    encoding: str
    open_evidence_source: str
    save_review_evidence_source: str
    save_evidence_source: str
    connected_evidence_source: str
    open_command: str
    save_review_command: str
    save_command: str
    real_connected_session: bool
    sftp_browser_open: bool
    editor_tab_visible: bool
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "out_dir": self.out_dir,
            "evidence_path": self.evidence_path,
            "release_target": self.release_target,
            "profile": self.profile_name,
            "remote_path": self.remote_path,
            "local_path": self.local_path,
            "remote_sha256": self.remote_sha256,
            "encoding": self.encoding,
            "open_evidence_source": self.open_evidence_source,
            "save_review_evidence_source": self.save_review_evidence_source,
            "save_evidence_source": self.save_evidence_source,
            "connected_evidence_source": self.connected_evidence_source,
            "open_command": self.open_command,
            "save_review_command": self.save_review_command,
            "save_command": self.save_command,
            "real_connected_session": self.real_connected_session,
            "sftp_browser_open": self.sftp_browser_open,
            "editor_tab_visible": self.editor_tab_visible,
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobaTextReleaseEvidenceBundleResult:
    plan: MobaTextReleaseEvidenceBundlePlan
    evidence_path: str
    files: tuple[str, ...]
    validation: MobaTextReleaseEvidenceValidation
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan": self.plan.to_dict(),
            "evidence_path": self.evidence_path,
            "files": list(self.files),
            "validation": self.validation.to_dict(),
            "notes": self.notes,
        }


def preview_text_document(
    path: Path | str,
    *,
    max_bytes: int = 65536,
    max_lines: int = 200,
    encoding: str = "utf-8",
) -> MobaTextPreview:
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    if max_lines <= 0:
        raise ValueError("max_lines must be positive")
    target = _path(path, "text preview path")
    if not target.exists():
        return MobaTextPreview(str(target), False, 0, encoding, 0, "", "", False, False, ["file does not exist"])
    if not target.is_file():
        raise ValueError(f"text preview path is not a regular file: {target}")
    size = target.stat().st_size
    with target.open("rb") as handle:
        payload = handle.read(max_bytes + 1)
    truncated = len(payload) > max_bytes
    payload = payload[:max_bytes]
    binary = b"\x00" in payload
    notes = ["MobaTextEditor-style local text preview."]
    text = ""
    line_count = 0
    if not binary:
        try:
            text = payload.decode(encoding)
        except UnicodeDecodeError:
            binary = True
    if binary:
        notes.append("binary or non-decodable payload; text preview suppressed")
    else:
        lines = text.splitlines()
        line_count = len(_read_text(target, encoding=encoding).splitlines())
        if len(lines) > max_lines:
            text = "\n".join(lines[:max_lines]) + "\n"
            truncated = True
        notes.append("Use row text write with --expected-sha256 or --force before saving changes.")
    return MobaTextPreview(
        path=str(target),
        exists=True,
        size=size,
        encoding=encoding,
        line_count=line_count,
        sha256=_sha256_path(target),
        text=text,
        binary=binary,
        truncated=truncated,
        notes=notes,
    )


def write_text_document(
    path: Path | str,
    text: str,
    *,
    create: bool = False,
    force: bool = False,
    expected_sha256: str | None = None,
    backup: bool = True,
    encoding: str = "utf-8",
) -> MobaTextEditResult:
    target = _path(path, "text write path")
    new_text = str(text)
    if "\x00" in new_text:
        raise ValueError("text document must not contain NUL bytes")
    existed = target.exists()
    if existed and not target.is_file():
        raise ValueError(f"text write path is not a regular file: {target}")
    if not existed and not create:
        raise ValueError("text write target does not exist; pass --create to create it")
    previous_sha256 = _sha256_path(target) if existed else ""
    if expected_sha256 and previous_sha256 != expected_sha256:
        raise ValueError("text write expected sha256 does not match current file")
    previous_text = _read_text(target, encoding=encoding) if existed else ""
    changed = previous_text != new_text
    if existed and changed and not force and not expected_sha256:
        raise ValueError("text write would modify an existing file; pass --force or --expected-sha256")
    backup_path = ""
    if existed and changed and backup:
        backup_target = target.with_name(f"{target.name}.bak")
        write_text_atomic(backup_target, previous_text)
        backup_path = str(backup_target)
    write_text_atomic(target, new_text)
    new_sha256 = _sha256_path(target)
    notes = ["MobaTextEditor-style guarded local save."]
    if backup_path:
        notes.append("Previous content was saved to a .bak file.")
    if not changed:
        notes.append("Content was unchanged.")
    return MobaTextEditResult(
        path=str(target),
        created=not existed,
        changed=changed,
        backup_path=backup_path,
        previous_sha256=previous_sha256,
        new_sha256=new_sha256,
        line_count=len(new_text.splitlines()),
        notes=notes,
    )


def diff_text_documents(
    left: Path | str,
    right: Path | str,
    *,
    context: int = 3,
    encoding: str = "utf-8",
) -> MobaDiffResult:
    if context < 0:
        raise ValueError("diff context must not be negative")
    left_path = _path(left, "left diff path")
    right_path = _path(right, "right diff path")
    left_text = _read_text(left_path, encoding=encoding)
    right_text = _read_text(right_path, encoding=encoding)
    left_lines = left_text.splitlines(keepends=True)
    right_lines = right_text.splitlines(keepends=True)
    diff_lines = list(
        difflib.unified_diff(
            left_lines,
            right_lines,
            fromfile=str(left_path),
            tofile=str(right_path),
            n=context,
        )
    )
    unified = "".join(diff_lines)
    added = sum(1 for line in diff_lines if line.startswith("+") and not line.startswith("+++"))
    removed = sum(1 for line in diff_lines if line.startswith("-") and not line.startswith("---"))
    hunks = sum(1 for line in diff_lines if line.startswith("@@"))
    return MobaDiffResult(
        left_path=str(left_path),
        right_path=str(right_path),
        equal=left_text == right_text,
        left_sha256=_sha256_path(left_path),
        right_sha256=_sha256_path(right_path),
        unified_diff=unified,
        added_lines=added,
        removed_lines=removed,
        hunk_count=hunks,
        notes=["MobaDiff-style unified local text diff."],
    )


def build_remote_text_edit_plan(
    profile: Profile,
    remote_path: str,
    *,
    local_path: Path | str | None = None,
) -> MobaRemoteTextEditPlan:
    remote = safe.option_value(remote_path, "remote text path")
    local = _remote_cache_path(profile, remote, local_path)
    download = build_sftp_get_plan(profile, remote, local_path=local, allow_overwrite=True)
    upload = build_sftp_put_plan(profile, local, remote_path=remote, allow_overwrite=True)
    notes = [
        "MobaTextEditor-style remote edit staging plan.",
        "Run the download plan, edit the local cache with row text write, inspect with row text diff, then run the upload plan.",
        "SFTP plans are explicit batch commands; no shell command string is used.",
    ]
    return MobaRemoteTextEditPlan(
        profile_name=profile.name,
        remote_path=remote,
        local_path=str(local),
        download_plan=download,
        upload_plan=upload,
        notes=notes,
    )


def build_moba_text_editor_tab_plan(
    profile: Profile,
    remote_path: str,
    *,
    local_path: Path | str | None = None,
    remote_sha256: str = "",
    encoding: str = "utf-8",
) -> MobaTextEditorTabPlan:
    remote = safe.option_value(remote_path, "remote text path")
    local = _remote_cache_path(profile, remote, local_path)
    remote_digest = _optional_sha256(remote_sha256, "remote sha256")
    download = build_sftp_get_plan(profile, remote, local_path=local, allow_overwrite=True)
    save = build_sftp_put_plan(profile, local, remote_path=remote, allow_overwrite=True)
    syntax = _syntax_for_remote_path(remote)
    notes = [
        "MobaTextEditor-style connected editor tab opened from the SSH/SFTP browser.",
        "Direct open downloads the remote file into a local edit cache using the same SFTP profile parameters.",
        "Save must run a conflict review against the original remote SHA-256 before upload.",
    ]
    return MobaTextEditorTabPlan(
        schema=MOBA_TEXT_EDITOR_TAB_SCHEMA,
        profile_name=profile.name,
        remote_path=remote,
        local_path=str(local),
        syntax=syntax,
        encoding=safe.option_value(encoding, "text encoding"),
        remote_sha256=remote_digest,
        opened_from_sftp_browser=True,
        download_plan=download,
        save_plan=save,
        conflict_policy="sha256-match-or-force",
        notes=notes,
    )


def review_moba_remote_text_save(
    profile: Profile,
    remote_path: str,
    local_path: Path | str,
    *,
    original_remote_sha256: str,
    current_remote_sha256: str,
    force: bool = False,
) -> MobaRemoteTextSaveReview:
    remote = safe.option_value(remote_path, "remote text path")
    local = _path(local_path, "local text cache path")
    original_digest = _required_sha256(original_remote_sha256, "original remote sha256")
    current_digest = _required_sha256(current_remote_sha256, "current remote sha256")
    local_digest = _sha256_path(local)
    conflict = original_digest != current_digest
    allowed = not conflict or force
    prompt = ""
    notes = ["MobaTextEditor-style remote save conflict review."]
    if conflict:
        prompt = (
            "Remote file changed since it was opened; review the diff and pass --force "
            "only if overwriting the remote version is intended."
        )
        notes.append("Remote SHA-256 differs from the editor-tab open baseline.")
    else:
        notes.append("Remote SHA-256 still matches the editor-tab open baseline.")
    upload = build_sftp_put_plan(profile, local, remote_path=remote, allow_overwrite=True)
    return MobaRemoteTextSaveReview(
        profile_name=profile.name,
        remote_path=remote,
        local_path=str(local),
        allowed=allowed,
        conflict=conflict,
        confirmation_required=conflict and not force,
        prompt=prompt,
        original_remote_sha256=original_digest,
        current_remote_sha256=current_digest,
        local_sha256=local_digest,
        upload_plan=upload,
        notes=notes,
    )


def build_moba_text_release_evidence_bundle_plan(
    profile: Profile,
    remote_path: str,
    *,
    out_dir: Path,
    local_path: Path | str,
    remote_sha256: str,
    open_evidence: Path,
    save_review_evidence: Path,
    save_evidence: Path,
    connected_evidence: Path,
    release_target: str = "local-bundle",
    encoding: str = "utf-8",
    open_command: str = "",
    save_review_command: str = "",
    save_command: str = "",
    real_connected_session: bool = False,
    sftp_browser_open: bool = False,
    editor_tab_visible: bool = False,
) -> MobaTextReleaseEvidenceBundlePlan:
    tab = build_moba_text_editor_tab_plan(
        profile,
        remote_path,
        local_path=local_path,
        remote_sha256=remote_sha256,
        encoding=encoding,
    )
    root = Path(out_dir).expanduser()
    evidence_path = root / "moba-text-remote-edit.json"
    notes = [
        "Bundle plan writes MobaTextEditor-style connected remote-edit release evidence from supplied proof files.",
        "Production parity requires the supplied evidence files to come from a real connected SSH/SFTP browser editor session.",
    ]
    if not real_connected_session or not sftp_browser_open or not editor_tab_visible:
        notes.append("Connected-session flags are incomplete; the verifier will fail until real connected evidence is asserted.")
    return MobaTextReleaseEvidenceBundlePlan(
        schema=MOBA_TEXT_RELEASE_EVIDENCE_BUNDLE_SCHEMA,
        out_dir=str(root),
        evidence_path=str(evidence_path),
        release_target=safe.clean_text(release_target, "release target"),
        profile_name=profile.name,
        remote_path=tab.remote_path,
        local_path=tab.local_path,
        remote_sha256=tab.remote_sha256,
        encoding=tab.encoding,
        open_evidence_source=str(Path(open_evidence).expanduser()),
        save_review_evidence_source=str(Path(save_review_evidence).expanduser()),
        save_evidence_source=str(Path(save_evidence).expanduser()),
        connected_evidence_source=str(Path(connected_evidence).expanduser()),
        open_command=safe.clean_text(open_command or _joined_batch_commands(tab.download_plan), "open command"),
        save_review_command=safe.clean_text(
            save_review_command or f"row text save-review {profile.name} {tab.remote_path}",
            "save review command",
        ),
        save_command=safe.clean_text(save_command or _joined_batch_commands(tab.save_plan), "save command"),
        real_connected_session=bool(real_connected_session),
        sftp_browser_open=bool(sftp_browser_open),
        editor_tab_visible=bool(editor_tab_visible),
        notes=notes,
    )


def write_moba_text_release_evidence_bundle(
    plan: MobaTextReleaseEvidenceBundlePlan,
    *,
    profile: Profile,
) -> MobaTextReleaseEvidenceBundleResult:
    if plan.schema != MOBA_TEXT_RELEASE_EVIDENCE_BUNDLE_SCHEMA:
        raise ValueError(f"text release evidence bundle schema must be {MOBA_TEXT_RELEASE_EVIDENCE_BUNDLE_SCHEMA}")
    root = Path(plan.out_dir)
    evidence_dir = root / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    tab = build_moba_text_editor_tab_plan(
        profile,
        plan.remote_path,
        local_path=plan.local_path,
        remote_sha256=plan.remote_sha256,
        encoding=plan.encoding,
    )
    copied: dict[str, str] = {
        "open_action": _copy_evidence_asset(
            Path(plan.open_evidence_source),
            evidence_dir,
            "open-action",
            root,
        ),
        "save_review": _copy_evidence_asset(
            Path(plan.save_review_evidence_source),
            evidence_dir,
            "save-review",
            root,
        ),
        "save_action": _copy_evidence_asset(
            Path(plan.save_evidence_source),
            evidence_dir,
            "save-action",
            root,
        ),
        "connected_session": _copy_evidence_asset(
            Path(plan.connected_evidence_source),
            evidence_dir,
            "connected-session",
            root,
        ),
    }
    payload = {
        "schema": MOBA_TEXT_RELEASE_EVIDENCE_SCHEMA,
        "release_target": plan.release_target,
        "profile": plan.profile_name,
        "remote_path": plan.remote_path,
        "editor_tab": tab.to_dict(),
        "open_action": {
            "status": "passed",
            "command": plan.open_command,
            "evidence_file": copied["open_action"],
            "evidence_sha256": _sha256_path(root / copied["open_action"]),
        },
        "save_review": {
            "status": "passed",
            "conflict_checked": True,
            "command": plan.save_review_command,
            "evidence_file": copied["save_review"],
            "evidence_sha256": _sha256_path(root / copied["save_review"]),
        },
        "save_action": {
            "status": "passed",
            "command": plan.save_command,
            "evidence_file": copied["save_action"],
            "evidence_sha256": _sha256_path(root / copied["save_action"]),
        },
        "connected_session": {
            "real_connected_session": plan.real_connected_session,
            "sftp_browser_open": plan.sftp_browser_open,
            "editor_tab_visible": plan.editor_tab_visible,
            "evidence_file": copied["connected_session"],
            "evidence_sha256": _sha256_path(root / copied["connected_session"]),
        },
    }
    target_evidence_path = Path(plan.evidence_path)
    write_json_atomic(target_evidence_path, payload, private=False)
    validation = validate_moba_text_release_evidence(target_evidence_path, assets_dir=root)
    files = tuple(
        dict.fromkeys(
            (
                copied["open_action"],
                copied["save_review"],
                copied["save_action"],
                copied["connected_session"],
                _relative_to_root(target_evidence_path, root),
            )
        )
    )
    return MobaTextReleaseEvidenceBundleResult(
        plan=plan,
        evidence_path=str(target_evidence_path),
        files=files,
        validation=validation,
        notes=list(plan.notes),
    )


def validate_moba_text_release_evidence(
    evidence_path: Path,
    *,
    assets_dir: Path | None = None,
) -> MobaTextReleaseEvidenceValidation:
    target_evidence_path = Path(evidence_path)
    root = Path(assets_dir) if assets_dir is not None else target_evidence_path.parent
    errors: list[str] = []
    warnings: list[str] = []
    summary: dict[str, Any] = {
        "schema": "",
        "release_target": "",
        "profile": "",
        "remote_path": "",
        "syntax": "",
    }
    try:
        data = json.loads(target_evidence_path.read_text(encoding="utf-8"))
    except OSError as exc:
        errors.append(f"evidence file cannot be read: {exc}")
        data = {}
    except json.JSONDecodeError as exc:
        errors.append(f"evidence file is not valid JSON: {exc}")
        data = {}
    if not isinstance(data, dict):
        errors.append("evidence root must be a JSON object")
        data = {}

    schema = str(data.get("schema") or data.get("schema_version") or "")
    summary["schema"] = schema
    if schema != MOBA_TEXT_RELEASE_EVIDENCE_SCHEMA:
        errors.append(f"schema must be {MOBA_TEXT_RELEASE_EVIDENCE_SCHEMA}")
    summary["release_target"] = _required_text(data, "release_target", errors)
    summary["profile"] = _required_text(data, "profile", errors)
    summary["remote_path"] = _required_text(data, "remote_path", errors)

    editor_tab = _required_mapping(data, "editor_tab", errors)
    if str(editor_tab.get("schema") or "") != MOBA_TEXT_EDITOR_TAB_SCHEMA:
        errors.append(f"editor_tab.schema must be {MOBA_TEXT_EDITOR_TAB_SCHEMA}")
    if editor_tab.get("opened_from_sftp_browser") is not True:
        errors.append("editor_tab.opened_from_sftp_browser must be true")
    syntax = _required_text(editor_tab, "syntax", errors, prefix="editor_tab.")
    summary["syntax"] = syntax
    _required_text(editor_tab, "local_path", errors, prefix="editor_tab.")
    _required_sha256(_required_text(editor_tab, "remote_sha256", errors, prefix="editor_tab."), "editor_tab.remote_sha256", errors)

    open_action = _required_mapping(data, "open_action", errors)
    _validate_action_evidence(open_action, root, errors, "open_action")
    save_review = _required_mapping(data, "save_review", errors)
    if save_review.get("status") != "passed":
        errors.append("save_review.status must be passed")
    if save_review.get("conflict_checked") is not True:
        errors.append("save_review.conflict_checked must be true")
    _validate_action_evidence(save_review, root, errors, "save_review")
    save_action = _required_mapping(data, "save_action", errors)
    _validate_action_evidence(save_action, root, errors, "save_action")

    connected = _required_mapping(data, "connected_session", errors)
    if connected.get("real_connected_session") is not True:
        errors.append("connected_session.real_connected_session must be true")
    if connected.get("sftp_browser_open") is not True:
        errors.append("connected_session.sftp_browser_open must be true")
    if connected.get("editor_tab_visible") is not True:
        errors.append("connected_session.editor_tab_visible must be true")
    connected_evidence = _required_text(connected, "evidence_file", errors, prefix="connected_session.")
    connected_digest = _required_sha256(
        _required_text(connected, "evidence_sha256", errors, prefix="connected_session."),
        "connected_session.evidence_sha256",
        errors,
    )
    if connected_evidence and connected_digest:
        _validate_asset_hash(root, connected_evidence, connected_digest, errors, "connected_session")

    return MobaTextReleaseEvidenceValidation(
        evidence_path=str(target_evidence_path),
        assets_dir=str(root),
        passed=not errors,
        errors=errors,
        warnings=warnings,
        summary=summary,
    )


def _remote_cache_path(profile: Profile, remote_path: str, local_path: Path | str | None) -> Path:
    if local_path is not None:
        return _path(local_path, "local text cache path")
    name = PurePosixPath(remote_path).name or "remote.txt"
    safe_name = "".join(char if char.isalnum() or char in "._-" else "_" for char in name)
    return Path(f"{profile.name}-{safe_name}.edit")


def _syntax_for_remote_path(remote_path: str) -> str:
    path = PurePosixPath(remote_path)
    name = path.name.lower()
    if name in {"authorized_keys", "known_hosts", "sshd_config", "ssh_config"}:
        return "ssh-config"
    suffixes = "".join(path.suffixes).lower()
    compound = {
        ".dockerfile": "dockerfile",
        ".nginx.conf": "nginx",
        ".service": "systemd",
    }
    if suffixes in compound:
        return compound[suffixes]
    mapping = {
        ".bash": "shell",
        ".c": "c",
        ".conf": "ini",
        ".cpp": "cpp",
        ".css": "css",
        ".csv": "csv",
        ".go": "go",
        ".h": "c",
        ".hpp": "cpp",
        ".htm": "html",
        ".html": "html",
        ".ini": "ini",
        ".java": "java",
        ".js": "javascript",
        ".json": "json",
        ".log": "log",
        ".md": "markdown",
        ".php": "php",
        ".ps1": "powershell",
        ".py": "python",
        ".rb": "ruby",
        ".rs": "rust",
        ".sh": "shell",
        ".sql": "sql",
        ".toml": "toml",
        ".ts": "typescript",
        ".txt": "plain-text",
        ".xml": "xml",
        ".yaml": "yaml",
        ".yml": "yaml",
    }
    return mapping.get(path.suffix.lower(), "plain-text")


def _optional_sha256(value: str | None, label: str) -> str:
    if not value:
        return ""
    return _required_sha256(value, label)


def _required_sha256(value: str, label: str, errors: list[str] | None = None) -> str:
    try:
        text = safe.clean_text(str(value), label)
    except ValueError as exc:
        if errors is not None:
            errors.append(f"{label} is invalid: {exc}")
            return str(value)
        raise
    if re.fullmatch(r"[0-9a-f]{64}", text):
        return text
    message = f"{label} must be a lowercase 64-character SHA-256 digest"
    if errors is not None:
        errors.append(message)
        return text
    raise ValueError(message)


def _required_mapping(data: dict[str, Any], key: str, errors: list[str]) -> dict[str, Any]:
    value = data.get(key)
    if isinstance(value, dict):
        return value
    errors.append(f"{key} must be a JSON object")
    return {}


def _required_text(
    data: dict[str, Any],
    key: str,
    errors: list[str],
    *,
    prefix: str = "",
) -> str:
    value = data.get(key)
    if isinstance(value, str) and value.strip():
        try:
            return safe.clean_text(value, f"{prefix}{key}")
        except ValueError as exc:
            errors.append(f"{prefix}{key} is invalid: {exc}")
            return value
    errors.append(f"{prefix}{key} must be a non-empty string")
    return ""


def _validate_action_evidence(action: dict[str, Any], assets_dir: Path, errors: list[str], label: str) -> None:
    if action.get("status") != "passed":
        errors.append(f"{label}.status must be passed")
    command = _required_text(action, "command", errors, prefix=f"{label}.")
    if not command:
        errors.append(f"{label}.command must record the executed action")
    evidence_file = _required_text(action, "evidence_file", errors, prefix=f"{label}.")
    digest = _required_sha256(
        _required_text(action, "evidence_sha256", errors, prefix=f"{label}."),
        f"{label}.evidence_sha256",
        errors,
    )
    if evidence_file and digest:
        _validate_asset_hash(assets_dir, evidence_file, digest, errors, label)


def _copy_evidence_asset(source: Path, evidence_dir: Path, label: str, root: Path) -> str:
    resolved_source = source.expanduser()
    if not resolved_source.is_file():
        raise ValueError(f"{label} evidence file is missing: {resolved_source}")
    suffix = resolved_source.suffix if resolved_source.suffix else ".txt"
    target = evidence_dir / f"{label}{suffix}"
    if resolved_source.resolve() != target.resolve():
        shutil.copy2(resolved_source, target)
    return _relative_to_root(target, root)


def _relative_to_root(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _joined_batch_commands(plan: SftpBatchPlan) -> str:
    return " && ".join(plan.batch_commands)


def _validate_asset_hash(
    assets_dir: Path,
    evidence_file: str,
    expected_sha256: str,
    errors: list[str],
    label: str,
) -> None:
    try:
        asset = _resolve_evidence_asset(assets_dir, evidence_file)
    except ValueError as exc:
        errors.append(f"{label}.evidence_file is invalid: {exc}")
        return
    if not asset.exists():
        errors.append(f"{label}.evidence_file does not exist: {asset}")
        return
    if not asset.is_file():
        errors.append(f"{label}.evidence_file is not a file: {asset}")
        return
    actual = _sha256_path(asset)
    if actual != expected_sha256:
        errors.append(f"{label}.evidence_sha256 does not match {asset.name}")


def _resolve_evidence_asset(assets_dir: Path, evidence_file: str) -> Path:
    relative = Path(safe.path_arg(evidence_file, "evidence file"))
    if relative.is_absolute():
        raise ValueError("must be relative to assets_dir")
    root = assets_dir.resolve()
    target = (root / relative).resolve()
    if root != target and root not in target.parents:
        raise ValueError("must stay inside assets_dir")
    return target


def _read_text(path: Path, *, encoding: str) -> str:
    if not path.exists():
        raise ValueError(f"text file does not exist: {path}")
    if not path.is_file():
        raise ValueError(f"text path is not a regular file: {path}")
    payload = path.read_bytes()
    if b"\x00" in payload:
        raise ValueError(f"text path appears to be binary: {path}")
    try:
        return payload.decode(encoding)
    except UnicodeDecodeError as exc:
        raise ValueError(f"text path is not {encoding} decodable: {path}") from exc


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _path(path: Path | str, label: str) -> Path:
    return Path(safe.path_arg(str(path), label))


def _batch_plan_dict(plan: SftpBatchPlan) -> dict[str, Any]:
    return {
        "profile": plan.profile_name,
        "command": plan.command,
        "batch_commands": plan.batch_commands,
        "notes": plan.notes,
        "destructive": plan.destructive,
        "force": plan.force,
        "safety_warnings": plan.safety_warnings,
    }

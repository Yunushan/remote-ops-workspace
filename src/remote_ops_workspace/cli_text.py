"""Text editor and remote-edit evidence commands for the CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .cli_transfers import _print_sftp_plan
from .moba_text import (
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
from .storage import ProfileStore


def add_text_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    text = sub.add_parser("text", help="preview, edit and diff local or SFTP-staged text files")
    text_sub = text.add_subparsers(required=True)
    text_preview = text_sub.add_parser("preview", help="preview a local text file with hash evidence")
    text_preview.add_argument("path", type=Path)
    text_preview.add_argument("--bytes", type=int, default=65536)
    text_preview.add_argument("--lines", type=int, default=200)
    text_preview.add_argument("--encoding", default="utf-8")
    text_preview.add_argument("--json", action="store_true")
    text_preview.set_defaults(func=cmd_text_preview)
    text_write = text_sub.add_parser("write", help="write a local text file with guardrails and optional backup")
    text_write.add_argument("path", type=Path)
    text_source = text_write.add_mutually_exclusive_group(required=True)
    text_source.add_argument("--text")
    text_source.add_argument("--text-file", type=Path)
    text_write.add_argument("--create", action="store_true")
    text_write.add_argument("--force", action="store_true")
    text_write.add_argument("--expected-sha256")
    text_write.add_argument("--no-backup", action="store_true")
    text_write.add_argument("--encoding", default="utf-8")
    text_write.add_argument("--json", action="store_true")
    text_write.set_defaults(func=cmd_text_write)
    text_diff = text_sub.add_parser("diff", help="show a unified diff between two local text files")
    text_diff.add_argument("left", type=Path)
    text_diff.add_argument("right", type=Path)
    text_diff.add_argument("--context", type=int, default=3)
    text_diff.add_argument("--encoding", default="utf-8")
    text_diff.add_argument("--json", action="store_true")
    text_diff.set_defaults(func=cmd_text_diff)
    text_remote = text_sub.add_parser("remote-plan", help="build SFTP get/put plans for editing a remote text file")
    text_remote.add_argument("profile")
    text_remote.add_argument("remote")
    text_remote.add_argument("--local", type=Path)
    text_remote.add_argument("--json", action="store_true")
    text_remote.set_defaults(func=cmd_text_remote_plan)
    text_open_remote = text_sub.add_parser(
        "open-remote",
        help="build a connected SFTP-browser editor-tab plan for a remote text file",
    )
    text_open_remote.add_argument("profile")
    text_open_remote.add_argument("remote")
    text_open_remote.add_argument("--local", type=Path)
    text_open_remote.add_argument("--remote-sha256", default="")
    text_open_remote.add_argument("--encoding", default="utf-8")
    text_open_remote.add_argument("--json", action="store_true")
    text_open_remote.set_defaults(func=cmd_text_open_remote)
    text_save_review = text_sub.add_parser(
        "save-review",
        help="review a remote text save against the editor-tab open baseline",
    )
    text_save_review.add_argument("profile")
    text_save_review.add_argument("remote")
    text_save_review.add_argument("--local", required=True, type=Path)
    text_save_review.add_argument("--original-remote-sha256", required=True)
    text_save_review.add_argument("--current-remote-sha256", required=True)
    text_save_review.add_argument("--force", action="store_true")
    text_save_review.add_argument("--json", action="store_true")
    text_save_review.set_defaults(func=cmd_text_save_review)
    text_evidence_bundle = text_sub.add_parser(
        "evidence-bundle",
        help="assemble MobaTextEditor-style connected remote-edit release evidence",
    )
    text_evidence_bundle.add_argument("profile")
    text_evidence_bundle.add_argument("remote")
    text_evidence_bundle.add_argument("--out-dir", required=True, type=Path)
    text_evidence_bundle.add_argument("--local", required=True, type=Path)
    text_evidence_bundle.add_argument("--remote-sha256", required=True)
    text_evidence_bundle.add_argument("--open-evidence", required=True, type=Path)
    text_evidence_bundle.add_argument("--save-review-evidence", required=True, type=Path)
    text_evidence_bundle.add_argument("--save-evidence", required=True, type=Path)
    text_evidence_bundle.add_argument("--connected-evidence", required=True, type=Path)
    text_evidence_bundle.add_argument("--release-target", default="local-bundle")
    text_evidence_bundle.add_argument("--encoding", default="utf-8")
    text_evidence_bundle.add_argument("--open-command", default="")
    text_evidence_bundle.add_argument("--save-review-command", default="")
    text_evidence_bundle.add_argument("--save-command", default="")
    text_evidence_bundle.add_argument("--real-connected-session", action="store_true")
    text_evidence_bundle.add_argument("--sftp-browser-open", action="store_true")
    text_evidence_bundle.add_argument("--editor-tab-visible", action="store_true")
    text_evidence_bundle.add_argument("--json", action="store_true")
    text_evidence_bundle.set_defaults(func=cmd_text_evidence_bundle)
    text_evidence = text_sub.add_parser(
        "evidence-verify",
        help="verify MobaTextEditor-style connected remote-edit release evidence",
    )
    text_evidence.add_argument("--evidence", required=True, type=Path)
    text_evidence.add_argument("--assets-dir", type=Path)
    text_evidence.add_argument("--json", action="store_true")
    text_evidence.set_defaults(func=cmd_text_evidence_verify)


def cmd_text_preview(args: argparse.Namespace) -> int:
    preview = preview_text_document(
        args.path,
        max_bytes=args.bytes,
        max_lines=args.lines,
        encoding=args.encoding,
    )
    if args.json:
        print(json.dumps(preview.to_dict(), indent=2, sort_keys=True))
        return 0 if preview.exists and not preview.binary else 1
    print(f"{preview.path}: {'present' if preview.exists else 'missing'}")
    if preview.exists:
        print(f"size: {preview.size}")
        print(f"sha256: {preview.sha256}")
        print(f"lines: {preview.line_count}")
    for note in preview.notes:
        print(f"note: {note}")
    if preview.text:
        print("preview:")
        print(preview.text.rstrip())
    return 0 if preview.exists and not preview.binary else 1


def cmd_text_write(args: argparse.Namespace) -> int:
    text = args.text if args.text is not None else args.text_file.read_bytes().decode(args.encoding)
    result = write_text_document(
        args.path,
        text,
        create=args.create,
        force=args.force,
        expected_sha256=args.expected_sha256,
        backup=not args.no_backup,
        encoding=args.encoding,
    )
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
        return 0
    print(f"written: {result.path}")
    print(f"changed: {'yes' if result.changed else 'no'}")
    print(f"sha256: {result.new_sha256}")
    if result.backup_path:
        print(f"backup: {result.backup_path}")
    for note in result.notes:
        print(f"note: {note}")
    return 0


def cmd_text_diff(args: argparse.Namespace) -> int:
    result = diff_text_documents(args.left, args.right, context=args.context, encoding=args.encoding)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"equal: {'yes' if result.equal else 'no'}")
        print(f"added: {result.added_lines} removed: {result.removed_lines} hunks: {result.hunk_count}")
        if result.unified_diff:
            print(result.unified_diff.rstrip())
    return 0 if result.equal else 1


def cmd_text_remote_plan(args: argparse.Namespace) -> int:
    profile = ProfileStore().get(args.profile)
    plan = build_remote_text_edit_plan(profile, args.remote, local_path=args.local)
    if args.json:
        print(json.dumps(plan.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"remote: {plan.remote_path}")
        print(f"local: {plan.local_path}")
        print("download:")
        _print_sftp_plan(plan.download_plan, show_batch=True)
        print("upload:")
        _print_sftp_plan(plan.upload_plan, show_batch=True)
        for note in plan.notes:
            print(f"note: {note}")
    return 0


def cmd_text_open_remote(args: argparse.Namespace) -> int:
    profile = ProfileStore().get(args.profile)
    plan = build_moba_text_editor_tab_plan(
        profile,
        args.remote,
        local_path=args.local,
        remote_sha256=args.remote_sha256,
        encoding=args.encoding,
    )
    if args.json:
        print(json.dumps(plan.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"remote: {plan.remote_path}")
        print(f"local: {plan.local_path}")
        print(f"syntax: {plan.syntax}")
        print(f"encoding: {plan.encoding}")
        if plan.remote_sha256:
            print(f"remote sha256: {plan.remote_sha256}")
        print("open/download:")
        _print_sftp_plan(plan.download_plan, show_batch=True)
        print("save/upload:")
        _print_sftp_plan(plan.save_plan, show_batch=True)
        print(f"conflict policy: {plan.conflict_policy}")
        for note in plan.notes:
            print(f"note: {note}")
    return 0


def cmd_text_save_review(args: argparse.Namespace) -> int:
    profile = ProfileStore().get(args.profile)
    review = review_moba_remote_text_save(
        profile,
        args.remote,
        args.local,
        original_remote_sha256=args.original_remote_sha256,
        current_remote_sha256=args.current_remote_sha256,
        force=args.force,
    )
    if args.json:
        print(json.dumps(review.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"remote: {review.remote_path}")
        print(f"local: {review.local_path}")
        print(f"allowed: {'yes' if review.allowed else 'no'}")
        print(f"conflict: {'yes' if review.conflict else 'no'}")
        print(f"confirmation required: {'yes' if review.confirmation_required else 'no'}")
        print(f"local sha256: {review.local_sha256}")
        if review.prompt:
            print(f"prompt: {review.prompt}")
        print("upload:")
        _print_sftp_plan(review.upload_plan, show_batch=True)
        for note in review.notes:
            print(f"note: {note}")
    return 0 if review.allowed else 1


def cmd_text_evidence_bundle(args: argparse.Namespace) -> int:
    profile = ProfileStore().get(args.profile)
    plan = build_moba_text_release_evidence_bundle_plan(
        profile,
        args.remote,
        out_dir=args.out_dir,
        local_path=args.local,
        remote_sha256=args.remote_sha256,
        open_evidence=args.open_evidence,
        save_review_evidence=args.save_review_evidence,
        save_evidence=args.save_evidence,
        connected_evidence=args.connected_evidence,
        release_target=args.release_target,
        encoding=args.encoding,
        open_command=args.open_command,
        save_review_command=args.save_review_command,
        save_command=args.save_command,
        real_connected_session=args.real_connected_session,
        sftp_browser_open=args.sftp_browser_open,
        editor_tab_visible=args.editor_tab_visible,
    )
    result = write_moba_text_release_evidence_bundle(plan, profile=profile)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"text remote-edit evidence bundle: {'passed' if result.validation.passed else 'failed'}")
        print(f"evidence: {result.evidence_path}")
        for note in result.notes:
            print(f"note: {note}")
        for error in result.validation.errors:
            print(f"error: {error}")
    return 0 if result.validation.passed else 1


def cmd_text_evidence_verify(args: argparse.Namespace) -> int:
    result = validate_moba_text_release_evidence(args.evidence, assets_dir=args.assets_dir)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"evidence: {result.evidence_path}")
        print(f"assets: {result.assets_dir}")
        print(f"passed: {'yes' if result.passed else 'no'}")
        if result.summary:
            print(f"schema: {result.summary.get('schema', '')}")
            print(f"release target: {result.summary.get('release_target', '')}")
            print(f"profile: {result.summary.get('profile', '')}")
            print(f"remote: {result.summary.get('remote_path', '')}")
            print(f"syntax: {result.summary.get('syntax', '')}")
        for warning in result.warnings:
            print(f"warning: {warning}")
        for error in result.errors:
            print(f"error: {error}", file=sys.stderr)
    return 0 if result.passed else 1

"""File transfer and SSH browser commands for the CLI."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .file_transfer import (
    SftpBatchPlan,
    SftpQueuePlan,
    SftpQueueResult,
    build_sftp_get_plan,
    build_sftp_interactive_plan,
    build_sftp_list_plan,
    build_sftp_mkdir_plan,
    build_sftp_put_plan,
    build_sftp_queue_plan,
    build_sftp_remote_preview_plan,
    build_sftp_rename_plan,
    build_sftp_rm_plan,
    build_sftp_rmdir_plan,
    parse_transfer_item_spec,
    preview_local_path,
    run_sftp_batch,
    run_sftp_interactive,
    run_sftp_queue,
)
from .moba_ssh_browser import (
    build_moba_ssh_browser_open_plan,
    load_moba_ssh_browser_preferences,
    review_moba_ssh_browser_overwrite,
    update_moba_ssh_browser_columns,
    update_moba_ssh_browser_location,
)
from .storage import ProfileStore


def add_transfer_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    files = sub.add_parser("files", help="browse and transfer files through SSH/SFTP profiles")
    files_sub = files.add_subparsers(required=True)
    files_open = files_sub.add_parser("open", help="open an interactive SFTP browser")
    files_open.add_argument("profile")
    files_open.add_argument("--dry-run", action="store_true")
    files_open.set_defaults(func=cmd_files_open)
    files_ls = files_sub.add_parser("ls", help="list a remote directory")
    files_ls.add_argument("profile")
    files_ls.add_argument("remote", nargs="?", default=".")
    files_ls.add_argument("--dry-run", action="store_true")
    files_ls.set_defaults(func=cmd_files_ls)
    files_get = files_sub.add_parser("get", help="download a remote file or directory")
    files_get.add_argument("profile")
    files_get.add_argument("remote")
    files_get.add_argument("--local", type=Path)
    files_get.add_argument("--recursive", action="store_true")
    files_get.add_argument("--force", action="store_true", help="allow overwriting an existing local target")
    files_get.add_argument("--dry-run", action="store_true")
    files_get.set_defaults(func=cmd_files_get)
    files_put = files_sub.add_parser("put", help="upload a local file or directory")
    files_put.add_argument("profile")
    files_put.add_argument("local", type=Path)
    files_put.add_argument("--remote")
    files_put.add_argument("--recursive", action="store_true")
    files_put.add_argument("--force", action="store_true", help="acknowledge remote overwrite risk")
    files_put.add_argument("--dry-run", action="store_true")
    files_put.set_defaults(func=cmd_files_put)
    files_mkdir = files_sub.add_parser("mkdir", help="create a remote directory")
    files_mkdir.add_argument("profile")
    files_mkdir.add_argument("remote")
    files_mkdir.add_argument("--dry-run", action="store_true")
    files_mkdir.set_defaults(func=cmd_files_mkdir)
    files_rm = files_sub.add_parser("rm", help="remove a remote file")
    files_rm.add_argument("profile")
    files_rm.add_argument("remote")
    files_rm.add_argument("--force", action="store_true", help="confirm remote deletion")
    files_rm.add_argument("--dry-run", action="store_true")
    files_rm.set_defaults(func=cmd_files_rm)
    files_rmdir = files_sub.add_parser("rmdir", help="remove a remote directory")
    files_rmdir.add_argument("profile")
    files_rmdir.add_argument("remote")
    files_rmdir.add_argument("--force", action="store_true", help="confirm remote directory deletion")
    files_rmdir.add_argument("--dry-run", action="store_true")
    files_rmdir.set_defaults(func=cmd_files_rmdir)
    files_rename = files_sub.add_parser("rename", help="rename a remote path")
    files_rename.add_argument("profile")
    files_rename.add_argument("old")
    files_rename.add_argument("new")
    files_rename.add_argument("--force", action="store_true", help="confirm remote rename or replace risk")
    files_rename.add_argument("--dry-run", action="store_true")
    files_rename.set_defaults(func=cmd_files_rename)
    files_queue = files_sub.add_parser("queue", help="run or inspect a queued SFTP transfer batch")
    files_queue.add_argument("profile")
    files_queue.add_argument(
        "--op",
        action="append",
        required=True,
        help='queued operation such as "get /etc/hosts ./hosts", "put ./build.tar.gz /tmp/build.tar.gz", "mkdir /tmp/x", or "rename old new"',
    )
    files_queue.add_argument("--force", action="store_true", help="allow destructive queue items during execution")
    files_queue.add_argument("--dry-run", action="store_true")
    files_queue.add_argument("--json", action="store_true")
    files_queue.set_defaults(func=cmd_files_queue)
    files_preview_local = files_sub.add_parser("preview-local", help="preview local file or directory metadata")
    files_preview_local.add_argument("path", type=Path)
    files_preview_local.add_argument("--bytes", type=int, default=4096)
    files_preview_local.add_argument("--entries", type=int, default=50)
    files_preview_local.add_argument("--json", action="store_true")
    files_preview_local.set_defaults(func=cmd_files_preview_local)
    files_preview_remote = files_sub.add_parser("preview-remote", help="preview a remote path through SFTP ls")
    files_preview_remote.add_argument("profile")
    files_preview_remote.add_argument("remote", nargs="?", default=".")
    files_preview_remote.add_argument("--dry-run", action="store_true")
    files_preview_remote.add_argument("--json", action="store_true")
    files_preview_remote.set_defaults(func=cmd_files_preview_remote)

    ssh_browser = sub.add_parser("ssh-browser", help="manage MobaXterm-style SSH-browser state")
    ssh_browser_sub = ssh_browser.add_subparsers(required=True)
    ssh_browser_status = ssh_browser_sub.add_parser("status", help="show saved SSH-browser location and column state")
    ssh_browser_status.add_argument("--json", action="store_true")
    ssh_browser_status.set_defaults(func=cmd_ssh_browser_status)
    ssh_browser_location = ssh_browser_sub.add_parser("location", help="set SSH-browser startup location")
    ssh_browser_location.add_argument("location", choices=["side-by-side", "below-terminal", "hidden"])
    ssh_browser_location.add_argument("--json", action="store_true")
    ssh_browser_location.set_defaults(func=cmd_ssh_browser_location)
    ssh_browser_columns = ssh_browser_sub.add_parser("columns", help="persist SSH-browser column widths")
    ssh_browser_columns.add_argument("--name", type=int)
    ssh_browser_columns.add_argument("--size", type=int)
    ssh_browser_columns.add_argument("--modified", type=int)
    ssh_browser_columns.add_argument("--json", action="store_true")
    ssh_browser_columns.set_defaults(func=cmd_ssh_browser_columns)
    ssh_browser_open = ssh_browser_sub.add_parser("open-plan", help="show same-parameter SFTP browser open plan")
    ssh_browser_open.add_argument("profile")
    ssh_browser_open.add_argument("--json", action="store_true")
    ssh_browser_open.set_defaults(func=cmd_ssh_browser_open_plan)
    ssh_browser_overwrite = ssh_browser_sub.add_parser("overwrite", help="review upload/download overwrite confirmation")
    ssh_browser_overwrite.add_argument("action", choices=["upload", "download"])
    ssh_browser_overwrite.add_argument("source")
    ssh_browser_overwrite.add_argument("destination")
    ssh_browser_overwrite.add_argument("--destination-exists", action="store_true")
    ssh_browser_overwrite.add_argument("--force", action="store_true")
    ssh_browser_overwrite.add_argument("--json", action="store_true")
    ssh_browser_overwrite.set_defaults(func=cmd_ssh_browser_overwrite)


def cmd_files_open(args: argparse.Namespace) -> int:
    profile = ProfileStore().get(args.profile)
    plan = build_sftp_interactive_plan(profile)
    run_sftp_interactive(plan, dry_run=args.dry_run)
    print(plan.printable())
    for note in plan.notes:
        print(f"note: {note}")
    return 0


def cmd_files_ls(args: argparse.Namespace) -> int:
    profile = ProfileStore().get(args.profile)
    plan = build_sftp_list_plan(profile, args.remote)
    run_sftp_batch(plan, dry_run=args.dry_run)
    _print_sftp_plan(plan, show_batch=args.dry_run)
    return 0


def cmd_files_get(args: argparse.Namespace) -> int:
    profile = ProfileStore().get(args.profile)
    plan = build_sftp_get_plan(
        profile,
        args.remote,
        local_path=args.local,
        recursive=args.recursive,
        allow_overwrite=args.force,
    )
    run_sftp_batch(plan, dry_run=args.dry_run)
    _print_sftp_plan(plan, show_batch=args.dry_run)
    return 0


def cmd_files_put(args: argparse.Namespace) -> int:
    profile = ProfileStore().get(args.profile)
    plan = build_sftp_put_plan(
        profile,
        args.local,
        remote_path=args.remote,
        recursive=args.recursive,
        allow_overwrite=args.force,
    )
    run_sftp_batch(plan, dry_run=args.dry_run)
    _print_sftp_plan(plan, show_batch=args.dry_run)
    return 0


def cmd_files_mkdir(args: argparse.Namespace) -> int:
    profile = ProfileStore().get(args.profile)
    plan = build_sftp_mkdir_plan(profile, args.remote)
    run_sftp_batch(plan, dry_run=args.dry_run)
    _print_sftp_plan(plan, show_batch=args.dry_run)
    return 0


def cmd_files_rm(args: argparse.Namespace) -> int:
    profile = ProfileStore().get(args.profile)
    plan = build_sftp_rm_plan(profile, args.remote, allow_delete=args.force)
    run_sftp_batch(plan, dry_run=args.dry_run)
    _print_sftp_plan(plan, show_batch=args.dry_run)
    return 0


def cmd_files_rmdir(args: argparse.Namespace) -> int:
    profile = ProfileStore().get(args.profile)
    plan = build_sftp_rmdir_plan(profile, args.remote, allow_delete=args.force)
    run_sftp_batch(plan, dry_run=args.dry_run)
    _print_sftp_plan(plan, show_batch=args.dry_run)
    return 0


def cmd_files_rename(args: argparse.Namespace) -> int:
    profile = ProfileStore().get(args.profile)
    plan = build_sftp_rename_plan(profile, args.old, args.new, allow_rename=args.force)
    run_sftp_batch(plan, dry_run=args.dry_run)
    _print_sftp_plan(plan, show_batch=args.dry_run)
    return 0


def cmd_files_queue(args: argparse.Namespace) -> int:
    profile = ProfileStore().get(args.profile)
    items = [parse_transfer_item_spec(spec) for spec in args.op]
    plan = build_sftp_queue_plan(profile, items, force=args.force)
    result = run_sftp_queue(plan, dry_run=args.dry_run)
    if args.json:
        payload = result.to_dict()
        payload["batch_commands"] = plan.batch_commands
        payload["notes"] = plan.notes
        print(json.dumps(payload, indent=2))
    else:
        _print_sftp_queue_result(plan, result)
    return 0 if result.ok else 1


def cmd_files_preview_local(args: argparse.Namespace) -> int:
    preview = preview_local_path(args.path, max_bytes=args.bytes, max_entries=args.entries)
    if args.json:
        print(json.dumps(preview.to_dict(), indent=2))
        return 0 if preview.error == "" else 1
    _print_local_preview(preview.to_dict())
    return 0 if preview.error == "" else 1


def cmd_files_preview_remote(args: argparse.Namespace) -> int:
    profile = ProfileStore().get(args.profile)
    plan = build_sftp_remote_preview_plan(profile, args.remote)
    run_sftp_batch(plan, dry_run=args.dry_run)
    if args.json:
        print(
            json.dumps(
                {
                    "profile": plan.profile_name,
                    "command": plan.command,
                    "batch_commands": plan.batch_commands,
                    "notes": plan.notes,
                    "dry_run": args.dry_run,
                },
                indent=2,
            )
        )
    else:
        _print_sftp_plan(plan, show_batch=True)
    return 0


def cmd_ssh_browser_status(args: argparse.Namespace) -> int:
    preferences = load_moba_ssh_browser_preferences()
    if args.json:
        print(json.dumps(preferences.to_dict(), indent=2, sort_keys=True))
        return 0
    print(f"location: {preferences.location}")
    print(f"overwrite confirmation: {'yes' if preferences.overwrite_confirmation else 'no'}")
    print("columns:")
    for key, width in preferences.column_widths.items():
        print(f"  {key:<8} {width}")
    print(f"updated: {preferences.updated_at}")
    return 0


def cmd_ssh_browser_location(args: argparse.Namespace) -> int:
    preferences = update_moba_ssh_browser_location(args.location)
    if args.json:
        print(json.dumps(preferences.to_dict(), indent=2, sort_keys=True))
        return 0
    print(f"location: {preferences.location}")
    return 0


def cmd_ssh_browser_columns(args: argparse.Namespace) -> int:
    widths = {
        key: value
        for key, value in {
            "name": args.name,
            "size": args.size,
            "modified": args.modified,
        }.items()
        if value is not None
    }
    if not widths:
        raise ValueError("at least one column width is required")
    preferences = update_moba_ssh_browser_columns(widths)
    if args.json:
        print(json.dumps(preferences.to_dict(), indent=2, sort_keys=True))
        return 0
    for key, width in preferences.column_widths.items():
        print(f"{key}: {width}")
    return 0


def cmd_ssh_browser_open_plan(args: argparse.Namespace) -> int:
    profile = ProfileStore().get(args.profile)
    plan = build_moba_ssh_browser_open_plan(profile)
    if args.json:
        print(json.dumps(plan.to_dict(), indent=2, sort_keys=True))
        return 0
    print(" ".join(plan.command))
    print(f"location: {plan.location}")
    print(f"terminal visible: {'yes' if plan.terminal_visible else 'no'}")
    print(f"browser visible: {'yes' if plan.browser_visible else 'no'}")
    for note in plan.notes:
        print(f"note: {note}")
    return 0


def cmd_ssh_browser_overwrite(args: argparse.Namespace) -> int:
    review = review_moba_ssh_browser_overwrite(
        args.action,
        args.source,
        args.destination,
        destination_exists=args.destination_exists,
        force=args.force,
    )
    if args.json:
        print(json.dumps(review.to_dict(), indent=2, sort_keys=True))
        return 0 if review.allowed else 1
    print(f"allowed: {'yes' if review.allowed else 'no'}")
    print(f"confirmation required: {'yes' if review.confirmation_required else 'no'}")
    if review.prompt:
        print(f"prompt: {review.prompt}")
    for note in review.notes:
            print(f"note: {note}")
    return 0 if review.allowed else 1


def _print_sftp_plan(plan: SftpBatchPlan, *, show_batch: bool) -> None:
    print(plan.printable())
    if show_batch:
        print("batch:")
        for command in plan.batch_commands:
            print(f"  {command}")
    for note in plan.notes:
        print(f"note: {note}")


def _print_sftp_queue_result(plan: SftpQueuePlan, result: SftpQueueResult) -> None:
    status = "DRY-RUN" if result.dry_run else ("OK" if result.ok else f"FAIL {result.returncode}")
    print(f"{plan.profile_name}: {status}: {plan.printable()}")
    print("queue:")
    for index, command in enumerate(plan.batch_commands, start=1):
        print(f"  {index}. {command}")
    if result.progress:
        print("progress:")
        for event in result.progress:
            returncode = "" if event.returncode is None else f" (exit {event.returncode})"
            print(f"  {event.index}/{event.total} {event.item.action}: {event.state}{returncode}")
    for note in plan.notes:
        print(f"note: {note}")
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr)


def _print_local_preview(preview: dict[str, object]) -> None:
    print(f"{preview['path']}: {preview['kind']}")
    if not preview["exists"]:
        print("missing")
        return
    if preview.get("size") is not None:
        print(f"size: {preview['size']}")
    children = preview.get("children")
    if isinstance(children, list) and children:
        print("children:")
        for child in children:
            print(f"  {child}")
    if preview.get("binary"):
        print("binary: true")
    if preview.get("truncated"):
        print("truncated: true")
    text = preview.get("text") or ""
    if text:
        print("preview:")
        print(text)
    if preview.get("error"):
        print(f"error: {preview['error']}", file=sys.stderr)

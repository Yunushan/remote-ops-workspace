"""Backup, profile import and export, and workspace sync commands."""

from __future__ import annotations

import argparse
import json
import sys
from getpass import getpass
from pathlib import Path

from .cli_input import secret_from_env
from .paths import data_dir
from .profile_importers import SUPPORTED_IMPORT_FORMATS, import_profiles_into_store
from .storage import ProfileStore
from .sync import BackupService, DirectorySyncProvider
from .team_sync import TeamSyncBackend, TeamSyncClient, TeamSyncSnapshot


def add_workspace_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    export = sub.add_parser("export", help="export profiles bundle")
    export.add_argument("--out", required=True, type=Path)
    export.set_defaults(func=cmd_export)

    workspace = sub.add_parser("workspace", help="encrypted offline backup and restore of full workspace state")
    workspace_sub = workspace.add_subparsers(required=True)
    workspace_backup = workspace_sub.add_parser("backup", help="snapshot ROW_HOME after closing all ROW processes")
    workspace_backup.add_argument("--out", required=True, type=Path, help="encrypted backup path outside ROW_HOME")
    workspace_backup.add_argument("--offline", required=True, action="store_true", help="confirm all other ROW processes and managed helpers are stopped")
    workspace_backup.add_argument("--passphrase-env", metavar="ENV", help="read backup passphrase from this variable; otherwise prompt with confirmation")
    workspace_backup.set_defaults(func=cmd_workspace_backup)
    workspace_restore = workspace_sub.add_parser("restore", help="restore into a new sibling ROW_HOME, retaining the original")
    workspace_restore.add_argument("--backup", required=True, type=Path)
    workspace_restore.add_argument("--destination", required=True, type=Path, help="new sibling directory next to the current ROW_HOME")
    workspace_restore.add_argument("--offline", required=True, action="store_true", help="confirm all other ROW processes and managed helpers are stopped")
    workspace_restore.add_argument("--passphrase-env", metavar="ENV", help="read backup passphrase from this variable; otherwise prompt")
    workspace_restore.set_defaults(func=cmd_workspace_restore)

    imp = sub.add_parser("import", help="import profiles bundle or external session export")
    imp.add_argument("--in", dest="input", required=True, type=Path)
    imp.add_argument(
        "--format",
        choices=sorted(SUPPORTED_IMPORT_FORMATS),
        default="auto",
        help="input format; auto detects ROW, Remmina, mRemoteNG, Termius-style JSON and MobaXterm sessions",
    )
    imp.add_argument("--replace", action="store_true")
    imp.set_defaults(func=cmd_import)

    sync = sub.add_parser("sync", help="sync through a mounted/shared directory provider")
    sync_sub = sync.add_subparsers(required=True)
    sync_push = sync_sub.add_parser("push", help="push a bundle to a shared directory")
    sync_push.add_argument("--to", required=True, type=Path)
    sync_push.set_defaults(func=cmd_sync_push)
    sync_pull = sync_sub.add_parser("pull", help="pull a bundle from a shared directory or bundle file")
    sync_pull.add_argument("--from", dest="source", required=True, type=Path)
    sync_pull.add_argument("--replace", action="store_true")
    sync_pull.set_defaults(func=cmd_sync_pull)

    team_sync = sub.add_parser("team-sync", help="sync shared profile metadata through a versioned team directory")
    team_sync_sub = team_sync.add_subparsers(required=True)
    team_status = team_sync_sub.add_parser("status", help="show shared team version and profile count")
    team_status.add_argument("--root", required=True, type=Path)
    team_status.add_argument("--team", required=True)
    team_status.add_argument("--json", action="store_true")
    team_status.set_defaults(func=cmd_team_sync_status)
    team_push = team_sync_sub.add_parser("push", help="publish local metadata with optimistic version control")
    team_push.add_argument("--root", required=True, type=Path)
    team_push.add_argument("--team", required=True)
    team_push.add_argument("--expected-version", required=True, type=int)
    team_push.add_argument("--json", action="store_true")
    team_push.set_defaults(func=cmd_team_sync_push)
    team_pull = team_sync_sub.add_parser("pull", help="merge shared metadata while retaining local credential references")
    team_pull.add_argument("--root", required=True, type=Path)
    team_pull.add_argument("--team", required=True)
    team_pull.add_argument("--replace", action="store_true", help="replace local profiles instead of merging")
    team_pull.add_argument("--json", action="store_true")
    team_pull.set_defaults(func=cmd_team_sync_pull)


def cmd_export(args: argparse.Namespace) -> int:
    BackupService().export_bundle(args.out)
    print(f"exported: {args.out}")
    return 0


def _workspace_backup_passphrase(args: argparse.Namespace, *, confirm: bool) -> str:
    if args.passphrase_env:
        return secret_from_env(args.passphrase_env, "backup passphrase")
    passphrase = getpass("Backup passphrase: ")
    if confirm and passphrase != getpass("Confirm backup passphrase: "):
        raise ValueError("backup passphrases do not match")
    return passphrase


def cmd_workspace_backup(args: argparse.Namespace) -> int:
    from .workspace_backup import create_workspace_backup

    result = create_workspace_backup(
        data_dir().resolve(), args.out, _workspace_backup_passphrase(args, confirm=True),
        offline_confirmed=args.offline,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def cmd_workspace_restore(args: argparse.Namespace) -> int:
    from .workspace_backup import restore_workspace_backup

    result = restore_workspace_backup(
        args.backup, args.destination, _workspace_backup_passphrase(args, confirm=False),
        current_home=data_dir().resolve(), offline_confirmed=args.offline,
    )
    print(json.dumps(result, indent=2, sort_keys=True))
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    result = import_profiles_into_store(args.input, ProfileStore(), source_format=args.format, replace=args.replace)
    print(f"imported profiles: {len(result.profiles)}")
    print(f"format: {result.source_format}")
    for warning in result.warnings:
        print(f"warning: {warning}", file=sys.stderr)
    return 0


def cmd_sync_push(args: argparse.Namespace) -> int:
    target = DirectorySyncProvider().push(args.to)
    print(f"synced: {target}")
    return 0


def cmd_sync_pull(args: argparse.Namespace) -> int:
    count = DirectorySyncProvider().pull(args.source, replace=args.replace)
    print(f"synced profiles: {count}")
    return 0


def _team_sync_client(root: Path) -> TeamSyncClient:
    return TeamSyncClient(ProfileStore(), TeamSyncBackend(root))


def _print_team_sync_snapshot(snapshot: TeamSyncSnapshot, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(snapshot.to_dict(), indent=2, sort_keys=True))
        return
    print(f"team: {snapshot.team}")
    print(f"version: {snapshot.version}")
    print(f"profiles: {len(snapshot.profiles)}")
    if snapshot.updated_at:
        print(f"updated_at: {snapshot.updated_at}")


def cmd_team_sync_status(args: argparse.Namespace) -> int:
    _print_team_sync_snapshot(TeamSyncBackend(args.root).read(args.team), as_json=args.json)
    return 0


def cmd_team_sync_push(args: argparse.Namespace) -> int:
    snapshot = _team_sync_client(args.root).push(args.team, expected_version=args.expected_version)
    _print_team_sync_snapshot(snapshot, as_json=args.json)
    return 0


def cmd_team_sync_pull(args: argparse.Namespace) -> int:
    snapshot = _team_sync_client(args.root).pull(args.team, replace=args.replace)
    _print_team_sync_snapshot(snapshot, as_json=args.json)
    return 0

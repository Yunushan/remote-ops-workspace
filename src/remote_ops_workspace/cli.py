from __future__ import annotations

import argparse
import json
import os
import shlex
import sys
from getpass import getpass
from pathlib import Path

from . import __version__
from .audit import append_event
from .broadcast import BroadcastResult, build_broadcast_plans, run_broadcast
from .doctor import run_doctor
from .features import coverage_report, feature_summary, load_feature_manifest
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
from .first_run import first_run_json, first_run_payload, format_first_run
from .file_safety import write_text_atomic
from .keys import build_keygen_plan, run_keygen
from .launcher import LauncherError, launch
from .layouts import (
    Layout,
    LayoutRunResult,
    LayoutStore,
    build_layout_terminal_plans,
    parse_layout_pane,
    run_layout_terminal_plans,
)
from .models import Profile, Tunnel
from .network_tools import build_network_tool_plan, check_tcp_port, run_network_tool
from .paths import ensure_data_dir
from .plugin_dev import (
    DEFAULT_PLUGIN_CHECK_HOST,
    DEFAULT_PLUGIN_CHECK_USERNAME,
    report_to_text,
    result_to_json,
    scaffold_plugin,
    validate_installed_plugins,
)
from .platform_targets import load_platform_targets
from .plugins import load_plugin_registry
from .profile_importers import SUPPORTED_IMPORT_FORMATS, import_profiles_into_store
from .snippets import Snippet, SnippetStore, run_snippet
from .storage import ProfileStore
from .sync import BackupService, DirectorySyncProvider
from .vault import LocalVault, VaultBackendUnavailable, VaultError, prompt_passphrase
from .web_server import serve_web
from .x11 import build_x_server_plan, run_x_server


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (KeyError, ValueError, LauncherError, VaultError, VaultBackendUnavailable) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="row", description="Remote Ops Workspace CLI")
    parser.add_argument("--version", action="version", version=f"remote-ops-workspace {__version__}")
    sub = parser.add_subparsers(required=True)

    init = sub.add_parser("init", help="initialize local workspace data")
    init.add_argument("--no-examples", action="store_true", help="do not create example profiles")
    init.add_argument("--quiet", action="store_true", help="only print the initialized data directory")
    init.add_argument("--json", action="store_true", help="print first-run guidance as JSON")
    init.set_defaults(func=cmd_init)

    welcome = sub.add_parser("welcome", help="show first-run guidance and useful next commands")
    welcome.add_argument("--json", action="store_true")
    welcome.set_defaults(func=cmd_welcome)

    profile = sub.add_parser("profile", help="manage connection profiles")
    psub = profile.add_subparsers(required=True)
    padd = psub.add_parser("add", help="add a profile")
    padd.add_argument("--name", required=True)
    padd.add_argument("--protocol", required=True)
    padd.add_argument("--host")
    padd.add_argument("--port", type=int)
    padd.add_argument("--username")
    padd.add_argument("--group", default="default")
    padd.add_argument("--tag", action="append", default=[])
    padd.add_argument("--description", default="")
    padd.add_argument("--path")
    padd.add_argument("--url")
    padd.add_argument("--command")
    padd.add_argument("--identity-file")
    padd.add_argument("--credential-ref")
    padd.add_argument(
        "--tunnel",
        action="append",
        default=[],
        help="SSH tunnel: local:15432:127.0.0.1:5432, remote:9000:127.0.0.1:9000, or dynamic:1080",
    )
    padd.add_argument("--option", action="append", default=[], help="protocol option as key=value")
    padd.add_argument("--replace", action="store_true")
    padd.set_defaults(func=cmd_profile_add)

    plist = psub.add_parser("list", help="list profiles")
    plist.add_argument("--json", action="store_true")
    plist.set_defaults(func=cmd_profile_list)

    pshow = psub.add_parser("show", help="show a profile")
    pshow.add_argument("name")
    pshow.set_defaults(func=cmd_profile_show)

    premove = psub.add_parser("remove", help="remove a profile")
    premove.add_argument("name")
    premove.set_defaults(func=cmd_profile_remove)

    pdefaults = psub.add_parser("defaults", help="set group-level profile defaults")
    pdefaults.add_argument("group")
    pdefaults.add_argument("--username")
    pdefaults.add_argument("--identity-file")
    pdefaults.add_argument("--credential-ref")
    pdefaults.add_argument("--option", action="append", default=[], help="default option as key=value")
    pdefaults.add_argument("--replace", action="store_true")
    pdefaults.set_defaults(func=cmd_profile_defaults)

    connect = sub.add_parser("connect", help="launch a profile")
    connect.add_argument("name")
    connect.add_argument("--dry-run", action="store_true")
    connect.set_defaults(func=cmd_connect)

    doctor = sub.add_parser("doctor", help="inspect platform and external client availability")
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(func=cmd_doctor)

    platforms = sub.add_parser("platforms", help="show release architecture and legacy OS targets")
    platforms.add_argument("--json", action="store_true")
    platforms.set_defaults(func=cmd_platforms)

    features = sub.add_parser("features", help="show feature coverage manifest")
    features.add_argument("--json", action="store_true")
    features.add_argument("--coverage", action="store_true", help="show weighted product coverage percentages")
    features.set_defaults(func=cmd_features)

    plugins = sub.add_parser("plugins", help="inspect installed protocol launch plugins")
    plugins_sub = plugins.add_subparsers(required=True)
    plugins_list = plugins_sub.add_parser("list", help="list installed plugin entry points")
    plugins_list.add_argument("--json", action="store_true")
    plugins_list.set_defaults(func=cmd_plugins_list)
    plugins_validate = plugins_sub.add_parser("validate", help="validate installed plugin contracts")
    plugins_validate.add_argument("--json", action="store_true")
    plugins_validate.add_argument("--host", default=DEFAULT_PLUGIN_CHECK_HOST)
    plugins_validate.add_argument("--username", default=DEFAULT_PLUGIN_CHECK_USERNAME)
    plugins_validate.add_argument("--port", type=int)
    plugins_validate.add_argument("--option", action="append", default=[], help="sample profile option as key=value")
    plugins_validate.set_defaults(func=cmd_plugins_validate)
    plugins_scaffold = plugins_sub.add_parser("scaffold", help="create a minimal protocol plugin project")
    plugins_scaffold.add_argument("--out", required=True, type=Path)
    plugins_scaffold.add_argument("--name", required=True, help="Python package project name, e.g. row-demo-plugin")
    plugins_scaffold.add_argument("--module", help="Python module name, e.g. row_demo_plugin")
    plugins_scaffold.add_argument("--protocol", required=True, help="new plugin protocol name")
    plugins_scaffold.add_argument("--client", required=True, help="external executable used by the sample plugin")
    plugins_scaffold.add_argument("--force", action="store_true", help="overwrite existing scaffold files")
    plugins_scaffold.add_argument("--json", action="store_true")
    plugins_scaffold.set_defaults(func=cmd_plugins_scaffold)

    snippet = sub.add_parser("snippet", help="manage reusable snippets and macros")
    snip_sub = snippet.add_subparsers(required=True)
    snip_add = snip_sub.add_parser("add", help="add a snippet")
    snip_add.add_argument("--name", required=True)
    snip_add.add_argument("--command", required=True)
    snip_add.add_argument("--description", default="")
    snip_add.add_argument("--tag", action="append", default=[])
    snip_add.add_argument("--replace", action="store_true")
    snip_add.set_defaults(func=cmd_snippet_add)
    snip_list = snip_sub.add_parser("list", help="list snippets")
    snip_list.add_argument("--json", action="store_true")
    snip_list.set_defaults(func=cmd_snippet_list)
    snip_show = snip_sub.add_parser("show", help="show a snippet")
    snip_show.add_argument("name")
    snip_show.set_defaults(func=cmd_snippet_show)
    snip_remove = snip_sub.add_parser("remove", help="remove a snippet")
    snip_remove.add_argument("name")
    snip_remove.set_defaults(func=cmd_snippet_remove)
    snip_run = snip_sub.add_parser("run", help="run a snippet")
    snip_run.add_argument("name")
    snip_run.add_argument("--dry-run", action="store_true")
    snip_run.set_defaults(func=cmd_snippet_run)

    layout = sub.add_parser("layout", help="manage saved terminal layouts")
    layout_sub = layout.add_subparsers(required=True)
    layout_save = layout_sub.add_parser("save", help="save a layout")
    layout_save.add_argument("name")
    layout_save.add_argument("--orientation", choices=["grid", "horizontal", "vertical"], default="grid")
    layout_save.add_argument("--pane", action="append", required=True, help="profile:name or command:argv")
    layout_save.add_argument("--description", default="")
    layout_save.add_argument("--replace", action="store_true")
    layout_save.set_defaults(func=cmd_layout_save)
    layout_list = layout_sub.add_parser("list", help="list layouts")
    layout_list.add_argument("--json", action="store_true")
    layout_list.set_defaults(func=cmd_layout_list)
    layout_show = layout_sub.add_parser("show", help="show a layout")
    layout_show.add_argument("name")
    layout_show.set_defaults(func=cmd_layout_show)
    layout_remove = layout_sub.add_parser("remove", help="remove a layout")
    layout_remove.add_argument("name")
    layout_remove.set_defaults(func=cmd_layout_remove)
    layout_run = layout_sub.add_parser("run", help="launch or inspect a saved layout")
    layout_run.add_argument("name")
    layout_run.add_argument("--dry-run", action="store_true")
    layout_run.add_argument("--json", action="store_true")
    layout_run.set_defaults(func=cmd_layout_run)

    broadcast = sub.add_parser("broadcast", help="fan out a command to multiple SSH profiles")
    broadcast.add_argument("--command", required=True)
    broadcast.add_argument("--profile", action="append", default=[])
    broadcast.add_argument("--group")
    broadcast.add_argument("--tag", action="append", default=[])
    broadcast.add_argument("--timeout", type=float, help="per-profile timeout in seconds")
    broadcast.add_argument("--json", action="store_true")
    broadcast.add_argument("--dry-run", action="store_true")
    broadcast.set_defaults(func=cmd_broadcast)

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

    keygen = sub.add_parser("keygen", help="generate SSH keys with ssh-keygen")
    keygen.add_argument("--out", required=True, type=Path)
    keygen.add_argument("--type", default="ed25519", choices=["ed25519", "ecdsa", "rsa", "ed25519-sk", "ecdsa-sk"])
    keygen.add_argument("--bits", type=int)
    keygen.add_argument("--comment", default="")
    keygen.add_argument(
        "--passphrase-env",
        help=(
            "environment variable containing the key passphrase; software keys are generated "
            "in-process so the passphrase is not placed on ssh-keygen argv"
        ),
    )
    keygen.add_argument("--resident", action="store_true", help="request a resident FIDO/security-key credential")
    keygen.add_argument("--dry-run", action="store_true")
    keygen.set_defaults(func=cmd_keygen)

    nettool = sub.add_parser("nettool", help="run network toolbox commands")
    net_sub = nettool.add_subparsers(required=True)
    net_ping = net_sub.add_parser("ping", help="ping a host")
    net_ping.add_argument("target")
    net_ping.add_argument("--count", type=int, default=4)
    net_ping.add_argument("--dry-run", action="store_true")
    net_ping.set_defaults(func=cmd_nettool_plan, tool="ping")
    net_trace = net_sub.add_parser("trace", help="trace route to a host")
    net_trace.add_argument("target")
    net_trace.add_argument("--dry-run", action="store_true")
    net_trace.set_defaults(func=cmd_nettool_plan, tool="trace")
    net_dns = net_sub.add_parser("dns", help="look up DNS records")
    net_dns.add_argument("target")
    net_dns.add_argument("--dry-run", action="store_true")
    net_dns.set_defaults(func=cmd_nettool_plan, tool="dns")
    net_whois = net_sub.add_parser("whois", help="run whois")
    net_whois.add_argument("target")
    net_whois.add_argument("--dry-run", action="store_true")
    net_whois.set_defaults(func=cmd_nettool_plan, tool="whois")
    net_port = net_sub.add_parser("port", help="check a TCP port using Python sockets")
    net_port.add_argument("host")
    net_port.add_argument("--port", required=True, type=int)
    net_port.add_argument("--timeout", default=3.0, type=float)
    net_port.set_defaults(func=cmd_nettool_port)

    x11 = sub.add_parser("x11", help="manage local X server helper")
    x11_sub = x11.add_subparsers(required=True)
    x11_start = x11_sub.add_parser("start", help="start or inspect a local X server helper")
    x11_start.add_argument("--display", default=":0")
    x11_start.add_argument("--dry-run", action="store_true")
    x11_start.set_defaults(func=cmd_x11_start)

    vault = sub.add_parser("vault", help="local encrypted vault")
    vsub = vault.add_subparsers(required=True)
    vinit = vsub.add_parser("init", help="initialize vault")
    vinit.set_defaults(func=cmd_vault_init)
    vset = vsub.add_parser("set", help="set a secret")
    vset.add_argument("name")
    vset_source = vset.add_mutually_exclusive_group()
    vset_source.add_argument(
        "--secret-env",
        metavar="ENV",
        help="read the secret value from an environment variable instead of prompting",
    )
    vset_source.add_argument(
        "--stdin",
        action="store_true",
        help="read the secret value from stdin; one trailing newline is removed",
    )
    vset.set_defaults(func=cmd_vault_set)
    vget = vsub.add_parser("get", help="retrieve a secret")
    vget.add_argument("name")
    vget_output = vget.add_mutually_exclusive_group()
    vget_output.add_argument("--show", action="store_true", help="print the secret to stdout")
    vget_output.add_argument(
        "--out",
        type=Path,
        help="write the secret to a file with best-effort owner-only permissions",
    )
    vget.set_defaults(func=cmd_vault_get)
    vdelete = vsub.add_parser("delete", help="delete a secret")
    vdelete.add_argument("name")
    vdelete.add_argument("--force", action="store_true", help="confirm deletion without prompting")
    vdelete.set_defaults(func=cmd_vault_delete)
    vlist = vsub.add_parser("list", help="list secret names")
    vlist.set_defaults(func=cmd_vault_list)
    vstatus = vsub.add_parser("status", help="show vault status without revealing secrets")
    vstatus.add_argument("--json", action="store_true")
    vstatus.set_defaults(func=cmd_vault_status)

    export = sub.add_parser("export", help="export profiles bundle")
    export.add_argument("--out", required=True, type=Path)
    export.set_defaults(func=cmd_export)

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

    gui = sub.add_parser("gui", help="start PyQt6 desktop UI")
    gui.set_defaults(func=cmd_gui)

    web = sub.add_parser("serve-web", help="serve static Web/PWA app")
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", default=8765, type=int)
    web.add_argument(
        "--allow-public-bind",
        action="store_true",
        help="allow binding Web/PWA to a non-loopback interface",
    )
    web.set_defaults(func=cmd_serve_web)

    return parser


def cmd_init(args: argparse.Namespace) -> int:
    path = ensure_data_dir()
    store = ProfileStore()
    store.init(with_examples=not args.no_examples)
    payload = _first_run_payload(path, store)
    if args.json:
        print(first_run_json(payload))
        return 0
    print(f"initialized: {path}")
    if not args.quiet:
        print()
        print(format_first_run(payload))
    return 0


def cmd_welcome(args: argparse.Namespace) -> int:
    path = ensure_data_dir()
    store = ProfileStore()
    payload = _first_run_payload(path, store)
    if args.json:
        print(first_run_json(payload))
        return 0
    print(format_first_run(payload))
    return 0


def cmd_profile_add(args: argparse.Namespace) -> int:
    options = _parse_options(args.option)
    profile = Profile(
        name=args.name,
        protocol=args.protocol,
        host=args.host,
        port=args.port,
        username=args.username,
        group=args.group,
        tags=args.tag,
        description=args.description,
        path=args.path,
        url=args.url,
        command=args.command,
        identity_file=args.identity_file,
        credential_ref=args.credential_ref,
        tunnels=_parse_tunnels(args.tunnel),
        options=options,
    )
    ProfileStore().add(profile, replace=args.replace)
    print(f"saved profile: {profile.name}")
    return 0


def cmd_profile_list(args: argparse.Namespace) -> int:
    profiles = ProfileStore().load()
    if args.json:
        print(json.dumps([p.to_dict() for p in profiles], indent=2))
        return 0
    if not profiles:
        print("no profiles; run `row init` or `row profile add ...`")
        return 0
    for p in profiles:
        print(f"{p.group}/{p.name:<24} {p.protocol:<10} {p.display_target}")
    return 0


def cmd_profile_show(args: argparse.Namespace) -> int:
    profile = ProfileStore().get(args.name)
    print(json.dumps(profile.to_dict(), indent=2, sort_keys=True))
    return 0


def cmd_profile_remove(args: argparse.Namespace) -> int:
    ProfileStore().remove(args.name)
    print(f"removed profile: {args.name}")
    return 0


def cmd_profile_defaults(args: argparse.Namespace) -> int:
    defaults: dict[str, object] = {
        "username": args.username,
        "identity_file": args.identity_file,
        "credential_ref": args.credential_ref,
        "options": _parse_options(args.option),
    }
    ProfileStore().set_group_defaults(args.group, defaults, replace=args.replace)
    print(f"saved defaults for group: {args.group}")
    return 0


def cmd_connect(args: argparse.Namespace) -> int:
    profile = ProfileStore().get(args.name)
    plan = launch(profile, dry_run=args.dry_run)
    append_event("connect.dry_run" if args.dry_run else "connect.launch", {"profile": profile.to_dict(), "command": plan.command})
    print(plan.printable())
    for note in plan.notes:
        print(f"note: {note}")
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    result = run_doctor()
    if args.json:
        print(result.to_json())
        return 0
    print(f"Platform : {result.platform}")
    print(f"Python   : {result.python}")
    print(f"Data dir : {result.data_dir}")
    print("\nExternal clients:")
    for protocol, candidates in result.executables.items():
        available = [name for name, ok in candidates.items() if ok]
        status = ", ".join(available) if available else "missing"
        print(f"  {protocol:<8} {status}")
    return 0


def cmd_platforms(args: argparse.Namespace) -> int:
    targets = load_platform_targets()
    if args.json:
        print(json.dumps(targets, indent=2, sort_keys=True))
        return 0

    architectures = targets.get("release_architectures", [])
    legacy_targets = targets.get("windows_legacy_targets", [])
    print("Release architecture targets:")
    platform_width = max(len(item["platform"]) for item in architectures)
    arch_width = max(len(item["cpu_arch"]) for item in architectures)
    for item in architectures:
        print(
            f"  {item['platform']:<{platform_width}} {item['cpu_arch']:<{arch_width}} "
            f"{item['bits']:>2}-bit {item['release_tier']}"
        )

    print("\nLegacy Windows targets:")
    version_width = max(len(item["version"]) for item in legacy_targets)
    for item in legacy_targets:
        print(
            f"  {item['version']:<{version_width}} host {item['host_tier']}, "
            f"remote target {item['remote_target_tier']}"
        )
    return 0


def cmd_features(args: argparse.Namespace) -> int:
    if args.json:
        payload = coverage_report() if args.coverage else load_feature_manifest()
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    if args.coverage:
        report = coverage_report()
        mapping = report["feature_family_mapping"]
        readiness = report["product_ready_coverage"]
        mapping_overall = mapping["overall"]
        readiness_overall = readiness["overall"]
        print(f"Feature-family mapping target : {mapping['target_percent']:.0f}%")
        print(f"Feature-family mapping current: {mapping_overall['current_percent']:.1f}% ({mapping_overall['feature_count']} families)")
        print(f"Product-ready target          : {readiness['target_percent']:.0f}%")
        print(
            f"Product-ready current         : {readiness_overall['current_percent']:.1f}% "
            f"({readiness_overall['gap_percent']:.1f}% gap)"
        )
        evidence = report["evidence_summary"]
        print(
            f"Evidence records              : {evidence['features_with_evidence']}/"
            f"{evidence['total_features']} feature families"
        )
        print("\nProduct coverage:")
        readiness_rows = {row["product"]: row for row in readiness["products"]}
        product_width = max(len(row["product"]) for row in mapping["products"])
        for row in mapping["products"]:
            ready_row = readiness_rows[row["product"]]
            print(
                f"  {row['product']:<{product_width}} mapping {row['current_percent']:>5.1f}%, "
                f"ready {ready_row['current_percent']:>5.1f}% "
                f"({row['feature_count']} families)"
            )
        return 0
    for row in feature_summary():
        print(f"{row['id']:<32} {row['status']:<18} {row['coverage']}")
    return 0


def cmd_plugins_list(args: argparse.Namespace) -> int:
    registry = load_plugin_registry()
    if args.json:
        print(json.dumps(registry.to_dict(), indent=2, sort_keys=True))
        return 0
    if not registry.loaded and not registry.failures:
        print("no plugins installed")
        return 0
    for plugin in registry.loaded:
        protocols = ", ".join(plugin.protocols) or "-"
        executables = ", ".join(plugin.executables) or "-"
        print(f"{plugin.name:<28} protocols {protocols:<24} executables {executables}")
    for failure in registry.failures:
        print(f"failed: {failure.name}: {failure.error}", file=sys.stderr)
    return 0


def cmd_plugins_validate(args: argparse.Namespace) -> int:
    report = validate_installed_plugins(
        host=args.host,
        username=args.username,
        port=args.port,
        options=_parse_options(args.option),
    )
    if args.json:
        print(result_to_json(report))
    else:
        print(report_to_text(report))
    return 0 if report.ok else 1


def cmd_plugins_scaffold(args: argparse.Namespace) -> int:
    result = scaffold_plugin(
        out_dir=args.out,
        project_name=args.name,
        module_name=args.module,
        protocol=args.protocol,
        client=args.client,
        force=args.force,
    )
    if args.json:
        print(result_to_json(result))
        return 0
    print(f"created plugin scaffold: {result.root}")
    for path in result.files:
        print(f"  {path}")
    print("next: python -m pip install -e . && row plugins validate")
    return 0


def cmd_snippet_add(args: argparse.Namespace) -> int:
    snippet = Snippet(
        name=args.name,
        command=args.command,
        description=args.description,
        tags=args.tag,
    )
    SnippetStore().add(snippet, replace=args.replace)
    print(f"saved snippet: {snippet.name}")
    return 0


def cmd_snippet_list(args: argparse.Namespace) -> int:
    snippets = SnippetStore().load()
    if args.json:
        print(json.dumps([snippet.to_dict() for snippet in snippets], indent=2))
        return 0
    for snippet in snippets:
        tags = ",".join(snippet.tags)
        print(f"{snippet.name:<24} {tags:<20} {snippet.command}")
    return 0


def cmd_snippet_show(args: argparse.Namespace) -> int:
    print(json.dumps(SnippetStore().get(args.name).to_dict(), indent=2, sort_keys=True))
    return 0


def cmd_snippet_remove(args: argparse.Namespace) -> int:
    SnippetStore().remove(args.name)
    print(f"removed snippet: {args.name}")
    return 0


def cmd_snippet_run(args: argparse.Namespace) -> int:
    snippet = SnippetStore().get(args.name)
    argv = run_snippet(snippet, dry_run=args.dry_run)
    print(" ".join(argv))
    return 0


def cmd_layout_save(args: argparse.Namespace) -> int:
    layout = Layout(
        name=args.name,
        orientation=args.orientation,
        panes=[parse_layout_pane(item) for item in args.pane],
        description=args.description,
    )
    LayoutStore().add(layout, replace=args.replace)
    print(f"saved layout: {layout.name}")
    return 0


def cmd_layout_list(args: argparse.Namespace) -> int:
    layouts = LayoutStore().load()
    if args.json:
        print(json.dumps([layout.to_dict() for layout in layouts], indent=2))
        return 0
    for layout in layouts:
        print(f"{layout.name:<24} {layout.orientation:<10} panes={len(layout.panes)}")
    return 0


def cmd_layout_show(args: argparse.Namespace) -> int:
    print(json.dumps(LayoutStore().get(args.name).to_dict(), indent=2, sort_keys=True))
    return 0


def cmd_layout_remove(args: argparse.Namespace) -> int:
    LayoutStore().remove(args.name)
    print(f"removed layout: {args.name}")
    return 0


def cmd_layout_run(args: argparse.Namespace) -> int:
    layout = LayoutStore().get(args.name)
    plans = build_layout_terminal_plans(layout, ProfileStore())
    results = run_layout_terminal_plans(plans, dry_run=args.dry_run)
    if args.json:
        print(json.dumps([result.to_dict() for result in results], indent=2))
        return 0
    for result in results:
        _print_layout_result(result)
    return 0


def cmd_broadcast(args: argparse.Namespace) -> int:
    profiles = _select_profiles(ProfileStore(), names=args.profile, group=args.group, tags=args.tag)
    results = run_broadcast(
        build_broadcast_plans(profiles, args.command),
        dry_run=args.dry_run,
        timeout=args.timeout,
    )
    if args.json:
        print(json.dumps([result.to_dict() for result in results], indent=2))
    else:
        for result in results:
            _print_broadcast_result(result)
    return 0 if all(result.ok for result in results) else 1


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


def cmd_keygen(args: argparse.Namespace) -> int:
    passphrase = _secret_from_env(args.passphrase_env, "key passphrase") if args.passphrase_env else ""
    plan = build_keygen_plan(
        output=args.out,
        key_type=args.type,
        bits=args.bits,
        comment=args.comment,
        passphrase=passphrase,
        resident=args.resident,
    )
    run_keygen(plan, dry_run=args.dry_run)
    print(plan.printable())
    return 0


def cmd_nettool_plan(args: argparse.Namespace) -> int:
    plan = build_network_tool_plan(args.tool, args.target, count=getattr(args, "count", 4))
    run_network_tool(plan, dry_run=args.dry_run)
    print(plan.printable())
    return 0


def cmd_nettool_port(args: argparse.Namespace) -> int:
    ok = check_tcp_port(args.host, args.port, timeout=args.timeout)
    print(f"{args.host}:{args.port} {'open' if ok else 'closed'}")
    return 0 if ok else 1


def cmd_x11_start(args: argparse.Namespace) -> int:
    plan = run_x_server(build_x_server_plan(display=args.display), dry_run=args.dry_run)
    print(plan.printable())
    for note in plan.notes:
        print(f"note: {note}")
    return 0


def cmd_vault_init(args: argparse.Namespace) -> int:
    passphrase = _vault_passphrase(confirm=True)
    LocalVault().init(passphrase)
    print("vault initialized")
    return 0


def cmd_vault_set(args: argparse.Namespace) -> int:
    passphrase = _vault_passphrase(confirm=False)
    secret = _vault_secret_value(args)
    LocalVault().set(args.name, secret, passphrase)
    print(f"secret saved: {args.name}")
    return 0


def cmd_vault_get(args: argparse.Namespace) -> int:
    if not args.show and not args.out:
        raise ValueError("refusing to print secret by default; use --show or --out")
    passphrase = _vault_passphrase(confirm=False)
    secret = LocalVault().get(args.name, passphrase)
    if args.out:
        _write_secret_file(args.out, secret)
        print(f"secret written: {args.out}")
    else:
        print(secret)
    return 0


def cmd_vault_list(args: argparse.Namespace) -> int:
    for name in LocalVault().list():
        print(name)
    return 0


def cmd_vault_delete(args: argparse.Namespace) -> int:
    if not args.force:
        raise ValueError("refusing to delete secret without --force")
    LocalVault().delete(args.name)
    print(f"secret deleted: {args.name}")
    return 0


def cmd_vault_status(args: argparse.Namespace) -> int:
    status = LocalVault().status()
    if args.json:
        print(json.dumps(status.to_dict(), indent=2, sort_keys=True))
        return 0
    print(f"path: {status.path}")
    print(f"initialized: {'yes' if status.initialized else 'no'}")
    print(f"backend: {'available' if status.backend_available else 'unavailable'}")
    if status.item_count is not None:
        print(f"secrets: {status.item_count}")
    if status.version is not None:
        print(f"version: {status.version}")
    if status.kdf:
        print(f"kdf: {status.kdf}")
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    BackupService().export_bundle(args.out)
    print(f"exported: {args.out}")
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


def cmd_gui(args: argparse.Namespace) -> int:
    from .gui import main as gui_main

    return int(gui_main())


def cmd_serve_web(args: argparse.Namespace) -> int:
    serve_web(host=args.host, port=args.port, allow_public_bind=args.allow_public_bind)
    return 0


def _first_run_payload(path: Path, store: ProfileStore) -> dict[str, object]:
    profiles = store.load(resolve=False)
    return first_run_payload(
        data_dir=path,
        profiles_file=store.path,
        profile_names=[profile.name for profile in profiles],
    )


def _parse_options(items: list[str]) -> dict[str, str]:
    options: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"option must be key=value: {item}")
        key, value = item.split("=", 1)
        options[key] = value
    return options


def _secret_from_env(name: str, label: str) -> str:
    if name not in os.environ:
        raise ValueError(f"{label} environment variable is not set: {name}")
    value = os.environ[name]
    if value == "":
        raise ValueError(f"{label} environment variable is empty: {name}")
    return value


def _vault_passphrase(confirm: bool) -> str:
    if "ROW_VAULT_PASSWORD" in os.environ:
        return _secret_from_env("ROW_VAULT_PASSWORD", "vault passphrase")
    return prompt_passphrase(confirm=confirm)


def _vault_secret_value(args: argparse.Namespace, input_stream=None) -> str:
    if getattr(args, "secret_env", None):
        return _secret_from_env(args.secret_env, "secret")
    if getattr(args, "stdin", False):
        stream = input_stream or sys.stdin
        return _strip_one_trailing_newline(stream.read())
    return getpass("Secret value: ")


def _strip_one_trailing_newline(value: str) -> str:
    if value.endswith("\r\n"):
        return value[:-2]
    if value.endswith("\n") or value.endswith("\r"):
        return value[:-1]
    return value


def _write_secret_file(path: Path, secret: str) -> None:
    write_text_atomic(path, secret, private=True)


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
    children = preview.get("children") or []
    if children:
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


def _print_broadcast_result(result: BroadcastResult) -> None:
    status = "DRY-RUN" if result.dry_run else ("OK" if result.ok else f"FAIL {result.returncode}")
    print(f"{result.profile_name}: {status}: {shlex.join(result.command)}")
    if result.stdout:
        print(result.stdout.rstrip())
    if result.stderr:
        print(result.stderr.rstrip(), file=sys.stderr)


def _print_layout_result(result: LayoutRunResult) -> None:
    status = "DRY-RUN" if result.dry_run else f"PID {result.pid}"
    print(f"{result.title}: {status}: {shlex.join(result.command)}")


def _parse_tunnels(items: list[str]) -> list[Tunnel]:
    tunnels: list[Tunnel] = []
    for item in items:
        parts = item.split(":")
        mode = parts[0]
        if mode == "dynamic" and len(parts) == 2:
            tunnels.append(Tunnel(mode=mode, local_port=int(parts[1])))
        elif mode in {"local", "remote"} and len(parts) == 5:
            tunnels.append(
                Tunnel(
                    mode=mode,
                    local_port=int(parts[1]),
                    remote_host=parts[2],
                    remote_port=int(parts[3]),
                    local_host=parts[4],
                )
            )
        elif mode in {"local", "remote"} and len(parts) == 4:
            tunnels.append(
                Tunnel(
                    mode=mode,
                    local_port=int(parts[1]),
                    remote_host=parts[2],
                    remote_port=int(parts[3]),
                )
            )
        else:
            raise ValueError(f"invalid tunnel: {item}")
    return tunnels


def _select_profiles(
    store: ProfileStore,
    names: list[str],
    group: str | None,
    tags: list[str],
) -> list[Profile]:
    if names:
        return [store.get(name) for name in names]
    profiles = store.load()
    if group:
        profiles = [profile for profile in profiles if profile.group == group]
    for tag in tags:
        profiles = [profile for profile in profiles if tag in profile.tags]
    if not profiles:
        raise ValueError("no profiles matched broadcast target")
    return profiles


if __name__ == "__main__":
    raise SystemExit(main())

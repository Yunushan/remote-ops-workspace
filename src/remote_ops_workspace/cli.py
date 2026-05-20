from __future__ import annotations

import argparse
import json
import os
import sys
from getpass import getpass
from pathlib import Path

from . import __version__
from .audit import append_event
from .doctor import run_doctor
from .features import feature_summary, load_feature_manifest
from .launcher import LauncherError, launch
from .models import Profile
from .paths import ensure_data_dir
from .storage import ProfileStore
from .sync import BackupService
from .vault import LocalVault, VaultBackendUnavailable, VaultError, prompt_passphrase
from .web_server import serve_web


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
    init.set_defaults(func=cmd_init)

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

    connect = sub.add_parser("connect", help="launch a profile")
    connect.add_argument("name")
    connect.add_argument("--dry-run", action="store_true")
    connect.set_defaults(func=cmd_connect)

    doctor = sub.add_parser("doctor", help="inspect platform and external client availability")
    doctor.add_argument("--json", action="store_true")
    doctor.set_defaults(func=cmd_doctor)

    features = sub.add_parser("features", help="show feature coverage manifest")
    features.add_argument("--json", action="store_true")
    features.set_defaults(func=cmd_features)

    vault = sub.add_parser("vault", help="local encrypted vault")
    vsub = vault.add_subparsers(required=True)
    vinit = vsub.add_parser("init", help="initialize vault")
    vinit.set_defaults(func=cmd_vault_init)
    vset = vsub.add_parser("set", help="set a secret")
    vset.add_argument("name")
    vset.set_defaults(func=cmd_vault_set)
    vget = vsub.add_parser("get", help="print a secret")
    vget.add_argument("name")
    vget.set_defaults(func=cmd_vault_get)
    vlist = vsub.add_parser("list", help="list secret names")
    vlist.set_defaults(func=cmd_vault_list)

    export = sub.add_parser("export", help="export profiles bundle")
    export.add_argument("--out", required=True, type=Path)
    export.set_defaults(func=cmd_export)

    imp = sub.add_parser("import", help="import profiles bundle")
    imp.add_argument("--in", dest="input", required=True, type=Path)
    imp.add_argument("--replace", action="store_true")
    imp.set_defaults(func=cmd_import)

    gui = sub.add_parser("gui", help="start PyQt6 desktop UI")
    gui.set_defaults(func=cmd_gui)

    web = sub.add_parser("serve-web", help="serve static Web/PWA app")
    web.add_argument("--host", default="127.0.0.1")
    web.add_argument("--port", default=8765, type=int)
    web.set_defaults(func=cmd_serve_web)

    return parser


def cmd_init(args: argparse.Namespace) -> int:
    path = ensure_data_dir()
    store = ProfileStore()
    store.init(with_examples=not args.no_examples)
    print(f"initialized: {path}")
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


def cmd_features(args: argparse.Namespace) -> int:
    if args.json:
        print(json.dumps(load_feature_manifest(), indent=2, sort_keys=True))
        return 0
    for row in feature_summary():
        print(f"{row['id']:<32} {row['status']:<18} {row['coverage']}")
    return 0


def cmd_vault_init(args: argparse.Namespace) -> int:
    passphrase = os.environ.get("ROW_VAULT_PASSWORD") or prompt_passphrase(confirm=True)
    LocalVault().init(passphrase)
    print("vault initialized")
    return 0


def cmd_vault_set(args: argparse.Namespace) -> int:
    passphrase = os.environ.get("ROW_VAULT_PASSWORD") or prompt_passphrase(confirm=False)
    secret = getpass("Secret value: ")
    LocalVault().set(args.name, secret, passphrase)
    print(f"secret saved: {args.name}")
    return 0


def cmd_vault_get(args: argparse.Namespace) -> int:
    passphrase = os.environ.get("ROW_VAULT_PASSWORD") or prompt_passphrase(confirm=False)
    print(LocalVault().get(args.name, passphrase))
    return 0


def cmd_vault_list(args: argparse.Namespace) -> int:
    for name in LocalVault().list():
        print(name)
    return 0


def cmd_export(args: argparse.Namespace) -> int:
    BackupService().export_bundle(args.out)
    print(f"exported: {args.out}")
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    count = BackupService().import_bundle(args.input, replace=args.replace)
    print(f"imported profiles: {count}")
    return 0


def cmd_gui(args: argparse.Namespace) -> int:
    from .gui import main as gui_main

    return int(gui_main())


def cmd_serve_web(args: argparse.Namespace) -> int:
    serve_web(host=args.host, port=args.port)
    return 0


def _parse_options(items: list[str]) -> dict[str, str]:
    options: dict[str, str] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"option must be key=value: {item}")
        key, value = item.split("=", 1)
        options[key] = value
    return options


if __name__ == "__main__":
    raise SystemExit(main())

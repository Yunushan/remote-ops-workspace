"""CLI commands for managed embedded servers and the local X server."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .embedded_cron import run_cron
from .moba_servers import (
    SERVER_CONTROL_PORTS,
    build_moba_server_config_plan,
    build_moba_server_plan,
    build_moba_server_runtime_bundle_plan,
    build_moba_server_runtime_status,
    build_moba_server_suite_status,
    run_http_server,
    start_moba_server,
    stop_moba_server,
    validate_moba_server_release_evidence,
    write_moba_server_runtime_bundle,
)
from .x11 import (
    build_moba_x_server_package_status,
    build_moba_x_server_plan,
    build_moba_x_server_runtime_bundle_plan,
    build_moba_x_server_status,
    run_moba_x_server_smoke,
    start_moba_x_server,
    stop_moba_x_server,
    validate_moba_x_server_release_evidence,
    write_moba_x_server_runtime_bundle,
    write_moba_x_server_smoke_evidence,
)


def add_managed_runtime_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    servers = sub.add_parser("servers", help="manage MobaXterm-style local server workflows")
    servers_sub = servers.add_subparsers(required=True)
    servers_status = servers_sub.add_parser("status", help="show embedded server suite status")
    servers_status.add_argument("--json", action="store_true")
    servers_status.set_defaults(func=cmd_servers_status)
    servers_runtime = servers_sub.add_parser("runtime-status", help="inspect packaged embedded server daemon roots")
    servers_runtime.add_argument("--root", action="append", type=Path, help="embedded server daemon runtime root to scan")
    servers_runtime.add_argument("--json", action="store_true")
    servers_runtime.set_defaults(func=cmd_servers_runtime_status)
    servers_bundle = servers_sub.add_parser("bundle-runtime", help="assemble a packaged embedded server daemon root")
    servers_bundle.add_argument("service", choices=[service for service in SERVER_CONTROL_PORTS if service != "cron"])
    servers_bundle.add_argument("--out", required=True, type=Path, help="output packaged daemon runtime directory")
    servers_bundle.add_argument("--runtime", help="runtime key such as sshd, tftpd, x11vnc or nfsd")
    servers_bundle.add_argument("--source", type=Path, help="source daemon executable to copy into the bundle")
    servers_bundle.add_argument("--system", help="target system key; defaults to this host")
    servers_bundle.add_argument("--release-target", default="local-bundle")
    servers_bundle.add_argument("--executable-name", help="override packaged executable filename")
    servers_bundle.add_argument("--allow-placeholder", action="store_true", help="allow placeholder daemon for rehearsal")
    servers_bundle.add_argument("--json", action="store_true")
    servers_bundle.set_defaults(func=cmd_servers_bundle_runtime)
    servers_config = servers_sub.add_parser("config-plan", help="build an embedded server auth/hardening configuration plan")
    servers_config.add_argument("service", choices=list(SERVER_CONTROL_PORTS))
    servers_config.add_argument("--host", default="127.0.0.1")
    servers_config.add_argument("--port", type=int)
    servers_config.add_argument("--root", type=Path)
    servers_config.add_argument("--hardening-profile", default="loopback-private", choices=["loopback-private", "strict-private", "trusted-lan"])
    servers_config.add_argument("--require-auth", action="store_true")
    servers_config.add_argument("--require-tls", action="store_true")
    servers_config.add_argument("--allow-public-bind", action="store_true")
    servers_config.add_argument("--json", action="store_true")
    servers_config.set_defaults(func=cmd_servers_config_plan)
    servers_verify = servers_sub.add_parser("evidence-verify", help="verify packaged embedded server release evidence")
    servers_verify.add_argument("--evidence", required=True, type=Path)
    servers_verify.add_argument("--assets-dir", type=Path)
    servers_verify.add_argument("--json", action="store_true")
    servers_verify.set_defaults(func=cmd_servers_evidence_verify)
    servers_start = servers_sub.add_parser("start", help="start or inspect a managed local server")
    servers_start.add_argument("service", choices=list(SERVER_CONTROL_PORTS))
    servers_start.add_argument("--host", default="127.0.0.1")
    servers_start.add_argument("--port", type=int)
    servers_start.add_argument("--root", type=Path)
    servers_start.add_argument("--allow-public-bind", action="store_true")
    servers_start.add_argument("--require-tls", action="store_true")
    servers_start.add_argument("--hardening-profile", default="loopback-private")
    servers_start.add_argument("--dry-run", action="store_true")
    servers_start.add_argument("--json", action="store_true")
    servers_start.set_defaults(func=cmd_servers_start)
    for parser in (servers_config, servers_start):
        parser.add_argument("--crontab", type=Path, help="Cron schedule file (default: the workspace crontab)")
        parser.add_argument("--iperf-version", type=int, choices=(2, 3), help="select Iperf protocol (default: 2)")

    cron_runtime = servers_sub.add_parser("_cron-runtime", help=argparse.SUPPRESS)
    cron_runtime.add_argument("--crontab", type=Path, required=True)
    cron_runtime.set_defaults(func=cmd_servers_cron_runtime)

    http_runtime = servers_sub.add_parser("_http-runtime", help=argparse.SUPPRESS)
    http_runtime.add_argument("--host", required=True)
    http_runtime.add_argument("--port", required=True, type=int)
    http_runtime.add_argument("--root", required=True, type=Path)
    http_runtime.add_argument("--allow-public-bind", action="store_true")
    http_runtime.set_defaults(func=cmd_servers_http_runtime)

    ftp_runtime = servers_sub.add_parser("_ftp-runtime", help=argparse.SUPPRESS)
    ftp_runtime.add_argument("--host", required=True)
    ftp_runtime.add_argument("--port", required=True, type=int)
    ftp_runtime.add_argument("--root", required=True, type=Path)
    ftp_runtime.set_defaults(func=cmd_servers_ftp_runtime)
    servers_stop = servers_sub.add_parser("stop", help="stop a managed local server")
    servers_stop.add_argument("service", choices=list(SERVER_CONTROL_PORTS))
    servers_stop.add_argument("--json", action="store_true")
    servers_stop.set_defaults(func=cmd_servers_stop)

    x11 = sub.add_parser("x11", help="manage local X server helper")
    x11_sub = x11.add_subparsers(required=True)
    x11_start = x11_sub.add_parser("start", help="start or inspect a local X server helper")
    x11_start.add_argument("--display", default=":0")
    x11_start.add_argument(
        "--allow-tcp",
        action="store_true",
        help="enable authenticated TCP, required for managed Windows X servers (may listen on all interfaces)",
    )
    x11_start.add_argument("--authority-file", type=Path)
    x11_start.add_argument("--dry-run", action="store_true")
    x11_start.add_argument("--json", action="store_true")
    x11_start.set_defaults(func=cmd_x11_start)
    x11_status = x11_sub.add_parser("status", help="inspect managed X server runtime status")
    x11_status.add_argument("--display", default=":0")
    x11_status.add_argument("--json", action="store_true")
    x11_status.set_defaults(func=cmd_x11_status)
    x11_package = x11_sub.add_parser("package-status", help="inspect packaged/bundled X server runtime roots")
    x11_package.add_argument("--root", action="append", type=Path, help="packaged X server runtime root to scan")
    x11_package.add_argument("--json", action="store_true")
    x11_package.set_defaults(func=cmd_x11_package_status)
    x11_bundle = x11_sub.add_parser("bundle-runtime", help="assemble a packaged X server runtime root")
    x11_bundle.add_argument("--out", required=True, type=Path, help="output packaged X server runtime directory")
    x11_bundle.add_argument("--runtime", required=True, help="runtime key such as vcxsrv, xquartz, xorg or xvfb")
    x11_bundle.add_argument("--source", type=Path, help="source X server executable to copy into the bundle")
    x11_bundle.add_argument("--system", help="target system key; defaults to this host")
    x11_bundle.add_argument("--release-target", default="local-bundle")
    x11_bundle.add_argument("--executable-name", help="override packaged executable filename")
    x11_bundle.add_argument("--allow-placeholder", action="store_true", help="allow placeholder runtime for rehearsal")
    x11_bundle.add_argument("--json", action="store_true")
    x11_bundle.set_defaults(func=cmd_x11_bundle_runtime)
    x11_stop = x11_sub.add_parser("stop", help="stop the managed X server process recorded by ROW")
    x11_stop.add_argument("--json", action="store_true")
    x11_stop.set_defaults(func=cmd_x11_stop)
    x11_smoke = x11_sub.add_parser("smoke", help="run an X11 display probe and optionally write evidence JSON")
    x11_smoke.add_argument("--display", default=":0")
    x11_smoke.add_argument("--probe-command", help="custom probe command, for example: xdpyinfo -display :0")
    x11_smoke.add_argument("--timeout", type=float, default=5.0)
    x11_smoke.add_argument("--out", type=Path)
    x11_smoke.add_argument("--json", action="store_true")
    x11_smoke.set_defaults(func=cmd_x11_smoke)
    x11_verify = x11_sub.add_parser("evidence-verify", help="verify MobaXterm-style packaged X server release evidence")
    x11_verify.add_argument("--evidence", required=True, type=Path)
    x11_verify.add_argument("--assets-dir", type=Path)
    x11_verify.add_argument("--json", action="store_true")
    x11_verify.set_defaults(func=cmd_x11_evidence_verify)


def cmd_servers_status(args: argparse.Namespace) -> int:
    status = build_moba_server_suite_status()
    if args.json:
        print(json.dumps(status.to_dict(), indent=2, sort_keys=True))
        return 0
    print(f"system: {status.system}")
    print("services:")
    for service in status.services:
        marker = "available" if service.available else "missing"
        lifecycle = ""
        if service.lifecycle is not None:
            lifecycle = f" lifecycle={service.lifecycle.state} pid={service.lifecycle.pid or 'none'}"
        print(f"  {service.key:<8} {marker:<9} port={service.default_port:<5} runtime={service.selected_runtime}{lifecycle}")
    for note in status.notes:
        print(f"note: {note}")
    return 0


def cmd_servers_runtime_status(args: argparse.Namespace) -> int:
    status = build_moba_server_runtime_status(roots=args.root)
    if args.json:
        print(json.dumps(status.to_dict(), indent=2, sort_keys=True))
        return 0
    print(f"packaged daemon runtime: {'yes' if status.packaged_available else 'no'}")
    print("roots:")
    for root in status.roots:
        print(f"  {root}")
    print("service coverage:")
    for service, available in status.service_coverage.items():
        print(f"  {service:<8} {'available' if available else 'missing'}")
    for note in status.notes:
        print(f"note: {note}")
    return 0


def cmd_servers_bundle_runtime(args: argparse.Namespace) -> int:
    plan = build_moba_server_runtime_bundle_plan(
        args.out,
        args.service,
        runtime_key=args.runtime,
        source_path=args.source,
        system=args.system,
        release_target=args.release_target,
        executable_name=args.executable_name,
        allow_placeholder=args.allow_placeholder,
    )
    result = write_moba_server_runtime_bundle(plan)
    service_available = result.runtime_status.service_coverage.get(plan.service, False)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"embedded server runtime bundle: {'available' if service_available else 'not discovered'}")
        print(f"service: {plan.service}")
        print(f"root: {result.root}")
        print(f"runtime: {result.executable_path}")
        print(f"manifest: {result.manifest_path}")
        print(f"sha256: {result.runtime_sha256}")
        if result.placeholder:
            print("placeholder: yes")
        for note in result.notes:
            print(f"note: {note}")
    return 0 if service_available else 1


def cmd_servers_config_plan(args: argparse.Namespace) -> int:
    plan = build_moba_server_config_plan(
        args.service,
        host=args.host,
        port=args.port,
        root=args.root,
        hardening_profile=args.hardening_profile,
        require_auth=True if args.require_auth else None,
        require_tls=args.require_tls,
        allow_public_bind=args.allow_public_bind,
        crontab=getattr(args, "crontab", None), iperf_version=getattr(args, "iperf_version", None),
    )
    if args.json:
        print(json.dumps(plan.to_dict(), indent=2, sort_keys=True))
        return 0
    print(f"service: {plan.service}")
    print(f"bind: {plan.host}:{plan.port}" if plan.host else f"crontab: {plan.settings['crontab']}")
    print(f"hardening: {plan.hardening_profile}")
    print(f"auth required: {'yes' if plan.auth_required else 'no'}")
    for note in plan.notes:
        print(f"note: {note}")
    return 0


def cmd_servers_evidence_verify(args: argparse.Namespace) -> int:
    result = validate_moba_server_release_evidence(args.evidence, assets_dir=args.assets_dir)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"embedded server release evidence: {'passed' if result.passed else 'failed'}")
        print(f"evidence: {result.evidence_path}")
        print(f"assets: {result.assets_dir}")
        for error in result.errors:
            print(f"error: {error}")
        for warning in result.warnings:
            print(f"warning: {warning}")
    return 0 if result.passed else 1


def cmd_servers_start(args: argparse.Namespace) -> int:
    plan = build_moba_server_plan(
        args.service,
        host=args.host,
        port=args.port,
        root=args.root,
        allow_public_bind=args.allow_public_bind,
        require_tls=getattr(args, "require_tls", False),
        hardening_profile=getattr(args, "hardening_profile", "loopback-private"),
        crontab=getattr(args, "crontab", None), iperf_version=getattr(args, "iperf_version", None),
    )
    record = start_moba_server(plan, dry_run=args.dry_run)
    if args.json:
        payload = plan.to_dict()
        payload["lifecycle"] = record.to_dict()
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    print(plan.printable())
    print(f"lifecycle: {record.state} pid={record.pid or 'none'} state={record.state_path}")
    for note in plan.notes:
        print(f"note: {note}")
    return 0


def cmd_servers_cron_runtime(args: argparse.Namespace) -> int:
    run_cron(args.crontab)
    return 0


def cmd_servers_http_runtime(args: argparse.Namespace) -> int:
    run_http_server(args.host, args.port, args.root, allow_public_bind=args.allow_public_bind)
    return 0


def cmd_servers_ftp_runtime(args: argparse.Namespace) -> int:
    from .embedded_ftp import main as ftp_main

    return ftp_main(["--host", args.host, "--port", str(args.port), "--root", str(args.root)])


def cmd_servers_stop(args: argparse.Namespace) -> int:
    record = stop_moba_server(args.service)
    if args.json:
        print(json.dumps(record.to_dict(), indent=2, sort_keys=True))
        return 0
    print(f"lifecycle: {record.state} pid={record.pid or 'none'} state={record.state_path}")
    return 0


def cmd_x11_start(args: argparse.Namespace) -> int:
    managed_plan = build_moba_x_server_plan(
        display=args.display,
        allow_tcp=getattr(args, "allow_tcp", False),
        authority_path=getattr(args, "authority_file", None),
    )
    record = start_moba_x_server(managed_plan, dry_run=args.dry_run)
    if args.json:
        payload = managed_plan.to_dict()
        payload["lifecycle"] = record.to_dict()
        print(json.dumps(payload, indent=2, sort_keys=True))
        return 0
    print(managed_plan.printable())
    print(f"lifecycle: {record.state} pid={record.pid or 'none'} state={record.state_path}")
    for note in managed_plan.notes:
        print(f"note: {note}")
    return 0


def cmd_x11_status(args: argparse.Namespace) -> int:
    status = build_moba_x_server_status(display=args.display)
    if args.json:
        print(json.dumps(status.to_dict(), indent=2, sort_keys=True))
        return 0
    print(f"display: {status.display}")
    print(f"available: {'yes' if status.available else 'no'}")
    print(f"selected runtime: {status.selected_runtime}")
    print(f"display in use: {'yes' if status.display_in_use else 'no'}")
    if status.lifecycle is not None:
        print(
            f"managed lifecycle: {status.lifecycle.state} "
            f"pid={status.lifecycle.pid or 'none'} "
            f"running={'yes' if status.lifecycle.running else 'no'}"
        )
    print("candidates:")
    for candidate in status.candidates:
        marker = "available" if candidate.available else "missing"
        print(f"  {candidate.key:<12} {marker:<9} {candidate.executable}")
    print("extensions:")
    for extension in status.extensions:
        print(f"  {extension.key:<10} {extension.status:<18} {extension.label}")
    for note in status.notes:
        print(f"note: {note}")
    return 0


def cmd_x11_package_status(args: argparse.Namespace) -> int:
    status = build_moba_x_server_package_status(roots=args.root)
    if args.json:
        print(json.dumps(status.to_dict(), indent=2, sort_keys=True))
        return 0
    print(f"system: {status.system}")
    print(f"packaged runtime: {'yes' if status.packaged_available else 'no'}")
    print("roots:")
    for root in status.roots:
        print(f"  {root}")
    print("packaged candidates:")
    if status.candidates:
        for candidate in status.candidates:
            print(f"  {candidate.key:<12} available  {candidate.executable}")
    else:
        print("  none")
    for note in status.notes:
        print(f"note: {note}")
    return 0


def cmd_x11_bundle_runtime(args: argparse.Namespace) -> int:
    plan = build_moba_x_server_runtime_bundle_plan(
        args.out,
        runtime_key=args.runtime,
        source_path=args.source,
        system=args.system,
        release_target=args.release_target,
        executable_name=args.executable_name,
        allow_placeholder=args.allow_placeholder,
    )
    result = write_moba_x_server_runtime_bundle(plan)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"x11 runtime bundle: {'available' if result.package_status.packaged_available else 'not discovered'}")
        print(f"root: {result.root}")
        print(f"runtime: {result.executable_path}")
        print(f"manifest: {result.manifest_path}")
        print(f"sha256: {result.runtime_sha256}")
        if result.placeholder:
            print("placeholder: yes")
        for note in result.notes:
            print(f"note: {note}")
    return 0 if result.package_status.packaged_available else 1


def cmd_x11_stop(args: argparse.Namespace) -> int:
    record = stop_moba_x_server()
    if args.json:
        print(json.dumps(record.to_dict(), indent=2, sort_keys=True))
        return 0
    print(f"lifecycle: {record.state} pid={record.pid or 'none'} state={record.state_path}")
    return 0


def cmd_x11_smoke(args: argparse.Namespace) -> int:
    evidence = run_moba_x_server_smoke(
        display=args.display,
        probe_command=args.probe_command,
        timeout_seconds=args.timeout,
    )
    if args.out:
        evidence = write_moba_x_server_smoke_evidence(evidence, args.out)
    if args.json:
        print(json.dumps(evidence.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"x11 smoke: {evidence.status} display={evidence.display} passed={'yes' if evidence.passed else 'no'}")
        if evidence.evidence_path:
            print(f"evidence: {evidence.evidence_path}")
        if evidence.evidence_sha256:
            print(f"evidence_sha256: {evidence.evidence_sha256}")
        for note in evidence.notes or []:
            print(f"note: {note}")
    return 0 if evidence.passed else 1


def cmd_x11_evidence_verify(args: argparse.Namespace) -> int:
    result = validate_moba_x_server_release_evidence(args.evidence, assets_dir=args.assets_dir)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"x11 release evidence: {'passed' if result.passed else 'failed'}")
        print(f"evidence: {result.evidence_path}")
        print(f"assets: {result.assets_dir}")
        for error in result.errors:
            print(f"error: {error}")
        for warning in result.warnings:
            print(f"warning: {warning}")
    return 0 if result.passed else 1

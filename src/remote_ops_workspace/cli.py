from __future__ import annotations

import argparse
import json
import os
import shlex
import subprocess
import sys
from getpass import getpass
from pathlib import Path

from . import __version__
from .audit import append_event
from .broadcast import BroadcastResult, build_broadcast_plans, run_broadcast
from .doctor import run_doctor
from .enterprise_policy import assert_profile_launch_allowed
from .features import coverage_report, feature_summary, load_feature_manifest
from .file_safety import write_text_atomic
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
from .moba_customizer import (
    REQUIRED_POLICY_SURFACES,
    build_moba_professional_customizer_plan,
    build_professional_deployment_evidence_bundle_plan,
    build_professional_deployment_plan,
    validate_professional_deployment_evidence,
    validate_professional_update_manifest,
    write_moba_professional_customizer_bundle,
    write_professional_deployment_evidence_bundle,
)
from .moba_macros import (
    MobaMacroStore,
    build_macro_gui_capture_plan,
    build_macro_live_evidence_bundle_plan,
    build_macro_live_replay_plans,
    build_macro_replay_plans,
    record_typed_macro,
    review_macro_live_replay,
    run_macro_replay,
    validate_macro_live_replay_evidence,
    write_macro_live_evidence_bundle,
)
from .moba_mobapt import (
    build_mobapt_environment_status,
    build_mobapt_package_plan,
    build_mobapt_runtime_bundle_plan,
    build_mobapt_runtime_status,
    run_mobapt_package_plan,
    validate_mobapt_cache_evidence,
    write_mobapt_runtime_bundle,
)
from .moba_servers import (
    SERVER_DEFAULT_PORTS,
    build_moba_server_config_plan,
    build_moba_server_plan,
    build_moba_server_runtime_bundle_plan,
    build_moba_server_runtime_status,
    build_moba_server_suite_status,
    start_moba_server,
    stop_moba_server,
    validate_moba_server_release_evidence,
    write_moba_server_runtime_bundle,
)
from .moba_smartcards import (
    MobaSmartCardCertificate,
    build_mobagent_smartcard_plan,
    build_smartcard_inventory_plan,
    build_smartcard_release_evidence_bundle_plan,
    build_smartcard_ssh_browser_plan,
    review_smartcard_certificate_selection,
    validate_smartcard_release_evidence,
    write_smartcard_release_evidence_bundle,
)
from .moba_ssh_browser import (
    build_moba_ssh_browser_open_plan,
    load_moba_ssh_browser_preferences,
    review_moba_ssh_browser_overwrite,
    update_moba_ssh_browser_columns,
    update_moba_ssh_browser_location,
)
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
from .models import Profile, Tunnel
from .network_tools import build_network_tool_plan, check_tcp_port, run_network_tool
from .paths import ensure_data_dir
from .platform_targets import load_platform_targets
from .plugin_dev import (
    DEFAULT_PLUGIN_CHECK_HOST,
    DEFAULT_PLUGIN_CHECK_USERNAME,
    report_to_text,
    result_to_json,
    scaffold_plugin,
    validate_installed_plugins,
)
from .plugins import load_plugin_registry
from .profile_importers import SUPPORTED_IMPORT_FORMATS, import_profiles_into_store
from .snippets import Snippet, SnippetStore, run_snippet
from .storage import ProfileStore
from .sync import BackupService, DirectorySyncProvider
from .vault import LocalVault, VaultBackendUnavailable, VaultError, prompt_passphrase
from .web_server import serve_web
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


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (KeyError, ValueError, FileExistsError, LauncherError, VaultError, VaultBackendUnavailable) as exc:
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

    customizer = sub.add_parser("customizer", help="build enterprise customization bundles")
    customizer_sub = customizer.add_subparsers(required=True)
    customizer_build = customizer_sub.add_parser(
        "build",
        help="build a MobaXterm Professional Customizer-style ROW enterprise bundle",
    )
    customizer_build.add_argument("--out", required=True, type=Path)
    customizer_build.add_argument("--brand-name", required=True)
    customizer_build.add_argument("--organization", default="")
    welcome_source = customizer_build.add_mutually_exclusive_group()
    welcome_source.add_argument("--welcome-message")
    welcome_source.add_argument("--welcome-file", type=Path)
    customizer_build.add_argument("--logo", type=Path)
    customizer_build.add_argument("--settings", type=Path)
    customizer_build.add_argument("--profiles", type=Path)
    customizer_build.add_argument("--policy", type=Path)
    customizer_build.add_argument(
        "--lock-setting",
        action="append",
        default=[],
        help="force an enterprise setting value as key=value",
    )
    customizer_build.add_argument("--force", action="store_true")
    customizer_build.add_argument("--json", action="store_true")
    customizer_build.set_defaults(func=cmd_customizer_build)
    customizer_deployment = customizer_sub.add_parser(
        "deployment-plan",
        help="plan Professional-style installer branding, policy locks and update channels",
    )
    customizer_deployment.add_argument("--brand-name", required=True)
    customizer_deployment.add_argument("--organization", default="")
    customizer_deployment.add_argument("--version", default=__version__)
    customizer_deployment.add_argument("--logo", type=Path)
    customizer_deployment.add_argument("--policy", type=Path)
    customizer_deployment.add_argument(
        "--lock-setting",
        action="append",
        default=[],
        help="force an enterprise setting value as key=value",
    )
    customizer_deployment.add_argument("--update-url", required=True)
    customizer_deployment.add_argument("--update-public-key", required=True)
    customizer_deployment.add_argument("--update-channel", default="stable")
    customizer_deployment.add_argument("--update-interval-hours", type=int, default=24)
    customizer_deployment.add_argument("--rollout-ring", default="enterprise")
    customizer_deployment.add_argument(
        "--surface",
        action="append",
        default=[],
        help="policy enforcement surface; defaults to CLI, GUI, Web, profile editor, quick connect and launcher",
    )
    customizer_deployment.add_argument("--json", action="store_true")
    customizer_deployment.set_defaults(func=cmd_customizer_deployment_plan)
    customizer_evidence_bundle = customizer_sub.add_parser(
        "evidence-bundle",
        help="assemble Professional-style deployment release evidence",
    )
    customizer_evidence_bundle.add_argument("--brand-name", required=True)
    customizer_evidence_bundle.add_argument("--organization", default="")
    customizer_evidence_bundle.add_argument("--version", default=__version__)
    customizer_evidence_bundle.add_argument("--logo", type=Path)
    customizer_evidence_bundle.add_argument("--policy", type=Path)
    customizer_evidence_bundle.add_argument(
        "--lock-setting",
        action="append",
        default=[],
        help="force an enterprise setting value as key=value",
    )
    customizer_evidence_bundle.add_argument("--update-url", required=True)
    customizer_evidence_bundle.add_argument("--update-public-key", required=True)
    customizer_evidence_bundle.add_argument("--update-channel", default="stable")
    customizer_evidence_bundle.add_argument("--update-interval-hours", type=int, default=24)
    customizer_evidence_bundle.add_argument("--rollout-ring", default="enterprise")
    customizer_evidence_bundle.add_argument("--out-dir", required=True, type=Path)
    customizer_evidence_bundle.add_argument("--bundle-manifest-evidence", required=True, type=Path)
    customizer_evidence_bundle.add_argument("--installer-evidence", required=True, type=Path)
    customizer_evidence_bundle.add_argument("--policy-evidence", required=True, type=Path)
    customizer_evidence_bundle.add_argument("--update-evidence", required=True, type=Path)
    customizer_evidence_bundle.add_argument("--update-manifest", required=True, type=Path)
    customizer_evidence_bundle.add_argument("--update-assets-dir", type=Path)
    customizer_evidence_bundle.add_argument("--bundle-manifest-sha256", required=True)
    customizer_evidence_bundle.add_argument("--release-target", default="windows-x64")
    customizer_evidence_bundle.add_argument("--bundle-command", default="")
    customizer_evidence_bundle.add_argument("--installer-command", default="")
    customizer_evidence_bundle.add_argument("--policy-command", default="")
    customizer_evidence_bundle.add_argument("--update-command", default="")
    customizer_evidence_bundle.add_argument("--sha256s-present", action="store_true")
    customizer_evidence_bundle.add_argument("--windows-exe-rebranded", action="store_true")
    customizer_evidence_bundle.add_argument("--windows-msi-rebranded", action="store_true")
    customizer_evidence_bundle.add_argument("--product-name-matches-brand", action="store_true")
    customizer_evidence_bundle.add_argument("--logo-applied", action="store_true")
    customizer_evidence_bundle.add_argument(
        "--surface-passed",
        action="append",
        default=[],
        choices=REQUIRED_POLICY_SURFACES,
        help="policy surface proven by release evidence",
    )
    customizer_evidence_bundle.add_argument(
        "--all-policy-surfaces-passed",
        action="store_true",
        help="mark CLI, GUI, Web, profile editor, quick connect and launcher policy checks as passed",
    )
    customizer_evidence_bundle.add_argument("--https-update-url", action="store_true")
    customizer_evidence_bundle.add_argument("--signature-verified", action="store_true")
    customizer_evidence_bundle.add_argument("--organization-channel", action="store_true")
    customizer_evidence_bundle.add_argument("--json", action="store_true")
    customizer_evidence_bundle.set_defaults(func=cmd_customizer_evidence_bundle)
    customizer_evidence = customizer_sub.add_parser(
        "evidence-verify",
        help="verify Professional-style deployment release evidence",
    )
    customizer_evidence.add_argument("--evidence", required=True, type=Path)
    customizer_evidence.add_argument("--assets-dir", type=Path)
    customizer_evidence.add_argument("--json", action="store_true")
    customizer_evidence.set_defaults(func=cmd_customizer_evidence_verify)
    customizer_update = customizer_sub.add_parser(
        "update-verify",
        help="verify a Professional-style signed update-channel manifest",
    )
    customizer_update.add_argument("--manifest", required=True, type=Path)
    customizer_update.add_argument("--public-key", required=True)
    customizer_update.add_argument("--channel", default="")
    customizer_update.add_argument("--organization", default="")
    customizer_update.add_argument("--assets-dir", type=Path)
    customizer_update.add_argument("--json", action="store_true")
    customizer_update.set_defaults(func=cmd_customizer_update_verify)

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

    macro = sub.add_parser("macro", help="record and replay typed terminal macros")
    macro_sub = macro.add_subparsers(required=True)
    macro_record = macro_sub.add_parser("record", help="save a typed terminal macro recording")
    macro_record.add_argument("--name", required=True)
    macro_source = macro_record.add_mutually_exclusive_group(required=True)
    macro_source.add_argument("--text")
    macro_source.add_argument("--text-file", type=Path)
    macro_source.add_argument("--stdin", action="store_true")
    macro_record.add_argument("--description", default="")
    macro_record.add_argument("--tag", action="append", default=[])
    macro_record.add_argument("--delay-ms", type=int, default=0)
    macro_record.add_argument("--replace", action="store_true")
    macro_record.add_argument("--json", action="store_true")
    macro_record.set_defaults(func=cmd_macro_record)
    macro_list = macro_sub.add_parser("list", help="list typed macro recordings")
    macro_list.add_argument("--json", action="store_true")
    macro_list.set_defaults(func=cmd_macro_list)
    macro_show = macro_sub.add_parser("show", help="show a typed macro recording")
    macro_show.add_argument("name")
    macro_show.set_defaults(func=cmd_macro_show)
    macro_remove = macro_sub.add_parser("remove", help="remove a typed macro recording")
    macro_remove.add_argument("name")
    macro_remove.set_defaults(func=cmd_macro_remove)
    macro_replay = macro_sub.add_parser("replay", help="replay a typed macro to SSH profiles")
    macro_replay.add_argument("name")
    macro_replay.add_argument("--profile", action="append", default=[])
    macro_replay.add_argument("--group")
    macro_replay.add_argument("--tag", action="append", default=[])
    macro_replay.add_argument("--timeout", type=float)
    macro_replay.add_argument("--dry-run", action="store_true")
    macro_replay.add_argument("--json", action="store_true")
    macro_replay.set_defaults(func=cmd_macro_replay)
    macro_capture_plan = macro_sub.add_parser(
        "capture-plan",
        help="show GUI terminal macro capture controls and timing contract",
    )
    macro_capture_plan.add_argument("name")
    macro_capture_plan.add_argument("--json", action="store_true")
    macro_capture_plan.set_defaults(func=cmd_macro_capture_plan)
    macro_live_plan = macro_sub.add_parser(
        "live-plan",
        help="build live connected-terminal macro replay plans with confirmation/cancel review",
    )
    macro_live_plan.add_argument("name")
    macro_live_plan.add_argument("--profile", action="append", default=[])
    macro_live_plan.add_argument("--group")
    macro_live_plan.add_argument("--tag", action="append", default=[])
    macro_live_plan.add_argument("--connected-profile", action="append", default=[])
    macro_live_plan.add_argument("--pane-id", action="append", default=[], help="profile=pane-id mapping")
    macro_live_plan.add_argument("--force", action="store_true")
    macro_live_plan.add_argument("--json", action="store_true")
    macro_live_plan.set_defaults(func=cmd_macro_live_plan)
    macro_evidence_bundle = macro_sub.add_parser(
        "evidence-bundle",
        help="assemble MobaXterm-style live macro capture/replay release evidence",
    )
    macro_evidence_bundle.add_argument("name")
    macro_evidence_bundle.add_argument("--profile", action="append", default=[])
    macro_evidence_bundle.add_argument("--group")
    macro_evidence_bundle.add_argument("--tag", action="append", default=[])
    macro_evidence_bundle.add_argument("--out-dir", required=True, type=Path)
    macro_evidence_bundle.add_argument("--capture-evidence", required=True, type=Path)
    macro_evidence_bundle.add_argument("--review-evidence", required=True, type=Path)
    macro_evidence_bundle.add_argument(
        "--replay-evidence",
        action="append",
        required=True,
        default=[],
        help="profile=path proof file for each replayed target profile",
    )
    macro_evidence_bundle.add_argument("--release-target", default="local-bundle")
    macro_evidence_bundle.add_argument("--connected-profile", action="append", default=[])
    macro_evidence_bundle.add_argument("--pane-id", action="append", default=[], help="profile=pane-id mapping")
    macro_evidence_bundle.add_argument("--capture-command", default="")
    macro_evidence_bundle.add_argument("--review-command", default="")
    macro_evidence_bundle.add_argument("--replay-command", action="append", default=[], help="profile=command")
    macro_evidence_bundle.add_argument("--gui-record-button", action="store_true")
    macro_evidence_bundle.add_argument("--gui-stop-button", action="store_true")
    macro_evidence_bundle.add_argument("--gui-cancel-button", action="store_true")
    macro_evidence_bundle.add_argument("--per-event-timing-captured", action="store_true")
    macro_evidence_bundle.add_argument("--confirmation-prompt", action="store_true")
    macro_evidence_bundle.add_argument("--cancel-prompt-verified", action="store_true")
    macro_evidence_bundle.add_argument("--conflict-checked", action="store_true")
    macro_evidence_bundle.add_argument("--real-connected-session", action="store_true")
    macro_evidence_bundle.add_argument("--live-terminal-pane", action="store_true")
    macro_evidence_bundle.add_argument("--per-keystroke-timing-replay", action="store_true")
    macro_evidence_bundle.add_argument("--json", action="store_true")
    macro_evidence_bundle.set_defaults(func=cmd_macro_evidence_bundle)
    macro_evidence = macro_sub.add_parser(
        "evidence-verify",
        help="verify MobaXterm-style live macro capture/replay release evidence",
    )
    macro_evidence.add_argument("--evidence", required=True, type=Path)
    macro_evidence.add_argument("--assets-dir", type=Path)
    macro_evidence.add_argument("--json", action="store_true")
    macro_evidence.set_defaults(func=cmd_macro_evidence_verify)

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

    smartcard = sub.add_parser("smartcard", help="manage MobaXterm 26.4-style SSH smart-card workflows")
    smartcard_sub = smartcard.add_subparsers(required=True)
    smartcard_inventory = smartcard_sub.add_parser(
        "inventory-plan",
        help="build a smart-card certificate inventory and OpenSSH public-key retrieval plan",
    )
    smartcard_inventory.add_argument("--provider", default="microsoft-capi")
    smartcard_inventory.add_argument("--json", action="store_true")
    smartcard_inventory.set_defaults(func=cmd_smartcard_inventory_plan)
    smartcard_select = smartcard_sub.add_parser(
        "select-review",
        help="review selecting a smart-card certificate in SSH session expert settings",
    )
    smartcard_select.add_argument("profile")
    smartcard_select.add_argument("--certificate-id", required=True)
    smartcard_select.add_argument(
        "--certificate",
        action="append",
        default=[],
        help="available certificate as id|label|provider|fingerprint_sha256|public_key",
    )
    smartcard_select.add_argument("--provider", default="microsoft-capi")
    smartcard_select.add_argument("--add-to-mobagent", action="store_true")
    smartcard_select.add_argument("--force", action="store_true")
    smartcard_select.add_argument("--json", action="store_true")
    smartcard_select.set_defaults(func=cmd_smartcard_select_review)
    smartcard_mobagent = smartcard_sub.add_parser(
        "mobagent-plan",
        help="build a MobAgent smart-card add/remove/list plan",
    )
    smartcard_mobagent.add_argument("--certificate-id", required=True)
    smartcard_mobagent.add_argument("--provider", default="microsoft-capi")
    smartcard_mobagent.add_argument("--action", default="add", choices=["add", "remove", "list"])
    smartcard_mobagent.add_argument("--agent-socket", default="")
    smartcard_mobagent.add_argument("--json", action="store_true")
    smartcard_mobagent.set_defaults(func=cmd_smartcard_mobagent_plan)
    smartcard_browser = smartcard_sub.add_parser(
        "ssh-browser-plan",
        help="build same-parameter SSH/SFTP browser plans for a smart-card SSH session",
    )
    smartcard_browser.add_argument("profile")
    smartcard_browser.add_argument("--certificate-id", required=True)
    smartcard_browser.add_argument("--provider", default="microsoft-capi")
    smartcard_browser.add_argument("--add-to-mobagent", action="store_true")
    smartcard_browser.add_argument("--json", action="store_true")
    smartcard_browser.set_defaults(func=cmd_smartcard_ssh_browser_plan)
    smartcard_evidence_bundle = smartcard_sub.add_parser(
        "evidence-bundle",
        help="assemble MobaXterm 26.4 smart-card management and SSH-browser release evidence",
    )
    smartcard_evidence_bundle.add_argument("profile")
    smartcard_evidence_bundle.add_argument("--certificate-id", required=True)
    smartcard_evidence_bundle.add_argument(
        "--certificate",
        action="append",
        required=True,
        default=[],
        help="available certificate as id|label|provider|fingerprint_sha256|public_key",
    )
    smartcard_evidence_bundle.add_argument("--provider", default="microsoft-capi")
    smartcard_evidence_bundle.add_argument("--out-dir", required=True, type=Path)
    smartcard_evidence_bundle.add_argument("--management-evidence", required=True, type=Path)
    smartcard_evidence_bundle.add_argument("--selection-evidence", required=True, type=Path)
    smartcard_evidence_bundle.add_argument("--mobagent-evidence", required=True, type=Path)
    smartcard_evidence_bundle.add_argument("--browser-evidence", required=True, type=Path)
    smartcard_evidence_bundle.add_argument("--release-target", default="local-bundle")
    smartcard_evidence_bundle.add_argument("--add-to-mobagent", action="store_true")
    smartcard_evidence_bundle.add_argument("--management-command", default="")
    smartcard_evidence_bundle.add_argument("--selection-command", default="")
    smartcard_evidence_bundle.add_argument("--mobagent-command", default="")
    smartcard_evidence_bundle.add_argument("--browser-command", default="")
    smartcard_evidence_bundle.add_argument("--gui-visible", action="store_true")
    smartcard_evidence_bundle.add_argument("--add-remove-controls", action="store_true")
    smartcard_evidence_bundle.add_argument("--openssh-public-key-visible", action="store_true")
    smartcard_evidence_bundle.add_argument("--expert-setting-visible", action="store_true")
    smartcard_evidence_bundle.add_argument("--certificate-selected", action="store_true")
    smartcard_evidence_bundle.add_argument("--profile-saved", action="store_true")
    smartcard_evidence_bundle.add_argument("--global-add-setting", action="store_true")
    smartcard_evidence_bundle.add_argument("--agent-loaded-certificate", action="store_true")
    smartcard_evidence_bundle.add_argument("--same-parameters-sftp", action="store_true")
    smartcard_evidence_bundle.add_argument("--multiplex-mode", action="store_true")
    smartcard_evidence_bundle.add_argument("--real-connected-session", action="store_true")
    smartcard_evidence_bundle.add_argument("--sftp-browser-open", action="store_true")
    smartcard_evidence_bundle.add_argument("--json", action="store_true")
    smartcard_evidence_bundle.set_defaults(func=cmd_smartcard_evidence_bundle)
    smartcard_evidence = smartcard_sub.add_parser(
        "evidence-verify",
        help="verify MobaXterm 26.4 smart-card management and SSH-browser evidence",
    )
    smartcard_evidence.add_argument("--evidence", required=True, type=Path)
    smartcard_evidence.add_argument("--assets-dir", type=Path)
    smartcard_evidence.add_argument("--json", action="store_true")
    smartcard_evidence.set_defaults(func=cmd_smartcard_evidence_verify)

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

    mobapt = sub.add_parser("mobapt", help="inspect Unix tools and host package-manager adapters")
    mobapt_sub = mobapt.add_subparsers(required=True)
    mobapt_status = mobapt_sub.add_parser("status", help="show MobApt-style Unix tool and package-manager status")
    mobapt_status.add_argument("--json", action="store_true")
    mobapt_status.set_defaults(func=cmd_mobapt_status)
    mobapt_runtime = mobapt_sub.add_parser("runtime-status", help="inspect ROW-owned MobApt runtime/cache roots")
    mobapt_runtime.add_argument("--root", action="append", type=Path, help="MobApt runtime/cache root to scan")
    mobapt_runtime.add_argument("--json", action="store_true")
    mobapt_runtime.set_defaults(func=cmd_mobapt_runtime_status)
    mobapt_bundle = mobapt_sub.add_parser("bundle-runtime", help="assemble a ROW-owned MobApt runtime/cache bundle")
    mobapt_bundle.add_argument("--out", required=True, type=Path, help="output runtime/cache bundle directory")
    mobapt_bundle.add_argument("--tool", action="append", default=[], help="Unix tool name to include")
    mobapt_bundle.add_argument("--tool-source", action="append", default=[], help="tool=path source binary to copy")
    mobapt_bundle.add_argument("--package", action="append", default=[], help="offline package spec as name=version")
    mobapt_bundle.add_argument("--package-source", action="append", default=[], help="name=version=path or name=path archive")
    mobapt_bundle.add_argument("--runtime-name", default="ROW Unix Runtime")
    mobapt_bundle.add_argument("--version", default="1.0.0")
    mobapt_bundle.add_argument("--release-target", default="local-bundle")
    mobapt_bundle.add_argument("--terminal-probe-command")
    mobapt_bundle.add_argument("--copy-host-tools", action="store_true", help="copy missing tools from PATH when found")
    mobapt_bundle.add_argument("--allow-shims", action="store_true", help="allow synthetic tool/package files for rehearsal")
    mobapt_bundle.add_argument("--json", action="store_true")
    mobapt_bundle.set_defaults(func=cmd_mobapt_bundle_runtime)
    mobapt_cache = mobapt_sub.add_parser("cache-verify", help="verify MobApt offline package cache release evidence")
    mobapt_cache.add_argument("--evidence", required=True, type=Path)
    mobapt_cache.add_argument("--assets-dir", type=Path)
    mobapt_cache.add_argument("--json", action="store_true")
    mobapt_cache.set_defaults(func=cmd_mobapt_cache_verify)
    mobapt_search = mobapt_sub.add_parser("search", help="plan or run a package search")
    mobapt_search.add_argument("package")
    mobapt_search.add_argument("--manager", help="package manager key such as apt, brew, winget, scoop or choco")
    mobapt_search.add_argument("--execute", action="store_true", help="run the external package manager")
    mobapt_search.add_argument("--timeout", type=float, default=120.0)
    mobapt_search.add_argument("--json", action="store_true")
    mobapt_search.set_defaults(func=cmd_mobapt_package, action="search")
    mobapt_install = mobapt_sub.add_parser("install", help="plan or run a package install")
    mobapt_install.add_argument("package")
    mobapt_install.add_argument("--manager", help="package manager key such as apt, brew, winget, scoop or choco")
    mobapt_install.add_argument("--execute", action="store_true", help="run the external package manager")
    mobapt_install.add_argument("--timeout", type=float, default=120.0)
    mobapt_install.add_argument("--json", action="store_true")
    mobapt_install.set_defaults(func=cmd_mobapt_package, action="install")
    mobapt_update = mobapt_sub.add_parser("update", help="plan or run package metadata/update refresh")
    mobapt_update.add_argument("--manager", help="package manager key such as apt, brew, winget, scoop or choco")
    mobapt_update.add_argument("--execute", action="store_true", help="run the external package manager")
    mobapt_update.add_argument("--timeout", type=float, default=120.0)
    mobapt_update.add_argument("--json", action="store_true")
    mobapt_update.set_defaults(func=cmd_mobapt_package, action="update", package=None)

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
    servers_bundle.add_argument("service", choices=list(SERVER_DEFAULT_PORTS))
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
    servers_config.add_argument("service", choices=list(SERVER_DEFAULT_PORTS))
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
    servers_start.add_argument("service", choices=list(SERVER_DEFAULT_PORTS))
    servers_start.add_argument("--host", default="127.0.0.1")
    servers_start.add_argument("--port", type=int)
    servers_start.add_argument("--root", type=Path)
    servers_start.add_argument("--allow-public-bind", action="store_true")
    servers_start.add_argument("--dry-run", action="store_true")
    servers_start.add_argument("--json", action="store_true")
    servers_start.set_defaults(func=cmd_servers_start)
    servers_stop = servers_sub.add_parser("stop", help="stop a managed local server")
    servers_stop.add_argument("service", choices=list(SERVER_DEFAULT_PORTS))
    servers_stop.add_argument("--json", action="store_true")
    servers_stop.set_defaults(func=cmd_servers_stop)

    x11 = sub.add_parser("x11", help="manage local X server helper")
    x11_sub = x11.add_subparsers(required=True)
    x11_start = x11_sub.add_parser("start", help="start or inspect a local X server helper")
    x11_start.add_argument("--display", default=":0")
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
    assert_profile_launch_allowed(profile, surface="launcher")
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
        status = result.protocol_status.get(protocol, {})
        summary = str(status.get("summary", _doctor_executable_summary(candidates)))
        print(f"  {protocol:<8} {summary}")
    return 0


def _doctor_executable_summary(candidates: dict[str, bool]) -> str:
    available = [name for name, ok in candidates.items() if ok]
    return ", ".join(available) if available else "missing"


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
        tier = str(item["release_tier"]).replace("-", " ")
        channel = str(item.get("github_release_channel", "unspecified")).replace("-", " ")
        print(
            f"  {item['platform']:<{platform_width}} {item['cpu_arch']:<{arch_width}} "
            f"{item['bits']:>2}-bit {tier} ({channel})"
        )

    print("\nLegacy Windows targets:")
    version_width = max(len(item["version"]) for item in legacy_targets)
    for item in legacy_targets:
        remote_detail = str(item["remote_target_tier"])
        if item.get("remote_target_coverage_percent") is not None:
            architectures = "/".join(str(arch) for arch in item.get("architectures", []))
            security = str(item.get("security_profile", ""))
            remote_detail = (
                f"{remote_detail} "
                f"({float(item['remote_target_coverage_percent']):.1f}% {architectures} {security})"
            )
        print(
            f"  {item['version']:<{version_width}} host {item['host_tier']}, "
            f"remote target {remote_detail}"
        )

    platform = coverage_report()["platform_verified_readiness"]
    protected_goal = platform.get("protected_goal_parity", {})
    if protected_goal:
        print("\nEvidence-backed protected readiness:")
        print(
            f"  Protected platform goal       : {float(protected_goal.get('current_percent', 0.0)):.1f}% "
            f"({float(protected_goal.get('gap_percent', 0.0)):.1f}% gap; "
            f"{int(protected_goal.get('accepted_target_count', 0))}/"
            f"{int(protected_goal.get('target_count', 0))} accepted; "
            f"{protected_goal.get('status', 'unknown')})"
        )
        asset_provenance_complete = (
            protected_goal.get("release_asset_provenance_complete") is True
        )
        asset_provenance_state = (
            "complete" if asset_provenance_complete else "not checked by static platform catalog"
        )
        print(f"  Release asset provenance      : {asset_provenance_state}")
        missing_targets = [
            str(target) for target in protected_goal.get("missing_targets", [])
        ]
        if missing_targets:
            print(f"  Missing accepted evidence     : {', '.join(missing_targets)}")
        print(
            "  Static platform catalog       : not native-host/readiness proof "
            "for Linux i386/armhf or Windows XP"
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
        adapter = report["adapter_ready_coverage"]
        parity = report["production_parity_coverage"]
        platform = report["platform_verified_readiness"]
        mapping_overall = mapping["overall"]
        adapter_overall = adapter["overall"]
        parity_overall = parity["overall"]
        platform_overall = platform["overall"]
        print(f"Feature-family mapping target : {mapping['target_percent']:.0f}%")
        print(f"Feature-family mapping current: {mapping_overall['current_percent']:.1f}% ({mapping_overall['feature_count']} families)")
        print(f"Adapter-ready target          : {adapter['target_percent']:.0f}%")
        print(
            f"Adapter-ready current         : {adapter_overall['current_percent']:.1f}% "
            f"({adapter_overall['gap_percent']:.1f}% gap)"
        )
        print(f"Workflow parity target        : {parity['target_percent']:.0f}%")
        print(
            f"Workflow parity current       : {parity_overall['current_percent']:.1f}% "
            f"({parity_overall['gap_percent']:.1f}% gap)"
        )
        print(
            f"Platform verified readiness   : {platform_overall['current_percent']:.1f}% "
            f"({platform_overall['gap_percent']:.1f}% gap across "
            f"{platform_overall['target_count']} verified targets; "
            f"{platform_overall.get('extended_target_count', 0)} extended rows)"
        )
        denominator = platform.get("denominator", {})
        if denominator:
            print(
                "Verified denominator        : "
                f"{int(denominator.get('included_target_count', 0))} included, "
                f"{int(denominator.get('excluded_target_count', 0))} extended excluded; "
                f"protected goal source={denominator.get('protected_goal_score_source', 'unknown')}"
            )
        protected_goal = platform.get("protected_goal_parity", {})
        if protected_goal:
            missing_targets = [
                str(target) for target in protected_goal.get("missing_targets", [])
            ]
            print(
                f"Protected platform goal       : {float(protected_goal.get('current_percent', 0.0)):.1f}% "
                f"({float(protected_goal.get('gap_percent', 0.0)):.1f}% gap; "
                f"{int(protected_goal.get('accepted_target_count', 0))}/"
                f"{int(protected_goal.get('target_count', 0))} accepted; "
                f"{protected_goal.get('status', 'unknown')})"
            )
            asset_provenance_complete = (
                protected_goal.get("release_asset_provenance_complete") is True
            )
            asset_provenance_state = (
                "complete" if asset_provenance_complete else "not checked by static report"
            )
            print(f"  Release asset provenance : {asset_provenance_state}")
            asset_command = str(protected_goal.get("release_asset_provenance_command", "")).strip()
            if not asset_provenance_complete and asset_command:
                print(f"  Asset provenance gate    : {asset_command}")
            if missing_targets:
                print(f"  Missing protected evidence  : {', '.join(missing_targets)}")
        evidence = report["evidence_summary"]
        print(
            f"Evidence records              : {evidence['features_with_evidence']}/"
            f"{evidence['total_features']} feature families"
        )
        print(f"Parity contract               : {report['workflow_parity_contract']['label']}")
        print("\nProduct coverage:")
        adapter_rows = {row["product"]: row for row in adapter["products"]}
        parity_rows = {row["product"]: row for row in parity["products"]}
        product_width = max(len(row["product"]) for row in mapping["products"])
        for row in mapping["products"]:
            adapter_row = adapter_rows[row["product"]]
            parity_row = parity_rows[row["product"]]
            print(
                f"  {row['product']:<{product_width}} mapping {row['current_percent']:>5.1f}%, "
                f"adapter {adapter_row['current_percent']:>5.1f}%, "
                f"workflow parity {parity_row['current_percent']:>5.1f}% "
                f"({row['feature_count']} families)"
            )
        if platform["targets"]:
            print("\nPlatform readiness:")
            target_width = max(len(row["target"]) for row in platform["targets"])
            for row in platform["targets"]:
                remote = ""
                if row.get("remote_target_coverage_percent") is not None:
                    architectures = "/".join(str(arch) for arch in row.get("legacy_architectures", []))
                    security = str(row.get("security_profile", ""))
                    remote = (
                        f"; remote target {float(row['remote_target_coverage_percent']):.1f}% "
                        f"{architectures} {security}"
                    )
                missing = ""
                missing_targets = row.get("accepted_evidence_missing_targets", [])
                if missing_targets:
                    missing = f"; missing evidence {', '.join(str(target) for target in missing_targets)}"
                print(
                    f"  {row['target']:<{target_width}} {row['current_percent']:>5.1f}% "
                    f"{row['status']} ({row['channel']}){remote}{missing}"
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


def cmd_customizer_build(args: argparse.Namespace) -> int:
    welcome_message = None
    if args.welcome_file:
        welcome_message = args.welcome_file.read_text(encoding="utf-8")
    elif args.welcome_message:
        welcome_message = args.welcome_message
    plan = build_moba_professional_customizer_plan(
        args.out,
        brand_name=args.brand_name,
        organization=args.organization,
        welcome_message=welcome_message,
        logo_path=args.logo,
        settings_path=args.settings,
        profiles_path=args.profiles,
        policy_path=args.policy,
        lock_settings=args.lock_setting,
        force=args.force,
    )
    bundle = write_moba_professional_customizer_bundle(plan)
    if args.json:
        print(json.dumps(bundle.to_dict(), indent=2, sort_keys=True))
        return 0
    print(f"customizer bundle: {bundle.root}")
    print(f"brand: {bundle.manifest['brand_name']}")
    print(f"profiles: {bundle.manifest['profile_count']}")
    print("files:")
    for path in bundle.files:
        print(f"  {path}")
    return 0


def cmd_customizer_deployment_plan(args: argparse.Namespace) -> int:
    plan = build_professional_deployment_plan(
        brand_name=args.brand_name,
        organization=args.organization,
        version=args.version,
        logo_path=args.logo,
        policy_path=args.policy,
        lock_settings=args.lock_setting,
        update_url=args.update_url,
        update_public_key=args.update_public_key,
        update_channel=args.update_channel,
        update_interval_hours=args.update_interval_hours,
        rollout_ring=args.rollout_ring,
        enforcement_surfaces=args.surface or None,
    )
    if args.json:
        print(json.dumps(plan.to_dict(), indent=2, sort_keys=True))
        return 0
    installer = plan.installer_branding
    policy = plan.policy_locks
    channel = plan.update_channel
    print(f"deployment plan: {plan.schema}")
    print(f"brand: {installer.brand_name}")
    print(f"publisher: {installer.publisher}")
    print("installer artifacts:")
    for target, name in installer.artifact_names.items():
        print(f"  {target}: {name}")
    print("locked settings:")
    for item in policy.locked_settings:
        print(f"  {item['key']}={item['value']}")
    print(f"enforcement surfaces: {', '.join(policy.enforcement_surfaces)}")
    print(f"update channel: {channel.channel} {channel.update_url}")
    print(f"signature required: {'yes' if channel.require_signature else 'no'}")
    for requirement in plan.evidence_requirements:
        print(f"evidence: {requirement}")
    return 0


def cmd_customizer_evidence_bundle(args: argparse.Namespace) -> int:
    deployment = build_professional_deployment_plan(
        brand_name=args.brand_name,
        organization=args.organization,
        version=args.version,
        logo_path=args.logo,
        policy_path=args.policy,
        lock_settings=args.lock_setting,
        update_url=args.update_url,
        update_public_key=args.update_public_key,
        update_channel=args.update_channel,
        update_interval_hours=args.update_interval_hours,
        rollout_ring=args.rollout_ring,
    )
    passed_surfaces = set(args.surface_passed)
    if args.all_policy_surfaces_passed:
        passed_surfaces.update(REQUIRED_POLICY_SURFACES)
    surfaces = {surface: surface in passed_surfaces for surface in REQUIRED_POLICY_SURFACES}
    plan = build_professional_deployment_evidence_bundle_plan(
        deployment,
        out_dir=args.out_dir,
        bundle_manifest_evidence=args.bundle_manifest_evidence,
        installer_evidence=args.installer_evidence,
        policy_evidence=args.policy_evidence,
        update_evidence=args.update_evidence,
        update_manifest=args.update_manifest,
        bundle_manifest_sha256=args.bundle_manifest_sha256,
        update_manifest_assets_dir=args.update_assets_dir,
        release_target=args.release_target,
        bundle_command=args.bundle_command,
        installer_command=args.installer_command,
        policy_command=args.policy_command,
        update_command=args.update_command,
        surfaces=surfaces,
        sha256s_present=args.sha256s_present,
        windows_exe_rebranded=args.windows_exe_rebranded,
        windows_msi_rebranded=args.windows_msi_rebranded,
        product_name_matches_brand=args.product_name_matches_brand,
        logo_applied=args.logo_applied,
        https_update_url=args.https_update_url,
        signature_verified=args.signature_verified,
        organization_channel=args.organization_channel,
    )
    result = write_professional_deployment_evidence_bundle(plan)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"deployment evidence bundle: {result.evidence_path}")
        print(f"passed: {'yes' if result.validation.passed else 'no'}")
        print("files:")
        for path in result.files:
            print(f"  {path}")
        for warning in result.validation.warnings:
            print(f"warning: {warning}")
        for error in result.validation.errors:
            print(f"error: {error}", file=sys.stderr)
    return 0 if result.validation.passed else 1


def cmd_customizer_evidence_verify(args: argparse.Namespace) -> int:
    result = validate_professional_deployment_evidence(args.evidence, assets_dir=args.assets_dir)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"evidence: {result.evidence_path}")
        print(f"assets: {result.assets_dir}")
        print(f"passed: {'yes' if result.passed else 'no'}")
        if result.summary:
            print(f"schema: {result.summary.get('schema', '')}")
            print(f"release target: {result.summary.get('release_target', '')}")
            print(f"brand: {result.summary.get('brand_name', '')}")
            print(f"policy surfaces: {result.summary.get('surface_count', 0)}")
        for warning in result.warnings:
            print(f"warning: {warning}")
        for error in result.errors:
            print(f"error: {error}", file=sys.stderr)
    return 0 if result.passed else 1


def cmd_customizer_update_verify(args: argparse.Namespace) -> int:
    result = validate_professional_update_manifest(
        args.manifest,
        public_key=args.public_key,
        expected_channel=args.channel,
        expected_organization=args.organization,
        assets_dir=args.assets_dir,
    )
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"update manifest: {result.manifest_path}")
        print(f"assets: {result.assets_dir}")
        print(f"passed: {'yes' if result.passed else 'no'}")
        if result.summary:
            print(f"schema: {result.summary.get('schema', '')}")
            print(f"channel: {result.summary.get('channel', '')}")
            print(f"organization: {result.summary.get('organization', '')}")
            print(f"version: {result.summary.get('version', '')}")
            print(f"artifacts: {result.summary.get('artifact_count', 0)}")
            print(f"signature: {result.summary.get('signature_algorithm', '')}")
        for warning in result.warnings:
            print(f"warning: {warning}")
        for error in result.errors:
            print(f"error: {error}", file=sys.stderr)
    return 0 if result.passed else 1


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


def cmd_macro_record(args: argparse.Namespace) -> int:
    if args.text is not None:
        body = args.text
    elif args.text_file is not None:
        body = args.text_file.read_text(encoding="utf-8")
    else:
        body = sys.stdin.read()
    recording = record_typed_macro(
        args.name,
        body,
        description=args.description,
        tags=args.tag,
        delay_ms=args.delay_ms,
    )
    MobaMacroStore().add(recording, replace=args.replace)
    if args.json:
        print(json.dumps(recording.to_dict(), indent=2, sort_keys=True))
        return 0
    print(f"saved macro: {recording.name}")
    print(f"events: {len(recording.events)}")
    return 0


def cmd_macro_list(args: argparse.Namespace) -> int:
    recordings = MobaMacroStore().load()
    if args.json:
        print(json.dumps([recording.to_dict() for recording in recordings], indent=2, sort_keys=True))
        return 0
    for recording in recordings:
        tags = ",".join(recording.tags)
        print(f"{recording.name:<24} events={len(recording.events):<4} {tags:<20} {recording.description}")
    return 0


def cmd_macro_show(args: argparse.Namespace) -> int:
    print(json.dumps(MobaMacroStore().get(args.name).to_dict(), indent=2, sort_keys=True))
    return 0


def cmd_macro_remove(args: argparse.Namespace) -> int:
    MobaMacroStore().remove(args.name)
    print(f"removed macro: {args.name}")
    return 0


def cmd_macro_replay(args: argparse.Namespace) -> int:
    recording = MobaMacroStore().get(args.name)
    profiles = _select_profiles(ProfileStore(), names=args.profile, group=args.group, tags=args.tag)
    plans = build_macro_replay_plans(recording, profiles)
    results = run_macro_replay(plans, dry_run=args.dry_run, timeout=args.timeout)
    if args.json:
        print(
            json.dumps(
                {
                    "macro": recording.to_dict(),
                    "plans": [plan.to_dict() for plan in plans],
                    "results": [result.to_dict() for result in results],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        for plan, result in zip(plans, results, strict=True):
            print(" ".join(plan.command))
            print(f"profile: {plan.profile_name} events={plan.event_count} dry_run={'yes' if result.dry_run else 'no'}")
            for note in plan.notes:
                print(f"note: {note}")
    return 0 if all(result.ok for result in results) else 1


def cmd_macro_capture_plan(args: argparse.Namespace) -> int:
    recording = MobaMacroStore().get(args.name)
    plan = build_macro_gui_capture_plan(recording)
    if args.json:
        print(json.dumps(plan.to_dict(), indent=2, sort_keys=True))
        return 0
    print(f"macro: {plan.macro_name}")
    print(f"events: {plan.event_count}")
    print(f"input sha256: {plan.input_sha256}")
    print(f"total delay ms: {plan.total_delay_ms}")
    print(f"controls: {', '.join(plan.capture_controls)}")
    print(f"cancel supported: {'yes' if plan.cancel_supported else 'no'}")
    for note in plan.notes:
        print(f"note: {note}")
    return 0


def cmd_macro_live_plan(args: argparse.Namespace) -> int:
    recording = MobaMacroStore().get(args.name)
    profiles = _select_profiles(ProfileStore(), names=args.profile, group=args.group, tags=args.tag)
    review = review_macro_live_replay(
        recording,
        profiles,
        connected_profiles=args.connected_profile,
        force=args.force,
    )
    plans = build_macro_live_replay_plans(recording, profiles, pane_ids=_parse_options(args.pane_id))
    if args.json:
        print(
            json.dumps(
                {
                    "macro": recording.to_dict(),
                    "review": review.to_dict(),
                    "plans": [plan.to_dict() for plan in plans],
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(f"macro: {recording.name}")
        print(f"allowed: {'yes' if review.allowed else 'no'}")
        print(f"confirmation required: {'yes' if review.confirmation_required else 'no'}")
        print(f"cancel supported: {'yes' if review.cancel_supported else 'no'}")
        if review.prompt:
            print(f"prompt: {review.prompt}")
        if review.disconnected_profiles:
            print(f"disconnected: {', '.join(review.disconnected_profiles)}")
        for plan in plans:
            print(f"profile: {plan.profile_name} pane={plan.pane_id} events={plan.event_count}")
            print(" ".join(plan.command))
            for step in plan.steps:
                print(
                    f"  event {step.index}: delay={step.delay_ms}ms "
                    f"at={step.scheduled_after_ms}ms enter={'yes' if step.enter else 'no'}"
                )
            for note in plan.notes:
                print(f"note: {note}")
    return 0 if review.allowed else 1


def cmd_macro_evidence_bundle(args: argparse.Namespace) -> int:
    recording = MobaMacroStore().get(args.name)
    profiles = _select_profiles(ProfileStore(), names=args.profile, group=args.group, tags=args.tag)
    plan = build_macro_live_evidence_bundle_plan(
        recording,
        profiles,
        out_dir=args.out_dir,
        capture_evidence=args.capture_evidence,
        review_evidence=args.review_evidence,
        replay_evidence=_parse_key_path_options(args.replay_evidence, "replay evidence"),
        release_target=args.release_target,
        connected_profiles=args.connected_profile,
        pane_ids=_parse_options(args.pane_id),
        capture_command=args.capture_command,
        review_command=args.review_command,
        replay_commands=_parse_options(args.replay_command),
        gui_record_button=args.gui_record_button,
        gui_stop_button=args.gui_stop_button,
        gui_cancel_button=args.gui_cancel_button,
        per_event_timing_captured=args.per_event_timing_captured,
        confirmation_prompt=args.confirmation_prompt,
        cancel_prompt_verified=args.cancel_prompt_verified,
        conflict_checked=args.conflict_checked,
        real_connected_session=args.real_connected_session,
        live_terminal_pane=args.live_terminal_pane,
        per_keystroke_timing_replay=args.per_keystroke_timing_replay,
    )
    result = write_macro_live_evidence_bundle(plan)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"macro live evidence bundle: {'passed' if result.validation.passed else 'failed'}")
        print(f"evidence: {result.evidence_path}")
        for note in result.notes:
            print(f"note: {note}")
        for error in result.validation.errors:
            print(f"error: {error}")
    return 0 if result.validation.passed else 1


def cmd_macro_evidence_verify(args: argparse.Namespace) -> int:
    result = validate_macro_live_replay_evidence(args.evidence, assets_dir=args.assets_dir)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"evidence: {result.evidence_path}")
        print(f"assets: {result.assets_dir}")
        print(f"passed: {'yes' if result.passed else 'no'}")
        if result.summary:
            print(f"schema: {result.summary.get('schema', '')}")
            print(f"release target: {result.summary.get('release_target', '')}")
            print(f"macro: {result.summary.get('macro', '')}")
            print(f"replay sessions: {result.summary.get('replay_sessions', 0)}")
        for warning in result.warnings:
            print(f"warning: {warning}")
        for error in result.errors:
            print(f"error: {error}", file=sys.stderr)
    return 0 if result.passed else 1


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


def cmd_smartcard_inventory_plan(args: argparse.Namespace) -> int:
    plan = build_smartcard_inventory_plan(args.provider)
    if args.json:
        print(json.dumps(plan.to_dict(), indent=2, sort_keys=True))
        return 0
    print(f"provider: {plan.provider}")
    print(f"platform: {plan.platform}")
    print("commands:")
    for command in plan.commands:
        print(" ".join(command))
    print(f"actions: {', '.join(plan.management_actions)}")
    for note in plan.notes:
        print(f"note: {note}")
    return 0


def cmd_smartcard_select_review(args: argparse.Namespace) -> int:
    profile = ProfileStore().get(args.profile)
    certificates = _parse_smartcard_certificates(
        args.certificate,
        provider=args.provider,
        default_certificate_id=args.certificate_id,
    )
    review = review_smartcard_certificate_selection(
        profile,
        args.certificate_id,
        certificates,
        add_to_mobagent=args.add_to_mobagent,
        force=args.force,
    )
    if args.json:
        print(json.dumps(review.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"profile: {review.profile_name}")
        print(f"certificate: {review.certificate_id}")
        print(f"allowed: {'yes' if review.allowed else 'no'}")
        print(f"confirmation required: {'yes' if review.confirmation_required else 'no'}")
        print(f"multiplex required: {'yes' if review.ssh_browser_multiplex_required else 'no'}")
        if review.prompt:
            print(f"prompt: {review.prompt}")
        for key, value in sorted(review.profile_options.items()):
            print(f"option: {key}={value}")
        for note in review.notes:
            print(f"note: {note}")
    return 0 if review.allowed else 1


def cmd_smartcard_mobagent_plan(args: argparse.Namespace) -> int:
    plan = build_mobagent_smartcard_plan(
        args.certificate_id,
        provider=args.provider,
        action=args.action,
        agent_socket=args.agent_socket,
    )
    if args.json:
        print(json.dumps(plan.to_dict(), indent=2, sort_keys=True))
        return 0
    print(f"action: {plan.action}")
    print(f"certificate: {plan.certificate_id}")
    print(f"provider: {plan.provider}")
    print(" ".join(plan.command))
    for note in plan.notes:
        print(f"note: {note}")
    return 0


def cmd_smartcard_ssh_browser_plan(args: argparse.Namespace) -> int:
    profile = ProfileStore().get(args.profile)
    plan = build_smartcard_ssh_browser_plan(
        profile,
        args.certificate_id,
        provider=args.provider,
        add_to_mobagent=args.add_to_mobagent,
    )
    if args.json:
        print(json.dumps(plan.to_dict(), indent=2, sort_keys=True))
        return 0
    print(f"profile: {plan.profile_name}")
    print(f"certificate: {plan.certificate_id}")
    print(f"provider: {plan.provider}")
    print(f"same parameters: {'yes' if plan.ssh_browser_same_parameters else 'no'}")
    print(f"multiplex required: {'yes' if plan.multiplex_mode_required else 'no'}")
    print("terminal:")
    print(" ".join(plan.terminal_command))
    print("sftp:")
    print(" ".join(plan.sftp_command))
    for note in plan.notes:
        print(f"note: {note}")
    return 0


def cmd_smartcard_evidence_bundle(args: argparse.Namespace) -> int:
    profile = ProfileStore().get(args.profile)
    certificates = _parse_smartcard_certificates(
        args.certificate,
        provider=args.provider,
        default_certificate_id=args.certificate_id,
    )
    certificate = _select_smartcard_certificate(certificates, args.certificate_id)
    plan = build_smartcard_release_evidence_bundle_plan(
        profile,
        certificate,
        out_dir=args.out_dir,
        management_evidence=args.management_evidence,
        selection_evidence=args.selection_evidence,
        mobagent_evidence=args.mobagent_evidence,
        browser_evidence=args.browser_evidence,
        release_target=args.release_target,
        add_to_mobagent=args.add_to_mobagent,
        management_command=args.management_command,
        selection_command=args.selection_command,
        mobagent_command=args.mobagent_command,
        browser_command=args.browser_command,
        gui_visible=args.gui_visible,
        add_remove_controls=args.add_remove_controls,
        openssh_public_key_visible=args.openssh_public_key_visible,
        expert_setting_visible=args.expert_setting_visible,
        certificate_selected=args.certificate_selected,
        profile_saved=args.profile_saved,
        global_add_setting=args.global_add_setting,
        agent_loaded_certificate=args.agent_loaded_certificate,
        same_parameters_sftp=args.same_parameters_sftp,
        multiplex_mode=args.multiplex_mode,
        real_connected_session=args.real_connected_session,
        sftp_browser_open=args.sftp_browser_open,
    )
    result = write_smartcard_release_evidence_bundle(plan)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"smart-card release evidence bundle: {'passed' if result.validation.passed else 'failed'}")
        print(f"evidence: {result.evidence_path}")
        for note in result.notes:
            print(f"note: {note}")
        for error in result.validation.errors:
            print(f"error: {error}")
    return 0 if result.validation.passed else 1


def cmd_smartcard_evidence_verify(args: argparse.Namespace) -> int:
    result = validate_smartcard_release_evidence(args.evidence, assets_dir=args.assets_dir)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"evidence: {result.evidence_path}")
        print(f"assets: {result.assets_dir}")
        print(f"passed: {'yes' if result.passed else 'no'}")
        if result.summary:
            print(f"schema: {result.summary.get('schema', '')}")
            print(f"release target: {result.summary.get('release_target', '')}")
            print(f"certificate: {result.summary.get('certificate_id', '')}")
            print(f"provider: {result.summary.get('provider', '')}")
        for warning in result.warnings:
            print(f"warning: {warning}")
        for error in result.errors:
            print(f"error: {error}", file=sys.stderr)
    return 0 if result.passed else 1


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
    text = args.text if args.text is not None else args.text_file.read_text(encoding=args.encoding)
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


def cmd_mobapt_status(args: argparse.Namespace) -> int:
    status = build_mobapt_environment_status()
    if args.json:
        print(json.dumps(status.to_dict(), indent=2, sort_keys=True))
        return 0
    print(f"system: {status.system}")
    print(f"adapter mode: {'yes' if status.adapter_mode else 'no'}")
    print(f"embedded runtime: {'yes' if status.embedded_runtime_available else 'no'}")
    print("package managers:")
    for manager in status.package_managers:
        marker = "available" if manager.available else "missing"
        print(f"  {manager.key:<10} {marker:<9} {manager.executable}")
    print("unix tools:")
    for tool in status.base_tools:
        marker = "available" if tool.available else "missing"
        print(f"  {tool.name:<10} {marker:<9} {tool.executable}")
    for note in status.notes:
        print(f"note: {note}")
    return 0


def cmd_mobapt_runtime_status(args: argparse.Namespace) -> int:
    status = build_mobapt_runtime_status(roots=args.root)
    if args.json:
        print(json.dumps(status.to_dict(), indent=2, sort_keys=True))
        return 0
    print(f"embedded runtime: {'yes' if status.embedded_runtime_available else 'no'}")
    print("roots:")
    for root in status.roots:
        print(f"  {root}")
    print("runtime candidates:")
    if status.candidates:
        for candidate in status.candidates:
            marker = "available" if candidate.available else "invalid"
            print(
                f"  {candidate.name or 'unknown':<24} {marker:<9} "
                f"tools={len(candidate.tools)} packages={len(candidate.packages)}"
            )
    else:
        print("  none")
    for note in status.notes:
        print(f"note: {note}")
    return 0


def cmd_mobapt_bundle_runtime(args: argparse.Namespace) -> int:
    tool_sources = _parse_key_path_options(args.tool_source, "tool source")
    package_sources = _parse_package_source_options(args.package_source)
    plan = build_mobapt_runtime_bundle_plan(
        args.out,
        tools=tuple(args.tool) if args.tool else None,
        packages=tuple(args.package),
        runtime_name=args.runtime_name,
        version=args.version,
        release_target=args.release_target,
        terminal_probe_command=args.terminal_probe_command,
        allow_shims=args.allow_shims,
        copy_host_tools=args.copy_host_tools,
        tool_sources=tool_sources,
        package_sources=package_sources,
    )
    result = write_mobapt_runtime_bundle(plan)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"mobapt runtime bundle: {'passed' if result.evidence_validation.passed else 'failed'}")
        print(f"root: {result.root}")
        print(f"manifest: {result.manifest_path}")
        print(f"package index: {result.package_index_path}")
        print(f"evidence: {result.evidence_path}")
        print(f"tools: {result.tool_count}")
        print(f"packages: {result.package_count}")
        if result.shimmed_tools:
            print(f"shimmed tools: {', '.join(result.shimmed_tools)}")
        if result.synthetic_packages:
            print(f"synthetic packages: {', '.join(result.synthetic_packages)}")
        for error in result.evidence_validation.errors:
            print(f"error: {error}")
        for note in result.notes:
            print(f"note: {note}")
    return 0 if result.evidence_validation.passed else 1


def cmd_mobapt_cache_verify(args: argparse.Namespace) -> int:
    result = validate_mobapt_cache_evidence(args.evidence, assets_dir=args.assets_dir)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        print(f"mobapt cache evidence: {'passed' if result.passed else 'failed'}")
        print(f"evidence: {result.evidence_path}")
        print(f"assets: {result.assets_dir}")
        for error in result.errors:
            print(f"error: {error}")
        for warning in result.warnings:
            print(f"warning: {warning}")
    return 0 if result.passed else 1


def cmd_mobapt_package(args: argparse.Namespace) -> int:
    plan = build_mobapt_package_plan(
        args.action,
        getattr(args, "package", None),
        manager=args.manager,
    )
    result = run_mobapt_package_plan(plan, execute=args.execute, timeout_seconds=args.timeout)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    else:
        print(plan.printable())
        print(f"executed: {'yes' if result.executed else 'no'}")
        print(f"status: {'ok' if result.ok else 'failed'} returncode={result.returncode}")
        for note in result.notes:
            print(f"note: {note}")
        if result.stdout:
            print(result.stdout.rstrip())
        if result.stderr:
            print(result.stderr.rstrip(), file=sys.stderr)
    return 0 if result.ok else 1


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
    )
    if args.json:
        print(json.dumps(plan.to_dict(), indent=2, sort_keys=True))
        return 0
    print(f"service: {plan.service}")
    print(f"bind: {plan.host}:{plan.port}")
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


def cmd_servers_stop(args: argparse.Namespace) -> int:
    record = stop_moba_server(args.service)
    if args.json:
        print(json.dumps(record.to_dict(), indent=2, sort_keys=True))
        return 0
    print(f"lifecycle: {record.state} pid={record.pid or 'none'} state={record.state_path}")
    return 0


def cmd_x11_start(args: argparse.Namespace) -> int:
    managed_plan = build_moba_x_server_plan(display=args.display)
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
    frozen_gui_result = _run_frozen_windows_gui_launcher()
    if frozen_gui_result is not None:
        return frozen_gui_result

    from .gui import main as gui_main

    return int(gui_main())


def _run_frozen_windows_gui_launcher() -> int | None:
    if os.name != "nt" or not getattr(sys, "frozen", False):
        return None
    gui_launcher = Path(sys.executable).with_name("row-gui.exe")
    if not gui_launcher.exists():
        return None
    completed = subprocess.run([str(gui_launcher)], check=False)
    return int(completed.returncode)


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


def _parse_key_path_options(items: list[str], label: str) -> dict[str, Path]:
    paths: dict[str, Path] = {}
    for item in items:
        if "=" not in item:
            raise ValueError(f"{label} must be key=path: {item}")
        key, value = item.split("=", 1)
        if not key or not value:
            raise ValueError(f"{label} must include both key and path: {item}")
        paths[key] = Path(value)
    return paths


def _parse_package_source_options(items: list[str]) -> dict[str, Path]:
    sources: dict[str, Path] = {}
    for item in items:
        parts = item.split("=", 2)
        if len(parts) == 2:
            key, path = parts
        elif len(parts) == 3:
            key = f"{parts[0]}={parts[1]}"
            path = parts[2]
        else:
            raise ValueError(f"package source must be name=path or name=version=path: {item}")
        if not key or not path:
            raise ValueError(f"package source must include both package key and path: {item}")
        sources[key] = Path(path)
    return sources


def _parse_smartcard_certificates(
    items: list[str],
    *,
    provider: str,
    default_certificate_id: str,
) -> list[MobaSmartCardCertificate]:
    if not items:
        return [
            MobaSmartCardCertificate(
                certificate_id=default_certificate_id,
                label=default_certificate_id,
                provider=provider,
                source="cli-default",
            )
        ]
    certificates: list[MobaSmartCardCertificate] = []
    for item in items:
        parts = item.split("|")
        certificate_id = parts[0] if len(parts) > 0 else ""
        label = parts[1] if len(parts) > 1 and parts[1] else certificate_id
        certificate_provider = parts[2] if len(parts) > 2 and parts[2] else provider
        fingerprint = parts[3] if len(parts) > 3 else ""
        public_key = parts[4] if len(parts) > 4 else ""
        certificates.append(
            MobaSmartCardCertificate(
                certificate_id=certificate_id,
                label=label,
                provider=certificate_provider,
                fingerprint_sha256=fingerprint,
                public_key=public_key,
                source="cli",
            )
        )
    return certificates


def _select_smartcard_certificate(
    certificates: list[MobaSmartCardCertificate],
    certificate_id: str,
) -> MobaSmartCardCertificate:
    selected_id = certificate_id
    for certificate in certificates:
        if certificate.certificate_id == selected_id:
            return certificate
    raise ValueError(f"smart-card certificate not found in --certificate inputs: {selected_id}")


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

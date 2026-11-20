"""Enterprise customizer and authenticated update staging commands."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
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
from .paths import data_dir


def add_customizer_commands(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
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

    for command, handler, description in (
        ("update-stage", cmd_customizer_update_stage, "authenticate and stage the complete signed update asset set"),
        ("update-stage-recover", cmd_customizer_update_stage_recover, "reverify an interrupted complete update stage; never install"),
    ):
        updater = customizer_sub.add_parser(command, help=description)
        updater.add_argument("--policy", required=True, type=Path)
        updater.add_argument("--stage", required=True, type=Path)
        updater.add_argument("--json", action="store_true")
        updater.set_defaults(func=handler)


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


def _customizer_authenticated_stage(args: argparse.Namespace, *, recover: bool) -> int:
    # Load the optional signature backend only for the explicit new command.
    from .update_channel import UpdateError, load_update_policy, recover_update, stage_update

    try:
        policy = load_update_policy(args.policy)
        operation = recover_update if recover else stage_update
        result = operation(policy, args.stage, current_home=data_dir())
    except UpdateError as exc:
        result = {"phase": "refused", "refusal": str(exc), "install_permitted": False}
    except (OSError, ValueError, RecursionError):
        result = {"phase": "refused", "refusal": "update-stage-input-refused", "install_permitted": False}
    if args.json:
        print(json.dumps(result, sort_keys=True))
    elif result["phase"] == "authenticated-staged":
        print(f"Authenticated update staged: {result['version']} ({result['artifact_count']} assets)")
        print("Installation is not permitted by the staging command.")
    else:
        print(f"Update staging refused: {result['refusal']}", file=sys.stderr)
    return 0 if result["phase"] == "authenticated-staged" else 1


def cmd_customizer_update_stage(args: argparse.Namespace) -> int:
    return _customizer_authenticated_stage(args, recover=False)


def cmd_customizer_update_stage_recover(args: argparse.Namespace) -> int:
    return _customizer_authenticated_stage(args, recover=True)

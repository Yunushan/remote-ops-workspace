"""Render diagnostic, platform, and feature reports for the CLI."""

from __future__ import annotations

import argparse
import json

from .doctor import run_doctor
from .features import coverage_report, feature_summary, load_feature_manifest
from .platform_targets import load_platform_targets


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
        remote_audit_command = str(
            protected_goal.get("remote_release_evidence_audit_command", "")
        ).strip()
        if remote_audit_command:
            print(f"  Published evidence audit      : {remote_audit_command}")
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
            f"Platform build contract coverage: {platform_overall['current_percent']:.1f}% "
            f"({platform_overall['gap_percent']:.1f}% gap across "
            f"{platform_overall['target_count']} included build targets; "
            f"{platform_overall.get('extended_target_count', 0)} extended rows)"
        )
        denominator = platform.get("denominator", {})
        if denominator:
            print(
                "Build contract denominator    : "
                f"{int(denominator.get('included_target_count', 0))} included, "
                f"{int(denominator.get('excluded_target_count', 0))} extended excluded; "
                f"protected goal source={denominator.get('protected_goal_score_source', 'unknown')}"
            )
        print(
            "Runtime verification          : not assessed by this catalog; "
            "production readiness requires artifact, host, trust and recovery evidence"
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
            remote_audit_command = str(
                protected_goal.get("remote_release_evidence_audit_command", "")
            ).strip()
            if remote_audit_command:
                print(f"  Remote evidence audit    : {remote_audit_command}")
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
            print("\nPlatform build contracts:")
            target_width = max(len(row["target"]) for row in platform["targets"])
            display_statuses = {
                "verified-default-native": "declared-default-native",
                "verified-termux-web-mobile": "declared-termux-web-mobile",
                "verified-ios-web-pwa": "declared-ios-web-pwa",
            }
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
                provenance = _protected_platform_row_provenance_note(row)
                print(
                    f"  {row['target']:<{target_width}} {row['current_percent']:>5.1f}% "
                    f"{display_statuses.get(row['status'], row['status'])} "
                    f"({row['channel']}){remote}{missing}{provenance}"
                )
        return 0
    for row in feature_summary():
        print(f"{row['id']:<32} {row['status']:<18} {row['coverage']}")
    return 0


def _protected_platform_row_provenance_note(row: dict[str, object]) -> str:
    required = row.get("accepted_evidence_required_targets")
    if not isinstance(required, list) or not required:
        return ""
    if row.get("release_backed_readiness_complete") is True:
        return "; release-backed proof complete"
    if row.get("accepted_evidence_record_complete") is True:
        return "; accepted records complete, release assets pending"
    return "; accepted records/release assets pending"

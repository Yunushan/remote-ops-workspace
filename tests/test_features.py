import hashlib
import json
from pathlib import Path

from remote_ops_workspace.features import (
    _platform_verified_readiness,
    _release_source_run_attempt_conflicts,
    coverage_report,
    load_feature_manifest,
)

LINUX_SECURITY_REQUIREMENTS = [
    "security patch evidence proving TLS 1.3 preferred, TLS 1.2 minimum, "
    "isolated legacy compatibility and CVE patch review with concrete "
    "security_update_channel and cve_review_reference update/advisory provenance",
    "modern Windows 10/11, Linux, and macOS defaults must keep hardened crypto",
]

REQUESTED_PRODUCTS = {
    "Apache Guacamole",
    "Bitvise SSH Client",
    "Cmder",
    "ConEmu (with Cygwin / MSYS2 / SSH)",
    "Devolutions Remote Desktop Manager",
    "Electerm",
    "Hyper",
    "KiTTY",
    "MTPuTTY",
    "MobaXterm",
    "Muon SSH",
    "PuTTY",
    "Remmina",
    "Royal TS / Royal TSX",
    "SecureCRT",
    "Solar-PuTTY",
    "SuperPuTTY",
    "Tabby",
    "Terminator",
    "Termius",
    "Warp (macOS/Linux, Windows coming)",
    "WinSCP",
    "Windows Terminal + OpenSSH",
    "X410 + any terminal (e.g., Windows Terminal, Alacritty)",
    "XPipe",
    "Xming (or VcXsrv) + PuTTY / mRemoteNG",
    "Xshell",
    "mRemoteNG",
}


def test_feature_manifest_covers_requested_products() -> None:
    manifest = load_feature_manifest()
    products = set(manifest["products"])
    assert REQUESTED_PRODUCTS.issubset(products)
    feature_ids = {item["id"] for item in manifest["features"]}
    assert "protocol.ssh" in feature_ids
    assert "protocol.rdp" in feature_ids
    assert "terminal.splits" in feature_ids
    assert "terminal.local-shell" in feature_ids
    assert "security.vault" in feature_ids
    assert "web.pwa" in feature_ids
    assert "ios.web-pwa" in feature_ids


def test_feature_coverage_report_scores_each_requested_product() -> None:
    report = coverage_report()
    assert report["target_percent"] == 100.0
    mapping = report["feature_family_mapping"]
    adapter = report["adapter_ready_coverage"]
    parity = report["production_parity_coverage"]
    assert mapping["overall"]["current_percent"] == 100.0
    assert adapter["overall"]["current_percent"] == mapping["overall"]["current_percent"]
    assert parity["overall"]["current_percent"] == mapping["overall"]["current_percent"]
    assert parity["overall"]["gap_percent"] == 0.0
    rows = {row["product"]: row for row in mapping["products"]}
    adapter_rows = {row["product"]: row for row in adapter["products"]}
    parity_rows = {row["product"]: row for row in parity["products"]}
    for product in REQUESTED_PRODUCTS:
        row = rows[product]
        adapter_row = adapter_rows[product]
        parity_row = parity_rows[product]
        assert row["feature_count"] > 0
        assert row["current_percent"] == row["target_percent"]
        assert adapter_row["current_percent"] == adapter_row["target_percent"]
        assert adapter_row["gap_percent"] == 0.0
        assert parity_row["current_percent"] == parity_row["target_percent"]
        assert parity_row["gap_percent"] == 0.0


def test_adapter_ready_reaches_target_without_full_overrides() -> None:
    manifest = load_feature_manifest()
    scoring = manifest["coverage_scoring"]
    assert scoring["adapter_ready_feature_overrides"] == {}
    assert scoring["adapter_ready_target_overrides"] == {}
    assert scoring["production_parity_feature_overrides"] == {}
    assert scoring["production_parity_target_overrides"] == {}
    assert scoring["product_ready_feature_overrides"] == {}
    assert scoring["product_ready_target_overrides"] == {}

    report = coverage_report()
    overall = report["adapter_ready_coverage"]["overall"]
    assert overall["current_percent"] == 100.0
    assert overall["gap_percent"] == 0.0

    adapter_rows = {
        row["product"]: row for row in report["adapter_ready_coverage"]["products"]
    }
    for product in REQUESTED_PRODUCTS:
        row = adapter_rows[product]
        assert row["current_percent"] == row["target_percent"]
        assert row["gap_percent"] == 0.0
        assert "overrides_applied" not in row


def test_feature_coverage_weights_cover_manifest_statuses() -> None:
    manifest = load_feature_manifest()
    report = coverage_report()
    mapping_weights = report["status_weights"]
    adapter_weights = report["adapter_ready_status_weights"]
    parity_weights = report["production_parity_status_weights"]
    statuses = {item["status"] for item in manifest["features"]}
    assert statuses.issubset(mapping_weights)
    assert statuses.issubset(adapter_weights)
    assert statuses.issubset(parity_weights)
    for status in statuses:
        assert adapter_weights[status] == mapping_weights[status]
        assert parity_weights[status] == adapter_weights[status]
    for status, weight in adapter_weights.items():
        if status not in statuses and not status.startswith("implemented"):
            assert weight < 1.0


def test_product_feature_mappings_reference_known_products_and_features() -> None:
    manifest = load_feature_manifest()
    products = set(manifest["products"])
    feature_ids = {item["id"] for item in manifest["features"]}
    mappings = manifest["coverage_scoring"]["product_feature_mappings"]
    assert set(mappings).issubset(products)
    for mapped_features in mappings.values():
        assert set(mapped_features).issubset(feature_ids)


def test_feature_coverage_report_includes_evidence_records() -> None:
    report = coverage_report()
    summary = report["evidence_summary"]
    evidence = report["feature_evidence"]
    assert summary["total_features"] == len(evidence)
    assert summary["features_missing_evidence"] == 0
    assert summary["features_missing_status"] == 0
    assert summary["features_missing_product_mapping"] == 0
    for item in evidence:
        assert item["id"]
        assert item["name"]
        assert item["implementation_kind"] != "unknown"
        assert item["evidence_count"] >= 2


def test_workflow_parity_report_explains_every_coverage_row() -> None:
    report = coverage_report()
    contract = report["workflow_parity_contract"]
    assert contract["label"] == "release-backed product workflow parity"
    assert contract["native_clone_claimed"] is False

    evidence_rows = {
        row["product"]: row for row in report["workflow_parity_evidence"]
    }
    parity_rows = [
        report["production_parity_coverage"]["overall"],
        *report["production_parity_coverage"]["products"],
    ]
    for row in parity_rows:
        evidence = evidence_rows[row["product"]]
        assert evidence["label"] == contract["label"]
        assert evidence["native_clone_claimed"] is False
        assert evidence["coverage_percent"] == row["current_percent"]
        assert evidence["gap_percent"] == row["gap_percent"]
        assert evidence["feature_count"] == row["feature_count"]
        assert len(evidence["feature_ids"]) == row["feature_count"]
        assert evidence["full_parity_feature_count"] == row["feature_count"]
        assert evidence["partial_feature_count"] == 0
        assert evidence["missing_release_evidence_count"] == 0
        for item in evidence["feature_evidence"]:
            assert item["id"]
            assert item["extension_point"]
            assert item["counts_as_full_parity"] is True
            assert item["release_backed"] is True
            assert item["evidence_refs"]


def test_readme_coverage_tables_match_generated_readiness_scores() -> None:
    report = coverage_report()
    adapter_rows = {
        row["product"]: row for row in report["adapter_ready_coverage"]["products"]
    }
    parity_rows = {
        row["product"]: row for row in report["production_parity_coverage"]["products"]
    }
    expected_lines = []
    for row in report["feature_family_mapping"]["products"]:
        adapter_row = adapter_rows[row["product"]]
        parity_row = parity_rows[row["product"]]
        expected_lines.append(
            f"| {row['product']} | {row['current_percent']:.1f}% | "
            f"{adapter_row['current_percent']:.1f}% | "
            f"{parity_row['current_percent']:.1f}% | {parity_row['gap_percent']:.1f}% | "
            f"{row['feature_count']} |"
        )
    mapping_overall = report["feature_family_mapping"]["overall"]
    adapter_overall = report["adapter_ready_coverage"]["overall"]
    parity_overall = report["production_parity_coverage"]["overall"]
    expected_lines.append(
        f"| **Overall** | **{mapping_overall['current_percent']:.1f}%** | "
        f"**{adapter_overall['current_percent']:.1f}%** | "
        f"**{parity_overall['current_percent']:.1f}%** | "
        f"**{parity_overall['gap_percent']:.1f}%** | "
        f"**{mapping_overall['feature_count']}** |"
    )

    for path in (Path("README.md"), Path("docs/FULL_FEATURE_COVERAGE.md")):
        text = path.read_text(encoding="utf-8")
        for line in expected_lines:
            assert line in text
        assert "| MobaXterm | 100.0% | 100.0% | 100.0% | 0.0% | 50 |" in text
        assert "release-backed product workflow parity" in text
        assert "not a proprietary native clone" in text


def test_platform_verified_readiness_tracks_partial_targets() -> None:
    report = coverage_report()
    platform = report["platform_verified_readiness"]
    assert platform["overall"]["current_percent"] == 100.0
    assert platform["overall"]["gap_percent"] == 0.0
    assert platform["overall"]["target_count"] == 10
    assert platform["overall"]["extended_target_count"] == 7
    denominator = platform["denominator"]
    assert denominator["scope"] == "verified_readiness_scope=true rows only"
    assert denominator["included_target_count"] == 10
    assert denominator["excluded_target_count"] == 7
    assert denominator["included_targets"] == platform["overall"]["included_targets"]
    assert denominator["excluded_targets"] == platform["overall"]["excluded_targets"]
    assert denominator["denominator_excludes_extended_compatibility_rows"] is True
    assert denominator["protected_goal_targets"] == [
        "linux-i386",
        "linux-armhf",
        "windows-xp-native-x86",
        "windows-xp-native-x64",
    ]
    assert denominator["protected_goal_score_source"] == "protected_goal_parity"
    assert denominator["release_asset_provenance_in_static_score"] is False
    assert "linux-i386" in denominator["excluded_targets"]
    assert "linux-armhf" in denominator["excluded_targets"]
    assert "Windows XP" in denominator["excluded_targets"]
    goal = platform["protected_goal_parity"]
    for block in (platform["overall"], denominator):
        assert block["protected_goal_current_percent"] == goal["current_percent"]
        assert block["protected_goal_gap_percent"] == goal["gap_percent"]
        assert block["protected_goal_status"] == goal["status"]
        assert block["protected_goal_complete"] == goal["complete"]
        assert block["protected_goal_release_backed_complete"] == goal["release_backed_complete"]
        assert block["protected_goal_accepted_target_count"] == goal["accepted_target_count"]
        assert block["protected_goal_target_count"] == goal["target_count"]
        assert block["protected_goal_missing_targets"] == goal["missing_targets"]
    assert goal["current_percent"] == 0.0
    assert goal["gap_percent"] == 100.0
    assert goal["accepted_target_count"] == 0
    assert goal["target_count"] == 4
    assert goal["complete"] is False
    assert goal["status"] == "missing-accepted-evidence"
    assert goal["release_source_run_urls"] == {}
    assert goal["release_source_workflows"] == {}
    assert goal["selected_release_source_run_urls"] == {}
    assert goal["release_source_run_attempt_conflicts"] == {}
    assert goal["release_source_provenance_complete"] is False
    assert goal["source_ref_preflight_command"] == (
        "python scripts/check_platform_evidence_source_ref.py "
        "--repository <owner>/<repo> --release-tag v<project.version> "
        "--require-goal-targets"
    )
    assert goal["release_import_dry_run_command"] == (
        "python scripts/import_platform_evidence_artifacts.py "
        "--release-tag v<project.version> --require-goal-targets "
        "--out-dir <release-assets-dir> --dry-run --verify-source-run "
        "--repository <owner>/<repo>"
    )
    assert goal["remote_release_evidence_audit_command"] == (
        "python scripts/check_platform_release_evidence_remote.py "
        "--repository <owner>/<repo> --release-tag v<project.version> "
        "--require-goal-targets --require-source-runs "
        "--require-source-artifact-bytes --require-final-record-bytes "
        "--require-release-asset-bytes --require-tag-source-head"
    )
    assert goal["missing_targets"] == [
        "linux-i386",
        "linux-armhf",
        "windows-xp-native-x86",
        "windows-xp-native-x64",
    ]
    requirements = {
        item["target"]: item for item in goal["target_evidence_requirements"]
    }
    assert set(requirements) == set(goal["required_targets"])
    assert requirements["linux-i386"]["status"] == "missing-accepted-evidence"
    assert requirements["linux-i386"]["accepted_evidence_record"] == {
        "registry": "configs/platform_verified_evidence.json",
        "target": "linux-i386",
        "status": "accepted",
        "readiness_percent": 100.0,
        "release_tag": "v<project.version>",
        "review_bundle_required": True,
    }
    assert "remote-ops-workspace-v<project.version>-linux-i386.deb" in requirements["linux-i386"]["required_artifacts"]
    linux_source = requirements["linux-i386"]["release_asset_source_required"]
    assert linux_source["type"] == "github-actions-artifact"
    assert linux_source["workflow"] == ".github/workflows/extended-platform-evidence.yml"
    assert linux_source["artifact_name"] == "extended-linux-evidence-linux-i386-v<project.version>"
    assert linux_source["head_sha"] == "40-character lowercase Git SHA matching release source"
    assert linux_source["run_attempt"] == "positive GitHub Actions run attempt matching release source"
    assert "GitHub Actions run URL" in linux_source["workflow_run_url"]
    assert set(linux_source["contains_files"]) == (
        set(requirements["linux-i386"]["required_artifacts"])
        | set(requirements["linux-i386"]["required_review_bundle_files"])
        | {"platform-verified-evidence-linux-i386-final.json"}
    )
    assert requirements["linux-i386"]["workflow_dispatch_command"] == (
        "gh workflow run extended-platform-evidence.yml --repo <owner>/<repo> "
        "--ref v<project.version> -f target=linux-i386 "
        "-f release_tag=v<project.version> "
        "-f release_asset_base_url=<github-release-download-url>"
    )
    xp_source = requirements["windows-xp-native-x86"]["release_asset_source_required"]
    assert xp_source["workflow"] == ".github/workflows/xp-native-evidence.yml"
    assert xp_source["artifact_name"] == "xp-native-evidence-windows-xp-native-x86-v<project.version>"
    assert xp_source["run_attempt"] == "positive GitHub Actions run attempt matching release source"
    assert set(xp_source["contains_files"]) == (
        set(requirements["windows-xp-native-x86"]["required_artifacts"])
        | set(requirements["windows-xp-native-x86"]["required_review_bundle_files"])
        | {"platform-verified-evidence-windows-xp-native-x86-final.json"}
    )
    assert requirements["windows-xp-native-x86"]["workflow_dispatch_command"] == (
        "gh workflow run xp-native-evidence.yml --repo <owner>/<repo> "
        "--ref v<project.version> -f target=windows-xp-native-x86 "
        "-f release_tag=v<project.version> "
        "-f release_asset_base_url=<github-release-download-url> "
        "-f assets_dir=<target-release-artifact-dir> "
        "-f evidence_file=<target-release-evidence.json> "
        "-f evidence_dir=<target-release-evidence-dir>"
    )
    assert "artifact_validation_command" in requirements["linux-i386"]["required_commands"]
    assert "local_evidence_preflight_command" in requirements["linux-i386"]["required_commands"]
    assert "check_platform_goal_local_evidence.py" in requirements["linux-i386"]["required_commands"]["local_evidence_preflight_command"]
    linux_candidate_command = requirements["linux-i386"]["required_commands"][
        "accepted_evidence_candidate_command"
    ]
    xp_candidate_command = requirements["windows-xp-native-x86"]["required_commands"][
        "accepted_evidence_candidate_command"
    ]
    assert (
        "--staged-upload-out-dir platform-evidence-upload/linux-i386/v<project.version>"
        in linux_candidate_command
    )
    assert (
        "--staged-upload-out-dir platform-evidence-upload/windows-xp-native-x86/v<project.version>"
        in xp_candidate_command
    )
    assert "--xp-evidence-output-dir <xp-evidence-output-dir>" in xp_candidate_command
    assert "staged_upload_command" in requirements["linux-i386"]["required_commands"]
    assert (
        "stage_extended_linux_evidence_upload.py"
        in requirements["linux-i386"]["required_commands"]["staged_upload_command"]
    )
    assert (
        "--out-dir platform-evidence-upload/linux-i386/v<project.version>"
        in requirements["linux-i386"]["required_commands"]["staged_upload_command"]
    )
    assert "staged_upload_command" in requirements["windows-xp-native-x86"]["required_commands"]
    assert (
        "stage_xp_native_evidence_upload.py"
        in requirements["windows-xp-native-x86"]["required_commands"]["staged_upload_command"]
    )
    assert (
        "--out-dir platform-evidence-upload/windows-xp-native-x86/v<project.version>"
        in requirements["windows-xp-native-x86"]["required_commands"]["staged_upload_command"]
    )
    assert requirements["linux-i386"]["security_requirements"] == LINUX_SECURITY_REQUIREMENTS
    assert requirements["linux-armhf"]["security_requirements"] == LINUX_SECURITY_REQUIREMENTS
    assert (
        "bind sanitized host label, deterministic evidence run ID and observed-at UTC timestamp into the native smoke log"
        in requirements["linux-i386"]["smoke_evidence"]
    )
    assert (
        "bind sanitized host label, deterministic evidence run ID and observed-at UTC timestamp into the native smoke log"
        in requirements["linux-armhf"]["smoke_evidence"]
    )
    assert requirements["windows-xp-native-x86"]["security_requirements"] == [
        "legacy TLS, SSH, and RDP compatibility must remain profile-scoped opt-in",
        "XP security patch evidence must include concrete security_update_channel "
        "and cve_review_reference update/advisory provenance",
        "modern Windows 10/11, Linux, and macOS defaults must keep hardened crypto",
    ]
    assert "XP remote-target coverage does not imply native-host readiness" in (
        requirements["windows-xp-native-x86"]["support_boundary"]
    )
    rows = {row["target"]: row for row in platform["targets"]}
    assert rows["windows-x64"]["current_percent"] == 100.0
    assert rows["windows-x64"]["verified_readiness_scope"] is True
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["verified_readiness_scope"] is False
    assert rows["linux-i386"]["accepted_evidence_record_complete"] is False
    assert rows["linux-i386"]["release_asset_provenance_complete"] is False
    assert rows["linux-i386"]["release_backed_readiness_complete"] is False
    assert "--assets-dir" in rows["linux-i386"]["static_readiness_evidence_scope"]
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]
    assert rows["android-arm64"]["current_percent"] == 100.0
    assert rows["android-arm64"]["status"] == "verified-termux-web-mobile"
    assert rows["android-arm64"]["verified_readiness_scope"] is True
    assert rows["ios-web"]["current_percent"] == 100.0
    assert rows["ios-web"]["status"] == "verified-ios-web-pwa"
    assert rows["ios-web"]["verified_readiness_scope"] is True
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["remote_target_coverage_percent"] == 100.0
    assert rows["Windows XP"]["legacy_architectures"] == ["x86", "x64"]
    assert rows["Windows XP"]["security_profile"] == "isolated-legacy-opt-in"
    assert rows["Windows XP"]["verified_readiness_scope"] is False
    assert rows["Windows XP"]["accepted_evidence_record_complete"] is False
    assert rows["Windows XP"]["release_asset_provenance_complete"] is False
    assert rows["Windows XP"]["release_backed_readiness_complete"] is False
    assert "--assets-dir" in rows["Windows XP"]["static_readiness_evidence_scope"]
    assert rows["Windows XP"]["accepted_evidence_missing_targets"] == [
        "windows-xp-native-x86",
        "windows-xp-native-x64",
    ]


def test_platform_verified_readiness_promotes_only_with_accepted_evidence() -> None:
    manifest = _extended_platform_manifest()
    evidence = _accepted_evidence_registry(
        _linux_accepted_evidence("linux-i386"),
        _xp_accepted_evidence("windows-xp-native-x86"),
    )

    report = _platform_verified_readiness(platform_data=manifest, evidence_registry=evidence)
    rows = {row["target"]: row for row in report["targets"]}
    goal = report["protected_goal_parity"]

    assert rows["linux-i386"]["current_percent"] == 100.0
    assert rows["linux-i386"]["status"] == "verified-accepted-native-evidence"
    assert rows["linux-i386"]["verified_readiness_scope"] is True
    assert rows["linux-i386"]["accepted_evidence_record_complete"] is True
    assert rows["linux-i386"]["release_asset_provenance_complete"] is False
    assert rows["linux-i386"]["release_backed_readiness_complete"] is False
    assert "accepted-record/source-run metadata only" in rows["linux-i386"]["static_readiness_evidence_scope"]
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == []
    assert rows["linux-i386"]["accepted_evidence_release_tags"] == {
        "linux-i386": "v1.0.2",
    }
    assert rows["linux-i386"]["accepted_evidence_release_repositories"] == {
        "linux-i386": ["example/remote-ops-workspace"],
    }
    assert rows["linux-i386"]["accepted_evidence_release_source_heads"] == {
        "linux-i386": "a" * 40,
    }
    assert rows["linux-i386"]["accepted_evidence_release_source_run_attempts"] == {
        "linux-i386": 1,
    }
    assert rows["linux-i386"]["accepted_evidence_release_source_run_urls"] == {
        "linux-i386": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
    }
    assert rows["linux-i386"]["accepted_evidence_release_source_workflows"] == {
        "linux-i386": ".github/workflows/extended-platform-evidence.yml",
    }
    assert rows["linux-armhf"]["current_percent"] == 70.0
    assert rows["linux-armhf"]["verified_readiness_scope"] is False
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "partial-xp-native-host-evidence"
    assert rows["Windows XP"]["verified_readiness_scope"] is False
    assert rows["Windows XP"]["accepted_evidence_record_complete"] is False
    assert rows["Windows XP"]["release_asset_provenance_complete"] is False
    assert rows["Windows XP"]["release_backed_readiness_complete"] is False
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == ["windows-xp-native-x86"]
    assert rows["Windows XP"]["accepted_evidence_missing_targets"] == ["windows-xp-native-x64"]
    assert rows["Windows XP"]["accepted_evidence_release_source_workflows"] == {
        "windows-xp-native-x86": ".github/workflows/xp-native-evidence.yml",
    }
    assert goal["current_percent"] == 50.0
    assert goal["accepted_targets"] == ["linux-i386", "windows-xp-native-x86"]
    assert goal["missing_targets"] == ["linux-armhf", "windows-xp-native-x64"]
    assert goal["release_source_provenance_complete"] is False
    assert goal["complete"] is False

    evidence["accepted_evidence"].append(_xp_accepted_evidence("windows-xp-native-x64"))
    report = _platform_verified_readiness(platform_data=manifest, evidence_registry=evidence)
    rows = {row["target"]: row for row in report["targets"]}
    goal = report["protected_goal_parity"]

    assert rows["Windows XP"]["current_percent"] == 100.0
    assert rows["Windows XP"]["status"] == "verified-xp-native-host-evidence"
    assert rows["Windows XP"]["verified_readiness_scope"] is True
    assert rows["Windows XP"]["accepted_evidence_record_complete"] is True
    assert rows["Windows XP"]["release_asset_provenance_complete"] is False
    assert rows["Windows XP"]["release_backed_readiness_complete"] is False
    assert "--require-complete" in rows["Windows XP"]["static_readiness_evidence_scope"]
    assert rows["Windows XP"]["accepted_evidence_missing_targets"] == []
    assert goal["current_percent"] == 75.0
    assert goal["missing_targets"] == ["linux-armhf"]
    assert goal["complete"] is False

    evidence["accepted_evidence"][-1]["release_tag"] = "v1.0.3"
    report = _platform_verified_readiness(platform_data=manifest, evidence_registry=evidence)
    rows = {row["target"]: row for row in report["targets"]}
    goal = report["protected_goal_parity"]

    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "partial-xp-native-host-evidence"
    assert rows["Windows XP"]["verified_readiness_scope"] is False
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == ["windows-xp-native-x86"]
    assert rows["Windows XP"]["accepted_evidence_missing_targets"] == ["windows-xp-native-x64"]
    assert rows["Windows XP"]["accepted_evidence_release_tags"] == {
        "windows-xp-native-x86": "v1.0.2",
    }
    assert rows["Windows XP"]["accepted_evidence_release_source_run_attempts"] == {
        "windows-xp-native-x86": 1,
    }
    assert rows["Windows XP"]["accepted_evidence_release_source_run_urls"] == {
        "windows-xp-native-x86": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
    }
    assert rows["Windows XP"]["accepted_evidence_release_source_workflows"] == {
        "windows-xp-native-x86": ".github/workflows/xp-native-evidence.yml",
    }
    assert goal["current_percent"] == 50.0
    assert goal["accepted_targets"] == ["linux-i386", "windows-xp-native-x86"]
    assert goal["missing_targets"] == ["linux-armhf", "windows-xp-native-x64"]
    assert goal["release_source_provenance_complete"] is False


def test_platform_verified_readiness_goal_parity_completes_with_all_accepted_evidence() -> None:
    manifest = _extended_platform_manifest()
    evidence = _accepted_evidence_registry(
        _linux_accepted_evidence("linux-i386"),
        _linux_accepted_evidence("linux-armhf"),
        _xp_accepted_evidence("windows-xp-native-x86"),
        _xp_accepted_evidence("windows-xp-native-x64"),
    )

    report = _platform_verified_readiness(platform_data=manifest, evidence_registry=evidence)
    goal = report["protected_goal_parity"]
    denominator = report["denominator"]

    assert goal["current_percent"] == 100.0
    assert goal["gap_percent"] == 0.0
    assert goal["accepted_target_count"] == 4
    assert goal["aggregate_accepted_target_count"] == 4
    assert goal["release_tag"] == "v1.0.2"
    assert goal["release_tags"] == ["v1.0.2"]
    assert goal["release_repository"] == "example/remote-ops-workspace"
    assert goal["release_repositories"] == ["example/remote-ops-workspace"]
    assert goal["release_source_head"] == "a" * 40
    assert goal["release_source_heads"] == ["a" * 40]
    assert goal["release_source_run_attempts"] == {
        "linux-armhf": 1,
        "linux-i386": 1,
        "windows-xp-native-x64": 1,
        "windows-xp-native-x86": 1,
    }
    assert goal["release_source_run_urls"] == {
        "linux-armhf": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "linux-i386": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "windows-xp-native-x64": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "windows-xp-native-x86": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
    }
    assert goal["release_source_workflows"] == {
        "linux-armhf": ".github/workflows/extended-platform-evidence.yml",
        "linux-i386": ".github/workflows/extended-platform-evidence.yml",
        "windows-xp-native-x64": ".github/workflows/xp-native-evidence.yml",
        "windows-xp-native-x86": ".github/workflows/xp-native-evidence.yml",
    }
    assert goal["selected_release_source_run_attempts"] == goal["release_source_run_attempts"]
    assert goal["selected_release_source_run_urls"] == goal["release_source_run_urls"]
    assert goal["selected_release_source_workflows"] == goal["release_source_workflows"]
    assert goal["release_source_run_attempt_conflicts"] == {}
    assert goal["release_source_provenance_complete"] is True
    assert goal["release_asset_provenance_complete"] is False
    assert goal["record_complete"] is True
    assert goal["release_backed_complete"] is False
    assert goal["completion_requires_release_asset_provenance"] is True
    assert goal["completion_evidence"] == "accepted-records-only"
    assert goal["remote_release_evidence_audit_command"] == (
        "python scripts/check_platform_release_evidence_remote.py "
        "--repository example/remote-ops-workspace --release-tag v1.0.2 "
        "--require-goal-targets --require-source-runs "
        "--require-source-artifact-bytes --require-final-record-bytes "
        "--require-release-asset-bytes --require-tag-source-head"
    )
    assert goal["release_asset_provenance_command"] == (
        "python scripts/check_protected_platform_goal.py "
        "--release-tag v1.0.2 --require-complete --assets-dir <release-assets-dir> "
        "--repository example/remote-ops-workspace"
    )
    assert goal["release_consistent"] is True
    assert goal["release_repository_consistent"] is True
    assert goal["release_source_head_consistent"] is True
    assert goal["accepted_targets"] == [
        "linux-i386",
        "linux-armhf",
        "windows-xp-native-x86",
        "windows-xp-native-x64",
    ]
    assert goal["missing_targets"] == []
    assert goal["complete"] is False
    assert denominator["included_targets"] == ["linux-i386", "linux-armhf", "Windows XP"]
    assert denominator["excluded_targets"] == []
    assert goal["status"] == "release-asset-provenance-required"
    assert all(
        item["accepted"] is True and item["status"] == "accepted"
        for item in goal["target_evidence_requirements"]
    )


def test_platform_verified_readiness_goal_parity_ignores_duplicate_target_records() -> None:
    manifest = _extended_platform_manifest()
    evidence = _accepted_evidence_registry(
        _linux_accepted_evidence("linux-i386"),
        _linux_accepted_evidence("linux-i386"),
        _linux_accepted_evidence("linux-armhf"),
        _xp_accepted_evidence("windows-xp-native-x86"),
        _xp_accepted_evidence("windows-xp-native-x64"),
    )

    report = _platform_verified_readiness(platform_data=manifest, evidence_registry=evidence)
    rows = {row["target"]: row for row in report["targets"]}
    goal = report["protected_goal_parity"]

    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]
    assert goal["current_percent"] == 75.0
    assert goal["accepted_target_count"] == 3
    assert goal["accepted_targets"] == [
        "linux-armhf",
        "windows-xp-native-x86",
        "windows-xp-native-x64",
    ]
    assert goal["missing_targets"] == ["linux-i386"]
    assert goal["complete"] is False


def test_platform_verified_readiness_detects_conflicting_source_attempts() -> None:
    assert _release_source_run_attempt_conflicts(
        {
            "linux-i386": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
            "linux-armhf": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
            "windows-xp-native-x86": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
            "windows-xp-native-x64": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
            "windows-x64": "https://github.com/example/remote-ops-workspace/actions/runs/99999",
        },
        {
            "linux-i386": 1,
            "linux-armhf": 1,
            "windows-xp-native-x86": 2,
            "windows-xp-native-x64": 1,
            "windows-x64": 3,
        },
    ) == {
        "https://github.com/example/remote-ops-workspace/actions/runs/12345": {
            "linux-armhf": 1,
            "linux-i386": 1,
            "windows-xp-native-x64": 1,
            "windows-xp-native-x86": 2,
        }
    }


def test_platform_verified_readiness_xp_row_rejects_conflicting_source_attempts() -> None:
    manifest = _extended_platform_manifest()
    xp_x64 = _xp_accepted_evidence("windows-xp-native-x64")
    _replace_xp_release_source_run_attempt(xp_x64, 2)
    evidence = _accepted_evidence_registry(
        _xp_accepted_evidence("windows-xp-native-x86"),
        xp_x64,
    )

    report = _platform_verified_readiness(platform_data=manifest, evidence_registry=evidence)
    rows = {row["target"]: row for row in report["targets"]}
    goal = report["protected_goal_parity"]

    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "partial-xp-native-host-evidence"
    assert rows["Windows XP"]["verified_readiness_scope"] is False
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == [
        "windows-xp-native-x86",
        "windows-xp-native-x64",
    ]
    assert rows["Windows XP"]["accepted_evidence_release_source_run_attempts"] == {
        "windows-xp-native-x86": 1,
        "windows-xp-native-x64": 2,
    }
    assert goal["release_source_run_attempt_conflicts"] == {
        "https://github.com/example/remote-ops-workspace/actions/runs/12345": {
            "windows-xp-native-x64": 2,
            "windows-xp-native-x86": 1,
        }
    }
    assert goal["complete"] is False


def test_platform_verified_readiness_goal_parity_requires_one_release_repository() -> None:
    manifest = _extended_platform_manifest()
    xp_x64 = _xp_accepted_evidence("windows-xp-native-x64")
    _replace_release_repository(xp_x64, "other/remote-ops-workspace")
    evidence = _accepted_evidence_registry(
        _linux_accepted_evidence("linux-i386"),
        _linux_accepted_evidence("linux-armhf"),
        _xp_accepted_evidence("windows-xp-native-x86"),
        xp_x64,
    )

    report = _platform_verified_readiness(platform_data=manifest, evidence_registry=evidence)
    rows = {row["target"]: row for row in report["targets"]}
    goal = report["protected_goal_parity"]

    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "partial-xp-native-host-evidence"
    assert rows["Windows XP"]["verified_readiness_scope"] is False
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == [
        "windows-xp-native-x86",
    ]
    assert rows["Windows XP"]["accepted_evidence_missing_targets"] == ["windows-xp-native-x64"]
    assert rows["Windows XP"]["accepted_evidence_release_repositories"] == {
        "windows-xp-native-x86": ["example/remote-ops-workspace"],
    }
    assert goal["current_percent"] == 75.0
    assert goal["gap_percent"] == 25.0
    assert goal["accepted_target_count"] == 3
    assert goal["release_tag"] == "v1.0.2"
    assert goal["release_repository"] == "example/remote-ops-workspace"
    assert goal["release_repositories"] == ["example/remote-ops-workspace"]
    assert goal["release_repository_consistent"] is True
    assert goal["selected_release_source_run_attempts"] == {
        "linux-i386": 1,
        "linux-armhf": 1,
        "windows-xp-native-x86": 1,
    }
    assert goal["selected_release_source_workflows"] == {
        "linux-i386": ".github/workflows/extended-platform-evidence.yml",
        "linux-armhf": ".github/workflows/extended-platform-evidence.yml",
        "windows-xp-native-x86": ".github/workflows/xp-native-evidence.yml",
    }
    assert goal["release_source_run_attempts"] == {
        "linux-armhf": 1,
        "linux-i386": 1,
        "windows-xp-native-x86": 1,
    }
    assert goal["accepted_targets"] == [
        "linux-i386",
        "linux-armhf",
        "windows-xp-native-x86",
    ]
    assert goal["missing_targets"] == ["windows-xp-native-x64"]
    assert goal["complete"] is False
    assert goal["status"] == "missing-accepted-evidence"


def test_platform_verified_readiness_goal_parity_requires_one_release_tag() -> None:
    manifest = _extended_platform_manifest()
    evidence = _accepted_evidence_registry(
        _linux_accepted_evidence("linux-i386"),
        _retag_accepted_evidence(_linux_accepted_evidence("linux-armhf"), "v1.0.3"),
        _retag_accepted_evidence(_xp_accepted_evidence("windows-xp-native-x86"), "v1.0.3"),
        _retag_accepted_evidence(_xp_accepted_evidence("windows-xp-native-x64"), "v1.0.3"),
    )

    report = _platform_verified_readiness(platform_data=manifest, evidence_registry=evidence)
    goal = report["protected_goal_parity"]

    assert goal["current_percent"] == 75.0
    assert goal["gap_percent"] == 25.0
    assert goal["accepted_target_count"] == 3
    assert goal["aggregate_accepted_target_count"] == 4
    assert goal["release_tag"] == "v1.0.3"
    assert goal["release_tags"] == ["v1.0.2", "v1.0.3"]
    assert goal["release_consistent"] is False
    assert goal["selected_release_source_run_attempts"] == {
        "linux-armhf": 1,
        "windows-xp-native-x86": 1,
        "windows-xp-native-x64": 1,
    }
    assert goal["selected_release_source_workflows"] == {
        "linux-armhf": ".github/workflows/extended-platform-evidence.yml",
        "windows-xp-native-x86": ".github/workflows/xp-native-evidence.yml",
        "windows-xp-native-x64": ".github/workflows/xp-native-evidence.yml",
    }
    assert goal["accepted_targets"] == [
        "linux-armhf",
        "windows-xp-native-x86",
        "windows-xp-native-x64",
    ]
    assert goal["missing_targets"] == ["linux-i386"]
    assert goal["aggregate_accepted_targets"] == [
        "linux-i386",
        "linux-armhf",
        "windows-xp-native-x86",
        "windows-xp-native-x64",
    ]
    assert goal["selected_release_scope_exclusions"] == {
        "linux-i386": ["release-tag:v1.0.2"]
    }
    assert goal["complete"] is False
    assert goal["status"] == "mixed-release-evidence"


def test_platform_verified_readiness_goal_parity_requires_one_release_source_head() -> None:
    manifest = _extended_platform_manifest()
    xp_x64 = _xp_accepted_evidence("windows-xp-native-x64")
    _replace_release_source_head(xp_x64, "b" * 40)
    evidence = _accepted_evidence_registry(
        _linux_accepted_evidence("linux-i386"),
        _linux_accepted_evidence("linux-armhf"),
        _xp_accepted_evidence("windows-xp-native-x86"),
        xp_x64,
    )

    report = _platform_verified_readiness(platform_data=manifest, evidence_registry=evidence)
    rows = {row["target"]: row for row in report["targets"]}
    goal = report["protected_goal_parity"]

    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "partial-xp-native-host-evidence"
    assert rows["Windows XP"]["verified_readiness_scope"] is False
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == [
        "windows-xp-native-x86",
        "windows-xp-native-x64",
    ]
    assert rows["Windows XP"]["accepted_evidence_release_source_heads"] == {
        "windows-xp-native-x86": "a" * 40,
        "windows-xp-native-x64": "b" * 40,
    }
    assert rows["Windows XP"]["accepted_evidence_release_source_run_attempts"] == {
        "windows-xp-native-x86": 1,
        "windows-xp-native-x64": 1,
    }
    assert rows["Windows XP"]["accepted_evidence_release_source_workflows"] == {
        "windows-xp-native-x86": ".github/workflows/xp-native-evidence.yml",
        "windows-xp-native-x64": ".github/workflows/xp-native-evidence.yml",
    }
    assert goal["current_percent"] == 75.0
    assert goal["gap_percent"] == 25.0
    assert goal["accepted_target_count"] == 3
    assert goal["aggregate_accepted_target_count"] == 4
    assert goal["release_tag"] == "v1.0.2"
    assert goal["release_repository"] == "example/remote-ops-workspace"
    assert goal["release_source_head"] == "a" * 40
    assert goal["release_source_heads"] == ["a" * 40, "b" * 40]
    assert goal["release_source_head_consistent"] is False
    assert goal["selected_release_source_run_attempts"] == {
        "linux-i386": 1,
        "linux-armhf": 1,
        "windows-xp-native-x86": 1,
    }
    assert goal["selected_release_source_workflows"] == {
        "linux-i386": ".github/workflows/extended-platform-evidence.yml",
        "linux-armhf": ".github/workflows/extended-platform-evidence.yml",
        "windows-xp-native-x86": ".github/workflows/xp-native-evidence.yml",
    }
    assert goal["release_source_run_attempts"] == {
        "linux-armhf": 1,
        "linux-i386": 1,
        "windows-xp-native-x64": 1,
        "windows-xp-native-x86": 1,
    }
    assert goal["selected_release_scope_exclusions"] == {
        "windows-xp-native-x64": [f"release-source-head:{'b' * 40}"]
    }
    assert goal["accepted_targets"] == [
        "linux-i386",
        "linux-armhf",
        "windows-xp-native-x86",
    ]
    assert goal["missing_targets"] == ["windows-xp-native-x64"]
    assert goal["complete"] is False
    assert goal["status"] == "mixed-release-source-evidence"


def test_platform_verified_readiness_ignores_release_asset_url_tag_mismatch() -> None:
    manifest = _extended_platform_manifest()
    record = _linux_accepted_evidence("linux-i386")
    record["release_asset_urls"][0] = record["release_asset_urls"][0].replace(
        "/releases/download/v1.0.2/",
        "/releases/download/v9.9.9/",
    )
    report = _platform_verified_readiness(
        platform_data=manifest,
        evidence_registry=_accepted_evidence_registry(record),
    )
    rows = {row["target"]: row for row in report["targets"]}

    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_malformed_release_asset_repository_slug() -> None:
    manifest = _extended_platform_manifest()
    record = _linux_accepted_evidence("linux-i386")
    record["release_asset_urls"][0] = record["release_asset_urls"][0].replace(
        "github.com/example/remote-ops-workspace/releases/",
        "github.com/example/remote-ops-workspace?download=1/releases/",
    )

    report = _platform_verified_readiness(
        platform_data=manifest,
        evidence_registry=_accepted_evidence_registry(record),
    )
    rows = {row["target"]: row for row in report["targets"]}

    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_nested_release_asset_url_filename() -> None:
    record = _linux_accepted_evidence("linux-i386")
    record["release_asset_urls"][0] = str(record["release_asset_urls"][0]).replace(
        "/releases/download/v1.0.2/",
        "/releases/download/v1.0.2/nested/",
    )

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_unfinalized_platform_candidate() -> None:
    manifest = _extended_platform_manifest()
    record = _linux_accepted_evidence("linux-i386")
    record.pop("review_bundle")

    report = _platform_verified_readiness(
        platform_data=manifest,
        evidence_registry=_accepted_evidence_registry(record),
    )
    rows = {row["target"]: row for row in report["targets"]}

    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["verified_readiness_scope"] is False
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_linux_workflow_repository_mismatch() -> None:
    manifest = _extended_platform_manifest()
    record = _linux_accepted_evidence("linux-i386")
    record["workflow_run_url"] = "https://github.com/other/remote-ops-workspace/actions/runs/12345"
    report = _platform_verified_readiness(
        platform_data=manifest,
        evidence_registry=_accepted_evidence_registry(record),
    )
    rows = {row["target"]: row for row in report["targets"]}

    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_linux_smoke_run_context_mismatch() -> None:
    manifest = _extended_platform_manifest()
    record = _linux_accepted_evidence("linux-i386")
    record["workflow_run_url"] = "https://github.com/example/remote-ops-workspace/actions/runs/67890"

    report = _platform_verified_readiness(
        platform_data=manifest,
        evidence_registry=_accepted_evidence_registry(record),
    )
    rows = {row["target"]: row for row in report["targets"]}

    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_linux_smoke_command_without_target_binding() -> None:
    record = _linux_accepted_evidence("linux-armhf")
    record["native_smoke_command"] = (
        "bash scripts/smoke_linux_native.sh --arch armhf --dist native-dist/linux "
        "--workflow-run-url https://github.com/example/remote-ops-workspace/actions/runs/12345"
    )

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-armhf"]["current_percent"] == 70.0
    assert rows["linux-armhf"]["status"] == "manual-script-supported"
    assert rows["linux-armhf"]["accepted_evidence_missing_targets"] == ["linux-armhf"]


def test_platform_verified_readiness_ignores_linux_workflow_input_mismatch() -> None:
    manifest = _extended_platform_manifest()
    record = _linux_accepted_evidence("linux-i386")
    record["workflow_inputs"]["release_asset_base_url"] = (
        "https://github.com/example/remote-ops-workspace/releases/download/v9.9.9"
    )
    report = _platform_verified_readiness(
        platform_data=manifest,
        evidence_registry=_accepted_evidence_registry(record),
    )
    rows = {row["target"]: row for row in report["targets"]}

    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_linux_workflow_input_trailing_slash_base_url() -> None:
    manifest = _extended_platform_manifest()
    record = _linux_accepted_evidence("linux-i386")
    record["workflow_inputs"]["release_asset_base_url"] = (
        "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/"
    )
    report = _platform_verified_readiness(
        platform_data=manifest,
        evidence_registry=_accepted_evidence_registry(record),
    )
    rows = {row["target"]: row for row in report["targets"]}

    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_mixed_release_repositories() -> None:
    manifest = _extended_platform_manifest()
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["release_asset_urls"][0] = record["release_asset_urls"][0].replace(
        "github.com/example/remote-ops-workspace",
        "github.com/other/remote-ops-workspace",
    )
    report = _platform_verified_readiness(
        platform_data=manifest,
        evidence_registry=_accepted_evidence_registry(record),
    )
    rows = {row["target"]: row for row in report["targets"]}

    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_xp_workflow_input_trailing_slash_base_url() -> None:
    manifest = _extended_platform_manifest()
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["workflow_inputs"]["release_asset_base_url"] = (
        "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/"
    )
    report = _platform_verified_readiness(
        platform_data=manifest,
        evidence_registry=_accepted_evidence_registry(record),
    )
    rows = {row["target"]: row for row in report["targets"]}

    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_missing_review_bundle_release_asset_urls() -> None:
    record = _linux_accepted_evidence("linux-i386")
    del record["review_bundle"]["release_asset_urls"]

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_extra_review_bundle_metadata() -> None:
    record = _linux_accepted_evidence("linux-i386")
    record["review_bundle"]["notes"] = "manual copy"

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_extra_review_bundle_file_metadata() -> None:
    record = _linux_accepted_evidence("linux-armhf")
    record["review_bundle"]["manifest"]["path"] = "review/manifest.json"

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-armhf"]["current_percent"] == 70.0
    assert rows["linux-armhf"]["status"] == "manual-script-supported"
    assert rows["linux-armhf"]["accepted_evidence_missing_targets"] == ["linux-armhf"]


def test_platform_verified_readiness_ignores_extra_xp_review_bundle_file_metadata() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["review_bundle"]["archive"]["path"] = "review/archive.zip"

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_nested_review_bundle_release_asset_url() -> None:
    record = _linux_accepted_evidence("linux-armhf")
    record["review_bundle"]["release_asset_urls"][0] = str(
        record["review_bundle"]["release_asset_urls"][0]
    ).replace(
        "/releases/download/v1.0.2/",
        "/releases/download/v1.0.2/nested/",
    )

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-armhf"]["current_percent"] == 70.0
    assert rows["linux-armhf"]["status"] == "manual-script-supported"
    assert rows["linux-armhf"]["accepted_evidence_missing_targets"] == ["linux-armhf"]


def test_platform_verified_readiness_ignores_boolean_review_bundle_size() -> None:
    record = _linux_accepted_evidence("linux-i386")
    record["review_bundle"]["manifest"]["size_bytes"] = True

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_missing_final_record_release_asset_url() -> None:
    record = _linux_accepted_evidence("linux-i386")
    del record["finalized_record_release_asset_url"]

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_nested_final_record_release_asset_url() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["finalized_record_release_asset_url"] = str(
        record["finalized_record_release_asset_url"]
    ).replace(
        "/releases/download/v1.0.2/",
        "/releases/download/v1.0.2/nested/",
    )

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_missing_release_asset_source() -> None:
    record = _linux_accepted_evidence("linux-i386")
    del record["release_asset_source"]

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_missing_release_source_run_attempt() -> None:
    record = _linux_accepted_evidence("linux-i386")
    del record["release_asset_source"]["run_attempt"]

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_invalid_release_source_run_attempt() -> None:
    record = _linux_accepted_evidence("linux-i386")
    record["release_asset_source"]["run_attempt"] = 0

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_release_asset_source_file_drift() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["release_asset_source"]["contains_files"].append("unexpected.zip")

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_release_asset_source_workflow_drift() -> None:
    record = _linux_accepted_evidence("linux-i386")
    record["release_asset_source"]["workflow"] = ".github/workflows/xp-native-evidence.yml"

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_builder_identity_source_head_sha_mismatch() -> None:
    record = _linux_accepted_evidence("linux-i386")
    record["builder_identity"]["source_head_sha"] = "b" * 40
    record["builder_identity_sha256"] = _json_sha256(record["builder_identity"])

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_builder_identity_workflow_provenance_mismatch() -> None:
    record = _linux_accepted_evidence("linux-i386")
    record["builder_identity"]["workflow_ref"] = (
        f"example/remote-ops-workspace/.github/workflows/ci.yml@{'a' * 40}"
    )
    record["builder_identity_sha256"] = _json_sha256(record["builder_identity"])
    record["linux_evidence_sources"]["builder_identity"]["sha256"] = record["builder_identity_sha256"]

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_builder_identity_observed_git_head_sha_mismatch() -> None:
    record = _linux_accepted_evidence("linux-i386")
    record["builder_identity"]["observed_git_head_sha"] = "b" * 40
    record["builder_identity_sha256"] = _json_sha256(record["builder_identity"])

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_dirty_builder_git_worktree() -> None:
    record = _linux_accepted_evidence("linux-i386")
    record["builder_identity"]["git_worktree_clean"] = False
    record["builder_identity_sha256"] = _json_sha256(record["builder_identity"])

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_missing_linux_runtime_identity() -> None:
    record = _linux_accepted_evidence("linux-i386")
    del record["builder_identity"]["os_release"]
    record["builder_identity"]["glibc_version"] = ""
    record["builder_identity_sha256"] = _json_sha256(record["builder_identity"])

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_unexpected_linux_builder_identity_fields() -> None:
    record = _linux_accepted_evidence("linux-i386")
    record["builder_identity"]["hostname"] = "private-builder"
    record["builder_identity"]["scratch_note"] = "manual copy"
    record["builder_identity"]["host_identity"]["runner_name"] = "private-runner"
    record["builder_identity"]["required_tools"]["home_dir"] = "/home/private-user"
    record["builder_identity"]["security_patch_evidence"]["operator_note"] = "manual review"
    record["builder_identity_sha256"] = _json_sha256(record["builder_identity"])
    record["linux_evidence_sources"]["builder_identity"]["sha256"] = record["builder_identity_sha256"]

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_linux_unexpected_top_level_fields() -> None:
    record = _linux_accepted_evidence("linux-i386")
    record["_source_files"] = ["native-dist/linux/private-builder-output.log"]

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    goal = report["protected_goal_parity"]
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]
    assert goal["current_percent"] == 0.0
    assert goal["accepted_targets"] == []


def test_platform_verified_readiness_ignores_unexpected_linux_evidence_check() -> None:
    record = _linux_accepted_evidence("linux-i386")
    record["checks"].append("manual_override")

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    goal = report["protected_goal_parity"]
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]
    assert goal["current_percent"] == 0.0
    assert goal["accepted_targets"] == []


def test_platform_verified_readiness_ignores_review_bundle_repository_mismatch() -> None:
    record = _linux_accepted_evidence("linux-armhf")
    record["review_bundle"]["release_asset_urls"] = [
        str(url).replace("github.com/example/remote-ops-workspace", "github.com/other/remote-ops-workspace")
        for url in record["review_bundle"]["release_asset_urls"]
    ]

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-armhf"]["current_percent"] == 70.0
    assert rows["linux-armhf"]["status"] == "manual-script-supported"
    assert rows["linux-armhf"]["accepted_evidence_missing_targets"] == ["linux-armhf"]


def test_platform_verified_readiness_ignores_final_record_release_asset_url_repository_drift() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["finalized_record_release_asset_url"] = str(
        record["finalized_record_release_asset_url"]
    ).replace("github.com/example/remote-ops-workspace", "github.com/other/remote-ops-workspace")

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_xp_unexpected_top_level_fields() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["operator_notes"] = "local lab scratch notes must stay out of accepted evidence"

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    goal = report["protected_goal_parity"]
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []
    assert rows["Windows XP"]["accepted_evidence_missing_targets"] == [
        "windows-xp-native-x86",
        "windows-xp-native-x64",
    ]
    assert goal["current_percent"] == 0.0
    assert goal["accepted_targets"] == []


def test_platform_verified_readiness_ignores_duplicate_xp_evidence_check() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["checks"].append("artifact_validation")

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    goal = report["protected_goal_parity"]
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []
    assert rows["Windows XP"]["accepted_evidence_missing_targets"] == [
        "windows-xp-native-x86",
        "windows-xp-native-x64",
    ]
    assert goal["current_percent"] == 0.0
    assert goal["accepted_targets"] == []


def test_platform_verified_readiness_ignores_artifact_validation_command_tag_mismatch() -> None:
    manifest = _extended_platform_manifest()
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["artifact_validation_command"] = record["artifact_validation_command"].replace(
        "--tag v1.0.2",
        "--tag v9.9.9",
    )
    report = _platform_verified_readiness(
        platform_data=manifest,
        evidence_registry=_accepted_evidence_registry(record),
    )
    rows = {row["target"]: row for row in report["targets"]}

    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_duplicate_artifact_validation_tag() -> None:
    record = _linux_accepted_evidence("linux-i386")
    record["artifact_validation_command"] = (
        "python scripts/check_platform_promotion_artifacts.py --target linux-i386 "
        "--assets-dir staged/linux-i386/v1.0.2/artifacts --tag v1.0.2 --strict --tag v9.9.9"
    )

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_missing_artifact_validation_strict() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["artifact_validation_command"] = str(record["artifact_validation_command"]).replace(
        " --strict",
        "",
    )

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_unexpected_artifact_validation_flag() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x64")
    record["artifact_validation_command"] = f"{record['artifact_validation_command']} --dry-run"

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_placeholder_artifact_validation_assets_dir() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["artifact_validation_command"] = (
        "python scripts/check_platform_promotion_artifacts.py --target windows-xp-native-x86 "
        "--assets-dir <artifact-dir> --tag v1.0.2 --strict"
    )

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_unscoped_xp_artifact_validation_assets_dir() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["artifact_validation_command"] = (
        "python scripts/check_platform_promotion_artifacts.py --target windows-xp-native-x86 "
        "--assets-dir native-dist/windows-xp --tag v1.0.2 --strict"
    )

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_missing_local_evidence_preflight_command() -> None:
    record = _linux_accepted_evidence("linux-i386")
    del record["local_evidence_preflight_command"]

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_missing_staged_upload_command() -> None:
    record = _linux_accepted_evidence("linux-i386")
    del record["staged_upload_command"]

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_overlapping_linux_staged_upload_command() -> None:
    record = _linux_accepted_evidence("linux-i386")
    record["staged_upload_command"] = str(record["staged_upload_command"]).replace(
        "--out-dir platform-evidence-upload/linux-i386/v1.0.2",
        "--out-dir staged/linux-i386/v1.0.2/artifacts/linux-evidence-upload",
    )

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_unscoped_linux_staged_upload_out_dir() -> None:
    record = _linux_accepted_evidence("linux-i386")
    record["staged_upload_command"] = str(record["staged_upload_command"]).replace(
        "--out-dir platform-evidence-upload/linux-i386/v1.0.2",
        "--out-dir platform-evidence-upload/linux-i386",
    )

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_overlapping_xp_staged_upload_command() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x64")
    record["staged_upload_command"] = str(record["staged_upload_command"]).replace(
        "--out-dir platform-evidence-upload/windows-xp-native-x64/v1.0.2",
        "--out-dir xp-evidence-output/windows-xp-native-x64/v1.0.2/upload",
    )

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_missing_targets"] == [
        "windows-xp-native-x86",
        "windows-xp-native-x64",
    ]


def test_platform_verified_readiness_ignores_unscoped_xp_staged_upload_out_dir() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["staged_upload_command"] = str(record["staged_upload_command"]).replace(
        "--out-dir platform-evidence-upload/windows-xp-native-x86/v1.0.2",
        "--out-dir platform-evidence-upload/v1.0.2",
    )

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_missing_targets"] == [
        "windows-xp-native-x86",
        "windows-xp-native-x64",
    ]


def test_platform_verified_readiness_ignores_linux_local_preflight_source_sha_drift() -> None:
    record = _linux_accepted_evidence("linux-armhf")
    record["local_evidence_preflight_command"] = str(
        record["local_evidence_preflight_command"]
    ).replace(f"--linux-source-head-sha {'a' * 40}", f"--linux-source-head-sha {'b' * 40}")

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-armhf"]["current_percent"] == 70.0
    assert rows["linux-armhf"]["status"] == "manual-script-supported"
    assert rows["linux-armhf"]["accepted_evidence_missing_targets"] == ["linux-armhf"]


def test_platform_verified_readiness_ignores_linux_local_preflight_allow_extra_artifacts() -> None:
    record = _linux_accepted_evidence("linux-i386")
    record["local_evidence_preflight_command"] = (
        f"{record['local_evidence_preflight_command']} --allow-extra-artifacts"
    )

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_unexpected_linux_local_preflight_flag() -> None:
    record = _linux_accepted_evidence("linux-armhf")
    record["local_evidence_preflight_command"] = (
        f"{record['local_evidence_preflight_command']} --dry-run"
    )

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-armhf"]["current_percent"] == 70.0
    assert rows["linux-armhf"]["status"] == "manual-script-supported"
    assert rows["linux-armhf"]["accepted_evidence_missing_targets"] == ["linux-armhf"]


def test_platform_verified_readiness_accepts_scoped_linux_local_preflight_root() -> None:
    target = "linux-i386"
    record = _linux_accepted_evidence(target)
    assets_dir = f"platform-evidence-staging/{target}/v1.0.2/artifacts"
    builder = f"platform-evidence-staging/{target}/v1.0.2/builder-identity-{target}.json"
    smoke = f"platform-evidence-staging/{target}/v1.0.2/native-smoke-{target}.log"
    record["artifact_validation_command"] = (
        f"python scripts/check_platform_promotion_artifacts.py --target {target} "
        f"--assets-dir {assets_dir} --tag v1.0.2 --strict"
    )
    record["staged_upload_command"] = (
        "python scripts/stage_extended_linux_evidence_upload.py "
        f"--target {target} --release-tag v1.0.2 --source-dir {assets_dir} "
        f"--out-dir platform-evidence-upload/{target}/v1.0.2 --force"
    )
    record["local_evidence_preflight_command"] = (
        "python scripts/check_platform_goal_local_evidence.py --root platform-evidence-staging "
        f"--release-tag v1.0.2 --target {target} --assets-dir {assets_dir} "
        "--repository example/remote-ops-workspace "
        f"--linux-builder-evidence {builder} "
        f"--linux-smoke-evidence {smoke} "
        "--linux-workflow-run-url https://github.com/example/remote-ops-workspace/actions/runs/12345 "
        f"--linux-source-head-sha {'a' * 40} "
        "--linux-source-run-attempt 1"
    )
    record["native_smoke_command"] = str(record["native_smoke_command"]).replace(
        f"evidence/{target}/v1.0.2/builder-identity-{target}.json",
        builder,
    )

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows[target]["current_percent"] == 100.0
    assert rows[target]["status"] == "verified-accepted-native-evidence"
    assert rows[target]["accepted_evidence_missing_targets"] == []


def test_platform_verified_readiness_rejects_linux_preflight_paths_outside_root() -> None:
    target = "linux-i386"
    record = _linux_accepted_evidence(target)
    record["local_evidence_preflight_command"] = str(
        record["local_evidence_preflight_command"]
    ).replace("--root .", "--root platform-evidence-staging")

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows[target]["current_percent"] == 70.0
    assert rows[target]["status"] == "manual-script-supported"
    assert rows[target]["accepted_evidence_missing_targets"] == [target]


def test_platform_verified_readiness_rejects_file_shaped_local_preflight_root() -> None:
    target = "linux-i386"
    record = _linux_accepted_evidence(target)
    assets_dir = f"platform-evidence.zip/{target}/v1.0.2/artifacts"
    builder = f"platform-evidence.zip/{target}/v1.0.2/builder-identity-{target}.json"
    smoke = f"platform-evidence.zip/{target}/v1.0.2/native-smoke-{target}.log"
    record["artifact_validation_command"] = (
        f"python scripts/check_platform_promotion_artifacts.py --target {target} "
        f"--assets-dir {assets_dir} --tag v1.0.2 --strict"
    )
    record["local_evidence_preflight_command"] = (
        "python scripts/check_platform_goal_local_evidence.py --root platform-evidence.zip "
        f"--release-tag v1.0.2 --target {target} --assets-dir {assets_dir} "
        f"--linux-builder-evidence {builder} "
        f"--linux-smoke-evidence {smoke} "
        "--linux-workflow-run-url https://github.com/example/remote-ops-workspace/actions/runs/12345 "
        f"--linux-source-head-sha {'a' * 40} "
        "--linux-source-run-attempt 1"
    )

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows[target]["current_percent"] == 70.0
    assert rows[target]["status"] == "manual-script-supported"
    assert rows[target]["accepted_evidence_missing_targets"] == [target]


def test_platform_verified_readiness_rejects_unscoped_linux_artifact_validation_assets_dir() -> None:
    target = "linux-i386"
    record = _linux_accepted_evidence(target)
    record["artifact_validation_command"] = (
        f"python scripts/check_platform_promotion_artifacts.py --target {target} "
        "--assets-dir native-dist/linux --tag v1.0.2 --strict"
    )
    record["local_evidence_preflight_command"] = str(
        record["local_evidence_preflight_command"]
    ).replace(f"--assets-dir staged/{target}/v1.0.2/artifacts", "--assets-dir native-dist/linux")

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows[target]["current_percent"] == 70.0
    assert rows[target]["status"] == "manual-script-supported"
    assert rows[target]["accepted_evidence_missing_targets"] == [target]


def test_platform_verified_readiness_ignores_xp_local_preflight_path_drift() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["local_evidence_preflight_command"] = str(
        record["local_evidence_preflight_command"]
    ).replace(
        "--xp-evidence-dir evidence/windows-xp-native-x86/v1.0.2",
        "--xp-evidence-dir evidence/windows-xp-native-x86/v1.0.2/other",
    )

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_xp_local_preflight_missing_source_binding() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["local_evidence_preflight_command"] = str(
        record["local_evidence_preflight_command"]
    ).replace(
        " --xp-source-workflow-run-url https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "",
    )

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_xp_local_preflight_source_sha_drift() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x64")
    record["local_evidence_preflight_command"] = str(
        record["local_evidence_preflight_command"]
    ).replace(f"--xp-source-head-sha {'a' * 40}", f"--xp-source-head-sha {'b' * 40}")

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_unexpected_xp_local_preflight_flag() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x64")
    record["local_evidence_preflight_command"] = (
        f"{record['local_evidence_preflight_command']} --dry-run"
    )

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_wrong_linux_artifact_name() -> None:
    record = _linux_accepted_evidence("linux-armhf")
    record["artifact_name"] = "extended-linux-evidence-linux-i386-v1.0.2"

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-armhf"]["current_percent"] == 70.0
    assert rows["linux-armhf"]["status"] == "manual-script-supported"
    assert rows["linux-armhf"]["accepted_evidence_missing_targets"] == ["linux-armhf"]


def test_platform_verified_readiness_ignores_missing_linux_command_provenance() -> None:
    record = _linux_accepted_evidence("linux-i386")
    del record["native_build_command"]
    del record["native_smoke_command"]

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_missing_linux_security_patch_evidence() -> None:
    record = _linux_accepted_evidence("linux-i386")
    del record["builder_identity"]["security_patch_evidence"]
    record["builder_identity_sha256"] = _json_sha256(record["builder_identity"])

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_boolean_linux_builder_schema_versions() -> None:
    record = _linux_accepted_evidence("linux-i386")
    record["builder_identity"]["schema_version"] = True
    record["builder_identity"]["host_identity"]["schema_version"] = True
    record["builder_identity_sha256"] = _json_sha256(record["builder_identity"])

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_placeholder_linux_security_patch_provenance() -> None:
    record = _linux_accepted_evidence("linux-i386")
    record["builder_identity"]["security_patch_evidence"]["security_update_channel"] = "test-security-update-channel"
    record["builder_identity"]["security_patch_evidence"]["cve_review_reference"] = "<replace-with-real-cve-review>"
    record["builder_identity_sha256"] = _json_sha256(record["builder_identity"])

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_vague_linux_security_patch_provenance() -> None:
    record = _linux_accepted_evidence("linux-i386")
    record["builder_identity"]["security_patch_evidence"]["security_update_channel"] = "monthly maintenance baseline"
    record["builder_identity"]["security_patch_evidence"]["cve_review_reference"] = "internal review 2026 06"
    record["builder_identity_sha256"] = _json_sha256(record["builder_identity"])

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_reserved_https_linux_security_patch_provenance() -> None:
    record = _linux_accepted_evidence("linux-i386")
    record["builder_identity"]["security_patch_evidence"][
        "security_update_channel"
    ] = "https://example.com/security-updates/linux-i386"
    record["builder_identity"]["security_patch_evidence"][
        "cve_review_reference"
    ] = "https://example.com/security-advisory/CVE-2026-0001"
    record["builder_identity_sha256"] = _json_sha256(record["builder_identity"])

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_generic_https_linux_security_patch_cve_reference() -> None:
    record = _linux_accepted_evidence("linux-i386")
    cve_review_reference = "https://security.vendor.com/releases/2026-07"
    record["builder_identity"]["security_patch_evidence"]["cve_review_reference"] = cve_review_reference
    summary = record["linux_smoke_summary"]
    assert isinstance(summary, dict)
    security = summary["security"]
    assert isinstance(security, dict)
    security["cve_review_reference"] = cve_review_reference
    record["builder_identity_sha256"] = _json_sha256(record["builder_identity"])

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_weak_linux_tool_path() -> None:
    record = _linux_accepted_evidence("linux-i386")
    record["builder_identity"]["required_tools"]["bash"] = "bash"
    record["builder_identity_sha256"] = _json_sha256(record["builder_identity"])

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_missing_noninteractive_sudo() -> None:
    record = _linux_accepted_evidence("linux-i386")
    del record["builder_identity"]["sudo_non_interactive"]
    record["builder_identity_sha256"] = _json_sha256(record["builder_identity"])

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_builder_identity_release_context_mismatch() -> None:
    record = _linux_accepted_evidence("linux-i386")
    record["builder_identity"]["release_tag"] = "v9.9.9"
    record["builder_identity"]["workflow_run_url"] = "https://github.com/example/remote-ops-workspace/actions/runs/99999"
    record["builder_identity_sha256"] = _json_sha256(record["builder_identity"])

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_boolean_linux_builder_run_attempts() -> None:
    record = _linux_accepted_evidence("linux-armhf")
    record["builder_identity"]["workflow_run_attempt"] = True
    record["builder_identity"]["host_identity"]["workflow_run_attempt"] = True
    record["builder_identity_sha256"] = _json_sha256(record["builder_identity"])

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-armhf"]["current_percent"] == 70.0
    assert rows["linux-armhf"]["status"] == "manual-script-supported"
    assert rows["linux-armhf"]["accepted_evidence_missing_targets"] == ["linux-armhf"]


def test_platform_verified_readiness_ignores_missing_linux_smoke_evidence() -> None:
    record = _linux_accepted_evidence("linux-i386")
    del record["linux_smoke_evidence_sha256"]

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_missing_linux_smoke_summary() -> None:
    record = _linux_accepted_evidence("linux-i386")
    del record["linux_smoke_summary"]

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    goal = report["protected_goal_parity"]
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]
    assert goal["current_percent"] == 0.0
    assert goal["accepted_targets"] == []


def test_platform_verified_readiness_ignores_weak_linux_smoke_summary_security() -> None:
    record = _linux_accepted_evidence("linux-i386")
    summary = record["linux_smoke_summary"]
    assert isinstance(summary, dict)
    security = summary["security"]
    assert isinstance(security, dict)
    security["weak_crypto_global_default"] = True

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    goal = report["protected_goal_parity"]
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]
    assert goal["current_percent"] == 0.0
    assert goal["accepted_targets"] == []


def test_platform_verified_readiness_ignores_boolean_linux_smoke_summary_run_attempt() -> None:
    record = _linux_accepted_evidence("linux-i386")
    record["linux_smoke_summary"]["workflow_run_attempt"] = True

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    goal = report["protected_goal_parity"]
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]
    assert goal["current_percent"] == 0.0
    assert goal["accepted_targets"] == []


def test_platform_verified_readiness_ignores_vague_linux_smoke_summary_security_provenance() -> None:
    record = _linux_accepted_evidence("linux-i386")
    summary = record["linux_smoke_summary"]
    assert isinstance(summary, dict)
    security = summary["security"]
    assert isinstance(security, dict)
    security["security_update_channel"] = "monthly maintenance baseline"
    security["cve_review_reference"] = "internal review 2026 06"

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    goal = report["protected_goal_parity"]
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]
    assert goal["current_percent"] == 0.0
    assert goal["accepted_targets"] == []


def test_platform_verified_readiness_ignores_missing_linux_evidence_sources() -> None:
    record = _linux_accepted_evidence("linux-i386")
    del record["linux_evidence_sources"]

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_boolean_linux_evidence_source_size() -> None:
    record = _linux_accepted_evidence("linux-armhf")
    record["linux_evidence_sources"]["builder_identity"]["size_bytes"] = True

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-armhf"]["current_percent"] == 70.0
    assert rows["linux-armhf"]["status"] == "manual-script-supported"
    assert rows["linux-armhf"]["accepted_evidence_missing_targets"] == ["linux-armhf"]


def test_platform_verified_readiness_ignores_wrong_xp_native_validation_command() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["native_evidence_validation_command"] = "python scripts/check_xp_native_evidence.py --help"

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_xp_native_validation_contract_flag() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x64")
    record["native_evidence_validation_command"] = (
        f"{record['native_evidence_validation_command']} --contract"
    )

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_unsafe_xp_native_validation_command_path() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["native_evidence_validation_command"] = (
        "python scripts/check_xp_native_evidence.py "
        "--evidence evidence/windows-xp-native-x86/v1.0.2/xp-evidence.json "
        "--assets-dir native-dist/windows-xp/windows-xp-native-x86/v1.0.2 "
        "--evidence-dir staged/windows-xp-native-x86/v1.0.2/.private-smoke"
    )

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_unscoped_xp_native_validation_command_path() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["native_evidence_validation_command"] = (
        "python scripts/check_xp_native_evidence.py "
        "--evidence evidence/windows-xp-native-x86/xp-evidence.json "
        "--assets-dir native-dist/windows-xp "
        "--evidence-dir evidence/windows-xp-native-x86/smoke"
    )

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_wrong_xp_workflow() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["workflow"] = ".github/workflows/ci.yml"

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_missing_xp_workflow_inputs() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    del record["workflow_inputs"]

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_xp_workflow_input_path_drift() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["workflow_inputs"]["assets_dir"] = "native-dist/windows-xp/windows-xp-native-x86/v1.0.3"

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_missing_xp_evidence_sources() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    del record["xp_evidence_sources"]

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_xp_evidence_source_hash_drift() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["xp_evidence_sources"]["smoke_evidence"]["cli_launch"]["sha256"] = "9" * 64

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_boolean_xp_evidence_source_sizes() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x64")
    record["xp_evidence_sources"]["evidence"]["size_bytes"] = True
    record["xp_evidence_sources"]["smoke_evidence"]["cli_launch"]["size_bytes"] = True

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_stale_xp_evidence_contract_hash() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["xp_evidence_contract_sha256"] = "0" * 64

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_mismatched_xp_evidence_summary() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["xp_evidence_summary"]["target"] = "windows-xp-native-x64"

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_xp_evidence_summary_release_source_mismatch() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["xp_evidence_summary"]["release_source"]["head_sha"] = "b" * 40

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_unexpected_xp_evidence_summary_fields() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    summary = record["xp_evidence_summary"]
    summary["operator_note"] = "manual copy"
    summary["release_source"]["scratch"] = "manual"
    summary["os"]["computer_name"] = "private-xp-host"
    summary["toolchain"]["tool_path"] = "C:\\private\\toolchain"
    summary["security"]["operator_note"] = "manual review"
    summary["security"]["patch_evidence"]["operator_note"] = "manual review"
    summary["host_identity"]["runner_name"] = "private-runner"
    summary["host_identity"]["os"]["hostname"] = "private-xp-host"
    summary["host_identity"]["toolchain"]["builder_user"] = "private-user"
    record["xp_host_identity_sha256"] = _json_sha256(summary["host_identity"])

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_boolean_xp_host_identity_schema_version() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x64")
    host_identity = record["xp_evidence_summary"]["host_identity"]
    host_identity["schema_version"] = True
    record["xp_host_identity_sha256"] = _json_sha256(host_identity)

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_missing_xp_smoke_commands() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    del record["xp_evidence_summary"]["smoke_commands"]

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_missing_xp_smoke_evidence_files() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    del record["xp_evidence_summary"]["smoke_evidence_files"]

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_placeholder_xp_smoke_command() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["xp_evidence_summary"]["smoke_commands"]["cli_launch"] = "<command>"

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_xp_smoke_command_target_mismatch() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["xp_evidence_summary"]["smoke_commands"]["cli_launch"] = (
        "scripts/xp_smoke_runner.cmd --target windows-xp-native-x64 --release-tag v1.0.2 "
        "--smoke-id cli_launch --evidence-file xp-smoke-evidence/cli_launch.txt "
        "--proof-file xp-smoke-proof/cli_launch.txt"
    )

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_xp_smoke_command_evidence_file_mismatch() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["xp_evidence_summary"]["smoke_commands"]["cli_launch"] = (
        "scripts/xp_smoke_runner.cmd --target windows-xp-native-x86 --release-tag v1.0.2 "
        "--smoke-id cli_launch --evidence-file xp-smoke-evidence/other.txt "
        "--proof-file xp-smoke-proof/cli_launch.txt"
    )

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_xp_smoke_evidence_file_path_mismatch() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["xp_evidence_summary"]["smoke_evidence_files"]["cli_launch"] = "logs/cli_launch.txt"
    record["xp_evidence_summary"]["smoke_commands"]["cli_launch"] = (
        "scripts/xp_smoke_runner.cmd --target windows-xp-native-x86 --release-tag v1.0.2 "
        "--smoke-id cli_launch --evidence-file logs/cli_launch.txt "
        "--proof-file xp-smoke-proof/cli_launch.txt"
    )

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_xp_smoke_command_proof_file_mismatch() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["xp_evidence_summary"]["smoke_commands"]["cli_launch"] = (
        "scripts/xp_smoke_runner.cmd --target windows-xp-native-x86 --release-tag v1.0.2 "
        "--smoke-id cli_launch --evidence-file xp-smoke-evidence/cli_launch.txt "
        "--proof-file xp-smoke-proof/other.txt"
    )

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_xp_smoke_command_source_head_mismatch() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["xp_evidence_summary"]["smoke_commands"]["cli_launch"] = record["xp_evidence_summary"][
        "smoke_commands"
    ]["cli_launch"].replace(
        "--source-head-sha aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "--source-head-sha bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    )

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_xp_smoke_command_observed_at_mismatch() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["xp_evidence_summary"]["smoke_commands"]["cli_launch"] = record["xp_evidence_summary"][
        "smoke_commands"
    ]["cli_launch"].replace(
        "--observed-at-utc 2026-06-20T12:00:00Z",
        "--observed-at-utc 2026-06-20T12:30:00Z",
    )

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_weak_xp_x64_summary() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x64")
    record["xp_evidence_summary"]["os"] = {
        "name": "Windows XP",
        "architecture": "x64",
        "service_pack": "x64",
    }

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_xp_security_smoke_command_provenance_mismatch() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["xp_evidence_summary"]["smoke_commands"]["modern_defaults_unchanged"] = record["xp_evidence_summary"][
        "smoke_commands"
    ]["modern_defaults_unchanged"].replace(
        "--security-update-channel vendor-security-updates-2026-06",
        "--security-update-channel stale-security-channel",
    )

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_missing_xp_security_patch_summary() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    del record["xp_evidence_summary"]["security"]["patch_evidence"]

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_placeholder_xp_security_patch_summary() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["xp_evidence_summary"]["security"]["patch_evidence"]["security_update_channel"] = "test-security"
    record["xp_evidence_summary"]["security"]["patch_evidence"]["cve_review_reference"] = "TODO"

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_vague_xp_security_patch_summary() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["xp_evidence_summary"]["security"]["patch_evidence"]["security_update_channel"] = "monthly maintenance baseline"
    record["xp_evidence_summary"]["security"]["patch_evidence"]["cve_review_reference"] = "internal review 2026 06"

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_reserved_https_xp_security_patch_summary() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["xp_evidence_summary"]["security"]["patch_evidence"][
        "security_update_channel"
    ] = "https://example.com/security-updates/windows-xp"
    record["xp_evidence_summary"]["security"]["patch_evidence"][
        "cve_review_reference"
    ] = "https://example.com/security-advisory/CVE-2026-0001"

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_generic_https_xp_security_patch_cve_reference() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["xp_evidence_summary"]["security"]["patch_evidence"][
        "cve_review_reference"
    ] = "https://security.vendor.com/releases/2026-07"

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_missing_xp_host_identity_summary() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    del record["xp_evidence_summary"]["host_identity"]

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_incomplete_artifact_set() -> None:
    manifest = _extended_platform_manifest()
    record = _linux_accepted_evidence("linux-armhf")
    removed_url = record["release_asset_urls"].pop()
    del record["artifact_sha256"][Path(removed_url).name]
    report = _platform_verified_readiness(
        platform_data=manifest,
        evidence_registry=_accepted_evidence_registry(record),
    )
    rows = {row["target"]: row for row in report["targets"]}

    assert rows["linux-armhf"]["current_percent"] == 70.0
    assert rows["linux-armhf"]["status"] == "manual-script-supported"
    assert rows["linux-armhf"]["accepted_evidence_missing_targets"] == ["linux-armhf"]


def test_platform_verified_readiness_ignores_malformed_artifact_hash() -> None:
    record = _linux_accepted_evidence("linux-i386")
    first_name = Path(record["release_asset_urls"][0]).name
    record["artifact_sha256"][first_name] = "not-a-sha256"

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_unfinalized_linux_evidence() -> None:
    record = _linux_accepted_evidence("linux-i386")
    del record["finalized_record_release_asset_url"]
    source = record["release_asset_source"]
    assert isinstance(source, dict)
    source["contains_files"] = sorted(str(name) for name in record["artifact_sha256"])

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    goal = report["protected_goal_parity"]
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]
    assert goal["current_percent"] == 0.0
    assert goal["accepted_targets"] == []


def test_platform_verified_readiness_ignores_review_bundle_free_xp_evidence() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    del record["review_bundle"]

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    goal = report["protected_goal_parity"]
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []
    assert rows["Windows XP"]["accepted_evidence_missing_targets"] == [
        "windows-xp-native-x86",
        "windows-xp-native-x64",
    ]
    assert goal["current_percent"] == 0.0
    assert goal["accepted_targets"] == []


def test_platform_verified_readiness_ignores_duplicate_release_asset_urls() -> None:
    record = _linux_accepted_evidence("linux-armhf")
    record["release_asset_urls"].append(record["release_asset_urls"][0])

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-armhf"]["current_percent"] == 70.0
    assert rows["linux-armhf"]["status"] == "manual-script-supported"
    assert rows["linux-armhf"]["accepted_evidence_missing_targets"] == ["linux-armhf"]


def test_platform_verified_readiness_ignores_stale_promotion_config_hash() -> None:
    record = _linux_accepted_evidence("linux-i386")
    record["promotion_config_sha256"] = "0" * 64

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_stale_builder_identity_hash() -> None:
    record = _linux_accepted_evidence("linux-i386")
    record["builder_identity"]["python_version"] = "3.13.0"

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry=_accepted_evidence_registry(record),
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_extra_artifact_hashes() -> None:
    manifest = _extended_platform_manifest()
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["artifact_sha256"]["remote-ops-workspace-v1.0.2-windows-xp-x86-extra.zip"] = "3" * 64
    report = _platform_verified_readiness(
        platform_data=manifest,
        evidence_registry=_accepted_evidence_registry(record),
    )
    rows = {row["target"]: row for row in report["targets"]}

    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []
    assert rows["Windows XP"]["accepted_evidence_missing_targets"] == [
        "windows-xp-native-x86",
        "windows-xp-native-x64",
    ]


def _extended_platform_manifest() -> dict[str, object]:
    return {
        "release_architectures": [
            {
                "id": "linux-i386",
                "platform": "Linux",
                "cpu_arch": "i386",
                "release_tier": "script-supported-native",
                "github_release_channel": "manual-script-native",
            },
            {
                "id": "linux-armhf",
                "platform": "Linux",
                "cpu_arch": "armhf",
                "release_tier": "script-supported-native",
                "github_release_channel": "manual-script-native",
            },
        ],
        "windows_legacy_targets": [
            {
                "version": "Windows XP",
                "host_tier": "remote-target-only",
                "remote_target_tier": "supported",
                "remote_target_coverage_percent": 100.0,
                "architectures": ["x86", "x64"],
                "security_profile": "isolated-legacy-opt-in",
                "supported_remote_protocols": ["rdp"],
            }
        ],
    }


def _platform_verified_evidence_policy() -> str:
    registry = json.loads(Path("configs/platform_verified_evidence.json").read_text(encoding="utf-8"))
    policy = registry.get("policy")
    assert isinstance(policy, str)
    return policy


def _accepted_evidence_registry(*records: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": 1,
        "policy": _platform_verified_evidence_policy(),
        "accepted_evidence": list(records),
    }


def _linux_accepted_evidence(target: str) -> dict[str, object]:
    arch = "i386" if target == "linux-i386" else "armhf"
    rpm_arch = "i686" if target == "linux-i386" else "armv7hl"
    artifact_arch = "i686" if target == "linux-i386" else "armhf"
    assets_dir = f"staged/{target}/v1.0.2/artifacts"
    artifact = f"extended-linux-evidence-{target}-v1.0.2"
    base_url = "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2"
    release_asset_urls = [
        f"{base_url}/remote-ops-workspace-v1.0.2-linux-{arch}.deb",
        f"{base_url}/remote-ops-workspace-v1.0.2-linux-{rpm_arch}.rpm",
        f"{base_url}/remote-ops-workspace-v1.0.2-linux-{artifact_arch}.AppImage",
        f"{base_url}/remote-ops-workspace-v1.0.2-linux-{artifact_arch}-native.tar.gz",
        f"{base_url}/remote-ops-workspace-v1.0.2-linux-{artifact_arch}-native-manifest.json",
        f"{base_url}/remote-ops-workspace-v1.0.2-linux-{artifact_arch}-native-SHA256SUMS.txt",
    ]
    builder_identity = _builder_identity(target)
    builder_identity_sha = _json_sha256(builder_identity)
    linux_smoke_hashes = _linux_smoke_hashes()
    return {
        "target": target,
        "evidence_type": "extended-linux-native",
        "status": "accepted",
        "readiness_percent": 100.0,
        "release_tag": "v1.0.2",
        "promotion_config_sha256": _promotion_config_sha256(),
        "workflow": ".github/workflows/extended-platform-evidence.yml",
        "workflow_inputs": {
            "target": target,
            "release_tag": "v1.0.2",
            "release_asset_base_url": base_url,
        },
        "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "artifact_name": artifact,
        "runner_labels": ["self-hosted", "linux", arch],
        "builder_identity": builder_identity,
        "builder_identity_sha256": builder_identity_sha,
        "linux_evidence_sources": _linux_evidence_sources(
            target,
            builder_identity_sha,
            linux_smoke_hashes["native_smoke"],
        ),
        "native_build_command": (
            f"TARGET_ARCH={arch} PYTHON_BIN=.venv-native/bin/python bash scripts/make_linux_native.sh"
        ),
        "native_smoke_command": (
            f"bash scripts/smoke_linux_native.sh --arch {arch} --dist native-dist/linux "
            f"--target {target} --workflow-run-url https://github.com/example/remote-ops-workspace/actions/runs/12345 "
            f"--workflow-run-attempt 1 --source-head-sha {'a' * 40} "
            f"--builder-evidence evidence/{target}/v1.0.2/builder-identity-{target}.json"
        ),
        "linux_smoke_evidence_sha256": linux_smoke_hashes,
        "linux_smoke_summary": _linux_smoke_summary(target),
        "local_evidence_preflight_command": (
            "python scripts/check_platform_goal_local_evidence.py --root . "
            f"--release-tag v1.0.2 --target {target} --assets-dir {assets_dir} "
            "--repository example/remote-ops-workspace "
            f"--linux-builder-evidence evidence/{target}/v1.0.2/builder-identity-{target}.json "
            f"--linux-smoke-evidence evidence/{target}/v1.0.2/native-smoke-{target}.log "
            "--linux-workflow-run-url https://github.com/example/remote-ops-workspace/actions/runs/12345 "
            f"--linux-source-head-sha {'a' * 40} "
            "--linux-source-run-attempt 1"
        ),
        "staged_upload_command": (
            "python scripts/stage_extended_linux_evidence_upload.py "
            f"--target {target} --release-tag v1.0.2 --source-dir {assets_dir} "
            f"--out-dir platform-evidence-upload/{target}/v1.0.2 --force"
        ),
        "artifact_validation_command": (
            f"python scripts/check_platform_promotion_artifacts.py --target {target} "
            f"--assets-dir {assets_dir} --tag v1.0.2 --strict"
        ),
        "checks": [
            "builder_preflight",
            "native_build",
            "native_smoke",
            "artifact_validation",
            "release_asset_attachment",
        ],
        "release_asset_urls": release_asset_urls,
        "artifact_sha256": _artifact_hashes_from_urls(release_asset_urls),
        "finalized_record_release_asset_url": (
            f"{base_url}/platform-verified-evidence-{target}-final.json"
        ),
        "release_asset_source": _release_asset_source(target, artifact, release_asset_urls),
        "review_bundle": _review_bundle(target),
    }


def _xp_accepted_evidence(target: str) -> dict[str, object]:
    arch = "x86" if target.endswith("x86") else "x64"
    base_url = "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2"
    evidence_file = f"evidence/{target}/v1.0.2/xp-evidence.json"
    assets_dir = f"native-dist/windows-xp/{target}/v1.0.2"
    evidence_dir = f"evidence/{target}/v1.0.2"
    evidence_summary = _xp_evidence_summary(target)
    smoke_hashes = _xp_smoke_hashes()
    release_asset_urls = [
        f"{base_url}/remote-ops-workspace-v1.0.2-windows-xp-{arch}-native.zip",
        f"{base_url}/remote-ops-workspace-v1.0.2-windows-xp-{arch}-native-manifest.json",
        f"{base_url}/remote-ops-workspace-v1.0.2-windows-xp-{arch}-native-SHA256SUMS.txt",
    ]
    return {
        "target": target,
        "evidence_type": "windows-xp-native-host",
        "status": "accepted",
        "readiness_percent": 100.0,
        "release_tag": "v1.0.2",
        "promotion_config_sha256": _promotion_config_sha256(),
        "workflow": ".github/workflows/xp-native-evidence.yml",
        "workflow_inputs": {
            "target": target,
            "release_tag": "v1.0.2",
            "release_asset_base_url": base_url,
            "assets_dir": assets_dir,
            "evidence_file": evidence_file,
            "evidence_dir": evidence_dir,
        },
        "architecture": arch,
        "separate_legacy_toolchain": True,
        "current_python_pyqt6_stack": False,
        "xp_evidence_sha256": "b" * 64,
        "xp_evidence_contract_sha256": _xp_native_evidence_contract_sha256(),
        "xp_host_identity_sha256": _json_sha256(_xp_host_identity(target)),
        "xp_evidence_summary": evidence_summary,
        "xp_smoke_evidence_sha256": smoke_hashes,
        "xp_evidence_sources": _xp_evidence_sources(
            evidence_file,
            "b" * 64,
            evidence_summary,
            smoke_hashes,
        ),
        "native_evidence_validation_command": (
            "python scripts/check_xp_native_evidence.py "
            f"--evidence {evidence_file} "
            f"--assets-dir {assets_dir} "
            f"--evidence-dir {evidence_dir}"
        ),
        "local_evidence_preflight_command": (
            "python scripts/check_platform_goal_local_evidence.py --root . "
            f"--release-tag v1.0.2 --target {target} --assets-dir {assets_dir} "
            "--repository example/remote-ops-workspace "
            f"--xp-evidence {evidence_file} --xp-evidence-dir {evidence_dir} "
            "--xp-source-workflow-run-url https://github.com/example/remote-ops-workspace/actions/runs/12345 "
            f"--xp-source-head-sha {'a' * 40} "
            "--xp-source-run-attempt 1"
        ),
        "staged_upload_command": (
            "python scripts/stage_xp_native_evidence_upload.py "
            f"--target {target} --release-tag v1.0.2 --assets-dir {assets_dir} "
            f"--evidence-output-dir xp-evidence-output/{target}/v1.0.2 "
            f"--out-dir platform-evidence-upload/{target}/v1.0.2 --force"
        ),
        "artifact_validation_command": (
            f"python scripts/check_platform_promotion_artifacts.py --target {target} "
            f"--assets-dir {assets_dir} --tag v1.0.2 --strict"
        ),
        "checks": [
            "xp_native_evidence_validation",
            "artifact_validation",
            "vm_or_host_smoke",
            "legacy_crypto_profile_scoped",
            "modern_defaults_unchanged",
            "release_asset_attachment",
        ],
        "release_asset_urls": release_asset_urls,
        "artifact_sha256": _artifact_hashes_from_urls(release_asset_urls),
        "finalized_record_release_asset_url": (
            f"{base_url}/platform-verified-evidence-{target}-final.json"
        ),
        "release_asset_source": _release_asset_source(
            target,
            f"xp-native-evidence-{target}-v1.0.2",
            release_asset_urls,
        ),
        "review_bundle": _review_bundle(target),
    }


def _builder_identity(target: str) -> dict[str, object]:
    machine = "i686" if target == "linux-i386" else "armv7l"
    dpkg_arch = "i386" if target == "linux-i386" else "armhf"
    return {
        "schema_version": 1,
        "target": target,
        "release_tag": "v1.0.2",
        "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "workflow_run_attempt": 1,
        "workflow_ref": (
            "example/remote-ops-workspace/.github/workflows/"
            f"extended-platform-evidence.yml@{'a' * 40}"
        ),
        "workflow_sha": "a" * 40,
        "source_head_sha": "a" * 40,
        "observed_git_head_sha": "a" * 40,
        "git_worktree_clean": True,
        "host_identity": _linux_host_identity(target),
        "sudo_non_interactive": True,
        "sys_platform": "linux",
        "platform_machine": machine,
        "uname_machine": machine,
        "dpkg_architecture": dpkg_arch,
        "userland_bits": "32",
        "os_release": "Debian GNU/Linux 12 (bookworm)",
        "kernel_release": "6.1.0-i386-ci",
        "glibc_version": "glibc 2.36",
        "python_version": "3.12.0",
        "required_tools": {
            "bash": "/usr/bin/bash",
            "curl": "/usr/bin/curl",
            "dpkg": "/usr/bin/dpkg",
            "dpkg-deb": "/usr/bin/dpkg-deb",
            "getconf": "/usr/bin/getconf",
            "openssl": "/usr/bin/openssl",
            "rpm": "/usr/bin/rpm",
            "rpmbuild": "/usr/bin/rpmbuild",
            "sha256sum": "/usr/bin/sha256sum",
            "sudo": "/usr/bin/sudo",
            "tar": "/usr/bin/tar",
        },
        "security_patch_evidence": _security_patch_evidence(),
    }


def _linux_host_identity(target: str, release_tag: str = "v1.0.2") -> dict[str, object]:
    return {
        "schema_version": 1,
        "target": target,
        "release_tag": release_tag,
        "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "workflow_run_attempt": 1,
        "host_label": f"{target}-builder",
        "evidence_run_id": f"{target}-{release_tag.removeprefix('v').replace('.', '-')}-run-12345",
        "observed_at_utc": "2026-06-20T12:00:00Z",
        "operator_private_data_redacted": True,
    }


def _artifact_hashes_from_urls(urls: list[str]) -> dict[str, str]:
    return {Path(url).name: "a" * 64 for url in urls}


def _release_asset_source(
    target: str,
    artifact_name: str,
    release_asset_urls: list[str],
    release_tag: str = "v1.0.2",
) -> dict[str, object]:
    contains_files = {Path(url).name for url in release_asset_urls}
    review_bundle = _review_bundle(target, release_tag=release_tag)
    contains_files.update(
        str(record.get("file", ""))
        for record in (
            review_bundle["manifest"],
            review_bundle["archive"],
            review_bundle["sha256s"],
        )
        if isinstance(record, dict)
    )
    contains_files.add(f"platform-verified-evidence-{target}-final.json")
    return {
        "type": "github-actions-artifact",
        "workflow": _release_source_workflow(target),
        "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "artifact_name": artifact_name,
        "head_sha": "a" * 40,
        "run_attempt": 1,
        "contains_files": sorted(contains_files),
    }


def _release_source_workflow(target: str) -> str:
    if target.startswith("linux-"):
        return ".github/workflows/extended-platform-evidence.yml"
    return ".github/workflows/xp-native-evidence.yml"


def _linux_smoke_hashes() -> dict[str, str]:
    return {"native_smoke": "6" * 64}


def _linux_smoke_summary(target: str, release_tag: str = "v1.0.2") -> dict[str, object]:
    machine = "i686" if target == "linux-i386" else "armv7l"
    dpkg_arch = "i386" if target == "linux-i386" else "armhf"
    target_arch = "i386" if target == "linux-i386" else "armhf"
    return {
        "target": target,
        "release_tag": release_tag,
        "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "workflow_run_attempt": 1,
        "source_head_sha": "a" * 40,
        "git_head_sha": "a" * 40,
        "target_arch": target_arch,
        "host_label": f"{target}-builder",
        "evidence_run_id": f"{target}-{release_tag.removeprefix('v').replace('.', '-')}-run-12345",
        "observed_at_utc": "2026-06-20T12:00:00Z",
        "uname_machine": machine,
        "dpkg_architecture": dpkg_arch,
        "userland_bits": "32",
        "os_release": "Debian GNU/Linux 12 (bookworm)",
        "kernel_release": "6.1.0-i386-ci",
        "glibc_version": "glibc 2.36",
        "python_ssl_openssl": "OpenSSL 3.0.13",
        "openssl_cli_version": "OpenSSL 3.0.13",
        "security": {
            "tls_minimum_modern_profiles": "TLS 1.2",
            "tls_preferred_modern_profiles": "TLS 1.3",
            "legacy_compatibility_profile": "isolated-opt-in",
            "legacy_crypto_scope": "profile-only",
            "weak_crypto_global_default": False,
            "modern_defaults_unchanged": True,
            "security_update_channel": "vendor-security-updates-2026-06",
            "cve_review_reference": "vendor-cve-advisory-review-2026-06",
        },
    }


def _linux_evidence_sources(
    target: str,
    builder_identity_sha: str,
    native_smoke_sha: str,
) -> dict[str, object]:
    return {
        "builder_identity": {
            "file": f"builder-identity-{target}.json",
            "sha256": builder_identity_sha,
            "size_bytes": 123,
        },
        "native_smoke": {
            "file": f"native-smoke-{target}.log",
            "sha256": native_smoke_sha,
            "size_bytes": 456,
        },
    }


def _review_bundle(target: str, release_tag: str = "v1.0.2") -> dict[str, object]:
    if target.startswith("linux-"):
        stem = f"extended-linux-evidence-bundle-{target}-{release_tag}"
        bundle_type = "extended-linux-native-evidence"
    else:
        stem = f"xp-native-evidence-bundle-{target}-{release_tag}"
        bundle_type = "windows-xp-native-host-evidence"
    base_url = f"https://github.com/example/remote-ops-workspace/releases/download/{release_tag}"
    return {
        "bundle_type": bundle_type,
        "manifest": {"file": f"{stem}.json", "sha256": "3" * 64, "size_bytes": 123},
        "archive": {"file": f"{stem}.zip", "sha256": "4" * 64, "size_bytes": 456},
        "sha256s": {"file": f"{stem}-SHA256SUMS.txt", "sha256": "5" * 64, "size_bytes": 78},
        "release_asset_urls": [
            f"{base_url}/{stem}.json",
            f"{base_url}/{stem}.zip",
            f"{base_url}/{stem}-SHA256SUMS.txt",
        ],
    }


def _xp_evidence_summary(target: str) -> dict[str, object]:
    arch = "x86" if target.endswith("x86") else "x64"
    os_summary: dict[str, object] = {
        "name": "Windows XP",
        "architecture": arch,
        "service_pack": "SP3" if arch == "x86" else "SP2",
    }
    if arch == "x64":
        os_summary["edition"] = "Professional x64 Edition"
    return {
        "target": target,
        "release_tag": "v1.0.2",
        "host_identity": _xp_host_identity(target),
        "os": os_summary,
        "toolchain": {
            "separate_legacy_toolchain": True,
            "current_python_pyqt6_stack": False,
        },
        "release_source": _xp_release_source_summary(target),
        "security": {
            "legacy_crypto_profile_scoped": True,
            "modern_defaults_unchanged": True,
            "weak_crypto_global_default": False,
            "patch_evidence": _xp_security_patch_evidence(),
        },
        "smoke_ids": sorted(_xp_smoke_hashes()),
        "smoke_evidence_files": _xp_smoke_evidence_files(),
        "smoke_commands": _xp_smoke_commands(target),
    }


def _xp_release_source_summary(target: str) -> dict[str, object]:
    return {
        "workflow": _release_source_workflow(target),
        "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "head_sha": "a" * 40,
        "run_attempt": 1,
    }


def _xp_host_identity(target: str) -> dict[str, object]:
    arch = "x86" if target.endswith("x86") else "x64"
    os_summary: dict[str, object] = {
        "name": "Windows XP",
        "architecture": arch,
        "service_pack": "SP3" if arch == "x86" else "SP2",
    }
    if arch == "x64":
        os_summary["edition"] = "Professional x64 Edition"
    return {
        "schema_version": 1,
        "target": target,
        "release_tag": "v1.0.2",
        "host_label": f"xp-{arch}-lab-01",
        "evidence_run_id": f"xp-{arch}-1-0-2-20260620t120000z",
        "observed_at_utc": "2026-06-20T12:00:00Z",
        "operator_private_data_redacted": True,
        "os": os_summary,
        "toolchain": {
            "separate_legacy_toolchain": True,
            "current_python_pyqt6_stack": False,
            "description": "Separate legacy XP-capable native host toolchain",
        },
    }


def _xp_smoke_hashes() -> dict[str, str]:
    return {
        "cli_launch": "c" * 64,
        "gui_or_legacy_host_ui_launch": "d" * 64,
        "loopback_profile_dry_run": "e" * 64,
        "artifact_manifest_validation": "f" * 64,
        "legacy_crypto_profile_scoped": "1" * 64,
        "modern_defaults_unchanged": "2" * 64,
    }


def _xp_smoke_evidence_files() -> dict[str, str]:
    return {
        smoke_id: f"xp-smoke-evidence/{smoke_id}.txt"
        for smoke_id in sorted(_xp_smoke_hashes())
    }


def _xp_evidence_sources(
    evidence_file: str,
    evidence_sha: str,
    evidence_summary: dict[str, object],
    smoke_hashes: dict[str, str],
) -> dict[str, object]:
    smoke_files = evidence_summary["smoke_evidence_files"]
    assert isinstance(smoke_files, dict)
    return {
        "evidence": {
            "file": "xp-evidence.json",
            "path": evidence_file,
            "size_bytes": 4096,
            "sha256": evidence_sha,
        },
        "smoke_evidence": {
            str(smoke_id): {
                "file": str(smoke_file),
                "size_bytes": 256 + index,
                "sha256": smoke_hashes[str(smoke_id)],
            }
            for index, (smoke_id, smoke_file) in enumerate(sorted(smoke_files.items()))
        },
    }


def _xp_smoke_commands(target: str) -> dict[str, str]:
    host_identity = _xp_host_identity(target)
    os_identity = host_identity["os"]
    assert isinstance(os_identity, dict)
    release_source = _xp_release_source_summary(target)
    security = _xp_security_patch_evidence()
    return {
        smoke_id: (
            f"scripts/xp_smoke_runner.cmd --target {target} --release-tag v1.0.2 "
            f"--smoke-id {smoke_id} --evidence-file xp-smoke-evidence/{smoke_id}.txt "
            f"--proof-file xp-smoke-proof/{smoke_id}.txt "
            f"--host-label {host_identity['host_label']} "
            f"--evidence-run-id {host_identity['evidence_run_id']} "
            f"--observed-at-utc {host_identity['observed_at_utc']} "
            f"--source-workflow-run-url {release_source['workflow_run_url']} "
            f"--source-head-sha {release_source['head_sha']} "
            f"--source-run-attempt {release_source['run_attempt']} "
            f"--security-update-channel {security['security_update_channel']} "
            f"--cve-review-reference {security['cve_review_reference']} "
            f'--os-name "{os_identity["name"]}" '
            f"--os-architecture {os_identity['architecture']} "
            f"--os-service-pack {os_identity['service_pack']}"
            + (
                f' --os-edition "{os_identity["edition"]}"'
                if "edition" in os_identity
                else ""
            )
        )
        for smoke_id in sorted(_xp_smoke_hashes())
    }


def _retag_accepted_evidence(record: dict[str, object], release_tag: str) -> dict[str, object]:
    updated = _replace_release_tag(record, "v1.0.2", release_tag)
    assert isinstance(updated, dict)
    builder_identity = updated.get("builder_identity")
    if isinstance(builder_identity, dict):
        updated["builder_identity_sha256"] = _json_sha256(builder_identity)
        linux_sources = updated.get("linux_evidence_sources")
        if isinstance(linux_sources, dict) and isinstance(linux_sources.get("builder_identity"), dict):
            linux_sources["builder_identity"]["sha256"] = updated["builder_identity_sha256"]
    xp_summary = updated.get("xp_evidence_summary")
    if isinstance(xp_summary, dict) and isinstance(xp_summary.get("host_identity"), dict):
        updated["xp_host_identity_sha256"] = _json_sha256(xp_summary["host_identity"])
    return updated


def _replace_release_tag(value: object, old: str, new: str) -> object:
    if isinstance(value, dict):
        return {
            str(key).replace(old, new): _replace_release_tag(item, old, new)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_replace_release_tag(item, old, new) for item in value]
    if isinstance(value, str):
        return value.replace(old, new)
    return value


def _replace_release_repository(record: dict[str, object], repository: str) -> None:
    old = "github.com/example/remote-ops-workspace"
    new = f"github.com/{repository}"
    record["release_asset_urls"] = [
        str(url).replace(old, new)
        for url in record.get("release_asset_urls", [])
    ]
    if isinstance(record.get("finalized_record_release_asset_url"), str):
        record["finalized_record_release_asset_url"] = str(
            record["finalized_record_release_asset_url"]
        ).replace(old, new)
    review_bundle = record.get("review_bundle")
    if isinstance(review_bundle, dict):
        review_bundle["release_asset_urls"] = [
            str(url).replace(old, new)
            for url in review_bundle.get("release_asset_urls", [])
        ]


def _replace_release_source_head(record: dict[str, object], head_sha: str) -> None:
    source = record.get("release_asset_source")
    assert isinstance(source, dict)
    old_head = str(source.get("head_sha", ""))
    source["head_sha"] = head_sha
    builder_identity = record.get("builder_identity")
    if isinstance(builder_identity, dict):
        builder_identity["workflow_ref"] = str(builder_identity.get("workflow_ref", "")).replace(old_head, head_sha)
        builder_identity["workflow_sha"] = head_sha
        builder_identity["source_head_sha"] = head_sha
        builder_identity["observed_git_head_sha"] = head_sha
        record["builder_identity_sha256"] = _json_sha256(builder_identity)
        linux_sources = record.get("linux_evidence_sources")
        if isinstance(linux_sources, dict) and isinstance(linux_sources.get("builder_identity"), dict):
            linux_sources["builder_identity"]["sha256"] = record["builder_identity_sha256"]
    if isinstance(record.get("local_evidence_preflight_command"), str) and old_head:
        record["local_evidence_preflight_command"] = str(
            record["local_evidence_preflight_command"]
        ).replace(old_head, head_sha)
    for field in ("native_smoke_command", "local_evidence_preflight_command"):
        if isinstance(record.get(field), str) and old_head:
            record[field] = str(record[field]).replace(old_head, head_sha)
    xp_summary = record.get("xp_evidence_summary")
    if isinstance(xp_summary, dict):
        xp_source = xp_summary.get("release_source")
        if isinstance(xp_source, dict):
            xp_source["head_sha"] = head_sha
        smoke_commands = xp_summary.get("smoke_commands")
        if isinstance(smoke_commands, dict) and old_head:
            for smoke_id, command in smoke_commands.items():
                smoke_commands[smoke_id] = str(command).replace(old_head, head_sha)


def _replace_xp_release_source_run_attempt(record: dict[str, object], run_attempt: int) -> None:
    source = record.get("release_asset_source")
    assert isinstance(source, dict)
    old_attempt = str(source.get("run_attempt", ""))
    source["run_attempt"] = run_attempt
    if isinstance(record.get("local_evidence_preflight_command"), str) and old_attempt:
        record["local_evidence_preflight_command"] = str(
            record["local_evidence_preflight_command"]
        ).replace(f"--xp-source-run-attempt {old_attempt}", f"--xp-source-run-attempt {run_attempt}")
    xp_summary = record.get("xp_evidence_summary")
    if not isinstance(xp_summary, dict):
        return
    xp_source = xp_summary.get("release_source")
    if isinstance(xp_source, dict):
        xp_source["run_attempt"] = run_attempt
    smoke_commands = xp_summary.get("smoke_commands")
    if isinstance(smoke_commands, dict) and old_attempt:
        for smoke_id, command in smoke_commands.items():
            smoke_commands[smoke_id] = str(command).replace(
                f"--source-run-attempt {old_attempt}",
                f"--source-run-attempt {run_attempt}",
            )


def _security_patch_evidence() -> dict[str, object]:
    return {
        "python_ssl_openssl": "OpenSSL 3.0.13",
        "openssl_cli_version": "OpenSSL 3.0.13",
        "tls_minimum_modern_profiles": "TLS 1.2",
        "tls_preferred_modern_profiles": "TLS 1.3",
        "legacy_compatibility_profile": "isolated-opt-in",
        "cve_patch_reviewed": True,
        "security_update_channel": "vendor-security-updates-2026-06",
        "cve_review_reference": "vendor-cve-advisory-review-2026-06",
    }


def _xp_security_patch_evidence() -> dict[str, object]:
    return {
        "tls_minimum_modern_profiles": "TLS 1.2",
        "tls_preferred_modern_profiles": "TLS 1.3",
        "legacy_compatibility_profile": "isolated-opt-in",
        "cve_patch_reviewed": True,
        "security_update_channel": "vendor-security-updates-2026-06",
        "cve_review_reference": "vendor-cve-advisory-review-2026-06",
    }


def _promotion_config_sha256() -> str:
    data = json.loads(Path("configs/platform_parity_promotion.json").read_text(encoding="utf-8"))
    return _json_sha256(data)


def _xp_native_evidence_contract_sha256() -> str:
    data = json.loads(Path("configs/xp_native_evidence_contract.json").read_text(encoding="utf-8"))
    return _json_sha256(data)


def _json_sha256(data: dict[str, object]) -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()

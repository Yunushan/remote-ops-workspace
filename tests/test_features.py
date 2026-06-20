import hashlib
import json
from pathlib import Path

from remote_ops_workspace.features import (
    _platform_verified_readiness,
    coverage_report,
    load_feature_manifest,
)

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
    goal = platform["protected_goal_parity"]
    assert goal["current_percent"] == 0.0
    assert goal["gap_percent"] == 100.0
    assert goal["accepted_target_count"] == 0
    assert goal["target_count"] == 4
    assert goal["complete"] is False
    assert goal["status"] == "missing-accepted-evidence"
    assert goal["missing_targets"] == [
        "linux-i386",
        "linux-armhf",
        "windows-xp-native-x86",
        "windows-xp-native-x64",
    ]
    rows = {row["target"]: row for row in platform["targets"]}
    assert rows["windows-x64"]["current_percent"] == 100.0
    assert rows["windows-x64"]["verified_readiness_scope"] is True
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["verified_readiness_scope"] is False
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
    assert rows["Windows XP"]["accepted_evidence_missing_targets"] == [
        "windows-xp-native-x86",
        "windows-xp-native-x64",
    ]


def test_platform_verified_readiness_promotes_only_with_accepted_evidence() -> None:
    manifest = _extended_platform_manifest()
    evidence = {
        "schema_version": 1,
        "accepted_evidence": [
            _linux_accepted_evidence("linux-i386"),
            _xp_accepted_evidence("windows-xp-native-x86"),
        ],
    }

    report = _platform_verified_readiness(platform_data=manifest, evidence_registry=evidence)
    rows = {row["target"]: row for row in report["targets"]}
    goal = report["protected_goal_parity"]

    assert rows["linux-i386"]["current_percent"] == 100.0
    assert rows["linux-i386"]["status"] == "verified-accepted-native-evidence"
    assert rows["linux-i386"]["verified_readiness_scope"] is True
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == []
    assert rows["linux-armhf"]["current_percent"] == 70.0
    assert rows["linux-armhf"]["verified_readiness_scope"] is False
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "partial-xp-native-host-evidence"
    assert rows["Windows XP"]["verified_readiness_scope"] is False
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == ["windows-xp-native-x86"]
    assert rows["Windows XP"]["accepted_evidence_missing_targets"] == ["windows-xp-native-x64"]
    assert goal["current_percent"] == 50.0
    assert goal["accepted_targets"] == ["linux-i386", "windows-xp-native-x86"]
    assert goal["missing_targets"] == ["linux-armhf", "windows-xp-native-x64"]
    assert goal["complete"] is False

    evidence["accepted_evidence"].append(_xp_accepted_evidence("windows-xp-native-x64"))
    report = _platform_verified_readiness(platform_data=manifest, evidence_registry=evidence)
    rows = {row["target"]: row for row in report["targets"]}
    goal = report["protected_goal_parity"]

    assert rows["Windows XP"]["current_percent"] == 100.0
    assert rows["Windows XP"]["status"] == "verified-xp-native-host-evidence"
    assert rows["Windows XP"]["verified_readiness_scope"] is True
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
    assert goal["current_percent"] == 50.0
    assert goal["accepted_targets"] == ["linux-i386", "windows-xp-native-x86"]
    assert goal["missing_targets"] == ["linux-armhf", "windows-xp-native-x64"]


def test_platform_verified_readiness_goal_parity_completes_with_all_accepted_evidence() -> None:
    manifest = _extended_platform_manifest()
    evidence = {
        "schema_version": 1,
        "accepted_evidence": [
            _linux_accepted_evidence("linux-i386"),
            _linux_accepted_evidence("linux-armhf"),
            _xp_accepted_evidence("windows-xp-native-x86"),
            _xp_accepted_evidence("windows-xp-native-x64"),
        ],
    }

    report = _platform_verified_readiness(platform_data=manifest, evidence_registry=evidence)
    goal = report["protected_goal_parity"]

    assert goal["current_percent"] == 100.0
    assert goal["gap_percent"] == 0.0
    assert goal["accepted_target_count"] == 4
    assert goal["aggregate_accepted_target_count"] == 4
    assert goal["release_tag"] == "v1.0.2"
    assert goal["release_tags"] == ["v1.0.2"]
    assert goal["release_repository"] == "example/remote-ops-workspace"
    assert goal["release_repositories"] == ["example/remote-ops-workspace"]
    assert goal["release_consistent"] is True
    assert goal["release_repository_consistent"] is True
    assert goal["accepted_targets"] == [
        "linux-i386",
        "linux-armhf",
        "windows-xp-native-x86",
        "windows-xp-native-x64",
    ]
    assert goal["missing_targets"] == []
    assert goal["complete"] is True
    assert goal["status"] == "complete"


def test_platform_verified_readiness_goal_parity_requires_one_release_repository() -> None:
    manifest = _extended_platform_manifest()
    xp_x64 = _xp_accepted_evidence("windows-xp-native-x64")
    _replace_release_repository(xp_x64, "other/remote-ops-workspace")
    evidence = {
        "schema_version": 1,
        "accepted_evidence": [
            _linux_accepted_evidence("linux-i386"),
            _linux_accepted_evidence("linux-armhf"),
            _xp_accepted_evidence("windows-xp-native-x86"),
            xp_x64,
        ],
    }

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
    assert rows["Windows XP"]["accepted_evidence_release_repositories"] == {
        "windows-xp-native-x86": ["example/remote-ops-workspace"],
        "windows-xp-native-x64": ["other/remote-ops-workspace"],
    }
    assert goal["current_percent"] == 75.0
    assert goal["gap_percent"] == 25.0
    assert goal["accepted_target_count"] == 3
    assert goal["release_tag"] == "v1.0.2"
    assert goal["release_repository"] == "example/remote-ops-workspace"
    assert goal["release_repositories"] == [
        "example/remote-ops-workspace",
        "other/remote-ops-workspace",
    ]
    assert goal["release_repository_consistent"] is False
    assert goal["accepted_targets"] == [
        "linux-i386",
        "linux-armhf",
        "windows-xp-native-x86",
    ]
    assert goal["missing_targets"] == ["windows-xp-native-x64"]
    assert goal["complete"] is False
    assert goal["status"] == "mixed-release-repository-evidence"


def test_platform_verified_readiness_goal_parity_requires_one_release_tag() -> None:
    manifest = _extended_platform_manifest()
    evidence = {
        "schema_version": 1,
        "accepted_evidence": [
            _linux_accepted_evidence("linux-i386"),
            _retag_accepted_evidence(_linux_accepted_evidence("linux-armhf"), "v1.0.3"),
            _retag_accepted_evidence(_xp_accepted_evidence("windows-xp-native-x86"), "v1.0.3"),
            _retag_accepted_evidence(_xp_accepted_evidence("windows-xp-native-x64"), "v1.0.3"),
        ],
    }

    report = _platform_verified_readiness(platform_data=manifest, evidence_registry=evidence)
    goal = report["protected_goal_parity"]

    assert goal["current_percent"] == 75.0
    assert goal["gap_percent"] == 25.0
    assert goal["accepted_target_count"] == 3
    assert goal["aggregate_accepted_target_count"] == 4
    assert goal["release_tag"] == "v1.0.3"
    assert goal["release_tags"] == ["v1.0.2", "v1.0.3"]
    assert goal["release_consistent"] is False
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
    assert goal["complete"] is False
    assert goal["status"] == "mixed-release-evidence"


def test_platform_verified_readiness_ignores_release_asset_url_tag_mismatch() -> None:
    manifest = _extended_platform_manifest()
    record = _linux_accepted_evidence("linux-i386")
    record["release_asset_urls"][0] = record["release_asset_urls"][0].replace(
        "/releases/download/v1.0.2/",
        "/releases/download/v9.9.9/",
    )
    report = _platform_verified_readiness(
        platform_data=manifest,
        evidence_registry={"schema_version": 1, "accepted_evidence": [record]},
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
        evidence_registry={"schema_version": 1, "accepted_evidence": [record]},
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
        evidence_registry={"schema_version": 1, "accepted_evidence": [record]},
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
        evidence_registry={"schema_version": 1, "accepted_evidence": [record]},
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
        evidence_registry={"schema_version": 1, "accepted_evidence": [record]},
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
        evidence_registry={"schema_version": 1, "accepted_evidence": [record]},
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
        evidence_registry={"schema_version": 1, "accepted_evidence": [record]},
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
        evidence_registry={"schema_version": 1, "accepted_evidence": [record]},
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_review_bundle_repository_mismatch() -> None:
    record = _linux_accepted_evidence("linux-armhf")
    record["review_bundle"]["release_asset_urls"] = [
        str(url).replace("github.com/example/remote-ops-workspace", "github.com/other/remote-ops-workspace")
        for url in record["review_bundle"]["release_asset_urls"]
    ]

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry={"schema_version": 1, "accepted_evidence": [record]},
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-armhf"]["current_percent"] == 70.0
    assert rows["linux-armhf"]["status"] == "manual-script-supported"
    assert rows["linux-armhf"]["accepted_evidence_missing_targets"] == ["linux-armhf"]


def test_platform_verified_readiness_ignores_artifact_validation_command_tag_mismatch() -> None:
    manifest = _extended_platform_manifest()
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["artifact_validation_command"] = record["artifact_validation_command"].replace(
        "--tag v1.0.2",
        "--tag v9.9.9",
    )
    report = _platform_verified_readiness(
        platform_data=manifest,
        evidence_registry={"schema_version": 1, "accepted_evidence": [record]},
    )
    rows = {row["target"]: row for row in report["targets"]}

    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_duplicate_artifact_validation_tag() -> None:
    record = _linux_accepted_evidence("linux-i386")
    record["artifact_validation_command"] = (
        "python scripts/check_platform_promotion_artifacts.py --target linux-i386 "
        "--assets-dir native-dist/linux --tag v1.0.2 --tag v9.9.9"
    )

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry={"schema_version": 1, "accepted_evidence": [record]},
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_placeholder_artifact_validation_assets_dir() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["artifact_validation_command"] = (
        "python scripts/check_platform_promotion_artifacts.py --target windows-xp-native-x86 "
        "--assets-dir <artifact-dir> --tag v1.0.2"
    )

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry={"schema_version": 1, "accepted_evidence": [record]},
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_wrong_linux_artifact_name() -> None:
    record = _linux_accepted_evidence("linux-armhf")
    record["artifact_name"] = "extended-linux-i386-native-evidence"

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry={"schema_version": 1, "accepted_evidence": [record]},
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
        evidence_registry={"schema_version": 1, "accepted_evidence": [record]},
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
        evidence_registry={"schema_version": 1, "accepted_evidence": [record]},
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
        evidence_registry={"schema_version": 1, "accepted_evidence": [record]},
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
        evidence_registry={"schema_version": 1, "accepted_evidence": [record]},
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
        evidence_registry={"schema_version": 1, "accepted_evidence": [record]},
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_missing_linux_smoke_evidence() -> None:
    record = _linux_accepted_evidence("linux-i386")
    del record["linux_smoke_evidence_sha256"]

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry={"schema_version": 1, "accepted_evidence": [record]},
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_wrong_xp_native_validation_command() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["native_evidence_validation_command"] = "python scripts/check_xp_native_evidence.py --help"

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry={"schema_version": 1, "accepted_evidence": [record]},
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
        evidence_registry={"schema_version": 1, "accepted_evidence": [record]},
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
        evidence_registry={"schema_version": 1, "accepted_evidence": [record]},
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
        evidence_registry={"schema_version": 1, "accepted_evidence": [record]},
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
        evidence_registry={"schema_version": 1, "accepted_evidence": [record]},
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
        evidence_registry={"schema_version": 1, "accepted_evidence": [record]},
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_xp_smoke_command_target_mismatch() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["xp_evidence_summary"]["smoke_commands"]["cli_launch"] = (
        "scripts/xp_smoke_runner.cmd --target windows-xp-native-x64 --release-tag v1.0.2 "
        "--smoke-id cli_launch"
    )

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry={"schema_version": 1, "accepted_evidence": [record]},
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["Windows XP"]["current_percent"] == 25.0
    assert rows["Windows XP"]["status"] == "remote-target-only"
    assert rows["Windows XP"]["accepted_evidence_present_targets"] == []


def test_platform_verified_readiness_ignores_xp_smoke_command_evidence_file_mismatch() -> None:
    record = _xp_accepted_evidence("windows-xp-native-x86")
    record["xp_evidence_summary"]["smoke_commands"]["cli_launch"] = (
        "scripts/xp_smoke_runner.cmd --target windows-xp-native-x86 --release-tag v1.0.2 "
        "--smoke-id cli_launch --evidence-file xp-smoke-evidence/other.txt"
    )

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry={"schema_version": 1, "accepted_evidence": [record]},
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
        evidence_registry={"schema_version": 1, "accepted_evidence": [record]},
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
        evidence_registry={"schema_version": 1, "accepted_evidence": [record]},
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
        evidence_registry={"schema_version": 1, "accepted_evidence": [record]},
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
        evidence_registry={"schema_version": 1, "accepted_evidence": [record]},
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
        evidence_registry={"schema_version": 1, "accepted_evidence": [record]},
    )

    rows = {row["target"]: row for row in report["targets"]}
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["linux-i386"]["status"] == "manual-script-supported"
    assert rows["linux-i386"]["accepted_evidence_missing_targets"] == ["linux-i386"]


def test_platform_verified_readiness_ignores_duplicate_release_asset_urls() -> None:
    record = _linux_accepted_evidence("linux-armhf")
    record["release_asset_urls"].append(record["release_asset_urls"][0])

    report = _platform_verified_readiness(
        platform_data=_extended_platform_manifest(),
        evidence_registry={"schema_version": 1, "accepted_evidence": [record]},
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
        evidence_registry={"schema_version": 1, "accepted_evidence": [record]},
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
        evidence_registry={"schema_version": 1, "accepted_evidence": [record]},
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
        evidence_registry={"schema_version": 1, "accepted_evidence": [record]},
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


def _linux_accepted_evidence(target: str) -> dict[str, object]:
    arch = "i386" if target == "linux-i386" else "armhf"
    rpm_arch = "i686" if target == "linux-i386" else "armv7hl"
    artifact_arch = "i686" if target == "linux-i386" else "armhf"
    artifact = (
        "extended-linux-i386-native-evidence"
        if target == "linux-i386"
        else "extended-linux-armhf-native-evidence"
    )
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
        "builder_identity_sha256": _json_sha256(builder_identity),
        "native_build_command": (
            f"TARGET_ARCH={arch} PYTHON_BIN=.venv-native/bin/python bash scripts/make_linux_native.sh"
        ),
        "native_smoke_command": (
            f"bash scripts/smoke_linux_native.sh --arch {arch} --dist native-dist/linux "
            f"--target {target} --workflow-run-url https://github.com/example/remote-ops-workspace/actions/runs/12345"
        ),
        "linux_smoke_evidence_sha256": _linux_smoke_hashes(),
        "artifact_validation_command": (
            f"python scripts/check_platform_promotion_artifacts.py --target {target} "
            "--assets-dir native-dist/linux --tag v1.0.2"
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
        "review_bundle": _review_bundle(target),
    }


def _xp_accepted_evidence(target: str) -> dict[str, object]:
    arch = "x86" if target.endswith("x86") else "x64"
    base_url = "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2"
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
        "architecture": arch,
        "separate_legacy_toolchain": True,
        "current_python_pyqt6_stack": False,
        "xp_evidence_sha256": "b" * 64,
        "xp_evidence_contract_sha256": _xp_native_evidence_contract_sha256(),
        "xp_host_identity_sha256": _json_sha256(_xp_host_identity(target)),
        "xp_evidence_summary": _xp_evidence_summary(target),
        "xp_smoke_evidence_sha256": _xp_smoke_hashes(),
        "native_evidence_validation_command": (
            "python scripts/check_xp_native_evidence.py "
            f"--evidence evidence/{target}/xp-evidence.json --assets-dir native-dist/windows-xp"
        ),
        "artifact_validation_command": (
            f"python scripts/check_platform_promotion_artifacts.py --target {target} "
            "--assets-dir native-dist/windows-xp --tag v1.0.2"
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
        "host_identity": _linux_host_identity(target),
        "sudo_non_interactive": True,
        "sys_platform": "linux",
        "platform_machine": machine,
        "uname_machine": machine,
        "dpkg_architecture": dpkg_arch,
        "userland_bits": "32",
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
        "host_label": f"{target}-builder",
        "evidence_run_id": f"{target}-{release_tag.removeprefix('v').replace('.', '-')}-run-12345",
        "observed_at_utc": "2026-06-20T12:00:00Z",
        "operator_private_data_redacted": True,
    }


def _artifact_hashes_from_urls(urls: list[str]) -> dict[str, str]:
    return {Path(url).name: "a" * 64 for url in urls}


def _linux_smoke_hashes() -> dict[str, str]:
    return {"native_smoke": "6" * 64}


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
        "security": {
            "legacy_crypto_profile_scoped": True,
            "modern_defaults_unchanged": True,
            "weak_crypto_global_default": False,
            "patch_evidence": _security_patch_evidence(),
        },
        "smoke_ids": sorted(_xp_smoke_hashes()),
        "smoke_evidence_files": _xp_smoke_evidence_files(),
        "smoke_commands": _xp_smoke_commands(target),
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


def _xp_smoke_commands(target: str) -> dict[str, str]:
    return {
        smoke_id: (
            f"scripts/xp_smoke_runner.cmd --target {target} --release-tag v1.0.2 "
            f"--smoke-id {smoke_id} --evidence-file xp-smoke-evidence/{smoke_id}.txt"
        )
        for smoke_id in sorted(_xp_smoke_hashes())
    }


def _retag_accepted_evidence(record: dict[str, object], release_tag: str) -> dict[str, object]:
    updated = _replace_release_tag(record, "v1.0.2", release_tag)
    assert isinstance(updated, dict)
    builder_identity = updated.get("builder_identity")
    if isinstance(builder_identity, dict):
        updated["builder_identity_sha256"] = _json_sha256(builder_identity)
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
    review_bundle = record.get("review_bundle")
    if isinstance(review_bundle, dict):
        review_bundle["release_asset_urls"] = [
            str(url).replace(old, new)
            for url in review_bundle.get("release_asset_urls", [])
        ]


def _security_patch_evidence() -> dict[str, object]:
    return {
        "python_ssl_openssl": "OpenSSL 3.0.13",
        "openssl_cli_version": "OpenSSL 3.0.13",
        "tls_minimum_modern_profiles": "TLS 1.2",
        "tls_preferred_modern_profiles": "TLS 1.3",
        "legacy_compatibility_profile": "isolated-opt-in",
        "cve_patch_reviewed": True,
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

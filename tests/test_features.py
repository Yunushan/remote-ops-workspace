from pathlib import Path

from remote_ops_workspace.features import coverage_report, load_feature_manifest

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
        assert "| MobaXterm | 100.0% | 100.0% | 100.0% | 0.0% | 25 |" in text
        assert "release-backed product workflow parity" in text
        assert "not a proprietary native clone" in text


def test_platform_verified_readiness_tracks_partial_targets() -> None:
    report = coverage_report()
    platform = report["platform_verified_readiness"]
    assert platform["overall"]["current_percent"] == 75.6
    assert platform["overall"]["gap_percent"] == 24.4
    rows = {row["target"]: row for row in platform["targets"]}
    assert rows["windows-x64"]["current_percent"] == 100.0
    assert rows["linux-i386"]["current_percent"] == 70.0
    assert rows["android-arm64"]["current_percent"] == 85.0
    assert rows["Windows XP"]["current_percent"] == 25.0

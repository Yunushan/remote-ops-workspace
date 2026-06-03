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
    readiness = report["product_ready_coverage"]
    assert mapping["overall"]["current_percent"] == 100.0
    assert readiness["overall"]["current_percent"] < mapping["overall"]["current_percent"]
    rows = {row["product"]: row for row in mapping["products"]}
    readiness_rows = {row["product"]: row for row in readiness["products"]}
    for product in REQUESTED_PRODUCTS:
        row = rows[product]
        ready_row = readiness_rows[product]
        assert row["feature_count"] > 0
        assert row["current_percent"] == row["target_percent"]
        assert 0 <= ready_row["current_percent"] <= ready_row["target_percent"]
        assert ready_row["current_percent"] <= row["current_percent"]


def test_product_readiness_uses_maturity_weights_not_full_overrides() -> None:
    manifest = load_feature_manifest()
    scoring = manifest["coverage_scoring"]
    assert scoring["product_ready_feature_overrides"] == {}
    assert scoring["product_ready_target_overrides"] == {}

    report = coverage_report()
    overall = report["product_ready_coverage"]["overall"]
    assert overall["current_percent"] == 82.4
    assert overall["gap_percent"] == 17.6

    readiness_rows = {
        row["product"]: row for row in report["product_ready_coverage"]["products"]
    }
    for product in REQUESTED_PRODUCTS:
        row = readiness_rows[product]
        assert row["current_percent"] < row["target_percent"]
        assert row["gap_percent"] > 0.0
        assert "overrides_applied" not in row


def test_feature_coverage_weights_cover_manifest_statuses() -> None:
    manifest = load_feature_manifest()
    report = coverage_report()
    mapping_weights = report["status_weights"]
    readiness_weights = report["product_ready_status_weights"]
    statuses = {item["status"] for item in manifest["features"]}
    assert statuses.issubset(mapping_weights)
    assert statuses.issubset(readiness_weights)
    assert any(readiness_weights[status] < mapping_weights[status] for status in statuses)


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


def test_readme_coverage_tables_match_generated_readiness_scores() -> None:
    report = coverage_report()
    readiness_rows = {
        row["product"]: row for row in report["product_ready_coverage"]["products"]
    }
    expected_lines = []
    for row in report["feature_family_mapping"]["products"]:
        ready_row = readiness_rows[row["product"]]
        expected_lines.append(
            f"| {row['product']} | {row['current_percent']:.1f}% | "
            f"{ready_row['current_percent']:.1f}% | {ready_row['gap_percent']:.1f}% | "
            f"{row['feature_count']} |"
        )
    mapping_overall = report["feature_family_mapping"]["overall"]
    readiness_overall = report["product_ready_coverage"]["overall"]
    expected_lines.append(
        f"| **Overall** | **{mapping_overall['current_percent']:.1f}%** | "
        f"**{readiness_overall['current_percent']:.1f}%** | "
        f"**{readiness_overall['gap_percent']:.1f}%** | "
        f"**{mapping_overall['feature_count']}** |"
    )

    for path in (Path("README.md"), Path("docs/FULL_FEATURE_COVERAGE.md")):
        text = path.read_text(encoding="utf-8")
        for line in expected_lines:
            assert line in text
        assert "| MobaXterm | 100.0% | 100.0% | 0.0% | 25 |" not in text

from remote_ops_workspace.features import coverage_report, load_feature_manifest


def test_feature_manifest_covers_requested_products() -> None:
    manifest = load_feature_manifest()
    products = set(manifest["products"])
    assert {"MobaXterm", "Remmina", "mRemoteNG", "Terminator", "Termius"}.issubset(products)
    feature_ids = {item["id"] for item in manifest["features"]}
    assert "protocol.ssh" in feature_ids
    assert "protocol.rdp" in feature_ids
    assert "terminal.splits" in feature_ids
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
    for product in {"MobaXterm", "Remmina", "mRemoteNG", "Terminator", "Termius"}:
        row = rows[product]
        ready_row = readiness_rows[product]
        assert row["feature_count"] > 0
        assert row["current_percent"] == row["target_percent"]
        assert 0 <= ready_row["current_percent"] <= ready_row["target_percent"]
        assert ready_row["current_percent"] <= row["current_percent"]


def test_feature_coverage_weights_cover_manifest_statuses() -> None:
    manifest = load_feature_manifest()
    report = coverage_report()
    mapping_weights = report["status_weights"]
    readiness_weights = report["product_ready_status_weights"]
    statuses = {item["status"] for item in manifest["features"]}
    assert statuses.issubset(mapping_weights)
    assert statuses.issubset(readiness_weights)
    assert any(readiness_weights[status] < mapping_weights[status] for status in statuses)


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

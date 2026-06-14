from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from remote_ops_workspace.features import coverage_report, load_feature_manifest  # noqa: E402

IMPLEMENTED_STATUSES = {
    "implemented",
    "implemented-adapter",
    "implemented-cli",
    "implemented-cli-gui",
    "implemented-gui",
    "implemented-optional",
    "implemented-shell",
}


def main() -> int:
    errors = check_product_readiness()
    if errors:
        for error in errors:
            print(f"coverage truth: {error}", file=sys.stderr)
        return 1
    print("coverage truth checks passed")
    return 0


def check_product_readiness() -> list[str]:
    errors: list[str] = []
    manifest = load_feature_manifest()
    report = coverage_report()
    scoring = manifest.get("coverage_scoring", {})
    adapter_weights = report["adapter_ready_status_weights"]
    parity_weights = report["production_parity_status_weights"]

    for status in IMPLEMENTED_STATUSES:
        if adapter_weights.get(status) != 1.0:
            errors.append(f"implemented status {status} must score 1.0 for adapter-ready coverage")
    for status, weight in adapter_weights.items():
        if not str(status).startswith("implemented") and float(weight) >= 1.0:
            errors.append(f"non-implemented status {status} must remain below 1.0 adapter-ready weight")
    for status in IMPLEMENTED_STATUSES:
        if parity_weights.get(status) != adapter_weights.get(status):
            errors.append(f"workflow parity status {status} must match adapter-ready weight")
    for status, weight in parity_weights.items():
        if not str(status).startswith("implemented") and float(weight) >= 1.0:
            errors.append(f"non-implemented status {status} must remain below 1.0 workflow parity weight")

    for key in (
        "adapter_ready_feature_overrides",
        "adapter_ready_target_overrides",
        "production_parity_feature_overrides",
        "production_parity_target_overrides",
        "product_ready_feature_overrides",
        "product_ready_target_overrides",
    ):
        if scoring.get(key) not in ({}, None):
            errors.append(f"{key} must not be used to force coverage percentages")

    adapter = report["adapter_ready_coverage"]
    rows = [adapter["overall"], *adapter["products"]]
    for row in rows:
        if row["current_percent"] != row["target_percent"]:
            errors.append(
                f"{row['product']} adapter-ready coverage is {row['current_percent']}%, "
                f"expected {row['target_percent']}%"
            )
        if row["gap_percent"] != 0.0:
            errors.append(f"{row['product']} adapter-ready gap must be 0.0%, got {row['gap_percent']}%")
    parity = report["production_parity_coverage"]
    parity_rows = [parity["overall"], *parity["products"]]
    workflow_evidence = {
        row["product"]: row for row in report.get("workflow_parity_evidence", [])
    }
    for row in parity_rows:
        if row["current_percent"] != row["target_percent"]:
            errors.append(
                f"{row['product']} workflow parity is {row['current_percent']}%, "
                f"expected {row['target_percent']}%"
            )
        if row["gap_percent"] != 0.0:
            errors.append(f"{row['product']} workflow parity gap must be 0.0%, got {row['gap_percent']}%")
        evidence = workflow_evidence.get(row["product"])
        if evidence is None:
            errors.append(f"{row['product']} workflow parity row must expose JSON evidence")
            continue
        if evidence.get("native_clone_claimed") is not False:
            errors.append(f"{row['product']} workflow parity must not claim proprietary native clone parity")
        if evidence.get("coverage_percent") != row["current_percent"]:
            errors.append(f"{row['product']} workflow parity evidence percentage does not match coverage row")
        if evidence.get("feature_count") != row["feature_count"]:
            errors.append(f"{row['product']} workflow parity evidence feature count does not match coverage row")
        if evidence.get("partial_feature_count") != 0:
            errors.append(f"{row['product']} workflow parity has partial feature evidence")
        if evidence.get("missing_release_evidence_count") != 0:
            errors.append(f"{row['product']} workflow parity is missing release-backed evidence")
        if evidence.get("full_parity_feature_count") != row["feature_count"]:
            errors.append(f"{row['product']} workflow parity full evidence count does not cover every feature")
        for item in evidence.get("feature_evidence", []):
            if item.get("counts_as_full_parity") and not item.get("release_backed"):
                errors.append(f"{row['product']} feature {item.get('id')} lacks release-backed parity evidence")
            if item.get("counts_as_full_parity") and not item.get("evidence_refs"):
                errors.append(f"{row['product']} feature {item.get('id')} lacks evidence refs")

    platform = report["platform_verified_readiness"]
    platform_rows = platform.get("targets", [])
    if not platform_rows:
        errors.append("platform verified readiness must include release and legacy targets")
    partial_rows = [row for row in platform_rows if row["current_percent"] < 100.0]
    if not partial_rows:
        errors.append("platform verified readiness must expose partial non-default targets")
    for row in partial_rows:
        if row.get("verified_readiness_scope") is not False:
            errors.append(f"{row['target']} partial compatibility row must stay outside verified readiness scope")
    if platform.get("overall", {}).get("current_percent") != 100.0:
        errors.append("platform verified readiness overall must be 100 for verified-scope targets")
    return errors


if __name__ == "__main__":
    raise SystemExit(main())

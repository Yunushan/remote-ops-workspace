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
    for status in IMPLEMENTED_STATUSES - {"implemented"}:
        if parity_weights.get(status, 0.0) >= adapter_weights.get(status, 0.0):
            errors.append(f"production parity status {status} must score below adapter-ready weight")

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
    if parity["overall"]["current_percent"] >= adapter["overall"]["current_percent"]:
        errors.append("production parity must remain a separate lower score than adapter-ready coverage")
    if parity["overall"]["gap_percent"] <= 0.0:
        errors.append("production parity must keep a visible gap until full native parity is implemented")

    platform = report["platform_verified_readiness"]
    platform_rows = platform.get("targets", [])
    if not platform_rows:
        errors.append("platform verified readiness must include release and legacy targets")
    if not any(row["current_percent"] < 100.0 for row in platform_rows):
        errors.append("platform verified readiness must expose partial non-default targets")
    if platform.get("overall", {}).get("current_percent", 100.0) >= 100.0:
        errors.append("platform verified readiness overall must not be 100 while partial targets exist")
    return errors


if __name__ == "__main__":
    raise SystemExit(main())

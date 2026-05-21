from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .paths import repo_root

DEFAULT_FEATURE_FAMILY_STATUS_WEIGHTS: dict[str, float] = {
    "implemented": 1.0,
    "implemented-cli-gui": 1.0,
    "implemented-cli": 1.0,
    "implemented-gui": 1.0,
    "implemented-adapter": 1.0,
    "implemented-optional": 1.0,
    "implemented-shell": 1.0,
    "gui-shell": 0.4,
    "adapter-seam": 0.25,
    "docs-adapter": 0.2,
    "plugin-seam": 0.2,
    "manifest-seam": 0.15,
    "script-seam": 0.15,
}

DEFAULT_PRODUCT_READY_STATUS_WEIGHTS: dict[str, float] = {
    "implemented": 1.0,
    "implemented-cli-gui": 0.9,
    "implemented-cli": 0.85,
    "implemented-gui": 0.85,
    "implemented-adapter": 0.75,
    "implemented-optional": 0.75,
    "implemented-shell": 0.45,
    "gui-shell": 0.4,
    "adapter-seam": 0.25,
    "docs-adapter": 0.2,
    "plugin-seam": 0.2,
    "manifest-seam": 0.15,
    "script-seam": 0.15,
}

STATUS_EVIDENCE_TYPES: dict[str, str] = {
    "implemented": "repo-code",
    "implemented-cli-gui": "cli-gui-workflow",
    "implemented-cli": "cli-workflow",
    "implemented-gui": "gui-workflow",
    "implemented-adapter": "external-client-adapter",
    "implemented-optional": "optional-dependency",
    "implemented-shell": "platform-shell",
    "gui-shell": "gui-shell",
    "adapter-seam": "adapter-extension",
    "docs-adapter": "documented-adapter",
    "plugin-seam": "plugin-extension",
    "manifest-seam": "manifest-contract",
    "script-seam": "platform-script",
}


def feature_manifest_path() -> Path:
    return repo_root() / "configs" / "feature_manifest.json"


def load_feature_manifest(path: Path | None = None) -> dict[str, Any]:
    target = path or feature_manifest_path()
    return json.loads(target.read_text(encoding="utf-8"))


def coverage_report(path: Path | None = None) -> dict[str, Any]:
    manifest = load_feature_manifest(path)
    features = manifest.get("features", [])
    products = manifest.get("products", [])
    scoring = manifest.get("coverage_scoring", {})
    feature_family_weights = _status_weights(
        scoring,
        "feature_family_status_weights",
        DEFAULT_FEATURE_FAMILY_STATUS_WEIGHTS,
        fallback_key="status_weights",
    )
    product_ready_weights = _status_weights(
        scoring,
        "product_ready_status_weights",
        DEFAULT_PRODUCT_READY_STATUS_WEIGHTS,
    )
    feature_family_target = float(
        scoring.get("feature_family_mapping_target_percent", scoring.get("target_percent", 100))
    )
    product_ready_target = float(scoring.get("product_ready_target_percent", 100))
    feature_family_mapping = _coverage_block(
        label="feature_family_mapping",
        products=products,
        features=features,
        weights=feature_family_weights,
        target_percent=feature_family_target,
        method=scoring.get(
            "feature_family_method",
            scoring.get("method", "Weighted feature-family mapping by feature status."),
        ),
    )
    product_ready_coverage = _coverage_block(
        label="product_ready_coverage",
        products=products,
        features=features,
        weights=product_ready_weights,
        target_percent=product_ready_target,
        method=scoring.get(
            "product_ready_method",
            "Evidence-weighted product readiness by feature status.",
        ),
    )
    evidence = [_feature_evidence(item) for item in features]

    return {
        "target_percent": feature_family_target,
        "method": feature_family_mapping["method"],
        "contract": scoring.get("contract", {}),
        "status_weights": feature_family_weights,
        "product_ready_status_weights": product_ready_weights,
        "overall": feature_family_mapping["overall"],
        "products": feature_family_mapping["products"],
        "feature_family_mapping": feature_family_mapping,
        "product_ready_coverage": product_ready_coverage,
        "evidence_summary": _evidence_summary(evidence),
        "feature_evidence": evidence,
    }


def feature_summary() -> list[dict[str, str]]:
    manifest = load_feature_manifest()
    rows: list[dict[str, str]] = []
    for item in manifest.get("features", []):
        rows.append(
            {
                "id": item.get("id", ""),
                "category": item.get("category", ""),
                "status": item.get("status", ""),
                "coverage": ", ".join(item.get("inspired_by", [])),
            }
        )
    return rows


def _status_weights(
    scoring: dict[str, Any],
    key: str,
    defaults: dict[str, float],
    *,
    fallback_key: str | None = None,
) -> dict[str, float]:
    configured = scoring.get(key, {})
    if not configured and fallback_key:
        configured = scoring.get(fallback_key, {})
    weights = defaults.copy()
    if isinstance(configured, dict):
        weights.update({str(key): float(value) for key, value in configured.items()})
    return weights


def _coverage_block(
    label: str,
    products: list[str],
    features: list[dict[str, Any]],
    weights: dict[str, float],
    target_percent: float,
    method: str,
) -> dict[str, Any]:
    return {
        "metric": label,
        "target_percent": round(target_percent, 1),
        "method": method,
        "status_weights": weights,
        "overall": _score_features("Overall", features, weights, target_percent),
        "products": [
            _score_features(product, _features_for_product(features, product), weights, target_percent)
            for product in products
        ],
    }


def _features_for_product(features: list[dict[str, Any]], product: str) -> list[dict[str, Any]]:
    return [
        item
        for item in features
        if any(product in str(source) for source in item.get("inspired_by", []))
    ]


def _score_features(
    label: str,
    features: list[dict[str, Any]],
    weights: dict[str, float],
    target_percent: float,
) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    current_points = 0.0

    for item in features:
        status = str(item.get("status", ""))
        status_counts[status] = status_counts.get(status, 0) + 1
        current_points += weights.get(status, 0.0)

    target_points = float(len(features))
    current_percent = (current_points / target_points * 100) if target_points else 0.0
    gap_percent = max(target_percent - current_percent, 0.0)
    return {
        "product": label,
        "feature_count": len(features),
        "current_points": round(current_points, 2),
        "target_points": round(target_points, 2),
        "current_percent": round(current_percent, 1),
        "target_percent": round(target_percent, 1),
        "gap_percent": round(gap_percent, 1),
        "status_counts": dict(sorted(status_counts.items())),
    }


def _feature_evidence(item: dict[str, Any]) -> dict[str, Any]:
    status = str(item.get("status", ""))
    extension_point = str(item.get("extension_point", ""))
    inspired_by = [str(product) for product in item.get("inspired_by", [])]
    missing_metadata = [
        field
        for field in ("id", "name", "category", "status", "extension_point", "inspired_by")
        if not item.get(field)
    ]
    evidence: list[dict[str, str]] = []
    if status:
        evidence.append(
            {
                "type": "manifest-status",
                "ref": status,
                "detail": "Feature maturity is declared in the manifest status field.",
            }
        )
    if extension_point:
        evidence.append(
            {
                "type": STATUS_EVIDENCE_TYPES.get(status, "extension-point"),
                "ref": extension_point,
                "detail": "Implementation, adapter, script, or extension point referenced by the manifest.",
            }
        )
    if inspired_by:
        evidence.append(
            {
                "type": "product-mapping",
                "ref": ", ".join(inspired_by),
                "detail": "Requested products whose public feature families map to this project feature.",
            }
        )
    return {
        "id": item.get("id", ""),
        "name": item.get("name", ""),
        "category": item.get("category", ""),
        "status": status,
        "implementation_kind": STATUS_EVIDENCE_TYPES.get(status, "unknown"),
        "products": inspired_by,
        "extension_point": extension_point,
        "evidence": evidence,
        "evidence_count": len(evidence),
        "missing_metadata": missing_metadata,
    }


def _evidence_summary(evidence: list[dict[str, Any]]) -> dict[str, int]:
    total = len(evidence)
    missing_extension_point = sum(1 for item in evidence if not item["extension_point"])
    missing_product_mapping = sum(1 for item in evidence if not item["products"])
    missing_status = sum(1 for item in evidence if not item["status"])
    missing_evidence = sum(1 for item in evidence if item["evidence_count"] == 0)
    return {
        "total_features": total,
        "features_with_evidence": total - missing_evidence,
        "features_missing_evidence": missing_evidence,
        "features_missing_extension_point": missing_extension_point,
        "features_missing_product_mapping": missing_product_mapping,
        "features_missing_status": missing_status,
    }

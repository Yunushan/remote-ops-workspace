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

DEFAULT_ADAPTER_READY_STATUS_WEIGHTS: dict[str, float] = {
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

DEFAULT_PRODUCTION_PARITY_STATUS_WEIGHTS: dict[str, float] = {
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
    adapter_ready_weights = _status_weights(
        scoring,
        "adapter_ready_status_weights",
        DEFAULT_ADAPTER_READY_STATUS_WEIGHTS,
        fallback_key="product_ready_status_weights",
    )
    production_parity_weights = _status_weights(
        scoring,
        "production_parity_status_weights",
        DEFAULT_PRODUCTION_PARITY_STATUS_WEIGHTS,
    )
    product_feature_mappings = _normalise_product_feature_mappings(
        scoring.get("product_feature_mappings", {})
    )
    feature_family_target = float(
        scoring.get("feature_family_mapping_target_percent", scoring.get("target_percent", 100))
    )
    adapter_ready_target = float(
        scoring.get("adapter_ready_target_percent", scoring.get("product_ready_target_percent", 100))
    )
    production_parity_target = float(scoring.get("production_parity_target_percent", 100))
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
        product_feature_mappings=product_feature_mappings,
    )
    adapter_ready_coverage = _coverage_block(
        label="adapter_ready_coverage",
        products=products,
        features=features,
        weights=adapter_ready_weights,
        target_percent=adapter_ready_target,
        method=scoring.get(
            "adapter_ready_method",
            scoring.get(
                "product_ready_method",
                "Adapter-ready coverage by executable feature status.",
            ),
        ),
        overrides=scoring.get(
            "adapter_ready_feature_overrides",
            scoring.get("product_ready_feature_overrides", {}),
        ),
        target_overrides=scoring.get(
            "adapter_ready_target_overrides",
            scoring.get("product_ready_target_overrides", {}),
        ),
        product_feature_mappings=product_feature_mappings,
    )
    production_parity_coverage = _coverage_block(
        label="production_parity_coverage",
        products=products,
        features=features,
        weights=production_parity_weights,
        target_percent=production_parity_target,
        method=scoring.get(
            "production_parity_method",
            "Honest parity coverage by feature status and implementation depth.",
        ),
        overrides=scoring.get("production_parity_feature_overrides", {}),
        target_overrides=scoring.get("production_parity_target_overrides", {}),
        product_feature_mappings=product_feature_mappings,
    )
    evidence = [_feature_evidence(item) for item in features]
    platform_verified_readiness = _platform_verified_readiness()

    return {
        "target_percent": feature_family_target,
        "method": feature_family_mapping["method"],
        "contract": scoring.get("contract", {}),
        "status_weights": feature_family_weights,
        "adapter_ready_status_weights": adapter_ready_weights,
        "product_ready_status_weights": adapter_ready_weights,
        "production_parity_status_weights": production_parity_weights,
        "overall": feature_family_mapping["overall"],
        "products": feature_family_mapping["products"],
        "feature_family_mapping": feature_family_mapping,
        "adapter_ready_coverage": adapter_ready_coverage,
        "product_ready_coverage": adapter_ready_coverage,
        "production_parity_coverage": production_parity_coverage,
        "platform_verified_readiness": platform_verified_readiness,
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
    overrides: dict[str, Any] | None = None,
    target_overrides: dict[str, Any] | None = None,
    product_feature_mappings: dict[str, set[str]] | None = None,
) -> dict[str, Any]:
    override_map = _normalise_product_overrides(overrides or {})
    target_override_map = _normalise_target_overrides(target_overrides or {})
    return {
        "metric": label,
        "target_percent": round(target_percent, 1),
        "method": method,
        "status_weights": weights,
        "overall": _score_features("Overall", features, weights, target_percent, {}),
        "products": [
            _score_features(
                product,
                _features_for_product(features, product, product_feature_mappings or {}),
                weights,
                target_percent,
                _product_overrides(
                    product,
                    _features_for_product(features, product, product_feature_mappings or {}),
                    override_map.get(product, {}),
                    target_override_map.get(product),
                ),
            )
            for product in products
        ],
    }


def _features_for_product(
    features: list[dict[str, Any]],
    product: str,
    product_feature_mappings: dict[str, set[str]] | None = None,
) -> list[dict[str, Any]]:
    mapped_ids = (product_feature_mappings or {}).get(product, set())
    return [
        item
        for item in features
        if str(item.get("id", "")) in mapped_ids
        or any(product in str(source) for source in item.get("inspired_by", []))
    ]


def _score_features(
    label: str,
    features: list[dict[str, Any]],
    weights: dict[str, float],
    target_percent: float,
    overrides: dict[str, dict[str, Any]],
) -> dict[str, Any]:
    status_counts: dict[str, int] = {}
    current_points = 0.0
    overrides_applied: list[dict[str, Any]] = []

    for item in features:
        status = str(item.get("status", ""))
        status_counts[status] = status_counts.get(status, 0) + 1
        status_weight = weights.get(status, 0.0)
        feature_id = str(item.get("id", ""))
        override = overrides.get(feature_id)
        if override:
            override_weight = float(override["weight"])
            current_points += override_weight
            overrides_applied.append(
                {
                    "id": feature_id,
                    "status": status,
                    "status_weight": round(status_weight, 2),
                    "override_weight": round(override_weight, 2),
                    "rationale": override.get("rationale", ""),
                    "evidence": override.get("evidence", ""),
                }
            )
        else:
            current_points += status_weight

    target_points = float(len(features))
    current_percent = (current_points / target_points * 100) if target_points else 0.0
    gap_percent = max(target_percent - current_percent, 0.0)
    row = {
        "product": label,
        "feature_count": len(features),
        "current_points": round(current_points, 2),
        "target_points": round(target_points, 2),
        "current_percent": round(current_percent, 1),
        "target_percent": round(target_percent, 1),
        "gap_percent": round(gap_percent, 1),
        "status_counts": dict(sorted(status_counts.items())),
    }
    if overrides_applied:
        row["overrides_applied"] = overrides_applied
    return row


def _normalise_product_overrides(overrides: dict[str, Any]) -> dict[str, dict[str, dict[str, Any]]]:
    normalised: dict[str, dict[str, dict[str, Any]]] = {}
    for product, product_overrides in overrides.items():
        if not isinstance(product_overrides, dict):
            continue
        normalised[str(product)] = {}
        for feature_id, override in product_overrides.items():
            if isinstance(override, dict):
                weight = float(override.get("weight", 0.0))
                rationale = str(override.get("rationale", ""))
                evidence = str(override.get("evidence", ""))
            else:
                weight = float(override)
                rationale = ""
                evidence = ""
            normalised[str(product)][str(feature_id)] = {
                "weight": weight,
                "rationale": rationale,
                "evidence": evidence,
            }
    return normalised


def _normalise_target_overrides(overrides: dict[str, Any]) -> dict[str, dict[str, Any]]:
    normalised: dict[str, dict[str, Any]] = {}
    for product, override in overrides.items():
        if not isinstance(override, dict):
            continue
        normalised[str(product)] = {
            "weight": float(override.get("weight", 0.0)),
            "rationale": str(override.get("rationale", "")),
            "evidence": str(override.get("evidence", "")),
        }
    return normalised


def _normalise_product_feature_mappings(overrides: dict[str, Any]) -> dict[str, set[str]]:
    normalised: dict[str, set[str]] = {}
    for product, feature_ids in overrides.items():
        if not isinstance(feature_ids, list):
            continue
        normalised[str(product)] = {str(feature_id) for feature_id in feature_ids}
    return normalised


def _product_overrides(
    product: str,
    features: list[dict[str, Any]],
    feature_overrides: dict[str, dict[str, Any]],
    target_override: dict[str, Any] | None,
) -> dict[str, dict[str, Any]]:
    if not target_override:
        return feature_overrides
    merged = dict(feature_overrides)
    for item in features:
        feature_id = str(item.get("id", ""))
        if not feature_id or feature_id in merged:
            continue
        extension_point = str(item.get("extension_point", ""))
        evidence = target_override.get("evidence", "")
        if extension_point:
            evidence = f"{evidence} / {extension_point}" if evidence else extension_point
        merged[feature_id] = {
            "weight": target_override["weight"],
            "rationale": target_override["rationale"].replace("{product}", product),
            "evidence": evidence,
        }
    return merged


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


def _platform_verified_readiness() -> dict[str, Any]:
    path = repo_root() / "configs" / "platform_targets.json"
    if not path.exists():
        return {
            "target_percent": 100.0,
            "overall": _platform_overall([]),
            "targets": [],
        }
    data = json.loads(path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    for item in data.get("release_architectures", []):
        score, status, rationale = _release_target_readiness(item)
        rows.append(
            _platform_row(
                target=str(item.get("id", "")),
                platform=str(item.get("platform", "")),
                cpu_arch=str(item.get("cpu_arch", "")),
                release_tier=str(item.get("release_tier", "")),
                channel=str(item.get("github_release_channel", "")),
                status=status,
                rationale=rationale,
                score=score,
                kind="release_architecture",
            )
        )
    for item in data.get("windows_legacy_targets", []):
        score, status, rationale = _legacy_windows_readiness(item)
        rows.append(
            _platform_row(
                target=str(item.get("version", "")),
                platform="Windows",
                cpu_arch="legacy",
                release_tier=str(item.get("host_tier", "")),
                channel="legacy-windows",
                status=status,
                rationale=rationale,
                score=score,
                kind="legacy_windows",
                remote_target_tier=str(item.get("remote_target_tier", "")),
            )
        )
    return {
        "target_percent": 100.0,
        "method": (
            "Default native release targets score 100%. Manual script-native, "
            "Termux/Web and legacy Windows rows keep separate partial readiness "
            "until their native installers or host support are verified."
        ),
        "overall": _platform_overall(rows),
        "targets": rows,
    }


def _release_target_readiness(item: dict[str, Any]) -> tuple[float, str, str]:
    channel = str(item.get("github_release_channel", ""))
    if channel == "default-native":
        return 100.0, "verified-default-native", "Default GitHub release channel with native artifacts."
    if channel == "manual-script-native":
        return 70.0, "manual-script-supported", "Native artifacts are declared but require a matching manual builder."
    if channel == "default-termux-web":
        return 85.0, "termux-web-default", "Termux and Web/PWA bundles ship by default; APK/native GUI is not present."
    return 50.0, "declared-unclassified", "Release target is declared but lacks a recognized readiness channel."


def _legacy_windows_readiness(item: dict[str, Any]) -> tuple[float, str, str]:
    host_tier = str(item.get("host_tier", ""))
    if host_tier == "best-effort-source":
        return 60.0, "best-effort-source-host", "Source install may work with compatible Python and clients."
    if host_tier == "legacy-source-only":
        return 45.0, "legacy-source-only", "Modern native artifacts are not guaranteed for this host."
    if host_tier == "remote-target-only":
        return 25.0, "remote-target-only", "Managed as a remote target, not as a modern native host."
    return 30.0, "legacy-unclassified", "Legacy Windows target lacks a recognized host tier."


def _platform_row(
    *,
    target: str,
    platform: str,
    cpu_arch: str,
    release_tier: str,
    channel: str,
    status: str,
    rationale: str,
    score: float,
    kind: str,
    remote_target_tier: str | None = None,
) -> dict[str, Any]:
    row = {
        "target": target,
        "platform": platform,
        "cpu_arch": cpu_arch,
        "release_tier": release_tier,
        "channel": channel,
        "status": status,
        "rationale": rationale,
        "current_percent": round(score, 1),
        "target_percent": 100.0,
        "gap_percent": round(max(100.0 - score, 0.0), 1),
        "kind": kind,
    }
    if remote_target_tier is not None:
        row["remote_target_tier"] = remote_target_tier
    return row


def _platform_overall(rows: list[dict[str, Any]]) -> dict[str, Any]:
    current_percent = (
        sum(float(row["current_percent"]) for row in rows) / len(rows)
        if rows
        else 0.0
    )
    return {
        "product": "Overall",
        "target_count": len(rows),
        "current_percent": round(current_percent, 1),
        "target_percent": 100.0,
        "gap_percent": round(max(100.0 - current_percent, 0.0), 1),
    }

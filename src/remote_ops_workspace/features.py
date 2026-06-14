from __future__ import annotations

import hashlib
import json
import re
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

WORKFLOW_PARITY_LABEL = "release-backed product workflow parity"
WORKFLOW_PARITY_SCOPE = (
    "Counts requested public product feature families when this release provides an "
    "implemented adapter, optional dependency path, CLI workflow, GUI workflow, "
    "platform shell, or combined workflow tied to manifest evidence. This is not a "
    "claim of proprietary native clone parity or embedded protocol-engine parity."
)
LINUX_ACCEPTED_EVIDENCE_CHECKS = {
    "builder_preflight",
    "native_build",
    "native_smoke",
    "artifact_validation",
    "release_asset_attachment",
}
LINUX_ACCEPTED_EVIDENCE_MACHINES = {
    "linux-i386": {"i386", "i486", "i586", "i686", "x86"},
    "linux-armhf": {"armv6l", "armv7l", "armv7hl", "armhf"},
}
LINUX_ACCEPTED_EVIDENCE_LABELS = {
    "linux-i386": {"self-hosted", "linux", "i386"},
    "linux-armhf": {"self-hosted", "linux", "armhf"},
}
LINUX_ACCEPTED_EVIDENCE_ARTIFACTS = {
    "linux-i386": "extended-linux-i386-native-evidence",
    "linux-armhf": "extended-linux-armhf-native-evidence",
}
LINUX_ACCEPTED_EVIDENCE_TOOLS = {
    "bash",
    "curl",
    "dpkg-deb",
    "rpmbuild",
    "sha256sum",
    "sudo",
    "tar",
}
ACCEPTED_EVIDENCE_ARTIFACT_TEMPLATES = {
    "linux-i386": {
        "remote-ops-workspace-v{version}-linux-i386.deb",
        "remote-ops-workspace-v{version}-linux-i686.rpm",
        "remote-ops-workspace-v{version}-linux-i686.AppImage",
        "remote-ops-workspace-v{version}-linux-i686-native.tar.gz",
        "remote-ops-workspace-v{version}-linux-i686-native-manifest.json",
        "remote-ops-workspace-v{version}-linux-i686-native-SHA256SUMS.txt",
    },
    "linux-armhf": {
        "remote-ops-workspace-v{version}-linux-armhf.deb",
        "remote-ops-workspace-v{version}-linux-armv7hl.rpm",
        "remote-ops-workspace-v{version}-linux-armhf.AppImage",
        "remote-ops-workspace-v{version}-linux-armhf-native.tar.gz",
        "remote-ops-workspace-v{version}-linux-armhf-native-manifest.json",
        "remote-ops-workspace-v{version}-linux-armhf-native-SHA256SUMS.txt",
    },
    "windows-xp-native-x86": {
        "remote-ops-workspace-v{version}-windows-xp-x86-native.zip",
        "remote-ops-workspace-v{version}-windows-xp-x86-native-manifest.json",
        "remote-ops-workspace-v{version}-windows-xp-x86-native-SHA256SUMS.txt",
    },
    "windows-xp-native-x64": {
        "remote-ops-workspace-v{version}-windows-xp-x64-native.zip",
        "remote-ops-workspace-v{version}-windows-xp-x64-native-manifest.json",
        "remote-ops-workspace-v{version}-windows-xp-x64-native-SHA256SUMS.txt",
    },
}
XP_ACCEPTED_EVIDENCE_CHECKS = {
    "xp_native_evidence_validation",
    "artifact_validation",
    "vm_or_host_smoke",
    "legacy_crypto_profile_scoped",
    "modern_defaults_unchanged",
    "release_asset_attachment",
}
XP_ACCEPTED_EVIDENCE_SMOKE_IDS = {
    "cli_launch",
    "gui_or_legacy_host_ui_launch",
    "loopback_profile_dry_run",
    "artifact_manifest_validation",
    "legacy_crypto_profile_scoped",
    "modern_defaults_unchanged",
}
XP_ACCEPTED_EVIDENCE_ARCHITECTURES = {
    "windows-xp-native-x86": "x86",
    "windows-xp-native-x64": "x64",
}
XP_ACCEPTED_EVIDENCE_TOOLCHAIN_FLAGS = {
    "separate_legacy_toolchain": True,
    "current_python_pyqt6_stack": False,
}
XP_ACCEPTED_EVIDENCE_SECURITY_FLAGS = {
    "legacy_crypto_profile_scoped": True,
    "modern_defaults_unchanged": True,
    "weak_crypto_global_default": False,
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
    workflow_parity_evidence = _workflow_parity_evidence(
        products=products,
        features=features,
        product_feature_mappings=product_feature_mappings,
        weights=production_parity_weights,
        coverage_rows=[
            production_parity_coverage["overall"],
            *production_parity_coverage["products"],
        ],
    )
    platform_verified_readiness = _platform_verified_readiness()

    return {
        "target_percent": feature_family_target,
        "method": feature_family_mapping["method"],
        "contract": scoring.get("contract", {}),
        "coverage_labels": {
            "feature_family_mapping": "public feature-family mapping",
            "adapter_ready_coverage": "adapter-ready coverage",
            "production_parity_coverage": WORKFLOW_PARITY_LABEL,
            "platform_verified_readiness": "platform verified readiness",
        },
        "workflow_parity_contract": {
            "metric": "production_parity_coverage",
            "label": WORKFLOW_PARITY_LABEL,
            "scope": WORKFLOW_PARITY_SCOPE,
            "native_clone_claimed": False,
        },
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
        "workflow_parity_evidence": workflow_parity_evidence,
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


def _workflow_parity_evidence(
    *,
    products: list[str],
    features: list[dict[str, Any]],
    product_feature_mappings: dict[str, set[str]],
    weights: dict[str, float],
    coverage_rows: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    coverage_by_product = {row["product"]: row for row in coverage_rows}
    evidence_by_id = {
        str(item["id"]): item
        for item in (_feature_evidence(feature) for feature in features)
    }
    rows: list[dict[str, Any]] = []
    feature_sets = [("Overall", features)]
    feature_sets.extend(
        (
            product,
            _features_for_product(features, product, product_feature_mappings),
        )
        for product in products
    )

    for product, product_features in feature_sets:
        feature_evidence = [
            _workflow_parity_feature(
                product=product,
                feature=item,
                evidence=evidence_by_id.get(str(item.get("id", "")), {}),
                product_feature_mappings=product_feature_mappings,
                weights=weights,
            )
            for item in product_features
        ]
        row = coverage_by_product.get(product, {})
        rows.append(
            {
                "product": product,
                "metric": "production_parity_coverage",
                "label": WORKFLOW_PARITY_LABEL,
                "evidence_contract": WORKFLOW_PARITY_SCOPE,
                "native_clone_claimed": False,
                "coverage_percent": row.get("current_percent", 0.0),
                "gap_percent": row.get("gap_percent", 0.0),
                "feature_count": len(product_features),
                "feature_ids": [str(item.get("id", "")) for item in product_features],
                "full_parity_feature_count": sum(
                    1
                    for item in feature_evidence
                    if item["counts_as_full_parity"] and item["release_backed"]
                ),
                "partial_feature_count": sum(
                    1 for item in feature_evidence if not item["counts_as_full_parity"]
                ),
                "missing_release_evidence_count": sum(
                    1
                    for item in feature_evidence
                    if item["counts_as_full_parity"] and not item["release_backed"]
                ),
                "feature_evidence": feature_evidence,
            }
        )
    return rows


def _workflow_parity_feature(
    *,
    product: str,
    feature: dict[str, Any],
    evidence: dict[str, Any],
    product_feature_mappings: dict[str, set[str]],
    weights: dict[str, float],
) -> dict[str, Any]:
    feature_id = str(feature.get("id", ""))
    status = str(feature.get("status", ""))
    extension_point = str(feature.get("extension_point", ""))
    status_weight = float(weights.get(status, 0.0))
    counts_as_full_parity = status_weight >= 1.0
    evidence_count = int(evidence.get("evidence_count", 0))
    release_backed = (
        counts_as_full_parity
        and status.startswith("implemented")
        and bool(extension_point)
        and evidence_count >= 3
    )
    return {
        "id": feature_id,
        "name": feature.get("name", ""),
        "status": status,
        "implementation_kind": evidence.get(
            "implementation_kind",
            STATUS_EVIDENCE_TYPES.get(status, "unknown"),
        ),
        "extension_point": extension_point,
        "status_weight": round(status_weight, 2),
        "counts_as_full_parity": counts_as_full_parity,
        "release_backed": release_backed,
        "product_mapping_source": _product_mapping_source(
            product,
            feature,
            product_feature_mappings,
        ),
        "evidence_count": evidence_count,
        "evidence_refs": [
            f"{item.get('type', '')}:{item.get('ref', '')}"
            for item in evidence.get("evidence", [])
            if item.get("ref")
        ],
    }


def _product_mapping_source(
    product: str,
    feature: dict[str, Any],
    product_feature_mappings: dict[str, set[str]],
) -> str:
    if product == "Overall":
        return "overall-manifest-feature"
    feature_id = str(feature.get("id", ""))
    if feature_id in product_feature_mappings.get(product, set()):
        return "explicit-product-feature-mapping"
    if any(product in str(source) for source in feature.get("inspired_by", [])):
        return "feature-inspired-by"
    return "implicit-product-match"


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


def _platform_verified_readiness(
    *,
    platform_data: dict[str, Any] | None = None,
    evidence_registry: dict[str, Any] | None = None,
) -> dict[str, Any]:
    path = repo_root() / "configs" / "platform_targets.json"
    evidence_data = (
        evidence_registry
        if evidence_registry is not None
        else _platform_verified_evidence_registry()
    )
    if platform_data is None and not path.exists():
        return {
            "target_percent": 100.0,
            "overall": _platform_overall([]),
            "targets": [],
        }
    data = platform_data or json.loads(path.read_text(encoding="utf-8"))
    rows: list[dict[str, Any]] = []
    for item in data.get("release_architectures", []):
        score, status, rationale = _release_target_readiness(item, evidence_data)
        target = str(item.get("id", ""))
        row = _platform_row(
            target=target,
            platform=str(item.get("platform", "")),
            cpu_arch=str(item.get("cpu_arch", "")),
            release_tier=str(item.get("release_tier", "")),
            channel=str(item.get("github_release_channel", "")),
            status=status,
            rationale=rationale,
            score=score,
            kind="release_architecture",
            verified_readiness_scope=_release_target_verified_scope(item, evidence_data),
        )
        if target in {"linux-i386", "linux-armhf"}:
            row.update(_single_target_evidence_status(evidence_data, target))
        rows.append(row)
    for item in data.get("windows_legacy_targets", []):
        score, status, rationale = _legacy_windows_readiness(item, evidence_data)
        remote_target_coverage = item.get("remote_target_coverage_percent")
        version = str(item.get("version", ""))
        row = _platform_row(
            target=version,
            platform="Windows",
            cpu_arch="legacy",
            release_tier=str(item.get("host_tier", "")),
            channel="legacy-windows",
            status=status,
            rationale=rationale,
            score=score,
            kind="legacy_windows",
            remote_target_tier=str(item.get("remote_target_tier", "")),
            remote_target_coverage_percent=(
                float(remote_target_coverage) if remote_target_coverage is not None else None
            ),
            legacy_architectures=[str(arch) for arch in item.get("architectures", [])],
            security_profile=str(item.get("security_profile", "")),
            supported_remote_protocol_count=len(item.get("supported_remote_protocols", [])),
            verified_readiness_scope=_legacy_windows_verified_scope(item, evidence_data),
        )
        if version == "Windows XP":
            row.update(_windows_xp_evidence_status(evidence_data))
        rows.append(row)
    return {
        "target_percent": 100.0,
        "method": (
            "Overall verified readiness averages only verified default-native "
            "and verified mobile Web/PWA release targets. Manual script-native "
            "and legacy Windows rows remain visible as extended compatibility "
            "rows outside the verified-readiness denominator until matching "
            "release or host verification exists in configs/platform_verified_evidence.json."
        ),
        "overall": _platform_overall(rows),
        "targets": rows,
    }


def _release_target_readiness(
    item: dict[str, Any],
    evidence_registry: dict[str, Any] | None = None,
) -> tuple[float, str, str]:
    target = str(item.get("id", ""))
    if target in {"linux-i386", "linux-armhf"} and _has_accepted_evidence(
        evidence_registry,
        target,
    ):
        return (
            100.0,
            "verified-accepted-native-evidence",
            "Accepted platform evidence records validate native build, smoke, artifact and release evidence.",
        )
    channel = str(item.get("github_release_channel", ""))
    if channel == "default-native":
        return 100.0, "verified-default-native", "Default GitHub release channel with native artifacts."
    if channel == "manual-script-native":
        return 70.0, "manual-script-supported", "Native artifacts are declared but require a matching manual builder."
    if channel == "default-termux-web":
        return (
            100.0,
            "verified-termux-web-mobile",
            "Termux/Web/PWA mobile contract is covered by static PWA checks and Android emulator CI; APK/native GUI is not present.",
        )
    if channel == "default-web-pwa":
        return (
            100.0,
            "verified-ios-web-pwa",
            "iOS/iPadOS Web/PWA contract is covered by static PWA checks and iOS simulator CI; native mobile app is not present.",
        )
    return 50.0, "declared-unclassified", "Release target is declared but lacks a recognized readiness channel."


def _release_target_verified_scope(
    item: dict[str, Any],
    evidence_registry: dict[str, Any] | None = None,
) -> bool:
    target = str(item.get("id", ""))
    if target in {"linux-i386", "linux-armhf"} and _has_accepted_evidence(
        evidence_registry,
        target,
    ):
        return True
    return str(item.get("github_release_channel", "")) in {
        "default-native",
        "default-termux-web",
        "default-web-pwa",
    }


def _legacy_windows_readiness(
    item: dict[str, Any],
    evidence_registry: dict[str, Any] | None = None,
) -> tuple[float, str, str]:
    if str(item.get("version", "")) == "Windows XP" and _has_windows_xp_native_evidence(
        evidence_registry,
    ):
        return (
            100.0,
            "verified-xp-native-host-evidence",
            "Accepted XP x86 and x64 native-host evidence records validate the legacy host toolchain.",
        )
    if str(item.get("version", "")) == "Windows XP" and _has_partial_windows_xp_native_evidence(
        evidence_registry,
    ):
        return (
            25.0,
            "partial-xp-native-host-evidence",
            "Accepted XP native-host evidence is partial; both XP x86 and XP x64 records are required.",
        )
    host_tier = str(item.get("host_tier", ""))
    if host_tier == "best-effort-source":
        return 60.0, "best-effort-source-host", "Source install may work with compatible Python and clients."
    if host_tier == "legacy-source-only":
        return 45.0, "legacy-source-only", "Modern native artifacts are not guaranteed for this host."
    if host_tier == "remote-target-only":
        return 25.0, "remote-target-only", "Managed as a remote target, not as a modern native host."
    return 30.0, "legacy-unclassified", "Legacy Windows target lacks a recognized host tier."


def _legacy_windows_verified_scope(
    item: dict[str, Any],
    evidence_registry: dict[str, Any] | None = None,
) -> bool:
    return str(item.get("version", "")) == "Windows XP" and _has_windows_xp_native_evidence(
        evidence_registry,
    )


def _platform_verified_evidence_registry() -> dict[str, Any]:
    path = repo_root() / "configs" / "platform_verified_evidence.json"
    if not path.exists():
        return {"schema_version": 1, "accepted_evidence": []}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"schema_version": 1, "accepted_evidence": []}
    return data if isinstance(data, dict) else {"schema_version": 1, "accepted_evidence": []}


def _promotion_config_sha256() -> str:
    path = repo_root() / "configs" / "platform_parity_promotion.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(data, dict):
        return ""
    return _json_sha256(data)


def _xp_native_evidence_contract_sha256() -> str:
    path = repo_root() / "configs" / "xp_native_evidence_contract.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(data, dict):
        return ""
    return _json_sha256(data)


def _json_sha256(data: dict[str, Any]) -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _accepted_evidence_targets(evidence_registry: dict[str, Any] | None) -> set[str]:
    return {str(item.get("target")) for item in _accepted_evidence_entries(evidence_registry)}


def _accepted_evidence_entries(evidence_registry: dict[str, Any] | None) -> list[dict[str, Any]]:
    if not isinstance(evidence_registry, dict):
        return []
    rows = evidence_registry.get("accepted_evidence", [])
    if not isinstance(rows, list):
        return []
    return [item for item in rows if isinstance(item, dict) and _is_accepted_evidence_entry(item)]


def _is_accepted_evidence_entry(item: dict[str, Any]) -> bool:
    target = str(item.get("target", ""))
    if item.get("status") != "accepted" or item.get("readiness_percent") != 100.0:
        return False
    if not re.fullmatch(r"v\d+\.\d+\.\d+", str(item.get("release_tag", ""))):
        return False
    if str(item.get("promotion_config_sha256", "")) != _promotion_config_sha256():
        return False
    if not _has_artifact_validation_command(item, target):
        return False
    if not _has_release_assets_and_hashes(item, target):
        return False
    if target in LINUX_ACCEPTED_EVIDENCE_MACHINES:
        return _is_linux_accepted_evidence_entry(item, target)
    if target in XP_ACCEPTED_EVIDENCE_ARCHITECTURES:
        return _is_xp_accepted_evidence_entry(item, target)
    return False


def _has_artifact_validation_command(item: dict[str, Any], target: str) -> bool:
    release_tag = str(item.get("release_tag", ""))
    command = str(item.get("artifact_validation_command", ""))
    expected_prefix = f"python scripts/check_platform_promotion_artifacts.py --target {target} "
    if not command.startswith(expected_prefix):
        return False
    tags = re.findall(r"(?:^|\s)--tag\s+(\S+)(?=\s|$)", command)
    return tags == [release_tag]


def _has_release_assets_and_hashes(item: dict[str, Any], target: str) -> bool:
    release_assets = item.get("release_asset_urls")
    artifact_hashes = item.get("artifact_sha256")
    release_tag = str(item.get("release_tag", ""))
    expected_names = _expected_accepted_artifact_names(target, release_tag)
    if not expected_names:
        return False
    if not isinstance(release_assets, list) or not release_assets:
        return False
    if not isinstance(artifact_hashes, dict) or not artifact_hashes:
        return False
    repositories: set[str] = set()
    asset_names: list[str] = []
    for url in release_assets:
        match = re.fullmatch(
            r"https://github\.com/([^/]+/[^/]+)/releases/download/(v\d+\.\d+\.\d+)/.+",
            str(url),
        )
        if not match or match.group(2) != release_tag:
            return False
        repositories.add(match.group(1))
        asset_names.append(Path(str(url)).name)
    if len(repositories) != 1:
        return False
    if len(asset_names) != len(set(asset_names)):
        return False
    hashes = {str(name): str(value) for name, value in artifact_hashes.items()}
    if set(asset_names) != expected_names or set(hashes) != expected_names:
        return False
    return all(re.fullmatch(r"[0-9a-f]{64}", digest) for digest in hashes.values())


def _expected_accepted_artifact_names(target: str, release_tag: str) -> set[str]:
    templates = ACCEPTED_EVIDENCE_ARTIFACT_TEMPLATES.get(target)
    if templates is None:
        return set()
    version = release_tag.removeprefix("v")
    return {template.format(version=version) for template in templates}


def _is_linux_accepted_evidence_entry(item: dict[str, Any], target: str) -> bool:
    if item.get("evidence_type") != "extended-linux-native":
        return False
    if item.get("workflow") != ".github/workflows/extended-platform-evidence.yml":
        return False
    if not _has_linux_workflow_inputs(item, target):
        return False
    workflow_repository = _github_actions_repository(item.get("workflow_run_url"))
    if not workflow_repository:
        return False
    if _release_asset_repositories(item.get("release_asset_urls")) != {workflow_repository}:
        return False
    if item.get("artifact_name") != LINUX_ACCEPTED_EVIDENCE_ARTIFACTS[target]:
        return False
    labels = {str(label) for label in item.get("runner_labels", [])}
    if not LINUX_ACCEPTED_EVIDENCE_LABELS[target].issubset(labels):
        return False
    checks = {str(check) for check in item.get("checks", [])}
    if not LINUX_ACCEPTED_EVIDENCE_CHECKS.issubset(checks):
        return False
    return _has_linux_builder_identity_binding(item, target)


def _has_linux_workflow_inputs(item: dict[str, Any], target: str) -> bool:
    raw_inputs = item.get("workflow_inputs")
    if not isinstance(raw_inputs, dict):
        return False
    release_tag = str(item.get("release_tag", ""))
    base_url = str(raw_inputs.get("release_asset_base_url", "")).rstrip("/")
    if raw_inputs.get("target") != target or raw_inputs.get("release_tag") != release_tag:
        return False
    if not base_url.startswith("https://github.com/") or not base_url.endswith(f"/releases/download/{release_tag}"):
        return False
    release_assets = item.get("release_asset_urls")
    if not isinstance(release_assets, list):
        return False
    return all(str(url).startswith(f"{base_url}/") for url in release_assets)


def _github_actions_repository(raw_url: Any) -> str:
    match = re.fullmatch(r"https://github\.com/([^/]+/[^/]+)/actions/runs/\d+/?", str(raw_url))
    return match.group(1) if match else ""


def _release_asset_repositories(raw_assets: Any) -> set[str]:
    if not isinstance(raw_assets, list):
        return set()
    repositories: set[str] = set()
    for url in raw_assets:
        match = re.fullmatch(
            r"https://github\.com/([^/]+/[^/]+)/releases/download/v\d+\.\d+\.\d+/.+",
            str(url),
        )
        if match:
            repositories.add(match.group(1))
    return repositories


def _has_linux_builder_identity(raw_identity: Any, target: str) -> bool:
    if not isinstance(raw_identity, dict):
        return False
    expected_machines = LINUX_ACCEPTED_EVIDENCE_MACHINES[target]
    if raw_identity.get("schema_version") != 1 or raw_identity.get("target") != target:
        return False
    if not str(raw_identity.get("sys_platform", "")).startswith("linux"):
        return False
    if str(raw_identity.get("platform_machine", "")).lower() not in expected_machines:
        return False
    if str(raw_identity.get("uname_machine", "")).lower() not in expected_machines:
        return False
    if _python_version_tuple(str(raw_identity.get("python_version", ""))) < (3, 10):
        return False
    tools = raw_identity.get("required_tools")
    if not isinstance(tools, dict):
        return False
    return all(str(tools.get(tool, "")).strip() for tool in LINUX_ACCEPTED_EVIDENCE_TOOLS)


def _has_linux_builder_identity_binding(item: dict[str, Any], target: str) -> bool:
    raw_identity = item.get("builder_identity")
    digest = str(item.get("builder_identity_sha256", ""))
    if not isinstance(raw_identity, dict) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        return False
    return digest == _json_sha256(raw_identity) and _has_linux_builder_identity(raw_identity, target)


def _is_xp_accepted_evidence_entry(item: dict[str, Any], target: str) -> bool:
    if item.get("evidence_type") != "windows-xp-native-host":
        return False
    if item.get("architecture") != XP_ACCEPTED_EVIDENCE_ARCHITECTURES[target]:
        return False
    if item.get("separate_legacy_toolchain") is not True:
        return False
    if item.get("current_python_pyqt6_stack") is not False:
        return False
    if item.get("native_evidence_validation_command") != (
        "python scripts/check_xp_native_evidence.py --evidence <evidence.json> --assets-dir <artifact-dir>"
    ):
        return False
    if not re.fullmatch(r"[0-9a-f]{64}", str(item.get("xp_evidence_sha256", ""))):
        return False
    if str(item.get("xp_evidence_contract_sha256", "")) != _xp_native_evidence_contract_sha256():
        return False
    if not _has_xp_evidence_summary(item, target):
        return False
    smoke_hashes = item.get("xp_smoke_evidence_sha256")
    if not isinstance(smoke_hashes, dict):
        return False
    if set(str(key) for key in smoke_hashes) != XP_ACCEPTED_EVIDENCE_SMOKE_IDS:
        return False
    if not all(re.fullmatch(r"[0-9a-f]{64}", str(value)) for value in smoke_hashes.values()):
        return False
    checks = {str(check) for check in item.get("checks", [])}
    return XP_ACCEPTED_EVIDENCE_CHECKS.issubset(checks)


def _has_xp_evidence_summary(item: dict[str, Any], target: str) -> bool:
    summary = item.get("xp_evidence_summary")
    if not isinstance(summary, dict):
        return False
    if summary.get("target") != target or summary.get("release_tag") != item.get("release_tag"):
        return False
    os_data = summary.get("os")
    if not isinstance(os_data, dict):
        return False
    if os_data.get("name") != "Windows XP":
        return False
    if os_data.get("architecture") != XP_ACCEPTED_EVIDENCE_ARCHITECTURES[target]:
        return False
    if not str(os_data.get("service_pack", "")).strip():
        return False
    toolchain = summary.get("toolchain")
    if not isinstance(toolchain, dict):
        return False
    if any(toolchain.get(flag) is not expected for flag, expected in XP_ACCEPTED_EVIDENCE_TOOLCHAIN_FLAGS.items()):
        return False
    security = summary.get("security")
    if not isinstance(security, dict):
        return False
    if any(security.get(flag) is not expected for flag, expected in XP_ACCEPTED_EVIDENCE_SECURITY_FLAGS.items()):
        return False
    smoke_ids = summary.get("smoke_ids")
    return isinstance(smoke_ids, list) and {str(smoke_id) for smoke_id in smoke_ids} == XP_ACCEPTED_EVIDENCE_SMOKE_IDS


def _python_version_tuple(version: str) -> tuple[int, int]:
    match = re.fullmatch(r"(\d+)\.(\d+)(?:\.\d+)?", version)
    if not match:
        return (0, 0)
    return int(match.group(1)), int(match.group(2))


def _has_accepted_evidence(
    evidence_registry: dict[str, Any] | None,
    target: str,
) -> bool:
    return target in _accepted_evidence_targets(evidence_registry)


def _has_windows_xp_native_evidence(evidence_registry: dict[str, Any] | None) -> bool:
    required = {"windows-xp-native-x86", "windows-xp-native-x64"}
    entries = {
        str(item.get("target")): item
        for item in _accepted_evidence_entries(evidence_registry)
        if str(item.get("target")) in required
    }
    if not required.issubset(entries):
        return False
    release_tags = {str(entries[target].get("release_tag", "")) for target in required}
    return len(release_tags) == 1 and "" not in release_tags


def _has_partial_windows_xp_native_evidence(evidence_registry: dict[str, Any] | None) -> bool:
    targets = _accepted_evidence_targets(evidence_registry)
    required = {"windows-xp-native-x86", "windows-xp-native-x64"}
    return bool(required & targets) and not _has_windows_xp_native_evidence(evidence_registry)


def _single_target_evidence_status(
    evidence_registry: dict[str, Any] | None,
    target: str,
) -> dict[str, Any]:
    accepted = target in _accepted_evidence_targets(evidence_registry)
    return {
        "accepted_evidence_required_targets": [target],
        "accepted_evidence_present_targets": [target] if accepted else [],
        "accepted_evidence_missing_targets": [] if accepted else [target],
    }


def _windows_xp_evidence_status(evidence_registry: dict[str, Any] | None) -> dict[str, Any]:
    required = ["windows-xp-native-x86", "windows-xp-native-x64"]
    entries = {
        str(item.get("target")): item
        for item in _accepted_evidence_entries(evidence_registry)
        if str(item.get("target")) in required
    }
    accepted_targets = set(entries)
    present = [target for target in required if target in accepted_targets]
    missing = [target for target in required if target not in accepted_targets]
    return {
        "accepted_evidence_required_targets": required,
        "accepted_evidence_present_targets": present,
        "accepted_evidence_missing_targets": missing,
        "accepted_evidence_release_tags": {
            target: str(entries[target].get("release_tag", ""))
            for target in present
            if entries[target].get("release_tag")
        },
    }


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
    verified_readiness_scope: bool,
    remote_target_tier: str | None = None,
    remote_target_coverage_percent: float | None = None,
    legacy_architectures: list[str] | None = None,
    security_profile: str | None = None,
    supported_remote_protocol_count: int | None = None,
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
        "verified_readiness_scope": verified_readiness_scope,
    }
    if remote_target_tier is not None:
        row["remote_target_tier"] = remote_target_tier
    if remote_target_coverage_percent is not None:
        row["remote_target_coverage_percent"] = round(remote_target_coverage_percent, 1)
    if legacy_architectures:
        row["legacy_architectures"] = legacy_architectures
    if security_profile:
        row["security_profile"] = security_profile
    if supported_remote_protocol_count is not None:
        row["supported_remote_protocol_count"] = supported_remote_protocol_count
    return row


def _platform_overall(rows: list[dict[str, Any]]) -> dict[str, Any]:
    scoped_rows = [row for row in rows if row.get("verified_readiness_scope") is True]
    current_percent = (
        sum(float(row["current_percent"]) for row in scoped_rows) / len(scoped_rows)
        if scoped_rows
        else 0.0
    )
    return {
        "product": "Verified targets",
        "target_count": len(scoped_rows),
        "tracked_target_count": len(rows),
        "extended_target_count": len(rows) - len(scoped_rows),
        "current_percent": round(current_percent, 1),
        "target_percent": 100.0,
        "gap_percent": round(max(100.0 - current_percent, 0.0), 1),
    }

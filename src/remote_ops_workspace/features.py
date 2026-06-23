from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
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
LINUX_ACCEPTED_EVIDENCE_WORKFLOW = ".github/workflows/extended-platform-evidence.yml"
LINUX_ACCEPTED_EVIDENCE_MACHINES = {
    "linux-i386": {"i386", "i486", "i586", "i686", "x86"},
    "linux-armhf": {"armv6l", "armv7l", "armv7hl", "armhf"},
}
LINUX_ACCEPTED_EVIDENCE_LABELS = {
    "linux-i386": {"self-hosted", "linux", "i386"},
    "linux-armhf": {"self-hosted", "linux", "armhf"},
}
LINUX_ACCEPTED_EVIDENCE_ARTIFACT_TEMPLATES = {
    "linux-i386": "extended-linux-evidence-linux-i386-{release_tag}",
    "linux-armhf": "extended-linux-evidence-linux-armhf-{release_tag}",
}
LINUX_ACCEPTED_EVIDENCE_BUILD_COMMANDS = {
    "linux-i386": "TARGET_ARCH=i386 PYTHON_BIN=.venv-native/bin/python bash scripts/make_linux_native.sh",
    "linux-armhf": "TARGET_ARCH=armhf PYTHON_BIN=.venv-native/bin/python bash scripts/make_linux_native.sh",
}
LINUX_ACCEPTED_EVIDENCE_SMOKE_COMMANDS = {
    "linux-i386": "bash scripts/smoke_linux_native.sh --arch i386 --dist native-dist/linux --target linux-i386",
    "linux-armhf": "bash scripts/smoke_linux_native.sh --arch armhf --dist native-dist/linux --target linux-armhf",
}
LINUX_ACCEPTED_EVIDENCE_TOOLS = {
    "bash",
    "curl",
    "dpkg",
    "dpkg-deb",
    "getconf",
    "openssl",
    "rpm",
    "rpmbuild",
    "sha256sum",
    "sudo",
    "tar",
}
LINUX_ACCEPTED_EVIDENCE_SMOKE_IDS = {
    "native_smoke",
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
XP_ACCEPTED_EVIDENCE_WORKFLOW = ".github/workflows/xp-native-evidence.yml"
XP_ACCEPTED_EVIDENCE_WORKFLOW_INPUT_KEYS = {
    "target",
    "release_tag",
    "release_asset_base_url",
    "assets_dir",
    "evidence_file",
    "evidence_dir",
}
XP_ACCEPTED_EVIDENCE_SERVICE_PACKS = {
    "windows-xp-native-x86": "SP3",
    "windows-xp-native-x64": "SP2",
}
XP_ACCEPTED_EVIDENCE_EDITIONS = {
    "windows-xp-native-x64": "Professional x64 Edition",
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
ACCEPTED_EVIDENCE_SECURITY_PATCH_EVIDENCE = {
    "tls_minimum_modern_profiles": "TLS 1.2",
    "tls_preferred_modern_profiles": "TLS 1.3",
    "legacy_compatibility_profile": "isolated-opt-in",
    "cve_patch_reviewed": True,
}
ACCEPTED_EVIDENCE_REVIEW_BUNDLE_TYPES = {
    "linux-i386": "extended-linux-native-evidence",
    "linux-armhf": "extended-linux-native-evidence",
    "windows-xp-native-x86": "windows-xp-native-host-evidence",
    "windows-xp-native-x64": "windows-xp-native-host-evidence",
}
PROTECTED_PLATFORM_GOAL_TARGETS = (
    "linux-i386",
    "linux-armhf",
    "windows-xp-native-x86",
    "windows-xp-native-x64",
)
RESERVED_WORKSPACE_ROOTS = {".agents", ".codex", ".git", ".github"}
FILE_LIKE_DIRECTORY_SUFFIXES = (
    ".appimage",
    ".deb",
    ".exe",
    ".gz",
    ".json",
    ".log",
    ".msi",
    ".rpm",
    ".sha256",
    ".tar",
    ".tgz",
    ".txt",
    ".xz",
    ".zip",
)
RELEASE_ASSET_SOURCE_TYPES = {"github-actions-artifact"}
GITHUB_OWNER_RE = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?"
GITHUB_REPOSITORY_RE = rf"{GITHUB_OWNER_RE}/[A-Za-z0-9._-]+"
GITHUB_RELEASE_BASE_RE = re.compile(
    rf"^https://github\.com/({GITHUB_REPOSITORY_RE})/releases/download/(v\d+\.\d+\.\d+)$"
)
GITHUB_RELEASE_ASSET_RE = re.compile(
    rf"^https://github\.com/({GITHUB_REPOSITORY_RE})/releases/download/(v\d+\.\d+\.\d+)/.+$"
)
GITHUB_RELEASE_ASSET_FILE_RE = re.compile(
    rf"^https://github\.com/({GITHUB_REPOSITORY_RE})/releases/download/(v\d+\.\d+\.\d+)/(.+)$"
)
GITHUB_ACTIONS_RUN_RE = re.compile(rf"^https://github\.com/({GITHUB_REPOSITORY_RE})/actions/runs/\d+/?$")


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
        "protected_goal_parity": _protected_platform_goal_parity(evidence_data),
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


def _protected_platform_goal_parity(evidence_registry: dict[str, Any] | None) -> dict[str, Any]:
    entries = {
        str(item.get("target")): item
        for item in _accepted_evidence_entries(evidence_registry)
        if str(item.get("target")) in PROTECTED_PLATFORM_GOAL_TARGETS
    }
    (
        release_tag,
        release_repository,
        release_source_head,
        release_targets,
    ) = _best_protected_platform_release_group(entries)
    present = [target for target in PROTECTED_PLATFORM_GOAL_TARGETS if target in release_targets]
    missing = [target for target in PROTECTED_PLATFORM_GOAL_TARGETS if target not in release_targets]
    aggregate_present = [target for target in PROTECTED_PLATFORM_GOAL_TARGETS if target in entries]
    aggregate_missing = [target for target in PROTECTED_PLATFORM_GOAL_TARGETS if target not in entries]
    release_tags = sorted(
        {
            str(entry.get("release_tag", ""))
            for entry in entries.values()
            if entry.get("release_tag")
        },
        key=_release_tag_version_tuple,
    )
    release_repositories = sorted(
        {
            repository
            for entry in entries.values()
            for repository in _release_asset_repositories(entry.get("release_asset_urls"))
        }
    )
    release_source_heads = sorted(
        {
            source_head
            for entry in entries.values()
            if (source_head := _release_source_head(entry))
        }
    )
    target_count = len(PROTECTED_PLATFORM_GOAL_TARGETS)
    accepted_count = len(present)
    current_percent = (accepted_count / target_count * 100.0) if target_count else 0.0
    complete = accepted_count == target_count
    release_consistent = len(release_tags) <= 1
    release_repository_consistent = len(release_repositories) <= 1
    release_source_head_consistent = len(release_source_heads) <= 1
    if complete:
        status = "complete"
    elif release_repositories and not release_repository_consistent:
        status = "mixed-release-repository-evidence"
    elif release_tags and not release_consistent:
        status = "mixed-release-evidence"
    elif release_source_heads and not release_source_head_consistent:
        status = "mixed-release-source-evidence"
    else:
        status = "missing-accepted-evidence"
    return {
        "metric": "protected_platform_goal_parity",
        "target_percent": 100.0,
        "current_percent": round(current_percent, 1),
        "gap_percent": round(max(100.0 - current_percent, 0.0), 1),
        "target_count": target_count,
        "accepted_target_count": accepted_count,
        "aggregate_accepted_target_count": len(aggregate_present),
        "required_targets": list(PROTECTED_PLATFORM_GOAL_TARGETS),
        "accepted_targets": present,
        "missing_targets": missing,
        "aggregate_accepted_targets": aggregate_present,
        "aggregate_missing_targets": aggregate_missing,
        "accepted_evidence_release_tags": {
            target: str(entries[target].get("release_tag", ""))
            for target in aggregate_present
            if entries[target].get("release_tag")
        },
        "target_evidence_requirements": _protected_platform_goal_target_requirements(
            present_targets=set(present),
            release_tag=release_tag,
        ),
        "release_tag": release_tag,
        "release_tags": release_tags,
        "release_repository": release_repository,
        "release_repositories": release_repositories,
        "release_source_head": release_source_head,
        "release_source_heads": release_source_heads,
        "release_consistent": release_consistent,
        "release_repository_consistent": release_repository_consistent,
        "release_source_head_consistent": release_source_head_consistent,
        "complete": complete,
        "status": status,
        "scope": (
            "Counts only Linux i386, Linux armhf, Windows XP native x86 and "
            "Windows XP native x64 accepted evidence records for one release_tag, "
            "one GitHub release repository, and one release source head SHA. "
            "The broader platform_verified_readiness overall score does not promote "
            "this goal unless this block reaches 100% for a single release."
        ),
    }


def _protected_platform_goal_target_requirements(
    *,
    present_targets: set[str],
    release_tag: str,
) -> list[dict[str, Any]]:
    promotion = _platform_parity_promotion_config()
    entries = {
        str(item.get("id", "")): item
        for item in promotion.get("protected_targets", [])
        if isinstance(item, dict)
    }
    rows: list[dict[str, Any]] = []
    for target in PROTECTED_PLATFORM_GOAL_TARGETS:
        entry = entries.get(target, {})
        requirements = entry.get("promotion_to_100_requires", {})
        if not isinstance(requirements, dict):
            requirements = {}
        accepted = target in present_targets
        row: dict[str, Any] = {
            "target": target,
            "accepted": accepted,
            "status": "accepted" if accepted else "missing-accepted-evidence",
            "current_status": str(entry.get("current_status", "")),
            "current_readiness_percent": entry.get("current_readiness_percent"),
            "target_readiness_percent": entry.get("target_readiness_percent", 100.0),
            "support_boundary": _protected_platform_support_boundary(target, entry),
            "accepted_evidence_record": {
                "registry": "configs/platform_verified_evidence.json",
                "target": target,
                "status": "accepted",
                "readiness_percent": 100.0,
                "release_tag": release_tag or "v<project.version>",
                "review_bundle_required": True,
            },
            "required_artifacts": _requirement_list(
                requirements.get("required_artifacts", requirements.get("native_artifacts", []))
            ),
            "required_review_bundle_files": _requirement_list(
                requirements.get("review_bundle_files", [])
            ),
            "required_commands": _protected_platform_required_commands(requirements),
        }
        builder_or_host = requirements.get("workflow_runner_evidence") or requirements.get(
            "xp_vm_or_self_hosted_runner"
        )
        if builder_or_host:
            row["builder_or_host_evidence"] = str(builder_or_host)
        security_requirements = _requirement_list(requirements.get("security_requirements", []))
        if security_requirements:
            row["security_requirements"] = security_requirements
        smoke_evidence = _requirement_list(requirements.get("smoke_evidence", []))
        if smoke_evidence:
            row["smoke_evidence"] = smoke_evidence
        rows.append(row)
    return rows


def _platform_parity_promotion_config() -> dict[str, Any]:
    path = repo_root() / "configs" / "platform_parity_promotion.json"
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"protected_targets": []}
    return data if isinstance(data, dict) else {"protected_targets": []}


def _protected_platform_support_boundary(target: str, entry: dict[str, Any]) -> str:
    current = str(entry.get("current_status", ""))
    if target.startswith("linux-"):
        channel = str(entry.get("current_github_release_channel", ""))
        return (
            f"{target} remains {current} on {channel} until accepted builder, "
            "artifact, smoke and release evidence exists."
        )
    return (
        f"{target} remains Windows XP native-host {current}; XP remote-target "
        "coverage does not imply native-host readiness."
    )


def _requirement_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item) for item in value]


def _protected_platform_required_commands(requirements: dict[str, Any]) -> dict[str, str]:
    command_keys = (
        "artifact_validation_command",
        "native_evidence_validation_command",
        "local_evidence_preflight_command",
        "accepted_evidence_candidate_command",
        "review_bundle_command",
        "finalized_evidence_record_command",
    )
    return {
        key: str(requirements[key])
        for key in command_keys
        if requirements.get(key)
    }


def _best_protected_platform_release_group(
    entries: dict[str, dict[str, Any]],
) -> tuple[str, str, str, set[str]]:
    groups: dict[tuple[str, str, str], set[str]] = {}
    for target, entry in entries.items():
        release_tag = str(entry.get("release_tag", ""))
        repositories = _release_asset_repositories(entry.get("release_asset_urls"))
        source_head = _release_source_head(entry)
        if release_tag and len(repositories) == 1 and source_head:
            repository = next(iter(repositories))
            groups.setdefault((release_tag, repository, source_head), set()).add(target)
    if not groups:
        return "", "", "", set()
    (release_tag, repository, source_head), targets = max(
        groups.items(),
        key=lambda item: (len(item[1]), _release_tag_version_tuple(item[0][0]), item[0][1], item[0][2]),
    )
    return release_tag, repository, source_head, targets


def _release_tag_version_tuple(release_tag: str) -> tuple[int, int, int]:
    match = re.fullmatch(r"v(\d+)\.(\d+)\.(\d+)", release_tag)
    if not match:
        return (0, 0, 0)
    return int(match.group(1)), int(match.group(2)), int(match.group(3))


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
    if not _has_review_bundle_binding(item, target):
        return False
    if not _has_finalized_record_release_asset_url(item, target):
        return False
    if not _has_artifact_validation_command(item, target):
        return False
    if not _has_local_evidence_preflight_command(item, target):
        return False
    if not _has_release_assets_and_hashes(item, target):
        return False
    if not _has_release_asset_source_binding(item, target):
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
    asset_dirs = re.findall(r"(?:^|\s)--assets-dir\s+(\S+)(?=\s|$)", command)
    if len(asset_dirs) != 1 or "<" in asset_dirs[0] or ">" in asset_dirs[0]:
        return False
    if not _is_safe_xp_validation_path(
        asset_dirs[0],
        target=target,
        release_tag=release_tag,
        require_directory_hint=True,
        require_target_release_scope=(
            target in LINUX_ACCEPTED_EVIDENCE_MACHINES
            or target in XP_ACCEPTED_EVIDENCE_ARCHITECTURES
        ),
    ):
        return False
    tags = re.findall(r"(?:^|\s)--tag\s+(\S+)(?=\s|$)", command)
    return tags == [release_tag] and _command_flag_count(command, "--strict") == 1


def _has_local_evidence_preflight_command(item: dict[str, Any], target: str) -> bool:
    release_tag = str(item.get("release_tag", ""))
    command = str(item.get("local_evidence_preflight_command", ""))
    if not command.startswith("python scripts/check_platform_goal_local_evidence.py "):
        return False
    roots = _command_values(command, "--root")
    if len(roots) != 1 or not _is_safe_local_evidence_root(roots[0]):
        return False
    if _command_values(command, "--release-tag") != [release_tag]:
        return False
    if _command_values(command, "--target") != [target]:
        return False
    asset_dirs = _command_values(command, "--assets-dir")
    artifact_asset_dirs = _command_values(str(item.get("artifact_validation_command", "")), "--assets-dir")
    if len(asset_dirs) != 1 or "<" in asset_dirs[0] or ">" in asset_dirs[0]:
        return False
    if asset_dirs != artifact_asset_dirs:
        return False
    if not all(
        _path_stays_under_root(roots[0], path)
        for path in _local_evidence_preflight_paths(target, command)
    ):
        return False
    if target in LINUX_ACCEPTED_EVIDENCE_MACHINES:
        return _has_linux_local_evidence_preflight_command(item, target, command)
    if target in XP_ACCEPTED_EVIDENCE_ARCHITECTURES:
        return _has_xp_local_evidence_preflight_command(item, target, command)
    return False


def _is_safe_local_evidence_root(raw_root: str) -> bool:
    return raw_root == "." or _is_safe_xp_validation_path(raw_root, require_directory_hint=True)


def _local_evidence_preflight_paths(target: str, command: str) -> list[str]:
    paths = [*_command_values(command, "--assets-dir")]
    if target in LINUX_ACCEPTED_EVIDENCE_MACHINES:
        paths.extend(_command_values(command, "--linux-builder-evidence"))
        paths.extend(_command_values(command, "--linux-smoke-evidence"))
    elif target in XP_ACCEPTED_EVIDENCE_ARCHITECTURES:
        paths.extend(_command_values(command, "--xp-evidence"))
        paths.extend(_command_values(command, "--xp-evidence-dir"))
    return paths


def _path_stays_under_root(raw_root: str, raw_path: str) -> bool:
    root_parts = _relative_path_parts(raw_root)
    path_parts = _relative_path_parts(raw_path)
    return not root_parts or (
        len(path_parts) >= len(root_parts)
        and path_parts[: len(root_parts)] == root_parts
    )


def _relative_path_parts(raw_path: str) -> tuple[str, ...]:
    path = raw_path.strip()
    windows_path = PureWindowsPath(path)
    posix_path = PurePosixPath(path)
    if "\\" in path or windows_path.is_absolute() or bool(windows_path.drive):
        parts = windows_path.parts
    else:
        parts = posix_path.parts
    return tuple(part for part in parts if part not in ("", "."))


def _has_linux_local_evidence_preflight_command(
    item: dict[str, Any],
    target: str,
    command: str,
) -> bool:
    release_tag = str(item.get("release_tag", ""))
    if _command_values(command, "--xp-evidence") or _command_values(command, "--xp-evidence-dir"):
        return False
    builder_paths = _command_values(command, "--linux-builder-evidence")
    if len(builder_paths) != 1 or Path(builder_paths[0]).name != f"builder-identity-{target}.json":
        return False
    smoke_paths = _command_values(command, "--linux-smoke-evidence")
    if len(smoke_paths) != 1 or Path(smoke_paths[0]).name != f"native-smoke-{target}.log":
        return False
    if not _is_safe_xp_validation_path(
        builder_paths[0],
        target=target,
        release_tag=release_tag,
        require_json_hint=True,
        require_target_release_scope=True,
    ):
        return False
    if not _is_safe_xp_validation_path(
        smoke_paths[0],
        target=target,
        release_tag=release_tag,
        require_target_release_scope=True,
    ):
        return False
    workflow_url = str(item.get("workflow_run_url", "")).rstrip("/")
    if _command_values(command, "--linux-workflow-run-url") != [workflow_url]:
        return False
    source = item.get("release_asset_source")
    if not isinstance(source, dict):
        return False
    source_head_sha = str(source.get("head_sha", "")).strip()
    if _command_values(command, "--linux-source-head-sha") != [source_head_sha]:
        return False
    return _command_flag_count(command, "--allow-extra-artifacts") == 0


def _has_xp_local_evidence_preflight_command(
    item: dict[str, Any],
    target: str,
    command: str,
) -> bool:
    forbidden_flags = (
        "--linux-builder-evidence",
        "--linux-smoke-evidence",
        "--linux-workflow-run-url",
        "--linux-source-head-sha",
    )
    if any(_command_values(command, flag) for flag in forbidden_flags):
        return False
    if _command_flag_count(command, "--allow-extra-artifacts") != 0:
        return False
    release_tag = str(item.get("release_tag", ""))
    native_command = str(item.get("native_evidence_validation_command", ""))
    path_bindings = {
        "--xp-evidence": ("--evidence", {"require_json_hint": True}),
        "--assets-dir": ("--assets-dir", {"require_directory_hint": True}),
        "--xp-evidence-dir": ("--evidence-dir", {"require_directory_hint": True}),
    }
    for preflight_flag, (native_flag, path_requirements) in path_bindings.items():
        values = _command_values(command, preflight_flag)
        native_values = _command_values(native_command, native_flag)
        if len(values) != 1 or values != native_values:
            return False
        if not _is_safe_xp_validation_path(
            values[0],
            target=target,
            release_tag=release_tag,
            require_target_release_scope=True,
            **path_requirements,
        ):
            return False
    return True


def _command_values(command: str, flag: str) -> list[str]:
    return re.findall(rf"(?:^|\s){re.escape(flag)}\s+(\S+)(?=\s|$)", command)


def _command_flag_count(command: str, flag: str) -> int:
    return len(re.findall(rf"(?:^|\s){re.escape(flag)}(?=\s|$)", command))


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
        match = GITHUB_RELEASE_ASSET_RE.fullmatch(str(url))
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


def _has_release_asset_source_binding(item: dict[str, Any], target: str) -> bool:
    source = item.get("release_asset_source")
    if not isinstance(source, dict):
        return False
    if source.get("type") not in RELEASE_ASSET_SOURCE_TYPES:
        return False
    if source.get("workflow") != _release_source_workflow(target):
        return False
    release_tag = str(item.get("release_tag", ""))
    workflow_run_url = str(source.get("workflow_run_url", "")).rstrip("/")
    workflow_repository = _github_actions_repository(workflow_run_url)
    if not workflow_repository:
        return False
    release_repositories = _release_asset_repositories(item.get("release_asset_urls"))
    if not release_repositories or release_repositories != {workflow_repository}:
        return False
    if target in LINUX_ACCEPTED_EVIDENCE_MACHINES and workflow_run_url != str(item.get("workflow_run_url", "")).rstrip("/"):
        return False
    if source.get("artifact_name") != _release_source_artifact_name(target, release_tag):
        return False
    if re.fullmatch(r"[0-9a-f]{40}", str(source.get("head_sha", ""))) is None:
        return False
    raw_files = source.get("contains_files")
    if not isinstance(raw_files, list) or not raw_files:
        return False
    files = [str(filename) for filename in raw_files]
    if len(files) != len(set(files)):
        return False
    if any(not _is_concrete_filename(filename) for filename in files):
        return False
    return set(files) == _expected_release_source_files(target, release_tag)


def _release_source_artifact_name(target: str, release_tag: str) -> str:
    if target in LINUX_ACCEPTED_EVIDENCE_MACHINES:
        return _linux_accepted_evidence_artifact_name(target, release_tag)
    if target in XP_ACCEPTED_EVIDENCE_ARCHITECTURES:
        return f"xp-native-evidence-{target}-{release_tag}"
    return ""


def _release_source_workflow(target: str) -> str:
    if target in LINUX_ACCEPTED_EVIDENCE_MACHINES:
        return LINUX_ACCEPTED_EVIDENCE_WORKFLOW
    if target in XP_ACCEPTED_EVIDENCE_ARCHITECTURES:
        return XP_ACCEPTED_EVIDENCE_WORKFLOW
    return ""


def _expected_release_source_files(target: str, release_tag: str) -> set[str]:
    review_files = set(_review_bundle_expected_files(target, release_tag).values())
    return (
        set(_expected_accepted_artifact_names(target, release_tag))
        | review_files
        | {f"platform-verified-evidence-{target}-final.json"}
    )


def _review_bundle_expected_files(target: str, release_tag: str) -> dict[str, str]:
    stem = _review_bundle_stem(target, release_tag)
    if not stem:
        return {}
    return {
        "manifest": f"{stem}.json",
        "archive": f"{stem}.zip",
        "sha256s": f"{stem}-SHA256SUMS.txt",
    }


def _is_concrete_filename(filename: str) -> bool:
    return bool(filename) and "<" not in filename and ">" not in filename and Path(filename).name == filename


def _has_review_bundle_binding(item: dict[str, Any], target: str) -> bool:
    release_tag = str(item.get("release_tag", ""))
    raw_bundle = item.get("review_bundle")
    if not isinstance(raw_bundle, dict):
        return False
    if raw_bundle.get("bundle_type") != ACCEPTED_EVIDENCE_REVIEW_BUNDLE_TYPES.get(target):
        return False
    stem = _review_bundle_stem(target, release_tag)
    if not stem:
        return False
    expected_files = _review_bundle_expected_files(target, release_tag)
    for key, expected_file in expected_files.items():
        raw_record = raw_bundle.get(key)
        if not isinstance(raw_record, dict):
            return False
        if raw_record.get("file") != expected_file:
            return False
        if not re.fullmatch(r"[0-9a-f]{64}", str(raw_record.get("sha256", ""))):
            return False
        size = raw_record.get("size_bytes")
        if not isinstance(size, int) or size <= 0:
            return False
    return _has_review_bundle_release_asset_urls(
        raw_bundle.get("release_asset_urls"),
        release_tag=release_tag,
        expected_files=set(expected_files.values()),
        native_release_assets=item.get("release_asset_urls"),
    )


def _has_review_bundle_release_asset_urls(
    raw_urls: Any,
    *,
    release_tag: str,
    expected_files: set[str],
    native_release_assets: Any,
) -> bool:
    if not isinstance(raw_urls, list) or not raw_urls:
        return False
    native_repositories = _release_asset_repositories(native_release_assets)
    if not native_repositories:
        return False
    bundle_repositories: set[str] = set()
    filenames: list[str] = []
    for url in raw_urls:
        match = GITHUB_RELEASE_ASSET_RE.fullmatch(str(url))
        if not match:
            return False
        if match.group(2) != release_tag:
            return False
        bundle_repositories.add(match.group(1))
        filenames.append(Path(str(url)).name)
    if bundle_repositories != native_repositories:
        return False
    if len(filenames) != len(set(filenames)):
        return False
    return set(filenames) == expected_files


def _has_finalized_record_release_asset_url(item: dict[str, Any], target: str) -> bool:
    release_tag = str(item.get("release_tag", ""))
    raw_url = str(item.get("finalized_record_release_asset_url", "")).strip()
    match = GITHUB_RELEASE_ASSET_FILE_RE.fullmatch(raw_url)
    if not match or match.group(2) != release_tag:
        return False
    if Path(match.group(3)).name != f"platform-verified-evidence-{target}-final.json":
        return False
    repositories = _release_asset_repositories(item.get("release_asset_urls"))
    raw_bundle = item.get("review_bundle")
    if isinstance(raw_bundle, dict):
        repositories.update(_release_asset_repositories(raw_bundle.get("release_asset_urls")))
    return bool(repositories) and repositories == {match.group(1)}


def _review_bundle_stem(target: str, release_tag: str) -> str:
    if target in LINUX_ACCEPTED_EVIDENCE_MACHINES:
        return f"extended-linux-evidence-bundle-{target}-{release_tag}"
    if target in XP_ACCEPTED_EVIDENCE_ARCHITECTURES:
        return f"xp-native-evidence-bundle-{target}-{release_tag}"
    return ""


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
    release_tag = str(item.get("release_tag", ""))
    if item.get("artifact_name") != _linux_accepted_evidence_artifact_name(target, release_tag):
        return False
    if item.get("native_build_command") != LINUX_ACCEPTED_EVIDENCE_BUILD_COMMANDS[target]:
        return False
    source = item.get("release_asset_source")
    source_head_sha = str(source.get("head_sha", "")).strip() if isinstance(source, dict) else ""
    expected_smoke = (
        f"{LINUX_ACCEPTED_EVIDENCE_SMOKE_COMMANDS[target]} "
        f"--workflow-run-url {item.get('workflow_run_url')} "
        f"--source-head-sha {source_head_sha}"
    )
    if item.get("native_smoke_command") != expected_smoke:
        return False
    labels = {str(label) for label in item.get("runner_labels", [])}
    if not LINUX_ACCEPTED_EVIDENCE_LABELS[target].issubset(labels):
        return False
    checks = {str(check) for check in item.get("checks", [])}
    if not LINUX_ACCEPTED_EVIDENCE_CHECKS.issubset(checks):
        return False
    return (
        _has_linux_builder_identity_binding(item, target)
        and _has_linux_smoke_evidence_hashes(item)
        and _has_linux_evidence_sources(item, target)
    )


def _linux_accepted_evidence_artifact_name(target: str, release_tag: str) -> str:
    template = LINUX_ACCEPTED_EVIDENCE_ARTIFACT_TEMPLATES[target]
    return template.format(release_tag=release_tag)


def _has_linux_workflow_inputs(item: dict[str, Any], target: str) -> bool:
    raw_inputs = item.get("workflow_inputs")
    if not isinstance(raw_inputs, dict):
        return False
    release_tag = str(item.get("release_tag", ""))
    base_url = str(raw_inputs.get("release_asset_base_url", ""))
    release_match = GITHUB_RELEASE_BASE_RE.fullmatch(base_url)
    if raw_inputs.get("target") != target or raw_inputs.get("release_tag") != release_tag:
        return False
    if not release_match or release_match.group(2) != release_tag:
        return False
    release_assets = item.get("release_asset_urls")
    if not isinstance(release_assets, list):
        return False
    return all(str(url).startswith(f"{base_url}/") for url in release_assets)


def _github_actions_repository(raw_url: Any) -> str:
    match = GITHUB_ACTIONS_RUN_RE.fullmatch(str(raw_url))
    return match.group(1) if match else ""


def _release_source_head(item: dict[str, Any]) -> str:
    source = item.get("release_asset_source")
    if not isinstance(source, dict):
        return ""
    source_head = str(source.get("head_sha", "")).strip()
    return source_head if re.fullmatch(r"[0-9a-f]{40}", source_head) else ""


def _release_asset_repositories(raw_assets: Any) -> set[str]:
    if not isinstance(raw_assets, list):
        return set()
    repositories: set[str] = set()
    for url in raw_assets:
        match = GITHUB_RELEASE_ASSET_RE.fullmatch(str(url))
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
    if raw_identity.get("sudo_non_interactive") is not True:
        return False
    if not _has_linux_required_tool_paths(raw_identity.get("required_tools")):
        return False
    return _has_linux_security_patch_evidence(raw_identity.get("security_patch_evidence"))


def _has_linux_required_tool_paths(raw_tools: Any) -> bool:
    if not isinstance(raw_tools, dict):
        return False
    for tool in LINUX_ACCEPTED_EVIDENCE_TOOLS:
        value = str(raw_tools.get(tool, "")).strip()
        if not value or "<" in value or ">" in value or not value.startswith("/"):
            return False
    return True


def _has_linux_builder_identity_binding(item: dict[str, Any], target: str) -> bool:
    raw_identity = item.get("builder_identity")
    digest = str(item.get("builder_identity_sha256", ""))
    if not isinstance(raw_identity, dict) or not re.fullmatch(r"[0-9a-f]{64}", digest):
        return False
    if raw_identity.get("release_tag") != item.get("release_tag"):
        return False
    if raw_identity.get("workflow_run_url") != item.get("workflow_run_url"):
        return False
    source = item.get("release_asset_source")
    if not isinstance(source, dict) or raw_identity.get("source_head_sha") != source.get("head_sha"):
        return False
    return digest == _json_sha256(raw_identity) and _has_linux_builder_identity(raw_identity, target)


def _has_linux_evidence_sources(item: dict[str, Any], target: str) -> bool:
    raw_sources = item.get("linux_evidence_sources")
    if not isinstance(raw_sources, dict):
        return False
    if set(str(key) for key in raw_sources) != {"builder_identity", "native_smoke"}:
        return False
    smoke_hashes = item.get("linux_smoke_evidence_sha256")
    native_smoke_sha = (
        str(smoke_hashes.get("native_smoke", ""))
        if isinstance(smoke_hashes, dict)
        else ""
    )
    expected = {
        "builder_identity": {
            "file": f"builder-identity-{target}.json",
            "sha256": str(item.get("builder_identity_sha256", "")),
        },
        "native_smoke": {
            "file": f"native-smoke-{target}.log",
            "sha256": native_smoke_sha,
        },
    }
    for key, expected_values in expected.items():
        record = raw_sources.get(key)
        if not isinstance(record, dict):
            return False
        if record.get("file") != expected_values["file"]:
            return False
        if record.get("sha256") != expected_values["sha256"]:
            return False
        size = record.get("size_bytes")
        if not isinstance(size, int) or size <= 0:
            return False
    return True


def _has_linux_smoke_evidence_hashes(item: dict[str, Any]) -> bool:
    smoke_hashes = item.get("linux_smoke_evidence_sha256")
    if not isinstance(smoke_hashes, dict):
        return False
    if set(str(key) for key in smoke_hashes) != LINUX_ACCEPTED_EVIDENCE_SMOKE_IDS:
        return False
    return all(re.fullmatch(r"[0-9a-f]{64}", str(value)) for value in smoke_hashes.values())


def _is_xp_accepted_evidence_entry(item: dict[str, Any], target: str) -> bool:
    if item.get("evidence_type") != "windows-xp-native-host":
        return False
    if item.get("workflow") != XP_ACCEPTED_EVIDENCE_WORKFLOW:
        return False
    if item.get("architecture") != XP_ACCEPTED_EVIDENCE_ARCHITECTURES[target]:
        return False
    if item.get("separate_legacy_toolchain") is not True:
        return False
    if item.get("current_python_pyqt6_stack") is not False:
        return False
    if not _has_xp_native_evidence_validation_command(item):
        return False
    if not _has_xp_workflow_inputs(item, target):
        return False
    if not re.fullmatch(r"[0-9a-f]{64}", str(item.get("xp_evidence_sha256", ""))):
        return False
    if str(item.get("xp_evidence_contract_sha256", "")) != _xp_native_evidence_contract_sha256():
        return False
    if not _has_xp_evidence_summary(item, target):
        return False
    if not _has_xp_host_identity_digest(item, target):
        return False
    smoke_hashes = item.get("xp_smoke_evidence_sha256")
    if not isinstance(smoke_hashes, dict):
        return False
    if set(str(key) for key in smoke_hashes) != XP_ACCEPTED_EVIDENCE_SMOKE_IDS:
        return False
    if not all(re.fullmatch(r"[0-9a-f]{64}", str(value)) for value in smoke_hashes.values()):
        return False
    if not _has_xp_evidence_sources(item, target):
        return False
    checks = {str(check) for check in item.get("checks", [])}
    return XP_ACCEPTED_EVIDENCE_CHECKS.issubset(checks)


def _has_xp_native_evidence_validation_command(item: dict[str, Any]) -> bool:
    command = str(item.get("native_evidence_validation_command", ""))
    target = str(item.get("target", ""))
    release_tag = str(item.get("release_tag", ""))
    if not command.startswith("python scripts/check_xp_native_evidence.py "):
        return False
    evidence_paths = re.findall(r"(?:^|\s)--evidence\s+(\S+)(?=\s|$)", command)
    if len(evidence_paths) != 1 or not _is_safe_xp_validation_path(
        evidence_paths[0],
        target=target,
        release_tag=release_tag,
        require_json_hint=True,
        require_target_release_scope=True,
    ):
        return False
    asset_dirs = re.findall(r"(?:^|\s)--assets-dir\s+(\S+)(?=\s|$)", command)
    if len(asset_dirs) != 1 or not _is_safe_xp_validation_path(
        asset_dirs[0],
        target=target,
        release_tag=release_tag,
        require_directory_hint=True,
        require_target_release_scope=True,
    ):
        return False
    evidence_dirs = re.findall(r"(?:^|\s)--evidence-dir\s+(\S+)(?=\s|$)", command)
    return len(evidence_dirs) == 1 and _is_safe_xp_validation_path(
        evidence_dirs[0],
        target=target,
        release_tag=release_tag,
        require_directory_hint=True,
        require_target_release_scope=True,
    )


def _has_xp_workflow_inputs(item: dict[str, Any], target: str) -> bool:
    raw_inputs = item.get("workflow_inputs")
    if not isinstance(raw_inputs, dict):
        return False
    if {str(key) for key in raw_inputs} != XP_ACCEPTED_EVIDENCE_WORKFLOW_INPUT_KEYS:
        return False
    release_tag = str(item.get("release_tag", ""))
    base_url = str(raw_inputs.get("release_asset_base_url", ""))
    release_match = GITHUB_RELEASE_BASE_RE.fullmatch(base_url)
    if raw_inputs.get("target") != target or raw_inputs.get("release_tag") != release_tag:
        return False
    if not release_match or release_match.group(2) != release_tag:
        return False
    source = item.get("release_asset_source")
    source_run_url = str(source.get("workflow_run_url", "")).rstrip("/") if isinstance(source, dict) else ""
    if _github_actions_repository(source_run_url) != release_match.group(1):
        return False
    release_assets = item.get("release_asset_urls")
    if not isinstance(release_assets, list):
        return False
    if any(not str(url).startswith(f"{base_url}/") for url in release_assets):
        return False
    command = str(item.get("native_evidence_validation_command", ""))
    command_paths = {
        "evidence_file": re.findall(r"(?:^|\s)--evidence\s+(\S+)(?=\s|$)", command),
        "assets_dir": re.findall(r"(?:^|\s)--assets-dir\s+(\S+)(?=\s|$)", command),
        "evidence_dir": re.findall(r"(?:^|\s)--evidence-dir\s+(\S+)(?=\s|$)", command),
    }
    path_requirements = {
        "evidence_file": {"require_json_hint": True},
        "assets_dir": {"require_directory_hint": True},
        "evidence_dir": {"require_directory_hint": True},
    }
    for input_key, values in command_paths.items():
        input_value = str(raw_inputs.get(input_key, "")).strip()
        if len(values) != 1 or input_value != values[0]:
            return False
        if not _is_safe_xp_validation_path(
            input_value,
            target=target,
            release_tag=release_tag,
            require_target_release_scope=True,
            **path_requirements[input_key],
        ):
            return False
    return True


def _has_xp_evidence_sources(item: dict[str, Any], target: str) -> bool:
    raw_sources = item.get("xp_evidence_sources")
    if not isinstance(raw_sources, dict):
        return False
    if {str(key) for key in raw_sources} != {"evidence", "smoke_evidence"}:
        return False
    evidence = raw_sources.get("evidence")
    workflow_inputs = item.get("workflow_inputs")
    if not isinstance(evidence, dict) or not isinstance(workflow_inputs, dict):
        return False
    if evidence.get("file") != "xp-evidence.json":
        return False
    if evidence.get("path") != workflow_inputs.get("evidence_file"):
        return False
    if evidence.get("sha256") != item.get("xp_evidence_sha256"):
        return False
    if not isinstance(evidence.get("size_bytes"), int) or evidence.get("size_bytes") <= 0:
        return False
    summary = item.get("xp_evidence_summary")
    if not isinstance(summary, dict):
        return False
    smoke_files = summary.get("smoke_evidence_files")
    smoke_hashes = item.get("xp_smoke_evidence_sha256")
    smoke_sources = raw_sources.get("smoke_evidence")
    if not isinstance(smoke_files, dict) or not isinstance(smoke_hashes, dict):
        return False
    if not isinstance(smoke_sources, dict):
        return False
    if {str(key) for key in smoke_sources} != XP_ACCEPTED_EVIDENCE_SMOKE_IDS:
        return False
    for smoke_id in XP_ACCEPTED_EVIDENCE_SMOKE_IDS:
        record = smoke_sources.get(smoke_id)
        if not isinstance(record, dict):
            return False
        if record.get("file") != smoke_files.get(smoke_id):
            return False
        if record.get("sha256") != smoke_hashes.get(smoke_id):
            return False
        size = record.get("size_bytes")
        if not isinstance(size, int) or size <= 0:
            return False
    return True


def _is_safe_xp_validation_path(
    raw_path: str,
    *,
    target: str = "",
    release_tag: str = "",
    require_directory_hint: bool = False,
    require_json_hint: bool = False,
    require_target_release_scope: bool = False,
) -> bool:
    path = raw_path.strip()
    if not path or "<" in path or ">" in path or any(char in path for char in "*?"):
        return False
    if "\\" in path:
        parsed_path = PureWindowsPath(path)
        parts = parsed_path.parts
        is_absolute = parsed_path.is_absolute() or bool(parsed_path.drive)
    else:
        parsed_path = PurePosixPath(path)
        parts = parsed_path.parts
        is_absolute = parsed_path.is_absolute()
    if is_absolute or any(part == ".." for part in parts):
        return False
    normalized_parts = tuple(part for part in parts if part not in ("", "."))
    if not normalized_parts:
        return False
    if normalized_parts[0] in RESERVED_WORKSPACE_ROOTS:
        return False
    if any(part.startswith(".") and part not in RESERVED_WORKSPACE_ROOTS for part in normalized_parts):
        return False
    if require_directory_hint and _directory_path_has_file_suffix(path):
        return False
    if require_json_hint and not path.endswith(".json"):
        return False
    if require_target_release_scope and (
        target not in normalized_parts or release_tag not in normalized_parts
    ):
        return False
    return True


def _directory_path_has_file_suffix(raw_path: str) -> bool:
    path = raw_path.strip()
    if not path:
        return False
    leaf = PureWindowsPath(path).name if "\\" in path else PurePosixPath(path).name
    leaf = leaf.lower()
    return any(leaf.endswith(suffix) for suffix in FILE_LIKE_DIRECTORY_SUFFIXES)


def _has_xp_evidence_summary(item: dict[str, Any], target: str) -> bool:
    summary = item.get("xp_evidence_summary")
    if not isinstance(summary, dict):
        return False
    if summary.get("target") != target or summary.get("release_tag") != item.get("release_tag"):
        return False
    if not _has_xp_host_identity(summary.get("host_identity"), target, str(item.get("release_tag", ""))):
        return False
    os_data = summary.get("os")
    if not isinstance(os_data, dict):
        return False
    if os_data.get("name") != "Windows XP":
        return False
    if os_data.get("architecture") != XP_ACCEPTED_EVIDENCE_ARCHITECTURES[target]:
        return False
    expected_service_pack = XP_ACCEPTED_EVIDENCE_SERVICE_PACKS[target]
    if expected_service_pack not in str(os_data.get("service_pack", "")):
        return False
    expected_edition = XP_ACCEPTED_EVIDENCE_EDITIONS.get(target)
    if expected_edition and os_data.get("edition") != expected_edition:
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
    if not _has_security_patch_evidence(security.get("patch_evidence")):
        return False
    smoke_ids = summary.get("smoke_ids")
    if not isinstance(smoke_ids, list) or {str(smoke_id) for smoke_id in smoke_ids} != XP_ACCEPTED_EVIDENCE_SMOKE_IDS:
        return False
    smoke_evidence_files = summary.get("smoke_evidence_files")
    if not _has_xp_smoke_evidence_files(smoke_evidence_files):
        return False
    return _has_xp_smoke_commands(
        summary.get("smoke_commands"),
        smoke_evidence_files,
        target,
        str(summary.get("release_tag", "")),
    )


def _has_xp_host_identity_digest(item: dict[str, Any], target: str) -> bool:
    summary = item.get("xp_evidence_summary")
    if not isinstance(summary, dict):
        return False
    identity = summary.get("host_identity")
    if not isinstance(identity, dict):
        return False
    digest = str(item.get("xp_host_identity_sha256", ""))
    return (
        re.fullmatch(r"[0-9a-f]{64}", digest) is not None
        and digest == _json_sha256(identity)
        and _has_xp_host_identity(identity, target, str(item.get("release_tag", "")))
    )


def _has_xp_host_identity(raw_identity: Any, target: str, release_tag: str) -> bool:
    if not isinstance(raw_identity, dict):
        return False
    if raw_identity.get("schema_version") != 1:
        return False
    if raw_identity.get("target") != target or raw_identity.get("release_tag") != release_tag:
        return False
    host_label = str(raw_identity.get("host_label", "")).strip()
    if re.fullmatch(r"^[a-z0-9][a-z0-9._-]{2,63}$", host_label) is None:
        return False
    evidence_run_id = str(raw_identity.get("evidence_run_id", "")).strip()
    if re.fullmatch(r"^[a-z0-9][a-z0-9._:-]{7,127}$", evidence_run_id) is None:
        return False
    observed_at = str(raw_identity.get("observed_at_utc", "")).strip()
    if re.fullmatch(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$", observed_at) is None:
        return False
    if raw_identity.get("operator_private_data_redacted") is not True:
        return False
    os_data = raw_identity.get("os")
    if not isinstance(os_data, dict):
        return False
    if os_data.get("name") != "Windows XP":
        return False
    if os_data.get("architecture") != XP_ACCEPTED_EVIDENCE_ARCHITECTURES[target]:
        return False
    if XP_ACCEPTED_EVIDENCE_SERVICE_PACKS[target] not in str(os_data.get("service_pack", "")):
        return False
    expected_edition = XP_ACCEPTED_EVIDENCE_EDITIONS.get(target)
    if expected_edition and os_data.get("edition") != expected_edition:
        return False
    toolchain = raw_identity.get("toolchain")
    if not isinstance(toolchain, dict):
        return False
    if any(toolchain.get(flag) is not expected for flag, expected in XP_ACCEPTED_EVIDENCE_TOOLCHAIN_FLAGS.items()):
        return False
    return len(str(toolchain.get("description", "")).strip()) >= 12


def _has_xp_smoke_evidence_files(raw_files: Any) -> bool:
    if not isinstance(raw_files, dict):
        return False
    files = {str(name): str(value).strip() for name, value in raw_files.items()}
    if set(files) != XP_ACCEPTED_EVIDENCE_SMOKE_IDS:
        return False
    if len(set(files.values())) != len(files):
        return False
    for smoke_id, filename in files.items():
        if filename != f"xp-smoke-evidence/{smoke_id}.txt":
            return False
        path = Path(filename)
        if not filename or "<" in filename or ">" in filename:
            return False
        if path.is_absolute() or ".." in path.parts:
            return False
    return True


def _has_xp_smoke_commands(raw_commands: Any, raw_files: Any, target: str, release_tag: str) -> bool:
    if not isinstance(raw_commands, dict):
        return False
    if not isinstance(raw_files, dict):
        return False
    commands = {str(name): str(value).strip() for name, value in raw_commands.items()}
    evidence_files = {str(name): str(value).strip() for name, value in raw_files.items()}
    if set(commands) != XP_ACCEPTED_EVIDENCE_SMOKE_IDS:
        return False
    return all(
        command
        and "<" not in command
        and ">" not in command
        and _xp_smoke_command_bound(command, target, release_tag, smoke_id, evidence_files.get(smoke_id, ""))
        for smoke_id, command in commands.items()
    )


def _xp_smoke_command_bound(
    command: str,
    target: str,
    release_tag: str,
    smoke_id: str,
    evidence_file: str,
) -> bool:
    expected_values = {
        "--target": target,
        "--release-tag": release_tag,
        "--smoke-id": smoke_id,
        "--evidence-file": evidence_file,
        "--proof-file": f"xp-smoke-proof/{smoke_id}.txt",
    }
    return all(
        re.findall(rf"(?:^|\s){re.escape(flag)}\s+(\S+)(?=\s|$)", command) == [expected]
        for flag, expected in expected_values.items()
    )


def _has_security_patch_evidence(raw_evidence: Any) -> bool:
    if not isinstance(raw_evidence, dict):
        return False
    return all(
        raw_evidence.get(key) == expected
        for key, expected in ACCEPTED_EVIDENCE_SECURITY_PATCH_EVIDENCE.items()
    )


def _has_linux_security_patch_evidence(raw_evidence: Any) -> bool:
    if not _has_security_patch_evidence(raw_evidence):
        return False
    return all(
        str(raw_evidence.get(key, "")).strip()
        for key in ("python_ssl_openssl", "openssl_cli_version")
    )


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
    if len(release_tags) != 1 or "" in release_tags:
        return False
    repository_sets = [
        _release_asset_repositories(entries[target].get("release_asset_urls"))
        for target in required
    ]
    if not all(len(repositories) == 1 for repositories in repository_sets):
        return False
    repositories = {
        next(iter(release_repositories))
        for release_repositories in repository_sets
    }
    if len(repositories) != 1:
        return False
    source_heads = {
        _release_source_head(entries[target])
        for target in required
    }
    return "" not in source_heads and len(source_heads) == 1


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
        "accepted_evidence_release_repositories": {
            target: sorted(_release_asset_repositories(entries[target].get("release_asset_urls")))
            for target in present
        },
        "accepted_evidence_release_source_heads": {
            target: _release_source_head(entries[target])
            for target in present
            if _release_source_head(entries[target])
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

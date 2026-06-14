from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from check_platform_promotion_artifacts import (  # noqa: E402
    check_platform_promotion_artifacts,
    required_artifacts,
    version_from_tag,
)
from check_platform_promotion_artifacts import (  # noqa: E402
    read_json as read_promotion_json,
)
from check_platform_verified_evidence import (  # noqa: E402
    LINUX_TARGETS,
    XP_TARGETS,
    check_platform_verified_evidence,
    json_sha256,
    promotion_config_sha256,
    xp_native_evidence_contract_sha256,
)
from check_xp_native_evidence import check_xp_native_evidence  # noqa: E402

PROMOTION_PATH = ROOT / "configs" / "platform_parity_promotion.json"
EVIDENCE_PATH = ROOT / "configs" / "platform_verified_evidence.json"
DEFAULT_EVIDENCE_POLICY = (
    "Only accepted evidence records in this file can promote Linux i386, Linux armhf, "
    "or Windows XP native-host readiness. Accepted records must include release asset URLs, "
    "per-artifact SHA-256 digests, Linux builder identity evidence and builder identity SHA-256 "
    "when applicable, Linux workflow dispatch inputs when applicable, and XP evidence bundle "
    "SHA-256 digests, XP evidence contract SHA-256, and XP evidence summary binding when "
    "applicable; each accepted record must include the promotion config SHA-256, have a unique "
    "target, all release evidence for one record must use the same GitHub repository, and Windows "
    "XP x86/x64 pairs must use the same release_tag. Empty means no promotion."
)
LINUX_CHECKS = [
    "builder_preflight",
    "native_build",
    "native_smoke",
    "artifact_validation",
    "release_asset_attachment",
]
XP_CHECKS = [
    "xp_native_evidence_validation",
    "artifact_validation",
    "vm_or_host_smoke",
    "legacy_crypto_profile_scoped",
    "modern_defaults_unchanged",
    "release_asset_attachment",
]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    errors, record = build_evidence_record(args)
    if errors:
        for error in errors:
            print(f"platform verified evidence record: {error}", file=sys.stderr)
        return 1
    output = json.dumps(record, indent=2) + "\n"
    if args.append_registry:
        registry_errors = append_record_to_registry(record, registry_path=args.registry)
        if registry_errors:
            for error in registry_errors:
                print(f"platform verified evidence record: {error}", file=sys.stderr)
            return 1
        if args.out:
            args.out.write_text(output, encoding="utf-8")
        print(f"platform verified evidence record appended to {args.registry}")
        return 0
    if args.out:
        args.out.write_text(output, encoding="utf-8")
    else:
        print(output, end="")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a validated accepted-evidence record for platform readiness promotion."
    )
    parser.add_argument("--target", choices=sorted({*LINUX_TARGETS, *XP_TARGETS}), required=True)
    parser.add_argument("--release-tag", required=True, help="Release tag, for example v1.0.2")
    parser.add_argument("--assets-dir", type=Path, required=True, help="Directory with built native artifacts")
    parser.add_argument(
        "--release-asset-base-url",
        required=True,
        help="GitHub release download base URL ending in /releases/download/vX.Y.Z",
    )
    parser.add_argument("--workflow-run-url", help="GitHub Actions run URL for Linux evidence")
    parser.add_argument("--runner-label", action="append", default=[], help="Runner label for Linux evidence")
    parser.add_argument("--builder-evidence", type=Path, help="Linux builder identity JSON emitted by builder preflight")
    parser.add_argument("--xp-evidence", type=Path, help="Windows XP native evidence JSON for XP targets")
    parser.add_argument(
        "--xp-evidence-dir",
        type=Path,
        help="directory containing smoke evidence files referenced by --xp-evidence",
    )
    parser.add_argument(
        "--append-registry",
        action="store_true",
        help="append the validated record to configs/platform_verified_evidence.json",
    )
    parser.add_argument(
        "--registry",
        type=Path,
        default=EVIDENCE_PATH,
        help="accepted evidence registry path used with --append-registry",
    )
    parser.add_argument("--out", type=Path, help="Write the generated evidence record to this file")
    return parser.parse_args(argv)


def build_evidence_record(args: argparse.Namespace) -> tuple[list[str], dict[str, Any]]:
    target = str(args.target)
    errors = validate_common_args(args)
    if target in LINUX_TARGETS:
        errors.extend(validate_linux_args(args))
    else:
        errors.extend(validate_xp_args(args))
    if errors:
        return errors, {}

    errors.extend(
        check_platform_promotion_artifacts(
            target=target,
            assets_dir=args.assets_dir,
            tag=args.release_tag,
        )
    )
    if target in XP_TARGETS:
        errors.extend(
            check_xp_native_evidence(
                args.xp_evidence,
                assets_dir=args.assets_dir,
                evidence_dir=args.xp_evidence_dir,
            )
        )
    if errors:
        return errors, {}

    promotion = read_promotion_json(PROMOTION_PATH)
    record = linux_record(args, promotion) if target in LINUX_TARGETS else xp_record(args, promotion)
    registry = {
        "schema_version": 1,
        "policy": DEFAULT_EVIDENCE_POLICY,
        "accepted_evidence": [record],
    }
    errors.extend(check_platform_verified_evidence(registry=registry, promotion=promotion))
    return errors, record


def validate_common_args(args: argparse.Namespace) -> list[str]:
    errors: list[str] = []
    version_errors: list[str] = []
    version_from_tag(str(args.release_tag), version_errors)
    errors.extend(version_errors)
    if not args.assets_dir.is_dir():
        errors.append(f"artifact directory missing: {args.assets_dir}")
    base_url = str(args.release_asset_base_url)
    expected_suffix = f"/releases/download/{args.release_tag}"
    if not base_url.startswith("https://github.com/") or not base_url.endswith(expected_suffix):
        errors.append(
            "--release-asset-base-url must be a GitHub release download URL ending in "
            f"{expected_suffix}"
        )
    return errors


def validate_linux_args(args: argparse.Namespace) -> list[str]:
    errors: list[str] = []
    if not args.workflow_run_url:
        errors.append("--workflow-run-url is required for Linux evidence")
    if args.builder_evidence is None:
        errors.append("--builder-evidence is required for Linux evidence")
    elif not args.builder_evidence.is_file():
        errors.append(f"Linux builder evidence file missing: {args.builder_evidence}")
    required_labels = LINUX_TARGETS[str(args.target)]["runner_labels"]
    labels = set(str(label) for label in args.runner_label)
    if not required_labels.issubset(labels):
        errors.append(f"--runner-label must include {sorted(required_labels)}")
    if args.xp_evidence is not None:
        errors.append("--xp-evidence is only valid for Windows XP evidence")
    if args.xp_evidence_dir is not None:
        errors.append("--xp-evidence-dir is only valid for Windows XP evidence")
    return errors


def validate_xp_args(args: argparse.Namespace) -> list[str]:
    errors: list[str] = []
    if args.builder_evidence is not None:
        errors.append("--builder-evidence is only valid for Linux evidence")
    if args.xp_evidence is None:
        errors.append("--xp-evidence is required for Windows XP evidence")
    elif not args.xp_evidence.is_file():
        errors.append(f"XP evidence file missing: {args.xp_evidence}")
    if args.xp_evidence_dir is not None and not args.xp_evidence_dir.is_dir():
        errors.append(f"XP evidence directory missing: {args.xp_evidence_dir}")
    if args.workflow_run_url:
        errors.append("--workflow-run-url is only valid for Linux evidence")
    if args.runner_label:
        errors.append("--runner-label is only valid for Linux evidence")
    return errors


def linux_record(args: argparse.Namespace, promotion: dict[str, Any]) -> dict[str, Any]:
    target = str(args.target)
    expected = LINUX_TARGETS[target]
    builder_identity = read_json(args.builder_evidence)
    return {
        "target": target,
        "evidence_type": "extended-linux-native",
        "status": "accepted",
        "readiness_percent": 100.0,
        "release_tag": str(args.release_tag),
        "promotion_config_sha256": promotion_config_sha256(promotion),
        "workflow": expected["workflow"],
        "workflow_inputs": {
            "target": target,
            "release_tag": str(args.release_tag),
            "release_asset_base_url": str(args.release_asset_base_url).rstrip("/"),
        },
        "workflow_run_url": str(args.workflow_run_url),
        "artifact_name": expected["artifact"],
        "runner_labels": sorted(set(str(label) for label in args.runner_label)),
        "builder_identity": builder_identity,
        "builder_identity_sha256": json_sha256(builder_identity),
        "artifact_validation_command": (
            f"python scripts/check_platform_promotion_artifacts.py --target {target} "
            f"--assets-dir {args.assets_dir.as_posix()} --tag {args.release_tag}"
        ),
        "checks": LINUX_CHECKS,
        "release_asset_urls": release_asset_urls(target, str(args.release_tag), str(args.release_asset_base_url), promotion),
        "artifact_sha256": artifact_sha256_map(target, str(args.release_tag), args.assets_dir, promotion),
    }


def xp_record(args: argparse.Namespace, promotion: dict[str, Any]) -> dict[str, Any]:
    target = str(args.target)
    arch = XP_TARGETS[target]["architecture"]
    evidence = read_json(args.xp_evidence)
    return {
        "target": target,
        "evidence_type": "windows-xp-native-host",
        "status": "accepted",
        "readiness_percent": 100.0,
        "release_tag": str(args.release_tag),
        "promotion_config_sha256": promotion_config_sha256(promotion),
        "architecture": arch,
        "separate_legacy_toolchain": True,
        "current_python_pyqt6_stack": False,
        "xp_evidence_sha256": sha256_file(args.xp_evidence),
        "xp_evidence_contract_sha256": xp_native_evidence_contract_sha256(),
        "xp_evidence_summary": xp_evidence_summary(target, str(args.release_tag), evidence),
        "xp_smoke_evidence_sha256": xp_smoke_evidence_sha256_map(evidence),
        "native_evidence_validation_command": (
            "python scripts/check_xp_native_evidence.py --evidence <evidence.json> --assets-dir <artifact-dir>"
        ),
        "artifact_validation_command": (
            f"python scripts/check_platform_promotion_artifacts.py --target {target} "
            f"--assets-dir {args.assets_dir.as_posix()} --tag {args.release_tag}"
        ),
        "checks": XP_CHECKS,
        "release_asset_urls": release_asset_urls(target, str(args.release_tag), str(args.release_asset_base_url), promotion),
        "artifact_sha256": artifact_sha256_map(target, str(args.release_tag), args.assets_dir, promotion),
    }


def release_asset_urls(
    target: str,
    release_tag: str,
    base_url: str,
    promotion: dict[str, Any],
) -> list[str]:
    version = release_tag.removeprefix("v")
    entries = {
        str(item.get("id")): item
        for item in promotion.get("protected_targets", [])
        if isinstance(item, dict)
    }
    artifacts = [
        str(item).replace("<project.version>", version)
        for item in required_artifacts(entries[target])
    ]
    return [f"{base_url.rstrip('/')}/{artifact}" for artifact in artifacts]


def artifact_sha256_map(
    target: str,
    release_tag: str,
    assets_dir: Path,
    promotion: dict[str, Any],
) -> dict[str, str]:
    return {
        artifact: sha256_file(assets_dir / artifact)
        for artifact in expected_artifact_names(target, release_tag, promotion)
    }


def expected_artifact_names(
    target: str,
    release_tag: str,
    promotion: dict[str, Any],
) -> list[str]:
    version = release_tag.removeprefix("v")
    entries = {
        str(item.get("id")): item
        for item in promotion.get("protected_targets", [])
        if isinstance(item, dict)
    }
    return [
        str(item).replace("<project.version>", version)
        for item in required_artifacts(entries[target])
    ]


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def xp_evidence_summary(target: str, release_tag: str, evidence: dict[str, Any]) -> dict[str, Any]:
    os_data = evidence.get("os", {})
    toolchain = evidence.get("toolchain", {})
    security = evidence.get("security", {})
    smoke_results = evidence.get("smoke_results", [])
    if not isinstance(os_data, dict):
        os_data = {}
    if not isinstance(toolchain, dict):
        toolchain = {}
    if not isinstance(security, dict):
        security = {}
    if not isinstance(smoke_results, list):
        smoke_results = []
    return {
        "target": target,
        "release_tag": release_tag,
        "os": {
            "name": str(os_data.get("name", "")),
            "architecture": str(os_data.get("architecture", "")),
            "service_pack": str(os_data.get("service_pack", "")),
        },
        "toolchain": {
            "separate_legacy_toolchain": toolchain.get("separate_legacy_toolchain") is True,
            "current_python_pyqt6_stack": toolchain.get("current_python_pyqt6_stack") is True,
        },
        "security": {
            "legacy_crypto_profile_scoped": security.get("legacy_crypto_profile_scoped") is True,
            "modern_defaults_unchanged": security.get("modern_defaults_unchanged") is True,
            "weak_crypto_global_default": security.get("weak_crypto_global_default") is True,
        },
        "smoke_ids": sorted(
            str(item.get("id", ""))
            for item in smoke_results
            if isinstance(item, dict) and str(item.get("id", ""))
        ),
    }


def xp_smoke_evidence_sha256_map(evidence: dict[str, Any]) -> dict[str, str]:
    results = evidence.get("smoke_results", [])
    if not isinstance(results, list):
        return {}
    hashes: dict[str, str] = {}
    for item in results:
        if not isinstance(item, dict):
            continue
        smoke_id = str(item.get("id", ""))
        evidence_sha = str(item.get("evidence_sha256", ""))
        if smoke_id:
            hashes[smoke_id] = evidence_sha
    return hashes


def append_record_to_registry(record: dict[str, Any], *, registry_path: Path = EVIDENCE_PATH) -> list[str]:
    registry = read_evidence_registry(registry_path)
    accepted = registry.get("accepted_evidence")
    if not isinstance(accepted, list):
        return ["platform verified evidence accepted_evidence must be a list"]

    target = str(record.get("target", ""))
    duplicate_targets = [
        entry
        for entry in accepted
        if isinstance(entry, dict) and str(entry.get("target", "")) == target
    ]
    if duplicate_targets:
        return [
            f"{target} already has accepted evidence; remove or replace the existing record deliberately "
            "before appending"
        ]

    updated = {**registry, "accepted_evidence": [*accepted, record]}
    errors = check_platform_verified_evidence(
        registry=updated,
        promotion=read_promotion_json(PROMOTION_PATH),
    )
    if errors:
        return errors

    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(json.dumps(updated, indent=2) + "\n", encoding="utf-8")
    return []


def read_evidence_registry(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "schema_version": 1,
            "policy": DEFAULT_EVIDENCE_POLICY,
            "accepted_evidence": [],
        }
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {
            "schema_version": 0,
            "policy": f"Invalid evidence registry JSON: {exc}",
            "accepted_evidence": None,
        }
    return data if isinstance(data, dict) else {"schema_version": 0, "policy": "", "accepted_evidence": None}


def read_json(path: Path) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return {"schema_version": 0, "error": f"invalid JSON: {exc}"}
    return data if isinstance(data, dict) else {"schema_version": 0, "error": "JSON root must be an object"}


if __name__ == "__main__":
    raise SystemExit(main())

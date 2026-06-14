from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / "configs" / "xp_native_evidence_contract.json"
PROMOTION_PATH = ROOT / "configs" / "platform_parity_promotion.json"


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    errors = make_xp_native_evidence_template(
        target=args.target,
        release_tag=args.release_tag,
        out_dir=args.out_dir,
        force=args.force,
    )
    if errors:
        for error in errors:
            print(f"XP native evidence template: {error}", file=sys.stderr)
        return 1
    print(f"XP native evidence template written to {args.out_dir}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    contract = read_json(CONTRACT_PATH)
    targets = sorted(str(target) for target in contract.get("targets", {}))
    parser = argparse.ArgumentParser(
        description=(
            "Create a failing-by-default Windows XP native evidence template. "
            "Replace it with real XP smoke evidence before validation or registry promotion."
        )
    )
    parser.add_argument("--target", choices=targets, required=True)
    parser.add_argument("--release-tag", required=True, help="Release tag, for example v1.0.2")
    parser.add_argument("--out-dir", type=Path, required=True, help="Directory that will receive xp-evidence.json")
    parser.add_argument("--force", action="store_true", help="overwrite an existing template file")
    return parser.parse_args(argv)


def make_xp_native_evidence_template(
    *,
    target: str,
    release_tag: str,
    out_dir: Path,
    force: bool = False,
) -> list[str]:
    errors: list[str] = []
    if not re.fullmatch(r"v\d+\.\d+\.\d+", release_tag):
        errors.append(f"release tag must look like vX.Y.Z: {release_tag}")
    contract = read_json(CONTRACT_PATH)
    target_contract = contract.get("targets", {}).get(target)
    if not isinstance(target_contract, dict):
        errors.append(f"unknown XP native evidence target: {target}")
    if errors:
        return errors

    evidence_path = out_dir / "xp-evidence.json"
    if evidence_path.exists() and not force:
        return [f"refusing to overwrite existing evidence template: {evidence_path}"]
    smoke_dir = out_dir / "xp-smoke-evidence"
    smoke_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(parents=True, exist_ok=True)

    smoke_ids = [str(item) for item in contract.get("required_smoke_ids", [])]
    for smoke_id in smoke_ids:
        smoke_path = smoke_dir / f"{smoke_id}.txt"
        if not smoke_path.exists() or force:
            smoke_path.write_text(template_smoke_text(target, release_tag, smoke_id), encoding="utf-8")

    evidence = evidence_template(
        target=target,
        release_tag=release_tag,
        target_contract=target_contract,
        smoke_ids=smoke_ids,
    )
    evidence_path.write_text(json.dumps(evidence, indent=2) + "\n", encoding="utf-8")
    return []


def evidence_template(
    *,
    target: str,
    release_tag: str,
    target_contract: dict[str, Any],
    smoke_ids: list[str],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "template_notice": (
            "This template is intentionally incomplete and must fail validation until a real "
            "Windows XP x86/x64 evidence host replaces every placeholder."
        ),
        "target": target,
        "release_tag": release_tag,
        "os": {
            "name": target_contract["os_name"],
            "architecture": target_contract["architecture"],
            "service_pack": f"{target_contract['minimum_service_pack']} TODO replace with real winver evidence",
        },
        "toolchain": {
            "separate_legacy_toolchain": True,
            "current_python_pyqt6_stack": False,
            "description": "TODO describe the separate XP-capable native host toolchain used for this run",
        },
        "artifact_validation": {
            "passed": False,
            "command": (
                f"python scripts/check_platform_promotion_artifacts.py --target {target} "
                f"--assets-dir <artifact-dir> --tag {release_tag}"
            ),
        },
        "artifacts": required_artifacts(target, release_tag),
        "smoke_results": [
            {
                "id": smoke_id,
                "passed": False,
                "evidence_file": f"xp-smoke-evidence/{smoke_id}.txt",
                "evidence_sha256": "<replace-with-real-sha256>",
            }
            for smoke_id in smoke_ids
        ],
        "security": {
            "legacy_crypto_profile_scoped": False,
            "modern_defaults_unchanged": False,
            "weak_crypto_global_default": True,
        },
    }


def template_smoke_text(target: str, release_tag: str, smoke_id: str) -> str:
    return (
        f"Template evidence for {target} {release_tag} smoke id {smoke_id}.\n"
        "Replace this file with real Windows XP host output before validation.\n"
        "Do not include confidential access material or other sensitive values.\n"
    )


def required_artifacts(target: str, release_tag: str) -> list[str]:
    promotion = read_json(PROMOTION_PATH)
    version = release_tag.removeprefix("v")
    for item in promotion.get("protected_targets", []):
        if isinstance(item, dict) and item.get("id") == target:
            requirements = item.get("promotion_to_100_requires", {})
            if not isinstance(requirements, dict):
                return []
            artifacts = requirements.get("native_artifacts", requirements.get("required_artifacts", []))
            if not isinstance(artifacts, list):
                return []
            return [str(artifact).replace("<project.version>", version) for artifact in artifacts]
    return []


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    raise SystemExit(main())

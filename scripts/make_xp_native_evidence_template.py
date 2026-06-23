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
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from check_platform_verified_evidence import directory_path_has_file_suffix  # noqa: E402


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
    smoke_ids = [str(item) for item in contract.get("required_smoke_ids", [])]
    errors.extend(check_template_output_paths(out_dir=out_dir, evidence_path=evidence_path, smoke_ids=smoke_ids))
    if errors:
        return errors
    if evidence_path.exists() and not force:
        return [f"refusing to overwrite existing evidence template: {evidence_path}"]
    smoke_dir = out_dir / "xp-smoke-evidence"
    out_dir.mkdir(parents=True, exist_ok=True)
    smoke_dir.mkdir(parents=True, exist_ok=True)

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


def check_template_output_paths(*, out_dir: Path, evidence_path: Path, smoke_ids: list[str]) -> list[str]:
    hint_errors = check_directory_path_hint(out_dir, "XP native evidence template output directory")
    if hint_errors:
        return hint_errors
    if out_dir.is_symlink():
        return [f"XP native evidence template output directory must not be a symlink: {out_dir}"]
    parent_errors = check_path_parent_symlinks(out_dir, "XP native evidence template output directory")
    if parent_errors:
        return parent_errors
    if out_dir.exists() and not out_dir.is_dir():
        return [f"XP native evidence template output path must be a directory: {out_dir}"]
    smoke_dir = out_dir / "xp-smoke-evidence"
    errors: list[str] = []
    if evidence_path.is_symlink():
        errors.append(f"XP native evidence template file must not be a symlink: {evidence_path}")
    elif evidence_path.exists() and not evidence_path.is_file():
        errors.append(f"XP native evidence template file must be a regular file: {evidence_path}")
    if smoke_dir.is_symlink():
        errors.append(f"XP native evidence template smoke directory must not be a symlink: {smoke_dir}")
    elif smoke_dir.exists() and not smoke_dir.is_dir():
        errors.append(f"XP native evidence template smoke path must be a directory: {smoke_dir}")
    for smoke_id in smoke_ids:
        smoke_path = smoke_dir / f"{smoke_id}.txt"
        if smoke_path.is_symlink():
            errors.append(f"XP native evidence template smoke file must not be a symlink: {smoke_path}")
        elif smoke_path.exists() and not smoke_path.is_file():
            errors.append(f"XP native evidence template smoke file must be a regular file: {smoke_path}")
    return errors


def check_path_parent_symlinks(path: Path, label: str) -> list[str]:
    check_path = path if path.is_absolute() else Path.cwd() / path
    for parent in reversed(check_path.parents):
        if parent == Path("."):
            continue
        if parent.is_symlink():
            return [f"{label} path must not contain symlinked directories: {parent}"]
    return []


def check_directory_path_hint(path: Path, label: str) -> list[str]:
    raw_path = path.as_posix()
    if directory_path_has_file_suffix(raw_path):
        return [f"{label} must be a directory path, got {raw_path!r}"]
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
            **xp_edition_template(target_contract),
        },
        "toolchain": {
            "separate_legacy_toolchain": True,
            "current_python_pyqt6_stack": False,
            "description": "TODO describe the separate XP-capable native host toolchain used for this run",
        },
        "host_identity": {
            "schema_version": 1,
            "target": target,
            "release_tag": release_tag,
            "host_label": "TODO-use-sanitized-lab-label-not-real-hostname",
            "evidence_run_id": "TODO-use-sanitized-run-id",
            "observed_at_utc": "TODO-use-YYYY-MM-DDTHH:MM:SSZ",
            "operator_private_data_redacted": False,
            "os": {
                "name": target_contract["os_name"],
                "architecture": target_contract["architecture"],
                "service_pack": f"{target_contract['minimum_service_pack']} TODO replace with real winver evidence",
                **xp_edition_template(target_contract),
            },
            "toolchain": {
                "separate_legacy_toolchain": True,
                "current_python_pyqt6_stack": False,
                "description": "TODO describe the separate XP-capable native host toolchain used for this run",
            },
        },
        "artifact_validation": {
            "passed": False,
            "command": (
                f"python scripts/check_platform_promotion_artifacts.py --target {target} "
                f"--assets-dir <artifact-dir> --tag {release_tag} --strict"
            ),
        },
        "artifacts": required_artifacts(target, release_tag),
        "smoke_results": [
            {
                "id": smoke_id,
                "passed": False,
                "command": (
                    f"scripts/xp_smoke_runner.cmd --target {target} --release-tag {release_tag} "
                    f"--smoke-id {smoke_id} --evidence-file xp-smoke-evidence/{smoke_id}.txt "
                    f"--proof-file xp-smoke-proof/{smoke_id}.txt "
                    "--host-label TODO-use-sanitized-lab-label-not-real-hostname "
                    "--evidence-run-id TODO-use-sanitized-run-id"
                ),
                "evidence_file": f"xp-smoke-evidence/{smoke_id}.txt",
                "evidence_sha256": "<replace-with-real-sha256>",
            }
            for smoke_id in smoke_ids
        ],
        "security": {
            "legacy_crypto_profile_scoped": False,
            "modern_defaults_unchanged": False,
            "weak_crypto_global_default": True,
            "patch_evidence": {
                "tls_minimum_modern_profiles": "TODO verify TLS 1.2 minimum is unchanged",
                "tls_preferred_modern_profiles": "TODO verify TLS 1.3 preferred is unchanged",
                "legacy_compatibility_profile": "TODO verify isolated opt-in legacy profile only",
                "cve_patch_reviewed": False,
            },
        },
    }


def template_smoke_text(target: str, release_tag: str, smoke_id: str) -> str:
    return (
        f"xp smoke target: {target}\n"
        f"xp smoke release: {release_tag}\n"
        f"xp smoke id: {smoke_id}\n"
        "xp smoke host label: TODO-use-sanitized-lab-label-not-real-hostname\n"
        "xp smoke evidence run id: TODO-use-sanitized-run-id\n"
        f"{template_security_smoke_lines(smoke_id)}"
        f"Template evidence for {target} {release_tag} smoke id {smoke_id}.\n"
        "Replace this file with real Windows XP host output before validation.\n"
        "Do not include confidential access material or other sensitive values.\n"
    )


def template_security_smoke_lines(smoke_id: str) -> str:
    if smoke_id == "legacy_crypto_profile_scoped":
        return (
            "Required real proof lines:\n"
            "legacy compatibility profile: isolated-opt-in\n"
            "legacy crypto scope: profile-only\n"
            "weak crypto global default: false\n"
        )
    if smoke_id == "modern_defaults_unchanged":
        return (
            "Required real proof lines:\n"
            "modern TLS minimum: TLS 1.2\n"
            "modern TLS preferred: TLS 1.3\n"
            "modern defaults unchanged: true\n"
            "weak crypto global default: false\n"
        )
    return ""


def xp_edition_template(target_contract: dict[str, Any]) -> dict[str, str]:
    edition = str(target_contract.get("required_edition", ""))
    if not edition:
        return {}
    return {"edition": f"{edition} TODO replace with real winver evidence"}


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

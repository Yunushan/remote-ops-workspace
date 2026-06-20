from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "scripts"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from check_platform_promotion_artifacts import (  # noqa: E402
    check_platform_promotion_artifacts,
)
from check_platform_verified_evidence import (  # noqa: E402
    LINUX_TARGETS,
    check_linux_smoke_log_text,
    check_platform_verified_evidence,
    json_sha256,
    promotion_config_sha256,
    read_json,
)
from make_platform_verified_evidence_record import (  # noqa: E402
    artifact_sha256_map,
    expected_artifact_names,
    linux_smoke_evidence_sha256_map,
    sha256_file,
)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    errors = make_extended_linux_evidence_bundle(
        target=args.target,
        release_tag=args.release_tag,
        assets_dir=args.assets_dir,
        builder_evidence=args.builder_evidence,
        smoke_evidence=args.smoke_evidence,
        candidate_record=args.candidate_record,
        out_dir=args.out_dir,
        force=args.force,
    )
    if errors:
        for error in errors:
            print(f"extended Linux evidence bundle: {error}", file=sys.stderr)
        return 1
    print(f"extended Linux evidence bundle written to {args.out_dir}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate and package Linux i386/armhf native evidence into a "
            "reviewable bundle before accepted registry promotion."
        )
    )
    parser.add_argument("--target", choices=sorted(LINUX_TARGETS), required=True)
    parser.add_argument("--release-tag", required=True, help="Release tag, for example v1.0.2")
    parser.add_argument("--assets-dir", type=Path, required=True, help="directory containing Linux native artifacts")
    parser.add_argument("--builder-evidence", type=Path, required=True, help="builder identity JSON")
    parser.add_argument("--smoke-evidence", type=Path, required=True, help="native smoke log captured on the builder")
    parser.add_argument("--candidate-record", type=Path, required=True, help="candidate accepted-evidence JSON")
    parser.add_argument("--out-dir", type=Path, required=True, help="directory that will receive the bundle")
    parser.add_argument("--force", action="store_true", help="overwrite existing bundle outputs")
    return parser.parse_args(argv)


def make_extended_linux_evidence_bundle(
    *,
    target: str,
    release_tag: str,
    assets_dir: Path,
    builder_evidence: Path,
    smoke_evidence: Path,
    candidate_record: Path,
    out_dir: Path,
    force: bool = False,
) -> list[str]:
    errors: list[str] = []
    builder_identity = load_json(builder_evidence, "builder evidence", errors)
    candidate = load_json(candidate_record, "candidate evidence record", errors)
    if builder_identity is None or candidate is None:
        return errors
    if not smoke_evidence.is_file():
        errors.append(f"smoke evidence file missing: {smoke_evidence}")
    if candidate.get("target") != target:
        errors.append(f"bundle target {target} must match candidate target {candidate.get('target')!r}")
    if builder_identity.get("target") != target:
        errors.append(f"bundle target {target} must match builder evidence target {builder_identity.get('target')!r}")
    if candidate.get("release_tag") != release_tag:
        errors.append(f"bundle release_tag {release_tag} must match candidate release_tag {candidate.get('release_tag')!r}")

    promotion = read_json(ROOT / "configs" / "platform_parity_promotion.json")
    errors.extend(
        check_platform_promotion_artifacts(
            target=target,
            assets_dir=assets_dir,
            tag=release_tag,
        )
    )
    registry = {
        "schema_version": 1,
        "policy": platform_evidence_policy(),
        "accepted_evidence": [candidate],
    }
    errors.extend(check_platform_verified_evidence(registry=registry, promotion=promotion))
    if candidate.get("builder_identity") != builder_identity:
        errors.append("candidate builder_identity must match builder evidence JSON")
    if candidate.get("builder_identity_sha256") != json_sha256(builder_identity):
        errors.append("candidate builder_identity_sha256 must match builder evidence JSON")
    if candidate.get("linux_smoke_evidence_sha256") != linux_smoke_evidence_sha256_map(smoke_evidence):
        errors.append("candidate linux_smoke_evidence_sha256 must match smoke evidence file")
    if smoke_evidence.is_file():
        errors.extend(
            check_linux_smoke_evidence_file(
                target,
                release_tag,
                str(candidate.get("native_smoke_command", "")),
                str(candidate.get("workflow_run_url", "")),
                smoke_evidence,
                artifact_sha256=candidate.get("artifact_sha256"),
            )
        )
    actual_artifact_sha = artifact_sha256_map(target, release_tag, assets_dir, promotion)
    if candidate.get("artifact_sha256") != actual_artifact_sha:
        errors.append("candidate artifact_sha256 must match current artifact files")
    if errors:
        return errors

    out_dir.mkdir(parents=True, exist_ok=True)
    stem = f"extended-linux-evidence-bundle-{target}-{release_tag}"
    manifest_path = out_dir / f"{stem}.json"
    archive_path = out_dir / f"{stem}.zip"
    sha_path = out_dir / f"{stem}-SHA256SUMS.txt"
    outputs = (manifest_path, archive_path, sha_path)
    if not force:
        existing = [str(path) for path in outputs if path.exists()]
        if existing:
            return [f"refusing to overwrite existing extended Linux evidence bundle outputs: {existing}"]

    manifest = bundle_manifest(
        target=target,
        release_tag=release_tag,
        assets_dir=assets_dir,
        builder_evidence=builder_evidence,
        smoke_evidence=smoke_evidence,
        candidate_record=candidate_record,
        candidate=candidate,
        promotion=promotion,
    )
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_bundle_archive(
        archive_path=archive_path,
        manifest_path=manifest_path,
        builder_evidence=builder_evidence,
        smoke_evidence=smoke_evidence,
        candidate_record=candidate_record,
        assets_dir=assets_dir,
        artifact_names=expected_artifact_names(target, release_tag, promotion),
    )
    sha_path.write_text(
        f"{sha256_file(manifest_path)}  {manifest_path.name}\n"
        f"{sha256_file(archive_path)}  {archive_path.name}\n",
        encoding="utf-8",
    )
    return []


def load_json(path: Path, label: str, errors: list[str]) -> dict[str, Any] | None:
    if not path.is_file():
        errors.append(f"{label} file missing: {path}")
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"{label} file is not readable JSON: {path}: {exc}")
        return None
    if not isinstance(data, dict):
        errors.append(f"{label} file must contain a JSON object")
        return None
    return data


def check_linux_smoke_evidence_file(
    target: str,
    release_tag: str,
    native_smoke_command: str,
    workflow_run_url: str,
    smoke_evidence: Path,
    *,
    artifact_sha256: Any | None = None,
) -> list[str]:
    try:
        text = smoke_evidence.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return [f"{target} linux_smoke_evidence must be UTF-8 text: {exc}"]
    return check_linux_smoke_log_text(
        target,
        release_tag,
        native_smoke_command,
        workflow_run_url,
        text,
        artifact_sha256=artifact_sha256,
    )


def bundle_manifest(
    *,
    target: str,
    release_tag: str,
    assets_dir: Path,
    builder_evidence: Path,
    smoke_evidence: Path,
    candidate_record: Path,
    candidate: dict[str, Any],
    promotion: dict[str, Any],
) -> dict[str, Any]:
    return {
        "schema_version": 1,
        "bundle_type": "extended-linux-native-evidence",
        "target": target,
        "release_tag": release_tag,
        "validated_commands": [
            str(candidate.get("native_build_command", "")),
            str(candidate.get("native_smoke_command", "")),
            str(candidate.get("artifact_validation_command", "")),
            "python scripts/check_platform_verified_evidence.py",
        ],
        "release_asset_urls": candidate.get("release_asset_urls", []),
        "promotion_config_sha256": promotion_config_sha256(promotion),
        "workflow": candidate.get("workflow", ""),
        "workflow_inputs": candidate.get("workflow_inputs", {}),
        "workflow_run_url": candidate.get("workflow_run_url", ""),
        "runner_labels": candidate.get("runner_labels", []),
        "security_patch_evidence": candidate.get("builder_identity", {}).get("security_patch_evidence", {}),
        "builder_evidence": file_record(builder_evidence.name, builder_evidence),
        "smoke_evidence": [
            {"id": "native_smoke", **file_record(smoke_evidence.name, smoke_evidence)}
        ],
        "candidate_record": file_record(candidate_record.name, candidate_record),
        "artifacts": artifact_records(target, release_tag, assets_dir, promotion),
    }


def artifact_records(
    target: str,
    release_tag: str,
    assets_dir: Path,
    promotion: dict[str, Any],
) -> list[dict[str, Any]]:
    return [
        file_record(name, assets_dir / name)
        for name in expected_artifact_names(target, release_tag, promotion)
    ]


def file_record(name: str, path: Path) -> dict[str, Any]:
    return {
        "file": name,
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def write_bundle_archive(
    *,
    archive_path: Path,
    manifest_path: Path,
    builder_evidence: Path,
    smoke_evidence: Path,
    candidate_record: Path,
    assets_dir: Path,
    artifact_names: list[str],
) -> None:
    with zipfile.ZipFile(archive_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(manifest_path, arcname=manifest_path.name)
        archive.write(builder_evidence, arcname=builder_evidence.name)
        archive.write(smoke_evidence, arcname=smoke_evidence.name)
        archive.write(candidate_record, arcname=candidate_record.name)
        for name in artifact_names:
            archive.write(assets_dir / name, arcname=name)


def platform_evidence_policy() -> str:
    registry = read_json(ROOT / "configs" / "platform_verified_evidence.json")
    return str(registry.get("policy", ""))


if __name__ == "__main__":
    raise SystemExit(main())

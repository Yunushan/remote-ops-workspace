from __future__ import annotations

import argparse
import json
import re
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
    check_platform_verified_evidence,
    json_sha256,
    promotion_config_sha256,
    read_json,
    xp_native_evidence_contract_sha256,
)
from check_xp_native_evidence import check_xp_native_evidence  # noqa: E402
from make_platform_verified_evidence_record import (  # noqa: E402
    sha256_file,
    xp_evidence_summary,
    xp_host_identity_summary,
    xp_smoke_evidence_sha256_map,
)

TARGETS = ("windows-xp-native-x86", "windows-xp-native-x64")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    errors = make_xp_native_evidence_bundle(
        target=args.target,
        evidence=args.evidence,
        candidate_record=args.candidate_record,
        assets_dir=args.assets_dir,
        out_dir=args.out_dir,
        evidence_dir=args.evidence_dir,
        force=args.force,
    )
    if errors:
        for error in errors:
            print(f"XP native evidence bundle: {error}", file=sys.stderr)
        return 1
    print(f"XP native evidence bundle written to {args.out_dir}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate and package Windows XP native host evidence into a "
            "reviewable bundle before accepted registry promotion."
        )
    )
    parser.add_argument("--target", choices=TARGETS, required=True)
    parser.add_argument("--evidence", type=Path, required=True, help="XP native evidence JSON file")
    parser.add_argument("--candidate-record", type=Path, required=True, help="candidate accepted-evidence JSON file")
    parser.add_argument("--assets-dir", type=Path, required=True, help="directory containing XP native artifacts")
    parser.add_argument(
        "--evidence-dir",
        type=Path,
        help="directory containing smoke evidence files referenced by the XP evidence JSON",
    )
    parser.add_argument("--out-dir", type=Path, required=True, help="directory that will receive the bundle")
    parser.add_argument("--force", action="store_true", help="overwrite existing bundle outputs")
    return parser.parse_args(argv)


def make_xp_native_evidence_bundle(
    *,
    target: str,
    evidence: Path,
    candidate_record: Path,
    assets_dir: Path,
    out_dir: Path,
    evidence_dir: Path | None = None,
    force: bool = False,
) -> list[str]:
    errors: list[str] = []
    errors.extend(check_input_symlinks(evidence, candidate_record, evidence_dir=evidence_dir))
    if errors:
        return errors
    evidence_data = load_evidence(evidence, errors)
    candidate_data = load_json_file(candidate_record, "candidate evidence record", errors)
    if evidence_data is None:
        return errors
    if candidate_data is None:
        return errors
    errors.extend(check_candidate_is_unfinalized(candidate_data))
    if errors:
        return errors
    if evidence_data.get("target") != target:
        errors.append(f"bundle target {target} must match evidence target {evidence_data.get('target')!r}")
    release_tag = str(evidence_data.get("release_tag", ""))
    evidence_root = evidence_dir or evidence.parent
    if release_tag:
        artifact_errors = check_platform_promotion_artifacts(
            target=target,
            assets_dir=assets_dir,
            tag=release_tag,
            strict=True,
        )
    else:
        artifact_errors = ["XP evidence release_tag must be set before bundle artifact validation"]
    errors.extend(artifact_errors)
    if artifact_errors:
        return errors
    errors.extend(
        validate_candidate_record(
            target,
            release_tag,
            candidate_record,
            candidate_data,
            evidence,
            evidence_data,
            assets_dir,
            evidence_root,
        )
    )
    errors.extend(
        check_xp_native_evidence(
            evidence,
            assets_dir=assets_dir,
            evidence_dir=evidence_dir,
        )
    )
    if errors:
        return errors

    stem = f"xp-native-evidence-bundle-{target}-{release_tag}"
    manifest_path = out_dir / f"{stem}.json"
    archive_path = out_dir / f"{stem}.zip"
    sha_path = out_dir / f"{stem}-SHA256SUMS.txt"
    outputs = (manifest_path, archive_path, sha_path)
    errors.extend(prepare_output_paths(out_dir=out_dir, outputs=outputs, force=force))
    if errors:
        return errors

    manifest = bundle_manifest(
        target=target,
        release_tag=release_tag,
        evidence=evidence,
        candidate_record=candidate_record,
        evidence_root=evidence_root,
        evidence_data=evidence_data,
        candidate_data=candidate_data,
        assets_dir=assets_dir,
    )
    manifest_path.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    write_bundle_archive(
        archive_path=archive_path,
        manifest_path=manifest_path,
        evidence=evidence,
        candidate_record=candidate_record,
        evidence_root=evidence_root,
        evidence_data=evidence_data,
        assets_dir=assets_dir,
    )
    sha_path.write_text(
        f"{sha256_file(manifest_path)}  {manifest_path.name}\n"
        f"{sha256_file(archive_path)}  {archive_path.name}\n",
        encoding="utf-8",
    )
    return []


def check_input_symlinks(
    evidence: Path,
    candidate_record: Path,
    *,
    evidence_dir: Path | None,
) -> list[str]:
    inputs = {
        "evidence": evidence,
        "candidate evidence record": candidate_record,
    }
    if evidence_dir is not None:
        inputs["evidence directory"] = evidence_dir
    errors: list[str] = []
    for label, path in inputs.items():
        if path.is_symlink():
            errors.append(f"{label} must not be a symlink: {path}")
        errors.extend(check_path_parent_symlinks(path, label))
    return errors


def check_candidate_is_unfinalized(candidate: dict[str, Any]) -> list[str]:
    finalized_fields = sorted(
        field
        for field in ("finalized_record_release_asset_url", "review_bundle")
        if field in candidate
    )
    if finalized_fields:
        return [
            "candidate evidence record must be unfinalized before bundling; "
            f"remove fields: {finalized_fields}"
        ]
    return []


def prepare_output_paths(*, out_dir: Path, outputs: tuple[Path, ...], force: bool) -> list[str]:
    if out_dir.is_symlink():
        return [f"XP native evidence bundle output directory must not be a symlink: {out_dir}"]
    parent_errors = check_path_parent_symlinks(out_dir, "XP native evidence bundle output directory")
    if parent_errors:
        return parent_errors
    if out_dir.exists() and not out_dir.is_dir():
        return [f"XP native evidence bundle output path must be a directory: {out_dir}"]
    errors: list[str] = []
    for path in outputs:
        if path.is_symlink():
            errors.append(f"XP native evidence bundle output file must not be a symlink: {path.name}")
        elif path.exists() and not path.is_file():
            errors.append(f"XP native evidence bundle output must be a regular file: {path.name}")
    if errors:
        return errors
    if not force:
        existing = [str(path) for path in outputs if path.exists()]
        if existing:
            return [f"refusing to overwrite existing XP evidence bundle outputs: {existing}"]
    out_dir.mkdir(parents=True, exist_ok=True)
    return []


def check_path_parent_symlinks(path: Path, label: str) -> list[str]:
    check_path = path if path.is_absolute() else Path.cwd() / path
    for parent in reversed(check_path.parents):
        if parent == Path("."):
            continue
        if parent.is_symlink():
            return [f"{label} path must not contain symlinked directories: {parent}"]
    return []


def load_evidence(path: Path, errors: list[str]) -> dict[str, Any] | None:
    return load_json_file(path, "evidence", errors)


def load_json_file(path: Path, label: str, errors: list[str]) -> dict[str, Any] | None:
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


def validate_candidate_record(
    target: str,
    release_tag: str,
    candidate_record: Path,
    candidate_data: dict[str, Any],
    evidence: Path,
    evidence_data: dict[str, Any],
    assets_dir: Path,
    evidence_root: Path,
) -> list[str]:
    errors: list[str] = []
    promotion = read_json(ROOT / "configs" / "platform_parity_promotion.json")
    registry = {
        "schema_version": 1,
        "policy": platform_evidence_policy(),
        "accepted_evidence": [candidate_data],
    }
    errors.extend(check_platform_verified_evidence(registry=registry, promotion=promotion))
    if candidate_data.get("target") != target:
        errors.append(f"candidate record target must be {target}")
    if candidate_data.get("release_tag") != release_tag:
        errors.append(f"candidate record release_tag must match XP evidence release_tag {release_tag}")
    expected_evidence_command = xp_evidence_validation_command(
        evidence=evidence,
        assets_dir=assets_dir,
        evidence_root=evidence_root,
    )
    if candidate_data.get("native_evidence_validation_command") != expected_evidence_command:
        errors.append("candidate record native_evidence_validation_command must match bundled XP evidence inputs")
    if candidate_data.get("xp_evidence_sha256") != sha256_file(evidence):
        errors.append("candidate record xp_evidence_sha256 must match XP evidence file")
    if candidate_data.get("xp_host_identity_sha256") != json_sha256(xp_host_identity_summary(evidence_data)):
        errors.append("candidate record xp_host_identity_sha256 must match XP host identity")
    if candidate_data.get("xp_evidence_summary") != xp_evidence_summary(target, release_tag, evidence_data):
        errors.append("candidate record xp_evidence_summary must match XP evidence file")
    if candidate_data.get("xp_smoke_evidence_sha256") != xp_smoke_evidence_sha256_map(evidence_data):
        errors.append("candidate record xp_smoke_evidence_sha256 must match XP evidence smoke hashes")
    if candidate_data.get("xp_evidence_sources") != xp_evidence_sources(
        evidence=evidence,
        evidence_data=evidence_data,
        evidence_root=evidence_root,
    ):
        errors.append("candidate record xp_evidence_sources must match bundled XP evidence files")
    candidate_artifacts = candidate_data.get("artifact_sha256")
    if not isinstance(candidate_artifacts, dict):
        errors.append("candidate record artifact_sha256 must be an object")
    else:
        artifact_hashes = {
            path.name: sha256_file(path)
            for path in sorted(assets_dir.resolve().iterdir(), key=lambda item: item.name)
            if path.is_file()
        }
        if {str(name): str(digest) for name, digest in candidate_artifacts.items()} != artifact_hashes:
            errors.append("candidate record artifact_sha256 must exactly match XP artifact files")
    expected_candidate_name = f"platform-verified-evidence-{target}.json"
    if candidate_record.name != expected_candidate_name:
        errors.append(
            f"candidate record file name must be {expected_candidate_name}, got {candidate_record.name!r}"
        )
    return errors


def bundle_manifest(
    *,
    target: str,
    release_tag: str,
    evidence: Path,
    candidate_record: Path,
    evidence_root: Path,
    evidence_data: dict[str, Any],
    candidate_data: dict[str, Any],
    assets_dir: Path,
) -> dict[str, Any]:
    promotion = read_json(ROOT / "configs" / "platform_parity_promotion.json")
    return {
        "schema_version": 1,
        "bundle_type": "windows-xp-native-host-evidence",
        "target": target,
        "release_tag": release_tag,
        "validated_commands": [
            xp_evidence_validation_command(evidence=evidence, assets_dir=assets_dir, evidence_root=evidence_root),
            str(candidate_data.get("local_evidence_preflight_command", "")),
            xp_strict_artifact_validation_command(candidate_data),
            "python scripts/check_platform_verified_evidence.py",
        ],
        "workflow": candidate_data.get("workflow", ""),
        "workflow_inputs": candidate_data.get("workflow_inputs", {}),
        "release_asset_source": candidate_data.get("release_asset_source", {}),
        "xp_evidence_sources": candidate_data.get("xp_evidence_sources", {}),
        "release_asset_urls": candidate_data.get("release_asset_urls", []),
        "xp_evidence_contract_sha256": xp_native_evidence_contract_sha256(),
        "promotion_config_sha256": promotion_config_sha256(promotion),
        "evidence": file_record("xp-evidence.json", evidence),
        "candidate_record": file_record(candidate_record.name, candidate_record),
        "smoke_evidence": smoke_records(evidence_data, evidence_root),
        "artifacts": artifact_records(assets_dir),
        "candidate_summary": {
            "readiness_percent": candidate_data.get("readiness_percent"),
            "checks": candidate_data.get("checks", []),
        },
        "host_identity": evidence_data.get("host_identity", {}),
        "toolchain": evidence_data.get("toolchain", {}),
        "security": evidence_data.get("security", {}),
    }


def xp_evidence_validation_command(*, evidence: Path, assets_dir: Path, evidence_root: Path) -> str:
    return (
        "python scripts/check_xp_native_evidence.py "
        f"--evidence {evidence.as_posix()} --assets-dir {assets_dir.as_posix()}"
        f" --evidence-dir {evidence_root.as_posix()}"
    )


def xp_strict_artifact_validation_command(candidate_data: dict[str, Any]) -> str:
    command = str(candidate_data.get("artifact_validation_command", "")).strip()
    if not command:
        return ""
    if re.search(r"(?:^|\s)--strict(?=\s|$)", command):
        return command
    return f"{command} --strict"


def smoke_records(evidence_data: dict[str, Any], evidence_root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for item in evidence_data.get("smoke_results", []):
        if not isinstance(item, dict):
            continue
        raw_file = str(item.get("evidence_file", ""))
        path = evidence_root / raw_file
        records.append(
            {
                "id": str(item.get("id", "")),
                "file": raw_file,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return records


def xp_evidence_sources(
    *,
    evidence: Path,
    evidence_data: dict[str, Any],
    evidence_root: Path,
) -> dict[str, Any]:
    evidence_record = file_record("xp-evidence.json", evidence)
    evidence_record["path"] = evidence.as_posix()
    return {
        "evidence": evidence_record,
        "smoke_evidence": {
            str(record["id"]): {
                "file": str(record["file"]),
                "size_bytes": record["size_bytes"],
                "sha256": str(record["sha256"]),
            }
            for record in smoke_records(evidence_data, evidence_root)
            if record.get("id")
        },
    }


def artifact_records(assets_dir: Path) -> list[dict[str, Any]]:
    return [
        file_record(path.name, path)
        for path in sorted(assets_dir.resolve().iterdir(), key=lambda item: item.name)
        if path.is_file()
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
    evidence: Path,
    candidate_record: Path,
    evidence_root: Path,
    evidence_data: dict[str, Any],
    assets_dir: Path,
) -> None:
    with zipfile.ZipFile(archive_path, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.write(manifest_path, arcname=manifest_path.name)
        archive.write(evidence, arcname="xp-evidence.json")
        archive.write(candidate_record, arcname=candidate_record.name)
        for record in smoke_records(evidence_data, evidence_root):
            raw_file = str(record["file"])
            archive.write(evidence_root / raw_file, arcname=raw_file)
        for record in artifact_records(assets_dir):
            raw_file = str(record["file"])
            archive.write(assets_dir / raw_file, arcname=raw_file)


def platform_evidence_policy() -> str:
    registry = read_json(ROOT / "configs" / "platform_verified_evidence.json")
    return str(registry.get("policy", ""))


if __name__ == "__main__":
    raise SystemExit(main())

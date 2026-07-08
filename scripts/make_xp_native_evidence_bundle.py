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

from check_platform_goal_local_evidence import check_platform_goal_local_evidence  # noqa: E402
from check_platform_promotion_artifacts import (  # noqa: E402
    archive_entry_name_is_safe,
    check_platform_promotion_artifacts,
)
from check_platform_verified_evidence import (  # noqa: E402
    RESERVED_WORKSPACE_ROOTS,
    check_platform_verified_evidence,
    command_argument_values,
    directory_path_has_file_suffix,
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
RELEASE_TAG_RE = re.compile(r"^v\d+\.\d+\.\d+$")


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
    evidence: object,
    candidate_record: object,
    assets_dir: object,
    out_dir: object,
    evidence_dir: object | None = None,
    force: bool = False,
) -> list[str]:
    errors: list[str] = []
    errors.extend(check_required_path_arg(evidence, "XP native evidence file"))
    errors.extend(check_required_path_arg(candidate_record, "candidate evidence record"))
    errors.extend(check_required_path_arg(assets_dir, "XP native artifact directory"))
    errors.extend(check_required_path_arg(out_dir, "XP native evidence bundle output directory"))
    errors.extend(check_optional_path_arg(evidence_dir, "XP evidence directory"))
    if errors:
        return errors
    assert isinstance(evidence, Path)
    assert isinstance(candidate_record, Path)
    assert isinstance(assets_dir, Path)
    assert isinstance(out_dir, Path)
    assert evidence_dir is None or isinstance(evidence_dir, Path)
    evidence_root = evidence_dir or evidence.parent
    errors.extend(check_directory_path_hint(assets_dir, "XP native artifact directory"))
    errors.extend(check_directory_path_hint(evidence_root, "XP evidence directory"))
    errors.extend(check_path_not_reserved_workspace_root(assets_dir, "XP native artifact directory"))
    errors.extend(check_path_not_reserved_workspace_root(evidence_root, "XP evidence directory"))
    if errors:
        return errors
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
    release_tag_errors, release_tag = xp_evidence_release_tag_value(evidence_data)
    errors.extend(release_tag_errors)
    if errors:
        return errors
    artifact_errors = check_platform_promotion_artifacts(
        target=target,
        assets_dir=assets_dir,
        tag=release_tag,
        strict=True,
    )
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
    if not errors:
        errors.extend(
            check_local_protected_goal_preflight(
                target=target,
                release_tag=release_tag,
                assets_dir=assets_dir,
                evidence=evidence,
                evidence_root=evidence_root,
                candidate=candidate_data,
            )
        )
    if not errors:
        errors.extend(
            check_candidate_staged_upload_command(
                target=target,
                assets_dir=assets_dir,
                out_dir=out_dir,
                candidate=candidate_data,
            )
        )
    if errors:
        return errors

    stem = f"xp-native-evidence-bundle-{target}-{release_tag}"
    manifest_path = out_dir / f"{stem}.json"
    archive_path = out_dir / f"{stem}.zip"
    sha_path = out_dir / f"{stem}-SHA256SUMS.txt"
    outputs = (manifest_path, archive_path, sha_path)
    errors.extend(
        check_bundle_source_files(
            target=target,
            evidence=evidence,
            candidate_record=candidate_record,
            evidence_data=evidence_data,
            evidence_root=evidence_root,
            assets_dir=assets_dir,
        )
    )
    if errors:
        return errors
    errors.extend(
        check_target_release_path_segments(
            target,
            release_tag,
            out_dir,
            label="XP native evidence bundle output directory",
        )
    )
    if errors:
        return errors
    errors.extend(
        check_bundle_archive_entry_names(
            xp_bundle_archive_entry_names(
                manifest_path=manifest_path,
                candidate_record=candidate_record,
                evidence_data=evidence_data,
                evidence_root=evidence_root,
                assets_dir=assets_dir,
            ),
            label="XP native evidence bundle archive",
        )
    )
    if errors:
        return errors
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


def path_arg_value(raw_path: object, label: str) -> tuple[list[str], Path | None]:
    if not isinstance(raw_path, Path):
        return [f"{label} path must be a pathlib.Path, got {raw_path!r}"], None
    return [], raw_path


def check_required_path_arg(raw_path: object, label: str) -> list[str]:
    errors, _path = path_arg_value(raw_path, label)
    return errors


def check_optional_path_arg(raw_path: object | None, label: str) -> list[str]:
    if raw_path is None:
        return []
    return check_required_path_arg(raw_path, label)


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
        errors.extend(check_path_not_reserved_workspace_root(path, label))
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


def xp_evidence_release_tag_value(evidence: dict[str, Any]) -> tuple[list[str], str]:
    raw_release_tag = evidence.get("release_tag", "")
    if not isinstance(raw_release_tag, str) or not raw_release_tag:
        return [f"XP evidence release_tag must be a non-empty string, got {raw_release_tag!r}"], ""
    if raw_release_tag.strip() != raw_release_tag or not RELEASE_TAG_RE.fullmatch(raw_release_tag):
        return [f"XP evidence release_tag must look like vX.Y.Z, got {raw_release_tag!r}"], ""
    return [], raw_release_tag


def check_local_protected_goal_preflight(
    *,
    target: str,
    release_tag: str,
    assets_dir: Path,
    evidence: Path,
    evidence_root: Path,
    candidate: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    command = candidate.get("local_evidence_preflight_command")
    if not isinstance(command, str):
        errors.append(f"{target} candidate local_evidence_preflight_command must be a string")
        return [f"local protected-goal preflight failed: {error}" for error in errors]
    roots = command_argument_values(command, "--root")
    if len(roots) != 1:
        errors.append(f"{target} candidate local evidence preflight command must include exactly one --root")
        return [f"local protected-goal preflight failed: {error}" for error in errors]
    source = candidate.get("release_asset_source")
    if not isinstance(source, dict):
        errors.append(f"{target} candidate release_asset_source must be an object")
        return [f"local protected-goal preflight failed: {error}" for error in errors]
    source_workflow_run_url = source.get("workflow_run_url")
    source_head_sha = source.get("head_sha")
    source_run_attempt = source.get("run_attempt")
    if not isinstance(source_workflow_run_url, str):
        errors.append(f"{target} candidate release_asset_source.workflow_run_url must be a string")
    if not isinstance(source_head_sha, str):
        errors.append(f"{target} candidate release_asset_source.head_sha must be a string")
    if not is_positive_int(source_run_attempt):
        errors.append(f"{target} candidate release_asset_source.run_attempt must be a positive integer")
    if errors:
        return [f"local protected-goal preflight failed: {error}" for error in errors]
    preflight_errors = check_platform_goal_local_evidence(
        root=Path(roots[0]),
        release_tag=release_tag,
        targets=(target,),
        strict_artifacts=True,
        assets_dir=assets_dir,
        xp_evidence=evidence,
        xp_evidence_dir=evidence_root,
        xp_source_workflow_run_url=source_workflow_run_url,
        xp_source_head_sha=source_head_sha,
        xp_source_run_attempt=source_run_attempt,
    )
    return [f"local protected-goal preflight failed: {error}" for error in preflight_errors]


def is_positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def check_candidate_staged_upload_command(
    *,
    target: str,
    assets_dir: Path,
    out_dir: Path,
    candidate: dict[str, Any],
) -> list[str]:
    command = str(candidate.get("staged_upload_command", ""))
    errors: list[str] = []
    expected_assets_dir = assets_dir.as_posix()
    asset_dirs = command_argument_values(command, "--assets-dir")
    if asset_dirs != [expected_assets_dir]:
        errors.append(
            f"{target} candidate staged_upload_command --assets-dir must match "
            f"bundled artifact directory {expected_assets_dir!r}, got {asset_dirs}"
        )
    expected_evidence_output_dir = out_dir.as_posix()
    evidence_output_dirs = command_argument_values(command, "--evidence-output-dir")
    if evidence_output_dirs != [expected_evidence_output_dir]:
        errors.append(
            f"{target} candidate staged_upload_command --evidence-output-dir must match "
            f"bundle output directory {expected_evidence_output_dir!r}, got {evidence_output_dirs}"
        )
    return errors


def prepare_output_paths(*, out_dir: object, outputs: tuple[object, ...], force: bool) -> list[str]:
    out_dir_errors, out_dir_path = path_arg_value(out_dir, "XP native evidence bundle output directory")
    output_paths: list[Path] = []
    errors = out_dir_errors
    for output in outputs:
        output_errors, output_path = path_arg_value(output, "XP native evidence bundle output file")
        errors.extend(output_errors)
        if output_path is not None:
            output_paths.append(output_path)
    if errors:
        return errors
    assert out_dir_path is not None
    hint_errors = check_directory_path_hint(out_dir_path, "XP native evidence bundle output directory")
    if hint_errors:
        return hint_errors
    reserved_errors = check_path_not_reserved_workspace_root(out_dir_path, "XP native evidence bundle output directory")
    if reserved_errors:
        return reserved_errors
    if out_dir_path.is_symlink():
        return [f"XP native evidence bundle output directory must not be a symlink: {out_dir_path}"]
    parent_errors = check_path_parent_symlinks(out_dir_path, "XP native evidence bundle output directory")
    if parent_errors:
        return parent_errors
    if out_dir_path.exists() and not out_dir_path.is_dir():
        return [f"XP native evidence bundle output path must be a directory: {out_dir_path}"]
    errors = []
    for path in output_paths:
        if path.is_symlink():
            errors.append(f"XP native evidence bundle output file must not be a symlink: {path.name}")
        elif path.exists() and not path.is_file():
            errors.append(f"XP native evidence bundle output must be a regular file: {path.name}")
    if errors:
        return errors
    if not force:
        existing = [str(path) for path in output_paths if path.exists()]
        if existing:
            return [f"refusing to overwrite existing XP evidence bundle outputs: {existing}"]
    out_dir_path.mkdir(parents=True, exist_ok=True)
    return []


def is_allowed_platform_parent_symlink(parent: Path) -> bool:
    if sys.platform != "darwin" or parent.as_posix() != "/var":
        return False
    try:
        return parent.resolve(strict=False).as_posix() == "/private/var"
    except OSError:
        return False


def check_path_parent_symlinks(path: object, label: str) -> list[str]:
    path_errors, path_value = path_arg_value(path, label)
    if path_errors:
        return path_errors
    assert path_value is not None
    check_path = path_value if path_value.is_absolute() else Path.cwd() / path_value
    for parent in reversed(check_path.parents):
        if parent == Path("."):
            continue
        if parent.is_symlink() and not is_allowed_platform_parent_symlink(parent):
            return [f"{label} path must not contain symlinked directories: {parent}"]
    return []


def check_directory_path_hint(path: object, label: str) -> list[str]:
    path_errors, path_value = path_arg_value(path, label)
    if path_errors:
        return path_errors
    assert path_value is not None
    raw_path = path_value.as_posix()
    if directory_path_has_file_suffix(raw_path):
        return [f"{label} must be a directory path, got {raw_path!r}"]
    return []


def check_path_not_reserved_workspace_root(path: object, label: str) -> list[str]:
    path_errors, path_value = path_arg_value(path, label)
    if path_errors:
        return path_errors
    assert path_value is not None
    roots: list[Path] = [Path.cwd(), ROOT]
    seen_roots: set[Path] = set()
    for root in roots:
        root_resolved = root.resolve(strict=False)
        if root_resolved in seen_roots:
            continue
        seen_roots.add(root_resolved)
        path_resolved = (
            path_value if path_value.is_absolute() else root_resolved / path_value
        ).resolve(strict=False)
        try:
            relative = path_resolved.relative_to(root_resolved)
        except ValueError:
            continue
        parts = tuple(part for part in relative.parts if part not in ("", "."))
        if not parts:
            continue
        reserved_root = parts[0]
        if reserved_root in RESERVED_WORKSPACE_ROOTS:
            return [
                f"{label} must not point inside reserved workspace directory "
                f"{reserved_root!r}: {path_value}"
            ]
    return []


def check_target_release_path_segments(
    target: str,
    release_tag: str,
    path: object,
    *,
    label: str,
) -> list[str]:
    path_errors, path_value = path_arg_value(path, label)
    if path_errors:
        return path_errors
    assert path_value is not None
    segments = {str(part) for part in path_value.parts if str(part)}
    raw_path = path_value.as_posix()
    errors: list[str] = []
    if target not in segments:
        errors.append(f"{label} must include target path segment {target!r}, got {raw_path!r}")
    if release_tag not in segments:
        errors.append(f"{label} must include release_tag path segment {release_tag!r}, got {raw_path!r}")
    return errors


def load_evidence(path: Path, errors: list[str]) -> dict[str, Any] | None:
    return load_json_file(path, "evidence", errors)


def load_json_file(path: Path, label: str, errors: list[str]) -> dict[str, Any] | None:
    if not path.is_file():
        errors.append(f"{label} file missing: {path}")
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
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
        candidate_hashes: dict[str, str] = {}
        for name, digest in candidate_artifacts.items():
            if not isinstance(name, str):
                errors.append(f"candidate record artifact_sha256 key must be a string, got {name!r}")
                continue
            if not isinstance(digest, str):
                errors.append(
                    f"candidate record artifact_sha256 for {name} must be a string SHA-256 hex digest"
                )
                continue
            candidate_hashes[name] = digest
        if candidate_hashes != artifact_hashes:
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
            xp_strict_artifact_validation_command(candidate_data),
            str(candidate_data.get("local_evidence_preflight_command", "")),
            str(candidate_data.get("staged_upload_command", "")),
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


def check_bundle_source_files(
    *,
    target: str,
    evidence: Path,
    candidate_record: Path,
    evidence_data: dict[str, Any],
    evidence_root: Path,
    assets_dir: Path,
) -> list[str]:
    sources = [
        ("XP evidence source file", evidence),
        ("candidate evidence record source file", candidate_record),
    ]
    for _smoke_id, raw_file in smoke_result_refs(evidence_data):
        sources.append((f"{target} smoke evidence source file", evidence_root / raw_file))
    sources.extend(
        (f"{target} artifact source file", path)
        for path in sorted(assets_dir.iterdir(), key=lambda item: item.name)
    )
    errors: list[str] = []
    for label, path in sources:
        errors.extend(check_bundle_source_file(path, label))
    return errors


def check_bundle_source_file(path: object, label: str) -> list[str]:
    path_errors, path_value = path_arg_value(path, label)
    if path_errors:
        return path_errors
    assert path_value is not None
    errors: list[str] = []
    if path_value.is_symlink():
        errors.append(f"{label} must not be a symlink: {path_value}")
    errors.extend(check_path_parent_symlinks(path_value, label))
    if not path_value.is_file():
        errors.append(f"{label} must be a regular file: {path_value}")
    return errors


def smoke_records(evidence_data: dict[str, Any], evidence_root: Path) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for smoke_id, raw_file in smoke_result_refs(evidence_data):
        path = evidence_root / raw_file
        if not path.is_file():
            continue
        records.append(
            {
                "id": smoke_id,
                "file": raw_file,
                "size_bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return records


def smoke_result_refs(evidence_data: dict[str, Any]) -> list[tuple[str, str]]:
    refs: list[tuple[str, str]] = []
    raw_results = evidence_data.get("smoke_results", [])
    if not isinstance(raw_results, list):
        return refs
    for item in raw_results:
        if not isinstance(item, dict):
            continue
        smoke_id = item.get("id")
        raw_file = item.get("evidence_file")
        if (
            isinstance(smoke_id, str)
            and smoke_id
            and isinstance(raw_file, str)
            and raw_file
            and archive_entry_name_is_safe(raw_file)
        ):
            refs.append((smoke_id, raw_file))
    return refs


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


def xp_bundle_archive_entry_names(
    *,
    manifest_path: Path,
    candidate_record: Path,
    evidence_data: dict[str, Any],
    evidence_root: Path,
    assets_dir: Path,
) -> list[str]:
    return [
        manifest_path.name,
        "xp-evidence.json",
        candidate_record.name,
        *(str(record["file"]) for record in smoke_records(evidence_data, evidence_root)),
        *(str(record["file"]) for record in artifact_records(assets_dir)),
    ]


def check_bundle_archive_entry_names(entry_names: list[str], *, label: str) -> list[str]:
    errors: list[str] = []
    duplicates = sorted({name for name in entry_names if entry_names.count(name) > 1})
    if duplicates:
        errors.append(f"{label} entries must be unique; duplicate entries: {duplicates}")
    unsafe = sorted({name for name in entry_names if not archive_entry_name_is_safe(name)})
    if unsafe:
        errors.append(f"{label} entries must use safe relative paths: {unsafe}")
    case_groups: dict[str, set[str]] = {}
    for name in entry_names:
        case_groups.setdefault(name.casefold(), set()).add(name)
    case_collisions = sorted({name for names in case_groups.values() if len(names) > 1 for name in names})
    if case_collisions:
        errors.append(
            f"{label} entries must not collide on case-insensitive filesystems: {case_collisions}"
        )
    unique_names = sorted(set(entry_names))
    path_prefix_collisions = sorted(
        f"{parent} -> {child}"
        for parent in unique_names
        for child in unique_names
        if parent != child and child.startswith(f"{parent}/")
    )
    if path_prefix_collisions:
        errors.append(
            f"{label} entries must not contain file/path-prefix collisions: {path_prefix_collisions}"
        )
    return errors


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
        write_regular_file_to_zip(archive, manifest_path, manifest_path.name)
        write_regular_file_to_zip(archive, evidence, "xp-evidence.json")
        write_regular_file_to_zip(archive, candidate_record, candidate_record.name)
        for record in smoke_records(evidence_data, evidence_root):
            raw_file = str(record["file"])
            write_regular_file_to_zip(archive, evidence_root / raw_file, raw_file)
        for record in artifact_records(assets_dir):
            raw_file = str(record["file"])
            write_regular_file_to_zip(archive, assets_dir / raw_file, raw_file)


def write_regular_file_to_zip(archive: zipfile.ZipFile, path: Path, arcname: str) -> None:
    info = zipfile.ZipInfo(arcname)
    info.compress_type = zipfile.ZIP_DEFLATED
    info.create_system = 3
    info.external_attr = 0o100644 << 16
    archive.writestr(info, path.read_bytes())


def platform_evidence_policy() -> str:
    registry = read_json(ROOT / "configs" / "platform_verified_evidence.json")
    return str(registry.get("policy", ""))


if __name__ == "__main__":
    raise SystemExit(main())

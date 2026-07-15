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
    LINUX_TARGETS,
    RESERVED_WORKSPACE_ROOTS,
    check_linux_smoke_builder_identity_binding,
    check_linux_smoke_log_text,
    check_platform_verified_evidence,
    command_argument_values,
    directory_path_has_file_suffix,
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

RELEASE_TAG_RE = re.compile(r"^v\d+\.\d+\.\d+$")


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
    parser.add_argument("--release-tag", required=True, help="Release tag, for example v1.0.4")
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
    assets_dir: object,
    builder_evidence: object,
    smoke_evidence: object,
    candidate_record: object,
    out_dir: object,
    force: bool = False,
) -> list[str]:
    errors: list[str] = []
    errors.extend(check_required_path_arg(assets_dir, "artifact directory"))
    errors.extend(check_required_path_arg(builder_evidence, "builder evidence"))
    errors.extend(check_required_path_arg(smoke_evidence, "smoke evidence"))
    errors.extend(check_required_path_arg(candidate_record, "candidate evidence record"))
    errors.extend(check_required_path_arg(out_dir, "extended Linux evidence bundle output directory"))
    if errors:
        return errors
    assert isinstance(assets_dir, Path)
    assert isinstance(builder_evidence, Path)
    assert isinstance(smoke_evidence, Path)
    assert isinstance(candidate_record, Path)
    assert isinstance(out_dir, Path)
    errors.extend(check_directory_path_hint(assets_dir, "artifact directory"))
    errors.extend(check_path_not_reserved_workspace_root(assets_dir, "artifact directory"))
    if errors:
        return errors
    errors.extend(check_input_symlinks(builder_evidence, smoke_evidence, candidate_record))
    if errors:
        return errors
    release_tag_errors, release_tag = extended_linux_release_tag_value(release_tag)
    errors.extend(release_tag_errors)
    if errors:
        return errors
    builder_identity = load_json(builder_evidence, "builder evidence", errors)
    candidate = load_json(candidate_record, "candidate evidence record", errors)
    if builder_identity is None or candidate is None:
        return errors
    errors.extend(check_candidate_is_unfinalized(candidate))
    if errors:
        return errors
    errors.extend(check_linux_evidence_file_names(target, builder_evidence, smoke_evidence, candidate_record))
    if not smoke_evidence.is_file():
        errors.append(f"smoke evidence file missing: {smoke_evidence}")
    if candidate.get("target") != target:
        errors.append(f"bundle target {target} must match candidate target {candidate.get('target')!r}")
    if builder_identity.get("target") != target:
        errors.append(f"bundle target {target} must match builder evidence target {builder_identity.get('target')!r}")
    if candidate.get("release_tag") != release_tag:
        errors.append(f"bundle release_tag {release_tag} must match candidate release_tag {candidate.get('release_tag')!r}")

    promotion = read_json(ROOT / "configs" / "platform_parity_promotion.json")
    artifact_errors = check_platform_promotion_artifacts(
        target=target,
        assets_dir=assets_dir,
        tag=release_tag,
        strict=True,
    )
    errors.extend(artifact_errors)
    if artifact_errors:
        return errors
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
    expected_sources = {
        "builder_identity": source_file_record(
            builder_evidence.name,
            builder_evidence,
            sha256=str(candidate.get("builder_identity_sha256", "")),
        ),
        "native_smoke": file_record(smoke_evidence.name, smoke_evidence),
    }
    if candidate.get("linux_evidence_sources") != expected_sources:
        errors.append("candidate linux_evidence_sources must match builder and smoke evidence files")
    source = candidate.get("release_asset_source")
    source_head_sha = source_string_field(source, "head_sha")
    source_run_attempt = source.get("run_attempt") if isinstance(source, dict) else 0
    if smoke_evidence.is_file():
        errors.extend(
            check_linux_smoke_evidence_file(
                target,
                release_tag,
                string_field(candidate.get("native_smoke_command")),
                string_field(candidate.get("workflow_run_url")),
                source_run_attempt if isinstance(source_run_attempt, int) and not isinstance(source_run_attempt, bool) else 0,
                smoke_evidence,
                source_head_sha=source_head_sha,
                artifact_sha256=candidate.get("artifact_sha256"),
                builder_identity=builder_identity,
            )
        )
    actual_artifact_sha = artifact_sha256_map(target, release_tag, assets_dir, promotion)
    if candidate.get("artifact_sha256") != actual_artifact_sha:
        errors.append("candidate artifact_sha256 must match current artifact files")
    if not errors:
        errors.extend(
            check_local_protected_goal_preflight(
                target=target,
                release_tag=release_tag,
                assets_dir=assets_dir,
                builder_evidence=builder_evidence,
                smoke_evidence=smoke_evidence,
                candidate=candidate,
            )
        )
    if not errors:
        errors.extend(
            check_candidate_staged_upload_command(
                target=target,
                assets_dir=assets_dir,
                candidate=candidate,
            )
        )
    if errors:
        return errors

    stem = f"extended-linux-evidence-bundle-{target}-{release_tag}"
    manifest_path = out_dir / f"{stem}.json"
    archive_path = out_dir / f"{stem}.zip"
    sha_path = out_dir / f"{stem}-SHA256SUMS.txt"
    outputs = (manifest_path, archive_path, sha_path)
    artifact_names = expected_artifact_names(target, release_tag, promotion)
    errors.extend(
        check_target_release_path_segments(
            target,
            release_tag,
            out_dir,
            label="extended Linux evidence bundle output directory",
        )
    )
    if errors:
        return errors
    errors.extend(
        check_bundle_archive_entry_names(
            extended_linux_bundle_archive_entry_names(
                manifest_path=manifest_path,
                builder_evidence=builder_evidence,
                smoke_evidence=smoke_evidence,
                candidate_record=candidate_record,
                artifact_names=artifact_names,
            ),
            label="extended Linux evidence bundle archive",
        )
    )
    if errors:
        return errors
    errors.extend(
        check_bundle_source_files(
            target=target,
            builder_evidence=builder_evidence,
            smoke_evidence=smoke_evidence,
            candidate_record=candidate_record,
            assets_dir=assets_dir,
            artifact_names=artifact_names,
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
        artifact_names=artifact_names,
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


def check_input_symlinks(
    builder_evidence: Path,
    smoke_evidence: Path,
    candidate_record: Path,
) -> list[str]:
    inputs = {
        "builder evidence": builder_evidence,
        "smoke evidence": smoke_evidence,
        "candidate evidence record": candidate_record,
    }
    errors: list[str] = []
    for label, path in inputs.items():
        errors.extend(check_path_not_reserved_workspace_root(path, f"{label} file"))
        if path.is_symlink():
            errors.append(f"{label} file must not be a symlink: {path}")
        errors.extend(check_path_parent_symlinks(path, f"{label} file"))
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


def extended_linux_release_tag_value(release_tag: object) -> tuple[list[str], str]:
    if not isinstance(release_tag, str) or not release_tag:
        return [f"extended Linux evidence release_tag must be a non-empty string, got {release_tag!r}"], ""
    if release_tag.strip() != release_tag or not RELEASE_TAG_RE.fullmatch(release_tag):
        return [f"extended Linux evidence release_tag must look like vX.Y.Z, got {release_tag!r}"], ""
    return [], release_tag


def check_local_protected_goal_preflight(
    *,
    target: str,
    release_tag: str,
    assets_dir: Path,
    builder_evidence: Path,
    smoke_evidence: Path,
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
    workflow_run_url = candidate.get("workflow_run_url")
    source_workflow_run_url = source.get("workflow_run_url")
    source_head_sha = source.get("head_sha")
    source_run_attempt = source.get("run_attempt")
    if not isinstance(workflow_run_url, str):
        errors.append(f"{target} candidate workflow_run_url must be a string")
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
        linux_workflow_run_url=workflow_run_url,
        linux_source_head_sha=source_head_sha,
        linux_source_run_attempt=source_run_attempt,
        strict_artifacts=True,
        assets_dir=assets_dir,
        linux_builder_evidence=builder_evidence,
        linux_smoke_evidence=smoke_evidence,
    )
    return [f"local protected-goal preflight failed: {error}" for error in preflight_errors]


def is_positive_int(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def string_field(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def source_string_field(source: Any, field: str) -> str:
    if not isinstance(source, dict):
        return ""
    return string_field(source.get(field))


def check_candidate_staged_upload_command(
    *,
    target: str,
    assets_dir: Path,
    candidate: dict[str, Any],
) -> list[str]:
    command = str(candidate.get("staged_upload_command", ""))
    source_dirs = command_argument_values(command, "--source-dir")
    expected_source_dir = assets_dir.as_posix()
    if source_dirs != [expected_source_dir]:
        return [
            f"{target} candidate staged_upload_command --source-dir must match "
            f"bundled artifact directory {expected_source_dir!r}, got {source_dirs}"
        ]
    return []


def prepare_output_paths(*, out_dir: object, outputs: tuple[object, ...], force: bool) -> list[str]:
    out_dir_errors, out_dir_path = path_arg_value(
        out_dir,
        "extended Linux evidence bundle output directory",
    )
    output_paths: list[Path] = []
    errors = out_dir_errors
    for output in outputs:
        output_errors, output_path = path_arg_value(output, "extended Linux evidence bundle output file")
        errors.extend(output_errors)
        if output_path is not None:
            output_paths.append(output_path)
    if errors:
        return errors
    assert out_dir_path is not None
    hint_errors = check_directory_path_hint(out_dir_path, "extended Linux evidence bundle output directory")
    if hint_errors:
        return hint_errors
    reserved_errors = check_path_not_reserved_workspace_root(
        out_dir_path,
        "extended Linux evidence bundle output directory",
    )
    if reserved_errors:
        return reserved_errors
    if out_dir_path.is_symlink():
        return [f"extended Linux evidence bundle output directory must not be a symlink: {out_dir_path}"]
    parent_errors = check_path_parent_symlinks(out_dir_path, "extended Linux evidence bundle output directory")
    if parent_errors:
        return parent_errors
    if out_dir_path.exists() and not out_dir_path.is_dir():
        return [f"extended Linux evidence bundle output path must be a directory: {out_dir_path}"]
    errors = []
    for path in output_paths:
        if path.is_symlink():
            errors.append(f"extended Linux evidence bundle output file must not be a symlink: {path.name}")
        elif path.exists() and not path.is_file():
            errors.append(f"extended Linux evidence bundle output must be a regular file: {path.name}")
    if errors:
        return errors
    if not force:
        existing = [str(path) for path in output_paths if path.exists()]
        if existing:
            return [f"refusing to overwrite existing extended Linux evidence bundle outputs: {existing}"]
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


def load_json(path: Path, label: str, errors: list[str]) -> dict[str, Any] | None:
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


def check_linux_evidence_file_names(
    target: str,
    builder_evidence: Path,
    smoke_evidence: Path,
    candidate_record: Path,
) -> list[str]:
    expected = {
        "builder evidence": f"builder-identity-{target}.json",
        "smoke evidence": f"native-smoke-{target}.log",
        "candidate evidence record": f"platform-verified-evidence-{target}.json",
    }
    actual = {
        "builder evidence": builder_evidence.name,
        "smoke evidence": smoke_evidence.name,
        "candidate evidence record": candidate_record.name,
    }
    return [
        f"{label} file name must be {expected_name}, got {actual[label]!r}"
        for label, expected_name in expected.items()
        if actual[label] != expected_name
    ]


def check_bundle_source_files(
    *,
    target: str,
    builder_evidence: Path,
    smoke_evidence: Path,
    candidate_record: Path,
    assets_dir: Path,
    artifact_names: list[str],
) -> list[str]:
    sources = [
        ("builder evidence source file", builder_evidence),
        ("smoke evidence source file", smoke_evidence),
        ("candidate evidence record source file", candidate_record),
        *[
            (f"{target} artifact source file", assets_dir / name)
            for name in artifact_names
        ],
    ]
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


def check_linux_smoke_evidence_file(
    target: str,
    release_tag: str,
    native_smoke_command: str,
    workflow_run_url: str,
    workflow_run_attempt: int,
    smoke_evidence: Path,
    *,
    source_head_sha: str,
    artifact_sha256: Any | None = None,
    builder_identity: Any | None = None,
) -> list[str]:
    try:
        text = smoke_evidence.read_text(encoding="utf-8")
    except UnicodeDecodeError as exc:
        return [f"{target} linux_smoke_evidence must be UTF-8 text: {exc}"]
    errors = check_linux_smoke_log_text(
        target,
        release_tag,
        native_smoke_command,
        workflow_run_url,
        text,
        workflow_run_attempt=workflow_run_attempt,
        source_head_sha=source_head_sha,
        artifact_sha256=artifact_sha256,
    )
    if builder_identity is not None:
        errors.extend(
            check_linux_smoke_builder_identity_binding(
                target,
                "linux_smoke_evidence",
                text,
                builder_identity,
            )
        )
    return errors


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
            str(candidate.get("local_evidence_preflight_command", "")),
            str(candidate.get("staged_upload_command", "")),
            "python scripts/check_platform_verified_evidence.py",
        ],
        "release_asset_urls": candidate.get("release_asset_urls", []),
        "release_asset_source": candidate.get("release_asset_source", {}),
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


def extended_linux_bundle_archive_entry_names(
    *,
    manifest_path: Path,
    builder_evidence: Path,
    smoke_evidence: Path,
    candidate_record: Path,
    artifact_names: list[str],
) -> list[str]:
    return [
        manifest_path.name,
        builder_evidence.name,
        smoke_evidence.name,
        candidate_record.name,
        *artifact_names,
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
    return source_file_record(name, path, sha256=sha256_file(path))


def source_file_record(name: str, path: Path, *, sha256: str) -> dict[str, Any]:
    return {
        "file": name,
        "size_bytes": path.stat().st_size,
        "sha256": sha256,
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
        write_regular_file_to_zip(archive, manifest_path, manifest_path.name)
        write_regular_file_to_zip(archive, builder_evidence, builder_evidence.name)
        write_regular_file_to_zip(archive, smoke_evidence, smoke_evidence.name)
        write_regular_file_to_zip(archive, candidate_record, candidate_record.name)
        for name in artifact_names:
            write_regular_file_to_zip(archive, assets_dir / name, name)


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

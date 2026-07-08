from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import zipfile
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "scripts"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from check_platform_verified_evidence import (  # noqa: E402
    GITHUB_RELEASE_ASSET_RE,
    KNOWN_TARGETS,
    RESERVED_WORKSPACE_ROOTS,
    REVIEW_BUNDLE_TYPES,
    accepted_record_source_file,
    check_linux_smoke_builder_identity_binding,
    check_linux_smoke_log_text,
    check_platform_verified_evidence,
    read_json,
    release_asset_url_filename,
    review_bundle_expected_files,
)
from check_xp_native_evidence import (  # noqa: E402
    check_security_smoke_evidence_lines,
    check_smoke_evidence_binding,
)
from make_platform_verified_evidence_record import (  # noqa: E402
    EVIDENCE_PATH,
    append_record_to_registry,
    check_path_parent_symlinks,
    sha256_file,
    write_text_output,
    xp_evidence_summary,
    xp_smoke_evidence_sha256_map,
)
from make_platform_verified_evidence_record import (  # noqa: E402
    check_text_output_path as check_base_text_output_path,
)

SHA256_HEX_RE = re.compile(r"[0-9a-f]{64}")
GIT_SHA_RE = re.compile(r"[0-9a-f]{40}")
RELEASE_TAG_RE = re.compile(r"v\d+\.\d+\.\d+")
MANIFEST_FILE_RECORD_KEYS = {"file", "sha256", "size_bytes"}
MANIFEST_SMOKE_RECORD_KEYS = MANIFEST_FILE_RECORD_KEYS | {"id"}
LINUX_BUNDLE_MANIFEST_KEYS = {
    "artifacts",
    "builder_evidence",
    "bundle_type",
    "candidate_record",
    "promotion_config_sha256",
    "release_asset_source",
    "release_asset_urls",
    "release_tag",
    "runner_labels",
    "schema_version",
    "security_patch_evidence",
    "smoke_evidence",
    "target",
    "validated_commands",
    "workflow",
    "workflow_inputs",
    "workflow_run_url",
}
XP_BUNDLE_MANIFEST_KEYS = {
    "artifacts",
    "bundle_type",
    "candidate_record",
    "candidate_summary",
    "evidence",
    "host_identity",
    "promotion_config_sha256",
    "release_asset_source",
    "release_asset_urls",
    "release_tag",
    "schema_version",
    "security",
    "smoke_evidence",
    "target",
    "toolchain",
    "validated_commands",
    "workflow",
    "workflow_inputs",
    "xp_evidence_contract_sha256",
    "xp_evidence_sources",
}
BUNDLE_MANIFEST_KEYS_BY_TYPE = {
    "extended-linux-native-evidence": LINUX_BUNDLE_MANIFEST_KEYS,
    "windows-xp-native-host-evidence": XP_BUNDLE_MANIFEST_KEYS,
}


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.append_registry and not args.out:
        print(
            "finalize platform evidence record: --append-registry requires --out "
            "so the finalized release artifact is written before registry append",
            file=sys.stderr,
        )
        return 1
    errors, record = finalize_platform_verified_evidence_record(
        candidate_record=args.candidate_record,
        bundle_manifest=args.bundle_manifest,
        bundle_archive=args.bundle_archive,
        bundle_sha256s=args.bundle_sha256s,
    )
    if errors:
        for error in errors:
            print(f"finalize platform evidence record: {error}", file=sys.stderr)
        return 1

    output = json.dumps(record, indent=2, sort_keys=True) + "\n"
    if args.out:
        output_errors = check_finalized_record_output_path(
            args.out,
            record,
            bundle_manifest=args.bundle_manifest,
        )
        if output_errors:
            for error in output_errors:
                print(f"finalize platform evidence record: {error}", file=sys.stderr)
            return 1
        write_text_output(args.out, output)
        output_errors = check_finalized_record_output_bytes(args.out, output)
        if output_errors:
            for error in output_errors:
                print(f"finalize platform evidence record: {error}", file=sys.stderr)
            return 1
    else:
        print(output, end="")

    if args.append_registry:
        registry_errors = append_record_to_registry(record, registry_path=args.registry)
        if registry_errors:
            for error in registry_errors:
                print(f"finalize platform evidence record: {error}", file=sys.stderr)
            return 1
        print(f"finalized platform evidence record appended to {args.registry}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Attach packaged review-bundle hashes to a platform accepted-evidence "
            "candidate and validate the strict promotion record."
        )
    )
    parser.add_argument("--candidate-record", type=Path, required=True, help="candidate accepted-evidence JSON")
    parser.add_argument("--bundle-manifest", type=Path, required=True, help="review bundle manifest JSON")
    parser.add_argument("--bundle-archive", type=Path, required=True, help="review bundle zip archive")
    parser.add_argument("--bundle-sha256s", type=Path, required=True, help="review bundle SHA256SUMS sidecar")
    parser.add_argument("--out", type=Path, help="write the finalized accepted-evidence record to this path")
    parser.add_argument("--append-registry", action="store_true", help="append the finalized record to the registry")
    parser.add_argument("--registry", type=Path, default=EVIDENCE_PATH, help="registry path used with --append-registry")
    return parser.parse_args(argv)


def finalize_platform_verified_evidence_record(
    *,
    candidate_record: object,
    bundle_manifest: object,
    bundle_archive: object,
    bundle_sha256s: object,
) -> tuple[list[str], dict[str, Any]]:
    errors: list[str] = []
    candidate_record_errors, candidate_record_path = path_arg_value(
        candidate_record,
        "candidate evidence record",
    )
    manifest_errors, bundle_manifest_path = path_arg_value(
        bundle_manifest,
        "review bundle manifest",
    )
    archive_errors, bundle_archive_path = path_arg_value(
        bundle_archive,
        "review bundle archive",
    )
    sidecar_errors, bundle_sha256s_path = path_arg_value(
        bundle_sha256s,
        "review bundle SHA-256 sidecar",
    )
    errors.extend(candidate_record_errors)
    errors.extend(manifest_errors)
    errors.extend(archive_errors)
    errors.extend(sidecar_errors)
    if errors:
        return errors, {}

    assert candidate_record_path is not None
    assert bundle_manifest_path is not None
    assert bundle_archive_path is not None
    assert bundle_sha256s_path is not None

    candidate = load_json(candidate_record_path, "candidate evidence record", errors)
    manifest = load_json(bundle_manifest_path, "review bundle manifest", errors)
    for label, path in (
        ("review bundle archive", bundle_archive_path),
        ("review bundle SHA-256 sidecar", bundle_sha256s_path),
    ):
        check_input_file(path, label, errors)
    errors.extend(
        check_review_bundle_input_siblings(
            bundle_manifest_path,
            bundle_archive_path,
            bundle_sha256s_path,
        )
    )
    if candidate is None or manifest is None or errors:
        return errors, {}

    target_errors, target = candidate_target_value(candidate)
    release_tag_errors, release_tag = candidate_release_tag_value(candidate)
    errors.extend(target_errors)
    errors.extend(release_tag_errors)
    if target in KNOWN_TARGETS:
        errors.extend(check_candidate_record_file_name(candidate_record_path, target))
    if target and manifest.get("target") != target:
        errors.append(f"review bundle manifest target must match candidate target {target}")
    if release_tag and manifest.get("release_tag") != release_tag:
        errors.append(f"review bundle manifest release_tag must match candidate release_tag {release_tag}")
    expected_bundle_type = REVIEW_BUNDLE_TYPES.get(target)
    if expected_bundle_type and manifest.get("bundle_type") != expected_bundle_type:
        errors.append(f"review bundle manifest bundle_type must be {expected_bundle_type}")
    candidate_finalization_errors = check_candidate_is_unfinalized(candidate)
    errors.extend(candidate_finalization_errors)
    if not candidate_finalization_errors:
        errors.extend(check_unfinalized_candidate_record(candidate))
    errors.extend(check_bundle_manifest_records(manifest))
    errors.extend(check_candidate_manifest_binding(candidate_record_path, candidate, manifest))

    expected_files: dict[str, str] = {}
    if target in KNOWN_TARGETS:
        expected_files = review_bundle_expected_files(target, release_tag)
        actual_files = {
            "manifest": bundle_manifest_path.name,
            "archive": bundle_archive_path.name,
            "sha256s": bundle_sha256s_path.name,
        }
        for key, expected_file in expected_files.items():
            if actual_files[key] != expected_file:
                errors.append(f"review bundle {key} file must be {expected_file}, got {actual_files[key]}")
        errors.extend(check_candidate_release_asset_source_files(candidate, expected_files))

    errors.extend(check_bundle_sidecar(bundle_sha256s_path, bundle_manifest_path, bundle_archive_path))
    errors.extend(check_bundle_archive(bundle_archive_path, bundle_manifest_path, manifest, candidate))
    bundle_url_errors, review_bundle_urls = review_bundle_release_asset_urls(candidate, expected_files)
    errors.extend(bundle_url_errors)
    final_url_errors, finalized_record_url = finalized_record_release_asset_url(candidate)
    errors.extend(final_url_errors)
    if errors:
        return errors, {}

    record = dict(candidate)
    record["finalized_record_release_asset_url"] = finalized_record_url
    record["review_bundle"] = {
        "bundle_type": str(manifest.get("bundle_type", "")),
        "manifest": file_record(bundle_manifest_path),
        "archive": file_record(bundle_archive_path),
        "sha256s": file_record(bundle_sha256s_path),
        "release_asset_urls": review_bundle_urls,
    }
    record["release_asset_source"] = finalized_release_asset_source(record, expected_files)
    registry = {
        "schema_version": 1,
        "policy": platform_evidence_policy(),
        "accepted_evidence": [record],
    }
    errors.extend(check_platform_verified_evidence(registry=registry, require_review_bundles=True))
    if errors:
        return errors, {}
    return [], record


def path_arg_value(raw_path: object, label: str) -> tuple[list[str], Path | None]:
    if not isinstance(raw_path, Path):
        return [f"{label} path must be a pathlib.Path, got {raw_path!r}"], None
    return [], raw_path


def finalized_release_asset_source(
    record: dict[str, Any],
    review_bundle_files: dict[str, str],
) -> dict[str, Any]:
    source = record.get("release_asset_source")
    source_data = dict(source) if isinstance(source, dict) else {}
    artifact_files = record.get("artifact_sha256")
    expected_files: set[str] = set()
    if isinstance(artifact_files, dict):
        expected_files.update(str(name) for name in artifact_files)
    expected_files.update(str(name) for name in review_bundle_files.values())
    target = str(record.get("target", ""))
    if target in KNOWN_TARGETS:
        expected_files.add(accepted_record_source_file(target))
    source_data["contains_files"] = sorted(expected_files)
    return source_data


def check_candidate_is_unfinalized(candidate: dict[str, Any]) -> list[str]:
    finalized_fields = sorted(
        field
        for field in ("finalized_record_release_asset_url", "review_bundle")
        if field in candidate
    )
    if finalized_fields:
        return [
            "candidate evidence record must be unfinalized before finalization; "
            f"remove fields: {finalized_fields}"
        ]
    return []


def candidate_target_value(candidate: dict[str, Any]) -> tuple[list[str], str]:
    raw_target = candidate.get("target", "")
    if not isinstance(raw_target, str) or not raw_target:
        return [f"candidate target must be a non-empty string, got {raw_target!r}"], ""
    if raw_target not in KNOWN_TARGETS:
        return [f"candidate target is not protected: {raw_target}"], raw_target
    return [], raw_target


def candidate_release_tag_value(candidate: dict[str, Any]) -> tuple[list[str], str]:
    raw_release_tag = candidate.get("release_tag", "")
    if not isinstance(raw_release_tag, str) or not raw_release_tag:
        return [f"candidate release_tag must be a non-empty string, got {raw_release_tag!r}"], ""
    if not RELEASE_TAG_RE.fullmatch(raw_release_tag):
        return [f"candidate release_tag must look like vX.Y.Z, got {raw_release_tag!r}"], raw_release_tag
    return [], raw_release_tag


def check_unfinalized_candidate_record(candidate: dict[str, Any]) -> list[str]:
    registry = {
        "schema_version": 1,
        "policy": platform_evidence_policy(),
        "accepted_evidence": [candidate],
    }
    return [
        f"candidate evidence record failed strict candidate validation: {error}"
        for error in check_platform_verified_evidence(
            registry=registry,
            require_review_bundles=False,
        )
    ]


def check_candidate_release_asset_source_files(
    candidate: dict[str, Any],
    review_bundle_files: dict[str, str],
) -> list[str]:
    target = str(candidate.get("target", ""))
    source = candidate.get("release_asset_source")
    if not isinstance(source, dict):
        return ["candidate release_asset_source must be an object before finalization"]
    raw_files = source.get("contains_files")
    if not isinstance(raw_files, list) or not raw_files:
        return ["candidate release_asset_source.contains_files must be a non-empty list before finalization"]
    files = [filename for filename in raw_files if isinstance(filename, str)]
    duplicate_files = sorted({filename for filename in files if files.count(filename) > 1})
    unsafe_files = sorted(
        {
            filename if isinstance(filename, str) else repr(filename)
            for filename in raw_files
            if not isinstance(filename, str) or not concrete_file_name(filename)
        }
    )
    artifact_hashes = candidate.get("artifact_sha256")
    unsafe_artifact_files = sorted(
        {
            filename if isinstance(filename, str) else repr(filename)
            for filename in artifact_hashes
            if not isinstance(filename, str) or not concrete_file_name(filename)
        }
    ) if isinstance(artifact_hashes, dict) else []
    artifact_files = (
        {filename for filename in artifact_hashes if isinstance(filename, str) and concrete_file_name(filename)}
        if isinstance(artifact_hashes, dict)
        else set()
    )
    actual_files = set(files)
    missing_artifacts = sorted(artifact_files - actual_files)
    finalization_only_files = set(review_bundle_files.values())
    if target in KNOWN_TARGETS:
        finalization_only_files.add(accepted_record_source_file(target))
    unexpected_files = sorted(actual_files - artifact_files)
    errors: list[str] = []
    if duplicate_files:
        errors.append(f"candidate release_asset_source.contains_files has duplicate files: {duplicate_files}")
    if unsafe_files:
        errors.append(f"candidate release_asset_source.contains_files has unsafe file names: {unsafe_files}")
    if unsafe_artifact_files:
        errors.append(f"candidate artifact_sha256 keys must be safe file names: {unsafe_artifact_files}")
    if missing_artifacts:
        errors.append(f"candidate release_asset_source.contains_files missing native artifacts: {missing_artifacts}")
    if unexpected_files:
        finalization_only = sorted(set(unexpected_files) & finalization_only_files)
        if finalization_only:
            errors.append(
                "candidate release_asset_source.contains_files must not include "
                f"finalization-only files before finalization: {finalization_only}"
            )
        other_unexpected = sorted(set(unexpected_files) - finalization_only_files)
        if other_unexpected:
            errors.append(
                "candidate release_asset_source.contains_files has files outside native artifacts: "
                f"{other_unexpected}"
            )
    return errors


def concrete_file_name(filename: str) -> bool:
    if (
        not filename
        or filename.strip() != filename
        or filename in (".", "..")
        or "<" in filename
        or ">" in filename
        or "/" in filename
        or "\\" in filename
    ):
        return False
    windows_path = PureWindowsPath(filename)
    posix_path = PurePosixPath(filename)
    return not windows_path.drive and not windows_path.is_absolute() and not posix_path.is_absolute()


def review_bundle_release_asset_urls(
    candidate: dict[str, Any],
    expected_files: dict[str, str],
) -> tuple[list[str], list[str]]:
    if not expected_files:
        return ["review bundle expected files could not be derived"], []
    release_tag_errors, release_tag = candidate_release_tag_value(candidate)
    if release_tag_errors:
        return release_tag_errors, []
    raw_urls = candidate.get("release_asset_urls")
    if not isinstance(raw_urls, list) or not raw_urls:
        return ["candidate release_asset_urls must be a non-empty list before deriving review bundle URLs"], []
    errors, base_urls = candidate_release_asset_base_urls(raw_urls, release_tag)
    if len(base_urls) != 1:
        errors.append(f"candidate release_asset_urls must use one GitHub release asset base URL, got {sorted(base_urls)}")
    if errors:
        return errors, []
    base_url = next(iter(base_urls))
    return [], [f"{base_url}/{filename}" for filename in expected_files.values()]


def finalized_record_release_asset_url(candidate: dict[str, Any]) -> tuple[list[str], str]:
    target_errors, target = candidate_target_value(candidate)
    release_tag_errors, release_tag = candidate_release_tag_value(candidate)
    if target_errors or release_tag_errors:
        return [*target_errors, *release_tag_errors], ""
    raw_urls = candidate.get("release_asset_urls")
    if not isinstance(raw_urls, list) or not raw_urls:
        return ["candidate release_asset_urls must be a non-empty list before deriving final record URL"], ""
    errors, base_urls = candidate_release_asset_base_urls(raw_urls, release_tag)
    if len(base_urls) != 1:
        errors.append(
            f"candidate release_asset_urls must use one GitHub release asset base URL, got {sorted(base_urls)}"
        )
    if errors:
        return errors, ""
    base_url = next(iter(base_urls))
    return [], f"{base_url}/{accepted_record_source_file(target)}"


def candidate_release_asset_base_urls(raw_urls: list[Any], release_tag: str) -> tuple[list[str], set[str]]:
    errors: list[str] = []
    base_urls: set[str] = set()
    for raw_url in raw_urls:
        if not isinstance(raw_url, str):
            errors.append(f"candidate release_asset_url must be a string, got {raw_url!r}")
            continue
        url = raw_url
        match = GITHUB_RELEASE_ASSET_RE.fullmatch(url)
        if not match:
            errors.append(f"candidate release_asset_url is not a GitHub release asset URL: {url}")
            continue
        if match.group(2) != release_tag:
            errors.append(f"candidate release_asset_url tag must match release_tag {release_tag}: {url}")
            continue
        if not release_asset_url_filename(url):
            errors.append(f"candidate release_asset_url file name must be an exact safe file name: {url}")
            continue
        base_urls.add(url.rsplit("/", 1)[0])
    return errors, base_urls


def check_bundle_manifest_records(manifest: dict[str, Any]) -> list[str]:
    bundle_type = str(manifest.get("bundle_type", ""))
    errors: list[str] = []
    errors.extend(check_bundle_manifest_top_level_keys(manifest, bundle_type))
    if bundle_type == "extended-linux-native-evidence":
        for key in ("builder_evidence", "candidate_record"):
            record = manifest.get(key)
            if not isinstance(record, dict):
                errors.append(f"review bundle manifest {key} must be an object")
            else:
                errors.extend(check_manifest_record_metadata(key, record, require_concrete_file=True))
        smoke_evidence = manifest.get("smoke_evidence")
        if not isinstance(smoke_evidence, list) or not smoke_evidence:
            errors.append("review bundle manifest smoke_evidence must be a non-empty list")
        elif not all(isinstance(item, dict) for item in smoke_evidence):
            errors.append("review bundle manifest smoke_evidence entries must be objects")
        else:
            errors.extend(
                check_manifest_record_collection_metadata(
                    "smoke_evidence",
                    smoke_evidence,
                    require_concrete_file=False,
                    allowed_keys=MANIFEST_SMOKE_RECORD_KEYS,
                )
            )
        errors.extend(
            check_manifest_record_collection_metadata(
                "artifacts",
                manifest.get("artifacts"),
                require_concrete_file=True,
                allowed_keys=MANIFEST_FILE_RECORD_KEYS,
            )
        )
    elif bundle_type == "windows-xp-native-host-evidence":
        evidence_record = manifest.get("evidence")
        if not isinstance(evidence_record, dict):
            errors.append("review bundle manifest evidence must be an object")
        else:
            errors.extend(check_manifest_record_metadata("evidence", evidence_record, require_concrete_file=True))
        candidate_record = manifest.get("candidate_record")
        if not isinstance(candidate_record, dict):
            errors.append("review bundle manifest candidate_record must be an object")
        else:
            errors.extend(
                check_manifest_record_metadata(
                    "candidate_record",
                    candidate_record,
                    require_concrete_file=True,
                )
            )
        smoke_evidence = manifest.get("smoke_evidence")
        if not isinstance(smoke_evidence, list) or not smoke_evidence:
            errors.append("review bundle manifest smoke_evidence must be a non-empty list")
        elif not all(isinstance(item, dict) for item in smoke_evidence):
            errors.append("review bundle manifest smoke_evidence entries must be objects")
        else:
            errors.extend(
                check_manifest_record_collection_metadata(
                    "smoke_evidence",
                    smoke_evidence,
                    require_concrete_file=False,
                    allowed_keys=MANIFEST_SMOKE_RECORD_KEYS,
                )
            )
        errors.extend(
            check_manifest_record_collection_metadata(
                "artifacts",
                manifest.get("artifacts"),
                require_concrete_file=True,
                allowed_keys=MANIFEST_FILE_RECORD_KEYS,
            )
        )
    elif bundle_type not in BUNDLE_MANIFEST_KEYS_BY_TYPE:
        errors.append(
            "review bundle manifest bundle_type must be one of "
            f"{sorted(BUNDLE_MANIFEST_KEYS_BY_TYPE)}, got {bundle_type!r}"
        )
    return errors


def check_bundle_manifest_top_level_keys(
    manifest: dict[str, Any],
    bundle_type: str,
) -> list[str]:
    errors: list[str] = []
    expected_keys = BUNDLE_MANIFEST_KEYS_BY_TYPE.get(bundle_type)
    if expected_keys is None:
        return errors
    keys: set[str] = set()
    for key in manifest:
        if not isinstance(key, str):
            errors.append(f"review bundle manifest fields must be strings, got {key!r}")
            continue
        keys.add(key)
    missing = sorted(expected_keys - keys)
    unexpected = sorted(keys - expected_keys)
    if missing:
        errors.append(f"review bundle manifest missing fields: {missing}")
    if unexpected:
        errors.append(f"review bundle manifest has unexpected fields: {unexpected}")
    schema_version = manifest.get("schema_version")
    if schema_version != 1 or isinstance(schema_version, bool):
        errors.append("review bundle manifest schema_version must be 1")
    return errors


def check_manifest_record_collection_metadata(
    label: str,
    raw_records: Any,
    *,
    require_concrete_file: bool,
    allowed_keys: set[str],
) -> list[str]:
    if not isinstance(raw_records, list):
        return []
    errors: list[str] = []
    for index, item in enumerate(raw_records):
        if isinstance(item, dict):
            errors.extend(
                check_manifest_record_metadata(
                    f"{label}[{index}]",
                    item,
                    require_concrete_file=require_concrete_file,
                    allowed_keys=allowed_keys,
                )
            )
    return errors


def check_manifest_record_metadata(
    label: str,
    record: dict[str, Any],
    *,
    require_concrete_file: bool,
    allowed_keys: set[str] = MANIFEST_FILE_RECORD_KEYS,
) -> list[str]:
    errors: list[str] = []
    errors.extend(check_manifest_record_keys(label, record, allowed_keys))
    raw_filename = record.get("file", "")
    if not isinstance(raw_filename, str):
        errors.append(f"review bundle manifest {label}.file must be a string, got {raw_filename!r}")
    elif not raw_filename:
        errors.append(f"review bundle manifest {label}.file must be set")
    elif require_concrete_file and not concrete_file_name(raw_filename):
        errors.append(
            f"review bundle manifest {label}.file must be an exact safe file name: "
            f"{raw_filename!r}"
        )
    elif not require_concrete_file and not archive_entry_name_is_safe(raw_filename):
        errors.append(
            f"review bundle manifest {label}.file must be a safe relative archive path: "
            f"{raw_filename!r}"
        )

    raw_size = record.get("size_bytes")
    if not isinstance(raw_size, int) or isinstance(raw_size, bool) or raw_size <= 0:
        errors.append(f"review bundle manifest {label}.size_bytes must be a positive integer")

    raw_sha256 = record.get("sha256", "")
    if not isinstance(raw_sha256, str) or not SHA256_HEX_RE.fullmatch(raw_sha256):
        errors.append(f"review bundle manifest {label}.sha256 must be a lowercase SHA-256 hex digest")
    return errors


def check_manifest_record_keys(
    label: str,
    record: dict[str, Any],
    allowed_keys: set[str],
) -> list[str]:
    errors: list[str] = []
    keys: set[str] = set()
    for key in record:
        if not isinstance(key, str):
            errors.append(f"review bundle manifest {label} fields must be strings, got {key!r}")
            continue
        keys.add(key)
    missing = sorted(allowed_keys - keys)
    unexpected = sorted(keys - allowed_keys)
    if missing:
        errors.append(f"review bundle manifest {label} missing fields: {missing}")
    if unexpected:
        errors.append(f"review bundle manifest {label} has unexpected fields: {unexpected}")
    return errors


def check_candidate_manifest_binding(
    candidate_record: Path,
    candidate: dict[str, Any],
    manifest: dict[str, Any],
) -> list[str]:
    bundle_type = str(manifest.get("bundle_type", ""))
    errors: list[str] = []
    if manifest.get("promotion_config_sha256") != candidate.get("promotion_config_sha256"):
        errors.append("review bundle manifest promotion_config_sha256 must match candidate record")
    if manifest.get("release_asset_urls") != candidate.get("release_asset_urls"):
        errors.append("review bundle manifest release_asset_urls must match candidate record")
    errors.extend(check_manifest_validated_commands(candidate, manifest))
    errors.extend(check_manifest_artifacts_match_candidate(candidate, manifest))
    if bundle_type == "extended-linux-native-evidence":
        target = str(candidate.get("target", ""))
        errors.extend(check_linux_manifest_evidence_file_names(target, manifest))
        errors.extend(
            check_manifest_file_record(
                "candidate_record",
                manifest.get("candidate_record"),
                expected_file=candidate_record_file_name(target),
                expected_sha256=sha256_file(candidate_record),
                expected_size=candidate_record.stat().st_size,
            )
        )
        for key in ("workflow", "workflow_inputs", "workflow_run_url", "release_asset_source", "runner_labels"):
            if manifest.get(key) != candidate.get(key):
                errors.append(f"review bundle manifest {key} must match candidate record")
        candidate_security = candidate.get("builder_identity", {})
        if not isinstance(candidate_security, dict):
            candidate_security = {}
        if manifest.get("security_patch_evidence") != candidate_security.get("security_patch_evidence"):
            errors.append("review bundle manifest security_patch_evidence must match candidate builder_identity")
        errors.extend(
            check_manifest_smoke_hashes_match_candidate(
                candidate,
                manifest,
                candidate_field="linux_smoke_evidence_sha256",
            )
        )
    elif bundle_type == "windows-xp-native-host-evidence":
        errors.extend(
            check_manifest_file_record(
                "candidate_record",
                manifest.get("candidate_record"),
                expected_file=candidate_record_file_name(str(candidate.get("target", ""))),
                expected_sha256=sha256_file(candidate_record),
                expected_size=candidate_record.stat().st_size,
            )
        )
        for key in ("workflow", "workflow_inputs", "release_asset_source", "xp_evidence_sources"):
            if manifest.get(key) != candidate.get(key):
                errors.append(f"review bundle manifest {key} must match candidate record")
        evidence_record = manifest.get("evidence")
        if isinstance(evidence_record, dict):
            if evidence_record.get("file") != "xp-evidence.json":
                errors.append("review bundle manifest evidence.file must be xp-evidence.json")
            if evidence_record.get("sha256") != candidate.get("xp_evidence_sha256"):
                errors.append("review bundle manifest evidence SHA-256 must match candidate xp_evidence_sha256")
        if manifest.get("xp_evidence_contract_sha256") != candidate.get("xp_evidence_contract_sha256"):
            errors.append("review bundle manifest xp_evidence_contract_sha256 must match candidate record")
        candidate_summary = candidate.get("xp_evidence_summary")
        candidate_host_identity = (
            candidate_summary.get("host_identity")
            if isinstance(candidate_summary, dict)
            else None
        )
        candidate_toolchain = (
            candidate_summary.get("toolchain")
            if isinstance(candidate_summary, dict)
            else None
        )
        candidate_security = (
            candidate_summary.get("security")
            if isinstance(candidate_summary, dict)
            else None
        )
        if manifest.get("host_identity") != candidate_host_identity:
            errors.append("review bundle manifest host_identity must match candidate xp_evidence_summary")
        if manifest.get("toolchain") != candidate_toolchain:
            errors.append("review bundle manifest toolchain must match candidate xp_evidence_summary")
        if manifest.get("security") != candidate_security:
            errors.append("review bundle manifest security must match candidate xp_evidence_summary")
        errors.extend(check_manifest_smoke_hashes_match_candidate(candidate, manifest))
    return errors


def check_manifest_validated_commands(candidate: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    raw_commands = manifest.get("validated_commands")
    if not isinstance(raw_commands, list) or not raw_commands:
        return ["review bundle manifest validated_commands must be a non-empty list"]
    commands: list[str] = []
    errors: list[str] = []
    for command in raw_commands:
        text = str(command).strip()
        if not text:
            errors.append("review bundle manifest validated_commands entries must be non-empty strings")
            continue
        if "<" in text or ">" in text:
            errors.append(f"review bundle manifest validated_commands entry must be concrete: {text!r}")
        commands.append(text)

    bundle_type = str(manifest.get("bundle_type", ""))
    if bundle_type == "extended-linux-native-evidence":
        errors.extend(check_manifest_local_evidence_preflight_command(candidate, commands))
        errors.extend(check_manifest_staged_upload_command(candidate, commands))
        expected = [
            str(candidate.get("native_build_command", "")),
            str(candidate.get("native_smoke_command", "")),
            str(candidate.get("artifact_validation_command", "")),
            str(candidate.get("local_evidence_preflight_command", "")),
            str(candidate.get("staged_upload_command", "")),
            "python scripts/check_platform_verified_evidence.py",
        ]
        if commands != expected:
            errors.append("review bundle manifest validated_commands must match Linux candidate command provenance")
    elif bundle_type == "windows-xp-native-host-evidence":
        expected_xp_command = str(candidate.get("native_evidence_validation_command", ""))
        errors.extend(check_manifest_local_evidence_preflight_command(candidate, commands))
        errors.extend(check_manifest_staged_upload_command(candidate, commands))
        xp_commands = [
            command
            for command in commands
            if command.startswith("python scripts/check_xp_native_evidence.py ")
        ]
        if len(xp_commands) != 1:
            errors.append("review bundle manifest validated_commands must include exactly one XP evidence validation command")
        else:
            errors.extend(check_xp_manifest_evidence_validation_command(xp_commands[0]))
        expected = [
            expected_xp_command,
            strict_artifact_validation_command(str(candidate.get("artifact_validation_command", ""))),
            str(candidate.get("local_evidence_preflight_command", "")),
            str(candidate.get("staged_upload_command", "")),
            "python scripts/check_platform_verified_evidence.py",
        ]
        if commands != expected:
            errors.append("review bundle manifest validated_commands must match XP bundle validation commands")
    return errors


def check_manifest_local_evidence_preflight_command(
    candidate: dict[str, Any],
    commands: list[str],
) -> list[str]:
    expected = str(candidate.get("local_evidence_preflight_command", ""))
    matches = [
        command
        for command in commands
        if command.startswith("python scripts/check_platform_goal_local_evidence.py ")
    ]
    if len(matches) != 1:
        return [
            "review bundle manifest validated_commands must include exactly one local evidence preflight command"
        ]
    if matches[0] != expected:
        return [
            "review bundle manifest validated_commands must match candidate local_evidence_preflight_command"
        ]
    return []


def check_manifest_staged_upload_command(
    candidate: dict[str, Any],
    commands: list[str],
) -> list[str]:
    expected = str(candidate.get("staged_upload_command", ""))
    matches = [
        command
        for command in commands
        if command.startswith("python scripts/stage_extended_linux_evidence_upload.py ")
        or command.startswith("python scripts/stage_xp_native_evidence_upload.py ")
    ]
    if len(matches) != 1:
        return [
            "review bundle manifest validated_commands must include exactly one staged upload command"
        ]
    if matches[0] != expected:
        return [
            "review bundle manifest validated_commands must match candidate staged_upload_command"
        ]
    return []


def check_linux_manifest_evidence_file_names(target: str, manifest: dict[str, Any]) -> list[str]:
    errors: list[str] = []
    builder_record = manifest.get("builder_evidence")
    expected_builder = f"builder-identity-{target}.json"
    if isinstance(builder_record, dict) and builder_record.get("file") != expected_builder:
        errors.append(f"review bundle manifest builder_evidence.file must be {expected_builder}")

    smoke_records = manifest.get("smoke_evidence")
    expected_smoke = f"native-smoke-{target}.log"
    if isinstance(smoke_records, list):
        native_records = [
            item
            for item in smoke_records
            if isinstance(item, dict) and item.get("id") == "native_smoke"
        ]
        if len(native_records) == 1 and native_records[0].get("file") != expected_smoke:
            errors.append(f"review bundle manifest native_smoke file must be {expected_smoke}")
    return errors


def check_xp_manifest_evidence_validation_command(command: str) -> list[str]:
    errors: list[str] = []
    evidence_values = re.findall(r"(?:^|\s)--evidence\s+(\S+)(?=\s|$)", command)
    if len(evidence_values) != 1:
        errors.append(
            f"review bundle manifest XP evidence validation command must include exactly one --evidence, got {evidence_values}"
        )
    assets_values = re.findall(r"(?:^|\s)--assets-dir\s+(\S+)(?=\s|$)", command)
    if len(assets_values) != 1:
        errors.append(
            f"review bundle manifest XP evidence validation command must include exactly one --assets-dir, got {assets_values}"
        )
    evidence_dir_values = re.findall(r"(?:^|\s)--evidence-dir\s+(\S+)(?=\s|$)", command)
    for value in [*evidence_values, *assets_values, *evidence_dir_values]:
        if "<" in value or ">" in value:
            errors.append(f"review bundle manifest XP evidence validation command path must be concrete: {value!r}")
    return errors


def strict_artifact_validation_command(command: str) -> str:
    command = command.strip()
    if not command:
        return ""
    if re.search(r"(?:^|\s)--strict(?=\s|$)", command):
        return command
    return f"{command} --strict"


def check_manifest_file_record(
    label: str,
    raw_record: Any,
    *,
    expected_file: str,
    expected_sha256: str,
    expected_size: int,
) -> list[str]:
    if not isinstance(raw_record, dict):
        return [f"review bundle manifest {label} must be an object"]
    errors: list[str] = []
    if raw_record.get("file") != expected_file:
        errors.append(f"review bundle manifest {label}.file must be {expected_file}")
    if raw_record.get("sha256") != expected_sha256:
        errors.append(f"review bundle manifest {label}.sha256 must match {expected_file}")
    raw_size = raw_record.get("size_bytes")
    if not isinstance(raw_size, int) or isinstance(raw_size, bool) or raw_size != expected_size:
        errors.append(f"review bundle manifest {label}.size_bytes must match {expected_file}")
    return errors


def check_manifest_artifacts_match_candidate(candidate: dict[str, Any], manifest: dict[str, Any]) -> list[str]:
    artifact_records = manifest.get("artifacts")
    if not isinstance(artifact_records, list) or not artifact_records:
        return ["review bundle manifest artifacts must be a non-empty list"]
    manifest_hashes: dict[str, str] = {}
    file_counts: dict[str, int] = {}
    errors: list[str] = []
    for record in artifact_records:
        if not isinstance(record, dict):
            errors.append("review bundle manifest artifact entries must be objects")
            continue
        raw_filename = record.get("file", "")
        if not isinstance(raw_filename, str):
            errors.append(
                f"review bundle manifest artifact entry file must be a string, got {raw_filename!r}"
            )
            continue
        filename = raw_filename
        raw_digest = record.get("sha256", "")
        if not isinstance(raw_digest, str):
            errors.append(f"review bundle manifest artifact entry sha256 must be a string, got {raw_digest!r}")
            continue
        digest = raw_digest
        if not filename:
            errors.append("review bundle manifest artifact entry missing file")
            continue
        if not concrete_file_name(filename):
            errors.append(
                f"review bundle manifest artifact file must be an exact safe file name: {filename!r}"
            )
            continue
        file_counts[filename] = file_counts.get(filename, 0) + 1
        manifest_hashes[filename] = digest
    duplicate_files = sorted(filename for filename, count in file_counts.items() if count > 1)
    if duplicate_files:
        errors.append(f"review bundle manifest artifact entries contain duplicate files: {duplicate_files}")
    candidate_hashes = candidate.get("artifact_sha256")
    if not isinstance(candidate_hashes, dict):
        return [*errors, "candidate artifact_sha256 must be an object"]
    candidate_hash_map: dict[str, str] = {}
    for name, digest in candidate_hashes.items():
        if not isinstance(name, str):
            errors.append(f"candidate artifact_sha256 key must be a string, got {name!r}")
            continue
        if not isinstance(digest, str):
            errors.append(f"candidate artifact_sha256 for {name} must be a string SHA-256 hex digest")
            continue
        candidate_hash_map[name] = digest
    if manifest_hashes != candidate_hash_map:
        errors.append("review bundle manifest artifacts must match candidate artifact_sha256")
    return errors


def check_manifest_smoke_hashes_match_candidate(
    candidate: dict[str, Any],
    manifest: dict[str, Any],
    *,
    candidate_field: str = "xp_smoke_evidence_sha256",
) -> list[str]:
    smoke_records = manifest.get("smoke_evidence")
    if not isinstance(smoke_records, list) or not smoke_records:
        return ["review bundle manifest smoke_evidence must be a non-empty list"]
    manifest_hashes: dict[str, str] = {}
    id_counts: dict[str, int] = {}
    errors: list[str] = []
    for record in smoke_records:
        if not isinstance(record, dict):
            errors.append("review bundle manifest smoke_evidence entries must be objects")
            continue
        raw_smoke_id = record.get("id", "")
        if not isinstance(raw_smoke_id, str):
            errors.append(
                f"review bundle manifest smoke_evidence id must be a string, got {raw_smoke_id!r}"
            )
            continue
        smoke_id = raw_smoke_id
        raw_digest = record.get("sha256", "")
        if not isinstance(raw_digest, str):
            errors.append(f"review bundle manifest smoke_evidence sha256 must be a string, got {raw_digest!r}")
            continue
        digest = raw_digest
        if not smoke_id:
            errors.append("review bundle manifest smoke_evidence entry missing id")
            continue
        raw_filename = record.get("file", "")
        if not isinstance(raw_filename, str) or not archive_entry_name_is_safe(raw_filename):
            errors.append(
                "review bundle manifest smoke_evidence file must be a safe relative path, "
                f"got {raw_filename!r}"
            )
        id_counts[smoke_id] = id_counts.get(smoke_id, 0) + 1
        manifest_hashes[smoke_id] = digest
    duplicate_ids = sorted(smoke_id for smoke_id, count in id_counts.items() if count > 1)
    if duplicate_ids:
        errors.append(f"review bundle manifest smoke_evidence entries contain duplicate ids: {duplicate_ids}")
    candidate_hashes = candidate.get(candidate_field)
    if not isinstance(candidate_hashes, dict):
        return [*errors, f"candidate {candidate_field} must be an object"]
    candidate_hash_map: dict[str, str] = {}
    for name, digest in candidate_hashes.items():
        if not isinstance(name, str):
            errors.append(f"candidate {candidate_field} key must be a string, got {name!r}")
            continue
        if not isinstance(digest, str):
            errors.append(f"candidate {candidate_field} for {name} must be a string SHA-256 hex digest")
            continue
        candidate_hash_map[name] = digest
    if manifest_hashes != candidate_hash_map:
        errors.append(f"review bundle manifest smoke_evidence must match candidate {candidate_field}")
    return errors


def check_bundle_sidecar(sidecar: object, manifest: object, archive: object) -> list[str]:
    sidecar_errors, sidecar_path = path_arg_value(sidecar, "review bundle SHA-256 sidecar")
    manifest_errors, manifest_path = path_arg_value(manifest, "review bundle manifest")
    archive_errors, archive_path = path_arg_value(archive, "review bundle archive")
    errors = sidecar_errors + manifest_errors + archive_errors
    if errors:
        return errors
    assert sidecar_path is not None
    assert manifest_path is not None
    assert archive_path is not None
    if not sidecar_path.is_file():
        return []
    try:
        lines = [line.strip() for line in sidecar_path.read_text(encoding="utf-8").splitlines() if line.strip()]
    except (OSError, UnicodeDecodeError) as exc:
        return [f"review bundle SHA-256 sidecar is not readable UTF-8: {exc}"]
    expected = {
        f"{sha256_file(manifest_path)}  {manifest_path.name}",
        f"{sha256_file(archive_path)}  {archive_path.name}",
    }
    line_set = set(lines)
    missing = sorted(expected - line_set)
    unexpected = sorted(line_set - expected)
    counts: dict[str, int] = {}
    for line in lines:
        counts[line] = counts.get(line, 0) + 1
    duplicates = sorted(line for line, count in counts.items() if count > 1)
    errors: list[str] = []
    if missing:
        errors.append(f"review bundle SHA-256 sidecar missing entries: {missing}")
    if unexpected:
        errors.append(f"review bundle SHA-256 sidecar contains unexpected entries: {unexpected}")
    if duplicates:
        errors.append(f"review bundle SHA-256 sidecar contains duplicate entries: {duplicates}")
    return errors


def check_bundle_archive(
    archive_path: Path,
    manifest_path: Path,
    manifest: dict[str, Any],
    candidate: dict[str, Any],
) -> list[str]:
    if not archive_path.is_file():
        return []
    try:
        with zipfile.ZipFile(archive_path) as archive:
            all_infos = archive.infolist()
            archive_safety_errors = check_archive_entry_safety(all_infos)
            if archive_safety_errors:
                return archive_safety_errors
            infos = [item for item in all_infos if not item.is_dir()]
            entry_counts: dict[str, int] = {}
            for item in infos:
                entry_counts[item.filename] = entry_counts.get(item.filename, 0) + 1
            entries = {item.filename: item for item in infos}
            errors = []
            duplicate_entries = sorted(name for name, count in entry_counts.items() if count > 1)
            if duplicate_entries:
                errors.append(f"review bundle archive contains duplicate entries: {duplicate_entries}")
            errors.extend(check_archive_expected_entries(entries, manifest_path, manifest))
            if errors:
                return errors
            errors.extend(check_archive_record_hashes(archive, manifest_path, manifest))
            errors.extend(check_archive_payloads_match_candidate(archive, manifest, candidate))
            return errors
    except (OSError, zipfile.BadZipFile) as exc:
        return [f"review bundle archive is not a readable ZIP: {archive_path.name}: {exc}"]


def check_archive_entry_safety(infos: list[zipfile.ZipInfo]) -> list[str]:
    directory_entries: list[str] = []
    encrypted_entries: list[str] = []
    symlink_entries: list[str] = []
    non_regular_entries: list[str] = []
    unexpected_permission_entries: list[str] = []
    unsafe_entries: list[str] = []
    for info in infos:
        name = info.filename
        if info.is_dir():
            directory_entries.append(name)
        if archive_entry_is_encrypted(info):
            encrypted_entries.append(name)
        if archive_entry_is_symlink(info):
            symlink_entries.append(name)
        if archive_entry_declares_non_regular_file(info):
            non_regular_entries.append(name)
        if archive_entry_declares_unexpected_regular_file_permissions(info):
            unexpected_permission_entries.append(name)
        if not archive_entry_name_is_safe(name):
            unsafe_entries.append(name)
    errors: list[str] = []
    if directory_entries:
        errors.append(f"review bundle archive entries must be regular files only: {sorted(directory_entries)}")
    if encrypted_entries:
        errors.append(f"review bundle archive entries must not be encrypted: {sorted(encrypted_entries)}")
    if symlink_entries:
        errors.append(f"review bundle archive entries must not be symlinks: {sorted(symlink_entries)}")
    if non_regular_entries:
        errors.append(
            f"review bundle archive entries must be regular files: {sorted(non_regular_entries)}"
        )
    if unexpected_permission_entries:
        errors.append(
            "review bundle archive regular file entries must use 0644 permissions: "
            f"{sorted(unexpected_permission_entries)}"
        )
    if unsafe_entries:
        errors.append(f"review bundle archive entries must use safe relative paths: {sorted(unsafe_entries)}")
    errors.extend(check_archive_entry_name_ambiguity(info.filename for info in infos if not info.is_dir()))
    return errors


def archive_entry_is_encrypted(info: zipfile.ZipInfo) -> bool:
    return bool(info.flag_bits & 0x1)


def archive_entry_is_symlink(info: zipfile.ZipInfo) -> bool:
    file_type = (info.external_attr >> 16) & 0o170000
    return file_type == 0o120000


def archive_entry_declares_non_regular_file(info: zipfile.ZipInfo) -> bool:
    file_type = (info.external_attr >> 16) & 0o170000
    if file_type == 0:
        return False
    if info.is_dir():
        return False
    return file_type != 0o100000


def archive_entry_declares_unexpected_regular_file_permissions(info: zipfile.ZipInfo) -> bool:
    unix_mode = (info.external_attr >> 16) & 0o177777
    file_type = unix_mode & 0o170000
    if file_type != 0o100000:
        return False
    permissions = unix_mode & 0o7777
    return permissions != 0o644


def check_archive_entry_name_ambiguity(entry_names: Any) -> list[str]:
    names = [str(name).rstrip("/") for name in entry_names if str(name).rstrip("/")]
    errors: list[str] = []
    case_groups: dict[str, set[str]] = {}
    for name in names:
        case_groups.setdefault(name.casefold(), set()).add(name)
    case_collisions = sorted(
        {
            name
            for group in case_groups.values()
            if len(group) > 1
            for name in group
        }
    )
    if case_collisions:
        errors.append(
            f"review bundle archive entries must not collide on case-insensitive filesystems: {case_collisions}"
        )
    unique_names = sorted(set(names))
    path_prefix_collisions = sorted(
        f"{parent} -> {child}"
        for parent in unique_names
        for child in unique_names
        if parent != child and child.startswith(f"{parent}/")
    )
    if path_prefix_collisions:
        errors.append(
            f"review bundle archive entries must not contain file/path-prefix collisions: "
            f"{path_prefix_collisions}"
        )
    return errors


def archive_entry_name_is_safe(name: str) -> bool:
    if not name or "\\" in name:
        return False
    parts = name.split("/")
    if any(part in ("", ".", "..") for part in parts):
        return False
    posix_path = PurePosixPath(name)
    windows_path = PureWindowsPath(name)
    return not posix_path.is_absolute() and not windows_path.is_absolute() and not windows_path.drive


def check_archive_expected_entries(
    entries: dict[str, zipfile.ZipInfo],
    manifest_path: Path,
    manifest: dict[str, Any],
) -> list[str]:
    expected = expected_archive_records(manifest_path, manifest)
    expected_counts: dict[str, int] = {}
    for name, _record in expected:
        expected_counts[name] = expected_counts.get(name, 0) + 1
    expected_names = set(expected_counts)
    actual_names = set(entries)
    missing = sorted(expected_names - actual_names)
    extra = sorted(actual_names - expected_names)
    errors: list[str] = []
    duplicate_expected = sorted(name for name, count in expected_counts.items() if count > 1)
    if duplicate_expected:
        errors.append(f"review bundle manifest references duplicate bundle entries: {duplicate_expected}")
    if missing:
        errors.append(f"review bundle archive missing expected entries: {missing}")
    if extra:
        errors.append(f"review bundle archive contains unexpected entries: {extra}")
    return errors


def check_archive_record_hashes(
    archive: zipfile.ZipFile,
    manifest_path: Path,
    manifest: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    for name, record in expected_archive_records(manifest_path, manifest):
        data = read_archive_entry_bytes(
            archive,
            name,
            errors,
            label="entry",
        )
        if data is None:
            continue
        expected_size = record.get("size_bytes")
        if not isinstance(expected_size, int) or isinstance(expected_size, bool) or expected_size <= 0:
            errors.append(f"review bundle manifest record {name} size_bytes must be positive")
        elif len(data) != expected_size:
            errors.append(f"review bundle archive entry size mismatch: {name}")
        expected_sha = record.get("sha256", "")
        if not isinstance(expected_sha, str) or not SHA256_HEX_RE.fullmatch(expected_sha):
            errors.append(
                f"review bundle manifest record {name} sha256 must be a lowercase SHA-256 hex digest"
            )
        elif sha256_bytes(data) != expected_sha:
            errors.append(f"review bundle archive entry SHA-256 mismatch: {name}")
    return errors


def check_archive_payloads_match_candidate(
    archive: zipfile.ZipFile,
    manifest: dict[str, Any],
    candidate: dict[str, Any],
) -> list[str]:
    errors: list[str] = []
    bundle_type = str(manifest.get("bundle_type", ""))
    if bundle_type == "extended-linux-native-evidence":
        archived_candidate = read_archive_json_record(archive, manifest.get("candidate_record"), "candidate_record", errors)
        if archived_candidate is not None and archived_candidate != candidate:
            errors.append("review bundle archive candidate_record must match candidate evidence record")
        archived_builder = read_archive_json_record(archive, manifest.get("builder_evidence"), "builder_evidence", errors)
        if archived_builder is not None and archived_builder != candidate.get("builder_identity"):
            errors.append("review bundle archive builder_evidence must match candidate builder_identity")
        errors.extend(check_linux_archive_smoke_log(archive, manifest, candidate))
    elif bundle_type == "windows-xp-native-host-evidence":
        archived_candidate = read_archive_json_record(archive, manifest.get("candidate_record"), "candidate_record", errors)
        if archived_candidate is not None and archived_candidate != candidate:
            errors.append("review bundle archive candidate_record must match candidate evidence record")
        archived_evidence = read_archive_json_record(archive, manifest.get("evidence"), "evidence", errors)
        if archived_evidence is not None:
            target = str(candidate.get("target", ""))
            release_tag = str(candidate.get("release_tag", ""))
            if xp_evidence_summary(target, release_tag, archived_evidence) != candidate.get("xp_evidence_summary"):
                errors.append("review bundle archive XP evidence summary must match candidate xp_evidence_summary")
            if xp_smoke_evidence_sha256_map(archived_evidence) != candidate.get("xp_smoke_evidence_sha256"):
                errors.append(
                    "review bundle archive XP smoke evidence hashes must match candidate xp_smoke_evidence_sha256"
                )
            errors.extend(check_xp_archive_smoke_manifest_matches_evidence(archived_evidence, manifest))
            errors.extend(check_xp_archive_smoke_files(archive, archived_evidence))
    return errors


def check_linux_archive_smoke_log(
    archive: zipfile.ZipFile,
    manifest: dict[str, Any],
    candidate: dict[str, Any],
) -> list[str]:
    smoke_records = manifest.get("smoke_evidence")
    if not isinstance(smoke_records, list):
        return []
    record = next(
        (item for item in smoke_records if isinstance(item, dict) and item.get("id") == "native_smoke"),
        None,
    )
    if not isinstance(record, dict):
        return ["review bundle manifest smoke_evidence must include native_smoke"]
    raw_filename = record.get("file")
    if not isinstance(raw_filename, str) or not raw_filename:
        return ["review bundle manifest native_smoke file must be set"]
    filename = raw_filename
    read_errors: list[str] = []
    data = read_archive_entry_bytes(
        archive,
        filename,
        read_errors,
        label="native_smoke evidence",
        missing_error=f"review bundle archive missing native_smoke evidence: {filename}",
    )
    if data is None:
        return read_errors
    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        return [f"review bundle archive native_smoke evidence is not UTF-8: {exc}"]
    source = candidate.get("release_asset_source")
    target = str(candidate.get("target", ""))
    if not isinstance(source, dict):
        return ["candidate release_asset_source must be an object for archived native_smoke evidence"]
    raw_source_head_sha = source.get("head_sha")
    if not isinstance(raw_source_head_sha, str) or not GIT_SHA_RE.fullmatch(raw_source_head_sha.strip()):
        return [
            "candidate release_asset_source.head_sha must be a 40-character "
            "lowercase Git SHA for archived native_smoke evidence"
        ]
    source_head_sha = raw_source_head_sha.strip()
    source_run_attempt = source.get("run_attempt") if isinstance(source, dict) else 0
    errors = check_linux_smoke_log_text(
        target,
        str(candidate.get("release_tag", "")),
        str(candidate.get("native_smoke_command", "")),
        str(candidate.get("workflow_run_url", "")),
        text,
        workflow_run_attempt=(
            source_run_attempt if isinstance(source_run_attempt, int) and not isinstance(source_run_attempt, bool) else 0
        ),
        source_head_sha=source_head_sha,
        label="archived native_smoke evidence",
        artifact_sha256=candidate.get("artifact_sha256"),
    )
    errors.extend(
        check_linux_smoke_builder_identity_binding(
            target,
            "archived native_smoke evidence",
            text,
            candidate.get("builder_identity"),
        )
    )
    return errors


def check_xp_archive_smoke_manifest_matches_evidence(
    archived_evidence: dict[str, Any],
    manifest: dict[str, Any],
) -> list[str]:
    smoke_results = archived_evidence.get("smoke_results")
    smoke_manifest = manifest.get("smoke_evidence")
    if not isinstance(smoke_results, list) or not isinstance(smoke_manifest, list):
        return []
    errors: list[str] = []
    evidence_files: dict[str, str] = {}
    for item in smoke_results:
        if not isinstance(item, dict):
            continue
        smoke_id = item.get("id")
        if not isinstance(smoke_id, str) or not smoke_id:
            errors.append(
                f"review bundle archive XP smoke result id must be a non-empty string, got {smoke_id!r}"
            )
            continue
        evidence_file = item.get("evidence_file")
        if not isinstance(evidence_file, str) or not evidence_file:
            errors.append(
                f"review bundle archive XP smoke result {smoke_id} "
                f"evidence_file must be a non-empty string, got {evidence_file!r}"
            )
            continue
        evidence_files[smoke_id] = evidence_file
    manifest_files: dict[str, str] = {}
    for item in smoke_manifest:
        if not isinstance(item, dict):
            continue
        smoke_id = item.get("id")
        if not isinstance(smoke_id, str) or not smoke_id:
            errors.append(
                f"review bundle manifest smoke_evidence id must be a non-empty string, got {smoke_id!r}"
            )
            continue
        smoke_file = item.get("file")
        if not isinstance(smoke_file, str) or not smoke_file:
            errors.append(
                f"review bundle manifest smoke_evidence {smoke_id} "
                f"file must be a non-empty string, got {smoke_file!r}"
            )
            continue
        manifest_files[smoke_id] = smoke_file
    if errors:
        return errors
    if evidence_files != manifest_files:
        return ["review bundle manifest smoke_evidence files must match archived XP evidence smoke_results"]
    return []


def check_xp_archive_smoke_files(
    archive: zipfile.ZipFile,
    archived_evidence: dict[str, Any],
) -> list[str]:
    target = str(archived_evidence.get("target", ""))
    release_tag = str(archived_evidence.get("release_tag", ""))
    host_identity = archived_evidence.get("host_identity")
    os_identity = archived_evidence.get("os")
    release_source = archived_evidence.get("release_source")
    smoke_results = archived_evidence.get("smoke_results")
    if not isinstance(smoke_results, list):
        return ["review bundle archive XP evidence smoke_results must be a list"]
    errors: list[str] = []
    for result in smoke_results:
        if not isinstance(result, dict):
            errors.append("review bundle archive XP evidence smoke_results entries must be objects")
            continue
        raw_smoke_id = result.get("id")
        if not isinstance(raw_smoke_id, str) or not raw_smoke_id:
            errors.append(
                f"review bundle archive XP smoke result id must be a non-empty string, got {raw_smoke_id!r}"
            )
            continue
        smoke_id = raw_smoke_id
        raw_filename = result.get("evidence_file")
        if not isinstance(raw_filename, str) or not raw_filename:
            errors.append(
                f"review bundle archive XP smoke result {smoke_id} "
                f"evidence_file must be a non-empty string, got {raw_filename!r}"
            )
            continue
        filename = raw_filename
        if not archive_entry_name_is_safe(filename):
            errors.append(
                f"review bundle archive XP smoke result {smoke_id} "
                f"evidence_file must be a safe relative archive path, got {filename!r}"
            )
            continue
        data = read_archive_entry_bytes(
            archive,
            filename,
            errors,
            label="XP smoke evidence file",
            missing_error=f"review bundle archive missing XP smoke evidence file: {filename}",
        )
        if data is None:
            continue
        expected_sha = result.get("evidence_sha256", "")
        if not isinstance(expected_sha, str) or not SHA256_HEX_RE.fullmatch(expected_sha):
            errors.append(
                f"review bundle archive XP smoke result {smoke_id} "
                "evidence_sha256 must be a lowercase SHA-256 hex digest"
            )
        elif sha256_bytes(data) != expected_sha:
            errors.append(f"review bundle archive XP smoke evidence SHA-256 mismatch: {filename}")
        errors.extend(
            check_smoke_evidence_binding(
                target,
                release_tag,
                smoke_id,
                data,
                host_identity=host_identity,
                os_identity=os_identity,
                release_source=release_source,
            )
        )
        errors.extend(
            check_security_smoke_evidence_lines(
                target,
                smoke_id,
                data,
                read_json(ROOT / "configs" / "xp_native_evidence_contract.json"),
                security=archived_evidence.get("security"),
            )
        )
    return errors


def read_archive_json_record(
    archive: zipfile.ZipFile,
    raw_record: Any,
    label: str,
    errors: list[str],
) -> dict[str, Any] | None:
    if not isinstance(raw_record, dict):
        return None
    filename = str(raw_record.get("file", ""))
    if not filename:
        return None
    data = read_archive_entry_bytes(
        archive,
        filename,
        errors,
        label=label,
    )
    if data is None:
        return None
    try:
        parsed = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"review bundle archive {label} is not UTF-8 JSON: {exc}")
        return None
    if not isinstance(parsed, dict):
        errors.append(f"review bundle archive {label} must contain a JSON object")
        return None
    return parsed


def read_archive_entry_bytes(
    archive: zipfile.ZipFile,
    filename: str,
    errors: list[str],
    *,
    label: str,
    missing_error: str | None = None,
) -> bytes | None:
    try:
        return archive.read(filename)
    except KeyError:
        if missing_error:
            errors.append(missing_error)
        return None
    except (RuntimeError, NotImplementedError, OSError, zipfile.BadZipFile) as exc:
        errors.append(f"review bundle archive {label} is not readable: {filename}: {exc}")
        return None


def expected_archive_records(manifest_path: Path, manifest: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    records: list[tuple[str, dict[str, Any]]] = [(manifest_path.name, file_record(manifest_path))]
    bundle_type = str(manifest.get("bundle_type", ""))
    if bundle_type == "extended-linux-native-evidence":
        for key in ("builder_evidence", "candidate_record"):
            append_manifest_record(records, manifest.get(key))
        for item in manifest.get("smoke_evidence", []):
            append_manifest_record(records, item)
        for item in manifest.get("artifacts", []):
            append_manifest_record(records, item)
    elif bundle_type == "windows-xp-native-host-evidence":
        append_manifest_record(records, manifest.get("candidate_record"))
        append_manifest_record(records, manifest.get("evidence"))
        for item in manifest.get("smoke_evidence", []):
            append_manifest_record(records, item)
        for item in manifest.get("artifacts", []):
            append_manifest_record(records, item)
    return records


def append_manifest_record(records: list[tuple[str, dict[str, Any]]], raw_record: Any) -> None:
    if not isinstance(raw_record, dict):
        return
    filename = str(raw_record.get("file", ""))
    if filename:
        records.append((filename, raw_record))


def file_record(path: Path) -> dict[str, Any]:
    return {
        "file": path.name,
        "size_bytes": path.stat().st_size,
        "sha256": sha256_file(path),
    }


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def platform_evidence_policy() -> str:
    registry = read_json(ROOT / "configs" / "platform_verified_evidence.json")
    return str(registry.get("policy", ""))


def load_json(path: object, label: str, errors: list[str]) -> dict[str, Any] | None:
    path_errors, path_value = path_arg_value(path, f"{label} file")
    if path_errors:
        errors.extend(path_errors)
        return None
    assert path_value is not None
    if not check_input_file(path_value, label, errors):
        return None
    try:
        data = json.loads(path_value.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        errors.append(f"{label} file is not readable JSON: {path_value}: {exc}")
        return None
    if not isinstance(data, dict):
        errors.append(f"{label} file must contain a JSON object")
        return None
    return data


def check_input_file(path: object, label: str, errors: list[str]) -> bool:
    path_errors, path_value = path_arg_value(path, f"{label} file")
    if path_errors:
        errors.extend(path_errors)
        return False
    assert path_value is not None
    reserved_errors = check_path_not_reserved_workspace_root(path_value, f"{label} file")
    if reserved_errors:
        errors.extend(reserved_errors)
        return False
    if path_value.is_symlink():
        errors.append(f"{label} file must not be a symlink: {path_value}")
        return False
    parent_errors = check_path_parent_symlinks(path_value, f"{label} file")
    if parent_errors:
        errors.extend(parent_errors)
        return False
    if not path_value.is_file():
        errors.append(f"{label} file missing: {path_value}")
        return False
    return True


def check_text_output_path(path: object, label: str) -> list[str]:
    path_errors, path_value = path_arg_value(path, label)
    if path_errors:
        return path_errors
    assert path_value is not None
    reserved_errors = check_path_not_reserved_workspace_root(path_value, label)
    if reserved_errors:
        return reserved_errors
    return check_base_text_output_path(path_value, label)


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


def check_candidate_record_file_name(candidate_record: object, target: str) -> list[str]:
    path_errors, candidate_path = path_arg_value(candidate_record, "candidate evidence record")
    if path_errors:
        return path_errors
    assert candidate_path is not None
    expected_name = candidate_record_file_name(target)
    if candidate_path.name == expected_name:
        return []
    return [
        f"candidate evidence record file name must be {expected_name}, "
        f"got {candidate_path.name!r}"
    ]


def candidate_record_file_name(target: str) -> str:
    return f"platform-verified-evidence-{target}.json"


def check_finalized_record_output_path(
    path: object,
    record: dict[str, Any],
    *,
    bundle_manifest: object | None = None,
) -> list[str]:
    path_errors, path_value = path_arg_value(path, "finalized platform evidence record output file")
    if path_errors:
        return path_errors
    assert path_value is not None
    manifest_path: Path | None = None
    if bundle_manifest is not None:
        manifest_errors, manifest_path = path_arg_value(bundle_manifest, "review bundle manifest")
        if manifest_errors:
            return manifest_errors
    target = str(record.get("target", ""))
    expected_name = accepted_record_source_file(target)
    errors: list[str] = []
    if path_value.name != expected_name:
        errors.append(
            f"finalized platform evidence record output file name must be {expected_name}, "
            f"got {path_value.name!r}"
        )
    errors.extend(check_text_output_path(path_value, "finalized platform evidence record output file"))
    if manifest_path is not None:
        output_parent = normalized_parent(path_value)
        bundle_parent = normalized_parent(manifest_path)
        if output_parent != bundle_parent:
            errors.append(
                "finalized platform evidence record output file must be written next to review bundle files: "
                f"output={output_parent}, review_bundle={bundle_parent}"
            )
    return errors


def check_finalized_record_output_bytes(path: object, expected_text: str) -> list[str]:
    path_errors, path_value = path_arg_value(path, "finalized platform evidence record output file")
    if path_errors:
        return path_errors
    assert path_value is not None
    errors = check_text_output_path(path_value, "finalized platform evidence record output file")
    if errors:
        return errors
    if not path_value.is_file():
        return [f"finalized platform evidence record output file missing after write: {path_value}"]
    try:
        actual = path_value.read_bytes()
    except OSError as exc:
        return [f"finalized platform evidence record output file is not readable after write: {path_value}: {exc}"]
    expected = expected_text.encode("utf-8")
    if actual != expected:
        return [
            "finalized platform evidence record output file bytes must match canonical record JSON "
            f"before registry append: {path_value}"
        ]
    return []


def check_review_bundle_input_siblings(
    manifest: object,
    archive: object,
    sidecar: object,
) -> list[str]:
    manifest_errors, manifest_path = path_arg_value(manifest, "review bundle manifest")
    archive_errors, archive_path = path_arg_value(archive, "review bundle archive")
    sidecar_errors, sidecar_path = path_arg_value(sidecar, "review bundle SHA-256 sidecar")
    errors = manifest_errors + archive_errors + sidecar_errors
    if errors:
        return errors
    assert manifest_path is not None
    assert archive_path is not None
    assert sidecar_path is not None
    parents = {
        "manifest": normalized_parent(manifest_path),
        "archive": normalized_parent(archive_path),
        "sha256s": normalized_parent(sidecar_path),
    }
    if len(set(parents.values())) == 1:
        return []
    return [
        "review bundle files must be siblings in one directory: "
        f"manifest={parents['manifest']}, archive={parents['archive']}, sha256s={parents['sha256s']}"
    ]


def normalized_parent(path: Path) -> Path:
    check_path = path if path.is_absolute() else Path.cwd() / path
    return check_path.parent.resolve()


if __name__ == "__main__":
    raise SystemExit(main())

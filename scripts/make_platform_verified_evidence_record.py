from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from check_platform_promotion_artifacts import (  # noqa: E402
    archive_entry_name_is_safe,
    check_platform_promotion_artifacts,
    required_artifacts,
    version_from_tag,
)
from check_platform_promotion_artifacts import (  # noqa: E402
    read_json as read_promotion_json,
)
from check_platform_verified_evidence import (  # noqa: E402
    LINUX_TARGETS,
    RESERVED_WORKSPACE_ROOTS,
    XP_TARGETS,
    check_linux_smoke_builder_identity_binding,
    check_linux_smoke_log_text,
    check_platform_verified_evidence,
    directory_path_has_file_suffix,
    json_sha256,
    linux_release_source_artifact_name,
    linux_smoke_line_values,
    promotion_config_sha256,
    release_source_workflow,
    xp_native_evidence_contract_sha256,
    xp_release_source_artifact_name,
)
from check_xp_native_evidence import (  # noqa: E402
    artifact_validation_asset_dirs,
    check_xp_native_evidence,
)

PROMOTION_PATH = ROOT / "configs" / "platform_parity_promotion.json"
EVIDENCE_PATH = ROOT / "configs" / "platform_verified_evidence.json"
DEFAULT_EVIDENCE_POLICY = (
    "Only accepted evidence records in this file can promote Linux i386, Linux armhf, "
    "or Windows XP native-host readiness. Accepted records must include release asset URLs, "
    "review-bundle manifest release asset URL binding, review bundle release asset URLs, "
    "release-importable artifact source binding, "
    "source artifact repository-id binding from exact source-run metadata, "
    "source artifact run-created timestamp binding from exact source-run metadata, "
    "source artifact run-start timestamp binding from exact source-run metadata, "
    "source artifact run-window timestamp binding from exact source-run metadata, "
    "source artifact retention expiration binding from exact source artifact metadata, "
    "release source head SHA binding, "
    "release source run-attempt binding, "
    "same release source workflow run URL cannot carry conflicting run attempts, "
    "release source workflow file binding, "
    "local protected-goal evidence preflight command binding, "
    "source artifact staged upload command binding, "
    "staged upload source/evidence/output root separation, "
    "finalized accepted-record source file binding, "
    "finalized accepted-record release asset URL binding, "
    "canonical finalized accepted-record JSON byte binding, "
    "published native and review-bundle release asset byte binding, "
    "published release asset GitHub id/API URL binding, "
    "Linux release source artifact names must be target/release-scoped, "
    "Linux accepted evidence command paths must be target/release-scoped, "
    "XP release source artifact names must be target/release-scoped, "
    "XP accepted evidence command paths must be target/release-scoped, "
    "per-artifact SHA-256 digests, safe relative non-link native archive entries, "
    "exact safe checksum and native manifest file references, "
    "target architecture/format manifest binding, exact safe release asset URL filenames, "
    "exact required check lists, exact workflow dispatch input sets, "
    "workflow dispatch release repository binding, exact evidence source record fields, "
    "exact release source and review bundle fields, "
    "Linux builder identity evidence, builder identity SHA-256, "
    "builder identity release/run binding, "
    "Linux builder workflow provenance binding, "
    "exact Linux builder identity fields, "
    "Linux builder/smoke source file binding, "
    "Linux builder/smoke host identity binding, Linux builder/smoke security evidence binding, "
    "Linux builder source head SHA binding, "
    "Linux builder observed Git HEAD binding, Linux builder clean checkout binding, "
    "Linux builder/smoke runtime OS identity binding, "
    "Linux builder host identity binding when applicable, "
    "Linux builder rpm and non-interactive sudo evidence, "
    "Linux security patch evidence, Linux security smoke proof-line binding, "
    "exact Linux smoke proof-line occurrence binding, "
    "case-insensitive Linux forbidden security proof-line rejection, "
    "Linux native smoke summary binding, "
    "Linux native build and smoke command provenance, "
    "Linux smoke evidence SHA-256, Linux smoke release/run/source head SHA binding, "
    "Linux smoke runtime architecture and userland binding, "
    "Linux smoke sanitized host identity and observed-at timestamp binding, "
    "Linux workflow dispatch inputs when applicable, XP workflow dispatch inputs when applicable, "
    "XP evidence source file binding, XP evidence release source binding, "
    "XP evidence bundle SHA-256 digests, "
    "XP evidence validation command binding, XP evidence contract SHA-256, "
    "XP evidence summary binding, exact XP evidence summary fields, XP host identity SHA-256 binding, "
    "XP sanitized target-scoped host identity binding, XP smoke host identity binding, "
    "XP smoke observed-at timestamp binding, XP smoke OS identity binding, "
    "XP smoke host probe proof-line binding, "
    "exact XP smoke proof-line occurrence binding, "
    "case-insensitive XP forbidden security proof-line rejection, "
    "XP security patch evidence, "
    "tracked scripts/xp_smoke_runner.cmd XP smoke command provenance, "
    "canonical XP smoke proof-file command binding, "
    "XP security smoke command provenance binding when applicable, "
    "canonical XP smoke evidence-file summary binding and "
    "XP security smoke proof-line binding when applicable, review bundle manifest, "
    "review bundle archive, safe relative non-symlink review bundle archive entries, and review bundle SHA-256 "
    "sidecar digests before strict promotion, and release uploads must include those review bundle "
    "files with matching size, SHA-256 and checksum-sidecar coverage plus canonical finalized "
    "accepted-record JSON with matching size and SHA-256; each accepted record must include the promotion "
    "config SHA-256, have a unique "
    "target, include no unrecognized top-level fields, "
    "all release evidence for one record must use the same GitHub repository, protected platform "
    "goal records for one release must use one release source head SHA and target-specific release source "
    "workflow files plus positive release source run attempts, "
    "partial protected platform goal records must use one release_tag, GitHub repository, "
    "target-specific release source workflow file, release source head SHA "
    "and positive release source run attempt before promotion, and Windows XP x86/x64 pairs must use the same release_tag, "
    "GitHub repository, target-specific release source workflow file, release source head SHA and positive "
    "release source run attempts. Empty means no promotion."
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
GITHUB_HEAD_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
GITHUB_OWNER_RE = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?"
GITHUB_REPOSITORY_RE = rf"{GITHUB_OWNER_RE}/[A-Za-z0-9._-]+"
GITHUB_RELEASE_BASE_RE = re.compile(
    rf"^https://github\.com/({GITHUB_REPOSITORY_RE})/releases/download/(v\d+\.\d+\.\d+)$"
)
GITHUB_ACTIONS_RUN_RE = re.compile(rf"^https://github\.com/({GITHUB_REPOSITORY_RE})/actions/runs/\d+$")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    errors, record = build_evidence_record(args)
    if errors:
        for error in errors:
            print(f"platform verified evidence record: {error}", file=sys.stderr)
        return 1
    output = json.dumps(record, indent=2) + "\n"
    if args.out:
        output_errors = check_generated_record_output_path(args.out, record)
        if output_errors:
            for error in output_errors:
                print(f"platform verified evidence record: {error}", file=sys.stderr)
            return 1
    if args.append_registry:
        append_usage_errors = check_generator_append_registry_usage(record)
        if append_usage_errors:
            for error in append_usage_errors:
                print(f"platform verified evidence record: {error}", file=sys.stderr)
            return 1
        registry_errors = append_record_to_registry(record, registry_path=args.registry)
        if registry_errors:
            for error in registry_errors:
                print(f"platform verified evidence record: {error}", file=sys.stderr)
            return 1
        if args.out:
            write_text_output(args.out, output)
        print(f"platform verified evidence record appended to {args.registry}")
        return 0
    if args.out:
        write_text_output(args.out, output)
    else:
        print(output, end="")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a validated accepted-evidence record for platform readiness promotion."
    )
    parser.add_argument("--target", choices=sorted({*LINUX_TARGETS, *XP_TARGETS}), required=True)
    parser.add_argument("--release-tag", required=True, help="Release tag, for example v1.0.5")
    parser.add_argument("--assets-dir", type=Path, required=True, help="Directory with built native artifacts")
    parser.add_argument(
        "--release-asset-base-url",
        required=True,
        help="Exact GitHub release download base URL: https://github.com/<owner>/<repo>/releases/download/vX.Y.Z",
    )
    parser.add_argument("--workflow-run-url", help="GitHub Actions run URL for Linux evidence")
    parser.add_argument(
        "--release-source-workflow-run-url",
        help=(
            "GitHub Actions run URL for the artifact that the tagged release workflow can download. "
            "Defaults to --workflow-run-url for Linux evidence."
        ),
    )
    parser.add_argument(
        "--release-source-artifact-name",
        help=(
            "GitHub Actions artifact name containing the accepted release files. Defaults to the "
            "target/release-scoped extended Linux evidence artifact for Linux evidence; required for XP evidence."
        ),
    )
    parser.add_argument(
        "--release-source-head-sha",
        help="40-character Git commit SHA for the source workflow run that produced the release files.",
    )
    parser.add_argument(
        "--release-source-run-attempt",
        type=int,
        help="Positive GitHub Actions run attempt for the source workflow artifact.",
    )
    parser.add_argument("--runner-label", action="append", default=[], help="Runner label for Linux evidence")
    parser.add_argument("--builder-evidence", type=Path, help="Linux builder identity JSON emitted by builder preflight")
    parser.add_argument("--linux-smoke-evidence", type=Path, help="Linux native smoke log captured from the builder")
    parser.add_argument(
        "--local-evidence-root",
        type=Path,
        default=Path("."),
        help=(
            "staging root used by the local protected-goal evidence preflight; "
            "defaults to the workspace root"
        ),
    )
    parser.add_argument(
        "--staged-upload-out-dir",
        type=Path,
        help=(
            "directory populated by the staged release-upload command; defaults to "
            "platform-evidence-upload/<target>/<release-tag>"
        ),
    )
    parser.add_argument("--xp-evidence", type=Path, help="Windows XP native evidence JSON for XP targets")
    parser.add_argument(
        "--xp-evidence-dir",
        type=Path,
        help="directory containing smoke evidence files referenced by --xp-evidence",
    )
    parser.add_argument(
        "--xp-evidence-output-dir",
        type=Path,
        help=(
            "XP finalized evidence bundle directory used by staged upload; defaults to "
            "xp-evidence-output/<target>/<release-tag>"
        ),
    )
    parser.add_argument(
        "--append-registry",
        action="store_true",
        help=(
            "deprecated guardrail: generated candidates are not final records; use "
            "scripts/finalize_platform_verified_evidence_record.py --append-registry"
        ),
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

    promotion = read_promotion_json(PROMOTION_PATH)
    artifact_errors = check_platform_promotion_artifacts(
        target=target,
        assets_dir=args.assets_dir,
        tag=args.release_tag,
        strict=True,
    )
    errors.extend(artifact_errors)
    artifact_hashes = (
        artifact_sha256_map(target, str(args.release_tag), args.assets_dir, promotion)
        if target in LINUX_TARGETS and not artifact_errors
        else None
    )
    builder_identity: dict[str, Any] | None = None
    builder_identity_errors: list[str] = []
    if target in LINUX_TARGETS:
        builder_identity, builder_identity_errors = read_json_object(
            args.builder_evidence,
            "Linux builder evidence",
        )
        errors.extend(builder_identity_errors)
    if target in LINUX_TARGETS:
        errors.extend(
            check_linux_smoke_evidence_file(
                target,
                str(args.release_tag),
                linux_native_smoke_command(
                    target,
                    promotion,
                    str(args.workflow_run_url),
                    int(args.release_source_run_attempt),
                    str(args.release_source_head_sha),
                    args.builder_evidence,
                ),
                str(args.workflow_run_url),
                int(args.release_source_run_attempt),
                args.linux_smoke_evidence,
                source_head_sha=str(args.release_source_head_sha),
                artifact_sha256=artifact_hashes,
                builder_identity=None if builder_identity_errors else builder_identity,
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
        errors.extend(check_xp_evidence_record_binding(args))
    if target in LINUX_TARGETS and not builder_identity_errors:
        errors.extend(
            check_linux_builder_release_source_binding(
                args,
                builder_identity=builder_identity,
            )
        )
    errors.extend(check_target_release_scoped_inputs(args))
    errors.extend(check_reserved_workspace_root_inputs(args))
    if not errors:
        errors.extend(check_local_evidence_preflight(args))
    if errors:
        return errors, {}

    record = linux_record(args, promotion) if target in LINUX_TARGETS else xp_record(args, promotion)
    registry = {
        "schema_version": 1,
        "policy": DEFAULT_EVIDENCE_POLICY,
        "accepted_evidence": [record],
    }
    errors.extend(check_platform_verified_evidence(registry=registry, promotion=promotion))
    return errors, record


def check_generator_append_registry_usage(record: dict[str, Any]) -> list[str]:
    target = str(record.get("target", "platform"))
    return [
        f"{target} generated evidence cannot be appended by this generator; "
        "write the candidate, package and validate its review bundle, then append with "
        "scripts/finalize_platform_verified_evidence_record.py --append-registry"
    ]


def release_tag_arg_value(args: argparse.Namespace) -> tuple[list[str], str]:
    raw_release_tag = getattr(args, "release_tag", "")
    if not isinstance(raw_release_tag, str) or not raw_release_tag:
        return [f"--release-tag must be a non-empty string, got {raw_release_tag!r}"], ""
    version_errors: list[str] = []
    version_from_tag(raw_release_tag, version_errors)
    return version_errors, raw_release_tag


def release_asset_base_url_arg_value(args: argparse.Namespace) -> tuple[list[str], str]:
    raw_base_url = getattr(args, "release_asset_base_url", "")
    if not isinstance(raw_base_url, str) or not raw_base_url:
        return [f"--release-asset-base-url must be a non-empty string, got {raw_base_url!r}"], ""
    return [], raw_base_url


def release_asset_base_url_repository(args: argparse.Namespace) -> str:
    _errors, base_url = release_asset_base_url_arg_value(args)
    match = GITHUB_RELEASE_BASE_RE.fullmatch(base_url)
    return match.group(1) if match else ""


def path_arg_value(raw_path: object, label: str) -> tuple[list[str], Path | None]:
    if not isinstance(raw_path, Path):
        return [f"{label} must be a pathlib.Path, got {raw_path!r}"], None
    return [], raw_path


def optional_path_arg_value(raw_path: object | None, label: str) -> tuple[list[str], Path | None]:
    if raw_path is None:
        return [], None
    return path_arg_value(raw_path, label)


def validate_common_args(args: argparse.Namespace) -> list[str]:
    errors: list[str] = []
    release_tag_errors, release_tag = release_tag_arg_value(args)
    errors.extend(release_tag_errors)
    assets_dir_errors, assets_dir = path_arg_value(getattr(args, "assets_dir", None), "artifact directory")
    errors.extend(assets_dir_errors)
    local_evidence_root_errors, local_evidence_root = path_arg_value(
        getattr(args, "local_evidence_root", Path(".")),
        "local evidence root",
    )
    errors.extend(local_evidence_root_errors)
    staged_upload_errors, staged_upload = optional_path_arg_value(
        getattr(args, "staged_upload_out_dir", None),
        "staged upload output directory",
    )
    errors.extend(staged_upload_errors)
    if assets_dir is not None:
        errors.extend(check_directory_path_hint(assets_dir, "artifact directory"))
        if not assets_dir.is_dir():
            errors.append(f"artifact directory missing: {assets_dir}")
        errors.extend(check_path_parent_symlinks(assets_dir, "artifact directory"))
    if local_evidence_root is not None:
        errors.extend(check_directory_path_hint(local_evidence_root, "local evidence root"))
    if staged_upload is not None:
        errors.extend(check_directory_path_hint(staged_upload, "staged upload output directory"))
    base_url_errors, base_url = release_asset_base_url_arg_value(args)
    errors.extend(base_url_errors)
    if not base_url_errors:
        match = GITHUB_RELEASE_BASE_RE.fullmatch(base_url)
        if not match:
            expected_tag = release_tag or "<release-tag>"
            errors.append(
                "--release-asset-base-url must be exactly "
                f"https://github.com/<owner>/<repo>/releases/download/{expected_tag}"
            )
        elif release_tag and match.group(2) != release_tag:
            errors.append(
                "--release-asset-base-url release tag must match --release-tag "
                f"{release_tag}"
            )
    if not args.release_source_head_sha:
        errors.append("--release-source-head-sha is required")
    elif not GITHUB_HEAD_SHA_RE.fullmatch(str(args.release_source_head_sha)):
        errors.append("--release-source-head-sha must be a 40-character lowercase Git SHA")
    if args.release_source_run_attempt is None:
        errors.append("--release-source-run-attempt is required")
    elif (
        not isinstance(args.release_source_run_attempt, int)
        or isinstance(args.release_source_run_attempt, bool)
        or args.release_source_run_attempt < 1
    ):
        errors.append("--release-source-run-attempt must be a positive integer")
    return errors


def validate_linux_args(args: argparse.Namespace) -> list[str]:
    errors: list[str] = []
    target = str(args.target)
    if not args.workflow_run_url:
        errors.append("--workflow-run-url is required for Linux evidence")
    elif not GITHUB_ACTIONS_RUN_RE.fullmatch(str(args.workflow_run_url)):
        errors.append("--workflow-run-url must be a GitHub Actions run URL")
    else:
        errors.extend(check_workflow_run_repository(args, str(args.workflow_run_url), "--workflow-run-url"))
    raw_builder_evidence = getattr(args, "builder_evidence", None)
    if raw_builder_evidence is None:
        errors.append("--builder-evidence is required for Linux evidence")
    else:
        builder_evidence_errors, builder_evidence = path_arg_value(
            raw_builder_evidence,
            "Linux builder evidence file",
        )
        errors.extend(builder_evidence_errors)
        if builder_evidence is not None:
            if not builder_evidence.is_file():
                errors.append(f"Linux builder evidence file missing: {builder_evidence}")
            elif builder_evidence.is_symlink():
                errors.append(f"Linux builder evidence file must not be a symlink: {builder_evidence}")
            else:
                errors.extend(check_path_parent_symlinks(builder_evidence, "Linux builder evidence file"))
            if builder_evidence.name != f"builder-identity-{target}.json":
                errors.append(f"--builder-evidence file name must be builder-identity-{target}.json")
    raw_smoke_evidence = getattr(args, "linux_smoke_evidence", None)
    if raw_smoke_evidence is None:
        errors.append("--linux-smoke-evidence is required for Linux evidence")
    else:
        smoke_evidence_errors, smoke_evidence = path_arg_value(
            raw_smoke_evidence,
            "Linux smoke evidence file",
        )
        errors.extend(smoke_evidence_errors)
        if smoke_evidence is not None:
            if not smoke_evidence.is_file():
                errors.append(f"Linux smoke evidence file missing: {smoke_evidence}")
            elif smoke_evidence.is_symlink():
                errors.append(f"Linux smoke evidence file must not be a symlink: {smoke_evidence}")
            else:
                errors.extend(check_path_parent_symlinks(smoke_evidence, "Linux smoke evidence file"))
            if smoke_evidence.name != f"native-smoke-{target}.log":
                errors.append(f"--linux-smoke-evidence file name must be native-smoke-{target}.log")
    required_labels = LINUX_TARGETS[target]["runner_labels"]
    labels = set(str(label) for label in args.runner_label)
    if not required_labels.issubset(labels):
        errors.append(f"--runner-label must include {sorted(required_labels)}")
    if args.xp_evidence is not None:
        errors.append("--xp-evidence is only valid for Windows XP evidence")
    if args.xp_evidence_dir is not None:
        errors.append("--xp-evidence-dir is only valid for Windows XP evidence")
    release_source_workflow_run_url = getattr(args, "release_source_workflow_run_url", None)
    if release_source_workflow_run_url is not None:
        if not GITHUB_ACTIONS_RUN_RE.fullmatch(str(release_source_workflow_run_url)):
            errors.append("--release-source-workflow-run-url must be a GitHub Actions run URL")
        else:
            errors.extend(
                check_workflow_run_repository(
                    args,
                    str(release_source_workflow_run_url),
                    "--release-source-workflow-run-url",
                )
            )
        if release_source_workflow_run_url != args.workflow_run_url:
            errors.append("--release-source-workflow-run-url must match --workflow-run-url for Linux evidence")
    release_source_artifact_name = getattr(args, "release_source_artifact_name", None)
    expected_artifact_name = linux_release_source_artifact_name(target, str(args.release_tag))
    if release_source_artifact_name is not None and release_source_artifact_name != expected_artifact_name:
        errors.append(
            f"--release-source-artifact-name must be {expected_artifact_name} for {target} Linux evidence"
        )
    return errors


def validate_xp_args(args: argparse.Namespace) -> list[str]:
    errors: list[str] = []
    if args.builder_evidence is not None:
        errors.append("--builder-evidence is only valid for Linux evidence")
    if args.linux_smoke_evidence is not None:
        errors.append("--linux-smoke-evidence is only valid for Linux evidence")
    raw_xp_evidence = getattr(args, "xp_evidence", None)
    if raw_xp_evidence is None:
        errors.append("--xp-evidence is required for Windows XP evidence")
    else:
        xp_evidence_errors, xp_evidence = path_arg_value(raw_xp_evidence, "XP evidence file")
        errors.extend(xp_evidence_errors)
        if xp_evidence is not None:
            if not xp_evidence.is_file():
                errors.append(f"XP evidence file missing: {xp_evidence}")
            elif xp_evidence.is_symlink():
                errors.append(f"XP evidence file must not be a symlink: {xp_evidence}")
            else:
                errors.extend(check_path_parent_symlinks(xp_evidence, "XP evidence file"))
    raw_xp_evidence_dir = getattr(args, "xp_evidence_dir", None)
    if raw_xp_evidence_dir is None:
        errors.append("--xp-evidence-dir is required for Windows XP evidence")
    else:
        xp_evidence_dir_errors, xp_evidence_dir = path_arg_value(
            raw_xp_evidence_dir,
            "XP evidence directory",
        )
        errors.extend(xp_evidence_dir_errors)
        if xp_evidence_dir is not None:
            errors.extend(check_directory_path_hint(xp_evidence_dir, "XP evidence directory"))
            if not xp_evidence_dir.is_dir():
                errors.append(f"XP evidence directory missing: {xp_evidence_dir}")
            elif xp_evidence_dir.is_symlink():
                errors.append(f"XP evidence directory must not be a symlink: {xp_evidence_dir}")
            else:
                errors.extend(check_path_parent_symlinks(xp_evidence_dir, "XP evidence directory"))
    xp_output_errors, xp_output_dir = optional_path_arg_value(
        getattr(args, "xp_evidence_output_dir", None),
        "XP evidence output directory",
    )
    errors.extend(xp_output_errors)
    if xp_output_dir is not None:
        errors.extend(check_directory_path_hint(xp_output_dir, "XP evidence output directory"))
    if args.workflow_run_url:
        errors.append("--workflow-run-url is only valid for Linux evidence")
    if args.runner_label:
        errors.append("--runner-label is only valid for Linux evidence")
    release_source_workflow_run_url = getattr(args, "release_source_workflow_run_url", None)
    if not release_source_workflow_run_url:
        errors.append("--release-source-workflow-run-url is required for Windows XP evidence")
    elif not GITHUB_ACTIONS_RUN_RE.fullmatch(str(release_source_workflow_run_url)):
        errors.append("--release-source-workflow-run-url must be a GitHub Actions run URL")
    else:
        errors.extend(
            check_workflow_run_repository(
                args,
                str(release_source_workflow_run_url),
                "--release-source-workflow-run-url",
            )
        )
    release_source_artifact_name = getattr(args, "release_source_artifact_name", None)
    if not release_source_artifact_name:
        errors.append("--release-source-artifact-name is required for Windows XP evidence")
    else:
        expected_artifact_name = xp_release_source_artifact_name(str(args.target), str(args.release_tag))
        if release_source_artifact_name != expected_artifact_name:
            errors.append(
                f"--release-source-artifact-name must be {expected_artifact_name} for {args.target} XP evidence"
            )
    return errors


def check_workflow_run_repository(
    args: argparse.Namespace,
    workflow_run_url: str,
    flag: str,
) -> list[str]:
    base_url_errors, base_url = release_asset_base_url_arg_value(args)
    if base_url_errors:
        return []
    release_match = GITHUB_RELEASE_BASE_RE.fullmatch(base_url)
    workflow_match = GITHUB_ACTIONS_RUN_RE.fullmatch(workflow_run_url)
    if not release_match or not workflow_match:
        return []
    release_repository = release_match.group(1)
    workflow_repository = workflow_match.group(1)
    if workflow_repository != release_repository:
        return [
            f"{flag} repository must match --release-asset-base-url repository "
            f"{release_repository}, got {workflow_repository}"
        ]
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


def check_target_release_scoped_inputs(args: argparse.Namespace) -> list[str]:
    target = str(args.target)
    release_tag = str(args.release_tag)
    errors = check_target_release_path_segments(
        target,
        release_tag,
        args.assets_dir,
        label="artifact directory",
    )
    errors.extend(
        check_target_release_path_segments(
            target,
            release_tag,
            staged_upload_out_dir(args),
            label="staged upload output directory",
        )
    )
    if target in LINUX_TARGETS:
        if args.builder_evidence is not None:
            errors.extend(
                check_target_release_path_segments(
                    target,
                    release_tag,
                    args.builder_evidence,
                    label="Linux builder evidence file",
                )
            )
        if args.linux_smoke_evidence is not None:
            errors.extend(
                check_target_release_path_segments(
                    target,
                    release_tag,
                    args.linux_smoke_evidence,
                    label="Linux smoke evidence file",
                )
            )
    if target in XP_TARGETS:
        if args.xp_evidence is not None:
            errors.extend(
                check_target_release_path_segments(
                    target,
                    release_tag,
                    args.xp_evidence,
                    label="XP evidence file",
                )
            )
        if args.xp_evidence_dir is not None:
            errors.extend(
                check_target_release_path_segments(
                    target,
                    release_tag,
                    args.xp_evidence_dir,
                    label="XP evidence directory",
                )
            )
        errors.extend(
            check_target_release_path_segments(
                target,
                release_tag,
                xp_evidence_output_dir(args),
                label="XP evidence output directory",
            )
        )
    return errors


def check_reserved_workspace_root_inputs(args: argparse.Namespace) -> list[str]:
    paths: list[tuple[Path, str]] = [
        (args.assets_dir, "artifact directory"),
        (staged_upload_out_dir(args), "staged upload output directory"),
    ]
    local_evidence_root = getattr(args, "local_evidence_root", Path("."))
    if isinstance(local_evidence_root, Path):
        root = local_evidence_root
    else:
        root = Path(str(local_evidence_root))
    if str(args.target) in LINUX_TARGETS:
        if args.builder_evidence is not None:
            paths.append((args.builder_evidence, "Linux builder evidence file"))
        if args.linux_smoke_evidence is not None:
            paths.append((args.linux_smoke_evidence, "Linux smoke evidence file"))
    if str(args.target) in XP_TARGETS:
        if args.xp_evidence is not None:
            paths.append((args.xp_evidence, "XP evidence file"))
        if args.xp_evidence_dir is not None:
            paths.append((args.xp_evidence_dir, "XP evidence directory"))
        paths.append((xp_evidence_output_dir(args), "XP evidence output directory"))
    errors: list[str] = []
    for path, label in paths:
        errors.extend(check_path_not_reserved_workspace_root(root, path, label))
    return errors


def check_path_not_reserved_workspace_root(root: Path, path: Path, label: str) -> list[str]:
    root_errors, root_path = path_arg_value(root, "local evidence root")
    path_errors, path_value = path_arg_value(path, label)
    errors = root_errors + path_errors
    if errors:
        return errors
    assert root_path is not None
    assert path_value is not None
    root_resolved = root_path.resolve(strict=False)
    path_resolved = path_value.resolve(strict=False)
    try:
        relative = path_resolved.relative_to(root_resolved)
    except ValueError:
        return []
    parts = tuple(part for part in relative.parts if part not in ("", "."))
    if not parts:
        return []
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


def check_linux_builder_release_source_binding(
    args: argparse.Namespace,
    *,
    builder_identity: dict[str, Any] | None = None,
) -> list[str]:
    if args.builder_evidence is None or not args.builder_evidence.is_file():
        return []
    if builder_identity is None:
        builder_identity, json_errors = read_json_object(
            args.builder_evidence,
            "Linux builder evidence",
        )
        if json_errors:
            return json_errors
    target = str(args.target)
    expected_head_sha = str(args.release_source_head_sha or "").strip()
    actual_head_sha = builder_identity.get("source_head_sha")
    errors: list[str] = []
    if not isinstance(actual_head_sha, str):
        errors.append(f"{target} builder evidence source_head_sha must be a string")
    elif actual_head_sha.strip() != expected_head_sha:
        errors.append(
            f"{target} builder evidence source_head_sha must match --release-source-head-sha "
            f"{expected_head_sha}, got {actual_head_sha.strip()!r}"
        )
    actual_observed_head_sha = builder_identity.get("observed_git_head_sha")
    if not isinstance(actual_observed_head_sha, str):
        errors.append(f"{target} builder evidence observed_git_head_sha must be a string")
    elif actual_observed_head_sha.strip() != expected_head_sha:
        errors.append(
            f"{target} builder evidence observed_git_head_sha must match --release-source-head-sha "
            f"{expected_head_sha}, got {actual_observed_head_sha.strip()!r}"
        )
    if builder_identity.get("git_worktree_clean") is not True:
        errors.append(f"{target} builder evidence git_worktree_clean must be true")
    expected_attempt = args.release_source_run_attempt
    actual_attempt = builder_identity.get("workflow_run_attempt")
    if not isinstance(actual_attempt, int) or isinstance(actual_attempt, bool) or actual_attempt < 1:
        errors.append(f"{target} builder evidence workflow_run_attempt must be a positive integer")
    elif actual_attempt != expected_attempt:
        errors.append(
            f"{target} builder evidence workflow_run_attempt must match "
            f"--release-source-run-attempt {expected_attempt}, got {actual_attempt!r}"
        )
    return errors


def check_xp_evidence_record_binding(args: argparse.Namespace) -> list[str]:
    if args.xp_evidence is None or not args.xp_evidence.is_file():
        return []
    evidence = read_json(args.xp_evidence)
    if "error" in evidence:
        return []
    target = str(args.target)
    release_tag = str(args.release_tag)
    actual_target = str(evidence.get("target", "")).strip()
    actual_release_tag = str(evidence.get("release_tag", "")).strip()
    errors: list[str] = []
    if actual_target != target:
        errors.append(
            f"{target} XP evidence target must match --target {target}, got {actual_target!r}"
        )
    if actual_release_tag != release_tag:
        errors.append(
            f"{target} XP evidence release_tag must match --release-tag {release_tag}, "
            f"got {actual_release_tag!r}"
        )
    asset_dirs = artifact_validation_asset_dirs(evidence)
    expected_assets_dir = args.assets_dir.as_posix()
    if asset_dirs != [expected_assets_dir]:
        errors.append(
            f"{target} XP evidence artifact_validation.command --assets-dir must match "
            f"--assets-dir {expected_assets_dir}, got {asset_dirs}"
        )
    source = evidence.get("release_source")
    if not isinstance(source, dict):
        errors.append(f"{target} XP evidence release_source must be an object")
        return errors
    expected_workflow = release_source_workflow(target)
    actual_workflow = source.get("workflow")
    if not isinstance(actual_workflow, str):
        errors.append(f"{target} XP evidence release_source.workflow must be a string")
    elif actual_workflow != expected_workflow:
        errors.append(f"{target} XP evidence release_source.workflow must be {expected_workflow}")
    expected_workflow_run_url = str(args.release_source_workflow_run_url or "")
    actual_workflow_run_url = source.get("workflow_run_url")
    if not isinstance(actual_workflow_run_url, str):
        errors.append(f"{target} XP evidence release_source.workflow_run_url must be a string")
    elif actual_workflow_run_url != expected_workflow_run_url:
        errors.append(
            f"{target} XP evidence release_source.workflow_run_url must match "
            f"--release-source-workflow-run-url {expected_workflow_run_url}, "
            f"got {actual_workflow_run_url!r}"
        )
    expected_head_sha = str(args.release_source_head_sha or "")
    actual_head_sha = source.get("head_sha")
    if not isinstance(actual_head_sha, str):
        errors.append(f"{target} XP evidence release_source.head_sha must be a string")
    elif actual_head_sha.strip() != expected_head_sha:
        errors.append(
            f"{target} XP evidence release_source.head_sha must match "
            f"--release-source-head-sha {expected_head_sha}, got {actual_head_sha.strip()!r}"
        )
    expected_run_attempt = args.release_source_run_attempt
    actual_run_attempt = source.get("run_attempt")
    if (
        not isinstance(actual_run_attempt, int)
        or isinstance(actual_run_attempt, bool)
        or actual_run_attempt < 1
    ):
        errors.append(f"{target} XP evidence release_source.run_attempt must be a positive integer")
    elif actual_run_attempt != expected_run_attempt:
        errors.append(
            f"{target} XP evidence release_source.run_attempt must match "
            f"--release-source-run-attempt {expected_run_attempt}, got {actual_run_attempt!r}"
        )
    return errors


def check_local_evidence_preflight(args: argparse.Namespace) -> list[str]:
    from check_platform_goal_local_evidence import check_platform_goal_local_evidence

    target = str(args.target)
    local_evidence_root = getattr(args, "local_evidence_root", Path("."))
    if target in LINUX_TARGETS:
        return check_platform_goal_local_evidence(
            root=local_evidence_root,
            release_tag=str(args.release_tag),
            targets=(target,),
            linux_workflow_run_url=str(args.workflow_run_url),
            linux_source_head_sha=str(args.release_source_head_sha),
            linux_source_run_attempt=args.release_source_run_attempt,
            strict_artifacts=True,
            assets_dir=args.assets_dir,
            linux_builder_evidence=args.builder_evidence,
            linux_smoke_evidence=args.linux_smoke_evidence,
        )
    return check_platform_goal_local_evidence(
        root=local_evidence_root,
        release_tag=str(args.release_tag),
        targets=(target,),
        strict_artifacts=True,
        assets_dir=args.assets_dir,
        xp_evidence=args.xp_evidence,
        xp_evidence_dir=args.xp_evidence_dir,
        xp_source_workflow_run_url=str(args.release_source_workflow_run_url),
        xp_source_head_sha=str(args.release_source_head_sha),
        xp_source_run_attempt=args.release_source_run_attempt,
    )


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
        "artifact_name": linux_release_source_artifact_name(target, str(args.release_tag)),
        "release_asset_source": release_asset_source(args, target, promotion),
        "runner_labels": sorted(set(str(label) for label in args.runner_label)),
        "builder_identity": builder_identity,
        "builder_identity_sha256": json_sha256(builder_identity),
        "linux_evidence_sources": linux_evidence_sources(args, builder_identity),
        "native_build_command": linux_native_build_command(target, promotion),
        "native_smoke_command": linux_native_smoke_command(
            target,
            promotion,
            str(args.workflow_run_url),
            int(args.release_source_run_attempt),
            str(args.release_source_head_sha),
            args.builder_evidence,
        ),
        "linux_smoke_evidence_sha256": linux_smoke_evidence_sha256_map(args.linux_smoke_evidence),
        "linux_smoke_summary": linux_smoke_summary(
            target,
            str(args.release_tag),
            args.linux_smoke_evidence,
        ),
        "local_evidence_preflight_command": local_evidence_preflight_command(args),
        "staged_upload_command": staged_upload_command(args),
        "artifact_validation_command": (
            f"python scripts/check_platform_promotion_artifacts.py --target {target} "
            f"--assets-dir {args.assets_dir.as_posix()} --tag {args.release_tag} --strict"
        ),
        "checks": LINUX_CHECKS,
        "release_asset_urls": release_asset_urls(target, str(args.release_tag), str(args.release_asset_base_url), promotion),
        "artifact_sha256": artifact_sha256_map(target, str(args.release_tag), args.assets_dir, promotion),
    }


def linux_native_build_command(target: str, promotion: dict[str, Any]) -> str:
    requirements = promotion_requirements(target, promotion)
    arch = str(requirements.get("release_matrix_arch", ""))
    script = str(requirements.get("build_script", ""))
    return f"TARGET_ARCH={arch} PYTHON_BIN=.venv-native/bin/python bash {script}"


def linux_evidence_sources(
    args: argparse.Namespace,
    builder_identity: dict[str, Any],
) -> dict[str, dict[str, object]]:
    return {
        "builder_identity": file_source_record(
            args.builder_evidence,
            sha256=json_sha256(builder_identity),
        ),
        "native_smoke": file_source_record(args.linux_smoke_evidence),
    }


def file_source_record(path: Path, *, sha256: str | None = None) -> dict[str, object]:
    return {
        "file": path.name,
        "size_bytes": path.stat().st_size,
        "sha256": sha256 or sha256_file(path),
    }


def linux_native_smoke_command(
    target: str,
    promotion: dict[str, Any],
    workflow_run_url: str,
    workflow_run_attempt: int,
    source_head_sha: str,
    builder_evidence: Path | str,
) -> str:
    requirements = promotion_requirements(target, promotion)
    script = str(requirements.get("smoke_script", ""))
    return (
        f"bash {script} --target {target} "
        f"--workflow-run-url {workflow_run_url} --workflow-run-attempt {workflow_run_attempt} "
        f"--source-head-sha {source_head_sha} --builder-evidence {Path(builder_evidence).as_posix()}"
    )


def release_asset_source(args: argparse.Namespace, target: str, promotion: dict[str, Any]) -> dict[str, Any]:
    if target in LINUX_TARGETS:
        raw_workflow_run_url = getattr(args, "release_source_workflow_run_url", None)
        workflow_run_url = str(args.workflow_run_url if raw_workflow_run_url is None else raw_workflow_run_url)
        raw_artifact_name = getattr(args, "release_source_artifact_name", None)
        artifact_name = str(
            linux_release_source_artifact_name(target, str(args.release_tag))
            if raw_artifact_name is None
            else raw_artifact_name
        )
    else:
        workflow_run_url = str(getattr(args, "release_source_workflow_run_url", ""))
        artifact_name = str(getattr(args, "release_source_artifact_name", ""))
    return {
        "type": "github-actions-artifact",
        "workflow": release_source_workflow(target),
        "workflow_run_url": workflow_run_url,
        "artifact_name": artifact_name,
        "head_sha": str(args.release_source_head_sha),
        "run_attempt": int(args.release_source_run_attempt),
        "contains_files": expected_artifact_names(target, str(args.release_tag), promotion),
    }


def promotion_requirements(target: str, promotion: dict[str, Any]) -> dict[str, Any]:
    entries = {
        str(item.get("id")): item
        for item in promotion.get("protected_targets", [])
        if isinstance(item, dict)
    }
    requirements = entries.get(target, {}).get("promotion_to_100_requires", {})
    return requirements if isinstance(requirements, dict) else {}


def xp_record(args: argparse.Namespace, promotion: dict[str, Any]) -> dict[str, Any]:
    target = str(args.target)
    arch = XP_TARGETS[target]["architecture"]
    evidence = read_json(args.xp_evidence)
    host_identity = xp_host_identity_summary(evidence)
    evidence_summary = xp_evidence_summary(target, str(args.release_tag), evidence)
    smoke_hashes = xp_smoke_evidence_sha256_map(evidence)
    requirements = promotion_requirements(target, promotion)
    return {
        "target": target,
        "evidence_type": "windows-xp-native-host",
        "status": "accepted",
        "readiness_percent": 100.0,
        "release_tag": str(args.release_tag),
        "promotion_config_sha256": promotion_config_sha256(promotion),
        "workflow": str(requirements.get("release_source_workflow", "")),
        "workflow_inputs": xp_workflow_inputs(args),
        "architecture": arch,
        "separate_legacy_toolchain": True,
        "current_python_pyqt6_stack": False,
        "xp_evidence_sha256": sha256_file(args.xp_evidence),
        "xp_evidence_contract_sha256": xp_native_evidence_contract_sha256(),
        "xp_host_identity_sha256": json_sha256(host_identity),
        "xp_evidence_summary": evidence_summary,
        "xp_smoke_evidence_sha256": smoke_hashes,
        "xp_evidence_sources": xp_evidence_sources(args, evidence_summary, smoke_hashes),
        "release_asset_source": release_asset_source(args, target, promotion),
        "native_evidence_validation_command": xp_native_evidence_validation_command(args),
        "local_evidence_preflight_command": local_evidence_preflight_command(args),
        "staged_upload_command": staged_upload_command(args),
        "artifact_validation_command": (
            f"python scripts/check_platform_promotion_artifacts.py --target {target} "
            f"--assets-dir {args.assets_dir.as_posix()} --tag {args.release_tag} --strict"
        ),
        "checks": XP_CHECKS,
        "release_asset_urls": release_asset_urls(target, str(args.release_tag), str(args.release_asset_base_url), promotion),
        "artifact_sha256": artifact_sha256_map(target, str(args.release_tag), args.assets_dir, promotion),
    }


def xp_native_evidence_validation_command(args: argparse.Namespace) -> str:
    command = (
        "python scripts/check_xp_native_evidence.py "
        f"--evidence {args.xp_evidence.as_posix()} --assets-dir {args.assets_dir.as_posix()}"
    )
    if args.xp_evidence_dir is not None:
        command = f"{command} --evidence-dir {args.xp_evidence_dir.as_posix()}"
    return command


def local_evidence_preflight_command(args: argparse.Namespace) -> str:
    target = str(args.target)
    local_evidence_root = getattr(args, "local_evidence_root", Path("."))
    local_evidence_root_path = (
        local_evidence_root
        if isinstance(local_evidence_root, Path)
        else Path(str(local_evidence_root))
    )
    command = (
        "python scripts/check_platform_goal_local_evidence.py "
        f"--root {local_evidence_root_path.as_posix()} --release-tag {args.release_tag} --target {target} "
        f"--assets-dir {args.assets_dir.as_posix()} --repository {release_asset_base_url_repository(args)}"
    )
    if target in LINUX_TARGETS:
        return (
            f"{command} --linux-builder-evidence {args.builder_evidence.as_posix()} "
            f"--linux-smoke-evidence {args.linux_smoke_evidence.as_posix()} "
            f"--linux-workflow-run-url {args.workflow_run_url} "
            f"--linux-source-head-sha {args.release_source_head_sha} "
            f"--linux-source-run-attempt {args.release_source_run_attempt}"
        )
    return (
        f"{command} --xp-evidence {args.xp_evidence.as_posix()} "
        f"--xp-evidence-dir {args.xp_evidence_dir.as_posix()} "
        f"--xp-source-workflow-run-url {args.release_source_workflow_run_url} "
        f"--xp-source-head-sha {args.release_source_head_sha} "
        f"--xp-source-run-attempt {args.release_source_run_attempt}"
    )


def staged_upload_command(args: argparse.Namespace) -> str:
    target = str(args.target)
    out_dir = staged_upload_out_dir(args)
    if target in LINUX_TARGETS:
        return (
            "python scripts/stage_extended_linux_evidence_upload.py "
            f"--target {target} --release-tag {args.release_tag} "
            f"--source-dir {args.assets_dir.as_posix()} "
            f"--out-dir {out_dir.as_posix()} --force"
        )
    return (
        "python scripts/stage_xp_native_evidence_upload.py "
        f"--target {target} --release-tag {args.release_tag} "
        f"--assets-dir {args.assets_dir.as_posix()} "
        f"--evidence-output-dir {xp_evidence_output_dir(args).as_posix()} "
        f"--out-dir {out_dir.as_posix()} --force"
    )


def staged_upload_out_dir(args: argparse.Namespace) -> Path:
    override = getattr(args, "staged_upload_out_dir", None)
    if override is not None:
        return override
    return Path("platform-evidence-upload") / str(args.target) / str(args.release_tag)


def xp_evidence_output_dir(args: argparse.Namespace) -> Path:
    override = getattr(args, "xp_evidence_output_dir", None)
    if override is not None:
        return override
    return Path("xp-evidence-output") / str(args.target) / str(args.release_tag)


def xp_workflow_inputs(args: argparse.Namespace) -> dict[str, str]:
    return {
        "target": str(args.target),
        "release_tag": str(args.release_tag),
        "release_asset_base_url": str(args.release_asset_base_url).rstrip("/"),
        "assets_dir": args.assets_dir.as_posix(),
        "evidence_file": args.xp_evidence.as_posix(),
        "evidence_dir": args.xp_evidence_dir.as_posix(),
    }


def xp_evidence_sources(
    args: argparse.Namespace,
    evidence_summary: dict[str, Any],
    smoke_hashes: dict[str, str],
) -> dict[str, Any]:
    evidence_source = file_source_record(
        args.xp_evidence,
        sha256=sha256_file(args.xp_evidence),
    )
    evidence_source["path"] = args.xp_evidence.as_posix()

    smoke_sources: dict[str, dict[str, object]] = {}
    evidence_dir = args.xp_evidence_dir
    raw_files = evidence_summary.get("smoke_evidence_files", {})
    if isinstance(raw_files, dict):
        for smoke_id, raw_file in sorted(raw_files.items()):
            if not isinstance(smoke_id, str) or not isinstance(raw_file, str):
                continue
            if not archive_entry_name_is_safe(raw_file):
                continue
            smoke_path = evidence_dir / raw_file
            if not smoke_path.is_file():
                continue
            digest = smoke_hashes.get(smoke_id, "")
            if not lowercase_sha256_hex(digest):
                continue
            smoke_sources[smoke_id] = {
                "file": raw_file.replace("\\", "/"),
                "size_bytes": smoke_path.stat().st_size,
                "sha256": digest,
            }

    return {
        "evidence": evidence_source,
        "smoke_evidence": smoke_sources,
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


def lowercase_sha256_hex(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def xp_evidence_summary(target: str, release_tag: str, evidence: dict[str, Any]) -> dict[str, Any]:
    release_source = evidence.get("release_source", {})
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
    smoke_ids: list[str] = []
    smoke_commands: dict[str, str] = {}
    smoke_evidence_files: dict[str, str] = {}
    for item in smoke_results:
        if not isinstance(item, dict):
            continue
        smoke_id = item.get("id")
        if not isinstance(smoke_id, str) or not smoke_id:
            continue
        smoke_ids.append(smoke_id)
        command = item.get("command")
        if isinstance(command, str):
            smoke_commands[smoke_id] = command
        evidence_file = item.get("evidence_file")
        if isinstance(evidence_file, str) and archive_entry_name_is_safe(evidence_file):
            smoke_evidence_files[smoke_id] = evidence_file
    os_summary = {
        "name": summary_string(os_data.get("name")),
        "architecture": summary_string(os_data.get("architecture")),
        "service_pack": summary_string(os_data.get("service_pack")),
    }
    edition = summary_string(os_data.get("edition"))
    if edition.strip():
        os_summary["edition"] = edition
    return {
        "target": target,
        "release_tag": release_tag,
        "release_source": xp_release_source_summary(release_source),
        "host_identity": xp_host_identity_summary(evidence),
        "os": os_summary,
        "toolchain": {
            "separate_legacy_toolchain": toolchain.get("separate_legacy_toolchain") is True,
            "current_python_pyqt6_stack": toolchain.get("current_python_pyqt6_stack") is True,
        },
        "security": {
            "legacy_crypto_profile_scoped": security.get("legacy_crypto_profile_scoped") is True,
            "modern_defaults_unchanged": security.get("modern_defaults_unchanged") is True,
            "weak_crypto_global_default": security.get("weak_crypto_global_default") is True,
            "patch_evidence": security.get("patch_evidence", {}),
        },
        "smoke_ids": sorted(smoke_ids),
        "smoke_evidence_files": {
            smoke_id: smoke_evidence_files[smoke_id]
            for smoke_id in sorted(smoke_evidence_files)
        },
        "smoke_commands": {smoke_id: smoke_commands[smoke_id] for smoke_id in sorted(smoke_commands)},
    }


def summary_string(value: Any) -> str:
    return value if isinstance(value, str) else ""


def xp_release_source_summary(raw_source: Any) -> dict[str, Any]:
    if not isinstance(raw_source, dict):
        return {}
    workflow = raw_source.get("workflow")
    workflow_run_url = raw_source.get("workflow_run_url")
    head_sha = raw_source.get("head_sha")
    run_attempt = raw_source.get("run_attempt")
    return {
        "workflow": workflow if isinstance(workflow, str) else "",
        "workflow_run_url": workflow_run_url if isinstance(workflow_run_url, str) else "",
        "head_sha": head_sha if isinstance(head_sha, str) else "",
        "run_attempt": (
            run_attempt
            if isinstance(run_attempt, int) and not isinstance(run_attempt, bool) and run_attempt > 0
            else None
        ),
    }


def xp_host_identity_summary(evidence: dict[str, Any]) -> dict[str, Any]:
    raw_identity = evidence.get("host_identity", {})
    if not isinstance(raw_identity, dict):
        return {}
    raw_os = raw_identity.get("os", {})
    raw_toolchain = raw_identity.get("toolchain", {})
    os_data = raw_os if isinstance(raw_os, dict) else {}
    toolchain = raw_toolchain if isinstance(raw_toolchain, dict) else {}
    host_identity = {
        "schema_version": raw_identity.get("schema_version"),
        "target": summary_string(raw_identity.get("target")),
        "release_tag": summary_string(raw_identity.get("release_tag")),
        "host_label": summary_string(raw_identity.get("host_label")),
        "evidence_run_id": summary_string(raw_identity.get("evidence_run_id")),
        "observed_at_utc": summary_string(raw_identity.get("observed_at_utc")),
        "operator_private_data_redacted": raw_identity.get("operator_private_data_redacted") is True,
        "os": {
            key: summary_string(os_data.get(key))
            for key in ("name", "architecture", "service_pack", "edition")
            if summary_string(os_data.get(key)).strip()
        },
        "toolchain": {
            "separate_legacy_toolchain": toolchain.get("separate_legacy_toolchain") is True,
            "current_python_pyqt6_stack": toolchain.get("current_python_pyqt6_stack") is True,
            "description": summary_string(toolchain.get("description")),
        },
    }
    return host_identity


def xp_smoke_evidence_sha256_map(evidence: dict[str, Any]) -> dict[str, str]:
    results = evidence.get("smoke_results", [])
    if not isinstance(results, list):
        return {}
    hashes: dict[str, str] = {}
    for item in results:
        if not isinstance(item, dict):
            continue
        smoke_id = item.get("id")
        evidence_file = item.get("evidence_file")
        evidence_sha = item.get("evidence_sha256")
        if (
            isinstance(smoke_id, str)
            and smoke_id
            and isinstance(evidence_file, str)
            and archive_entry_name_is_safe(evidence_file)
            and lowercase_sha256_hex(evidence_sha)
        ):
            hashes[smoke_id] = evidence_sha
    return hashes


def linux_smoke_evidence_sha256_map(smoke_evidence: Path) -> dict[str, str]:
    return {"native_smoke": sha256_file(smoke_evidence)}


def linux_smoke_summary(target: str, release_tag: str, smoke_evidence: Path) -> dict[str, Any]:
    text = smoke_evidence.read_text(encoding="utf-8")

    def value(key: str) -> str:
        values = linux_smoke_line_values(text, key)
        return values[0] if len(values) == 1 else ""

    def bool_value(key: str) -> bool:
        return value(key).lower() == "true"

    attempt = value("native installer smoke workflow run attempt")
    return {
        "target": value("native installer smoke target") or target,
        "release_tag": value("native installer smoke release") or release_tag,
        "workflow_run_url": value("native installer smoke workflow run"),
        "workflow_run_attempt": int(attempt) if attempt.isdigit() else 0,
        "source_head_sha": value("native installer smoke source head sha"),
        "git_head_sha": value("native installer smoke git head sha"),
        "target_arch": value("native installer smoke target arch"),
        "host_label": value("native installer smoke host label"),
        "evidence_run_id": value("native installer smoke evidence run id"),
        "observed_at_utc": value("native installer smoke observed at utc"),
        "uname_machine": value("native installer smoke uname machine"),
        "dpkg_architecture": value("native installer smoke dpkg architecture"),
        "userland_bits": value("native installer smoke userland bits"),
        "os_release": value("native installer smoke os release"),
        "kernel_release": value("native installer smoke kernel release"),
        "glibc_version": value("native installer smoke glibc version"),
        "python_ssl_openssl": value("native installer smoke python ssl openssl"),
        "openssl_cli_version": value("native installer smoke openssl cli version"),
        "security": {
            "tls_minimum_modern_profiles": value("native installer smoke TLS minimum modern profiles"),
            "tls_preferred_modern_profiles": value("native installer smoke TLS preferred modern profiles"),
            "legacy_compatibility_profile": value("native installer smoke legacy compatibility profile"),
            "legacy_crypto_scope": value("native installer smoke legacy crypto scope"),
            "weak_crypto_global_default": bool_value("native installer smoke weak crypto global default"),
            "modern_defaults_unchanged": bool_value("native installer smoke modern defaults unchanged"),
            "security_update_channel": value("native installer smoke security update channel"),
            "cve_review_reference": value("native installer smoke CVE review reference"),
        },
    }


def append_record_to_registry(record: dict[str, Any], *, registry_path: object = EVIDENCE_PATH) -> list[str]:
    errors = check_text_output_path(registry_path, "platform verified evidence registry")
    if errors:
        return errors
    assert isinstance(registry_path, Path)
    registry = read_evidence_registry(registry_path)
    accepted = registry.get("accepted_evidence")
    if not isinstance(accepted, list):
        return ["platform verified evidence accepted_evidence must be a list"]

    target = accepted_record_target(record)
    if not target:
        return [
            "platform verified evidence record target must be a non-empty string, "
            f"got {record.get('target', '')!r}"
        ]
    duplicate_targets = [
        entry
        for entry in accepted
        if isinstance(entry, dict) and accepted_record_target(entry) == target
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
        require_review_bundles=True,
    )
    if errors:
        return errors

    write_text_output(registry_path, json.dumps(updated, indent=2) + "\n")
    return []


def check_text_output_path(path: object, label: str) -> list[str]:
    path_errors, path_value = path_arg_value(path, label)
    if path_errors:
        return path_errors
    assert path_value is not None
    parent = path_value.parent
    if parent.is_symlink():
        return [f"{label} directory must not be a symlink: {parent}"]
    parent_errors = check_path_parent_symlinks(parent, f"{label} directory")
    if parent_errors:
        return parent_errors
    if parent.exists() and not parent.is_dir():
        return [f"{label} directory must be a directory: {parent}"]
    if path_value.is_symlink():
        return [f"{label} must not be a symlink: {path_value}"]
    if path_value.exists() and not path_value.is_file():
        return [f"{label} must be a regular file: {path_value}"]
    return []


def check_generated_record_output_path(path: object, record: dict[str, Any]) -> list[str]:
    path_errors, path_value = path_arg_value(path, "platform verified evidence record output file")
    if path_errors:
        return path_errors
    assert path_value is not None
    target = accepted_record_target(record)
    if not target:
        return [
            "platform verified evidence record target must be a non-empty string, "
            f"got {record.get('target', '')!r}"
        ]
    expected_name = generated_record_file_name(target)
    if path_value.name != expected_name:
        return [
            f"platform verified evidence record output file name must be {expected_name}, "
            f"got {path_value.name!r}"
        ]
    return check_text_output_path(path_value, "platform verified evidence record output file")


def generated_record_file_name(target: str) -> str:
    return f"platform-verified-evidence-{target}.json"


def accepted_record_target(record: dict[str, Any]) -> str:
    target = record.get("target", "")
    if not isinstance(target, str):
        return ""
    return target.strip()


def write_text_output(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8", newline="\n")


def read_evidence_registry(path: object) -> dict[str, Any]:
    path_errors, path_value = path_arg_value(path, "platform verified evidence registry")
    if path_errors:
        return {
            "schema_version": 0,
            "policy": "; ".join(path_errors),
            "accepted_evidence": None,
        }
    assert path_value is not None
    if not path_value.exists():
        return {
            "schema_version": 1,
            "policy": DEFAULT_EVIDENCE_POLICY,
            "accepted_evidence": [],
        }
    try:
        data = json.loads(path_value.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {
            "schema_version": 0,
            "policy": f"Invalid evidence registry JSON: {exc}",
            "accepted_evidence": None,
        }
    return data if isinstance(data, dict) else {"schema_version": 0, "policy": "", "accepted_evidence": None}


def read_json(path: object) -> dict[str, Any]:
    path_errors, path_value = path_arg_value(path, "JSON file")
    if path_errors:
        return {"schema_version": 0, "error": "; ".join(path_errors)}
    assert path_value is not None
    try:
        data = json.loads(path_value.read_text(encoding="utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return {"schema_version": 0, "error": f"invalid JSON: {exc}"}
    return data if isinstance(data, dict) else {"schema_version": 0, "error": "JSON root must be an object"}


def read_json_object(path: object, label: str) -> tuple[dict[str, Any], list[str]]:
    path_errors, path_value = path_arg_value(path, f"{label} file")
    if path_errors:
        return {"schema_version": 0, "error": "; ".join(path_errors)}, path_errors
    assert path_value is not None
    data = read_json(path_value)
    error = str(data.get("error", ""))
    if data.get("schema_version") == 0 and error:
        if error == "JSON root must be an object":
            return data, [f"{label} file must contain a JSON object: {path_value}"]
        return data, [f"{label} file is not readable JSON: {path_value}: {error}"]
    return data, []


if __name__ == "__main__":
    raise SystemExit(main())

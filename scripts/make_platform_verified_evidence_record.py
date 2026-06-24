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
    check_linux_smoke_builder_identity_binding,
    check_linux_smoke_log_text,
    check_platform_verified_evidence,
    directory_path_has_file_suffix,
    json_sha256,
    linux_release_source_artifact_name,
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
    "release source head SHA binding, "
    "release source run-attempt binding, "
    "release source workflow file binding, "
    "local protected-goal evidence preflight command binding, "
    "finalized accepted-record source file binding, "
    "finalized accepted-record release asset URL binding, "
    "Linux release source artifact names must be target/release-scoped, "
    "Linux accepted evidence command paths must be target/release-scoped, "
    "XP release source artifact names must be target/release-scoped, "
    "XP accepted evidence command paths must be target/release-scoped, "
    "per-artifact SHA-256 digests, safe relative non-link native archive entries, "
    "exact safe checksum and native manifest file references, exact safe release asset URL filenames, "
    "exact required check lists, exact workflow dispatch input sets, exact evidence source record fields, "
    "exact release source and review bundle fields, "
    "Linux builder identity evidence, builder identity SHA-256, "
    "Linux builder/smoke source file binding, "
    "Linux builder/smoke host identity binding, "
    "builder identity release/run binding, Linux builder source head SHA binding, "
    "Linux builder observed Git HEAD binding, Linux builder clean checkout binding, "
    "Linux builder host identity binding when applicable, "
    "Linux builder rpm and non-interactive sudo evidence, "
    "Linux security patch evidence, Linux security smoke proof-line binding, "
    "Linux native build and smoke command provenance, "
    "Linux smoke evidence SHA-256, Linux smoke release/run/source head SHA binding, "
    "Linux smoke runtime architecture and userland binding, "
    "Linux smoke sanitized host identity and observed-at timestamp binding, "
    "Linux workflow dispatch inputs when applicable, XP workflow dispatch inputs when applicable, "
    "XP evidence source file binding, XP evidence release source binding, and "
    "XP evidence bundle SHA-256 digests, "
    "XP evidence validation command binding, XP evidence contract SHA-256, "
    "XP evidence summary binding, XP host identity SHA-256 binding, XP smoke host identity binding, "
    "XP smoke observed-at timestamp binding, XP smoke OS identity binding, "
    "XP smoke host probe proof-line binding, "
    "XP security patch evidence, "
    "tracked scripts/xp_smoke_runner.cmd XP smoke command provenance, "
    "canonical XP smoke proof-file command binding, "
    "canonical XP smoke evidence-file summary binding and "
    "XP security smoke proof-line binding when applicable, and review bundle manifest, "
    "review bundle archive, safe relative non-symlink review bundle archive entries, and review bundle SHA-256 "
    "sidecar digests before strict promotion, and release uploads must include those review bundle "
    "files with matching size, SHA-256 and checksum-sidecar coverage; each accepted record must include the promotion "
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
GITHUB_ACTIONS_RUN_RE = re.compile(rf"^https://github\.com/({GITHUB_REPOSITORY_RE})/actions/runs/\d+/?$")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    errors, record = build_evidence_record(args)
    if errors:
        for error in errors:
            print(f"platform verified evidence record: {error}", file=sys.stderr)
        return 1
    output = json.dumps(record, indent=2) + "\n"
    if args.out:
        output_errors = check_text_output_path(args.out, "platform verified evidence record output file")
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
    parser.add_argument("--release-tag", required=True, help="Release tag, for example v1.0.2")
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
    parser.add_argument("--xp-evidence", type=Path, help="Windows XP native evidence JSON for XP targets")
    parser.add_argument(
        "--xp-evidence-dir",
        type=Path,
        help="directory containing smoke evidence files referenced by --xp-evidence",
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
    builder_identity = read_json(args.builder_evidence) if target in LINUX_TARGETS else None
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
                ),
                str(args.workflow_run_url),
                int(args.release_source_run_attempt),
                args.linux_smoke_evidence,
                source_head_sha=str(args.release_source_head_sha),
                artifact_sha256=artifact_hashes,
                builder_identity=builder_identity,
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
    if target in LINUX_TARGETS:
        errors.extend(check_linux_builder_release_source_binding(args))
    errors.extend(check_target_release_scoped_inputs(args))
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
    missing_final_fields = [
        field for field in ("finalized_record_release_asset_url", "review_bundle") if field not in record
    ]
    if not missing_final_fields:
        return []
    target = str(record.get("target", "platform"))
    return [
        f"{target} generated evidence is an unfinalized candidate; "
        "finalize it with scripts/finalize_platform_verified_evidence_record.py "
        "--append-registry before adding it to configs/platform_verified_evidence.json"
    ]


def validate_common_args(args: argparse.Namespace) -> list[str]:
    errors: list[str] = []
    version_errors: list[str] = []
    version_from_tag(str(args.release_tag), version_errors)
    errors.extend(version_errors)
    errors.extend(check_directory_path_hint(args.assets_dir, "artifact directory"))
    local_evidence_root = getattr(args, "local_evidence_root", Path("."))
    errors.extend(check_directory_path_hint(local_evidence_root, "local evidence root"))
    if not args.assets_dir.is_dir():
        errors.append(f"artifact directory missing: {args.assets_dir}")
    errors.extend(check_path_parent_symlinks(args.assets_dir, "artifact directory"))
    base_url = str(args.release_asset_base_url)
    match = GITHUB_RELEASE_BASE_RE.fullmatch(base_url)
    if not match:
        errors.append(
            "--release-asset-base-url must be exactly "
            f"https://github.com/<owner>/<repo>/releases/download/{args.release_tag}"
        )
    elif match.group(2) != str(args.release_tag):
        errors.append(
            "--release-asset-base-url release tag must match --release-tag "
            f"{args.release_tag}"
        )
    if not args.release_source_head_sha:
        errors.append("--release-source-head-sha is required")
    elif not GITHUB_HEAD_SHA_RE.fullmatch(str(args.release_source_head_sha)):
        errors.append("--release-source-head-sha must be a 40-character lowercase Git SHA")
    if args.release_source_run_attempt is None:
        errors.append("--release-source-run-attempt is required")
    elif args.release_source_run_attempt < 1:
        errors.append("--release-source-run-attempt must be a positive integer")
    return errors


def validate_linux_args(args: argparse.Namespace) -> list[str]:
    errors: list[str] = []
    target = str(args.target)
    if not args.workflow_run_url:
        errors.append("--workflow-run-url is required for Linux evidence")
    elif not GITHUB_ACTIONS_RUN_RE.fullmatch(str(args.workflow_run_url).rstrip("/")):
        errors.append("--workflow-run-url must be a GitHub Actions run URL")
    else:
        errors.extend(check_workflow_run_repository(args, str(args.workflow_run_url), "--workflow-run-url"))
    if args.builder_evidence is None:
        errors.append("--builder-evidence is required for Linux evidence")
    elif not args.builder_evidence.is_file():
        errors.append(f"Linux builder evidence file missing: {args.builder_evidence}")
    elif args.builder_evidence.is_symlink():
        errors.append(f"Linux builder evidence file must not be a symlink: {args.builder_evidence}")
    else:
        errors.extend(check_path_parent_symlinks(args.builder_evidence, "Linux builder evidence file"))
    if args.builder_evidence is not None and args.builder_evidence.name != f"builder-identity-{target}.json":
        errors.append(f"--builder-evidence file name must be builder-identity-{target}.json")
    if args.linux_smoke_evidence is None:
        errors.append("--linux-smoke-evidence is required for Linux evidence")
    elif not args.linux_smoke_evidence.is_file():
        errors.append(f"Linux smoke evidence file missing: {args.linux_smoke_evidence}")
    elif args.linux_smoke_evidence.is_symlink():
        errors.append(f"Linux smoke evidence file must not be a symlink: {args.linux_smoke_evidence}")
    else:
        errors.extend(check_path_parent_symlinks(args.linux_smoke_evidence, "Linux smoke evidence file"))
    if args.linux_smoke_evidence is not None and args.linux_smoke_evidence.name != f"native-smoke-{target}.log":
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
    if release_source_workflow_run_url:
        if not GITHUB_ACTIONS_RUN_RE.fullmatch(str(release_source_workflow_run_url).rstrip("/")):
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
    if release_source_artifact_name and release_source_artifact_name != expected_artifact_name:
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
    if args.xp_evidence is None:
        errors.append("--xp-evidence is required for Windows XP evidence")
    elif not args.xp_evidence.is_file():
        errors.append(f"XP evidence file missing: {args.xp_evidence}")
    elif args.xp_evidence.is_symlink():
        errors.append(f"XP evidence file must not be a symlink: {args.xp_evidence}")
    else:
        errors.extend(check_path_parent_symlinks(args.xp_evidence, "XP evidence file"))
    if args.xp_evidence_dir is None:
        errors.append("--xp-evidence-dir is required for Windows XP evidence")
    else:
        errors.extend(check_directory_path_hint(args.xp_evidence_dir, "XP evidence directory"))
        if not args.xp_evidence_dir.is_dir():
            errors.append(f"XP evidence directory missing: {args.xp_evidence_dir}")
        elif args.xp_evidence_dir.is_symlink():
            errors.append(f"XP evidence directory must not be a symlink: {args.xp_evidence_dir}")
        else:
            errors.extend(check_path_parent_symlinks(args.xp_evidence_dir, "XP evidence directory"))
    if args.workflow_run_url:
        errors.append("--workflow-run-url is only valid for Linux evidence")
    if args.runner_label:
        errors.append("--runner-label is only valid for Linux evidence")
    release_source_workflow_run_url = getattr(args, "release_source_workflow_run_url", None)
    if not release_source_workflow_run_url:
        errors.append("--release-source-workflow-run-url is required for Windows XP evidence")
    elif not GITHUB_ACTIONS_RUN_RE.fullmatch(str(release_source_workflow_run_url).rstrip("/")):
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
    release_match = GITHUB_RELEASE_BASE_RE.fullmatch(str(args.release_asset_base_url))
    workflow_match = GITHUB_ACTIONS_RUN_RE.fullmatch(workflow_run_url.rstrip("/"))
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


def check_target_release_scoped_inputs(args: argparse.Namespace) -> list[str]:
    target = str(args.target)
    release_tag = str(args.release_tag)
    errors = check_target_release_path_segments(
        target,
        release_tag,
        args.assets_dir,
        label="artifact directory",
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
    return errors


def check_target_release_path_segments(
    target: str,
    release_tag: str,
    path: Path,
    *,
    label: str,
) -> list[str]:
    segments = {str(part) for part in path.parts if str(part)}
    raw_path = path.as_posix()
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


def check_linux_builder_release_source_binding(args: argparse.Namespace) -> list[str]:
    if args.builder_evidence is None or not args.builder_evidence.is_file():
        return []
    builder_identity = read_json(args.builder_evidence)
    target = str(args.target)
    expected_head_sha = str(args.release_source_head_sha or "").strip()
    actual_head_sha = str(builder_identity.get("source_head_sha", "")).strip()
    errors: list[str] = []
    if actual_head_sha != expected_head_sha:
        errors.append(
            f"{target} builder evidence source_head_sha must match --release-source-head-sha "
            f"{expected_head_sha}, got {actual_head_sha!r}"
        )
    actual_observed_head_sha = str(builder_identity.get("observed_git_head_sha", "")).strip()
    if actual_observed_head_sha != expected_head_sha:
        errors.append(
            f"{target} builder evidence observed_git_head_sha must match --release-source-head-sha "
            f"{expected_head_sha}, got {actual_observed_head_sha!r}"
        )
    if builder_identity.get("git_worktree_clean") is not True:
        errors.append(f"{target} builder evidence git_worktree_clean must be true")
    expected_attempt = args.release_source_run_attempt
    actual_attempt = builder_identity.get("workflow_run_attempt")
    if actual_attempt != expected_attempt:
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
    if source.get("workflow") != expected_workflow:
        errors.append(f"{target} XP evidence release_source.workflow must be {expected_workflow}")
    expected_workflow_run_url = str(args.release_source_workflow_run_url or "").rstrip("/")
    actual_workflow_run_url = str(source.get("workflow_run_url", "")).rstrip("/")
    if actual_workflow_run_url != expected_workflow_run_url:
        errors.append(
            f"{target} XP evidence release_source.workflow_run_url must match "
            f"--release-source-workflow-run-url {expected_workflow_run_url}, got {actual_workflow_run_url!r}"
        )
    expected_head_sha = str(args.release_source_head_sha or "")
    actual_head_sha = str(source.get("head_sha", "")).strip()
    if actual_head_sha != expected_head_sha:
        errors.append(
            f"{target} XP evidence release_source.head_sha must match "
            f"--release-source-head-sha {expected_head_sha}, got {actual_head_sha!r}"
        )
    expected_run_attempt = args.release_source_run_attempt
    actual_run_attempt = source.get("run_attempt")
    if actual_run_attempt != expected_run_attempt:
        errors.append(
            f"{target} XP evidence release_source.run_attempt must match "
            f"--release-source-run-attempt {expected_run_attempt}, got {actual_run_attempt!r}"
        )
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
        ),
        "linux_smoke_evidence_sha256": linux_smoke_evidence_sha256_map(args.linux_smoke_evidence),
        "local_evidence_preflight_command": local_evidence_preflight_command(args),
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
) -> str:
    requirements = promotion_requirements(target, promotion)
    return (
        f"bash {requirements.get('smoke_script', '')} --target {target} "
        f"--workflow-run-url {workflow_run_url} --workflow-run-attempt {workflow_run_attempt} "
        f"--source-head-sha {source_head_sha}"
    )


def release_asset_source(args: argparse.Namespace, target: str, promotion: dict[str, Any]) -> dict[str, Any]:
    if target in LINUX_TARGETS:
        workflow_run_url = str(getattr(args, "release_source_workflow_run_url", None) or args.workflow_run_url)
        artifact_name = str(
            getattr(args, "release_source_artifact_name", None)
            or linux_release_source_artifact_name(target, str(args.release_tag))
        )
    else:
        workflow_run_url = str(getattr(args, "release_source_workflow_run_url", ""))
        artifact_name = str(getattr(args, "release_source_artifact_name", ""))
    return {
        "type": "github-actions-artifact",
        "workflow": release_source_workflow(target),
        "workflow_run_url": workflow_run_url.rstrip("/"),
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
        f"--assets-dir {args.assets_dir.as_posix()}"
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
            smoke_path = evidence_dir / str(raw_file)
            smoke_sources[str(smoke_id)] = {
                "file": str(raw_file).replace("\\", "/"),
                "size_bytes": smoke_path.stat().st_size,
                "sha256": str(smoke_hashes.get(str(smoke_id), "")),
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
    smoke_commands = {
        str(item.get("id", "")): str(item.get("command", ""))
        for item in smoke_results
        if isinstance(item, dict) and str(item.get("id", ""))
    }
    smoke_evidence_files = {
        str(item.get("id", "")): str(item.get("evidence_file", ""))
        for item in smoke_results
        if isinstance(item, dict) and str(item.get("id", ""))
    }
    os_summary = {
        "name": str(os_data.get("name", "")),
        "architecture": str(os_data.get("architecture", "")),
        "service_pack": str(os_data.get("service_pack", "")),
    }
    if str(os_data.get("edition", "")).strip():
        os_summary["edition"] = str(os_data.get("edition", ""))
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
        "smoke_ids": sorted(
            str(item.get("id", ""))
            for item in smoke_results
            if isinstance(item, dict) and str(item.get("id", ""))
        ),
        "smoke_evidence_files": {
            smoke_id: smoke_evidence_files[smoke_id]
            for smoke_id in sorted(smoke_evidence_files)
        },
        "smoke_commands": {smoke_id: smoke_commands[smoke_id] for smoke_id in sorted(smoke_commands)},
    }


def xp_release_source_summary(raw_source: Any) -> dict[str, Any]:
    if not isinstance(raw_source, dict):
        return {}
    return {
        "workflow": str(raw_source.get("workflow", "")),
        "workflow_run_url": str(raw_source.get("workflow_run_url", "")).rstrip("/"),
        "head_sha": str(raw_source.get("head_sha", "")),
        "run_attempt": raw_source.get("run_attempt"),
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
        "target": str(raw_identity.get("target", "")),
        "release_tag": str(raw_identity.get("release_tag", "")),
        "host_label": str(raw_identity.get("host_label", "")),
        "evidence_run_id": str(raw_identity.get("evidence_run_id", "")),
        "observed_at_utc": str(raw_identity.get("observed_at_utc", "")),
        "operator_private_data_redacted": raw_identity.get("operator_private_data_redacted") is True,
        "os": {
            key: str(os_data.get(key, ""))
            for key in ("name", "architecture", "service_pack", "edition")
            if str(os_data.get(key, "")).strip()
        },
        "toolchain": {
            "separate_legacy_toolchain": toolchain.get("separate_legacy_toolchain") is True,
            "current_python_pyqt6_stack": toolchain.get("current_python_pyqt6_stack") is True,
            "description": str(toolchain.get("description", "")),
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
        smoke_id = str(item.get("id", ""))
        evidence_sha = str(item.get("evidence_sha256", ""))
        if smoke_id:
            hashes[smoke_id] = evidence_sha
    return hashes


def linux_smoke_evidence_sha256_map(smoke_evidence: Path) -> dict[str, str]:
    return {"native_smoke": sha256_file(smoke_evidence)}


def append_record_to_registry(record: dict[str, Any], *, registry_path: Path = EVIDENCE_PATH) -> list[str]:
    errors = check_text_output_path(registry_path, "platform verified evidence registry")
    if errors:
        return errors
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
        require_review_bundles=True,
    )
    if errors:
        return errors

    write_text_output(registry_path, json.dumps(updated, indent=2) + "\n")
    return []


def check_text_output_path(path: Path, label: str) -> list[str]:
    parent = path.parent
    if parent.is_symlink():
        return [f"{label} directory must not be a symlink: {parent}"]
    parent_errors = check_path_parent_symlinks(parent, f"{label} directory")
    if parent_errors:
        return parent_errors
    if parent.exists() and not parent.is_dir():
        return [f"{label} directory must be a directory: {parent}"]
    if path.is_symlink():
        return [f"{label} must not be a symlink: {path}"]
    if path.exists() and not path.is_file():
        return [f"{label} must be a regular file: {path}"]
    return []


def write_text_output(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


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

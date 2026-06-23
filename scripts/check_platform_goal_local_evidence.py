from __future__ import annotations

import argparse
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
    read_json,
)
from check_platform_verified_evidence import (  # noqa: E402
    LINUX_TARGETS,
    PROTECTED_GOAL_TARGETS,
    XP_TARGETS,
    check_linux_builder_identity,
    directory_path_has_file_suffix,
)
from check_xp_native_evidence import (  # noqa: E402
    artifact_validation_asset_dirs,
    check_xp_native_evidence,
)
from make_platform_verified_evidence_record import (  # noqa: E402
    PROMOTION_PATH,
    artifact_sha256_map,
    check_linux_smoke_evidence_file,
    linux_native_smoke_command,
)

RELEASE_TAG_RE = re.compile(r"^v\d+\.\d+\.\d+$")
GITHUB_ACTIONS_RUN_RE = re.compile(r"^https://github\.com/[^/]+/[^/]+/actions/runs/\d+/?$")
GITHUB_HEAD_SHA_RE = re.compile(r"^[0-9a-f]{40}$")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    targets = tuple(args.target or PROTECTED_GOAL_TARGETS)
    errors = check_platform_goal_local_evidence(
        root=args.root,
        release_tag=args.release_tag,
        targets=targets,
        linux_workflow_run_url=args.linux_workflow_run_url,
        linux_source_head_sha=args.linux_source_head_sha,
        strict_artifacts=not args.allow_extra_artifacts,
        assets_dir=args.assets_dir,
        linux_builder_evidence=args.linux_builder_evidence,
        linux_smoke_evidence=args.linux_smoke_evidence,
        xp_evidence=args.xp_evidence,
        xp_evidence_dir=args.xp_evidence_dir,
    )
    if errors:
        for error in errors:
            print(f"platform goal local evidence: {error}", file=sys.stderr)
        return 1
    print(f"platform goal local evidence checks passed: {', '.join(targets)}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Preflight staged local proof for protected platform promotion before "
            "generating accepted evidence records."
        )
    )
    parser.add_argument(
        "--root",
        type=Path,
        required=True,
        help=(
            "staging root containing <target>/<release-tag>/artifacts plus "
            "Linux builder/smoke evidence or XP evidence files"
        ),
    )
    parser.add_argument("--release-tag", required=True, help="release tag, for example v1.0.2")
    parser.add_argument(
        "--target",
        action="append",
        choices=PROTECTED_GOAL_TARGETS,
        help="protected target to check; repeat or omit for all four targets",
    )
    parser.add_argument(
        "--linux-workflow-run-url",
        help=(
            "GitHub Actions run URL that Linux builder and smoke evidence must bind; "
            "omitted values are inferred from each target's builder identity JSON"
        ),
    )
    parser.add_argument(
        "--linux-source-head-sha",
        help=(
            "40-character source commit SHA that Linux builder evidence must bind; "
            "omitted values are inferred from each target's builder identity JSON"
        ),
    )
    parser.add_argument(
        "--allow-extra-artifacts",
        action="store_true",
        help="allow files outside the exact required artifact set in each artifacts directory",
    )
    parser.add_argument(
        "--assets-dir",
        type=Path,
        help="explicit artifact directory for a single --target preflight",
    )
    parser.add_argument(
        "--linux-builder-evidence",
        type=Path,
        help="explicit Linux builder identity JSON for a single Linux --target preflight",
    )
    parser.add_argument(
        "--linux-smoke-evidence",
        type=Path,
        help="explicit Linux native smoke log for a single Linux --target preflight",
    )
    parser.add_argument(
        "--xp-evidence",
        type=Path,
        help="explicit XP evidence JSON for a single XP --target preflight",
    )
    parser.add_argument(
        "--xp-evidence-dir",
        type=Path,
        help="explicit XP smoke evidence directory for a single XP --target preflight",
    )
    return parser.parse_args(argv)


def check_platform_goal_local_evidence(
    *,
    root: Path,
    release_tag: str,
    targets: tuple[str, ...] = PROTECTED_GOAL_TARGETS,
    linux_workflow_run_url: str | None = None,
    linux_source_head_sha: str | None = None,
    strict_artifacts: bool = True,
    assets_dir: Path | None = None,
    linux_builder_evidence: Path | None = None,
    linux_smoke_evidence: Path | None = None,
    xp_evidence: Path | None = None,
    xp_evidence_dir: Path | None = None,
) -> list[str]:
    errors: list[str] = []
    if not RELEASE_TAG_RE.fullmatch(release_tag):
        errors.append(f"release_tag must look like vX.Y.Z: {release_tag}")
    errors.extend(check_directory_path_hint(root, "local evidence root"))
    if errors:
        return errors
    if root.is_symlink():
        errors.append(f"local evidence root must not be a symlink: {root}")
        return errors
    root_parent_errors = check_path_parent_symlinks(root, "local evidence root")
    if root_parent_errors:
        errors.extend(root_parent_errors)
        return errors
    if not root.is_dir():
        errors.append(f"local evidence root missing: {root}")
        return errors
    if any(
        path is not None
        for path in (
            assets_dir,
            linux_builder_evidence,
            linux_smoke_evidence,
            xp_evidence,
            xp_evidence_dir,
        )
    ) and len(targets) != 1:
        errors.append("explicit evidence paths require exactly one --target")
        return errors

    promotion = read_json(PROMOTION_PATH)
    for target in targets:
        if target in LINUX_TARGETS:
            errors.extend(
                check_linux_local_evidence(
                    root=root,
                    release_tag=release_tag,
                    target=target,
                    promotion=promotion,
                    workflow_run_url=linux_workflow_run_url,
                    source_head_sha=linux_source_head_sha,
                    strict_artifacts=strict_artifacts,
                    assets_dir=assets_dir,
                    builder_evidence=linux_builder_evidence,
                    smoke_evidence=linux_smoke_evidence,
                )
            )
        elif target in XP_TARGETS:
            errors.extend(
                check_xp_local_evidence(
                    root=root,
                    release_tag=release_tag,
                    target=target,
                    strict_artifacts=strict_artifacts,
                    assets_dir=assets_dir,
                    evidence_file=xp_evidence,
                    evidence_dir=xp_evidence_dir,
                )
            )
        else:
            errors.append(f"unknown protected target: {target}")
    return errors


def check_linux_local_evidence(
    *,
    root: Path,
    release_tag: str,
    target: str,
    promotion: dict[str, Any],
    workflow_run_url: str | None,
    source_head_sha: str | None,
    strict_artifacts: bool,
    assets_dir: Path | None = None,
    builder_evidence: Path | None = None,
    smoke_evidence: Path | None = None,
) -> list[str]:
    target_dir = root / target
    target_root = target_dir / release_tag
    artifacts_dir = assets_dir or target_root / "artifacts"
    builder_evidence = builder_evidence or target_root / f"builder-identity-{target}.json"
    smoke_evidence = smoke_evidence or target_root / f"native-smoke-{target}.log"
    errors: list[str] = []
    if target_dir.is_symlink():
        errors.append(f"{target} local Linux evidence target directory must not be a symlink: {target_dir}")
    if target_root.is_symlink():
        errors.append(f"{target} local Linux evidence release directory must not be a symlink: {target_root}")
    errors.extend(check_directory_path_hint(artifacts_dir, f"{target} artifact directory"))
    if errors:
        return errors
    errors.extend(check_path_parent_symlinks(artifacts_dir, f"{target} artifact directory"))
    errors.extend(check_path_parent_symlinks(builder_evidence, f"{target} builder identity evidence"))
    errors.extend(check_path_parent_symlinks(smoke_evidence, f"{target} native smoke evidence"))
    errors.extend(check_path_inside_root(root, artifacts_dir, f"{target} artifact directory"))
    errors.extend(check_path_inside_root(root, builder_evidence, f"{target} builder identity evidence"))
    errors.extend(check_path_inside_root(root, smoke_evidence, f"{target} native smoke evidence"))
    errors.extend(check_path_inside_target_root(target_root, artifacts_dir, f"{target} artifact directory"))
    errors.extend(check_path_inside_target_root(target_root, builder_evidence, f"{target} builder identity evidence"))
    errors.extend(check_path_inside_target_root(target_root, smoke_evidence, f"{target} native smoke evidence"))
    if errors:
        return errors
    errors.extend(
        check_platform_promotion_artifacts(
            target=target,
            assets_dir=artifacts_dir,
            tag=release_tag,
            strict=strict_artifacts,
            promotion=promotion,
        )
    )
    infer_linux_bindings = builder_evidence.is_file() and builder_evidence.name == f"builder-identity-{target}.json"
    if not workflow_run_url and not infer_linux_bindings:
        errors.append(f"{target} --linux-workflow-run-url is required for local Linux evidence preflight")
    elif workflow_run_url and not GITHUB_ACTIONS_RUN_RE.fullmatch(str(workflow_run_url).rstrip("/")):
        errors.append(f"{target} --linux-workflow-run-url must be a GitHub Actions run URL")
    if not source_head_sha and not infer_linux_bindings:
        errors.append(f"{target} --linux-source-head-sha is required for local Linux evidence preflight")
    elif source_head_sha and not GITHUB_HEAD_SHA_RE.fullmatch(str(source_head_sha)):
        errors.append(f"{target} --linux-source-head-sha must be a 40-character lowercase Git SHA")
    if builder_evidence.is_symlink():
        errors.append(f"{target} builder identity evidence must not be a symlink: {builder_evidence}")
    elif not builder_evidence.is_file():
        errors.append(f"{target} builder identity evidence missing: {builder_evidence}")
    elif builder_evidence.name != f"builder-identity-{target}.json":
        errors.append(
            f"{target} builder identity evidence file name must be "
            f"builder-identity-{target}.json: {builder_evidence}"
        )
    if smoke_evidence.is_symlink():
        errors.append(f"{target} native smoke evidence must not be a symlink: {smoke_evidence}")
    elif not smoke_evidence.is_file():
        errors.append(f"{target} native smoke evidence missing: {smoke_evidence}")
    elif smoke_evidence.name != f"native-smoke-{target}.log":
        errors.append(
            f"{target} native smoke evidence file name must be "
            f"native-smoke-{target}.log: {smoke_evidence}"
        )
    if errors:
        return errors

    builder_identity = read_json(builder_evidence)
    resolved_workflow_run_url = str(
        workflow_run_url or builder_identity.get("workflow_run_url", "")
        if isinstance(builder_identity, dict)
        else workflow_run_url or ""
    ).strip()
    resolved_source_head_sha = str(
        source_head_sha or builder_identity.get("source_head_sha", "")
        if isinstance(builder_identity, dict)
        else source_head_sha or ""
    ).strip()
    errors.extend(
        check_linux_resolved_run_bindings(
            target,
            workflow_run_url=resolved_workflow_run_url,
            source_head_sha=resolved_source_head_sha,
            inferred_workflow_run_url=not workflow_run_url,
            inferred_source_head_sha=not source_head_sha,
        )
    )
    if errors:
        return errors
    errors.extend(
        check_linux_builder_identity(
            target,
            builder_identity,
            LINUX_TARGETS[target]["machine_names"],
            release_tag=release_tag,
            workflow_run_url=resolved_workflow_run_url,
            source_head_sha=resolved_source_head_sha,
        )
    )
    artifact_hashes = artifact_sha256_map(target, release_tag, artifacts_dir, promotion)
    errors.extend(
        check_linux_smoke_evidence_file(
            target,
            release_tag,
            linux_native_smoke_command(target, promotion, resolved_workflow_run_url, resolved_source_head_sha),
            resolved_workflow_run_url,
            smoke_evidence,
            source_head_sha=resolved_source_head_sha,
            artifact_sha256=artifact_hashes,
        )
    )
    return errors


def check_linux_resolved_run_bindings(
    target: str,
    *,
    workflow_run_url: str,
    source_head_sha: str,
    inferred_workflow_run_url: bool,
    inferred_source_head_sha: bool,
) -> list[str]:
    errors: list[str] = []
    workflow_label = (
        "builder_identity.workflow_run_url"
        if inferred_workflow_run_url
        else "--linux-workflow-run-url"
    )
    source_label = (
        "builder_identity.source_head_sha"
        if inferred_source_head_sha
        else "--linux-source-head-sha"
    )
    if not workflow_run_url:
        errors.append(f"{target} {workflow_label} is required for local Linux evidence preflight")
    elif not GITHUB_ACTIONS_RUN_RE.fullmatch(workflow_run_url.rstrip("/")):
        errors.append(f"{target} {workflow_label} must be a GitHub Actions run URL")
    if not source_head_sha:
        errors.append(f"{target} {source_label} is required for local Linux evidence preflight")
    elif not GITHUB_HEAD_SHA_RE.fullmatch(source_head_sha):
        errors.append(f"{target} {source_label} must be a 40-character lowercase Git SHA")
    return errors


def check_xp_local_evidence(
    *,
    root: Path,
    release_tag: str,
    target: str,
    strict_artifacts: bool,
    assets_dir: Path | None = None,
    evidence_file: Path | None = None,
    evidence_dir: Path | None = None,
) -> list[str]:
    target_dir = root / target
    target_root = target_dir / release_tag
    artifacts_dir = assets_dir or target_root / "artifacts"
    evidence_file = evidence_file or target_root / "xp-evidence.json"
    evidence_dir = evidence_dir or target_root
    errors: list[str] = []
    if target_dir.is_symlink():
        errors.append(f"{target} XP evidence target directory must not be a symlink: {target_dir}")
    if target_root.is_symlink():
        errors.append(f"{target} XP evidence release directory must not be a symlink: {target_root}")
    errors.extend(check_directory_path_hint(artifacts_dir, f"{target} artifact directory"))
    errors.extend(check_directory_path_hint(evidence_dir, f"{target} XP evidence directory"))
    if errors:
        return errors
    errors.extend(check_path_parent_symlinks(artifacts_dir, f"{target} artifact directory"))
    errors.extend(check_path_parent_symlinks(evidence_file, f"{target} XP evidence file"))
    errors.extend(check_path_parent_symlinks(evidence_dir, f"{target} XP evidence directory"))
    errors.extend(check_path_inside_root(root, artifacts_dir, f"{target} artifact directory"))
    errors.extend(check_path_inside_root(root, evidence_file, f"{target} XP evidence file"))
    errors.extend(check_path_inside_root(root, evidence_dir, f"{target} XP evidence directory"))
    if errors:
        return errors
    if evidence_file.is_symlink():
        errors.append(f"{target} XP evidence file must not be a symlink: {evidence_file}")
    if evidence_dir.is_symlink():
        errors.append(f"{target} XP evidence directory must not be a symlink: {evidence_dir}")
    if errors:
        return errors
    errors.extend(check_path_inside_target_root(target_root, artifacts_dir, f"{target} artifact directory"))
    errors.extend(check_path_inside_target_root(target_root, evidence_file, f"{target} XP evidence file"))
    errors.extend(check_path_inside_target_root(target_root, evidence_dir, f"{target} XP evidence directory"))
    if errors:
        return errors
    errors.extend(
        check_platform_promotion_artifacts(
            target=target,
            assets_dir=artifacts_dir,
            tag=release_tag,
            strict=strict_artifacts,
        )
    )
    if not evidence_file.is_file():
        errors.append(f"{target} XP evidence file missing: {evidence_file}")
    if errors:
        return errors
    errors.extend(
        check_xp_native_evidence(
            evidence_file,
            assets_dir=artifacts_dir,
            evidence_dir=evidence_dir,
        )
    )
    evidence = read_json(evidence_file)
    if isinstance(evidence, dict) and evidence.get("release_tag") != release_tag:
        errors.append(
            f"{target} XP evidence release_tag must match --release-tag {release_tag}, "
            f"got {evidence.get('release_tag')!r}"
        )
    if isinstance(evidence, dict):
        asset_dirs = artifact_validation_asset_dirs(evidence)
        expected_assets_dir = local_evidence_path_value(root, artifacts_dir)
        if asset_dirs != [expected_assets_dir]:
            errors.append(
                f"{target} XP evidence artifact_validation.command --assets-dir must match "
                f"local artifacts path {expected_assets_dir}, got {asset_dirs}"
            )
    return errors


def local_evidence_path_value(root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def check_path_inside_root(root: Path, path: Path, label: str) -> list[str]:
    root_resolved = root.resolve(strict=False)
    path_resolved = path.resolve(strict=False)
    try:
        path_resolved.relative_to(root_resolved)
    except ValueError:
        return [f"{label} must stay inside local evidence root: {path}"]
    return []


def check_path_inside_target_root(target_root: Path, path: Path, label: str) -> list[str]:
    target_root_resolved = target_root.resolve(strict=False)
    path_resolved = path.resolve(strict=False)
    target = target_root.name
    release_tag = ""
    root_resolved = target_root_resolved.parent
    if target_root.parent != target_root:
        target = target_root.parent.name
        release_tag = target_root.name
        root_resolved = target_root_resolved.parent.parent
    try:
        relative = path_resolved.relative_to(root_resolved)
    except ValueError:
        return [f"{label} must stay inside local evidence root: {path}"]
    parts = relative.parts
    if target and release_tag:
        for index, part in enumerate(parts[:-1]):
            if part == target and parts[index + 1] == release_tag:
                return []
        return [
            f"{label} must include target/release path segment "
            f"{target}/{release_tag} under local evidence root: {path}"
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


if __name__ == "__main__":
    raise SystemExit(main())

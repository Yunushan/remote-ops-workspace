from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import re
import sys
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = ROOT / "configs" / "release_matrix.json"
EVIDENCE_PATH = ROOT / "configs" / "platform_verified_evidence.json"
MOBAXTERM_EVIDENCE_PATH = ROOT / "configs" / "mobaxterm_parity_evidence.json"
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "release.yml"
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

from check_platform_verified_evidence import (  # noqa: E402
    GITHUB_RELEASE_ASSET_RE,
    GITHUB_REPOSITORY_RE,
    RESERVED_WORKSPACE_ROOTS,
    directory_path_has_file_suffix,
)

EXPECTED_CHECKSUM_SUFFIX = "SHA256SUMS.txt"
XP_NATIVE_EVIDENCE_TARGETS = {"windows-xp-native-x86", "windows-xp-native-x64"}
PLATFORM_GOAL_TARGETS = (
    "linux-i386",
    "linux-armhf",
    "windows-xp-native-x86",
    "windows-xp-native-x64",
)
PUBLISH_PROTECTED_PLATFORM_ASSET_COMMAND = (
    'python scripts/check_protected_platform_goal.py --release-tag "${{ inputs.release_tag }}" '
    '--require-complete --assets-dir release-assets --repository "${{ github.repository }}"'
)
PUBLISH_REMOTE_PLATFORM_EVIDENCE_AUDIT_COMMAND = (
    'python scripts/check_platform_release_evidence_remote.py --repository "${{ github.repository }}" '
    '--release-tag "${{ inputs.release_tag }}" --require-goal-targets --require-source-runs '
    "--require-source-artifact-bytes --require-final-record-bytes "
    "--require-release-asset-bytes --require-tag-source-head"
)
PROTECTED_PUBLISH_JOB = "publish-protected-platform-evidence"
PROTECTED_PROMOTION_INPUT = "include_protected_platform_evidence"
FINAL_ACCEPTED_RECORD_RE = re.compile(
    r"^platform-verified-evidence-(linux-i386|linux-armhf|windows-xp-native-x86|windows-xp-native-x64)-final\.json$"
)
GATED_NATIVE_PATTERNS = {
    "linux-i386": (
        r"remote-ops-workspace-v\d+\.\d+\.\d+-linux-i386\.deb$",
        r"remote-ops-workspace-v\d+\.\d+\.\d+-linux-i686\.",
        r"remote-ops-workspace-v\d+\.\d+\.\d+-linux-i686-native-",
    ),
    "linux-armhf": (
        r"remote-ops-workspace-v\d+\.\d+\.\d+-linux-armhf\.deb$",
        r"remote-ops-workspace-v\d+\.\d+\.\d+-linux-armv7hl\.",
        r"remote-ops-workspace-v\d+\.\d+\.\d+-linux-armhf\.",
        r"remote-ops-workspace-v\d+\.\d+\.\d+-linux-armhf-native-",
    ),
    "windows-xp-native-x86": (
        r"remote-ops-workspace-v\d+\.\d+\.\d+-windows-xp-x86-native",
    ),
    "windows-xp-native-x64": (
        r"remote-ops-workspace-v\d+\.\d+\.\d+-windows-xp-x64-native",
    ),
}


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    strict_errors = strict_platform_goal_arg_errors(args)
    if strict_errors:
        for error in strict_errors:
            print(f"release publish assets: {error}", file=sys.stderr)
        return 2
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    evidence_registry = read_evidence_registry()
    mobaxterm_registry = read_mobaxterm_evidence_registry()
    workflow = WORKFLOW_PATH.read_text(encoding="utf-8")
    errors = check_publish_contract(
        matrix,
        workflow,
        tag=args.tag,
        evidence_registry=evidence_registry,
        mobaxterm_parity_registry=mobaxterm_registry,
        require_platform_goal_targets=args.require_platform_goal_targets,
        require_mobaxterm_parity_complete=args.require_mobaxterm_parity_complete,
    )
    if args.assets_dir is not None:
        errors.extend(
            check_release_assets(
                args.assets_dir,
                matrix,
                tag=args.tag,
                repository=args.repository,
                evidence_registry=evidence_registry,
                mobaxterm_parity_registry=mobaxterm_registry,
                require_platform_goal_targets=args.require_platform_goal_targets,
                require_mobaxterm_parity_complete=args.require_mobaxterm_parity_complete,
            )
        )
    if errors:
        for error in errors:
            print(f"release publish assets: {error}", file=sys.stderr)
        return 1
    print("release publish asset checks passed")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate GitHub release publish asset completeness.")
    parser.add_argument(
        "--assets-dir",
        type=Path,
        help="Downloaded release asset directory to validate before publish.",
    )
    parser.add_argument(
        "--tag",
        help="Expected release tag, for example v1.0.2. Defaults to the matrix release tag.",
    )
    parser.add_argument(
        "--repository",
        help="Expected GitHub release repository in owner/name form, for example owner/repo.",
    )
    parser.add_argument(
        "--require-platform-goal-targets",
        action="store_true",
        help=(
            "fail unless Linux i386, Linux armhf, Windows XP native x86, "
            "and Windows XP native x64 all have accepted platform evidence"
        ),
    )
    parser.add_argument(
        "--require-mobaxterm-parity-complete",
        action="store_true",
        help="fail unless every strict MobaXterm parity article has accepted release evidence",
    )
    return parser.parse_args(argv)


def strict_platform_goal_arg_errors(args: argparse.Namespace) -> list[str]:
    if not args.require_platform_goal_targets:
        return []
    errors: list[str] = []
    if args.assets_dir is None:
        errors.append("--require-platform-goal-targets requires --assets-dir")
    if not args.tag:
        errors.append("--require-platform-goal-targets requires --tag vX.Y.Z")
    return errors


def check_publish_contract(
    matrix: dict[str, Any],
    workflow: str,
    *,
    tag: str | None = None,
    evidence_registry: dict[str, Any] | None = None,
    mobaxterm_parity_registry: dict[str, Any] | None = None,
    require_platform_goal_targets: bool = False,
    require_mobaxterm_parity_complete: bool = False,
) -> list[str]:
    errors: list[str] = []
    release_tag = tag or matrix_tag(matrix)
    expected = expected_release_assets(matrix, tag=release_tag)
    platform_registry = evidence_registry_or_default(evidence_registry)
    errors.extend(
        validate_mobaxterm_parity_registry(
            mobaxterm_parity_registry_or_default(mobaxterm_parity_registry),
            require_complete=require_mobaxterm_parity_complete,
        )
    )
    if require_platform_goal_targets:
        errors.extend(
            validate_platform_goal_evidence_registry(
                platform_registry,
                release_tag=tag or matrix_tag(matrix),
            )
        )
    errors.extend(
        check_gated_native_assets_have_evidence(
            expected,
            evidence_registry=evidence_registry,
            tag=release_tag,
            label="default release matrix",
        )
    )
    if len(expected) < 20:
        errors.append(f"release matrix expected asset set is unexpectedly small: {len(expected)}")
    checksum_assets = [asset for asset in expected if asset.endswith(EXPECTED_CHECKSUM_SUFFIX)]
    if len(checksum_assets) < 6:
        errors.append("release matrix must include source and per-native checksum sidecars")
    errors.extend(check_release_job_clean_checkouts(workflow))
    errors.extend(check_platform_evidence_import_job(workflow))
    errors.extend(check_job_disallows_continue_on_error(workflow, "release-preflight"))
    publish_block = workflow_job_block(workflow, "publish")
    if not publish_block:
        return [*errors, "release workflow missing publish job"]
    errors.extend(check_job_block_disallows_continue_on_error("publish", publish_block))
    required_snippets = {
        "actions/download-artifact@v8": "artifact download",
        "merge-multiple: true": "merged downloaded artifact directory",
        "python scripts/check_release_publish_assets.py --assets-dir release-assets --tag": "publish asset validation",
        '--repository "${{ github.repository }}"': "publish evidence repository binding",
        "softprops/action-gh-release@v3": "GitHub release upload",
        "fail_on_unmatched_files: true": "strict GitHub release upload",
    }
    for snippet, label in required_snippets.items():
        if snippet not in publish_block:
            errors.append(f"publish job missing {label}: {snippet}")
    validate_index = publish_block.find("scripts/check_release_publish_assets.py")
    upload_index = publish_block.find("softprops/action-gh-release")
    if validate_index < 0 or upload_index < 0 or validate_index > upload_index:
        errors.append("publish asset validation must run before GitHub release upload")
    if "--require-platform-goal-targets" in publish_block or PUBLISH_PROTECTED_PLATFORM_ASSET_COMMAND in publish_block:
        errors.append("core publish job must not require protected-platform evidence")
    if "- accepted-platform-evidence-assets" in publish_block:
        errors.append("core publish job must not depend on accepted-platform-evidence-assets")
    errors.extend(check_protected_publish_job(workflow))
    return errors


def check_protected_publish_job(workflow: str) -> list[str]:
    block = workflow_job_block(workflow, PROTECTED_PUBLISH_JOB)
    if not block:
        return [f"release workflow missing {PROTECTED_PUBLISH_JOB} job"]
    errors = check_job_block_disallows_continue_on_error(PROTECTED_PUBLISH_JOB, block)
    errors.extend(check_checkout_step(block, job=PROTECTED_PUBLISH_JOB))
    required_snippets = {
        f"if: ${{{{ inputs.{PROTECTED_PROMOTION_INPUT} }}}}": "opt-in protected promotion condition",
        "- publish": "core release dependency",
        "- accepted-platform-evidence-assets": "accepted platform evidence dependency",
        "actions: read": "Actions metadata read permission for published evidence audit",
        "GH_TOKEN: ${{ github.token }}": "GitHub token for published evidence audit",
        "actions/download-artifact@v8": "artifact download",
        "merge-multiple: true": "merged downloaded artifact directory",
        PUBLISH_PROTECTED_PLATFORM_ASSET_COMMAND: "protected platform release asset gate",
        "python scripts/check_release_publish_assets.py --assets-dir release-assets --tag": "protected publish asset validation",
        "--require-platform-goal-targets": "protected platform goal publish gate",
        PUBLISH_REMOTE_PLATFORM_EVIDENCE_AUDIT_COMMAND: "published protected platform evidence audit",
        "softprops/action-gh-release@v3": "GitHub release upload",
        "fail_on_unmatched_files: true": "strict GitHub release upload",
    }
    for snippet, label in required_snippets.items():
        if snippet not in block:
            errors.append(f"{PROTECTED_PUBLISH_JOB} job missing {label}: {snippet}")
    protected_gate_index = block.find(PUBLISH_PROTECTED_PLATFORM_ASSET_COMMAND)
    validate_index = block.find("scripts/check_release_publish_assets.py")
    upload_index = block.find("softprops/action-gh-release")
    remote_audit_index = block.find(PUBLISH_REMOTE_PLATFORM_EVIDENCE_AUDIT_COMMAND)
    if protected_gate_index < 0 or validate_index < 0 or protected_gate_index > validate_index:
        errors.append("protected platform release asset gate must run before protected publish asset validation")
    if protected_gate_index < 0 or upload_index < 0 or protected_gate_index > upload_index:
        errors.append("protected platform release asset gate must run before protected GitHub release upload")
    if validate_index < 0 or upload_index < 0 or validate_index > upload_index:
        errors.append("protected publish asset validation must run before GitHub release upload")
    if remote_audit_index < 0 or upload_index < 0 or remote_audit_index < upload_index:
        errors.append("published protected platform evidence audit must run after GitHub release upload")
    return errors


def check_release_job_clean_checkouts(workflow: str) -> list[str]:
    errors: list[str] = []
    for job in (
        "release-preflight",
        "source-and-python",
        "windows-native",
        "macos-native",
        "linux-native",
        "accepted-platform-evidence-assets",
        "publish",
        PROTECTED_PUBLISH_JOB,
    ):
        block = workflow_job_block(workflow, job)
        if not block:
            continue
        errors.extend(check_checkout_step(block, job=job))
    return errors


def check_checkout_step(job_block: str, *, job: str) -> list[str]:
    checkout = workflow_step_block(job_block, "uses: actions/checkout@v6")
    if not checkout:
        return [f"{job} job missing repository checkout: uses: actions/checkout@v6"]
    errors: list[str] = []
    if "persist-credentials: false" not in checkout:
        errors.append(f"{job} job missing checkout credential isolation: persist-credentials: false")
    if "clean: true" not in checkout:
        errors.append(f"{job} job missing clean release checkout: clean: true")
    return errors


def check_platform_evidence_import_job(workflow: str) -> list[str]:
    block = workflow_job_block(workflow, "accepted-platform-evidence-assets")
    if not block:
        return ["release workflow missing accepted-platform-evidence-assets job"]
    errors: list[str] = []
    errors.extend(
        check_job_block_disallows_continue_on_error(
            "accepted-platform-evidence-assets",
            block,
        )
    )
    errors.extend(check_checkout_step(block, job="accepted-platform-evidence-assets"))
    required_snippets = {
        "needs: release-preflight": "release preflight dependency",
        f"if: ${{{{ inputs.{PROTECTED_PROMOTION_INPUT} }}}}": "opt-in protected promotion condition",
        "timeout-minutes: 20": "bounded platform evidence import timeout",
        "actions: read": "Actions artifact read permission",
        "contents: read": "read-only repository permission",
        "uses: actions/checkout@v6": "repository checkout",
        "persist-credentials: false": "checkout credential isolation",
        "clean: true": "clean platform evidence import checkout",
        "uses: actions/setup-python@v6": "Python setup",
        "GH_TOKEN: ${{ github.token }}": "GitHub token for gh artifact download",
        "name: Check out immutable release source for evidence binding": (
            "immutable release source checkout"
        ),
        "ref: ${{ inputs.release_tag }}": "immutable release source checkout ref",
        "path: release-source": "immutable release source checkout path",
        "python scripts/import_platform_evidence_artifacts.py --release-tag": "platform evidence artifact importer",
        '--release-head-sha "$(git -C release-source rev-parse HEAD)"': (
            "immutable release source SHA binding"
        ),
        "--require-goal-targets": "strict protected target import",
        "--out-dir release-assets": "release asset import directory",
        "--verify-source-run": "source run metadata verification",
        '--repository "${{ github.repository }}"': "repository-bound accepted evidence import",
        "python scripts/check_platform_review_bundle_artifacts.py --bundle-dir release-assets": (
            "imported platform review bundle validator"
        ),
        "--require-final-record-assets": "imported finalized accepted-record asset validator",
        "actions/upload-artifact@v7": "imported artifact upload",
        "name: release-platform-evidence-assets": "platform evidence release artifact name",
        "path: release-assets/*": "platform evidence release artifact path",
        "if-no-files-found: error": "missing imported asset failure",
        "include-hidden-files: false": "imported asset hidden file exclusion",
        "retention-days: 90": "imported asset retention window",
    }
    for snippet, label in required_snippets.items():
        if snippet not in block:
            errors.append(f"accepted-platform-evidence-assets job missing {label}: {snippet}")
    if "--dry-run" in block:
        errors.append("platform evidence import job must download accepted artifacts, not run with --dry-run")
    import_index = block.find("scripts/import_platform_evidence_artifacts.py")
    review_bundle_index = block.find("scripts/check_platform_review_bundle_artifacts.py")
    upload_index = block.find("actions/upload-artifact@v7")
    if import_index < 0 or upload_index < 0 or import_index > upload_index:
        errors.append("platform evidence import must run before imported artifact upload")
    if review_bundle_index < 0 or upload_index < 0 or review_bundle_index > upload_index:
        errors.append("platform review bundle validation must run before imported artifact upload")
    if import_index >= 0 and review_bundle_index >= 0 and import_index > review_bundle_index:
        errors.append("platform review bundle validation must run after platform evidence import")
    if re.search(r"(?m)^\s+[A-Za-z0-9_-]+:\s+write\s*$", block):
        errors.append("accepted-platform-evidence-assets job must not request write permissions")
    return errors


def check_job_disallows_continue_on_error(workflow: str, job: str) -> list[str]:
    block = workflow_job_block(workflow, job)
    if not block:
        return []
    return check_job_block_disallows_continue_on_error(job, block)


def check_job_block_disallows_continue_on_error(job: str, block: str) -> list[str]:
    if re.search(r"(?im)^\s*continue-on-error:\s*true\s*(?:#.*)?$", block):
        return [f"{job} job must not use continue-on-error: true for protected release gates"]
    return []


def check_release_assets(
    assets_dir: object,
    matrix: dict[str, Any],
    *,
    tag: str | None,
    evidence_registry: dict[str, Any] | None = None,
    mobaxterm_parity_registry: dict[str, Any] | None = None,
    repository: str | None = None,
    require_platform_goal_targets: bool = False,
    require_mobaxterm_parity_complete: bool = False,
) -> list[str]:
    errors: list[str] = []
    errors.extend(check_release_asset_directory(assets_dir))
    if errors:
        return errors
    assert isinstance(assets_dir, Path)
    root = assets_dir.resolve()
    if not root.is_dir():
        return [f"release asset directory missing: {assets_dir}"]
    errors.extend(
        validate_mobaxterm_parity_registry(
            mobaxterm_parity_registry_or_default(mobaxterm_parity_registry),
            require_complete=require_mobaxterm_parity_complete,
        )
    )
    registry = evidence_registry_or_default(evidence_registry)
    if require_platform_goal_targets:
        errors.extend(
            validate_platform_goal_evidence_registry(
                registry,
                release_tag=tag or matrix_tag(matrix),
            )
        )
    release_tag = tag or matrix_tag(matrix)
    expected = expected_release_assets(matrix, tag=release_tag) | accepted_platform_release_assets(
        registry,
        tag=release_tag,
    )
    errors.extend(check_release_asset_symlinks(root))
    errors.extend(check_release_asset_root_entries(root))
    actual = {path.name for path in root.iterdir() if path.is_file()}
    errors.extend(
        check_gated_native_assets_have_evidence(
            actual,
            evidence_registry=registry,
            tag=release_tag,
            label="release asset directory",
        )
    )
    errors.extend(
        check_platform_evidence_asset_hashes(
            root,
            actual,
            tag=release_tag,
            repository=repository,
            evidence_registry=registry,
        )
    )
    errors.extend(
        check_platform_review_bundle_artifacts(
            root,
            tag=release_tag,
            evidence_registry=registry,
        )
    )
    missing = sorted(expected - actual)
    extra = sorted(actual - expected)
    if missing:
        errors.append(f"release assets missing expected files: {missing}")
    if extra:
        errors.append(f"release assets include unexpected files: {extra}")
    errors.extend(check_checksum_sidecars(root, expected))
    errors.extend(check_release_manifest(root, matrix, tag=tag))
    return errors


def check_release_asset_directory(assets_dir: object) -> list[str]:
    path_errors, assets_path = path_arg_value(assets_dir, "release asset directory")
    if path_errors:
        return path_errors
    assert assets_path is not None
    hint_errors = check_directory_path_hint(assets_path, "release asset directory")
    if hint_errors:
        return hint_errors
    reserved_errors = check_path_not_reserved_workspace_root(assets_path, "release asset directory")
    if reserved_errors:
        return reserved_errors
    if assets_path.is_symlink():
        return [f"release asset directory must not be a symlink: {assets_path}"]
    return check_path_parent_symlinks(assets_path, "release asset directory")


def path_arg_value(raw_path: object, label: str) -> tuple[list[str], Path | None]:
    if not isinstance(raw_path, Path):
        return [f"{label} path must be a pathlib.Path, got {raw_path!r}"], None
    return [], raw_path


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


def check_release_asset_symlinks(root: object) -> list[str]:
    path_errors, root_path = path_arg_value(root, "release asset directory")
    if path_errors:
        return path_errors
    assert root_path is not None
    symlinks = sorted(path.name for path in root_path.iterdir() if path.is_symlink())
    if symlinks:
        return [f"release assets must not contain symlinks: {symlinks}"]
    return []


def check_release_asset_root_entries(root: object) -> list[str]:
    path_errors, root_path = path_arg_value(root, "release asset directory")
    if path_errors:
        return path_errors
    assert root_path is not None
    files = [path.name for path in root_path.iterdir() if path.is_file()]
    directories = sorted(path.name for path in root_path.iterdir() if path.is_dir() and not path.is_symlink())
    unsupported = sorted(
        path.name
        for path in root_path.iterdir()
        if not path.is_file() and not path.is_dir() and not path.is_symlink()
    )
    errors: list[str] = []
    errors.extend(check_release_asset_file_names(files))
    if directories:
        errors.append(f"release assets must contain root files only, found directories: {directories}")
    if unsupported:
        errors.append(f"release assets contain unsupported entries: {unsupported}")
    return errors


def check_release_asset_file_names(filenames: list[str]) -> list[str]:
    errors: list[str] = []
    unsafe = sorted({name for name in filenames if not checksum_reference_name_is_safe(name)})
    if unsafe:
        errors.append(f"release asset file names must be exact safe file names: {unsafe}")
    duplicates = sorted({name for name in filenames if filenames.count(name) > 1})
    if duplicates:
        errors.append(f"release asset file names must be unique: {duplicates}")
    case_groups: dict[str, set[str]] = {}
    for name in filenames:
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
            f"release asset file names must not collide on case-insensitive filesystems: {case_collisions}"
        )
    return errors


def check_platform_review_bundle_artifacts(
    root: object,
    *,
    tag: str,
    evidence_registry: dict[str, Any],
) -> list[str]:
    root_errors, root_path = path_arg_value(root, "release asset directory")
    if root_errors:
        return root_errors
    assert root_path is not None
    rows = evidence_registry.get("accepted_evidence", [])
    if not isinstance(rows, list):
        return ["platform verified evidence accepted_evidence must be a list"]
    accepted_rows = [
        row
        for row in rows
        if isinstance(row, dict)
        and row.get("status") == "accepted"
        and row.get("readiness_percent") == 100.0
        and row.get("release_tag") == tag
    ]
    if not accepted_rows:
        return []
    checker = load_platform_review_bundle_artifact_checker()
    scoped_registry = {**evidence_registry, "accepted_evidence": accepted_rows}
    return checker.check_platform_review_bundle_artifacts(
        registry=scoped_registry,
        bundle_dir=root_path,
    )


def check_gated_native_assets_have_evidence(
    assets: set[str],
    *,
    evidence_registry: dict[str, Any] | None = None,
    tag: str,
    label: str,
) -> list[str]:
    accepted = accepted_evidence_targets(
        evidence_registry_or_default(evidence_registry),
        release_tag=tag,
    )
    errors: list[str] = []
    for asset in sorted(assets):
        gated_targets = gated_native_targets_for_asset(asset)
        for target in sorted(gated_targets):
            if target in XP_NATIVE_EVIDENCE_TARGETS:
                missing_xp = sorted(XP_NATIVE_EVIDENCE_TARGETS - accepted)
                if missing_xp:
                    errors.append(
                        f"{label} includes gated Windows XP native asset {asset} but XP native "
                        f"promotion requires accepted evidence for both targets for release_tag {tag}; "
                        f"missing {missing_xp}"
                    )
                continue
            if target not in accepted:
                errors.append(
                    f"{label} includes gated native asset {asset} for {target} "
                    f"without accepted platform evidence for release_tag {tag}"
                )
    return errors


def evidence_registry_or_default(evidence_registry: dict[str, Any] | None) -> dict[str, Any]:
    if evidence_registry is None:
        return read_evidence_registry()
    return evidence_registry


def mobaxterm_parity_registry_or_default(registry: dict[str, Any] | None) -> dict[str, Any]:
    if registry is None:
        return read_mobaxterm_evidence_registry()
    return registry


def gated_native_targets_for_asset(filename: str) -> set[str]:
    targets: set[str] = set()
    for target, patterns in GATED_NATIVE_PATTERNS.items():
        if any(re.search(pattern, filename) for pattern in patterns):
            targets.add(target)
    return targets


def accepted_evidence_targets(
    evidence_registry: dict[str, Any],
    *,
    release_tag: str | None = None,
) -> set[str]:
    if validate_accepted_evidence_registry(evidence_registry):
        return set()
    rows = evidence_registry.get("accepted_evidence", [])
    if not isinstance(rows, list):
        return set()
    return {
        accepted_record_target(item)
        for item in rows
        if isinstance(item, dict)
        and item.get("status") == "accepted"
        and item.get("readiness_percent") == 100.0
        and (release_tag is None or item.get("release_tag") == release_tag)
        and accepted_record_target(item)
    }


def check_platform_evidence_asset_hashes(
    root: object,
    assets: set[str],
    *,
    tag: str,
    repository: str | None = None,
    evidence_registry: dict[str, Any],
) -> list[str]:
    root_errors, root_path = path_arg_value(root, "release asset directory")
    if root_errors:
        return root_errors
    assert root_path is not None
    registry_errors = validate_accepted_evidence_registry(evidence_registry)
    if registry_errors:
        return registry_errors
    rows = evidence_registry.get("accepted_evidence", [])
    if not isinstance(rows, list):
        return ["platform verified evidence accepted_evidence must be a list"]
    repository_errors, expected_repository = normalize_expected_repository(repository)
    accepted = {
        accepted_record_target(item): item
        for item in rows
        if isinstance(item, dict)
        and item.get("status") == "accepted"
        and item.get("readiness_percent") == 100.0
        and item.get("release_tag") == tag
        and accepted_record_target(item)
    }
    errors: list[str] = repository_errors
    for target, record in sorted(accepted.items()):
        if record.get("release_tag") != tag:
            continue
        hashes = record.get("artifact_sha256")
        if not isinstance(hashes, dict):
            errors.append(f"{target} accepted evidence artifact_sha256 must be an object")
            continue
        release_urls = record.get("release_asset_urls")
        if not isinstance(release_urls, list):
            errors.append(f"{target} accepted evidence release_asset_urls must be a list")
            continue
        url_assets: set[str] = set()
        for url in release_urls:
            if not isinstance(url, str):
                errors.append(
                    f"{target} accepted evidence release_asset_urls entries must be strings, "
                    f"got {url!r}"
                )
                continue
            release_url_errors = check_accepted_release_asset_url_scope(
                target,
                url,
                tag,
                repository=expected_repository,
            )
            if release_url_errors:
                errors.extend(release_url_errors)
                continue
            filename = release_asset_url_filename(url)
            if not filename:
                errors.append(
                    f"{target} accepted evidence release_asset_urls file name must be an exact safe file name: {url}"
                )
                continue
            url_assets.add(filename)
        expected_assets: set[str] = set()
        for asset in hashes:
            if not isinstance(asset, str):
                errors.append(
                    f"{target} accepted evidence artifact_sha256 keys must be exact safe file names, "
                    f"got {asset!r}"
                )
                continue
            expected_assets.add(asset)
        if url_assets != expected_assets:
            errors.append(
                f"{target} accepted evidence release_asset_urls must match artifact_sha256 files"
            )
        for asset, expected_sha in sorted(hashes.items(), key=lambda item: repr(item[0])):
            if not isinstance(asset, str):
                continue
            asset_name = asset
            if not lowercase_sha256_hex(expected_sha):
                errors.append(
                    f"{target} accepted evidence artifact_sha256.{asset_name} "
                    "must be a lowercase SHA-256 hex digest"
                )
                continue
            if asset_name not in assets:
                errors.append(
                    f"{target} accepted evidence release asset missing from release directory: "
                    f"{asset_name}"
                )
                continue
            actual_sha = sha256_file(root_path / asset_name)
            if actual_sha != expected_sha:
                errors.append(
                    f"release asset {asset_name} SHA-256 does not match accepted evidence for {target}"
                )
        review_bundle = record.get("review_bundle")
        if not isinstance(review_bundle, dict):
            errors.append(f"{target} accepted evidence review_bundle must be an object")
            continue
        for bundle_key in ("manifest", "archive", "sha256s"):
            bundle_record = review_bundle.get(bundle_key)
            if not isinstance(bundle_record, dict):
                errors.append(f"{target} accepted evidence review_bundle {bundle_key} must be an object")
                continue
            raw_bundle_name = bundle_record.get("file", "")
            if not isinstance(raw_bundle_name, str):
                errors.append(
                    f"{target} accepted evidence review_bundle {bundle_key}.file "
                    f"must be an exact safe file name: {raw_bundle_name!r}"
                )
                continue
            bundle_name = raw_bundle_name
            if not checksum_reference_name_is_safe(bundle_name):
                errors.append(
                    f"{target} accepted evidence review_bundle {bundle_key}.file "
                    f"must be an exact safe file name: {bundle_name!r}"
                )
                continue
            if bundle_name not in assets:
                errors.append(
                    f"{target} accepted evidence review bundle asset missing from release directory: "
                    f"{bundle_name}"
                )
                continue
            bundle_path = root_path / bundle_name
            expected_size = bundle_record.get("size_bytes")
            if (
                bundle_path.is_file()
                and (
                    not isinstance(expected_size, int)
                    or isinstance(expected_size, bool)
                    or expected_size != bundle_path.stat().st_size
                )
            ):
                errors.append(
                    f"release review bundle asset {bundle_name} size does not match accepted evidence for {target}"
                )
            expected_sha = bundle_record.get("sha256", "")
            if not lowercase_sha256_hex(expected_sha):
                errors.append(
                    f"{target} accepted evidence review_bundle {bundle_key}.sha256 "
                    "must be a lowercase SHA-256 hex digest"
                )
                continue
            if bundle_path.is_file() and sha256_file(bundle_path) != expected_sha:
                errors.append(
                    f"release review bundle asset {bundle_name} SHA-256 does not match accepted evidence for {target}"
                )
        final_record_name = accepted_record_source_file(target)
        if final_record_name not in assets:
            errors.append(
                f"{target} accepted evidence finalized record asset missing from release directory: "
                f"{final_record_name}"
            )
        else:
            errors.extend(
                check_final_accepted_record_asset(
                    root_path / final_record_name,
                    target=target,
                    record=record,
                )
            )
    for asset in sorted(assets):
        for target in sorted(gated_native_targets_for_asset(asset)):
            record = accepted.get(target)
            if record is None:
                continue
            hashes = record.get("artifact_sha256")
            if not isinstance(hashes, dict):
                errors.append(f"{target} accepted evidence artifact_sha256 must be an object")
                continue
            expected_sha = hashes.get(asset, "")
            if expected_sha == "":
                errors.append(
                    f"release asset {asset} is gated for {target} but accepted evidence "
                    "artifact_sha256 has no entry"
                )
                continue
            if not lowercase_sha256_hex(expected_sha):
                errors.append(
                    f"{target} accepted evidence artifact_sha256.{asset} "
                    "must be a lowercase SHA-256 hex digest"
                )
                continue
            actual_sha = sha256_file(root_path / asset)
            if actual_sha != expected_sha:
                errors.append(
                    f"release asset {asset} SHA-256 does not match accepted evidence for {target}"
                )
    return errors


def normalize_expected_repository(repository: str | None) -> tuple[list[str], str | None]:
    if repository is None:
        return [], None
    if not isinstance(repository, str):
        return [f"release repository must be a string owner/name value, got {repository!r}"], None
    normalized = repository.strip().strip("/")
    if not normalized:
        return ["release repository must be a non-empty owner/name value"], None
    if not re.fullmatch(GITHUB_REPOSITORY_RE, normalized):
        return [f"release repository must be a GitHub owner/name value, got {repository!r}"], None
    return [], normalized


def check_accepted_release_asset_url_scope(
    target: str,
    url: str,
    tag: str,
    *,
    repository: str | None = None,
) -> list[str]:
    match = GITHUB_RELEASE_ASSET_RE.fullmatch(url)
    if not match:
        return [
            f"{target} accepted evidence release_asset_urls entries must be "
            f"GitHub release asset URLs: {url}"
        ]
    if repository is not None and match.group(1) != repository:
        return [
            f"{target} accepted evidence release_asset_urls repository must match "
            f"release repository {repository}: {url}"
        ]
    if match.group(2) != tag:
        return [
            f"{target} accepted evidence release_asset_urls tag must match "
            f"release tag {tag}: {url}"
        ]
    return []


def accepted_platform_release_assets(evidence_registry: dict[str, Any], *, tag: str) -> set[str]:
    if validate_accepted_evidence_registry(evidence_registry):
        return set()
    rows = evidence_registry.get("accepted_evidence", [])
    if not isinstance(rows, list):
        return set()
    assets: set[str] = set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        if row.get("status") != "accepted" or row.get("readiness_percent") != 100.0:
            continue
        if row.get("release_tag") != tag:
            continue
        for url in row.get("release_asset_urls", []):
            if not isinstance(url, str):
                continue
            filename = release_asset_url_filename(url)
            if filename:
                assets.add(filename)
        hashes = row.get("artifact_sha256")
        if isinstance(hashes, dict):
            assets.update(name for name in hashes if isinstance(name, str))
        review_bundle = row.get("review_bundle")
        if isinstance(review_bundle, dict):
            for bundle_key in ("manifest", "archive", "sha256s"):
                bundle_record = review_bundle.get(bundle_key)
                if isinstance(bundle_record, dict):
                    filename = bundle_record.get("file")
                    if isinstance(filename, str) and checksum_reference_name_is_safe(filename):
                        assets.add(filename)
        target = accepted_record_target(row)
        if target in PLATFORM_GOAL_TARGETS:
            assets.add(accepted_record_source_file(target))
    return assets


def accepted_record_target(record: dict[str, Any]) -> str:
    target = record.get("target")
    return target if isinstance(target, str) else ""


def lowercase_sha256_hex(value: Any) -> bool:
    return isinstance(value, str) and re.fullmatch(r"[0-9a-f]{64}", value) is not None


def accepted_record_source_file(target: str) -> str:
    return f"platform-verified-evidence-{target}-final.json"


def check_final_accepted_record_asset(
    path: object,
    *,
    target: str,
    record: dict[str, Any],
) -> list[str]:
    path_errors, path_value = path_arg_value(
        path,
        f"{target} accepted evidence finalized record asset",
    )
    if path_errors:
        return path_errors
    assert path_value is not None
    if path_value.is_symlink():
        return [f"{target} accepted evidence finalized record asset must not be a symlink: {path_value.name}"]
    if not path_value.is_file():
        return [f"{target} accepted evidence finalized record asset missing from release directory: {path_value.name}"]
    try:
        raw_bytes = path_value.read_bytes()
        data = json.loads(raw_bytes.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        return [f"{target} accepted evidence finalized record asset is not readable JSON: {path_value.name}: {exc}"]
    if not isinstance(data, dict):
        return [f"{target} accepted evidence finalized record asset must contain a JSON object: {path_value.name}"]
    key_errors = public_record_key_errors(target, record)
    if key_errors:
        return key_errors
    if data != public_record(record):
        return [f"{target} accepted evidence finalized record asset must match accepted registry record: {path_value.name}"]
    if raw_bytes != canonical_public_record_bytes(record):
        return [
            f"{target} accepted evidence finalized record asset must use canonical sorted JSON: {path_value.name}"
        ]
    return []


def public_record_key_errors(target: str, record: dict[str, Any]) -> list[str]:
    invalid = [key for key in record if not isinstance(key, str)]
    if invalid:
        return [
            f"{target} accepted evidence finalized registry record keys must be strings, "
            f"got {invalid[0]!r}"
        ]
    return []


def public_record(record: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value
        for key, value in record.items()
        if isinstance(key, str) and not key.startswith("_")
    }


def canonical_public_record_bytes(record: dict[str, Any]) -> bytes:
    return (json.dumps(public_record(record), indent=2, sort_keys=True) + "\n").encode("utf-8")


def validate_accepted_evidence_registry(evidence_registry: dict[str, Any]) -> list[str]:
    module = load_platform_verified_evidence_checker()
    return module.check_platform_verified_evidence(
        registry=evidence_registry,
        require_review_bundles=True,
    )


def validate_platform_goal_evidence_registry(
    evidence_registry: dict[str, Any],
    *,
    release_tag: str,
) -> list[str]:
    module = load_platform_verified_evidence_checker()
    return module.check_platform_verified_evidence(
        registry=evidence_registry,
        required_targets=PLATFORM_GOAL_TARGETS,
        required_release_tag=release_tag,
        require_review_bundles=True,
    )


def load_platform_verified_evidence_checker() -> Any:
    checker_path = ROOT / "scripts" / "check_platform_verified_evidence.py"
    spec = importlib.util.spec_from_file_location("check_platform_verified_evidence", checker_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load platform verified evidence checker")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def load_platform_review_bundle_artifact_checker() -> Any:
    checker_path = ROOT / "scripts" / "check_platform_review_bundle_artifacts.py"
    spec = importlib.util.spec_from_file_location("check_platform_review_bundle_artifacts", checker_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load platform review bundle artifact checker")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def validate_mobaxterm_parity_registry(
    registry: dict[str, Any],
    *,
    require_complete: bool,
) -> list[str]:
    checker_path = ROOT / "scripts" / "check_mobaxterm_parity_evidence.py"
    spec = importlib.util.spec_from_file_location("check_mobaxterm_parity_evidence", checker_path)
    if spec is None or spec.loader is None:
        return ["cannot load MobaXterm parity evidence checker"]
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.check_mobaxterm_parity_evidence(registry=registry, require_complete=require_complete)


def read_evidence_registry() -> dict[str, Any]:
    if not EVIDENCE_PATH.exists():
        return {"schema_version": 1, "accepted_evidence": []}
    try:
        data = json.loads(EVIDENCE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"schema_version": 1, "accepted_evidence": []}
    return data if isinstance(data, dict) else {"schema_version": 1, "accepted_evidence": []}


def read_mobaxterm_evidence_registry() -> dict[str, Any]:
    if not MOBAXTERM_EVIDENCE_PATH.exists():
        return {"schema_version": 1, "policy": "", "accepted_evidence": []}
    try:
        data = json.loads(MOBAXTERM_EVIDENCE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"schema_version": 1, "policy": "", "accepted_evidence": []}
    return data if isinstance(data, dict) else {"schema_version": 1, "policy": "", "accepted_evidence": []}


def expected_release_assets(matrix: dict[str, Any], *, tag: str | None = None) -> set[str]:
    version = version_from_tag(tag or matrix_tag(matrix))
    source = matrix["default_github_release"]["source_and_python"]
    assets = {
        normalize_version(str(item), version)
        for item in [*source["artifacts"], *source["target_bundles"]]
    }
    for job in matrix["default_github_release"]["native_jobs"]:
        for pattern in job["asset_patterns"]:
            for expanded in expand_asset_pattern(str(pattern)):
                assets.add(normalize_version(expanded, version))
    return assets


def check_checksum_sidecars(root: object, expected: set[str]) -> list[str]:
    root_errors, root_path = path_arg_value(root, "release asset directory")
    if root_errors:
        return root_errors
    assert root_path is not None
    errors: list[str] = []
    checksum_files = sorted(asset for asset in expected if asset.endswith(EXPECTED_CHECKSUM_SUFFIX))
    final_record_assets = {asset for asset in expected if FINAL_ACCEPTED_RECORD_RE.fullmatch(asset)}
    expected_references = set(expected - set(checksum_files) - final_record_assets)
    referenced_assets: set[str] = set()
    for checksum_name in checksum_files:
        path = root_path / checksum_name
        if not path.is_file():
            continue
        try:
            lines = [line for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
        except UnicodeDecodeError:
            errors.append(f"{checksum_name} must be UTF-8 text")
            continue
        if not lines:
            errors.append(f"{checksum_name} must contain checksum entries")
            continue
        for line in lines:
            match = re.fullmatch(r"([0-9a-f]{64})\s+(.+)", line.strip())
            if not match:
                errors.append(f"{checksum_name} has invalid checksum line: {line}")
                continue
            raw_reference = match.group(2)
            if not checksum_reference_name_is_safe(raw_reference):
                errors.append(
                    f"{checksum_name} reference must be an exact safe file name: {raw_reference!r}"
                )
                continue
            referenced = raw_reference
            if referenced not in expected:
                errors.append(f"{checksum_name} references unexpected file: {referenced}")
                continue
            referenced_path = root_path / referenced
            if not referenced_path.is_file():
                errors.append(f"{checksum_name} references missing file: {referenced}")
                continue
            if sha256_file(referenced_path) != match.group(1):
                errors.append(f"{checksum_name} checksum mismatch for {referenced}")
                continue
            referenced_assets.add(referenced)
    missing_references = sorted(expected_references - referenced_assets)
    if missing_references:
        errors.append(f"checksum sidecars missing references for expected files: {missing_references}")
    return errors


def checksum_reference_name_is_safe(name: str) -> bool:
    if not name or name.strip() != name or "/" in name or "\\" in name:
        return False
    if name in (".", ".."):
        return False
    windows_path = PureWindowsPath(name)
    posix_path = PurePosixPath(name)
    return not windows_path.drive and not windows_path.is_absolute() and not posix_path.is_absolute()


def release_asset_url_filename(url: str) -> str:
    parts = urlsplit(url)
    if parts.query or parts.fragment:
        return ""
    path_segments = parts.path.split("/")
    if (
        len(path_segments) != 7
        or path_segments[0] != ""
        or path_segments[3:5] != ["releases", "download"]
        or not path_segments[-1]
    ):
        return ""
    filename = unquote(path_segments[-1])
    return filename if checksum_reference_name_is_safe(filename) else ""


def release_manifest_artifact_filename(file_value: Any) -> str:
    if not isinstance(file_value, str) or not file_value or file_value.strip() != file_value or "\\" in file_value:
        return ""
    parts = file_value.split("/")
    if len(parts) == 1:
        filename = parts[0]
    elif len(parts) == 2 and parts[0] == "dist":
        filename = parts[1]
    else:
        return ""
    return filename if checksum_reference_name_is_safe(filename) else ""


def check_release_manifest(root: object, matrix: dict[str, Any], *, tag: str | None) -> list[str]:
    root_errors, root_path = path_arg_value(root, "release asset directory")
    if root_errors:
        return root_errors
    assert root_path is not None
    errors: list[str] = []
    manifests = sorted(root_path.glob("remote-ops-workspace-v*-release-manifest.json"))
    if len(manifests) != 1:
        return [f"expected exactly one release manifest, found {len(manifests)}"]
    manifest_name = manifests[0].name
    try:
        manifest = json.loads(manifests[0].read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        return [f"{manifest_name} is not valid JSON: {exc}"]
    raw_artifacts = manifest.get("artifacts")
    if not isinstance(raw_artifacts, list):
        return [f"{manifest_name} artifacts must be a list"]
    artifact_files = {
        filename
        for item in raw_artifacts
        if isinstance(item, dict)
        for filename in [release_manifest_artifact_filename(item.get("file"))]
        if filename
    }
    source_expected = expected_source_manifest_artifacts(matrix, tag=tag)
    missing = sorted(source_expected - artifact_files)
    if missing:
        errors.append(f"{manifest_name} missing source/Python artifact records: {missing}")
    for item in raw_artifacts:
        if not isinstance(item, dict):
            errors.append(f"{manifest_name} artifact entries must be objects")
            continue
        raw_file = item.get("file")
        filename = release_manifest_artifact_filename(raw_file)
        if not filename:
            errors.append(
                f"{manifest_name} artifact file must be an exact release file name or dist/<file>: {raw_file!r}"
            )
            continue
        if filename not in source_expected:
            errors.append(f"{manifest_name} includes unexpected artifact record: {filename}")
        size_bytes = item.get("size_bytes")
        if not isinstance(size_bytes, int) or isinstance(size_bytes, bool) or size_bytes <= 0:
            errors.append(f"{manifest_name} artifact {filename} missing positive size_bytes")
        digest = item.get("sha256")
        digest_is_valid = isinstance(digest, str) and re.fullmatch(r"[0-9a-f]{64}", digest)
        if not digest_is_valid:
            errors.append(f"{manifest_name} artifact {filename} sha256 must be a lowercase SHA-256 hex digest")
        if filename in source_expected:
            artifact_path = root_path / filename
            if not artifact_path.is_file():
                errors.append(f"{manifest_name} artifact {filename} file missing from release assets")
                continue
            if isinstance(size_bytes, int) and not isinstance(size_bytes, bool) and size_bytes != artifact_path.stat().st_size:
                errors.append(f"{manifest_name} artifact {filename} size_bytes does not match release asset")
            if digest_is_valid and digest != sha256_file(artifact_path):
                errors.append(f"{manifest_name} artifact {filename} sha256 does not match release asset")
    return errors


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


def expected_source_manifest_artifacts(matrix: dict[str, Any], *, tag: str | None = None) -> set[str]:
    version = version_from_tag(tag or matrix_tag(matrix))
    source = matrix["default_github_release"]["source_and_python"]
    return {
        normalize_version(str(item), version)
        for item in [*source["artifacts"], *source["target_bundles"]]
        if not str(item).endswith("-release-manifest.json") and not str(item).endswith(EXPECTED_CHECKSUM_SUFFIX)
    }


def expand_asset_pattern(pattern: str) -> list[str]:
    match = re.search(r"<([^>]+)>", pattern)
    if not match:
        return [pattern]
    choices = match.group(1).split("|")
    return [pattern[: match.start()] + choice + pattern[match.end() :] for choice in choices]


def normalize_version(filename: str, version: str) -> str:
    filename = re.sub(r"remote-ops-workspace-v\d+\.\d+\.\d+", f"remote-ops-workspace-v{version}", filename)
    filename = re.sub(r"remote_ops_workspace-\d+\.\d+\.\d+", f"remote_ops_workspace-{version}", filename)
    return filename


def matrix_tag(matrix: dict[str, Any]) -> str:
    for item in matrix["default_github_release"]["source_and_python"]["artifacts"]:
        match = re.search(r"remote-ops-workspace-(v\d+\.\d+\.\d+)-release-manifest\.json", str(item))
        if match:
            return match.group(1)
    raise ValueError("release matrix does not contain a release manifest tag")


def version_from_tag(tag: str) -> str:
    if not re.fullmatch(r"v\d+\.\d+\.\d+", tag):
        raise ValueError(f"release tag must look like vX.Y.Z: {tag}")
    return tag[1:]


def workflow_job_block(workflow: str, job: str) -> str:
    match = re.search(rf"(?ms)^  {re.escape(job)}:\n(.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)", workflow)
    return match.group(1) if match else ""


def workflow_step_block(job_block: str, marker: str) -> str:
    pattern = rf"(?ms)^      - {re.escape(marker)}\n(.*?)(?=^      - |\Z)"
    match = re.search(pattern, job_block)
    return match.group(0) if match else ""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())

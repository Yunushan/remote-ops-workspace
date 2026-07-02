from __future__ import annotations

import argparse
import re
import sys
from pathlib import PurePosixPath, PureWindowsPath

TARGETS = {"windows-xp-native-x86", "windows-xp-native-x64"}
RESERVED_WORKSPACE_ROOTS = {".agents", ".codex", ".git", ".github"}
FILE_LIKE_DIRECTORY_SUFFIXES = (
    ".appimage",
    ".deb",
    ".exe",
    ".gz",
    ".json",
    ".log",
    ".msi",
    ".rpm",
    ".sha256",
    ".tar",
    ".tgz",
    ".txt",
    ".xz",
    ".zip",
)
GITHUB_OWNER_RE = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?"
GITHUB_REPOSITORY_RE = rf"{GITHUB_OWNER_RE}/[A-Za-z0-9._-]+"
GITHUB_RELEASE_RE = re.compile(
    rf"^https://github\.com/({GITHUB_REPOSITORY_RE})/releases/download/(v\d+\.\d+\.\d+)$"
)
GITHUB_RUN_RE = re.compile(rf"^https://github\.com/({GITHUB_REPOSITORY_RE})/actions/runs/\d+/?$")
RELEASE_TAG_RE = re.compile(r"^v\d+\.\d+\.\d+$")
SOURCE_HEAD_SHA_RE = re.compile(r"^[a-f0-9]{40}$")
PLACEHOLDER_RE = re.compile(r"<[^>]+>|TODO|placeholder|replace with real", re.IGNORECASE)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    errors = check_xp_native_evidence_dispatch_inputs(
        target=args.target,
        release_tag=args.release_tag,
        release_asset_base_url=args.release_asset_base_url,
        workflow_run_url=args.workflow_run_url,
        source_head_sha=args.source_head_sha,
        source_run_attempt=args.source_run_attempt,
        assets_dir=args.assets_dir,
        evidence_file=args.evidence_file,
        evidence_dir=args.evidence_dir,
    )
    if errors:
        for error in errors:
            print(f"XP native evidence dispatch inputs: {error}", file=sys.stderr)
        return 1
    print("XP native evidence dispatch inputs passed")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Validate XP native evidence workflow dispatch inputs before touching staged evidence."
    )
    parser.add_argument("--target", required=True, choices=sorted(TARGETS))
    parser.add_argument("--release-tag", required=True, help="Release tag, for example v1.0.2")
    parser.add_argument(
        "--release-asset-base-url",
        required=True,
        help="Exact GitHub release download base URL: https://github.com/<owner>/<repo>/releases/download/vX.Y.Z",
    )
    parser.add_argument("--workflow-run-url", required=True, help="GitHub Actions run URL for this evidence run")
    parser.add_argument("--source-head-sha", required=True, help="Git commit SHA for this evidence workflow run")
    parser.add_argument(
        "--source-run-attempt",
        required=True,
        help="GitHub Actions run attempt number for this evidence workflow run",
    )
    parser.add_argument(
        "--assets-dir",
        required=True,
        help="workspace-relative XP native artifact directory containing adjacent target/release_tag path segments",
    )
    parser.add_argument(
        "--evidence-file",
        required=True,
        help="workspace-relative XP evidence JSON path containing adjacent target/release_tag path segments",
    )
    parser.add_argument(
        "--evidence-dir",
        required=True,
        help="workspace-relative XP smoke evidence directory containing adjacent target/release_tag path segments",
    )
    return parser.parse_args(argv)


def check_xp_native_evidence_dispatch_inputs(
    *,
    target: str,
    release_tag: str,
    release_asset_base_url: str,
    workflow_run_url: str,
    source_head_sha: str,
    source_run_attempt: object,
    assets_dir: str,
    evidence_file: str,
    evidence_dir: str,
) -> list[str]:
    errors: list[str] = []
    if target not in TARGETS:
        errors.append(f"target must be one of {sorted(TARGETS)}, got {target!r}")
    if not RELEASE_TAG_RE.fullmatch(release_tag):
        errors.append(f"release_tag must look like vX.Y.Z, got {release_tag!r}")
    if not SOURCE_HEAD_SHA_RE.fullmatch(source_head_sha):
        errors.append(f"source_head_sha must be a lowercase 40-character Git SHA, got {source_head_sha!r}")
    if not is_positive_integer_text(source_run_attempt):
        errors.append(f"source_run_attempt must be a positive integer, got {source_run_attempt!r}")

    release_match = GITHUB_RELEASE_RE.fullmatch(release_asset_base_url)
    run_match = GITHUB_RUN_RE.fullmatch(workflow_run_url.rstrip("/"))
    if not release_match:
        errors.append(
            "--release-asset-base-url must be exactly "
            f"https://github.com/<owner>/<repo>/releases/download/{release_tag}"
        )
    elif release_match.group(2) != release_tag:
        errors.append(f"release_asset_base_url tag must match release_tag {release_tag}, got {release_match.group(2)}")
    if not run_match:
        errors.append("--workflow-run-url must be a GitHub Actions run URL")
    if release_match and run_match and release_match.group(1) != run_match.group(1):
        errors.append(
            "release_asset_base_url repository must match workflow_run_url repository "
            f"{run_match.group(1)}, got {release_match.group(1)}"
        )

    scoped_paths = {
        "assets_dir": assets_dir,
        "evidence_file": evidence_file,
        "evidence_dir": evidence_dir,
    }
    errors.extend(check_workspace_relative_path("assets_dir", assets_dir, require_directory_hint=True))
    errors.extend(check_workspace_relative_path("evidence_file", evidence_file, require_json_hint=True))
    errors.extend(check_workspace_relative_path("evidence_dir", evidence_dir, require_directory_hint=True))
    for label, raw_path in scoped_paths.items():
        errors.extend(check_target_release_scoped_path(label, raw_path, target, release_tag))
    return errors


def is_positive_integer_text(value: object) -> bool:
    if isinstance(value, bool):
        return False
    text = str(value).strip()
    return bool(text) and text.isdigit() and int(text) > 0


def check_workspace_relative_path(
    label: str,
    raw_path: str,
    *,
    require_directory_hint: bool = False,
    require_json_hint: bool = False,
) -> list[str]:
    path = raw_path.strip()
    errors: list[str] = []
    if not path:
        return [f"{label} must be set"]
    if PLACEHOLDER_RE.search(path):
        errors.append(f"{label} must be concrete, got {raw_path!r}")
    if any(char in path for char in "*?"):
        errors.append(f"{label} must not contain wildcards, got {raw_path!r}")
    parts, is_absolute = workspace_path_parts(path)
    if is_absolute:
        errors.append(f"{label} must be workspace-relative, got {raw_path!r}")
    if any(part == ".." for part in parts):
        errors.append(f"{label} must not traverse outside the workspace, got {raw_path!r}")
    normalized_parts = tuple(part for part in parts if part not in ("", "."))
    if not normalized_parts:
        errors.append(f"{label} must not point at the workspace root, got {raw_path!r}")
    else:
        reserved_root = normalized_parts[0]
        if reserved_root in RESERVED_WORKSPACE_ROOTS:
            errors.append(f"{label} must not point inside reserved workspace directory {reserved_root!r}")
        hidden_segments = sorted(
            {
                part
                for part in normalized_parts
                if part.startswith(".") and part not in RESERVED_WORKSPACE_ROOTS
            }
        )
        if hidden_segments:
            errors.append(f"{label} must not contain hidden path segments: {hidden_segments}")
    if require_directory_hint and directory_path_has_file_suffix(path):
        errors.append(f"{label} must be a directory path, got {raw_path!r}")
    if require_json_hint and not path.endswith(".json"):
        errors.append(f"{label} must point to an XP evidence JSON file, got {raw_path!r}")
    return errors


def directory_path_has_file_suffix(raw_path: str) -> bool:
    path = raw_path.strip()
    if not path:
        return False
    leaf = PureWindowsPath(path).name if "\\" in path else PurePosixPath(path).name
    leaf = leaf.lower()
    return any(leaf.endswith(suffix) for suffix in FILE_LIKE_DIRECTORY_SUFFIXES)


def check_target_release_scoped_path(
    label: str,
    raw_path: str,
    target: str,
    release_tag: str,
) -> list[str]:
    path = raw_path.strip()
    if not path:
        return []
    parts, _ = workspace_path_parts(path)
    normalized_parts = tuple(part for part in parts if part not in ("", "."))
    errors: list[str] = []
    if target not in normalized_parts:
        errors.append(f"{label} must include target path segment {target!r}, got {raw_path!r}")
    if release_tag not in normalized_parts:
        errors.append(f"{label} must include release_tag path segment {release_tag!r}, got {raw_path!r}")
    if not errors and not has_adjacent_target_release_segments(normalized_parts, target, release_tag):
        errors.append(
            f"{label} must include adjacent target/release path segment "
            f"{target}/{release_tag}, got {raw_path!r}"
        )
    return errors


def has_adjacent_target_release_segments(
    parts: tuple[str, ...],
    target: str,
    release_tag: str,
) -> bool:
    return any(
        part == target and index + 1 < len(parts) and parts[index + 1] == release_tag
        for index, part in enumerate(parts)
    )


def workspace_path_parts(path: str) -> tuple[tuple[str, ...], bool]:
    win_path = PureWindowsPath(path)
    posix_path = PurePosixPath(path)
    win_absolute = win_path.is_absolute() or bool(win_path.drive)
    posix_absolute = posix_path.is_absolute()
    if "\\" in path or win_absolute:
        return win_path.parts, win_absolute or posix_absolute
    return posix_path.parts, win_absolute or posix_absolute


if __name__ == "__main__":
    raise SystemExit(main())

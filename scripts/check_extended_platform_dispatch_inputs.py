from __future__ import annotations

import argparse
import re
import sys

LINUX_TARGETS = {"linux-i386", "linux-armhf"}
RELEASE_TAG_RE = re.compile(r"v\d+\.\d+\.\d+")
GITHUB_OWNER_RE = r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?"
GITHUB_REPOSITORY_RE = rf"{GITHUB_OWNER_RE}/[A-Za-z0-9._-]+"
GITHUB_RELEASE_DOWNLOAD_BASE_RE = re.compile(
    rf"https://github\.com/({GITHUB_REPOSITORY_RE})/releases/download/(v\d+\.\d+\.\d+)"
)
GITHUB_ACTIONS_RUN_RE = re.compile(
    rf"https://github\.com/({GITHUB_REPOSITORY_RE})/actions/runs/\d+/?"
)
SOURCE_HEAD_SHA_RE = re.compile(r"^[a-f0-9]{40}$")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    errors = check_extended_platform_dispatch_inputs(
        target=args.target,
        release_tag=args.release_tag,
        release_asset_base_url=args.release_asset_base_url,
        workflow_run_url=args.workflow_run_url,
        source_head_sha=args.source_head_sha,
        source_run_attempt=args.source_run_attempt,
    )
    if errors:
        for error in errors:
            print(f"extended platform dispatch inputs: {error}", file=sys.stderr)
        return 1
    print(f"extended platform dispatch inputs passed for {args.target}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Validate extended platform evidence workflow dispatch inputs before "
            "spending self-hosted Linux i386/armhf builder time."
        )
    )
    parser.add_argument("--target", required=True, choices=sorted(LINUX_TARGETS))
    parser.add_argument("--release-tag", required=True, help="Release tag, for example v1.0.2")
    parser.add_argument(
        "--release-asset-base-url",
        required=True,
        help="Exact GitHub release download base URL: https://github.com/<owner>/<repo>/releases/download/vX.Y.Z",
    )
    parser.add_argument(
        "--workflow-run-url",
        required=True,
        help="GitHub Actions run URL for this evidence workflow run",
    )
    parser.add_argument("--source-head-sha", required=True, help="Git commit SHA for this evidence workflow run")
    parser.add_argument(
        "--source-run-attempt",
        required=True,
        help="GitHub Actions run attempt number for this evidence workflow run",
    )
    return parser.parse_args(argv)


def check_extended_platform_dispatch_inputs(
    *,
    target: str,
    release_tag: str,
    release_asset_base_url: str,
    workflow_run_url: str,
    source_head_sha: str,
    source_run_attempt: object,
) -> list[str]:
    errors: list[str] = []
    if target not in LINUX_TARGETS:
        errors.append(f"target must be one of {sorted(LINUX_TARGETS)}, got {target!r}")
    if not RELEASE_TAG_RE.fullmatch(release_tag):
        errors.append(f"release_tag must look like vX.Y.Z: {release_tag}")
    if not SOURCE_HEAD_SHA_RE.fullmatch(source_head_sha):
        errors.append(f"source_head_sha must be a lowercase 40-character Git SHA, got {source_head_sha!r}")
    if not is_positive_integer_text(source_run_attempt):
        errors.append(f"source_run_attempt must be a positive integer, got {source_run_attempt!r}")

    release_match = GITHUB_RELEASE_DOWNLOAD_BASE_RE.fullmatch(release_asset_base_url)
    if not release_match:
        errors.append(
            "release_asset_base_url must be exactly "
            f"https://github.com/<owner>/<repo>/releases/download/{release_tag}"
        )
    elif release_match.group(2) != release_tag:
        errors.append(
            "release_asset_base_url tag must match release_tag "
            f"{release_tag}, got {release_match.group(2)}"
        )

    run_match = GITHUB_ACTIONS_RUN_RE.fullmatch(workflow_run_url.rstrip("/"))
    if not run_match:
        errors.append("workflow_run_url must be a GitHub Actions run URL")

    if release_match and run_match and release_match.group(1) != run_match.group(1):
        errors.append(
            "release_asset_base_url repository must match workflow_run_url repository "
            f"{run_match.group(1)}, got {release_match.group(1)}"
        )
    return errors


def is_positive_integer_text(value: object) -> bool:
    if isinstance(value, bool):
        return False
    text = str(value).strip()
    return bool(text) and text.isdigit() and int(text) > 0


if __name__ == "__main__":
    raise SystemExit(main())

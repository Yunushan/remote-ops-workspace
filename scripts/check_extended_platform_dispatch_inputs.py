from __future__ import annotations

import argparse
import re
import sys

LINUX_TARGETS = {"linux-i386", "linux-armhf"}
RELEASE_TAG_RE = re.compile(r"v\d+\.\d+\.\d+")
GITHUB_RELEASE_DOWNLOAD_BASE_RE = re.compile(
    r"https://github\.com/([^/]+/[^/]+)/releases/download/(v\d+\.\d+\.\d+)"
)
GITHUB_ACTIONS_RUN_RE = re.compile(
    r"https://github\.com/([^/]+/[^/]+)/actions/runs/\d+/?"
)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    errors = check_extended_platform_dispatch_inputs(
        target=args.target,
        release_tag=args.release_tag,
        release_asset_base_url=args.release_asset_base_url,
        workflow_run_url=args.workflow_run_url,
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
    return parser.parse_args(argv)


def check_extended_platform_dispatch_inputs(
    *,
    target: str,
    release_tag: str,
    release_asset_base_url: str,
    workflow_run_url: str,
) -> list[str]:
    errors: list[str] = []
    if target not in LINUX_TARGETS:
        errors.append(f"target must be one of {sorted(LINUX_TARGETS)}, got {target!r}")
    if not RELEASE_TAG_RE.fullmatch(release_tag):
        errors.append(f"release_tag must look like vX.Y.Z: {release_tag}")

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


if __name__ == "__main__":
    raise SystemExit(main())

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
        workflow_ref_name=args.workflow_ref_name,
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
    parser.add_argument("--release-tag", required=True, help="Release tag, for example v1.0.13")
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
    parser.add_argument(
        "--workflow-ref-name",
        required=True,
        help="GitHub Actions ref name for this evidence workflow run; must equal --release-tag",
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
    target: object,
    release_tag: object,
    release_asset_base_url: object,
    workflow_run_url: object,
    workflow_ref_name: object,
    source_head_sha: object,
    source_run_attempt: object,
) -> list[str]:
    errors: list[str] = []
    target_value, type_errors = dispatch_string_value("target", target)
    errors.extend(type_errors)
    release_tag_value, type_errors = dispatch_string_value("release_tag", release_tag)
    errors.extend(type_errors)
    release_asset_base_url_value, type_errors = dispatch_string_value(
        "release_asset_base_url",
        release_asset_base_url,
    )
    errors.extend(type_errors)
    workflow_run_url_value, type_errors = dispatch_string_value("workflow_run_url", workflow_run_url)
    errors.extend(type_errors)
    workflow_ref_name_value, type_errors = dispatch_string_value("workflow_ref_name", workflow_ref_name)
    errors.extend(type_errors)
    source_head_sha_value, type_errors = dispatch_string_value("source_head_sha", source_head_sha)
    errors.extend(type_errors)

    if isinstance(target, str) and target_value not in LINUX_TARGETS:
        errors.append(f"target must be one of {sorted(LINUX_TARGETS)}, got {target_value!r}")
    if isinstance(release_tag, str) and not RELEASE_TAG_RE.fullmatch(release_tag_value):
        errors.append(f"release_tag must look like vX.Y.Z: {release_tag_value}")
    if isinstance(source_head_sha, str) and not SOURCE_HEAD_SHA_RE.fullmatch(source_head_sha_value):
        errors.append(f"source_head_sha must be a lowercase 40-character Git SHA, got {source_head_sha_value!r}")
    if not is_positive_integer_text(source_run_attempt):
        errors.append(f"source_run_attempt must be a positive integer, got {source_run_attempt!r}")
    if (
        isinstance(workflow_ref_name, str)
        and isinstance(release_tag, str)
        and workflow_ref_name_value != release_tag_value
    ):
        errors.append(
            "workflow_ref_name must match release_tag so evidence is dispatched from "
            f"the release tag ref, got {workflow_ref_name_value!r}"
        )

    release_match = None
    if isinstance(release_asset_base_url, str):
        release_match = GITHUB_RELEASE_DOWNLOAD_BASE_RE.fullmatch(release_asset_base_url_value)
        if not release_match:
            errors.append(
                "release_asset_base_url must be exactly "
                f"https://github.com/<owner>/<repo>/releases/download/{release_tag_value or '<release-tag>'}"
            )
        elif release_match.group(2) != release_tag_value:
            errors.append(
                "release_asset_base_url tag must match release_tag "
                f"{release_tag_value}, got {release_match.group(2)}"
            )

    run_match = None
    if isinstance(workflow_run_url, str):
        if (
            workflow_run_url_value != workflow_run_url_value.strip()
            or workflow_run_url_value != workflow_run_url_value.rstrip("/")
        ):
            errors.append(
                "workflow_run_url must be canonical without surrounding whitespace or trailing slash"
            )
        else:
            run_match = GITHUB_ACTIONS_RUN_RE.fullmatch(workflow_run_url_value)
        if not run_match:
            errors.append("workflow_run_url must be a GitHub Actions run URL")

    if release_match and run_match and release_match.group(1) != run_match.group(1):
        errors.append(
            "release_asset_base_url repository must match workflow_run_url repository "
            f"{run_match.group(1)}, got {release_match.group(1)}"
        )
    return errors


def dispatch_string_value(label: str, value: object) -> tuple[str, list[str]]:
    if not isinstance(value, str):
        return "", [f"{label} must be a string, got {value!r}"]
    return value, []


def is_positive_integer_text(value: object) -> bool:
    if isinstance(value, bool):
        return False
    text = str(value)
    if text != text.strip():
        return False
    return bool(text) and text.isdigit() and int(text) > 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Verify the live GitHub release carries the generated boundary-aware notes."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

TAG_RE = re.compile(r"^v\d+\.\d+\.\d+$")
REPOSITORY_RE = re.compile(r"^[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+$")
CHANNELS = {"production-signed", "unsigned-preview"}


def check_release_notes(payload: object, *, tag: str, channel: str) -> list[str]:
    """Return contract violations for one GitHub release response."""

    if not isinstance(payload, dict):
        return ["GitHub release response must be a JSON object"]

    errors: list[str] = []
    if payload.get("tag_name") != tag:
        errors.append(f"published release tag must be {tag!r}")
    if payload.get("draft") is not False:
        errors.append("published release must not be a draft")
    expected_prerelease = channel == "unsigned-preview"
    if payload.get("prerelease") is not expected_prerelease:
        errors.append(
            f"published release prerelease flag must be {expected_prerelease!r} for {channel}"
        )

    name = payload.get("name")
    if not isinstance(name, str) or not name.strip():
        errors.append("published release must have a non-empty name")
    elif channel == "unsigned-preview" and "UNSIGNED PREVIEW" not in name:
        errors.append("unsigned preview release name must say UNSIGNED PREVIEW")
    elif channel == "production-signed" and "UNSIGNED PREVIEW" in name:
        errors.append("production-signed release name must not say UNSIGNED PREVIEW")

    body = payload.get("body")
    if not isinstance(body, str) or not body.strip():
        errors.append("published release body must contain boundary-aware release notes")
        return errors

    required_marker = (
        "**Channel: production-signed.**"
        if channel == "production-signed"
        else "**Channel: unsigned preview.**"
    )
    for marker, label in (
        (f"# {tag}", "release tag heading"),
        (required_marker, "release channel marker"),
        ("## Support boundaries", "support-boundary section"),
    ):
        if marker not in body:
            errors.append(f"published release body missing {label}: {marker}")
    return errors


def load_release_json(
    *, repository: str, tag: str, release_json: Path | None, timeout: float
) -> object:
    if release_json is not None:
        return json.loads(release_json.read_text(encoding="utf-8"))

    api_path = f"repos/{repository}/releases/tags/{tag}"
    if shutil.which("gh"):
        try:
            completed = subprocess.run(
                ["gh", "api", api_path],
                check=True,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=os.environ.copy(),
            )
        except subprocess.CalledProcessError as exc:
            detail = exc.stderr.strip() or "no error details"
            raise RuntimeError(f"GitHub CLI could not read {api_path}: {detail}") from exc
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise RuntimeError(f"GitHub CLI could not read {api_path}: {exc}") from exc
        try:
            return json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("GitHub CLI release response must be JSON") from exc

    endpoint = (
        f"https://api.github.com/repos/{repository}/releases/tags/{quote(tag, safe='')}"
    )
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "remote-ops-workspace-release-notes-check",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = Request(endpoint, headers=headers)
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except (HTTPError, URLError, TimeoutError, OSError) as exc:
        raise RuntimeError(f"could not read published GitHub release: {exc}") from exc


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True, help="GitHub repository in owner/name form")
    parser.add_argument("--tag", required=True, help="release tag, for example v1.0.16")
    parser.add_argument("--channel", choices=sorted(CHANNELS), required=True)
    parser.add_argument("--release-json", type=Path, help="offline GitHub release JSON fixture")
    parser.add_argument("--timeout", type=float, default=30.0)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not REPOSITORY_RE.fullmatch(args.repository):
        print("published release notes: repository must be owner/name", file=sys.stderr)
        return 2
    if not TAG_RE.fullmatch(args.tag):
        print("published release notes: tag must be vX.Y.Z", file=sys.stderr)
        return 2
    try:
        payload = load_release_json(
            repository=args.repository,
            tag=args.tag,
            release_json=args.release_json,
            timeout=args.timeout,
        )
    except (OSError, json.JSONDecodeError, RuntimeError) as exc:
        print(f"published release notes: {exc}", file=sys.stderr)
        return 1
    errors = check_release_notes(payload, tag=args.tag, channel=args.channel)
    if errors:
        for error in errors:
            print(f"published release notes: {error}", file=sys.stderr)
        return 1
    print("published release notes passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

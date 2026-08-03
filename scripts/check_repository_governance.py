#!/usr/bin/env python3
"""Audit GitHub branch protection required for a production release.

The repository can validate its own workflow files locally, but branch
protection is remote policy. This check deliberately reads the live GitHub
API (or a supplied response fixture) so the strict production gate cannot
claim governance readiness from documentation alone.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

DEFAULT_BRANCH = "main"
REQUIRED_CHECKS = (
    "Repository policy and lint",
    "CodeQL python",
    "CodeQL javascript-typescript",
)


def normalize_repository(value: str) -> str:
    repository = value.strip().strip("/")
    if repository.count("/") != 1 or any(not part for part in repository.split("/")):
        raise ValueError("repository must be owner/name")
    return repository


def _enabled(payload: Any, key: str) -> bool:
    value = payload.get(key) if isinstance(payload, dict) else None
    return isinstance(value, dict) and value.get("enabled") is True


def _disabled(payload: Any, key: str) -> bool:
    value = payload.get(key) if isinstance(payload, dict) else None
    return isinstance(value, dict) and value.get("enabled") is False


def audit_protection(
    payload: dict[str, Any], required_checks: tuple[str, ...] = REQUIRED_CHECKS
) -> list[str]:
    """Return actionable failures for one GitHub branch-protection response."""

    errors: list[str] = []
    status = payload.get("required_status_checks")
    if not isinstance(status, dict):
        errors.append("required_status_checks must be configured")
    else:
        if status.get("strict") is not True:
            errors.append("required_status_checks.strict must be true")
        contexts = set()
        raw_contexts = status.get("contexts", [])
        if isinstance(raw_contexts, list):
            contexts.update(item for item in raw_contexts if isinstance(item, str))
        raw_checks = status.get("checks", [])
        if isinstance(raw_checks, list):
            contexts.update(
                item.get("context")
                for item in raw_checks
                if isinstance(item, dict) and isinstance(item.get("context"), str)
            )
            contexts.update(
                item.get("name")
                for item in raw_checks
                if isinstance(item, dict) and isinstance(item.get("name"), str)
            )
        for check in required_checks:
            if check not in contexts:
                errors.append(f"required status check missing: {check}")

    reviews = payload.get("required_pull_request_reviews")
    if not isinstance(reviews, dict) or not isinstance(
        reviews.get("required_approving_review_count"), int
    ):
        errors.append("at least one required pull-request approval must be configured")
    elif reviews["required_approving_review_count"] < 1:
        errors.append("required pull-request approval count must be at least 1")

    for key, label in (
        ("enforce_admins", "administrator enforcement"),
        ("required_linear_history", "linear history"),
        ("required_conversation_resolution", "conversation resolution"),
        ("required_signatures", "signed commits"),
    ):
        if not _enabled(payload, key):
            errors.append(f"{label} must be enabled ({key})")
    for key, label in (("allow_force_pushes", "force pushes"), ("allow_deletions", "branch deletion")):
        if not _disabled(payload, key):
            errors.append(f"{label} must be disabled ({key})")
    return errors


def load_fixture(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("protection fixture must contain a JSON object")
    return value


def _fetch_with_gh(gh: str, url: str) -> dict[str, Any]:
    environment = os.environ.copy()
    if not environment.get("GH_TOKEN") and environment.get("GITHUB_TOKEN"):
        environment["GH_TOKEN"] = environment["GITHUB_TOKEN"]
    try:
        completed = subprocess.run(
            [gh, "api", url, "--header", "Accept: application/vnd.github+json"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
            env=environment,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"gh could not read branch protection: {exc}") from exc
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError("GitHub branch-protection response was not JSON") from exc
    if not isinstance(value, dict):
        raise RuntimeError("GitHub branch-protection response must be a JSON object")
    return value


def fetch_protection(repository: str, branch: str) -> dict[str, Any]:
    url = f"https://api.github.com/repos/{repository}/branches/{branch}/protection"
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        request = Request(
            url,
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
            },
        )
        try:
            with urlopen(request, timeout=30) as response:
                value = json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            raise RuntimeError(f"GitHub branch-protection request failed: {exc}") from exc
        except (URLError, TimeoutError) as exc:
            gh = shutil.which("gh")
            if gh is None:
                raise RuntimeError(f"GitHub branch-protection request failed: {exc}") from exc
            value = _fetch_with_gh(gh, url)
    else:
        gh = shutil.which("gh")
        if gh is None:
            raise RuntimeError("set GH_TOKEN/GITHUB_TOKEN or install/authenticate gh to read branch protection")
        value = _fetch_with_gh(gh, url)
    if not isinstance(value, dict):
        raise RuntimeError("GitHub branch-protection response must be a JSON object")
    return value


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", help="GitHub repository in owner/name form")
    parser.add_argument("--branch", default=DEFAULT_BRANCH)
    parser.add_argument("--protection-json", type=Path, help="offline branch-protection response fixture")
    parser.add_argument("--required-check", action="append", dest="required_checks")
    args = parser.parse_args()
    if not args.protection_json and not args.repository:
        parser.error("--repository is required unless --protection-json is provided")
    try:
        repository = normalize_repository(args.repository) if args.repository else "fixture/fixture"
        payload = load_fixture(args.protection_json) if args.protection_json else fetch_protection(repository, args.branch)
        required_checks = tuple(args.required_checks or REQUIRED_CHECKS)
        errors = audit_protection(payload, required_checks)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"repository governance: {exc}", file=sys.stderr)
        return 1
    if errors:
        print("repository governance failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    print(f"repository governance passed: {repository}@{args.branch}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Fail closed on remote GitHub settings that must hold before release mutation."""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urljoin, urlsplit

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
TAG_RE = re.compile(r"v\d+\.\d+\.\d+")
PRODUCTION_BRANCH = "main"
MAX_JSON_BYTES = 20 * 1024 * 1024
MAX_RELEASE_PAGES = 1000


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(  # type: ignore[override]
        self,
        req: urllib.request.Request,
        fp: Any,
        code: int,
        msg: str,
        headers: Any,
        newurl: str,
    ) -> None:
        return None


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    for command in ("immutable", "namespace"):
        child = subparsers.add_parser(command)
        child.add_argument("--repository", required=True)
        child.add_argument("--tag", required=True)
    pre_tag = subparsers.add_parser("pre-tag", help="check the exact production source before creating a tag")
    pre_tag.add_argument("--repository", required=True)
    pre_tag.add_argument("--tag", required=True)
    pre_tag.add_argument("--sha", required=True, help="full commit SHA selected for production")
    args = parser.parse_args(argv)
    try:
        repository = normalize_repository(args.repository)
        tag = normalize_tag(args.tag)
        api_root = normalize_api_root(os.environ.get("GITHUB_API_URL", "https://api.github.com"))
        if args.command == "immutable":
            token = require_token("ROW_RELEASE_IMMUTABILITY_TOKEN")
            require_immutable_enabled(api_root, repository, token)
        elif args.command == "namespace":
            token = require_token("GITHUB_TOKEN")
            require_unused_namespace(api_root, repository, tag, token)
        else:
            if re.fullmatch(r"[0-9a-fA-F]{40}", args.sha) is None:
                raise ValueError("--sha must be a full 40-character commit SHA")
            require_pre_tag(api_root, repository, tag, args.sha.lower())
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as exc:
        print(f"release remote precondition: {exc}", file=sys.stderr)
        return 1
    scope = f" for {repository}@{args.sha.lower()} and {tag}" if args.command == "pre-tag" else ""
    print(f"release remote precondition {args.command} passed{scope}")
    return 0


def require_pre_tag(api_root: str, repository: str, tag: str, sha: str) -> None:
    if api_root != "https://api.github.com":
        raise ValueError("pre-tag checks require the GitHub.com API used by the governance and CI verifiers")
    check_local_pre_tag_refs(tag, sha)
    run_release_check("check_repository_cleanup.py", "--require-clean")
    run_release_check("check_release_version.py", "--release-tag", tag)
    run_release_check("check_release_maturity.py", "--release-tag", tag)
    run_release_check("check_release_license_compliance.py", "--check-policy-only")

    check_remote_pre_tag_refs(repository, tag, sha)
    require_immutable_enabled(api_root, repository, require_token("ROW_RELEASE_IMMUTABILITY_TOKEN"))
    coordinates = ("--repository", repository, "--branch", PRODUCTION_BRANCH)
    run_release_check("check_python315_ci_evidence.py", *coordinates, "--sha", sha)
    run_release_check("check_repository_governance.py", *coordinates, "--sha", sha)
    # This policy-only tag check works before the tag exists. The signed
    # release audit still uses both the tag and its exact SHA together.
    run_release_check("check_repository_governance.py", *coordinates, "--release-tag", tag)
    runner_token = require_token("ROW_PLATFORM_RUNNER_INVENTORY_TOKEN")
    run_release_check(
        "check_platform_evidence_runner_readiness.py", "--repository", repository,
        "--require-goal-targets", "--require-idle", env={**os.environ, "GH_TOKEN": runner_token},
    )
    require_unused_namespace(api_root, repository, tag, require_token("GITHUB_TOKEN"), require_push=True)
    check_remote_pre_tag_refs(repository, tag, sha)
    run_release_check("check_repository_cleanup.py", "--require-clean")
    check_local_pre_tag_refs(tag, sha)


def run_release_check(script: str, *args: str, env: dict[str, str] | None = None) -> None:
    result = subprocess.run([sys.executable, str(ROOT / "scripts" / script), *args], cwd=ROOT, env=env, check=False)
    if result.returncode != 0:
        raise RuntimeError(f"{script} failed with exit code {result.returncode}")


def run_git(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=60, check=False,
        env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
    )


def check_local_pre_tag_refs(tag: str, sha: str) -> None:
    head = run_git("rev-parse", "--verify", "HEAD^{commit}")
    if head.returncode != 0 or head.stdout.strip() != sha:
        raise RuntimeError("the release checkout HEAD must match the selected SHA")
    tag_ref = run_git("show-ref", "--exists", f"refs/tags/{tag}")
    if tag_ref.returncode == 0:
        raise RuntimeError(f"the local tag {tag} already exists")
    if tag_ref.returncode != 2:
        raise RuntimeError(f"could not establish whether local tag {tag} exists")


def check_remote_pre_tag_refs(repository: str, tag: str, sha: str) -> None:
    branch_ref = f"refs/heads/{PRODUCTION_BRANCH}"
    tag_ref = f"refs/tags/{tag}"
    refs = run_git("ls-remote", "--exit-code", "--refs", "--", f"https://github.com/{repository}.git", branch_ref, tag_ref)
    if refs.returncode != 0:
        raise RuntimeError("could not verify the remote branch and release tag refs")
    lines = refs.stdout.splitlines()
    if any(line.endswith(f"\t{tag_ref}") for line in lines):
        raise RuntimeError(f"the remote tag {tag} already exists")
    head = re.fullmatch(rf"([0-9a-f]{{40}})\t{branch_ref}", lines[0]) if len(lines) == 1 else None
    if head is None:
        raise RuntimeError(f"could not identify the live {PRODUCTION_BRANCH} commit")
    if head[1] != sha:
        ancestry = run_git("merge-base", "--is-ancestor", sha, head[1])
        if ancestry.returncode == 1:
            raise RuntimeError(f"the selected release SHA must be on remote {PRODUCTION_BRANCH}")
        if ancestry.returncode != 0:
            raise RuntimeError(f"could not verify remote {PRODUCTION_BRANCH} ancestry from the local checkout")


def normalize_repository(value: str) -> str:
    if REPOSITORY_RE.fullmatch(value) is None:
        raise ValueError("repository must be owner/name")
    return value


def normalize_tag(value: str) -> str:
    if TAG_RE.fullmatch(value) is None:
        raise ValueError("tag must look like vX.Y.Z")
    return value


def normalize_api_root(value: str) -> str:
    parsed = urlsplit(value.rstrip("/"))
    if (
        parsed.scheme != "https"
        or not parsed.hostname
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
    ):
        raise ValueError("GITHUB_API_URL must be a credential-free HTTPS origin/path")
    return value.rstrip("/")


def require_token(name: str) -> str:
    token = os.environ.get(name)
    if not token or "\r" in token or "\n" in token:
        raise ValueError(f"{name} is required and must be a single line")
    return token


def get_json(url: str, token: str, *, api_version: str) -> tuple[Any, Any]:
    request = urllib.request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "User-Agent": "remote-ops-release-preconditions/1",
            "X-GitHub-Api-Version": api_version,
        },
    )
    opener = urllib.request.build_opener(NoRedirect())
    try:
        response = opener.open(request, timeout=60)
    except urllib.error.HTTPError as exc:
        detail = exc.read(2000).decode("utf-8", errors="replace")
        raise RuntimeError(f"GitHub API {url} failed with HTTP {exc.code}: {detail}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"GitHub API {url} failed: {exc.reason}") from exc
    with response:
        if getattr(response, "status", 200) != 200:
            raise RuntimeError(f"GitHub API {url} did not return HTTP 200")
        length = response.headers.get("Content-Length")
        if length is not None and int(length) > MAX_JSON_BYTES:
            raise RuntimeError("GitHub API response exceeds the JSON size limit")
        raw = response.read(MAX_JSON_BYTES + 1)
        headers = response.headers
    if len(raw) > MAX_JSON_BYTES:
        raise RuntimeError("GitHub API response exceeds the JSON size limit")
    return json.loads(raw), headers


def require_immutable_enabled(api_root: str, repository: str, token: str) -> None:
    payload, _ = get_json(
        f"{api_root}/repos/{repository}/immutable-releases",
        token,
        api_version="2026-03-10",
    )
    if not isinstance(payload, dict) or payload.get("enabled") is not True:
        raise RuntimeError("repository immutable releases setting is not enabled")


def require_unused_namespace(
    api_root: str,
    repository: str,
    tag: str,
    token: str,
    *,
    require_push: bool = False,
) -> None:
    repository_url = f"{api_root}/repos/{repository}"
    metadata, _ = get_json(repository_url, token, api_version="2022-11-28")
    if not isinstance(metadata, dict):
        raise RuntimeError("GitHub repository API did not return an object")
    repository_id = metadata.get("id")
    full_name = metadata.get("full_name")
    if (
        not isinstance(full_name, str)
        or full_name.casefold() != repository.casefold()
        or not isinstance(repository_id, int)
        or isinstance(repository_id, bool)
        or repository_id < 1
    ):
        raise RuntimeError("GitHub repository API did not identify the requested repository")
    permissions = metadata.get("permissions")
    if require_push and (not isinstance(permissions, dict) or permissions.get("push") is not True):
        raise RuntimeError("GITHUB_TOKEN must demonstrate repository push access so draft releases are visible")

    base_url = f"{repository_url}/releases"
    # GitHub can return numeric repository paths in pagination links.
    allowed_paths = {
        urlsplit(base_url).path,
        urlsplit(f"{api_root}/repositories/{repository_id}/releases").path,
    }
    url = f"{base_url}?per_page=100"
    for page in range(1, MAX_RELEASE_PAGES + 1):
        payload, headers = get_json(url, token, api_version="2022-11-28")
        if not isinstance(payload, list) or not all(isinstance(item, dict) for item in payload):
            raise RuntimeError("GitHub releases API did not return a list of objects")
        if any(item.get("tag_name") == tag or item.get("name") == tag for item in payload):
            raise RuntimeError(f"a published or draft release already uses tag/name {tag}")
        next_url = next_page_url(
            headers.get("Link"), current=url, allowed_paths=allowed_paths, expected_page=page + 1
        )
        if next_url is None:
            return
        url = next_url
    raise RuntimeError("GitHub release pagination exceeded the safety limit")


def next_page_url(
    value: str | None, *, current: str, allowed_paths: set[str], expected_page: int
) -> str | None:
    if value is None:
        return None
    next_values: list[str] = []
    for item in value.split(","):
        match = re.fullmatch(r'\s*<([^>]+)>\s*;\s*rel="([^"]+)"\s*', item)
        if match is None:
            raise RuntimeError("GitHub releases pagination has an invalid Link header")
        if match.group(2) == "next":
            next_values.append(urljoin(current, match.group(1)))
    if not next_values:
        return None
    if len(next_values) != 1:
        raise RuntimeError("GitHub releases pagination has an invalid next link")
    candidate = next_values[0]
    parsed = urlsplit(candidate)
    expected = urlsplit(current)
    query = parse_qs(parsed.query, keep_blank_values=True)
    if (
        parsed.scheme != "https"
        or parsed.netloc != expected.netloc
        or parsed.path not in allowed_paths
        or parsed.username
        or parsed.password
        or parsed.fragment
        or query != {"page": [str(expected_page)], "per_page": ["100"]}
    ):
        raise RuntimeError("GitHub releases pagination left the expected HTTPS endpoint or page")
    return candidate


if __name__ == "__main__":
    raise SystemExit(main())

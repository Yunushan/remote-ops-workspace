#!/usr/bin/env python3
"""Fail closed on remote GitHub settings that must hold before release mutation."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import parse_qs, urljoin, urlsplit

REPOSITORY_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
TAG_RE = re.compile(r"v\d+\.\d+\.\d+")
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
    args = parser.parse_args(argv)
    try:
        repository = normalize_repository(args.repository)
        tag = normalize_tag(args.tag)
        api_root = normalize_api_root(os.environ.get("GITHUB_API_URL", "https://api.github.com"))
        if args.command == "immutable":
            token = require_token("ROW_RELEASE_IMMUTABILITY_TOKEN")
            require_immutable_enabled(api_root, repository, token)
        else:
            token = require_token("GITHUB_TOKEN")
            require_unused_namespace(api_root, repository, tag, token)
    except (OSError, RuntimeError, ValueError, json.JSONDecodeError) as exc:
        print(f"release remote precondition: {exc}", file=sys.stderr)
        return 1
    print(f"release remote precondition {args.command} passed")
    return 0


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

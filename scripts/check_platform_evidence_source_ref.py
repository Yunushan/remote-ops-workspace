from __future__ import annotations

import argparse
import base64
import json
import os
import re
import ssl
import sys
from collections.abc import Callable, Sequence
from typing import Any
from urllib.error import HTTPError
from urllib.parse import quote
from urllib.request import Request, urlopen

GOAL_TARGETS = (
    "linux-i386",
    "linux-armhf",
    "windows-xp-native-x86",
    "windows-xp-native-x64",
)
TARGET_WORKFLOWS = {
    "linux-i386": ".github/workflows/extended-platform-evidence.yml",
    "linux-armhf": ".github/workflows/extended-platform-evidence.yml",
    "windows-xp-native-x86": ".github/workflows/xp-native-evidence.yml",
    "windows-xp-native-x64": ".github/workflows/xp-native-evidence.yml",
}
REPOSITORY_RE = re.compile(
    r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?/[A-Za-z0-9._-]+$"
)
RELEASE_TAG_RE = re.compile(r"^v(\d+)\.(\d+)\.(\d+)$")
LOWER_GIT_SHA_RE = re.compile(r"^[0-9a-f]{40}$")
PROJECT_VERSION_RE = re.compile(
    r"(?ms)^\[project\]\s*$.*?^version\s*=\s*['\"]([^'\"]+)['\"]\s*$"
)
ApiFetcher = Callable[[str], dict[str, Any]]


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    targets = selected_targets(args.target, require_goal_targets=args.require_goal_targets)
    report, errors = check_platform_evidence_source_ref(
        repository=args.repository,
        release_tag=args.release_tag,
        targets=targets,
        fetcher=GitHubApiFetcher(
            repository=args.repository,
            timeout=args.timeout,
        ),
    )
    if args.json:
        print(json.dumps({**report, "errors": errors}, indent=2, sort_keys=True))
    elif errors:
        for error in errors:
            print(f"platform evidence source ref: {error}", file=sys.stderr)
    else:
        workflows = ", ".join(report["workflow_files"])
        print(
            "platform evidence source ref ready: "
            f"{args.repository}@{args.release_tag} -> {report['source_head_sha']}; "
            f"targets={len(targets)}/{len(targets)}; workflows={workflows}"
        )
    return 1 if errors else 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Fail before protected-platform workflow dispatch when the release tag does "
            "not resolve to a commit containing the required evidence workflows."
        )
    )
    parser.add_argument("--repository", required=True, help="GitHub repository as owner/name")
    parser.add_argument("--release-tag", required=True, help="Release tag, for example v1.0.3")
    parser.add_argument(
        "--target",
        action="append",
        choices=GOAL_TARGETS,
        help="Protected target to inspect; repeat for more than one target",
    )
    parser.add_argument(
        "--require-goal-targets",
        action="store_true",
        help="Require all four protected platform targets",
    )
    parser.add_argument("--timeout", type=float, default=20.0, help="GitHub API timeout in seconds")
    parser.add_argument("--json", action="store_true", help="Emit a machine-readable report")
    args = parser.parse_args(argv)
    if not args.require_goal_targets and not args.target:
        parser.error("pass --require-goal-targets or at least one --target")
    if args.timeout <= 0:
        parser.error("--timeout must be greater than zero")
    return args


def selected_targets(raw_targets: Sequence[str] | None, *, require_goal_targets: bool) -> tuple[str, ...]:
    if require_goal_targets:
        return GOAL_TARGETS
    return tuple(dict.fromkeys(raw_targets or ()))


def check_platform_evidence_source_ref(
    *,
    repository: object,
    release_tag: object,
    targets: Sequence[object],
    fetcher: ApiFetcher,
) -> tuple[dict[str, Any], list[str]]:
    report: dict[str, Any] = {
        "repository": repository,
        "release_tag": release_tag,
        "source_head_sha": None,
        "targets": list(targets),
        "workflow_files": [],
        "workflow_blob_shas": {},
        "project_version": None,
        "ready": False,
    }
    errors = validate_inputs(repository=repository, release_tag=release_tag, targets=targets)
    if errors:
        return report, errors
    assert isinstance(repository, str)
    assert isinstance(release_tag, str)
    target_values = tuple(str(target) for target in targets)

    source_head_sha, resolve_errors = resolve_tag_commit(fetcher, release_tag)
    errors.extend(resolve_errors)
    report["source_head_sha"] = source_head_sha

    pyproject, fetch_errors = fetch_tagged_file(fetcher, release_tag, "pyproject.toml")
    errors.extend(fetch_errors)
    if pyproject is not None:
        version_match = PROJECT_VERSION_RE.search(pyproject)
        if version_match is None:
            errors.append(f"{release_tag} pyproject.toml does not define [project].version")
        else:
            project_version = version_match.group(1)
            report["project_version"] = project_version
            expected_version = release_tag.removeprefix("v")
            if project_version != expected_version:
                errors.append(
                    f"{release_tag} pyproject.toml version must be {expected_version}, "
                    f"got {project_version!r}"
                )

    workflow_targets: dict[str, list[str]] = {}
    for target in target_values:
        workflow_targets.setdefault(TARGET_WORKFLOWS[target], []).append(target)
    report["workflow_files"] = sorted(workflow_targets)
    for workflow_path, expected_targets in sorted(workflow_targets.items()):
        workflow_text, workflow_errors, blob_sha = fetch_tagged_workflow(
            fetcher,
            release_tag,
            workflow_path,
        )
        errors.extend(workflow_errors)
        if blob_sha:
            report["workflow_blob_shas"][workflow_path] = blob_sha
        if workflow_text is None:
            continue
        if "workflow_dispatch:" not in workflow_text:
            errors.append(
                f"{release_tag} workflow {workflow_path} does not declare workflow_dispatch"
            )
        for target in expected_targets:
            if re.search(rf"(?m)^\s*-\s+{re.escape(target)}\s*$", workflow_text) is None:
                errors.append(
                    f"{release_tag} workflow {workflow_path} does not expose target {target}"
                )

    report["ready"] = not errors
    return report, errors


def validate_inputs(
    *, repository: object, release_tag: object, targets: Sequence[object]
) -> list[str]:
    errors: list[str] = []
    if not isinstance(repository, str):
        errors.append(f"repository must be a string, got {repository!r}")
    elif repository != repository.strip() or REPOSITORY_RE.fullmatch(repository) is None:
        errors.append(f"repository must be a canonical GitHub owner/name slug, got {repository!r}")
    if not isinstance(release_tag, str):
        errors.append(f"release_tag must be a string, got {release_tag!r}")
    elif release_tag != release_tag.strip() or RELEASE_TAG_RE.fullmatch(release_tag) is None:
        errors.append(f"release_tag must look like vX.Y.Z, got {release_tag!r}")
    if not targets:
        errors.append("at least one protected target is required")
    seen: set[str] = set()
    for target in targets:
        if not isinstance(target, str):
            errors.append(f"target must be a string, got {target!r}")
            continue
        if target not in TARGET_WORKFLOWS:
            errors.append(f"target must be one of {list(GOAL_TARGETS)}, got {target!r}")
        if target in seen:
            errors.append(f"target must not be repeated: {target}")
        seen.add(target)
    return errors


def resolve_tag_commit(fetcher: ApiFetcher, release_tag: str) -> tuple[str | None, list[str]]:
    endpoint = f"git/ref/tags/{quote(release_tag, safe='')}"
    try:
        ref = fetcher(endpoint)
    except Exception as exc:
        return None, [fetch_failure(endpoint, exc, release_tag=release_tag)]
    current = ref.get("object")
    if not isinstance(current, dict):
        return None, [f"{release_tag} Git ref response does not contain an object"]
    visited: set[str] = set()
    for _ in range(8):
        object_type = current.get("type")
        object_sha = current.get("sha")
        if not isinstance(object_sha, str) or LOWER_GIT_SHA_RE.fullmatch(object_sha) is None:
            return None, [f"{release_tag} Git ref object has invalid SHA {object_sha!r}"]
        if object_type == "commit":
            return object_sha, []
        if object_type != "tag":
            return None, [f"{release_tag} Git ref must resolve to a commit, got {object_type!r}"]
        if object_sha in visited:
            return None, [f"{release_tag} annotated tag chain contains a cycle at {object_sha}"]
        visited.add(object_sha)
        tag_endpoint = f"git/tags/{object_sha}"
        try:
            tag_object = fetcher(tag_endpoint)
        except Exception as exc:
            return None, [fetch_failure(tag_endpoint, exc, release_tag=release_tag)]
        current = tag_object.get("object")
        if not isinstance(current, dict):
            return None, [f"{release_tag} annotated tag {object_sha} does not contain an object"]
    return None, [f"{release_tag} annotated tag chain exceeds 8 objects"]


def fetch_tagged_workflow(
    fetcher: ApiFetcher,
    release_tag: str,
    workflow_path: str,
) -> tuple[str | None, list[str], str | None]:
    text, errors, blob_sha = fetch_tagged_file_with_sha(fetcher, release_tag, workflow_path)
    if errors and any("was not found" in error for error in errors):
        return (
            None,
            [
                f"{release_tag} does not contain required workflow {workflow_path}; "
                "create a new release tag from a commit containing the workflow before dispatch"
            ],
            None,
        )
    return text, errors, blob_sha


def fetch_tagged_file(
    fetcher: ApiFetcher,
    release_tag: str,
    path: str,
) -> tuple[str | None, list[str]]:
    text, errors, _ = fetch_tagged_file_with_sha(fetcher, release_tag, path)
    return text, errors


def fetch_tagged_file_with_sha(
    fetcher: ApiFetcher,
    release_tag: str,
    path: str,
) -> tuple[str | None, list[str], str | None]:
    endpoint = f"contents/{quote(path, safe='/')}?ref={quote(release_tag, safe='')}"
    try:
        payload = fetcher(endpoint)
    except Exception as exc:
        return None, [fetch_failure(endpoint, exc, release_tag=release_tag, path=path)], None
    if payload.get("type") != "file":
        return None, [f"{release_tag} path {path} must be a file"], None
    blob_sha = payload.get("sha")
    if not isinstance(blob_sha, str) or LOWER_GIT_SHA_RE.fullmatch(blob_sha) is None:
        return None, [f"{release_tag} file {path} has invalid blob SHA {blob_sha!r}"], None
    if payload.get("encoding") != "base64" or not isinstance(payload.get("content"), str):
        return None, [f"{release_tag} file {path} must include base64 GitHub content"], None
    try:
        encoded = "".join(payload["content"].split())
        raw = base64.b64decode(encoded, validate=True)
        return raw.decode("utf-8"), [], blob_sha
    except (ValueError, UnicodeDecodeError) as exc:
        return None, [f"{release_tag} file {path} content is invalid: {exc}"], None


def fetch_failure(
    endpoint: str,
    exc: Exception,
    *,
    release_tag: str,
    path: str | None = None,
) -> str:
    if isinstance(exc, HTTPError) and exc.code == 404:
        if path is not None:
            return f"{release_tag} path {path} was not found"
        return f"release tag {release_tag} was not found"
    message = f"failed to fetch GitHub API endpoint {endpoint}: {exc}"
    if isinstance(exc, HTTPError) and exc.code == 403:
        remaining = exc.headers.get("x-ratelimit-remaining") if exc.headers else None
        if remaining == "0" or "rate limit" in str(exc).casefold():
            message += "; set GH_TOKEN or GITHUB_TOKEN with contents:read access or wait for reset"
    return message


class GitHubApiFetcher:
    def __init__(self, *, repository: str, timeout: float) -> None:
        self.repository = repository
        self.timeout = timeout
        self.ssl_context = verified_ssl_context()

    def __call__(self, endpoint: str) -> dict[str, Any]:
        url = f"https://api.github.com/repos/{self.repository}/{endpoint}"
        request = Request(url, headers=github_api_headers())
        with urlopen(request, timeout=self.timeout, context=self.ssl_context) as response:
            payload = json.loads(response.read().decode("utf-8"))
        if not isinstance(payload, dict):
            raise ValueError(f"GitHub API response must be an object: {endpoint}")
        return payload


def verified_ssl_context() -> ssl.SSLContext:
    try:
        import truststore
    except ImportError:
        pass
    else:
        return truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    try:
        import certifi
    except ImportError:
        return ssl.create_default_context()
    return ssl.create_default_context(cafile=certifi.where())


def github_api_headers() -> dict[str, str]:
    headers = {
        "Accept": "application/vnd.github+json",
        "User-Agent": "remote-ops-workspace-platform-evidence-source-ref",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


if __name__ == "__main__":
    raise SystemExit(main())

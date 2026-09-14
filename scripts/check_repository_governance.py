#!/usr/bin/env python3
"""Audit GitHub branch, check-workflow, and release-tag production policy.

The repository can validate its own workflow files locally, but branch
protection, check ownership, workflow-run identity, and tag rulesets are remote
policy. This check deliberately reads the live GitHub API (or supplied response
fixtures) so the strict production gate cannot claim governance readiness from
documentation or spoofable check names alone.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from collections.abc import Mapping
from fnmatch import fnmatchcase
from pathlib import Path
from typing import Any, cast
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode, urlsplit
from urllib.request import Request, urlopen

DEFAULT_BRANCH = "main"
REQUIRED_CHECKS = (
    "Repository policy and lint",
    "Python 3.15 readiness",
    "Native Windows readiness",
    "CodeQL python",
    "CodeQL javascript-typescript",
)
GITHUB_ACTIONS_APP_ID = 15368
GITHUB_ACTIONS_APP_SLUG = "github-actions"
REQUIRED_CHECK_IDENTITIES: dict[str, dict[str, Any]] = {
    "Repository policy and lint": {
        "app_id": GITHUB_ACTIONS_APP_ID,
        "app_slug": GITHUB_ACTIONS_APP_SLUG,
        "workflow_path": ".github/workflows/ci.yml",
    },
    "Python 3.15 readiness": {
        "app_id": GITHUB_ACTIONS_APP_ID,
        "app_slug": GITHUB_ACTIONS_APP_SLUG,
        "workflow_path": ".github/workflows/ci.yml",
    },
    "Native Windows readiness": {
        "app_id": GITHUB_ACTIONS_APP_ID,
        "app_slug": GITHUB_ACTIONS_APP_SLUG,
        "workflow_path": ".github/workflows/ci.yml",
    },
    "CodeQL python": {
        "app_id": GITHUB_ACTIONS_APP_ID,
        "app_slug": GITHUB_ACTIONS_APP_SLUG,
        "workflow_path": ".github/workflows/codeql.yml",
    },
    "CodeQL javascript-typescript": {
        "app_id": GITHUB_ACTIONS_APP_ID,
        "app_slug": GITHUB_ACTIONS_APP_SLUG,
        "workflow_path": ".github/workflows/codeql.yml",
    },
}


def normalize_repository(value: str) -> str:
    repository = value.strip().strip("/")
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) is None:
        raise ValueError("repository must be owner/name")
    return repository


def normalize_sha(value: str) -> str:
    sha = value.strip()
    if re.fullmatch(r"[0-9a-fA-F]{40}", sha) is None:
        raise ValueError("sha must be a full 40-character hexadecimal commit id")
    return sha.lower()


def normalize_release_tag(value: str) -> str:
    tag = value.strip()
    if re.fullmatch(r"v\d+\.\d+\.\d+", tag) is None:
        raise ValueError("release tag must look like vX.Y.Z")
    return tag


def _identity_for(
    check: str,
    required_check_identities: Mapping[str, Mapping[str, Any]] | None,
) -> Mapping[str, Any] | None:
    identities = required_check_identities or REQUIRED_CHECK_IDENTITIES
    identity = identities.get(check)
    return identity if isinstance(identity, Mapping) else None


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _app_matches(value: Any, identity: Mapping[str, Any]) -> bool:
    return (
        isinstance(value, dict)
        and value.get("id") == identity.get("app_id")
        and value.get("slug") == identity.get("app_slug")
    )


def _enabled(payload: Any, key: str) -> bool:
    value = payload.get(key) if isinstance(payload, dict) else None
    return isinstance(value, dict) and value.get("enabled") is True


def _disabled(payload: Any, key: str) -> bool:
    value = payload.get(key) if isinstance(payload, dict) else None
    return isinstance(value, dict) and value.get("enabled") is False


def audit_protection(
    payload: dict[str, Any],
    required_checks: tuple[str, ...] = REQUIRED_CHECKS,
    *,
    require_review: bool = False,
    require_signed_commits: bool = False,
    required_check_identities: Mapping[str, Mapping[str, Any]] | None = None,
) -> list[str]:
    """Return actionable failures for one GitHub branch-protection response.

    Pull-request approvals and signed commits are intentionally optional by
    default.  This matches repositories that use status checks and linear
    history as their merge controls, while the two ``require_*`` switches keep
    the stricter production policy available for release audits.
    """

    errors: list[str] = []
    status = payload.get("required_status_checks")
    if not isinstance(status, dict):
        errors.append("required_status_checks must be configured")
    else:
        if status.get("strict") is not True:
            errors.append("required_status_checks.strict must be true")
        contexts: set[str] = set()
        raw_contexts = status.get("contexts", [])
        if isinstance(raw_contexts, list):
            contexts.update(item for item in raw_contexts if isinstance(item, str))
        raw_checks = status.get("checks", [])
        configured_checks: list[dict[str, Any]] = []
        if isinstance(raw_checks, list):
            configured_checks = [item for item in raw_checks if isinstance(item, dict)]
            for item in configured_checks:
                for key in ("context", "name"):
                    value = item.get(key)
                    if isinstance(value, str):
                        contexts.add(value)
        for check in required_checks:
            if check not in contexts:
                errors.append(f"required status check missing: {check}")
                continue
            identity = _identity_for(check, required_check_identities)
            if identity is None:
                errors.append(f"required status check has no trusted app/workflow identity: {check}")
                continue
            expected_app_id = identity.get("app_id")
            expected_slug = identity.get("app_slug")
            if not _positive_int(expected_app_id) or not isinstance(expected_slug, str) or not expected_slug:
                errors.append(f"required status check identity is invalid: {check}")
                continue
            matches = [
                item
                for item in configured_checks
                if item.get("context") == check or item.get("name") == check
            ]
            if len(matches) != 1:
                errors.append(
                    f"required status check {check} must have exactly one GitHub App binding; "
                    f"found {len(matches)}"
                )
                continue
            if matches[0].get("app_id") != expected_app_id:
                errors.append(
                    f"required status check {check} must be bound to app_id "
                    f"{expected_app_id} ({expected_slug}), got {matches[0].get('app_id')!r}"
                )

    if require_review:
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
    ):
        if not _enabled(payload, key):
            errors.append(f"{label} must be enabled ({key})")
    if require_signed_commits and not _enabled(payload, "required_signatures"):
        errors.append("signed commits must be enabled (required_signatures)")
    for key, label in (("allow_force_pushes", "force pushes"), ("allow_deletions", "branch deletion")):
        if not _disabled(payload, key):
            errors.append(f"{label} must be disabled ({key})")
    return errors


def _complete_evidence_rows(
    payload: dict[str, Any] | None,
    *,
    key: str,
    label: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    if not isinstance(payload, dict):
        return [], [f"{label} evidence is required"]
    raw_rows = payload.get(key)
    if not isinstance(raw_rows, list) or not all(isinstance(item, dict) for item in raw_rows):
        return [], [f"{label} response must contain {key}"]
    total_count = payload.get("total_count")
    if not isinstance(total_count, int) or isinstance(total_count, bool) or total_count < 0:
        return [], [f"{label} response must contain a non-negative integer total_count"]
    if total_count != len(raw_rows):
        return [], [
            f"{label} response is incomplete or inconsistent: "
            f"total_count={total_count}, received={len(raw_rows)}"
        ]
    rows = [item for item in raw_rows if isinstance(item, dict)]
    if any(not _positive_int(item.get("id")) for item in rows):
        return [], [f"{label} ids must be positive integers"]
    ids = [int(item["id"]) for item in rows]
    if len(ids) != len(set(ids)):
        return [], [f"{label} ids must be unique"]
    return rows, []


def _actions_run_id(details_url: Any, repository: str | None) -> int | None:
    if not isinstance(details_url, str) or not repository:
        return None
    parsed = urlsplit(details_url)
    if parsed.scheme != "https" or parsed.netloc.casefold() != "github.com":
        return None
    if parsed.query or parsed.fragment:
        return None
    parts = [part for part in parsed.path.split("/") if part]
    expected_repository = repository.split("/", 1)
    if len(parts) != 7 or [part.casefold() for part in parts[:2]] != [
        part.casefold() for part in expected_repository
    ]:
        return None
    if parts[2:4] != ["actions", "runs"] or parts[5] != "job":
        return None
    if not parts[4].isdigit() or int(parts[4]) <= 0 or not parts[6].isdigit():
        return None
    if int(parts[6]) <= 0:
        return None
    return int(parts[4])


def _repository_name(value: Any) -> str | None:
    if not isinstance(value, dict):
        return None
    full_name = value.get("full_name")
    return full_name if isinstance(full_name, str) else None


def _workflow_path_matches(value: Any, expected_path: str, branch: str) -> bool:
    if value == expected_path:
        return True
    if not isinstance(value, str) or not value.startswith(f"{expected_path}@"):
        return False
    source_ref = value.removeprefix(f"{expected_path}@")
    return source_ref in {branch, f"refs/heads/{branch}"}


def audit_check_runs(
    payload: dict[str, Any],
    sha: str,
    required_checks: tuple[str, ...] = REQUIRED_CHECKS,
    *,
    required_check_identities: Mapping[str, Mapping[str, Any]] | None = None,
    check_suites_payload: dict[str, Any] | None = None,
    workflow_runs_payload: dict[str, Any] | None = None,
    repository: str | None = None,
    branch: str = DEFAULT_BRANCH,
) -> list[str]:
    """Require app-, suite-, workflow-, and exact-SHA-bound check evidence.

    The positional API remains compatible with the original checker.  The new
    keyword evidence is mandatory for a successful audit so a same-name check
    created by another GitHub App cannot satisfy the production gate.
    """

    raw_runs = payload.get("check_runs")
    if not isinstance(raw_runs, list):
        return ["check-runs response must contain check_runs"]
    total_count = payload.get("total_count")
    if not isinstance(total_count, int) or isinstance(total_count, bool) or total_count < 0:
        return ["check-runs response must contain a non-negative integer total_count"]
    # The live request intentionally asks for one 100-item page. Refuse to
    # certify a truncated response instead of treating unseen checks as green.
    if total_count != len(raw_runs):
        return [
            "check-runs response is incomplete or inconsistent: "
            f"total_count={total_count}, received={len(raw_runs)}"
        ]

    suites, suite_errors = _complete_evidence_rows(
        check_suites_payload,
        key="check_suites",
        label="check-suites",
    )
    workflows, workflow_errors = _complete_evidence_rows(
        workflow_runs_payload,
        key="workflow_runs",
        label="workflow-runs",
    )
    errors: list[str] = [*suite_errors, *workflow_errors]
    suite_by_id = {int(item["id"]): item for item in suites}
    workflow_by_id = {int(item["id"]): item for item in workflows}
    expected_sha = sha.lower()

    for check in required_checks:
        identity = _identity_for(check, required_check_identities)
        if identity is None:
            errors.append(f"required check run has no trusted app/workflow identity: {check}")
            continue
        expected_app_id = identity.get("app_id")
        expected_slug = identity.get("app_slug")
        expected_workflow = identity.get("workflow_path")
        if (
            not _positive_int(expected_app_id)
            or not isinstance(expected_slug, str)
            or not expected_slug
            or not isinstance(expected_workflow, str)
            or not expected_workflow.startswith(".github/workflows/")
        ):
            errors.append(f"required check run identity is invalid: {check}")
            continue
        candidates = [
            run
            for run in raw_runs
            if isinstance(run, dict) and run.get("name") == check
        ]
        if not candidates:
            errors.append(f"required check run missing for SHA {sha}: {check}")
            continue
        authentic = [run for run in candidates if _app_matches(run.get("app"), identity)]
        if not authentic:
            observed_slugs: set[str] = set()
            for run in candidates:
                app = run.get("app")
                slug = app.get("slug") if isinstance(app, dict) else None
                if isinstance(slug, str):
                    observed_slugs.add(slug)
            observed = sorted(observed_slugs)
            errors.append(
                f"required check run {check} must come from app_id {expected_app_id} "
                f"({expected_slug}); observed apps={observed}"
            )
            continue
        if any(not _positive_int(run.get("id")) for run in authentic):
            errors.append(f"required check run ids must be positive integers: {check}")
            continue
        latest = max(authentic, key=lambda run: cast(int, run["id"]))
        actual_sha = latest.get("head_sha")
        if not isinstance(actual_sha, str) or actual_sha.lower() != expected_sha:
            errors.append(
                f"required check run {check} is not bound to SHA {sha}: "
                f"got {actual_sha!r}"
            )
        if latest.get("status") != "completed":
            errors.append(
                f"required check run {check} status must be completed, "
                f"got {latest.get('status')!r}"
            )
        if latest.get("conclusion") != "success":
            errors.append(
                f"required check run {check} conclusion must be success, "
                f"got {latest.get('conclusion')!r}"
            )

        suite_ref = latest.get("check_suite")
        suite_id = suite_ref.get("id") if isinstance(suite_ref, dict) else None
        if not _positive_int(suite_id):
            errors.append(f"required check run {check} has no valid check_suite.id")
            continue
        suite = suite_by_id.get(cast(int, suite_id))
        if suite is None:
            errors.append(f"required check run {check} check suite {suite_id} is missing")
        else:
            if not _app_matches(suite.get("app"), identity):
                errors.append(
                    f"required check run {check} check suite {suite_id} is not owned by "
                    f"app_id {expected_app_id} ({expected_slug})"
                )
            suite_sha = suite.get("head_sha")
            if not isinstance(suite_sha, str) or suite_sha.lower() != expected_sha:
                errors.append(
                    f"required check run {check} check suite {suite_id} is not bound to SHA {sha}"
                )

        actions_run_id = _actions_run_id(latest.get("details_url"), repository)
        if actions_run_id is None:
            errors.append(
                f"required check run {check} details_url is not a repository GitHub Actions job"
            )
            continue
        workflow = workflow_by_id.get(actions_run_id)
        if workflow is None:
            errors.append(
                f"required check run {check} GitHub Actions run {actions_run_id} is missing"
            )
            continue
        expected_repository = repository.casefold() if repository else None
        workflow_head_sha = workflow.get("head_sha")
        checks = {
            "check_suite_id": (workflow.get("check_suite_id"), suite_id),
            "head_sha": (
                workflow_head_sha.lower()
                if isinstance(workflow_head_sha, str)
                else workflow_head_sha,
                expected_sha,
            ),
            "head_branch": (workflow.get("head_branch"), branch),
            "event": (workflow.get("event"), "push"),
            "status": (workflow.get("status"), "completed"),
            "conclusion": (workflow.get("conclusion"), "success"),
        }
        for field, (actual, expected) in checks.items():
            if actual != expected:
                errors.append(
                    f"required check run {check} workflow run {actions_run_id} {field} "
                    f"must be {expected!r}, got {actual!r}"
                )
        workflow_path = workflow.get("path")
        if not _workflow_path_matches(workflow_path, expected_workflow, branch):
            errors.append(
                f"required check run {check} workflow run {actions_run_id} path must identify "
                f"{expected_workflow!r} on {branch!r}, got {workflow_path!r}"
            )
        for field in ("repository", "head_repository"):
            actual_repository = _repository_name(workflow.get(field))
            if expected_repository is None or (
                not isinstance(actual_repository, str)
                or actual_repository.casefold() != expected_repository
            ):
                errors.append(
                    f"required check run {check} workflow run {actions_run_id} {field} "
                    f"must be {repository!r}, got {actual_repository!r}"
                )
    return errors


def _ref_pattern_matches(pattern: Any, ref: str) -> bool:
    if pattern == "~ALL":
        return True
    if not isinstance(pattern, str) or not pattern:
        return False
    pattern_parts = pattern.split("/")
    ref_parts = ref.split("/")
    if "**" in pattern_parts:
        # GitHub rulesets use fnmatch syntax; a complete ** segment is the only
        # form permitted here to cross a ref-name slash.
        expression = "^" + re.escape(pattern) + "$"
        expression = expression.replace(r"\*\*", ".*")
        expression = expression.replace(r"\*", "[^/]*").replace(r"\?", "[^/]")
        return re.fullmatch(expression, ref) is not None
    if len(pattern_parts) != len(ref_parts):
        return False
    return all(
        fnmatchcase(value, expected)
        for value, expected in zip(ref_parts, pattern_parts, strict=True)
    )


def _ruleset_applies_to_tag(value: dict[str, Any], tag: str) -> bool:
    if value.get("target") != "tag" or value.get("enforcement") != "active":
        return False
    conditions = value.get("conditions")
    ref_name = conditions.get("ref_name") if isinstance(conditions, dict) else None
    if not isinstance(ref_name, dict):
        return False
    include = ref_name.get("include")
    exclude = ref_name.get("exclude")
    if not isinstance(include, list) or not include or not isinstance(exclude, list):
        return False
    ref = f"refs/tags/{tag}"
    return any(_ref_pattern_matches(pattern, ref) for pattern in include) and not any(
        _ref_pattern_matches(pattern, ref) for pattern in exclude
    )


def audit_tag_rulesets(payload: Any, tag: str) -> list[str]:
    """Require non-bypassable update/deletion protection for one release tag."""

    raw_rulesets = payload.get("rulesets") if isinstance(payload, dict) else payload
    if not isinstance(raw_rulesets, list) or not all(
        isinstance(item, dict) for item in raw_rulesets
    ):
        return ["tag-rulesets response must contain a rulesets list"]
    if isinstance(payload, dict) and "total_count" in payload:
        total_count = payload.get("total_count")
        if (
            not isinstance(total_count, int)
            or isinstance(total_count, bool)
            or total_count != len(raw_rulesets)
        ):
            return [
                "tag-rulesets response is incomplete or inconsistent: "
                f"total_count={total_count!r}, received={len(raw_rulesets)}"
            ]

    applicable = [item for item in raw_rulesets if _ruleset_applies_to_tag(item, tag)]
    if not applicable:
        return [f"no active tag ruleset applies to refs/tags/{tag}"]

    missing_bypass_visibility = [
        item for item in applicable if "bypass_actors" not in item
    ]
    strict = [item for item in applicable if item.get("bypass_actors") == []]
    if not strict:
        if missing_bypass_visibility:
            return [
                "cannot prove release-tag immutability because applicable ruleset "
                "bypass_actors are hidden; use a token with ruleset write visibility"
            ]
        return [
            f"every active tag ruleset applying to refs/tags/{tag} has bypass actors"
        ]

    protected_operations = {
        rule.get("type")
        for ruleset in strict
        for rule in ruleset.get("rules", [])
        if isinstance(rule, dict)
    }
    errors: list[str] = []
    if "update" not in protected_operations:
        errors.append(f"release tag refs/tags/{tag} is not protected against updates")
    if "deletion" not in protected_operations:
        errors.append(f"release tag refs/tags/{tag} is not protected against deletion")
    return errors


def load_fixture(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict):
        raise ValueError("protection fixture must contain a JSON object")
    return value


def load_rulesets_fixture(path: Path) -> dict[str, Any] | list[Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, (dict, list)):
        raise ValueError("tag-rulesets fixture must contain a JSON object or array")
    return value


def _fetch_with_gh_json(gh: str, url: str, *, label: str) -> Any:
    parsed = urlsplit(url)
    endpoint = url
    if parsed.netloc == "api.github.com" and parsed.path:
        endpoint = parsed.path.lstrip("/")
        if parsed.query:
            endpoint = f"{endpoint}?{parsed.query}"
    environment = os.environ.copy()
    if not environment.get("GH_TOKEN") and environment.get("GITHUB_TOKEN"):
        environment["GH_TOKEN"] = environment["GITHUB_TOKEN"]
    try:
        completed = subprocess.run(
            [gh, "api", endpoint, "--header", "Accept: application/vnd.github+json"],
            check=True,
            capture_output=True,
            text=True,
            timeout=30,
            env=environment,
        )
    except (OSError, subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError(f"gh could not read {label}: {exc}") from exc
    try:
        value = json.loads(completed.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"GitHub {label} response was not JSON") from exc
    return value


def _fetch_with_gh(gh: str, url: str, *, label: str) -> dict[str, Any]:
    value = _fetch_with_gh_json(gh, url, label=label)
    if not isinstance(value, dict):
        raise RuntimeError(f"GitHub {label} response must be a JSON object")
    return value


def _fetch_github_json(url: str, *, label: str) -> Any:
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
            raise RuntimeError(f"GitHub {label} request failed: {exc}") from exc
        except (URLError, TimeoutError) as exc:
            gh = shutil.which("gh")
            if gh is None:
                raise RuntimeError(f"GitHub {label} request failed: {exc}") from exc
            value = _fetch_with_gh_json(gh, url, label=label)
    else:
        gh = shutil.which("gh")
        if gh is None:
            raise RuntimeError(
                f"set GH_TOKEN/GITHUB_TOKEN or install/authenticate gh to read {label}"
            )
        value = _fetch_with_gh_json(gh, url, label=label)
    return value


def _fetch_github_object(url: str, *, label: str) -> dict[str, Any]:
    value = _fetch_github_json(url, label=label)
    if not isinstance(value, dict):
        raise RuntimeError(f"GitHub {label} response must be a JSON object")
    return value


def _fetch_github_list(url: str, *, label: str) -> list[Any]:
    value = _fetch_github_json(url, label=label)
    if not isinstance(value, list):
        raise RuntimeError(f"GitHub {label} response must be a JSON array")
    return value


def fetch_protection(repository: str, branch: str) -> dict[str, Any]:
    url = (
        f"https://api.github.com/repos/{repository}/branches/"
        f"{quote(branch, safe='')}/protection"
    )
    return _fetch_github_object(url, label="branch-protection")


def fetch_check_runs(repository: str, sha: str) -> dict[str, Any]:
    query = urlencode({"filter": "latest", "per_page": 100})
    url = (
        f"https://api.github.com/repos/{repository}/commits/{quote(sha, safe='')}/check-runs?{query}"
    )
    return _fetch_github_object(url, label="check-runs")


def fetch_check_suites(repository: str, sha: str) -> dict[str, Any]:
    query = urlencode({"per_page": 100})
    url = (
        f"https://api.github.com/repos/{repository}/commits/{quote(sha, safe='')}/check-suites?{query}"
    )
    return _fetch_github_object(url, label="check-suites")


def fetch_workflow_runs(repository: str, sha: str, branch: str) -> dict[str, Any]:
    query = urlencode(
        {
            "branch": branch,
            "event": "push",
            "head_sha": sha,
            "per_page": 100,
        }
    )
    url = f"https://api.github.com/repos/{repository}/actions/runs?{query}"
    return _fetch_github_object(url, label="workflow-runs")


def fetch_tag_rulesets(repository: str) -> dict[str, Any]:
    summaries: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    page = 1
    while True:
        if page > 100:
            raise RuntimeError("GitHub tag-rulesets pagination exceeded 100 pages")
        query = urlencode(
            {
                "includes_parents": "true",
                "targets": "tag",
                "per_page": 100,
                "page": page,
            }
        )
        url = f"https://api.github.com/repos/{repository}/rulesets?{query}"
        raw_page = _fetch_github_list(url, label=f"tag-rulesets page {page}")
        for item in raw_page:
            if not isinstance(item, dict) or not _positive_int(item.get("id")):
                raise RuntimeError("GitHub tag-rulesets response contains an invalid ruleset id")
            ruleset_id = int(item["id"])
            if ruleset_id in seen_ids:
                raise RuntimeError(f"GitHub tag-rulesets response repeats ruleset id {ruleset_id}")
            seen_ids.add(ruleset_id)
            summaries.append(item)
        if len(raw_page) < 100:
            break
        page += 1

    details: list[dict[str, Any]] = []
    for item in summaries:
        ruleset_id = int(item["id"])
        query = urlencode({"includes_parents": "true"})
        url = f"https://api.github.com/repos/{repository}/rulesets/{ruleset_id}?{query}"
        details.append(_fetch_github_object(url, label=f"tag-ruleset {ruleset_id}"))
    return {"total_count": len(details), "rulesets": details}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", help="GitHub repository in owner/name form")
    parser.add_argument("--branch", default=DEFAULT_BRANCH)
    parser.add_argument("--protection-json", type=Path, help="offline branch-protection response fixture")
    parser.add_argument("--sha", help="exact release commit whose required check runs must pass")
    parser.add_argument("--check-runs-json", type=Path, help="offline check-runs response fixture")
    parser.add_argument("--check-suites-json", type=Path, help="offline check-suites response fixture")
    parser.add_argument("--workflow-runs-json", type=Path, help="offline Actions workflow-runs fixture")
    parser.add_argument("--release-tag", help="exact vX.Y.Z release tag that must be immutable")
    parser.add_argument("--tag-rulesets-json", type=Path, help="offline detailed tag-rulesets fixture")
    parser.add_argument("--required-check", action="append", dest="required_checks")
    parser.add_argument(
        "--require-review",
        action="store_true",
        help="require at least one approving pull-request review",
    )
    parser.add_argument(
        "--require-signed-commits",
        action="store_true",
        help="require GitHub signed-commit protection",
    )
    args = parser.parse_args(argv)
    if not args.protection_json and not args.repository:
        parser.error("--repository is required unless --protection-json is provided")
    try:
        exact_sha_fixtures = (
            args.check_runs_json,
            args.check_suites_json,
            args.workflow_runs_json,
        )
        if any(exact_sha_fixtures) and not args.sha:
            raise ValueError("exact-SHA check/suite/workflow fixtures require --sha")
        if any(exact_sha_fixtures) and not all(exact_sha_fixtures):
            raise ValueError(
                "offline exact-SHA evidence requires --check-runs-json, "
                "--check-suites-json, and --workflow-runs-json together"
            )
        if args.sha and not args.check_runs_json and not args.repository:
            raise ValueError("--repository is required for live exact-SHA check-run evidence")
        if args.tag_rulesets_json and not args.release_tag:
            raise ValueError("--tag-rulesets-json requires --release-tag")
        if args.release_tag and not args.tag_rulesets_json and not args.repository:
            raise ValueError("--repository is required for live release-tag ruleset evidence")
        sha = normalize_sha(args.sha) if args.sha else None
        release_tag = normalize_release_tag(args.release_tag) if args.release_tag else None
        repository = normalize_repository(args.repository) if args.repository else "fixture/fixture"
        payload = load_fixture(args.protection_json) if args.protection_json else fetch_protection(repository, args.branch)
        required_checks = tuple(args.required_checks or REQUIRED_CHECKS)
        errors = audit_protection(
            payload,
            required_checks,
            require_review=args.require_review,
            require_signed_commits=args.require_signed_commits,
        )
        if sha:
            check_runs_payload = (
                load_fixture(args.check_runs_json)
                if args.check_runs_json
                else fetch_check_runs(repository, sha)
            )
            check_suites_payload = (
                load_fixture(args.check_suites_json)
                if args.check_suites_json
                else fetch_check_suites(repository, sha)
            )
            workflow_runs_payload = (
                load_fixture(args.workflow_runs_json)
                if args.workflow_runs_json
                else fetch_workflow_runs(repository, sha, args.branch)
            )
            errors.extend(
                audit_check_runs(
                    check_runs_payload,
                    sha,
                    required_checks,
                    check_suites_payload=check_suites_payload,
                    workflow_runs_payload=workflow_runs_payload,
                    repository=repository,
                    branch=args.branch,
                )
            )
        if release_tag:
            tag_rulesets = (
                load_rulesets_fixture(args.tag_rulesets_json)
                if args.tag_rulesets_json
                else fetch_tag_rulesets(repository)
            )
            errors.extend(audit_tag_rulesets(tag_rulesets, release_tag))
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"repository governance: {exc}", file=sys.stderr)
        return 1
    if errors:
        print("repository governance failed:", file=sys.stderr)
        for error in errors:
            print(f"- {error}", file=sys.stderr)
        return 1
    suffix = f" SHA {sha}" if sha else ""
    if release_tag:
        suffix += f" immutable-tag {release_tag}"
    print(f"repository governance passed: {repository}@{args.branch}{suffix}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

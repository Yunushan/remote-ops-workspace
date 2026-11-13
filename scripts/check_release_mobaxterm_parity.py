"""Verify reviewed MobaXterm parity evidence for one published release."""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
from pathlib import Path
from typing import Any

SCRIPTS = Path(__file__).resolve().parent
ROOT = SCRIPTS.parent
for location in (ROOT, SCRIPTS):
    if str(location) not in sys.path:
        sys.path.insert(0, str(location))

from check_mobaxterm_parity_evidence import (  # noqa: E402
    ARTICLE_SPECS,
    GITHUB_REVIEW_RE,
    GITHUB_WORKFLOW_RUN_RE,
    check_mobaxterm_parity_evidence,
    review_acceptance_line,
)
from check_release_license_compliance import path_is_reparse, secure_regular_file  # noqa: E402
from check_release_provenance import (  # noqa: E402
    local_release_assets,
    normalize_repository,
    normalize_sha,
    normalize_tag,
    run_gh_json,
    sha256_file,
)
from scripts.make_mobaxterm_parity_evidence_record import VALIDATORS  # noqa: E402

REGISTRY = "configs/mobaxterm_parity_evidence.json"


def github_object(repository: str, resource: str) -> dict[str, Any]:
    value = run_gh_json(
        ["api", "--hostname", "github.com", f"repos/{repository}/{resource}"],
        resource,
        timeout=30,
    )
    if not isinstance(value, dict):
        raise ValueError(f"GitHub {resource} must return a JSON object")
    return value


def require_ancestor(repository: str, ancestor: str, descendant: str) -> None:
    if ancestor == descendant:
        return
    comparison = github_object(repository, f"compare/{ancestor}...{descendant}?per_page=1")
    base = comparison.get("base_commit")
    common = comparison.get("merge_base_commit")
    if (
        comparison.get("status") != "ahead"
        or type(comparison.get("behind_by")) is not int
        or comparison["behind_by"] != 0
        or not isinstance(base, dict)
        or base.get("sha") != ancestor
        or not isinstance(common, dict)
        or common.get("sha") != ancestor
    ):
        raise ValueError(f"GitHub did not establish {ancestor} as an ancestor of {descendant}")


def load_registry(repository: str, release_sha: str, registry_commit: str) -> dict[str, Any]:
    branch = github_object(repository, "branches/main")
    commit = branch.get("commit")
    if branch.get("name") != "main" or branch.get("protected") is not True or not isinstance(commit, dict):
        raise ValueError("GitHub must report a protected main branch")
    tip = commit.get("sha")
    if not isinstance(tip, str) or normalize_sha(tip) != tip:
        raise ValueError("GitHub main branch must resolve to a canonical commit SHA")
    if registry_commit == release_sha:
        raise ValueError("parity registry commit must follow the release source commit")
    require_ancestor(repository, release_sha, registry_commit)
    require_ancestor(repository, registry_commit, tip)

    file = github_object(repository, f"contents/{REGISTRY}?ref={registry_commit}")
    encoded = file.get("content")
    if (
        file.get("type") != "file"
        or file.get("path") != REGISTRY
        or file.get("encoding") != "base64"
        or not isinstance(encoded, str)
    ):
        raise ValueError("GitHub must return the parity registry file at the pinned commit")
    try:
        payload = base64.b64decode("".join(encoded.splitlines()), validate=True)
    except ValueError as exc:
        raise ValueError("GitHub parity registry has invalid base64 content") from exc
    if type(file.get("size")) is not int or len(payload) != file["size"]:
        raise ValueError("GitHub parity registry content length differs from its metadata")
    registry = json.loads(payload)
    if not isinstance(registry, dict):
        raise ValueError("GitHub parity registry must contain a JSON object")
    return registry


def verify_workflow_run(repository: str, source: dict[str, Any]) -> None:
    match = GITHUB_WORKFLOW_RUN_RE.fullmatch(source["workflow_run_url"])
    assert match is not None  # The registry validator checked the URL.
    run_id = int(match.group(2))
    attempt = source["run_attempt"]
    run = github_object(repository, f"actions/runs/{run_id}/attempts/{attempt}")
    expected = {
        "id": run_id,
        "run_attempt": attempt,
        "head_sha": source["head_sha"],
        "status": "completed",
        "conclusion": "success",
    }
    if (
        type(run.get("id")) is not int
        or type(run.get("run_attempt")) is not int
        or any(run.get(key) != value for key, value in expected.items())
    ):
        raise ValueError("GitHub workflow attempt does not match successful release evidence")
    for key in ("repository", "head_repository"):
        owner = run.get(key)
        if not isinstance(owner, dict) or owner.get("full_name") != repository:
            raise ValueError(f"GitHub workflow attempt {key} differs from the release repository")


def verify_review(repository: str, review: dict[str, Any]) -> set[str]:
    url = review["review_url"]
    match = GITHUB_REVIEW_RE.fullmatch(url)
    assert match is not None  # The registry validator checked the URL.
    if "#pullrequestreview-" in url:
        identifier = int(match.group(3))
        result = github_object(repository, f"pulls/{match.group(2)}/reviews/{identifier}")
        if result.get("state") != "APPROVED":
            raise ValueError("GitHub pull request review is not approved")
        timestamp = result.get("submitted_at")
    else:
        identifier = int(match.group(3) or match.group(5))
        result = github_object(repository, f"issues/comments/{identifier}")
        timestamp = result.get("created_at")

    author = result.get("user")
    if (
        type(result.get("id")) is not int
        or result["id"] != identifier
        or result.get("html_url") != url
        or timestamp != review["reviewed_at"]
        or not isinstance(author, dict)
        or author.get("login") != review["reviewer"]
    ):
        raise ValueError("GitHub review identity differs from the accepted evidence record")
    body = result.get("body")
    if not isinstance(body, str):
        raise ValueError("GitHub review has no explicit parity acceptance")
    return set(body.splitlines())


def verify_article_evidence(record: dict[str, Any], evidence_root: Path) -> None:
    article = record["article_id"]
    root = evidence_root / article
    if path_is_reparse(root) or not root.is_dir():
        raise ValueError("reviewed article evidence directory must exist without a reparse point")

    # Use a closed file set so a validator cannot accidentally consume an
    # unreviewed adjacent file. All paths remain below the article directory.
    expected = record["evidence_assets_sha256"]
    evidence = "evidence.json"
    if expected.get(evidence) != record["evidence_file_sha256"]:
        raise ValueError("reviewed article evidence.json digest differs from its evidence inventory")
    remaining = set(expected)
    for directory, subdirs, files in os.walk(root, followlinks=False):
        current = Path(directory)
        if any(path_is_reparse(current / name) for name in subdirs):
            raise ValueError("reviewed article evidence contains a linked directory")
        for name in files:
            relative = (current / name).relative_to(root).as_posix()
            if relative not in remaining:
                raise ValueError(f"reviewed article evidence contains an unexpected file: {relative}")
            path, error = secure_regular_file(root, relative, "reviewed article evidence")
            if error is not None or path is None:
                raise ValueError(error or "reviewed article evidence file is unavailable")
            if sha256_file(path) != expected[relative]:
                raise ValueError(f"reviewed article evidence SHA-256 differs: {relative}")
            remaining.remove(relative)
    if remaining:
        raise ValueError(f"reviewed article evidence files are missing: {sorted(remaining)}")

    verified = VALIDATORS[article](root / evidence, assets_dir=root).to_dict()
    if verified.get("passed") is not True:
        raise ValueError("the article validator did not pass on the reviewed evidence")
    if verified.get("summary") != record["validation_summary"]["summary"]:
        raise ValueError("article validator results differ from the reviewed summary")


def audit_release(
    *,
    repository: str,
    tag: str,
    release_sha: str,
    registry_commit: str,
    assets_dir: Path,
    evidence_root: Path,
) -> list[str]:
    registry = load_registry(repository, release_sha, registry_commit)
    errors = check_mobaxterm_parity_evidence(registry=registry, require_complete=True)
    if errors:
        return errors
    evidence_root = evidence_root.absolute()
    if not evidence_root.is_dir() or any(path_is_reparse(path) for path in (*evidence_root.parents, evidence_root)):
        return ["reviewed parity evidence root must be a real directory without linked parents"]
    assets, errors = local_release_assets(assets_dir)
    if errors:
        return errors

    digests: dict[str, str] = {}
    checked_runs: set[tuple[str, int]] = set()
    checked_reviews: dict[tuple[str, str, str], set[str]] = {}
    for record in registry["accepted_evidence"]:
        article = record["article_id"]
        source = record["release_source"]
        if record["release_tag"] != tag or source["repository"] != repository or source["head_sha"] != release_sha:
            errors.append(f"{article} accepted record must bind the exact release repository, tag, and source SHA")
            continue

        for name, expected in record["artifact_sha256"].items():
            path = assets.get(name)
            if path is None:
                errors.append(f"{article} references a missing release asset: {name}")
                continue
            if name not in digests:
                digests[name] = sha256_file(path)
            if digests[name] != expected:
                errors.append(f"{article} SHA-256 differs from the downloaded release asset: {name}")

        run_key = (source["workflow_run_url"], source["run_attempt"])
        review = record["acceptance_review"]
        review_key = (review["review_url"], review["reviewer"], review["reviewed_at"])
        try:
            if run_key not in checked_runs:
                verify_workflow_run(repository, source)
                checked_runs.add(run_key)
            if review_key not in checked_reviews:
                checked_reviews[review_key] = verify_review(repository, review)
            if review_acceptance_line(record) not in checked_reviews[review_key]:
                raise ValueError("GitHub review does not explicitly accept this exact article evidence")
            verify_article_evidence(record, evidence_root)
        except (OSError, RuntimeError, ValueError) as exc:
            errors.append(f"{article} {exc}")
    return errors


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--registry-commit", required=True, help="reviewed parity registry commit merged to main")
    parser.add_argument("--assets-dir", type=Path, required=True)
    parser.add_argument("--evidence-root", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        repository = normalize_repository(args.repository)
        if any(part in {".", ".."} for part in repository.split("/")):
            raise ValueError("repository must name a GitHub owner and repository")
        errors = audit_release(
            repository=repository,
            tag=normalize_tag(args.tag),
            release_sha=normalize_sha(args.sha),
            registry_commit=normalize_sha(args.registry_commit),
            assets_dir=args.assets_dir,
            evidence_root=args.evidence_root,
        )
    except (OSError, RuntimeError, ValueError) as exc:
        errors = [str(exc)]
    if errors:
        for error in errors:
            print(f"release MobaXterm parity: {error}", file=sys.stderr)
        return 1
    print(f"release MobaXterm parity: {len(ARTICLE_SPECS)}/{len(ARTICLE_SPECS)} articles verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

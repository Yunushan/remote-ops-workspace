"""Preflight reviewed parity evidence against the sealed candidate before publication."""

from __future__ import annotations

import argparse
import json
import os
import sys
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.check_mobaxterm_parity_evidence import (  # noqa: E402
    ARTICLE_SPECS,
    check_candidate_record,
    check_review_provenance,
    release_asset_repositories,
)
from scripts.check_release_license_compliance import (  # noqa: E402
    path_is_reparse,
    secure_regular_file,
    valid_sha256,
)
from scripts.check_release_mobaxterm_parity import audit_reviewed_records  # noqa: E402
from scripts.finalize_mobaxterm_parity_evidence_record import release_source  # noqa: E402
from scripts.release_candidate_inventory import (  # noqa: E402
    MAX_JSON_BYTES,
    GitHubClient,
    normalize_repository,
    normalize_sha,
    normalize_tag,
    safe_name,
)
from scripts.release_candidate_source import InventoryPointer, read_attested_inventory  # noqa: E402


def read_review_object(root: Path, name: str) -> dict[str, Any]:
    path, error = secure_regular_file(root, name, "candidate parity input")
    if path is None or error:
        raise ValueError(error)
    with path.open("rb") as file:
        raw = file.read(MAX_JSON_BYTES + 1)
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError(f"candidate parity input exceeds the JSON size limit: {name}")
    obj = json.loads(raw)
    if not isinstance(obj, dict):
        raise ValueError(f"candidate parity input must contain a JSON object: {name}")
    return obj


def load_reviewed_candidates(root: Path, repository: str, tag: str, sha: str) -> list[dict[str, Any]]:
    if not root.is_dir() or any(path_is_reparse(path) for path in (*root.parents, root)):
        raise ValueError("reviewed parity evidence root must be a real directory without linked parents")
    reviews = read_review_object(root, "candidate-reviews.json")
    if reviews.keys() != ARTICLE_SPECS.keys():
        raise ValueError("candidate-reviews.json must index all eight parity articles exactly")

    records = []
    for article, review in sorted(reviews.items()):
        candidate = read_review_object(root, f"candidates/{article}.json")
        if candidate.get("article_id") != article:
            raise ValueError(f"{article} candidate file must contain that article")
        if {"release_source", "acceptance_review", "release_asset_bytes"} & candidate.keys():
            raise ValueError(f"{article} preflight requires the original workflow candidate")
        errors = check_candidate_record(candidate)
        review_errors, _, _ = check_review_provenance(article, repository, review)
        if errors or review_errors:
            raise ValueError("; ".join((*errors, *review_errors)))
        summary = candidate["validation_summary"]["summary"]
        if (
            (summary["repository"], candidate["release_tag"], summary["source_head_sha"]) != (repository, tag, sha)
            or release_asset_repositories(candidate["release_asset_urls"]) != {repository}
        ):
            raise ValueError(f"{article} candidate must match the exact release repository, tag, and source SHA")
        source = release_source(candidate, repository, sha, sha, summary["workflow_run_url"], summary["run_attempt"])
        records.append({**candidate, "release_source": source, "acceptance_review": review})
    return records


def sealed_asset_hashes(records: list[dict]) -> dict[str, str]:
    hashes: dict[str, str] = {}
    filenames: set[str] = set()
    for artifact in records:
        for item in artifact["files"]:
            if not isinstance(item, dict):
                raise ValueError("sealed inventory file entry must be an object")
            name, digest = item.get("path"), item.get("sha256")
            if not safe_name(name) or not valid_sha256(digest):
                raise ValueError("sealed inventory file entry requires a safe name and SHA-256")
            if name.casefold() in filenames:
                raise ValueError(f"sealed inventory has a duplicate or case-colliding asset: {name}")
            filenames.add(name.casefold())
            hashes[name] = digest
    return hashes


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--candidate-inventory", required=True, metavar="'RUN_ID ARTIFACT_ID sha256:DIGEST'")
    parser.add_argument("--assets-dir", type=Path, required=True, help="staged assets from the sealed build")
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument(
        "--retain-workflow-artifacts", action="store_true",
        help="retain verified original Actions ZIPs under the evidence root for the published audit",
    )
    parser.add_argument("--professional-update-origin", action="append", help="independently approved HTTPS origin")
    args = parser.parse_args(argv)
    try:
        repository, tag, sha = normalize_repository(args.repository), normalize_tag(args.tag), normalize_sha(args.sha)
        pointer = InventoryPointer.parse(args.candidate_inventory)
        if pointer is None:
            raise ValueError("sealed candidate inventory coordinates are required")
        root = args.evidence_root.absolute()
        candidates = load_reviewed_candidates(root, repository, tag, sha)
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if not token:
            raise ValueError("sealed candidate verification requires a GitHub token")
        client = GitHubClient(repository, token, api_url="https://api.github.com")
        with TemporaryDirectory(prefix="row-parity-candidate-") as directory:
            records, _ = read_attested_inventory(client, repository, Path(directory), tag, sha, pointer)
        errors = audit_reviewed_records(
            candidates, repository=repository, tag=tag, release_sha=sha, assets_dir=args.assets_dir, evidence_root=root,
            professional_update_origins=(args.professional_update_origin or
                                         os.environ.get("RELEASE_PROFESSIONAL_UPDATE_ORIGINS", "").split()),
            sealed_assets=sealed_asset_hashes(records),
            retain_workflow_artifacts=args.retain_workflow_artifacts,
        )
    except (OSError, RuntimeError, ValueError, zipfile.BadZipFile) as exc:
        errors = [str(exc)]
    if errors:
        for error in errors:
            print(f"candidate MobaXterm parity preflight: {error}", file=sys.stderr)
        return 1
    count = len(ARTICLE_SPECS)
    print(f"candidate MobaXterm parity preflight: {count}/{count} reviewed candidates verified")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

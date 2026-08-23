from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_mobaxterm_parity_evidence import (  # noqa: E402
    REGISTRY_PATH,
    check_candidate_record,
    check_mobaxterm_parity_evidence,
    check_record,
)
from scripts.make_mobaxterm_parity_evidence_record import registry_policy  # noqa: E402


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.append_registry and args.out is None:
        print(
            "mobaxterm parity evidence finalizer: --append-registry requires --out so the reviewed "
            "accepted record is retained as a separate artifact",
            file=sys.stderr,
        )
        return 1
    candidate, read_errors = read_json_object(args.candidate_record, "candidate record")
    published_assets, asset_arg_errors = published_asset_paths(args.published_release_asset)
    errors, record = finalize_candidate(
        candidate,
        repository=args.repository,
        source_head_sha=args.source_head_sha,
        tag_source_head_sha=args.tag_source_head_sha,
        workflow_run_url=args.workflow_run_url,
        run_attempt=args.run_attempt,
        reviewer=args.reviewer,
        review_url=args.review_url,
        reviewed_at=args.reviewed_at,
        published_assets=published_assets,
    )
    errors = [*read_errors, *asset_arg_errors, *errors]
    if errors:
        for error in errors:
            print(f"mobaxterm parity evidence finalizer: {error}", file=sys.stderr)
        return 1
    if args.out is not None:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(canonical_json(record), encoding="utf-8")
    if args.append_registry:
        append_errors = append_record(record, registry_path=args.registry)
        if append_errors:
            for error in append_errors:
                print(f"mobaxterm parity evidence finalizer: {error}", file=sys.stderr)
            return 1
    if args.out is None:
        print(canonical_json(record), end="")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Finalize a reviewed MobaXterm candidate as accepted evidence. The finalizer binds exact "
            "repository/tag/source-run/reviewer provenance and re-hashes downloaded published release bytes."
        )
    )
    parser.add_argument("--candidate-record", required=True, type=Path)
    parser.add_argument("--repository", required=True, help="exact GitHub owner/name")
    parser.add_argument("--source-head-sha", required=True, help="exact 40-character release source SHA")
    parser.add_argument("--tag-source-head-sha", required=True, help="resolved release tag source SHA")
    parser.add_argument("--workflow-run-url", required=True, help="exact GitHub Actions source run URL")
    parser.add_argument("--run-attempt", required=True, type=positive_int)
    parser.add_argument("--reviewer", required=True, help="GitHub login that accepted the evidence")
    parser.add_argument("--review-url", required=True, help="exact GitHub pull-request review or review-comment URL")
    parser.add_argument("--reviewed-at", required=True, help="UTC RFC3339 review timestamp")
    parser.add_argument(
        "--published-release-asset",
        action="append",
        default=[],
        help="downloaded published release bytes as release-file-name=local-path; repeat for every candidate asset",
    )
    parser.add_argument("--out", type=Path, help="write the finalized accepted record")
    parser.add_argument("--append-registry", action="store_true")
    parser.add_argument("--registry", type=Path, default=REGISTRY_PATH)
    return parser.parse_args(argv)


def positive_int(value: str) -> int:
    if not value.isdigit() or value.startswith("0"):
        raise argparse.ArgumentTypeError("must be a positive integer without padding")
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("must be a positive integer")
    return parsed


def finalize_candidate(
    candidate: dict[str, Any],
    *,
    repository: str,
    source_head_sha: str,
    tag_source_head_sha: str,
    workflow_run_url: str,
    run_attempt: int,
    reviewer: str,
    review_url: str,
    reviewed_at: str,
    published_assets: dict[str, Path],
) -> tuple[list[str], dict[str, Any]]:
    errors = check_candidate_record(candidate)
    if candidate.get("article_id") == "shared-authenticated-transport-terminal-grid":
        validation = candidate.get("validation_summary")
        summary = validation.get("summary") if isinstance(validation, dict) else None
        if not isinstance(summary, dict):
            errors.append(
                "shared-authenticated-transport-terminal-grid validation_summary.summary "
                "must contain source provenance"
            )
        else:
            expected = {
                "repository": repository,
                "release_tag": candidate.get("release_tag"),
                "release_target": candidate.get("release_target"),
                "source_head_sha": source_head_sha,
                "workflow_run_url": workflow_run_url,
                "run_attempt": run_attempt,
            }
            for key, value in expected.items():
                if summary.get(key) != value:
                    errors.append(
                        "shared-authenticated-transport-terminal-grid validation_summary.summary."
                        f"{key} must match accepted release provenance {value!r}"
                    )
    expected_hashes = candidate.get("artifact_sha256")
    if not isinstance(expected_hashes, dict):
        expected_hashes = {}
    expected_names = set(expected_hashes)
    actual_names = set(published_assets)
    if actual_names != expected_names:
        errors.append(
            "published release asset names must exactly match candidate artifact_sha256 keys: "
            f"expected {sorted(expected_names)}, got {sorted(actual_names)}"
        )
    published_hashes: dict[str, str] = {}
    for name, path in sorted(published_assets.items()):
        if not path.is_file():
            errors.append(f"downloaded published release asset is missing: {name}={path}")
            continue
        digest = sha256_file(path)
        published_hashes[name] = digest
        expected = expected_hashes.get(name)
        if expected is not None and digest != expected:
            errors.append(
                f"published release asset bytes for {name} have SHA-256 {digest}, expected {expected}"
            )
    if errors:
        return errors, {}

    record = {
        **candidate,
        "status": "accepted",
        "release_source": {
            "repository": repository,
            "release_tag": candidate.get("release_tag"),
            "head_sha": source_head_sha,
            "tag_source_head_sha": tag_source_head_sha,
            "workflow_run_url": workflow_run_url,
            "run_attempt": run_attempt,
        },
        "acceptance_review": {
            "reviewer": reviewer,
            "review_url": review_url,
            "reviewed_at": reviewed_at,
        },
        "release_asset_bytes": {
            "verified": True,
            "verified_by": reviewer,
            "verified_at": reviewed_at,
            "sha256": published_hashes,
        },
    }
    final_errors = check_record(record)
    return final_errors, record if not final_errors else {}


def published_asset_paths(items: list[str]) -> tuple[dict[str, Path], list[str]]:
    result: dict[str, Path] = {}
    errors: list[str] = []
    if not items:
        return result, ["--published-release-asset is required for every release asset"]
    for item in items:
        if "=" not in item:
            errors.append(f"--published-release-asset must be release-file-name=local-path: {item}")
            continue
        name, raw_path = item.split("=", 1)
        if not name or Path(name).name != name or name in {".", ".."}:
            errors.append(f"--published-release-asset name must be one safe file name: {name!r}")
            continue
        if name in result:
            errors.append(f"duplicate --published-release-asset name: {name}")
            continue
        result[name] = Path(raw_path)
    return result, errors


def append_record(record: dict[str, Any], *, registry_path: Path) -> list[str]:
    registry, read_errors = read_json_object(registry_path, "MobaXterm parity registry")
    if read_errors:
        return read_errors
    accepted = registry.get("accepted_evidence")
    if not isinstance(accepted, list):
        return ["mobaxterm parity evidence accepted_evidence must be a list"]
    article_id = record.get("article_id")
    if any(isinstance(item, dict) and item.get("article_id") == article_id for item in accepted):
        return [f"{article_id} already has accepted evidence; replace it only through deliberate review"]
    updated = {**registry, "accepted_evidence": [*accepted, record]}
    errors = check_mobaxterm_parity_evidence(registry=updated)
    if errors:
        return errors
    registry_path.parent.mkdir(parents=True, exist_ok=True)
    registry_path.write_text(canonical_json(updated), encoding="utf-8")
    return []


def read_json_object(path: Path, label: str) -> tuple[dict[str, Any], list[str]]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        return {}, [f"cannot read {label} {path}: {exc}"]
    except json.JSONDecodeError as exc:
        return {}, [f"{label} {path} is not valid JSON: {exc}"]
    if not isinstance(data, dict):
        return {}, [f"{label} root must be a JSON object"]
    return data, []


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def canonical_json(value: dict[str, Any]) -> str:
    return json.dumps(value, indent=2, sort_keys=True) + "\n"


def empty_registry() -> dict[str, Any]:
    return {"schema_version": 2, "policy": registry_policy(), "accepted_evidence": []}


if __name__ == "__main__":
    raise SystemExit(main())

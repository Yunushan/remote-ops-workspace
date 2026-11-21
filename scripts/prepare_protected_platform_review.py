"""Prepare one independently reviewable input set for the four protected platforms."""

from __future__ import annotations

import argparse
import json
import os
import sys
import zipfile
from contextlib import suppress
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.check_platform_evidence_source_ref import (  # noqa: E402
    GitHubApiFetcher,
    resolve_tag_commit,
)
from scripts.check_platform_release_evidence_remote import (  # noqa: E402
    capture_live_source_evidence,
)
from scripts.check_platform_review_bundle_artifacts import (  # noqa: E402
    canonical_public_record_bytes,
    check_platform_review_bundle_artifacts,
)
from scripts.check_platform_verified_evidence import (  # noqa: E402
    EVIDENCE_PATH,
    PROTECTED_GOAL_TARGETS,
    accepted_record_source_file,
    check_platform_verified_evidence,
    read_json,
)
from scripts.check_release_license_compliance import (  # noqa: E402
    path_is_reparse,
    secure_regular_file,
)
from scripts.release_candidate_inventory import (  # noqa: E402
    MAX_JSON_BYTES,
    extract_archive,
    normalize_repository,
    normalize_sha,
    normalize_tag,
)


def build_release_registry(records_dir: Path, repository: str, tag: str, sha: str) -> dict[str, Any]:
    root = records_dir.absolute()
    if not root.is_dir() or any(path_is_reparse(path) for path in (*root.parents, root)):
        raise ValueError("finalized platform records must be in a real directory without linked parents")
    records = []
    for target in PROTECTED_GOAL_TARGETS:
        name = accepted_record_source_file(target)
        path, error = secure_regular_file(root, name, "finalized platform record")
        if path is None or error:
            raise ValueError(error)
        with path.open("rb") as stream:
            raw = stream.read(MAX_JSON_BYTES + 1)
        if len(raw) > MAX_JSON_BYTES:
            raise ValueError(f"{target} finalized record exceeds the JSON size limit")
        record = json.loads(raw)
        if not isinstance(record, dict) or record.get("target") != target:
            raise ValueError(f"{name} must contain the finalized record for {target}")
        if raw != canonical_public_record_bytes(record):
            raise ValueError(f"{target} finalized record must match the canonical workflow JSON bytes")
        source = record.get("release_asset_source")
        if (
            not isinstance(source, dict) or source.get("head_sha") != sha
            or record.get("release_tag") != tag
            or not str(source.get("workflow_run_url", "")).startswith(f"https://github.com/{repository}/actions/runs/")
        ):
            raise ValueError(f"{target} finalized record must match the selected repository, tag and SHA")
        records.append(record)
    registry = {**read_json(EVIDENCE_PATH), "accepted_evidence": records}
    errors = check_platform_verified_evidence(
        registry=registry, required_targets=PROTECTED_GOAL_TARGETS,
        required_release_tag=tag, require_review_bundles=True,
    )
    if errors:
        raise ValueError("; ".join(errors))
    return registry


def require_live_tag(fetcher: GitHubApiFetcher, tag: str, sha: str) -> None:
    live_sha, errors = resolve_tag_commit(fetcher, tag)
    if errors:
        raise ValueError("; ".join(errors))
    if live_sha != sha:
        raise ValueError("live release tag does not resolve to the selected source SHA")


def prepare_review(records_dir: Path, output: Path, repository: str, tag: str, sha: str) -> None:
    destination = output.absolute()
    if (
        os.path.lexists(destination) or destination.resolve().is_relative_to(records_dir.resolve())
        or any(path_is_reparse(path) for path in destination.parents)
    ):
        raise ValueError("--out must be a new directory with unlinked parents outside the records directory")
    registry = build_release_registry(records_dir, repository, tag, sha)
    fetcher = GitHubApiFetcher(repository=repository, timeout=20)
    require_live_tag(fetcher, tag, sha)

    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".row-protected-platform-review-", dir=destination.parent) as directory:
        work = Path(directory)
        packet = work / "review"
        errors = capture_live_source_evidence(repository, tag, registry, packet)
        if errors:
            raise ValueError("; ".join(errors))
        for target in PROTECTED_GOAL_TARGETS:
            with TemporaryDirectory(prefix="bundle-", dir=work) as bundle:
                extract_archive(packet / "archives" / f"{target}.zip", Path(bundle))
                errors = check_platform_review_bundle_artifacts(
                    registry=registry, bundle_dir=Path(bundle), required_targets=(target,),
                    required_release_tag=tag, require_final_record_assets=True,
                )
                if errors:
                    raise ValueError("; ".join(errors))
        require_live_tag(fetcher, tag, sha)
        (packet / EVIDENCE_PATH.name).write_bytes(
            (json.dumps(registry, indent=2, sort_keys=True) + "\n").encode("utf-8"),
        )
        if os.name == "nt":
            packet.rename(destination)
        else:
            # Reserve the name before rename so POSIX cannot replace someone else's empty directory.
            destination.mkdir(mode=0o700)
            try:
                packet.rename(destination)
            except OSError:
                with suppress(OSError):
                    destination.rmdir()
                raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--release-sha", required=True)
    parser.add_argument("--records-dir", required=True, type=Path, help="directory holding the four original finalized JSON files")
    parser.add_argument("--out", required=True, type=Path, help="new review directory")
    args = parser.parse_args(argv)
    try:
        prepare_review(
            args.records_dir, args.out, normalize_repository(args.repository),
            normalize_tag(args.release_tag), normalize_sha(args.release_sha),
        )
    except (OSError, RuntimeError, ValueError, zipfile.BadZipFile) as exc:
        print(f"protected-platform review preparation: {exc}", file=sys.stderr)
        return 1
    print(f"Prepared {len(PROTECTED_GOAL_TARGETS)} verified source archives and a release registry for review in {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

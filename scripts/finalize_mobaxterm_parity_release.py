"""Finalize all reviewed parity records against one immutable published release."""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.check_candidate_mobaxterm_parity import load_reviewed_candidates  # noqa: E402
from scripts.check_mobaxterm_parity_evidence import check_mobaxterm_parity_evidence  # noqa: E402
from scripts.check_release_mobaxterm_parity import audit_reviewed_records  # noqa: E402
from scripts.check_release_provenance import (  # noqa: E402
    main as verify_release_provenance,
)
from scripts.check_release_provenance import (  # noqa: E402
    normalize_repository,
    normalize_sha,
    normalize_tag,
)
from scripts.finalize_mobaxterm_parity_evidence_record import (  # noqa: E402
    accepted_record,
    canonical_json,
    empty_registry,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--assets-dir", type=Path, required=True, help="complete immutable release downloads")
    parser.add_argument("--evidence-root", type=Path, required=True)
    parser.add_argument("--professional-update-origin", action="append", help="independently approved HTTPS origin")
    parser.add_argument("--out", type=Path, required=True, help="new complete registry file for review")
    args = parser.parse_args(argv)

    try:
        repository, tag, sha = normalize_repository(args.repository), normalize_tag(args.tag), normalize_sha(args.sha)
        output = args.out.absolute()
        if os.path.lexists(output) or any(
            output.resolve().is_relative_to(root.resolve()) for root in (args.assets_dir, args.evidence_root)
        ):
            raise ValueError("--out must be a new file outside the release assets and evidence directories")

        records = load_reviewed_candidates(args.evidence_root.absolute(), repository, tag, sha)
        hashes: dict[str, str] = {}
        for record in records:
            for name, digest in record["artifact_sha256"].items():
                if hashes.setdefault(name, digest) != digest:
                    raise ValueError(f"reviewed candidates disagree on the published SHA-256 of {name}")

        if verify_release_provenance(
            ["--assets-dir", str(args.assets_dir), "--repository", repository, "--tag", tag, "--sha", sha],
            reviewed_asset_hashes=hashes,
        ):
            raise ValueError("immutable release provenance did not pass for the reviewed hashes")
        errors = audit_reviewed_records(
            records, repository=repository, tag=tag, release_sha=sha, assets_dir=args.assets_dir,
            evidence_root=args.evidence_root,
            professional_update_origins=(
                args.professional_update_origin or os.environ.get("RELEASE_PROFESSIONAL_UPDATE_ORIGINS", "").split()
            ),
        )
        if errors:
            raise ValueError("; ".join(errors))
        registry = empty_registry()
        registry["accepted_evidence"] = [accepted_record(record, record["artifact_sha256"]) for record in records]
        errors = check_mobaxterm_parity_evidence(registry=registry, require_complete=True)
        if errors:
            raise ValueError("; ".join(errors))

        output.parent.mkdir(parents=True, exist_ok=True)
        with TemporaryDirectory(prefix=".row-parity-registry-", dir=output.parent) as directory:
            staged = Path(directory) / "registry.json"
            staged.write_text(canonical_json(registry), encoding="utf-8")
            # Windows rename and POSIX link both refuse a concurrently created output.
            if os.name == "nt":
                staged.rename(output)
            else:
                os.link(staged, output)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"MobaXterm release parity finalization: {exc}", file=sys.stderr)
        return 1

    count = len(records)
    print(f"MobaXterm release parity finalization: {count}/{count} reviewed records written to {output}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

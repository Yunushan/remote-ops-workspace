"""Fetch the exact wheel or Debian package a release qualification may use."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import zipfile
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.release_candidate_inventory import (  # noqa: E402
    GitHubClient,
    normalize_repository,
    normalize_sha,
    normalize_tag,
)
from scripts.release_candidate_source import (  # noqa: E402
    InventoryPointer,
    asset_filename,
    materialize_asset,
)


def fetch_asset(
    repository: str, tag: str, sha: str, kind: str, directory: Path, pointer: InventoryPointer | None,
) -> Path:
    filename = asset_filename(kind, tag)
    result = directory / filename
    if directory.is_symlink() or not directory.is_dir() or os.path.lexists(result):
        raise ValueError("qualification download requires a real directory and unused asset filename")

    with TemporaryDirectory(prefix=".qualification-", dir=directory) as scratch:
        staging = Path(scratch)
        if pointer is None:
            subprocess.run(
                ["gh", "release", "download", tag, "--repo", repository, "--pattern", filename, "--dir", scratch],
                check=True, timeout=300,
            )
            asset = staging / filename
            subprocess.run(
                [sys.executable, "-I", str(ROOT / "scripts/check_release_provenance.py"), "--asset", str(asset),
                 "--repository", repository, "--tag", tag, "--sha", sha],
                check=True, timeout=300,
            )
        else:
            token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
            if not token:
                raise ValueError("sealed candidate verification requires a GitHub token")
            client = GitHubClient(repository, token, api_url="https://api.github.com")
            asset, _, _ = materialize_asset(client, repository, staging, tag, sha, pointer, kind=kind)
        source_file = asset.lstat()
        if not asset.is_file() or asset.is_symlink() or source_file.st_size <= 0:
            raise ValueError("verified qualification asset must be a nonempty regular file")
        asset.rename(result)
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--kind", choices=("wheel", "debian-amd64"), required=True)
    parser.add_argument("--directory", type=Path, required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--sha", required=True)
    args = parser.parse_args(argv)
    try:
        pointer = InventoryPointer.parse(os.environ.get("ROW_QUALIFICATION_CANDIDATE_INVENTORY", ""))
        asset = fetch_asset(
            normalize_repository(args.repository), normalize_tag(args.tag), normalize_sha(args.sha),
            args.kind, args.directory, pointer,
        )
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError, zipfile.BadZipFile) as exc:
        print(f"qualification release asset: {exc}", file=sys.stderr)
        return 1
    origin = "immutable release" if pointer is None else f"sealed build run {pointer.run_id}"
    print(f"Verified {asset.name} from {origin}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

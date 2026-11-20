"""Verify a reviewed Debian amd64 bundle from a release evidence commit."""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tarfile
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.release_candidate_inventory import normalize_sha, normalize_tag  # noqa: E402
from scripts.stage_debian_server_bundle import (  # noqa: E402
    ARCHIVE_NAME,
    MAX_COMPRESSED_BYTES,
    stage_bundle,
)

EVIDENCE_REF = "refs/remotes/origin/release-compliance-evidence"


def prepare_bundle(repo: Path, commit: str, tag: str, digest: str, output: Path) -> None:
    commit = normalize_sha(commit)
    tag = normalize_tag(tag)
    if os.path.lexists(output):
        raise ValueError("server bundle output already exists")

    git = ["git", "--no-replace-objects", "-C", str(repo)]
    resolved = subprocess.check_output(
        [*git, "rev-parse", "--verify", f"{commit}^{{commit}}"], timeout=30,
    ).decode("ascii").strip()
    if resolved != commit:
        raise ValueError("server bundle source must be an exact commit")
    ancestry = subprocess.run(
        [*git, "merge-base", "--is-ancestor", commit, EVIDENCE_REF], check=False, timeout=30,
    )
    if ancestry.returncode != 0:
        raise ValueError("server bundle commit must be on the fetched release-compliance-evidence branch")

    path = f"server-bundles/{tag}/{ARCHIVE_NAME}"
    entry = subprocess.check_output([*git, "ls-tree", commit, "--", path], timeout=30)
    if not entry.startswith(b"100644 blob "):
        raise ValueError("server bundle commit must contain the archive as a regular data file")
    blob = f"{commit}:{path}"
    size = int(subprocess.check_output([*git, "cat-file", "-s", blob], timeout=30))
    if not 0 < size <= MAX_COMPRESSED_BYTES:
        raise ValueError("server bundle Git blob exceeds the archive size limit or is empty")

    with tempfile.TemporaryDirectory(prefix="row-server-upload-", dir=output.parent) as temporary:
        root = Path(temporary)
        upload = root / "upload"
        upload.mkdir()
        archive = upload / ARCHIVE_NAME
        with archive.open("xb") as stream:
            subprocess.run([*git, "cat-file", "blob", blob], stdout=stream, check=True, timeout=30)
        if archive.stat().st_size != size:
            raise ValueError("server bundle Git blob size changed while copying")
        stage_bundle(archive, digest, "linux-x86_64", root / "verified")
        upload.rename(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--commit", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    try:
        prepare_bundle(Path.cwd(), args.commit, args.tag, args.sha256, args.out)
    except (EOFError, OSError, ValueError, subprocess.SubprocessError, tarfile.TarError) as exc:
        parser.exit(1, f"Debian server bundle preparation failed: {exc}\n")
    print(f"Prepared {ARCHIVE_NAME} from {args.commit} for {args.tag} (sha256:{args.sha256})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

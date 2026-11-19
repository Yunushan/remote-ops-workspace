"""Stage a digest-pinned Debian server bundle for the native release build."""

from __future__ import annotations

import argparse
import gzip
import hashlib
import os
import re
import shutil
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import BinaryIO

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.moba_debian_server_payload import (  # noqa: E402
    ELF_TARGETS,
    EXTERNAL_SERVICES,
    MANIFEST,
    NOTICE_MAX_BYTES,
    SERVER_RUNTIME_MAX_BYTES,
    server_payload,
    verify_debian_notice_inputs,
)
from scripts.release_candidate_inventory import (  # noqa: E402
    GitHubClient,
    extract_archive,
    normalize_digest,
    normalize_repository,
    positive_int,
)

ARCHIVE_NAME = "server-bundle.tar.gz"
MAX_MEMBERS = 64
MAX_TAR_BYTES = (len(EXTERNAL_SERVICES) + 2) * SERVER_RUNTIME_MAX_BYTES + 8 * 1024 * 1024
MAX_COMPRESSED_BYTES = MAX_TAR_BYTES + 1024 * 1024
SAFE_COMPONENT = re.compile(r"[A-Za-z0-9._+-]+")


def download_bundle(client: GitHubClient, artifact_id: int, temporary: Path) -> Path:
    endpoint = f"actions/artifacts/{artifact_id}"
    artifact = client.json(endpoint)
    if positive_int(artifact.get("id"), "artifact ID") != artifact_id or artifact.get("expired") is not False:
        raise ValueError("GitHub returned a different or expired artifact")
    digest = normalize_digest(artifact.get("digest"), "artifact ZIP digest")
    size = positive_int(artifact.get("size_in_bytes"), "artifact ZIP size")
    if size > MAX_COMPRESSED_BYTES:
        raise ValueError("artifact ZIP exceeds the size limit")
    zip_path = temporary / "artifact.zip"
    downloaded = client.download(f"{endpoint}/zip", zip_path, max_bytes=size)
    if downloaded != digest or zip_path.stat().st_size != size:
        raise ValueError("artifact ZIP bytes do not match GitHub metadata")
    extracted = temporary / "download"
    extract_archive(zip_path, extracted, max_expanded_bytes=MAX_COMPRESSED_BYTES, only_name=ARCHIVE_NAME)
    return extracted / ARCHIVE_NAME


def copy_bounded(source: BinaryIO, destination: BinaryIO, limit: int) -> str:
    digest = hashlib.sha256()
    size = 0
    while chunk := source.read(1024 * 1024):
        size += len(chunk)
        if size > limit:
            raise ValueError("server bundle exceeds the archive size limit")
        digest.update(chunk)
        destination.write(chunk)
    return digest.hexdigest()


def extract_bundle(archive: tarfile.TarFile, destination: Path) -> tuple[set[PurePosixPath], set[PurePosixPath]]:
    seen: set[str] = set()
    files: set[PurePosixPath] = set()
    directories: set[PurePosixPath] = set()
    for item in archive:
        name = item.name.removeprefix("./")
        relative = PurePosixPath(name)
        if (
            name != relative.as_posix() or not relative.parts
            or any(part == ".." or SAFE_COMPONENT.fullmatch(part) is None for part in relative.parts)
            or relative.parts[0] not in (MANIFEST, "linux", "notices")
        ):
            raise ValueError(f"server bundle contains an unsafe path: {item.name!r}")
        if len(seen) >= MAX_MEMBERS or name.casefold() in seen:
            raise ValueError(f"server bundle contains too many or duplicate members: {item.name!r}")
        seen.add(name.casefold())
        if item.isdir() and relative.parts[0] != MANIFEST:
            if item.size != 0:
                raise ValueError(f"server bundle directory contains data: {item.name!r}")
            directories.add(relative)
            continue
        native = relative.parts[0] == "linux"
        if not item.isfile() or item.sparse is not None:
            raise ValueError(f"server bundle member must be a regular file: {item.name!r}")
        if not 0 < item.size <= (SERVER_RUNTIME_MAX_BYTES if native else NOTICE_MAX_BYTES):
            raise ValueError(f"server bundle member has an invalid size: {item.name!r}")
        path = destination / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        with archive.extractfile(item) as contents, path.open("xb") as file:
            shutil.copyfileobj(contents, file, length=1024 * 1024)
        path.chmod(0o755 if native else 0o644)
        files.add(relative)
    return files, directories


def stage_bundle(archive_path: Path, expected_sha256: str, target: str, output: Path) -> None:
    if re.fullmatch(r"[0-9a-f]{64}", expected_sha256) is None:
        raise ValueError("server bundle SHA-256 must be 64 lowercase hexadecimal characters")
    if output.exists() or output.is_symlink():
        raise ValueError("server bundle output already exists")
    with tempfile.TemporaryDirectory(prefix="row-server-stage-", dir=output.parent) as temporary:
        staged = Path(temporary) / "verified"
        staged.mkdir()
        with tempfile.TemporaryFile() as compressed, tempfile.TemporaryFile() as expanded:
            with archive_path.open("rb") as source:
                actual = copy_bounded(source, compressed, MAX_COMPRESSED_BYTES)
            if actual != expected_sha256:
                raise ValueError("server bundle SHA-256 does not match the approved archive")
            compressed.seek(0)
            with gzip.GzipFile(mode="rb", fileobj=compressed) as source:
                # Count tar headers and extended metadata against the same bound as file data.
                copy_bounded(source, expanded, MAX_TAR_BYTES)
            expanded.seek(0)
            with tarfile.open(fileobj=expanded, mode="r:") as archive:
                files, directories = extract_bundle(archive, staged)
        manifest, payload = server_payload(staged, target, EXTERNAL_SERVICES)
        notices = verify_debian_notice_inputs(staged, manifest.get("debian_notices"))
        expected_files = {PurePosixPath(path) for path in payload}
        expected_files.update(PurePosixPath("notices", f"{name}.copyright") for name in notices)
        expected_directories = {parent for path in expected_files for parent in path.parents}
        if files != expected_files or not directories <= expected_directories:
            raise ValueError("server bundle contains members outside the reviewed manifest and notices")
        staged.rename(output)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group(required=True)
    source.add_argument("--archive", type=Path)
    source.add_argument("--artifact-id", type=int)
    parser.add_argument("--repository", default=os.environ.get("GITHUB_REPOSITORY"))
    parser.add_argument("--sha256", required=True)
    parser.add_argument("--target", choices=ELF_TARGETS, required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    try:
        if args.archive is not None:
            stage_bundle(args.archive, args.sha256, args.target, args.out)
        else:
            token = os.environ.get("GITHUB_TOKEN")
            if not token:
                raise ValueError("GITHUB_TOKEN is required to read the selected Actions artifact")
            client = GitHubClient(normalize_repository(args.repository), token)
            artifact_id = positive_int(args.artifact_id, "artifact ID")
            with tempfile.TemporaryDirectory(prefix="row-server-download-") as temporary:
                archive = download_bundle(client, artifact_id, Path(temporary))
                stage_bundle(archive, args.sha256, args.target, args.out)
    except (EOFError, OSError, RuntimeError, ValueError, tarfile.TarError, zipfile.BadZipFile) as exc:
        parser.exit(1, f"Debian server bundle staging failed: {exc}\n")
    print(f"Verified Debian server bundle for {args.target} (sha256:{args.sha256})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

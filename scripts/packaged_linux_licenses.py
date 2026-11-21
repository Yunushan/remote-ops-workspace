"""Read frozen runtime license files from Linux release packages."""

from __future__ import annotations

import io
import subprocess
import tarfile
import tempfile
from collections.abc import Iterator
from pathlib import Path, PurePosixPath

from check_preview_redistribution import (
    MAX_LICENSE_BYTES,
    EmbeddedFile,
    appimage_squashfs_offset,
    deb_tar_payload,
    rpm_cpio_payload,
)
from check_release_license_compliance import path_is_reparse
from collect_unsigned_runtime import DEFAULT_LIMITS, Observations, cpio_members
from stage_linux_runtime_licenses import LICENSE_COMPONENTS, LICENSE_ROOT, is_runtime_license_member

REQUIRED_LICENSE_PATHS = {
    LICENSE_ROOT / "cpython/LICENSE.txt",
    LICENSE_ROOT / "cryptography/LICENSE",
    LICENSE_ROOT / "cryptography/LICENSE.APACHE",
    LICENSE_ROOT / "cryptography/LICENSE.BSD",
}


def tar_license_members(archive: tarfile.TarFile) -> Iterator[tuple[PurePosixPath, bytes]]:
    for member in archive:
        path = PurePosixPath(member.name)
        if path in LICENSE_ROOT.parents and not member.isdir():
            raise ValueError(f"invalid Linux runtime license directory: {member.name}")
        if not path.is_relative_to(LICENSE_ROOT):
            continue
        if not is_runtime_license_member(path, directory=member.isdir()):
            raise ValueError(f"unexpected Linux runtime license path: {member.name}")
        if member.isdir():
            continue
        if not member.isfile() or not 0 < member.size <= MAX_LICENSE_BYTES:
            raise ValueError(f"invalid Linux runtime license file: {member.name}")
        stream = archive.extractfile(member)
        if stream is None:
            raise ValueError(f"unreadable Linux runtime license file: {member.name}")
        with stream:
            yield path, stream.read()


def appimage_license_members(archive: Path) -> Iterator[tuple[PurePosixPath, bytes]]:
    with tempfile.TemporaryDirectory(prefix="row-linux-licenses-") as temporary:
        destination = Path(temporary) / "filesystem"
        command = [
            "unsquashfs", "-dest", str(destination), "-offset", str(appimage_squashfs_offset(archive)),
            "-no-wildcards", str(archive), LICENSE_ROOT.as_posix(),
        ]
        try:
            result = subprocess.run(command, capture_output=True, timeout=300, check=False)
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            raise ValueError(f"cannot inspect {archive.name} with unsquashfs: {exc}") from exc
        if result.returncode:
            detail = result.stderr.decode("utf-8", errors="replace").strip()[:300]
            raise ValueError(f"cannot read runtime licenses from {archive.name}: {detail}")
        root = destination / LICENSE_ROOT
        for part in (*reversed(LICENSE_ROOT.parents), LICENSE_ROOT):
            if path_is_reparse(destination / part):
                raise ValueError(f"linked Linux runtime license directory: {part}")
        for entry in root.rglob("*"):
            path = PurePosixPath(entry.relative_to(destination).as_posix())
            directory = entry.is_dir()
            if path_is_reparse(entry) or not is_runtime_license_member(path, directory=directory):
                raise ValueError(f"unexpected Linux runtime license path: {path}")
            if not directory:
                if not entry.is_file() or not 0 < entry.stat().st_size <= MAX_LICENSE_BYTES:
                    raise ValueError(f"invalid Linux runtime license file: {path}")
                yield path, entry.read_bytes()


def license_members(archive: Path) -> Iterator[tuple[PurePosixPath, bytes]]:
    suffix = archive.suffix.lower()
    if suffix == ".rpm":
        for name, data in cpio_members(rpm_cpio_payload(archive), Observations(DEFAULT_LIMITS)):
            path = PurePosixPath(name)
            if path.is_relative_to(LICENSE_ROOT):
                yield path, data
    elif suffix == ".deb":
        with tarfile.open(fileobj=io.BytesIO(deb_tar_payload(archive)), mode="r:") as payload:
            yield from tar_license_members(payload)
    elif suffix == ".appimage":
        yield from appimage_license_members(archive)
    elif archive.name.endswith(".tar.gz"):
        with tarfile.open(archive, mode="r:gz") as payload:
            yield from tar_license_members(payload)
    else:
        raise ValueError(f"unsupported Linux license package: {archive.name}")


def read_runtime_licenses(archive: Path) -> list[EmbeddedFile]:
    records = {}
    for path, data in license_members(archive):
        if path in records or not is_runtime_license_member(path) or not 0 < len(data) <= MAX_LICENSE_BYTES:
            raise ValueError(f"{archive.name} has an invalid or duplicate runtime license: {path}")
        records[path] = data

    components = {path.relative_to(LICENSE_ROOT).parts[0] for path in records}
    missing_components = LICENSE_COMPONENTS - components
    missing_paths = REQUIRED_LICENSE_PATHS - records.keys()
    if missing_components or missing_paths:
        raise ValueError(
            f"{archive.name} is missing Linux runtime licenses "
            f"(components {sorted(missing_components)}, files {sorted(map(str, missing_paths))})"
        )
    return [EmbeddedFile(path.as_posix(), data) for path, data in sorted(records.items())]

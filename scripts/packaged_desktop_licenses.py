"""Read frozen runtime licenses from Windows and macOS native release packages."""

from __future__ import annotations

import stat
import tempfile
import zipfile
from collections.abc import Iterator
from pathlib import Path, PurePosixPath

from check_preview_redistribution import (
    MAX_LICENSE_BYTES,
    EmbeddedFile,
    pkg_cpio_payload,
    seven_zip_members,
    seven_zip_read,
    windows_installer_payload,
)
from check_release_license_compliance import path_is_reparse
from stage_runtime_licenses import LICENSE_PATH_PART, LICENSE_PROFILES, RuntimeLicense

WINDOWS_LICENSE_ROOT = PurePosixPath("docs/licenses/runtime")
MSI_LICENSE_DIRS = tuple(
    PurePosixPath(folder) / "Remote Ops Workspace" / WINDOWS_LICENSE_ROOT
    for folder in ("PFiles", "PFiles64", "Program Files", "Program Files (x86)")
)
DMG_LICENSE_ROOT = PurePosixPath("Remote Ops Workspace.app/Contents/Resources/licenses/runtime")
PKG_LICENSE_ROOT = PurePosixPath("Applications") / DMG_LICENSE_ROOT
REQUIRED_BASE_LICENSES = {"cpython/LICENSE.txt", "pyinstaller/COPYING.txt"}
REQUIRED_CRYPTOGRAPHY_LICENSES = {"cryptography/LICENSE", "cryptography/LICENSE.APACHE", "cryptography/LICENSE.BSD"}


def zip_runtime_members(archive: Path) -> Iterator[EmbeddedFile]:
    with zipfile.ZipFile(archive) as package:
        for item in package.infolist():
            path = PurePosixPath(item.filename)
            mode = stat.S_IFMT(item.external_attr >> 16)
            if path in WINDOWS_LICENSE_ROOT.parents and (not item.is_dir() or mode not in (0, stat.S_IFDIR)):
                raise ValueError(f"{archive.name} has a linked runtime license directory: {path}")
            if not path.is_relative_to(WINDOWS_LICENSE_ROOT):
                continue
            if item.is_dir() and mode in (0, stat.S_IFDIR):
                continue
            if mode not in (0, stat.S_IFREG) or item.flag_bits & 1 or not 0 < item.file_size <= MAX_LICENSE_BYTES:
                raise ValueError(f"{archive.name} has an invalid runtime license: {path}")
            yield EmbeddedFile(path.as_posix(), package.read(item))


def windows_installer_members(archive: Path) -> Iterator[tuple[PurePosixPath, EmbeddedFile]]:
    with windows_installer_payload(archive, WINDOWS_LICENSE_ROOT.as_posix()) as extracted:
        roots = MSI_LICENSE_DIRS if archive.suffix == ".msi" else (PurePosixPath("app") / WINDOWS_LICENSE_ROOT,)
        for candidate in roots:
            if any(path_is_reparse(extracted / part) for part in (*candidate.parents, candidate)):
                raise ValueError(f"{archive.name} has a linked runtime license directory: {candidate}")
            root = extracted / candidate
            for entry in root.rglob("*"):
                path = PurePosixPath(entry.relative_to(extracted).as_posix())
                if path_is_reparse(entry):
                    raise ValueError(f"{archive.name} has a linked runtime license: {path}")
                if entry.is_dir():
                    continue
                if not entry.is_file() or not 0 < entry.stat().st_size <= MAX_LICENSE_BYTES:
                    raise ValueError(f"{archive.name} has an invalid runtime license: {path}")
                yield candidate, EmbeddedFile(path.as_posix(), entry.read_bytes())


def macos_archive_members(
    archive: Path, root: PurePosixPath, *, archive_format: str | None = None,
) -> Iterator[EmbeddedFile]:
    for record in seven_zip_members(archive, archive_format=archive_format):
        name = record.get("Path", "")
        path = PurePosixPath(name)
        mode = record.get("Mode", "")
        if path == root or path in root.parents:
            if not mode.startswith("d") or record.get("Symbolic Link"):
                raise ValueError(f"{archive.name} has a linked runtime license directory: {path}")
            continue
        if not path.is_relative_to(root):
            continue
        if mode.startswith("d") and not record.get("Symbolic Link"):
            continue
        size = record.get("Size", "")
        if (
            not mode.startswith("-") or record.get("Symbolic Link") or record.get("Links", "1") != "1"
            or not size.isascii() or not size.isdecimal() or not 0 < int(size) <= MAX_LICENSE_BYTES
        ):
            raise ValueError(f"{archive.name} has an invalid runtime license: {path}")
        data = seven_zip_read(archive, name, archive_format=archive_format)
        if len(data) != int(size):
            raise ValueError(f"{archive.name} has an inconsistent runtime license size: {path}")
        yield EmbeddedFile(path.as_posix(), data)


def runtime_members(archive: Path) -> Iterator[tuple[PurePosixPath, EmbeddedFile]]:
    suffix = archive.suffix
    if suffix == ".zip":
        yield from ((WINDOWS_LICENSE_ROOT, member) for member in zip_runtime_members(archive))
    elif suffix in {".exe", ".msi"}:
        yield from windows_installer_members(archive)
    elif suffix == ".dmg":
        yield from ((DMG_LICENSE_ROOT, member) for member in macos_archive_members(archive, DMG_LICENSE_ROOT))
    elif suffix == ".pkg":
        with tempfile.TemporaryDirectory(prefix="row-pkg-runtime-licenses-") as temporary:
            payload = Path(temporary) / "payload.cpio"
            payload.write_bytes(pkg_cpio_payload(archive))
            yield from (
                (PKG_LICENSE_ROOT, member) for member in macos_archive_members(payload, PKG_LICENSE_ROOT, archive_format="Cpio")
            )
    else:
        raise ValueError(f"unsupported desktop license package: {archive.name}")


def read_desktop_runtime_licenses(archive: Path, target: str) -> list[RuntimeLicense]:
    profile = "windows-x86" if target == "windows-x86" else "desktop"
    components = {"cpython", *LICENSE_PROFILES[profile]}
    required_files = REQUIRED_BASE_LICENSES | (REQUIRED_CRYPTOGRAPHY_LICENSES if profile == "desktop" else set())
    found = {}
    roots = set()
    for root, member in runtime_members(archive):
        relative = PurePosixPath(member.path).relative_to(root)
        key = relative.as_posix()
        if (
            len(relative.parts) < 2 or relative.parts[0] not in components or key.casefold() in found
            or any(not LICENSE_PATH_PART.fullmatch(part) for part in relative.parts)
        ):
            raise ValueError(f"{archive.name} has an invalid or duplicate runtime license: {member.path}")
        roots.add(root)
        found[key.casefold()] = (relative, member)

    observed = {relative.parts[0] for relative, _ in found.values()}
    paths = {relative.as_posix() for relative, _ in found.values()}
    if len(roots) > 1 or not components <= observed or not required_files <= paths:
        raise ValueError(
            f"{archive.name} has an incomplete runtime license inventory "
            f"(missing components {sorted(components - observed)}, files {sorted(required_files - paths)})"
        )
    return [
        RuntimeLicense(member.path, member.data, relative.parts[0])
        for relative, member in sorted(found.values())
    ]

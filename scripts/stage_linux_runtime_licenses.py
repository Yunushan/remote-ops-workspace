#!/usr/bin/env python3
"""Copy license files from the Python runtime and installed Linux bundle inputs."""

from __future__ import annotations

import argparse
import re
import sysconfig
from importlib.metadata import Distribution, PackageNotFoundError, distribution
from pathlib import Path, PurePosixPath

FROZEN_DISTRIBUTIONS = (
    "bcrypt", "cffi", "cryptography", "pyasynchat", "pyasyncore", "pycparser",
    "pyftpdlib", "pyinstaller", "pyopenssl", "truststore",
)
LICENSE_ROOT = PurePosixPath("usr/share/doc/remote-ops-workspace/licenses")
LICENSE_COMPONENTS = {"cpython", *FROZEN_DISTRIBUTIONS}
LICENSE_PATH_PART = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


def is_runtime_license_member(path: PurePosixPath, *, directory: bool = False) -> bool:
    if path.anchor == "/":
        path = path.relative_to("/")
    if path == LICENSE_ROOT:
        return directory
    if not path.is_relative_to(LICENSE_ROOT):
        return False
    component, *relative = path.relative_to(LICENSE_ROOT).parts
    return (
        component in LICENSE_COMPONENTS
        and (directory or bool(relative))
        and all(LICENSE_PATH_PART.fullmatch(part) for part in relative)
    )


def copy_license(source: Path, destination: Path) -> None:
    if not source.is_file() or source.stat().st_size == 0:
        raise ValueError(f"license file is missing or empty: {source.name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(source.read_bytes())
    destination.chmod(0o644)


def copy_distribution_licenses(installed: Distribution, destination: Path) -> None:
    files = {}
    for entry in installed.files or ():
        parts = entry.parts
        if len(parts) < 3 or not parts[0].endswith(".dist-info") or parts[1] != "licenses":
            continue
        relative = PurePosixPath(*parts[2:])
        if relative in files or any(not LICENSE_PATH_PART.fullmatch(part) for part in relative.parts):
            raise ValueError(f"{installed.name} has an invalid installed license path")
        files[relative] = Path(entry.locate())

    declared = set(installed.metadata.get_all("License-File", ()))
    if not files or declared - {relative.as_posix() for relative in files}:
        raise ValueError(f"{installed.name} has missing installed license records")
    for relative, source in sorted(files.items()):
        copy_license(source, destination / relative)


def stage(destination: Path) -> None:
    copy_license(Path(sysconfig.get_path("stdlib")) / "LICENSE.txt", destination / "cpython/LICENSE.txt")
    for component in FROZEN_DISTRIBUTIONS:
        try:
            installed = distribution(component)
        except PackageNotFoundError:
            # Manual builds may omit optional dependencies. Release jobs pin these inputs.
            continue
        copy_distribution_licenses(installed, destination / component)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    stage(parser.parse_args().destination)

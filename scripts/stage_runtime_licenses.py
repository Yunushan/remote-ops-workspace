#!/usr/bin/env python3
"""Copy license files from the frozen Python runtime and installed bundle inputs."""

from __future__ import annotations

import argparse
import re
import sys
import sysconfig
from importlib.metadata import Distribution, PackageNotFoundError, distribution
from pathlib import Path, PurePosixPath
from typing import NamedTuple

FROZEN_DISTRIBUTIONS = (
    "bcrypt", "cffi", "cryptography", "pyasynchat", "pyasyncore", "pycparser",
    "pyftpdlib", "pyinstaller", "pyopenssl", "truststore",
)
LICENSE_PROFILES = {
    "linux": FROZEN_DISTRIBUTIONS,
    "desktop": (*FROZEN_DISTRIBUTIONS, "pyqt6-sip"),
    "windows-x86": ("pyinstaller",),
}
LICENSE_PATH_PART = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]*")


class RuntimeLicense(NamedTuple):
    path: str
    data: bytes
    component: str


def copy_license(source: Path, destination: Path) -> None:
    if not source.is_file() or source.stat().st_size == 0:
        raise ValueError(f"license file is missing or empty: {source.name}")
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(source.read_bytes())
    destination.chmod(0o644)


def copy_distribution_licenses(installed: Distribution, destination: Path) -> None:
    files = {}
    declared = set(installed.metadata.get_all("License-File", ()))
    for entry in installed.files or ():
        parts = entry.parts
        if len(parts) < 2 or not parts[0].endswith(".dist-info"):
            continue
        license_parts = parts[2:] if parts[1] == "licenses" else parts[1:]
        relative = PurePosixPath(*license_parts)
        if parts[1] != "licenses" and relative.as_posix() not in declared:
            continue
        if (
            not relative.parts or relative in files
            or any(not LICENSE_PATH_PART.fullmatch(part) for part in relative.parts)
        ):
            raise ValueError(f"{installed.name} has an invalid installed license path")
        files[relative] = Path(entry.locate())

    if not files or declared - {relative.as_posix() for relative in files}:
        raise ValueError(f"{installed.name} has missing installed license records")
    for relative, source in sorted(files.items()):
        copy_license(source, destination / relative)


def stage(destination: Path, profile: str = "linux") -> None:
    python_license = Path(sysconfig.get_path("stdlib")) / "LICENSE.txt"
    if not python_license.is_file():
        python_license = Path(sys.base_prefix) / "LICENSE.txt"
    copy_license(python_license, destination / "cpython/LICENSE.txt")
    for component in LICENSE_PROFILES[profile]:
        try:
            installed = distribution(component)
        except PackageNotFoundError:
            # Manual builds may omit optional dependencies. Release jobs pin these inputs.
            continue
        copy_distribution_licenses(installed, destination / component)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    parser.add_argument("--profile", choices=LICENSE_PROFILES, default="linux")
    args = parser.parse_args()
    stage(args.destination, args.profile)

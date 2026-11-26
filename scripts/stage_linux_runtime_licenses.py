#!/usr/bin/env python3
"""Stage the frozen Linux runtime licenses and define their package paths."""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
from collections.abc import Iterable
from pathlib import Path, PurePosixPath

if __package__:
    from .debian_server_notices import VERSION_RE as DEBIAN_VERSION_RE
    from .stage_runtime_licenses import FROZEN_DISTRIBUTIONS, LICENSE_PATH_PART, copy_license, stage
else:
    from debian_server_notices import VERSION_RE as DEBIAN_VERSION_RE
    from stage_runtime_licenses import FROZEN_DISTRIBUTIONS, LICENSE_PATH_PART, copy_license, stage

LICENSE_ROOT = PurePosixPath("usr/share/doc/remote-ops-workspace/licenses")
LICENSE_COMPONENTS = {"cpython", *FROZEN_DISTRIBUTIONS}
SYSTEM_LICENSE_PREFIX = "system-"
SYSTEM_VERSION_FILE = "package-version.txt"
DPKG_PACKAGE = re.compile(r"([a-z0-9][a-z0-9+.-]+)(?::[a-z0-9-]+)?")
SYSTEM_LIBRARY_DIRS = tuple(Path(name) for name in ("/lib", "/lib64", "/usr/lib", "/usr/lib64"))
SYSTEM_DOC_ROOT = Path("/usr/share/doc")


def dpkg_owner(path: Path, query: str) -> str | None:
    candidates = [path.as_posix()]
    if candidates[0].startswith("/usr/lib"):
        candidates.append(candidates[0].removeprefix("/usr"))
    for candidate in candidates:
        result = subprocess.run([query, "-S", "--", candidate], text=True, capture_output=True, timeout=10)
        if result.returncode == 1 and not result.stdout:
            continue
        result.check_returncode()
        owners = set()
        for line in result.stdout.splitlines():
            owner, _, matched = line.rpartition(": ")
            if matched == candidate and DPKG_PACKAGE.fullmatch(owner):
                owners.add(owner)
        if len(owners) != 1:
            raise ValueError(f"ambiguous Debian owner for bundled system library: {path.name}")
        return owners.pop()
    return None


def stage_system_runtime_notices(libraries: Iterable[Path], destination: Path) -> None:
    query = shutil.which("dpkg-query")
    if query is None:
        return
    paths = {source.resolve() for source in libraries}
    system = (path for path in sorted(paths) if any(path.is_relative_to(root) for root in SYSTEM_LIBRARY_DIRS))
    owners = {owner for path in system if (owner := dpkg_owner(path, query)) is not None}
    packages = {owner.split(":", 1)[0]: owner for owner in owners}
    if len(packages) != len(owners):
        raise ValueError("multiple architectures of a Debian package supplied bundled system libraries")
    for package, owner in sorted(packages.items()):
        output = destination / f"{SYSTEM_LICENSE_PREFIX}{package}"
        version = subprocess.run(
            [query, "-W", "-f", "${Version}\n", "--", owner],
            check=True, text=True, capture_output=True, timeout=10,
        ).stdout.strip()
        if DEBIAN_VERSION_RE.fullmatch(version) is None:
            raise ValueError(f"invalid version for bundled Debian package: {owner}")
        source = (SYSTEM_DOC_ROOT / package / "copyright").resolve(strict=True)
        if not source.is_relative_to(SYSTEM_DOC_ROOT) or source.name != "copyright":
            raise ValueError(f"unexpected copyright location for bundled Debian package: {owner}")
        copy_license(source, output / "copyright")
        (output / SYSTEM_VERSION_FILE).write_bytes(f"{version}\n".encode("ascii"))


def is_runtime_license_member(path: PurePosixPath, *, directory: bool = False) -> bool:
    if path.anchor == "/":
        path = path.relative_to("/")
    if path == LICENSE_ROOT:
        return directory
    if not path.is_relative_to(LICENSE_ROOT):
        return False
    component, *relative = path.relative_to(LICENSE_ROOT).parts
    if component.startswith(SYSTEM_LICENSE_PREFIX):
        owner = component.removeprefix(SYSTEM_LICENSE_PREFIX)
        return (
            ":" not in owner
            and DPKG_PACKAGE.fullmatch(owner) is not None
            and (relative == [] if directory else relative in (["copyright"], [SYSTEM_VERSION_FILE]))
        )
    return (
        component in LICENSE_COMPONENTS
        and (directory or bool(relative))
        and all(LICENSE_PATH_PART.fullmatch(part) for part in relative)
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    stage(parser.parse_args().destination)

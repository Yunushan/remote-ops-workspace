"""Derive Debian shared-library dependencies from staged native executables."""

from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from collections.abc import Iterable
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.linux_frozen_elf import archive_elf_members  # noqa: E402

# Package names shared by the supported Debian and Ubuntu builders.
LIBRARY_PACKAGES = {
    "libavahi-client.so.3": "libavahi-client3",
    "libavahi-common.so.3": "libavahi-common3",
    "libcom_err.so.2": "libcom-err2",
    "libcrypt.so.1": "libcrypt1",
    "libcrypto.so.3": "libssl3t64",
    "libgcc_s.so.1": "libgcc-s1",
    "libgssapi_krb5.so.2": "libgssapi-krb5-2",
    "libk5crypto.so.3": "libk5crypto3",
    "libkrb5.so.3": "libkrb5-3",
    "libpam.so.0": "libpam0g",
    "libselinux.so.1": "libselinux1",
    "libssl.so.3": "libssl3t64",
    "libstdc++.so.6": "libstdc++6",
    "libtinfo.so.6": "libtinfo6",
    "libvncclient.so.1": "libvncclient1",
    "libvncserver.so.1": "libvncserver1",
    "libwrap.so.0": "libwrap0",
    "libX11.so.6": "libx11-6",
    "libXdamage.so.1": "libxdamage1",
    "libXext.so.6": "libxext6",
    "libXfixes.so.3": "libxfixes3",
    "libXi.so.6": "libxi6",
    "libXinerama.so.1": "libxinerama1",
    "libXrandr.so.2": "libxrandr2",
    "libXtst.so.6": "libxtst6",
    "libz.so.1": "zlib1g",
}
GLIBC_LIBRARIES = {
    "ld-linux-aarch64.so.1", "ld-linux-armhf.so.3", "ld-linux-x86-64.so.2", "ld-linux.so.2",
    "libanl.so.1", "libc.so.6", "libdl.so.2", "libm.so.6", "libpthread.so.0",
    "libresolv.so.2", "librt.so.1", "libutil.so.1",
}
PACKAGE_NAME = r"[a-z0-9][a-z0-9+.-]+"
RELATIONSHIP = re.compile(rf"{PACKAGE_NAME}(?: \(>= [0-9]+(?:\.[0-9]+)+\))?")


def elf_requirements(path: Path) -> tuple[set[str], set[tuple[int, ...]]]:
    result = subprocess.run(
        ["readelf", "--wide", "--dynamic", "--version-info", str(path.resolve())],
        check=True, capture_output=True, text=True,
        env={**os.environ, "LC_ALL": "C"}, timeout=30,
    )
    needed = set(re.findall(r"\(NEEDED\).*Shared library: \[([^\]]+)\]", result.stdout))
    versions = set()
    requirements = result.stdout.partition("Version needs section ")[2]
    for name in re.findall(r"\bName: GLIBC_(\S+)", requirements):
        if name == "ABI_DT_RELR":
            versions.add((2, 36))
        elif re.fullmatch(r"[0-9]+(?:\.[0-9]+)+", name):
            versions.add(tuple(int(part) for part in name.split(".")))
        else:
            raise ValueError(f"{path.name} requires an unsupported glibc version: GLIBC_{name}")
    return needed, versions


def launcher_archive_requirements(launcher: Path) -> tuple[set[str], set[tuple[int, ...]]]:
    provided = set()
    needed: set[str] = set()
    versions: set[tuple[int, ...]] = set()
    with TemporaryDirectory() as directory:
        member = Path(directory) / "archive-elf"
        for name, data in archive_elf_members(launcher):
            # The one-file launcher adds the extraction root to its library search path.
            if len(PurePosixPath(name).parts) == 1:
                provided.add(name)
            member.write_bytes(data)
            libraries, glibc = elf_requirements(member)
            needed.update(libraries)
            versions.update(glibc)
    return needed - provided, versions


def debian_dependencies(launcher: Path, executables: Iterable[Path]) -> list[str]:
    needed, versions = launcher_archive_requirements(launcher)
    for path in (launcher, *executables):
        libraries, glibc = elf_requirements(path)
        needed.update(libraries)
        versions.update(glibc)
    unknown = needed - GLIBC_LIBRARIES - LIBRARY_PACKAGES.keys()
    if unknown:
        raise ValueError(f"Debian package mapping is missing for shared libraries: {', '.join(sorted(unknown))}")
    packages = {LIBRARY_PACKAGES[library] for library in needed if library not in GLIBC_LIBRARIES}
    if versions:
        minimum = ".".join(map(str, max(versions)))
        packages.add(f"libc6 (>= {minimum})")
    elif needed & GLIBC_LIBRARIES:
        packages.add("libc6")
    return sorted(packages)


def dependency_field(dependencies: object) -> str:
    if (
        not isinstance(dependencies, list) or not dependencies
        or not all(isinstance(value, str) and RELATIONSHIP.fullmatch(value) for value in dependencies)
        or dependencies != sorted(set(dependencies))
        or len({item.split()[0] for item in dependencies}) != len(dependencies)
    ):
        raise ValueError("Debian runtime metadata requires a sorted list of unique library dependencies")
    return ", ".join(dependencies)


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Print the Debian Depends field for a frozen CLI.")
    parser.add_argument("launcher", type=Path)
    args = parser.parse_args(argv)
    print(dependency_field(debian_dependencies(args.launcher, ())))


if __name__ == "__main__":
    main()

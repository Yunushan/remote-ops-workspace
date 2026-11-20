"""Generate RPM requirements for the ELF libraries inside the frozen CLI."""

from __future__ import annotations

import argparse
import re
import subprocess
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory

from scripts.linux_frozen_elf import archive_elf_members

CAPABILITY = re.compile(r"[A-Za-z0-9._+/-]+(?:\([A-Za-z0-9._+-]*\)){0,2}")


def elf_capabilities(elfdeps: Path, elf: Path, *options: str) -> set[str]:
    result = subprocess.run(
        [str(elfdeps), *options, str(elf)], capture_output=True, check=True,
        encoding="utf-8", timeout=30,
    )
    capabilities = set(result.stdout.splitlines())
    if any(not CAPABILITY.fullmatch(capability) for capability in capabilities):
        raise ValueError("RPM ELF generator emitted an invalid capability")
    return capabilities


def archive_rpm_requirements(launcher: Path, elfdeps: Path) -> list[str]:
    requires: set[str] = set()
    provides: set[str] = set()
    with TemporaryDirectory() as directory:
        elf = Path(directory) / "archive-elf"
        for name, data in archive_elf_members(launcher):
            elf.write_bytes(data)
            requires.update(elf_capabilities(elfdeps, elf, "--requires"))
            # The PyInstaller loader searches the extraction root for this
            # exact name. An incompatible symbol version still needs a provider.
            if len(PurePosixPath(name).parts) == 1:
                provides.update(
                    capability
                    for capability in elf_capabilities(elfdeps, elf, "--provides", "--no-fake-soname")
                    if capability.partition("(")[0] == name
                )
    external = sorted(requires - provides)
    bundled = {capability.partition("(")[0] for capability in provides}
    incompatible = [capability for capability in external if capability.partition("(")[0] in bundled]
    if incompatible:
        raise ValueError(f"Frozen CLI archive contains incompatible libraries: {', '.join(incompatible)}")
    return external


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Print the RPM spec requirements for a frozen CLI archive.")
    parser.add_argument("launcher", type=Path)
    args = parser.parse_args(argv)
    rpm_config = subprocess.check_output(["rpm", "--eval", "%{_rpmconfigdir}"], encoding="utf-8", timeout=30)
    elfdeps = Path(rpm_config.strip()) / "elfdeps"
    for capability in archive_rpm_requirements(args.launcher, elfdeps):
        print(f"Requires: {capability}")


if __name__ == "__main__":
    main()

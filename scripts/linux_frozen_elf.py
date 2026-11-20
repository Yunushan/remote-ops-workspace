"""Read the embedded ELF files in a PyInstaller one-file launcher."""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path


def archive_elf_members(launcher: Path) -> Iterator[tuple[str, bytes]]:
    from PyInstaller.archive.readers import CArchiveReader

    archive = CArchiveReader(str(launcher))
    for name, entry in archive.toc.items():
        if entry[-1] == "b":
            data = archive.extract(name)
            if data.startswith(b"\x7fELF"):
                yield name, data

"""Check the target architecture of a Linux native launcher without running it."""

from __future__ import annotations

import argparse
import struct
import sys
from pathlib import Path

# ELF class, machine and complete ELF header size.
TARGETS = {
    "x86_64": (2, 62, 64),
    "i686": (1, 3, 52),
    "armhf": (1, 40, 52),
    "aarch64": (2, 183, 64),
}


def validate_elf(path: Path, target: str) -> None:
    elf_class, machine, header_size = TARGETS[target]
    with path.open("rb") as handle:
        header = handle.read(header_size)
    if len(header) != header_size or header[:7] != b"\x7fELF" + bytes((elf_class, 1, 1)):
        raise ValueError(f"expected a complete little-endian ELF header for {target}")
    kind, actual_machine, version = struct.unpack_from("<HHI", header, 16)
    if kind not in (2, 3) or version != 1 or actual_machine != machine:
        raise ValueError(f"ELF executable type, version or machine does not match {target}")
    if struct.unpack_from("<H", header, header_size - 12)[0] != header_size:
        raise ValueError(f"ELF header size does not match {target}")
    if target == "armhf":
        flags, = struct.unpack_from("<I", header, 36)
        # Require EABI v5 and hard-float, with no conflicting soft-float bit.
        if flags & 0xFF000600 != 0x05000400:
            raise ValueError("ARM executable does not declare the EABI v5 hard-float ABI")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=sorted(TARGETS), required=True)
    parser.add_argument("--executable", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        validate_elf(args.executable, args.target)
    except (OSError, ValueError) as exc:
        print(f"Linux native architecture check failed: {exc}", file=sys.stderr)
        return 1
    print(f"Linux native launcher matches {args.target}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

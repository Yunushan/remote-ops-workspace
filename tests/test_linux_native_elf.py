from __future__ import annotations

import struct
from pathlib import Path

import pytest

from scripts.check_linux_native_elf import main, validate_elf


def launcher_header(elf_class: int, machine: int, *, flags: int = 0) -> bytearray:
    size = 52 if elf_class == 1 else 64
    header = bytearray(size)
    header[:7] = b"\x7fELF" + bytes((elf_class, 1, 1))
    struct.pack_into("<HHI", header, 16, 3, machine, 1)
    struct.pack_into("<I", header, size - 16, flags)
    struct.pack_into("<H", header, size - 12, size)
    return header


@pytest.mark.parametrize(
    ("target", "elf_class", "machine", "flags"),
    [("x86_64", 2, 62, 0), ("i686", 1, 3, 0), ("armhf", 1, 40, 0x05000400), ("aarch64", 2, 183, 0)],
)
def test_native_launcher_matches_packaging_architecture(
    tmp_path: Path, target: str, elf_class: int, machine: int, flags: int,
) -> None:
    executable = tmp_path / "row"
    executable.write_bytes(launcher_header(elf_class, machine, flags=flags))
    assert main(["--target", target, "--executable", str(executable)]) == 0


@pytest.mark.parametrize("flags", [0x05000200, 0x05000600, 0x04000400, 0])
def test_armhf_refuses_wrong_or_ambiguous_abi(tmp_path: Path, flags: int) -> None:
    executable = tmp_path / "row"
    executable.write_bytes(launcher_header(1, 40, flags=flags))
    with pytest.raises(ValueError, match="hard-float ABI"):
        validate_elf(executable, "armhf")


def test_native_launcher_refuses_wrong_class_machine_or_truncated_header(tmp_path: Path) -> None:
    executable = tmp_path / "row"
    executable.write_bytes(launcher_header(2, 62))
    assert main(["--target", "i686", "--executable", str(executable)]) == 1
    with pytest.raises(ValueError, match="machine"):
        validate_elf(executable, "aarch64")
    executable.write_bytes(launcher_header(2, 62)[:-1])
    with pytest.raises(ValueError, match="complete"):
        validate_elf(executable, "x86_64")


def test_native_builder_checks_launcher_before_packaging() -> None:
    text = Path("scripts/make_linux_native.sh").read_text(encoding="utf-8")
    check = 'scripts/check_linux_native_elf.py --target "$APPIMAGE_ARCH" --executable "$ROW_BIN"'
    assert text.index('ROW_BIN="$PY_DIST/row"') < text.index(check) < text.index('PKGROOT="$BUILD_DIR/pkgroot"')

from __future__ import annotations

import shutil
import struct
import subprocess
import sys
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


@pytest.mark.skipif(sys.platform != "linux" or shutil.which("bash") is None, reason="requires Linux Bash")
def test_legacy_smoke_refuses_wrong_launcher_before_execution(tmp_path: Path) -> None:
    source = Path("scripts/smoke_linux_native.sh").read_text(encoding="utf-8")
    start = source.index("verify_row() {\n")
    end = source.index("\n}\n", start) + 3
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copyfile("scripts/check_linux_native_elf.py", scripts / "check_linux_native_elf.py")
    executable = tmp_path / "row"
    executable.write_text("#!/bin/sh\ntouch launched\necho 1.0.27\n", encoding="utf-8")
    executable.chmod(0o755)
    probe = (
        "set -euo pipefail\n" + source[start:end]
        + '\nTARGET=linux-i386 APPIMAGE_ARCH=i686 VERSION=1.0.27\n'
        + 'run_row_command() { "$1" --version; }\n'
        + 'verify_row ./row direct fixture deb/usr/bin/row install\n'
    )
    result = subprocess.run(
        ["bash", "-c", probe], cwd=tmp_path, capture_output=True, text=True, timeout=30, check=False,
    )
    assert result.returncode != 0
    assert "Linux native architecture check failed" in result.stderr
    assert not (tmp_path / "launched").exists()

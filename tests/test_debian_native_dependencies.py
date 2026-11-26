import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import debian_native_dependencies as dependencies


def test_readelf_collects_needed_libraries_and_required_glibc_versions(tmp_path, monkeypatch):
    output = """
 0x0000000000000001 (NEEDED)             Shared library: [libssl.so.3]
 0x0000000000000001 (NEEDED)             Shared library: [libc.so.6]
Version definition section '.gnu.version_d' contains 1 entry:
  000000: Rev: 1  Flags: none  Index: 1  Cnt: 1  Name: GLIBC_2.99
Version needs section '.gnu.version_r' contains 1 entry:
  000000: Version: 1  File: libc.so.6  Cnt: 3
  0x0010:   Name: GLIBC_2.9  Flags: none  Version: 5
  0x0020:   Name: GLIBC_2.34  Flags: none  Version: 4
  0x0030:   Name: GLIBC_ABI_DT_RELR  Flags: none  Version: 3
"""
    monkeypatch.setattr(dependencies.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(stdout=output))
    assert dependencies.elf_requirements(tmp_path / "native") == (
        {"libssl.so.3", "libc.so.6"}, {(2, 9), (2, 34), (2, 36)},
    )


def test_dependency_calculation_includes_daemons_and_archive_glibc(monkeypatch):
    launcher = Path("row")
    helper = Path("sshd-auth")
    monkeypatch.setattr(dependencies, "launcher_archive_requirements", lambda _: ({"libc.so.6"}, {(2, 38)}))
    requirements = {
        launcher: ({"libz.so.1", "libc.so.6"}, {(2, 14)}),
        helper: ({"libcrypto.so.3", "libssl.so.3", "libpam.so.0"}, {(2, 36)}),
    }
    monkeypatch.setattr(dependencies, "elf_requirements", requirements.__getitem__)
    assert dependencies.debian_dependencies(launcher, [helper]) == [
        "libc6 (>= 2.38)", "libpam0g", "libssl3t64", "zlib1g",
    ]

    requirements[helper] = ({"libunknown.so.1"}, set())
    with pytest.raises(ValueError, match=r"missing for shared libraries: libunknown\.so\.1"):
        dependencies.debian_dependencies(launcher, [helper])


def test_archive_only_satisfies_dependencies_from_root_level_elf_members(tmp_path, monkeypatch):
    def elf_requirements(path):
        if path.read_bytes() == b"\x7fELFconsumer":
            return {"libcrypto.so.3", "libpam.so.0", "libc.so.6"}, {(2, 38)}
        return set(), set()

    binaries = {
        "libpython3.14.so.1.0": b"\x7fELFconsumer",
        "libcrypto.so.3": b"\x7fELFcrypto",
        "subdir/libpam.so.0": b"\x7fELFpam",
    }
    archive = SimpleNamespace(toc={name: ("b",) for name in binaries}, extract=binaries.__getitem__)
    readers = SimpleNamespace(CArchiveReader=lambda _: archive)
    monkeypatch.setitem(sys.modules, "PyInstaller.archive.readers", readers)
    monkeypatch.setattr(dependencies, "elf_requirements", elf_requirements)
    assert dependencies.launcher_archive_requirements(tmp_path / "row") == (
        {"libpam.so.0", "libc.so.6"}, {(2, 38)},
    )


def test_cli_derives_the_plain_deb_field_from_the_launcher_and_archive(monkeypatch, capsys):
    launcher = Path("row with spaces")

    def inspect_archive(path):
        assert path == launcher
        return {"libc.so.6"}, {(2, 38)}

    def inspect_launcher(path):
        assert path == launcher
        return {"libz.so.1"}, {(2, 14)}

    monkeypatch.setattr(dependencies, "launcher_archive_requirements", inspect_archive)
    monkeypatch.setattr(dependencies, "elf_requirements", inspect_launcher)

    dependencies.main([str(launcher)])

    assert capsys.readouterr().out == "libc6 (>= 2.38), zlib1g\n"


@pytest.mark.parametrize("value", [
    [], ["libpam0g", "libpam0g"], ["libssl3t64 | libc6"],
    ["libpam0g\nConflicts: libc6"], ["libc6", "libc6 (>= 2.38)"],
])
def test_dependency_field_rejects_ambiguous_control_values(value):
    with pytest.raises(ValueError, match="sorted list of unique library dependencies"):
        dependencies.dependency_field(value)


def test_merge_debian_dependencies_keeps_the_stronger_minimum(monkeypatch):
    def compare(argv, *, check, timeout):
        assert argv == ["dpkg", "--compare-versions", "2:1.0-1", "gt", "9.0"]
        assert check is False and timeout == 30
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(dependencies.subprocess, "run", compare)
    merged = dependencies.merge_debian_dependencies(
        ["libc6 (>= 2.38)", "xserver-common (>= 9.0)"],
        "xauth, libc6, xserver-common (>= 2:1.0-1)",
    )
    assert dependencies.dependency_field(merged) == "libc6 (>= 2.38), xauth, xserver-common (>= 2:1.0-1)"


def test_merge_debian_dependencies_rejects_unreviewed_constraint_types():
    with pytest.raises(ValueError, match="unsupported Debian minimum-version relationship"):
        dependencies.merge_debian_dependencies(["libc6"], "xdmcp | xauth")

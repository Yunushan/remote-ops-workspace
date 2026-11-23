from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import rpm_native_dependencies as rpm


@pytest.mark.parametrize("missing_version", [False, True])
def test_archive_checks_exact_capabilities_from_the_extraction_root(monkeypatch, missing_version):
    members = [
        ("python/consumer.so", b"consumer"),
        ("libbundled.so.1", b"bundled"),
        ("python/libnested.so.1", b"nested"),
        ("different-name.so", b"alias"),
    ]
    monkeypatch.setattr(rpm, "archive_elf_members", lambda _: iter(members))
    needs = {
        "libbundled.so.1()(64bit)", "libbundled.so.1(BUNDLED_1)(64bit)",
        "libnested.so.1()(64bit)",
        "libalias.so.1()(64bit)", "libm.so.6(GLIBC_2.38)(64bit)",
    }
    if missing_version:
        needs.add("libbundled.so.1(BUNDLED_2)(64bit)")

    def capabilities(_tool, elf, *options):
        content = elf.read_bytes()
        if options == ("--requires",):
            return needs if content == b"consumer" else set()
        assert options == ("--provides", "--no-fake-soname")
        return {
            b"bundled": {"libbundled.so.1()(64bit)", "libbundled.so.1(BUNDLED_1)(64bit)"},
            b"nested": {"libnested.so.1()(64bit)"},
            b"alias": {"libalias.so.1()(64bit)"},
        }[content]

    monkeypatch.setattr(rpm, "elf_capabilities", capabilities)
    if missing_version:
        with pytest.raises(ValueError, match=r"incompatible libraries: libbundled\.so\.1\(BUNDLED_2\)"):
            rpm.archive_rpm_requirements(Path("row"), Path("elfdeps"))
    else:
        assert rpm.archive_rpm_requirements(Path("row"), Path("elfdeps")) == [
            "libalias.so.1()(64bit)", "libm.so.6(GLIBC_2.38)(64bit)", "libnested.so.1()(64bit)",
        ]


def test_rpm_cli_uses_the_packager_generator_and_emits_spec_lines(monkeypatch, capsys, tmp_path):
    elfdeps = tmp_path / "elfdeps"
    elfdeps.touch()
    elfdeps.chmod(0o700)

    def rpm_config(args, **_options):
        assert args == ["rpm", "--eval", "%{_rpmconfigdir}"]
        return f"{tmp_path}\n"

    def dependencies(launcher, tool):
        assert launcher == Path("row with spaces") and tool == elfdeps
        return ["libm.so.6(GLIBC_2.38)(64bit)", "libz.so.1()(64bit)"]

    monkeypatch.setattr(rpm.subprocess, "check_output", rpm_config)
    monkeypatch.setattr(rpm, "archive_rpm_requirements", dependencies)
    rpm.main(["row with spaces"])
    assert capsys.readouterr().out.splitlines() == [
        "Requires: libm.so.6(GLIBC_2.38)(64bit)", "Requires: libz.so.1()(64bit)",
    ]


@pytest.mark.parametrize("kind", ["relative", "missing", "non-executable"])
def test_rpm_generator_requires_an_absolute_executable(monkeypatch, tmp_path, kind):
    configuration = "relative" if kind == "relative" else str(tmp_path)
    monkeypatch.setattr(rpm.subprocess, "check_output", lambda *_args, **_kwargs: configuration)
    if kind == "non-executable":
        (tmp_path / "elfdeps").touch()
        monkeypatch.setattr(rpm.os, "access", lambda *_args: False)

    with pytest.raises(ValueError, match="RPM must provide an executable elfdeps"):
        rpm.rpm_elfdeps()


def test_generator_rejects_output_that_could_extend_the_rpm_spec(monkeypatch):
    monkeypatch.setattr(
        rpm.subprocess, "run",
        lambda *_args, **_kwargs: SimpleNamespace(stdout="libc.so.6()(64bit)\n%unexpected\n"),
    )
    with pytest.raises(ValueError, match="invalid capability"):
        rpm.elf_capabilities(Path("elfdeps"), Path("row"), "--requires")

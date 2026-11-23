import subprocess
from pathlib import Path

import pytest

from scripts import stage_linux_runtime_licenses as notices


def test_dpkg_owner_checks_exact_path_and_usrmerge_alias(monkeypatch):
    calls = []

    def lookup(argv, **_kwargs):
        calls.append(argv[-1])
        if argv[-1].startswith("/usr/"):
            return subprocess.CompletedProcess(argv, 1, "", "no path found")
        return subprocess.CompletedProcess(argv, 0, "libfoo:arm64: /lib/aarch64-linux-gnu/libfoo.so.1\n", "")

    monkeypatch.setattr(notices.subprocess, "run", lookup)
    assert notices.dpkg_owner(Path("/usr/lib/aarch64-linux-gnu/libfoo.so.1"), "dpkg-query") == "libfoo"
    assert calls == ["/usr/lib/aarch64-linux-gnu/libfoo.so.1", "/lib/aarch64-linux-gnu/libfoo.so.1"]


def test_only_bundled_debian_system_libraries_contribute_notices(tmp_path, monkeypatch):
    library = tmp_path / "system/lib"
    library.mkdir(parents=True)
    a, b = library / "libfoo.so.1", library / "libfoo-extra.so.1"
    bundled = tmp_path / "wheel-extension.so"
    for source in (a, b, bundled):
        source.write_bytes(b"fixture")
    documentation = tmp_path / "doc"
    copyright_file = documentation / "libfoo/copyright"
    copyright_file.parent.mkdir(parents=True)
    copyright_file.write_bytes(b"original distribution notice\r\n")

    seen = []

    def owner(path, _query):
        seen.append(path)
        return "libfoo"

    monkeypatch.setattr(notices, "SYSTEM_LIBRARY_DIRS", (library,))
    monkeypatch.setattr(notices, "SYSTEM_DOC_ROOT", documentation)
    monkeypatch.setattr(notices.shutil, "which", lambda _tool: "dpkg-query")
    monkeypatch.setattr(notices, "dpkg_owner", owner)
    out = tmp_path / "licenses"
    notices.stage_system_runtime_notices([a, b, bundled, a], out)
    assert set(seen) == {a, b} and len(seen) == 2
    assert [p.relative_to(out).as_posix() for p in out.rglob("copyright")] == ["system-libfoo/copyright"]
    assert (out / "system-libfoo/copyright").read_bytes() == copyright_file.read_bytes()
    assert notices.is_runtime_license_member(notices.LICENSE_ROOT / "system-libfoo/copyright")
    assert not notices.is_runtime_license_member(notices.LICENSE_ROOT / "system-libfoo/payload")
    assert not notices.is_runtime_license_member(notices.LICENSE_ROOT / "system-libfoo/nested/copyright")
    copyright_file.unlink()
    with pytest.raises(FileNotFoundError):
        notices.stage_system_runtime_notices([a], out)

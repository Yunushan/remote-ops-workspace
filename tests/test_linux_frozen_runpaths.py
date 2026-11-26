from __future__ import annotations

import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

from scripts.debian_native_dependencies import elf_requirements
from scripts.linux_frozen_runpaths import (
    prepare_spec,
    stage_binaries,
    stage_distribution_metadata,
    without_toolcache_runpath,
)
from scripts.qualify_deb_loader import qualify, selections

HOSTED = "/opt/hostedtoolcache/Python/3.14.10/x64/lib"


@pytest.mark.skipif(
    sys.platform != "linux" or not shutil.which("cc") or not shutil.which("readelf"),
    reason="uses native GNU ELF tools",
)
@pytest.mark.parametrize(
    ("before", "after", "legacy_rpath"),
    [
        (HOSTED, None, False),
        ("$ORIGIN:/usr/lib", "$ORIGIN:/usr/lib", False),
        (f"$ORIGIN:{HOSTED}:/usr/lib", "$ORIGIN:/usr/lib", False),
        (f"{HOSTED}:$ORIGIN", "$ORIGIN", False),
        (f"/opt/hostedtoolcache/site/lib:{HOSTED}", "/opt/hostedtoolcache/site/lib", False),
        (HOSTED, HOSTED, True),
    ],
)
def test_staged_real_elf_preserves_unrelated_search_paths(tmp_path, before, after, legacy_rpath):
    original = tmp_path / "source.so"
    linker_option = "--disable-new-dtags," if legacy_rpath else ""
    subprocess.run(
        [
            "cc",
            "-x",
            "c",
            "-",
            "-shared",
            "-fPIC",
            f"-Wl,{linker_option}-rpath,{before}",
            "-o",
            str(original),
        ],
        input=b"int answer(void) { return 42; }",
        check=True,
    )
    source_bytes = original.read_bytes()
    manifest = [("package/extension.so", str(original), "EXTENSION")]
    _, staged, _ = stage_binaries(manifest, tmp_path / "work")[0]
    assert original.read_bytes() == source_bytes
    assert (Path(staged) == original) == (before == after)
    assert without_toolcache_runpath(Path(staged).read_bytes()) == Path(staged).read_bytes()
    output = subprocess.check_output(["readelf", "--wide", "--dynamic", staged], text=True)
    paths = [
        line.split("[", 1)[1].split("]", 1)[0]
        for line in output.splitlines()
        if "(RUNPATH)" in line or "(RPATH)" in line
    ]
    assert paths == ([after] if after is not None else [])


def test_only_known_pyinstaller_spec_is_adjusted(tmp_path):
    path = tmp_path / "row.spec"
    path.write_text("# spec\npyz = PYZ(a.pure)\n", encoding="utf-8")
    prepare_spec(path)
    assert path.read_text().index("pyz = PYZ") < path.read_text().index(
        "stage_binaries(a.binaries + pyz.dependencies"
    )
    assert "a.datas = stage_distribution_metadata(a.datas" in path.read_text()
    path.write_text("unknown format", encoding="utf-8")
    with pytest.raises(ValueError, match="Unrecognized"):
        prepare_spec(path)


def test_frozen_base_library_is_independent_of_module_order(tmp_path):
    names = ["encodings/__init__.pyc", "types.pyc"]
    staged_archives = []
    for build, order in enumerate((names, names[::-1])):
        root = tmp_path / str(build)
        root.mkdir()
        archive = root / "base_library.zip"
        with zipfile.ZipFile(archive, "w") as original:
            original.comment = b"standard library"
            for name in order:
                entry = zipfile.ZipInfo(name, date_time=(2020, 1, 2, 3, 4, 6))
                entry.external_attr = 0o644 << 16
                entry.compress_type = zipfile.ZIP_DEFLATED
                original.writestr(entry, name.encode())
        source_bytes = archive.read_bytes()
        name, staged, kind = stage_distribution_metadata(
            [("base_library.zip", str(archive), "DATA")], root / "stage"
        )[0]
        assert name == "base_library.zip" and kind == "DATA"
        staged_archives.append(Path(staged).read_bytes())
        assert archive.read_bytes() == source_bytes
        with zipfile.ZipFile(staged) as output:
            assert output.namelist() == names
            assert output.comment == b"standard library"
            for entry in output.infolist():
                assert output.read(entry) == entry.filename.encode()
                assert entry.date_time == (2020, 1, 2, 3, 4, 6)
                assert entry.external_attr == 0o644 << 16
                assert entry.compress_type == zipfile.ZIP_DEFLATED
    assert staged_archives[0] == staged_archives[1]


def test_frozen_metadata_is_independent_of_install_checkout(tmp_path):
    project = "remote_ops_workspace-1.0.28.dist-info"
    expected = [f"{project}/METADATA,sha256=stable,4", f"{project}/RECORD,,"]
    staged_records = []
    for checkout in ("first", "alternate"):
        root = tmp_path / checkout
        root.mkdir()
        metadata = root / "METADATA"
        metadata.write_text("Name: remote-ops-workspace\n", encoding="utf-8")
        origin = root / "direct_url.json"
        origin.write_text(f'{{"url":"file:///{checkout}"}}', encoding="utf-8")
        record = root / "RECORD"
        installed = "\n".join([
            f"../../../bin/remote-ops-workspace,sha256={checkout},20",
            f"../../../bin/row,sha256={checkout},18",
            *expected,
            f"{project}/direct_url.json,sha256={checkout},25",
        ]) + "\n"
        record.write_text(installed, encoding="utf-8")
        unrelated = ("dependency-1.0.dist-info/direct_url.json", str(origin), "DATA")
        datas = [
            (f"{project}/{file.name}", str(file), "DATA")
            for file in (metadata, origin, record)
        ]
        staged = stage_distribution_metadata([*datas, unrelated], root / "stage")
        assert staged[0] == datas[0] and staged[-1] == unrelated
        assert [row[0] for row in staged] == [datas[0][0], datas[2][0], unrelated[0]]
        staged_records.append(Path(staged[1][1]).read_bytes())
        assert record.read_text(encoding="utf-8") == installed
    assert staged_records[0] == staged_records[1]
    assert staged_records[0].decode().splitlines() == expected


@pytest.mark.skipif(
    sys.platform != "linux" or not shutil.which("cc") or not shutil.which("readelf"),
    reason="uses native GNU ELF tools",
)
def test_shared_dynamic_string_and_final_package_check_fail_closed(tmp_path):
    value = f"$ORIGIN:{HOSTED}:/usr/lib"
    lib = tmp_path / "shared.so"
    subprocess.run(
        [
            "cc",
            "-x",
            "c",
            "-",
            "-shared",
            "-fPIC",
            f"-Wl,-rpath,{value},-soname,{value}",
            "-o",
            str(lib),
        ],
        input=b"int x(void) { return 0; }",
        check=True,
    )
    with pytest.raises(ValueError, match="shares ELF string storage"):
        without_toolcache_runpath(lib.read_bytes())
    with pytest.raises(ValueError, match="retains a build-toolcache"):
        elf_requirements(lib)


def test_trace_rejects_search_and_unverified_extraction_member(tmp_path):
    trace = tmp_path / "trace"
    trace.write_text("  23:  trying file=" + HOSTED + "/libffi.so\n")
    with pytest.raises(ValueError, match="hosted toolcache"):
        selections([trace], tmp_path, {})
    member = tmp_path / "_MEI00abc" / "libpython.so"
    trace.write_text(f"  23: calling init: {member}\n")
    assert selections([trace], tmp_path, {"libpython.so": "a" * 64})["archive_members"] == {
        "libpython.so": "a" * 64
    }
    with pytest.raises(ValueError, match="absent"):
        selections([trace], tmp_path, {})


def test_trace_retains_unsuccessful_library_lookups_without_random_extraction_root(tmp_path):
    trace = tmp_path / "trace"
    extract = tmp_path / "_MEI000001"
    trace.write_text(
        f"  23: trying file={extract}/glibc-hwcaps/x86-64-v3/libz.so.1\n"
        f"  23: trying file={extract}/libz.so.1\n"
        f"  23: trying file={tmp_path / '_MEI000002'}/libz.so.1\n"
        "  24: trying file=/usr/lib/x86_64-linux-gnu/libz.so.1\n"
        "  24: trying file=/lib/x86_64-linux-gnu/libz.so.1\n"
    )
    assert selections([trace], tmp_path, {}) == {
        "archive_members": {},
        "host_files": {},
        "attempted_paths": {
            "extraction": ["glibc-hwcaps/x86-64-v3/libz.so.1", "libz.so.1"],
            "host": ["/lib/x86_64-linux-gnu/libz.so.1", "/usr/lib/x86_64-linux-gnu/libz.so.1"],
        },
    }


@pytest.mark.parametrize("searched", ["libz.so.1", "/build/runner/lib/libz.so.1", "/usr/share/lib/libz.so.1",
                                     "/usr/lib/../../build/libz.so.1"])
def test_trace_rejects_even_unsuccessful_lookups_outside_library_roots(tmp_path, searched):
    trace = tmp_path / "trace"
    trace.write_text(f"  23: trying file={searched}\n")
    with pytest.raises(ValueError, match="Unexpected glibc library search path"):
        selections([trace], tmp_path, {})


@pytest.mark.parametrize(("target", "architecture"), [("linux-i386", "i386"), ("linux-armhf", "armhf")])
def test_loader_rejects_deb_from_another_architecture(tmp_path, monkeypatch, target, architecture):
    deb = tmp_path / "row.deb"

    def check_output(command, *, text):
        assert text
        if command == ["dpkg", "--print-architecture"]:
            return architecture + "\n"
        assert command == ["dpkg-deb", "-f", str(deb), "Architecture"]
        return "amd64\n"

    monkeypatch.setattr(subprocess, "check_output", check_output)
    with pytest.raises(ValueError, match="package architecture does not match"):
        qualify(tmp_path / "row", deb, target, None, None)

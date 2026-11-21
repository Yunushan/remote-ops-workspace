from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from scripts.debian_native_dependencies import elf_requirements
from scripts.linux_frozen_runpaths import prepare_spec, stage_binaries, without_toolcache_runpath
from scripts.qualify_deb_loader import selections

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
    path.write_text("unknown format", encoding="utf-8")
    with pytest.raises(ValueError, match="Unrecognized"):
        prepare_spec(path)


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

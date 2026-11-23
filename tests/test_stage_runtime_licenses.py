import hashlib
import json
from importlib.metadata import PathDistribution
from pathlib import Path

import pytest

from scripts.check_preview_redistribution import ROOT
from scripts.stage_runtime_licenses import copy_distribution_licenses, stage_gui_sources


def install_fixture(root: Path, recorded: list[str], declared: list[str], *, legacy: bool = False) -> PathDistribution:
    info = root / "test_component-1.0.dist-info"
    info.mkdir(parents=True)
    declarations = "".join(f"License-File: {entry}\n" for entry in declared)
    (info / "METADATA").write_text(f"Metadata-Version: 2.4\nName: test-component\nVersion: 1.0\n{declarations}")
    license_dir = info.name if legacy else f"{info.name}/licenses"
    paths = [f"{license_dir}/{entry}" for entry in recorded]
    (info / "RECORD").write_text("".join(f"{path},,\n" for path in [*paths, "test_component/__init__.py"]))
    for path in paths:
        license_path = root / path
        license_path.parent.mkdir(parents=True, exist_ok=True)
        license_path.write_bytes(path.encode())
    return PathDistribution(info)


def test_copies_exact_installed_license_bytes_and_relative_paths(tmp_path: Path) -> None:
    names = ["LICENSE", "vendor/COPYING.txt"]
    installed = install_fixture(tmp_path / "installed", names, names)
    destination = tmp_path / "staged"

    copy_distribution_licenses(installed, destination)

    assert sorted(path.relative_to(destination).as_posix() for path in destination.rglob("*") if path.is_file()) == names
    for name in names:
        assert (destination / name).read_bytes() == f"test_component-1.0.dist-info/licenses/{name}".encode()


def test_refuses_missing_declared_license_before_copying(tmp_path: Path) -> None:
    installed = install_fixture(tmp_path / "installed", ["LICENSE"], ["LICENSE", "vendor/COPYING.txt"])
    destination = tmp_path / "staged"

    with pytest.raises(ValueError, match="missing installed license records"):
        copy_distribution_licenses(installed, destination)

    assert not destination.exists()


def test_copies_legacy_wheel_license_named_in_metadata(tmp_path: Path) -> None:
    installed = install_fixture(tmp_path / "installed", ["LICENSE", "README"], ["LICENSE"], legacy=True)
    destination = tmp_path / "staged"

    copy_distribution_licenses(installed, destination)

    assert {path.name for path in destination.iterdir()} == {"LICENSE"}
    assert (destination / "LICENSE").read_bytes() == b"test_component-1.0.dist-info/LICENSE"


def test_stages_only_current_gui_source_descriptors_with_exact_manifest_bytes(tmp_path: Path) -> None:
    materials = json.loads((ROOT / "redistribution-evidence" / "preview.json").read_bytes())["materials"]
    expected = {materials[key]["file"]: materials[key]["sha256"] for key in ("pyqt6_source", "qt_source")}

    stage_gui_sources(tmp_path)

    assert {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in tmp_path.iterdir()} == expected


@pytest.mark.parametrize("mismatch", ["file", "sha256"])
def test_rejects_gui_source_descriptor_drift(tmp_path: Path, mismatch: str) -> None:
    source = ROOT / "redistribution-evidence"
    evidence = tmp_path / "evidence"
    evidence.mkdir()
    manifest = json.loads((source / "preview.json").read_bytes())
    record = manifest["materials"]["pyqt6_source"]
    descriptor = evidence / record["file"]
    descriptor.write_bytes((source / record["file"]).read_bytes())
    if mismatch == "file":
        record["file"] = "stale-source.json"
    else:
        descriptor.write_bytes(descriptor.read_bytes() + b" ")
    (evidence / "preview.json").write_text(json.dumps(manifest), encoding="utf-8")

    with pytest.raises(ValueError, match="pyqt6_source descriptor differs"):
        stage_gui_sources(tmp_path / "staged", evidence)

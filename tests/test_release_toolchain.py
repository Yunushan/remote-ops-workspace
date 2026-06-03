import importlib.util
import json
import sys
from pathlib import Path


def test_release_toolchain_checker_passes_current_tree() -> None:
    checker = _load_release_toolchain_checker()
    assert checker.main() == 0


def test_release_constraints_match_manifest() -> None:
    manifest = json.loads(Path("configs/release_toolchain.json").read_text(encoding="utf-8"))
    expected = {
        checker_name(row["name"]): row["version"]
        for row in manifest["python_packages"]
    }
    actual = {}
    for line in Path("requirements-release.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, version = line.split("==", 1)
        actual[checker_name(name)] = version
    assert actual == expected


def test_release_toolchain_is_recorded_in_manifest(tmp_path: Path) -> None:
    make_release = _load_make_release()
    old_root = make_release.ROOT
    old_toolchain = make_release.RELEASE_TOOLCHAIN
    make_release.ROOT = tmp_path
    make_release.RELEASE_TOOLCHAIN = tmp_path / "configs" / "release_toolchain.json"
    try:
        (tmp_path / "configs").mkdir()
        make_release.RELEASE_TOOLCHAIN.write_text(
            json.dumps(
                {
                    "schema_version": 1,
                    "python": {
                        "version": "3.12",
                        "constraints_file": "requirements-release.txt",
                        "source_date_epoch": 1704067200,
                    },
                    "python_packages": [],
                    "native_toolchains": {},
                }
            ),
            encoding="utf-8",
        )
        dist = tmp_path / "dist"
        dist.mkdir()
        asset = dist / "asset.txt"
        asset.write_text("payload", encoding="utf-8")
        artifact = make_release.artifact_record(
            phase="test",
            target="asset",
            label="Asset",
            path=asset,
            format="txt",
            install_command="cat asset.txt",
            notes=[],
        )
        manifest_rel = make_release.write_manifest("1.2.3", [artifact], dist)
        manifest = json.loads((tmp_path / manifest_rel).read_text(encoding="utf-8"))
    finally:
        make_release.ROOT = old_root
        make_release.RELEASE_TOOLCHAIN = old_toolchain

    assert manifest["toolchain"]["python"]["constraints_file"] == "requirements-release.txt"


def checker_name(name: str) -> str:
    return name.lower().replace("_", "-")


def _load_release_toolchain_checker():
    path = Path("scripts/check_release_toolchain.py")
    spec = importlib.util.spec_from_file_location("check_release_toolchain_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def _load_make_release():
    path = Path("scripts/make_release.py")
    spec = importlib.util.spec_from_file_location("make_release_for_toolchain_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["make_release_for_toolchain_test"] = module
    spec.loader.exec_module(module)
    return module

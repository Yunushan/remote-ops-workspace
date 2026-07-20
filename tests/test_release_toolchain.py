import importlib.util
import json
import sys
from pathlib import Path


def test_release_toolchain_checker_passes_current_tree() -> None:
    checker = _load_release_toolchain_checker()
    assert checker.main() == 0


def test_release_toolchain_checker_requires_pinned_python_build_backend() -> None:
    checker = _load_release_toolchain_checker()
    toolchain = json.loads(Path("configs/release_toolchain.json").read_text(encoding="utf-8"))
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8").replace(
        'requires = ["setuptools==83.0.0", "wheel==0.47.0"]',
        'requires = ["setuptools>=77", "wheel"]',
    )

    errors = checker.check_python_build_backend(toolchain, pyproject)

    assert errors == [
        "pyproject.toml build-system.requires must pin setuptools and wheel to "
        "configs/release_toolchain.json"
    ]


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


def test_release_compatibility_constraints_apply_only_declared_overrides() -> None:
    manifest = json.loads(Path("configs/release_toolchain.json").read_text(encoding="utf-8"))
    profile = manifest["python"]["compatibility_profiles"][0]
    expected = {
        checker_name(row["name"]): row["version"]
        for row in manifest["python_packages"]
    }
    expected.update(
        {checker_name(name): version for name, version in profile["package_overrides"].items()}
    )
    actual = {}
    for line in Path(profile["constraints_file"]).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, version = line.split("==", 1)
        actual[checker_name(name)] = version

    assert set(profile["targets"]) == {"windows-x86", "macos-x64"}
    assert profile["package_overrides"] == {"cryptography": "48.0.1"}
    assert actual == expected


def test_release_toolchain_checker_requires_arm64_openssl_hardening() -> None:
    checker = _load_release_toolchain_checker()
    manifest = json.loads(Path("configs/release_toolchain.json").read_text(encoding="utf-8"))
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        '$env:OPENSSL_NO_VENDOR = "1"',
        '$env:OPENSSL_NO_VENDOR = "0"',
    )

    errors = checker.check_workflow(manifest, workflow)

    assert any("no untracked vendored OpenSSL fallback" in error for error in errors)


def test_release_toolchain_checker_requires_pinned_arm64_build_isolation_policy() -> None:
    checker = _load_release_toolchain_checker()
    manifest = json.loads(Path("configs/release_toolchain.json").read_text(encoding="utf-8"))
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        "--no-cache-dir --no-build-isolation --no-binary=cryptography",
        "--no-cache-dir --no-binary=cryptography",
    )

    errors = checker.check_workflow(manifest, workflow)

    assert any("deterministic Windows ARM64 cryptography source build" in error for error in errors)


def test_release_toolchain_checker_requires_packaged_msi_vault_smoke() -> None:
    checker = _load_release_toolchain_checker()
    script = Path("scripts/smoke_windows_native.ps1").read_text(encoding="utf-8").replace(
        'Test-RowVault $MsiRow "MSI install"',
        'Write-Host "MSI vault smoke disabled"',
    )

    errors = checker.check_windows_native_smoke(script)

    assert any("installed MSI vault smoke" in error for error in errors)


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

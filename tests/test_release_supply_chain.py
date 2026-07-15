import importlib.util
import json
import sys
import tarfile
import zipfile
from pathlib import Path


def load_make_release():
    path = Path("scripts/make_release.py")
    spec = importlib.util.spec_from_file_location("make_release", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load make_release.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["make_release"] = module
    spec.loader.exec_module(module)
    return module


def test_release_version_validation_rejects_non_release_versions() -> None:
    make_release = load_make_release()
    make_release.validate_version("1.2.3")
    make_release.validate_version("1.2.3rc1")
    for version in ["1.2", "1.2.3+local", "v1.2.3", "1.2.3.dev1"]:
        try:
            make_release.validate_version(version)
        except SystemExit:
            pass
        else:
            raise AssertionError(f"release version should be rejected: {version}")


def test_release_tag_guard_allows_manual_controller_branch(monkeypatch) -> None:
    make_release = load_make_release()
    monkeypatch.setenv("RELEASE_TAG", "v1.2.3")
    monkeypatch.setenv("GITHUB_REF_NAME", "main")
    monkeypatch.setenv("GITHUB_REF_TYPE", "branch")

    make_release.validate_github_tag("1.2.3")


def test_release_tag_guard_rejects_wrong_dispatch_tag(monkeypatch) -> None:
    make_release = load_make_release()
    monkeypatch.setenv("RELEASE_TAG", "v1.2.4")
    monkeypatch.setenv("GITHUB_REF_NAME", "main")
    monkeypatch.setenv("GITHUB_REF_TYPE", "branch")

    try:
        make_release.validate_github_tag("1.2.3")
    except SystemExit as exc:
        assert "RELEASE_TAG='v1.2.4'" in str(exc)
    else:
        raise AssertionError("mismatched workflow-dispatch release tag should be rejected")


def test_release_dist_must_be_inside_repo(tmp_path: Path) -> None:
    make_release = load_make_release()
    try:
        make_release.resolve_dist(make_release.ROOT)
    except SystemExit as exc:
        assert "repository root" in str(exc)
    else:
        raise AssertionError("release dist must not be repository root")

    try:
        make_release.resolve_dist(tmp_path)
    except SystemExit as exc:
        assert "inside the repository" in str(exc)
    else:
        raise AssertionError("release dist outside repo should be rejected")

    assert make_release.resolve_dist(make_release.ROOT / "dist-test") == (make_release.ROOT / "dist-test").resolve()


def test_file_integrity_reports_size_and_sha256(tmp_path: Path) -> None:
    make_release = load_make_release()
    artifact = tmp_path / "artifact.txt"
    artifact.write_bytes(b"release\n")
    integrity = make_release.file_integrity(artifact)
    assert integrity["size_bytes"] == len("release\n")
    assert integrity["sha256"] == make_release.sha256_file(artifact)
    assert len(integrity["sha256"]) == 64


def test_manifest_and_checksum_file_include_artifact_integrity(tmp_path: Path) -> None:
    make_release = load_make_release()
    old_root = make_release.ROOT
    make_release.ROOT = tmp_path
    try:
        dist = tmp_path / "dist"
        dist.mkdir()
        asset = dist / "asset.txt"
        asset.write_text("payload", encoding="utf-8")
        artifacts = [
            make_release.artifact_record(
                phase="test",
                target="asset",
                label="Asset",
                path=asset,
                format="txt",
                install_command="cat asset.txt",
                notes=[],
            )
        ]
        manifest_rel = make_release.write_manifest("1.2.3", artifacts, dist)
        checksum_rel = make_release.write_checksums("1.2.3", artifacts, tmp_path / manifest_rel, dist)
        manifest = json.loads((tmp_path / manifest_rel).read_text(encoding="utf-8"))
        checksums = (tmp_path / checksum_rel).read_text(encoding="utf-8")
    finally:
        make_release.ROOT = old_root

    assert manifest["schema_version"] == 1
    assert manifest["toolchain"]["python"]["constraints_file"] == "requirements-release.txt"
    assert manifest["artifacts"][0]["size_bytes"] == 7
    assert len(manifest["artifacts"][0]["sha256"]) == 64
    assert "asset.txt" in checksums
    assert "release-manifest.json" in checksums


def test_release_archive_metadata_is_deterministic(tmp_path: Path) -> None:
    make_release = load_make_release()
    zip_path = tmp_path / "asset.zip"
    with zipfile.ZipFile(zip_path, "w") as archive:
        make_release.add_text_to_zip(archive, "asset.txt", "payload")
    with zipfile.ZipFile(zip_path) as archive:
        info = archive.getinfo("asset.txt")
        assert info.date_time == make_release.zip_datetime()
        assert (info.external_attr >> 16) == 0o644

    tar_path = tmp_path / "asset.tar"
    with tarfile.open(tar_path, "w") as archive:
        make_release.add_text_to_tar(archive, "asset.txt", "payload")
    with tarfile.open(tar_path) as archive:
        info = archive.getmember("asset.txt")
        assert info.mtime == make_release.source_date_epoch()
        assert info.uid == 0
        assert info.gid == 0
        assert info.mode == 0o644


def test_release_workflow_uses_minimal_permissions() -> None:
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    assert "permissions:\n  contents: read" in workflow
    assert "persist-credentials: false" in workflow
    assert "permissions:\n      contents: write" in workflow
    assert "fail_on_unmatched_files: true" in workflow
    assert workflow.count("tag_name: ${{ env.RELEASE_TAG }}") == 2


def test_release_workflow_uses_pinned_toolchain() -> None:
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    assert 'SOURCE_DATE_EPOCH: "1704067200"' in workflow
    assert "--constraint requirements-release.txt" in workflow
    assert "python -m pip install --upgrade" not in workflow
    assert "choco install innosetup --version=6.3.3" in workflow
    assert "dotnet tool install --global wix --version 5.0.2" in workflow


def test_native_manifest_scripts_add_integrity_fields() -> None:
    linux = Path("scripts/make_linux_native.sh").read_text(encoding="utf-8")
    macos = Path("scripts/make_macos_native.sh").read_text(encoding="utf-8")
    windows = Path("scripts/make_windows_native.ps1").read_text(encoding="utf-8")
    assert "sha256_file" in linux
    assert "size_bytes" in linux
    assert "sha256_file" in macos
    assert "size_bytes" in macos
    assert "Get-FileHash -Algorithm SHA256" in windows
    assert "size_bytes" in windows


def test_native_release_scripts_emit_checksum_sidecars() -> None:
    linux = Path("scripts/make_linux_native.sh").read_text(encoding="utf-8")
    macos = Path("scripts/make_macos_native.sh").read_text(encoding="utf-8")
    windows = Path("scripts/make_windows_native.ps1").read_text(encoding="utf-8")
    assert "linux-{appimage_arch}-native-SHA256SUMS.txt" in linux
    assert "macos-{arch}-native-SHA256SUMS.txt" in macos
    assert "windows-$Arch-native-SHA256SUMS.txt" in windows
    assert "write_checksums([deb, rpm, appimage, tarball, manifest_path], checksums)" in linux
    assert "write_checksums([dmg, pkg, manifest_path], checksums)" in macos
    assert "Write-NativeChecksums" in windows


def test_linux_appimagetool_download_supports_sha256_verification() -> None:
    linux = Path("scripts/make_linux_native.sh").read_text(encoding="utf-8")
    assert "https://github.com/AppImage/appimagetool/releases/download/continuous" in linux
    assert "APPIMAGETOOL_SHA256" in linux
    assert "sha256sum -c -" in linux


def test_linux_native_build_allows_branch_evidence_dispatch_with_release_tag_binding() -> None:
    linux = Path("scripts/make_linux_native.sh").read_text(encoding="utf-8")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8")

    assert 'EXPECTED_TAG="v${VERSION}"' in linux
    assert 'RELEASE_TAG=\'${RELEASE_TAG}\'' in linux
    assert '"${GITHUB_REF_TYPE:-}" == "tag"' in linux
    assert '"${GITHUB_REF_NAME}" == v*' in linux
    assert "RELEASE_TAG: ${{ inputs.release_tag }}" in workflow


def test_windows_and_macos_builds_allow_manual_controller_branch_with_release_tag_binding() -> None:
    macos = Path("scripts/make_macos_native.sh").read_text(encoding="utf-8")
    windows = Path("scripts/make_windows_native.ps1").read_text(encoding="utf-8")

    assert "${RELEASE_TAG:-}" in macos
    assert "${GITHUB_REF_TYPE:-}" in macos
    assert '"${GITHUB_REF_NAME}" == v*' in macos
    assert "$env:RELEASE_TAG" in windows
    assert "$env:GITHUB_REF_TYPE" in windows
    assert '.StartsWith("v")' in windows

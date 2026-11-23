from __future__ import annotations

import gzip
import hashlib
import importlib.util
import io
import json
import stat
import struct
import tarfile
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import pytest

ROOT = Path(__file__).resolve().parents[1]


def checker():
    path = ROOT / "scripts" / "check_preview_redistribution.py"
    spec = importlib.util.spec_from_file_location("check_preview_redistribution", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def runtime_license_fixture(profile: str) -> dict[str, bytes]:
    from scripts.stage_runtime_licenses import LICENSE_PROFILES

    paths = {"cpython/LICENSE.txt", "pyinstaller/COPYING.txt"}
    paths.update(f"{component}/LICENSE" for component in LICENSE_PROFILES[profile] if component != "pyinstaller")
    if "cryptography" in LICENSE_PROFILES[profile]:
        paths |= {"cryptography/LICENSE.APACHE", "cryptography/LICENSE.BSD"}
    return {path: path.encode() for path in sorted(paths)}


def test_native_package_inventory_matches_real_release_matrix() -> None:
    module = checker()
    names = module.expected_native_assets("v1.0.27")
    assert len(names) == 35
    assert len([name for name in names if module.NATIVE_PACKAGE.fullmatch(name)]) == 21
    assert {target: len(module.target_asset_names("v1.0.27", target)) for target in module.BUILD_TARGETS} == {
        "windows-x86": 5,
        "windows-x64": 5,
        "windows-arm64": 5,
        "macos-x64": 4,
        "macos-arm64": 4,
        "linux-x86_64": 6,
        "linux-aarch64": 6,
    }


def test_packaged_linux_system_notice_requires_approved_distro_version(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import check_packaged_release_notices as notices
    from check_release_license_compliance import ApprovedPackageNotices, check_packaged_notice_scans
    from packaged_linux_licenses import APPLICATION_LICENSE_PATH, LICENSE_ROOT

    package = tmp_path / "remote-ops-workspace-v2.3.4-linux-x86_64-native.tar.gz"
    component = "system-libfoo"
    copyright_path = (LICENSE_ROOT / component / "copyright").as_posix()
    files = {
        APPLICATION_LICENSE_PATH.as_posix(): (ROOT / "LICENSE").read_bytes().replace(b"\r\n", b"\n"),
        "usr/share/doc/remote-ops-workspace/THIRD_PARTY_NOTICES.md": (
            ROOT / "redistribution-evidence/THIRD_PARTY_NOTICES.md"
        ).read_bytes(),
        **{(LICENSE_ROOT / path).as_posix(): data for path, data in runtime_license_fixture("linux").items()},
        copyright_path: b"Exact distro copyright text.\n",
    }

    def write_package() -> None:
        with tarfile.open(package, "w:gz") as archive:
            for path, data in files.items():
                member = tarfile.TarInfo(path)
                member.size = len(data)
                archive.addfile(member, io.BytesIO(data))

    write_package()
    with pytest.raises(ValueError, match="missing a valid bundled Debian notice and version"):
        list(notices.observe_notices(tmp_path, {package.name}))

    version_path = (LICENSE_ROOT / component / "package-version.txt").as_posix()
    files[version_path] = b"1:3.1.4-2+deb13u1\n"
    write_package()
    [observed] = notices.observe_notices(tmp_path, {package.name})
    approved_components = {}
    scans = []
    for member in observed.files:
        record = {
            "path": member.path,
            "sha256": hashlib.sha256(member.data).hexdigest(),
            "size_bytes": len(member.data),
        }
        scans.append(record)
        if name := getattr(member, "component", None):
            item = approved_components.setdefault(name, {
                "name": name, "scope": "bundled", "license_files": [],
            })
            item["license_files"].append(record)
            if member.version is not None:
                item.update(version=member.version, origin="native-component")

    approved = {package.name: ApprovedPackageNotices(
        observed._asdict(), scans, list(approved_components.values()),
    )}
    assert approved_components[component]["version"] == "1:3.1.4-2+deb13u1"
    assert check_packaged_notice_scans(tmp_path, set(approved), approved) == []
    approved_components[component]["version"] = "1:3.1.4-2"
    assert check_packaged_notice_scans(tmp_path, set(approved), approved) == [
        f"{package.name} signed bundled component {component} must match packaged version '1:3.1.4-2+deb13u1'",
    ]


def test_production_notices_cover_protected_linux_and_require_exact_bytes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import check_packaged_release_notices as notices
    from check_release_license_compliance import ApprovedPackageNotices, check_packaged_notice_scans

    tag = "v2.3.4"
    names = notices.expected_production_packages(tag)
    assert len(names) == 29
    assert f"remote-ops-workspace-{tag}-linux-i386.deb" in names
    assert f"remote-ops-workspace-{tag}-linux-armv7hl.rpm" in names
    groups = notices.expected_production_manifest_packages(tag, json.loads(notices.MATRIX_PATH.read_bytes()))
    assert len(groups) == 9
    assert {member for group in groups.values() for member in group} == names
    assert f"remote-ops-workspace-{tag}-linux-arm64.deb" in groups[
        f"remote-ops-workspace-{tag}-linux-aarch64-native-manifest.json"
    ]
    assert f"remote-ops-workspace-{tag}-linux-armv7hl.rpm" in groups[
        f"remote-ops-workspace-{tag}-linux-armhf-native-manifest.json"
    ]
    assets = tmp_path / "assets"
    assets.mkdir()
    bundle = tmp_path / "bundle"
    bundle.mkdir()
    package = assets / f"remote-ops-workspace-{tag}-windows-x86-native.zip"
    gui_package = assets / f"remote-ops-workspace-{tag}-windows-x64-native.zip"
    material_dir = ROOT / "redistribution-evidence"
    material = material_dir / "THIRD_PARTY_NOTICES.md"
    monkeypatch.setattr(notices, "expected_production_packages", lambda _tag: {package.name, gui_package.name})
    with zipfile.ZipFile(package, "w") as archive:
        archive.write(material, "docs/THIRD_PARTY_NOTICES.md")
        project_license = (ROOT / "LICENSE").read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n")
        archive.writestr("docs/LICENSE", project_license)
        for path, data in runtime_license_fixture("windows-x86").items():
            archive.writestr(f"docs/licenses/runtime/{path}", data)
    with zipfile.ZipFile(gui_package, "w") as archive:
        archive.write(material, "docs/THIRD_PARTY_NOTICES.md")
        archive.write(ROOT / "LICENSE", "docs/LICENSE")
        for name in (
            "PyQt6-GPL-3.0.txt", "Qt-LGPL-3.0.txt", "Qt-Relinking.md",
            *notices.pinned_gui_source_records().values(),
        ):
            archive.write(material_dir / name, f"docs/licenses/{name}")
        for path, data in runtime_license_fixture("desktop").items():
            archive.writestr(f"docs/licenses/runtime/{path}", data)

    assert notices.verify_notices(assets, tag) == 2
    assert not list(bundle.iterdir())
    assert notices.verify_notices(assets, tag, evidence_root=bundle) == 2
    output = bundle / "packaged-notices"
    capture = json.loads((output / "notice-extraction.json").read_bytes())
    assert capture["release_tag"] == tag
    assert set(capture["packages"]) == {package.name, gui_package.name}
    expected_gui_licenses = {
        "docs/licenses/PyQt6-GPL-3.0.txt": "pyqt6", "docs/licenses/Qt-LGPL-3.0.txt": "pyqt6-qt6",
    }
    approved = {}
    for artifact in (package, gui_package):
        found = capture["packages"][artifact.name]
        assert found["sha256"] == hashlib.sha256(artifact.read_bytes()).hexdigest()
        assert found["size_bytes"] == artifact.stat().st_size
        assert len(found["notice_files"]) == (4 if artifact == package else 21)
        components = {}
        with zipfile.ZipFile(artifact) as archive:
            for record in found["notice_files"]:
                packaged = archive.read(record["path"])
                assert packaged == (bundle / record["file"]).read_bytes()
                assert record["sha256"] == hashlib.sha256(packaged).hexdigest()
                assert record["size_bytes"] == len(packaged)
                if record["path"].startswith("docs/licenses/runtime/"):
                    assert record["component"] == record["path"].split("/")[3]
                elif record["path"] == "docs/LICENSE":
                    assert record["component"] == "remote-ops-workspace"
                elif record["path"] in expected_gui_licenses:
                    assert record["component"] == expected_gui_licenses[record["path"]]
                else:
                    assert "component" not in record
                if component := record.get("component"):
                    components.setdefault(component, []).append(record)
        approved[artifact.name] = ApprovedPackageNotices(
            found, found["notice_files"],
            [
                {"name": name, "scope": "bundled", "license_files": license_files}
                for name, license_files in components.items()
            ],
        )
    assert check_packaged_notice_scans(assets, set(approved), approved) == []
    gui_evidence = approved[gui_package.name]
    for component in gui_evidence.components:
        if component["name"] == "pyqt6-qt6":
            component["license_files"] = components["pyqt6"]
    assert check_packaged_notice_scans(assets, set(approved), approved) == [
        f"{gui_package.name} signed bundled component pyqt6-qt6 does not bind its packaged licenses",
    ]
    with pytest.raises(ValueError, match="no packaged-notices output"):
        notices.verify_notices(assets, tag, evidence_root=bundle)
    assert json.loads((output / "notice-extraction.json").read_bytes()) == capture

    failed = tmp_path / "failed"
    failed.mkdir()
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("docs/THIRD_PARTY_NOTICES.md", b"Different bytes")
    with pytest.raises(ValueError, match="contains different bytes"):
        notices.verify_notices(assets, tag, evidence_root=failed)
    assert not list(failed.iterdir())


@pytest.mark.parametrize(("problem", "message"), [
    ("missing", "does not contain"),
    ("stale", "does not contain"),
    ("modified", "contains different bytes"),
    ("misplaced", "beside Qt-Relinking"),
    ("wrong-directory", "under docs/licenses"),
])
def test_packaged_qt_source_records_must_match_relink_guide(tmp_path, problem, message):
    module = checker()
    package = tmp_path / "remote-ops-workspace-v1.0.28-windows-x64-native.zip"
    material_dir = ROOT / "redistribution-evidence"
    sources = module.pinned_gui_source_records()
    names = ["Qt-Relinking.md", *sources.values()]
    with zipfile.ZipFile(package, "w") as archive:
        for name in names:
            member = f"elsewhere/{name}" if problem == "wrong-directory" else f"docs/licenses/{name}"
            data = (material_dir / name).read_bytes()
            if name == sources["qt_source"]:
                if problem == "missing":
                    continue
                if problem == "stale":
                    member = "docs/licenses/qt-everywhere-src-6.11.2-source.json"
                elif problem == "modified":
                    data += b" "
                elif problem == "misplaced":
                    member = f"docs/{name}"
            archive.writestr(member, data)
    with pytest.raises(ValueError, match=message):
        module.check_packaged_legal_material(package, {name: module.file_hash(material_dir / name) for name in names})


def test_notice_capture_refuses_package_changed_after_extraction(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import check_packaged_release_notices as notices

    tag = "v2.3.4"
    assets, bundle = tmp_path / "assets", tmp_path / "bundle"
    assets.mkdir()
    bundle.mkdir()
    package = assets / f"remote-ops-workspace-{tag}-windows-x86-native.zip"
    material = ROOT / "redistribution-evidence" / "THIRD_PARTY_NOTICES.md"
    with zipfile.ZipFile(package, "w") as archive:
        archive.write(material, "docs/THIRD_PARTY_NOTICES.md")
        archive.write(ROOT / "LICENSE", "docs/LICENSE")
        for path, data in runtime_license_fixture("windows-x86").items():
            archive.writestr(f"docs/licenses/runtime/{path}", data)
    monkeypatch.setattr(notices, "expected_production_packages", lambda _tag: {package.name})
    inspect = notices.read_desktop_component_licenses

    def replace_after_inspection(artifact, target):
        verified = inspect(artifact, target)
        artifact.write_bytes(b"replacement bytes")
        return verified

    monkeypatch.setattr(notices, "read_desktop_component_licenses", replace_after_inspection)
    with pytest.raises(ValueError, match="changed during notice extraction"):
        notices.verify_notices(assets, tag, evidence_root=bundle)
    assert not list(bundle.iterdir())


@pytest.mark.parametrize(("fault", "failure"), [
    ("", ""),
    ("changed-manifest-identity", "sha256 does not match release asset"),
    ("different-license-bytes", "inconsistent packaged license files for cpython"),
])
def test_manifest_review_inputs_preserve_paths_and_debian_component_scope(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str, failure: str,
) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import check_packaged_release_notices as capture
    from check_preview_redistribution import ComponentLicense, EmbeddedFile
    from check_release_license_compliance import (
        check_debian_notice_inventory,
        required_artifact_license_records,
    )
    from debian_server_notices import notice_path

    tag = "v2.3.4"
    assets, bundle = tmp_path / "assets", tmp_path / "review"
    assets.mkdir()
    bundle.mkdir()
    deb, rpm = [f"remote-ops-workspace-{tag}-linux-{suffix}" for suffix in ("amd64.deb", "x86_64.rpm")]
    manifest = assets / f"remote-ops-workspace-{tag}-linux-x86_64-native-manifest.json"
    matrix = tmp_path / "matrix.json"
    matrix.write_text(json.dumps({"default_github_release": {"native_jobs": [
        {"asset_patterns": [deb, rpm, manifest.name]},
    ]}}), encoding="utf-8")
    monkeypatch.setattr(capture, "MATRIX_PATH", matrix)
    notice = b"Debian openssh-server copyright"
    version = "1:10.0p1-7+deb13u4"
    debian_path = notice_path("openssh-server").as_posix()
    receipts = [
        capture.PackageNotices(deb, "", 0, [
            ComponentLicense("usr/share/docs/cpython/LICENSE.txt", b"Python license", "CPython"),
            ComponentLicense(debian_path, notice, "openssh-server", version),
        ]),
        capture.PackageNotices(rpm, "", 0, [
            ComponentLicense(
                "usr/share/licenses/cpython/LICENSE.txt",
                b"Different bytes" if fault == "different-license-bytes" else b"Python license",
                "cpython",
            ),
            EmbeddedFile("docs/THIRD_PARTY_NOTICES.md", b"Common notices"),
        ]),
    ]
    entries = []
    for index, package in enumerate(receipts):
        raw = package.name.encode()
        (assets / package.name).write_bytes(raw)
        digest = hashlib.sha256(raw).hexdigest()
        receipts[index] = package._replace(sha256=digest, size_bytes=len(raw))
        entries.append({"file": f"native-dist/linux/{package.name}", "sha256": digest, "size_bytes": len(raw)})
    if fault == "changed-manifest-identity":
        entries[0]["sha256"] = "0" * 64
    manifest.write_text(json.dumps(entries), encoding="utf-8")

    def inspect(directory, expected):
        assert directory == assets and expected == {deb, rpm}
        return iter(receipts)

    monkeypatch.setattr(capture, "observe_notices", inspect)
    if failure:
        with pytest.raises(ValueError, match=failure):
            capture.verify_notices(assets, tag, evidence_root=bundle, write_review_inputs=True)
        assert not list(bundle.iterdir())
        return

    assert capture.verify_notices(assets, tag, evidence_root=bundle, write_review_inputs=True) == 2
    report = json.loads((bundle / "packaged-notices/review-inputs.json").read_bytes())
    assert report["release_tag"] == tag
    assert set(report["native_manifests"]) == {manifest.name}
    result = report["native_manifests"][manifest.name]
    assert result["sha256"] == hashlib.sha256(manifest.read_bytes()).hexdigest()
    classifications = {
        name: {"scope": "bundled", **component}
        for name, component in result["component_license_files"].items()
    }
    cpython, = classifications["cpython"]["license_files"]
    assert cpython["path"] == receipts[0].files[0].path
    assert cpython["artifact_paths"] == {rpm: receipts[1].files[0].path}
    openssh, = classifications["openssh-server"]["license_files"]
    assert openssh["path"] == debian_path
    errors = []
    scoped = check_debian_notice_inventory(
        {deb: {"openssh-server": {**openssh, "version": version}}}, classifications, manifest.name, errors,
    )
    required = required_artifact_license_records(classifications, {deb, rpm}, scoped, manifest.name, errors)
    assert not errors
    scans = result["artifact_license_files"]
    for asset, rows in scans.items():
        for row in rows:
            assert set(row) == {"path", "file", "sha256", "size_bytes"}
            assert hashlib.sha256((bundle / row["file"]).read_bytes()).hexdigest() == row["sha256"]
        assert required[asset] <= {(row["path"], row["sha256"], row["size_bytes"]) for row in rows}
    assert all(row["path"] != debian_path for row in scans[rpm])


def test_manifest_review_refuses_swapped_architectures_with_valid_hashes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    from check_packaged_release_notices import expected_production_manifest_packages
    from package_license_review_inputs import manifest_review_inputs

    tag = "v2.3.4"
    stem = f"remote-ops-workspace-{tag}-windows"
    matrix = {"default_github_release": {"native_jobs": [{"asset_patterns": [
        f"{stem}-<x64|arm64>-native.zip", f"{stem}-<x64|arm64>-native-manifest.json",
    ]}]}}
    groups = expected_production_manifest_packages(tag, matrix)
    x64, arm64 = (f"{stem}-{architecture}-native.zip" for architecture in ("x64", "arm64"))
    packages = {}
    for asset in (x64, arm64):
        raw = asset.encode()
        (tmp_path / asset).write_bytes(raw)
        packages[asset] = {"sha256": hashlib.sha256(raw).hexdigest(), "size_bytes": len(raw), "notice_files": []}
    for architecture, misplaced in (("x64", arm64), ("arm64", x64)):
        (tmp_path / f"{stem}-{architecture}-native-manifest.json").write_text(
            json.dumps([{"file": misplaced, **packages[misplaced]}]), encoding="utf-8",
        )

    with pytest.raises(ValueError, match="package inventory differs from its release matrix target"):
        manifest_review_inputs(tmp_path, tag, groups, packages)


@pytest.mark.parametrize("fault", ["", "missing-license", "duplicate-license", "linked-license",
                                  "missing-application-license", "changed-application-license"])
def test_production_captures_runtime_licenses_by_installed_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, fault: str,
) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import check_packaged_release_notices as notices
    from packaged_linux_licenses import APPLICATION_LICENSE_PATH, REQUIRED_LICENSE_PATHS
    from stage_linux_runtime_licenses import LICENSE_COMPONENTS, LICENSE_ROOT

    tag = "v2.3.4"
    assets, bundle = tmp_path / "assets", tmp_path / "bundle"
    assets.mkdir()
    bundle.mkdir()
    package = assets / f"remote-ops-workspace-{tag}-linux-armhf-native.tar.gz"
    monkeypatch.setattr(notices, "expected_production_packages", lambda _tag: {package.name})
    paths = REQUIRED_LICENSE_PATHS | {
        LICENSE_ROOT / component / "LICENSE"
        for component in LICENSE_COMPONENTS - {"cpython", "cryptography"}
    }
    contents = {path.as_posix(): path.as_posix().encode() for path in paths}
    affected = (LICENSE_ROOT / "cryptography/LICENSE.APACHE").as_posix()
    with tarfile.open(package, "w:gz") as archive:
        archive.add(ROOT / "redistribution-evidence/THIRD_PARTY_NOTICES.md", arcname="docs/THIRD_PARTY_NOTICES.md")
        if fault != "missing-application-license":
            application_license = (ROOT / "LICENSE").read_bytes()
            if fault == "changed-application-license":
                application_license += b"changed license"
            member = tarfile.TarInfo(APPLICATION_LICENSE_PATH.as_posix())
            member.size = len(application_license)
            archive.addfile(member, io.BytesIO(application_license))
        for path, data in contents.items():
            if path == affected and fault == "missing-license":
                continue
            member = tarfile.TarInfo(path)
            if path == affected and fault == "linked-license":
                member.type = tarfile.SYMTYPE
                member.linkname = "LICENSE"
                archive.addfile(member)
                continue
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))
            if path == affected and fault == "duplicate-license":
                archive.addfile(member, io.BytesIO(data))

    if fault:
        with pytest.raises(ValueError, match="application license" if fault.endswith("application-license") else "runtime license"):
            notices.verify_notices(assets, tag, evidence_root=bundle)
        assert not list(bundle.iterdir())
        return

    assert notices.verify_notices(assets, tag, evidence_root=bundle) == 1
    report = json.loads((bundle / "packaged-notices/notice-extraction.json").read_bytes())
    application_record = next(
        record for record in report["packages"][package.name]["notice_files"]
        if record["path"] == APPLICATION_LICENSE_PATH.as_posix()
    )
    assert application_record["component"] == "remote-ops-workspace"
    assert (bundle / application_record["file"]).read_bytes() == application_license
    records = {
        record["path"]: (record["component"], (bundle / record["file"]).read_bytes())
        for record in report["packages"][package.name]["notice_files"]
        if record["path"].startswith(LICENSE_ROOT.as_posix() + "/")
    }
    assert records == {
        path: (path.removeprefix(LICENSE_ROOT.as_posix() + "/").split("/")[0], data)
        for path, data in contents.items()
    }


@pytest.mark.parametrize("suffix", [".dmg", ".pkg"])
@pytest.mark.parametrize("fault", ["", "wrong-root", "linked-member", "missing-application-license"])
def test_macos_runtime_licenses_require_regular_members_at_the_installed_path(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, suffix: str, fault: str,
) -> None:
    monkeypatch.syspath_prepend(str(ROOT / "scripts"))
    import packaged_desktop_licenses as desktop

    package = tmp_path / f"remote-ops-workspace-v2.3.4-macos-x64{suffix}"
    package.write_bytes(b"fixture")
    runtime_root = desktop.PKG_LICENSE_ROOT if suffix == ".pkg" else desktop.DMG_LICENSE_ROOT
    member_root = Path("unrelated") / runtime_root if fault == "wrong-root" else runtime_root
    member_prefix = "./" if suffix == ".pkg" else ""
    contents = {
        f"{member_prefix}{member_root.as_posix()}/{path}": data
        for path, data in runtime_license_fixture("desktop").items()
    }
    if fault != "missing-application-license":
        contents[f"{member_prefix}{member_root.parent.as_posix()}/LICENSE"] = b"application license"
    if suffix == ".dmg":
        contents["LICENSE"] = b"volume license"
    members = [
        {"Path": name, "Mode": "-rw-r--r--", "Size": str(len(data)), "Links": "1"}
        for name, data in contents.items()
    ]
    if fault == "linked-member":
        members[0]["Links"] = "2"

    def list_members(archive, *, archive_format):
        if suffix == ".pkg":
            assert archive.read_bytes() == b"CPIO fixture" and archive_format == "Cpio"
        else:
            assert archive == package and archive_format is None
        return members

    monkeypatch.setattr(desktop, "pkg_cpio_payload", lambda _package: b"CPIO fixture")
    monkeypatch.setattr(desktop, "seven_zip_members", list_members)
    monkeypatch.setattr(desktop, "seven_zip_read", lambda _archive, name, **_kwargs: contents[name])
    if fault:
        with pytest.raises(ValueError, match="application license" if fault == "missing-application-license" else "runtime license"):
            desktop.read_desktop_component_licenses(package, "macos-x64")
        return

    result = desktop.read_desktop_component_licenses(package, "macos-x64")
    assert {member.path: member.data for member in result} == {
        name.removeprefix("./"): data for name, data in contents.items() if name != "LICENSE"
    }


def test_missing_evidence_fails_before_native_publication(tmp_path: Path) -> None:
    module = checker()
    with pytest.raises(ValueError, match="preview evidence manifest.*missing"):
        module.evidence_materials(tmp_path / "redistribution-evidence", "v1.0.27")


def test_commercial_channel_has_no_self_asserted_bypass(tmp_path: Path) -> None:
    module = checker()
    evidence = tmp_path / "redistribution-evidence"
    evidence.mkdir()
    (evidence / "preview.json").write_text(
        json.dumps({"schema_version": 1, "release_tag": "v1.0.27", "channel": "commercial", "materials": {}}),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="verifiable vendor grant"):
        module.evidence_materials(evidence, "v1.0.27")


def test_source_archive_records_pin_official_urls_versions_and_upstream_digests() -> None:
    module = checker()
    upstream_digests = {
        "pyqt6_source": "17bb18b3ae953ab54b23026291ecea2579b028597b56c281a752c8ed66dd1a58",
        "qt_source": "98ff4f44bac6ec3e1e62ee2a4316ae0e3d15badb015d753cc0268a20db52f165",
    }
    with patch.object(module, "fetch_upstream_checksum", side_effect=lambda key, _url, _filename: upstream_digests[key]):
        materials = module.evidence_materials(Path("redistribution-evidence"), "v1.0.27")
        records = module.source_archive_records(materials)

    assert records["pyqt6_source"] == {
        "component": "PyQt6",
        "version": "6.12.1",
        "filename": "pyqt6-6.12.1.tar.gz",
        "url": "https://files.pythonhosted.org/packages/61/5f/39d2cf3eabc36006a5c87df6e1ed34928025b4a1768d752859bf404ec341/pyqt6-6.12.1.tar.gz",
        "sha256": "17bb18b3ae953ab54b23026291ecea2579b028597b56c281a752c8ed66dd1a58",
        "upstream_checksum_page": "https://pypi.org/pypi/PyQt6/6.12.1/json",
    }
    assert records["qt_source"]["version"] == "6.12.0"
    assert records["qt_source"]["filename"] == "qt-everywhere-src-6.12.0.tar.xz"
    assert records["qt_source"]["url"].startswith("https://download.qt.io/official_releases/")
    assert records["qt_source"]["sha256"] == "98ff4f44bac6ec3e1e62ee2a4316ae0e3d15badb015d753cc0268a20db52f165"


def test_official_checksum_parsers_extract_pinned_archive_digests() -> None:
    module = checker()
    filename = "pyqt6-6.11.0.tar.gz"
    digest = "45dd60aa69976de1918b5ced6b4e7b6a25abd2a919ecef5fd5826ecc76718889"
    pypi_payload = json.dumps({
        "urls": [{
            "filename": filename,
            "packagetype": "sdist",
            "digests": {"sha256": digest},
        }],
    }).encode()
    assert module.parse_upstream_checksum(pypi_payload, "pyqt6_source", filename) == digest

    qt_filename = "qt-everywhere-src-6.11.2.tar.xz"
    qt_digest = "6dcfbca271d76a6502741a2c0dc6fc98ef7dd0b7b4cfd0abcebb285a86a26f33"
    qt_payload = (
        f"<h2>Mirrors for {qt_filename}</h2><dt>SHA-256 Hash:</dt><dd>{qt_digest}</dd>"
    ).encode()
    assert module.parse_upstream_checksum(qt_payload, "qt_source", qt_filename) == qt_digest


def test_upstream_digest_mismatch_fails_closed() -> None:
    module = checker()
    with patch.object(module, "fetch_upstream_checksum", return_value="0" * 64):
        with pytest.raises(ValueError, match="does not match the official upstream checksum"):
            module.evidence_materials(Path("redistribution-evidence"), "v1.0.27")


def test_source_archive_record_rejects_unpinned_hosts_or_versions(tmp_path: Path) -> None:
    module = checker()
    record = json.loads(Path("redistribution-evidence/PyQt6-6.12.1-source.json").read_text())
    record["url"] = "https://attacker.example/pyqt6-6.12.1.tar.gz"
    path = tmp_path / "source.json"
    path.write_text(json.dumps(record), encoding="utf-8")

    with pytest.raises(ValueError, match="official upstream archive"):
        module.source_archive_record(path, "pyqt6_source")


def test_installed_distribution_versions_normalizes_package_names() -> None:
    module = checker()
    distributions = [
        SimpleNamespace(metadata={"Name": "Example_Package.Name"}, version="1.2.3"),
        SimpleNamespace(metadata={"Name": "PyQt6"}, version="6.11.0"),
    ]
    with patch.object(module.metadata, "distributions", return_value=distributions):
        assert module.installed_distribution_versions() == {
            "example-package-name": "1.2.3",
            "pyqt6": "6.11.0",
        }


def test_installed_distribution_versions_rejects_conflicts_and_empty_inventory() -> None:
    module = checker()
    conflicting = [
        SimpleNamespace(metadata={"Name": "Example_Package"}, version="1.0"),
        SimpleNamespace(metadata={"Name": "example-package"}, version="2.0"),
    ]
    with patch.object(module.metadata, "distributions", return_value=conflicting):
        with pytest.raises(ValueError, match="conflicting installed versions"):
            module.installed_distribution_versions()
    with patch.object(module.metadata, "distributions", return_value=[]):
        with pytest.raises(ValueError, match="did not contain installed packages"):
            module.installed_distribution_versions()


def test_capture_builder_inventory_uses_installed_distribution_metadata(tmp_path: Path) -> None:
    module = checker()
    assets = tmp_path / "assets"
    assets.mkdir()
    target = "windows-x64"
    tag = "v1.0.27"
    for name in module.target_asset_names(tag, target):
        (assets / name).write_bytes(b"actual asset")
    versions = {"pyqt6": "6.12.1", "pyqt6-qt6": "6.12.0"}
    with patch.object(module, "installed_distribution_versions", return_value=versions):
        record = module.capture_builder_inventory(
            assets_dir=assets, tag=tag, sha="a" * 40,
            repository="owner/project", target=target,
        )
    assert record["distribution_inventory_source"] == "importlib.metadata"
    assert record["distributions"] == {"PyQt6": "6.12.1", "PyQt6-Qt6": "6.12.0"}
    assert set(record["assets_sha256"]) == module.target_asset_names(tag, target)


@pytest.mark.parametrize("separator", ["/", "\\"])
def test_packaged_license_bytes_are_read_from_real_archives(tmp_path: Path, separator: str) -> None:
    module = checker()
    zip_path = tmp_path / "portable.zip"
    tar_path = tmp_path / "portable.tar.gz"
    payload = b"Third party release notices\n"
    with zipfile.ZipFile(zip_path, "w") as package:
        package.writestr(f"docs{separator}THIRD_PARTY_NOTICES.md", payload)
    with tarfile.open(tar_path, "w:gz") as package:
        member = tarfile.TarInfo("usr/share/doc/THIRD_PARTY_NOTICES.md")
        member.size = len(payload)
        package.addfile(member, io.BytesIO(payload))
    assert module.embedded_file_bytes(zip_path, "THIRD_PARTY_NOTICES.md") == payload
    assert module.embedded_file_bytes(tar_path, "THIRD_PARTY_NOTICES.md") == payload
    assert module.embedded_file_bytes(zip_path, "PyQt6-GPL-3.0.txt") is None


@pytest.mark.parametrize("extension", ["exe", "msi", "dmg", "pkg", "deb", "rpm", "AppImage"])
def test_non_portable_packages_do_not_fall_back_to_zip(tmp_path: Path, extension: str) -> None:
    module = checker()
    package = tmp_path / f"relabelled.{extension}"
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr("docs/THIRD_PARTY_NOTICES.md", b"Copied from a companion ZIP")
    with pytest.raises(ValueError, match="different package extension"):
        module.embedded_file_bytes(package, "THIRD_PARTY_NOTICES.md")


def test_portable_notice_must_be_an_unambiguous_regular_file(tmp_path: Path) -> None:
    module = checker()
    wanted = "THIRD_PARTY_NOTICES.md"
    package = tmp_path / "portable.zip"
    notice_link = zipfile.ZipInfo(f"docs/{wanted}")
    notice_link.create_system = 3
    notice_link.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr(notice_link, b"missing-target")
    assert module.embedded_file_bytes(package, wanted) is None
    with zipfile.ZipFile(package, "w") as archive:
        archive.writestr(f"docs/{wanted}", b"expected bytes")
        archive.writestr(f"DOCS/{wanted.lower()}", b"ambiguous Windows path")
    assert module.embedded_file_bytes(package, wanted) is None


def test_deb_license_bytes_are_read_from_filesystem_tar_without_extraction(tmp_path: Path) -> None:
    module = checker()
    deb_path = tmp_path / "remote-ops-workspace-v1.0.27-linux-amd64.deb"
    deb_path.write_bytes(b"Debian package fixture")
    notices = b"Third party release notices from Debian\n"
    filesystem_tar = io.BytesIO()
    with tarfile.open(fileobj=filesystem_tar, mode="w") as package:
        member = tarfile.TarInfo("./usr/share/doc/remote-ops-workspace/THIRD_PARTY_NOTICES.md")
        member.size = len(notices)
        package.addfile(member, io.BytesIO(notices))

    with patch.object(
        module.subprocess,
        "run",
        return_value=SimpleNamespace(returncode=0, stdout=filesystem_tar.getvalue(), stderr=b""),
    ) as run:
        assert module.embedded_file(deb_path, "THIRD_PARTY_NOTICES.md") == (
            "usr/share/doc/remote-ops-workspace/THIRD_PARTY_NOTICES.md", notices,
        )

    run.assert_called_once_with(
        ["dpkg-deb", "--fsys-tarfile", str(deb_path)],
        capture_output=True,
        timeout=300,
        check=False,
    )


@pytest.mark.parametrize("elf_class", [1, 2])
def test_appimage_license_bytes_come_from_the_runtime_squashfs_offset(tmp_path: Path, elf_class: int) -> None:
    module = checker()
    appimage = tmp_path / "remote-ops-workspace-v1.0.27-linux-aarch64.AppImage"
    ident = b"\x7fELF" + bytes((elf_class, 1, 1, 0)) + b"AI\x02" + bytes(5)
    header = struct.Struct("<16sHHIIIIIHHHHHH" if elf_class == 1 else "<16sHHIQQQIHHHHHH")
    section_size = 40 if elf_class == 1 else 64
    padding = b"hsqs" + bytes(92)
    table_offset = header.size + len(padding)
    elf = header.pack(ident, 2, 3, 1, 0, 0, table_offset, 0, header.size, 0, 0, section_size, 1, 0)
    squashfs_offset = table_offset + section_size
    superblock = bytearray(96)
    superblock[:4] = b"hsqs"
    struct.pack_into("<Q", superblock, 40, len(superblock))
    appimage.write_bytes(elf + padding + bytes(section_size) + superblock)
    payload = b"Third party release notices from AppImage\n"

    def inspect(command: list[str], **_kwargs: object) -> SimpleNamespace:
        assert int(command[command.index("-offset") + 1]) == squashfs_offset
        destination = Path(command[command.index("-d") + 1])
        destination.mkdir()
        (destination / "usr" / "share" / "doc").mkdir(parents=True)
        (destination / "usr" / "share" / "doc" / "THIRD_PARTY_NOTICES.md").write_bytes(payload)
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    with patch.object(module.subprocess, "run", side_effect=inspect) as run:
        assert module.embedded_file(appimage, "THIRD_PARTY_NOTICES.md") == (
            "usr/share/doc/THIRD_PARTY_NOTICES.md", payload,
        )

    assert run.call_count == 1
    assert run.call_args.args[0][0:2] == ["unsquashfs", "-d"]

    appimage.write_bytes(elf + padding + bytes(section_size + 96) + superblock)
    with patch.object(module.subprocess, "run") as run:
        with pytest.raises(ValueError, match="no SquashFS payload at the ELF boundary"):
            module.embedded_file_bytes(appimage, "THIRD_PARTY_NOTICES.md")
        run.assert_not_called()


def test_rpm_license_bytes_are_read_from_cpio_without_extracting_paths(tmp_path: Path) -> None:
    module = checker()
    rpm_path = tmp_path / "remote-ops-workspace-v1.0.27-linux-x86_64.rpm"
    rpm_path.write_bytes(b"rpm fixture")
    cpio_payload = b"validated cpio stream"
    notices = b"Third party release notices from RPM\n"

    def inspect(command: list[str], **kwargs: object) -> SimpleNamespace:
        if command[0] == "rpm2cpio":
            return SimpleNamespace(returncode=0, stdout=cpio_payload, stderr=b"")
        assert kwargs["input"] == cpio_payload
        if command == ["cpio", "-it"]:
            listing = (
                b"./usr/share/doc/remote-ops-workspace/THIRD_PARTY_NOTICES.md\n"
                b"./usr/share/doc/remote-ops-workspace/README.md\n"
            )
            return SimpleNamespace(returncode=0, stdout=listing, stderr=b"")
        assert command == [
            "cpio", "-i", "--to-stdout", "--",
            "./usr/share/doc/remote-ops-workspace/THIRD_PARTY_NOTICES.md",
        ]
        return SimpleNamespace(returncode=0, stdout=notices, stderr=b"")

    with patch.object(module.subprocess, "run", side_effect=inspect) as run:
        assert module.embedded_file(rpm_path, "THIRD_PARTY_NOTICES.md") == (
            "usr/share/doc/remote-ops-workspace/THIRD_PARTY_NOTICES.md", notices,
        )

    assert [call.args[0][0] for call in run.call_args_list] == ["rpm2cpio", "cpio", "cpio"]


@pytest.mark.parametrize("payload_parts", [("Payload",), ("remote-ops-workspace-component.pkg", "Payload")])
def test_pkg_license_bytes_are_read_from_gzip_cpio_payload(
    tmp_path: Path, payload_parts: tuple[str, ...],
) -> None:
    module = checker()
    payload_path = str(Path(*payload_parts))
    pkg_path = tmp_path / "remote-ops-workspace-v1.0.27-macos-arm64.pkg"
    pkg_path.write_bytes(b"xar fixture")
    cpio_payload = b"old ASCII CPIO payload"
    notices = b"Third party release notices from installed macOS app\n"
    member = "./Applications/Remote Ops Workspace.app/Contents/Resources/licenses/THIRD_PARTY_NOTICES.md"

    def inspect(command: list[str], **kwargs: object) -> SimpleNamespace:
        if command[0] == "7z":
            if command[1] == "l":
                assert command == ["7z", "l", "-slt", "-ba", "-txar", str(pkg_path)]
                return SimpleNamespace(returncode=0, stdout=f"Path = {payload_path}\n", stderr="")
            assert command == ["7z", "x", "-so", "-spd", "-txar", str(pkg_path), payload_path]
            return SimpleNamespace(returncode=0, stdout=gzip.compress(cpio_payload), stderr=b"")
        assert kwargs["input"] == cpio_payload
        if command == ["cpio", "-it"]:
            return SimpleNamespace(returncode=0, stdout=member.encode() + b"\n", stderr=b"")
        assert command == ["cpio", "-i", "--to-stdout", "--", member]
        return SimpleNamespace(returncode=0, stdout=notices, stderr=b"")

    with patch.object(module.subprocess, "run", side_effect=inspect):
        assert module.embedded_file(pkg_path, "THIRD_PARTY_NOTICES.md") == (member.removeprefix("./"), notices)


def test_pkg_rejects_invalid_compressed_payload(tmp_path: Path) -> None:
    module = checker()
    pkg_path = tmp_path / "installer.pkg"
    pkg_path.write_bytes(b"xar fixture")
    with patch.object(
        module.subprocess, "run",
        side_effect=[
            SimpleNamespace(returncode=0, stdout="Path = Payload\n", stderr=""),
            SimpleNamespace(returncode=0, stdout=b"not gzip", stderr=b""),
        ],
    ):
        with pytest.raises(ValueError, match="cannot decompress.*CPIO payload"):
            module.embedded_file_bytes(pkg_path, "THIRD_PARTY_NOTICES.md")


@pytest.mark.parametrize("payload_paths", [
    [],
    ["unrelated.pkg/Payload"],
    ["Payload", "remote-ops-workspace-component.pkg/Payload"],
])
def test_pkg_rejects_missing_unrelated_or_ambiguous_payload(
    tmp_path: Path, payload_paths: list[str],
) -> None:
    module = checker()
    pkg_path = tmp_path / "installer.pkg"
    pkg_path.write_bytes(b"xar fixture")
    listing = "".join(f"Path = {Path(path)}\n" for path in payload_paths)
    with patch.object(
        module.subprocess, "run", return_value=SimpleNamespace(returncode=0, stdout=listing, stderr=""),
    ) as run:
        with pytest.raises(ValueError, match="must contain one expected XAR payload"):
            module.embedded_file_bytes(pkg_path, "THIRD_PARTY_NOTICES.md")
    run.assert_called_once()


def test_dmg_reads_only_the_regular_license_member_to_stdout(tmp_path: Path) -> None:
    module = checker()
    dmg_path = tmp_path / "installer.dmg"
    dmg_path.write_bytes(b"DMG fixture")
    member = "Remote Ops Workspace.app/Contents/Resources/licenses/THIRD_PARTY_NOTICES.md"
    notices = b"Installed DMG notices\n"
    listing = (
        "Path = Remote Ops Workspace.app/Contents/Resources/QtCore\n"
        "Mode = lrwxr-xr-x\nSymbolic Link = ../Frameworks/QtCore.framework\n\n"
        f"Path = {member}\nMode = -rw-r--r--\nSymbolic Link = \n\n"
    )

    def inspect(command: list[str], **_kwargs: object) -> SimpleNamespace:
        if command[1] == "l":
            return SimpleNamespace(returncode=0, stdout=listing, stderr="")
        assert command == ["7z", "x", "-so", "-spd", str(dmg_path), member]
        return SimpleNamespace(returncode=0, stdout=notices, stderr=b"")

    with patch.object(module.subprocess, "run", side_effect=inspect):
        assert module.embedded_file(dmg_path, "THIRD_PARTY_NOTICES.md") == (member, notices)


@pytest.mark.parametrize("prefix,mode", [("../docs/", "-rw-r--r--"), ("/docs/", "-rw-r--r--")])
def test_dmg_rejects_unsafe_regular_member_paths(tmp_path: Path, prefix: str, mode: str) -> None:
    module = checker()
    dmg_path = tmp_path / "installer.dmg"
    dmg_path.write_bytes(b"DMG fixture")
    listing = f"Path = {prefix}THIRD_PARTY_NOTICES.md\nMode = {mode}\n\n"
    with patch.object(
        module.subprocess, "run",
        return_value=SimpleNamespace(returncode=0, stdout=listing, stderr=""),
    ):
        with pytest.raises(ValueError, match="unsafe DMG member"):
            module.embedded_file_bytes(dmg_path, "THIRD_PARTY_NOTICES.md")


def test_dmg_does_not_accept_a_license_symlink_or_ambiguous_file(tmp_path: Path) -> None:
    module = checker()
    dmg_path = tmp_path / "installer.dmg"
    dmg_path.write_bytes(b"DMG fixture")
    symlink = "Path = docs/THIRD_PARTY_NOTICES.md\nMode = lrwxrwxrwx\nSymbolic Link = elsewhere\n\n"
    regular = "Path = docs/THIRD_PARTY_NOTICES.md\nMode = -rw-r--r--\n\n"
    for listing in (symlink, regular + regular.replace("docs/", "other/")):
        with patch.object(
            module.subprocess, "run",
            return_value=SimpleNamespace(returncode=0, stdout=listing, stderr=""),
        ) as run:
            assert module.embedded_file_bytes(dmg_path, "THIRD_PARTY_NOTICES.md") is None
        assert run.call_count == 1


@pytest.mark.parametrize("suffix,tool", [(".exe", "innoextract"), (".msi", "msiextract")])
def test_windows_installer_reads_restored_installed_filenames(
    tmp_path: Path, suffix: str, tool: str
) -> None:
    module = checker()
    archive = tmp_path / f"installer{suffix}"
    archive.write_bytes(b"Windows installer fixture")
    notices = b"Actual installed notices, not a cabinet file ID\n"

    def inspect(command: list[str], **_kwargs: object) -> SimpleNamespace:
        assert command[0] == tool
        option = "-C" if suffix == ".msi" else "--output-dir"
        destination = Path(command[command.index(option) + 1])
        installed = destination / "Remote Ops Workspace" / "docs"
        installed.mkdir(parents=True)
        (installed / "THIRD_PARTY_NOTICES.md").write_bytes(notices)
        (installed / "ThirdPartyNoticesFile").write_bytes(b"cabinet key is not a filename")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    with patch.object(module.subprocess, "run", side_effect=inspect):
        assert module.embedded_file(archive, "THIRD_PARTY_NOTICES.md") == (
            "Remote Ops Workspace/docs/THIRD_PARTY_NOTICES.md", notices,
        )


@pytest.mark.parametrize("suffix", [".exe", ".msi"])
def test_windows_installer_extraction_failure_is_not_accepted(tmp_path: Path, suffix: str) -> None:
    module = checker()
    archive = tmp_path / f"installer{suffix}"
    archive.write_bytes(b"Windows installer fixture")
    with patch.object(
        module.subprocess, "run",
        return_value=SimpleNamespace(returncode=1, stdout="", stderr="unsupported installer"),
    ):
        with pytest.raises(ValueError, match="cannot extract.*exit 1.*unsupported installer"):
            module.embedded_file_bytes(archive, "THIRD_PARTY_NOTICES.md")


def test_builder_inventory_rejects_unhashed_native_bytes(tmp_path: Path) -> None:
    module = checker()
    assets = tmp_path / "assets"
    inventories = tmp_path / "inventory"
    assets.mkdir()
    inventories.mkdir()
    tag = "v1.0.27"
    sha = "a" * 40
    for target in module.BUILD_TARGETS:
        names = module.target_asset_names(tag, target)
        for name in names:
            (assets / name).write_bytes(b"actual asset")
        (inventories / f"{target}.json").write_text(
            json.dumps({
                "schema_version": 1,
                "repository": "owner/project",
                "release_tag": tag,
                "release_sha": sha,
                "target": target,
                "distribution_inventory_source": "importlib.metadata",
                "distributions": {"PyQt6": "6.12.1", "PyQt6-Qt6": "6.12.0"},
                "assets_sha256": {name: "0" * 64 for name in names},
            }),
            encoding="utf-8",
        )
    with pytest.raises(ValueError, match="digest differs"):
        module.check_builder_inventories(inventories, assets, tag, sha, "owner/project")

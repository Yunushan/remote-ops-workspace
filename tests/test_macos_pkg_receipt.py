from __future__ import annotations

from pathlib import Path

import pytest

from scripts import check_macos_pkg_receipt as metadata

VERSION = "1.0.28"
INFO = (
    f'<pkg-info identifier="{metadata.APP_ID}" version="{VERSION}" install-location="/" auth="root" relocatable="false">'
    '<payload numberOfFiles="4" installKBytes="64"/><relocate/>'
    '</pkg-info>'
)
DIST = (
    '<installer-gui-script minSpecVersion="1"><volume-check><allowed-os-versions><os-version min="14.4"/>'
    '</allowed-os-versions></volume-check>'
    f'<pkg-ref id="{metadata.APP_ID}" version="{VERSION}">#{metadata.COMPONENT}</pkg-ref></installer-gui-script>'
)
APP_PATHS = (metadata.APP, metadata.APP + "/Contents", metadata.LAUNCHER, metadata.APP + "/Contents/Info.plist")
RECEIPT = f"package-id: {metadata.APP_ID}\nversion: {VERSION}\nvolume: /\nlocation: /\ninstall-time: 100\n"


def write(path: Path, text: str) -> Path:
    path.write_bytes(text.encode("utf-8"))
    return path


@pytest.fixture
def package(tmp_path):
    expanded = tmp_path / "expanded"
    component = expanded / metadata.COMPONENT
    component.mkdir(parents=True)
    write(expanded / "Distribution", DIST)
    write(component / "PackageInfo", INFO)
    return expanded


@pytest.mark.parametrize("location", ("/", "", "."))
def test_check_accepts_the_same_package_paths_without_root_entries(package, tmp_path, location, capsys):
    paths = write(tmp_path / "bom", ".\n./Applications\n" + "\n".join(f"./{name}" for name in APP_PATHS) + "\n")
    paths.write_bytes(paths.read_bytes().replace(b"\n", b"\r\n"))
    info = write(tmp_path / "info", RECEIPT.replace("location: /", f"location: {location}"))
    files = write(tmp_path / "files", "\n".join(APP_PATHS) + "\n")
    common = ["--version", VERSION, "--bom-paths", str(paths)]
    assert metadata.main(["package", "--expanded", str(package), *common]) == 0
    assert metadata.main(["receipt", "--info", str(info), "--files", str(files), *common]) == 0
    assert "4 package paths matched" in capsys.readouterr().out


@pytest.mark.parametrize(("file", "old", "new", "message"), [
    ("Distribution", 'min="14.4"', 'min="13.0"', "must require macOS 14.4"),
    ("Distribution", metadata.COMPONENT, "other-component.pkg", "exact application component"),
    ("Distribution", VERSION, "1.0.280", "exact application component"),
    ("PackageInfo", 'install-location="/"', 'install-location="/tmp"', "root install location"),
    ("PackageInfo", 'relocatable="false"', 'relocatable="true"', "root install location"),
    ("PackageInfo", 'auth="root"', 'auth="none"', "root install location"),
    ("PackageInfo", f'identifier="{metadata.APP_ID}"', 'identifier="com.example.package"', "component identity"),
    ("PackageInfo", VERSION, "1.0.280", "component identity"),
    ("PackageInfo", "<relocate/>", '<relocate path="elsewhere"/>', "declares a relocation"),
    ("PackageInfo", "<relocate/>", "<scripts><postinstall/></scripts>", "contain installer scripts"),
    ("PackageInfo", "<pkg-info", '<!DOCTYPE pkg-info [<!ENTITY fixture "x">]><pkg-info', "document type or entity"),
])
def test_expanded_package_rejects_wrong_metadata(package, file, old, new, message):
    path = package / (file if file == "Distribution" else f"{metadata.COMPONENT}/{file}")
    write(path, path.read_text(encoding="utf-8").replace(old, new))
    with pytest.raises(ValueError, match=message):
        metadata.check_package(package, VERSION)


def test_package_rejects_script_archive_even_with_no_script_declaration(package):
    write(package / metadata.COMPONENT / "Scripts", "not allowed")
    with pytest.raises(ValueError, match="contain installer scripts"):
        metadata.check_package(package, VERSION)


@pytest.mark.parametrize(("entries", "message"), [
    (("Library/LaunchAgents/extra.plist",), "outside the stock app"),
    ((metadata.APP + "/../elsewhere",), "unsafe path"),
    ((metadata.APP + "/Contents/control\tfile",), "unsafe path"),
    ((metadata.APP + "/contents/Info.plist",), "duplicate or aliased"),
])
def test_package_path_listing_checks_scope_and_aliases(tmp_path, entries, message):
    paths = write(tmp_path / "bom", "\n".join((*APP_PATHS, *entries)))
    with pytest.raises(ValueError, match=message):
        metadata.app_paths(paths)


def test_package_inventory_rejects_a_missing_launcher(tmp_path):
    paths = write(tmp_path / "bom", "\n".join(path for path in APP_PATHS if path != metadata.LAUNCHER))
    with pytest.raises(ValueError, match="does not include the app executable"):
        metadata.app_paths(paths)


@pytest.mark.parametrize(("from_text", "replacement"), [
    (metadata.APP_ID, "com.example.receipt"),
    (VERSION, "1.0.280"),
    ("volume: /", "volume: /Volumes/Other"),
    ("location: /", "location: /Applications"),
    ("location: /", ""),
])
def test_receipt_requires_exact_identity_and_root_location(tmp_path, from_text, replacement):
    text = RECEIPT.replace(from_text, replacement)
    info = write(tmp_path / "info", text.replace("\n\n", "\n"))
    paths = write(tmp_path / "files", "\n".join(APP_PATHS))
    with pytest.raises(ValueError, match="receipt identity, version, or root location"):
        metadata.check_receipt(info, paths, set(APP_PATHS), VERSION)


@pytest.mark.parametrize(("extra", "missing", "message"), [
    ((), (APP_PATHS[-1],), "1 missing, 0 unexpected"),
    ((metadata.APP + "/Contents/Extra",), (), "0 missing, 1 unexpected"),
])
def test_receipt_file_listing_must_match_the_package(tmp_path, extra, missing, message):
    info = write(tmp_path / "info", RECEIPT)
    paths = write(tmp_path / "files", "\n".join(tuple(name for name in APP_PATHS if name not in missing) + extra))
    with pytest.raises(ValueError, match=message):
        metadata.check_receipt(info, paths, set(APP_PATHS), VERSION)

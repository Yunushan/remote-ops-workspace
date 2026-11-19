"""Capture Professional installer branding from the exact native Windows files."""

from __future__ import annotations

import argparse
import json
import mmap
import os
import shutil
import struct
import subprocess
import sys
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Any
from xml.etree import ElementTree

ROOT = Path(__file__).resolve().parents[1]
for location in (ROOT, ROOT / "src"):
    if str(location) not in sys.path:
        sys.path.insert(0, str(location))

from remote_ops_workspace.moba_customizer import (  # noqa: E402
    build_installer_branding_plan,
    validate_professional_update_manifest,
)
from scripts.check_moba_professional_deployment_evidence import (  # noqa: E402
    INSTALLER_CAPTURE_SCHEMA,
    decode_object,
    read_object,
    read_small,
    verify_exe_icon,
    verify_windows_capture,
)
from scripts.check_mobaxterm_parity_evidence import capture_release_identity  # noqa: E402
from scripts.check_release_license_compliance import (  # noqa: E402
    secure_regular_file,
    sha256_file,
    valid_sha256,
)
from scripts.release_candidate_inventory import safe_name  # noqa: E402

DIRECTORY_FLAG = 0x80000000
ICON_RESOURCE_TYPE = 3
MAX_ICON_BYTES = 1024 * 1024
VERSION_FIELDS = ("ProductName", "CompanyName", "ProductVersion")
VERSION_QUERY = """
[Console]::OutputEncoding = [Text.UTF8Encoding]::new($false)
$info = [Diagnostics.FileVersionInfo]::GetVersionInfo($env:ROW_INSPECT_INSTALLER)
[ordered]@{
    ProductName = ([string]$info.ProductName).Trim()
    CompanyName = ([string]$info.CompanyName).Trim()
    ProductVersion = ([string]$info.ProductVersion).Trim()
} | ConvertTo-Json -Compress
"""


def resource_section(image: mmap.mmap) -> tuple[int, int, int, int, int]:
    if len(image) < 64 or image[:2] != b"MZ":
        raise ValueError("installer is missing a DOS header")
    pe = struct.unpack_from("<I", image, 0x3C)[0]
    if not 64 <= pe <= len(image) - 24 or image[pe:pe + 4] != b"PE\0\0":
        raise ValueError("installer is missing a PE header")
    count = struct.unpack_from("<H", image, pe + 6)[0]
    optional_size = struct.unpack_from("<H", image, pe + 20)[0]
    optional = pe + 24
    sections = optional + optional_size
    if not 1 <= count <= 96 or optional_size < 2 or sections + 40 * count > len(image):
        raise ValueError("installer has an invalid section table")
    magic = struct.unpack_from("<H", image, optional)[0]
    directory = {0x10B: 96, 0x20B: 112}.get(magic)
    if directory is None or directory + 24 > optional_size:
        raise ValueError("installer has an invalid PE resource directory")
    directory_count = struct.unpack_from("<I", image, optional + directory - 4)[0]
    root_rva, root_size = struct.unpack_from("<II", image, optional + directory + 16)
    for offset in range(sections, sections + count * 40, 40):
        if image[offset:offset + 8] != b".rsrc\0\0\0":
            continue
        section_rva, raw_size, start = struct.unpack_from("<III", image, offset + 12)
        relative = root_rva - section_rva
        if directory_count >= 3 and 0 <= relative <= raw_size - root_size and root_size >= 16 and start + raw_size <= len(image):
            return section_rva, start, raw_size, start + relative, root_size
    raise ValueError("installer has no usable PE resource section")


def resource_entries(image: mmap.mmap, root: int, size: int, relative: int) -> list[tuple[int, int]]:
    if relative > size - 16:
        raise ValueError("resource directory escapes its PE section")
    header = root + relative
    named, numbered = struct.unpack_from("<HH", image, header + 12)
    count = named + numbered
    if count > (size - relative - 16) // 8:
        raise ValueError("resource entries escape their PE section")
    return list(struct.iter_unpack("<II", image[header + 16:header + 16 + count * 8]))


def find_icon(executable: Path, logo: bytes) -> tuple[int, bytes]:
    with executable.open("rb") as stream, mmap.mmap(stream.fileno(), 0, access=mmap.ACCESS_READ) as image:
        section_rva, start, raw_size, root, root_size = resource_section(image)
        for kind, names in resource_entries(image, root, root_size, 0):
            if kind != ICON_RESOURCE_TYPE or not names & DIRECTORY_FLAG:
                continue
            for _, languages in resource_entries(image, root, root_size, names & ~DIRECTORY_FLAG):
                if not languages & DIRECTORY_FLAG:
                    raise ValueError("EXE icon lacks a language directory")
                for _, data in resource_entries(image, root, root_size, languages & ~DIRECTORY_FLAG):
                    if data & DIRECTORY_FLAG or data > root_size - 16:
                        raise ValueError("invalid EXE icon data entry")
                    rva, length = struct.unpack_from("<II", image, root + data)
                    relative = rva - section_rva
                    if not 0 < length <= MAX_ICON_BYTES or not 0 <= relative <= raw_size - length:
                        raise ValueError("EXE icon bytes escape the supported resource range")
                    offset = start + relative
                    content = image[offset:offset + length]
                    try:
                        verify_exe_icon(logo, content)
                    except ValueError:
                        continue
                    return offset, content
    raise ValueError("the EXE contains no icon resource matching the original logo")


def inspect_exe_version(executable: Path) -> dict[str, str]:
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-NonInteractive", "-Command", VERSION_QUERY],
        env={**os.environ, "ROW_INSPECT_INSTALLER": str(executable)},
        stdin=subprocess.DEVNULL, capture_output=True, encoding="utf-8", timeout=30, check=True,
    )
    fields = json.loads(result.stdout)
    if not isinstance(fields, dict) or any(not isinstance(fields.get(key), str) or not fields[key] for key in VERSION_FIELDS):
        raise ValueError("native Windows version information is missing branding fields")
    return fields


def native_msi_files(wix: str, package: Path, scratch: Path) -> tuple[bytes, bytes, bytes]:
    command = shutil.which(wix)
    if command is None:
        raise ValueError("the Windows WiX CLI could not be found")
    source, exports = scratch / "installer.wxs", scratch / "export"
    subprocess.run(
        [str(Path(command).absolute()), "msi", "decompile", "-x", exports.name, "-o", source.name, str(package)],
        cwd=scratch, stdin=subprocess.DEVNULL, capture_output=True, text=True, errors="replace", timeout=120, check=True,
    )
    xml = read_small(source, "decompiled MSI")
    icon = regular(exports, "Icon/RemoteOpsWorkspaceIcon", "MSI exported icon")
    welcome = regular(exports, "File/WelcomeFile", "MSI exported welcome")
    return xml, read_small(icon, "MSI exported icon"), read_small(welcome, "MSI exported welcome")


def regular(root: Path, name: str, label: str) -> Path:
    path, error = secure_regular_file(root, name, label)
    if path is None:
        raise ValueError(error)
    return path


def attach(root: Path, name: str, raw: bytes) -> dict[str, str]:
    target = root / name
    target.write_bytes(raw)
    return {"evidence_file": name, "evidence_sha256": sha256_file(target)}


def json_bytes(document: dict[str, Any]) -> bytes:
    return (json.dumps(document, indent=2, sort_keys=True) + "\n").encode("utf-8")


def copy_installers(
    root: Path, native: Path, plan_names: dict[str, str], build: dict[str, Any], update: dict[str, Any],
) -> dict[str, Path]:
    records = build.get("artifacts")
    if not isinstance(records, list) or len(records) != len(plan_names) or any(not isinstance(row, dict) for row in records):
        raise ValueError("the native build manifest must identify both installers")
    paths: dict[str, Path] = {}
    for kind, name in plan_names.items():
        expected = [row for row in records if row.get("name") == name]
        rows = [row for row in update.get("artifacts", []) if isinstance(row, dict) and row.get("name") == name]
        if len(expected) != 1 or len(rows) != 1:
            raise ValueError(f"the build and signed update manifest must each name {name} once")
        relative = rows[0].get("file")
        if not isinstance(relative, str):
            raise ValueError(f"the signed manifest must name the local installer for {name}")
        posix = PurePosixPath(relative)
        if posix.as_posix() != relative or posix.name != name or any(not safe_name(part) for part in posix.parts):
            raise ValueError(f"the signed manifest path is invalid for {name}")
        digest, size = expected[0].get("sha256"), expected[0].get("size_bytes")
        original = regular(native, name, "native installer")
        if not valid_sha256(digest) or type(size) is not int or size <= 0 or original.stat().st_size != size:
            raise ValueError(f"the native installer does not match the build inventory for {name}")
        target = root / posix
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(original, target)
        if sha256_file(target) != digest:
            raise ValueError(f"the native installer digest differs for {name}")
        paths[kind] = target
    return paths


def capture_installers(
    bundle: Path, native: Path, update_path: Path, key: str, wix: str, output: Path,
    *, source_path: Path | None = None, release_asset: Path | None = None,
) -> Path:
    if sys.platform != "win32":
        raise ValueError("native installer capture requires Windows")
    if output.exists() or output.is_symlink():
        raise ValueError("capture output must be a new directory")
    output = output.absolute()
    manifest_file = regular(bundle, "manifest.json", "customizer manifest")
    manifest_bytes = read_small(manifest_file, "customizer manifest")
    original = decode_object(manifest_bytes, "customizer manifest")
    brand, organization, version = (original[key] for key in ("brand_name", "organization", "project_version"))
    plan = build_installer_branding_plan(brand_name=brand, version=version, organization=organization)
    build_file = regular(native, "enterprise-installers.json", "Windows build manifest")
    build_bytes = read_small(build_file, "Windows build manifest")
    build = decode_object(build_bytes, "Windows build manifest")
    target = f"windows-{build['architecture']}"
    if target not in {"windows-x86", "windows-x64", "windows-arm64"}:
        raise ValueError("installer capture requires a supported Windows architecture")
    logo = read_small(regular(bundle, "branding/logo.ico", "customizer logo"), "customizer logo")
    welcome = read_small(regular(bundle, "welcome.txt", "customizer welcome"), "customizer welcome")
    if (source_path is None) != (release_asset is None):
        raise ValueError("a release capture requires both the source identity and the published source asset")
    provenance: dict[str, Any] = {}
    if source_path is not None and release_asset is not None:
        provenance = {
            "source": read_object(source_path, "release source identity"),
            "release_asset": {"name": release_asset.name, "sha256": sha256_file(release_asset)},
        }
        identity = capture_release_identity(provenance, "Windows installer capture")
        if identity["release_tag"] != f"v{version}":
            raise ValueError("release source tag must match the customizer project version")

    with TemporaryDirectory(prefix=".installer-capture-", dir=output.parent) as temporary:
        scratch = Path(temporary)
        root = scratch / "review"
        root.mkdir()
        update = attach(root, "signed-update.json", read_small(update_path, "signed update manifest"))
        signed_path = root / update["evidence_file"]
        update_data = read_object(signed_path, "signed update manifest")
        installers = copy_installers(root, native, plan.artifact_names, build, update_data)
        signed = validate_professional_update_manifest(signed_path, public_key=key, assets_dir=root,
                                                       expected_organization=organization)
        if not signed.passed:
            raise ValueError("signed update manifest failed validation\n" + "\n".join(signed.errors))

        exe = installers["windows-exe"]
        offset, icon = find_icon(exe, logo)
        version_info = inspect_exe_version(exe)
        xml, msi_icon, msi_welcome = native_msi_files(wix, installers["windows-msi"], scratch)
        capture = {
            **provenance,
            "schema": INSTALLER_CAPTURE_SCHEMA,
            "build_manifest": attach(root, "enterprise-installers.json", build_bytes),
            "logo": attach(root, "logo.ico", logo),
            "welcome": attach(root, "welcome.txt", welcome),
            "installer_sha256": {path.name: sha256_file(path) for path in installers.values()},
            "exe_version": attach(root, "exe-version.json", json_bytes(version_info)),
            "exe_icon": attach(root, "exe-icon.bin", icon),
            "exe_icon_offset": offset,
            "msi_database": attach(root, "installer.wxs", xml),
            "msi_icon": attach(root, "msi-icon.ico", msi_icon),
            "msi_welcome": attach(root, "msi-welcome.txt", msi_welcome),
        }
        manifest = attach(root, "bundle-manifest.json", manifest_bytes)
        result = {
            **provenance,
            "release_target": target, "brand_name": brand, "version": version,
            "bundle_manifest": {**manifest, "manifest_sha256": manifest["evidence_sha256"]},
            "installer_branding": attach(root, "installer-capture.json", json_bytes(capture)),
            "update_manifest": update,
        }
        result["verified_installer_metadata"] = verify_windows_capture(root, result, capture, update_data)
        if release_asset is not None and sha256_file(release_asset) != provenance["release_asset"]["sha256"]:
            raise ValueError("the published source asset changed during capture")
        attach(root, "installer-review.json", json_bytes(result))
        root.rename(output)
    return output / "installer-review.json"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--bundle", type=Path, required=True)
    parser.add_argument("--installers", type=Path, required=True)
    parser.add_argument("--update-manifest", type=Path, required=True)
    parser.add_argument("--update-key", required=True, help="trusted public key for the signed update manifest")
    parser.add_argument("--wix", default=shutil.which("wix.exe"), help="path to the native WiX CLI")
    parser.add_argument("--out", type=Path, required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--source", type=Path, help="source identity from the release qualification run")
    mode.add_argument("--local", action="store_true", help="rehearse without hosted release provenance")
    parser.add_argument("--release-asset", type=Path, help="exact published source asset exercised by the build")
    args = parser.parse_args()
    if not args.wix:
        parser.error("the Windows WiX CLI is required")
    try:
        review = capture_installers(
            args.bundle, args.installers, args.update_manifest, args.update_key, args.wix, args.out,
            source_path=args.source, release_asset=args.release_asset,
        )
    except subprocess.CalledProcessError as error:
        parser.exit(1, f"Native installer inspection failed with exit status {error.returncode}\n{error.stderr or ''}")
    except (OSError, ValueError, KeyError, TypeError, ElementTree.ParseError, subprocess.TimeoutExpired) as error:
        parser.exit(1, f"Native installer capture failed: {error}\n")
    print(f"Verified Windows installer metadata in {review}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

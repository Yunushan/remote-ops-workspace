"""Verify the required notices inside every production native package without running it."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import tarfile
import tempfile
import zipfile
from collections.abc import Iterator
from contextlib import suppress
from pathlib import Path, PurePosixPath
from typing import Any, NamedTuple

from check_preview_redistribution import (
    BUILD_TARGETS,
    GUI_TARGET,
    MATRIX_PATH,
    NATIVE_PACKAGE,
    ROOT,
    TAG,
    ComponentLicense,
    EmbeddedFile,
    check_packaged_legal_material,
    expected_native_assets,
    file_hash,
    regular_child,
)
from check_release_license_compliance import path_is_reparse, safe_relative_path
from package_license_review_inputs import manifest_review_inputs
from packaged_desktop_licenses import read_desktop_component_licenses
from packaged_linux_licenses import read_linux_component_licenses

PROTECTED_LINUX_PACKAGE = re.compile(
    r"remote-ops-workspace-v\d+\.\d+\.\d+-linux-(?:i386|i686|armhf|armv7hl)"
    r"(?:-native)?\.(?:deb|rpm|AppImage|tar\.gz)\Z"
)
GUI_LICENSE_COMPONENTS = {
    "PyQt6-GPL-3.0.txt": "pyqt6",
    "Qt-LGPL-3.0.txt": "pyqt6-qt6",
}


class PackageNotices(NamedTuple):
    name: str
    sha256: str
    size_bytes: int
    files: list[EmbeddedFile | ComponentLicense]


def expected_production_packages(tag: str, *, matrix: dict[str, Any] | None = None) -> set[str]:
    if matrix is None:
        matrix = json.loads(MATRIX_PATH.read_bytes())
    standard = {name for name in expected_native_assets(tag, matrix=matrix) if NATIVE_PACKAGE.fullmatch(name)}
    protected = {
        name
        for target in matrix.get("script_supported_native", ())
        for pattern in target["asset_patterns"]
        if PROTECTED_LINUX_PACKAGE.fullmatch(name := re.sub(r"v\d+\.\d+\.\d+", tag, pattern))
    }
    return standard | protected


def expected_production_manifest_packages(tag: str, matrix: dict[str, Any]) -> dict[str, set[str]]:
    """Map each packaged release manifest to its exact release matrix assets."""
    standard = expected_native_assets(tag, matrix=matrix)
    groups: dict[str, set[str]] = {}
    for name in sorted(standard):
        if not name.endswith("-native-manifest.json"):
            continue
        target = name.removeprefix(f"remote-ops-workspace-{tag}-").removesuffix("-native-manifest.json")
        if target not in BUILD_TARGETS:
            raise ValueError(f"release matrix has an unsupported native manifest: {name}")
        groups[name] = {
            asset for asset in standard
            if (match := NATIVE_PACKAGE.fullmatch(asset)) and match[2] in BUILD_TARGETS[target]
        }

    for target in matrix.get("script_supported_native", ()):
        names = {re.sub(r"v\d+\.\d+\.\d+", tag, pattern) for pattern in target["asset_patterns"]}
        packages = {name for name in names if PROTECTED_LINUX_PACKAGE.fullmatch(name)}
        if not packages:
            continue
        manifests = sorted(name for name in names if name.endswith("-native-manifest.json"))
        if len(manifests) != 1 or manifests[0] in groups:
            raise ValueError(f"protected Linux package group requires one unique native manifest: {sorted(packages)}")
        groups[manifests[0]] = packages

    expected = expected_production_packages(tag, matrix=matrix)
    if (
        any(not members for members in groups.values())
        or sum(map(len, groups.values())) != len(expected)
        or set().union(*groups.values()) != expected
    ):
        raise ValueError("release matrix must assign every production package to exactly one native manifest")
    return groups


def publish_notice_capture(
    destination: Path, tag: str, packages: dict[str, Any], blobs: dict[str, bytes],
    *, review: dict[str, Any] | None = None,
) -> None:
    with tempfile.TemporaryDirectory(prefix=".row-packaged-notices-", dir=destination.parent) as temporary:
        staged = Path(temporary) / "packaged-notices"
        files = staged / "files"
        files.mkdir(parents=True)
        for digest, data in blobs.items():
            (files / f"{digest}.bin").write_bytes(data)
        report = {
            "schema": "row.packaged-notice-extraction.v1",
            "release_tag": tag,
            "packages": packages,
        }
        (staged / "notice-extraction.json").write_bytes((json.dumps(report, indent=2) + "\n").encode("utf-8"))
        if review is not None:
            (staged / "review-inputs.json").write_bytes((json.dumps(review, indent=2) + "\n").encode("utf-8"))
        if os.name == "nt":
            staged.rename(destination)
        else:
            # Reserve the output name before rename, which can replace empty directories on POSIX.
            destination.mkdir(mode=0o700)
            try:
                staged.rename(destination)
            except OSError:
                with suppress(OSError):
                    destination.rmdir()
                raise


def observe_notices(assets_dir: Path, expected: set[str]) -> Iterator[PackageNotices]:
    actual = {
        path.name for path in assets_dir.iterdir()
        if NATIVE_PACKAGE.fullmatch(path.name) or PROTECTED_LINUX_PACKAGE.fullmatch(path.name)
    }
    if actual != expected:
        raise ValueError(
            f"native package inventory differs from the release matrix "
            f"(missing {sorted(expected - actual)}, unexpected {sorted(actual - expected)})"
        )
    material_dir = ROOT / "redistribution-evidence"
    project_license = regular_child(ROOT, "LICENSE", "application license").read_bytes().replace(b"\r\n", b"\n")
    notices = {
        "THIRD_PARTY_NOTICES.md": file_hash(
            regular_child(material_dir, "THIRD_PARTY_NOTICES.md", "third-party notices"),
        ),
    }
    gui = {
        **notices,
        **{
            filename: file_hash(regular_child(material_dir, filename, "GUI redistribution material"))
            for filename in (*GUI_LICENSE_COMPONENTS, "Qt-Relinking.md")
        },
    }
    for name in sorted(expected):
        package = regular_child(assets_dir, name, "native package")
        package_sha = file_hash(package)
        package_size = package.stat().st_size
        embedded: list[EmbeddedFile | ComponentLicense] = []
        for member in check_packaged_legal_material(package, gui if GUI_TARGET.search(name) else notices):
            component = GUI_LICENSE_COMPONENTS.get(PurePosixPath(member.path).name)
            embedded.append(ComponentLicense(member.path, member.data, component) if component else member)
        if "-linux-" in name:
            component_licenses = read_linux_component_licenses(package)
        else:
            target = NATIVE_PACKAGE.fullmatch(name)
            assert target is not None
            component_licenses = read_desktop_component_licenses(package, target[2])
        for license_file in component_licenses:
            if (
                license_file.component == "remote-ops-workspace"
                and license_file.data.replace(b"\r\n", b"\n") != project_license
            ):
                raise ValueError(f"{name} contains different bytes for the application license")
        embedded.extend(component_licenses)
        if package.stat().st_size != package_size or file_hash(package) != package_sha:
            raise ValueError(f"{name} changed during notice extraction")
        if any(not safe_relative_path(member.path) for member in embedded):
            raise ValueError(f"{name} has an invalid packaged notice path")
        yield PackageNotices(name, package_sha, package_size, embedded)


def verify_notices(
    assets_dir: Path, tag: str, *, evidence_root: Path | None = None, write_review_inputs: bool = False,
) -> int:
    if not TAG.fullmatch(tag):
        raise ValueError("release tag must be an exact vX.Y.Z tag")
    if write_review_inputs and evidence_root is None:
        raise ValueError("--write-review-inputs requires --evidence-root")
    capture = None
    if evidence_root is not None:
        evidence_root = evidence_root.absolute()
        capture = evidence_root / "packaged-notices"
        if (
            not evidence_root.is_dir() or any(path_is_reparse(path) for path in (*evidence_root.parents, evidence_root))
            or capture.resolve().is_relative_to(assets_dir.resolve()) or os.path.lexists(capture)
        ):
            raise ValueError("--evidence-root must be a real directory outside the assets with no packaged-notices output")
    expected = expected_production_packages(tag)
    packages = {}
    blobs = {}
    for package in observe_notices(assets_dir, expected):
        if capture is not None:
            records = []
            for member in package.files:
                digest = hashlib.sha256(member.data).hexdigest()
                blobs.setdefault(digest, member.data)
                record = {
                    "path": member.path,
                    "file": f"packaged-notices/files/{digest}.bin",
                    "sha256": digest,
                    "size_bytes": len(member.data),
                }
                if isinstance(member, ComponentLicense):
                    record["component"] = member.component
                    if member.version is not None:
                        record["origin"] = "native-component"
                        record["version"] = member.version
                records.append(record)
            packages[package.name] = {
                "sha256": package.sha256, "size_bytes": package.size_bytes, "notice_files": records,
            }
    if capture is not None:
        review = (
            manifest_review_inputs(
                assets_dir, tag, expected_production_manifest_packages(tag, json.loads(MATRIX_PATH.read_bytes())), packages,
            )
            if write_review_inputs else None
        )
        publish_notice_capture(capture, tag, packages, blobs, review=review)
    return len(expected)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets-dir", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--evidence-root", type=Path, help="retain verified notices in a new packaged-notices subdirectory")
    parser.add_argument("--write-review-inputs", action="store_true", help="prepare per-manifest license scan records")
    args = parser.parse_args()
    try:
        count = verify_notices(
            args.assets_dir, args.tag, evidence_root=args.evidence_root, write_review_inputs=args.write_review_inputs,
        )
    except (OSError, ValueError, zipfile.BadZipFile, tarfile.TarError) as exc:
        print(f"production package notices: {exc}", file=sys.stderr)
        return 1
    print(f"Verified required embedded notices in {count} exact native packages")
    if args.evidence_root is not None:
        print(f"Captured notice evidence in {args.evidence_root / 'packaged-notices'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

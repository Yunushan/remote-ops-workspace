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
from contextlib import suppress
from pathlib import Path
from typing import Any

from check_preview_redistribution import (
    GUI_TARGET,
    MATRIX_PATH,
    NATIVE_PACKAGE,
    ROOT,
    TAG,
    check_packaged_legal_material,
    expected_native_assets,
    file_hash,
    regular_child,
)
from check_release_license_compliance import path_is_reparse, safe_relative_path
from packaged_desktop_licenses import read_desktop_runtime_licenses
from packaged_linux_licenses import read_runtime_licenses

PROTECTED_LINUX_PACKAGE = re.compile(
    r"remote-ops-workspace-v\d+\.\d+\.\d+-linux-(?:i386|i686|armhf|armv7hl)"
    r"(?:-native)?\.(?:deb|rpm|AppImage|tar\.gz)\Z"
)


def expected_production_packages(tag: str) -> set[str]:
    matrix = json.loads(MATRIX_PATH.read_bytes())
    standard = {name for name in expected_native_assets(tag) if NATIVE_PACKAGE.fullmatch(name)}
    protected = {
        name
        for target in matrix["script_supported_native"]
        for pattern in target["asset_patterns"]
        if PROTECTED_LINUX_PACKAGE.fullmatch(name := re.sub(r"v\d+\.\d+\.\d+", tag, pattern))
    }
    return standard | protected


def publish_notice_capture(
    destination: Path, tag: str, packages: dict[str, Any], blobs: dict[str, bytes],
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


def verify_notices(assets_dir: Path, tag: str, *, evidence_root: Path | None = None) -> int:
    if not TAG.fullmatch(tag):
        raise ValueError("release tag must be an exact vX.Y.Z tag")
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
    notices = {
        "THIRD_PARTY_NOTICES.md": file_hash(
            regular_child(material_dir, "THIRD_PARTY_NOTICES.md", "third-party notices"),
        ),
    }
    gui = {
        **notices,
        **{
            filename: file_hash(regular_child(material_dir, filename, "GUI redistribution material"))
            for filename in ("PyQt6-GPL-3.0.txt", "Qt-LGPL-3.0.txt", "Qt-Relinking.md")
        },
    }
    packages = {}
    blobs = {}
    for name in sorted(expected):
        package = regular_child(assets_dir, name, "native package")
        package_sha = file_hash(package) if capture is not None else None
        embedded = check_packaged_legal_material(package, gui if GUI_TARGET.search(name) else notices)
        if "-linux-" in name:
            embedded.extend(read_runtime_licenses(package))
        else:
            target = NATIVE_PACKAGE.fullmatch(name)
            assert target is not None
            embedded.extend(read_desktop_runtime_licenses(package, target[2]))
        if capture is not None:
            if file_hash(package) != package_sha:
                raise ValueError(f"{name} changed during notice extraction")
            records = []
            for member in embedded:
                if not safe_relative_path(member.path):
                    raise ValueError(f"{name} has an invalid packaged notice path")
                digest = hashlib.sha256(member.data).hexdigest()
                blobs.setdefault(digest, member.data)
                records.append({
                    "path": member.path,
                    "file": f"packaged-notices/files/{digest}.bin",
                    "sha256": digest,
                    "size_bytes": len(member.data),
                })
            packages[name] = {
                "sha256": package_sha, "size_bytes": package.stat().st_size, "notice_files": records,
            }
    if capture is not None:
        publish_notice_capture(capture, tag, packages, blobs)
    return len(expected)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets-dir", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--evidence-root", type=Path, help="retain verified notices in a new packaged-notices subdirectory")
    args = parser.parse_args()
    try:
        count = verify_notices(args.assets_dir, args.tag, evidence_root=args.evidence_root)
    except (OSError, ValueError, zipfile.BadZipFile, tarfile.TarError) as exc:
        print(f"production package notices: {exc}", file=sys.stderr)
        return 1
    print(f"Verified required embedded notices in {count} exact native packages")
    if args.evidence_root is not None:
        print(f"Captured notice evidence in {args.evidence_root / 'packaged-notices'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

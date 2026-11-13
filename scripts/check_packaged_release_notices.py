"""Verify the required notices inside every production native package without running it."""

from __future__ import annotations

import argparse
import json
import re
import sys
import tarfile
import zipfile
from pathlib import Path

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


def verify_notices(assets_dir: Path, tag: str) -> int:
    if not TAG.fullmatch(tag):
        raise ValueError("release tag must be an exact vX.Y.Z tag")
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
    for name in sorted(expected):
        package = regular_child(assets_dir, name, "native package")
        check_packaged_legal_material(package, gui if GUI_TARGET.search(name) else notices)
    return len(expected)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets-dir", type=Path, required=True)
    parser.add_argument("--tag", required=True)
    args = parser.parse_args()
    try:
        count = verify_notices(args.assets_dir, args.tag)
    except (OSError, ValueError, zipfile.BadZipFile, tarfile.TarError) as exc:
        print(f"production package notices: {exc}", file=sys.stderr)
        return 1
    print(f"Verified required embedded notices in {count} exact native packages")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

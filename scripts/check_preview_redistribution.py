#!/usr/bin/env python3
"""Fail closed on missing redistribution material for an unsigned native preview.

This is an artifact/evidence check, not a legal certification.  The tagged source
must contain ``redistribution-evidence/preview.json`` and the files it names.
The open-source channel requires exact PyQt6 GPLv3 and Qt LGPLv3 license texts,
corresponding source archives, LGPL relink instructions, and third-party notices.
The license texts and notices must be found in every actual native package;
GUI packages must also contain the PyQt6 and Qt texts.  All downloaded release
asset hashes are recorded in the output report.

There is intentionally no self-asserted commercial bypass.  A commercial
channel needs a separately verifiable vendor grant/trust anchor first.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
MATRIX_PATH = ROOT / "configs" / "release_matrix.json"
REQUIREMENTS_PATH = ROOT / "requirements-release.txt"
HEX = re.compile(r"[0-9a-f]{64}\Z")
TAG = re.compile(r"v\d+\.\d+\.\d+\Z")
SHA = re.compile(r"[0-9a-f]{40}\Z")
NATIVE_PACKAGE = re.compile(
    r"^remote-ops-workspace-(v\d+\.\d+\.\d+)-(windows-(?:x86|x64|arm64)|"
    r"macos-(?:x64|arm64)|linux-(?:amd64|arm64|x86_64|aarch64))"
    r"(?:-native)?(?:-setup)?\.(?:zip|tar\.gz|exe|msi|dmg|pkg|deb|rpm|AppImage)$"
)
GUI_TARGET = re.compile(r"-(?:windows-(?:x64|arm64)|macos-(?:x64|arm64))(?:-|\.)")
REQUIRED_RECORDS = {
    "third_party_notices": "THIRD_PARTY_NOTICES.md",
    "pyqt6_gplv3": "PyQt6-GPL-3.0.txt",
    "qt_lgplv3": "Qt-LGPL-3.0.txt",
    "pyqt6_source": None,
    "qt_source": None,
    "qt_relink_instructions": None,
}
BUILD_TARGETS = {
    "windows-x86": ("windows-x86",),
    "windows-x64": ("windows-x64",),
    "windows-arm64": ("windows-arm64",),
    "macos-x64": ("macos-x64",),
    "macos-arm64": ("macos-arm64",),
    "linux-x86_64": ("linux-amd64", "linux-x86_64"),
    "linux-aarch64": ("linux-arm64", "linux-aarch64"),
}


def expected_native_assets(tag: str) -> set[str]:
    matrix = json.loads(MATRIX_PATH.read_text(encoding="utf-8"))
    names: set[str] = set()
    for job in matrix["default_github_release"]["native_jobs"]:
        for pattern in job["asset_patterns"]:
            versioned = re.sub(r"v\d+\.\d+\.\d+", tag, pattern)
            match = re.search(r"<([^>]+)>", versioned)
            if match:
                names.update(versioned[: match.start()] + choice + versioned[match.end() :] for choice in match.group(1).split("|"))
            else:
                names.add(versioned)
    return names


def pinned_gui_versions() -> dict[str, str]:
    requirements = REQUIREMENTS_PATH.read_text(encoding="utf-8")
    versions: dict[str, str] = {}
    for name in ("PyQt6", "PyQt6-Qt6"):
        match = re.search(rf"(?m)^{re.escape(name)}==([0-9]+(?:\.[0-9]+)+)$", requirements)
        if match is None:
            raise ValueError(f"{name} is not exactly pinned in release requirements")
        versions[name] = match.group(1)
    return versions


def target_asset_names(tag: str, target: str) -> set[str]:
    prefixes = BUILD_TARGETS[target]
    return {
        name for name in expected_native_assets(tag)
        if any(name.startswith(f"remote-ops-workspace-{tag}-{prefix}") for prefix in prefixes)
    }


def file_hash(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def regular_child(root: Path, relative: Any, label: str) -> Path:
    if root.is_symlink() or not root.is_dir():
        raise ValueError(f"{label} directory is missing or a symlink: {root}")
    if not isinstance(relative, str) or not relative or "\\" in relative:
        raise ValueError(f"{label} must name a regular evidence file")
    path = Path(relative)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError(f"{label} path escapes the evidence directory")
    resolved_root = root.resolve(strict=True)
    candidate = root / path
    if candidate.is_symlink() or not candidate.is_file():
        raise ValueError(f"{label} is missing or a symlink: {relative}")
    if not candidate.resolve(strict=True).is_relative_to(resolved_root):
        raise ValueError(f"{label} path escapes the evidence directory")
    return candidate


def evidence_materials(evidence_dir: Path, tag: str) -> dict[str, tuple[Path, str]]:
    manifest_path = regular_child(evidence_dir, "preview.json", "preview evidence manifest")
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(manifest, dict) or manifest.get("schema_version") != 1:
        raise ValueError("preview evidence manifest schema_version must be 1")
    if manifest.get("release_tag") != tag:
        raise ValueError("preview evidence must name the exact release tag")
    channel = manifest.get("channel")
    if channel != "gpl-lgpl":
        raise ValueError(
            "preview redistribution channel must be gpl-lgpl; commercial distribution "
            "requires a separately verifiable vendor grant and trust anchor"
        )
    records = manifest.get("materials")
    if not isinstance(records, dict) or set(records) != set(REQUIRED_RECORDS):
        raise ValueError(f"preview evidence materials must contain exactly {sorted(REQUIRED_RECORDS)}")
    verified: dict[str, tuple[Path, str]] = {}
    for key, required_name in REQUIRED_RECORDS.items():
        record = records[key]
        if not isinstance(record, dict) or set(record) != {"file", "sha256"}:
            raise ValueError(f"{key} must provide file and sha256")
        path = regular_child(evidence_dir, record["file"], key)
        digest = record["sha256"]
        if not isinstance(digest, str) or not HEX.fullmatch(digest):
            raise ValueError(f"{key} sha256 must be lowercase SHA-256")
        if path.name != required_name and required_name is not None:
            raise ValueError(f"{key} must use {required_name}")
        if file_hash(path) != digest:
            raise ValueError(f"{key} sha256 does not match evidence bytes")
        minimum_size = 10_000 if key == "pyqt6_gplv3" else 5_000 if key == "qt_lgplv3" else 500
        if path.stat().st_size < minimum_size:
            raise ValueError(f"{key} evidence is too small to establish its claimed material")
        if key == "pyqt6_gplv3" and "GNU GENERAL PUBLIC LICENSE" not in path.read_text(encoding="utf-8"):
            raise ValueError("PyQt6 license material must contain the GPL terms")
        if key == "qt_lgplv3" and "GNU LESSER GENERAL PUBLIC LICENSE" not in path.read_text(encoding="utf-8"):
            raise ValueError("Qt license material must contain the LGPL terms")
        verified[key] = path, digest
    versions = pinned_gui_versions()
    source_prefixes = {
        "pyqt6_source": f"PyQt6-{versions['PyQt6']}",
        "qt_source": f"qt-everywhere-src-{versions['PyQt6-Qt6']}",
    }
    for key, prefix in source_prefixes.items():
        path = verified[key][0]
        if not path.name.startswith(prefix + "."):
            raise ValueError(f"{key} filename must bind installed version {prefix}")
        if tarfile.is_tarfile(path):
            with tarfile.open(path, "r:*") as archive:
                names = archive.getnames()
        elif zipfile.is_zipfile(path):
            with zipfile.ZipFile(path) as archive:
                names = archive.namelist()
        else:
            raise ValueError(f"{key} must be a real source archive")
        if len(names) < 25 or not all(name.startswith(prefix + "/") for name in names):
            raise ValueError(f"{key} archive must contain the pinned version's source tree")
    instructions = verified["qt_relink_instructions"][0].read_text(encoding="utf-8")
    if not all(word in instructions.lower() for word in ("qt", "relink", "replace")):
        raise ValueError("Qt relink instructions must explain replacement and relinking")
    return verified


def capture_builder_inventory(
    *, assets_dir: Path, tag: str, sha: str, repository: str, target: str
) -> dict[str, Any]:
    if target not in BUILD_TARGETS or not TAG.fullmatch(tag) or not SHA.fullmatch(sha):
        raise ValueError("builder target, tag, and SHA must identify an exact release build")
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) is None:
        raise ValueError("repository must be owner/name")
    expected = target_asset_names(tag, target)
    if not assets_dir.is_dir() or assets_dir.is_symlink():
        raise ValueError("builder asset directory is missing or a symlink")
    files = list(assets_dir.iterdir())
    if {path.name for path in files} != expected or any(not path.is_file() or path.is_symlink() for path in files):
        raise ValueError(f"{target} builder output differs from the exact native matrix")
    result = subprocess.run(
        [sys.executable, "-m", "pip", "inspect", "--local"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    if result.returncode:
        raise ValueError(f"pip inspect failed for {target}")
    inspect = json.loads(result.stdout)
    installed = inspect.get("installed")
    if not isinstance(installed, list):
        raise ValueError("pip inspect did not contain installed distributions")
    versions = {
        item["metadata"]["name"].lower().replace("_", "-"): item["metadata"]["version"]
        for item in installed
        if isinstance(item, dict) and isinstance(item.get("metadata"), dict)
        and isinstance(item["metadata"].get("name"), str)
        and isinstance(item["metadata"].get("version"), str)
    }
    required = pinned_gui_versions()
    if target.startswith("windows-") and target != "windows-x86" or target.startswith("macos-"):
        for name, version in required.items():
            if versions.get(name.lower()) != version:
                raise ValueError(f"{target} realized {name} version does not match {version}")
    return {
        "schema_version": 1,
        "repository": repository,
        "release_tag": tag,
        "release_sha": sha,
        "target": target,
        "distributions": {name: versions.get(name.lower()) for name in required},
        "assets_sha256": {path.name: file_hash(path) for path in files},
    }


def check_builder_inventories(
    inventory_dir: Path, assets_dir: Path, tag: str, sha: str, repository: str
) -> dict[str, dict[str, Any]]:
    if inventory_dir.is_symlink() or not inventory_dir.is_dir():
        raise ValueError("seven exact native builder inventories are missing")
    actual = {path.name for path in inventory_dir.iterdir()}
    expected = {f"{target}.json" for target in BUILD_TARGETS}
    if actual != expected:
        raise ValueError(f"native builder inventories must be exactly {sorted(expected)}")
    pinned = pinned_gui_versions()
    records: dict[str, dict[str, Any]] = {}
    for target in BUILD_TARGETS:
        path = inventory_dir / f"{target}.json"
        if path.is_symlink() or not path.is_file():
            raise ValueError(f"{target} builder inventory is not a regular file")
        record = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(record, dict) or any(record.get(k) != v for k, v in {
            "schema_version": 1, "repository": repository, "release_tag": tag,
            "release_sha": sha, "target": target,
        }.items()):
            raise ValueError(f"{target} builder inventory is not bound to this release")
        expected_assets = target_asset_names(tag, target)
        hashes = record.get("assets_sha256")
        if not isinstance(hashes, dict) or set(hashes) != expected_assets:
            raise ValueError(f"{target} builder inventory does not cover exact native assets")
        for name, digest in hashes.items():
            asset = assets_dir / name
            if not isinstance(digest, str) or not HEX.fullmatch(digest) or file_hash(asset) != digest:
                raise ValueError(f"{target} builder inventory digest differs from {name}")
        distributions = record.get("distributions")
        if not isinstance(distributions, dict) or set(distributions) != set(pinned):
            raise ValueError(f"{target} builder inventory lacks realized GUI distributions")
        if target.startswith("macos-") or target in {"windows-x64", "windows-arm64"}:
            if distributions != pinned:
                raise ValueError(f"{target} realized PyQt/Qt versions differ from source evidence")
        records[target] = record
    return records


def embedded_file_bytes(archive: Path, wanted: str) -> bytes | None:
    """Read a real packaged file, using 7z for non-ZIP/non-tar installers."""
    if zipfile.is_zipfile(archive):
        with zipfile.ZipFile(archive) as package:
            matches = [name for name in package.namelist() if Path(name).name == wanted]
            if len(matches) != 1:
                return None
            return package.read(matches[0])
    if tarfile.is_tarfile(archive):
        with tarfile.open(archive, "r:*") as package:
            matches = [member for member in package.getmembers() if member.isfile() and Path(member.name).name == wanted]
            if len(matches) != 1:
                return None
            stream = package.extractfile(matches[0])
            return stream.read() if stream else None
    with tempfile.TemporaryDirectory(prefix="row-license-extract-") as temp:
        destination = Path(temp)
        try:
            result = subprocess.run(
                ["7z", "x", "-y", f"-o{destination}", str(archive)],
                capture_output=True,
                text=True,
                timeout=300,
                check=False,
            )
        except (FileNotFoundError, subprocess.TimeoutExpired) as exc:
            raise ValueError(f"cannot inspect {archive.name} with 7z: {exc}") from exc
        if result.returncode != 0:
            raise ValueError(f"cannot extract {archive.name} with 7z (exit {result.returncode})")
        matches = [
            path for path in destination.rglob(wanted)
            if path.is_file() and not path.is_symlink() and path.resolve().is_relative_to(destination)
        ]
        if len(matches) != 1:
            return None
        return matches[0].read_bytes()


def audit(
    *, assets_dir: Path, evidence_dir: Path, inventory_dir: Path,
    tag: str, sha: str, repository: str
) -> dict[str, Any]:
    if not TAG.fullmatch(tag) or not SHA.fullmatch(sha):
        raise ValueError("tag and source SHA must be exact")
    if re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository) is None:
        raise ValueError("repository must be owner/name")
    materials = evidence_materials(evidence_dir, tag)
    if assets_dir.is_symlink() or not assets_dir.is_dir():
        raise ValueError("release asset directory is missing or a symlink")
    assets = sorted(assets_dir.iterdir(), key=lambda path: path.name)
    if not assets or any(not path.is_file() or path.is_symlink() for path in assets):
        raise ValueError("release assets must be a nonempty flat set of regular files")
    inventories = check_builder_inventories(inventory_dir, assets_dir, tag, sha, repository)
    packages = [path for path in assets if NATIVE_PACKAGE.fullmatch(path.name)]
    expected_packages = {name for name in expected_native_assets(tag) if NATIVE_PACKAGE.fullmatch(name)}
    if {path.name for path in packages} != expected_packages:
        raise ValueError("native package names do not match the release matrix")
    for package in packages:
        if not package.name.startswith(f"remote-ops-workspace-{tag}-"):
            raise ValueError(f"native package belongs to another version: {package.name}")
        required = ["third_party_notices"]
        if GUI_TARGET.search(package.name):
            required += ["pyqt6_gplv3", "qt_lgplv3"]
        for key in required:
            expected_name = materials[key][0].name
            embedded = embedded_file_bytes(package, expected_name)
            if embedded is None:
                raise ValueError(f"{package.name} does not contain {expected_name}")
            if hashlib.sha256(embedded).hexdigest() != materials[key][1]:
                raise ValueError(f"{package.name} contains different bytes for {expected_name}")
    return {
        "schema_version": 1,
        "kind": "unsigned-preview-redistribution-material-check",
        "legal_certification": False,
        "repository": repository,
        "release_tag": tag,
        "release_sha": sha,
        "channel": "gpl-lgpl",
        "materials_sha256": {key: digest for key, (_, digest) in sorted(materials.items())},
        "builder_inventory_sha256": {
            target: file_hash(inventory_dir / f"{target}.json") for target in inventories
        },
        "assets_sha256": {path.name: file_hash(path) for path in assets},
        "native_packages_inspected": [path.name for path in packages],
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--assets-dir", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path)
    parser.add_argument("--inventory-dir", type=Path)
    parser.add_argument("--capture-target", choices=sorted(BUILD_TARGETS))
    parser.add_argument("--preflight", action="store_true")
    parser.add_argument("--tag", required=True)
    parser.add_argument("--sha", required=True)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args(argv)
    try:
        if args.preflight:
            if args.capture_target or args.evidence_dir is None:
                raise ValueError("--preflight requires --evidence-dir and no capture target")
            materials = evidence_materials(args.evidence_dir, args.tag)
            report = {
                "schema_version": 1,
                "kind": "unsigned-preview-redistribution-source-preflight",
                "release_tag": args.tag,
                "materials_sha256": {key: digest for key, (_, digest) in sorted(materials.items())},
            }
        elif args.capture_target:
            report = capture_builder_inventory(
                assets_dir=args.assets_dir, tag=args.tag, sha=args.sha,
                repository=args.repository, target=args.capture_target,
            )
        else:
            if args.evidence_dir is None or args.inventory_dir is None:
                raise ValueError("publish audit requires --evidence-dir and --inventory-dir")
            report = audit(
                assets_dir=args.assets_dir, evidence_dir=args.evidence_dir,
                inventory_dir=args.inventory_dir, tag=args.tag, sha=args.sha,
                repository=args.repository,
            )
        args.report.parent.mkdir(parents=True, exist_ok=True)
        args.report.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, ValueError, json.JSONDecodeError, UnicodeError, zipfile.BadZipFile, tarfile.TarError) as exc:
        print(f"preview redistribution: {exc}", file=sys.stderr)
        return 1
    print("preview redistribution material and exact native artifact checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Fail closed on missing redistribution material for an unsigned native preview.

This is an artifact/evidence check, not a legal certification.  The tagged source
must contain ``redistribution-evidence/preview.json`` and the files it names.
The open-source channel requires exact PyQt6 GPLv3 and Qt LGPLv3 license texts,
version-pinned upstream source archive URLs and digests, LGPL relink instructions,
and third-party notices.
The license texts and notices must be found in every actual native package;
GUI packages must also contain the PyQt6 and Qt texts.  All downloaded release
asset hashes are recorded in the output report.

There is intentionally no self-asserted commercial bypass.  A commercial
channel needs a separately verifiable vendor grant/trust anchor first.
"""

from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import subprocess
import sys
import tarfile
import tempfile
import urllib.request
import zipfile
from importlib import metadata
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

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


def source_archive_record(path: Path, key: str) -> dict[str, str]:
    """Validate an upstream source link and its published archive digest."""
    specs = {
        "pyqt6_source": {
            "component": "PyQt6",
            "version_name": "PyQt6",
            "filename": "pyqt6-{version}.tar.gz",
            "host": "files.pythonhosted.org",
            "path_suffix": "/pyqt6-{version}.tar.gz",
            "checksum_host": "pypi.org",
            "checksum_path": "/pypi/PyQt6/{version}/json",
        },
        "qt_source": {
            "component": "Qt",
            "version_name": "PyQt6-Qt6",
            "filename": "qt-everywhere-src-{version}.tar.xz",
            "host": "download.qt.io",
            "path_suffix": "/official_releases/qt/{major}.{minor}/{version}/single/qt-everywhere-src-{version}.tar.xz",
            "checksum_host": "download.qt.io",
            "checksum_path": "/official_releases/qt/{major}.{minor}/{version}/single/qt-everywhere-src-{version}.tar.xz.mirrorlist",
        },
    }
    spec = specs.get(key)
    if spec is None:
        raise ValueError(f"{key} is not a recognized source archive record")
    record = json.loads(path.read_text(encoding="utf-8"))
    required_fields = {
        "schema_version", "component", "version", "filename", "url",
        "sha256", "upstream_checksum_page",
    }
    if not isinstance(record, dict) or set(record) != required_fields or record.get("schema_version") != 1:
        raise ValueError(f"{key} source record has an invalid schema")
    versions = pinned_gui_versions()
    version = versions[spec["version_name"]]
    filename = spec["filename"].format(version=version)
    expected_path = spec["path_suffix"].format(
        version=version,
        major=version.split(".")[0],
        minor=version.split(".")[1],
    )
    url = record.get("url")
    parsed = urlsplit(url) if isinstance(url, str) else None
    if parsed is None:
        raise ValueError(f"{key} source URL must be the pinned official upstream archive")
    path_matches = (
        re.fullmatch(
            rf"/packages/[0-9a-f]{{2}}/[0-9a-f]{{2}}/[0-9a-f]{{60}}/{re.escape(filename)}",
            parsed.path,
        ) is not None
        if key == "pyqt6_source"
        else parsed.path == expected_path
    )
    if record.get("component") != spec["component"] or record.get("version") != version:
        raise ValueError(f"{key} source record does not match pinned {spec['component']} {version}")
    if record.get("filename") != filename:
        raise ValueError(f"{key} source filename must be {filename}")
    digest = record.get("sha256")
    if not isinstance(digest, str) or not HEX.fullmatch(digest):
        raise ValueError(f"{key} source archive sha256 must be lowercase SHA-256")
    if (
        parsed.scheme != "https" or parsed.hostname != spec["host"]
        or not path_matches or parsed.username is not None
        or parsed.password is not None or parsed.port is not None
        or parsed.query or parsed.fragment
    ):
        raise ValueError(f"{key} source URL must be the pinned official upstream archive")
    checksum_page = record.get("upstream_checksum_page")
    checksum_parsed = urlsplit(checksum_page) if isinstance(checksum_page, str) else None
    expected_checksum_path = spec["checksum_path"].format(
        version=version,
        major=version.split(".")[0],
        minor=version.split(".")[1],
    )
    if (
        checksum_parsed is None or checksum_parsed.scheme != "https"
        or checksum_parsed.hostname != spec["checksum_host"]
        or checksum_parsed.path != expected_checksum_path
        or checksum_parsed.username is not None or checksum_parsed.password is not None
        or checksum_parsed.port is not None or checksum_parsed.query or checksum_parsed.fragment
    ):
        raise ValueError(f"{key} checksum page must be hosted by the upstream project")
    upstream_digest = fetch_upstream_checksum(key, checksum_page, filename)
    if digest != upstream_digest:
        raise ValueError(f"{key} sha256 does not match the official upstream checksum")
    return {
        "component": spec["component"],
        "version": version,
        "filename": filename,
        "url": url,
        "sha256": digest,
        "upstream_checksum_page": checksum_page,
    }


_UPSTREAM_CHECKSUM_CACHE: dict[tuple[str, str, str], str] = {}


def parse_upstream_checksum(payload: bytes, key: str, filename: str) -> str:
    """Extract one archive SHA-256 from PyPI JSON or a Qt mirror list page."""
    if key == "pyqt6_source":
        try:
            metadata = json.loads(payload)
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise ValueError("PyPI checksum metadata is not valid JSON") from exc
        files = metadata.get("urls") if isinstance(metadata, dict) else None
        matches: list[Any] = []
        if isinstance(files, list):
            for item in files:
                if (
                    not isinstance(item, dict)
                    or item.get("filename") != filename
                    or item.get("packagetype") != "sdist"
                ):
                    continue
                digests = item.get("digests")
                matches.append(digests.get("sha256") if isinstance(digests, dict) else None)
    elif key == "qt_source":
        try:
            page = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise ValueError("Qt checksum metadata is not UTF-8") from exc
        if filename not in page:
            raise ValueError("Qt checksum metadata does not name the pinned archive")
        plain = html.unescape(re.sub(r"<[^>]*>", " ", page))
        matches = re.findall(
            r"SHA-256(?:\s+Hash)?\s*:?\s*([0-9a-f]{64})",
            plain,
            flags=re.IGNORECASE,
        )
    else:
        raise ValueError(f"{key} has no recognized upstream checksum format")
    digests = {value.lower() for value in matches if isinstance(value, str) and HEX.fullmatch(value.lower())}
    if len(digests) != 1:
        raise ValueError(f"upstream checksum metadata must contain one SHA-256 for {filename}")
    return digests.pop()


def fetch_upstream_checksum(key: str, url: str, filename: str) -> str:
    """Fetch a small official checksum document without downloading the source archive."""
    cache_key = (key, url, filename)
    cached = _UPSTREAM_CHECKSUM_CACHE.get(cache_key)
    if cached is not None:
        return cached
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "remote-ops-workspace-release-check/1.0"},
    )
    with urllib.request.urlopen(request, timeout=30) as response:
        final_url = urlsplit(response.geturl())
        if response.status != 200 or final_url.scheme != "https" or final_url.hostname != urlsplit(url).hostname:
            raise ValueError("upstream checksum request left its pinned HTTPS host")
        payload = response.read(2_000_001)
    if len(payload) > 2_000_000:
        raise ValueError("upstream checksum metadata exceeds the size limit")
    digest = parse_upstream_checksum(payload, key, filename)
    _UPSTREAM_CHECKSUM_CACHE[cache_key] = digest
    return digest


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
        minimum_size = (
            10_000 if key == "pyqt6_gplv3"
            else 5_000 if key == "qt_lgplv3"
            else 100 if key in {"pyqt6_source", "qt_source"}
            else 500
        )
        if path.stat().st_size < minimum_size:
            raise ValueError(f"{key} evidence is too small to establish its claimed material")
        if key == "pyqt6_gplv3" and "GNU GENERAL PUBLIC LICENSE" not in path.read_text(encoding="utf-8"):
            raise ValueError("PyQt6 license material must contain the GPL terms")
        if key == "qt_lgplv3" and "GNU LESSER GENERAL PUBLIC LICENSE" not in path.read_text(encoding="utf-8"):
            raise ValueError("Qt license material must contain the LGPL terms")
        verified[key] = path, digest
    for key in ("pyqt6_source", "qt_source"):
        source_archive_record(verified[key][0], key)
    instructions = verified["qt_relink_instructions"][0].read_text(encoding="utf-8")
    if not all(word in instructions.lower() for word in ("qt", "relink", "replace")):
        raise ValueError("Qt relink instructions must explain replacement and relinking")
    return verified


def source_archive_records(materials: dict[str, tuple[Path, str]]) -> dict[str, dict[str, str]]:
    return {
        key: source_archive_record(materials[key][0], key)
        for key in ("pyqt6_source", "qt_source")
    }


def installed_distribution_versions() -> dict[str, str]:
    """Read installed package names and versions directly from dist-info metadata."""
    versions: dict[str, str] = {}
    for distribution in metadata.distributions():
        name = distribution.metadata.get("Name")
        version = distribution.version
        if not isinstance(name, str) or not name.strip() or not isinstance(version, str) or not version.strip():
            continue
        normalized = re.sub(r"[-_.]+", "-", name).lower()
        previous = versions.get(normalized)
        if previous is not None and previous != version:
            raise ValueError(f"conflicting installed versions for {normalized}")
        versions[normalized] = version
    if not versions:
        raise ValueError("Python distribution metadata did not contain installed packages")
    return versions


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
    versions = installed_distribution_versions()
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
        "distribution_inventory_source": "importlib.metadata",
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
        if record.get("distribution_inventory_source") != "importlib.metadata":
            raise ValueError(f"{target} builder inventory has an unsupported package metadata source")
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
            required += ["pyqt6_gplv3", "qt_lgplv3", "qt_relink_instructions"]
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
        "source_archives": source_archive_records(materials),
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
                "source_archives": source_archive_records(materials),
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

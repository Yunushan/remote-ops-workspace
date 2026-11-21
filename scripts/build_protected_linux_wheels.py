"""Compile the protected Linux source inputs and record the resulting wheel digests."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tarfile
from pathlib import Path

from check_release_license_compliance import (
    PROTECTED_LINUX_LOCK_DIR,
    ROOT,
    read_hashed_lock_entries,
)
from prepare_protected_linux_cargo import (
    SOURCE_DISTRIBUTIONS,
    download_locked_source,
    extract_locked_source,
    locked_source,
)

SOURCE_WHEEL_COMPONENTS = {
    "linux-i386": tuple(SOURCE_DISTRIBUTIONS),
    "linux-armhf": ("cffi",),
}
WHEEL_PLATFORM = {
    "linux-i386": r"linux_(?:i[3-6]86|x86)",
    "linux-armhf": r"linux_(?:armv[6-8]l|armhf)",
}


def write_lock(path: Path, entries: dict[str, tuple[str, set[str]]]) -> None:
    lines = [
        f"{name}=={version} " + " ".join(f"--hash=sha256:{digest}" for digest in sorted(hashes))
        for name, (version, hashes) in sorted(entries.items())
    ]
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def pip(*arguments: str | Path) -> None:
    subprocess.run([sys.executable, "-m", "pip", *arguments], check=True, timeout=600)


def read_runtime_lock(root: Path, target: str) -> dict[str, tuple[str, set[str]]]:
    lock, errors = read_hashed_lock_entries(
        root, {"file": f"{PROTECTED_LINUX_LOCK_DIR}/{target}.txt"}, f"{target} lock",
    )
    if errors:
        raise ValueError("\n".join(errors))
    return lock


def unique_json_fields(fields: list[tuple[str, object]]) -> dict[str, object]:
    values = dict(fields)
    if len(values) != len(fields):
        raise ValueError("inventory contains duplicate JSON fields")
    return values


def inventory_schema(target: str) -> str:
    return f"row.protected-{target.removeprefix('linux-')}-built-wheels.v1"


def validate_source_wheel_inventory(raw: str, target: str, *, lock_root: Path | None = None) -> None:
    if not 0 < len(raw) <= 8192:
        raise ValueError("inventory must have a positive, bounded size")
    inventory = json.loads(raw, object_pairs_hook=unique_json_fields)
    if (
        not isinstance(inventory, dict) or set(inventory) != {"schema", "components"}
        or inventory["schema"] != inventory_schema(target)
        or not isinstance(inventory["components"], dict)
        or set(inventory["components"]) != set(SOURCE_WHEEL_COMPONENTS[target])
    ):
        raise ValueError(f"inventory must describe the exact {target} source wheel components")

    lock = read_runtime_lock(lock_root, target) if lock_root is not None else None
    for name, component in inventory["components"].items():
        if (
            not isinstance(component, dict)
            or set(component) != {"source", "source_sha256", "wheel", "wheel_sha256"}
            or not all(isinstance(value, str) for value in component.values())
            or not all(re.fullmatch(r"[0-9a-f]{64}", component[key]) for key in ("source_sha256", "wheel_sha256"))
        ):
            raise ValueError(f"{name} inventory entry must contain source and wheel names and SHA-256 digests")
        source = re.fullmatch(rf"{name}-([0-9][A-Za-z0-9.!+_-]*)\.tar\.gz", component["source"])
        if source is None or not re.fullmatch(
            rf"{name}-{re.escape(source[1])}-[a-z0-9_]+-[a-z0-9_]+-{WHEEL_PLATFORM[target]}\.whl",
            component["wheel"],
        ):
            raise ValueError(f"{name} source and {target} wheel filenames must match the same version")
        if lock is not None and (component["source"], component["source_sha256"]) != locked_source(lock, name):
            raise ValueError(f"{name} source filename and SHA-256 must match the exact {target.removeprefix('linux-')} lock")


def build_wheels(root: Path, workspace: Path, inventory: Path, target: str) -> None:
    lock = read_runtime_lock(root, target)

    sources = workspace / "dependency-sources"
    wheels = workspace / "generated-wheels"
    archives = workspace / "source-archives"
    sources.mkdir()
    wheels.mkdir()
    archives.mkdir(exist_ok=True)

    # CFFI and the native cryptography build use the pinned parser.
    parser_lock = workspace / "cffi-build-prerequisite.txt"
    write_lock(parser_lock, {"pycparser": lock["pycparser"]})
    pip("install", "--require-hashes", "--only-binary=:all:", "--no-deps", "--requirement", parser_lock)

    bindings = {}
    for name in SOURCE_WHEEL_COMPONENTS[target]:
        filename, source_digest = locked_source(lock, name)
        archive = archives / filename
        if target == "linux-armhf" and not archive.exists():
            archive.write_bytes(download_locked_source(SOURCE_DISTRIBUTIONS[name][0], source_digest))
        source = extract_locked_source(archive, source_digest, sources)
        pip("wheel", "--no-index", "--no-deps", "--no-build-isolation", "--no-cache-dir", "--wheel-dir", wheels, source)
        version, _ = lock[name]
        (wheel,) = wheels.glob(f"{name}-{version}-*.whl")
        with wheel.open("rb") as stream:
            wheel_digest = hashlib.file_digest(stream, "sha256").hexdigest()
        wheel_lock = workspace / f"{name}-generated-wheel.txt"
        write_lock(wheel_lock, {name: (version, {wheel_digest})})
        pip("install", "--no-index", "--find-links", wheels, "--only-binary=:all:", "--no-deps",
            "--require-hashes", "--requirement", wheel_lock)
        bindings[name] = {
            "source": filename,
            "source_sha256": source_digest,
            "wheel": wheel.name,
            "wheel_sha256": wheel_digest,
        }

    write_lock(workspace / "remaining-requirements.txt", {
        name: entry for name, entry in lock.items() if name not in bindings
    })
    with inventory.open("x", encoding="utf-8") as stream:
        json.dump({"schema": inventory_schema(target), "components": bindings}, stream, indent=2)
        stream.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=SOURCE_WHEEL_COMPONENTS, required=True)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    args = parser.parse_args()
    try:
        build_wheels(ROOT, args.workspace, args.inventory, args.target)
    except (KeyError, OSError, ValueError, tarfile.TarError, subprocess.SubprocessError) as exc:
        print(f"protected {args.target} wheels: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

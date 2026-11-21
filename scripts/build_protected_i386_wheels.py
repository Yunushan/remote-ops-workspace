"""Compile the protected i386 source inputs and record the resulting wheel digests."""

from __future__ import annotations

import argparse
import hashlib
import json
import subprocess
import sys
import tarfile
from pathlib import Path

from check_release_license_compliance import (
    PROTECTED_LINUX_LOCK_DIR,
    ROOT,
    read_hashed_lock_entries,
)
from prepare_protected_linux_cargo import SOURCE_DISTRIBUTIONS, extract_locked_source, locked_source


def write_lock(path: Path, entries: dict[str, tuple[str, set[str]]]) -> None:
    lines = [
        f"{name}=={version} " + " ".join(f"--hash=sha256:{digest}" for digest in sorted(hashes))
        for name, (version, hashes) in sorted(entries.items())
    ]
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def pip(*arguments: str | Path) -> None:
    subprocess.run([sys.executable, "-m", "pip", *arguments], check=True, timeout=600)


def build_wheels(root: Path, workspace: Path, inventory: Path) -> None:
    lock, errors = read_hashed_lock_entries(
        root, {"file": f"{PROTECTED_LINUX_LOCK_DIR}/linux-i386.txt"}, "Linux i386 lock",
    )
    if errors:
        raise ValueError("\n".join(errors))

    sources = workspace / "dependency-sources"
    wheels = workspace / "generated-wheels"
    sources.mkdir()
    wheels.mkdir()

    # Cryptography's native build imports CFFI and its pinned parser.
    parser_lock = workspace / "cffi-build-prerequisite.txt"
    write_lock(parser_lock, {"pycparser": lock["pycparser"]})
    pip("install", "--require-hashes", "--only-binary=:all:", "--no-deps", "--requirement", parser_lock)

    bindings = {}
    for name in SOURCE_DISTRIBUTIONS:
        filename, source_digest = locked_source(lock, name)
        source = extract_locked_source(workspace / "source-archives" / filename, source_digest, sources)
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

    write_lock(workspace / "remaining-i386-requirements.txt", {
        name: entry for name, entry in lock.items() if name not in bindings
    })
    with inventory.open("x", encoding="utf-8") as stream:
        json.dump({"schema": "row.protected-i386-built-wheels.v1", "components": bindings}, stream, indent=2)
        stream.write("\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", required=True, type=Path)
    parser.add_argument("--inventory", required=True, type=Path)
    args = parser.parse_args()
    try:
        build_wheels(ROOT, args.workspace, args.inventory)
    except (KeyError, OSError, ValueError, tarfile.TarError, subprocess.SubprocessError) as exc:
        print(f"protected i386 wheels: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

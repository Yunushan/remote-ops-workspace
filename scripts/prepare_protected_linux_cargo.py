"""Fetch locked Rust dependencies for the protected Linux i386 build."""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import tarfile
import tempfile
import tomllib
import urllib.request
from pathlib import Path

from check_release_license_compliance import (
    PROTECTED_LINUX_LOCK_DIR,
    ROOT,
    read_hashed_lock_entries,
)

RUST_TARGET = "i686-unknown-linux-gnu"
MAX_SOURCE_BYTES = 16 * 1024 * 1024
SOURCE_DISTRIBUTIONS = {
    "bcrypt": (
        "https://files.pythonhosted.org/packages/d4/36/3329e2518d70ad8e2e5817d5a4cac6bba05a47767ec416c7d020a965f408/bcrypt-5.0.0.tar.gz",
        "src/_bcrypt",
    ),
    "cryptography": (
        "https://files.pythonhosted.org/packages/9d/af/182eb91b0df3fe75c4d9f26fe70684569566745f6ba7e5c9c73a862c5252/cryptography-50.0.2.tar.gz",
        ".",
    ),
}


def download_locked_source(url: str, digest: str) -> bytes:
    with urllib.request.urlopen(url, timeout=45) as response:
        if response.geturl() != url:
            raise ValueError(f"unexpected redirect for {url}")
        data = response.read(MAX_SOURCE_BYTES + 1)
    if not 0 < len(data) <= MAX_SOURCE_BYTES or hashlib.sha256(data).hexdigest() != digest:
        raise ValueError(f"source archive size or SHA-256 is invalid for {url}")
    return data


def fetch_locked_crates(manifest: Path, environment: dict[str, str]) -> None:
    cargo_lock = manifest.with_name("Cargo.lock")
    if not manifest.is_file() or not cargo_lock.is_file():
        raise ValueError(f"source archive must contain {manifest.name} and {cargo_lock.name}")
    lock_bytes = cargo_lock.read_bytes()
    packages = tomllib.loads(lock_bytes.decode("utf-8"))["package"]
    for package in packages:
        if "source" not in package:
            continue
        checksum = package.get("checksum", "")
        if (
            package["source"] != "registry+https://github.com/rust-lang/crates.io-index"
            or len(checksum) != 64 or any(char not in "0123456789abcdef" for char in checksum)
        ):
            raise ValueError(f"Cargo package {package['name']} must have a crates.io SHA-256 checksum")
    for mode in ("--locked", "--frozen"):
        subprocess.run(
            ["cargo", "fetch", mode, "--manifest-path", str(manifest)],
            cwd=manifest.parent, env=environment, check=True, timeout=300,
        )
        if cargo_lock.read_bytes() != lock_bytes:
            raise ValueError(f"Cargo modified the pinned lockfile beside {manifest}")


def prepare_cargo(root: Path) -> None:
    cargo_home = os.environ.get("CARGO_HOME")
    if not cargo_home:
        raise ValueError("set CARGO_HOME to a new job-local directory before fetching crates")
    cargo_dir = Path(cargo_home)
    if not cargo_dir.is_absolute() or cargo_dir.is_symlink() or not cargo_dir.is_dir() or any(cargo_dir.iterdir()):
        raise ValueError("CARGO_HOME must be an absolute, empty job-local directory")
    rust = subprocess.check_output(["rustc", "-vV"], text=True, timeout=30)
    if f"host: {RUST_TARGET}" not in rust.splitlines():
        raise ValueError(f"the protected i386 build needs a native Rust toolchain for {RUST_TARGET}")

    lock, errors = read_hashed_lock_entries(
        root, {"file": f"{PROTECTED_LINUX_LOCK_DIR}/linux-i386.txt"}, "Linux i386 lock",
    )
    if errors:
        raise ValueError("\n".join(errors))
    environment = {**os.environ, "CARGO_NET_OFFLINE": "false"}
    with tempfile.TemporaryDirectory(prefix="row-protected-linux-cargo-") as temporary:
        temp_dir = Path(temporary)
        for name, (url, manifest_directory) in SOURCE_DISTRIBUTIONS.items():
            version, hashes = lock[name]
            source_name = f"{name}-{version}"
            filename = f"{source_name}.tar.gz"
            if not url.endswith(f"/{filename}") or len(hashes) != 1:
                raise ValueError(f"{name} source URL must match its single i386 lock hash and version")
            source = temp_dir / filename
            source.write_bytes(download_locked_source(url, next(iter(hashes))))
            with tarfile.open(source, mode="r:gz") as archive:
                archive.extractall(temp_dir, filter="data")
            manifest = temp_dir / source_name / manifest_directory / "Cargo.toml"
            fetch_locked_crates(manifest, environment)
            print(f"Fetched the pinned Cargo dependencies for {source_name}")


def main() -> int:
    try:
        prepare_cargo(ROOT)
    except (KeyError, OSError, ValueError, tarfile.TarError, subprocess.SubprocessError) as exc:
        print(f"protected Linux Cargo inputs: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

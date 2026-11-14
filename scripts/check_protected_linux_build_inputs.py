"""Check the pinned CPython and hash-locked inputs for protected Linux builds."""

from __future__ import annotations

import argparse
import json
import platform
import sys
from pathlib import Path

from check_release_license_compliance import (
    PROTECTED_LINUX_CFFI_LOCK,
    PROTECTED_LINUX_LOCK_DIR,
    ROOT,
    TOOLCHAIN_PATH,
    check_bootstrap_lock_subset,
    normalize_component_name,
    read_hashed_lock_entries,
)

TARGETS = ("linux-i386", "linux-armhf")


def check_lock_inputs(root: Path, target: str, toolchain: dict) -> list[str]:
    final_lock = f"{PROTECTED_LINUX_LOCK_DIR}/{target}.txt"
    entries, errors = read_hashed_lock_entries(root, {"file": final_lock}, target)
    for bootstrap_lock in (f"{PROTECTED_LINUX_LOCK_DIR}/{target}-bootstrap.txt", PROTECTED_LINUX_CFFI_LOCK):
        errors.extend(check_bootstrap_lock_subset(root, final_lock, bootstrap_lock))
    required = {
        "pip", "setuptools", "wheel", "build", "pyinstaller", "bcrypt", "cryptography", "cffi",
        "pycparser", "truststore", "pyftpdlib", "pyopenssl", "pyasyncore", "pyasynchat",
    }
    required.update({"maturin", "setuptools-rust"} if target == "linux-i386" else {"hatchling"})
    missing = required - entries.keys()
    if missing:
        errors.append(f"{target} lock is missing required packages: {', '.join(sorted(missing))}")
    for package in toolchain["python_packages"]:
        name = normalize_component_name(package["name"])
        if name in entries and entries[name][0] != package["version"]:
            errors.append(f"{target} lock must use the release pin {name}=={package['version']}")
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", required=True, choices=TARGETS)
    args = parser.parse_args()
    target = args.target
    try:
        toolchain = json.loads(TOOLCHAIN_PATH.read_bytes())
        expected_python = toolchain["python"]["version"]
        actual_python = platform.python_version()
        if platform.python_implementation() != "CPython" or actual_python != expected_python:
            raise ValueError(f"{target} needs CPython {expected_python}, got {platform.python_implementation()} {actual_python}")
        errors = check_lock_inputs(ROOT, target, toolchain)
        if errors:
            raise ValueError("\n".join(errors))
    except (OSError, KeyError, ValueError) as exc:
        print(f"protected Linux build inputs: {exc}", file=sys.stderr)
        return 1
    print(f"{target} dependency locks and CPython {actual_python} passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

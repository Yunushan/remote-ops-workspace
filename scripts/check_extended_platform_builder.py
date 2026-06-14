from __future__ import annotations

import argparse
import json
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

LINUX_TARGET_ARCHES = {
    "linux-i386": {"i386", "i486", "i586", "i686", "x86"},
    "linux-armhf": {"armv6l", "armv7l", "armv7hl", "armhf"},
}

REQUIRED_LINUX_TOOLS = (
    "bash",
    "curl",
    "dpkg-deb",
    "rpmbuild",
    "sha256sum",
    "sudo",
    "tar",
)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    errors = check_extended_platform_builder(args.target)
    if errors:
        for error in errors:
            print(f"extended platform builder: {error}", file=sys.stderr)
        return 1
    if args.out:
        args.out.parent.mkdir(parents=True, exist_ok=True)
        args.out.write_text(json.dumps(builder_identity(args.target), indent=2) + "\n", encoding="utf-8")
    print(f"extended platform builder checks passed for {args.target}")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Validate an extended-platform native builder.")
    parser.add_argument("--target", choices=sorted(LINUX_TARGET_ARCHES), required=True)
    parser.add_argument("--out", type=Path, help="write builder identity evidence JSON after validation passes")
    return parser.parse_args(argv)


def check_extended_platform_builder(target: str) -> list[str]:
    errors: list[str] = []
    if not sys.platform.startswith("linux"):
        errors.append(f"{target} builder must run on Linux, got {sys.platform}")
    machine = normalized_machine()
    expected = LINUX_TARGET_ARCHES[target]
    if machine not in expected:
        errors.append(f"{target} builder architecture must be one of {sorted(expected)}, got {machine}")
    for tool in REQUIRED_LINUX_TOOLS:
        if shutil.which(tool) is None:
            errors.append(f"{target} builder missing required tool: {tool}")
    python_version = sys.version_info
    if python_version < (3, 10):
        errors.append(
            f"{target} builder Python must be 3.10 or newer, got "
            f"{python_version.major}.{python_version.minor}"
        )
    if shutil.which("python3") is None:
        errors.append(f"{target} builder missing python3 command")
    errors.extend(check_uname_machine(target, expected))
    return errors


def builder_identity(target: str) -> dict[str, Any]:
    version = sys.version_info
    major = version.major if hasattr(version, "major") else version[0]
    minor = version.minor if hasattr(version, "minor") else version[1]
    micro = version.micro if hasattr(version, "micro") else version[2]
    return {
        "schema_version": 1,
        "target": target,
        "sys_platform": sys.platform,
        "platform_machine": normalized_machine(),
        "uname_machine": uname_machine(),
        "python_version": f"{major}.{minor}.{micro}",
        "required_tools": {tool: shutil.which(tool) or "" for tool in REQUIRED_LINUX_TOOLS},
    }


def check_uname_machine(target: str, expected: set[str]) -> list[str]:
    output = uname_machine()
    if not output:
        return [f"{target} builder cannot run uname -m"]
    machine = output.lower()
    if machine not in expected:
        return [f"{target} uname -m must be one of {sorted(expected)}, got {machine}"]
    return []


def uname_machine() -> str:
    try:
        output = subprocess.run(
            ["uname", "-m"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""
    return output.lower()


def normalized_machine() -> str:
    return platform.machine().lower()


if __name__ == "__main__":
    raise SystemExit(main())

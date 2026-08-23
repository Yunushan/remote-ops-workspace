from __future__ import annotations

import argparse
import importlib.metadata
import json
import os
import platform
import struct
import sys
import sysconfig
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

EVIDENCE_SCHEMA = "row.python-runtime-evidence.v1"
EVIDENCE_DISTRIBUTIONS = (
    "build",
    "cryptography",
    "mypy",
    "pip",
    "pyinstaller",
    "pytest",
    "pytest-cov",
    "PyQt6",
    "PyQt6-Qt6",
    "PyQt6-sip",
    "remote-ops-workspace",
    "ruff",
    "setuptools",
    "truststore",
    "wheel",
)
REQUIRED_DISTRIBUTIONS = (
    "build",
    "cryptography",
    "mypy",
    "pyinstaller",
    "pytest",
    "pytest-cov",
    "PyQt6",
    "remote-ops-workspace",
    "ruff",
    "truststore",
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Write exact, machine-readable Python runtime and dependency evidence."
    )
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument(
        "--expected-version",
        required=True,
        help="Required major.minor interpreter line, for example 3.15.",
    )
    parser.add_argument(
        "--require-standard-gil",
        action="store_true",
        help="Require standard GIL-enabled CPython rather than a free-threaded build.",
    )
    parser.add_argument(
        "--require-final",
        action="store_true",
        help="Require an upstream final interpreter. Do not use this before Python 3.15 GA.",
    )
    return parser.parse_args(argv)


def gil_state() -> tuple[bool, bool]:
    disabled_config = bool(sysconfig.get_config_var("Py_GIL_DISABLED") or 0)
    probe = getattr(sys, "_is_gil_enabled", None)
    enabled = bool(probe()) if callable(probe) else not disabled_config
    return enabled, disabled_config


def distribution_versions() -> dict[str, str | None]:
    versions: dict[str, str | None] = {}
    for name in EVIDENCE_DISTRIBUTIONS:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = None
    return versions


def collect_runtime_evidence() -> dict[str, Any]:
    gil_enabled, gil_disabled_config = gil_state()
    github = {
        key.lower(): os.environ.get(f"GITHUB_{key}")
        for key in (
            "ACTION",
            "JOB",
            "REF",
            "REPOSITORY",
            "RUN_ATTEMPT",
            "RUN_ID",
            "SHA",
            "WORKFLOW",
        )
        if os.environ.get(f"GITHUB_{key}")
    }
    return {
        "schema": EVIDENCE_SCHEMA,
        "captured_at_utc": datetime.now(timezone.utc).isoformat(),
        "python": {
            "version": platform.python_version(),
            "version_info": {
                "major": sys.version_info.major,
                "minor": sys.version_info.minor,
                "micro": sys.version_info.micro,
                "releaselevel": sys.version_info.releaselevel,
                "serial": sys.version_info.serial,
            },
            "implementation": platform.python_implementation(),
            "implementation_version": platform.python_version(),
            "cache_tag": sys.implementation.cache_tag,
            "hexversion": sys.hexversion,
            "executable": sys.executable,
            "gil_enabled": gil_enabled,
            "gil_disabled_config": gil_disabled_config,
        },
        "host": {
            "platform": platform.platform(),
            "system": platform.system(),
            "release": platform.release(),
            "machine": platform.machine(),
            "architecture": platform.architecture()[0],
            "pointer_bits": struct.calcsize("P") * 8,
        },
        "distributions": distribution_versions(),
        "github": github,
    }


def validate_runtime_evidence(
    evidence: dict[str, Any],
    *,
    expected_version: str,
    require_standard_gil: bool,
    require_final: bool,
) -> list[str]:
    errors: list[str] = []
    try:
        expected_major, expected_minor = (int(value) for value in expected_version.split("."))
    except (TypeError, ValueError):
        return [f"expected version must be major.minor, got {expected_version!r}"]

    python = evidence.get("python", {})
    version_info = python.get("version_info", {})
    actual = (version_info.get("major"), version_info.get("minor"))
    if actual != (expected_major, expected_minor):
        errors.append(
            f"resolved interpreter is {actual[0]}.{actual[1]}, expected {expected_version}"
        )
    if require_standard_gil:
        if python.get("implementation") != "CPython":
            errors.append("standard runtime evidence requires CPython")
        if python.get("gil_disabled_config") is not False:
            errors.append("standard runtime evidence rejects a free-threaded CPython build")
        if python.get("gil_enabled") is not True:
            errors.append("standard runtime evidence requires the GIL to be enabled")
    if require_final and version_info.get("releaselevel") != "final":
        errors.append(
            "final-GA certification requires releaselevel=final, got "
            f"{version_info.get('releaselevel')!r}"
        )

    distributions = evidence.get("distributions", {})
    missing = sorted(name for name in REQUIRED_DISTRIBUTIONS if not distributions.get(name))
    if missing:
        errors.append(f"required Python distributions are missing: {', '.join(missing)}")
    return errors


def write_evidence(path: Path, evidence: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(evidence, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    evidence = collect_runtime_evidence()
    errors = validate_runtime_evidence(
        evidence,
        expected_version=args.expected_version,
        require_standard_gil=args.require_standard_gil,
        require_final=args.require_final,
    )
    evidence["validation"] = {
        "expected_version": args.expected_version,
        "require_standard_gil": args.require_standard_gil,
        "require_final": args.require_final,
        "passed": not errors,
        "errors": errors,
    }
    write_evidence(args.out, evidence)
    if errors:
        for error in errors:
            print(f"Python runtime evidence: {error}", file=sys.stderr)
        return 1
    version = evidence["python"]["version"]
    releaselevel = evidence["python"]["version_info"]["releaselevel"]
    print(f"Python runtime evidence passed: {version} ({releaselevel}) -> {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

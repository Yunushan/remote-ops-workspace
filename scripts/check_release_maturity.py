#!/usr/bin/env python3
"""Reject production certification while package metadata is pre-production."""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 compatibility (tomllib landed in 3.11).
    import tomli as tomllib  # type: ignore[no-redef]

ROOT = Path(__file__).resolve().parents[1]
PYPROJECT = ROOT / "pyproject.toml"
PRODUCTION_CLASSIFIER = "Development Status :: 5 - Production/Stable"
PREPRODUCTION_CLASSIFIERS = {
    "Development Status :: 1 - Planning",
    "Development Status :: 2 - Pre-Alpha",
    "Development Status :: 3 - Alpha",
    "Development Status :: 4 - Beta",
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release-tag", required=True)
    args = parser.parse_args(argv)
    try:
        errors = check_maturity(PYPROJECT.read_text(encoding="utf-8"), args.release_tag)
    except OSError as exc:
        errors = [f"cannot read pyproject.toml: {exc}"]
    if errors:
        for error in errors:
            print(f"release maturity: {error}", file=sys.stderr)
        return 1
    print("release maturity passed: package metadata is Production/Stable")
    return 0


def check_maturity(pyproject: str, release_tag: str) -> list[str]:
    errors: list[str] = []
    if re.fullmatch(r"v\d+\.\d+\.\d+", release_tag) is None:
        errors.append("release tag must look like vX.Y.Z")
    try:
        payload = tomllib.loads(pyproject)
    except tomllib.TOMLDecodeError as exc:
        return [*errors, f"pyproject.toml is not valid TOML: {exc}"]
    project = payload.get("project")
    if not isinstance(project, dict):
        return [*errors, "pyproject.toml must contain a [project] table"]
    version = project.get("version")
    if not isinstance(version, str) or not version:
        errors.append("pyproject.toml must declare project.version")
    elif release_tag != f"v{version}":
        errors.append(
            f"release tag {release_tag!r} must match project version v{version}"
        )
    raw_classifiers = project.get("classifiers")
    if not isinstance(raw_classifiers, list) or not all(
        isinstance(item, str) for item in raw_classifiers
    ):
        errors.append("pyproject.toml project.classifiers must be a string list")
        classifiers: set[str] = set()
    else:
        classifiers = {
            item for item in raw_classifiers if item.startswith("Development Status :: ")
        }
    if PRODUCTION_CLASSIFIER not in classifiers:
        errors.append(
            "pyproject.toml must declare Development Status :: 5 - Production/Stable "
            "before production certification"
        )
    stale = sorted(classifiers & PREPRODUCTION_CLASSIFIERS)
    if stale:
        errors.append(f"pyproject.toml retains pre-production classifiers: {stale}")
    return errors


if __name__ == "__main__":
    raise SystemExit(main())

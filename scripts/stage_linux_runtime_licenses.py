#!/usr/bin/env python3
"""Stage the frozen Linux runtime licenses and define their package paths."""

from __future__ import annotations

import argparse
from pathlib import Path, PurePosixPath

if __package__:
    from .stage_runtime_licenses import FROZEN_DISTRIBUTIONS, LICENSE_PATH_PART, stage
else:
    from stage_runtime_licenses import FROZEN_DISTRIBUTIONS, LICENSE_PATH_PART, stage

LICENSE_ROOT = PurePosixPath("usr/share/doc/remote-ops-workspace/licenses")
LICENSE_COMPONENTS = {"cpython", *FROZEN_DISTRIBUTIONS}


def is_runtime_license_member(path: PurePosixPath, *, directory: bool = False) -> bool:
    if path.anchor == "/":
        path = path.relative_to("/")
    if path == LICENSE_ROOT:
        return directory
    if not path.is_relative_to(LICENSE_ROOT):
        return False
    component, *relative = path.relative_to(LICENSE_ROOT).parts
    return (
        component in LICENSE_COMPONENTS
        and (directory or bool(relative))
        and all(LICENSE_PATH_PART.fullmatch(part) for part in relative)
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("destination", type=Path)
    stage(parser.parse_args().destination)

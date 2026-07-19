from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10 compatibility for the repository test matrix.
    tomllib = None  # type: ignore[assignment]

ROOT = Path(__file__).resolve().parents[1]
VERSION_RE = re.compile(r"^\d+\.\d+\.\d+(?:a\d+|b\d+|rc\d+|\.post\d+)?$")
PROJECT_TABLE_RE = re.compile(
    r"(?ms)^\[project\][ \t]*(?:#.*)?\n(?P<body>.*?)(?=^\[|\Z)"
)
PROJECT_VERSION_RE = re.compile(
    r'''(?m)^version\s*=\s*["']([^"']+)["']\s*(?:#.*)?$'''
)
PACKAGE_VERSION_RE = re.compile(
    r'^__version__\s*=\s*["\']([^"\']+)["\']\s*$', re.MULTILINE
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Require an immutable release tag to match both project version declarations."
    )
    parser.add_argument("--release-tag", required=True, help="exact release tag, for example v1.0.11")
    args = parser.parse_args(argv)

    errors = check_release_version(args.release_tag)
    if errors:
        for error in errors:
            print(f"release version: {error}", file=sys.stderr)
        return 1
    print(f"release version matched: {args.release_tag}")
    return 0


def check_release_version(release_tag: str, *, root: Path = ROOT) -> list[str]:
    errors: list[str] = []
    project_version = read_project_version(root / "pyproject.toml", errors)
    package_version = read_package_version(
        root / "src" / "remote_ops_workspace" / "__init__.py", errors
    )

    if not release_tag.startswith("v") or not VERSION_RE.fullmatch(release_tag[1:]):
        errors.append(f"release tag {release_tag!r} must be canonical vX.Y.Z")
    elif project_version and release_tag != f"v{project_version}":
        errors.append(
            f"release tag {release_tag} does not match project version {project_version}"
        )

    if project_version and package_version and package_version != project_version:
        errors.append(
            "package __version__ "
            f"{package_version} does not match project version {project_version}"
        )
    return errors


def read_project_version(path: Path, errors: list[str]) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        errors.append(f"missing {path}")
        return None

    if tomllib is None:
        table_match = PROJECT_TABLE_RE.search(text)
        if not table_match:
            errors.append(f"{path} is missing [project]")
            return None
        version_match = PROJECT_VERSION_RE.search(table_match.group("body"))
        project: object = {"version": version_match.group(1)} if version_match else {}
    else:
        try:
            project = tomllib.loads(text).get("project")
        except tomllib.TOMLDecodeError as exc:
            errors.append(f"{path} is not valid TOML: {exc}")
            return None
    if not isinstance(project, dict):
        errors.append(f"{path} is missing [project]")
        return None
    version = project.get("version")
    if not isinstance(version, str) or not VERSION_RE.fullmatch(version):
        errors.append(f"{path} project.version must be canonical X.Y.Z")
        return None
    return version


def read_package_version(path: Path, errors: list[str]) -> str | None:
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        errors.append(f"missing {path}")
        return None
    match = PACKAGE_VERSION_RE.search(text)
    if not match or not VERSION_RE.fullmatch(match.group(1)):
        errors.append(f"{path} must declare a canonical __version__")
        return None
    return match.group(1)


if __name__ == "__main__":
    raise SystemExit(main())

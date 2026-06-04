from __future__ import annotations

import argparse
import fnmatch
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_GITIGNORE_PATTERNS = (
    "__pycache__/",
    "*.py[cod]",
    "build/",
    "dist/",
    "native-dist/",
    "release-assets/",
    ".pytest_cache/",
    ".mypy_cache/",
    ".ruff_cache/",
    ".coverage",
    "htmlcov/",
    ".verify-row-home/",
    ".row/",
    "remote-ops-data/",
    "profiles.json",
    "vault.json",
    "*.vault",
    "*.key",
    "*.pem",
    "*.p12",
    "*.pfx",
    "*.ppk",
    "*.rdp",
    "*.vnc",
    "*.kdbx",
    "*.log",
    "support-bundle-*.zip",
)

PRIVATE_BASENAME_PATTERNS = (
    "profiles.json",
    "vault.json",
    "*.vault",
    "*.key",
    "*.pem",
    "*.p12",
    "*.pfx",
    "*.ppk",
    "*.rdp",
    "*.vnc",
    "*.kdbx",
    "*.log",
    "support-bundle-*.zip",
)

PRIVATE_PREFIXES = (
    ".row/",
    "remote-ops-data/",
)

TRANSIENT_OUTPUT_PREFIXES = (
    ".verify-row-home/",
    "build/",
    "dist/",
    "native-dist/",
    "release-assets/",
)

TEXT_SUFFIXES = {
    ".bat",
    ".css",
    ".html",
    ".ini",
    ".iss",
    ".js",
    ".json",
    ".md",
    ".ps1",
    ".py",
    ".sh",
    ".toml",
    ".txt",
    ".wxs",
    ".xml",
    ".yaml",
    ".yml",
}

TEXT_FILENAMES = {
    ".gitattributes",
    ".gitignore",
    "LICENSE",
    "Makefile",
    "NOTICE",
}


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    errors: list[str] = []
    tracked = git_paths("ls-files")
    untracked = git_paths("ls-files", "--others", "--exclude-standard")
    scanned_paths = sorted(set(tracked + untracked))

    errors.extend(check_gitignore_patterns(ROOT))
    errors.extend(check_conflict_markers(ROOT, scanned_paths))
    errors.extend(check_private_artifacts(tracked, "tracked"))
    errors.extend(check_private_artifacts(untracked, "untracked non-ignored"))
    errors.extend(check_unignored_transient_outputs(untracked))
    errors.extend(check_docs_and_verifier(ROOT))
    if args.require_clean:
        errors.extend(check_clean_worktree())

    if errors:
        for error in errors:
            print(f"repository cleanup: {error}", file=sys.stderr)
        return 1
    print("repository cleanup preflight passed")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Check repository hygiene before release tagging.")
    parser.add_argument(
        "--require-clean",
        action="store_true",
        help="also require git status --porcelain to be empty; use immediately before tagging",
    )
    return parser.parse_args(argv)


def check_gitignore_patterns(root: Path) -> list[str]:
    gitignore = root / ".gitignore"
    try:
        patterns = {line.strip() for line in gitignore.read_text(encoding="utf-8").splitlines()}
    except FileNotFoundError:
        return ["missing .gitignore"]
    return [
        f".gitignore missing required cleanup pattern: {pattern}"
        for pattern in REQUIRED_GITIGNORE_PATTERNS
        if pattern not in patterns
    ]


def check_conflict_markers(root: Path, paths: list[str]) -> list[str]:
    errors: list[str] = []
    for relative in paths:
        path = root / relative
        if not is_text_path(path) or not path.exists() or not path.is_file():
            continue
        try:
            lines = path.read_text(encoding="utf-8").splitlines()
        except UnicodeDecodeError:
            continue
        for number, line in enumerate(lines, start=1):
            if line.startswith("<<<<<<< ") or line.startswith(">>>>>>> "):
                errors.append(f"{relative}:{number} contains a merge conflict marker")
    return errors


def check_private_artifacts(paths: list[str], label: str) -> list[str]:
    errors = []
    for relative in paths:
        if is_private_artifact(relative):
            errors.append(f"{label} private/support artifact must not be committed or left unignored: {relative}")
    return errors


def check_unignored_transient_outputs(paths: list[str]) -> list[str]:
    errors = []
    for relative in paths:
        normalized = normalize_path(relative)
        if any(normalized == prefix.rstrip("/") or normalized.startswith(prefix) for prefix in TRANSIENT_OUTPUT_PREFIXES):
            errors.append(f"transient output path is not ignored: {relative}")
    return errors


def check_docs_and_verifier(root: Path) -> list[str]:
    errors = []
    verifier = read(root, "scripts/verify.py")
    if "scripts/check_repository_cleanup.py" not in verifier:
        errors.append("scripts/verify.py must run scripts/check_repository_cleanup.py")
    docs = "\n".join(
        read(root, path)
        for path in (
            "README.md",
            "README.tr.md",
            "CONTRIBUTING.md",
            "docs/RELEASE_STRATEGY.md",
            "docs/VERIFYING.md",
        )
    )
    for snippet in (
        "Repository cleanup before tagging",
        "python scripts/check_repository_cleanup.py",
        "--require-clean",
    ):
        if snippet not in docs:
            errors.append(f"cleanup docs missing required snippet: {snippet}")
    return errors


def check_clean_worktree() -> list[str]:
    result = run_git("status", "--porcelain")
    if result is None:
        return ["cannot inspect git status for --require-clean"]
    if result.stdout.strip():
        return ["working tree must be clean before tagging; commit, stash, or remove local changes first"]
    return []


def git_paths(*args: str) -> list[str]:
    result = run_git(*args)
    if result is None:
        return []
    return [line for line in result.stdout.splitlines() if line]


def run_git(*args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", *args],
            cwd=ROOT,
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError):
        return None


def is_private_artifact(relative: str) -> bool:
    normalized = normalize_path(relative)
    if any(normalized == prefix.rstrip("/") or normalized.startswith(prefix) for prefix in PRIVATE_PREFIXES):
        return True
    basename = Path(normalized).name
    return any(fnmatch.fnmatchcase(basename, pattern) for pattern in PRIVATE_BASENAME_PATTERNS)


def is_text_path(path: Path) -> bool:
    return path.name in TEXT_FILENAMES or path.suffix.lower() in TEXT_SUFFIXES


def normalize_path(relative: str) -> str:
    return relative.replace("\\", "/").lstrip("./")


def read(root: Path, relative: str) -> str:
    return (root / relative).read_text(encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

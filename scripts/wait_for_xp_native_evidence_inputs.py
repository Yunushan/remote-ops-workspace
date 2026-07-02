from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path


DEFAULT_TIMEOUT_SECONDS = 2700
DEFAULT_POLL_SECONDS = 10.0
DEFAULT_STABLE_POLLS = 2


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    errors = wait_for_xp_native_evidence_inputs(
        assets_dir=args.assets_dir,
        evidence_file=args.evidence_file,
        evidence_dir=args.evidence_dir,
        timeout_seconds=args.timeout_seconds,
        poll_seconds=args.poll_seconds,
        stable_polls=args.stable_polls,
    )
    if errors:
        for error in errors:
            print(f"XP staged evidence inputs: {error}", file=sys.stderr)
        return 1
    print("XP staged evidence inputs found")
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Wait for XP native evidence files staged onto the self-hosted "
            "collector after a workflow run starts and exposes its source run URL."
        )
    )
    parser.add_argument("--assets-dir", type=Path, required=True)
    parser.add_argument("--evidence-file", type=Path, required=True)
    parser.add_argument("--evidence-dir", type=Path, required=True)
    parser.add_argument("--timeout-seconds", type=int, default=DEFAULT_TIMEOUT_SECONDS)
    parser.add_argument("--poll-seconds", type=float, default=DEFAULT_POLL_SECONDS)
    parser.add_argument("--stable-polls", type=int, default=DEFAULT_STABLE_POLLS)
    return parser.parse_args(argv)


def wait_for_xp_native_evidence_inputs(
    *,
    assets_dir: Path,
    evidence_file: Path,
    evidence_dir: Path,
    timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
    poll_seconds: float = DEFAULT_POLL_SECONDS,
    stable_polls: int = DEFAULT_STABLE_POLLS,
) -> list[str]:
    deadline = time.monotonic() + max(timeout_seconds, 0)
    delay = max(poll_seconds, 0.1)
    required_stable_polls = max(stable_polls, 1)
    last_snapshot: tuple[tuple[str, int, int], ...] | None = None
    stable_count = 0
    errors: list[str] = []
    while True:
        errors = check_xp_native_evidence_inputs(
            assets_dir=assets_dir,
            evidence_file=evidence_file,
            evidence_dir=evidence_dir,
        )
        if errors:
            last_snapshot = None
            stable_count = 0
        else:
            snapshot, snapshot_errors = snapshot_xp_native_evidence_inputs(
                assets_dir=assets_dir,
                evidence_file=evidence_file,
                evidence_dir=evidence_dir,
            )
            errors = snapshot_errors
            if errors:
                last_snapshot = None
                stable_count = 0
            elif snapshot == last_snapshot:
                stable_count += 1
            else:
                last_snapshot = snapshot
                stable_count = 1
            if stable_count >= required_stable_polls:
                return []
        if time.monotonic() >= deadline:
            if errors:
                return errors
            return [
                "staged XP evidence inputs did not remain stable for "
                f"{required_stable_polls} consecutive poll(s) before timeout"
            ]
        sleep_for = min(delay, max(deadline - time.monotonic(), 0.0))
        if sleep_for:
            time.sleep(sleep_for)


def check_xp_native_evidence_inputs(
    *,
    assets_dir: Path,
    evidence_file: Path,
    evidence_dir: Path,
) -> list[str]:
    errors: list[str] = []
    for label, path in (
        ("assets_dir", assets_dir),
        ("evidence_file", evidence_file),
        ("evidence_dir", evidence_dir),
    ):
        errors.extend(check_parent_directories_not_symlinked(label, path))
        if path.is_symlink():
            errors.append(f"{label} must not be a symlink: {path}")
    if not assets_dir.is_dir():
        errors.append(f"assets_dir is not a directory: {assets_dir}")
    if not evidence_file.is_file():
        errors.append(f"evidence_file is not a file: {evidence_file}")
    if not evidence_dir.is_dir():
        errors.append(f"evidence_dir is not a directory: {evidence_dir}")
    return errors


def snapshot_xp_native_evidence_inputs(
    *,
    assets_dir: Path,
    evidence_file: Path,
    evidence_dir: Path,
) -> tuple[tuple[tuple[str, int, int], ...], list[str]]:
    errors: list[str] = []
    entries: list[tuple[str, int, int]] = []
    evidence_json_snapshot = file_snapshot("evidence_file", evidence_file)
    if isinstance(evidence_json_snapshot, str):
        errors.append(evidence_json_snapshot)
    else:
        entries.append(evidence_json_snapshot)
    evidence_file_resolved = evidence_file.resolve(strict=False)
    for label, root in (("assets_dir", assets_dir), ("evidence_dir", evidence_dir)):
        symlink_errors = staged_tree_symlink_errors(label, root)
        if symlink_errors:
            errors.extend(symlink_errors)
        files = sorted(
            path
            for path in root.rglob("*")
            if path.is_file()
            and not (label == "evidence_dir" and path.resolve(strict=False) == evidence_file_resolved)
        )
        if not files:
            errors.append(f"{label} contains no files yet: {root}")
            continue
        for path in files:
            if path.is_symlink():
                errors.append(f"{label} staged file must not be a symlink: {path}")
                continue
            snapshot = file_snapshot(label, path, root=root)
            if isinstance(snapshot, str):
                errors.append(snapshot)
            else:
                entries.append(snapshot)
    return tuple(sorted(entries)), errors


def check_parent_directories_not_symlinked(label: str, path: Path) -> list[str]:
    errors: list[str] = []
    for parent in path.parents:
        if str(parent) in ("", "."):
            continue
        try:
            is_symlink = parent.is_symlink()
        except OSError as exc:
            errors.append(f"{label} parent directory could not be checked: {parent}: {exc}")
            continue
        if is_symlink:
            errors.append(f"{label} path must not contain symlinked parent directory: {parent}")
    return errors


def staged_tree_symlink_errors(label: str, root: Path) -> list[str]:
    errors: list[str] = []
    for path in sorted(root.rglob("*")):
        try:
            is_symlink = path.is_symlink()
        except OSError as exc:
            errors.append(f"{label} staged path could not be checked for symlink: {path}: {exc}")
            continue
        if is_symlink:
            errors.append(f"{label} staged path must not be a symlink: {path}")
    return errors


def file_snapshot(label: str, path: Path, *, root: Path | None = None) -> tuple[str, int, int] | str:
    try:
        stat = path.stat()
    except OSError as exc:
        return f"{label} could not be statted: {path}: {exc}"
    name = path.as_posix() if root is None else f"{label}/{path.relative_to(root).as_posix()}"
    return (name, stat.st_size, stat.st_mtime_ns)


if __name__ == "__main__":
    raise SystemExit(main())

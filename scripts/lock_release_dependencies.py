#!/usr/bin/env python3
"""Resolve complete hash-locked release inputs for each declared build platform.

This command generates dependency inputs, not native-host or redistribution
approval evidence. Review the diff and verify each lock on its native builder.
The resolver executable is supplied explicitly and must match the pinned version.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
CONFIG = ROOT / "configs" / "release_dependency_locks.json"
LOCKS = ROOT / "requirements-locks"


def release_input_paths(root: Path, config: dict) -> list[Path]:
    return [
        root / "configs/release_dependency_locks.json",
        root / config["constraints"],
        *sorted((root / "requirements-locks/inputs").glob("*.in")),
    ]


def release_input_hashes(root: Path, config: dict) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in release_input_paths(root, config)
    }


def lock_hashes() -> dict[str, str]:
    return {path.name: hashlib.sha256(path.read_bytes()).hexdigest() for path in sorted(LOCKS.glob("*.txt"))}


def prior_unselected_hashes(
    receipt_path: Path, metadata: dict, selected_locks: set[str], expected_locks: set[str],
) -> dict[str, str]:
    try:
        previous = json.loads(receipt_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ValueError("partial resolution needs a valid previous receipt. Run again without --target") from exc
    if not isinstance(previous, dict) or any(previous.get(key) != value for key, value in metadata.items()):
        raise ValueError("release inputs differ from the previous receipt. Run again without --target")
    previous_hashes = previous.get("lock_sha256")
    if not isinstance(previous_hashes, dict) or set(previous_hashes) != expected_locks:
        raise ValueError("previous receipt must cover all declared locks. Run again without --target")
    return {name: digest for name, digest in previous_hashes.items() if name not in selected_locks}


def lock_names(targets: dict, selected: list[str]) -> set[str]:
    names = {f"{target}.txt" for target in selected}
    names.update(f"{target}-bootstrap.txt" for target in selected if targets[target].get("bootstrap"))
    return names


def check_unselected_hashes(
    actual: dict[str, str], selected_locks: set[str], previous: dict[str, str],
) -> None:
    if {name: digest for name, digest in actual.items() if name not in selected_locks} != previous:
        raise ValueError("unselected locks differ from the previous receipt. Run again without --target")


def check_release_lf(root: Path, config: dict) -> list[str]:
    """Keep receipts bound to bytes that a normal Git checkout preserves."""
    errors: list[str] = []
    files = [*release_input_paths(root, config), *sorted((root / "requirements-locks").glob("*.txt"))]
    for path in files:
        if b"\r" in path.read_bytes():
            errors.append(
                f"{path.relative_to(root).as_posix()}: byte-hashed release inputs and locks require LF-only line endings; "
                "convert CRLF/lone CR to LF without changing pins, then refresh and review the resolution receipt"
            )
    required = {
        "*.json text eol=lf",
        "requirements-release.txt text eol=lf",
        "requirements-locks/*.txt text eol=lf",
        "requirements-locks/inputs/*.in text eol=lf",
    }
    attributes = root / ".gitattributes"
    actual = {" ".join(line.split()) for line in attributes.read_text(encoding="utf-8").splitlines()} if attributes.is_file() else set()
    for rule in sorted(required - actual):
        errors.append(f"root .gitattributes must preserve release receipt bytes with: {rule}")
    return errors


def compile_lock(uv: Path, config: dict, target: str, spec: dict, *, system_certs: bool) -> None:
    inputs = LOCKS / "inputs"
    output = LOCKS / f"{target}.txt"
    command = [str(uv)]
    if system_certs:
        command.append("--system-certs")
    command.extend([
        "pip", "compile", str(inputs / spec["input"]),
        "--quiet", "--no-header", "--no-annotate", "--generate-hashes",
        "--python-version", config["python_version"],
        "--python-platform", spec["platform"],
        "--default-index", config["resolver"]["index"],
        "--cache-dir", str(ROOT / ".tmp" / "uv-lock-cache"),
        "--constraint", str(ROOT / config["constraints"]),
        "--output-file", str(output),
    ])
    sources = spec.get("source_packages", [])
    if sources:
        command.extend(["--only-binary", ":all:", "--no-binary", ",".join(sources)])
    else:
        command.append("--no-build")
    environment = os.environ.copy()
    if spec["platform"].endswith("-apple-darwin"):
        environment["MACOSX_DEPLOYMENT_TARGET"] = config["macos_deployment_target"]
    subprocess.run(command, cwd=ROOT, env=environment, check=True)
    contents = output.read_text(encoding="utf-8")
    if not re.search(r"(?m)^\w[\w.-]*==", contents) or "--hash=sha256:" not in contents:
        raise ValueError(f"resolver produced an empty or unhashed lock for {target}")
    header = (
        f"# Target: {target}; Python: {config['python_version']}; resolver: uv {config['resolver']['version']}\n"
        "# Generated by scripts/lock_release_dependencies.py; verify on the native builder.\n"
        "# This file is not runtime inventory or independent approval evidence.\n"
    )
    output.write_text(header + contents, encoding="utf-8", newline="\n")
    print(f"resolved {target}: {output.relative_to(ROOT).as_posix()}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--uv", type=Path, required=True)
    parser.add_argument("--target", action="append", help="target ID; omit to resolve all when shared inputs change")
    parser.add_argument("--system-certs", action="store_true")
    args = parser.parse_args(argv)
    try:
        config_bytes = CONFIG.read_bytes()
        config = json.loads(config_bytes.decode("utf-8"))
        line_errors = check_release_lf(ROOT, config)
        if line_errors:
            raise ValueError("; ".join(line_errors))
        input_hashes = release_input_hashes(ROOT, config)
        if input_hashes[CONFIG.relative_to(ROOT).as_posix()] != hashlib.sha256(config_bytes).hexdigest():
            raise ValueError("release configuration changed while reading inputs. Run resolution again")
        receipt_path = LOCKS / "resolution.json"
        receipt = {
            "schema_version": 1,
            "scope": config["evidence_scope"],
            "resolver": config["resolver"],
            "python_version": config["python_version"],
            "input_sha256": input_hashes,
        }
        declared_targets = config["targets"]
        targets = args.target or list(declared_targets)
        for target in targets:
            if target not in declared_targets:
                raise ValueError(f"unknown release-lock target: {target}")
        previous = None
        selected_locks = lock_names(declared_targets, targets)
        expected_locks = lock_names(declared_targets, list(declared_targets))
        if selected_locks != expected_locks:
            previous = prior_unselected_hashes(receipt_path, receipt, selected_locks, expected_locks)
            check_unselected_hashes(lock_hashes(), selected_locks, previous)
        uv = args.uv.resolve(strict=True)
        actual = subprocess.run([str(uv), "--version"], check=True, text=True, capture_output=True)
        version = re.match(r"^uv\s+(\S+)(?:\s|$)", actual.stdout.strip())
        if version is None or version.group(1) != config["resolver"]["version"]:
            raise ValueError(f"expected uv {config['resolver']['version']}, got {actual.stdout.strip()}")
        for target in targets:
            spec = declared_targets[target]
            compile_lock(uv, config, target, spec, system_certs=args.system_certs)
            if spec.get("bootstrap"):
                bootstrap = {
                    **spec,
                    "input": spec.get("bootstrap_input", "build-backends.in"),
                    "source_packages": [],
                }
                compile_lock(uv, config, f"{target}-bootstrap", bootstrap, system_certs=args.system_certs)
        line_errors = check_release_lf(ROOT, config)
        if line_errors:
            raise ValueError("; ".join(line_errors))
        if release_input_hashes(ROOT, config) != input_hashes:
            raise ValueError("release inputs changed during resolution. Run resolution again")
        resolved_hashes = lock_hashes()
        if previous is not None:
            check_unselected_hashes(resolved_hashes, selected_locks, previous)
        if set(resolved_hashes) != expected_locks:
            raise ValueError("generated locks must exactly cover declared final and bootstrap locks")
        receipt["lock_sha256"] = resolved_hashes
        receipt_path.write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8", newline="\n")
    except (OSError, ValueError, KeyError, subprocess.CalledProcessError) as exc:
        print(f"release lock resolution: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

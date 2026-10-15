"""Validate resolved modern release locks and mandatory workflow consumption.

This checks build inputs; it does not approve redistribution or certify native hosts.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location(
    "release_lock_compliance", ROOT / "scripts" / "check_release_license_compliance.py"
)
assert spec is not None and spec.loader is not None
compliance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(compliance)
resolver_spec = importlib.util.spec_from_file_location(
    "release_lock_resolver", ROOT / "scripts" / "lock_release_dependencies.py"
)
assert resolver_spec is not None and resolver_spec.loader is not None
resolver = importlib.util.module_from_spec(resolver_spec)
resolver_spec.loader.exec_module(resolver)

MODERN_TARGETS = {
    "source-linux-x86_64", "windows-x86", "windows-x64", "windows-arm64",
    "macos-x64", "macos-arm64", "linux-x86_64", "linux-aarch64",
    "release-verifier-linux-x86_64",
}


def check_locks(root: Path = ROOT, workflows: dict[str, str] | None = None) -> list[str]:
    errors: list[str] = []
    config = json.loads((root / "configs/release_dependency_locks.json").read_text(encoding="utf-8"))
    receipt = json.loads((root / "requirements-locks/resolution.json").read_text(encoding="utf-8"))
    errors.extend(resolver.check_release_lf(root, config))
    targets = config["targets"]
    if set(targets) != MODERN_TARGETS:
        errors.append("resolved release targets must exactly cover the modern source/native/verifier matrix")
    for key in ("resolver", "python_version"):
        if receipt.get(key) != config.get(key):
            errors.append(f"release lock receipt {key} differs from the resolver configuration")
    expected_inputs = {path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest() for path in resolver.release_input_paths(root, config)}
    if receipt.get("input_sha256") != expected_inputs:
        errors.append("release lock resolution inputs changed; regenerate and review the locks")
    expected_locks = {f"{target}.txt" for target in targets}
    expected_locks.update(f"{target}-bootstrap.txt" for target, row in targets.items() if row.get("bootstrap"))
    if set(receipt.get("lock_sha256", {})) != expected_locks:
        errors.append("release lock receipt must exactly cover final and bootstrap locks")
    for name in sorted(expected_locks):
        relative = f"requirements-locks/{name}"
        entries, lock_errors = compliance.read_hashed_lock_entries(root, {"file": relative}, relative)
        errors.extend(lock_errors)
        if not lock_errors and receipt.get("lock_sha256", {}).get(name) != hashlib.sha256((root / relative).read_bytes()).hexdigest():
            errors.append(f"release lock digest changed: {name}")
        if name == "windows-x86.txt" and {"bcrypt", "cryptography", "truststore", "pyqt6", "pyftpdlib", "pyopenssl"} & set(entries):
            errors.append("Windows x86 lock must preserve its unavailable security/server/GUI boundary")
    for target, row in targets.items():
        if row.get("bootstrap"):
            errors.extend(compliance.check_bootstrap_lock_subset(
                root, f"requirements-locks/{target}.txt", f"requirements-locks/{target}-bootstrap.txt"
            ))
    if workflows is None:
        workflows = {name: (root / ".github/workflows" / name).read_text(encoding="utf-8") for name in ("release.yml", "versioned-unsigned-release.yml")}
    for name, workflow in workflows.items():
        for target, row in targets.items():
            if target.startswith("release-verifier-"):
                continue
            lock = f"requirements-locks/{target}.txt"
            if target.startswith("source-"):
                job, arch = "source-and-python", None
            else:
                _, job, arch = compliance.producer_for_target(target, release_workflow=workflow, extended_workflow="", xp_workflow="")
            block = compliance.workflow_job_block(workflow, job)
            if arch is not None and not compliance.matrix_row_binds_lock(block, arch, lock):
                errors.append(f"{name} {target} matrix does not bind its reviewed lock")
            bootstrap = (
                f"requirements-locks/{target}-bootstrap.txt" if row.get("bootstrap")
                else compliance.matrix_row_lock(block, arch, "bootstrap_lock") if arch is not None
                else None
            )
            if bootstrap is not None and arch is not None and compliance.matrix_row_lock(block, arch, "bootstrap_lock") != bootstrap:
                errors.append(f"{name} {target} matrix does not bind its reviewed bootstrap lock")
            errors.extend(f"{name}: {error}" for error in compliance.check_native_job_lock_usage(
                block, job, target, lock, allow_matrix_lock=arch is not None,
                bootstrap_lock_path=bootstrap, lock_root=root,
            ))
        if "--no-build-isolation --only-binary=:all: --no-binary=cryptography,pyftpdlib" not in workflow:
            errors.append(f"{name} must restrict source builds to the reviewed cryptography/FTP inputs")
    return errors


def main() -> int:
    try:
        errors = check_locks()
    except (OSError, ValueError, KeyError) as exc:
        errors = [str(exc)]
    for error in errors:
        print(f"release dependency locks: {error}", file=sys.stderr)
    if errors:
        return 1
    print("modern release dependency locks and workflow consumption passed; native evidence and independent approval remain separate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

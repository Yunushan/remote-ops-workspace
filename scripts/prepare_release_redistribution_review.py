"""Collect exact candidate assets and runtime inputs for independent redistribution review."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import zipfile
from contextlib import suppress
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]

from scripts.check_release_dependency_locks import check_locks, check_runtime_report  # noqa: E402
from scripts.check_release_license_compliance import (  # noqa: E402
    matrix_row_binds_lock,
    path_is_reparse,
    producer_for_target,
    secure_regular_file,
    workflow_job_block,
)
from scripts.release_candidate_inventory import (  # noqa: E402
    BUILD_WORKFLOW,
    MANAGED_DEBIAN_ARTIFACT,
    RPM_ARTIFACT,
    RUNTIME_REPORT_ARTIFACT_NAMES,
    RUNTIME_REPORT_NAME,
    GitHubClient,
    check_artifact_metadata,
    download_qualification_archives,
    materialize_sealed_records,
    normalize_repository,
    normalize_sha,
    normalize_tag,
    sealed_json_artifact,
    validate_managed_report,
    validate_rpm_report,
    validate_runtime_report,
)
from scripts.release_candidate_source import (  # noqa: E402
    INVENTORY_FILE,
    InventoryPointer,
    read_attested_inventory,
    require_candidate_run,
)

POLICY_FILE = "configs/release_compliance_policy.json"


def require_clean_source(sha: str) -> None:
    def git(*arguments: str) -> str:
        result = subprocess.run(
            ["git", *arguments], cwd=ROOT, capture_output=True, text=True, check=True, timeout=30,
        )
        return result.stdout.strip()

    if git("rev-parse", "--verify", "HEAD") != sha or git("status", "--porcelain=v1", "--untracked-files=no"):
        raise ValueError("run review preparation from the selected release SHA with clean tracked files")


def review_locks(policy: bytes) -> dict[str, str]:
    configured = json.loads(policy)["build_lock_enforcement"]["platform_locks"]
    if not isinstance(configured, dict):
        raise ValueError("compliance policy platform_locks must be an object")
    workflow = (ROOT / BUILD_WORKFLOW).read_text(encoding="utf-8")
    locks = {}
    for target in RUNTIME_REPORT_ARTIFACT_NAMES:
        lock = configured.get(target)
        _, job, architecture = producer_for_target(target, release_workflow=workflow, extended_workflow="")
        if (
            not isinstance(lock, str) or architecture is None
            or not matrix_row_binds_lock(workflow_job_block(workflow, job), architecture, lock)
        ):
            raise ValueError(f"{target} compliance policy lock must match the release build matrix")
        locks[target] = lock
    return locks


def evidence_record(path: Path, bundle: Path, raw: bytes, reference: str) -> dict[str, Any]:
    return {
        "file": path.relative_to(bundle).as_posix(),
        "sha256": hashlib.sha256(raw).hexdigest(),
        "size_bytes": len(raw),
        "reference": reference,
    }


def collect_qualification_archives(
    client: GitHubClient, archives: Path, inventory: dict[str, Any],
    repository: str, tag: str, sha: str, run_id: int,
) -> dict[str, Any]:
    artifact_ids = {}
    if "managed_debian_update" in inventory:
        record = inventory["managed_debian_update"]
        artifact_id = validate_managed_report(record, tag, sha, run_id, 1, source_root=ROOT)
        artifact_ids[MANAGED_DEBIAN_ARTIFACT] = artifact_id
    if "rpm_smoke" in inventory:
        artifact_id, _ = validate_rpm_report(
            inventory["rpm_recovery"], repository, tag, sha, run_id, 1, source_root=ROOT,
        )
        artifact_ids[RPM_ARTIFACT] = artifact_id

    download_qualification_archives(client, inventory, run_id, sha, archives)
    records = {}
    for name, artifact_id in artifact_ids.items():
        archive = archives / f"{name}.zip"
        reference = f"https://github.com/{repository}/actions/runs/{run_id}/artifacts/{artifact_id}"
        records[name] = evidence_record(archive, archives.parent, archive.read_bytes(), reference)
    smoke = {**inventory.get("gui_smoke", {}), **inventory.get("linux_smoke", {})}
    for name, record in smoke.items():
        records[name] = {
            "file": f"archives/{name}.zip",
            "sha256": record["archive_digest"].removeprefix("sha256:"),
            "size_bytes": record["size_in_bytes"],
            "reference": f"https://github.com/{repository}/actions/runs/{run_id}/artifacts/{record['artifact_id']}",
        }
    return records


def collect_runtime_inputs(
    client: GitHubClient,
    bundle: Path,
    archives: Path,
    repository: str,
    sha: str,
    run_id: int,
    sealed_reports: dict[str, dict[str, Any]],
    platform_locks: dict[str, str],
) -> dict[str, Any]:
    reviews = {}
    for target, artifact_name in sorted(RUNTIME_REPORT_ARTIFACT_NAMES.items()):
        expected = sealed_reports[target]
        artifact_id = expected["artifact_id"]
        metadata = client.json(f"actions/artifacts/{artifact_id}")
        check_artifact_metadata(
            metadata, artifact_id=artifact_id, name=artifact_name,
            digest=expected["archive_digest"], run_id=run_id, release_sha=sha,
        )
        raw, observed = sealed_json_artifact(
            client, metadata, artifact_name, run_id, sha, RUNTIME_REPORT_NAME,
            archive_output=archives / f"{artifact_name}.zip",
        )
        if observed != expected:
            raise ValueError(f"{target} pip inspect bytes do not match the sealed inventory")
        validate_runtime_report(raw, artifact_name)
        report = bundle / "runtime-reports" / target / RUNTIME_REPORT_NAME
        report.parent.mkdir(parents=True)
        report.write_bytes(raw)

        source_name = platform_locks[target]
        source, error = secure_regular_file(ROOT, source_name, f"{target} resolver lock")
        if source is None:
            raise ValueError(error)
        lock = bundle / source_name
        lock.parent.mkdir(parents=True, exist_ok=True)
        lock_bytes = source.read_bytes()
        lock.write_bytes(lock_bytes)
        errors = check_runtime_report(report, lock)
        if errors:
            raise ValueError(f"{target}: " + "; ".join(errors))

        report_reference = f"https://github.com/{repository}/actions/runs/{run_id}/artifacts/{artifact_id}"
        lock_reference = f"https://github.com/{repository}/blob/{sha}/{source_name}"
        reviews[target] = {
            "realized_environment": {
                **evidence_record(report, bundle, raw, report_reference), "format": "pip-inspect-v1",
            },
            "resolver_lock": {
                **evidence_record(lock, bundle, lock_bytes, lock_reference),
                "fully_hashed": True, "format": "pip-requirements", "source_file": source_name,
            },
        }
    return reviews


def prepare_review(
    client: GitHubClient, output: Path, repository: str, tag: str, sha: str, pointer: InventoryPointer,
) -> None:
    destination = output.absolute()
    if (
        os.path.lexists(destination) or destination.resolve().is_relative_to(ROOT)
        or any(path_is_reparse(path) for path in destination.parents)
    ):
        raise ValueError("--out must be a new directory outside the checkout with unlinked parents")

    require_clean_source(sha)
    errors = check_locks(ROOT)
    if errors:
        raise ValueError("; ".join(errors))
    policy = (ROOT / POLICY_FILE).read_bytes()
    platform_locks = review_locks(policy)

    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix=".row-redistribution-review-", dir=destination.parent) as directory:
        packet = Path(directory) / "review"
        bundle, archives = packet / "bundle", packet / "archives"
        bundle.mkdir(parents=True)
        archives.mkdir()
        records, inventory_meta = read_attested_inventory(
            client, repository, bundle, tag, sha, pointer,
            archive_output=archives / "release-candidate-inventory.zip",
        )
        inventory = bundle / INVENTORY_FILE
        inventory_bytes = inventory.read_bytes()
        sealed = json.loads(inventory_bytes)
        qualification_archives = collect_qualification_archives(
            client, archives, sealed, repository, tag, sha, pointer.run_id,
        )
        reviews = collect_runtime_inputs(
            client, bundle, archives, repository, sha, pointer.run_id,
            sealed["runtime_reports"], platform_locks,
        )
        materialize_sealed_records(client, records, packet / "assets", run_id=pointer.run_id, release_sha=sha)
        require_candidate_run(client, repository, tag, sha, pointer.run_id)
        require_clean_source(sha)

        inventory_reference = (
            f"https://github.com/{repository}/actions/runs/{pointer.run_id}/artifacts/{pointer.artifact_id}"
        )
        materials = {
            "schema": "row.redistribution-review-materials.v1",
            "repository": repository,
            "release_tag": tag,
            "release_sha": sha,
            "build_run_id": pointer.run_id,
            "build_run_attempt": 1,
            "policy_sha256": hashlib.sha256(policy).hexdigest(),
            "candidate_inventory": evidence_record(inventory, bundle, inventory_bytes, inventory_reference),
            "candidate_inventory_source": inventory_meta,
            "qualification_archives": qualification_archives,
            "modern_targets": reviews,
        }
        (packet / "review-materials.json").write_bytes((json.dumps(materials, indent=2) + "\n").encode("utf-8"))
        if os.name == "nt":
            packet.rename(destination)
        else:
            # Reserve the output name so rename cannot replace an existing empty directory.
            destination.mkdir(mode=0o700)
            try:
                packet.rename(destination)
            except OSError:
                with suppress(OSError):
                    destination.rmdir()
                raise


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--release-tag", required=True)
    parser.add_argument("--release-sha", required=True)
    parser.add_argument("--candidate-inventory", required=True, metavar='"RUN_ID ARTIFACT_ID sha256:DIGEST"')
    parser.add_argument("--out", required=True, type=Path, help="new review directory outside the checkout")
    args = parser.parse_args(argv)
    try:
        token = os.environ.get("GH_TOKEN") or os.environ.get("GITHUB_TOKEN")
        if not token:
            raise ValueError("GH_TOKEN or GITHUB_TOKEN is required")
        repository = normalize_repository(args.repository)
        pointer = InventoryPointer.parse(args.candidate_inventory)
        if pointer is None:
            raise ValueError("the sealed candidate inventory coordinates are required")
        prepare_review(
            GitHubClient(repository, token), args.out, repository,
            normalize_tag(args.release_tag), normalize_sha(args.release_sha), pointer,
        )
    except (OSError, KeyError, RuntimeError, ValueError, subprocess.SubprocessError, zipfile.BadZipFile) as exc:
        print(f"redistribution review preparation: {exc}", file=sys.stderr)
        return 1
    print(f"Prepared candidate assets and {len(RUNTIME_REPORT_ARTIFACT_NAMES)} native runtime inputs for review in {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Resolve a release asset from an attested, unpublished build inventory."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from scripts.check_platform_evidence_source_ref import resolve_tag_commit
from scripts.release_candidate_inventory import (
    CANDIDATE_INVENTORY_ARTIFACT,
    GitHubClient,
    check_artifact_metadata,
    check_build_run,
    materialize_records,
    normalize_digest,
    normalize_repository_from_api,
    positive_int,
    sealed_json_artifact,
    validate_inventory,
    verify_candidate_attestation,
)

INVENTORY_FILE = "release-candidate-inventory.json"
ASSETS = {
    "windows-msi": ("release-windows-native-x64", "remote-ops-workspace-{tag}-windows-x64.msi"),
    "wheel": ("release-source-python", "remote_ops_workspace-{version}-py3-none-any.whl"),
    "debian-amd64": ("release-linux-native-x86_64", "remote-ops-workspace-{tag}-linux-amd64.deb"),
}


@dataclass(frozen=True)
class InventoryPointer:
    run_id: int
    artifact_id: int
    archive_digest: str

    @classmethod
    def parse(cls, value: str) -> InventoryPointer | None:
        if value == "":
            return None
        match = re.fullmatch(r"([1-9][0-9]{0,18}) ([1-9][0-9]{0,18}) (sha256:[0-9a-f]{64})", value)
        if match is None:
            raise ValueError("expected candidate inventory coordinates as RUN_ID ARTIFACT_ID sha256:DIGEST")
        return cls(int(match[1]), int(match[2]), match[3])


def asset_filename(kind: str, tag: str) -> str:
    return ASSETS[kind][1].format(tag=tag, version=tag[1:])


def require_candidate_run(
    client: GitHubClient, repository: str, tag: str, sha: str, run_id: int,
) -> dict:
    observed, errors = resolve_tag_commit(client.json, tag)
    if errors or observed != sha:
        raise ValueError("live release tag does not resolve to the selected candidate SHA")
    run = client.json(f"actions/runs/{run_id}")
    check_build_run(run, release_tag=tag, release_sha=sha, run_id=run_id, run_attempt=1, require_success=True)
    if normalize_repository_from_api(run) != repository:
        raise ValueError("candidate build run belongs to a different repository")
    return run


def read_attested_inventory(
    client: GitHubClient, repository: str, directory: Path, tag: str, sha: str, pointer: InventoryPointer,
    *, archive_output: Path | None = None,
) -> tuple[list[dict], dict]:
    """Read the exact first-attempt candidate inventory without fetching package archives."""
    run = require_candidate_run(client, repository, tag, sha, pointer.run_id)
    coordinates = {"release_tag": tag, "release_sha": sha, "run_id": pointer.run_id, "run_attempt": 1}
    metadata = client.json(f"actions/artifacts/{pointer.artifact_id}")
    check_artifact_metadata(
        metadata, artifact_id=pointer.artifact_id, name=CANDIDATE_INVENTORY_ARTIFACT,
        digest=pointer.archive_digest, run_id=pointer.run_id, release_sha=sha,
    )
    raw, inventory = sealed_json_artifact(
        client, metadata, CANDIDATE_INVENTORY_ARTIFACT, pointer.run_id, sha, INVENTORY_FILE,
        archive_output=archive_output,
    )
    inventory_path = directory / INVENTORY_FILE
    with inventory_path.open("xb") as stream:
        stream.write(raw)
    verify_candidate_attestation(
        inventory_path, repository=repository, **coordinates,
        inventory_sha256=inventory["sha256"], build_event=run["event"],
    )
    return validate_inventory(json.loads(raw), repository=repository, **coordinates), inventory


def materialize_asset(
    client: GitHubClient, repository: str, directory: Path, tag: str, sha: str, pointer: InventoryPointer,
    *, kind: str,
) -> tuple[Path, dict, dict]:
    """Download the inventory and just the build archive owning the requested asset."""
    artifact_name = ASSETS[kind][0]
    filename = asset_filename(kind, tag)
    root = directory / tag
    root.mkdir()
    records, inventory = read_attested_inventory(client, repository, root, tag, sha, pointer)
    artifact = next(record for record in records if record["name"] == artifact_name)
    files = [entry for entry in artifact["files"] if isinstance(entry, dict) and entry.get("path") == filename]
    if len(files) != 1:
        raise ValueError(f"sealed {artifact_name} artifact must contain exactly one {filename}")
    file = files[0]
    normalize_digest(f"sha256:{file.get('sha256')}", f"sealed {filename} digest")
    positive_int(file.get("size"), f"sealed {filename} size")

    payload = client.json(f"actions/artifacts/{artifact['id']}")
    check_artifact_metadata(
        payload, artifact_id=artifact["id"], name=artifact_name,
        digest=artifact["archive_digest"], run_id=pointer.run_id, release_sha=sha,
    )
    assets = root / "assets"
    materialize_records(client, {artifact_name: payload}, assets, expected_records=[artifact])
    return assets / filename, file, {
        "kind": "sealed-candidate",
        "build_run_id": pointer.run_id,
        "build_run_attempt": 1,
        "inventory_artifact_id": pointer.artifact_id,
        "inventory_archive_digest": pointer.archive_digest,
        "inventory_sha256": inventory["sha256"],
        "native_artifact_id": artifact["id"],
        "native_archive_digest": artifact["archive_digest"],
    }

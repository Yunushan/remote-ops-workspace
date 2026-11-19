"""Resolve a stock Windows MSI from an attested, unpublished release candidate."""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path

from check_platform_evidence_source_ref import resolve_tag_commit
from release_candidate_inventory import (
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

WINDOWS_ARTIFACT = "release-windows-native-x64"
INVENTORY_FILE = "release-candidate-inventory.json"


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


def materialize_msi(
    client: GitHubClient, repository: str, directory: Path, tag: str, sha: str, pointer: InventoryPointer,
) -> tuple[Path, dict, dict]:
    """Materialize only the attested Windows x64 artifact for a disposable drill."""
    observed, errors = resolve_tag_commit(client.json, tag)
    if errors or observed != sha:
        raise ValueError("live release tag does not resolve to the selected candidate SHA")
    run = client.json(f"actions/runs/{pointer.run_id}")
    coordinates = {"release_tag": tag, "release_sha": sha, "run_id": pointer.run_id, "run_attempt": 1}
    check_build_run(run, **coordinates, require_success=True)
    if normalize_repository_from_api(run) != repository:
        raise ValueError("candidate build run belongs to a different repository")

    metadata = client.json(f"actions/artifacts/{pointer.artifact_id}")
    check_artifact_metadata(
        metadata, artifact_id=pointer.artifact_id, name=CANDIDATE_INVENTORY_ARTIFACT,
        digest=pointer.archive_digest, run_id=pointer.run_id, release_sha=sha,
    )
    raw, inventory = sealed_json_artifact(
        client, metadata, CANDIDATE_INVENTORY_ARTIFACT, pointer.run_id, sha, INVENTORY_FILE,
    )
    root = directory / tag
    root.mkdir()
    inventory_path = root / INVENTORY_FILE
    with inventory_path.open("xb") as stream:
        stream.write(raw)
    verify_candidate_attestation(
        inventory_path, repository=repository, **coordinates,
        inventory_sha256=inventory["sha256"], build_event=run["event"],
    )
    records = validate_inventory(json.loads(raw), repository=repository, **coordinates)
    windows = next(record for record in records if record["name"] == WINDOWS_ARTIFACT)
    filename = f"remote-ops-workspace-{tag}-windows-x64.msi"
    files = [entry for entry in windows["files"] if isinstance(entry, dict) and entry.get("path") == filename]
    if len(files) != 1:
        raise ValueError("sealed Windows artifact must contain one stock Windows x64 MSI")
    file = files[0]
    normalize_digest(f"sha256:{file.get('sha256')}", "sealed Windows MSI digest")
    positive_int(file.get("size"), "sealed Windows MSI size")

    payload = client.json(f"actions/artifacts/{windows['id']}")
    check_artifact_metadata(
        payload, artifact_id=windows["id"], name=WINDOWS_ARTIFACT,
        digest=windows["archive_digest"], run_id=pointer.run_id, release_sha=sha,
    )
    assets = root / "assets"
    materialize_records(client, {WINDOWS_ARTIFACT: payload}, assets, expected_records=[windows])
    return assets / filename, file, {
        "kind": "sealed-candidate",
        "build_run_id": pointer.run_id,
        "build_run_attempt": 1,
        "inventory_artifact_id": pointer.artifact_id,
        "inventory_archive_digest": pointer.archive_digest,
        "inventory_sha256": inventory["sha256"],
        "native_artifact_id": windows["id"],
        "native_archive_digest": windows["archive_digest"],
    }

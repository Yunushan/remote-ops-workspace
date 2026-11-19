from __future__ import annotations

import hashlib
import io
import json
import zipfile
from types import SimpleNamespace

import pytest

from scripts import qualify_windows_msi_upgrade as upgrade
from scripts import release_candidate_inventory as core
from scripts import windows_msi_candidate_source as source

REPO = upgrade.REPOSITORY
TAG = "v1.0.29"
SHA = "a" * 40
RUN = 123
INVENTORY = 100
MSI = f"remote-ops-workspace-{TAG}-windows-x64.msi"


def sha256(raw):
    return hashlib.sha256(raw).hexdigest()


def zip_bytes(files):
    result = io.BytesIO()
    with zipfile.ZipFile(result, "w") as archive:
        for name, body in files.items():
            archive.writestr(name, body)
    return result.getvalue()


@pytest.mark.parametrize("bad", ["1 2 abcd", "0 2 sha256:" + "a" * 64, "1 2 sha256:" + "A" * 64,
                                 "1\n2 sha256:" + "a" * 64, "1 2  sha256:" + "a" * 64])
def test_candidate_pointer_requires_exact_coordinates(bad):
    digest = "sha256:" + "a" * 64
    assert source.InventoryPointer.parse("") is None
    assert source.InventoryPointer.parse(f"123 100 {digest}") == source.InventoryPointer(123, 100, digest)
    with pytest.raises(ValueError, match="expected candidate inventory coordinates"):
        source.InventoryPointer.parse(bad)


@pytest.mark.parametrize(("defect", "message", "download_count"), [
    ("valid", "", 2),
    ("moved-tag", "live release tag", 0),
    ("failed-run", "completed successfully", 0),
    ("rerun", "run_attempt must be", 0),
    ("wrong-repository", "different repository", 0),
    ("cross-run-inventory", "not bound to the approved build run", 0),
    ("wrong-inventory-pin", "live digest", 0),
    ("wrong-zip-bytes", "archive does not match GitHub", 1),
    ("self-hosted-attestation", "lacks a witnessed exact-tag attestation", 1),
    ("wrong-attestation-attempt", "lacks a witnessed exact-tag attestation", 1),
    ("missing-msi", "one stock Windows x64 MSI", 1),
    ("cross-run-windows-artifact", "not bound to the approved build run", 1),
    ("windows-entry-mismatch", "bytes/metadata do not match approved inventory", 2),
])
def test_resolves_only_msi_from_the_exact_attested_build(tmp_path, monkeypatch, defect, message, download_count):
    payloads = {MSI: b"native MSI fixture", "manifest.json": b"native manifest fixture"}
    if defect == "missing-msi":
        payloads.pop(MSI)
    archives = {}
    records = []
    for artifact_id, label in enumerate(sorted(core.EXPECTED_ARTIFACT_NAMES), 200):
        contents = payloads if label == source.WINDOWS_ARTIFACT else {"other.txt": b"other platform bytes"}
        archive = zip_bytes(contents)
        archives[artifact_id] = archive
        records.append({
            "id": artifact_id, "name": label, "archive_digest": f"sha256:{sha256(archive)}",
            "size_in_bytes": len(archive),
            "files": [{"path": name, "size": len(body), "sha256": sha256(body)}
                      for name, body in sorted(contents.items(), key=lambda item: item[0].casefold())],
        })
    windows = next(row for row in records if row["name"] == source.WINDOWS_ARTIFACT)
    if defect == "windows-entry-mismatch":
        next(entry for entry in windows["files"] if entry["path"] == MSI)["sha256"] = "a" * 64
    inventory = {
        "schema_version": core.LEGACY_SCHEMA_VERSION, "repository": REPO,
        "release_tag": TAG, "release_sha": SHA, "source_ref": f"refs/tags/{TAG}",
        "workflow": core.BUILD_WORKFLOW, "build_run_id": RUN, "build_run_attempt": 1,
        "artifacts": records, "runtime_reports": {
            target: {"artifact_id": artifact_id, "archive_digest": f"sha256:{'f' * 64}",
                     "sha256": "b" * 64, "size_bytes": 200}
            for artifact_id, target in enumerate(core.RUNTIME_REPORT_ARTIFACT_NAMES, 300)
        },
    }
    raw = core.canonical_json(inventory).encode()
    archive = zip_bytes({source.INVENTORY_FILE: raw})
    archives[INVENTORY] = archive
    pointer = source.InventoryPointer(RUN, INVENTORY, "sha256:" + ("0" * 64 if defect == "wrong-inventory-pin"
                                                                    else sha256(archive)))
    downloads = []
    attestations = []

    class GitHubFixture:
        def json(self, endpoint):
            if endpoint == f"git/ref/tags/{TAG}":
                return {"object": {"type": "commit", "sha": "b" * 40 if defect == "moved-tag" else SHA}}
            if endpoint == f"actions/runs/{RUN}":
                return {
                    "id": RUN, "run_attempt": 2 if defect == "rerun" else 1,
                    "head_branch": TAG, "head_sha": SHA, "status": "completed",
                    "event": "push", "path": core.BUILD_WORKFLOW,
                    "conclusion": "failure" if defect == "failed-run" else "success",
                    "repository": {"full_name": "other/project" if defect == "wrong-repository" else REPO},
                }
            artifact_id = int(endpoint.removeprefix("actions/artifacts/"))
            assert artifact_id in (INVENTORY, windows["id"])
            label = core.CANDIDATE_INVENTORY_ARTIFACT if artifact_id == INVENTORY else source.WINDOWS_ARTIFACT
            archive = archives[artifact_id]
            wrong_run = ((artifact_id == INVENTORY and defect == "cross-run-inventory")
                         or (artifact_id == windows["id"] and defect == "cross-run-windows-artifact"))
            return {"id": artifact_id, "name": label, "digest": f"sha256:{sha256(archive)}", "expired": False,
                    "size_in_bytes": len(archive), "workflow_run": {"id": RUN + wrong_run, "head_sha": SHA}}

        def download(self, endpoint, destination, *, max_bytes=core.MAX_ARCHIVE_BYTES):
            artifact_id = int(endpoint.split("/")[2])
            assert artifact_id in (INVENTORY, windows["id"]) and endpoint.endswith("/zip")
            downloads.append(artifact_id)
            contents = archives[artifact_id] + (b"wrong" if defect == "wrong-zip-bytes" else b"")
            assert len(contents) <= max_bytes and not destination.exists()
            destination.write_bytes(contents)
            return f"sha256:{sha256(contents)}"

    def verify_cli(command, *, check, capture_output, timeout):
        assert command[:3] == ["gh", "attestation", "verify"] and check is False and capture_output and timeout
        assert "--deny-self-hosted-runners" in command
        assert command[command.index("--signer-workflow") + 1] == f"{REPO}/{core.BUILD_WORKFLOW}"
        assert command[command.index("--source-ref") + 1] == f"refs/tags/{TAG}"
        assert command[command.index("--source-digest") + 1] == SHA
        assert (tmp_path / TAG / source.INVENTORY_FILE).read_bytes() == raw
        assert downloads == [INVENTORY]
        attestations.append(command)
        certificate = {
            "sourceRepositoryURI": f"https://github.com/{REPO}",
            "sourceRepositoryRef": f"refs/tags/{TAG}",
            "sourceRepositoryDigest": SHA,
            "buildTrigger": "push",
            "runnerEnvironment": "self-hosted" if defect == "self-hosted-attestation" else "github-hosted",
            "runInvocationURI": f"https://github.com/{REPO}/actions/runs/{RUN}/attempts/"
                                f"{2 if defect == 'wrong-attestation-attempt' else 1}",
        }
        response = [{"verificationResult": {
            "verifiedTimestamps": [{"uri": "witness"}],
            "signature": {"certificate": certificate},
            "statement": {"predicateType": "https://slsa.dev/provenance/v1",
                          "subject": [{"digest": {"sha256": sha256(raw)}}]},
        }}]
        return SimpleNamespace(returncode=0, stdout=json.dumps(response).encode())

    monkeypatch.setattr(core.subprocess, "run", verify_cli)
    if message:
        with pytest.raises(ValueError, match=message):
            source.materialize_msi(GitHubFixture(), REPO, tmp_path, TAG, SHA, pointer)
        assert not (tmp_path / TAG / "assets").exists()
    else:
        path, file, receipt = source.materialize_msi(GitHubFixture(), REPO, tmp_path, TAG, SHA, pointer)
        assert path.name == MSI and path.read_bytes() == payloads[MSI]
        assert file["sha256"] == sha256(payloads[MSI])
        assert receipt == {
            "kind": "sealed-candidate", "build_run_id": RUN, "build_run_attempt": 1,
            "inventory_artifact_id": INVENTORY, "inventory_archive_digest": pointer.archive_digest,
            "inventory_sha256": sha256(raw), "native_artifact_id": windows["id"],
            "native_archive_digest": windows["archive_digest"],
        }
    assert downloads == [INVENTORY, windows["id"]][:download_count]
    assert len(attestations) == int(download_count > 0 and defect != "wrong-zip-bytes")

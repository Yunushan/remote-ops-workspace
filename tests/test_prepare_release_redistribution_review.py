from __future__ import annotations

import hashlib
import io
import json
import zipfile

import pytest

from scripts import prepare_release_redistribution_review as review
from scripts import release_candidate_inventory as candidate
from scripts import release_candidate_source as source
from scripts.check_release_license_compliance import read_fully_hashed_lock
from scripts.check_release_version import read_project_version
from scripts.managed_debian_qualification import SCHEMA as DEBIAN_RECEIPT_SCHEMA

REPO = "owner/project"
SHA = "a" * 40
RUN_ID = 100
INVENTORY_ID = 200


def digest(raw):
    return hashlib.sha256(raw).hexdigest()


def archive(name, data):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as zipped:
        zipped.writestr(name, data)
    return stream.getvalue()


@pytest.mark.parametrize(("defect", "error"), [
    ("none", ""),
    ("wrong-run", "is not bound to the approved build run"),
    ("wrong-archive", "archive does not match GitHub"),
    ("wrong-sealed-payload", "pip inspect bytes do not match the sealed inventory"),
    ("wrong-distributions", "runtime distributions differ"),
    ("wrong-package", "raw ZIP digest must be"),
    ("wrong-qualification-controller", "managed Debian controller digest differs"),
    ("wrong-qualification-archive", "archive does not match GitHub"),
    ("wrong-qualification-receipt", "does not match the sealed inventory"),
    ("moved-tag", "live release tag does not resolve"),
    ("source-changed", "tracked files changed"),
])
def test_review_captures_exact_candidate_and_all_runtime_inputs(tmp_path, monkeypatch, defect, error):
    destination = tmp_path / "review"
    version_errors = []
    version = read_project_version(review.ROOT / "pyproject.toml", version_errors)
    assert version and not version_errors
    tag = f"v{version}"
    policy = (review.ROOT / review.POLICY_FILE).read_bytes()
    lock_paths = review.review_locks(policy)
    assert lock_paths.keys() == candidate.RUNTIME_REPORT_ARTIFACT_NAMES.keys()
    archives = {}
    metadata = {}
    files = {}
    raw_reports = {}
    reports = {}
    package_artifacts = []
    bad_report_id = 300

    def fixture(artifact_id, label, filename, raw):
        data = archive(filename, raw)
        archives[artifact_id] = data
        metadata[artifact_id] = {
            "id": artifact_id, "name": label, "expired": False, "digest": f"sha256:{digest(data)}",
            "size_in_bytes": len(data), "workflow_run": {"id": RUN_ID, "head_sha": SHA},
        }
        return metadata[artifact_id]["digest"]

    for artifact_id, (target, label) in enumerate(sorted(candidate.RUNTIME_REPORT_ARTIFACT_NAMES.items()), 300):
        pinned, errors = read_fully_hashed_lock(review.ROOT, {"file": lock_paths[target]}, target)
        assert pinned and not errors
        installed = {**pinned, "remote-ops-workspace": version}
        if defect == "wrong-distributions" and artifact_id == bad_report_id:
            installed["not-in-the-lock"] = "1.0.0"
        raw = (json.dumps({
            "installed": [{"metadata": {"name": name, "version": v}} for name, v in installed.items()],
            "version": "1",
        }, indent=3) + "\n").encode()
        raw_reports[target] = raw
        report_digest = fixture(artifact_id, label, candidate.RUNTIME_REPORT_NAME, raw)
        if defect == "wrong-run" and artifact_id == bad_report_id:
            metadata[artifact_id]["workflow_run"]["id"] += 1
        reports[target] = {
            "artifact_id": artifact_id, "archive_digest": report_digest, "size_bytes": len(raw),
            "sha256": "0" * 64 if defect == "wrong-sealed-payload" and artifact_id == bad_report_id else digest(raw),
        }

    deb_name = f"remote-ops-workspace-{tag}-linux-amd64.deb"
    for artifact_id, label in enumerate(sorted(candidate.EXPECTED_ARTIFACT_NAMES), 400):
        filename, raw = f"{label}.txt", f"immutable fixture {label}\n".encode()
        if label == "release-linux-native-x86_64":
            filename = deb_name
        files[filename] = raw
        archive_digest = fixture(artifact_id, label, filename, raw)
        package_artifacts.append({
            "id": artifact_id, "name": label, "archive_digest": archive_digest,
            "size_in_bytes": metadata[artifact_id]["size_in_bytes"],
            "files": [{"path": filename, "size": len(raw), "sha256": digest(raw)}],
        })

    pins = json.loads((review.ROOT / "configs/native_linux_previous_release_pins.json").read_bytes())
    previous_name = f"remote-ops-workspace-{pins['tag']}-linux-amd64.deb"
    previous = next(row["digest"].removeprefix("sha256:") for row in pins["assets"] if row["name"] == previous_name)
    deb_digest = digest(files[deb_name])
    fault_digest = "f" * 64
    receipts = {name: {"phase": "authenticated-staged", "exit_code": 0}
                for name in ("previous", "candidate", "failing", "interrupted", "dependency-blocked")}
    receipts.update({
        "candidate-apply": {"phase": "applied", "exit_code": 0, "architecture": "amd64",
                            "candidate_sha256": deb_digest, "previous_sha256": previous,
                            "candidate_version": version, "previous_version": pins["tag"][1:], "action": "update"},
        "explicit-rollback": {"phase": "rolled-back", "exit_code": 0},
        "changed-launcher-rollback": {"phase": "refused", "exit_code": 1,
                                      "refusal": "installed-launcher-digest-refused"},
        "failing-apply": {"phase": "rolled-back", "exit_code": 1, "candidate_sha256": fault_digest},
        "interrupted-apply": {"phase": "rolled-back", "exit_code": 1, "action": "update",
                              "previous_sha256": previous},
        "automatic-candidate": {"phase": "applied", "exit_code": 0, "action": "update",
                                "previous_sha256": previous, "candidate_sha256": deb_digest},
        "automatic-failing": {"phase": "rolled-back", "exit_code": 1, "action": "update",
                              "previous_sha256": previous, "candidate_sha256": fault_digest},
        "automatic-explicit-rollback": {"phase": "rolled-back", "exit_code": 0, "action": "rollback",
                                        "previous_sha256": previous, "candidate_sha256": deb_digest},
        "dependency-blocked-apply": {
            "action": "apply", "phase": "refused", "exit_code": 1,
            "refusal": "debian-upgrade-plan-refused", "previous_sha256": previous,
            "candidate_sha256": digest(b"fixture candidate with unavailable dependency"),
            "previous_installation_unchanged": True, "journal_created": False,
        },
    })
    rollback = {"action": "rollback", "phase": "rolled-back", "exit_code": 0,
                "previous_sha256": previous, "candidate_sha256": deb_digest,
                "previous_launcher_sha256": "e" * 64}
    receipts["candidate-apply"]["previous_launcher_sha256"] = "e" * 64
    receipts["dependency-blocked-rollback"] = {
        "phase": "refused", "exit_code": 1, "action": "rollback", "refusal": "debian-rollback-plan-refused",
        "previous_sha256": previous, "candidate_sha256": deb_digest,
        "candidate_installation_unchanged": True, "journal_unchanged": True,
    }
    receipts["dependency-blocked-update-retry"] = dict(receipts["candidate-apply"])
    receipts["explicit-rollback"] = rollback
    receipts["repeated-rollback"] = dict(rollback)
    receipts["rollback-interruption"] = {
        **rollback, "phase": "rolling-back", "exit_code": -15, "native_rollback_invocations": 1,
    }
    receipt = {
        "schema": DEBIAN_RECEIPT_SCHEMA, "status": "passed", "target": "linux-x86_64", "production_acceptance": False,
        "previous_sha256": previous, "candidate_sha256": deb_digest, "candidate_has_server_bundle": False,
        "controller_sha256": (
            "c" * 64 if defect == "wrong-qualification-controller" else
            digest((review.ROOT / "scripts/managed_linux_update.py").read_bytes())
        ),
        "source_archive_sha256": "d" * 64, "receipts": receipts,
        "download_server_closed_before_apply": True, "workspace_unchanged": True,
        "source_sha": SHA, "run_id": str(RUN_ID), "run_attempt": "1",
        "container_image": candidate.MANAGED_IMAGE, "drill_image": candidate.MANAGED_IMAGE, "debian_depends": "",
    }
    receipt_bytes = candidate.qualification_receipt_bytes(receipt)
    archived_receipt = receipt_bytes if defect != "wrong-qualification-receipt" else receipt_bytes + b"\n"
    qualification_digest = fixture(500, candidate.MANAGED_DEBIAN_ARTIFACT, candidate.REPORT_NAME, archived_receipt)
    inventory = {
        "schema_version": candidate.MANAGED_SCHEMA_VERSION, "repository": REPO,
        "release_tag": tag, "release_sha": SHA, "source_ref": f"refs/tags/{tag}",
        "workflow": candidate.BUILD_WORKFLOW, "build_run_id": RUN_ID, "build_run_attempt": 1,
        "artifacts": package_artifacts, "runtime_reports": reports,
        "managed_debian_update": {
            "artifact_id": 500, "archive_digest": qualification_digest, "sha256": digest(receipt_bytes),
            "size_bytes": len(receipt_bytes), "receipt": receipt,
        },
    }
    inventory_bytes = (json.dumps(inventory, indent=2) + "\n").encode()
    inventory_digest = fixture(
        INVENTORY_ID, candidate.CANDIDATE_INVENTORY_ARTIFACT, source.INVENTORY_FILE, inventory_bytes,
    )
    pointer = source.InventoryPointer(RUN_ID, INVENTORY_ID, inventory_digest)
    downloads, source_checks, tag_checks, attestations = [], [], [], []

    class CandidateRepository:
        def json(self, endpoint):
            if endpoint == f"git/ref/tags/{tag}":
                tag_checks.append(endpoint)
                commit = "b" * 40 if defect == "moved-tag" and len(tag_checks) == 2 else SHA
                return {"object": {"type": "commit", "sha": commit}}
            if endpoint == f"actions/runs/{RUN_ID}":
                return {
                    "id": RUN_ID, "head_branch": tag, "head_sha": SHA, "status": "completed",
                    "event": "push", "conclusion": "success", "path": candidate.BUILD_WORKFLOW,
                    "repository": {"full_name": REPO}, "run_attempt": 1,
                }
            return metadata[int(endpoint.removeprefix("actions/artifacts/"))]

        def download(self, endpoint, path, *, max_bytes=candidate.MAX_ARCHIVE_BYTES):
            artifact_id = int(endpoint.removeprefix("actions/artifacts/").removesuffix("/zip"))
            downloads.append(artifact_id)
            raw = archives[artifact_id]
            if (defect, artifact_id) in (("wrong-archive", bad_report_id), ("wrong-package", 400)):
                raw += b"tamper"
            if defect == "wrong-qualification-archive" and artifact_id == 500:
                raw += b"tamper"
            assert len(raw) <= max_bytes and not path.exists()
            path.write_bytes(raw)
            return f"sha256:{digest(raw)}"

    def check_source(sha):
        assert sha == SHA
        source_checks.append(sha)
        if defect == "source-changed" and len(source_checks) == 2:
            raise ValueError("tracked files changed")

    def attest(path, **expected):
        assert path.read_bytes() == inventory_bytes
        assert expected == {
            "repository": REPO, "release_tag": tag, "release_sha": SHA,
            "run_id": RUN_ID, "run_attempt": 1, "build_event": "push", "inventory_sha256": digest(inventory_bytes),
        }
        assert downloads == [INVENTORY_ID]
        attestations.append(expected)

    monkeypatch.setattr(review, "require_clean_source", check_source)
    monkeypatch.setattr(source, "verify_candidate_attestation", attest)
    client = CandidateRepository()
    if error:
        with pytest.raises(ValueError, match=error):
            review.prepare_review(client, destination, REPO, tag, SHA, pointer)
        assert not destination.exists() and not list(tmp_path.iterdir())
        assert len(attestations) == 1
        if defect in ("wrong-run", "wrong-archive", "wrong-sealed-payload", "wrong-distributions"):
            assert not any(400 <= item < 408 for item in downloads)
        if defect.startswith("wrong-qualification"):
            assert not any(300 <= item < 408 for item in downloads)
        return

    review.prepare_review(client, destination, REPO, tag, SHA, pointer)
    assert len(attestations) == 1 and len(tag_checks) == len(source_checks) == 2
    assert downloads == [INVENTORY_ID, 500, *range(300, 307), *range(400, 408)]
    assert {path.name: path.read_bytes() for path in (destination / "assets").iterdir()} == files
    assert not (destination / "release-evidence.json").exists()
    index = json.loads((destination / "review-materials.json").read_bytes())
    assert index["policy_sha256"] == digest(policy)
    assert index["candidate_inventory_source"]["archive_digest"] == inventory_digest
    assert index["candidate_inventory_source"]["schema_version"] == candidate.MANAGED_SCHEMA_VERSION
    assert (destination / "archives/release-candidate-inventory.zip").read_bytes() == archives[INVENTORY_ID]
    qualification = index["qualification_archives"][candidate.MANAGED_DEBIAN_ARTIFACT]
    assert (destination / qualification["file"]).read_bytes() == archives[500]
    assert qualification["sha256"] == qualification_digest.removeprefix("sha256:")
    bundle = destination / "bundle"
    assert (bundle / source.INVENTORY_FILE).read_bytes() == inventory_bytes
    assert index["candidate_inventory"]["sha256"] == digest(inventory_bytes)
    for target, report in index["modern_targets"].items():
        realized = report["realized_environment"]
        resolver_lock = report["resolver_lock"]
        assert realized["format"] == "pip-inspect-v1"
        assert (bundle / realized["file"]).read_bytes() == raw_reports[target]
        assert realized["sha256"] == digest(raw_reports[target])
        assert resolver_lock["source_file"] == lock_paths[target]
        assert (bundle / resolver_lock["file"]).read_bytes() == (review.ROOT / lock_paths[target]).read_bytes()
        artifact = destination / "archives" / f"{candidate.RUNTIME_REPORT_ARTIFACT_NAMES[target]}.zip"
        assert artifact.read_bytes() == archives[reports[target]["artifact_id"]]

    with pytest.raises(ValueError, match="must be a new directory"):
        review.prepare_review(client, destination, REPO, tag, SHA, pointer)
    assert (bundle / source.INVENTORY_FILE).read_bytes() == inventory_bytes


def test_review_lock_must_be_the_lock_consumed_by_the_tagged_target():
    policy = json.loads((review.ROOT / review.POLICY_FILE).read_bytes())
    locks = policy["build_lock_enforcement"]["platform_locks"]
    locks["windows-x64"] = locks["windows-arm64"]
    with pytest.raises(ValueError, match="windows-x64 compliance policy lock must match the release build matrix"):
        review.review_locks(json.dumps(policy).encode())

from __future__ import annotations

import hashlib
import io
import json
import subprocess
import zipfile
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import fetch_qualification_release_asset as fetch
from scripts import qualify_windows_msi_upgrade as upgrade
from scripts import release_candidate_inventory as core
from scripts import release_candidate_source as source

REPO = upgrade.REPOSITORY
TAG = "v1.0.29"
SHA = "a" * 40
RUN = 123
INVENTORY = 100
ASSETS = [
    ("windows-msi", "release-windows-native-x64", f"remote-ops-workspace-{TAG}-windows-x64.msi"),
    ("wheel", "release-source-python", "remote_ops_workspace-1.0.29-py3-none-any.whl"),
    ("debian-amd64", "release-linux-native-x86_64", f"remote-ops-workspace-{TAG}-linux-amd64.deb"),
]


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


@pytest.mark.parametrize(("kind", "owner", "filename"), ASSETS)
@pytest.mark.parametrize(("defect", "message", "download_count"), [
    ("valid", "", 2),
    ("current-valid", "", 2),
    ("current-stale-manifest", "size or digest differs from extracted archive file", 2),
    ("current-foreign-checksum", "foreign, repeated or mismatched checksum", 2),
    ("moved-tag", "live release tag", 0),
    ("failed-run", "completed successfully", 0),
    ("rerun", "run_attempt must be", 0),
    ("wrong-repository", "different repository", 0),
    ("cross-run-inventory", "not bound to the approved build run", 0),
    ("wrong-inventory-pin", "live digest", 0),
    ("wrong-zip-bytes", "archive does not match GitHub", 1),
    ("self-hosted-attestation", "lacks a witnessed exact-tag attestation", 1),
    ("wrong-attestation-attempt", "lacks a witnessed exact-tag attestation", 1),
    ("missing-file", "must contain exactly one", 1),
    ("cross-run-payload", "not bound to the approved build run", 1),
    ("payload-entry-mismatch", "bytes/metadata do not match approved inventory", 2),
])
def test_resolves_only_asset_from_exact_attested_build(
    tmp_path, monkeypatch, kind, owner, filename, defect, message, download_count,
):
    current = defect.startswith("current-")
    archive_files = core.expected_candidate_archive_files(TAG) if current else {}
    payloads = {filename: b"asset fixture", "manifest.json": b"manifest fixture"}
    if current:
        manifest, = (name for name in archive_files[owner] if name.endswith("-manifest.json"))
        checksum, = (name for name in archive_files[owner] if name.endswith("-SHA256SUMS.txt"))
        payloads = {
            name: b"asset fixture" if name == filename else name.encode()
            for name in sorted(archive_files[owner] - {manifest, checksum})
        }
        entries = [
            {
                "file": name, "size_bytes": len(body),
                "sha256": "a" * 64 if defect == "current-stale-manifest" and name == filename else sha256(body),
            }
            for name, body in payloads.items()
        ]
        payloads[manifest] = json.dumps({"artifacts": entries} if kind == "wheel" else entries).encode()
        payloads[checksum] = "".join(
            f"{sha256(body)}  "
            f"{'foreign-release-material.txt' if defect == 'current-foreign-checksum' and name == filename else name}\n"
            for name, body in payloads.items()
        ).encode()

        def validate_current_scope(document, **coordinates):
            # The managed Debian and installer smoke receipts have separate fixtures.
            assert document["schema_version"] == core.ARCHIVE_FILE_SCOPE_SCHEMA_VERSION
            records = core.validate_inventory({**document, "schema_version": core.LEGACY_SCHEMA_VERSION}, **coordinates)
            core.require_candidate_archive_files(records, archive_files)
            return records

        monkeypatch.setattr(source, "validate_inventory", validate_current_scope)
    if defect == "missing-file":
        payloads.pop(filename)
    archives = {}
    records = []
    for artifact_id, label in enumerate(sorted(core.EXPECTED_ARTIFACT_NAMES), 200):
        if label == owner:
            contents = payloads
        elif current:
            contents = {name: name.encode() for name in sorted(archive_files[label])}
        else:
            contents = {"other.txt": b"other platform bytes"}
        archive = zip_bytes(contents)
        archives[artifact_id] = archive
        records.append({
            "id": artifact_id, "name": label, "archive_digest": f"sha256:{sha256(archive)}",
            "size_in_bytes": len(archive),
            "files": [{"path": name, "size": len(body), "sha256": sha256(body)}
                      for name, body in sorted(contents.items(), key=lambda item: item[0].casefold())],
        })
    selected = next(row for row in records if row["name"] == owner)
    if defect == "payload-entry-mismatch":
        next(entry for entry in selected["files"] if entry["path"] == filename)["sha256"] = "a" * 64
    inventory = {
        "schema_version": core.ARCHIVE_FILE_SCOPE_SCHEMA_VERSION if current else core.LEGACY_SCHEMA_VERSION,
        "repository": REPO,
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
            assert artifact_id in (INVENTORY, selected["id"])
            label = core.CANDIDATE_INVENTORY_ARTIFACT if artifact_id == INVENTORY else owner
            archive = archives[artifact_id]
            wrong_run = ((artifact_id == INVENTORY and defect == "cross-run-inventory")
                         or (artifact_id == selected["id"] and defect == "cross-run-payload"))
            return {"id": artifact_id, "name": label, "digest": f"sha256:{sha256(archive)}", "expired": False,
                    "size_in_bytes": len(archive), "workflow_run": {"id": RUN + wrong_run, "head_sha": SHA}}

        def download(self, endpoint, destination, *, max_bytes=core.MAX_ARCHIVE_BYTES):
            artifact_id = int(endpoint.split("/")[2])
            assert artifact_id in (INVENTORY, selected["id"]) and endpoint.endswith("/zip")
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
            source.materialize_asset(GitHubFixture(), REPO, tmp_path, TAG, SHA, pointer, kind=kind)
        assert not (tmp_path / TAG / "assets").exists()
    else:
        path, file, receipt = source.materialize_asset(GitHubFixture(), REPO, tmp_path, TAG, SHA, pointer, kind=kind)
        assert path.name == filename and path.read_bytes() == payloads[filename]
        assert file["sha256"] == sha256(payloads[filename])
        assert receipt == {
            "kind": "sealed-candidate", "build_run_id": RUN, "build_run_attempt": 1,
            "inventory_artifact_id": INVENTORY, "inventory_archive_digest": pointer.archive_digest,
            "inventory_sha256": sha256(raw), "native_artifact_id": selected["id"],
            "native_archive_digest": selected["archive_digest"],
        }
    assert downloads == [INVENTORY, selected["id"]][:download_count]
    assert len(attestations) == int(download_count > 0 and defect != "wrong-zip-bytes")


@pytest.mark.parametrize("qualified", [True, False])
def test_published_download_is_exposed_only_after_provenance(tmp_path, monkeypatch, qualified):
    kind, _, filename = ASSETS[1]
    calls = []

    def run(argv, *, check, timeout):
        calls.append(argv)
        assert check and timeout == 300
        assert not (tmp_path / filename).exists()
        if argv[:3] == ["gh", "release", "download"]:
            assert argv[3:-1] == [TAG, "--repo", REPO, "--pattern", filename, "--dir"]
            (Path(argv[-1]) / filename).write_bytes(b"wheel")
        else:
            assert Path(argv[2]).name == "check_release_provenance.py"
            assert Path(argv[4]).read_bytes() == b"wheel"
            assert argv[5:] == ["--repository", REPO, "--tag", TAG, "--sha", SHA]
            if not qualified:
                raise subprocess.CalledProcessError(1, argv)

    monkeypatch.setattr(fetch.subprocess, "run", run)
    if qualified:
        result = fetch.fetch_asset(REPO, TAG, SHA, kind, tmp_path, None)
        assert result.read_bytes() == b"wheel" and list(tmp_path.iterdir()) == [result]
    else:
        with pytest.raises(subprocess.CalledProcessError):
            fetch.fetch_asset(REPO, TAG, SHA, kind, tmp_path, None)
        assert not list(tmp_path.iterdir())
    assert len(calls) == 2


@pytest.mark.parametrize("valid_pointer", [True, False])
def test_sealed_candidate_cli_never_falls_back_to_a_release(tmp_path, monkeypatch, capsys, valid_pointer):
    kind, _, filename = ASSETS[2]
    coordinates = f"{RUN} {INVENTORY} sha256:{'a' * 64}" if valid_pointer else "  "
    monkeypatch.setenv("ROW_QUALIFICATION_CANDIDATE_INVENTORY", coordinates)
    monkeypatch.setenv("GH_TOKEN", "fixture")
    monkeypatch.setattr(fetch.subprocess, "run", lambda *_args, **_kwargs: pytest.fail("fell back to published download"))
    monkeypatch.setattr(fetch, "GitHubClient", lambda *_args, **_kwargs: "fixture-client")

    def materialize(client, repository, staging, tag, sha, pointer, *, kind):
        assert (client, repository, tag, sha, kind) == ("fixture-client", REPO, TAG, SHA, "debian-amd64")
        assert pointer == source.InventoryPointer.parse(coordinates)
        asset = staging / filename
        asset.write_bytes(b"verified Debian fixture")
        return asset, {}, {}

    monkeypatch.setattr(fetch, "materialize_asset", materialize)
    status = fetch.main(["--kind", kind, "--directory", str(tmp_path), "--repository", REPO, "--tag", TAG, "--sha", SHA])
    if valid_pointer:
        assert status == 0 and (tmp_path / filename).read_bytes() == b"verified Debian fixture"
        assert "from sealed build run" in capsys.readouterr().out
    else:
        assert status == 1 and not list(tmp_path.iterdir())
        assert "expected candidate inventory coordinates" in capsys.readouterr().err

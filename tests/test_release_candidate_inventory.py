from __future__ import annotations

import hashlib
import io
import json
import re
import stat
import sys
import urllib.error
import zipfile
from email.message import Message
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SCRIPTS = ROOT / "scripts"
if str(SCRIPTS) not in sys.path:
    sys.path.insert(0, str(SCRIPTS))

import release_candidate_inventory as candidate  # noqa: E402

from scripts import qualify_rpm_candidate as rpm_qualification  # noqa: E402


@pytest.mark.parametrize(
    "name",
    [
        "parent/file", "../escape", "..\\escape", "C:escape", "empty/",
        "installer.exe.", "native?.pkg", "NUL.txt", "COM¹.log", "Lpt2 .txt",
    ],
)
def test_candidate_zip_rejects_unsafe_entries_before_writing(
    tmp_path: Path, name: str,
) -> None:
    source = tmp_path / "candidate.zip"
    destination = tmp_path / "unpacked"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("installer.exe", b"fixture")
        archive.writestr(name, b"")

    with pytest.raises(ValueError, match="at ZIP root"):
        candidate.extract_archive(source, destination)

    assert not destination.exists()


@pytest.mark.parametrize(
    ("bad_entry", "options", "expected"),
    [
        ("INSTALLER.EXE", {}, "case-colliding"),
        ("inventory.json", {"only_name": "installer.exe"}, "must contain only"),
        ("other.exe", {"max_expanded_bytes": 8}, "expands beyond"),
    ],
)
def test_candidate_zip_rejects_invalid_inventory_before_writing(
    tmp_path: Path, bad_entry: str, options: dict, expected: str,
) -> None:
    source = tmp_path / "candidate.zip"
    destination = tmp_path / "unpacked"
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr("installer.exe", b"fixture")
        archive.writestr(bad_entry, b"fixture")

    with pytest.raises(ValueError, match=expected):
        candidate.extract_archive(source, destination, **options)

    assert not destination.exists()


def test_candidate_zip_rejects_non_regular_members(tmp_path: Path) -> None:
    source = tmp_path / "candidate.zip"
    destination = tmp_path / "unpacked"
    member = zipfile.ZipInfo("installer.exe")
    member.create_system = 3
    member.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(source, "w") as archive:
        archive.writestr(member, "outside")

    with pytest.raises(ValueError, match="non-regular"):
        candidate.extract_archive(source, destination)

    assert not destination.exists()


@pytest.mark.parametrize("existing_root", [False, True])
def test_candidate_staging_can_retry_after_a_later_archive_fails(
    tmp_path: Path, existing_root: bool,
) -> None:
    root = tmp_path / "assets"
    if existing_root:
        root.mkdir()
    artifacts = {}
    archives = {}
    for artifact_id, name in enumerate(("first", "second"), start=1):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            archive.writestr(f"{name}.txt", name)
        raw = stream.getvalue()
        artifacts[name] = {
            "id": artifact_id,
            "digest": f"sha256:{hashlib.sha256(raw).hexdigest()}",
            "size_in_bytes": len(raw),
            "expired": False,
        }
        archives[f"actions/artifacts/{artifact_id}/zip"] = raw

    class BuildRun:
        def download(self, endpoint: str, destination: Path) -> str:
            raw = archives[endpoint]
            destination.write_bytes(raw)
            return f"sha256:{hashlib.sha256(raw).hexdigest()}"

    client = BuildRun()
    second_digest = artifacts["second"]["digest"]
    artifacts["second"]["digest"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="artifact second raw ZIP digest"):
        candidate.materialize_records(client, artifacts, root)

    assert list(tmp_path.iterdir()) == ([root] if existing_root else [])
    if existing_root:
        assert not list(root.iterdir())
    artifacts["second"]["digest"] = second_digest
    assert [record["name"] for record in candidate.materialize_records(client, artifacts, root)] == [
        "first", "second",
    ]
    assert {path.name: path.read_text() for path in root.iterdir()} == {
        "first.txt": "first", "second.txt": "second",
    }


def test_expected_gui_smoke_artifacts_match_the_signed_build_matrix() -> None:
    workflow = (ROOT / candidate.BUILD_WORKFLOW).read_text(encoding="utf-8")
    expected = set()
    for platform, label, condition in (
        ("windows", "Windows", "if: ${{ always() && matrix.arch != 'x86' }}"),
        ("macos", "macOS", "if: always()"),
    ):
        job = re.search(
            rf"(?ms)^  {platform}-native:\n(.*?)(?=^  [\w-]+:\n|\Z)",
            workflow,
        )
        assert job is not None
        matrix, steps = job[1].split("    steps:", 1)
        architectures = re.findall(r"(?m)^          - arch: ([\w-]+)$", matrix)
        marker = f"      - name: Retain installed {label} GUI workflow evidence\n"
        smoke_step = steps.split(marker, 1)[1].split("\n      - ", 1)[0]
        assert condition in smoke_step
        assert f"name: release-{platform}-gui-smoke-${{{{ matrix.arch }}}}" in smoke_step
        expected.update(
            f"release-{platform}-gui-smoke-{arch}"
            for arch in architectures
            if (platform, arch) != ("windows", "x86")
        )
    assert expected == set(candidate.GUI_SMOKE_ARTIFACT_NAMES)


def test_release_workflow_qualifies_and_uploads_the_amd64_deb_before_inventory_sealing() -> None:
    source = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    job, sealer = source.split("  linux-native:\n", 1)[1].split("  seal-release-candidate:\n", 1)
    drill = job.split("- name: Qualify managed Debian upgrade and rollback", 1)[1].split("- name:", 1)[0]
    assert "matrix.arch == 'x86_64'" in drill
    assert "outputs.release_sha" in drill and "steps.debian-amd64-bundle.outputs.path != ''" in drill
    assert "scripts/native_linux_installer_recovery.py managed-release" in drill
    assert job.index("Run Linux native installer smoke tests") < job.index(drill)
    assert job.index(drill) < job.index(f"name: {candidate.MANAGED_DEBIAN_ARTIFACT}")
    assert f"path: build/native-smoke/linux-x86_64/{candidate.REPORT_NAME}" in job
    assert "needs.linux-native.result == 'success'" in sealer


def test_release_workflow_qualifies_and_uploads_the_smoke_bound_rpm() -> None:
    source = (ROOT / candidate.BUILD_WORKFLOW).read_text(encoding="utf-8")
    job = source.split("  linux-native:\n", 1)[1].split("  seal-release-candidate:\n", 1)[0]
    step = job.split("- name: Qualify the exact release RPM upgrade and rollback", 1)[1].split("- name:", 1)[0]
    bind = job.index("Bind the Linux x86-64 release checkout before packaging")
    build = job.index("Build Linux DEB, RPM and AppImage packages")
    smoke = job.index("Run Linux native installer smoke tests")
    assert bind < build < smoke < job.index(step) < job.index(f"name: {candidate.RPM_ARTIFACT}")
    assert "matrix.arch == 'x86_64'" in step
    assert "scripts/candidate_native_proof.py finish" in step
    assert "python -m scripts.qualify_rpm_candidate" in step
    assert f"path: build/candidate-proof/linux-x86_64/{candidate.RPM_REPORT_NAME}" in job


@pytest.mark.parametrize(
    ("condition", "error"),
    [
        ("complete", ""),
        ("missing-installer", "missing=.*release-source-python"),
        ("missing-smoke", "missing=.*release-macos-gui-smoke-x64"),
        ("missing-runtime", "missing=.*release-runtime-windows-x86"),
        ("missing-managed", "missing=.*release-managed-debian-update"),
        ("missing-rpm", "missing=.*release-linux-rpm-recovery"),
        ("wrong-managed-run", "managed Debian receipt does not match the release source and Actions attempt"),
        ("wrong-managed-deb", "managed Debian receipt must bind the exact candidate DEB"),
        ("missing-rollback", "managed-debian-receipt-binding-mismatch"),
        ("wrong-rpm-ref", "RPM recovery receipt does not match the release source and Actions attempt"),
        ("wrong-rpm-attempt", "RPM recovery receipt does not match the release source and Actions attempt"),
        ("wrong-rpm-digest", "RPM recovery receipt must bind the exact candidate RPM"),
        ("rpm-failed", "RPM recovery receipt has invalid package identities or rollback results"),
        ("complete-bundled", ""),
        ("wrong-runtime-run", "is not bound to the approved build run and SHA"),
        ("wrong-installer-sha", "artifact release-source-python is not bound to the approved build run and SHA"),
        ("bad-runtime-report", "must be a non-empty pip inspect v1 inventory"),
        ("nonregular-runtime-report", "artifact ZIP contains non-regular entry"),
        ("unknown-artifact", "unexpected=.*unexpected-build"),
        ("incomplete-listing", "artifact listing is incomplete"),
        ("expired-smoke", "artifact release-macos-gui-smoke-x64 live expired must be False"),
        ("wrong-smoke-run", "artifact release-macos-gui-smoke-x64 is not bound to the approved build run and SHA"),
        ("duplicate-smoke-id", "run artifact ID is duplicated"),
    ],
)
@pytest.mark.parametrize("event", ["push", "workflow_dispatch"])
def test_seal_requires_workflow_artifacts_and_keeps_smoke_reports_out_of_release(
    tmp_path: Path,
    condition: str,
    error: str,
    event: str,
) -> None:
    sha = "a" * 40
    tag = "v1.2.3"
    standard = (
        "release-source-python",
        "release-windows-native-x64",
        "release-windows-native-x86",
        "release-windows-native-arm64",
        "release-macos-native-x64",
        "release-macos-native-arm64",
        "release-linux-native-x86_64",
        "release-linux-native-aarch64",
    )
    smoke = (
        "release-windows-gui-smoke-x64",
        "release-windows-gui-smoke-arm64",
        "release-macos-gui-smoke-x64",
        "release-macos-gui-smoke-arm64",
    )
    runtime = tuple(sorted(candidate.RUNTIME_REPORT_ARTIFACT_NAMES.values()))
    names = [*standard, *smoke, *runtime, candidate.MANAGED_DEBIAN_ARTIFACT, candidate.RPM_ARTIFACT]
    if condition == "missing-installer":
        names.remove("release-source-python")
    if condition == "missing-smoke":
        names.remove("release-macos-gui-smoke-x64")
    if condition == "missing-runtime":
        names.remove("release-runtime-windows-x86")
    if condition == "missing-managed":
        names.remove(candidate.MANAGED_DEBIAN_ARTIFACT)
    if condition == "missing-rpm":
        names.remove(candidate.RPM_ARTIFACT)
    if condition == "unknown-artifact":
        names.append("unexpected-build")
    artifacts = []
    archives: dict[int, bytes] = {}
    raw_report = b'{"version":"1","installed":[{"metadata":{"name":"pip","version":"26.3"}}]}'
    deb_name = f"remote-ops-workspace-{tag}-linux-amd64.deb"
    deb_bytes = b"exact release Debian installer"
    deb_sha = "b" * 64 if condition == "wrong-managed-deb" else hashlib.sha256(deb_bytes).hexdigest()
    previous = "d64ef85359085440798b86515c4751e73ef2633a3cd761f93b6d168d4a8456af"
    steps = {name: {"phase": "authenticated-staged", "exit_code": 0}
             for name in ("previous", "candidate", "failing", "interrupted")}
    steps["candidate-apply"] = {"phase": "applied", "exit_code": 0, "architecture": "amd64",
                                "candidate_sha256": deb_sha, "previous_sha256": previous,
                                "candidate_version": "1.2.3", "previous_version": "1.0.24"}
    steps["explicit-rollback"] = {"phase": "rolled-back", "exit_code": 0}
    for name in ("failing-apply", "interrupted-apply"):
        steps[name] = {"phase": "rolled-back", "exit_code": 1}
    steps["changed-launcher-rollback"] = {"phase": "refused", "exit_code": 1,
                                          "refusal": "installed-launcher-digest-refused"}
    if condition == "missing-rollback":
        del steps["explicit-rollback"]
    bundled = condition == "complete-bundled"
    if bundled:
        steps["changed-server-manifest-rollback"] = {"phase": "refused", "exit_code": 1,
                                                    "refusal": "installed-runtime-payload-refused"}
    managed_report = candidate.qualification_receipt_bytes({
        "schema": "row.managed-debian-qualification.v1", "status": "passed", "target": "linux-x86_64",
        "production_acceptance": False, "candidate_has_server_bundle": bundled,
        "previous_sha256": previous, "candidate_sha256": deb_sha,
        "controller_sha256": "c" * 64, "source_archive_sha256": "d" * 64,
        "download_server_closed_before_apply": True, "workspace_unchanged": True,
        "source_sha": sha, "run_id": "224" if condition == "wrong-managed-run" else "123", "run_attempt": "1",
        "container_image": candidate.MANAGED_IMAGE,
        "drill_image": "sha256:" + "e" * 64 if bundled else candidate.MANAGED_IMAGE,
        "debian_depends": "libc6 (>= 2.38), libvncserver1" if bundled else "", "receipts": steps,
    })
    rpm_name = rpm_qualification.rpm_name(tag[1:])
    rpm_bytes = b"exact release RPM installer"
    rpm_sha = hashlib.sha256(rpm_bytes).hexdigest()
    rpm_report = candidate.qualification_receipt_bytes({
        "schema": rpm_qualification.SCHEMA, "target": "linux-x86_64",
        "source_commit": sha, "run_id": 123, "run_attempt": 2 if condition == "wrong-rpm-attempt" else 1,
        "workflow_ref": f"example/project/{candidate.BUILD_WORKFLOW}@refs/tags/"
                        + ("v1.2.2" if condition == "wrong-rpm-ref" else tag),
        "container_image": rpm_qualification.IMAGE, "previous_release_asset_id": rpm_qualification.PREVIOUS_ASSET,
        "previous_release_url": rpm_qualification.PREVIOUS_URL, "candidate_native_proof_sha256": "2" * 64,
        "receipt": {
            "schema": "remote-ops-workspace/rpm-recovery/v1",
            "backup_created_with": "verified-candidate-launcher-before-upgrade", "backup_sha256": "7" * 64,
            "previous": {"version": rpm_qualification.PREVIOUS_VERSION, "architecture": "x86_64",
                         "package_sha256": rpm_qualification.PREVIOUS_SHA256, "launcher_sha256": "8" * 64},
            "candidate": {"version": tag[1:], "architecture": "x86_64", "launcher_sha256": "9" * 64,
                          "package_sha256": "3" * 64 if condition == "wrong-rpm-digest" else rpm_sha},
            **{key: condition != "rpm-failed" for key in rpm_qualification.CHECKS},
        },
    })
    for artifact_id, name in enumerate(names, start=1):
        stream = io.BytesIO()
        with zipfile.ZipFile(stream, "w") as archive:
            if name in runtime:
                body = b"{}" if condition == "bad-runtime-report" else raw_report
                report = zipfile.ZipInfo(candidate.RUNTIME_REPORT_NAME)
                if condition == "nonregular-runtime-report":
                    report.create_system = 3
                    report.external_attr = (stat.S_IFIFO | 0o600) << 16
                archive.writestr(report, body)
            elif name == candidate.MANAGED_DEBIAN_ARTIFACT:
                archive.writestr(candidate.REPORT_NAME, managed_report)
            elif name == candidate.RPM_ARTIFACT:
                archive.writestr(candidate.RPM_REPORT_NAME, rpm_report)
            else:
                archive.writestr(f"{name}.txt", f"bytes from {name}")
                if name == "release-linux-native-x86_64":
                    archive.writestr(deb_name, deb_bytes)
                    archive.writestr(rpm_name, rpm_bytes)
        data = stream.getvalue()
        artifacts.append({
            "id": artifact_id,
            "name": name,
            "digest": f"sha256:{hashlib.sha256(data).hexdigest()}",
            "expired": condition == "expired-smoke" and name == "release-macos-gui-smoke-x64",
            "size_in_bytes": len(data),
            "workflow_run": {
                "id": 99 if condition == "wrong-runtime-run" and name in runtime else 123,
                "head_sha": "b" * 40 if condition == "wrong-installer-sha" and name == standard[0] else sha,
            },
        })
        if name in standard or name in runtime or name in {candidate.MANAGED_DEBIAN_ARTIFACT, candidate.RPM_ARTIFACT}:
            archives[artifact_id] = data
    smoke_artifact = next((item for item in artifacts if item["name"] == "release-macos-gui-smoke-x64"), None)
    if condition == "wrong-smoke-run":
        smoke_artifact["workflow_run"]["id"] = 99
    if condition == "duplicate-smoke-id":
        smoke_artifact["id"] = artifacts[0]["id"]
    downloads: list[int] = []

    class BuildRun:
        def json(self, endpoint: str) -> dict:
            if endpoint == "actions/runs/123":
                return {
                    "id": 123,
                    "run_attempt": 1,
                    "event": event,
                    "head_branch": tag,
                    "head_sha": sha,
                    "path": ".github/workflows/release.yml",
                    "repository": {"full_name": "example/project"},
                }
            assert endpoint == "actions/runs/123/artifacts?per_page=100"
            total_count = len(artifacts) + (1 if condition == "incomplete-listing" else 0)
            return {"total_count": total_count, "artifacts": artifacts}

        def download(self, endpoint: str, destination: Path, *, max_bytes: int = candidate.MAX_ARCHIVE_BYTES) -> str:
            artifact_id = int(endpoint.split("/")[2])
            assert endpoint == f"actions/artifacts/{artifact_id}/zip"
            downloads.append(artifact_id)
            data = archives[artifact_id]
            assert len(data) <= max_bytes
            destination.write_bytes(data)
            return f"sha256:{hashlib.sha256(data).hexdigest()}"

    root = tmp_path / "assets"
    output = tmp_path / "inventory.json"

    def seal() -> None:
        candidate.stage(
            BuildRun(),
            release_tag=tag,
            release_sha=sha,
            run_id=123,
            run_attempt=1,
            assets_root=root,
            output=output,
        )

    if error:
        with pytest.raises(ValueError, match=error):
            seal()
        if condition in {"wrong-managed-deb", "wrong-rpm-digest"}:
            assert len(downloads) == len(archives)
        elif condition in {"wrong-managed-run", "missing-rollback"}:
            assert len(downloads) == len(runtime) + 1
        elif condition in {"wrong-rpm-ref", "wrong-rpm-attempt", "rpm-failed"}:
            assert len(downloads) == len(runtime) + 2
        else:
            assert len(downloads) == (1 if condition in {"bad-runtime-report", "nonregular-runtime-report"} else 0)
        assert not root.exists()
        assert not output.exists()
        return

    seal()
    inventory = json.loads(output.read_text(encoding="utf-8"))
    records = candidate.validate_inventory(
        inventory, repository="example/project", release_tag=tag, release_sha=sha,
        run_id=123, run_attempt=1,
    )
    assert {record["name"] for record in records} == set(standard)
    assert {path.name for path in root.iterdir()} == {deb_name, rpm_name, *(f"{name}.txt" for name in standard)}
    assert len(downloads) == len(archives) and set(downloads) == set(archives)
    assert inventory["runtime_reports"].keys() == candidate.RUNTIME_REPORT_ARTIFACT_NAMES.keys()
    for report in inventory["runtime_reports"].values():
        assert report["sha256"] == hashlib.sha256(raw_report).hexdigest()
        assert report["size_bytes"] == len(raw_report)
    managed = inventory.pop("managed_debian_update")
    assert managed["sha256"] == hashlib.sha256(managed_report).hexdigest()
    assert managed["receipt"]["candidate_sha256"] == deb_sha
    assert managed["receipt"]["candidate_has_server_bundle"] is bundled
    rpm = inventory["rpm_recovery"]
    assert rpm["sha256"] == hashlib.sha256(rpm_report).hexdigest()
    assert rpm["receipt"]["receipt"]["candidate"]["package_sha256"] == rpm_sha
    coordinates = dict(repository="example/project", release_tag=tag, release_sha=sha, run_id=123, run_attempt=1)
    public_coordinates = {key: coordinates[key] for key in ("repository", "release_tag", "release_sha")}
    with pytest.raises(ValueError, match="managed Debian receipt is missing"):
        candidate.validate_inventory(inventory, **coordinates)
    # Historical inventory bytes remain readable when their tag's workflow
    # predated the managed Debian qualification.
    inventory.pop("rpm_recovery")
    inventory["schema_version"] = candidate.LEGACY_SCHEMA_VERSION
    candidate.validate_inventory(inventory, **coordinates)
    with pytest.raises(ValueError, match="requires the current sealed candidate inventory"):
        candidate.validate_managed_release_qualification(inventory, **public_coordinates, deb_sha256=deb_sha)
    inventory["schema_version"] = candidate.MANAGED_SCHEMA_VERSION
    inventory["managed_debian_update"] = managed
    candidate.validate_managed_release_qualification(inventory, **public_coordinates, deb_sha256=deb_sha)
    with pytest.raises(ValueError, match="must bind the exact candidate DEB"):
        candidate.validate_managed_release_qualification(inventory, **public_coordinates, deb_sha256="9" * 64)
    inventory["schema_version"] = candidate.SCHEMA_VERSION
    with pytest.raises(ValueError, match="RPM recovery receipt is missing"):
        candidate.validate_inventory(inventory, **coordinates)
    inventory["rpm_recovery"] = rpm
    rpm_id = rpm["artifact_id"]
    rpm["artifact_id"] = managed["artifact_id"]
    with pytest.raises(ValueError, match="RPM recovery report artifact id is duplicated"):
        candidate.validate_inventory(inventory, **coordinates)
    rpm["artifact_id"] = rpm_id
    inventory["runtime_reports"]["windows-x86"]["artifact_id"] = records[0]["id"]
    with pytest.raises(ValueError, match="runtime report windows-x86 artifact id is duplicated"):
        candidate.validate_inventory(
            inventory, repository="example/project", release_tag=tag, release_sha=sha,
            run_id=123, run_attempt=1,
        )


@pytest.mark.parametrize(
    ("event", "ref_name", "attempt", "error"),
    [
        ("pull_request", "v1.2.3", 1, "event must be"),
        ("workflow_dispatch", "main", 1, "head_branch must be"),
        ("workflow_dispatch", "v1.2.3", 2, "attempt must be exactly 1"),
    ],
)
def test_candidate_recovery_rejects_untrusted_runs(
    event: str, ref_name: str, attempt: int, error: str,
) -> None:
    run = {
        "id": 123,
        "run_attempt": attempt,
        "event": event,
        "head_branch": ref_name,
        "head_sha": "a" * 40,
        "path": candidate.BUILD_WORKFLOW,
        "repository": {"full_name": "example/project"},
    }
    with pytest.raises(ValueError, match=error):
        candidate.check_build_run(
            run,
            release_tag="v1.2.3",
            release_sha="a" * 40,
            run_id=123,
            run_attempt=attempt,
            require_success=False,
        )


@pytest.mark.parametrize("event", ["push", "workflow_dispatch"])
def test_candidate_attestation_binds_the_build_event(event: str) -> None:
    repository = "example/project"
    sha = "a" * 40
    digest = "b" * 64
    tag = "v1.2.3"
    certificate = {
        "sourceRepositoryURI": f"https://github.com/{repository}",
        "sourceRepositoryDigest": sha,
        "sourceRepositoryRef": f"refs/tags/{tag}",
        "runnerEnvironment": "github-hosted",
        "buildTrigger": event,
        "runInvocationURI": f"https://github.com/{repository}/actions/runs/123/attempts/1",
    }
    result = [{
        "verificationResult": {
            "verifiedTimestamps": [{"uri": "witness"}],
            "signature": {"certificate": certificate},
            "statement": {
                "predicateType": "https://slsa.dev/provenance/v1",
                "subject": [{"digest": {"sha256": digest}}],
            },
        },
    }]

    def verify() -> None:
        candidate.check_candidate_attestation_payload(
            result,
            repository=repository,
            release_tag=tag,
            release_sha=sha,
            run_id=123,
            run_attempt=1,
            inventory_sha256=digest,
            build_event=event,
        )

    verify()
    certificate["buildTrigger"] = "push" if event == "workflow_dispatch" else "workflow_dispatch"
    with pytest.raises(ValueError, match="lacks a witnessed exact-tag attestation"):
        verify()


def redirect_error(url: str, location: str) -> urllib.error.HTTPError:
    headers = Message()
    headers["Location"] = location
    return urllib.error.HTTPError(url, 302, "Found", headers, io.BytesIO(b""))


@pytest.mark.parametrize(
    ("failure", "message"),
    [
        ("redirect", "GitHub artifact download returned an unexpected second redirect"),
        ("http", "GitHub artifact download failed with HTTP 403"),
        ("connection", "GitHub artifact download failed to connect"),
    ],
)
def test_artifact_download_keeps_storage_credentials_out_of_errors(
    monkeypatch: pytest.MonkeyPatch, failure: str, message: str,
) -> None:
    requests: list[object] = []
    signed_url = "https://objects.githubusercontent.com/candidate.zip?sig=private-capability"

    class Opener:
        def open(self, request: object, timeout: int) -> object:
            del timeout
            requests.append(request)
            if len(requests) == 1:
                raise redirect_error(
                    "https://api.github.com/repos/acme/project/actions/artifacts/7/zip",
                    signed_url,
                )
            if failure == "redirect":
                raise redirect_error(signed_url, signed_url)
            if failure == "http":
                raise urllib.error.HTTPError(
                    signed_url, 403, "Forbidden", Message(), io.BytesIO(signed_url.encode()),
                )
            raise urllib.error.URLError(signed_url)

    opener = Opener()
    monkeypatch.setattr(candidate.urllib.request, "build_opener", lambda *_: opener)
    client = candidate.GitHubClient("acme/project", "top-secret")

    with pytest.raises(RuntimeError) as error:
        client._open("actions/artifacts/7/zip", allow_redirect=True)

    assert str(error.value) == message
    assert error.value.__suppress_context__
    assert len(requests) == 2
    first_headers = dict(requests[0].header_items())  # type: ignore[attr-defined]
    second_headers = dict(requests[1].header_items())  # type: ignore[attr-defined]
    assert first_headers["Authorization"] == "Bearer top-secret"
    assert "Authorization" not in second_headers


@pytest.mark.parametrize(
    "value",
    [
        ".github/workflows/release.yml",
        ".github/workflows/release.yml@v1.2.3",
        ".github/workflows/release.yml@refs/tags/v1.2.3",
    ],
)
def test_workflow_path_accepts_only_exact_tag_suffixes(value: str) -> None:
    assert candidate.workflow_path_matches(value, candidate.BUILD_WORKFLOW, "v1.2.3")


@pytest.mark.parametrize(
    "value",
    [
        ".github/workflows/release.yml@main",
        ".github/workflows/release.yml.evil@refs/tags/v1.2.3",
        "prefix/.github/workflows/release.yml@v1.2.3",
        ".github/workflows/release.yml@refs/tags/v1.2.30",
    ],
)
def test_workflow_path_rejects_branch_and_spoof_suffixes(value: str) -> None:
    assert not candidate.workflow_path_matches(value, candidate.BUILD_WORKFLOW, "v1.2.3")

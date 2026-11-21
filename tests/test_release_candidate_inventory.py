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

from scripts import (  # noqa: E402
    managed_debian_qualification,
    managed_rpm_qualification,
    prepare_release_redistribution_review,
    release_evidence_file,
)
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


@pytest.mark.parametrize("destination_changed", [False, True])
def test_publish_candidate_directory_checks_destination_after_windows_retry(tmp_path, monkeypatch, destination_changed):
    staged = tmp_path / "staging"
    destination = tmp_path / "assets"
    staged.mkdir()
    (staged / "candidate.rpm").write_bytes(b"verified candidate bytes")
    original_rename = Path.rename
    attempts = []

    def temporarily_denied(source, target):
        attempts.append(source)
        if len(attempts) == 1:
            error = PermissionError("rename denied")
            error.winerror = 5
            raise error
        return original_rename(source, target)

    def wait_for_retry(_delay):
        if destination_changed:
            destination.mkdir()

    monkeypatch.setattr(Path, "rename", temporarily_denied)
    monkeypatch.setattr(release_evidence_file.time, "sleep", wait_for_retry)
    if destination_changed:
        with pytest.raises(ValueError, match="assets root appeared"):
            candidate.publish_candidate_directory(staged, destination)
        assert len(attempts) == 1 and not list(destination.iterdir())
        assert (staged / "candidate.rpm").read_bytes() == b"verified candidate bytes"
    else:
        candidate.publish_candidate_directory(staged, destination)
        assert len(attempts) == 2 and not staged.exists()
        assert (destination / "candidate.rpm").read_bytes() == b"verified candidate bytes"


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


def test_tagged_release_verifies_the_reviewed_debian_bundle_before_fanning_out() -> None:
    source = (ROOT / candidate.BUILD_WORKFLOW).read_text(encoding="utf-8")
    preflight = source.split("  release-preflight:\n", 1)[1].split("  source-and-python:\n", 1)[0]
    selected, verifier = preflight.split(
        "      - name: Verify the reviewed Debian amd64 server bundle before candidate builds\n", 1,
    )
    selected = selected.split("      - name: Freeze the reviewed Debian amd64 server bundle selection\n", 1)[1]
    verifier = verifier.split("      - name:", 1)[0]
    gate = "if: ${{ steps.signing-readiness.outputs.candidate_build_ready == 'true' }}"
    assert gate in selected and gate in verifier
    assert "exit 0" not in selected
    assert 'vars.ROW_DEBIAN_AMD64_SERVER_BUNDLE' in selected
    assert "continue-on-error:" not in verifier
    assert "scripts/stage_debian_server_bundle.py" in verifier
    assert '--artifact-id "$SERVER_BUNDLE_ARTIFACT_ID" --sha256 "$SERVER_BUNDLE_SHA256"' in verifier
    for key in ("artifact_id", "sha256"):
        assert f"steps.debian-amd64-bundle.outputs.{key}" in verifier
    sealing = source.split("  seal-release-candidate:\n", 1)[1]
    assert "needs.release-preflight.outputs.debian_amd64_bundle_artifact_id" in sealing
    assert "needs.release-preflight.outputs.debian_amd64_bundle_sha256" in sealing
    assert '--server-bundle-artifact-id "$SERVER_BUNDLE_ARTIFACT_ID"' in sealing
    assert '--server-bundle-sha256 "$SERVER_BUNDLE_SHA256"' in sealing
    for job in ("source-and-python", "windows-native", "macos-native", "linux-native"):
        builder = source.split(f"  {job}:\n", 1)[1].split("    steps:", 1)[0]
        assert "needs: release-preflight" in builder
        assert "if: ${{ needs.release-preflight.outputs.candidate_build_ready == 'true' }}" in builder


def test_release_workflow_qualifies_and_uploads_the_amd64_deb_before_inventory_sealing() -> None:
    source = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    job, sealer = source.split("  linux-native:\n", 1)[1].split("  seal-release-candidate:\n", 1)
    drill = job.split("- name: Qualify managed Debian upgrade and rollback", 1)[1].split("- name:", 1)[0]
    assert "matrix.arch == 'x86_64'" in drill
    stage = job.split("      - name: Stage the reviewed Debian amd64 server bundle\n", 1)[1].split("      - name:", 1)[0]
    assert "if: ${{ matrix.arch == 'x86_64' }}" in stage
    for key in ("artifact_id", "sha256"):
        assert f"needs.release-preflight.outputs.debian_amd64_bundle_{key}" in stage
    assert "ROW_RELEASE_SERVER_BUNDLE: ${{ steps.debian-amd64-bundle.outputs.path }}" in job
    assert "outputs.release_sha" in drill and "--server-bundle true" in drill
    assert "scripts/native_linux_installer_recovery.py managed-release" in drill
    assert job.index("Run Linux native installer smoke tests") < job.index(drill)
    assert job.index(drill) < job.index(f"name: {candidate.MANAGED_DEBIAN_ARTIFACT}")
    assert f"path: build/native-smoke/linux-x86_64/{candidate.REPORT_NAME}" in job
    assert "needs.linux-native.result == 'success'" in sealer


def test_release_workflow_qualifies_and_uploads_the_smoke_bound_rpm() -> None:
    source = (ROOT / candidate.BUILD_WORKFLOW).read_text(encoding="utf-8")
    job = source.split("  linux-native:\n", 1)[1].split("  seal-release-candidate:\n", 1)[0]
    step = job.split("- name: Qualify the exact release RPM upgrade and rollback", 1)[1].split("- name:", 1)[0]
    binding = job.split("- name: Bind the Linux release checkout before packaging", 1)[1].split("- name:", 1)[0]
    bind = job.index(binding)
    build = job.index("Build Linux DEB, RPM and AppImage packages")
    smoke = job.index("Run Linux native installer smoke tests")
    verify = job.split("- name: Verify Linux installer smoke against the packaged build", 1)[1].split("- name:", 1)[0]
    retained = job.split("- name: Retain Linux native smoke evidence", 1)[1].split("- name:", 1)[0]
    assert bind < build < smoke < job.index(verify) < job.index(retained) < job.index(step)
    assert "matrix.arch == 'x86_64'" in step
    for marker in (binding, verify, retained):
        assert "if:" not in marker and "continue-on-error:" not in marker
        assert "matrix.arch" in marker
    assert "scripts/candidate_native_proof.py finish" in verify
    assert candidate.LINUX_SMOKE_PROOF_FILE in retained and candidate.NATIVE_BYTE_BINDING_FILE in retained
    assert "python -m scripts.qualify_rpm_candidate" in step
    assert "path: build/release-rpm-evidence/" in job
    assert all(name in step for name in (*candidate.RPM_SMOKE_FILES, candidate.RPM_REPORT_NAME))


@pytest.mark.parametrize(
    ("condition", "error"),
    [
        ("unbundled", "the production Debian candidate requires the embedded server bundle"),
        ("missing-installer", "missing=.*release-source-python"),
        ("missing-smoke", "missing=.*release-macos-gui-smoke-x64"),
        ("missing-linux-smoke", "missing=.*release-linux-native-smoke-aarch64"),
        ("wrong-linux-proof", "native proof does not bind the completed exact-run installer smoke receipt"),
        ("wrong-linux-package", "smoke receipt differs from the candidate installer"),
        ("swapped-native-manifests", "files differ from its release matrix assignment"),
        ("unexpected-source-file", "files differ from its release matrix assignment"),
        ("foreign-checksum-reference", "foreign, repeated or mismatched checksum"),
        ("repeated-checksum-reference", "foreign, repeated or mismatched checksum"),
        ("stale-native-manifest-digest", "size or digest differs from extracted archive file"),
        ("missing-native-manifest-row", "missing release file records"),
        ("missing-gui-proof", "archive must contain one root gui-archive-proof.json"),
        ("wrong-gui-binding", "GUI archive proof does not bind the completed smoke receipt"),
        ("missing-gui-module", "GUI archive proof must attest every required frozen GUI module"),
        ("unverified-gui-module", "GUI archive proof must attest every required frozen GUI module"),
        ("wrong-gui-path", "GUI archive proof must attest every required frozen GUI module"),
        ("wrong-gui-launcher", "GUI archive proof refers to different executable bytes"),
        ("wrong-gui-observation", "smoke did not observe the verified GUI executable bytes"),
        ("missing-gui-installers", "must bind the complete installer digest set"),
        ("wrong-gui-installer", "smoke receipt differs from the candidate installer"),
        ("missing-runtime", "missing=.*release-runtime-windows-x86"),
        ("missing-managed", "missing=.*release-managed-debian-update"),
        ("missing-rpm", "missing=.*release-linux-rpm-recovery"),
        ("missing-rpm-smoke", "archive must contain the exact evidence files"),
        ("wrong-managed-run", "managed Debian receipt does not match the release source and Actions attempt"),
        ("wrong-managed-controller", "managed Debian controller digest differs from the release checkout"),
        ("wrong-managed-deb", "managed Debian receipt must bind the exact candidate DEB"),
        ("wrong-managed-depends", "receipt Depends field differs from the candidate DEB"),
        ("wrong-managed-bundle", "receipt server bundle claim differs from the candidate DEB"),
        ("old-managed-schema", "managed-debian-receipt-binding-mismatch"),
        ("missing-rollback", "managed-debian-receipt-binding-mismatch"),
        ("wrong-rpm-ref", "RPM recovery receipt does not match the release source and Actions attempt"),
        ("wrong-rpm-attempt", "RPM recovery receipt does not match the release source and Actions attempt"),
        ("wrong-rpm-digest", "RPM recovery receipt must bind the exact candidate RPM"),
        ("wrong-rpm-smoke-sha", "RPM native proof refers to different workflow, package or smoke bytes"),
        ("changed-rpm-launcher", "RPM smoke did not observe the recovered candidate launcher"),
        ("rpm-failed", "RPM recovery receipt has invalid package identities or rollback results"),
        ("missing-managed-rpm", "requires the managed-update qualification"),
        ("old-managed-rpm", "must verify upgrade and rollback dependency-conflict recovery"),
        ("missing-rpm-dependency-check", "missing passing upgrade and rollback checks"),
        ("missing-rpm-rollback-dependency-check", "missing passing upgrade and rollback checks"),
        ("wrong-managed-rpm-controller", "missing its controller, feed, or dependency binding"),
        ("wrong-managed-rpm-lock", "missing its controller, feed, or dependency binding"),
        ("managed-rpm-failed", "missing passing upgrade and rollback checks"),
        ("wrong-managed-rpm-launcher", "refers to a different package or launcher"),
        ("wrong-managed-rpm-requests", "missing the ordered HTTPS downloads"),
        ("wrong-managed-rpm-rollback-count", "must record exactly one native installer invocation"),
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
    monkeypatch: pytest.MonkeyPatch,
    condition: str,
    error: str,
    event: str,
) -> None:
    sha = "a" * 40
    tag = "v1.2.3"
    expected_archive_files = candidate.expected_candidate_archive_files(tag)
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
    linux_smoke = candidate.LINUX_SMOKE_ARTIFACT_NAMES
    names = [*standard, *smoke, *linux_smoke, *runtime, candidate.MANAGED_DEBIAN_ARTIFACT, candidate.RPM_ARTIFACT]
    if condition == "missing-installer":
        names.remove("release-source-python")
    if condition == "missing-smoke":
        names.remove("release-macos-gui-smoke-x64")
    if condition == "missing-linux-smoke":
        names.remove("release-linux-native-smoke-aarch64")
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
    installers = {}
    for name in smoke:
        target = name.removeprefix("release-").replace("-gui-smoke-", "-", 1)
        suffixes = ("-native.zip", "-setup.exe", ".msi") if target.startswith("windows-") else (".dmg", ".pkg")
        installers[target] = {
            f"remote-ops-workspace-{tag}-{target}{suffix}": f"candidate bytes for {target}{suffix}".encode()
            for suffix in suffixes
        }
    raw_report = b'{"version":"1","installed":[{"metadata":{"name":"pip","version":"26.3"}}]}'
    deb_name = f"remote-ops-workspace-{tag}-linux-amd64.deb"
    deb_bytes = b"exact release Debian installer"
    deb_sha = "b" * 64 if condition == "wrong-managed-deb" else hashlib.sha256(deb_bytes).hexdigest()
    previous = "d64ef85359085440798b86515c4751e73ef2633a3cd761f93b6d168d4a8456af"
    previous_launcher = "7" * 64
    failing_sha = "f" * 64
    blocked_sha = "0" * 64
    steps = {name: {"phase": "authenticated-staged", "exit_code": 0}
             for name in ("previous", "candidate", "failing", "interrupted")}
    steps["candidate-apply"] = {"phase": "applied", "exit_code": 0, "architecture": "amd64",
                                "candidate_sha256": deb_sha, "previous_sha256": previous,
                                "candidate_version": "1.2.3", "previous_version": "1.0.24",
                                "action": "update", "previous_launcher_sha256": previous_launcher}
    rollback = {"action": "rollback", "phase": "rolled-back", "exit_code": 0,
                "previous_sha256": previous, "candidate_sha256": deb_sha,
                "previous_launcher_sha256": previous_launcher}
    steps.update({
        "explicit-rollback": rollback,
        "repeated-rollback": dict(rollback),
        "rollback-interruption": {
            **rollback, "phase": "rolling-back", "exit_code": -15, "native_rollback_invocations": 1,
        },
        "interrupted-apply": {"phase": "rolled-back", "exit_code": 1, "action": "update", "previous_sha256": previous},
        "failing-apply": {"phase": "rolled-back", "exit_code": 1, "candidate_sha256": failing_sha},
        "automatic-candidate": {"phase": "applied", "exit_code": 0, "action": "update",
                                "previous_sha256": previous, "candidate_sha256": deb_sha},
        "automatic-failing": {"phase": "rolled-back", "exit_code": 1, "action": "update",
                              "previous_sha256": previous, "candidate_sha256": failing_sha},
        "automatic-explicit-rollback": dict(rollback),
    })
    steps["dependency-blocked"] = {"phase": "authenticated-staged", "exit_code": 0}
    steps["dependency-blocked-apply"] = {
        "phase": "refused", "exit_code": 1, "action": "apply", "refusal": "debian-upgrade-plan-refused",
        "previous_sha256": previous, "candidate_sha256": blocked_sha,
        "previous_installation_unchanged": True, "journal_created": False,
    }
    if condition != "old-managed-schema":
        steps["dependency-blocked-rollback"] = {
            "phase": "refused", "exit_code": 1, "action": "rollback", "refusal": "debian-rollback-plan-refused",
            "previous_sha256": previous, "candidate_sha256": deb_sha,
            "candidate_installation_unchanged": True, "journal_unchanged": True,
        }
        steps["dependency-blocked-update-retry"] = dict(steps["candidate-apply"])
    steps["changed-launcher-rollback"] = {"phase": "refused", "exit_code": 1,
                                          "refusal": "installed-launcher-digest-refused"}
    if condition == "missing-rollback":
        del steps["explicit-rollback"]
    bundled = condition != "unbundled"
    if bundled:
        steps["changed-server-manifest-rollback"] = {"phase": "refused", "exit_code": 1,
                                                    "refusal": "installed-runtime-payload-refused"}
    depends = "libc6 (>= 2.38), libvncserver1" if bundled else "libc6 (>= 2.38), zlib1g"
    managed_report = candidate.qualification_receipt_bytes({
        "schema": managed_debian_qualification.UPGRADE_PLAN_SCHEMA if condition == "old-managed-schema" else
                  managed_debian_qualification.SCHEMA, "status": "passed", "target": "linux-x86_64",
        "production_acceptance": False, "candidate_has_server_bundle": bundled,
        "previous_sha256": previous, "candidate_sha256": deb_sha,
        "controller_sha256": (
            "c" * 64 if condition == "wrong-managed-controller" else
            hashlib.sha256((ROOT / candidate.MANAGED_DEBIAN_CONTROLLER).read_bytes()).hexdigest()
        ),
        "source_archive_sha256": "d" * 64,
        "download_server_closed_before_apply": True, "workspace_unchanged": True,
        "source_sha": sha, "run_id": "224" if condition == "wrong-managed-run" else "123", "run_attempt": "1",
        "container_image": candidate.MANAGED_IMAGE,
        "drill_image": "sha256:" + "e" * 64,
        "debian_depends": depends, "receipts": steps,
    })
    if condition == "old-managed-schema":
        historical = {
            "artifact_id": 99, "archive_digest": "sha256:" + "a" * 64,
            "sha256": hashlib.sha256(managed_report).hexdigest(), "size_bytes": len(managed_report),
            "receipt": json.loads(managed_report),
        }
        assert candidate.validate_managed_report(historical, tag, sha, 123, 1) == 99
    rpm_name = rpm_qualification.rpm_name(tag[1:])
    rpm_bytes = b"exact release RPM installer"
    rpm_sha = hashlib.sha256(rpm_bytes).hexdigest()
    claimed_rpm_sha = "3" * 64 if condition == "wrong-rpm-digest" else rpm_sha
    launcher = "9" * 64
    workflow_ref = f"example/project/{candidate.BUILD_WORKFLOW}@refs/tags/{tag}"
    binding = candidate.qualification_receipt_bytes({
        "target": "linux-x86_64", "schema_version": 1, "status": "bound", "smoke_complete": True,
        "expected_executables": [{"path": "build/native/linux/pyinstaller-dist/row", "role": "cli", "sha256": launcher}],
        "observations": [
            {"path": "rpm/usr/bin/row", "role": "cli", "matched": True, "phase": phase, "probe": probe,
             "expected_sha256": launcher,
             "observed_sha256": "a" * 64 if condition == "changed-rpm-launcher" else launcher}
            for phase in ("install", "reinstall")
            for probe in ("version", "platforms")
        ],
    })
    proof = candidate.qualification_receipt_bytes({
        "target": "linux-x86_64", "source": {"head": sha}, "run_id": "123", "run_attempt": "1",
        "workflow_ref": workflow_ref, "source_unchanged": True,
        "native_build_outcome": "success", "native_smoke_outcome": "success",
        "assets": [{"path": f"native-dist/linux/{rpm_name}", "sha256": claimed_rpm_sha, "size": len(rpm_bytes)}],
        "native_executable_byte_binding": {
            "status": "bound", "report_path": rpm_qualification.SMOKE_BINDING.as_posix(),
            "report_sha256": "4" * 64 if condition == "wrong-rpm-smoke-sha" else hashlib.sha256(binding).hexdigest(),
        },
    })
    rpm_native = {
        "schema": "remote-ops-workspace/rpm-recovery/v1",
        "backup_created_with": "verified-candidate-launcher-before-upgrade", "backup_sha256": "7" * 64,
        "previous": {"version": rpm_qualification.PREVIOUS_VERSION, "architecture": "x86_64",
                     "package_sha256": rpm_qualification.PREVIOUS_SHA256, "launcher_sha256": "8" * 64},
        "candidate": {"version": tag[1:], "architecture": "x86_64", "launcher_sha256": launcher,
                      "package_sha256": claimed_rpm_sha},
        **{key: condition != "rpm-failed" for key in rpm_qualification.CHECKS},
    }
    rpm_outer = {
        "schema": rpm_qualification.SCHEMA, "target": "linux-x86_64",
        "source_commit": sha, "run_id": 123, "run_attempt": 2 if condition == "wrong-rpm-attempt" else 1,
        "workflow_ref": f"example/project/{candidate.BUILD_WORKFLOW}@refs/tags/"
                        + ("v1.2.2" if condition == "wrong-rpm-ref" else tag),
        "container_image": rpm_qualification.IMAGE, "previous_release_asset_id": rpm_qualification.PREVIOUS_ASSET,
        "previous_release_url": rpm_qualification.PREVIOUS_URL,
        "candidate_native_proof_sha256": hashlib.sha256(proof).hexdigest(),
        "receipt": rpm_native,
    }
    if condition == "missing-managed-rpm":
        rpm_outer["schema"] = rpm_qualification.NATIVE_ONLY_SCHEMA
    else:
        rpm_outer["managed_update"] = {
            "schema": managed_rpm_qualification.SCHEMA,
            "feed": managed_rpm_qualification.FEED,
            "controller_sha256": ("0" * 64 if condition == "wrong-managed-rpm-controller"
                                  else rpm_qualification.sha256(ROOT / managed_rpm_qualification.CONTROLLER)),
            "crypto_requirements_sha256": (
                "0" * 64 if condition == "wrong-managed-rpm-lock" else
                hashlib.sha256(managed_rpm_qualification.locked_crypto_requirements(ROOT)).hexdigest()
            ),
            "previous": rpm_native["previous"],
            "candidate": {**rpm_native["candidate"],
                          "launcher_sha256": "1" * 64 if condition == "wrong-managed-rpm-launcher" else launcher},
            "requests": (
                ["/candidate/manifest.json"] if condition == "wrong-managed-rpm-requests" else
                ["/previous/manifest.json", f"/previous/{rpm_qualification.rpm_name(rpm_qualification.PREVIOUS_VERSION)}",
                 "/candidate/manifest.json", f"/candidate/{rpm_name}"]
            ),
            "checks": dict.fromkeys(managed_rpm_qualification.CHECKS, condition != "managed-rpm-failed"),
            "interrupted_rollback_native_invocations": 2 if condition == "wrong-managed-rpm-rollback-count" else 1,
        }
        managed_rpm = rpm_outer["managed_update"]
        if condition == "old-managed-rpm":
            managed_rpm["schema"] = managed_rpm_qualification.ROLLBACK_PLAN_SCHEMA
            del managed_rpm["interrupted_rollback_native_invocations"]
            managed_rpm_qualification.verify_receipt(managed_rpm, rpm_native)
        if condition == "missing-rpm-dependency-check":
            del managed_rpm["checks"]["dependency_conflict_refused_and_same_transaction_retried_offline"]
        if condition == "missing-rpm-rollback-dependency-check":
            managed_rpm["checks"] = dict.fromkeys(managed_rpm_qualification.PREVIOUS_CHECKS, True)
    rpm_report = candidate.qualification_receipt_bytes(rpm_outer)
    installers["linux-x86_64"] = {
        deb_name: deb_bytes, rpm_name: rpm_bytes,
        f"remote-ops-workspace-{tag}-linux-x86_64.AppImage": b"candidate x86_64 AppImage",
    }
    installers["linux-aarch64"] = {
        f"remote-ops-workspace-{tag}-linux-{label}": f"candidate aarch64 {label}".encode()
        for label in ("arm64.deb", "aarch64.rpm", "aarch64.AppImage")
    }
    staged_artifacts = {}
    for name, files in expected_archive_files.items():
        target = name.removeprefix("release-").replace("-native-", "-", 1)
        manifest, = (asset for asset in files if asset.endswith(("-native-manifest.json", "-release-manifest.json")))
        checksum, = (asset for asset in files if asset.endswith("-SHA256SUMS.txt"))
        body = {
            filename: installers.get(target, {}).get(filename, f"bytes from {filename}".encode())
            for filename in sorted(files - {manifest, checksum})
        }
        rows = [
            {"file": filename, "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()}
            for filename, data in body.items()
        ]
        if target == "windows-x86":
            if condition == "stale-native-manifest-digest":
                rows[0]["sha256"] = "b" * 64
            elif condition == "missing-native-manifest-row":
                rows.pop(0)
        payload = {"artifacts": rows} if name == "release-source-python" else rows
        body[manifest] = json.dumps(payload).encode()
        lines = [f"{hashlib.sha256(data).hexdigest()}  {filename}\n" for filename, data in body.items()]
        if condition == "repeated-checksum-reference" and target == "windows-x86":
            lines.append(lines[0])
        body[checksum] = "".join(lines).encode()
        staged_artifacts[name] = body
    x86 = staged_artifacts["release-windows-native-x86"]
    x64 = staged_artifacts["release-windows-native-x64"]
    x86_manifest = f"remote-ops-workspace-{tag}-windows-x86-native-manifest.json"
    x64_manifest = f"remote-ops-workspace-{tag}-windows-x64-native-manifest.json"
    if condition == "swapped-native-manifests":
        x86[x64_manifest], x64[x86_manifest] = x64.pop(x64_manifest), x86.pop(x86_manifest)
    elif condition == "foreign-checksum-reference":
        x86_checksum, = (asset for asset in x86 if asset.endswith("-SHA256SUMS.txt"))
        x64_checksum, = (asset for asset in x64 if asset.endswith("-SHA256SUMS.txt"))
        x86_row = f"{hashlib.sha256(x86[x86_manifest]).hexdigest()}  {x86_manifest}\n".encode()
        x64_row = f"{hashlib.sha256(x64[x64_manifest]).hexdigest()}  {x64_manifest}\n".encode()
        x86[x86_checksum] = x86[x86_checksum].replace(x86_row, x64_row)
        x64[x64_checksum] = x64[x64_checksum].replace(x64_row, x86_row)
    elif condition == "unexpected-source-file":
        staged_artifacts["release-source-python"]["unexpected-build-notes.txt"] = b"Unexpected build notes"

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
            elif name in smoke:
                target = name.removeprefix("release-").replace("-gui-smoke-", "-", 1)
                gui_path = candidate.GUI_PYZ_ARCHIVE_PATHS[target]
                if (condition, name) == ("wrong-gui-path", smoke[0]):
                    gui_path = "native/row-gui"
                installer_hashes = {key: hashlib.sha256(data).hexdigest()
                                    for key, data in installers[target].items()}
                if (condition, name) == ("missing-gui-installers", smoke[0]):
                    installer_hashes.clear()
                if (condition, name) == ("wrong-gui-installer", smoke[0]):
                    installer_hashes[next(iter(installer_hashes))] = "d" * 64
                gui_binding = candidate.qualification_receipt_bytes({
                    "installer_sha256": installer_hashes,
                    "target": target, "status": "bound", "smoke_complete": True,
                    "expected_executables": [{"role": "gui", "path": gui_path, "sha256": "c" * 64}],
                    "observations": [{
                        "role": "gui", "matched": True, "expected_sha256": "c" * 64,
                        "observed_sha256": (
                            "d" * 64 if (condition, name) == ("wrong-gui-observation", smoke[0]) else "c" * 64
                        ),
                    }],
                })
                archive.writestr(candidate.NATIVE_BYTE_BINDING_FILE, gui_binding)
                archive.writestr("gui-example/result.png", b"fixture screenshot bytes")
                if (condition, name) != ("missing-gui-proof", smoke[0]):
                    required = list(candidate.GUI_PYZ_REQUIRED_MODULES)
                    monitoring = "remote_ops_workspace.gui_remote_monitoring"
                    if (condition, name) == ("missing-gui-module", smoke[0]):
                        required.remove(monitoring)
                    observed = dict.fromkeys(required, True)
                    if (condition, name) == ("unverified-gui-module", smoke[0]):
                        observed[monitoring] = False
                    archive.writestr(candidate.GUI_ARCHIVE_PROOF_FILE, candidate.qualification_receipt_bytes({
                        "schema_version": 1, "role": "gui", "target": target, "status": "passed", "path": gui_path,
                        "required_modules": required, "observed_presence": observed, "errors": [],
                        "artifact_sha256": "d" * 64 if (condition, name) == ("wrong-gui-launcher", smoke[0]) else "c" * 64,
                        "smoke_binding_sha256": "d" * 64 if (condition, name) == ("wrong-gui-binding", smoke[0])
                        else hashlib.sha256(gui_binding).hexdigest(),
                    }))
            elif name in linux_smoke:
                target = name.replace("release-linux-native-smoke-", "linux-", 1)
                digests = {asset: hashlib.sha256(data).hexdigest() for asset, data in installers[target].items()}
                changed = name == "release-linux-native-smoke-aarch64"
                if changed and condition == "wrong-linux-package":
                    digests[next(iter(digests))] = "b" * 64
                raw_binding = candidate.qualification_receipt_bytes({
                    "target": target, "status": "bound", "smoke_complete": True, "installer_sha256": digests,
                })
                proof_sha = "b" * 40 if changed and condition == "wrong-linux-proof" else sha
                archive.writestr(candidate.NATIVE_BYTE_BINDING_FILE, raw_binding)
                archive.writestr(candidate.LINUX_SMOKE_PROOF_FILE, candidate.qualification_receipt_bytes({
                    "target": target, "source": {"head": proof_sha}, "event_sha": sha, "run_id": "123",
                    "run_attempt": "1", "native_build_outcome": "success", "native_smoke_outcome": "success",
                    "source_unchanged": True, "native_pyinstaller_inventory_complete": True,
                    "native_executable_byte_binding": {
                        "status": "bound",
                        "report_path": f"build/native-smoke/{target}/{candidate.NATIVE_BYTE_BINDING_FILE}",
                        "report_sha256": hashlib.sha256(raw_binding).hexdigest(),
                    },
                }))
            elif name == candidate.MANAGED_DEBIAN_ARTIFACT:
                archive.writestr(candidate.REPORT_NAME, managed_report)
            elif name == candidate.RPM_ARTIFACT:
                archive.writestr(candidate.RPM_REPORT_NAME, rpm_report)
                archive.writestr(candidate.RPM_SMOKE_FILES[0], proof)
                if condition != "missing-rpm-smoke":
                    archive.writestr(candidate.RPM_SMOKE_FILES[1], binding)
            elif name in staged_artifacts:
                for filename, data in staged_artifacts[name].items():
                    archive.writestr(filename, data)
            else:
                archive.writestr(f"{name}.txt", f"bytes from {name}")
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
        if name in {*standard, *runtime, *smoke, *linux_smoke, candidate.MANAGED_DEBIAN_ARTIFACT, candidate.RPM_ARTIFACT}:
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
                    "status": "completed",
                    "conclusion": "success",
                }
            if endpoint.startswith("actions/artifacts/"):
                artifact_id = int(endpoint.rsplit("/", 1)[1])
                return next(item for item in artifacts if item["id"] == artifact_id)
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

    metadata_reads = []
    reviewed_bundle = {"artifact_id": 500, "archive_sha256": "b" * 64, "runtime_sha256": "c" * 64}

    def seal_bundle(_client, artifact_id, archive_sha256):
        assert (artifact_id, archive_sha256) == (500, reviewed_bundle["archive_sha256"])
        return reviewed_bundle

    monkeypatch.setattr(candidate, "seal_debian_server_bundle", seal_bundle)

    def deb_metadata(package: Path, *, expected_runtime_sha256: str | None) -> tuple[str, bool]:
        assert expected_runtime_sha256 == reviewed_bundle["runtime_sha256"]
        metadata_reads.append((output.exists(), root.exists()))
        assert package.name == deb_name and package.read_bytes() == deb_bytes
        return (
            "libc6" if condition == "wrong-managed-depends" else depends,
            not bundled if condition == "wrong-managed-bundle" else bundled,
        )

    monkeypatch.setattr(candidate, "read_candidate_deb_metadata", deb_metadata)

    def seal() -> None:
        candidate.stage(
            BuildRun(),
            release_tag=tag,
            release_sha=sha,
            run_id=123,
            run_attempt=1,
            assets_root=root,
            output=output,
            server_bundle_artifact_id=reviewed_bundle["artifact_id"],
            server_bundle_sha256=reviewed_bundle["archive_sha256"],
        )

    if error:
        with pytest.raises(ValueError, match=error):
            seal()
        if condition in {
            "wrong-managed-deb", "wrong-rpm-digest", "wrong-managed-depends", "wrong-managed-bundle",
            "missing-gui-installers", "wrong-gui-installer", "wrong-linux-package",
            "swapped-native-manifests", "unexpected-source-file",
            "foreign-checksum-reference", "repeated-checksum-reference", "stale-native-manifest-digest",
            "missing-native-manifest-row",
        }:
            assert len(downloads) == len(archives)
        elif condition in {"wrong-managed-run", "wrong-managed-controller", "missing-rollback", "old-managed-schema", "unbundled"}:
            assert len(downloads) == len(runtime) + 1
        elif condition in {
            "wrong-rpm-ref", "wrong-rpm-attempt", "rpm-failed",
            "missing-rpm-smoke", "wrong-rpm-smoke-sha", "changed-rpm-launcher",
            "missing-managed-rpm", "wrong-managed-rpm-controller", "wrong-managed-rpm-lock",
            "old-managed-rpm", "missing-rpm-dependency-check", "missing-rpm-rollback-dependency-check",
            "managed-rpm-failed", "wrong-managed-rpm-launcher", "wrong-managed-rpm-requests",
            "wrong-managed-rpm-rollback-count",
        }:
            assert len(downloads) == len(runtime) + 2
        elif condition in {
            "missing-gui-proof", "wrong-gui-binding", "wrong-gui-launcher", "wrong-gui-observation",
            "missing-gui-module", "unverified-gui-module", "wrong-gui-path",
        }:
            assert len(downloads) == len(runtime) + 3
        elif condition == "wrong-linux-proof":
            assert len(downloads) == len(runtime) + 2 + len(smoke) + len(linux_smoke)
        else:
            assert len(downloads) == (1 if condition in {"bad-runtime-report", "nonregular-runtime-report"} else 0)
        assert not root.exists()
        assert not output.exists()
        return

    seal()
    assert metadata_reads == [(False, False)]
    inventory = json.loads(output.read_text(encoding="utf-8"))
    records = candidate.validate_inventory(
        inventory, repository="example/project", release_tag=tag, release_sha=sha,
        run_id=123, run_attempt=1,
    )
    assert {record["name"] for record in records} == set(standard)
    assert {path.name for path in root.iterdir()} == set().union(*expected_archive_files.values())
    assert len(downloads) == len(archives) and set(downloads) == set(archives)
    assert inventory["runtime_reports"].keys() == candidate.RUNTIME_REPORT_ARTIFACT_NAMES.keys()
    for report in inventory["runtime_reports"].values():
        assert report["sha256"] == hashlib.sha256(raw_report).hexdigest()
        assert report["size_bytes"] == len(raw_report)
    gui_archives = inventory["gui_smoke"]
    linux_archives = inventory["linux_smoke"]
    assert gui_archives.keys() == set(smoke)
    assert linux_archives.keys() == set(linux_smoke)
    for name, record in {**gui_archives, **linux_archives}.items():
        target = name.removeprefix("release-").replace("-gui-smoke-", "-", 1).replace("-native-smoke-", "-", 1)
        metadata = next(artifact for artifact in artifacts if artifact["name"] == name)
        assert record == {
            "artifact_id": metadata["id"], "archive_digest": metadata["digest"],
            "size_in_bytes": len(archives[metadata["id"]]),
            "installer_sha256": {
                asset: hashlib.sha256(data).hexdigest()
                for asset, data in installers[target].items()
            },
        }
    managed = inventory.pop("managed_debian_update")
    assert managed["sha256"] == hashlib.sha256(managed_report).hexdigest()
    assert managed["receipt"]["candidate_sha256"] == deb_sha
    assert managed["receipt"]["candidate_has_server_bundle"] is bundled
    rpm = inventory["rpm_recovery"]
    assert rpm["sha256"] == hashlib.sha256(rpm_report).hexdigest()
    assert rpm["receipt"]["receipt"]["candidate"]["package_sha256"] == rpm_sha
    assert rpm["receipt"]["managed_update"]["candidate"]["package_sha256"] == rpm_sha
    smoke_records = inventory["rpm_smoke"]
    assert smoke_records[candidate.RPM_SMOKE_FILES[0]]["sha256"] == hashlib.sha256(proof).hexdigest()
    assert smoke_records[candidate.RPM_SMOKE_FILES[1]]["sha256"] == hashlib.sha256(binding).hexdigest()
    coordinates = dict(repository="example/project", release_tag=tag, release_sha=sha, run_id=123, run_attempt=1)
    public_coordinates = {key: coordinates[key] for key in ("repository", "release_tag", "release_sha")}

    def revised_rpm(record, **fields):
        receipt = {**record["receipt"], **fields}
        encoded = candidate.qualification_receipt_bytes(receipt)
        return {**record, "receipt": receipt, "sha256": hashlib.sha256(encoded).hexdigest(),
                "size_bytes": len(encoded)}

    historic = json.loads(output.read_bytes())
    historic["schema_version"] = candidate.ARCHIVE_FILE_SCOPE_SCHEMA_VERSION
    with pytest.raises(ValueError, match="pinned Fedora qualification image"):
        candidate.validate_inventory(historic, **coordinates)
    old_managed = {**rpm["receipt"]["managed_update"], "schema": managed_rpm_qualification.ROLLBACK_PLAN_SCHEMA}
    old_rpm = revised_rpm(rpm, container_image=rpm_qualification.LEGACY_IMAGE, managed_update=old_managed)
    historic["rpm_recovery"] = old_rpm
    candidate.validate_inventory(historic, **coordinates)
    historic["schema_version"] = candidate.SCHEMA_VERSION
    with pytest.raises(ValueError, match="pinned Fedora qualification image"):
        candidate.validate_inventory(historic, **coordinates)
    historic["rpm_recovery"] = revised_rpm(rpm, managed_update=old_managed)
    with pytest.raises(ValueError, match="installer retries"):
        candidate.validate_inventory(historic, **coordinates)
    swapped = json.loads(output.read_bytes())
    windows = {record["name"]: record["files"] for record in swapped["artifacts"] if "windows-native" in record["name"]}
    x64, x86 = windows["release-windows-native-x64"], windows["release-windows-native-x86"]
    x64_manifest, = (file for file in x64 if file["path"].endswith("-native-manifest.json"))
    x86_manifest, = (file for file in x86 if file["path"].endswith("-native-manifest.json"))
    x64[x64.index(x64_manifest)], x86[x86.index(x86_manifest)] = x86_manifest, x64_manifest
    with pytest.raises(ValueError, match="files differ from its release matrix assignment"):
        candidate.validate_inventory(swapped, **coordinates)
    swapped["schema_version"] = candidate.GUI_MODULE_PROOF_SCHEMA_VERSION
    swapped["rpm_recovery"] = old_rpm
    candidate.validate_inventory(swapped, **coordinates)
    with pytest.raises(ValueError, match="managed Debian receipt is missing"):
        candidate.validate_inventory(inventory, **coordinates)
    # Historical inventory bytes remain readable when their tag's workflow
    # predated the managed Debian qualification.
    inventory.pop("rpm_recovery")
    inventory.pop("rpm_smoke")
    inventory.pop("gui_smoke")
    inventory.pop("linux_smoke")
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
    inventory["rpm_recovery"] = old_rpm
    inventory["schema_version"] = candidate.RPM_SCHEMA_VERSION
    candidate.validate_inventory(inventory, **coordinates)
    inventory["schema_version"] = candidate.SCHEMA_VERSION
    inventory["rpm_recovery"] = rpm
    with pytest.raises(ValueError, match="RPM native smoke evidence is missing"):
        candidate.validate_inventory(inventory, **coordinates)
    inventory["rpm_smoke"] = smoke_records
    inventory["managed_debian_update"] = managed
    legacy = {key: value for key, value in rpm["receipt"].items() if key != "managed_update"}
    legacy["schema"] = rpm_qualification.NATIVE_ONLY_SCHEMA
    legacy_bytes = candidate.qualification_receipt_bytes(legacy)
    inventory["rpm_recovery"] = {**rpm, "receipt": legacy, "sha256": hashlib.sha256(legacy_bytes).hexdigest(),
                                 "size_bytes": len(legacy_bytes)}
    with pytest.raises(ValueError, match="requires the managed-update qualification"):
        candidate.validate_inventory(inventory, **coordinates)
    inventory["schema_version"] = candidate.RPM_SMOKE_SCHEMA_VERSION
    inventory["rpm_recovery"] = revised_rpm(inventory["rpm_recovery"], container_image=rpm_qualification.LEGACY_IMAGE)
    candidate.validate_inventory(inventory, **coordinates)
    inventory["schema_version"] = candidate.SCHEMA_VERSION
    inventory["rpm_recovery"] = rpm
    with pytest.raises(ValueError, match="must contain all desktop GUI smoke archives"):
        candidate.validate_inventory(inventory, **coordinates)
    inventory["schema_version"] = candidate.MANAGED_RPM_SCHEMA_VERSION
    candidate.validate_inventory({**inventory, "rpm_recovery": old_rpm}, **coordinates)
    inventory["schema_version"] = candidate.SCHEMA_VERSION
    inventory["gui_smoke"] = gui_archives
    gui_record = gui_archives[smoke[0]]
    installer_hashes = gui_record.pop("installer_sha256")
    with pytest.raises(ValueError, match="must bind the complete installer digest set"):
        candidate.validate_inventory(inventory, **coordinates)
    inventory["schema_version"] = candidate.GUI_SMOKE_SCHEMA_VERSION
    candidate.validate_inventory({**inventory, "rpm_recovery": old_rpm}, **coordinates)
    inventory["schema_version"] = candidate.SCHEMA_VERSION
    gui_record["installer_sha256"] = installer_hashes
    with pytest.raises(ValueError, match="must contain all Linux native smoke archives"):
        candidate.validate_inventory(inventory, **coordinates)
    inventory["schema_version"] = candidate.GUI_INSTALLER_SCHEMA_VERSION
    candidate.validate_inventory({**inventory, "rpm_recovery": old_rpm}, **coordinates)
    inventory["schema_version"] = candidate.SCHEMA_VERSION
    inventory["linux_smoke"] = linux_archives
    old_receipt = {**managed["receipt"], "candidate_has_server_bundle": False}
    old_receipt["receipts"] = {
        name: result for name, result in old_receipt["receipts"].items() if name != "changed-server-manifest-rollback"
    }
    old_bytes = candidate.qualification_receipt_bytes(old_receipt)
    inventory["managed_debian_update"] = {
        **managed, "receipt": old_receipt, "size_bytes": len(old_bytes), "sha256": hashlib.sha256(old_bytes).hexdigest(),
    }
    with pytest.raises(ValueError, match="the production Debian candidate requires the embedded server bundle"):
        candidate.validate_inventory(inventory, **coordinates)
    inventory["schema_version"] = candidate.LINUX_INSTALLER_SCHEMA_VERSION
    del inventory["linux_smoke"]
    with pytest.raises(ValueError, match="must contain all Linux native smoke archives"):
        candidate.validate_inventory({**inventory, "rpm_recovery": old_rpm}, **coordinates)
    inventory["linux_smoke"] = linux_archives
    candidate.validate_inventory({**inventory, "rpm_recovery": old_rpm}, **coordinates)
    inventory["schema_version"] = candidate.SCHEMA_VERSION
    inventory["managed_debian_update"] = managed
    assert inventory.pop("debian_server_bundle") == reviewed_bundle
    with pytest.raises(ValueError, match="missing verified Debian server archive coordinates"):
        candidate.validate_inventory(inventory, **coordinates)
    inventory["schema_version"] = candidate.SERVER_BUNDLE_SCHEMA_VERSION
    candidate.validate_inventory({**inventory, "rpm_recovery": old_rpm}, **coordinates)
    inventory["schema_version"] = candidate.SCHEMA_VERSION
    inventory["debian_server_bundle"] = {**reviewed_bundle, "runtime_sha256": "invalid digest"}
    with pytest.raises(ValueError, match="missing verified Debian server archive coordinates"):
        candidate.validate_inventory(inventory, **coordinates)
    inventory["debian_server_bundle"] = reviewed_bundle
    with pytest.raises(ValueError, match="requires the exact package for server bundle verification"):
        candidate.validate_managed_release_qualification(inventory, **public_coordinates, deb_sha256=deb_sha)
    wrong_deb = tmp_path / deb_name
    wrong_deb.write_bytes(b"different file under the same published name")
    with pytest.raises(ValueError, match="differs from the qualified release installer"):
        candidate.validate_managed_release_qualification(
            inventory, **public_coordinates, deb_sha256=deb_sha, deb_package=wrong_deb,
        )
    candidate.validate_managed_release_qualification(
        inventory, **public_coordinates, deb_sha256=deb_sha, deb_package=root / deb_name,
    )
    retained = tmp_path / "review" / "archives"
    retained.mkdir(parents=True)
    qualifications = prepare_release_redistribution_review.collect_qualification_archives(
        BuildRun(), retained, inventory, "example/project", tag, sha, 123,
    )
    expected_qualifications = {
        candidate.MANAGED_DEBIAN_ARTIFACT: managed, candidate.RPM_ARTIFACT: rpm, **gui_archives, **linux_archives,
    }
    assert downloads[-len(expected_qualifications):] == [
        record["artifact_id"] for record in expected_qualifications.values()
    ]
    for name, record in expected_qualifications.items():
        path = retained / f"{name}.zip"
        assert path.read_bytes() == archives[record["artifact_id"]]
        assert qualifications[name]["sha256"] == record["archive_digest"].removeprefix("sha256:")

    pointer_id = max(archives) + 1
    pointer_zip = io.BytesIO()
    with zipfile.ZipFile(pointer_zip, "w") as sealed:
        sealed.writestr("release-candidate-inventory.json", output.read_bytes())
    archives[pointer_id] = pointer_zip.getvalue()
    pointer_digest = f"sha256:{hashlib.sha256(archives[pointer_id]).hexdigest()}"
    artifacts.append({
        "id": pointer_id, "name": candidate.CANDIDATE_INVENTORY_ARTIFACT, "digest": pointer_digest,
        "size_in_bytes": len(archives[pointer_id]), "expired": False, "workflow_run": {"id": 123, "head_sha": sha},
    })
    promoted_assets = tmp_path / "promoted-assets"
    promoted_qualifications = tmp_path / "promoted-qualifications"
    attestations = []
    monkeypatch.setattr(candidate, "verify_candidate_attestation", lambda path, **kwargs: attestations.append((path, kwargs)))

    def promote():
        candidate.promote(
            BuildRun(), release_tag=tag, release_sha=sha, run_id=123, run_attempt=1,
            inventory_artifact_id=pointer_id, inventory_archive_digest=pointer_digest,
            approved_inventory=output, assets_root=promoted_assets, qualification_archives=promoted_qualifications,
        )

    arm_id = linux_archives[linux_smoke[1]]["artifact_id"]
    arm_original = archives[arm_id]
    archives[arm_id] = arm_original[:-1] + bytes([arm_original[-1] ^ 1])
    with pytest.raises(ValueError, match="aarch64 archive digest or size differs"):
        promote()
    assert not promoted_assets.exists() and not promoted_qualifications.exists()
    archives[arm_id] = arm_original
    with monkeypatch.context() as changed_metadata:
        changed_metadata.setattr(candidate, "read_candidate_deb_metadata", lambda _package, **_kwargs: (depends, False))
        with pytest.raises(ValueError, match="receipt server bundle claim differs from the candidate DEB"):
            promote()
        assert not promoted_assets.exists() and not promoted_qualifications.exists()
        with pytest.raises(ValueError, match="receipt server bundle claim differs from the candidate DEB"):
            candidate.validate_managed_release_qualification(
                inventory, **public_coordinates, deb_sha256=deb_sha, deb_package=root / deb_name,
            )
    promote()
    assert attestations[-1] == (output, {
        **coordinates, "inventory_sha256": hashlib.sha256(output.read_bytes()).hexdigest(), "build_event": event,
    })
    assert {path.name: path.read_bytes() for path in promoted_assets.iterdir()} == {
        path.name: path.read_bytes() for path in root.iterdir()
    }
    assert {path.name: path.read_bytes() for path in promoted_qualifications.iterdir()} == {
        path.name: path.read_bytes() for path in retained.iterdir()
    }
    candidate.verify_retained_qualification_archives(promoted_qualifications, inventory)
    candidate.verify_retained_qualification_archives(retained, inventory)
    gui_archive = retained / f"{smoke[0]}.zip"
    gui_bytes = gui_archive.read_bytes()
    gui_record = gui_archives[smoke[0]]
    with zipfile.ZipFile(io.BytesIO(gui_bytes)) as original:
        native_binding = original.read(candidate.NATIVE_BYTE_BINDING_FILE)
        gui_proof = json.loads(original.read(candidate.GUI_ARCHIVE_PROOF_FILE))
    gui_proof.pop("observed_presence")
    with zipfile.ZipFile(gui_archive, "w") as reduced:
        reduced.writestr(candidate.NATIVE_BYTE_BINDING_FILE, native_binding)
        reduced.writestr(candidate.GUI_ARCHIVE_PROOF_FILE, candidate.qualification_receipt_bytes(gui_proof))
    legacy_bytes = gui_archive.read_bytes()
    legacy_record = {
        **gui_record, "size_in_bytes": len(legacy_bytes),
        "archive_digest": f"sha256:{hashlib.sha256(legacy_bytes).hexdigest()}",
    }
    gui_archives[smoke[0]] = legacy_record
    with pytest.raises(ValueError, match="GUI archive proof must attest every required frozen GUI module"):
        candidate.verify_retained_qualification_archives(retained, inventory)
    candidate.verify_retained_qualification_archives(
        retained, {**inventory, "schema_version": candidate.REVIEWED_SERVER_BUNDLE_SCHEMA_VERSION},
    )
    gui_archives[smoke[0]] = gui_record
    gui_archive.write_bytes(gui_bytes)
    arm_archive = retained / f"{linux_smoke[1]}.zip"
    arm_bytes = arm_archive.read_bytes()
    arm_archive.unlink()
    with pytest.raises(ValueError, match="missing or invalid retained.*aarch64"):
        candidate.verify_retained_qualification_archives(retained, inventory)
    arm_archive.write_bytes(arm_bytes[:-1] + bytes([arm_bytes[-1] ^ 1]))
    with pytest.raises(ValueError, match="aarch64 retained archive digest or size differs"):
        candidate.verify_retained_qualification_archives(retained, inventory)
    arm_archive.write_bytes(arm_bytes)
    arm_record = linux_archives[linux_smoke[1]]
    arm_installers = arm_record["installer_sha256"]
    arm_record["installer_sha256"] = {name: "f" * 64 for name in arm_installers}
    with pytest.raises(ValueError, match="aarch64 installer smoke hashes differ"):
        candidate.verify_retained_qualification_archives(retained, inventory)
    arm_record["installer_sha256"] = arm_installers
    smoke_records[candidate.RPM_SMOKE_FILES[1]]["sha256"] = "f" * 64
    with pytest.raises(ValueError, match="RPM native smoke file differs"):
        candidate.verify_sealed_rpm_smoke(BuildRun(), inventory, 123, sha)
    smoke_records[candidate.RPM_SMOKE_FILES[1]]["sha256"] = hashlib.sha256(binding).hexdigest()
    rpm_id = rpm["artifact_id"]
    rpm["artifact_id"] = managed["artifact_id"]
    with pytest.raises(ValueError, match="RPM recovery report artifact id is duplicated"):
        candidate.validate_inventory(inventory, **coordinates)
    rpm["artifact_id"] = rpm_id
    gui_record = gui_archives[smoke[0]]
    gui_id = gui_record["artifact_id"]
    gui_record["artifact_id"] = rpm_id
    with pytest.raises(ValueError, match="gui-smoke.*artifact id is duplicated"):
        candidate.validate_inventory(inventory, **coordinates)
    gui_record["artifact_id"] = gui_id
    changed_archive = {**gui_record, "size_in_bytes": gui_record["size_in_bytes"] + 1}
    with pytest.raises(ValueError, match="archive digest or size differs from the sealed inventory"):
        candidate.verify_sealed_smoke(BuildRun(), {smoke[0]: changed_archive}, 123, sha)
    original_archive = archives[gui_id]
    archives[gui_id] = original_archive[:-1] + bytes([original_archive[-1] ^ 1])
    with pytest.raises(ValueError, match="archive digest or size differs from the sealed inventory"):
        candidate.verify_sealed_smoke(BuildRun(), {smoke[0]: gui_record}, 123, sha)
    archives[gui_id] = original_archive
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

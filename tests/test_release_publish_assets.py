from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

POLICY = (
    "Only accepted evidence records in this file can promote Linux i386, Linux armhf, "
    "or Windows XP native-host readiness. Accepted records must include release asset URLs, "
    "review-bundle manifest release asset URL binding, review bundle release asset URLs, "
    "release-importable artifact source binding, "
    "and per-artifact SHA-256 digests, Linux builder identity evidence, builder identity "
    "SHA-256, builder identity release/run binding, "
    "Linux builder host identity binding when applicable, "
    "Linux builder rpm and non-interactive sudo evidence, Linux security patch evidence, "
    "Linux native build and smoke command provenance, "
    "Linux smoke evidence SHA-256 and Linux smoke release/run binding, "
    "Linux workflow dispatch inputs when applicable, XP evidence bundle SHA-256 digests, "
    "XP evidence validation command binding, XP evidence contract SHA-256, "
    "XP evidence summary binding, XP host identity SHA-256 binding, XP security patch evidence, "
    "tracked scripts/xp_smoke_runner.cmd XP smoke command provenance, "
    "XP smoke evidence-file summary binding and "
    "XP security smoke proof-line binding when applicable, and review "
    "bundle manifest, review bundle archive, and review bundle SHA-256 sidecar digests "
    "before strict promotion, and release uploads must include those review bundle files with matching "
    "size, SHA-256 and checksum-sidecar coverage; each accepted record must include "
    "the promotion config SHA-256, have a unique target, all release evidence for one record must "
    "use the same GitHub repository, and Windows XP x86/x64 pairs must use the same release_tag "
    "and GitHub repository. "
    "Empty means no promotion."
)
MOBA_PARITY_POLICY = (
    "Only accepted evidence records in this file can close strict MobaXterm 26.4 Home/Professional parity "
    "articles. Accepted records must include one unique article_id, status accepted, a vX.Y.Z release_tag, "
    "a release_target, the exact validation command for that article, SHA-256 digests for the validated "
    "evidence JSON and evidence assets, release asset URLs under the same GitHub release tag, per-artifact "
    "SHA-256 digests, required article checks, and a validation summary proving the article evidence passed. "
    "Empty means the generated feature-family score remains separate from true product-depth parity."
)


def test_release_publish_asset_checker_passes_current_tree() -> None:
    checker = _load_checker()

    assert checker.main([]) == 0


def test_release_publish_asset_checker_can_require_platform_goal_targets() -> None:
    checker = _load_checker()

    assert checker.main(["--require-platform-goal-targets"]) == 1


def test_expected_release_assets_expand_default_matrix() -> None:
    checker = _load_checker()
    matrix = _load_matrix()

    assets = checker.expected_release_assets(matrix)

    assert "remote_ops_workspace-1.0.2-py3-none-any.whl" in assets
    assert "remote-ops-workspace-v1.0.2-windows-x86-setup.exe" in assets
    assert "remote-ops-workspace-v1.0.2-macos-arm64.pkg" in assets
    assert "remote-ops-workspace-v1.0.2-linux-amd64.deb" in assets
    assert "remote-ops-workspace-v1.0.2-linux-aarch64-native-SHA256SUMS.txt" in assets
    assert "remote-ops-workspace-v1.0.2-linux-i386.deb" not in assets
    assert "remote-ops-workspace-v1.0.2-linux-armhf.deb" not in assets


def test_expected_release_assets_normalize_to_requested_tag() -> None:
    checker = _load_checker()
    matrix = _load_matrix()

    assets = checker.expected_release_assets(matrix, tag="v1.0.3")

    assert "remote_ops_workspace-1.0.3-py3-none-any.whl" in assets
    assert "remote-ops-workspace-v1.0.3-windows-x64-setup.exe" in assets
    assert "remote_ops_workspace-1.0.2-py3-none-any.whl" not in assets
    assert "remote-ops-workspace-v1.0.2-windows-x64-setup.exe" not in assets


def test_publish_contract_rejects_gated_default_asset_without_evidence() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    linux_job = next(job for job in matrix["default_github_release"]["native_jobs"] if job["job"] == "linux-native")
    linux_job["asset_patterns"].append("remote-ops-workspace-v1.0.2-linux-i386.deb")

    errors = checker.check_publish_contract(matrix, workflow, evidence_registry=_empty_evidence_registry())

    assert any("gated native asset remote-ops-workspace-v1.0.2-linux-i386.deb" in error for error in errors)


def test_publish_contract_allows_gated_default_asset_with_accepted_evidence() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    linux_job = next(job for job in matrix["default_github_release"]["native_jobs"] if job["job"] == "linux-native")
    linux_job["asset_patterns"].append("remote-ops-workspace-v1.0.2-linux-i386.deb")

    errors = checker.check_publish_contract(
        matrix,
        workflow,
        evidence_registry=_accepted_evidence_registry("linux-i386"),
    )

    assert not any("gated native asset remote-ops-workspace-v1.0.2-linux-i386.deb" in error for error in errors)


def test_publish_contract_rejects_gated_default_asset_with_wrong_release_evidence() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    linux_job = next(job for job in matrix["default_github_release"]["native_jobs"] if job["job"] == "linux-native")
    linux_job["asset_patterns"].append("remote-ops-workspace-v1.0.2-linux-i386.deb")

    errors = checker.check_publish_contract(
        matrix,
        workflow,
        tag="v1.0.3",
        evidence_registry=_accepted_evidence_registry("linux-i386"),
    )

    assert any(
        "default release matrix includes gated native asset remote-ops-workspace-v1.0.3-linux-i386.deb "
        "for linux-i386 without accepted platform evidence for release_tag v1.0.3"
        in error
        for error in errors
    )


def test_publish_contract_rejects_gated_asset_with_unfinalized_platform_candidate() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    linux_job = next(job for job in matrix["default_github_release"]["native_jobs"] if job["job"] == "linux-native")
    linux_job["asset_patterns"].append("remote-ops-workspace-v1.0.2-linux-i386.deb")
    registry = _accepted_evidence_registry("linux-i386")
    registry["accepted_evidence"][0].pop("review_bundle")

    errors = checker.check_publish_contract(matrix, workflow, evidence_registry=registry)

    assert any("gated native asset remote-ops-workspace-v1.0.2-linux-i386.deb" in error for error in errors)


def test_publish_contract_rejects_malformed_accepted_evidence_for_gated_asset() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    linux_job = next(job for job in matrix["default_github_release"]["native_jobs"] if job["job"] == "linux-native")
    linux_job["asset_patterns"].append("remote-ops-workspace-v1.0.2-linux-i386.deb")

    errors = checker.check_publish_contract(
        matrix,
        workflow,
        evidence_registry={
            "schema_version": 1,
            "policy": POLICY,
            "accepted_evidence": [
                {
                    "target": "linux-i386",
                    "status": "accepted",
                    "readiness_percent": 100.0,
                }
            ],
        },
    )

    assert any("gated native asset remote-ops-workspace-v1.0.2-linux-i386.deb" in error for error in errors)


def test_publish_contract_rejects_xp_asset_without_complete_xp_pair() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    windows_job = next(job for job in matrix["default_github_release"]["native_jobs"] if job["job"] == "windows-native")
    windows_job["asset_patterns"].append("remote-ops-workspace-v1.0.2-windows-xp-x86-native.zip")

    errors = checker.check_publish_contract(
        matrix,
        workflow,
        evidence_registry=_accepted_evidence_registry("windows-xp-native-x86"),
    )

    assert any("XP native promotion requires accepted evidence for both targets" in error for error in errors)


def test_publish_contract_requires_validation_before_upload() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        "python scripts/check_release_publish_assets.py --assets-dir release-assets --tag",
        "python scripts/check_release_matrix.py # disabled publish asset validation",
    )

    errors = checker.check_publish_contract(matrix, workflow)

    assert any("publish asset validation" in error for error in errors)


def test_publish_contract_requires_platform_goal_gate_before_upload() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        " --require-platform-goal-targets",
        "",
    )

    errors = checker.check_publish_contract(matrix, workflow)

    assert any("protected platform goal publish gate" in error for error in errors)


def test_publish_contract_requires_platform_evidence_import_job() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        "accepted-platform-evidence-assets",
        "removed-platform-evidence-assets",
    )

    errors = checker.check_publish_contract(matrix, workflow)

    assert "release workflow missing accepted-platform-evidence-assets job" in errors


def test_publish_contract_rejects_malformed_mobaxterm_parity_registry() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")

    errors = checker.check_publish_contract(
        matrix,
        workflow,
        mobaxterm_parity_registry={"schema_version": 1, "policy": "", "accepted_evidence": []},
    )

    assert any("mobaxterm parity evidence policy missing" in error for error in errors)


def test_publish_contract_can_require_complete_mobaxterm_parity_registry() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")

    errors = checker.check_publish_contract(
        matrix,
        workflow,
        mobaxterm_parity_registry=_empty_mobaxterm_parity_registry(),
        require_mobaxterm_parity_complete=True,
    )

    assert any("missing required MobaXterm parity articles" in error for error in errors)


def test_publish_contract_can_require_platform_goal_targets() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")

    errors = checker.check_publish_contract(
        matrix,
        workflow,
        evidence_registry=_accepted_evidence_registry(),
        require_platform_goal_targets=True,
    )

    assert any("missing required accepted evidence targets" in error for error in errors)


def test_publish_contract_allows_complete_platform_goal_targets() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")

    errors = checker.check_publish_contract(
        matrix,
        workflow,
        evidence_registry=_accepted_evidence_registry(
            "linux-i386",
            "linux-armhf",
            "windows-xp-native-x86",
            "windows-xp-native-x64",
        ),
        require_platform_goal_targets=True,
    )

    assert not any("missing required accepted evidence targets" in error for error in errors)


def test_publish_contract_rejects_goal_target_evidence_for_wrong_release_tag() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")

    errors = checker.check_publish_contract(
        matrix,
        workflow,
        tag="v1.0.3",
        evidence_registry=_accepted_evidence_registry(
            "linux-i386",
            "linux-armhf",
            "windows-xp-native-x86",
            "windows-xp-native-x64",
        ),
        require_platform_goal_targets=True,
    )

    assert (
        "missing required accepted evidence targets for release_tag v1.0.3: "
        "['linux-armhf', 'linux-i386', 'windows-xp-native-x64', 'windows-xp-native-x86']"
    ) in errors


def test_publish_contract_allows_complete_synthetic_mobaxterm_parity_registry() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")

    errors = checker.check_publish_contract(
        matrix,
        workflow,
        mobaxterm_parity_registry=_complete_mobaxterm_parity_registry(),
        require_mobaxterm_parity_complete=True,
    )

    assert not any("mobaxterm parity evidence" in error for error in errors)
    assert not any("MobaXterm parity" in error for error in errors)


def test_release_assets_report_missing_expected_files(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()

    errors = checker.check_release_assets(tmp_path, matrix, tag="v1.0.2")

    assert any("missing expected files" in error for error in errors)


def test_release_assets_report_gated_extra_files(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    (tmp_path / "remote-ops-workspace-v1.0.2-linux-armhf.deb").write_text("native\n", encoding="utf-8")

    errors = checker.check_release_assets(
        tmp_path,
        matrix,
        tag="v1.0.2",
        evidence_registry=_empty_evidence_registry(),
    )

    assert any("gated native asset remote-ops-workspace-v1.0.2-linux-armhf.deb" in error for error in errors)


def test_release_assets_reject_accepted_evidence_hash_mismatch(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    _add_default_linux_asset(matrix, "remote-ops-workspace-v1.0.2-linux-i386.deb")
    _write_synthetic_release_assets(checker, matrix, tmp_path)

    errors = checker.check_release_assets(
        tmp_path,
        matrix,
        tag="v1.0.2",
        evidence_registry=_accepted_evidence_registry("linux-i386"),
    )

    assert (
        "release asset remote-ops-workspace-v1.0.2-linux-i386.deb SHA-256 does not match "
        "accepted evidence for linux-i386"
    ) in errors


def test_release_assets_allow_accepted_evidence_hash_match(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    registry = _accepted_evidence_registry("linux-i386")
    record = registry["accepted_evidence"][0]
    _add_default_linux_assets(matrix, record["artifact_sha256"])
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    _sync_evidence_artifact_hashes(record, tmp_path)
    _write_accepted_review_bundle_assets(record, tmp_path)

    errors = checker.check_release_assets(
        tmp_path,
        matrix,
        tag="v1.0.2",
        evidence_registry=registry,
    )

    assert errors == []


def test_release_assets_reject_accepted_evidence_missing_review_bundle(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    registry = _accepted_evidence_registry("linux-i386")
    record = registry["accepted_evidence"][0]
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    _write_accepted_native_assets(record, tmp_path)
    _sync_evidence_artifact_hashes(record, tmp_path)

    errors = checker.check_release_assets(
        tmp_path,
        matrix,
        tag="v1.0.2",
        evidence_registry=registry,
    )

    assert (
        "linux-i386 accepted evidence review bundle asset missing from release directory: "
        "extended-linux-evidence-bundle-linux-i386-v1.0.2.json"
    ) in errors


def test_release_assets_reject_accepted_evidence_review_bundle_hash_mismatch(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    registry = _accepted_evidence_registry("linux-i386")
    record = registry["accepted_evidence"][0]
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    _write_accepted_evidence_assets(record, tmp_path)
    _sync_evidence_artifact_hashes(record, tmp_path)
    bundle_name = record["review_bundle"]["archive"]["file"]
    (tmp_path / str(bundle_name)).write_bytes(b"tampered review bundle\n")

    errors = checker.check_release_assets(
        tmp_path,
        matrix,
        tag="v1.0.2",
        evidence_registry=registry,
    )

    assert (
        "release review bundle asset extended-linux-evidence-bundle-linux-i386-v1.0.2.zip "
        "SHA-256 does not match accepted evidence for linux-i386"
    ) in errors


def test_release_assets_reject_accepted_evidence_review_bundle_content_mismatch(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    registry = _accepted_evidence_registry("linux-i386")
    record = registry["accepted_evidence"][0]
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    _write_accepted_evidence_assets(record, tmp_path)
    review_bundle = record["review_bundle"]
    assert isinstance(review_bundle, dict)
    archive_record = review_bundle["archive"]
    sidecar_record = review_bundle["sha256s"]
    manifest_record = review_bundle["manifest"]
    assert isinstance(archive_record, dict)
    assert isinstance(sidecar_record, dict)
    assert isinstance(manifest_record, dict)
    archive_path = tmp_path / str(archive_record["file"])
    sidecar_path = tmp_path / str(sidecar_record["file"])
    manifest_path = tmp_path / str(manifest_record["file"])
    archive_path.write_bytes(b"not a review bundle zip\n")
    archive_record["size_bytes"] = archive_path.stat().st_size
    archive_record["sha256"] = _sha256(archive_path)
    sidecar_path.write_text(
        f"{_sha256(manifest_path)}  {manifest_path.name}\n"
        f"{_sha256(archive_path)}  {archive_path.name}\n",
        encoding="utf-8",
    )
    sidecar_record["size_bytes"] = sidecar_path.stat().st_size
    sidecar_record["sha256"] = _sha256(sidecar_path)

    errors = checker.check_release_assets(
        tmp_path,
        matrix,
        tag="v1.0.2",
        evidence_registry=registry,
    )

    assert any(
        "linux-i386 review bundle archive is not a readable ZIP" in error
        for error in errors
    )


def test_release_assets_reject_review_bundle_sidecar_missing_archive_reference(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    registry = _accepted_evidence_registry("linux-i386")
    record = registry["accepted_evidence"][0]
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    _write_accepted_evidence_assets(record, tmp_path)
    _sync_evidence_artifact_hashes(record, tmp_path)
    review_bundle = record["review_bundle"]
    assert isinstance(review_bundle, dict)
    sidecar_record = review_bundle["sha256s"]
    assert isinstance(sidecar_record, dict)
    sidecar_path = tmp_path / str(sidecar_record["file"])
    sidecar_path.write_text(sidecar_path.read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8")
    sidecar_record["size_bytes"] = sidecar_path.stat().st_size
    sidecar_record["sha256"] = _sha256(sidecar_path)

    errors = checker.check_release_assets(
        tmp_path,
        matrix,
        tag="v1.0.2",
        evidence_registry=registry,
    )

    assert any(
        "checksum sidecars missing references for expected files" in error
        and "extended-linux-evidence-bundle-linux-i386-v1.0.2.zip" in error
        for error in errors
    )


def test_release_assets_allow_evidence_backed_assets_outside_default_matrix(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    registry = _accepted_evidence_registry("linux-i386")
    record = registry["accepted_evidence"][0]
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    _write_accepted_evidence_assets(record, tmp_path)
    _sync_evidence_artifact_hashes(record, tmp_path)

    errors = checker.check_release_assets(
        tmp_path,
        matrix,
        tag="v1.0.2",
        evidence_registry=registry,
    )

    assert errors == []


def test_release_assets_reject_accepted_evidence_missing_referenced_asset(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    _write_synthetic_release_assets(checker, matrix, tmp_path)

    errors = checker.check_release_assets(
        tmp_path,
        matrix,
        tag="v1.0.2",
        evidence_registry=_accepted_evidence_registry("linux-i386"),
    )

    assert (
        "linux-i386 accepted evidence release asset missing from release directory: "
        "remote-ops-workspace-v1.0.2-linux-i386.deb"
    ) in errors


def test_release_assets_accept_complete_synthetic_directory(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    _write_synthetic_release_assets(checker, matrix, tmp_path)

    errors = checker.check_release_assets(tmp_path, matrix, tag="v1.0.2")

    assert errors == []


def test_release_assets_reject_checksum_mismatch(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    checksum = tmp_path / "remote-ops-workspace-v1.0.2-SHA256SUMS.txt"
    checksum.write_text("0" * 64 + "  remote_ops_workspace-1.0.2-py3-none-any.whl\n", encoding="utf-8")

    errors = checker.check_release_assets(tmp_path, matrix, tag="v1.0.2")

    assert any("checksum mismatch" in error for error in errors)


def _write_synthetic_release_assets(checker, matrix: dict[str, object], root: Path) -> None:
    expected = checker.expected_release_assets(matrix, tag="v1.0.2")
    source_manifest_artifacts = checker.expected_source_manifest_artifacts(matrix, tag="v1.0.2")
    release_manifest = "remote-ops-workspace-v1.0.2-release-manifest.json"
    checksum_assets = {asset for asset in expected if asset.endswith("SHA256SUMS.txt")}

    for asset in sorted(expected - checksum_assets - {release_manifest}):
        (root / asset).write_bytes(f"{asset}\n".encode())

    manifest_payload = {
        "schema_version": 1,
        "artifacts": [
            {
                "file": f"dist/{asset}",
                "size_bytes": (root / asset).stat().st_size,
                "sha256": _sha256(root / asset),
            }
            for asset in sorted(source_manifest_artifacts)
        ],
    }
    (root / release_manifest).write_text(json.dumps(manifest_payload, indent=2) + "\n", encoding="utf-8")

    reference_assets = sorted(expected - checksum_assets)
    checksum_lines = "\n".join(f"{_sha256(root / asset)}  {asset}" for asset in reference_assets) + "\n"
    for checksum in checksum_assets:
        (root / checksum).write_text(checksum_lines, encoding="utf-8")


def _add_default_linux_asset(matrix: dict[str, object], asset: str) -> None:
    linux_job = next(job for job in matrix["default_github_release"]["native_jobs"] if job["job"] == "linux-native")
    linux_job["asset_patterns"].append(asset)


def _add_default_linux_assets(matrix: dict[str, object], assets: dict[str, object]) -> None:
    for asset in assets:
        _add_default_linux_asset(matrix, str(asset))


def _sync_evidence_artifact_hashes(record: dict[str, object], root: Path) -> None:
    hashes = record["artifact_sha256"]
    assert isinstance(hashes, dict)
    for asset in hashes:
        hashes[asset] = _sha256(root / str(asset))


def _write_accepted_evidence_assets(record: dict[str, object], root: Path) -> None:
    _write_accepted_native_assets(record, root)
    _sync_evidence_artifact_hashes(record, root)
    _write_accepted_review_bundle_assets(record, root)


def _write_accepted_native_assets(record: dict[str, object], root: Path) -> None:
    hashes = record["artifact_sha256"]
    assert isinstance(hashes, dict)
    assets = sorted(str(asset) for asset in hashes)
    sidecars = [asset for asset in assets if asset.endswith("SHA256SUMS.txt")]
    payloads = [asset for asset in assets if asset not in sidecars]
    for asset in payloads:
        (root / asset).write_bytes(f"{asset}\n".encode())
    checksum_lines = "\n".join(f"{_sha256(root / asset)}  {asset}" for asset in payloads) + "\n"
    for sidecar in sidecars:
        (root / sidecar).write_text(checksum_lines, encoding="utf-8")


def _write_accepted_review_bundle_assets(record: dict[str, object], root: Path) -> None:
    target = str(record["target"])
    if not target.startswith("linux-"):
        raise AssertionError(f"test helper only creates Linux review bundles, got {target}")
    _sync_evidence_artifact_hashes(record, root)
    finalizer = _load_script("finalize_platform_verified_evidence_record")
    bundle_helpers = _load_finalize_tests()
    release_tag = str(record["release_tag"])
    candidate = copy.deepcopy(record)
    candidate.pop("review_bundle")
    hashes = candidate["artifact_sha256"]
    assert isinstance(hashes, dict)
    artifact_archive_files = {
        str(name): (root / str(name)).read_bytes()
        for name in sorted(hashes)
    }
    with tempfile.TemporaryDirectory(prefix=f"{target}-bundle-", dir=root) as raw_tmp:
        work_root = Path(raw_tmp)
        candidate_path = work_root / f"platform-verified-evidence-{target}.json"
        builder_path = work_root / f"builder-identity-{target}.json"
        smoke_path = work_root / f"native-smoke-{target}.log"
        builder_path.write_text(json.dumps(candidate["builder_identity"], indent=2) + "\n", encoding="utf-8")
        bundle_helpers._write_linux_smoke_evidence(smoke_path, target, hashes)
        candidate["linux_smoke_evidence_sha256"] = {"native_smoke": _sha256(smoke_path)}
        record["linux_smoke_evidence_sha256"] = candidate["linux_smoke_evidence_sha256"]
        candidate_path.write_text(json.dumps(candidate, indent=2) + "\n", encoding="utf-8")
        manifest, archive, sidecar = bundle_helpers._write_bundle_files(
            work_root,
            stem=f"extended-linux-evidence-bundle-{target}-{release_tag}",
            bundle_type="extended-linux-native-evidence",
            target=target,
            release_tag=release_tag,
            manifest_records={
                "promotion_config_sha256": candidate["promotion_config_sha256"],
                "release_asset_urls": candidate["release_asset_urls"],
                "validated_commands": bundle_helpers._linux_validated_commands(candidate),
                "workflow": candidate["workflow"],
                "workflow_inputs": candidate["workflow_inputs"],
                "workflow_run_url": candidate["workflow_run_url"],
                "runner_labels": candidate["runner_labels"],
                "security_patch_evidence": candidate["builder_identity"]["security_patch_evidence"],
                "builder_evidence": bundle_helpers._file_record(builder_path),
                "smoke_evidence": [
                    bundle_helpers._smoke_file_record(smoke_path, smoke_id="native_smoke", name=smoke_path.name)
                ],
                "candidate_record": bundle_helpers._file_record(candidate_path),
                "artifacts": [
                    {
                        "file": str(name),
                        "size_bytes": (root / str(name)).stat().st_size,
                        "sha256": str(digest),
                    }
                    for name, digest in sorted(hashes.items())
                ],
            },
            archive_files={
                **artifact_archive_files,
                builder_path.name: builder_path.read_bytes(),
                smoke_path.name: smoke_path.read_bytes(),
                candidate_path.name: candidate_path.read_bytes(),
            },
        )
        errors, finalized = finalizer.finalize_platform_verified_evidence_record(
            candidate_record=candidate_path,
            bundle_manifest=manifest,
            bundle_archive=archive,
            bundle_sha256s=sidecar,
        )
        for bundle_file in (manifest, archive, sidecar):
            shutil.copyfile(bundle_file, root / bundle_file.name)
    assert errors == []
    record.clear()
    record.update(finalized)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_matrix() -> dict[str, object]:
    return json.loads(Path("configs/release_matrix.json").read_text(encoding="utf-8"))


def _empty_evidence_registry() -> dict[str, object]:
    return {"schema_version": 1, "accepted_evidence": []}


def _empty_mobaxterm_parity_registry() -> dict[str, object]:
    return {
        "schema_version": 1,
        "policy": MOBA_PARITY_POLICY,
        "accepted_evidence": [],
    }


def _complete_mobaxterm_parity_registry() -> dict[str, object]:
    checker = _load_mobaxterm_checker()
    return {
        "schema_version": 1,
        "policy": MOBA_PARITY_POLICY,
        "accepted_evidence": [
            _mobaxterm_parity_record(article_id, spec)
            for article_id, spec in sorted(checker.ARTICLE_SPECS.items())
        ],
    }


def _mobaxterm_parity_record(article_id: str, spec) -> dict[str, object]:
    artifact_name = f"{article_id}-evidence.zip"
    return {
        "article_id": article_id,
        "status": "accepted",
        "evidence_type": spec.evidence_type,
        "release_tag": "v1.0.2",
        "release_target": "windows-x64",
        "validation_command": spec.validation_command,
        "evidence_file_sha256": "a" * 64,
        "evidence_assets_sha256": {f"{article_id}.json": "b" * 64},
        "release_asset_urls": [
            f"https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/{artifact_name}"
        ],
        "artifact_sha256": {artifact_name: "c" * 64},
        "checks": sorted(spec.required_checks),
        "validation_summary": {
            "passed": True,
            "errors": [],
            "summary": {"article_id": article_id},
        },
    }


def _accepted_evidence_registry(*targets: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [_accepted_evidence_record(target) for target in targets],
    }


def _accepted_evidence_record(target: str) -> dict[str, object]:
    if target in {"linux-i386", "linux-armhf"}:
        return _linux_accepted_evidence(target)
    return _xp_accepted_evidence(target)


def _linux_accepted_evidence(target: str) -> dict[str, object]:
    arch = "i386" if target == "linux-i386" else "armhf"
    rpm_arch = "i686" if target == "linux-i386" else "armv7hl"
    artifact_arch = "i686" if target == "linux-i386" else "armhf"
    artifact = "extended-linux-i386-native-evidence" if target == "linux-i386" else "extended-linux-armhf-native-evidence"
    base_url = "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2"
    release_asset_urls = [
        f"{base_url}/remote-ops-workspace-v1.0.2-linux-{arch}.deb",
        f"{base_url}/remote-ops-workspace-v1.0.2-linux-{rpm_arch}.rpm",
        f"{base_url}/remote-ops-workspace-v1.0.2-linux-{artifact_arch}.AppImage",
        f"{base_url}/remote-ops-workspace-v1.0.2-linux-{artifact_arch}-native.tar.gz",
        f"{base_url}/remote-ops-workspace-v1.0.2-linux-{artifact_arch}-native-manifest.json",
        f"{base_url}/remote-ops-workspace-v1.0.2-linux-{artifact_arch}-native-SHA256SUMS.txt",
    ]
    builder_identity = _builder_identity(target)
    return {
        "target": target,
        "evidence_type": "extended-linux-native",
        "status": "accepted",
        "readiness_percent": 100.0,
        "release_tag": "v1.0.2",
        "promotion_config_sha256": _promotion_config_sha256(),
        "workflow": ".github/workflows/extended-platform-evidence.yml",
        "workflow_inputs": {
            "target": target,
            "release_tag": "v1.0.2",
            "release_asset_base_url": base_url,
        },
        "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "artifact_name": artifact,
        "runner_labels": ["self-hosted", "linux", arch],
        "builder_identity": builder_identity,
        "builder_identity_sha256": _json_sha256(builder_identity),
        "native_build_command": (
            f"TARGET_ARCH={arch} PYTHON_BIN=.venv-native/bin/python bash scripts/make_linux_native.sh"
        ),
        "native_smoke_command": (
            f"bash scripts/smoke_linux_native.sh --arch {arch} --dist native-dist/linux "
            f"--target {target} --workflow-run-url https://github.com/example/remote-ops-workspace/actions/runs/12345"
        ),
        "linux_smoke_evidence_sha256": _linux_smoke_hashes(),
        "artifact_validation_command": (
            f"python scripts/check_platform_promotion_artifacts.py --target {target} "
            "--assets-dir native-dist/linux --tag v1.0.2"
        ),
        "checks": [
            "builder_preflight",
            "native_build",
            "native_smoke",
            "artifact_validation",
            "release_asset_attachment",
        ],
        "release_asset_urls": release_asset_urls,
        "artifact_sha256": _artifact_hashes_from_urls(release_asset_urls),
        "release_asset_source": _release_asset_source(
            target,
            artifact,
            release_asset_urls,
            include_review_bundle=True,
        ),
        "review_bundle": _review_bundle(target),
    }


def _xp_accepted_evidence(target: str) -> dict[str, object]:
    arch = "x86" if target.endswith("x86") else "x64"
    smoke_ids = sorted(
        [
            "cli_launch",
            "gui_or_legacy_host_ui_launch",
            "loopback_profile_dry_run",
            "artifact_manifest_validation",
            "legacy_crypto_profile_scoped",
            "modern_defaults_unchanged",
        ]
    )
    os_summary: dict[str, object] = {
        "name": "Windows XP",
        "architecture": arch,
        "service_pack": "SP3" if arch == "x86" else "SP2",
    }
    if arch == "x64":
        os_summary["edition"] = "Professional x64 Edition"
    release_asset_urls = [
        f"https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/remote-ops-workspace-v1.0.2-windows-xp-{arch}-native.zip",
        f"https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/remote-ops-workspace-v1.0.2-windows-xp-{arch}-native-manifest.json",
        f"https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/remote-ops-workspace-v1.0.2-windows-xp-{arch}-native-SHA256SUMS.txt",
    ]
    return {
        "target": target,
        "evidence_type": "windows-xp-native-host",
        "status": "accepted",
        "readiness_percent": 100.0,
        "release_tag": "v1.0.2",
        "promotion_config_sha256": _promotion_config_sha256(),
        "architecture": arch,
        "separate_legacy_toolchain": True,
        "current_python_pyqt6_stack": False,
        "xp_evidence_sha256": "b" * 64,
        "xp_evidence_contract_sha256": _xp_native_evidence_contract_sha256(),
        "xp_host_identity_sha256": _json_sha256(_xp_host_identity(target)),
        "xp_evidence_summary": {
            "target": target,
            "release_tag": "v1.0.2",
            "host_identity": _xp_host_identity(target),
            "os": os_summary,
            "toolchain": {
                "separate_legacy_toolchain": True,
                "current_python_pyqt6_stack": False,
            },
            "security": {
                "legacy_crypto_profile_scoped": True,
                "modern_defaults_unchanged": True,
                "weak_crypto_global_default": False,
                "patch_evidence": _security_patch_evidence(),
            },
            "smoke_ids": sorted(
                [
                    "cli_launch",
                    "gui_or_legacy_host_ui_launch",
                    "loopback_profile_dry_run",
                    "artifact_manifest_validation",
                    "legacy_crypto_profile_scoped",
                    "modern_defaults_unchanged",
                ]
            ),
            "smoke_evidence_files": {
                smoke_id: f"xp-smoke-evidence/{smoke_id}.txt"
                for smoke_id in smoke_ids
            },
            "smoke_commands": {
                smoke_id: (
                    f"scripts/xp_smoke_runner.cmd --target {target} --release-tag v1.0.2 "
                    f"--smoke-id {smoke_id} --evidence-file xp-smoke-evidence/{smoke_id}.txt"
                )
                for smoke_id in smoke_ids
            },
        },
        "xp_smoke_evidence_sha256": {
            "cli_launch": "c" * 64,
            "gui_or_legacy_host_ui_launch": "d" * 64,
            "loopback_profile_dry_run": "e" * 64,
            "artifact_manifest_validation": "f" * 64,
            "legacy_crypto_profile_scoped": "1" * 64,
            "modern_defaults_unchanged": "2" * 64,
        },
        "native_evidence_validation_command": (
            "python scripts/check_xp_native_evidence.py "
            f"--evidence evidence/{target}/xp-evidence.json --assets-dir native-dist/windows-xp"
        ),
        "artifact_validation_command": (
            f"python scripts/check_platform_promotion_artifacts.py --target {target} "
            "--assets-dir native-dist/windows-xp --tag v1.0.2"
        ),
        "checks": [
            "xp_native_evidence_validation",
            "artifact_validation",
            "vm_or_host_smoke",
            "legacy_crypto_profile_scoped",
            "modern_defaults_unchanged",
            "release_asset_attachment",
        ],
        "release_asset_urls": release_asset_urls,
        "artifact_sha256": _artifact_hashes_from_urls(release_asset_urls),
        "release_asset_source": _release_asset_source(
            target,
            f"xp-native-evidence-{target}-v1.0.2",
            release_asset_urls,
            include_review_bundle=True,
        ),
        "review_bundle": _review_bundle(target),
    }


def _artifact_hashes_from_urls(urls: list[str]) -> dict[str, str]:
    return {Path(url).name: "a" * 64 for url in urls}


def _release_asset_source(
    target: str,
    artifact_name: str,
    release_asset_urls: list[str],
    *,
    include_review_bundle: bool,
) -> dict[str, object]:
    contains_files = {Path(url).name for url in release_asset_urls}
    if include_review_bundle:
        review_bundle = _review_bundle(target)
        contains_files.update(
            str(record.get("file", ""))
            for record in (
                review_bundle["manifest"],
                review_bundle["archive"],
                review_bundle["sha256s"],
            )
            if isinstance(record, dict)
        )
    return {
        "type": "github-actions-artifact",
        "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "artifact_name": artifact_name,
        "contains_files": sorted(contains_files),
    }


def _linux_smoke_hashes() -> dict[str, str]:
    return {"native_smoke": "6" * 64}


def _review_bundle(target: str, *, release_tag: str = "v1.0.2") -> dict[str, object]:
    if target.startswith("linux-"):
        stem = f"extended-linux-evidence-bundle-{target}-{release_tag}"
        bundle_type = "extended-linux-native-evidence"
    else:
        stem = f"xp-native-evidence-bundle-{target}-{release_tag}"
        bundle_type = "windows-xp-native-host-evidence"
    base_url = f"https://github.com/example/remote-ops-workspace/releases/download/{release_tag}"
    return {
        "bundle_type": bundle_type,
        "manifest": {"file": f"{stem}.json", "sha256": "3" * 64, "size_bytes": 123},
        "archive": {"file": f"{stem}.zip", "sha256": "4" * 64, "size_bytes": 456},
        "sha256s": {"file": f"{stem}-SHA256SUMS.txt", "sha256": "5" * 64, "size_bytes": 78},
        "release_asset_urls": [
            f"{base_url}/{stem}.json",
            f"{base_url}/{stem}.zip",
            f"{base_url}/{stem}-SHA256SUMS.txt",
        ],
}


def _xp_host_identity(target: str) -> dict[str, object]:
    arch = "x86" if target.endswith("x86") else "x64"
    os_summary: dict[str, object] = {
        "name": "Windows XP",
        "architecture": arch,
        "service_pack": "SP3" if arch == "x86" else "SP2",
    }
    if arch == "x64":
        os_summary["edition"] = "Professional x64 Edition"
    return {
        "schema_version": 1,
        "target": target,
        "release_tag": "v1.0.2",
        "host_label": f"xp-{arch}-lab-01",
        "evidence_run_id": f"xp-{arch}-1-0-2-20260620t120000z",
        "observed_at_utc": "2026-06-20T12:00:00Z",
        "operator_private_data_redacted": True,
        "os": os_summary,
        "toolchain": {
            "separate_legacy_toolchain": True,
            "current_python_pyqt6_stack": False,
            "description": "Separate legacy XP-capable native host toolchain",
        },
    }


def _promotion_config_sha256() -> str:
    data = json.loads(Path("configs/platform_parity_promotion.json").read_text(encoding="utf-8"))
    return _json_sha256(data)


def _xp_native_evidence_contract_sha256() -> str:
    data = json.loads(Path("configs/xp_native_evidence_contract.json").read_text(encoding="utf-8"))
    return _json_sha256(data)


def _json_sha256(data: dict[str, object]) -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _builder_identity(target: str) -> dict[str, object]:
    machine = "i686" if target == "linux-i386" else "armv7l"
    dpkg_arch = "i386" if target == "linux-i386" else "armhf"
    return {
        "schema_version": 1,
        "target": target,
        "release_tag": "v1.0.2",
        "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "host_identity": _linux_host_identity(target),
        "sudo_non_interactive": True,
        "sys_platform": "linux",
        "platform_machine": machine,
        "uname_machine": machine,
        "dpkg_architecture": dpkg_arch,
        "userland_bits": "32",
        "python_version": "3.12.0",
        "required_tools": {
            "bash": "/usr/bin/bash",
            "curl": "/usr/bin/curl",
            "dpkg": "/usr/bin/dpkg",
            "dpkg-deb": "/usr/bin/dpkg-deb",
            "getconf": "/usr/bin/getconf",
            "openssl": "/usr/bin/openssl",
            "rpm": "/usr/bin/rpm",
            "rpmbuild": "/usr/bin/rpmbuild",
            "sha256sum": "/usr/bin/sha256sum",
            "sudo": "/usr/bin/sudo",
            "tar": "/usr/bin/tar",
        },
        "security_patch_evidence": _security_patch_evidence(),
    }


def _linux_host_identity(target: str, release_tag: str = "v1.0.2") -> dict[str, object]:
    return {
        "schema_version": 1,
        "target": target,
        "release_tag": release_tag,
        "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "host_label": f"{target}-builder",
        "evidence_run_id": f"{target}-{release_tag.removeprefix('v').replace('.', '-')}-run-12345",
        "observed_at_utc": "2026-06-20T12:00:00Z",
        "operator_private_data_redacted": True,
    }


def _security_patch_evidence() -> dict[str, object]:
    return {
        "python_ssl_openssl": "OpenSSL 3.0.13",
        "openssl_cli_version": "OpenSSL 3.0.13",
        "tls_minimum_modern_profiles": "TLS 1.2",
        "tls_preferred_modern_profiles": "TLS 1.3",
        "legacy_compatibility_profile": "isolated-opt-in",
        "cve_patch_reviewed": True,
    }


def _load_checker():
    path = Path("scripts/check_release_publish_assets.py")
    spec = importlib.util.spec_from_file_location("check_release_publish_assets_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_script(name: str):
    path = Path("scripts") / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_finalize_tests():
    path = Path("tests/test_finalize_platform_verified_evidence_record.py")
    spec = importlib.util.spec_from_file_location("finalize_platform_verified_evidence_test_helpers_for_release", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_mobaxterm_checker():
    path = Path("scripts/check_mobaxterm_parity_evidence.py")
    spec = importlib.util.spec_from_file_location("check_mobaxterm_parity_evidence_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

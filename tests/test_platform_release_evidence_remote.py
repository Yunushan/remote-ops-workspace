from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import sys
from pathlib import Path
from typing import Any


def test_remote_release_audit_reports_missing_goal_evidence() -> None:
    checker = _load_checker()
    registry = _empty_registry()
    promotion = checker.read_json(checker.PROMOTION_PATH)
    release = _release_with_assets([])

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        workflow_runs_by_workflow={
            ".github/workflows/extended-platform-evidence.yml": {"workflow_runs": []},
            ".github/workflows/xp-native-evidence.yml": {"workflow_runs": []},
        },
        release_tag="v1.0.2",
        required_targets=checker.PROTECTED_GOAL_TARGETS,
        require_source_runs=True,
    )

    assert any(
        "missing required accepted evidence targets for release_tag v1.0.2" in error
        and "linux-i386" in error
        for error in errors
    )
    assert any(
        "linux-i386 remote release v1.0.2 missing protected evidence assets" in error
        and "remote-ops-workspace-v1.0.2-linux-i386.deb" in error
        and "platform-verified-evidence-linux-i386-final.json" in error
        for error in errors
    )
    assert (
        "windows-xp-native-x64 accepted evidence record missing; cannot verify release source run"
        in errors
    )


def test_remote_release_audit_accepts_bound_linux_record(tmp_path: Path) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    registry = _registry_with(record)
    promotion = checker.read_json(checker.PROMOTION_PATH)
    required_assets = checker.required_release_assets_by_target(
        promotion,
        release_tag="v1.0.2",
        targets=("linux-i386",),
    )
    release = _release_with_record_assets(checker, record, sorted(required_assets["linux-i386"]))

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        workflow_runs_by_workflow=_workflow_runs_for(record),
        source_artifacts_by_run=_source_artifacts_for(record),
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_source_runs=True,
    )

    assert errors == []


def test_remote_release_audit_accepts_exact_source_run_metadata(tmp_path: Path) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    registry = _registry_with(record)
    promotion = checker.read_json(checker.PROMOTION_PATH)
    required_assets = checker.required_release_assets_by_target(
        promotion,
        release_tag="v1.0.2",
        targets=("linux-i386",),
    )
    release = _release_with_record_assets(checker, record, sorted(required_assets["linux-i386"]))

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        source_runs_by_run=_source_runs_for(record),
        workflow_runs_by_workflow={},
        source_artifacts_by_run=_source_artifacts_for(record),
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_source_runs=True,
    )

    assert errors == []


def test_remote_release_audit_accepts_release_tag_source_head(tmp_path: Path) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    registry = _registry_with(record)
    promotion = checker.read_json(checker.PROMOTION_PATH)
    required_assets = checker.required_release_assets_by_target(
        promotion,
        release_tag="v1.0.2",
        targets=("linux-i386",),
    )
    release = _release_with_record_assets(checker, record, sorted(required_assets["linux-i386"]))
    head_sha = record["release_asset_source"]["head_sha"]

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        workflow_runs_by_workflow={},
        tag_ref={"ref": "refs/tags/v1.0.2", "object": {"type": "commit", "sha": head_sha}},
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_tag_source_head=True,
    )

    assert errors == []


def test_remote_release_audit_rejects_release_tag_source_head_drift(tmp_path: Path) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    registry = _registry_with(record)
    promotion = checker.read_json(checker.PROMOTION_PATH)
    required_assets = checker.required_release_assets_by_target(
        promotion,
        release_tag="v1.0.2",
        targets=("linux-i386",),
    )
    release = _release_with_record_assets(checker, record, sorted(required_assets["linux-i386"]))
    expected_head = record["release_asset_source"]["head_sha"]

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        workflow_runs_by_workflow={},
        tag_ref={"ref": "refs/tags/v1.0.2", "object": {"type": "commit", "sha": "b" * 40}},
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_tag_source_head=True,
    )

    assert (
        f"remote release tag v1.0.2 Git object must resolve to accepted "
        f"release source head {expected_head}, got {'b' * 40}"
    ) in errors


def test_remote_release_audit_accepts_annotated_release_tag_source_head(tmp_path: Path) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    registry = _registry_with(record)
    promotion = checker.read_json(checker.PROMOTION_PATH)
    required_assets = checker.required_release_assets_by_target(
        promotion,
        release_tag="v1.0.2",
        targets=("linux-i386",),
    )
    release = _release_with_record_assets(checker, record, sorted(required_assets["linux-i386"]))
    head_sha = record["release_asset_source"]["head_sha"]
    tag_object_sha = "c" * 40

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        workflow_runs_by_workflow={},
        tag_ref={"ref": "refs/tags/v1.0.2", "object": {"type": "tag", "sha": tag_object_sha}},
        tag_object={
            "sha": tag_object_sha,
            "tag": "v1.0.2",
            "object": {"type": "commit", "sha": head_sha},
        },
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_tag_source_head=True,
    )

    assert errors == []


def test_remote_release_audit_requires_annotated_tag_object(tmp_path: Path) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    registry = _registry_with(record)
    promotion = checker.read_json(checker.PROMOTION_PATH)
    required_assets = checker.required_release_assets_by_target(
        promotion,
        release_tag="v1.0.2",
        targets=("linux-i386",),
    )
    release = _release_with_record_assets(checker, record, sorted(required_assets["linux-i386"]))
    tag_object_sha = "c" * 40

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        workflow_runs_by_workflow={},
        tag_ref={"ref": "refs/tags/v1.0.2", "object": {"type": "tag", "sha": tag_object_sha}},
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_tag_source_head=True,
    )

    assert f"release tag v1.0.2 annotated tag object metadata missing for {tag_object_sha}" in errors


def test_remote_release_audit_requires_exact_source_run_when_no_workflow_list(
    tmp_path: Path,
) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    registry = _registry_with(record)
    promotion = checker.read_json(checker.PROMOTION_PATH)
    required_assets = checker.required_release_assets_by_target(
        promotion,
        release_tag="v1.0.2",
        targets=("linux-i386",),
    )
    release = _release_with_record_assets(checker, record, sorted(required_assets["linux-i386"]))
    source_runs = _source_runs_for(record)
    source_runs["https://github.com/example/remote-ops-workspace/actions/runs/99999"] = (
        source_runs.pop("https://github.com/example/remote-ops-workspace/actions/runs/12345")
    )

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        source_runs_by_run=source_runs,
        workflow_runs_by_workflow={},
        source_artifacts_by_run=_source_artifacts_for(record),
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_source_runs=True,
    )

    assert (
        "linux-i386 exact source workflow run metadata missing for "
        "https://github.com/example/remote-ops-workspace/actions/runs/12345"
    ) in errors


def test_remote_release_audit_rejects_unexpected_protected_assets(tmp_path: Path) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    registry = _registry_with(record)
    promotion = checker.read_json(checker.PROMOTION_PATH)
    required_assets = checker.required_release_assets_by_target(
        promotion,
        release_tag="v1.0.2",
        targets=("linux-i386",),
    )
    release = _release_with_record_assets(checker, record, sorted(required_assets["linux-i386"]))
    release["assets"].extend(
        [
            {"name": "platform-verified-evidence-linux-i386.json"},
            {"name": "extended-linux-evidence-bundle-linux-armhf-v1.0.1.zip"},
            {"name": "remote-ops-workspace-v1.0.1-windows-xp-x64-native.zip"},
            {"name": "release-notes-v1.0.2.txt"},
        ]
    )

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        workflow_runs_by_workflow=_workflow_runs_for(record),
        source_artifacts_by_run=_source_artifacts_for(record),
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_source_runs=True,
    )

    assert (
        "linux-i386 remote release v1.0.2 contains protected platform assets "
        "not expected for this audited evidence scope: "
        "['platform-verified-evidence-linux-i386.json']"
    ) in errors
    assert (
        "linux-armhf remote release v1.0.2 contains protected platform assets "
        "not expected for this audited evidence scope: "
        "['extended-linux-evidence-bundle-linux-armhf-v1.0.1.zip']"
    ) in errors
    assert (
        "windows-xp-native-x64 remote release v1.0.2 contains protected platform assets "
        "not expected for this audited evidence scope: "
        "['remote-ops-workspace-v1.0.1-windows-xp-x64-native.zip']"
    ) in errors
    assert not any("release-notes-v1.0.2.txt" in error for error in errors)


def test_remote_release_audit_rejects_failed_source_run(tmp_path: Path) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    registry = _registry_with(record)
    promotion = checker.read_json(checker.PROMOTION_PATH)
    required_assets = checker.required_release_assets_by_target(
        promotion,
        release_tag="v1.0.2",
        targets=("linux-i386",),
    )
    release = _release_with_record_assets(checker, record, sorted(required_assets["linux-i386"]))
    workflow_runs = _workflow_runs_for(record)
    workflow = str(record["release_asset_source"]["workflow"])
    workflow_runs[workflow]["workflow_runs"][0]["conclusion"] = "failure"

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        workflow_runs_by_workflow=workflow_runs,
        source_artifacts_by_run=_source_artifacts_for(record),
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_source_runs=True,
    )

    assert "linux-i386 source workflow run conclusion must be success, got 'failure'" in errors


def test_remote_release_audit_rejects_published_asset_metadata_mismatch(tmp_path: Path) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    registry = _registry_with(record)
    promotion = checker.read_json(checker.PROMOTION_PATH)
    required_assets = checker.required_release_assets_by_target(
        promotion,
        release_tag="v1.0.2",
        targets=("linux-i386",),
    )
    release = _release_with_record_assets(checker, record, sorted(required_assets["linux-i386"]))
    deb_asset = _release_asset(release, "remote-ops-workspace-v1.0.2-linux-i386.deb")
    deb_asset["state"] = "starter"
    deb_asset["digest"] = f"sha256:{'b' * 64}"
    deb_asset["browser_download_url"] = (
        "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/wrong.deb"
    )
    bundle_asset = _release_asset(
        release,
        "extended-linux-evidence-bundle-linux-i386-v1.0.2.zip",
    )
    bundle_asset["size"] = 1
    final_record_asset = _release_asset(release, "platform-verified-evidence-linux-i386-final.json")
    final_record_asset["digest"] = f"sha256:{'c' * 64}"
    final_record_asset["size"] = 2

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        workflow_runs_by_workflow=_workflow_runs_for(record),
        source_artifacts_by_run=_source_artifacts_for(record),
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_source_runs=True,
    )

    assert (
        "linux-i386 remote release asset remote-ops-workspace-v1.0.2-linux-i386.deb "
        "state must be uploaded, got 'starter'"
    ) in errors
    assert (
        "linux-i386 remote release asset remote-ops-workspace-v1.0.2-linux-i386.deb "
        "digest must be "
        f"sha256:{'a' * 64}, got 'sha256:{'b' * 64}'"
    ) in errors
    assert any(
        "linux-i386 remote release asset remote-ops-workspace-v1.0.2-linux-i386.deb "
        "browser_download_url must be "
        in error
        and "wrong.deb" in error
        for error in errors
    )
    assert (
        "linux-i386 remote release asset extended-linux-evidence-bundle-linux-i386-v1.0.2.zip "
        "size must be 456, got 1"
    ) in errors
    assert any(
        "linux-i386 remote release asset platform-verified-evidence-linux-i386-final.json "
        "digest must be "
        in error
        and f"got 'sha256:{'c' * 64}'" in error
        for error in errors
    )
    assert any(
        "linux-i386 remote release asset platform-verified-evidence-linux-i386-final.json "
        "size must be "
        in error
        and "got 2" in error
        for error in errors
    )


def test_remote_release_audit_verifies_final_record_asset_bytes(tmp_path: Path) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    registry = _registry_with(record)
    promotion = checker.read_json(checker.PROMOTION_PATH)
    required_assets = checker.required_release_assets_by_target(
        promotion,
        release_tag="v1.0.2",
        targets=("linux-i386",),
    )
    release = _release_with_record_assets(checker, record, sorted(required_assets["linux-i386"]))

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        source_runs_by_run=_source_runs_for(record),
        workflow_runs_by_workflow={},
        source_artifacts_by_run=_source_artifacts_for(record),
        final_record_bytes_by_url={
            record["finalized_record_release_asset_url"]: checker.canonical_public_record_bytes(record)
        },
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_source_runs=True,
        require_final_record_bytes=True,
    )

    assert errors == []


def test_remote_release_audit_verifies_published_release_asset_bytes(tmp_path: Path) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    release_asset_bytes = _bind_release_asset_bytes(checker, record)
    registry = _registry_with(record)
    promotion = checker.read_json(checker.PROMOTION_PATH)
    required_assets = checker.required_release_assets_by_target(
        promotion,
        release_tag="v1.0.2",
        targets=("linux-i386",),
    )
    release = _release_with_record_assets(checker, record, sorted(required_assets["linux-i386"]))

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        source_runs_by_run=_source_runs_for(record),
        workflow_runs_by_workflow={},
        source_artifacts_by_run=_source_artifacts_for(record),
        release_asset_bytes_by_url=release_asset_bytes,
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_source_runs=True,
        require_release_asset_bytes=True,
    )

    assert errors == []


def test_remote_release_audit_rejects_missing_published_release_asset_bytes(
    tmp_path: Path,
) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    registry = _registry_with(record)
    promotion = checker.read_json(checker.PROMOTION_PATH)
    required_assets = checker.required_release_assets_by_target(
        promotion,
        release_tag="v1.0.2",
        targets=("linux-i386",),
    )
    release = _release_with_record_assets(checker, record, sorted(required_assets["linux-i386"]))

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        source_runs_by_run=_source_runs_for(record),
        workflow_runs_by_workflow={},
        source_artifacts_by_run=_source_artifacts_for(record),
        release_asset_bytes_by_url={},
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_source_runs=True,
        require_release_asset_bytes=True,
    )

    assert any(
        "linux-i386 published release asset bytes missing for "
        "remote-ops-workspace-v1.0.2-linux-i386.deb at "
        "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/"
        "remote-ops-workspace-v1.0.2-linux-i386.deb"
        in error
        for error in errors
    )


def test_remote_release_audit_rejects_published_release_asset_byte_drift(
    tmp_path: Path,
) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    release_asset_bytes = _bind_release_asset_bytes(checker, record)
    zip_asset = "extended-linux-evidence-bundle-linux-i386-v1.0.2.zip"
    zip_url = next(
        str(asset["url"])
        for asset in checker.expected_release_asset_byte_sources(record)
        if asset["filename"] == zip_asset
    )
    release_asset_bytes[zip_url] = b"tampered release asset bytes\n"
    registry = _registry_with(record)
    promotion = checker.read_json(checker.PROMOTION_PATH)
    required_assets = checker.required_release_assets_by_target(
        promotion,
        release_tag="v1.0.2",
        targets=("linux-i386",),
    )
    release = _release_with_record_assets(checker, record, sorted(required_assets["linux-i386"]))

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        source_runs_by_run=_source_runs_for(record),
        workflow_runs_by_workflow={},
        source_artifacts_by_run=_source_artifacts_for(record),
        release_asset_bytes_by_url=release_asset_bytes,
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_source_runs=True,
        require_release_asset_bytes=True,
    )

    assert any(
        "linux-i386 published release asset extended-linux-evidence-bundle-linux-i386-v1.0.2.zip "
        "bytes SHA-256 must match accepted evidence"
        in error
        for error in errors
    )
    assert any(
        "linux-i386 published release asset extended-linux-evidence-bundle-linux-i386-v1.0.2.zip "
        "byte size must match accepted evidence"
        in error
        for error in errors
    )


def test_remote_release_audit_rejects_missing_final_record_asset_bytes(tmp_path: Path) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    registry = _registry_with(record)
    promotion = checker.read_json(checker.PROMOTION_PATH)
    required_assets = checker.required_release_assets_by_target(
        promotion,
        release_tag="v1.0.2",
        targets=("linux-i386",),
    )
    release = _release_with_record_assets(checker, record, sorted(required_assets["linux-i386"]))

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        source_runs_by_run=_source_runs_for(record),
        workflow_runs_by_workflow={},
        source_artifacts_by_run=_source_artifacts_for(record),
        final_record_bytes_by_url={},
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_source_runs=True,
        require_final_record_bytes=True,
    )

    assert (
        "linux-i386 finalized accepted-record release asset bytes missing for "
        f"{record['finalized_record_release_asset_url']}"
    ) in errors


def test_remote_release_audit_rejects_final_record_asset_byte_drift(tmp_path: Path) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    registry = _registry_with(record)
    promotion = checker.read_json(checker.PROMOTION_PATH)
    required_assets = checker.required_release_assets_by_target(
        promotion,
        release_tag="v1.0.2",
        targets=("linux-i386",),
    )
    release = _release_with_record_assets(checker, record, sorted(required_assets["linux-i386"]))

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        source_runs_by_run=_source_runs_for(record),
        workflow_runs_by_workflow={},
        source_artifacts_by_run=_source_artifacts_for(record),
        final_record_bytes_by_url={record["finalized_record_release_asset_url"]: b"{}\n"},
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_source_runs=True,
        require_final_record_bytes=True,
    )

    assert (
        "linux-i386 finalized accepted-record release asset bytes must match "
        "canonical public accepted registry record"
    ) in errors


def test_remote_release_audit_requires_exact_source_run_metadata(tmp_path: Path) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    registry = _registry_with(record)
    promotion = checker.read_json(checker.PROMOTION_PATH)
    required_assets = checker.required_release_assets_by_target(
        promotion,
        release_tag="v1.0.2",
        targets=("linux-i386",),
    )
    release = _release_with_record_assets(checker, record, sorted(required_assets["linux-i386"]))
    workflow_runs = _workflow_runs_for(record)
    workflow = str(record["release_asset_source"]["workflow"])
    run = workflow_runs[workflow]["workflow_runs"][0]
    run["html_url"] = "https://github.com/example/remote-ops-workspace/actions/runs/99999"
    run.pop("run_attempt")
    run.pop("path")

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        workflow_runs_by_workflow=workflow_runs,
        source_artifacts_by_run=_source_artifacts_for(record),
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_source_runs=True,
    )

    assert (
        "linux-i386 source workflow run html_url must match accepted record "
        "https://github.com/example/remote-ops-workspace/actions/runs/12345, "
        "got 'https://github.com/example/remote-ops-workspace/actions/runs/99999'"
    ) in errors
    assert "linux-i386 source workflow run run_attempt must match accepted record 1, got None" in errors
    assert (
        "linux-i386 source workflow run path must be "
        "'.github/workflows/extended-platform-evidence.yml', got None"
    ) in errors


def test_remote_release_audit_requires_source_run_repository_binding(tmp_path: Path) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    registry = _registry_with(record)
    promotion = checker.read_json(checker.PROMOTION_PATH)
    required_assets = checker.required_release_assets_by_target(
        promotion,
        release_tag="v1.0.2",
        targets=("linux-i386",),
    )
    release = _release_with_record_assets(checker, record, sorted(required_assets["linux-i386"]))
    source_runs = _source_runs_for(record)
    run = next(iter(source_runs.values()))
    run["repository"]["full_name"] = "other/remote-ops-workspace"
    run["head_repository"]["full_name"] = "example/forked-remote-ops-workspace"

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        source_runs_by_run=source_runs,
        workflow_runs_by_workflow={},
        source_artifacts_by_run=_source_artifacts_for(record),
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_source_runs=True,
    )

    assert (
        "linux-i386 source workflow run repository.full_name must match accepted record "
        "example/remote-ops-workspace, got 'other/remote-ops-workspace'"
    ) in errors
    assert (
        "linux-i386 source workflow run head_repository.full_name must match accepted record "
        "example/remote-ops-workspace, got 'example/forked-remote-ops-workspace'"
    ) in errors


def test_remote_release_audit_requires_source_artifact_inventory(tmp_path: Path) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    registry = _registry_with(record)
    promotion = checker.read_json(checker.PROMOTION_PATH)
    required_assets = checker.required_release_assets_by_target(
        promotion,
        release_tag="v1.0.2",
        targets=("linux-i386",),
    )
    release = _release_with_record_assets(checker, record, sorted(required_assets["linux-i386"]))

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        workflow_runs_by_workflow=_workflow_runs_for(record),
        source_artifacts_by_run={},
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_source_runs=True,
    )

    assert (
        "linux-i386 source workflow artifacts missing for "
        "https://github.com/example/remote-ops-workspace/actions/runs/12345"
    ) in errors


def test_remote_release_audit_binds_source_artifact_repository_ids(tmp_path: Path) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    registry = _registry_with(record)
    promotion = checker.read_json(checker.PROMOTION_PATH)
    required_assets = checker.required_release_assets_by_target(
        promotion,
        release_tag="v1.0.2",
        targets=("linux-i386",),
    )
    release = _release_with_record_assets(checker, record, sorted(required_assets["linux-i386"]))
    source_artifacts = _source_artifacts_for(record)
    run_url = str(record["release_asset_source"]["workflow_run_url"])
    artifact = source_artifacts[run_url]["artifacts"][0]
    artifact["workflow_run"]["repository_id"] = 2222
    artifact["workflow_run"]["head_repository_id"] = 3333

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        source_runs_by_run=_source_runs_for(record),
        workflow_runs_by_workflow={},
        source_artifacts_by_run=source_artifacts,
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_source_runs=True,
    )

    assert (
        "linux-i386 source workflow artifact extended-linux-evidence-linux-i386-v1.0.2 "
        "workflow_run.repository_id must match exact source run repository id 1001, got 2222"
    ) in errors
    assert (
        "linux-i386 source workflow artifact extended-linux-evidence-linux-i386-v1.0.2 "
        "workflow_run.head_repository_id must match exact source run head repository id 1001, got 3333"
    ) in errors


def test_remote_release_audit_rejects_artifact_created_before_exact_run_start(
    tmp_path: Path,
) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    registry = _registry_with(record)
    promotion = checker.read_json(checker.PROMOTION_PATH)
    required_assets = checker.required_release_assets_by_target(
        promotion,
        release_tag="v1.0.2",
        targets=("linux-i386",),
    )
    release = _release_with_record_assets(checker, record, sorted(required_assets["linux-i386"]))
    source_artifacts = _source_artifacts_for(record)
    run_url = str(record["release_asset_source"]["workflow_run_url"])
    source_artifacts[run_url]["artifacts"][0]["created_at"] = "2026-06-30T11:59:59Z"

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        source_runs_by_run=_source_runs_for(record),
        workflow_runs_by_workflow={},
        source_artifacts_by_run=source_artifacts,
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_source_runs=True,
    )

    assert (
        "linux-i386 source workflow artifact extended-linux-evidence-linux-i386-v1.0.2 "
        "created_at must be at or after exact source run start 2026-06-30T12:00:00Z, "
        "got '2026-06-30T11:59:59Z'"
    ) in errors


def test_remote_release_audit_rejects_artifact_created_after_exact_run_update(
    tmp_path: Path,
) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    registry = _registry_with(record)
    promotion = checker.read_json(checker.PROMOTION_PATH)
    required_assets = checker.required_release_assets_by_target(
        promotion,
        release_tag="v1.0.2",
        targets=("linux-i386",),
    )
    release = _release_with_record_assets(checker, record, sorted(required_assets["linux-i386"]))
    source_artifacts = _source_artifacts_for(record)
    run_url = str(record["release_asset_source"]["workflow_run_url"])
    source_artifacts[run_url]["artifacts"][0]["created_at"] = "2026-06-30T12:05:01Z"

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        source_runs_by_run=_source_runs_for(record),
        workflow_runs_by_workflow={},
        source_artifacts_by_run=source_artifacts,
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_source_runs=True,
    )

    assert (
        "linux-i386 source workflow artifact extended-linux-evidence-linux-i386-v1.0.2 "
        "created_at must be at or before exact source run update 2026-06-30T12:05:00Z, "
        "got '2026-06-30T12:05:01Z'"
    ) in errors


def test_remote_release_audit_rejects_bad_source_artifact_metadata(tmp_path: Path) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    registry = _registry_with(record)
    promotion = checker.read_json(checker.PROMOTION_PATH)
    required_assets = checker.required_release_assets_by_target(
        promotion,
        release_tag="v1.0.2",
        targets=("linux-i386",),
    )
    release = _release_with_record_assets(checker, record, sorted(required_assets["linux-i386"]))
    source_artifacts = _source_artifacts_for(record)
    run_url = str(record["release_asset_source"]["workflow_run_url"])
    artifact = source_artifacts[run_url]["artifacts"][0]
    artifact["expired"] = True
    artifact["size_in_bytes"] = 0
    artifact["archive_download_url"] = "https://api.github.com/repos/example/remote-ops-workspace/actions/artifacts/99/zip"
    artifact["workflow_run"]["head_sha"] = "b" * 40

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        workflow_runs_by_workflow=_workflow_runs_for(record),
        source_artifacts_by_run=source_artifacts,
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_source_runs=True,
    )

    assert (
        "linux-i386 source workflow artifact extended-linux-evidence-linux-i386-v1.0.2 "
        "must not be expired, got True"
    ) in errors
    assert (
        "linux-i386 source workflow artifact extended-linux-evidence-linux-i386-v1.0.2 "
        "size_in_bytes must be positive, got 0"
    ) in errors
    assert any(
        "linux-i386 source workflow artifact extended-linux-evidence-linux-i386-v1.0.2 "
        "archive_download_url must be "
        in error
        and "artifacts/99/zip" in error
        for error in errors
    )
    assert (
        "linux-i386 source workflow artifact extended-linux-evidence-linux-i386-v1.0.2 "
        f"workflow_run.head_sha must match accepted record {'a' * 40}, got {('b' * 40)!r}"
    ) in errors


def test_required_release_assets_include_native_review_bundle_and_final_record() -> None:
    checker = _load_checker()
    promotion = checker.read_json(checker.PROMOTION_PATH)

    assets = checker.required_release_assets_by_target(
        promotion,
        release_tag="v1.0.2",
        targets=("linux-armhf", "windows-xp-native-x86"),
    )

    assert "remote-ops-workspace-v1.0.2-linux-armhf.deb" in assets["linux-armhf"]
    assert "extended-linux-evidence-bundle-linux-armhf-v1.0.2.zip" in assets["linux-armhf"]
    assert "platform-verified-evidence-linux-armhf-final.json" in assets["linux-armhf"]
    assert (
        "remote-ops-workspace-v1.0.2-windows-xp-x86-native.zip"
        in assets["windows-xp-native-x86"]
    )
    assert (
        "xp-native-evidence-bundle-windows-xp-native-x86-v1.0.2-SHA256SUMS.txt"
        in assets["windows-xp-native-x86"]
    )
    assert (
        "platform-verified-evidence-windows-xp-native-x86-final.json"
        in assets["windows-xp-native-x86"]
    )


def test_source_run_attempt_api_url_uses_exact_attempt_endpoint() -> None:
    checker = _load_checker()

    assert checker.source_run_attempt_api_url("example/remote-ops-workspace", "12345", 2) == (
        "https://api.github.com/repos/example/remote-ops-workspace/actions/runs/12345/attempts/2"
    )


def test_offline_require_source_runs_requires_exact_source_run_json(tmp_path: Path) -> None:
    checker = _load_checker()
    args = checker.parse_args(
        [
            "--release-tag",
            "v1.0.2",
            "--release-json",
            str(tmp_path / "release.json"),
            "--require-source-runs",
            "--workflow-runs-json",
            f".github/workflows/extended-platform-evidence.yml={tmp_path / 'runs.json'}",
            "--source-artifacts-json",
            f"https://github.com/example/remote-ops-workspace/actions/runs/12345={tmp_path / 'artifacts.json'}",
        ]
    )

    errors = checker.strict_arg_errors(args)

    assert (
        "--require-source-runs without --repository requires --source-run-json "
        "for exact accepted source run metadata"
    ) in errors


def test_offline_require_final_record_bytes_requires_final_record_json(tmp_path: Path) -> None:
    checker = _load_checker()
    args = checker.parse_args(
        [
            "--release-tag",
            "v1.0.2",
            "--release-json",
            str(tmp_path / "release.json"),
            "--require-final-record-bytes",
        ]
    )

    errors = checker.strict_arg_errors(args)

    assert "--require-final-record-bytes without --repository requires --final-record-json" in errors


def test_offline_require_release_asset_bytes_requires_release_asset(tmp_path: Path) -> None:
    checker = _load_checker()
    args = checker.parse_args(
        [
            "--release-tag",
            "v1.0.2",
            "--release-json",
            str(tmp_path / "release.json"),
            "--require-release-asset-bytes",
        ]
    )

    errors = checker.strict_arg_errors(args)

    assert "--require-release-asset-bytes without --repository requires --release-asset" in errors


def test_offline_require_tag_source_head_requires_tag_ref_json(tmp_path: Path) -> None:
    checker = _load_checker()
    args = checker.parse_args(
        [
            "--release-tag",
            "v1.0.2",
            "--release-json",
            str(tmp_path / "release.json"),
            "--require-tag-source-head",
        ]
    )

    errors = checker.strict_arg_errors(args)

    assert "--require-tag-source-head without --repository requires --tag-ref-json" in errors


def test_live_final_record_byte_loader_rejects_unscoped_url_before_fetch(
    tmp_path: Path,
) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    record["finalized_record_release_asset_url"] = (
        "https://example.com/remote-ops-workspace/releases/download/v1.0.2/"
        "platform-verified-evidence-linux-i386-final.json"
    )
    registry = _registry_with(record)
    args = checker.parse_args(
        [
            "--repository",
            "example/remote-ops-workspace",
            "--release-tag",
            "v1.0.2",
            "--require-final-record-bytes",
        ]
    )
    called = False
    original_fetch_bytes = checker.fetch_bytes

    def fake_fetch_bytes(url: str, *, timeout: float) -> tuple[bytes | None, list[str]]:
        nonlocal called
        called = True
        return b"{}", []

    checker.fetch_bytes = fake_fetch_bytes
    try:
        records_by_url, errors = checker.load_final_record_bytes(
            args,
            registry,
            ("linux-i386",),
        )
    finally:
        checker.fetch_bytes = original_fetch_bytes

    assert records_by_url == {}
    assert called is False
    assert (
        "linux-i386 finalized accepted-record release asset URL must be "
        "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/"
        "platform-verified-evidence-linux-i386-final.json before live byte fetch"
    ) in errors[0]


def test_live_release_asset_byte_loader_rejects_unscoped_url_before_fetch(
    tmp_path: Path,
) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    record["release_asset_urls"] = [
        str(url).replace("https://github.com/", "https://example.com/")
        for url in record["release_asset_urls"]
    ]
    record["review_bundle"]["release_asset_urls"] = [
        str(url).replace("https://github.com/", "https://example.com/")
        for url in record["review_bundle"]["release_asset_urls"]
    ]
    registry = _registry_with(record)
    args = checker.parse_args(
        [
            "--repository",
            "example/remote-ops-workspace",
            "--release-tag",
            "v1.0.2",
            "--require-release-asset-bytes",
        ]
    )
    called = False
    original_fetch_bytes = checker.fetch_bytes

    def fake_fetch_bytes(url: str, *, timeout: float) -> tuple[bytes | None, list[str]]:
        nonlocal called
        called = True
        return b"{}", []

    checker.fetch_bytes = fake_fetch_bytes
    try:
        assets_by_url, errors = checker.load_release_asset_bytes(
            args,
            registry,
            ("linux-i386",),
        )
    finally:
        checker.fetch_bytes = original_fetch_bytes

    assert assets_by_url == {}
    assert called is False
    assert any(
        "linux-i386 release asset remote-ops-workspace-v1.0.2-linux-i386.deb URL must be "
        "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/"
        "remote-ops-workspace-v1.0.2-linux-i386.deb before live byte fetch"
        in error
        for error in errors
    )


def test_github_api_headers_use_environment_token() -> None:
    checker = _load_checker()
    original_gh_token = os.environ.get("GH_TOKEN")
    original_github_token = os.environ.get("GITHUB_TOKEN")
    try:
        os.environ["GH_TOKEN"] = "secret-token"
        os.environ.pop("GITHUB_TOKEN", None)

        headers = checker.github_api_headers()
    finally:
        _restore_env("GH_TOKEN", original_gh_token)
        _restore_env("GITHUB_TOKEN", original_github_token)

    assert headers["Authorization"] == "Bearer secret-token"
    assert headers["X-GitHub-Api-Version"] == "2022-11-28"


def _restore_env(name: str, value: str | None) -> None:
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value


def _release_with_assets(asset_names: list[str]) -> dict[str, Any]:
    return {
        "tag_name": "v1.0.2",
        "draft": False,
        "prerelease": False,
        "assets": [{"name": name} for name in asset_names],
    }


def _release_with_record_assets(
    checker: Any,
    record: dict[str, Any],
    asset_names: list[str],
) -> dict[str, Any]:
    expected = checker.expected_published_assets(record)
    assets = []
    for index, name in enumerate(asset_names, start=1):
        metadata = expected.get(name, {})
        assets.append(
            {
                "name": name,
                "state": "uploaded",
                "size": metadata.get("size", 1024 + index),
                "digest": f"sha256:{metadata.get('sha256', '0' * 64)}",
                "browser_download_url": metadata.get(
                    "browser_download_url",
                    f"https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/{name}",
                ),
            }
        )
    return {
        "tag_name": "v1.0.2",
        "draft": False,
        "prerelease": False,
        "assets": assets,
    }


def _release_asset(release: dict[str, Any], name: str) -> dict[str, Any]:
    for asset in release["assets"]:
        if asset["name"] == name:
            return asset
    raise AssertionError(f"missing release asset fixture {name}")


def _bind_release_asset_bytes(checker: Any, record: dict[str, Any]) -> dict[str, bytes]:
    for filename in sorted(record["artifact_sha256"]):
        payload = f"published bytes for {filename}\n".encode()
        record["artifact_sha256"][filename] = hashlib.sha256(payload).hexdigest()
    for key in ("manifest", "archive", "sha256s"):
        bundle = record["review_bundle"][key]
        payload = f"published bytes for {bundle['file']}\n".encode()
        bundle["sha256"] = hashlib.sha256(payload).hexdigest()
        bundle["size_bytes"] = len(payload)
    return {
        str(asset["url"]): f"published bytes for {asset['filename']}\n".encode()
        for asset in checker.expected_release_asset_byte_sources(record)
    }


def _workflow_runs_for(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    source = record["release_asset_source"]
    run_url = str(source["workflow_run_url"])
    run_id = int(run_url.rstrip("/").rsplit("/", 1)[-1])
    workflow = str(source["workflow"])
    repository = _repository_from_run_url(run_url)
    return {
        workflow: {
            "workflow_runs": [
                {
                    "id": run_id,
                    "html_url": run_url,
                    "repository": {"full_name": repository, "id": 1001},
                    "head_repository": {"full_name": repository, "id": 1001},
                    "status": "completed",
                    "conclusion": "success",
                    "event": "workflow_dispatch",
                    "head_sha": source["head_sha"],
                    "run_attempt": source["run_attempt"],
                    "path": workflow,
                    "run_started_at": "2026-06-30T12:00:00Z",
                    "updated_at": "2026-06-30T12:05:00Z",
                }
            ]
        }
    }


def _source_runs_for(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    source = record["release_asset_source"]
    run_url = str(source["workflow_run_url"])
    run_id = int(run_url.rstrip("/").rsplit("/", 1)[-1])
    workflow = str(source["workflow"])
    repository = _repository_from_run_url(run_url)
    return {
        run_url: {
            "id": run_id,
            "htmlUrl": run_url,
            "repository": {"full_name": repository, "id": 1001},
            "head_repository": {"full_name": repository, "id": 1001},
            "status": "completed",
            "conclusion": "success",
            "event": "workflow_dispatch",
            "headSha": source["head_sha"],
            "attempt": source["run_attempt"],
            "path": workflow,
            "runStartedAt": "2026-06-30T12:00:00Z",
            "updatedAt": "2026-06-30T12:05:00Z",
        }
    }


def _repository_from_run_url(run_url: str) -> str:
    return run_url.split("https://github.com/", 1)[1].split("/actions/runs/", 1)[0]


def _source_artifacts_for(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    source = record["release_asset_source"]
    run_url = str(source["workflow_run_url"])
    run_id = int(run_url.rstrip("/").rsplit("/", 1)[-1])
    artifact_id = 98765
    return {
        run_url: {
            "total_count": 1,
            "artifacts": [
                {
                    "id": artifact_id,
                    "name": source["artifact_name"],
                    "archive_download_url": (
                        "https://api.github.com/repos/example/remote-ops-workspace/"
                        f"actions/artifacts/{artifact_id}/zip"
                    ),
                    "expired": False,
                    "size_in_bytes": 4096,
                    "created_at": "2026-06-30T12:03:00Z",
                    "workflow_run": {
                        "id": run_id,
                        "repository_id": 1001,
                        "head_repository_id": 1001,
                        "head_sha": source["head_sha"],
                    },
                }
            ],
        }
    }


def _registry_with(record: dict[str, Any]) -> dict[str, Any]:
    registry = json.loads(Path("configs/platform_verified_evidence.json").read_text(encoding="utf-8"))
    return {**registry, "accepted_evidence": [record]}


def _empty_registry() -> dict[str, Any]:
    registry = json.loads(Path("configs/platform_verified_evidence.json").read_text(encoding="utf-8"))
    return {**registry, "accepted_evidence": []}


def _load_checker() -> Any:
    path = Path("scripts/check_platform_release_evidence_remote.py")
    spec = importlib.util.spec_from_file_location("check_platform_release_evidence_remote", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_platform_verified_evidence_helpers() -> Any:
    path = Path("tests/test_platform_verified_evidence.py")
    spec = importlib.util.spec_from_file_location("platform_verified_remote_helpers", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

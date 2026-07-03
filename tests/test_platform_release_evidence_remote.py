from __future__ import annotations

import hashlib
import importlib.util
import io
import json
import os
import sys
import zipfile
from pathlib import Path
from typing import Any

import pytest


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
    assert (
        "linux-i386 source workflow .github/workflows/extended-platform-evidence.yml "
        "has no runs available for release_tag v1.0.2; dispatch native evidence before accepting this target"
        in errors
    )
    assert (
        "windows-xp-native-x86 source workflow .github/workflows/xp-native-evidence.yml "
        "has no runs available for release_tag v1.0.2; dispatch native evidence before accepting this target"
        in errors
    )


def test_remote_release_audit_ignores_non_release_tag_runs_when_record_is_missing() -> None:
    checker = _load_checker()
    promotion = checker.read_json(checker.PROMOTION_PATH)

    errors = checker.check_remote_platform_release_evidence(
        registry=_empty_registry(),
        promotion=promotion,
        release=_release_with_assets([]),
        workflow_runs_by_workflow={
            ".github/workflows/extended-platform-evidence.yml": {
                "workflow_runs": [
                    {
                        "event": "workflow_dispatch",
                        "head_branch": "main",
                    }
                ]
            }
        },
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_source_runs=True,
    )

    assert (
        "linux-i386 source workflow .github/workflows/extended-platform-evidence.yml "
        "has no runs available for release_tag v1.0.2; dispatch native evidence before accepting this target"
        in errors
    )


def test_remote_release_audit_rejects_bad_release_timestamps() -> None:
    checker = _load_checker()
    promotion = checker.read_json(checker.PROMOTION_PATH)
    release = _release_with_assets([])
    release["created_at"] = "not-a-date"
    release["published_at"] = ""

    errors = checker.check_remote_platform_release_evidence(
        registry=_empty_registry(),
        promotion=promotion,
        release=release,
        workflow_runs_by_workflow={},
        release_tag="v1.0.2",
        required_targets=(),
    )

    assert (
        "remote release v1.0.2 created_at must be a GitHub ISO-8601 timestamp, "
        "got 'not-a-date'"
    ) in errors
    assert (
        "remote release v1.0.2 published_at must be a GitHub ISO-8601 timestamp, got ''"
    ) in errors


def test_remote_release_audit_rejects_invalid_release_id() -> None:
    checker = _load_checker()
    promotion = checker.read_json(checker.PROMOTION_PATH)
    release = _release_with_assets([])
    release["id"] = 0

    errors = checker.check_remote_platform_release_evidence(
        registry=_empty_registry(),
        promotion=promotion,
        release=release,
        workflow_runs_by_workflow={},
        release_tag="v1.0.2",
        required_targets=(),
    )

    assert "remote release v1.0.2 id must be a positive integer, got 0" in errors


def test_remote_release_audit_rejects_bad_release_api_identity(tmp_path: Path) -> None:
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
    release["url"] = "https://api.github.com/repos/example/remote-ops-workspace/releases/999"
    release["html_url"] = "https://github.com/example/remote-ops-workspace/releases/tag/v1.0.1"
    release["assets_url"] = "https://api.github.com/repos/example/remote-ops-workspace/releases/999/assets"
    release["upload_url"] = (
        "https://uploads.github.com/repos/example/remote-ops-workspace/releases/999/assets{?name,label}"
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
        "remote release v1.0.2 url must be "
        "'https://api.github.com/repos/example/remote-ops-workspace/releases/240102', "
        "got 'https://api.github.com/repos/example/remote-ops-workspace/releases/999'"
    ) in errors
    assert (
        "remote release v1.0.2 html_url must be "
        "'https://github.com/example/remote-ops-workspace/releases/tag/v1.0.2', "
        "got 'https://github.com/example/remote-ops-workspace/releases/tag/v1.0.1'"
    ) in errors
    assert (
        "remote release v1.0.2 assets_url must be "
        "'https://api.github.com/repos/example/remote-ops-workspace/releases/240102/assets', "
        "got 'https://api.github.com/repos/example/remote-ops-workspace/releases/999/assets'"
    ) in errors
    assert (
        "remote release v1.0.2 upload_url must be "
        "'https://uploads.github.com/repos/example/remote-ops-workspace/releases/240102/assets{?name,label}', "
        "got 'https://uploads.github.com/repos/example/remote-ops-workspace/releases/999/assets{?name,label}'"
    ) in errors


def test_remote_release_audit_rejects_mixed_release_asset_repositories(
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
    release["assets"].append(
        {
            "name": "release-notes-v1.0.2.txt",
            "browser_download_url": (
                "https://github.com/other/remote-ops-workspace/"
                "releases/download/v1.0.2/release-notes-v1.0.2.txt"
            ),
        }
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
        "remote release v1.0.2 assets must use one GitHub release repository, "
        "got ['example/remote-ops-workspace', 'other/remote-ops-workspace']"
    ) in errors
    assert not any("release-notes-v1.0.2.txt" in error for error in errors)


def test_remote_release_audit_rejects_release_published_before_created() -> None:
    checker = _load_checker()
    promotion = checker.read_json(checker.PROMOTION_PATH)
    release = _release_with_assets([])
    release["created_at"] = "2026-06-30T12:00:00Z"
    release["published_at"] = "2026-06-30T11:59:59Z"

    errors = checker.check_remote_platform_release_evidence(
        registry=_empty_registry(),
        promotion=promotion,
        release=release,
        workflow_runs_by_workflow={},
        release_tag="v1.0.2",
        required_targets=(),
    )

    assert (
        "remote release v1.0.2 published_at must be at or after created_at "
        "2026-06-30T12:00:00Z, got '2026-06-30T11:59:59Z'"
    ) in errors


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
    release = _release_with_record_assets(
        checker,
        record,
        sorted(required_assets["linux-i386"]),
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
    release = _release_with_record_assets(
        checker,
        record,
        sorted(required_assets["linux-i386"]),
    )

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
    release = _release_with_record_assets(
        checker,
        record,
        sorted(required_assets["linux-i386"]),
    )
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
    release = _release_with_record_assets(
        checker,
        record,
        sorted(required_assets["linux-i386"]),
    )
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
    release = _release_with_record_assets(
        checker,
        record,
        sorted(required_assets["linux-i386"]),
    )
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
    release = _release_with_record_assets(
        checker,
        record,
        sorted(required_assets["linux-i386"]),
    )
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


def test_remote_release_audit_rejects_malformed_release_assets(tmp_path: Path) -> None:
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
    first_malformed_index = len(release["assets"])
    release["assets"].extend(["anonymous-asset", {}, {"name": ""}, {"name": 123}])

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
        f"remote release asset at index {first_malformed_index} "
        "must be an object, got 'anonymous-asset'"
    ) in errors
    assert (
        f"remote release asset at index {first_malformed_index + 1} "
        "name must be a non-empty string, got None"
    ) in errors
    assert (
        f"remote release asset at index {first_malformed_index + 2} "
        "name must be a non-empty string, got ''"
    ) in errors
    assert (
        f"remote release asset at index {first_malformed_index + 3} "
        "name must be a non-empty string, got 123"
    ) in errors


def test_remote_release_audit_rejects_ambiguous_release_asset_names(tmp_path: Path) -> None:
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
            dict(release["assets"][0]),
            {"name": "../escape.txt"},
            {"name": "Readme.txt"},
            {"name": "readme.txt"},
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

    assert "remote release asset name must be an exact safe file name: '../escape.txt'" in errors
    assert f"remote release contains duplicate asset names: ['{release['assets'][0]['name']}']" in errors
    assert (
        "remote release asset names must not collide on case-insensitive filesystems: "
        "['Readme.txt', 'readme.txt']"
    ) in errors


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


def test_remote_release_audit_rejects_bad_source_run_timestamps(tmp_path: Path) -> None:
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
    run_url = str(record["release_asset_source"]["workflow_run_url"])
    run = source_runs[run_url]
    run["createdAt"] = "not-a-date"
    run["runStartedAt"] = "2026-06-30T11:59:59Z"
    run["updatedAt"] = "2026-06-30T11:59:58Z"

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
        "linux-i386 source workflow run created_at must be a GitHub ISO-8601 timestamp, "
        "got 'not-a-date'"
    ) in errors
    assert (
        "linux-i386 source workflow run updated_at must be at or after run_started_at "
        "2026-06-30T11:59:59Z, got '2026-06-30T11:59:58Z'"
    ) in errors


def test_remote_release_audit_rejects_source_run_started_before_created(tmp_path: Path) -> None:
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
    run_url = str(record["release_asset_source"]["workflow_run_url"])
    source_runs[run_url]["createdAt"] = "2026-06-30T12:00:01Z"

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
        "linux-i386 source workflow run run_started_at must be at or after created_at "
        "2026-06-30T12:00:01Z, got '2026-06-30T12:00:00Z'"
    ) in errors


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
    deb_asset["id"] = 0
    deb_asset["browser_download_url"] = (
        "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/wrong.deb"
    )
    bundle_asset = _release_asset(
        release,
        "extended-linux-evidence-bundle-linux-i386-v1.0.2.zip",
    )
    bundle_asset["size"] = 1
    bundle_asset["url"] = "https://api.github.com/repos/example/remote-ops-workspace/releases/assets/999999"
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
        "linux-i386 remote release asset remote-ops-workspace-v1.0.2-linux-i386.deb "
        "id must be a positive integer, got 0"
    ) in errors
    assert any(
        "linux-i386 remote release asset extended-linux-evidence-bundle-linux-i386-v1.0.2.zip "
        "url must be "
        in error
        and "releases/assets/999999" in error
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


def test_remote_release_audit_requires_github_asset_identity_fields(tmp_path: Path) -> None:
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
    deb_asset["node_id"] = ""
    bundle_asset = _release_asset(
        release,
        "extended-linux-evidence-bundle-linux-i386-v1.0.2.zip",
    )
    bundle_asset["content_type"] = None
    final_record_asset = _release_asset(release, "platform-verified-evidence-linux-i386-final.json")
    final_record_asset["download_count"] = -1

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
        "node_id must be a non-empty string, got ''"
    ) in errors
    assert (
        "linux-i386 remote release asset extended-linux-evidence-bundle-linux-i386-v1.0.2.zip "
        "content_type must be a non-empty string, got None"
    ) in errors
    assert (
        "linux-i386 remote release asset platform-verified-evidence-linux-i386-final.json "
        "download_count must be a non-negative integer, got -1"
    ) in errors


def test_remote_release_audit_rejects_bad_release_asset_timestamps(tmp_path: Path) -> None:
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
    deb_asset["created_at"] = "not-a-date"
    bundle_asset = _release_asset(
        release,
        "extended-linux-evidence-bundle-linux-i386-v1.0.2.zip",
    )
    bundle_asset["updated_at"] = "2026-06-30T12:02:59Z"
    final_record_asset = _release_asset(release, "platform-verified-evidence-linux-i386-final.json")
    final_record_asset["updated_at"] = ""

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
        "created_at must be a GitHub ISO-8601 timestamp, got 'not-a-date'"
    ) in errors
    assert (
        "linux-i386 remote release asset extended-linux-evidence-bundle-linux-i386-v1.0.2.zip "
        "updated_at must be at or after created_at 2026-06-30T12:03:00Z, "
        "got '2026-06-30T12:02:59Z'"
    ) in errors
    assert (
        "linux-i386 remote release asset platform-verified-evidence-linux-i386-final.json "
        "updated_at must be a GitHub ISO-8601 timestamp, got ''"
    ) in errors


def test_remote_release_audit_rejects_release_asset_created_before_release(
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
    asset = _release_asset(
        release,
        "extended-linux-evidence-bundle-linux-i386-v1.0.2.zip",
    )
    asset["created_at"] = "2026-06-30T11:54:59Z"

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
        "linux-i386 remote release asset extended-linux-evidence-bundle-linux-i386-v1.0.2.zip "
        "created_at must be at or after release created_at 2026-06-30T11:55:00Z, "
        "got '2026-06-30T11:54:59Z'"
    ) in errors


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
    release = _release_with_record_assets(
        checker,
        record,
        sorted(required_assets["linux-i386"]),
    )

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
    release = _release_with_record_assets(
        checker,
        record,
        sorted(required_assets["linux-i386"]),
        release_asset_bytes=release_asset_bytes,
    )

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
    release = _release_with_record_assets(
        checker,
        record,
        sorted(required_assets["linux-i386"]),
    )

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
    release = _release_with_record_assets(
        checker,
        record,
        sorted(required_assets["linux-i386"]),
        release_asset_bytes=release_asset_bytes,
    )

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


def test_remote_release_audit_rejects_nonpositive_release_asset_metadata_size(
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
    _release_asset(release, "remote-ops-workspace-v1.0.2-linux-i386.deb")["size"] = 0

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

    assert (
        "linux-i386 remote release asset remote-ops-workspace-v1.0.2-linux-i386.deb "
        "size must be a positive integer, got 0"
    ) in errors


def test_remote_release_audit_rejects_release_asset_byte_size_metadata_drift(
    tmp_path: Path,
) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    release_asset_bytes = _bind_release_asset_bytes(checker, record)
    native_asset = "remote-ops-workspace-v1.0.2-linux-i386.deb"
    native_url = next(
        str(asset["url"])
        for asset in checker.expected_release_asset_byte_sources(record)
        if asset["filename"] == native_asset
    )
    registry = _registry_with(record)
    promotion = checker.read_json(checker.PROMOTION_PATH)
    required_assets = checker.required_release_assets_by_target(
        promotion,
        release_tag="v1.0.2",
        targets=("linux-i386",),
    )
    release = _release_with_record_assets(
        checker,
        record,
        sorted(required_assets["linux-i386"]),
        release_asset_bytes=release_asset_bytes,
    )
    _release_asset(release, native_asset)["size"] = len(release_asset_bytes[native_url]) + 1

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

    assert (
        "linux-i386 published release asset remote-ops-workspace-v1.0.2-linux-i386.deb "
        "byte size must match remote release metadata "
        f"{len(release_asset_bytes[native_url]) + 1}, got {len(release_asset_bytes[native_url])}"
    ) in errors


def test_repository_from_release_asset_url_requires_exact_safe_asset_url() -> None:
    checker = _load_checker()
    valid = (
        "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/"
        "remote-ops-workspace-v1.0.2-linux-i386.deb"
    )

    assert checker.repository_from_release_asset_url(valid) == "example/remote-ops-workspace"
    assert checker.repository_from_release_asset_url(f"{valid}?download=1") == ""
    assert (
        checker.repository_from_release_asset_url(
            "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/nested/"
            "remote-ops-workspace-v1.0.2-linux-i386.deb"
        )
        == ""
    )
    assert (
        checker.repository_from_release_asset_url(
            "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/%2E%2E"
        )
        == ""
    )
    assert (
        checker.repository_from_release_asset_url(
            "https://example.invalid/example/remote-ops-workspace/releases/download/v1.0.2/"
            "remote-ops-workspace-v1.0.2-linux-i386.deb"
        )
        == ""
    )


def test_remote_release_audit_rejects_published_native_manifest_size_drift(
    tmp_path: Path,
) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    release_asset_bytes = _bind_release_asset_bytes(checker, record)
    manifest_asset = "remote-ops-workspace-v1.0.2-linux-i686-native-manifest.json"
    manifest_url = next(
        str(asset["url"])
        for asset in checker.expected_release_asset_byte_sources(record)
        if asset["filename"] == manifest_asset
    )
    manifest = json.loads(release_asset_bytes[manifest_url].decode("utf-8"))
    first_record = manifest["artifacts"][0]
    first_record["size_bytes"] = int(first_record["size_bytes"]) + 1
    tampered_manifest = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    release_asset_bytes[manifest_url] = tampered_manifest
    record["artifact_sha256"][manifest_asset] = hashlib.sha256(tampered_manifest).hexdigest()
    registry = _registry_with(record)
    promotion = checker.read_json(checker.PROMOTION_PATH)
    required_assets = checker.required_release_assets_by_target(
        promotion,
        release_tag="v1.0.2",
        targets=("linux-i386",),
    )
    release = _release_with_record_assets(
        checker,
        record,
        sorted(required_assets["linux-i386"]),
        release_asset_bytes=release_asset_bytes,
    )

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
        "linux-i386 published native manifest record remote-ops-workspace-v1.0.2-linux-i386.deb "
        "size_bytes must match published asset bytes"
        in error
        for error in errors
    )


def test_remote_release_audit_rejects_published_native_manifest_case_colliding_records(
    tmp_path: Path,
) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    release_asset_bytes = _bind_release_asset_bytes(checker, record)
    manifest_asset = "remote-ops-workspace-v1.0.2-linux-i686-native-manifest.json"
    manifest_url = next(
        str(asset["url"])
        for asset in checker.expected_release_asset_byte_sources(record)
        if asset["filename"] == manifest_asset
    )
    manifest = json.loads(release_asset_bytes[manifest_url].decode("utf-8"))
    first_record = dict(manifest["artifacts"][0])
    first_name = str(first_record["file"])
    first_record["file"] = first_name.upper()
    manifest["artifacts"].append(first_record)
    tampered_manifest = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
    release_asset_bytes[manifest_url] = tampered_manifest
    record["artifact_sha256"][manifest_asset] = hashlib.sha256(tampered_manifest).hexdigest()
    registry = _registry_with(record)
    promotion = checker.read_json(checker.PROMOTION_PATH)
    required_assets = checker.required_release_assets_by_target(
        promotion,
        release_tag="v1.0.2",
        targets=("linux-i386",),
    )
    release = _release_with_record_assets(
        checker,
        record,
        sorted(required_assets["linux-i386"]),
        release_asset_bytes=release_asset_bytes,
    )

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
        f"linux-i386 published native manifest {manifest_asset} payload records must not collide on "
        "case-insensitive filesystems" in error
        and first_name in error
        and first_name.upper() in error
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
    run["id"] = "12345"
    run["url"] = "https://api.github.com/repos/example/remote-ops-workspace/actions/runs/99999"
    run["node_id"] = ""
    run["run_number"] = 0
    run["workflow_id"] = "445566"
    run["check_suite_id"] = 0
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

    assert "linux-i386 source workflow run id must be a positive integer, got '12345'" in errors
    assert (
        "linux-i386 source workflow run url must be "
        "'https://api.github.com/repos/example/remote-ops-workspace/actions/runs/12345', "
        "got 'https://api.github.com/repos/example/remote-ops-workspace/actions/runs/99999'"
    ) in errors
    assert "linux-i386 source workflow run node_id must be a non-empty string, got ''" in errors
    assert "linux-i386 source workflow run run_number must be a positive integer, got 0" in errors
    assert (
        "linux-i386 source workflow run workflow_id must be a positive integer, got '445566'"
    ) in errors
    assert "linux-i386 source workflow run check_suite_id must be a positive integer, got 0" in errors
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


def test_remote_release_audit_rejects_source_run_release_tag_ref_mismatch(
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
    run = next(iter(source_runs.values()))
    run["headBranch"] = "main"

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
        "linux-i386 source workflow run head_branch must match release_tag "
        "v1.0.2, got 'main'"
    ) in errors


def test_remote_release_audit_requires_source_run_endpoint_metadata(tmp_path: Path) -> None:
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
    run["workflowUrl"] = "https://api.github.com/repos/example/remote-ops-workspace/actions/workflows/999"
    run["jobsUrl"] = "https://api.github.com/repos/example/remote-ops-workspace/actions/runs/99999/jobs"
    run["logsUrl"] = "https://api.github.com/repos/example/remote-ops-workspace/actions/runs/99999/logs"
    run["artifactsUrl"] = "https://api.github.com/repos/example/remote-ops-workspace/actions/runs/99999/artifacts"
    run["checkSuiteUrl"] = "https://api.github.com/repos/example/remote-ops-workspace/check-suites/1"

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
        "linux-i386 source workflow run workflow_url must be "
        "'https://api.github.com/repos/example/remote-ops-workspace/actions/workflows/445566', "
        "got 'https://api.github.com/repos/example/remote-ops-workspace/actions/workflows/999'"
    ) in errors
    assert (
        "linux-i386 source workflow run jobs_url must be "
        "'https://api.github.com/repos/example/remote-ops-workspace/actions/runs/12345/jobs', "
        "got 'https://api.github.com/repos/example/remote-ops-workspace/actions/runs/99999/jobs'"
    ) in errors
    assert (
        "linux-i386 source workflow run logs_url must be "
        "'https://api.github.com/repos/example/remote-ops-workspace/actions/runs/12345/logs', "
        "got 'https://api.github.com/repos/example/remote-ops-workspace/actions/runs/99999/logs'"
    ) in errors
    assert (
        "linux-i386 source workflow run artifacts_url must be "
        "'https://api.github.com/repos/example/remote-ops-workspace/actions/runs/12345/artifacts', "
        "got 'https://api.github.com/repos/example/remote-ops-workspace/actions/runs/99999/artifacts'"
    ) in errors
    assert (
        "linux-i386 source workflow run check_suite_url must be "
        "'https://api.github.com/repos/example/remote-ops-workspace/check-suites/998877', "
        "got 'https://api.github.com/repos/example/remote-ops-workspace/check-suites/1'"
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


def test_remote_release_audit_requires_source_run_repository_ids(tmp_path: Path) -> None:
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
    del run["repository"]["id"]
    run["head_repository"]["id"] = "1001"

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

    assert "linux-i386 source workflow run repository.id must be a positive integer, got None" in errors
    assert (
        "linux-i386 source workflow run head_repository.id must be a positive integer, "
        "got '1001'"
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


def test_remote_release_audit_rejects_extra_source_artifacts(tmp_path: Path) -> None:
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
    source_artifacts[run_url]["artifacts"].append(
        {
            "id": 98766,
            "name": "unrelated-debug-artifact",
            "archive_download_url": (
                "https://api.github.com/repos/example/remote-ops-workspace/"
                "actions/artifacts/98766/zip"
            ),
            "expired": False,
            "size_in_bytes": 1,
            "created_at": "2026-06-30T12:03:00Z",
            "workflow_run": {
                "id": 12345,
                "repository_id": 1001,
                "head_repository_id": 1001,
                "head_sha": record["release_asset_source"]["head_sha"],
            },
        }
    )
    source_artifacts[run_url]["total_count"] = 2

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
        "linux-i386 source workflow artifact list must contain only the "
        "target-scoped evidence artifact 'extended-linux-evidence-linux-i386-v1.0.2', "
        "got 2 artifacts"
    ) in errors


def test_remote_release_audit_verifies_source_artifact_zip_contents(tmp_path: Path) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    source_artifact_zip = _source_artifact_zip_for(checker, record)
    source_artifacts = _source_artifacts_for(
        record,
        size_in_bytes=len(next(iter(source_artifact_zip.values()))),
    )
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
        source_artifacts_by_run=source_artifacts,
        source_artifact_bytes_by_run=source_artifact_zip,
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_source_runs=True,
        require_source_artifact_bytes=True,
    )

    assert errors == []


def test_remote_release_audit_rejects_source_artifact_zip_size_drift(tmp_path: Path) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    source_artifact_zip = _source_artifact_zip_for(checker, record)
    source_zip_bytes = next(iter(source_artifact_zip.values()))
    source_artifacts = _source_artifacts_for(record, size_in_bytes=len(source_zip_bytes) + 1)
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
        source_artifacts_by_run=source_artifacts,
        source_artifact_bytes_by_run=source_artifact_zip,
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_source_runs=True,
        require_source_artifact_bytes=True,
    )

    assert (
        "linux-i386 source workflow artifact extended-linux-evidence-linux-i386-v1.0.2 "
        f"size_in_bytes must match downloaded ZIP byte length {len(source_zip_bytes)}, "
        f"got {len(source_zip_bytes) + 1}"
    ) in errors


def test_remote_release_audit_requires_source_artifact_zip_bytes(tmp_path: Path) -> None:
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
        source_artifact_bytes_by_run={},
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_source_runs=True,
        require_source_artifact_bytes=True,
    )

    assert (
        "linux-i386 source workflow artifact ZIP bytes missing for "
        "https://github.com/example/remote-ops-workspace/actions/runs/12345"
    ) in errors


def test_remote_release_audit_rejects_source_artifact_zip_content_drift(tmp_path: Path) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    source_file_bytes = _source_artifact_zip_file_bytes(checker, record)
    registry = _registry_with(record)
    promotion = checker.read_json(checker.PROMOTION_PATH)
    required_assets = checker.required_release_assets_by_target(
        promotion,
        release_tag="v1.0.2",
        targets=("linux-i386",),
    )
    release = _release_with_record_assets(checker, record, sorted(required_assets["linux-i386"]))
    source = record["release_asset_source"]
    assert isinstance(source, dict)
    last_file = sorted(source_file_bytes)[-1]
    source_file_bytes.pop(last_file)
    source_file_bytes["unreviewed-debug.txt"] = b"unreviewed debug bytes\n"
    drifted_zip = _zip_named_bytes(source_file_bytes)

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        source_runs_by_run=_source_runs_for(record),
        workflow_runs_by_workflow={},
        source_artifacts_by_run=_source_artifacts_for(record),
        source_artifact_bytes_by_run={
            str(source["workflow_run_url"]): drifted_zip,
        },
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_source_runs=True,
        require_source_artifact_bytes=True,
    )

    assert any(
        error.startswith(
            "linux-i386 source workflow artifact extended-linux-evidence-linux-i386-v1.0.2 "
            "ZIP missing files:"
        )
        for error in errors
    )
    assert (
        "linux-i386 source workflow artifact extended-linux-evidence-linux-i386-v1.0.2 "
        "ZIP has unexpected files: ['unreviewed-debug.txt']"
    ) in errors


def test_remote_release_audit_rejects_source_artifact_zip_case_colliding_files(tmp_path: Path) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    source_file_bytes = _source_artifact_zip_file_bytes(checker, record)
    target_file = sorted(source_file_bytes)[0]
    source_file_bytes[target_file.upper()] = source_file_bytes[target_file]
    registry = _registry_with(record)
    promotion = checker.read_json(checker.PROMOTION_PATH)
    required_assets = checker.required_release_assets_by_target(
        promotion,
        release_tag="v1.0.2",
        targets=("linux-i386",),
    )
    release = _release_with_record_assets(checker, record, sorted(required_assets["linux-i386"]))
    source = record["release_asset_source"]
    assert isinstance(source, dict)

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        source_runs_by_run=_source_runs_for(record),
        workflow_runs_by_workflow={},
        source_artifacts_by_run=_source_artifacts_for(record),
        source_artifact_bytes_by_run={
            str(source["workflow_run_url"]): _zip_named_bytes(source_file_bytes),
        },
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_source_runs=True,
        require_source_artifact_bytes=True,
    )

    assert any(
        "linux-i386 source workflow artifact extended-linux-evidence-linux-i386-v1.0.2 "
        "ZIP is invalid: contains files that collide on case-insensitive filesystems" in error
        and target_file in error
        and target_file.upper() in error
        for error in errors
    )


def test_remote_release_audit_rejects_source_artifact_zip_byte_drift(tmp_path: Path) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    source_file_bytes = _source_artifact_zip_file_bytes(checker, record)
    registry = _registry_with(record)
    promotion = checker.read_json(checker.PROMOTION_PATH)
    required_assets = checker.required_release_assets_by_target(
        promotion,
        release_tag="v1.0.2",
        targets=("linux-i386",),
    )
    release = _release_with_record_assets(checker, record, sorted(required_assets["linux-i386"]))
    source = record["release_asset_source"]
    assert isinstance(source, dict)
    target_file = sorted(source_file_bytes)[0]
    source_file_bytes[target_file] = b"tampered source artifact bytes\n"

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        source_runs_by_run=_source_runs_for(record),
        workflow_runs_by_workflow={},
        source_artifacts_by_run=_source_artifacts_for(record),
        source_artifact_bytes_by_run={
            str(source["workflow_run_url"]): _zip_named_bytes(source_file_bytes),
        },
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_source_runs=True,
        require_source_artifact_bytes=True,
    )

    assert any(
        error.startswith(
            "linux-i386 source workflow artifact extended-linux-evidence-linux-i386-v1.0.2 "
            f"ZIP file {target_file} bytes SHA-256 must match accepted evidence "
        )
        for error in errors
    )


def test_remote_release_audit_rejects_nested_source_artifact_zip_entries(tmp_path: Path) -> None:
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
    source = record["release_asset_source"]
    assert isinstance(source, dict)

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        source_runs_by_run=_source_runs_for(record),
        workflow_runs_by_workflow={},
        source_artifacts_by_run=_source_artifacts_for(record),
        source_artifact_bytes_by_run={
            str(source["workflow_run_url"]): _zip_bytes(["nested/proof.txt"]),
        },
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_source_runs=True,
        require_source_artifact_bytes=True,
    )

    assert (
        "linux-i386 source workflow artifact extended-linux-evidence-linux-i386-v1.0.2 "
        "ZIP is invalid: contains non-root or unsafe file name 'nested/proof.txt'"
    ) in errors


def test_remote_release_audit_rejects_source_artifact_zip_symlink_entries(tmp_path: Path) -> None:
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
    source = record["release_asset_source"]
    assert isinstance(source, dict)

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        source_runs_by_run=_source_runs_for(record),
        workflow_runs_by_workflow={},
        source_artifacts_by_run=_source_artifacts_for(record),
        source_artifact_bytes_by_run={
            str(source["workflow_run_url"]): _zip_with_symlink_entry("proof.txt"),
        },
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_source_runs=True,
        require_source_artifact_bytes=True,
    )

    assert (
        "linux-i386 source workflow artifact extended-linux-evidence-linux-i386-v1.0.2 "
        "ZIP is invalid: contains symlink entry 'proof.txt'"
    ) in errors


def test_remote_release_audit_rejects_source_artifact_zip_special_file_entries(
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
    source = record["release_asset_source"]
    assert isinstance(source, dict)

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        source_runs_by_run=_source_runs_for(record),
        workflow_runs_by_workflow={},
        source_artifacts_by_run=_source_artifacts_for(record),
        source_artifact_bytes_by_run={
            str(source["workflow_run_url"]): _zip_with_mode_entry("proof.txt", 0o010666),
        },
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_source_runs=True,
        require_source_artifact_bytes=True,
    )

    assert (
        "linux-i386 source workflow artifact extended-linux-evidence-linux-i386-v1.0.2 "
        "ZIP is invalid: contains non-regular file entry 'proof.txt'"
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


def test_remote_release_audit_requires_source_artifact_workflow_run_integer_ids(
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
    artifact_run = source_artifacts[run_url]["artifacts"][0]["workflow_run"]
    artifact_run["id"] = "12345"
    del artifact_run["repository_id"]
    artifact_run["head_repository_id"] = "1001"

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
        "workflow_run.id must be a positive integer, got '12345'"
    ) in errors
    assert (
        "linux-i386 source workflow artifact extended-linux-evidence-linux-i386-v1.0.2 "
        "workflow_run.repository_id must be a positive integer, got None"
    ) in errors
    assert (
        "linux-i386 source workflow artifact extended-linux-evidence-linux-i386-v1.0.2 "
        "workflow_run.head_repository_id must be a positive integer, got '1001'"
    ) in errors


def test_remote_release_audit_rejects_artifact_created_before_exact_run_creation(
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
    source_artifacts = _source_artifacts_for(record)
    run_url = str(record["release_asset_source"]["workflow_run_url"])
    source_artifacts[run_url]["artifacts"][0]["created_at"] = "2026-06-30T11:58:59Z"

    errors = checker.check_remote_platform_release_evidence(
        registry=registry,
        promotion=promotion,
        release=release,
        source_runs_by_run=source_runs,
        workflow_runs_by_workflow={},
        source_artifacts_by_run=source_artifacts,
        release_tag="v1.0.2",
        required_targets=("linux-i386",),
        require_source_runs=True,
    )

    assert (
        "linux-i386 source workflow artifact extended-linux-evidence-linux-i386-v1.0.2 "
        "created_at must be at or after exact source run creation 2026-06-30T11:59:00Z, "
        "got '2026-06-30T11:58:59Z'"
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


def test_remote_release_audit_rejects_artifact_updated_after_exact_run_update(
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
    source_artifacts[run_url]["artifacts"][0]["updated_at"] = "2026-06-30T12:05:01Z"

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
        "updated_at must be at or before exact source run update 2026-06-30T12:05:00Z, "
        "got '2026-06-30T12:05:01Z'"
    ) in errors


def test_remote_release_audit_rejects_artifact_updated_before_created_at(
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
    source_artifacts[run_url]["artifacts"][0]["updated_at"] = "2026-06-30T12:02:59Z"

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
        "updated_at must be at or after created_at 2026-06-30T12:03:00Z, "
        "got '2026-06-30T12:02:59Z'"
    ) in errors


def test_remote_release_audit_rejects_missing_source_artifact_expiration(
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
    source_artifacts[run_url]["artifacts"][0].pop("expires_at")

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
        "expires_at must be a GitHub ISO-8601 timestamp, got None"
    ) in errors


def test_remote_release_audit_rejects_stale_source_artifact_expiration(
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
    source_artifacts[run_url]["artifacts"][0]["expires_at"] = "2026-06-30T12:03:30Z"

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
        "expires_at must be after updated_at 2026-06-30T12:04:00Z, "
        "got '2026-06-30T12:03:30Z'"
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
    artifact["url"] = "https://api.github.com/repos/example/remote-ops-workspace/actions/artifacts/99"
    artifact["node_id"] = ""
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
        "url must be "
        in error
        and "artifacts/99" in error
        for error in errors
    )
    assert (
        "linux-i386 source workflow artifact extended-linux-evidence-linux-i386-v1.0.2 "
        "node_id must be a non-empty string, got ''"
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


def test_workflow_runs_api_url_scopes_to_release_tag_dispatch_runs() -> None:
    checker = _load_checker()

    assert checker.workflow_runs_api_url(
        "example/remote-ops-workspace",
        ".github/workflows/extended-platform-evidence.yml",
        "v1.0.2",
    ) == (
        "https://api.github.com/repos/example/remote-ops-workspace/actions/workflows/"
        "extended-platform-evidence.yml/runs?branch=v1.0.2&event=workflow_dispatch&per_page=100"
    )


def test_require_goal_targets_requires_all_published_release_proof_flags() -> None:
    checker = _load_checker()
    args = checker.parse_args(
        [
            "--repository",
            "example/remote-ops-workspace",
            "--release-tag",
            "v1.0.2",
            "--require-goal-targets",
        ]
    )

    errors = checker.strict_arg_errors(args)

    assert (
        "--require-goal-targets requires strict published release proof flags: "
        "--require-source-runs, --require-source-artifact-bytes, --require-final-record-bytes, "
        "--require-release-asset-bytes, --require-tag-source-head"
    ) in errors


def test_require_goal_targets_accepts_full_published_release_proof_flags() -> None:
    checker = _load_checker()
    args = checker.parse_args(
        [
            "--repository",
            "example/remote-ops-workspace",
            "--release-tag",
            "v1.0.2",
            "--require-goal-targets",
            "--require-source-runs",
            "--require-source-artifact-bytes",
            "--require-final-record-bytes",
            "--require-release-asset-bytes",
            "--require-tag-source-head",
        ]
    )

    errors = checker.strict_arg_errors(args)

    assert errors == []


def test_require_source_artifact_bytes_requires_source_runs() -> None:
    checker = _load_checker()
    args = checker.parse_args(
        [
            "--repository",
            "example/remote-ops-workspace",
            "--release-tag",
            "v1.0.2",
            "--require-source-artifact-bytes",
        ]
    )

    errors = checker.strict_arg_errors(args)

    assert "--require-source-artifact-bytes requires --require-source-runs" in errors


def test_require_goal_targets_continues_remote_audit_after_missing_records(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    checker = _load_checker()
    registry_path = tmp_path / "platform_verified_evidence.json"
    release_path = tmp_path / "release.json"
    linux_runs_path = tmp_path / "extended-platform-runs.json"
    xp_runs_path = tmp_path / "xp-native-runs.json"
    tag_ref_path = tmp_path / "tag-ref.json"
    registry_path.write_text(json.dumps(_empty_registry(), indent=2) + "\n", encoding="utf-8")
    release_path.write_text(json.dumps(_release_with_assets([]), indent=2) + "\n", encoding="utf-8")
    linux_runs_path.write_text(json.dumps({"workflow_runs": []}) + "\n", encoding="utf-8")
    xp_runs_path.write_text(json.dumps({"workflow_runs": []}) + "\n", encoding="utf-8")
    tag_ref_path.write_text(
        json.dumps({"ref": "refs/tags/v1.0.2", "object": {"type": "commit", "sha": "a" * 40}})
        + "\n",
        encoding="utf-8",
    )

    def fail_fetch_json(*_args: Any, **_kwargs: Any) -> tuple[None, list[str]]:
        raise AssertionError("offline remote audit fixture should not fetch JSON")

    def fail_fetch_bytes(*_args: Any, **_kwargs: Any) -> tuple[None, list[str]]:
        raise AssertionError("offline remote audit fixture should not fetch bytes")

    monkeypatch.setattr(checker, "fetch_json", fail_fetch_json)
    monkeypatch.setattr(checker, "fetch_bytes", fail_fetch_bytes)

    result = checker.main(
        [
            "--repository",
            "example/remote-ops-workspace",
            "--release-tag",
            "v1.0.2",
            "--registry",
            str(registry_path),
            "--release-json",
            str(release_path),
            "--workflow-runs-json",
            f".github/workflows/extended-platform-evidence.yml={linux_runs_path}",
            "--workflow-runs-json",
            f".github/workflows/xp-native-evidence.yml={xp_runs_path}",
            "--tag-ref-json",
            str(tag_ref_path),
            "--require-goal-targets",
            "--require-source-runs",
            "--require-source-artifact-bytes",
            "--require-final-record-bytes",
            "--require-release-asset-bytes",
            "--require-tag-source-head",
        ]
    )

    stderr = capsys.readouterr().err

    assert result == 1
    assert "missing required accepted evidence targets for release_tag v1.0.2" in stderr
    assert "linux-i386 remote release v1.0.2 missing protected evidence assets" in stderr
    assert (
        "linux-i386 source workflow .github/workflows/extended-platform-evidence.yml "
        "has no runs available for release_tag v1.0.2"
    ) in stderr


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


def test_offline_require_source_artifact_bytes_requires_zip_fixture(tmp_path: Path) -> None:
    checker = _load_checker()
    args = checker.parse_args(
        [
            "--release-tag",
            "v1.0.2",
            "--release-json",
            str(tmp_path / "release.json"),
            "--require-source-runs",
            "--require-source-artifact-bytes",
            "--source-run-json",
            f"https://github.com/example/remote-ops-workspace/actions/runs/12345={tmp_path / 'run.json'}",
            "--source-artifacts-json",
            f"https://github.com/example/remote-ops-workspace/actions/runs/12345={tmp_path / 'artifacts.json'}",
        ]
    )

    errors = checker.strict_arg_errors(args)

    assert "--require-source-artifact-bytes without --repository requires --source-artifact-zip" in errors


def test_offline_source_run_fixture_rejects_duplicate_run_bindings(tmp_path: Path) -> None:
    checker = _load_checker()
    run = "https://github.com/example/remote-ops-workspace/actions/runs/12345"
    args = checker.parse_args(
        [
            "--release-tag",
            "v1.0.2",
            "--require-source-runs",
            "--source-run-json",
            f"{run}={tmp_path / 'first-run.json'}",
            "--source-run-json",
            f"{run} ={tmp_path / 'second-run.json'}",
        ]
    )

    errors = checker.strict_arg_errors(args)

    assert f"--source-run-json contains duplicate run fixtures: ['{run}']" in errors


def test_offline_source_artifact_fixture_rejects_duplicate_run_bindings(tmp_path: Path) -> None:
    checker = _load_checker()
    args = checker.parse_args(
        [
            "--release-tag",
            "v1.0.2",
            "--require-source-runs",
            "--source-artifacts-json",
            f"12345={tmp_path / 'first-artifacts.json'}",
            "--source-artifacts-json",
            f"12345 ={tmp_path / 'second-artifacts.json'}",
        ]
    )

    errors = checker.strict_arg_errors(args)

    assert "--source-artifacts-json contains duplicate run fixtures: ['12345']" in errors


def test_offline_source_run_fixture_rejects_full_url_and_id_aliases(
    tmp_path: Path,
) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    run_url = str(record["release_asset_source"]["workflow_run_url"])
    run_id = run_url.rsplit("/", 1)[-1]
    first_fixture = tmp_path / "run-url.json"
    second_fixture = tmp_path / "run-id.json"
    first_fixture.write_text("{}", encoding="utf-8")
    second_fixture.write_text("{}", encoding="utf-8")
    args = checker.parse_args(
        [
            "--release-tag",
            "v1.0.2",
            "--require-source-runs",
            "--source-run-json",
            f"{run_url}={first_fixture}",
            "--source-run-json",
            f"{run_id}={second_fixture}",
        ]
    )

    _source_runs, errors = checker.load_source_runs(
        args,
        _registry_with(record),
        ("linux-i386",),
    )

    assert (
        "--source-run-json contains ambiguous aliases for accepted source run "
        f"{run_url}: ['{run_url}', '{run_id}']"
    ) in errors


def test_offline_source_artifact_fixture_rejects_full_url_and_id_aliases(
    tmp_path: Path,
) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    run_url = str(record["release_asset_source"]["workflow_run_url"])
    run_id = run_url.rsplit("/", 1)[-1]
    first_fixture = tmp_path / "artifacts-url.json"
    second_fixture = tmp_path / "artifacts-id.json"
    first_fixture.write_text("{}", encoding="utf-8")
    second_fixture.write_text("{}", encoding="utf-8")
    args = checker.parse_args(
        [
            "--release-tag",
            "v1.0.2",
            "--require-source-runs",
            "--source-artifacts-json",
            f"{run_url}={first_fixture}",
            "--source-artifacts-json",
            f"{run_id}={second_fixture}",
        ]
    )

    _source_artifacts, errors = checker.load_source_artifacts(
        args,
        _registry_with(record),
        ("linux-i386",),
    )

    assert (
        "--source-artifacts-json contains ambiguous aliases for accepted source run "
        f"{run_url}: ['{run_url}', '{run_id}']"
    ) in errors


def test_offline_source_run_fixture_requires_every_required_run(
    tmp_path: Path,
) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    run_url = str(record["release_asset_source"]["workflow_run_url"]).rstrip("/")
    args = checker.parse_args(
        [
            "--release-tag",
            "v1.0.2",
            "--release-json",
            str(tmp_path / "release.json"),
            "--require-source-runs",
            "--workflow-runs-json",
            f".github/workflows/extended-platform-evidence.yml={tmp_path / 'runs.json'}",
        ]
    )

    _source_runs, errors = checker.load_source_runs(
        args,
        _registry_with(record),
        ("linux-i386",),
    )

    assert (
        "--source-run-json missing fixtures for required accepted source runs: "
        f"['{run_url}']"
    ) in errors


def test_offline_source_artifact_fixture_requires_every_required_run(
    tmp_path: Path,
) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    run_url = str(record["release_asset_source"]["workflow_run_url"]).rstrip("/")
    source_run_fixture = tmp_path / "run.json"
    source_run_fixture.write_text("{}", encoding="utf-8")
    args = checker.parse_args(
        [
            "--release-tag",
            "v1.0.2",
            "--release-json",
            str(tmp_path / "release.json"),
            "--require-source-runs",
            "--source-run-json",
            f"{run_url}={source_run_fixture}",
        ]
    )

    _source_artifacts, errors = checker.load_source_artifacts(
        args,
        _registry_with(record),
        ("linux-i386",),
    )

    assert (
        "--source-artifacts-json missing fixtures for required accepted source runs: "
        f"['{run_url}']"
    ) in errors


def test_offline_source_run_fixture_rejects_offscope_run(
    tmp_path: Path,
) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    fixture = tmp_path / "run.json"
    fixture.write_text("{}", encoding="utf-8")
    offscope_run = "https://github.com/example/remote-ops-workspace/actions/runs/99999"
    args = checker.parse_args(
        [
            "--release-tag",
            "v1.0.2",
            "--require-source-runs",
            "--source-run-json",
            f"{offscope_run}={fixture}",
        ]
    )

    source_runs, errors = checker.load_source_runs(
        args,
        _registry_with(record),
        ("linux-i386",),
    )

    assert source_runs == {offscope_run: {}}
    assert (
        "--source-run-json contains fixtures outside required accepted "
        f"source-run scope: ['{offscope_run}']"
    ) in errors


def test_offline_source_artifact_fixture_rejects_offscope_run(
    tmp_path: Path,
) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    fixture = tmp_path / "artifacts.json"
    fixture.write_text("{}", encoding="utf-8")
    offscope_run = "99999"
    args = checker.parse_args(
        [
            "--release-tag",
            "v1.0.2",
            "--require-source-runs",
            "--source-artifacts-json",
            f"{offscope_run}={fixture}",
        ]
    )

    source_artifacts, errors = checker.load_source_artifacts(
        args,
        _registry_with(record),
        ("linux-i386",),
    )

    assert source_artifacts == {offscope_run: {}}
    assert (
        "--source-artifacts-json contains fixtures outside required accepted "
        f"source-run scope: ['{offscope_run}']"
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


def test_offline_final_record_fixture_rejects_duplicate_url_bindings(tmp_path: Path) -> None:
    checker = _load_checker()
    url = (
        "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/"
        "platform-verified-evidence-linux-i386-final.json"
    )
    args = checker.parse_args(
        [
            "--release-tag",
            "v1.0.2",
            "--release-json",
            str(tmp_path / "release.json"),
            "--final-record-json",
            f"{url}={tmp_path / 'first.json'}",
            "--final-record-json",
            f"{url} ={tmp_path / 'second.json'}",
        ]
    )

    errors = checker.strict_arg_errors(args)

    assert f"--final-record-json contains duplicate URL fixtures: ['{url}']" in errors


def test_offline_final_record_fixture_rejects_offscope_url(
    tmp_path: Path,
) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    fixture = tmp_path / "record.json"
    fixture.write_bytes(checker.canonical_public_record_bytes(record))
    offscope_url = (
        "https://github.com/example/remote-ops-workspace/releases/download/v1.0.3/"
        "platform-verified-evidence-linux-i386-final.json"
    )
    args = checker.parse_args(
        [
            "--release-tag",
            "v1.0.2",
            "--require-final-record-bytes",
            "--final-record-json",
            f"{offscope_url}={fixture}",
        ]
    )

    records_by_url, errors = checker.load_final_record_bytes(
        args,
        _registry_with(record),
        ("linux-i386",),
    )

    assert records_by_url == {offscope_url: fixture.read_bytes()}
    assert (
        "--final-record-json contains fixtures outside required accepted "
        f"final-record byte scope: ['{offscope_url}']"
    ) in errors


def test_offline_final_record_fixture_requires_every_required_url(
    tmp_path: Path,
) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    expected_url = str(record["finalized_record_release_asset_url"])
    args = checker.parse_args(
        [
            "--release-tag",
            "v1.0.2",
            "--release-json",
            str(tmp_path / "release.json"),
            "--require-final-record-bytes",
        ]
    )

    _records_by_url, errors = checker.load_final_record_bytes(
        args,
        _registry_with(record),
        ("linux-i386",),
    )

    assert (
        "--final-record-json missing fixtures for required accepted "
        f"final-record bytes: ['{expected_url}']"
    ) in errors


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


def test_offline_release_asset_fixture_rejects_duplicate_url_bindings(tmp_path: Path) -> None:
    checker = _load_checker()
    url = (
        "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/"
        "remote-ops-workspace-v1.0.2-linux-i386.deb"
    )
    args = checker.parse_args(
        [
            "--release-tag",
            "v1.0.2",
            "--release-json",
            str(tmp_path / "release.json"),
            "--release-asset",
            f"{url}={tmp_path / 'first.deb'}",
            "--release-asset",
            f"{url} ={tmp_path / 'second.deb'}",
        ]
    )

    errors = checker.strict_arg_errors(args)

    assert f"--release-asset contains duplicate URL fixtures: ['{url}']" in errors


def test_offline_release_asset_fixture_rejects_offscope_url(
    tmp_path: Path,
) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    fixture = tmp_path / "asset.deb"
    fixture.write_bytes(b"asset bytes")
    offscope_url = (
        "https://github.com/example/remote-ops-workspace/releases/download/v1.0.3/"
        "remote-ops-workspace-v1.0.2-linux-i386.deb"
    )
    args = checker.parse_args(
        [
            "--release-tag",
            "v1.0.2",
            "--require-release-asset-bytes",
            "--release-asset",
            f"{offscope_url}={fixture}",
        ]
    )

    assets_by_url, errors = checker.load_release_asset_bytes(
        args,
        _registry_with(record),
        ("linux-i386",),
    )

    assert assets_by_url == {offscope_url: b"asset bytes"}
    assert (
        "--release-asset contains fixtures outside required release "
        f"asset byte scope: ['{offscope_url}']"
    ) in errors


def test_offline_release_asset_fixture_requires_every_required_url(
    tmp_path: Path,
) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    first_asset = checker.expected_release_asset_byte_sources(record)[0]
    provided_url = str(first_asset["url"])
    provided_fixture = tmp_path / "asset.bin"
    provided_fixture.write_bytes(b"asset bytes")
    expected_urls = sorted(
        str(asset["url"])
        for asset in checker.expected_release_asset_byte_sources(record)
        if asset.get("url")
    )
    missing_urls = [url for url in expected_urls if url != provided_url]
    args = checker.parse_args(
        [
            "--release-tag",
            "v1.0.2",
            "--release-json",
            str(tmp_path / "release.json"),
            "--require-release-asset-bytes",
            "--release-asset",
            f"{provided_url}={provided_fixture}",
        ]
    )

    _assets_by_url, errors = checker.load_release_asset_bytes(
        args,
        _registry_with(record),
        ("linux-i386",),
    )

    assert (
        "--release-asset missing fixtures for required release asset bytes: "
        f"{missing_urls}"
    ) in errors


def test_expected_release_asset_helpers_ignore_non_string_artifact_keys() -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    record["artifact_sha256"][True] = "0" * 64
    record.pop("finalized_record_release_asset_url", None)

    sources = checker.expected_release_asset_byte_sources(record)
    published = checker.expected_published_assets(record)

    assert all(asset["filename"] != "True" for asset in sources)
    assert "True" not in published


def test_expected_release_asset_helpers_ignore_non_string_release_asset_urls() -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    record["release_asset_urls"].append(True)
    record["review_bundle"]["release_asset_urls"].append(False)
    record.pop("finalized_record_release_asset_url", None)

    sources = checker.expected_release_asset_byte_sources(record)
    published = checker.expected_published_assets(record)

    assert all(asset.get("url") != "True" for asset in sources)
    assert all(asset.get("url") != "False" for asset in sources)
    assert all(metadata.get("browser_download_url") != "True" for metadata in published.values())
    assert all(metadata.get("browser_download_url") != "False" for metadata in published.values())


def test_remote_release_audit_rejects_reserved_registry_and_promotion_paths(tmp_path: Path) -> None:
    checker = _load_checker()
    args = checker.parse_args(
        [
            "--release-tag",
            "v1.0.2",
            "--release-json",
            str(tmp_path / "release.json"),
            "--registry",
            str(Path(".github") / "platform_verified_evidence.json"),
            "--promotion",
            str(Path(".codex") / "platform_parity_promotion.json"),
        ]
    )

    errors = checker.strict_arg_errors(args)

    assert any(
        "--registry file must not point inside reserved workspace directory '.github'" in error
        for error in errors
    )
    assert any(
        "--promotion file must not point inside reserved workspace directory '.codex'" in error
        for error in errors
    )


def test_remote_release_audit_main_rejects_duplicate_registry_before_fetch(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    registry = _registry_with(record)
    registry["accepted_evidence"].append(dict(record))
    registry_path = tmp_path / "platform_verified_evidence.json"
    registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")

    def fail_fetch_json(*_args: Any, **_kwargs: Any) -> tuple[None, list[str]]:
        raise AssertionError("remote audit should reject duplicate registry targets before JSON fetch")

    def fail_fetch_bytes(*_args: Any, **_kwargs: Any) -> tuple[None, list[str]]:
        raise AssertionError("remote audit should reject duplicate registry targets before byte fetch")

    monkeypatch.setattr(checker, "fetch_json", fail_fetch_json)
    monkeypatch.setattr(checker, "fetch_bytes", fail_fetch_bytes)

    result = checker.main(
        [
            "--repository",
            "example/remote-ops-workspace",
            "--release-tag",
            "v1.0.2",
            "--registry",
            str(registry_path),
        ]
    )

    assert result == 1
    assert "accepted_evidence target must be unique: linux-i386" in capsys.readouterr().err


def test_offline_json_fixture_rejects_reserved_workspace_root() -> None:
    checker = _load_checker()
    args = checker.parse_args(
        [
            "--release-tag",
            "v1.0.2",
            "--release-json",
            str(Path(".github") / "release.json"),
        ]
    )

    release, errors = checker.load_release_data(args)

    assert release is None
    assert errors
    assert "--release-json fixture must not point inside reserved workspace directory '.github'" in errors[0]


def test_offline_release_asset_fixture_rejects_reserved_workspace_root() -> None:
    checker = _load_checker()
    helpers = _load_platform_verified_evidence_helpers()
    record = helpers._linux_record("linux-i386")
    url = str(checker.expected_release_asset_byte_sources(record)[0]["url"])
    args = checker.parse_args(
        [
            "--release-tag",
            "v1.0.2",
            "--release-asset",
            f"{url}={Path('.github') / 'linux-i386.deb'}",
        ]
    )

    assets_by_url, errors = checker.load_release_asset_bytes(args, _registry_with(record), ("linux-i386",))

    assert assets_by_url == {}
    assert errors
    assert "--release-asset fixture must not point inside reserved workspace directory '.github'" in errors[0]


def test_offline_json_fixture_rejects_parent_symlink(tmp_path: Path) -> None:
    checker = _load_checker()
    fixture_dir = tmp_path / "fixtures"
    fixture_dir.mkdir()
    (fixture_dir / "release.json").write_text("{}", encoding="utf-8")
    linked_dir = tmp_path / "linked-fixtures"
    try:
        linked_dir.symlink_to(fixture_dir, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlinks unavailable on this platform: {exc}")

    data, error = checker.read_json_file(linked_dir / "release.json", "--release-json fixture")

    assert data is None
    assert error is not None
    assert "--release-json fixture path must not contain symlinked directories" in error


def test_offline_byte_fixture_rejects_symlinked_file(tmp_path: Path) -> None:
    checker = _load_checker()
    asset = tmp_path / "asset.deb"
    asset.write_bytes(b"asset bytes")
    linked_asset = tmp_path / "asset-link.deb"
    try:
        linked_asset.symlink_to(asset)
    except OSError as exc:
        pytest.skip(f"file symlinks unavailable on this platform: {exc}")

    data, error = checker.read_bytes_file(linked_asset, "--release-asset fixture")

    assert data is None
    assert error == f"--release-asset fixture path must not be a symlink: {linked_asset}"


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
    release_id = 240102
    repository = "example/remote-ops-workspace"
    return {
        "id": release_id,
        "tag_name": "v1.0.2",
        "url": f"https://api.github.com/repos/{repository}/releases/{release_id}",
        "html_url": "https://github.com/example/remote-ops-workspace/releases/tag/v1.0.2",
        "assets_url": f"https://api.github.com/repos/{repository}/releases/{release_id}/assets",
        "upload_url": (
            f"https://uploads.github.com/repos/{repository}/releases/"
            f"{release_id}/assets{{?name,label}}"
        ),
        "draft": False,
        "prerelease": False,
        "created_at": "2026-06-30T11:55:00Z",
        "published_at": "2026-06-30T12:10:00Z",
        "assets": [{"name": name} for name in asset_names],
    }


def _release_with_record_assets(
    checker: Any,
    record: dict[str, Any],
    asset_names: list[str],
    *,
    release_asset_bytes: dict[str, bytes] | None = None,
) -> dict[str, Any]:
    expected = checker.expected_published_assets(record)
    assets = []
    release_id = 240102
    release_repository = "example/remote-ops-workspace"
    for index, name in enumerate(asset_names, start=1):
        metadata = expected.get(name, {})
        browser_download_url = metadata.get(
            "browser_download_url",
            f"https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/{name}",
        )
        repository = checker.repository_from_release_asset_url(browser_download_url)
        asset_id = 1000 + index
        size = metadata.get("size")
        if size is None and release_asset_bytes is not None:
            payload = release_asset_bytes.get(str(browser_download_url))
            if payload is not None:
                size = len(payload)
        assets.append(
            {
                "id": asset_id,
                "node_id": f"MDEyOlJlbGVhc2VBc3NldD{asset_id}",
                "name": name,
                "state": "uploaded",
                "content_type": "application/octet-stream",
                "size": size if size is not None else len(f"published bytes for {name}\n".encode()),
                "digest": f"sha256:{metadata.get('sha256', '0' * 64)}",
                "download_count": 0,
                "url": checker.expected_release_asset_api_url(repository, asset_id),
                "browser_download_url": browser_download_url,
                "created_at": "2026-06-30T12:03:00Z",
                "updated_at": "2026-06-30T12:04:00Z",
            }
        )
    return {
        "id": release_id,
        "tag_name": "v1.0.2",
        "url": f"https://api.github.com/repos/{release_repository}/releases/{release_id}",
        "html_url": "https://github.com/example/remote-ops-workspace/releases/tag/v1.0.2",
        "assets_url": (
            f"https://api.github.com/repos/{release_repository}/releases/{release_id}/assets"
        ),
        "upload_url": (
            f"https://uploads.github.com/repos/{release_repository}/releases/"
            f"{release_id}/assets{{?name,label}}"
        ),
        "draft": False,
        "prerelease": False,
        "created_at": "2026-06-30T11:55:00Z",
        "published_at": "2026-06-30T12:10:00Z",
        "assets": assets,
    }


def _release_asset(release: dict[str, Any], name: str) -> dict[str, Any]:
    for asset in release["assets"]:
        if asset["name"] == name:
            return asset
    raise AssertionError(f"missing release asset fixture {name}")


def _bind_release_asset_bytes(checker: Any, record: dict[str, Any]) -> dict[str, bytes]:
    target = str(record["target"])
    payload_bytes_by_filename: dict[str, bytes] = {}
    manifest_name = ""
    for filename in sorted(record["artifact_sha256"]):
        if filename.endswith(checker.MANIFEST_SUFFIX):
            manifest_name = filename
            continue
        payload = f"published bytes for {filename}\n".encode()
        payload_bytes_by_filename[filename] = payload
        record["artifact_sha256"][filename] = hashlib.sha256(payload).hexdigest()
    if manifest_name:
        manifest_payloads = [
            filename
            for filename in sorted(payload_bytes_by_filename)
            if not filename.endswith(checker.CHECKSUM_SUFFIX)
        ]
        manifest = {
            "artifacts": [
                {
                    "file": filename,
                    "size_bytes": len(payload_bytes_by_filename[filename]),
                    "sha256": hashlib.sha256(payload_bytes_by_filename[filename]).hexdigest(),
                    "architecture": checker.expected_manifest_architecture(target, filename),
                    "format": checker.expected_manifest_format(filename),
                }
                for filename in manifest_payloads
            ]
        }
        manifest_payload = (json.dumps(manifest, indent=2, sort_keys=True) + "\n").encode("utf-8")
        payload_bytes_by_filename[manifest_name] = manifest_payload
        record["artifact_sha256"][manifest_name] = hashlib.sha256(manifest_payload).hexdigest()
    for key in ("manifest", "archive", "sha256s"):
        bundle = record["review_bundle"][key]
        payload = f"published bytes for {bundle['file']}\n".encode()
        bundle["sha256"] = hashlib.sha256(payload).hexdigest()
        bundle["size_bytes"] = len(payload)
    return {
        str(asset["url"]): payload_bytes_by_filename.get(
            str(asset["filename"]),
            f"published bytes for {asset['filename']}\n".encode(),
        )
        for asset in checker.expected_release_asset_byte_sources(record)
    }


def _workflow_runs_for(record: dict[str, Any]) -> dict[str, dict[str, Any]]:
    source = record["release_asset_source"]
    run_url = str(source["workflow_run_url"])
    run_id = int(run_url.rstrip("/").rsplit("/", 1)[-1])
    workflow_id = 445566
    check_suite_id = 998877
    workflow = str(source["workflow"])
    repository = _repository_from_run_url(run_url)
    return {
        workflow: {
            "workflow_runs": [
                {
                    "id": run_id,
                    "node_id": f"WFR_kwLO{run_id}",
                    "url": f"https://api.github.com/repos/{repository}/actions/runs/{run_id}",
                    "html_url": run_url,
                    "run_number": 77,
                    "workflow_id": workflow_id,
                    "workflow_url": f"https://api.github.com/repos/{repository}/actions/workflows/{workflow_id}",
                    "jobs_url": f"https://api.github.com/repos/{repository}/actions/runs/{run_id}/jobs",
                    "logs_url": f"https://api.github.com/repos/{repository}/actions/runs/{run_id}/logs",
                    "artifacts_url": f"https://api.github.com/repos/{repository}/actions/runs/{run_id}/artifacts",
                    "check_suite_id": check_suite_id,
                    "check_suite_url": f"https://api.github.com/repos/{repository}/check-suites/{check_suite_id}",
                    "repository": {"full_name": repository, "id": 1001},
                    "head_repository": {"full_name": repository, "id": 1001},
                    "status": "completed",
                    "conclusion": "success",
                    "event": "workflow_dispatch",
                    "head_sha": source["head_sha"],
                    "head_branch": record["release_tag"],
                    "run_attempt": source["run_attempt"],
                    "path": workflow,
                    "created_at": "2026-06-30T11:59:00Z",
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
    workflow_id = 445566
    check_suite_id = 998877
    workflow = str(source["workflow"])
    repository = _repository_from_run_url(run_url)
    return {
        run_url: {
            "id": run_id,
            "node_id": f"WFR_kwLO{run_id}",
            "url": f"https://api.github.com/repos/{repository}/actions/runs/{run_id}",
            "htmlUrl": run_url,
            "runNumber": 77,
            "workflowId": workflow_id,
            "workflowUrl": f"https://api.github.com/repos/{repository}/actions/workflows/{workflow_id}",
            "jobsUrl": f"https://api.github.com/repos/{repository}/actions/runs/{run_id}/jobs",
            "logsUrl": f"https://api.github.com/repos/{repository}/actions/runs/{run_id}/logs",
            "artifactsUrl": f"https://api.github.com/repos/{repository}/actions/runs/{run_id}/artifacts",
            "checkSuiteId": check_suite_id,
            "checkSuiteUrl": f"https://api.github.com/repos/{repository}/check-suites/{check_suite_id}",
            "repository": {"full_name": repository, "id": 1001},
            "head_repository": {"full_name": repository, "id": 1001},
            "status": "completed",
            "conclusion": "success",
            "event": "workflow_dispatch",
            "headSha": source["head_sha"],
            "headBranch": record["release_tag"],
            "attempt": source["run_attempt"],
            "path": workflow,
            "createdAt": "2026-06-30T11:59:00Z",
            "runStartedAt": "2026-06-30T12:00:00Z",
            "updatedAt": "2026-06-30T12:05:00Z",
        }
    }


def _repository_from_run_url(run_url: str) -> str:
    return run_url.split("https://github.com/", 1)[1].split("/actions/runs/", 1)[0]


def _source_artifacts_for(record: dict[str, Any], *, size_in_bytes: int = 4096) -> dict[str, dict[str, Any]]:
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
                    "node_id": f"MDEyOkFydGlmYWN0{artifact_id}",
                    "name": source["artifact_name"],
                    "url": (
                        "https://api.github.com/repos/example/remote-ops-workspace/"
                        f"actions/artifacts/{artifact_id}"
                    ),
                    "archive_download_url": (
                        "https://api.github.com/repos/example/remote-ops-workspace/"
                        f"actions/artifacts/{artifact_id}/zip"
                    ),
                    "expired": False,
                    "size_in_bytes": size_in_bytes,
                    "created_at": "2026-06-30T12:03:00Z",
                    "updated_at": "2026-06-30T12:04:00Z",
                    "expires_at": "2026-09-28T12:04:00Z",
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


def _source_artifact_zip_for(checker: Any, record: dict[str, Any]) -> dict[str, bytes]:
    source = record["release_asset_source"]
    return {
        str(source["workflow_run_url"]): _zip_named_bytes(
            _source_artifact_zip_file_bytes(checker, record)
        )
    }


def _source_artifact_zip_file_bytes(checker: Any, record: dict[str, Any]) -> dict[str, bytes]:
    release_asset_bytes_by_url = _bind_release_asset_bytes(checker, record)
    source_file_bytes: dict[str, bytes] = {}
    for asset in checker.expected_release_asset_byte_sources(record):
        url = str(asset["url"])
        source_file_bytes[str(asset["filename"])] = release_asset_bytes_by_url[url]
    target = str(record["target"])
    source_file_bytes[checker.accepted_record_source_file(target)] = checker.canonical_public_record_bytes(record)
    return source_file_bytes


def _zip_named_bytes(file_bytes_by_name: dict[str, bytes]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as archive:
        for filename, payload in sorted(file_bytes_by_name.items()):
            archive.writestr(filename, payload)
    return buffer.getvalue()


def _zip_bytes(filenames: list[str]) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, mode="w") as archive:
        for filename in filenames:
            archive.writestr(filename, f"source artifact bytes for {filename}\n")
    return buffer.getvalue()


def _zip_with_symlink_entry(filename: str) -> bytes:
    return _zip_with_mode_entry(filename, 0o120777)


def _zip_with_mode_entry(filename: str, mode: int) -> bytes:
    buffer = io.BytesIO()
    info = zipfile.ZipInfo(filename)
    info.external_attr = mode << 16
    with zipfile.ZipFile(buffer, mode="w") as archive:
        archive.writestr(info, b"link-target")
    return buffer.getvalue()


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

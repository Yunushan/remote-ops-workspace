from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

POLICY = (
    "Only accepted evidence records in this file can promote Linux i386, Linux armhf, "
    "or Windows XP native-host readiness. Accepted records must include release asset URLs, "
    "review-bundle manifest release asset URL binding, review bundle release asset URLs, "
    "release-importable artifact source binding, "
    "release source head SHA binding, "
    "release source workflow file binding, "
    "finalized accepted-record source file binding, "
    "Linux release source artifact names must be target/release-scoped, "
    "XP release source artifact names must be target/release-scoped, "
    "and per-artifact SHA-256 digests, Linux builder identity evidence, builder identity "
    "SHA-256, builder identity release/run binding, "
    "Linux builder/smoke source file binding, "
    "Linux builder source head SHA binding, "
    "Linux builder host identity binding when applicable, "
    "Linux builder rpm and non-interactive sudo evidence, Linux security patch evidence, "
    "Linux native build and smoke command provenance, "
    "Linux smoke evidence SHA-256 and Linux smoke release/run binding, "
    "Linux workflow dispatch inputs when applicable, XP workflow dispatch inputs when applicable, "
    "XP evidence source file binding, XP evidence bundle SHA-256 digests, "
    "XP evidence validation command binding, XP evidence contract SHA-256, "
    "XP evidence summary binding, XP host identity SHA-256 binding, XP security patch evidence, "
    "tracked scripts/xp_smoke_runner.cmd XP smoke command provenance, "
    "canonical XP smoke proof-file command binding, "
    "canonical XP smoke evidence-file summary binding and "
    "XP security smoke proof-line binding when applicable, and review "
    "bundle manifest, review bundle archive, and review bundle SHA-256 sidecar digests "
    "before strict promotion, and release uploads must include those review bundle files with matching "
    "size, SHA-256 and checksum-sidecar coverage; each accepted record must include "
    "the promotion config SHA-256, have a unique target, all release evidence for one record must "
    "use the same GitHub repository, and Windows XP x86/x64 pairs must use the same release_tag "
    "and GitHub repository. "
    "Empty means no promotion."
)


def test_platform_verified_evidence_checker_passes_empty_registry() -> None:
    checker = _load_platform_verified_evidence_checker()

    assert checker.main() == 0


def test_platform_verified_evidence_rejects_missing_xp_validation_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("XP evidence validation command binding, ", ""),
            "accepted_evidence": [],
        }
    )

    assert "platform verified evidence policy must require XP evidence validation command binding" in errors


def test_platform_verified_evidence_rejects_missing_xp_workflow_input_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("XP workflow dispatch inputs when applicable, ", ""),
            "accepted_evidence": [],
        }
    )

    assert "platform verified evidence policy must require XP workflow dispatch input binding" in errors


def test_platform_verified_evidence_rejects_missing_xp_evidence_source_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("XP evidence source file binding, ", ""),
            "accepted_evidence": [],
        }
    )

    assert "platform verified evidence policy must require XP evidence source file binding" in errors


def test_platform_verified_evidence_rejects_missing_linux_workflow_input_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("Linux workflow dispatch inputs when applicable, ", ""),
            "accepted_evidence": [],
        }
    )

    assert "platform verified evidence policy must require Linux workflow dispatch input binding" in errors


def test_platform_verified_evidence_rejects_missing_review_bundle_manifest_url_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("review-bundle manifest release asset URL binding, ", ""),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must require review-bundle manifest release asset URL binding"
    ) in errors


def test_platform_verified_evidence_rejects_missing_review_bundle_upload_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace(
                "and release uploads must include those review bundle files with matching "
                "size, SHA-256 and checksum-sidecar coverage; ",
                "",
            ),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must require release upload review bundle size, "
        "SHA-256, and checksum-sidecar coverage"
    ) in errors


def test_platform_verified_evidence_rejects_missing_release_asset_source_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("release-importable artifact source binding, ", ""),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must require release-importable artifact source binding"
    ) in errors


def test_platform_verified_evidence_rejects_missing_xp_release_source_artifact_scope_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace(
                "XP release source artifact names must be target/release-scoped, ",
                "",
            ),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must require target/release-scoped XP release source artifacts"
    ) in errors


def test_platform_verified_evidence_rejects_missing_xp_smoke_proof_file_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("canonical XP smoke proof-file command binding, ", ""),
            "accepted_evidence": [],
        }
    )

    assert "platform verified evidence policy must require canonical XP smoke proof-file command binding" in errors


def test_platform_verified_evidence_rejects_missing_linux_release_source_artifact_scope_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace(
                "Linux release source artifact names must be target/release-scoped, ",
                "",
            ),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must require target/release-scoped Linux release source artifacts"
    ) in errors


def test_platform_verified_evidence_rejects_missing_release_source_head_sha_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("release source head SHA binding, ", ""),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must require release source head SHA binding"
    ) in errors


def test_platform_verified_evidence_rejects_missing_release_source_workflow_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("release source workflow file binding, ", ""),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must require release source workflow file binding"
    ) in errors


def test_platform_verified_evidence_rejects_missing_final_record_source_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("finalized accepted-record source file binding, ", ""),
            "accepted_evidence": [],
        }
    )

    assert "platform verified evidence policy must require finalized accepted-record source file binding" in errors


def test_platform_verified_evidence_rejects_missing_linux_builder_source_head_sha_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("Linux builder source head SHA binding, ", ""),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must require Linux builder source head SHA binding"
    ) in errors


def test_platform_verified_evidence_rejects_missing_linux_source_file_binding_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("Linux builder/smoke source file binding, ", ""),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must require Linux builder/smoke source file binding"
    ) in errors


def test_platform_verified_evidence_cli_requires_finalized_review_bundle(tmp_path: Path) -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    del record["review_bundle"]
    record["release_asset_source"]["contains_files"] = [
        filename
        for filename in record["release_asset_source"]["contains_files"]
        if not str(filename).startswith("extended-linux-evidence-bundle-")
        and filename != "platform-verified-evidence-linux-i386-final.json"
    ]
    registry_path = tmp_path / "platform_verified_evidence.json"
    registry_path.write_text(
        json.dumps(
            {
                "schema_version": 1,
                "policy": POLICY,
                "accepted_evidence": [record],
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )
    original_path = checker.EVIDENCE_PATH
    checker.EVIDENCE_PATH = registry_path
    try:
        assert checker.main() == 1
        assert checker.main(["--allow-unfinalized-candidates"]) == 0
    finally:
        checker.EVIDENCE_PATH = original_path


def test_platform_verified_evidence_goal_required_targets_fail_empty_registry() -> None:
    checker = _load_platform_verified_evidence_checker()
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [],
    }

    errors = checker.check_platform_verified_evidence(
        registry=registry,
        required_targets=checker.PROTECTED_GOAL_TARGETS,
    )

    assert errors == ["protected platform goal required targets require --release-tag vX.Y.Z"]


def test_platform_verified_evidence_goal_required_targets_fail_empty_registry_with_release_tag() -> None:
    checker = _load_platform_verified_evidence_checker()
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [],
    }

    errors = checker.check_platform_verified_evidence(
        registry=registry,
        required_targets=checker.PROTECTED_GOAL_TARGETS,
        required_release_tag="v1.0.2",
    )

    assert errors == [
        "missing required accepted evidence targets for release_tag v1.0.2: "
        "['linux-armhf', 'linux-i386', 'windows-xp-native-x64', 'windows-xp-native-x86']"
    ]


def test_platform_verified_evidence_goal_required_targets_pass_with_all_records() -> None:
    checker = _load_platform_verified_evidence_checker()
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [
            _linux_record("linux-i386"),
            _linux_record("linux-armhf"),
            _xp_record("windows-xp-native-x86"),
            _xp_record("windows-xp-native-x64"),
        ],
    }

    errors = checker.check_platform_verified_evidence(
        registry=registry,
        required_targets=checker.PROTECTED_GOAL_TARGETS,
        required_release_tag="v1.0.2",
        require_review_bundles=True,
    )

    assert errors == []


def test_platform_verified_evidence_goal_required_targets_reject_mixed_release_repositories() -> None:
    checker = _load_platform_verified_evidence_checker()
    xp_x64 = _xp_record("windows-xp-native-x64")
    _replace_release_repository(xp_x64, "other/remote-ops-workspace")
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [
            _linux_record("linux-i386"),
            _linux_record("linux-armhf"),
            _xp_record("windows-xp-native-x86"),
            xp_x64,
        ],
    }

    errors = checker.check_platform_verified_evidence(
        registry=registry,
        required_targets=checker.PROTECTED_GOAL_TARGETS,
        required_release_tag="v1.0.2",
        require_review_bundles=True,
    )

    assert (
        "protected platform goal evidence for release_tag v1.0.2 must use one GitHub release repository, "
        "got {'linux-armhf': ['example/remote-ops-workspace'], "
        "'linux-i386': ['example/remote-ops-workspace'], "
        "'windows-xp-native-x64': ['other/remote-ops-workspace'], "
        "'windows-xp-native-x86': ['example/remote-ops-workspace']}"
    ) in errors


def test_platform_verified_evidence_rejects_xp_pair_mixed_release_repositories() -> None:
    checker = _load_platform_verified_evidence_checker()
    xp_x64 = _xp_record("windows-xp-native-x64")
    _replace_release_repository(xp_x64, "other/remote-ops-workspace")
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [
            _xp_record("windows-xp-native-x86"),
            xp_x64,
        ],
    }

    errors = checker.check_platform_verified_evidence(
        registry=registry,
        require_review_bundles=True,
    )

    assert (
        "Windows XP native evidence pair must use one GitHub release repository, "
        "got {'windows-xp-native-x64': ['other/remote-ops-workspace'], "
        "'windows-xp-native-x86': ['example/remote-ops-workspace']}"
    ) in errors


def test_platform_verified_evidence_goal_required_targets_reject_wrong_release_tag() -> None:
    checker = _load_platform_verified_evidence_checker()
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [
            _linux_record("linux-i386"),
            _linux_record("linux-armhf"),
            _xp_record("windows-xp-native-x86"),
            _xp_record("windows-xp-native-x64"),
        ],
    }

    errors = checker.check_platform_verified_evidence(
        registry=registry,
        required_targets=checker.PROTECTED_GOAL_TARGETS,
        required_release_tag="v1.0.3",
        require_review_bundles=True,
    )

    assert errors == [
        "missing required accepted evidence targets for release_tag v1.0.3: "
        "['linux-armhf', 'linux-i386', 'windows-xp-native-x64', 'windows-xp-native-x86']"
    ]


def test_platform_verified_evidence_goal_cli_fails_until_required_targets_exist() -> None:
    checker = _load_platform_verified_evidence_checker()

    assert checker.main(["--require-goal-targets"]) == 1


def test_platform_verified_evidence_single_required_target_can_be_unscoped() -> None:
    checker = _load_platform_verified_evidence_checker()
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [_linux_record("linux-i386")],
    }

    errors = checker.check_platform_verified_evidence(
        registry=registry,
        required_targets=("linux-i386",),
        require_review_bundles=True,
    )

    assert errors == []


def test_platform_verified_evidence_accepts_linux_i386_record() -> None:
    checker = _load_platform_verified_evidence_checker()
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [_linux_record("linux-i386")],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert errors == []


def test_platform_verified_evidence_requires_review_bundle_when_strict() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    del record["review_bundle"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry, require_review_bundles=True)

    assert "linux-i386 review_bundle must be an object" in errors


def test_platform_verified_evidence_rejects_review_bundle_name_mismatch() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x64")
    record["review_bundle"]["manifest"]["file"] = "wrong.json"
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry, require_review_bundles=True)

    assert (
        "windows-xp-native-x64 review_bundle manifest.file must be "
        "xp-native-evidence-bundle-windows-xp-native-x64-v1.0.2.json"
    ) in errors


def test_platform_verified_evidence_rejects_review_bundle_missing_release_asset_urls() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    del record["review_bundle"]["release_asset_urls"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry, require_review_bundles=True)

    assert "linux-i386 review_bundle release_asset_urls must be a non-empty list" in errors


def test_platform_verified_evidence_rejects_review_bundle_repository_mismatch() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x64")
    record["review_bundle"]["release_asset_urls"] = [
        url.replace(
            "https://github.com/example/remote-ops-workspace/",
            "https://github.com/other/remote-ops-workspace/",
        )
        for url in record["review_bundle"]["release_asset_urls"]
    ]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry, require_review_bundles=True)

    assert (
        "windows-xp-native-x64 review_bundle release asset URLs must use release asset repository "
        "['example/remote-ops-workspace'], got ['other/remote-ops-workspace']"
    ) in errors


def test_platform_verified_evidence_rejects_missing_promotion_config_hash() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    del record["promotion_config_sha256"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 promotion_config_sha256 must be a SHA-256 hex digest" in errors


def test_platform_verified_evidence_rejects_stale_promotion_config_hash() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["promotion_config_sha256"] = "0" * 64
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "windows-xp-native-x86 promotion_config_sha256 must match current promotion config SHA-256" in errors


def test_platform_verified_evidence_rejects_missing_release_asset_urls() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-armhf")
    record["release_asset_urls"] = []
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-armhf evidence must include release_asset_urls" in errors


def test_platform_verified_evidence_rejects_missing_artifact_sha256() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-armhf")
    del record["artifact_sha256"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-armhf evidence must include artifact_sha256 map" in errors


def test_platform_verified_evidence_rejects_release_asset_url_tag_mismatch() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["release_asset_urls"][0] = record["release_asset_urls"][0].replace(
        "/releases/download/v1.0.2/",
        "/releases/download/v9.9.9/",
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert any("linux-i386 release asset URL tag must match release_tag v1.0.2" in error for error in errors)


def test_platform_verified_evidence_rejects_mixed_release_repositories() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["release_asset_urls"][0] = record["release_asset_urls"][0].replace(
        "github.com/example/remote-ops-workspace",
        "github.com/other/remote-ops-workspace",
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert any("windows-xp-native-x86 release asset URLs must use one GitHub repository" in error for error in errors)


def test_platform_verified_evidence_rejects_unexpected_release_asset_url() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["release_asset_urls"].append(
        "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/"
        "remote-ops-workspace-v1.0.2-windows-xp-x86-extra.zip"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert any(
        "windows-xp-native-x86 release asset URLs reference unexpected files" in error
        for error in errors
    )


def test_platform_verified_evidence_rejects_duplicate_release_asset_url() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["release_asset_urls"].append(record["release_asset_urls"][0])
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert any("linux-i386 release asset URLs contain duplicate files" in error for error in errors)


def test_platform_verified_evidence_rejects_linux_workflow_repository_mismatch() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["workflow_run_url"] = "https://github.com/other/remote-ops-workspace/actions/runs/12345"
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert any("linux-i386 workflow_run_url repository must match release asset repository" in error for error in errors)


def test_platform_verified_evidence_rejects_linux_smoke_run_context_mismatch() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["workflow_run_url"] = "https://github.com/example/remote-ops-workspace/actions/runs/67890"
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "linux-i386 native_smoke_command must be "
        "'bash scripts/smoke_linux_native.sh --arch i386 --dist native-dist/linux "
        "--target linux-i386 --workflow-run-url "
        "https://github.com/example/remote-ops-workspace/actions/runs/67890'"
    ) in errors


def test_platform_verified_evidence_rejects_missing_linux_workflow_inputs() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    del record["workflow_inputs"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 evidence must include workflow_inputs object" in errors


def test_platform_verified_evidence_rejects_missing_release_asset_source() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    del record["release_asset_source"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 release_asset_source must be an object" in errors


def test_platform_verified_evidence_rejects_missing_release_source_head_sha() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    del record["release_asset_source"]["head_sha"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 release_asset_source.head_sha must be a 40-character lowercase Git SHA" in errors


def test_platform_verified_evidence_rejects_release_source_workflow_drift() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["release_asset_source"]["workflow"] = ".github/workflows/extended-platform-evidence.yml"
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry, require_review_bundles=True)

    assert (
        "windows-xp-native-x86 release_asset_source.workflow must be "
        ".github/workflows/xp-native-evidence.yml"
    ) in errors


def test_platform_verified_evidence_rejects_unimportable_release_asset_source() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x64")
    record["release_asset_source"] = {
        "type": "manual-local-folder",
        "workflow": ".github/workflows/xp-native-evidence.yml",
        "workflow_run_url": "https://github.com/other/remote-ops-workspace/actions/runs/12345",
        "artifact_name": "<artifact>",
        "contains_files": ["remote-ops-workspace-v1.0.2-windows-xp-x64-native.zip"],
    }
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry, require_review_bundles=True)

    assert (
        "windows-xp-native-x64 release_asset_source.type must be one of "
        "['github-actions-artifact'], got 'manual-local-folder'"
    ) in errors
    assert (
        "windows-xp-native-x64 release_asset_source.workflow_run_url repository must match "
        "release asset repository ['example/remote-ops-workspace'], got other/remote-ops-workspace"
    ) in errors
    assert "windows-xp-native-x64 release_asset_source.artifact_name must be a concrete artifact name" in errors
    assert any("windows-xp-native-x64 release_asset_source.contains_files missing files" in error for error in errors)


def test_platform_verified_evidence_rejects_xp_release_asset_source_name_drift() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["release_asset_source"]["artifact_name"] = "xp-native-evidence-windows-xp-native-x64-v1.0.2"
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry, require_review_bundles=True)

    assert (
        "windows-xp-native-x86 release_asset_source.artifact_name must be "
        "xp-native-evidence-windows-xp-native-x86-v1.0.2"
    ) in errors


def test_platform_verified_evidence_rejects_linux_release_asset_source_drift() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["release_asset_source"]["workflow_run_url"] = (
        "https://github.com/example/remote-ops-workspace/actions/runs/67890"
    )
    record["release_asset_source"]["artifact_name"] = "wrong-artifact"
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 release_asset_source.workflow_run_url must match workflow_run_url" in errors
    assert (
        "linux-i386 release_asset_source.artifact_name must be "
        "extended-linux-evidence-linux-i386-v1.0.2"
        in errors
    )


def test_platform_verified_evidence_rejects_missing_linux_command_provenance() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    del record["native_build_command"]
    del record["native_smoke_command"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "linux-i386 native_build_command must be "
        "'TARGET_ARCH=i386 PYTHON_BIN=.venv-native/bin/python bash scripts/make_linux_native.sh'"
    ) in errors
    assert (
        "linux-i386 native_smoke_command must be "
        "'bash scripts/smoke_linux_native.sh --arch i386 --dist native-dist/linux "
        "--target linux-i386 --workflow-run-url "
        "https://github.com/example/remote-ops-workspace/actions/runs/12345'"
    ) in errors


def test_platform_verified_evidence_rejects_wrong_linux_command_provenance() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-armhf")
    record["native_build_command"] = "bash scripts/make_linux_native.sh"
    record["native_smoke_command"] = "bash scripts/smoke_linux_native.sh"
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert any("linux-armhf native_build_command must be" in error for error in errors)
    assert any("linux-armhf native_smoke_command must be" in error for error in errors)


def test_platform_verified_evidence_rejects_linux_workflow_input_base_url_mismatch() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-armhf")
    record["workflow_inputs"]["release_asset_base_url"] = (
        "https://github.com/example/remote-ops-workspace/releases/download/v9.9.9"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert any(
        "linux-armhf workflow_inputs release_asset_base_url must be a GitHub release download URL" in error
        for error in errors
    )
    assert "linux-armhf workflow_inputs release_asset_base_url must prefix every release_asset_url" in errors


def test_platform_verified_evidence_rejects_artifact_validation_command_tag_mismatch() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-armhf")
    record["artifact_validation_command"] = record["artifact_validation_command"].replace(
        "--tag v1.0.2",
        "--tag v9.9.9",
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-armhf artifact_validation_command must include exactly one --tag v1.0.2, got ['v9.9.9']" in errors


def test_platform_verified_evidence_rejects_duplicate_artifact_validation_command_tag() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["artifact_validation_command"] = (
        f"{record['artifact_validation_command']} --tag v9.9.9"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "linux-i386 artifact_validation_command must include exactly one --tag v1.0.2, "
        "got ['v1.0.2', 'v9.9.9']"
    ) in errors


def test_platform_verified_evidence_rejects_missing_artifact_validation_assets_dir() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["artifact_validation_command"] = (
        "python scripts/check_platform_promotion_artifacts.py --target windows-xp-native-x86 --tag v1.0.2"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "windows-xp-native-x86 artifact_validation_command must include exactly one --assets-dir, got []" in errors


def test_platform_verified_evidence_rejects_placeholder_artifact_validation_assets_dir() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x64")
    record["artifact_validation_command"] = (
        "python scripts/check_platform_promotion_artifacts.py --target windows-xp-native-x64 "
        "--assets-dir <artifact-dir> --tag v1.0.2"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x64 artifact_validation_command --assets-dir must be concrete, got '<artifact-dir>'"
        in errors
    )


def test_platform_verified_evidence_rejects_unsafe_linux_artifact_validation_assets_dir() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["artifact_validation_command"] = (
        "python scripts/check_platform_promotion_artifacts.py --target linux-i386 "
        "--assets-dir .github/linux-i386 --tag v1.0.2"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "linux-i386 artifact_validation_command --assets-dir "
        "must not point inside reserved workspace directory '.github'"
    ) in errors


def test_platform_verified_evidence_rejects_wildcard_xp_artifact_validation_assets_dir() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["artifact_validation_command"] = (
        "python scripts/check_platform_promotion_artifacts.py --target windows-xp-native-x86 "
        "--assets-dir staged/xp-x86/* --tag v1.0.2"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x86 artifact_validation_command --assets-dir "
        "must not contain wildcards, got 'staged/xp-x86/*'"
    ) in errors


def test_platform_verified_evidence_rejects_unscoped_xp_artifact_validation_assets_dir() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["artifact_validation_command"] = (
        "python scripts/check_platform_promotion_artifacts.py --target windows-xp-native-x86 "
        "--assets-dir native-dist/windows-xp --tag v1.0.2"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x86 artifact_validation_command --assets-dir "
        "must include target path segment 'windows-xp-native-x86', got 'native-dist/windows-xp'"
    ) in errors
    assert (
        "windows-xp-native-x86 artifact_validation_command --assets-dir "
        "must include release_tag path segment 'v1.0.2', got 'native-dist/windows-xp'"
    ) in errors


def test_platform_verified_evidence_rejects_missing_xp_native_validation_evidence_path() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["native_evidence_validation_command"] = (
        "python scripts/check_xp_native_evidence.py --assets-dir native-dist/windows-xp"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x86 native_evidence_validation_command must include exactly one --evidence, "
        "got []"
    ) in errors


def test_platform_verified_evidence_rejects_placeholder_xp_native_validation_paths() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x64")
    record["native_evidence_validation_command"] = (
        "python scripts/check_xp_native_evidence.py --evidence <evidence.json> "
        "--assets-dir <artifact-dir> --evidence-dir <evidence-dir>"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x64 native_evidence_validation_command --evidence must be concrete, "
        "got '<evidence.json>'"
    ) in errors
    assert (
        "windows-xp-native-x64 native_evidence_validation_command --assets-dir must be concrete, "
        "got '<artifact-dir>'"
    ) in errors
    assert (
        "windows-xp-native-x64 native_evidence_validation_command --evidence-dir must be concrete, "
        "got '<evidence-dir>'"
    ) in errors


def test_platform_verified_evidence_rejects_unsafe_xp_native_validation_paths() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["native_evidence_validation_command"] = (
        "python scripts/check_xp_native_evidence.py "
        "--evidence .github/xp-evidence.json "
        "--assets-dir /tmp/xp-artifacts "
        "--evidence-dir staged/.private-smoke"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x86 native_evidence_validation_command --evidence "
        "must not point inside reserved workspace directory '.github'"
    ) in errors
    assert (
        "windows-xp-native-x86 native_evidence_validation_command --assets-dir "
        "must be workspace-relative, got '/tmp/xp-artifacts'"
    ) in errors
    assert (
        "windows-xp-native-x86 native_evidence_validation_command --evidence-dir "
        "must not contain hidden path segments: ['.private-smoke']"
    ) in errors


def test_platform_verified_evidence_rejects_wildcard_xp_native_validation_paths() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x64")
    record["native_evidence_validation_command"] = (
        "python scripts/check_xp_native_evidence.py "
        "--evidence staged/windows-xp-native-x64/v1.0.2/*.json "
        "--assets-dir staged/windows-xp-native-x64/v1.0.2/artifacts "
        "--evidence-dir staged/windows-xp-native-x64/v1.0.2/smoke"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x64 native_evidence_validation_command --evidence "
        "must not contain wildcards, got 'staged/windows-xp-native-x64/v1.0.2/*.json'"
    ) in errors


def test_platform_verified_evidence_rejects_unscoped_xp_native_validation_paths() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["native_evidence_validation_command"] = (
        "python scripts/check_xp_native_evidence.py "
        "--evidence evidence/windows-xp-native-x86/xp-evidence.json "
        "--assets-dir native-dist/windows-xp "
        "--evidence-dir evidence/windows-xp-native-x86/smoke"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x86 native_evidence_validation_command --evidence "
        "must include release_tag path segment 'v1.0.2', got 'evidence/windows-xp-native-x86/xp-evidence.json'"
    ) in errors
    assert (
        "windows-xp-native-x86 native_evidence_validation_command --assets-dir "
        "must include target path segment 'windows-xp-native-x86', got 'native-dist/windows-xp'"
    ) in errors
    assert (
        "windows-xp-native-x86 native_evidence_validation_command --assets-dir "
        "must include release_tag path segment 'v1.0.2', got 'native-dist/windows-xp'"
    ) in errors


def test_platform_verified_evidence_rejects_wrong_xp_workflow() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["workflow"] = ".github/workflows/ci.yml"
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "windows-xp-native-x86 workflow must be .github/workflows/xp-native-evidence.yml" in errors


def test_platform_verified_evidence_rejects_missing_xp_workflow_inputs() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x64")
    del record["workflow_inputs"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "windows-xp-native-x64 evidence must include workflow_inputs object" in errors


def test_platform_verified_evidence_rejects_xp_workflow_input_path_drift() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["workflow_inputs"]["evidence_file"] = (
        "evidence/windows-xp-native-x86/v1.0.2/other-xp-evidence.json"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x86 workflow_inputs evidence_file must match "
        "native_evidence_validation_command --evidence"
    ) in errors


def test_platform_verified_evidence_rejects_xp_workflow_input_repository_drift() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x64")
    record["workflow_inputs"]["release_asset_base_url"] = (
        "https://github.com/other/remote-ops-workspace/releases/download/v1.0.2"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "windows-xp-native-x64 workflow_inputs release_asset_base_url must prefix every release_asset_url" in errors
    assert (
        "windows-xp-native-x64 workflow_inputs release_asset_base_url repository must match "
        "release_asset_source.workflow_run_url repository example/remote-ops-workspace, "
        "got other/remote-ops-workspace"
    ) in errors


def test_platform_verified_evidence_rejects_missing_xp_evidence_sources() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    del record["xp_evidence_sources"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "windows-xp-native-x86 xp_evidence_sources must be an object" in errors


def test_platform_verified_evidence_rejects_xp_evidence_source_hash_drift() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x64")
    record["xp_evidence_sources"]["evidence"]["sha256"] = "0" * 64
    record["xp_evidence_sources"]["smoke_evidence"]["cli_launch"]["sha256"] = "9" * 64
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "windows-xp-native-x64 xp_evidence_sources.evidence.sha256 must match xp_evidence_sha256" in errors
    assert (
        "windows-xp-native-x64 xp_evidence_sources.smoke_evidence.cli_launch.sha256 "
        "must match xp_smoke_evidence_sha256"
    ) in errors


def test_platform_verified_evidence_rejects_xp_evidence_source_file_drift() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["xp_evidence_sources"]["evidence"]["path"] = (
        "evidence/windows-xp-native-x86/v1.0.2/other-xp-evidence.json"
    )
    record["xp_evidence_sources"]["smoke_evidence"]["cli_launch"]["file"] = (
        "xp-smoke-evidence/other.txt"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "windows-xp-native-x86 xp_evidence_sources.evidence.path must match workflow_inputs evidence_file" in errors
    assert (
        "windows-xp-native-x86 xp_evidence_sources.smoke_evidence.cli_launch.file "
        "must match xp_evidence_summary smoke_evidence_files"
    ) in errors


def test_platform_verified_evidence_rejects_missing_builder_identity() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    del record["builder_identity"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 evidence must include builder_identity object" in errors


def test_platform_verified_evidence_rejects_missing_builder_identity_digest() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    del record["builder_identity_sha256"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 builder_identity_sha256 must be a SHA-256 hex digest" in errors


def test_platform_verified_evidence_rejects_stale_builder_identity_digest() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-armhf")
    record["builder_identity"]["python_version"] = "3.13.0"
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-armhf builder_identity_sha256 must match builder_identity JSON SHA-256" in errors


def test_platform_verified_evidence_rejects_builder_identity_release_context_mismatch() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["builder_identity"]["release_tag"] = "v9.9.9"
    record["builder_identity"]["workflow_run_url"] = "https://github.com/example/remote-ops-workspace/actions/runs/99999"
    record["builder_identity_sha256"] = _json_sha256(record["builder_identity"])
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 builder_identity release_tag must match record release_tag v1.0.2" in errors
    assert "linux-i386 builder_identity workflow_run_url must match record workflow_run_url" in errors


def test_platform_verified_evidence_rejects_builder_identity_source_head_sha_mismatch() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["builder_identity"]["source_head_sha"] = "b" * 40
    record["builder_identity_sha256"] = _json_sha256(record["builder_identity"])
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 builder_identity source_head_sha must match release_asset_source.head_sha" in errors


def test_platform_verified_evidence_rejects_missing_linux_builder_host_identity() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    del record["builder_identity"]["host_identity"]
    record["builder_identity_sha256"] = _json_sha256(record["builder_identity"])
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 builder_identity host_identity must be an object" in errors


def test_platform_verified_evidence_rejects_private_linux_builder_host_identity_fields() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-armhf")
    record["builder_identity"]["host_identity"]["host_label"] = "yunus-pc"
    record["builder_identity"]["host_identity"]["hostname"] = "yunus-pc"
    record["builder_identity_sha256"] = _json_sha256(record["builder_identity"])
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "linux-armhf builder_identity host_identity.host_label must be a sanitized target-scoped label, "
        "got 'yunus-pc'"
    ) in errors
    assert (
        "linux-armhf builder_identity host_identity contains forbidden private fields: ['hostname']"
    ) in errors


def test_platform_verified_evidence_rejects_wrong_builder_machine() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-armhf")
    record["builder_identity"]["uname_machine"] = "x86_64"
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert any("linux-armhf builder_identity uname_machine must be one of" in error for error in errors)


def test_platform_verified_evidence_rejects_wrong_linux_dpkg_architecture() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-armhf")
    record["builder_identity"]["dpkg_architecture"] = "arm64"
    record["builder_identity_sha256"] = _json_sha256(record["builder_identity"])
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-armhf builder_identity dpkg_architecture must be one of ['armhf'], got 'arm64'" in errors


def test_platform_verified_evidence_rejects_wrong_linux_userland_bits() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["builder_identity"]["userland_bits"] = "64"
    record["builder_identity_sha256"] = _json_sha256(record["builder_identity"])
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 builder_identity userland_bits must be '32', got '64'" in errors


def test_platform_verified_evidence_rejects_weak_linux_tool_paths() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["builder_identity"]["required_tools"]["bash"] = "bash"
    record["builder_identity"]["required_tools"]["curl"] = "<curl>"
    record["builder_identity_sha256"] = _json_sha256(record["builder_identity"])
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 builder_identity required_tools.bash must be an absolute Linux path, got 'bash'" in errors
    assert "linux-i386 builder_identity required_tools.curl must be concrete, got '<curl>'" in errors


def test_platform_verified_evidence_rejects_missing_noninteractive_sudo() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    del record["builder_identity"]["sudo_non_interactive"]
    record["builder_identity_sha256"] = _json_sha256(record["builder_identity"])
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 builder_identity sudo_non_interactive must be true" in errors


def test_platform_verified_evidence_rejects_missing_linux_security_patch_evidence() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    del record["builder_identity"]["security_patch_evidence"]
    record["builder_identity_sha256"] = _json_sha256(record["builder_identity"])
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 builder_identity security_patch_evidence must be an object" in errors


def test_platform_verified_evidence_rejects_missing_linux_smoke_evidence() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    del record["linux_smoke_evidence_sha256"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 linux_smoke_evidence_sha256 must be an object" in errors


def test_platform_verified_evidence_rejects_wrong_linux_smoke_evidence() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-armhf")
    record["linux_smoke_evidence_sha256"] = {"native_smoke": "not-a-sha256"}
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-armhf linux_smoke_evidence_sha256 for native_smoke must be a SHA-256 hex digest" in errors


def test_platform_verified_evidence_rejects_missing_linux_evidence_sources() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    del record["linux_evidence_sources"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 linux_evidence_sources must be an object" in errors


def test_platform_verified_evidence_rejects_linux_evidence_source_hash_mismatch() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-armhf")
    record["linux_evidence_sources"]["native_smoke"]["sha256"] = "0" * 64
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "linux-armhf linux_evidence_sources.native_smoke.sha256 "
        "must match native_smoke evidence SHA-256"
    ) in errors


def test_platform_verified_evidence_rejects_duplicate_target_records() -> None:
    checker = _load_platform_verified_evidence_checker()
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [_linux_record("linux-i386"), _linux_record("linux-i386")],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "accepted_evidence target must be unique: linux-i386" in errors


def test_platform_verified_evidence_rejects_mismatched_xp_pair_release_tags() -> None:
    checker = _load_platform_verified_evidence_checker()
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [
            _xp_record("windows-xp-native-x86", release_tag="v1.0.2"),
            _xp_record("windows-xp-native-x64", release_tag="v1.0.3"),
        ],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "Windows XP native evidence pair must use one release_tag, got ['v1.0.2', 'v1.0.3']" in errors


def test_platform_verified_evidence_rejects_partial_xp_pair() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["checks"] = ["artifact_validation"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert any("windows-xp-native-x86 evidence missing required checks" in error for error in errors)


def test_platform_verified_evidence_rejects_missing_xp_evidence_digest() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    del record["xp_evidence_sha256"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "windows-xp-native-x86 xp_evidence_sha256 must be a SHA-256 hex digest" in errors


def test_platform_verified_evidence_rejects_missing_xp_contract_digest() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    del record["xp_evidence_contract_sha256"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "windows-xp-native-x86 xp_evidence_contract_sha256 must be a SHA-256 hex digest" in errors


def test_platform_verified_evidence_rejects_stale_xp_contract_digest() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x64")
    record["xp_evidence_contract_sha256"] = "0" * 64
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x64 xp_evidence_contract_sha256 must match current XP evidence contract SHA-256"
        in errors
    )


def test_platform_verified_evidence_rejects_missing_xp_host_identity_digest() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    del record["xp_host_identity_sha256"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "windows-xp-native-x86 xp_host_identity_sha256 must be a SHA-256 hex digest" in errors


def test_platform_verified_evidence_rejects_xp_host_identity_digest_mismatch() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x64")
    record["xp_host_identity_sha256"] = "0" * 64
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "windows-xp-native-x64 xp_host_identity_sha256 must match xp_evidence_summary host_identity" in errors


def test_platform_verified_evidence_rejects_missing_xp_host_identity_summary() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    del record["xp_evidence_summary"]["host_identity"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "windows-xp-native-x86 xp_evidence_summary host_identity must be an object" in errors


def test_platform_verified_evidence_rejects_missing_xp_smoke_digest() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x64")
    del record["xp_smoke_evidence_sha256"]["cli_launch"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert any("windows-xp-native-x64 xp_smoke_evidence_sha256 missing smoke ids" in error for error in errors)


def test_platform_verified_evidence_rejects_missing_xp_evidence_summary() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    del record["xp_evidence_summary"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "windows-xp-native-x86 xp_evidence_summary must be an object" in errors


def test_platform_verified_evidence_rejects_xp_evidence_summary_target_mismatch() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x64")
    record["xp_evidence_summary"]["target"] = "windows-xp-native-x86"
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "windows-xp-native-x64 xp_evidence_summary target must be windows-xp-native-x64" in errors


def test_platform_verified_evidence_rejects_missing_xp_smoke_commands() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    del record["xp_evidence_summary"]["smoke_commands"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "windows-xp-native-x86 xp_evidence_summary smoke_commands must be an object" in errors


def test_platform_verified_evidence_rejects_missing_xp_smoke_evidence_files() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    del record["xp_evidence_summary"]["smoke_evidence_files"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "windows-xp-native-x86 xp_evidence_summary smoke_evidence_files must be an object" in errors


def test_platform_verified_evidence_rejects_noncanonical_xp_smoke_evidence_file() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["xp_evidence_summary"]["smoke_evidence_files"]["cli_launch"] = "xp-smoke-evidence/other.txt"
    record["xp_evidence_summary"]["smoke_commands"]["cli_launch"] = (
        "scripts/xp_smoke_runner.cmd --target windows-xp-native-x86 --release-tag v1.0.2 "
        "--smoke-id cli_launch --evidence-file xp-smoke-evidence/other.txt"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x86 xp_evidence_summary smoke_evidence_files cli_launch "
        "must be xp-smoke-evidence/cli_launch.txt, got 'xp-smoke-evidence/other.txt'"
    ) in errors


def test_platform_verified_evidence_rejects_placeholder_xp_smoke_command() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["xp_evidence_summary"]["smoke_commands"]["cli_launch"] = "<command>"
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x86 xp_evidence_summary smoke_commands cli_launch must be concrete, got '<command>'"
        in errors
    )


def test_platform_verified_evidence_rejects_xp_smoke_command_target_mismatch() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["xp_evidence_summary"]["smoke_commands"]["cli_launch"] = (
        "scripts/xp_smoke_runner.cmd --target windows-xp-native-x64 --release-tag v1.0.2 "
        "--smoke-id cli_launch"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x86 xp_evidence_summary smoke_commands cli_launch must include exactly one "
        "--target windows-xp-native-x86, got ['windows-xp-native-x64']"
    ) in errors


def test_platform_verified_evidence_rejects_xp_smoke_command_evidence_file_mismatch() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["xp_evidence_summary"]["smoke_commands"]["cli_launch"] = (
        "scripts/xp_smoke_runner.cmd --target windows-xp-native-x86 --release-tag v1.0.2 "
        "--smoke-id cli_launch --evidence-file xp-smoke-evidence/other.txt"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x86 xp_evidence_summary smoke_commands cli_launch must include exactly one "
        "--evidence-file xp-smoke-evidence/cli_launch.txt, got ['xp-smoke-evidence/other.txt']"
    ) in errors


def test_platform_verified_evidence_rejects_xp_smoke_command_proof_file_mismatch() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["xp_evidence_summary"]["smoke_commands"]["cli_launch"] = (
        "scripts/xp_smoke_runner.cmd --target windows-xp-native-x86 --release-tag v1.0.2 "
        "--smoke-id cli_launch --evidence-file xp-smoke-evidence/cli_launch.txt "
        "--proof-file xp-smoke-proof/other.txt"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x86 xp_evidence_summary smoke_commands cli_launch must include exactly one "
        "--proof-file xp-smoke-proof/cli_launch.txt, got ['xp-smoke-proof/other.txt']"
    ) in errors


def test_platform_verified_evidence_rejects_untracked_xp_smoke_runner() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["xp_evidence_summary"]["smoke_commands"]["cli_launch"] = (
        "xp-smoke-runner --target windows-xp-native-x86 --release-tag v1.0.2 --smoke-id cli_launch"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert any(
        "windows-xp-native-x86 xp_evidence_summary smoke_commands cli_launch "
        "must start with 'scripts/xp_smoke_runner.cmd'"
        in error
        for error in errors
    )


def test_platform_verified_evidence_rejects_missing_xp_security_patch_summary() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    del record["xp_evidence_summary"]["security"]["patch_evidence"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "windows-xp-native-x86 xp_evidence_summary security.patch_evidence must be an object" in errors


def test_platform_verified_evidence_rejects_weak_xp_x64_summary() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x64")
    record["xp_evidence_summary"]["os"] = {
        "name": "Windows XP",
        "architecture": "x64",
        "service_pack": "x64",
    }
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x64 xp_evidence_summary os.service_pack must include "
        "'SP2', got 'x64'"
    ) in errors
    assert (
        "windows-xp-native-x64 xp_evidence_summary os.edition must be "
        "'Professional x64 Edition', got None"
    ) in errors


def _linux_record(target: str) -> dict[str, object]:
    arch = "i386" if target == "linux-i386" else "armhf"
    rpm_arch = "i686" if target == "linux-i386" else "armv7hl"
    artifact = f"extended-linux-evidence-{target}-v1.0.2"
    release_asset_urls = [
        f"https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/remote-ops-workspace-v1.0.2-linux-{arch}.deb",
        f"https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/remote-ops-workspace-v1.0.2-linux-{rpm_arch}.rpm",
        f"https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/remote-ops-workspace-v1.0.2-linux-{arch if target == 'linux-armhf' else 'i686'}.AppImage",
        f"https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/remote-ops-workspace-v1.0.2-linux-{arch if target == 'linux-armhf' else 'i686'}-native.tar.gz",
        f"https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/remote-ops-workspace-v1.0.2-linux-{arch if target == 'linux-armhf' else 'i686'}-native-manifest.json",
        f"https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/remote-ops-workspace-v1.0.2-linux-{arch if target == 'linux-armhf' else 'i686'}-native-SHA256SUMS.txt",
    ]
    builder_identity = _builder_identity(target)
    builder_identity_sha = _json_sha256(builder_identity)
    linux_smoke_hashes = _linux_smoke_hashes()
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
            "release_asset_base_url": "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2",
        },
        "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "artifact_name": artifact,
        "release_asset_source": _release_asset_source(
            target,
            artifact,
            release_asset_urls,
            release_tag="v1.0.2",
            include_review_bundle=True,
        ),
        "runner_labels": ["self-hosted", "linux", arch],
        "builder_identity": builder_identity,
        "builder_identity_sha256": builder_identity_sha,
        "linux_evidence_sources": _linux_evidence_sources(
            target,
            builder_identity_sha,
            linux_smoke_hashes["native_smoke"],
        ),
        "native_build_command": (
            f"TARGET_ARCH={arch} PYTHON_BIN=.venv-native/bin/python bash scripts/make_linux_native.sh"
        ),
        "native_smoke_command": (
            f"bash scripts/smoke_linux_native.sh --arch {arch} --dist native-dist/linux "
            f"--target {target} --workflow-run-url https://github.com/example/remote-ops-workspace/actions/runs/12345"
        ),
        "linux_smoke_evidence_sha256": linux_smoke_hashes,
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
        "review_bundle": _review_bundle(target),
    }


def _xp_record(target: str, *, release_tag: str = "v1.0.2") -> dict[str, object]:
    arch = "x86" if target.endswith("x86") else "x64"
    base_url = f"https://github.com/example/remote-ops-workspace/releases/download/{release_tag}"
    evidence_file = f"evidence/{target}/{release_tag}/xp-evidence.json"
    assets_dir = f"native-dist/windows-xp/{target}/{release_tag}"
    evidence_dir = f"evidence/{target}/{release_tag}"
    evidence_summary = _xp_evidence_summary(target, release_tag)
    smoke_hashes = _xp_smoke_hashes()
    release_asset_urls = [
        f"{base_url}/remote-ops-workspace-{release_tag}-windows-xp-{arch}-native.zip",
        f"{base_url}/remote-ops-workspace-{release_tag}-windows-xp-{arch}-native-manifest.json",
        f"{base_url}/remote-ops-workspace-{release_tag}-windows-xp-{arch}-native-SHA256SUMS.txt",
    ]
    return {
        "target": target,
        "evidence_type": "windows-xp-native-host",
        "status": "accepted",
        "readiness_percent": 100.0,
        "release_tag": release_tag,
        "promotion_config_sha256": _promotion_config_sha256(),
        "workflow": ".github/workflows/xp-native-evidence.yml",
        "workflow_inputs": {
            "target": target,
            "release_tag": release_tag,
            "release_asset_base_url": base_url,
            "assets_dir": assets_dir,
            "evidence_file": evidence_file,
            "evidence_dir": evidence_dir,
        },
        "architecture": arch,
        "separate_legacy_toolchain": True,
        "current_python_pyqt6_stack": False,
        "xp_evidence_sha256": "b" * 64,
        "xp_evidence_contract_sha256": _xp_native_evidence_contract_sha256(),
        "xp_host_identity_sha256": _json_sha256(_xp_host_identity(target, release_tag)),
        "xp_evidence_summary": evidence_summary,
        "xp_smoke_evidence_sha256": smoke_hashes,
        "xp_evidence_sources": _xp_evidence_sources(
            evidence_file,
            "b" * 64,
            evidence_summary,
            smoke_hashes,
        ),
        "release_asset_source": _release_asset_source(
            target,
            f"xp-native-evidence-{target}-{release_tag}",
            release_asset_urls,
            release_tag=release_tag,
            include_review_bundle=True,
        ),
        "native_evidence_validation_command": (
            "python scripts/check_xp_native_evidence.py "
            f"--evidence {evidence_file} "
            f"--assets-dir {assets_dir} "
            f"--evidence-dir {evidence_dir}"
        ),
        "artifact_validation_command": (
            f"python scripts/check_platform_promotion_artifacts.py --target {target} "
            f"--assets-dir {assets_dir} --tag {release_tag}"
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
        "review_bundle": _review_bundle(target, release_tag=release_tag),
    }


def _artifact_hashes_from_urls(urls: list[str]) -> dict[str, str]:
    return {Path(url).name: "a" * 64 for url in urls}


def _xp_evidence_sources(
    evidence_file: str,
    evidence_sha: str,
    evidence_summary: dict[str, object],
    smoke_hashes: dict[str, str],
) -> dict[str, object]:
    smoke_files = evidence_summary["smoke_evidence_files"]
    assert isinstance(smoke_files, dict)
    return {
        "evidence": {
            "file": "xp-evidence.json",
            "path": evidence_file,
            "size_bytes": 4096,
            "sha256": evidence_sha,
        },
        "smoke_evidence": {
            str(smoke_id): {
                "file": str(smoke_file),
                "size_bytes": 256 + index,
                "sha256": smoke_hashes[str(smoke_id)],
            }
            for index, (smoke_id, smoke_file) in enumerate(sorted(smoke_files.items()))
        },
    }


def _release_asset_source(
    target: str,
    artifact_name: str,
    release_asset_urls: list[str],
    *,
    release_tag: str,
    include_review_bundle: bool,
) -> dict[str, object]:
    contains_files = {Path(url).name for url in release_asset_urls}
    if include_review_bundle:
        review_bundle = _review_bundle(target, release_tag=release_tag)
        contains_files.update(
            str(record.get("file", ""))
            for record in (
                review_bundle["manifest"],
                review_bundle["archive"],
                review_bundle["sha256s"],
            )
            if isinstance(record, dict)
        )
        contains_files.add(f"platform-verified-evidence-{target}-final.json")
    return {
        "type": "github-actions-artifact",
        "workflow": _release_source_workflow(target),
        "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "artifact_name": artifact_name,
        "head_sha": "a" * 40,
        "contains_files": sorted(contains_files),
    }


def _release_source_workflow(target: str) -> str:
    if target.startswith("linux-"):
        return ".github/workflows/extended-platform-evidence.yml"
    return ".github/workflows/xp-native-evidence.yml"


def _linux_smoke_hashes() -> dict[str, str]:
    return {"native_smoke": "6" * 64}


def _linux_evidence_sources(
    target: str,
    builder_identity_sha: str,
    native_smoke_sha: str,
) -> dict[str, object]:
    return {
        "builder_identity": {
            "file": f"builder-identity-{target}.json",
            "sha256": builder_identity_sha,
            "size_bytes": 123,
        },
        "native_smoke": {
            "file": f"native-smoke-{target}.log",
            "sha256": native_smoke_sha,
            "size_bytes": 456,
        },
    }


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


def _replace_release_repository(record: dict[str, object], repository: str) -> None:
    old = "github.com/example/remote-ops-workspace"
    new = f"github.com/{repository}"
    record["release_asset_urls"] = [
        str(url).replace(old, new)
        for url in record.get("release_asset_urls", [])
    ]
    review_bundle = record.get("review_bundle")
    if isinstance(review_bundle, dict):
        review_bundle["release_asset_urls"] = [
            str(url).replace(old, new)
            for url in review_bundle.get("release_asset_urls", [])
        ]


def _xp_evidence_summary(target: str, release_tag: str = "v1.0.2") -> dict[str, object]:
    arch = "x86" if target.endswith("x86") else "x64"
    os_summary: dict[str, object] = {
        "name": "Windows XP",
        "architecture": arch,
        "service_pack": "SP3" if arch == "x86" else "SP2",
    }
    if arch == "x64":
        os_summary["edition"] = "Professional x64 Edition"
    return {
        "target": target,
        "release_tag": release_tag,
        "host_identity": _xp_host_identity(target, release_tag),
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
        "smoke_ids": sorted(_xp_smoke_hashes()),
        "smoke_evidence_files": _xp_smoke_evidence_files(),
        "smoke_commands": _xp_smoke_commands(target, release_tag),
    }


def _xp_host_identity(target: str, release_tag: str = "v1.0.2") -> dict[str, object]:
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
        "release_tag": release_tag,
        "host_label": f"xp-{arch}-lab-01",
        "evidence_run_id": f"xp-{arch}-{release_tag.removeprefix('v').replace('.', '-')}-20260620t120000z",
        "observed_at_utc": "2026-06-20T12:00:00Z",
        "operator_private_data_redacted": True,
        "os": os_summary,
        "toolchain": {
            "separate_legacy_toolchain": True,
            "current_python_pyqt6_stack": False,
            "description": "Separate legacy XP-capable native host toolchain",
        },
    }


def _xp_smoke_hashes() -> dict[str, str]:
    return {
        "cli_launch": "c" * 64,
        "gui_or_legacy_host_ui_launch": "d" * 64,
        "loopback_profile_dry_run": "e" * 64,
        "artifact_manifest_validation": "f" * 64,
        "legacy_crypto_profile_scoped": "1" * 64,
        "modern_defaults_unchanged": "2" * 64,
    }


def _xp_smoke_evidence_files() -> dict[str, str]:
    return {
        smoke_id: f"xp-smoke-evidence/{smoke_id}.txt"
        for smoke_id in sorted(_xp_smoke_hashes())
    }


def _xp_smoke_commands(target: str, release_tag: str = "v1.0.2") -> dict[str, str]:
    return {
        smoke_id: (
            f"scripts/xp_smoke_runner.cmd --target {target} --release-tag {release_tag} "
            f"--smoke-id {smoke_id} --evidence-file xp-smoke-evidence/{smoke_id}.txt "
            f"--proof-file xp-smoke-proof/{smoke_id}.txt"
        )
        for smoke_id in sorted(_xp_smoke_hashes())
    }


def _builder_identity(target: str) -> dict[str, object]:
    machine = "i686" if target == "linux-i386" else "armv7l"
    dpkg_arch = "i386" if target == "linux-i386" else "armhf"
    return {
        "schema_version": 1,
        "target": target,
        "release_tag": "v1.0.2",
        "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "source_head_sha": "a" * 40,
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


def _promotion_config_sha256() -> str:
    data = json.loads(Path("configs/platform_parity_promotion.json").read_text(encoding="utf-8"))
    return _json_sha256(data)


def _xp_native_evidence_contract_sha256() -> str:
    data = json.loads(Path("configs/xp_native_evidence_contract.json").read_text(encoding="utf-8"))
    return _json_sha256(data)


def _json_sha256(data: dict[str, object]) -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _load_platform_verified_evidence_checker():
    path = Path("scripts/check_platform_verified_evidence.py")
    spec = importlib.util.spec_from_file_location("check_platform_verified_evidence", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

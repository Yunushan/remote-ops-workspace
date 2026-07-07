from __future__ import annotations

import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

POLICY = (
    "Only accepted evidence records in this file can promote Linux i386, Linux armhf, "
    "or Windows XP native-host readiness. Accepted records must include release asset URLs, "
    "review-bundle manifest release asset URL binding, review bundle release asset URLs, "
    "release-importable artifact source binding, "
    "source artifact repository-id binding from exact source-run metadata, "
    "source artifact run-created timestamp binding from exact source-run metadata, "
    "source artifact run-start timestamp binding from exact source-run metadata, "
    "source artifact run-window timestamp binding from exact source-run metadata, "
    "source artifact retention expiration binding from exact source artifact metadata, "
    "release source head SHA binding, "
    "release source run-attempt binding, "
    "same release source workflow run URL cannot carry conflicting run attempts, "
    "release source workflow file binding, "
    "local protected-goal evidence preflight command binding, "
    "source artifact staged upload command binding, "
    "staged upload source/evidence/output root separation, "
    "finalized accepted-record source file binding, "
    "finalized accepted-record release asset URL binding, "
    "canonical finalized accepted-record JSON byte binding, "
    "published native and review-bundle release asset byte binding, "
    "published release asset GitHub id/API URL binding, "
    "Linux release source artifact names must be target/release-scoped, "
    "Linux accepted evidence command paths must be target/release-scoped, "
    "XP release source artifact names must be target/release-scoped, "
    "XP accepted evidence command paths must be target/release-scoped, "
    "and per-artifact SHA-256 digests, safe relative non-link native archive entries, "
    "exact safe checksum and native manifest file references, "
    "target architecture/format manifest binding, "
    "exact safe release asset URL filenames, "
    "exact required check lists, exact workflow dispatch input sets, "
    "workflow dispatch release repository binding, exact evidence source record fields, "
    "exact release source and review bundle fields, "
    "Linux builder identity evidence, builder identity "
    "SHA-256, builder identity release/run binding, "
    "Linux builder workflow provenance binding, "
    "exact Linux builder identity fields, "
    "Linux builder/smoke source file binding, "
    "Linux builder/smoke host identity binding, Linux builder/smoke security evidence binding, "
    "Linux builder source head SHA binding, "
    "Linux builder observed Git HEAD binding, "
    "Linux builder clean checkout binding, "
    "Linux builder/smoke runtime OS identity binding, "
    "Linux builder host identity binding when applicable, "
    "Linux builder rpm and non-interactive sudo evidence, Linux security patch evidence, "
    "Linux security smoke proof-line binding, "
    "exact Linux smoke proof-line occurrence binding, "
    "case-insensitive Linux forbidden security proof-line rejection, "
    "Linux native smoke summary binding, "
    "Linux native build and smoke command provenance, "
    "Linux smoke evidence SHA-256, Linux smoke release/run/source head SHA binding, "
    "Linux smoke runtime architecture and userland binding, "
    "Linux smoke sanitized host identity and observed-at timestamp binding, "
    "Linux workflow dispatch inputs when applicable, XP workflow dispatch inputs when applicable, "
    "XP evidence source file binding, XP evidence release source binding, "
    "XP evidence bundle SHA-256 digests, "
    "XP evidence validation command binding, XP evidence contract SHA-256, "
    "XP evidence summary binding, exact XP evidence summary fields, XP host identity SHA-256 binding, "
    "XP sanitized target-scoped host identity binding, XP smoke host identity binding, "
    "XP smoke observed-at timestamp binding, XP smoke OS identity binding, "
    "XP smoke host probe proof-line binding, exact XP smoke proof-line occurrence binding, "
    "case-insensitive XP forbidden security proof-line rejection, "
    "XP security patch evidence, "
    "tracked scripts/xp_smoke_runner.cmd XP smoke command provenance, "
    "canonical XP smoke proof-file command binding, "
    "XP security smoke command provenance binding when applicable, "
    "canonical XP smoke evidence-file summary binding and "
    "XP security smoke proof-line binding when applicable, and review "
    "bundle manifest, review bundle archive, safe relative non-symlink review bundle archive entries, "
    "and review bundle SHA-256 sidecar digests "
    "before strict promotion, and release uploads must include those review bundle files with matching "
    "size, SHA-256 and checksum-sidecar coverage plus canonical finalized accepted-record JSON "
    "with matching size and SHA-256; each accepted record must include "
    "the promotion config SHA-256, have a unique target, include no unrecognized top-level fields, "
    "all release evidence for one record must "
    "use the same GitHub repository, protected platform goal records for one release must use "
    "one release source head SHA and target-specific release source workflow files plus positive release source run attempts, "
    "partial protected platform goal records must use one release_tag, GitHub repository, "
    "target-specific release source workflow file, release source head SHA "
    "and positive release source run attempt before promotion, and Windows XP x86/x64 pairs must use the same release_tag, "
    "GitHub repository, target-specific release source workflow file, release source head SHA "
    "and positive release source run attempts. "
    "Empty means no promotion."
)


def test_platform_verified_evidence_checker_passes_empty_registry() -> None:
    checker = _load_platform_verified_evidence_checker()

    assert checker.main() == 0


def test_platform_verified_evidence_uses_explicit_empty_registry() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(registry={})

    assert "configs/platform_verified_evidence.json schema_version must be 1" in errors


def test_platform_verified_evidence_uses_explicit_empty_promotion() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY,
            "accepted_evidence": [],
        },
        promotion={},
    )

    assert any("promotion config missing protected target entries" in error for error in errors)


def test_platform_verified_evidence_rejects_non_string_promotion_target_id() -> None:
    checker = _load_platform_verified_evidence_checker()
    promotion = checker.read_json(checker.PROMOTION_PATH)
    linux_i386 = next(
        item for item in promotion["protected_targets"] if item["id"] == "linux-i386"
    )
    linux_i386["id"] = True

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY,
            "accepted_evidence": [],
        },
        promotion=promotion,
    )

    assert "promotion protected target id must be a non-empty string, got True" in errors
    assert not any("promotion config missing protected target entries: ['True']" in error for error in errors)


def test_platform_verified_evidence_rejects_boolean_registry_schema_version() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": True,
            "policy": POLICY,
            "accepted_evidence": [],
        }
    )

    assert "configs/platform_verified_evidence.json schema_version must be 1" in errors


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


def test_platform_verified_evidence_rejects_missing_exact_xp_evidence_summary_fields_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("exact XP evidence summary fields, ", ""),
            "accepted_evidence": [],
        }
    )

    assert "platform verified evidence policy must require exact XP evidence summary fields" in errors


def test_platform_verified_evidence_rejects_missing_local_evidence_preflight_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("local protected-goal evidence preflight command binding, ", ""),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must require local protected-goal evidence preflight command binding"
    ) in errors


def test_platform_verified_evidence_rejects_missing_staged_upload_root_separation_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("staged upload source/evidence/output root separation, ", ""),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must require staged upload source/evidence/output root separation"
    ) in errors


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


def test_platform_verified_evidence_rejects_missing_xp_release_source_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("XP evidence release source binding, ", ""),
            "accepted_evidence": [],
        }
    )

    assert "platform verified evidence policy must require XP evidence release source binding" in errors


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


def test_platform_verified_evidence_rejects_missing_linux_smoke_runtime_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("Linux smoke runtime architecture and userland binding, ", ""),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must require Linux smoke runtime architecture and userland binding"
        in errors
    )


def test_platform_verified_evidence_rejects_missing_linux_smoke_identity_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace(
                "Linux smoke sanitized host identity and observed-at timestamp binding, ",
                "",
            ),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must require Linux smoke sanitized host identity and observed-at timestamp binding"
        in errors
    )


def test_platform_verified_evidence_rejects_missing_linux_builder_smoke_identity_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("Linux builder/smoke host identity binding, ", ""),
            "accepted_evidence": [],
        }
    )

    assert "platform verified evidence policy must require Linux builder/smoke host identity binding" in errors


def test_platform_verified_evidence_rejects_missing_linux_builder_smoke_security_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("Linux builder/smoke security evidence binding, ", ""),
            "accepted_evidence": [],
        }
    )

    assert "platform verified evidence policy must require Linux builder/smoke security evidence binding" in errors


def test_platform_verified_evidence_rejects_missing_linux_security_smoke_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("Linux security smoke proof-line binding, ", ""),
            "accepted_evidence": [],
        }
    )

    assert "platform verified evidence policy must require Linux security smoke proof-line binding" in errors


def test_platform_verified_evidence_rejects_missing_exact_linux_smoke_proof_line_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("exact Linux smoke proof-line occurrence binding, ", ""),
            "accepted_evidence": [],
        }
    )

    assert "platform verified evidence policy must require exact Linux smoke proof-line occurrence binding" in errors


def test_platform_verified_evidence_rejects_missing_linux_forbidden_security_case_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace(
                "case-insensitive Linux forbidden security proof-line rejection, ",
                "",
            ),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must require case-insensitive Linux forbidden security proof-line rejection"
    ) in errors


def test_platform_verified_evidence_rejects_missing_linux_smoke_summary_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("Linux native smoke summary binding, ", ""),
            "accepted_evidence": [],
        }
    )

    assert "platform verified evidence policy must require Linux native smoke summary binding" in errors


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
                "size, SHA-256 and checksum-sidecar coverage plus canonical finalized accepted-record JSON "
                "with matching size and SHA-256; ",
                "",
            ),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must require release upload review bundle size, "
        "SHA-256, and checksum-sidecar coverage"
    ) in errors


def test_platform_verified_evidence_rejects_missing_final_record_upload_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace(
                " plus canonical finalized accepted-record JSON with matching size and SHA-256",
                "",
            ),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must require release upload finalized accepted-record "
        "canonical JSON size and SHA-256 binding"
    ) in errors


def test_platform_verified_evidence_rejects_missing_review_bundle_archive_entry_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace(
                "safe relative non-symlink review bundle archive entries, ",
                "",
            ),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must require safe relative non-symlink review bundle archive entries"
    ) in errors


def test_platform_verified_evidence_rejects_missing_native_archive_entry_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace(
                "safe relative non-link native archive entries, ",
                "",
            ),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must require safe relative non-link native archive entries"
    ) in errors


def test_platform_verified_evidence_rejects_missing_exact_artifact_reference_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace(
                "exact safe checksum and native manifest file references, ",
                "",
            ),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must require exact safe checksum and native manifest file references"
    ) in errors


def test_platform_verified_evidence_rejects_missing_manifest_architecture_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace(
                "target architecture/format manifest binding, ",
                "",
            ),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must require target architecture/format manifest binding"
    ) in errors


def test_platform_verified_evidence_rejects_missing_exact_release_url_filename_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace(
                "exact safe release asset URL filenames, ",
                "",
            ),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must require exact safe release asset URL filenames"
    ) in errors


def test_platform_verified_evidence_rejects_missing_exact_check_list_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("exact required check lists, ", ""),
            "accepted_evidence": [],
        }
    )

    assert "platform verified evidence policy must require exact accepted evidence check lists" in errors


def test_platform_verified_evidence_rejects_missing_exact_workflow_input_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("exact workflow dispatch input sets, ", ""),
            "accepted_evidence": [],
        }
    )

    assert "platform verified evidence policy must require exact workflow dispatch input sets" in errors


def test_platform_verified_evidence_rejects_missing_workflow_repository_binding_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("workflow dispatch release repository binding, ", ""),
            "accepted_evidence": [],
        }
    )

    assert "platform verified evidence policy must require workflow dispatch release repository binding" in errors


def test_platform_verified_evidence_rejects_missing_exact_evidence_source_record_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("exact evidence source record fields, ", ""),
            "accepted_evidence": [],
        }
    )

    assert "platform verified evidence policy must require exact evidence source record fields" in errors


def test_platform_verified_evidence_rejects_missing_exact_release_source_review_bundle_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("exact release source and review bundle fields, ", ""),
            "accepted_evidence": [],
        }
    )

    assert "platform verified evidence policy must require exact release source and review bundle fields" in errors


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


def test_platform_verified_evidence_rejects_missing_source_artifact_repository_id_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace(
                "source artifact repository-id binding from exact source-run metadata, ",
                "",
            ),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must require source artifact repository-id binding"
    ) in errors


def test_platform_verified_evidence_rejects_missing_source_artifact_run_created_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace(
                "source artifact run-created timestamp binding from exact source-run metadata, ",
                "",
            ),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must require source artifact run-created timestamp binding"
    ) in errors


def test_platform_verified_evidence_rejects_missing_source_artifact_run_start_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace(
                "source artifact run-start timestamp binding from exact source-run metadata, ",
                "",
            ),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must require source artifact run-start timestamp binding"
    ) in errors


def test_platform_verified_evidence_rejects_missing_source_artifact_run_window_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace(
                "source artifact run-window timestamp binding from exact source-run metadata, ",
                "",
            ),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must require source artifact run-window timestamp binding"
    ) in errors


def test_platform_verified_evidence_rejects_missing_source_artifact_retention_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace(
                "source artifact retention expiration binding from exact source artifact metadata, ",
                "",
            ),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must require source artifact retention expiration binding"
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


def test_platform_verified_evidence_rejects_missing_xp_path_scope_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace(
                "XP accepted evidence command paths must be target/release-scoped, ",
                "",
            ),
            "accepted_evidence": [],
        }
    )

    assert "platform verified evidence policy must require target/release-scoped XP accepted evidence paths" in errors


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


def test_platform_verified_evidence_rejects_missing_xp_security_smoke_command_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("XP security smoke command provenance binding when applicable, ", ""),
            "accepted_evidence": [],
        }
    )

    assert "platform verified evidence policy must require XP security smoke command provenance binding" in errors


def test_platform_verified_evidence_rejects_missing_xp_smoke_host_identity_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("XP smoke host identity binding, ", ""),
            "accepted_evidence": [],
        }
    )

    assert "platform verified evidence policy must require XP smoke host identity binding" in errors


def test_platform_verified_evidence_rejects_missing_xp_sanitized_identity_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("XP sanitized target-scoped host identity binding, ", ""),
            "accepted_evidence": [],
        }
    )

    assert "platform verified evidence policy must require XP sanitized target-scoped host identity binding" in errors


def test_platform_verified_evidence_rejects_missing_xp_smoke_observed_at_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("XP smoke observed-at timestamp binding, ", ""),
            "accepted_evidence": [],
        }
    )

    assert "platform verified evidence policy must require XP smoke observed-at timestamp binding" in errors


def test_platform_verified_evidence_rejects_missing_xp_smoke_os_identity_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("XP smoke OS identity binding, ", ""),
            "accepted_evidence": [],
        }
    )

    assert "platform verified evidence policy must require XP smoke OS identity binding" in errors


def test_platform_verified_evidence_rejects_missing_xp_smoke_host_probe_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("XP smoke host probe proof-line binding, ", ""),
            "accepted_evidence": [],
        }
    )

    assert "platform verified evidence policy must require XP smoke host probe proof-line binding" in errors


def test_platform_verified_evidence_rejects_missing_exact_xp_smoke_proof_line_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("exact XP smoke proof-line occurrence binding, ", ""),
            "accepted_evidence": [],
        }
    )

    assert "platform verified evidence policy must require exact XP smoke proof-line occurrence binding" in errors


def test_platform_verified_evidence_rejects_missing_xp_forbidden_security_case_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("case-insensitive XP forbidden security proof-line rejection, ", ""),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must require "
        "case-insensitive XP forbidden security proof-line rejection"
    ) in errors


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


def test_platform_verified_evidence_rejects_missing_linux_path_scope_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace(
                "Linux accepted evidence command paths must be target/release-scoped, ",
                "",
            ),
            "accepted_evidence": [],
        }
    )

    assert "platform verified evidence policy must require target/release-scoped Linux accepted evidence paths" in errors


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


def test_platform_verified_evidence_rejects_missing_release_source_run_attempt_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("release source run-attempt binding, ", ""),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must require release source run-attempt binding"
    ) in errors


def test_platform_verified_evidence_rejects_missing_conflicting_source_attempt_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace(
                "same release source workflow run URL cannot carry conflicting run attempts, ",
                "",
            ),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must forbid conflicting run attempts "
        "for one release source workflow run URL"
    ) in errors


def test_platform_verified_evidence_rejects_missing_protected_goal_source_head_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace(
                "protected platform goal records for one release must use "
                "one release source head SHA and target-specific release source workflow files "
                "plus positive release source run attempts, ",
                "",
            ),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must require protected platform goal source workflow, "
        "source head SHA and run-attempt binding"
    ) in errors


def test_platform_verified_evidence_rejects_protected_goal_policy_without_workflow_files() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace(
                " and target-specific release source workflow files plus",
                " and",
            ),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must require protected platform goal source workflow, "
        "source head SHA and run-attempt binding"
    ) in errors


def test_platform_verified_evidence_rejects_missing_partial_goal_run_attempt_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace(
                "partial protected platform goal records must use one release_tag, GitHub repository, "
                "target-specific release source workflow file, release source head SHA "
                "and positive release source run attempt before promotion, ",
                "",
            ),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must require partial protected platform goal release scope, "
        "workflow and run-attempt binding"
    ) in errors


def test_platform_verified_evidence_rejects_partial_goal_policy_without_workflow_file() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace(
                "target-specific release source workflow file, ",
                "",
            ),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must require partial protected platform goal release scope, "
        "workflow and run-attempt binding"
    ) in errors
    assert (
        "platform verified evidence policy must require Windows XP pair source workflow, "
        "source head SHA and run-attempt binding"
    ) in errors


def test_platform_verified_evidence_rejects_missing_xp_pair_source_head_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace(
                "Windows XP x86/x64 pairs must use the same release_tag, "
                "GitHub repository, target-specific release source workflow file, release source head SHA "
                "and positive release source run attempts. ",
                "Windows XP x86/x64 pairs must use the same release_tag and GitHub repository. ",
            ),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must require Windows XP pair source workflow, "
        "source head SHA and run-attempt binding"
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


def test_platform_verified_evidence_rejects_missing_final_record_release_url_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("finalized accepted-record release asset URL binding, ", ""),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must require finalized accepted-record release asset URL binding"
    ) in errors


def test_platform_verified_evidence_rejects_missing_canonical_final_record_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("canonical finalized accepted-record JSON byte binding, ", ""),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must require canonical finalized accepted-record JSON byte binding"
    ) in errors


def test_platform_verified_evidence_rejects_missing_published_release_asset_byte_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("published native and review-bundle release asset byte binding, ", ""),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must require published native and review-bundle release asset byte binding"
    ) in errors


def test_platform_verified_evidence_rejects_missing_published_release_asset_identity_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("published release asset GitHub id/API URL binding, ", ""),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must require published release asset GitHub id/API URL binding"
    ) in errors


def test_platform_verified_evidence_rejects_missing_exact_top_level_field_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("include no unrecognized top-level fields, ", ""),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must reject unrecognized top-level fields"
    ) in errors


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


def test_platform_verified_evidence_rejects_missing_linux_builder_workflow_provenance_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("Linux builder workflow provenance binding, ", ""),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must require Linux builder workflow provenance binding"
    ) in errors


def test_platform_verified_evidence_rejects_missing_linux_builder_identity_fields_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("exact Linux builder identity fields, ", ""),
            "accepted_evidence": [],
        }
    )

    assert "platform verified evidence policy must require exact Linux builder identity fields" in errors


def test_platform_verified_evidence_rejects_missing_linux_builder_observed_git_head_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("Linux builder observed Git HEAD binding, ", ""),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must require Linux builder observed Git HEAD binding"
    ) in errors


def test_platform_verified_evidence_rejects_missing_linux_builder_clean_checkout_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("Linux builder clean checkout binding, ", ""),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must require Linux builder clean checkout binding"
    ) in errors


def test_platform_verified_evidence_rejects_missing_linux_runtime_identity_policy() -> None:
    checker = _load_platform_verified_evidence_checker()

    errors = checker.check_platform_verified_evidence(
        registry={
            "schema_version": 1,
            "policy": POLICY.replace("Linux builder/smoke runtime OS identity binding, ", ""),
            "accepted_evidence": [],
        }
    )

    assert (
        "platform verified evidence policy must require Linux builder/smoke runtime OS identity binding"
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
    del record["finalized_record_release_asset_url"]
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
        assert checker.main(["--allow-unfinalized-candidates"]) == 2
    finally:
        checker.EVIDENCE_PATH = original_path


def test_platform_verified_evidence_read_json_rejects_reserved_workspace_root() -> None:
    checker = _load_platform_verified_evidence_checker()
    registry = Path(".github") / "platform_verified_evidence.json"

    with pytest.raises(ValueError) as exc_info:
        checker.read_json(registry)

    assert str(exc_info.value) == (
        "JSON evidence source must not point inside reserved workspace directory "
        f"'.github': {registry}"
    )


def test_platform_verified_evidence_cli_reports_unsafe_registry_path(capsys) -> None:
    checker = _load_platform_verified_evidence_checker()
    original_path = checker.EVIDENCE_PATH
    registry = Path(".github") / "platform_verified_evidence.json"
    checker.EVIDENCE_PATH = registry
    try:
        result = checker.main()
    finally:
        checker.EVIDENCE_PATH = original_path

    assert result == 1
    assert (
        "platform verified evidence: JSON evidence source must not point inside "
        f"reserved workspace directory '.github': {registry}"
    ) in capsys.readouterr().err


def test_platform_verified_evidence_read_json_rejects_symlinked_file(tmp_path: Path) -> None:
    checker = _load_platform_verified_evidence_checker()
    registry = tmp_path / "platform_verified_evidence.json"
    registry.write_text("{}\n", encoding="utf-8")
    linked_registry = tmp_path / "linked-registry.json"
    try:
        linked_registry.symlink_to(registry)
    except OSError as exc:
        pytest.skip(f"file symlinks unavailable on this platform: {exc}")

    with pytest.raises(ValueError) as exc_info:
        checker.read_json(linked_registry)

    assert str(exc_info.value) == f"JSON evidence source must not be a symlink: {linked_registry}"


def test_platform_verified_evidence_read_json_rejects_symlinked_parent(tmp_path: Path) -> None:
    checker = _load_platform_verified_evidence_checker()
    registry_dir = tmp_path / "registry-dir"
    registry_dir.mkdir()
    registry = registry_dir / "platform_verified_evidence.json"
    registry.write_text("{}\n", encoding="utf-8")
    linked_dir = tmp_path / "linked-registry-dir"
    try:
        linked_dir.symlink_to(registry_dir, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlinks unavailable on this platform: {exc}")

    with pytest.raises(ValueError) as exc_info:
        checker.read_json(linked_dir / "platform_verified_evidence.json")

    assert str(exc_info.value) == (
        f"JSON evidence source path must not contain symlinked directories: {linked_dir}"
    )


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


def test_platform_verified_evidence_rejects_malformed_required_targets_without_stringifying() -> None:
    checker = _load_platform_verified_evidence_checker()
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [_linux_record("linux-i386")],
    }

    errors = checker.check_platform_verified_evidence(
        registry=registry,
        required_targets=(True, "linux-i386"),
    )

    assert errors == [
        "required platform evidence target must be a non-empty string, got True"
    ]
    assert not any("['True']" in error for error in errors)


def test_platform_verified_evidence_arg_targets_do_not_stringify_malformed_values() -> None:
    checker = _load_platform_verified_evidence_checker()
    args = checker.parse_args(["--require-target", "linux-i386"])
    args.require_target = [True, "linux-i386"]

    errors = checker.strict_platform_goal_arg_errors(args)
    required_targets = checker.required_targets_from_args(args)

    assert errors == ["platform verified evidence required target must be a non-empty string, got True"]
    assert required_targets == ("linux-i386",)
    assert "True" not in required_targets


def test_platform_verified_evidence_rejects_malformed_required_release_tag_without_crashing() -> None:
    checker = _load_platform_verified_evidence_checker()
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [_linux_record("linux-i386")],
    }

    errors = checker.check_platform_verified_evidence(
        registry=registry,
        required_targets=("linux-i386",),
        required_release_tag=True,
    )

    assert errors == ["required_release_tag must be a string, got True"]


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


def test_platform_verified_evidence_goal_required_targets_ignore_non_100_readiness() -> None:
    checker = _load_platform_verified_evidence_checker()
    linux_i386 = _linux_record("linux-i386")
    linux_i386["readiness_percent"] = 99.0
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [
            linux_i386,
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

    assert "linux-i386 evidence readiness_percent must be 100.0" in errors
    assert (
        "missing required accepted evidence targets for release_tag v1.0.2: "
        "['linux-i386']"
    ) in errors


def test_platform_verified_evidence_goal_required_targets_ignore_invalid_records() -> None:
    checker = _load_platform_verified_evidence_checker()
    linux_i386 = _linux_record("linux-i386")
    del linux_i386["review_bundle"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [
            linux_i386,
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

    assert "linux-i386 review_bundle must be an object" in errors
    assert (
        "missing required accepted evidence targets for release_tag v1.0.2: "
        "['linux-i386']"
    ) in errors


def test_platform_verified_evidence_rejects_linux_unexpected_top_level_fields() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["_source_files"] = ["native-dist/linux/private-builder-output.log"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(
        registry=registry,
        require_review_bundles=True,
    )

    assert "linux-i386 accepted evidence has unexpected top-level fields: ['_source_files']" in errors


def test_platform_verified_evidence_rejects_xp_unexpected_top_level_fields() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["operator_notes"] = "local lab scratch notes must stay out of accepted evidence"
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(
        registry=registry,
        require_review_bundles=True,
    )

    assert (
        "windows-xp-native-x86 accepted evidence has unexpected top-level fields: "
        "['operator_notes']"
    ) in errors


def test_platform_verified_evidence_rejects_ambiguous_top_level_keys() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["TARGET"] = record["target"]
    record[True] = "manual scratch"
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(
        registry=registry,
        require_review_bundles=True,
    )

    assert "linux-i386 accepted evidence top-level keys must be strings, got True" in errors
    assert (
        "linux-i386 accepted evidence top-level keys must not collide on "
        "case-insensitive filesystems: ['TARGET', 'target']"
    ) in errors


def test_platform_verified_evidence_rejects_non_string_target() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["target"] = True
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "accepted_evidence target must be a string, got True" in errors


def test_platform_verified_evidence_non_string_target_cannot_satisfy_required_target() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["target"] = True
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(
        registry=registry,
        required_targets=("linux-i386",),
    )

    assert "accepted_evidence target must be a string, got True" in errors
    assert "missing required accepted evidence targets: ['linux-i386']" in errors


def test_platform_verified_evidence_rejects_boolean_linux_identity_schema_versions() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["builder_identity"]["schema_version"] = True
    record["builder_identity"]["host_identity"]["schema_version"] = True
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 builder_identity schema_version must be 1" in errors
    assert "linux-i386 builder_identity host_identity.schema_version must be 1" in errors


def test_platform_verified_evidence_rejects_boolean_xp_host_identity_schema_version() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["xp_evidence_summary"]["host_identity"]["schema_version"] = True
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "windows-xp-native-x86 xp_evidence_summary host_identity.schema_version must be 1" in errors


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
        "windows-xp-native-x64 release_asset_source.workflow_run_url repository must match "
        "release asset repository ['other/remote-ops-workspace'], got example/remote-ops-workspace"
    ) in errors
    assert (
        "missing required accepted evidence targets for release_tag v1.0.2: "
        "['windows-xp-native-x64']"
    ) in errors


def test_platform_verified_evidence_goal_required_targets_reject_mixed_release_source_heads() -> None:
    checker = _load_platform_verified_evidence_checker()
    linux_i386 = _linux_record("linux-i386")
    linux_armhf = _linux_record("linux-armhf")
    _replace_release_source_head(linux_i386, "b" * 40)
    _replace_release_source_head(linux_armhf, "b" * 40)
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [
            linux_i386,
            linux_armhf,
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

    assert (
        "protected platform goal evidence for release_tag v1.0.2 must use one release source head SHA, "
        f"got {{'linux-armhf': '{'b' * 40}', "
        f"'linux-i386': '{'b' * 40}', "
        f"'windows-xp-native-x64': '{'a' * 40}', "
        f"'windows-xp-native-x86': '{'a' * 40}'}}"
    ) in errors


def test_platform_verified_evidence_goal_required_targets_reject_conflicting_source_run_attempts() -> None:
    checker = _load_platform_verified_evidence_checker()
    xp_x86 = _xp_record("windows-xp-native-x86")
    _replace_release_source_run_attempt(xp_x86, 2)
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [
            _linux_record("linux-i386"),
            _linux_record("linux-armhf"),
            xp_x86,
            _xp_record("windows-xp-native-x64"),
        ],
    }

    errors = checker.check_platform_verified_evidence(
        registry=registry,
        required_targets=checker.PROTECTED_GOAL_TARGETS,
        required_release_tag="v1.0.2",
        require_review_bundles=True,
    )

    assert not any("missing required accepted evidence targets" in error for error in errors)
    assert (
        "protected platform goal evidence for release_tag v1.0.2 must not reuse one "
        "release source workflow run URL with conflicting run attempts, got "
        "https://github.com/example/remote-ops-workspace/actions/runs/12345: "
        "{'linux-armhf': 1, 'linux-i386': 1, "
        "'windows-xp-native-x64': 1, 'windows-xp-native-x86': 2}"
    ) in errors


def test_platform_verified_evidence_rejects_partial_protected_goal_mixed_release_tags() -> None:
    checker = _load_platform_verified_evidence_checker()
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [
            _linux_record("linux-i386"),
            _xp_record("windows-xp-native-x86", release_tag="v1.0.3"),
        ],
    }

    errors = checker.check_platform_verified_evidence(
        registry=registry,
        require_review_bundles=True,
    )

    assert (
        "partial protected platform goal evidence must use one release_tag before promotion, "
        "got {'linux-i386': 'v1.0.2', 'windows-xp-native-x86': 'v1.0.3'}"
    ) in errors


def test_platform_verified_evidence_partial_goal_does_not_stringify_malformed_release_tag() -> None:
    checker = _load_platform_verified_evidence_checker()
    linux_i386 = _linux_record("linux-i386")
    linux_i386["release_tag"] = True
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [
            linux_i386,
            _xp_record("windows-xp-native-x86"),
        ],
    }

    errors = checker.check_platform_verified_evidence(
        registry=registry,
        require_review_bundles=True,
    )

    assert "linux-i386 release_tag must be a string" in errors
    assert not any(
        "partial protected platform goal evidence must use one release_tag" in error
        and "True" in error
        for error in errors
    )


def test_platform_verified_evidence_rejects_partial_protected_goal_mixed_repositories() -> None:
    checker = _load_platform_verified_evidence_checker()
    xp_x86 = _xp_record("windows-xp-native-x86")
    _replace_release_repository(xp_x86, "other/remote-ops-workspace")
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [
            _linux_record("linux-i386"),
            xp_x86,
        ],
    }

    errors = checker.check_platform_verified_evidence(
        registry=registry,
        require_review_bundles=True,
    )

    assert (
        "partial protected platform goal evidence must use one GitHub release repository before promotion, "
        "got {'linux-i386': ['example/remote-ops-workspace'], "
        "'windows-xp-native-x86': ['other/remote-ops-workspace']}"
    ) in errors


def test_release_asset_repositories_ignores_unsafe_release_asset_urls() -> None:
    checker = _load_platform_verified_evidence_checker()

    repositories = checker.release_asset_repositories(
        [
            "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/"
            "remote-ops-workspace-v1.0.2-linux-i386.deb",
            "https://github.com/other/remote-ops-workspace/releases/download/v1.0.2/nested/"
            "remote-ops-workspace-v1.0.2-linux-i386.deb",
            "https://github.com/third/remote-ops-workspace/releases/download/v1.0.2/"
            "remote-ops-workspace-v1.0.2-linux-i386.deb?download=1",
            "not-a-release-url",
        ]
    )

    assert repositories == {"example/remote-ops-workspace"}


def test_platform_verified_evidence_rejects_partial_goal_without_safe_release_repository() -> None:
    checker = _load_platform_verified_evidence_checker()
    xp_x86 = _xp_record("windows-xp-native-x86")
    xp_x86["release_asset_urls"] = [
        str(url).replace("/releases/download/v1.0.2/", "/releases/download/v1.0.2/nested/")
        for url in xp_x86["release_asset_urls"]
    ]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [
            _linux_record("linux-i386"),
            xp_x86,
        ],
    }

    errors = checker.check_platform_verified_evidence(
        registry=registry,
        require_review_bundles=True,
    )

    assert (
        "partial protected platform goal evidence must derive exactly one safe "
        "GitHub release repository before promotion, got {'windows-xp-native-x86': []}"
    ) in errors


def test_platform_verified_evidence_rejects_partial_protected_goal_mixed_source_heads() -> None:
    checker = _load_platform_verified_evidence_checker()
    linux_i386 = _linux_record("linux-i386")
    _replace_release_source_head(linux_i386, "b" * 40)
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [
            linux_i386,
            _xp_record("windows-xp-native-x86"),
        ],
    }

    errors = checker.check_platform_verified_evidence(
        registry=registry,
        require_review_bundles=True,
    )

    assert (
        "partial protected platform goal evidence must use one release source head SHA before promotion, "
        f"got {{'linux-i386': '{'b' * 40}', 'windows-xp-native-x86': '{'a' * 40}'}}"
    ) in errors


def test_platform_verified_evidence_rejects_conflicting_attempts_for_one_source_run_url() -> None:
    checker = _load_platform_verified_evidence_checker()
    xp_x86 = _xp_record("windows-xp-native-x86")
    source = xp_x86["release_asset_source"]
    assert isinstance(source, dict)
    source["run_attempt"] = 2
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [
            _linux_record("linux-i386"),
            xp_x86,
        ],
    }

    errors = checker.check_platform_verified_evidence(
        registry=registry,
        require_review_bundles=True,
    )

    assert (
        "partial protected platform goal evidence must not reuse one release source workflow run URL "
        "with conflicting run attempts before promotion, got "
        "https://github.com/example/remote-ops-workspace/actions/runs/12345: "
        "{'linux-i386': 1, 'windows-xp-native-x86': 2}"
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


def test_platform_verified_evidence_xp_pair_does_not_stringify_malformed_release_tag() -> None:
    checker = _load_platform_verified_evidence_checker()
    xp_x86 = _xp_record("windows-xp-native-x86")
    xp_x86["release_tag"] = True
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [
            xp_x86,
            _xp_record("windows-xp-native-x64"),
        ],
    }

    errors = checker.check_platform_verified_evidence(
        registry=registry,
        require_review_bundles=True,
    )

    assert "windows-xp-native-x86 release_tag must be a string" in errors
    assert not any(
        "Windows XP native evidence pair must use one release_tag" in error
        and "True" in error
        for error in errors
    )


def test_platform_verified_evidence_rejects_xp_pair_without_safe_release_repository() -> None:
    checker = _load_platform_verified_evidence_checker()
    xp_x64 = _xp_record("windows-xp-native-x64")
    xp_x64["release_asset_urls"] = [
        str(url).replace("/releases/download/v1.0.2/", "/releases/download/v1.0.2/nested/")
        for url in xp_x64["release_asset_urls"]
    ]
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
        "Windows XP native evidence pair must derive exactly one safe "
        "GitHub release repository, got {'windows-xp-native-x64': []}"
    ) in errors


def test_platform_verified_evidence_rejects_xp_pair_mixed_release_source_heads() -> None:
    checker = _load_platform_verified_evidence_checker()
    xp_x64 = _xp_record("windows-xp-native-x64")
    _replace_release_source_head(xp_x64, "b" * 40)
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
        "Windows XP native evidence pair must use one release source head SHA, "
        f"got {{'windows-xp-native-x64': '{'b' * 40}', "
        f"'windows-xp-native-x86': '{'a' * 40}'}}"
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


def test_platform_verified_evidence_goal_cli_requires_release_tag() -> None:
    checker = _load_platform_verified_evidence_checker()

    assert checker.main(["--require-goal-targets"]) == 2


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


def test_platform_verified_evidence_rejects_review_bundle_unexpected_fields() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["review_bundle"]["notes"] = "manual approval"
    record["review_bundle"]["manifest"]["path"] = (
        "review/extended-linux-evidence-bundle-linux-i386-v1.0.2.json"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry, require_review_bundles=True)

    assert "linux-i386 review_bundle unexpected fields: ['notes']" in errors
    assert "linux-i386 review_bundle manifest unexpected fields: ['path']" in errors


def test_platform_verified_evidence_rejects_non_string_review_bundle_metadata() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["review_bundle"]["manifest"]["file"] = True
    record["review_bundle"]["archive"]["sha256"] = True
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(
        registry=registry,
        require_review_bundles=True,
    )

    assert "linux-i386 review_bundle manifest.file must be a string, got True" in errors
    assert (
        "linux-i386 review_bundle archive.sha256 must be a string SHA-256 hex digest, "
        "got True"
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


def test_platform_verified_evidence_rejects_review_bundle_release_asset_url_query_string() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["review_bundle"]["release_asset_urls"][0] = (
        f"{record['review_bundle']['release_asset_urls'][0]}?download=1"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry, require_review_bundles=True)

    assert any(
        "linux-i386 review_bundle release asset URL file name must be an exact safe file name" in error
        for error in errors
    )


def test_platform_verified_evidence_rejects_review_bundle_release_asset_url_path_segment() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["review_bundle"]["release_asset_urls"][0] = record["review_bundle"]["release_asset_urls"][0].replace(
        "/releases/download/v1.0.2/",
        "/releases/download/v1.0.2/nested/",
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry, require_review_bundles=True)

    assert any(
        "linux-i386 review_bundle release asset URL file name must be an exact safe file name" in error
        for error in errors
    )


def test_platform_verified_evidence_rejects_case_colliding_review_bundle_release_asset_url() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x64")
    first_url = record["review_bundle"]["release_asset_urls"][0]
    prefix, filename = first_url.rsplit("/", 1)
    record["review_bundle"]["release_asset_urls"].append(f"{prefix}/{filename.upper()}")
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry, require_review_bundles=True)

    assert any(
        "windows-xp-native-x64 review_bundle release asset URL file names must not collide on "
        "case-insensitive filesystems" in error
        and filename in error
        and filename.upper() in error
        for error in errors
    )


def test_platform_verified_evidence_rejects_non_string_review_bundle_release_asset_url_entries() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x64")
    record["review_bundle"]["release_asset_urls"][0] = True
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry, require_review_bundles=True)

    assert (
        "windows-xp-native-x64 review_bundle release asset URL entries must be strings, got True"
    ) in errors


def test_platform_verified_evidence_rejects_missing_finalized_record_release_asset_url() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    del record["finalized_record_release_asset_url"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry, require_review_bundles=True)

    assert "linux-i386 finalized_record_release_asset_url must be set" in errors


def test_platform_verified_evidence_rejects_non_string_finalized_record_release_asset_url() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["finalized_record_release_asset_url"] = True
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry, require_review_bundles=True)

    assert (
        "linux-i386 finalized_record_release_asset_url must be a string GitHub release asset URL, got True"
    ) in errors


def test_platform_verified_evidence_rejects_finalized_record_release_asset_url_file_drift() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x64")
    record["finalized_record_release_asset_url"] = str(
        record["finalized_record_release_asset_url"]
    ).replace("platform-verified-evidence-windows-xp-native-x64-final.json", "wrong.json")
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry, require_review_bundles=True)

    assert (
        "windows-xp-native-x64 finalized_record_release_asset_url file must be "
        "platform-verified-evidence-windows-xp-native-x64-final.json"
    ) in errors


def test_platform_verified_evidence_rejects_finalized_record_release_asset_url_query_string() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x64")
    record["finalized_record_release_asset_url"] = f"{record['finalized_record_release_asset_url']}?download=1"
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry, require_review_bundles=True)

    assert (
        "windows-xp-native-x64 finalized_record_release_asset_url file name must be an exact safe file name"
    ) in errors


def test_platform_verified_evidence_rejects_finalized_record_release_asset_url_path_segment() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x64")
    record["finalized_record_release_asset_url"] = str(record["finalized_record_release_asset_url"]).replace(
        "/releases/download/v1.0.2/",
        "/releases/download/v1.0.2/nested/",
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry, require_review_bundles=True)

    assert (
        "windows-xp-native-x64 finalized_record_release_asset_url file name must be an exact safe file name"
    ) in errors


def test_platform_verified_evidence_binds_source_run_to_full_release_package_repository() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["release_asset_urls"] = []
    record["finalized_record_release_asset_url"] = str(
        record["finalized_record_release_asset_url"]
    ).replace("github.com/example/remote-ops-workspace", "github.com/other/remote-ops-workspace")
    review_bundle = record["review_bundle"]
    assert isinstance(review_bundle, dict)
    review_bundle["release_asset_urls"] = [
        str(url).replace("github.com/example/remote-ops-workspace", "github.com/other/remote-ops-workspace")
        for url in review_bundle["release_asset_urls"]
    ]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry, require_review_bundles=True)

    assert (
        "linux-i386 release_asset_source.workflow_run_url repository must match release asset repository "
        "['other/remote-ops-workspace'], got example/remote-ops-workspace"
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


def test_platform_verified_evidence_rejects_non_string_release_tag_and_promotion_hash() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["release_tag"] = True
    record["promotion_config_sha256"] = True
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 release_tag must be a string" in errors
    assert "linux-i386 promotion_config_sha256 must be a string SHA-256 hex digest" in errors


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


def test_platform_verified_evidence_rejects_unsafe_artifact_sha256_keys() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-armhf")
    record["artifact_sha256"]["nested/file.bin"] = "a" * 64
    record["artifact_sha256"][True] = "b" * 64
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-armhf artifact_sha256 keys must be exact safe file names, got 'nested/file.bin'" in errors
    assert "linux-armhf artifact_sha256 keys must be exact safe file names, got True" in errors


def test_platform_verified_evidence_rejects_non_string_artifact_sha256_values() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-armhf")
    artifact_name = next(iter(record["artifact_sha256"]))
    record["artifact_sha256"][artifact_name] = True
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        f"linux-armhf artifact_sha256 for {artifact_name} must be a string SHA-256 hex digest"
        in errors
    )


def test_platform_verified_evidence_rejects_non_string_linux_smoke_artifact_binding_values() -> None:
    checker = _load_platform_verified_evidence_checker()
    target = "linux-i386"
    release_tag = "v1.0.2"
    artifact_hashes = {
        name: "1" * 64
        for name in checker.linux_smoke_artifact_names(target, release_tag)
    }
    artifact_name = sorted(artifact_hashes)[0]
    artifact_hashes[artifact_name] = True
    smoke_text = "\n".join(
        f"native installer smoke artifact sha256: {name} {digest}"
        for name, digest in sorted(artifact_hashes.items())
        if isinstance(digest, str)
    )

    errors = checker.check_linux_smoke_artifact_sha256_lines(
        target,
        release_tag,
        smoke_text,
        artifact_hashes,
        label="linux_smoke_evidence",
    )

    assert (
        f"{target} linux_smoke_evidence artifact_sha256 for smoke-tested artifact "
        f"{artifact_name} must be a string SHA-256 hex digest"
    ) in errors
    assert not any("True" in error for error in errors)


def test_platform_verified_evidence_rejects_case_colliding_artifact_sha256_keys() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    first_file = next(iter(record["artifact_sha256"]))
    record["artifact_sha256"][first_file.upper()] = "c" * 64
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert any(
        "linux-i386 artifact_sha256 keys must not collide on case-insensitive filesystems" in error
        and first_file in error
        and first_file.upper() in error
        for error in errors
    )


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


def test_platform_verified_evidence_rejects_release_asset_url_query_string() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["release_asset_urls"][0] = f"{record['release_asset_urls'][0]}?download=1"
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert any(
        "linux-i386 release asset URL file name must be an exact safe file name" in error
        for error in errors
    )


def test_platform_verified_evidence_rejects_non_string_release_asset_url_entries() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["release_asset_urls"][0] = True
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 release asset URL entries must be strings, got True" in errors


def test_platform_verified_evidence_rejects_malformed_release_asset_repository_slug() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["release_asset_urls"][0] = record["release_asset_urls"][0].replace(
        "github.com/example/remote-ops-workspace/releases/",
        "github.com/example/remote-ops-workspace?download=1/releases/",
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert any("linux-i386 release asset URL is not a GitHub release asset URL" in error for error in errors)


def test_platform_verified_evidence_rejects_release_asset_url_path_segment() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["release_asset_urls"][0] = record["release_asset_urls"][0].replace(
        "/releases/download/v1.0.2/",
        "/releases/download/v1.0.2/nested/",
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert any(
        "linux-i386 release asset URL file name must be an exact safe file name" in error
        for error in errors
    )


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


def test_platform_verified_evidence_rejects_case_colliding_release_asset_url() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    first_url = record["release_asset_urls"][0]
    prefix, filename = first_url.rsplit("/", 1)
    record["release_asset_urls"].append(f"{prefix}/{filename.upper()}")
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert any(
        "linux-i386 release asset URL file names must not collide on case-insensitive filesystems" in error
        and filename in error
        and filename.upper() in error
        for error in errors
    )


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


def test_platform_verified_evidence_rejects_non_string_linux_workflow_run_url() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["workflow_run_url"] = True
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 workflow_run_url must be a string GitHub Actions run URL" in errors


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
        f"https://github.com/example/remote-ops-workspace/actions/runs/67890 "
        f"--workflow-run-attempt 1 --source-head-sha {'a' * 40} "
        "--builder-evidence evidence/linux-i386/v1.0.2/builder-identity-linux-i386.json'"
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


def test_platform_verified_evidence_rejects_missing_linux_runner_labels() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    del record["runner_labels"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 runner_labels must be a list" in errors


def test_platform_verified_evidence_rejects_ambiguous_linux_runner_labels() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["runner_labels"] = ["self-hosted", "linux", "LINUX", "linux", True]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 runner_labels entries must be strings, got True" in errors
    assert (
        "linux-i386 runner_labels must not collide on case-insensitive "
        "filesystems: ['LINUX', 'linux']"
    ) in errors
    assert "linux-i386 runner_labels must not contain duplicates: ['linux']" in errors
    assert "linux-i386 runner_labels must include ['i386', 'linux', 'self-hosted']" in errors


def test_platform_verified_evidence_rejects_missing_linux_workflow_input_keys() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-armhf")
    del record["workflow_inputs"]["release_asset_base_url"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-armhf workflow_inputs missing keys: ['release_asset_base_url']" in errors


def test_platform_verified_evidence_rejects_unexpected_linux_workflow_input_keys() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["workflow_inputs"]["allow_extra_artifacts"] = "true"
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 workflow_inputs unexpected keys: ['allow_extra_artifacts']" in errors


def test_platform_verified_evidence_rejects_ambiguous_linux_workflow_input_keys() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["workflow_inputs"]["TARGET"] = record["workflow_inputs"]["target"]
    record["workflow_inputs"][False] = "manual scratch"
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 workflow_inputs keys must be strings, got False" in errors
    assert (
        "linux-i386 workflow_inputs keys must not collide on case-insensitive filesystems: "
        "['TARGET', 'target']"
    ) in errors


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


def test_platform_verified_evidence_rejects_release_asset_source_unexpected_fields() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-armhf")
    record["release_asset_source"]["download_url"] = (
        "https://github.com/example/remote-ops-workspace/actions/runs/12345/artifacts/1"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-armhf release_asset_source unexpected fields: ['download_url']" in errors


def test_platform_verified_evidence_rejects_non_string_release_asset_source_metadata() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    source = record["release_asset_source"]
    assert isinstance(source, dict)
    source["type"] = True
    source["workflow"] = False
    source["workflow_run_url"] = 12345
    source["artifact_name"] = False
    source["head_sha"] = 42
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 release_asset_source.type must be a string" in errors
    assert "linux-i386 release_asset_source.workflow must be a string" in errors
    assert "linux-i386 release_asset_source.workflow_run_url must be a string" in errors
    assert "linux-i386 release_asset_source.artifact_name must be a string" in errors
    assert "linux-i386 release_asset_source.head_sha must be a string" in errors


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


def test_platform_verified_evidence_rejects_missing_release_source_run_attempt() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    del record["release_asset_source"]["run_attempt"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 release_asset_source missing fields: ['run_attempt']" in errors


def test_platform_verified_evidence_rejects_invalid_release_source_run_attempt() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["release_asset_source"]["run_attempt"] = 0
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 release_asset_source.run_attempt must be a positive integer" in errors


def test_platform_verified_evidence_rejects_malformed_linux_source_attempt_command_binding() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["release_asset_source"]["run_attempt"] = True
    record["local_evidence_preflight_command"] = str(record["local_evidence_preflight_command"]).replace(
        "--linux-source-run-attempt 1",
        "--linux-source-run-attempt True",
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 release_asset_source.run_attempt must be a positive integer" in errors
    assert (
        "linux-i386 local_evidence_preflight_command --linux-source-run-attempt must match "
        "release_asset_source.run_attempt"
    ) in errors


def test_platform_verified_evidence_rejects_malformed_xp_source_attempt_command_binding() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["release_asset_source"]["run_attempt"] = True
    record["local_evidence_preflight_command"] = str(record["local_evidence_preflight_command"]).replace(
        "--xp-source-run-attempt 1",
        "--xp-source-run-attempt True",
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "windows-xp-native-x86 release_asset_source.run_attempt must be a positive integer" in errors
    assert (
        "windows-xp-native-x86 local_evidence_preflight_command --xp-source-run-attempt must match "
        "release_asset_source.run_attempt"
    ) in errors


def test_platform_verified_evidence_source_scope_helpers_ignore_malformed_source_values() -> None:
    checker = _load_platform_verified_evidence_checker()
    records = {
        "linux-i386": {
            "release_asset_source": {
                "workflow_run_url": True,
                "head_sha": True,
                "run_attempt": 1,
            }
        },
        "linux-armhf": {
            "release_asset_source": {
                "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
                "head_sha": "a" * 40,
                "run_attempt": True,
            }
        },
    }

    assert checker.release_source_run_attempt_conflicts(records) == {}
    assert checker.release_source_heads_by_target(records) == {"linux-armhf": "a" * 40}
    assert checker.valid_release_source_workflow_run_url(records["linux-i386"]["release_asset_source"]) == ""
    assert checker.valid_release_source_run_attempt_text(records["linux-armhf"]["release_asset_source"]) == ""


def test_platform_verified_evidence_rejects_boolean_linux_evidence_source_size() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["linux_evidence_sources"]["builder_identity"]["size_bytes"] = True
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 linux_evidence_sources.builder_identity.size_bytes must be a positive integer" in errors


def test_platform_verified_evidence_rejects_boolean_xp_evidence_source_sizes() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["xp_evidence_sources"]["evidence"]["size_bytes"] = True
    record["xp_evidence_sources"]["smoke_evidence"]["cli_launch"]["size_bytes"] = True
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "windows-xp-native-x86 xp_evidence_sources.evidence.size_bytes must be a positive integer" in errors
    assert (
        "windows-xp-native-x86 xp_evidence_sources.smoke_evidence.cli_launch.size_bytes "
        "must be a positive integer"
    ) in errors


def test_platform_verified_evidence_rejects_boolean_review_bundle_size() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-armhf")
    record["review_bundle"]["manifest"]["size_bytes"] = True
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(
        registry=registry,
        require_review_bundles=True,
    )

    assert "linux-armhf review_bundle manifest.size_bytes must be a positive integer" in errors


def test_platform_verified_evidence_rejects_missing_local_evidence_preflight_command() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    del record["local_evidence_preflight_command"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert any(
        "linux-i386 local_evidence_preflight_command must start with" in error
        for error in errors
    )


def test_platform_verified_evidence_rejects_non_string_local_evidence_preflight_command() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["local_evidence_preflight_command"] = True
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "linux-i386 local_evidence_preflight_command must be a string command, got True"
        in errors
    )


def test_platform_verified_evidence_rejects_missing_staged_upload_command() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    del record["staged_upload_command"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert any("linux-i386 staged_upload_command must start with" in error for error in errors)


def test_platform_verified_evidence_rejects_non_string_staged_upload_command() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["staged_upload_command"] = True
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 staged_upload_command must be a string command, got True" in errors


def test_platform_verified_evidence_rejects_linux_staged_upload_source_drift() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-armhf")
    record["staged_upload_command"] = str(record["staged_upload_command"]).replace(
        "--source-dir staged/linux-armhf/v1.0.2/artifacts",
        "--source-dir staged/linux-armhf/v1.0.2/other-artifacts",
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "linux-armhf staged_upload_command --source-dir must match "
        "artifact_validation_command --assets-dir"
    ) in errors


def test_platform_verified_evidence_rejects_linux_staged_upload_overlapping_output_dir() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["staged_upload_command"] = str(record["staged_upload_command"]).replace(
        "--out-dir platform-evidence-upload/linux-i386/v1.0.2",
        "--out-dir staged/linux-i386/v1.0.2/artifacts/linux-evidence-upload",
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "linux-i386 staged_upload_command --out-dir must be a separate root from --source-dir"
        in errors
    )


def test_platform_verified_evidence_rejects_linux_staged_upload_unscoped_out_dir() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["staged_upload_command"] = str(record["staged_upload_command"]).replace(
        "--out-dir platform-evidence-upload/linux-i386/v1.0.2",
        "--out-dir linux-evidence-upload",
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "linux-i386 staged_upload_command --out-dir "
        "must include target path segment 'linux-i386', got 'linux-evidence-upload'"
    ) in errors
    assert (
        "linux-i386 staged_upload_command --out-dir "
        "must include release_tag path segment 'v1.0.2', got 'linux-evidence-upload'"
    ) in errors


def test_platform_verified_evidence_rejects_xp_staged_upload_missing_force() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["staged_upload_command"] = str(record["staged_upload_command"]).replace(" --force", "")
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "windows-xp-native-x86 staged_upload_command must include exactly one --force, got 0" in errors


def test_platform_verified_evidence_rejects_xp_staged_upload_unscoped_output_dir() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x64")
    record["staged_upload_command"] = str(record["staged_upload_command"]).replace(
        "--evidence-output-dir xp-evidence-output/windows-xp-native-x64/v1.0.2",
        "--evidence-output-dir xp-evidence-output/latest",
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x64 staged_upload_command --evidence-output-dir "
        "must include target path segment 'windows-xp-native-x64', got "
        "'xp-evidence-output/latest'"
    ) in errors
    assert (
        "windows-xp-native-x64 staged_upload_command --evidence-output-dir "
        "must include release_tag path segment 'v1.0.2', got 'xp-evidence-output/latest'"
    ) in errors


def test_platform_verified_evidence_rejects_xp_staged_upload_overlapping_output_dir() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["staged_upload_command"] = str(record["staged_upload_command"]).replace(
        "--out-dir platform-evidence-upload/windows-xp-native-x86/v1.0.2",
        "--out-dir native-dist/windows-xp/windows-xp-native-x86/v1.0.2/xp-evidence-upload",
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x86 staged_upload_command --out-dir "
        "must be a separate root from --assets-dir"
    ) in errors


def test_platform_verified_evidence_rejects_xp_staged_upload_overlapping_evidence_output_dir() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x64")
    record["staged_upload_command"] = str(record["staged_upload_command"]).replace(
        "--out-dir platform-evidence-upload/windows-xp-native-x64/v1.0.2",
        "--out-dir xp-evidence-output/windows-xp-native-x64/v1.0.2/upload",
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x64 staged_upload_command --out-dir "
        "must be a separate root from --evidence-output-dir"
    ) in errors


def test_platform_verified_evidence_rejects_xp_staged_upload_unscoped_out_dir() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["staged_upload_command"] = str(record["staged_upload_command"]).replace(
        "--out-dir platform-evidence-upload/windows-xp-native-x86/v1.0.2",
        "--out-dir xp-evidence-upload",
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x86 staged_upload_command --out-dir "
        "must include target path segment 'windows-xp-native-x86', got 'xp-evidence-upload'"
    ) in errors
    assert (
        "windows-xp-native-x86 staged_upload_command --out-dir "
        "must include release_tag path segment 'v1.0.2', got 'xp-evidence-upload'"
    ) in errors


def test_platform_verified_evidence_rejects_xp_asset_evidence_output_overlap() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["staged_upload_command"] = str(record["staged_upload_command"]).replace(
        "--evidence-output-dir xp-evidence-output/windows-xp-native-x86/v1.0.2",
        "--evidence-output-dir native-dist/windows-xp/windows-xp-native-x86/v1.0.2/evidence-output",
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x86 staged_upload_command --assets-dir and "
        "--evidence-output-dir must be separate roots"
    ) in errors


def test_platform_verified_evidence_rejects_linux_local_preflight_source_sha_mismatch() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-armhf")
    record["local_evidence_preflight_command"] = str(
        record["local_evidence_preflight_command"]
    ).replace(f"--linux-source-head-sha {'a' * 40}", f"--linux-source-head-sha {'b' * 40}")
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "linux-armhf local_evidence_preflight_command --linux-source-head-sha must match "
        "release_asset_source.head_sha"
    ) in errors


def test_platform_verified_evidence_rejects_linux_local_preflight_allow_extra_artifacts() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["local_evidence_preflight_command"] = (
        f"{record['local_evidence_preflight_command']} --allow-extra-artifacts"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 local_evidence_preflight_command must not include --allow-extra-artifacts" in errors


def test_platform_verified_evidence_rejects_unexpected_local_preflight_flag() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-armhf")
    record["local_evidence_preflight_command"] = (
        f"{record['local_evidence_preflight_command']} --json"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "linux-armhf local_evidence_preflight_command has unexpected flags: ['--json']"
        in errors
    )


def test_platform_verified_evidence_rejects_unsafe_linux_local_preflight_paths() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["local_evidence_preflight_command"] = (
        "python scripts/check_platform_goal_local_evidence.py --root . "
        "--release-tag v1.0.2 --target linux-i386 "
        "--assets-dir staged/linux-i386/v1.0.2/artifacts "
        "--linux-builder-evidence .github/builder-identity-linux-i386.json "
        "--linux-smoke-evidence evidence/.private/native-smoke-linux-i386.log "
        "--linux-workflow-run-url https://github.com/example/remote-ops-workspace/actions/runs/12345 "
        f"--linux-source-head-sha {'a' * 40} "
        "--linux-source-run-attempt 1"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "linux-i386 local_evidence_preflight_command --linux-builder-evidence "
        "must not point inside reserved workspace directory '.github'"
    ) in errors
    assert (
        "linux-i386 local_evidence_preflight_command --linux-smoke-evidence "
        "must not contain hidden path segments: ['.private']"
    ) in errors


def test_platform_verified_evidence_rejects_linux_local_preflight_without_release_scope() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["local_evidence_preflight_command"] = (
        "python scripts/check_platform_goal_local_evidence.py --root . "
        "--release-tag v1.0.2 --target linux-i386 "
        "--assets-dir staged/linux-i386/v1.0.2/artifacts "
        "--linux-builder-evidence evidence/linux-i386/builder-identity-linux-i386.json "
        "--linux-smoke-evidence evidence/linux-i386/native-smoke-linux-i386.log "
        "--linux-workflow-run-url https://github.com/example/remote-ops-workspace/actions/runs/12345 "
        f"--linux-source-head-sha {'a' * 40} "
        "--linux-source-run-attempt 1"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "linux-i386 local_evidence_preflight_command --linux-builder-evidence "
        "must include release_tag path segment 'v1.0.2', got "
        "'evidence/linux-i386/builder-identity-linux-i386.json'"
    ) in errors
    assert (
        "linux-i386 local_evidence_preflight_command --linux-smoke-evidence "
        "must include release_tag path segment 'v1.0.2', got "
        "'evidence/linux-i386/native-smoke-linux-i386.log'"
    ) in errors


def test_platform_verified_evidence_accepts_scoped_linux_local_preflight_root() -> None:
    checker = _load_platform_verified_evidence_checker()
    target = "linux-i386"
    record = _linux_record(target)
    assets_dir = f"platform-evidence-staging/{target}/v1.0.2/artifacts"
    builder = f"platform-evidence-staging/{target}/v1.0.2/builder-identity-{target}.json"
    smoke = f"platform-evidence-staging/{target}/v1.0.2/native-smoke-{target}.log"
    record["artifact_validation_command"] = (
        f"python scripts/check_platform_promotion_artifacts.py --target {target} "
        f"--assets-dir {assets_dir} --tag v1.0.2 --strict"
    )
    record["staged_upload_command"] = (
        "python scripts/stage_extended_linux_evidence_upload.py "
        f"--target {target} --release-tag v1.0.2 --source-dir {assets_dir} "
        f"--out-dir platform-evidence-upload/{target}/v1.0.2 --force"
    )
    record["local_evidence_preflight_command"] = (
        "python scripts/check_platform_goal_local_evidence.py --root platform-evidence-staging "
        f"--release-tag v1.0.2 --target {target} --assets-dir {assets_dir} "
        f"--linux-builder-evidence {builder} "
        f"--linux-smoke-evidence {smoke} "
        "--linux-workflow-run-url https://github.com/example/remote-ops-workspace/actions/runs/12345 "
        f"--linux-source-head-sha {'a' * 40} "
        "--linux-source-run-attempt 1"
    )
    record["native_smoke_command"] = (
        "bash scripts/smoke_linux_native.sh --arch i386 --dist native-dist/linux "
        f"--target {target} --workflow-run-url https://github.com/example/remote-ops-workspace/actions/runs/12345 "
        f"--workflow-run-attempt 1 --source-head-sha {'a' * 40} "
        f"--builder-evidence {builder}"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert errors == []


def test_platform_verified_evidence_rejects_local_preflight_paths_outside_root() -> None:
    checker = _load_platform_verified_evidence_checker()
    target = "linux-i386"
    record = _linux_record(target)
    record["local_evidence_preflight_command"] = (
        "python scripts/check_platform_goal_local_evidence.py --root platform-evidence-staging "
        f"--release-tag v1.0.2 --target {target} "
        f"--assets-dir staged/{target}/v1.0.2/artifacts "
        f"--linux-builder-evidence evidence/{target}/v1.0.2/builder-identity-{target}.json "
        f"--linux-smoke-evidence evidence/{target}/v1.0.2/native-smoke-{target}.log "
        "--linux-workflow-run-url https://github.com/example/remote-ops-workspace/actions/runs/12345 "
        f"--linux-source-head-sha {'a' * 40} "
        "--linux-source-run-attempt 1"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "linux-i386 local_evidence_preflight_command --assets-dir "
        "must stay under --root platform-evidence-staging, got "
        "'staged/linux-i386/v1.0.2/artifacts'"
    ) in errors
    assert (
        "linux-i386 local_evidence_preflight_command --linux-builder-evidence "
        "must stay under --root platform-evidence-staging, got "
        "'evidence/linux-i386/v1.0.2/builder-identity-linux-i386.json'"
    ) in errors


def test_platform_verified_evidence_rejects_unsafe_local_preflight_root() -> None:
    checker = _load_platform_verified_evidence_checker()
    target = "linux-i386"
    record = _linux_record(target)
    record["local_evidence_preflight_command"] = str(
        record["local_evidence_preflight_command"]
    ).replace("--root .", "--root .github")
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "linux-i386 local_evidence_preflight_command --root "
        "must not point inside reserved workspace directory '.github'"
    ) in errors


def test_platform_verified_evidence_rejects_file_shaped_local_preflight_root() -> None:
    checker = _load_platform_verified_evidence_checker()
    target = "linux-i386"
    record = _linux_record(target)
    assets_dir = f"platform-evidence.zip/{target}/v1.0.2/artifacts"
    builder = f"platform-evidence.zip/{target}/v1.0.2/builder-identity-{target}.json"
    smoke = f"platform-evidence.zip/{target}/v1.0.2/native-smoke-{target}.log"
    record["artifact_validation_command"] = (
        f"python scripts/check_platform_promotion_artifacts.py --target {target} "
        f"--assets-dir {assets_dir} --tag v1.0.2 --strict"
    )
    record["local_evidence_preflight_command"] = (
        "python scripts/check_platform_goal_local_evidence.py --root platform-evidence.zip "
        f"--release-tag v1.0.2 --target {target} --assets-dir {assets_dir} "
        f"--linux-builder-evidence {builder} "
        f"--linux-smoke-evidence {smoke} "
        "--linux-workflow-run-url https://github.com/example/remote-ops-workspace/actions/runs/12345 "
        f"--linux-source-head-sha {'a' * 40} "
        "--linux-source-run-attempt 1"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "linux-i386 local_evidence_preflight_command --root "
        "must be a directory path, got 'platform-evidence.zip'"
    ) in errors


def test_platform_verified_evidence_rejects_xp_local_preflight_evidence_dir_mismatch() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["local_evidence_preflight_command"] = str(
        record["local_evidence_preflight_command"]
    ).replace(
        "--xp-evidence-dir evidence/windows-xp-native-x86/v1.0.2",
        "--xp-evidence-dir evidence/windows-xp-native-x86/v1.0.2/other",
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x86 local_evidence_preflight_command --xp-evidence-dir must match "
        "native_evidence_validation_command --evidence-dir"
    ) in errors


def test_platform_verified_evidence_rejects_xp_local_preflight_missing_source_run() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["local_evidence_preflight_command"] = str(
        record["local_evidence_preflight_command"]
    ).replace(
        " --xp-source-workflow-run-url https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "",
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x86 local_evidence_preflight_command --xp-source-workflow-run-url "
        "must match release_asset_source.workflow_run_url"
    ) in errors


def test_platform_verified_evidence_rejects_xp_local_preflight_source_sha_mismatch() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x64")
    record["local_evidence_preflight_command"] = str(
        record["local_evidence_preflight_command"]
    ).replace(f"--xp-source-head-sha {'a' * 40}", f"--xp-source-head-sha {'b' * 40}")
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x64 local_evidence_preflight_command --xp-source-head-sha "
        "must match release_asset_source.head_sha"
    ) in errors


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


def test_platform_verified_evidence_rejects_malformed_release_source_repository_slug() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x64")
    record["release_asset_source"]["workflow_run_url"] = (
        "https://github.com/example/remote-ops-workspace?run=1/actions/runs/12345"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x64 release_asset_source.workflow_run_url must be a GitHub Actions run URL"
        in errors
    )


def test_platform_verified_evidence_rejects_os_specific_release_source_file_paths() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["release_asset_source"]["contains_files"] = [
        *record["release_asset_source"]["contains_files"],
        r"nested\remote-ops-workspace-v1.0.2-linux-i386.deb",
        r"C:\release\remote-ops-workspace-v1.0.2-linux-i686.rpm",
        True,
    ]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry, require_review_bundles=True)

    assert (
        r"linux-i386 release_asset_source.contains_files entries must be concrete file names, "
        r"got 'nested\\remote-ops-workspace-v1.0.2-linux-i386.deb'"
    ) in errors
    assert (
        r"linux-i386 release_asset_source.contains_files entries must be concrete file names, "
        r"got 'C:\\release\\remote-ops-workspace-v1.0.2-linux-i686.rpm'"
    ) in errors
    assert (
        "linux-i386 release_asset_source.contains_files entries must be concrete file names, "
        "got True"
    ) in errors


def test_platform_verified_evidence_rejects_case_colliding_release_source_files() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    first_file = record["release_asset_source"]["contains_files"][0]
    record["release_asset_source"]["contains_files"].append(first_file.upper())
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry, require_review_bundles=True)

    assert any(
        "linux-i386 release_asset_source.contains_files must not collide on "
        "case-insensitive filesystems" in error
        and first_file in error
        and first_file.upper() in error
        for error in errors
    )


def test_platform_verified_evidence_rejects_unfinalized_source_finalization_files() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    del record["review_bundle"]
    del record["finalized_record_release_asset_url"]
    record["release_asset_source"]["contains_files"] = [
        *sorted(record["artifact_sha256"]),
        "extended-linux-evidence-bundle-linux-i386-v1.0.2.json",
        "platform-verified-evidence-linux-i386-final.json",
    ]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "linux-i386 release_asset_source.contains_files has unexpected files: "
        "['extended-linux-evidence-bundle-linux-i386-v1.0.2.json', "
        "'platform-verified-evidence-linux-i386-final.json']"
    ) in errors


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
        f"https://github.com/example/remote-ops-workspace/actions/runs/12345 "
        f"--workflow-run-attempt 1 --source-head-sha {'a' * 40} "
        "--builder-evidence evidence/linux-i386/v1.0.2/builder-identity-linux-i386.json'"
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


def test_platform_verified_evidence_rejects_linux_smoke_command_without_source_sha() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["native_smoke_command"] = (
        "bash scripts/smoke_linux_native.sh --arch i386 --dist native-dist/linux "
        "--target linux-i386 --workflow-run-url "
        "https://github.com/example/remote-ops-workspace/actions/runs/12345"
    )
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
        f"https://github.com/example/remote-ops-workspace/actions/runs/12345 "
        f"--workflow-run-attempt 1 --source-head-sha {'a' * 40} "
        "--builder-evidence evidence/linux-i386/v1.0.2/builder-identity-linux-i386.json'"
    ) in errors


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
        "linux-armhf workflow_inputs release_asset_base_url must be exactly "
        "https://github.com/<owner>/<repo>/releases/download/v1.0.2" in error
        for error in errors
    )
    assert "linux-armhf workflow_inputs release_asset_base_url must prefix every release_asset_url" in errors


def test_platform_verified_evidence_rejects_linux_workflow_input_repository_drift() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["workflow_inputs"]["release_asset_base_url"] = (
        "https://github.com/other/remote-ops-workspace/releases/download/v1.0.2"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 workflow_inputs release_asset_base_url must prefix every release_asset_url" in errors
    assert (
        "linux-i386 workflow_inputs release_asset_base_url repository must match "
        "release_asset_source.workflow_run_url repository example/remote-ops-workspace, "
        "got other/remote-ops-workspace"
    ) in errors


def test_platform_verified_evidence_rejects_linux_workflow_input_trailing_slash_base_url() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["workflow_inputs"]["release_asset_base_url"] = (
        "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "linux-i386 workflow_inputs release_asset_base_url must be exactly "
        "https://github.com/<owner>/<repo>/releases/download/v1.0.2"
    ) in errors


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


def test_platform_verified_evidence_rejects_non_string_artifact_validation_command() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["artifact_validation_command"] = True
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 artifact_validation_command must be a string command, got True" in errors


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


def test_platform_verified_evidence_rejects_unexpected_artifact_validation_flag() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x64")
    record["artifact_validation_command"] = (
        f"{record['artifact_validation_command']} --dry-run"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x64 artifact_validation_command has unexpected flags: ['--dry-run']"
        in errors
    )


def test_platform_verified_evidence_rejects_missing_artifact_validation_strict() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["artifact_validation_command"] = record["artifact_validation_command"].replace(
        " --strict",
        "",
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "windows-xp-native-x86 artifact_validation_command must include exactly one --strict, got 0" in errors


def test_platform_verified_evidence_rejects_missing_artifact_validation_assets_dir() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["artifact_validation_command"] = (
        "python scripts/check_platform_promotion_artifacts.py --target windows-xp-native-x86 --tag v1.0.2 --strict"
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
        "--assets-dir <artifact-dir> --tag v1.0.2 --strict"
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
        "--assets-dir .github/linux-i386 --tag v1.0.2 --strict"
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


def test_platform_verified_evidence_rejects_windows_drive_artifact_validation_assets_dir() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["artifact_validation_command"] = (
        "python scripts/check_platform_promotion_artifacts.py --target linux-i386 "
        "--assets-dir C:/staged/linux-i386/v1.0.2/artifacts --tag v1.0.2 --strict"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "linux-i386 artifact_validation_command --assets-dir "
        "must be workspace-relative, got 'C:/staged/linux-i386/v1.0.2/artifacts'"
    ) in errors


def test_platform_verified_evidence_rejects_unscoped_linux_artifact_validation_assets_dir() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["artifact_validation_command"] = (
        "python scripts/check_platform_promotion_artifacts.py --target linux-i386 "
        "--assets-dir native-dist/linux --tag v1.0.2 --strict"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "linux-i386 artifact_validation_command --assets-dir "
        "must include target path segment 'linux-i386', got 'native-dist/linux'"
    ) in errors


def test_platform_verified_evidence_rejects_file_shaped_artifact_validation_assets_dir() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["artifact_validation_command"] = (
        "python scripts/check_platform_promotion_artifacts.py --target linux-i386 "
        "--assets-dir staged/linux-i386/v1.0.2/artifacts.zip --tag v1.0.2 --strict"
    )
    record["local_evidence_preflight_command"] = str(
        record["local_evidence_preflight_command"]
    ).replace(
        "--assets-dir staged/linux-i386/v1.0.2/artifacts",
        "--assets-dir staged/linux-i386/v1.0.2/artifacts.zip",
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "linux-i386 artifact_validation_command --assets-dir "
        "must be a directory path, got 'staged/linux-i386/v1.0.2/artifacts.zip'"
    ) in errors


def test_platform_verified_evidence_rejects_linux_artifact_validation_without_release_scope() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["artifact_validation_command"] = (
        "python scripts/check_platform_promotion_artifacts.py --target linux-i386 "
        "--assets-dir staged/linux-i386/artifacts --tag v1.0.2 --strict"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "linux-i386 artifact_validation_command --assets-dir "
        "must include release_tag path segment 'v1.0.2', got 'staged/linux-i386/artifacts'"
    ) in errors


def test_platform_verified_evidence_rejects_wildcard_xp_artifact_validation_assets_dir() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["artifact_validation_command"] = (
        "python scripts/check_platform_promotion_artifacts.py --target windows-xp-native-x86 "
        "--assets-dir staged/xp-x86/* --tag v1.0.2 --strict"
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
        "--assets-dir native-dist/windows-xp --tag v1.0.2 --strict"
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


def test_platform_verified_evidence_rejects_non_string_xp_native_validation_command() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["native_evidence_validation_command"] = True
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x86 native_evidence_validation_command must be a string command, got True"
        in errors
    )


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


def test_platform_verified_evidence_rejects_xp_native_validation_contract_flag() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["native_evidence_validation_command"] = (
        f"{record['native_evidence_validation_command']} --contract"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(
        registry=registry,
        require_review_bundles=True,
    )

    assert (
        "windows-xp-native-x86 native_evidence_validation_command "
        "has unexpected flags: ['--contract']"
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


def test_platform_verified_evidence_rejects_ambiguous_xp_workflow_input_keys() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["workflow_inputs"]["TARGET"] = record["workflow_inputs"]["target"]
    record["workflow_inputs"][True] = "manual scratch"
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "windows-xp-native-x86 workflow_inputs keys must be strings, got True" in errors
    assert (
        "windows-xp-native-x86 workflow_inputs keys must not collide on case-insensitive "
        "filesystems: ['TARGET', 'target']"
    ) in errors


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


def test_platform_verified_evidence_rejects_xp_workflow_input_trailing_slash_base_url() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x64")
    record["workflow_inputs"]["release_asset_base_url"] = (
        "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x64 workflow_inputs release_asset_base_url must be exactly "
        "https://github.com/<owner>/<repo>/releases/download/v1.0.2"
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


def test_platform_verified_evidence_rejects_ambiguous_xp_evidence_source_keys() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    sources = record["xp_evidence_sources"]
    sources["SMOKE_EVIDENCE"] = sources["smoke_evidence"]
    sources[True] = sources["evidence"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "windows-xp-native-x86 xp_evidence_sources keys must be strings, got True" in errors
    assert any(
        "windows-xp-native-x86 xp_evidence_sources keys must not collide on "
        "case-insensitive filesystems" in error
        and "smoke_evidence" in error
        and "SMOKE_EVIDENCE" in error
        for error in errors
    )


def test_platform_verified_evidence_rejects_ambiguous_xp_smoke_evidence_source_keys() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    smoke_sources = record["xp_evidence_sources"]["smoke_evidence"]
    smoke_sources["CLI_LAUNCH"] = smoke_sources["cli_launch"]
    smoke_sources[False] = smoke_sources["artifact_manifest_validation"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x86 xp_evidence_sources.smoke_evidence smoke ids must be strings, "
        "got False"
    ) in errors
    assert any(
        "windows-xp-native-x86 xp_evidence_sources.smoke_evidence smoke ids must not collide on "
        "case-insensitive filesystems" in error
        and "cli_launch" in error
        and "CLI_LAUNCH" in error
        for error in errors
    )


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


def test_platform_verified_evidence_rejects_xp_evidence_source_unexpected_fields() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["xp_evidence_sources"]["evidence"]["operator_note"] = "manual review"
    record["xp_evidence_sources"]["smoke_evidence"]["cli_launch"]["path"] = (
        "xp-smoke-evidence/cli_launch.txt"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x86 xp_evidence_sources.evidence unexpected fields: ['operator_note']"
    ) in errors
    assert (
        "windows-xp-native-x86 xp_evidence_sources.smoke_evidence.cli_launch unexpected fields: ['path']"
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


def test_platform_verified_evidence_rejects_non_string_builder_identity_digest() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["builder_identity_sha256"] = True
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 builder_identity_sha256 must be a string SHA-256 hex digest" in errors


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


def test_platform_verified_evidence_rejects_builder_identity_workflow_provenance_mismatch() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["builder_identity"]["workflow_ref"] = (
        "example/remote-ops-workspace/.github/workflows/ci.yml@refs/heads/main"
    )
    record["builder_identity"]["workflow_sha"] = "b" * 40
    record["builder_identity_sha256"] = _json_sha256(record["builder_identity"])
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert any(
        "linux-i386 builder_identity workflow_ref must point at "
        "example/remote-ops-workspace/.github/workflows/extended-platform-evidence.yml@<ref>"
        in error
        for error in errors
    )
    assert "linux-i386 builder_identity workflow_sha must match release_asset_source.head_sha" in errors


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


def test_platform_verified_evidence_rejects_builder_identity_observed_git_head_sha_mismatch() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["builder_identity"]["observed_git_head_sha"] = "b" * 40
    record["builder_identity_sha256"] = _json_sha256(record["builder_identity"])
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 builder_identity observed_git_head_sha must match release_asset_source.head_sha" in errors


def test_platform_verified_evidence_rejects_dirty_builder_git_worktree() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["builder_identity"]["git_worktree_clean"] = False
    record["builder_identity_sha256"] = _json_sha256(record["builder_identity"])
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 builder_identity git_worktree_clean must be true" in errors


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


def test_platform_verified_evidence_rejects_unexpected_linux_builder_identity_fields() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["builder_identity"]["hostname"] = "private-builder"
    record["builder_identity"]["scratch_note"] = "manual copy"
    record["builder_identity"]["host_identity"]["runner_name"] = "private-runner"
    record["builder_identity"]["required_tools"]["home_dir"] = "/home/private-user"
    record["builder_identity"]["security_patch_evidence"]["operator_note"] = "manual review"
    record["builder_identity_sha256"] = _json_sha256(record["builder_identity"])
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 builder_identity unexpected fields: ['hostname', 'scratch_note']" in errors
    assert (
        "linux-i386 builder_identity host_identity unexpected fields: ['runner_name']"
    ) in errors
    assert (
        "linux-i386 builder_identity host_identity contains forbidden private fields: ['runner_name']"
    ) in errors
    assert (
        "linux-i386 builder_identity required_tools unexpected fields: ['home_dir']"
    ) in errors
    assert (
        "linux-i386 builder_identity security_patch_evidence unexpected fields: ['operator_note']"
    ) in errors


def test_platform_verified_evidence_rejects_ambiguous_linux_builder_host_identity_keys() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    host_identity = record["builder_identity"]["host_identity"]
    assert isinstance(host_identity, dict)
    host_identity["TARGET"] = host_identity["target"]
    host_identity[True] = "manual"
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 builder_identity host_identity keys must be strings, got True" in errors
    assert (
        "linux-i386 builder_identity host_identity keys must not collide on case-insensitive "
        "filesystems: ['TARGET', 'target']"
    ) in errors
    assert (
        "linux-i386 builder_identity JSON object keys must be strings for SHA-256 verification"
    ) in errors


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


def test_platform_verified_evidence_rejects_missing_linux_runtime_identity() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    del record["builder_identity"]["os_release"]
    record["builder_identity"]["kernel_release"] = ""
    record["builder_identity_sha256"] = _json_sha256(record["builder_identity"])
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 builder_identity os_release must be set" in errors
    assert "linux-i386 builder_identity kernel_release must be set" in errors


def test_platform_verified_evidence_rejects_non_string_linux_runtime_identity() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["builder_identity"]["os_release"] = True
    record["builder_identity"]["kernel_release"] = 610
    record["builder_identity"]["glibc_version"] = None
    record["builder_identity_sha256"] = _json_sha256(record["builder_identity"])
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 builder_identity os_release must be a string" in errors
    assert "linux-i386 builder_identity kernel_release must be a string" in errors
    assert "linux-i386 builder_identity glibc_version must be a string" in errors


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


def test_platform_verified_evidence_rejects_missing_security_patch_provenance() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    del record["builder_identity"]["security_patch_evidence"]["cve_review_reference"]
    record["builder_identity"]["security_patch_evidence"]["security_update_channel"] = ""
    record["builder_identity_sha256"] = _json_sha256(record["builder_identity"])
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 builder_identity security_patch_evidence.cve_review_reference must be set" in errors
    assert "linux-i386 builder_identity security_patch_evidence.security_update_channel must be set" in errors


def test_platform_verified_evidence_rejects_placeholder_security_patch_provenance() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["builder_identity"]["security_patch_evidence"]["security_update_channel"] = "test-security-update-channel"
    record["builder_identity"]["security_patch_evidence"]["cve_review_reference"] = "<replace-with-real-cve-review>"
    record["builder_identity_sha256"] = _json_sha256(record["builder_identity"])
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "linux-i386 builder_identity security_patch_evidence.security_update_channel "
        "must name concrete non-placeholder provenance"
    ) in errors
    assert (
        "linux-i386 builder_identity security_patch_evidence.cve_review_reference "
        "must name concrete non-placeholder provenance"
    ) in errors


def test_platform_verified_evidence_rejects_vague_security_patch_provenance() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["builder_identity"]["security_patch_evidence"]["security_update_channel"] = "monthly maintenance baseline"
    record["builder_identity"]["security_patch_evidence"]["cve_review_reference"] = "internal review 2026 06"
    record["builder_identity_sha256"] = _json_sha256(record["builder_identity"])
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "linux-i386 builder_identity security_patch_evidence.security_update_channel "
        "must name concrete non-placeholder provenance"
    ) in errors
    assert (
        "linux-i386 builder_identity security_patch_evidence.cve_review_reference "
        "must name concrete non-placeholder provenance"
    ) in errors


def test_platform_verified_evidence_rejects_reserved_https_security_patch_provenance() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["builder_identity"]["security_patch_evidence"][
        "security_update_channel"
    ] = "https://example.com/security-updates/linux-i386"
    record["builder_identity"]["security_patch_evidence"][
        "cve_review_reference"
    ] = "https://example.com/security-advisory/CVE-2026-0001"
    record["builder_identity_sha256"] = _json_sha256(record["builder_identity"])
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "linux-i386 builder_identity security_patch_evidence.security_update_channel "
        "must name concrete non-placeholder provenance"
    ) in errors
    assert (
        "linux-i386 builder_identity security_patch_evidence.cve_review_reference "
        "must name concrete non-placeholder provenance"
    ) in errors


def test_platform_verified_evidence_rejects_generic_https_security_patch_cve_reference() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    security = record["builder_identity"]["security_patch_evidence"]
    assert isinstance(security, dict)
    security["security_update_channel"] = "vendor-security-updates-2026-07"
    security["cve_review_reference"] = "https://security.vendor.com/releases/2026-07"
    summary = record["linux_smoke_summary"]
    assert isinstance(summary, dict)
    summary_security = summary["security"]
    assert isinstance(summary_security, dict)
    summary_security["security_update_channel"] = security["security_update_channel"]
    summary_security["cve_review_reference"] = security["cve_review_reference"]
    record["builder_identity_sha256"] = _json_sha256(record["builder_identity"])
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "linux-i386 builder_identity security_patch_evidence.cve_review_reference "
        "must name concrete non-placeholder provenance"
    ) in errors
    assert (
        "linux-i386 linux_smoke_summary security.cve_review_reference "
        "must name concrete non-placeholder provenance"
    ) in errors


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


def test_platform_verified_evidence_rejects_non_string_linux_smoke_digest() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-armhf")
    record["linux_smoke_evidence_sha256"]["native_smoke"] = True
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "linux-armhf linux_smoke_evidence_sha256 for native_smoke must be "
        "a string SHA-256 hex digest"
    ) in errors


def test_platform_verified_evidence_rejects_non_string_linux_smoke_evidence_key() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["linux_smoke_evidence_sha256"][True] = "0" * 64
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 linux_smoke_evidence_sha256 smoke ids must be strings, got True" in errors


def test_platform_verified_evidence_rejects_case_colliding_linux_smoke_evidence_key() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    smoke_id = next(iter(record["linux_smoke_evidence_sha256"]))
    record["linux_smoke_evidence_sha256"][smoke_id.upper()] = "0" * 64
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert any(
        "linux-i386 linux_smoke_evidence_sha256 smoke ids must not collide on "
        "case-insensitive filesystems" in error
        and smoke_id in error
        and smoke_id.upper() in error
        for error in errors
    )


def test_platform_verified_evidence_rejects_missing_linux_smoke_summary() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    del record["linux_smoke_summary"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 linux_smoke_summary must be an object" in errors


def test_platform_verified_evidence_rejects_weak_linux_smoke_summary_security() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    summary = record["linux_smoke_summary"]
    assert isinstance(summary, dict)
    security = summary["security"]
    assert isinstance(security, dict)
    security["tls_minimum_modern_profiles"] = "TLS 1.1"
    security["weak_crypto_global_default"] = True
    security["modern_defaults_unchanged"] = False
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 linux_smoke_summary security.tls_minimum_modern_profiles must be 'TLS 1.2'" in errors
    assert "linux-i386 linux_smoke_summary security.weak_crypto_global_default must be False" in errors
    assert "linux-i386 linux_smoke_summary security.modern_defaults_unchanged must be True" in errors


def test_platform_verified_evidence_rejects_wrong_linux_smoke_summary_runtime() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-armhf")
    summary = record["linux_smoke_summary"]
    assert isinstance(summary, dict)
    summary["uname_machine"] = "x86_64"
    summary["dpkg_architecture"] = "arm64"
    summary["userland_bits"] = "64"
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert any("linux-armhf linux_smoke_summary uname_machine must be one of" in error for error in errors)
    assert "linux-armhf linux_smoke_summary dpkg_architecture must be one of ['armhf'], got 'arm64'" in errors
    assert "linux-armhf linux_smoke_summary userland_bits must be '32', got '64'" in errors


def test_platform_verified_evidence_rejects_non_string_linux_smoke_summary_metadata() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    summary = record["linux_smoke_summary"]
    assert isinstance(summary, dict)
    summary["source_head_sha"] = True
    summary["git_head_sha"] = 12345
    summary["uname_machine"] = 686
    summary["dpkg_architecture"] = False
    summary["userland_bits"] = 32
    summary["host_label"] = None
    summary["evidence_run_id"] = 12345
    summary["observed_at_utc"] = True
    summary["os_release"] = 12
    summary["kernel_release"] = False
    summary["glibc_version"] = None
    summary["python_ssl_openssl"] = 3
    summary["openssl_cli_version"] = False
    security = summary["security"]
    assert isinstance(security, dict)
    security["security_update_channel"] = True
    security["cve_review_reference"] = False
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 linux_smoke_summary source_head_sha must be a string" in errors
    assert "linux-i386 linux_smoke_summary git_head_sha must be a string" in errors
    assert "linux-i386 linux_smoke_summary uname_machine must be a string" in errors
    assert "linux-i386 linux_smoke_summary dpkg_architecture must be a string" in errors
    assert "linux-i386 linux_smoke_summary userland_bits must be a string" in errors
    assert "linux-i386 linux_smoke_summary host_label must be a string" in errors
    assert "linux-i386 linux_smoke_summary evidence_run_id must be a string" in errors
    assert "linux-i386 linux_smoke_summary observed_at_utc must be a string" in errors
    assert "linux-i386 linux_smoke_summary os_release must be a string" in errors
    assert "linux-i386 linux_smoke_summary kernel_release must be a string" in errors
    assert "linux-i386 linux_smoke_summary glibc_version must be a string" in errors
    assert "linux-i386 linux_smoke_summary python_ssl_openssl must be a string" in errors
    assert "linux-i386 linux_smoke_summary openssl_cli_version must be a string" in errors
    assert "linux-i386 linux_smoke_summary security.security_update_channel must be a string" in errors
    assert "linux-i386 linux_smoke_summary security.cve_review_reference must be a string" in errors


def test_platform_verified_evidence_rejects_placeholder_linux_smoke_summary_provenance() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    summary = record["linux_smoke_summary"]
    assert isinstance(summary, dict)
    security = summary["security"]
    assert isinstance(security, dict)
    security["security_update_channel"] = "test-security-update-channel"
    security["cve_review_reference"] = "<replace-with-real-cve-review>"
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "linux-i386 linux_smoke_summary security.security_update_channel "
        "must name concrete non-placeholder provenance"
    ) in errors
    assert (
        "linux-i386 linux_smoke_summary security.cve_review_reference "
        "must name concrete non-placeholder provenance"
    ) in errors


def test_platform_verified_evidence_rejects_vague_linux_smoke_summary_provenance() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    summary = record["linux_smoke_summary"]
    assert isinstance(summary, dict)
    security = summary["security"]
    assert isinstance(security, dict)
    security["security_update_channel"] = "monthly maintenance baseline"
    security["cve_review_reference"] = "internal review 2026 06"
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "linux-i386 linux_smoke_summary security.security_update_channel "
        "must name concrete non-placeholder provenance"
    ) in errors
    assert (
        "linux-i386 linux_smoke_summary security.cve_review_reference "
        "must name concrete non-placeholder provenance"
    ) in errors


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


def test_platform_verified_evidence_rejects_ambiguous_linux_evidence_source_keys() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    sources = record["linux_evidence_sources"]
    sources["NATIVE_SMOKE"] = sources["native_smoke"]
    sources[True] = sources["builder_identity"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 linux_evidence_sources keys must be strings, got True" in errors
    assert any(
        "linux-i386 linux_evidence_sources keys must not collide on "
        "case-insensitive filesystems" in error
        and "native_smoke" in error
        and "NATIVE_SMOKE" in error
        for error in errors
    )


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


def test_platform_verified_evidence_rejects_linux_evidence_source_unexpected_fields() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["linux_evidence_sources"]["builder_identity"]["path"] = (
        "evidence/linux-i386/v1.0.2/builder-identity-linux-i386.json"
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "linux-i386 linux_evidence_sources.builder_identity unexpected fields: ['path']"
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


def test_platform_verified_evidence_rejects_non_list_checks() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["checks"] = "builder_preflight,native_build"
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 evidence checks must be a list" in errors


def test_platform_verified_evidence_rejects_unexpected_checks() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-armhf")
    record["checks"] = [*record["checks"], "manual-operator-approval"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-armhf evidence has unexpected checks: ['manual-operator-approval']" in errors


def test_platform_verified_evidence_rejects_duplicate_checks() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x64")
    record["checks"] = [*record["checks"], "artifact_validation"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "windows-xp-native-x64 evidence has duplicate checks: ['artifact_validation']" in errors


def test_platform_verified_evidence_rejects_non_string_checks() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _linux_record("linux-i386")
    record["checks"] = [*record["checks"], True]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "linux-i386 evidence checks entries must be strings, got True" in errors


def test_platform_verified_evidence_rejects_case_colliding_checks() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x64")
    record["checks"] = [*record["checks"], "ARTIFACT_VALIDATION"]
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x64 evidence checks must not collide on case-insensitive "
        "filesystems: ['ARTIFACT_VALIDATION', 'artifact_validation']"
    ) in errors


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


def test_platform_verified_evidence_rejects_non_string_xp_evidence_digest() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["xp_evidence_sha256"] = True
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "windows-xp-native-x86 xp_evidence_sha256 must be a string SHA-256 hex digest" in errors


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


def test_platform_verified_evidence_rejects_non_string_xp_contract_digest() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["xp_evidence_contract_sha256"] = True
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x86 xp_evidence_contract_sha256 must be a string SHA-256 hex digest"
        in errors
    )


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


def test_platform_verified_evidence_rejects_non_string_xp_host_identity_digest() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["xp_host_identity_sha256"] = True
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x86 xp_host_identity_sha256 must be a string SHA-256 hex digest"
        in errors
    )


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


def test_platform_verified_evidence_rejects_private_xp_host_identity_fields() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    host_identity = record["xp_evidence_summary"]["host_identity"]
    assert isinstance(host_identity, dict)
    host_identity["host_label"] = "yunus-pc"
    host_identity["evidence_run_id"] = "manual-run-20260620t120000z"
    host_identity["hostname"] = "yunus-pc"
    record["xp_host_identity_sha256"] = _json_sha256(host_identity)
    smoke_commands = record["xp_evidence_summary"]["smoke_commands"]
    assert isinstance(smoke_commands, dict)
    for smoke_id, command in list(smoke_commands.items()):
        smoke_commands[smoke_id] = str(command).replace(
            "--host-label xp-x86-lab-01",
            "--host-label yunus-pc",
        ).replace(
            "--evidence-run-id xp-x86-1-0-2-20260620t120000z",
            "--evidence-run-id manual-run-20260620t120000z",
        )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x86 xp_evidence_summary host_identity.host_label "
        "must be a sanitized target-scoped lab label, got 'yunus-pc'"
    ) in errors
    assert (
        "windows-xp-native-x86 xp_evidence_summary host_identity.evidence_run_id "
        "must be a sanitized target-scoped run id, got 'manual-run-20260620t120000z'"
    ) in errors
    assert (
        "windows-xp-native-x86 xp_evidence_summary host_identity contains forbidden private fields: ['hostname']"
    ) in errors


def test_platform_verified_evidence_rejects_ambiguous_xp_host_identity_keys() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    host_identity = record["xp_evidence_summary"]["host_identity"]
    assert isinstance(host_identity, dict)
    host_identity["TARGET"] = host_identity["target"]
    host_identity[False] = "manual"
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x86 xp_evidence_summary host_identity keys must be strings, got False"
    ) in errors
    assert (
        "windows-xp-native-x86 xp_evidence_summary host_identity keys must not collide on "
        "case-insensitive filesystems: ['TARGET', 'target']"
    ) in errors
    assert (
        "windows-xp-native-x86 xp_evidence_summary host_identity JSON object keys must be strings "
        "for SHA-256 verification"
    ) in errors


def test_platform_verified_evidence_rejects_xp_run_id_not_bound_to_observed_at() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x64")
    host_identity = record["xp_evidence_summary"]["host_identity"]
    assert isinstance(host_identity, dict)
    host_identity["evidence_run_id"] = "xp-x64-1-0-2-20260620t123000z"
    record["xp_host_identity_sha256"] = _json_sha256(host_identity)
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x64 xp_evidence_summary host_identity.evidence_run_id must include "
        "release/observed-at marker '1-0-2-20260620t120000z', got 'xp-x64-1-0-2-20260620t123000z'"
    ) in errors


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


def test_platform_verified_evidence_rejects_non_string_xp_smoke_digest_key() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x64")
    record["xp_smoke_evidence_sha256"][True] = "0" * 64
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "windows-xp-native-x64 xp_smoke_evidence_sha256 smoke ids must be strings, got True" in errors


def test_platform_verified_evidence_rejects_non_string_xp_smoke_digest_value() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x64")
    record["xp_smoke_evidence_sha256"]["cli_launch"] = True
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x64 xp_smoke_evidence_sha256 for cli_launch must be "
        "a string SHA-256 hex digest"
    ) in errors


def test_platform_verified_evidence_rejects_case_colliding_xp_smoke_digest_key() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x64")
    smoke_id = next(iter(record["xp_smoke_evidence_sha256"]))
    record["xp_smoke_evidence_sha256"][smoke_id.upper()] = "0" * 64
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert any(
        "windows-xp-native-x64 xp_smoke_evidence_sha256 smoke ids must not collide on "
        "case-insensitive filesystems" in error
        and smoke_id in error
        and smoke_id.upper() in error
        for error in errors
    )


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


def test_platform_verified_evidence_rejects_ambiguous_xp_summary_smoke_ids() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    smoke_id = record["xp_evidence_summary"]["smoke_ids"][0]
    record["xp_evidence_summary"]["smoke_ids"].extend([smoke_id, smoke_id.upper(), True])
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "windows-xp-native-x86 xp_evidence_summary smoke_ids entries must be strings, got True" in errors
    assert f"windows-xp-native-x86 xp_evidence_summary smoke_ids contains duplicates: ['{smoke_id}']" in errors
    assert any(
        "windows-xp-native-x86 xp_evidence_summary smoke_ids must not collide on "
        "case-insensitive filesystems" in error
        and smoke_id in error
        and smoke_id.upper() in error
        for error in errors
    )


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


def test_platform_verified_evidence_rejects_unexpected_xp_evidence_summary_fields() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    summary = record["xp_evidence_summary"]
    summary["operator_note"] = "manual copy"
    summary["release_source"]["scratch"] = "manual"
    summary["os"]["computer_name"] = "private-xp-host"
    summary["toolchain"]["tool_path"] = "C:\\private\\toolchain"
    summary["security"]["operator_note"] = "manual review"
    summary["security"]["patch_evidence"]["operator_note"] = "manual review"
    summary["host_identity"]["runner_name"] = "private-runner"
    summary["host_identity"]["os"]["hostname"] = "private-xp-host"
    summary["host_identity"]["toolchain"]["builder_user"] = "private-user"
    record["xp_host_identity_sha256"] = _json_sha256(summary["host_identity"])
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "windows-xp-native-x86 xp_evidence_summary unexpected fields: ['operator_note']" in errors
    assert (
        "windows-xp-native-x86 xp_evidence_summary release_source unexpected fields: ['scratch']"
    ) in errors
    assert "windows-xp-native-x86 xp_evidence_summary os unexpected fields: ['computer_name']" in errors
    assert (
        "windows-xp-native-x86 xp_evidence_summary toolchain unexpected fields: ['tool_path']"
    ) in errors
    assert (
        "windows-xp-native-x86 xp_evidence_summary security unexpected fields: ['operator_note']"
    ) in errors
    assert (
        "windows-xp-native-x86 xp_evidence_summary security.patch_evidence unexpected fields: ['operator_note']"
    ) in errors
    assert (
        "windows-xp-native-x86 xp_evidence_summary host_identity unexpected fields: ['runner_name']"
    ) in errors
    assert (
        "windows-xp-native-x86 xp_evidence_summary host_identity contains forbidden private fields: ['runner_name']"
    ) in errors
    assert (
        "windows-xp-native-x86 xp_evidence_summary host_identity.os unexpected fields: ['hostname']"
    ) in errors
    assert (
        "windows-xp-native-x86 xp_evidence_summary host_identity.toolchain unexpected fields: ['builder_user']"
    ) in errors


def test_platform_verified_evidence_rejects_xp_evidence_summary_release_source_mismatch() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["xp_evidence_summary"]["release_source"]["head_sha"] = "b" * 40
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x86 xp_evidence_summary release_source.head_sha must match "
        "release_asset_source.head_sha"
    ) in errors


def test_platform_verified_evidence_rejects_non_string_xp_evidence_summary_release_source() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    source = record["xp_evidence_summary"]["release_source"]
    source["workflow"] = True
    source["workflow_run_url"] = 12345
    source["head_sha"] = False
    source["run_attempt"] = "1"
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "windows-xp-native-x86 xp_evidence_summary release_source.workflow must be a string" in errors
    assert (
        "windows-xp-native-x86 xp_evidence_summary release_source.workflow_run_url must be a string"
        in errors
    )
    assert "windows-xp-native-x86 xp_evidence_summary release_source.head_sha must be a string" in errors
    assert (
        "windows-xp-native-x86 xp_evidence_summary release_source.run_attempt must be a positive integer"
        in errors
    )


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


def test_platform_verified_evidence_rejects_ambiguous_xp_smoke_evidence_file_keys() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    files = record["xp_evidence_summary"]["smoke_evidence_files"]
    smoke_id = "cli_launch"
    files[smoke_id.upper()] = files[smoke_id]
    files[True] = "xp-smoke-evidence/true.txt"
    files["artifact_manifest_validation"] = True
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x86 xp_evidence_summary smoke_evidence_files smoke ids must be strings, "
        "got True"
    ) in errors
    assert (
        "windows-xp-native-x86 xp_evidence_summary smoke_evidence_files artifact_manifest_validation "
        "must be a string path, got True"
    ) in errors
    assert any(
        "windows-xp-native-x86 xp_evidence_summary smoke_evidence_files smoke ids must not collide on "
        "case-insensitive filesystems" in error
        and smoke_id in error
        and smoke_id.upper() in error
        for error in errors
    )


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


def test_platform_verified_evidence_rejects_ambiguous_xp_smoke_command_keys() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    commands = record["xp_evidence_summary"]["smoke_commands"]
    smoke_id = "cli_launch"
    commands[smoke_id.upper()] = commands[smoke_id]
    commands[True] = "python scripts/check_xp_native_evidence.py --smoke-id true"
    commands["artifact_manifest_validation"] = True
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert "windows-xp-native-x86 xp_evidence_summary smoke_commands smoke ids must be strings, got True" in errors
    assert (
        "windows-xp-native-x86 xp_evidence_summary smoke_commands artifact_manifest_validation "
        "must be a string command, got True"
    ) in errors
    assert any(
        "windows-xp-native-x86 xp_evidence_summary smoke_commands smoke ids must not collide on "
        "case-insensitive filesystems" in error
        and smoke_id in error
        and smoke_id.upper() in error
        for error in errors
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


def test_platform_verified_evidence_rejects_xp_smoke_command_release_source_mismatch() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["xp_evidence_summary"]["smoke_commands"]["cli_launch"] = record["xp_evidence_summary"][
        "smoke_commands"
    ]["cli_launch"].replace(
        "--source-head-sha aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "--source-head-sha bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb",
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x86 xp_evidence_summary smoke_commands cli_launch must include exactly one "
        "--source-head-sha aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa, got "
        "['bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb']"
    ) in errors


def test_platform_verified_evidence_rejects_xp_smoke_command_host_identity_mismatch() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["xp_evidence_summary"]["smoke_commands"]["cli_launch"] = record["xp_evidence_summary"][
        "smoke_commands"
    ]["cli_launch"].replace(
        "--host-label xp-x86-lab-01",
        "--host-label xp-x86-lab-02",
    ).replace(
        "--evidence-run-id xp-x86-1-0-2-20260620t120000z",
        "--evidence-run-id xp-x86-1-0-2-other",
    ).replace(
        "--observed-at-utc 2026-06-20T12:00:00Z",
        "--observed-at-utc 2026-06-20T12:30:00Z",
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x86 xp_evidence_summary smoke_commands cli_launch must include exactly one "
        "--host-label xp-x86-lab-01, got ['xp-x86-lab-02']"
    ) in errors
    assert (
        "windows-xp-native-x86 xp_evidence_summary smoke_commands cli_launch must include exactly one "
        "--evidence-run-id xp-x86-1-0-2-20260620t120000z, got ['xp-x86-1-0-2-other']"
    ) in errors
    assert (
        "windows-xp-native-x86 xp_evidence_summary smoke_commands cli_launch must include exactly one "
        "--observed-at-utc 2026-06-20T12:00:00Z, got ['2026-06-20T12:30:00Z']"
    ) in errors


def test_platform_verified_evidence_rejects_xp_security_smoke_command_provenance_mismatch() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["xp_evidence_summary"]["smoke_commands"]["legacy_crypto_profile_scoped"] = record["xp_evidence_summary"][
        "smoke_commands"
    ]["legacy_crypto_profile_scoped"].replace(
        "--cve-review-reference vendor-cve-advisory-review-2026-06",
        "--cve-review-reference stale-cve-review",
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x86 xp_evidence_summary smoke_commands legacy_crypto_profile_scoped "
        "must include exactly one --cve-review-reference vendor-cve-advisory-review-2026-06, "
        "got ['stale-cve-review']"
    ) in errors


def test_platform_verified_evidence_rejects_xp_smoke_command_os_identity_mismatch() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x64")
    record["xp_evidence_summary"]["smoke_commands"]["cli_launch"] = record["xp_evidence_summary"][
        "smoke_commands"
    ]["cli_launch"].replace(
        '--os-name "Windows XP"',
        '--os-name "Windows 7"',
    ).replace(
        "--os-architecture x64",
        "--os-architecture x86",
    ).replace(
        "--os-service-pack SP2",
        "--os-service-pack SP1",
    ).replace(
        '--os-edition "Professional x64 Edition"',
        '--os-edition "Ultimate"',
    )
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x64 xp_evidence_summary smoke_commands cli_launch must include exactly one "
        "--os-name Windows XP, got ['Windows 7']"
    ) in errors
    assert (
        "windows-xp-native-x64 xp_evidence_summary smoke_commands cli_launch must include exactly one "
        "--os-architecture x64, got ['x86']"
    ) in errors
    assert (
        "windows-xp-native-x64 xp_evidence_summary smoke_commands cli_launch must include exactly one "
        "--os-service-pack SP2, got ['SP1']"
    ) in errors
    assert (
        "windows-xp-native-x64 xp_evidence_summary smoke_commands cli_launch must include exactly one "
        "--os-edition Professional x64 Edition, got ['Ultimate']"
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


def test_platform_verified_evidence_rejects_placeholder_xp_security_patch_summary() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["xp_evidence_summary"]["security"]["patch_evidence"]["security_update_channel"] = "test-security"
    record["xp_evidence_summary"]["security"]["patch_evidence"]["cve_review_reference"] = "TODO"
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x86 xp_evidence_summary security.patch_evidence.security_update_channel "
        "must name concrete non-placeholder provenance"
    ) in errors
    assert (
        "windows-xp-native-x86 xp_evidence_summary security.patch_evidence.cve_review_reference "
        "must name concrete non-placeholder provenance"
    ) in errors


def test_platform_verified_evidence_rejects_reserved_https_xp_security_patch_summary() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    record["xp_evidence_summary"]["security"]["patch_evidence"][
        "security_update_channel"
    ] = "https://example.com/security-updates/windows-xp"
    record["xp_evidence_summary"]["security"]["patch_evidence"][
        "cve_review_reference"
    ] = "https://example.com/security-advisory/CVE-2026-0001"
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x86 xp_evidence_summary security.patch_evidence.security_update_channel "
        "must name concrete non-placeholder provenance"
    ) in errors
    assert (
        "windows-xp-native-x86 xp_evidence_summary security.patch_evidence.cve_review_reference "
        "must name concrete non-placeholder provenance"
    ) in errors


def test_platform_verified_evidence_rejects_generic_https_xp_security_patch_cve_reference() -> None:
    checker = _load_platform_verified_evidence_checker()
    record = _xp_record("windows-xp-native-x86")
    patch_evidence = record["xp_evidence_summary"]["security"]["patch_evidence"]
    assert isinstance(patch_evidence, dict)
    patch_evidence["security_update_channel"] = "vendor-security-updates-2026-07"
    patch_evidence["cve_review_reference"] = "https://security.vendor.com/releases/2026-07"
    registry = {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [record],
    }

    errors = checker.check_platform_verified_evidence(registry=registry)

    assert (
        "windows-xp-native-x86 xp_evidence_summary security.patch_evidence.cve_review_reference "
        "must name concrete non-placeholder provenance"
    ) in errors


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
    assets_dir = f"staged/{target}/v1.0.2/artifacts"
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
            f"--target {target} --workflow-run-url https://github.com/example/remote-ops-workspace/actions/runs/12345 "
            f"--workflow-run-attempt 1 --source-head-sha {'a' * 40} "
            f"--builder-evidence evidence/{target}/v1.0.2/builder-identity-{target}.json"
        ),
        "linux_smoke_evidence_sha256": linux_smoke_hashes,
        "linux_smoke_summary": _linux_smoke_summary(target),
        "local_evidence_preflight_command": (
            "python scripts/check_platform_goal_local_evidence.py --root . "
            f"--release-tag v1.0.2 --target {target} --assets-dir {assets_dir} "
            f"--linux-builder-evidence evidence/{target}/v1.0.2/builder-identity-{target}.json "
            f"--linux-smoke-evidence evidence/{target}/v1.0.2/native-smoke-{target}.log "
            "--linux-workflow-run-url https://github.com/example/remote-ops-workspace/actions/runs/12345 "
            f"--linux-source-head-sha {'a' * 40} "
            "--linux-source-run-attempt 1"
        ),
        "staged_upload_command": (
            "python scripts/stage_extended_linux_evidence_upload.py "
            f"--target {target} --release-tag v1.0.2 --source-dir {assets_dir} "
            f"--out-dir platform-evidence-upload/{target}/v1.0.2 --force"
        ),
        "artifact_validation_command": (
            f"python scripts/check_platform_promotion_artifacts.py --target {target} "
            f"--assets-dir {assets_dir} --tag v1.0.2 --strict"
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
        "finalized_record_release_asset_url": (
            f"https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/"
            f"platform-verified-evidence-{target}-final.json"
        ),
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
        "local_evidence_preflight_command": (
            "python scripts/check_platform_goal_local_evidence.py --root . "
            f"--release-tag {release_tag} --target {target} --assets-dir {assets_dir} "
            f"--xp-evidence {evidence_file} --xp-evidence-dir {evidence_dir} "
            "--xp-source-workflow-run-url https://github.com/example/remote-ops-workspace/actions/runs/12345 "
            f"--xp-source-head-sha {'a' * 40} "
            "--xp-source-run-attempt 1"
        ),
        "staged_upload_command": (
            "python scripts/stage_xp_native_evidence_upload.py "
            f"--target {target} --release-tag {release_tag} --assets-dir {assets_dir} "
            f"--evidence-output-dir xp-evidence-output/{target}/{release_tag} "
            f"--out-dir platform-evidence-upload/{target}/{release_tag} --force"
        ),
        "artifact_validation_command": (
            f"python scripts/check_platform_promotion_artifacts.py --target {target} "
            f"--assets-dir {assets_dir} --tag {release_tag} --strict"
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
        "finalized_record_release_asset_url": (
            f"{base_url}/platform-verified-evidence-{target}-final.json"
        ),
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
        "run_attempt": 1,
        "contains_files": sorted(contains_files),
    }


def _release_source_workflow(target: str) -> str:
    if target.startswith("linux-"):
        return ".github/workflows/extended-platform-evidence.yml"
    return ".github/workflows/xp-native-evidence.yml"


def _linux_smoke_hashes() -> dict[str, str]:
    return {"native_smoke": "6" * 64}


def _linux_smoke_summary(target: str, release_tag: str = "v1.0.2") -> dict[str, object]:
    machine = "i686" if target == "linux-i386" else "armv7l"
    dpkg_arch = "i386" if target == "linux-i386" else "armhf"
    target_arch = "i386" if target == "linux-i386" else "armhf"
    return {
        "target": target,
        "release_tag": release_tag,
        "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "workflow_run_attempt": 1,
        "source_head_sha": "a" * 40,
        "git_head_sha": "a" * 40,
        "target_arch": target_arch,
        "host_label": f"{target}-builder",
        "evidence_run_id": f"{target}-{release_tag.removeprefix('v').replace('.', '-')}-run-12345",
        "observed_at_utc": "2026-06-20T12:00:00Z",
        "uname_machine": machine,
        "dpkg_architecture": dpkg_arch,
        "userland_bits": "32",
        "os_release": "Debian GNU/Linux 12 (bookworm)",
        "kernel_release": "6.1.0-i386-ci",
        "glibc_version": "glibc 2.36",
        "python_ssl_openssl": "OpenSSL 3.0.13",
        "openssl_cli_version": "OpenSSL 3.0.13",
        "security": {
            "tls_minimum_modern_profiles": "TLS 1.2",
            "tls_preferred_modern_profiles": "TLS 1.3",
            "legacy_compatibility_profile": "isolated-opt-in",
            "legacy_crypto_scope": "profile-only",
            "weak_crypto_global_default": False,
            "modern_defaults_unchanged": True,
            "security_update_channel": "vendor-security-updates-2026-06",
            "cve_review_reference": "vendor-cve-advisory-review-2026-06",
        },
    }


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
    if isinstance(record.get("finalized_record_release_asset_url"), str):
        record["finalized_record_release_asset_url"] = str(
            record["finalized_record_release_asset_url"]
        ).replace(old, new)
    review_bundle = record.get("review_bundle")
    if isinstance(review_bundle, dict):
        review_bundle["release_asset_urls"] = [
            str(url).replace(old, new)
            for url in review_bundle.get("release_asset_urls", [])
        ]


def _replace_release_source_head(record: dict[str, object], head_sha: str) -> None:
    source = record.get("release_asset_source")
    old_head = ""
    if isinstance(source, dict):
        old_head = str(source.get("head_sha", ""))
        source["head_sha"] = head_sha
    if isinstance(record.get("local_evidence_preflight_command"), str) and old_head:
        record["local_evidence_preflight_command"] = str(
            record["local_evidence_preflight_command"]
        ).replace(old_head, head_sha)
    xp_summary = record.get("xp_evidence_summary")
    if isinstance(xp_summary, dict):
        xp_source = xp_summary.get("release_source")
        if isinstance(xp_source, dict):
            xp_source["head_sha"] = head_sha
        smoke_commands = xp_summary.get("smoke_commands")
        if isinstance(smoke_commands, dict) and old_head:
            for smoke_id, command in smoke_commands.items():
                smoke_commands[smoke_id] = str(command).replace(old_head, head_sha)
    if not str(record.get("target", "")).startswith("linux-"):
        return
    builder_identity = record.get("builder_identity")
    if isinstance(builder_identity, dict):
        if old_head and isinstance(builder_identity.get("workflow_ref"), str):
            builder_identity["workflow_ref"] = str(builder_identity["workflow_ref"]).replace(
                old_head,
                head_sha,
            )
        builder_identity["workflow_sha"] = head_sha
        builder_identity["source_head_sha"] = head_sha
        builder_identity["observed_git_head_sha"] = head_sha
        builder_identity_sha = _json_sha256(builder_identity)
        record["builder_identity_sha256"] = builder_identity_sha
        linux_sources = record.get("linux_evidence_sources")
        if isinstance(linux_sources, dict) and isinstance(linux_sources.get("builder_identity"), dict):
            linux_sources["builder_identity"]["sha256"] = builder_identity_sha
    linux_smoke_summary = record.get("linux_smoke_summary")
    if isinstance(linux_smoke_summary, dict):
        linux_smoke_summary["source_head_sha"] = head_sha
        linux_smoke_summary["git_head_sha"] = head_sha
    for field in ("native_smoke_command", "local_evidence_preflight_command"):
        if isinstance(record.get(field), str) and old_head:
            record[field] = str(record[field]).replace(old_head, head_sha)


def _replace_release_source_run_attempt(record: dict[str, object], run_attempt: int) -> None:
    source = record.get("release_asset_source")
    old_attempt = ""
    if isinstance(source, dict):
        old_attempt = str(source.get("run_attempt", ""))
        source["run_attempt"] = run_attempt
    if isinstance(record.get("local_evidence_preflight_command"), str) and old_attempt:
        record["local_evidence_preflight_command"] = str(
            record["local_evidence_preflight_command"]
        ).replace(f"-source-run-attempt {old_attempt}", f"-source-run-attempt {run_attempt}")
    xp_summary = record.get("xp_evidence_summary")
    if isinstance(xp_summary, dict):
        xp_source = xp_summary.get("release_source")
        if isinstance(xp_source, dict):
            xp_source["run_attempt"] = run_attempt
        smoke_commands = xp_summary.get("smoke_commands")
        if isinstance(smoke_commands, dict) and old_attempt:
            for smoke_id, command in smoke_commands.items():
                smoke_commands[smoke_id] = str(command).replace(
                    f"--source-run-attempt {old_attempt}",
                    f"--source-run-attempt {run_attempt}",
                )
    if not str(record.get("target", "")).startswith("linux-"):
        return
    builder_identity = record.get("builder_identity")
    if isinstance(builder_identity, dict):
        builder_identity["workflow_run_attempt"] = run_attempt
        host_identity = builder_identity.get("host_identity")
        if isinstance(host_identity, dict):
            host_identity["workflow_run_attempt"] = run_attempt
        builder_identity_sha = _json_sha256(builder_identity)
        record["builder_identity_sha256"] = builder_identity_sha
        linux_sources = record.get("linux_evidence_sources")
        if isinstance(linux_sources, dict) and isinstance(linux_sources.get("builder_identity"), dict):
            linux_sources["builder_identity"]["sha256"] = builder_identity_sha
    linux_smoke_summary = record.get("linux_smoke_summary")
    if isinstance(linux_smoke_summary, dict):
        linux_smoke_summary["workflow_run_attempt"] = run_attempt
    for field in ("native_smoke_command", "local_evidence_preflight_command"):
        if isinstance(record.get(field), str) and old_attempt:
            record[field] = str(record[field]).replace(
                f"run-attempt {old_attempt}",
                f"run-attempt {run_attempt}",
            )


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
        "release_source": _xp_release_source_summary(target),
        "security": {
            "legacy_crypto_profile_scoped": True,
            "modern_defaults_unchanged": True,
            "weak_crypto_global_default": False,
            "patch_evidence": _xp_security_patch_evidence(),
        },
        "smoke_ids": sorted(_xp_smoke_hashes()),
        "smoke_evidence_files": _xp_smoke_evidence_files(),
        "smoke_commands": _xp_smoke_commands(target, release_tag),
    }


def _xp_release_source_summary(target: str) -> dict[str, object]:
    return {
        "workflow": _release_source_workflow(target),
        "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "head_sha": "a" * 40,
        "run_attempt": 1,
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
    host_identity = _xp_host_identity(target, release_tag)
    os_identity = host_identity["os"]
    assert isinstance(os_identity, dict)
    release_source = _xp_release_source_summary(target)
    security = _xp_security_patch_evidence()
    return {
        smoke_id: (
            f"scripts/xp_smoke_runner.cmd --target {target} --release-tag {release_tag} "
            f"--smoke-id {smoke_id} --evidence-file xp-smoke-evidence/{smoke_id}.txt "
            f"--proof-file xp-smoke-proof/{smoke_id}.txt "
            f"--host-label {host_identity['host_label']} "
            f"--evidence-run-id {host_identity['evidence_run_id']} "
            f"--observed-at-utc {host_identity['observed_at_utc']} "
            f"--source-workflow-run-url {release_source['workflow_run_url']} "
            f"--source-head-sha {release_source['head_sha']} "
            f"--source-run-attempt {release_source['run_attempt']} "
            f"--security-update-channel {security['security_update_channel']} "
            f"--cve-review-reference {security['cve_review_reference']} "
            f'--os-name "{os_identity["name"]}" '
            f"--os-architecture {os_identity['architecture']} "
            f"--os-service-pack {os_identity['service_pack']}"
            + (
                f' --os-edition "{os_identity["edition"]}"'
                if "edition" in os_identity
                else ""
            )
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
        "workflow_run_attempt": 1,
        "workflow_ref": (
            "example/remote-ops-workspace/.github/workflows/"
            f"extended-platform-evidence.yml@{'a' * 40}"
        ),
        "workflow_sha": "a" * 40,
        "source_head_sha": "a" * 40,
        "observed_git_head_sha": "a" * 40,
        "git_worktree_clean": True,
        "host_identity": _linux_host_identity(target),
        "sudo_non_interactive": True,
        "sys_platform": "linux",
        "platform_machine": machine,
        "uname_machine": machine,
        "dpkg_architecture": dpkg_arch,
        "userland_bits": "32",
        "os_release": "Debian GNU/Linux 12 (bookworm)",
        "kernel_release": "6.1.0-i386-ci",
        "glibc_version": "glibc 2.36",
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
        "workflow_run_attempt": 1,
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
        "security_update_channel": "vendor-security-updates-2026-06",
        "cve_review_reference": "vendor-cve-advisory-review-2026-06",
    }


def _xp_security_patch_evidence() -> dict[str, object]:
    return {
        "tls_minimum_modern_profiles": "TLS 1.2",
        "tls_preferred_modern_profiles": "TLS 1.3",
        "legacy_compatibility_profile": "isolated-opt-in",
        "cve_patch_reviewed": True,
        "security_update_channel": "vendor-security-updates-2026-06",
        "cve_review_reference": "vendor-cve-advisory-review-2026-06",
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

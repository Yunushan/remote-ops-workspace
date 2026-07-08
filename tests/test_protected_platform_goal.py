from __future__ import annotations

import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path

import pytest

LINUX_SECURITY_REQUIREMENTS = [
    "security patch evidence proving TLS 1.3 preferred, TLS 1.2 minimum, "
    "isolated legacy compatibility and CVE patch review with concrete "
    "security_update_channel and cve_review_reference update/advisory provenance",
    "modern Windows 10/11, Linux, and macOS defaults must keep hardened crypto",
]


def test_protected_platform_goal_reports_empty_registry_without_promotion() -> None:
    checker = _load_protected_goal_checker()

    errors, goal = checker.check_protected_platform_goal(registry=_empty_registry())

    assert errors == []
    assert goal["current_percent"] == 0.0
    assert goal["accepted_target_count"] == 0
    assert goal["target_count"] == 4
    assert goal["complete"] is False
    assert goal["status"] == "missing-accepted-evidence"
    assert goal["missing_targets"] == [
        "linux-i386",
        "linux-armhf",
        "windows-xp-native-x86",
        "windows-xp-native-x64",
    ]


def test_protected_platform_goal_strict_gate_fails_empty_registry() -> None:
    checker = _load_protected_goal_checker()

    errors, goal = checker.check_protected_platform_goal(
        registry=_empty_registry(),
        release_tag="v1.0.2",
        require_records_complete=True,
    )

    assert goal["release_tag"] == "v1.0.2"
    assert goal["current_percent"] == 0.0
    requirements = {
        item["target"]: item for item in goal["target_evidence_requirements"]
    }
    assert requirements["linux-i386"]["required_release_tag"] == "v1.0.2"
    assert requirements["linux-i386"]["accepted_evidence_record"]["release_tag"] == "v1.0.2"
    assert "artifact_validation_command" in requirements["linux-i386"]["required_commands"]
    assert "local_evidence_preflight_command" in requirements["linux-i386"]["required_commands"]
    assert "finalized_evidence_record_command" in requirements["linux-i386"]["required_commands"]
    linux_source = requirements["linux-i386"]["release_asset_source_required"]
    assert linux_source["workflow"] == ".github/workflows/extended-platform-evidence.yml"
    assert linux_source["artifact_name"] == "extended-linux-evidence-linux-i386-v1.0.2"
    assert linux_source["run_attempt"] == "positive GitHub Actions run attempt matching release source"
    assert "platform-verified-evidence-linux-i386-final.json" in linux_source["contains_files"]
    assert requirements["linux-i386"]["workflow_dispatch_command"] == (
        "gh workflow run extended-platform-evidence.yml --repo <owner>/<repo> "
        "--ref v1.0.2 -f target=linux-i386 "
        "-f release_tag=v1.0.2 "
        "-f release_asset_base_url=<github-release-download-url>"
    )
    xp_source = requirements["windows-xp-native-x64"]["release_asset_source_required"]
    assert xp_source["workflow"] == ".github/workflows/xp-native-evidence.yml"
    assert xp_source["artifact_name"] == "xp-native-evidence-windows-xp-native-x64-v1.0.2"
    assert xp_source["run_attempt"] == "positive GitHub Actions run attempt matching release source"
    assert "platform-verified-evidence-windows-xp-native-x64-final.json" in xp_source["contains_files"]
    assert requirements["windows-xp-native-x64"]["workflow_dispatch_command"] == (
        "gh workflow run xp-native-evidence.yml --repo <owner>/<repo> "
        "--ref v1.0.2 -f target=windows-xp-native-x64 "
        "-f release_tag=v1.0.2 "
        "-f release_asset_base_url=<github-release-download-url> "
        "-f assets_dir=<target-release-artifact-dir> "
        "-f evidence_file=<target-release-evidence.json> "
        "-f evidence_dir=<target-release-evidence-dir>"
    )
    assert goal["release_import_dry_run_command"] == (
        "python scripts/import_platform_evidence_artifacts.py "
        "--release-tag v1.0.2 --require-goal-targets "
        "--out-dir <release-assets-dir> --dry-run --verify-source-run "
        "--repository <owner>/<repo>"
    )
    assert goal["remote_release_evidence_audit_command"] == (
        "python scripts/check_platform_release_evidence_remote.py "
        "--repository <owner>/<repo> --release-tag v1.0.2 "
        "--require-goal-targets --require-source-runs "
        "--require-source-artifact-bytes --require-final-record-bytes "
        "--require-release-asset-bytes --require-tag-source-head"
    )
    assert goal["release_asset_provenance_command"] == (
        "python scripts/check_protected_platform_goal.py "
        "--release-tag v1.0.2 --require-complete --assets-dir <release-assets-dir> "
        "--repository <owner>/<repo>"
    )
    assert requirements["linux-i386"]["security_requirements"] == LINUX_SECURITY_REQUIREMENTS
    assert requirements["linux-armhf"]["security_requirements"] == LINUX_SECURITY_REQUIREMENTS
    assert requirements["windows-xp-native-x64"]["builder_or_host_evidence"].startswith(
        "Windows XP Professional x64 Edition SP2"
    )
    assert requirements["windows-xp-native-x64"]["security_requirements"] == [
        "legacy TLS, SSH, and RDP compatibility must remain profile-scoped opt-in",
        "XP security patch evidence must include concrete security_update_channel "
        "and cve_review_reference update/advisory provenance",
        "modern Windows 10/11, Linux, and macOS defaults must keep hardened crypto",
    ]
    human_scope = checker.format_goal_scope(goal)
    assert "release scope: requires one release_tag, one GitHub release repository" in human_scope
    assert "per-target release source workflow files" in human_scope
    assert "per-record release source run attempts" in human_scope
    assert "without conflicting attempts for one run URL" in human_scope
    assert (
        "pre-release import dry-run: python scripts/import_platform_evidence_artifacts.py "
        "--release-tag v1.0.2 --require-goal-targets "
        "--out-dir <release-assets-dir> --dry-run --verify-source-run "
        "--repository <owner>/<repo>"
    ) in human_scope
    assert (
        "published release evidence audit: "
        "python scripts/check_platform_release_evidence_remote.py "
        "--repository <owner>/<repo> --release-tag v1.0.2 "
        "--require-goal-targets --require-source-runs "
        "--require-source-artifact-bytes --require-final-record-bytes "
        "--require-release-asset-bytes --require-tag-source-head"
    ) in human_scope
    assert "accepted release scope evidence: none" in human_scope
    human_requirements = checker.format_goal_requirements(goal)
    assert "required proof for missing targets:" in human_requirements
    assert "linux-i386: missing" in human_requirements
    assert "release_tag=v1.0.2 status=accepted readiness=100.0" in human_requirements
    assert "release proof: 6 artifacts, 3 review-bundle files" in human_requirements
    assert (
        "source workflow: .github/workflows/extended-platform-evidence.yml; "
        "artifact=extended-linux-evidence-linux-i386-v1.0.2"
    ) in human_requirements
    assert (
        "dispatch command: gh workflow run extended-platform-evidence.yml "
        "--repo <owner>/<repo> --ref v1.0.2 "
        "-f target=linux-i386 -f release_tag=v1.0.2 "
        "-f release_asset_base_url=<github-release-download-url>"
    ) in human_requirements
    assert (
        "dispatch command: gh workflow run xp-native-evidence.yml "
        "--repo <owner>/<repo> --ref v1.0.2 "
        "-f target=windows-xp-native-x64 -f release_tag=v1.0.2 "
        "-f release_asset_base_url=<github-release-download-url> "
        "-f assets_dir=<target-release-artifact-dir> "
        "-f evidence_file=<target-release-evidence.json> "
        "-f evidence_dir=<target-release-evidence-dir>"
    ) in human_requirements
    assert "commands: accepted_evidence_candidate_command, artifact_validation_command" in human_requirements
    assert "    command templates:" in human_requirements
    assert (
        "artifact_validation_command: python scripts/check_platform_promotion_artifacts.py "
        "--target linux-i386"
    ) in human_requirements
    assert (
        "local_evidence_preflight_command: python scripts/check_platform_goal_local_evidence.py "
        "--root . --release-tag v1.0.2 --target linux-i386"
    ) in human_requirements
    assert (
        "native_evidence_validation_command: python scripts/check_xp_native_evidence.py "
        "--evidence <target-release-evidence.json>"
    ) in human_requirements
    assert "    smoke evidence:" in human_requirements
    assert (
        "- capture native smoke log with target, release tag, workflow run URL, "
        "workflow run attempt, source head SHA and observed git HEAD SHA"
    ) in human_requirements
    assert (
        "bind sanitized host label, deterministic evidence run ID and observed-at UTC timestamp "
        "into the native smoke log"
    ) in human_requirements
    assert (
        "consume matching builder identity evidence during native smoke and bind host identity "
        "plus security provenance from it"
    ) in human_requirements
    assert "verify AppImage install, verify, upgrade and uninstall" in human_requirements
    assert "- launch CLI without unsupported Windows APIs" in human_requirements
    assert "validate artifact manifest and SHA256SUMS on the Windows XP host before collector upload" in human_requirements
    assert LINUX_SECURITY_REQUIREMENTS[0] in human_requirements
    assert (
        "builder/host: Windows XP Professional x64 Edition SP2 VM or physical host "
        "running scripts/xp_smoke_runner.cmd and artifact validation; collector: "
        "modern self-hosted xp-evidence collector with Python 3.12 and GitHub Actions support"
    ) in human_requirements
    assert "modern Windows 10/11, Linux, and macOS defaults must keep hardened crypto" in human_requirements
    assert any(
        "missing required accepted evidence targets for release_tag v1.0.2" in error
        for error in errors
    )
    assert any("protected platform goal is incomplete" in error for error in errors)
    assert any(
        "missing required accepted evidence targets for release_tag v1.0.2" in error
        for error in goal["validation_errors"]
    )
    assert goal["record_validation_errors"] == []
    assert goal["blocking_errors"] == errors


def test_protected_platform_goal_records_gate_requires_release_tag() -> None:
    checker = _load_protected_goal_checker()

    errors, goal = checker.check_protected_platform_goal(
        registry=_complete_registry(),
        require_records_complete=True,
    )

    assert checker.REQUIRE_RECORDS_COMPLETE_RELEASE_TAG_ERROR in errors
    assert goal["current_percent"] == 0.0
    assert goal["accepted_target_count"] == 0
    assert goal["complete"] is False
    assert goal["record_complete"] is False
    assert goal["release_backed_complete"] is False
    assert goal["completion_requires_release_asset_provenance"] is True
    assert goal["completion_evidence"] == "incomplete"
    assert goal["status"] == "release-tag-required"
    assert goal["scope_error"] == checker.REQUIRE_RECORDS_COMPLETE_RELEASE_TAG_ERROR
    assert goal["validation_errors"] == []
    assert goal["record_validation_errors"] == []
    assert goal["blocking_errors"] == errors
    assert goal["missing_targets"] == [
        "linux-i386",
        "linux-armhf",
        "windows-xp-native-x86",
        "windows-xp-native-x64",
    ]


def test_protected_platform_goal_rejects_drifted_requirement_command_metadata(
    monkeypatch,
) -> None:
    checker = _load_protected_goal_checker()
    original_readiness = checker._platform_verified_readiness

    def fake_platform_verified_readiness(*args, **kwargs):
        report = original_readiness(*args, **kwargs)
        drifted = deepcopy(report)
        requirements = drifted["protected_goal_parity"]["target_evidence_requirements"]
        linux_i386 = next(item for item in requirements if item["target"] == "linux-i386")
        linux_i386["required_commands"]["staged_upload_command"] = linux_i386[
            "required_commands"
        ]["staged_upload_command"].replace(
            "stage_extended_linux_evidence_upload.py",
            "stage_linux_upload.py",
        )
        return drifted

    monkeypatch.setattr(checker, "_platform_verified_readiness", fake_platform_verified_readiness)

    errors, goal = checker.check_protected_platform_goal(
        registry=_complete_registry(),
        release_tag="v1.0.2",
        require_records_complete=True,
    )

    assert any(
        "linux-i386 protected platform requirement staged_upload_command must be"
        in error
        for error in errors
    )
    assert goal["complete"] is False
    assert goal["status"] == "requirement-metadata-invalid"
    assert goal["requirement_metadata_complete"] is False
    assert goal["requirement_metadata_error_count"] == 1
    assert goal["report_validation_errors"] == [
        error for error in errors if "staged_upload_command must be" in error
    ]
    assert "protected platform goal is incomplete: status=requirement-metadata-invalid" in errors


def test_protected_platform_goal_rejects_malformed_release_scope_metadata(
    monkeypatch,
) -> None:
    checker = _load_protected_goal_checker()
    original_readiness = checker._platform_verified_readiness
    conflict_url = "https://github.com/example/remote-ops-workspace/actions/runs/12345"

    def fake_platform_verified_readiness(*args, **kwargs):
        report = original_readiness(*args, **kwargs)
        drifted = deepcopy(report)
        goal = drifted["protected_goal_parity"]
        goal["release_tags"].append(True)
        goal["release_repositories"].append("EXAMPLE/REMOTE-OPS-WORKSPACE")
        goal["release_source_workflows"]["LINUX-I386"] = goal["release_source_workflows"]["linux-i386"]
        goal["release_source_workflows"]["linux-armhf"] = False
        goal["selected_release_source_workflows"] = {"linux-i386": ""}
        goal["release_source_run_urls"]["windows-xp-native-x86"] = []
        goal["selected_release_source_run_urls"] = {"linux-i386": True}
        goal["release_source_run_attempts"][False] = 1
        goal["release_source_run_attempts"]["linux-armhf"] = 0
        goal["selected_release_source_run_attempts"] = {"linux-i386": True}
        goal["release_source_run_attempt_conflicts"] = {
            False: {"linux-i386": 1},
            conflict_url: {"linux-i386": 1, "linux-armhf": False, True: 2},
        }
        return drifted

    monkeypatch.setattr(checker, "_platform_verified_readiness", fake_platform_verified_readiness)

    errors, goal = checker.check_protected_platform_goal(
        registry=_complete_registry(),
        release_tag="v1.0.2",
        require_records_complete=True,
    )

    assert "protected platform goal parity release_tags entries must be non-empty strings, got True" in errors
    assert any(
        "protected platform goal parity release_repositories must not collide on "
        "case-insensitive filesystems" in error
        and "example/remote-ops-workspace" in error
        and "EXAMPLE/REMOTE-OPS-WORKSPACE" in error
        for error in errors
    )
    assert any(
        "protected platform goal parity release_source_workflows keys must not collide on "
        "case-insensitive filesystems" in error
        and "linux-i386" in error
        and "LINUX-I386" in error
        for error in errors
    )
    assert (
        "protected platform goal parity release_source_run_attempts keys must be "
        "non-empty strings, got False"
    ) in errors
    assert (
        "protected platform goal parity release_source_workflows.linux-armhf "
        "must be a non-empty string, got False"
    ) in errors
    assert (
        "protected platform goal parity selected_release_source_workflows.linux-i386 "
        "must be a non-empty string, got ''"
    ) in errors
    assert (
        "protected platform goal parity release_source_run_urls.windows-xp-native-x86 "
        "must be a non-empty string, got []"
    ) in errors
    assert (
        "protected platform goal parity selected_release_source_run_urls.linux-i386 "
        "must be a non-empty string, got True"
    ) in errors
    assert (
        "protected platform goal parity release_source_run_attempts.linux-armhf "
        "must be a positive integer, got 0"
    ) in errors
    assert (
        "protected platform goal parity selected_release_source_run_attempts.linux-i386 "
        "must be a positive integer, got True"
    ) in errors
    assert (
        "protected platform goal parity release_source_run_attempt_conflicts keys must be "
        "non-empty strings, got False"
    ) in errors
    assert (
        "protected platform goal parity "
        f"release_source_run_attempt_conflicts.{conflict_url} keys must be "
        "non-empty strings, got True"
    ) in errors
    assert (
        "protected platform goal parity "
        f"release_source_run_attempt_conflicts.{conflict_url}.linux-armhf "
        "must be a positive integer, got False"
    ) in errors
    assert goal["complete"] is False
    assert goal["status"] == "requirement-metadata-invalid"
    assert goal["requirement_metadata_error_count"] >= 13
    assert "protected platform goal is incomplete: status=requirement-metadata-invalid" in errors


def test_protected_platform_goal_rejects_drifted_percentage_metadata(
    monkeypatch,
) -> None:
    checker = _load_protected_goal_checker()
    original_readiness = checker._platform_verified_readiness

    def fake_platform_verified_readiness(*args, **kwargs):
        report = original_readiness(*args, **kwargs)
        drifted = deepcopy(report)
        goal = drifted["protected_goal_parity"]
        goal["current_percent"] = 75.0
        goal["gap_percent"] = 0.0
        return drifted

    monkeypatch.setattr(checker, "_platform_verified_readiness", fake_platform_verified_readiness)

    errors, goal = checker.check_protected_platform_goal(
        registry=_complete_registry(),
        release_tag="v1.0.2",
        require_records_complete=True,
    )

    assert (
        "protected platform goal parity current_percent must match "
        "4/4 accepted targets (100.0), got 75.0"
    ) in errors
    assert (
        "protected platform goal parity gap_percent must equal "
        "100.0-current_percent (25.0), got 0.0"
    ) in errors
    assert goal["complete"] is False
    assert goal["status"] == "requirement-metadata-invalid"
    assert goal["requirement_metadata_error_count"] >= 2
    assert "protected platform goal is incomplete: status=requirement-metadata-invalid" in errors


def test_protected_platform_goal_rejects_drifted_requirement_target_set(
    monkeypatch,
) -> None:
    checker = _load_protected_goal_checker()
    original_readiness = checker._platform_verified_readiness

    def fake_platform_verified_readiness(*args, **kwargs):
        report = original_readiness(*args, **kwargs)
        drifted = deepcopy(report)
        requirements = drifted["protected_goal_parity"]["target_evidence_requirements"]
        requirements[0]["accepted"] = False
        requirements[1]["target"] = "linux-i386"
        return drifted

    monkeypatch.setattr(checker, "_platform_verified_readiness", fake_platform_verified_readiness)

    errors, goal = checker.check_protected_platform_goal(
        registry=_complete_registry(),
        release_tag="v1.0.2",
        require_records_complete=True,
    )

    assert (
        "protected platform goal parity requirement targets contain duplicates: ['linux-i386']"
        in errors
    )
    assert "protected platform goal parity requirement targets missing: ['linux-armhf']" in errors
    assert "linux-i386 protected platform requirement accepted must match accepted_targets" in errors
    assert goal["complete"] is False
    assert goal["status"] == "requirement-metadata-invalid"
    assert "protected platform goal is incomplete: status=requirement-metadata-invalid" in errors


def test_protected_platform_goal_rejects_malformed_requirement_target_without_stringifying(
    monkeypatch,
) -> None:
    checker = _load_protected_goal_checker()
    original_readiness = checker._platform_verified_readiness

    def fake_platform_verified_readiness(*args, **kwargs):
        report = original_readiness(*args, **kwargs)
        drifted = deepcopy(report)
        requirements = drifted["protected_goal_parity"]["target_evidence_requirements"]
        linux_i386 = next(item for item in requirements if item["target"] == "linux-i386")
        linux_i386["target"] = True
        linux_armhf = next(item for item in requirements if item["target"] == "linux-armhf")
        linux_armhf["required_commands"][False] = "python scripts/fake.py"
        return drifted

    monkeypatch.setattr(checker, "_platform_verified_readiness", fake_platform_verified_readiness)

    errors, goal = checker.check_protected_platform_goal(
        registry=_complete_registry(),
        release_tag="v1.0.2",
        require_records_complete=True,
    )

    assert (
        "protected platform goal parity requirement target must be a non-empty string, "
        "got True"
    ) in errors
    assert (
        "linux-armhf protected platform requirement required_commands keys "
        "must be non-empty strings, got [False]"
    ) in errors
    assert not any("True protected platform requirement" in error for error in errors)
    assert not any("required_commands has unexpected keys: ['False']" in error for error in errors)
    assert goal["complete"] is False
    assert goal["status"] == "requirement-metadata-invalid"
    assert "protected platform goal is incomplete: status=requirement-metadata-invalid" in errors


def test_protected_platform_goal_rejects_malformed_release_tag() -> None:
    checker = _load_protected_goal_checker()

    errors, goal = checker.check_protected_platform_goal(
        registry=_empty_registry(),
        release_tag="latest",
    )

    assert goal["release_tag"] == "latest"
    assert "release_tag must look like vX.Y.Z: latest" in errors
    assert goal["blocking_errors"] == errors


def test_protected_platform_goal_rejects_non_string_release_tag_before_asset_check(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checker = _load_protected_goal_checker()

    def fail_release_asset_check(*_args, **_kwargs):
        raise AssertionError("release asset checker must not run for non-string release_tag")

    monkeypatch.setattr(checker, "check_release_assets", fail_release_asset_check)

    errors, goal = checker.check_protected_platform_goal(
        registry=_complete_registry(),
        release_tag=True,
        require_complete=True,
        assets_dir=tmp_path,
        repository="example/remote-ops-workspace",
    )

    assert "release_tag must be a string, got True" in errors
    assert "required_release_tag must be a string, got True" in errors
    assert (
        "protected platform goal is incomplete: missing linux-i386, linux-armhf, "
        "windows-xp-native-x86, windows-xp-native-x64"
    ) in errors
    assert goal["complete"] is False
    assert goal["record_complete"] is False
    assert goal["release_backed_complete"] is False
    assert goal["status"] == "release-tag-invalid"
    assert goal["scope_error"] == "release_tag must be a string, got True"
    assert goal["release_asset_provenance_complete"] is False
    assert goal["release_assets_dir"] == str(tmp_path)
    assert goal["blocking_errors"] == errors


def test_protected_platform_goal_assets_dir_requires_strict_completion(tmp_path: Path) -> None:
    checker = _load_protected_goal_checker()
    args = checker.parse_args(
        ["--release-tag", "v1.0.2", "--assets-dir", str(tmp_path)]
    )

    assert checker.strict_completion_arg_errors(args) == [
        checker.REQUIRE_ASSETS_COMPLETE_ERROR
    ]


def test_protected_platform_goal_complete_gate_requires_assets_dir() -> None:
    checker = _load_protected_goal_checker()
    args = checker.parse_args(["--release-tag", "v1.0.2", "--require-complete"])

    assert checker.strict_completion_arg_errors(args) == [
        checker.REQUIRE_COMPLETE_ASSETS_DIR_ERROR,
        checker.REQUIRE_COMPLETE_REPOSITORY_ERROR,
    ]


def test_protected_platform_goal_complete_gate_requires_repository(tmp_path: Path) -> None:
    checker = _load_protected_goal_checker()
    args = checker.parse_args(
        ["--release-tag", "v1.0.2", "--require-complete", "--assets-dir", str(tmp_path)]
    )

    assert checker.strict_completion_arg_errors(args) == [
        checker.REQUIRE_COMPLETE_REPOSITORY_ERROR
    ]


def test_protected_platform_goal_rejects_non_path_assets_dir_argument(tmp_path: Path) -> None:
    checker = _load_protected_goal_checker()
    args = checker.parse_args(
        [
            "--release-tag",
            "v1.0.2",
            "--require-complete",
            "--assets-dir",
            str(tmp_path),
            "--repository",
            "example/remote-ops-workspace",
        ]
    )
    args.assets_dir = True

    assert checker.strict_completion_arg_errors(args) == [
        "release assets directory path must be a pathlib.Path, got True"
    ]


def test_protected_platform_goal_completion_modes_are_mutually_exclusive(tmp_path: Path) -> None:
    checker = _load_protected_goal_checker()
    args = checker.parse_args(
        [
            "--release-tag",
            "v1.0.2",
            "--require-complete",
            "--require-records-complete",
            "--assets-dir",
            str(tmp_path),
            "--repository",
            "example/remote-ops-workspace",
        ]
    )

    assert checker.REQUIRE_COMPLETE_MODE_CONFLICT_ERROR in checker.strict_completion_arg_errors(args)


def test_protected_platform_goal_assets_dir_validation_blocks_completion(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checker = _load_protected_goal_checker()
    registry = _complete_registry()
    calls = []

    def fake_check_release_assets(
        assets_dir,
        matrix,
        *,
        tag,
        repository,
        evidence_registry,
        require_platform_goal_targets,
        **_kwargs,
    ):
        calls.append(
            {
                "assets_dir": assets_dir,
                "matrix": matrix,
                "tag": tag,
                "repository": repository,
                "same_registry": evidence_registry is registry,
                "require_platform_goal_targets": require_platform_goal_targets,
            }
        )
        return ["release asset sentinel failure"]

    monkeypatch.setattr(checker, "read_release_matrix", lambda: {"matrix": "sentinel"})
    monkeypatch.setattr(checker, "check_release_assets", fake_check_release_assets)

    errors, goal = checker.check_protected_platform_goal(
        registry=registry,
        release_tag="v1.0.2",
        require_complete=True,
        assets_dir=tmp_path,
        repository="example/remote-ops-workspace",
    )

    assert calls == [
        {
            "assets_dir": tmp_path,
            "matrix": {"matrix": "sentinel"},
            "tag": "v1.0.2",
            "repository": "example/remote-ops-workspace",
            "same_registry": True,
            "require_platform_goal_targets": True,
        }
    ]
    assert errors == ["release asset sentinel failure"]
    assert goal["complete"] is False
    assert goal["record_complete"] is True
    assert goal["release_backed_complete"] is False
    assert goal["completion_evidence"] == "release-assets-invalid"
    assert goal["status"] == "release-assets-invalid"
    assert goal["release_asset_provenance_complete"] is False
    assert goal["release_asset_error_count"] == 1
    assert goal["release_asset_validation_errors"] == ["release asset sentinel failure"]
    assert goal["release_assets_dir"] == str(tmp_path)
    assert goal["blocking_errors"] == errors


def test_protected_platform_goal_assets_dir_success_marks_release_asset_provenance(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checker = _load_protected_goal_checker()
    registry = _complete_registry()
    calls = []

    def fake_check_release_assets(
        assets_dir,
        matrix,
        *,
        tag,
        repository,
        evidence_registry,
        require_platform_goal_targets,
        **_kwargs,
    ):
        calls.append(
            {
                "assets_dir": assets_dir,
                "matrix": matrix,
                "tag": tag,
                "repository": repository,
                "same_registry": evidence_registry is registry,
                "require_platform_goal_targets": require_platform_goal_targets,
            }
        )
        return []

    monkeypatch.setattr(checker, "read_release_matrix", lambda: {"matrix": "sentinel"})
    monkeypatch.setattr(checker, "check_release_assets", fake_check_release_assets)

    errors, goal = checker.check_protected_platform_goal(
        registry=registry,
        release_tag="v1.0.2",
        require_complete=True,
        assets_dir=tmp_path,
        repository="example/remote-ops-workspace",
    )

    assert errors == []
    assert calls == [
        {
            "assets_dir": tmp_path,
            "matrix": {"matrix": "sentinel"},
            "tag": "v1.0.2",
            "repository": "example/remote-ops-workspace",
            "same_registry": True,
            "require_platform_goal_targets": True,
        }
    ]
    assert goal["complete"] is True
    assert goal["record_complete"] is True
    assert goal["release_backed_complete"] is True
    assert goal["completion_evidence"] == "release-assets"
    assert goal["status"] == "complete"
    assert goal["release_asset_provenance_complete"] is True
    assert goal["release_asset_error_count"] == 0
    assert goal["release_asset_validation_errors"] == []
    assert goal["release_assets_dir"] == str(tmp_path)
    assert "release asset provenance: complete" in checker.format_goal_scope(goal)


def test_protected_platform_goal_rejects_non_path_assets_dir_before_release_check(
    monkeypatch,
) -> None:
    checker = _load_protected_goal_checker()

    def fail_release_asset_check(*_args, **_kwargs):
        raise AssertionError("release asset checker must not run for non-Path assets_dir")

    monkeypatch.setattr(checker, "check_release_assets", fail_release_asset_check)

    errors, goal = checker.check_protected_platform_goal(
        registry=_complete_registry(),
        release_tag="v1.0.2",
        require_complete=True,
        assets_dir=True,
        repository="example/remote-ops-workspace",
    )

    assert errors == ["release assets directory path must be a pathlib.Path, got True"]
    assert goal["complete"] is False
    assert goal["record_complete"] is True
    assert goal["release_backed_complete"] is False
    assert goal["status"] == "release-assets-invalid"
    assert goal["release_asset_provenance_complete"] is False
    assert goal["release_asset_validation_errors"] == errors
    assert goal["release_assets_dir"] == ""


def test_protected_platform_goal_reports_release_scoped_completion() -> None:
    checker = _load_protected_goal_checker()

    errors, goal = checker.check_protected_platform_goal(
        registry=_complete_registry(),
        release_tag="v1.0.2",
        require_records_complete=True,
    )

    assert errors == []
    assert goal["release_tag"] == "v1.0.2"
    assert goal["current_percent"] == 100.0
    assert goal["accepted_target_count"] == 4
    assert goal["missing_targets"] == []
    assert goal["complete"] is False
    assert goal["record_complete"] is True
    assert goal["release_backed_complete"] is False
    assert goal["completion_requires_release_asset_provenance"] is True
    assert goal["completion_evidence"] == "accepted-records-only"
    assert goal["status"] == "release-asset-provenance-required"
    assert goal["release_asset_provenance_complete"] is False
    assert goal["release_asset_validation_errors"] == []
    assert goal["release_assets_dir"] == ""
    human_scope = checker.format_goal_scope(goal)
    assert "accepted release tags: v1.0.2" in human_scope
    assert "accepted release repositories: example/remote-ops-workspace" in human_scope
    assert f"accepted release source heads: {'a' * 40}" in human_scope
    assert (
        "accepted release source workflows: "
        "linux-armhf=.github/workflows/extended-platform-evidence.yml, "
        "linux-i386=.github/workflows/extended-platform-evidence.yml"
    ) in human_scope
    assert (
        "windows-xp-native-x64=.github/workflows/xp-native-evidence.yml, "
        "windows-xp-native-x86=.github/workflows/xp-native-evidence.yml"
    ) in human_scope
    assert "accepted release source run URLs: linux-armhf=https://github.com/example/remote-ops-workspace/actions/runs/12345" in human_scope
    assert "windows-xp-native-x86=https://github.com/example/remote-ops-workspace/actions/runs/12345" in human_scope
    assert "accepted release source run attempts: linux-armhf=1, linux-i386=1" in human_scope
    assert "windows-xp-native-x64=1, windows-xp-native-x86=1" in human_scope
    assert (
        "pre-release import dry-run: python scripts/import_platform_evidence_artifacts.py "
        "--release-tag v1.0.2 --require-goal-targets "
        "--out-dir <release-assets-dir> --dry-run --verify-source-run "
        "--repository <owner>/<repo>"
    ) in human_scope
    assert (
        "release asset provenance gate: python scripts/check_protected_platform_goal.py "
        "--release-tag v1.0.2 --require-complete --assets-dir <release-assets-dir> "
        "--repository example/remote-ops-workspace"
    ) in human_scope
    assert (
        "release-backed completion: pending release asset validation with --assets-dir"
    ) in human_scope


def test_protected_platform_goal_strict_gate_does_not_count_malformed_accepted_record() -> None:
    checker = _load_protected_goal_checker()
    registry = _complete_registry()
    records = registry["accepted_evidence"]
    assert isinstance(records, list)
    first_record = records[0]
    assert isinstance(first_record, dict)
    del first_record["review_bundle"]

    errors, goal = checker.check_protected_platform_goal(
        registry=registry,
        release_tag="v1.0.2",
        require_records_complete=True,
    )

    assert any("linux-i386 review_bundle must be an object" in error for error in errors)
    assert any("protected platform goal is incomplete" in error for error in errors)
    assert goal["release_tag"] == "v1.0.2"
    assert goal["current_percent"] == 0.0
    assert goal["accepted_target_count"] == 0
    assert goal["accepted_targets"] == []
    assert goal["complete"] is False
    assert goal["status"] == "missing-accepted-evidence"
    assert any(
        "linux-i386 review_bundle must be an object" in error
        for error in goal["validation_errors"]
    )
    assert any(
        "linux-i386 review_bundle must be an object" in error
        for error in goal["record_validation_errors"]
    )
    assert goal["blocking_errors"] == errors


def test_protected_platform_goal_strict_gate_does_not_count_duplicate_target_records() -> None:
    checker = _load_protected_goal_checker()
    registry = _complete_registry()
    records = registry["accepted_evidence"]
    assert isinstance(records, list)
    first_record = records[0]
    assert isinstance(first_record, dict)
    records.append(deepcopy(first_record))

    errors, goal = checker.check_protected_platform_goal(
        registry=registry,
        release_tag="v1.0.2",
        require_records_complete=True,
    )

    assert "accepted_evidence target must be unique: linux-i386" in errors
    assert any("protected platform goal is incomplete" in error for error in errors)
    assert goal["release_tag"] == "v1.0.2"
    assert goal["current_percent"] == 0.0
    assert goal["accepted_target_count"] == 0
    assert goal["accepted_targets"] == []
    assert goal["missing_targets"] == [
        "linux-i386",
        "linux-armhf",
        "windows-xp-native-x86",
        "windows-xp-native-x64",
    ]
    assert goal["complete"] is False
    assert goal["status"] == "missing-accepted-evidence"
    assert "accepted_evidence target must be unique: linux-i386" in goal["validation_errors"]
    assert "accepted_evidence target must be unique: linux-i386" in goal["record_validation_errors"]
    assert goal["blocking_errors"] == errors


def test_protected_platform_goal_duplicate_check_ignores_non_string_targets() -> None:
    checker = _load_protected_goal_checker()
    registry = _complete_registry()
    records = registry["accepted_evidence"]
    assert isinstance(records, list)
    malformed_record = {
        "target": True,
        "status": "accepted",
        "readiness_percent": 100.0,
        "release_tag": "v1.0.2",
    }
    records.append(deepcopy(malformed_record))
    records.append(deepcopy(malformed_record))

    errors, goal = checker.check_protected_platform_goal(
        registry=registry,
        release_tag="v1.0.2",
        require_records_complete=True,
    )

    assert any("accepted_evidence target must be a string, got True" in error for error in errors)
    assert not any("accepted_evidence target must be unique: True" in error for error in errors)
    assert not any(
        "accepted_evidence target must be unique: True" in error
        for error in goal["record_validation_errors"]
    )
    assert goal["current_percent"] == 0.0
    assert goal["accepted_targets"] == []
    assert goal["status"] == "missing-accepted-evidence"


def test_protected_platform_goal_report_does_not_count_unfinalized_candidate() -> None:
    checker = _load_protected_goal_checker()
    registry = _complete_registry()
    records = registry["accepted_evidence"]
    assert isinstance(records, list)
    first_record = records[0]
    assert isinstance(first_record, dict)
    del first_record["review_bundle"]
    del first_record["finalized_record_release_asset_url"]
    release_source = first_record["release_asset_source"]
    artifact_hashes = first_record["artifact_sha256"]
    assert isinstance(release_source, dict)
    assert isinstance(artifact_hashes, dict)
    release_source["contains_files"] = sorted(str(name) for name in artifact_hashes)

    errors, goal = checker.check_protected_platform_goal(
        registry=registry,
        release_tag="v1.0.2",
    )

    assert any("linux-i386 finalized_record_release_asset_url must be set" in error for error in errors)
    assert any("linux-i386 review_bundle must be an object" in error for error in errors)
    assert goal["release_tag"] == "v1.0.2"
    assert goal["current_percent"] == 0.0
    assert goal["accepted_target_count"] == 0
    assert goal["accepted_targets"] == []
    assert goal["complete"] is False
    assert goal["status"] == "missing-accepted-evidence"
    assert any(
        "linux-i386 finalized_record_release_asset_url must be set" in error
        for error in goal["validation_errors"]
    )
    assert any(
        "linux-i386 review_bundle must be an object" in error
        for error in goal["record_validation_errors"]
    )
    assert goal["blocking_errors"] == errors


def test_protected_platform_goal_human_scope_reports_mixed_release_source_heads() -> None:
    checker = _load_protected_goal_checker()
    fixtures = _load_platform_verified_evidence_fixtures()
    registry = _complete_registry()
    records = registry["accepted_evidence"]
    assert isinstance(records, list)
    linux_i386 = records[0]
    assert isinstance(linux_i386, dict)
    fixtures._replace_release_source_head(linux_i386, "b" * 40)

    errors, goal = checker.check_protected_platform_goal(
        registry=registry,
        release_tag="v1.0.2",
        require_records_complete=True,
    )

    assert goal["status"] == "mixed-release-source-evidence"
    assert goal["accepted_target_count"] == 3
    assert goal["aggregate_accepted_target_count"] == 4
    human_scope = checker.format_goal_scope(goal)
    assert "accepted in selected release scope: 3/4; aggregate accepted records: 4/4" in human_scope
    assert f"accepted release source heads: {'a' * 40}, {'b' * 40}" in human_scope
    assert "selected release source run attempts: linux-armhf=1" in human_scope
    assert "windows-xp-native-x64=1, windows-xp-native-x86=1" in human_scope
    assert "aggregate accepted release source run attempts: linux-armhf=1, linux-i386=1" in human_scope
    assert any("must use one release source head SHA" in error for error in errors)


def test_protected_platform_goal_human_scope_reports_source_attempt_conflicts() -> None:
    checker = _load_protected_goal_checker()

    human_scope = checker.format_goal_scope(
        {
            "target_count": 4,
            "accepted_target_count": 4,
            "aggregate_accepted_target_count": 4,
            "release_tags": ["v1.0.2"],
            "release_repositories": ["example/remote-ops-workspace"],
            "release_source_heads": ["a" * 40],
            "release_source_workflows": {
                "linux-i386": ".github/workflows/extended-platform-evidence.yml",
                "windows-xp-native-x86": ".github/workflows/xp-native-evidence.yml",
            },
            "release_source_run_urls": {
                "linux-i386": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
                "windows-xp-native-x86": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
            },
            "release_source_run_attempts": {
                "linux-i386": 1,
                "windows-xp-native-x86": 2,
            },
            "release_source_run_attempt_conflicts": {
                "https://github.com/example/remote-ops-workspace/actions/runs/12345": {
                    "linux-i386": 1,
                    "windows-xp-native-x86": 2,
                }
            },
        }
    )

    assert "accepted release source run URLs: linux-i386=https://github.com/example/remote-ops-workspace/actions/runs/12345" in human_scope
    assert (
        "conflicting release source run attempts: "
        "https://github.com/example/remote-ops-workspace/actions/runs/12345: "
        "linux-i386=1, windows-xp-native-x86=2"
    ) in human_scope


def test_protected_platform_goal_filters_nonmatching_release_tag() -> None:
    checker = _load_protected_goal_checker()

    errors, goal = checker.check_protected_platform_goal(
        registry=_complete_registry(),
        release_tag="v1.0.3",
    )

    assert errors == []
    assert goal["release_tag"] == "v1.0.3"
    assert goal["current_percent"] == 0.0
    assert goal["accepted_targets"] == []
    assert goal["missing_targets"] == [
        "linux-i386",
        "linux-armhf",
        "windows-xp-native-x86",
        "windows-xp-native-x64",
    ]


def test_protected_platform_goal_cli_requires_release_tag_for_completion(tmp_path: Path) -> None:
    checker = _load_protected_goal_checker()
    registry = tmp_path / "platform_verified_evidence.json"
    registry.write_text(json.dumps(_empty_registry()), encoding="utf-8")

    assert checker.main(["--registry", str(registry), "--require-complete"]) == 2


def test_protected_platform_goal_rejects_reserved_registry_path() -> None:
    checker = _load_protected_goal_checker()
    registry = Path(".github") / "platform_verified_evidence.json"
    args = checker.parse_args(
        [
            "--registry",
            str(registry),
            "--release-tag",
            "v1.0.2",
        ]
    )

    errors = checker.strict_completion_arg_errors(args)

    assert errors == [
        "accepted evidence registry must not point inside reserved workspace directory "
        f"'.github': {registry}"
    ]


def test_protected_platform_goal_rejects_non_path_registry_argument() -> None:
    checker = _load_protected_goal_checker()
    args = checker.parse_args(["--release-tag", "v1.0.2"])
    args.registry = "configs/platform_verified_evidence.json"

    errors = checker.strict_completion_arg_errors(args)

    assert errors == [
        "accepted evidence registry path must be a pathlib.Path, "
        "got 'configs/platform_verified_evidence.json'"
    ]


def test_protected_platform_goal_path_helpers_reject_non_path_args() -> None:
    checker = _load_protected_goal_checker()

    assert checker.check_registry_path("configs/platform_verified_evidence.json") == [
        "accepted evidence registry path must be a pathlib.Path, "
        "got 'configs/platform_verified_evidence.json'"
    ]
    assert checker.check_assets_dir_path("release-assets") == [
        "release assets directory path must be a pathlib.Path, got 'release-assets'"
    ]
    assert checker.check_path_parent_symlinks(
        "configs/platform_verified_evidence.json",
        "accepted evidence registry",
    ) == [
        "accepted evidence registry path must be a pathlib.Path, "
        "got 'configs/platform_verified_evidence.json'"
    ]
    assert checker.check_path_not_reserved_workspace_root(
        "configs/platform_verified_evidence.json",
        "accepted evidence registry",
    ) == [
        "accepted evidence registry path must be a pathlib.Path, "
        "got 'configs/platform_verified_evidence.json'"
    ]


def test_protected_platform_goal_rejects_symlinked_registry_file(tmp_path: Path) -> None:
    checker = _load_protected_goal_checker()
    registry = tmp_path / "platform_verified_evidence.json"
    registry.write_text(json.dumps(_empty_registry()), encoding="utf-8")
    linked_registry = tmp_path / "linked-registry.json"
    try:
        linked_registry.symlink_to(registry)
    except OSError as exc:
        pytest.skip(f"file symlinks unavailable on this platform: {exc}")
    args = checker.parse_args(["--registry", str(linked_registry)])

    errors = checker.strict_completion_arg_errors(args)

    assert errors == [f"accepted evidence registry must not be a symlink: {linked_registry}"]


def test_protected_platform_goal_rejects_registry_parent_symlink(tmp_path: Path) -> None:
    checker = _load_protected_goal_checker()
    registry_dir = tmp_path / "registry-dir"
    registry_dir.mkdir()
    registry = registry_dir / "platform_verified_evidence.json"
    registry.write_text(json.dumps(_empty_registry()), encoding="utf-8")
    linked_dir = tmp_path / "linked-registry-dir"
    try:
        linked_dir.symlink_to(registry_dir, target_is_directory=True)
    except OSError as exc:
        pytest.skip(f"directory symlinks unavailable on this platform: {exc}")
    linked_registry = linked_dir / "platform_verified_evidence.json"
    args = checker.parse_args(["--registry", str(linked_registry)])

    errors = checker.strict_completion_arg_errors(args)

    assert errors == [
        f"accepted evidence registry path must not contain symlinked directories: {linked_dir}"
    ]


def _empty_registry() -> dict[str, object]:
    fixtures = _load_platform_verified_evidence_fixtures()
    return {
        "schema_version": 1,
        "policy": fixtures.POLICY,
        "accepted_evidence": [],
    }


def _complete_registry() -> dict[str, object]:
    fixtures = _load_platform_verified_evidence_fixtures()
    return {
        "schema_version": 1,
        "policy": fixtures.POLICY,
        "accepted_evidence": [
            fixtures._linux_record("linux-i386"),
            fixtures._linux_record("linux-armhf"),
            fixtures._xp_record("windows-xp-native-x86"),
            fixtures._xp_record("windows-xp-native-x64"),
        ],
    }


def _load_protected_goal_checker():
    return _load_module("check_protected_platform_goal", Path("scripts/check_protected_platform_goal.py"))


def _load_platform_verified_evidence_fixtures():
    return _load_module("platform_verified_evidence_fixtures", Path("tests/test_platform_verified_evidence.py"))


def _load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

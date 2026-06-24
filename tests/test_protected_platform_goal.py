from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

LINUX_SECURITY_REQUIREMENTS = [
    "security patch evidence proving TLS 1.3 preferred, TLS 1.2 minimum, "
    "isolated legacy compatibility and CVE patch review",
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
        require_complete=True,
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
    xp_source = requirements["windows-xp-native-x64"]["release_asset_source_required"]
    assert xp_source["workflow"] == ".github/workflows/xp-native-evidence.yml"
    assert xp_source["artifact_name"] == "xp-native-evidence-windows-xp-native-x64-v1.0.2"
    assert xp_source["run_attempt"] == "positive GitHub Actions run attempt matching release source"
    assert "platform-verified-evidence-windows-xp-native-x64-final.json" in xp_source["contains_files"]
    assert requirements["linux-i386"]["security_requirements"] == LINUX_SECURITY_REQUIREMENTS
    assert requirements["linux-armhf"]["security_requirements"] == LINUX_SECURITY_REQUIREMENTS
    assert requirements["windows-xp-native-x64"]["builder_or_host_evidence"].startswith(
        "Windows XP Professional x64 Edition SP2"
    )
    assert requirements["windows-xp-native-x64"]["security_requirements"] == [
        "legacy TLS, SSH, and RDP compatibility must remain profile-scoped opt-in",
        "modern Windows 10/11, Linux, and macOS defaults must keep hardened crypto",
    ]
    human_scope = checker.format_goal_scope(goal)
    assert "release scope: requires one release_tag, one GitHub release repository" in human_scope
    assert "per-target release source workflow files" in human_scope
    assert "per-record release source run attempts" in human_scope
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
    assert "commands: accepted_evidence_candidate_command, artifact_validation_command" in human_requirements
    assert "    smoke evidence:" in human_requirements
    assert (
        "- capture native smoke log with target, release tag, workflow run URL, "
        "workflow run attempt, source head SHA and observed git HEAD SHA"
    ) in human_requirements
    assert (
        "bind sanitized host label, deterministic evidence run ID and observed-at UTC timestamp "
        "into the native smoke log"
    ) in human_requirements
    assert "verify AppImage install, verify, upgrade and uninstall" in human_requirements
    assert "- launch CLI without unsupported Windows APIs" in human_requirements
    assert "validate artifact manifest and SHA256SUMS on the XP evidence host" in human_requirements
    assert LINUX_SECURITY_REQUIREMENTS[0] in human_requirements
    assert "builder/host: Windows XP Professional x64 Edition SP2 VM" in human_requirements
    assert "modern Windows 10/11, Linux, and macOS defaults must keep hardened crypto" in human_requirements
    assert any(
        "missing required accepted evidence targets for release_tag v1.0.2" in error
        for error in errors
    )
    assert any("protected platform goal is incomplete" in error for error in errors)


def test_protected_platform_goal_strict_gate_requires_release_tag() -> None:
    checker = _load_protected_goal_checker()

    errors, goal = checker.check_protected_platform_goal(
        registry=_complete_registry(),
        require_complete=True,
    )

    assert checker.REQUIRE_COMPLETE_RELEASE_TAG_ERROR in errors
    assert goal["current_percent"] == 0.0
    assert goal["accepted_target_count"] == 0
    assert goal["complete"] is False
    assert goal["status"] == "release-tag-required"
    assert goal["scope_error"] == checker.REQUIRE_COMPLETE_RELEASE_TAG_ERROR
    assert goal["missing_targets"] == [
        "linux-i386",
        "linux-armhf",
        "windows-xp-native-x86",
        "windows-xp-native-x64",
    ]


def test_protected_platform_goal_rejects_malformed_release_tag() -> None:
    checker = _load_protected_goal_checker()

    errors, goal = checker.check_protected_platform_goal(
        registry=_empty_registry(),
        release_tag="latest",
    )

    assert goal["release_tag"] == "latest"
    assert "release_tag must look like vX.Y.Z: latest" in errors


def test_protected_platform_goal_reports_release_scoped_completion() -> None:
    checker = _load_protected_goal_checker()

    errors, goal = checker.check_protected_platform_goal(
        registry=_complete_registry(),
        release_tag="v1.0.2",
        require_complete=True,
    )

    assert errors == []
    assert goal["release_tag"] == "v1.0.2"
    assert goal["current_percent"] == 100.0
    assert goal["accepted_target_count"] == 4
    assert goal["missing_targets"] == []
    assert goal["complete"] is True
    assert goal["status"] == "complete"
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
    assert "accepted release source run attempts: linux-armhf=1, linux-i386=1" in human_scope
    assert "windows-xp-native-x64=1, windows-xp-native-x86=1" in human_scope


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
        require_complete=True,
    )

    assert any("linux-i386 review_bundle must be an object" in error for error in errors)
    assert any("protected platform goal is incomplete" in error for error in errors)
    assert goal["release_tag"] == "v1.0.2"
    assert goal["current_percent"] == 0.0
    assert goal["accepted_target_count"] == 0
    assert goal["accepted_targets"] == []
    assert goal["complete"] is False
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
        require_complete=True,
    )

    assert goal["status"] == "mixed-release-source-evidence"
    assert goal["accepted_target_count"] == 3
    assert goal["aggregate_accepted_target_count"] == 4
    human_scope = checker.format_goal_scope(goal)
    assert "accepted in selected release scope: 3/4; aggregate accepted records: 4/4" in human_scope
    assert f"accepted release source heads: {'a' * 40}, {'b' * 40}" in human_scope
    assert any("must use one release source head SHA" in error for error in errors)


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

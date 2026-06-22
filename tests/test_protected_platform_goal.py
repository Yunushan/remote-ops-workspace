from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


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
    assert requirements["windows-xp-native-x64"]["builder_or_host_evidence"].startswith(
        "Windows XP Professional x64 Edition SP2"
    )
    assert requirements["windows-xp-native-x64"]["security_requirements"] == [
        "legacy TLS, SSH, and RDP compatibility must remain profile-scoped opt-in",
        "modern Windows 10/11, Linux, and macOS defaults must keep hardened crypto",
    ]
    human_requirements = checker.format_goal_requirements(goal)
    assert "required proof for missing targets:" in human_requirements
    assert "linux-i386: missing" in human_requirements
    assert "release_tag=v1.0.2 status=accepted readiness=100.0" in human_requirements
    assert "release proof: 6 artifacts, 3 review-bundle files" in human_requirements
    assert "commands: accepted_evidence_candidate_command, artifact_validation_command" in human_requirements
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

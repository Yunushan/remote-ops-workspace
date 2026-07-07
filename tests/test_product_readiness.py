import importlib.util
import json
import sys
from copy import deepcopy
from pathlib import Path


def load_product_readiness_checker():
    path = Path("scripts/check_product_readiness.py")
    spec = importlib.util.spec_from_file_location("check_product_readiness", path)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load check_product_readiness.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules["check_product_readiness"] = module
    spec.loader.exec_module(module)
    return module


def test_product_readiness_checker_passes_current_tree() -> None:
    checker = load_product_readiness_checker()
    assert checker.main() == 0


def test_product_readiness_rejects_invalid_platform_evidence_registry(tmp_path: Path) -> None:
    checker = load_product_readiness_checker()
    registry = json.loads(Path("configs/platform_verified_evidence.json").read_text(encoding="utf-8"))
    registry["policy"] = registry["policy"].replace(
        "review-bundle manifest release asset URL binding, ",
        "",
    )
    registry_path = tmp_path / "platform_verified_evidence.json"
    registry_path.write_text(json.dumps(registry, indent=2) + "\n", encoding="utf-8")
    original_path = checker.platform_evidence_checker.EVIDENCE_PATH
    checker.platform_evidence_checker.EVIDENCE_PATH = registry_path
    try:
        errors = checker.check_product_readiness()
    finally:
        checker.platform_evidence_checker.EVIDENCE_PATH = original_path

    assert (
        "platform verified evidence registry: platform verified evidence policy must require "
        "review-bundle manifest release asset URL binding"
    ) in errors


def test_product_readiness_rejects_missing_protected_goal_release_source_heads(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    del report["platform_verified_readiness"]["protected_goal_parity"]["release_source_heads"]
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert "protected platform goal parity must expose release_source_heads" in errors


def test_product_readiness_rejects_missing_platform_denominator(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    del report["platform_verified_readiness"]["denominator"]
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert "platform verified readiness must expose structured denominator" in errors


def test_product_readiness_rejects_platform_denominator_target_drift(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    denominator = report["platform_verified_readiness"]["denominator"]
    denominator["included_targets"] = []
    denominator["release_asset_provenance_in_static_score"] = True
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert "platform verified readiness denominator included_targets must match verified rows" in errors
    assert "platform verified readiness denominator must keep release asset provenance outside static score" in errors


def test_product_readiness_rejects_platform_protected_goal_summary_drift(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    platform = report["platform_verified_readiness"]
    platform["denominator"]["protected_goal_current_percent"] = 100.0
    platform["overall"]["protected_goal_status"] = "complete"
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert (
        "platform verified readiness denominator protected_goal_current_percent "
        "must match protected_goal_parity"
    ) in errors
    assert (
        "platform verified readiness overall protected_goal_status "
        "must match protected_goal_parity"
    ) in errors


def test_product_readiness_rejects_missing_protected_goal_release_source_run_attempts(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    del report["platform_verified_readiness"]["protected_goal_parity"]["release_source_run_attempts"]
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert "protected platform goal parity must expose release_source_run_attempts" in errors


def test_product_readiness_rejects_missing_protected_goal_release_source_workflows(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    del report["platform_verified_readiness"]["protected_goal_parity"]["release_source_workflows"]
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert "protected platform goal parity must expose release_source_workflows" in errors


def test_product_readiness_rejects_missing_protected_goal_release_source_run_urls(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    del report["platform_verified_readiness"]["protected_goal_parity"]["release_source_run_urls"]
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert "protected platform goal parity must expose release_source_run_urls" in errors


def test_product_readiness_rejects_missing_protected_goal_selected_release_source_maps(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    goal = report["platform_verified_readiness"]["protected_goal_parity"]
    del goal["selected_release_source_run_attempts"]
    del goal["selected_release_source_run_urls"]
    del goal["selected_release_source_workflows"]
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert "protected platform goal parity must expose selected_release_source_run_attempts" in errors
    assert "protected platform goal parity must expose selected_release_source_run_urls" in errors
    assert "protected platform goal parity must expose selected_release_source_workflows" in errors


def test_product_readiness_rejects_missing_protected_goal_selected_release_scope_exclusions(
    monkeypatch,
) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    goal = report["platform_verified_readiness"]["protected_goal_parity"]
    del goal["selected_release_scope_exclusions"]
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert "protected platform goal parity must expose selected_release_scope_exclusions" in errors


def test_product_readiness_rejects_selected_release_source_maps_outside_scope(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    goal = report["platform_verified_readiness"]["protected_goal_parity"]
    goal["selected_release_source_run_attempts"] = {"linux-i386": 1}
    goal["selected_release_source_run_urls"] = {
        "linux-i386": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
    }
    goal["selected_release_source_workflows"] = {
        "linux-i386": ".github/workflows/extended-platform-evidence.yml",
    }
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert (
        "protected platform goal parity selected_release_source_run_attempts "
        "contains targets outside selected release scope: ['linux-i386']"
    ) in errors
    assert (
        "protected platform goal parity selected_release_source_run_urls "
        "contains targets outside selected release scope: ['linux-i386']"
    ) in errors
    assert (
        "protected platform goal parity selected_release_source_workflows "
        "contains targets outside selected release scope: ['linux-i386']"
    ) in errors


def test_product_readiness_rejects_malformed_goal_target_lists_without_stringifying(
    monkeypatch,
) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    goal = report["platform_verified_readiness"]["protected_goal_parity"]
    required = list(goal["required_targets"])
    goal["accepted_targets"] = [True]
    goal["missing_targets"] = required
    goal["accepted_target_count"] = 1
    goal["aggregate_accepted_targets"] = [True]
    goal["aggregate_missing_targets"] = required
    goal["aggregate_accepted_target_count"] = 1
    goal["selected_release_source_run_attempts"] = {"True": 1}
    goal["selected_release_source_run_urls"] = {
        "True": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
    }
    goal["selected_release_source_workflows"] = {
        "True": ".github/workflows/extended-platform-evidence.yml",
    }
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert (
        "protected platform goal parity accepted_targets entries must be "
        "non-empty strings, got True"
    ) in errors
    assert (
        "protected platform goal parity aggregate_accepted_targets entries must be "
        "non-empty strings, got True"
    ) in errors
    assert (
        "protected platform goal parity selected_release_source_run_attempts "
        "contains targets outside selected release scope: ['True']"
    ) in errors
    assert (
        "protected platform goal parity selected_release_source_run_urls "
        "contains targets outside selected release scope: ['True']"
    ) in errors
    assert (
        "protected platform goal parity selected_release_source_workflows "
        "contains targets outside selected release scope: ['True']"
    ) in errors


def test_product_readiness_rejects_inconsistent_selected_release_scope_exclusions(
    monkeypatch,
) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    goal = report["platform_verified_readiness"]["protected_goal_parity"]
    goal["aggregate_accepted_targets"] = ["linux-i386"]
    goal["aggregate_missing_targets"] = [
        "linux-armhf",
        "windows-xp-native-x86",
        "windows-xp-native-x64",
    ]
    goal["aggregate_accepted_target_count"] = 1
    goal["selected_release_scope_exclusions"] = {}
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert (
        "protected platform goal parity selected_release_scope_exclusions "
        "must match aggregate accepted targets outside selected release scope: ['linux-i386']"
    ) in errors

    goal["selected_release_scope_exclusions"] = {"linux-i386": []}
    errors = checker.check_product_readiness()
    assert (
        "protected platform goal parity selected_release_scope_exclusions[linux-i386] "
        "must be a non-empty list of reason strings"
    ) in errors


def test_product_readiness_rejects_missing_protected_goal_release_source_provenance_flag(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    del report["platform_verified_readiness"]["protected_goal_parity"][
        "release_source_provenance_complete"
    ]
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert "protected platform goal parity must expose release_source_provenance_complete" in errors


def test_product_readiness_rejects_missing_protected_goal_release_asset_provenance_flag(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    del report["platform_verified_readiness"]["protected_goal_parity"][
        "release_asset_provenance_complete"
    ]
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert "protected platform goal parity must expose release_asset_provenance_complete" in errors


def test_product_readiness_rejects_static_release_asset_provenance_claim(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    goal = report["platform_verified_readiness"]["protected_goal_parity"]
    goal["release_asset_provenance_complete"] = True
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert (
        "protected platform goal parity release_asset_provenance_complete must be false "
        "in the static readiness report; use the asset-backed protected goal gate"
    ) in errors


def test_product_readiness_rejects_static_protected_row_release_asset_claim(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    linux_i386 = next(
        row
        for row in report["platform_verified_readiness"]["targets"]
        if row["target"] == "linux-i386"
    )
    linux_i386["release_asset_provenance_complete"] = True
    linux_i386["release_backed_readiness_complete"] = True
    linux_i386["static_readiness_evidence_scope"] = "accepted evidence"
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert (
        "linux-i386 protected platform row must keep release_asset_provenance_complete false "
        "in the static readiness report"
    ) in errors
    assert (
        "linux-i386 protected platform row must keep release_backed_readiness_complete false "
        "in the static readiness report"
    ) in errors
    assert (
        "linux-i386 protected platform row static_readiness_evidence_scope must mention --assets-dir"
        in errors
    )


def test_product_readiness_rejects_missing_protected_goal_release_asset_provenance_command(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    del report["platform_verified_readiness"]["protected_goal_parity"][
        "release_asset_provenance_command"
    ]
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert "protected platform goal parity must expose release_asset_provenance_command" in errors


def test_product_readiness_rejects_missing_protected_goal_release_import_dry_run_command(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    del report["platform_verified_readiness"]["protected_goal_parity"][
        "release_import_dry_run_command"
    ]
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert "protected platform goal parity must expose release_import_dry_run_command" in errors


def test_product_readiness_rejects_weak_protected_goal_release_import_dry_run_command(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    goal = report["platform_verified_readiness"]["protected_goal_parity"]
    goal["release_import_dry_run_command"] = (
        "python scripts/import_platform_evidence_artifacts.py --help"
    )
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert any(
        error.startswith(
            "protected platform goal parity release_import_dry_run_command must be"
        )
        and "--require-goal-targets" in error
        and "--dry-run" in error
        and "--verify-source-run" in error
        for error in errors
    )


def test_product_readiness_rejects_weak_protected_goal_release_asset_provenance_command(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    goal = report["platform_verified_readiness"]["protected_goal_parity"]
    goal["release_asset_provenance_command"] = (
        "python scripts/check_protected_platform_goal.py --require-complete"
    )
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert any(
        error.startswith(
            "protected platform goal parity release_asset_provenance_command must be"
        )
        and "--release-tag v<project.version>" in error
        and "--require-complete" in error
        and "--assets-dir <release-assets-dir>" in error
        for error in errors
    )


def test_product_readiness_rejects_inconsistent_protected_goal_release_source_provenance_flag(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    goal = report["platform_verified_readiness"]["protected_goal_parity"]
    goal["release_source_provenance_complete"] = True
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert (
        "protected platform goal parity release_source_provenance_complete must match "
        "required target run-attempt, run URL, workflow and conflict coverage"
    ) in errors


def test_product_readiness_rejects_inconsistent_source_run_attempt_conflict_map(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    goal = report["platform_verified_readiness"]["protected_goal_parity"]
    goal["release_source_run_urls"] = {
        "linux-i386": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "windows-xp-native-x86": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
    }
    goal["release_source_run_attempts"] = {
        "linux-i386": 1,
        "windows-xp-native-x86": 2,
    }
    goal["release_source_run_attempt_conflicts"] = {}
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert (
        "protected platform goal parity release_source_run_attempt_conflicts must match "
        "release source run URLs and attempts"
    ) in errors


def test_product_readiness_rejects_inconsistent_protected_goal_status(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    goal = report["platform_verified_readiness"]["protected_goal_parity"]
    goal["status"] = "complete"
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert (
        "protected platform goal parity status must be missing-accepted-evidence"
        in errors
    )


def test_product_readiness_rejects_inconsistent_protected_goal_target_count(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    goal = report["platform_verified_readiness"]["protected_goal_parity"]
    goal["target_count"] = 99
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert (
        "protected platform goal parity target_count must match required_targets"
        in errors
    )


def test_product_readiness_rejects_inconsistent_protected_goal_gap(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    goal = report["platform_verified_readiness"]["protected_goal_parity"]
    goal["gap_percent"] = 0.0
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert (
        "protected platform goal parity gap_percent must match accepted target count"
        in errors
    )


def test_product_readiness_rejects_complete_status_without_release_source_provenance(
    monkeypatch,
) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    goal = report["platform_verified_readiness"]["protected_goal_parity"]
    required = list(goal["required_targets"])
    goal["accepted_targets"] = required
    goal["missing_targets"] = []
    goal["accepted_target_count"] = len(required)
    goal["aggregate_accepted_targets"] = required
    goal["aggregate_missing_targets"] = []
    goal["aggregate_accepted_target_count"] = len(required)
    goal["current_percent"] = 100.0
    goal["release_source_provenance_complete"] = False
    goal["complete"] = False
    goal["status"] = "complete"
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert (
        "protected platform goal parity status must be missing-release-source-provenance"
        in errors
    )


def test_product_readiness_rejects_weak_linux_protected_goal_support_boundary(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    requirements = report["platform_verified_readiness"]["protected_goal_parity"][
        "target_evidence_requirements"
    ]
    linux_i386 = next(item for item in requirements if item["target"] == "linux-i386")
    linux_i386["support_boundary"] = "linux-i386 is fully native-ready."
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert (
        "linux-i386 protected platform requirement support_boundary missing: "
        "['remains manual-script-supported', 'manual-script-native', "
        "'until accepted builder, artifact, smoke and release evidence exists']"
    ) in errors


def test_product_readiness_rejects_weak_xp_protected_goal_support_boundary(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    requirements = report["platform_verified_readiness"]["protected_goal_parity"][
        "target_evidence_requirements"
    ]
    xp_x86 = next(item for item in requirements if item["target"] == "windows-xp-native-x86")
    xp_x86["support_boundary"] = "Windows XP x86 is fully native-ready."
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert (
        "windows-xp-native-x86 protected platform requirement support_boundary missing: "
        "['Windows XP native-host remote-target-only', "
        "'XP remote-target coverage does not imply native-host readiness']"
    ) in errors


def test_product_readiness_rejects_wrong_linux_builder_or_host_evidence(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    requirements = report["platform_verified_readiness"]["protected_goal_parity"][
        "target_evidence_requirements"
    ]
    linux_armhf = next(item for item in requirements if item["target"] == "linux-armhf")
    linux_armhf["builder_or_host_evidence"] = "generic Linux builder"
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert (
        "linux-armhf protected platform requirement builder_or_host_evidence must be "
        "matching self-hosted armv7l/armhf Linux runner or equivalent real armhf builder"
    ) in errors


def test_product_readiness_rejects_wrong_xp_builder_or_host_evidence(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    requirements = report["platform_verified_readiness"]["protected_goal_parity"][
        "target_evidence_requirements"
    ]
    xp_x64 = next(item for item in requirements if item["target"] == "windows-xp-native-x64")
    xp_x64["builder_or_host_evidence"] = "generic Windows VM"
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert (
        "windows-xp-native-x64 protected platform requirement builder_or_host_evidence must be "
        "Windows XP Professional x64 Edition SP2 VM or physical host running "
        "scripts/xp_smoke_runner.cmd and artifact validation; collector: modern "
        "self-hosted xp-evidence collector with Python 3.12 and GitHub Actions support; "
        "validates staged XP host proof but does not replace XP host smoke evidence"
    ) in errors


def test_product_readiness_rejects_weak_linux_smoke_evidence_requirements(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    requirements = report["platform_verified_readiness"]["protected_goal_parity"][
        "target_evidence_requirements"
    ]
    linux_i386 = next(item for item in requirements if item["target"] == "linux-i386")
    linux_i386["smoke_evidence"] = [
        "capture native smoke log with target, release tag, workflow run URL, workflow run attempt, source head SHA and observed git HEAD SHA",
        "capture native smoke log with target, release tag, workflow run URL, workflow run attempt, source head SHA and observed git HEAD SHA",
        "run a Linux smoke script",
    ]
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert (
        "linux-i386 protected platform requirement smoke_evidence contains duplicates: "
        "['capture native smoke log with target, release tag, workflow run URL, workflow run attempt, source head SHA and observed git HEAD SHA']"
    ) in errors
    assert any(
        error.startswith("linux-i386 protected platform requirement smoke_evidence missing:")
        and "consume matching builder identity evidence during native smoke and bind host identity plus security provenance from it" in error
        and "bind sanitized host label, deterministic evidence run ID and observed-at UTC timestamp into the native smoke log" in error
        and "prove 32-bit Linux userland and target architecture on the builder" in error
        and "bind DEB, RPM and AppImage SHA-256 lines into the native smoke log" in error
        and "verify DEB install, verify, upgrade and uninstall" in error
        and "prove TLS 1.3 preferred, TLS 1.2 minimum, isolated legacy crypto and modern defaults unchanged" in error
        for error in errors
    )
    assert (
        "linux-i386 protected platform requirement smoke_evidence has unexpected items: "
        "['run a Linux smoke script']"
    ) in errors


def test_product_readiness_rejects_weak_xp_smoke_evidence_requirements(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    requirements = report["platform_verified_readiness"]["protected_goal_parity"][
        "target_evidence_requirements"
    ]
    xp_x86 = next(item for item in requirements if item["target"] == "windows-xp-native-x86")
    xp_x86["smoke_evidence"] = [
        "launch CLI without unsupported Windows APIs",
        "launch CLI without unsupported Windows APIs",
        "verify isolated legacy crypto never changes modern defaults",
    ]
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert (
        "windows-xp-native-x86 protected platform requirement smoke_evidence contains duplicates: "
        "['launch CLI without unsupported Windows APIs']"
    ) in errors
    assert any(
        error.startswith("windows-xp-native-x86 protected platform requirement smoke_evidence missing:")
        and "validate artifact manifest and SHA256SUMS on the Windows XP host before collector upload" in error
        and "prove legacy crypto remains profile-scoped opt-in" in error
        and "prove modern defaults remain unchanged" in error
        for error in errors
    )
    assert (
        "windows-xp-native-x86 protected platform requirement smoke_evidence has unexpected items: "
        "['verify isolated legacy crypto never changes modern defaults']"
    ) in errors


def test_product_readiness_rejects_malformed_protected_goal_requirement_metadata(
    monkeypatch,
) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    requirements = report["platform_verified_readiness"]["protected_goal_parity"][
        "target_evidence_requirements"
    ]
    linux_i386 = next(item for item in requirements if item["target"] == "linux-i386")
    linux_i386["target"] = True
    linux_armhf = next(item for item in requirements if item["target"] == "linux-armhf")
    linux_armhf["required_commands"][False] = "python scripts/fake.py"
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert "protected platform goal parity requirements must cover every protected target" in errors
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


def test_product_readiness_rejects_missing_protected_goal_staged_upload_command(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    requirements = report["platform_verified_readiness"]["protected_goal_parity"][
        "target_evidence_requirements"
    ]
    linux_i386 = next(item for item in requirements if item["target"] == "linux-i386")
    del linux_i386["required_commands"]["staged_upload_command"]
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert (
        "linux-i386 protected platform requirement required_commands missing: "
        "['staged_upload_command']"
    ) in errors


def test_product_readiness_rejects_wrong_protected_goal_staged_upload_command(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    requirements = report["platform_verified_readiness"]["protected_goal_parity"][
        "target_evidence_requirements"
    ]
    xp_x64 = next(item for item in requirements if item["target"] == "windows-xp-native-x64")
    xp_x64["required_commands"]["staged_upload_command"] = xp_x64["required_commands"][
        "staged_upload_command"
    ].replace("stage_xp_native_evidence_upload.py", "stage_xp_upload.py")
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert any(
        "windows-xp-native-x64 protected platform requirement staged_upload_command must be"
        in error
        for error in errors
    )


def test_product_readiness_rejects_protected_goal_staged_upload_without_force(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    requirements = report["platform_verified_readiness"]["protected_goal_parity"][
        "target_evidence_requirements"
    ]
    linux_i386 = next(item for item in requirements if item["target"] == "linux-i386")
    linux_i386["required_commands"]["staged_upload_command"] = linux_i386["required_commands"][
        "staged_upload_command"
    ].replace(" --force", "")
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert any(
        "linux-i386 protected platform requirement staged_upload_command must be" in error
        for error in errors
    )


def test_product_readiness_rejects_unscoped_protected_goal_staged_upload(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    requirements = report["platform_verified_readiness"]["protected_goal_parity"][
        "target_evidence_requirements"
    ]
    linux_armhf = next(item for item in requirements if item["target"] == "linux-armhf")
    linux_armhf["required_commands"]["staged_upload_command"] = linux_armhf[
        "required_commands"
    ]["staged_upload_command"].replace(
        "platform-evidence-upload/linux-armhf/v<project.version>",
        "<release-upload-staging-dir>",
    )
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert any(
        "linux-armhf protected platform requirement staged_upload_command must be" in error
        for error in errors
    )


def test_product_readiness_rejects_wrong_protected_goal_command_template(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    requirements = report["platform_verified_readiness"]["protected_goal_parity"][
        "target_evidence_requirements"
    ]
    linux_armhf = next(item for item in requirements if item["target"] == "linux-armhf")
    linux_armhf["required_commands"]["accepted_evidence_candidate_command"] = linux_armhf[
        "required_commands"
    ]["accepted_evidence_candidate_command"].replace(
        " --release-source-run-attempt <github-actions-run-attempt>",
        "",
    )
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert any(
        "linux-armhf protected platform requirement accepted_evidence_candidate_command must be"
        in error
        for error in errors
    )


def test_product_readiness_rejects_unbound_candidate_upload_paths(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    requirements = report["platform_verified_readiness"]["protected_goal_parity"][
        "target_evidence_requirements"
    ]
    linux_i386 = next(item for item in requirements if item["target"] == "linux-i386")
    linux_i386["required_commands"]["accepted_evidence_candidate_command"] = linux_i386[
        "required_commands"
    ]["accepted_evidence_candidate_command"].replace(
        " --staged-upload-out-dir platform-evidence-upload/linux-i386/v<project.version>",
        "",
    )
    xp_x64 = next(item for item in requirements if item["target"] == "windows-xp-native-x64")
    xp_x64["required_commands"]["accepted_evidence_candidate_command"] = xp_x64[
        "required_commands"
    ]["accepted_evidence_candidate_command"].replace(
        " --xp-evidence-output-dir <xp-evidence-output-dir>",
        "",
    )
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert any(
        "linux-i386 protected platform requirement accepted_evidence_candidate_command must be"
        in error
        for error in errors
    )
    assert any(
        "windows-xp-native-x64 protected platform requirement accepted_evidence_candidate_command must be"
        in error
        for error in errors
    )


def test_product_readiness_rejects_unscoped_candidate_upload_path(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    requirements = report["platform_verified_readiness"]["protected_goal_parity"][
        "target_evidence_requirements"
    ]
    xp_x86 = next(item for item in requirements if item["target"] == "windows-xp-native-x86")
    xp_x86["required_commands"]["accepted_evidence_candidate_command"] = xp_x86[
        "required_commands"
    ]["accepted_evidence_candidate_command"].replace(
        "platform-evidence-upload/windows-xp-native-x86/v<project.version>",
        "<release-upload-staging-dir>",
    )
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert any(
        "windows-xp-native-x86 protected platform requirement "
        "accepted_evidence_candidate_command must be" in error
        for error in errors
    )


def test_product_readiness_rejects_unexpected_protected_goal_command(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    requirements = report["platform_verified_readiness"]["protected_goal_parity"][
        "target_evidence_requirements"
    ]
    xp_x86 = next(item for item in requirements if item["target"] == "windows-xp-native-x86")
    xp_x86["required_commands"]["unsafe_upload_command"] = "python scripts/upload_everything.py"
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert (
        "windows-xp-native-x86 protected platform requirement required_commands has unexpected keys: "
        "['unsafe_upload_command']"
    ) in errors


def test_product_readiness_rejects_inconsistent_protected_goal_release_source_flag(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    goal = report["platform_verified_readiness"]["protected_goal_parity"]
    goal["release_source_heads"] = ["a" * 40, "b" * 40]
    goal["release_source_head_consistent"] = True
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert (
        "protected platform goal parity release_source_head_consistent must match release_source_heads"
        in errors
    )


def test_product_readiness_rejects_weak_protected_goal_accepted_evidence_record(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    requirements = report["platform_verified_readiness"]["protected_goal_parity"][
        "target_evidence_requirements"
    ]
    linux_i386 = next(item for item in requirements if item["target"] == "linux-i386")
    linux_i386["accepted_evidence_record"] = {
        "registry": "configs/other.json",
        "target": "linux-armhf",
        "status": "draft",
        "readiness_percent": 70.0,
        "release_tag": "latest",
        "review_bundle_required": False,
    }
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert "linux-i386 protected platform requirement must point at accepted evidence registry" in errors
    assert (
        "linux-i386 protected platform requirement accepted_evidence_record.target must match target"
        in errors
    )
    assert (
        "linux-i386 protected platform requirement accepted_evidence_record.status must be accepted"
        in errors
    )
    assert (
        "linux-i386 protected platform requirement accepted_evidence_record.readiness_percent must be 100.0"
        in errors
    )
    assert (
        "linux-i386 protected platform requirement accepted_evidence_record.release_tag "
        "must be v<project.version> or a concrete vX.Y.Z release tag"
    ) in errors
    assert (
        "linux-i386 protected platform requirement accepted_evidence_record.review_bundle_required must be true"
        in errors
    )


def test_product_readiness_rejects_weak_protected_goal_review_bundle_files(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    requirements = report["platform_verified_readiness"]["protected_goal_parity"][
        "target_evidence_requirements"
    ]
    linux_i386 = next(item for item in requirements if item["target"] == "linux-i386")
    linux_i386["required_review_bundle_files"] = [
        "extended-linux-evidence-bundle-linux-i386-v<project.version>.json",
        "extended-linux-evidence-bundle-linux-i386-v<project.version>.json",
        "extra-review-bundle.txt",
    ]
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert (
        "linux-i386 protected platform requirement review bundle files contain duplicates: "
        "['extended-linux-evidence-bundle-linux-i386-v<project.version>.json']"
    ) in errors
    assert any(
        error.startswith("linux-i386 protected platform requirement review bundle files missing:")
        and "extended-linux-evidence-bundle-linux-i386-v<project.version>.zip" in error
        and "extended-linux-evidence-bundle-linux-i386-v<project.version>-SHA256SUMS.txt" in error
        for error in errors
    )
    assert (
        "linux-i386 protected platform requirement review bundle files has unexpected files: "
        "['extra-review-bundle.txt']"
    ) in errors


def test_product_readiness_rejects_missing_protected_goal_release_asset_source(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    requirements = report["platform_verified_readiness"]["protected_goal_parity"][
        "target_evidence_requirements"
    ]
    linux_i386 = next(item for item in requirements if item["target"] == "linux-i386")
    linux_i386.pop("release_asset_source_required")
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert (
        "linux-i386 protected platform requirement missing release_asset_source_required"
        in errors
    )


def test_product_readiness_rejects_weak_protected_goal_release_asset_source(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    requirements = report["platform_verified_readiness"]["protected_goal_parity"][
        "target_evidence_requirements"
    ]
    linux_i386 = next(item for item in requirements if item["target"] == "linux-i386")
    linux_i386["release_asset_source_required"] = {
        "type": "zip",
        "workflow": ".github/workflows/xp-native-evidence.yml",
        "workflow_run_url": "latest",
        "artifact_name": "latest",
        "head_sha": "latest",
        "run_attempt": "latest",
        "contains_files": ["remote-ops-workspace-v<project.version>-linux-i386.deb"],
    }
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert (
        "linux-i386 protected platform requirement release_asset_source_required.type "
        "must be github-actions-artifact"
    ) in errors
    assert (
        "linux-i386 protected platform requirement release_asset_source_required.workflow "
        "must be .github/workflows/extended-platform-evidence.yml"
    ) in errors
    assert (
        "linux-i386 protected platform requirement release_asset_source_required.artifact_name "
        "must be extended-linux-evidence-linux-i386-v<project.version>"
    ) in errors
    assert (
        "linux-i386 protected platform requirement release_asset_source_required.workflow_run_url "
        "must require a GitHub Actions run URL"
    ) in errors
    assert (
        "linux-i386 protected platform requirement release_asset_source_required.head_sha "
        "must require the release source Git SHA"
    ) in errors
    assert (
        "linux-i386 protected platform requirement release_asset_source_required.run_attempt "
        "must require the release source run attempt"
    ) in errors
    assert any(
        error.startswith(
            "linux-i386 protected platform requirement "
            "release_asset_source_required.contains_files missing files:"
        )
        for error in errors
    )


def test_product_readiness_rejects_non_string_protected_goal_requirement_entries(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    requirements = report["platform_verified_readiness"]["protected_goal_parity"][
        "target_evidence_requirements"
    ]
    linux_i386 = next(item for item in requirements if item["target"] == "linux-i386")
    linux_i386["required_artifacts"].append(True)
    linux_i386["required_review_bundle_files"].append(True)
    linux_i386["release_asset_source_required"]["contains_files"].append(True)
    linux_i386["smoke_evidence"].append(True)
    linux_i386["security_requirements"].append(True)
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert (
        "linux-i386 protected platform requirement required artifacts entries "
        "must be plain file names, got True"
    ) in errors
    assert (
        "linux-i386 protected platform requirement review bundle files entries "
        "must be plain file names, got True"
    ) in errors
    assert (
        "linux-i386 protected platform requirement "
        "release_asset_source_required.contains_files entries must be plain file names, got True"
    ) in errors
    assert (
        "linux-i386 protected platform requirement smoke_evidence entries must be strings, got True"
        in errors
    )
    assert (
        "linux-i386 Linux protected platform requirement "
        "security_requirements entries must be strings, got True"
    ) in errors


def test_product_readiness_rejects_missing_linux_modern_default_security_proof(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    requirements = report["platform_verified_readiness"]["protected_goal_parity"][
        "target_evidence_requirements"
    ]
    linux_i386 = next(item for item in requirements if item["target"] == "linux-i386")
    linux_i386["security_requirements"] = [
        "security patch evidence proving TLS 1.3 preferred, TLS 1.2 minimum, isolated legacy compatibility "
        "and CVE patch review with concrete security_update_channel and cve_review_reference "
        "update/advisory provenance",
    ]
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert any(
        "linux-i386 Linux protected platform requirement missing security proof" in error
        and "modern Windows 10/11, Linux, and macOS defaults must keep hardened crypto" in error
        for error in errors
    )


def test_product_readiness_requires_accepted_row_release_bindings(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    linux_i386 = next(
        row
        for row in report["platform_verified_readiness"]["targets"]
        if row["target"] == "linux-i386"
    )
    linux_i386["accepted_evidence_present_targets"] = ["linux-i386"]
    linux_i386.pop("accepted_evidence_release_tags", None)
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert "linux-i386 accepted evidence row must expose accepted_evidence_release_tags" in errors


def test_product_readiness_rejects_malformed_accepted_row_target_lists_without_stringifying(
    monkeypatch,
) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    linux_i386 = next(
        row
        for row in report["platform_verified_readiness"]["targets"]
        if row["target"] == "linux-i386"
    )
    linux_i386["accepted_evidence_required_targets"] = [True]
    linux_i386["accepted_evidence_present_targets"] = [True]
    for field, value in {
        "accepted_evidence_release_tags": "v1.0.2",
        "accepted_evidence_release_repositories": ["example/remote-ops-workspace"],
        "accepted_evidence_release_source_heads": "a" * 40,
        "accepted_evidence_release_source_run_attempts": 1,
        "accepted_evidence_release_source_run_urls": (
            "https://github.com/example/remote-ops-workspace/actions/runs/12345"
        ),
        "accepted_evidence_release_source_workflows": (
            ".github/workflows/extended-platform-evidence.yml"
        ),
    }.items():
        linux_i386[field] = {True: value}
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert (
        "protected platform row linux-i386 accepted_evidence_required_targets "
        "entries must be non-empty strings, got True"
    ) in errors
    assert (
        "protected platform row linux-i386 accepted_evidence_present_targets "
        "entries must be non-empty strings, got True"
    ) in errors
    assert (
        "accepted evidence row linux-i386 accepted_evidence_present_targets "
        "entries must be non-empty strings, got True"
    ) in errors
    assert (
        "linux-i386 accepted evidence accepted_evidence_release_tags keys "
        "must be non-empty strings, got True"
    ) in errors
    assert not any("accepted_evidence_release_tags[True]" in error for error in errors)


def test_product_readiness_rejects_missing_accepted_row_release_source_run_attempts(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    linux_i386 = next(
        row
        for row in report["platform_verified_readiness"]["targets"]
        if row["target"] == "linux-i386"
    )
    linux_i386["accepted_evidence_present_targets"] = ["linux-i386"]
    linux_i386.pop("accepted_evidence_release_source_run_attempts", None)
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert "linux-i386 accepted evidence row must expose accepted_evidence_release_source_run_attempts" in errors


def test_product_readiness_rejects_missing_accepted_row_release_source_run_urls(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    linux_i386 = next(
        row
        for row in report["platform_verified_readiness"]["targets"]
        if row["target"] == "linux-i386"
    )
    linux_i386["accepted_evidence_present_targets"] = ["linux-i386"]
    linux_i386.pop("accepted_evidence_release_source_run_urls", None)
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert "linux-i386 accepted evidence row must expose accepted_evidence_release_source_run_urls" in errors


def test_product_readiness_rejects_missing_accepted_row_release_source_workflows(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    linux_i386 = next(
        row
        for row in report["platform_verified_readiness"]["targets"]
        if row["target"] == "linux-i386"
    )
    linux_i386["accepted_evidence_present_targets"] = ["linux-i386"]
    linux_i386.pop("accepted_evidence_release_source_workflows", None)
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert "linux-i386 accepted evidence row must expose accepted_evidence_release_source_workflows" in errors


def test_product_readiness_rejects_weak_accepted_row_release_bindings(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    linux_i386 = next(
        row
        for row in report["platform_verified_readiness"]["targets"]
        if row["target"] == "linux-i386"
    )
    linux_i386["accepted_evidence_present_targets"] = ["linux-i386"]
    linux_i386["accepted_evidence_release_tags"] = {"linux-i386": "latest"}
    linux_i386["accepted_evidence_release_repositories"] = {
        "linux-i386": ["example/remote-ops-workspace", "other/remote-ops-workspace"],
    }
    linux_i386["accepted_evidence_release_source_heads"] = {"linux-i386": "ABC123"}
    linux_i386["accepted_evidence_release_source_run_attempts"] = {"linux-i386": 0}
    linux_i386["accepted_evidence_release_source_run_urls"] = {"linux-i386": "latest"}
    linux_i386["accepted_evidence_release_source_workflows"] = {
        "linux-i386": ".github/workflows/xp-native-evidence.yml",
    }
    monkeypatch.setattr(checker, "coverage_report", lambda: report)

    errors = checker.check_product_readiness()

    assert (
        "linux-i386 accepted evidence accepted_evidence_release_tags[linux-i386] "
        "must be a concrete vX.Y.Z release tag"
    ) in errors
    assert (
        "linux-i386 accepted evidence accepted_evidence_release_repositories[linux-i386] "
        "must list exactly one GitHub release repository"
    ) in errors
    assert (
        "linux-i386 accepted evidence accepted_evidence_release_source_heads[linux-i386] "
        "must be a 40-character lowercase Git SHA"
    ) in errors
    assert (
        "linux-i386 accepted evidence accepted_evidence_release_source_run_attempts[linux-i386] "
        "must be a positive integer GitHub Actions run attempt"
    ) in errors
    assert (
        "linux-i386 accepted evidence accepted_evidence_release_source_run_urls[linux-i386] "
        "must be a GitHub Actions run URL"
    ) in errors
    assert (
        "linux-i386 accepted evidence accepted_evidence_release_source_workflows[linux-i386] "
        "must be .github/workflows/extended-platform-evidence.yml"
    ) in errors

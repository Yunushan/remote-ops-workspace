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


def test_product_readiness_rejects_missing_linux_modern_default_security_proof(monkeypatch) -> None:
    checker = load_product_readiness_checker()
    report = deepcopy(checker.coverage_report())
    requirements = report["platform_verified_readiness"]["protected_goal_parity"][
        "target_evidence_requirements"
    ]
    linux_i386 = next(item for item in requirements if item["target"] == "linux-i386")
    linux_i386["security_requirements"] = [
        "security patch evidence proving TLS 1.3 preferred, TLS 1.2 minimum, isolated legacy compatibility and CVE patch review",
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

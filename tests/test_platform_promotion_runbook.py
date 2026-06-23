from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def test_platform_promotion_runbook_passes_current_tree() -> None:
    checker = _load_checker()

    assert checker.main() == 0


def test_platform_promotion_runbook_rejects_missing_target_id() -> None:
    checker = _load_checker()
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8")
    text = text.replace("Target id: `linux-i386`", "Target id: `linux-i386-missing`")

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert "promotion runbook missing target id section: linux-i386" in errors


def test_platform_promotion_runbook_rejects_missing_blocker() -> None:
    checker = _load_checker()
    promotion = json.loads(Path("configs/platform_parity_promotion.json").read_text(encoding="utf-8"))
    blocker = promotion["protected_targets"][0]["current_blockers"][0]
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(blocker, "")

    errors = checker.check_platform_promotion_runbook(runbook_text=text, promotion=promotion)

    assert f"linux-i386 runbook missing blocker: {blocker}" in errors


def test_platform_promotion_runbook_requires_protected_goal_gate() -> None:
    checker = _load_checker()
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(
        "python scripts/check_protected_platform_goal.py --release-tag v<project.version> --require-complete\n",
        "",
    )

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert any("check_protected_platform_goal.py" in error for error in errors)


def test_platform_promotion_runbook_requires_bundle_backed_strict_verify() -> None:
    checker = _load_checker()
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(
        (
            "python scripts/verify.py --quick --no-cli-smoke --require-platform-goal-targets "
            "--release-tag v<project.version> --platform-review-bundle-dir <bundle-dir> "
            "--release-assets-dir <release-assets-dir>"
        ),
        "python scripts/verify.py --quick --no-cli-smoke --require-platform-goal-targets",
    )

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert any("--platform-review-bundle-dir <bundle-dir>" in error for error in errors)
    assert any("--release-assets-dir <release-assets-dir>" in error for error in errors)


def test_platform_promotion_runbook_requires_asset_backed_strict_publish() -> None:
    checker = _load_checker()
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(
        (
            "python scripts/check_release_publish_assets.py --assets-dir <release-assets-dir> "
            "--tag v<project.version> --require-platform-goal-targets"
        ),
        "python scripts/check_release_publish_assets.py --require-platform-goal-targets",
    )

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert any("--assets-dir <release-assets-dir>" in error for error in errors)
    assert any("--tag v<project.version>" in error for error in errors)


def test_platform_promotion_runbook_requires_strict_verify_import_dry_run() -> None:
    checker = _load_checker()
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(
        "python scripts/import_platform_evidence_artifacts.py --dry-run",
        "python scripts/import_platform_evidence_artifacts.py",
    )

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert any("import_platform_evidence_artifacts.py --dry-run" in error for error in errors)


def test_platform_promotion_runbook_requires_staged_upload_hash_binding() -> None:
    checker = _load_checker()
    snippet = "staged native artifacts and review-bundle files must match the finalized accepted record hashes"
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(snippet, "")

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert any("finalized accepted record hashes" in error for error in errors)


def test_platform_promotion_runbook_requires_staged_review_bundle_refinalization() -> None:
    checker = _load_checker()
    snippet = "staged review bundle must re-finalize to the accepted record before upload"
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(snippet, "")

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert any("re-finalize to the accepted record before upload" in error for error in errors)


def test_platform_promotion_runbook_requires_local_goal_preflight() -> None:
    checker = _load_checker()
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(
        "python scripts/check_platform_goal_local_evidence.py",
        "python scripts/removed.py",
    )

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert any("check_platform_goal_local_evidence.py" in error for error in errors)


def test_platform_promotion_runbook_requires_xp_x64_edition_evidence() -> None:
    checker = _load_checker()
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(
        "Professional x64 Edition",
        "x64",
    )

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert "windows-xp-native-x64 runbook missing XP x64 snippet: Professional x64 Edition" in errors


def test_platform_promotion_runbook_requires_xp_source_workflow() -> None:
    checker = _load_checker()
    workflow = ".github/workflows/xp-native-evidence.yml"
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(workflow, "")

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert f"windows-xp-native-x86 runbook missing XP release source workflow: {workflow}" in errors


def test_platform_promotion_runbook_requires_xp_scoped_upload_staging() -> None:
    checker = _load_checker()
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(
        "python scripts/stage_xp_native_evidence_upload.py",
        "python scripts/removed.py",
    )

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert any("stage_xp_native_evidence_upload.py" in error for error in errors)


def test_platform_promotion_runbook_requires_xp_target_release_scoped_dispatch_paths() -> None:
    checker = _load_checker()
    snippet = (
        "assets_dir, evidence_file and evidence_dir dispatch inputs must be "
        "workspace-relative staged paths that include the target id and release tag as path segments"
    )
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(
        snippet,
        "assets_dir, evidence_file and evidence_dir dispatch inputs must be workspace-relative staged paths",
    )

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert any("target id and release tag as path segments" in error for error in errors)


def test_platform_promotion_runbook_requires_linux_target_scoped_evidence_filenames() -> None:
    checker = _load_checker()
    snippet = "builder-identity-<target>.json`, `native-smoke-<target>.log`, `platform-verified-evidence-<target>.json"
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(snippet, "")

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert any("native-smoke-<target>.log" in error for error in errors)


def test_platform_promotion_runbook_requires_linux_builder_source_head_sha() -> None:
    checker = _load_checker()
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(
        " --source-head-sha <github-actions-head-sha>",
        "",
    )

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert any("--source-head-sha <github-actions-head-sha>" in error for error in errors)


def test_platform_promotion_runbook_requires_linux_security_boundaries() -> None:
    checker = _load_checker()
    promotion = json.loads(Path("configs/platform_parity_promotion.json").read_text(encoding="utf-8"))
    target = next(item for item in promotion["protected_targets"] if item["id"] == "linux-i386")
    security_requirement = target["promotion_to_100_requires"]["security_requirements"][1]
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(
        security_requirement,
        "",
    )

    errors = checker.check_platform_promotion_runbook(runbook_text=text, promotion=promotion)

    assert f"linux-i386 runbook missing security requirement: {security_requirement}" in errors


def test_platform_promotion_runbook_requires_exact_candidate_command() -> None:
    checker = _load_checker()
    promotion = json.loads(Path("configs/platform_parity_promotion.json").read_text(encoding="utf-8"))
    target = next(item for item in promotion["protected_targets"] if item["id"] == "linux-i386")
    command = target["promotion_to_100_requires"]["accepted_evidence_candidate_command"]
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(command, "")

    errors = checker.check_platform_promotion_runbook(runbook_text=text, promotion=promotion)

    assert f"linux-i386 runbook missing accepted evidence candidate command: {command}" in errors


def _load_checker():
    path = Path("scripts/check_platform_promotion_runbook.py")
    spec = importlib.util.spec_from_file_location("check_platform_promotion_runbook", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

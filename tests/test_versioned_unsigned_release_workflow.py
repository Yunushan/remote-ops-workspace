from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "versioned-unsigned-release.yml"


def checker():
    path = ROOT / "scripts" / "check_versioned_unsigned_release_workflow.py"
    spec = importlib.util.spec_from_file_location("check_versioned_unsigned_release_workflow", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def workflow() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


def test_exact_tag_unsigned_preview_contract_passes() -> None:
    assert checker().check_versioned_unsigned_release_workflow(workflow()) == []


@pytest.mark.parametrize(
    ("old", "new", "expected"),
    [
        ('test "$GITHUB_REF" = "refs/tags/$RELEASE_TAG"', 'echo "$GITHUB_REF"', "exact tag"),
        ('test "$GITHUB_RUN_ATTEMPT" = "1"', 'echo "$GITHUB_RUN_ATTEMPT"', "RUN_ATTEMPT"),
        ('--sha "$RELEASE_SHA"', '--sha "$GITHUB_REF_NAME"', "--sha"),
        ('--native-release-channel unsigned-preview', '--source-assets-only', "native"),
        ('--evidence-dir redistribution-evidence', '--evidence-dir nonexistent', "redistribution"),
        ("prerelease: true", "prerelease: false", "prerelease"),
    ],
)
def test_release_boundary_rejects_removed_guards(old: str, new: str, expected: str) -> None:
    source = workflow()
    assert old in source
    errors = checker().check_versioned_unsigned_release_workflow(source.replace(old, new, 1))
    assert any(expected in error for error in errors), errors


def test_release_boundary_rejects_automatic_tag_publication() -> None:
    source = workflow().replace("on:\n  workflow_dispatch:\n", 'on:\n  push:\n    tags: ["v*"]\n', 1)
    assert any(
        "workflow_dispatch only" in error
        for error in checker().check_versioned_unsigned_release_workflow(source)
    )


def test_release_boundary_rejects_missing_native_build_dependency() -> None:
    source = workflow()
    publish_start = source.index("  publish-unsigned-preview:\n")
    before, publish = source[:publish_start], source[publish_start:]
    assert "      - macos-native\n" in publish
    publish = publish.replace("      - macos-native\n", "", 1)
    errors = checker().check_versioned_unsigned_release_workflow(before + publish)
    assert any("must depend on macos-native" in error for error in errors)


def test_release_boundary_rejects_production_signing_claim() -> None:
    source = workflow().replace("--channel unsigned-preview", "--channel production-signed", 1)
    errors = checker().check_versioned_unsigned_release_workflow(source)
    assert any("production certification" in error for error in errors)


def test_release_boundary_rejects_ignored_asset_validator() -> None:
    source = workflow().replace(
        "      - name: Validate complete unsigned release asset inventory\n",
        "      - name: Validate complete unsigned release asset inventory\n        continue-on-error: true\n",
        1,
    )
    errors = checker().check_versioned_unsigned_release_workflow(source)
    assert any("ignore publication checks" in error for error in errors)


def test_release_boundary_rejects_ignored_redistribution_gate() -> None:
    source = workflow().replace(
        "      - name: Require exact-artifact preview redistribution evidence\n",
        "      - name: Require exact-artifact preview redistribution evidence\n        continue-on-error: true\n",
        1,
    )
    errors = checker().check_versioned_unsigned_release_workflow(source)
    assert any("ignore publication checks" in error for error in errors)


def test_release_boundary_rejects_missing_early_evidence_preflight() -> None:
    source = workflow().replace(
        "      - name: Require tagged preview redistribution materials before builds\n",
        "      - name: Skipped redistribution evidence\n",
        1,
    )
    errors = checker().check_versioned_unsigned_release_workflow(source)
    assert any("before builds" in error for error in errors)


def test_release_boundary_rejects_late_redistribution_gate() -> None:
    source = workflow()
    marker = "      - name: Require exact-artifact preview redistribution evidence\n"
    start = source.index(marker)
    end = source.index("      - uses: actions/upload-artifact@", start)
    step = source[start:end]
    changed = source[:start] + source[end:]
    draft = "      - name: Create new unsigned draft by numeric API identity\n"
    changed = changed.replace(draft, step + draft, 1)
    errors = checker().check_versioned_unsigned_release_workflow(changed)
    assert any("validate, attest" in error for error in errors)

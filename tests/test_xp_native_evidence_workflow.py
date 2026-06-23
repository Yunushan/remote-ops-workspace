from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def test_xp_native_evidence_workflow_passes_current_tree() -> None:
    checker = _load_checker()

    assert checker.main() == 0


def test_xp_native_evidence_workflow_rejects_publish_trigger() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/xp-native-evidence.yml").read_text(encoding="utf-8")
    workflow += "\npush:\n"

    errors = checker.check_xp_native_evidence_workflow(workflow)

    assert "XP native evidence workflow must not run on push" in errors


def test_xp_native_evidence_workflow_rejects_write_permissions() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/xp-native-evidence.yml").read_text(encoding="utf-8").replace(
        "permissions:\n  contents: read",
        "permissions:\n  contents: read\n  actions: write",
    )

    errors = checker.check_xp_native_evidence_workflow(workflow)

    assert "XP native evidence workflow must not request write permissions" in errors


def test_xp_native_evidence_workflow_requires_scoped_artifact_name() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/xp-native-evidence.yml").read_text(encoding="utf-8").replace(
        'xp-native-evidence-${{ inputs.target }}-${{ inputs.release_tag }}',
        "xp-native-evidence",
    )

    errors = checker.check_xp_native_evidence_workflow(workflow)

    assert any("target/release scoped source artifact name" in error for error in errors)
    assert any("target/release scoped uploaded artifact" in error for error in errors)


def test_xp_native_evidence_workflow_requires_finalizer() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/xp-native-evidence.yml").read_text(encoding="utf-8").replace(
        "python scripts/finalize_platform_verified_evidence_record.py",
        "python scripts/removed.py",
    )

    errors = checker.check_xp_native_evidence_workflow(workflow)

    assert any("finalized evidence record generation" in error for error in errors)


def test_xp_native_evidence_workflow_requires_release_source_run_attempt() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/xp-native-evidence.yml").read_text(encoding="utf-8").replace(
        '--release-source-run-attempt "${{ github.run_attempt }}" ',
        "",
        1,
    )

    errors = checker.check_xp_native_evidence_workflow(workflow)

    assert any("release source run-attempt binding" in error for error in errors)


def test_xp_native_evidence_workflow_requires_local_source_run_attempt() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/xp-native-evidence.yml").read_text(encoding="utf-8").replace(
        ' --xp-source-run-attempt "${{ github.run_attempt }}"',
        "",
        1,
    )

    errors = checker.check_xp_native_evidence_workflow(workflow)

    assert any("XP local source run-attempt binding" in error for error in errors)


def test_xp_native_evidence_workflow_requires_dispatch_input_preflight() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/xp-native-evidence.yml").read_text(encoding="utf-8").replace(
        "python scripts/check_xp_native_evidence_dispatch_inputs.py",
        "python scripts/removed.py",
    )

    errors = checker.check_xp_native_evidence_workflow(workflow)

    assert any("XP dispatch input preflight" in error for error in errors)


def test_xp_native_evidence_workflow_requires_local_goal_preflight() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/xp-native-evidence.yml").read_text(encoding="utf-8").replace(
        "python scripts/check_platform_goal_local_evidence.py",
        "python scripts/removed.py",
    )

    errors = checker.check_xp_native_evidence_workflow(workflow)

    assert any("XP local protected goal evidence preflight" in error for error in errors)


def test_xp_native_evidence_workflow_requires_scoped_upload_staging() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/xp-native-evidence.yml").read_text(encoding="utf-8").replace(
        "python scripts/stage_xp_native_evidence_upload.py",
        "python scripts/removed.py",
    )

    errors = checker.check_xp_native_evidence_workflow(workflow)

    assert any("scoped XP upload staging" in error for error in errors)


def test_xp_native_evidence_workflow_requires_target_release_scoped_output_dir() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/xp-native-evidence.yml").read_text(encoding="utf-8").replace(
        "xp-evidence-output/${{ inputs.target }}/${{ inputs.release_tag }}",
        "xp-evidence-output",
    )

    errors = checker.check_xp_native_evidence_workflow(workflow)

    assert any("target/release scoped XP evidence output" in error for error in errors)


def test_xp_native_evidence_workflow_rejects_raw_artifact_wildcards() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/xp-native-evidence.yml").read_text(encoding="utf-8").replace(
        "path: xp-evidence-upload/*",
        "path: |\n            ${{ inputs.assets_dir }}/*\n            xp-evidence-output/*",
    )

    errors = checker.check_xp_native_evidence_workflow(workflow)

    assert "xp-native-evidence job must not upload raw operator-supplied assets_dir wildcard" in errors
    assert "xp-native-evidence job must upload scoped staged files, not raw xp-evidence-output wildcard" in errors


def test_xp_native_evidence_dispatch_rejects_file_shaped_directory_inputs() -> None:
    checker = _load_dispatch_checker()

    errors = checker.check_xp_native_evidence_dispatch_inputs(
        target="windows-xp-native-x86",
        release_tag="v1.0.2",
        release_asset_base_url="https://github.com/example/remote-ops-workspace/releases/download/v1.0.2",
        workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/12345",
        assets_dir="native-dist/windows-xp/windows-xp-native-x86/v1.0.2/artifacts.zip",
        evidence_file="evidence/windows-xp-native-x86/v1.0.2/xp-evidence.json",
        evidence_dir="evidence/windows-xp-native-x86/v1.0.2/proof.log",
    )

    assert "assets_dir must be a directory path, got 'native-dist/windows-xp/windows-xp-native-x86/v1.0.2/artifacts.zip'" in errors
    assert "evidence_dir must be a directory path, got 'evidence/windows-xp-native-x86/v1.0.2/proof.log'" in errors


def _load_checker():
    path = Path("scripts/check_xp_native_evidence_workflow.py")
    spec = importlib.util.spec_from_file_location("check_xp_native_evidence_workflow", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_dispatch_checker():
    path = Path("scripts/check_xp_native_evidence_dispatch_inputs.py")
    spec = importlib.util.spec_from_file_location("check_xp_native_evidence_dispatch_inputs", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

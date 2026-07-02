from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def test_xp_dispatch_inputs_accept_valid_workspace_relative_paths() -> None:
    checker = _load_checker()

    errors = _check_dispatch_inputs(
        checker,
        target="windows-xp-native-x86",
        release_tag="v1.0.2",
        release_asset_base_url="https://github.com/example/remote-ops-workspace/releases/download/v1.0.2",
        workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/12345",
        assets_dir="staged/windows-xp-native-x86/v1.0.2/artifacts",
        evidence_file="staged/windows-xp-native-x86/v1.0.2/xp-evidence.json",
        evidence_dir="staged/windows-xp-native-x86/v1.0.2/smoke",
    )

    assert errors == []


def test_xp_dispatch_inputs_reject_unscoped_staging_paths() -> None:
    checker = _load_checker()

    errors = _check_dispatch_inputs(
        checker,
        target="windows-xp-native-x86",
        release_tag="v1.0.2",
        release_asset_base_url="https://github.com/example/remote-ops-workspace/releases/download/v1.0.2",
        workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/12345",
        assets_dir="staged/xp-x86/artifacts",
        evidence_file="staged/xp-x86/xp-evidence.json",
        evidence_dir="staged/xp-x86/smoke",
    )

    assert "assets_dir must include target path segment 'windows-xp-native-x86', got 'staged/xp-x86/artifacts'" in errors
    assert "assets_dir must include release_tag path segment 'v1.0.2', got 'staged/xp-x86/artifacts'" in errors
    assert (
        "evidence_file must include target path segment 'windows-xp-native-x86', "
        "got 'staged/xp-x86/xp-evidence.json'"
    ) in errors
    assert "evidence_dir must include release_tag path segment 'v1.0.2', got 'staged/xp-x86/smoke'" in errors


def test_xp_dispatch_inputs_reject_nonadjacent_target_release_paths() -> None:
    checker = _load_checker()

    errors = _check_dispatch_inputs(
        checker,
        target="windows-xp-native-x86",
        release_tag="v1.0.2",
        release_asset_base_url="https://github.com/example/remote-ops-workspace/releases/download/v1.0.2",
        workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/12345",
        assets_dir="staged/v1.0.2/windows-xp-native-x86/artifacts",
        evidence_file="staged/v1.0.2/windows-xp-native-x86/xp-evidence.json",
        evidence_dir="staged/v1.0.2/windows-xp-native-x86/smoke",
    )

    assert (
        "assets_dir must include adjacent target/release path segment "
        "windows-xp-native-x86/v1.0.2, got "
        "'staged/v1.0.2/windows-xp-native-x86/artifacts'"
    ) in errors
    assert (
        "evidence_file must include adjacent target/release path segment "
        "windows-xp-native-x86/v1.0.2, got "
        "'staged/v1.0.2/windows-xp-native-x86/xp-evidence.json'"
    ) in errors
    assert (
        "evidence_dir must include adjacent target/release path segment "
        "windows-xp-native-x86/v1.0.2, got "
        "'staged/v1.0.2/windows-xp-native-x86/smoke'"
    ) in errors


def test_xp_dispatch_inputs_reject_release_tag_mismatch() -> None:
    checker = _load_checker()

    errors = _check_dispatch_inputs(
        checker,
        target="windows-xp-native-x64",
        release_tag="v1.0.2",
        release_asset_base_url="https://github.com/example/remote-ops-workspace/releases/download/v1.0.3",
        workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/12345",
        assets_dir="staged/xp-x64/artifacts",
        evidence_file="staged/xp-x64/xp-evidence.json",
        evidence_dir="staged/xp-x64/smoke",
    )

    assert "release_asset_base_url tag must match release_tag v1.0.2, got v1.0.3" in errors


def test_xp_dispatch_inputs_reject_trailing_slash_release_base() -> None:
    checker = _load_checker()

    errors = _check_dispatch_inputs(
        checker,
        target="windows-xp-native-x86",
        release_tag="v1.0.2",
        release_asset_base_url="https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/",
        workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/12345",
        assets_dir="staged/windows-xp-native-x86/v1.0.2/artifacts",
        evidence_file="staged/windows-xp-native-x86/v1.0.2/xp-evidence.json",
        evidence_dir="staged/windows-xp-native-x86/v1.0.2/smoke",
    )

    assert (
        "--release-asset-base-url must be exactly "
        "https://github.com/<owner>/<repo>/releases/download/v1.0.2"
    ) in errors


def test_xp_dispatch_inputs_reject_cross_repo_inputs() -> None:
    checker = _load_checker()

    errors = _check_dispatch_inputs(
        checker,
        target="windows-xp-native-x86",
        release_tag="v1.0.2",
        release_asset_base_url="https://github.com/other/remote-ops-workspace/releases/download/v1.0.2",
        workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/12345",
        assets_dir="staged/xp-x86/artifacts",
        evidence_file="staged/xp-x86/xp-evidence.json",
        evidence_dir="staged/xp-x86/smoke",
    )

    assert (
        "release_asset_base_url repository must match workflow_run_url repository "
        "example/remote-ops-workspace, got other/remote-ops-workspace"
    ) in errors


def test_xp_dispatch_inputs_reject_malformed_repo_slug() -> None:
    checker = _load_checker()

    errors = _check_dispatch_inputs(
        checker,
        target="windows-xp-native-x64",
        release_tag="v1.0.2",
        release_asset_base_url=(
            "https://github.com/example/remote-ops-workspace?download=1/releases/download/v1.0.2"
        ),
        workflow_run_url="https://github.com/example/remote-ops-workspace?run=1/actions/runs/12345",
        assets_dir="staged/windows-xp-native-x64/v1.0.2/artifacts",
        evidence_file="staged/windows-xp-native-x64/v1.0.2/xp-evidence.json",
        evidence_dir="staged/windows-xp-native-x64/v1.0.2/smoke",
    )

    assert (
        "--release-asset-base-url must be exactly "
        "https://github.com/<owner>/<repo>/releases/download/v1.0.2"
    ) in errors
    assert "--workflow-run-url must be a GitHub Actions run URL" in errors


def test_xp_dispatch_inputs_reject_unsafe_paths() -> None:
    checker = _load_checker()

    errors = _check_dispatch_inputs(
        checker,
        target="windows-xp-native-x64",
        release_tag="v1.0.2",
        release_asset_base_url="https://github.com/example/remote-ops-workspace/releases/download/v1.0.2",
        workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/12345",
        assets_dir="/tmp/xp-artifacts",
        evidence_file="..\\secrets\\xp-evidence.json",
        evidence_dir="<evidence-dir>",
    )

    assert "assets_dir must be workspace-relative, got '/tmp/xp-artifacts'" in errors
    assert "evidence_file must not traverse outside the workspace, got '..\\\\secrets\\\\xp-evidence.json'" in errors
    assert "evidence_dir must be concrete, got '<evidence-dir>'" in errors


def test_xp_dispatch_inputs_reject_windows_drive_paths_with_forward_slashes() -> None:
    checker = _load_checker()

    errors = _check_dispatch_inputs(
        checker,
        target="windows-xp-native-x86",
        release_tag="v1.0.2",
        release_asset_base_url="https://github.com/example/remote-ops-workspace/releases/download/v1.0.2",
        workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/12345",
        assets_dir="C:/staged/windows-xp-native-x86/v1.0.2/artifacts",
        evidence_file="C:/staged/windows-xp-native-x86/v1.0.2/xp-evidence.json",
        evidence_dir="C:/staged/windows-xp-native-x86/v1.0.2/smoke",
    )

    assert (
        "assets_dir must be workspace-relative, "
        "got 'C:/staged/windows-xp-native-x86/v1.0.2/artifacts'"
    ) in errors
    assert (
        "evidence_file must be workspace-relative, "
        "got 'C:/staged/windows-xp-native-x86/v1.0.2/xp-evidence.json'"
    ) in errors
    assert (
        "evidence_dir must be workspace-relative, "
        "got 'C:/staged/windows-xp-native-x86/v1.0.2/smoke'"
    ) in errors


def test_xp_dispatch_inputs_reject_workspace_root_and_reserved_paths() -> None:
    checker = _load_checker()

    errors = _check_dispatch_inputs(
        checker,
        target="windows-xp-native-x86",
        release_tag="v1.0.2",
        release_asset_base_url="https://github.com/example/remote-ops-workspace/releases/download/v1.0.2",
        workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/12345",
        assets_dir=".",
        evidence_file=".github/xp-evidence.json",
        evidence_dir="staged/.private-smoke",
    )

    assert "assets_dir must not point at the workspace root, got '.'" in errors
    assert "evidence_file must not point inside reserved workspace directory '.github'" in errors
    assert "evidence_dir must not contain hidden path segments: ['.private-smoke']" in errors


def test_xp_dispatch_inputs_reject_invalid_source_head_sha() -> None:
    checker = _load_checker()

    errors = _check_dispatch_inputs(
        checker,
        source_head_sha="ABCDEF0123456789ABCDEF0123456789ABCDEF01",
    )

    assert (
        "source_head_sha must be a lowercase 40-character Git SHA, "
        "got 'ABCDEF0123456789ABCDEF0123456789ABCDEF01'"
    ) in errors


def test_xp_dispatch_inputs_reject_invalid_source_run_attempt() -> None:
    checker = _load_checker()

    errors = _check_dispatch_inputs(checker, source_run_attempt="0")

    assert "source_run_attempt must be a positive integer, got '0'" in errors


def test_xp_workflow_requires_dispatch_input_preflight() -> None:
    checker = _load_workflow_checker()
    workflow = Path(".github/workflows/xp-native-evidence.yml").read_text(encoding="utf-8").replace(
        "python scripts/check_xp_native_evidence_dispatch_inputs.py",
        "python scripts/removed.py",
    )

    errors = checker.check_xp_native_evidence_workflow(workflow)

    assert any("XP dispatch input preflight" in error for error in errors)


def _check_dispatch_inputs(checker, **overrides):
    values = {
        "target": "windows-xp-native-x86",
        "release_tag": "v1.0.2",
        "release_asset_base_url": "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2",
        "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "source_head_sha": "0123456789abcdef0123456789abcdef01234567",
        "source_run_attempt": "1",
        "assets_dir": "staged/windows-xp-native-x86/v1.0.2/artifacts",
        "evidence_file": "staged/windows-xp-native-x86/v1.0.2/xp-evidence.json",
        "evidence_dir": "staged/windows-xp-native-x86/v1.0.2/smoke",
    }
    values.update(overrides)
    return checker.check_xp_native_evidence_dispatch_inputs(**values)


def _load_checker():
    path = Path("scripts/check_xp_native_evidence_dispatch_inputs.py")
    spec = importlib.util.spec_from_file_location("check_xp_native_evidence_dispatch_inputs", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_workflow_checker():
    path = Path("scripts/check_xp_native_evidence_workflow.py")
    spec = importlib.util.spec_from_file_location("check_xp_native_evidence_workflow", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

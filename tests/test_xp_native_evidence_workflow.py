from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path

import pytest


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


def test_xp_native_evidence_workflow_requires_clean_checkout() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/xp-native-evidence.yml").read_text(encoding="utf-8").replace(
        "          clean: true\n",
        "",
    )

    errors = checker.check_xp_native_evidence_workflow(workflow)

    assert any("self-hosted checkout workspace cleanup" in error for error in errors)


def test_xp_native_evidence_workflow_rejects_clean_setting_outside_checkout_step() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/xp-native-evidence.yml").read_text(encoding="utf-8")
    block = checker.workflow_job_block(workflow, "xp-native-evidence")
    assert block
    mutated = block.replace("          clean: true\n", "", 1).replace(
        "      - uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1 # v6\n",
        "      - name: Misleading clean setting\n"
        "        run: echo clean\n"
        "        env:\n"
        "          clean: true\n"
        "      - uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1 # v6\n",
        1,
    )
    workflow = workflow.replace(block, mutated, 1)

    errors = checker.check_xp_native_evidence_workflow(workflow)

    assert "xp-native-evidence checkout step missing workspace cleanup: clean: true" in errors


def test_xp_native_evidence_workflow_rejects_persist_credentials_outside_checkout_step() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/xp-native-evidence.yml").read_text(encoding="utf-8")
    block = checker.workflow_job_block(workflow, "xp-native-evidence")
    assert block
    mutated = block.replace("          persist-credentials: false\n", "", 1).replace(
        "      - uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1 # v6\n",
        "      - name: Misleading credential setting\n"
        "        run: echo persist\n"
        "        env:\n"
        "          persist-credentials: false\n"
        "      - uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1 # v6\n",
        1,
    )
    workflow = workflow.replace(block, mutated, 1)

    errors = checker.check_xp_native_evidence_workflow(workflow)

    assert (
        "xp-native-evidence checkout step missing credential isolation: persist-credentials: false"
        in errors
    )


def test_xp_native_evidence_workflow_requires_target_release_concurrency() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/xp-native-evidence.yml").read_text(encoding="utf-8").replace(
        "group: xp-native-evidence-${{ inputs.target }}-${{ inputs.release_tag }}",
        "group: xp-native-evidence",
    )

    errors = checker.check_xp_native_evidence_workflow(workflow)

    assert any("target/release-scoped concurrency group" in error for error in errors)


def test_xp_native_evidence_workflow_requires_concurrency_at_top_level() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/xp-native-evidence.yml").read_text(encoding="utf-8")
    top_level_block = (
        "concurrency:\n"
        "  group: xp-native-evidence-${{ inputs.target }}-${{ inputs.release_tag }}\n"
        "  cancel-in-progress: false\n\n"
    )
    workflow = workflow.replace(top_level_block, "")
    workflow = workflow.replace(
        "  xp-native-evidence:\n",
        "  xp-native-evidence:\n"
        "    concurrency:\n"
        "      group: xp-native-evidence-${{ inputs.target }}-${{ inputs.release_tag }}\n"
        "      cancel-in-progress: false\n",
        1,
    )

    errors = checker.check_xp_native_evidence_workflow(workflow)

    assert "XP native evidence workflow missing top-level concurrency gate: concurrency:" in errors


def test_xp_native_evidence_workflow_rejects_cancelling_evidence_runs() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/xp-native-evidence.yml").read_text(encoding="utf-8").replace(
        "cancel-in-progress: false",
        "cancel-in-progress: true",
    )

    errors = checker.check_xp_native_evidence_workflow(workflow)

    assert any("non-cancelling evidence concurrency" in error for error in errors)


def test_xp_native_evidence_workflow_requires_scoped_artifact_name() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/xp-native-evidence.yml").read_text(encoding="utf-8").replace(
        'xp-native-evidence-${{ inputs.target }}-${{ inputs.release_tag }}',
        "xp-native-evidence",
    )

    errors = checker.check_xp_native_evidence_workflow(workflow)

    assert any("target/release scoped source artifact name" in error for error in errors)
    assert any("target/release scoped uploaded artifact" in error for error in errors)


def test_xp_native_evidence_workflow_requires_collector_boundary() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/xp-native-evidence.yml").read_text(encoding="utf-8").replace(
        "XP evidence collector validates staged proof captured on real Windows XP hosts; "
        "run scripts/xp_smoke_runner.cmd after this workflow starts so smoke proof binds "
        "the printed source run metadata.",
        "XP evidence workflow validates staged proof.",
    )

    errors = checker.check_xp_native_evidence_workflow(workflow)

    assert any("XP host versus collector boundary" in error for error in errors)


def test_xp_native_evidence_workflow_requires_bounded_staged_input_wait() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/xp-native-evidence.yml").read_text(encoding="utf-8").replace(
        "python scripts/wait_for_xp_native_evidence_inputs.py",
        "python scripts/removed.py",
    )

    errors = checker.check_xp_native_evidence_workflow(workflow)

    assert any("bounded stable wait for staged XP evidence inputs" in error for error in errors)


def test_xp_native_evidence_workflow_requires_ordered_evidence_steps() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/xp-native-evidence.yml").read_text(encoding="utf-8")
    wait_step = (
        '      - name: Wait for staged XP evidence inputs\n'
        '        run: python scripts/wait_for_xp_native_evidence_inputs.py --assets-dir "${{ inputs.assets_dir }}" '
        '--evidence-file "${{ inputs.evidence_file }}" --evidence-dir "${{ inputs.evidence_dir }}" '
        "--timeout-seconds 2700 --poll-seconds 10 --stable-polls 2\n"
    )
    validate_step = (
        '      - name: Validate XP native evidence\n'
        '        run: python scripts/check_xp_native_evidence.py --evidence "${{ inputs.evidence_file }}" '
        '--assets-dir "${{ inputs.assets_dir }}" --evidence-dir "${{ inputs.evidence_dir }}"\n'
    )
    workflow = workflow.replace(wait_step, "", 1).replace(validate_step, validate_step + wait_step, 1)

    errors = checker.check_xp_native_evidence_workflow(workflow)

    assert (
        "xp-native-evidence job protected evidence step order is invalid: "
        "XP native evidence validation must run after staged input wait"
    ) in errors


def test_xp_native_evidence_workflow_validates_dispatch_before_output_directory_creation() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/xp-native-evidence.yml").read_text(encoding="utf-8")
    create_step = (
        '      - name: Create XP evidence output directory\n'
        '        run: python -c "from pathlib import Path; '
        "Path('xp-evidence-output/${{ inputs.target }}/${{ inputs.release_tag }}').mkdir(parents=True, "
        'exist_ok=True)"\n'
    )
    validate_step = (
        '      - name: Validate XP evidence dispatch inputs\n'
        '        run: python scripts/check_xp_native_evidence_dispatch_inputs.py --target "${{ inputs.target }}" '
        '--release-tag "${{ inputs.release_tag }}" --release-asset-base-url "${{ inputs.release_asset_base_url }}" '
        '--workflow-run-url "${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}" '
        '--workflow-ref-name "${{ github.ref_name }}" --source-head-sha "${{ github.sha }}" '
        '--source-run-attempt "${{ github.run_attempt }}" --assets-dir "${{ inputs.assets_dir }}" '
        '--evidence-file "${{ inputs.evidence_file }}" --evidence-dir "${{ inputs.evidence_dir }}"\n'
    )
    workflow = workflow.replace(create_step, "", 1).replace(validate_step, create_step + validate_step, 1)

    errors = checker.check_xp_native_evidence_workflow(workflow)

    assert (
        "xp-native-evidence job protected evidence step order is invalid: "
        "target/release scoped XP evidence output directory creation must run after dispatch input preflight"
    ) in errors


def test_xp_native_evidence_workflow_requires_wait_helper_file(monkeypatch, tmp_path: Path) -> None:
    checker = _load_checker()
    missing = tmp_path / "missing-helper.py"
    monkeypatch.setattr(checker, "WAIT_HELPER_PATH", missing)

    errors = checker.check_xp_native_evidence_workflow()

    assert "XP staged evidence wait helper must exist in checkout at scripts/wait_for_xp_native_evidence_inputs.py" in errors


def test_xp_native_evidence_workflow_rejects_symlinked_wait_helper(monkeypatch, tmp_path: Path) -> None:
    checker = _load_checker()
    real_helper = tmp_path / "real-helper.py"
    helper_link = tmp_path / "helper-link.py"
    real_helper.write_text("print('helper')\n", encoding="utf-8")
    _symlink_or_skip(real_helper, helper_link)
    monkeypatch.setattr(checker, "WAIT_HELPER_PATH", helper_link)

    errors = checker.check_xp_native_evidence_workflow()

    assert "XP staged evidence wait helper must not be a symlink: scripts/wait_for_xp_native_evidence_inputs.py" in errors


def test_xp_native_evidence_workflow_rejects_untracked_wait_helper(monkeypatch, tmp_path: Path) -> None:
    checker = _load_checker()
    helper = tmp_path / "wait-helper.py"
    helper.write_text("print('helper')\n", encoding="utf-8")
    monkeypatch.setattr(checker, "WAIT_HELPER_PATH", helper)
    monkeypatch.setattr(checker, "is_git_tracked", lambda relative: False)

    errors = checker.check_xp_native_evidence_workflow()

    assert "XP staged evidence wait helper must be tracked by git: scripts/wait_for_xp_native_evidence_inputs.py" in errors


def test_xp_native_evidence_workflow_rejects_untracked_script_dependency(monkeypatch, tmp_path: Path) -> None:
    checker = _load_checker()
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    dependency = scripts_dir / "stage_xp_native_evidence_upload.py"
    dependency.write_text("print('stage')\n", encoding="utf-8")
    monkeypatch.setattr(checker, "ROOT", tmp_path)
    monkeypatch.setattr(checker, "is_git_tracked", lambda relative: False)

    errors = checker.check_workflow_script_dependencies(
        (Path("scripts") / "stage_xp_native_evidence_upload.py",)
    )

    assert (
        "XP native evidence workflow script dependency must be tracked by git: "
        "scripts/stage_xp_native_evidence_upload.py"
    ) in errors


def test_xp_native_evidence_workflow_rejects_missing_script_dependency(tmp_path: Path, monkeypatch) -> None:
    checker = _load_checker()
    monkeypatch.setattr(checker, "ROOT", tmp_path)

    errors = checker.check_workflow_script_dependencies(
        (Path("scripts") / "make_xp_native_evidence_bundle.py",)
    )

    assert (
        "XP native evidence workflow script dependency must exist in checkout at "
        "scripts/make_xp_native_evidence_bundle.py"
    ) in errors


def test_xp_native_evidence_workflow_discovers_new_script_references() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/xp-native-evidence.yml").read_text(encoding="utf-8")
    workflow = workflow.replace(
        "      - name: Validate XP native evidence\n",
        "      - name: Extra local XP proof helper\n"
        "        run: python scripts/local_only_xp_proof.py\n\n"
        "      - name: Validate XP native evidence\n",
        1,
    )

    errors = checker.check_xp_native_evidence_workflow(workflow)

    assert (
        "XP native evidence workflow script dependency must exist in checkout at "
        "scripts/local_only_xp_proof.py"
    ) in errors


def test_xp_native_evidence_workflow_requires_printed_source_metadata() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/xp-native-evidence.yml").read_text(encoding="utf-8").replace(
        "XP evidence source workflow run: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}",
        "XP evidence source workflow run: missing",
    )

    errors = checker.check_xp_native_evidence_workflow(workflow)

    assert any("printed XP source workflow run metadata" in error for error in errors)


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


def test_xp_native_evidence_workflow_requires_candidate_local_evidence_root() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/xp-native-evidence.yml").read_text(encoding="utf-8").replace(
        " --local-evidence-root .",
        "",
        1,
    )

    errors = checker.check_xp_native_evidence_workflow(workflow)

    assert any("candidate local evidence root binding" in error for error in errors)


def test_xp_native_evidence_workflow_requires_candidate_staged_upload_out_dir() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/xp-native-evidence.yml").read_text(encoding="utf-8").replace(
        ' --staged-upload-out-dir "platform-evidence-upload/${{ inputs.target }}/${{ inputs.release_tag }}"',
        "",
        1,
    )

    errors = checker.check_xp_native_evidence_workflow(workflow)

    assert any("candidate staged upload output binding" in error for error in errors)


def test_xp_native_evidence_workflow_requires_candidate_xp_evidence_output_dir() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/xp-native-evidence.yml").read_text(encoding="utf-8").replace(
        ' --xp-evidence-output-dir "xp-evidence-output/${{ inputs.target }}/${{ inputs.release_tag }}"',
        "",
        1,
    )

    errors = checker.check_xp_native_evidence_workflow(workflow)

    assert any("candidate XP evidence output binding" in error for error in errors)


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


def test_xp_native_evidence_workflow_requires_dispatch_source_head_sha() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/xp-native-evidence.yml").read_text(encoding="utf-8").replace(
        ' --source-head-sha "${{ github.sha }}"',
        "",
        1,
    )

    errors = checker.check_xp_native_evidence_workflow(workflow)

    assert any("XP dispatch source head SHA binding" in error for error in errors)


def test_xp_native_evidence_workflow_requires_dispatch_release_tag_ref_binding() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/xp-native-evidence.yml").read_text(encoding="utf-8").replace(
        ' --workflow-ref-name "${{ github.ref_name }}"',
        "",
        1,
    )

    errors = checker.check_xp_native_evidence_workflow(workflow)

    assert any("XP dispatch input preflight" in error for error in errors)


def test_xp_native_evidence_workflow_requires_dispatch_source_run_attempt() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/xp-native-evidence.yml").read_text(encoding="utf-8").replace(
        ' --source-run-attempt "${{ github.run_attempt }}"',
        "",
        1,
    )

    errors = checker.check_xp_native_evidence_workflow(workflow)

    assert any("XP dispatch source run-attempt binding" in error for error in errors)


def test_xp_native_evidence_workflow_requires_local_goal_preflight() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/xp-native-evidence.yml").read_text(encoding="utf-8").replace(
        "python scripts/check_platform_goal_local_evidence.py",
        "python scripts/removed.py",
    )

    errors = checker.check_xp_native_evidence_workflow(workflow)

    assert any("XP local protected goal evidence preflight" in error for error in errors)


def test_xp_native_evidence_workflow_requires_local_goal_preflight_repository() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/xp-native-evidence.yml").read_text(encoding="utf-8").replace(
        ' --repository "${{ github.repository }}"',
        "",
        1,
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


def test_xp_native_evidence_workflow_rejects_unbalanced_github_expression() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/xp-native-evidence.yml").read_text(encoding="utf-8").replace(
        '${{ inputs.release_tag }}',
        '${{ inputs.release_tag }',
        1,
    )

    errors = checker.check_xp_native_evidence_workflow(workflow)

    assert any("unbalanced GitHub expression delimiters" in error for error in errors)


def test_xp_native_evidence_workflow_rejects_out_of_order_github_expression_delimiters() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/xp-native-evidence.yml").read_text(encoding="utf-8") + (
        "\n# malformed but count-balanced expression }} before ${{ inputs.release_tag\n"
    )

    errors = checker.check_xp_native_evidence_workflow(workflow)

    assert any("unbalanced GitHub expression delimiters" in error for error in errors)


def test_xp_native_evidence_workflow_rejects_malformed_scoped_upload_release_tag() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/xp-native-evidence.yml").read_text(encoding="utf-8").replace(
        '--evidence-output-dir "xp-evidence-output/${{ inputs.target }}/${{ inputs.release_tag }}"',
        '--evidence-output-dir "xp-evidence-output/${{ inputs.target }}/${{ inputs.release_tag }"',
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
        "path: platform-evidence-upload/${{ inputs.target }}/${{ inputs.release_tag }}/*",
        "path: |\n            ${{ inputs.assets_dir }}/*\n            xp-evidence-output/*",
    )

    errors = checker.check_xp_native_evidence_workflow(workflow)

    assert "xp-native-evidence job must not upload raw operator-supplied assets_dir wildcard" in errors
    assert "xp-native-evidence job must upload scoped staged files, not raw xp-evidence-output wildcard" in errors


def test_xp_native_evidence_workflow_requires_hidden_file_exclusion_for_upload() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/xp-native-evidence.yml").read_text(encoding="utf-8").replace(
        "          include-hidden-files: false\n",
        "",
    )

    errors = checker.check_xp_native_evidence_workflow(workflow)

    assert any("hidden file exclusion for evidence artifact upload" in error for error in errors)


def test_xp_native_evidence_workflow_requires_retained_source_artifact_upload() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/xp-native-evidence.yml").read_text(encoding="utf-8").replace(
        "          retention-days: 90\n",
        "",
    )

    errors = checker.check_xp_native_evidence_workflow(workflow)

    assert any("evidence artifact retention window" in error for error in errors)


def test_xp_native_evidence_dispatch_rejects_file_shaped_directory_inputs() -> None:
    checker = _load_dispatch_checker()

    errors = checker.check_xp_native_evidence_dispatch_inputs(
        target="windows-xp-native-x86",
        release_tag="v1.0.2",
        release_asset_base_url="https://github.com/example/remote-ops-workspace/releases/download/v1.0.2",
        workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/12345",
        workflow_ref_name="v1.0.2",
        source_head_sha="0123456789abcdef0123456789abcdef01234567",
        source_run_attempt="1",
        assets_dir="native-dist/windows-xp/windows-xp-native-x86/v1.0.2/artifacts.zip",
        evidence_file="evidence/windows-xp-native-x86/v1.0.2/xp-evidence.json",
        evidence_dir="evidence/windows-xp-native-x86/v1.0.2/proof.log",
    )

    assert "assets_dir must be a directory path, got 'native-dist/windows-xp/windows-xp-native-x86/v1.0.2/artifacts.zip'" in errors
    assert "evidence_dir must be a directory path, got 'evidence/windows-xp-native-x86/v1.0.2/proof.log'" in errors


def test_xp_native_evidence_dispatch_rejects_release_tag_ref_mismatch() -> None:
    checker = _load_dispatch_checker()

    errors = checker.check_xp_native_evidence_dispatch_inputs(
        target="windows-xp-native-x64",
        release_tag="v1.0.2",
        release_asset_base_url="https://github.com/example/remote-ops-workspace/releases/download/v1.0.2",
        workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/12345",
        workflow_ref_name="main",
        source_head_sha="0123456789abcdef0123456789abcdef01234567",
        source_run_attempt="1",
        assets_dir="native-dist/windows-xp/windows-xp-native-x64/v1.0.2",
        evidence_file="evidence/windows-xp-native-x64/v1.0.2/xp-evidence.json",
        evidence_dir="evidence/windows-xp-native-x64/v1.0.2/xp-smoke-evidence",
    )

    assert (
        "workflow_ref_name must match release_tag so evidence is dispatched from "
        "the release tag ref, got 'main'"
    ) in errors


def test_wait_for_xp_native_evidence_inputs_accepts_present_paths(tmp_path: Path) -> None:
    waiter = _load_waiter()
    assets_dir = tmp_path / "assets"
    evidence_dir = tmp_path / "evidence"
    evidence_file = evidence_dir / "xp-evidence.json"
    assets_dir.mkdir()
    evidence_dir.mkdir()
    evidence_file.write_text("{}", encoding="utf-8")
    (assets_dir / "artifact.zip").write_text("artifact", encoding="utf-8")
    (evidence_dir / "proof.txt").write_text("proof", encoding="utf-8")

    errors = waiter.wait_for_xp_native_evidence_inputs(
        assets_dir=assets_dir,
        evidence_file=evidence_file,
        evidence_dir=evidence_dir,
        timeout_seconds=0,
        poll_seconds=0.1,
        stable_polls=1,
    )

    assert errors == []


def test_wait_for_xp_native_evidence_inputs_waits_for_non_empty_staging(tmp_path: Path) -> None:
    waiter = _load_waiter()
    assets_dir = tmp_path / "assets"
    evidence_dir = tmp_path / "evidence"
    evidence_file = evidence_dir / "xp-evidence.json"
    assets_dir.mkdir()
    evidence_dir.mkdir()
    evidence_file.write_text("{}", encoding="utf-8")

    errors = waiter.wait_for_xp_native_evidence_inputs(
        assets_dir=assets_dir,
        evidence_file=evidence_file,
        evidence_dir=evidence_dir,
        timeout_seconds=0,
        poll_seconds=0.1,
        stable_polls=1,
    )

    assert errors == [
        f"assets_dir contains no files yet: {assets_dir}",
        f"evidence_dir contains no files yet: {evidence_dir}",
    ]


def test_wait_for_xp_native_evidence_inputs_requires_stable_snapshot(tmp_path: Path) -> None:
    waiter = _load_waiter()
    assets_dir = tmp_path / "assets"
    evidence_dir = tmp_path / "evidence"
    evidence_file = evidence_dir / "xp-evidence.json"
    assets_dir.mkdir()
    evidence_dir.mkdir()
    evidence_file.write_text("{}", encoding="utf-8")
    (assets_dir / "artifact.zip").write_text("artifact", encoding="utf-8")
    (evidence_dir / "proof.txt").write_text("proof", encoding="utf-8")

    errors = waiter.wait_for_xp_native_evidence_inputs(
        assets_dir=assets_dir,
        evidence_file=evidence_file,
        evidence_dir=evidence_dir,
        timeout_seconds=0,
        poll_seconds=0.1,
        stable_polls=2,
    )

    assert errors == [
        "staged XP evidence inputs did not remain stable for 2 consecutive poll(s) before timeout"
    ]


def test_wait_for_xp_native_evidence_inputs_reports_missing_paths(tmp_path: Path) -> None:
    waiter = _load_waiter()

    errors = waiter.wait_for_xp_native_evidence_inputs(
        assets_dir=tmp_path / "missing-assets",
        evidence_file=tmp_path / "missing-evidence.json",
        evidence_dir=tmp_path / "missing-evidence",
        timeout_seconds=0,
        poll_seconds=0.1,
        stable_polls=1,
    )

    assert errors == [
        f"assets_dir is not a directory: {tmp_path / 'missing-assets'}",
        f"evidence_file is not a file: {tmp_path / 'missing-evidence.json'}",
        f"evidence_dir is not a directory: {tmp_path / 'missing-evidence'}",
    ]


def test_wait_for_xp_native_evidence_inputs_rejects_symlinked_roots(tmp_path: Path) -> None:
    waiter = _load_waiter()
    real_assets_dir = tmp_path / "real-assets"
    real_evidence_dir = tmp_path / "real-evidence"
    real_evidence_file = real_evidence_dir / "xp-evidence.json"
    assets_link = tmp_path / "assets-link"
    evidence_link = tmp_path / "evidence-link"
    real_assets_dir.mkdir()
    real_evidence_dir.mkdir()
    real_evidence_file.write_text("{}", encoding="utf-8")
    (real_assets_dir / "artifact.zip").write_text("artifact", encoding="utf-8")
    (real_evidence_dir / "proof.txt").write_text("proof", encoding="utf-8")
    _symlink_or_skip(real_assets_dir, assets_link, target_is_directory=True)
    _symlink_or_skip(real_evidence_file, evidence_link)

    errors = waiter.wait_for_xp_native_evidence_inputs(
        assets_dir=assets_link,
        evidence_file=evidence_link,
        evidence_dir=real_evidence_dir,
        timeout_seconds=0,
        poll_seconds=0.1,
        stable_polls=1,
    )

    assert f"assets_dir must not be a symlink: {assets_link}" in errors
    assert f"evidence_file must not be a symlink: {evidence_link}" in errors


def test_wait_for_xp_native_evidence_inputs_rejects_symlinked_staged_files(tmp_path: Path) -> None:
    waiter = _load_waiter()
    assets_dir = tmp_path / "assets"
    evidence_dir = tmp_path / "evidence"
    evidence_file = evidence_dir / "xp-evidence.json"
    real_artifact = tmp_path / "real-artifact.zip"
    artifact_link = assets_dir / "artifact-link.zip"
    assets_dir.mkdir()
    evidence_dir.mkdir()
    evidence_file.write_text("{}", encoding="utf-8")
    real_artifact.write_text("artifact", encoding="utf-8")
    (evidence_dir / "proof.txt").write_text("proof", encoding="utf-8")
    _symlink_or_skip(real_artifact, artifact_link)

    errors = waiter.wait_for_xp_native_evidence_inputs(
        assets_dir=assets_dir,
        evidence_file=evidence_file,
        evidence_dir=evidence_dir,
        timeout_seconds=0,
        poll_seconds=0.1,
        stable_polls=1,
    )

    assert f"assets_dir staged file must not be a symlink: {artifact_link}" in errors


def test_wait_for_xp_native_evidence_inputs_rejects_symlinked_parent_directory(tmp_path: Path) -> None:
    waiter = _load_waiter()
    real_parent = tmp_path / "real-parent"
    parent_link = tmp_path / "parent-link"
    real_parent.mkdir()
    _symlink_or_skip(real_parent, parent_link, target_is_directory=True)
    assets_dir = parent_link / "assets"
    evidence_dir = parent_link / "evidence"
    evidence_file = evidence_dir / "xp-evidence.json"
    assets_dir.mkdir()
    evidence_dir.mkdir()
    evidence_file.write_text("{}", encoding="utf-8")
    (assets_dir / "artifact.zip").write_text("artifact", encoding="utf-8")
    (evidence_dir / "proof.txt").write_text("proof", encoding="utf-8")

    errors = waiter.wait_for_xp_native_evidence_inputs(
        assets_dir=assets_dir,
        evidence_file=evidence_file,
        evidence_dir=evidence_dir,
        timeout_seconds=0,
        poll_seconds=0.1,
        stable_polls=1,
    )

    assert f"assets_dir path must not contain symlinked parent directory: {parent_link}" in errors
    assert f"evidence_file path must not contain symlinked parent directory: {parent_link}" in errors
    assert f"evidence_dir path must not contain symlinked parent directory: {parent_link}" in errors


def test_wait_for_xp_native_evidence_inputs_allows_macos_var_temp_alias(monkeypatch) -> None:
    waiter = _load_waiter()
    original_resolve = Path.resolve

    def fake_is_symlink(self: Path) -> bool:
        return self.as_posix() == "/var"

    def fake_resolve(self: Path, strict: bool = False) -> Path:
        if self.as_posix() == "/var":
            return Path("/private/var")
        return original_resolve(self, strict=strict)

    monkeypatch.setattr(waiter.sys, "platform", "darwin")
    monkeypatch.setattr(Path, "is_symlink", fake_is_symlink)
    monkeypatch.setattr(Path, "resolve", fake_resolve)

    assert (
        waiter.check_parent_directories_not_symlinked(
            "assets_dir",
            Path("/var/folders/pytest/xp-staged/assets"),
        )
        == []
    )


def test_wait_for_xp_native_evidence_inputs_rejects_symlinked_staged_directories(tmp_path: Path) -> None:
    waiter = _load_waiter()
    assets_dir = tmp_path / "assets"
    evidence_dir = tmp_path / "evidence"
    evidence_file = evidence_dir / "xp-evidence.json"
    real_nested = tmp_path / "real-nested"
    nested_link = assets_dir / "nested-link"
    assets_dir.mkdir()
    evidence_dir.mkdir()
    real_nested.mkdir()
    evidence_file.write_text("{}", encoding="utf-8")
    (assets_dir / "artifact.zip").write_text("artifact", encoding="utf-8")
    (evidence_dir / "proof.txt").write_text("proof", encoding="utf-8")
    _symlink_or_skip(real_nested, nested_link, target_is_directory=True)

    errors = waiter.wait_for_xp_native_evidence_inputs(
        assets_dir=assets_dir,
        evidence_file=evidence_file,
        evidence_dir=evidence_dir,
        timeout_seconds=0,
        poll_seconds=0.1,
        stable_polls=1,
    )

    assert f"assets_dir staged path must not be a symlink: {nested_link}" in errors


def _symlink_or_skip(target: Path, link: Path, *, target_is_directory: bool = False) -> None:
    try:
        os.symlink(target, link, target_is_directory=target_is_directory)
    except (OSError, NotImplementedError) as exc:
        pytest.skip(f"symlink creation unavailable in this environment: {exc}")


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


def _load_waiter():
    path = Path("scripts/wait_for_xp_native_evidence_inputs.py")
    spec = importlib.util.spec_from_file_location("wait_for_xp_native_evidence_inputs", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

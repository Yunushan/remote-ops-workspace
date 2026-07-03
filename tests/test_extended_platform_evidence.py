from __future__ import annotations

import importlib.util
import json
import shutil
import sys
from pathlib import Path


def test_extended_platform_evidence_workflow_passes_current_tree() -> None:
    checker = _load_script("check_extended_platform_evidence")

    assert checker.main() == 0


def test_extended_platform_evidence_rejects_publish_trigger() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8")
    workflow += "\npush:\n"

    errors = checker.check_extended_platform_evidence(workflow)

    assert "extended platform evidence workflow must not run on push" in errors


def test_extended_platform_evidence_rejects_write_permissions() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8").replace(
        "permissions:\n  contents: read",
        "permissions:\n  contents: read\n  actions: write",
    )

    errors = checker.check_extended_platform_evidence(workflow)

    assert "extended platform evidence workflow must not request write permissions" in errors


def test_extended_platform_evidence_requires_clean_checkout() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8").replace(
        "          clean: true\n",
        "",
    )

    errors = checker.check_extended_platform_evidence(workflow)

    assert any("self-hosted checkout workspace cleanup" in error for error in errors)


def test_extended_platform_evidence_rejects_clean_setting_outside_checkout_step() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8")
    block = checker.workflow_job_block(workflow, "linux-i386-native-evidence")
    assert block
    mutated = block.replace("          clean: true\n", "", 1).replace(
        "      - name: Validate Linux i386 evidence dispatch inputs\n",
        "      - name: Misleading clean setting\n"
        "        run: echo clean\n"
        "        env:\n"
        "          clean: true\n"
        "      - name: Validate Linux i386 evidence dispatch inputs\n",
        1,
    )
    workflow = workflow.replace(block, mutated, 1)

    errors = checker.check_extended_platform_evidence(workflow)

    assert "linux-i386-native-evidence checkout step missing workspace cleanup: clean: true" in errors


def test_extended_platform_evidence_rejects_persist_credentials_outside_checkout_step() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8")
    block = checker.workflow_job_block(workflow, "linux-armhf-native-evidence")
    assert block
    mutated = block.replace("          persist-credentials: false\n", "", 1).replace(
        "      - name: Validate Linux armhf evidence dispatch inputs\n",
        "      - name: Misleading credential setting\n"
        "        run: echo persist\n"
        "        env:\n"
        "          persist-credentials: false\n"
        "      - name: Validate Linux armhf evidence dispatch inputs\n",
        1,
    )
    workflow = workflow.replace(block, mutated, 1)

    errors = checker.check_extended_platform_evidence(workflow)

    assert (
        "linux-armhf-native-evidence checkout step missing credential isolation: persist-credentials: false"
        in errors
    )


def test_extended_platform_evidence_forces_bash_shell_for_linux_steps() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8").replace(
        "defaults:\n  run:\n    shell: bash\n\n",
        "",
        1,
    )

    errors = checker.check_extended_platform_evidence(workflow)

    assert "extended platform evidence workflow missing top-level Bash run default: defaults:" in errors


def test_extended_platform_evidence_rejects_job_level_only_bash_default() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8")
    workflow = workflow.replace("defaults:\n  run:\n    shell: bash\n\n", "", 1)
    workflow = workflow.replace(
        "  linux-i386-native-evidence:\n",
        "  linux-i386-native-evidence:\n"
        "    defaults:\n"
        "      run:\n"
        "        shell: bash\n",
        1,
    )

    errors = checker.check_extended_platform_evidence(workflow)

    assert "extended platform evidence workflow missing top-level Bash run default: defaults:" in errors


def test_extended_platform_evidence_requires_strict_shell_safety() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8").replace(
        "          set -euo pipefail\n",
        "",
        1,
    )

    errors = checker.check_extended_platform_evidence(workflow)

    assert any("run step 1 missing strict shell safety: set -euo pipefail" in error for error in errors)


def test_extended_platform_evidence_rejects_pipefail_only_smoke_step() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8").replace(
        "      - name: Smoke Linux i386 native artifacts\n"
        "        run: |\n"
        "          set -euo pipefail\n",
        "      - name: Smoke Linux i386 native artifacts\n"
        "        run: |\n"
        "          set -o pipefail\n",
        1,
    )

    errors = checker.check_extended_platform_evidence(workflow)

    assert any("missing strict shell safety: set -euo pipefail" in error for error in errors)


def test_extended_platform_evidence_requires_target_release_concurrency() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8").replace(
        "group: extended-platform-evidence-${{ inputs.target }}-${{ inputs.release_tag }}",
        "group: extended-platform-evidence",
    )

    errors = checker.check_extended_platform_evidence(workflow)

    assert any("target/release-scoped concurrency group" in error for error in errors)


def test_extended_platform_evidence_requires_concurrency_at_top_level() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8")
    top_level_block = (
        "concurrency:\n"
        "  group: extended-platform-evidence-${{ inputs.target }}-${{ inputs.release_tag }}\n"
        "  cancel-in-progress: false\n\n"
    )
    workflow = workflow.replace(top_level_block, "")
    workflow = workflow.replace(
        "  linux-i386-native-evidence:\n",
        "  linux-i386-native-evidence:\n"
        "    concurrency:\n"
        "      group: extended-platform-evidence-${{ inputs.target }}-${{ inputs.release_tag }}\n"
        "      cancel-in-progress: false\n",
        1,
    )

    errors = checker.check_extended_platform_evidence(workflow)

    assert "extended platform evidence workflow missing top-level concurrency gate: concurrency:" in errors


def test_extended_platform_evidence_rejects_cancelling_evidence_runs() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8").replace(
        "cancel-in-progress: false",
        "cancel-in-progress: true",
    )

    errors = checker.check_extended_platform_evidence(workflow)

    assert any("non-cancelling evidence concurrency" in error for error in errors)


def test_extended_platform_evidence_rejects_unbalanced_github_expression() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8").replace(
        "${{ inputs.release_tag }}",
        "${{ inputs.release_tag }",
        1,
    )

    errors = checker.check_extended_platform_evidence(workflow)

    assert any("unbalanced GitHub expression delimiters" in error for error in errors)


def test_extended_platform_evidence_rejects_out_of_order_github_expression_delimiters() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8") + (
        "\n# malformed but count-balanced expression }} before ${{ inputs.release_tag\n"
    )

    errors = checker.check_extended_platform_evidence(workflow)

    assert any("unbalanced GitHub expression delimiters" in error for error in errors)


def test_extended_platform_evidence_requires_ordered_linux_evidence_steps() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8")
    preflight_marker = "      - name: Preflight Linux i386 local platform goal evidence\n"
    next_marker = "      - name: Generate Linux i386 accepted-evidence candidate\n"
    validation_marker = "      - name: Validate Linux i386 promotion artifacts\n"
    before_preflight, after_preflight_marker = workflow.split(preflight_marker, 1)
    preflight_body, after_preflight = after_preflight_marker.split(next_marker, 1)
    preflight_step = preflight_marker + preflight_body
    workflow = before_preflight + next_marker + after_preflight
    workflow = workflow.replace(validation_marker, preflight_step + validation_marker, 1)

    errors = checker.check_extended_platform_evidence(workflow)

    assert (
        "linux-i386-native-evidence protected evidence step order is invalid: "
        "local protected goal evidence preflight must run after strict promotion artifact validation"
    ) in errors


def test_extended_platform_evidence_requires_candidate_record_generation() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8")
    workflow = workflow.replace("python scripts/make_platform_verified_evidence_record.py", "python scripts/removed.py")

    errors = checker.check_extended_platform_evidence(workflow)

    assert any("accepted-evidence record generation" in error for error in errors)


def test_extended_platform_evidence_requires_local_goal_preflight() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8")
    workflow = workflow.replace("python scripts/check_platform_goal_local_evidence.py", "python scripts/removed.py", 1)

    errors = checker.check_extended_platform_evidence(workflow)

    assert any("local protected goal evidence preflight" in error for error in errors)


def test_extended_platform_evidence_requires_review_bundle_generation() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8")
    workflow = workflow.replace("python scripts/make_extended_linux_evidence_bundle.py", "python scripts/removed.py")

    errors = checker.check_extended_platform_evidence(workflow)

    assert any("review evidence bundle generation" in error for error in errors)


def test_extended_platform_evidence_requires_scoped_review_bundle_output() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8")
    workflow = workflow.replace(
        "            --out-dir platform-evidence-staging/linux-i386/${{ inputs.release_tag }}/artifacts",
        "            --out-dir bundle",
        1,
    )

    errors = checker.check_extended_platform_evidence(workflow)

    assert any("target/release scoped review bundle output directory" in error for error in errors)
    assert (
        "linux-i386-native-evidence must use target/release-scoped platform-evidence-staging paths, "
        "found --out-dir bundle"
    ) in errors


def test_extended_platform_evidence_requires_builder_release_context() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8")
    workflow = workflow.replace(
        "          python3 scripts/check_extended_platform_builder.py \\\n"
        "            --target linux-i386 \\\n"
        '            --release-tag "${{ inputs.release_tag }}" \\\n',
        "          python3 scripts/check_extended_platform_builder.py \\\n"
        "            --target linux-i386 \\\n",
        1,
    )

    errors = checker.check_extended_platform_evidence(workflow)

    assert any(
        "builder identity preflight must bind release_tag, workflow_run_url, workflow_run_attempt and source_head_sha"
        in error
        for error in errors
    )


def test_extended_platform_evidence_requires_release_tag_env_for_native_build() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8").replace(
        "    env:\n      RELEASE_TAG: ${{ inputs.release_tag }}\n",
        "",
        1,
    )

    errors = checker.check_extended_platform_evidence(workflow)

    assert any("release-tag environment binding for native build script" in error for error in errors)


def test_extended_platform_evidence_requires_builder_workflow_run_attempt() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8").replace(
        '            --workflow-run-attempt "${{ github.run_attempt }}" \\\n',
        "",
        1,
    )

    errors = checker.check_extended_platform_evidence(workflow)

    assert any("builder workflow run-attempt evidence" in error for error in errors)


def test_extended_platform_evidence_requires_smoke_workflow_run_attempt() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8").replace(
        ' --workflow-run-attempt "${{ github.run_attempt }}" --source-head-sha "${{ github.sha }}"',
        ' --source-head-sha "${{ github.sha }}"',
        1,
    )

    errors = checker.check_extended_platform_evidence(workflow)

    assert any("native installer smoke evidence capture" in error for error in errors)
    assert any("native smoke workflow run-attempt evidence" in error for error in errors)


def test_extended_platform_evidence_requires_smoke_builder_identity_binding() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8").replace(
        " --builder-evidence platform-evidence-staging/linux-i386/${{ inputs.release_tag }}/builder-identity-linux-i386.json",
        "",
        1,
    )

    errors = checker.check_extended_platform_evidence(workflow)

    assert any("native installer smoke evidence capture" in error for error in errors)


def test_extended_platform_evidence_requires_release_source_artifact_name() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8").replace(
        "            --release-source-artifact-name extended-linux-evidence-linux-i386-${{ inputs.release_tag }} \\\n",
        "",
        1,
    )

    errors = checker.check_extended_platform_evidence(workflow)

    assert any("release source artifact name binding" in error for error in errors)


def test_extended_platform_evidence_requires_release_source_run_attempt() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8").replace(
        '            --release-source-run-attempt "${{ github.run_attempt }}" \\\n',
        "",
        1,
    )

    errors = checker.check_extended_platform_evidence(workflow)

    assert any("release source run-attempt binding" in error for error in errors)


def test_extended_platform_evidence_requires_local_source_run_attempt() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8").replace(
        '            --linux-source-run-attempt "${{ github.run_attempt }}"\n',
        "\n",
        1,
    )

    errors = checker.check_extended_platform_evidence(workflow)

    assert any("local evidence source run-attempt binding" in error for error in errors)


def test_extended_platform_evidence_requires_candidate_local_evidence_root_binding() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8").replace(
        "            --local-evidence-root platform-evidence-staging \\\n",
        "",
        1,
    )

    errors = checker.check_extended_platform_evidence(workflow)

    assert any("local evidence preflight root binding" in error for error in errors)


def test_extended_platform_evidence_requires_candidate_staged_upload_out_dir() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8").replace(
        "            --staged-upload-out-dir platform-evidence-upload/linux-i386/${{ inputs.release_tag }} \\\n",
        "",
        1,
    )

    errors = checker.check_extended_platform_evidence(workflow)

    assert any("candidate staged upload output binding" in error for error in errors)


def test_extended_platform_evidence_requires_scoped_upload_staging() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8").replace(
        "python scripts/stage_extended_linux_evidence_upload.py",
        "python scripts/removed.py",
        1,
    )

    errors = checker.check_extended_platform_evidence(workflow)

    assert any("scoped Linux evidence upload staging" in error for error in errors)


def test_extended_platform_evidence_requires_target_scoped_artifact_copy() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8").replace(
        "cp native-dist/linux/remote-ops-workspace-${{ inputs.release_tag }}-linux-i386.deb platform-evidence-staging/linux-i386/${{ inputs.release_tag }}/artifacts/",
        "",
        1,
    )

    errors = checker.check_extended_platform_evidence(workflow)

    assert any("target-scoped artifact staging" in error for error in errors)


def test_extended_platform_evidence_rejects_old_native_dist_promotion_staging() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8").replace(
        "platform-evidence-staging/linux-i386/${{ inputs.release_tag }}/artifacts",
        "native-dist/linux/linux-i386",
        1,
    )

    errors = checker.check_extended_platform_evidence(workflow)

    assert any(
        "linux-i386-native-evidence must use target/release-scoped platform-evidence-staging paths" in error
        for error in errors
    )


def test_extended_platform_evidence_rejects_raw_upload_wildcard() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8").replace(
        "path: platform-evidence-upload/linux-i386/${{ inputs.release_tag }}/*",
        "path: native-dist/linux/*",
        1,
    )

    errors = checker.check_extended_platform_evidence(workflow)

    assert "linux-i386-native-evidence must upload scoped staged files, not raw native-dist/linux wildcard" in errors


def test_extended_platform_evidence_requires_hidden_file_exclusion_for_upload() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8").replace(
        "          include-hidden-files: false\n",
        "",
    )

    errors = checker.check_extended_platform_evidence(workflow)

    assert any("hidden file exclusion for evidence artifact upload" in error for error in errors)


def test_extended_platform_evidence_requires_retained_source_artifact_upload() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8").replace(
        "          retention-days: 90\n",
        "",
    )

    errors = checker.check_extended_platform_evidence(workflow)

    assert any("evidence artifact retention window" in error for error in errors)


def test_extended_platform_evidence_requires_dispatch_input_preflight() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8")
    workflow = workflow.replace("python3 scripts/check_extended_platform_dispatch_inputs.py", "python3 scripts/removed.py")

    errors = checker.check_extended_platform_evidence(workflow)

    assert any("dispatch input preflight" in error for error in errors)


def test_extended_platform_evidence_requires_dispatch_release_tag_ref_binding() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8").replace(
        '            --workflow-ref-name "${{ github.ref_name }}" \\\n',
        "",
        1,
    )

    errors = checker.check_extended_platform_evidence(workflow)

    assert any("release-tag workflow ref binding" in error for error in errors)


def test_extended_platform_evidence_requires_dispatch_source_head_sha() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8").replace(
        '            --source-head-sha "${{ github.sha }}" \\\n',
        "",
        1,
    )

    errors = checker.check_extended_platform_evidence(workflow)

    assert any("workflow_ref_name, source_head_sha and source_run_attempt" in error for error in errors)


def test_extended_platform_evidence_requires_dispatch_source_run_attempt() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8").replace(
        '            --source-run-attempt "${{ github.run_attempt }}"\n',
        "\n",
        1,
    )

    errors = checker.check_extended_platform_evidence(workflow)

    assert any("workflow_ref_name, source_head_sha and source_run_attempt" in error for error in errors)


def test_extended_platform_evidence_rejects_untracked_script_dependency(
    monkeypatch,
    tmp_path: Path,
) -> None:
    checker = _load_script("check_extended_platform_evidence")
    scripts_dir = tmp_path / "scripts"
    scripts_dir.mkdir()
    dependency = scripts_dir / "stage_extended_linux_evidence_upload.py"
    dependency.write_text("print('stage')\n", encoding="utf-8")
    monkeypatch.setattr(checker, "ROOT", tmp_path)
    monkeypatch.setattr(checker, "is_git_tracked", lambda relative: False)

    errors = checker.check_workflow_script_dependencies(
        (Path("scripts") / "stage_extended_linux_evidence_upload.py",)
    )

    assert (
        "extended platform evidence workflow script dependency must be tracked by git: "
        "scripts/stage_extended_linux_evidence_upload.py"
    ) in errors


def test_extended_platform_evidence_rejects_missing_script_dependency(
    monkeypatch,
    tmp_path: Path,
) -> None:
    checker = _load_script("check_extended_platform_evidence")
    monkeypatch.setattr(checker, "ROOT", tmp_path)

    errors = checker.check_workflow_script_dependencies(
        (Path("scripts") / "check_extended_platform_builder.py",)
    )

    assert (
        "extended platform evidence workflow script dependency must exist in checkout at "
        "scripts/check_extended_platform_builder.py"
    ) in errors


def test_extended_platform_evidence_discovers_new_script_references() -> None:
    checker = _load_script("check_extended_platform_evidence")
    workflow = Path(".github/workflows/extended-platform-evidence.yml").read_text(encoding="utf-8")
    workflow = workflow.replace(
        "      - name: Validate Linux i386 evidence dispatch inputs\n",
        "      - name: Extra local Linux proof helper\n"
        "        run: python scripts/local_only_linux_proof.py\n\n"
        "      - name: Validate Linux i386 evidence dispatch inputs\n",
        1,
    )

    errors = checker.check_extended_platform_evidence(workflow)

    assert (
        "extended platform evidence workflow script dependency must exist in checkout at "
        "scripts/local_only_linux_proof.py"
    ) in errors


def test_extended_platform_dispatch_input_validator_accepts_matching_inputs() -> None:
    checker = _load_script("check_extended_platform_dispatch_inputs")

    errors = _check_extended_dispatch_inputs(
        checker,
        target="linux-i386",
        release_tag="v1.0.2",
        release_asset_base_url="https://github.com/example/remote-ops-workspace/releases/download/v1.0.2",
        workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/12345",
    )

    assert errors == []


def test_extended_platform_dispatch_input_validator_rejects_release_tag_mismatch() -> None:
    checker = _load_script("check_extended_platform_dispatch_inputs")

    errors = _check_extended_dispatch_inputs(
        checker,
        target="linux-armhf",
        release_tag="v1.0.2",
        release_asset_base_url="https://github.com/example/remote-ops-workspace/releases/download/v1.0.3",
        workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/12345",
    )

    assert "release_asset_base_url tag must match release_tag v1.0.2, got v1.0.3" in errors


def test_extended_platform_dispatch_input_validator_rejects_trailing_slash_release_base() -> None:
    checker = _load_script("check_extended_platform_dispatch_inputs")

    errors = _check_extended_dispatch_inputs(
        checker,
        target="linux-i386",
        release_tag="v1.0.2",
        release_asset_base_url="https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/",
        workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/12345",
    )

    assert (
        "release_asset_base_url must be exactly "
        "https://github.com/<owner>/<repo>/releases/download/v1.0.2"
    ) in errors


def test_extended_platform_dispatch_input_validator_rejects_cross_repo_inputs() -> None:
    checker = _load_script("check_extended_platform_dispatch_inputs")

    errors = _check_extended_dispatch_inputs(
        checker,
        target="linux-armhf",
        release_tag="v1.0.2",
        release_asset_base_url="https://github.com/other/remote-ops-workspace/releases/download/v1.0.2",
        workflow_run_url="https://github.com/example/remote-ops-workspace/actions/runs/12345",
    )

    assert (
        "release_asset_base_url repository must match workflow_run_url repository "
        "example/remote-ops-workspace, got other/remote-ops-workspace"
    ) in errors


def test_extended_platform_dispatch_input_validator_rejects_malformed_repo_slug() -> None:
    checker = _load_script("check_extended_platform_dispatch_inputs")

    errors = _check_extended_dispatch_inputs(
        checker,
        target="linux-i386",
        release_tag="v1.0.2",
        release_asset_base_url=(
            "https://github.com/example/remote-ops-workspace?download=1/releases/download/v1.0.2"
        ),
        workflow_run_url="https://github.com/example/remote-ops-workspace?run=1/actions/runs/12345",
    )

    assert (
        "release_asset_base_url must be exactly "
        "https://github.com/<owner>/<repo>/releases/download/v1.0.2"
    ) in errors
    assert "workflow_run_url must be a GitHub Actions run URL" in errors


def test_extended_platform_dispatch_input_validator_rejects_invalid_source_head_sha() -> None:
    checker = _load_script("check_extended_platform_dispatch_inputs")

    errors = _check_extended_dispatch_inputs(
        checker,
        source_head_sha="ABCDEF0123456789ABCDEF0123456789ABCDEF01",
    )

    assert (
        "source_head_sha must be a lowercase 40-character Git SHA, "
        "got 'ABCDEF0123456789ABCDEF0123456789ABCDEF01'"
    ) in errors


def test_extended_platform_dispatch_input_validator_rejects_invalid_source_run_attempt() -> None:
    checker = _load_script("check_extended_platform_dispatch_inputs")

    errors = _check_extended_dispatch_inputs(checker, source_run_attempt="0")

    assert "source_run_attempt must be a positive integer, got '0'" in errors


def test_extended_platform_dispatch_input_validator_rejects_release_tag_ref_mismatch() -> None:
    checker = _load_script("check_extended_platform_dispatch_inputs")

    errors = _check_extended_dispatch_inputs(checker, workflow_ref_name="main")

    assert (
        "workflow_ref_name must match release_tag so evidence is dispatched from "
        "the release tag ref, got 'main'"
    ) in errors


def test_extended_platform_builder_accepts_matching_i386(monkeypatch) -> None:
    checker = _load_script("check_extended_platform_builder")
    monkeypatch.setattr(checker.sys, "platform", "linux")
    monkeypatch.setattr(checker.sys, "version_info", (3, 12, 0))
    monkeypatch.setattr(checker, "normalized_machine", lambda: "i686")
    monkeypatch.setattr(checker, "command_output", _linux_command_output("i686", "i386", "32"))
    monkeypatch.setattr(checker, "os_release", lambda: "Debian GNU/Linux 12 (bookworm)")
    monkeypatch.setattr(checker, "kernel_release", lambda: "6.1.0-i386-ci")
    monkeypatch.setattr(checker, "glibc_version", lambda: "glibc 2.36")
    monkeypatch.setattr(checker, "command_succeeds", lambda _command: True)
    monkeypatch.setattr(shutil, "which", lambda _tool: f"/usr/bin/{_tool}")

    assert checker.check_extended_platform_builder("linux-i386") == []


def test_extended_platform_builder_rejects_relative_tool_path(monkeypatch) -> None:
    checker = _load_script("check_extended_platform_builder")
    monkeypatch.setattr(checker.sys, "platform", "linux")
    monkeypatch.setattr(checker.sys, "version_info", (3, 12, 0))
    monkeypatch.setattr(checker, "normalized_machine", lambda: "i686")
    monkeypatch.setattr(checker, "command_output", _linux_command_output("i686", "i386", "32"))
    monkeypatch.setattr(checker, "command_succeeds", lambda _command: True)
    monkeypatch.setattr(shutil, "which", lambda tool: tool if tool == "bash" else f"/usr/bin/{tool}")

    errors = checker.check_extended_platform_builder("linux-i386")

    assert "linux-i386 builder required tool bash must resolve to an absolute path, got 'bash'" in errors


def test_extended_platform_builder_rejects_interactive_sudo(monkeypatch) -> None:
    checker = _load_script("check_extended_platform_builder")
    monkeypatch.setattr(checker.sys, "platform", "linux")
    monkeypatch.setattr(checker.sys, "version_info", (3, 12, 0))
    monkeypatch.setattr(checker, "normalized_machine", lambda: "i686")
    monkeypatch.setattr(checker, "command_output", _linux_command_output("i686", "i386", "32"))
    monkeypatch.setattr(checker, "command_succeeds", lambda command: command != ["sudo", "-n", "true"])
    monkeypatch.setattr(shutil, "which", lambda tool: f"/usr/bin/{tool}")

    errors = checker.check_extended_platform_builder("linux-i386")

    assert "linux-i386 builder sudo must be non-interactive: sudo -n true failed" in errors


def test_extended_platform_builder_writes_identity_evidence(tmp_path: Path, monkeypatch) -> None:
    checker = _load_script("check_extended_platform_builder")
    for name in (
        "GITHUB_ACTIONS",
        "GITHUB_SHA",
        "GITHUB_RUN_ATTEMPT",
        "GITHUB_RUN_ID",
        "GITHUB_REPOSITORY",
        "GITHUB_WORKFLOW_REF",
        "GITHUB_WORKFLOW_SHA",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("GITHUB_ACTIONS", "true")
    monkeypatch.setenv("GITHUB_SHA", "a" * 40)
    monkeypatch.setenv("GITHUB_RUN_ATTEMPT", "1")
    monkeypatch.setenv("GITHUB_RUN_ID", "12345")
    monkeypatch.setenv("GITHUB_REPOSITORY", "example/remote-ops-workspace")
    monkeypatch.setenv(
        "GITHUB_WORKFLOW_REF",
        "example/remote-ops-workspace/.github/workflows/extended-platform-evidence.yml@refs/heads/main",
    )
    monkeypatch.setenv("GITHUB_WORKFLOW_SHA", "a" * 40)
    monkeypatch.setattr(checker.sys, "platform", "linux")
    monkeypatch.setattr(checker.sys, "version_info", (3, 12, 0))
    monkeypatch.setattr(checker, "normalized_machine", lambda: "i686")
    monkeypatch.setattr(checker, "command_output", _linux_command_output("i686", "i386", "32"))
    monkeypatch.setattr(checker, "os_release", lambda: "Debian GNU/Linux 12 (bookworm)")
    monkeypatch.setattr(checker, "kernel_release", lambda: "6.1.0-i386-ci")
    monkeypatch.setattr(checker, "glibc_version", lambda: "glibc 2.36")
    monkeypatch.setattr(checker, "git_status_porcelain", lambda: "")
    monkeypatch.setattr(checker, "git_worktree_clean", lambda: True)
    monkeypatch.setattr(checker, "command_succeeds", lambda _command: True)
    monkeypatch.setattr(shutil, "which", lambda tool: f"/usr/bin/{tool}")
    output = tmp_path / "builder-identity-linux-i386.json"

    assert (
        checker.main(
            [
                "--target",
                "linux-i386",
                "--release-tag",
                "v1.0.2",
                "--workflow-run-url",
                "https://github.com/example/remote-ops-workspace/actions/runs/12345",
                "--workflow-run-attempt",
                "1",
                "--source-head-sha",
                "a" * 40,
                "--out",
                str(output),
            ]
        )
        == 0
    )

    data = json.loads(output.read_text(encoding="utf-8"))
    assert data["target"] == "linux-i386"
    assert data["release_tag"] == "v1.0.2"
    assert data["workflow_run_url"] == "https://github.com/example/remote-ops-workspace/actions/runs/12345"
    assert data["workflow_run_attempt"] == 1
    assert data["workflow_ref"] == (
        "example/remote-ops-workspace/.github/workflows/extended-platform-evidence.yml@refs/heads/main"
    )
    assert data["workflow_sha"] == "a" * 40
    assert data["source_head_sha"] == "a" * 40
    assert data["observed_git_head_sha"] == "a" * 40
    assert data["git_worktree_clean"] is True
    assert data["host_identity"] == {
        "schema_version": 1,
        "target": "linux-i386",
        "release_tag": "v1.0.2",
        "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "workflow_run_attempt": 1,
        "host_label": "linux-i386-builder",
        "evidence_run_id": "linux-i386-1-0-2-run-12345",
        "observed_at_utc": data["host_identity"]["observed_at_utc"],
        "operator_private_data_redacted": True,
    }
    assert data["host_identity"]["observed_at_utc"].endswith("Z")
    assert data["platform_machine"] == "i686"
    assert data["os_release"] == "Debian GNU/Linux 12 (bookworm)"
    assert data["kernel_release"] == "6.1.0-i386-ci"
    assert data["glibc_version"] == "glibc 2.36"
    assert data["uname_machine"] == "i686"
    assert data["dpkg_architecture"] == "i386"
    assert data["userland_bits"] == "32"
    assert data["required_tools"]["dpkg"] == "/usr/bin/dpkg"
    assert data["required_tools"]["dpkg-deb"] == "/usr/bin/dpkg-deb"
    assert data["required_tools"]["rpm"] == "/usr/bin/rpm"
    assert data["sudo_non_interactive"] is True


def test_extended_platform_builder_rejects_symlinked_identity_output(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checker = _load_script("check_extended_platform_builder")
    output = tmp_path / "builder-identity-linux-i386.json"
    output.write_text("{}\n", encoding="utf-8")

    def fake_is_symlink(self: Path) -> bool:
        return self == output

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = checker.check_builder_identity_output_path("linux-i386", output)

    assert errors == [f"builder identity output file must not be a symlink: {output}"]


def test_extended_platform_builder_rejects_symlinked_identity_output_parent(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checker = _load_script("check_extended_platform_builder")
    output_parent = tmp_path / "linked-output" / "linux-evidence"
    output = output_parent / "builder-identity-linux-i386.json"

    def fake_is_symlink(self: Path) -> bool:
        return self == tmp_path / "linked-output"

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = checker.check_builder_identity_output_path("linux-i386", output)

    assert errors == [
        "builder identity output directory path must not contain symlinked directories: "
        f"{tmp_path / 'linked-output'}"
    ]


def test_extended_platform_builder_rejects_file_shaped_identity_output_parent(
    tmp_path: Path,
) -> None:
    checker = _load_script("check_extended_platform_builder")
    output_parent = tmp_path / "linux-builder-evidence.zip"
    output = output_parent / "builder-identity-linux-i386.json"

    errors = checker.check_builder_identity_output_path("linux-i386", output)

    assert errors == [
        f"builder identity output directory must be a directory path, got {output_parent.as_posix()!r}"
    ]


def test_extended_platform_builder_rejects_reserved_workspace_identity_output() -> None:
    checker = _load_script("check_extended_platform_builder")
    output_parent = Path(".github") / "linux-builder"
    output = output_parent / "builder-identity-linux-i386.json"

    errors = checker.check_builder_identity_output_path("linux-i386", output)

    assert errors == [
        "builder identity output directory must not point inside "
        f"reserved workspace directory '.github': {output_parent}"
    ]
    assert not output_parent.exists()


def test_extended_platform_builder_rejects_non_file_identity_output(tmp_path: Path) -> None:
    checker = _load_script("check_extended_platform_builder")
    output = tmp_path / "builder-identity-linux-i386.json"
    output.mkdir()

    errors = checker.check_builder_identity_output_path("linux-i386", output)

    assert errors == [f"builder identity output file must be a regular file: {output}"]


def test_extended_platform_builder_requires_release_context_for_identity_output(tmp_path: Path, monkeypatch) -> None:
    checker = _load_script("check_extended_platform_builder")
    monkeypatch.setattr(checker.sys, "platform", "linux")
    monkeypatch.setattr(checker.sys, "version_info", (3, 12, 0))
    monkeypatch.setattr(checker, "normalized_machine", lambda: "i686")
    monkeypatch.setattr(checker, "command_output", _linux_command_output("i686", "i386", "32"))
    monkeypatch.setattr(checker, "command_succeeds", lambda _command: True)
    monkeypatch.setattr(shutil, "which", lambda tool: f"/usr/bin/{tool}")

    result = checker.main(["--target", "linux-i386", "--out", str(tmp_path / "builder.json")])

    assert result == 1


def test_extended_platform_builder_rejects_wrong_arch(monkeypatch) -> None:
    checker = _load_script("check_extended_platform_builder")
    monkeypatch.setattr(checker.sys, "platform", "linux")
    monkeypatch.setattr(checker.sys, "version_info", (3, 12, 0))
    monkeypatch.setattr(checker, "normalized_machine", lambda: "x86_64")
    monkeypatch.setattr(checker, "command_output", _linux_command_output("x86_64", "amd64", "64"))
    monkeypatch.setattr(checker, "command_succeeds", lambda _command: True)
    monkeypatch.setattr(shutil, "which", lambda _tool: f"/usr/bin/{_tool}")

    errors = checker.check_extended_platform_builder("linux-armhf")

    assert any("linux-armhf builder architecture must be one of" in error for error in errors)
    assert any("linux-armhf uname -m must be one of" in error for error in errors)
    assert any("linux-armhf dpkg architecture must be one of" in error for error in errors)
    assert "linux-armhf userland bits must be 32, got 64" in errors


def _linux_command_output(uname: str, dpkg_arch: str, bits: str):
    def _output(command: list[str]) -> str:
        if command == ["uname", "-m"]:
            return uname
        if command == ["dpkg", "--print-architecture"]:
            return dpkg_arch
        if command == ["getconf", "LONG_BIT"]:
            return bits
        if command == ["openssl", "version"]:
            return "openssl 3.0.13"
        if command == ["git", "rev-parse", "HEAD"]:
            return "a" * 40
        return ""

    return _output


def _check_extended_dispatch_inputs(checker, **overrides):
    values = {
        "target": "linux-i386",
        "release_tag": "v1.0.2",
        "release_asset_base_url": "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2",
        "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "workflow_ref_name": "v1.0.2",
        "source_head_sha": "0123456789abcdef0123456789abcdef01234567",
        "source_run_attempt": "1",
    }
    values.update(overrides)
    return checker.check_extended_platform_dispatch_inputs(**values)


def _load_script(name: str):
    path = Path("scripts") / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

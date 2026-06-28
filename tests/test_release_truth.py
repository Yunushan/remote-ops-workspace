from __future__ import annotations

import importlib.util
from pathlib import Path


def test_release_truth_checker_passes_current_tree() -> None:
    checker = _load_release_truth_checker()

    assert checker.main() == 0


def test_release_truth_checker_tracks_default_workflow_arches() -> None:
    checker = _load_release_truth_checker()

    assert checker.WORKFLOW_ARCHES["windows-native"] == {"x86", "x64", "arm64"}
    assert checker.WORKFLOW_ARCHES["macos-native"] == {"x64", "arm64"}
    assert checker.WORKFLOW_ARCHES["linux-native"] == {"x86_64", "aarch64"}


def test_release_truth_checker_rejects_stale_default_linux_patterns() -> None:
    checker = _load_release_truth_checker()

    assert "remote-ops-workspace-v1.0.2-linux-<i386|amd64|armhf|arm64>.deb" in (
        checker.STALE_DEFAULT_ARTIFACT_SNIPPETS
    )
    assert "remote-ops-workspace-v1.0.2-linux-<amd64|arm64>.deb" in checker.REQUIRED_DOC_SNIPPETS


def test_release_truth_checker_requires_linux_smoke_git_head_docs() -> None:
    checker = _load_release_truth_checker()

    assert "observed_git_head_sha" in checker.REQUIRED_DOC_SNIPPETS
    assert "git_worktree_clean" in checker.REQUIRED_DOC_SNIPPETS
    assert "observed Git HEAD SHA matching the release source head SHA" in checker.REQUIRED_DOC_SNIPPETS


def test_release_truth_checker_requires_xp_release_source_docs() -> None:
    checker = _load_release_truth_checker()

    assert "--source-workflow-run-url" in checker.REQUIRED_DOC_SNIPPETS
    assert "xp smoke source head sha" in checker.REQUIRED_DOC_SNIPPETS
    assert "xp_evidence_summary.release_source" in checker.REQUIRED_DOC_SNIPPETS
    assert "scripts/xp_smoke_runner.cmd" in checker.REQUIRED_DOC_SNIPPETS
    assert "modern self-hosted `xp-evidence` collector" in checker.REQUIRED_DOC_SNIPPETS


def test_release_truth_checker_requires_release_strategy_import_dry_run_docs() -> None:
    checker = _load_release_truth_checker()

    assert (
        "python scripts/import_platform_evidence_artifacts.py --release-tag <tag> "
        "--require-goal-targets --out-dir <release-assets-dir> --dry-run --verify-source-run"
    ) in checker.REQUIRED_RELEASE_STRATEGY_SNIPPETS
    assert "pre-release protected-platform import dry-run" in checker.REQUIRED_RELEASE_STRATEGY_SNIPPETS
    assert "does not stage files for upload" in checker.REQUIRED_RELEASE_STRATEGY_SNIPPETS


def test_release_truth_checker_requires_xp_host_collector_docs() -> None:
    checker = _load_release_truth_checker()
    original_read = checker.read

    def fake_read(relative: str) -> str:
        text = original_read(relative)
        if relative in {"README.md", "README.tr.md", "docs/PLATFORM_SUPPORT.md", "docs/RELEASE_STRATEGY.md"}:
            return (
                text.replace("modern self-hosted `xp-evidence` collector", "XP runner")
                .replace("self-hosted `xp-evidence` collector", "XP runner")
                .replace("`xp-evidence` collector", "XP runner")
                .replace("`scripts/xp_smoke_runner.cmd`", "`xp_smoke.cmd`")
                .replace("scripts/xp_smoke_runner.cmd", "xp_smoke.cmd")
            )
        return text

    checker.read = fake_read
    try:
        errors = checker.check_release_docs()
    finally:
        checker.read = original_read

    assert any("scripts/xp_smoke_runner.cmd" in error for error in errors)
    assert any("xp-evidence" in error and "collector" in error for error in errors)


def test_release_truth_checker_rejects_stale_unfinalized_candidate_guidance() -> None:
    checker = _load_release_truth_checker()

    assert (
        "`--allow-unfinalized-candidates` flag is only for local candidate checks before append"
        in checker.STALE_PLATFORM_EVIDENCE_SNIPPETS
    )
    assert "source-head-bound accepted evidence artifacts" in checker.STALE_PLATFORM_EVIDENCE_SNIPPETS
    assert (
        "source-head-bound accepted Linux i386, Linux armhf and Windows XP native-host artifacts"
        in checker.STALE_PLATFORM_EVIDENCE_SNIPPETS
    )


def test_release_truth_checker_requires_turkish_platform_evidence_gate() -> None:
    checker = _load_release_truth_checker()
    original_read = checker.read

    def fake_read(relative: str) -> str:
        text = original_read(relative)
        if relative == "README.tr.md":
            return text.replace(
                "python scripts/check_platform_verified_evidence.py --require-goal-targets --require-review-bundles --release-tag <tag>",
                "python scripts/check_platform_verified_evidence.py",
            )
        return text

    checker.read = fake_read
    try:
        errors = checker.check_release_docs()
    finally:
        checker.read = original_read

    assert any("README.tr.md missing protected platform evidence truth snippet" in error for error in errors)


def test_release_truth_checker_requires_turkish_protected_goal_gate() -> None:
    checker = _load_release_truth_checker()
    original_read = checker.read

    def fake_read(relative: str) -> str:
        text = original_read(relative)
        if relative == "README.tr.md":
            return text.replace(
                "python scripts/check_protected_platform_goal.py --release-tag <tag> --require-complete --show-requirements",
                "python scripts/check_protected_platform_goal.py --release-tag <tag> --show-requirements",
            )
        return text

    checker.read = fake_read
    try:
        errors = checker.check_release_docs()
    finally:
        checker.read = original_read

    assert any(
        "README.tr.md missing protected platform evidence truth snippet" in error
        and "check_protected_platform_goal.py" in error
        for error in errors
    )


def test_release_truth_checker_requires_readme_release_section_strict_platform_publish_gate() -> None:
    checker = _load_release_truth_checker()
    original_read = checker.read

    def fake_read(relative: str) -> str:
        text = original_read(relative)
        if relative == "README.md":
            return text.replace(
                "`python scripts/check_release_publish_assets.py --assets-dir release-assets --tag <tag> --require-platform-goal-targets`\n"
                "to verify",
                "`python scripts/check_release_publish_assets.py --assets-dir release-assets --tag <tag>`\n"
                "to verify",
            )
        return text

    checker.read = fake_read
    try:
        errors = checker.check_release_docs()
    finally:
        checker.read = original_read

    assert any("README.md release section missing protected platform evidence truth snippet" in error for error in errors)


def test_release_truth_checker_requires_source_artifact_hash_preflight_docs() -> None:
    checker = _load_release_truth_checker()
    original_read = checker.read

    def fake_read(relative: str) -> str:
        text = original_read(relative)
        if relative == "README.md":
            return text.replace(
                "downloaded source artifact native artifact SHA-256 values",
                "downloaded source artifact checks",
            )
        if relative == "docs/RELEASE_STRATEGY.md":
            return text.replace(
                "downloaded source artifact native artifact",
                "downloaded source artifact checks",
            )
        return text

    checker.read = fake_read
    try:
        errors = checker.check_release_docs()
    finally:
        checker.read = original_read

    assert any(
        "README.md release section missing protected platform evidence truth snippet" in error
        and "downloaded source artifact native artifact SHA-256 values" in error
        for error in errors
    )
    assert any(
        "release docs missing workflow artifact truth snippet" in error
        and "downloaded source artifact native artifact SHA-256 values" in error
        for error in errors
    )


def test_release_truth_checker_requires_final_record_asset_import_docs() -> None:
    checker = _load_release_truth_checker()
    original_read = checker.read

    def fake_read(relative: str) -> str:
        text = original_read(relative)
        if relative in {"README.md", "README.tr.md", "docs/RELEASE_STRATEGY.md"}:
            return text.replace(" --require-final-record-assets", "")
        return text

    checker.read = fake_read
    try:
        errors = checker.check_release_docs()
    finally:
        checker.read = original_read

    assert any(
        "release docs missing workflow artifact truth snippet" in error
        and "--require-final-record-assets" in error
        for error in errors
    )
    assert any(
        "README.md release section missing protected platform evidence truth snippet" in error
        and "--require-final-record-assets" in error
        for error in errors
    )
    assert any(
        "README.tr.md missing protected platform evidence truth snippet" in error
        and "--require-final-record-assets" in error
        for error in errors
    )


def test_release_truth_checker_requires_readme_import_run_attempt_binding() -> None:
    checker = _load_release_truth_checker()
    original_read = checker.read

    def fake_read(relative: str) -> str:
        text = original_read(relative)
        if relative == "README.md":
            return text.replace(
                "workflow-file, source-head and\nrun-attempt-bound accepted evidence artifacts",
                "source-head-bound\naccepted evidence artifacts",
            )
        return text

    checker.read = fake_read
    try:
        errors = checker.check_release_docs()
    finally:
        checker.read = original_read

    assert any(
        "README.md release section missing protected platform evidence truth snippet" in error
        and "run-attempt-bound accepted evidence artifacts" in error
        for error in errors
    )
    assert (
        "release docs still advertise stale platform evidence workflow guidance: "
        "source-head-bound accepted evidence artifacts"
    ) in errors


def test_release_truth_checker_requires_readme_target_specific_release_source_workflow() -> None:
    checker = _load_release_truth_checker()
    original_read = checker.read

    def fake_read(relative: str) -> str:
        text = original_read(relative)
        if relative == "README.md":
            return text.replace(
                "target-specific release source workflow file",
                "release source evidence",
            )
        return text

    checker.read = fake_read
    try:
        errors = checker.check_release_docs()
    finally:
        checker.read = original_read

    assert any(
        "README.md release section missing protected platform evidence truth snippet" in error
        and "target-specific release source workflow file" in error
        for error in errors
    )


def test_release_truth_checker_requires_release_strategy_import_run_attempt_binding() -> None:
    checker = _load_release_truth_checker()
    original_read = checker.read

    def fake_read(relative: str) -> str:
        text = original_read(relative)
        if relative == "docs/RELEASE_STRATEGY.md":
            return text.replace(
                "workflow-file, source-head and\n"
                "  run-attempt-bound accepted Linux i386, Linux armhf and Windows XP native-host\n"
                "  artifacts",
                "source-head-bound\n"
                "  accepted Linux i386, Linux armhf and Windows XP native-host artifacts",
            )
        return text

    checker.read = fake_read
    try:
        errors = checker.check_release_docs()
    finally:
        checker.read = original_read

    assert any(
        "release docs missing workflow artifact truth snippet" in error
        and "run-attempt-bound accepted Linux i386" in error
        for error in errors
    )
    assert (
        "release docs still advertise stale platform evidence workflow guidance: "
        "source-head-bound accepted Linux i386, Linux armhf and Windows XP native-host artifacts"
    ) in errors


def test_release_truth_checker_requires_release_strategy_import_dry_run_proof() -> None:
    checker = _load_release_truth_checker()
    original_read = checker.read

    def fake_read(relative: str) -> str:
        text = original_read(relative)
        if relative == "docs/RELEASE_STRATEGY.md":
            return text.replace(
                "python scripts/import_platform_evidence_artifacts.py --release-tag <tag> "
                "--require-goal-targets --out-dir <release-assets-dir> --dry-run --verify-source-run",
                "python scripts/import_platform_evidence_artifacts.py --help",
            )
        return text

    checker.read = fake_read
    try:
        errors = checker.check_release_docs()
    finally:
        checker.read = original_read

    assert any(
        "docs/RELEASE_STRATEGY.md missing pre-release platform import truth snippet" in error
        and "--dry-run --verify-source-run" in error
        for error in errors
    )


def test_release_truth_checker_requires_turkish_import_run_attempt_binding() -> None:
    checker = _load_release_truth_checker()
    original_read = checker.read

    def fake_read(relative: str) -> str:
        text = original_read(relative)
        if relative == "README.tr.md":
            return text.replace(
                "ayni tag/repository/workflow file path/source-head/run-attempt",
                "ayni tag/repository/source-head",
            )
        return text

    checker.read = fake_read
    try:
        errors = checker.check_release_docs()
    finally:
        checker.read = original_read

    assert any(
        "README.tr.md missing protected platform evidence truth snippet" in error
        and "ayni tag/repository/workflow file path/source-head/run-attempt" in error
        for error in errors
    )


def test_release_truth_checker_requires_turkish_target_specific_release_source_workflow() -> None:
    checker = _load_release_truth_checker()
    original_read = checker.read

    def fake_read(relative: str) -> str:
        text = original_read(relative)
        if relative == "README.tr.md":
            return text.replace(
                "target'a ozel release source workflow file",
                "release source evidence",
            )
        return text

    checker.read = fake_read
    try:
        errors = checker.check_release_docs()
    finally:
        checker.read = original_read

    assert any(
        "README.tr.md missing protected platform evidence truth snippet" in error
        and "target'a ozel release source workflow file path" in error
        for error in errors
    )


def test_release_truth_checker_rejects_stale_turkish_release_version() -> None:
    checker = _load_release_truth_checker()
    original_read = checker.read

    def fake_read(relative: str) -> str:
        text = original_read(relative)
        if relative == "README.tr.md":
            return text.replace("release-v1.0.2", "release-v1.0.1")
        return text

    checker.read = fake_read
    try:
        errors = checker.check_release_docs()
    finally:
        checker.read = original_read

    assert "README.tr.md still contains stale release truth snippet: release-v1.0.1" in errors


def test_release_truth_checker_requires_release_preflight_job() -> None:
    checker = _load_release_truth_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        "  release-preflight:",
        "  release_preflight_disabled:",
    )

    errors = checker.check_release_preflight(workflow)

    assert "release workflow missing release-preflight job" in errors


def test_release_truth_checker_requires_node24_javascript_action_runtime() -> None:
    checker = _load_release_truth_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        '  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true"\n',
        "",
    )

    errors = checker.check_release_preflight(workflow)

    assert "release workflow must opt JavaScript actions into Node.js 24" in errors


def test_release_truth_checker_rejects_insecure_node_runtime_opt_out() -> None:
    checker = _load_release_truth_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8") + (
        "\nenv:\n  ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION: true\n"
    )

    errors = checker.check_release_preflight(workflow)

    assert "release workflow must not opt JavaScript actions into an insecure Node.js runtime" in errors


def test_release_truth_checker_requires_build_jobs_to_need_preflight() -> None:
    checker = _load_release_truth_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        "      - release-preflight\n",
        "",
        1,
    )

    errors = checker.check_release_preflight(workflow)

    assert "source-and-python must depend on release-preflight" in errors


def test_release_truth_checker_requires_build_jobs_to_wait_for_platform_import() -> None:
    checker = _load_release_truth_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        "      - accepted-platform-evidence-assets\n",
        "",
        1,
    )

    errors = checker.check_release_preflight(workflow)

    assert "source-and-python must wait for accepted-platform-evidence-assets" in errors


def test_release_truth_checker_ignores_step_mentions_when_checking_build_job_needs() -> None:
    checker = _load_release_truth_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        "      - accepted-platform-evidence-assets\n",
        "",
        1,
    )
    workflow = workflow.replace(
        "      - name: Build source and Python package assets\n",
        '      - name: Mention platform import without depending on it\n'
        '        run: echo "- accepted-platform-evidence-assets"\n'
        "      - name: Build source and Python package assets\n",
        1,
    )

    errors = checker.check_release_preflight(workflow)

    assert "source-and-python must wait for accepted-platform-evidence-assets" in errors


def test_release_truth_checker_requires_platform_import_job_to_need_preflight() -> None:
    checker = _load_release_truth_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        "  accepted-platform-evidence-assets:\n    needs: release-preflight\n",
        "  accepted-platform-evidence-assets:\n",
    )

    errors = checker.check_release_preflight(workflow)

    assert "accepted-platform-evidence-assets must depend on release-preflight" in errors


def test_release_truth_checker_requires_preflight_cleanup_command() -> None:
    checker = _load_release_truth_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        "python scripts/check_repository_cleanup.py --require-clean",
        "python scripts/check_repository_cleanup.py",
    )

    errors = checker.check_release_preflight(workflow)

    assert any("clean checkout requirement" in error for error in errors)


def test_release_truth_checker_requires_tag_scoped_preflight_verifier() -> None:
    checker = _load_release_truth_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        ' --release-tag "${{ github.ref_name }}"',
        "",
    )

    errors = checker.check_release_preflight(workflow)

    assert any("tag-scoped protected platform parity report" in error for error in errors)


def test_release_truth_checker_requires_early_platform_goal_evidence_gate() -> None:
    checker = _load_release_truth_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        '      - name: Require protected platform evidence before release builds\n'
        '        run: python scripts/check_platform_verified_evidence.py --require-goal-targets --require-review-bundles --release-tag "${{ github.ref_name }}"\n',
        "",
    )

    errors = checker.check_release_preflight(workflow)

    assert any("strict accepted evidence registry gate" in error for error in errors)


def test_release_truth_checker_rejects_preflight_evidence_gate_without_explicit_review_bundles() -> None:
    checker = _load_release_truth_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        " --require-review-bundles",
        "",
        1,
    )

    errors = checker.check_release_preflight(workflow)

    assert any("strict accepted evidence registry gate" in error for error in errors)


def test_release_truth_checker_requires_preflight_platform_requirements_report() -> None:
    checker = _load_release_truth_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        '      - name: Report protected platform readiness requirements\n'
        '        run: python scripts/check_protected_platform_goal.py --release-tag "${{ github.ref_name }}" --show-requirements\n',
        "",
    )

    errors = checker.check_release_preflight(workflow)

    assert any("protected platform readiness requirements report" in error for error in errors)


def test_release_truth_checker_requires_hard_protected_platform_goal_gate() -> None:
    checker = _load_release_truth_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        '      - name: Require protected platform goal completion before release builds\n'
        '        run: python scripts/check_protected_platform_goal.py --release-tag "${{ github.ref_name }}" --require-complete --show-requirements\n',
        "",
    )

    errors = checker.check_release_preflight(workflow)

    assert any("hard protected platform goal completion gate" in error for error in errors)


def test_release_truth_checker_requires_publish_time_platform_goal_gate() -> None:
    checker = _load_release_truth_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        " --require-platform-goal-targets",
        "",
    )

    errors = checker.check_release_preflight(workflow)

    assert any("publish-time protected platform goal gate" in error for error in errors)


def test_release_truth_checker_requires_tagged_publish_time_platform_goal_gate() -> None:
    checker = _load_release_truth_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        ' --tag "${{ github.ref_name }}"',
        "",
    )

    errors = checker.check_release_preflight(workflow)

    assert any("publish-time protected platform goal gate" in error and "--tag" in error for error in errors)


def test_release_truth_checker_requires_protected_platform_release_asset_gate() -> None:
    checker = _load_release_truth_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        '      - name: Require protected platform release assets\n'
        '        run: python scripts/check_protected_platform_goal.py --release-tag "${{ github.ref_name }}" --require-complete --assets-dir release-assets\n',
        "",
    )

    errors = checker.check_release_preflight(workflow)

    assert any("protected platform release asset gate" in error for error in errors)


def test_release_truth_checker_requires_protected_asset_gate_before_publish_asset_validation() -> None:
    checker = _load_release_truth_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    protected_gate = (
        '      - name: Require protected platform release assets\n'
        '        run: python scripts/check_protected_platform_goal.py --release-tag "${{ github.ref_name }}" --require-complete --assets-dir release-assets\n'
    )
    publish_gate = (
        '      - name: Validate release publish assets\n'
        '        run: python scripts/check_release_publish_assets.py --assets-dir release-assets --tag "${{ github.ref_name }}" --require-platform-goal-targets\n'
    )
    workflow = workflow.replace(protected_gate, "").replace(publish_gate, publish_gate + protected_gate)

    errors = checker.check_release_preflight(workflow)

    assert "protected platform release asset gate must run before publish asset validation" in errors


def test_release_truth_checker_requires_protected_asset_gate_before_release_upload() -> None:
    checker = _load_release_truth_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    protected_gate = (
        '      - name: Require protected platform release assets\n'
        '        run: python scripts/check_protected_platform_goal.py --release-tag "${{ github.ref_name }}" --require-complete --assets-dir release-assets\n'
    )
    workflow = workflow.replace(protected_gate, "") + protected_gate

    errors = checker.check_release_preflight(workflow)

    assert "protected platform release asset gate must run before GitHub release upload" in errors


def test_release_truth_checker_requires_publish_gate_before_release_upload() -> None:
    checker = _load_release_truth_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    gate = (
        '      - name: Validate release publish assets\n'
        '        run: python scripts/check_release_publish_assets.py --assets-dir release-assets --tag "${{ github.ref_name }}" --require-platform-goal-targets\n'
    )
    upload = (
        "      - name: Upload release assets\n"
        "        uses: softprops/action-gh-release@v3\n"
    )
    workflow = workflow.replace(gate, "").replace(upload, upload + gate)

    errors = checker.check_release_preflight(workflow)

    assert "publish-time protected platform goal gate must run before GitHub release upload" in errors


def test_release_truth_checker_requires_platform_evidence_import_command() -> None:
    checker = _load_release_truth_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        'python scripts/import_platform_evidence_artifacts.py --release-tag "${{ github.ref_name }}" '
        "--require-goal-targets --out-dir release-assets --verify-source-run",
        "python scripts/import_platform_evidence_artifacts.py --help",
    )

    errors = checker.check_release_preflight(workflow)

    assert any("accepted platform evidence artifact importer" in error for error in errors)


def test_release_truth_checker_rejects_platform_import_dry_run() -> None:
    checker = _load_release_truth_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        "--require-goal-targets --out-dir release-assets --verify-source-run",
        "--require-goal-targets --out-dir release-assets --verify-source-run --dry-run",
    )

    errors = checker.check_release_preflight(workflow)

    assert (
        "accepted-platform-evidence-assets must download accepted artifacts, not run importer with --dry-run"
        in errors
    )


def test_release_truth_checker_requires_imported_review_bundle_validation() -> None:
    checker = _load_release_truth_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        'python scripts/check_platform_review_bundle_artifacts.py --bundle-dir release-assets '
        '--require-goal-targets --release-tag "${{ github.ref_name }}" --require-final-record-assets',
        "python scripts/check_platform_review_bundle_artifacts.py --help",
    )

    errors = checker.check_release_preflight(workflow)

    assert any("imported platform review bundle and final record validator" in error for error in errors)


def test_release_truth_checker_requires_imported_final_record_asset_validation() -> None:
    checker = _load_release_truth_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        " --require-final-record-assets",
        "",
    )

    errors = checker.check_release_preflight(workflow)

    assert any("imported platform review bundle and final record validator" in error for error in errors)


def test_release_truth_checker_requires_platform_import_gh_token() -> None:
    checker = _load_release_truth_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        "          GH_TOKEN: ${{ github.token }}\n",
        "",
    )

    errors = checker.check_release_preflight(workflow)

    assert any("GitHub token for gh run download" in error for error in errors)


def test_release_truth_checker_rejects_platform_import_write_permissions() -> None:
    checker = _load_release_truth_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        "      actions: read\n",
        "      actions: write\n",
    )

    errors = checker.check_release_preflight(workflow)

    assert "accepted-platform-evidence-assets must not request write permissions" in errors


def test_release_truth_checker_rejects_platform_import_nonstandard_write_permissions() -> None:
    checker = _load_release_truth_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        "      contents: read\n",
        "      contents: read\n      packages: write\n",
    )

    errors = checker.check_release_preflight(workflow)

    assert "accepted-platform-evidence-assets must not request write permissions" in errors


def test_release_truth_checker_requires_platform_import_timeout() -> None:
    checker = _load_release_truth_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        "    runs-on: ubuntu-latest\n    timeout-minutes: 20\n    permissions:",
        "    runs-on: ubuntu-latest\n    permissions:",
        1,
    )

    errors = checker.check_release_preflight(workflow)

    assert any("bounded platform evidence import timeout" in error for error in errors)


def test_release_truth_checker_requires_platform_import_hidden_file_exclusion() -> None:
    checker = _load_release_truth_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        "          include-hidden-files: false\n",
        "",
    )

    errors = checker.check_release_preflight(workflow)

    assert any("platform evidence upload hidden file exclusion" in error for error in errors)


def test_release_truth_checker_requires_platform_import_retention_window() -> None:
    checker = _load_release_truth_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        "          retention-days: 90\n",
        "",
    )

    errors = checker.check_release_preflight(workflow)

    assert any("platform evidence upload retention window" in error for error in errors)


def test_release_truth_checker_requires_publish_to_need_platform_evidence_assets() -> None:
    checker = _load_release_truth_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        "      - accepted-platform-evidence-assets\n",
        "",
    )

    errors = checker.check_release_preflight(workflow)

    assert "publish job must depend on accepted-platform-evidence-assets" in errors


def test_release_truth_checker_ignores_step_mentions_when_checking_publish_needs() -> None:
    checker = _load_release_truth_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        "      - linux-native\n      - accepted-platform-evidence-assets\n",
        "      - linux-native\n",
    )
    workflow = workflow.replace(
        "      - name: Validate release publish assets\n",
        '      - name: Mention platform import without depending on it\n'
        '        run: echo "- accepted-platform-evidence-assets"\n'
        "      - name: Validate release publish assets\n",
        1,
    )

    errors = checker.check_release_preflight(workflow)

    assert "publish job must depend on accepted-platform-evidence-assets" in errors


def _load_release_truth_checker():
    path = Path("scripts/check_release_truth.py")
    spec = importlib.util.spec_from_file_location("check_release_truth_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module

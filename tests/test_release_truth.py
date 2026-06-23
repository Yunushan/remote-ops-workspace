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


def test_release_truth_checker_requires_turkish_platform_evidence_gate() -> None:
    checker = _load_release_truth_checker()
    original_read = checker.read

    def fake_read(relative: str) -> str:
        text = original_read(relative)
        if relative == "README.tr.md":
            return text.replace(
                "python scripts/check_platform_verified_evidence.py --require-goal-targets --release-tag <tag>",
                "python scripts/check_platform_verified_evidence.py",
            )
        return text

    checker.read = fake_read
    try:
        errors = checker.check_release_docs()
    finally:
        checker.read = original_read

    assert any("README.tr.md missing protected platform evidence truth snippet" in error for error in errors)


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
        '        run: python scripts/check_platform_verified_evidence.py --require-goal-targets --release-tag "${{ github.ref_name }}"\n',
        "",
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
        "--require-goal-targets --out-dir release-assets",
        "python scripts/import_platform_evidence_artifacts.py --help",
    )

    errors = checker.check_release_preflight(workflow)

    assert any("accepted platform evidence artifact importer" in error for error in errors)


def test_release_truth_checker_requires_imported_review_bundle_validation() -> None:
    checker = _load_release_truth_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        'python scripts/check_platform_review_bundle_artifacts.py --bundle-dir release-assets '
        '--require-goal-targets --release-tag "${{ github.ref_name }}"',
        "python scripts/check_platform_review_bundle_artifacts.py --help",
    )

    errors = checker.check_release_preflight(workflow)

    assert any("imported platform review bundle validator" in error for error in errors)


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

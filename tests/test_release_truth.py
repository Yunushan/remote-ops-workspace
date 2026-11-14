from __future__ import annotations

import importlib.util
import re
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_script(name: str):
    path = ROOT / "scripts" / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def build_workflow() -> str:
    return (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")


def promotion_workflow() -> str:
    return (ROOT / ".github/workflows/release-promotion.yml").read_text(encoding="utf-8")


def remove_named_step(workflow: str, name: str) -> str:
    return re.sub(
        rf"(?ms)^      - name: {re.escape(name)}\n.*?(?=^      - |\Z)",
        "",
        workflow,
        count=1,
    )


def both_contract_errors(workflow: str) -> tuple[list[str], list[str]]:
    truth = load_script("check_release_truth")
    assets = load_script("check_release_publish_assets")
    return (
        truth.check_promotion_truth(truth.strip_unquoted_comments(workflow)),
        assets.check_promotion_transaction_contract(workflow),
    )


def test_release_truth_baseline_passes() -> None:
    checker = load_script("check_release_truth")
    assert checker.main() == 0


def test_candidate_build_supports_exact_tag_recovery_and_never_publishes() -> None:
    checker = load_script("check_release_truth")
    workflow = build_workflow()
    assert "  workflow_dispatch:\n" in workflow
    assert "softprops/action-gh-release" not in workflow
    assert "seal-release-candidate:" in workflow

    errors = checker.check_release_preflight(
        workflow.replace('      - "v*"\n', "", 1)
    )
    assert any("v* tag trigger" in error for error in errors)
    errors = checker.check_release_preflight(
        workflow.replace("  workflow_dispatch:\n", "", 1)
    )
    assert any("manual exact-tag candidate recovery trigger" in error for error in errors)
    errors = checker.check_release_preflight(
        workflow.replace("    if: ${{ github.ref_type == 'tag' }}\n", "", 1)
    )
    assert any("tag-only preflight job" in error for error in errors)


def test_candidate_build_requires_active_maturity_gate() -> None:
    checker = load_script("check_release_truth")
    workflow = build_workflow().replace(
        'run: python scripts/check_release_maturity.py --release-tag "$RELEASE_TAG"',
        'run: echo "python scripts/check_release_maturity.py --release-tag $RELEASE_TAG"',
        1,
    )
    assert any("production maturity gate" in error for error in checker.check_release_preflight(workflow))


def test_run_source_never_interpolates_untrusted_context_directly() -> None:
    checker = load_script("check_release_truth")
    injected = promotion_workflow().replace(
        '          test "$GITHUB_EVENT_NAME" = "workflow_dispatch"',
        '          echo "${{ inputs.build_run_id }}"\n'
        '          test "$GITHUB_EVENT_NAME" = "workflow_dispatch"',
        1,
    )
    errors = checker.check_untrusted_run_interpolation(injected, label="promotion")
    assert any("inputs" in error for error in errors)


@pytest.mark.parametrize(
    "injected",
    [
        "        if: ${{ false && always() }}\n",
        "        continue-on-error: ${{ true }}\n",
    ],
)
def test_mandatory_compliance_step_rejects_conditions_and_continue_on_error(
    injected: str,
) -> None:
    workflow = promotion_workflow().replace(
        "      - name: Audit signed exact-byte redistribution and resolver evidence\n",
        "      - name: Audit signed exact-byte redistribution and resolver evidence\n" + injected,
        1,
    )
    truth_errors, asset_errors = both_contract_errors(workflow)
    assert truth_errors
    assert asset_errors


@pytest.mark.parametrize("suffix", [" &", " || :", " --check-policy-only", " --help", " --dry-run"])
def test_compliance_command_rejects_backgrounding_and_downgrades(suffix: str) -> None:
    workflow = promotion_workflow().replace(
        "          --audit-redistribution-only",
        "          --audit-redistribution-only" + suffix,
        1,
    )
    truth_errors, asset_errors = both_contract_errors(workflow)
    assert truth_errors
    assert asset_errors


def test_compliance_command_in_unreachable_shell_is_rejected() -> None:
    workflow = promotion_workflow().replace(
        "          python scripts/check_release_license_compliance.py",
        "          if false; then python scripts/check_release_license_compliance.py",
        1,
    )
    truth_errors, asset_errors = both_contract_errors(workflow)
    assert truth_errors
    assert asset_errors


def test_deleted_complete_asset_gate_is_rejected() -> None:
    workflow = remove_named_step(
        promotion_workflow(),
        "Validate complete production asset inventory",
    )
    truth_errors, asset_errors = both_contract_errors(workflow)
    assert any("production asset inventory" in error for error in truth_errors)
    assert any("production asset inventory" in error for error in asset_errors)


def test_duplicate_unsigned_preview_channel_cannot_override_production_signed() -> None:
    workflow = promotion_workflow().replace(
        "          --native-release-channel production-signed",
        "          --native-release-channel production-signed"
        " --native-release-channel unsigned-preview",
        1,
    )
    truth_errors, asset_errors = both_contract_errors(workflow)
    assert truth_errors
    assert asset_errors


def test_fake_uses_text_does_not_replace_attestation_action() -> None:
    workflow = promotion_workflow().replace(
        "        uses: actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6 # v4.2.2",
        '        run: echo "uses: actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6"',
        1,
    )
    truth_errors, asset_errors = both_contract_errors(workflow)
    assert truth_errors
    assert asset_errors


def test_immutable_preflight_cannot_be_backgrounded_or_forged() -> None:
    workflow = promotion_workflow().replace(
        '          python scripts/check_release_remote_preconditions.py immutable\n'
        '          --repository "$GITHUB_REPOSITORY"\n'
        '          --tag "$RELEASE_TAG"',
        '          python scripts/check_release_remote_preconditions.py immutable\n'
        '          --repository "$GITHUB_REPOSITORY"\n'
        '          --tag "$RELEASE_TAG"; printf \'{"enabled":true}\'',
        1,
    )
    truth_errors, asset_errors = both_contract_errors(workflow)
    assert truth_errors
    assert asset_errors


def test_namespace_preflight_rejects_appended_collision_override() -> None:
    workflow = promotion_workflow().replace(
        '          python scripts/check_release_remote_preconditions.py namespace\n'
        '          --repository "$GITHUB_REPOSITORY"\n'
        '          --tag "$RELEASE_TAG"',
        '          python scripts/check_release_remote_preconditions.py namespace\n'
        '          --repository "$GITHUB_REPOSITORY"\n'
        '          --tag "$RELEASE_TAG"; echo 0',
        1,
    )
    truth_errors, asset_errors = both_contract_errors(workflow)
    assert truth_errors
    assert asset_errors


def test_promotion_requires_exact_tag_sha_and_signed_pinned_evidence() -> None:
    workflow = promotion_workflow()
    assert 'test "$GITHUB_REF" = "refs/tags/$RELEASE_TAG"' in workflow
    assert "target_commitish: $sha" in workflow
    assert "--audit-redistribution-only" in workflow
    assert "--governance-attestation release-governance-publish/tag-governance-attestation.json" in workflow
    assert "--governance-signature release-governance-publish/tag-governance-attestation.sig.json" in workflow
    assert "--evidence-registry" in workflow
    assert "Re-resolve immutable tag after publication" in workflow


def test_promotion_requires_fresh_governance_check_before_publication() -> None:
    workflow = remove_named_step(
        promotion_workflow(),
        "Revalidate signed tag governance immediately before publication",
    )

    truth_errors, asset_errors = both_contract_errors(workflow)

    assert any("publication-bound tag governance proof" in error for error in truth_errors)
    assert any("publication-bound tag governance proof" in error for error in asset_errors)


@pytest.mark.parametrize(
    ("step_name", "label"),
    [
        ("Revalidate signed tag governance at mutation boundary", "mutation-bound tag governance proof"),
        ("Revalidate signed tag governance immediately before publication", "publication-bound tag governance proof"),
        ("Verify final immutable release and complete exact-tag provenance", "final in-run"),
    ],
)
def test_promotion_requires_signed_redistribution(step_name: str, label: str) -> None:
    workflow = promotion_workflow()
    step = re.search(rf"(?ms)^      - name: {re.escape(step_name)}\n.*?(?=^      - |\Z)", workflow)
    assert step is not None
    changed_step, count = re.subn(r"(?m)^ +--redistribution-signature .+\n", "", step[0])
    assert count == 1
    changed = workflow[:step.start()] + changed_step + workflow[step.end():]
    truth_errors, asset_errors = both_contract_errors(changed)
    assert any(label in error and "missing required exact arguments" in error for error in truth_errors)
    assert any(label in error and "missing required exact arguments" in error for error in asset_errors)


def test_promotion_requires_immutable_release_setting_at_publication() -> None:
    workflow = remove_named_step(
        promotion_workflow(),
        "Recheck immutable releases enabled before publication",
    )
    truth_errors, asset_errors = both_contract_errors(workflow)
    assert any("publication-time immutable release setting proof" in error for error in truth_errors)
    assert any("publication-time immutable release setting proof" in error for error in asset_errors)


def test_promotion_requires_exact_package_notices_audit() -> None:
    workflow = remove_named_step(promotion_workflow(), "Verify notices in the exact native packages")
    _, errors = both_contract_errors(workflow)
    assert any("exact package notices audit" in error for error in errors)


@pytest.mark.parametrize(
    ("name", "wait_for"),
    [
        ("Require unused release namespace including drafts", "draft creation"),
        ("Re-resolve immutable tag immediately before mutation", "draft creation"),
        ("Verify protected branch and exact required checks before draft creation", "draft creation"),
        ("Recheck immutable releases enabled before publication", "publication"),
        ("Re-resolve immutable tag before publication", "publication"),
        ("Verify protected branch and exact required checks before publication", "publication"),
    ],
)
def test_promotion_rejects_remote_preconditions_before_auditor_wait(
    name: str, wait_for: str
) -> None:
    workflow = promotion_workflow()
    step = re.search(rf"(?ms)^      - name: {re.escape(name)}\n.*?(?=^      - |\Z)", workflow)
    assert step is not None
    marker = f"      - name: Fetch fresh signed governance for {wait_for}\n"
    stale = remove_named_step(workflow, name).replace(marker, step[0] + marker, 1)
    _, errors = both_contract_errors(stale)
    assert any("in order" in error for error in errors)


def test_promotion_requires_exact_workflow_identity_and_checks_before_publication() -> None:
    workflow = promotion_workflow().replace(
        '          --sha "$RELEASE_SHA"\n      - name: Reverify draft bytes after waiting for the auditor',
        '          --sha "$RELEASE_SHA" --required-check "CodeQL python"\n'
        '      - name: Reverify draft bytes after waiting for the auditor',
        1,
    )
    _, errors = both_contract_errors(workflow)
    assert any("publication-time branch governance" in error and "allowlisted" in error for error in errors)


def test_promotion_rechecks_draft_at_the_publication_boundary() -> None:
    workflow = promotion_workflow()
    recheck = "Reverify draft bytes after waiting for the auditor"
    signing_proof = "Revalidate signed tag governance immediately before publication"
    message = "promotion must recheck the complete draft immediately before publication governance"
    assert message not in both_contract_errors(workflow)[1]
    old_boundary = workflow.replace(
        f"      - name: {signing_proof}\n",
        "      - name: Unrelated publication delay\n        run: sleep 1\n"
        f"      - name: {signing_proof}\n",
        1,
    )
    assert message in both_contract_errors(old_boundary)[1]
    assert message in both_contract_errors(remove_named_step(workflow, recheck))[1]


def test_promotion_requires_post_wait_tag_comparison() -> None:
    workflow = promotion_workflow().replace(
        """          test "$(git rev-parse 'refs/tags/row-release-final-candidate^{commit}')" = "$RELEASE_SHA"\n""",
        "",
        1,
    )
    _, errors = both_contract_errors(workflow)
    assert any("must fetch and compare the exact source tag" in error for error in errors)


def test_promotion_attests_both_governance_inputs() -> None:
    workflow = promotion_workflow().replace(
        "            release-governance-publish/tag-governance-attestation.sig.json",
        "            release-governance-publish/other.json",
        1,
    )

    _, errors = both_contract_errors(workflow)

    assert "promotion must attest both exact signed tag governance inputs" in errors


def test_promotion_rejects_automatic_release_deletion() -> None:
    checker = load_script("check_release_truth")
    workflow = promotion_workflow()
    changed = workflow + '          gh api --method DELETE "repos/$GITHUB_REPOSITORY/releases/$RELEASE_ID"\n'
    assert "promotion workflow must preserve releases after failure" in checker.check_promotion_truth(changed)


def test_promotion_captures_release_id_before_rejecting_draft_response() -> None:
    checker = load_script("check_release_truth")
    capture = '          echo "release-id=$release_id" >> "$GITHUB_OUTPUT"\n'
    response_check = '          jq -e \'.draft == true and .prerelease == false\' "$response" >/dev/null\n'
    workflow = promotion_workflow()
    assert workflow.count(capture) == workflow.count(response_check) == 1
    late_capture = workflow.replace(capture, "", 1).replace(response_check, response_check + capture, 1)
    message = "promotion must capture the validated release ID before checking the draft response"

    assert message not in checker.check_promotion_truth(workflow)
    assert message in checker.check_promotion_truth(late_capture)
    assert message in checker.check_promotion_truth(workflow.replace(capture, "", 1))


def test_production_candidate_refuses_unapproved_release_policy() -> None:
    checker = load_script("check_release_truth")
    workflow = (ROOT / ".github/workflows/release.yml").read_text(encoding="utf-8")
    name = "Require independently approved production release policy"
    assert checker.check_release_preflight(workflow) == []
    without_policy = remove_named_step(workflow, name)
    assert any("independently approved production release policy" in error
               for error in checker.check_release_preflight(without_policy))
    mutable_policy = workflow.replace("--check-policy-only", "--check-policy-only --policy-root /tmp")
    assert any("independently approved production release policy" in error and "allowlisted" in error
               for error in checker.check_release_preflight(mutable_policy))


def test_promotion_recovers_draft_id_for_the_exact_interrupted_attempt() -> None:
    checker = load_script("check_release_truth")
    workflow = promotion_workflow()
    marker = "$RELEASE_TAG:$RELEASE_SHA:$GITHUB_RUN_ID:$GITHUB_RUN_ATTEMPT"
    message = "promotion workflow must recover and report the release ID for its exact failed attempt"
    assert message not in checker.check_promotion_truth(workflow)
    assert message in checker.check_promotion_truth(workflow.replace(marker, "$RELEASE_TAG:$RELEASE_SHA", 1))
    assert message in checker.check_promotion_truth(workflow.replace("index($marker) != null", "true", 1))


def test_promotion_requires_qualified_default_branch_source() -> None:
    checker = load_script("check_release_truth")
    workflow = promotion_workflow()
    changed = workflow.replace('git merge-base --is-ancestor "$RELEASE_SHA"', "git merge-base --is-ancestor HEAD")
    assert "promotion source gate must bind the release SHA to the live default branch" in (
        checker.check_promotion_truth(changed)
    )
    changed = workflow.replace("python scripts/check_python315_ci_evidence.py", "echo check_python315_ci_evidence.py")
    assert any("exact default-branch CI evidence" in error for error in checker.check_promotion_truth(changed))


def test_completed_certification_is_separate_from_in_progress_transaction() -> None:
    workflow = (ROOT / ".github/workflows/release-certification.yml").read_text(
        encoding="utf-8"
    )
    assert "workflow_run:" in workflow
    assert 'test "$PROMOTION_STATUS" = "completed"' in workflow
    assert "check_release_provenance.py" in workflow
    assert "--current-transaction-run-id" not in workflow
    checker = load_script("check_release_truth")
    assert checker.check_certification_truth(workflow) == []
    changed = workflow.replace('run-id: ${{ env.PROMOTION_RUN_ID }}', 'run-id: ${{ github.run_id }}', 1)
    assert checker.check_certification_truth(changed) == [
        "release certification governance proof missing exact artifact source run",
    ]
    changed = workflow.replace("production-redistribution-approval-", "other-")
    assert any("attempt-specific redistribution approval" in error for error in checker.check_certification_truth(changed))


def test_certification_verifies_source_before_installing_dependencies() -> None:
    checker = load_script("check_release_truth")
    workflow = (ROOT / ".github/workflows/release-certification.yml").read_text(encoding="utf-8")
    name = "Verify checkout against the live release tag and default branch"
    message = "release certification must verify live tag and default-branch ancestry before installing dependencies"
    assert message not in checker.check_certification_truth(workflow)
    assert message in checker.check_certification_truth(remove_named_step(workflow, name))
    late = workflow.replace("name: Install hash-locked compliance verifier", "name: Delayed dependency install", 1)
    late = late.replace(f"      - name: {name}\n", f"      - name: Install hash-locked compliance verifier\n        run: echo misplaced\n      - name: {name}\n", 1)
    assert message in checker.check_certification_truth(late)

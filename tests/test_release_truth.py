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


def test_candidate_build_is_tag_push_only_and_never_publishes() -> None:
    checker = load_script("check_release_truth")
    workflow = build_workflow()
    assert "workflow_dispatch:" not in workflow
    assert "softprops/action-gh-release" not in workflow
    assert "seal-release-candidate:" in workflow

    errors = checker.check_release_preflight(
        workflow.replace('      - "v*"\n', "", 1)
    )
    assert any("v* tag trigger" in error for error in errors)


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


@pytest.mark.parametrize("index", [0, 1])
def test_promotion_requires_signed_redistribution_at_both_mutations(index: int) -> None:
    workflow = promotion_workflow()
    flag = next(line for line in workflow.splitlines() if "--redistribution-signature" in line)
    matches = [match.start() for match in re.finditer(re.escape(flag + "\n"), workflow)]
    assert len(matches) == 2
    start = matches[index]
    changed = workflow[:start] + workflow[start + len(flag) + 1:]
    truth_errors, asset_errors = both_contract_errors(changed)
    assert truth_errors
    assert asset_errors


def test_promotion_requires_immutable_release_setting_at_publication() -> None:
    workflow = remove_named_step(
        promotion_workflow(),
        "Recheck immutable releases enabled before publication",
    )
    truth_errors, asset_errors = both_contract_errors(workflow)
    assert any("publication-time immutable release setting proof" in error for error in truth_errors)
    assert any("publication-time immutable release setting proof" in error for error in asset_errors)


@pytest.mark.parametrize(
    ("name", "wait_for"),
    [
        ("Require unused release namespace including drafts", "draft creation"),
        ("Re-resolve immutable tag immediately before mutation", "draft creation"),
        ("Recheck immutable releases enabled before publication", "publication"),
        ("Re-resolve immutable tag before publication", "publication"),
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


def test_completed_certification_is_separate_from_in_progress_transaction() -> None:
    workflow = (ROOT / ".github/workflows/release-certification.yml").read_text(
        encoding="utf-8"
    )
    assert "workflow_run:" in workflow
    assert 'test "$PROMOTION_STATUS" = "completed"' in workflow
    assert "check_release_provenance.py" in workflow
    assert "--current-transaction-run-id" not in workflow

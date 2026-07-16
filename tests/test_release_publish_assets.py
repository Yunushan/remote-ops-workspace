from __future__ import annotations

import copy
import hashlib
import importlib.util
import json
import shutil
import sys
import tempfile
from pathlib import Path

POLICY = (
    "Only accepted evidence records in this file can promote Linux i386, Linux armhf, "
    "or Windows XP native-host readiness. Accepted records must include release asset URLs, "
    "review-bundle manifest release asset URL binding, review bundle release asset URLs, "
    "release-importable artifact source binding, "
    "source artifact repository-id binding from exact source-run metadata, "
    "source artifact run-created timestamp binding from exact source-run metadata, "
    "source artifact run-start timestamp binding from exact source-run metadata, "
    "source artifact run-window timestamp binding from exact source-run metadata, "
    "source artifact retention expiration binding from exact source artifact metadata, "
    "release source head SHA binding, "
    "release source run-attempt binding, "
    "same release source workflow run URL cannot carry conflicting run attempts, "
    "release source workflow file binding, "
    "local protected-goal evidence preflight command binding, "
    "source artifact staged upload command binding, "
    "staged upload source/evidence/output root separation, "
    "finalized accepted-record source file binding, "
    "finalized accepted-record release asset URL binding, "
    "canonical finalized accepted-record JSON byte binding, "
    "published native and review-bundle release asset byte binding, "
    "published release asset GitHub id/API URL binding, "
    "Linux release source artifact names must be target/release-scoped, "
    "Linux accepted evidence command paths must be target/release-scoped, "
    "XP release source artifact names must be target/release-scoped, "
    "XP accepted evidence command paths must be target/release-scoped, "
    "and per-artifact SHA-256 digests, safe relative non-link native archive entries, "
    "exact safe checksum and native manifest file references, "
    "target architecture/format manifest binding, "
    "exact safe release asset URL filenames, "
    "exact required check lists, exact workflow dispatch input sets, "
    "workflow dispatch release repository binding, exact evidence source record fields, "
    "exact release source and review bundle fields, "
    "Linux builder identity evidence, builder identity "
    "SHA-256, builder identity release/run binding, "
    "Linux builder workflow provenance binding, "
    "exact Linux builder identity fields, "
    "Linux builder/smoke source file binding, "
    "Linux builder/smoke host identity binding, "
    "Linux builder/smoke security evidence binding, "
    "Linux builder source head SHA binding, "
    "Linux builder observed Git HEAD binding, "
    "Linux builder clean checkout binding, "
    "Linux builder/smoke runtime OS identity binding, "
    "Linux builder host identity binding when applicable, "
    "Linux builder rpm and non-interactive sudo evidence, Linux security patch evidence, "
    "Linux security smoke proof-line binding, exact Linux smoke proof-line occurrence binding, "
    "case-insensitive Linux forbidden security proof-line rejection, "
    "Linux native smoke summary binding, "
    "Linux native build and smoke command provenance, "
    "Linux smoke evidence SHA-256, Linux smoke release/run/source head SHA binding, "
    "Linux smoke runtime architecture and userland binding, "
    "Linux smoke sanitized host identity and observed-at timestamp binding, "
    "Linux workflow dispatch inputs when applicable, XP workflow dispatch inputs when applicable, "
    "XP evidence source file binding, XP evidence release source binding, "
    "XP evidence bundle SHA-256 digests, "
    "XP evidence validation command binding, XP evidence contract SHA-256, "
    "XP evidence summary binding, exact XP evidence summary fields, XP host identity SHA-256 binding, "
    "XP sanitized target-scoped host identity binding, XP smoke host identity binding, "
    "XP smoke observed-at timestamp binding, XP smoke OS identity binding, "
    "XP smoke host probe proof-line binding, exact XP smoke proof-line occurrence binding, "
    "case-insensitive XP forbidden security proof-line rejection, "
    "XP security patch evidence, "
    "tracked scripts/xp_smoke_runner.cmd XP smoke command provenance, "
    "canonical XP smoke proof-file command binding, "
    "XP security smoke command provenance binding when applicable, "
    "canonical XP smoke evidence-file summary binding and "
    "XP security smoke proof-line binding when applicable, and review "
    "bundle manifest, review bundle archive, safe relative non-symlink review bundle archive entries, "
    "and review bundle SHA-256 sidecar digests "
    "before strict promotion, and release uploads must include those review bundle files with matching "
    "size, SHA-256 and checksum-sidecar coverage plus canonical finalized accepted-record JSON "
    "with matching size and SHA-256; each accepted record must include "
    "the promotion config SHA-256, have a unique target, include no unrecognized top-level fields, "
    "all release evidence for one record must "
    "use the same GitHub repository, protected platform goal records for one release must use "
    "one release source head SHA and target-specific release source workflow files plus positive release source run attempts, "
    "partial protected platform goal records must use one release_tag, GitHub repository, "
    "target-specific release source workflow file, release source head SHA "
    "and positive release source run attempt before promotion, and Windows XP x86/x64 pairs must use the same release_tag, "
    "GitHub repository, target-specific release source workflow file, release source head SHA "
    "and positive release source run attempts. "
    "Empty means no promotion."
)
MOBA_PARITY_POLICY = (
    "Only accepted evidence records in this file can close strict MobaXterm 26.4 Home/Professional parity "
    "articles. Accepted records must include one unique article_id, status accepted, a vX.Y.Z release_tag, "
    "a release_target, the exact validation command for that article, SHA-256 digests for the validated "
    "evidence JSON and evidence assets, release asset URLs under the same GitHub release tag, per-artifact "
    "SHA-256 digests, required article checks, and a validation summary proving the article evidence passed. "
    "Empty means the generated feature-family score remains separate from true product-depth parity."
)


def test_release_publish_asset_checker_passes_current_tree() -> None:
    checker = _load_checker()

    assert checker.main([]) == 0


def test_release_publish_asset_checker_requires_strict_platform_goal_assets_dir() -> None:
    checker = _load_checker()

    assert checker.main(["--require-platform-goal-targets", "--tag", "v1.0.6"]) == 2


def test_release_publish_asset_checker_requires_strict_platform_goal_tag(tmp_path: Path) -> None:
    checker = _load_checker()

    assert checker.main(["--require-platform-goal-targets", "--assets-dir", str(tmp_path)]) == 2


def test_expected_release_assets_expand_default_matrix() -> None:
    checker = _load_checker()
    matrix = _load_matrix()

    assets = checker.expected_release_assets(matrix)

    assert "remote_ops_workspace-1.0.6-py3-none-any.whl" in assets
    assert "remote-ops-workspace-v1.0.6-windows-x86-setup.exe" in assets
    assert "remote-ops-workspace-v1.0.6-macos-arm64.pkg" in assets
    assert "remote-ops-workspace-v1.0.6-linux-amd64.deb" in assets
    assert "remote-ops-workspace-v1.0.6-linux-aarch64-native-SHA256SUMS.txt" in assets
    assert "remote-ops-workspace-v1.0.6-linux-i386.deb" not in assets
    assert "remote-ops-workspace-v1.0.6-linux-armhf.deb" not in assets


def test_expected_release_assets_normalize_to_requested_tag() -> None:
    checker = _load_checker()
    matrix = _load_matrix()

    assets = checker.expected_release_assets(matrix, tag="v1.0.3")

    assert "remote_ops_workspace-1.0.3-py3-none-any.whl" in assets
    assert "remote-ops-workspace-v1.0.3-windows-x64-setup.exe" in assets
    assert "remote_ops_workspace-1.0.6-py3-none-any.whl" not in assets
    assert "remote-ops-workspace-v1.0.6-windows-x64-setup.exe" not in assets


def test_publish_contract_rejects_gated_default_asset_without_evidence() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    linux_job = next(job for job in matrix["default_github_release"]["native_jobs"] if job["job"] == "linux-native")
    linux_job["asset_patterns"].append("remote-ops-workspace-v1.0.6-linux-i386.deb")

    errors = checker.check_publish_contract(matrix, workflow, evidence_registry=_empty_evidence_registry())

    assert any("gated native asset remote-ops-workspace-v1.0.6-linux-i386.deb" in error for error in errors)


def test_publish_contract_uses_explicit_empty_platform_registry(monkeypatch) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    linux_job = next(job for job in matrix["default_github_release"]["native_jobs"] if job["job"] == "linux-native")
    linux_job["asset_patterns"].append("remote-ops-workspace-v1.0.6-linux-i386.deb")
    monkeypatch.setattr(checker, "read_evidence_registry", lambda: _accepted_evidence_registry("linux-i386"))

    errors = checker.check_publish_contract(matrix, workflow, evidence_registry={})

    assert any(
        "default release matrix includes gated native asset remote-ops-workspace-v1.0.6-linux-i386.deb "
        "for linux-i386 without accepted platform evidence for release_tag v1.0.6"
        in error
        for error in errors
    )


def test_publish_contract_allows_gated_default_asset_with_accepted_evidence() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    linux_job = next(job for job in matrix["default_github_release"]["native_jobs"] if job["job"] == "linux-native")
    linux_job["asset_patterns"].append("remote-ops-workspace-v1.0.2-linux-i386.deb")

    errors = checker.check_publish_contract(
        matrix,
        workflow,
        tag="v1.0.2",
        evidence_registry=_accepted_evidence_registry("linux-i386"),
    )

    assert not any("gated native asset remote-ops-workspace-v1.0.2-linux-i386.deb" in error for error in errors)


def test_publish_contract_rejects_gated_default_asset_with_wrong_release_evidence() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    linux_job = next(job for job in matrix["default_github_release"]["native_jobs"] if job["job"] == "linux-native")
    linux_job["asset_patterns"].append("remote-ops-workspace-v1.0.6-linux-i386.deb")

    errors = checker.check_publish_contract(
        matrix,
        workflow,
        tag="v1.0.3",
        evidence_registry=_accepted_evidence_registry("linux-i386"),
    )

    assert any(
        "default release matrix includes gated native asset remote-ops-workspace-v1.0.3-linux-i386.deb "
        "for linux-i386 without accepted platform evidence for release_tag v1.0.3"
        in error
        for error in errors
    )


def test_publish_contract_rejects_gated_asset_with_unfinalized_platform_candidate() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    linux_job = next(job for job in matrix["default_github_release"]["native_jobs"] if job["job"] == "linux-native")
    linux_job["asset_patterns"].append("remote-ops-workspace-v1.0.6-linux-i386.deb")
    registry = _accepted_evidence_registry("linux-i386")
    registry["accepted_evidence"][0].pop("review_bundle")

    errors = checker.check_publish_contract(matrix, workflow, evidence_registry=registry)

    assert any("gated native asset remote-ops-workspace-v1.0.6-linux-i386.deb" in error for error in errors)


def test_publish_contract_rejects_malformed_accepted_evidence_for_gated_asset() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    linux_job = next(job for job in matrix["default_github_release"]["native_jobs"] if job["job"] == "linux-native")
    linux_job["asset_patterns"].append("remote-ops-workspace-v1.0.6-linux-i386.deb")

    errors = checker.check_publish_contract(
        matrix,
        workflow,
        evidence_registry={
            "schema_version": 1,
            "policy": POLICY,
            "accepted_evidence": [
                {
                    "target": "linux-i386",
                    "status": "accepted",
                    "readiness_percent": 100.0,
                }
            ],
        },
    )

    assert any("gated native asset remote-ops-workspace-v1.0.6-linux-i386.deb" in error for error in errors)


def test_publish_contract_rejects_xp_asset_without_complete_xp_pair() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    windows_job = next(job for job in matrix["default_github_release"]["native_jobs"] if job["job"] == "windows-native")
    windows_job["asset_patterns"].append("remote-ops-workspace-v1.0.6-windows-xp-x86-native.zip")

    errors = checker.check_publish_contract(
        matrix,
        workflow,
        evidence_registry=_accepted_evidence_registry("windows-xp-native-x86"),
    )

    assert any("XP native promotion requires accepted evidence for both targets" in error for error in errors)


def test_publish_contract_requires_validation_before_upload() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        "python scripts/check_release_publish_assets.py --assets-dir release-assets --tag",
        "python scripts/check_release_matrix.py # disabled publish asset validation",
    )

    errors = checker.check_publish_contract(matrix, workflow)

    assert any("publish asset validation" in error for error in errors)


def test_publish_contract_requires_repository_bound_validation() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        ' --repository "${{ github.repository }}"',
        "",
    )

    errors = checker.check_publish_contract(matrix, workflow)

    assert any("publish evidence repository binding" in error for error in errors)


def test_publish_contract_requires_platform_goal_gate_before_upload() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        " --require-platform-goal-targets",
        "",
    )

    errors = checker.check_publish_contract(matrix, workflow)

    assert any("protected platform goal publish gate" in error for error in errors)


def test_publish_contract_requires_protected_platform_release_asset_gate() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        '      - name: Require protected platform release assets\n'
        '        run: python scripts/check_protected_platform_goal.py --release-tag "$RELEASE_TAG" --require-complete --assets-dir release-assets --repository "${{ github.repository }}"\n',
        "",
    )

    errors = checker.check_publish_contract(matrix, workflow)

    assert any("protected platform release asset gate" in error for error in errors)


def test_publish_contract_requires_protected_asset_gate_before_publish_asset_validation() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    protected_gate = (
        '      - name: Require protected platform release assets\n'
        '        run: python scripts/check_protected_platform_goal.py --release-tag "$RELEASE_TAG" --require-complete --assets-dir release-assets --repository "${{ github.repository }}"\n'
    )
    workflow = workflow.replace(protected_gate, "")

    errors = checker.check_publish_contract(matrix, workflow)

    assert "protected platform release asset gate must run before protected publish asset validation" in errors


def test_publish_contract_requires_protected_asset_gate_before_release_upload() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    protected_gate = (
        '      - name: Require protected platform release assets\n'
        '        run: python scripts/check_protected_platform_goal.py --release-tag "$RELEASE_TAG" --require-complete --assets-dir release-assets --repository "${{ github.repository }}"\n'
    )
    workflow = workflow.replace(protected_gate, "") + protected_gate

    errors = checker.check_publish_contract(matrix, workflow)

    assert "protected platform release asset gate must run before protected GitHub release upload" in errors


def test_publish_contract_requires_remote_evidence_audit_after_upload() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    audit_step = (
        '      - name: Audit published protected platform evidence\n'
        '        env:\n'
        '          GH_TOKEN: ${{ github.token }}\n'
        '        run: python scripts/check_platform_release_evidence_remote.py --repository "${{ github.repository }}" --release-tag "$RELEASE_TAG" --require-goal-targets --require-source-runs --require-source-artifact-bytes --require-final-record-bytes --require-release-asset-bytes --require-tag-source-head\n'
    )
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        audit_step,
        "",
    )

    errors = checker.check_publish_contract(matrix, workflow)

    assert any("published protected platform evidence audit" in error for error in errors)


def test_publish_contract_rejects_remote_evidence_audit_before_upload() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    audit_step = (
        '      - name: Audit published protected platform evidence\n'
        '        env:\n'
        '          GH_TOKEN: ${{ github.token }}\n'
        '        run: python scripts/check_platform_release_evidence_remote.py --repository "${{ github.repository }}" --release-tag "$RELEASE_TAG" --require-goal-targets --require-source-runs --require-source-artifact-bytes --require-final-record-bytes --require-release-asset-bytes --require-tag-source-head\n'
    )
    upload_step = (
        '      - name: Upload release assets\n'
        '        uses: softprops/action-gh-release@c12583777ecdfd3be55c69cf75464299dc01057e # v3\n'
        '        with:\n'
        '          fail_on_unmatched_files: true\n'
        '          files: release-assets/**\n'
    )
    workflow = workflow.replace(audit_step, "").replace(upload_step, audit_step + upload_step)

    errors = checker.check_publish_contract(matrix, workflow)

    assert "published protected platform evidence audit must run after GitHub release upload" in errors


def test_publish_contract_requires_remote_evidence_audit_token_and_actions_read() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        "      actions: read\n",
        "",
    ).replace(
        "          GH_TOKEN: ${{ github.token }}\n",
        "",
    )

    errors = checker.check_publish_contract(matrix, workflow)

    assert any("Actions metadata read permission" in error for error in errors)
    assert any("GitHub token for published evidence audit" in error for error in errors)


def test_publish_contract_rejects_release_preflight_continue_on_error() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        '      - name: Require protected platform accepted records\n'
        '        run: python scripts/check_protected_platform_goal.py --release-tag "$RELEASE_TAG" --require-records-complete --show-requirements\n',
        '      - name: Require protected platform accepted records\n'
        '        continue-on-error: true\n'
        '        run: python scripts/check_protected_platform_goal.py --release-tag "$RELEASE_TAG" --require-records-complete --show-requirements\n',
    )

    errors = checker.check_publish_contract(matrix, workflow)

    assert "accepted-platform-evidence-assets job must not use continue-on-error: true for protected release gates" in errors


def test_publish_contract_rejects_publish_continue_on_error() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        '      - name: Require protected platform release assets\n'
        '        run: python scripts/check_protected_platform_goal.py --release-tag "$RELEASE_TAG" --require-complete --assets-dir release-assets --repository "${{ github.repository }}"\n',
        '      - name: Require protected platform release assets\n'
        '        continue-on-error: true\n'
        '        run: python scripts/check_protected_platform_goal.py --release-tag "$RELEASE_TAG" --require-complete --assets-dir release-assets --repository "${{ github.repository }}"\n',
    )

    errors = checker.check_publish_contract(matrix, workflow)

    assert "publish-protected-platform-evidence job must not use continue-on-error: true for protected release gates" in errors


def test_publish_contract_keeps_core_release_independent_from_protected_evidence() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        "      - linux-native\n    steps:\n",
        "      - linux-native\n      - accepted-platform-evidence-assets\n    steps:\n",
        1,
    )

    errors = checker.check_publish_contract(matrix, workflow)

    assert "core publish job must not depend on accepted-platform-evidence-assets" in errors


def test_publish_contract_requires_clean_checkouts_for_release_jobs() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    block = checker.workflow_job_block(workflow, "linux-native")
    assert block
    workflow = workflow.replace(block, block.replace("          clean: true\n", "", 1), 1)

    errors = checker.check_publish_contract(matrix, workflow)

    assert "linux-native job missing clean release checkout: clean: true" in errors


def test_publish_contract_rejects_clean_checkout_setting_outside_checkout_step() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    block = checker.workflow_job_block(workflow, "linux-native")
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

    errors = checker.check_publish_contract(matrix, workflow)

    assert "linux-native job missing clean release checkout: clean: true" in errors


def test_publish_contract_rejects_persist_credentials_outside_checkout_step() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    block = checker.workflow_job_block(workflow, "publish")
    assert block
    mutated = block.replace("          persist-credentials: false\n", "", 1).replace(
        "      - uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1 # v6\n",
        "      - name: Misleading checkout credential setting\n"
        "        run: echo persist\n"
        "        env:\n"
        "          persist-credentials: false\n"
        "      - uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1 # v6\n",
        1,
    )
    workflow = workflow.replace(block, mutated, 1)

    errors = checker.check_publish_contract(matrix, workflow)

    assert "publish job missing checkout credential isolation: persist-credentials: false" in errors


def test_publish_contract_requires_platform_evidence_import_job() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        "accepted-platform-evidence-assets",
        "removed-platform-evidence-assets",
    )

    errors = checker.check_publish_contract(matrix, workflow)

    assert "release workflow missing accepted-platform-evidence-assets job" in errors


def test_publish_contract_rejects_platform_evidence_import_write_permissions() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        "      actions: read\n",
        "      actions: write\n",
    )

    errors = checker.check_publish_contract(matrix, workflow)

    assert "accepted-platform-evidence-assets job must not request write permissions" in errors


def test_publish_contract_rejects_platform_evidence_import_continue_on_error() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        '      - name: Import accepted protected platform evidence artifacts\n'
        '        env:\n'
        '          GH_TOKEN: ${{ github.token }}\n'
        '        run: python scripts/import_platform_evidence_artifacts.py --release-tag "$RELEASE_TAG" --release-head-sha "$(git -C release-source rev-parse HEAD)" --require-goal-targets --out-dir release-assets --verify-source-run --repository "${{ github.repository }}"\n',
        '      - name: Import accepted protected platform evidence artifacts\n'
        '        continue-on-error: true\n'
        '        env:\n'
        '          GH_TOKEN: ${{ github.token }}\n'
        '        run: python scripts/import_platform_evidence_artifacts.py --release-tag "$RELEASE_TAG" --release-head-sha "$(git -C release-source rev-parse HEAD)" --require-goal-targets --out-dir release-assets --verify-source-run --repository "${{ github.repository }}"\n',
    )

    errors = checker.check_publish_contract(matrix, workflow)

    assert (
        "accepted-platform-evidence-assets job must not use continue-on-error: true "
        "for protected release gates"
    ) in errors


def test_publish_contract_rejects_platform_evidence_import_nonstandard_write_permissions() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        "      contents: read\n",
        "      contents: read\n      id-token: write\n",
    )

    errors = checker.check_publish_contract(matrix, workflow)

    assert "accepted-platform-evidence-assets job must not request write permissions" in errors


def test_publish_contract_requires_platform_evidence_import_timeout() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        "    runs-on: ubuntu-latest\n    timeout-minutes: 20\n    permissions:",
        "    runs-on: ubuntu-latest\n    permissions:",
        1,
    )

    errors = checker.check_platform_evidence_import_job(workflow)

    assert any("bounded platform evidence import timeout" in error for error in errors)


def test_publish_contract_requires_platform_evidence_import_clean_checkout() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        "          clean: true\n"
        "      - name: Check out immutable release source for evidence binding\n",
        "      - name: Check out immutable release source for evidence binding\n",
        1,
    )

    errors = checker.check_platform_evidence_import_job(workflow)

    assert "accepted-platform-evidence-assets job missing clean release checkout: clean: true" in errors


def test_platform_evidence_import_rejects_clean_setting_outside_checkout_step() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    block = checker.workflow_job_block(workflow, "accepted-platform-evidence-assets")
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

    errors = checker.check_platform_evidence_import_job(workflow)

    assert "accepted-platform-evidence-assets job missing clean release checkout: clean: true" in errors


def test_platform_evidence_import_rejects_persist_credentials_outside_checkout_step() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    block = checker.workflow_job_block(workflow, "accepted-platform-evidence-assets")
    assert block
    mutated = block.replace("          persist-credentials: false\n", "", 1).replace(
        "      - uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1 # v6\n",
        "      - name: Misleading credential isolation setting\n"
        "        run: echo credentials\n"
        "        env:\n"
        "          persist-credentials: false\n"
        "      - uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1 # v6\n",
        1,
    )
    workflow = workflow.replace(block, mutated, 1)

    errors = checker.check_platform_evidence_import_job(workflow)

    assert (
        "accepted-platform-evidence-assets job missing checkout credential isolation: "
        "persist-credentials: false"
    ) in errors


def test_publish_contract_requires_platform_evidence_import_hidden_file_exclusion() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        "          include-hidden-files: false\n",
        "",
    )

    errors = checker.check_platform_evidence_import_job(workflow)

    assert any("imported asset hidden file exclusion" in error for error in errors)


def test_publish_contract_requires_platform_evidence_import_retention_window() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        "          retention-days: 90\n",
        "",
    )

    errors = checker.check_platform_evidence_import_job(workflow)

    assert any("imported asset retention window" in error for error in errors)


def test_publish_contract_requires_platform_evidence_import_before_upload() -> None:
    checker = _load_checker()
    workflow = """
jobs:
  accepted-platform-evidence-assets:
    needs: release-preflight
    permissions:
      actions: read
      contents: read
    steps:
      - uses: actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10 # v6
        with:
          persist-credentials: false
      - uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1 # v6
      - uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7
        with:
          name: release-platform-evidence-assets
          path: release-assets/*
          if-no-files-found: error
      - name: Import accepted protected platform evidence artifacts
        env:
          GH_TOKEN: ${{ github.token }}
        run: python scripts/import_platform_evidence_artifacts.py --release-tag "${{ github.ref_name }}" --require-goal-targets --out-dir release-assets
"""

    errors = checker.check_platform_evidence_import_job(workflow)

    assert "platform evidence import must run before imported artifact upload" in errors


def test_publish_contract_requires_platform_evidence_source_run_verification() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        " --verify-source-run",
        "",
    )

    errors = checker.check_platform_evidence_import_job(workflow)

    assert any("source run metadata verification" in error for error in errors)


def test_publish_contract_requires_repository_bound_platform_evidence_import() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        ' --repository "${{ github.repository }}"',
        "",
    )

    errors = checker.check_platform_evidence_import_job(workflow)

    assert any("repository-bound accepted evidence import" in error for error in errors)


def test_publish_contract_rejects_platform_evidence_import_dry_run() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        " --verify-source-run",
        " --verify-source-run --dry-run",
    )

    errors = checker.check_platform_evidence_import_job(workflow)

    assert "platform evidence import job must download accepted artifacts, not run with --dry-run" in errors


def test_publish_contract_requires_platform_review_bundle_validation() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        "python scripts/check_platform_review_bundle_artifacts.py --bundle-dir release-assets",
        "python scripts/check_platform_review_bundle_artifacts.py --help",
    )

    errors = checker.check_platform_evidence_import_job(workflow)

    assert any("imported platform review bundle validator" in error for error in errors)


def test_publish_contract_requires_platform_final_record_asset_validation() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        " --require-final-record-assets",
        "",
    )

    errors = checker.check_platform_evidence_import_job(workflow)

    assert any("imported finalized accepted-record asset validator" in error for error in errors)


def test_publish_contract_requires_platform_review_bundle_validation_before_upload() -> None:
    checker = _load_checker()
    workflow = """
jobs:
  accepted-platform-evidence-assets:
    needs: release-preflight
    permissions:
      actions: read
      contents: read
    steps:
      - uses: actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10 # v6
        with:
          persist-credentials: false
      - uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1 # v6
      - name: Import accepted protected platform evidence artifacts
        env:
          GH_TOKEN: ${{ github.token }}
        run: python scripts/import_platform_evidence_artifacts.py --release-tag "${{ github.ref_name }}" --require-goal-targets --out-dir release-assets
      - uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7
        with:
          name: release-platform-evidence-assets
          path: release-assets/*
          if-no-files-found: error
      - name: Validate imported protected platform review bundles
        run: python scripts/check_platform_review_bundle_artifacts.py --bundle-dir release-assets --require-goal-targets --release-tag "${{ github.ref_name }}"
"""

    errors = checker.check_platform_evidence_import_job(workflow)

    assert "platform review bundle validation must run before imported artifact upload" in errors


def test_publish_contract_rejects_malformed_mobaxterm_parity_registry() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")

    errors = checker.check_publish_contract(
        matrix,
        workflow,
        mobaxterm_parity_registry={"schema_version": 1, "policy": "", "accepted_evidence": []},
    )

    assert any("mobaxterm parity evidence policy missing" in error for error in errors)


def test_publish_contract_can_require_complete_mobaxterm_parity_registry() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")

    errors = checker.check_publish_contract(
        matrix,
        workflow,
        mobaxterm_parity_registry=_empty_mobaxterm_parity_registry(),
        require_mobaxterm_parity_complete=True,
    )

    assert any("missing required MobaXterm parity articles" in error for error in errors)


def test_publish_contract_can_require_platform_goal_targets() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")

    errors = checker.check_publish_contract(
        matrix,
        workflow,
        evidence_registry=_accepted_evidence_registry(),
        require_platform_goal_targets=True,
    )

    assert any("missing required accepted evidence targets" in error for error in errors)


def test_publish_contract_allows_complete_platform_goal_targets() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")

    errors = checker.check_publish_contract(
        matrix,
        workflow,
        tag="v1.0.2",
        evidence_registry=_accepted_evidence_registry(
            "linux-i386",
            "linux-armhf",
            "windows-xp-native-x86",
            "windows-xp-native-x64",
        ),
        require_platform_goal_targets=True,
    )

    assert not any("missing required accepted evidence targets" in error for error in errors)


def test_publish_contract_rejects_goal_target_evidence_for_wrong_release_tag() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")

    errors = checker.check_publish_contract(
        matrix,
        workflow,
        tag="v1.0.3",
        evidence_registry=_accepted_evidence_registry(
            "linux-i386",
            "linux-armhf",
            "windows-xp-native-x86",
            "windows-xp-native-x64",
        ),
        require_platform_goal_targets=True,
    )

    assert (
        "missing required accepted evidence targets for release_tag v1.0.3: "
        "['linux-armhf', 'linux-i386', 'windows-xp-native-x64', 'windows-xp-native-x86']"
    ) in errors


def test_publish_contract_allows_complete_synthetic_mobaxterm_parity_registry() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")

    errors = checker.check_publish_contract(
        matrix,
        workflow,
        mobaxterm_parity_registry=_complete_mobaxterm_parity_registry(),
        require_mobaxterm_parity_complete=True,
    )

    assert not any("mobaxterm parity evidence" in error for error in errors)
    assert not any("MobaXterm parity" in error for error in errors)


def test_release_assets_report_missing_expected_files(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()

    errors = checker.check_release_assets(tmp_path, matrix, tag="v1.0.2")

    assert any("missing expected files" in error for error in errors)


def test_release_assets_report_gated_extra_files(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    (tmp_path / "remote-ops-workspace-v1.0.2-linux-armhf.deb").write_text("native\n", encoding="utf-8")

    errors = checker.check_release_assets(
        tmp_path,
        matrix,
        tag="v1.0.2",
        evidence_registry=_empty_evidence_registry(),
    )

    assert any("gated native asset remote-ops-workspace-v1.0.2-linux-armhf.deb" in error for error in errors)


def test_release_assets_use_explicit_empty_platform_registry(tmp_path: Path, monkeypatch) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    (tmp_path / "remote-ops-workspace-v1.0.2-linux-i386.deb").write_text("native\n", encoding="utf-8")
    monkeypatch.setattr(checker, "read_evidence_registry", lambda: _accepted_evidence_registry("linux-i386"))

    errors = checker.check_release_assets(
        tmp_path,
        matrix,
        tag="v1.0.2",
        evidence_registry={},
    )

    assert any(
        "release asset directory includes gated native asset remote-ops-workspace-v1.0.2-linux-i386.deb "
        "for linux-i386 without accepted platform evidence for release_tag v1.0.2"
        in error
        for error in errors
    )


def test_release_assets_reject_accepted_evidence_hash_mismatch(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    _add_default_linux_asset(matrix, "remote-ops-workspace-v1.0.2-linux-i386.deb")
    _write_synthetic_release_assets(checker, matrix, tmp_path)

    errors = checker.check_release_assets(
        tmp_path,
        matrix,
        tag="v1.0.2",
        evidence_registry=_accepted_evidence_registry("linux-i386"),
    )

    assert (
        "release asset remote-ops-workspace-v1.0.2-linux-i386.deb SHA-256 does not match "
        "accepted evidence for linux-i386"
    ) in errors


def test_release_assets_allow_accepted_evidence_hash_match(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    registry = _accepted_evidence_registry("linux-i386")
    record = registry["accepted_evidence"][0]
    _add_default_linux_assets(matrix, record["artifact_sha256"])
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    _sync_evidence_artifact_hashes(record, tmp_path)
    _write_accepted_review_bundle_assets(record, tmp_path)

    errors = checker.check_release_assets(
        tmp_path,
        matrix,
        tag="v1.0.2",
        evidence_registry=registry,
    )

    assert errors == []


def test_release_assets_reject_missing_final_accepted_record_asset(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    registry = _accepted_evidence_registry("linux-i386")
    record = registry["accepted_evidence"][0]
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    _write_accepted_evidence_assets(record, tmp_path)
    final_record = tmp_path / "platform-verified-evidence-linux-i386-final.json"
    final_record.unlink()

    errors = checker.check_release_assets(
        tmp_path,
        matrix,
        tag="v1.0.2",
        evidence_registry=registry,
    )

    assert (
        "linux-i386 accepted evidence finalized record asset missing from release directory: "
        "platform-verified-evidence-linux-i386-final.json"
    ) in errors


def test_release_assets_reject_final_accepted_record_asset_drift(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    registry = _accepted_evidence_registry("linux-i386")
    record = registry["accepted_evidence"][0]
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    _write_accepted_evidence_assets(record, tmp_path)
    final_record = tmp_path / "platform-verified-evidence-linux-i386-final.json"
    data = json.loads(final_record.read_text(encoding="utf-8"))
    data["readiness_percent"] = 99.0
    final_record.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    errors = checker.check_release_assets(
        tmp_path,
        matrix,
        tag="v1.0.2",
        evidence_registry=registry,
    )

    assert (
        "linux-i386 accepted evidence finalized record asset must match accepted registry record: "
        "platform-verified-evidence-linux-i386-final.json"
    ) in errors


def test_release_assets_reject_noncanonical_final_accepted_record_asset(
    tmp_path: Path,
) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    registry = _accepted_evidence_registry("linux-i386")
    record = registry["accepted_evidence"][0]
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    _write_accepted_evidence_assets(record, tmp_path)
    final_record = tmp_path / "platform-verified-evidence-linux-i386-final.json"
    data = json.loads(final_record.read_text(encoding="utf-8"))
    final_record.write_text(json.dumps(data, sort_keys=True) + "\n", encoding="utf-8")

    errors = checker.check_release_assets(
        tmp_path,
        matrix,
        tag="v1.0.2",
        evidence_registry=registry,
    )

    assert (
        "linux-i386 accepted evidence finalized record asset must use canonical sorted JSON: "
        "platform-verified-evidence-linux-i386-final.json"
    ) in errors


def test_release_assets_final_record_helper_rejects_non_string_registry_keys(
    tmp_path: Path,
) -> None:
    checker = _load_checker()
    record = _accepted_evidence_record("linux-i386")
    record[True] = "coerced-private-field"
    final_record = tmp_path / "platform-verified-evidence-linux-i386-final.json"
    final_record.write_text("{}\n", encoding="utf-8")

    errors = checker.check_final_accepted_record_asset(
        final_record,
        target="linux-i386",
        record=record,
    )

    assert errors == [
        "linux-i386 accepted evidence finalized registry record keys must be strings, got True"
    ]


def test_release_assets_public_record_does_not_stringify_keys() -> None:
    checker = _load_checker()
    record = _accepted_evidence_record("linux-i386")
    record["_scratch"] = "private"
    record[True] = "coerced"

    public = checker.public_record(record)

    assert "_scratch" not in public
    assert True not in public
    assert "True" not in public
    assert public["target"] == "linux-i386"


def test_accepted_platform_release_assets_ignores_malformed_target(
    monkeypatch,
) -> None:
    checker = _load_checker()
    monkeypatch.setattr(checker, "validate_accepted_evidence_registry", lambda _registry: [])
    registry = {
        "schema_version": 1,
        "policy": "test",
        "accepted_evidence": [
            {
                "target": True,
                "status": "accepted",
                "readiness_percent": 100.0,
                "release_tag": "v1.0.2",
                "release_asset_urls": [],
                "artifact_sha256": {},
            }
        ],
    }

    assets = checker.accepted_platform_release_assets(registry, tag="v1.0.2")

    assert assets == set()
    assert "platform-verified-evidence-True-final.json" not in assets


def test_release_assets_reject_accepted_evidence_missing_review_bundle(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    registry = _accepted_evidence_registry("linux-i386")
    record = registry["accepted_evidence"][0]
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    _write_accepted_native_assets(record, tmp_path)
    _sync_evidence_artifact_hashes(record, tmp_path)

    errors = checker.check_release_assets(
        tmp_path,
        matrix,
        tag="v1.0.2",
        evidence_registry=registry,
    )

    assert (
        "linux-i386 accepted evidence review bundle asset missing from release directory: "
        "extended-linux-evidence-bundle-linux-i386-v1.0.2.json"
    ) in errors


def test_release_asset_hashes_reject_unsafe_review_bundle_file_name(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    registry = _accepted_evidence_registry("linux-i386")
    record = registry["accepted_evidence"][0]
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    _write_accepted_evidence_assets(record, tmp_path)
    _sync_evidence_artifact_hashes(record, tmp_path)
    record["review_bundle"]["manifest"]["file"] = (
        r"nested\extended-linux-evidence-bundle-linux-i386-v1.0.2.json"
    )
    monkeypatch.setattr(checker, "validate_accepted_evidence_registry", lambda _registry: [])
    assets = {path.name for path in tmp_path.iterdir() if path.is_file()}

    errors = checker.check_platform_evidence_asset_hashes(
        tmp_path,
        assets,
        tag="v1.0.2",
        evidence_registry=registry,
    )

    assert (
        "linux-i386 accepted evidence review_bundle manifest.file must be an exact safe file name: "
        r"'nested\\extended-linux-evidence-bundle-linux-i386-v1.0.2.json'"
    ) in errors


def test_release_asset_hashes_reject_non_string_accepted_evidence_release_asset_url(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    registry = _accepted_evidence_registry("linux-i386")
    record = registry["accepted_evidence"][0]
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    _write_accepted_evidence_assets(record, tmp_path)
    _sync_evidence_artifact_hashes(record, tmp_path)
    record["release_asset_urls"][0] = True
    monkeypatch.setattr(checker, "validate_accepted_evidence_registry", lambda _registry: [])
    assets = {path.name for path in tmp_path.iterdir() if path.is_file()}

    errors = checker.check_platform_evidence_asset_hashes(
        tmp_path,
        assets,
        tag="v1.0.2",
        evidence_registry=registry,
    )

    assert "linux-i386 accepted evidence release_asset_urls entries must be strings, got True" in errors


def test_release_asset_hashes_reject_out_of_scope_accepted_evidence_release_asset_urls(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    registry = _accepted_evidence_registry("linux-i386")
    record = registry["accepted_evidence"][0]
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    _write_accepted_evidence_assets(record, tmp_path)
    _sync_evidence_artifact_hashes(record, tmp_path)
    first_url = str(record["release_asset_urls"][0])
    second_url = str(record["release_asset_urls"][1])
    record["release_asset_urls"][0] = first_url.replace("https://github.com/", "https://example.com/")
    record["release_asset_urls"][1] = second_url.replace("/releases/download/v1.0.2/", "/releases/download/v1.0.1/")
    monkeypatch.setattr(checker, "validate_accepted_evidence_registry", lambda _registry: [])
    assets = {path.name for path in tmp_path.iterdir() if path.is_file()}

    errors = checker.check_platform_evidence_asset_hashes(
        tmp_path,
        assets,
        tag="v1.0.2",
        evidence_registry=registry,
    )

    assert (
        "linux-i386 accepted evidence release_asset_urls entries must be "
        f"GitHub release asset URLs: {record['release_asset_urls'][0]}"
    ) in errors
    assert (
        "linux-i386 accepted evidence release_asset_urls tag must match "
        f"release tag v1.0.2: {record['release_asset_urls'][1]}"
    ) in errors


def test_release_asset_hashes_reject_wrong_repository_release_asset_urls(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    registry = _accepted_evidence_registry("linux-i386")
    record = registry["accepted_evidence"][0]
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    _write_accepted_evidence_assets(record, tmp_path)
    _sync_evidence_artifact_hashes(record, tmp_path)
    record["release_asset_urls"][0] = str(record["release_asset_urls"][0]).replace(
        "https://github.com/example/remote-ops-workspace/",
        "https://github.com/example/wrong-workspace/",
    )
    monkeypatch.setattr(checker, "validate_accepted_evidence_registry", lambda _registry: [])
    assets = {path.name for path in tmp_path.iterdir() if path.is_file()}

    errors = checker.check_platform_evidence_asset_hashes(
        tmp_path,
        assets,
        tag="v1.0.2",
        repository="example/remote-ops-workspace",
        evidence_registry=registry,
    )

    assert (
        "linux-i386 accepted evidence release_asset_urls repository must match "
        f"release repository example/remote-ops-workspace: {record['release_asset_urls'][0]}"
    ) in errors


def test_release_asset_hashes_reject_invalid_expected_repository(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    registry = _accepted_evidence_registry("linux-i386")
    record = registry["accepted_evidence"][0]
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    _write_accepted_evidence_assets(record, tmp_path)
    _sync_evidence_artifact_hashes(record, tmp_path)
    monkeypatch.setattr(checker, "validate_accepted_evidence_registry", lambda _registry: [])
    assets = {path.name for path in tmp_path.iterdir() if path.is_file()}

    errors = checker.check_platform_evidence_asset_hashes(
        tmp_path,
        assets,
        tag="v1.0.2",
        repository="not a repository",
        evidence_registry=registry,
    )

    assert "release repository must be a GitHub owner/name value, got 'not a repository'" in errors


def test_release_asset_hashes_reject_non_string_accepted_evidence_artifact_key(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    registry = _accepted_evidence_registry("linux-i386")
    record = registry["accepted_evidence"][0]
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    _write_accepted_evidence_assets(record, tmp_path)
    _sync_evidence_artifact_hashes(record, tmp_path)
    record["artifact_sha256"][True] = "0" * 64
    monkeypatch.setattr(checker, "validate_accepted_evidence_registry", lambda _registry: [])
    assets = {path.name for path in tmp_path.iterdir() if path.is_file()}

    errors = checker.check_platform_evidence_asset_hashes(
        tmp_path,
        assets,
        tag="v1.0.2",
        evidence_registry=registry,
    )

    assert "linux-i386 accepted evidence artifact_sha256 keys must be exact safe file names, got True" in errors


def test_release_asset_hashes_reject_non_string_accepted_evidence_artifact_digest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    registry = _accepted_evidence_registry("linux-i386")
    record = registry["accepted_evidence"][0]
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    _write_accepted_evidence_assets(record, tmp_path)
    _sync_evidence_artifact_hashes(record, tmp_path)
    asset_name = next(iter(record["artifact_sha256"]))
    record["artifact_sha256"][asset_name] = True
    monkeypatch.setattr(checker, "validate_accepted_evidence_registry", lambda _registry: [])
    assets = {path.name for path in tmp_path.iterdir() if path.is_file()}

    errors = checker.check_platform_evidence_asset_hashes(
        tmp_path,
        assets,
        tag="v1.0.2",
        evidence_registry=registry,
    )

    assert (
        f"linux-i386 accepted evidence artifact_sha256.{asset_name} "
        "must be a lowercase SHA-256 hex digest"
    ) in errors
    assert not any(f"release asset {asset_name} SHA-256 does not match" in error for error in errors)


def test_release_asset_hashes_reject_non_string_review_bundle_file_name(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    registry = _accepted_evidence_registry("linux-i386")
    record = registry["accepted_evidence"][0]
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    _write_accepted_evidence_assets(record, tmp_path)
    _sync_evidence_artifact_hashes(record, tmp_path)
    record["review_bundle"]["manifest"]["file"] = True
    monkeypatch.setattr(checker, "validate_accepted_evidence_registry", lambda _registry: [])
    assets = {path.name for path in tmp_path.iterdir() if path.is_file()}

    errors = checker.check_platform_evidence_asset_hashes(
        tmp_path,
        assets,
        tag="v1.0.2",
        evidence_registry=registry,
    )

    assert "linux-i386 accepted evidence review_bundle manifest.file must be an exact safe file name: True" in errors


def test_release_asset_hashes_reject_non_string_review_bundle_digest(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    registry = _accepted_evidence_registry("linux-i386")
    record = registry["accepted_evidence"][0]
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    _write_accepted_evidence_assets(record, tmp_path)
    _sync_evidence_artifact_hashes(record, tmp_path)
    archive_record = record["review_bundle"]["archive"]
    bundle_name = str(archive_record["file"])
    archive_record["sha256"] = True
    monkeypatch.setattr(checker, "validate_accepted_evidence_registry", lambda _registry: [])
    assets = {path.name for path in tmp_path.iterdir() if path.is_file()}

    errors = checker.check_platform_evidence_asset_hashes(
        tmp_path,
        assets,
        tag="v1.0.2",
        evidence_registry=registry,
    )

    assert (
        "linux-i386 accepted evidence review_bundle archive.sha256 "
        "must be a lowercase SHA-256 hex digest"
    ) in errors
    assert not any(
        f"release review bundle asset {bundle_name} SHA-256 does not match" in error
        for error in errors
    )


def test_release_asset_hashes_reject_boolean_review_bundle_size(
    tmp_path: Path,
    monkeypatch,
) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    registry = _accepted_evidence_registry("linux-i386")
    record = registry["accepted_evidence"][0]
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    _write_accepted_evidence_assets(record, tmp_path)
    _sync_evidence_artifact_hashes(record, tmp_path)
    archive_record = record["review_bundle"]["archive"]
    archive_path = tmp_path / str(archive_record["file"])
    archive_path.write_bytes(b"x")
    archive_record["size_bytes"] = True
    archive_record["sha256"] = _sha256(archive_path)
    monkeypatch.setattr(checker, "validate_accepted_evidence_registry", lambda _registry: [])
    assets = {path.name for path in tmp_path.iterdir() if path.is_file()}

    errors = checker.check_platform_evidence_asset_hashes(
        tmp_path,
        assets,
        tag="v1.0.2",
        evidence_registry=registry,
    )

    assert (
        "release review bundle asset extended-linux-evidence-bundle-linux-i386-v1.0.2.zip "
        "size does not match accepted evidence for linux-i386"
    ) in errors


def test_release_assets_reject_accepted_evidence_review_bundle_hash_mismatch(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    registry = _accepted_evidence_registry("linux-i386")
    record = registry["accepted_evidence"][0]
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    _write_accepted_evidence_assets(record, tmp_path)
    _sync_evidence_artifact_hashes(record, tmp_path)
    bundle_name = record["review_bundle"]["archive"]["file"]
    (tmp_path / str(bundle_name)).write_bytes(b"tampered review bundle\n")

    errors = checker.check_release_assets(
        tmp_path,
        matrix,
        tag="v1.0.2",
        evidence_registry=registry,
    )

    assert (
        "release review bundle asset extended-linux-evidence-bundle-linux-i386-v1.0.2.zip "
        "SHA-256 does not match accepted evidence for linux-i386"
    ) in errors


def test_release_assets_reject_accepted_evidence_review_bundle_content_mismatch(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    registry = _accepted_evidence_registry("linux-i386")
    record = registry["accepted_evidence"][0]
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    _write_accepted_evidence_assets(record, tmp_path)
    review_bundle = record["review_bundle"]
    assert isinstance(review_bundle, dict)
    archive_record = review_bundle["archive"]
    sidecar_record = review_bundle["sha256s"]
    manifest_record = review_bundle["manifest"]
    assert isinstance(archive_record, dict)
    assert isinstance(sidecar_record, dict)
    assert isinstance(manifest_record, dict)
    archive_path = tmp_path / str(archive_record["file"])
    sidecar_path = tmp_path / str(sidecar_record["file"])
    manifest_path = tmp_path / str(manifest_record["file"])
    archive_path.write_bytes(b"not a review bundle zip\n")
    archive_record["size_bytes"] = archive_path.stat().st_size
    archive_record["sha256"] = _sha256(archive_path)
    sidecar_path.write_text(
        f"{_sha256(manifest_path)}  {manifest_path.name}\n"
        f"{_sha256(archive_path)}  {archive_path.name}\n",
        encoding="utf-8",
    )
    sidecar_record["size_bytes"] = sidecar_path.stat().st_size
    sidecar_record["sha256"] = _sha256(sidecar_path)

    errors = checker.check_release_assets(
        tmp_path,
        matrix,
        tag="v1.0.2",
        evidence_registry=registry,
    )

    assert any(
        "linux-i386 review bundle archive is not a readable ZIP" in error
        for error in errors
    )


def test_release_assets_reject_review_bundle_sidecar_missing_archive_reference(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    registry = _accepted_evidence_registry("linux-i386")
    record = registry["accepted_evidence"][0]
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    _write_accepted_evidence_assets(record, tmp_path)
    _sync_evidence_artifact_hashes(record, tmp_path)
    review_bundle = record["review_bundle"]
    assert isinstance(review_bundle, dict)
    sidecar_record = review_bundle["sha256s"]
    assert isinstance(sidecar_record, dict)
    sidecar_path = tmp_path / str(sidecar_record["file"])
    sidecar_path.write_text(sidecar_path.read_text(encoding="utf-8").splitlines()[0] + "\n", encoding="utf-8")
    sidecar_record["size_bytes"] = sidecar_path.stat().st_size
    sidecar_record["sha256"] = _sha256(sidecar_path)

    errors = checker.check_release_assets(
        tmp_path,
        matrix,
        tag="v1.0.2",
        evidence_registry=registry,
    )

    assert any(
        "checksum sidecars missing references for expected files" in error
        and "extended-linux-evidence-bundle-linux-i386-v1.0.2.zip" in error
        for error in errors
    )


def test_release_assets_allow_evidence_backed_assets_outside_default_matrix(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    registry = _accepted_evidence_registry("linux-i386")
    record = registry["accepted_evidence"][0]
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    _write_accepted_evidence_assets(record, tmp_path)
    _sync_evidence_artifact_hashes(record, tmp_path)

    errors = checker.check_release_assets(
        tmp_path,
        matrix,
        tag="v1.0.2",
        evidence_registry=registry,
    )

    assert errors == []


def test_release_assets_reject_accepted_evidence_release_url_query_string(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    registry = _accepted_evidence_registry("linux-i386")
    record = registry["accepted_evidence"][0]
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    _write_accepted_evidence_assets(record, tmp_path)
    record["release_asset_urls"][0] = f"{record['release_asset_urls'][0]}?download=1"

    errors = checker.check_release_assets(
        tmp_path,
        matrix,
        tag="v1.0.2",
        evidence_registry=registry,
    )

    assert any(
        "linux-i386 release asset URL file name must be an exact safe file name" in error
        or "linux-i386 accepted evidence release_asset_urls file name must be an exact safe file name" in error
        for error in errors
    )


def test_release_assets_reject_accepted_evidence_release_url_path_segment(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    registry = _accepted_evidence_registry("linux-i386")
    record = registry["accepted_evidence"][0]
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    _write_accepted_evidence_assets(record, tmp_path)
    record["release_asset_urls"][0] = record["release_asset_urls"][0].replace(
        "/releases/download/v1.0.2/",
        "/releases/download/v1.0.2/nested/",
    )

    errors = checker.check_release_assets(
        tmp_path,
        matrix,
        tag="v1.0.2",
        evidence_registry=registry,
    )

    assert any(
        "linux-i386 release asset URL file name must be an exact safe file name" in error
        or "linux-i386 accepted evidence release_asset_urls file name must be an exact safe file name" in error
        for error in errors
    )


def test_release_assets_reject_accepted_evidence_missing_referenced_asset(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    _write_synthetic_release_assets(checker, matrix, tmp_path)

    errors = checker.check_release_assets(
        tmp_path,
        matrix,
        tag="v1.0.2",
        evidence_registry=_accepted_evidence_registry("linux-i386"),
    )

    assert (
        "linux-i386 accepted evidence release asset missing from release directory: "
        "remote-ops-workspace-v1.0.2-linux-i386.deb"
    ) in errors


def test_release_assets_accept_complete_synthetic_directory(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    _write_synthetic_release_assets(checker, matrix, tmp_path)

    errors = checker.check_release_assets(tmp_path, matrix, tag="v1.0.2")

    assert errors == []


def test_release_assets_reject_release_manifest_boolean_size_bytes(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    manifest = tmp_path / "remote-ops-workspace-v1.0.2-release-manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    first_artifact = data["artifacts"][0]
    first_artifact["size_bytes"] = True
    manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    filename = Path(str(first_artifact["file"])).name

    errors = checker.check_release_assets(tmp_path, matrix, tag="v1.0.2")

    assert f"{manifest.name} artifact {filename} missing positive size_bytes" in errors


def test_release_manifest_rejects_non_list_artifacts(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    manifest = tmp_path / "remote-ops-workspace-v1.0.2-release-manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    data["artifacts"] = {"file": "remote-ops-workspace-v1.0.2.tar.gz"}
    manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    errors = checker.check_release_manifest(tmp_path, matrix, tag="v1.0.2")

    assert errors == [f"{manifest.name} artifacts must be a list"]


def test_release_manifest_rejects_malformed_artifact_sha256(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    manifest = tmp_path / "remote-ops-workspace-v1.0.2-release-manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    first_artifact = data["artifacts"][0]
    filename = Path(str(first_artifact["file"])).name
    first_artifact["sha256"] = True
    manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    errors = checker.check_release_manifest(tmp_path, matrix, tag="v1.0.2")

    assert (
        f"{manifest.name} artifact {filename} "
        "sha256 must be a lowercase SHA-256 hex digest"
    ) in errors
    assert f"{manifest.name} artifact {filename} sha256 does not match release asset" not in errors


def test_release_manifest_rejects_artifact_size_drift(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    manifest = tmp_path / "remote-ops-workspace-v1.0.2-release-manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    first_artifact = data["artifacts"][0]
    filename = Path(str(first_artifact["file"])).name
    first_artifact["size_bytes"] = (tmp_path / filename).stat().st_size + 1
    manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    errors = checker.check_release_manifest(tmp_path, matrix, tag="v1.0.2")

    assert f"{manifest.name} artifact {filename} size_bytes does not match release asset" in errors


def test_release_manifest_rejects_artifact_sha256_drift(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    manifest = tmp_path / "remote-ops-workspace-v1.0.2-release-manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    first_artifact = data["artifacts"][0]
    filename = Path(str(first_artifact["file"])).name
    first_artifact["sha256"] = "0" * 64
    manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    errors = checker.check_release_manifest(tmp_path, matrix, tag="v1.0.2")

    assert f"{manifest.name} artifact {filename} sha256 does not match release asset" in errors


def test_release_manifest_accepts_exact_artifact_file_reference(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    manifest = tmp_path / "remote-ops-workspace-v1.0.2-release-manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    first_artifact = data["artifacts"][0]
    first_artifact["file"] = Path(str(first_artifact["file"])).name
    manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    errors = checker.check_release_manifest(tmp_path, matrix, tag="v1.0.2")

    assert errors == []


def test_release_manifest_rejects_path_qualified_artifact_file_reference(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    manifest = tmp_path / "remote-ops-workspace-v1.0.2-release-manifest.json"
    data = json.loads(manifest.read_text(encoding="utf-8"))
    first_artifact = data["artifacts"][0]
    filename = Path(str(first_artifact["file"])).name
    first_artifact["file"] = f"../{filename}"
    manifest.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")

    errors = checker.check_release_manifest(tmp_path, matrix, tag="v1.0.2")

    assert (
        f"{manifest.name} artifact file must be an exact release file name or dist/<file>: '../{filename}'" in errors
    )
    assert any(
        error.startswith(f"{manifest.name} missing source/Python artifact records: ") and filename in error
        for error in errors
    )


def test_release_assets_reject_symlinked_asset_directory(tmp_path: Path, monkeypatch) -> None:
    checker = _load_checker()
    matrix = _load_matrix()

    def fake_is_symlink(self: Path) -> bool:
        return self == tmp_path

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = checker.check_release_assets(tmp_path, matrix, tag="v1.0.2")

    assert errors == [f"release asset directory must not be a symlink: {tmp_path}"]


def test_release_assets_reject_file_shaped_asset_directory(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    assets_dir = tmp_path / "release-assets.zip"

    errors = checker.check_release_assets(assets_dir, matrix, tag="v1.0.2")

    assert errors == [
        f"release asset directory must be a directory path, got {assets_dir.as_posix()!r}"
    ]
    assert not assets_dir.exists()


def test_release_assets_reject_non_path_asset_directory() -> None:
    checker = _load_checker()
    matrix = _load_matrix()

    errors = checker.check_release_assets("release-assets", matrix, tag="v1.0.2")

    assert errors == [
        "release asset directory path must be a pathlib.Path, got 'release-assets'"
    ]


def test_release_asset_path_helpers_reject_non_path_args() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    registry = _accepted_evidence_registry("linux-i386")
    record = registry["accepted_evidence"][0]

    assert checker.check_directory_path_hint(
        "release-assets",
        "release asset directory",
    ) == [
        "release asset directory path must be a pathlib.Path, got 'release-assets'"
    ]
    assert checker.check_path_not_reserved_workspace_root(
        ["release-assets"],
        "release asset directory",
    ) == [
        "release asset directory path must be a pathlib.Path, got ['release-assets']"
    ]
    assert checker.check_path_parent_symlinks(
        {"path": "release-assets"},
        "release asset directory",
    ) == [
        "release asset directory path must be a pathlib.Path, got {'path': 'release-assets'}"
    ]
    assert checker.check_release_asset_symlinks(True) == [
        "release asset directory path must be a pathlib.Path, got True"
    ]
    assert checker.check_release_asset_root_entries(False) == [
        "release asset directory path must be a pathlib.Path, got False"
    ]
    assert checker.check_platform_review_bundle_artifacts(
        "release-assets",
        tag="v1.0.2",
        evidence_registry=registry,
    ) == [
        "release asset directory path must be a pathlib.Path, got 'release-assets'"
    ]
    assert checker.check_platform_evidence_asset_hashes(
        "release-assets",
        set(),
        tag="v1.0.2",
        evidence_registry=registry,
    ) == [
        "release asset directory path must be a pathlib.Path, got 'release-assets'"
    ]
    assert checker.check_final_accepted_record_asset(
        "platform-verified-evidence-linux-i386-final.json",
        target="linux-i386",
        record=record,
    ) == [
        "linux-i386 accepted evidence finalized record asset path must be a pathlib.Path, "
        "got 'platform-verified-evidence-linux-i386-final.json'"
    ]
    assert checker.check_checksum_sidecars("release-assets", set()) == [
        "release asset directory path must be a pathlib.Path, got 'release-assets'"
    ]
    assert checker.check_release_manifest(
        "release-assets",
        matrix,
        tag="v1.0.2",
    ) == [
        "release asset directory path must be a pathlib.Path, got 'release-assets'"
    ]


def test_release_assets_reject_reserved_workspace_asset_directory() -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    assets_dir = Path(".github") / "release-assets"

    errors = checker.check_release_assets(assets_dir, matrix, tag="v1.0.2")

    assert errors == [
        "release asset directory must not point inside "
        f"reserved workspace directory '.github': {assets_dir}"
    ]
    assert not assets_dir.exists()


def test_release_assets_reject_symlinked_asset_directory_parent(
    tmp_path: Path, monkeypatch
) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    parent = tmp_path / "linked-parent"
    assets_dir = parent / "release-assets"
    assets_dir.mkdir(parents=True)

    def fake_is_symlink(self: Path) -> bool:
        return self == parent

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = checker.check_release_assets(assets_dir, matrix, tag="v1.0.2")

    assert errors == [
        f"release asset directory path must not contain symlinked directories: {parent}"
    ]


def test_release_assets_reject_symlinked_release_asset(tmp_path: Path, monkeypatch) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    symlink_name = "remote_ops_workspace-1.0.2-py3-none-any.whl"

    def fake_is_symlink(self: Path) -> bool:
        return self.name == symlink_name

    monkeypatch.setattr(type(tmp_path), "is_symlink", fake_is_symlink)

    errors = checker.check_release_assets(tmp_path, matrix, tag="v1.0.2")

    assert f"release assets must not contain symlinks: ['{symlink_name}']" in errors


def test_release_asset_file_names_reject_ambiguous_names() -> None:
    checker = _load_checker()

    errors = checker.check_release_asset_file_names(
        [
            "remote-ops-workspace-v1.0.2-linux-amd64.deb",
            "remote-ops-workspace-v1.0.2-linux-amd64.deb",
            "Readme.txt",
            "readme.txt",
            "nested/asset.whl",
        ]
    )

    assert "release asset file names must be exact safe file names: ['nested/asset.whl']" in errors
    assert (
        "release asset file names must be unique: "
        "['remote-ops-workspace-v1.0.2-linux-amd64.deb']"
    ) in errors
    assert (
        "release asset file names must not collide on case-insensitive filesystems: "
        "['Readme.txt', 'readme.txt']"
    ) in errors


def test_release_assets_reject_nested_release_asset_directory(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    (tmp_path / "nested-output").mkdir()

    errors = checker.check_release_assets(tmp_path, matrix, tag="v1.0.2")

    assert "release assets must contain root files only, found directories: ['nested-output']" in errors


def test_release_assets_reject_checksum_mismatch(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    checksum = tmp_path / "remote-ops-workspace-v1.0.2-SHA256SUMS.txt"
    checksum.write_text("0" * 64 + "  remote_ops_workspace-1.0.2-py3-none-any.whl\n", encoding="utf-8")

    errors = checker.check_release_assets(tmp_path, matrix, tag="v1.0.2")

    assert any("checksum mismatch" in error for error in errors)


def test_release_assets_reject_checksum_path_reference(tmp_path: Path) -> None:
    checker = _load_checker()
    matrix = _load_matrix()
    _write_synthetic_release_assets(checker, matrix, tmp_path)
    checksum = tmp_path / "remote-ops-workspace-v1.0.2-SHA256SUMS.txt"
    asset = "remote_ops_workspace-1.0.2-py3-none-any.whl"
    checksum.write_text(
        checksum.read_text(encoding="utf-8").replace(f"  {asset}", f"  ../{asset}", 1),
        encoding="utf-8",
    )

    errors = checker.check_release_assets(tmp_path, matrix, tag="v1.0.2")

    assert (
        f"remote-ops-workspace-v1.0.2-SHA256SUMS.txt reference must be an exact safe file name: '../{asset}'"
        in errors
    )


def _write_synthetic_release_assets(checker, matrix: dict[str, object], root: Path) -> None:
    expected = checker.expected_release_assets(matrix, tag="v1.0.2")
    source_manifest_artifacts = checker.expected_source_manifest_artifacts(matrix, tag="v1.0.2")
    release_manifest = "remote-ops-workspace-v1.0.2-release-manifest.json"
    checksum_assets = {asset for asset in expected if asset.endswith("SHA256SUMS.txt")}

    for asset in sorted(expected - checksum_assets - {release_manifest}):
        (root / asset).write_bytes(f"{asset}\n".encode())

    manifest_payload = {
        "schema_version": 1,
        "artifacts": [
            {
                "file": f"dist/{asset}",
                "size_bytes": (root / asset).stat().st_size,
                "sha256": _sha256(root / asset),
            }
            for asset in sorted(source_manifest_artifacts)
        ],
    }
    (root / release_manifest).write_text(json.dumps(manifest_payload, indent=2) + "\n", encoding="utf-8")

    reference_assets = sorted(expected - checksum_assets)
    checksum_lines = "\n".join(f"{_sha256(root / asset)}  {asset}" for asset in reference_assets) + "\n"
    for checksum in checksum_assets:
        (root / checksum).write_text(checksum_lines, encoding="utf-8")


def _add_default_linux_asset(matrix: dict[str, object], asset: str) -> None:
    linux_job = next(job for job in matrix["default_github_release"]["native_jobs"] if job["job"] == "linux-native")
    linux_job["asset_patterns"].append(asset)


def _add_default_linux_assets(matrix: dict[str, object], assets: dict[str, object]) -> None:
    for asset in assets:
        _add_default_linux_asset(matrix, str(asset))


def _sync_evidence_artifact_hashes(record: dict[str, object], root: Path) -> None:
    hashes = record["artifact_sha256"]
    assert isinstance(hashes, dict)
    for asset in hashes:
        hashes[asset] = _sha256(root / str(asset))


def _write_accepted_evidence_assets(record: dict[str, object], root: Path) -> None:
    _write_accepted_native_assets(record, root)
    _sync_evidence_artifact_hashes(record, root)
    _write_accepted_review_bundle_assets(record, root)
    _write_final_accepted_record_asset(record, root)


def _write_accepted_native_assets(record: dict[str, object], root: Path) -> None:
    hashes = record["artifact_sha256"]
    assert isinstance(hashes, dict)
    assets = sorted(str(asset) for asset in hashes)
    sidecars = [asset for asset in assets if asset.endswith("SHA256SUMS.txt")]
    payloads = [asset for asset in assets if asset not in sidecars]
    for asset in payloads:
        (root / asset).write_bytes(f"{asset}\n".encode())
    checksum_lines = "\n".join(f"{_sha256(root / asset)}  {asset}" for asset in payloads) + "\n"
    for sidecar in sidecars:
        (root / sidecar).write_text(checksum_lines, encoding="utf-8")


def _write_accepted_review_bundle_assets(record: dict[str, object], root: Path) -> None:
    target = str(record["target"])
    if not target.startswith("linux-"):
        raise AssertionError(f"test helper only creates Linux review bundles, got {target}")
    _sync_evidence_artifact_hashes(record, root)
    finalizer = _load_script("finalize_platform_verified_evidence_record")
    bundle_helpers = _load_finalize_tests()
    release_tag = str(record["release_tag"])
    candidate = _prefinalized_candidate(record)
    hashes = candidate["artifact_sha256"]
    assert isinstance(hashes, dict)
    artifact_archive_files = {
        str(name): (root / str(name)).read_bytes()
        for name in sorted(hashes)
    }
    with tempfile.TemporaryDirectory(prefix=f"{target}-bundle-", dir=root) as raw_tmp:
        work_root = Path(raw_tmp)
        candidate_path = work_root / f"platform-verified-evidence-{target}.json"
        builder_path = work_root / f"builder-identity-{target}.json"
        smoke_path = work_root / f"native-smoke-{target}.log"
        builder_path.write_text(json.dumps(candidate["builder_identity"], indent=2) + "\n", encoding="utf-8")
        bundle_helpers._write_linux_smoke_evidence(
            smoke_path,
            target,
            hashes,
            builder_evidence=f"evidence/{target}/{release_tag}/builder-identity-{target}.json",
        )
        smoke_sha = _sha256(smoke_path)
        candidate["linux_smoke_evidence_sha256"] = {"native_smoke": smoke_sha}
        _sync_linux_source_record(candidate, "native_smoke", smoke_sha, smoke_path.stat().st_size)
        record["linux_smoke_evidence_sha256"] = candidate["linux_smoke_evidence_sha256"]
        _sync_linux_source_record(record, "native_smoke", smoke_sha, smoke_path.stat().st_size)
        candidate_path.write_text(json.dumps(candidate, indent=2) + "\n", encoding="utf-8")
        manifest, archive, sidecar = bundle_helpers._write_bundle_files(
            work_root,
            stem=f"extended-linux-evidence-bundle-{target}-{release_tag}",
            bundle_type="extended-linux-native-evidence",
            target=target,
            release_tag=release_tag,
                manifest_records={
                    "promotion_config_sha256": candidate["promotion_config_sha256"],
                    "release_asset_urls": candidate["release_asset_urls"],
                    "release_asset_source": candidate["release_asset_source"],
                    "validated_commands": bundle_helpers._linux_validated_commands(candidate),
                    "workflow": candidate["workflow"],
                "workflow_inputs": candidate["workflow_inputs"],
                "workflow_run_url": candidate["workflow_run_url"],
                "runner_labels": candidate["runner_labels"],
                "security_patch_evidence": candidate["builder_identity"]["security_patch_evidence"],
                "builder_evidence": bundle_helpers._file_record(builder_path),
                "smoke_evidence": [
                    bundle_helpers._smoke_file_record(smoke_path, smoke_id="native_smoke", name=smoke_path.name)
                ],
                "candidate_record": bundle_helpers._file_record(candidate_path),
                "artifacts": [
                    {
                        "file": str(name),
                        "size_bytes": (root / str(name)).stat().st_size,
                        "sha256": str(digest),
                    }
                    for name, digest in sorted(hashes.items())
                ],
            },
            archive_files={
                **artifact_archive_files,
                builder_path.name: builder_path.read_bytes(),
                smoke_path.name: smoke_path.read_bytes(),
                candidate_path.name: candidate_path.read_bytes(),
            },
        )
        errors, finalized = finalizer.finalize_platform_verified_evidence_record(
            candidate_record=candidate_path,
            bundle_manifest=manifest,
            bundle_archive=archive,
            bundle_sha256s=sidecar,
        )
        for bundle_file in (manifest, archive, sidecar):
            shutil.copyfile(bundle_file, root / bundle_file.name)
    assert errors == []
    record.clear()
    record.update(finalized)
    _write_final_accepted_record_asset(record, root)


def _write_final_accepted_record_asset(record: dict[str, object], root: Path) -> None:
    target = str(record["target"])
    path = root / f"platform-verified-evidence-{target}-final.json"
    path.write_bytes((json.dumps(record, indent=2, sort_keys=True) + "\n").encode("utf-8"))


def _prefinalized_candidate(record: dict[str, object]) -> dict[str, object]:
    candidate = copy.deepcopy(record)
    candidate.pop("review_bundle", None)
    candidate.pop("finalized_record_release_asset_url", None)
    source = candidate.get("release_asset_source")
    artifact_hashes = candidate.get("artifact_sha256")
    if isinstance(source, dict) and isinstance(artifact_hashes, dict):
        source_data = dict(source)
        source_data["contains_files"] = sorted(str(name) for name in artifact_hashes)
        candidate["release_asset_source"] = source_data
    return candidate


def _sync_linux_source_record(
    record: dict[str, object],
    key: str,
    sha256: str,
    size_bytes: int,
) -> None:
    sources = record.get("linux_evidence_sources")
    if isinstance(sources, dict) and isinstance(sources.get(key), dict):
        source = sources[key]
        source["sha256"] = sha256
        source["size_bytes"] = size_bytes


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _load_matrix() -> dict[str, object]:
    return json.loads(Path("configs/release_matrix.json").read_text(encoding="utf-8"))


def _empty_evidence_registry() -> dict[str, object]:
    return {"schema_version": 1, "accepted_evidence": []}


def _empty_mobaxterm_parity_registry() -> dict[str, object]:
    return {
        "schema_version": 1,
        "policy": MOBA_PARITY_POLICY,
        "accepted_evidence": [],
    }


def _complete_mobaxterm_parity_registry() -> dict[str, object]:
    checker = _load_mobaxterm_checker()
    return {
        "schema_version": 1,
        "policy": MOBA_PARITY_POLICY,
        "accepted_evidence": [
            _mobaxterm_parity_record(article_id, spec)
            for article_id, spec in sorted(checker.ARTICLE_SPECS.items())
        ],
    }


def _mobaxterm_parity_record(article_id: str, spec) -> dict[str, object]:
    artifact_name = f"{article_id}-evidence.zip"
    return {
        "article_id": article_id,
        "status": "accepted",
        "evidence_type": spec.evidence_type,
        "release_tag": "v1.0.2",
        "release_target": "windows-x64",
        "validation_command": spec.validation_command,
        "evidence_file_sha256": "a" * 64,
        "evidence_assets_sha256": {f"{article_id}.json": "b" * 64},
        "release_asset_urls": [
            f"https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/{artifact_name}"
        ],
        "artifact_sha256": {artifact_name: "c" * 64},
        "checks": sorted(spec.required_checks),
        "validation_summary": {
            "passed": True,
            "errors": [],
            "summary": {"article_id": article_id},
        },
    }


def _accepted_evidence_registry(*targets: str) -> dict[str, object]:
    return {
        "schema_version": 1,
        "policy": POLICY,
        "accepted_evidence": [_accepted_evidence_record(target) for target in targets],
    }


def _accepted_evidence_record(target: str) -> dict[str, object]:
    if target in {"linux-i386", "linux-armhf"}:
        return _linux_accepted_evidence(target)
    return _xp_accepted_evidence(target)


def _linux_accepted_evidence(target: str) -> dict[str, object]:
    arch = "i386" if target == "linux-i386" else "armhf"
    rpm_arch = "i686" if target == "linux-i386" else "armv7hl"
    artifact_arch = "i686" if target == "linux-i386" else "armhf"
    release_tag = "v1.0.2"
    assets_dir = f"staged/{target}/{release_tag}/artifacts"
    artifact = f"extended-linux-evidence-{target}-{release_tag}"
    base_url = "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2"
    release_asset_urls = [
        f"{base_url}/remote-ops-workspace-v1.0.2-linux-{arch}.deb",
        f"{base_url}/remote-ops-workspace-v1.0.2-linux-{rpm_arch}.rpm",
        f"{base_url}/remote-ops-workspace-v1.0.2-linux-{artifact_arch}.AppImage",
        f"{base_url}/remote-ops-workspace-v1.0.2-linux-{artifact_arch}-native.tar.gz",
        f"{base_url}/remote-ops-workspace-v1.0.2-linux-{artifact_arch}-native-manifest.json",
        f"{base_url}/remote-ops-workspace-v1.0.2-linux-{artifact_arch}-native-SHA256SUMS.txt",
    ]
    builder_identity = _builder_identity(target)
    builder_identity_sha = _json_sha256(builder_identity)
    linux_smoke_hashes = _linux_smoke_hashes()
    return {
        "target": target,
        "evidence_type": "extended-linux-native",
        "status": "accepted",
        "readiness_percent": 100.0,
        "release_tag": "v1.0.2",
        "promotion_config_sha256": _promotion_config_sha256(),
        "workflow": ".github/workflows/extended-platform-evidence.yml",
        "workflow_inputs": {
            "target": target,
            "release_tag": "v1.0.2",
            "release_asset_base_url": base_url,
        },
        "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "artifact_name": artifact,
        "runner_labels": ["self-hosted", "linux", arch],
        "builder_identity": builder_identity,
        "builder_identity_sha256": builder_identity_sha,
        "linux_evidence_sources": _linux_evidence_sources(
            target,
            builder_identity_sha,
            linux_smoke_hashes["native_smoke"],
        ),
        "native_build_command": (
            f"TARGET_ARCH={arch} PYTHON_BIN=.venv-native/bin/python bash scripts/make_linux_native.sh"
        ),
        "native_smoke_command": (
            f"bash scripts/smoke_linux_native.sh --arch {arch} --dist native-dist/linux "
            f"--target {target} --workflow-run-url https://github.com/example/remote-ops-workspace/actions/runs/12345 "
            f"--workflow-run-attempt 1 --source-head-sha {'a' * 40} "
            f"--builder-evidence evidence/{target}/v1.0.2/builder-identity-{target}.json"
        ),
        "linux_smoke_evidence_sha256": linux_smoke_hashes,
        "linux_smoke_summary": _linux_smoke_summary(target),
        "local_evidence_preflight_command": (
            "python scripts/check_platform_goal_local_evidence.py --root . "
            f"--release-tag v1.0.2 --target {target} --assets-dir {assets_dir} "
            f"--linux-builder-evidence evidence/{target}/v1.0.2/builder-identity-{target}.json "
            f"--linux-smoke-evidence evidence/{target}/v1.0.2/native-smoke-{target}.log "
            "--linux-workflow-run-url https://github.com/example/remote-ops-workspace/actions/runs/12345 "
            f"--linux-source-head-sha {'a' * 40} "
            "--linux-source-run-attempt 1 "
            "--repository example/remote-ops-workspace"
        ),
        "staged_upload_command": (
            "python scripts/stage_extended_linux_evidence_upload.py "
            f"--target {target} --release-tag v1.0.2 --source-dir {assets_dir} "
            f"--out-dir platform-evidence-upload/{target}/v1.0.2 --force"
        ),
        "artifact_validation_command": (
            f"python scripts/check_platform_promotion_artifacts.py --target {target} "
            f"--assets-dir {assets_dir} --tag v1.0.2 --strict"
        ),
        "checks": [
            "builder_preflight",
            "native_build",
            "native_smoke",
            "artifact_validation",
            "release_asset_attachment",
        ],
        "release_asset_urls": release_asset_urls,
        "artifact_sha256": _artifact_hashes_from_urls(release_asset_urls),
        "finalized_record_release_asset_url": (
            f"https://github.com/example/remote-ops-workspace/releases/download/v1.0.2/"
            f"platform-verified-evidence-{target}-final.json"
        ),
        "release_asset_source": _release_asset_source(
            target,
            artifact,
            release_asset_urls,
            include_review_bundle=True,
        ),
        "review_bundle": _review_bundle(target),
    }


def _xp_accepted_evidence(target: str) -> dict[str, object]:
    arch = "x86" if target.endswith("x86") else "x64"
    base_url = "https://github.com/example/remote-ops-workspace/releases/download/v1.0.2"
    evidence_file = f"evidence/{target}/v1.0.2/xp-evidence.json"
    assets_dir = f"native-dist/windows-xp/{target}/v1.0.2"
    evidence_dir = f"evidence/{target}/v1.0.2"
    smoke_ids = sorted(
        [
            "cli_launch",
            "gui_or_legacy_host_ui_launch",
            "loopback_profile_dry_run",
            "artifact_manifest_validation",
            "legacy_crypto_profile_scoped",
            "modern_defaults_unchanged",
        ]
    )
    os_summary: dict[str, object] = {
        "name": "Windows XP",
        "architecture": arch,
        "service_pack": "SP3" if arch == "x86" else "SP2",
    }
    if arch == "x64":
        os_summary["edition"] = "Professional x64 Edition"
    host_identity = _xp_host_identity(target)
    release_source = _xp_release_source_summary(target)
    security = _xp_security_patch_evidence()
    evidence_summary: dict[str, object] = {
        "target": target,
        "release_tag": "v1.0.2",
        "release_source": release_source,
        "host_identity": host_identity,
        "os": os_summary,
        "toolchain": {
            "separate_legacy_toolchain": True,
            "current_python_pyqt6_stack": False,
        },
        "security": {
            "legacy_crypto_profile_scoped": True,
            "modern_defaults_unchanged": True,
            "weak_crypto_global_default": False,
            "patch_evidence": security,
        },
        "smoke_ids": sorted(smoke_ids),
        "smoke_evidence_files": {
            smoke_id: f"xp-smoke-evidence/{smoke_id}.txt"
            for smoke_id in smoke_ids
        },
        "smoke_commands": {
            smoke_id: (
                f"scripts/xp_smoke_runner.cmd --target {target} --release-tag v1.0.2 "
                f"--smoke-id {smoke_id} --evidence-file xp-smoke-evidence/{smoke_id}.txt "
                f"--proof-file xp-smoke-proof/{smoke_id}.txt "
                f"--host-label {host_identity['host_label']} "
                f"--evidence-run-id {host_identity['evidence_run_id']} "
                f"--observed-at-utc {host_identity['observed_at_utc']} "
                f"--source-workflow-run-url {release_source['workflow_run_url']} "
                f"--source-head-sha {release_source['head_sha']} "
                f"--source-run-attempt {release_source['run_attempt']} "
                f"--security-update-channel {security['security_update_channel']} "
                f"--cve-review-reference {security['cve_review_reference']} "
                f'--os-name "{os_summary["name"]}" '
                f"--os-architecture {os_summary['architecture']} "
                f"--os-service-pack {os_summary['service_pack']}"
                + (
                    f' --os-edition "{os_summary["edition"]}"'
                    if "edition" in os_summary
                    else ""
                )
            )
            for smoke_id in smoke_ids
        },
    }
    smoke_hashes = {
        "cli_launch": "c" * 64,
        "gui_or_legacy_host_ui_launch": "d" * 64,
        "loopback_profile_dry_run": "e" * 64,
        "artifact_manifest_validation": "f" * 64,
        "legacy_crypto_profile_scoped": "1" * 64,
        "modern_defaults_unchanged": "2" * 64,
    }
    release_asset_urls = [
        f"{base_url}/remote-ops-workspace-v1.0.2-windows-xp-{arch}-native.zip",
        f"{base_url}/remote-ops-workspace-v1.0.2-windows-xp-{arch}-native-manifest.json",
        f"{base_url}/remote-ops-workspace-v1.0.2-windows-xp-{arch}-native-SHA256SUMS.txt",
    ]
    return {
        "target": target,
        "evidence_type": "windows-xp-native-host",
        "status": "accepted",
        "readiness_percent": 100.0,
        "release_tag": "v1.0.2",
        "promotion_config_sha256": _promotion_config_sha256(),
        "workflow": ".github/workflows/xp-native-evidence.yml",
        "workflow_inputs": {
            "target": target,
            "release_tag": "v1.0.2",
            "release_asset_base_url": base_url,
            "assets_dir": assets_dir,
            "evidence_file": evidence_file,
            "evidence_dir": evidence_dir,
        },
        "architecture": arch,
        "separate_legacy_toolchain": True,
        "current_python_pyqt6_stack": False,
        "xp_evidence_sha256": "b" * 64,
        "xp_evidence_contract_sha256": _xp_native_evidence_contract_sha256(),
        "xp_host_identity_sha256": _json_sha256(_xp_host_identity(target)),
        "xp_evidence_summary": evidence_summary,
        "xp_smoke_evidence_sha256": smoke_hashes,
        "xp_evidence_sources": _xp_evidence_sources(
            evidence_file,
            "b" * 64,
            evidence_summary,
            smoke_hashes,
        ),
        "native_evidence_validation_command": (
            "python scripts/check_xp_native_evidence.py "
            f"--evidence {evidence_file} "
            f"--assets-dir {assets_dir} "
            f"--evidence-dir {evidence_dir}"
        ),
        "local_evidence_preflight_command": (
            "python scripts/check_platform_goal_local_evidence.py --root . "
            f"--release-tag v1.0.2 --target {target} --assets-dir {assets_dir} "
            f"--xp-evidence {evidence_file} --xp-evidence-dir {evidence_dir} "
            "--xp-source-workflow-run-url https://github.com/example/remote-ops-workspace/actions/runs/12345 "
            f"--xp-source-head-sha {'a' * 40} "
            "--xp-source-run-attempt 1 "
            "--repository example/remote-ops-workspace"
        ),
        "staged_upload_command": (
            "python scripts/stage_xp_native_evidence_upload.py "
            f"--target {target} --release-tag v1.0.2 --assets-dir {assets_dir} "
            f"--evidence-output-dir xp-evidence-output/{target}/v1.0.2 "
            f"--out-dir platform-evidence-upload/{target}/v1.0.2 --force"
        ),
        "artifact_validation_command": (
            f"python scripts/check_platform_promotion_artifacts.py --target {target} "
            f"--assets-dir {assets_dir} --tag v1.0.2 --strict"
        ),
        "checks": [
            "xp_native_evidence_validation",
            "artifact_validation",
            "vm_or_host_smoke",
            "legacy_crypto_profile_scoped",
            "modern_defaults_unchanged",
            "release_asset_attachment",
        ],
        "release_asset_urls": release_asset_urls,
        "artifact_sha256": _artifact_hashes_from_urls(release_asset_urls),
        "finalized_record_release_asset_url": (
            f"{base_url}/platform-verified-evidence-{target}-final.json"
        ),
        "release_asset_source": _release_asset_source(
            target,
            f"xp-native-evidence-{target}-v1.0.2",
            release_asset_urls,
            include_review_bundle=True,
        ),
        "review_bundle": _review_bundle(target),
    }


def _artifact_hashes_from_urls(urls: list[str]) -> dict[str, str]:
    return {Path(url).name: "a" * 64 for url in urls}


def _xp_evidence_sources(
    evidence_file: str,
    evidence_sha: str,
    evidence_summary: dict[str, object],
    smoke_hashes: dict[str, str],
) -> dict[str, object]:
    smoke_files = evidence_summary["smoke_evidence_files"]
    assert isinstance(smoke_files, dict)
    return {
        "evidence": {
            "file": "xp-evidence.json",
            "path": evidence_file,
            "size_bytes": 4096,
            "sha256": evidence_sha,
        },
        "smoke_evidence": {
            str(smoke_id): {
                "file": str(smoke_file),
                "size_bytes": 256 + index,
                "sha256": smoke_hashes[str(smoke_id)],
            }
            for index, (smoke_id, smoke_file) in enumerate(sorted(smoke_files.items()))
        },
    }


def _release_asset_source(
    target: str,
    artifact_name: str,
    release_asset_urls: list[str],
    *,
    include_review_bundle: bool,
) -> dict[str, object]:
    contains_files = {Path(url).name for url in release_asset_urls}
    if include_review_bundle:
        review_bundle = _review_bundle(target)
        contains_files.update(
            str(record.get("file", ""))
            for record in (
                review_bundle["manifest"],
                review_bundle["archive"],
                review_bundle["sha256s"],
            )
            if isinstance(record, dict)
        )
        contains_files.add(f"platform-verified-evidence-{target}-final.json")
    return {
        "type": "github-actions-artifact",
        "workflow": _release_source_workflow(target),
        "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "artifact_name": artifact_name,
        "head_sha": "a" * 40,
        "run_attempt": 1,
        "contains_files": sorted(contains_files),
    }


def _release_source_workflow(target: str) -> str:
    if target.startswith("linux-"):
        return ".github/workflows/extended-platform-evidence.yml"
    return ".github/workflows/xp-native-evidence.yml"


def _xp_release_source_summary(target: str) -> dict[str, object]:
    return {
        "workflow": _release_source_workflow(target),
        "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "head_sha": "a" * 40,
        "run_attempt": 1,
    }


def _linux_smoke_hashes() -> dict[str, str]:
    return {"native_smoke": "6" * 64}


def _linux_smoke_summary(target: str, release_tag: str = "v1.0.2") -> dict[str, object]:
    machine = "i686" if target == "linux-i386" else "armv7l"
    dpkg_arch = "i386" if target == "linux-i386" else "armhf"
    target_arch = "i386" if target == "linux-i386" else "armhf"
    return {
        "target": target,
        "release_tag": release_tag,
        "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "workflow_run_attempt": 1,
        "source_head_sha": "a" * 40,
        "git_head_sha": "a" * 40,
        "target_arch": target_arch,
        "host_label": f"{target}-builder",
        "evidence_run_id": f"{target}-{release_tag.removeprefix('v').replace('.', '-')}-run-12345",
        "observed_at_utc": "2026-06-20T12:00:00Z",
        "uname_machine": machine,
        "dpkg_architecture": dpkg_arch,
        "userland_bits": "32",
        "os_release": "Debian GNU/Linux 12 (bookworm)",
        "kernel_release": "6.1.0-i386-ci",
        "glibc_version": "glibc 2.36",
        "python_ssl_openssl": "OpenSSL 3.0.13",
        "openssl_cli_version": "OpenSSL 3.0.13",
        "security": {
            "tls_minimum_modern_profiles": "TLS 1.2",
            "tls_preferred_modern_profiles": "TLS 1.3",
            "legacy_compatibility_profile": "isolated-opt-in",
            "legacy_crypto_scope": "profile-only",
            "weak_crypto_global_default": False,
            "modern_defaults_unchanged": True,
            "security_update_channel": "vendor-security-updates-2026-06",
            "cve_review_reference": "vendor-cve-advisory-review-2026-06",
        },
    }


def _linux_evidence_sources(
    target: str,
    builder_identity_sha: str,
    native_smoke_sha: str,
) -> dict[str, object]:
    return {
        "builder_identity": {
            "file": f"builder-identity-{target}.json",
            "sha256": builder_identity_sha,
            "size_bytes": 123,
        },
        "native_smoke": {
            "file": f"native-smoke-{target}.log",
            "sha256": native_smoke_sha,
            "size_bytes": 456,
        },
    }


def _review_bundle(target: str, *, release_tag: str = "v1.0.2") -> dict[str, object]:
    if target.startswith("linux-"):
        stem = f"extended-linux-evidence-bundle-{target}-{release_tag}"
        bundle_type = "extended-linux-native-evidence"
    else:
        stem = f"xp-native-evidence-bundle-{target}-{release_tag}"
        bundle_type = "windows-xp-native-host-evidence"
    base_url = f"https://github.com/example/remote-ops-workspace/releases/download/{release_tag}"
    return {
        "bundle_type": bundle_type,
        "manifest": {"file": f"{stem}.json", "sha256": "3" * 64, "size_bytes": 123},
        "archive": {"file": f"{stem}.zip", "sha256": "4" * 64, "size_bytes": 456},
        "sha256s": {"file": f"{stem}-SHA256SUMS.txt", "sha256": "5" * 64, "size_bytes": 78},
        "release_asset_urls": [
            f"{base_url}/{stem}.json",
            f"{base_url}/{stem}.zip",
            f"{base_url}/{stem}-SHA256SUMS.txt",
        ],
}


def _xp_host_identity(target: str) -> dict[str, object]:
    arch = "x86" if target.endswith("x86") else "x64"
    os_summary: dict[str, object] = {
        "name": "Windows XP",
        "architecture": arch,
        "service_pack": "SP3" if arch == "x86" else "SP2",
    }
    if arch == "x64":
        os_summary["edition"] = "Professional x64 Edition"
    return {
        "schema_version": 1,
        "target": target,
        "release_tag": "v1.0.2",
        "host_label": f"xp-{arch}-lab-01",
        "evidence_run_id": f"xp-{arch}-1-0-2-20260620t120000z",
        "observed_at_utc": "2026-06-20T12:00:00Z",
        "operator_private_data_redacted": True,
        "os": os_summary,
        "toolchain": {
            "separate_legacy_toolchain": True,
            "current_python_pyqt6_stack": False,
            "description": "Separate legacy XP-capable native host toolchain",
        },
    }


def _promotion_config_sha256() -> str:
    data = json.loads(Path("configs/platform_parity_promotion.json").read_text(encoding="utf-8"))
    return _json_sha256(data)


def _xp_native_evidence_contract_sha256() -> str:
    data = json.loads(Path("configs/xp_native_evidence_contract.json").read_text(encoding="utf-8"))
    return _json_sha256(data)


def _json_sha256(data: dict[str, object]) -> str:
    payload = json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(payload).hexdigest()


def _builder_identity(target: str) -> dict[str, object]:
    machine = "i686" if target == "linux-i386" else "armv7l"
    dpkg_arch = "i386" if target == "linux-i386" else "armhf"
    return {
        "schema_version": 1,
        "target": target,
        "release_tag": "v1.0.2",
        "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "workflow_run_attempt": 1,
        "workflow_ref": (
            "example/remote-ops-workspace/.github/workflows/"
            f"extended-platform-evidence.yml@{'a' * 40}"
        ),
        "workflow_sha": "a" * 40,
        "source_head_sha": "a" * 40,
        "observed_git_head_sha": "a" * 40,
        "git_worktree_clean": True,
        "host_identity": _linux_host_identity(target),
        "sudo_non_interactive": True,
        "sys_platform": "linux",
        "platform_machine": machine,
        "uname_machine": machine,
        "dpkg_architecture": dpkg_arch,
        "userland_bits": "32",
        "os_release": "Debian GNU/Linux 12 (bookworm)",
        "kernel_release": "6.1.0-i386-ci",
        "glibc_version": "glibc 2.36",
        "python_version": "3.12.0",
        "required_tools": {
            "bash": "/usr/bin/bash",
            "curl": "/usr/bin/curl",
            "dpkg": "/usr/bin/dpkg",
            "dpkg-deb": "/usr/bin/dpkg-deb",
            "getconf": "/usr/bin/getconf",
            "openssl": "/usr/bin/openssl",
            "rpm": "/usr/bin/rpm",
            "rpmbuild": "/usr/bin/rpmbuild",
            "sha256sum": "/usr/bin/sha256sum",
            "sudo": "/usr/bin/sudo",
            "tar": "/usr/bin/tar",
        },
        "security_patch_evidence": _security_patch_evidence(),
    }


def _linux_host_identity(target: str, release_tag: str = "v1.0.2") -> dict[str, object]:
    return {
        "schema_version": 1,
        "target": target,
        "release_tag": release_tag,
        "workflow_run_url": "https://github.com/example/remote-ops-workspace/actions/runs/12345",
        "workflow_run_attempt": 1,
        "host_label": f"{target}-builder",
        "evidence_run_id": f"{target}-{release_tag.removeprefix('v').replace('.', '-')}-run-12345",
        "observed_at_utc": "2026-06-20T12:00:00Z",
        "operator_private_data_redacted": True,
    }


def _security_patch_evidence() -> dict[str, object]:
    return {
        "python_ssl_openssl": "OpenSSL 3.0.13",
        "openssl_cli_version": "OpenSSL 3.0.13",
        "tls_minimum_modern_profiles": "TLS 1.2",
        "tls_preferred_modern_profiles": "TLS 1.3",
        "legacy_compatibility_profile": "isolated-opt-in",
        "cve_patch_reviewed": True,
        "security_update_channel": "vendor-security-updates-2026-06",
        "cve_review_reference": "vendor-cve-advisory-review-2026-06",
    }


def _xp_security_patch_evidence() -> dict[str, object]:
    return {
        "tls_minimum_modern_profiles": "TLS 1.2",
        "tls_preferred_modern_profiles": "TLS 1.3",
        "legacy_compatibility_profile": "isolated-opt-in",
        "cve_patch_reviewed": True,
        "security_update_channel": "vendor-security-updates-2026-06",
        "cve_review_reference": "vendor-cve-advisory-review-2026-06",
    }


def _load_checker():
    path = Path("scripts/check_release_publish_assets.py")
    spec = importlib.util.spec_from_file_location("check_release_publish_assets_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_script(name: str):
    path = Path("scripts") / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_finalize_tests():
    path = Path("tests/test_finalize_platform_verified_evidence_record.py")
    spec = importlib.util.spec_from_file_location("finalize_platform_verified_evidence_test_helpers_for_release", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _load_mobaxterm_checker():
    path = Path("scripts/check_mobaxterm_parity_evidence.py")
    spec = importlib.util.spec_from_file_location("check_mobaxterm_parity_evidence_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

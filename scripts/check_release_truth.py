from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_URL = "https://github.com/Yunushan/remote-ops-workspace"
REPOSITORY_CLONE_URL = f"{REPOSITORY_URL}.git"

WORKFLOW_ARCHES = {
    "windows-native": {"x86", "x64", "arm64"},
    "macos-native": {"x64", "arm64"},
    "linux-native": {"x86_64", "aarch64"},
}

RELEASE_PREFLIGHT_JOB = "release-preflight"
RELEASE_PREFLIGHT_DEPENDENTS = (
    "source-and-python",
    "windows-native",
    "macos-native",
    "linux-native",
    "accepted-platform-evidence-assets",
    "publish",
)
TAGGED_RELEASE_SOURCE_JOBS = (
    "source-and-python",
    "windows-native",
    "macos-native",
    "linux-native",
    "accepted-platform-evidence-assets",
    "publish",
)
PROTECTED_PUBLISH_JOB = "publish-protected-platform-evidence"
RELEASE_TAG_RESOLVER = "RELEASE_TAG: ${{ inputs.release_tag || github.ref_name }}"
TAGGED_RELEASE_REF = "ref: ${{ env.RELEASE_TAG }}"
FROZEN_RELEASE_REF = "ref: ${{ needs.release-preflight.outputs.release_sha }}"
FROZEN_RELEASE_SHA_ENV = "EXPECTED_RELEASE_SHA: ${{ needs.release-preflight.outputs.release_sha }}"
RELEASE_UPLOAD_TAG_NAME = "tag_name: ${{ env.RELEASE_TAG }}"
RELEASE_JOB_TIMEOUTS = {
    "release-preflight": 100,
    "source-and-python": 60,
    "windows-native": 240,
    "macos-native": 180,
    "linux-native": 120,
    "accepted-platform-evidence-assets": 20,
    "publish": 45,
}
RELEASE_VERSION_GATE_COMMAND = (
    'python scripts/check_release_version.py --release-tag "$RELEASE_TAG"'
)
RELEASE_VERIFY_COMMAND = (
    'python scripts/verify.py --quick --no-cli-smoke --release-tag "$RELEASE_TAG"'
)
PYTHON315_CI_EVIDENCE_COMMAND = "python scripts/check_python315_ci_evidence.py"
PROTECTED_PROMOTION_CONDITION = (
    "if: ${{ github.event_name == 'workflow_dispatch' && inputs.include_protected_platform_evidence }}"
)
CERTIFIED_EVIDENCE_IMPORT_CONDITION = (
    "if: ${{ github.event_name == 'push' || (github.event_name == 'workflow_dispatch' && inputs.include_protected_platform_evidence) }}"
)
PUBLISH_PROTECTED_PLATFORM_ASSET_COMMAND = (
    'python scripts/check_protected_platform_goal.py --release-tag "$RELEASE_TAG" '
    '--require-complete --assets-dir release-assets --repository "${{ github.repository }}"'
)
PUBLISH_PLATFORM_GOAL_COMMAND = (
    'python scripts/check_release_publish_assets.py --assets-dir release-assets '
    '--tag "$RELEASE_TAG" --repository "${{ github.repository }}" '
    "--require-platform-goal-targets"
)
PUBLISH_REMOTE_PLATFORM_EVIDENCE_AUDIT_COMMAND = (
    'python scripts/check_platform_release_evidence_remote.py --repository "${{ github.repository }}" '
    '--release-tag "$RELEASE_TAG" --require-goal-targets --require-source-runs '
    "--require-source-artifact-bytes --require-final-record-bytes "
    "--require-release-asset-bytes --require-tag-source-head"
)

REQUIRED_DOC_SNIPPETS = (
    "docs/PRODUCTION_READINESS.md",
    "complete 100/100 production-readiness checklist",
    "check_repository_governance.py --repository <owner/repo>",
    "check_release_provenance.py --assets-dir <release-assets> --tag <tag> --repository <owner/repo> --sha <release-sha>",
    "check_release_license_compliance.py --assets-dir <release-assets> --tag <tag> --repository <owner/repo> --sha <release-sha>",
    "check_release_maturity.py --release-tag <tag>",
    "blocked-pending-independent-review",
    "Production/Stable",
    "--require-hashes",
    "unsigned-preview.yml",
    "remote-ops-workspace-v1.0.27-linux-<amd64|arm64>.deb",
    "remote-ops-workspace-v1.0.27-linux-<x86_64|aarch64>.rpm",
    "remote-ops-workspace-v1.0.27-linux-<x86_64|aarch64>.AppImage",
    "remote-ops-workspace-v1.0.27-linux-<x86_64|aarch64>-native.tar.gz",
    "remote-ops-workspace-v1.0.27-macos-<x64|arm64>.dmg",
    "remote-ops-workspace-v1.0.27-macos-<x64|arm64>.pkg",
    "not uploaded by the default GitHub",
    "release_asset_provenance_complete=false",
    "asset-backed protected goal gate",
    "check_release_publish_assets.py --assets-dir release-assets --tag <tag> --repository <owner>/<repo> --require-platform-goal-targets",
    "import_platform_evidence_artifacts.py --release-tag <tag> --require-goal-targets --out-dir release-assets --verify-source-run --repository <owner>/<repo>",
    "check_platform_review_bundle_artifacts.py --bundle-dir release-assets --require-goal-targets --release-tag <tag> --require-final-record-assets",
    "check_platform_release_evidence_remote.py --repository <owner>/<repo> --release-tag <tag> --require-goal-targets --require-source-runs --require-source-artifact-bytes --require-final-record-bytes --require-release-asset-bytes --require-tag-source-head",
    "downloaded source artifact native artifact SHA-256 values plus review-bundle size/SHA-256 values",
    "published asset digests, sizes and bytes",
    "published final accepted-record JSON bytes",
    "release tag Git object/source head SHA",
    "GH_TOKEN` or `GITHUB_TOKEN",
    "`contents:read`\nand `actions:read`",
    "workflow_run.repository_id",
    "workflow_run.head_repository_id",
    "artifact created_at",
    "source artifact ZIP",
    "source run creation/start/update window",
    "workflow-file, source-head and",
    "run-attempt-bound accepted Linux i386, Linux armhf and Windows XP native-host artifacts",
    "target-specific release source workflow file",
    "positive release source run attempt",
    "observed_git_head_sha",
    "git_worktree_clean",
    "observed Git HEAD SHA matching the release source head SHA",
    "linux_smoke_summary",
    "profile-only legacy crypto scope",
    "weak crypto disabled by",
    "--observed-at-utc",
    "--source-workflow-run-url",
    "--source-head-sha",
    "--source-run-attempt",
    "--os-name",
    "--os-architecture",
    "--os-service-pack",
    "xp smoke observed at utc",
    "xp smoke source workflow run",
    "xp smoke source head sha",
    "xp smoke source run attempt",
    "xp smoke os name",
    "xp smoke os architecture",
    "xp smoke os service pack",
    "xp smoke host probe command",
    "xp smoke processor architecture env",
    "xp smoke wmic os caption",
    "wmic os get Caption,CSDVersion /value",
    "xp_evidence_summary.release_source",
    "scripts/xp_smoke_runner.cmd",
    "modern self-hosted `xp-evidence` collector",
)

REQUIRED_TURKISH_DOC_SNIPPETS = (
    "![published preview](https://img.shields.io/badge/published%20preview-v1.0.24-orange)",
    "![candidate](https://img.shields.io/badge/candidate-v1.0.27-yellow)",
    "configs/platform_verified_evidence.json",
    "python scripts/check_protected_platform_goal.py --release-tag <tag> --require-records-complete --show-requirements",
    "python scripts/check_platform_verified_evidence.py --require-goal-targets --require-review-bundles --release-tag <tag>",
    "python scripts/import_platform_evidence_artifacts.py --release-tag <tag> --require-goal-targets --out-dir release-assets --verify-source-run --repository <owner>/<repo>",
    "python scripts/check_platform_review_bundle_artifacts.py --bundle-dir release-assets --require-goal-targets --release-tag <tag> --require-final-record-assets",
    "python scripts/check_platform_release_evidence_remote.py --repository <owner>/<repo> --release-tag <tag> --require-goal-targets --require-source-runs --require-source-artifact-bytes --require-final-record-bytes --require-release-asset-bytes --require-tag-source-head",
    "indirilen source artifact native",
    "published asset digest/size/byte",
    "published final accepted-record JSON bytes",
    "release tag Git object/source head SHA",
    "`GH_TOKEN` veya `GITHUB_TOKEN`",
    "`contents:read` ve `actions:read`",
    "workflow_run.repository_id",
    "workflow_run.head_repository_id",
    "artifact created_at",
    "source artifact ZIP",
    "source run creation/start/update",
    "ayni tag/repository/workflow file path/source-head/run-attempt",
    "target'a ozel release source workflow file path",
    "release_asset_provenance_complete=false",
    "asset-backed protected goal",
    "python scripts/check_release_publish_assets.py --assets-dir release-assets --tag <tag> --repository <owner>/<repo> --require-platform-goal-targets",
    "Linux i386, Linux armhf, windows-xp-native-x86 ve windows-xp-native-x64",
    "ayni GitHub release repository, target'a ozel release source workflow file path",
    "ayni release source head SHA",
    "pozitif release source run attempt",
    "linux_smoke_summary",
    "Windows XP native-host readiness 25.0%",
    "self-hosted `xp-evidence` collector",
    "`scripts/xp_smoke_runner.cmd`",
)

REQUIRED_README_RELEASE_SECTION_SNIPPETS = (
    "docs/PRODUCTION_READINESS.md",
    "python scripts/verify.py --quick --no-cli-smoke --release-tag <tag>",
    "python scripts/check_protected_platform_goal.py --release-tag <tag> --require-records-complete --show-requirements",
    "python scripts/check_platform_verified_evidence.py --require-goal-targets --require-review-bundles --release-tag <tag>",
    "accepted-platform-evidence-assets",
    "python scripts/import_platform_evidence_artifacts.py --release-tag <tag> --require-goal-targets --out-dir release-assets --verify-source-run --repository <owner>/<repo>",
    "python scripts/check_platform_review_bundle_artifacts.py --bundle-dir release-assets --require-goal-targets --release-tag <tag> --require-final-record-assets",
    "python scripts/check_platform_release_evidence_remote.py --repository <owner>/<repo> --release-tag <tag> --require-goal-targets --require-source-runs --require-source-artifact-bytes --require-final-record-bytes --require-release-asset-bytes --require-tag-source-head",
    "downloaded source artifact native artifact SHA-256 values",
    "published asset digests, sizes and bytes",
    "published final accepted-record JSON bytes",
    "release tag Git object/source head SHA",
    "GH_TOKEN` or `GITHUB_TOKEN",
    "`contents:read`\nand `actions:read`",
    "workflow_run.repository_id",
    "workflow_run.head_repository_id",
    "artifact created_at",
    "source artifact ZIP",
    "source run creation/start/update window",
    "workflow-file, source-head and",
    "run-attempt-bound accepted evidence artifacts",
    "Linux i386, Linux armhf, windows-xp-native-x86",
    "windows-xp-native-x64 require finalized accepted evidence records",
    "same release tag, GitHub release repository",
    "target-specific release source workflow file",
    "release source head SHA and per-record release source run attempt before any 100%",
    "release_asset_provenance_complete=false",
    "asset-backed protected goal gate",
    "python scripts/check_release_publish_assets.py --assets-dir release-assets --tag <tag> --repository <owner>/<repo> --require-platform-goal-targets",
    "configs/platform_verified_evidence.json",
    "accepted review-bundle hashes",
    "The exact-tag publish job waits for",
    "same draft-first",
    "`linux_smoke_summary`",
    "`scripts/xp_smoke_runner.cmd`",
    "`xp-evidence` collector",
)

REQUIRED_RELEASE_STRATEGY_SNIPPETS = (
    "python scripts/check_platform_evidence_source_ref.py --repository <owner>/<repo> --release-tag <tag> --require-goal-targets",
    "python scripts/import_platform_evidence_artifacts.py --release-tag <tag> --require-goal-targets --out-dir <release-assets-dir> --dry-run --verify-source-run --repository <owner>/<repo>",
    "pre-release protected-platform import dry-run",
    "does not stage files for upload",
    "release_asset_provenance_complete=false",
    "record_complete",
    "release_backed_complete",
    "asset-backed protected goal gate",
    "refuses release tags that do not contain the tagged project version",
)

STALE_TURKISH_RELEASE_SNIPPETS = (
    "release-v1.0.1",
    "v1.0.1",
    "remote-ops-workspace-v1.0.1-SHA256SUMS.txt",
)

STALE_DEFAULT_ARTIFACT_SNIPPETS = (
    "remote-ops-workspace-v1.0.27-linux-<i386|amd64|armhf|arm64>.deb",
    "remote-ops-workspace-v1.0.27-linux-<i686|x86_64|armv7hl|aarch64>.rpm",
    "remote-ops-workspace-v1.0.27-linux-<i686|x86_64|armhf|aarch64>.AppImage",
    "remote-ops-workspace-v1.0.27-linux-<i686|x86_64|armhf|aarch64>-native.tar.gz",
    "remote-ops-workspace-v1.0.27-macos-<arch>.dmg",
    "remote-ops-workspace-v1.0.27-macos-<arch>.pkg",
)

STALE_PLATFORM_EVIDENCE_SNIPPETS = (
    "`--allow-unfinalized-candidates` flag is only for local candidate checks before append",
    "source-head-bound accepted evidence artifacts",
    "source-head-bound accepted Linux i386, Linux armhf and Windows XP native-host artifacts",
)


def main() -> int:
    errors: list[str] = []
    errors.extend(check_repository_identity())
    errors.extend(check_workflow_matrix())
    errors.extend(check_release_preflight())
    errors.extend(check_release_docs())
    if errors:
        for error in errors:
            print(f"release truth: {error}", file=sys.stderr)
        return 1
    print("release identity and artifact truth passed")
    return 0


def check_repository_identity() -> list[str]:
    errors: list[str] = []
    pyproject = read("pyproject.toml")
    for key, expected in {
        "Homepage": REPOSITORY_URL,
        "Documentation": f"{REPOSITORY_URL}/tree/main/docs",
        "Issues": f"{REPOSITORY_URL}/issues",
    }.items():
        if f'{key} = "{expected}"' not in pyproject:
            errors.append(f"pyproject.toml {key} must be {expected}")

    for relative in (
        "README.md",
        "README.tr.md",
        "docs/runbooks/QUICKSTART_LINUX.md",
        "docs/runbooks/QUICKSTART_WINDOWS_SERVER.md",
    ):
        text = read(relative)
        if REPOSITORY_CLONE_URL not in text:
            errors.append(f"{relative} must use clone URL {REPOSITORY_CLONE_URL}")
        if "YOUR-ORG" in text:
            errors.append(f"{relative} still contains YOUR-ORG placeholder")

    return errors


def check_workflow_matrix() -> list[str]:
    errors: list[str] = []
    workflow = read(".github/workflows/release.yml")
    for job, expected_arches in WORKFLOW_ARCHES.items():
        block = workflow_job_block(workflow, job)
        if not block:
            errors.append(f"release workflow missing job: {job}")
            continue
        found = set(re.findall(r"(?m)^\s+- arch:\s*([A-Za-z0-9_]+)\s*$", block))
        if found != expected_arches:
            errors.append(f"{job} arch matrix {sorted(found)} must equal {sorted(expected_arches)}")
    return errors


def check_release_preflight(workflow: str | None = None) -> list[str]:
    build = strip_unquoted_comments(
        workflow if workflow is not None else read(".github/workflows/release.yml")
    )
    promotion = strip_unquoted_comments(read(".github/workflows/release-promotion.yml"))
    certification = strip_unquoted_comments(read(".github/workflows/release-certification.yml"))
    errors: list[str] = []
    if "workflow_dispatch:" in build:
        errors.append("candidate release build must be tag-push-only")
    for snippet, label in {
        '      - "v*"': "v* tag trigger",
        "group: release-candidate-${{ github.repository }}-${{ github.ref_name }}": (
            "repository/tag candidate concurrency"
        ),
        "cancel-in-progress: false": "non-cancelling candidate concurrency",
        "RELEASE_TAG: ${{ github.ref_name }}": "tag-push release tag binding",
    }.items():
        if snippet not in build:
            errors.append(f"candidate build workflow missing {label}: {snippet}")
    if "softprops/action-gh-release" in build or re.search(
        r"(?m)^\s*gh\s+api\s+--method\s+(?:POST|PATCH|DELETE)\b.*releases", build
    ):
        errors.append("candidate build workflow must not create or mutate a GitHub Release")
    preflight = workflow_job_block(build, "release-preflight")
    if not preflight:
        return [*errors, "candidate build workflow missing release-preflight job"]
    errors.extend(check_checkout_step(preflight, job="release-preflight"))
    for snippet, label in {
        "timeout-minutes: 100": "bounded preflight timeout",
        "release_sha: ${{ steps.release-source.outputs.sha }}": "frozen source SHA output",
        "candidate_build_ready: ${{ steps.signing-readiness.outputs.candidate_build_ready }}": (
            "candidate readiness output"
        ),
        'python-version: "3.14.7"': "exact release Python",
        'test "$GITHUB_EVENT_NAME" = "push"': "push-only event guard",
        'test "$GITHUB_REF_TYPE" = "tag"': "tag type guard",
        'test "$GITHUB_REF" = "refs/tags/$RELEASE_TAG"': "exact tag ref guard",
        'test "$GITHUB_RUN_ATTEMPT" = "1"': "rerun refusal",
        'tag_sha="$(git rev-parse "${RELEASE_TAG}^{commit}")"': "peeled tag resolution",
        'test "$tag_sha" = "$release_sha"': "tag/source equality",
        RELEASE_VERSION_GATE_COMMAND: "release version gate",
        'python scripts/check_release_maturity.py --release-tag "$RELEASE_TAG"': (
            "production maturity gate"
        ),
        RELEASE_VERIFY_COMMAND: "quick verifier",
        PYTHON315_CI_EVIDENCE_COMMAND: "source-SHA CI evidence",
        "candidate_build_ready=$signed_native_ready": "signed candidate readiness",
        "python scripts/check_repository_cleanup.py --require-clean": "clean checkout gate",
        "unsigned-preview.yml": "separate unsigned preview boundary",
    }.items():
        if snippet not in preflight:
            errors.append(f"release-preflight missing {label}: {snippet}")
    maturity_index = preflight.find("check_release_maturity.py")
    verify_index = preflight.find("scripts/verify.py")
    if min(maturity_index, verify_index) < 0 or maturity_index > verify_index:
        errors.append("release maturity gate must run before the repository verifier")
    for job in (
        "source-and-python",
        "windows-native",
        "macos-native",
        "linux-native",
        "seal-release-candidate",
    ):
        block = workflow_job_block(build, job)
        if not block:
            errors.append(f"candidate build workflow missing {job} job")
            continue
        if not job_depends_on(block, "release-preflight"):
            errors.append(f"{job} must depend on release-preflight")
        errors.extend(check_checkout_step(block, job=job))
        if job != "seal-release-candidate":
            if "needs.release-preflight.outputs.candidate_build_ready == 'true'" not in block:
                errors.append(f"{job} must be gated on signed candidate readiness")
            if FROZEN_RELEASE_REF not in block:
                errors.append(f"{job} checkout must use the frozen release SHA")
            if 'test "$(git rev-parse HEAD)" = "$EXPECTED_RELEASE_SHA"' not in block:
                errors.append(f"{job} must verify the frozen release SHA")
    seal = workflow_job_block(build, "seal-release-candidate")
    for token, label, kind, step_name in (
        (
            "release_candidate_inventory.py stage",
            "candidate inventory seal",
            "run",
            "Materialize exact staged artifacts and seal candidate inventory",
        ),
        (
            "actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6",
            "candidate attestation",
            "uses",
            "Attest exact candidate inventory",
        ),
        (
            "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
            "candidate inventory upload",
            "uses",
            "Upload immutable candidate inventory",
        ),
    ):
        errors.extend(
            require_active_step(
                seal,
                token,
                label=label,
                kind=kind,
                step_name=step_name,
            )
        )
    errors.extend(check_promotion_truth(promotion))
    errors.extend(check_certification_truth(certification))
    errors.extend(check_untrusted_run_interpolation(build, label="candidate build"))
    errors.extend(check_untrusted_run_interpolation(promotion, label="promotion"))
    errors.extend(check_untrusted_run_interpolation(certification, label="certification"))
    return errors


def check_promotion_truth(workflow: str) -> list[str]:
    errors: list[str] = []
    block = workflow_job_block(workflow, "promote-production-release")
    if not block:
        return ["promotion workflow missing promote-production-release job"]
    required = {
        "workflow_dispatch:": "dispatch trigger",
        "build_run_id:": "build run ID input",
        "build_run_attempt:": "build attempt input",
        "candidate_inventory_artifact_id:": "candidate inventory artifact ID input",
        "candidate_inventory_archive_digest:": "candidate archive digest input",
        "evidence_commit_sha:": "exact evidence commit input",
        'test "$GITHUB_REF" = "refs/tags/$RELEASE_TAG"': "exact tag dispatch",
        'test "$GITHUB_RUN_ATTEMPT" = "1"': "promotion rerun refusal",
        "ref: ${{ inputs.evidence_commit_sha }}": "exact evidence checkout",
        "release-compliance-evidence": "evidence branch ancestry proof",
        "release_candidate_inventory.py promote": "numeric artifact-ID promotion",
        "Verify attestation and download exact candidate artifact IDs": "build-run attestation binding",
        "--require-hashes --requirement requirements-locks/release-verifier-linux-x86_64.txt": (
            "hashed compliance verifier"
        ),
        "--candidate-inventory": "signed candidate inventory binding",
        "check_release_remote_preconditions.py immutable": "pre-mutation immutable-release API",
        "ROW_RELEASE_IMMUTABILITY_TOKEN": "Administration(read) immutable-setting token",
        "check_release_remote_preconditions.py namespace": "draft-inclusive namespace scan",
        "gh api --method POST": "create-only draft",
        "steps.create-draft.outputs.release-id": "numeric draft identity",
        "gh api --method PATCH": "numeric publication",
        "target_commitish: $sha": "exact-SHA defensive draft target",
        "--tag-governance-attestation": "signed out-of-band tag governance proof",
        "--tag-governance-signature": "independent tag governance signature",
        "check_release_tag_governance.py": "just-in-time signed tag governance revalidation",
        "Re-resolve immutable tag after publication": "post-publication tag race check",
        "Require same numeric release becomes immutable": "same-ID immutable poll",
        "--current-transaction-run-id": "in-progress final transaction proof",
        "steps.publish-draft.outcome != 'success'": "failed-draft cleanup guard",
        ".draft == true": "exact still-draft cleanup proof",
        'gh api --method DELETE "repos/$GITHUB_REPOSITORY/releases/$RELEASE_ID"': (
            "numeric failed-draft cleanup"
        ),
        "remote-ops-release-transaction:": "failed-draft transaction marker",
    }
    for snippet, label in required.items():
        if snippet not in workflow:
            errors.append(f"promotion workflow missing {label}: {snippet}")
    command_contracts = {
        "Verify attestation and download exact candidate artifact IDs": (
            (
                '--repository "$GITHUB_REPOSITORY"',
                '--release-tag "$RELEASE_TAG"',
                '--release-sha "$RELEASE_SHA"',
                '--build-run-id "$INPUT_BUILD_RUN_ID"',
                '--build-run-attempt "$INPUT_BUILD_RUN_ATTEMPT"',
                '--inventory-artifact-id "$INPUT_INVENTORY_ARTIFACT_ID"',
                '--inventory-archive-digest "$INPUT_INVENTORY_ARCHIVE_DIGEST"',
                '--approved-inventory "release-compliance-input/releases/$RELEASE_TAG/$RELEASE_SHA/bundle/release-candidate-inventory.json"',
                "--assets-root release-assets",
            ),
            ("--help", "--dry-run"),
            frozenset(
                {
                    "--repository",
                    "--release-tag",
                    "--release-sha",
                    "--build-run-id",
                    "--build-run-attempt",
                    "--inventory-artifact-id",
                    "--inventory-archive-digest",
                    "--approved-inventory",
                    "--assets-root",
                }
            ),
        ),
        "Validate complete production asset inventory": (
            (
                "--assets-dir release-assets",
                "--evidence-registry",
                "--require-platform-goal-targets",
                "--native-release-channel production-signed",
            ),
            ("--source-assets-only", "unsigned-preview"),
            frozenset(
                {
                    "--assets-dir",
                    "--tag",
                    "--repository",
                    "--evidence-registry",
                    "--require-platform-goal-targets",
                    "--native-release-channel",
                }
            ),
        ),
        "Audit signed exact-byte redistribution and resolver evidence": (
            (
                "--assets-dir release-assets",
                "--policy ",
                "--evidence ",
                "--signature ",
                "--evidence-root ",
                "--candidate-inventory ",
                "--protected-platform-registry ",
                "--tag-governance-attestation ",
                "--tag-governance-signature ",
            ),
            ("--check-policy-only",),
            frozenset(
                {
                    "--policy",
                    "--policy-root",
                    "--assets-dir",
                    "--tag",
                    "--repository",
                    "--sha",
                    "--evidence",
                    "--signature",
                    "--evidence-root",
                    "--candidate-inventory",
                    "--protected-platform-registry",
                    "--tag-governance-attestation",
                    "--tag-governance-signature",
                }
            ),
        ),
        "Require immutable releases enabled before any mutation": (
            (
                "--repository \"$GITHUB_REPOSITORY\"",
                "--tag \"$RELEASE_TAG\"",
            ),
            (),
            frozenset({"--repository", "--tag"}),
        ),
        "Revalidate signed tag governance at mutation boundary": (
            (
                "--policy configs/release_compliance_policy.json",
                '--attestation "release-compliance-input/releases/$RELEASE_TAG/$RELEASE_SHA/tag-governance-attestation.json"',
                '--signature "release-compliance-input/releases/$RELEASE_TAG/$RELEASE_SHA/tag-governance-attestation.sig.json"',
                '--repository "$GITHUB_REPOSITORY"',
                '--tag "$RELEASE_TAG"',
                '--sha "$RELEASE_SHA"',
            ),
            ("--help", "--dry-run", "--check-policy-only"),
            frozenset(
                {"--policy", "--attestation", "--signature", "--repository", "--tag", "--sha"}
            ),
        ),
        "Require unused release namespace including drafts": (
            (
                "--repository \"$GITHUB_REPOSITORY\"",
                "--tag \"$RELEASE_TAG\"",
            ),
            (),
            frozenset({"--repository", "--tag"}),
        ),
    }
    for token, label, kind, step_name in (
        (
            "check_release_maturity.py",
            "maturity gate",
            "run",
            "Re-run immutable source release gates",
        ),
        (
            "release_candidate_inventory.py promote",
            "candidate verifier/downloader",
            "run",
            "Verify attestation and download exact candidate artifact IDs",
        ),
        (
            "check_release_publish_assets.py",
            "complete production asset inventory",
            "run",
            "Validate complete production asset inventory",
        ),
        (
            "check_release_license_compliance.py",
            "exact compliance audit",
            "run",
            "Audit signed exact-byte redistribution and resolver evidence",
        ),
        (
            "actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6",
            "asset attestation",
            "uses",
            "Attest every certified release asset",
        ),
        (
            "check_release_tag_governance.py",
            "mutation-bound tag governance proof",
            "run",
            "Revalidate signed tag governance at mutation boundary",
        ),
        (
            "check_release_remote_preconditions.py immutable",
            "immutable release setting proof",
            "run",
            "Require immutable releases enabled before any mutation",
        ),
        (
            "check_release_remote_preconditions.py namespace",
            "draft-inclusive namespace proof",
            "run",
            "Require unused release namespace including drafts",
        ),
        (
            "gh api --method POST",
            "draft creation",
            "run",
            "Create new draft by numeric API identity",
        ),
        (
            "--draft-release-id",
            "draft provenance",
            "run",
            "Verify complete numeric-ID draft transaction",
        ),
        (
            "gh api --method PATCH",
            "numeric publish",
            "run",
            "Publish verified draft by numeric ID once",
        ),
        (
            "--current-transaction-run-id",
            "final in-run provenance",
            "run",
            "Verify final immutable release and complete exact-tag provenance",
        ),
    ):
        required_tokens, forbidden_tokens, allowed_flags = command_contracts.get(
            step_name,
            ((), (), None),
        )
        errors.extend(
            require_active_step(
                block,
                token,
                label=label,
                kind=kind,
                step_name=step_name,
                required_tokens=required_tokens,
                forbidden_tokens=forbidden_tokens,
                allowed_flags=allowed_flags,
            )
        )
    if "environment: release-compliance-review" not in block:
        errors.append("promotion must use the protected release-compliance-review environment")
    return errors


def check_certification_truth(workflow: str) -> list[str]:
    errors: list[str] = []
    block = workflow_job_block(workflow, "certify-completed-promotion")
    if not block:
        return ["release certification workflow missing completed-promotion job"]
    for snippet, label in {
        "workflow_run:": "post-completion trigger",
        "- release-promotion": "promotion workflow selection",
        "github.event.workflow_run.conclusion == 'success'": "successful-run condition",
        'test "$PROMOTION_STATUS" = "completed"': "completed status proof",
        "--published-release-id": "numeric immutable release proof",
        "check_release_provenance.py": "completed-success provenance audit",
    }.items():
        if snippet not in workflow:
            errors.append(f"release certification workflow missing {label}: {snippet}")
    return errors

def check_tag_targeted_release_dispatch(workflow: str) -> list[str]:
    errors: list[str] = []
    if "workflow_dispatch:" not in workflow:
        errors.append("release workflow must retain workflow_dispatch for protected evidence promotion")
    push_block = re.search(r"(?ms)^  push:\n(.*?)(?=^  [A-Za-z_][A-Za-z0-9_-]*:|^\S|\Z)", workflow)
    if not push_block or not re.search(r'(?m)^      - "v\*"\s*$', push_block.group(1)):
        errors.append("release workflow must publish standard assets automatically for v* tag pushes")
    if RELEASE_TAG_RESOLVER not in workflow:
        errors.append("release workflow must resolve release tags from dispatch input or pushed tag name")
    input_block = re.search(r"(?ms)^  workflow_dispatch:\n(.*?)(?=^\S|\Z)", workflow)
    if not input_block or not re.search(
        r"(?ms)^      release_tag:\n.*?^        required:\s*true\s*$.*?^        type:\s*string\s*$",
        input_block.group(1),
    ):
        errors.append("release workflow must retain a string workflow_dispatch release_tag input for protected promotion")
    return errors


def check_tagged_source_checkout(job_block: str, *, job: str) -> list[str]:
    if not re.search(r"(?m)^      - uses: actions/checkout@[0-9a-f]{40}(?:\s+#.*)?$", job_block):
        return [f"{job} missing repository checkout pinned to a 40-character commit SHA"]
    checkout = workflow_step_block(job_block, "uses: actions/checkout@")
    if not checkout:
        return [f"{job} missing repository checkout: uses: actions/checkout@<pinned-sha>"]
    expected_ref = TAGGED_RELEASE_REF if job == RELEASE_PREFLIGHT_JOB else FROZEN_RELEASE_REF
    if expected_ref not in checkout:
        if job == RELEASE_PREFLIGHT_JOB:
            return [f"{job} checkout must resolve the immutable env.RELEASE_TAG source"]
        return [f"{job} checkout must use the frozen release-preflight release_sha"]
    return []


def check_accepted_platform_evidence_assets_job(workflow: str) -> list[str]:
    block = workflow_job_block(workflow, "accepted-platform-evidence-assets")
    if not block:
        return ["release workflow missing accepted-platform-evidence-assets job"]
    errors: list[str] = []
    required_snippets = {
        CERTIFIED_EVIDENCE_IMPORT_CONDITION: (
            "mandatory tag-push or opt-in staging evidence import condition"
        ),
        "timeout-minutes: 20": "bounded platform evidence import timeout",
        "actions: read": "Actions read permission for artifact import",
        "contents: read": "contents read permission for checkout",
        "GH_TOKEN: ${{ github.token }}": "GitHub token for gh run download",
        "name: Check out immutable release source for evidence binding": (
            "immutable release source checkout"
        ),
        FROZEN_RELEASE_REF: "frozen release source checkout ref",
        "path: release-source": "immutable release source checkout path",
        (
            'python scripts/check_platform_evidence_source_ref.py '
            '--repository "${{ github.repository }}" '
            '--release-tag "$RELEASE_TAG" --require-goal-targets'
        ): "protected platform release source-ref gate",
        "GITHUB_TOKEN: ${{ github.token }}": "GitHub token for release source-ref gate",
        (
            'python scripts/check_protected_platform_goal.py --release-tag "$RELEASE_TAG" '
            "--require-records-complete --show-requirements"
        ): "protected platform accepted records gate",
        'python scripts/check_platform_verified_evidence.py --require-goal-targets --require-review-bundles --release-tag "$RELEASE_TAG"': (
            "strict accepted evidence registry gate"
        ),
        (
            'python scripts/import_platform_evidence_artifacts.py --release-tag "$RELEASE_TAG" '
            '--release-head-sha "$(git -C release-source rev-parse HEAD)" '
            '--require-goal-targets --out-dir release-assets --verify-source-run --repository "${{ github.repository }}"'
        ): "accepted platform evidence artifact importer",
        (
            'python scripts/check_platform_review_bundle_artifacts.py --bundle-dir release-assets '
            '--require-goal-targets --release-tag "$RELEASE_TAG" --require-final-record-assets'
        ): "imported platform review bundle and final record validator",
        "name: release-platform-evidence-assets": "platform evidence release asset artifact name",
        "path: release-assets/*": "platform evidence release asset upload path",
        "if-no-files-found: error": "platform evidence upload must fail when empty",
        "include-hidden-files: false": "platform evidence upload hidden file exclusion",
        "retention-days: 90": "platform evidence upload retention window",
    }
    for snippet, label in required_snippets.items():
        if snippet not in block:
            errors.append(f"accepted-platform-evidence-assets missing {label}: {snippet}")
    if "--dry-run" in block:
        errors.append("accepted-platform-evidence-assets must download accepted artifacts, not run importer with --dry-run")
    if re.search(r"(?m)^\s+[A-Za-z0-9_-]+:\s+write\s*$", block):
        errors.append("accepted-platform-evidence-assets must not request write permissions")
    return errors


def check_publish_platform_evidence_dependency(workflow: str) -> list[str]:
    block = workflow_job_block(workflow, PROTECTED_PUBLISH_JOB)
    if not block:
        return [f"release workflow missing {PROTECTED_PUBLISH_JOB} job"]
    errors: list[str] = []
    if PROTECTED_PROMOTION_CONDITION not in block:
        errors.append(f"{PROTECTED_PUBLISH_JOB} missing opt-in protected promotion condition")
    if not job_depends_on(block, "publish"):
        errors.append(f"{PROTECTED_PUBLISH_JOB} must depend on publish")
    if not job_depends_on(block, "accepted-platform-evidence-assets"):
        errors.append(f"{PROTECTED_PUBLISH_JOB} must depend on accepted-platform-evidence-assets")
    remote_audit_step = workflow_step_block(block, "name: Audit published protected platform evidence")
    protected_asset_gate_index = block.find(PUBLISH_PROTECTED_PLATFORM_ASSET_COMMAND)
    gate_index = block.find(PUBLISH_PLATFORM_GOAL_COMMAND)
    upload_index = block.find("softprops/action-gh-release")
    remote_audit_index = block.find(remote_audit_step) if remote_audit_step else -1
    if protected_asset_gate_index < 0:
        errors.append(
            f"{PROTECTED_PUBLISH_JOB} missing protected platform release asset gate: "
            f"{PUBLISH_PROTECTED_PLATFORM_ASSET_COMMAND}"
        )
    if gate_index < 0:
        errors.append(f"{PROTECTED_PUBLISH_JOB} missing publish-time protected platform goal gate: {PUBLISH_PLATFORM_GOAL_COMMAND}")
    if upload_index < 0:
        errors.append(f"{PROTECTED_PUBLISH_JOB} missing GitHub release upload step: uses: softprops/action-gh-release@<pinned-sha>")
    if not remote_audit_step or PUBLISH_REMOTE_PLATFORM_EVIDENCE_AUDIT_COMMAND not in remote_audit_step:
        errors.append(
            f"{PROTECTED_PUBLISH_JOB} missing published protected platform evidence audit: "
            f"{PUBLISH_REMOTE_PLATFORM_EVIDENCE_AUDIT_COMMAND}"
        )
    if not job_permission_is(block, "actions", "read"):
        errors.append(f"{PROTECTED_PUBLISH_JOB} missing Actions read permission for published protected platform evidence audit")
    if not job_permission_is(block, "contents", "write"):
        errors.append(f"{PROTECTED_PUBLISH_JOB} missing contents write permission for GitHub release upload")
    if not remote_audit_step or "GH_TOKEN: ${{ github.token }}" not in remote_audit_step:
        errors.append(f"{PROTECTED_PUBLISH_JOB} missing GitHub token for published protected platform evidence audit")
    if (
        protected_asset_gate_index >= 0
        and gate_index >= 0
        and protected_asset_gate_index > gate_index
    ):
        errors.append("protected platform release asset gate must run before protected publish asset validation")
    if protected_asset_gate_index >= 0 and upload_index >= 0 and protected_asset_gate_index > upload_index:
        errors.append("protected platform release asset gate must run before protected GitHub release upload")
    if gate_index >= 0 and upload_index >= 0 and gate_index > upload_index:
        errors.append("protected publish-time platform goal gate must run before GitHub release upload")
    if remote_audit_index >= 0 and upload_index >= 0 and remote_audit_index < upload_index:
        errors.append("published protected platform evidence audit must run after GitHub release upload")
    return errors


def check_explicit_release_upload_tags(workflow: str) -> list[str]:
    errors: list[str] = []
    upload_steps = {"publish": "name: Upload release assets"}
    for job, marker in upload_steps.items():
        block = workflow_job_block(workflow, job)
        if not block:
            continue
        upload = workflow_step_block(block, marker)
        if (
            upload
            and "uses: softprops/action-gh-release@" in upload
            and RELEASE_UPLOAD_TAG_NAME not in upload
        ):
            errors.append(
                f"{job} GitHub release upload must explicitly target env.RELEASE_TAG"
            )
        if upload and "uses: softprops/action-gh-release@" in upload:
            if "overwrite_files: false" not in upload:
                errors.append(f"{job} GitHub release upload must disable asset overwrites")
            if job == "publish" and "prerelease: false" not in upload:
                errors.append("publish GitHub release upload must be production-only")
            if job == "publish" and "draft: true" not in upload:
                errors.append("publish GitHub release upload must create a draft transaction")
    return errors


def check_certified_release_transaction(workflow: str) -> list[str]:
    """Enforce one exact-tag, draft-first upload of the complete certified inventory."""
    errors: list[str] = []
    if workflow_job_block(workflow, PROTECTED_PUBLISH_JOB):
        errors.append(
            "release workflow must not mutate production releases from a manual supplemental job"
        )
    block = workflow_job_block(workflow, "publish")
    if not block:
        return [*errors, "release workflow missing publish job"]
    if not job_depends_on(block, "accepted-platform-evidence-assets"):
        errors.append("publish must depend on accepted-platform-evidence-assets")
    required = {
        "name: Audit exact native redistribution evidence": "exact-artifact compliance audit",
        "environment: release-compliance-review": "post-build independent review hold",
        "name: Fetch independently signed exact-byte compliance evidence": (
            "external exact-byte evidence checkout"
        ),
        "ref: release-compliance-evidence": "separate compliance evidence branch",
        '--evidence "release-compliance-input/releases/$RELEASE_TAG/${{ needs.release-preflight.outputs.release_sha }}/release-evidence.json"': (
            "signed compliance evidence input"
        ),
        '--signature "release-compliance-input/releases/$RELEASE_TAG/${{ needs.release-preflight.outputs.release_sha }}/release-evidence.sig.json"': (
            "compliance signature input"
        ),
        '--evidence-root "release-compliance-input/releases/$RELEASE_TAG/${{ needs.release-preflight.outputs.release_sha }}/bundle"': (
            "compliance evidence bundle root"
        ),
        "name: Verify complete draft release transaction": "draft byte/provenance audit",
        '--draft-release-id "${{ steps.draft-release.outputs.id }}"': (
            "numeric draft release identity binding"
        ),
        '--draft-transaction-run-id "$GITHUB_RUN_ID"': "current-run draft provenance binding",
        '--draft-transaction-run-attempt "$GITHUB_RUN_ATTEMPT"': (
            "current-attempt draft provenance binding"
        ),
        "name: Publish verified immutable release once": "single draft promotion step",
        'gh api --method PATCH "repos/${{ github.repository }}/releases/$DRAFT_RELEASE_ID"': (
            "numeric-ID draft promotion command"
        ),
        "DRAFT_RELEASE_ID: ${{ steps.draft-release.outputs.id }}": (
            "captured draft release ID"
        ),
        "--field draft=false": "draft-to-published state transition",
        "refs/tags/row-release-final-candidate^{commit}": "final pre-promotion tag recheck",
    }
    for snippet, label in required.items():
        if snippet not in block:
            errors.append(f"publish missing {label}: {snippet}")
    compliance_index = block.find("check_release_license_compliance.py")
    attest_index = block.find("actions/attest@")
    upload_index = block.find("softprops/action-gh-release@")
    verify_index = block.find("--draft-transaction-run-id")
    final_tag_index = block.find("refs/tags/row-release-final-candidate^{commit}")
    promote_index = block.find("--field draft=false")
    ordered = (compliance_index, attest_index, upload_index, verify_index, final_tag_index, promote_index)
    if any(index < 0 for index in ordered) or list(ordered) != sorted(ordered):
        errors.append(
            "publish must audit, attest, draft-upload, verify, recheck the tag, and promote in order"
        )
    if workflow.count("softprops/action-gh-release@") != 1:
        errors.append("release workflow must have exactly one production asset upload action")
    if block.count("gh api --method PATCH") != 1:
        errors.append("publish must perform exactly one numeric-ID API patch for draft promotion")
    return errors


def strip_unquoted_comments(text: str) -> str:
    active: list[str] = []
    for line in text.splitlines():
        quote: str | None = None
        escaped = False
        kept: list[str] = []
        for char in line:
            if escaped:
                kept.append(char)
                escaped = False
                continue
            if char == "\\" and quote != "'":
                kept.append(char)
                escaped = True
                continue
            if char in {"'", '"'}:
                quote = char if quote is None else (None if quote == char else quote)
                kept.append(char)
                continue
            if char == "#" and quote is None:
                break
            kept.append(char)
        active.append("".join(kept).rstrip())
    return "\n".join(active)


def check_release_docs() -> list[str]:
    errors: list[str] = []
    readme = normalize_markdown_pipes(read("README.md"))
    release_strategy = normalize_markdown_pipes(read("docs/RELEASE_STRATEGY.md"))
    docs = "\n".join(
        normalize_markdown_pipes(read(path))
        for path in (
            "docs/PLATFORM_SUPPORT.md",
            "docs/RELEASE_STRATEGY.md",
        )
    )
    docs = "\n".join((readme, docs))
    turkish_readme = normalize_markdown_pipes(read("README.tr.md"))
    readme_release_section = bounded_section(readme, "The release workflow starts", "Release phases:")
    for snippet in REQUIRED_DOC_SNIPPETS:
        if not contains_snippet(docs, snippet):
            errors.append(f"release docs missing workflow artifact truth snippet: {snippet}")
    if not readme_release_section:
        errors.append("README.md missing release workflow truth section")
    else:
        for snippet in REQUIRED_README_RELEASE_SECTION_SNIPPETS:
            if not contains_snippet(readme_release_section, snippet):
                errors.append(f"README.md release section missing protected platform evidence truth snippet: {snippet}")
    for snippet in REQUIRED_RELEASE_STRATEGY_SNIPPETS:
        if not contains_snippet(release_strategy, snippet):
            errors.append(f"docs/RELEASE_STRATEGY.md missing pre-release platform import truth snippet: {snippet}")
    for snippet in REQUIRED_TURKISH_DOC_SNIPPETS:
        if not contains_snippet(turkish_readme, snippet):
            errors.append(f"README.tr.md missing protected platform evidence truth snippet: {snippet}")
    for snippet in STALE_TURKISH_RELEASE_SNIPPETS:
        if contains_exact_release_version_snippet(turkish_readme, snippet):
            errors.append(f"README.tr.md still contains stale release truth snippet: {snippet}")
    for snippet in STALE_DEFAULT_ARTIFACT_SNIPPETS:
        if snippet in docs:
            errors.append(f"release docs still advertise stale default artifact pattern: {snippet}")
    for snippet in STALE_PLATFORM_EVIDENCE_SNIPPETS:
        if contains_snippet(docs, snippet):
            errors.append(f"release docs still advertise stale platform evidence workflow guidance: {snippet}")
    return errors


def workflow_job_block(workflow: str, job: str) -> str:
    match = re.search(rf"(?ms)^  {re.escape(job)}:\n(.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)", workflow)
    return match.group(1) if match else ""


def check_checkout_step(job_block: str, *, job: str) -> list[str]:
    if not re.search(r"(?m)^      - uses: actions/checkout@[0-9a-f]{40}(?:\s+#.*)?$", job_block):
        return [f"{job} missing repository checkout pinned to a 40-character commit SHA"]
    checkout = workflow_step_block(job_block, "uses: actions/checkout@")
    if not checkout:
        return [f"{job} missing repository checkout: uses: actions/checkout@<pinned-sha>"]
    errors: list[str] = []
    if "persist-credentials: false" not in checkout:
        errors.append(f"{job} checkout step missing credential isolation: persist-credentials: false")
    if "clean: true" not in checkout:
        errors.append(f"{job} checkout step missing workspace cleanup: clean: true")
    return errors


def workflow_step_block(job_block: str, marker: str) -> str:
    pattern = rf"(?ms)^      - {re.escape(marker)}[^\n]*\n(.*?)(?=^      - |\Z)"
    match = re.search(pattern, job_block)
    return match.group(0) if match else ""


def workflow_step_blocks(job_block: str) -> list[str]:
    starts = [match.start() for match in re.finditer(r"(?m)^      - (?:name|uses|run):", job_block)]
    return [
        job_block[start : starts[index + 1] if index + 1 < len(starts) else len(job_block)]
        for index, start in enumerate(starts)
    ]


def require_active_step(
    job_block: str,
    token: str,
    *,
    label: str,
    kind: str,
    step_name: str | None = None,
    required_tokens: tuple[str, ...] = (),
    forbidden_tokens: tuple[str, ...] = (),
    allowed_flags: frozenset[str] | None = None,
) -> list[str]:
    errors: list[str] = []
    for step in workflow_step_blocks(job_block):
        if step_name is not None and not step_name_is(step, step_name):
            continue
        if kind == "uses":
            found = re.search(
                rf"(?m)^\s*(?:-\s+)?uses:\s*{re.escape(token)}\s*(?:#.*)?$",
                step,
            ) is not None
        else:
            commands = executable_step_commands(step)
            matching = [
                command
                for command in commands
                if command_executes_token(command, token)
            ]
            found = bool(matching)
        if not found:
            continue
        if step_is_suppressed(step) or step_has_dead_code_construct(step):
            errors.append(f"mandatory {label} step must be unconditional and fail closed")
        if not literal_run_is_fail_closed(step):
            errors.append(f"mandatory multiline {label} step must start with set -euo pipefail")
        if kind == "run" and not any(
            all(value in command for value in required_tokens) for command in matching
        ):
            errors.append(f"mandatory {label} command is missing required exact arguments")
        if any(value in step for value in forbidden_tokens):
            errors.append(f"mandatory {label} step contains a forbidden downgrade")
        if kind == "run" and allowed_flags is not None:
            if (
                len(commands) != 1
                or len(matching) != 1
                or re.search(r"(?im)^\s*(?:echo|printf|Write-(?:Host|Output))\b", step)
                or any(operator in step for operator in (";", "|", "&"))
            ):
                errors.append(f"mandatory {label} must be one isolated executable command")
            flag_list = re.findall(
                r"(?<!\S)(--[A-Za-z0-9-]+)(?=\s|=|$)",
                matching[0],
            )
            if set(flag_list) != set(allowed_flags) or len(flag_list) != len(allowed_flags):
                errors.append(f"mandatory {label} command flags are not the exact allowlisted set")
        return errors
    return [f"mandatory executable {label} step is missing"]


def step_name_is(step: str, expected: str) -> bool:
    return re.search(rf"(?m)^\s*-\s+name:\s*{re.escape(expected)}\s*$", step) is not None


def step_is_suppressed(step: str) -> bool:
    if re.search(r"(?im)^\s*if:\s*", step):
        return True
    continue_match = re.search(r"(?im)^\s*continue-on-error:\s*([^#\r\n]+)", step)
    if continue_match and continue_match.group(1).strip().lower() != "false":
        return True
    return bool(
        re.search(r"\|\|", step)
        or "&" in step
        or re.search(r"(?im)^\s*set\s+\+e\b", step)
        or re.search(r"(?im)^\s*trap\b.*\bERR\b", step)
        or re.search(r"(?m);\s*(?:true|:|exit\s+0)(?:\s|$)", step)
    )


def step_has_dead_code_construct(step: str) -> bool:
    return bool(
        re.search(
            r"(?m)^\s*(?:if|then|elif|else|case|for|select|while|until|function)(?:\s|$)",
            step,
        )
        or re.search(r"(?m)^\s*[A-Za-z_][A-Za-z0-9_]*\s*\(\)\s*\{", step)
        or re.search(r"<<-?\s*['\"]?[A-Za-z_][A-Za-z0-9_]*", step)
    )


def literal_run_is_fail_closed(step: str) -> bool:
    if re.search(r"(?m)^\s*run:\s*\|[-+]?\s*$", step) is None:
        return True
    return re.search(r"(?m)^\s*set\s+-euo\s+pipefail\s*$", step) is not None


def command_executes_token(command: str, token: str) -> bool:
    normalized = command.strip()
    if not normalized or normalized.startswith(("!", "(", "{")):
        return False
    if token.startswith("gh "):
        return normalized.startswith(token)
    script_match = re.search(r"([A-Za-z0-9_]+\.py)(.*)", token)
    if script_match:
        script = re.escape(script_match.group(1))
        suffix = script_match.group(2).strip()
        if re.search(rf"^(?:python|python3)\s+scripts/{script}(?:\s|$)", normalized) is None:
            return False
        return not suffix or re.search(rf"(?:^|\s){re.escape(suffix)}(?:\s|$)", normalized) is not None
    if token.startswith("--"):
        return bool(
            re.match(r"^(?:python|python3)\s+scripts/check_release_provenance\.py(?:\s|$)", normalized)
            and token in normalized
        )
    return token in normalized


def workflow_run_sources(workflow: str) -> list[str]:
    lines = workflow.splitlines()
    sources: list[str] = []
    for index, line in enumerate(lines):
        match = re.match(r"^(\s*)run:\s*(.*)$", line)
        if match is None:
            continue
        indent = len(match.group(1))
        scalar = match.group(2).strip()
        if scalar not in {"|", "|-", "|+", ">", ">-", ">+"}:
            sources.append(scalar)
            continue
        body: list[str] = []
        for item in lines[index + 1 :]:
            if item.strip() and len(item) - len(item.lstrip()) <= indent:
                break
            body.append(item)
        sources.append("\n".join(body))
    return sources


def check_untrusted_run_interpolation(workflow: str, *, label: str) -> list[str]:
    forbidden = (
        "${{ inputs.",
        "${{ github.ref",
        "${{ github.event.workflow_run.",
    )
    errors: list[str] = []
    for source in workflow_run_sources(workflow):
        for token in forbidden:
            if token in source:
                errors.append(
                    f"{label} run source interpolates untrusted context directly: {token}"
                )
    return errors


def executable_step_commands(step: str) -> list[str]:
    lines = step.splitlines()
    for index, line in enumerate(lines):
        match = re.match(r"^\s*(?:-\s+)?run:\s*(.*)$", line)
        if match is None:
            continue
        scalar = match.group(1).strip()
        if scalar not in {"|", "|-", "|+", ">", ">-", ">+"}:
            return [] if re.match(r"^(?:echo|printf)\b", scalar) else [scalar]
        block = lines[index + 1 :]
        indents = [len(item) - len(item.lstrip()) for item in block if item.strip()]
        trim = min(indents, default=0)
        stripped = [item[trim:].strip() for item in block]
        if scalar.startswith(">"):
            stripped = [" ".join(stripped)]
        commands: list[str] = []
        current = ""
        for raw in stripped:
            if not raw or raw.startswith("#"):
                continue
            current = f"{current} {raw}".strip()
            if current.endswith(("\\", "`")):
                current = current[:-1].strip()
                continue
            if not re.match(r"^(?:echo|printf|Write-(?:Host|Output))\b", current, re.I):
                commands.append(current)
            current = ""
        if current:
            commands.append(current)
        return commands
    return []


def job_depends_on(block: str, job: str) -> bool:
    return job in job_needs(block)


def job_needs(block: str) -> set[str]:
    lines = block.splitlines()
    for index, line in enumerate(lines):
        match = re.fullmatch(r"    needs:\s*(.*)", line)
        if not match:
            continue
        inline = match.group(1).strip()
        if inline:
            return parse_inline_needs(inline)
        needs: set[str] = set()
        for item in lines[index + 1 :]:
            if re.fullmatch(r"    [A-Za-z0-9_-]+:.*", item):
                break
            item_match = re.fullmatch(r"      -\s*([A-Za-z0-9_-]+)\s*", item)
            if item_match:
                needs.add(item_match.group(1))
        return needs
    return set()


def job_permission_is(block: str, permission: str, expected: str) -> bool:
    lines = block.splitlines()
    for index, line in enumerate(lines):
        if not re.fullmatch(r"    permissions:\s*", line):
            continue
        for item in lines[index + 1 :]:
            if re.fullmatch(r"    [A-Za-z0-9_-]+:.*", item):
                break
            match = re.fullmatch(r"\s{6}([A-Za-z0-9_-]+):\s*([A-Za-z]+)\s*", item)
            if match and match.group(1) == permission:
                return match.group(2) == expected
        return False
    return False


def parse_inline_needs(raw: str) -> set[str]:
    value = raw.strip()
    if value.startswith("[") and value.endswith("]"):
        return {
            item.strip().strip("'\"")
            for item in value[1:-1].split(",")
            if item.strip().strip("'\"")
        }
    return {value.strip("'\"")}


def normalize_markdown_pipes(text: str) -> str:
    return text.replace("\\|", "|")


def contains_snippet(text: str, snippet: str) -> bool:
    return normalize_snippet_text(snippet) in normalize_snippet_text(text)


def contains_exact_release_version_snippet(text: str, snippet: str) -> bool:
    """Match a stale release token without treating v1.0.27 as v1.0.1."""

    return re.search(rf"{re.escape(snippet)}(?!\d)", text) is not None


def normalize_snippet_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def bounded_section(text: str, start: str, end: str) -> str:
    start_index = text.find(start)
    if start_index == -1:
        return ""
    end_index = text.find(end, start_index)
    if end_index == -1:
        return text[start_index:]
    return text[start_index:end_index]


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

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
PLATFORM_EVIDENCE_IMPORT_DEPENDENTS = (
    "source-and-python",
    "windows-native",
    "macos-native",
    "linux-native",
)
PUBLISH_PROTECTED_PLATFORM_ASSET_COMMAND = (
    'python scripts/check_protected_platform_goal.py --release-tag "${{ github.ref_name }}" '
    "--require-complete --assets-dir release-assets"
)
PUBLISH_PLATFORM_GOAL_COMMAND = (
    'python scripts/check_release_publish_assets.py --assets-dir release-assets '
    '--tag "${{ github.ref_name }}" --require-platform-goal-targets'
)
PUBLISH_REMOTE_PLATFORM_EVIDENCE_AUDIT_COMMAND = (
    'python scripts/check_platform_release_evidence_remote.py --repository "${{ github.repository }}" '
    '--release-tag "${{ github.ref_name }}" --require-goal-targets --require-source-runs '
    "--require-source-artifact-bytes --require-final-record-bytes "
    "--require-release-asset-bytes --require-tag-source-head"
)

REQUIRED_DOC_SNIPPETS = (
    "remote-ops-workspace-v1.0.2-linux-<amd64|arm64>.deb",
    "remote-ops-workspace-v1.0.2-linux-<x86_64|aarch64>.rpm",
    "remote-ops-workspace-v1.0.2-linux-<x86_64|aarch64>.AppImage",
    "remote-ops-workspace-v1.0.2-linux-<x86_64|aarch64>-native.tar.gz",
    "remote-ops-workspace-v1.0.2-macos-<x64|arm64>.dmg",
    "remote-ops-workspace-v1.0.2-macos-<x64|arm64>.pkg",
    "not uploaded by the default GitHub",
    "check_protected_platform_goal.py --release-tag <tag> --require-complete --assets-dir release-assets",
    "release_asset_provenance_complete=false",
    "asset-backed protected goal gate",
    "check_release_publish_assets.py --assets-dir release-assets --tag <tag> --require-platform-goal-targets",
    "import_platform_evidence_artifacts.py --release-tag <tag> --require-goal-targets --out-dir release-assets --verify-source-run",
    "check_platform_review_bundle_artifacts.py --bundle-dir release-assets --require-goal-targets --release-tag <tag> --require-final-record-assets",
    "check_platform_release_evidence_remote.py --repository <owner>/<repo> --release-tag <tag> --require-goal-targets --require-source-runs --require-source-artifact-bytes --require-final-record-bytes --require-release-asset-bytes --require-tag-source-head",
    "downloaded source artifact native artifact SHA-256 values plus review-bundle size/SHA-256 values",
    "published asset digests, sizes and bytes",
    "published final accepted-record JSON bytes",
    "release tag Git object/source head SHA",
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
    "![release](https://img.shields.io/badge/release-v1.0.2-blue)",
    "configs/platform_verified_evidence.json",
    "python scripts/check_protected_platform_goal.py --release-tag <tag> --require-records-complete --show-requirements",
    "python scripts/check_platform_verified_evidence.py --require-goal-targets --require-review-bundles --release-tag <tag>",
    "python scripts/import_platform_evidence_artifacts.py --release-tag <tag> --require-goal-targets --out-dir release-assets --verify-source-run",
    "python scripts/check_platform_review_bundle_artifacts.py --bundle-dir release-assets --require-goal-targets --release-tag <tag> --require-final-record-assets",
    "python scripts/check_platform_release_evidence_remote.py --repository <owner>/<repo> --release-tag <tag> --require-goal-targets --require-source-runs --require-source-artifact-bytes --require-final-record-bytes --require-release-asset-bytes --require-tag-source-head",
    "indirilen source artifact native",
    "published asset digest/size/byte",
    "published final accepted-record JSON bytes",
    "release tag Git object/source head SHA",
    "workflow_run.repository_id",
    "workflow_run.head_repository_id",
    "artifact created_at",
    "source artifact ZIP",
    "source run creation/start/update",
    "ayni tag/repository/workflow file path/source-head/run-attempt",
    "target'a ozel release source workflow file path",
    "python scripts/check_protected_platform_goal.py --release-tag <tag> --require-complete --assets-dir release-assets",
    "release_asset_provenance_complete=false",
    "asset-backed protected goal",
    "python scripts/check_release_publish_assets.py --assets-dir release-assets --tag <tag> --require-platform-goal-targets",
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
    "python scripts/verify.py --quick --no-cli-smoke --release-tag <tag>",
    "python scripts/check_protected_platform_goal.py --release-tag <tag> --require-records-complete --show-requirements",
    "python scripts/check_platform_verified_evidence.py --require-goal-targets --require-review-bundles --release-tag <tag>",
    "accepted-platform-evidence-assets",
    "python scripts/import_platform_evidence_artifacts.py --release-tag <tag> --require-goal-targets --out-dir release-assets --verify-source-run",
    "python scripts/check_platform_review_bundle_artifacts.py --bundle-dir release-assets --require-goal-targets --release-tag <tag> --require-final-record-assets",
    "python scripts/check_platform_release_evidence_remote.py --repository <owner>/<repo> --release-tag <tag> --require-goal-targets --require-source-runs --require-source-artifact-bytes --require-final-record-bytes --require-release-asset-bytes --require-tag-source-head",
    "downloaded source artifact native artifact SHA-256 values",
    "published asset digests, sizes and bytes",
    "published final accepted-record JSON bytes",
    "release tag Git object/source head SHA",
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
    "python scripts/check_protected_platform_goal.py --release-tag <tag> --require-complete --assets-dir release-assets",
    "release_asset_provenance_complete=false",
    "asset-backed protected goal gate",
    "python scripts/check_release_publish_assets.py --assets-dir release-assets --tag <tag> --require-platform-goal-targets",
    "configs/platform_verified_evidence.json",
    "accepted review-bundle hashes",
    "source and native release jobs wait for it before building",
    "`linux_smoke_summary`",
    "`scripts/xp_smoke_runner.cmd`",
    "`xp-evidence` collector",
)

REQUIRED_RELEASE_STRATEGY_SNIPPETS = (
    "python scripts/import_platform_evidence_artifacts.py --release-tag <tag> --require-goal-targets --out-dir <release-assets-dir> --dry-run --verify-source-run",
    "pre-release protected-platform import dry-run",
    "does not stage files for upload",
    "release_asset_provenance_complete=false",
    "record_complete",
    "release_backed_complete",
    "asset-backed protected goal gate",
)

STALE_TURKISH_RELEASE_SNIPPETS = (
    "release-v1.0.1",
    "v1.0.1",
    "remote-ops-workspace-v1.0.1-SHA256SUMS.txt",
)

STALE_DEFAULT_ARTIFACT_SNIPPETS = (
    "remote-ops-workspace-v1.0.2-linux-<i386|amd64|armhf|arm64>.deb",
    "remote-ops-workspace-v1.0.2-linux-<i686|x86_64|armv7hl|aarch64>.rpm",
    "remote-ops-workspace-v1.0.2-linux-<i686|x86_64|armhf|aarch64>.AppImage",
    "remote-ops-workspace-v1.0.2-linux-<i686|x86_64|armhf|aarch64>-native.tar.gz",
    "remote-ops-workspace-v1.0.2-macos-<arch>.dmg",
    "remote-ops-workspace-v1.0.2-macos-<arch>.pkg",
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
    workflow_text = workflow if workflow is not None else read(".github/workflows/release.yml")
    errors: list[str] = []
    if 'FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true"' not in workflow_text:
        errors.append("release workflow must opt JavaScript actions into Node.js 24")
    if "ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION" in workflow_text:
        errors.append("release workflow must not opt JavaScript actions into an insecure Node.js runtime")
    block = workflow_job_block(workflow_text, RELEASE_PREFLIGHT_JOB)
    if not block:
        return [*errors, "release workflow missing release-preflight job"]
    errors.extend(check_checkout_step(block, job=RELEASE_PREFLIGHT_JOB))
    required_snippets = {
        "persist-credentials: false": "checkout credential persistence disabled",
        'python-version: "3.12"': "stable preflight Python version",
        "python scripts/verify.py --quick --no-cli-smoke": "quick verifier before release builds",
        '--release-tag "${{ github.ref_name }}"': "tag-scoped protected platform parity report",
        'python scripts/check_protected_platform_goal.py --release-tag "${{ github.ref_name }}" --show-requirements': (
            "protected platform readiness requirements report"
        ),
        (
            'python scripts/check_protected_platform_goal.py --release-tag "${{ github.ref_name }}" '
            "--require-records-complete --show-requirements"
        ): "protected platform accepted records gate",
        'python scripts/check_platform_verified_evidence.py --require-goal-targets --require-review-bundles --release-tag "${{ github.ref_name }}"': (
            "strict accepted evidence registry gate"
        ),
        "python scripts/check_repository_cleanup.py --require-clean": "clean checkout requirement before tagging",
    }
    for snippet, label in required_snippets.items():
        if snippet not in block:
            errors.append(f"release-preflight missing {label}: {snippet}")
    for job in RELEASE_PREFLIGHT_DEPENDENTS:
        dependent_block = workflow_job_block(workflow_text, job)
        if not dependent_block:
            errors.append(f"release workflow missing preflight dependent job: {job}")
            continue
        if not job_depends_on(dependent_block, "release-preflight"):
            errors.append(f"{job} must depend on release-preflight")
    for job in PLATFORM_EVIDENCE_IMPORT_DEPENDENTS:
        dependent_block = workflow_job_block(workflow_text, job)
        if not dependent_block:
            continue
        if not job_depends_on(dependent_block, "accepted-platform-evidence-assets"):
            errors.append(f"{job} must wait for accepted-platform-evidence-assets")
    errors.extend(check_accepted_platform_evidence_assets_job(workflow_text))
    errors.extend(check_publish_platform_evidence_dependency(workflow_text))
    return errors


def check_accepted_platform_evidence_assets_job(workflow: str) -> list[str]:
    block = workflow_job_block(workflow, "accepted-platform-evidence-assets")
    if not block:
        return ["release workflow missing accepted-platform-evidence-assets job"]
    errors: list[str] = []
    required_snippets = {
        "timeout-minutes: 20": "bounded platform evidence import timeout",
        "actions: read": "Actions read permission for artifact import",
        "contents: read": "contents read permission for checkout",
        "GH_TOKEN: ${{ github.token }}": "GitHub token for gh run download",
        (
            'python scripts/import_platform_evidence_artifacts.py --release-tag "${{ github.ref_name }}" '
            "--require-goal-targets --out-dir release-assets --verify-source-run"
        ): "accepted platform evidence artifact importer",
        (
            'python scripts/check_platform_review_bundle_artifacts.py --bundle-dir release-assets '
            '--require-goal-targets --release-tag "${{ github.ref_name }}" --require-final-record-assets'
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
    block = workflow_job_block(workflow, "publish")
    if not block:
        return ["release workflow missing publish job"]
    errors: list[str] = []
    if not job_depends_on(block, "accepted-platform-evidence-assets"):
        errors.append("publish job must depend on accepted-platform-evidence-assets")
    release_upload_step = workflow_step_block(block, "name: Upload release assets")
    remote_audit_step = workflow_step_block(block, "name: Audit published protected platform evidence")
    protected_asset_gate_index = block.find(PUBLISH_PROTECTED_PLATFORM_ASSET_COMMAND)
    gate_index = block.find(PUBLISH_PLATFORM_GOAL_COMMAND)
    upload_index = block.find(release_upload_step) if release_upload_step else block.find("softprops/action-gh-release")
    remote_audit_index = block.find(remote_audit_step) if remote_audit_step else -1
    if protected_asset_gate_index < 0:
        errors.append(
            "publish job missing protected platform release asset gate: "
            f"{PUBLISH_PROTECTED_PLATFORM_ASSET_COMMAND}"
        )
    if gate_index < 0:
        errors.append(f"publish job missing publish-time protected platform goal gate: {PUBLISH_PLATFORM_GOAL_COMMAND}")
    if not release_upload_step or "uses: softprops/action-gh-release@v3" not in release_upload_step:
        errors.append("publish job missing GitHub release upload step: uses: softprops/action-gh-release@v3")
    if not remote_audit_step or PUBLISH_REMOTE_PLATFORM_EVIDENCE_AUDIT_COMMAND not in remote_audit_step:
        errors.append(
            "publish job missing published protected platform evidence audit: "
            f"{PUBLISH_REMOTE_PLATFORM_EVIDENCE_AUDIT_COMMAND}"
        )
    if not job_permission_is(block, "actions", "read"):
        errors.append("publish job missing Actions read permission for published protected platform evidence audit")
    if not job_permission_is(block, "contents", "write"):
        errors.append("publish job missing contents write permission for GitHub release upload")
    if not remote_audit_step or "GH_TOKEN: ${{ github.token }}" not in remote_audit_step:
        errors.append("publish job missing GitHub token for published protected platform evidence audit")
    if (
        protected_asset_gate_index >= 0
        and gate_index >= 0
        and protected_asset_gate_index > gate_index
    ):
        errors.append("protected platform release asset gate must run before publish asset validation")
    if protected_asset_gate_index >= 0 and upload_index >= 0 and protected_asset_gate_index > upload_index:
        errors.append("protected platform release asset gate must run before GitHub release upload")
    if gate_index >= 0 and upload_index >= 0 and gate_index > upload_index:
        errors.append("publish-time protected platform goal gate must run before GitHub release upload")
    if remote_audit_index >= 0 and upload_index >= 0 and remote_audit_index < upload_index:
        errors.append("published protected platform evidence audit must run after GitHub release upload")
    return errors


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
    readme_release_section = bounded_section(readme, "The release workflow also starts", "Release phases:")
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
        if snippet in turkish_readme:
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
    checkout = workflow_step_block(job_block, "uses: actions/checkout@v6")
    if not checkout:
        return [f"{job} missing repository checkout: uses: actions/checkout@v6"]
    errors: list[str] = []
    if "persist-credentials: false" not in checkout:
        errors.append(f"{job} checkout step missing credential isolation: persist-credentials: false")
    if "clean: true" not in checkout:
        errors.append(f"{job} checkout step missing workspace cleanup: clean: true")
    return errors


def workflow_step_block(job_block: str, marker: str) -> str:
    pattern = rf"(?ms)^      - {re.escape(marker)}\n(.*?)(?=^      - |\Z)"
    match = re.search(pattern, job_block)
    return match.group(0) if match else ""


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

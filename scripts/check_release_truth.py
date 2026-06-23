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
PUBLISH_PLATFORM_GOAL_COMMAND = (
    'python scripts/check_release_publish_assets.py --assets-dir release-assets '
    '--tag "${{ github.ref_name }}" --require-platform-goal-targets'
)

REQUIRED_DOC_SNIPPETS = (
    "remote-ops-workspace-v1.0.2-linux-<amd64|arm64>.deb",
    "remote-ops-workspace-v1.0.2-linux-<x86_64|aarch64>.rpm",
    "remote-ops-workspace-v1.0.2-linux-<x86_64|aarch64>.AppImage",
    "remote-ops-workspace-v1.0.2-linux-<x86_64|aarch64>-native.tar.gz",
    "remote-ops-workspace-v1.0.2-macos-<x64|arm64>.dmg",
    "remote-ops-workspace-v1.0.2-macos-<x64|arm64>.pkg",
    "not uploaded by the default GitHub",
    "check_release_publish_assets.py --assets-dir release-assets --tag <tag> --require-platform-goal-targets",
    "import_platform_evidence_artifacts.py --release-tag <tag> --require-goal-targets --out-dir release-assets --verify-source-run",
    "positive release source run attempt",
)

REQUIRED_TURKISH_DOC_SNIPPETS = (
    "![release](https://img.shields.io/badge/release-v1.0.2-blue)",
    "configs/platform_verified_evidence.json",
    "python scripts/check_platform_verified_evidence.py --require-goal-targets --require-review-bundles --release-tag <tag>",
    "python scripts/import_platform_evidence_artifacts.py --release-tag <tag> --require-goal-targets --out-dir release-assets --verify-source-run",
    "python scripts/check_release_publish_assets.py --assets-dir release-assets --tag <tag> --require-platform-goal-targets",
    "Linux i386, Linux armhf, windows-xp-native-x86 ve windows-xp-native-x64",
    "ayni GitHub release repository, ayni release source head SHA",
    "pozitif release source run attempt",
    "Windows XP native-host readiness 25.0%",
)

REQUIRED_README_RELEASE_SECTION_SNIPPETS = (
    "python scripts/verify.py --quick --no-cli-smoke --release-tag <tag>",
    "python scripts/check_protected_platform_goal.py --release-tag <tag> --require-complete --show-requirements",
    "python scripts/check_platform_verified_evidence.py --require-goal-targets --require-review-bundles --release-tag <tag>",
    "accepted-platform-evidence-assets",
    "python scripts/import_platform_evidence_artifacts.py --release-tag <tag> --require-goal-targets --out-dir release-assets --verify-source-run",
    "Linux i386, Linux armhf, windows-xp-native-x86",
    "windows-xp-native-x64 require finalized accepted evidence records",
    "same release tag, GitHub release repository, release",
    "source head SHA and per-record release source run attempt before any 100%",
    "python scripts/check_release_publish_assets.py --assets-dir release-assets --tag <tag> --require-platform-goal-targets",
    "configs/platform_verified_evidence.json",
    "accepted review-bundle hashes",
    "source and native release jobs wait for it before building",
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
            "--require-complete --show-requirements"
        ): "hard protected platform goal completion gate",
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
        "actions: read": "Actions read permission for artifact import",
        "contents: read": "contents read permission for checkout",
        "GH_TOKEN: ${{ github.token }}": "GitHub token for gh run download",
        (
            'python scripts/import_platform_evidence_artifacts.py --release-tag "${{ github.ref_name }}" '
            "--require-goal-targets --out-dir release-assets --verify-source-run"
        ): "accepted platform evidence artifact importer",
        (
            'python scripts/check_platform_review_bundle_artifacts.py --bundle-dir release-assets '
            '--require-goal-targets --release-tag "${{ github.ref_name }}"'
        ): "imported platform review bundle validator",
        "name: release-platform-evidence-assets": "platform evidence release asset artifact name",
        "path: release-assets/*": "platform evidence release asset upload path",
        "if-no-files-found: error": "platform evidence upload must fail when empty",
    }
    for snippet, label in required_snippets.items():
        if snippet not in block:
            errors.append(f"accepted-platform-evidence-assets missing {label}: {snippet}")
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
    gate_index = block.find(PUBLISH_PLATFORM_GOAL_COMMAND)
    upload_index = block.find("softprops/action-gh-release")
    if gate_index < 0:
        errors.append(f"publish job missing publish-time protected platform goal gate: {PUBLISH_PLATFORM_GOAL_COMMAND}")
    if gate_index >= 0 and upload_index >= 0 and gate_index > upload_index:
        errors.append("publish-time protected platform goal gate must run before GitHub release upload")
    return errors


def check_release_docs() -> list[str]:
    errors: list[str] = []
    readme = normalize_markdown_pipes(read("README.md"))
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
        if snippet in docs:
            errors.append(f"release docs still advertise stale platform evidence workflow guidance: {snippet}")
    return errors


def workflow_job_block(workflow: str, job: str) -> str:
    match = re.search(rf"(?ms)^  {re.escape(job)}:\n(.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)", workflow)
    return match.group(1) if match else ""


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

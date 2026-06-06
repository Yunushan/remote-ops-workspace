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
    "publish",
)

REQUIRED_DOC_SNIPPETS = (
    "remote-ops-workspace-v1.0.1-linux-<amd64|arm64>.deb",
    "remote-ops-workspace-v1.0.1-linux-<x86_64|aarch64>.rpm",
    "remote-ops-workspace-v1.0.1-linux-<x86_64|aarch64>.AppImage",
    "remote-ops-workspace-v1.0.1-linux-<x86_64|aarch64>-native.tar.gz",
    "remote-ops-workspace-v1.0.1-macos-<x64|arm64>.dmg",
    "remote-ops-workspace-v1.0.1-macos-<x64|arm64>.pkg",
    "not uploaded by the default GitHub",
)

STALE_DEFAULT_ARTIFACT_SNIPPETS = (
    "remote-ops-workspace-v1.0.1-linux-<i386|amd64|armhf|arm64>.deb",
    "remote-ops-workspace-v1.0.1-linux-<i686|x86_64|armv7hl|aarch64>.rpm",
    "remote-ops-workspace-v1.0.1-linux-<i686|x86_64|armhf|aarch64>.AppImage",
    "remote-ops-workspace-v1.0.1-linux-<i686|x86_64|armhf|aarch64>-native.tar.gz",
    "remote-ops-workspace-v1.0.1-macos-<arch>.dmg",
    "remote-ops-workspace-v1.0.1-macos-<arch>.pkg",
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
        if "needs: release-preflight" not in dependent_block and "- release-preflight" not in dependent_block:
            errors.append(f"{job} must depend on release-preflight")
    return errors


def check_release_docs() -> list[str]:
    errors: list[str] = []
    docs = "\n".join(
        normalize_markdown_pipes(read(path))
        for path in (
            "README.md",
            "docs/PLATFORM_SUPPORT.md",
            "docs/RELEASE_STRATEGY.md",
        )
    )
    for snippet in REQUIRED_DOC_SNIPPETS:
        if snippet not in docs:
            errors.append(f"release docs missing workflow artifact truth snippet: {snippet}")
    for snippet in STALE_DEFAULT_ARTIFACT_SNIPPETS:
        if snippet in docs:
            errors.append(f"release docs still advertise stale default artifact pattern: {snippet}")
    return errors


def workflow_job_block(workflow: str, job: str) -> str:
    match = re.search(rf"(?ms)^  {re.escape(job)}:\n(.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)", workflow)
    return match.group(1) if match else ""


def normalize_markdown_pipes(text: str) -> str:
    return text.replace("\\|", "|")


def read(relative: str) -> str:
    return (ROOT / relative).read_text(encoding="utf-8")


if __name__ == "__main__":
    raise SystemExit(main())

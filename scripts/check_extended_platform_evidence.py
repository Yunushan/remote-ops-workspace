from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "extended-platform-evidence.yml"


def main() -> int:
    errors = check_extended_platform_evidence()
    if errors:
        for error in errors:
            print(f"extended platform evidence: {error}", file=sys.stderr)
        return 1
    print("extended platform evidence workflow passed")
    return 0


def check_extended_platform_evidence(workflow: str | None = None) -> list[str]:
    text = workflow if workflow is not None else WORKFLOW_PATH.read_text(encoding="utf-8")
    errors: list[str] = []
    errors.extend(check_top_level_policy(text))
    errors.extend(check_linux_job(text, target="linux-i386", job="linux-i386-native-evidence", runner="i386"))
    errors.extend(check_linux_job(text, target="linux-armhf", job="linux-armhf-native-evidence", runner="armhf"))
    return errors


def check_top_level_policy(workflow: str) -> list[str]:
    errors: list[str] = []
    if "workflow_dispatch:" not in workflow:
        errors.append("extended platform evidence workflow must be manual workflow_dispatch only")
    for disallowed in ("push:", "pull_request:", "tags:"):
        if disallowed in workflow:
            errors.append(f"extended platform evidence workflow must not run on {disallowed.rstrip(':')}")
    if "permissions:\n  contents: read" not in workflow:
        errors.append("extended platform evidence workflow must use read-only contents permission")
    if 'FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true"' not in workflow:
        errors.append("extended platform evidence workflow must opt JavaScript actions into Node.js 24")
    if "linux-i386" not in workflow or "linux-armhf" not in workflow:
        errors.append("extended platform evidence workflow must expose linux-i386 and linux-armhf targets")
    if "release_asset_base_url:" not in workflow:
        errors.append("extended platform evidence workflow must require release_asset_base_url input")
    return errors


def check_linux_job(workflow: str, *, target: str, job: str, runner: str) -> list[str]:
    block = workflow_job_block(workflow, job)
    if not block:
        return [f"extended platform evidence workflow missing job: {job}"]
    record_name = f"platform-verified-evidence-{target}.json"
    builder_identity_name = f"builder-identity-{target}.json"
    errors: list[str] = []
    required_snippets = {
        f"if: ${{{{ inputs.target == '{target}' }}}}": "target guard",
        f"runs-on: [self-hosted, linux, {runner}]": "matching self-hosted runner labels",
        "timeout-minutes: 90": "bounded native evidence job timeout",
        "uses: actions/checkout@v6": "repository checkout",
        "persist-credentials: false": "checkout credential isolation",
        f"python3 scripts/check_extended_platform_builder.py --target {target} --out native-dist/linux/{builder_identity_name}": "builder identity preflight evidence",
        "python3 -m venv .venv-native": "isolated release virtual environment",
        'python -m pip install --constraint requirements-release.txt pip setuptools wheel ".[security,package]"': "pinned release dependency installation",
        "bash scripts/make_linux_native.sh": "native Linux artifact build",
        "bash scripts/smoke_linux_native.sh": "native installer smoke",
        f"python scripts/check_platform_promotion_artifacts.py --target {target}": "promotion artifact validation",
        f"python scripts/make_platform_verified_evidence_record.py \\\n            --target {target}": "accepted-evidence record generation",
        '--release-asset-base-url "${{ inputs.release_asset_base_url }}"': "release asset URL evidence input",
        '--workflow-run-url "${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}"': "workflow run URL evidence",
        f"--builder-evidence native-dist/linux/{builder_identity_name}": "builder identity evidence input",
        "--runner-label self-hosted": "self-hosted runner-label evidence",
        "--runner-label linux": "linux runner-label evidence",
        f"--runner-label {runner}": "architecture runner-label evidence",
        f"--out native-dist/linux/{record_name}": "candidate evidence record output",
        "actions/upload-artifact@v7": "evidence artifact upload",
        "if-no-files-found: error": "missing evidence artifact failure",
    }
    for snippet, label in required_snippets.items():
        if snippet not in block:
            errors.append(f"{job} missing {label}: {snippet}")
    if "softprops/action-gh-release" in block:
        errors.append(f"{job} must not publish GitHub releases")
    if "contents: write" in block:
        errors.append(f"{job} must not request write permissions")
    return errors


def workflow_job_block(workflow: str, job: str) -> str:
    match = re.search(rf"(?ms)^  {re.escape(job)}:\n(.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)", workflow)
    return match.group(1) if match else ""


if __name__ == "__main__":
    raise SystemExit(main())

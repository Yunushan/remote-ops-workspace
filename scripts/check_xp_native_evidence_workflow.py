from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "xp-native-evidence.yml"


def main() -> int:
    errors = check_xp_native_evidence_workflow()
    if errors:
        for error in errors:
            print(f"XP native evidence workflow: {error}", file=sys.stderr)
        return 1
    print("XP native evidence workflow passed")
    return 0


def check_xp_native_evidence_workflow(workflow: str | None = None) -> list[str]:
    text = workflow if workflow is not None else WORKFLOW_PATH.read_text(encoding="utf-8")
    errors: list[str] = []
    errors.extend(check_top_level_policy(text))
    errors.extend(check_xp_job(text))
    return errors


def check_top_level_policy(workflow: str) -> list[str]:
    errors: list[str] = []
    if "workflow_dispatch:" not in workflow:
        errors.append("XP native evidence workflow must be manual workflow_dispatch only")
    for disallowed in ("push:", "pull_request:", "tags:"):
        if disallowed in workflow:
            errors.append(f"XP native evidence workflow must not run on {disallowed.rstrip(':')}")
    if "permissions:\n  contents: read" not in workflow:
        errors.append("XP native evidence workflow must use read-only contents permission")
    if re.search(r"(?m)^\s+[A-Za-z0-9_-]+:\s+write\s*$", workflow):
        errors.append("XP native evidence workflow must not request write permissions")
    if 'FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true"' not in workflow:
        errors.append("XP native evidence workflow must opt JavaScript actions into Node.js 24")
    for target in ("windows-xp-native-x86", "windows-xp-native-x64"):
        if target not in workflow:
            errors.append(f"XP native evidence workflow must expose target {target}")
    for input_name in ("release_asset_base_url", "assets_dir", "evidence_file", "evidence_dir"):
        if f"{input_name}:" not in workflow:
            errors.append(f"XP native evidence workflow must require {input_name} input")
    return errors


def check_xp_job(workflow: str) -> list[str]:
    block = workflow_job_block(workflow, "xp-native-evidence")
    if not block:
        return ["XP native evidence workflow missing job: xp-native-evidence"]
    errors: list[str] = []
    required_snippets = {
        "runs-on: [self-hosted, xp-evidence]": "XP evidence self-hosted runner labels",
        "timeout-minutes: 60": "bounded XP evidence job timeout",
        "uses: actions/checkout@v6": "repository checkout",
        "persist-credentials: false": "checkout credential isolation",
        "uses: actions/setup-python@v6": "Python setup",
        'python-version: "3.12"': "Python version pin",
        "Path('xp-evidence-output').mkdir(parents=True, exist_ok=True)": "evidence output directory creation",
        'python scripts/check_xp_native_evidence_dispatch_inputs.py --target "${{ inputs.target }}" --release-tag "${{ inputs.release_tag }}" --release-asset-base-url "${{ inputs.release_asset_base_url }}" --workflow-run-url "${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}" --assets-dir "${{ inputs.assets_dir }}" --evidence-file "${{ inputs.evidence_file }}" --evidence-dir "${{ inputs.evidence_dir }}"': "XP dispatch input preflight",
        'python scripts/check_xp_native_evidence.py --evidence "${{ inputs.evidence_file }}" --assets-dir "${{ inputs.assets_dir }}" --evidence-dir "${{ inputs.evidence_dir }}"': "XP evidence validation",
        'python scripts/check_platform_promotion_artifacts.py --target "${{ inputs.target }}" --assets-dir "${{ inputs.assets_dir }}" --tag "${{ inputs.release_tag }}"': "XP promotion artifact validation",
        'python scripts/make_platform_verified_evidence_record.py --target "${{ inputs.target }}"': "accepted-evidence candidate generation",
        '--release-asset-base-url "${{ inputs.release_asset_base_url }}"': "release asset URL input binding",
        '--release-source-workflow-run-url "${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}"': "release source workflow run binding",
        '--release-source-artifact-name "xp-native-evidence-${{ inputs.target }}-${{ inputs.release_tag }}"': "target/release scoped source artifact name",
        '--release-source-head-sha "${{ github.sha }}"': "release source head SHA binding",
        '--xp-evidence "${{ inputs.evidence_file }}"': "XP evidence input binding",
        '--xp-evidence-dir "${{ inputs.evidence_dir }}"': "XP evidence directory binding",
        '--out "xp-evidence-output/platform-verified-evidence-${{ inputs.target }}.json"': "candidate evidence output",
        'python scripts/make_xp_native_evidence_bundle.py --target "${{ inputs.target }}"': "review evidence bundle generation",
        '--candidate-record "xp-evidence-output/platform-verified-evidence-${{ inputs.target }}.json"': "candidate record bundle input",
        "--out-dir xp-evidence-output": "review bundle output directory",
        'python scripts/finalize_platform_verified_evidence_record.py --candidate-record "xp-evidence-output/platform-verified-evidence-${{ inputs.target }}.json"': "finalized evidence record generation",
        '--bundle-manifest "xp-evidence-output/xp-native-evidence-bundle-${{ inputs.target }}-${{ inputs.release_tag }}.json"': "finalized evidence manifest binding",
        '--bundle-archive "xp-evidence-output/xp-native-evidence-bundle-${{ inputs.target }}-${{ inputs.release_tag }}.zip"': "finalized evidence archive binding",
        '--bundle-sha256s "xp-evidence-output/xp-native-evidence-bundle-${{ inputs.target }}-${{ inputs.release_tag }}-SHA256SUMS.txt"': "finalized evidence checksum sidecar binding",
        '--out "xp-evidence-output/platform-verified-evidence-${{ inputs.target }}-final.json"': "finalized evidence output",
        'python scripts/stage_xp_native_evidence_upload.py --target "${{ inputs.target }}" --release-tag "${{ inputs.release_tag }}" --assets-dir "${{ inputs.assets_dir }}" --evidence-output-dir xp-evidence-output --out-dir xp-evidence-upload --force': "scoped XP upload staging",
        "actions/upload-artifact@v7": "evidence artifact upload",
        "name: xp-native-evidence-${{ inputs.target }}-${{ inputs.release_tag }}": "target/release scoped uploaded artifact",
        "path: xp-evidence-upload/*": "scoped staged upload path",
        "if-no-files-found: error": "missing evidence artifact failure",
    }
    for snippet, label in required_snippets.items():
        if snippet not in block:
            errors.append(f"xp-native-evidence job missing {label}: {snippet}")
    if "${{ inputs.assets_dir }}/*" in block:
        errors.append("xp-native-evidence job must not upload raw operator-supplied assets_dir wildcard")
    if re.search(r"(?m)^\s+xp-evidence-output/\*", block):
        errors.append("xp-native-evidence job must upload scoped staged files, not raw xp-evidence-output wildcard")
    if "softprops/action-gh-release" in block:
        errors.append("xp-native-evidence job must not publish GitHub releases")
    if re.search(r"(?m)^\s+[A-Za-z0-9_-]+:\s+write\s*$", block):
        errors.append("xp-native-evidence job must not request write permissions")
    return errors


def workflow_job_block(workflow: str, job: str) -> str:
    match = re.search(rf"(?ms)^  {re.escape(job)}:\n(.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)", workflow)
    return match.group(1) if match else ""


if __name__ == "__main__":
    raise SystemExit(main())

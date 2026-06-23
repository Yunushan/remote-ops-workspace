from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "extended-platform-evidence.yml"
LINUX_TARGET_ARTIFACTS = {
    "linux-i386": (
        "remote-ops-workspace-${{ inputs.release_tag }}-linux-i386.deb",
        "remote-ops-workspace-${{ inputs.release_tag }}-linux-i686.rpm",
        "remote-ops-workspace-${{ inputs.release_tag }}-linux-i686.AppImage",
        "remote-ops-workspace-${{ inputs.release_tag }}-linux-i686-native.tar.gz",
        "remote-ops-workspace-${{ inputs.release_tag }}-linux-i686-native-manifest.json",
        "remote-ops-workspace-${{ inputs.release_tag }}-linux-i686-native-SHA256SUMS.txt",
    ),
    "linux-armhf": (
        "remote-ops-workspace-${{ inputs.release_tag }}-linux-armhf.deb",
        "remote-ops-workspace-${{ inputs.release_tag }}-linux-armv7hl.rpm",
        "remote-ops-workspace-${{ inputs.release_tag }}-linux-armhf.AppImage",
        "remote-ops-workspace-${{ inputs.release_tag }}-linux-armhf-native.tar.gz",
        "remote-ops-workspace-${{ inputs.release_tag }}-linux-armhf-native-manifest.json",
        "remote-ops-workspace-${{ inputs.release_tag }}-linux-armhf-native-SHA256SUMS.txt",
    ),
}


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
    if re.search(r"(?m)^\s+[A-Za-z0-9_-]+:\s+write\s*$", workflow):
        errors.append("extended platform evidence workflow must not request write permissions")
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
    smoke_name = f"native-smoke-{target}.log"
    release_dir = f"platform-evidence-staging/{target}/${{{{ inputs.release_tag }}}}"
    assets_dir = f"{release_dir}/artifacts"
    evidence_dir = release_dir
    source_artifact_name = f"extended-linux-evidence-{target}-${{{{ inputs.release_tag }}}}"
    stage_upload_snippet = (
        "python scripts/stage_extended_linux_evidence_upload.py \\\n"
        f"            --target {target} \\\n"
        '            --release-tag "${{ inputs.release_tag }}" \\\n'
        f"            --source-dir {assets_dir} \\\n"
        "            --out-dir linux-evidence-upload \\\n"
        "            --force"
    )
    smoke_command_snippet = (
        f"bash scripts/smoke_linux_native.sh --arch {runner} --dist native-dist/linux "
        f"--target {target} --workflow-run-url "
        '"${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}" '
        '--source-head-sha "${{ github.sha }}" '
        f"2>&1 | tee {evidence_dir}/{smoke_name}"
    )
    local_preflight_snippet = (
        "python scripts/check_platform_goal_local_evidence.py \\\n"
        "            --root platform-evidence-staging \\\n"
        '            --release-tag "${{ inputs.release_tag }}" \\\n'
        f"            --target {target} \\\n"
        f"            --assets-dir {assets_dir} \\\n"
        f"            --linux-builder-evidence {evidence_dir}/{builder_identity_name} \\\n"
        f"            --linux-smoke-evidence {evidence_dir}/{smoke_name} \\\n"
        '            --linux-workflow-run-url "${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}" \\\n'
        '            --linux-source-head-sha "${{ github.sha }}"'
    )
    errors: list[str] = []
    required_snippets = {
        f"if: ${{{{ inputs.target == '{target}' }}}}": "target guard",
        f"runs-on: [self-hosted, linux, {runner}]": "matching self-hosted runner labels",
        "timeout-minutes: 90": "bounded native evidence job timeout",
        "uses: actions/checkout@v6": "repository checkout",
        "persist-credentials: false": "checkout credential isolation",
        f"python3 scripts/check_extended_platform_dispatch_inputs.py \\\n            --target {target}": "dispatch input preflight",
        f"python3 scripts/check_extended_platform_builder.py \\\n            --target {target}": "builder identity preflight evidence",
        f"--out {evidence_dir}/{builder_identity_name}": "builder identity output",
        '--source-head-sha "${{ github.sha }}"': "builder source head SHA evidence",
        "python3 -m venv .venv-native": "isolated release virtual environment",
        'python -m pip install --constraint requirements-release.txt pip setuptools wheel ".[security,package]"': "pinned release dependency installation",
        "bash scripts/make_linux_native.sh": "native Linux artifact build",
        f"mkdir -p native-dist/linux {assets_dir}": "raw build output and target/release promotion staging directories",
        f"mkdir -p {assets_dir}": "target-scoped Linux artifact staging directory",
        smoke_command_snippet: "native installer smoke evidence capture",
        (
            f'python scripts/check_platform_promotion_artifacts.py --target {target} '
            f'--assets-dir {assets_dir} --tag "${{{{ inputs.release_tag }}}}" --strict'
        ): "strict promotion artifact validation",
        local_preflight_snippet: "local protected goal evidence preflight",
        f"python scripts/make_platform_verified_evidence_record.py \\\n            --target {target}": "accepted-evidence record generation",
        f"--assets-dir {assets_dir}": "target-scoped accepted-evidence artifact path",
        '--release-asset-base-url "${{ inputs.release_asset_base_url }}"': "release asset URL evidence input",
        '--workflow-run-url "${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}"': "workflow run URL evidence",
        f"--release-source-artifact-name {source_artifact_name}": "release source artifact name binding",
        '--release-source-head-sha "${{ github.sha }}"': "release source head SHA evidence",
        f"--builder-evidence {evidence_dir}/{builder_identity_name}": "builder identity evidence input",
        f"--linux-smoke-evidence {evidence_dir}/{smoke_name}": "native smoke evidence input",
        "--local-evidence-root platform-evidence-staging": "local evidence preflight root binding",
        "--runner-label self-hosted": "self-hosted runner-label evidence",
        "--runner-label linux": "linux runner-label evidence",
        f"--runner-label {runner}": "architecture runner-label evidence",
        f"--out {assets_dir}/{record_name}": "candidate evidence record output",
        f"python scripts/make_extended_linux_evidence_bundle.py \\\n            --target {target}": "review evidence bundle generation",
        f"--smoke-evidence {evidence_dir}/{smoke_name}": "review bundle smoke evidence input",
        f"--candidate-record {assets_dir}/{record_name}": "candidate record bundle input",
        f"python scripts/finalize_platform_verified_evidence_record.py \\\n            --candidate-record {assets_dir}/{record_name}": "finalized evidence record generation",
        f"--bundle-manifest {assets_dir}/extended-linux-evidence-bundle-{target}-${{{{ inputs.release_tag }}}}.json": "finalized evidence manifest binding",
        f"--bundle-archive {assets_dir}/extended-linux-evidence-bundle-{target}-${{{{ inputs.release_tag }}}}.zip": "finalized evidence archive binding",
        f"--bundle-sha256s {assets_dir}/extended-linux-evidence-bundle-{target}-${{{{ inputs.release_tag }}}}-SHA256SUMS.txt": "finalized evidence checksum sidecar binding",
        f"--out {assets_dir}/platform-verified-evidence-{target}-final.json": "finalized evidence record output",
        stage_upload_snippet: "scoped Linux evidence upload staging",
        "actions/upload-artifact@v7": "evidence artifact upload",
        f"name: {source_artifact_name}": "target/release-scoped evidence artifact name",
        "path: linux-evidence-upload/*": "scoped staged upload path",
        "if-no-files-found: error": "missing evidence artifact failure",
    }
    for artifact in LINUX_TARGET_ARTIFACTS[target]:
        required_snippets[f"cp native-dist/linux/{artifact} {assets_dir}/"] = (
            f"target-scoped artifact staging for {artifact}"
        )
    for snippet, label in required_snippets.items():
        if snippet not in block:
            errors.append(f"{job} missing {label}: {snippet}")
    dispatch_command = (
        "python3 scripts/check_extended_platform_dispatch_inputs.py \\\n"
        f"            --target {target} \\\n"
        '            --release-tag "${{ inputs.release_tag }}" \\\n'
        '            --release-asset-base-url "${{ inputs.release_asset_base_url }}" \\\n'
        '            --workflow-run-url "${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}"'
    )
    if dispatch_command not in block:
        errors.append(f"{job} dispatch input preflight must bind target, release_tag, release URL and workflow_run_url")
    builder_command = (
        "python3 scripts/check_extended_platform_builder.py \\\n"
        f"            --target {target} \\\n"
        '            --release-tag "${{ inputs.release_tag }}" \\\n'
        '            --workflow-run-url "${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}" \\\n'
        '            --source-head-sha "${{ github.sha }}" \\\n'
        f"            --out {evidence_dir}/{builder_identity_name}"
    )
    if builder_command not in block:
        errors.append(f"{job} builder identity preflight must bind release_tag, workflow_run_url and source_head_sha")
    if "--allow-extra-artifacts" in block:
        errors.append(f"{job} must use strict Linux artifact preflight without --allow-extra-artifacts")
    if "path: native-dist/linux/*" in block:
        errors.append(f"{job} must upload scoped staged files, not raw native-dist/linux wildcard")
    stale_paths = (
        f"--root . \\\n            --release-tag \"${{{{ inputs.release_tag }}}}\" \\\n            --target {target}",
        f"--assets-dir native-dist/linux/{target}",
        f"--builder-evidence native-dist/linux-evidence/{target}/",
        f"--linux-builder-evidence native-dist/linux-evidence/{target}/",
        f"--smoke-evidence native-dist/linux-evidence/{target}/",
        f"--linux-smoke-evidence native-dist/linux-evidence/{target}/",
        f"--source-dir native-dist/linux/{target}",
        f"native-dist/linux/{target}",
    )
    for stale in stale_paths:
        if stale in block:
            errors.append(f"{job} must use target/release-scoped platform-evidence-staging paths, found {stale}")
    if "softprops/action-gh-release" in block:
        errors.append(f"{job} must not publish GitHub releases")
    if re.search(r"(?m)^\s+[A-Za-z0-9_-]+:\s+write\s*$", block):
        errors.append(f"{job} must not request write permissions")
    return errors


def workflow_job_block(workflow: str, job: str) -> str:
    match = re.search(rf"(?ms)^  {re.escape(job)}:\n(.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)", workflow)
    return match.group(1) if match else ""


if __name__ == "__main__":
    raise SystemExit(main())

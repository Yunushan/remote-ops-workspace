from __future__ import annotations

import re
import subprocess
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
WORKFLOW_SCRIPT_DEPENDENCIES = (
    Path("scripts") / "check_extended_platform_dispatch_inputs.py",
    Path("scripts") / "check_extended_platform_builder.py",
    Path("scripts") / "make_linux_native.sh",
    Path("scripts") / "smoke_linux_native.sh",
    Path("scripts") / "check_platform_promotion_artifacts.py",
    Path("scripts") / "check_platform_goal_local_evidence.py",
    Path("scripts") / "make_platform_verified_evidence_record.py",
    Path("scripts") / "make_extended_linux_evidence_bundle.py",
    Path("scripts") / "finalize_platform_verified_evidence_record.py",
    Path("scripts") / "stage_extended_linux_evidence_upload.py",
)
WORKFLOW_SCRIPT_REFERENCE_RE = re.compile(r"scripts/[A-Za-z0-9_./-]+\.(?:cmd|py|sh)")


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
    errors.extend(check_github_expression_delimiters(text))
    errors.extend(check_top_level_policy(text))
    errors.extend(check_linux_job(text, target="linux-i386", job="linux-i386-native-evidence", runner="i386"))
    errors.extend(check_linux_job(text, target="linux-armhf", job="linux-armhf-native-evidence", runner="armhf"))
    errors.extend(check_workflow_script_dependencies(workflow_script_dependencies(text)))
    return errors


def check_github_expression_delimiters(workflow: str) -> list[str]:
    errors: list[str] = []
    for line_number, line in enumerate(workflow.splitlines(), start=1):
        if github_expression_delimiters_unbalanced(line):
            errors.append(
                "extended platform evidence workflow has unbalanced GitHub expression "
                f"delimiters on line {line_number}: {line.strip()}"
            )
    return errors


def github_expression_delimiters_unbalanced(line: str) -> bool:
    index = 0
    while index < len(line):
        next_open = line.find("${{", index)
        next_close = line.find("}}", index)
        if next_close != -1 and (next_open == -1 or next_close < next_open):
            return True
        if next_open == -1:
            return False
        close = line.find("}}", next_open + 3)
        nested_open = line.find("${{", next_open + 3)
        if close == -1 or (nested_open != -1 and nested_open < close):
            return True
        index = close + 2
    return False


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
    errors.extend(
        check_top_level_concurrency(
            workflow,
            workflow_label="extended platform evidence",
            group="extended-platform-evidence-${{ inputs.target }}-${{ inputs.release_tag }}",
        )
    )
    errors.extend(check_top_level_run_defaults(workflow, workflow_label="extended platform evidence"))
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
    upload_dir = f"platform-evidence-upload/{target}/${{{{ inputs.release_tag }}}}"
    source_artifact_name = f"extended-linux-evidence-{target}-${{{{ inputs.release_tag }}}}"
    stage_upload_snippet = (
        "python scripts/stage_extended_linux_evidence_upload.py \\\n"
        f"            --target {target} \\\n"
        '            --release-tag "${{ inputs.release_tag }}" \\\n'
        f"            --source-dir {assets_dir} \\\n"
        f"            --out-dir {upload_dir} \\\n"
        "            --force"
    )
    smoke_command_snippet = (
        f"bash scripts/smoke_linux_native.sh --arch {runner} --dist native-dist/linux "
        f"--target {target} --workflow-run-url "
        '"${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}" '
        '--workflow-run-attempt "${{ github.run_attempt }}" '
        '--source-head-sha "${{ github.sha }}" '
        f"--builder-evidence {evidence_dir}/{builder_identity_name} "
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
        '            --linux-source-head-sha "${{ github.sha }}" \\\n'
        '            --linux-source-run-attempt "${{ github.run_attempt }}"'
    )
    errors: list[str] = []
    required_snippets = {
        f"if: ${{{{ inputs.target == '{target}' }}}}": "target guard",
        f"runs-on: [self-hosted, linux, {runner}]": "matching self-hosted runner labels",
        "timeout-minutes: 90": "bounded native evidence job timeout",
        "RELEASE_TAG: ${{ inputs.release_tag }}": "release-tag environment binding for native build script",
        "uses: actions/checkout@v6": "repository checkout",
        "persist-credentials: false": "checkout credential isolation",
        "clean: true": "self-hosted checkout workspace cleanup",
        f"python3 scripts/check_extended_platform_dispatch_inputs.py \\\n            --target {target}": "dispatch input preflight",
        f"python3 scripts/check_extended_platform_builder.py \\\n            --target {target}": "builder identity preflight evidence",
        f"--out {evidence_dir}/{builder_identity_name}": "builder identity output",
        '            --workflow-run-attempt "${{ github.run_attempt }}" \\\n': "builder workflow run-attempt evidence",
        '--source-head-sha "${{ github.sha }}"': "builder source head SHA evidence",
        "python3 -m venv .venv-native": "isolated release virtual environment",
        'python -m pip install --constraint requirements-release.txt pip setuptools wheel ".[security,package]"': "pinned release dependency installation",
        "bash scripts/make_linux_native.sh": "native Linux artifact build",
        f"mkdir -p native-dist/linux {assets_dir}": "raw build output and target/release promotion staging directories",
        f"mkdir -p {assets_dir}": "target-scoped Linux artifact staging directory",
        smoke_command_snippet: "native installer smoke evidence capture",
        '--workflow-run-attempt "${{ github.run_attempt }}" --source-head-sha "${{ github.sha }}"': (
            "native smoke workflow run-attempt evidence"
        ),
        (
            f'python scripts/check_platform_promotion_artifacts.py --target {target} '
            f'--assets-dir {assets_dir} --tag "${{{{ inputs.release_tag }}}}" --strict'
        ): "strict promotion artifact validation",
        local_preflight_snippet: "local protected goal evidence preflight",
        f"python scripts/make_platform_verified_evidence_record.py \\\n            --target {target}": "accepted-evidence record generation",
        f"--assets-dir {assets_dir}": "target-scoped accepted-evidence artifact path",
        '--release-asset-base-url "${{ inputs.release_asset_base_url }}"': "release asset URL evidence input",
        '--workflow-run-url "${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}"': "workflow run URL evidence",
        '--workflow-ref-name "${{ github.ref_name }}"': "release-tag workflow ref binding",
        f"--release-source-artifact-name {source_artifact_name}": "release source artifact name binding",
        '--release-source-head-sha "${{ github.sha }}"': "release source head SHA evidence",
        '--linux-source-run-attempt "${{ github.run_attempt }}"': "local evidence source run-attempt binding",
        '--release-source-run-attempt "${{ github.run_attempt }}"': "release source run-attempt binding",
        f"--builder-evidence {evidence_dir}/{builder_identity_name}": "builder identity evidence input",
        f"--linux-smoke-evidence {evidence_dir}/{smoke_name}": "native smoke evidence input",
        "--local-evidence-root platform-evidence-staging": "local evidence preflight root binding",
        f"--staged-upload-out-dir {upload_dir}": "candidate staged upload output binding",
        "--runner-label self-hosted": "self-hosted runner-label evidence",
        "--runner-label linux": "linux runner-label evidence",
        f"--runner-label {runner}": "architecture runner-label evidence",
        f"--out {assets_dir}/{record_name}": "candidate evidence record output",
        f"python scripts/make_extended_linux_evidence_bundle.py \\\n            --target {target}": "review evidence bundle generation",
        f"--smoke-evidence {evidence_dir}/{smoke_name}": "review bundle smoke evidence input",
        f"--candidate-record {assets_dir}/{record_name}": "candidate record bundle input",
        f"--out-dir {assets_dir}": "target/release scoped review bundle output directory",
        f"python scripts/finalize_platform_verified_evidence_record.py \\\n            --candidate-record {assets_dir}/{record_name}": "finalized evidence record generation",
        f"--bundle-manifest {assets_dir}/extended-linux-evidence-bundle-{target}-${{{{ inputs.release_tag }}}}.json": "finalized evidence manifest binding",
        f"--bundle-archive {assets_dir}/extended-linux-evidence-bundle-{target}-${{{{ inputs.release_tag }}}}.zip": "finalized evidence archive binding",
        f"--bundle-sha256s {assets_dir}/extended-linux-evidence-bundle-{target}-${{{{ inputs.release_tag }}}}-SHA256SUMS.txt": "finalized evidence checksum sidecar binding",
        f"--out {assets_dir}/platform-verified-evidence-{target}-final.json": "finalized evidence record output",
        stage_upload_snippet: "scoped Linux evidence upload staging",
        "actions/upload-artifact@v7": "evidence artifact upload",
        f"name: {source_artifact_name}": "target/release-scoped evidence artifact name",
        f"path: {upload_dir}/*": "target/release scoped staged upload path",
        "if-no-files-found: error": "missing evidence artifact failure",
        "include-hidden-files: false": "hidden file exclusion for evidence artifact upload",
        "retention-days: 90": "evidence artifact retention window",
    }
    for artifact in LINUX_TARGET_ARTIFACTS[target]:
        required_snippets[f"cp native-dist/linux/{artifact} {assets_dir}/"] = (
            f"target-scoped artifact staging for {artifact}"
        )
    for snippet, label in required_snippets.items():
        if snippet not in block:
            errors.append(f"{job} missing {label}: {snippet}")
    errors.extend(check_checkout_step(block, job=job))
    errors.extend(check_run_shell_safety(block, job=job))
    arch_label = target.removeprefix("linux-")
    step_prefix = f"Linux {arch_label}"
    errors.extend(
        check_ordered_snippets(
            block,
            (
                ("dispatch input preflight", f"      - name: Validate {step_prefix} evidence dispatch inputs"),
                ("builder identity evidence", f"      - name: Check {step_prefix} builder identity"),
                ("isolated release environment", "      - name: Create isolated release environment"),
                ("native Linux artifact build", f"      - name: Build {step_prefix} native artifacts"),
                ("native installer smoke evidence capture", f"      - name: Smoke {step_prefix} native artifacts"),
                ("target artifact staging", f"      - name: Stage {step_prefix} target artifacts"),
                ("strict promotion artifact validation", f"      - name: Validate {step_prefix} promotion artifacts"),
                (
                    "local protected goal evidence preflight",
                    f"      - name: Preflight {step_prefix} local platform goal evidence",
                ),
                (
                    "accepted-evidence candidate generation",
                    f"      - name: Generate {step_prefix} accepted-evidence candidate",
                ),
                ("review evidence bundle generation", f"      - name: Package {step_prefix} review evidence bundle"),
                (
                    "finalized evidence record generation",
                    f"      - name: Finalize {step_prefix} accepted-evidence candidate",
                ),
                ("scoped Linux evidence upload staging", f"      - name: Stage scoped {step_prefix} evidence upload"),
                ("evidence artifact upload", "      - uses: actions/upload-artifact@v7"),
            ),
            job=job,
        )
    )
    dispatch_command = (
        "python3 scripts/check_extended_platform_dispatch_inputs.py \\\n"
        f"            --target {target} \\\n"
        '            --release-tag "${{ inputs.release_tag }}" \\\n'
        '            --release-asset-base-url "${{ inputs.release_asset_base_url }}" \\\n'
        '            --workflow-run-url "${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}" \\\n'
        '            --workflow-ref-name "${{ github.ref_name }}" \\\n'
        '            --source-head-sha "${{ github.sha }}" \\\n'
        '            --source-run-attempt "${{ github.run_attempt }}"'
    )
    if dispatch_command not in block:
        errors.append(
            f"{job} dispatch input preflight must bind target, release_tag, release URL, workflow_run_url, "
            "workflow_ref_name, source_head_sha and source_run_attempt"
        )
    builder_command = (
        "python3 scripts/check_extended_platform_builder.py \\\n"
        f"            --target {target} \\\n"
        '            --release-tag "${{ inputs.release_tag }}" \\\n'
        '            --workflow-run-url "${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}" \\\n'
        '            --workflow-run-attempt "${{ github.run_attempt }}" \\\n'
        '            --source-head-sha "${{ github.sha }}" \\\n'
        f"            --out {evidence_dir}/{builder_identity_name}"
    )
    if builder_command not in block:
        errors.append(
            f"{job} builder identity preflight must bind release_tag, workflow_run_url, "
            "workflow_run_attempt and source_head_sha"
        )
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
        "--out-dir <bundle-dir>",
        "--out-dir bundle",
        "--out-dir linux-evidence-output",
    )
    for stale in stale_paths:
        if stale in block:
            errors.append(f"{job} must use target/release-scoped platform-evidence-staging paths, found {stale}")
    if "softprops/action-gh-release" in block:
        errors.append(f"{job} must not publish GitHub releases")
    if re.search(r"(?m)^\s+[A-Za-z0-9_-]+:\s+write\s*$", block):
        errors.append(f"{job} must not request write permissions")
    return errors


def check_ordered_snippets(
    block: str,
    ordered_snippets: tuple[tuple[str, str], ...],
    *,
    job: str,
) -> list[str]:
    errors: list[str] = []
    previous_index = -1
    previous_label = ""
    for label, snippet in ordered_snippets:
        index = block.find(snippet)
        if index < 0:
            continue
        if index < previous_index:
            errors.append(
                f"{job} protected evidence step order is invalid: {label} must run after {previous_label}"
            )
        previous_index = max(previous_index, index)
        previous_label = label
    return errors


def check_run_shell_safety(block: str, *, job: str) -> list[str]:
    errors: list[str] = []
    run_blocks = re.finditer(r"(?m)^        run: \|\n((?:^          [^\n]*(?:\n|$))+)", block)
    for index, match in enumerate(run_blocks, start=1):
        script_lines = [line[10:] for line in match.group(1).splitlines() if line.startswith("          ")]
        first_command = next((line.strip() for line in script_lines if line.strip()), "")
        if first_command != "set -euo pipefail":
            errors.append(
                f"{job} run step {index} missing strict shell safety: set -euo pipefail"
            )
    return errors


def check_top_level_concurrency(workflow: str, *, workflow_label: str, group: str) -> list[str]:
    block = workflow_top_level_block(workflow, "concurrency")
    if not block:
        return [f"{workflow_label} workflow missing top-level concurrency gate: concurrency:"]
    errors: list[str] = []
    required_snippets = {
        f"group: {group}": "target/release-scoped concurrency group",
        "cancel-in-progress: false": "non-cancelling evidence concurrency",
    }
    for snippet, label in required_snippets.items():
        if snippet not in block:
            errors.append(f"{workflow_label} workflow missing {label}: {snippet}")
    return errors


def check_top_level_run_defaults(workflow: str, *, workflow_label: str) -> list[str]:
    block = workflow_top_level_block(workflow, "defaults")
    if not block:
        return [f"{workflow_label} workflow missing top-level Bash run default: defaults:"]
    if "  run:\n    shell: bash" not in block:
        return [f"{workflow_label} workflow must force Bash for multiline Linux proof steps"]
    return []


def check_workflow_script_dependencies(dependencies: tuple[Path, ...] | None = None) -> list[str]:
    dependencies = WORKFLOW_SCRIPT_DEPENDENCIES if dependencies is None else dependencies
    label = "extended platform evidence workflow script dependency"
    errors: list[str] = []
    for relative_path in dependencies:
        dependency = ROOT / relative_path
        relative = relative_path.as_posix()
        if not dependency.exists():
            errors.append(f"{label} must exist in checkout at {relative}")
            continue
        if dependency.is_symlink():
            errors.append(f"{label} must not be a symlink: {relative}")
        if not dependency.is_file():
            errors.append(f"{label} must be a file: {relative}")
        if not is_git_tracked(relative_path):
            errors.append(f"{label} must be tracked by git: {relative}")
    return errors


def workflow_script_dependencies(workflow: str) -> tuple[Path, ...]:
    discovered = {Path(reference) for reference in WORKFLOW_SCRIPT_REFERENCE_RE.findall(workflow)}
    required = set(WORKFLOW_SCRIPT_DEPENDENCIES)
    return tuple(sorted(discovered | required, key=lambda path: path.as_posix()))


def is_git_tracked(relative: Path) -> bool:
    result = subprocess.run(
        ["git", "ls-files", "--error-unmatch", "--", relative.as_posix()],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return result.returncode == 0


def workflow_top_level_block(workflow: str, key: str) -> str:
    match = re.search(rf"(?ms)^{re.escape(key)}:\n(.*?)(?=^[A-Za-z0-9_-]+:|\Z)", workflow)
    return match.group(0) if match else ""


def workflow_job_block(workflow: str, job: str) -> str:
    match = re.search(rf"(?ms)^  {re.escape(job)}:\n(.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)", workflow)
    return match.group(1) if match else ""


def check_checkout_step(block: str, *, job: str) -> list[str]:
    checkout = workflow_step_block(block, "uses: actions/checkout@v6")
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


if __name__ == "__main__":
    raise SystemExit(main())

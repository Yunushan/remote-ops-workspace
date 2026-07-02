from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "xp-native-evidence.yml"
WAIT_HELPER_RELATIVE = Path("scripts") / "wait_for_xp_native_evidence_inputs.py"
WAIT_HELPER_PATH = ROOT / WAIT_HELPER_RELATIVE
WORKFLOW_SCRIPT_DEPENDENCIES = (
    Path("scripts") / "check_xp_native_evidence_dispatch_inputs.py",
    Path("scripts") / "wait_for_xp_native_evidence_inputs.py",
    Path("scripts") / "check_xp_native_evidence.py",
    Path("scripts") / "check_platform_promotion_artifacts.py",
    Path("scripts") / "check_platform_goal_local_evidence.py",
    Path("scripts") / "make_platform_verified_evidence_record.py",
    Path("scripts") / "make_xp_native_evidence_bundle.py",
    Path("scripts") / "finalize_platform_verified_evidence_record.py",
    Path("scripts") / "stage_xp_native_evidence_upload.py",
    Path("scripts") / "xp_smoke_runner.cmd",
)
WORKFLOW_SCRIPT_REFERENCE_RE = re.compile(r"scripts/[A-Za-z0-9_./-]+\.(?:cmd|py|sh)")
GHA_TARGET = "${{ inputs.target }}"
GHA_RELEASE_TAG = "${{ inputs.release_tag }}"
GHA_ASSETS_DIR = "${{ inputs.assets_dir }}"
XP_EVIDENCE_OUTPUT_DIR = f"xp-evidence-output/{GHA_TARGET}/{GHA_RELEASE_TAG}"
XP_EVIDENCE_UPLOAD_DIR = f"platform-evidence-upload/{GHA_TARGET}/{GHA_RELEASE_TAG}"


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
    errors.extend(check_github_expression_delimiters(text))
    errors.extend(check_top_level_policy(text))
    errors.extend(check_xp_job(text))
    errors.extend(check_required_helper_files())
    errors.extend(check_workflow_script_dependencies(workflow_script_dependencies(text)))
    return errors


def check_github_expression_delimiters(workflow: str) -> list[str]:
    errors: list[str] = []
    for line_number, line in enumerate(workflow.splitlines(), start=1):
        if line.count("${{") != line.count("}}"):
            errors.append(
                "XP native evidence workflow has unbalanced GitHub expression "
                f"delimiters on line {line_number}: {line.strip()}"
            )
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
    errors.extend(
        check_top_level_concurrency(
            workflow,
            workflow_label="XP native evidence",
            group="xp-native-evidence-${{ inputs.target }}-${{ inputs.release_tag }}",
        )
    )
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
        "clean: true": "self-hosted checkout workspace cleanup",
        "uses: actions/setup-python@v6": "Python setup",
        'python-version: "3.12"': "Python version pin",
        "XP evidence collector validates staged proof captured on real Windows XP hosts; run scripts/xp_smoke_runner.cmd after this workflow starts so smoke proof binds the printed source run metadata.": "XP host versus collector boundary",
        f"Path('{XP_EVIDENCE_OUTPUT_DIR}').mkdir(parents=True, exist_ok=True)": "target/release scoped XP evidence output directory creation",
        'python scripts/check_xp_native_evidence_dispatch_inputs.py --target "${{ inputs.target }}" --release-tag "${{ inputs.release_tag }}" --release-asset-base-url "${{ inputs.release_asset_base_url }}" --workflow-run-url "${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}" --source-head-sha "${{ github.sha }}" --source-run-attempt "${{ github.run_attempt }}" --assets-dir "${{ inputs.assets_dir }}" --evidence-file "${{ inputs.evidence_file }}" --evidence-dir "${{ inputs.evidence_dir }}"': "XP dispatch input preflight",
        "XP evidence source workflow run: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}": "printed XP source workflow run metadata",
        "XP evidence source head SHA: ${{ github.sha }}": "printed XP source head SHA metadata",
        "XP evidence source run attempt: ${{ github.run_attempt }}": "printed XP source run-attempt metadata",
        'python scripts/wait_for_xp_native_evidence_inputs.py --assets-dir "${{ inputs.assets_dir }}" --evidence-file "${{ inputs.evidence_file }}" --evidence-dir "${{ inputs.evidence_dir }}" --timeout-seconds 2700 --poll-seconds 10 --stable-polls 2': "bounded stable wait for staged XP evidence inputs",
        'python scripts/check_xp_native_evidence.py --evidence "${{ inputs.evidence_file }}" --assets-dir "${{ inputs.assets_dir }}" --evidence-dir "${{ inputs.evidence_dir }}"': "XP evidence validation",
        'python scripts/check_platform_promotion_artifacts.py --target "${{ inputs.target }}" --assets-dir "${{ inputs.assets_dir }}" --tag "${{ inputs.release_tag }}" --strict': "XP promotion artifact validation",
        'python scripts/check_platform_goal_local_evidence.py --root . --release-tag "${{ inputs.release_tag }}" --target "${{ inputs.target }}" --assets-dir "${{ inputs.assets_dir }}" --xp-evidence "${{ inputs.evidence_file }}" --xp-evidence-dir "${{ inputs.evidence_dir }}" --xp-source-workflow-run-url "${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}" --xp-source-head-sha "${{ github.sha }}" --xp-source-run-attempt "${{ github.run_attempt }}"': "XP local protected goal evidence preflight",
        'python scripts/make_platform_verified_evidence_record.py --target "${{ inputs.target }}"': "accepted-evidence candidate generation",
        '--release-asset-base-url "${{ inputs.release_asset_base_url }}"': "release asset URL input binding",
        '--release-source-workflow-run-url "${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}"': "release source workflow run binding",
        '--release-source-artifact-name "xp-native-evidence-${{ inputs.target }}-${{ inputs.release_tag }}"': "target/release scoped source artifact name",
        '--release-source-head-sha "${{ github.sha }}"': "release source head SHA binding",
        '--source-head-sha "${{ github.sha }}"': "XP dispatch source head SHA binding",
        '--source-run-attempt "${{ github.run_attempt }}"': "XP dispatch source run-attempt binding",
        '--xp-source-run-attempt "${{ github.run_attempt }}"': "XP local source run-attempt binding",
        '--release-source-run-attempt "${{ github.run_attempt }}"': "release source run-attempt binding",
        "--local-evidence-root .": "candidate local evidence root binding",
        '--xp-evidence "${{ inputs.evidence_file }}"': "XP evidence input binding",
        '--xp-evidence-dir "${{ inputs.evidence_dir }}"': "XP evidence directory binding",
        f'--out "{XP_EVIDENCE_OUTPUT_DIR}/platform-verified-evidence-{GHA_TARGET}.json"': "target/release scoped candidate evidence output",
        'python scripts/make_xp_native_evidence_bundle.py --target "${{ inputs.target }}"': "review evidence bundle generation",
        f'--candidate-record "{XP_EVIDENCE_OUTPUT_DIR}/platform-verified-evidence-{GHA_TARGET}.json"': "target/release scoped candidate record bundle input",
        f'--out-dir "{XP_EVIDENCE_OUTPUT_DIR}"': "target/release scoped review bundle output directory",
        f'python scripts/finalize_platform_verified_evidence_record.py --candidate-record "{XP_EVIDENCE_OUTPUT_DIR}/platform-verified-evidence-{GHA_TARGET}.json"': "finalized evidence record generation",
        f'--bundle-manifest "{XP_EVIDENCE_OUTPUT_DIR}/xp-native-evidence-bundle-{GHA_TARGET}-{GHA_RELEASE_TAG}.json"': "target/release scoped finalized evidence manifest binding",
        f'--bundle-archive "{XP_EVIDENCE_OUTPUT_DIR}/xp-native-evidence-bundle-{GHA_TARGET}-{GHA_RELEASE_TAG}.zip"': "target/release scoped finalized evidence archive binding",
        f'--bundle-sha256s "{XP_EVIDENCE_OUTPUT_DIR}/xp-native-evidence-bundle-{GHA_TARGET}-{GHA_RELEASE_TAG}-SHA256SUMS.txt"': "target/release scoped finalized evidence checksum sidecar binding",
        f'--out "{XP_EVIDENCE_OUTPUT_DIR}/platform-verified-evidence-{GHA_TARGET}-final.json"': "target/release scoped finalized evidence output",
        f'python scripts/stage_xp_native_evidence_upload.py --target "{GHA_TARGET}" --release-tag "{GHA_RELEASE_TAG}" --assets-dir "{GHA_ASSETS_DIR}" --evidence-output-dir "{XP_EVIDENCE_OUTPUT_DIR}" --out-dir "{XP_EVIDENCE_UPLOAD_DIR}" --force': "target/release scoped XP upload staging",
        "actions/upload-artifact@v7": "evidence artifact upload",
        "name: xp-native-evidence-${{ inputs.target }}-${{ inputs.release_tag }}": "target/release scoped uploaded artifact",
        f"path: {XP_EVIDENCE_UPLOAD_DIR}/*": "target/release scoped staged upload path",
        "if-no-files-found: error": "missing evidence artifact failure",
        "include-hidden-files: false": "hidden file exclusion for evidence artifact upload",
        "retention-days: 90": "evidence artifact retention window",
    }
    for snippet, label in required_snippets.items():
        if snippet not in block:
            errors.append(f"xp-native-evidence job missing {label}: {snippet}")
    errors.extend(
        check_ordered_snippets(
            block,
            (
                ("dispatch input preflight", "      - name: Validate XP evidence dispatch inputs"),
                ("source metadata print", "      - name: Print XP evidence capture source metadata"),
                ("staged input wait", "      - name: Wait for staged XP evidence inputs"),
                ("XP native evidence validation", "      - name: Validate XP native evidence"),
                ("XP promotion artifact validation", "      - name: Validate XP promotion artifacts"),
                ("local protected-goal preflight", "      - name: Preflight XP local platform goal evidence"),
                ("accepted-evidence candidate generation", "      - name: Generate XP accepted-evidence candidate"),
                ("review evidence bundle generation", "      - name: Package XP review evidence bundle"),
                ("finalized evidence record generation", "      - name: Finalize XP accepted-evidence candidate"),
                ("scoped XP upload staging", "      - name: Stage scoped XP evidence upload"),
                ("evidence artifact upload", "      - uses: actions/upload-artifact@v7"),
            ),
            job="xp-native-evidence",
        )
    )
    errors.extend(check_checkout_step(block, job="xp-native-evidence"))
    if "${{ inputs.assets_dir }}/*" in block:
        errors.append("xp-native-evidence job must not upload raw operator-supplied assets_dir wildcard")
    if re.search(r"(?m)^\s+xp-evidence-output/\*", block):
        errors.append("xp-native-evidence job must upload scoped staged files, not raw xp-evidence-output wildcard")
    generic_output_snippets = (
        "Path('xp-evidence-output').mkdir",
        "xp-evidence-output/platform-verified-evidence-",
        "--out-dir xp-evidence-output",
        "--evidence-output-dir xp-evidence-output",
    )
    for snippet in generic_output_snippets:
        if snippet in block:
            errors.append(
                "xp-native-evidence job must use target/release scoped XP evidence output paths, "
                f"not generic {snippet}"
            )
    if "softprops/action-gh-release" in block:
        errors.append("xp-native-evidence job must not publish GitHub releases")
    if re.search(r"(?m)^\s+[A-Za-z0-9_-]+:\s+write\s*$", block):
        errors.append("xp-native-evidence job must not request write permissions")
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


def check_required_helper_files() -> list[str]:
    errors: list[str] = []
    helper = WAIT_HELPER_PATH
    label = "XP staged evidence wait helper"
    relative = WAIT_HELPER_RELATIVE.as_posix()
    if not helper.exists():
        return [f"{label} must exist in checkout at {relative}"]
    if helper.is_symlink():
        errors.append(f"{label} must not be a symlink: {relative}")
    if not helper.is_file():
        errors.append(f"{label} must be a file: {relative}")
    if not is_git_tracked(WAIT_HELPER_RELATIVE):
        errors.append(f"{label} must be tracked by git: {relative}")
    return errors


def check_workflow_script_dependencies(dependencies: tuple[Path, ...] | None = None) -> list[str]:
    dependencies = WORKFLOW_SCRIPT_DEPENDENCIES if dependencies is None else dependencies
    label = "XP native evidence workflow script dependency"
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
                f"{job} job protected evidence step order is invalid: "
                f"{label} must run after {previous_label}"
            )
        previous_index = max(previous_index, index)
        previous_label = label
    return errors


def workflow_step_block(job_block: str, marker: str) -> str:
    pattern = rf"(?ms)^      - {re.escape(marker)}\n(.*?)(?=^      - |\Z)"
    match = re.search(pattern, job_block)
    return match.group(0) if match else ""


if __name__ == "__main__":
    raise SystemExit(main())

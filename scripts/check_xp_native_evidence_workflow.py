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
GITHUB_INPUT_EXPRESSION_RE = re.compile(
    r"\$\{\{\s*inputs\.([A-Za-z0-9_-]+)\s*\}\}"
)
FREE_FORM_DISPATCH_INPUTS = frozenset(
    {"release_tag", "release_asset_base_url", "assets_dir", "evidence_file", "evidence_dir"}
)
PS_TARGET = "$env:EVIDENCE_TARGET"
PS_RELEASE_TAG = "$env:RELEASE_TAG"
PS_ASSETS_DIR = "$env:ASSETS_DIR"
PS_TARGET_EXPR = "$($env:EVIDENCE_TARGET)"
PS_RELEASE_TAG_EXPR = "$($env:RELEASE_TAG)"
XP_EVIDENCE_OUTPUT_DIR = "xp-evidence-output/$($env:EVIDENCE_TARGET)/$($env:RELEASE_TAG)"
XP_EVIDENCE_UPLOAD_DIR = "platform-evidence-upload/$($env:EVIDENCE_TARGET)/$($env:RELEASE_TAG)"
ACTION_XP_EVIDENCE_UPLOAD_DIR = (
    "platform-evidence-upload/${{ inputs.target }}/${{ inputs.release_tag }}"
)


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
    errors.extend(
        check_run_dispatch_input_interpolation(
            text,
            workflow_label="XP native evidence",
            free_form_inputs=FREE_FORM_DISPATCH_INPUTS,
        )
    )
    errors.extend(check_top_level_policy(text))
    errors.extend(check_runner_readiness_job(text))
    errors.extend(check_unavailable_runner_job(text))
    errors.extend(check_xp_job(text))
    errors.extend(check_required_helper_files())
    errors.extend(check_workflow_script_dependencies(workflow_script_dependencies(text)))
    return errors


def check_github_expression_delimiters(workflow: str) -> list[str]:
    errors: list[str] = []
    for line_number, line in enumerate(workflow.splitlines(), start=1):
        if github_expression_delimiters_unbalanced(line):
            errors.append(
                "XP native evidence workflow has unbalanced GitHub expression "
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


def check_run_dispatch_input_interpolation(
    workflow: str,
    *,
    workflow_label: str,
    free_form_inputs: frozenset[str],
) -> list[str]:
    """Reject GitHub input expressions inside shell-controlled ``run`` bodies."""

    lines = workflow.splitlines()
    errors: list[str] = []
    for index, line in enumerate(lines):
        match = re.match(
            r"^(?P<indent>\s*)(?P<list_item>-\s+)?run:\s*(?P<body>.*)$",
            line,
        )
        if match is None:
            continue
        candidates = [(index + 1, match.group("body"))]
        base_indent = len(match.group("indent")) + len(match.group("list_item") or "")
        cursor = index + 1
        while cursor < len(lines):
            candidate = lines[cursor]
            if candidate.strip() and len(candidate) - len(candidate.lstrip()) <= base_indent:
                break
            candidates.append((cursor + 1, candidate))
            cursor += 1
        for line_number, candidate in candidates:
            for input_name in GITHUB_INPUT_EXPRESSION_RE.findall(candidate):
                if input_name in free_form_inputs:
                    errors.append(
                        f"{workflow_label} run script must not directly interpolate free-form "
                        f"workflow_dispatch input {input_name!r} on line {line_number}; bind it through env"
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


def check_runner_readiness_job(workflow: str) -> list[str]:
    job = "evidence-runner-readiness"
    block = workflow_job_block(workflow, job)
    if not block:
        return [f"XP native evidence workflow missing job: {job}"]
    required_snippets = {
        "runs-on: ubuntu-latest": "hosted runner for readiness preflight",
        "timeout-minutes: 5": "bounded runner readiness preflight timeout",
        "outputs:\n      ready: ${{ steps.runner-readiness.outputs.ready }}": "runner readiness output binding",
        "permissions:\n      actions: read\n      contents: read": "read-only runner inventory permissions",
        "uses: actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10 # v6": "readiness preflight checkout",
        "persist-credentials: false": "readiness checkout credential isolation",
        "clean: true": "readiness checkout workspace cleanup",
        "uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1 # v6": "readiness Python setup",
        'python-version: "3.12"': "readiness Python version pin",
        "GH_TOKEN: ${{ github.token }}": "GitHub token binding for runner inventory",
        "python scripts/check_platform_evidence_runner_readiness.py \\\n            --repository \"${{ github.repository }}\" \\\n            --target \"${{ inputs.target }}\" \\\n            --require-idle \\\n            --allow-unavailable \\\n            --github-output \"$GITHUB_OUTPUT\"": "target-specific idle runner readiness check",
    }
    errors: list[str] = []
    for snippet, label in required_snippets.items():
        if snippet not in block:
            errors.append(f"{job} missing {label}: {snippet}")
    errors.extend(
        check_ordered_snippets(
            block,
            (
                ("readiness preflight checkout", "      - uses: actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10 # v6"),
                ("readiness Python setup", "      - uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1 # v6"),
                (
                    "target-specific idle runner readiness check",
                    "      - id: runner-readiness\n        name: Check evidence runner availability",
                ),
            ),
            job=job,
        )
    )
    errors.extend(check_checkout_step(block, job=job))
    return errors


def check_unavailable_runner_job(workflow: str) -> list[str]:
    job = "evidence-runner-unavailable"
    block = workflow_job_block(workflow, job)
    if not block:
        return [f"XP native evidence workflow missing job: {job}"]
    required_snippets = {
        "needs: evidence-runner-readiness": "runner readiness dependency",
        "if: ${{ needs.evidence-runner-readiness.result == 'success' && needs.evidence-runner-readiness.outputs.ready != 'true' }}": "non-promotional unavailable-runner condition",
        "runs-on: ubuntu-latest": "hosted reporting runner",
        "timeout-minutes: 5": "bounded unavailable-runner report timeout",
        "permissions:\n      contents: read": "read-only unavailable-runner report permissions",
        "::warning::No idle protected-platform evidence runner": "unavailable-runner warning",
        "strict release promotion remains blocked until accepted evidence exists": "strict promotion boundary",
    }
    errors: list[str] = []
    for snippet, label in required_snippets.items():
        if snippet not in block:
            errors.append(f"{job} missing {label}: {snippet}")
    return errors


def check_xp_job(workflow: str) -> list[str]:
    block = workflow_job_block(workflow, "xp-native-evidence")
    if not block:
        return ["XP native evidence workflow missing job: xp-native-evidence"]
    errors: list[str] = []
    required_snippets = {
        "needs: evidence-runner-readiness": "runner readiness preflight dependency",
        "if: ${{ needs.evidence-runner-readiness.outputs.ready == 'true' }}": "runner readiness target guard",
        "runs-on: [self-hosted, xp-evidence]": "XP evidence self-hosted runner labels",
        "timeout-minutes: 60": "bounded XP evidence job timeout",
        "ASSETS_DIR: ${{ inputs.assets_dir }}": "assets directory environment binding",
        "EVIDENCE_DIR: ${{ inputs.evidence_dir }}": "evidence directory environment binding",
        "EVIDENCE_FILE: ${{ inputs.evidence_file }}": "evidence file environment binding",
        "RELEASE_ASSET_BASE_URL: ${{ inputs.release_asset_base_url }}": "release URL environment binding",
        "RELEASE_TAG: ${{ inputs.release_tag }}": "release tag environment binding",
        "WORKFLOW_REF_NAME: ${{ github.ref_name }}": "workflow ref environment binding",
        "WORKFLOW_RUN_URL: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}": "workflow URL environment binding",
        "uses: actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10 # v6": "repository checkout",
        "persist-credentials: false": "checkout credential isolation",
        "clean: true": "self-hosted checkout workspace cleanup",
        "uses: actions/setup-python@ece7cb06caefa5fff74198d8649806c4678c61a1 # v6": "Python setup",
        'python-version: "3.12"': "Python version pin",
        "XP evidence collector validates staged proof captured on real Windows XP hosts; run scripts/xp_smoke_runner.cmd after this workflow starts so smoke proof binds the printed source run metadata.": "XP host versus collector boundary",
        f'Path(sys.argv[1]).mkdir(parents=True, exist_ok=True)" "{XP_EVIDENCE_OUTPUT_DIR}"': "target/release scoped XP evidence output directory creation",
        'python scripts/check_xp_native_evidence_dispatch_inputs.py --target "$env:EVIDENCE_TARGET" --release-tag "$env:RELEASE_TAG" --release-asset-base-url "$env:RELEASE_ASSET_BASE_URL" --workflow-run-url "$env:WORKFLOW_RUN_URL" --workflow-ref-name "$env:WORKFLOW_REF_NAME" --source-head-sha "$env:SOURCE_HEAD_SHA" --source-run-attempt "$env:SOURCE_RUN_ATTEMPT" --assets-dir "$env:ASSETS_DIR" --evidence-file "$env:EVIDENCE_FILE" --evidence-dir "$env:EVIDENCE_DIR"': "XP dispatch input preflight",
        "XP evidence source workflow run: $env:WORKFLOW_RUN_URL": "printed XP source workflow run metadata",
        "XP evidence source head SHA: $env:SOURCE_HEAD_SHA": "printed XP source head SHA metadata",
        "XP evidence source run attempt: $env:SOURCE_RUN_ATTEMPT": "printed XP source run-attempt metadata",
        'python scripts/wait_for_xp_native_evidence_inputs.py --assets-dir "$env:ASSETS_DIR" --evidence-file "$env:EVIDENCE_FILE" --evidence-dir "$env:EVIDENCE_DIR" --timeout-seconds 2700 --poll-seconds 10 --stable-polls 2': "bounded stable wait for staged XP evidence inputs",
        'python scripts/check_xp_native_evidence.py --evidence "$env:EVIDENCE_FILE" --assets-dir "$env:ASSETS_DIR" --evidence-dir "$env:EVIDENCE_DIR"': "XP evidence validation",
        'python scripts/check_platform_promotion_artifacts.py --target "$env:EVIDENCE_TARGET" --assets-dir "$env:ASSETS_DIR" --tag "$env:RELEASE_TAG" --strict': "XP promotion artifact validation",
        'python scripts/check_platform_goal_local_evidence.py --root . --release-tag "$env:RELEASE_TAG" --target "$env:EVIDENCE_TARGET" --assets-dir "$env:ASSETS_DIR" --repository "$env:REPOSITORY" --xp-evidence "$env:EVIDENCE_FILE" --xp-evidence-dir "$env:EVIDENCE_DIR" --xp-source-workflow-run-url "$env:WORKFLOW_RUN_URL" --xp-source-head-sha "$env:SOURCE_HEAD_SHA" --xp-source-run-attempt "$env:SOURCE_RUN_ATTEMPT"': "XP local protected goal evidence preflight",
        'python scripts/make_platform_verified_evidence_record.py --target "$env:EVIDENCE_TARGET"': "accepted-evidence candidate generation",
        '--release-asset-base-url "$env:RELEASE_ASSET_BASE_URL"': "release asset URL input binding",
        '--release-source-workflow-run-url "$env:WORKFLOW_RUN_URL"': "release source workflow run binding",
        f'--release-source-artifact-name "xp-native-evidence-{PS_TARGET_EXPR}-{PS_RELEASE_TAG_EXPR}"': "target/release scoped source artifact name",
        '--release-source-head-sha "$env:SOURCE_HEAD_SHA"': "release source head SHA binding",
        '--source-head-sha "$env:SOURCE_HEAD_SHA"': "XP dispatch source head SHA binding",
        '--source-run-attempt "$env:SOURCE_RUN_ATTEMPT"': "XP dispatch source run-attempt binding",
        '--xp-source-run-attempt "$env:SOURCE_RUN_ATTEMPT"': "XP local source run-attempt binding",
        '--release-source-run-attempt "$env:SOURCE_RUN_ATTEMPT"': "release source run-attempt binding",
        "--local-evidence-root .": "candidate local evidence root binding",
        f'--staged-upload-out-dir "{XP_EVIDENCE_UPLOAD_DIR}"': "candidate staged upload output binding",
        '--xp-evidence "$env:EVIDENCE_FILE"': "XP evidence input binding",
        '--xp-evidence-dir "$env:EVIDENCE_DIR"': "XP evidence directory binding",
        f'--xp-evidence-output-dir "{XP_EVIDENCE_OUTPUT_DIR}"': "candidate XP evidence output binding",
        f'--out "{XP_EVIDENCE_OUTPUT_DIR}/platform-verified-evidence-{PS_TARGET_EXPR}.json"': "target/release scoped candidate evidence output",
        'python scripts/make_xp_native_evidence_bundle.py --target "$env:EVIDENCE_TARGET"': "review evidence bundle generation",
        f'--candidate-record "{XP_EVIDENCE_OUTPUT_DIR}/platform-verified-evidence-{PS_TARGET_EXPR}.json"': "target/release scoped candidate record bundle input",
        f'--out-dir "{XP_EVIDENCE_OUTPUT_DIR}"': "target/release scoped review bundle output directory",
        f'python scripts/finalize_platform_verified_evidence_record.py --candidate-record "{XP_EVIDENCE_OUTPUT_DIR}/platform-verified-evidence-{PS_TARGET_EXPR}.json"': "finalized evidence record generation",
        f'--bundle-manifest "{XP_EVIDENCE_OUTPUT_DIR}/xp-native-evidence-bundle-{PS_TARGET_EXPR}-{PS_RELEASE_TAG_EXPR}.json"': "target/release scoped finalized evidence manifest binding",
        f'--bundle-archive "{XP_EVIDENCE_OUTPUT_DIR}/xp-native-evidence-bundle-{PS_TARGET_EXPR}-{PS_RELEASE_TAG_EXPR}.zip"': "target/release scoped finalized evidence archive binding",
        f'--bundle-sha256s "{XP_EVIDENCE_OUTPUT_DIR}/xp-native-evidence-bundle-{PS_TARGET_EXPR}-{PS_RELEASE_TAG_EXPR}-SHA256SUMS.txt"': "target/release scoped finalized evidence checksum sidecar binding",
        f'--out "{XP_EVIDENCE_OUTPUT_DIR}/platform-verified-evidence-{PS_TARGET_EXPR}-final.json"': "target/release scoped finalized evidence output",
        f'python scripts/stage_xp_native_evidence_upload.py --target "{PS_TARGET}" --release-tag "{PS_RELEASE_TAG}" --assets-dir "{PS_ASSETS_DIR}" --evidence-output-dir "{XP_EVIDENCE_OUTPUT_DIR}" --out-dir "{XP_EVIDENCE_UPLOAD_DIR}" --force': "target/release scoped XP upload staging",
        "actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7": "evidence artifact upload",
        "name: xp-native-evidence-${{ inputs.target }}-${{ inputs.release_tag }}": "target/release scoped uploaded artifact",
        f"path: {ACTION_XP_EVIDENCE_UPLOAD_DIR}/*": "target/release scoped staged upload path",
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
                (
                    "target/release scoped XP evidence output directory creation",
                    "      - name: Create XP evidence output directory",
                ),
                ("source metadata print", "      - name: Print XP evidence capture source metadata"),
                ("staged input wait", "      - name: Wait for staged XP evidence inputs"),
                ("XP native evidence validation", "      - name: Validate XP native evidence"),
                ("XP promotion artifact validation", "      - name: Validate XP promotion artifacts"),
                ("local protected-goal preflight", "      - name: Preflight XP local platform goal evidence"),
                ("accepted-evidence candidate generation", "      - name: Generate XP accepted-evidence candidate"),
                ("review evidence bundle generation", "      - name: Package XP review evidence bundle"),
                ("finalized evidence record generation", "      - name: Finalize XP accepted-evidence candidate"),
                ("scoped XP upload staging", "      - name: Stage scoped XP evidence upload"),
                ("evidence artifact upload", "      - uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7"),
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
    checkout = workflow_step_block(block, "uses: actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10 # v6")
    if not checkout:
        return [f"{job} missing repository checkout: uses: actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10 # v6"]
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

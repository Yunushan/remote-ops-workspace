from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "extended-platform-evidence.yml"
LINUX_CAPTURE_PATH = Path("scripts") / "capture_linux_platform_evidence.sh"
NATIVE_LOCK_DIR = "requirements-locks/protected-linux"
NATIVE_LINUX_ARCHES = {
    "linux-i386": ("i386", "i686", "i686"),
    "linux-armhf": ("armhf", "armv7hl", "armhf"),
}
WORKFLOW_SCRIPT_DEPENDENCIES = (
    LINUX_CAPTURE_PATH,
    Path("scripts") / "check_extended_platform_dispatch_inputs.py",
    Path("scripts") / "check_extended_platform_builder.py",
    Path("scripts") / "check_linux_native_elf.py",
    Path("scripts") / "check_protected_linux_build_inputs.py",
    Path("scripts") / "prepare_protected_linux_cargo.py",
    Path("scripts") / "protected_linux_cargo.sh",
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
GITHUB_INPUT_EXPRESSION_RE = re.compile(
    r"\$\{\{\s*inputs\.([A-Za-z0-9_-]+)\s*\}\}"
)
FREE_FORM_DISPATCH_INPUTS = frozenset({"release_tag", "release_asset_base_url"})


def main() -> int:
    errors = check_extended_platform_evidence()
    if errors:
        for error in errors:
            print(f"extended platform evidence: {error}", file=sys.stderr)
        return 1
    print("extended platform evidence workflow passed")
    return 0


def check_extended_platform_evidence(
    workflow: str | None = None, *, native_capture: str | None = None,
) -> list[str]:
    text = workflow if workflow is not None else WORKFLOW_PATH.read_text(encoding="utf-8")
    errors: list[str] = []
    errors.extend(check_github_expression_delimiters(text))
    errors.extend(
        check_run_dispatch_input_interpolation(
            text,
            workflow_label="extended platform evidence",
            free_form_inputs=FREE_FORM_DISPATCH_INPUTS,
        )
    )
    errors.extend(check_top_level_policy(text))
    errors.extend(check_runner_readiness_job(text))
    errors.extend(check_unavailable_runner_job(text))
    capture_path = ROOT / LINUX_CAPTURE_PATH
    capture = native_capture if native_capture is not None else (
        capture_path.read_text(encoding="utf-8") if capture_path.is_file() else ""
    )
    for target in NATIVE_LINUX_ARCHES:
        errors.extend(check_linux_job(text, target=target))
        errors.extend(check_native_capture(capture, target))
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


def check_runner_readiness_job(workflow: str) -> list[str]:
    job = "evidence-runner-readiness"
    block = workflow_job_block(workflow, job)
    if not block:
        return [f"extended platform evidence workflow missing job: {job}"]
    required_snippets = {
        "runs-on: ubuntu-latest": "hosted runner for readiness preflight",
        "timeout-minutes: 5": "bounded runner readiness preflight timeout",
        "environment: platform-evidence": "tag-restricted runner inventory environment",
        "outputs:\n      ready: ${{ steps.runner-readiness.outputs.ready }}": "runner readiness output binding",
        "permissions:\n      contents: read": "read-only workflow checkout permissions",
        "uses: actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10 # v6": "readiness preflight checkout",
        "persist-credentials: false": "readiness checkout credential isolation",
        "clean: true": "readiness checkout workspace cleanup",
        "uses: actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0 # v7.1.0": "readiness Python setup",
        'python-version: "3.12"': "readiness Python version pin",
        "GH_TOKEN: ${{ secrets.ROW_PLATFORM_RUNNER_INVENTORY_TOKEN }}": "Administration read token for runner inventory",
        "RELEASE_TAG: ${{ inputs.release_tag }}": "runner inventory release tag binding",
        'test "$GITHUB_REF" = "refs/tags/$RELEASE_TAG"': "exact release tag dispatch guard",
        'if [[ -z "$GH_TOKEN" ]]; then': "missing inventory token guard",
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
                ("readiness Python setup", "      - uses: actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0 # v7.1.0"),
                (
                    "target-specific idle runner readiness check",
                    "      - id: runner-readiness\n        name: Check evidence runner availability",
                ),
            ),
            job=job,
        )
    )
    errors.extend(check_checkout_step(block, job=job))
    source = workflow_step_block(block, "name: Verify protected evidence source")
    required_source = (
        '        env:\n'
        '          DEFAULT_BRANCH: ${{ github.event.repository.default_branch }}\n'
        '          RELEASE_TAG: ${{ inputs.release_tag }}\n'
        '        run: |\n'
        '          set -euo pipefail\n'
        '          [[ "$RELEASE_TAG" =~ ^v[0-9]+\\.[0-9]+\\.[0-9]+$ ]]\n'
        '          test "$GITHUB_REF" = "refs/tags/$RELEASE_TAG"\n'
        '          test "$(git rev-parse HEAD)" = "$GITHUB_SHA"\n'
        '          test "$(git rev-parse --verify "refs/tags/${RELEASE_TAG}^{commit}")" = "$GITHUB_SHA"\n'
        '          git check-ref-format --branch "$DEFAULT_BRANCH" >/dev/null\n'
        '          git fetch --no-tags origin "refs/heads/$DEFAULT_BRANCH:refs/remotes/origin/$DEFAULT_BRANCH"\n'
        '          git merge-base --is-ancestor "$GITHUB_SHA" "refs/remotes/origin/$DEFAULT_BRANCH"\n'
    )
    if (
        not source or source.split("\n", 1)[1] != required_source
        or "          fetch-depth: 0\n" not in workflow_step_block(
            block, "uses: actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10 # v6"
        )
        or not 0 <= block.find(source) < block.find("      - id: runner-readiness")
    ):
        errors.append(f"{job} must verify the tagged commit is on the default branch before runner discovery")
    return errors


def check_unavailable_runner_job(workflow: str) -> list[str]:
    job = "evidence-runner-unavailable"
    block = workflow_job_block(workflow, job)
    if not block:
        return [f"extended platform evidence workflow missing job: {job}"]
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


def check_linux_job(workflow: str, *, target: str) -> list[str]:
    job = f"{target}-native-evidence"
    arch = target.removeprefix("linux-")
    step_prefix = f"Linux {arch}"
    block = workflow_job_block(workflow, job)
    if not block:
        return [f"extended platform evidence workflow missing job: {job}"]
    record_name = f"platform-verified-evidence-{target}.json"
    builder_identity_name = f"builder-identity-{target}.json"
    smoke_name = f"native-smoke-{target}.log"
    release_dir = f"platform-evidence-staging/{target}/${{RELEASE_TAG}}"
    assets_dir = f"{release_dir}/artifacts"
    evidence_dir = release_dir
    upload_dir = f"platform-evidence-upload/{target}/${{RELEASE_TAG}}"
    source_artifact_name = f"extended-linux-evidence-{target}-${{RELEASE_TAG}}"
    action_upload_dir = f"platform-evidence-upload/{target}/${{{{ inputs.release_tag }}}}"
    action_source_artifact_name = f"extended-linux-evidence-{target}-${{{{ inputs.release_tag }}}}"
    stage_upload_snippet = (
        "python scripts/stage_extended_linux_evidence_upload.py \\\n"
        f"            --target {target} \\\n"
        '            --release-tag "$RELEASE_TAG" \\\n'
        f'            --source-dir "{assets_dir}" \\\n'
        f'            --out-dir "{upload_dir}" \\\n'
        "            --force"
    )
    local_preflight_snippet = (
        "python scripts/check_platform_goal_local_evidence.py \\\n"
        "            --root platform-evidence-staging \\\n"
        '            --release-tag "$RELEASE_TAG" \\\n'
        f"            --target {target} \\\n"
        f'            --assets-dir "{assets_dir}" \\\n'
        '            --repository "$REPOSITORY" \\\n'
        f'            --linux-builder-evidence "{evidence_dir}/{builder_identity_name}" \\\n'
        f'            --linux-smoke-evidence "{evidence_dir}/{smoke_name}" \\\n'
        '            --linux-workflow-run-url "$WORKFLOW_RUN_URL" \\\n'
        '            --linux-source-head-sha "$SOURCE_HEAD_SHA" \\\n'
        '            --linux-source-run-attempt "$SOURCE_RUN_ATTEMPT"'
    )
    errors: list[str] = []
    required_snippets = {
        "needs: evidence-runner-readiness": "runner readiness preflight dependency",
        f"if: ${{{{ inputs.target == '{target}' && needs.evidence-runner-readiness.outputs.ready == 'true' }}}}": "target guard",
        f"runs-on: [self-hosted, linux, x64, {arch}]": "matching self-hosted runner labels",
        "timeout-minutes: 90": "bounded native evidence job timeout",
        "RELEASE_ASSET_BASE_URL: ${{ inputs.release_asset_base_url }}": "release asset URL environment binding",
        "RELEASE_TAG: ${{ inputs.release_tag }}": "release-tag environment binding for native build script",
        "WORKFLOW_REF_NAME: ${{ github.ref_name }}": "workflow ref environment binding",
        "WORKFLOW_RUN_URL: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}": "workflow URL environment binding",
        "uses: actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10 # v6": "repository checkout",
        "persist-credentials: false": "checkout credential isolation",
        "clean: true": "self-hosted checkout workspace cleanup",
        f"python3 scripts/check_extended_platform_dispatch_inputs.py \\\n            --target {target}": "dispatch input preflight",
        (
            f'python scripts/check_platform_promotion_artifacts.py --target {target} '
            f'--assets-dir "{assets_dir}" --tag "$RELEASE_TAG" --strict'
        ): "strict promotion artifact validation",
        local_preflight_snippet: "local protected goal evidence preflight",
        f"python scripts/make_platform_verified_evidence_record.py \\\n            --target {target}": "accepted-evidence record generation",
        f'--assets-dir "{assets_dir}"': "target-scoped accepted-evidence artifact path",
        '--release-asset-base-url "$RELEASE_ASSET_BASE_URL"': "release asset URL evidence input",
        '--workflow-run-url "$WORKFLOW_RUN_URL"': "workflow run URL evidence",
        '--workflow-ref-name "$WORKFLOW_REF_NAME"': "release-tag workflow ref binding",
        f'--release-source-artifact-name "{source_artifact_name}"': "release source artifact name binding",
        '--release-source-head-sha "$SOURCE_HEAD_SHA"': "release source head SHA evidence",
        '--linux-source-run-attempt "$SOURCE_RUN_ATTEMPT"': "local evidence source run-attempt binding",
        '--release-source-run-attempt "$SOURCE_RUN_ATTEMPT"': "release source run-attempt binding",
        f'--builder-evidence "{evidence_dir}/{builder_identity_name}"': "builder identity evidence input",
        f'--linux-smoke-evidence "{evidence_dir}/{smoke_name}"': "native smoke evidence input",
        "--local-evidence-root platform-evidence-staging": "local evidence preflight root binding",
        f'--staged-upload-out-dir "{upload_dir}"': "candidate staged upload output binding",
        "--runner-label self-hosted": "self-hosted runner-label evidence",
        "--runner-label linux": "linux runner-label evidence",
        f"--runner-label {arch}": "target collector label evidence",
        f'--out "{assets_dir}/{record_name}"': "candidate evidence record output",
        f"python scripts/make_extended_linux_evidence_bundle.py \\\n            --target {target}": "review evidence bundle generation",
        f'--smoke-evidence "{evidence_dir}/{smoke_name}"': "review bundle smoke evidence input",
        f'--runtime-report "{evidence_dir}/candidate-pip-inspect.json"': "review bundle runtime evidence input",
        f'--candidate-record "{assets_dir}/{record_name}"': "candidate record bundle input",
        f'--out-dir "{assets_dir}"': "target/release scoped review bundle output directory",
        f'python scripts/finalize_platform_verified_evidence_record.py \\\n            --candidate-record "{assets_dir}/{record_name}"': "finalized evidence record generation",
        f'--bundle-manifest "{assets_dir}/extended-linux-evidence-bundle-{target}-${{RELEASE_TAG}}.json"': "finalized evidence manifest binding",
        f'--bundle-archive "{assets_dir}/extended-linux-evidence-bundle-{target}-${{RELEASE_TAG}}.zip"': "finalized evidence archive binding",
        f'--bundle-sha256s "{assets_dir}/extended-linux-evidence-bundle-{target}-${{RELEASE_TAG}}-SHA256SUMS.txt"': "finalized evidence checksum sidecar binding",
        f'--out "{assets_dir}/platform-verified-evidence-{target}-final.json"': "finalized evidence record output",
        stage_upload_snippet: "scoped Linux evidence upload staging",
        "actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7": "evidence artifact upload",
        f"name: {action_source_artifact_name}": "target/release-scoped evidence artifact name",
        f"path: {action_upload_dir}/*": "target/release scoped staged upload path",
        "if-no-files-found: error": "missing evidence artifact failure",
        "include-hidden-files: false": "hidden file exclusion for evidence artifact upload",
        "retention-days: 90": "evidence artifact retention window",
    }
    required_snippets.update({
        'uses: actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0 # v7.1.0': "collector Python setup",
        f"with scripts/{LINUX_CAPTURE_PATH.name} {target}.": "native capture instructions",
        '"$RELEASE_TAG" "$RELEASE_ASSET_BASE_URL" "$WORKFLOW_RUN_URL" "$SOURCE_HEAD_SHA" "$SOURCE_RUN_ATTEMPT"':
            "exact run identity printed for the native host",
        '[[ ! -e "$evidence_dir" && ! -L "$evidence_dir" ]]': "fresh collector staging directory",
        "--runner-label x64": "x64 collector runner-label evidence",
    })
    wait_step = (
        f"      - name: Wait for completed {step_prefix} evidence\n"
        "        timeout-minutes: 80\n"
        "        run: |\n"
        "          set -euo pipefail\n"
        f'          while [[ ! -d "platform-evidence-staging/{target}/$RELEASE_TAG/artifacts" ]]; do\n'
        "            sleep 10\n"
        "          done\n"
    )
    if workflow_step_block(block, f"name: Wait for completed {step_prefix} evidence") != wait_step:
        errors.append(f"{job} must wait for staged native evidence before collector validation")
    for snippet, label in required_snippets.items():
        if snippet not in block:
            errors.append(f"{job} missing {label}: {snippet}")
    errors.extend(check_checkout_step(block, job=job))
    errors.extend(check_run_shell_safety(block, job=job))
    errors.extend(
        check_ordered_snippets(
            block,
            (
                ("dispatch input preflight", f"      - name: Validate {step_prefix} evidence dispatch inputs"),
                ("native builder request", f"      - name: Request {step_prefix} evidence from the native builder"),
                ("native evidence collection", f"      - name: Wait for completed {step_prefix} evidence"),
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
                ("evidence artifact upload", "      - uses: actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9 # v7"),
            ),
            job=job,
        )
    )
    dispatch_command = (
        "python3 scripts/check_extended_platform_dispatch_inputs.py \\\n"
        f"            --target {target} \\\n"
        '            --release-tag "$RELEASE_TAG" \\\n'
        '            --release-asset-base-url "$RELEASE_ASSET_BASE_URL" \\\n'
        '            --workflow-run-url "$WORKFLOW_RUN_URL" \\\n'
        '            --workflow-ref-name "$WORKFLOW_REF_NAME" \\\n'
        '            --source-head-sha "$SOURCE_HEAD_SHA" \\\n'
        '            --source-run-attempt "$SOURCE_RUN_ATTEMPT"'
    )
    if dispatch_command not in block:
        errors.append(
            f"{job} dispatch input preflight must bind target, release_tag, release URL, workflow_run_url, "
            "workflow_ref_name, source_head_sha and source_run_attempt"
        )
    if "--allow-extra-artifacts" in block:
        errors.append(f"{job} must use strict Linux artifact preflight without --allow-extra-artifacts")
    if "path: native-dist/linux/*" in block:
        errors.append(f"{job} must upload scoped staged files, not raw native-dist/linux wildcard")
    stale_paths = (
        f'--root . \\\n            --release-tag "$RELEASE_TAG" \\\n            --target {target}',
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


def native_capture_for_target(shell: str, target: str) -> str:
    """Return the shared capture commands and the selected native dependency setup."""
    cases = re.search(r'(?ms)^case "\$TARGET" in\n(.*?)^esac\n', shell)
    if cases is None:
        return ""
    branches = re.findall(r"(?ms)^  (linux-[a-z0-9]+|\*)\)\n(.*?)^    ;;$", cases[1])
    if [label for label, _ in branches] != [*NATIVE_LINUX_ARCHES, "*"]:
        return ""
    return shell[:cases.start()] + dict(branches)[target] + shell[cases.end():]


def check_native_capture(shell: str, target: str) -> list[str]:
    arch, rpm_arch, appimage_arch = NATIVE_LINUX_ARCHES[target]
    label = f"native {arch} capture"
    selected = native_capture_for_target(shell, target)
    if not selected:
        return [f"{label} missing its protected dependency setup"]
    lines = (line.strip() for line in selected.splitlines())
    commands = "\n".join(
        line for line in lines if not line.startswith("#") or line.startswith("#!")
    ).replace(" \\\n", " ")
    cargo = (
        ("locked offline Cargo configuration", 'export CARGO_NET_OFFLINE=true MATURIN_NO_INSTALL_RUST=true MATURIN_PEP517_ARGS="--locked --offline"'),
        ("locked Cargo prefetch", "python3 scripts/prepare_protected_linux_cargo.py"),
        ("locked Cargo wrapper", 'export CARGO="$CARGO_HOME/locked-cargo"'),
    ) if target == "linux-i386" else ()
    source_packages = "bcrypt,cffi,cryptography,pyftpdlib" if target == "linux-i386" else "cffi,pyftpdlib,pyinstaller"
    required = (
        ("strict shell safety", "#!/usr/bin/env bash\nset -euo pipefail\numask 077"),
        ("dispatch input preflight", 'python3 scripts/check_extended_platform_dispatch_inputs.py --target "$TARGET"'),
        ("exact tagged checkout", '$(git rev-parse --verify "refs/tags/${RELEASE_TAG}^{commit}")" != "$SOURCE_HEAD_SHA"'),
        ("protected build inputs", 'python3 scripts/check_protected_linux_build_inputs.py --target "$TARGET"'),
        ("builder identity run context", 'python3 scripts/check_extended_platform_builder.py --target "$TARGET" '
         '--release-tag "$RELEASE_TAG" --workflow-run-url "$WORKFLOW_RUN_URL" '
         '--workflow-run-attempt "$SOURCE_RUN_ATTEMPT" --source-head-sha "$SOURCE_HEAD_SHA" '
         '--out "$EVIDENCE_DIR/builder-identity-$TARGET.json"'),
        ("isolated release environment", "python3 -m venv .venv-native"),
        ("artifact architectures", f"readonly ARCH={arch} RPM_ARCH={rpm_arch} APPIMAGE_ARCH={appimage_arch}"),
        *cargo,
        ("protected bootstrap lock", "pip install --require-hashes --force-reinstall --only-binary=:all: "
         f"--requirement {NATIVE_LOCK_DIR}/{target}-bootstrap.txt"),
        ("protected CFFI lock", "pip install --require-hashes --no-cache-dir --no-build-isolation "
         f"--only-binary=:all: --no-binary=cffi --requirement {NATIVE_LOCK_DIR}/linux-32bit-cffi.txt"),
        ("protected runtime lock", "pip install --require-hashes --no-cache-dir --no-build-isolation "
         f"--only-binary=:all: --no-binary={source_packages} --requirement {NATIVE_LOCK_DIR}/{target}.txt"),
        ("exact runtime lock verification", 'python scripts/check_release_dependency_locks.py '
         '--runtime-report "$EVIDENCE_DIR/candidate-pip-inspect.json" '
         f'--lock "{NATIVE_LOCK_DIR}/$TARGET.txt"'),
        ("native artifact build", 'TARGET_ARCH="$ARCH" PYTHON_BIN=.venv-native/bin/python bash scripts/make_linux_native.sh'),
        ("native smoke run identity", 'bash scripts/smoke_linux_native.sh --arch "$ARCH" --dist native-dist/linux --target "$TARGET" '
         '--workflow-run-url "$WORKFLOW_RUN_URL" --workflow-run-attempt "$SOURCE_RUN_ATTEMPT" '
         '--source-head-sha "$SOURCE_HEAD_SHA" --builder-evidence "$EVIDENCE_DIR/builder-identity-$TARGET.json" '
         '2>&1 | tee "$EVIDENCE_DIR/native-smoke-$TARGET.log"'),
        ("staging after native smoke", 'mkdir -- "$EVIDENCE_DIR/artifacts"'),
        ("strict promotion artifact validation", 'python scripts/check_platform_promotion_artifacts.py --target "$TARGET" '
         '--assets-dir "$EVIDENCE_DIR/artifacts" --tag "$RELEASE_TAG" --strict'),
    )
    errors = [f"{label} missing {name}" for name, snippet in required if snippet not in commands]
    errors.extend(check_ordered_snippets(commands, required, job=label))
    for suffix in (
        "$ARCH.deb", "$RPM_ARCH.rpm", "$APPIMAGE_ARCH.AppImage", "$APPIMAGE_ARCH-native.tar.gz",
        "$APPIMAGE_ARCH-native-manifest.json", "$APPIMAGE_ARCH-native-SHA256SUMS.txt",
    ):
        if f'"native-dist/linux/remote-ops-workspace-$RELEASE_TAG-linux-{suffix}"' not in commands:
            errors.append(f"{label} missing target-scoped artifact staging for {suffix}")
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
    if not dependencies:
        return []
    tracked = tracked_workflow_scripts(dependencies)
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
        if relative not in tracked:
            errors.append(f"{label} must be tracked by git: {relative}")
    return errors


def workflow_script_dependencies(workflow: str) -> tuple[Path, ...]:
    discovered = {Path(reference) for reference in WORKFLOW_SCRIPT_REFERENCE_RE.findall(workflow)}
    required = set(WORKFLOW_SCRIPT_DEPENDENCIES)
    return tuple(sorted(discovered | required, key=lambda path: path.as_posix()))


def tracked_workflow_scripts(dependencies: tuple[Path, ...]) -> set[str]:
    result = subprocess.run(
        ["git", "--literal-pathspecs", "ls-files", "-z", "--", *(path.as_posix() for path in dependencies)],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    return set(result.stdout.split("\0")) if result.returncode == 0 else set()


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


def workflow_step_block(job_block: str, marker: str) -> str:
    pattern = rf"(?ms)^      - {re.escape(marker)}\n(.*?)(?=^      - |\Z)"
    match = re.search(pattern, job_block)
    return match.group(0) if match else ""


if __name__ == "__main__":
    raise SystemExit(main())

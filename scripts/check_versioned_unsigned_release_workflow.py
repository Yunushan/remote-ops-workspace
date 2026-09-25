"""Keep the exact-tag unsigned download lane separate from production promotion."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "versioned-unsigned-release.yml"
FROZEN_REF = "ref: ${{ needs.release-preflight.outputs.release_sha }}"


def _active_text(workflow: str) -> str:
    return "\n".join(
        line for line in workflow.splitlines() if not line.lstrip().startswith("#")
    )


def _job_block(workflow: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(name)}:\n(.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)",
        workflow,
    )
    return match.group(1) if match else ""


def _step_block(job: str, name: str) -> str:
    match = re.search(
        rf"(?ms)^      - name: {re.escape(name)}\n(.*?)(?=^      - |\Z)",
        job,
    )
    return match.group(1) if match else ""


def _require_step(
    errors: list[str], job: str, name: str, snippets: tuple[str, ...]
) -> None:
    step = _step_block(job, name)
    if not step:
        errors.append(f"missing mandatory step: {name}")
        return
    if re.search(r"(?m)^        (?:if|continue-on-error):", step):
        errors.append(f"mandatory step must not be conditional or ignored: {name}")
    for snippet in snippets:
        if snippet not in step:
            errors.append(f"{name} missing {snippet}")


def check_versioned_unsigned_release_workflow(workflow: str | None = None) -> list[str]:
    """Validate the release boundary and complete unsigned asset path."""
    raw = workflow if workflow is not None else WORKFLOW_PATH.read_text(encoding="utf-8")
    text = _active_text(raw)
    errors: list[str] = []

    event = re.search(r"(?ms)^on:\n(.*?)(?=^[A-Za-z][^:\n]*:\n|\Z)", text)
    if not event or not re.fullmatch(r"\s*workflow_dispatch:\s*", event.group(1)):
        errors.append("versioned unsigned publication must use workflow_dispatch only")
    for snippet, label in {
        "name: versioned-unsigned-release": "dedicated workflow identity",
        'ROW_REQUIRE_RELEASE_SIGNING: "0"': "explicit unsigned build setting",
        "RELEASE_TAG: ${{ github.ref_name }}": "exact dispatch-ref tag binding",
        "contents: read": "read-only default token permissions",
    }.items():
        if snippet not in text:
            errors.append(f"missing {label}: {snippet}")
    for forbidden in (
        "secrets.ROW_WINDOWS_",
        "secrets.ROW_MACOS_",
        "environment: release-compliance-review",
        "--channel production-signed",
        "--native-release-channel production-signed",
        "--require-platform-goal-targets",
        "--require-mobaxterm-parity-complete",
        "check_release_license_compliance.py",
        "check_release_provenance.py",
    ):
        if forbidden in text:
            errors.append(f"unsigned preview must not claim production certification: {forbidden}")

    preflight = _job_block(text, "release-preflight")
    if not preflight:
        errors.append("missing release-preflight job")
    else:
        _require_step(
            errors,
            preflight,
            "Bind exact tag and main source",
            (
                'test "$GITHUB_EVENT_NAME" = "workflow_dispatch"',
                'test "$GITHUB_RUN_ATTEMPT" = "1"',
                'test "$GITHUB_REF_TYPE" = "tag"',
                'test "$GITHUB_REF" = "refs/tags/$RELEASE_TAG"',
                "^v[0-9]+\\.[0-9]+\\.[0-9]+$",
                'test "$GITHUB_SHA" = "$release_sha"',
                'git merge-base --is-ancestor "$release_sha"',
            ),
        )
        _require_step(
            errors,
            preflight,
            "Require tagged preview redistribution materials before builds",
            ("check_preview_redistribution.py", "--preflight",
             "--evidence-dir redistribution-evidence", '--tag "$RELEASE_TAG"',
             '--sha "$RELEASE_SHA"'),
        )
        _require_step(
            errors,
            preflight,
            "Require version and verified release source",
            (
                'check_release_version.py --release-tag "$RELEASE_TAG"',
                'check_release_maturity.py --release-tag "$RELEASE_TAG"',
                'verify.py --quick --no-cli-smoke --release-tag "$RELEASE_TAG"',
                "check_repository_cleanup.py --require-clean",
            ),
        )
        _require_step(
            errors,
            preflight,
            "Require exact-SHA Python 3.15 and Windows CI evidence",
            (
                "check_python315_ci_evidence.py",
                '--branch "$DEFAULT_BRANCH"',
                '--sha "$RELEASE_SHA"',
            ),
        )
        material_position = preflight.find("      - name: Require tagged preview redistribution materials before builds\n")
        verify_position = preflight.find("      - name: Require version and verified release source\n")
        if material_position < 0 or verify_position < 0 or material_position >= verify_position:
            errors.append("preview redistribution materials must be checked before build verification")

    build_jobs = {
        "source-and-python": (
            "scripts/make_release.py",
            "--source-assets-only",
            "Smoke-test installed source Python wheel",
            "Smoke-test installed source distribution",
            "Smoke-test installed portable source bundle",
            "path: dist/*",
        ),
        "windows-native": (
            "scripts\\make_windows_native.ps1",
            "scripts\\smoke_windows_native.ps1",
            "- arch: x86",
            "- arch: x64",
            "- arch: arm64",
            "path: native-dist/windows/*",
        ),
        "macos-native": (
            "scripts/make_macos_native.sh",
            "scripts/smoke_macos_native.sh",
            "- arch: x64",
            "- arch: arm64",
            "path: native-dist/macos/*",
        ),
        "linux-native": (
            "scripts/make_linux_native.sh",
            "scripts/smoke_linux_native.sh",
            "- arch: x86_64",
            "- arch: aarch64",
            "path: native-dist/linux/*",
        ),
    }
    for name, required in build_jobs.items():
        block = _job_block(text, name)
        if not block:
            errors.append(f"missing full-download build job: {name}")
            continue
        for snippet in ("needs: release-preflight", FROZEN_REF, "persist-credentials: false", *required):
            if snippet not in block:
                errors.append(f"{name} missing {snippet}")
        if "continue-on-error:" in block:
            errors.append(f"{name} must not ignore build or smoke failures")

    source = _job_block(text, "source-and-python")
    if source:
        for name in (
            "Smoke-test installed source Python wheel",
            "Smoke-test installed Web/PWA wheel",
            "Smoke-test installed source distribution",
            "Smoke-test installed portable source bundle",
        ):
            _require_step(errors, source, name, ())
    for job_name, step_name, command in (
        ("windows-native", "Run Windows native installer smoke tests", "scripts\\smoke_windows_native.ps1"),
        ("macos-native", "Run macOS native installer smoke tests", "scripts/smoke_macos_native.sh"),
        ("linux-native", "Run Linux native installer smoke tests", "scripts/smoke_linux_native.sh"),
    ):
        block = _job_block(text, job_name)
        if block:
            _require_step(errors, block, step_name, (command,))
    for job_name, target, label in (
        ("windows-native", "windows-${{ matrix.arch }}", "Windows"),
        ("macos-native", "macos-${{ matrix.arch }}", "macOS"),
        ("linux-native", "linux-${{ matrix.arch }}", "Linux"),
    ):
        block = _job_block(text, job_name)
        if block:
            _require_step(
                errors, block, f"Capture exact {label} redistribution inventory",
                ("check_preview_redistribution.py", f'--capture-target "{target}"',
                 "--assets-dir native-dist/", "--tag \"$RELEASE_TAG\"", "--report"),
            )
            if f"name: preview-license-{target}" not in block:
                errors.append(f"{job_name} must upload separate builder inventory")

    publish = _job_block(text, "publish-unsigned-preview")
    if not publish:
        errors.append("missing publish-unsigned-preview job")
    else:
        for name in ("release-preflight", *build_jobs):
            if re.search(rf"(?m)^      - {re.escape(name)}$", publish) is None:
                errors.append(f"publish-unsigned-preview must depend on {name}")
        for snippet in (
            FROZEN_REF,
            "contents: write",
            "actions/download-artifact@",
            "pattern: release-*",
            "pattern: preview-license-*",
            "merge-multiple: true",
            "--native-release-channel unsigned-preview",
            "check_preview_redistribution.py",
            "--channel unsigned-preview",
            "check_release_remote_preconditions.py namespace",
            "actions/attest@",
            "UNSIGNED PREVIEW",
            "prerelease: true",
            "check_published_release_notes.py",
        ):
            if snippet not in publish:
                errors.append(f"publish-unsigned-preview missing {snippet}")
        validation = _step_block(publish, "Validate complete unsigned release asset inventory")
        if not validation:
            errors.append("missing mandatory step: Validate complete unsigned release asset inventory")
        else:
            if "check_release_publish_assets.py" not in validation:
                errors.append("full unsigned asset validation command missing")
            if "--source-assets-only" in validation:
                errors.append("final unsigned asset validation must include native downloads")
            if "--native-release-channel unsigned-preview" not in validation:
                errors.append("final unsigned asset validation must verify unsigned native metadata")
            if re.search(r"(?m)^        (?:if|continue-on-error):", validation):
                errors.append("full unsigned asset validation must be mandatory")
        required_steps = (
            "Validate complete unsigned release asset inventory",
            "Require exact-artifact preview redistribution evidence",
            "Generate explicit unsigned release notes",
            "Require unused release namespace including drafts",
            "Attest every unsigned release asset",
            "Verify exact-tag unsigned asset attestations",
            "Create new unsigned draft by numeric API identity",
            "Upload every unsigned asset to the new numeric draft",
            "Verify complete numeric unsigned draft inventory",
            "Re-resolve exact tag before publication",
            "Publish verified unsigned draft by numeric ID once",
            "Verify published unsigned release notes",
            "Verify final numeric release and exact asset bytes",
        )
        positions = [publish.find(f"      - name: {name}\n") for name in required_steps]
        for name, position in zip(required_steps, positions, strict=True):
            if position < 0:
                errors.append(f"publish-unsigned-preview missing mandatory step: {name}")
        if all(position >= 0 for position in positions) and positions != sorted(positions):
            errors.append("unsigned publication must validate, attest, verify draft bytes, then publish")
        redistribution = _step_block(publish, "Require exact-artifact preview redistribution evidence")
        if redistribution:
            for snippet in (
                "python scripts/check_preview_redistribution.py",
                "--assets-dir release-assets",
                "--evidence-dir redistribution-evidence",
                "--inventory-dir preview-license-inventory",
                '--tag "$RELEASE_TAG"',
                '--sha "$RELEASE_SHA"',
                '--repository "$GITHUB_REPOSITORY"',
                "--report",
            ):
                if snippet not in redistribution:
                    errors.append(f"preview redistribution gate missing {snippet}")
        for name in required_steps:
            step = _step_block(publish, name)
            if step and re.search(r"(?m)^        (?:if|continue-on-error):", step):
                errors.append(f"mandatory publish step must not be conditional or ignored: {name}")
        for snippet in (
            "gh api --method POST",
            "gh api --method PATCH",
            "--field draft=false",
            "--field prerelease=true",
            'assert len(assets) == len(expected)',
            'assert (asset["size"], asset["digest"]) == expected[name]',
            "--source-ref \"refs/tags/$RELEASE_TAG\"",
        ):
            if snippet not in publish:
                errors.append(f"unsigned draft transaction missing {snippet}")
        if "continue-on-error:" in publish:
            errors.append("publish-unsigned-preview must not ignore publication checks")

    return errors


def main() -> int:
    try:
        errors = check_versioned_unsigned_release_workflow()
    except OSError as exc:
        errors = [f"could not read workflow: {exc}"]
    if errors:
        for error in errors:
            print(f"versioned unsigned release workflow: {error}", file=sys.stderr)
        return 1
    print("versioned unsigned release workflow policy passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

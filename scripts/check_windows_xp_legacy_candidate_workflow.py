from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "xp-legacy-candidate.yml"
REQUIRED_FILES = (
    Path("legacy") / "xp_host" / "RemoteOpsXpHost.template.cs",
    Path("legacy") / "xp_host" / "net40-references.json",
    Path("scripts") / "make_windows_xp_legacy.ps1",
    Path("scripts") / "check_platform_promotion_artifacts.py",
    Path("scripts") / "check_xp_candidate_build_inputs.py",
)


def main() -> int:
    errors = check_windows_xp_legacy_candidate_workflow()
    if errors:
        for error in errors:
            print(f"Windows XP legacy candidate workflow: {error}", file=sys.stderr)
        return 1
    print("Windows XP legacy candidate workflow passed")
    return 0


def check_windows_xp_legacy_candidate_workflow(workflow: str | None = None) -> list[str]:
    text = workflow if workflow is not None else WORKFLOW_PATH.read_text(encoding="utf-8")
    errors: list[str] = []
    for trigger in ("push:", "pull_request:", "workflow_dispatch:"):
        if trigger not in text:
            errors.append(f"legacy candidate workflow missing trigger: {trigger.rstrip(':')}")
    if "permissions:\n  contents: read" not in text:
        errors.append("legacy candidate workflow must use read-only contents permission")
    if re.search(r"(?m)^\s+[A-Za-z0-9_-]+:\s+write\s*$", text):
        errors.append("legacy candidate workflow must not request write permissions")
    for relative in REQUIRED_FILES:
        path = ROOT / relative
        if not path.is_file() or path.is_symlink():
            errors.append(f"legacy candidate dependency must be a plain file: {relative.as_posix()}")
    required_snippets = {
        'branches:\n      - "**"': "branch push trigger",
        'tags:\n      - "v*"': "release tag trigger",
        "name: Windows XP signed candidate (${{ matrix.arch }})": "signed candidate matrix",
        "if: ${{ github.ref_type != 'tag' }}": "non-tag candidate job",
        "if: ${{ github.event_name == 'push' && github.ref_type == 'tag' }}": "tag-only signing job",
        "environment: release": "protected release environment",
        "ROW_XP_REQUIRE_SIGNING:": "tag signing requirement",
        "runs-on: windows-2025-vs2026": "modern Windows builder",
        "arch: [x86, x64]": "x86/x64 matrix",
        "uses: actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10 # v6": "checkout",
        "persist-credentials: false": "checkout credential isolation",
        "clean: true": "clean checkout",
        "uses: actions/setup-python@6d4fd22b20465ccc0f7354476588e8df7c9ca0e0 # v7.1.0": "Python setup",
        'python-version: "3.12"': "Python pin",
        "./scripts/make_windows_xp_legacy.ps1 -Arch ${{ matrix.arch }}": "legacy builder",
        "$actual -cne $env:GITHUB_SHA": "exact checkout source",
        "name: windows-xp-legacy-candidate-${{ matrix.arch }}-${{ github.run_attempt }}": "attempt-scoped candidate name",
        "path: native-dist/windows-xp/${{ matrix.arch }}/*": "scoped artifact path",
        "if-no-files-found: error": "artifact absence failure",
        "include-hidden-files: false": "hidden artifact exclusion",
        "retention-days: 30": "candidate artifact retention",
        "name: windows-xp-build-inputs-${{ matrix.arch }}-${{ github.run_attempt }}": "attempt-scoped build evidence",
        "path: build/native/windows-xp/${{ matrix.arch }}/xp-build-inputs.json": "build evidence path",
    }
    for snippet, label in required_snippets.items():
        if snippet not in text:
            errors.append(f"legacy candidate workflow missing {label}: {snippet}")
    verify = text.find("python scripts/check_xp_candidate_build_inputs.py")
    upload = text.find("uses: actions/upload-artifact@")
    if verify < 0 or upload < verify:
        errors.append("legacy candidate workflow must verify build evidence before upload")
    if "softprops/action-gh-release" in text or "gh release" in text:
        errors.append("legacy candidate workflow must not publish a release or claim XP-host proof")
    return errors


if __name__ == "__main__":
    raise SystemExit(main())

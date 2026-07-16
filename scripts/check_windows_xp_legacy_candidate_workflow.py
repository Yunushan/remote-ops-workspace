from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "xp-legacy-candidate.yml"
REQUIRED_FILES = (
    Path("legacy") / "xp_host" / "RemoteOpsXpHost.template.cs",
    Path("scripts") / "make_windows_xp_legacy.ps1",
    Path("scripts") / "check_platform_promotion_artifacts.py",
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
        "runs-on: windows-2025-vs2026": "modern Windows builder",
        "arch: [x86, x64]": "x86/x64 matrix",
        "uses: actions/checkout@v6": "checkout",
        "persist-credentials: false": "checkout credential isolation",
        "clean: true": "clean checkout",
        "uses: actions/setup-python@v6": "Python setup",
        'python-version: "3.12"': "Python pin",
        "./scripts/make_windows_xp_legacy.ps1 -Arch ${{ matrix.arch }}": "legacy builder",
        "name: windows-xp-legacy-candidate-${{ matrix.arch }}": "scoped artifact name",
        "path: native-dist/windows-xp/${{ matrix.arch }}/*": "scoped artifact path",
        "if-no-files-found: error": "artifact absence failure",
        "include-hidden-files: false": "hidden artifact exclusion",
        "retention-days: 30": "candidate artifact retention",
    }
    for snippet, label in required_snippets.items():
        if snippet not in text:
            errors.append(f"legacy candidate workflow missing {label}: {snippet}")
    if "softprops/action-gh-release" in text or "gh release" in text:
        errors.append("legacy candidate workflow must not publish a release or claim XP-host proof")
    return errors


if __name__ == "__main__":
    raise SystemExit(main())

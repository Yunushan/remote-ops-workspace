from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_PATH = ROOT / ".github" / "workflows" / "unsigned-preview.yml"


def main() -> int:
    errors = check_unsigned_preview_workflow()
    if errors:
        for error in errors:
            print(f"unsigned preview workflow: {error}", file=sys.stderr)
        return 1
    print("unsigned preview workflow policy passed")
    return 0


def check_unsigned_preview_workflow(workflow: str | None = None) -> list[str]:
    text = workflow if workflow is not None else WORKFLOW_PATH.read_text(encoding="utf-8")
    errors: list[str] = []
    required_snippets = {
        'name: unsigned-preview': "dedicated workflow name",
        'branches:\n      - preview\n      - "preview/**"': "preview-only push trigger",
        "workflow_dispatch:": "manual preview dispatch",
        "preview_ref:": "explicit preview ref input",
        "contents: write": "release permission for preview prereleases",
        "PREVIEW_REF: ${{ inputs.preview_ref || github.ref_name }}": "preview ref resolver",
        "PREVIEW_TAG: unsigned-preview-${{ github.run_id }}": "non-production tag namespace",
        "preview|preview/*)": "preview branch guard",
        'The unsigned preview lane cannot build main': "main branch rejection",
        'Run the preview workflow from the preview branch, not main': "workflow ref rejection",
        'Unsigned previews cannot be tag-triggered': "tag rejection",
        "name: unsigned-preview-source-python-${{ github.run_id }}": "preview artifact name",
        "UNSIGNED_PREVIEW.txt": "unsigned marker asset",
        "prerelease: true": "prerelease publication",
        "name: ${{ env.PREVIEW_TAG }} (UNSIGNED PREVIEW)": "visible unsigned release label",
        "target_commitish: ${{ github.sha }}": "preview commit binding",
        "Production releases remain gated by the protected default branch": "production boundary note",
    }
    for snippet, label in required_snippets.items():
        if snippet not in text:
            errors.append(f"missing {label}: {snippet}")

    if re.search(r"(?m)^\s*-\s+main\s*$", text):
        errors.append("preview workflow must not trigger from the main branch")
    if re.search(r"(?m)^\s+tags:\s*$", text):
        errors.append("preview workflow must not define a tag trigger")
    if "actions/attest@" in text:
        errors.append("preview workflow must not imply production attestation")
    if "tag_name: v" in text:
        errors.append("preview release tag must not use the production v* namespace")
    if "persist-credentials: false" not in text:
        errors.append("every preview checkout must disable persisted credentials")
    return errors


if __name__ == "__main__":
    raise SystemExit(main())

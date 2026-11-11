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
        "PREVIEW_REF: ${{ inputs.preview_ref || github.ref_name }}": "preview ref resolver",
        "PREVIEW_TAG: unsigned-preview-${{ github.run_id }}": "non-production tag namespace",
        "preview|preview/*)": "preview branch guard",
        'The unsigned preview lane cannot build main': "main branch rejection",
        'Run the preview workflow from the preview branch, not main': "workflow ref rejection",
        'Unsigned previews cannot be tag-triggered': "tag rejection",
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
    if re.search(r"(?m)^\s*PREVIEW_TAG:\s*['\"]?v", text):
        errors.append("preview release tag must not use the production v* namespace")

    read_jobs, separator, publish = text.partition("\n  publish:\n")
    checkout_count = len(re.findall(r"(?m)^\s*- uses: actions/checkout@", read_jobs))
    if checkout_count != 2 or read_jobs.count("persist-credentials: false") != checkout_count:
        errors.append("every preview checkout must disable persisted credentials")
    if "contents: write" in read_jobs or text.count("contents: write") != 1:
        errors.append("only the preview publication job may have contents write permission")
    if not separator or "actions/checkout@" in publish or "softprops/action-gh-release@" in publish:
        errors.append("preview publication must use the isolated draft transaction without a checkout")
    if "continue-on-error:" in publish:
        errors.append("preview publication must fail closed")
    if "--method DELETE" in publish or "gh release delete" in publish:
        errors.append("preview publication must preserve a failed release for inspection")

    guard_and_build = (
        "source-sha: ${{ steps.pin-source.outputs.sha }}",
        "ref: ${{ github.event_name == 'push' && github.sha || format('refs/heads/{0}', env.PREVIEW_REF) }}",
        "PREVIEW_SHA: ${{ needs.guard.outputs.source-sha }}",
        "ref: ${{ env.PREVIEW_SHA }}",
        'test "$(git rev-parse HEAD)" = "$PREVIEW_SHA"',
        "Commit: ${PREVIEW_SHA}",
        "artifact-id: ${{ steps.preview-assets.outputs.artifact-id }}",
    )
    publish_binding = (
        "needs: [guard, build]",
        "PREVIEW_SHA: ${{ needs.guard.outputs.source-sha }}",
        "artifact-ids: ${{ needs.build.outputs.artifact-id }}",
        "This prerelease was built from **${PREVIEW_REF}** at **${PREVIEW_SHA}**.",
        "Production releases remain gated by the protected default branch",
        "test -f preview-dist/UNSIGNED_PREVIEW.txt",
        'target_commitish: $sha, name: ($tag + " (UNSIGNED PREVIEW)")',
        "draft: true, prerelease: true",
        '(map({name, size, digest}) | sort_by(.name)) == $expected[0]',
    )
    for block, snippets in ((read_jobs, guard_and_build), (publish, publish_binding)):
        for snippet in snippets:
            if snippet not in block:
                errors.append(f"missing exact preview source, asset or release binding: {snippet}")

    transaction_commands = (
        'gh api --method POST "$api/releases" --input "$request"',
        '--data-binary "@$asset" "$upload_url?name=$encoded_name"',
        "verify_release true",
        'gh api --method PATCH "$api/releases/$release_id" --field draft=false',
        "verify_release false",
        'gh api "$api/git/ref/tags/$PREVIEW_TAG"',
    )
    positions = [publish.find(command) for command in transaction_commands]
    if -1 in positions or positions != sorted(positions):
        errors.append("preview publication must verify the full draft before publishing and recheck the final release and tag")
    return errors


if __name__ == "__main__":
    raise SystemExit(main())

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest

from scripts.check_unsigned_preview_workflow import check_unsigned_preview_workflow

WORKFLOW = Path(".github/workflows/unsigned-preview.yml").read_text(encoding="utf-8")


def test_unsigned_preview_workflow_is_isolated_and_explicit() -> None:
    assert check_unsigned_preview_workflow(WORKFLOW) == []


def test_unsigned_preview_workflow_rejects_main_trigger() -> None:
    errors = check_unsigned_preview_workflow(WORKFLOW.replace("      - preview\n", "      - main\n", 1))
    assert "preview workflow must not trigger from the main branch" in errors


def test_unsigned_preview_workflow_rejects_production_tag_namespace() -> None:
    errors = check_unsigned_preview_workflow(
        WORKFLOW.replace(
            "PREVIEW_TAG: unsigned-preview-${{ github.run_id }}",
            "PREVIEW_TAG: v1.0.27",
            1,
        )
    )
    assert "preview release tag must not use the production v* namespace" in errors


def test_unsigned_preview_workflow_rejects_moving_build_ref() -> None:
    errors = check_unsigned_preview_workflow(
        WORKFLOW.replace("ref: ${{ env.PREVIEW_SHA }}", "ref: ${{ env.PREVIEW_REF }}", 1)
    )
    assert "missing exact preview source, asset or release binding: ref: ${{ env.PREVIEW_SHA }}" in errors


def test_unsigned_preview_workflow_requires_verification_before_publication() -> None:
    errors = check_unsigned_preview_workflow(WORKFLOW.replace("          verify_release true\n", "", 1))
    assert "preview publication must verify the full draft before publishing and recheck the final release and tag" in errors


MOCK_PREVIEW_API = r'''
gh() {
  case "$*" in
    "api $api/git/matching-refs/tags/$PREVIEW_TAG") echo '[]' ;;
    "api --paginate --slurp $api/releases?per_page=100") echo '[[]]' ;;
    "api --method POST $api/releases --input $request")
      jq -e --arg sha "$PREVIEW_SHA" --arg tag "$PREVIEW_TAG" \
        'select(.draft and .prerelease and .tag_name == $tag and .target_commitish == $sha) |
         . + {id: 42, upload_url: "https://uploads.github.com/repos/owner/repo/releases/42/assets{?name,label}"}' \
        "$request" ;;
    "api $api/releases/42")
      local draft=true
      if [[ -f published ]]; then draft=false; fi
      jq --argjson draft "$draft" --slurpfile assets uploaded.json \
        '. + {id: 42, draft: $draft, assets: $assets[0]}' "$request" ;;
    "api --method PATCH $api/releases/42 --field draft=false --silent") touch published ;;
    "api --method DELETE $api/releases/42 --silent") touch deleted ;;
    "api $api/git/ref/tags/$PREVIEW_TAG")
      jq -n --arg ref "$tag_ref" --arg sha "$PREVIEW_SHA" '{ref: $ref, object: {type: "commit", sha: $sha}}' ;;
    *) return 93 ;;
  esac
}
curl() {
  printf '%s\n' "${!#}" >> uploads.txt
  printf '201'
}
'''


@pytest.mark.skipif(
    sys.platform != "linux" or not all(shutil.which(tool) for tool in ("bash", "jq", "sha256sum", "stat")),
    reason="requires the Ubuntu publication shell and tools",
)
@pytest.mark.parametrize("matches", [True, False])
def test_preview_draft_transaction_verifies_bytes_before_publishing(tmp_path, matches) -> None:
    assets = tmp_path / "preview-dist"
    assets.mkdir()
    (tmp_path / "preview-notes.md").write_text("# UNSIGNED PREVIEW\n", encoding="utf-8")
    uploaded = []
    for asset_id, name in enumerate(("UNSIGNED_PREVIEW.txt", "unsigned-preview-fixture.whl"), start=1):
        data = name.encode()
        (assets / name).write_bytes(data)
        digest = hashlib.sha256(data if matches or asset_id == 1 else b"different bytes").hexdigest()
        uploaded.append(dict(id=asset_id, name=name, size=len(data), digest=f"sha256:{digest}", state="uploaded"))
    (tmp_path / "uploaded.json").write_text(json.dumps(uploaded), encoding="utf-8")
    publication = WORKFLOW.split("      - name: Publish verified preview draft\n", 1)[1]
    script = textwrap.dedent(publication.split("        run: |\n", 1)[1])
    result = subprocess.run(
        ["bash", "-c", MOCK_PREVIEW_API + script],
        cwd=tmp_path,
        env={
            "PATH": os.environ["PATH"],
            "RUNNER_TEMP": str(tmp_path),
            "GITHUB_REPOSITORY": "owner/repo",
            "GITHUB_RUN_ID": "123",
            "GITHUB_RUN_ATTEMPT": "1",
            "GH_TOKEN": "fixture",
            "PREVIEW_SHA": "a" * 40,
            "PREVIEW_TAG": "unsigned-preview-123",
        },
        check=False,
        capture_output=True,
        text=True,
        timeout=20,
    )
    assert (result.returncode == 0) is matches, result.stdout + result.stderr
    assert (tmp_path / "published").exists() is matches
    assert (tmp_path / "deleted").exists() is not matches
    assert (tmp_path / "uploads.txt").read_text(encoding="utf-8").splitlines() == [
        f"https://uploads.github.com/repos/owner/repo/releases/42/assets?name={asset['name']}"
        for asset in uploaded
    ]

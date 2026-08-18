from __future__ import annotations

from pathlib import Path

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
            "tag_name: ${{ env.PREVIEW_TAG }}",
            "tag_name: v1.0.20",
            1,
        )
    )
    assert "preview release tag must not use the production v* namespace" in errors

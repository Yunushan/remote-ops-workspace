from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


def test_platform_promotion_runbook_passes_current_tree() -> None:
    checker = _load_checker()

    assert checker.main() == 0


def test_platform_promotion_runbook_rejects_missing_target_id() -> None:
    checker = _load_checker()
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8")
    text = text.replace("Target id: `linux-i386`", "Target id: `linux-i386-missing`")

    errors = checker.check_platform_promotion_runbook(runbook_text=text)

    assert "promotion runbook missing target id section: linux-i386" in errors


def test_platform_promotion_runbook_rejects_missing_blocker() -> None:
    checker = _load_checker()
    promotion = json.loads(Path("configs/platform_parity_promotion.json").read_text(encoding="utf-8"))
    blocker = promotion["protected_targets"][0]["current_blockers"][0]
    text = Path("docs/PLATFORM_PROMOTION_RUNBOOK.md").read_text(encoding="utf-8").replace(blocker, "")

    errors = checker.check_platform_promotion_runbook(runbook_text=text, promotion=promotion)

    assert f"linux-i386 runbook missing blocker: {blocker}" in errors


def _load_checker():
    path = Path("scripts/check_platform_promotion_runbook.py")
    spec = importlib.util.spec_from_file_location("check_platform_promotion_runbook", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

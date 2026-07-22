from __future__ import annotations

import importlib.util
from pathlib import Path


def test_production_deployment_checker_passes_current_tree() -> None:
    checker = _load_checker()

    assert checker.check_production_deployment() == []


def test_production_deployment_checker_rejects_missing_restore_drill(monkeypatch, tmp_path: Path) -> None:
    checker = _load_checker()
    guide = checker.DEPLOYMENT_GUIDE.read_text(encoding="utf-8")
    replacement = tmp_path / "production-deployment-guide.md"
    replacement.write_text(guide.replace("restore drill", "recovery exercise"), encoding="utf-8")
    monkeypatch.setattr(checker, "DEPLOYMENT_GUIDE", replacement)

    assert any("restore drill" in error for error in checker.check_production_deployment())


def test_production_deployment_checker_rejects_public_port_mapping(monkeypatch, tmp_path: Path) -> None:
    checker = _load_checker()
    compose = checker.COMPOSE_FILE.read_text(encoding="utf-8")
    replacement = tmp_path / "compose.yaml"
    replacement.write_text(
        compose.replace('      - "127.0.0.1:8765:8765"', '      - "127.0.0.1:8765:8765"\n      - "8765:8765"'),
        encoding="utf-8",
    )
    monkeypatch.setattr(checker, "COMPOSE_FILE", replacement)

    assert any("public network port mapping: 8765:8765" in error for error in checker.check_production_deployment())


def _load_checker():
    path = Path("scripts/check_production_deployment.py")
    spec = importlib.util.spec_from_file_location("check_production_deployment_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def test_verify_steps_include_full_checks_and_cli_smoke(tmp_path: Path) -> None:
    verify = _load_verify_module()

    steps = verify.build_steps("python", row_home=tmp_path)
    names = [step.name for step in steps]

    assert "compile source, tests, and scripts" in names
    assert "documentation consistency" in names
    assert "roadmap truth" in names
    assert "CI workflow policy" in names
    assert "release identity and artifact truth" in names
    assert "release toolchain reproducibility" in names
    assert "platform support truth" in names
    assert "release publish asset contract" in names
    assert "optional dependency smoke" in names
    assert "native release hardening" in names
    assert "native installer smoke contract" in names
    assert "GUI preview workflow" in names
    assert "GUI visual metrics" in names
    assert "GUI parity criteria" in names
    assert "real GUI render smoke" in names
    assert "README media workflow" in names
    assert "first-run UX" in names
    assert "feature reality alignment" in names
    assert "pytest" in names
    assert "CLI smoke: init temp workspace" in names
    assert "CLI smoke: feature coverage" in names
    assert any(step.requires_module == "pytest" for step in steps)
    assert all(str(tmp_path) in step.env.get("ROW_HOME", "") for step in steps if step.name.startswith("CLI smoke"))


def test_verify_quick_mode_skips_pytest_but_keeps_cli_smoke(tmp_path: Path) -> None:
    verify = _load_verify_module()

    steps = verify.build_steps("python", quick=True, row_home=tmp_path)
    names = [step.name for step in steps]

    assert "compile source, tests, and scripts" in names
    assert "documentation consistency" in names
    assert "roadmap truth" in names
    assert "CI workflow policy" in names
    assert "release identity and artifact truth" in names
    assert "release toolchain reproducibility" in names
    assert "platform support truth" in names
    assert "release publish asset contract" in names
    assert "optional dependency smoke" in names
    assert "native release hardening" in names
    assert "native installer smoke contract" in names
    assert "GUI preview workflow" in names
    assert "GUI visual metrics" in names
    assert "GUI parity criteria" in names
    assert "real GUI render smoke" in names
    assert "README media workflow" in names
    assert "first-run UX" in names
    assert "feature reality alignment" in names
    assert "pytest" not in names
    assert "CLI smoke: init temp workspace" in names
    assert "CLI smoke: feature coverage" in names


def _load_verify_module():
    path = Path("scripts/verify.py")
    spec = importlib.util.spec_from_file_location("verify_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

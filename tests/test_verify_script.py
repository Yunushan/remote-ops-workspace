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
    assert "platform parity promotion gate" in names
    assert "platform promotion runbook" in names
    assert "platform promotion artifact validator contract" in names
    assert "extended platform evidence workflow" in names
    assert "extended platform dispatch input validator" in names
    assert "extended Linux evidence bundle packer" in names
    assert "Windows XP native evidence contract" in names
    assert "Windows XP native evidence template generator" in names
    assert "Windows XP native evidence bundle packer" in names
    assert "platform verified evidence registry" in names
    assert "protected platform goal parity report" in names
    assert "platform verified evidence record generator" in names
    assert "platform verified evidence record finalizer" in names
    assert "platform review bundle artifact validator" in names
    assert "platform evidence artifact importer" in names
    assert "MobaXterm parity evidence registry" in names
    assert "MobaXterm parity evidence record generator" in names
    assert "release publish asset contract" in names
    assert "optional dependency smoke" in names
    assert "native release hardening" in names
    assert "native installer smoke contract" in names
    assert "GUI preview workflow" in names
    assert "GUI visual metrics" in names
    assert "GUI parity criteria" in names
    assert "real GUI render smoke" in names
    assert "real GUI render artifact validator contract" in names
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
    assert "platform parity promotion gate" in names
    assert "platform promotion runbook" in names
    assert "platform promotion artifact validator contract" in names
    assert "extended platform evidence workflow" in names
    assert "extended platform dispatch input validator" in names
    assert "extended Linux evidence bundle packer" in names
    assert "Windows XP native evidence contract" in names
    assert "Windows XP native evidence template generator" in names
    assert "Windows XP native evidence bundle packer" in names
    assert "platform verified evidence registry" in names
    assert "protected platform goal parity report" in names
    assert "platform verified evidence record generator" in names
    assert "platform verified evidence record finalizer" in names
    assert "platform review bundle artifact validator" in names
    assert "platform evidence artifact importer" in names
    assert "MobaXterm parity evidence registry" in names
    assert "MobaXterm parity evidence record generator" in names
    assert "release publish asset contract" in names
    assert "optional dependency smoke" in names
    assert "native release hardening" in names
    assert "native installer smoke contract" in names
    assert "GUI preview workflow" in names
    assert "GUI visual metrics" in names
    assert "GUI parity criteria" in names
    assert "real GUI render smoke" in names
    assert "real GUI render artifact validator contract" in names
    assert "README media workflow" in names
    assert "first-run UX" in names
    assert "feature reality alignment" in names
    assert "pytest" not in names
    assert "CLI smoke: init temp workspace" in names
    assert "CLI smoke: feature coverage" in names


def test_verify_can_require_real_gui_render(tmp_path: Path) -> None:
    verify = _load_verify_module()

    default_steps = verify.build_steps("python", quick=True, row_home=tmp_path)
    strict_steps = verify.build_steps(
        "python",
        quick=True,
        require_real_gui=True,
        row_home=tmp_path,
    )

    default_real_gui = next(step for step in default_steps if step.name == "real GUI render smoke")
    strict_real_gui = next(step for step in strict_steps if step.name == "real GUI render smoke")

    assert "--require-pyqt6" not in default_real_gui.command
    assert "--require-pyqt6" in strict_real_gui.command
    assert ["--timeout-seconds", "240"] == default_real_gui.command[2:4]
    assert ["--timeout-seconds", "240"] == strict_real_gui.command[2:4]


def test_verify_can_require_platform_goal_targets(tmp_path: Path) -> None:
    verify = _load_verify_module()
    bundle_dir = tmp_path / "platform-bundles"

    default_steps = verify.build_steps("python", quick=True, row_home=tmp_path)
    strict_steps = verify.build_steps(
        "python",
        quick=True,
        require_platform_goal_targets=True,
        release_tag="v1.0.3",
        platform_review_bundle_dir=bundle_dir,
        row_home=tmp_path,
    )

    default_names = [step.name for step in default_steps]
    strict_names = [step.name for step in strict_steps]
    default_publish = next(
        step for step in default_steps if step.name == "release publish asset contract"
    )
    strict_publish = next(
        step for step in strict_steps if step.name == "release publish asset contract"
    )
    strict_goal = next(
        step for step in strict_steps if step.name == "platform verified evidence goal gate"
    )
    strict_protected_report = next(
        step for step in strict_steps if step.name == "protected platform goal parity report"
    )
    strict_protected_gate = next(
        step for step in strict_steps if step.name == "protected platform goal parity gate"
    )
    strict_bundle = next(
        step for step in strict_steps if step.name == "platform review bundle artifact validation"
    )

    assert "protected platform goal parity report" in default_names
    assert "protected platform goal parity report" in strict_names
    assert "protected platform goal parity gate" not in default_names
    assert "protected platform goal parity gate" in strict_names
    assert "platform verified evidence goal gate" not in default_names
    assert "platform verified evidence goal gate" in strict_names
    assert "platform review bundle artifact validation" not in default_names
    assert "platform review bundle artifact validation" in strict_names
    assert "--require-platform-goal-targets" not in default_publish.command
    assert "--require-platform-goal-targets" in strict_publish.command
    assert "--require-goal-targets" in strict_goal.command
    assert ["--release-tag", "v1.0.3"] == strict_goal.command[-2:]
    assert ["--release-tag", "v1.0.3"] == strict_protected_report.command[-2:]
    assert "--require-complete" in strict_protected_gate.command
    assert ["--release-tag", "v1.0.3"] == strict_protected_gate.command[-2:]
    assert ["--tag", "v1.0.3"] == strict_publish.command[2:4]
    assert ["--bundle-dir", str(bundle_dir)] == strict_bundle.command[2:4]
    assert "--require-goal-targets" in strict_bundle.command
    assert ["--release-tag", "v1.0.3"] == strict_bundle.command[-2:]


def test_verify_rejects_strict_platform_goal_without_release_tag(tmp_path: Path) -> None:
    verify = _load_verify_module()

    result = verify.main(
        [
            "--quick",
            "--no-cli-smoke",
            "--require-platform-goal-targets",
            "--platform-review-bundle-dir",
            str(tmp_path),
        ]
    )

    assert result == 2


def test_verify_rejects_strict_platform_goal_without_review_bundle_dir() -> None:
    verify = _load_verify_module()

    result = verify.main(
        [
            "--quick",
            "--no-cli-smoke",
            "--require-platform-goal-targets",
            "--release-tag",
            "v1.0.3",
        ]
    )

    assert result == 2


def _load_verify_module():
    path = Path("scripts/verify.py")
    spec = importlib.util.spec_from_file_location("verify_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

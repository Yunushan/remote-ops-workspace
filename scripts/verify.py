from __future__ import annotations

import argparse
import importlib.util
import os
import shlex
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
DEV_INSTALL_HINT = 'python -m pip install -e ".[desktop,security,dev]"'


@dataclass(frozen=True)
class VerifyStep:
    name: str
    command: list[str]
    env: dict[str, str] | None = None
    requires_module: str | None = None


def build_steps(
    python: str,
    *,
    quick: bool = False,
    lint: bool = False,
    no_cli_smoke: bool = False,
    row_home: Path | None = None,
) -> list[VerifyStep]:
    steps = [
        VerifyStep(
            "compile source, tests, and scripts",
            [python, "-m", "compileall", "src", "tests", "scripts"],
            env=_source_env(),
        ),
        VerifyStep(
            "documentation consistency",
            [python, "scripts/check_docs.py"],
            env=_source_env(),
        ),
        VerifyStep(
            "roadmap truth",
            [python, "scripts/check_roadmap_truth.py"],
            env=_source_env(),
        ),
        VerifyStep(
            "CI workflow policy",
            [python, "scripts/check_ci_workflow.py"],
            env=_source_env(),
        ),
        VerifyStep(
            "release identity and artifact truth",
            [python, "scripts/check_release_truth.py"],
            env=_source_env(),
        ),
        VerifyStep(
            "release toolchain reproducibility",
            [python, "scripts/check_release_toolchain.py"],
            env=_source_env(),
        ),
        VerifyStep(
            "release matrix policy",
            [python, "scripts/check_release_matrix.py"],
            env=_source_env(),
        ),
        VerifyStep(
            "platform support truth",
            [python, "scripts/check_platform_support_truth.py"],
            env=_source_env(),
        ),
        VerifyStep(
            "release publish asset contract",
            [python, "scripts/check_release_publish_assets.py"],
            env=_source_env(),
        ),
        VerifyStep(
            "optional dependency smoke",
            [python, "scripts/check_optional_dependencies.py"],
            env=_source_env(),
        ),
        VerifyStep(
            "native release hardening",
            [python, "scripts/check_native_release_hardening.py"],
            env=_source_env(),
        ),
        VerifyStep(
            "native installer smoke contract",
            [python, "scripts/check_native_installer_smoke.py"],
            env=_source_env(),
        ),
        VerifyStep(
            "production security polish",
            [python, "scripts/check_security_polish.py"],
            env=_source_env(),
        ),
        VerifyStep(
            "repository cleanup preflight",
            [python, "scripts/check_repository_cleanup.py"],
            env=_source_env(),
        ),
        VerifyStep(
            "GUI preview workflow",
            [python, "scripts/check_gui_design_previews.py"],
            env=_source_env(),
        ),
        VerifyStep(
            "real GUI render smoke",
            [python, "scripts/check_real_gui_render.py"],
            env=_source_env(),
        ),
        VerifyStep(
            "README media workflow",
            [python, "scripts/check_readme_media.py"],
            env=_source_env(),
        ),
        VerifyStep(
            "first-run UX",
            [python, "scripts/check_first_run_ux.py"],
            env=_source_env(),
        ),
        VerifyStep(
            "feature reality alignment",
            [python, "scripts/check_feature_reality.py"],
            env=_source_env(),
        ),
        VerifyStep(
            "coverage truth metrics",
            [python, "scripts/check_product_readiness.py"],
            env=_source_env(),
        ),
    ]
    if lint:
        steps.append(
            VerifyStep(
                "ruff lint",
                [python, "-m", "ruff", "check", "src", "tests", "scripts"],
                env=_source_env(),
                requires_module="ruff",
            )
        )
    if not quick:
        steps.append(
            VerifyStep(
                "pytest",
                [python, "-m", "pytest", "-q"],
                env=_source_env(),
                requires_module="pytest",
            )
        )
    if not no_cli_smoke:
        smoke_home = row_home or Path(".verify-row-home")
        steps.extend(_cli_smoke_steps(python, smoke_home))
    return steps


def run_steps(steps: list[VerifyStep]) -> int:
    for step in steps:
        if step.requires_module and importlib.util.find_spec(step.requires_module) is None:
            print(
                f"missing Python module for verification step '{step.name}': "
                f"{step.requires_module}\nInstall dev dependencies with: {DEV_INSTALL_HINT}",
                file=sys.stderr,
            )
            return 2
        print(f"==> {step.name}", flush=True)
        print(f"    {_format_command(step.command)}", flush=True)
        try:
            subprocess.run(step.command, cwd=ROOT, env=step.env, check=True)
        except subprocess.CalledProcessError as exc:
            return exc.returncode or 1
    print("verification passed", flush=True)
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run reproducible local verification.")
    parser.add_argument(
        "--quick",
        action="store_true",
        help="run stdlib-only checks and CLI smoke; skip pytest",
    )
    parser.add_argument(
        "--lint",
        action="store_true",
        help="also run ruff; requires the dev extra",
    )
    parser.add_argument(
        "--no-cli-smoke",
        action="store_true",
        help="skip CLI smoke commands",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="row-verify-") as raw_tmp:
        row_home = Path(raw_tmp) / "row-home"
        steps = build_steps(
            sys.executable,
            quick=args.quick,
            lint=args.lint,
            no_cli_smoke=args.no_cli_smoke,
            row_home=row_home,
        )
        return run_steps(steps)


def _cli_smoke_steps(python: str, row_home: Path) -> list[VerifyStep]:
    env = _source_env(row_home=row_home)
    return [
        VerifyStep("CLI smoke: init temp workspace", [python, "-m", "remote_ops_workspace", "init"], env=env),
        VerifyStep("CLI smoke: list profiles", [python, "-m", "remote_ops_workspace", "profile", "list"], env=env),
        VerifyStep(
            "CLI smoke: dry-run example SSH",
            [python, "-m", "remote_ops_workspace", "connect", "example-ssh", "--dry-run"],
            env=env,
        ),
        VerifyStep("CLI smoke: doctor JSON", [python, "-m", "remote_ops_workspace", "doctor", "--json"], env=env),
        VerifyStep(
            "CLI smoke: feature coverage",
            [python, "-m", "remote_ops_workspace", "features", "--coverage"],
            env=env,
        ),
    ]


def _source_env(*, row_home: Path | None = None) -> dict[str, str]:
    env = os.environ.copy()
    existing = env.get("PYTHONPATH")
    env["PYTHONPATH"] = str(SRC) if not existing else f"{SRC}{os.pathsep}{existing}"
    if row_home is not None:
        env["ROW_HOME"] = str(row_home)
    return env


def _format_command(command: list[str]) -> str:
    return " ".join(shlex.quote(part) for part in command)


if __name__ == "__main__":
    raise SystemExit(main())

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
    require_real_gui: bool = False,
    require_platform_goal_targets: bool = False,
    release_tag: str | None = None,
    platform_review_bundle_dir: Path | None = None,
    release_assets_dir: Path | None = None,
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
            "platform parity promotion gate",
            [python, "scripts/check_platform_parity_promotion.py"],
            env=_source_env(),
        ),
        VerifyStep(
            "platform promotion runbook",
            [python, "scripts/check_platform_promotion_runbook.py"],
            env=_source_env(),
        ),
        VerifyStep(
            "platform promotion artifact validator contract",
            [python, "scripts/check_platform_promotion_artifacts.py", "--contract"],
            env=_source_env(),
        ),
        VerifyStep(
            "protected platform local evidence preflight",
            [python, "scripts/check_platform_goal_local_evidence.py", "--help"],
            env=_source_env(),
        ),
        VerifyStep(
            "extended platform evidence workflow",
            [python, "scripts/check_extended_platform_evidence.py"],
            env=_source_env(),
        ),
        VerifyStep(
            "extended platform dispatch input validator",
            [python, "scripts/check_extended_platform_dispatch_inputs.py", "--help"],
            env=_source_env(),
        ),
        VerifyStep(
            "extended Linux evidence bundle packer",
            [python, "scripts/make_extended_linux_evidence_bundle.py", "--help"],
            env=_source_env(),
        ),
        VerifyStep(
            "extended Linux staged upload packer",
            [python, "scripts/stage_extended_linux_evidence_upload.py", "--help"],
            env=_source_env(),
        ),
        VerifyStep(
            "Windows XP native evidence contract",
            [python, "scripts/check_xp_native_evidence.py", "--contract"],
            env=_source_env(),
        ),
        VerifyStep(
            "Windows XP native evidence source workflow",
            [python, "scripts/check_xp_native_evidence_workflow.py"],
            env=_source_env(),
        ),
        VerifyStep(
            "Windows XP native evidence dispatch input validator",
            [python, "scripts/check_xp_native_evidence_dispatch_inputs.py", "--help"],
            env=_source_env(),
        ),
        VerifyStep(
            "Windows XP native evidence template generator",
            [python, "scripts/make_xp_native_evidence_template.py", "--help"],
            env=_source_env(),
        ),
        VerifyStep(
            "Windows XP native evidence bundle packer",
            [python, "scripts/make_xp_native_evidence_bundle.py", "--help"],
            env=_source_env(),
        ),
        VerifyStep(
            "Windows XP native staged upload packer",
            [python, "scripts/stage_xp_native_evidence_upload.py", "--help"],
            env=_source_env(),
        ),
        VerifyStep(
            "platform verified evidence registry",
            [python, "scripts/check_platform_verified_evidence.py"],
            env=_source_env(),
        ),
        VerifyStep(
            "protected platform goal parity report",
            [
                python,
                "scripts/check_protected_platform_goal.py",
                *(["--release-tag", release_tag] if release_tag else []),
            ],
            env=_source_env(),
        ),
        *(
            [
                VerifyStep(
                    "protected platform goal parity gate",
                    [
                        python,
                        "scripts/check_protected_platform_goal.py",
                        "--require-complete",
                        *(["--release-tag", release_tag] if release_tag else []),
                    ],
                    env=_source_env(),
                )
            ]
            if require_platform_goal_targets
            else []
        ),
        *(
            [
                VerifyStep(
                    "platform verified evidence goal gate",
                    [
                        python,
                        "scripts/check_platform_verified_evidence.py",
                        "--require-goal-targets",
                        "--require-review-bundles",
                        *(["--release-tag", release_tag] if release_tag else []),
                    ],
                    env=_source_env(),
                )
            ]
            if require_platform_goal_targets
            else []
        ),
        VerifyStep(
            "platform verified evidence record generator",
            [python, "scripts/make_platform_verified_evidence_record.py", "--help"],
            env=_source_env(),
        ),
        VerifyStep(
            "platform verified evidence record finalizer",
            [python, "scripts/finalize_platform_verified_evidence_record.py", "--help"],
            env=_source_env(),
        ),
        VerifyStep(
            "platform review bundle artifact validator",
            [python, "scripts/check_platform_review_bundle_artifacts.py", "--help"],
            env=_source_env(),
        ),
        VerifyStep(
            "platform evidence artifact importer",
            [python, "scripts/import_platform_evidence_artifacts.py", "--help"],
            env=_source_env(),
        ),
        *(
            [
                VerifyStep(
                    "platform evidence artifact import dry-run",
                    [
                        python,
                        "scripts/import_platform_evidence_artifacts.py",
                        "--release-tag",
                        release_tag,
                        "--require-goal-targets",
                        "--out-dir",
                        str(release_assets_dir),
                        "--dry-run",
                        "--verify-source-run",
                    ],
                    env=_source_env(),
                )
            ]
            if require_platform_goal_targets and release_tag and release_assets_dir is not None
            else []
        ),
        *(
            [
                VerifyStep(
                    "platform review bundle artifact validation",
                    [
                        python,
                        "scripts/check_platform_review_bundle_artifacts.py",
                        "--bundle-dir",
                        str(platform_review_bundle_dir),
                        *(["--require-goal-targets"] if require_platform_goal_targets else []),
                        *(["--release-tag", release_tag] if release_tag else []),
                    ],
                    env=_source_env(),
                )
            ]
            if platform_review_bundle_dir is not None
            else []
        ),
        VerifyStep(
            "MobaXterm parity evidence registry",
            [python, "scripts/check_mobaxterm_parity_evidence.py"],
            env=_source_env(),
        ),
        VerifyStep(
            "MobaXterm parity evidence record generator",
            [python, "scripts/make_mobaxterm_parity_evidence_record.py", "--help"],
            env=_source_env(),
        ),
        VerifyStep(
            "mobile support contract",
            [python, "scripts/check_mobile_support.py"],
            env=_source_env(),
        ),
        VerifyStep(
            "release publish asset contract",
            [
                python,
                "scripts/check_release_publish_assets.py",
                *(["--assets-dir", str(release_assets_dir)] if release_assets_dir is not None else []),
                *(["--tag", release_tag] if release_tag else []),
                *(["--require-platform-goal-targets"] if require_platform_goal_targets else []),
            ],
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
            "GUI visual metrics",
            [python, "scripts/check_gui_visual_metrics.py"],
            env=_source_env(),
        ),
        VerifyStep(
            "GUI parity criteria",
            [python, "scripts/check_gui_parity.py"],
            env=_source_env(),
        ),
        VerifyStep(
            "real GUI render smoke",
            [
                python,
                "scripts/check_real_gui_render.py",
                "--timeout-seconds",
                "240",
                *(["--require-pyqt6"] if require_real_gui else []),
            ],
            env=_source_env(),
        ),
        VerifyStep(
            "real GUI render artifact validator contract",
            [python, "scripts/check_real_gui_render_artifact.py", "--contract"],
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
    parser.add_argument(
        "--require-real-gui",
        action="store_true",
        help="require PyQt6 and fail unless the live GUI render smoke captures real screenshots",
    )
    parser.add_argument(
        "--require-platform-goal-targets",
        action="store_true",
        help=(
            "fail unless Linux i386, Linux armhf, Windows XP native x86, "
            "and Windows XP native x64 all have accepted platform evidence; "
            "requires --release-tag, --platform-review-bundle-dir, and --release-assets-dir"
        ),
    )
    parser.add_argument(
        "--release-tag",
        help="When running release-sensitive gates, validate accepted evidence against this tag.",
    )
    parser.add_argument(
        "--platform-review-bundle-dir",
        type=Path,
        help=(
            "Downloaded platform review-bundle artifact directory to validate as part of "
            "strict platform-goal promotion."
        ),
    )
    parser.add_argument(
        "--release-assets-dir",
        type=Path,
        help=(
            "Downloaded/publish-ready release asset directory to validate as part of "
            "strict platform-goal promotion."
        ),
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    strict_errors = strict_platform_goal_arg_errors(args)
    if strict_errors:
        for error in strict_errors:
            print(f"verify: {error}", file=sys.stderr)
        return 2
    with tempfile.TemporaryDirectory(prefix="row-verify-") as raw_tmp:
        row_home = Path(raw_tmp) / "row-home"
        steps = build_steps(
            sys.executable,
            quick=args.quick,
            lint=args.lint,
            no_cli_smoke=args.no_cli_smoke,
            require_real_gui=args.require_real_gui,
            require_platform_goal_targets=args.require_platform_goal_targets,
            release_tag=args.release_tag,
            platform_review_bundle_dir=args.platform_review_bundle_dir,
            release_assets_dir=args.release_assets_dir,
            row_home=row_home,
        )
        return run_steps(steps)


def strict_platform_goal_arg_errors(args: argparse.Namespace) -> list[str]:
    if not args.require_platform_goal_targets:
        return []
    errors: list[str] = []
    if not args.release_tag:
        errors.append("--require-platform-goal-targets requires --release-tag vX.Y.Z")
    if args.platform_review_bundle_dir is None:
        errors.append("--require-platform-goal-targets requires --platform-review-bundle-dir")
    if args.release_assets_dir is None:
        errors.append("--require-platform-goal-targets requires --release-assets-dir")
    return errors


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

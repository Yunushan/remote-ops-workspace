from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def test_ci_workflow_checker_passes_current_tree() -> None:
    checker = _load_checker()

    assert checker.main() == 0


def test_ci_workflow_requires_lint_enabled_verifier() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "python scripts/verify.py --lint",
        "python scripts/verify.py",
    )

    errors = checker.check_ci_workflow(workflow)

    assert "ci test job must run the lint-enabled verifier" in errors


def test_ci_workflow_requires_node24_javascript_action_runtime() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        '  FORCE_JAVASCRIPT_ACTIONS_TO_NODE24: "true"\n',
        "",
    )

    errors = checker.check_ci_workflow(workflow)

    assert "ci workflow must opt JavaScript actions into Node.js 24" in errors


def test_ci_workflow_rejects_insecure_node_runtime_opt_out() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8") + (
        "\nenv:\n  ACTIONS_ALLOW_USE_UNSECURE_NODE_VERSION: true\n"
    )

    errors = checker.check_ci_workflow(workflow)

    assert "ci workflow must not opt JavaScript actions into an insecure Node.js runtime" in errors


def test_ci_workflow_requires_dedicated_gui_render_job() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "  gui-render:",
        "  gui_render_disabled:",
    )

    errors = checker.check_ci_workflow(workflow)

    assert "ci workflow missing gui-render job for live PyQt6 screenshots" in errors


def test_ci_workflow_requires_mobile_web_pwa_contract_job() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "  mobile-web:",
        "  mobile_web_disabled:",
    )

    errors = checker.check_ci_workflow(workflow)

    assert "ci workflow missing mobile-web job for Android/iOS Web/PWA contract" in errors


def test_ci_workflow_requires_android_emulator_web_job() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "  android-emulator-web:",
        "  android_emulator_web_disabled:",
    )

    errors = checker.check_ci_workflow(workflow)

    assert "ci workflow missing android-emulator-web job for Android API Web/PWA smoke" in errors


def test_ci_workflow_requires_android_api_31_to_36_matrix() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "        api-level: [31, 32, 33, 34, 35, 36]\n",
        "        api-level: [35]\n",
    )

    errors = checker.check_ci_workflow(workflow)

    assert "ci android-emulator-web job missing Android 12-16 API matrix" in "\n".join(errors)


def test_ci_workflow_requires_ios_simulator_web_job() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "  ios-simulator-web:",
        "  ios_simulator_web_disabled:",
    )

    errors = checker.check_ci_workflow(workflow)

    assert "ci workflow missing ios-simulator-web job for iOS Web/PWA smoke" in errors


def test_ci_workflow_requires_all_preset_live_render_capture() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "--require-pyqt6 --timeout-seconds 240 --out-dir",
        "--require-pyqt6 --timeout-seconds 240 --preset native --preset mobaxterm --out-dir",
    )

    errors = checker.check_ci_workflow(workflow)

    assert "ci gui-render job must use the default all-preset live screenshot set" in errors


def test_ci_workflow_requires_linux_qt_runtime_libraries() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "            libegl1 \\\n",
        "",
    )

    errors = checker.check_ci_workflow(workflow)

    assert "ci gui-render job missing Qt EGL runtime library for PyQt6: libegl1" in errors


def test_ci_workflow_requires_current_macos_intel_and_apple_silicon_smoke_runners() -> None:
    checker = _load_checker()
    source = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    for runner in ("macos-26-intel", "macos-14", "macos-15", "macos-26"):
        for version in ("3.12", "3.13", "3.14"):
            workflow = source.replace(
                f'          - os: {runner}\n            python-version: "{version}"\n',
                "",
            )

            errors = checker.check_ci_workflow(workflow)

            assert f"ci test matrix missing macOS smoke row: {runner} Python {version}" in errors


def test_ci_workflow_requires_bounded_live_gui_render_timeouts() -> None:
    checker = _load_checker()
    workflow_without_job_timeout = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "    timeout-minutes: 15\n",
        "",
    )
    workflow_without_step_timeout = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "        timeout-minutes: 8\n",
        "",
    )

    job_errors = checker.check_ci_workflow(workflow_without_job_timeout)
    step_errors = checker.check_ci_workflow(workflow_without_step_timeout)

    assert "ci gui-render job missing bounded live GUI render job timeout: timeout-minutes: 15" in job_errors
    assert "ci gui-render job missing bounded live GUI render smoke step timeout: timeout-minutes: 8" in step_errors


def test_ci_workflow_requires_live_gui_artifact_validation_before_upload() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "      - name: Validate real GUI render artifact\n"
        "        timeout-minutes: 2\n"
        "        run: python scripts/check_real_gui_render_artifact.py --artifact-dir artifacts/gui-real\n",
        "",
    )

    errors = checker.check_ci_workflow(workflow)

    assert any("ci gui-render job missing live GUI artifact validator" in error for error in errors)


def test_ci_workflow_requires_checkout_credentials_disabled() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "          persist-credentials: false\n",
        "",
        1,
    )

    errors = checker.check_ci_workflow(workflow)

    assert "every ci checkout step must set persist-credentials: false" in errors


def _load_checker():
    path = Path("scripts/check_ci_workflow.py")
    spec = importlib.util.spec_from_file_location("check_ci_workflow_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

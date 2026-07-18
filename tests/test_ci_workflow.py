from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def test_ci_workflow_checker_passes_current_tree() -> None:
    checker = _load_checker()

    assert checker.main() == 0


def test_ci_workflow_requires_single_row_policy_verifier() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "  repo-policy:",
        "  repo_policy_disabled:",
    )

    errors = checker.check_ci_workflow(workflow)

    assert "ci workflow missing repo-policy job for single-row repository gates" in errors


def test_ci_workflow_scopes_pushes_to_main_and_cancels_superseded_runs() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    push_errors = checker.check_ci_workflow(
        workflow.replace("  push:\n    branches: [main]\n", "  push:\n")
    )
    concurrency_errors = checker.check_ci_workflow(
        workflow.replace("  cancel-in-progress: true\n", "")
    )

    assert "ci workflow must run on pushes to main" in push_errors
    assert any("cancel superseded runs" in error for error in concurrency_errors)


def test_ci_workflow_requires_policy_job_lint_and_quick_verifier() -> None:
    checker = _load_checker()
    workflow_without_ruff = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "      - name: Ruff lint\n"
        "        run: python -m ruff check src tests scripts\n",
        "",
    )
    workflow_without_quick_verify = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "        run: python scripts/verify.py --quick\n",
        "        run: python scripts/verify.py\n",
    )

    ruff_errors = checker.check_ci_workflow(workflow_without_ruff)
    verify_errors = checker.check_ci_workflow(workflow_without_quick_verify)

    assert any("ci repo-policy job missing single-row ruff lint" in error for error in ruff_errors)
    assert any("ci repo-policy job missing single-row repository verifier" in error for error in verify_errors)


def test_ci_workflow_requires_dependency_vulnerability_audit() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "      - name: Dependency vulnerability audit\n"
        "        run: >-\n"
        '          python -c "import truststore; truststore.inject_into_ssl(); from pip_audit._cli import audit; audit()"\n'
        "          --strict --no-deps --disable-pip -r requirements-release.txt\n",
        "",
    )

    errors = checker.check_ci_workflow(workflow)

    assert any("dependency vulnerability audit" in error for error in errors)


def test_ci_workflow_requires_qt_headless_runtime_dependency() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "      - name: Install Qt headless runtime dependency\n"
        "        run: |\n"
        "          sudo apt-get update\n"
        "          sudo apt-get install -y libegl1\n",
        "",
    )

    errors = checker.check_ci_workflow(workflow)

    assert any("Qt headless runtime dependency" in error for error in errors)


def test_ci_workflow_test_matrix_runs_pytest_not_monolithic_verifier() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "        run: python -m pytest -q\n",
        "        run: python scripts/verify.py --lint\n",
    )

    errors = checker.check_ci_workflow(workflow)

    assert "ci test job must run pytest directly" in errors
    assert "ci test matrix must not fan out the monolithic lint verifier" in errors


def test_ci_workflow_requires_bounded_test_matrix_timeout() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "    timeout-minutes: 30\n",
        "",
    )

    errors = checker.check_ci_workflow(workflow)

    assert "ci test matrix must have a bounded 30 minute job timeout" in errors


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


def test_ci_workflow_requires_android_sdk_path_setup() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "      - name: Configure Android SDK command-line tools\n"
        "        run: |\n"
        "          set -euo pipefail\n"
        '          sdk_root="${ANDROID_HOME:-${ANDROID_SDK_ROOT:-/usr/local/lib/android/sdk}}"\n'
        '          sdk_tools="$sdk_root/cmdline-tools/latest/bin"\n'
        '          if [[ ! -x "$sdk_tools/sdkmanager" || ! -x "$sdk_tools/avdmanager" ]]; then\n'
        '            echo "::error::Android SDK command-line tools not found under $sdk_tools"\n'
        '            find "$sdk_root" -maxdepth 4 -type f \\( -name sdkmanager -o -name avdmanager \\) -print || true\n'
        "            exit 1\n"
        "          fi\n"
        '          avd_home="${RUNNER_TEMP:-$HOME}/android-avd"\n'
        '          mkdir -p "$avd_home"\n'
        '          echo "ANDROID_HOME=$sdk_root" >> "$GITHUB_ENV"\n'
        '          echo "ANDROID_SDK_ROOT=$sdk_root" >> "$GITHUB_ENV"\n'
        '          echo "ANDROID_AVD_HOME=$avd_home" >> "$GITHUB_ENV"\n'
        '          echo "$sdk_tools" >> "$GITHUB_PATH"\n'
        '          echo "$sdk_root/emulator" >> "$GITHUB_PATH"\n'
        '          echo "$sdk_root/platform-tools" >> "$GITHUB_PATH"\n'
        '          "$sdk_tools/sdkmanager" --version\n',
        "",
    )

    errors = checker.check_ci_workflow(workflow)

    assert any("Android SDK command-line tools PATH setup" in error for error in errors)


def test_ci_workflow_requires_android_sdk_archive_recovery() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "          for attempt in 1 2 3; do\n",
        "",
    )

    errors = checker.check_ci_workflow(workflow)

    assert any("bounded Android SDK installation retries" in error for error in errors)


def test_ci_workflow_requires_durable_android_avd_home_and_creation_assertion() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    workflow_without_avd_home = workflow.replace(
        '          echo "ANDROID_AVD_HOME=$avd_home" >> "$GITHUB_ENV"\n',
        "",
    )
    workflow_without_creation_listing = workflow.replace("          avdmanager list avd\n", "")
    workflow_without_creation_assertion = workflow.replace(
        '            echo "::error::Android AVD row-api-${{ matrix.api-level }} was not created under ANDROID_AVD_HOME=$ANDROID_AVD_HOME"\n',
        "",
    )

    avd_home_errors = checker.check_ci_workflow(workflow_without_avd_home)
    creation_listing_errors = checker.check_ci_workflow(workflow_without_creation_listing)
    creation_assertion_errors = checker.check_ci_workflow(workflow_without_creation_assertion)

    assert any("durable Android AVD home export" in error for error in avd_home_errors)
    assert any("Android virtual device creation diagnostics" in error for error in creation_listing_errors)
    assert any("Android virtual device creation assertion" in error for error in creation_assertion_errors)


def test_ci_workflow_requires_bounded_android_emulator_boot_diagnostics() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    workflow_without_step_timeout = workflow.replace("        timeout-minutes: 8\n", "", 1)
    workflow_without_avd_listing = workflow.replace("          emulator -list-avds\n", "")
    workflow_without_preboot_assertion = workflow.replace(
        '            echo "::error::Android AVD row-api-${{ matrix.api-level }} missing before emulator boot; ANDROID_AVD_HOME=$ANDROID_AVD_HOME"\n',
        "",
    )
    workflow_without_pid_tracking = workflow.replace('          echo "$emulator_pid" > emulator.pid\n', "")
    workflow_without_connection_diagnostic = workflow.replace(
        '              echo "::error::Android emulator did not appear in adb devices within 180 seconds"\n',
        "",
    )
    workflow_without_boot_diagnostic = workflow.replace(
        '            echo "::error::Android emulator did not complete boot within 180 seconds"\n',
        "",
    )
    workflow_without_log_tail = workflow.replace("              tail -200 emulator.log || true\n", "").replace(
        "            tail -200 emulator.log || true\n",
        "",
    )

    step_timeout_errors = checker.check_ci_workflow(workflow_without_step_timeout)
    avd_listing_errors = checker.check_ci_workflow(workflow_without_avd_listing)
    preboot_assertion_errors = checker.check_ci_workflow(workflow_without_preboot_assertion)
    pid_tracking_errors = checker.check_ci_workflow(workflow_without_pid_tracking)
    connection_diagnostic_errors = checker.check_ci_workflow(workflow_without_connection_diagnostic)
    boot_diagnostic_errors = checker.check_ci_workflow(workflow_without_boot_diagnostic)
    log_tail_errors = checker.check_ci_workflow(workflow_without_log_tail)

    assert any("bounded Android emulator boot timeout" in error for error in step_timeout_errors)
    assert any("Android emulator AVD visibility diagnostics" in error for error in avd_listing_errors)
    assert any("Android emulator pre-boot AVD assertion" in error for error in preboot_assertion_errors)
    assert any("Android emulator process tracking" in error for error in pid_tracking_errors)
    assert any("Android emulator adb connection timeout diagnostic" in error for error in connection_diagnostic_errors)
    assert any("Android emulator boot-completion timeout diagnostic" in error for error in boot_diagnostic_errors)
    assert any("Android emulator log diagnostics" in error for error in log_tail_errors)


def test_ci_workflow_requires_ios_simulator_web_job() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "  ios-simulator-web:",
        "  ios_simulator_web_disabled:",
    )

    errors = checker.check_ci_workflow(workflow)

    assert "ci workflow missing ios-simulator-web job for iOS Web/PWA smoke" in errors


def test_ci_workflow_requires_ios_server_readiness_before_simulator_smoke() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    workflow_without_bind = workflow.replace(
        'python -m http.server "$WEB_PWA_PORT" --directory apps/web --bind 127.0.0.1',
        'python -m http.server "$WEB_PWA_PORT" --directory apps/web',
    )
    workflow_without_dynamic_port = workflow.replace(
        '          sock.bind(("127.0.0.1", 0))\n',
        "",
    )
    workflow_without_url_export = workflow.replace(
        '          export WEB_PWA_URL="http://127.0.0.1:${WEB_PWA_PORT}/index.html"\n',
        "",
    )
    workflow_without_probe = workflow.replace(
        '          with urllib.request.urlopen(os.environ["WEB_PWA_URL"], timeout=3) as response:\n',
        "",
    )
    workflow_without_timeout_budget = workflow.replace(
        "          deadline = time.monotonic() + 90\n",
        "          deadline = time.monotonic() + 30\n",
    )
    workflow_without_clear_error = workflow.replace(
        '              "Web/PWA server did not become reachable before iOS simulator smoke: "\n',
        "",
    )
    workflow_without_smoke_url = workflow.replace(
        '--url "$WEB_PWA_URL"',
        "--url http://127.0.0.1:8765/index.html",
    )

    bind_errors = checker.check_ci_workflow(workflow_without_bind)
    dynamic_port_errors = checker.check_ci_workflow(workflow_without_dynamic_port)
    url_export_errors = checker.check_ci_workflow(workflow_without_url_export)
    probe_errors = checker.check_ci_workflow(workflow_without_probe)
    timeout_budget_errors = checker.check_ci_workflow(workflow_without_timeout_budget)
    message_errors = checker.check_ci_workflow(workflow_without_clear_error)
    smoke_url_errors = checker.check_ci_workflow(workflow_without_smoke_url)

    assert any("loopback-bound dynamic local Web/PWA server" in error for error in bind_errors)
    assert any("dynamic loopback Web/PWA server port" in error for error in dynamic_port_errors)
    assert any("exported iOS Web/PWA server URL" in error for error in url_export_errors)
    assert any("iOS Web/PWA server readiness probe" in error for error in probe_errors)
    assert any("iOS Web/PWA server readiness timeout budget" in error for error in timeout_budget_errors)
    assert any("clear iOS Web/PWA server readiness failure" in error for error in message_errors)
    assert any("iOS simulator host loopback URL" in error for error in smoke_url_errors)


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


def test_ci_workflow_rejects_unknown_hosted_runner_labels() -> None:
    checker = _load_checker()
    workflow_with_unknown_matrix_runner = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "windows-2025-vs2026",
        "windows-2025-vs20260",
        1,
    )
    workflow_with_unknown_direct_runner = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "runs-on: macos-26",
        "runs-on: macos-260",
        1,
    )

    matrix_errors = checker.check_ci_workflow(workflow_with_unknown_matrix_runner)
    direct_errors = checker.check_ci_workflow(workflow_with_unknown_direct_runner)

    assert any("unsupported GitHub-hosted runner label 'windows-2025-vs20260'" in error for error in matrix_errors)
    assert any("unsupported GitHub-hosted runner label 'macos-260'" in error for error in direct_errors)


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


def test_ci_workflow_requires_linux_and_native_windows_gui_interaction_gates() -> None:
    checker = _load_checker()
    source = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    without_linux_gate = source.replace(
        "      - name: Exercise GUI controls and responsive layouts\n"
        "        timeout-minutes: 5\n"
        "        run: python scripts/check_gui_interactions.py --require-pyqt6 --out-dir artifacts/gui-interactions\n",
        "",
    )
    without_windows_job = source.replace(
        "  gui-interactions-windows:",
        "  gui_interactions_windows_disabled:",
    )
    wrong_windows_runner = source.replace(
        "  gui-interactions-windows:\n"
        "    name: Native Windows PyQt6 render and interactions\n"
        "    runs-on: windows-2025-vs2026\n",
        "  gui-interactions-windows:\n"
        "    name: Native Windows PyQt6 render and interactions\n"
        "    runs-on: ubuntu-latest\n",
    )

    linux_errors = checker.check_ci_workflow(without_linux_gate)
    missing_windows_errors = checker.check_ci_workflow(without_windows_job)
    runner_errors = checker.check_ci_workflow(wrong_windows_runner)

    assert any(
        "ci gui-render job missing Linux GUI interaction gate" in error for error in linux_errors
    )
    assert (
        "ci workflow missing gui-interactions-windows job for native Windows PyQt6 controls"
        in missing_windows_errors
    )
    assert any("repository-approved native Windows runner" in error for error in runner_errors)


def test_ci_workflow_requires_fonts_and_native_windows_full_renderer() -> None:
    checker = _load_checker()
    source = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    without_linux_font = source.replace("            fonts-dejavu-core \\\n", "")
    without_native_renderer = source.replace(
        "      - name: Render full GUI on native Windows\n"
        "        timeout-minutes: 8\n"
        "        run: python scripts/check_real_gui_render.py --require-pyqt6 --timeout-seconds 240 --out-dir artifacts/gui-real-windows\n",
        "",
    )

    font_errors = checker.check_ci_workflow(without_linux_font)
    native_renderer_errors = checker.check_ci_workflow(without_native_renderer)

    assert any("known readable Linux GUI font" in error for error in font_errors)
    assert any(
        "native Windows all-preset GUI render gate" in error
        for error in native_renderer_errors
    )


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

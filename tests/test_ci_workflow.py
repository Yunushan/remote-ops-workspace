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


def test_ci_workflow_requires_cross_platform_gui_type_safety() -> None:
    checker = _load_checker()
    source = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    labels = {
        "linux": "Linux",
        "win32": "Windows",
        "darwin": "macOS",
    }

    for platform in ("linux", "win32", "darwin"):
        workflow = source.replace(
            "python -m mypy src/remote_ops_workspace/gui.py "
            f"--platform {platform}",
            "python -m mypy src/remote_ops_workspace/gui.py "
            f"--platform removed-{platform}",
        )

        errors = checker.check_ci_workflow(workflow)

        assert any(
            f"{labels[platform]} GUI type-safety gate" in error
            for error in errors
        )


def test_ci_workflow_requires_non_gui_production_type_gate() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "      - name: Non-GUI production type gate\n"
        "        run: python scripts/check_non_gui_types.py\n",
        "",
    )

    errors = checker.check_ci_workflow(workflow)

    assert any("bounded non-GUI production type gate" in error for error in errors)


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


def test_ci_workflow_requires_enforced_branch_coverage_job() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "  coverage:",
        "  coverage_disabled:",
    )

    errors = checker.check_ci_workflow(workflow)

    assert "ci workflow missing coverage job for enforced Python branch coverage" in errors


def test_ci_workflow_rejects_reduced_or_advisory_coverage_gate() -> None:
    checker = _load_checker()
    source = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    reduced_threshold = source.replace("--cov-fail-under=100", "--cov-fail-under=99.9")
    reduced_validated_total = source.replace("--min-total 100", "--min-total 99.9")
    reduced_branch_threshold = source.replace("--min-branches 100", "--min-branches 99.9")
    advisory_gate = source.replace(
        "  coverage:\n    name: Python branch-aware coverage\n",
        "  coverage:\n    continue-on-error: true\n    name: Python branch-aware coverage\n",
    )

    threshold_errors = checker.check_ci_workflow(reduced_threshold)
    total_errors = checker.check_ci_workflow(reduced_validated_total)
    branch_errors = checker.check_ci_workflow(reduced_branch_threshold)
    advisory_errors = checker.check_ci_workflow(advisory_gate)

    assert any("aggregate coverage failure threshold" in error for error in threshold_errors)
    assert any("validated aggregate coverage threshold" in error for error in total_errors)
    assert any("pure branch coverage threshold" in error for error in branch_errors)
    assert "ci coverage job must remain release-blocking" in advisory_errors


def test_ci_workflow_requires_branch_and_machine_readable_coverage_evidence() -> None:
    checker = _load_checker()
    source = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    without_branch = source.replace("          --cov-branch\n", "")
    without_xml = source.replace(
        "          --cov-report=xml:artifacts/coverage/coverage.xml\n",
        "",
    )
    without_json = source.replace(
        "          --cov-report=json:artifacts/coverage/coverage.json\n",
        "",
    )

    branch_errors = checker.check_ci_workflow(without_branch)
    xml_errors = checker.check_ci_workflow(without_xml)
    json_errors = checker.check_ci_workflow(without_json)

    assert any("branch coverage measurement" in error for error in branch_errors)
    assert any("XML coverage evidence" in error for error in xml_errors)
    assert any("JSON coverage evidence" in error for error in json_errors)


def test_ci_workflow_requires_independent_coverage_report_validation() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "          python scripts/check_coverage_report.py\n",
        "          python -c 'print(\"coverage accepted\")'\n",
    )

    errors = checker.check_ci_workflow(workflow)

    assert any("aggregate and branch report validator" in error for error in errors)


def test_ci_workflow_requires_stable_windows_coverage_runner() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "    runs-on: windows-2025-vs2026\n",
        "    runs-on: ubuntu-latest\n",
        1,
    )

    errors = checker.check_ci_workflow(workflow)

    assert any("stable Windows coverage runner" in error for error in errors)


def test_ci_workflow_requires_headless_qt_coverage_platform() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        '      QT_QPA_PLATFORM: "offscreen"\n',
        '      QT_QPA_PLATFORM: "windows"\n',
        1,
    )

    errors = checker.check_ci_workflow(workflow)

    assert any("deterministic headless Qt coverage platform" in error for error in errors)


def test_ci_workflow_requires_coverage_evidence_directory() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "        run: New-Item -ItemType Directory -Force -Path artifacts/coverage | Out-Null\n",
        "",
    )

    errors = checker.check_ci_workflow(workflow)

    assert any("explicit Windows coverage evidence directory" in error for error in errors)


def test_ci_workflow_test_matrix_runs_pytest_not_monolithic_verifier() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "        run: python -m pytest -q\n",
        "        run: python scripts/verify.py --lint\n",
    )

    errors = checker.check_ci_workflow(workflow)

    assert "ci test job must run pytest directly" in errors
    assert "ci test matrix must not fan out the monolithic lint verifier" in errors


def test_ci_workflow_requires_intel_macos_maintained_security_source_build() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        '          python -m pip install --no-cache-dir --no-build-isolation --no-binary=cryptography --constraint requirements-release.txt -e ".[security,dev]"\n',
        '          python -m pip install -e ".[security,dev]"\n',
    )

    errors = checker.check_ci_workflow(workflow)

    assert any("maintained Intel macOS cryptography source build" in error for error in errors)


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


def test_ci_workflow_requires_live_web_container_smoke_job() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "  web-container:",
        "  web_container_disabled:",
    )

    errors = checker.check_ci_workflow(workflow)

    assert "ci workflow missing web-container job for live Web/PWA container smoke" in errors


def test_ci_workflow_requires_writable_non_root_web_data_volume() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "          compose exec -T remote-ops-web sh -c 'test -w /data && touch /data/.row-write-smoke && rm /data/.row-write-smoke'\n",
        "",
    )

    errors = checker.check_ci_workflow(workflow)

    assert any("writable non-root data-volume smoke" in error for error in errors)


def test_ci_workflow_requires_destructive_web_recovery_job() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "  web-recovery:",
        "  web_recovery_disabled:",
    )

    errors = checker.check_ci_workflow(workflow)

    assert "ci workflow missing web-recovery job for destructive backup and restore evidence" in errors


def test_ci_workflow_requires_source_bound_recovery_evidence() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        '            --source-sha "$GITHUB_SHA" \\\n',
        "",
    )

    errors = checker.check_ci_workflow(workflow)

    assert any("source-bound recovery evidence" in error for error in errors)


def test_ci_workflow_requires_failure_path_recovery_evidence_upload() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "        if: ${{ always() }}\n",
        "",
    )

    errors = checker.check_ci_workflow(workflow)

    assert any("failure-path evidence retention" in error for error in errors)


def test_ci_workflow_rejects_recovery_backup_payload_upload() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "          path: artifacts/recovery/web-recovery-evidence.json\n",
        "          path: artifacts/recovery/remote-ops-data.tar.gz\n",
    )

    errors = checker.check_ci_workflow(workflow)

    assert "ci web-recovery job must not upload backup payloads" in errors


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


def test_ci_workflow_requires_android_google_apis_image_for_hosted_smoke() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "google_apis;x86_64",
        "google_apis_playstore;x86_64",
    )

    errors = checker.check_ci_workflow(workflow)

    assert any("Android Google APIs system image for reliable hosted boot" in error for error in errors)


def test_ci_workflow_requires_real_android_web_response_coverage() -> None:
    checker = _load_checker()
    source = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    workflow_without_server = source.replace(
        '          python -m http.server "$WEB_PWA_PORT" --directory apps/web --bind 127.0.0.1 > web-server.log 2>&1 &\n',
        "",
    )
    workflow_without_reverse = source.replace(
        '          adb reverse "tcp:${WEB_PWA_PORT}" "tcp:${WEB_PWA_PORT}"\n',
        "",
    )
    workflow_with_skip = source.replace(
        ' --url "$WEB_PWA_URL" --out-dir artifacts/mobile',
        ' --url "$WEB_PWA_URL" --skip-web-response --out-dir artifacts/mobile',
    )
    workflow_without_response_timeout = source.replace(
        "      - name: Android emulator Web/PWA response smoke\n        timeout-minutes: 2\n",
        "      - name: Android emulator Web/PWA response smoke\n",
    )

    server_errors = checker.check_ci_workflow(workflow_without_server)
    reverse_errors = checker.check_ci_workflow(workflow_without_reverse)
    skip_errors = checker.check_ci_workflow(workflow_with_skip)
    timeout_errors = checker.check_ci_workflow(workflow_without_response_timeout)

    assert any("loopback-only host Web/PWA server" in error for error in server_errors)
    assert any("Android reverse-port mapping" in error for error in reverse_errors)
    assert any("must not skip the emulator Web/PWA response assertion" in error for error in skip_errors)
    assert any("bounded Android Web/PWA response smoke timeout" in error for error in timeout_errors)


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
    workflow_without_step_timeout = workflow.replace(
        "      - name: Boot Android emulator\n"
        "        timeout-minutes: 8\n",
        "      - name: Boot Android emulator\n",
        1,
    )
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
        for version in ("3.12", "3.13", "3.14", "3.15"):
            workflow = source.replace(
                f'          - os: {runner}\n            python-version: "{version}"\n',
                "",
            )

            errors = checker.check_ci_workflow(workflow)

            assert f"ci test matrix missing macOS smoke row: {runner} Python {version}" in errors


def test_ci_workflow_requires_python_315_linux_and_windows_arm64_smoke_rows() -> None:
    checker = _load_checker()
    source = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    for runner in ("ubuntu-24.04-arm", "windows-11-arm"):
        workflow = source.replace(
            f'          - os: {runner}\n            python-version: "3.15"\n',
            "",
            1,
        )

        errors = checker.check_ci_workflow(workflow)

        assert (
            f"ci test matrix missing modern ARM64 smoke row: {runner} Python 3.15"
            in errors
        )


def test_ci_workflow_requires_windows_arm64_security_source_build_in_both_jobs() -> None:
    checker = _load_checker()
    source = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    step = """      - name: Prepare pinned Windows ARM64 security source build
        if: runner.os == 'Windows' && runner.arch == 'ARM64'
        shell: powershell
        run: .\\scripts\\install_windows_arm64_security.ps1
"""

    assert source.count(step) == 2
    without_first = source.replace(step, "", 1)
    without_both = source.replace(step, "")

    assert any(
        "ci test job missing maintained Windows ARM64 security source-build step" in error
        for error in checker.check_ci_workflow(without_first)
    )
    assert any(
        "ci python315-optional-dependencies job missing maintained Windows ARM64 "
        "security source-build step" in error
        for error in checker.check_ci_workflow(without_both)
    )


def test_ci_workflow_requires_python_315_prerelease_resolution() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "          allow-prereleases: true\n",
        "",
    )

    errors = checker.check_ci_workflow(workflow)

    assert (
        "ci test job must allow the Python 3.15 prerelease until upstream GA is available"
        in errors
    )


def test_ci_workflow_requires_blocking_python_315_optional_dependency_job() -> None:
    checker = _load_checker()
    source = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    missing_job = source.replace(
        "  python315-optional-dependencies:",
        "  python315_optional_dependencies_disabled:",
    )
    advisory_job = source.replace(
        "  python315-optional-dependencies:\n",
        "  python315-optional-dependencies:\n    continue-on-error: true\n",
    )

    assert (
        "ci workflow missing python315-optional-dependencies job for Python 3.15 "
        "optional dependency and distribution verification"
        in checker.check_ci_workflow(missing_job)
    )
    assert (
        "ci python315-optional-dependencies job must remain release-blocking"
        in checker.check_ci_workflow(advisory_job)
    )


def test_ci_workflow_requires_python_315_qtwidgets_startup_and_real_gui_evidence() -> None:
    checker = _load_checker()
    source = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    without_qapplication = source.replace("app = QApplication([])", "app = object()")
    without_widget_paint = source.replace(
        "assert not label.grab().isNull()",
        "assert label.isVisible()",
    )
    without_real_renderer = source.replace(
        "python scripts/check_real_gui_render.py --out-dir artifacts/python315-gui",
        "python scripts/check_real_gui_render.py --preset native --out-dir artifacts/python315-gui",
    )
    without_gui_artifact = source.replace(
        "name: python315-gui-${{ matrix.os }}",
        "name: python315-imports-${{ matrix.os }}",
    )
    without_native_render_platform = source.replace(
        "          QT_QPA_PLATFORM: ${{ matrix.qt_platform }}\n",
        "",
    )
    without_macos_offscreen = source.replace(
        "          - os: macos-15-intel\n"
        "            # Hosted macOS is not guaranteed to expose a logged-in WindowServer.\n"
        "            # Keep the full application render deterministic and headless there.\n"
        '            qt_platform: "offscreen"',
        "          - os: macos-15-intel\n"
        '            qt_platform: "cocoa"',
    )

    assert any(
        "real Python 3.15 QApplication startup" in error
        for error in checker.check_ci_workflow(without_qapplication)
    )
    assert any(
        "Python 3.15 Qt widget paint assertion" in error
        for error in checker.check_ci_workflow(without_widget_paint)
    )
    assert any(
        "Python 3.15 all-preset application GUI renderer" in error
        for error in checker.check_ci_workflow(without_real_renderer)
    )
    assert (
        "ci python315-optional-dependencies job must render the default complete preset set"
        in checker.check_ci_workflow(without_real_renderer)
    )
    assert any(
        "per-host Python 3.15 GUI artifact" in error
        for error in checker.check_ci_workflow(without_gui_artifact)
    )
    assert any(
        "host-native Python 3.15 full GUI render override" in error
        for error in checker.check_ci_workflow(without_native_render_platform)
    )
    assert any(
        "hosted macOS offscreen real-GUI render platform" in error
        for error in checker.check_ci_workflow(without_macos_offscreen)
    )


def test_ci_workflow_requires_comprehensive_python_315_dependency_and_package_evidence() -> None:
    checker = _load_checker()
    source = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    mutations = {
        'python -m pip install -e ".[desktop,security,package,dev]"': (
            'python -m pip install -e ".[desktop,security,dev]"',
            "complete Python 3.15 optional dependency installation",
        ),
        'python -m pip install "paramiko==5.0.0"': (
            "python -m pip list",
            "pinned Python 3.15 loopback SSH evidence dependency",
        ),
        "python -m pip check": ("python -m pip list", "dependency consistency gate"),
        "python scripts/check_optional_dependencies.py --require-extra desktop --require-extra security --require-extra package --require-extra dev": (
            "python scripts/check_optional_dependencies.py",
            "desktop, security, package and development extra smoke",
        ),
        "python -m PyInstaller --version": (
            "python -c \"print('packager skipped')\"",
            "PyInstaller startup smoke",
        ),
        "python scripts/write_python_runtime_evidence.py --expected-version 3.15": (
            "python -c \"print('runtime unrecorded')\"",
            "exact Python 3.15 runtime evidence producer",
        ),
        "python scripts/check_gui_interactions.py --require-pyqt6": (
            "python -c \"print('interactions skipped')\"",
            "all-preset GUI interaction gate",
        ),
        "python scripts/check_python_distribution_install.py": (
            "python -c \"print('distribution install skipped')\"",
            "clean Python 3.15 wheel and sdist installation verifier",
        ),
        "python -m pytest -q tests/test_windows_ssh_loopback.py": (
            "python -m pytest -q tests/test_windows_conpty.py",
            "real Python 3.15 native Windows OpenSSH/ConPTY loopback tests",
        ),
    }

    for original, (replacement, expected_error) in mutations.items():
        errors = checker.check_ci_workflow(source.replace(original, replacement, 1))

        assert any(expected_error in error for error in errors)


def test_ci_workflow_requires_durable_python_315_evidence_uploads() -> None:
    checker = _load_checker()
    source = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    without_runtime_artifact = source.replace(
        "          name: python315-runtime-${{ matrix.os }}\n",
        "          name: python315-runtime-removed-${{ matrix.os }}\n",
    )
    without_windows_ssh_artifact = source.replace(
        "          name: python315-windows-ssh-${{ matrix.os }}\n",
        "          name: python315-windows-ssh-removed-${{ matrix.os }}\n",
    )
    advisory_windows_ssh = source.replace(
        "        if: ${{ always() && runner.os == 'Windows' }}\n",
        "        if: ${{ runner.os == 'Windows' }}\n",
        1,
    )
    short_retention = source.replace("          retention-days: 90\n", "", 1)

    runtime_errors = checker.check_ci_workflow(without_runtime_artifact)
    windows_ssh_errors = checker.check_ci_workflow(without_windows_ssh_artifact)
    advisory_windows_ssh_errors = checker.check_ci_workflow(advisory_windows_ssh)
    retention_errors = checker.check_ci_workflow(short_retention)

    assert any("per-host exact Python 3.15 runtime artifact" in error for error in runtime_errors)
    assert any(
        "per-host Python 3.15 native Windows SSH artifact" in error
        for error in windows_ssh_errors
    )
    assert any(
        "fail-closed retained Python 3.15 native Windows SSH evidence upload" in error
        for error in advisory_windows_ssh_errors
    )
    assert (
        "ci Python 3.15 evidence artifacts must retain all six declared groups for 90 days"
        in retention_errors
    )


def test_ci_workflow_requires_fail_closed_python315_readiness_aggregate() -> None:
    checker = _load_checker()
    source = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    without_normal_need = source.replace(
        "    needs: [test, python315-optional-dependencies]\n",
        "    needs: [python315-optional-dependencies]\n",
        1,
    )
    without_always = source.replace(
        "  python315-readiness:\n"
        "    name: Python 3.15 readiness\n"
        "    needs: [test, python315-optional-dependencies]\n"
        "    if: ${{ always() }}\n",
        "  python315-readiness:\n"
        "    name: Python 3.15 readiness\n"
        "    needs: [test, python315-optional-dependencies]\n",
        1,
    )
    advisory = source.replace(
        "  python315-readiness:\n",
        "  python315-readiness:\n    continue-on-error: true\n",
        1,
    )

    assert any(
        "readiness aggregate missing active needs" in error
        for error in checker.check_ci_workflow(without_normal_need)
    )
    assert any(
        "readiness aggregate missing active always" in error
        for error in checker.check_ci_workflow(without_always)
    )
    assert "ci Python 3.15 readiness aggregate must fail closed" in (
        checker.check_ci_workflow(advisory)
    )


def test_ci_workflow_rejects_comment_only_python315_readiness_assertions() -> None:
    checker = _load_checker()
    source = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    for command, label in (
        ('          test "$NORMAL_MATRIX_RESULT" = "success"', "normal success assertion"),
        (
            '          test "$OPTIONAL_MATRIX_RESULT" = "success"',
            "optional success assertion",
        ),
    ):
        workflow = source.replace(command, f"          # {command.strip()}", 1)
        errors = checker.check_ci_workflow(workflow)

        assert any(f"missing active {label}" in error for error in errors)


def test_ci_workflow_requires_fail_closed_native_windows_readiness_aggregate() -> None:
    checker = _load_checker()
    source = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    without_gui_need = source.replace(
        "    needs: [gui-interactions-windows]\n",
        "    needs: []\n",
        1,
    )
    without_always = source.replace(
        "  native-windows-readiness:\n"
        "    name: Native Windows readiness\n"
        "    needs: [gui-interactions-windows]\n"
        "    if: ${{ always() }}\n",
        "  native-windows-readiness:\n"
        "    name: Native Windows readiness\n"
        "    needs: [gui-interactions-windows]\n",
        1,
    )
    advisory = source.replace(
        "  native-windows-readiness:\n",
        "  native-windows-readiness:\n    continue-on-error: true\n",
        1,
    )

    assert any(
        "Native Windows readiness aggregate missing active needs" in error
        for error in checker.check_ci_workflow(without_gui_need)
    )
    assert any(
        "Native Windows readiness aggregate missing active always" in error
        for error in checker.check_ci_workflow(without_always)
    )
    assert "ci Native Windows readiness aggregate must fail closed" in (
        checker.check_ci_workflow(advisory)
    )


def test_ci_workflow_rejects_comment_only_native_windows_readiness_assertions() -> None:
    checker = _load_checker()
    source = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    for command, label in (
        (
            '          test "$NATIVE_WINDOWS_RESULT" = "success"',
            "native Windows success assertion",
        ),
    ):
        workflow = source.replace(command, f"          # {command.strip()}", 1)
        errors = checker.check_ci_workflow(workflow)

        assert any(f"missing active {label}" in error for error in errors)


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


def test_ci_workflow_requires_real_windows_conpty_transport_tests() -> None:
    checker = _load_checker()
    source = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    without_conpty_tests = source.replace(
        "      - name: Verify real Windows ConPTY terminal transport\n"
        "        timeout-minutes: 5\n"
        "        run: python -m pytest -q tests/test_windows_conpty.py tests/test_qt_terminal_process.py\n",
        "",
    )

    errors = checker.check_ci_workflow(without_conpty_tests)

    assert any("real Windows ConPTY transport" in error for error in errors)


def test_ci_workflow_requires_authenticated_windows_ssh_loopback_gate() -> None:
    checker = _load_checker()
    source = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    without_loopback_gate = source.replace(
        "      - name: Verify native Windows OpenSSH authentication through Qt ConPTY\n"
        "        timeout-minutes: 5\n"
        "        run: python -m pytest -q tests/test_windows_ssh_loopback.py --junitxml=artifacts/windows-ssh-loopback/junit.xml\n",
        "",
    )
    without_required_mode = source.replace(
        '      ROW_REQUIRE_WINDOWS_SSH_LOOPBACK: "1"\n',
        "",
    )
    without_evidence_contract = source.replace(
        "      ROW_WINDOWS_SSH_EVIDENCE_DIR: artifacts/windows-ssh-loopback\n",
        "",
    )
    without_pinned_server = source.replace(
        "      - name: Install pinned loopback SSH test server\n"
        '        run: python -m pip install "paramiko==5.0.0"\n',
        "",
    )
    without_evidence_upload = source.replace(
        "      - uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7\n"
        "        with:\n"
        "          name: windows-ssh-loopback-conpty\n"
        "          path: artifacts/windows-ssh-loopback/*\n"
        "          if-no-files-found: error\n",
        "",
    )

    gate_errors = checker.check_ci_workflow(without_loopback_gate)
    required_errors = checker.check_ci_workflow(without_required_mode)
    evidence_contract_errors = checker.check_ci_workflow(without_evidence_contract)
    dependency_errors = checker.check_ci_workflow(without_pinned_server)
    artifact_errors = checker.check_ci_workflow(without_evidence_upload)

    assert any("authenticated native OpenSSH" in error for error in gate_errors)
    assert any("release-blocking native Windows SSH" in error for error in required_errors)
    assert any(
        "SSH structured evidence output" in error for error in evidence_contract_errors
    )
    assert any("pinned secret-free loopback SSH" in error for error in dependency_errors)
    assert any("SSH loopback evidence artifact" in error for error in artifact_errors)


def test_ci_workflow_rejects_comment_only_native_windows_ssh_and_gui_lines() -> None:
    checker = _load_checker()
    source = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    active_lines = (
        (
            '      ROW_REQUIRE_WINDOWS_SSH_LOOPBACK: "1"',
            "release-blocking native Windows SSH loopback contract",
        ),
        (
            "        run: python -m pytest -q tests/test_windows_ssh_loopback.py --junitxml=artifacts/windows-ssh-loopback/junit.xml",
            "native Windows OpenSSH loopback authentication and I/O test",
        ),
        (
            "        run: python scripts/check_real_gui_render.py --require-pyqt6 --timeout-seconds 240 --out-dir artifacts/gui-real-windows",
            "native Windows all-preset GUI render gate",
        ),
        (
            "        run: python scripts/check_gui_interactions.py --require-pyqt6 --out-dir artifacts/gui-interactions-windows",
            "native Windows GUI interaction gate",
        ),
        (
            "        run: python scripts/check_windows_tab_switch_paint.py --require-native-windows --out-dir artifacts/gui-tab-switch-windows",
            "native Windows real tab-bar click and transient paint gate",
        ),
        (
            "          name: windows-ssh-loopback-conpty",
            "native Windows SSH loopback evidence artifact name",
        ),
        (
            "          path: artifacts/windows-ssh-loopback/*",
            "native Windows SSH loopback evidence artifact path",
        ),
    )

    for line, label in active_lines:
        before_job, job_marker, native_job = source.partition("  gui-interactions-windows:\n")
        commented = f"{line[: len(line) - len(line.lstrip())]}# {line.lstrip()}"
        workflow = before_job + job_marker + native_job.replace(line, commented, 1)
        errors = checker.check_ci_workflow(workflow)

        assert any(f"missing active {label}" in error for error in errors)

    commented_runner = source.replace(
        "  gui-interactions-windows:\n"
        "    name: Native Windows PyQt6 render and interactions\n"
        "    runs-on: windows-2025-vs2026\n",
        "  gui-interactions-windows:\n"
        "    name: Native Windows PyQt6 render and interactions\n"
        "    # runs-on: windows-2025-vs2026\n",
        1,
    )
    commented_upload = source.replace(
        "      - uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7\n"
        "        with:\n"
        "          name: gui-real-render-windows\n",
        "      # - uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7\n"
        "        with:\n"
        "          name: gui-real-render-windows\n",
        1,
    )
    commented_fail_closed = source.replace(
        "          name: gui-real-render-windows\n"
        "          path: artifacts/gui-real-windows/*\n"
        "          if-no-files-found: error\n",
        "          name: gui-real-render-windows\n"
        "          path: artifacts/gui-real-windows/*\n"
        "          # if-no-files-found: error\n",
        1,
    )

    assert any(
        "missing active repository-approved native Windows runner" in error
        for error in checker.check_ci_workflow(commented_runner)
    )
    assert any(
        "retain four active evidence uploads" in error
        for error in checker.check_ci_workflow(commented_upload)
    )
    assert any(
        "fail closed for all four evidence uploads" in error
        for error in checker.check_ci_workflow(commented_fail_closed)
    )


def test_ci_workflow_requires_native_windows_tab_switch_paint_gate() -> None:
    checker = _load_checker()
    source = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    without_paint_gate = source.replace(
        "      - name: Capture native Windows terminal tab-switch paint turns\n"
        "        timeout-minutes: 3\n"
        "        run: python scripts/check_windows_tab_switch_paint.py --require-native-windows --out-dir artifacts/gui-tab-switch-windows\n",
        "",
    )
    without_paint_evidence = source.replace(
        "      - uses: actions/upload-artifact@043fb46d1a93c77aae656e7c1c64a875d1fc6a0a # v7\n"
        "        with:\n"
        "          name: gui-tab-switch-paint-windows\n"
        "          path: artifacts/gui-tab-switch-windows/*\n"
        "          if-no-files-found: error\n",
        "",
    )

    gate_errors = checker.check_ci_workflow(without_paint_gate)
    artifact_errors = checker.check_ci_workflow(without_paint_evidence)

    assert any("real tab-bar click" in error for error in gate_errors)
    assert any("terminal tab paint artifact" in error for error in artifact_errors)


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

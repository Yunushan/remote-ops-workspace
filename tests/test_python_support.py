from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def test_python_support_checker_passes_current_tree() -> None:
    checker = load_checker()

    assert checker.check_python_support() == []
    assert checker.main() == 0


def test_python_support_checker_rejects_unbounded_metadata() -> None:
    checker = load_checker()
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8").replace(
        'requires-python = ">=3.10,<3.16"',
        'requires-python = ">=3.10"',
    )

    errors = checker.check_python_support({"pyproject.toml": pyproject})

    assert "pyproject.toml must bound source-host support to >=3.10,<3.16" in errors


def test_python_support_checker_requires_python315_capable_pyinstaller_floor() -> None:
    checker = load_checker()
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8").replace(
        'package = ["build>=1.2", "pyinstaller>=6.21"]',
        'package = ["build>=1.2", "pyinstaller>=6.0"]',
        1,
    )

    errors = checker.check_python_support({"pyproject.toml": pyproject})

    assert (
        "pyproject.toml package extra must require pyinstaller>=6.21 for Python 3.15"
        in errors
    )


def test_python_support_checker_requires_blocking_python315_optional_dependency_ci() -> None:
    checker = load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "  python315-optional-dependencies:\n",
        "  python315-optional-dependencies:\n    continue-on-error: true\n",
    )

    errors = checker.check_python_support({".github/workflows/ci.yml": workflow})

    assert (
        "Python 3.15 optional dependency verification must remain release-blocking" in errors
    )


def test_python_support_checker_requires_stable_fail_closed_readiness_context() -> None:
    checker = load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        '          test "$OPTIONAL_MATRIX_RESULT" = "success"\n',
        '          # test "$OPTIONAL_MATRIX_RESULT" = "success"\n',
        1,
    )

    errors = checker.check_python_support({".github/workflows/ci.yml": workflow})

    assert any("optional matrix success assertion" in error for error in errors)


def test_python_support_checker_requires_native_windows_readiness_context() -> None:
    checker = load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        '          test "$NATIVE_WINDOWS_RESULT" = "success"\n',
        '          # test "$NATIVE_WINDOWS_RESULT" = "success"\n',
        1,
    )

    errors = checker.check_python_support({".github/workflows/ci.yml": workflow})

    assert any("native Windows success assertion" in error for error in errors)


def test_python_support_checker_binds_governance_and_release_to_readiness() -> None:
    checker = load_checker()
    governance = Path("scripts/check_repository_governance.py").read_text(
        encoding="utf-8"
    ).replace(
        '    "Python 3.15 readiness",\n',
        '    # "Python 3.15 readiness",\n',
        1,
    )
    release = Path(".github/workflows/release.yml").read_text(encoding="utf-8").replace(
        "          python scripts/check_python315_ci_evidence.py\n",
        "          # python scripts/check_python315_ci_evidence.py\n",
        1,
    )

    governance_errors = checker.check_python_support(
        {"scripts/check_repository_governance.py": governance}
    )
    release_errors = checker.check_python_support({".github/workflows/release.yml": release})

    assert "repository governance must require the Python 3.15 readiness context" in (
        governance_errors
    )
    assert any("exact release-source CI evidence command" in error for error in release_errors)


def test_python_support_checker_binds_governance_to_native_windows_readiness() -> None:
    checker = load_checker()
    governance = Path("scripts/check_repository_governance.py").read_text(
        encoding="utf-8"
    ).replace(
        '    "Native Windows readiness",\n',
        '    # "Native Windows readiness",\n',
        1,
    )

    errors = checker.check_python_support(
        {"scripts/check_repository_governance.py": governance}
    )

    assert "repository governance must require the Native Windows readiness context" in (
        errors
    )


def test_python_support_checker_requires_bounded_release_ci_evidence_polling() -> None:
    checker = load_checker()
    source = Path(".github/workflows/release.yml").read_text(encoding="utf-8")

    without_wait = source.replace("          --wait-seconds 5400\n", "", 1)
    without_poll = source.replace("          --poll-interval-seconds 15\n", "", 1)

    assert any(
        "bounded release-source CI evidence wait" in error
        for error in checker.check_python_support({".github/workflows/release.yml": without_wait})
    )
    assert any(
        "bounded release-source CI evidence polling" in error
        for error in checker.check_python_support({".github/workflows/release.yml": without_poll})
    )


def test_python_support_checker_requires_python315_real_qtwidgets_evidence() -> None:
    checker = load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    workflow = workflow.replace(
        "from PyQt6.QtWidgets import QApplication, QLabel",
        "from PyQt6.QtCore import QCoreApplication",
    ).replace(
        "python scripts/check_real_gui_render.py --out-dir artifacts/python315-gui",
        "python scripts/check_real_gui_render.py --preset native --out-dir artifacts/python315-gui",
    ).replace(
        "          QT_QPA_PLATFORM: ${{ matrix.qt_platform }}\n",
        "",
    ).replace(
        "          - os: macos-15-intel\n"
        "            # Hosted macOS is not guaranteed to expose a logged-in WindowServer.\n"
        "            # Keep the full application render deterministic and headless there.\n"
        '            qt_platform: "offscreen"',
        "          - os: macos-15-intel\n"
        '            qt_platform: "cocoa"',
    )

    errors = checker.check_python_support({".github/workflows/ci.yml": workflow})

    assert any("Python 3.15 QtWidgets application startup" in error for error in errors)
    assert any("Python 3.15 all-preset real application GUI render" in error for error in errors)
    assert any(
        "host-native Python 3.15 full GUI renderer platform" in error for error in errors
    )
    assert any(
        "hosted macOS offscreen Python 3.15 GUI renderer" in error for error in errors
    )
    assert (
        "Python 3.15 optional dependency verification must exercise every GUI preset"
        in errors
    )


def test_python_support_checker_requires_full_extras_runtime_and_distribution_evidence() -> None:
    checker = load_checker()
    source = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    workflow = source.replace(
        'python -m pip install -e ".[desktop,security,package,dev]"',
        'python -m pip install -e ".[desktop,security,dev]"',
        1,
    ).replace(
        "python scripts/write_python_runtime_evidence.py --expected-version 3.15",
        "python -c \"print('runtime evidence skipped')\"",
        1,
    ).replace(
        "python scripts/check_gui_interactions.py --require-pyqt6",
        "python -c \"print('interaction evidence skipped')\"",
        1,
    ).replace(
        "python scripts/check_python_distribution_install.py",
        "python -c \"print('distribution install skipped')\"",
        1,
    )

    errors = checker.check_python_support({".github/workflows/ci.yml": workflow})

    assert any("desktop/security/package/development dependency install" in error for error in errors)
    assert any("exact Python 3.15 runtime evidence" in error for error in errors)
    assert any("all-preset GUI interaction gate" in error for error in errors)
    assert any("clean distribution installation verifier" in error for error in errors)


def test_python_support_checker_requires_linux_and_windows_arm64_rows() -> None:
    checker = load_checker()
    source = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")

    for runner in ("ubuntu-24.04-arm", "windows-11-arm"):
        workflow = source.replace(
            f'          - os: {runner}\n            python-version: "3.15"\n',
            "",
            1,
        )

        errors = checker.check_python_support({".github/workflows/ci.yml": workflow})

        assert f"ci workflow missing {runner} Python 3.15 ARM64 host row" in errors


def test_python_support_checker_requires_installer_upper_bound() -> None:
    checker = load_checker()
    installer = Path("installers/install.sh").read_text(encoding="utf-8").replace(
        "(3, 10) <= sys.version_info < (3, 16)",
        "sys.version_info >= (3, 10)",
    )

    errors = checker.check_python_support({"installers/install.sh": installer})

    assert "installers/install.sh must reject runtimes outside Python 3.10-3.15" in errors


def test_python_support_checker_keeps_rc_and_final_claims_separate() -> None:
    checker = load_checker()
    support_doc = Path("docs/PYTHON_SUPPORT.md").read_text(encoding="utf-8").replace(
        "3.15 final-GA certification",
        "3.15 certification",
    )

    errors = checker.check_python_support({"docs/PYTHON_SUPPORT.md": support_doc})

    assert "docs/PYTHON_SUPPORT.md missing final-GA evidence distinction" in errors


def load_checker():
    path = Path("scripts/check_python_support.py")
    spec = importlib.util.spec_from_file_location("python_support_checker", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

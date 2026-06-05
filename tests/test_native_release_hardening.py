import importlib.util
from pathlib import Path


def test_native_release_hardening_checker_passes_current_tree() -> None:
    checker = _load_checker()

    assert checker.main() == 0


def test_native_hardening_checker_tracks_native_jobs() -> None:
    checker = _load_checker()

    assert checker.WORKFLOW_NATIVE_JOBS == ("windows-native", "macos-native", "linux-native")
    assert set(checker.NATIVE_SCRIPTS) == {"windows", "macos", "linux"}


def test_native_checksum_patterns_are_documented_in_scripts() -> None:
    checker = _load_checker()

    for platform, pattern in checker.CHECKSUM_PATTERNS.items():
        text = checker.NATIVE_SCRIPTS[platform].read_text(encoding="utf-8")
        assert pattern in text


def test_native_pyinstaller_entrypoints_use_launchers() -> None:
    checker = _load_checker()

    assert checker.check_pyinstaller_launchers() == []
    for platform in ("windows", "linux"):
        text = checker.NATIVE_SCRIPTS[platform].read_text(encoding="utf-8")
        assert "row_launcher.py" in text
        assert "__main__.py" not in text


def test_native_workflow_uploads_fail_if_assets_missing() -> None:
    checker = _load_checker()

    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    for job in checker.WORKFLOW_NATIVE_JOBS:
        block = checker.workflow_job_block(workflow, job)
        assert "if-no-files-found: error" in block
        assert "persist-credentials: false" in block


def test_release_macos_x64_uses_current_intel_runner() -> None:
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")

    assert "runner: macos-15-intel" in workflow
    assert "runner: macos-13" not in workflow


def test_macos_pkg_install_path_is_not_relocatable() -> None:
    script = Path("scripts/make_macos_native.sh").read_text(encoding="utf-8")

    assert "pkgbuild --analyze" in script
    assert "BundleIsRelocatable false" in script
    assert "--component-plist" in script


def test_macos_dmg_creation_retries_resource_busy_failures() -> None:
    script = Path("scripts/make_macos_native.sh").read_text(encoding="utf-8")

    assert "create_macos_dmg()" in script
    assert 'hdiutil detach "/Volumes/$APP_NAME" -force' in script
    assert "for attempt in 1 2 3" in script
    assert '$(basename "${dmg%.dmg}").tmp.dmg' in script


def test_windows_wix_debug_sidecars_are_removed() -> None:
    script = Path("scripts/make_windows_native.ps1").read_text(encoding="utf-8")

    assert ".wixpdb" in script
    assert "Remove-Item -LiteralPath $WixPdb" in script


def test_windows_native_package_builds_double_click_gui_launcher() -> None:
    script = Path("scripts/make_windows_native.ps1").read_text(encoding="utf-8")
    cli = Path("src/remote_ops_workspace/cli.py").read_text(encoding="utf-8")
    workflow = Path(".github/workflows/release.yml").read_text(encoding="utf-8")
    smoke = Path("scripts/smoke_windows_native.ps1").read_text(encoding="utf-8")

    assert "row_gui_launcher.py" in script
    assert "from remote_ops_workspace.gui import main" in script
    assert "--name row-gui" in script
    assert "--windowed" in script
    assert "Copy-Item $RowGuiExe" in script
    assert '$BuildGuiLauncher = $Arch -ne "x86"' in script
    assert "--exclude-module PyQt6" in script
    assert "--exclude-module remote_ops_workspace.gui" in script
    assert 'Path(sys.executable).with_name("row-gui.exe")' in cli
    assert 'getattr(sys, "frozen", False)' in cli
    assert '".[desktop,security,package]"' in workflow
    assert "Test-RowGuiLauncher" in smoke
    assert "row-gui.exe" in smoke
    assert "CommandTimeoutSeconds" in smoke
    assert "WaitForExit" in smoke
    assert "$Process.Refresh()" in smoke


def _load_checker():
    path = Path("scripts/check_native_release_hardening.py")
    spec = importlib.util.spec_from_file_location("check_native_release_hardening_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module

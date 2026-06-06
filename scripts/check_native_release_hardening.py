from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

NATIVE_SCRIPTS = {
    "windows": ROOT / "scripts" / "make_windows_native.ps1",
    "macos": ROOT / "scripts" / "make_macos_native.sh",
    "linux": ROOT / "scripts" / "make_linux_native.sh",
}

CHECKSUM_PATTERNS = {
    "windows": "remote-ops-workspace-v$Version-windows-$Arch-native-SHA256SUMS.txt",
    "macos": "remote-ops-workspace-v{version}-macos-{arch}-native-SHA256SUMS.txt",
    "linux": "remote-ops-workspace-v{version}-linux-{appimage_arch}-native-SHA256SUMS.txt",
}

WORKFLOW_NATIVE_JOBS = ("windows-native", "macos-native", "linux-native")


def main() -> int:
    errors: list[str] = []
    errors.extend(check_line_endings())
    errors.extend(check_native_checksum_sidecars())
    errors.extend(check_native_manifest_integrity())
    errors.extend(check_pyinstaller_launchers())
    errors.extend(check_windows_gui_launcher())
    errors.extend(check_windows_wix_debug_sidecars())
    errors.extend(check_macos_dmg_creation_retry())
    errors.extend(check_linux_appimagetool_download())
    errors.extend(check_native_workflow_boundaries())
    if errors:
        for error in errors:
            print(f"native release hardening: {error}", file=sys.stderr)
        return 1
    print("native release hardening passed")
    return 0


def check_line_endings() -> list[str]:
    errors: list[str] = []
    gitattributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    if "*.sh text eol=lf" not in gitattributes:
        errors.append(".gitattributes must force LF line endings for shell scripts")
    for path in sorted((ROOT / "scripts").glob("*.sh")) + sorted((ROOT / "installers").glob("*.sh")):
        if b"\r\n" in path.read_bytes():
            errors.append(f"{display(path)} must use LF line endings for POSIX shell compatibility")
    return errors


def check_native_checksum_sidecars() -> list[str]:
    errors: list[str] = []
    for platform, path in NATIVE_SCRIPTS.items():
        text = path.read_text(encoding="utf-8")
        if "SHA256SUMS.txt" not in text:
            errors.append(f"{display(path)} must write a native SHA256SUMS sidecar")
        if CHECKSUM_PATTERNS[platform] not in text:
            errors.append(f"{display(path)} missing expected checksum filename pattern")
        if "Get-FileHash -Algorithm SHA256" not in text and "sha256_file(path)" not in text:
            errors.append(f"{display(path)} must hash native artifacts with SHA-256")
    return errors


def check_native_manifest_integrity() -> list[str]:
    errors: list[str] = []
    for path in NATIVE_SCRIPTS.values():
        text = path.read_text(encoding="utf-8")
        if "size_bytes" not in text:
            errors.append(f"{display(path)} native manifest must include size_bytes")
        if "sha256" not in text.lower():
            errors.append(f"{display(path)} native manifest must include sha256")
        if "GITHUB_REF_NAME" not in text:
            errors.append(f"{display(path)} must reject tag/version mismatches")
    return errors


def check_pyinstaller_launchers() -> list[str]:
    errors: list[str] = []
    cli_launcher_requirements = {
        "linux": ("row_launcher.py", "from remote_ops_workspace.cli import main", "raise SystemExit(main())"),
        "windows": ("row_launcher.py", "from remote_ops_workspace.cli import main", "raise SystemExit(main())"),
    }
    for platform, requirements in cli_launcher_requirements.items():
        path = NATIVE_SCRIPTS[platform]
        text = path.read_text(encoding="utf-8")
        for requirement in requirements:
            if requirement not in text:
                errors.append(f"{display(path)} must build PyInstaller from a package-aware CLI launcher")
        if "src/remote_ops_workspace/__main__.py" in text or "src\\remote_ops_workspace\\__main__.py" in text:
            errors.append(f"{display(path)} must not pass package __main__.py directly to PyInstaller")

    macos = NATIVE_SCRIPTS["macos"].read_text(encoding="utf-8")
    if "remote_ops_workspace_gui_launcher.py" not in macos or 'main(["gui"])' not in macos:
        errors.append("scripts/make_macos_native.sh must build PyInstaller from the GUI launcher")
    if "BundleIsRelocatable false" not in macos:
        errors.append("scripts/make_macos_native.sh must make the app bundle non-relocatable in PKG builds")
    return errors


def check_windows_wix_debug_sidecars() -> list[str]:
    text = NATIVE_SCRIPTS["windows"].read_text(encoding="utf-8")
    errors: list[str] = []
    if ".wixpdb" not in text or "Remove-Item -LiteralPath $WixPdb" not in text:
        errors.append("scripts/make_windows_native.ps1 must remove WiX .wixpdb sidecars from release output")
    return errors


def check_windows_gui_launcher() -> list[str]:
    script = NATIVE_SCRIPTS["windows"].read_text(encoding="utf-8")
    cli = (ROOT / "src" / "remote_ops_workspace" / "cli.py").read_text(encoding="utf-8")
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    windows_job = workflow_job_block(workflow, "windows-native")
    smoke = (ROOT / "scripts" / "smoke_windows_native.ps1").read_text(encoding="utf-8")
    smoke_contract = (ROOT / "configs" / "native_installer_smoke.json").read_text(encoding="utf-8")
    errors: list[str] = []
    required_script_snippets = {
        "row_gui_launcher.py": "GUI PyInstaller launcher source",
        "from remote_ops_workspace.gui import main": "GUI launcher entry point",
        "--name row-gui": "row-gui executable name",
        "--windowed": "no-console GUI executable mode",
        "Copy-Item $RowGuiExe": "row-gui.exe copied into the native package stage",
        "$PortableStage": "separate portable zip staging directory",
        "Remote Ops Workspace GUI.exe": "top-level portable GUI launcher alias",
        "portable_entrypoints": "native manifest portable entrypoint map",
        "$PortableEntrypoints[\"desktop_gui\"]": "manifest desktop GUI entrypoint",
        "$BuildGuiLauncher = $Arch -ne \"x86\"": "x86 PyQt6 wheel guard",
        "--exclude-module PyQt6": "PyQt6 exclusion from the CLI row.exe launcher",
        "--exclude-module remote_ops_workspace.gui": "GUI module exclusion from the CLI row.exe launcher",
    }
    for snippet, label in required_script_snippets.items():
        if snippet not in script:
            errors.append(f"scripts/make_windows_native.ps1 missing {label}: {snippet}")
    required_cli_snippets = {
        "getattr(sys, \"frozen\", False)": "frozen executable detection",
        "Path(sys.executable).with_name(\"row-gui.exe\")": "sibling GUI launcher delegation",
        "subprocess.run([str(gui_launcher)]": "row-gui.exe subprocess launch",
    }
    for snippet, label in required_cli_snippets.items():
        if snippet not in cli:
            errors.append(f"src/remote_ops_workspace/cli.py missing Windows GUI delegation {label}: {snippet}")
    if '".[desktop,security,package]"' not in workflow or "matrix.arch" not in workflow:
        errors.append("release workflow must install the desktop extra for Windows GUI-capable native builds")
    if "Test-RowGuiLauncher" not in smoke or "row-gui.exe" not in smoke:
        errors.append("scripts/smoke_windows_native.ps1 must verify the installed Windows GUI launcher")
    if "Expand-Archive" not in smoke or "Test-PortableGuiLauncher" not in smoke:
        errors.append("scripts/smoke_windows_native.ps1 must verify the Windows native portable zip")
    if "Remote Ops Workspace GUI.exe" not in smoke:
        errors.append("scripts/smoke_windows_native.ps1 must verify the top-level portable GUI alias")
    if "Run Windows native installer smoke tests" not in windows_job or "timeout-minutes: 20" not in windows_job:
        errors.append("release workflow must bound Windows native installer smoke with timeout-minutes")
    if "row-gui.exe exists on x64/ARM64" not in smoke_contract:
        errors.append("configs/native_installer_smoke.json must document Windows GUI launcher verification")
    return errors


def check_macos_dmg_creation_retry() -> list[str]:
    text = NATIVE_SCRIPTS["macos"].read_text(encoding="utf-8")
    errors: list[str] = []
    required = {
        "create_macos_dmg()": "retryable DMG creation helper",
        "hdiutil detach \"/Volumes/$APP_NAME\" -force": "stale volume detach before retry",
        "for attempt in 1 2 3": "bounded hdiutil retry loop",
        "$(basename \"${dmg%.dmg}\").tmp.dmg": "temporary DMG output path",
    }
    for snippet, label in required.items():
        if snippet not in text:
            errors.append(f"scripts/make_macos_native.sh missing {label}: {snippet}")
    return errors


def check_linux_appimagetool_download() -> list[str]:
    text = NATIVE_SCRIPTS["linux"].read_text(encoding="utf-8")
    errors: list[str] = []
    if "APPIMAGETOOL_URL" not in text:
        errors.append("make_linux_native.sh must make the appimagetool URL explicit")
    if "APPIMAGETOOL_SHA256" not in text or "sha256sum -c -" not in text:
        errors.append("make_linux_native.sh must support checksum verification for downloaded appimagetool")
    if "AppImageKit/releases/download/continuous" in text:
        errors.append("make_linux_native.sh must not use the obsolete AppImageKit appimagetool URL")
    return errors


def check_native_workflow_boundaries() -> list[str]:
    workflow = (ROOT / ".github" / "workflows" / "release.yml").read_text(encoding="utf-8")
    errors: list[str] = []
    for job in WORKFLOW_NATIVE_JOBS:
        block = workflow_job_block(workflow, job)
        if not block:
            errors.append(f"release workflow missing native job: {job}")
            continue
        if "persist-credentials: false" not in block:
            errors.append(f"{job} must disable checkout credential persistence")
        if "if-no-files-found: error" not in block:
            errors.append(f"{job} artifact upload must fail when native assets are missing")
    if "permissions:\n  contents: read" not in workflow:
        errors.append("release workflow native jobs must inherit read-only contents permission")
    if "runner: macos-13" in workflow:
        errors.append("macOS x64 release builds must not use the deprecated macos-13 runner label")
    if "runner: macos-15-intel" not in workflow:
        errors.append("macOS x64 release builds must use the Intel macos-15-intel runner")
    return errors


def workflow_job_block(workflow: str, job: str) -> str:
    match = re.search(rf"(?ms)^  {re.escape(job)}:\n(.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)", workflow)
    return match.group(1) if match else ""


def display(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


if __name__ == "__main__":
    raise SystemExit(main())

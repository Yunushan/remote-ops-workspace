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
    return errors


def workflow_job_block(workflow: str, job: str) -> str:
    match = re.search(rf"(?ms)^  {re.escape(job)}:\n(.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)", workflow)
    return match.group(1) if match else ""


def display(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


if __name__ == "__main__":
    raise SystemExit(main())

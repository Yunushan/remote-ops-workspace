from __future__ import annotations

import re
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

INSTALLERS = (
    ROOT / "installers" / "install.ps1",
    ROOT / "installers" / "install.bat",
    ROOT / "installers" / "install.sh",
    ROOT / "installers" / "install-termux.sh",
)

PUBLIC_FIRST_RUN_FILES = (
    ROOT / "README.md",
    ROOT / "README.tr.md",
    ROOT / "configs" / "profiles.example.json",
    ROOT / "docs" / "ANDROID.md",
    ROOT / "docs" / "ARCHITECTURE.md",
    ROOT / "docs" / "PLATFORM_SUPPORT.md",
    ROOT / "docs" / "PROTOCOLS.md",
    ROOT / "docs" / "SECURITY_MODEL.md",
    ROOT / "docs" / "runbooks" / "QUICKSTART_LINUX.md",
    ROOT / "docs" / "runbooks" / "QUICKSTART_WINDOWS_SERVER.md",
)

STALE_DOC_IP_RE = re.compile(r"\b192\.0\.2\.\d+\b")


def main() -> int:
    errors = check_first_run_ux()
    if errors:
        for error in errors:
            print(f"first-run UX: {error}", file=sys.stderr)
        return 1
    print("first-run UX passed")
    return 0


def check_first_run_ux() -> list[str]:
    errors: list[str] = []
    errors.extend(check_installers())
    errors.extend(check_public_examples())
    errors.extend(check_first_run_commands_documented())
    return errors


def check_installers() -> list[str]:
    errors: list[str] = []
    for path in INSTALLERS:
        text = path.read_text(encoding="utf-8")
        relative = display(path)
        if "init --quiet" not in text:
            errors.append(f"{relative} must initialize quietly before first-run guide output")
        if "doctor" not in text:
            errors.append(f"{relative} must run row doctor after installation")
        if "welcome" not in text:
            errors.append(f"{relative} must print row welcome first-run guidance")
    return errors


def check_public_examples() -> list[str]:
    errors: list[str] = []
    for path in PUBLIC_FIRST_RUN_FILES:
        text = path.read_text(encoding="utf-8")
        for match in STALE_DOC_IP_RE.finditer(text):
            errors.append(f"{display(path)} contains confusing first-run example IP: {match.group(0)}")
    return errors


def check_first_run_commands_documented() -> list[str]:
    errors: list[str] = []
    for path in (ROOT / "README.md", ROOT / "README.tr.md"):
        text = path.read_text(encoding="utf-8")
        for snippet in ("row welcome", "row doctor", "row connect"):
            if snippet not in text:
                errors.append(f"{display(path)} missing first-run snippet: {snippet}")
    return errors


def display(path: Path) -> str:
    return path.relative_to(ROOT).as_posix()


if __name__ == "__main__":
    raise SystemExit(main())

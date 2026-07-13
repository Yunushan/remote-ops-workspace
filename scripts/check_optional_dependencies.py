from __future__ import annotations

import argparse
import importlib.util
import os
import subprocess
import sys
import tempfile
from collections.abc import Iterable
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
sys.path.insert(0, str(SRC))

EXPECTED_EXTRA_SNIPPETS = {
    "desktop": ('"PyQt6>=6.6"',),
    "security": ('"cryptography>=42"', '"truststore>=0.10"'),
    "package": ('"build>=1.2"', '"pyinstaller>=6.0"'),
    "dev": ('"build>=1.2"', '"pytest>=8"', '"ruff>=0.5"', '"mypy>=1.10"'),
}

OPTIONAL_MODULES = {
    "desktop": ("PyQt6",),
    "security": ("cryptography", "truststore"),
    "package": ("build", "PyInstaller"),
    "dev": ("pytest", "ruff", "mypy"),
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Check optional dependency declarations and smoke paths.")
    parser.add_argument(
        "--require-extra",
        action="append",
        choices=sorted(OPTIONAL_MODULES),
        help="Fail if the named optional extra's import modules are not available.",
    )
    args = parser.parse_args(argv)

    required = set(args.require_extra or [])
    errors: list[str] = []
    messages: list[str] = []
    errors.extend(check_declared_extras())
    dependency_errors, dependency_messages = check_optional_modules(required)
    errors.extend(dependency_errors)
    messages.extend(dependency_messages)

    with tempfile.TemporaryDirectory(prefix="row-optional-") as raw_tmp:
        tmp_path = Path(raw_tmp)
        desktop_errors, desktop_messages = check_desktop_gui(tmp_path)
        security_errors, security_messages = check_security_vault(tmp_path)
        errors.extend(desktop_errors)
        errors.extend(security_errors)
        messages.extend(desktop_messages)
        messages.extend(security_messages)

    for message in messages:
        print(f"optional dependency: {message}")
    if errors:
        for error in errors:
            print(f"optional dependency: {error}", file=sys.stderr)
        return 1
    print("optional dependency checks passed")
    return 0


def check_declared_extras() -> list[str]:
    text = (ROOT / "pyproject.toml").read_text(encoding="utf-8")
    errors: list[str] = []
    for extra, snippets in EXPECTED_EXTRA_SNIPPETS.items():
        if f"{extra} = [" not in text:
            errors.append(f"pyproject.toml missing optional extra: {extra}")
            continue
        for snippet in snippets:
            if snippet not in text:
                errors.append(f"pyproject.toml optional extra {extra} missing dependency {snippet}")
    return errors


def check_optional_modules(required_extras: Iterable[str]) -> tuple[list[str], list[str]]:
    required = set(required_extras)
    errors: list[str] = []
    messages: list[str] = []
    for extra, modules in OPTIONAL_MODULES.items():
        missing = [module for module in modules if not module_available(module)]
        if missing:
            messages.append(f"{extra} missing modules: {', '.join(missing)}")
            if extra in required:
                errors.append(f"{extra} extra is required but missing modules: {', '.join(missing)}")
        else:
            messages.append(f"{extra} modules importable: {', '.join(modules)}")
    return errors, messages


def check_desktop_gui(tmp_path: Path, *, render_timeout_seconds: int = 60) -> tuple[list[str], list[str]]:
    from remote_ops_workspace import gui

    if not module_available("PyQt6"):
        try:
            gui.create_main_window(["row-gui-optional-check"], show=False)
        except gui.GuiDependencyError:
            return [], ["desktop/PyQt6 unavailable; GUI factory fail-closed path verified"]
        return ["GUI factory must raise GuiDependencyError when PyQt6 is unavailable"], []

    env = os.environ.copy()
    env.setdefault("QT_QPA_PLATFORM", "offscreen")
    env["ROW_HOME"] = str(tmp_path / "row-home")
    command = [
        sys.executable,
        str(ROOT / "scripts" / "check_real_gui_render.py"),
        "--timeout-seconds",
        str(render_timeout_seconds),
        "--preset",
        "native",
    ]
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            env=env,
            text=True,
            capture_output=True,
            timeout=render_timeout_seconds + 15,
            check=False,
        )
    except subprocess.TimeoutExpired:
        return [f"desktop/PyQt6 live render smoke exceeded {render_timeout_seconds + 15} seconds"], []
    output = "\n".join(part for part in (result.stdout.strip(), result.stderr.strip()) if part)
    if result.returncode != 0:
        detail = output.splitlines()[-1] if output else f"exit code {result.returncode}"
        return [f"desktop/PyQt6 live render smoke failed: {detail}"], []
    return [], ["desktop/PyQt6 bounded live render smoke passed for native preset"]


def check_security_vault(tmp_path: Path) -> tuple[list[str], list[str]]:
    from remote_ops_workspace.vault import LocalVault, VaultBackendUnavailable

    vault = LocalVault(tmp_path / "vault.json")
    if not module_available("cryptography"):
        try:
            vault.init("passphrase")
        except VaultBackendUnavailable:
            return [], ["security/cryptography unavailable; vault fail-closed path verified"]
        return ["vault init must raise VaultBackendUnavailable when cryptography is unavailable"], []

    vault.init("passphrase")
    vault.set("prod/router-password", "top-secret", "passphrase")
    if vault.get("prod/router-password", "passphrase") != "top-secret":
        return ["cryptography-backed vault smoke did not round-trip secret"], []
    vault.delete("prod/router-password")
    return [], ["security/cryptography vault smoke passed"]


def module_available(module: str) -> bool:
    return importlib.util.find_spec(module) is not None


def restore_env(name: str, old_value: str | None) -> None:
    if old_value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = old_value


if __name__ == "__main__":
    raise SystemExit(main())

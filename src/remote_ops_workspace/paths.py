from __future__ import annotations

import os
import platform
from importlib.resources import files
from pathlib import Path

from .file_safety import ensure_private_dir

APP_NAME = "remote-ops-workspace"
APP_TITLE = "RemoteOpsWorkspace"


def data_dir() -> Path:
    """Return writable application data directory.

    Operators can set ROW_HOME for portable mode, operator-secured local media,
    or temporary test workspaces. It is not a safe multi-user sharing boundary
    for profiles, vaults, or other private state.
    """
    override = os.environ.get("ROW_HOME")
    if override:
        return Path(override).expanduser().resolve()

    system = platform.system().lower()
    home = Path.home()
    if system == "windows":
        base = os.environ.get("APPDATA") or str(home / "AppData" / "Roaming")
        return Path(base) / APP_TITLE
    if system == "darwin":
        return home / "Library" / "Application Support" / APP_TITLE
    base = os.environ.get("XDG_CONFIG_HOME") or str(home / ".config")
    return Path(base) / APP_NAME


def ensure_data_dir() -> Path:
    # Resolve an explicitly selected portable/home location once before the
    # private-file layer rejects later ancestor indirection. This preserves
    # intentional ROW_HOME symlinks without allowing a nested link to redirect
    # an individual private artifact.
    path = data_dir().resolve(strict=False)
    ensure_private_dir(path)
    return path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def runtime_config_path(name: str) -> Path:
    repository_path = repo_root() / "configs" / name
    if repository_path.is_file():
        return repository_path
    packaged_path = Path(str(files("remote_ops_workspace").joinpath("configs", name)))
    if packaged_path.is_file():
        return packaged_path
    raise FileNotFoundError(f"runtime configuration is missing: {name}")


def runtime_web_dir() -> Path:
    repository_path = repo_root() / "apps" / "web"
    if repository_path.is_dir():
        return repository_path
    packaged_path = Path(str(files("remote_ops_workspace").joinpath("web")))
    if packaged_path.is_dir():
        return packaged_path
    raise FileNotFoundError("packaged Web/PWA assets are missing")

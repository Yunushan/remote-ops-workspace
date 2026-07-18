from __future__ import annotations

import importlib.util
from pathlib import Path


def test_release_version_checker_passes_current_tree() -> None:
    checker = _load_checker()

    assert checker.check_release_version("v1.0.8") == []


def test_release_version_checker_rejects_observed_tag_project_mismatch(tmp_path: Path) -> None:
    checker = _load_checker()
    _write_versions(tmp_path, project="1.0.2", package="1.0.2")

    errors = checker.check_release_version("v1.0.4", root=tmp_path)

    assert "release tag v1.0.4 does not match project version 1.0.2" in errors


def test_release_version_checker_rejects_package_version_drift(tmp_path: Path) -> None:
    checker = _load_checker()
    _write_versions(tmp_path, project="1.0.4", package="1.0.3")

    errors = checker.check_release_version("v1.0.4", root=tmp_path)

    assert "package __version__ 1.0.3 does not match project version 1.0.4" in errors


def test_release_version_checker_rejects_noncanonical_tag(tmp_path: Path) -> None:
    checker = _load_checker()
    _write_versions(tmp_path, project="1.0.4", package="1.0.4")

    errors = checker.check_release_version("release-1.0.4", root=tmp_path)

    assert "release tag 'release-1.0.4' must be canonical vX.Y.Z" in errors


def test_release_version_checker_rejects_missing_project_declaration(tmp_path: Path) -> None:
    checker = _load_checker()
    package_dir = tmp_path / "src" / "remote_ops_workspace"
    package_dir.mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text("[build-system]\nrequires = []\n", encoding="utf-8")
    (package_dir / "__init__.py").write_text('__version__ = "1.0.4"\n', encoding="utf-8")

    errors = checker.check_release_version("v1.0.4", root=tmp_path)

    assert any("missing [project]" in error for error in errors)


def test_release_version_checker_python310_fallback_scopes_version_to_project(
    tmp_path: Path,
) -> None:
    checker = _load_checker()
    package_dir = tmp_path / "src" / "remote_ops_workspace"
    package_dir.mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text(
        '[tool.example]\nversion = "9.9.9"\n\n'
        '[project]\nname = "fixture"\nversion = "1.0.4"\n',
        encoding="utf-8",
    )
    (package_dir / "__init__.py").write_text('__version__ = "1.0.4"\n', encoding="utf-8")
    checker.tomllib = None

    errors = checker.check_release_version("v1.0.4", root=tmp_path)

    assert errors == []


def _write_versions(root: Path, *, project: str, package: str) -> None:
    package_dir = root / "src" / "remote_ops_workspace"
    package_dir.mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "fixture"\nversion = "{project}"\n', encoding="utf-8"
    )
    (package_dir / "__init__.py").write_text(
        f'__version__ = "{package}"\n', encoding="utf-8"
    )


def _load_checker():
    path = Path("scripts/check_release_version.py")
    spec = importlib.util.spec_from_file_location("check_release_version_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module

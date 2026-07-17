from __future__ import annotations

import importlib.util
import sys
from pathlib import Path


def test_container_base_images_cover_checked_in_dockerfile() -> None:
    checker = _load_checker()

    assert checker.check_container_base_images() == []


def test_container_base_images_reject_mutable_tags() -> None:
    checker = _load_checker()
    dockerfile = Path("docker/Dockerfile.web").read_text(encoding="utf-8")
    mutable = dockerfile.replace(checker.PYTHON_BASE_IMAGE, "python:3.12-slim")

    errors = checker.check_container_base_images(mutable)

    assert any("must use only the pinned base image" in error for error in errors)
    assert any("base image must be digest-pinned" in error for error in errors)


def test_container_base_images_require_pinned_build_toolchain() -> None:
    checker = _load_checker()
    dockerfile = Path("docker/Dockerfile.web").read_text(encoding="utf-8")
    unpinned = dockerfile.replace(checker.PINNED_BUILD_TOOLCHAIN, "pip install pip setuptools wheel")

    errors = checker.check_container_base_images(unpinned)

    assert any("install its build tooling from requirements-release.txt" in error for error in errors)


def test_container_base_images_require_no_build_isolation() -> None:
    checker = _load_checker()
    dockerfile = Path("docker/Dockerfile.web").read_text(encoding="utf-8")
    isolated = dockerfile.replace("--no-build-isolation ", "")

    errors = checker.check_container_base_images(isolated)

    assert any("install the application with --no-build-isolation" in error for error in errors)


def _load_checker():
    path = Path("scripts/check_container_base_images.py")
    spec = importlib.util.spec_from_file_location("container_base_images", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

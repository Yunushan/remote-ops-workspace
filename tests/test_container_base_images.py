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


def test_container_base_images_require_loopback_compose_hardening() -> None:
    checker = _load_checker()
    compose = Path("docker/compose.yaml").read_text(encoding="utf-8").replace(
        '"127.0.0.1:8765:8765"',
        '"8765:8765"',
    )

    errors = checker.check_compose_hardening(compose)

    assert any("loopback-only published port" in error for error in errors)


def test_container_base_images_require_bounded_local_log_retention() -> None:
    checker = _load_checker()
    compose = Path("docker/compose.yaml").read_text(encoding="utf-8").replace(
        '        max-file: "3"\n',
        "",
    )

    errors = checker.check_compose_hardening(compose)

    assert any("bounded local container log retention" in error for error in errors)


def test_container_base_images_rejects_log_retention_on_a_different_service() -> None:
    checker = _load_checker()
    compose = Path("docker/compose.yaml").read_text(encoding="utf-8")
    logging_block = (
        "    logging:\n"
        "      driver: local\n"
        "      options:\n"
        '        max-size: "10m"\n'
        '        max-file: "3"'
    )
    replacement = (
        "  reverse-proxy:\n"
        "    image: caddy:2\n"
        f"{logging_block}\n"
        "volumes:\n"
    )
    compose = compose.replace(logging_block, "").replace("volumes:\n", replacement)

    errors = checker.check_compose_hardening(compose)

    assert any("bounded local container log retention" in error for error in errors)


def test_container_base_images_require_runtime_config_build_context() -> None:
    checker = _load_checker()
    dockerignore = Path(".dockerignore").read_text(encoding="utf-8").replace(
        "!configs/platform_targets.json\n",
        "",
    )

    errors = checker.check_docker_build_context(dockerignore)

    assert errors == [
        ".dockerignore must allow required Web/PWA build input: !configs/platform_targets.json"
    ]


def _load_checker():
    path = Path("scripts/check_container_base_images.py")
    spec = importlib.util.spec_from_file_location("container_base_images", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

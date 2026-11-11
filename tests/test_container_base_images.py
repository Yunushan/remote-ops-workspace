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


def test_container_base_images_require_docker_dependabot_to_target_docker_directory() -> None:
    checker = _load_checker()
    dependabot = Path(".github/dependabot.yml").read_text(encoding="utf-8").replace(
        '    directory: "/docker"',
        '    directory: "/"',
    )

    assert checker.check_dependabot_docker_updates(dependabot) == [
        "dependabot.yml Docker updates must target /docker for Dockerfile.web"
    ]


def test_container_image_sbom_covers_the_checked_in_ci_workflow() -> None:
    checker = _load_checker()

    assert checker.check_container_image_sbom() == []


def test_container_image_sbom_requires_the_web_container_job() -> None:
    checker = _load_checker()

    assert checker.check_container_image_sbom("jobs:\n  other:\n    steps: []\n") == [
        "ci workflow missing web-container job for live Web/PWA container smoke"
    ]


def test_container_image_sbom_requires_image_inventory_generation() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        "importlib.metadata.distributions()",
        "importlib.metadata.packages()",
    )

    errors = checker.check_container_image_sbom(workflow)

    assert (
        "ci web-container step Collect container image package inventory missing: "
        "importlib.metadata.distributions()" in errors
    )


def test_container_image_sbom_requires_digest_check_before_signing() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    verify = workflow.index("      - name: Verify the SBOM names the downloaded image manifest digest\n")
    attest = workflow.index("      - name: Attest Web/PWA image build provenance\n", verify)
    following = workflow.index("      - name: Attest the Web/PWA image SBOM\n", attest)
    workflow = workflow[:verify] + workflow[attest:following] + workflow[verify:attest] + workflow[following:]

    errors = checker.check_container_image_sbom(workflow)

    assert "ci web-container-attestation job has an out-of-order step: Attest Web/PWA image build provenance" in errors


def test_container_image_sbom_restricts_attestation_permissions_to_main_push_job() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    attestation = "  web-container-attestation:\n"
    build, signing = workflow.split(attestation, 1)
    build = build.replace(
        "    name: Web/PWA container smoke\n",
        "    name: Web/PWA container smoke\n    permissions:\n      id-token: write\n",
    )
    signing = signing.replace("      attestations: write\n      contents: read\n      id-token: write\n", "", 1)
    signing = signing.replace(checker.MAIN_PUSH, "if: always()", 1)

    errors = checker.check_container_image_sbom(build + attestation + signing)

    assert "ci web-container job must build and test without attestation permissions" in errors
    assert "ci web-container-attestation job missing: attestations: write" in errors
    assert "ci web-container-attestation job missing: id-token: write" in errors
    assert f"ci web-container-attestation job missing: {checker.MAIN_PUSH}" in errors


def test_container_image_sbom_binds_the_producer_artifact_and_image_subject() -> None:
    checker = _load_checker()
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8")
    workflow = workflow.replace(
        f"artifact-ids: {checker.ATTESTATION_ARTIFACT}",
        "name: web-container-image",
    ).replace(
        f"subject-path: {checker.CONTAINER_MANIFEST_PATH}",
        f"subject-path: {checker.CONTAINER_SBOM_PATH}",
    ).replace(
        '--source-digest "$GITHUB_SHA"',
        '--source-digest "$OTHER_SHA"',
    )

    errors = checker.check_container_image_sbom(workflow)

    assert (
        "ci web-container-attestation step Download the Web/PWA image evidence missing: "
        f"artifact-ids: {checker.ATTESTATION_ARTIFACT}"
    ) in errors
    assert (
        "ci web-container-attestation step Attest the Web/PWA image SBOM missing: "
        f"subject-path: {checker.CONTAINER_MANIFEST_PATH}"
    ) in errors
    assert (
        "ci web-container-attestation step Verify the Web/PWA image attestations missing: "
        '--source-digest "$GITHUB_SHA"'
    ) in errors


def test_container_image_sbom_rejects_an_export_that_uses_a_mutable_tag() -> None:
    checker = _load_checker()
    export = 'docker image save --output "$RUNNER_TEMP/web-container-image.tar" "$TESTED_IMAGE_ID"'
    workflow = Path(".github/workflows/ci.yml").read_text(encoding="utf-8").replace(
        export,
        export.replace('"$TESTED_IMAGE_ID"', "remote-ops-workspace-web:latest"),
    )

    assert (
        "ci web-container step Export the smoke-tested Web/PWA image missing: "
        f"{export}"
    ) in checker.check_container_image_sbom(workflow)


def _load_checker():
    path = Path("scripts/check_container_base_images.py")
    spec = importlib.util.spec_from_file_location("container_base_images", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

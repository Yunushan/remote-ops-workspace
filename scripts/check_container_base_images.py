from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB_DOCKERFILE = ROOT / "docker" / "Dockerfile.web"
COMPOSE_PATH = ROOT / "docker" / "compose.yaml"
DOCKERIGNORE_PATH = ROOT / ".dockerignore"
DEPENDABOT_CONFIG_PATH = ROOT / ".github" / "dependabot.yml"
CI_WORKFLOW_PATH = ROOT / ".github" / "workflows" / "ci.yml"
PYTHON_BASE_IMAGE = (
    "python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de"
)
FROM_RE = re.compile(r"(?mi)^FROM\s+([^\s]+)")
DEPENDABOT_DOCKER_ENTRY_RE = re.compile(
    r"(?ms)^  - package-ecosystem:\s*docker\s*$.*?(?=^  - package-ecosystem:|\Z)"
)
PINNED_BUILD_TOOLCHAIN = (
    "pip install --no-cache-dir --no-compile --constraint requirements-release.txt pip setuptools wheel"
)
ISOLATED_APP_INSTALL = "pip install --no-cache-dir --no-compile --no-build-isolation ."
WEB_SERVICE_NAME = "remote-ops-web"
REQUIRED_WEB_SERVICE_LOG_OPTIONS = (
    "driver: local",
    'max-size: "10m"',
    'max-file: "3"',
)
CONTAINER_INVENTORY_PATH = "artifacts/container-sbom/container-image-packages.json"
CONTAINER_SBOM_PATH = "artifacts/container-sbom/container-image-sbom.cdx.json"
CONTAINER_SBOM_BUILDER = "scripts/build_container_sbom.py"
CONTAINER_SBOM_ATTEST_ACTION = "actions/attest@1e69f48acb82d1966a394da916b4c1698aa569d6"
CONTAINER_SBOM_UPLOAD_ACTION = "actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9"
CONTAINER_DEBIAN_INVENTORY_PATH = "artifacts/container-sbom/container-image-debian-packages.tsv"
CONTAINER_MANIFEST_PATH = "artifacts/container-sbom/web-container-image-manifest.json"
CONTAINER_DOWNLOAD_ACTION = "actions/download-artifact@9000827ccba6bdab643e8b6fd33ac0654aef8333"
MAIN_PUSH = "if: ${{ github.event_name == 'push' && github.ref == 'refs/heads/main' }}"
ATTESTATION_ARTIFACT = "${{ needs.web-container.outputs.image-artifact-id }}"
IMAGE_ID_OUTPUT = "${{ steps.smoke-tested-container.outputs.image-id }}"
CONTAINER_ID_OUTPUT = "${{ steps.smoke-tested-container.outputs.container-id }}"


def main() -> int:
    errors = check_container_base_images()
    errors.extend(check_container_image_sbom())
    if errors:
        for error in errors:
            print(f"container base images: {error}", file=sys.stderr)
        return 1
    print("container base images passed")
    return 0


def check_container_base_images(dockerfile: str | None = None) -> list[str]:
    text = dockerfile if dockerfile is not None else WEB_DOCKERFILE.read_text(encoding="utf-8")
    images = FROM_RE.findall(text)
    errors: list[str] = []
    if images != [PYTHON_BASE_IMAGE]:
        errors.append(f"Dockerfile.web must use only the pinned base image {PYTHON_BASE_IMAGE}")
    for image in images:
        if "@sha256:" not in image:
            errors.append(f"Dockerfile.web base image must be digest-pinned, got {image}")
    if "COPY . /app" not in text:
        errors.append("Dockerfile.web must copy only the allowlisted build context into /app")
    if PINNED_BUILD_TOOLCHAIN not in text:
        errors.append("Dockerfile.web must install its build tooling from requirements-release.txt")
    if ISOLATED_APP_INSTALL not in text:
        errors.append("Dockerfile.web must install the application with --no-build-isolation")
    errors.extend(check_docker_build_context())
    errors.extend(check_dependabot_docker_updates())
    errors.extend(check_compose_hardening())
    return errors


def check_docker_build_context(dockerignore_text: str | None = None) -> list[str]:
    text = dockerignore_text if dockerignore_text is not None else DOCKERIGNORE_PATH.read_text(encoding="utf-8")
    required_entries = (
        "!pyproject.toml",
        "!setup.py",
        "!requirements-release.txt",
        "!configs/",
        "!configs/feature_manifest.json",
        "!configs/platform_targets.json",
        "!configs/platform_verified_evidence.json",
        "!configs/platform_parity_promotion.json",
        "!configs/xp_native_evidence_contract.json",
        "!src/",
        "!apps/",
    )
    return [
        f".dockerignore must allow required Web/PWA build input: {entry}"
        for entry in required_entries
        if entry not in text
    ]


def check_dependabot_docker_updates(dependabot_text: str | None = None) -> list[str]:
    text = (
        dependabot_text
        if dependabot_text is not None
        else DEPENDABOT_CONFIG_PATH.read_text(encoding="utf-8")
    )
    entry = DEPENDABOT_DOCKER_ENTRY_RE.search(text)
    if entry is None:
        return ["dependabot.yml must define a Docker update entry for Dockerfile.web"]
    if 'directory: "/docker"' not in entry.group(0):
        return ["dependabot.yml Docker updates must target /docker for Dockerfile.web"]
    return []


def check_compose_hardening(compose_text: str | None = None) -> list[str]:
    text = compose_text if compose_text is not None else COMPOSE_PATH.read_text(encoding="utf-8")
    errors: list[str] = []
    required_snippets = {
        "remote-ops-web:": "remote-ops-web service",
        '"127.0.0.1:8765:8765"': "loopback-only published port",
        "read_only: true": "read-only container root filesystem",
        "cap_drop:\n      - ALL": "dropped Linux capabilities",
        "security_opt:\n      - no-new-privileges:true": "no-new-privileges runtime policy",
        "tmpfs:\n      - /tmp": "ephemeral writable temporary directory",
        "pids_limit: 128": "bounded PID limit",
        "mem_limit: 256m": "bounded memory limit",
        "remote-ops-data:/data": "named writable application data volume",
    }
    for snippet, label in required_snippets.items():
        if snippet not in text:
            errors.append(f"compose.yaml missing {label}: {snippet}")
    web_logging = compose_service_mapping_block(text, WEB_SERVICE_NAME, "logging")
    if not all(option in web_logging for option in REQUIRED_WEB_SERVICE_LOG_OPTIONS):
        errors.append("compose.yaml missing bounded local container log retention on remote-ops-web")
    for snippet, label in {
        "privileged: true": "privileged container mode",
        "network_mode: host": "host networking",
    }.items():
        if snippet in text:
            errors.append(f"compose.yaml must not enable {label}: {snippet}")
    return errors


def check_container_image_sbom(workflow: str | None = None) -> list[str]:
    text = workflow if workflow is not None else CI_WORKFLOW_PATH.read_text(encoding="utf-8")
    build = ci_job_block(text, "web-container")
    if not build:
        return ["ci workflow missing web-container job for live Web/PWA container smoke"]
    errors: list[str] = []
    if any(permission in build for permission in ("attestations: write", "id-token: write")):
        errors.append("ci web-container job must build and test without attestation permissions")
    if "image-artifact-id: ${{ steps.upload-web-container.outputs.artifact-id }}" not in build:
        errors.append("ci web-container job must expose the exact uploaded image artifact ID")
    if (
        "'container-image-sbom' || format('container-image-sbom-{0}', github.run_attempt)" not in build
        or f"path: {CONTAINER_SBOM_PATH}" not in build
    ):
        errors.append("ci web-container job must retain the standalone CycloneDX SBOM artifact")
    errors.extend(check_container_steps("web-container", build, {
        "Build and smoke-test Web/PWA container": (
            "id: smoke-tested-container",
            "docker inspect --format '{{.Image}}' \"$container_id\"",
            ">> \"$GITHUB_OUTPUT\"",
        ),
        "Collect container image package inventory": (
            f"TESTED_CONTAINER_ID: {CONTAINER_ID_OUTPUT}",
            "importlib.metadata.distributions()",
            "dpkg-query --show",
            CONTAINER_INVENTORY_PATH,
            CONTAINER_DEBIAN_INVENTORY_PATH,
        ),
        "Export the smoke-tested Web/PWA image": (
            f"TESTED_IMAGE_ID: {IMAGE_ID_OUTPUT}",
            'docker image save --output "$RUNNER_TEMP/web-container-image.tar" "$TESTED_IMAGE_ID"',
        ),
        "Generate container image SBOM": (
            f"TESTED_CONTAINER_ID: {CONTAINER_ID_OUTPUT}",
            f"TESTED_IMAGE_ID: {IMAGE_ID_OUTPUT}",
            CONTAINER_SBOM_BUILDER,
            f"--debian-packages {CONTAINER_DEBIAN_INVENTORY_PATH}",
            '--image-archive "$RUNNER_TEMP/web-container-image.tar"',
            f"--manifest-output {CONTAINER_MANIFEST_PATH}",
            f"--output {CONTAINER_SBOM_PATH}",
        ),
        "Upload the Web/PWA image evidence for attestation": (
            MAIN_PUSH,
            "id: upload-web-container",
            f"uses: {CONTAINER_SBOM_UPLOAD_ACTION}",
            "name: web-container-image-evidence-${{ github.run_attempt }}",
            f"path: |\n            {CONTAINER_MANIFEST_PATH}\n            {CONTAINER_SBOM_PATH}\n          if-no-files-found: error",
            "retention-days: 30",
        ),
    }))
    attestation = ci_job_block(text, "web-container-attestation")
    if not attestation:
        return [*errors, "ci workflow missing the Web/PWA image attestation job"]
    header = attestation.split("    steps:", 1)[0]
    for snippet in (MAIN_PUSH, "needs: web-container", "attestations: write", "id-token: write"):
        if snippet not in header:
            errors.append(f"ci web-container-attestation job missing: {snippet}")
    errors.extend(check_container_steps("web-container-attestation", attestation, {
        "Require the smoke job's exact image evidence artifact": (
            f"IMAGE_ARTIFACT_ID: {ATTESTATION_ARTIFACT}",
            '[[ "$IMAGE_ARTIFACT_ID" =~ ^[1-9][0-9]*$ ]]',
        ),
        "Download the Web/PWA image evidence": (
            f"uses: {CONTAINER_DOWNLOAD_ACTION}",
            f"artifact-ids: {ATTESTATION_ARTIFACT}",
        ),
        "Verify the SBOM names the downloaded image manifest digest": (
            "sha256sum web-container-image-manifest.json",
            '.metadata.component.hashes == [{"alg":"SHA-256","content":$digest}]',
            "container-image-sbom.cdx.json",
        ),
        "Attest Web/PWA image build provenance": (
            f"uses: {CONTAINER_SBOM_ATTEST_ACTION}",
            f"subject-path: |\n            {CONTAINER_MANIFEST_PATH}\n            {CONTAINER_SBOM_PATH}",
        ),
        "Attest the Web/PWA image SBOM": (
            f"uses: {CONTAINER_SBOM_ATTEST_ACTION}",
            f"subject-path: {CONTAINER_MANIFEST_PATH}",
            "predicate-type: https://cyclonedx.org/bom",
            f"predicate-path: {CONTAINER_SBOM_PATH}",
        ),
        "Verify the Web/PWA image attestations": (
            f"manifest={CONTAINER_MANIFEST_PATH}",
            '--signer-workflow "$GITHUB_REPOSITORY/.github/workflows/ci.yml"',
            "--source-ref refs/heads/main",
            '--source-digest "$GITHUB_SHA"',
            "--deny-self-hosted-runners",
            '--bundle "$PROVENANCE_BUNDLE"',
            "--predicate-type https://slsa.dev/provenance/v1",
            '--bundle "$SBOM_BUNDLE"',
            "--predicate-type https://cyclonedx.org/bom",
        ),
    }))
    return errors


def check_container_steps(
    job: str,
    block: str,
    required_steps: dict[str, tuple[str, ...]],
) -> list[str]:
    errors: list[str] = []
    previous = -1
    for name, snippets in required_steps.items():
        step = re.search(
            rf"(?ms)^      - name: {re.escape(name)}\n(.*?)(?=^      - |\Z)",
            block,
        )
        if step is None:
            errors.append(f"ci {job} job missing step: {name}")
            continue
        if step.start() <= previous:
            errors.append(f"ci {job} job has an out-of-order step: {name}")
        previous = step.start()
        for snippet in snippets:
            if snippet not in step.group(1):
                errors.append(f"ci {job} step {name} missing: {snippet}")
    return errors


def ci_job_block(workflow_text: str, job_name: str) -> str:
    match = re.search(
        rf"(?ms)^  {re.escape(job_name)}:\n(.*?)(?=^  [A-Za-z0-9_-]+:\n|\Z)",
        workflow_text,
    )
    return match.group(1) if match else ""


def compose_service_block(compose_text: str, service_name: str) -> str:
    lines = compose_text.splitlines()
    services_indent: int | None = None
    service_indent: int | None = None
    body: list[str] = []
    for line in lines:
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if services_indent is None:
            if stripped == "services:" and indent == 0:
                services_indent = indent
            continue
        if service_indent is None:
            if indent <= services_indent:
                return ""
            if indent == services_indent + 2 and stripped == f"{service_name}:":
                service_indent = indent
            continue
        if indent <= services_indent:
            break
        if indent == service_indent and stripped.endswith(":"):
            break
        body.append(line)
    return "\n".join(body)


def compose_service_mapping_block(compose_text: str, service_name: str, mapping_name: str) -> str:
    return compose_mapping_block(compose_service_block(compose_text, service_name), mapping_name)


def compose_mapping_block(text: str, mapping_name: str) -> str:
    mapping_indent: int | None = None
    body: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        indent = len(line) - len(line.lstrip())
        if mapping_indent is None:
            if stripped == f"{mapping_name}:":
                mapping_indent = indent
            continue
        if indent <= mapping_indent:
            break
        body.append(line)
    return "\n".join(body)


if __name__ == "__main__":
    raise SystemExit(main())

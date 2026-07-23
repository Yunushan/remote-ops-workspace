from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB_DOCKERFILE = ROOT / "docker" / "Dockerfile.web"
COMPOSE_PATH = ROOT / "docker" / "compose.yaml"
DOCKERIGNORE_PATH = ROOT / ".dockerignore"
PYTHON_BASE_IMAGE = (
    "python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de"
)
FROM_RE = re.compile(r"(?mi)^FROM\s+([^\s]+)")
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


def main() -> int:
    errors = check_container_base_images()
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

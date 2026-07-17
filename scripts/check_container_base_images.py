from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB_DOCKERFILE = ROOT / "docker" / "Dockerfile.web"
PYTHON_BASE_IMAGE = (
    "python:3.12-slim@sha256:57cd7c3a7a273101a6485ba99423ee568157882804b1124b4dd04266317710de"
)
FROM_RE = re.compile(r"(?mi)^FROM\s+([^\s]+)")
PINNED_BUILD_TOOLCHAIN = (
    "pip install --no-cache-dir --no-compile --constraint requirements-release.txt pip setuptools wheel"
)
ISOLATED_APP_INSTALL = "pip install --no-cache-dir --no-compile --no-build-isolation ."


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
    return errors


if __name__ == "__main__":
    raise SystemExit(main())

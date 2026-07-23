from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEPLOYMENT_GUIDE = ROOT / "docs" / "PRODUCTION_DEPLOYMENT.md"
COMPOSE_FILE = ROOT / "docker" / "compose.yaml"

REQUIRED_GUIDE_SNIPPETS = (
    "operator workstation application",
    "not a multi-tenant remote-desktop gateway",
    "Configure uptime checks against `/healthz`",
    "back up the named `/data` volume with encryption at rest",
    "bounded rotation",
    "restore drill",
    "Do not use it as an enterprise source of truth",
    "UNSIGNED PREVIEW",
)

REQUIRED_COMPOSE_SNIPPETS = (
    "restart: unless-stopped",
    "read_only: true",
    "- ALL",
    "no-new-privileges:true",
    "pids_limit: 128",
    "mem_limit: 256m",
    "driver: local",
    'max-size: "10m"',
    'max-file: "3"',
    "remote-ops-data:/data",
)


def check_production_deployment() -> list[str]:
    errors: list[str] = []
    if not DEPLOYMENT_GUIDE.exists():
        return ["missing production deployment guide"]
    if not COMPOSE_FILE.exists():
        return ["missing Web/PWA Compose deployment file"]

    guide = " ".join(DEPLOYMENT_GUIDE.read_text(encoding="utf-8").split())
    compose = COMPOSE_FILE.read_text(encoding="utf-8")
    for snippet in REQUIRED_GUIDE_SNIPPETS:
        if " ".join(snippet.split()) not in guide:
            errors.append(f"production deployment guide missing required boundary: {snippet}")
    for snippet in REQUIRED_COMPOSE_SNIPPETS:
        if snippet not in compose:
            errors.append(f"Compose deployment missing required hardening: {snippet}")
    if not has_bounded_web_service_logs(compose):
        errors.append("Compose deployment must configure bounded local logs on remote-ops-web")
    errors.extend(check_loopback_port_mappings(compose))
    return errors


def has_bounded_web_service_logs(compose: str) -> bool:
    return all(
        snippet in compose_service_block(compose, "remote-ops-web")
        for snippet in ("driver: local", 'max-size: "10m"', 'max-file: "3"')
    )


def check_loopback_port_mappings(compose: str) -> list[str]:
    mappings = compose_port_mappings(compose)
    if not mappings:
        return ["Compose deployment must expose the Web/PWA through a loopback port mapping"]

    errors: list[str] = []
    for mapping in mappings:
        if not mapping.startswith("127.0.0.1:"):
            errors.append(f"Compose deployment has a public network port mapping: {mapping}")
    return errors


def compose_port_mappings(compose: str) -> list[str]:
    mappings: list[str] = []
    ports_indent: int | None = None
    for line in compose.splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(line) - len(line.lstrip())
        if stripped == "ports:":
            ports_indent = indent
            continue
        if ports_indent is None:
            continue
        if indent <= ports_indent:
            ports_indent = None
            continue
        if stripped.startswith("-"):
            mapping = stripped[1:].strip().split("#", 1)[0].strip().strip("\"'")
            mappings.append(mapping)
    return mappings


def compose_service_block(compose: str, service_name: str) -> str:
    lines = compose.splitlines()
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


def main() -> int:
    errors = check_production_deployment()
    if errors:
        for error in errors:
            print(f"production deployment: {error}", file=sys.stderr)
        return 1
    print("production deployment readiness checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

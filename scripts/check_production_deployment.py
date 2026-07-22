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
    "restore drill",
    "Do not use it as an enterprise source of truth",
    "UNSIGNED PREVIEW",
)

REQUIRED_COMPOSE_SNIPPETS = (
    '"127.0.0.1:8765:8765"',
    "restart: unless-stopped",
    "read_only: true",
    "- ALL",
    "no-new-privileges:true",
    "pids_limit: 128",
    "mem_limit: 256m",
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
    return errors


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

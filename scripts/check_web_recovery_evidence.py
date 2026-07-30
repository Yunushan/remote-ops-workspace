from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from run_web_recovery_drill import validate_evidence


def check_evidence(
    path: Path,
    *,
    repository: str,
    source_sha: str,
    workflow_run_url: str,
    run_attempt: int,
    project_name: str = "row-web-recovery",
    compose_file: str = "docker/compose.yaml",
) -> list[str]:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [f"evidence must be readable UTF-8 JSON: {exc}"]
    if not isinstance(value, dict):
        return ["evidence root must be a JSON object"]
    return validate_evidence(
        value,
        expected_repository=repository,
        expected_source_sha=source_sha,
        expected_workflow_run_url=workflow_run_url,
        expected_run_attempt=run_attempt,
        expected_project_name=project_name,
        expected_compose_file=compose_file,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Validate retained Web/PWA recovery drill evidence.")
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--source-sha", required=True)
    parser.add_argument("--workflow-run-url", required=True)
    parser.add_argument("--run-attempt", required=True, type=int)
    parser.add_argument("--project-name", default="row-web-recovery")
    parser.add_argument("--compose-file", default="docker/compose.yaml")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    errors = check_evidence(
        args.evidence,
        repository=args.repository,
        source_sha=args.source_sha,
        workflow_run_url=args.workflow_run_url,
        run_attempt=args.run_attempt,
        project_name=args.project_name,
        compose_file=args.compose_file,
    )
    if errors:
        for error in errors:
            print(f"web recovery evidence: {error}", file=sys.stderr)
        return 1
    print("Web/PWA recovery drill evidence passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

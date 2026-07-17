from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "codeql.yml"
CODEQL_PIN = "7188fc363630916deb702c7fdcf4e481b751f97a"


def main() -> int:
    errors = check_code_security_workflow()
    if errors:
        for error in errors:
            print(f"code-security workflow: {error}", file=sys.stderr)
        return 1
    print("code-security workflow passed")
    return 0


def check_code_security_workflow(workflow: str | None = None) -> list[str]:
    if workflow is None:
        try:
            workflow = WORKFLOW.read_text(encoding="utf-8")
        except OSError as exc:
            return [f"cannot read {WORKFLOW}: {exc}"]

    required = {
        "name: code-security": "clear workflow name",
        "branches: [main]": "main-branch push or pull-request scope",
        "schedule:": "scheduled recurring scan",
        "security-events: write": "CodeQL security-event permission",
        "actions/checkout@df4cb1c069e1874edd31b4311f1884172cec0e10": "pinned checkout action",
        f"github/codeql-action/init@{CODEQL_PIN}": "pinned CodeQL initialization",
        "build-mode: none": "interpreted-language CodeQL build mode",
        f"github/codeql-action/analyze@{CODEQL_PIN}": "pinned CodeQL analysis",
        'language: ["python", "javascript-typescript"]': "Python and Web/PWA language matrix",
        'category: "/language:${{ matrix.language }}"': "language-specific CodeQL category",
        "timeout-minutes: 20": "bounded CodeQL job timeout",
    }
    return [
        f"missing {label}: {snippet}"
        for snippet, label in required.items()
        if snippet not in workflow
    ]


if __name__ == "__main__":
    raise SystemExit(main())

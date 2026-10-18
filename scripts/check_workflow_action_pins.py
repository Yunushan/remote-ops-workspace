from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"
ACTION_PINS = {
    "actions/checkout": "df4cb1c069e1874edd31b4311f1884172cec0e10",
    "actions/setup-python": "ece7cb06caefa5fff74198d8649806c4678c61a1",
    "actions/upload-artifact": "cf430e030ddbb5b0abf93d22962f4752f3646cd9",
    "actions/download-artifact": "9000827ccba6bdab643e8b6fd33ac0654aef8333",
    "actions/attest": "1e69f48acb82d1966a394da916b4c1698aa569d6",
    "softprops/action-gh-release": "c12583777ecdfd3be55c69cf75464299dc01057e",
    "github/codeql-action/init": "24c54180a607b1449ed407dd24f251e4e9147c8d",
    "github/codeql-action/analyze": "24c54180a607b1449ed407dd24f251e4e9147c8d",
}
USES_RE = re.compile(r"(?m)^\s*(?:-\s+)?uses:\s*([^\s@]+)@([^\s#]+)")


def main() -> int:
    errors = check_workflow_action_pins()
    if errors:
        for error in errors:
            print(f"workflow action pins: {error}", file=sys.stderr)
        return 1
    print("workflow action pins passed")
    return 0


def check_workflow_action_pins(workflows: dict[str, str] | None = None) -> list[str]:
    workflow_texts = workflows if workflows is not None else read_workflows()
    errors: list[str] = []
    for name, workflow in sorted(workflow_texts.items()):
        for action, revision in USES_RE.findall(workflow):
            expected = ACTION_PINS.get(action)
            if expected is None:
                errors.append(
                    f"{name} uses unapproved action {action}; add an explicitly reviewed immutable pin"
                )
            elif revision != expected:
                errors.append(
                    f"{name} must pin {action}@{expected}, got {revision}"
                )
    return errors


def read_workflows() -> dict[str, str]:
    return {
        path.name: path.read_text(encoding="utf-8")
        for path in sorted(WORKFLOW_DIR.glob("*.yml"))
    }


if __name__ == "__main__":
    raise SystemExit(main())

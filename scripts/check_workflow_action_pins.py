from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW_DIR = ROOT / ".github" / "workflows"
ACTION_PINS = {
    "actions/checkout": "df4cb1c069e1874edd31b4311f1884172cec0e10",
    "actions/setup-python": "ece7cb06caefa5fff74198d8649806c4678c61a1",
    "actions/upload-artifact": "043fb46d1a93c77aae656e7c1c64a875d1fc6a0a",
    "actions/download-artifact": "3e5f45b2cfb9172054b4087a40e8e0b5a5461e7c",
    "softprops/action-gh-release": "c12583777ecdfd3be55c69cf75464299dc01057e",
    "github/codeql-action/init": "7188fc363630916deb702c7fdcf4e481b751f97a",
    "github/codeql-action/analyze": "7188fc363630916deb702c7fdcf4e481b751f97a",
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

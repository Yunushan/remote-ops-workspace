from __future__ import annotations

import json
from pathlib import Path
from typing import Any

DEFAULT_DOCS = (
    "docs/PROTOCOLS.md",
    "docs/FILE_TRANSFER.md",
    "docs/GUI_DESIGN.md",
    "docs/PLUGIN_DEVELOPMENT.md",
)


def first_run_payload(
    *,
    data_dir: Path,
    profiles_file: Path,
    profile_names: list[str],
    row_command: str = "row",
) -> dict[str, Any]:
    profile_names = sorted(profile_names, key=profile_sort_key)
    steps = [
        {
            "title": "Check available clients",
            "command": f"{row_command} doctor",
            "detail": "Shows OpenSSH, RDP, VNC, serial and other external client availability.",
        },
        {
            "title": "Review profiles",
            "command": f"{row_command} profile list",
            "detail": "Lists the local profile store.",
        },
    ]
    if profile_names:
        steps.append(
            {
                "title": "Dry-run a profile",
                "command": f"{row_command} connect {profile_names[0]} --dry-run",
                "detail": "Prints the launch argv without starting an external client.",
            }
        )
    else:
        steps.append(
            {
                "title": "Add your first SSH profile",
                "command": (
                    f"{row_command} profile add --name prod-ssh --protocol ssh "
                    "--host ssh.example.invalid --username operator"
                ),
                "detail": "Replace the example host and username with your real target.",
            }
        )
    steps.extend(
        [
            {
                "title": "Start the desktop UI",
                "command": f"{row_command} gui",
                "detail": "Requires the desktop extra: pip install -e \".[desktop]\".",
            },
            {
                "title": "Start the Web/PWA shell",
                "command": f"{row_command} serve-web --host 127.0.0.1 --port 8765",
                "detail": "Binds to loopback by default.",
            },
        ]
    )
    return {
        "data_dir": str(data_dir),
        "profiles_file": str(profiles_file),
        "profile_count": len(profile_names),
        "profiles": profile_names,
        "next_steps": steps,
        "docs": list(DEFAULT_DOCS),
    }


def format_first_run(payload: dict[str, Any]) -> str:
    lines = [
        "First-run guide",
        f"  Data dir     : {payload['data_dir']}",
        f"  Profiles file: {payload['profiles_file']}",
        "",
        "Next steps:",
    ]
    for index, step in enumerate(payload["next_steps"], start=1):
        lines.append(f"  {index}. {step['title']}")
        lines.append(f"     {step['command']}")
        lines.append(f"     {step['detail']}")
    lines.append("")
    lines.append("Useful docs:")
    for doc in payload["docs"]:
        lines.append(f"  - {doc}")
    return "\n".join(lines)


def first_run_json(payload: dict[str, Any]) -> str:
    return json.dumps(payload, indent=2, sort_keys=True)


def profile_sort_key(name: str) -> tuple[int, str]:
    if name == "example-ssh":
        return (0, name)
    return (1, name)

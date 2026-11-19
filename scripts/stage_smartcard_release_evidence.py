"""Prepare and seal a physical smart-card capture on an approved release runner."""

from __future__ import annotations

import argparse
import re
import secrets
import sys
from pathlib import Path, PurePosixPath
from tempfile import TemporaryDirectory
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.capture_native_transport_release import require_native_runner  # noqa: E402
from scripts.check_mobaxterm_parity_evidence import capture_release_identity  # noqa: E402
from scripts.debian_release_fixture import actions_source  # noqa: E402
from scripts.qt_release_capture import TARGET, verify_wheel, write_json  # noqa: E402

ARTICLE = "ssh-browser-26-4-smartcard"
NESTED_ATTACHMENTS = {
    "management_interface": ("certificate_der", "present_tokens", "removed_tokens"),
    "ssh_browser": ("sshd_log", "sftp_listing"),
}


def stage_capture(ready: Path, destination: Path, identity: dict[str, Any], fixture: str) -> None:
    """Seal only the referenced captures and validate those exact bytes."""
    from scripts.check_moba_smartcard_evidence import (
        attachment,
        json_object,
        read_capture,
        validate_smartcard_connected_release_evidence,
    )

    if destination.exists() or destination.is_symlink():
        raise ValueError("smart-card review output must be a new directory")
    if not re.fullmatch(r"row-smartcard-[0-9a-f]{32}\.txt", fixture):
        raise ValueError("invalid smart-card capture challenge")
    expected = capture_release_identity(identity, "verified release wheel")
    _, envelope = read_capture(ready, "evidence.json", "smart-card capture")
    bundle = json_object(envelope, "smart-card capture")
    if capture_release_identity(bundle, "smart-card capture") != expected or bundle.get("release_target") != TARGET:
        raise ValueError("smart-card capture must match the exact release wheel and current workflow attempt")

    captured = {"evidence.json": envelope}

    def remember(reference: Any, label: str) -> bytes:
        content = attachment(ready, reference, label)
        name = reference["evidence_file"]
        path = PurePosixPath(name)
        if name != path.as_posix() or name in captured or any(part.startswith(".") for part in path.parts):
            raise ValueError(f"{label} must reference a unique visible capture path")
        captured[name] = content
        return content

    for action in ("management_interface", "ssh_session_selection", "mobagent", "ssh_browser"):
        content = remember(bundle.get(action), action)
        if action in NESTED_ATTACHMENTS:
            record = json_object(content, action)
            if action == "ssh_browser" and record.get("fixture_name") != fixture:
                raise ValueError("smart-card browser must show the challenge issued for this workflow attempt")
            for field in NESTED_ATTACHMENTS[action]:
                remember(record.get(field), field)

    with TemporaryDirectory(prefix=".smartcard-review-", dir=destination.parent) as scratch:
        pending = Path(scratch) / ARTICLE
        pending.mkdir(mode=0o700)
        for name, data in captured.items():
            target = pending / name
            target.parent.mkdir(parents=True, exist_ok=True)
            with target.open("xb") as file:
                file.write(data)
        result = validate_smartcard_connected_release_evidence(pending / "evidence.json", assets_dir=pending)
        if not result.passed:
            raise ValueError("smart-card capture failed validation: " + "; ".join(result.errors))
        pending.rename(destination)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--work", required=True, type=Path)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("prepare")
    collect = commands.add_parser("collect")
    collect.add_argument("--fixture", required=True)
    args = parser.parse_args()
    try:
        require_native_runner()
        tag, asset = verify_wheel(args.wheel)
        source = actions_source(tag)
        identity = {"release_target": TARGET, "release_asset": asset, "source": source}
        capture_release_identity(identity, "verified release wheel")
        if args.command == "prepare":
            fixture = f"row-smartcard-{secrets.token_hex(16)}.txt"
            (args.work / "inbox").mkdir(mode=0o700)
            write_json(args.work / "capture-request.json", {**identity, "fixture_name": fixture})
            print(fixture)
        else:
            stage_capture(args.work / "inbox/ready", args.work / "review" / ARTICLE, identity, args.fixture)
    except (OSError, RuntimeError, ValueError) as exc:
        print(f"smart-card release capture: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

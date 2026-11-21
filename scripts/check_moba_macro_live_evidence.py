from __future__ import annotations

import argparse
import ipaddress
import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
for location in (ROOT, SRC):
    if str(location) not in sys.path:
        sys.path.insert(0, str(location))

from remote_ops_workspace.moba_macros import (  # noqa: E402
    MobaMacroLiveEvidenceValidation,
    MobaMacroRecording,
    validate_macro_live_replay_evidence,
)
from scripts.check_mobaxterm_parity_evidence import capture_release_identity  # noqa: E402
from scripts.check_release_license_compliance import (  # noqa: E402
    bound_evidence_file,
    secure_regular_file,
)

REVIEW_SCHEMA = "row.moba-macro.live-review.v1"
SSH_REPLAY_SCHEMA = "row.moba-macro.ssh-replay.v1"
TRANSCRIPT_BYTE = re.compile(r"^ROW_INPUT_(\d+)_([0-9a-f]{2})_(\d+)\s*$", re.MULTILINE)
TRANSCRIPT_READY = re.compile(
    r"^ROW_MACRO_READY_(\d+) (\S+) (\d+) (\S+) (\d+)[ \t]*$", re.MULTILINE
)
CONNECT = re.compile(r"^Connection from (\S+) port (\d+) on (\S+) port (\d+)\b", re.MULTILINE)
AUTH = re.compile(r"^Accepted publickey for (\S+) from (\S+) port (\d+) ssh2:", re.MULTILINE)
PTY = re.compile(
    r"^Starting session: command on pts/\d+ for (\S+) from (\S+) port (\d+)", re.MULTILINE
)
TIMING_TOLERANCE_MS = 120


def captured_text(path: Path) -> str:
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("macro evidence attachment exceeds 1 MiB")
    return path.read_text(encoding="utf-8")


def captured_object(path: Path, label: str) -> dict[str, Any]:
    try:
        data = json.loads(captured_text(path))
    except ValueError as exc:
        raise ValueError(f"{label} must be structured JSON evidence") from exc
    if not isinstance(data, dict):
        raise ValueError(f"{label} must be a JSON object")
    return data


def bound_capture(root: Path, entry: Any, label: str, *, action: bool = False) -> Path:
    if not isinstance(entry, dict):
        raise ValueError(f"{label} requires a path and hash")
    name, digest = ("evidence_file", "evidence_sha256") if action else ("file", "sha256")
    return bound_evidence_file(root, entry.get(name), entry.get(digest), label)


def capture_recording(path: Path, macro: dict[str, Any]) -> MobaMacroRecording:
    data = captured_object(path, "macro recording")
    events = data.get("events")
    if (
        data.get("source") != "pyqt-terminal-pane"
        or not isinstance(events, list)
        or len(events) < 2
        or any(
            not isinstance(event, dict)
            or type(event.get("index")) is not int
            or event["index"] != index
            or type(event.get("enter")) is not bool
            or not isinstance(event.get("text"), str)
            or not (event["text"] or event["enter"])
            or type(event.get("delay_ms")) is not int
            or event["delay_ms"] < 0
            for index, event in enumerate(events, 1)
        )
        or max(event["delay_ms"] for event in events[1:]) < 2 * TIMING_TOLERANCE_MS
        or not any(event["text"] and not event["enter"] for event in events)
    ):
        raise ValueError(
            "macro recording requires ordered Qt keystrokes and a measurable inter-event delay"
        )
    recording = MobaMacroRecording.from_dict(data)
    normalized = recording.to_dict()
    if any(macro.get(key) != normalized[key] for key in ("name", "event_count", "input_sha256")):
        raise ValueError("macro recording bytes or event count differ from the bundle")
    return recording


def parse_observations(text: str, pid: int) -> list[tuple[int, str, int]]:
    rows: list[tuple[int, str, int]] = []
    for index, line in enumerate(text.splitlines(), 1):
        event = json.loads(line)
        if (
            not isinstance(event, dict)
            or type(event.get("index")) is not int
            or event["index"] != index
            or event.get("pid") != pid
            or not isinstance(event.get("hex"), str)
            or not re.fullmatch(r"[0-9a-f]{2}", event["hex"])
            or type(event.get("monotonic_ns")) is not int
            or event["monotonic_ns"] <= (rows[-1][2] if rows else 0)
        ):
            raise ValueError(
                "SSH receiver must contain every byte in order with a strictly increasing timestamp"
            )
        rows.append((index, event["hex"], event["monotonic_ns"]))
    return rows


def verify_ssh_sessions(text: str, user: str, connections: list[tuple[str, str, str, str]]) -> None:
    started = {(address, port) for login, address, port in PTY.findall(text) if login == user}
    accepted = {(address, port) for login, address, port in AUTH.findall(text) if login == user}
    observed = set(CONNECT.findall(text))
    origins = {(client, port) for client, port, _, _ in connections}
    if (
        len(origins) != 2
        or not origins <= started & accepted
        or not set(connections) <= observed
        or any(
            ipaddress.ip_address(client) == ipaddress.ip_address(server)
            or ipaddress.ip_address(client).is_loopback
            or ipaddress.ip_address(server).is_loopback
            for client, _, server, _ in connections
        )
    ):
        raise ValueError(
            "SSH server log must show two separate public-key-authenticated remote PTY connections"
        )


def verify_timed_bytes(
    rows: list[tuple[int, str, int]],
    payloads: list[bytes],
    recording: MobaMacroRecording,
) -> None:
    if bytes.fromhex("".join(value for _, value, _ in rows)) != b"".join(payloads):
        raise ValueError("SSH receiver bytes differ from the recorded keystrokes")
    previous = rows[0][2]
    offset = len(payloads[0])
    for step, payload in zip(recording.events[1:], payloads[1:], strict=True):
        timestamp = rows[offset][2]
        elapsed_ms = (timestamp - previous) / 1_000_000
        if abs(elapsed_ms - step.delay_ms) > TIMING_TOLERANCE_MS:
            raise ValueError("SSH receiver timing differs from recorded inter-event delays")
        previous = timestamp
        offset += len(payload)


def verify_review_windows(
    review: Any,
    recording: MobaMacroRecording,
    destination: str,
    *,
    size: int,
    total_observations: int,
) -> int:
    if not isinstance(review, dict) or set(review) != {
        "decline",
        "complete",
        "cancel",
        "reconnect",
    }:
        raise ValueError(
            "macro review requires decline, completed replay, cancellation and reconnect observations"
        )
    quiet_ms = sum(event.delay_ms for event in recording.events)
    for action, row in review.items():
        if (
            not isinstance(row, dict)
            or row.get("default_is_cancel") is not True
            or row.get("decision") != ("Cancel" if action == "decline" else "Yes")
            or row.get("text") != f"Replay {recording.name} in {destination}?"
            or type(row.get("before")) is not int
            or type(row.get("after")) is not int
            or (
                action != "complete"
                and (type(row.get("quiet_ms")) is not int or row["quiet_ms"] < quiet_ms)
            )
        ):
            raise ValueError(
                f"{action} must record the destination prompt, operator decision and observation window"
            )
    if (review["decline"]["before"], review["decline"]["after"]) != (size, size):
        raise ValueError("declining replay must leave the observed byte count unchanged")
    if (review["complete"]["before"], review["complete"]["after"]) != (size, 2 * size):
        raise ValueError("approved replay must send exactly one recording")
    prefix = review["cancel"]["after"] - 2 * size
    if (
        review["cancel"]["before"] != 2 * size
        or not 0 < prefix < size
        or total_observations != 2 * size + prefix
    ):
        raise ValueError("cancellation must stop a replay after a nonempty prefix")
    if (review["reconnect"]["before"], review["reconnect"]["after"]) != (total_observations, 0):
        raise ValueError("stale review must send zero bytes to the replacement connection")
    return prefix


def verify_replay_capture(
    root: Path,
    receipt: dict[str, Any],
    recording: MobaMacroRecording,
    review: Any,
) -> None:
    original_pid = receipt.get("receiver_pid")
    replacement_pid = receipt.get("replacement_receiver_pid")
    destination, user = receipt.get("destination"), receipt.get("ssh_user")
    enter = receipt.get("enter_byte")
    if (
        type(original_pid) is not int
        or original_pid < 1
        or type(replacement_pid) is not int
        or replacement_pid < 1
        or original_pid == replacement_pid
        or not isinstance(destination, str)
        or not destination.strip()
        or not isinstance(user, str)
        or not user.strip()
        or enter not in ("0a", "0d")
    ):
        raise ValueError(
            "macro replay must identify distinct remote receivers, the destination and the terminal Enter byte"
        )
    transcript = captured_text(
        bound_capture(root, receipt.get("terminal_transcript"), "original terminal transcript")
    )
    replacement = captured_text(
        bound_capture(
            root, receipt.get("replacement_transcript"), "replacement terminal transcript"
        )
    )
    original_ready = TRANSCRIPT_READY.findall(transcript)
    replacement_ready = TRANSCRIPT_READY.findall(replacement)
    if (
        [ready[0] for ready in original_ready] != [str(original_pid)]
        or [ready[0] for ready in replacement_ready] != [str(replacement_pid)]
        or "ROW_INPUT_" in replacement
        or not all(
            marker in transcript
            for marker in (
                "[macro recording started]",
                f"[macro recording saved: {recording.name}]",
                "[macro replay queued:",
                "[macro replay cancelled]",
            )
        )
    ):
        raise ValueError(
            "terminal transcripts must show recording, cancellation and a quiet replacement SSH receiver"
        )
    rows = parse_observations(
        captured_text(bound_capture(root, receipt.get("server_bytes"), "SSH receiver bytes")),
        original_pid,
    )
    client_rows = [
        (int(index), value, int(at)) for index, value, at in TRANSCRIPT_BYTE.findall(transcript)
    ]
    if rows != client_rows:
        raise ValueError("terminal transcript and separate SSH receiver bytes disagree")
    connections = [
        (client, client_port, server, server_port)
        for _, client, client_port, server, server_port in (*original_ready, *replacement_ready)
    ]
    verify_ssh_sessions(
        captured_text(bound_capture(root, receipt.get("ssh_log"), "SSH server log")),
        user,
        connections,
    )
    payloads = [
        event.text.encode() + (bytes.fromhex(enter) if event.enter else b"")
        for event in recording.events
    ]
    original = b"".join(payloads)
    size = len(original)
    prefix = verify_review_windows(
        review, recording, destination, size=size, total_observations=len(rows)
    )
    verify_timed_bytes(rows[:size], payloads, recording)
    verify_timed_bytes(rows[size : 2 * size], payloads, recording)
    if (
        bytes.fromhex("".join(value for _, value, _ in rows[2 * size : 2 * size + prefix]))
        != original[:prefix]
    ):
        raise ValueError(
            "cancelled SSH replay must contain exactly the observed prefix of the recording"
        )


def validate_macro_release_replay_evidence(
    evidence_path: Path,
    *,
    assets_dir: Path | None = None,
) -> MobaMacroLiveEvidenceValidation:
    root = (assets_dir if assets_dir is not None else evidence_path.parent).absolute()
    summary: dict[str, Any] = {"verified_macro_replays": 0}
    try:
        relative = evidence_path.absolute().relative_to(root).as_posix()
        source, error = secure_regular_file(root, relative, "macro release evidence")
        if source is None:
            raise ValueError(error)
        evidence = captured_object(source, "macro release evidence")
        summary.update(capture_release_identity(evidence, "macro release evidence"))
        recording = capture_recording(
            bound_capture(root, evidence["capture_session"], "GUI recording", action=True),
            evidence["macro"],
        )
        review = captured_object(
            bound_capture(root, evidence["replay_review"], "GUI review", action=True), "GUI review"
        )
        cases = review.get("profiles")
        if (
            review.get("schema") != REVIEW_SCHEMA
            or review.get("input_sha256") != recording.to_dict()["input_sha256"]
            or not isinstance(cases, dict)
        ):
            raise ValueError("GUI review must bind the recording and per-profile observations")
        sessions = evidence["replay_sessions"]
        names = [entry["profile"] for entry in sessions]
        if (
            not names
            or any(not isinstance(name, str) or not name for name in names)
            or len(set(names)) != len(names)
            or set(names) != set(cases)
        ):
            raise ValueError("macro review and replay must each cover the same unique profiles")
        observations: set[str] = set()
        for session in sessions:
            receipt = captured_object(
                bound_capture(root, session, "SSH replay", action=True), "SSH replay receipt"
            )
            if (
                receipt.get("schema") != SSH_REPLAY_SCHEMA
                or receipt.get("profile") != session["profile"]
                or receipt.get("input_sha256") != review["input_sha256"]
                or receipt.get("source") != evidence["source"]
                or receipt.get("release_asset") != evidence["release_asset"]
            ):
                raise ValueError(
                    "SSH replay receipt must bind the profile, recording, workflow and tested release asset"
                )
            verify_replay_capture(root, receipt, recording, cases[session["profile"]])
            observed_digest = receipt["server_bytes"]["sha256"]
            if observed_digest in observations:
                raise ValueError("each macro profile requires a separate SSH receiver capture")
            observations.add(observed_digest)
            summary["verified_macro_replays"] += 1
    except (AttributeError, KeyError, OSError, TypeError, ValueError) as exc:
        return MobaMacroLiveEvidenceValidation(
            str(evidence_path), str(root), False, [str(exc)], [], summary
        )
    result = validate_macro_live_replay_evidence(evidence_path, assets_dir=root)
    result.summary.update(summary)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Verify MobaXterm-style live macro capture/replay evidence."
    )
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--assets-dir", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args()

    result = validate_macro_release_replay_evidence(args.evidence, assets_dir=args.assets_dir)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    elif result.passed:
        print("moba macro live evidence passed")
    else:
        for error in result.errors:
            print(f"moba macro live evidence: {error}", file=sys.stderr)
    return 0 if result.passed else 1


if __name__ == "__main__":
    raise SystemExit(main())

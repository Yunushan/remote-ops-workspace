from __future__ import annotations

import argparse
import hashlib
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
from scripts.check_mobaxterm_parity_evidence import (  # noqa: E402
    capture_release_identity,
    requires_named_macro_evidence,
)
from scripts.check_release_license_compliance import (  # noqa: E402
    bound_evidence_file,
    canonical_json,
    secure_regular_file,
)

REVIEW_SCHEMA = "row.moba-macro.live-review.v1"
SSH_REPLAY_SCHEMA = "row.moba-macro.ssh-replay.v1"
WORKSPACE_CONTROLS_SCHEMA = "row.moba-macro.workspace-controls.v1"
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


def verify_ssh_sessions(
    text: str, users: list[str], connections: list[tuple[str, str, str, str]]
) -> None:
    started = set(PTY.findall(text))
    accepted = set(AUTH.findall(text))
    observed = set(CONNECT.findall(text))
    origins = {(client, port) for client, port, _, _ in connections}
    logins = {
        (user, client, port) for user, (client, port, _, _) in zip(users, connections, strict=True)
    }
    if (
        len(origins) != len(connections)
        or not logins <= started & accepted
        or not set(connections) <= observed
        or any(
            ipaddress.ip_address(client) == ipaddress.ip_address(server)
            or ipaddress.ip_address(client).is_loopback
            or ipaddress.ip_address(server).is_loopback
            for client, _, server, _ in connections
        )
    ):
        raise ValueError(
            "SSH server log must show distinct public-key-authenticated remote PTY connections"
        )


def recorded_payloads(recording: MobaMacroRecording, enter: str) -> list[bytes]:
    return [
        event.text.encode() + (bytes.fromhex(enter) if event.enter else b"")
        for event in recording.events
    ]


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
        [user, user],
        connections,
    )
    payloads = recorded_payloads(recording, enter)
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


def verify_persisted_recording(
    root: Path, controls: dict[str, Any], recording: MobaMacroRecording
) -> None:
    captured, reopened = controls.get("capture_app_pid"), controls.get("replay_app_pid")
    if (
        controls.get("schema") != WORKSPACE_CONTROLS_SCHEMA
        or controls.get("macro_name") != recording.name
        or controls.get("input_sha256") != recording.to_dict()["input_sha256"]
        or type(captured) is not int
        or type(reopened) is not int
        or min(captured, reopened) < 1
        or captured == reopened
    ):
        raise ValueError(
            "named macro controls must identify the recording and two separate GUI processes"
        )
    expected_route = {
        "preset": "mobaxterm",
        "menu": "Macros",
        "record": "Record new macro",
        "stop": "Stop recording",
        "stop_object": "mobaStopRecording",
        "prompt": "Please enter a name for this macro",
        "accepted_name": recording.name,
        "focused_output": "terminalOutput",
    }
    if controls.get("capture_route") != expected_route:
        raise ValueError(
            "named macro capture must show the Macros menu, focused terminal, Stop and accepted name"
        )

    before = bound_capture(root, controls.get("store_before_exit"), "macro store before exit")
    after = bound_capture(root, controls.get("store_after_restart"), "macro store after restart")
    store = captured_object(after, "reopened macro store")
    if (
        before == after
        or controls["store_before_exit"]["sha256"] != controls["store_after_restart"]["sha256"]
        or type(store.get("version")) is not int
        or store["version"] != 1
        or not isinstance(store.get("macros"), list)
    ):
        raise ValueError(
            "separate macro store snapshots must retain identical workspace bytes across restart"
        )
    saved = [
        row
        for row in store["macros"]
        if isinstance(row, dict) and row.get("name") == recording.name
    ]
    if canonical_json(saved) != canonical_json([recording.to_dict()]):
        raise ValueError("the reopened named macro must preserve every recorded event and delay")


def named_replay_observations(
    root: Path, receipt: dict[str, Any], controls: dict[str, Any], event_count: int
) -> list[tuple[int, str, int]]:
    selected, inactive = controls["selected"], controls["inactive"]
    if controls.get("ssh_log") != receipt["ssh_log"]:
        raise ValueError(
            "named replay must reference the same authenticated SSH log as the capture"
        )

    connections = []
    pids = [
        receipt["receiver_pid"],
        receipt["replacement_receiver_pid"],
        selected["receiver_pid"],
        inactive["receiver_pid"],
    ]
    if any(type(pid) is not int or pid < 1 for pid in pids) or len(set(pids)) != len(pids):
        raise ValueError("named replay requires fresh, distinct SSH receiver processes")
    transcripts = []
    for pid, attachment in zip(
        pids,
        (
            receipt["terminal_transcript"],
            receipt["replacement_transcript"],
            selected["terminal_transcript"],
            inactive["terminal_transcript"],
        ),
        strict=True,
    ):
        transcript = captured_text(bound_capture(root, attachment, "SSH terminal transcript"))
        ready = TRANSCRIPT_READY.findall(transcript)
        if len(ready) != 1 or ready[0][0] != str(pid):
            raise ValueError(
                "named replay transcript must identify its own SSH receiver and connection"
            )
        _, client, port, server, server_port = ready[0]
        connections.append((client, port, server, server_port))
        transcripts.append(transcript)
    verify_ssh_sessions(
        captured_text(bound_capture(root, controls["ssh_log"], "workspace SSH log")),
        [receipt["ssh_user"], receipt["ssh_user"], selected["ssh_user"], inactive["ssh_user"]],
        connections,
    )
    rows = parse_observations(
        captured_text(bound_capture(root, selected["server_bytes"], "selected receiver bytes")),
        pids[2],
    )
    selected_text, inactive_text = transcripts[2:]
    queued = [
        line for line in selected_text.splitlines() if line.startswith("[macro replay queued:")
    ]
    if (
        queued != [f"[macro replay queued: {event_count} event(s)]"]
        or "[macro replay queued:" in inactive_text
    ):
        raise ValueError("the selected terminal must queue exactly one named replay")
    client_rows = [
        (int(index), byte, int(ns)) for index, byte, ns in TRANSCRIPT_BYTE.findall(selected_text)
    ]
    if selected_text.count("ROW_INPUT_") != len(client_rows) or rows != client_rows:
        raise ValueError("selected named replay transcript and independent receiver bytes disagree")
    if "ROW_INPUT_" in inactive_text or captured_text(
        bound_capture(root, inactive["server_bytes"], "inactive receiver bytes")
    ):
        raise ValueError(
            "the separate inactive SSH receiver must remain quiet throughout both named replay reviews"
        )

    return rows


def verify_workspace_controls(
    root: Path, receipt: dict[str, Any], recording: MobaMacroRecording
) -> str:
    controls = captured_object(
        bound_capture(root, receipt.get("workspace_controls"), "named macro controls"),
        "named macro controls",
    )
    verify_persisted_recording(root, controls, recording)
    selected, inactive = controls["selected"], controls["inactive"]
    if (
        selected["profile"] != receipt["profile"]
        or selected["ssh_user"] != receipt["ssh_user"]
        or any(
            not isinstance(peer[k], str) or not peer[k].strip()
            for peer in (selected, inactive)
            for k in ("profile", "destination", "ssh_user")
        )
        or any(selected[k] == inactive[k] for k in ("profile", "destination", "ssh_user"))
    ):
        raise ValueError(
            "named replay must identify the selected profile and a distinct inactive SSH peer"
        )
    if controls.get("replay_route") != {
        "preset": "mobaxterm",
        "menu": "Macros",
        "saved_section": "Saved macros",
        "selected_entry": recording.name,
        "active_profile": selected["profile"],
        "active_destination": selected["destination"],
    }:
        raise ValueError(
            "the clicked tab and saved menu entry must match the selected replay destination"
        )
    rows = named_replay_observations(root, receipt, controls, len(recording.events))
    payloads = recorded_payloads(recording, receipt["enter_byte"])
    verify_timed_bytes(rows, payloads, recording)
    duration = sum(event.delay_ms for event in recording.events)
    for action, decision, end in (("decline", "Cancel", 0), ("complete", "Yes", len(rows))):
        row = controls["reviews"][action]
        if (
            row.get("decision") != decision
            or row.get("default_is_cancel") is not True
            or row.get("text") != f"Replay {recording.name} in {selected['destination']}?"
            or any(
                type(row.get(k)) is not int or row[k] != expected
                for k, expected in (
                    ("before", 0),
                    ("after", end),
                    ("inactive_before", 0),
                    ("inactive_after", 0),
                )
            )
            or action == "decline"
            and (type(row.get("quiet_ms")) is not int or row["quiet_ms"] < duration)
        ):
            raise ValueError(
                f"named replay {action} must bind the destination, default-Cancel review and both receiver windows"
            )
    # Compare the receiver observations across profiles even if the JSONL whitespace differs.
    return hashlib.sha256(canonical_json(rows)).hexdigest()


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
        named_observations: set[str] = set()
        named_required = requires_named_macro_evidence(summary["release_tag"])
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
            if named_required or "workspace_controls" in receipt:
                named_digest = verify_workspace_controls(root, receipt, recording)
                if named_digest in named_observations:
                    raise ValueError(
                        "each named macro replay profile requires a separate receiver capture"
                    )
                named_observations.add(named_digest)
            observed_digest = receipt["server_bytes"]["sha256"]
            if observed_digest in observations:
                raise ValueError("each macro profile requires a separate SSH receiver capture")
            observations.add(observed_digest)
            summary["verified_macro_replays"] += 1
        if len(named_observations) == len(sessions):
            summary["verified_named_macro_replays"] = len(named_observations)
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

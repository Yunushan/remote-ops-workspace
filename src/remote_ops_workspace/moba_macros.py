from __future__ import annotations

import hashlib
import json
import re
import shutil
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import command_safety as safe
from .file_safety import write_json_atomic
from .launcher import build_launch_plan
from .models import Profile
from .paths import ensure_data_dir

MOBA_MACRO_GUI_CAPTURE_SCHEMA = "row.moba-macro.gui-capture-plan.v1"
MOBA_MACRO_LIVE_EVIDENCE_BUNDLE_SCHEMA = "row.moba-macro.live-replay-evidence-bundle.v1"
MOBA_MACRO_LIVE_REPLAY_SCHEMA = "row.moba-macro.live-replay-plan.v1"
MOBA_MACRO_LIVE_EVIDENCE_SCHEMA = "row.moba-macro.live-replay-evidence.v1"
MOBA_MACRO_TERMINAL_CAPTURE_SCHEMA = "row.moba-macro.terminal-capture-state.v1"
MOBA_MACRO_TERMINAL_REPLAY_SCHEMA = "row.moba-macro.terminal-replay-injection.v1"


@dataclass(slots=True)
class MobaMacroEvent:
    index: int
    text: str
    enter: bool = True
    delay_ms: int = 0

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MobaMacroEvent:
        return cls(
            index=int(data["index"]),
            text=_typed_text(str(data.get("text", ""))),
            enter=bool(data.get("enter", True)),
            delay_ms=int(data.get("delay_ms", 0)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "text": self.text,
            "enter": self.enter,
            "delay_ms": self.delay_ms,
        }


@dataclass(slots=True)
class MobaMacroRecording:
    name: str
    events: list[MobaMacroEvent]
    description: str = ""
    tags: list[str] = field(default_factory=list)
    source: str = "typed-text"

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MobaMacroRecording:
        return cls(
            name=safe.option_value(str(data["name"]), "macro name"),
            events=[MobaMacroEvent.from_dict(item) for item in data.get("events", [])],
            description=safe.clean_text(str(data.get("description", "")), "macro description", allow_empty=True),
            tags=[safe.option_value(str(tag), "macro tag") for tag in data.get("tags", [])],
            source=safe.option_value(str(data.get("source", "typed-text")), "macro source"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "tags": self.tags,
            "source": self.source,
            "event_count": len(self.events),
            "input_text": self.input_text,
            "input_sha256": _sha256_text(self.input_text),
            "events": [event.to_dict() for event in self.events],
        }

    @property
    def input_text(self) -> str:
        parts: list[str] = []
        for event in self.events:
            parts.append(event.text)
            if event.enter:
                parts.append("\n")
        return "".join(parts)


@dataclass(slots=True)
class MobaMacroReplayPlan:
    macro_name: str
    profile_name: str
    command: list[str]
    input_text: str
    event_count: int
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "macro": self.macro_name,
            "profile": self.profile_name,
            "command": self.command,
            "input_text": self.input_text,
            "event_count": self.event_count,
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobaMacroReplayResult:
    macro_name: str
    profile_name: str
    command: list[str]
    dry_run: bool
    ok: bool
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "macro": self.macro_name,
            "profile": self.profile_name,
            "command": self.command,
            "dry_run": self.dry_run,
            "ok": self.ok,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
        }


@dataclass(slots=True)
class MobaMacroGuiCapturePlan:
    schema: str
    macro_name: str
    event_count: int
    input_sha256: str
    total_delay_ms: int
    capture_controls: list[str]
    conflict_policy: str
    cancel_supported: bool
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "macro": self.macro_name,
            "event_count": self.event_count,
            "input_sha256": self.input_sha256,
            "total_delay_ms": self.total_delay_ms,
            "capture_controls": self.capture_controls,
            "conflict_policy": self.conflict_policy,
            "cancel_supported": self.cancel_supported,
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobaMacroLiveReplayStep:
    index: int
    text: str
    enter: bool
    delay_ms: int
    scheduled_after_ms: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "index": self.index,
            "text": self.text,
            "enter": self.enter,
            "delay_ms": self.delay_ms,
            "scheduled_after_ms": self.scheduled_after_ms,
        }


@dataclass(slots=True)
class MobaMacroLiveReplayPlan:
    schema: str
    macro_name: str
    profile_name: str
    pane_id: str
    command: list[str]
    event_count: int
    input_sha256: str
    total_delay_ms: int
    steps: list[MobaMacroLiveReplayStep]
    confirmation_required: bool
    cancel_supported: bool
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "macro": self.macro_name,
            "profile": self.profile_name,
            "pane_id": self.pane_id,
            "command": self.command,
            "event_count": self.event_count,
            "input_sha256": self.input_sha256,
            "total_delay_ms": self.total_delay_ms,
            "steps": [step.to_dict() for step in self.steps],
            "confirmation_required": self.confirmation_required,
            "cancel_supported": self.cancel_supported,
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobaMacroLiveReplayReview:
    macro_name: str
    target_profiles: list[str]
    connected_profiles: list[str]
    allowed: bool
    disconnected_profiles: list[str]
    confirmation_required: bool
    prompt: str
    cancel_supported: bool
    force: bool
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "macro": self.macro_name,
            "target_profiles": self.target_profiles,
            "connected_profiles": self.connected_profiles,
            "allowed": self.allowed,
            "disconnected_profiles": self.disconnected_profiles,
            "confirmation_required": self.confirmation_required,
            "prompt": self.prompt,
            "cancel_supported": self.cancel_supported,
            "force": self.force,
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobaMacroLiveEvidenceValidation:
    evidence_path: str
    assets_dir: str
    passed: bool
    errors: list[str]
    warnings: list[str]
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_path": self.evidence_path,
            "assets_dir": self.assets_dir,
            "passed": self.passed,
            "errors": self.errors,
            "warnings": self.warnings,
            "summary": self.summary,
        }


@dataclass(slots=True)
class MobaMacroLiveEvidenceBundlePlan:
    schema: str
    out_dir: str
    evidence_path: str
    release_target: str
    macro_name: str
    event_count: int
    input_sha256: str
    target_profiles: tuple[str, ...]
    connected_profiles: tuple[str, ...]
    pane_ids: dict[str, str]
    capture_evidence_source: str
    review_evidence_source: str
    replay_evidence_sources: dict[str, str]
    capture_command: str
    review_command: str
    replay_commands: dict[str, str]
    gui_record_button: bool
    gui_stop_button: bool
    gui_cancel_button: bool
    per_event_timing_captured: bool
    confirmation_prompt: bool
    cancel_prompt_verified: bool
    conflict_checked: bool
    real_connected_session: bool
    live_terminal_pane: bool
    per_keystroke_timing_replay: bool
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "out_dir": self.out_dir,
            "evidence_path": self.evidence_path,
            "release_target": self.release_target,
            "macro": self.macro_name,
            "event_count": self.event_count,
            "input_sha256": self.input_sha256,
            "target_profiles": list(self.target_profiles),
            "connected_profiles": list(self.connected_profiles),
            "pane_ids": self.pane_ids,
            "capture_evidence_source": self.capture_evidence_source,
            "review_evidence_source": self.review_evidence_source,
            "replay_evidence_sources": self.replay_evidence_sources,
            "capture_command": self.capture_command,
            "review_command": self.review_command,
            "replay_commands": self.replay_commands,
            "gui_record_button": self.gui_record_button,
            "gui_stop_button": self.gui_stop_button,
            "gui_cancel_button": self.gui_cancel_button,
            "per_event_timing_captured": self.per_event_timing_captured,
            "confirmation_prompt": self.confirmation_prompt,
            "cancel_prompt_verified": self.cancel_prompt_verified,
            "conflict_checked": self.conflict_checked,
            "real_connected_session": self.real_connected_session,
            "live_terminal_pane": self.live_terminal_pane,
            "per_keystroke_timing_replay": self.per_keystroke_timing_replay,
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobaMacroLiveEvidenceBundleResult:
    plan: MobaMacroLiveEvidenceBundlePlan
    evidence_path: str
    files: tuple[str, ...]
    validation: MobaMacroLiveEvidenceValidation
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan": self.plan.to_dict(),
            "evidence_path": self.evidence_path,
            "files": list(self.files),
            "validation": self.validation.to_dict(),
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobaMacroTerminalCaptureState:
    schema: str
    macro_name: str
    pane_id: str
    active: bool
    cancelled: bool
    events: list[MobaMacroEvent]
    capture_controls: list[str]
    source: str
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        input_text = "".join(event.text + ("\n" if event.enter else "") for event in self.events)
        return {
            "schema": self.schema,
            "macro": self.macro_name,
            "pane_id": self.pane_id,
            "active": self.active,
            "cancelled": self.cancelled,
            "event_count": len(self.events),
            "input_text": input_text,
            "input_sha256": _sha256_text(input_text),
            "capture_controls": self.capture_controls,
            "source": self.source,
            "notes": self.notes,
            "events": [event.to_dict() for event in self.events],
        }


@dataclass(slots=True)
class MobaMacroTerminalReplayInjection:
    schema: str
    macro_name: str
    pane_id: str
    event_count: int
    input_sha256: str
    total_delay_ms: int
    steps: list[MobaMacroLiveReplayStep]
    injected_payloads: list[str]
    cancel_supported: bool
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "macro": self.macro_name,
            "pane_id": self.pane_id,
            "event_count": self.event_count,
            "input_sha256": self.input_sha256,
            "total_delay_ms": self.total_delay_ms,
            "steps": [step.to_dict() for step in self.steps],
            "injected_payloads": self.injected_payloads,
            "cancel_supported": self.cancel_supported,
            "notes": self.notes,
        }


class MobaMacroStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (ensure_data_dir() / "moba-macros.json")

    def load(self) -> list[MobaMacroRecording]:
        if not self.path.exists():
            return []
        data = json.loads(self.path.read_text(encoding="utf-8"))
        return [MobaMacroRecording.from_dict(item) for item in data.get("macros", [])]

    def save(self, recordings: Iterable[MobaMacroRecording]) -> None:
        data = {"version": 1, "macros": [recording.to_dict() for recording in recordings]}
        write_json_atomic(self.path, data, private=True)

    def add(self, recording: MobaMacroRecording, replace: bool = False) -> None:
        recordings = self.load()
        names = {item.name for item in recordings}
        if recording.name in names and not replace:
            raise ValueError(f"macro already exists: {recording.name}")
        recordings = [item for item in recordings if item.name != recording.name]
        recordings.append(recording)
        self.save(sorted(recordings, key=lambda item: item.name))

    def get(self, name: str) -> MobaMacroRecording:
        for recording in self.load():
            if recording.name == name:
                return recording
        raise KeyError(name)

    def remove(self, name: str) -> None:
        recordings = self.load()
        remaining = [item for item in recordings if item.name != name]
        if len(remaining) == len(recordings):
            raise KeyError(name)
        self.save(remaining)


def record_typed_macro(
    name: str,
    text: str,
    *,
    description: str = "",
    tags: Iterable[str] = (),
    delay_ms: int = 0,
) -> MobaMacroRecording:
    macro_name = safe.option_value(name, "macro name")
    if delay_ms < 0:
        raise ValueError("macro delay must not be negative")
    typed_text = _macro_body(text)
    lines = typed_text.splitlines()
    if typed_text.endswith(("\n", "\r")):
        # splitlines already represents the final typed Enter through the last line.
        pass
    if not lines:
        raise ValueError("macro recording requires at least one typed line")
    events = [
        MobaMacroEvent(index=index, text=_typed_text(line), enter=True, delay_ms=delay_ms)
        for index, line in enumerate(lines, start=1)
    ]
    return MobaMacroRecording(
        name=macro_name,
        events=events,
        description=safe.clean_text(description, "macro description", allow_empty=True),
        tags=[safe.option_value(tag, "macro tag") for tag in tags],
    )


def build_macro_replay_plans(
    recording: MobaMacroRecording,
    profiles: Iterable[Profile],
) -> list[MobaMacroReplayPlan]:
    if not recording.events:
        raise ValueError("macro recording has no events")
    input_text = recording.input_text
    plans: list[MobaMacroReplayPlan] = []
    for profile in profiles:
        if profile.protocol.lower() != "ssh":
            raise ValueError(f"macro replay currently supports ssh profiles only: {profile.name}")
        launch = build_launch_plan(profile)
        plans.append(
            MobaMacroReplayPlan(
                macro_name=recording.name,
                profile_name=profile.name,
                command=launch.command,
                input_text=input_text,
                event_count=len(recording.events),
                notes=[
                    *launch.notes,
                    "MobaXterm-style typed macro replay sends recorded terminal input over stdin.",
                    "Delay metadata is preserved for GUI replay; CLI replay streams stdin as one batch.",
                ],
            )
        )
    if not plans:
        raise ValueError("macro replay requires at least one profile")
    return plans


def build_macro_gui_capture_plan(recording: MobaMacroRecording) -> MobaMacroGuiCapturePlan:
    _require_recording_events(recording)
    notes = [
        "MobaXterm-style GUI macro capture contract for terminal typed input.",
        "Record, stop and cancel controls must be visible in the connected terminal surface.",
        "Per-event delay metadata is preserved for live GUI replay.",
    ]
    return MobaMacroGuiCapturePlan(
        schema=MOBA_MACRO_GUI_CAPTURE_SCHEMA,
        macro_name=recording.name,
        event_count=len(recording.events),
        input_sha256=_sha256_text(recording.input_text),
        total_delay_ms=_total_delay_ms(recording),
        capture_controls=["record", "stop", "cancel"],
        conflict_policy="replace-requires-confirmation",
        cancel_supported=True,
        notes=notes,
    )


def review_macro_live_replay(
    recording: MobaMacroRecording,
    profiles: Iterable[Profile],
    *,
    connected_profiles: Iterable[str] = (),
    force: bool = False,
) -> MobaMacroLiveReplayReview:
    _require_recording_events(recording)
    targets = [safe.option_value(profile.name, "macro target profile") for profile in profiles]
    if not targets:
        raise ValueError("macro live replay requires at least one target profile")
    connected = sorted({safe.option_value(name, "connected profile") for name in connected_profiles})
    missing = sorted(name for name in targets if name not in set(connected))
    allowed = not missing or force
    if missing:
        prompt = (
            "Some target terminal panes are not marked as connected; confirm the target list "
            "or pass --force only when replaying into newly opened panes is intended."
        )
    else:
        prompt = "Confirm live macro replay; Cancel remains available until the final recorded event is sent."
    notes = [
        "MobaXterm-style live macro replay review keeps GUI replay explicit before keystrokes are injected.",
        "Cancel support is required for release evidence.",
    ]
    if missing:
        notes.append("Disconnected target profile conflict detected.")
    return MobaMacroLiveReplayReview(
        macro_name=recording.name,
        target_profiles=targets,
        connected_profiles=connected,
        allowed=allowed,
        disconnected_profiles=missing,
        confirmation_required=True,
        prompt=prompt,
        cancel_supported=True,
        force=force,
        notes=notes,
    )


def build_macro_live_replay_plans(
    recording: MobaMacroRecording,
    profiles: Iterable[Profile],
    *,
    pane_ids: dict[str, str] | None = None,
) -> list[MobaMacroLiveReplayPlan]:
    _require_recording_events(recording)
    plans: list[MobaMacroLiveReplayPlan] = []
    for profile in profiles:
        if profile.protocol.lower() != "ssh":
            raise ValueError(f"macro live replay currently supports ssh profiles only: {profile.name}")
        launch = build_launch_plan(profile)
        pane_id = (pane_ids or {}).get(profile.name) or f"{profile.name}:terminal"
        plans.append(
            MobaMacroLiveReplayPlan(
                schema=MOBA_MACRO_LIVE_REPLAY_SCHEMA,
                macro_name=recording.name,
                profile_name=profile.name,
                pane_id=safe.option_value(pane_id, "macro live pane id"),
                command=launch.command,
                event_count=len(recording.events),
                input_sha256=_sha256_text(recording.input_text),
                total_delay_ms=_total_delay_ms(recording),
                steps=_live_replay_steps(recording),
                confirmation_required=True,
                cancel_supported=True,
                notes=[
                    *launch.notes,
                    "MobaXterm-style live macro replay injects recorded events into a connected terminal pane.",
                    "Unlike CLI replay, live replay preserves per-event delay metadata and exposes Cancel.",
                ],
            )
        )
    if not plans:
        raise ValueError("macro live replay requires at least one profile")
    return plans


def start_terminal_macro_capture(
    macro_name: str,
    *,
    pane_id: str,
) -> MobaMacroTerminalCaptureState:
    return MobaMacroTerminalCaptureState(
        schema=MOBA_MACRO_TERMINAL_CAPTURE_SCHEMA,
        macro_name=safe.option_value(macro_name, "macro name"),
        pane_id=safe.option_value(pane_id, "terminal pane id"),
        active=True,
        cancelled=False,
        events=[],
        capture_controls=["record", "stop", "cancel"],
        source="pyqt-terminal-pane",
        notes=[
            "MobaXterm-style live terminal macro capture is attached to operator-submitted terminal input.",
            "Stop converts captured input into a typed macro recording; Cancel discards pending events.",
        ],
    )


def capture_terminal_macro_input(
    state: MobaMacroTerminalCaptureState,
    text: str,
    *,
    enter: bool = True,
    delay_ms: int = 0,
) -> MobaMacroTerminalCaptureState:
    if not state.active:
        raise ValueError("terminal macro capture is not active")
    if state.cancelled:
        raise ValueError("terminal macro capture has been cancelled")
    if delay_ms < 0:
        raise ValueError("terminal macro event delay must not be negative")
    state.events.append(
        MobaMacroEvent(
            index=len(state.events) + 1,
            text=_typed_text(text),
            enter=enter,
            delay_ms=delay_ms,
        )
    )
    return state


def finish_terminal_macro_capture(
    state: MobaMacroTerminalCaptureState,
    *,
    description: str = "",
    tags: Iterable[str] = (),
) -> MobaMacroRecording:
    if state.cancelled:
        raise ValueError("terminal macro capture was cancelled")
    if not state.events:
        raise ValueError("terminal macro capture requires at least one event")
    state.active = False
    return MobaMacroRecording(
        name=state.macro_name,
        events=list(state.events),
        description=safe.clean_text(description, "macro description", allow_empty=True),
        tags=[safe.option_value(tag, "macro tag") for tag in tags],
        source="pyqt-terminal-pane",
    )


def cancel_terminal_macro_capture(state: MobaMacroTerminalCaptureState) -> MobaMacroTerminalCaptureState:
    state.active = False
    state.cancelled = True
    state.events.clear()
    return state


def build_terminal_macro_replay_injection(
    recording: MobaMacroRecording,
    *,
    pane_id: str,
) -> MobaMacroTerminalReplayInjection:
    _require_recording_events(recording)
    steps = _live_replay_steps(recording)
    payloads = [step.text + ("\n" if step.enter else "") for step in steps]
    return MobaMacroTerminalReplayInjection(
        schema=MOBA_MACRO_TERMINAL_REPLAY_SCHEMA,
        macro_name=recording.name,
        pane_id=safe.option_value(pane_id, "terminal pane id"),
        event_count=len(recording.events),
        input_sha256=_sha256_text(recording.input_text),
        total_delay_ms=_total_delay_ms(recording),
        steps=steps,
        injected_payloads=payloads,
        cancel_supported=True,
        notes=[
            "MobaXterm-style live macro replay injects recorded terminal input into the connected pane.",
            "Each payload is scheduled using the recorded per-event delay metadata.",
        ],
    )


def build_macro_live_evidence_bundle_plan(
    recording: MobaMacroRecording,
    profiles: Iterable[Profile],
    *,
    out_dir: Path,
    capture_evidence: Path,
    review_evidence: Path,
    replay_evidence: dict[str, Path],
    release_target: str = "local-bundle",
    connected_profiles: Iterable[str] = (),
    pane_ids: dict[str, str] | None = None,
    capture_command: str = "",
    review_command: str = "",
    replay_commands: dict[str, str] | None = None,
    gui_record_button: bool = False,
    gui_stop_button: bool = False,
    gui_cancel_button: bool = False,
    per_event_timing_captured: bool = False,
    confirmation_prompt: bool = False,
    cancel_prompt_verified: bool = False,
    conflict_checked: bool = False,
    real_connected_session: bool = False,
    live_terminal_pane: bool = False,
    per_keystroke_timing_replay: bool = False,
) -> MobaMacroLiveEvidenceBundlePlan:
    _require_recording_events(recording)
    profile_list = tuple(profiles)
    if not profile_list:
        raise ValueError("macro live evidence bundle requires at least one target profile")
    capture_plan = build_macro_gui_capture_plan(recording)
    connected = tuple(sorted({safe.option_value(name, "connected profile") for name in connected_profiles}))
    clean_pane_ids = {
        safe.option_value(profile, "pane profile"): safe.option_value(pane_id, "terminal pane id")
        for profile, pane_id in (pane_ids or {}).items()
    }
    review = review_macro_live_replay(recording, profile_list, connected_profiles=connected)
    live_plans = build_macro_live_replay_plans(recording, profile_list, pane_ids=clean_pane_ids)
    target_names = tuple(plan.profile_name for plan in live_plans)
    replay_sources = {
        safe.option_value(profile, "replay evidence profile"): str(Path(path).expanduser())
        for profile, path in replay_evidence.items()
    }
    missing = [profile for profile in target_names if profile not in replay_sources]
    unknown = sorted(set(replay_sources).difference(target_names))
    if missing:
        raise ValueError(f"missing replay evidence for profile(s): {', '.join(missing)}")
    if unknown:
        raise ValueError(f"replay evidence was supplied for unknown profile(s): {', '.join(unknown)}")
    root = Path(out_dir).expanduser()
    default_replay_commands = {
        plan.profile_name: f"live pane replay {plan.profile_name} {plan.pane_id}" for plan in live_plans
    }
    supplied_replay_commands = {
        safe.option_value(profile, "replay command profile"): safe.clean_text(command, "replay command")
        for profile, command in (replay_commands or {}).items()
    }
    unknown_commands = sorted(set(supplied_replay_commands).difference(target_names))
    if unknown_commands:
        raise ValueError(f"replay command was supplied for unknown profile(s): {', '.join(unknown_commands)}")
    final_replay_commands = {
        profile: supplied_replay_commands.get(profile, default_replay_commands[profile]) for profile in target_names
    }
    evidence_path = root / "moba-macro-live.json"
    notes = [
        "Bundle plan writes MobaXterm-style live macro replay release evidence from supplied proof files.",
        "Production parity requires the supplied evidence files to come from real connected terminal pane capture and replay sessions.",
    ]
    if not review.allowed:
        notes.append("Replay review is not allowed until every target profile is marked connected or reviewed with force outside this bundle.")
    if not all(
        (
            gui_record_button,
            gui_stop_button,
            gui_cancel_button,
            per_event_timing_captured,
            confirmation_prompt,
            cancel_prompt_verified,
            conflict_checked,
            real_connected_session,
            live_terminal_pane,
            per_keystroke_timing_replay,
        )
    ):
        notes.append("Evidence flags are incomplete; the verifier will fail until real GUI capture/replay evidence is asserted.")
    return MobaMacroLiveEvidenceBundlePlan(
        schema=MOBA_MACRO_LIVE_EVIDENCE_BUNDLE_SCHEMA,
        out_dir=str(root),
        evidence_path=str(evidence_path),
        release_target=safe.clean_text(release_target, "release target"),
        macro_name=recording.name,
        event_count=capture_plan.event_count,
        input_sha256=capture_plan.input_sha256,
        target_profiles=target_names,
        connected_profiles=connected,
        pane_ids=clean_pane_ids,
        capture_evidence_source=str(Path(capture_evidence).expanduser()),
        review_evidence_source=str(Path(review_evidence).expanduser()),
        replay_evidence_sources=replay_sources,
        capture_command=safe.clean_text(capture_command or f"row macro capture-plan {recording.name}", "capture command"),
        review_command=safe.clean_text(
            review_command or _macro_live_plan_command(recording.name, target_names, connected, clean_pane_ids),
            "review command",
        ),
        replay_commands=final_replay_commands,
        gui_record_button=bool(gui_record_button),
        gui_stop_button=bool(gui_stop_button),
        gui_cancel_button=bool(gui_cancel_button),
        per_event_timing_captured=bool(per_event_timing_captured),
        confirmation_prompt=bool(confirmation_prompt),
        cancel_prompt_verified=bool(cancel_prompt_verified),
        conflict_checked=bool(conflict_checked),
        real_connected_session=bool(real_connected_session),
        live_terminal_pane=bool(live_terminal_pane),
        per_keystroke_timing_replay=bool(per_keystroke_timing_replay),
        notes=notes,
    )


def write_macro_live_evidence_bundle(plan: MobaMacroLiveEvidenceBundlePlan) -> MobaMacroLiveEvidenceBundleResult:
    if plan.schema != MOBA_MACRO_LIVE_EVIDENCE_BUNDLE_SCHEMA:
        raise ValueError(f"macro live evidence bundle schema must be {MOBA_MACRO_LIVE_EVIDENCE_BUNDLE_SCHEMA}")
    root = Path(plan.out_dir)
    evidence_dir = root / "evidence"
    evidence_dir.mkdir(parents=True, exist_ok=True)
    capture_file = _copy_evidence_asset(Path(plan.capture_evidence_source), evidence_dir, "capture-session", root)
    review_file = _copy_evidence_asset(Path(plan.review_evidence_source), evidence_dir, "replay-review", root)
    replay_files: dict[str, str] = {}
    for index, profile in enumerate(plan.target_profiles, start=1):
        replay_files[profile] = _copy_evidence_asset(
            Path(plan.replay_evidence_sources[profile]),
            evidence_dir,
            f"replay-session-{index:02d}-{_safe_file_label(profile)}",
            root,
        )
    payload = {
        "schema": MOBA_MACRO_LIVE_EVIDENCE_SCHEMA,
        "release_target": plan.release_target,
        "macro": {
            "name": plan.macro_name,
            "event_count": plan.event_count,
            "input_sha256": plan.input_sha256,
        },
        "capture_session": {
            "status": "passed",
            "command": plan.capture_command,
            "evidence_file": capture_file,
            "evidence_sha256": _sha256_path(root / capture_file),
            "gui_record_button": plan.gui_record_button,
            "gui_stop_button": plan.gui_stop_button,
            "gui_cancel_button": plan.gui_cancel_button,
            "per_event_timing_captured": plan.per_event_timing_captured,
        },
        "replay_review": {
            "status": "passed",
            "command": plan.review_command,
            "evidence_file": review_file,
            "evidence_sha256": _sha256_path(root / review_file),
            "confirmation_prompt": plan.confirmation_prompt,
            "cancel_prompt_verified": plan.cancel_prompt_verified,
            "conflict_checked": plan.conflict_checked,
        },
        "replay_sessions": [
            {
                "profile": profile,
                "status": "passed",
                "command": plan.replay_commands[profile],
                "evidence_file": replay_files[profile],
                "evidence_sha256": _sha256_path(root / replay_files[profile]),
                "real_connected_session": plan.real_connected_session,
                "live_terminal_pane": plan.live_terminal_pane,
                "per_keystroke_timing_replay": plan.per_keystroke_timing_replay,
            }
            for profile in plan.target_profiles
        ],
    }
    target_evidence_path = Path(plan.evidence_path)
    write_json_atomic(target_evidence_path, payload, private=False)
    validation = validate_macro_live_replay_evidence(target_evidence_path, assets_dir=root)
    files = tuple(
        dict.fromkeys(
            (
                capture_file,
                review_file,
                *[replay_files[profile] for profile in plan.target_profiles],
                _relative_to_root(target_evidence_path, root),
            )
        )
    )
    return MobaMacroLiveEvidenceBundleResult(
        plan=plan,
        evidence_path=str(target_evidence_path),
        files=files,
        validation=validation,
        notes=list(plan.notes),
    )


def validate_macro_live_replay_evidence(
    evidence_path: Path,
    *,
    assets_dir: Path | None = None,
) -> MobaMacroLiveEvidenceValidation:
    target_evidence_path = Path(evidence_path)
    root = Path(assets_dir) if assets_dir is not None else target_evidence_path.parent
    errors: list[str] = []
    warnings: list[str] = []
    summary: dict[str, Any] = {
        "schema": "",
        "release_target": "",
        "macro": "",
        "replay_sessions": 0,
    }
    try:
        data = json.loads(target_evidence_path.read_text(encoding="utf-8"))
    except OSError as exc:
        errors.append(f"evidence file cannot be read: {exc}")
        data = {}
    except json.JSONDecodeError as exc:
        errors.append(f"evidence file is not valid JSON: {exc}")
        data = {}
    if not isinstance(data, dict):
        errors.append("evidence root must be a JSON object")
        data = {}

    schema = str(data.get("schema") or data.get("schema_version") or "")
    summary["schema"] = schema
    if schema != MOBA_MACRO_LIVE_EVIDENCE_SCHEMA:
        errors.append(f"schema must be {MOBA_MACRO_LIVE_EVIDENCE_SCHEMA}")
    summary["release_target"] = _required_text(data, "release_target", errors)

    macro = _required_mapping(data, "macro", errors)
    summary["macro"] = _required_text(macro, "name", errors, prefix="macro.")
    event_count = macro.get("event_count")
    if not isinstance(event_count, int) or event_count <= 0:
        errors.append("macro.event_count must be a positive integer")
    _required_sha256(_required_text(macro, "input_sha256", errors, prefix="macro."), "macro.input_sha256", errors)

    capture = _required_mapping(data, "capture_session", errors)
    _validate_action_evidence(capture, root, errors, "capture_session")
    for key in ("gui_record_button", "gui_stop_button", "gui_cancel_button", "per_event_timing_captured"):
        if capture.get(key) is not True:
            errors.append(f"capture_session.{key} must be true")

    review = _required_mapping(data, "replay_review", errors)
    _validate_action_evidence(review, root, errors, "replay_review")
    for key in ("confirmation_prompt", "cancel_prompt_verified", "conflict_checked"):
        if review.get(key) is not True:
            errors.append(f"replay_review.{key} must be true")

    sessions = data.get("replay_sessions")
    if not isinstance(sessions, list) or not sessions:
        errors.append("replay_sessions must be a non-empty list")
        sessions = []
    summary["replay_sessions"] = len(sessions)
    for index, session in enumerate(sessions, start=1):
        label = f"replay_sessions[{index}]"
        if not isinstance(session, dict):
            errors.append(f"{label} must be a JSON object")
            continue
        _required_text(session, "profile", errors, prefix=f"{label}.")
        _validate_action_evidence(session, root, errors, label)
        for key in ("real_connected_session", "live_terminal_pane", "per_keystroke_timing_replay"):
            if session.get(key) is not True:
                errors.append(f"{label}.{key} must be true")

    return MobaMacroLiveEvidenceValidation(
        evidence_path=str(target_evidence_path),
        assets_dir=str(root),
        passed=not errors,
        errors=errors,
        warnings=warnings,
        summary=summary,
    )


def run_macro_replay(
    plans: list[MobaMacroReplayPlan],
    *,
    dry_run: bool = False,
    timeout: float | None = None,
    runner: Any = subprocess.run,
) -> list[MobaMacroReplayResult]:
    results: list[MobaMacroReplayResult] = []
    for plan in plans:
        safe.argv_list(plan.command, "macro replay command")
        if dry_run:
            results.append(
                MobaMacroReplayResult(
                    macro_name=plan.macro_name,
                    profile_name=plan.profile_name,
                    command=plan.command,
                    dry_run=True,
                    ok=True,
                )
            )
            continue
        completed = runner(
            plan.command,
            input=plan.input_text,
            text=True,
            capture_output=True,
            check=False,
            timeout=timeout,
        )
        returncode = int(getattr(completed, "returncode", 1))
        results.append(
            MobaMacroReplayResult(
                macro_name=plan.macro_name,
                profile_name=plan.profile_name,
                command=plan.command,
                dry_run=False,
                ok=returncode == 0,
                returncode=returncode,
                stdout=str(getattr(completed, "stdout", "") or ""),
                stderr=str(getattr(completed, "stderr", "") or ""),
            )
        )
    return results


def _macro_live_plan_command(
    macro_name: str,
    target_profiles: Iterable[str],
    connected_profiles: Iterable[str],
    pane_ids: dict[str, str],
) -> str:
    parts = ["row", "macro", "live-plan", safe.option_value(macro_name, "macro name")]
    for profile in target_profiles:
        parts.extend(["--profile", safe.option_value(profile, "macro target profile")])
    for profile in connected_profiles:
        parts.extend(["--connected-profile", safe.option_value(profile, "connected profile")])
    for profile, pane_id in sorted(pane_ids.items()):
        parts.extend(["--pane-id", f"{safe.option_value(profile, 'pane profile')}={safe.option_value(pane_id, 'pane id')}"])
    return " ".join(parts)


def _copy_evidence_asset(source: Path, evidence_dir: Path, label: str, root: Path) -> str:
    resolved_source = source.expanduser()
    if not resolved_source.is_file():
        raise ValueError(f"{label} evidence file is missing: {resolved_source}")
    suffix = resolved_source.suffix if resolved_source.suffix else ".txt"
    target = evidence_dir / f"{label}{suffix}"
    if resolved_source.resolve() != target.resolve():
        shutil.copy2(resolved_source, target)
    return _relative_to_root(target, root)


def _relative_to_root(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _safe_file_label(value: str) -> str:
    clean = safe.option_value(value, "evidence label")
    return "".join(char if char.isalnum() or char in "._-" else "_" for char in clean)


def _require_recording_events(recording: MobaMacroRecording) -> None:
    if not recording.events:
        raise ValueError("macro recording has no events")
    for event in recording.events:
        if event.delay_ms < 0:
            raise ValueError("macro event delay must not be negative")


def _live_replay_steps(recording: MobaMacroRecording) -> list[MobaMacroLiveReplayStep]:
    elapsed = 0
    steps: list[MobaMacroLiveReplayStep] = []
    for event in recording.events:
        elapsed += event.delay_ms
        steps.append(
            MobaMacroLiveReplayStep(
                index=event.index,
                text=event.text,
                enter=event.enter,
                delay_ms=event.delay_ms,
                scheduled_after_ms=elapsed,
            )
        )
    return steps


def _total_delay_ms(recording: MobaMacroRecording) -> int:
    return sum(event.delay_ms for event in recording.events)


def _sha256_text(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _sha256_path(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _required_sha256(value: str, label: str, errors: list[str] | None = None) -> str:
    try:
        text = safe.clean_text(str(value), label)
    except ValueError as exc:
        if errors is not None:
            errors.append(f"{label} is invalid: {exc}")
            return str(value)
        raise
    if re.fullmatch(r"[0-9a-f]{64}", text):
        return text
    message = f"{label} must be a lowercase 64-character SHA-256 digest"
    if errors is not None:
        errors.append(message)
        return text
    raise ValueError(message)


def _required_mapping(data: dict[str, Any], key: str, errors: list[str]) -> dict[str, Any]:
    value = data.get(key)
    if isinstance(value, dict):
        return value
    errors.append(f"{key} must be a JSON object")
    return {}


def _required_text(
    data: dict[str, Any],
    key: str,
    errors: list[str],
    *,
    prefix: str = "",
) -> str:
    value = data.get(key)
    if isinstance(value, str) and value.strip():
        try:
            return safe.clean_text(value, f"{prefix}{key}")
        except ValueError as exc:
            errors.append(f"{prefix}{key} is invalid: {exc}")
            return value
    errors.append(f"{prefix}{key} must be a non-empty string")
    return ""


def _validate_action_evidence(action: dict[str, Any], assets_dir: Path, errors: list[str], label: str) -> None:
    if action.get("status") != "passed":
        errors.append(f"{label}.status must be passed")
    command = _required_text(action, "command", errors, prefix=f"{label}.")
    if not command:
        errors.append(f"{label}.command must record the executed action")
    evidence_file = _required_text(action, "evidence_file", errors, prefix=f"{label}.")
    digest = _required_sha256(
        _required_text(action, "evidence_sha256", errors, prefix=f"{label}."),
        f"{label}.evidence_sha256",
        errors,
    )
    if evidence_file and digest:
        _validate_asset_hash(assets_dir, evidence_file, digest, errors, label)


def _validate_asset_hash(
    assets_dir: Path,
    evidence_file: str,
    expected_sha256: str,
    errors: list[str],
    label: str,
) -> None:
    try:
        asset = _resolve_evidence_asset(assets_dir, evidence_file)
    except ValueError as exc:
        errors.append(f"{label}.evidence_file is invalid: {exc}")
        return
    if not asset.exists():
        errors.append(f"{label}.evidence_file does not exist: {asset}")
        return
    if not asset.is_file():
        errors.append(f"{label}.evidence_file is not a file: {asset}")
        return
    actual = _sha256_path(asset)
    if actual != expected_sha256:
        errors.append(f"{label}.evidence_sha256 does not match {asset.name}")


def _resolve_evidence_asset(assets_dir: Path, evidence_file: str) -> Path:
    relative = Path(safe.path_arg(evidence_file, "evidence file"))
    if relative.is_absolute():
        raise ValueError("must be relative to assets_dir")
    root = assets_dir.resolve()
    target = (root / relative).resolve()
    if root != target and root not in target.parents:
        raise ValueError("must stay inside assets_dir")
    return target


def _macro_body(value: str) -> str:
    text = str(value)
    if "\x00" in text:
        raise ValueError("macro typed input must not contain NUL bytes")
    return text.replace("\r\n", "\n").replace("\r", "\n")


def _typed_text(value: str) -> str:
    text = safe.clean_text(value, "macro typed text", allow_empty=True)
    if "\n" in text or "\r" in text:
        raise ValueError("macro typed event text must be one line")
    return text

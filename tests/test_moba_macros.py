from __future__ import annotations

import hashlib
import json
from pathlib import Path

from remote_ops_workspace.cli import build_parser
from remote_ops_workspace.moba_macros import (
    MobaMacroStore,
    build_macro_gui_capture_plan,
    build_macro_live_evidence_bundle_plan,
    build_macro_live_replay_plans,
    build_macro_replay_plans,
    build_terminal_macro_replay_injection,
    cancel_terminal_macro_capture,
    capture_terminal_macro_input,
    finish_terminal_macro_capture,
    record_typed_macro,
    review_macro_live_replay,
    run_macro_replay,
    start_terminal_macro_capture,
    validate_macro_live_replay_evidence,
    write_macro_live_evidence_bundle,
)
from remote_ops_workspace.models import Profile


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_moba_macro_recording_store_roundtrip(tmp_path: Path) -> None:
    store = MobaMacroStore(tmp_path / "macros.json")
    recording = record_typed_macro(
        "triage",
        "hostname\nuptime\n",
        description="basic host triage",
        tags=["ops"],
        delay_ms=25,
    )

    store.add(recording)
    loaded = store.get("triage")

    assert loaded.name == "triage"
    assert loaded.description == "basic host triage"
    assert loaded.tags == ["ops"]
    assert [event.text for event in loaded.events] == ["hostname", "uptime"]
    assert loaded.events[0].delay_ms == 25
    assert loaded.input_text == "hostname\nuptime\n"
    assert len(loaded.to_dict()["input_sha256"]) == 64


def test_moba_macro_recording_rejects_nul_input() -> None:
    try:
        record_typed_macro("bad", "hostname\x00")
    except ValueError as exc:
        assert "NUL" in str(exc)
    else:
        raise AssertionError("macro recording must reject NUL bytes")


def test_moba_macro_replay_plan_targets_ssh_profiles() -> None:
    recording = record_typed_macro("triage", "hostname\nuptime")
    profile = Profile(name="edge", protocol="ssh", host="192.0.2.10", username="admin")

    plans = build_macro_replay_plans(recording, [profile])

    assert plans[0].macro_name == "triage"
    assert plans[0].profile_name == "edge"
    assert plans[0].command == ["ssh", "-p", "22", "admin@192.0.2.10"]
    assert plans[0].input_text == "hostname\nuptime\n"
    assert plans[0].event_count == 2


def test_moba_macro_replay_rejects_non_ssh_profiles() -> None:
    recording = record_typed_macro("triage", "hostname")
    profile = Profile(name="web", protocol="http", url="https://example.invalid")

    try:
        build_macro_replay_plans(recording, [profile])
    except ValueError as exc:
        assert "ssh profiles only" in str(exc)
    else:
        raise AssertionError("macro replay should be scoped to ssh profiles")


def test_moba_macro_replay_dry_run_does_not_call_runner() -> None:
    recording = record_typed_macro("triage", "hostname")
    plans = build_macro_replay_plans(recording, [Profile(name="edge", protocol="ssh", host="192.0.2.10")])
    calls: list[list[str]] = []

    results = run_macro_replay(plans, dry_run=True, runner=lambda command, **kwargs: calls.append(command))

    assert results[0].dry_run is True
    assert results[0].ok is True
    assert calls == []


def test_moba_macro_replay_executes_with_recorded_stdin() -> None:
    recording = record_typed_macro("triage", "hostname")
    plans = build_macro_replay_plans(recording, [Profile(name="edge", protocol="ssh", host="192.0.2.10")])
    captured: dict[str, object] = {}

    def runner(command: list[str], **kwargs: object) -> _FakeCompletedProcess:
        captured["command"] = command
        captured["input"] = kwargs["input"]
        return _FakeCompletedProcess(0, "edge\n", "")

    results = run_macro_replay(plans, runner=runner)

    assert results[0].ok is True
    assert results[0].stdout == "edge\n"
    assert captured["command"] == ["ssh", "-p", "22", "192.0.2.10"]
    assert captured["input"] == "hostname\n"


def test_moba_macro_gui_capture_plan_exposes_controls_and_timing() -> None:
    recording = record_typed_macro("triage", "hostname\nuptime", delay_ms=125)

    plan = build_macro_gui_capture_plan(recording)

    assert plan.schema == "row.moba-macro.gui-capture-plan.v1"
    assert plan.macro_name == "triage"
    assert plan.event_count == 2
    assert plan.total_delay_ms == 250
    assert plan.capture_controls == ["record", "stop", "cancel"]
    assert plan.cancel_supported is True
    assert len(plan.input_sha256) == 64


def test_moba_macro_live_replay_review_blocks_disconnected_targets_without_force() -> None:
    recording = record_typed_macro("triage", "hostname")
    profiles = [
        Profile(name="edge", protocol="ssh", host="192.0.2.10"),
        Profile(name="core", protocol="ssh", host="192.0.2.11"),
    ]

    review = review_macro_live_replay(recording, profiles, connected_profiles=["edge"])
    forced = review_macro_live_replay(recording, profiles, connected_profiles=["edge"], force=True)

    assert review.allowed is False
    assert review.disconnected_profiles == ["core"]
    assert review.confirmation_required is True
    assert review.cancel_supported is True
    assert "not marked as connected" in review.prompt
    assert forced.allowed is True


def test_moba_macro_live_replay_plan_preserves_per_event_timing() -> None:
    recording = record_typed_macro("triage", "hostname\nuptime", delay_ms=75)
    profile = Profile(name="edge", protocol="ssh", host="192.0.2.10", username="admin")

    plans = build_macro_live_replay_plans(recording, [profile], pane_ids={"edge": "pane-1"})

    assert plans[0].schema == "row.moba-macro.live-replay-plan.v1"
    assert plans[0].profile_name == "edge"
    assert plans[0].pane_id == "pane-1"
    assert plans[0].command == ["ssh", "-p", "22", "admin@192.0.2.10"]
    assert plans[0].confirmation_required is True
    assert plans[0].cancel_supported is True
    assert [step.scheduled_after_ms for step in plans[0].steps] == [75, 150]


def test_terminal_macro_capture_state_finishes_recording_and_replay_injection() -> None:
    state = start_terminal_macro_capture("triage-live", pane_id="pane-1")

    capture_terminal_macro_input(state, "hostname", delay_ms=15)
    capture_terminal_macro_input(state, "uptime", delay_ms=25)
    state_dict = state.to_dict()
    recording = finish_terminal_macro_capture(state, description="GUI capture", tags=["gui"])
    injection = build_terminal_macro_replay_injection(recording, pane_id="pane-1")

    assert state_dict["schema"] == "row.moba-macro.terminal-capture-state.v1"
    assert state_dict["source"] == "pyqt-terminal-pane"
    assert state_dict["event_count"] == 2
    assert recording.source == "pyqt-terminal-pane"
    assert recording.input_text == "hostname\nuptime\n"
    assert injection.schema == "row.moba-macro.terminal-replay-injection.v1"
    assert injection.injected_payloads == ["hostname\n", "uptime\n"]
    assert [step.scheduled_after_ms for step in injection.steps] == [15, 40]
    assert injection.cancel_supported is True


def test_terminal_macro_capture_cancel_discards_pending_events() -> None:
    state = start_terminal_macro_capture("triage-live", pane_id="pane-1")
    capture_terminal_macro_input(state, "hostname", delay_ms=5)

    cancel_terminal_macro_capture(state)

    assert state.active is False
    assert state.cancelled is True
    assert state.events == []
    try:
        finish_terminal_macro_capture(state)
    except ValueError as exc:
        assert "cancelled" in str(exc)
    else:
        raise AssertionError("cancelled terminal macro capture must not finish")


def test_moba_macro_live_evidence_validation_accepts_real_connected_bundle(tmp_path: Path) -> None:
    capture_log = tmp_path / "capture.txt"
    review_log = tmp_path / "review.txt"
    replay_log = tmp_path / "replay.txt"
    capture_log.write_text("row macro capture-plan triage\n", encoding="utf-8")
    review_log.write_text("row macro live-plan triage --profile edge --connected-profile edge\n", encoding="utf-8")
    replay_log.write_text("live pane replay edge\n", encoding="utf-8")
    evidence = tmp_path / "macro-live-evidence.json"
    input_sha = hashlib.sha256(b"hostname\n").hexdigest()
    evidence.write_text(
        json.dumps(
            {
                "schema": "row.moba-macro.live-replay-evidence.v1",
                "release_target": "windows-x64",
                "macro": {"name": "triage", "event_count": 1, "input_sha256": input_sha},
                "capture_session": {
                    "status": "passed",
                    "command": "row macro capture-plan triage",
                    "evidence_file": "capture.txt",
                    "evidence_sha256": _sha256(capture_log),
                    "gui_record_button": True,
                    "gui_stop_button": True,
                    "gui_cancel_button": True,
                    "per_event_timing_captured": True,
                },
                "replay_review": {
                    "status": "passed",
                    "command": "row macro live-plan triage --profile edge --connected-profile edge",
                    "evidence_file": "review.txt",
                    "evidence_sha256": _sha256(review_log),
                    "confirmation_prompt": True,
                    "cancel_prompt_verified": True,
                    "conflict_checked": True,
                },
                "replay_sessions": [
                    {
                        "profile": "edge",
                        "status": "passed",
                        "command": "live pane replay edge",
                        "evidence_file": "replay.txt",
                        "evidence_sha256": _sha256(replay_log),
                        "real_connected_session": True,
                        "live_terminal_pane": True,
                        "per_keystroke_timing_replay": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = validate_macro_live_replay_evidence(evidence, assets_dir=tmp_path)

    assert result.passed is True
    assert result.errors == []
    assert result.summary["macro"] == "triage"
    assert result.summary["replay_sessions"] == 1


def test_moba_macro_live_evidence_bundle_writer_creates_valid_bundle(tmp_path: Path) -> None:
    recording = record_typed_macro("triage", "hostname\n", delay_ms=25)
    profile = Profile(name="edge", protocol="ssh", host="192.0.2.10", username="admin")
    capture_log = tmp_path / "source-capture.txt"
    review_log = tmp_path / "source-review.txt"
    replay_log = tmp_path / "source-replay.txt"
    capture_log.write_text("record stop cancel controls visible\n", encoding="utf-8")
    review_log.write_text("confirmation and cancel prompt verified\n", encoding="utf-8")
    replay_log.write_text("real connected terminal pane replay with per-keystroke timing\n", encoding="utf-8")

    plan = build_macro_live_evidence_bundle_plan(
        recording,
        [profile],
        out_dir=tmp_path / "bundle",
        capture_evidence=capture_log,
        review_evidence=review_log,
        replay_evidence={"edge": replay_log},
        release_target="windows-x64",
        connected_profiles=["edge"],
        pane_ids={"edge": "pane-1"},
        gui_record_button=True,
        gui_stop_button=True,
        gui_cancel_button=True,
        per_event_timing_captured=True,
        confirmation_prompt=True,
        cancel_prompt_verified=True,
        conflict_checked=True,
        real_connected_session=True,
        live_terminal_pane=True,
        per_keystroke_timing_replay=True,
    )
    result = write_macro_live_evidence_bundle(plan)

    assert result.validation.passed is True
    assert result.validation.errors == []
    assert "moba-macro-live.json" in result.files
    assert "evidence/replay-session-01-edge.txt" in result.files
    assert Path(result.evidence_path).is_file()


def test_moba_macro_live_evidence_rejects_missing_real_session(tmp_path: Path) -> None:
    action = tmp_path / "action.txt"
    action.write_text("passed\n", encoding="utf-8")
    passed_action = {
        "status": "passed",
        "command": "action",
        "evidence_file": "action.txt",
        "evidence_sha256": _sha256(action),
    }
    evidence = tmp_path / "macro-live-evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "schema": "row.moba-macro.live-replay-evidence.v1",
                "release_target": "windows-x64",
                "macro": {"name": "triage", "event_count": 1, "input_sha256": "a" * 64},
                "capture_session": {
                    **passed_action,
                    "gui_record_button": True,
                    "gui_stop_button": True,
                    "gui_cancel_button": True,
                    "per_event_timing_captured": True,
                },
                "replay_review": {
                    **passed_action,
                    "confirmation_prompt": True,
                    "cancel_prompt_verified": True,
                    "conflict_checked": True,
                },
                "replay_sessions": [
                    {
                        **passed_action,
                        "profile": "edge",
                        "real_connected_session": False,
                        "live_terminal_pane": True,
                        "per_keystroke_timing_replay": True,
                    }
                ],
            }
        ),
        encoding="utf-8",
    )

    result = validate_macro_live_replay_evidence(evidence, assets_dir=tmp_path)

    assert result.passed is False
    assert "replay_sessions[1].real_connected_session must be true" in result.errors


def test_moba_macro_cli_commands_are_registered() -> None:
    parser = build_parser()
    record = parser.parse_args(["macro", "record", "--name", "triage", "--text", "hostname"])
    list_args = parser.parse_args(["macro", "list", "--json"])
    show = parser.parse_args(["macro", "show", "triage"])
    remove = parser.parse_args(["macro", "remove", "triage"])
    replay = parser.parse_args(["macro", "replay", "triage", "--profile", "edge", "--dry-run"])
    capture_plan = parser.parse_args(["macro", "capture-plan", "triage", "--json"])
    live_plan = parser.parse_args(
        [
            "macro",
            "live-plan",
            "triage",
            "--profile",
            "edge",
            "--connected-profile",
            "edge",
            "--pane-id",
            "edge=pane-1",
            "--json",
        ]
    )
    evidence_bundle = parser.parse_args(
        [
            "macro",
            "evidence-bundle",
            "triage",
            "--profile",
            "edge",
            "--out-dir",
            "artifact",
            "--capture-evidence",
            "capture.txt",
            "--review-evidence",
            "review.txt",
            "--replay-evidence",
            "edge=replay.txt",
            "--connected-profile",
            "edge",
            "--pane-id",
            "edge=pane-1",
            "--gui-record-button",
            "--gui-stop-button",
            "--gui-cancel-button",
            "--per-event-timing-captured",
            "--confirmation-prompt",
            "--cancel-prompt-verified",
            "--conflict-checked",
            "--real-connected-session",
            "--live-terminal-pane",
            "--per-keystroke-timing-replay",
            "--json",
        ]
    )
    evidence = parser.parse_args(["macro", "evidence-verify", "--evidence", "macro-live.json", "--json"])

    assert record.func.__name__ == "cmd_macro_record"
    assert list_args.func.__name__ == "cmd_macro_list"
    assert show.func.__name__ == "cmd_macro_show"
    assert remove.func.__name__ == "cmd_macro_remove"
    assert replay.func.__name__ == "cmd_macro_replay"
    assert capture_plan.func.__name__ == "cmd_macro_capture_plan"
    assert live_plan.func.__name__ == "cmd_macro_live_plan"
    assert evidence_bundle.func.__name__ == "cmd_macro_evidence_bundle"
    assert evidence.func.__name__ == "cmd_macro_evidence_verify"


class _FakeCompletedProcess:
    def __init__(self, returncode: int, stdout: str, stderr: str) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

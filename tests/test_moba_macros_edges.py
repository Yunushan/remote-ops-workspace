from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest

import remote_ops_workspace.moba_macros as macros
from remote_ops_workspace.models import Profile


def _profile(name: str = "edge", protocol: str = "ssh") -> Profile:
    if protocol == "ssh":
        return Profile(name=name, protocol=protocol, host=f"{name}.example")
    return Profile(name=name, protocol=protocol, url="https://example.test")


def _recording() -> macros.MobaMacroRecording:
    return macros.record_typed_macro("triage", "hostname\nuptime", delay_ms=5)


def test_macro_value_objects_serialize() -> None:
    recording = macros.MobaMacroRecording(
        name="mixed",
        events=[
            macros.MobaMacroEvent(index=1, text="printf x", enter=False, delay_ms=1),
            macros.MobaMacroEvent(index=2, text="uptime", enter=True, delay_ms=2),
        ],
    )
    assert recording.input_text == "printf xuptime\n"
    plans = macros.build_macro_replay_plans(recording, [_profile()])
    assert plans[0].to_dict()["event_count"] == 2
    dry_result = macros.run_macro_replay(plans, dry_run=True)[0]
    assert dry_result.to_dict()["ok"] is True

    capture = macros.build_macro_gui_capture_plan(recording)
    assert capture.to_dict()["cancel_supported"] is True
    review = macros.review_macro_live_replay(recording, [_profile()], connected_profiles=["edge"])
    assert review.to_dict()["allowed"] is True
    live = macros.build_macro_live_replay_plans(recording, [_profile()])[0]
    assert live.to_dict()["steps"][0]["scheduled_after_ms"] == 1
    injection = macros.build_terminal_macro_replay_injection(recording, pane_id="pane-1")
    assert injection.to_dict()["injected_payloads"] == ["printf x", "uptime\n"]


def test_macro_store_duplicate_missing_and_remove_paths(tmp_path: Path) -> None:
    store = macros.MobaMacroStore(tmp_path / "macros.json")
    recording = _recording()
    store.add(recording)
    with pytest.raises(ValueError, match="already exists"):
        store.add(recording)
    with pytest.raises(KeyError, match="missing"):
        store.get("missing")
    with pytest.raises(KeyError, match="missing"):
        store.remove("missing")
    store.remove("triage")
    assert store.load() == []


def test_recording_and_batch_replay_reject_empty_inputs() -> None:
    with pytest.raises(ValueError, match="delay must not be negative"):
        macros.record_typed_macro("bad", "hostname", delay_ms=-1)
    with pytest.raises(ValueError, match="at least one typed line"):
        macros.record_typed_macro("bad", "")

    empty = macros.MobaMacroRecording(name="empty", events=[])
    with pytest.raises(ValueError, match="has no events"):
        macros.build_macro_replay_plans(empty, [_profile()])
    with pytest.raises(ValueError, match="at least one profile"):
        macros.build_macro_replay_plans(_recording(), [])


def test_live_review_and_plan_reject_missing_or_invalid_targets() -> None:
    with pytest.raises(ValueError, match="at least one target profile"):
        macros.review_macro_live_replay(_recording(), [])
    connected = macros.review_macro_live_replay(
        _recording(),
        [_profile()],
        connected_profiles=["edge"],
    )
    assert "Confirm live macro replay" in connected.prompt
    assert connected.disconnected_profiles == []

    with pytest.raises(ValueError, match="ssh profiles only"):
        macros.build_macro_live_replay_plans(_recording(), [_profile(protocol="https")])
    with pytest.raises(ValueError, match="at least one profile"):
        macros.build_macro_live_replay_plans(_recording(), [])


def test_terminal_capture_rejects_invalid_lifecycle_and_delay() -> None:
    inactive = macros.start_terminal_macro_capture("inactive", pane_id="pane")
    inactive.active = False
    with pytest.raises(ValueError, match="not active"):
        macros.capture_terminal_macro_input(inactive, "hostname")

    cancelled = macros.start_terminal_macro_capture("cancelled", pane_id="pane")
    cancelled.cancelled = True
    with pytest.raises(ValueError, match="has been cancelled"):
        macros.capture_terminal_macro_input(cancelled, "hostname")

    active = macros.start_terminal_macro_capture("active", pane_id="pane")
    with pytest.raises(ValueError, match="delay must not be negative"):
        macros.capture_terminal_macro_input(active, "hostname", delay_ms=-1)
    with pytest.raises(ValueError, match="at least one event"):
        macros.finish_terminal_macro_capture(active)


def test_recording_event_validation_and_multiline_rejection() -> None:
    empty = macros.MobaMacroRecording(name="empty", events=[])
    with pytest.raises(ValueError, match="has no events"):
        macros._require_recording_events(empty)
    negative = macros.MobaMacroRecording(
        name="bad",
        events=[macros.MobaMacroEvent(index=1, text="hostname", delay_ms=-1)],
    )
    with pytest.raises(ValueError, match="delay must not be negative"):
        macros._require_recording_events(negative)
    with pytest.raises(ValueError, match="control characters"):
        macros._typed_text("one\ntwo")


def _bundle_args(tmp_path: Path) -> dict[str, object]:
    return {
        "out_dir": tmp_path / "bundle",
        "capture_evidence": tmp_path / "capture.txt",
        "review_evidence": tmp_path / "review.txt",
    }


def test_live_evidence_plan_rejects_profile_and_source_mismatches(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="at least one target profile"):
        macros.build_macro_live_evidence_bundle_plan(
            _recording(),
            [],
            replay_evidence={},
            **_bundle_args(tmp_path),
        )
    with pytest.raises(ValueError, match="missing replay evidence"):
        macros.build_macro_live_evidence_bundle_plan(
            _recording(),
            [_profile()],
            replay_evidence={},
            **_bundle_args(tmp_path),
        )
    with pytest.raises(ValueError, match="unknown profile"):
        macros.build_macro_live_evidence_bundle_plan(
            _recording(),
            [_profile()],
            replay_evidence={"edge": tmp_path / "edge.txt", "unknown": tmp_path / "unknown.txt"},
            **_bundle_args(tmp_path),
        )
    with pytest.raises(ValueError, match="replay command was supplied for unknown"):
        macros.build_macro_live_evidence_bundle_plan(
            _recording(),
            [_profile()],
            replay_evidence={"edge": tmp_path / "edge.txt"},
            replay_commands={"unknown": "run"},
            **_bundle_args(tmp_path),
        )


def test_incomplete_live_evidence_plan_and_result_serialize(tmp_path: Path) -> None:
    plan = macros.build_macro_live_evidence_bundle_plan(
        _recording(),
        [_profile()],
        replay_evidence={"edge": tmp_path / "edge.txt"},
        **_bundle_args(tmp_path),
    )
    assert any("Replay review is not allowed" in note for note in plan.notes)
    assert any("flags are incomplete" in note for note in plan.notes)
    assert plan.to_dict()["target_profiles"] == ["edge"]

    validation = macros.MobaMacroLiveEvidenceValidation(
        evidence_path="evidence.json",
        assets_dir=".",
        passed=False,
        errors=["missing"],
        warnings=[],
        summary={},
    )
    assert validation.to_dict()["errors"] == ["missing"]
    result = macros.MobaMacroLiveEvidenceBundleResult(
        plan=plan,
        evidence_path=plan.evidence_path,
        files=("evidence.json",),
        validation=validation,
        notes=[],
    )
    assert result.to_dict()["validation"]["passed"] is False

    plan.schema = "wrong"
    with pytest.raises(ValueError, match="bundle schema"):
        macros.write_macro_live_evidence_bundle(plan)


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("{", "not valid JSON"),
        ("[]", "root must be a JSON object"),
    ],
)
def test_live_evidence_validator_rejects_malformed_roots(
    tmp_path: Path,
    content: str,
    message: str,
) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(content, encoding="utf-8")
    result = macros.validate_macro_live_replay_evidence(evidence)
    assert any(message in error for error in result.errors)


def test_live_evidence_validator_reports_missing_contracts(tmp_path: Path) -> None:
    result = macros.validate_macro_live_replay_evidence(tmp_path / "missing.json")
    assert result.passed is False
    assert any("cannot be read" in error for error in result.errors)
    assert any("macro.event_count" in error for error in result.errors)
    assert any("capture_session.gui_record_button" in error for error in result.errors)
    assert any("replay_review.conflict_checked" in error for error in result.errors)
    assert any("replay_sessions must be a non-empty list" in error for error in result.errors)


def test_live_evidence_validator_rejects_non_object_session(tmp_path: Path) -> None:
    evidence = tmp_path / "invalid.json"
    evidence.write_text(
        json.dumps(
            {
                "schema": "wrong",
                "release_target": "target",
                "macro": {"event_count": 0},
                "capture_session": {},
                "replay_review": {},
                "replay_sessions": ["not-an-object"],
            }
        ),
        encoding="utf-8",
    )
    result = macros.validate_macro_live_replay_evidence(evidence, assets_dir=tmp_path)
    assert any("replay_sessions[1] must be a JSON object" in error for error in result.errors)


def test_evidence_copy_digest_mapping_and_text_helpers_fail_closed(tmp_path: Path) -> None:
    evidence_dir = tmp_path / "evidence"
    evidence_dir.mkdir()
    with pytest.raises(ValueError, match="evidence file is missing"):
        macros._copy_evidence_asset(tmp_path / "missing.txt", evidence_dir, "capture-session", tmp_path)
    target = evidence_dir / "capture-session.txt"
    target.write_text("present", encoding="utf-8")
    assert (
        macros._copy_evidence_asset(target, evidence_dir, "capture-session", tmp_path)
        == "evidence/capture-session.txt"
    )

    errors: list[str] = []
    assert macros._required_sha256("\n", "digest", errors) == "\n"
    with pytest.raises(ValueError, match="control characters"):
        macros._required_sha256("\n", "digest")
    with pytest.raises(ValueError, match="lowercase 64-character"):
        macros._required_sha256("bad", "digest")
    assert macros._required_sha256("bad", "digest", errors) == "bad"
    assert macros._required_mapping({"item": []}, "item", errors) == {}
    assert macros._required_text({"item": "bad\ntext"}, "item", errors) == "bad\ntext"
    assert macros._required_text({}, "item", errors) == ""


def test_action_and_asset_evidence_fail_closed(tmp_path: Path) -> None:
    errors: list[str] = []
    macros._validate_action_evidence({}, tmp_path, errors, "action")
    assert "action.status must be passed" in errors
    assert "action.command must record the executed action" in errors

    absolute = tmp_path / "absolute.txt"
    macros._validate_asset_hash(tmp_path, str(absolute), "a" * 64, errors, "absolute")
    macros._validate_asset_hash(tmp_path, "missing.txt", "a" * 64, errors, "missing")
    directory = tmp_path / "directory"
    directory.mkdir()
    macros._validate_asset_hash(tmp_path, "directory", "a" * 64, errors, "directory")
    asset = tmp_path / "asset.txt"
    asset.write_text("content", encoding="utf-8")
    macros._validate_asset_hash(tmp_path, "asset.txt", "a" * 64, errors, "mismatch")

    assert any("absolute.evidence_file is invalid" in error for error in errors)
    assert any("missing.evidence_file does not exist" in error for error in errors)
    assert any("directory.evidence_file is not a file" in error for error in errors)
    assert any("mismatch.evidence_sha256 does not match" in error for error in errors)
    with pytest.raises(ValueError, match="inside assets_dir"):
        macros._resolve_evidence_asset(tmp_path, "../escape.txt")


def test_replay_result_defaults_handle_missing_process_attributes() -> None:
    plan = macros.build_macro_replay_plans(_recording(), [_profile()])[0]
    result = macros.run_macro_replay([plan], runner=lambda *_args, **_kwargs: SimpleNamespace())[0]
    assert result.ok is False
    assert result.returncode == 1
    assert result.stdout == ""
    assert result.stderr == ""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from scripts.check_moba_transport_terminal_evidence import (
    PROOF_SCHEMAS,
    SCHEMA,
    validate_moba_transport_terminal_evidence,
)
from scripts.check_mobaxterm_parity_evidence import check_record
from scripts.finalize_mobaxterm_parity_evidence_record import finalize_candidate
from scripts.make_mobaxterm_parity_evidence_record import build_evidence_record

HEAD_SHA = "d" * 40
REPOSITORY = "example/remote-ops-workspace"
RELEASE_TAG = "v1.0.20"
RUN_URL = "https://github.com/example/remote-ops-workspace/actions/runs/1234"
CAPTURED_AT = "2026-08-23T12:34:56Z"
RELEASE_TARGET = "windows-x64"
SESSION_ID = "session-123"
TRANSPORT_ID = "transport-456"


def test_complete_transport_terminal_evidence_passes(tmp_path: Path) -> None:
    evidence = _write_complete_evidence(tmp_path)

    result = validate_moba_transport_terminal_evidence(evidence, assets_dir=tmp_path)

    assert result.passed is True
    assert result.errors == []
    assert result.summary == {
        "schema": SCHEMA,
        "release_target": RELEASE_TARGET,
        "session_id": SESSION_ID,
        "transport_id": TRANSPORT_ID,
        "repository": REPOSITORY,
        "release_tag": RELEASE_TAG,
        "source_head_sha": HEAD_SHA,
        "workflow_run_url": RUN_URL,
        "run_attempt": 2,
        "proof_count": 6,
    }


def test_transport_terminal_evidence_rejects_tampered_proof_bytes(tmp_path: Path) -> None:
    evidence = _write_complete_evidence(tmp_path)
    proof_path = tmp_path / "terminal-grid.json"
    proof_path.write_text("{}\n", encoding="utf-8")

    result = validate_moba_transport_terminal_evidence(evidence, assets_dir=tmp_path)

    assert result.passed is False
    assert "proofs.terminal_grid.sha256 does not match terminal-grid.json" in result.errors


def test_transport_terminal_evidence_rejects_identity_drift(tmp_path: Path) -> None:
    evidence = _write_complete_evidence(tmp_path)
    _mutate_proof_and_rebind(
        evidence,
        tmp_path,
        "connection_state",
        {"source_head_sha": "e" * 40},
    )

    result = validate_moba_transport_terminal_evidence(evidence, assets_dir=tmp_path)

    assert result.passed is False
    assert (
        "proofs.connection_state.source_head_sha must match the top-level evidence identity"
        in result.errors
    )


def test_transport_terminal_evidence_fails_closed_on_transcript_grid(tmp_path: Path) -> None:
    evidence = _write_complete_evidence(tmp_path)
    _mutate_proof_and_rebind(
        evidence,
        tmp_path,
        "terminal_grid",
        {"real_cell_grid": False, "no_transcript_fallback": False},
    )

    result = validate_moba_transport_terminal_evidence(evidence, assets_dir=tmp_path)

    assert result.passed is False
    assert "proofs.terminal_grid.real_cell_grid must be true" in result.errors
    assert "proofs.terminal_grid.no_transcript_fallback must be true" in result.errors


def test_transport_terminal_evidence_requires_mouse_and_alternate_screen_semantics(
    tmp_path: Path,
) -> None:
    evidence = _write_complete_evidence(tmp_path)
    _mutate_proof_and_rebind(
        evidence,
        tmp_path,
        "terminal_modes",
        {"sgr_mouse_reporting": False, "mouse_press_release_wheel": False},
    )
    _mutate_proof_and_rebind(
        evidence,
        tmp_path,
        "alternate_screen",
        {"primary_screen_restored": False, "shell_input_resumed": False},
    )

    result = validate_moba_transport_terminal_evidence(evidence, assets_dir=tmp_path)

    assert result.passed is False
    assert "proofs.terminal_modes.sgr_mouse_reporting must be true" in result.errors
    assert "proofs.terminal_modes.mouse_press_release_wheel must be true" in result.errors
    assert "proofs.alternate_screen.primary_screen_restored must be true" in result.errors
    assert "proofs.alternate_screen.shell_input_resumed must be true" in result.errors


def test_transport_terminal_evidence_requires_remote_non_fixture_capture(tmp_path: Path) -> None:
    evidence = _write_complete_evidence(tmp_path)
    data = _read_json(evidence)
    data["source"]["fixture"] = True
    data["session"]["loopback"] = True
    _write_json(evidence, data)
    _mutate_proof_and_rebind(
        evidence,
        tmp_path,
        "connected_session",
        {"fixture": True, "real_connected_session": False},
    )

    result = validate_moba_transport_terminal_evidence(evidence, assets_dir=tmp_path)

    assert result.passed is False
    assert "source.fixture must be false" in result.errors
    assert "session.loopback must be false for strict remote connected evidence" in result.errors
    assert "proofs.connected_session.fixture must be false" in result.errors
    assert "proofs.connected_session.real_connected_session must be true" in result.errors


def test_article_eight_generator_emits_candidate_only(tmp_path: Path) -> None:
    errors, record, _artifact = _build_candidate(tmp_path)

    assert errors == []
    assert record["status"] == "candidate"
    assert record["article_id"] == "shared-authenticated-transport-terminal-grid"
    assert record["validation_summary"]["summary"]["source_head_sha"] == HEAD_SHA
    assert "release_source" not in record
    assert "acceptance_review" not in record


def test_article_eight_generator_rejects_release_target_drift(tmp_path: Path) -> None:
    evidence = _write_complete_evidence(tmp_path)
    artifact = tmp_path / "moba-transport-terminal.zip"
    artifact.write_bytes(b"release evidence bundle\n")

    errors, record = build_evidence_record(
        _generator_args(evidence, artifact, release_target="windows-arm64")
    )

    assert record == {}
    assert errors == [
        "shared-authenticated-transport-terminal-grid validated release_target "
        "'windows-x64' must match --release-target 'windows-arm64'"
    ]


def test_article_eight_generator_rejects_release_repository_drift(tmp_path: Path) -> None:
    evidence = _write_complete_evidence(tmp_path)
    artifact = tmp_path / "moba-transport-terminal.zip"
    artifact.write_bytes(b"release evidence bundle\n")
    args = _generator_args(evidence, artifact)
    args.release_asset_url = [
        "https://github.com/other/remote-ops-workspace/releases/download/"
        f"{RELEASE_TAG}/{artifact.name}"
    ]

    errors, record = build_evidence_record(args)

    assert record == {}
    assert errors == [
        "shared-authenticated-transport-terminal-grid validated repository "
        "'example/remote-ops-workspace' must exactly match release asset repository "
        "['other/remote-ops-workspace']"
    ]


def test_article_eight_finalizer_binds_validated_source_run(tmp_path: Path) -> None:
    candidate_errors, candidate, artifact = _build_candidate(tmp_path)
    assert candidate_errors == []

    errors, accepted = finalize_candidate(
        candidate,
        repository=REPOSITORY,
        source_head_sha="e" * 40,
        tag_source_head_sha="e" * 40,
        workflow_run_url=RUN_URL,
        run_attempt=2,
        reviewer="release-reviewer",
        review_url=(
            "https://github.com/example/remote-ops-workspace/pull/42#pullrequestreview-99"
        ),
        reviewed_at=CAPTURED_AT,
        published_assets={artifact.name: artifact},
    )

    assert accepted == {}
    assert any("source_head_sha must match accepted release provenance" in error for error in errors)


def test_article_eight_finalizer_accepts_exact_validated_source_run(tmp_path: Path) -> None:
    candidate_errors, candidate, artifact = _build_candidate(tmp_path)
    assert candidate_errors == []

    errors, accepted = finalize_candidate(
        candidate,
        repository=REPOSITORY,
        source_head_sha=HEAD_SHA,
        tag_source_head_sha=HEAD_SHA,
        workflow_run_url=RUN_URL,
        run_attempt=2,
        reviewer="release-reviewer",
        review_url=(
            "https://github.com/example/remote-ops-workspace/pull/42#pullrequestreview-99"
        ),
        reviewed_at=CAPTURED_AT,
        published_assets={artifact.name: artifact},
    )

    assert errors == []
    assert accepted["status"] == "accepted"
    assert accepted["release_source"] == {
        "repository": REPOSITORY,
        "release_tag": RELEASE_TAG,
        "head_sha": HEAD_SHA,
        "tag_source_head_sha": HEAD_SHA,
        "workflow_run_url": RUN_URL,
        "run_attempt": 2,
    }


def test_article_eight_accepted_checker_rejects_validated_source_drift(tmp_path: Path) -> None:
    candidate_errors, candidate, artifact = _build_candidate(tmp_path)
    assert candidate_errors == []
    errors, accepted = finalize_candidate(
        candidate,
        repository=REPOSITORY,
        source_head_sha=HEAD_SHA,
        tag_source_head_sha=HEAD_SHA,
        workflow_run_url=RUN_URL,
        run_attempt=2,
        reviewer="release-reviewer",
        review_url=(
            "https://github.com/example/remote-ops-workspace/pull/42#pullrequestreview-99"
        ),
        reviewed_at=CAPTURED_AT,
        published_assets={artifact.name: artifact},
    )
    assert errors == []
    accepted["release_source"]["head_sha"] = "e" * 40
    accepted["release_source"]["tag_source_head_sha"] = "e" * 40

    record_errors = check_record(accepted)

    assert any(
        "release_source.head_sha must match validation summary provenance" in error
        for error in record_errors
    )


def _build_candidate(tmp_path: Path) -> tuple[list[str], dict[str, Any], Path]:
    evidence = _write_complete_evidence(tmp_path)
    artifact = tmp_path / "moba-transport-terminal.zip"
    artifact.write_bytes(b"release evidence bundle\n")
    errors, record = build_evidence_record(_generator_args(evidence, artifact))
    return errors, record, artifact


def _generator_args(
    evidence: Path,
    artifact: Path,
    *,
    release_target: str = RELEASE_TARGET,
) -> SimpleNamespace:
    return SimpleNamespace(
        article_id="shared-authenticated-transport-terminal-grid",
        release_tag="v1.0.20",
        release_target=release_target,
        evidence=evidence,
        assets_dir=evidence.parent,
        release_asset_url=[
            "https://github.com/example/remote-ops-workspace/releases/download/"
            "v1.0.20/moba-transport-terminal.zip"
        ],
        artifact=[f"{artifact.name}={artifact}"],
    )


def _write_complete_evidence(root: Path) -> Path:
    common: dict[str, Any] = {
        "release_target": RELEASE_TARGET,
        "session_id": SESSION_ID,
        "transport_id": TRANSPORT_ID,
        "repository": REPOSITORY,
        "release_tag": RELEASE_TAG,
        "source_head_sha": HEAD_SHA,
        "workflow_run_url": RUN_URL,
        "run_attempt": 2,
        "captured_at_utc": CAPTURED_AT,
    }
    proofs = {
        "shared_transport": {
            **common,
            "schema": PROOF_SCHEMAS["shared_transport"],
            "transport_mode": "shared-authenticated-transport",
            "authenticated_transport_established": True,
            "terminal_channel_opened": True,
            "sftp_channel_opened": True,
            "monitoring_channel_opened": True,
            "credential_reuse_without_reprompt": True,
            "authentication_event_count": 1,
            "credential_reprompt_count": 0,
            "terminal_channel_transport_id": TRANSPORT_ID,
            "sftp_channel_transport_id": TRANSPORT_ID,
            "monitoring_channel_transport_id": TRANSPORT_ID,
        },
        "connection_state": {
            **common,
            "schema": PROOF_SCHEMAS["connection_state"],
            "transition_sequence": [
                "connecting",
                "authenticating",
                "connected",
                "closing",
                "closed",
            ],
            "disconnect_reason_recorded": True,
            "terminal_exit_status_recorded": True,
            "reconnect_transition_recorded": True,
            "state_visible_to_terminal_sftp_monitoring": True,
            "terminal_exit_status": 0,
        },
        "terminal_grid": {
            **common,
            "schema": PROOF_SCHEMAS["terminal_grid"],
            "rows": 40,
            "columns": 120,
            "real_cell_grid": True,
            "cursor_addressing": True,
            "scroll_regions": True,
            "dirty_region_updates": True,
            "wide_character_width": True,
            "combining_character_support": True,
            "resize_reflow_stable": True,
            "no_transcript_fallback": True,
            "initial_screen_sha256": "1" * 64,
            "updated_screen_sha256": "2" * 64,
        },
        "alternate_screen": {
            **common,
            "schema": PROOF_SCHEMAS["alternate_screen"],
            "application": "vim",
            "entered": True,
            "full_screen_application_rendered": True,
            "cursor_addressing_stable": True,
            "resize_stable": True,
            "exited": True,
            "primary_screen_restored": True,
            "shell_input_resumed": True,
            "primary_before_sha256": "3" * 64,
            "alternate_screen_sha256": "4" * 64,
            "primary_restored_sha256": "3" * 64,
        },
        "terminal_modes": {
            **common,
            "schema": PROOF_SCHEMAS["terminal_modes"],
            "cursor_position": True,
            "cursor_visibility": True,
            "cursor_shape": True,
            "sgr_attributes": True,
            "ansi_16_colors": True,
            "indexed_256_colors": True,
            "truecolor": True,
            "application_cursor_keys": True,
            "bracketed_paste": True,
            "sgr_mouse_reporting": True,
            "mouse_enable_disable": True,
            "mouse_press_release_wheel": True,
            "mode_capture_sha256": "5" * 64,
        },
        "connected_session": {
            **common,
            "schema": PROOF_SCHEMAS["connected_session"],
            "real_connected_session": True,
            "native_host": True,
            "remote_host_observed": True,
            "terminal_input_output_round_trip": True,
            "sftp_round_trip": True,
            "monitoring_sample_observed": True,
            "same_authenticated_transport_observed": True,
            "fixture": False,
            "simulation": False,
            "placeholder": False,
            "observed_transport_id": TRANSPORT_ID,
            "session_duration_seconds": 42.5,
            "transcript_sha256": "6" * 64,
        },
    }
    references: dict[str, dict[str, str]] = {}
    for name, proof in proofs.items():
        path = root / f"{name.replace('_', '-')}.json"
        _write_json(path, proof)
        references[name] = {"file": path.name, "sha256": _sha256(path)}
    evidence = root / "moba-transport-terminal-evidence.json"
    _write_json(
        evidence,
        {
            "schema": SCHEMA,
            "release_target": RELEASE_TARGET,
            "source": {
                "repository": REPOSITORY,
                "release_tag": RELEASE_TAG,
                "head_sha": HEAD_SHA,
                "workflow_run_url": RUN_URL,
                "run_attempt": 2,
                "captured_at_utc": CAPTURED_AT,
                "capture_kind": "native-connected-session",
                "synthetic": False,
                "fixture": False,
                "simulation": False,
            },
            "session": {
                "session_id": SESSION_ID,
                "transport_id": TRANSPORT_ID,
                "protocol": "ssh",
                "host_key_sha256": "7" * 64,
                "loopback": False,
            },
            "proofs": references,
        },
    )
    return evidence


def _mutate_proof_and_rebind(
    evidence: Path,
    root: Path,
    proof_name: str,
    changes: dict[str, Any],
) -> None:
    data = _read_json(evidence)
    proof_path = root / data["proofs"][proof_name]["file"]
    proof = _read_json(proof_path)
    proof.update(changes)
    _write_json(proof_path, proof)
    data["proofs"][proof_name]["sha256"] = _sha256(proof_path)
    _write_json(evidence, data)


def _read_json(path: Path) -> dict[str, Any]:
    value = json.loads(path.read_text(encoding="utf-8"))
    assert isinstance(value, dict)
    return value


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

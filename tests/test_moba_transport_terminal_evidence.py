from __future__ import annotations

import base64
import hashlib
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from scripts.check_moba_transport_terminal_evidence import (
    CAPTURE_ROLES,
    PROOF_SCHEMAS,
    SCHEMA,
    SSH_PHASES,
    SSH_VIEWS,
    validate_moba_transport_terminal_evidence,
)
from scripts.check_mobaxterm_parity_evidence import check_record
from scripts.finalize_mobaxterm_parity_evidence_record import finalize_candidate
from scripts.make_mobaxterm_parity_evidence_record import build_evidence_record

HEAD_SHA = "d" * 40
REPOSITORY = "example/remote-ops-workspace"
RELEASE_TAG = "v1.0.27"
RUN_URL = "https://github.com/example/remote-ops-workspace/actions/runs/1234"
CAPTURED_AT = "2026-08-23T12:34:56Z"
RELEASE_TARGET = "linux-x86_64"
SESSION_ID = "session-123"
TRANSPORT_ID = "transport-456"
HOST_KEY = "7" * 64
WHEEL = "remote_ops_workspace-1.0.27-py3-none-any.whl"
WHEEL_BYTES = b"test release wheel bytes\n"
ASSET = {"name": WHEEL, "sha256": hashlib.sha256(WHEEL_BYTES).hexdigest()}
SERVER_LOG = (
    "Connection from 192.168.40.2 port 54600 on 192.168.40.3 port 22 rdomain \"\"\n"
    "Accepted publickey for reviewer from 192.168.40.2 port 54600 ssh2: ED25519 SHA256:test\n"
    "Starting session: shell on pts/0 for reviewer from 192.168.40.2 port 54600 id 0\n"
    "Starting session: subsystem 'sftp' for reviewer from 192.168.40.2 port 54600 id 1\n"
    "Starting session: command for reviewer from 192.168.40.2 port 54600 id 1\n"
)


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
        "tested_release_asset": ASSET,
        "verified_capture_count": 12,
        "verified_ssh_channel_count": 3,
        "verified_screen_proof_count": 3,
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


@pytest.mark.parametrize("change", ["missing", "empty", "tampered", "reused", "traversal"])
def test_transport_terminal_requires_distinct_retained_capture_bytes(tmp_path: Path, change: str) -> None:
    evidence = _write_complete_evidence(tmp_path)
    data = _read_json(evidence)
    grid = _read_json(tmp_path / data["proofs"]["terminal_grid"]["file"])
    captures = grid["captures"]
    file = tmp_path / captures["updated_screen"]["file"]
    if change == "missing":
        file.unlink()
    elif change == "empty":
        file.write_bytes(b"")
        captures["updated_screen"]["sha256"] = _sha256(file)
    elif change == "tampered":
        file.write_bytes(b"changed screen")
    elif change == "reused":
        captures["updated_screen"] = captures["initial_screen"]
    else:
        captures["updated_screen"]["file"] = "../updated-screen.txt"
    _mutate_proof_and_rebind(evidence, tmp_path, "terminal_grid", {"captures": captures})

    result = validate_moba_transport_terminal_evidence(evidence, assets_dir=tmp_path)

    assert not result.passed
    assert any("proofs.terminal_grid.captures.updated_screen" in error for error in result.errors)


@pytest.mark.parametrize(
    ("old", "new"),
    [
        ("id 1\nStarting session: command", "id 1\nDiscarded session: command"),
        ("pts/0 for reviewer from 192.168.40.2 port 54600", "pts/0 for reviewer from 192.168.40.2 port 54601"),
        ("Starting session: shell", "Accepted publickey for reviewer from 192.168.40.2 port 54600 ssh2: again\n"
         "Starting session: shell"),
    ],
)
def test_transport_terminal_requires_three_channels_on_one_authenticated_socket(
    tmp_path: Path, old: str, new: str,
) -> None:
    evidence = _write_complete_evidence(tmp_path)
    data = _read_json(evidence)
    proof = _read_json(tmp_path / data["proofs"]["shared_transport"]["file"])
    capture = proof["captures"]["sshd_log"]
    file = tmp_path / capture["file"]
    assert old in SERVER_LOG
    file.write_text(SERVER_LOG.replace(old, new), encoding="utf-8")
    capture["sha256"] = _sha256(file)
    _mutate_proof_and_rebind(evidence, tmp_path, "shared_transport", {"captures": proof["captures"]})

    result = validate_moba_transport_terminal_evidence(evidence, assets_dir=tmp_path)

    assert not result.passed
    assert result.summary["verified_ssh_channel_count"] == 0
    assert any("SSH server must observe" in error for error in result.errors)


def test_transport_terminal_proof_rejects_release_asset_drift(tmp_path: Path) -> None:
    evidence = _write_complete_evidence(tmp_path)
    _mutate_proof_and_rebind(evidence, tmp_path, "connection_state", {"release_asset": {"name": WHEEL, "sha256": "a" * 64}})

    result = validate_moba_transport_terminal_evidence(evidence, assets_dir=tmp_path)

    assert not result.passed
    assert any("proofs.connection_state.release_asset" in error for error in result.errors)


@pytest.mark.parametrize(
    "asset_name",
    ["transport-capture.zip", "remote_ops_workspace-1.0.26-py3-none-any.whl", "remote-ops-workspace-v1.0.27-linux-arm64.deb"],
)
def test_transport_terminal_rejects_other_release_assets(tmp_path: Path, asset_name: str) -> None:
    evidence = _write_complete_evidence(tmp_path)
    data = _read_json(evidence)
    data["release_asset"]["name"] = asset_name
    _write_json(evidence, data)

    result = validate_moba_transport_terminal_evidence(evidence, assets_dir=tmp_path)

    assert not result.passed
    assert any("published desktop package for the exact tag and target" in error for error in result.errors)


@pytest.mark.parametrize("change", ["exit", "view", "retry"])
def test_transport_terminal_only_counts_observed_connection_transitions(tmp_path: Path, change: str) -> None:
    evidence = _write_complete_evidence(tmp_path)
    capture = tmp_path / "state_log.txt"
    log = _read_json(capture)
    if change == "exit":
        log["events"][4]["exit_code"] = 17
    elif change == "view":
        log["connected_views"]["sftp"]["phase"] = "authenticating"
    else:
        log["events"].pop()
    _write_json(capture, log)
    _mutate_proof_and_rebind(evidence, tmp_path, "connection_state", {
        "captures": {"state_log": {"file": capture.name, "sha256": _sha256(capture)}},
    })

    result = validate_moba_transport_terminal_evidence(evidence, assets_dir=tmp_path)

    assert not result.passed
    assert any("proofs.connection_state.captures.state_log" in error for error in result.errors)


@pytest.mark.parametrize(
    ("role", "replacement", "error"),
    [
        ("transcript", "not an SSH terminal observation", "same observed SSH socket"),
        ("sftp_capture", "different file", "SFTP bytes differ"),
        ("monitoring_capture", "cpu=bad processes=none", "observed CPU and process sample"),
    ],
)
def test_transport_terminal_cross_checks_connected_observations(
    tmp_path: Path, role: str, replacement: str, error: str,
) -> None:
    evidence = _write_complete_evidence(tmp_path)
    data = _read_json(evidence)
    proof = _read_json(tmp_path / data["proofs"]["connected_session"]["file"])
    capture = proof["captures"][role]
    file = tmp_path / capture["file"]
    file.write_text(replacement, encoding="utf-8")
    capture["sha256"] = _sha256(file)
    _mutate_proof_and_rebind(evidence, tmp_path, "connected_session", {"captures": proof["captures"]})

    result = validate_moba_transport_terminal_evidence(evidence, assets_dir=tmp_path)

    assert not result.passed
    assert any(error in detail for detail in result.errors)


@pytest.mark.parametrize(
    ("section", "role", "field", "value", "error"),
    [
        ("terminal_grid", "updated_screen", "geometry", [125, 18], "remote PTY resize"),
        ("terminal_grid", "updated_screen", "line", "unrelated", "combining cells across reflow"),
        ("terminal_grid", "updated_screen", "dirty_update", [0, 19, 19], "style-only Qt row update"),
        ("alternate_screen", "alternate_screen", "resized_text", "", "resized alternate screen"),
        ("alternate_screen", "alternate_screen", "insert_text", "", "Vim's insert-mode screen"),
        ("terminal_modes", "mode_capture", "remote", {}, "observed cursor, key, paste and mouse bytes"),
        ("terminal_modes", "mode_capture", "ssh_connection", "192.168.40.2 54601 192.168.40.3 22", "verified SSH socket"),
    ],
)
def test_transport_terminal_rejects_inconsistent_screen_observations(
    tmp_path: Path, section: str, role: str, field: str, value: Any, error: str,
) -> None:
    evidence = _write_complete_evidence(tmp_path)
    data = _read_json(evidence)
    proof = _read_json(tmp_path / data["proofs"][section]["file"])
    capture = proof["captures"][role]
    file = tmp_path / capture["file"]
    contents = _read_json(file)
    contents[field] = value
    _write_json(file, contents)
    capture["sha256"] = _sha256(file)
    _mutate_proof_and_rebind(evidence, tmp_path, section, {"captures": proof["captures"]})

    result = validate_moba_transport_terminal_evidence(evidence, assets_dir=tmp_path)

    assert not result.passed
    assert any(error in detail for detail in result.errors)
    assert result.summary["verified_screen_proof_count"] == 2


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
    artifact = tmp_path / WHEEL
    artifact.write_bytes(WHEEL_BYTES)

    errors, record = build_evidence_record(
        _generator_args(evidence, artifact, release_target="windows-arm64")
    )

    assert record == {}
    assert errors == [
        "shared-authenticated-transport-terminal-grid validated release_target "
        "'linux-x86_64' must match --release-target 'windows-arm64'"
    ]


def test_article_eight_generator_rejects_release_repository_drift(tmp_path: Path) -> None:
    evidence = _write_complete_evidence(tmp_path)
    artifact = tmp_path / WHEEL
    artifact.write_bytes(WHEEL_BYTES)
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


def test_article_eight_generator_rejects_mismatched_downloaded_release_bytes(tmp_path: Path) -> None:
    evidence = _write_complete_evidence(tmp_path)
    artifact = tmp_path / WHEEL
    artifact.write_bytes(b"different artifact bytes")

    errors, _ = build_evidence_record(_generator_args(evidence, artifact))

    assert any("tested release asset must match the record artifact name and SHA-256" in error for error in errors)


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
    artifact = tmp_path / WHEEL
    artifact.write_bytes(WHEEL_BYTES)
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
        release_tag="v1.0.27",
        release_target=release_target,
        evidence=evidence,
        assets_dir=evidence.parent,
        release_asset_url=[
            "https://github.com/example/remote-ops-workspace/releases/download/"
            f"{RELEASE_TAG}/{WHEEL}"
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
        "release_asset": ASSET,
        "host_key_sha256": HOST_KEY,
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
            "ssh_user": "reviewer",
            "client_endpoint": {"address": "192.168.40.2", "port": 54600},
            "server_endpoint": {"address": "192.168.40.3", "port": 22},
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
        },
    }
    references: dict[str, dict[str, str]] = {}
    host_fingerprint = base64.b64encode(bytes.fromhex(HOST_KEY)).decode("ascii").rstrip("=")
    states = [{"attempt": 1, "phase": phase} for phase in SSH_PHASES]
    states[3]["disconnect_reason"] = "remote-command-exited"
    states[4].update(disconnect_reason="remote-command-exited", exit_code=0, exit_status="NormalExit")
    states.extend({"attempt": 2, "phase": phase} for phase in SSH_PHASES[:3])
    sftp_payload = "remote bytes\n"
    sftp_digest = hashlib.sha256(sftp_payload.encode()).hexdigest()
    socket = "192.168.40.2 54600 192.168.40.3 22"
    grid_line = "a" * 110
    primary = json.dumps({"geometry": [145, 40], "text": "ROW_PRIMARY_界_e\u0301"})
    raw_captures = {
        "sshd_log": SERVER_LOG,
        "ssh_client_log": (
            f"debug1: Server host key: ssh-ed25519 SHA256:{host_fingerprint}\n"
            'Authenticated to peer ([192.168.40.3]:22) using "publickey".\n'
        ),
        "state_log": json.dumps({"events": states, "connected_views": dict.fromkeys(SSH_VIEWS, states[2])}),
        "transcript": f"ROW_SHARED_{socket}\nROW_SFTP_SHA256_{sftp_digest}\n",
        "sftp_capture": sftp_payload,
        "monitoring_capture": "cpu=8 processes=19\n",
        "initial_screen": json.dumps({
            "geometry": [120, 40], "line": grid_line + "\u2028界\u0301z", "cell_cursor": [1, 3],
        }),
        "updated_screen": json.dumps({
            "geometry": [145, 40], "line": grid_line + "界\u0301z", "ssh_connection": socket,
            "remote": {"initial": [120, 40], "resized": [145, 40], "cursor_reply": "1b5b323b3452"},
            "dirty_update": [18, 4, 4], "scroll_region": ["outside-top", "three", "four", "", "outside-bottom"],
        }),
        "primary_before": primary,
        "primary_restored": primary,
        "alternate_screen": json.dumps({
            "geometry": [145, 40], "resized": [125, 34], "ssh_connection": socket, "application": "vim",
            "text": "screen content\n~", "resized_text": "screen content\n~\n~", "insert_text": "-- INSERT --",
            "cursor_modes": ["bar", "block"], "remote": {"shell_input": "62"},
        }),
        "mode_capture": json.dumps({
            "ssh_connection": socket, "cursor_visibility": [False, True],
            "styles": [
                {"foreground": "#cd3131", "bold": True, "underline": True},
                {"foreground": "#ff0000"}, {"foreground": "#0c2238"},
            ],
            "remote": {
                "cursor_position": "1b5b373b3452",
                "cursor_shape_report": "1b503124723620711b5c",
                "application_up": "1b4f41",
                "bracketed_paste": "1b5b3230307e70617374652d66726f6d2d6465736b746f701b5b3230317e",
                "mouse_press_release_wheel": "1b5b3c303b313b314d1b5b3c303b313b316d1b5b3c36343b313b314d",
                "unwrapped_input_after_mouse_off": "78",
            },
        }),
    }
    for name, proof in proofs.items():
        proof["captures"] = {}
        for role in CAPTURE_ROLES[name]:
            capture = root / f"{role}.txt"
            capture.write_bytes(raw_captures.get(role, f"{role} test bytes\n").encode())
            proof["captures"][role] = {"file": capture.name, "sha256": _sha256(capture)}
        path = root / f"{name.replace('_', '-')}.json"
        _write_json(path, proof)
        references[name] = {"file": path.name, "sha256": _sha256(path)}
    evidence = root / "moba-transport-terminal-evidence.json"
    _write_json(
        evidence,
        {
            "schema": SCHEMA,
            "release_target": RELEASE_TARGET,
            "release_asset": ASSET,
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
                "host_key_sha256": HOST_KEY,
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

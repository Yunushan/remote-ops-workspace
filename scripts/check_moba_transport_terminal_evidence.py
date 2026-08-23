from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

SCHEMA = "row.moba-transport-terminal.release-evidence.v1"
SHA256_RE = re.compile(r"[0-9a-f]{64}")
GIT_SHA_RE = re.compile(r"[0-9a-f]{40}")
RUN_URL_RE = re.compile(
    r"https://github\.com/(?P<repository>[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+)/"
    r"actions/runs/[1-9]\d*"
)
REPOSITORY_RE = re.compile(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+")
RELEASE_TAG_RE = re.compile(r"v\d+\.\d+\.\d+")
UTC_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z")

PROOF_SCHEMAS = {
    "shared_transport": "row.moba-transport-terminal.shared-transport-proof.v1",
    "connection_state": "row.moba-transport-terminal.connection-state-proof.v1",
    "terminal_grid": "row.moba-transport-terminal.terminal-grid-proof.v1",
    "alternate_screen": "row.moba-transport-terminal.alternate-screen-proof.v1",
    "terminal_modes": "row.moba-transport-terminal.terminal-modes-proof.v1",
    "connected_session": "row.moba-transport-terminal.connected-session-proof.v1",
}


@dataclass(frozen=True)
class MobaTransportTerminalEvidenceValidation:
    evidence_path: str
    assets_dir: str
    passed: bool
    errors: list[str]
    warnings: list[str]
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=(
            "Verify strict MobaXterm shared authenticated transport and terminal-grid release evidence."
        )
    )
    parser.add_argument("--evidence", required=True, type=Path)
    parser.add_argument("--assets-dir", type=Path)
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)
    result = validate_moba_transport_terminal_evidence(args.evidence, assets_dir=args.assets_dir)
    if args.json:
        print(json.dumps(result.to_dict(), indent=2, sort_keys=True))
    elif result.passed:
        print("moba shared transport and terminal-grid evidence passed")
    else:
        for error in result.errors:
            print(f"moba transport terminal evidence: {error}", file=sys.stderr)
    return 0 if result.passed else 1


def validate_moba_transport_terminal_evidence(
    evidence_path: Path,
    *,
    assets_dir: Path | None = None,
) -> MobaTransportTerminalEvidenceValidation:
    target = Path(evidence_path)
    root = Path(assets_dir) if assets_dir is not None else target.parent
    errors: list[str] = []
    data = _read_json_file(target, "evidence", errors)
    summary: dict[str, Any] = {
        "schema": data.get("schema") if isinstance(data, dict) else "",
        "release_target": "",
        "session_id": "",
        "transport_id": "",
        "repository": "",
        "release_tag": "",
        "source_head_sha": "",
        "workflow_run_url": "",
        "run_attempt": 0,
        "proof_count": 0,
    }
    if not isinstance(data, dict):
        data = {}
    if data.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA}")
    release_target = _required_text(data, "release_target", errors)
    summary["release_target"] = release_target

    source = _required_mapping(data, "source", errors)
    repository = _required_text(source, "repository", errors, "source.")
    if repository and not REPOSITORY_RE.fullmatch(repository):
        errors.append("source.repository must be an exact GitHub owner/name value")
    release_tag = _required_text(source, "release_tag", errors, "source.")
    if release_tag and not RELEASE_TAG_RE.fullmatch(release_tag):
        errors.append("source.release_tag must look like vX.Y.Z")
    source_head_sha = _required_text(source, "head_sha", errors, "source.")
    if source_head_sha and not GIT_SHA_RE.fullmatch(source_head_sha):
        errors.append("source.head_sha must be a 40-character lowercase Git SHA")
    workflow_run_url = _required_text(source, "workflow_run_url", errors, "source.")
    run_url_match = RUN_URL_RE.fullmatch(workflow_run_url) if workflow_run_url else None
    if workflow_run_url and run_url_match is None:
        errors.append("source.workflow_run_url must be an exact GitHub Actions run URL")
    elif run_url_match is not None and repository and run_url_match.group("repository") != repository:
        errors.append("source.workflow_run_url repository must match source.repository")
    run_attempt = source.get("run_attempt")
    if not _positive_int(run_attempt):
        errors.append("source.run_attempt must be a positive integer")
    captured_at = source.get("captured_at_utc")
    if not _valid_utc(captured_at):
        errors.append("source.captured_at_utc must be an exact UTC RFC3339 timestamp")
    if source.get("capture_kind") != "native-connected-session":
        errors.append("source.capture_kind must be native-connected-session")
    for key in ("synthetic", "fixture", "simulation"):
        if source.get(key) is not False:
            errors.append(f"source.{key} must be false")
    summary.update(
        {
            "repository": repository,
            "release_tag": release_tag,
            "source_head_sha": source_head_sha,
            "workflow_run_url": workflow_run_url,
            "run_attempt": run_attempt if _positive_int(run_attempt) else 0,
        }
    )

    session = _required_mapping(data, "session", errors)
    session_id = _required_text(session, "session_id", errors, "session.")
    transport_id = _required_text(session, "transport_id", errors, "session.")
    summary["session_id"] = session_id
    summary["transport_id"] = transport_id
    if session.get("protocol") != "ssh":
        errors.append("session.protocol must be ssh")
    _required_sha(session.get("host_key_sha256"), "session.host_key_sha256", errors)
    if session.get("loopback") is not False:
        errors.append("session.loopback must be false for strict remote connected evidence")

    proofs = _required_mapping(data, "proofs", errors)
    missing = sorted(set(PROOF_SCHEMAS) - set(proofs))
    extra = sorted(set(proofs) - set(PROOF_SCHEMAS))
    if missing:
        errors.append(f"proofs missing required proof records: {missing}")
    if extra:
        errors.append(f"proofs contain unknown proof records: {extra}")
    loaded: dict[str, dict[str, Any]] = {}
    for proof_name, proof_schema in PROOF_SCHEMAS.items():
        reference = proofs.get(proof_name)
        proof = _load_proof(
            reference,
            root=root,
            label=f"proofs.{proof_name}",
            expected_schema=proof_schema,
            release_target=release_target,
            session_id=session_id,
            transport_id=transport_id,
            repository=repository,
            release_tag=release_tag,
            source_head_sha=source_head_sha,
            workflow_run_url=workflow_run_url,
            run_attempt=run_attempt,
            errors=errors,
        )
        if proof:
            loaded[proof_name] = proof
    summary["proof_count"] = len(loaded)
    if "shared_transport" in loaded:
        _check_shared_transport(loaded["shared_transport"], transport_id, errors)
    if "connection_state" in loaded:
        _check_connection_state(loaded["connection_state"], errors)
    if "terminal_grid" in loaded:
        _check_terminal_grid(loaded["terminal_grid"], errors)
    if "alternate_screen" in loaded:
        _check_alternate_screen(loaded["alternate_screen"], errors)
    if "terminal_modes" in loaded:
        _check_terminal_modes(loaded["terminal_modes"], errors)
    if "connected_session" in loaded:
        _check_connected_session(loaded["connected_session"], transport_id, errors)

    return MobaTransportTerminalEvidenceValidation(
        evidence_path=str(target),
        assets_dir=str(root),
        passed=not errors,
        errors=errors,
        warnings=[],
        summary=summary,
    )


def _load_proof(
    reference: Any,
    *,
    root: Path,
    label: str,
    expected_schema: str,
    release_target: str,
    session_id: str,
    transport_id: str,
    repository: str,
    release_tag: str,
    source_head_sha: str,
    workflow_run_url: str,
    run_attempt: Any,
    errors: list[str],
) -> dict[str, Any]:
    if not isinstance(reference, dict):
        errors.append(f"{label} must be an object")
        return {}
    relative = _required_text(reference, "file", errors, f"{label}.")
    expected_hash = reference.get("sha256")
    _required_sha(expected_hash, f"{label}.sha256", errors)
    if not relative or not isinstance(expected_hash, str) or not SHA256_RE.fullmatch(expected_hash):
        return {}
    path = _resolve_asset(root, relative, label, errors)
    if path is None:
        return {}
    actual_hash = _sha256_file(path)
    if actual_hash != expected_hash:
        errors.append(f"{label}.sha256 does not match {relative}")
        return {}
    proof = _read_json_file(path, label, errors)
    if not isinstance(proof, dict):
        return {}
    if proof.get("schema") != expected_schema:
        errors.append(f"{label} schema must be {expected_schema}")
    expected = {
        "release_target": release_target,
        "session_id": session_id,
        "transport_id": transport_id,
        "repository": repository,
        "release_tag": release_tag,
        "source_head_sha": source_head_sha,
        "workflow_run_url": workflow_run_url,
        "run_attempt": run_attempt,
    }
    for key, value in expected.items():
        if proof.get(key) != value:
            errors.append(f"{label}.{key} must match the top-level evidence identity")
    if not _valid_utc(proof.get("captured_at_utc")):
        errors.append(f"{label}.captured_at_utc must be an exact UTC RFC3339 timestamp")
    return proof


def _check_shared_transport(proof: dict[str, Any], transport_id: str, errors: list[str]) -> None:
    label = "proofs.shared_transport"
    if proof.get("transport_mode") not in {
        "shared-authenticated-transport",
        "controlled-multiplexing",
    }:
        errors.append(f"{label}.transport_mode must prove shared transport or controlled multiplexing")
    for key in (
        "authenticated_transport_established",
        "terminal_channel_opened",
        "sftp_channel_opened",
        "monitoring_channel_opened",
        "credential_reuse_without_reprompt",
    ):
        _require_true(proof, key, label, errors)
    if proof.get("authentication_event_count") != 1:
        errors.append(f"{label}.authentication_event_count must be 1")
    if proof.get("credential_reprompt_count") != 0:
        errors.append(f"{label}.credential_reprompt_count must be 0")
    for key in (
        "terminal_channel_transport_id",
        "sftp_channel_transport_id",
        "monitoring_channel_transport_id",
    ):
        if proof.get(key) != transport_id:
            errors.append(f"{label}.{key} must match the authenticated transport id")


def _check_connection_state(proof: dict[str, Any], errors: list[str]) -> None:
    label = "proofs.connection_state"
    expected = ["connecting", "authenticating", "connected", "closing", "closed"]
    if proof.get("transition_sequence") != expected:
        errors.append(f"{label}.transition_sequence must be {expected}")
    for key in (
        "disconnect_reason_recorded",
        "terminal_exit_status_recorded",
        "reconnect_transition_recorded",
        "state_visible_to_terminal_sftp_monitoring",
    ):
        _require_true(proof, key, label, errors)
    exit_status = proof.get("terminal_exit_status")
    if not isinstance(exit_status, int) or isinstance(exit_status, bool):
        errors.append(f"{label}.terminal_exit_status must be an integer")


def _check_terminal_grid(proof: dict[str, Any], errors: list[str]) -> None:
    label = "proofs.terminal_grid"
    rows = proof.get("rows")
    columns = proof.get("columns")
    if not isinstance(rows, int) or isinstance(rows, bool) or rows < 24:
        errors.append(f"{label}.rows must be an integer of at least 24")
    if not isinstance(columns, int) or isinstance(columns, bool) or columns < 80:
        errors.append(f"{label}.columns must be an integer of at least 80")
    for key in (
        "real_cell_grid",
        "cursor_addressing",
        "scroll_regions",
        "dirty_region_updates",
        "wide_character_width",
        "combining_character_support",
        "resize_reflow_stable",
        "no_transcript_fallback",
    ):
        _require_true(proof, key, label, errors)
    _required_sha(proof.get("initial_screen_sha256"), f"{label}.initial_screen_sha256", errors)
    _required_sha(proof.get("updated_screen_sha256"), f"{label}.updated_screen_sha256", errors)


def _check_alternate_screen(proof: dict[str, Any], errors: list[str]) -> None:
    label = "proofs.alternate_screen"
    for key in (
        "entered",
        "full_screen_application_rendered",
        "cursor_addressing_stable",
        "resize_stable",
        "exited",
        "primary_screen_restored",
        "shell_input_resumed",
    ):
        _require_true(proof, key, label, errors)
    if proof.get("application") not in {"vim", "htop", "less", "tmux"}:
        errors.append(f"{label}.application must identify a real full-screen terminal application")
    before = proof.get("primary_before_sha256")
    alternate = proof.get("alternate_screen_sha256")
    restored = proof.get("primary_restored_sha256")
    for key, value in (
        ("primary_before_sha256", before),
        ("alternate_screen_sha256", alternate),
        ("primary_restored_sha256", restored),
    ):
        _required_sha(value, f"{label}.{key}", errors)
    if isinstance(before, str) and isinstance(restored, str) and before != restored:
        errors.append(f"{label}.primary_restored_sha256 must match primary_before_sha256")
    if isinstance(before, str) and isinstance(alternate, str) and before == alternate:
        errors.append(f"{label}.alternate_screen_sha256 must differ from the primary screen")


def _check_terminal_modes(proof: dict[str, Any], errors: list[str]) -> None:
    label = "proofs.terminal_modes"
    for key in (
        "cursor_position",
        "cursor_visibility",
        "cursor_shape",
        "sgr_attributes",
        "ansi_16_colors",
        "indexed_256_colors",
        "truecolor",
        "application_cursor_keys",
        "bracketed_paste",
        "sgr_mouse_reporting",
        "mouse_enable_disable",
        "mouse_press_release_wheel",
    ):
        _require_true(proof, key, label, errors)
    _required_sha(proof.get("mode_capture_sha256"), f"{label}.mode_capture_sha256", errors)


def _check_connected_session(proof: dict[str, Any], transport_id: str, errors: list[str]) -> None:
    label = "proofs.connected_session"
    for key in (
        "real_connected_session",
        "native_host",
        "remote_host_observed",
        "terminal_input_output_round_trip",
        "sftp_round_trip",
        "monitoring_sample_observed",
        "same_authenticated_transport_observed",
    ):
        _require_true(proof, key, label, errors)
    for key in ("fixture", "simulation", "placeholder"):
        if proof.get(key) is not False:
            errors.append(f"{label}.{key} must be false")
    if proof.get("observed_transport_id") != transport_id:
        errors.append(f"{label}.observed_transport_id must match the authenticated transport id")
    duration = proof.get("session_duration_seconds")
    if not isinstance(duration, (int, float)) or isinstance(duration, bool) or duration <= 0:
        errors.append(f"{label}.session_duration_seconds must be positive")
    _required_sha(proof.get("transcript_sha256"), f"{label}.transcript_sha256", errors)


def _require_true(data: dict[str, Any], key: str, prefix: str, errors: list[str]) -> None:
    if data.get(key) is not True:
        errors.append(f"{prefix}.{key} must be true")


def _required_mapping(data: dict[str, Any], key: str, errors: list[str]) -> dict[str, Any]:
    value = data.get(key)
    if isinstance(value, dict):
        return value
    errors.append(f"{key} must be a JSON object")
    return {}


def _required_text(data: dict[str, Any], key: str, errors: list[str], prefix: str = "") -> str:
    value = data.get(key)
    if isinstance(value, str) and value and value == value.strip():
        return value
    errors.append(f"{prefix}{key} must be a non-empty unpadded string")
    return ""


def _required_sha(value: Any, label: str, errors: list[str]) -> None:
    if not isinstance(value, str) or not SHA256_RE.fullmatch(value):
        errors.append(f"{label} must be a lowercase 64-character SHA-256 digest")


def _positive_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value > 0


def _valid_utc(value: Any) -> bool:
    if not isinstance(value, str) or not UTC_RE.fullmatch(value):
        return False
    try:
        dt.datetime.strptime(value, "%Y-%m-%dT%H:%M:%SZ")
    except ValueError:
        return False
    return True


def _resolve_asset(root: Path, relative: str, label: str, errors: list[str]) -> Path | None:
    path = Path(relative)
    if path.is_absolute() or ".." in path.parts:
        errors.append(f"{label}.file must stay inside assets_dir")
        return None
    try:
        resolved_root = root.resolve(strict=True)
    except OSError as exc:
        errors.append(f"assets_dir cannot be resolved: {exc}")
        return None
    candidate = root / path
    try:
        resolved = candidate.resolve(strict=True)
    except OSError as exc:
        errors.append(f"{label}.file cannot be resolved: {exc}")
        return None
    if resolved_root != resolved and resolved_root not in resolved.parents:
        errors.append(f"{label}.file must stay inside assets_dir")
        return None
    current = candidate
    while current != root.parent:
        if current.is_symlink():
            errors.append(f"{label}.file must not traverse symlinks")
            return None
        if current == root:
            break
        current = current.parent
    if not resolved.is_file():
        errors.append(f"{label}.file must be a regular file")
        return None
    return resolved


def _read_json_file(path: Path, label: str, errors: list[str]) -> dict[str, Any]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        errors.append(f"{label} file cannot be read: {exc}")
        return {}
    except json.JSONDecodeError as exc:
        errors.append(f"{label} file is not valid JSON: {exc}")
        return {}
    if not isinstance(data, dict):
        errors.append(f"{label} root must be a JSON object")
        return {}
    return data


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


if __name__ == "__main__":
    raise SystemExit(main())

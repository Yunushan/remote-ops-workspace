from __future__ import annotations

import argparse
import base64
import datetime as dt
import hashlib
import ipaddress
import json
import math
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from scripts.check_release_license_compliance import secure_regular_file  # noqa: E402

SCHEMA = "row.moba-transport-terminal.release-evidence.v2"
MAX_CAPTURE_BYTES = 8 * 1024 * 1024
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
    "shared_transport": "row.moba-transport-terminal.shared-transport-proof.v2",
    "connection_state": "row.moba-transport-terminal.connection-state-proof.v2",
    "terminal_grid": "row.moba-transport-terminal.terminal-grid-proof.v2",
    "alternate_screen": "row.moba-transport-terminal.alternate-screen-proof.v2",
    "terminal_modes": "row.moba-transport-terminal.terminal-modes-proof.v2",
    "connected_session": "row.moba-transport-terminal.connected-session-proof.v2",
}

CAPTURE_ROLES = {
    "shared_transport": ("sshd_log", "ssh_client_log"),
    "connection_state": ("state_log",),
    "terminal_grid": ("initial_screen", "updated_screen"),
    "alternate_screen": ("primary_before", "alternate_screen", "primary_restored"),
    "terminal_modes": ("mode_capture",),
    "connected_session": ("transcript", "sftp_capture", "monitoring_capture"),
}
LINUX_PACKAGES = {
    "linux-x86_64": ("amd64", "x86_64"),
    "linux-arm64": ("arm64", "aarch64"),
    "linux-i386": ("i386", "i686"),
    "linux-armhf": ("armhf", "armhf"),
}
MACOS_TARGETS = {"macos-x64", "macos-arm64"}
SERVER_CONNECT = re.compile(r"^Connection from (\S+) port (\d+) on (\S+) port (\d+)(?: .*)?$")
SERVER_AUTH = re.compile(r"^Accepted publickey for (\S+) from (\S+) port (\d+) ssh2: .+$")
SERVER_SESSION = re.compile(
    r"^Starting session: (shell on pts/\d+|subsystem 'sftp'|command) for (\S+) from (\S+) port (\d+) id (\d+)$"
)
CLIENT_HOST_KEY = re.compile(r"^debug1: Server host key: \S+ SHA256:([A-Za-z0-9+/]{43})$")
CLIENT_AUTH = re.compile(r'^Authenticated to \S+ \(\[([^\]]+)\]:(\d+)\) using "publickey"\.$')
TERMINAL_SOCKET = re.compile(r"^ROW_SHARED_(\S+) (\d+) (\S+) (\d+)[ \t]*$", re.MULTILINE)
TERMINAL_SFTP_SHA = re.compile(r"^ROW_SFTP_SHA256_([0-9a-f]{64})[ \t]*$", re.MULTILINE)
SSH_PHASES = ["connecting", "authenticating", "connected", "closing", "closed"]
SSH_VIEWS = ("terminal", "sftp", "monitoring")


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
        "verified_capture_count": 0,
        "verified_ssh_channel_count": 0,
    }
    if not isinstance(data, dict):
        data = {}
    if data.get("schema") != SCHEMA:
        errors.append(f"schema must be {SCHEMA}")
    release_target = _required_text(data, "release_target", errors)
    summary["release_target"] = release_target
    asset = _required_mapping(data, "release_asset", errors)
    name = _required_text(asset, "name", errors, "release_asset.")
    digest = asset.get("sha256")
    _required_sha(digest, "release_asset.sha256", errors)
    tested_asset = {"name": name, "sha256": digest}
    summary["tested_release_asset"] = tested_asset

    source = _required_mapping(data, "source", errors)
    repository = _required_text(source, "repository", errors, "source.")
    if repository and not REPOSITORY_RE.fullmatch(repository):
        errors.append("source.repository must be an exact GitHub owner/name value")
    release_tag = _required_text(source, "release_tag", errors, "source.")
    if release_tag and not RELEASE_TAG_RE.fullmatch(release_tag):
        errors.append("source.release_tag must look like vX.Y.Z")
    if not _desktop_package(name, release_tag, release_target):
        errors.append("release_asset.name must identify a published desktop package for the exact tag and target")
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
    host_key = session.get("host_key_sha256")
    _required_sha(host_key, "session.host_key_sha256", errors)
    if session.get("loopback") is not False:
        errors.append("session.loopback must be false for strict remote connected evidence")

    proofs = _required_mapping(data, "proofs", errors)
    missing = sorted(set(PROOF_SCHEMAS) - set(proofs))
    extra = sorted(set(proofs) - set(PROOF_SCHEMAS))
    if missing:
        errors.append(f"proofs missing required proof records: {missing}")
    if extra:
        errors.append(f"proofs contain unknown proof records: {extra}")
    identity = {
        "release_target": release_target,
        "session_id": session_id,
        "transport_id": transport_id,
        "repository": repository,
        "release_tag": release_tag,
        "source_head_sha": source_head_sha,
        "workflow_run_url": workflow_run_url,
        "run_attempt": run_attempt,
        "release_asset": tested_asset,
        "host_key_sha256": host_key,
    }
    loaded: dict[str, dict[str, Any]] = {}
    capture_paths: set[Path] = set()
    for proof_name, proof_schema in PROOF_SCHEMAS.items():
        reference = proofs.get(proof_name)
        proof = _load_proof(
            reference,
            root=root,
            label=f"proofs.{proof_name}",
            expected_schema=proof_schema,
            identity=identity,
            errors=errors,
        )
        if proof:
            loaded[proof_name] = proof
            captures = _load_captures(root, proof_name, proof, capture_paths, errors)
            if proof_name == "shared_transport" and len(captures) == len(CAPTURE_ROLES[proof_name]):
                observed = verify_ssh_channels(proof, captures, host_key, errors)
                summary["verified_ssh_channel_count"] = observed
            if proof_name == "connection_state" and "state_log" in captures:
                verify_connection_states(captures["state_log"], proof.get("terminal_exit_status"), errors)
            if proof_name == "connected_session" and len(captures) == len(CAPTURE_ROLES[proof_name]):
                verify_connected_captures(captures, loaded.get("shared_transport", {}), errors)
    summary["proof_count"] = len(loaded)
    summary["verified_capture_count"] = len(capture_paths)
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


def _desktop_package(name: str, tag: str, target: str) -> bool:
    if not RELEASE_TAG_RE.fullmatch(tag):
        return False
    wheel = f"remote_ops_workspace-{tag[1:]}-py3-none-any.whl"
    if target in MACOS_TARGETS:
        native = f"remote-ops-workspace-{tag}-{target}"
        return name in {wheel, f"{native}.dmg", f"{native}.pkg"}
    if target not in LINUX_PACKAGES:
        return False
    debian, linux = LINUX_PACKAGES[target]
    prefix = f"remote-ops-workspace-{tag}-linux-"
    return name in {wheel, f"{prefix}{debian}.deb", f"{prefix}{linux}.AppImage", f"{prefix}{linux}-native.tar.gz"}


def _load_proof(
    reference: Any,
    *,
    root: Path,
    label: str,
    expected_schema: str,
    identity: dict[str, Any],
    errors: list[str],
) -> dict[str, Any]:
    if not isinstance(reference, dict):
        errors.append(f"{label} must be an object")
        return {}
    path, raw = _read_bound_file(root, reference, label, errors)
    if path is None:
        return {}
    proof = _decode_object(raw, label, errors)
    if proof.get("schema") != expected_schema:
        errors.append(f"{label} schema must be {expected_schema}")
    for key, value in identity.items():
        if proof.get(key) != value or type(proof.get(key)) is not type(value):
            errors.append(f"{label}.{key} must match the top-level evidence identity")
    if not _valid_utc(proof.get("captured_at_utc")):
        errors.append(f"{label}.captured_at_utc must be an exact UTC RFC3339 timestamp")
    return proof


def _load_captures(
    root: Path, proof_name: str, proof: dict[str, Any], used: set[Path], errors: list[str],
) -> dict[str, bytes]:
    label = f"proofs.{proof_name}.captures"
    attachments = proof.get("captures")
    required = CAPTURE_ROLES[proof_name]
    if not isinstance(attachments, dict) or set(attachments) != set(required):
        errors.append(f"{label} must contain exactly {list(required)}")
        return {}
    loaded = {}
    for role in required:
        reference = attachments[role]
        role_label = f"{label}.{role}"
        if not isinstance(reference, dict):
            errors.append(f"{role_label} must be an object")
            continue
        path, raw = _read_bound_file(root, reference, role_label, errors)
        if path is None:
            continue
        if path in used:
            errors.append(f"{role_label} reuses another capture path")
            continue
        used.add(path)
        loaded[role] = raw
    return loaded


def _read_bound_file(
    root: Path, reference: dict[str, Any], label: str, errors: list[str],
) -> tuple[Path | None, bytes]:
    relative = reference.get("file")
    expected_hash = reference.get("sha256")
    if not isinstance(expected_hash, str) or not SHA256_RE.fullmatch(expected_hash):
        _required_sha(expected_hash, f"{label}.sha256", errors)
        return None, b""
    path, error = secure_regular_file(root, relative, label)
    if path is None:
        errors.append(error or f"{label} evidence file is missing")
        return None, b""
    raw = _read_capture_bytes(path, label, errors)
    if not raw:
        return None, b""
    if hashlib.sha256(raw).hexdigest() != expected_hash:
        errors.append(f"{label}.sha256 does not match {relative}")
        return None, b""
    return path, raw


def verify_ssh_channels(
    proof: dict[str, Any], captures: dict[str, bytes], host_key: Any, errors: list[str],
) -> int:
    label = "proofs.shared_transport"
    try:
        client_log = captures["ssh_client_log"].decode("utf-8").splitlines()
        server_log = captures["sshd_log"].decode("utf-8").splitlines()
        user = proof["ssh_user"]
        peer, endpoint = proof["client_endpoint"], proof["server_endpoint"]
        if not isinstance(user, str) or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]{0,63}", user):
            raise ValueError("a valid SSH login is required")
        client_ip, client_port = _endpoint(peer)
        server_ip, server_port = _endpoint(endpoint)
        if client_ip == server_ip:
            raise ValueError("client and server must have different addresses")
    except (KeyError, UnicodeError, ValueError) as exc:
        errors.append(f"{label} cannot identify a remote SSH connection: {exc}")
        return 0
    fingerprints = {
        base64.b64decode(match[1] + "=").hex()
        for line in client_log if (match := CLIENT_HOST_KEY.fullmatch(line))
    }
    if not isinstance(host_key, str) or fingerprints != {host_key}:
        errors.append(f"{label} SSH client host key does not match the session")
        return 0
    client_auth = [match.groups() for line in client_log if (match := CLIENT_AUTH.fullmatch(line))]
    if client_auth != [(server_ip, server_port)]:
        errors.append(f"{label} SSH client must authenticate by public key to the observed server socket")
        return 0
    connection = (client_ip, client_port, server_ip, server_port)
    login = (user, client_ip, client_port)
    connected_at = [index for index, line in enumerate(server_log)
                    if (match := SERVER_CONNECT.fullmatch(line)) and match.groups() == connection]
    authenticated_at = [index for index, line in enumerate(server_log)
                        if (match := SERVER_AUTH.fullmatch(line)) and match.groups() == login]
    if len(connected_at) != 1 or len(authenticated_at) != 1 or connected_at[0] >= authenticated_at[0]:
        errors.append(f"{label} SSH server must observe one connection and one authentication on the same socket")
        return 0
    channels = {
        match[1].split()[0]
        for line in server_log[authenticated_at[0] + 1:]
        if (match := SERVER_SESSION.fullmatch(line)) and match.groups()[1:4] == login
    }
    if channels != {"shell", "subsystem", "command"}:
        errors.append(f"{label} SSH server must observe a PTY, SFTP and command channels on the authenticated socket")
        return 0
    return 3


def verify_connection_states(raw: bytes, exit_code: Any, errors: list[str]) -> None:
    label = "proofs.connection_state.captures.state_log"
    state_log = _decode_object(raw, label, errors)
    events, views = state_log.get("events"), state_log.get("connected_views")
    expected = [(1, phase) for phase in SSH_PHASES] + [(2, phase) for phase in SSH_PHASES[:3]]
    if (
        not isinstance(events, list) or len(events) != len(expected)
        or any(
            not isinstance(row, dict) or type(row.get("attempt")) is not int
            or (row["attempt"], row.get("phase")) != identity
            for row, identity in zip(events, expected, strict=True)
        )
    ):
        errors.append(f"{label} must record connect, authenticate, close and reconnect in order")
        return
    _, _, connected, closing, closed, *_ = events
    reason = closed.get("disconnect_reason")
    if (
        not isinstance(reason, str) or not reason.strip() or reason != closing.get("disconnect_reason")
        or type(closed.get("exit_code")) is not int or closed["exit_code"] != exit_code
        or closed.get("exit_status") != "NormalExit"
    ):
        errors.append(f"{label} must record the disconnect reason and terminal exit status")
    if (
        not isinstance(views, dict) or set(views) != set(SSH_VIEWS)
        or any(state != connected for state in views.values())
    ):
        errors.append(f"{label} must show the same authenticated state on terminal, SFTP and monitoring")


def _endpoint(value: Any) -> tuple[str, str]:
    if not isinstance(value, dict) or type(value.get("port")) is not int or not 0 < value["port"] < 65536:
        raise ValueError("an SSH endpoint must have an address and TCP port")
    if not isinstance(address := value.get("address"), str):
        raise ValueError("an SSH endpoint must have an IP address")
    ip = ipaddress.ip_address(address)
    if ip.is_loopback or ip.is_unspecified or ip.is_multicast or ip.is_link_local:
        raise ValueError("an SSH endpoint must be a non-loopback unicast address")
    return address, str(value["port"])


def verify_connected_captures(
    captures: dict[str, bytes], transport: dict[str, Any], errors: list[str],
) -> None:
    from remote_ops_workspace.moba_connected import parse_remote_monitoring_output

    label = "proofs.connected_session.captures"
    try:
        transcript = captures["transcript"].decode("utf-8")
        client = _endpoint(transport.get("client_endpoint"))
        server = _endpoint(transport.get("server_endpoint"))
        monitoring = parse_remote_monitoring_output(captures["monitoring_capture"].decode("utf-8"))
    except (UnicodeError, ValueError) as exc:
        errors.append(f"{label} cannot read the terminal or monitoring observations: {exc}")
        return
    if TERMINAL_SOCKET.findall(transcript) != [(*client, *server)]:
        errors.append(f"{label} terminal did not report the same observed SSH socket")
    if TERMINAL_SFTP_SHA.findall(transcript) != [hashlib.sha256(captures["sftp_capture"]).hexdigest()]:
        errors.append(f"{label} SFTP bytes differ from the independent digest observed in the terminal")
    if monitoring is None or monitoring.cpu_percent is None or monitoring.process_count is None:
        errors.append(f"{label} monitoring capture does not contain an observed CPU and process sample")


def _check_shared_transport(proof: dict[str, Any], transport_id: str, errors: list[str]) -> None:
    label = "proofs.shared_transport"
    if proof.get("transport_mode") not in (
        "shared-authenticated-transport",
        "controlled-multiplexing",
    ):
        errors.append(f"{label}.transport_mode must prove shared transport or controlled multiplexing")
    for key in (
        "authenticated_transport_established",
        "terminal_channel_opened",
        "sftp_channel_opened",
        "monitoring_channel_opened",
        "credential_reuse_without_reprompt",
    ):
        _require_true(proof, key, label, errors)
    if type(proof.get("authentication_event_count")) is not int or proof["authentication_event_count"] != 1:
        errors.append(f"{label}.authentication_event_count must be 1")
    if type(proof.get("credential_reprompt_count")) is not int or proof["credential_reprompt_count"] != 0:
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
    if proof.get("transition_sequence") != SSH_PHASES:
        errors.append(f"{label}.transition_sequence must be {SSH_PHASES}")
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
    initial = _capture_digest(proof, "initial_screen")
    updated = _capture_digest(proof, "updated_screen")
    if initial is not None and updated is not None and initial == updated:
        errors.append(f"{label} initial and updated captures must differ")


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
    if proof.get("application") not in ("vim", "htop", "less", "tmux"):
        errors.append(f"{label}.application must identify a real full-screen terminal application")
    before = _capture_digest(proof, "primary_before")
    alternate = _capture_digest(proof, "alternate_screen")
    restored = _capture_digest(proof, "primary_restored")
    if before is not None and restored is not None and before != restored:
        errors.append(f"{label} primary restored capture must match the primary before capture")
    if before is not None and alternate is not None and before == alternate:
        errors.append(f"{label} alternate screen capture must differ from the primary screen")


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
    if type(duration) not in {int, float} or not 0 < duration or (isinstance(duration, float) and not math.isfinite(duration)):
        errors.append(f"{label}.session_duration_seconds must be positive")


def _capture_digest(proof: dict[str, Any], role: str) -> str | None:
    captures = proof.get("captures")
    entry = captures.get(role) if isinstance(captures, dict) else None
    digest = entry.get("sha256") if isinstance(entry, dict) else None
    return digest if isinstance(digest, str) else None


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


def _read_json_file(path: Path, label: str, errors: list[str]) -> dict[str, Any]:
    raw = _read_capture_bytes(path, label, errors)
    return _decode_object(raw, label, errors) if raw else {}


def _read_capture_bytes(path: Path, label: str, errors: list[str]) -> bytes:
    try:
        with path.open("rb") as stream:
            raw = stream.read(MAX_CAPTURE_BYTES + 1)
    except OSError as exc:
        errors.append(f"{label} file cannot be read: {exc}")
        return b""
    if not 0 < len(raw) <= MAX_CAPTURE_BYTES:
        errors.append(f"{label} file must contain between 1 byte and 8 MiB")
        return b""
    return raw


def _decode_object(raw: bytes, label: str, errors: list[str]) -> dict[str, Any]:
    try:
        data = json.loads(raw.decode("utf-8"))
    except (UnicodeError, ValueError, RecursionError) as exc:
        errors.append(f"{label} file is not valid JSON: {exc}")
        return {}
    if not isinstance(data, dict):
        errors.append(f"{label} root must be a JSON object")
        return {}
    return data


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT / "src"))
    raise SystemExit(main())

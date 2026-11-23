"""Produce review evidence from an approved native runner and dedicated SSH peer."""

from __future__ import annotations

import argparse
import datetime as dt
import ipaddress
import json
import os
import re
import shutil
import stat
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory
from uuid import uuid4

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.capture_moba_shared_ssh_channels import (  # noqa: E402
    SCREEN_FILES,
    TransportPeer,
    capture_session,
)
from scripts.check_moba_transport_terminal_evidence import (  # noqa: E402
    CAPTURE_ROLES,
    PROOF_SCHEMAS,
    SCHEMA,
    SSH_PHASES,
    validate_moba_transport_terminal_evidence,
)
from scripts.debian_release_fixture import actions_source  # noqa: E402
from scripts.qt_release_capture import TARGET, sha256, verify_wheel, write_json  # noqa: E402

CAPTURE_FILES = {
    "shared_transport": {"sshd_log": "sshd.log", "ssh_client_log": "ssh-client.log"},
    "connection_state": {"state_log": "connection-state.json"},
    **SCREEN_FILES,
    "connected_session": {
        "transcript": "terminal.txt", "sftp_capture": "sftp.txt", "monitoring_capture": "monitoring.txt",
    },
}
PRIVATE_NETS = tuple(map(ipaddress.ip_network, ("10.0.0.0/8", "172.16.0.0/12", "192.168.0.0/16", "fc00::/7")))


def require_native_runner() -> None:
    if (
        os.environ.get("GITHUB_ACTIONS") != "true" or os.environ.get("RUNNER_ENVIRONMENT") != "self-hosted"
        or sys.platform != "linux" or os.uname().machine != "x86_64" or os.geteuid() == 0
        or any(Path(path).exists() for path in ("/.dockerenv", "/run/.containerenv"))
    ):
        raise ValueError("release capture requires an unprivileged native Linux x86_64 self-hosted runner")
    detector = shutil.which("systemd-detect-virt")
    if detector is None or subprocess.run([detector, "--container", "--quiet"], check=False, timeout=5).returncode != 1:
        raise ValueError("release capture cannot establish that the runner is outside a container")


def administrator_file(path: Path, *, private_key: bool = False) -> Path:
    if not path.is_absolute() or ".." in path.parts:
        raise ValueError("the native peer configuration requires absolute administrator paths")
    for parent in path.parents:
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022:
            raise ValueError(f"the peer file has an untrusted parent: {path.name}")
    info = path.lstat()
    owner = os.geteuid() if private_key else 0
    forbidden_bits = 0o077 if private_key else 0o022
    if not stat.S_ISREG(info.st_mode) or info.st_uid != owner or info.st_mode & forbidden_bits:
        raise ValueError(f"the native peer file is untrusted: {path.name}")
    return path


def load_peer(configuration: Path) -> TransportPeer:
    config = administrator_file(configuration)
    with config.open("rb") as stream:
        raw = stream.read(4097)
    if len(raw) > 4096:
        raise ValueError("the native peer configuration exceeds 4 KiB")
    data = json.loads(raw)
    if not isinstance(data, dict) or set(data) != {"address", "port", "user"}:
        raise ValueError("the native peer configuration requires address, port and user")
    host, port, user = data["address"], data["port"], data["user"]
    if not isinstance(host, str) or "%" in host:
        raise ValueError("the native SSH peer requires a literal private IP address")
    ip = ipaddress.ip_address(host)
    if str(ip) != host or not any(ip in network for network in PRIVATE_NETS):
        raise ValueError("the native SSH peer requires a canonical private IP address")
    if type(port) is not int or not 0 < port < 65536:
        raise ValueError("the native SSH peer requires a valid TCP port")
    if not isinstance(user, str) or user == "root" or not re.fullmatch(r"[a-z_][a-z0-9_-]{0,31}", user):
        raise ValueError("the native SSH peer requires a dedicated unprivileged account")
    return TransportPeer(
        host, port, user, administrator_file(config.parent / "identity", private_key=True),
        administrator_file(config.parent / "known_hosts"), administrator_file(config.parent / "sshd.log"),
    )


def native_proof_values(report: dict, transport: str) -> dict:
    columns, rows = report["grid"]["initial"]
    return {
        "shared_transport": {
            "transport_mode": "controlled-multiplexing",
            "authentication_event_count": 1, "credential_reprompt_count": 0,
            "terminal_channel_transport_id": transport, "sftp_channel_transport_id": transport,
            "monitoring_channel_transport_id": transport,
            **{field: report[field] for field in ("ssh_user", "client_endpoint", "server_endpoint")},
            **dict.fromkeys((
                "authenticated_transport_established", "terminal_channel_opened", "sftp_channel_opened",
                "monitoring_channel_opened", "credential_reuse_without_reprompt",
            ), True),
        },
        "connection_state": {
            "transition_sequence": SSH_PHASES, "terminal_exit_status": 0,
            **dict.fromkeys((
                "disconnect_reason_recorded", "terminal_exit_status_recorded", "reconnect_transition_recorded",
                "state_visible_to_terminal_sftp_monitoring",
            ), True),
        },
        "terminal_grid": {
            "columns": columns, "rows": rows,
            **dict.fromkeys((
                "real_cell_grid", "cursor_addressing", "scroll_regions", "dirty_region_updates", "wide_character_width",
                "combining_character_support", "resize_reflow_stable", "no_transcript_fallback",
            ), True),
        },
        "alternate_screen": {
            "application": report["alternate_screen"]["application"],
            **dict.fromkeys((
                "entered", "full_screen_application_rendered", "cursor_addressing_stable", "resize_stable",
                "exited", "primary_screen_restored", "shell_input_resumed",
            ), True),
        },
        "terminal_modes": dict.fromkeys((
            "cursor_position", "cursor_visibility", "cursor_shape", "sgr_attributes", "ansi_16_colors",
            "indexed_256_colors", "truecolor", "application_cursor_keys", "bracketed_paste", "sgr_mouse_reporting",
            "mouse_enable_disable", "mouse_press_release_wheel",
        ), True),
        "connected_session": {
            "observed_transport_id": transport, "session_duration_seconds": report["session_duration_seconds"],
            **dict.fromkeys(("fixture", "simulation", "placeholder"), False),
            **dict.fromkeys((
                "real_connected_session", "native_host", "remote_host_observed", "terminal_input_output_round_trip",
                "sftp_round_trip", "monitoring_sample_observed", "same_authenticated_transport_observed",
            ), True),
        },
    }


def write_native_evidence(root: Path, source: dict, asset: dict, report: dict) -> None:
    if report.get("native_peer_verified") is not True or report.get("production_acceptance") is False:
        raise ValueError("release evidence requires a successful native peer observation")
    if root.joinpath("local-qualification.json").exists():
        raise ValueError("a fixture capture cannot be converted into native release evidence")
    session_id = str(uuid4())
    socket = {key: report[key] for key in ("ssh_user", "host_key_sha256", "client_endpoint", "server_endpoint")}
    transport = sha256(json.dumps(socket, sort_keys=True).encode())
    captured = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    identity = {
        **{key: source[key] for key in ("repository", "release_tag", "workflow_run_url", "run_attempt")},
        "source_head_sha": source["head_sha"], "captured_at_utc": captured, "release_target": TARGET,
        "session_id": session_id, "transport_id": transport, "host_key_sha256": report["host_key_sha256"],
        "release_asset": asset,
    }
    references = {}
    for name, values in native_proof_values(report, transport).items():
        captures = {role: {"file": CAPTURE_FILES[name][role], "sha256": report["captures"][CAPTURE_FILES[name][role]]}
                    for role in CAPTURE_ROLES[name]}
        path = root / f"{name}.json"
        write_json(path, {**identity, **values, "schema": PROOF_SCHEMAS[name], "captures": captures})
        references[name] = {"file": path.name, "sha256": sha256(path.read_bytes())}
    envelope = root / "evidence.json"
    write_json(envelope, {
        "schema": SCHEMA, "release_target": TARGET, "release_asset": asset,
        "source": {**source, "captured_at_utc": captured, "capture_kind": "native-connected-session",
                   "synthetic": False, "fixture": False, "simulation": False},
        "session": {"session_id": session_id, "transport_id": transport, "protocol": "ssh",
                    "host_key_sha256": report["host_key_sha256"], "loopback": False},
        "proofs": references,
    })
    result = validate_moba_transport_terminal_evidence(envelope, assets_dir=root)
    if not result.passed:
        raise ValueError(f"native evidence did not validate: {result.errors}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wheel", required=True, type=Path)
    parser.add_argument("--peer-config", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    args = parser.parse_args()
    require_native_runner()
    if args.out.exists() or args.out.is_symlink():
        raise ValueError("release capture output must be a new directory")
    peer = load_peer(args.peer_config)
    tag, asset = verify_wheel(args.wheel)
    source = actions_source(tag)
    if source is None:
        raise ValueError("native capture requires an exact GitHub release attempt")
    with TemporaryDirectory(prefix=".native-transport-", dir=args.out.parent) as temporary:
        scratch = Path(temporary)
        raw, review, home = (scratch / part for part in ("raw", "review", "workspace"))
        for directory in (raw, review, home):
            directory.mkdir()
        os.environ.update(ROW_HOME=str(home), QT_QPA_PLATFORM="offscreen")
        report = capture_session(review, raw, peer, native=True)
        write_native_evidence(review, source, asset, report)
        review.rename(args.out)
    print("Verified native terminal-grid evidence for independent review")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

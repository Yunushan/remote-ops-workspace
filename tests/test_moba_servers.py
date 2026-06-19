from __future__ import annotations

import hashlib
import json
from pathlib import Path

from remote_ops_workspace.cli import build_parser
from remote_ops_workspace.moba_servers import (
    build_moba_server_plan,
    build_moba_server_config_plan,
    build_moba_server_gui_config_surface,
    build_moba_server_runtime_bundle_plan,
    build_moba_server_runtime_status,
    build_moba_server_suite_status,
    discover_packaged_moba_server_runtimes,
    load_moba_server_record,
    SERVER_DEFAULT_PORTS,
    start_moba_server,
    stop_moba_server,
    validate_moba_server_release_evidence,
    write_moba_server_runtime_bundle,
)


def test_moba_server_suite_status_includes_builtin_http_and_daemon_adapters(tmp_path: Path) -> None:
    status = build_moba_server_suite_status(
        system="Linux",
        which=lambda name: "/usr/sbin/sshd" if name == "sshd" else None,
        state_dir=tmp_path,
    )
    services = {service.key: service for service in status.services}

    assert services["http"].available is True
    assert services["http"].selected_runtime == "python-http"
    assert services["ssh"].available is True
    assert services["sftp"].selected_runtime == "sshd-sftp"
    assert services["ftp"].available is False


def test_moba_http_server_plan_uses_loopback_safe_python_http_runtime(tmp_path: Path) -> None:
    plan = build_moba_server_plan("http", root=tmp_path, port=8091)

    assert plan.service == "http"
    assert plan.host == "127.0.0.1"
    assert plan.port == 8091
    assert plan.root == str(tmp_path.resolve())
    assert plan.command[1:] == [
        "-m",
        "http.server",
        "8091",
        "--bind",
        "127.0.0.1",
        "--directory",
        str(tmp_path.resolve()),
    ]
    assert plan.runtime.available is True
    assert plan.public_bind is False


def test_packaged_server_runtime_is_preferred_for_daemon_services(tmp_path: Path) -> None:
    runtime_root = tmp_path / "servers"
    sshd = runtime_root / "ssh" / "bin" / "sshd"
    sshd.parent.mkdir(parents=True)
    sshd.write_text("fake sshd", encoding="utf-8")

    candidates = discover_packaged_moba_server_runtimes("ssh", system="Linux", roots=[runtime_root])
    plan = build_moba_server_plan(
        "ssh",
        port=2225,
        system="Linux",
        which=lambda name: "/usr/sbin/sshd" if name == "sshd" else None,
        packaged_roots=[runtime_root],
    )
    runtime_status = build_moba_server_runtime_status(system="Linux", roots=[runtime_root])

    assert candidates[0].bundled is True
    assert candidates[0].executable == str(sshd)
    assert plan.runtime.bundled is True
    assert plan.command[0] == str(sshd)
    assert runtime_status.packaged_available is True
    assert runtime_status.service_coverage["ssh"] is True


def test_moba_server_runtime_bundle_writer_creates_discoverable_daemon(tmp_path: Path) -> None:
    runtime_root = tmp_path / "servers-bundle"

    plan = build_moba_server_runtime_bundle_plan(
        runtime_root,
        "ssh",
        runtime_key="sshd",
        system="Linux",
        release_target="linux-x64",
        allow_placeholder=True,
    )
    result = write_moba_server_runtime_bundle(plan)
    candidates = discover_packaged_moba_server_runtimes("ssh", system="Linux", roots=[runtime_root])
    runtime_status = build_moba_server_runtime_status(system="Linux", roots=[runtime_root])

    assert result.placeholder is True
    assert result.runtime_sha256
    assert result.files == ("linux/ssh/bin/sshd", "servers-runtime.json")
    assert result.runtime_status.service_coverage["ssh"] is True
    assert candidates[0].bundled is True
    assert candidates[0].executable == result.executable_path
    assert runtime_status.service_coverage["ssh"] is True
    assert Path(result.manifest_path).is_file()


def test_moba_server_config_plan_requires_auth_for_sensitive_daemons(tmp_path: Path) -> None:
    plan = build_moba_server_config_plan(
        "ftp",
        root=tmp_path,
        hardening_profile="strict-private",
    )

    assert plan.schema == "row.moba-servers.policy.v1"
    assert plan.auth_required is True
    assert plan.public_bind_allowed is False
    assert plan.settings["auth"]["passwords_in_config"] is False


def test_moba_server_gui_config_surface_exposes_service_rows_and_actions(tmp_path: Path) -> None:
    surface = build_moba_server_gui_config_surface(
        selected_service="ftp",
        root=tmp_path,
        hardening_profile="strict-private",
        system="Linux",
        which=lambda name: "/usr/sbin/sshd" if name == "sshd" else None,
        state_dir=tmp_path,
    )
    data = surface.to_dict()
    rows = {row["service"]: row for row in data["rows"]}

    assert data["schema"] == "row.moba-servers.gui-config-surface.v1"
    assert data["selected_service"] == "ftp"
    assert data["selected_config"]["service"] == "ftp"
    assert data["selected_config"]["hardening_profile"] == "strict-private"
    assert "service-table" in data["gui_controls"]
    assert rows["http"]["start_action"].startswith("row servers start http")
    assert rows["http"]["root_required"] is True
    assert rows["http"]["auth_required"] is True
    assert rows["ssh"]["runtime_available"] is True
    assert rows["ftp"]["config_action"].startswith("row servers config-plan ftp")


def test_moba_server_plan_rejects_public_bind_without_explicit_flag(tmp_path: Path) -> None:
    try:
        build_moba_server_plan("http", host="0.0.0.0", root=tmp_path)
    except ValueError as exc:
        assert "non-loopback" in str(exc)
    else:
        raise AssertionError("public server bind must require an explicit flag")


def test_moba_server_lifecycle_dry_run_does_not_write_state(tmp_path: Path) -> None:
    plan = build_moba_server_plan("http", root=tmp_path)
    record = start_moba_server(plan, dry_run=True, state_dir=tmp_path)

    assert record.state == "dry-run"
    assert record.pid is None
    assert not (tmp_path / "http-server-state.json").exists()


def test_moba_server_lifecycle_writes_loads_and_stops_state(tmp_path: Path) -> None:
    plan = build_moba_server_plan("http", root=tmp_path, port=8092)
    started = start_moba_server(
        plan,
        state_dir=tmp_path,
        popen_factory=lambda command, env: _FakeProcess(pid=6262),
    )
    loaded = load_moba_server_record("http", state_dir=tmp_path, pid_probe=lambda pid: pid == 6262)
    terminated: list[int] = []
    stopped = stop_moba_server(
        "http",
        state_dir=tmp_path,
        pid_probe=lambda pid: pid == 6262,
        terminator=lambda pid: terminated.append(pid),
    )

    assert started.state == "started"
    assert started.pid == 6262
    assert loaded is not None
    assert loaded.running is True
    assert stopped.state == "stopped"
    assert stopped.running is False
    assert terminated == [6262]


def test_moba_ssh_server_adapter_plan_uses_discovered_sshd() -> None:
    plan = build_moba_server_plan(
        "ssh",
        host="127.0.0.1",
        port=2224,
        system="Linux",
        which=lambda name: "/usr/sbin/sshd" if name == "sshd" else None,
    )

    assert plan.command == ["/usr/sbin/sshd", "-D", "-p", "2224", "-o", "ListenAddress=127.0.0.1"]
    assert plan.runtime.available is True


def test_moba_servers_cli_commands_are_registered() -> None:
    parser = build_parser()
    status = parser.parse_args(["servers", "status", "--json"])
    runtime = parser.parse_args(["servers", "runtime-status", "--json"])
    bundle = parser.parse_args(
        ["servers", "bundle-runtime", "ssh", "--out", "bundle", "--runtime", "sshd", "--system", "Linux", "--json"]
    )
    config = parser.parse_args(["servers", "config-plan", "ftp", "--root", ".", "--json"])
    verify = parser.parse_args(["servers", "evidence-verify", "--evidence", "servers-release.json", "--json"])
    start = parser.parse_args(["servers", "start", "http", "--dry-run", "--json"])
    stop = parser.parse_args(["servers", "stop", "http", "--json"])

    assert status.func.__name__ == "cmd_servers_status"
    assert runtime.func.__name__ == "cmd_servers_runtime_status"
    assert bundle.func.__name__ == "cmd_servers_bundle_runtime"
    assert config.func.__name__ == "cmd_servers_config_plan"
    assert verify.func.__name__ == "cmd_servers_evidence_verify"
    assert start.func.__name__ == "cmd_servers_start"
    assert stop.func.__name__ == "cmd_servers_stop"


def test_moba_server_release_evidence_requires_all_services_and_client_proofs(tmp_path: Path) -> None:
    evidence = _write_server_evidence_bundle(tmp_path)

    result = validate_moba_server_release_evidence(evidence, assets_dir=tmp_path)

    assert result.passed is True
    assert result.errors == []
    assert result.summary["service_count"] == len(SERVER_DEFAULT_PORTS)
    assert result.summary["client_proof_count"] == len(SERVER_DEFAULT_PORTS)


def test_moba_server_release_evidence_rejects_missing_service(tmp_path: Path) -> None:
    evidence = _write_server_evidence_bundle(tmp_path)
    payload = json.loads(evidence.read_text(encoding="utf-8"))
    payload["services"] = payload["services"][:-1]
    evidence.write_text(json.dumps(payload), encoding="utf-8")

    result = validate_moba_server_release_evidence(evidence, assets_dir=tmp_path)

    assert result.passed is False
    assert any("services missing release evidence for" in error for error in result.errors)


class _FakeProcess:
    def __init__(self, pid: int) -> None:
        self.pid = pid


def _write_server_evidence_bundle(tmp_path: Path) -> Path:
    services: list[dict[str, object]] = []
    for service in SERVER_DEFAULT_PORTS:
        runtime = tmp_path / "runtimes" / service / f"{service}d"
        runtime.parent.mkdir(parents=True, exist_ok=True)
        runtime.write_bytes(f"fake {service} daemon".encode("utf-8"))
        client_evidence = tmp_path / "evidence" / f"{service}-client.txt"
        client_evidence.parent.mkdir(parents=True, exist_ok=True)
        client_evidence.write_text(f"{service} client passed\n", encoding="utf-8")
        policy = build_moba_server_config_plan(
            service,
            root=tmp_path if service in {"http", "ftp", "tftp"} else None,
            require_auth=service in {"http", "ftp", "ssh", "sftp", "telnet", "vnc", "nfs"},
        )
        services.append(
            {
                "service": service,
                "runtime": {
                    "key": service,
                    "bundled": True,
                    "executable": str(runtime.relative_to(tmp_path)),
                    "sha256": _sha256(runtime),
                },
                "policy": policy.to_dict(),
                "client_test": {
                    "status": "passed",
                    "command": f"{service}-client --check",
                    "evidence_file": str(client_evidence.relative_to(tmp_path)),
                    "evidence_sha256": _sha256(client_evidence),
                },
            }
        )
    evidence = tmp_path / "servers-release-evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "schema": "row.moba-servers.release-evidence.v1",
                "release_target": "windows-x64",
                "services": services,
            }
        ),
        encoding="utf-8",
    )
    return evidence


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

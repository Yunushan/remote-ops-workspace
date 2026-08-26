from __future__ import annotations

import json
import os
import signal
from dataclasses import replace
from pathlib import Path

import pytest

import remote_ops_workspace.moba_servers as servers


def _runtime(
    key: str,
    *,
    service: str = "ssh",
    executable: str = "daemon",
    available: bool = True,
    bundled: bool = False,
    builtin: bool = False,
) -> servers.MobaEmbeddedServerRuntime:
    return servers.MobaEmbeddedServerRuntime(
        key=key,
        label=key,
        service=service,
        executable=executable,
        available=available,
        bundled=bundled,
        builtin=builtin,
        notes=["test runtime"],
    )


def test_server_status_plans_and_validation_are_json_ready(tmp_path: Path) -> None:
    suite = servers.build_moba_server_suite_status(
        system="Linux",
        which=lambda _name: None,
        packaged_roots=[],
        state_dir=tmp_path,
    )
    suite_data = suite.to_dict()
    assert suite_data["services"][0]["runtimes"][0]["service"] == "http"

    runtime_status = servers.build_moba_server_runtime_status(system="Linux", roots=[])
    assert runtime_status.to_dict()["service_coverage"]["http"] is False

    plan = servers.build_moba_server_plan("http", root=tmp_path)
    assert "http.server" in plan.printable()
    assert plan.to_dict()["runtime"]["key"] == "python-http"

    validation = servers.MobaEmbeddedServerReleaseEvidenceValidation("evidence", ".", False, ["bad"], [], {})
    assert validation.to_dict()["errors"] == ["bad"]


def test_pyftpdlib_discovery_uses_current_python(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(servers.importlib.util, "find_spec", lambda name: object() if name == "pyftpdlib" else None)

    runtimes = servers.discover_moba_server_runtimes(
        "ftp",
        system="Linux",
        which=lambda _name: None,
        packaged_roots=[],
    )

    assert runtimes[0].key == "pyftpdlib"
    assert runtimes[0].available is True
    assert runtimes[0].executable == servers.sys.executable


def test_runtime_status_reports_complete_packaged_coverage(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(servers, "moba_server_runtime_roots", lambda _roots=None: ())
    monkeypatch.setattr(
        servers,
        "discover_packaged_moba_server_runtimes",
        lambda service, **_kwargs: (_runtime(service, service=service, bundled=True),),
    )

    status = servers.build_moba_server_runtime_status(system="Linux", roots=[])

    assert all(status.service_coverage.values())
    assert any("every embedded server service" in note for note in status.notes)


def test_runtime_bundle_source_and_failure_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "sshd-source"
    source.write_bytes(b"sshd")
    plan = servers.build_moba_server_runtime_bundle_plan(
        tmp_path / "bundle",
        "ssh",
        runtime_key="sshd",
        source_path=source,
        system="Linux",
        allow_placeholder=False,
    )
    result = servers.write_moba_server_runtime_bundle(plan)

    assert plan.to_dict()["source_path"] == str(source)
    assert result.placeholder is False
    assert result.to_dict()["runtime_status"]["service_coverage"]["ssh"] is True

    with pytest.raises(ValueError, match="schema"):
        servers.write_moba_server_runtime_bundle(replace(plan, schema="wrong"))

    missing_source = servers.build_moba_server_runtime_bundle_plan(
        tmp_path / "missing",
        "ssh",
        source_path=tmp_path / "not-there",
        system="Linux",
    )
    with pytest.raises(ValueError, match="source is missing"):
        servers.write_moba_server_runtime_bundle(missing_source)

    no_source = servers.build_moba_server_runtime_bundle_plan(
        tmp_path / "no-source",
        "ssh",
        system="Linux",
    )
    with pytest.raises(ValueError, match="source is required"):
        servers.write_moba_server_runtime_bundle(no_source)

    unavailable_status = servers.MobaEmbeddedServerRuntimeStatus(
        "linux",
        (),
        False,
        {service: False for service in servers.SERVER_DEFAULT_PORTS},
        (),
        [],
    )
    monkeypatch.setattr(servers, "build_moba_server_runtime_status", lambda **_kwargs: unavailable_status)
    placeholder_plan = servers.build_moba_server_runtime_bundle_plan(
        tmp_path / "undiscovered",
        "ssh",
        system="Linux",
        allow_placeholder=True,
    )
    undiscovered = servers.write_moba_server_runtime_bundle(placeholder_plan)
    assert any("was not discovered" in note for note in undiscovered.notes)


def test_runtime_bundle_validation_and_windows_name(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    windows = servers.build_moba_server_runtime_bundle_plan(
        tmp_path / "windows",
        "ssh",
        runtime_key="sshd",
        system="windows",
    )
    assert windows.executable_name == "sshd.exe"

    with pytest.raises(ValueError, match="unsupported embedded server runtime"):
        servers.build_moba_server_runtime_bundle_plan(
            tmp_path / "bad-runtime",
            "ftp",
            runtime_key="missing",
            system="Linux",
        )
    with pytest.raises(ValueError, match="must be a filename"):
        servers.build_moba_server_runtime_bundle_plan(
            tmp_path / "bad-name",
            "ssh",
            runtime_key="sshd",
            system="Linux",
            executable_name="nested/sshd",
        )

    target = tmp_path / "daemon"
    target.write_bytes(b"daemon")

    def fail_chmod(_self: Path, _mode: int) -> None:
        raise OSError("read-only")

    monkeypatch.setattr(Path, "chmod", fail_chmod)
    servers._chmod_executable(target)


def test_runtime_manifest_merges_services_and_tolerates_bad_existing_data(tmp_path: Path) -> None:
    manifest = tmp_path / "servers-runtime.json"
    ssh = {"service": "ssh", "runtime": {"key": "sshd"}}
    ftp = {"service": "ftp", "runtime": {"key": "ftpd"}}

    manifest.write_text("{", encoding="utf-8")
    first = servers._merged_server_runtime_manifest(
        manifest,
        release_target="linux-x64",
        system="linux",
        service_record=ssh,
    )
    manifest.write_text(json.dumps(first), encoding="utf-8")
    merged = servers._merged_server_runtime_manifest(
        manifest,
        release_target="linux-x64",
        system="linux",
        service_record=ftp,
    )

    assert [item["service"] for item in merged["services"]] == ["ftp", "ssh"]

    manifest.write_text(json.dumps({"schema": servers.SERVER_RUNTIME_BUNDLE_SCHEMA, "services": "bad"}), encoding="utf-8")
    reset = servers._merged_server_runtime_manifest(
        manifest,
        release_target="linux-x64",
        system="linux",
        service_record=ssh,
    )
    assert reset["services"] == [ssh]


def test_server_runtime_roots_include_environment_and_deduplicate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shared = tmp_path / "shared"
    extra = tmp_path / "extra"
    shared.mkdir()
    monkeypatch.setenv(servers.SERVER_RUNTIME_DIR_ENV, os.pathsep.join((str(shared), str(extra))))

    roots = servers.moba_server_runtime_roots([shared])

    assert roots.count(shared) == 1
    assert extra in roots


def test_public_server_config_and_gui_actions(tmp_path: Path) -> None:
    config = servers.build_moba_server_config_plan(
        "http",
        host="0.0.0.0",
        root=tmp_path,
        hardening_profile="trusted-lan",
        require_auth=True,
        require_tls=True,
        allow_public_bind=True,
    )
    assert config.settings["network"]["public_bind_active"] is True
    assert any("Public bind is active" in note for note in config.notes)
    assert servers.validate_server_bind("public.example", allow_public_bind=True) == "public.example"

    launch = servers.build_moba_server_plan(
        "http",
        host="0.0.0.0",
        root=tmp_path,
        allow_public_bind=True,
    )
    assert any("Public bind requested" in note for note in launch.notes)

    surface = servers.build_moba_server_gui_config_surface(
        selected_service="http",
        root=tmp_path,
        require_tls=True,
        system="Linux",
        which=lambda _name: None,
        packaged_roots=[],
        state_dir=tmp_path,
    )
    http_row = next(row for row in surface.rows if row.service == "http")
    assert "--require-tls" in http_row.config_action


def test_server_plan_reports_unavailable_runtime_and_rejects_start(tmp_path: Path) -> None:
    plan = servers.build_moba_server_plan(
        "ftp",
        root=tmp_path,
        system="Linux",
        which=lambda _name: None,
        packaged_roots=[],
    )
    assert plan.runtime.available is False
    assert any("not available" in note for note in plan.notes)

    with pytest.raises(ValueError, match="runtime is not available"):
        servers.start_moba_server(plan, state_dir=tmp_path)


def test_server_lifecycle_missing_inactive_and_malformed_state(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="no managed embedded server state"):
        servers.stop_moba_server("http", state_dir=tmp_path)

    malformed = tmp_path / "http-server-state.json"
    malformed.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a JSON object"):
        servers.load_moba_server_record("http", state_dir=tmp_path)

    record = servers.MobaEmbeddedServerLifecycleRecord(
        service="http",
        host="127.0.0.1",
        port=8080,
        runtime_key="python-http",
        command=["python", "-m", "http.server"],
        state="stopped",
        pid=None,
        state_path=str(malformed),
    )
    malformed.write_text(json.dumps(record.to_dict()), encoding="utf-8")
    terminated: list[int] = []
    stopped = servers.stop_moba_server("http", state_dir=tmp_path, terminator=terminated.append)

    assert stopped.state == "stopped"
    assert terminated == []


def test_release_evidence_reports_file_shape_and_schema_errors(tmp_path: Path) -> None:
    missing = servers.validate_moba_server_release_evidence(tmp_path / "missing.json")
    assert any("cannot be read" in error for error in missing.errors)

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    invalid_result = servers.validate_moba_server_release_evidence(invalid)
    assert any("not valid JSON" in error for error in invalid_result.errors)

    wrong_root = tmp_path / "root.json"
    wrong_root.write_text("[]", encoding="utf-8")
    root_result = servers.validate_moba_server_release_evidence(wrong_root)
    assert "evidence root must be a JSON object" in root_result.errors

    wrong_services = tmp_path / "services.json"
    wrong_services.write_text(
        json.dumps({"schema": "wrong", "release_target": "bad\nvalue", "services": {}}),
        encoding="utf-8",
    )
    services_result = servers.validate_moba_server_release_evidence(wrong_services)
    errors = "\n".join(services_result.errors)
    assert "schema must be" in errors
    assert "release_target is invalid" in errors
    assert "services must be a list" in errors


def test_release_evidence_rejects_malformed_service_contracts(tmp_path: Path) -> None:
    evidence = tmp_path / "evidence.json"
    evidence.write_text(
        json.dumps(
            {
                "schema": servers.SERVER_RELEASE_EVIDENCE_SCHEMA,
                "release_target": "linux-x64",
                "services": [
                    "not-an-object",
                    {},
                    {
                        "service": "invalid",
                        "runtime": {"bundled": False, "executable": "runtime", "sha256": "bad"},
                        "policy": {"schema": "bad", "public_bind_allowed": True, "auth_required": False},
                        "client_test": {"status": "failed", "command": ""},
                    },
                    {
                        "service": "ftp",
                        "runtime": {"bundled": False},
                        "policy": {
                            "schema": servers.SERVER_POLICY_SCHEMA,
                            "public_bind_allowed": True,
                            "auth_required": False,
                        },
                        "client_test": {"status": "failed"},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    result = servers.validate_moba_server_release_evidence(evidence, assets_dir=tmp_path)
    errors = "\n".join(result.errors)

    assert "services[0] must be an object" in errors
    assert "services[1].service is required" in errors
    assert "services[2].service is invalid" in errors
    assert "runtime.bundled must be true" in errors
    assert "policy.schema must be" in errors
    assert "auth_required must be true for ftp" in errors
    assert "public binds require authentication" in errors
    assert "client_test.status must be passed" in errors


def test_release_asset_validation_rejects_bad_paths_and_hashes(tmp_path: Path) -> None:
    errors: list[str] = []
    digest = "0" * 64

    assert servers._validate_asset_hash("", "", tmp_path, errors, "asset") is None
    assert servers._validate_asset_hash("runtime", "bad", tmp_path, errors, "asset") is None
    assert servers._validate_asset_hash("../outside", digest, tmp_path, errors, "asset") is None
    assert servers._validate_asset_hash("missing", digest, tmp_path, errors, "asset") is None

    existing = tmp_path / "existing"
    existing.write_bytes(b"content")
    assert servers._validate_asset_hash(existing.name, digest, tmp_path, errors, "asset") is None

    joined = "\n".join(errors)
    assert "64-character" in joined
    assert "inside assets_dir" in joined
    assert "file is missing" in joined
    assert "SHA-256 mismatch" in joined


@pytest.mark.parametrize(
    ("key", "service", "executable", "root", "host", "expected"),
    [
        ("pyftpdlib", "ftp", "python.exe", "root", "127.0.0.1", ["python.exe", "-m", "pyftpdlib"]),
        ("pyftpdlib", "ftp", "pyftpdlib", "root", "127.0.0.1", ["pyftpdlib", "-i"]),
        ("ftpd", "ftp", "ftpd", "root", "127.0.0.1", ["ftpd", "-D"]),
        ("tftpd", "tftp", "tftpd", "root", "127.0.0.1", ["tftpd", "--foreground"]),
        ("atftpd", "tftp", "atftpd", "root", "127.0.0.1", ["atftpd", "--foreground"]),
        ("sshd-sftp", "sftp", "sshd", None, "127.0.0.1", ["sshd", "-D"]),
        ("telnetd", "telnet", "telnetd", None, "127.0.0.1", ["telnetd", "-debug"]),
        ("x11vnc", "vnc", "x11vnc", None, "127.0.0.1", ["x11vnc", "-listen"]),
        ("vncserver", "vnc", "vncserver", None, "127.0.0.1", ["vncserver", "-rfbport"]),
        ("vncserver", "vnc", "vncserver", None, "192.0.2.1", ["vncserver", "-rfbport"]),
        ("nfsd", "nfs", "nfsd", None, "127.0.0.1", ["nfsd", "-F"]),
    ],
)
def test_runtime_commands_cover_daemon_adapters(
    tmp_path: Path,
    key: str,
    service: str,
    executable: str,
    root: str | None,
    host: str,
    expected: list[str],
) -> None:
    runtime_root = tmp_path if root else None
    command = servers._runtime_command(_runtime(key, service=service, executable=executable), host, 2222, runtime_root)
    assert command[: len(expected)] == expected
    if key == "vncserver":
        assert command[-1] == ("yes" if host == "127.0.0.1" else "no")


@pytest.mark.parametrize("key", ["python-http", "pyftpdlib", "ftpd", "tftpd"])
def test_file_server_runtime_commands_require_root(key: str) -> None:
    service = "http" if key == "python-http" else "tftp" if key == "tftpd" else "ftp"
    with pytest.raises(ValueError, match="requires a root directory"):
        servers._runtime_command(_runtime(key, service=service), "127.0.0.1", 1234, None)


def test_runtime_command_and_definition_validation(monkeypatch: pytest.MonkeyPatch) -> None:
    with pytest.raises(ValueError, match="unsupported embedded server runtime"):
        servers._runtime_command(_runtime("unknown"), "127.0.0.1", 1, None)
    with pytest.raises(ValueError, match="unsupported embedded server service"):
        servers._runtime_definitions("unknown", "linux")
    with pytest.raises(ValueError, match="hardening profile"):
        servers._hardening_profile("unknown")
    with pytest.raises(ValueError, match="no embedded server runtimes"):
        servers._select_runtime(())

    assert servers._runtime_definition_by_key("ssh", "linux", None)[0] == "sshd"
    assert servers._runtime_definition_by_key("ftp", "linux", None)[0] == "pyftpdlib"

    monkeypatch.setattr(
        servers,
        "_runtime_definitions",
        lambda _service, _system: (
            ("one", "one", "one", False, True, ()),
            ("two", "two", "two", False, True, ()),
        ),
    )
    assert servers._runtime_definition_by_key("ftp", "linux", None)[0] == "one"


def test_root_service_and_loopback_validation(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="root does not exist"):
        servers.build_moba_server_plan("http", root=tmp_path / "missing")
    with pytest.raises(ValueError, match="unsupported embedded server service"):
        servers.build_moba_server_plan("smtp")

    assert servers._command_root_arg("ssh", tmp_path) == ""
    assert servers._command_root_arg("http", None) == str(Path.cwd().resolve())
    assert servers._is_loopback_host("localhost") is True
    assert servers._is_loopback_host("ip6-localhost") is True
    assert servers._is_loopback_host("::1") is True
    assert servers._is_loopback_host("not-an-ip") is False


def test_pid_probe_and_termination_platform_paths(monkeypatch: pytest.MonkeyPatch) -> None:
    assert servers._pid_running(0) is False

    with monkeypatch.context() as patch:
        patch.setattr(servers.os, "kill", lambda _pid, _sig: None)
        assert servers._pid_running(42) is True
    with monkeypatch.context() as patch:
        patch.setattr(servers.os, "kill", lambda _pid, _sig: _raise(OSError("missing")))
        assert servers._pid_running(42) is False

    windows_calls: list[list[str]] = []
    with monkeypatch.context() as patch:
        patch.setattr(servers.platform, "system", lambda: "Windows")
        patch.setattr(servers, "run_hidden", lambda command, **_kwargs: windows_calls.append(command))
        servers._terminate_pid(50)
    assert windows_calls == [["taskkill", "/PID", "50", "/T"]]

    posix_calls: list[tuple[int, int]] = []
    with monkeypatch.context() as patch:
        patch.setattr(servers.platform, "system", lambda: "Linux")
        patch.setattr(servers.os, "kill", lambda pid, sig: posix_calls.append((pid, sig)))
        servers._terminate_pid(51)
    assert posix_calls == [(51, signal.SIGTERM)]


def _raise(error: BaseException) -> None:
    raise error

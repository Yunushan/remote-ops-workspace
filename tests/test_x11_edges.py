from __future__ import annotations

import hashlib
import json
import os
import signal
import subprocess
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

import pytest

import remote_ops_workspace.x11 as x11


def test_x11_data_objects_are_printable_and_json_ready(tmp_path: Path) -> None:
    basic = x11.XServerPlan(["Xorg", ":2"], ["note"])
    assert basic.printable() == "Xorg :2"

    plan = x11.build_moba_x_server_plan(
        display=":2",
        system="darwin",
        which=lambda name: "/usr/bin/open" if name == "open" else None,
        packaged_roots=[],
        display_probe=lambda _display: False,
    )
    assert plan.printable() == "/usr/bin/open -a XQuartz"
    assert plan.to_dict()["runtime"]["key"] == "xquartz"
    assert any("macOS uses XQuartz" in note for note in plan.notes)

    status = x11.build_moba_x_server_status(
        display=":2",
        system="darwin",
        which=lambda name: "/usr/bin/open" if name == "open" else None,
        packaged_roots=[],
        display_probe=lambda _display: False,
        state_path=tmp_path / "missing-state.json",
    )
    assert status.to_dict()["plan"]["display"] == ":2"

    package_status = x11.XServerPackageStatus("linux", (), False, (), "", ["missing"])
    assert package_status.to_dict()["packaged_available"] is False

    validation = x11.XServerReleaseEvidenceValidation("evidence.json", ".", False, ["bad"], [], {})
    assert validation.to_dict()["errors"] == ["bad"]


def test_runtime_bundle_source_and_failure_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "source-Xvfb"
    source.write_bytes(b"real runtime")
    plan = x11.build_moba_x_server_runtime_bundle_plan(
        tmp_path / "source-bundle",
        runtime_key="xvfb",
        source_path=source,
        system="linux",
        allow_placeholder=False,
    )
    result = x11.write_moba_x_server_runtime_bundle(plan)

    assert plan.to_dict()["source_path"] == str(source)
    assert result.placeholder is False
    assert result.to_dict()["package_status"]["packaged_available"] is True

    with pytest.raises(ValueError, match="schema"):
        x11.write_moba_x_server_runtime_bundle(replace(plan, schema="wrong"))

    missing_source = x11.build_moba_x_server_runtime_bundle_plan(
        tmp_path / "missing-source-bundle",
        runtime_key="xvfb",
        source_path=tmp_path / "missing-Xvfb",
        system="linux",
    )
    with pytest.raises(ValueError, match="source is missing"):
        x11.write_moba_x_server_runtime_bundle(missing_source)

    no_source = x11.build_moba_x_server_runtime_bundle_plan(
        tmp_path / "no-source-bundle",
        runtime_key="xvfb",
        system="linux",
    )
    with pytest.raises(ValueError, match="source is required"):
        x11.write_moba_x_server_runtime_bundle(no_source)

    unavailable = x11.XServerPackageStatus("linux", (), False, (), "", [])
    monkeypatch.setattr(x11, "build_moba_x_server_package_status", lambda **_kwargs: unavailable)
    placeholder_plan = x11.build_moba_x_server_runtime_bundle_plan(
        tmp_path / "undiscovered-bundle",
        runtime_key="xvfb",
        system="linux",
        allow_placeholder=True,
    )
    undiscovered = x11.write_moba_x_server_runtime_bundle(placeholder_plan)
    assert any("was not discovered" in note for note in undiscovered.notes)


def test_runtime_bundle_platform_validation_and_chmod_failure(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    windows_plan = x11.build_moba_x_server_runtime_bundle_plan(
        tmp_path / "windows",
        runtime_key="vcxsrv",
        system="windows",
    )
    assert windows_plan.executable_name == "vcxsrv.exe"

    with pytest.raises(ValueError, match="unsupported X server runtime"):
        x11.build_moba_x_server_runtime_bundle_plan(
            tmp_path / "bad",
            runtime_key="missing",
            system="linux",
        )

    target = tmp_path / "runtime"
    target.write_bytes(b"runtime")

    def fail_chmod(_self: Path, _mode: int) -> None:
        raise OSError("read-only filesystem")

    monkeypatch.setattr(Path, "chmod", fail_chmod)
    x11._chmod_executable(target)


def test_package_status_reports_no_packaged_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(x11, "x_server_packaged_runtime_roots", lambda _roots=None: ())
    status = x11.build_moba_x_server_package_status(system="linux", roots=[])

    assert status.packaged_available is False
    assert any("No packaged X server runtime" in note for note in status.notes)


def test_packaged_runtime_roots_include_environment_and_deduplicate(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    shared = tmp_path / "shared"
    extra = tmp_path / "extra"
    shared.mkdir()
    monkeypatch.setenv(x11.XSERVER_RUNTIME_DIR_ENV, os.pathsep.join((str(shared), str(extra))))

    roots = x11.x_server_packaged_runtime_roots([shared])

    assert roots.count(shared) == 1
    assert extra in roots


@pytest.mark.parametrize(
    ("system", "key", "expected"),
    [
        ("windows", "xlaunch", ["runtime"]),
        ("windows", "xming", ["runtime", ":3", "-multiwindow", "-clipboard", "-ac"]),
        ("darwin", "xquartz-xorg", ["runtime", ":3"]),
        ("darwin", "xquartz", ["runtime", "-a", "XQuartz"]),
        ("linux", "xvfb", ["runtime", ":3", "-screen", "0", "1920x1080x24", "-nolisten", "tcp"]),
        ("linux", "xephyr", ["runtime", ":3", "-nolisten", "tcp"]),
        ("linux", "xorg", ["runtime", ":3", "-nolisten", "tcp"]),
    ],
)
def test_runtime_commands_cover_supported_platform_variants(
    system: str,
    key: str,
    expected: list[str],
) -> None:
    runtime = x11.XServerRuntimeCandidate(key, key, "runtime", True, "test")
    assert x11._runtime_command(runtime, ":3", system) == expected


def test_run_and_lifecycle_failure_paths(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    launched: list[list[str]] = []
    basic = x11.XServerPlan(["Xorg", ":4"], [])
    monkeypatch.setattr(x11, "popen_hidden", lambda command: launched.append(command))

    assert x11.run_x_server(basic, dry_run=True) is basic
    assert launched == []
    assert x11.run_x_server(basic) is basic
    assert launched == [["Xorg", ":4"]]

    unavailable_runtime = x11.XServerRuntimeCandidate("xorg", "Xorg", "Xorg", False, "missing")
    unavailable_plan = x11.ManagedXServerPlan(
        display=":4",
        command=["Xorg", ":4"],
        runtime=unavailable_runtime,
        extensions=x11.x_server_extension_inventory(unavailable_runtime),
        environment={"DISPLAY": ":4"},
        display_in_use=False,
        notes=[],
        candidates=(unavailable_runtime,),
    )
    with pytest.raises(ValueError, match="runtime is not available"):
        x11.start_moba_x_server(unavailable_plan, state_path=tmp_path / "unused.json")

    with pytest.raises(ValueError, match="no managed X server state"):
        x11.stop_moba_x_server(state_path=tmp_path / "missing.json")

    malformed = tmp_path / "malformed.json"
    malformed.write_text("[]", encoding="utf-8")
    with pytest.raises(ValueError, match="must be a JSON object"):
        x11.load_moba_x_server_record(state_path=malformed)


def test_stop_does_not_terminate_an_inactive_record(tmp_path: Path) -> None:
    state_path = tmp_path / "inactive.json"
    record = x11.XServerLifecycleRecord(
        display=":5",
        runtime_key="xvfb",
        command=["Xvfb", ":5"],
        state="stopped",
        pid=123,
        started_at="2026-01-01T00:00:00+00:00",
        state_path=str(state_path),
    )
    state_path.write_text(json.dumps(record.to_dict()), encoding="utf-8")
    terminated: list[int] = []

    stopped = x11.stop_moba_x_server(state_path=state_path, terminator=terminated.append)

    assert stopped.state == "stopped"
    assert terminated == []


def test_smoke_rejects_invalid_timeout_and_reports_missing_probe(tmp_path: Path) -> None:
    common = {
        "display": ":6",
        "system": "linux",
        "which": lambda name: "/usr/bin/Xvfb" if name == "Xvfb" else None,
        "packaged_roots": [],
        "display_probe": lambda _display: False,
        "state_path": tmp_path / "missing.json",
    }
    with pytest.raises(ValueError, match="timeout must be positive"):
        x11.run_moba_x_server_smoke(**common, timeout_seconds=0)

    evidence = x11.run_moba_x_server_smoke(**common)
    assert evidence.status == "missing-probe-command"


def test_smoke_reports_timeout_and_decodes_partial_bytes(tmp_path: Path) -> None:
    def timeout_runner(command: list[str], **_kwargs: object) -> None:
        raise subprocess.TimeoutExpired(command, 1, output=b"partial out", stderr=b"partial err")

    evidence = x11.run_moba_x_server_smoke(
        display=":7",
        system="linux",
        which=lambda name: "/usr/bin/Xorg" if name == "Xorg" else None,
        packaged_roots=[],
        display_probe=lambda _display: False,
        state_path=tmp_path / "missing.json",
        probe_command="xdpyinfo",
        runner=timeout_runner,
    )

    assert evidence.status == "timeout"
    assert evidence.stdout == "partial out"
    assert evidence.stderr == "partial err"
    assert x11._subprocess_output_text(None) == ""


def test_smoke_reports_probe_error_and_failed_output(tmp_path: Path) -> None:
    common = {
        "display": ":8",
        "system": "linux",
        "which": lambda name: "/usr/bin/Xorg" if name == "Xorg" else None,
        "packaged_roots": [],
        "display_probe": lambda _display: False,
        "state_path": tmp_path / "missing.json",
        "probe_command": "xdpyinfo",
    }

    def fail_runner(_command: list[str], **_kwargs: object) -> None:
        raise OSError("probe unavailable")

    failed_to_run = x11.run_moba_x_server_smoke(**common, runner=fail_runner)
    assert failed_to_run.status == "probe-error"
    assert failed_to_run.stderr == "probe unavailable"

    long_output = "x" * 4100
    completed = SimpleNamespace(returncode=2, stdout=long_output, stderr="failed")
    failed = x11.run_moba_x_server_smoke(**common, runner=lambda *_args, **_kwargs: completed)
    assert failed.status == "failed"
    assert failed.stdout.endswith("...[truncated]")


def test_smoke_discovers_default_probe_command(tmp_path: Path) -> None:
    resolved = {"Xorg": "/usr/bin/Xorg", "xset": "/usr/bin/xset"}
    completed = SimpleNamespace(returncode=0, stdout="ok", stderr="")
    evidence = x11.run_moba_x_server_smoke(
        display=":9",
        system="linux",
        which=lambda name: resolved.get(name),
        packaged_roots=[],
        display_probe=lambda _display: False,
        state_path=tmp_path / "missing.json",
        runner=lambda *_args, **_kwargs: completed,
    )

    assert evidence.passed is True
    assert evidence.probe_command == ["/usr/bin/xset", "-display", ":9", "q"]


def test_release_evidence_reports_file_and_shape_errors(tmp_path: Path) -> None:
    missing = x11.validate_moba_x_server_release_evidence(tmp_path / "missing.json")
    assert any("cannot be read" in error for error in missing.errors)

    invalid = tmp_path / "invalid.json"
    invalid.write_text("{", encoding="utf-8")
    invalid_result = x11.validate_moba_x_server_release_evidence(invalid)
    assert any("not valid JSON" in error for error in invalid_result.errors)

    wrong_root = tmp_path / "list.json"
    wrong_root.write_text("[]", encoding="utf-8")
    root_result = x11.validate_moba_x_server_release_evidence(wrong_root)
    assert "evidence root must be a JSON object" in root_result.errors


def test_release_evidence_rejects_invalid_fields_and_hashes(tmp_path: Path) -> None:
    evidence, payload = _write_valid_release_evidence(tmp_path, display=":10")
    payload["schema"] = "wrong"
    payload["release_target"] = "bad\nvalue"
    payload["display"] = "invalid-display"
    payload["runtime"].update(
        {
            "source": "PATH",
            "bundled": False,
            "sha256": "BAD",
        }
    )
    payload["smoke"].update({"passed": False, "status": "failed"})
    payload["forwarded_gui_app"].update(
        {
            "status": "failed",
            "command": "",
            "x11_forwarding": "bogus",
            "window_observed": False,
        }
    )
    evidence.write_text(json.dumps(payload), encoding="utf-8")

    result = x11.validate_moba_x_server_release_evidence(evidence, assets_dir=tmp_path)
    errors = "\n".join(result.errors)

    assert result.passed is False
    assert "schema must be" in errors
    assert "release_target is invalid" in errors
    assert "display is invalid" in errors
    assert "runtime.source must be" in errors
    assert "runtime.executable sha256 must be" in errors
    assert "smoke must have passed" in errors
    assert "forwarded_gui_app.status must be passed" in errors
    assert "forwarded_gui_app.command is required" in errors
    assert "x11_forwarding must be trusted" in errors
    assert "window_observed must be true" in errors


def test_release_evidence_validates_asset_boundaries_and_hashes(tmp_path: Path) -> None:
    errors: list[str] = []
    valid_digest = "0" * 64

    assert x11._validate_asset_hash("", "", tmp_path, errors, "asset") is None
    assert x11._validate_asset_hash("asset", "invalid", tmp_path, errors, "asset") is None
    assert x11._validate_asset_hash("../outside", valid_digest, tmp_path, errors, "asset") is None
    assert x11._validate_asset_hash("missing", valid_digest, tmp_path, errors, "asset") is None

    existing = tmp_path / "existing"
    existing.write_bytes(b"content")
    assert x11._validate_asset_hash("existing", valid_digest, tmp_path, errors, "asset") is None

    joined = "\n".join(errors)
    assert "64-character" in joined
    assert "inside assets_dir" in joined
    assert "file is missing" in joined
    assert "SHA-256 mismatch" in joined


@pytest.mark.parametrize(
    ("smoke_content", "expected_error"),
    [
        ("{", "cannot be parsed as JSON"),
        ("[]", "JSON root must be an object"),
        (json.dumps({"passed": False, "display": ":wrong"}), "must also have passed=true"),
    ],
)
def test_release_evidence_checks_smoke_evidence_content(
    tmp_path: Path,
    smoke_content: str,
    expected_error: str,
) -> None:
    evidence, payload = _write_valid_release_evidence(tmp_path, display=":11")
    smoke = tmp_path / "smoke.json"
    smoke.write_text(smoke_content, encoding="utf-8")
    payload["smoke"]["evidence_sha256"] = _sha256(smoke)
    evidence.write_text(json.dumps(payload), encoding="utf-8")

    result = x11.validate_moba_x_server_release_evidence(evidence, assets_dir=tmp_path)

    assert any(expected_error in error for error in result.errors)
    if "passed" in expected_error:
        assert any("display must match" in error for error in result.errors)


def test_release_evidence_skips_json_parsing_for_non_json_smoke_asset(tmp_path: Path) -> None:
    evidence, payload = _write_valid_release_evidence(tmp_path, display=":12")
    smoke = tmp_path / "smoke.txt"
    smoke.write_text("passed", encoding="utf-8")
    payload["smoke"].update({"evidence_file": smoke.name, "evidence_sha256": _sha256(smoke)})
    evidence.write_text(json.dumps(payload), encoding="utf-8")

    result = x11.validate_moba_x_server_release_evidence(evidence, assets_dir=tmp_path)

    assert result.passed is True


def test_display_detection_checks_unix_socket_and_tcp(monkeypatch: pytest.MonkeyPatch) -> None:
    class ExistingSocket:
        def exists(self) -> bool:
            return True

    with monkeypatch.context() as patch:
        patch.setattr(x11.os, "name", "posix")
        patch.setattr(x11, "Path", lambda _value: ExistingSocket())
        assert x11.is_x_display_in_use(":13.1") is True

    connections: list[tuple[tuple[str, int], float]] = []

    class Connection:
        def __enter__(self) -> Connection:
            return self

        def __exit__(self, *_args: object) -> None:
            return None

    def connect(address: tuple[str, int], timeout: float) -> Connection:
        connections.append((address, timeout))
        return Connection()

    with monkeypatch.context() as patch:
        patch.setattr(x11.os, "name", "nt")
        patch.setattr(x11.socket, "create_connection", connect)
        assert x11.is_x_display_in_use(":14") is True

    assert connections == [(('127.0.0.1', 6014), 0.2)]

    with monkeypatch.context() as patch:
        patch.setattr(x11.os, "name", "nt")
        patch.setattr(x11.socket, "create_connection", lambda *_args, **_kwargs: _raise(OSError("closed")))
        assert x11.is_x_display_in_use(":14") is False


def test_pid_probe_covers_windows_and_posix_outcomes(monkeypatch: pytest.MonkeyPatch) -> None:
    assert x11._pid_exists(0) is False

    with monkeypatch.context() as patch:
        patch.setattr(x11.os, "name", "nt")
        patch.setattr(x11, "run_hidden", lambda *_args, **_kwargs: SimpleNamespace(stdout='"python","42"'))
        assert x11._pid_exists(42) is True
        assert x11._pid_exists(41) is False

    with monkeypatch.context() as patch:
        patch.setattr(x11.os, "name", "nt")
        patch.setattr(x11, "run_hidden", lambda *_args, **_kwargs: _raise(OSError("tasklist failed")))
        assert x11._pid_exists(42) is False

    for failure, expected in (
        (None, True),
        (ProcessLookupError(), False),
        (PermissionError(), True),
        (OSError(), False),
    ):
        with monkeypatch.context() as patch:
            patch.setattr(x11.os, "name", "posix")

            def kill(_pid: int, _signal: int, failure: BaseException | None = failure) -> None:
                if failure is not None:
                    raise failure

            patch.setattr(x11.os, "kill", kill)
            assert x11._pid_exists(42) is expected


def test_pid_termination_and_first_available(monkeypatch: pytest.MonkeyPatch) -> None:
    windows_calls: list[list[str]] = []
    with monkeypatch.context() as patch:
        patch.setattr(x11.os, "name", "nt")
        patch.setattr(x11, "run_hidden", lambda command, **_kwargs: windows_calls.append(command))
        x11._terminate_pid(51)
    assert windows_calls == [["taskkill", "/PID", "51", "/T"]]

    posix_calls: list[tuple[int, int]] = []
    with monkeypatch.context() as patch:
        patch.setattr(x11.os, "name", "posix")
        patch.setattr(x11.os, "kill", lambda pid, sig: posix_calls.append((pid, sig)))
        x11._terminate_pid(52)
    assert posix_calls == [(52, signal.SIGTERM)]

    with monkeypatch.context() as patch:
        patch.setattr(x11.shutil, "which", lambda name: f"/bin/{name}" if name == "second" else None)
        assert x11._first_available(["first", "second", "third"]) == "second"

    monkeypatch.setattr(x11.shutil, "which", lambda _name: None)
    assert x11._first_available(["first"]) is None


def _write_valid_release_evidence(tmp_path: Path, *, display: str) -> tuple[Path, dict[str, object]]:
    runtime = tmp_path / "runtime"
    runtime.write_bytes(b"runtime")
    smoke = tmp_path / "smoke.json"
    smoke.write_text(json.dumps({"passed": True, "display": display}), encoding="utf-8")
    screenshot = tmp_path / "window.png"
    screenshot.write_bytes(b"png")
    payload: dict[str, object] = {
        "schema": x11.XSERVER_RELEASE_EVIDENCE_SCHEMA,
        "release_target": "linux-x64",
        "platform": "linux",
        "display": display,
        "runtime": {
            "key": "xvfb",
            "source": "packaged",
            "bundled": True,
            "executable": runtime.name,
            "sha256": _sha256(runtime),
        },
        "smoke": {
            "passed": True,
            "status": "passed",
            "evidence_file": smoke.name,
            "evidence_sha256": _sha256(smoke),
        },
        "forwarded_gui_app": {
            "status": "passed",
            "command": "xclock",
            "x11_forwarding": "trusted",
            "window_observed": True,
            "screenshot": screenshot.name,
            "screenshot_sha256": _sha256(screenshot),
        },
    }
    evidence = tmp_path / "release.json"
    evidence.write_text(json.dumps(payload), encoding="utf-8")
    return evidence, payload


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _raise(error: BaseException) -> None:
    raise error

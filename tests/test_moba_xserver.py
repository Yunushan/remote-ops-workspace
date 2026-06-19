from __future__ import annotations

import hashlib
import json
from pathlib import Path

from remote_ops_workspace.cli import build_parser
from remote_ops_workspace.x11 import (
    build_moba_x_server_plan,
    build_moba_x_server_package_status,
    build_moba_x_server_runtime_bundle_plan,
    build_moba_x_server_status,
    discover_packaged_x_server_runtimes,
    discover_x_server_runtimes,
    load_moba_x_server_record,
    run_moba_x_server_smoke,
    start_moba_x_server,
    stop_moba_x_server,
    validate_moba_x_server_release_evidence,
    write_moba_x_server_runtime_bundle,
    write_moba_x_server_smoke_evidence,
    x_server_extension_inventory,
)


def test_moba_x_server_plan_discovers_windows_runtime_and_extensions() -> None:
    plan = build_moba_x_server_plan(
        display=":7",
        system="windows",
        which=lambda name: f"C:/Tools/{name}.exe" if name == "vcxsrv" else None,
        display_probe=lambda display: False,
    )

    assert plan.runtime.key == "vcxsrv"
    assert plan.command[:2] == ["C:/Tools/vcxsrv.exe", ":7"]
    assert "-multiwindow" in plan.command
    assert "-clipboard" in plan.command
    assert plan.environment == {"DISPLAY": ":7"}
    assert plan.display_in_use is False
    assert {"glx", "randr", "composite", "xdmcp"}.issubset(
        {extension.key for extension in plan.extensions}
    )


def test_moba_x_server_status_reports_display_collision_without_blocking() -> None:
    status = build_moba_x_server_status(
        display=":8",
        system="linux",
        which=lambda name: f"/usr/bin/{name}" if name == "Xvfb" else None,
        display_probe=lambda display: True,
    )

    assert status.available is True
    assert status.selected_runtime == "xvfb"
    assert status.display_in_use is True
    assert status.plan is not None
    assert status.plan.command[:2] == ["/usr/bin/Xvfb", ":8"]
    assert any("Display appears to be in use" in note for note in status.notes)


def test_moba_x_server_start_plan_blocks_display_collision() -> None:
    try:
        build_moba_x_server_plan(
            display=":8",
            system="linux",
            which=lambda name: f"/usr/bin/{name}" if name == "Xorg" else None,
            display_probe=lambda display: True,
        )
    except ValueError as exc:
        assert "appears to be in use" in str(exc)
    else:
        raise AssertionError("X server start plan should reject a display collision")


def test_x_server_runtime_inventory_is_json_ready() -> None:
    candidates = discover_x_server_runtimes(
        system="darwin",
        which=lambda name: "/usr/bin/open" if name == "open" else None,
    )
    extensions = x_server_extension_inventory(candidates[0])

    assert candidates[0].to_dict()["available"] is True
    assert extensions[0].to_dict()["status"] == "planned"


def test_packaged_x_server_runtime_is_preferred_over_path(tmp_path: Path) -> None:
    runtime_root = tmp_path / "release-runtime"
    executable = runtime_root / "linux" / "bin" / "Xvfb"
    executable.parent.mkdir(parents=True)
    executable.write_text("fake xvfb", encoding="utf-8")

    candidates = discover_packaged_x_server_runtimes(system="linux", roots=[runtime_root])
    plan = build_moba_x_server_plan(
        display=":15",
        system="linux",
        which=lambda name: None,
        packaged_roots=[runtime_root],
        display_probe=lambda display: False,
    )
    package_status = build_moba_x_server_package_status(system="linux", roots=[runtime_root])

    assert candidates[0].key == "xvfb"
    assert candidates[0].bundled is True
    assert candidates[0].source.startswith("packaged:")
    assert plan.runtime.key == "xvfb"
    assert plan.runtime.bundled is True
    assert plan.command[0] == str(executable)
    assert package_status.packaged_available is True
    assert package_status.selected_runtime == "xvfb"


def test_x_server_runtime_bundle_writer_creates_discoverable_runtime(tmp_path: Path) -> None:
    out_dir = tmp_path / "xserver-bundle"

    plan = build_moba_x_server_runtime_bundle_plan(
        out_dir,
        runtime_key="xvfb",
        system="linux",
        release_target="linux-x64",
        allow_placeholder=True,
    )
    result = write_moba_x_server_runtime_bundle(plan)
    package_status = build_moba_x_server_package_status(system="linux", roots=[out_dir])

    assert result.placeholder is True
    assert result.runtime_sha256
    assert result.files == ("linux/bin/Xvfb", "xserver-runtime.json")
    assert result.package_status.packaged_available is True
    assert package_status.selected_runtime == "xvfb"
    assert Path(result.manifest_path).is_file()


def test_x11_status_cli_command_is_registered() -> None:
    args = build_parser().parse_args(["x11", "status", "--display", ":9", "--json"])

    assert args.func.__name__ == "cmd_x11_status"


def test_moba_x_server_lifecycle_writes_and_stops_state(tmp_path) -> None:
    state_path = tmp_path / "xserver-state.json"
    plan = build_moba_x_server_plan(
        display=":10",
        system="linux",
        which=lambda name: "/usr/bin/Xvfb" if name == "Xvfb" else None,
        display_probe=lambda display: False,
    )
    started = start_moba_x_server(
        plan,
        state_path=state_path,
        popen_factory=lambda command, env: _FakeProcess(pid=4242),
    )
    loaded = load_moba_x_server_record(state_path=state_path, pid_probe=lambda pid: pid == 4242)
    terminated: list[int] = []
    stopped = stop_moba_x_server(
        state_path=state_path,
        pid_probe=lambda pid: pid == 4242,
        terminator=lambda pid: terminated.append(pid),
    )

    assert started.pid == 4242
    assert started.state == "started"
    assert loaded is not None
    assert loaded.running is True
    assert stopped.state == "stopped"
    assert stopped.running is False
    assert terminated == [4242]


def test_moba_x_server_lifecycle_dry_run_does_not_write_state(tmp_path) -> None:
    state_path = tmp_path / "xserver-state.json"
    plan = build_moba_x_server_plan(
        display=":11",
        system="linux",
        which=lambda name: "/usr/bin/Xorg" if name == "Xorg" else None,
        display_probe=lambda display: False,
    )
    record = start_moba_x_server(plan, dry_run=True, state_path=state_path)

    assert record.state == "dry-run"
    assert record.pid is None
    assert not state_path.exists()


def test_moba_x_server_status_includes_lifecycle_record(tmp_path) -> None:
    state_path = tmp_path / "xserver-state.json"
    plan = build_moba_x_server_plan(
        display=":12",
        system="linux",
        which=lambda name: "/usr/bin/Xvfb" if name == "Xvfb" else None,
        display_probe=lambda display: False,
    )
    start_moba_x_server(
        plan,
        state_path=state_path,
        popen_factory=lambda command, env: _FakeProcess(pid=5252),
    )
    status = build_moba_x_server_status(
        display=":12",
        system="linux",
        which=lambda name: "/usr/bin/Xvfb" if name == "Xvfb" else None,
        display_probe=lambda display: False,
        state_path=state_path,
        pid_probe=lambda pid: pid == 5252,
    )

    assert status.lifecycle is not None
    assert status.lifecycle.pid == 5252
    assert status.lifecycle.running is True


def test_x11_stop_cli_command_is_registered() -> None:
    args = build_parser().parse_args(["x11", "stop", "--json"])

    assert args.func.__name__ == "cmd_x11_stop"


def test_moba_x_server_smoke_reports_unavailable_without_runtime_or_probe(tmp_path: Path) -> None:
    evidence = run_moba_x_server_smoke(
        display=":13",
        system="windows",
        which=lambda name: None,
        display_probe=lambda display: False,
        state_path=tmp_path / "missing-state.json",
    )

    assert evidence.passed is False
    assert evidence.status == "unavailable"
    assert evidence.probe_command == []
    assert any("No X11 probe command" in note for note in evidence.notes or [])


def test_moba_x_server_smoke_runs_custom_probe_and_writes_evidence(tmp_path: Path) -> None:
    evidence = run_moba_x_server_smoke(
        display=":14",
        system="linux",
        which=lambda name: "/usr/bin/Xvfb" if name == "Xvfb" else None,
        display_probe=lambda display: True,
        probe_command="xdpyinfo -display :14",
        runner=lambda command, **kwargs: _FakeCompletedProcess(0, "screen #0\n", ""),
    )
    out = tmp_path / "x11-smoke.json"
    written = write_moba_x_server_smoke_evidence(evidence, out)
    payload = json.loads(out.read_text(encoding="utf-8"))

    assert written.passed is True
    assert written.status == "passed"
    assert written.returncode == 0
    assert written.evidence_sha256
    assert payload["evidence_sha256"] == written.evidence_sha256
    assert payload["probe_command"] == ["xdpyinfo", "-display", ":14"]


def test_x11_smoke_cli_command_is_registered() -> None:
    args = build_parser().parse_args(["x11", "smoke", "--display", ":9", "--json"])

    assert args.func.__name__ == "cmd_x11_smoke"


def test_x11_package_and_evidence_cli_commands_are_registered() -> None:
    package = build_parser().parse_args(["x11", "package-status", "--json"])
    bundle = build_parser().parse_args(
        ["x11", "bundle-runtime", "--out", "bundle", "--runtime", "xvfb", "--system", "linux", "--json"]
    )
    verify = build_parser().parse_args(["x11", "evidence-verify", "--evidence", "x11-release.json", "--json"])

    assert package.func.__name__ == "cmd_x11_package_status"
    assert bundle.func.__name__ == "cmd_x11_bundle_runtime"
    assert verify.func.__name__ == "cmd_x11_evidence_verify"


def test_moba_x_server_release_evidence_requires_packaged_runtime_and_forwarded_gui(
    tmp_path: Path,
) -> None:
    runtime = tmp_path / "xserver" / "bin" / "Xvfb"
    runtime.parent.mkdir(parents=True)
    runtime.write_bytes(b"fake-xvfb-runtime")
    smoke = tmp_path / "x11-smoke.json"
    smoke.write_text(json.dumps({"passed": True, "display": ":16"}), encoding="utf-8")
    screenshot = tmp_path / "xclock.png"
    screenshot.write_bytes(b"fake-png")
    evidence = tmp_path / "moba-xserver-release.json"
    evidence.write_text(
        json.dumps(
            {
                "schema": "row.moba-xserver.release-evidence.v1",
                "release_target": "linux-x64",
                "platform": "linux",
                "display": ":16",
                "runtime": {
                    "key": "xvfb",
                    "source": "packaged",
                    "bundled": True,
                    "executable": "xserver/bin/Xvfb",
                    "sha256": _sha256(runtime),
                },
                "smoke": {
                    "passed": True,
                    "status": "passed",
                    "evidence_file": "x11-smoke.json",
                    "evidence_sha256": _sha256(smoke),
                },
                "forwarded_gui_app": {
                    "status": "passed",
                    "command": "xclock",
                    "x11_forwarding": "trusted",
                    "window_observed": True,
                    "screenshot": "xclock.png",
                    "screenshot_sha256": _sha256(screenshot),
                },
            }
        ),
        encoding="utf-8",
    )

    result = validate_moba_x_server_release_evidence(evidence, assets_dir=tmp_path)

    assert result.passed is True
    assert result.errors == []
    assert result.summary["runtime_key"] == "xvfb"
    assert result.summary["forwarded_gui_command"] == "xclock"


def test_moba_x_server_release_evidence_rejects_host_only_runtime(tmp_path: Path) -> None:
    runtime = tmp_path / "Xvfb"
    runtime.write_bytes(b"host-runtime")
    smoke = tmp_path / "x11-smoke.json"
    smoke.write_text(json.dumps({"passed": True, "display": ":17"}), encoding="utf-8")
    screenshot = tmp_path / "xclock.png"
    screenshot.write_bytes(b"fake-png")
    evidence = tmp_path / "moba-xserver-release.json"
    payload = {
        "schema": "row.moba-xserver.release-evidence.v1",
        "release_target": "linux-x64",
        "platform": "linux",
        "display": ":17",
        "runtime": {
            "key": "xvfb",
            "source": "PATH",
            "bundled": False,
            "executable": "Xvfb",
            "sha256": _sha256(runtime),
        },
        "smoke": {
            "passed": True,
            "status": "passed",
            "evidence_file": "x11-smoke.json",
            "evidence_sha256": _sha256(smoke),
        },
        "forwarded_gui_app": {
            "status": "passed",
            "command": "xclock",
            "x11_forwarding": "trusted",
            "window_observed": True,
            "screenshot": "xclock.png",
            "screenshot_sha256": _sha256(screenshot),
        },
    }
    evidence.write_text(json.dumps(payload), encoding="utf-8")

    result = validate_moba_x_server_release_evidence(evidence, assets_dir=tmp_path)

    assert result.passed is False
    assert "runtime.source must be bundled or packaged" in result.errors
    assert "runtime.bundled must be true" in "\n".join(result.errors)


class _FakeProcess:
    def __init__(self, pid: int) -> None:
        self.pid = pid


class _FakeCompletedProcess:
    def __init__(self, returncode: int, stdout: str, stderr: str) -> None:
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

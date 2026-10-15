from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import time

import pytest

from remote_ops_workspace import launcher, terminal, windows_conpty
from remote_ops_workspace.models import Profile


@pytest.mark.parametrize("display,xauth", [(None, None), (":8", "private xauth.exe")])
def test_ssh_x11_plan_forwards_managed_authority_without_mutating_parent(monkeypatch, display, xauth) -> None:
    managed = []
    opened = []
    if display is None:
        monkeypatch.delenv("DISPLAY", raising=False)
    else:
        monkeypatch.setenv("DISPLAY", display)
    monkeypatch.setenv("ROW_ENV_PARENT_SENTINEL", "unchanged")
    monkeypatch.delenv("XAUTHORITY", raising=False)
    monkeypatch.setattr(launcher, "managed_x11_environment", lambda value: managed.append(value) or {"DISPLAY": value, "XAUTHORITY": "private authority path"})
    monkeypatch.setattr(launcher, "managed_xauth_location", lambda: xauth)
    monkeypatch.setattr(launcher.subprocess, "Popen", lambda command, **kwargs: opened.append((command, kwargs)))
    profile = Profile(name="X11 session", protocol="ssh", host="example.invalid", options={"x11": "trusted"})

    plan = launcher.launch(profile)
    pane = terminal.terminal_plan_for_profile(profile)

    assert "-Y" in plan.command
    assert ('XAuthLocation="private xauth.exe"' in plan.command) is (xauth is not None)
    assert managed == [display or ":0", display or ":0"]
    assert plan.environment == pane.environment == {"DISPLAY": display or ":0", "XAUTHORITY": "private authority path"}
    assert pane.environment is not plan.environment
    assert opened[0][1]["env"]["ROW_ENV_PARENT_SENTINEL"] == "unchanged"
    assert opened[0][1]["env"]["XAUTHORITY"] == "private authority path"
    assert os.environ.get("DISPLAY") == display
    assert "XAUTHORITY" not in os.environ


def test_real_openssh_parser_preserves_xauth_location_with_spaces(monkeypatch) -> None:
    executable = shutil.which("ssh")
    if executable is None:
        pytest.skip("OpenSSH is not installed")
    location = r"C:\Program Files\VcXsrv\xauth.exe"
    monkeypatch.setattr(launcher, "managed_xauth_location", lambda: location)
    plan = launcher.build_launch_plan(Profile(name="X11", protocol="ssh", host="example.invalid", options={"x11": "true"}))
    result = subprocess.run([executable, "-G", "-F", os.devnull, *plan.command[1:]], capture_output=True, text=True, check=False)
    assert result.returncode == 0, result.stderr
    assert f"xauthlocation {location}" in result.stdout.splitlines()


@pytest.mark.parametrize("display", ["127.0.0.1:0.0", "localhost:10.0", "[::1]:11.0", "/private/tmp/com.apple.launchd.ABC/org.xquartz:0"])
def test_launcher_and_terminal_preserve_external_client_display_authority(monkeypatch, tmp_path, display) -> None:
    authority = str(tmp_path / "external authority")
    monkeypatch.setenv("ROW_HOME", str(tmp_path / "workspace"))
    monkeypatch.setenv("DISPLAY", display)
    monkeypatch.setenv("XAUTHORITY", authority)
    profile = Profile(name="forwarded X11", protocol="ssh", host="example.invalid", options={"x11": "true"})
    plan = launcher.build_launch_plan(profile)
    pane = terminal.terminal_plan_for_profile(profile)
    assert plan.environment == pane.environment == {"DISPLAY": display, "XAUTHORITY": authority}
    assert os.environ["DISPLAY"] == display
    assert os.environ["XAUTHORITY"] == authority


def test_unicode_environment_block_is_sorted_terminated_and_case_insensitive() -> None:
    env = {"=C:": "C:/drive directory", "z": "last", "PATH": "first", "path": "replacement", "XAUTHORITY": "C:/private/ü authority"}
    process = windows_conpty.WindowsConPtyProcess(["cmd.exe"], env=env)
    assert process._environment_block == "=C:=C:/drive directory\0path=replacement\0XAUTHORITY=C:/private/ü authority\0z=last\0\0"
    env["z"] = "mutated after constructor"
    assert process._environment_block.endswith("z=last\0\0")
    assert windows_conpty._windows_environment_block({}) == "\0\0"


@pytest.mark.parametrize("environment", [{"": "value"}, {"a=b": "value"}, {"a\0": "value"}, {"key": "bad\0value"}, {1: "value"}, {"key": 1}, {"=AB:": "value"}, {"=é:": "value"}, {"=C:bad": "value"}, {"=C:": "bad\0value"}])
def test_invalid_environment_cannot_truncate_or_inject_native_block(environment) -> None:
    with pytest.raises(ValueError, match="environment keys and values"):
        windows_conpty.WindowsConPtyProcess(["cmd.exe"], env=environment)


@pytest.fixture
def qt_application():
    qt = pytest.importorskip("PyQt6.QtWidgets")
    application = qt.QApplication.instance() or qt.QApplication(["x11-environment-regression"])
    return application


@pytest.mark.parametrize("backend", ["QtHiddenProcess", "QtConPtyProcess"])
def test_qt_process_environment_reaches_real_child_and_keeps_parent_unchanged(qt_application, monkeypatch, backend) -> None:
    from PyQt6.QtCore import QProcess, QProcessEnvironment

    from remote_ops_workspace import qt_terminal_process

    if backend == "QtConPtyProcess" and not windows_conpty.conpty_support().supported:
        pytest.skip(windows_conpty.conpty_support().reason)
    monkeypatch.setenv("ROW_ENV_PARENT_SENTINEL", "unchanged")
    monkeypatch.delenv("XAUTHORITY", raising=False)
    environment = QProcessEnvironment.systemEnvironment()
    environment.insert("DISPLAY", ":77")
    environment.insert("XAUTHORITY", "C:/private/ü authority")
    if os.name == "nt":
        environment.insert("=C:", os.getcwd())
    process = getattr(qt_terminal_process, backend)()
    process.setProcessEnvironment(environment)
    environment.insert("XAUTHORITY", "later mutation")
    process.setProgram(sys.executable)
    process.setArguments(["-u", "-c", "import json,os;print('ROW_ENV=' + json.dumps([os.environ.get(k) for k in ['DISPLAY','XAUTHORITY','ROW_ENV_PARENT_SENTINEL']]), flush=True)"])
    output = bytearray()
    errors = []
    completed = []
    process.readyReadStandardOutput.connect(lambda: output.extend(process.readAllStandardOutput()))
    process.errorOccurred.connect(errors.append)
    process.finished.connect(lambda code, _status: completed.append(code))
    try:
        process.start()
        deadline = time.monotonic() + 8
        while not completed and time.monotonic() < deadline:
            qt_application.processEvents()
            time.sleep(0.01)
        output.extend(process.readAllStandardOutput())
        assert errors == [], process.errorString()
        assert completed == [0]
        assert process.state() == QProcess.ProcessState.NotRunning
        expected = json.dumps([":77", "C:/private/ü authority", "unchanged"]).encode()
        assert b"ROW_ENV=" + expected in output
        assert "XAUTHORITY" not in os.environ
        assert os.environ["ROW_ENV_PARENT_SENTINEL"] == "unchanged"
    finally:
        process.close()


def test_gui_terminal_inserts_plan_environment_into_selected_process(qt_application, monkeypatch, tmp_path) -> None:
    from remote_ops_workspace import gui

    monkeypatch.setenv("ROW_HOME", str(tmp_path / "workspace"))
    monkeypatch.setenv("ROW_ENV_PARENT_SENTINEL", "unchanged")
    monkeypatch.delenv("XAUTHORITY", raising=False)
    _app, window = gui.create_main_window(["x11-terminal-regression"], show=False)
    plan = terminal.TerminalPanePlan(title="X11", command=[sys.executable, "-c", "pass"], environment={"DISPLAY": ":77", "XAUTHORITY": "private authority path"})
    pane = window.new_terminal_pane(plan, autostart=False)
    captured = []
    monkeypatch.setattr(pane.process, "setProcessEnvironment", lambda env: captured.append({key: env.value(key) for key in env.keys()}))
    monkeypatch.setattr(pane.process, "start", lambda: None)
    try:
        pane.start()
        assert captured[0]["DISPLAY"] == ":77"
        assert captured[0]["XAUTHORITY"] == "private authority path"
        assert captured[0]["ROW_ENV_PARENT_SENTINEL"] == "unchanged"
        assert "XAUTHORITY" not in os.environ
    finally:
        pane.close()
        window.close()
        qt_application.processEvents()

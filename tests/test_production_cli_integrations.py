from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from remote_ops_workspace import cli, gui, gui_smoke


def test_managed_server_and_x11_start_forward_security_options(monkeypatch, tmp_path) -> None:
    calls = []
    record = SimpleNamespace(to_dict=lambda: {"state": "planned"})
    plan = SimpleNamespace(to_dict=lambda: {"command": ["safe-helper"]})
    monkeypatch.setattr(cli, "build_moba_server_plan", lambda service, **kwargs: calls.append((service, kwargs)) or plan)
    monkeypatch.setattr(cli, "start_moba_server", lambda _plan, **_kwargs: record)
    monkeypatch.setattr(cli, "build_moba_x_server_plan", lambda **kwargs: calls.append(("x11", kwargs)) or plan)
    monkeypatch.setattr(cli, "start_moba_x_server", lambda _plan, **_kwargs: record)
    authority = tmp_path / "private authority"
    assert cli.main(["servers", "start", "ftp", "--require-tls", "--hardening-profile", "tls-authenticated", "--dry-run", "--json"]) == 0
    assert calls[0] == ("ftp", {"host": "127.0.0.1", "port": None, "root": None, "allow_public_bind": False, "require_tls": True, "hardening_profile": "tls-authenticated"})
    assert cli.main(["x11", "start", "--display", ":8", "--allow-tcp", "--authority-file", str(authority), "--dry-run", "--json"]) == 0
    assert calls[1] == ("x11", {"display": ":8", "allow_tcp": True, "authority_path": authority})


def test_packaged_ftp_runtime_preserves_exact_nonsecret_arguments(monkeypatch, tmp_path) -> None:
    from remote_ops_workspace import embedded_ftp

    received = []
    monkeypatch.setattr(embedded_ftp, "main", lambda argv: received.append(argv) or 7)
    assert cli.main(["servers", "_ftp-runtime", "--host", "127.0.0.1", "--port", "2121", "--root", str(tmp_path)]) == 7
    assert received == [["--host", "127.0.0.1", "--port", "2121", "--root", str(tmp_path)]]


def test_source_gui_smoke_routes_to_real_smoke_module(monkeypatch, tmp_path) -> None:
    output = tmp_path / "report.json"
    paths = []
    monkeypatch.setattr(cli, "_run_frozen_windows_gui_launcher", lambda path: paths.append(path))
    monkeypatch.setattr(gui_smoke, "run", lambda path: paths.append(path) or 6)
    assert cli.main(["gui", "--smoke-json", str(output)]) == 6
    assert paths == [output, output]
    args = []
    monkeypatch.setattr(gui_smoke, "main", lambda argv: args.append(argv) or 8)
    monkeypatch.setattr(gui.sys, "argv", ["row-gui.exe", "--smoke-json", str(output)])
    assert gui.main() == 8
    assert args == [["--out", str(output)]]


def test_frozen_gui_smoke_uses_packaged_gui_entrypoint(monkeypatch, tmp_path) -> None:
    commands = []
    output = tmp_path / "report.json"
    monkeypatch.setattr(cli, "os", SimpleNamespace(name="nt"))
    monkeypatch.setattr(cli.sys, "frozen", True, raising=False)
    monkeypatch.setattr(cli.sys, "executable", str(tmp_path / "row.exe"))
    monkeypatch.setattr(Path, "exists", lambda _path: True)
    monkeypatch.setattr(cli.subprocess, "run", lambda command, **kwargs: commands.append((command, kwargs)) or SimpleNamespace(returncode=9))
    assert cli.cmd_gui(SimpleNamespace(smoke_json=output)) == 9
    assert commands == [([str(tmp_path / "row-gui.exe"), "--smoke-json", str(output)], {"check": False})]

from __future__ import annotations

from types import SimpleNamespace

import remote_ops_workspace.cli as cli_module
import remote_ops_workspace.doctor as doctor_module
from remote_ops_workspace.doctor import DoctorResult, run_doctor


def test_doctor_marks_sshv1_as_legacy_opt_in(monkeypatch) -> None:
    monkeypatch.setattr(
        doctor_module.shutil,
        "which",
        lambda candidate: f"/mock/{candidate}" if candidate == "ssh" else None,
    )

    result = run_doctor()

    assert result.executables["ssh1"]["ssh"] is True
    assert result.executables["sshv1"]["ssh"] is True
    assert result.protocol_status["ssh"]["status"] == "available"
    assert result.protocol_status["ssh"]["launchable_by_default"] is True
    for protocol in ("ssh1", "sshv1"):
        status = result.protocol_status[protocol]
        assert status["status"] == "legacy-insecure-opt-in"
        assert status["client_present"] is True
        assert status["launchable_by_default"] is False
        assert status["requires_profile_opt_in"] is True
        assert "allow_insecure_sshv1=true" in status["summary"]
        assert any("protocol v1" in note for note in status["notes"])


def test_doctor_cli_prints_sshv1_legacy_status(monkeypatch, capsys) -> None:
    result = DoctorResult(
        platform="Windows 11 (AMD64)",
        python="3.14.5",
        data_dir="C:/row",
        executables={
            "ssh": {"ssh": True},
            "ssh1": {"ssh": True},
            "sshv1": {"ssh": True},
        },
        protocol_status={
            "ssh": {
                "status": "available",
                "client_present": True,
                "launchable_by_default": True,
                "requires_profile_opt_in": False,
                "available_clients": ["ssh"],
                "summary": "ssh",
                "notes": [],
            },
            "ssh1": {
                "status": "legacy-insecure-opt-in",
                "client_present": True,
                "launchable_by_default": False,
                "requires_profile_opt_in": True,
                "available_clients": ["ssh"],
                "summary": (
                    "legacy-insecure-opt-in: ssh; requires allow_insecure_sshv1=true; "
                    "protocol v1 support is not verified"
                ),
                "notes": [],
            },
            "sshv1": {
                "status": "legacy-insecure-opt-in",
                "client_present": True,
                "launchable_by_default": False,
                "requires_profile_opt_in": True,
                "available_clients": ["ssh"],
                "summary": (
                    "legacy-insecure-opt-in: ssh; requires allow_insecure_sshv1=true; "
                    "protocol v1 support is not verified"
                ),
                "notes": [],
            },
        },
    )
    monkeypatch.setattr(cli_module, "run_doctor", lambda: result)

    assert cli_module.cmd_doctor(SimpleNamespace(json=False)) == 0

    output = capsys.readouterr().out
    assert "ssh      ssh" in output
    assert "ssh1     legacy-insecure-opt-in" in output
    assert "sshv1    legacy-insecure-opt-in" in output
    assert "allow_insecure_sshv1=true" in output
    assert "ssh1     ssh\n" not in output

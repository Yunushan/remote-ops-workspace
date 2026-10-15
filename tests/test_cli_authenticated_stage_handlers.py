"""Exercise actual CLI command functions under explicit policy and operation mocks."""
from __future__ import annotations

import argparse
import json

import pytest

from remote_ops_workspace import cli
from remote_ops_workspace import update_channel as channel


@pytest.mark.parametrize("recover", [False, True])
@pytest.mark.parametrize("as_json", [False, True])
def test_authenticated_stage_commands_route_selected_operation_and_report_no_install(monkeypatch, capsys, recover, as_json):
    marker, calls = object(), []
    monkeypatch.setattr(channel, "load_update_policy", lambda path: calls.append(("policy", path)) or marker)
    monkeypatch.setattr(cli, "data_dir", lambda: "synthetic-current-home")

    def operation(policy, root, *, current_home):
        calls.append(("operation", policy, root, current_home))
        return {"phase": "authenticated-staged", "version": "1.0.28", "artifact_count": 2, "install_permitted": False}

    def unselected(*_args, **_kwargs):
        pytest.fail("CLI selected the wrong staging operation")

    monkeypatch.setattr(channel, "recover_update" if recover else "stage_update", operation)
    monkeypatch.setattr(channel, "stage_update" if recover else "recover_update", unselected)
    args = argparse.Namespace(policy="explicit-policy", stage="explicit-stage", json=as_json)
    handler = cli.cmd_customizer_update_stage_recover if recover else cli.cmd_customizer_update_stage
    assert handler(args) == 0
    output = capsys.readouterr()
    assert output.err == ""
    if as_json:
        assert json.loads(output.out) == {"phase": "authenticated-staged", "version": "1.0.28",
                                          "artifact_count": 2, "install_permitted": False}
    else:
        assert output.out.splitlines() == ["Authenticated update staged: 1.0.28 (2 assets)",
                                          "Installation is not permitted by the staging command."]
    assert calls == [("policy", "explicit-policy"), ("operation", marker, "explicit-stage", "synthetic-current-home")]


@pytest.mark.parametrize("as_json", [False, True])
def test_authenticated_stage_policy_refusal_does_not_start_operation(monkeypatch, capsys, as_json):
    def refuse(_path):
        raise channel.UpdateError("update-policy-not-enabled")

    monkeypatch.setattr(channel, "load_update_policy", refuse)
    monkeypatch.setattr(channel, "stage_update", lambda *_args, **_kwargs: pytest.fail("refused policy started staging"))
    monkeypatch.setattr(cli, "data_dir", lambda: pytest.fail("refused policy inspected current home"))
    assert cli.cmd_customizer_update_stage(argparse.Namespace(policy="policy", stage="stage", json=as_json)) == 1
    output = capsys.readouterr()
    if as_json:
        assert json.loads(output.out) == {"phase": "refused", "refusal": "update-policy-not-enabled", "install_permitted": False}
        assert output.err == ""
    else:
        assert output.out == "" and output.err == "Update staging refused: update-policy-not-enabled\n"


@pytest.mark.parametrize("error_type", [OSError, ValueError, RecursionError])
@pytest.mark.parametrize("recover", [False, True])
def test_authenticated_stage_cli_hides_input_or_operation_exception_details(monkeypatch, capsys, error_type, recover):
    marker = object()
    monkeypatch.setattr(channel, "load_update_policy", lambda _path: marker)
    monkeypatch.setattr(cli, "data_dir", lambda: "synthetic-home")

    def refuse(_policy, _root, *, current_home):
        assert current_home == "synthetic-home"
        raise error_type("SECRET untrusted input and private filesystem detail")

    monkeypatch.setattr(channel, "recover_update" if recover else "stage_update", refuse)
    handler = cli.cmd_customizer_update_stage_recover if recover else cli.cmd_customizer_update_stage
    assert handler(argparse.Namespace(policy="policy", stage="stage", json=True)) == 1
    output = capsys.readouterr()
    assert output.err == "" and "SECRET" not in output.out
    assert json.loads(output.out) == {"phase": "refused", "refusal": "update-stage-input-refused", "install_permitted": False}

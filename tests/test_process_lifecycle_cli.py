from __future__ import annotations

import pytest

from remote_ops_workspace import cli
from remote_ops_workspace.process_status import ProcessIdentityError, ProcessStatusError


@pytest.mark.parametrize("command,handler", [
    (["servers", "stop", "http"], "stop_moba_server"),
    (["x11", "stop"], "stop_moba_x_server"),
])
@pytest.mark.parametrize("error", [
    ProcessIdentityError("saved helper identity does not match the current process"),
    ProcessStatusError("native process identity could not be verified"),
    TimeoutError("managed process did not exit before the shutdown deadline"),
])
def test_verified_shutdown_failure_is_reported_at_cli_boundary(command, handler, error, monkeypatch, capsys):
    calls = []

    def refuse(*args, **kwargs):
        calls.append((args, kwargs))
        raise error

    monkeypatch.setattr(cli, handler, refuse)
    assert cli.main(command) == 1
    assert len(calls) == 1
    output = capsys.readouterr()
    assert output.out == ""
    assert output.err == f"error: {error}\n"

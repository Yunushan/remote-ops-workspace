from __future__ import annotations

import pytest

from remote_ops_workspace import command_safety as safe
from remote_ops_workspace import x11


@pytest.mark.parametrize("display", [
    ":0", ":34.1", "127.0.0.1:0.0", "localhost:10.0", "workstation.example:2",
    "tcp/workstation.example:2.1", "unix/:0", "unix:0", "inet6/[::1]:0.0",
    "[fe80::1%eth0]:0", "workstation::0", "/private/tmp/com.apple.launchd.UFeDJu0S1Q/org.xquartz:0",
])
def test_external_client_display_and_authority_are_preserved(display, tmp_path, monkeypatch):
    # A display manager or SSH may own the cookie file. Preserve that selection
    # even when this ROW process cannot inspect it yet; do not replace it.
    authority = str(tmp_path / "external session" / "Xauthority")
    monkeypatch.setenv("XAUTHORITY", authority)
    assert x11.managed_x11_environment(display) == {"DISPLAY": display, "XAUTHORITY": authority}


@pytest.mark.parametrize("display", [
    "127.0.0.1:0.0", "localhost:10.0", "tcp/workstation:2", "unix/:0", "workstation::0",
    "/private/tmp/com.apple.launchd.UFeDJu0S1Q/org.xquartz:0",
])
def test_external_client_display_does_not_inherit_unrelated_managed_cookie(display, tmp_path, monkeypatch):
    monkeypatch.delenv("XAUTHORITY", raising=False)
    monkeypatch.setenv("ROW_HOME", str(tmp_path))
    authority = tmp_path / "x11" / "Xauthority-0"
    authority.parent.mkdir()
    authority.write_bytes(b"unrelated managed cookie")
    assert x11.managed_x11_environment(display) == {"DISPLAY": display}


@pytest.mark.parametrize("display", [
    "localhost", ":abc", "localhost:1.bad", " localhost:1", "localhost:1 ",
    "localhost:1\nXAUTHORITY=attacker", "localhost:1\x00", "host name:1", "-option:1",
    "localhost:1;calc", "$(calc):1", "host:1.2.3", "[]:1", "tcp/host:bad",
])
def test_client_display_rejects_malformed_or_injected_values(display, monkeypatch):
    monkeypatch.delenv("XAUTHORITY", raising=False)
    with pytest.raises(safe.CommandSafetyError):
        x11.managed_x11_environment(display)


def test_client_authority_rejects_control_characters(monkeypatch):
    monkeypatch.setenv("XAUTHORITY", "cookie\nDISPLAY=attacker:1")
    with pytest.raises(safe.CommandSafetyError, match="control"):
        x11.managed_x11_environment("localhost:10.0")


def test_empty_client_display_uses_managed_default(tmp_path, monkeypatch):
    monkeypatch.delenv("XAUTHORITY", raising=False)
    monkeypatch.setenv("ROW_HOME", str(tmp_path))
    assert x11.managed_x11_environment("") == {"DISPLAY": ":0"}


@pytest.mark.parametrize("display", ["127.0.0.1:0.0", "localhost:10.0", "tcp/host:1"])
def test_managed_server_display_remains_narrow(display):
    with pytest.raises(safe.CommandSafetyError, match="start with"):
        x11.build_moba_x_server_plan(display, system="linux", which=lambda _name: None)

from remote_ops_workspace.gui_editors import (
    format_layout_panes_text,
    format_tunnels_text,
    layout_from_editor_data,
    layout_to_editor_data,
    parse_key_value_text,
    profile_from_editor_data,
    profile_to_editor_data,
    protocol_preset_editor_data,
)
from remote_ops_workspace.layouts import Layout, LayoutPane
from remote_ops_workspace.models import Profile, Tunnel


def test_profile_editor_data_roundtrip_builds_profile() -> None:
    profile = profile_from_editor_data(
        {
            "name": "edge",
            "protocol": "ssh",
            "host": "192.0.2.10",
            "port": "2222",
            "username": "admin",
            "group": "prod",
            "tags": "ssh, prod, ssh",
            "description": "Production edge",
            "path": "",
            "url": "",
            "command": "",
            "identity_file": "/home/me/.ssh/id_ed25519",
            "credential_ref": "prod/edge",
            "options": "proxy_jump=bastion\nkeepalive_interval=30\n",
            "tunnels": "dynamic:1080\nlocal:15432:127.0.0.1:5432",
        }
    )

    assert profile.name == "edge"
    assert profile.protocol == "ssh"
    assert profile.port == 2222
    assert profile.tags == ["ssh", "prod"]
    assert profile.options["proxy_jump"] == "bastion"
    assert profile.options["keepalive_interval"] == "30"
    assert profile.tunnels[0].mode == "dynamic"
    assert profile.tunnels[1].remote_port == 5432

    data = profile_to_editor_data(profile)
    assert data["port"] == "2222"
    assert "proxy_jump=bastion" in data["options"]
    assert "dynamic:1080" in data["tunnels"]


def test_profile_editor_data_formats_existing_profile() -> None:
    profile = Profile(
        name="desk",
        protocol="rdp",
        host="192.0.2.20",
        port=3389,
        group="windows",
        tags=["rdp"],
        options={"geometry": "1600x900"},
        tunnels=[Tunnel(mode="dynamic", local_port=1080)],
    )

    data = profile_to_editor_data(profile)

    assert data["name"] == "desk"
    assert data["options"] == "geometry=1600x900"
    assert data["tunnels"] == "dynamic:1080"


def test_protocol_preset_editor_data_uses_safe_protocol_defaults() -> None:
    assert protocol_preset_editor_data("ssh") == {
        "port": "22",
        "options": "strict_host_key_checking=accept-new",
    }
    assert protocol_preset_editor_data("rdp")["port"] == "3389"
    assert "baud=115200" in protocol_preset_editor_data("serial")["options"]
    assert protocol_preset_editor_data("unknown") == {}


def test_profile_editor_rejects_bad_options_and_tunnels() -> None:
    try:
        parse_key_value_text("not-an-option")
    except ValueError as exc:
        assert "key=value" in str(exc)
    else:
        raise AssertionError("bad option editor text should be rejected")

    try:
        profile_from_editor_data(
            {
                "name": "edge",
                "protocol": "ssh",
                "host": "192.0.2.10",
                "port": "",
                "tunnels": "local:not-a-port:127.0.0.1:5432",
            }
        )
    except ValueError as exc:
        assert "integer" in str(exc)
    else:
        raise AssertionError("bad tunnel editor text should be rejected")


def test_layout_editor_roundtrip_with_titles() -> None:
    layout = layout_from_editor_data(
        {
            "name": "triage",
            "orientation": "horizontal",
            "description": "Ops triage",
            "panes": "profile:edge | Edge\ncommand:python -V | Version",
        }
    )

    assert layout.name == "triage"
    assert layout.orientation == "horizontal"
    assert layout.panes[0].profile == "edge"
    assert layout.panes[0].title == "Edge"
    assert layout.panes[1].command == "python -V"
    assert layout.panes[1].title == "Version"

    data = layout_to_editor_data(layout)
    assert "profile:edge | Edge" in data["panes"]
    assert "command:python -V | Version" in data["panes"]


def test_layout_editor_formats_panes() -> None:
    text = format_layout_panes_text(
        [LayoutPane(profile="edge", title="Edge"), LayoutPane(command="uptime", title="Uptime")]
    )
    assert text == "profile:edge | Edge\ncommand:uptime | Uptime"

    tunnel_text = format_tunnels_text([Tunnel(mode="local", local_port=8080, remote_host="127.0.0.1", remote_port=80)])
    assert tunnel_text == "local:8080:127.0.0.1:80"


def test_layout_editor_rejects_empty_layout() -> None:
    try:
        layout_from_editor_data({"name": "empty", "orientation": "grid", "panes": "", "description": ""})
    except ValueError as exc:
        assert "at least one pane" in str(exc)
    else:
        raise AssertionError("empty GUI layout editor data should be rejected")


def test_layout_to_editor_data_defaults() -> None:
    assert profile_to_editor_data()["protocol"] == "ssh"
    assert layout_to_editor_data()["orientation"] == "grid"
    assert layout_to_editor_data(Layout(name="solo", panes=[LayoutPane(command="whoami")]))["panes"] == "command:whoami"

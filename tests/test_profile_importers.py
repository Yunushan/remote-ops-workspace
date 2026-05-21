import contextlib
import io
import os
from pathlib import Path

from remote_ops_workspace.cli import main
from remote_ops_workspace.profile_importers import detect_import_format, import_profiles
from remote_ops_workspace.storage import ProfileStore


def test_remmina_importer_maps_rdp_options(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "desk.remmina"
    source.write_text(
        "\n".join(
            [
                "[remmina]",
                "name=Prod Desktop",
                "protocol=RDP",
                "server=192.0.2.20:3390",
                "username=administrator",
                "group=prod/windows",
                "domain=LAB",
                "resolution=1600x900",
                "ignore-cert=1",
                "disableclipboard=1",
            ]
        ),
        encoding="utf-8",
    )

    result = import_profiles(source, source_format="remmina")

    assert result.source_format == "remmina"
    assert len(result.profiles) == 1
    profile = result.profiles[0]
    assert profile.name == "Prod Desktop"
    assert profile.protocol == "rdp"
    assert profile.host == "192.0.2.20"
    assert profile.port == 3390
    assert profile.username == "administrator"
    assert profile.group == "prod/windows"
    assert profile.options["domain"] == "LAB"
    assert profile.options["geometry"] == "1600x900"
    assert profile.options["cert_ignore"] == "true"
    assert profile.options["clipboard"] == "false"


def test_mremoteng_importer_maps_nested_groups_and_skips_password(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "confCons.xml"
    source.write_text(
        """<Connections>
  <Node Name="Prod" Type="Container">
    <Node Name="Edge" Type="Connection" Protocol="SSH2" Hostname="192.0.2.10" Port="2222" Username="admin" Password="secret" />
    <Node Name="Win" Type="Connection" Protocol="RDP" Hostname="192.0.2.20" Port="3389" Username="administrator" Domain="LAB" />
  </Node>
</Connections>""",
        encoding="utf-8",
    )

    result = import_profiles(source, source_format="mremoteng")

    assert [profile.name for profile in result.profiles] == ["Edge", "Win"]
    edge, win = result.profiles
    assert edge.protocol == "ssh"
    assert edge.host == "192.0.2.10"
    assert edge.port == 2222
    assert edge.group == "Prod"
    assert win.protocol == "rdp"
    assert win.options["domain"] == "LAB"
    assert any("not imported" in warning for warning in result.warnings)


def test_termius_importer_maps_host_json(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "termius.json"
    source.write_text(
        """{
  "hosts": [
    {
      "label": "Bastion",
      "address": "192.0.2.30",
      "port": 22,
      "username": "ops",
      "group": {"name": "prod"},
      "tags": ["ssh", "bastion"],
      "identityFile": "/home/me/.ssh/id_ed25519"
    },
    {
      "label": "Mobile Shell",
      "address": "192.0.2.31",
      "protocol": "mosh",
      "mosh_port": "60000:60010"
    }
  ]
}""",
        encoding="utf-8",
    )

    result = import_profiles(source, source_format="termius")

    bastion, mobile = result.profiles
    assert bastion.name == "Bastion"
    assert bastion.protocol == "ssh"
    assert bastion.identity_file == "/home/me/.ssh/id_ed25519"
    assert bastion.group == "prod"
    assert "bastion" in bastion.tags
    assert mobile.protocol == "mosh"
    assert mobile.options["mosh_port"] == "60000:60010"


def test_mobaxterm_importer_maps_percent_session(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    source = tmp_path / "sessions.mxtsessions"
    source.write_text(
        "\n".join(
            [
                "[Bookmarks]",
                "SubRep=prod",
                "Edge SSH=#109#0%192.0.2.40%2222%admin%%%%",
            ]
        ),
        encoding="utf-8",
    )

    result = import_profiles(source, source_format="mobaxterm")

    assert len(result.profiles) == 1
    profile = result.profiles[0]
    assert profile.name == "Edge SSH"
    assert profile.protocol == "ssh"
    assert profile.host == "192.0.2.40"
    assert profile.port == 2222
    assert profile.username == "admin"
    assert profile.group == "prod"


def test_import_auto_detects_row_and_external_formats(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    row = tmp_path / "bundle.json"
    row.write_text('{"version": 1, "profiles": []}', encoding="utf-8")
    remmina = tmp_path / "desk.remmina"
    remmina.write_text("[remmina]\nname=desk\nprotocol=RDP\nserver=192.0.2.20\n", encoding="utf-8")
    xml = tmp_path / "confCons.xml"
    xml.write_text("<Connections />", encoding="utf-8")

    assert detect_import_format(row) == "row"
    assert detect_import_format(remmina) == "remmina"
    assert detect_import_format(xml) == "mremoteng"


def test_cli_import_external_profile_uses_store(tmp_path: Path) -> None:
    tmp_path.mkdir(parents=True, exist_ok=True)
    row_home = tmp_path / "row-home"
    source = tmp_path / "desk.remmina"
    source.write_text("[remmina]\nname=desk\nprotocol=RDP\nserver=192.0.2.20\n", encoding="utf-8")
    old_home = os.environ.get("ROW_HOME")
    os.environ["ROW_HOME"] = str(row_home)
    try:
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            assert main(["import", "--in", str(source), "--format", "auto"]) == 0
        assert "imported profiles: 1" in stdout.getvalue()
        profile = ProfileStore(row_home / "profiles.json").get("desk")
    finally:
        if old_home is None:
            os.environ.pop("ROW_HOME", None)
        else:
            os.environ["ROW_HOME"] = old_home
    assert profile.protocol == "rdp"
    assert profile.host == "192.0.2.20"

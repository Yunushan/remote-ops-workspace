from __future__ import annotations

import json
from pathlib import Path

import pytest

import remote_ops_workspace.profile_importers as importers
from remote_ops_workspace.models import Profile
from remote_ops_workspace.storage import ProfileStore


def test_import_profiles_rejects_invalid_inputs(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source = tmp_path / "profiles.json"
    source.write_text('{"profiles": []}', encoding="utf-8")

    with pytest.raises(ValueError, match="unsupported import format"):
        importers.import_profiles(source, source_format="unknown")
    with pytest.raises(ValueError, match="does not exist"):
        importers.import_profiles(tmp_path / "missing.json")
    with pytest.raises(ValueError, match="no profiles found"):
        importers.import_profiles(source, source_format="row")

    monkeypatch.setattr(importers, "detect_import_format", lambda _path: "unexpected")
    with pytest.raises(ValueError, match="unsupported import format: unexpected"):
        importers.import_profiles(source)


def test_import_profiles_into_explicit_store_replaces_existing_profile(tmp_path: Path) -> None:
    source = tmp_path / "profiles.json"
    source.write_text(
        json.dumps({"profiles": [{"name": "edge", "protocol": "ssh", "host": "new.example"}]}),
        encoding="utf-8",
    )
    store = ProfileStore(tmp_path / "stored.json")
    store.add(Profile(name="edge", protocol="ssh", host="old.example"))

    result = importers.import_profiles_into_store(source, store, source_format="row", replace=True)

    assert result.profiles[0].host == "new.example"
    assert store.get("edge").host == "new.example"


def test_detect_import_format_for_directories(tmp_path: Path) -> None:
    remmina_dir = tmp_path / "remmina"
    remmina_dir.mkdir()
    (remmina_dir / "desk.remmina").write_text("[remmina]", encoding="utf-8")
    assert importers.detect_import_format(remmina_dir) == "remmina"

    moba_dir = tmp_path / "moba"
    moba_dir.mkdir()
    (moba_dir / "sessions.mxtsessions").write_text("[Bookmarks]", encoding="utf-8")
    assert importers.detect_import_format(moba_dir) == "mobaxterm"

    ini_dir = tmp_path / "moba-ini"
    ini_dir.mkdir()
    (ini_dir / "MobaXterm.ini").write_text("[Bookmarks]", encoding="utf-8")
    assert importers.detect_import_format(ini_dir) == "mobaxterm"

    unknown = tmp_path / "unknown"
    unknown.mkdir()
    with pytest.raises(ValueError, match="cannot auto-detect"):
        importers.detect_import_format(unknown)


@pytest.mark.parametrize(
    ("name", "content", "expected"),
    [
        ("sessions.ini", "[Bookmarks]\nentry=value", "mobaxterm"),
        ("termius.json", '{"hosts": []}', "termius"),
        ("row.data", '{"profiles": []}', "row"),
        ("termius.data", "[]", "termius"),
        ("connections.data", "<Connections />", "mremoteng"),
        ("desk.data", "[remmina]\nname=desk", "remmina"),
        ("moba.data", "[Bookmarks_1]\nentry=value", "mobaxterm"),
    ],
)
def test_detect_import_format_from_content(
    tmp_path: Path,
    name: str,
    content: str,
    expected: str,
) -> None:
    source = tmp_path / name
    source.write_text(content, encoding="utf-8")
    assert importers.detect_import_format(source) == expected


def test_detect_import_format_rejects_unknown_file(tmp_path: Path) -> None:
    source = tmp_path / "unknown.ini"
    source.write_text("[settings]\nvalue=1", encoding="utf-8")
    with pytest.raises(ValueError, match="cannot auto-detect"):
        importers.detect_import_format(source)


def test_remmina_import_handles_empty_web_and_headerless_files(tmp_path: Path) -> None:
    source_dir = tmp_path / "remmina"
    source_dir.mkdir()
    (source_dir / "empty.remmina").write_text("", encoding="utf-8")
    (source_dir / "web.remmina").write_text(
        "\n".join(
            (
                "name=Portal",
                "protocol=WWW",
                "url=https://portal.example/path",
                "username=operator",
            )
        ),
        encoding="utf-8",
    )

    result = importers.import_profiles(source_dir, source_format="remmina")

    assert [profile.name for profile in result.profiles] == ["Portal"]
    assert result.profiles[0].protocol == "https"
    assert result.profiles[0].host == "portal.example"
    assert importers._read_remmina_file(source_dir / "empty.remmina") == {}

    defaults_only = source_dir / "defaults.remmina"
    defaults_only.write_text("[DEFAULT]\nname=ignored", encoding="utf-8")
    assert importers._read_remmina_file(defaults_only) == {}


def test_remmina_protocol_options_cover_rdp_vnc_and_ssh() -> None:
    rdp = importers._remmina_options(
        "rdp",
        {
            "resolution": "default",
            "sharefolder": "yes",
            "sharefolder_name": "docs",
            "sharefolder_path": "/srv/docs",
        },
    )
    vnc = importers._remmina_options(
        "vnc",
        {"viewonly": "true", "quality": "9", "compression": "2"},
    )
    ssh = importers._remmina_options("ssh", {"ssh_tunnel_server": "jump.example:2222"})
    empty_vnc = importers._remmina_options("vnc", {})
    invalid_jump = importers._remmina_options("ssh", {"ssh_tunnel_server": ":22"})

    assert rdp["drive"] == "docs,/srv/docs"
    assert "geometry" not in rdp
    assert vnc == {"view_only": "true", "quality": "9", "compression": "2"}
    assert ssh == {"proxy_jump": "jump.example"}
    assert empty_vnc == {}
    assert invalid_jump == {}


def test_mremoteng_walks_non_connection_nodes_and_namespaces(tmp_path: Path) -> None:
    source = tmp_path / "connections.xml"
    source.write_text(
        """<root xmlns:x="urn:test">
  <x:Node Name="Parent" Type="Connection" Protocol="SSH2">
    <x:Node Name="Child" Type="Connection" Protocol="SSH2" Hostname="child.example" />
  </x:Node>
</root>""",
        encoding="utf-8",
    )

    result = importers.import_profiles(source, source_format="mremoteng")

    assert [profile.name for profile in result.profiles] == ["Child"]
    assert result.profiles[0].host == "child.example"


def test_termius_import_skips_non_hosts_credentials_and_missing_addresses(tmp_path: Path) -> None:
    source = tmp_path / "termius.json"
    source.write_text(
        json.dumps(
            {
                "metadata": "ignored",
                "credentials": {"name": "hidden", "address": "secret.example"},
                "hosts": [
                    {"label": "missing address", "address": "", "protocol": "ssh"},
                    {
                        "label": "Mosh",
                        "address": "mosh.example",
                        "protocol": "mosh",
                        "group": "operations",
                        "tags": "mobile",
                        "password": "not-imported",
                    },
                    {
                        "label": "Odd tags",
                        "address": "odd.example",
                        "labels": {"not": "a-list"},
                    },
                ],
            }
        ),
        encoding="utf-8",
    )

    result = importers.import_profiles(source, source_format="termius")

    assert [profile.name for profile in result.profiles] == ["Mosh", "Odd tags"]
    assert result.profiles[0].group == "operations"
    assert result.profiles[0].tags[-1] == "mobile"
    assert "mosh_port" not in result.profiles[0].options
    assert result.profiles[1].tags == ["imported", "termius"]
    assert any("not imported" in warning for warning in result.warnings)


def test_mobaxterm_directory_imports_commands_and_warns_on_secret_entries(tmp_path: Path) -> None:
    source_dir = tmp_path / "moba"
    source_dir.mkdir()
    (source_dir / "sessions.mxtsessions").write_text(
        "\n".join(
            (
                "[General]",
                "ignored=value",
                "[Bookmarks]",
                "SubRep=operations",
                "SSH command=ssh -p 2200 -i /keys/id operator@edge.example",
                "Web command=https https://portal.example:444/path",
                "password=secret-value",
                "not-a-session=hello",
            )
        ),
        encoding="utf-8",
    )
    (source_dir / "MobaXterm.ini").write_text("[General]\nsetting=1", encoding="utf-8")

    result = importers.import_profiles(source_dir, source_format="mobaxterm")

    ssh, web = result.profiles
    assert ssh.protocol == "ssh"
    assert ssh.host == "edge.example"
    assert ssh.port == 2200
    assert ssh.username == "operator"
    assert ssh.identity_file == "/keys/id"
    assert web.protocol == "https"
    assert web.host == "portal.example"
    assert web.port == 444
    assert any("secret-like field" in warning for warning in result.warnings)

    sessions_only = tmp_path / "sessions-only"
    sessions_only.mkdir()
    (sessions_only / "one.mxtsessions").write_text("[Bookmarks]", encoding="utf-8")
    assert importers._mobaxterm_files(sessions_only) == [sessions_only / "one.mxtsessions"]


@pytest.mark.parametrize(
    "value",
    [
        "plain text",
        "a%b",
        "#1%2%3",
    ],
)
def test_mobaxterm_percent_parser_rejects_unusable_entries(value: str) -> None:
    assert importers._mobaxterm_profile("entry", value, "group") is None


def test_command_profile_parser_handles_invalid_and_non_ssh_targets() -> None:
    assert importers._command_like_profile("bad", 'ssh "unterminated', "", "test") is None
    assert importers._command_like_profile("empty", "", "", "test") is None
    assert importers._command_like_profile("unknown", "unknown host", "", "test") is None
    assert importers._command_like_profile("missing", "https", "", "test") is None

    rdp = importers._command_like_profile("desktop", "rdp desk.example:3390", "", "test")
    assert rdp is not None
    assert rdp.host == "desk.example"
    assert rdp.port == 3390


def test_ssh_command_parser_handles_plain_host_and_missing_target() -> None:
    plain = importers._ssh_command_profile("plain", ["-v", "host.example"], "", "test")
    assert plain is not None
    assert plain.host == "host.example"
    assert plain.username is None

    assert importers._ssh_command_profile("missing", ["-p"], "", "test") is None
    assert importers._ssh_command_profile("flags", ["-v"], "", "test") is None


def test_json_and_recursive_host_helpers_cover_shape_variants() -> None:
    nested = {
        "credential": {"username": "nested-user"},
        "folder": {"label": "nested-folder"},
    }
    assert importers._first(nested, "username") == "nested-user"
    assert importers._group_from_json(nested) == "nested-folder"
    assert importers._group_from_json({}) is None
    assert importers._json_tags({"tags": ["one", "", "two"]}) == ["one", "two"]
    assert importers._json_tags({"tags": 4}) == []
    assert list(importers._iter_host_dicts("text")) == []
    assert list(importers._iter_host_dicts([{"name": "host", "address": "host.example"}]))


def test_profile_helpers_normalize_servers_names_tags_and_duplicates() -> None:
    assert importers._server_and_port(None, "ssh") == (None, None)
    assert importers._server_and_port("ssh://host.example:2200", "ssh") == ("host.example", 2200)
    assert importers._server_and_port("[2001:db8::1]:2222", "ssh") == ("2001:db8::1", 2222)
    assert importers._server_and_port("[2001:db8::1]", "ssh") == ("2001:db8::1", None)
    assert importers._server_and_port("host.example:not-a-port", "ssh") == ("host.example:not-a-port", None)
    assert importers._map_protocol(None, default="ssh") == "ssh"

    serial = importers._profile(name=" serial/profile ", protocol="serial", host="ignored", tags=["one", "one", ""])
    assert serial.name == "serial_profile"
    assert serial.host is None
    assert serial.tags == ["one"]
    assert importers._clean_host(None, "ssh") is None
    assert importers._profile_name("   ") == "imported"
    assert importers._clean_optional("", "value") is None

    profiles = [
        Profile(name="duplicate", protocol="ssh", host="one.example"),
        Profile(name="duplicate", protocol="ssh", host="two.example"),
    ]
    deduped = importers._dedupe_profiles(profiles)
    assert [profile.name for profile in deduped] == ["duplicate", "duplicate-2"]


@pytest.mark.parametrize(
    ("name", "marker", "expected"),
    [
        ("RDP desktop", "", "rdp"),
        ("VNC console", "", "vnc"),
        ("Telnet console", "", "telnet"),
        ("FTP files", "", "ftp"),
        ("SSH shell", "", "ssh"),
    ],
)
def test_mobaxterm_protocol_detection(name: str, marker: str, expected: str) -> None:
    assert importers._mobaxterm_protocol(name, marker) == expected


def test_host_index_integer_and_text_helpers() -> None:
    assert importers._first_host_index(["", "#109", "-flag", "22", "___", "host.example"]) == 5
    assert importers._first_host_index(["", "#109", "-flag", "22", "___"]) is None
    assert importers._int_or_none("bad") is None
    assert importers._truthy("ON") is True
    assert importers._truthy(None) is False
    assert importers._has_secret_field("PassPhrase") is True


def test_warning_helpers_respect_explicit_legacy_opt_ins() -> None:
    result = importers.ProfileImportResult(
        "row",
        [
            Profile(
                name="approved-ssh1",
                protocol="ssh1",
                host="legacy.example",
                options={"allow_insecure_sshv1": "yes"},
            ),
            Profile(
                name="approved-telnet",
                protocol="telnet",
                host="legacy.example",
                options={"allow_insecure_cleartext": "true"},
            ),
        ],
    )

    importers._warn_legacy_sshv1(result)
    importers._warn_cleartext_protocols(result)

    assert result.warnings == []


def test_read_text_uses_cp1252_and_replacement_fallback(tmp_path: Path) -> None:
    cp1252 = tmp_path / "legacy.txt"
    cp1252.write_bytes(b"legacy \x96 text")
    assert importers._read_text(cp1252) == "legacy – text"

    class FailingTextPath:
        def __init__(self) -> None:
            self.calls = 0

        def read_text(self, *, encoding: str, errors: str | None = None) -> str:
            self.calls += 1
            if errors != "replace":
                raise UnicodeError("decode failed")
            return "replacement"

    fake = FailingTextPath()
    assert importers._read_text(fake) == "replacement"  # type: ignore[arg-type]
    assert fake.calls == 4

from __future__ import annotations

from types import SimpleNamespace

import pytest

import remote_ops_workspace.moba_connected as connected
from remote_ops_workspace.models import Profile


def _profile(**overrides: object) -> Profile:
    values: dict[str, object] = {
        "name": "edge",
        "protocol": "ssh",
        "host": "edge.example",
    }
    values.update(overrides)
    return Profile(**values)


def test_monitoring_and_chrome_value_objects_serialize() -> None:
    plan = connected.build_remote_monitoring_plan(_profile())
    assert plan.printable().startswith("ssh ")

    missing = connected.RemoteMonitoringSnapshot(None, None, None, None, None, None, None, None, None)
    observed = connected.RemoteMonitoringSnapshot(1, 1.0, 2.0, 3.0, 4.0, 0.25, 0.5, 1, 2)
    assert missing.network_label == "Unavailable"
    assert observed.network_label == "0.25 Mb/s up, 0.50 Mb/s down"

    state = connected.build_moba_connected_session_state(
        _profile(),
        monitoring_output="cpu=1 mem_mb=1/2 disk_mb=3/4 users=1 processes=2",
        preview_sample_data=True,
    )
    assert connected.moba_telemetry_segments(state)[0].to_dict()["key"] == "target"
    assert connected.moba_telemetry_cell_geometry()[0].to_dict()["key"] == "target"
    assert connected.moba_connected_tab_chrome_items(state)[0].to_dict()["key"] == "home"
    assert connected.moba_connected_tab_chrome_geometry_items()[0].to_dict()["key"] == "home"
    assert connected.build_moba_terminal_transcript(_profile(), "/")[0].to_dict()["tone"] == "info"


def test_profile_labels_cover_username_port_and_display_fallback() -> None:
    assert connected.moba_connected_profile_label(_profile(username=None)) == "edge.example"
    assert connected.moba_connected_profile_target(_profile(port=2222)) == "edge.example:2222"
    fallback = Profile(name="layout", protocol="ssh", host=None)
    assert connected.moba_connected_profile_target(fallback) == fallback.display_target


def test_geometry_lookup_and_explicit_target_port_edges() -> None:
    with pytest.raises(KeyError, match="missing"):
        connected.moba_connected_tab_chrome_geometry_for("missing")
    with pytest.raises(KeyError, match="missing"):
        connected.moba_telemetry_cell_geometry_for("missing")

    state = connected.build_moba_connected_session_state(_profile(port=2222))
    assert connected.moba_telemetry_port(state) == "2222"
    assert connected.moba_telemetry_target_display(state) == "edge.example:2222"


def test_banner_reports_trusted_x11() -> None:
    banner = connected.build_ssh_connection_banner(_profile(options={"x11": "trusted"}))
    assert banner.x11_forwarding == "trusted"


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        ({"smartcard_provider": "", "pkcs11_provider": "pkcs11:/module.so"}, "PKCS#11 provider"),
        ({"smartcard_provider": "my-pkcs11-module"}, "PKCS#11 provider"),
        ({"smartcard_provider": "custom-provider"}, "provider"),
        ({"identity_agent": "/tmp/agent.sock"}, "agent handoff"),
        ({"certificate_file": "/tmp/cert.pub"}, "certificate file"),
        ({"security_key_provider": "internal"}, "security-key provider"),
        ({}, "requested"),
    ],
)
def test_smartcard_provider_label_fallbacks(options: dict[str, str], expected: str) -> None:
    assert connected._moba_smartcard_provider_label(options) == expected


def test_browser_preferences_accept_objects_and_reject_invalid_values() -> None:
    source = SimpleNamespace(location="beside-terminal", overwrite_confirmation=True)
    assert connected._preference_value(source, "location", "hidden") == "beside-terminal"
    assert connected._preference_value(source, "missing", "default") == "default"

    with pytest.raises(ValueError, match="location must be one of"):
        connected._connected_ssh_browser_location("sideways")
    with pytest.raises(ValueError, match="column_widths must be an object"):
        connected._connected_ssh_browser_columns([])
    with pytest.raises(ValueError, match="column key must be one of"):
        connected._connected_ssh_browser_columns({"unknown": 100})
    with pytest.raises(ValueError, match="column width must be between"):
        connected._connected_ssh_browser_columns({"name": 1})


def test_text_editor_selection_path_and_preview_fallbacks() -> None:
    entries = (
        connected.RemoteFileEntry("folder", "dir", 0, "now"),
        connected.RemoteFileEntry("binary.bin", "file", 1, "now"),
        connected.RemoteFileEntry("notes.txt", "file", 1, "now"),
    )
    selected, index = connected._default_text_editor_entry(entries)
    assert selected is entries[2]
    assert index == 3

    fallback, fallback_index = connected._default_text_editor_entry(entries[:2])
    assert fallback is entries[1]
    assert fallback_index == 2
    assert connected._join_remote_file_path("/tmp", "..") == "/tmp/README.txt"
    assert connected._connected_text_editor_preview("json", "/tmp/data.json").startswith("{")
    assert connected._connected_text_editor_preview("shell", "/tmp/run.sh").startswith("#!")
    assert connected._connected_text_editor_preview("unknown", "/tmp/data.bin") == ""


def test_listing_and_monitoring_parsers_ignore_noise_and_invalid_values() -> None:
    assert connected.parse_sftp_ls_output("short row\n") == []
    snapshot = connected.parse_remote_monitoring_output(
        "noise cpu=bad mem_mb=bad disk_mb=1/2 net_up_mbps=bad net_down_mbps=0.5 processes=bad"
    )
    assert snapshot is not None
    assert snapshot.cpu_percent is None
    assert snapshot.memory_used_gb is None
    assert snapshot.disk_used_gb == 0.0
    assert snapshot.net_up_mbps is None
    assert snapshot.net_down_mbps == 0.5
    assert snapshot.process_count is None

    day_snapshot = connected.parse_remote_monitoring_output(
        "cpu=1 mem_mb=1/2 disk_mb=1/2 uptime_seconds=86400 "
        "mounts=relative:10%|/broken:not-a-number|/ok:101%"
    )
    assert day_snapshot is not None
    assert day_snapshot.uptime_label == "1d 0h"
    assert day_snapshot.filesystem_usage == (("/ok", 100),)

    minute_snapshot = connected.parse_remote_monitoring_output(
        "cpu=1 mem_mb=1/2 disk_mb=1/2 uptime_seconds=60 mounts=-"
    )
    assert minute_snapshot is not None
    assert minute_snapshot.uptime_label == "1 min"


def test_path_and_numeric_parsers_fail_closed() -> None:
    with pytest.raises(ValueError, match="must not start"):
        connected.normalise_remote_path("-unsafe")
    assert connected.parse_pair_mb("broken") == (0, 0)
    assert connected._optional_pair_gb(None) == (None, None)
    assert connected._optional_pair_gb("broken") == (None, None)
    assert connected._optional_clamp_int(None, 0, 10) is None
    assert connected._optional_clamp_int("bad", 0, 10) is None
    assert connected._optional_float(None) is None
    assert connected._optional_float("bad") is None
    assert connected.clamp_int("bad", 3, 10) == 3

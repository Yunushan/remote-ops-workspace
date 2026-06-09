import pytest

from remote_ops_workspace.moba_connected import (
    REMOTE_MONITORING_SCRIPT,
    build_follow_terminal_folder_plan,
    build_moba_connected_session_state,
    build_moba_terminal_transcript,
    build_remote_monitoring_plan,
    build_ssh_connection_banner,
    moba_connected_profile_label,
    moba_connected_tab_chrome_items,
    moba_connected_tab_label,
    moba_connected_window_title,
    moba_telemetry_cells,
    moba_telemetry_segments,
    normalise_remote_path,
    parse_remote_monitoring_output,
    parse_sftp_ls_output,
)
from remote_ops_workspace.models import Profile


def ssh_profile(**overrides) -> Profile:
    values = {
        "name": "example-ssh",
        "protocol": "ssh",
        "host": "example.internal",
        "username": "operator",
        "options": {"compression": "true", "ssh_browser": "true"},
    }
    values.update(overrides)
    return Profile(**values)


def test_connected_session_state_tracks_browser_follow_monitoring_and_banner() -> None:
    profile = ssh_profile()
    state = build_moba_connected_session_state(
        profile,
        remote_path="/",
        terminal_cwd="/var/log",
        follow_terminal_folder=True,
        sftp_listing="-rw-r--r-- 1 operator operator 4096 Jun 06 12:00 app.log\n"
        "drwxr-xr-x 2 operator operator 4096 Jun 06 12:01 nginx",
        monitoring_output="cpu=12 mem_mb=512/2048 disk_mb=1024/8192 load=0.12 users=2 "
        "processes=158 net_up_mbps=0.02 net_down_mbps=0.03",
    )

    assert state.remote_path == "/var/log"
    assert state.follow_terminal_folder is True
    assert [entry.name for entry in state.file_entries] == ["app.log", "nginx"]
    assert state.sftp_list_plan.batch_commands == ["ls -la /var/log"]
    assert state.follow_folder_plan.batch_commands == ["ls -la /var/log"]
    assert state.monitoring.cpu_percent == 12
    assert state.monitoring.connection_count == 2
    assert state.monitoring.process_count == 158
    assert "SSH session to example.internal" in state.banner.lines()[0]
    assert state.connection_label == "example.internal (operator)"
    assert [line.key for line in state.terminal_transcript] == [
        "web-console",
        "spacer",
        "last-login",
        "prompt-ready",
    ]
    assert state.terminal_transcript[0].text == (
        "Web console: https://example.internal:9090/ or https://192.0.2.10:9090/"
    )
    assert state.terminal_transcript[3].text == "[operator@example ~]$ "
    assert state.to_dict()["telemetry_cells"][0]["display_text"] == "example.internal:22"


def test_connected_session_chrome_uses_target_identity_and_telemetry_segments() -> None:
    profile = ssh_profile()
    state = build_moba_connected_session_state(
        profile,
        monitoring_output="cpu=7 mem_mb=410/7680 disk_mb=2867/49152 users=1 processes=158 "
        "net_up_mbps=0.01 net_down_mbps=0.01",
    )
    segments = moba_telemetry_segments(state)

    assert moba_connected_profile_label(profile) == "example.internal (operator)"
    assert moba_connected_tab_label(state) == "example.internal (operator)"
    assert moba_connected_tab_label(state, ordinal=7) == "7. example.internal (operator)"
    assert moba_connected_window_title(state) == "example.internal (operator)"
    assert [segment.key for segment in segments] == [
        "target",
        "cpu",
        "memory",
        "disk",
        "net-up",
        "net-down",
        "connections",
        "processes",
    ]
    assert [segment.icon_key for segment in segments] == [
        "host",
        "cpu",
        "memory",
        "disk",
        "upload",
        "download",
        "connection",
        "process",
    ]


def test_bottom_telemetry_cells_match_reference_like_status_strip() -> None:
    state = build_moba_connected_session_state(
        ssh_profile(),
        monitoring_output="cpu=7 mem_mb=410/7680 disk_mb=2867/49152 users=1 processes=158 "
        "net_up_mbps=0.01 net_down_mbps=0.01",
    )
    cells = moba_telemetry_cells(state)

    assert [cell.key for cell in cells] == [
        "target",
        "cpu",
        "memory",
        "disk",
        "net-up",
        "net-down",
        "connections",
        "processes",
    ]
    assert [cell.display_text for cell in cells] == [
        "example.internal:22",
        "7%",
        "0.4 GB / 7.5 GB",
        "2.8 GB / 48.0 GB",
        "0.01 Mb/s",
        "0.01 Mb/s",
        "Connections: 1 (port 22)",
        "2/158",
    ]
    assert [cell.width for cell in cells] == [165, 60, 125, 124, 88, 88, 145, 77]
    assert [cell.icon_size for cell in cells] == [12] * 8
    assert [cell.icon_accent for cell in cells] == [
        "#35d7c7",
        "#f4c430",
        "#6ac76a",
        "#6ac76a",
        "#4da3ff",
        "#4da3ff",
        "#35d7c7",
        "#f4c430",
    ]


def test_connected_tab_chrome_tracks_reference_tab_sequence_without_user_samples() -> None:
    state = build_moba_connected_session_state(ssh_profile())
    items = moba_connected_tab_chrome_items(state)

    assert [item.key for item in items] == ["home", "inactive-session", "active-session", "new-session"]
    assert [item.icon_key for item in items] == ["home", "terminal-key", "terminal-key", "plus"]
    assert items[0].label == ""
    assert items[1].label == "6. jump.example.invalid (operator)"
    assert items[2].label == "7. example.internal (operator)"
    assert items[2].active is True
    assert items[2].closeable is True
    assert items[3].label == "+"
    assert "yunus" not in " ".join(item.label.lower() for item in items)


def test_terminal_transcript_uses_generic_connected_state_without_user_samples() -> None:
    lines = build_moba_terminal_transcript(ssh_profile(host="edge-prod.example.invalid"), "/var/log")

    assert [line.tone for line in lines] == ["info", "spacer", "info", "command"]
    assert lines[0].text == "Web console: https://edge-prod.example.invalid:9090/ or https://192.0.2.10:9090/"
    assert lines[3].text == "[operator@edge-prod ~]$ "
    assert "yunus" not in "\n".join(line.text.lower() for line in lines)


def test_remote_monitoring_plan_uses_existing_ssh_transport_even_for_sftp_profiles() -> None:
    profile = ssh_profile(protocol="sftp", port=2222)

    plan = build_remote_monitoring_plan(profile)

    assert plan.profile_name == "example-ssh"
    assert "ssh" in plan.command[0].lower()
    assert "-p" in plan.command
    assert "2222" in plan.command
    assert "sh" in plan.command
    assert "-lc" in plan.command
    assert REMOTE_MONITORING_SCRIPT in plan.command
    assert any("existing SSH transport" in note for note in plan.notes)


def test_follow_terminal_folder_plan_normalises_remote_paths() -> None:
    plan = build_follow_terminal_folder_plan(ssh_profile(), "var/www")

    assert plan.batch_commands == ["ls -la /var/www"]
    assert normalise_remote_path("var/www") == "/var/www"


def test_sftp_listing_parser_extracts_file_table_rows() -> None:
    rows = parse_sftp_ls_output(
        "total 4\n"
        "drwxr-xr-x 2 operator operator 4096 Jun 06 12:01 releases\n"
        "-rw-r--r-- 1 operator operator 2048 Jun 06 12:02 deploy.log\n"
    )

    assert [row.to_dict() for row in rows] == [
        {"name": "releases", "kind": "dir", "size_kb": 4, "modified": "Jun 06 12:01"},
        {"name": "deploy.log", "kind": "file", "size_kb": 2, "modified": "Jun 06 12:02"},
    ]


def test_remote_monitoring_parser_uses_users_as_connection_count() -> None:
    snapshot = parse_remote_monitoring_output("cpu=7 mem_mb=256/1024 disk_mb=512/4096 users=3 processes=91")

    assert snapshot is not None
    assert snapshot.cpu_percent == 7
    assert snapshot.memory_label == "0.2 GB / 1.0 GB"
    assert snapshot.disk_label == "0.5 GB / 4.0 GB"
    assert snapshot.connection_count == 3
    assert snapshot.process_count == 91


def test_ssh_connection_banner_reports_disabled_options() -> None:
    banner = build_ssh_connection_banner(
        ssh_profile(options={"compression": "false", "ssh_browser": "false", "x11": "true"})
    )
    rows = banner.capability_rows()

    assert banner.direct_ssh is True
    assert banner.ssh_compression is False
    assert banner.ssh_browser is False
    assert banner.x11_forwarding == "enabled"
    assert [row.key for row in rows] == ["direct-ssh", "ssh-compression", "ssh-browser", "x11-forwarding"]
    assert [row.label for row in rows] == ["Direct SSH", "SSH compression", "SSH-browser", "X11-forwarding"]
    assert [row.value for row in rows] == ["yes", "no", "no", "enabled"]
    assert [row.status for row in rows] == ["ok", "disabled", "disabled", "ok"]
    assert banner.footer_links() == ("help", "website")
    assert banner.to_dict()["capabilities"][0]["key"] == "direct-ssh"


def test_connected_session_rejects_non_ssh_profiles() -> None:
    with pytest.raises(ValueError, match="requires an SSH/SFTP profile"):
        build_moba_connected_session_state(Profile(name="web", protocol="https", url="https://example.com"))

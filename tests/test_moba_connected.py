import pytest

from remote_ops_workspace.moba_connected import (
    REMOTE_MONITORING_SCRIPT,
    build_follow_terminal_folder_plan,
    build_moba_connected_session_state,
    build_moba_terminal_transcript,
    build_remote_monitoring_plan,
    build_same_parameters_sftp_plan,
    build_ssh_connection_banner,
    moba_connected_profile_label,
    moba_connected_session_action_route,
    moba_connected_session_identity_route,
    moba_connected_session_route,
    moba_connected_tab_chrome_geometry_for,
    moba_connected_tab_chrome_geometry_items,
    moba_connected_tab_chrome_items,
    moba_connected_tab_label,
    moba_connected_text_editor_route,
    moba_connected_window_title,
    moba_sftp_terminal_folder_route,
    moba_telemetry_cell_geometry,
    moba_telemetry_cell_geometry_for,
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
    assert state.terminal_transcript == ()
    assert state.state_source == "runtime-observed"
    assert state.connection_phase == "connected-observed"
    assert state.to_dict()["telemetry_cells"][0]["display_text"] == "example.internal:22"
    assert state.to_dict()["connected_route"]["key"] == "moba-active-connected-session-route"
    assert state.to_dict()["identity_route"]["key"] == "moba-connected-session-identity-route"
    assert state.to_dict()["session_action_route"]["key"] == "moba-connected-session-actions-route"
    assert state.to_dict()["sftp_terminal_folder_route"]["key"] == "moba-sftp-terminal-folder-route"


def test_connected_session_state_consumes_ssh_browser_preferences_and_smartcard_selection() -> None:
    profile = ssh_profile(
        options={
            "compression": "true",
            "ssh_browser": "true",
            "smartcard_provider": "microsoft-capi",
            "smartcard_certificate_id": "cert-1",
            "smartcard_certificate_label": "Operator Card",
            "smartcard_public_key": "ssh-rsa AAAA operator-card",
            "add_smartcard_to_mobagent": "true",
        }
    )

    state = build_moba_connected_session_state(
        profile,
        ssh_browser_preferences={
            "location": "below-terminal",
            "column_widths": {"name": 244, "size": 96},
            "overwrite_confirmation": False,
        },
    )

    assert state.ssh_browser_state.location == "below-terminal"
    assert state.ssh_browser_state.column_widths["name"] == 244
    assert state.ssh_browser_state.column_widths["size"] == 96
    assert state.ssh_browser_state.column_widths["modified"] == 94
    assert state.ssh_browser_state.overwrite_confirmation is False
    assert state.ssh_browser_state.browser_visible is True
    assert state.smartcard_selection.enabled is True
    assert state.smartcard_selection.provider_label == "Microsoft CryptoAPI/CAPI"
    assert state.smartcard_selection.certificate_id == "cert-1"
    assert state.smartcard_selection.certificate_label == "Operator Card"
    assert state.smartcard_selection.add_to_mobagent is True
    payload = state.to_dict()
    assert payload["ssh_browser_state"]["column_widths"]["name"] == 244
    assert payload["smartcard_selection"]["certificate_id"] == "cert-1"


def test_connected_session_state_exposes_sftp_text_editor_route() -> None:
    state = build_moba_connected_session_state(
        ssh_profile(),
        remote_path="/etc",
        sftp_listing="-rw-r--r-- 1 root root 2048 Jun 06 12:00 sshd_config\n"
        "-rw-r--r-- 1 root root 4096 Jun 06 12:01 app.log",
    )
    route = moba_connected_text_editor_route(state)

    assert route.schema == "row.moba-text.editor-tab.v1"
    assert route.source_browser_object == "mobaSftpBrowser"
    assert route.source_table_object == "mobaSftpFileTable"
    assert route.editor_tab_object == "mobaTextEditorTab"
    assert route.editor_object == "mobaTextEditor"
    assert route.save_action_object == "mobaTextEditorSaveAction"
    assert route.diff_action_object == "mobaTextEditorDiffAction"
    assert route.open_signal == "itemDoubleClicked"
    assert route.remote_path == "/etc/sshd_config"
    assert route.local_path.endswith("example-ssh-sshd_config.edit")
    assert route.syntax == "ssh-config"
    assert route.open_command[0] == "sftp"
    assert route.open_batch_commands == ("get /etc/sshd_config example-ssh-sshd_config.edit",)
    assert route.save_batch_commands == ("put example-ssh-sshd_config.edit /etc/sshd_config",)
    assert route.conflict_policy == "sha256-match-or-force"
    assert state.to_dict()["text_editor"]["remote_path"] == "/etc/sshd_config"


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


def test_connected_session_route_ties_active_tab_to_visible_surfaces() -> None:
    state = build_moba_connected_session_state(ssh_profile(), remote_path="/var/log")
    route = moba_connected_session_route(state)

    assert route.key == "moba-active-connected-session-route"
    assert route.route_role == "active-tab-to-connected-workspace"
    assert route.active_tab_key == "active-session"
    assert route.active_tab_label == "example.internal (operator)"
    assert route.reference_tab_label == "7. example.internal (operator)"
    assert route.active_tab_object == "sessionTabs"
    assert route.connected_panel_object == "mobaConnectedSession"
    assert route.left_dock_object == "mobaConnectedLeftDock"
    assert route.sftp_browser_object == "mobaSftpBrowser"
    assert route.sftp_path_object == "mobaSftpPath"
    assert route.sftp_table_object == "mobaSftpFileTable"
    assert route.ssh_banner_object == "mobaSshBanner"
    assert route.terminal_area_object == "mobaTerminalArea"
    assert route.terminal_output_object == "terminalOutput"
    assert route.telemetry_bar_object == "mobaTelemetryBar"
    assert route.telemetry_identity_cell_key == "target"
    assert route.target == "example.internal"
    assert route.remote_path == "/var/log"
    assert route.tab_label_property == "mobaConnectedRouteActiveTabLabel"
    assert route.target_property == "mobaConnectedRouteTarget"
    assert route.remote_path_property == "mobaConnectedRouteRemotePath"
    assert route.render_source == "connected-session-state"
    assert "yunus" not in " ".join(str(value).lower() for value in route.to_dict().values())


def test_connected_session_action_route_ties_context_menu_to_active_tab() -> None:
    state = build_moba_connected_session_state(ssh_profile(), remote_path="/var/log")
    route = moba_connected_session_action_route(state)

    assert route.key == "moba-connected-session-actions-route"
    assert route.route_role == "active-connected-tab-context-session-actions"
    assert route.profile_name == "example-ssh"
    assert route.target == "example.internal"
    assert route.active_tab_key == "active-session"
    assert route.active_tab_label == "example.internal (operator)"
    assert route.reference_tab_label == "7. example.internal (operator)"
    assert route.tabs_object == "sessionTabs"
    assert route.tab_bar_object == "sessionTabBar"
    assert route.reference_tab_role == "terminal"
    assert route.menu_object == "mobaConnectedSessionTabContextMenu"
    assert route.action_object == "mobaConnectedSessionTabContextAction"
    assert route.expected_action_keys == (
        "new-local-terminal",
        "split-horizontal",
        "split-vertical",
        "duplicate-tab",
        "open-sftp-same-parameters",
        "close-tab",
        "close-other-tabs",
        "recover-previous-sessions",
    )
    assert route.expected_action_labels == (
        "New local terminal",
        "Split horizontal",
        "Split vertical",
        "Duplicate tab",
        "Open SFTP with same parameters",
        "Close tab",
        "Close other tabs",
        "Recover previous sessions",
    )
    assert route.expected_action_count == 8
    assert route.always_enabled_action_keys == (
        "new-local-terminal",
        "split-horizontal",
        "split-vertical",
        "duplicate-tab",
        "open-sftp-same-parameters",
        "close-tab",
        "recover-previous-sessions",
    )
    assert route.conditional_enabled_action_keys == ("close-other-tabs",)
    assert route.action_key_property == "sessionTabContextActionKey"
    assert route.to_dict()["menu_object"] == "mobaConnectedSessionTabContextMenu"
    assert route.captured_action_keys_property == "mobaConnectedSessionActionKeys"
    assert route.captured_enabled_keys_property == "mobaConnectedSessionActionEnabledKeys"
    assert route.render_source == "connected-session-state"
    assert "yunus" not in " ".join(str(value).lower() for value in route.to_dict().values())


def test_connected_session_identity_route_ties_visible_target_text_together() -> None:
    state = build_moba_connected_session_state(
        ssh_profile(),
        remote_path="/var/log",
        preview_sample_data=True,
    )
    route = moba_connected_session_identity_route(state)

    assert route.key == "moba-connected-session-identity-route"
    assert route.route_role == "title-tab-banner-terminal-telemetry-identity"
    assert route.window_title == "example.internal (operator)"
    assert route.active_tab_label == "example.internal (operator)"
    assert route.reference_tab_label == "7. example.internal (operator)"
    assert route.banner_target == "example.internal"
    assert route.web_console_line == "Web console: https://example.internal:9090/ or https://192.0.2.10:9090/"
    assert route.terminal_prompt == "[operator@example ~]$ "
    assert route.telemetry_target == "example.internal:22"
    assert route.target_endpoint == "example.internal"
    assert route.remote_path == "/var/log"
    assert route.window_title_property == "mobaConnectedIdentityWindowTitle"
    assert route.banner_target_property == "mobaConnectedIdentityBannerTarget"
    assert route.terminal_prompt_property == "mobaConnectedIdentityTerminalPrompt"
    assert route.telemetry_target_property == "mobaConnectedIdentityTelemetryTarget"
    assert route.render_source == "connected-session-state"
    assert "yunus" not in " ".join(str(value).lower() for value in route.to_dict().values())


def test_sftp_terminal_folder_route_ties_terminal_checkbox_path_and_rows() -> None:
    state = build_moba_connected_session_state(
        ssh_profile(),
        remote_path="/",
        terminal_cwd="/var/log",
        follow_terminal_folder=True,
    )
    route = moba_sftp_terminal_folder_route(state)

    assert route.key == "moba-sftp-terminal-folder-route"
    assert route.route_role == "terminal-cwd-follow-checkbox-to-sftp-path-and-rows"
    assert route.terminal_area_object == "mobaTerminalArea"
    assert route.terminal_output_object == "terminalOutput"
    assert route.source_control_object == "mobaFollowTerminalFolder"
    assert route.target_browser_object == "mobaSftpBrowser"
    assert route.target_path_object == "mobaSftpPath"
    assert route.target_table_object == "mobaSftpFileTable"
    assert route.parent_row_label == ".."
    assert route.selected_row_kind == "parent-dir"
    assert route.remote_path == "/var/log"
    assert route.list_command == "ls -la /var/log"
    assert route.follow_enabled is True
    assert route.path_property == "mobaSftpTerminalFolderRoutePath"
    assert route.plan_property == "mobaSftpTerminalFolderRoutePlan"
    assert route.enabled_property == "mobaSftpTerminalFolderRouteEnabled"
    assert route.row_route_property == "mobaSftpTerminalFolderRouteKey"
    assert route.render_source == "connected-session-state"
    assert "yunus" not in " ".join(str(value).lower() for value in route.to_dict().values())


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


def test_bottom_telemetry_cell_geometry_tracks_reference_offsets() -> None:
    geometry = moba_telemetry_cell_geometry()

    assert [item.key for item in geometry] == [
        "target",
        "cpu",
        "memory",
        "disk",
        "net-up",
        "net-down",
        "connections",
        "processes",
    ]
    assert [item.static_x for item in geometry] == [10, 175, 235, 360, 484, 572, 660, 805]
    assert [item.width for item in geometry] == [165, 60, 125, 124, 88, 88, 145, 77]
    assert {item.static_y for item in geometry} == {1}
    assert {item.height for item in geometry} == {22}
    assert {item.icon_x for item in geometry} == {5}
    assert {item.icon_y for item in geometry} == {5}
    assert {item.icon_size for item in geometry} == {12}
    assert {item.label_x for item in geometry} == {22}
    assert {item.label_y for item in geometry} == {6}
    assert {item.label_font_size for item in geometry} == {9}
    assert {item.separator_top for item in geometry} == {2}
    assert {item.separator_bottom for item in geometry} == {22}
    assert moba_telemetry_cell_geometry_for("connections").static_x == 660


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
    assert [item.width for item in items] == [42, 226, 258, 32]
    assert items[3].label == "+"
    assert "yunus" not in " ".join(item.label.lower() for item in items)


def test_connected_tab_chrome_geometry_tracks_reference_offsets() -> None:
    geometry = moba_connected_tab_chrome_geometry_items()

    assert [item.key for item in geometry] == ["home", "inactive-session", "active-session", "new-session"]
    assert [item.width for item in geometry] == [42, 226, 258, 32]
    assert {item.height for item in geometry} == {22}
    assert {item.corner_radius for item in geometry} == {2}
    assert {item.icon_x for item in geometry} == {8}
    assert {item.icon_y for item in geometry} == {5}
    assert {item.icon_size for item in geometry} == {12}
    assert {item.label_x for item in geometry} == {26}
    assert {item.label_y for item in geometry} == {7}
    assert {item.close_right_offset for item in geometry} == {16}
    assert {item.close_y for item in geometry} == {6}
    assert {item.plus_x for item in geometry} == {11}
    assert {item.plus_y for item in geometry} == {3}
    assert {item.gap_after for item in geometry} == {4}
    assert moba_connected_tab_chrome_geometry_for("active-session").width == 258


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


def test_same_parameters_sftp_plan_preserves_ssh_options() -> None:
    plan = build_same_parameters_sftp_plan(
        ssh_profile(
            port=2222,
            options={
                "compression": "true",
                "ssh_browser": "true",
                "pkcs11_provider": "/usr/lib/opensc-pkcs11.so",
                "certificate_file": "/home/operator/.ssh/id_ed25519-cert.pub",
                "identity_agent": "/tmp/agent.sock",
            },
        )
    )

    assert plan.command[:3] == ["sftp", "-P", "2222"]
    assert "-C" in plan.command
    assert "-I" in plan.command
    assert "/usr/lib/opensc-pkcs11.so" in plan.command
    assert "CertificateFile=/home/operator/.ssh/id_ed25519-cert.pub" in plan.command
    assert "IdentityAgent=/tmp/agent.sock" in plan.command
    assert plan.command[-1] == "operator@example.internal"


def test_sftp_listing_parser_extracts_file_table_rows() -> None:
    rows = parse_sftp_ls_output(
        "total 4\n"
        "drwxr-xr-x 4 operator operator 4096 Jun 06 12:00 .\n"
        "drwxr-xr-x 4 operator operator 4096 Jun 06 12:00 ..\n"
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
    assert snapshot.net_up_mbps is None
    assert snapshot.net_down_mbps is None


def test_live_connected_session_default_does_not_fabricate_runtime_evidence() -> None:
    state = build_moba_connected_session_state(ssh_profile(), remote_path="/var/log")
    payload = state.to_dict()

    assert state.file_entries == ()
    assert state.terminal_transcript == ()
    assert state.monitoring.observed is False
    assert state.monitoring.cpu_percent is None
    assert state.monitoring.memory_used_gb is None
    assert state.monitoring.net_up_mbps is None
    assert state.state_source == "live"
    assert state.connection_phase == "connecting"
    assert payload["monitoring"]["cpu_percent"] is None
    assert payload["monitoring"]["observed"] is False
    assert payload["telemetry_cells"][1]["display_text"] == "Unavailable"
    assert payload["telemetry_cells"][6]["display_text"] == "Connections: unavailable"
    assert payload["state_source"] == "live"
    assert payload["connection_phase"] == "connecting"


def test_preview_sample_data_is_explicit_and_never_duplicates_parent_row() -> None:
    state = build_moba_connected_session_state(
        ssh_profile(),
        remote_path="/",
        preview_sample_data=True,
    )

    assert state.file_entries
    assert "." not in {entry.name for entry in state.file_entries}
    assert ".." not in {entry.name for entry in state.file_entries}
    assert state.monitoring.observed is True
    assert state.terminal_transcript
    assert state.state_source == "preview-sample"
    assert state.connection_phase == "preview"


def test_ssh_connection_banner_reports_disabled_options() -> None:
    banner = build_ssh_connection_banner(
        ssh_profile(options={"compression": "false", "ssh_browser": "false", "x11": "true"})
    )
    rows = banner.capability_rows()

    assert banner.direct_ssh is True
    assert banner.ssh_compression is False
    assert banner.smartcard_auth is False
    assert banner.ssh_browser is False
    assert banner.x11_forwarding == "enabled"
    assert [row.key for row in rows] == [
        "direct-ssh",
        "ssh-compression",
        "smartcard-auth",
        "ssh-browser",
        "x11-forwarding",
    ]
    assert [row.label for row in rows] == [
        "Direct SSH",
        "SSH compression",
        "Smart card auth",
        "SSH-browser",
        "X11-forwarding",
    ]
    assert [row.value for row in rows] == ["yes", "no", "no", "no", "enabled"]
    assert [row.status for row in rows] == ["ok", "disabled", "disabled", "disabled", "ok"]
    assert banner.footer_links() == ("help", "website")
    assert banner.to_dict()["capabilities"][0]["key"] == "direct-ssh"


def test_ssh_connection_banner_reports_smartcard_provider() -> None:
    banner = build_ssh_connection_banner(
        ssh_profile(
            options={
                "compression": "true",
                "ssh_browser": "true",
                "smartcard_auth": "true",
                "smartcard_provider": "microsoft-capi",
            }
        )
    )
    rows = {row.key: row for row in banner.capability_rows()}

    assert banner.smartcard_auth is True
    assert banner.smartcard_provider == "Microsoft CryptoAPI/CAPI"
    assert rows["smartcard-auth"].value == "yes"
    assert rows["smartcard-auth"].status == "ok"
    assert rows["smartcard-auth"].note == "Microsoft CryptoAPI/CAPI"


def test_connected_session_rejects_non_ssh_profiles() -> None:
    with pytest.raises(ValueError, match="requires an SSH/SFTP profile"):
        build_moba_connected_session_state(Profile(name="web", protocol="https", url="https://example.com"))

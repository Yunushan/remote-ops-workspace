from __future__ import annotations

import os

import pytest


@pytest.fixture
def gui_window(monkeypatch, tmp_path):
    if "QT_QPA_PLATFORM" not in os.environ:
        monkeypatch.setenv("QT_QPA_PLATFORM", "offscreen")
    monkeypatch.setenv("ROW_HOME", str(tmp_path / "row-home"))
    pytest.importorskip("PyQt6")
    from remote_ops_workspace.gui import create_main_window

    app, window = create_main_window(
        ["gui-product-transfer-edges"],
        show=False,
        preview_samples=False,
    )
    window.resize(1120, 760)
    window.show()
    app.processEvents()
    yield app, window
    window.close()
    app.processEvents()


def test_product_file_transfer_and_snippet_handlers(gui_window) -> None:
    from PyQt6.QtCore import QSize
    from PyQt6.QtWidgets import QFrame, QLabel, QToolButton

    from remote_ops_workspace.gui_designs import (
        gui_design_remmina_sftp_transfer_route,
        gui_design_securecrt_sftp_browser_route,
        gui_design_termius_files_browser_route,
        gui_design_termius_snippet_route,
    )

    _app, window = gui_window

    termius_panel = window.build_termius_files_browser_evidence()
    termius_route = gui_design_termius_files_browser_route()
    window.handle_termius_files_sync()
    assert termius_panel.property(termius_route.captured_property) is True
    assert termius_panel.property(termius_route.captured_action_property)
    window.handle_termius_files_sync("upload")
    assert termius_panel.property(termius_route.captured_action_property) == "upload"
    assert "upload queued" in window.termius_files_queue.text()

    remmina_panel = window.build_remmina_sftp_transfer_evidence()
    remmina_route = gui_design_remmina_sftp_transfer_route()
    window.handle_remmina_sftp_transfer_action()
    assert remmina_panel.property(remmina_route.captured_property) is True
    window.handle_remmina_sftp_transfer_action("download")
    assert remmina_panel.property(remmina_route.captured_action_property) == "download"
    assert "download queued" in window.remmina_sftp_transfer_queue.text()

    securecrt_panel = window.build_securecrt_sftp_browser_evidence()
    securecrt_route = gui_design_securecrt_sftp_browser_route()
    window.handle_securecrt_sftp_browser_action()
    assert securecrt_panel.property(securecrt_route.captured_property) is True
    window.handle_securecrt_sftp_browser_action("download")
    assert (
        securecrt_panel.property(securecrt_route.captured_action_property)
        == "download"
    )
    assert "download queued" in window.securecrt_sftp_queue.text()

    snippet_route = gui_design_termius_snippet_route()
    snippet_widgets = [QFrame(), QLabel(), QToolButton()]
    window.termius_snippet_workflow_panel = snippet_widgets[0]
    window.termius_snippet_card = snippet_widgets[1]
    window.termius_snippet_title = None
    window.termius_snippet_primary = snippet_widgets[2]
    window.termius_snippet_secondary = None
    window.termius_snippet_action = None
    window.termius_snippet_shortcut = None
    window.termius_snippet_identity_panel = None
    window.termius_snippet_identity_cell = None
    window.handle_termius_snippet_run()
    assert snippet_widgets[0].property(snippet_route.captured_property) is True
    assert (
        snippet_widgets[0].property(snippet_route.captured_command_property)
        == snippet_route.snippet_command
    )

    for attr in (
        "termius_files_queue",
        "termius_files_identity_panel",
        "termius_files_identity_cell",
        "termius_files_browser_panel",
        "termius_files_toolbar",
        "termius_files_path",
        "termius_files_table",
        "termius_files_active_row",
        "remmina_sftp_transfer_queue",
        "remmina_sftp_profile_panel",
        "remmina_sftp_profile_row",
        "remmina_sftp_transfer_panel",
        "remmina_sftp_transfer_toolbar",
        "remmina_sftp_transfer_path",
        "remmina_sftp_transfer_table",
        "remmina_sftp_transfer_active_row",
        "securecrt_sftp_queue",
        "securecrt_sftp_browser_panel",
        "securecrt_sftp_toolbar",
        "securecrt_sftp_path",
        "securecrt_sftp_table",
        "securecrt_sftp_active_row",
    ):
        setattr(window, attr, None)
    window.termius_files_action_buttons = [None]
    window.remmina_sftp_transfer_action_buttons = [None]
    window.securecrt_sftp_action_buttons = [None]
    window.handle_termius_files_sync("mkdir")
    window.handle_remmina_sftp_transfer_action("upload")
    window.handle_securecrt_sftp_browser_action("download")

    for icon_key in ("folder", "properties", "connect"):
        icon = window.securecrt_session_manager_action_icon(icon_key, size=16)
        assert not icon.pixmap(QSize(16, 16)).isNull()


def test_product_host_action_dispatch_and_generated_icon_edges(
    gui_window,
    monkeypatch,
) -> None:
    from PyQt6.QtCore import QSize

    _app, window = gui_window
    calls: list[tuple[str, object]] = []
    monkeypatch.setattr(
        window,
        "connect_selected",
        lambda dry_run: calls.append(("connect", dry_run)),
    )
    monkeypatch.setattr(
        window,
        "create_profile",
        lambda: calls.append(("create", None)),
    )
    monkeypatch.setattr(
        window,
        "edit_selected_profile",
        lambda: calls.append(("edit", None)),
    )
    monkeypatch.setattr(
        window,
        "refresh_profiles",
        lambda: calls.append(("refresh", None)),
    )

    for key in ("connect", "new-folder", "properties", "unknown"):
        window.run_securecrt_session_manager_action(key)
    for key in ("new-host", "keychain", "sync-hosts", "unknown"):
        window.run_termius_hosts_action(key)
    assert calls == [
        ("connect", False),
        ("create", None),
        ("edit", None),
        ("create", None),
        ("refresh", None),
    ]
    assert window.termius_hosts_icon_name("plus")
    assert window.termius_hosts_icon_name("key")
    assert window.termius_hosts_icon_name("sync")
    assert window.termius_hosts_icon_name("unknown") == "SP_FileIcon"

    for icon_key in (
        "arrow-left",
        "arrow-right",
        "close",
        "clip",
        "spark",
        "gear",
        "unknown",
    ):
        icon = window.moba_utility_icon(icon_key, "#33bb99")
        assert not icon.pixmap(QSize(20, 20)).isNull()

    for icon_key, group in (
        ("folder", True),
        ("database", False),
        ("sftp", False),
        ("pin", False),
        ("shell", False),
        ("command", False),
        ("ssh", False),
        ("ssh2", False),
        ("host", False),
        ("rdp", False),
        ("vnc", False),
        ("snippet", False),
        ("unknown", False),
    ):
        icon = window.profile_tree_generated_icon(
            icon_key,
            group=group,
            size=16,
        )
        assert not icon.pixmap(QSize(16, 16)).isNull()

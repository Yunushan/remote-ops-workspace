from __future__ import annotations

from pathlib import Path

from remote_ops_workspace.cli import build_parser
from remote_ops_workspace.moba_ssh_browser import (
    build_moba_ssh_browser_open_plan,
    load_moba_ssh_browser_preferences,
    review_moba_ssh_browser_overwrite,
    update_moba_ssh_browser_columns,
    update_moba_ssh_browser_location,
)
from remote_ops_workspace.models import Profile


def test_moba_ssh_browser_defaults_to_side_by_side_and_saved_columns(tmp_path: Path) -> None:
    preferences = load_moba_ssh_browser_preferences(tmp_path / "missing.json")

    assert preferences.location == "side-by-side"
    assert preferences.overwrite_confirmation is True
    assert preferences.column_widths == {"name": 182, "size": 78, "modified": 94}


def test_moba_ssh_browser_location_and_columns_persist(tmp_path: Path) -> None:
    state = tmp_path / "ssh-browser.json"

    update_moba_ssh_browser_location("below-terminal", path=state)
    update_moba_ssh_browser_columns({"name": 240, "size": 90}, path=state)
    loaded = load_moba_ssh_browser_preferences(state)

    assert loaded.location == "below-terminal"
    assert loaded.column_widths["name"] == 240
    assert loaded.column_widths["size"] == 90
    assert loaded.column_widths["modified"] == 94


def test_moba_ssh_browser_open_plan_uses_same_sftp_parameters(tmp_path: Path) -> None:
    state = tmp_path / "ssh-browser.json"
    preferences = update_moba_ssh_browser_columns({"name": 220}, path=state)
    profile = Profile(
        name="edge",
        protocol="ssh",
        host="192.0.2.10",
        username="admin",
        port=2222,
        options={"compression": "true", "ssh_browser": "true"},
    )

    plan = build_moba_ssh_browser_open_plan(profile, preferences=preferences)

    assert plan.location == "side-by-side"
    assert plan.terminal_visible is True
    assert plan.browser_visible is True
    assert plan.command[0] == "sftp"
    assert plan.command[plan.command.index("-P") + 1] == "2222"
    assert plan.command[-1] == "admin@192.0.2.10"
    assert plan.column_widths["name"] == 220
    assert any("same SSH/SFTP parameters" in note for note in plan.notes)


def test_moba_ssh_browser_overwrite_review_blocks_existing_destination() -> None:
    review = review_moba_ssh_browser_overwrite(
        "upload",
        "build.tar.gz",
        "/tmp/build.tar.gz",
        destination_exists=True,
    )

    assert review.allowed is False
    assert review.confirmation_required is True
    assert "confirm" in review.prompt


def test_moba_ssh_browser_overwrite_review_allows_force() -> None:
    review = review_moba_ssh_browser_overwrite(
        "download",
        "/etc/hosts",
        "hosts.copy",
        destination_exists=True,
        force=True,
    )

    assert review.allowed is True
    assert review.confirmation_required is False
    assert any("force" in note.lower() for note in review.notes)


def test_moba_ssh_browser_rejects_invalid_column_width(tmp_path: Path) -> None:
    try:
        update_moba_ssh_browser_columns({"name": 8}, path=tmp_path / "ssh-browser.json")
    except ValueError as exc:
        assert "column width" in str(exc)
    else:
        raise AssertionError("invalid column widths must be rejected")


def test_moba_ssh_browser_cli_commands_are_registered() -> None:
    parser = build_parser()
    status = parser.parse_args(["ssh-browser", "status", "--json"])
    location = parser.parse_args(["ssh-browser", "location", "side-by-side"])
    columns = parser.parse_args(["ssh-browser", "columns", "--name", "220"])
    open_plan = parser.parse_args(["ssh-browser", "open-plan", "edge", "--json"])
    overwrite = parser.parse_args(["ssh-browser", "overwrite", "upload", "a", "b", "--destination-exists"])

    assert status.func.__name__ == "cmd_ssh_browser_status"
    assert location.func.__name__ == "cmd_ssh_browser_location"
    assert columns.func.__name__ == "cmd_ssh_browser_columns"
    assert open_plan.func.__name__ == "cmd_ssh_browser_open_plan"
    assert overwrite.func.__name__ == "cmd_ssh_browser_overwrite"

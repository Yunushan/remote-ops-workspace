from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

from remote_ops_workspace.first_run import first_run_json, first_run_payload, format_first_run
from remote_ops_workspace.storage import example_profiles


def test_first_run_payload_uses_existing_profile_for_dry_run(tmp_path: Path) -> None:
    payload = first_run_payload(
        data_dir=tmp_path,
        profiles_file=tmp_path / "profiles.json",
        profile_names=["example-rdp", "example-ssh"],
    )

    commands = [step["command"] for step in payload["next_steps"]]
    assert "row doctor" in commands
    assert "row profile list" in commands
    assert "row connect example-ssh --dry-run" in commands
    assert "row gui" in commands
    assert "row serve-web --host 127.0.0.1 --port 8765" in commands


def test_first_run_payload_guides_empty_profile_store(tmp_path: Path) -> None:
    payload = first_run_payload(
        data_dir=tmp_path,
        profiles_file=tmp_path / "profiles.json",
        profile_names=[],
    )
    text = format_first_run(payload)

    assert "row profile add --name prod-ssh" in text
    assert "ssh.example.invalid" in text
    assert "docs/PLUGIN_DEVELOPMENT.md" in text
    assert json.loads(first_run_json(payload))["profile_count"] == 0


def test_example_profiles_use_clearly_fake_hostnames() -> None:
    examples = {profile.name: profile for profile in example_profiles()}

    assert examples["example-ssh"].host == "ssh.example.invalid"
    assert examples["example-rdp"].host == "rdp.example.invalid"
    for name in ["edge-prod", "files-prod", "win-admin", "linux-console", "sftp-ops", "jump-host", "prod-cluster"]:
        assert str(examples[name].host).endswith(".example.invalid")
    assert not any(str(profile.host or "").startswith("192.0.2.") for profile in examples.values())


def test_first_run_ux_checker_passes_current_tree() -> None:
    checker = _load_checker()

    assert checker.main() == 0


def _load_checker():
    path = Path("scripts/check_first_run_ux.py")
    spec = importlib.util.spec_from_file_location("check_first_run_ux_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module

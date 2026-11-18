from __future__ import annotations

import base64
import shlex
from dataclasses import replace
from pathlib import Path

import pytest

from remote_ops_workspace.file_transfer import build_sftp_list_plan
from remote_ops_workspace.launcher import LauncherError, build_launch_plan
from remote_ops_workspace.moba_smartcards import update_smartcard_profile_key
from remote_ops_workspace.models import Profile
from remote_ops_workspace.profile_validation import normalize_group_defaults
from remote_ops_workspace.smartcard_keys import PINNED_SMARTCARD_KEY
from remote_ops_workspace.terminal import terminal_plan_for_profile

KEY = "ssh-ed25519 " + base64.b64encode(b"\x00\x00\x00\x0bssh-ed25519\x00\x00\x00\x20" + b"r" * 32).decode()


def test_saved_public_key_drives_ssh_sftp_scp_mosh_and_recreates_local_file(tmp_path, monkeypatch):
    first_home = tmp_path / "profile home with 100% spaces"
    monkeypatch.setenv("ROW_HOME", str(first_home))
    profile = Profile(name="card", protocol="ssh", host="remote.invalid", identity_file="usual-private-key",
                      options={"smartcard_fingerprint_sha256": "a" * 64, "pkcs11_provider": "/other.so",
                               "smart_card_provider": "pkcs11:/another.so", "strict_host_key_checking": "yes"})
    bound = update_smartcard_profile_key(profile, "/vendor/Token Middleware.so", KEY)
    assert "pkcs11_provider" not in bound.options and "smart_card_provider" not in bound.options
    assert "smartcard_fingerprint_sha256" not in bound.options
    assert bound.options["smartcard_certificate_id"].startswith("SHA256:")
    assert bound.identity_file == "usual-private-key"
    bound.options["pkcs11_provider"] = "/inherited/provider.so"

    commands = [build_launch_plan(replace(bound, protocol=protocol)).command for protocol in ("ssh", "sftp", "scp", "mosh")]
    commands[-1] = shlex.split(commands[-1][2])
    commands += [build_sftp_list_plan(bound).command, terminal_plan_for_profile(bound).command]
    paths = set()
    for argv in commands:
        assert "IdentitiesOnly=yes" in argv and "usual-private-key" not in argv
        assert not any("/inherited/provider.so" in arg for arg in argv)
        assert "-i" not in argv
        assert "ControlMaster=no" in argv and "ControlPath=none" in argv
        options = [arg for arg in argv if arg.startswith("IdentityFile=")]
        assert len(options) == 1 and "100%%" in options[0]
        path = options[0].removeprefix('IdentityFile="').removesuffix('"')
        paths.add(Path(path.replace("\\\\", "\\").replace("%%", "%")))
    assert len(paths) == 1
    identity = paths.pop()
    assert identity.parent == first_home.resolve() / "smartcard-identities"
    assert identity.read_bytes() == KEY.encode() + b"\n"

    second_home = tmp_path / "relocated profile"
    monkeypatch.setenv("ROW_HOME", str(second_home))
    restored = Profile.from_dict(bound.to_dict())
    fresh = build_launch_plan(restored).command
    option = next(arg for arg in fresh if arg.startswith("IdentityFile="))
    recreated = Path(option.removeprefix('IdentityFile="').removesuffix('"').replace("\\\\", "\\"))
    assert recreated == second_home.resolve() / "smartcard-identities" / identity.name
    assert recreated.read_bytes() == identity.read_bytes()


def test_existing_same_key_certificate_and_profile_options_survive_binding_and_clear(tmp_path, monkeypatch):
    monkeypatch.setenv("ROW_HOME", str(tmp_path))
    profile = Profile(name="card", protocol="ssh", host="remote.invalid", identity_file="usual-key",
                      options={"smartcard_public_key": KEY + " saved comment", "smartcard_fingerprint_sha256": "b" * 64,
                               "add_smartcard_to_mobagent": "true", "compression": "true"})
    assert update_smartcard_profile_key(profile, "", None) is profile
    bound = update_smartcard_profile_key(profile, "/vendor.so", KEY)
    assert bound.options["smartcard_fingerprint_sha256"] == "b" * 64
    cleared = update_smartcard_profile_key(bound, "", None)
    assert cleared.options["smartcard_provider"] == "pkcs11:/vendor.so"
    assert cleared.options["add_smartcard_to_mobagent"] == "true"
    assert cleared.options["compression"] == "true"
    assert PINNED_SMARTCARD_KEY not in cleared.options
    assert "smartcard_certificate_id" not in cleared.options and "smartcard_fingerprint_sha256" not in cleared.options
    command = build_launch_plan(cleared).command
    assert command[command.index("-i") + 1] == "usual-key"
    assert "IdentitiesOnly=yes" not in command
    with pytest.raises(ValueError, match="Select an SSH profile"):
        update_smartcard_profile_key(replace(profile, protocol="sftp"), "/vendor.so", KEY)
    with pytest.raises(ValueError, match="profile-only security options"):
        normalize_group_defaults({"options": {PINNED_SMARTCARD_KEY: KEY}})


@pytest.mark.parametrize("record", ["", "ssh-ed25519 @@@!", KEY + " trailing comment", "é"])
def test_invalid_saved_key_stops_planning(tmp_path, monkeypatch, record):
    monkeypatch.setenv("ROW_HOME", str(tmp_path))
    profile = Profile(name="card", protocol="ssh", host="remote.invalid", options={PINNED_SMARTCARD_KEY: record})
    with pytest.raises(LauncherError, match="Cannot use the saved smart-card key"):
        build_launch_plan(profile)
    assert not (tmp_path / "smartcard-identities").exists()


def test_pinned_key_fails_closed_on_unsafe_workspace_path_or_unavailable_storage(tmp_path, monkeypatch):
    profile = Profile(name="card", protocol="ssh", host="remote.invalid", options={PINNED_SMARTCARD_KEY: KEY})
    monkeypatch.setenv("ROW_HOME", str(tmp_path / "literal-${HOME}"))
    with pytest.raises(LauncherError, match="workspace path contains an OpenSSH environment expansion"):
        build_launch_plan(profile)
    monkeypatch.setenv("ROW_HOME", str(tmp_path))
    (tmp_path / "smartcard-identities").write_text("occupied")
    with pytest.raises(LauncherError, match="Cannot use the saved smart-card key"):
        build_launch_plan(profile)


@pytest.mark.parametrize(("options", "agent"), [
    ({}, None),
    ({"identity_agent": "none", "add_smartcard_to_mobagent": "true"}, None),
    ({"identity_agent": "/tmp/agent"}, "/tmp/agent"),
    ({"add_smartcard_to_mobagent": "true"}, "SSH_AUTH_SOCK"),
])
def test_pinned_key_uses_exactly_one_private_key_source(tmp_path, monkeypatch, options, agent):
    monkeypatch.setenv("ROW_HOME", str(tmp_path))
    profile = Profile(name="card", protocol="ssh", host="remote.invalid", options=options)
    selected = update_smartcard_profile_key(profile, "/vendor/provider.so", KEY)
    direct = build_launch_plan(selected).command
    transfer = build_sftp_list_plan(selected).command
    if agent is None:
        assert "IdentityAgent=none" in direct and "IdentityAgent=none" in transfer
        assert direct[direct.index("-I") + 1] == "/vendor/provider.so"
        assert 'PKCS11Provider="/vendor/provider.so"' in transfer
    else:
        for command in (direct, transfer):
            assert "-I" not in command and "/vendor/provider.so" not in " ".join(command)
            assert f"IdentityAgent={agent}" in command and "PKCS11Provider=none" in command

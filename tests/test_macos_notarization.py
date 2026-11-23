from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from scripts import macos_notarization as notary

SUBMISSION_ID = "22a164ab-54fb-4b39-a349-094d70c323bc"


@pytest.fixture
def run_notary(tmp_path, monkeypatch):
    def run(extension, *, status="Accepted", log_updates=None, change_during=None, fail_command=None):
        artifact = tmp_path / f"candidate.{extension}"
        artifact.write_bytes(b"signed package before stapling")
        original = notary.sha256_file(artifact)
        commands = []
        log_files = []

        def fake_run(command, *, check, stdout=None):
            assert check is True
            commands.append(command)
            if command[:3] == ["xcrun", "notarytool", "submit"]:
                assert stdout == subprocess.PIPE
                return subprocess.CompletedProcess(command, 0, json.dumps({"id": SUBMISSION_ID, "status": status}).encode())
            if command[:3] == ["xcrun", "notarytool", "log"]:
                log = {
                    "logFormatVersion": 1, "statusCode": 0, "status": "Accepted", "jobId": SUBMISSION_ID.upper(),
                    "archiveFilename": artifact.name, "sha256": original, "issues": None,
                }
                result = Path(command[-1])
                result.write_text(json.dumps(log | (log_updates or {})), encoding="utf-8")
                log_files.append(result)
                if change_during == "log":
                    artifact.write_bytes(b"other package after submission")
            if command[:3] == ["xcrun", "stapler", "staple"]:
                artifact.write_bytes(artifact.read_bytes() + b" and stapled ticket")
            if command[0] == "spctl" and change_during == "verify":
                artifact.write_bytes(b"other package during verification")
            if fail_command == command[:3]:
                raise subprocess.CalledProcessError(1, command)
            return subprocess.CompletedProcess(command, 0)

        monkeypatch.setattr(notary.subprocess, "run", fake_run)
        return artifact, original, commands, log_files

    return run


@pytest.mark.parametrize("extension", ["pkg", "dmg"])
def test_macos_notarization_binds_apple_upload_and_verified_ticket(run_notary, extension) -> None:
    artifact, original, commands, logs = run_notary(extension)
    receipt = notary.notarize(artifact, profile="fixture", keychain="/test/keychain")

    assert receipt == {
        "archive": artifact.name, "status": "Accepted", "submission_id": SUBMISSION_ID,
        "submitted_sha256": original, "stapled_sha256": notary.sha256_file(artifact),
    }
    assert receipt["stapled_sha256"] != original
    arguments = ["--keychain-profile", "fixture", "--keychain", "/test/keychain"]
    assert commands[:4] == [
        ["xcrun", "notarytool", "submit", str(artifact), *arguments, "--wait", "--output-format", "json"],
        ["xcrun", "notarytool", "log", SUBMISSION_ID, *arguments, str(logs[0])],
        ["xcrun", "stapler", "staple", str(artifact)],
        ["xcrun", "stapler", "validate", str(artifact)],
    ]
    assert commands[4][0] == ("pkgutil" if extension == "pkg" else "codesign")
    assert commands[5][:4] == ["spctl", "--assess", "--type", "install" if extension == "pkg" else "open"]
    assert not logs[0].exists()


@pytest.mark.parametrize("updates", [
    {"sha256": "1" * 64},
    {"archiveFilename": "different.pkg"},
    {"jobId": "6f3d5918-ec01-4650-88ee-cce5ff28c218"},
    {"status": "Invalid"},
    {"statusCode": True},
    {"logFormatVersion": 2},
])
def test_macos_notarization_refuses_an_unbound_apple_log(run_notary, updates) -> None:
    artifact, original, commands, _ = run_notary("pkg", log_updates=updates)

    with pytest.raises(ValueError, match="does not match the accepted upload"):
        notary.notarize(artifact, profile="fixture")
    assert len(commands) == 2
    assert notary.sha256_file(artifact) == original


@pytest.mark.parametrize("status", ["Invalid", "In Progress", "Rejected", None])
def test_macos_notarization_checks_apple_status_even_on_success_exit(run_notary, status) -> None:
    artifact, _, commands, _ = run_notary("dmg", status=status)

    with pytest.raises(ValueError, match="did not accept"):
        notary.notarize(artifact, profile="fixture")
    assert len(commands) == 1


@pytest.mark.parametrize("stage", ["log", "verify"])
def test_macos_notarization_checks_artifact_identity_within_each_phase(run_notary, stage) -> None:
    artifact, _, _, _ = run_notary("pkg", change_during=stage)

    with pytest.raises(ValueError, match="changed"):
        notary.notarize(artifact, profile="fixture")


def test_macos_notarization_refuses_failed_stapled_ticket_validation(run_notary) -> None:
    artifact, _, commands, _ = run_notary("dmg", fail_command=["xcrun", "stapler", "validate"])
    with pytest.raises(subprocess.CalledProcessError):
        notary.notarize(artifact, profile="fixture")
    assert not any(command[0] == "spctl" for command in commands)


@pytest.mark.parametrize("production", [False, True])
def test_native_macos_manifest_seals_the_verified_ticket_digest(tmp_path, production) -> None:
    root = Path.cwd()
    build = Path(__file__).resolve().parents[1] / "scripts/make_macos_native.sh"
    script = build.read_text(encoding="utf-8").rsplit("<<'PY'\n", 1)[1].removesuffix("\nPY\n")
    assets = {}
    for index, extension in enumerate(("dmg", "pkg")):
        asset = tmp_path / f"candidate.{extension}"
        assets[extension] = asset
        asset.write_bytes(f"stapled {extension}".encode())
        receipt = {
            "archive": asset.name, "status": "Accepted", "submission_id": SUBMISSION_ID[:-1] + str(index),
            "submitted_sha256": "1" * 64, "stapled_sha256": notary.sha256_file(asset),
        }
        if production:
            (tmp_path / f"notary-{extension}.json").write_text(json.dumps(receipt), encoding="utf-8")
    command = [sys.executable, "-", str(root), "1.0.28", str(assets["dmg"]), str(assets["pkg"]),
               "arm64", str(tmp_path), "1" if production else "0", str(tmp_path)]
    # The builder stores repo-relative paths. Provide its script imports in a
    # disposable checkout-shaped directory beside the fixtures.
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    (scripts / "macos_notarization.py").write_bytes((root / "scripts/macos_notarization.py").read_bytes())
    command[2] = str(tmp_path)
    result = subprocess.run(command, input=script, capture_output=True, text=True, timeout=10, check=False)
    assert result.returncode == 0, result.stderr
    manifest = tmp_path / "remote-ops-workspace-v1.0.28-macos-arm64-native-manifest.json"
    for row in json.loads(manifest.read_bytes()):
        assert ("notarization" in row) is production
        if production:
            assert row["sha256"] == row["notarization"]["stapled_sha256"]
    if production:
        assets["pkg"].write_bytes(b"changed after ticket verification")
        result = subprocess.run(command, input=script, capture_output=True, text=True, timeout=10, check=False)
        assert result.returncode == 1 and "must bind the accepted upload" in result.stderr

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import check_native_frozen_cron as smoke


def test_windows_frozen_cron_is_bound_to_the_exercised_portable_bytes(tmp_path):
    row = tmp_path / "row.exe"
    row.write_bytes(b"one-file candidate fixture")
    digest = hashlib.sha256(row.read_bytes()).hexdigest()
    binding = {
        "schema_version": 1, "target": "windows-arm64", "status": "bound", "smoke_complete": True,
        "expected_executables": [{"role": "cli", "path": smoke.CLI, "sha256": digest, "size": row.stat().st_size}],
        "observations": [{"path": "portable/bin/row.exe", "expected_sha256": digest,
                          "observed_sha256": digest, "matched": True}],
    }
    assert smoke.verify_candidate(row, binding, "windows-arm64") == digest
    with pytest.raises(ValueError, match="native candidate"):
        smoke.verify_candidate(row, binding, "windows-x86")
    binding["observations"][0]["matched"] = False
    with pytest.raises(ValueError, match="native candidate"):
        smoke.verify_candidate(row, binding, "windows-arm64")


def test_macos_frozen_cron_requires_intact_installer_qualified_app_bundle(tmp_path):
    bundle = tmp_path / smoke.MAC_APP
    row = bundle / smoke.MAC_LAUNCHER
    row.parent.mkdir(parents=True)
    row.write_bytes(b"macOS CLI launcher fixture")
    member = bundle / "Contents/fixture.dat"
    member.write_bytes(b"frozen bundle fixture")
    digest = hashlib.sha256(row.read_bytes()).hexdigest()
    inventory = smoke.app_bundle_inventory(bundle)
    binding = {
        "schema_version": 2, "target": "macos-arm64", "status": "bound", "smoke_complete": True,
        "expected_executables": [{"role": "gui", "path": smoke.MAC_CLI, "sha256": digest}],
        "expected_app_bundle": {"path": smoke.MAC_APP_SOURCE, **inventory},
        "app_bundle_observations": [{"path": f"{kind}/{smoke.MAC_APP}", "phase": phase, "matched": True, "inventory": inventory}
                                    for kind in ("pkg","dmg") for phase in ("install","reinstall")],
        "observations": [{"path": f"{kind}/{smoke.MAC_APP}/{smoke.MAC_LAUNCHER}", "expected_sha256": digest,
                          "observed_sha256": digest, "matched": True} for kind in ("dmg","pkg")],
    }
    assert smoke.verify_candidate(row, binding, "macos-arm64") == digest
    member.write_bytes(b"unexpected replacement")
    with pytest.raises(ValueError, match="bundle differs"):
        smoke.verify_candidate(row, binding, "macos-arm64")


COMMON_CASES = [
    ("none", ""), ("wrong-runtime", "process identity"), ("missing-job", "first real minute"),
    ("stale-worker", "did not release"), ("repeated-job", "continued scheduling"),
    ("leftover-extraction", "extraction directory"), ("cli-failure", "start failed"),
]


@pytest.mark.parametrize(("mac", "fault", "failure"), [
    *((mac, fault, failure) for mac in (False, True) for fault, failure in COMMON_CASES),
    (True, "status-generation", "active generation"),
    (True, "stop-generation", "revoke its original generation"),
])
def test_frozen_cron_acceptance_requires_effect_and_natural_stop(tmp_path, monkeypatch, fault, failure, mac):
    elapsed = [5.0]
    stopped = []
    token = []
    marker = tmp_path / "cron-marker.txt"
    identity = {"kind": "owned" if mac else "windows", "pid": 42}
    state_path = tmp_path / "servers.json"
    generation = "1" * 32
    launcher = tmp_path / "row"
    table = tmp_path / "crontab"

    def command(args, *, cwd, env, **kwargs):
        assert cwd == tmp_path and Path(env["ROW_HOME"]).parent == tmp_path
        assert env["USERPROFILE"] == env["HOME"] == str(tmp_path)
        assert "PYTHONPATH" not in env and "PYTHONHOME" not in env
        assert Path(env["TEMP"]).is_relative_to(tmp_path) and kwargs["timeout"] > 0
        if args[2] == "start":
            token.append((cwd / "crontab").read_text().split()[6])
            if fault == "cli-failure":
                return SimpleNamespace(returncode=1, stderr="refusal")
            payload = {"lifecycle": {"state": "started", "service": "cron", "running": True, "pid": 42,
                                     "process_identity": identity, "runtime_key": "other" if fault == "wrong-runtime" else "row-cron",
                                     "cron_generation": generation, "state_path": str(state_path)}}
        elif args[2] == "status":
            assert mac
            payload = {"services":[{"key":"cron","lifecycle":{"state":"stopped" if stopped else "started",
                                  "running":not stopped,"port":0,"host":"","pid":None if stopped else 42,
                                  "cron_generation":"2" * 32 if fault == "status-generation" else generation,
                                  "process_identity":identity}}]}
        else:
            assert args[2:4] == ["stop", "cron"]
            stopped.append(True)
            payload = {"state": "stopped", "running": False, "pid": None, "process_identity": identity}
            if fault == "leftover-extraction":
                (tmp_path / "temp/_MEIleftover").mkdir()
            revoked = "2" * 32 if fault == "stop-generation" else generation
            state_path.with_suffix(".control").write_text(f"revoked {revoked}")
        return SimpleNamespace(returncode=0, stdout=json.dumps(payload))

    def advance(duration):
        elapsed[0] += duration
        if stopped and fault == "repeated-job":
            marker.write_text(f"{token[0]}\n{token[0]}\n")
        elif not stopped and fault != "missing-job":
            marker.write_text(token[0] + "\n")

    monkeypatch.setattr(smoke.subprocess, "run", command)
    monkeypatch.setattr(smoke, "time", SimpleNamespace(time=lambda: elapsed[0], monotonic=lambda: elapsed[0], sleep=advance))
    monkeypatch.setattr(smoke, "recorded_process_is_running", lambda pid, record: not stopped or fault == "stale-worker")
    start_time = "Sun Nov 22 08:05:00 2026"
    observed = f"{start_time} {launcher} servers _cron-runtime --crontab {table}"
    monkeypatch.setattr(smoke, "darwin_process", lambda pid: observed if not stopped else
                        f"{start_time} (zombie)" if fault == "stale-worker" else "")
    if mac and fault == "stale-worker":
        failure = "survived stop"
    if failure:
        with pytest.raises(RuntimeError, match=failure):
            smoke.capture(launcher, tmp_path, mac=mac)
    else:
        assert smoke.capture(launcher, tmp_path, mac=mac)["next_minute_quiet"]
    assert stopped == [True]


def test_native_targets_require_frozen_cron_and_windows_job_drain():
    native = (smoke.ROOT / ".github/workflows/native-candidate-validation.yml").read_text()
    job = native.split("  windows-native:", 1)[1].split("  macos-native:", 1)[0]
    step = job.split("      - name: Verify frozen Cron", 1)[1].split("      - name:", 1)[0]
    assert "if:" not in step
    assert "candidate_windows_owned.py --timeout 175 --drain-descendants" in step
    assert 'windows-${{ matrix.arch }}/owned-cron.json' in step
    assert 'check_native_frozen_cron.py --target "windows-${{ matrix.arch }}"' in step
    job = native.split("  macos-native:", 1)[1].split("  linux-native:", 1)[0]
    step = job.split("      - name: Verify frozen Cron", 1)[1].split("      - name:", 1)[0]
    assert "if:" not in step
    assert 'check_native_frozen_cron.py --target "macos-${{ matrix.arch }}"' in step

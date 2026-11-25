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


def test_linux_frozen_cron_requires_the_installed_deb_and_loader_report(tmp_path):
    row = tmp_path / "row"
    deb = tmp_path / "remote-ops-workspace-v1.0.28-linux-arm64.deb"
    report = tmp_path / "deb-loader-selection.json"
    row.write_bytes(b"frozen launcher")
    deb.write_bytes(b"Debian package")
    binding = {
        "schema_version": 1, "target": "linux-aarch64", "kernel_machine": "aarch64",
        "deb": deb.name, "deb_sha256": smoke.sha256(deb), "launcher_sha256": smoke.sha256(row),
        "source_sha": "1" * 40, "staged_runpath_changes": {},
    }
    report.write_text(json.dumps(binding))
    result = smoke.verify_linux_candidate(row, deb, report, "linux-aarch64")
    assert result == {
        "row_sha256": binding["launcher_sha256"], "deb": deb.name, "deb_sha256": binding["deb_sha256"],
        "deb_loader_report_sha256": smoke.sha256(report), "source_sha": "1" * 40,
    }
    for key, value in (
        ("kernel_machine", "x86_64"), ("deb", "other.deb"), ("deb_sha256", "2" * 64),
        ("launcher_sha256", "3" * 64), ("staged_runpath_changes", None), ("source_sha", "invalid"),
    ):
        report.write_text(json.dumps({**binding, key: value}))
        with pytest.raises(ValueError, match="exact Debian package and launcher"):
            smoke.verify_linux_candidate(row, deb, report, "linux-aarch64")


COMMON_CASES = [
    ("none", ""), ("wrong-runtime", "process identity"), ("missing-job", "first real minute"),
    ("stale-worker", "did not release"), ("repeated-job", "continued scheduling"),
    ("leftover-extraction", "extraction directory"), ("cli-failure", "start failed"),
]


@pytest.mark.parametrize(("target", "fault", "failure"), [
    *((target, fault, failure) for target in ("windows-x64", "macos-x64", "linux-x86_64") for fault, failure in COMMON_CASES),
    *((target, fault, failure) for target in ("macos-x64", "linux-x86_64") for fault, failure in (
        ("status-generation", "active generation"), ("stop-generation", "revoke its original generation"),
    )),
])
def test_frozen_cron_acceptance_requires_effect_and_natural_stop(tmp_path, monkeypatch, fault, failure, target):
    mac = target.startswith("macos-")
    linux = target.startswith("linux-")
    elapsed = [5.0]
    stopped = []
    token = []
    marker = tmp_path / "cron-marker.txt"
    identity = {"kind": "owned" if mac else "linux" if linux else "windows", "pid": 42}
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
            assert mac or linux
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
            smoke.capture(launcher, tmp_path, target=target)
    else:
        assert smoke.capture(launcher, tmp_path, target=target)["next_minute_quiet"]
    assert stopped == [True]


def test_native_targets_require_frozen_cron_and_windows_job_drain():
    native = (smoke.ROOT / ".github/workflows/native-candidate-validation.yml").read_text()
    job = native.split("  windows-native:", 1)[1].split("  macos-native:", 1)[0]
    step = job.split("      - name: Verify frozen Cron", 1)[1].split("      - name:", 1)[0]
    assert "if:" not in step
    assert "candidate_windows_owned.py --timeout 175 --drain-descendants" in step
    assert 'windows-${{ matrix.arch }}/owned-cron.json' in step
    assert 'check_native_frozen_cron.py --target "windows-${{ matrix.arch }}"' in step
    assert 'windows-${{ matrix.arch }}/owned-cron.log' in step
    assert 'Get-Content -LiteralPath $log' in step and 'exit $probeExit' in step
    job = native.split("  macos-native:", 1)[1].split("  linux-native:", 1)[0]
    step = job.split("      - name: Verify frozen Cron", 1)[1].split("      - name:", 1)[0]
    assert "if:" not in step
    assert 'check_native_frozen_cron.py --target "macos-${{ matrix.arch }}"' in step
    script = (smoke.ROOT / "scripts/smoke_linux_native.sh").read_text()
    installed = script.split('echo "native installer smoke: DEB verify"', 1)[1].split('echo "native installer smoke: DEB upgrade"', 1)[0]
    assert installed.index("qualify_deb_loader.py") < installed.index("check_native_frozen_cron.py")
    assert 'check_native_frozen_cron.py --target "$BINDING_TARGET" --deb "$DEB" --proof-dir "$SMOKE_ROOT"' in installed


@pytest.mark.parametrize(("shift", "failure"), [
    (0.0, ""), (-0.125, ""), (0.125, ""),
    (-60.0, "did not reach the next minute"), (60.0, "jumped forward"),
])
def test_quiet_minute_handles_early_wakes_and_bounded_clock_adjustment(tmp_path, monkeypatch, shift, failure):
    marker = tmp_path / "marker"
    marker.write_bytes(b"one\n")
    elapsed = 0.0
    calls = 0

    def wall():
        return 58.0 + elapsed + (shift if calls else 0.0)

    def wake_early(duration):
        nonlocal elapsed, calls
        # Match an early wake without allowing synthetic time to stand still.
        elapsed += duration - 0.01 if duration >= 0.05 else duration
        calls += 1

    monkeypatch.setattr(smoke, "time", SimpleNamespace(time=wall, monotonic=lambda: elapsed, sleep=wake_early))
    if failure:
        with pytest.raises(RuntimeError, match=failure):
            smoke.verify_quiet_minute(marker, "one")
    else:
        smoke.verify_quiet_minute(marker, "one")
        assert elapsed >= 3.5 and wall() >= 61.5 and calls > 1
    assert elapsed <= 6.5


def test_quiet_minute_rejects_extra_job_before_observation_starts(tmp_path):
    marker = tmp_path / "marker"
    marker.write_bytes(b"one\none\n")
    with pytest.raises(RuntimeError, match="unexpected scheduled effects before"):
        smoke.verify_quiet_minute(marker, "one")

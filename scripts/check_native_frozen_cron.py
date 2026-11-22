"""Qualify Cron through the frozen Windows CLI or macOS application exercised by installer smoke."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import platform
import subprocess
import sys
import tempfile
import time
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT))

from remote_ops_workspace.process_status import recorded_process_is_running  # noqa: E402
from scripts.candidate_posix_byte_binding import (  # noqa: E402
    MAC_APP,
    MAC_APP_SOURCE,
    app_bundle_inventory,
    binding_schema,
    validate_app_bundle_observations,
)

CLI = "build/native/windows/pyinstaller-dist/row.exe"
MAC_LAUNCHER = "Contents/MacOS/Remote Ops Workspace"
MAC_CLI = f"{MAC_APP_SOURCE}/{MAC_LAUNCHER}"


def verify_candidate(row: Path, binding: dict, target: str) -> str:
    digest = hashlib.sha256(row.read_bytes()).hexdigest()
    mac = target.startswith("macos-")
    role, original_path = ("gui", MAC_CLI) if mac else ("cli", CLI)
    public_paths = {f"{kind}/{MAC_APP}/{MAC_LAUNCHER}" for kind in ("dmg", "pkg")} if mac else {"portable/bin/row.exe"}
    expected = [entry for entry in binding["expected_executables"] if entry["role"] == role]
    observed = [entry for entry in binding["observations"] if entry["path"] in public_paths]
    if not (
        binding["schema_version"] == binding_schema(target) and binding["target"] == target and binding["status"] == "bound"
        and binding["smoke_complete"] is True and len(expected) == 1 and expected[0]["path"] == original_path
        and expected[0]["sha256"] == digest and (mac or expected[0]["size"] == row.stat().st_size)
        and {item["path"] for item in observed} == public_paths
        and all(item["matched"] is True and item["expected_sha256"] == item["observed_sha256"] == digest for item in observed)
    ):
        raise ValueError("Cron probe executable differs from the qualified native candidate")
    if mac:
        validate_app_bundle_observations(binding, app_bundle_inventory(row.parents[2]))
    return digest


def darwin_process(pid: int) -> str:
    # Observe start time and full argv without signaling a persisted PID.
    seen = subprocess.run(["/bin/ps", "-ww", "-p", str(pid), "-o", "lstart=", "-o", "command="],
                          capture_output=True, text=True, timeout=5)
    if seen.returncode == 1 and not seen.stdout.strip() and not seen.stderr.strip():
        return ""
    seen.check_returncode()
    return seen.stdout.strip()


def capture(row: Path, home: Path, *, mac: bool) -> dict:
    # All supported shells resolve the relative job output inside the disposable home.
    extraction = home / "temp"
    extraction.mkdir()
    env = {**os.environ, "ROW_HOME": str(home / "row"), "USERPROFILE": str(home), "HOME": str(home),
           "TMP": str(extraction), "TEMP": str(extraction), "TMPDIR": str(extraction)}
    for key in ("PYTHONHOME", "PYTHONPATH"):
        env.pop(key, None)
    table, marker = home / "crontab", home / "cron-marker.txt"
    token = uuid.uuid4().hex
    table.write_text(f"* * * * * echo {token} >> cron-marker.txt\n", encoding="ascii")

    def cli(*args: str) -> dict:
        result = subprocess.run([str(row), "servers", *args, "--json"], cwd=home, env=env,
                                capture_output=True, text=True, encoding="utf-8", timeout=40)
        if result.returncode:
            raise RuntimeError(f"frozen Cron {args[0]} failed ({result.returncode}): {result.stderr[-500:]}")
        return json.loads(result.stdout)

    try:
        record = cli("start", "cron", "--crontab", str(table))["lifecycle"]
        pid, identity = record["pid"], record["process_identity"]
        process = darwin_process(pid) if mac else ""
        alive = (str(row) in process and "_cron-runtime" in process and str(table) in process
                 if mac else recorded_process_is_running(pid, identity))
        if not (record["state"] == "started" and record["service"] == "cron" and record["running"] is True
                and record["runtime_key"] == "row-cron" and identity["kind"] == ("owned" if mac else "windows") and alive):
            raise RuntimeError("frozen Cron did not record a running native process identity")
        if mac:
            generation = record["cron_generation"]
            if not generation or not isinstance(generation, str):
                raise RuntimeError("frozen Cron did not publish its generation")
            status, = (s["lifecycle"] for s in cli("status")["services"] if s["key"] == "cron")
            if (not status["running"] or status["pid"] != pid or status["cron_generation"] != generation
                    or status["process_identity"] != identity or status["host"] != "" or status["port"] != 0):
                raise RuntimeError("frozen Cron status did not observe the active generation")
        deadline = time.monotonic() + 69
        while True:
            try:
                if marker.read_text(encoding="ascii").split() == [token]:
                    break
            except (FileNotFoundError, PermissionError):
                # cmd.exe may still have the freshly created marker open.
                pass
            if time.monotonic() >= deadline:
                raise RuntimeError("no unique scheduled effect after the first real minute boundary")
            time.sleep(0.15)
    finally:
        # Windows additionally drains the native job's descendants after this probe.
        stopped = cli("stop", "cron")

    if stopped["state"] != "stopped" or stopped["running"] or stopped["pid"] is not None or stopped["process_identity"] != identity:
        raise RuntimeError("frozen Cron stop did not release the recorded process")
    if mac:
        closed, = (s["lifecycle"] for s in cli("status")["services"] if s["key"] == "cron")
        control = Path(record["state_path"]).with_suffix(".control")
        if (not control.is_relative_to(home) or control.read_text(encoding="utf-8") != f"revoked {generation}"
                or closed["running"] or closed["pid"] is not None or closed["state"] != "stopped"):
            raise RuntimeError("frozen Cron stop did not revoke its original generation")
    elif recorded_process_is_running(pid, identity):
        raise RuntimeError("frozen Cron stop did not release the recorded process")
    before = marker.read_bytes()
    next_minute = (int(time.time()) // 60 + 1) * 60 + 1.5
    time.sleep(max(0.0, min(62.0, next_minute - time.time())))
    if time.time() < next_minute or marker.read_bytes() != before or before.decode("ascii").split() != [token]:
        raise RuntimeError("frozen Cron continued scheduling or the next minute boundary was not observed")
    # lstart has five fields. A command name can change when a process becomes
    # a zombie; the birth time also distinguishes a newly reused PID.
    if mac and darwin_process(pid).split(maxsplit=5)[:5] == process.split(maxsplit=5)[:5]:
        raise RuntimeError("the original macOS Cron worker survived stop")
    if any(extraction.glob("_MEI*")):
        raise RuntimeError("frozen Cron left a one-file extraction directory after stop")
    return {"real_minute_job_count": 1, "stopped_pid_exited": True, "next_minute_quiet": True,
            **({"darwin_command_and_start_time_verified": True, "public_status_and_lease_verified": True} if mac
               else {"windows_process_identity_verified": True, "onefile_extraction_released": True})}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--target", choices=("windows-x86", "windows-x64", "windows-arm64", "macos-arm64", "macos-x64"), required=True)
    args = parser.parse_args()
    target = args.target
    mac = target.startswith("macos-")
    if mac:
        if sys.platform != "darwin" or platform.machine() != {"macos-arm64": "arm64", "macos-x64": "x86_64"}[target]:
            raise RuntimeError("matching native macOS target required")
    elif os.name != "nt":
        raise RuntimeError("native Windows required")
    proof = ROOT / "build/native-smoke" / target
    row = ROOT / (MAC_CLI if mac else CLI)
    binding = json.loads((proof / "candidate-runtime-byte-binding.json").read_text(encoding="utf-8-sig"))
    digest = verify_candidate(row, binding, target)
    with tempfile.TemporaryDirectory(prefix="row-frozen-cron-") as home:
        result = capture(row, Path(home).resolve(), mac=mac)
    receipt = {"schema": "row.native-frozen-cron.v1", "target": target, "row_sha256": digest, **result}
    (proof / "frozen-cron.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(f"{target} frozen CLI passed scheduled execution, stop and next-minute quiescence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

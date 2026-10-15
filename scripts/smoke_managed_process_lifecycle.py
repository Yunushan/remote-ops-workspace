"""Verify a real managed HTTP child, PID reuse refusal, exit and offline recovery."""
from __future__ import annotations

import argparse
import copy
import json
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

REPOSITORY = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPOSITORY / "src"))


def main() -> int:
    from remote_ops_workspace.moba_servers import (
        build_moba_server_plan,
        load_moba_server_record,
        start_moba_server,
        stop_moba_server,
    )
    from remote_ops_workspace.process_status import (
        ProcessIdentityError,
        process_is_running,
        register_process,
        terminate_owned_process,
        terminate_recorded_process,
    )
    from remote_ops_workspace.workspace_backup import (
        WorkspaceBackupError,
        create_workspace_backup,
        restore_workspace_backup,
    )

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    scratch = REPOSITORY / ".tmp"
    scratch.mkdir(exist_ok=True)
    children = []
    with tempfile.TemporaryDirectory(prefix="managed-lifecycle-", dir=scratch) as temporary:
        directory = Path(temporary).resolve()
        assert directory.is_relative_to(scratch.resolve())
        home = directory / "home"
        root = home / "public"
        root.mkdir(parents=True)
        content = b"managed lifecycle real HTTP proof\n"
        (root / "proof.txt").write_bytes(content)
        (home / "unknown-plugin-state.bin").write_bytes(bytes(range(256)))
        with socket.socket() as reservation:
            reservation.bind(("127.0.0.1", 0))
            port = reservation.getsockname()[1]
        state_dir = home / "servers"
        plan = build_moba_server_plan("http", root=root, port=port, which=lambda _name: None, packaged_roots=[])

        def spawn(command, env):
            process = subprocess.Popen(command, env=env, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            children.append(process)
            return process

        try:
            started = start_moba_server(plan, state_dir=state_dir, popen_factory=spawn)
            process = children[0]
            assert started.pid == process.pid and started.process_identity
            url = f"http://127.0.0.1:{port}/proof.txt"
            deadline = time.monotonic() + 10
            while True:
                try:
                    with urllib.request.urlopen(url, timeout=1) as response:
                        assert response.read() == content
                    break
                except (urllib.error.URLError, TimeoutError):
                    assert process.poll() is None
                    if time.monotonic() >= deadline:
                        raise RuntimeError("managed HTTP child did not become ready") from None
                    time.sleep(0.05)
            status = load_moba_server_record("http", state_dir=state_dir)
            assert status and status.running and process_is_running(process.pid)
            record_path = state_dir / "http-server-state.json"
            before_repeat = record_path.read_bytes()
            try:
                start_moba_server(plan, state_dir=state_dir, popen_factory=spawn)
            except ValueError as exc:
                assert "already running" in str(exc)
            else:
                raise AssertionError("repeated start replaced an active managed child")
            assert len(children) == 1 and process.poll() is None and record_path.read_bytes() == before_repeat
            archive = directory / "backup.json"
            try:
                create_workspace_backup(home, archive, "synthetic lifecycle proof passphrase", offline_confirmed=True)
            except WorkspaceBackupError as exc:
                assert "managed runtime" in str(exc)
            else:
                raise AssertionError("active lifecycle was accepted as offline")

            # Exercise a stale birth identity against our own live server. The
            # actual managed lifecycle file remains untouched throughout.
            stale_dir = directory / "stale-record"
            stale_dir.mkdir()
            stale = copy.deepcopy(started.to_dict())
            identity = stale["process_identity"]
            key = {"windows": "creation_time", "linux": "start_ticks", "owned": "token"}[identity["kind"]]
            identity[key] = identity[key] + 1 if key != "token" else "different-owned-child"
            stale_path = stale_dir / "http-server-state.json"
            stale_path.write_text(json.dumps(stale), encoding="utf-8")
            prior = stale_path.read_bytes()
            try:
                stop_moba_server("http", state_dir=stale_dir)
            except ProcessIdentityError:
                pass
            else:
                raise AssertionError("stale process identity was accepted")
            assert stale_path.read_bytes() == prior and process.poll() is None
            with urllib.request.urlopen(url, timeout=1) as response:
                assert response.read() == content

            stopped = stop_moba_server("http", state_dir=state_dir)
            assert stopped.pid is None and stopped.state == "stopped" and not stopped.running
            assert process.poll() is not None and not process_is_running(process.pid)
            assert json.loads(record_path.read_text())["pid"] is None
            create_workspace_backup(home, archive, "synthetic lifecycle proof passphrase", offline_confirmed=True)
            restored = directory / "restored"
            restore_workspace_backup(archive, restored, "synthetic lifecycle proof passphrase", current_home=home, offline_confirmed=True)
            assert (restored / "servers/http-server-state.json").read_bytes() == record_path.read_bytes()
            assert (restored / "unknown-plugin-state.bin").read_bytes() == bytes(range(256))

            # Independently confirm native read-only status and verified shutdown
            # for a dummy child with no listeners or existing user process.
            dummy = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            children.append(dummy)
            dummy_identity = register_process(dummy)
            assert process_is_running(dummy.pid)
            terminate_recorded_process(dummy.pid, dummy_identity)
            assert dummy.poll() is not None
            payload = {
                "schema": "row.managed-process-lifecycle-smoke.v1", "passed": True,
                "checked_at": datetime.now(timezone.utc).isoformat(),
                "platform": sys.platform, "identity_kind": started.process_identity["kind"],
                "actual_http_request_passed": True, "read_only_status_passed": True,
                "repeated_start_refused": True, "original_live_process_and_record_preserved": True,
                "active_workspace_backup_refused": True, "stale_identity_stop_refused": True,
                "stale_record_unchanged": True, "unrelated_live_instance_survived": True,
                "verified_stop_confirmed": True, "stop_cleared_pid": True,
                "normal_stop_then_backup_restore_passed": True,
                "unknown_plugin_bytes_preserved": True, "dummy_child_verified_stop_passed": True,
                "original_lifecycle_manually_edited": False,
            }
        finally:
            for child in children:
                terminate_owned_process(child)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    print(f"Managed process lifecycle smoke passed: {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

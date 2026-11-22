"""Exercise concurrent SSH session logging without requiring a Docker daemon."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest


@pytest.mark.skipif(sys.platform != "linux", reason="the SSH fixture runs in a Linux container")
def test_concurrent_ssh_children_share_one_pipe_to_the_evidence_log(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(Path(__file__).resolve().parents[1] / "scripts"))
    from run_qt_release_fixture import server_command

    # Run the fixture's startup shell without privileged account setup or a real daemon.
    command = "useradd() { :; }\ninstall() { :; }\n" + server_command("macro", "rowmacro")
    for source, local in (
        ("/run/sshd", "./run/sshd"), ("/tmp/sshd_config", "./config"),
        ("/log/sshd.log", "./sshd.log"), ("/usr/sbin/sshd", "sh ./daemon"),
    ):
        command = command.replace(source, local)
    (tmp_path / "daemon").write_text(
        """set -eu
test -p /dev/stderr
echo "$$"
for child in 1 2 3 4; do
    (
        line=0
        while [ "$line" -lt 128 ]; do
            printf 'session %s record %s\\n' "$child" "$line" >&2
            line=$((line + 1))
        done
    ) &
done
wait
""",
        encoding="ascii",
    )
    with (tmp_path / "startup-errors").open("w+", encoding="ascii") as errors, subprocess.Popen(
        ["sh", "-ec", command], cwd=tmp_path, stdout=subprocess.PIPE, stderr=errors, text=True,
    ) as process:
        stdout, _ = process.communicate(timeout=10)
        errors.seek(0)
        assert process.returncode == 0, errors.read()
        assert int(stdout) == process.pid

    records = (tmp_path / "sshd.log").read_text(encoding="ascii").splitlines()
    assert len(records) == 4 * 128
    for child in range(1, 5):
        prefix = f"session {child} record "
        assert [row for row in records if row.startswith(prefix)] == [f"{prefix}{line}" for line in range(128)]

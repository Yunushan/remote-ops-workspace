from __future__ import annotations

from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

from remote_ops_workspace import embedded_cron as cron


def test_crontab_matches_real_original_day_cases_and_parses_field_ranges():
    sunday = datetime(2026, 11, 22, 22, 6)
    entries = cron.parse_crontab(
        "# day-of-month and weekday match either restriction\n\n"
        "*/3 21-23 22 nov sun echo both\n"
        "1,6 22 22 NOV mon echo day\n"
        "6 22 23 11 7 echo weekday\n"
        "6 22 23 11 1 echo neither\n"
        "6 22 * * 1 echo not-Sunday\n"
        "6 22 23 * * echo not-day\n"
        "6 22 * * fri-mon echo weekend"
    )
    assert [entry.command for entry in entries if entry.due(sunday)] == ["echo both", "echo day", "echo weekday", "echo weekend"]
    assert not any(entry.due(datetime(2026, 11, 22, 5, 4)) for entry in entries)


@pytest.mark.parametrize("text", ["@reboot echo job", "61 * * * * job", "*/0 * * * * job", "* * * Noday * job",
                                  "a * * * * job", "* * * * * bad\x00job", "é" * (cron.MAX_CRONTAB_BYTES // 2 + 1)],
                         ids=("macro", "minute", "step", "month", "letter", "nul", "size"))
def test_crontab_rejects_invalid_whole_table(text):
    with pytest.raises(ValueError, match="crontab"):
        cron.parse_crontab("* * * * * first\n" + text)


def test_crontab_editor_refuses_stale_buffer_and_preserves_newer_bytes(tmp_path, monkeypatch):
    monkeypatch.setenv("ROW_HOME", str(tmp_path / "profile"))
    path = cron.default_crontab_path()
    assert cron.read_crontab_text() == ""
    assert not path.parent.exists()
    cron.prepare_crontab(path)
    cron.prepare_crontab(path)
    assert path.is_file() and path.read_bytes() == b""
    cron.save_crontab_text("* * * * * echo one\n", expected="")
    with pytest.raises(ValueError, match="changed while it was open"):
        cron.save_crontab_text("* * * * * echo two\n", expected="")
    assert cron.read_crontab_text() == "* * * * * echo one\n"
    with pytest.raises(ValueError):
        cron.save_crontab_text("broken", expected=cron.read_crontab_text())
    # No setup of an externally supplied schedule's directory.
    missing = tmp_path / "elsewhere" / "table"
    with pytest.raises(FileNotFoundError):
        cron.prepare_crontab(missing)
    assert not missing.parent.exists()


def test_gui_edit_contention_is_bounded_and_leaves_file_unchanged(tmp_path, monkeypatch):
    import threading
    import time

    monkeypatch.setenv("ROW_HOME", str(tmp_path))
    cron.save_crontab_text("# before\n", expected="")
    entered = threading.Event()
    finished = threading.Event()
    def hold():
        with cron.exclusive_file_lock(cron.default_crontab_path()):
            entered.set()
            finished.wait(4)
    worker = threading.Thread(target=hold)
    worker.start()
    try:
        assert entered.wait(2)
        started = time.monotonic()
        with pytest.raises(TimeoutError):
            cron.save_crontab_text("# after\n", expected="# before\n")
        assert time.monotonic() - started < 2
        assert cron.read_crontab_text() == "# before\n"
    finally:
        finished.set()
        worker.join(3)


def test_generation_compare_and_worker_readiness(tmp_path, monkeypatch):
    token = "012345"
    control = tmp_path / "run.control"
    assert cron.cron_phase(control) == ""
    assert not cron._activate_worker(control, token)
    assert cron.change_cron_phase(control, token, (), "pending")
    monkeypatch.setattr(cron.time, "sleep", lambda _delay: cron.change_cron_phase(control, token, ("ready",), "active"))
    assert cron._activate_worker(control, token)
    assert not cron.change_cron_phase(control, "replacement", ("active",), "revoked")
    assert cron.cron_phase(control) == f"active {token}"
    cron.change_cron_phase(control, token, (), "pending")
    monkeypatch.setattr(cron, "CRON_START_TIMEOUT", 0)
    assert not cron._activate_worker(control, token)
    cron.wait_for_cron_ready(control, token, SimpleNamespace(poll=lambda: None))
    cron.change_cron_phase(control, token, (), "revoked")
    with pytest.raises(ValueError, match="confirm startup"):
        cron.wait_for_cron_ready(control, token, SimpleNamespace(poll=lambda: 1))
    with pytest.raises(ValueError, match="confirm startup"):
        cron.wait_for_cron_ready(control, token, SimpleNamespace(poll=lambda: None))
    monkeypatch.setattr(cron, "CRON_START_TIMEOUT", 30)
    monkeypatch.setattr(cron.time, "sleep", lambda _delay: cron.change_cron_phase(control, token, (), "ready"))
    cron.wait_for_cron_ready(control, token, SimpleNamespace(poll=lambda: None))


def test_cron_phase_read_holds_the_transition_lock(tmp_path, monkeypatch):
    from concurrent.futures import ThreadPoolExecutor

    control = tmp_path / "cron.control"
    assert cron.change_cron_phase(control, "generation", (), "active")
    read_text = cron._read_text

    def try_transition_lock():
        with cron.exclusive_file_lock(control, timeout_seconds=0.05):
            pytest.fail("transition lock was available while reading the control file")

    def guarded_read(path):
        with ThreadPoolExecutor(max_workers=1) as executor:
            waiter = executor.submit(try_transition_lock)
            with pytest.raises(cron.FileLockTimeoutError):
                waiter.result(timeout=3)
        return read_text(path)

    monkeypatch.setattr(cron, "_read_text", guarded_read)
    assert cron.cron_phase(control) == "active generation"


def test_worker_activation_survives_same_generation_atomic_replacement(tmp_path, monkeypatch):
    control = tmp_path / "cron.control"
    generation = "test-generation"
    cron.change_cron_phase(control, generation, (), "pending")
    actual_open = cron.os.open
    replaced = False

    def open_after_parent_activates(path, flags, *args, **kwargs):
        nonlocal replaced
        if path == control and not replaced and control.read_text() == f"ready {generation}":
            # The worker already took its pre-read stat. Publish the parent's
            # normal transition before it opens the descriptor for that read.
            replaced = True
            assert cron.change_cron_phase(control, generation, ("ready",), "active")
        return actual_open(path, flags, *args, **kwargs)

    monkeypatch.setattr(cron.os, "open", open_after_parent_activates)
    assert cron._activate_worker(control, generation)
    assert replaced and cron.cron_phase(control) == f"active {generation}"


@pytest.mark.parametrize("phase", ["", "revoked gen", "active different"])
def test_activation_requires_positive_own_generation_before_deadline(tmp_path, monkeypatch, phase):
    monkeypatch.setattr(cron, "change_cron_phase", lambda *_args: True)
    monkeypatch.setattr(cron, "cron_phase", lambda _control: phase)
    monkeypatch.setattr(cron, "CRON_START_TIMEOUT", 0 if not phase else 30)
    monkeypatch.setattr(cron.time, "sleep", lambda _delay: pytest.fail("activation should have ended"))
    assert not cron._activate_worker(tmp_path / "control", "gen")


def test_owned_only_posix_worker_lease_proves_same_generation(tmp_path, monkeypatch):
    import threading
    control = tmp_path / "cron.control"
    path = tmp_path / "crontab"
    path.write_text("")
    token = "test-generation"
    cron.change_cron_phase(control, token, (), "pending")
    acquired = threading.Event()
    release = threading.Event()
    def wait_in_worker(*_args):
        acquired.set()
        assert release.wait(3)
    monkeypatch.setenv("ROW_CRON_CONTROL_FILE", str(control))
    monkeypatch.setenv("ROW_CRON_GENERATION", token)
    monkeypatch.setattr(cron, "uses_cron_worker_lease", lambda: True)
    monkeypatch.setattr(cron, "_run_schedule", wait_in_worker)
    worker = threading.Thread(target=cron.run_cron, args=(path,))
    worker.start()
    try:
        assert acquired.wait(2)
        assert cron.cron_worker_lease_held(control, token)
        assert not cron.cron_worker_lease_held(control, "other")
    finally:
        release.set()
        worker.join(3)
    assert not worker.is_alive()
    assert not cron.cron_worker_lease_held(control, token)


@pytest.mark.parametrize("phases,launched", [
    (["revoked gen"], 0),
    (["active gen", "revoked gen"], 0),
    (["active gen", "active gen", "revoked gen"], 1),
])
def test_worker_checks_own_generation_before_launch(tmp_path, monkeypatch, phases, launched):
    path = tmp_path / "tab"
    path.write_text("* * * * * test\n")
    monkeypatch.setenv("ROW_CRON_CONTROL_FILE", str(tmp_path / "control"))
    monkeypatch.setenv("ROW_CRON_GENERATION", "gen")
    monkeypatch.setattr(cron, "_activate_worker", lambda *_args: True)
    phase_iter = iter(phases)
    monkeypatch.setattr(cron, "cron_phase", lambda _path: next(phase_iter))
    clock = iter([0, 60, 60])
    monkeypatch.setattr(cron.time, "time", lambda: next(clock))
    monkeypatch.setattr(cron.time, "sleep", lambda _delay: None)
    jobs = []
    monkeypatch.setattr(cron, "popen_hidden", lambda *_args, **_kwargs: jobs.append(1))
    cron.run_cron(path)
    assert len(jobs) == launched
    monkeypatch.setenv("ROW_CRON_CONTROL_FILE", str(tmp_path / "control"))
    monkeypatch.setattr(cron, "_activate_worker", lambda *_args: False)
    cron.run_cron(path)


def test_crontab_rejects_nonregular_oversized_and_replaced_schedule(tmp_path, monkeypatch):
    with pytest.raises(ValueError, match="regular file"):
        cron._read_text(tmp_path)
    path = tmp_path / "crontab"
    path.write_bytes(b"x" * (cron.MAX_CRONTAB_BYTES + 2))
    with pytest.raises(ValueError, match="1 MiB"):
        cron._read_text(path)
    path.write_bytes(b"# table\n")
    monkeypatch.setattr(cron.os.path, "samestat", lambda *_args: False)
    with pytest.raises(ValueError, match="changed during read"):
        cron._read_text(path)


def test_default_crontab_refuses_linked_ancestor_without_changing_target(tmp_path, monkeypatch):
    import os
    import subprocess

    workspace = tmp_path / "workspace"
    outside = tmp_path / "other"
    workspace.mkdir()
    outside.mkdir(mode=0o755)
    target = outside / "crontab"
    target.write_text("private target")
    before = outside.stat().st_mode
    monkeypatch.setenv("ROW_HOME", str(workspace))
    link = workspace / "servers"
    if os.name == "nt":
        subprocess.run(["cmd", "/d", "/c", "mklink", "/J", str(link), str(outside)], check=True, capture_output=True)
    else:
        link.symlink_to(outside, target_is_directory=True)
    for action in (cron.read_crontab_text, lambda: cron.prepare_crontab(cron.default_crontab_path()),
                   lambda: cron.save_crontab_text("", expected="private target")):
        with pytest.raises(OSError):
            action()
    assert target.read_text() == "private target" and outside.stat().st_mode == before


def test_shell_uses_posix_sh_or_the_native_windows_raw_command_tail(monkeypatch):
    monkeypatch.setattr(cron, "os", SimpleNamespace(name="posix", environ={}))
    assert cron._job_argv('echo "hello"') == ["/bin/sh", "-c", 'echo "hello"']
    monkeypatch.setattr(cron, "os", SimpleNamespace(name="nt", environ={"SystemRoot": "C:/Windows"}))
    monkeypatch.setattr(cron.shutil, "which", lambda _name: "test-sh.exe")
    assert cron._job_argv("true") == ["test-sh.exe", "-c", "true"]
    monkeypatch.setattr(cron.shutil, "which", lambda _name: None)
    assert '/d /s /c "echo "hello" > out"' in cron._job_argv('echo "hello" > out')


def test_scheduler_waits_for_next_minute_reloads_atomically_and_skips_active_jobs(tmp_path, monkeypatch):
    table = tmp_path / "schedule"
    line = "* * * * * echo tick\n"
    table.write_text(line)
    seconds = [0]
    launches = []

    def launch(argv, **options):
        launches.append((seconds[0], argv))
        assert options["cwd"] == Path.home()
        return SimpleNamespace(poll=lambda: None if seconds[0] < 240 else 0)

    def advance(duration):
        assert duration == 60
        seconds[0] += 60
        if seconds[0] == 180:
            table.write_text(line + "invalid partial line")
        elif seconds[0] == 240:
            table.write_text(line + "0 0 1 jan * echo annual\n")
        elif seconds[0] == 300:
            raise KeyboardInterrupt

    monkeypatch.setattr(cron.time, "time", lambda: seconds[0])
    monkeypatch.setattr(cron.time, "sleep", advance)
    monkeypatch.setattr(cron, "popen_hidden", launch)
    with pytest.raises(KeyboardInterrupt):
        cron.run_cron(table)
    assert [ts for ts, _argv in launches] == [60, 240]

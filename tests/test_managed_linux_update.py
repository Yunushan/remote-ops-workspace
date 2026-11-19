from __future__ import annotations

import hashlib
from contextlib import contextmanager
from pathlib import Path
from types import SimpleNamespace

import pytest

from scripts import managed_linux_update as updater


def state(phase: str) -> dict[str, object]:
    return {
        "schema": updater.SCHEMA, "architecture": "amd64", "phase": phase,
        "previous_version": "1.0.24", "candidate_version": "1.0.28",
        "previous_size": 123, "previous_sha256": "a" * 64, "candidate_sha256": "b" * 64,
        "previous_launcher_sha256": "c" * 64, "candidate_launcher_sha256": "d" * 64,
    }


def test_manager_refuses_non_root_or_other_platform_before_package_commands(monkeypatch):
    monkeypatch.setattr(updater.sys, "platform", "win32")
    monkeypatch.setattr(updater, "native_command", lambda *_a, **_kw: pytest.fail("system tool started"))
    with pytest.raises(updater.UpdateError, match="linux-root-required"):
        updater.run(SimpleNamespace())


@pytest.mark.parametrize("previous_stage_state", ["empty", "prepared", "interrupted"])
def test_update_prepares_the_rollback_installer_before_the_candidate(tmp_path, monkeypatch, previous_stage_state):
    previous, candidate, transaction, workspace = [tmp_path / name for name in ("previous", "candidate", "tx", "home")]
    for directory in (previous, candidate, transaction, workspace):
        directory.mkdir()
    marker = previous / (updater.STAGE_LOCK if previous_stage_state == "empty" else "manifest.json")
    marker.write_bytes(b"staging canary")
    args = SimpleNamespace(stage=candidate, previous_stage=previous, version="1.0.28")
    monkeypatch.setattr(updater, "trusted_path", lambda path, **_kw: path)
    monkeypatch.setattr(updater, "upgrade_preflight", lambda *_args: ("1.0.24", "candidate-policy", "previous-policy"))
    observations = []

    def download(policy, root, *, current_home, expected_version):
        observations.append(("download", policy, root, current_home, expected_version))

    def recover(policy, root, *, current_home, expected_version):
        observations.append(("recover", policy, root, current_home, expected_version))
        if previous_stage_state == "interrupted":
            raise updater.UpdateError("update-stage-refused")

    monkeypatch.setattr(updater, "stage_update", download)
    monkeypatch.setattr(updater, "recover_update", recover)
    if previous_stage_state == "interrupted":
        with pytest.raises(updater.UpdateError, match="update-stage-refused"):
            updater.prepare_upgrade(args, workspace, transaction, "amd64")
        assert observations == [("recover", "previous-policy", previous, workspace, "1.0.24")]
    else:
        assert updater.prepare_upgrade(args, workspace, transaction, "amd64") == "1.0.24"
        assert observations == [
            ("download" if previous_stage_state == "empty" else "recover", "previous-policy", previous, workspace, "1.0.24"),
            ("download", "candidate-policy", candidate, workspace, "1.0.28"),
        ]
    assert marker.read_bytes() == b"staging canary"


@pytest.mark.parametrize("journal_exists", [False, True])
def test_update_downloads_before_the_dpkg_lease_or_recovers_offline(tmp_path, monkeypatch, journal_exists):
    transaction = tmp_path / "tx"
    transaction.mkdir()
    journal = transaction / updater.JOURNAL
    if journal_exists:
        journal.touch()
    args = SimpleNamespace(action="update", transaction=transaction, workspace=tmp_path / "home")
    monkeypatch.setattr(updater.sys, "platform", "linux")
    monkeypatch.setattr(updater.os, "getuid", lambda: 0, raising=False)
    monkeypatch.setattr(updater.os, "geteuid", lambda: 0, raising=False)
    monkeypatch.setattr(updater, "native_command", lambda *_args: SimpleNamespace(stdout="amd64\n"))
    monkeypatch.setattr(updater, "trusted_path", lambda path, **_kw: path)
    global_root = tmp_path / "global"
    monkeypatch.setattr(updater, "SYSTEM_LOCK_ROOT", global_root)
    active = []

    @contextmanager
    def lock(path="dpkg"):
        active.append(path)
        try:
            yield
        finally:
            assert active.pop() == path

    monkeypatch.setattr(updater, "exclusive_file_lock", lock)
    monkeypatch.setattr(updater, "debian_frontend_lock", lock)
    updater_locks = [global_root / updater.JOURNAL, journal]

    def prepare(inputs, workspace, root, architecture):
        assert not journal_exists and active == updater_locks
        assert (inputs, workspace, root, architecture) == (args, args.workspace, transaction, "amd64")
        return "1.0.24"

    def apply(inputs, path, architecture, *, expected_previous):
        assert active == [*updater_locks, "dpkg"]
        assert (inputs, path, architecture) == (args, journal, "amd64")
        assert expected_previous == (None if journal_exists else "1.0.24")
        return state("rolled-back" if journal_exists else "applied")

    monkeypatch.setattr(updater, "prepare_upgrade", prepare)
    monkeypatch.setattr(updater, "apply", apply)
    assert updater.run(args)["phase"] == ("rolled-back" if journal_exists else "applied")
    assert active == []


def test_update_refuses_a_package_replacement_between_staging_and_installing(tmp_path, monkeypatch):
    monkeypatch.setattr(updater, "installed_package", lambda _arch: ("installed", "1.0.26"))
    monkeypatch.setattr(updater, "load_policy", lambda *_args: pytest.fail("policies entered after package changed"))
    args = SimpleNamespace(version="1.0.28", policy=tmp_path / "policy.json")
    journal = tmp_path / updater.JOURNAL
    with pytest.raises(updater.UpdateError, match="installed-package-changed"):
        updater.apply(args, journal, "amd64", expected_previous="1.0.24")
    assert not journal.exists()


def test_interrupted_apply_requires_recovery_instead_of_retrying_install(tmp_path, monkeypatch):
    journal = tmp_path / updater.JOURNAL
    journal.touch()
    interrupted = state("applying")
    monkeypatch.setattr(updater, "read_journal", lambda _p, _a: interrupted)
    monkeypatch.setattr(updater, "load_policy", lambda _path: pytest.fail("unexpected new apply"))
    calls = []

    def rollback(_journal, observed, architecture):
        calls.append((observed["phase"], architecture))
        return state("rolled-back")

    monkeypatch.setattr(updater, "rollback", rollback)
    assert updater.apply(SimpleNamespace(version="1.0.28"), journal, "amd64") == state("rolled-back")
    assert calls == [("applying", "amd64")]
    with pytest.raises(updater.UpdateError, match="existing-update-transaction"):
        updater.apply(SimpleNamespace(version="1.0.29"), journal, "amd64")


@pytest.mark.parametrize("status", [("installed", "1.0.29"), ("half-configured", "1.0.28")])
def test_rollback_will_not_install_after_external_replacement_or_payload_change(tmp_path, monkeypatch, status):
    monkeypatch.setattr(updater, "installed_package", lambda _arch: status)
    monkeypatch.setattr(updater, "trusted_path", lambda path, **_kw: path)
    monkeypatch.setattr(updater, "install_deb", lambda *_a: pytest.fail("installation attempted"))
    retained = tmp_path / updater.PREVIOUS_PACKAGE
    retained.write_bytes(b"unsafe bytes")
    error = "installed-package-changed" if status[1] == "1.0.29" else "installer-size-mismatch"
    with pytest.raises(updater.UpdateError, match=error):
        updater.rollback(tmp_path / updater.JOURNAL, state("applying"), "amd64")


def test_successful_rollback_checks_retained_package_before_install(tmp_path, monkeypatch):
    events = []
    runtime = {updater.LAUNCHER: "c" * 64}
    monkeypatch.setattr(updater, "installed_package", lambda _arch: ("half-configured", "1.0.28"))
    monkeypatch.setattr(updater, "verify_bytes", lambda *args: events.append(("verify", *args)))
    monkeypatch.setattr(updater, "deb_runtime_digests", lambda _path: runtime)
    monkeypatch.setattr(updater, "install_deb", lambda *args: events.append(("install", *args)))

    def write(_journal, document, phase):
        events.append((phase,))
        return {**document, "phase": phase}

    monkeypatch.setattr(updater, "journal_write", write)
    retained = tmp_path / updater.PREVIOUS_PACKAGE
    assert updater.rollback(tmp_path / updater.JOURNAL, state("applying"), "amd64") == state("rolled-back")
    assert events == [
        ("verify", retained, 123, "a" * 64),
        ("rolling-back",),
        ("install", retained, "amd64", "1.0.24", runtime),
        ("rolled-back",),
    ]


@pytest.mark.parametrize(("observed", "launcher_digest", "refusal"), [
    (("installed", "1.0.28"), "f" * 64, "installed-launcher-digest-refused"),
    (("installed", "1.0.24"), "c" * 64, "installed-package-identity-refused"),
])
def test_explicit_rollback_refuses_a_changed_completed_installation(
    tmp_path, monkeypatch, observed, launcher_digest, refusal,
):
    monkeypatch.setattr(updater, "installed_package", lambda _arch: observed)
    monkeypatch.setattr(updater, "installed_launcher_sha256", lambda: launcher_digest)
    monkeypatch.setattr(updater, "retained_runtime", lambda *_args: {updater.LAUNCHER: "d" * 64})
    monkeypatch.setattr(updater, "verify_bytes", lambda *_a: pytest.fail("rollback package accessed"))
    monkeypatch.setattr(updater, "journal_write", lambda *_a: pytest.fail("journal advanced"))
    monkeypatch.setattr(updater, "install_deb", lambda *_a: pytest.fail("installation attempted"))

    with pytest.raises(updater.UpdateError, match=refusal):
        updater.rollback(tmp_path / updater.JOURNAL, state("applied"), "amd64")


@pytest.mark.parametrize("change", [None, "changed", "missing", "untracked"])
def test_installed_servers_must_match_the_signers_runtime_inventory(tmp_path, monkeypatch, change):
    relative = updater.SERVER_ROOT / "linux/ssh/bin/sshd"
    daemon = tmp_path / relative.relative_to(updater.SERVER_ROOT)
    daemon.parent.mkdir(parents=True)
    daemon.write_bytes(b"digest-pinned daemon")
    digests = {updater.LAUNCHER: "d" * 64, relative: hashlib.sha256(daemon.read_bytes()).hexdigest()}
    monkeypatch.setattr(updater, "trusted_path", lambda path, **_kwargs: path)

    if change == "changed":
        daemon.write_bytes(b"same-version replacement")
    elif change == "missing":
        daemon.unlink()
    elif change == "untracked":
        (daemon.parent / "extra").write_bytes(b"untracked")
    if change is None:
        updater.verify_installed_servers(digests, tmp_path)
    else:
        with pytest.raises(updater.UpdateError, match="installed-runtime-payload-refused"):
            updater.verify_installed_servers(digests, tmp_path)


def test_rollback_refuses_changed_candidate_runtime_before_changing_state(tmp_path, monkeypatch):
    runtime = {updater.LAUNCHER: "d" * 64}
    candidate = tmp_path / updater.CANDIDATE_PACKAGE

    def retained(path, digest, launcher):
        assert (path, digest, launcher) == (candidate, "b" * 64, "d" * 64)
        return runtime

    def changed_runtime(digests):
        assert digests == runtime
        raise updater.UpdateError("installed-runtime-payload-refused")

    monkeypatch.setattr(updater, "retained_runtime", retained)
    monkeypatch.setattr(updater, "installed_package", lambda _arch: ("installed", "1.0.28"))
    monkeypatch.setattr(updater, "installed_launcher_sha256", lambda: "d" * 64)
    monkeypatch.setattr(updater, "verify_installed_servers", changed_runtime)
    monkeypatch.setattr(updater, "journal_write", lambda *_a: pytest.fail("journal advanced"))
    monkeypatch.setattr(updater, "install_deb", lambda *_a: pytest.fail("installation attempted"))

    with pytest.raises(updater.UpdateError, match="installed-runtime-payload-refused"):
        updater.rollback(tmp_path / updater.JOURNAL, state("applied"), "amd64")


@pytest.mark.parametrize("name", [updater.PREVIOUS_PACKAGE, "candidate.deb"])
def test_snapshot_refuses_to_replace_an_existing_unrelated_file(tmp_path: Path, monkeypatch, name):
    monkeypatch.setattr(updater, "trusted_path", lambda path, **_kw: path)
    stage = tmp_path / "stage.deb"
    stage.write_bytes(b"approved")
    retained = tmp_path / name
    retained.write_bytes(b"existing")
    artifact = SimpleNamespace(size=8, sha256=hashlib.sha256(b"approved").hexdigest())

    with pytest.raises(updater.UpdateError, match="transaction-snapshot-conflict"):
        updater.snapshot_deb(stage, artifact, retained)

    assert retained.read_bytes() == b"existing"
    assert set(tmp_path.iterdir()) == {stage, retained}


def test_snapshot_reuses_identical_bytes_from_interrupted_preparation(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(updater, "trusted_path", lambda path, **_kw: path)
    retained = tmp_path / updater.PREVIOUS_PACKAGE
    retained.write_bytes(b"approved")
    original_inode = retained.stat().st_ino
    artifact = SimpleNamespace(size=8, sha256=hashlib.sha256(b"approved").hexdigest())

    updater.snapshot_deb(tmp_path / "not-needed.deb", artifact, retained)

    assert retained.stat().st_ino == original_inode
    assert retained.read_bytes() == b"approved"


def test_snapshot_rejects_changed_staged_bytes_before_publication(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(updater, "trusted_path", lambda path, **_kw: path)
    stage = tmp_path / "stage.deb"
    stage.write_bytes(b"changed!")
    retained = tmp_path / updater.PREVIOUS_PACKAGE
    artifact = SimpleNamespace(size=8, sha256=hashlib.sha256(b"approved").hexdigest())

    with pytest.raises(updater.UpdateError, match="installer-digest-mismatch"):
        updater.snapshot_deb(stage, artifact, retained)

    assert set(tmp_path.iterdir()) == {stage}

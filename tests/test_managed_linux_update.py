from __future__ import annotations

import hashlib
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
    monkeypatch.setattr(updater, "installed_package", lambda _arch: ("half-configured", "1.0.28"))
    monkeypatch.setattr(updater, "verify_bytes", lambda *args: events.append(("verify", *args)))
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
        ("install", retained, "amd64", "1.0.24", "c" * 64),
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
    monkeypatch.setattr(updater, "verify_bytes", lambda *_a: pytest.fail("rollback package accessed"))
    monkeypatch.setattr(updater, "journal_write", lambda *_a: pytest.fail("journal advanced"))
    monkeypatch.setattr(updater, "install_deb", lambda *_a: pytest.fail("installation attempted"))

    with pytest.raises(updater.UpdateError, match=refusal):
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

from __future__ import annotations

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


def test_snapshot_rejects_same_size_replacement_without_overwriting_retained_bytes(tmp_path: Path, monkeypatch):
    monkeypatch.setattr(updater, "trusted_path", lambda path, **_kw: path)
    source = tmp_path / "candidate.deb"
    source.write_bytes(b"changed")
    retained = tmp_path / updater.PREVIOUS_PACKAGE
    retained.write_bytes(b"original")
    with pytest.raises(updater.UpdateError, match="installer-digest-mismatch"):
        updater.snapshot_deb(source, SimpleNamespace(size=7, sha256="0" * 64), retained)
    assert retained.read_bytes() == b"original"
    assert set(tmp_path.iterdir()) == {source, retained}

from __future__ import annotations

import copy
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

ROOT = Path(__file__).resolve().parents[1]


def _load_smoke():
    spec = importlib.util.spec_from_file_location("workspace_recovery_smoke", ROOT / "scripts/smoke_workspace_recovery.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def released_wheel_report():
    smoke = _load_smoke()
    wheel = ROOT / ".tmp" / smoke.EXPECTED_WHEEL_NAME
    if not wheel.exists():
        pytest.skip("released-wheel integration runs in the blocking Linux/Windows recovery CI smoke")
    return smoke, smoke.run_drill(wheel)


@pytest.fixture
def contract_input():
    """Synthetic validator input is never written as production evidence."""
    smoke = _load_smoke()
    stage = {"counts": {name: 1 for name in ("profiles", "group_defaults", "layouts", "snippets", "macros", "vault_items")},
             "tree": {"sha256": "a" * 64, "file_count": 8, "directory_count": 3, "total_bytes": 3000},
             "semantic_sha256": "b" * 64}
    return smoke, {
        "schema": smoke.REPORT_SCHEMA, "status": "passed", "scope": "source-and-released-wheel-state-compatibility",
        "previous_version": "1.0.24", "current_version": "1.0.27", "previous_wheel_sha256": smoke.EXPECTED_WHEEL_SHA256,
        "previous_vault_version": 2, "upgraded_vault_version": 3,
        "previous": copy.deepcopy(stage), "current": copy.deepcopy(stage), "checks": dict.fromkeys(smoke.CHECK_NAMES, True),
    }


def test_full_state_recovery_uses_actual_released_wheel_and_loaders(released_wheel_report):
    smoke, report = released_wheel_report
    smoke.validate_report(report)
    assert report["previous_version"] == "1.0.24"
    assert report["previous_wheel_sha256"] == smoke.EXPECTED_WHEEL_SHA256
    assert report["previous_vault_version"] == 2
    assert report["upgraded_vault_version"] == 3
    assert report["previous"]["counts"] == {
        "profiles": 2, "group_defaults": 1, "layouts": 1, "snippets": 1, "macros": 1, "vault_items": 1,
    }
    assert report["current"]["counts"]["profiles"] == 3
    assert report["current"]["counts"]["vault_items"] == 2
    assert all(report["checks"].values())
    assert report["previous"]["tree"]["sha256"] != report["current"]["tree"]["sha256"]
    rendered = json.dumps(report)
    for value in ("inherited.invalid", "recovery-secret", "opaque-plugin-state", '"passphrase":', '"token":', "ROW_HOME"):
        assert value not in rendered


@pytest.mark.parametrize("mutate", [
    lambda report: report.update(passphrase="must-never-upload"),
    lambda report: report["previous"].update(payload="must-never-upload"),
    lambda report: report["previous"]["tree"].update(path="home/payload.json"),
    lambda report: report["previous"]["counts"].update(secret="must-never-upload"),
    lambda report: report["checks"].update(released_previous_loaders_decrypted_rollback=False),
    lambda report: report.update(previous_wheel_sha256="0" * 64),
    lambda report: report["previous"]["counts"].update(profiles=True),
    lambda report: report["checks"].pop("post_snapshot_state_absent"),
])
def test_evidence_contract_rejects_payloads_fabricated_hash_and_missing_proofs(contract_input, mutate):
    smoke, report = contract_input
    changed = copy.deepcopy(report)
    mutate(changed)
    with pytest.raises(ValueError):
        smoke.validate_report(changed)


def test_release_fixture_pins_the_public_wheel_identity(tmp_path):
    smoke = _load_smoke()
    fixture = smoke.load_fixture()
    assert fixture["previous_release"]["sha256"] == smoke.EXPECTED_WHEEL_SHA256
    fixture["previous_release"]["url"] = "https://untrusted.invalid/payload.whl"
    changed = tmp_path / "fixture.json"
    changed.write_text(json.dumps(fixture), encoding="utf-8")
    with pytest.raises(ValueError, match="identity"):
        smoke.load_fixture(changed)


def test_previous_wheel_hash_is_checked_before_any_code_execution(tmp_path, monkeypatch):
    smoke = _load_smoke()
    wheel = tmp_path / smoke.EXPECTED_WHEEL_NAME
    wheel.write_bytes(b"x" * smoke.EXPECTED_WHEEL_SIZE)
    monkeypatch.setattr(smoke, "_worker", lambda *_args: pytest.fail("unverified wheel executed"))
    with pytest.raises(ValueError, match="SHA256"):
        smoke.run_drill(wheel)
    wheel.write_bytes(b"small")
    with pytest.raises(ValueError, match="size"):
        smoke.run_drill(wheel)


def test_download_is_bounded_and_hash_checked_before_save(tmp_path, monkeypatch):
    smoke = _load_smoke()
    reads = []

    class Download:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def read(self, bound):
            reads.append(bound)
            return b"x" * smoke.EXPECTED_WHEEL_SIZE

    monkeypatch.setattr(smoke.urllib.request, "urlopen", lambda url, timeout: Download())
    wheel = tmp_path / smoke.EXPECTED_WHEEL_NAME
    with pytest.raises(ValueError, match="pinned release digest"):
        smoke.download_previous_wheel(wheel)
    assert reads == [smoke.EXPECTED_WHEEL_SIZE + 1]
    assert not wheel.exists()


@pytest.mark.parametrize("status, attempts", [(503, 3), (404, 1)])
def test_download_retries_only_bounded_transient_http_failures(tmp_path, monkeypatch, status, attempts):
    smoke = _load_smoke()
    calls, waits = [], []

    def unavailable(url, timeout):
        calls.append((url, timeout))
        raise smoke.urllib.error.HTTPError(url, status, "unavailable", {}, None)

    monkeypatch.setattr(smoke.urllib.request, "urlopen", unavailable)
    monkeypatch.setattr(smoke.time, "sleep", waits.append)
    wheel = tmp_path / smoke.EXPECTED_WHEEL_NAME
    with pytest.raises(smoke.urllib.error.HTTPError):
        smoke.download_previous_wheel(wheel)
    assert len(calls) == attempts
    assert calls[0] == (smoke.EXPECTED_WHEEL_URL, 30)
    assert waits == ([1, 2] if attempts == 3 else [])
    assert not wheel.exists()


def test_worker_uses_isolated_runtime_and_stdin_without_disclosing_failures(tmp_path, monkeypatch):
    smoke = _load_smoke()
    calls = []

    def run(argv, **kwargs):
        calls.append((argv, kwargs))
        return SimpleNamespace(returncode=1, stdout="sensitive-store-content", stderr="sensitive-passphrase")

    monkeypatch.setattr(smoke.subprocess, "run", run)
    payload = {"vault_passphrase": "stdin-only-passphrase"}
    with pytest.raises(RuntimeError, match="isolated state worker failed") as raised:
        smoke._worker(tmp_path / "wheel.whl", tmp_path / "home", payload)
    argv, kwargs = calls[0]
    assert "-I" in argv
    assert "stdin-only-passphrase" not in " ".join(argv)
    assert json.loads(kwargs["input"]) == payload
    assert "sensitive" not in str(raised.value)


def test_main_failure_report_contains_only_sanitized_failure_type(tmp_path, monkeypatch):
    smoke = _load_smoke()
    output = tmp_path / "report.json"

    def fail(_wheel):
        raise RuntimeError("secret-passphrase and decrypted-payload")

    monkeypatch.setattr(smoke, "run_drill", fail)
    assert smoke.main(["--out", str(output)]) == 1
    assert json.loads(output.read_text(encoding="utf-8")) == {
        "schema": smoke.REPORT_SCHEMA, "status": "failed", "failure_type": "RuntimeError",
    }


@pytest.mark.parametrize("relative", [
    ".profiles.json.lock", ".vault.json.lock", ".layouts.json.lock",
    ".snippets.json.lock", ".moba-macros.json.lock", ".xserver-state.json.lock",
    "servers/.http-server-state.json.lock", "servers/.ftp-server-state.json.lock",
    "servers/.tftp-server-state.json.lock", "servers/.ssh-server-state.json.lock",
    "servers/.sftp-server-state.json.lock", "servers/.telnet-server-state.json.lock",
    "servers/.vnc-server-state.json.lock", "servers/.nfs-server-state.json.lock",
    ".PROFILES.JSON.LOCK",
])
def test_tree_oracle_ignores_only_known_advisory_relative_lock_files(tmp_path, relative):
    smoke = _load_smoke()
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    before = smoke._tree_summary(tmp_path)
    target.write_bytes(b"advisory lock")
    assert smoke._tree_summary(tmp_path) == before
    target.write_bytes(b"changed advisory lock")
    assert smoke._tree_summary(tmp_path) == before
    target.unlink()
    assert smoke._tree_summary(tmp_path) == before


@pytest.mark.parametrize("relative", [
    ".plugin.lock", "plugins/unrecognized/.plugin.lock",
    "plugins/unrecognized/.profiles.json.lock",
    "plugins/servers/.http-server-state.json.lock",
])
@pytest.mark.parametrize("change", ["same-size-mutation", "loss"])
def test_tree_oracle_detects_unknown_and_nested_known_basename_lock_changes(tmp_path, relative, change):
    smoke = _load_smoke()
    target = tmp_path / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(b"original")
    before = smoke._tree_summary(tmp_path)
    assert before["file_count"] == 1
    if change == "same-size-mutation":
        target.write_bytes(b"modified")
    else:
        target.unlink()
    changed = smoke._tree_summary(tmp_path)
    assert changed["sha256"] != before["sha256"]
    with pytest.raises(AssertionError, match="full-state evidence differs"):
        smoke._assert_same(before, changed)
    target.write_bytes(b"original")
    smoke._assert_same(before, smoke._tree_summary(tmp_path))


def test_tree_oracle_keeps_empty_directories_even_with_advisory_lock_basename(tmp_path):
    smoke = _load_smoke()
    target = tmp_path / ".profiles.json.lock"
    target.mkdir()
    before = smoke._tree_summary(tmp_path)
    assert before["directory_count"] == 1
    target.rmdir()
    assert smoke._tree_summary(tmp_path)["sha256"] != before["sha256"]


def test_recovery_fixture_seeds_both_opaque_locks_without_changing_known_store_counts():
    fixture = _load_smoke().load_fixture()
    assert set(fixture["opaque_files"]) == {
        "plugins/unrecognized/state.json", "plugins/unrecognized/cache.dat",
        "plugins/unrecognized/.plugin.lock", "plugins/unrecognized/.profiles.json.lock",
    }
    assert fixture["empty_directories"] == ["plugins/unrecognized/empty"]
    assert len(fixture["profiles"]) == 2 and len(fixture["group_defaults"]) == 1
    assert len(fixture["layouts"]) == len(fixture["snippets"]) == len(fixture["macros"]) == 1


def test_encrypted_recovery_and_oracle_preserve_opaque_locks_bytes_and_empty_directories(tmp_path):
    import secrets

    from remote_ops_workspace.workspace_backup import (
        create_workspace_backup,
        restore_workspace_backup,
    )

    smoke = _load_smoke()
    fixture = smoke.load_fixture()
    source = tmp_path / "original"
    source.mkdir()
    expected_bytes = {name: content.encode("utf-8") for name, content in fixture["opaque_files"].items()}
    for name, content in expected_bytes.items():
        target = source / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(content)
    for name in fixture["empty_directories"]:
        (source / name).mkdir(parents=True)
    (source / ".profiles.json.lock").write_bytes(b"advisory state")
    expected = smoke._tree_summary(source)
    passphrase = secrets.token_urlsafe(32)
    archive = tmp_path / "encrypted.rowbackup"
    created = create_workspace_backup(source, archive, passphrase, offline_confirmed=True)
    assert created["file_count"] == len(expected_bytes)
    assert created["directory_count"] == expected["directory_count"]
    ciphertext = archive.read_bytes()
    assert passphrase.encode() not in ciphertext
    assert all(name.encode() not in ciphertext and content not in ciphertext for name, content in expected_bytes.items())
    restored = tmp_path / "restored"
    restore_workspace_backup(archive, restored, passphrase, current_home=source, offline_confirmed=True)
    smoke._assert_same(expected, smoke._tree_summary(restored))
    assert not (restored / ".profiles.json.lock").exists()
    assert all((restored / name).read_bytes() == content for name, content in expected_bytes.items())
    assert all((restored / name).is_dir() for name in fixture["empty_directories"])
    for index, name in enumerate((
        "plugins/unrecognized/.plugin.lock", "plugins/unrecognized/.profiles.json.lock",
        "plugins/unrecognized/cache.dat", "plugins/unrecognized/empty",
    )):
        target = restored / name
        if target.is_dir():
            target.rmdir()
        else:
            target.unlink()
        with pytest.raises(AssertionError, match="full-state evidence differs"):
            smoke._assert_same(expected, smoke._tree_summary(restored))
        fresh = tmp_path / f"recovered-{index}"
        restore_workspace_backup(archive, fresh, passphrase, current_home=source, offline_confirmed=True)
        smoke._assert_same(expected, smoke._tree_summary(fresh))
        restored = fresh
    smoke._assert_same(expected, smoke._tree_summary(source))

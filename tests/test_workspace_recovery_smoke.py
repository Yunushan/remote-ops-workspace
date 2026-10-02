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

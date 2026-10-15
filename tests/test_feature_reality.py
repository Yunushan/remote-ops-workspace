from __future__ import annotations

import importlib.util
from pathlib import Path
from types import SimpleNamespace

from remote_ops_workspace.features import load_feature_manifest


def test_feature_reality_checker_passes_current_tree() -> None:
    checker = _load_checker()

    assert checker.main() == 0


def test_feature_reality_rules_cover_implemented_manifest_features() -> None:
    checker = _load_checker()
    manifest = load_feature_manifest()
    implemented_ids = {
        item["id"]
        for item in manifest["features"]
        if item["status"].startswith(checker.IMPLEMENTED_STATUS_PREFIX)
    }

    assert implemented_ids.issubset(checker.FEATURE_REALITY_RULES)


def test_xserver_lifecycle_reality_requires_verified_identity_and_exit_evidence(tmp_path, monkeypatch) -> None:
    checker = _load_checker()
    feature = "moba.xserver-lifecycle-supervision"
    rule = checker.FEATURE_REALITY_RULES[feature]
    assert checker.check_module_attrs(feature, rule["module_attrs"]) == []
    assert checker.check_source_tokens(feature, rule["source_tokens"]) == []
    for relative, tokens in rule["source_tokens"].items():
        path = tmp_path / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("\n".join(tokens), encoding="utf-8")
    monkeypatch.setattr(checker, "ROOT", tmp_path)
    assert checker.check_source_tokens(feature, rule["source_tokens"]) == []
    lifecycle = tmp_path / "src/remote_ops_workspace/x11.py"
    lifecycle.write_text("XServerLifecycleRecord xserver-state.json pid_probe taskkill SIGTERM", encoding="utf-8")
    failures = checker.check_source_tokens(feature, rule["source_tokens"])
    assert any("terminate_recorded_process(record.pid, record.process_identity)" in failure for failure in failures)
    assert any("pid=None" in failure for failure in failures)
    lifecycle.write_text("\n".join(rule["source_tokens"]["src/remote_ops_workspace/x11.py"]), encoding="utf-8")
    helper = tmp_path / "src/remote_ops_workspace/process_status.py"
    helper.write_text(helper.read_text().replace("pidfd_send_signal", "unsafe_numeric_pid_signal"), encoding="utf-8")
    assert any("pidfd_send_signal" in failure for failure in checker.check_source_tokens(feature, rule["source_tokens"]))


def test_feature_reality_collects_nested_cli_command_paths() -> None:
    checker = _load_checker()

    command_paths = checker.collect_cli_command_paths(checker.build_parser())

    assert ("connect",) in command_paths
    assert ("files", "queue") in command_paths
    assert ("vault", "status") in command_paths
    assert ("sync", "push") in command_paths


def test_feature_reality_protocol_samples_are_non_executing_plans() -> None:
    checker = _load_checker()

    errors = checker.check_protocol_plans("protocol.ssh", ["ssh", "rdp", "serial", "local-shell"])

    assert errors == []


def test_feature_reality_verifies_cleartext_default_and_opted_in_plan() -> None:
    checker = _load_checker()

    protocols = ["ftp", "rlogin", "rsh", "telnet"]
    errors = checker.check_protocol_plans("protocol.cleartext", protocols)

    assert errors == []
    for protocol in protocols:
        assert checker.sample_profile(protocol).options["allow_insecure_cleartext"] == "true"


def test_feature_reality_rejects_permissive_cleartext_launcher(monkeypatch) -> None:
    checker = _load_checker()
    monkeypatch.setattr(
        checker,
        "build_launch_plan",
        lambda profile: SimpleNamespace(protocol=profile.protocol, command=[profile.protocol]),
    )

    errors = checker.check_protocol_plans("protocol.telnet", ["telnet"])

    assert "protocol.telnet telnet must be rejected without explicit per-profile cleartext opt-in" in errors


def _load_checker():
    path = Path("scripts/check_feature_reality.py")
    spec = importlib.util.spec_from_file_location("check_feature_reality_script", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module

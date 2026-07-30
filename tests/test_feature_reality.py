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

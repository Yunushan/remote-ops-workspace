from __future__ import annotations

import argparse
import json
import runpy
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from remote_ops_workspace import cli
from remote_ops_workspace.models import Profile


class _Record(SimpleNamespace):
    def to_dict(self) -> dict[str, Any]:
        return {key: _json_value(value) for key, value in vars(self).items()}

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), sort_keys=True)

    def printable(self) -> str:
        return "tool --flag"


def _json_value(value: Any) -> Any:
    if isinstance(value, _Record):
        return value.to_dict()
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, list):
        return [_json_value(item) for item in value]
    if isinstance(value, tuple):
        return [_json_value(item) for item in value]
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    return value


def _validation(*, passed: bool = True, summary: bool = True) -> _Record:
    return _Record(
        passed=passed,
        ok=passed,
        evidence_path=Path("evidence.json"),
        manifest_path=Path("manifest.json"),
        assets_dir=Path("assets"),
        summary=(
            {
                "schema": "row.test.v1",
                "release_target": "windows-x64",
                "brand_name": "Corp Ops",
                "surface_count": 2,
                "channel": "stable",
                "organization": "Example Corp",
                "version": "1.0.0",
                "artifact_count": 2,
                "signature_algorithm": "ed25519",
                "macro": "triage",
                "replay_sessions": 1,
            }
            if summary
            else {}
        ),
        warnings=["review warning"],
        errors=["review error"],
    )


class _Store:
    def __init__(self, records: list[Any] | None = None, item: Any | None = None) -> None:
        self.records = list(records or [])
        self.item = item if item is not None else (self.records[0] if self.records else None)
        self.path = Path("profiles.json")
        self.calls: list[tuple[Any, ...]] = []

    def init(self, *, with_examples: bool) -> None:
        self.calls.append(("init", with_examples))

    def load(self, *, resolve: bool = True) -> list[Any]:
        self.calls.append(("load", resolve))
        return list(self.records)

    def get(self, name: str) -> Any:
        self.calls.append(("get", name))
        if self.item is None:
            raise KeyError(name)
        return self.item

    def add(self, item: Any, *, replace: bool = False) -> None:
        self.calls.append(("add", item, replace))
        self.item = item
        self.records.append(item)

    def remove(self, name: str) -> None:
        self.calls.append(("remove", name))

    def set_group_defaults(
        self, group: str, defaults: dict[str, object], *, replace: bool = False
    ) -> None:
        self.calls.append(("defaults", group, defaults, replace))


def _ns(**values: Any) -> argparse.Namespace:
    return argparse.Namespace(**values)


def test_setup_profile_connect_and_doctor_handlers(monkeypatch, capsys, tmp_path: Path) -> None:
    profile = Profile(name="edge", protocol="ssh", host="192.0.2.10", tags=["prod"])
    store = _Store([profile], profile)
    monkeypatch.setattr(cli, "ensure_data_dir", lambda: tmp_path)
    monkeypatch.setattr(cli, "ProfileStore", lambda: store)
    monkeypatch.setattr(
        cli,
        "first_run_payload",
        lambda **kwargs: {"data_dir": str(kwargs["data_dir"]), "profiles": kwargs["profile_names"]},
    )
    monkeypatch.setattr(cli, "first_run_json", lambda payload: json.dumps(payload))
    monkeypatch.setattr(cli, "format_first_run", lambda payload: f"welcome {payload['profiles']}")

    assert cli.cmd_init(_ns(no_examples=True, json=True, quiet=False)) == 0
    assert cli.cmd_init(_ns(no_examples=False, json=False, quiet=True)) == 0
    assert cli.cmd_init(_ns(no_examples=True, json=False, quiet=False)) == 0
    assert cli.cmd_welcome(_ns(json=True)) == 0
    assert cli.cmd_welcome(_ns(json=False)) == 0

    add_args = _ns(
        option=["compression=yes"],
        name="new-edge",
        protocol="ssh",
        host="192.0.2.11",
        port=22,
        username="operator",
        group="prod",
        tag=["prod"],
        description="Edge host",
        path=None,
        url=None,
        command=None,
        identity_file=None,
        credential_ref=None,
        tunnel=["dynamic:1080"],
        replace=True,
    )
    assert cli.cmd_profile_add(add_args) == 0
    assert cli.cmd_profile_list(_ns(json=True)) == 0
    assert cli.cmd_profile_list(_ns(json=False)) == 0
    store.records = []
    assert cli.cmd_profile_list(_ns(json=False)) == 0
    store.records = [profile]
    store.item = profile
    assert cli.cmd_profile_show(_ns(name="edge")) == 0
    assert cli.cmd_profile_remove(_ns(name="edge")) == 0
    assert (
        cli.cmd_profile_defaults(
            _ns(
                username="operator",
                identity_file="id_ed25519",
                credential_ref="vault/key",
                option=["compression=yes"],
                group="prod",
                replace=True,
            )
        )
        == 0
    )

    plan = _Record(command=["ssh", "edge"], notes=["safe launch"])
    monkeypatch.setattr(cli, "assert_profile_launch_allowed", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(cli, "launch", lambda *_args, **_kwargs: plan)
    events: list[tuple[str, dict[str, Any]]] = []
    monkeypatch.setattr(cli, "append_event", lambda event, payload: events.append((event, payload)))
    assert cli.cmd_connect(_ns(name="edge", dry_run=True)) == 0
    assert cli.cmd_connect(_ns(name="edge", dry_run=False)) == 0
    assert [event for event, _payload in events] == ["connect.dry_run", "connect.launch"]

    doctor = _Record(
        platform="windows",
        python="3.12",
        data_dir=tmp_path,
        executables={"ssh": {"ssh": True}, "rdp": {"mstsc": False}},
        protocol_status={"ssh": {"summary": "ready"}},
    )
    monkeypatch.setattr(cli, "run_doctor", lambda: doctor)
    assert cli.cmd_doctor(_ns(json=True)) == 0
    assert cli.cmd_doctor(_ns(json=False)) == 0
    assert cli._doctor_executable_summary({"ssh": True, "plink": False}) == "ssh"
    assert cli._doctor_executable_summary({"ssh": False}) == "missing"
    assert "no profiles" in capsys.readouterr().out


def test_feature_and_plugin_handler_output_branches(monkeypatch, capsys) -> None:
    manifest = {"features": ["ssh"]}
    monkeypatch.setattr(cli, "load_feature_manifest", lambda: manifest)
    monkeypatch.setattr(
        cli,
        "feature_summary",
        lambda: [{"id": "ssh", "status": "ready", "coverage": "complete"}],
    )
    assert cli.cmd_features(_ns(json=True, coverage=False)) == 0
    assert cli.cmd_features(_ns(json=False, coverage=False)) == 0

    assert cli._protected_platform_row_provenance_note({}) == ""
    assert (
        cli._protected_platform_row_provenance_note(
            {"accepted_evidence_required_targets": ["linux"], "release_backed_readiness_complete": True}
        )
        == "; release-backed proof complete"
    )
    assert (
        cli._protected_platform_row_provenance_note(
            {"accepted_evidence_required_targets": ["linux"], "accepted_evidence_record_complete": True}
        )
        == "; accepted records complete, release assets pending"
    )
    assert (
        cli._protected_platform_row_provenance_note({"accepted_evidence_required_targets": ["linux"]})
        == "; accepted records/release assets pending"
    )

    empty_registry = _Record(loaded=[], failures=[])
    monkeypatch.setattr(cli, "load_plugin_registry", lambda: empty_registry)
    assert cli.cmd_plugins_list(_ns(json=False)) == 0
    assert cli.cmd_plugins_list(_ns(json=True)) == 0

    registry = _Record(
        loaded=[_Record(name="demo", protocols=["ssh"], executables=[]), _Record(name="tools", protocols=[], executables=["tool"])],
        failures=[_Record(name="broken", error="bad metadata")],
    )
    monkeypatch.setattr(cli, "load_plugin_registry", lambda: registry)
    assert cli.cmd_plugins_list(_ns(json=False)) == 0

    report = _Record(ok=True)
    monkeypatch.setattr(cli, "validate_installed_plugins", lambda **_kwargs: report)
    monkeypatch.setattr(cli, "result_to_json", lambda result: result.to_json())
    monkeypatch.setattr(cli, "report_to_text", lambda _result: "plugin report")
    validate_args = _ns(host="host", username="user", port=22, option=["key=value"], json=True)
    assert cli.cmd_plugins_validate(validate_args) == 0
    validate_args.json = False
    report.ok = False
    assert cli.cmd_plugins_validate(validate_args) == 1

    scaffold = _Record(root=Path("plugin"), files=[Path("plugin/pyproject.toml")])
    monkeypatch.setattr(cli, "scaffold_plugin", lambda **_kwargs: scaffold)
    scaffold_args = _ns(
        out=Path("plugin"),
        name="demo",
        module="demo_plugin",
        protocol="demo",
        client="demo-client",
        force=False,
        json=True,
    )
    assert cli.cmd_plugins_scaffold(scaffold_args) == 0
    scaffold_args.json = False
    assert cli.cmd_plugins_scaffold(scaffold_args) == 0
    captured = capsys.readouterr()
    assert "no plugins installed" in captured.out
    assert "failed: broken" in captured.err


def test_platform_and_coverage_reports_cover_optional_sections(monkeypatch) -> None:
    targets = {
        "release_architectures": [
            {
                "platform": "windows",
                "cpu_arch": "x86_64",
                "bits": 64,
                "release_tier": "native",
                "github_release_channel": "stable-release",
            }
        ],
        "windows_legacy_targets": [
            {
                "version": "Windows XP",
                "host_tier": "extended",
                "remote_target_tier": "verified",
                "remote_target_coverage_percent": 100.0,
                "architectures": ["x86", "x64"],
                "security_profile": "restricted",
            },
            {
                "version": "Windows 7",
                "host_tier": "extended",
                "remote_target_tier": "catalog",
                "remote_target_coverage_percent": None,
            },
        ],
    }
    protected_goal = {
        "current_percent": 50.0,
        "gap_percent": 50.0,
        "accepted_target_count": 1,
        "target_count": 2,
        "status": "partial",
        "release_asset_provenance_complete": False,
        "release_asset_provenance_command": "verify-assets",
        "remote_release_evidence_audit_command": "audit-release",
        "missing_targets": ["linux-armhf"],
    }
    platform = {
        "overall": {
            "current_percent": 100.0,
            "gap_percent": 0.0,
            "target_count": 2,
            "extended_target_count": 1,
        },
        "denominator": {
            "included_target_count": 2,
            "excluded_target_count": 1,
            "protected_goal_score_source": "protected_goal_parity",
        },
        "protected_goal_parity": protected_goal,
        "targets": [
            {
                "target": "windows-x64",
                "current_percent": 100.0,
                "status": "ready",
                "channel": "stable",
                "remote_target_coverage_percent": 100.0,
                "legacy_architectures": ["x64"],
                "security_profile": "restricted",
                "accepted_evidence_missing_targets": ["linux-armhf"],
                "accepted_evidence_required_targets": ["windows-x64"],
                "release_backed_readiness_complete": True,
            },
            {
                "target": "linux-x64",
                "current_percent": 100.0,
                "status": "ready",
                "channel": "stable",
                "remote_target_coverage_percent": None,
                "accepted_evidence_missing_targets": [],
            },
        ],
    }
    product = {"product": "workspace", "current_percent": 100.0, "feature_count": 1}
    report = {
        "feature_family_mapping": {
            "target_percent": 100.0,
            "overall": {"current_percent": 100.0, "feature_count": 1},
            "products": [product],
        },
        "adapter_ready_coverage": {
            "target_percent": 100.0,
            "overall": {"current_percent": 100.0, "gap_percent": 0.0},
            "products": [{"product": "workspace", "current_percent": 100.0}],
        },
        "production_parity_coverage": {
            "target_percent": 100.0,
            "overall": {"current_percent": 100.0, "gap_percent": 0.0},
            "products": [{"product": "workspace", "current_percent": 100.0}],
        },
        "platform_verified_readiness": platform,
        "evidence_summary": {"features_with_evidence": 1, "total_features": 1},
        "workflow_parity_contract": {"label": "strict"},
    }
    monkeypatch.setattr(cli, "load_platform_targets", lambda: targets)
    monkeypatch.setattr(cli, "coverage_report", lambda: report)

    assert cli.cmd_platforms(_ns(json=True)) == 0
    assert cli.cmd_platforms(_ns(json=False)) == 0
    protected_goal["release_asset_provenance_complete"] = True
    protected_goal["remote_release_evidence_audit_command"] = ""
    protected_goal["missing_targets"] = []
    assert cli.cmd_platforms(_ns(json=False)) == 0
    platform["protected_goal_parity"] = {}
    assert cli.cmd_platforms(_ns(json=False)) == 0

    platform["protected_goal_parity"] = protected_goal
    protected_goal["release_asset_provenance_complete"] = False
    protected_goal["release_asset_provenance_command"] = "verify-assets"
    protected_goal["remote_release_evidence_audit_command"] = "audit-release"
    protected_goal["missing_targets"] = ["linux-armhf"]
    assert cli.cmd_features(_ns(json=False, coverage=True)) == 0
    protected_goal["release_asset_provenance_complete"] = True
    protected_goal["remote_release_evidence_audit_command"] = ""
    protected_goal["missing_targets"] = []
    assert cli.cmd_features(_ns(json=False, coverage=True)) == 0
    protected_goal["release_asset_provenance_complete"] = False
    protected_goal["release_asset_provenance_command"] = ""
    platform["denominator"] = {}
    platform["targets"] = []
    assert cli.cmd_features(_ns(json=False, coverage=True)) == 0
    platform["protected_goal_parity"] = {}
    assert cli.cmd_features(_ns(json=False, coverage=True)) == 0


def test_customizer_handlers_cover_json_text_and_failure(monkeypatch, tmp_path: Path) -> None:
    files = [Path("bundle/manifest.json"), Path("bundle/logo.png")]
    bundle = _Record(
        root=Path("bundle"),
        manifest={"brand_name": "Corp Ops", "profile_count": 2},
        files=files,
    )
    monkeypatch.setattr(cli, "build_moba_professional_customizer_plan", lambda *_args, **_kwargs: _Record())
    monkeypatch.setattr(cli, "write_moba_professional_customizer_bundle", lambda _plan: bundle)
    common_build = dict(
        out=Path("bundle"),
        brand_name="Corp Ops",
        organization="Example Corp",
        welcome_file=None,
        welcome_message=None,
        logo=None,
        settings=None,
        profiles=None,
        policy=None,
        lock_setting=[],
        force=False,
        json=False,
    )
    welcome = tmp_path / "welcome.txt"
    welcome.write_text("hello", encoding="utf-8")
    assert cli.cmd_customizer_build(_ns(**(common_build | {"welcome_file": welcome}))) == 0
    assert cli.cmd_customizer_build(_ns(**(common_build | {"welcome_message": "hello", "json": True}))) == 0
    assert cli.cmd_customizer_build(_ns(**common_build)) == 0

    installer = _Record(
        brand_name="Corp Ops",
        publisher="Example Corp",
        artifact_names={"windows": "row.exe"},
    )
    policy = _Record(
        locked_settings=[{"key": "theme", "value": "dark"}],
        enforcement_surfaces=["gui", "cli"],
    )
    channel = _Record(channel="stable", update_url="https://updates.example.test", require_signature=True)
    deployment = _Record(
        schema="row.professional.v1",
        installer_branding=installer,
        policy_locks=policy,
        update_channel=channel,
        evidence_requirements=["signed installer"],
    )
    monkeypatch.setattr(cli, "build_professional_deployment_plan", lambda **_kwargs: deployment)
    deployment_args = _ns(
        brand_name="Corp Ops",
        organization="Example Corp",
        version="1.0.0",
        logo=None,
        policy=None,
        lock_setting=[],
        update_url="https://updates.example.test",
        update_public_key="key",
        update_channel="stable",
        update_interval_hours=24,
        rollout_ring="stable",
        surface=[],
        json=True,
    )
    assert cli.cmd_customizer_deployment_plan(deployment_args) == 0
    deployment_args.json = False
    assert cli.cmd_customizer_deployment_plan(deployment_args) == 0
    channel.require_signature = False
    assert cli.cmd_customizer_deployment_plan(deployment_args) == 0

    validation = _validation(passed=True)
    evidence_result = _Record(
        validation=validation,
        evidence_path=Path("deployment.json"),
        files=[Path("deployment.json")],
    )
    monkeypatch.setattr(
        cli, "build_professional_deployment_evidence_bundle_plan", lambda *_args, **_kwargs: _Record()
    )
    monkeypatch.setattr(cli, "write_professional_deployment_evidence_bundle", lambda _plan: evidence_result)
    evidence_args = _ns(
        **vars(deployment_args),
        out_dir=Path("artifacts"),
        surface_passed=["gui"],
        all_policy_surfaces_passed=False,
        bundle_manifest_evidence=Path("bundle.txt"),
        installer_evidence=Path("installer.txt"),
        policy_evidence=Path("policy.txt"),
        update_evidence=Path("update.txt"),
        update_manifest=Path("update.json"),
        bundle_manifest_sha256="a" * 64,
        update_assets_dir=Path("assets"),
        release_target="windows-x64",
        bundle_command="bundle",
        installer_command="install",
        policy_command="policy",
        update_command="update",
        sha256s_present=True,
        windows_exe_rebranded=True,
        windows_msi_rebranded=True,
        product_name_matches_brand=True,
        logo_applied=True,
        https_update_url=True,
        signature_verified=True,
        organization_channel=True,
    )
    evidence_args.json = True
    assert cli.cmd_customizer_evidence_bundle(evidence_args) == 0
    evidence_args.json = False
    evidence_args.all_policy_surfaces_passed = True
    validation.passed = False
    assert cli.cmd_customizer_evidence_bundle(evidence_args) == 1


@pytest.mark.parametrize(
    ("handler_name", "dependency_name", "args"),
    [
        (
            "cmd_customizer_evidence_verify",
            "validate_professional_deployment_evidence",
            _ns(evidence=Path("deployment.json"), assets_dir=Path("assets"), json=False),
        ),
        (
            "cmd_customizer_update_verify",
            "validate_professional_update_manifest",
            _ns(
                manifest=Path("update.json"),
                public_key="key",
                channel="stable",
                organization="Example Corp",
                assets_dir=Path("assets"),
                json=False,
            ),
        ),
        (
            "cmd_macro_evidence_verify",
            "validate_macro_live_replay_evidence",
            _ns(evidence=Path("macro.json"), assets_dir=Path("assets"), json=False),
        ),
    ],
)
def test_validation_handlers_cover_all_output_states(
    monkeypatch,
    handler_name: str,
    dependency_name: str,
    args: argparse.Namespace,
) -> None:
    result = _validation(passed=True, summary=True)
    monkeypatch.setattr(cli, dependency_name, lambda *_args, **_kwargs: result)
    handler = getattr(cli, handler_name)
    assert handler(args) == 0
    args.json = True
    assert handler(args) == 0
    args.json = False
    result.passed = False
    result.ok = False
    result.summary = {}
    assert handler(args) == 1


def test_snippet_macro_layout_and_broadcast_handlers(monkeypatch, tmp_path: Path) -> None:
    snippet = _Record(name="triage", command="hostname", description="check", tags=["ops"])
    snippet_store = _Store([snippet], snippet)
    monkeypatch.setattr(cli, "SnippetStore", lambda: snippet_store)
    monkeypatch.setattr(cli, "run_snippet", lambda *_args, **_kwargs: ["ssh", "host"])
    assert (
        cli.cmd_snippet_add(
            _ns(name="triage", command="hostname", description="check", tag=["ops"], replace=True)
        )
        == 0
    )
    assert cli.cmd_snippet_list(_ns(json=True)) == 0
    assert cli.cmd_snippet_list(_ns(json=False)) == 0
    assert cli.cmd_snippet_show(_ns(name="triage")) == 0
    assert cli.cmd_snippet_remove(_ns(name="triage")) == 0
    assert cli.cmd_snippet_run(_ns(name="triage", dry_run=True)) == 0

    recording = _Record(
        name="triage",
        description="check",
        tags=["ops"],
        events=[_Record(text="hostname")],
    )
    macro_store = _Store([recording], recording)
    monkeypatch.setattr(cli, "MobaMacroStore", lambda: macro_store)
    monkeypatch.setattr(cli, "record_typed_macro", lambda *_args, **_kwargs: recording)
    record_base = dict(
        name="triage",
        description="check",
        tag=["ops"],
        delay_ms=10,
        replace=True,
        json=False,
        text=None,
        text_file=None,
    )
    assert cli.cmd_macro_record(_ns(**(record_base | {"text": "hostname"}))) == 0
    source = tmp_path / "macro.txt"
    source.write_text("uptime", encoding="utf-8")
    assert cli.cmd_macro_record(_ns(**(record_base | {"text_file": source, "json": True}))) == 0
    monkeypatch.setattr(cli.sys, "stdin", SimpleNamespace(read=lambda: "whoami"))
    assert cli.cmd_macro_record(_ns(**record_base)) == 0
    assert cli.cmd_macro_list(_ns(json=True)) == 0
    assert cli.cmd_macro_list(_ns(json=False)) == 0
    assert cli.cmd_macro_show(_ns(name="triage")) == 0
    assert cli.cmd_macro_remove(_ns(name="triage")) == 0

    profile = Profile(name="edge", protocol="ssh", host="192.0.2.10", tags=["ops"])
    profile_store = _Store([profile], profile)
    monkeypatch.setattr(cli, "ProfileStore", lambda: profile_store)
    plan = _Record(
        profile_name="edge",
        pane_id="pane-1",
        event_count=1,
        command=["ssh", "edge"],
        notes=["reviewed"],
        steps=[_Record(index=1, delay_ms=10, scheduled_after_ms=10, enter=True)],
    )
    replay_result = _Record(ok=True, dry_run=True)
    monkeypatch.setattr(cli, "build_macro_replay_plans", lambda *_args: [plan])
    monkeypatch.setattr(cli, "run_macro_replay", lambda *_args, **_kwargs: [replay_result])
    replay_args = _ns(
        name="triage",
        profile=["edge"],
        group=None,
        tag=[],
        dry_run=True,
        timeout=10,
        json=True,
    )
    assert cli.cmd_macro_replay(replay_args) == 0
    replay_args.json = False
    assert cli.cmd_macro_replay(replay_args) == 0
    replay_result.ok = False
    assert cli.cmd_macro_replay(replay_args) == 1

    capture = _Record(
        macro_name="triage",
        event_count=1,
        input_sha256="a" * 64,
        total_delay_ms=10,
        capture_controls=["record", "stop"],
        cancel_supported=True,
        notes=["capture note"],
    )
    monkeypatch.setattr(cli, "build_macro_gui_capture_plan", lambda _recording: capture)
    assert cli.cmd_macro_capture_plan(_ns(name="triage", json=True)) == 0
    assert cli.cmd_macro_capture_plan(_ns(name="triage", json=False)) == 0
    capture.cancel_supported = False
    assert cli.cmd_macro_capture_plan(_ns(name="triage", json=False)) == 0

    review = _Record(
        allowed=True,
        confirmation_required=True,
        cancel_supported=True,
        prompt="Continue?",
        disconnected_profiles=["offline"],
    )
    monkeypatch.setattr(cli, "review_macro_live_replay", lambda *_args, **_kwargs: review)
    monkeypatch.setattr(cli, "build_macro_live_replay_plans", lambda *_args, **_kwargs: [plan])
    live_args = _ns(
        name="triage",
        profile=["edge"],
        group=None,
        tag=[],
        connected_profile=["edge"],
        force=False,
        pane_id=["edge=pane-1"],
        json=True,
    )
    assert cli.cmd_macro_live_plan(live_args) == 0
    live_args.json = False
    assert cli.cmd_macro_live_plan(live_args) == 0
    review.allowed = False
    review.confirmation_required = False
    review.cancel_supported = False
    review.prompt = ""
    review.disconnected_profiles = []
    plan.steps[0].enter = False
    assert cli.cmd_macro_live_plan(live_args) == 1

    validation = _validation(passed=True)
    evidence = _Record(
        validation=validation,
        evidence_path=Path("macro.json"),
        notes=["bundle note"],
    )
    monkeypatch.setattr(cli, "build_macro_live_evidence_bundle_plan", lambda *_args, **_kwargs: _Record())
    monkeypatch.setattr(cli, "write_macro_live_evidence_bundle", lambda _plan: evidence)
    evidence_args = _ns(
        name="triage",
        profile=["edge"],
        group=None,
        tag=[],
        out_dir=Path("artifact"),
        capture_evidence=Path("capture.txt"),
        review_evidence=Path("review.txt"),
        replay_evidence=["edge=replay.txt"],
        release_target="windows-x64",
        connected_profile=["edge"],
        pane_id=["edge=pane-1"],
        capture_command="capture",
        review_command="review",
        replay_command=["edge=replay"],
        gui_record_button=True,
        gui_stop_button=True,
        gui_cancel_button=True,
        per_event_timing_captured=True,
        confirmation_prompt=True,
        cancel_prompt_verified=True,
        conflict_checked=True,
        real_connected_session=True,
        live_terminal_pane=True,
        per_keystroke_timing_replay=True,
        json=True,
    )
    assert cli.cmd_macro_evidence_bundle(evidence_args) == 0
    evidence_args.json = False
    validation.passed = False
    assert cli.cmd_macro_evidence_bundle(evidence_args) == 1

    layout = _Record(name="ops", orientation="vertical", panes=["edge"], description="Ops")
    layout_store = _Store([layout], layout)
    monkeypatch.setattr(cli, "LayoutStore", lambda: layout_store)
    monkeypatch.setattr(cli, "Layout", lambda **kwargs: _Record(**kwargs))
    monkeypatch.setattr(cli, "parse_layout_pane", lambda value: value)
    monkeypatch.setattr(cli, "build_layout_terminal_plans", lambda *_args: [plan])
    layout_result = _Record(title="edge", dry_run=True, pid=None, command=["ssh", "edge"])
    monkeypatch.setattr(cli, "run_layout_terminal_plans", lambda *_args, **_kwargs: [layout_result])
    assert (
        cli.cmd_layout_save(
            _ns(name="ops", orientation="vertical", pane=["edge"], description="Ops", replace=True)
        )
        == 0
    )
    assert cli.cmd_layout_list(_ns(json=True)) == 0
    assert cli.cmd_layout_list(_ns(json=False)) == 0
    assert cli.cmd_layout_show(_ns(name="ops")) == 0
    assert cli.cmd_layout_remove(_ns(name="ops")) == 0
    assert cli.cmd_layout_run(_ns(name="ops", dry_run=True, json=True)) == 0
    assert cli.cmd_layout_run(_ns(name="ops", dry_run=True, json=False)) == 0

    broadcast_result = _Record(
        profile_name="edge",
        dry_run=True,
        ok=True,
        returncode=0,
        command=["ssh", "edge"],
        stdout="done\n",
        stderr="warning\n",
    )
    monkeypatch.setattr(cli, "build_broadcast_plans", lambda *_args: [plan])
    monkeypatch.setattr(cli, "run_broadcast", lambda *_args, **_kwargs: [broadcast_result])
    broadcast_args = _ns(
        profile=["edge"], group=None, tag=[], command="hostname", dry_run=True, timeout=10, json=True
    )
    assert cli.cmd_broadcast(broadcast_args) == 0
    broadcast_args.json = False
    assert cli.cmd_broadcast(broadcast_args) == 0
    broadcast_result.dry_run = False
    broadcast_result.ok = False
    broadcast_result.returncode = 2
    broadcast_result.stdout = ""
    broadcast_result.stderr = ""
    assert cli.cmd_broadcast(broadcast_args) == 1


def test_cli_helpers_cover_validation_and_formatting(monkeypatch, capsys) -> None:
    assert cli._parse_options(["a=1", "b=two=parts"]) == {"a": "1", "b": "two=parts"}
    with pytest.raises(ValueError, match="key=value"):
        cli._parse_options(["broken"])

    assert cli._parse_key_path_options(["edge=proof.txt"], "proof") == {"edge": Path("proof.txt")}
    with pytest.raises(ValueError, match="key=path"):
        cli._parse_key_path_options(["broken"], "proof")
    with pytest.raises(ValueError, match="both key and path"):
        cli._parse_key_path_options(["=proof.txt"], "proof")
    with pytest.raises(ValueError, match="both key and path"):
        cli._parse_key_path_options(["edge="], "proof")

    assert cli._parse_package_source_options(["htop=htop.zip", "curl=8.0=curl.zip"]) == {
        "htop": Path("htop.zip"),
        "curl=8.0": Path("curl.zip"),
    }
    with pytest.raises(ValueError, match="name=path"):
        cli._parse_package_source_options(["broken"])
    with pytest.raises(ValueError, match="both package key and path"):
        cli._parse_package_source_options(["=file.zip"])
    with pytest.raises(ValueError, match="both package key and path"):
        cli._parse_package_source_options(["name="])

    defaults = cli._parse_smartcard_certificates(
        [], provider="microsoft-capi", default_certificate_id="cert-1"
    )
    assert defaults[0].source == "cli-default"
    parsed = cli._parse_smartcard_certificates(
        ["cert-1", "cert-2||pkcs11|fingerprint|ssh-rsa AAAA"],
        provider="microsoft-capi",
        default_certificate_id="fallback",
    )
    assert [certificate.certificate_id for certificate in parsed] == ["cert-1", "cert-2"]
    assert parsed[0].label == "cert-1"
    assert parsed[1].provider == "pkcs11"
    assert cli._select_smartcard_certificate(parsed, "cert-2") is parsed[1]
    with pytest.raises(ValueError, match="not found"):
        cli._select_smartcard_certificate(parsed, "missing")

    monkeypatch.delenv("ROW_TEST_SECRET", raising=False)
    with pytest.raises(ValueError, match="not set"):
        cli._secret_from_env("ROW_TEST_SECRET", "secret")
    monkeypatch.setenv("ROW_TEST_SECRET", "")
    with pytest.raises(ValueError, match="empty"):
        cli._secret_from_env("ROW_TEST_SECRET", "secret")
    monkeypatch.setenv("ROW_TEST_SECRET", "value")
    assert cli._secret_from_env("ROW_TEST_SECRET", "secret") == "value"
    monkeypatch.setenv("ROW_VAULT_PASSWORD", "vault-pass")
    assert cli._vault_passphrase(confirm=True) == "vault-pass"
    monkeypatch.delenv("ROW_VAULT_PASSWORD")
    monkeypatch.setattr(cli, "prompt_passphrase", lambda *, confirm: f"prompt-{confirm}")
    assert cli._vault_passphrase(confirm=False) == "prompt-False"
    monkeypatch.setattr(cli, "getpass", lambda _prompt: "typed-secret")
    assert cli._vault_secret_value(_ns(secret_env=None, stdin=False)) == "typed-secret"

    cli._print_local_preview({"path": "missing", "kind": "missing", "exists": False})
    cli._print_local_preview(
        {
            "path": "file.txt",
            "kind": "file",
            "exists": True,
            "size": 5,
            "children": ["a", "b"],
            "binary": True,
            "truncated": True,
            "text": "hello",
            "error": "preview error",
        }
    )
    cli._print_local_preview(
        {
            "path": "empty",
            "kind": "directory",
            "exists": True,
            "size": None,
            "children": [],
            "binary": False,
            "truncated": False,
            "text": "",
            "error": "",
        }
    )

    progress = _Record(
        index=1,
        total=1,
        item=_Record(action="get"),
        state="done",
        returncode=0,
    )
    queue_plan = _Record(
        profile_name="edge",
        batch_commands=["get /a /b"],
        notes=["queue note"],
    )
    queue_result = _Record(
        dry_run=True,
        ok=True,
        returncode=0,
        progress=[progress],
        stdout="stdout\n",
        stderr="stderr\n",
    )
    cli._print_sftp_queue_result(queue_plan, queue_result)
    queue_result.dry_run = False
    queue_result.ok = False
    queue_result.returncode = 3
    queue_result.progress = []
    queue_result.stdout = ""
    queue_result.stderr = ""
    cli._print_sftp_queue_result(queue_plan, queue_result)
    queue_result.ok = True
    cli._print_sftp_queue_result(queue_plan, queue_result)

    plan = _Record(batch_commands=["ls"], notes=["note"])
    cli._print_sftp_plan(plan, show_batch=True)
    cli._print_sftp_plan(plan, show_batch=False)

    broadcast = _Record(
        profile_name="edge",
        dry_run=False,
        ok=True,
        returncode=0,
        command=["ssh", "edge"],
        stdout="out",
        stderr="err",
    )
    cli._print_broadcast_result(broadcast)
    broadcast.ok = False
    broadcast.returncode = 2
    broadcast.stdout = ""
    broadcast.stderr = ""
    cli._print_broadcast_result(broadcast)
    broadcast.dry_run = True
    cli._print_broadcast_result(broadcast)

    cli._print_layout_result(_Record(title="edge", dry_run=True, pid=None, command=["ssh", "edge"]))
    cli._print_layout_result(_Record(title="edge", dry_run=False, pid=42, command=["ssh", "edge"]))

    tunnels = cli._parse_tunnels(
        [
            "dynamic:1080",
            "local:15432:127.0.0.1:5432",
            "remote:9000:127.0.0.1:9000:0.0.0.0",
        ]
    )
    assert len(tunnels) == 3
    with pytest.raises(ValueError, match="invalid tunnel"):
        cli._parse_tunnels(["invalid:1"])

    profiles = [
        Profile(name="edge", protocol="ssh", host="edge", group="prod", tags=["blue"]),
        Profile(name="lab", protocol="ssh", host="lab", group="lab", tags=["green"]),
    ]
    store = _Store(profiles, profiles[0])
    assert cli._select_profiles(store, ["edge"], None, []) == [profiles[0]]
    assert cli._select_profiles(store, [], "prod", []) == [profiles[0]]
    assert cli._select_profiles(store, [], None, ["green"]) == [profiles[1]]
    with pytest.raises(ValueError, match="no profiles matched"):
        cli._select_profiles(store, [], "missing", [])
    assert "preview error" in capsys.readouterr().err


def test_vault_sync_gui_and_module_guard_handlers(monkeypatch, capsys, tmp_path: Path) -> None:
    vault_status = _Record(
        path=Path("vault.json"),
        initialized=True,
        backend_available=True,
        item_count=2,
        version=1,
        kdf="scrypt",
    )

    class Vault:
        def init(self, passphrase: str) -> None:
            assert passphrase

        def set(self, name: str, secret: str, passphrase: str) -> None:
            assert name and secret and passphrase

        def get(self, name: str, passphrase: str) -> str:
            assert name and passphrase
            return "secret"

        def list(self) -> list[str]:
            return ["one", "two"]

        def delete(self, name: str) -> None:
            assert name

        def status(self) -> _Record:
            return vault_status

    monkeypatch.setattr(cli, "LocalVault", Vault)
    monkeypatch.setattr(cli, "_vault_passphrase", lambda *, confirm: "passphrase")
    monkeypatch.setattr(cli, "_vault_secret_value", lambda _args: "secret")
    assert cli.cmd_vault_init(_ns()) == 0
    assert cli.cmd_vault_set(_ns(name="one")) == 0
    secret_writes: list[tuple[Path, str]] = []
    monkeypatch.setattr(cli, "_write_secret_file", lambda path, secret: secret_writes.append((path, secret)))
    secret_path = tmp_path / "retrieved-secret"
    assert cli.cmd_vault_get(_ns(name="one", out=secret_path)) == 0
    assert secret_writes == [(secret_path, "secret")]
    assert cli.cmd_vault_list(_ns()) == 0
    with pytest.raises(ValueError, match="--force"):
        cli.cmd_vault_delete(_ns(name="one", force=False))
    assert cli.cmd_vault_delete(_ns(name="one", force=True)) == 0
    assert cli.cmd_vault_status(_ns(json=True)) == 0
    assert cli.cmd_vault_status(_ns(json=False)) == 0
    vault_status.initialized = False
    vault_status.backend_available = False
    vault_status.item_count = None
    vault_status.version = None
    vault_status.kdf = ""
    assert cli.cmd_vault_status(_ns(json=False)) == 0

    class Backup:
        def export_bundle(self, out: Path) -> None:
            assert out == tmp_path / "backup.zip"

    class Sync:
        def push(self, target: Path) -> Path:
            return target

        def pull(self, source: Path, *, replace: bool) -> int:
            assert source and replace
            return 2

    monkeypatch.setattr(cli, "BackupService", Backup)
    monkeypatch.setattr(cli, "DirectorySyncProvider", Sync)
    assert cli.cmd_export(_ns(out=tmp_path / "backup.zip")) == 0
    assert cli.cmd_sync_push(_ns(to=tmp_path / "remote")) == 0
    assert cli.cmd_sync_pull(_ns(source=tmp_path / "remote", replace=True)) == 0

    snapshot = _Record(team="ops", version=3, profiles=[1, 2], updated_at="now")
    cli._print_team_sync_snapshot(snapshot, as_json=True)
    cli._print_team_sync_snapshot(snapshot, as_json=False)
    snapshot.updated_at = ""
    cli._print_team_sync_snapshot(snapshot, as_json=False)

    class Backend:
        def __init__(self, root: Path) -> None:
            self.root = root

        def read(self, team: str) -> _Record:
            return snapshot

    client = _Record()
    client.push = lambda team, expected_version: snapshot
    client.pull = lambda team, replace: snapshot
    monkeypatch.setattr(cli, "TeamSyncBackend", Backend)
    monkeypatch.setattr(cli, "_team_sync_client", lambda _root: client)
    team_args = _ns(root=tmp_path, team="ops", json=False, expected_version=2, replace=True)
    assert cli.cmd_team_sync_status(team_args) == 0
    assert cli.cmd_team_sync_push(team_args) == 0
    assert cli.cmd_team_sync_pull(team_args) == 0

    monkeypatch.setattr(cli, "_run_frozen_windows_gui_launcher", lambda: 7)
    assert cli.cmd_gui(_ns()) == 7
    monkeypatch.setattr(cli, "_run_frozen_windows_gui_launcher", lambda: None)
    import remote_ops_workspace.gui as gui_module

    monkeypatch.setattr(gui_module, "main", lambda: 3)
    assert cli.cmd_gui(_ns()) == 3
    assert "vault initialized" in capsys.readouterr().out


def test_frozen_windows_launcher_paths(monkeypatch) -> None:
    monkeypatch.setattr(cli.sys, "frozen", False, raising=False)
    assert cli._run_frozen_windows_gui_launcher() is None
    monkeypatch.setattr(cli.sys, "frozen", True, raising=False)

    class MissingLauncher:
        def with_name(self, _name: str) -> MissingLauncher:
            return self

        def exists(self) -> bool:
            return False

    monkeypatch.setattr(cli, "Path", lambda _value: MissingLauncher())
    assert cli._run_frozen_windows_gui_launcher() is None

    class Launcher(MissingLauncher):
        def exists(self) -> bool:
            return True

        def __str__(self) -> str:
            return "row-gui.exe"

    monkeypatch.setattr(cli, "Path", lambda _value: Launcher())
    monkeypatch.setattr(cli.subprocess, "run", lambda *_args, **_kwargs: _Record(returncode=9))
    assert cli._run_frozen_windows_gui_launcher() == 9


def test_cli_module_main_guard_is_executable(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("ROW_HOME", str(tmp_path))
    monkeypatch.setattr(sys, "argv", ["row", "welcome", "--json"])
    with pytest.warns(RuntimeWarning, match="found in sys.modules"):
        with pytest.raises(SystemExit) as exc:
            runpy.run_module("remote_ops_workspace.cli", run_name="__main__")
    assert exc.value.code == 0


def test_main_error_and_remaining_secret_input_paths(monkeypatch) -> None:
    class Parser:
        def parse_args(self, _argv):
            def fail(_args):
                raise KeyError("missing")

            return _ns(func=fail)

    monkeypatch.setattr(cli, "build_parser", Parser)
    assert cli.main([]) == 1

    monkeypatch.setenv("CLI_SECRET", "from-env")
    assert cli._vault_secret_value(_ns(secret_env="CLI_SECRET", stdin=False)) == "from-env"
    stream = SimpleNamespace(read=lambda: "from-stdin\n")
    assert cli._vault_secret_value(_ns(secret_env=None, stdin=True), stream) == "from-stdin"

from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path

import remote_ops_workspace.plugins as plugins_module
from remote_ops_workspace.cli import main
from remote_ops_workspace.launcher import LaunchPlan, build_launch_plan
from remote_ops_workspace.models import Profile
from remote_ops_workspace.plugin_dev import scaffold_plugin, validate_installed_plugins
from remote_ops_workspace.plugins import load_plugin_registry
from remote_ops_workspace.profile_validation import prepare_profile
from remote_ops_workspace.storage import ProfileStore


class DemoPlugin:
    name = "demo plugin"
    protocols = ("demo", "demo-alt")
    executables = ("demo-client",)

    def build(self, profile: Profile) -> LaunchPlan:
        return LaunchPlan(profile.protocol, ["demo-client", profile.name], ["demo plugin plan"])


class BadPlugin:
    name = "bad plugin"
    protocols = ()


class NoBuildPlugin:
    name = "no build plugin"
    protocols = ("nobuild",)


class ShadowPlugin:
    name = "shadow plugin"
    protocols = ("ssh",)

    def build(self, profile: Profile) -> LaunchPlan:
        return LaunchPlan(profile.protocol, ["ssh", profile.name], [])


class InvalidPlanPlugin:
    name = "invalid plan plugin"
    protocols = ("invalid",)
    executables = ("invalid-client",)

    def build(self, profile: Profile) -> object:
        return ["invalid-client", profile.name]


class FakeEntryPoint:
    def __init__(self, name: str, plugin: object, *, fail: bool = False) -> None:
        self.name = name
        self.module = "tests.fake_plugin"
        self.attr = name
        self._plugin = plugin
        self._fail = fail

    def load(self) -> object:
        if self._fail:
            raise RuntimeError("boom")
        return self._plugin

    def __str__(self) -> str:
        return f"{self.module}:{self.attr}"


class FakeEntryPoints:
    def __init__(self, *items: FakeEntryPoint) -> None:
        self.items = list(items)

    def select(self, *, group: str):
        return self.items if group == "remote_ops_workspace.plugins" else []


def fake_entry_points() -> FakeEntryPoints:
    return FakeEntryPoints(FakeEntryPoint("DemoPlugin", DemoPlugin))


def with_fake_entry_points(provider):
    class _Patch:
        def __enter__(self):
            self.old = plugins_module.entry_points
            plugins_module.entry_points = provider
            return self

        def __exit__(self, exc_type, exc, tb):
            plugins_module.entry_points = self.old
            return False

    return _Patch()


def test_plugin_registry_loads_protocol_plugins_and_failures() -> None:
    registry = load_plugin_registry(
        entry_points_provider=lambda: FakeEntryPoints(
            FakeEntryPoint("DemoPlugin", DemoPlugin),
            FakeEntryPoint("BrokenPlugin", DemoPlugin, fail=True),
            FakeEntryPoint("BadPlugin", BadPlugin),
            FakeEntryPoint("NoBuildPlugin", NoBuildPlugin),
        )
    )

    assert registry.protocols == {"demo", "demo-alt"}
    assert registry.protocol_clients() == {"demo": ["demo-client"], "demo-alt": ["demo-client"]}
    assert registry.plugin_for_protocol("demo").name == "demo plugin"
    assert len(registry.failures) == 3
    assert registry.to_dict()["loaded"][0]["protocols"] == ["demo", "demo-alt"]
    assert any("build(profile)" in failure.error for failure in registry.failures)


def test_plugin_registry_rejects_builtin_protocol_collisions() -> None:
    registry = load_plugin_registry(
        entry_points_provider=lambda: FakeEntryPoints(FakeEntryPoint("ShadowPlugin", ShadowPlugin))
    )

    assert registry.loaded == []
    assert len(registry.failures) == 1
    assert "built-in protocol" in registry.failures[0].error


def test_prepare_profile_accepts_explicit_plugin_protocols() -> None:
    profile = prepare_profile(Profile(name="plug", protocol="DEMO"), extra_protocols={"demo"})
    assert profile.protocol == "demo"
    assert profile.host is None


def test_launcher_dispatches_plugin_launch_plan() -> None:
    with with_fake_entry_points(fake_entry_points):
        plan = build_launch_plan(Profile(name="plug", protocol="demo"))

    assert plan.command == ["demo-client", "plug"]
    assert "Built by plugin: demo plugin" in plan.notes
    assert "demo plugin plan" in plan.notes


def test_profile_store_accepts_plugin_protocol_when_installed(tmp_path: Path) -> None:
    with with_fake_entry_points(fake_entry_points):
        store = ProfileStore(tmp_path / "profiles.json")
        store.add(Profile(name="plug", protocol="demo"))
        loaded = store.get("plug")

    assert loaded.protocol == "demo"


def test_cli_plugins_list_json_reports_loaded_plugins() -> None:
    with with_fake_entry_points(fake_entry_points):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rc = main(["plugins", "list", "--json"])

    payload = json.loads(stdout.getvalue())
    assert rc == 0
    assert payload["loaded"][0]["name"] == "demo plugin"
    assert payload["loaded"][0]["protocols"] == ["demo", "demo-alt"]


def test_plugin_validation_report_checks_launch_plan_shape() -> None:
    report = validate_installed_plugins(entry_points_provider=fake_entry_points)

    assert report.ok
    assert [check.protocol for check in report.plan_checks] == ["demo", "demo-alt"]
    assert report.plan_checks[0].command == ["demo-client", "plugin-check-demo"]


def test_plugin_validation_report_rejects_invalid_plan_shape() -> None:
    report = validate_installed_plugins(
        entry_points_provider=lambda: FakeEntryPoints(FakeEntryPoint("InvalidPlanPlugin", InvalidPlanPlugin))
    )

    assert not report.ok
    assert "LaunchPlan" in report.plan_checks[0].error


def test_cli_plugins_validate_json_reports_plan_checks() -> None:
    with with_fake_entry_points(fake_entry_points):
        stdout = io.StringIO()
        with contextlib.redirect_stdout(stdout):
            rc = main(["plugins", "validate", "--json"])

    payload = json.loads(stdout.getvalue())
    assert rc == 0
    assert payload["ok"] is True
    assert payload["plan_checks"][0]["command"] == ["demo-client", "plugin-check-demo"]


def test_plugin_scaffold_writes_minimal_project(tmp_path: Path) -> None:
    result = scaffold_plugin(
        out_dir=tmp_path / "row-demo-plugin",
        project_name="row-demo-plugin",
        module_name="row_demo_plugin",
        protocol="demo",
        client="demo-client",
    )

    assert (result.root / "pyproject.toml").exists()
    assert (result.root / "src" / "row_demo_plugin" / "plugin.py").exists()
    pyproject = (result.root / "pyproject.toml").read_text(encoding="utf-8")
    plugin = (result.root / "src" / "row_demo_plugin" / "plugin.py").read_text(encoding="utf-8")
    assert '[project.entry-points."remote_ops_workspace.plugins"]' in pyproject
    assert 'demo = "row_demo_plugin.plugin:Plugin"' in pyproject
    assert 'protocols = ("demo",)' in plugin


def test_plugin_scaffold_rejects_builtin_protocol(tmp_path: Path) -> None:
    try:
        scaffold_plugin(
            out_dir=tmp_path / "bad-plugin",
            project_name="bad-plugin",
            module_name="bad_plugin",
            protocol="ssh",
            client="ssh",
        )
    except ValueError as exc:
        assert "built-in protocol" in str(exc)
    else:
        raise AssertionError("plugin scaffold should reject built-in protocol collisions")

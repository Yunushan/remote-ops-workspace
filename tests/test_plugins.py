from __future__ import annotations

import contextlib
import io
import json
from pathlib import Path
from typing import Any, cast

import pytest

import remote_ops_workspace.plugin_dev as plugin_dev_module
import remote_ops_workspace.plugins as plugins_module
from remote_ops_workspace.cli import main
from remote_ops_workspace.launcher import LaunchPlan, build_launch_plan
from remote_ops_workspace.models import Profile
from remote_ops_workspace.plugin_dev import (
    PluginPlanCheck,
    PluginValidationReport,
    report_to_text,
    scaffold_plugin,
    validate_installed_plugins,
    validate_launch_plan_shape,
)
from remote_ops_workspace.plugins import (
    LoadedPlugin,
    load_plugin_registry,
    normalize_plugin_executables,
    normalize_plugin_protocols,
)
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


class ExplodingPlanPlugin:
    name = "exploding plan plugin"
    protocols = ("explode",)
    executables = ("explode-client",)

    def build(self, profile: Profile) -> LaunchPlan:
        raise RuntimeError(f"cannot build {profile.name}")


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


def test_plugin_registry_survives_broken_environment_metadata() -> None:
    def broken_discovery() -> FakeEntryPoints:
        raise OSError("unreadable third-party entry_points.txt")

    registry = load_plugin_registry(entry_points_provider=broken_discovery)

    assert registry.loaded == []
    assert len(registry.failures) == 1
    assert registry.failures[0].name == "entry-point-discovery"
    assert registry.failures[0].entry_point == "remote_ops_workspace.plugins"
    assert "unreadable third-party" in registry.failures[0].error


def test_plugin_protocol_metadata_must_be_string_or_iterable() -> None:
    try:
        normalize_plugin_protocols(7)
    except TypeError as exc:
        assert str(exc) == "plugin protocols must be a string or iterable"
    else:
        raise AssertionError("non-iterable plugin protocol metadata should be rejected")


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


def test_plugin_validation_report_captures_plugin_build_errors() -> None:
    report = validate_installed_plugins(
        entry_points_provider=lambda: FakeEntryPoints(
            FakeEntryPoint("ExplodingPlanPlugin", ExplodingPlanPlugin)
        )
    )

    assert not report.ok
    assert report.plan_checks[0].error == "cannot build plugin-check-explode"


def test_plugin_launch_plan_validation_reports_protocol_command_and_note_errors() -> None:
    plugin = LoadedPlugin(
        name="demo plugin",
        protocols=("demo",),
        executables=("demo-client",),
        object=DemoPlugin(),
        entry_point="tests.fake_plugin:DemoPlugin",
    )
    malformed = LaunchPlan("other", ["demo-client", "bad\nargument"], [])
    malformed.notes = cast(Any, "not-a-list")

    errors = validate_launch_plan_shape(plugin, "demo", malformed)

    assert any("not declared by plugin" in error for error in errors)
    assert any("control characters" in error for error in errors)
    assert "launch plan notes must be a list" in errors

    invalid_note = LaunchPlan("demo", ["demo-client"], ["bad\nnote"])
    note_errors = validate_launch_plan_shape(plugin, "demo", invalid_note)
    assert any("control characters" in error for error in note_errors)


def test_plugin_validation_report_text_covers_loaded_failures_and_plan_details() -> None:
    assert report_to_text(PluginValidationReport([], [], [])) == "no plugins installed"
    report = PluginValidationReport(
        loaded=[
            {"name": "demo", "protocols": ["demo", "demo-alt"]},
            {"name": "empty", "protocols": []},
            {"name": "legacy", "protocols": "not-a-list"},
        ],
        failures=[{"name": "broken", "error": "boom"}],
        plan_checks=[
            PluginPlanCheck(
                plugin="demo",
                protocol="demo",
                ok=True,
                command=["demo-client", "plugin.example"],
            ),
            PluginPlanCheck(plugin="broken", protocol="broken", ok=False, error="no plan"),
        ],
    )

    text = report_to_text(report)

    assert "loaded: demo protocols demo, demo-alt" in text
    assert "loaded: empty protocols -" in text
    assert "loaded: legacy protocols -" in text
    assert "failed: broken: boom" in text
    assert "plan ok: demo / demo" in text
    assert "  command: demo-client plugin.example" in text
    assert "plan failed: broken / broken" in text
    assert "  error: no plan" in text


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
    assert result.to_dict()["protocol"] == "demo"


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


def test_plugin_scaffold_rejects_invalid_names_protocol_and_nonempty_output(
    tmp_path: Path,
) -> None:
    with pytest.raises(ValueError, match="project name"):
        scaffold_plugin(
            out_dir=tmp_path / "bad-project",
            project_name="Bad Project!",
            module_name="valid_module",
            protocol="demo",
            client="demo-client",
        )
    with pytest.raises(ValueError, match="module name"):
        scaffold_plugin(
            out_dir=tmp_path / "bad-module",
            project_name="valid-project",
            module_name="bad-module",
            protocol="demo",
            client="demo-client",
        )
    with pytest.raises(ValueError, match="exactly one protocol"):
        scaffold_plugin(
            out_dir=tmp_path / "bad-protocol",
            project_name="valid-project",
            module_name="valid_module",
            protocol="",
            client="demo-client",
        )

    nonempty = tmp_path / "nonempty"
    nonempty.mkdir()
    (nonempty / "keep.txt").write_text("keep", encoding="utf-8")
    with pytest.raises(ValueError, match="output directory is not empty"):
        scaffold_plugin(
            out_dir=nonempty,
            project_name="valid-project",
            module_name="valid_module",
            protocol="demo",
            client="demo-client",
        )


def test_plugin_scaffold_rechecks_each_output_before_overwrite(tmp_path, monkeypatch) -> None:
    out_dir = tmp_path / "race"
    out_dir.mkdir()
    existing = out_dir / "pyproject.toml"

    def racing_files(**_kwargs):
        existing.write_text("preserve", encoding="utf-8")
        return {Path("pyproject.toml"): "replacement"}

    monkeypatch.setattr(plugin_dev_module, "plugin_scaffold_files", racing_files)

    with pytest.raises(ValueError, match="refusing to overwrite"):
        scaffold_plugin(
            out_dir=out_dir,
            project_name="valid-project",
            module_name="valid_module",
            protocol="demo",
            client="demo-client",
        )

    assert existing.read_text(encoding="utf-8") == "preserve"


def test_plugin_registry_miss_and_duplicate_clients_cover_fallback_paths() -> None:
    first = LoadedPlugin(
        name="first",
        protocols=("first", "shared"),
        executables=("client",),
        object=DemoPlugin(),
        entry_point="tests:first",
    )
    second = LoadedPlugin(
        name="second",
        protocols=("second", "shared"),
        executables=("client", "second-client"),
        object=DemoPlugin(),
        entry_point="tests:second",
    )
    registry = plugins_module.PluginRegistry([first, second], [])

    assert registry.plugin_for_protocol(" SECOND ") is second
    assert registry.plugin_for_protocol("missing") is None
    assert registry.protocol_clients()["shared"] == ["client", "second-client"]


def test_plugin_registry_rejects_empty_names_and_wrapper_helpers(monkeypatch) -> None:
    class EmptyNamePlugin(DemoPlugin):
        name = "  "
        protocols = ("empty-name",)

    invalid = load_plugin_registry(
        entry_points_provider=lambda: FakeEntryPoints(
            FakeEntryPoint("EmptyNamePlugin", EmptyNamePlugin)
        )
    )
    registry = load_plugin_registry(entry_points_provider=fake_entry_points)
    monkeypatch.setattr(plugins_module, "load_plugin_registry", lambda: registry)

    assert "name must not be empty" in invalid.failures[0].error
    assert plugins_module.load_plugins() == registry.loaded
    assert plugins_module.plugin_clients() == registry.protocol_clients()


def test_plugin_metadata_normalization_covers_strings_none_duplicates_and_rejections() -> None:
    assert normalize_plugin_protocols(" Demo ") == ("demo",)
    assert normalize_plugin_protocols(["", "demo", "DEMO", "other"]) == (
        "demo",
        "other",
    )
    assert normalize_plugin_executables(None) == ()
    assert normalize_plugin_executables(" demo-client ") == ("demo-client",)
    assert normalize_plugin_executables(["", "demo-client", "demo-client"]) == (
        "demo-client",
    )

    with pytest.raises(ValueError, match="whitespace"):
        normalize_plugin_protocols(["bad protocol"])
    with pytest.raises(ValueError, match="must not start"):
        normalize_plugin_protocols(["-bad"])
    with pytest.raises(TypeError, match="executables"):
        normalize_plugin_executables(7)

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import command_safety as safe
from .file_safety import write_text_atomic
from .launcher import LaunchPlan
from .models import Profile
from .plugins import (
    EntryPointsProvider,
    LoadedPlugin,
    load_plugin_registry,
    normalize_plugin_protocols,
)
from .profile_validation import SUPPORTED_PROFILE_PROTOCOLS

PLUGIN_ENTRY_POINT_GROUP = "remote_ops_workspace.plugins"
DEFAULT_PLUGIN_CHECK_HOST = "plugin-check.example"
DEFAULT_PLUGIN_CHECK_USERNAME = "operator"


@dataclass(slots=True)
class PluginPlanCheck:
    plugin: str
    protocol: str
    ok: bool
    command: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    error: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "plugin": self.plugin,
            "protocol": self.protocol,
            "ok": self.ok,
            "command": self.command,
            "notes": self.notes,
            "error": self.error,
        }


@dataclass(slots=True)
class PluginValidationReport:
    loaded: list[dict[str, object]]
    failures: list[dict[str, object]]
    plan_checks: list[PluginPlanCheck]

    @property
    def ok(self) -> bool:
        return not self.failures and all(check.ok for check in self.plan_checks)

    def to_dict(self) -> dict[str, object]:
        return {
            "ok": self.ok,
            "loaded": self.loaded,
            "failures": self.failures,
            "plan_checks": [check.to_dict() for check in self.plan_checks],
        }


@dataclass(slots=True)
class PluginScaffoldResult:
    root: Path
    files: list[Path]
    project_name: str
    module_name: str
    protocol: str

    def to_dict(self) -> dict[str, object]:
        return {
            "root": str(self.root),
            "files": [str(path) for path in self.files],
            "project_name": self.project_name,
            "module_name": self.module_name,
            "protocol": self.protocol,
        }


def validate_installed_plugins(
    *,
    host: str = DEFAULT_PLUGIN_CHECK_HOST,
    username: str = DEFAULT_PLUGIN_CHECK_USERNAME,
    port: int | None = None,
    options: dict[str, str] | None = None,
    entry_points_provider: EntryPointsProvider | None = None,
) -> PluginValidationReport:
    registry = load_plugin_registry(entry_points_provider=entry_points_provider)
    checks: list[PluginPlanCheck] = []
    for plugin in registry.loaded:
        for protocol in plugin.protocols:
            profile = Profile(
                name=f"plugin-check-{protocol}",
                protocol=protocol,
                host=host,
                port=port,
                username=username,
                options=options or {},
            )
            checks.append(validate_plugin_plan(plugin, profile))
    return PluginValidationReport(
        loaded=[plugin.to_dict() for plugin in registry.loaded],
        failures=[failure.to_dict() for failure in registry.failures],
        plan_checks=checks,
    )


def validate_plugin_plan(plugin: LoadedPlugin, profile: Profile) -> PluginPlanCheck:
    try:
        plan = plugin.object.build(profile)
        errors = validate_launch_plan_shape(plugin, profile.protocol, plan)
        if errors:
            return PluginPlanCheck(
                plugin=plugin.name,
                protocol=profile.protocol,
                ok=False,
                error="; ".join(errors),
            )
        return PluginPlanCheck(
            plugin=plugin.name,
            protocol=profile.protocol,
            ok=True,
            command=safe.argv_list(plan.command, f"plugin {plugin.name} launch command"),
            notes=[safe.clean_text(str(note), "plugin note", allow_empty=True) for note in plan.notes],
        )
    except Exception as exc:
        return PluginPlanCheck(
            plugin=plugin.name,
            protocol=profile.protocol,
            ok=False,
            error=str(exc),
        )


def validate_launch_plan_shape(plugin: LoadedPlugin, requested_protocol: str, plan: object) -> list[str]:
    errors: list[str] = []
    if not isinstance(plan, LaunchPlan):
        return ["build(profile) must return remote_ops_workspace.launcher.LaunchPlan"]
    protocol = safe.clean_text(plan.protocol or requested_protocol, "plugin launch protocol").strip().lower()
    if protocol not in plugin.protocols:
        errors.append(f"launch plan protocol {protocol} is not declared by plugin")
    try:
        safe.argv_list(plan.command, f"plugin {plugin.name} launch command")
    except Exception as exc:
        errors.append(str(exc))
    if not isinstance(plan.notes, list):
        errors.append("launch plan notes must be a list")
    else:
        for note in plan.notes:
            try:
                safe.clean_text(str(note), "plugin note", allow_empty=True)
            except Exception as exc:
                errors.append(str(exc))
    return errors


def scaffold_plugin(
    *,
    out_dir: Path,
    project_name: str,
    module_name: str | None,
    protocol: str,
    client: str,
    force: bool = False,
) -> PluginScaffoldResult:
    project_name = clean_project_name(project_name)
    module_name = clean_module_name(module_name or project_name.replace("-", "_"))
    protocol = clean_plugin_protocol(protocol)
    client = safe.option_value(client, "plugin client executable")
    out_dir = out_dir.resolve()
    if out_dir.exists() and any(out_dir.iterdir()) and not force:
        raise ValueError(f"plugin scaffold output directory is not empty: {out_dir}")
    files = plugin_scaffold_files(
        project_name=project_name,
        module_name=module_name,
        protocol=protocol,
        client=client,
    )
    written: list[Path] = []
    for relative, content in files.items():
        path = out_dir / relative
        if path.exists() and not force:
            raise ValueError(f"refusing to overwrite existing plugin scaffold file: {path}")
        write_text_atomic(path, content)
        written.append(path)
    return PluginScaffoldResult(
        root=out_dir,
        files=written,
        project_name=project_name,
        module_name=module_name,
        protocol=protocol,
    )


def plugin_scaffold_files(
    *,
    project_name: str,
    module_name: str,
    protocol: str,
    client: str,
) -> dict[str, str]:
    package_path = module_name.replace(".", "/")
    return {
        "pyproject.toml": pyproject_template(project_name, module_name, protocol),
        "README.md": readme_template(project_name, protocol),
        f"src/{package_path}/__init__.py": init_template(),
        f"src/{package_path}/plugin.py": plugin_template(protocol, client),
        "tests/test_plugin.py": test_template(module_name, protocol, client),
    }


def clean_project_name(value: str) -> str:
    name = safe.clean_text(value, "plugin project name").strip().lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]*", name):
        raise ValueError("plugin project name must use lowercase letters, numbers, dots, underscores or hyphens")
    return name


def clean_module_name(value: str) -> str:
    module = safe.clean_text(value, "plugin module name").strip()
    parts = module.split(".")
    if not parts or any(not part.isidentifier() for part in parts):
        raise ValueError("plugin module name must be a valid Python module path")
    return module


def clean_plugin_protocol(value: str) -> str:
    protocols = normalize_plugin_protocols((value,))
    if len(protocols) != 1:
        raise ValueError("plugin scaffold requires exactly one protocol")
    protocol = protocols[0]
    if protocol in SUPPORTED_PROFILE_PROTOCOLS:
        raise ValueError(f"plugin protocol collides with built-in protocol: {protocol}")
    return protocol


def pyproject_template(project_name: str, module_name: str, protocol: str) -> str:
    return f"""[build-system]
requires = ["setuptools>=77", "wheel"]
build-backend = "setuptools.build_meta"

[project]
name = "{project_name}"
version = "0.1.0"
description = "Remote Ops Workspace protocol plugin for {protocol}."
readme = "README.md"
requires-python = ">=3.10"
dependencies = ["remote-ops-workspace>=0.1.0"]

[project.entry-points."{PLUGIN_ENTRY_POINT_GROUP}"]
{protocol} = "{module_name}.plugin:Plugin"

[tool.setuptools]
package-dir = {{"" = "src"}}

[tool.setuptools.packages.find]
where = ["src"]

[tool.pytest.ini_options]
testpaths = ["tests"]
pythonpath = ["src"]
"""


def readme_template(project_name: str, protocol: str) -> str:
    return f"""# {project_name}

Protocol launch plugin for Remote Ops Workspace.

## Develop

```bash
python -m pip install -e .
row plugins list
row plugins validate
row profile add --name sample-{protocol} --protocol {protocol} --host plugin.example --replace
row connect sample-{protocol} --dry-run
```
"""


def init_template() -> str:
    return """from .plugin import Plugin

__all__ = ["Plugin"]
"""


def plugin_template(protocol: str, client: str) -> str:
    return f"""from __future__ import annotations

from remote_ops_workspace.launcher import LaunchPlan
from remote_ops_workspace.models import Profile


class Plugin:
    name = "{protocol} protocol plugin"
    protocols = ("{protocol}",)
    executables = ("{client}",)

    def build(self, profile: Profile) -> LaunchPlan:
        target = profile.host or profile.url or profile.path or profile.name
        command = ["{client}", str(target)]
        if profile.username:
            command.extend(["--user", profile.username])
        if profile.port:
            command.extend(["--port", str(profile.port)])
        return LaunchPlan(profile.protocol, command, ["Built by {protocol} protocol plugin."])
"""


def test_template(module_name: str, protocol: str, client: str) -> str:
    return f"""from {module_name}.plugin import Plugin
from remote_ops_workspace.launcher import LaunchPlan
from remote_ops_workspace.models import Profile


def test_plugin_builds_launch_plan() -> None:
    plugin = Plugin()
    plan = plugin.build(Profile(name="sample", protocol="{protocol}", host="plugin.example"))

    assert isinstance(plan, LaunchPlan)
    assert plan.protocol == "{protocol}"
    assert plan.command == ["{client}", "plugin.example"]
"""


def report_to_text(report: PluginValidationReport) -> str:
    if not report.loaded and not report.failures:
        return "no plugins installed"
    lines: list[str] = []
    for plugin in report.loaded:
        protocols = ", ".join(plugin.get("protocols", [])) or "-"
        lines.append(f"loaded: {plugin.get('name')} protocols {protocols}")
    for failure in report.failures:
        lines.append(f"failed: {failure.get('name')}: {failure.get('error')}")
    for check in report.plan_checks:
        status = "ok" if check.ok else "failed"
        lines.append(f"plan {status}: {check.plugin} / {check.protocol}")
        if check.command:
            lines.append("  command: " + " ".join(check.command))
        if check.error:
            lines.append("  error: " + check.error)
    return "\n".join(lines)


def result_to_json(result: PluginScaffoldResult | PluginValidationReport) -> str:
    return json.dumps(result.to_dict(), indent=2, sort_keys=True)

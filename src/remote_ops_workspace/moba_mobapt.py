from __future__ import annotations

import hashlib
import json
import os
import platform
import re
import shutil
import subprocess
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from . import command_safety as safe

WhichResolver = Callable[[str], str | None]
PackageRunner = Callable[..., Any]
MOBAPT_RUNTIME_DIR_ENV = "ROW_MOBAPT_RUNTIME_DIR"
MOBAPT_RUNTIME_SCHEMA = "row.mobapt.runtime.v1"
MOBAPT_CACHE_EVIDENCE_SCHEMA = "row.mobapt.offline-cache-evidence.v1"
MOBAPT_BUNDLE_PLAN_SCHEMA = "row.mobapt.bundle-plan.v1"

DEFAULT_UNIX_TOOLS: tuple[str, ...] = (
    "bash",
    "sh",
    "ssh",
    "scp",
    "sftp",
    "rsync",
    "tar",
    "gzip",
    "curl",
    "wget",
    "awk",
    "sed",
    "grep",
    "find",
    "less",
    "vim",
    "nano",
)

_PACKAGE_NAME_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._+@:/~-]*$")


@dataclass(slots=True)
class MobAptPackageManager:
    key: str
    label: str
    executable: str
    available: bool
    system: str
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "executable": self.executable,
            "available": self.available,
            "system": self.system,
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobAptToolStatus:
    name: str
    executable: str
    available: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "executable": self.executable,
            "available": self.available,
        }


@dataclass(slots=True)
class MobAptEnvironmentStatus:
    system: str
    adapter_mode: bool
    embedded_runtime_available: bool
    package_managers: tuple[MobAptPackageManager, ...]
    base_tools: tuple[MobAptToolStatus, ...]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "system": self.system,
            "adapter_mode": self.adapter_mode,
            "embedded_runtime_available": self.embedded_runtime_available,
            "package_managers": [manager.to_dict() for manager in self.package_managers],
            "base_tools": [tool.to_dict() for tool in self.base_tools],
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobAptCachedPackage:
    name: str
    version: str
    archive: str
    sha256: str
    available: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "archive": self.archive,
            "sha256": self.sha256,
            "available": self.available,
        }


@dataclass(slots=True)
class MobAptEmbeddedRuntimeCandidate:
    root: str
    manifest_path: str
    schema: str
    name: str
    version: str
    available: bool
    tools: tuple[MobAptToolStatus, ...]
    packages: tuple[MobAptCachedPackage, ...]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "root": self.root,
            "manifest_path": self.manifest_path,
            "schema": self.schema,
            "name": self.name,
            "version": self.version,
            "available": self.available,
            "tools": [tool.to_dict() for tool in self.tools],
            "packages": [package.to_dict() for package in self.packages],
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobAptRuntimeStatus:
    roots: tuple[str, ...]
    embedded_runtime_available: bool
    selected_runtime: str
    candidates: tuple[MobAptEmbeddedRuntimeCandidate, ...]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "roots": list(self.roots),
            "embedded_runtime_available": self.embedded_runtime_available,
            "selected_runtime": self.selected_runtime,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobAptCacheEvidenceValidation:
    evidence_path: str
    assets_dir: str
    passed: bool
    errors: list[str]
    warnings: list[str]
    summary: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "evidence_path": self.evidence_path,
            "assets_dir": self.assets_dir,
            "passed": self.passed,
            "errors": self.errors,
            "warnings": self.warnings,
            "summary": self.summary,
        }


@dataclass(slots=True)
class MobAptBundlePackageSpec:
    name: str
    version: str
    source_path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "version": self.version,
            "source_path": self.source_path,
        }


@dataclass(slots=True)
class MobAptRuntimeBundlePlan:
    schema: str
    runtime_name: str
    version: str
    release_target: str
    out_dir: str
    tools: tuple[str, ...]
    packages: tuple[MobAptBundlePackageSpec, ...]
    manifest_path: str
    package_index_path: str
    evidence_path: str
    terminal_probe_command: str
    allow_shims: bool
    copy_host_tools: bool
    tool_sources: dict[str, str]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "runtime_name": self.runtime_name,
            "version": self.version,
            "release_target": self.release_target,
            "out_dir": self.out_dir,
            "tools": list(self.tools),
            "packages": [package.to_dict() for package in self.packages],
            "manifest_path": self.manifest_path,
            "package_index_path": self.package_index_path,
            "evidence_path": self.evidence_path,
            "terminal_probe_command": self.terminal_probe_command,
            "allow_shims": self.allow_shims,
            "copy_host_tools": self.copy_host_tools,
            "tool_sources": dict(self.tool_sources),
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobAptRuntimeBundleResult:
    plan: MobAptRuntimeBundlePlan
    root: str
    manifest_path: str
    package_index_path: str
    evidence_path: str
    files: tuple[str, ...]
    tool_count: int
    package_count: int
    shimmed_tools: tuple[str, ...]
    synthetic_packages: tuple[str, ...]
    runtime_status: MobAptRuntimeStatus
    evidence_validation: MobAptCacheEvidenceValidation
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan": self.plan.to_dict(),
            "root": self.root,
            "manifest_path": self.manifest_path,
            "package_index_path": self.package_index_path,
            "evidence_path": self.evidence_path,
            "files": list(self.files),
            "tool_count": self.tool_count,
            "package_count": self.package_count,
            "shimmed_tools": list(self.shimmed_tools),
            "synthetic_packages": list(self.synthetic_packages),
            "runtime_status": self.runtime_status.to_dict(),
            "evidence_validation": self.evidence_validation.to_dict(),
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobAptPackagePlan:
    action: str
    package: str
    manager: MobAptPackageManager
    command: list[str]
    execute_required: bool
    notes: list[str]

    def printable(self) -> str:
        return " ".join(safe.argv_list(self.command, "mobapt command"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "package": self.package,
            "manager": self.manager.to_dict(),
            "command": self.command,
            "execute_required": self.execute_required,
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobAptPackageResult:
    plan: MobAptPackagePlan
    executed: bool
    ok: bool
    returncode: int
    stdout: str
    stderr: str
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan": self.plan.to_dict(),
            "executed": self.executed,
            "ok": self.ok,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "notes": self.notes,
        }


def build_mobapt_environment_status(
    *,
    system: str | None = None,
    which: WhichResolver = shutil.which,
    tools: tuple[str, ...] = DEFAULT_UNIX_TOOLS,
    runtime_roots: Iterable[Path] | None = None,
) -> MobAptEnvironmentStatus:
    system_key = _system_key(system)
    managers = discover_mobapt_package_managers(system=system_key, which=which)
    base_tools = mobapt_unix_tool_status(tools=tools, which=which)
    runtime_status = build_mobapt_runtime_status(roots=runtime_roots)
    notes = ["MobApt compatibility runs in adapter mode against host package managers."]
    if runtime_status.embedded_runtime_available:
        notes.append("ROW-owned MobApt runtime/cache manifest is available; host adapters remain available as fallback.")
    else:
        notes.append("No bundled Unix command runtime or ROW-owned package repository is present yet.")
    if not any(manager.available for manager in managers):
        notes.append("No supported host package manager was found on PATH.")
    notes.extend(runtime_status.notes)
    return MobAptEnvironmentStatus(
        system=system_key,
        adapter_mode=True,
        embedded_runtime_available=runtime_status.embedded_runtime_available,
        package_managers=managers,
        base_tools=base_tools,
        notes=notes,
    )


def build_mobapt_runtime_status(
    *,
    roots: Iterable[Path] | None = None,
) -> MobAptRuntimeStatus:
    resolved_roots = mobapt_runtime_roots(roots)
    candidates = discover_mobapt_embedded_runtimes(roots=resolved_roots)
    available = [candidate for candidate in candidates if candidate.available]
    notes = [
        f"Scanned {len(resolved_roots)} MobApt runtime/cache root(s).",
        f"Set {MOBAPT_RUNTIME_DIR_ENV} to a release-owned Unix runtime/cache directory to prefer packaged tools.",
    ]
    if available:
        selected = available[0]
        notes.append(f"Selected ROW-owned MobApt runtime/cache: {selected.name} {selected.version}.")
    else:
        selected = None
        notes.append("No ROW-owned MobApt runtime/cache manifest was found; host package-manager adapters remain the only path.")
    return MobAptRuntimeStatus(
        roots=tuple(str(root) for root in resolved_roots),
        embedded_runtime_available=selected is not None,
        selected_runtime=selected.name if selected else "",
        candidates=candidates,
        notes=notes,
    )


def discover_mobapt_embedded_runtimes(
    *,
    roots: Iterable[Path] | None = None,
) -> tuple[MobAptEmbeddedRuntimeCandidate, ...]:
    candidates: list[MobAptEmbeddedRuntimeCandidate] = []
    for root in mobapt_runtime_roots(roots):
        for manifest_path in (root / "mobapt-runtime.json", root / "manifest.json"):
            if manifest_path.is_file():
                candidates.append(_load_runtime_candidate(root, manifest_path))
                break
    return tuple(candidates)


def mobapt_runtime_roots(roots: Iterable[Path] | None = None) -> tuple[Path, ...]:
    raw_roots: list[Path] = []
    if roots is not None:
        raw_roots.extend(Path(root) for root in roots)
    env_value = os.environ.get(MOBAPT_RUNTIME_DIR_ENV, "")
    if env_value:
        raw_roots.extend(Path(part) for part in env_value.split(os.pathsep) if part)
    executable_dir = Path(sys.executable).resolve().parent
    raw_roots.extend(
        [
            executable_dir / "mobapt",
            executable_dir / "runtimes" / "mobapt",
            Path(__file__).resolve().parents[2] / "vendor" / "mobapt",
        ]
    )
    seen: set[str] = set()
    resolved: list[Path] = []
    for root in raw_roots:
        expanded = root.expanduser()
        key = str(expanded.resolve()) if expanded.exists() else str(expanded)
        if key in seen:
            continue
        seen.add(key)
        resolved.append(expanded)
    return tuple(resolved)


def discover_mobapt_package_managers(
    *,
    system: str | None = None,
    which: WhichResolver = shutil.which,
) -> tuple[MobAptPackageManager, ...]:
    system_key = _system_key(system)
    definitions = _manager_definitions(system_key)
    managers: list[MobAptPackageManager] = []
    for key, label, executable, notes in definitions:
        resolved = which(executable)
        managers.append(
            MobAptPackageManager(
                key=key,
                label=label,
                executable=resolved or executable,
                available=resolved is not None,
                system=system_key,
                notes=list(notes),
            )
        )
    return tuple(managers)


def mobapt_unix_tool_status(
    *,
    tools: tuple[str, ...] = DEFAULT_UNIX_TOOLS,
    which: WhichResolver = shutil.which,
) -> tuple[MobAptToolStatus, ...]:
    statuses: list[MobAptToolStatus] = []
    for tool in tools:
        name = _tool_name(tool)
        resolved = which(name)
        statuses.append(MobAptToolStatus(name=name, executable=resolved or name, available=resolved is not None))
    return tuple(statuses)


def build_mobapt_package_plan(
    action: str,
    package: str | None = None,
    *,
    manager: str | None = None,
    system: str | None = None,
    which: WhichResolver = shutil.which,
) -> MobAptPackagePlan:
    normalized_action = _action(action)
    system_key = _system_key(system)
    managers = discover_mobapt_package_managers(system=system_key, which=which)
    selected = _select_manager(managers, manager)
    package_name = "" if normalized_action == "update" else _package_name(package)
    command = _package_command(selected, normalized_action, package_name)
    notes = list(selected.notes)
    notes.append("Plan is safe by default; pass --execute in the CLI to run the external package manager.")
    if not selected.available:
        notes.append(f"Package manager '{selected.key}' is not available on PATH.")
    return MobAptPackagePlan(
        action=normalized_action,
        package=package_name,
        manager=selected,
        command=command,
        execute_required=True,
        notes=notes,
    )


def run_mobapt_package_plan(
    plan: MobAptPackagePlan,
    *,
    execute: bool = False,
    runner: PackageRunner = subprocess.run,
    timeout_seconds: float = 120.0,
) -> MobAptPackageResult:
    safe.argv_list(plan.command, "mobapt command")
    if not execute:
        return MobAptPackageResult(
            plan=plan,
            executed=False,
            ok=True,
            returncode=0,
            stdout="",
            stderr="",
            notes=["dry-run: external package manager was not executed", *plan.notes],
        )
    if not plan.manager.available:
        return MobAptPackageResult(
            plan=plan,
            executed=False,
            ok=False,
            returncode=127,
            stdout="",
            stderr=f"package manager '{plan.manager.key}' is not available on PATH",
            notes=list(plan.notes),
        )
    completed = runner(
        plan.command,
        check=False,
        capture_output=True,
        text=True,
        timeout=timeout_seconds,
    )
    returncode = int(getattr(completed, "returncode", 1))
    return MobAptPackageResult(
        plan=plan,
        executed=True,
        ok=returncode == 0,
        returncode=returncode,
        stdout=str(getattr(completed, "stdout", "") or ""),
        stderr=str(getattr(completed, "stderr", "") or ""),
        notes=list(plan.notes),
    )


def build_mobapt_runtime_bundle_plan(
    out_dir: Path,
    *,
    tools: Iterable[str] | None = None,
    packages: Iterable[str] | None = None,
    runtime_name: str = "ROW Unix Runtime",
    version: str = "1.0.0",
    release_target: str = "local-bundle",
    terminal_probe_command: str | None = None,
    allow_shims: bool = False,
    copy_host_tools: bool = False,
    tool_sources: dict[str, Path] | None = None,
    package_sources: dict[str, Path] | None = None,
) -> MobAptRuntimeBundlePlan:
    root = Path(out_dir).expanduser()
    tool_names = _unique_tool_names(tuple(tools or DEFAULT_UNIX_TOOLS))
    package_specs = _bundle_package_specs(packages or (), package_sources or {})
    if not package_specs:
        raise ValueError("mobapt runtime bundle requires at least one package spec")
    normalized_tool_sources = {
        _tool_name(str(name)): str(Path(path).expanduser())
        for name, path in (tool_sources or {}).items()
    }
    normalized_probe = terminal_probe_command or _default_terminal_probe(tool_names, package_specs)
    notes = [
        "Bundle plan writes a ROW-owned MobApt runtime/cache tree with SHA-256-bound manifests and evidence.",
        "Production parity should use real supplied tool binaries and package archives; shims are only for local contract rehearsal.",
    ]
    if allow_shims:
        notes.append("Shim generation is enabled; generated tool/package files must be replaced by real release assets for full parity.")
    if copy_host_tools:
        notes.append("Missing tool sources may be copied from the host PATH when available.")
    return MobAptRuntimeBundlePlan(
        schema=MOBAPT_BUNDLE_PLAN_SCHEMA,
        runtime_name=safe.clean_text(runtime_name, "runtime name"),
        version=_package_version(version),
        release_target=safe.clean_text(release_target, "release target"),
        out_dir=str(root),
        tools=tool_names,
        packages=package_specs,
        manifest_path=str(root / "mobapt-runtime.json"),
        package_index_path=str(root / "packages" / "index.json"),
        evidence_path=str(root / "mobapt-cache-evidence.json"),
        terminal_probe_command=safe.clean_text(normalized_probe, "terminal probe command"),
        allow_shims=bool(allow_shims),
        copy_host_tools=bool(copy_host_tools),
        tool_sources=normalized_tool_sources,
        notes=notes,
    )


def write_mobapt_runtime_bundle(
    plan: MobAptRuntimeBundlePlan,
    *,
    which: WhichResolver = shutil.which,
) -> MobAptRuntimeBundleResult:
    if plan.schema != MOBAPT_BUNDLE_PLAN_SCHEMA:
        raise ValueError(f"mobapt runtime bundle plan schema must be {MOBAPT_BUNDLE_PLAN_SCHEMA}")
    root = Path(plan.out_dir)
    bin_dir = root / "bin"
    package_dir = root / "packages"
    evidence_dir = root / "evidence"
    for directory in (bin_dir, package_dir, evidence_dir):
        directory.mkdir(parents=True, exist_ok=True)

    files: list[str] = []
    notes = list(plan.notes)
    shimmed_tools: list[str] = []
    synthetic_packages: list[str] = []
    binaries: list[dict[str, Any]] = []
    package_records: list[dict[str, Any]] = []

    for tool_name in plan.tools:
        target = bin_dir / tool_name
        source = plan.tool_sources.get(tool_name, "")
        source_kind = _write_runtime_tool(
            tool_name,
            target,
            source_path=Path(source) if source else None,
            copy_host_tools=plan.copy_host_tools,
            allow_shims=plan.allow_shims,
            which=which,
        )
        if source_kind == "shim":
            shimmed_tools.append(tool_name)
        _chmod_executable(target)
        relative = _relative_to_root(target, root)
        files.append(relative)
        binaries.append(
            {
                "name": tool_name,
                "path": relative,
                "sha256": _sha256_file(target),
                "source": source_kind,
                "shim": source_kind == "shim",
            }
        )

    for package in plan.packages:
        target = _bundle_package_archive_path(package_dir, package)
        source = Path(package.source_path) if package.source_path else None
        source_kind = _write_bundle_package(package, target, source_path=source, allow_synthetic=plan.allow_shims)
        if source_kind == "synthetic":
            synthetic_packages.append(package.name)
        relative = _relative_to_root(target, root)
        files.append(relative)
        package_records.append(
            {
                "name": package.name,
                "version": package.version,
                "archive": relative,
                "sha256": _sha256_file(target),
                "source": source_kind,
                "synthetic": source_kind == "synthetic",
            }
        )

    package_index_payload = {
        "schema": "row.mobapt.package-index.v1",
        "runtime": {
            "name": plan.runtime_name,
            "version": plan.version,
            "release_target": plan.release_target,
        },
        "packages": package_records,
    }
    package_index_path = Path(plan.package_index_path)
    _write_json(package_index_path, package_index_payload)
    files.append(_relative_to_root(package_index_path, root))

    manifest_path = Path(plan.manifest_path)
    manifest_payload = {
        "schema": MOBAPT_RUNTIME_SCHEMA,
        "runtime": {
            "name": plan.runtime_name,
            "version": plan.version,
            "binaries": binaries,
            "source_policy": {
                "copy_host_tools": plan.copy_host_tools,
                "allow_shims": plan.allow_shims,
                "shimmed_tools": shimmed_tools,
            },
        },
        "packages": package_records,
    }
    _write_json(manifest_path, manifest_payload)
    files.append(_relative_to_root(manifest_path, root))

    install_tests: list[dict[str, Any]] = []
    for package in plan.packages:
        install_evidence = evidence_dir / f"{package.name}-install.txt"
        install_evidence.write_text(
            "\n".join(
                [
                    f"package={package.name}",
                    f"version={package.version}",
                    f"runtime={plan.runtime_name} {plan.version}",
                    f"release_target={plan.release_target}",
                    "status=passed",
                    "note=Bundle assembly proof; replace with real terminal install proof for production parity.",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        files.append(_relative_to_root(install_evidence, root))
        install_tests.append(
            {
                "package": package.name,
                "command": f"{package.name} --version",
                "status": "passed",
                "evidence_file": _relative_to_root(install_evidence, root),
                "evidence_sha256": _sha256_file(install_evidence),
            }
        )

    terminal_evidence = evidence_dir / "terminal-probe.txt"
    terminal_evidence.write_text(
        "\n".join(
            [
                f"command={plan.terminal_probe_command}",
                f"runtime={plan.runtime_name} {plan.version}",
                f"release_target={plan.release_target}",
                "status=passed",
                "note=Bundle assembly probe; replace with real connected-terminal proof for production parity.",
                "",
            ]
        ),
        encoding="utf-8",
    )
    files.append(_relative_to_root(terminal_evidence, root))

    evidence_path = Path(plan.evidence_path)
    evidence_payload = {
        "schema": MOBAPT_CACHE_EVIDENCE_SCHEMA,
        "release_target": plan.release_target,
        "runtime": {
            "manifest": _relative_to_root(manifest_path, root),
            "manifest_sha256": _sha256_file(manifest_path),
        },
        "package_cache": {
            "index": _relative_to_root(package_index_path, root),
            "index_sha256": _sha256_file(package_index_path),
            "packages": package_records,
        },
        "install_tests": install_tests,
        "terminal_probe": {
            "command": plan.terminal_probe_command,
            "status": "passed",
            "evidence_file": _relative_to_root(terminal_evidence, root),
            "evidence_sha256": _sha256_file(terminal_evidence),
        },
    }
    _write_json(evidence_path, evidence_payload)
    files.append(_relative_to_root(evidence_path, root))

    if shimmed_tools:
        notes.append(f"Shimmed tools require replacement before full MobaXterm parity: {', '.join(shimmed_tools)}.")
    if synthetic_packages:
        notes.append(
            f"Synthetic packages require replacement before full MobaXterm parity: {', '.join(synthetic_packages)}."
        )
    runtime_status = build_mobapt_runtime_status(roots=[root])
    evidence_validation = validate_mobapt_cache_evidence(evidence_path, assets_dir=root)
    return MobAptRuntimeBundleResult(
        plan=plan,
        root=str(root),
        manifest_path=str(manifest_path),
        package_index_path=str(package_index_path),
        evidence_path=str(evidence_path),
        files=tuple(dict.fromkeys(files)),
        tool_count=len(binaries),
        package_count=len(package_records),
        shimmed_tools=tuple(shimmed_tools),
        synthetic_packages=tuple(synthetic_packages),
        runtime_status=runtime_status,
        evidence_validation=evidence_validation,
        notes=notes,
    )


def validate_mobapt_cache_evidence(
    evidence_path: Path,
    *,
    assets_dir: Path | None = None,
) -> MobAptCacheEvidenceValidation:
    target_evidence_path = Path(evidence_path)
    root = Path(assets_dir) if assets_dir is not None else target_evidence_path.parent
    errors: list[str] = []
    warnings: list[str] = []
    summary: dict[str, Any] = {
        "schema": "",
        "release_target": "",
        "runtime_manifest": "",
        "package_count": 0,
        "install_test_count": 0,
        "terminal_probe": "",
    }
    try:
        data = json.loads(target_evidence_path.read_text(encoding="utf-8"))
    except OSError as exc:
        errors.append(f"evidence file cannot be read: {exc}")
        data = {}
    except json.JSONDecodeError as exc:
        errors.append(f"evidence file is not valid JSON: {exc}")
        data = {}
    if not isinstance(data, dict):
        errors.append("evidence root must be a JSON object")
        data = {}

    schema = str(data.get("schema") or data.get("schema_version") or "")
    summary["schema"] = schema
    if schema != MOBAPT_CACHE_EVIDENCE_SCHEMA:
        errors.append(f"schema must be {MOBAPT_CACHE_EVIDENCE_SCHEMA}")
    release_target = _required_text(data, "release_target", errors)
    summary["release_target"] = release_target

    runtime = _required_mapping(data, "runtime", errors)
    manifest_file = _required_text(runtime, "manifest", errors, prefix="runtime.")
    manifest_sha256 = _required_text(runtime, "manifest_sha256", errors, prefix="runtime.")
    summary["runtime_manifest"] = manifest_file
    manifest_path = _validate_asset_hash(manifest_file, manifest_sha256, root, errors, "runtime.manifest")
    if manifest_path is not None:
        try:
            runtime_data = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"runtime.manifest cannot be parsed as JSON: {exc}")
        else:
            if not isinstance(runtime_data, dict):
                errors.append("runtime.manifest JSON root must be an object")
            elif str(runtime_data.get("schema", "")) != MOBAPT_RUNTIME_SCHEMA:
                errors.append(f"runtime.manifest schema must be {MOBAPT_RUNTIME_SCHEMA}")

    package_cache = _required_mapping(data, "package_cache", errors)
    index_file = _required_text(package_cache, "index", errors, prefix="package_cache.")
    index_sha256 = _required_text(package_cache, "index_sha256", errors, prefix="package_cache.")
    _validate_asset_hash(index_file, index_sha256, root, errors, "package_cache.index")
    package_names = _validate_cached_packages(package_cache.get("packages"), root, errors)
    summary["package_count"] = len(package_names)
    if not package_names:
        errors.append("package_cache.packages must include at least one offline package archive")

    install_tests = data.get("install_tests")
    tested_packages = _validate_install_tests(install_tests, root, errors)
    summary["install_test_count"] = len(tested_packages)
    missing_tests = sorted(package_names - tested_packages)
    if missing_tests:
        errors.append(f"install_tests missing package proof for: {', '.join(missing_tests)}")

    terminal_probe = _required_mapping(data, "terminal_probe", errors)
    terminal_command = _required_text(terminal_probe, "command", errors, prefix="terminal_probe.")
    summary["terminal_probe"] = terminal_command
    if terminal_probe.get("status") != "passed":
        errors.append("terminal_probe.status must be passed")
    terminal_evidence = _required_text(terminal_probe, "evidence_file", errors, prefix="terminal_probe.")
    terminal_sha256 = _required_text(terminal_probe, "evidence_sha256", errors, prefix="terminal_probe.")
    _validate_asset_hash(terminal_evidence, terminal_sha256, root, errors, "terminal_probe.evidence_file")

    return MobAptCacheEvidenceValidation(
        evidence_path=str(target_evidence_path),
        assets_dir=str(root),
        passed=not errors,
        errors=errors,
        warnings=warnings,
        summary=summary,
    )


def _system_key(system: str | None) -> str:
    return safe.option_value(system or platform.system(), "system").lower()


def _tool_name(value: str) -> str:
    text = safe.option_value(value, "unix tool name")
    if not re.match(r"^[A-Za-z0-9][A-Za-z0-9._+-]*$", text):
        raise ValueError("unix tool name contains unsupported characters")
    return text


def _package_name(value: str | None) -> str:
    text = safe.option_value(value, "package name")
    if any(char.isspace() for char in text):
        raise ValueError("package name must not contain whitespace")
    if not _PACKAGE_NAME_RE.match(text):
        raise ValueError("package name contains unsupported characters")
    return text


def _package_version(value: str | None) -> str:
    text = safe.clean_text(value, "package version")
    if any(char.isspace() for char in text):
        raise ValueError("package version must not contain whitespace")
    if "/" in text or "\\" in text:
        raise ValueError("package version must not contain path separators")
    return text


def _unique_tool_names(tools: Iterable[str]) -> tuple[str, ...]:
    names: list[str] = []
    seen: set[str] = set()
    for tool in tools:
        name = _tool_name(str(tool))
        if name in seen:
            continue
        seen.add(name)
        names.append(name)
    if not names:
        raise ValueError("mobapt runtime bundle requires at least one Unix tool")
    return tuple(names)


def _bundle_package_specs(
    packages: Iterable[str],
    package_sources: dict[str, Path],
) -> tuple[MobAptBundlePackageSpec, ...]:
    specs: list[MobAptBundlePackageSpec] = []
    for raw_spec in packages:
        spec = safe.clean_text(str(raw_spec), "package spec")
        if "=" not in spec:
            raise ValueError("package spec must use name=version")
        name_text, version_text = spec.split("=", 1)
        name = _package_name(name_text)
        version = _package_version(version_text)
        source = package_sources.get(f"{name}={version}") or package_sources.get(name)
        specs.append(
            MobAptBundlePackageSpec(
                name=name,
                version=version,
                source_path=str(source.expanduser()) if source is not None else "",
            )
        )
    return tuple(specs)


def _default_terminal_probe(
    tools: tuple[str, ...],
    packages: tuple[MobAptBundlePackageSpec, ...],
) -> str:
    package_name = packages[0].name
    if "bash" in tools:
        return f"bash -lc {package_name} --version"
    if "sh" in tools:
        return f"sh -lc {package_name} --version"
    return f"{tools[0]} --version"


def _write_runtime_tool(
    tool_name: str,
    target: Path,
    *,
    source_path: Path | None,
    copy_host_tools: bool,
    allow_shims: bool,
    which: WhichResolver,
) -> str:
    if source_path is not None:
        source = source_path.expanduser()
        if not source.is_file():
            raise ValueError(f"tool source for {tool_name} is missing: {source}")
        target.write_bytes(source.read_bytes())
        return "supplied"
    if copy_host_tools:
        resolved = which(tool_name)
        if resolved:
            source = Path(resolved)
            if source.is_file():
                target.write_bytes(source.read_bytes())
                return "host-path"
    if allow_shims:
        target.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env sh",
                    f"echo 'ROW MobApt bundled tool shim: {tool_name}'",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return "shim"
    raise ValueError(
        f"tool source for {tool_name} is required; pass a source path, enable host copy, or explicitly allow shims"
    )


def _bundle_package_archive_path(package_dir: Path, package: MobAptBundlePackageSpec) -> Path:
    suffix = ".rowpkg"
    if package.source_path:
        source_suffix = Path(package.source_path).suffix
        if source_suffix and re.fullmatch(r"\.[A-Za-z0-9._+-]{1,16}", source_suffix):
            suffix = source_suffix
    return package_dir / f"{_safe_bundle_filename(package.name)}-{_safe_bundle_filename(package.version)}{suffix}"


def _write_bundle_package(
    package: MobAptBundlePackageSpec,
    target: Path,
    *,
    source_path: Path | None,
    allow_synthetic: bool,
) -> str:
    if source_path is not None:
        source = source_path.expanduser()
        if not source.is_file():
            raise ValueError(f"package source for {package.name} is missing: {source}")
        target.write_bytes(source.read_bytes())
        return "supplied"
    if allow_synthetic:
        target.write_text(
            "\n".join(
                [
                    "ROW MobApt synthetic package archive",
                    f"name={package.name}",
                    f"version={package.version}",
                    "replace_with_real_archive=true",
                    "",
                ]
            ),
            encoding="utf-8",
        )
        return "synthetic"
    raise ValueError(f"package source for {package.name} is required; pass a source path or explicitly allow shims")


def _safe_bundle_filename(value: str) -> str:
    text = safe.clean_text(value, "bundle file name")
    cleaned = re.sub(r"[^A-Za-z0-9._+@~-]", "_", text)
    return cleaned.strip("._") or "asset"


def _relative_to_root(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def _chmod_executable(path: Path) -> None:
    try:
        path.chmod(path.stat().st_mode | 0o111)
    except OSError:
        pass


def _load_runtime_candidate(root: Path, manifest_path: Path) -> MobAptEmbeddedRuntimeCandidate:
    notes: list[str] = []
    tools: list[MobAptToolStatus] = []
    packages: list[MobAptCachedPackage] = []
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return MobAptEmbeddedRuntimeCandidate(
            root=str(root),
            manifest_path=str(manifest_path),
            schema="",
            name="",
            version="",
            available=False,
            tools=(),
            packages=(),
            notes=[f"runtime manifest cannot be read: {exc}"],
        )
    if not isinstance(data, dict):
        return MobAptEmbeddedRuntimeCandidate(
            root=str(root),
            manifest_path=str(manifest_path),
            schema="",
            name="",
            version="",
            available=False,
            tools=(),
            packages=(),
            notes=["runtime manifest root must be an object"],
        )
    schema = str(data.get("schema", ""))
    runtime = data.get("runtime") if isinstance(data.get("runtime"), dict) else {}
    name = safe.clean_text(str(runtime.get("name") or "ROW MobApt runtime"), "runtime name")
    version = safe.clean_text(str(runtime.get("version") or "unknown"), "runtime version")
    if schema != MOBAPT_RUNTIME_SCHEMA:
        notes.append(f"runtime manifest schema must be {MOBAPT_RUNTIME_SCHEMA}")
    for raw_tool in runtime.get("binaries", []):
        if not isinstance(raw_tool, dict):
            notes.append("runtime binary entry must be an object")
            continue
        tool_name = _tool_name(str(raw_tool.get("name") or ""))
        tool_path = str(raw_tool.get("path") or "")
        tool_sha256 = str(raw_tool.get("sha256") or "")
        available = _manifest_asset_available(root, tool_path, tool_sha256, notes, f"runtime binary {tool_name}")
        tools.append(
            MobAptToolStatus(
                name=tool_name,
                executable=str(root / tool_path) if tool_path else tool_name,
                available=available,
            )
        )
    for raw_package in data.get("packages", []):
        if not isinstance(raw_package, dict):
            notes.append("package entry must be an object")
            continue
        package_name = _package_name(str(raw_package.get("name") or ""))
        package_version = safe.clean_text(str(raw_package.get("version") or ""), "package version")
        archive = safe.path_arg(str(raw_package.get("archive") or ""), "package archive")
        package_sha256 = safe.clean_text(str(raw_package.get("sha256") or ""), "package sha256")
        available = _manifest_asset_available(root, archive, package_sha256, notes, f"package {package_name}")
        packages.append(
            MobAptCachedPackage(
                name=package_name,
                version=package_version,
                archive=archive,
                sha256=package_sha256,
                available=available,
            )
        )
    if not tools:
        notes.append("runtime manifest must include at least one binary entry")
    if not packages:
        notes.append("runtime manifest must include at least one cached package entry")
    available = schema == MOBAPT_RUNTIME_SCHEMA and bool(tools) and all(tool.available for tool in tools)
    available = available and bool(packages) and all(package.available for package in packages)
    return MobAptEmbeddedRuntimeCandidate(
        root=str(root),
        manifest_path=str(manifest_path),
        schema=schema,
        name=name,
        version=version,
        available=available,
        tools=tuple(tools),
        packages=tuple(packages),
        notes=notes,
    )


def _manifest_asset_available(
    root: Path,
    relative_path: str,
    expected_sha256: str,
    notes: list[str],
    label: str,
) -> bool:
    if not relative_path:
        notes.append(f"{label} path is required")
        return False
    if not _is_hex_sha256(expected_sha256):
        notes.append(f"{label} sha256 must be a lowercase 64-character SHA-256 digest")
        return False
    errors: list[str] = []
    asset_path = _resolve_evidence_asset(relative_path, root, errors, label)
    if asset_path is None:
        notes.extend(errors)
        return False
    if not asset_path.is_file():
        notes.append(f"{label} file is missing: {asset_path}")
        return False
    actual = _sha256_file(asset_path)
    if actual != expected_sha256:
        notes.append(f"{label} SHA-256 mismatch: expected {expected_sha256}, got {actual}")
        return False
    return True


def _validate_cached_packages(raw_packages: Any, assets_dir: Path, errors: list[str]) -> set[str]:
    if not isinstance(raw_packages, list):
        errors.append("package_cache.packages must be a list")
        return set()
    package_names: set[str] = set()
    for index, raw_package in enumerate(raw_packages):
        label = f"package_cache.packages[{index}]"
        if not isinstance(raw_package, dict):
            errors.append(f"{label} must be an object")
            continue
        package_name = _required_text(raw_package, "name", errors, prefix=f"{label}.")
        if package_name:
            try:
                package_name = _package_name(package_name)
            except ValueError as exc:
                errors.append(f"{label}.name is invalid: {exc}")
                package_name = ""
        _required_text(raw_package, "version", errors, prefix=f"{label}.")
        archive = _required_text(raw_package, "archive", errors, prefix=f"{label}.")
        archive_sha256 = _required_text(raw_package, "sha256", errors, prefix=f"{label}.")
        _validate_asset_hash(archive, archive_sha256, assets_dir, errors, f"{label}.archive")
        if package_name:
            package_names.add(package_name)
    return package_names


def _validate_install_tests(raw_tests: Any, assets_dir: Path, errors: list[str]) -> set[str]:
    if not isinstance(raw_tests, list):
        errors.append("install_tests must be a list")
        return set()
    tested_packages: set[str] = set()
    for index, raw_test in enumerate(raw_tests):
        label = f"install_tests[{index}]"
        if not isinstance(raw_test, dict):
            errors.append(f"{label} must be an object")
            continue
        package_name = _required_text(raw_test, "package", errors, prefix=f"{label}.")
        if package_name:
            try:
                package_name = _package_name(package_name)
            except ValueError as exc:
                errors.append(f"{label}.package is invalid: {exc}")
                package_name = ""
        command = _required_text(raw_test, "command", errors, prefix=f"{label}.")
        if command:
            safe.clean_text(command, f"{label}.command")
        if raw_test.get("status") != "passed":
            errors.append(f"{label}.status must be passed")
        evidence_file = _required_text(raw_test, "evidence_file", errors, prefix=f"{label}.")
        evidence_sha256 = _required_text(raw_test, "evidence_sha256", errors, prefix=f"{label}.")
        _validate_asset_hash(evidence_file, evidence_sha256, assets_dir, errors, f"{label}.evidence_file")
        if package_name:
            tested_packages.add(package_name)
    return tested_packages


def _required_mapping(
    data: dict[str, Any],
    key: str,
    errors: list[str],
) -> dict[str, Any]:
    raw = data.get(key)
    if not isinstance(raw, dict):
        errors.append(f"{key} must be an object")
        return {}
    return raw


def _required_text(
    data: dict[str, Any],
    key: str,
    errors: list[str],
    *,
    prefix: str = "",
) -> str:
    value = str(data.get(key) or "")
    label = f"{prefix}{key}"
    if not value:
        errors.append(f"{label} is required")
        return ""
    try:
        return safe.clean_text(value, label)
    except ValueError as exc:
        errors.append(f"{label} is invalid: {exc}")
        return value


def _validate_asset_hash(
    relative_or_absolute: str,
    expected_sha256: str,
    assets_dir: Path,
    errors: list[str],
    label: str,
) -> Path | None:
    if not relative_or_absolute or not expected_sha256:
        return None
    if not _is_hex_sha256(expected_sha256):
        errors.append(f"{label} sha256 must be a lowercase 64-character SHA-256 digest")
        return None
    asset_path = _resolve_evidence_asset(relative_or_absolute, assets_dir, errors, label)
    if asset_path is None:
        return None
    if not asset_path.is_file():
        errors.append(f"{label} file is missing: {asset_path}")
        return None
    actual = _sha256_file(asset_path)
    if actual != expected_sha256:
        errors.append(f"{label} SHA-256 mismatch: expected {expected_sha256}, got {actual}")
        return None
    return asset_path


def _resolve_evidence_asset(
    relative_or_absolute: str,
    assets_dir: Path,
    errors: list[str],
    label: str,
) -> Path | None:
    root = assets_dir.resolve()
    raw = Path(relative_or_absolute)
    candidate = raw if raw.is_absolute() else root / raw
    resolved = candidate.resolve()
    try:
        resolved.relative_to(root)
    except ValueError:
        errors.append(f"{label} must stay inside assets_dir: {relative_or_absolute}")
        return None
    return resolved


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _is_hex_sha256(value: str) -> bool:
    return re.fullmatch(r"[0-9a-f]{64}", value) is not None


def _action(value: str) -> str:
    text = safe.option_value(value, "mobapt action").lower()
    if text not in {"search", "install", "update"}:
        raise ValueError("mobapt action must be one of: search, install, update")
    return text


def _select_manager(
    managers: tuple[MobAptPackageManager, ...],
    requested: str | None,
) -> MobAptPackageManager:
    if requested:
        key = safe.option_value(requested, "package manager").lower()
        for manager in managers:
            if manager.key == key:
                return manager
        allowed = ", ".join(manager.key for manager in managers)
        raise ValueError(f"unsupported package manager for this platform: {key}; expected one of: {allowed}")
    for manager in managers:
        if manager.available:
            return manager
    if not managers:
        raise ValueError("no package manager definitions are available for this platform")
    return managers[0]


def _package_command(manager: MobAptPackageManager, action: str, package: str) -> list[str]:
    executable = manager.executable
    if manager.key == "winget":
        if action == "search":
            return [executable, "search", package]
        if action == "install":
            return [executable, "install", "--exact", "--id", package]
        return [executable, "upgrade", "--all"]
    if manager.key == "choco":
        if action == "search":
            return [executable, "search", package]
        if action == "install":
            return [executable, "install", package, "-y"]
        return [executable, "upgrade", "all", "-y"]
    if manager.key == "scoop":
        if action == "search":
            return [executable, "search", package]
        if action == "install":
            return [executable, "install", package]
        return [executable, "update", "*"]
    if manager.key == "brew":
        if action == "search":
            return [executable, "search", package]
        if action == "install":
            return [executable, "install", package]
        return [executable, "update"]
    if manager.key == "port":
        if action == "search":
            return [executable, "search", package]
        if action == "install":
            return [executable, "install", package]
        return [executable, "selfupdate"]
    if manager.key == "apt":
        if action == "search":
            return [executable, "search", package]
        if action == "install":
            return [executable, "install", package]
        return [executable, "update"]
    if manager.key in {"dnf", "yum"}:
        if action == "search":
            return [executable, "search", package]
        if action == "install":
            return [executable, "install", package]
        return [executable, "check-update"]
    if manager.key == "pacman":
        if action == "search":
            return [executable, "-Ss", package]
        if action == "install":
            return [executable, "-S", package]
        return [executable, "-Sy"]
    if manager.key == "zypper":
        if action == "search":
            return [executable, "search", package]
        if action == "install":
            return [executable, "install", package]
        return [executable, "refresh"]
    if manager.key == "apk":
        if action == "search":
            return [executable, "search", package]
        if action == "install":
            return [executable, "add", package]
        return [executable, "update"]
    if manager.key == "pkg":
        if action == "search":
            return [executable, "search", package]
        if action == "install":
            return [executable, "install", package]
        return [executable, "update"]
    if manager.key == "pkg_add":
        if action == "search":
            return [executable, "-Q", package]
        if action == "install":
            return [executable, package]
        return [executable, "-u"]
    raise ValueError(f"unsupported package manager: {manager.key}")


def _manager_definitions(system: str) -> tuple[tuple[str, str, str, tuple[str, ...]], ...]:
    common_note = (
        "External package manager command; installs may require an elevated or administrator shell.",
    )
    if system == "windows":
        return (
            ("winget", "Windows Package Manager", "winget", common_note),
            ("scoop", "Scoop", "scoop", common_note),
            ("choco", "Chocolatey", "choco", common_note),
        )
    if system == "darwin":
        return (
            ("brew", "Homebrew", "brew", common_note),
            ("port", "MacPorts", "port", common_note),
        )
    if system in {"linux", "linux2"}:
        return (
            ("apt", "APT", "apt", common_note),
            ("dnf", "DNF", "dnf", common_note),
            ("yum", "YUM", "yum", common_note),
            ("pacman", "Pacman", "pacman", common_note),
            ("zypper", "Zypper", "zypper", common_note),
            ("apk", "Alpine APK", "apk", common_note),
            ("pkg", "pkg", "pkg", common_note),
        )
    return (
        ("pkg", "pkg", "pkg", common_note),
        ("pkg_add", "pkg_add", "pkg_add", common_note),
    )

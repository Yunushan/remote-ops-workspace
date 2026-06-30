from __future__ import annotations

import hashlib
import importlib.util
import ipaddress
import json
import os
import platform
import re
import shutil
import signal
import subprocess
import sys
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import command_safety as safe
from .file_safety import write_json_atomic
from .paths import ensure_data_dir

WhichResolver = Callable[[str], str | None]
PidProbe = Callable[[int], bool]
ProcessTerminator = Callable[[int], None]
SERVER_RUNTIME_DIR_ENV = "ROW_SERVER_RUNTIME_DIR"
SERVER_RUNTIME_BUNDLE_SCHEMA = "row.moba-servers.runtime-bundle.v1"
SERVER_RELEASE_EVIDENCE_SCHEMA = "row.moba-servers.release-evidence.v1"
SERVER_POLICY_SCHEMA = "row.moba-servers.policy.v1"
SERVER_GUI_CONFIG_SCHEMA = "row.moba-servers.gui-config-surface.v1"

SERVER_DEFAULT_PORTS: dict[str, int] = {
    "http": 8080,
    "ftp": 2121,
    "tftp": 6969,
    "ssh": 2222,
    "sftp": 2222,
    "telnet": 2323,
    "vnc": 5901,
    "nfs": 2049,
}

FILE_ROOT_SERVICES = {"http", "ftp", "tftp"}
AUTH_CAPABLE_SERVICES = {"ftp", "ssh", "sftp", "telnet", "vnc"}


@dataclass(slots=True)
class MobaEmbeddedServerRuntime:
    key: str
    label: str
    service: str
    executable: str
    available: bool
    bundled: bool
    builtin: bool
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "service": self.service,
            "executable": self.executable,
            "available": self.available,
            "bundled": self.bundled,
            "builtin": self.builtin,
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobaEmbeddedServerServiceStatus:
    key: str
    label: str
    default_port: int
    available: bool
    startable: bool
    selected_runtime: str
    runtimes: tuple[MobaEmbeddedServerRuntime, ...]
    lifecycle: MobaEmbeddedServerLifecycleRecord | None
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "default_port": self.default_port,
            "available": self.available,
            "startable": self.startable,
            "selected_runtime": self.selected_runtime,
            "runtimes": [runtime.to_dict() for runtime in self.runtimes],
            "lifecycle": self.lifecycle.to_dict() if self.lifecycle else None,
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobaEmbeddedServerSuiteStatus:
    system: str
    services: tuple[MobaEmbeddedServerServiceStatus, ...]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "system": self.system,
            "services": [service.to_dict() for service in self.services],
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobaEmbeddedServerRuntimeStatus:
    system: str
    roots: tuple[str, ...]
    packaged_available: bool
    service_coverage: dict[str, bool]
    runtimes: tuple[MobaEmbeddedServerRuntime, ...]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "system": self.system,
            "roots": list(self.roots),
            "packaged_available": self.packaged_available,
            "service_coverage": self.service_coverage,
            "runtimes": [runtime.to_dict() for runtime in self.runtimes],
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobaEmbeddedServerRuntimeBundlePlan:
    schema: str
    out_dir: str
    system: str
    release_target: str
    service: str
    runtime_key: str
    runtime_label: str
    source_path: str
    executable_name: str
    target_executable: str
    manifest_path: str
    allow_placeholder: bool
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "out_dir": self.out_dir,
            "system": self.system,
            "release_target": self.release_target,
            "service": self.service,
            "runtime_key": self.runtime_key,
            "runtime_label": self.runtime_label,
            "source_path": self.source_path,
            "executable_name": self.executable_name,
            "target_executable": self.target_executable,
            "manifest_path": self.manifest_path,
            "allow_placeholder": self.allow_placeholder,
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobaEmbeddedServerRuntimeBundleResult:
    plan: MobaEmbeddedServerRuntimeBundlePlan
    root: str
    executable_path: str
    manifest_path: str
    runtime_sha256: str
    files: tuple[str, ...]
    placeholder: bool
    runtime_status: MobaEmbeddedServerRuntimeStatus
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan": self.plan.to_dict(),
            "root": self.root,
            "executable_path": self.executable_path,
            "manifest_path": self.manifest_path,
            "runtime_sha256": self.runtime_sha256,
            "files": list(self.files),
            "placeholder": self.placeholder,
            "runtime_status": self.runtime_status.to_dict(),
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobaEmbeddedServerConfigPlan:
    schema: str
    service: str
    host: str
    port: int
    root: str
    hardening_profile: str
    auth_required: bool
    tls_required: bool
    public_bind_allowed: bool
    settings: dict[str, Any]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "service": self.service,
            "host": self.host,
            "port": self.port,
            "root": self.root,
            "hardening_profile": self.hardening_profile,
            "auth_required": self.auth_required,
            "tls_required": self.tls_required,
            "public_bind_allowed": self.public_bind_allowed,
            "settings": self.settings,
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobaEmbeddedServerGuiConfigRow:
    service: str
    label: str
    status: str
    default_port: int
    selected_runtime: str
    runtime_available: bool
    packaged_runtime: bool
    lifecycle_state: str
    root_required: bool
    hardening_profile: str
    auth_required: bool
    tls_required: bool
    config_action: str
    start_action: str
    stop_action: str
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "service": self.service,
            "label": self.label,
            "status": self.status,
            "default_port": self.default_port,
            "selected_runtime": self.selected_runtime,
            "runtime_available": self.runtime_available,
            "packaged_runtime": self.packaged_runtime,
            "lifecycle_state": self.lifecycle_state,
            "root_required": self.root_required,
            "hardening_profile": self.hardening_profile,
            "auth_required": self.auth_required,
            "tls_required": self.tls_required,
            "config_action": self.config_action,
            "start_action": self.start_action,
            "stop_action": self.stop_action,
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobaEmbeddedServerGuiConfigSurface:
    schema: str
    system: str
    title: str
    selected_service: str
    selected_config: MobaEmbeddedServerConfigPlan
    rows: tuple[MobaEmbeddedServerGuiConfigRow, ...]
    runtime_roots: tuple[str, ...]
    packaged_available: bool
    packaged_service_count: int
    gui_controls: tuple[str, ...]
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": self.schema,
            "system": self.system,
            "title": self.title,
            "selected_service": self.selected_service,
            "selected_config": self.selected_config.to_dict(),
            "rows": [row.to_dict() for row in self.rows],
            "runtime_roots": list(self.runtime_roots),
            "packaged_available": self.packaged_available,
            "packaged_service_count": self.packaged_service_count,
            "gui_controls": list(self.gui_controls),
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobaEmbeddedServerPlan:
    service: str
    label: str
    host: str
    port: int
    root: str
    command: list[str]
    runtime: MobaEmbeddedServerRuntime
    environment: dict[str, str]
    public_bind: bool
    notes: list[str]

    def printable(self) -> str:
        return " ".join(safe.argv_list(self.command, "embedded server command"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "service": self.service,
            "label": self.label,
            "host": self.host,
            "port": self.port,
            "root": self.root,
            "command": self.command,
            "runtime": self.runtime.to_dict(),
            "environment": self.environment,
            "public_bind": self.public_bind,
            "notes": self.notes,
        }


@dataclass(slots=True)
class MobaEmbeddedServerReleaseEvidenceValidation:
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
class MobaEmbeddedServerLifecycleRecord:
    service: str
    host: str
    port: int
    runtime_key: str
    command: list[str]
    state: str
    pid: int | None = None
    started_at: str = ""
    stopped_at: str = ""
    dry_run: bool = False
    state_path: str = ""
    running: bool = False

    @classmethod
    def from_dict(
        cls,
        data: dict[str, Any],
        *,
        state_path: Path | None = None,
        running: bool | None = None,
    ) -> MobaEmbeddedServerLifecycleRecord:
        pid_value = data.get("pid")
        pid = int(pid_value) if pid_value not in (None, "") else None
        return cls(
            service=_service_key(str(data.get("service") or "http")),
            host=safe.host(str(data.get("host") or "127.0.0.1"), "server bind host"),
            port=safe.port(int(data.get("port") or SERVER_DEFAULT_PORTS["http"]), "server port"),
            runtime_key=safe.option_value(str(data.get("runtime_key") or "unknown"), "server runtime key"),
            command=safe.argv_list([str(item) for item in data.get("command", [])], "embedded server command"),
            state=safe.option_value(str(data.get("state") or "unknown"), "embedded server state"),
            pid=pid,
            started_at=safe.clean_text(str(data.get("started_at") or ""), "started_at", allow_empty=True),
            stopped_at=safe.clean_text(str(data.get("stopped_at") or ""), "stopped_at", allow_empty=True),
            dry_run=bool(data.get("dry_run", False)),
            state_path=str(state_path or data.get("state_path") or ""),
            running=bool(running) if running is not None else bool(data.get("running", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "service": self.service,
            "host": self.host,
            "port": self.port,
            "runtime_key": self.runtime_key,
            "command": self.command,
            "state": self.state,
            "pid": self.pid,
            "started_at": self.started_at,
            "stopped_at": self.stopped_at,
            "dry_run": self.dry_run,
            "state_path": self.state_path,
            "running": self.running,
        }


def build_moba_server_suite_status(
    *,
    system: str | None = None,
    which: WhichResolver = shutil.which,
    packaged_roots: Iterable[Path] | None = None,
    state_dir: Path | None = None,
    pid_probe: PidProbe | None = None,
) -> MobaEmbeddedServerSuiteStatus:
    system_key = safe.option_value(system or platform.system(), "system").lower()
    services = tuple(
        _service_status(
            service,
            system=system_key,
            which=which,
            packaged_roots=packaged_roots,
            state_dir=state_dir,
            pid_probe=pid_probe,
        )
        for service in SERVER_DEFAULT_PORTS
    )
    notes = [
        "MobaXterm-style embedded server suite is represented by a built-in HTTP runtime and host daemon adapters.",
        "Full proprietary parity still needs bundled, release-tested daemon binaries and per-service hardening.",
    ]
    return MobaEmbeddedServerSuiteStatus(system=system_key, services=services, notes=notes)


def discover_moba_server_runtimes(
    service: str,
    *,
    system: str | None = None,
    which: WhichResolver = shutil.which,
    packaged_roots: Iterable[Path] | None = None,
) -> tuple[MobaEmbeddedServerRuntime, ...]:
    service_key = _service_key(service)
    system_key = safe.option_value(system or platform.system(), "system").lower()
    packaged = discover_packaged_moba_server_runtimes(service_key, system=system_key, roots=packaged_roots)
    runtimes: list[MobaEmbeddedServerRuntime] = []
    for key, label, executable, bundled, builtin, notes in _runtime_definitions(service_key, system_key):
        if key == "pyftpdlib" and importlib.util.find_spec("pyftpdlib") is not None:
            resolved = sys.executable
            available = True
        elif builtin and executable == "python":
            resolved = sys.executable
            available = bool(sys.executable)
        else:
            resolved = which(executable)
            available = resolved is not None
        runtimes.append(
            MobaEmbeddedServerRuntime(
                key=key,
                label=label,
                service=service_key,
                executable=resolved or executable,
                available=available,
                bundled=bundled,
                builtin=builtin,
                notes=list(notes),
            )
        )
    return (*packaged, *tuple(runtimes))


def build_moba_server_runtime_status(
    *,
    system: str | None = None,
    roots: Iterable[Path] | None = None,
) -> MobaEmbeddedServerRuntimeStatus:
    system_key = safe.option_value(system or platform.system(), "system").lower()
    resolved_roots = moba_server_runtime_roots(roots)
    runtimes = tuple(
        runtime
        for service in SERVER_DEFAULT_PORTS
        for runtime in discover_packaged_moba_server_runtimes(service, system=system_key, roots=resolved_roots)
    )
    coverage = {service: any(runtime.service == service and runtime.available for runtime in runtimes) for service in SERVER_DEFAULT_PORTS}
    notes = [
        f"Scanned {len(resolved_roots)} embedded server runtime root(s).",
        f"Set {SERVER_RUNTIME_DIR_ENV} to a release-owned daemon runtime directory to prefer packaged server binaries.",
    ]
    if all(coverage.values()):
        notes.append("Packaged daemon runtime coverage is present for every embedded server service.")
    elif any(coverage.values()):
        missing = ", ".join(service for service, available in coverage.items() if not available)
        notes.append(f"Packaged daemon runtime coverage is partial; missing: {missing}.")
    else:
        notes.append("No packaged daemon runtimes were found; ROW will fall back to built-in/host adapters.")
    return MobaEmbeddedServerRuntimeStatus(
        system=system_key,
        roots=tuple(str(root) for root in resolved_roots),
        packaged_available=any(coverage.values()),
        service_coverage=coverage,
        runtimes=runtimes,
        notes=notes,
    )


def build_moba_server_runtime_bundle_plan(
    out_dir: Path,
    service: str,
    *,
    runtime_key: str | None = None,
    source_path: Path | None = None,
    system: str | None = None,
    release_target: str = "local-bundle",
    executable_name: str | None = None,
    allow_placeholder: bool = False,
) -> MobaEmbeddedServerRuntimeBundlePlan:
    service_key = _service_key(service)
    system_key = safe.option_value(system or platform.system(), "system").lower()
    key, label, default_executable, _bundled, _builtin, _notes = _runtime_definition_by_key(
        service_key,
        system_key,
        runtime_key,
    )
    root = Path(out_dir).expanduser()
    packaged_name = executable_name or _packaged_daemon_executable_name(system_key, default_executable)
    target = root / system_key / service_key / "bin" / _safe_executable_name(packaged_name)
    manifest_path = root / "servers-runtime.json"
    notes = [
        "Bundle plan writes a release-owned embedded-server daemon layout discoverable through ROW_SERVER_RUNTIME_DIR.",
        "Production parity should use real daemon binaries supplied by the release build; placeholders are only for local contract rehearsal.",
    ]
    if allow_placeholder:
        notes.append("Placeholder daemon generation is enabled; replace it with a real daemon binary before claiming full parity.")
    return MobaEmbeddedServerRuntimeBundlePlan(
        schema=SERVER_RUNTIME_BUNDLE_SCHEMA,
        out_dir=str(root),
        system=system_key,
        release_target=safe.clean_text(release_target, "release target"),
        service=service_key,
        runtime_key=key,
        runtime_label=label,
        source_path=str(source_path.expanduser()) if source_path is not None else "",
        executable_name=packaged_name,
        target_executable=str(target),
        manifest_path=str(manifest_path),
        allow_placeholder=bool(allow_placeholder),
        notes=notes,
    )


def write_moba_server_runtime_bundle(
    plan: MobaEmbeddedServerRuntimeBundlePlan,
) -> MobaEmbeddedServerRuntimeBundleResult:
    if plan.schema != SERVER_RUNTIME_BUNDLE_SCHEMA:
        raise ValueError(f"embedded server runtime bundle plan schema must be {SERVER_RUNTIME_BUNDLE_SCHEMA}")
    root = Path(plan.out_dir)
    target = Path(plan.target_executable)
    target.parent.mkdir(parents=True, exist_ok=True)
    placeholder = False
    if plan.source_path:
        source = Path(plan.source_path).expanduser()
        if not source.is_file():
            raise ValueError(f"embedded server daemon source is missing: {source}")
        shutil.copy2(source, target)
    elif plan.allow_placeholder:
        placeholder = True
        target.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env sh",
                    f"echo 'ROW packaged embedded server placeholder: {plan.service}/{plan.runtime_key}'",
                    "",
                ]
            ),
            encoding="utf-8",
        )
    else:
        raise ValueError("embedded server daemon source is required unless --allow-placeholder is explicitly set")
    _chmod_executable(target)
    runtime_sha256 = _sha256_file(target)
    manifest_path = Path(plan.manifest_path)
    service_record = {
        "service": plan.service,
        "runtime": {
            "key": plan.runtime_key,
            "label": plan.runtime_label,
            "source": "packaged",
            "bundled": True,
            "executable": _relative_to_root(target, root),
            "sha256": runtime_sha256,
            "placeholder": placeholder,
        },
    }
    manifest = _merged_server_runtime_manifest(
        manifest_path,
        release_target=plan.release_target,
        system=plan.system,
        service_record=service_record,
    )
    write_json_atomic(manifest_path, manifest, private=False)
    runtime_status = build_moba_server_runtime_status(system=plan.system, roots=[root])
    notes = list(plan.notes)
    if placeholder:
        notes.append("Placeholder daemon requires replacement before full MobaXterm embedded server parity.")
    if not runtime_status.service_coverage.get(plan.service, False):
        notes.append("Packaged daemon was written but was not discovered by runtime-status; check service/runtime layout.")
    return MobaEmbeddedServerRuntimeBundleResult(
        plan=plan,
        root=str(root),
        executable_path=str(target),
        manifest_path=str(manifest_path),
        runtime_sha256=runtime_sha256,
        files=(_relative_to_root(target, root), _relative_to_root(manifest_path, root)),
        placeholder=placeholder,
        runtime_status=runtime_status,
        notes=notes,
    )


def discover_packaged_moba_server_runtimes(
    service: str,
    *,
    system: str | None = None,
    roots: Iterable[Path] | None = None,
) -> tuple[MobaEmbeddedServerRuntime, ...]:
    service_key = _service_key(service)
    system_key = safe.option_value(system or platform.system(), "system").lower()
    found: list[MobaEmbeddedServerRuntime] = []
    for root in moba_server_runtime_roots(roots):
        for key, label, executable, _bundled, builtin, notes in _runtime_definitions(service_key, system_key):
            for candidate_path in _packaged_daemon_paths(root, system_key, service_key, key, executable):
                if candidate_path.is_file():
                    found.append(
                        MobaEmbeddedServerRuntime(
                            key=key,
                            label=label,
                            service=service_key,
                            executable=str(candidate_path),
                            available=True,
                            bundled=True,
                            builtin=builtin,
                            notes=[
                                f"Release-packaged daemon runtime from {root}.",
                                *notes,
                            ],
                        )
                    )
                    break
    return tuple(found)


def moba_server_runtime_roots(roots: Iterable[Path] | None = None) -> tuple[Path, ...]:
    raw_roots: list[Path] = []
    if roots is not None:
        raw_roots.extend(Path(root) for root in roots)
    env_value = os.environ.get(SERVER_RUNTIME_DIR_ENV, "")
    if env_value:
        raw_roots.extend(Path(part) for part in env_value.split(os.pathsep) if part)
    executable_dir = Path(sys.executable).resolve().parent
    raw_roots.extend(
        [
            executable_dir / "servers",
            executable_dir / "runtimes" / "servers",
            Path(__file__).resolve().parents[2] / "vendor" / "servers",
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


def build_moba_server_plan(
    service: str,
    *,
    host: str = "127.0.0.1",
    port: int | None = None,
    root: Path | str | None = None,
    allow_public_bind: bool = False,
    system: str | None = None,
    which: WhichResolver = shutil.which,
    packaged_roots: Iterable[Path] | None = None,
) -> MobaEmbeddedServerPlan:
    service_key = _service_key(service)
    system_key = safe.option_value(system or platform.system(), "system").lower()
    host = validate_server_bind(host, allow_public_bind=allow_public_bind)
    resolved_port = safe.port(port or SERVER_DEFAULT_PORTS[service_key], "server port")
    resolved_root = _resolve_root(service_key, root)
    runtimes = discover_moba_server_runtimes(
        service_key,
        system=system_key,
        which=which,
        packaged_roots=packaged_roots,
    )
    runtime = _select_runtime(runtimes)
    command = _runtime_command(runtime, host, resolved_port, resolved_root)
    notes = _plan_notes(service_key, runtime, host, resolved_root)
    return MobaEmbeddedServerPlan(
        service=service_key,
        label=_service_label(service_key),
        host=host,
        port=resolved_port,
        root=str(resolved_root) if resolved_root else "",
        command=command,
        runtime=runtime,
        environment={"ROW_SERVER_SERVICE": service_key},
        public_bind=not _is_loopback_host(host.lower()),
        notes=notes,
    )


def build_moba_server_config_plan(
    service: str,
    *,
    host: str = "127.0.0.1",
    port: int | None = None,
    root: Path | str | None = None,
    hardening_profile: str = "loopback-private",
    require_auth: bool | None = None,
    require_tls: bool = False,
    allow_public_bind: bool = False,
) -> MobaEmbeddedServerConfigPlan:
    service_key = _service_key(service)
    profile = _hardening_profile(hardening_profile)
    bind_host = validate_server_bind(host, allow_public_bind=allow_public_bind)
    resolved_port = safe.port(port or SERVER_DEFAULT_PORTS[service_key], "server port")
    resolved_root = _resolve_root(service_key, root)
    auth_required = bool(require_auth) if require_auth is not None else service_key in AUTH_CAPABLE_SERVICES
    public_bind = not _is_loopback_host(bind_host.lower())
    settings: dict[str, Any] = {
        "bind_host": bind_host,
        "port": resolved_port,
        "service": service_key,
        "root": str(resolved_root) if resolved_root else "",
        "auth": {
            "required": auth_required,
            "source": "external-secret-or-system-account" if auth_required else "disabled",
            "passwords_in_config": False,
        },
        "network": {
            "loopback_default": True,
            "public_bind_allowed": bool(allow_public_bind),
            "public_bind_active": public_bind,
        },
        "transport": {"tls_required": bool(require_tls)},
        "logging": {"audit_events": True, "redact_secrets": True},
    }
    notes = [
        "MobaXterm-style embedded server configuration plan.",
        "Secrets are referenced through external stores or system accounts; generated config does not contain passwords.",
    ]
    if public_bind:
        notes.append("Public bind is active; use only on trusted networks and pair with authentication.")
    if profile == "strict-private":
        settings["network"]["public_bind_allowed"] = False
        settings["auth"]["required"] = True
        notes.append("Strict-private hardening forces authentication and loopback-only network exposure.")
    return MobaEmbeddedServerConfigPlan(
        schema=SERVER_POLICY_SCHEMA,
        service=service_key,
        host=bind_host,
        port=resolved_port,
        root=str(resolved_root) if resolved_root else "",
        hardening_profile=profile,
        auth_required=bool(settings["auth"]["required"]),
        tls_required=bool(require_tls),
        public_bind_allowed=bool(allow_public_bind),
        settings=settings,
        notes=notes,
    )


def build_moba_server_gui_config_surface(
    *,
    selected_service: str = "http",
    host: str = "127.0.0.1",
    port: int | None = None,
    root: Path | str | None = None,
    hardening_profile: str = "loopback-private",
    require_auth: bool | None = None,
    require_tls: bool = False,
    allow_public_bind: bool = False,
    system: str | None = None,
    which: WhichResolver = shutil.which,
    packaged_roots: Iterable[Path] | None = None,
    state_dir: Path | None = None,
    pid_probe: PidProbe | None = None,
) -> MobaEmbeddedServerGuiConfigSurface:
    service_key = _service_key(selected_service)
    system_key = safe.option_value(system or platform.system(), "system").lower()
    packaged_root_tuple = tuple(packaged_roots) if packaged_roots is not None else None
    suite = build_moba_server_suite_status(
        system=system_key,
        which=which,
        packaged_roots=packaged_root_tuple,
        state_dir=state_dir,
        pid_probe=pid_probe,
    )
    runtime_status = build_moba_server_runtime_status(system=system_key, roots=packaged_root_tuple)
    selected_config = build_moba_server_config_plan(
        service_key,
        host=host,
        port=port,
        root=root,
        hardening_profile=hardening_profile,
        require_auth=require_auth,
        require_tls=require_tls,
        allow_public_bind=allow_public_bind,
    )
    rows = tuple(
        _gui_config_row(
            service,
            hardening_profile=selected_config.hardening_profile,
            require_tls=require_tls,
            root=root,
        )
        for service in suite.services
    )
    notes = [
        "MobaXterm-style embedded server GUI configuration surface.",
        "Rows are backed by the same status, config-plan, start/stop and packaged-runtime contracts used by the CLI.",
        *suite.notes,
        *runtime_status.notes,
    ]
    return MobaEmbeddedServerGuiConfigSurface(
        schema=SERVER_GUI_CONFIG_SCHEMA,
        system=system_key,
        title="Embedded Servers",
        selected_service=service_key,
        selected_config=selected_config,
        rows=rows,
        runtime_roots=runtime_status.roots,
        packaged_available=runtime_status.packaged_available,
        packaged_service_count=sum(1 for available in runtime_status.service_coverage.values() if available),
        gui_controls=("service-table", "configure", "start", "stop", "runtime-status", "evidence-verify"),
        notes=notes,
    )


def validate_moba_server_release_evidence(
    evidence_path: Path,
    *,
    assets_dir: Path | None = None,
) -> MobaEmbeddedServerReleaseEvidenceValidation:
    target_evidence_path = Path(evidence_path)
    root = Path(assets_dir) if assets_dir is not None else target_evidence_path.parent
    errors: list[str] = []
    warnings: list[str] = []
    summary: dict[str, Any] = {
        "schema": "",
        "release_target": "",
        "service_count": 0,
        "client_proof_count": 0,
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
    if schema != SERVER_RELEASE_EVIDENCE_SCHEMA:
        errors.append(f"schema must be {SERVER_RELEASE_EVIDENCE_SCHEMA}")
    summary["release_target"] = _required_text(data, "release_target", errors)

    service_entries = data.get("services")
    if not isinstance(service_entries, list):
        errors.append("services must be a list")
        service_entries = []
    summary["service_count"] = len(service_entries)
    covered_services: set[str] = set()
    client_proofs = 0
    for index, raw_service in enumerate(service_entries):
        label = f"services[{index}]"
        if not isinstance(raw_service, dict):
            errors.append(f"{label} must be an object")
            continue
        service_key = _required_text(raw_service, "service", errors, prefix=f"{label}.")
        if service_key:
            try:
                service_key = _service_key(service_key)
                covered_services.add(service_key)
            except ValueError as exc:
                errors.append(f"{label}.service is invalid: {exc}")
        runtime = _required_mapping(raw_service, "runtime", errors, prefix=f"{label}.")
        runtime_file = _required_text(runtime, "executable", errors, prefix=f"{label}.runtime.")
        runtime_sha256 = _required_text(runtime, "sha256", errors, prefix=f"{label}.runtime.")
        _validate_asset_hash(runtime_file, runtime_sha256, root, errors, f"{label}.runtime.executable")
        if runtime.get("bundled") is not True:
            errors.append(f"{label}.runtime.bundled must be true")
        policy = _required_mapping(raw_service, "policy", errors, prefix=f"{label}.")
        policy_schema = str(policy.get("schema") or "")
        if policy_schema != SERVER_POLICY_SCHEMA:
            errors.append(f"{label}.policy.schema must be {SERVER_POLICY_SCHEMA}")
        if service_key in AUTH_CAPABLE_SERVICES and policy.get("auth_required") is not True:
            errors.append(f"{label}.policy.auth_required must be true for {service_key}")
        if policy.get("public_bind_allowed") is True and policy.get("auth_required") is not True:
            errors.append(f"{label}.policy public binds require authentication")
        client = _required_mapping(raw_service, "client_test", errors, prefix=f"{label}.")
        if client.get("status") != "passed":
            errors.append(f"{label}.client_test.status must be passed")
        _required_text(client, "command", errors, prefix=f"{label}.client_test.")
        evidence_file = _required_text(client, "evidence_file", errors, prefix=f"{label}.client_test.")
        evidence_sha256 = _required_text(client, "evidence_sha256", errors, prefix=f"{label}.client_test.")
        if _validate_asset_hash(evidence_file, evidence_sha256, root, errors, f"{label}.client_test.evidence_file"):
            client_proofs += 1
    summary["client_proof_count"] = client_proofs
    missing_services = sorted(set(SERVER_DEFAULT_PORTS) - covered_services)
    if missing_services:
        errors.append(f"services missing release evidence for: {', '.join(missing_services)}")

    return MobaEmbeddedServerReleaseEvidenceValidation(
        evidence_path=str(target_evidence_path),
        assets_dir=str(root),
        passed=not errors,
        errors=errors,
        warnings=warnings,
        summary=summary,
    )


def start_moba_server(
    plan: MobaEmbeddedServerPlan,
    *,
    dry_run: bool = False,
    state_dir: Path | None = None,
    popen_factory: Callable[..., Any] = subprocess.Popen,
) -> MobaEmbeddedServerLifecycleRecord:
    safe.argv_list(plan.command, "embedded server command")
    target_state_path = moba_server_state_path(plan.service, state_dir=state_dir)
    if dry_run:
        return MobaEmbeddedServerLifecycleRecord(
            service=plan.service,
            host=plan.host,
            port=plan.port,
            runtime_key=plan.runtime.key,
            command=plan.command,
            state="dry-run",
            dry_run=True,
            state_path=str(target_state_path),
        )
    if not plan.runtime.available:
        raise ValueError(f"embedded server runtime is not available: {plan.runtime.label}")
    process = popen_factory(plan.command, env={**os.environ, **plan.environment})
    record = MobaEmbeddedServerLifecycleRecord(
        service=plan.service,
        host=plan.host,
        port=plan.port,
        runtime_key=plan.runtime.key,
        command=plan.command,
        state="started",
        pid=int(process.pid),
        started_at=_now(),
        state_path=str(target_state_path),
        running=True,
    )
    write_json_atomic(target_state_path, record.to_dict(), private=True)
    return record


def stop_moba_server(
    service: str,
    *,
    state_dir: Path | None = None,
    pid_probe: PidProbe | None = None,
    terminator: ProcessTerminator | None = None,
) -> MobaEmbeddedServerLifecycleRecord:
    service_key = _service_key(service)
    target_state_path = moba_server_state_path(service_key, state_dir=state_dir)
    record = load_moba_server_record(service_key, state_dir=state_dir, pid_probe=pid_probe)
    if record is None:
        raise ValueError(f"no managed embedded server state found at {target_state_path}")
    if record.pid and record.running:
        (terminator or _terminate_pid)(record.pid)
    stopped = MobaEmbeddedServerLifecycleRecord(
        service=record.service,
        host=record.host,
        port=record.port,
        runtime_key=record.runtime_key,
        command=record.command,
        state="stopped",
        pid=record.pid,
        started_at=record.started_at,
        stopped_at=_now(),
        state_path=str(target_state_path),
        running=False,
    )
    write_json_atomic(target_state_path, stopped.to_dict(), private=True)
    return stopped


def load_moba_server_record(
    service: str,
    *,
    state_dir: Path | None = None,
    pid_probe: PidProbe | None = None,
) -> MobaEmbeddedServerLifecycleRecord | None:
    service_key = _service_key(service)
    target_state_path = moba_server_state_path(service_key, state_dir=state_dir)
    if not target_state_path.exists():
        return None
    data = json.loads(target_state_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"embedded server state must be a JSON object: {target_state_path}")
    probe = pid_probe or _pid_running
    running = bool(data.get("pid")) and probe(int(data.get("pid")))
    return MobaEmbeddedServerLifecycleRecord.from_dict(data, state_path=target_state_path, running=running)


def moba_server_state_path(service: str, *, state_dir: Path | None = None) -> Path:
    service_key = _service_key(service)
    root = state_dir or (ensure_data_dir() / "servers")
    return root / f"{service_key}-server-state.json"


def validate_server_bind(host: str, *, allow_public_bind: bool = False) -> str:
    normalized = safe.host(host, "server bind host").lower()
    if _is_loopback_host(normalized):
        return host
    if not allow_public_bind:
        raise ValueError(
            "embedded servers refuse non-loopback bind hosts by default; "
            "use --allow-public-bind only for trusted networks"
        )
    return host


def _service_status(
    service: str,
    *,
    system: str,
    which: WhichResolver,
    packaged_roots: Iterable[Path] | None,
    state_dir: Path | None,
    pid_probe: PidProbe | None,
) -> MobaEmbeddedServerServiceStatus:
    runtimes = discover_moba_server_runtimes(
        service,
        system=system,
        which=which,
        packaged_roots=packaged_roots,
    )
    runtime = _select_runtime(runtimes)
    lifecycle = load_moba_server_record(service, state_dir=state_dir, pid_probe=pid_probe)
    notes = list(runtime.notes)
    if not runtime.available:
        notes.append("Install or bundle a compatible daemon before starting this service.")
    return MobaEmbeddedServerServiceStatus(
        key=service,
        label=_service_label(service),
        default_port=SERVER_DEFAULT_PORTS[service],
        available=runtime.available,
        startable=runtime.available,
        selected_runtime=runtime.key,
        runtimes=runtimes,
        lifecycle=lifecycle,
        notes=notes,
    )


def _gui_config_row(
    service: MobaEmbeddedServerServiceStatus,
    *,
    hardening_profile: str,
    require_tls: bool,
    root: Path | str | None,
) -> MobaEmbeddedServerGuiConfigRow:
    runtime = next((item for item in service.runtimes if item.key == service.selected_runtime), service.runtimes[0])
    lifecycle_state = service.lifecycle.state if service.lifecycle is not None else "stopped"
    running = bool(service.lifecycle and service.lifecycle.running)
    status = "running" if running else ("available" if service.available else "missing")
    service_root = _command_root_arg(service.key, root)
    row_config = build_moba_server_config_plan(
        service.key,
        port=service.default_port,
        root=service_root or None,
        hardening_profile=hardening_profile,
        require_tls=require_tls,
    )
    return MobaEmbeddedServerGuiConfigRow(
        service=service.key,
        label=service.label,
        status=status,
        default_port=service.default_port,
        selected_runtime=service.selected_runtime,
        runtime_available=service.available,
        packaged_runtime=runtime.bundled,
        lifecycle_state=lifecycle_state,
        root_required=service.key in FILE_ROOT_SERVICES,
        hardening_profile=row_config.hardening_profile,
        auth_required=row_config.auth_required,
        tls_required=row_config.tls_required,
        config_action=_server_config_action(service.key, service.default_port, service_root, row_config.hardening_profile, require_tls),
        start_action=_server_start_action(service.key, service.default_port, service_root),
        stop_action=f"row servers stop {service.key}",
        notes=list(service.notes),
    )


def _packaged_daemon_paths(
    root: Path,
    system: str,
    service: str,
    runtime_key: str,
    executable: str,
) -> tuple[Path, ...]:
    names = [executable]
    if system == "windows" and not executable.lower().endswith(".exe"):
        names.append(f"{executable}.exe")
    return tuple(
        candidate
        for name in dict.fromkeys(names)
        for candidate in (
            root / service / name,
            root / service / "bin" / name,
            root / runtime_key / name,
            root / runtime_key / "bin" / name,
            root / "bin" / service / name,
            root / "bin" / name,
            root / system / service / name,
            root / system / service / "bin" / name,
        )
    )


def _runtime_definition_by_key(
    service: str,
    system: str,
    runtime_key: str | None,
) -> tuple[str, str, str, bool, bool, tuple[str, ...]]:
    definitions = _runtime_definitions(service, system)
    if runtime_key:
        requested = safe.option_value(runtime_key, "embedded server runtime").lower()
        for definition in definitions:
            if definition[0] == requested:
                return definition
        allowed = ", ".join(definition[0] for definition in definitions)
        raise ValueError(f"unsupported embedded server runtime for {service}: {requested}; expected one of: {allowed}")
    if len(definitions) == 1:
        return definitions[0]
    for definition in definitions:
        if definition[4] is False:
            return definition
    return definitions[0]


def _packaged_daemon_executable_name(system: str, executable: str) -> str:
    name = Path(executable).name
    if system == "windows" and not name.lower().endswith(".exe"):
        return f"{name}.exe"
    return name


def _safe_executable_name(value: str) -> str:
    name = safe.path_arg(value, "embedded server executable name")
    if "/" in name or "\\" in name or not name.strip():
        raise ValueError("embedded server executable name must be a filename, not a path")
    return name


def _merged_server_runtime_manifest(
    manifest_path: Path,
    *,
    release_target: str,
    system: str,
    service_record: dict[str, Any],
) -> dict[str, Any]:
    services: list[dict[str, Any]] = []
    if manifest_path.is_file():
        try:
            existing = json.loads(manifest_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            existing = {}
        if isinstance(existing, dict) and existing.get("schema") == SERVER_RUNTIME_BUNDLE_SCHEMA:
            raw_services = existing.get("services", [])
            if isinstance(raw_services, list):
                services = [item for item in raw_services if isinstance(item, dict)]
    service_key = str(service_record.get("service") or "")
    services = [item for item in services if str(item.get("service") or "") != service_key]
    services.append(service_record)
    return {
        "schema": SERVER_RUNTIME_BUNDLE_SCHEMA,
        "release_target": release_target,
        "system": system,
        "services": sorted(services, key=lambda item: str(item.get("service") or "")),
    }


def _relative_to_root(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _chmod_executable(path: Path) -> None:
    try:
        path.chmod(path.stat().st_mode | 0o111)
    except OSError:
        pass


def _runtime_definitions(
    service: str,
    system: str,
) -> tuple[tuple[str, str, str, bool, bool, tuple[str, ...]], ...]:
    external = ("Host-provided daemon adapter; not yet a bundled ROW runtime.",)
    if service == "http":
        return (
            (
                "python-http",
                "Python HTTP static server",
                "python",
                False,
                True,
                ("Built-in Python http.server adapter with loopback-safe defaults.",),
            ),
        )
    if service == "ftp":
        return (
            ("pyftpdlib", "pyftpdlib FTP server", "pyftpdlib", False, False, external),
            ("ftpd", "System FTP daemon", "ftpd", False, False, external),
        )
    if service == "tftp":
        executable = "tftpd.exe" if system == "windows" else "in.tftpd"
        return (
            ("tftpd", "TFTP daemon", executable, False, False, external),
            ("atftpd", "Advanced TFTP daemon", "atftpd", False, False, external),
        )
    if service == "ssh":
        return (("sshd", "OpenSSH server daemon", "sshd", False, False, external),)
    if service == "sftp":
        return (("sshd-sftp", "OpenSSH SFTP subsystem via sshd", "sshd", False, False, external),)
    if service == "telnet":
        executable = "tlntsvr.exe" if system == "windows" else "telnetd"
        return (("telnetd", "Telnet daemon", executable, False, False, external),)
    if service == "vnc":
        return (
            ("x11vnc", "x11vnc server", "x11vnc", False, False, external),
            ("vncserver", "VNC server", "vncserver", False, False, external),
        )
    if service == "nfs":
        executable = "nfsd.exe" if system == "windows" else "nfsd"
        return (("nfsd", "NFS daemon", executable, False, False, external),)
    raise ValueError(f"unsupported embedded server service: {service}")


def _runtime_command(
    runtime: MobaEmbeddedServerRuntime,
    host: str,
    port: int,
    root: Path | None,
) -> list[str]:
    executable = safe.path_arg(runtime.executable, "embedded server executable")
    if runtime.key == "python-http":
        if root is None:
            raise ValueError("http server requires a root directory")
        return [executable, "-m", "http.server", str(port), "--bind", host, "--directory", str(root)]
    if runtime.key == "pyftpdlib":
        if root is None:
            raise ValueError("ftp server requires a root directory")
        if Path(executable).name.lower().startswith("python"):
            return [executable, "-m", "pyftpdlib", "-i", host, "-p", str(port), "-d", str(root)]
        return [executable, "-i", host, "-p", str(port), "-d", str(root)]
    if runtime.key == "ftpd":
        if root is None:
            raise ValueError("ftp server requires a root directory")
        return [executable, "-D", "-P", str(port), "-a", host, str(root)]
    if runtime.key in {"tftpd", "atftpd"}:
        if root is None:
            raise ValueError("tftp server requires a root directory")
        return [executable, "--foreground", "--address", f"{host}:{port}", str(root)]
    if runtime.key == "sshd":
        return [executable, "-D", "-p", str(port), "-o", f"ListenAddress={host}"]
    if runtime.key == "sshd-sftp":
        return [executable, "-D", "-p", str(port), "-o", f"ListenAddress={host}", "-o", "Subsystem=sftp internal-sftp"]
    if runtime.key == "telnetd":
        return [executable, "-debug", str(port)]
    if runtime.key == "x11vnc":
        return [executable, "-listen", host, "-rfbport", str(port), "-forever"]
    if runtime.key == "vncserver":
        return [executable, "-rfbport", str(port), "-localhost", "yes" if _is_loopback_host(host.lower()) else "no"]
    if runtime.key == "nfsd":
        return [executable, "-F"]
    raise ValueError(f"unsupported embedded server runtime: {runtime.key}")


def _hardening_profile(value: str) -> str:
    profile = safe.option_value(value, "embedded server hardening profile").lower()
    if profile not in {"loopback-private", "strict-private", "trusted-lan"}:
        raise ValueError("embedded server hardening profile must be one of: loopback-private, strict-private, trusted-lan")
    return profile


def _required_mapping(
    data: dict[str, Any],
    key: str,
    errors: list[str],
    *,
    prefix: str = "",
) -> dict[str, Any]:
    raw = data.get(key)
    label = f"{prefix}{key}"
    if not isinstance(raw, dict):
        errors.append(f"{label} must be an object")
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


def _plan_notes(
    service: str,
    runtime: MobaEmbeddedServerRuntime,
    host: str,
    root: Path | None,
) -> list[str]:
    notes = [
        f"MobaXterm-style embedded {service} server workflow.",
        "Server binds to loopback by default; public binds require --allow-public-bind.",
        *runtime.notes,
    ]
    if root is not None:
        notes.append(f"Serving root: {root}")
    if not runtime.available:
        notes.append(f"Selected runtime is not available on PATH: {runtime.label}.")
    if not _is_loopback_host(host.lower()):
        notes.append("Public bind requested; use only on a trusted network.")
    return notes


def _select_runtime(runtimes: tuple[MobaEmbeddedServerRuntime, ...]) -> MobaEmbeddedServerRuntime:
    for runtime in runtimes:
        if runtime.available:
            return runtime
    if not runtimes:
        raise ValueError("no embedded server runtimes are defined")
    return runtimes[0]


def _command_root_arg(service: str, root: Path | str | None) -> str:
    if service not in FILE_ROOT_SERVICES:
        return ""
    return str(Path(root).resolve() if root is not None else Path.cwd().resolve())


def _server_config_action(
    service: str,
    port: int,
    root: str,
    hardening_profile: str,
    require_tls: bool,
) -> str:
    command = [
        "row",
        "servers",
        "config-plan",
        service,
        "--port",
        str(port),
        "--hardening-profile",
        hardening_profile,
    ]
    if root:
        command.extend(["--root", root])
    if require_tls:
        command.append("--require-tls")
    return " ".join(command)


def _server_start_action(service: str, port: int, root: str) -> str:
    command = ["row", "servers", "start", service, "--port", str(port)]
    if root:
        command.extend(["--root", root])
    return " ".join(command)


def _resolve_root(service: str, root: Path | str | None) -> Path | None:
    if service not in FILE_ROOT_SERVICES:
        return None
    candidate = Path(root) if root is not None else Path.cwd()
    resolved = candidate.resolve()
    if not resolved.exists() or not resolved.is_dir():
        raise ValueError(f"{service} server root does not exist or is not a directory: {resolved}")
    return resolved


def _service_key(value: str) -> str:
    key = safe.option_value(value, "embedded server service").lower()
    if key not in SERVER_DEFAULT_PORTS:
        allowed = ", ".join(SERVER_DEFAULT_PORTS)
        raise ValueError(f"unsupported embedded server service: {key}; expected one of: {allowed}")
    return key


def _service_label(service: str) -> str:
    return {
        "http": "HTTP static file server",
        "ftp": "FTP file server",
        "tftp": "TFTP file server",
        "ssh": "SSH server",
        "sftp": "SFTP server",
        "telnet": "Telnet server",
        "vnc": "VNC server",
        "nfs": "NFS server",
    }[service]


def _is_loopback_host(host: str) -> bool:
    if host in {"localhost", "ip6-localhost"}:
        return True
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return False


def _pid_running(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _terminate_pid(pid: int) -> None:
    if platform.system().lower() == "windows":
        subprocess.run(["taskkill", "/PID", str(pid), "/T"], check=False, capture_output=True, text=True)
        return
    os.kill(pid, signal.SIGTERM)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()

from __future__ import annotations

import os
import platform
import re
import shutil
import signal
import socket
import subprocess
import hashlib
import json
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
DisplayProbe = Callable[[str], bool]
PidProbe = Callable[[int], bool]
ProcessTerminator = Callable[[int], None]
ProbeRunner = Callable[..., Any]
XSERVER_RELEASE_EVIDENCE_SCHEMA = "row.moba-xserver.release-evidence.v1"
XSERVER_RUNTIME_BUNDLE_SCHEMA = "row.moba-xserver.runtime-bundle.v1"
XSERVER_RUNTIME_DIR_ENV = "ROW_XSERVER_RUNTIME_DIR"


@dataclass(slots=True)
class XServerPlan:
    command: list[str]
    notes: list[str]

    def printable(self) -> str:
        return " ".join(safe.argv_list(self.command, "x server command"))


@dataclass(slots=True)
class XServerRuntimeCandidate:
    key: str
    label: str
    executable: str
    available: bool
    source: str
    bundled: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "executable": self.executable,
            "available": self.available,
            "source": self.source,
            "bundled": self.bundled,
        }


@dataclass(slots=True)
class XServerExtension:
    key: str
    label: str
    required_for: str
    status: str

    def to_dict(self) -> dict[str, str]:
        return {
            "key": self.key,
            "label": self.label,
            "required_for": self.required_for,
            "status": self.status,
        }


@dataclass(slots=True)
class ManagedXServerPlan:
    display: str
    command: list[str]
    runtime: XServerRuntimeCandidate
    extensions: tuple[XServerExtension, ...]
    environment: dict[str, str]
    display_in_use: bool
    notes: list[str]
    candidates: tuple[XServerRuntimeCandidate, ...]

    def printable(self) -> str:
        return " ".join(safe.argv_list(self.command, "managed x server command"))

    def to_dict(self) -> dict[str, Any]:
        return {
            "display": self.display,
            "command": self.command,
            "runtime": self.runtime.to_dict(),
            "extensions": [extension.to_dict() for extension in self.extensions],
            "environment": self.environment,
            "display_in_use": self.display_in_use,
            "notes": self.notes,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
        }


@dataclass(slots=True)
class MobaXServerStatus:
    display: str
    available: bool
    selected_runtime: str
    display_in_use: bool
    extensions: tuple[XServerExtension, ...]
    candidates: tuple[XServerRuntimeCandidate, ...]
    plan: ManagedXServerPlan | None
    lifecycle: XServerLifecycleRecord | None
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "display": self.display,
            "available": self.available,
            "selected_runtime": self.selected_runtime,
            "display_in_use": self.display_in_use,
            "extensions": [extension.to_dict() for extension in self.extensions],
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "plan": self.plan.to_dict() if self.plan else None,
            "lifecycle": self.lifecycle.to_dict() if self.lifecycle else None,
            "notes": self.notes,
        }


@dataclass(slots=True)
class XServerPackageStatus:
    system: str
    roots: tuple[str, ...]
    packaged_available: bool
    candidates: tuple[XServerRuntimeCandidate, ...]
    selected_runtime: str
    notes: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "system": self.system,
            "roots": list(self.roots),
            "packaged_available": self.packaged_available,
            "candidates": [candidate.to_dict() for candidate in self.candidates],
            "selected_runtime": self.selected_runtime,
            "notes": self.notes,
        }


@dataclass(slots=True)
class XServerRuntimeBundlePlan:
    schema: str
    out_dir: str
    system: str
    runtime_key: str
    runtime_label: str
    release_target: str
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
            "runtime_key": self.runtime_key,
            "runtime_label": self.runtime_label,
            "release_target": self.release_target,
            "source_path": self.source_path,
            "executable_name": self.executable_name,
            "target_executable": self.target_executable,
            "manifest_path": self.manifest_path,
            "allow_placeholder": self.allow_placeholder,
            "notes": self.notes,
        }


@dataclass(slots=True)
class XServerRuntimeBundleResult:
    plan: XServerRuntimeBundlePlan
    root: str
    executable_path: str
    manifest_path: str
    runtime_sha256: str
    files: tuple[str, ...]
    placeholder: bool
    package_status: XServerPackageStatus
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
            "package_status": self.package_status.to_dict(),
            "notes": self.notes,
        }


@dataclass(slots=True)
class XServerLifecycleRecord:
    display: str
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
    def from_dict(cls, data: dict[str, Any], *, state_path: Path | None = None, running: bool | None = None) -> XServerLifecycleRecord:
        pid_value = data.get("pid")
        pid = int(pid_value) if pid_value not in (None, "") else None
        return cls(
            display=safe.display(str(data.get("display") or ":0")),
            runtime_key=safe.option_value(str(data.get("runtime_key") or "unknown"), "runtime key"),
            command=safe.argv_list([str(item) for item in data.get("command", [])], "x server lifecycle command"),
            state=safe.option_value(str(data.get("state") or "unknown"), "x server lifecycle state"),
            pid=pid,
            started_at=safe.clean_text(str(data.get("started_at") or ""), "started_at", allow_empty=True),
            stopped_at=safe.clean_text(str(data.get("stopped_at") or ""), "stopped_at", allow_empty=True),
            dry_run=bool(data.get("dry_run", False)),
            state_path=str(state_path or data.get("state_path") or ""),
            running=bool(running) if running is not None else bool(data.get("running", False)),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "display": self.display,
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


@dataclass(slots=True)
class XServerSmokeEvidence:
    display: str
    passed: bool
    status: str
    runtime_key: str
    display_in_use: bool
    probe_command: list[str]
    checked_at: str
    lifecycle_state: str = ""
    lifecycle_running: bool = False
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    timeout_seconds: float = 5.0
    evidence_path: str = ""
    evidence_sha256: str = ""
    notes: list[str] | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "display": self.display,
            "passed": self.passed,
            "status": self.status,
            "runtime_key": self.runtime_key,
            "display_in_use": self.display_in_use,
            "probe_command": self.probe_command,
            "checked_at": self.checked_at,
            "lifecycle_state": self.lifecycle_state,
            "lifecycle_running": self.lifecycle_running,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "timeout_seconds": self.timeout_seconds,
            "evidence_path": self.evidence_path,
            "evidence_sha256": self.evidence_sha256,
            "notes": list(self.notes or []),
        }


@dataclass(slots=True)
class XServerReleaseEvidenceValidation:
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


def build_x_server_plan(display: str = ":0") -> XServerPlan:
    plan = build_moba_x_server_plan(display=display)
    return XServerPlan(plan.command, plan.notes)


def build_moba_x_server_plan(
    display: str = ":0",
    *,
    system: str | None = None,
    which: WhichResolver = shutil.which,
    packaged_roots: Iterable[Path] | None = None,
    display_probe: DisplayProbe | None = None,
    allow_display_in_use: bool = False,
) -> ManagedXServerPlan:
    display = safe.display(display)
    system_key = (system or platform.system()).lower()
    candidates = discover_x_server_runtimes(system=system_key, which=which, packaged_roots=packaged_roots)
    runtime = _select_runtime(candidates, system_key)
    probe = display_probe or is_x_display_in_use
    display_in_use = probe(display)
    if display_in_use and not allow_display_in_use:
        raise ValueError(f"X display {display} appears to be in use; choose another display or stop the existing X server")
    command = _runtime_command(runtime, display, system_key)
    notes = _runtime_notes(runtime, display, display_in_use, system_key)
    return ManagedXServerPlan(
        display=display,
        command=command,
        runtime=runtime,
        extensions=x_server_extension_inventory(runtime),
        environment={"DISPLAY": display},
        display_in_use=display_in_use,
        notes=notes,
        candidates=candidates,
    )


def build_moba_x_server_status(
    display: str = ":0",
    *,
    system: str | None = None,
    which: WhichResolver = shutil.which,
    packaged_roots: Iterable[Path] | None = None,
    display_probe: DisplayProbe | None = None,
    state_path: Path | None = None,
    pid_probe: PidProbe | None = None,
) -> MobaXServerStatus:
    display = safe.display(display)
    system_key = (system or platform.system()).lower()
    candidates = discover_x_server_runtimes(system=system_key, which=which, packaged_roots=packaged_roots)
    probe = display_probe or is_x_display_in_use
    display_in_use = probe(display)
    runtime = _select_runtime(candidates, system_key)
    notes: list[str] = []
    plan: ManagedXServerPlan | None = None
    if runtime.available:
        plan = build_moba_x_server_plan(
            display=display,
            system=system_key,
            which=which,
            packaged_roots=packaged_roots,
            display_probe=probe,
            allow_display_in_use=True,
        )
        notes.extend(plan.notes)
    else:
        notes.append("No local X server runtime was found; install VcXsrv, XQuartz, Xorg, Xvfb, Xephyr or Xnest.")
    lifecycle = load_moba_x_server_record(state_path=state_path, pid_probe=pid_probe)
    if lifecycle is not None:
        notes.append(f"Managed lifecycle state: {lifecycle.state} pid={lifecycle.pid or 'none'} running={'yes' if lifecycle.running else 'no'}.")
    return MobaXServerStatus(
        display=display,
        available=runtime.available,
        selected_runtime=runtime.key,
        display_in_use=display_in_use,
        extensions=x_server_extension_inventory(runtime),
        candidates=candidates,
        plan=plan,
        lifecycle=lifecycle,
        notes=notes,
    )


def build_moba_x_server_package_status(
    *,
    system: str | None = None,
    roots: Iterable[Path] | None = None,
) -> XServerPackageStatus:
    system_key = (system or platform.system()).lower()
    resolved_roots = x_server_packaged_runtime_roots(roots)
    candidates = discover_packaged_x_server_runtimes(system=system_key, roots=resolved_roots)
    selected = candidates[0].key if candidates else ""
    notes = [
        f"Scanned {len(resolved_roots)} packaged X server runtime root(s).",
        f"Set {XSERVER_RUNTIME_DIR_ENV} to a release-owned runtime directory to prefer packaged X server binaries.",
    ]
    if candidates:
        notes.append(f"Selected packaged X server runtime: {candidates[0].label}.")
    else:
        notes.append("No packaged X server runtime was found; ROW will fall back to host PATH discovery.")
    return XServerPackageStatus(
        system=system_key,
        roots=tuple(str(root) for root in resolved_roots),
        packaged_available=bool(candidates),
        candidates=candidates,
        selected_runtime=selected,
        notes=notes,
    )


def build_moba_x_server_runtime_bundle_plan(
    out_dir: Path,
    *,
    runtime_key: str,
    source_path: Path | None = None,
    system: str | None = None,
    release_target: str = "local-bundle",
    executable_name: str | None = None,
    allow_placeholder: bool = False,
) -> XServerRuntimeBundlePlan:
    system_key = (system or platform.system()).lower()
    key, label, default_executable, _bundled = _runtime_spec_by_key(system_key, runtime_key)
    root = Path(out_dir).expanduser()
    packaged_name = executable_name or _packaged_runtime_executable_name(system_key, default_executable)
    target = root / system_key / "bin" / safe.path_arg(packaged_name, "x server executable name")
    manifest_path = root / "xserver-runtime.json"
    notes = [
        "Bundle plan writes a release-owned X server runtime layout discoverable through ROW_XSERVER_RUNTIME_DIR.",
        "Production parity should use real X server binaries supplied by the release build; placeholders are only for local contract rehearsal.",
    ]
    if allow_placeholder:
        notes.append("Placeholder runtime generation is enabled; replace it with a real X server binary before claiming full parity.")
    return XServerRuntimeBundlePlan(
        schema=XSERVER_RUNTIME_BUNDLE_SCHEMA,
        out_dir=str(root),
        system=system_key,
        runtime_key=key,
        runtime_label=label,
        release_target=safe.clean_text(release_target, "release target"),
        source_path=str(source_path.expanduser()) if source_path is not None else "",
        executable_name=packaged_name,
        target_executable=str(target),
        manifest_path=str(manifest_path),
        allow_placeholder=bool(allow_placeholder),
        notes=notes,
    )


def write_moba_x_server_runtime_bundle(plan: XServerRuntimeBundlePlan) -> XServerRuntimeBundleResult:
    if plan.schema != XSERVER_RUNTIME_BUNDLE_SCHEMA:
        raise ValueError(f"x server runtime bundle plan schema must be {XSERVER_RUNTIME_BUNDLE_SCHEMA}")
    root = Path(plan.out_dir)
    target = Path(plan.target_executable)
    target.parent.mkdir(parents=True, exist_ok=True)
    placeholder = False
    if plan.source_path:
        source = Path(plan.source_path).expanduser()
        if not source.is_file():
            raise ValueError(f"x server runtime source is missing: {source}")
        shutil.copy2(source, target)
    elif plan.allow_placeholder:
        placeholder = True
        target.write_text(
            "\n".join(
                [
                    "#!/usr/bin/env sh",
                    f"echo 'ROW packaged X server placeholder: {plan.runtime_key}'",
                    "",
                ]
            ),
            encoding="utf-8",
        )
    else:
        raise ValueError("x server runtime source is required unless --allow-placeholder is explicitly set")
    _chmod_executable(target)
    runtime_sha256 = _sha256_file(target)
    manifest_path = Path(plan.manifest_path)
    manifest = {
        "schema": XSERVER_RUNTIME_BUNDLE_SCHEMA,
        "release_target": plan.release_target,
        "system": plan.system,
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
    write_json_atomic(manifest_path, manifest, private=False)
    package_status = build_moba_x_server_package_status(system=plan.system, roots=[root])
    notes = list(plan.notes)
    if placeholder:
        notes.append("Placeholder runtime requires replacement before full MobaXterm embedded X server parity.")
    if not package_status.packaged_available:
        notes.append("Packaged runtime was written but was not discovered by package-status; check runtime key/system layout.")
    return XServerRuntimeBundleResult(
        plan=plan,
        root=str(root),
        executable_path=str(target),
        manifest_path=str(manifest_path),
        runtime_sha256=runtime_sha256,
        files=(_relative_to_root(target, root), _relative_to_root(manifest_path, root)),
        placeholder=placeholder,
        package_status=package_status,
        notes=notes,
    )


def run_x_server(plan: XServerPlan, dry_run: bool = False) -> XServerPlan:
    if not dry_run:
        safe.argv_list(plan.command, "x server command")
        subprocess.Popen(plan.command)  # noqa: S603 - argv list, no shell
    return plan


def start_moba_x_server(
    plan: ManagedXServerPlan,
    *,
    dry_run: bool = False,
    state_path: Path | None = None,
    popen_factory: Callable[..., Any] = subprocess.Popen,
) -> XServerLifecycleRecord:
    safe.argv_list(plan.command, "managed x server command")
    target_state_path = moba_x_server_state_path(state_path)
    now = _timestamp()
    if dry_run:
        return XServerLifecycleRecord(
            display=plan.display,
            runtime_key=plan.runtime.key,
            command=plan.command,
            state="dry-run",
            pid=None,
            started_at=now,
            dry_run=True,
            state_path=str(target_state_path),
            running=False,
        )
    if not plan.runtime.available:
        raise ValueError(f"X server runtime is not available: {plan.runtime.label}")
    process = popen_factory(plan.command, env={**os.environ, **plan.environment})  # noqa: S603 - argv list, no shell
    pid = int(process.pid)
    record = XServerLifecycleRecord(
        display=plan.display,
        runtime_key=plan.runtime.key,
        command=plan.command,
        state="started",
        pid=pid,
        started_at=now,
        dry_run=False,
        state_path=str(target_state_path),
        running=True,
    )
    write_json_atomic(target_state_path, record.to_dict(), private=True)
    return record


def stop_moba_x_server(
    *,
    state_path: Path | None = None,
    pid_probe: PidProbe | None = None,
    terminator: ProcessTerminator | None = None,
) -> XServerLifecycleRecord:
    target_state_path = moba_x_server_state_path(state_path)
    record = load_moba_x_server_record(state_path=target_state_path, pid_probe=pid_probe)
    if record is None:
        raise ValueError(f"no managed X server state found at {target_state_path}")
    if record.pid is not None and record.running:
        (terminator or _terminate_pid)(record.pid)
    stopped = XServerLifecycleRecord(
        display=record.display,
        runtime_key=record.runtime_key,
        command=record.command,
        state="stopped",
        pid=record.pid,
        started_at=record.started_at,
        stopped_at=_timestamp(),
        dry_run=record.dry_run,
        state_path=str(target_state_path),
        running=False,
    )
    write_json_atomic(target_state_path, stopped.to_dict(), private=True)
    return stopped


def load_moba_x_server_record(
    *,
    state_path: Path | None = None,
    pid_probe: PidProbe | None = None,
) -> XServerLifecycleRecord | None:
    target_state_path = moba_x_server_state_path(state_path)
    if not target_state_path.exists():
        return None

    data = json.loads(target_state_path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"managed X server state must be a JSON object: {target_state_path}")
    pid_value = data.get("pid")
    pid = int(pid_value) if pid_value not in (None, "") else None
    running = (pid_probe or _pid_exists)(pid) if pid is not None and str(data.get("state", "")) == "started" else False
    return XServerLifecycleRecord.from_dict(data, state_path=target_state_path, running=running)


def moba_x_server_state_path(path: Path | None = None) -> Path:
    return path or (ensure_data_dir() / "xserver-state.json")


def run_moba_x_server_smoke(
    display: str = ":0",
    *,
    system: str | None = None,
    which: WhichResolver = shutil.which,
    packaged_roots: Iterable[Path] | None = None,
    display_probe: DisplayProbe | None = None,
    state_path: Path | None = None,
    pid_probe: PidProbe | None = None,
    probe_command: str | None = None,
    timeout_seconds: float = 5.0,
    runner: ProbeRunner = subprocess.run,
) -> XServerSmokeEvidence:
    display = safe.display(display)
    if timeout_seconds <= 0:
        raise ValueError("x11 smoke timeout must be positive")
    status = build_moba_x_server_status(
        display=display,
        system=system,
        which=which,
        packaged_roots=packaged_roots,
        display_probe=display_probe,
        state_path=state_path,
        pid_probe=pid_probe,
    )
    lifecycle_state = status.lifecycle.state if status.lifecycle else ""
    lifecycle_running = bool(status.lifecycle and status.lifecycle.running)
    notes = list(status.notes)
    command = safe.argv(probe_command, "x11 smoke probe command") if probe_command else _default_probe_command(display, which=which)
    if not command:
        smoke_status = "missing-probe-command"
        if not status.available and not lifecycle_running and not status.display_in_use:
            smoke_status = "unavailable"
        notes.append("No X11 probe command was found; install xdpyinfo, xset or xprop, or pass --probe-command.")
        return XServerSmokeEvidence(
            display=display,
            passed=False,
            status=smoke_status,
            runtime_key=status.selected_runtime,
            display_in_use=status.display_in_use,
            probe_command=[],
            checked_at=_timestamp(),
            lifecycle_state=lifecycle_state,
            lifecycle_running=lifecycle_running,
            timeout_seconds=float(timeout_seconds),
            notes=notes,
        )
    try:
        completed = runner(
            command,
            env={**os.environ, "DISPLAY": display},
            capture_output=True,
            text=True,
            timeout=float(timeout_seconds),
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        return XServerSmokeEvidence(
            display=display,
            passed=False,
            status="timeout",
            runtime_key=status.selected_runtime,
            display_in_use=status.display_in_use,
            probe_command=command,
            checked_at=_timestamp(),
            lifecycle_state=lifecycle_state,
            lifecycle_running=lifecycle_running,
            stdout=_limit_text(exc.stdout or ""),
            stderr=_limit_text(exc.stderr or ""),
            timeout_seconds=float(timeout_seconds),
            notes=[*notes, "X11 smoke probe timed out."],
        )
    except OSError as exc:
        return XServerSmokeEvidence(
            display=display,
            passed=False,
            status="probe-error",
            runtime_key=status.selected_runtime,
            display_in_use=status.display_in_use,
            probe_command=command,
            checked_at=_timestamp(),
            lifecycle_state=lifecycle_state,
            lifecycle_running=lifecycle_running,
            stderr=_limit_text(str(exc)),
            timeout_seconds=float(timeout_seconds),
            notes=[*notes, "X11 smoke probe could not be executed."],
        )
    return XServerSmokeEvidence(
        display=display,
        passed=int(completed.returncode) == 0,
        status="passed" if int(completed.returncode) == 0 else "failed",
        runtime_key=status.selected_runtime,
        display_in_use=status.display_in_use,
        probe_command=command,
        checked_at=_timestamp(),
        lifecycle_state=lifecycle_state,
        lifecycle_running=lifecycle_running,
        returncode=int(completed.returncode),
        stdout=_limit_text(str(completed.stdout or "")),
        stderr=_limit_text(str(completed.stderr or "")),
        timeout_seconds=float(timeout_seconds),
        notes=notes,
    )


def write_moba_x_server_smoke_evidence(
    evidence: XServerSmokeEvidence,
    out_path: Path,
) -> XServerSmokeEvidence:
    evidence.evidence_path = str(out_path)
    payload_without_hash = dict(evidence.to_dict())
    payload_without_hash["evidence_sha256"] = ""
    encoded = json.dumps(payload_without_hash, indent=2, sort_keys=True).encode("utf-8")
    evidence.evidence_sha256 = hashlib.sha256(encoded).hexdigest()
    write_json_atomic(out_path, evidence.to_dict(), private=True)
    return evidence


def validate_moba_x_server_release_evidence(
    evidence_path: Path,
    *,
    assets_dir: Path | None = None,
) -> XServerReleaseEvidenceValidation:
    target_evidence_path = Path(evidence_path)
    root = Path(assets_dir) if assets_dir is not None else target_evidence_path.parent
    errors: list[str] = []
    warnings: list[str] = []
    summary: dict[str, Any] = {
        "schema": "",
        "release_target": "",
        "platform": "",
        "display": "",
        "runtime_key": "",
        "forwarded_gui_command": "",
        "smoke_status": "",
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
    if schema != XSERVER_RELEASE_EVIDENCE_SCHEMA:
        errors.append(f"schema must be {XSERVER_RELEASE_EVIDENCE_SCHEMA}")

    release_target = _required_text(data, "release_target", errors)
    platform_name = _required_text(data, "platform", errors)
    display = _required_text(data, "display", errors)
    summary.update({"release_target": release_target, "platform": platform_name, "display": display})
    if display:
        try:
            safe.display(display)
        except ValueError as exc:
            errors.append(f"display is invalid: {exc}")

    runtime = _required_mapping(data, "runtime", errors)
    runtime_key = _required_text(runtime, "key", errors, prefix="runtime.")
    runtime_source = _required_text(runtime, "source", errors, prefix="runtime.")
    runtime_executable = _required_text(runtime, "executable", errors, prefix="runtime.")
    runtime_sha256 = _required_text(runtime, "sha256", errors, prefix="runtime.")
    summary["runtime_key"] = runtime_key
    if runtime_source not in {"bundled", "packaged"}:
        errors.append("runtime.source must be bundled or packaged")
    if runtime.get("bundled") is not True:
        errors.append("runtime.bundled must be true for MobaXterm-style embedded X server parity evidence")
    _validate_asset_hash(
        runtime_executable,
        runtime_sha256,
        root,
        errors,
        "runtime.executable",
    )

    smoke = _required_mapping(data, "smoke", errors)
    smoke_status = str(smoke.get("status") or "")
    summary["smoke_status"] = smoke_status
    if smoke.get("passed") is not True or smoke_status != "passed":
        errors.append("smoke must have passed=true and status=passed")
    smoke_file = _required_text(smoke, "evidence_file", errors, prefix="smoke.")
    smoke_sha256 = _required_text(smoke, "evidence_sha256", errors, prefix="smoke.")
    smoke_path = _validate_asset_hash(smoke_file, smoke_sha256, root, errors, "smoke.evidence_file")
    if smoke_path is not None and smoke_path.suffix.lower() == ".json":
        try:
            smoke_data = json.loads(smoke_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            errors.append(f"smoke.evidence_file cannot be parsed as JSON: {exc}")
        else:
            if isinstance(smoke_data, dict):
                if smoke_data.get("passed") is not True:
                    errors.append("smoke.evidence_file JSON must also have passed=true")
                if display and str(smoke_data.get("display", "")) != display:
                    errors.append("smoke.evidence_file display must match release evidence display")
            else:
                errors.append("smoke.evidence_file JSON root must be an object")

    forwarded = _required_mapping(data, "forwarded_gui_app", errors)
    forwarded_command = _required_text(forwarded, "command", errors, prefix="forwarded_gui_app.")
    summary["forwarded_gui_command"] = forwarded_command
    if forwarded.get("status") != "passed":
        errors.append("forwarded_gui_app.status must be passed")
    forwarding_mode = _required_text(forwarded, "x11_forwarding", errors, prefix="forwarded_gui_app.")
    if forwarding_mode and forwarding_mode not in {"trusted", "untrusted", "enabled"}:
        errors.append("forwarded_gui_app.x11_forwarding must be trusted, untrusted or enabled")
    if forwarded.get("window_observed") is not True:
        errors.append("forwarded_gui_app.window_observed must be true")
    screenshot = _required_text(forwarded, "screenshot", errors, prefix="forwarded_gui_app.")
    screenshot_sha256 = _required_text(forwarded, "screenshot_sha256", errors, prefix="forwarded_gui_app.")
    _validate_asset_hash(
        screenshot,
        screenshot_sha256,
        root,
        errors,
        "forwarded_gui_app.screenshot",
    )

    return XServerReleaseEvidenceValidation(
        evidence_path=str(target_evidence_path),
        assets_dir=str(root),
        passed=not errors,
        errors=errors,
        warnings=warnings,
        summary=summary,
    )


def discover_x_server_runtimes(
    *,
    system: str | None = None,
    which: WhichResolver = shutil.which,
    packaged_roots: Iterable[Path] | None = None,
) -> tuple[XServerRuntimeCandidate, ...]:
    system_key = (system or platform.system()).lower()
    packaged = discover_packaged_x_server_runtimes(system=system_key, roots=packaged_roots)
    path_candidates = tuple(_runtime_candidate(*candidate, which=which) for candidate in _runtime_specs(system_key))
    return (*packaged, *path_candidates)


def discover_packaged_x_server_runtimes(
    *,
    system: str | None = None,
    roots: Iterable[Path] | None = None,
) -> tuple[XServerRuntimeCandidate, ...]:
    system_key = (system or platform.system()).lower()
    candidates: list[XServerRuntimeCandidate] = []
    for root in x_server_packaged_runtime_roots(roots):
        for key, label, executable, bundled in _runtime_specs(system_key):
            for candidate_path in _packaged_executable_paths(root, system_key, key, label, executable):
                if candidate_path.is_file():
                    candidates.append(
                        XServerRuntimeCandidate(
                            key=key,
                            label=label,
                            executable=str(candidate_path),
                            available=True,
                            source=f"packaged:{root}",
                            bundled=True,
                        )
                    )
                    break
    return tuple(candidates)


def x_server_packaged_runtime_roots(roots: Iterable[Path] | None = None) -> tuple[Path, ...]:
    raw_roots: list[Path] = []
    if roots is not None:
        raw_roots.extend(Path(root) for root in roots)
    env_value = os.environ.get(XSERVER_RUNTIME_DIR_ENV, "")
    if env_value:
        raw_roots.extend(Path(part) for part in env_value.split(os.pathsep) if part)
    executable_dir = Path(sys.executable).resolve().parent
    raw_roots.extend(
        [
            executable_dir / "xserver",
            executable_dir / "runtimes" / "xserver",
            Path(__file__).resolve().parents[2] / "vendor" / "xserver",
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


def x_server_extension_inventory(
    runtime: XServerRuntimeCandidate | None = None,
) -> tuple[XServerExtension, ...]:
    runtime_status = "planned" if runtime and runtime.available else "runtime-dependent"
    return (
        XServerExtension("glx", "GLX / OpenGL", "OpenGL X applications", runtime_status),
        XServerExtension("randr", "RANDR", "remote desktop resizing and rotation", runtime_status),
        XServerExtension("render", "RENDER", "modern X drawing acceleration", runtime_status),
        XServerExtension("composite", "Composite", "composited remote GUI windows", runtime_status),
        XServerExtension("xfixes", "XFixes", "cursor and selection fixes", runtime_status),
        XServerExtension("xinput", "XInput", "extended keyboard and pointer input", runtime_status),
        XServerExtension("xkeyboard", "XKeyboard", "keyboard layout handling", runtime_status),
        XServerExtension("xdmcp", "XDMCP", "display-manager sessions", runtime_status),
    )


def is_x_display_in_use(display: str) -> bool:
    display = safe.display(display)
    number = _display_number(display)
    if os.name != "nt" and Path(f"/tmp/.X11-unix/X{number}").exists():
        return True
    port = 6000 + number
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.2):
            return True
    except OSError:
        return False


def _runtime_specs(system_key: str) -> tuple[tuple[str, str, str, bool], ...]:
    if system_key == "windows":
        return (
            ("vcxsrv", "VcXsrv", "vcxsrv", False),
            ("xlaunch", "XLaunch", "xlaunch", False),
            ("xming", "Xming", "Xming", False),
            ("xwin", "Cygwin/X XWin", "XWin", False),
        )
    if system_key == "darwin":
        return (
            ("xquartz", "XQuartz", "open", False),
            ("xquartz-xorg", "XQuartz Xorg", "Xquartz", False),
        )
    return (
        ("xorg", "Xorg", "Xorg", False),
        ("xvfb", "Xvfb", "Xvfb", False),
        ("xephyr", "Xephyr", "Xephyr", False),
        ("xnest", "Xnest", "Xnest", False),
    )


def _runtime_spec_by_key(system_key: str, runtime_key: str) -> tuple[str, str, str, bool]:
    key = safe.option_value(runtime_key, "x server runtime").lower()
    for spec in _runtime_specs(system_key):
        if spec[0] == key:
            return spec
    allowed = ", ".join(spec[0] for spec in _runtime_specs(system_key))
    raise ValueError(f"unsupported X server runtime for {system_key}: {key}; expected one of: {allowed}")


def _packaged_runtime_executable_name(system_key: str, executable: str) -> str:
    if system_key == "windows" and not executable.lower().endswith(".exe"):
        return f"{executable}.exe"
    return executable


def _packaged_executable_paths(
    root: Path,
    system_key: str,
    key: str,
    label: str,
    executable: str,
) -> tuple[Path, ...]:
    names = [executable]
    if system_key == "windows":
        names.extend([f"{executable}.exe", f"{label}.exe", f"{key}.exe"])
    label_dir = label.replace(" ", "")
    return tuple(
        candidate
        for name in dict.fromkeys(names)
        for candidate in (
            root / name,
            root / "bin" / name,
            root / "xserver" / name,
            root / "xserver" / "bin" / name,
            root / system_key / name,
            root / system_key / "bin" / name,
            root / key / name,
            root / key / "bin" / name,
            root / label_dir / name,
            root / label_dir / "bin" / name,
        )
    )


def _relative_to_root(path: Path, root: Path) -> str:
    return path.resolve().relative_to(root.resolve()).as_posix()


def _chmod_executable(path: Path) -> None:
    try:
        path.chmod(path.stat().st_mode | 0o111)
    except OSError:
        pass


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


def _runtime_candidate(
    key: str,
    label: str,
    executable: str,
    bundled: bool,
    *,
    which: WhichResolver,
) -> XServerRuntimeCandidate:
    resolved = which(executable)
    return XServerRuntimeCandidate(
        key=key,
        label=label,
        executable=resolved or executable,
        available=resolved is not None,
        source="PATH" if resolved else "missing",
        bundled=bundled,
    )


def _select_runtime(
    candidates: tuple[XServerRuntimeCandidate, ...],
    system: str,
) -> XServerRuntimeCandidate:
    for candidate in candidates:
        if candidate.available:
            return candidate
    fallback = {
        "windows": XServerRuntimeCandidate("vcxsrv", "VcXsrv", "vcxsrv", False, "fallback"),
        "darwin": XServerRuntimeCandidate("xquartz", "XQuartz", "open", False, "fallback"),
    }.get(system)
    return fallback or XServerRuntimeCandidate("xorg", "Xorg", "Xorg", False, "fallback")


def _runtime_command(runtime: XServerRuntimeCandidate, display: str, system: str) -> list[str]:
    executable = safe.path_arg(runtime.executable, "x server executable")
    if system == "windows":
        if runtime.key == "xlaunch":
            return [executable]
        if runtime.key == "xming":
            return [executable, display, "-multiwindow", "-clipboard", "-ac"]
        return [executable, display, "-multiwindow", "-clipboard", "-wgl", "-ac"]
    if system == "darwin":
        if runtime.key == "xquartz-xorg":
            return [executable, display]
        return [executable, "-a", "XQuartz"]
    if runtime.key == "xvfb":
        return [executable, display, "-screen", "0", "1920x1080x24", "-nolisten", "tcp"]
    if runtime.key in {"xephyr", "xnest"}:
        return [executable, display, "-nolisten", "tcp"]
    return [executable, display, "-nolisten", "tcp"]


def _runtime_notes(
    runtime: XServerRuntimeCandidate,
    display: str,
    display_in_use: bool,
    system: str,
) -> list[str]:
    notes = [
        "Managed X server runtime plan for X11-forwarded SSH and XDMCP workflows.",
        f"DISPLAY will be set to {display}.",
    ]
    if runtime.available:
        notes.append(f"Selected X server runtime: {runtime.label}.")
    else:
        notes.append(f"No detected X server runtime; fallback command uses {runtime.executable}.")
    if runtime.bundled:
        notes.append("Runtime is bundled with the ROW distribution.")
    else:
        notes.append("Runtime is provided by the host system; install it before launching for a real session.")
    if display_in_use:
        notes.append("Display appears to be in use; status mode reports this but start mode blocks unless explicitly allowed.")
    if system == "windows":
        notes.append("Windows multiwindow and clipboard flags mirror the common MobaXterm-style X server workflow.")
    elif system == "darwin":
        notes.append("macOS uses XQuartz through LaunchServices when available.")
    else:
        notes.append("POSIX launch disables TCP listening by default; use SSH X11 forwarding for transport.")
    return notes


def _display_number(display: str) -> int:
    body = display[1:]
    if "." in body:
        body = body.split(".", 1)[0]
    return int(body)


def _default_probe_command(display: str, *, which: WhichResolver) -> list[str]:
    for executable, args in (
        ("xdpyinfo", ["-display", display]),
        ("xset", ["-display", display, "q"]),
        ("xprop", ["-display", display, "-root"]),
    ):
        resolved = which(executable)
        if resolved:
            return [resolved, *args]
    return []


def _limit_text(value: str, limit: int = 4000) -> str:
    if len(value) <= limit:
        return value
    return value[:limit] + "\n...[truncated]"


def _pid_exists(pid: int) -> bool:
    if pid <= 0:
        return False
    if os.name == "nt":
        try:
            completed = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                check=False,
                capture_output=True,
                text=True,
                timeout=3,
            )
        except (OSError, subprocess.SubprocessError):
            return False
        return str(pid) in completed.stdout
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _terminate_pid(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(["taskkill", "/PID", str(pid), "/T"], check=False, capture_output=True, text=True)
        return
    os.kill(pid, signal.SIGTERM)


def _timestamp() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _first_available(candidates: list[str]) -> str | None:
    for candidate in candidates:
        if shutil.which(candidate):
            return candidate
    return None

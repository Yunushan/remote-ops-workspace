from __future__ import annotations

import shlex
import subprocess
from collections.abc import Callable, Iterable
from dataclasses import dataclass, field
from dataclasses import replace as replace_dataclass
from pathlib import Path, PurePosixPath

from . import command_safety as safe
from .launcher import LaunchPlan, build_launch_plan
from .models import Profile


@dataclass(slots=True)
class SftpBatchPlan:
    profile_name: str
    command: list[str]
    batch_commands: list[str]
    notes: list[str]
    destructive: bool = False
    force: bool = False
    safety_warnings: list[str] = field(default_factory=list)

    def batch_input(self) -> str:
        return "\n".join(self.batch_commands) + "\n"

    def printable(self) -> str:
        return shlex.join(self.command)

    def printable_batch(self) -> str:
        return "\n".join(self.batch_commands)


@dataclass(slots=True)
class SftpQueueItem:
    action: str
    remote_path: str | None = None
    local_path: str | None = None
    new_remote_path: str | None = None
    recursive: bool = False

    def to_dict(self) -> dict[str, object]:
        return {
            "action": self.action,
            "remote_path": self.remote_path,
            "local_path": self.local_path,
            "new_remote_path": self.new_remote_path,
            "recursive": self.recursive,
        }


@dataclass(frozen=True, slots=True)
class SftpSafetyReview:
    warnings: tuple[str, ...] = ()

    @property
    def destructive(self) -> bool:
        return bool(self.warnings)


@dataclass(slots=True)
class SftpQueuePlan:
    profile_name: str
    command: list[str]
    items: list[SftpQueueItem]
    batch_commands: list[str]
    notes: list[str]
    destructive: bool = False
    force: bool = False
    safety_warnings: list[str] = field(default_factory=list)

    def batch_input(self) -> str:
        return "\n".join(self.batch_commands) + "\n"

    def printable(self) -> str:
        return shlex.join(self.command)

    def printable_batch(self) -> str:
        return "\n".join(self.batch_commands)

    def to_dict(self) -> dict[str, object]:
        return {
            "profile": self.profile_name,
            "command": self.command,
            "items": [item.to_dict() for item in self.items],
            "batch_commands": self.batch_commands,
            "notes": self.notes,
            "destructive": self.destructive,
            "force": self.force,
            "safety_warnings": self.safety_warnings,
        }


@dataclass(slots=True)
class SftpQueueResult:
    profile_name: str
    command: list[str]
    items: list[SftpQueueItem]
    dry_run: bool
    ok: bool
    destructive: bool = False
    force: bool = False
    safety_warnings: list[str] = field(default_factory=list)
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""
    progress: list[SftpQueueProgress] = field(default_factory=list)

    def to_dict(self) -> dict[str, object]:
        return {
            "profile": self.profile_name,
            "command": self.command,
            "items": [item.to_dict() for item in self.items],
            "dry_run": self.dry_run,
            "ok": self.ok,
            "destructive": self.destructive,
            "force": self.force,
            "safety_warnings": self.safety_warnings,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "progress": [event.to_dict() for event in self.progress],
        }


@dataclass(frozen=True, slots=True)
class SftpQueueProgress:
    index: int
    total: int
    item: SftpQueueItem
    state: str
    returncode: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "index": self.index,
            "total": self.total,
            "item": self.item.to_dict(),
            "state": self.state,
            "returncode": self.returncode,
        }


@dataclass(slots=True)
class LocalFilePreview:
    path: str
    exists: bool
    kind: str
    size: int | None = None
    text: str = ""
    children: list[str] | None = None
    binary: bool = False
    truncated: bool = False
    error: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "path": self.path,
            "exists": self.exists,
            "kind": self.kind,
            "size": self.size,
            "text": self.text,
            "children": self.children or [],
            "binary": self.binary,
            "truncated": self.truncated,
            "error": self.error,
        }


def build_sftp_interactive_plan(profile: Profile) -> LaunchPlan:
    _require_sftp_capable(profile)
    return build_launch_plan(replace_dataclass(profile, protocol="sftp"))


def run_sftp_interactive(plan: LaunchPlan, dry_run: bool = False) -> LaunchPlan:
    if not dry_run:
        safe.argv_list(plan.command, "sftp command")
        subprocess.run(plan.command, check=True)  # noqa: S603 - argv list, no shell
    return plan


def build_sftp_list_plan(profile: Profile, remote_path: str = ".") -> SftpBatchPlan:
    return _build_batch_plan(profile, [f"ls -la {_quote_remote(remote_path)}"])


def build_sftp_remote_preview_plan(profile: Profile, remote_path: str = ".") -> SftpBatchPlan:
    return _build_batch_plan(profile, [f"ls -la {_quote_remote(remote_path)}"])


def build_sftp_get_plan(
    profile: Profile,
    remote_path: str,
    local_path: Path | str | None = None,
    *,
    recursive: bool = False,
    allow_overwrite: bool = False,
) -> SftpBatchPlan:
    safety = _review_get_safety(remote_path, local_path)
    command = "get"
    if recursive:
        command += " -r"
    command += f" {_quote_remote(remote_path)}"
    if local_path is not None:
        command += f" {_quote_local(local_path)}"
    return _build_batch_plan(
        profile,
        [command],
        safety=safety,
        force=allow_overwrite,
    )


def build_sftp_put_plan(
    profile: Profile,
    local_path: Path | str,
    remote_path: str | None = None,
    *,
    recursive: bool = False,
    allow_overwrite: bool = False,
) -> SftpBatchPlan:
    safety = _review_put_safety(local_path, remote_path)
    command = "put"
    if recursive:
        command += " -r"
    command += f" {_quote_local(local_path)}"
    if remote_path is not None:
        command += f" {_quote_remote(remote_path)}"
    return _build_batch_plan(
        profile,
        [command],
        safety=safety,
        force=allow_overwrite,
    )


def build_sftp_mkdir_plan(profile: Profile, remote_path: str) -> SftpBatchPlan:
    return _build_batch_plan(profile, [f"mkdir {_quote_remote(remote_path)}"])


def build_sftp_rm_plan(profile: Profile, remote_path: str, *, allow_delete: bool = False) -> SftpBatchPlan:
    safety = _review_delete_safety("rm", remote_path)
    return _build_batch_plan(profile, [f"rm {_quote_remote(remote_path)}"], safety=safety, force=allow_delete)


def build_sftp_rmdir_plan(profile: Profile, remote_path: str, *, allow_delete: bool = False) -> SftpBatchPlan:
    safety = _review_delete_safety("rmdir", remote_path)
    return _build_batch_plan(profile, [f"rmdir {_quote_remote(remote_path)}"], safety=safety, force=allow_delete)


def build_sftp_rename_plan(
    profile: Profile,
    old_path: str,
    new_path: str,
    *,
    allow_rename: bool = False,
) -> SftpBatchPlan:
    safety = _review_rename_safety(old_path, new_path)
    return _build_batch_plan(
        profile,
        [f"rename {_quote_remote(old_path)} {_quote_remote(new_path)}"],
        safety=safety,
        force=allow_rename,
    )


def run_sftp_batch(plan: SftpBatchPlan, dry_run: bool = False) -> SftpBatchPlan:
    _require_force_for_execution(plan.destructive, plan.force, dry_run, plan.safety_warnings)
    if not dry_run:
        safe.argv_list(plan.command, "sftp command")
        subprocess.run(plan.command, input=plan.batch_input(), text=True, check=True)
    return plan


def parse_transfer_item_spec(spec: str) -> SftpQueueItem:
    parts = safe.argv(spec, "transfer queue item")
    action = parts[0].lower()
    recursive = False
    values: list[str] = []
    for part in parts[1:]:
        if part in {"-r", "--recursive"}:
            recursive = True
        else:
            values.append(part)

    if action == "get" and values:
        return SftpQueueItem(
            action="get",
            remote_path=values[0],
            local_path=values[1] if len(values) > 1 else None,
            recursive=recursive,
        )
    if action == "put" and values:
        return SftpQueueItem(
            action="put",
            local_path=values[0],
            remote_path=values[1] if len(values) > 1 else None,
            recursive=recursive,
        )
    if action in {"mkdir", "rm", "rmdir"} and len(values) == 1:
        return SftpQueueItem(action=action, remote_path=values[0])
    if action == "rename" and len(values) == 2:
        return SftpQueueItem(action=action, remote_path=values[0], new_remote_path=values[1])
    raise ValueError(f"invalid transfer queue item: {spec}")


def build_sftp_queue_plan(profile: Profile, items: Iterable[SftpQueueItem], *, force: bool = False) -> SftpQueuePlan:
    _require_sftp_capable(profile)
    queue_items = list(items)
    if not queue_items:
        raise ValueError("transfer queue requires at least one item")
    interactive = build_sftp_interactive_plan(profile)
    command = [interactive.command[0], "-b", "-", *interactive.command[1:]]
    safety_warnings = _queue_safety_warnings(queue_items)
    batch_commands = [_queue_item_batch_command(item) for item in queue_items]
    notes = [
        "Each queue item runs through sftp stdin; no shell command string is used.",
        "Execution emits actual per-item running/completed/failed progress; byte percentages are not fabricated.",
        *interactive.notes,
    ]
    notes.extend(_safety_notes(safety_warnings, force))
    return SftpQueuePlan(
        profile_name=profile.name,
        command=command,
        items=queue_items,
        batch_commands=batch_commands,
        notes=notes,
        destructive=bool(safety_warnings),
        force=force,
        safety_warnings=safety_warnings,
    )


def run_sftp_queue(
    plan: SftpQueuePlan,
    dry_run: bool = False,
    *,
    on_progress: Callable[[SftpQueueProgress], None] | None = None,
) -> SftpQueueResult:
    safe.argv_list(plan.command, "sftp queue command")
    _require_force_for_execution(plan.destructive, plan.force, dry_run, plan.safety_warnings)
    if dry_run:
        progress = [
            SftpQueueProgress(index=index, total=len(plan.items), item=item, state="planned")
            for index, item in enumerate(plan.items, start=1)
        ]
        if on_progress:
            for event in progress:
                on_progress(event)
        return SftpQueueResult(
            profile_name=plan.profile_name,
            command=plan.command,
            items=plan.items,
            dry_run=True,
            ok=True,
            destructive=plan.destructive,
            force=plan.force,
            safety_warnings=plan.safety_warnings,
            progress=progress,
        )
    progress: list[SftpQueueProgress] = []
    output: list[str] = []
    errors: list[str] = []
    failed_returncode: int | None = None
    for index, (item, command) in enumerate(zip(plan.items, plan.batch_commands, strict=True), start=1):
        running = SftpQueueProgress(index=index, total=len(plan.items), item=item, state="running")
        if on_progress:
            on_progress(running)
        process = subprocess.run(
            plan.command,
            input=f"{command}\n",
            text=True,
            capture_output=True,
            check=False,
        )
        if process.stdout:
            output.append(process.stdout)
        if process.stderr:
            errors.append(process.stderr)
        if process.returncode != 0:
            failed_returncode = process.returncode
            event = SftpQueueProgress(
                index=index,
                total=len(plan.items),
                item=item,
                state="failed",
                returncode=process.returncode,
            )
            progress.append(event)
            if on_progress:
                on_progress(event)
            for skipped_index, skipped_item in enumerate(plan.items[index:], start=index + 1):
                skipped = SftpQueueProgress(
                    index=skipped_index,
                    total=len(plan.items),
                    item=skipped_item,
                    state="skipped",
                )
                progress.append(skipped)
                if on_progress:
                    on_progress(skipped)
            break
        event = SftpQueueProgress(
            index=index,
            total=len(plan.items),
            item=item,
            state="completed",
            returncode=process.returncode,
        )
        progress.append(event)
        if on_progress:
            on_progress(event)
    return SftpQueueResult(
        profile_name=plan.profile_name,
        command=plan.command,
        items=plan.items,
        dry_run=False,
        ok=failed_returncode is None,
        destructive=plan.destructive,
        force=plan.force,
        safety_warnings=plan.safety_warnings,
        returncode=failed_returncode or 0,
        stdout="".join(output),
        stderr="".join(errors),
        progress=progress,
    )


def preview_local_path(path: Path | str, *, max_bytes: int = 4096, max_entries: int = 50) -> LocalFilePreview:
    if max_bytes <= 0:
        raise ValueError("max_bytes must be positive")
    if max_entries <= 0:
        raise ValueError("max_entries must be positive")
    target = Path(safe.path_arg(str(path), "preview path"))
    try:
        if not target.exists():
            return LocalFilePreview(path=str(target), exists=False, kind="missing")
        if target.is_dir():
            child_names = sorted(child.name for child in target.iterdir())[: max_entries + 1]
            truncated = len(child_names) > max_entries
            return LocalFilePreview(
                path=str(target),
                exists=True,
                kind="directory",
                children=child_names[:max_entries],
                truncated=truncated,
            )
        if not target.is_file():
            return LocalFilePreview(path=str(target), exists=True, kind="special")
        size = target.stat().st_size
        with target.open("rb") as handle:
            payload = handle.read(max_bytes + 1)
        truncated = len(payload) > max_bytes
        payload = payload[:max_bytes]
        binary = b"\x00" in payload
        text = ""
        if not binary:
            try:
                text = payload.decode("utf-8")
            except UnicodeDecodeError:
                binary = True
        return LocalFilePreview(
            path=str(target),
            exists=True,
            kind="file",
            size=size,
            text=text,
            binary=binary,
            truncated=truncated,
        )
    except OSError as exc:
        return LocalFilePreview(path=str(target), exists=target.exists(), kind="error", error=str(exc))


def _build_batch_plan(
    profile: Profile,
    batch_commands: list[str],
    *,
    safety: SftpSafetyReview | None = None,
    force: bool = False,
) -> SftpBatchPlan:
    _require_sftp_capable(profile)
    interactive = build_sftp_interactive_plan(profile)
    command = [interactive.command[0], "-b", "-", *interactive.command[1:]]
    safety_warnings = list((safety or SftpSafetyReview()).warnings)
    notes = ["Batch is sent to sftp over stdin; no shell command string is used.", *interactive.notes]
    notes.extend(_safety_notes(safety_warnings, force))
    return SftpBatchPlan(
        profile_name=profile.name,
        command=command,
        batch_commands=batch_commands,
        notes=notes,
        destructive=bool(safety_warnings),
        force=force,
        safety_warnings=safety_warnings,
    )


def _require_sftp_capable(profile: Profile) -> None:
    if profile.protocol.lower() not in {"ssh", "sftp"}:
        raise ValueError(f"SFTP file browser requires an ssh or sftp profile: {profile.name}")


def _quote_remote(path: str) -> str:
    return shlex.quote(safe.option_value(path, "remote path"))


def _quote_local(path: Path | str) -> str:
    return shlex.quote(safe.option_value(str(path), "local path"))


def _review_get_safety(remote_path: str, local_path: Path | str | None) -> SftpSafetyReview:
    remote_text = safe.option_value(remote_path, "remote path")
    warnings: list[str] = []
    if _contains_remote_glob(remote_text):
        warnings.append("get uses a remote glob; local overwrite targets cannot be predicted")
    local_target = _local_download_target(remote_text, local_path)
    if local_target is not None and local_target.exists():
        warnings.append(f"get may overwrite existing local target: {local_target}")
    return SftpSafetyReview(tuple(warnings))


def _review_put_safety(local_path: Path | str, remote_path: str | None) -> SftpSafetyReview:
    safe.option_value(str(local_path), "local path")
    if remote_path is not None:
        safe.option_value(remote_path, "remote path")
    return SftpSafetyReview(("put can overwrite remote files because sftp has no no-clobber mode",))


def _review_delete_safety(action: str, remote_path: str) -> SftpSafetyReview:
    remote_text = _validate_destructive_remote_path(action, remote_path)
    return SftpSafetyReview((f"{action} deletes remote path: {remote_text}",))


def _review_rename_safety(old_path: str, new_path: str) -> SftpSafetyReview:
    old_text = _validate_destructive_remote_path("rename source", old_path)
    new_text = _validate_destructive_remote_path("rename destination", new_path)
    return SftpSafetyReview((f"rename moves remote path {old_text} to {new_text}",))


def _queue_safety_warnings(items: Iterable[SftpQueueItem]) -> list[str]:
    warnings: list[str] = []
    for item in items:
        action = item.action.lower()
        if action == "get" and item.remote_path:
            warnings.extend(_review_get_safety(item.remote_path, item.local_path).warnings)
        elif action == "put" and item.local_path:
            warnings.extend(_review_put_safety(item.local_path, item.remote_path).warnings)
        elif action in {"rm", "rmdir"} and item.remote_path:
            warnings.extend(_review_delete_safety(action, item.remote_path).warnings)
        elif action == "rename" and item.remote_path and item.new_remote_path:
            warnings.extend(_review_rename_safety(item.remote_path, item.new_remote_path).warnings)
    return warnings


def _safety_notes(safety_warnings: list[str], force: bool) -> list[str]:
    if not safety_warnings:
        return []
    notes = ["Destructive SFTP actions are blocked during execution unless --force is set."]
    notes.extend(f"safety: {warning}" for warning in safety_warnings)
    if force:
        notes.append("Destructive SFTP safety override acknowledged.")
    return notes


def _require_force_for_execution(
    destructive: bool,
    force: bool,
    dry_run: bool,
    safety_warnings: Iterable[str],
) -> None:
    if not destructive or force or dry_run:
        return
    details = "; ".join(safety_warnings)
    suffix = f": {details}" if details else ""
    raise ValueError(f"destructive SFTP plan requires --force before execution{suffix}")


def _local_download_target(remote_path: str, local_path: Path | str | None) -> Path | None:
    if local_path is not None:
        return Path(safe.option_value(str(local_path), "local path"))
    basename = PurePosixPath(remote_path.rstrip("/")).name
    if basename in {"", ".", ".."}:
        return None
    return Path(basename)


def _validate_destructive_remote_path(action: str, remote_path: str) -> str:
    text = safe.option_value(remote_path, f"{action} remote path")
    stripped = text.strip()
    normalized = stripped.rstrip("/")
    if normalized in {"", ".", "/", "~"}:
        raise ValueError(f"{action} remote path is too broad: {text}")
    if ".." in PurePosixPath(stripped).parts:
        raise ValueError(f"{action} remote path must not contain '..': {text}")
    if _contains_remote_glob(text):
        raise ValueError(f"{action} remote path must not contain glob characters: {text}")
    return text


def _contains_remote_glob(path: str) -> bool:
    return any(char in path for char in "*?[]{}")


def _queue_item_batch_command(item: SftpQueueItem) -> str:
    action = item.action.lower()
    if action == "get":
        if not item.remote_path:
            raise ValueError("get queue item requires remote_path")
        command = "get"
        if item.recursive:
            command += " -r"
        command += f" {_quote_remote(item.remote_path)}"
        if item.local_path:
            command += f" {_quote_local(item.local_path)}"
        return command
    if action == "put":
        if not item.local_path:
            raise ValueError("put queue item requires local_path")
        command = "put"
        if item.recursive:
            command += " -r"
        command += f" {_quote_local(item.local_path)}"
        if item.remote_path:
            command += f" {_quote_remote(item.remote_path)}"
        return command
    if action == "mkdir":
        if not item.remote_path:
            raise ValueError("mkdir queue item requires remote_path")
        return f"mkdir {_quote_remote(item.remote_path)}"
    if action == "rm":
        if not item.remote_path:
            raise ValueError("rm queue item requires remote_path")
        return f"rm {_quote_remote(item.remote_path)}"
    if action == "rmdir":
        if not item.remote_path:
            raise ValueError("rmdir queue item requires remote_path")
        return f"rmdir {_quote_remote(item.remote_path)}"
    if action == "rename":
        if not item.remote_path or not item.new_remote_path:
            raise ValueError("rename queue item requires remote_path and new_remote_path")
        return f"rename {_quote_remote(item.remote_path)} {_quote_remote(item.new_remote_path)}"
    raise ValueError(f"unsupported transfer queue action: {item.action}")

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass
from dataclasses import replace as replace_dataclass
from pathlib import Path
from typing import Iterable

from . import command_safety as safe
from .launcher import LaunchPlan, build_launch_plan
from .models import Profile


@dataclass(slots=True)
class SftpBatchPlan:
    profile_name: str
    command: list[str]
    batch_commands: list[str]
    notes: list[str]

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


@dataclass(slots=True)
class SftpQueuePlan:
    profile_name: str
    command: list[str]
    items: list[SftpQueueItem]
    batch_commands: list[str]
    notes: list[str]

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
        }


@dataclass(slots=True)
class SftpQueueResult:
    profile_name: str
    command: list[str]
    items: list[SftpQueueItem]
    dry_run: bool
    ok: bool
    returncode: int | None = None
    stdout: str = ""
    stderr: str = ""

    def to_dict(self) -> dict[str, object]:
        return {
            "profile": self.profile_name,
            "command": self.command,
            "items": [item.to_dict() for item in self.items],
            "dry_run": self.dry_run,
            "ok": self.ok,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
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
) -> SftpBatchPlan:
    command = "get"
    if recursive:
        command += " -r"
    command += f" {_quote_remote(remote_path)}"
    if local_path is not None:
        command += f" {_quote_local(local_path)}"
    return _build_batch_plan(profile, [command])


def build_sftp_put_plan(
    profile: Profile,
    local_path: Path | str,
    remote_path: str | None = None,
    *,
    recursive: bool = False,
) -> SftpBatchPlan:
    command = "put"
    if recursive:
        command += " -r"
    command += f" {_quote_local(local_path)}"
    if remote_path is not None:
        command += f" {_quote_remote(remote_path)}"
    return _build_batch_plan(profile, [command])


def build_sftp_mkdir_plan(profile: Profile, remote_path: str) -> SftpBatchPlan:
    return _build_batch_plan(profile, [f"mkdir {_quote_remote(remote_path)}"])


def build_sftp_rm_plan(profile: Profile, remote_path: str) -> SftpBatchPlan:
    return _build_batch_plan(profile, [f"rm {_quote_remote(remote_path)}"])


def build_sftp_rmdir_plan(profile: Profile, remote_path: str) -> SftpBatchPlan:
    return _build_batch_plan(profile, [f"rmdir {_quote_remote(remote_path)}"])


def build_sftp_rename_plan(profile: Profile, old_path: str, new_path: str) -> SftpBatchPlan:
    return _build_batch_plan(profile, [f"rename {_quote_remote(old_path)} {_quote_remote(new_path)}"])


def run_sftp_batch(plan: SftpBatchPlan, dry_run: bool = False) -> SftpBatchPlan:
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


def build_sftp_queue_plan(profile: Profile, items: Iterable[SftpQueueItem]) -> SftpQueuePlan:
    _require_sftp_capable(profile)
    queue_items = list(items)
    if not queue_items:
        raise ValueError("transfer queue requires at least one item")
    interactive = build_sftp_interactive_plan(profile)
    command = [interactive.command[0], "-b", "-", *interactive.command[1:]]
    batch_commands = [_queue_item_batch_command(item) for item in queue_items]
    return SftpQueuePlan(
        profile_name=profile.name,
        command=command,
        items=queue_items,
        batch_commands=batch_commands,
        notes=[
            "Transfer queue is sent to sftp over stdin; no shell command string is used.",
            *interactive.notes,
        ],
    )


def run_sftp_queue(plan: SftpQueuePlan, dry_run: bool = False) -> SftpQueueResult:
    safe.argv_list(plan.command, "sftp queue command")
    if dry_run:
        return SftpQueueResult(
            profile_name=plan.profile_name,
            command=plan.command,
            items=plan.items,
            dry_run=True,
            ok=True,
        )
    process = subprocess.run(
        plan.command,
        input=plan.batch_input(),
        text=True,
        capture_output=True,
        check=False,
    )
    return SftpQueueResult(
        profile_name=plan.profile_name,
        command=plan.command,
        items=plan.items,
        dry_run=False,
        ok=process.returncode == 0,
        returncode=process.returncode,
        stdout=process.stdout,
        stderr=process.stderr,
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


def _build_batch_plan(profile: Profile, batch_commands: list[str]) -> SftpBatchPlan:
    _require_sftp_capable(profile)
    interactive = build_sftp_interactive_plan(profile)
    command = [interactive.command[0], "-b", "-", *interactive.command[1:]]
    return SftpBatchPlan(
        profile_name=profile.name,
        command=command,
        batch_commands=batch_commands,
        notes=["Batch is sent to sftp over stdin; no shell command string is used.", *interactive.notes],
    )


def _require_sftp_capable(profile: Profile) -> None:
    if profile.protocol.lower() not in {"ssh", "sftp"}:
        raise ValueError(f"SFTP file browser requires an ssh or sftp profile: {profile.name}")


def _quote_remote(path: str) -> str:
    return shlex.quote(safe.option_value(path, "remote path"))


def _quote_local(path: Path | str) -> str:
    return shlex.quote(safe.option_value(str(path), "local path"))


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

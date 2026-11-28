"""Current-user, minute-resolution scheduler for the Moba-style Cron control."""

from __future__ import annotations

import os
import re
import shutil
import stat
import subprocess
import sys
import time
from contextlib import nullcontext
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from .file_safety import (
    _require_no_linked_path_components,
    ensure_private_dir_required,
    write_text_atomic,
)
from .paths import data_dir
from .process_launch import popen_hidden
from .state_lock import FileLockTimeoutError, exclusive_file_lock

MAX_CRONTAB_BYTES = 1024 * 1024
CRON_START_TIMEOUT = 30.0
CRON_STOP_TIMEOUT = 8.0


def default_crontab_path() -> Path:
    return data_dir().resolve() / "servers" / "crontab"


def _field(text: str, low: int, high: int, names: tuple[str, ...] = ()) -> frozenset[int]:
    """Expand the numbers, names, lists, ranges and steps in one time field."""
    aliases = {name: i for i, name in enumerate(names, start=low)}

    def number(token: str) -> int:
        if token in aliases:
            return aliases[token]
        if not re.fullmatch("[0-9]+", token) or not low <= int(token) <= high:
            raise ValueError(f"expected a value between {low} and {high}")
        return int(token)

    result: set[int] = set()
    for term in text.lower().split(","):
        span, separator, stride = term.partition("/")
        if separator and not re.fullmatch("[1-9][0-9]*", stride):
            raise ValueError("step must be positive")
        step = int(stride) if separator else 1
        first, dash, last = span.partition("-")
        if span == "*":
            begin, end = low, high
        else:
            begin = number(first)
            end = number(last) if dash else begin
        # BusyBox cron permits ranges crossing Sunday or midnight. Sunday
        # has two numeric spellings, but consumes just one step in a range.
        values = list(range(begin, end + 1)) if begin <= end else [*range(begin, high + 1), *range(low, end + 1)]
        if names and low == 0:
            values = list(dict.fromkeys(n % 7 for n in values))
        result.update(values[::step])
    return frozenset(result)


@dataclass(frozen=True)
class CronEntry:
    minutes: frozenset[int]
    hours: frozenset[int]
    days: frozenset[int]
    months: frozenset[int]
    weekdays: frozenset[int]
    command: str

    def due(self, when: datetime) -> bool:
        day = when.day in self.days
        weekday = (when.weekday() + 1) % 7 in self.weekdays
        # A restricted weekday or month day applies on its own. Two
        # restricted fields select the union, as in a per-user crontab.
        dates_match = day or weekday if len(self.days) < 31 and len(self.weekdays) < 7 else day and weekday
        return when.minute in self.minutes and when.hour in self.hours and when.month in self.months and dates_match


def parse_crontab(text: str) -> list[CronEntry]:
    if len(text.encode("utf-8")) > MAX_CRONTAB_BYTES or "\x00" in text:
        raise ValueError("crontab must be UTF-8 text no larger than 1 MiB")
    entries: list[CronEntry] = []
    for index, line in enumerate(text.splitlines(), 1):
        line = line.lstrip()
        if not line or line.startswith("#"):
            continue
        try:
            minute, hour, day, month, weekday, command = line.split(None, 5)
            months = tuple("jan feb mar apr may jun jul aug sep oct nov dec".split())
            weekdays = tuple("sun mon tue wed thu fri sat".split())
            entries.append(CronEntry(
                _field(minute, 0, 59), _field(hour, 0, 23), _field(day, 1, 31),
                _field(month, 1, 12, months), _field(weekday, 0, 7, weekdays),
                command,
            ))
        except ValueError as exc:
            raise ValueError(f"invalid crontab line {index}: expected five time fields and a shell command") from exc
    return entries


def _read_text(path: Path) -> str:
    _require_no_linked_path_components(path)
    before = path.lstat()
    if not stat.S_ISREG(before.st_mode):
        raise ValueError(f"crontab must be a regular file: {path}")
    flags = os.O_RDONLY | getattr(os, "O_BINARY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_NONBLOCK", 0)
    with os.fdopen(os.open(path, flags), "rb") as stream:
        opened = os.fstat(stream.fileno())
        content = stream.read(MAX_CRONTAB_BYTES + 1)
    if len(content) > MAX_CRONTAB_BYTES:
        raise ValueError("crontab must be no larger than 1 MiB")
    after = path.lstat()
    if (not os.path.samestat(before, opened) or not os.path.samestat(opened, after)
            or before.st_mtime_ns != after.st_mtime_ns or len(content) != after.st_size):
        raise ValueError("crontab changed during read; retry after saving it")
    return content.decode("utf-8-sig")


def read_crontab_text() -> str:
    try:
        return _read_text(default_crontab_path())
    except FileNotFoundError:
        return ""


def save_crontab_text(text: str, *, expected: str) -> None:
    parse_crontab(text)
    path = default_crontab_path()
    ensure_private_dir_required(path.parent)
    with exclusive_file_lock(path, timeout_seconds=0.25):
        if read_crontab_text() != expected:
            raise ValueError("the crontab changed while it was open; reopen it before saving")
        write_text_atomic(path, text, private=True)


def prepare_crontab(path: Path) -> None:
    if path == default_crontab_path():
        _require_no_linked_path_components(path)
        ensure_private_dir_required(path.parent)
        # An editor can save concurrently. Exclusive creation keeps those bytes intact.
        try:
            os.close(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600))
        except FileExistsError:
            pass
    parse_crontab(_read_text(path))


def _job_argv(command: str) -> list[str] | str:
    if os.name != "nt":
        return ["/bin/sh", "-c", command]
    shell = shutil.which("sh")
    if shell:
        return [shell, "-c", command]
    # cmd.exe expects a raw tail following /S /C, not CRT argument escaping.
    cmd = os.environ.get("COMSPEC") or str(Path(os.environ["SystemRoot"]) / "System32" / "cmd.exe")
    return f'{subprocess.list2cmdline([cmd])} /d /s /c "{command}"'


def cron_phase(control: Path) -> str:
    try:
        # Windows readers can prevent atomic replacement while their handles
        # are open. Use the same lock for reads and generation transitions.
        with exclusive_file_lock(control, timeout_seconds=1.0):
            return _read_text(control)
    except (OSError, ValueError):
        return ""


def change_cron_phase(control: Path, generation: str, before: tuple[str, ...], after: str) -> bool:
    """Only the instance that owns this generation can acknowledge or revoke it."""
    with exclusive_file_lock(control):
        if before and cron_phase(control) not in {f"{phase} {generation}" for phase in before}:
            return False
        write_text_atomic(control, f"{after} {generation}", private=True)
        return True


def wait_for_cron_ready(control: Path, generation: str, process: subprocess.Popen[Any]) -> None:
    deadline = time.monotonic() + CRON_START_TIMEOUT
    while cron_phase(control) != f"ready {generation}":
        if process.poll() is not None or time.monotonic() >= deadline:
            raise ValueError("the Cron worker did not confirm startup")
        time.sleep(0.1)


def _activate_worker(control: Path, generation: str) -> bool:
    if not change_cron_phase(control, generation, ("pending",), "ready"):
        return False
    deadline = time.monotonic() + CRON_START_TIMEOUT
    while True:
        phase = cron_phase(control)
        if phase == f"active {generation}":
            return True
        # The parent's atomic replacement can change the file identity during
        # this read. An empty observation grants no authority; retry until the
        # original deadline. A different published phase ends activation.
        if phase not in ("", f"ready {generation}") or time.monotonic() >= deadline:
            return False
        time.sleep(0.1)


def uses_cron_worker_lease() -> bool:
    # Windows and Linux can verify the birth identity across CLI invocations.
    return os.name == "posix" and not sys.platform.startswith("linux")


def cron_worker_lease_held(control: Path, generation: str) -> bool:
    if cron_phase(control) not in {f"{phase} {generation}" for phase in ("pending", "ready", "active", "revoked")}:
        return False
    try:
        with exclusive_file_lock(control.with_suffix(".worker"), timeout_seconds=0.01):
            return False
    except FileLockTimeoutError:
        return True


def run_cron(path: Path) -> None:
    parse_crontab(_read_text(path))
    control_env = os.environ.pop("ROW_CRON_CONTROL_FILE", "")
    generation = os.environ.pop("ROW_CRON_GENERATION", "")
    control = Path(control_env) if control_env else None
    # On owned-only POSIX systems another invocation cannot inspect the
    # starter's Popen. The kernel releases this lease even after a crash.
    worker_lock = exclusive_file_lock(control.with_suffix(".worker")) if control and uses_cron_worker_lease() else nullcontext()
    with worker_lock:
        _run_schedule(path, control, generation)


def _run_schedule(path: Path, control: Path | None, generation: str) -> None:
    if control is not None and not _activate_worker(control, generation):
        return
    active: dict[tuple[int, CronEntry], subprocess.Popen[Any]] = {}
    previous_minute = int(time.time() // 60)
    while control is None or cron_phase(control) == f"active {generation}":
        now = time.time()
        minute = int(now // 60)
        if minute != previous_minute:
            previous_minute = minute
            when = datetime.fromtimestamp(now)
            active = {key: child for key, child in active.items() if child.poll() is None}
            try:
                entries = parse_crontab(_read_text(path))
            except (OSError, ValueError):
                # An external editor may be partway through a save. Skip the
                # whole minute and retry; a valid prefix must never run alone.
                entries = []
            for index, entry in enumerate(entries):
                key = index, entry
                if entry.due(when) and key not in active:
                    if control is not None and cron_phase(control) != f"active {generation}":
                        return
                    active[key] = popen_hidden(_job_argv(entry.command), cwd=Path.home(),
                                               stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        pause = 0.25 if control is not None else 60
        time.sleep(min(pause, max(0, (minute + 1) * 60 - time.time())))

from __future__ import annotations

import shlex
import subprocess
from dataclasses import dataclass

from . import command_safety as safe
from .launcher import build_launch_plan
from .models import Profile


@dataclass(slots=True)
class BroadcastPlan:
    profile_name: str
    command: list[str]
    notes: list[str]

    def printable(self) -> str:
        return shlex.join(self.command)


@dataclass(slots=True)
class BroadcastResult:
    profile_name: str
    command: list[str]
    returncode: int | None
    stdout: str = ""
    stderr: str = ""
    dry_run: bool = False

    @property
    def ok(self) -> bool:
        return self.dry_run or self.returncode == 0

    def to_dict(self) -> dict[str, object]:
        return {
            "profile": self.profile_name,
            "command": self.command,
            "returncode": self.returncode,
            "stdout": self.stdout,
            "stderr": self.stderr,
            "dry_run": self.dry_run,
            "ok": self.ok,
        }


def build_broadcast_plans(profiles: list[Profile], command: str) -> list[BroadcastPlan]:
    remote_command = safe.shellish_text(command, "broadcast command")
    plans: list[BroadcastPlan] = []
    for profile in profiles:
        if profile.protocol != "ssh":
            raise ValueError(f"broadcast currently supports ssh profiles only: {profile.name}")
        plan = build_launch_plan(profile)
        plans.append(
            BroadcastPlan(
                profile_name=profile.name,
                command=[*plan.command, remote_command],
                notes=[*plan.notes, f"Broadcast command for profile: {profile.name}"],
            )
        )
    return plans


def run_broadcast(
    plans: list[BroadcastPlan],
    dry_run: bool = False,
    *,
    timeout: float | None = None,
) -> list[BroadcastResult]:
    results: list[BroadcastResult] = []
    for plan in plans:
        safe.argv_list(plan.command, "broadcast command")
        if dry_run:
            results.append(BroadcastResult(plan.profile_name, plan.command, None, dry_run=True))
            continue
        try:
            completed = subprocess.run(
                plan.command,
                check=False,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            results.append(
                BroadcastResult(
                    profile_name=plan.profile_name,
                    command=plan.command,
                    returncode=completed.returncode,
                    stdout=completed.stdout,
                    stderr=completed.stderr,
                )
            )
        except subprocess.TimeoutExpired as exc:
            results.append(
                BroadcastResult(
                    profile_name=plan.profile_name,
                    command=plan.command,
                    returncode=124,
                    stdout=exc.stdout or "",
                    stderr=exc.stderr or f"timed out after {timeout} seconds",
                )
            )
    return results

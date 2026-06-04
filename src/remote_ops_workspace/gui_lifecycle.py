from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ProcessStopPolicy:
    terminate_timeout_ms: int = 1500
    kill_timeout_ms: int = 500

    def __post_init__(self) -> None:
        if self.terminate_timeout_ms < 0:
            raise ValueError("terminate timeout must not be negative")
        if self.kill_timeout_ms < 0:
            raise ValueError("kill timeout must not be negative")


@dataclass(frozen=True, slots=True)
class ProcessStopResult:
    was_running: bool
    terminate_requested: bool
    kill_requested: bool
    finished: bool


DEFAULT_PROCESS_STOP_POLICY = ProcessStopPolicy()


def is_process_running(process: Any, *, not_running_state: object) -> bool:
    return process.state() != not_running_state


def stop_process(
    process: Any,
    *,
    not_running_state: object,
    policy: ProcessStopPolicy = DEFAULT_PROCESS_STOP_POLICY,
) -> ProcessStopResult:
    if not is_process_running(process, not_running_state=not_running_state):
        return ProcessStopResult(
            was_running=False,
            terminate_requested=False,
            kill_requested=False,
            finished=True,
        )

    process.terminate()
    if process.waitForFinished(policy.terminate_timeout_ms):
        return ProcessStopResult(
            was_running=True,
            terminate_requested=True,
            kill_requested=False,
            finished=True,
        )

    process.kill()
    return ProcessStopResult(
        was_running=True,
        terminate_requested=True,
        kill_requested=True,
        finished=bool(process.waitForFinished(policy.kill_timeout_ms)),
    )

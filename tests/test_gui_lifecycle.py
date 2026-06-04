from remote_ops_workspace.gui_lifecycle import ProcessStopPolicy, is_process_running, stop_process

NOT_RUNNING = "not-running"
RUNNING = "running"


class FakeProcess:
    def __init__(
        self,
        *,
        running: bool = True,
        finish_after_terminate: bool = True,
        finish_after_kill: bool = True,
    ) -> None:
        self._state = RUNNING if running else NOT_RUNNING
        self.finish_after_terminate = finish_after_terminate
        self.finish_after_kill = finish_after_kill
        self.terminated = False
        self.killed = False
        self.waits: list[int] = []

    def state(self) -> str:
        return self._state

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True

    def waitForFinished(self, timeout_ms: int) -> bool:
        self.waits.append(timeout_ms)
        if self.terminated and not self.killed and self.finish_after_terminate:
            self._state = NOT_RUNNING
            return True
        if self.killed and self.finish_after_kill:
            self._state = NOT_RUNNING
            return True
        return False


def test_stop_process_is_noop_for_idle_process() -> None:
    process = FakeProcess(running=False)

    result = stop_process(process, not_running_state=NOT_RUNNING)

    assert is_process_running(process, not_running_state=NOT_RUNNING) is False
    assert result.was_running is False
    assert result.finished is True
    assert process.terminated is False
    assert process.killed is False
    assert process.waits == []


def test_stop_process_terminates_gracefully_before_kill() -> None:
    process = FakeProcess(finish_after_terminate=True)

    result = stop_process(
        process,
        not_running_state=NOT_RUNNING,
        policy=ProcessStopPolicy(terminate_timeout_ms=123, kill_timeout_ms=456),
    )

    assert result.was_running is True
    assert result.terminate_requested is True
    assert result.kill_requested is False
    assert result.finished is True
    assert process.terminated is True
    assert process.killed is False
    assert process.waits == [123]


def test_stop_process_kills_after_terminate_timeout() -> None:
    process = FakeProcess(finish_after_terminate=False, finish_after_kill=True)

    result = stop_process(
        process,
        not_running_state=NOT_RUNNING,
        policy=ProcessStopPolicy(terminate_timeout_ms=123, kill_timeout_ms=456),
    )

    assert result.was_running is True
    assert result.terminate_requested is True
    assert result.kill_requested is True
    assert result.finished is True
    assert process.terminated is True
    assert process.killed is True
    assert process.waits == [123, 456]


def test_stop_process_reports_unfinished_after_kill_timeout() -> None:
    process = FakeProcess(finish_after_terminate=False, finish_after_kill=False)

    result = stop_process(
        process,
        not_running_state=NOT_RUNNING,
        policy=ProcessStopPolicy(terminate_timeout_ms=123, kill_timeout_ms=456),
    )

    assert result.kill_requested is True
    assert result.finished is False
    assert process.waits == [123, 456]


def test_stop_policy_rejects_negative_timeouts() -> None:
    for kwargs in [{"terminate_timeout_ms": -1}, {"kill_timeout_ms": -1}]:
        try:
            ProcessStopPolicy(**kwargs)
        except ValueError as exc:
            assert "timeout" in str(exc)
        else:
            raise AssertionError("negative GUI process timeouts should be rejected")

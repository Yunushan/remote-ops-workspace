import threading
from types import SimpleNamespace

import pytest
from windows_window_observer import (
    RetainedWindowRoots,
    VisibleWindowSampler,
    WindowObservationError,
    birth_consistent_chain,
    close_cells,
)


def test_observed_old_agent_numeric_chain_is_not_a_descendant():
    parents = {884: 2600, 2600: 988, 988: 876, 876: 760}
    births = {884: 400, 2600: 300, 988: 200, 876: 100, 760: 1000, 7956: 1100}
    plausible, chain, reason = birth_consistent_chain(884, parents, {760: 1000, 7956: 1100}, births.__getitem__)
    assert not plausible and reason == "predates-all-retained-roots"
    assert chain == [{"pid": 884, "creation_time": 400}]


@pytest.mark.parametrize("owner,parents,births", [
    (760, {}, {760: 1000}),
    (800, {800: 760}, {760: 1000, 800: 1200}),
    (900, {900: 800, 800: 760}, {760: 1000, 800: 1200, 900: 1400}),
])
def test_root_and_plausible_children_remain_visible_candidates(owner, parents, births):
    plausible, chain, reason = birth_consistent_chain(owner, parents, {760: 1000}, births.__getitem__)
    assert plausible and reason == "birth-consistent-numeric-candidate"
    assert chain[-1] == {"pid": 760, "creation_time": 1000}


def test_new_owner_does_not_hide_an_old_intermediate():
    plausible, chain, reason = birth_consistent_chain(
        900, {900: 876, 876: 760}, {760: 1000}, {900: 1400, 876: 100, 760: 1000}.__getitem__,
    )
    assert not plausible and reason == "predates-all-retained-roots"
    assert chain[-1]["pid"] == 876


def test_parent_born_after_child_is_rejected_with_both_identities():
    plausible, chain, reason = birth_consistent_chain(
        900, {900: 760}, {760: 1100, 7956: 900}, {900: 1000, 760: 1100}.__getitem__,
    )
    assert not plausible and reason == "parent-created-after-child"
    assert [row["creation_time"] for row in chain] == [1000, 1100]


@pytest.mark.parametrize("birth", [0, -1, None, True, 1.5])
def test_unknown_birth_is_an_error(birth):
    with pytest.raises(WindowObservationError, match="unavailable-process-birth"):
        birth_consistent_chain(900, {900: 760}, {760: 1000}, lambda _pid: birth)


@pytest.mark.parametrize("owner", [760, 900])
def test_replaced_root_is_an_error_even_when_edge_is_contradictory(owner):
    with pytest.raises(WindowObservationError, match="root-identity-drift"):
        birth_consistent_chain(owner, {900: 760}, {760: 1000}, {760: 2000, 900: 1400}.__getitem__)


def test_equal_birth_time_is_unqualified():
    with pytest.raises(WindowObservationError, match="ambiguous-equal-birth-times"):
        birth_consistent_chain(900, {900: 760}, {760: 1000}, lambda _pid: 1000)


def test_denied_query_propagates_and_never_becomes_empty_success():
    def denied(_pid):
        raise PermissionError("mock-query-denied")
    with pytest.raises(PermissionError, match="mock-query-denied"):
        birth_consistent_chain(900, {900: 760}, {760: 1000}, denied)


def test_missing_parent_is_unqualified():
    with pytest.raises(WindowObservationError, match="ancestry-incomplete"):
        birth_consistent_chain(900, {}, {760: 1000}, lambda _pid: 1400)


def test_cycle_is_unqualified():
    with pytest.raises(WindowObservationError, match="ancestry-cycle-or-invalid-pid"):
        birth_consistent_chain(900, {900: 900}, {760: 1000}, lambda _pid: 1400)


def test_depth_bound_is_unqualified():
    parents = {pid: pid - 1 for pid in range(100, 200)}
    with pytest.raises(WindowObservationError, match="ancestry-depth-bound"):
        birth_consistent_chain(199, parents, {1: 1}, lambda pid: pid)


class FakeAPI:
    def __init__(self):
        self.births = {760: 1000, 7956: 1100}
        self.duplicates = []
        self.closed = []
        self.fail_duplicate = None
        self.fail_identity = None
        self.close_failures = {}

    @staticmethod
    def cell():
        return SimpleNamespace(value=None)

    def duplicate_into(self, source, destination):
        destination.value = source.value
        self.duplicates.append(source.value)
        if source.value == self.fail_duplicate:
            raise OSError("mock-partial-duplicate")

    def identity(self, handle, expected_pid):
        if expected_pid == self.fail_identity:
            raise ProcessLookupError("mock-vanished-process")
        assert handle.value == expected_pid
        return self.births[expected_pid]

    def close(self, cell):
        self.closed.append(cell.value)
        if cell.value in self.close_failures:
            raise self.close_failures[cell.value]
        cell.value = None


def sessions():
    return [SimpleNamespace(pid=pid, _process_handle=SimpleNamespace(value=pid), _lifecycle_lock=threading.RLock()) for pid in (760, 7956)]


def test_roots_duplicate_original_handles_and_keep_expected_births():
    api = FakeAPI()
    roots = RetainedWindowRoots(sessions(), _api=api)
    assert api.duplicates == [760, 7956]
    assert roots.verify({760, 7956}) == {760: 1000, 7956: 1100}
    roots.close()
    assert api.closed == [7956, 760]
    roots.close()
    assert api.closed == [7956, 760]


@pytest.mark.parametrize("phase,pid,expected", [
    ("duplicate", 760, [760]), ("duplicate", 7956, [7956, 760]),
    ("identity", 760, [760]), ("identity", 7956, [7956, 760]),
])
def test_partial_acquisition_attempts_every_registered_close(phase, pid, expected):
    api = FakeAPI()
    setattr(api, "fail_" + phase, pid)
    with pytest.raises((OSError, ProcessLookupError)):
        RetainedWindowRoots(sessions(), _api=api)
    assert api.closed == expected


@pytest.mark.parametrize("failure_type", [KeyboardInterrupt, SystemExit, MemoryError, OSError])
def test_close_failure_preserves_remaining_attempts_and_first_cause(failure_type):
    api = FakeAPI()
    first = failure_type("mock-first-close")
    api.close_failures = {7956: first, 760: OSError("mock-later-close")}
    roots = RetainedWindowRoots(sessions(), _api=api)
    with pytest.raises(WindowObservationError, match="window-observer-cleanup-refused") as caught:
        roots.close()
    assert api.closed == [7956, 760] and caught.value.__cause__ is first
    with pytest.raises(WindowObservationError, match="window-observer-cleanup-refused"):
        roots.close()
    assert api.closed == [7956, 760]


@pytest.mark.parametrize("change", ["birth", "session", "requested", "vanished"])
def test_identity_drift_or_vanished_root_refuses(change):
    api = FakeAPI()
    roots = RetainedWindowRoots(sessions(), _api=api)
    requested = {760, 7956}
    if change == "birth":
        api.births[760] = 2000
    elif change == "session":
        roots.rows[0][0].pid = 8000
    elif change == "requested":
        requested = {760}
    else:
        api.fail_identity = 760
    with pytest.raises((WindowObservationError, ProcessLookupError)):
        roots.verify(requested)
    roots.close()
    assert api.closed == [7956, 760]


def test_live_sampler_borrower_prevents_root_handle_close():
    api = FakeAPI()
    roots = RetainedWindowRoots(sessions(), _api=api)
    borrower = SimpleNamespace(is_alive=lambda: True)
    roots.register_thread(borrower)
    with pytest.raises(WindowObservationError, match="live-sampler-borrower"):
        roots.close()
    assert api.closed == []
    borrower.is_alive = lambda: False
    roots.close()
    assert api.closed == [7956, 760]


def test_rejected_chains_are_deduplicated_and_bounded():
    roots = RetainedWindowRoots(sessions(), _api=FakeAPI())
    for pid in range(64):
        chain = [{"pid": pid, "creation_time": pid + 1}]
        roots.reject(chain, "mock-old-owner")
        roots.reject(chain, "mock-old-owner")
    assert len(roots.rejected) == 64
    with pytest.raises(WindowObservationError, match="rejected-chain-bound"):
        roots.reject([{"pid": 100, "creation_time": 100}], "mock-old-owner")
    roots.close()


def test_close_cells_skips_unacquired_slots():
    api = FakeAPI()
    cells = [SimpleNamespace(value=None), SimpleNamespace(value=760)]
    close_cells(api, reversed(cells))
    assert api.closed == [760]


def test_sampler_requires_observation_and_completed_phase():
    roots = RetainedWindowRoots(sessions(), _api=FakeAPI())
    with VisibleWindowSampler({760, 7956}, roots, _observe=lambda *_: []) as sampler:
        assert sampler.samples and not sampler.completed
    assert sampler.completed and sampler.failure is None
    roots.close()


@pytest.mark.parametrize("failure_type", [PermissionError, MemoryError, KeyboardInterrupt])
def test_sampler_observation_failure_is_sticky_before_phase_start(failure_type):
    failure = failure_type("mock-observer-failure")
    def observe(*_):
        raise failure
    roots = RetainedWindowRoots(sessions(), _api=FakeAPI())
    sampler = VisibleWindowSampler({760, 7956}, roots, _observe=observe)
    with pytest.raises(WindowObservationError, match="window-sampler-failed") as caught:
        with sampler:
            pytest.fail("failed sampler entered the native event phase")
    assert caught.value.__cause__ is failure and sampler.failure is failure
    assert not sampler.completed
    roots.close()


def test_sampler_publication_failure_cannot_be_an_empty_success():
    class RefusePublication(list):
        def append(self, _record):
            raise MemoryError("mock-sample-publication")
    roots = RetainedWindowRoots(sessions(), _api=FakeAPI())
    sampler = VisibleWindowSampler({760, 7956}, roots, _observe=lambda *_: [])
    sampler.samples = RefusePublication()
    with pytest.raises(WindowObservationError, match="window-sampler-failed"):
        with sampler:
            pytest.fail("missing sample publication was accepted")
    assert isinstance(sampler.failure, MemoryError) and not sampler.completed
    roots.close()


def test_sampler_unformattable_failure_still_refuses():
    class UnformattableError(RuntimeError):
        def __str__(self):
            raise MemoryError("mock-diagnostic-allocation")
    failure = UnformattableError()
    def observe(*_):
        raise failure
    roots = RetainedWindowRoots(sessions(), _api=FakeAPI())
    sampler = VisibleWindowSampler({760, 7956}, roots, _observe=observe)
    with pytest.raises(WindowObservationError, match="window-sampler-failed") as caught:
        with sampler:
            pytest.fail("diagnostic failure erased observation failure")
    assert caught.value.__cause__ is failure and sampler.failure is failure
    assert sampler.errors == [] and not sampler.completed
    roots.close()


def test_sampler_failure_after_start_cannot_complete_phase():
    fail = threading.Event()
    failure = PermissionError("mock-later-observation")
    def observe(*_):
        if fail.is_set():
            raise failure
        return []
    roots = RetainedWindowRoots(sessions(), _api=FakeAPI())
    sampler = VisibleWindowSampler({760, 7956}, roots, _observe=observe)
    with pytest.raises(WindowObservationError, match="window-sampler-failed"):
        with sampler:
            fail.set()
            assert sampler._finished.wait(1.0)
    assert sampler.samples and sampler.failure is failure and not sampler.completed
    roots.close()


def test_sampler_startup_refusal_stops_and_joins_registered_worker():
    api = FakeAPI()
    roots = RetainedWindowRoots(sessions(), _api=api)
    sampler = VisibleWindowSampler({760, 7956}, roots, _observe=lambda *_: [])
    # Inject a timeout result rather than relying on millisecond scheduling.
    # The real registered worker must still stop before retained roots close.
    sampler._ready = SimpleNamespace(wait=lambda _timeout: False, set=lambda: None)
    with pytest.raises(WindowObservationError, match="window-sampler-startup-timeout"):
        with sampler:
            pytest.fail("observation startup timeout was accepted")
    assert not sampler.completed and not roots._threads[0].is_alive()
    roots.close()
    assert api.closed == [7956, 760]

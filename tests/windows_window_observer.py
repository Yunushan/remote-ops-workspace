"""Bounded test-only Windows window observation with retained process roots.

Birth ordering rejects impossible numeric ancestry. It does not turn a Toolhelp
parent PID into a complete, historical process-parent identity proof.
Creation times are wall-clock values: temporal rejection assumes a stable host
clock and does not qualify ancestry across clock adjustments.
"""
from __future__ import annotations

import ctypes
import sys
import threading
import time
from collections.abc import Callable
from ctypes import wintypes
from typing import Any


class WindowObservationError(RuntimeError):
    pass


def birth_consistent_chain(
    owner: int, parents: dict[int, int], roots: dict[int, int],
    read_birth: Callable[[int], int],
) -> tuple[bool, list[dict[str, int]], str]:
    """Conservatively retain plausible chains; reject only impossible ones."""
    if not roots or len(roots) > 16 or any(type(pid) is not int or type(birth) is not int or pid <= 0 or birth <= 0 for pid, birth in roots.items()):
        raise WindowObservationError("invalid-retained-roots")
    chain: list[dict[str, int]] = []
    visited: set[int] = set()
    pid = owner
    for _ in range(64):
        if pid <= 0 or pid in visited:
            raise WindowObservationError("ancestry-cycle-or-invalid-pid")
        visited.add(pid)
        birth = read_birth(pid)
        if type(birth) is not int or birth <= 0:
            raise WindowObservationError("unavailable-process-birth")
        chain.append({"pid": pid, "creation_time": birth})
        if pid in roots:
            if birth != roots[pid]:
                raise WindowObservationError("root-identity-drift")
            return True, chain, "birth-consistent-numeric-candidate"
        if birth < min(roots.values()):
            return False, chain, "predates-all-retained-roots"
        parent = parents.get(pid)
        if parent is None or parent <= 0:
            raise WindowObservationError("ancestry-incomplete")
        if parent in visited:
            raise WindowObservationError("ancestry-cycle-or-invalid-pid")
        parent_birth = read_birth(parent)
        if type(parent_birth) is not int or parent_birth <= 0:
            raise WindowObservationError("unavailable-parent-birth")
        if parent in roots and parent_birth != roots[parent]:
            raise WindowObservationError("root-identity-drift")
        if parent_birth > birth:
            chain.append({"pid": parent, "creation_time": parent_birth})
            return False, chain, "parent-created-after-child"
        if parent_birth == birth:
            raise WindowObservationError("ambiguous-equal-birth-times")
        pid = parent
    raise WindowObservationError("ancestry-depth-bound")


def close_cells(api: Any, closing: Any) -> None:
    """One attempt per registered cell; failed closure remains an error."""
    failure = None
    for cell in closing:
        if not cell.value:
            continue
        try:
            api.close(cell)
        except BaseException as error:
            if failure is None:
                failure = error
    if failure is not None:
        raise WindowObservationError("window-observer-cleanup-refused") from failure


class WindowsProcessAPI:
    def __init__(self) -> None:
        if sys.platform != "win32":
            raise WindowObservationError("windows-observation-required")
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        prototypes = {
            "GetCurrentProcess": ([], wintypes.HANDLE),
            "GetCurrentProcessId": ([], wintypes.DWORD),
            "GetProcessId": ([wintypes.HANDLE], wintypes.DWORD),
            "DuplicateHandle": ([wintypes.HANDLE, wintypes.HANDLE, wintypes.HANDLE,
                                 ctypes.POINTER(wintypes.HANDLE), wintypes.DWORD,
                                 wintypes.BOOL, wintypes.DWORD], wintypes.BOOL),
            "OpenProcess": ([wintypes.DWORD, wintypes.BOOL, wintypes.DWORD], wintypes.HANDLE),
            "GetProcessTimes": ([wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4, wintypes.BOOL),
            "WaitForSingleObject": ([wintypes.HANDLE, wintypes.DWORD], wintypes.DWORD),
            "CloseHandle": ([wintypes.HANDLE], wintypes.BOOL),
        }
        for name, (arguments, result) in prototypes.items():
            function = getattr(self.kernel, name)
            function.argtypes, function.restype = arguments, result

    @staticmethod
    def cell() -> Any:
        return wintypes.HANDLE()

    def duplicate_into(self, source: Any, destination: Any) -> None:
        current = self.kernel.GetCurrentProcess()
        # Query and synchronization only, noninheritable, no close-source option.
        if not self.kernel.DuplicateHandle(current, source, current, ctypes.byref(destination), 0x101000, False, 0):
            raise ctypes.WinError(ctypes.get_last_error())

    def open_into(self, pid: int, destination: Any) -> None:
        destination.value = self.kernel.OpenProcess(0x101000, False, pid)
        if not destination.value:
            raise ctypes.WinError(ctypes.get_last_error())

    def identity(self, handle: Any, expected_pid: int) -> int:
        if int(self.kernel.GetProcessId(handle)) != expected_pid:
            raise WindowObservationError("process-handle-pid-mismatch")
        if int(self.kernel.WaitForSingleObject(handle, 0)) != 258:
            raise WindowObservationError("process-not-provably-live")
        times = [wintypes.FILETIME() for _ in range(4)]
        if not self.kernel.GetProcessTimes(handle, *(ctypes.byref(item) for item in times)):
            raise ctypes.WinError(ctypes.get_last_error())
        birth = (int(times[0].dwHighDateTime) << 32) | int(times[0].dwLowDateTime)
        if birth <= 0:
            raise WindowObservationError("unavailable-process-birth")
        return birth

    def close(self, cell: Any) -> None:
        if not self.kernel.CloseHandle(cell):
            raise ctypes.WinError(ctypes.get_last_error())
        cell.value = None


class RetainedWindowRoots:
    """Duplicate actual ConPTY-created handles under their lifecycle locks."""
    def __init__(self, sessions: list[Any], *, _api: Any = None) -> None:
        if not 1 <= len(sessions) <= 16:
            raise WindowObservationError("root-count-bound")
        self.api = WindowsProcessAPI() if _api is None else _api
        self.rows = [[session, self.api.cell(), None, None] for session in sessions]
        self._threads: list[threading.Thread] = []
        self.observation_lock = threading.RLock()
        self._close_failure: BaseException | None = None
        self.rejected: list[dict[str, object]] = []
        self._rejection_keys: set[tuple[object, ...]] = set()
        self._closing = reversed([row[1] for row in self.rows])
        try:
            for row in self.rows:
                session = row[0]
                with session._lifecycle_lock:
                    row[2] = int(session.pid or 0)
                    if row[2] <= 0:
                        raise WindowObservationError("missing-conpty-process")
                    self.api.duplicate_into(session._process_handle, row[1])
                    row[3] = self.api.identity(row[1], row[2])
                    if type(row[3]) is not int or row[3] <= 0:
                        raise WindowObservationError("unavailable-process-birth")
            if len({row[2] for row in self.rows}) != len(self.rows):
                raise WindowObservationError("duplicate-root-pid")
        except BaseException:
            close_cells(self.api, self._closing)
            raise

    def verify(self, process_ids: set[int]) -> dict[int, int]:
        roots = {row[2]: row[3] for row in self.rows}
        if process_ids != set(roots):
            raise WindowObservationError("requested-root-set-drift")
        for row in self.rows:
            if not row[1].value or self.api.identity(row[1], row[2]) != row[3]:
                raise WindowObservationError("root-identity-drift")
            if int(row[0].pid or 0) != row[2]:
                raise WindowObservationError("conpty-session-pid-drift")
        return roots

    def register_thread(self, thread: threading.Thread) -> None:
        if len(self._threads) >= 128:
            raise WindowObservationError("sampler-thread-bound")
        self._threads.append(thread)

    def reject(self, chain: list[dict[str, int]], reason: str) -> None:
        key = (reason, *(tuple(row.items()) for row in chain))
        if key in self._rejection_keys:
            return
        if len(self.rejected) >= 64:
            raise WindowObservationError("rejected-chain-bound")
        self._rejection_keys.add(key)
        self.rejected.append({"reason": reason, "chain": chain})

    def close(self) -> None:
        if self._close_failure is not None:
            raise WindowObservationError("window-observer-cleanup-refused") from self._close_failure
        if any(thread.is_alive() for thread in self._threads):
            # A timed-out borrower is an error; hosted disposal retains custody.
            raise WindowObservationError("live-sampler-borrower")
        try:
            close_cells(self.api, self._closing)
        except BaseException as error:
            self._close_failure = error
            raise


class VisibleWindowSampler:
    """Bounded sampler with a recorded startup sample and sticky failures.

    Startup is sampled before the event; later observations remain discrete,
    not a proof that no surface can appear between observations.
    """
    def __init__(self, process_ids: set[int], roots: RetainedWindowRoots, *,
                 interval_seconds: float = 0.004, _observe: Any = None,
                 _startup_timeout: float = 1.0) -> None:
        self.process_ids = set(process_ids)
        self.roots = roots
        self.interval_seconds = max(0.001, float(interval_seconds))
        self._startup_timeout = float(_startup_timeout)
        if not 0 < self._startup_timeout <= 5.0:
            raise WindowObservationError("sampler-startup-timeout-bound")
        self._observe = visible_windows if _observe is None else _observe
        self.samples: list[dict[str, object]] = []
        self.errors: list[str] = []
        self.failure: BaseException | None = None
        self.completed = False
        self._stop = threading.Event()
        self._ready = threading.Event()
        self._finished = threading.Event()
        self._started_at = 0.0
        self._thread: threading.Thread | None = None

    def _stop_and_join(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=1.0)
            if self._thread.is_alive():
                raise WindowObservationError("window-sampler-did-not-stop")

    def __enter__(self) -> VisibleWindowSampler:
        self._started_at = time.monotonic()
        self._thread = threading.Thread(target=self._run,
                                       name="remote-ops-visible-window-sampler",
                                       daemon=True)
        self.roots.verify(self.process_ids)
        self.roots.register_thread(self._thread)
        try:
            self._thread.start()
            if not self._ready.wait(self._startup_timeout):
                raise WindowObservationError("window-sampler-startup-timeout")
            if self.failure is not None:
                raise WindowObservationError("window-sampler-failed") from self.failure
            if not self.samples:
                raise WindowObservationError("window-sampler-startup-empty")
        except BaseException:
            self._stop.set()
            if self._thread.ident is not None:
                self._stop_and_join()
            raise
        return self

    def __exit__(self, _exc_type, _exc_value, _traceback) -> None:
        self._stop_and_join()
        if not self._finished.is_set():
            raise WindowObservationError("window-sampler-completion-unavailable")
        if self.failure is not None:
            raise WindowObservationError("window-sampler-failed") from self.failure
        if not self.samples:
            raise WindowObservationError("window-sampler-phase-empty")
        self.completed = True

    def _run(self) -> None:
        try:
            while not self._stop.wait(self.interval_seconds):
                if len(self.samples) >= 8192:
                    raise WindowObservationError("window-sample-bound")
                visible = self._observe(self.process_ids, self.roots)
                self.samples.append({
                    "elapsed_ms": round((time.monotonic() - self._started_at) * 1000, 3),
                    "visible_child_windows": visible,
                })
                self._ready.set()
        except BaseException as exc:
            # Set the acceptance fact before formatting or allocating diagnostics.
            self.failure = exc
            try:
                self.errors.append(str(exc))
            except BaseException:
                pass
        finally:
            self._ready.set()
            self._finished.set()

    @property
    def violations(self) -> list[dict[str, object]]:
        return [sample for sample in self.samples if sample["visible_child_windows"]]


def visible_windows(process_ids: set[int], roots: RetainedWindowRoots) -> list[dict[str, object]]:
    # Shared DLL prototypes and rejection diagnostics are serialized between
    # the Qt thread and the continuous sampler. No hostile caller is supported.
    with roots.observation_lock:
        return _visible_windows_locked(process_ids, roots)


def _visible_windows_locked(process_ids: set[int], roots: RetainedWindowRoots) -> list[dict[str, object]]:
    root_births = roots.verify(process_ids)
    api, kernel, user = roots.api, roots.api.kernel, roots.api.user

    class ProcessEntry(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", wintypes.WCHAR * 260)]

    kernel.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    kernel.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    for name in ("Process32FirstW", "Process32NextW"):
        function = getattr(kernel, name)
        function.argtypes, function.restype = [wintypes.HANDLE, ctypes.POINTER(ProcessEntry)], wintypes.BOOL
    snapshot = api.cell()
    entry = ProcessEntry()
    entry.dwSize = ctypes.sizeof(entry)
    parents: dict[int, int] = {}
    images: dict[int, str] = {}
    closing_snapshot = iter([snapshot])
    snapshot.value = kernel.CreateToolhelp32Snapshot(2, 0)
    if not snapshot.value or snapshot.value == ctypes.c_void_p(-1).value:
        snapshot.value = None
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        more = kernel.Process32FirstW(snapshot, ctypes.byref(entry))
        while more:
            pid = int(entry.th32ProcessID)
            if len(parents) >= 4096 or pid in parents:
                raise WindowObservationError("process-snapshot-bound-or-duplicate")
            parents[pid], images[pid] = int(entry.th32ParentProcessID), str(entry.szExeFile)
            more = kernel.Process32NextW(snapshot, ctypes.byref(entry))
        if ctypes.get_last_error() != 18:
            raise WindowObservationError("incomplete-process-snapshot")
    finally:
        close_cells(api, closing_snapshot)

    if not process_ids.issubset(parents):
        raise WindowObservationError("retained-root-missing-from-snapshot")

    tracked = set(process_ids)
    for _ in range(64):
        expanded = tracked | {child for child, parent in parents.items() if parent in tracked}
        if len(expanded) > 256:
            raise WindowObservationError("numeric-candidate-bound")
        if expanded == tracked:
            break
        tracked = expanded
    else:
        raise WindowObservationError("numeric-candidate-depth-bound")
    cells = {pid: [api.cell(), None] for pid in sorted(tracked - process_ids)}
    closing = reversed([row[0] for row in cells.values()])
    root_rows = {row[2]: row for row in roots.rows}

    def read_birth(pid: int) -> int:
        if pid in root_rows:
            row = root_rows[pid]
            birth = api.identity(row[1], pid)
            if birth != row[3]:
                raise WindowObservationError("root-identity-drift")
            return birth
        row = cells.get(pid)
        if row is None:
            raise WindowObservationError("parent-outside-numeric-candidates")
        if not row[0].value:
            api.open_into(pid, row[0])
            row[1] = api.identity(row[0], pid)
        return row[1]

    user.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    user.GetWindowThreadProcessId.restype = wintypes.DWORD
    user.IsWindowVisible.argtypes, user.IsWindowVisible.restype = [wintypes.HWND], wintypes.BOOL
    user.GetWindowRect.argtypes, user.GetWindowRect.restype = [wintypes.HWND, ctypes.POINTER(wintypes.RECT)], wintypes.BOOL
    user.GetWindowTextLengthW.argtypes, user.GetWindowTextLengthW.restype = [wintypes.HWND], ctypes.c_int
    user.GetWindowTextW.argtypes, user.GetWindowTextW.restype = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int
    user.GetClassNameW.argtypes, user.GetClassNameW.restype = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int], ctypes.c_int
    callback_type = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    records: list[dict[str, object]] = []
    observed_owners: dict[int, int] = {}
    callback_failure: list[BaseException | None] = [None]

    @callback_type
    def visit(hwnd: Any, _lparam: Any) -> bool:
        try:
            if not user.IsWindowVisible(hwnd):
                return True
            owner = wintypes.DWORD()
            if not user.GetWindowThreadProcessId(hwnd, ctypes.byref(owner)):
                raise WindowObservationError("window-owner-unavailable")
            pid = int(owner.value)
            if pid not in tracked:
                return True
            rect = wintypes.RECT()
            if not user.GetWindowRect(hwnd, ctypes.byref(rect)):
                raise WindowObservationError("window-rectangle-unavailable")
            if rect.right <= rect.left or rect.bottom <= rect.top:
                return True
            observed_owners[int(getattr(hwnd, "value", hwnd) or 0)] = pid
            plausible, chain, reason = birth_consistent_chain(pid, parents, root_births, read_birth)
            if not plausible:
                roots.reject(chain, reason)
                return True
            length = user.GetWindowTextLengthW(hwnd)
            if not 0 <= length <= 4096:
                raise WindowObservationError("window-title-bound")
            title = ctypes.create_unicode_buffer(length + 1)
            user.GetWindowTextW(hwnd, title, len(title))
            window_class = ctypes.create_unicode_buffer(256)
            if not user.GetClassNameW(hwnd, window_class, len(window_class)):
                raise WindowObservationError("window-class-unavailable")
            compact = "".join(c.casefold() for c in f"{title.value} {images.get(pid, '')}" if c.isalnum())
            if window_class.value.casefold() == "cascadia_hosting_window_class" and "hostedcomputeagent" in compact:
                return True
            if len(records) >= 64:
                raise WindowObservationError("visible-window-bound")
            records.append({"hwnd": int(getattr(hwnd, "value", hwnd) or 0), "pid": pid,
                            "requested_root_pids": sorted(process_ids), "snapshot_parent_chain": chain,
                            "ancestry_proof": reason, "class": window_class.value, "title": title.value,
                            "rect": [int(rect.left), int(rect.top), int(rect.right), int(rect.bottom)]})
            return True
        except BaseException as error:
            callback_failure[0] = error
            return False

    user.EnumWindows.argtypes, user.EnumWindows.restype = [callback_type, wintypes.LPARAM], wintypes.BOOL
    try:
        success = user.EnumWindows(visit, 0)
        if callback_failure[0] is not None:
            raise callback_failure[0]
        if not success:
            raise ctypes.WinError(ctypes.get_last_error())
        roots.verify(process_ids)
        for hwnd, expected_pid in observed_owners.items():
            owner = wintypes.DWORD()
            if not user.GetWindowThreadProcessId(hwnd, ctypes.byref(owner)) or int(owner.value) != expected_pid:
                raise WindowObservationError("window-owner-drift-or-vanished")
        for pid, row in cells.items():
            if row[0].value and api.identity(row[0], pid) != row[1]:
                raise WindowObservationError("candidate-identity-drift")
        return records
    finally:
        close_cells(api, closing)

"""Application-owned Cron and Iperf lifecycle for the Moba-style desktop."""

from __future__ import annotations

import json
import logging
import math
import time
from collections.abc import Callable
from concurrent.futures import Future, ThreadPoolExecutor
from dataclasses import asdict, dataclass

from PyQt6.QtCore import QCoreApplication, QObject, Qt, QTimer, pyqtSignal

from .file_safety import write_json_atomic
from .moba_servers import (
    MobaEmbeddedServerLifecycleRecord,
    build_moba_server_plan,
    load_moba_server_record,
    start_moba_server,
    stop_moba_server,
)
from .paths import data_dir
from .state_lock import exclusive_file_lock

_SERVICES = ("cron", "iperf")
_LIFECYCLE_ERRORS = (OSError, RuntimeError, ValueError)
DEFAULT_STOP_SECONDS = 360


@dataclass(frozen=True)
class ServicePreferences:
    auto_stop_seconds: int | None = DEFAULT_STOP_SECONDS
    start_with_app: bool = False

    def __post_init__(self) -> None:
        seconds = self.auto_stop_seconds
        if seconds is not None and (type(seconds) is not int or not 1 <= seconds <= 65535):
            raise ValueError("Stop time must be between 1 and 65535 seconds.")
        if not isinstance(self.start_with_app, bool):
            raise ValueError("Start with the application must be true or false.")


@dataclass(frozen=True)
class _OwnedRun:
    record: MobaEmbeddedServerLifecycleRecord
    started_at: float


_Observation = tuple[MobaEmbeddedServerLifecycleRecord | None, _OwnedRun | None, str]


class ServerLifecycleManager(QObject):
    changed = pyqtSignal(str, str, str)

    def __init__(self, parent: QObject) -> None:
        super().__init__(parent)
        self._path = data_dir() / "server-preferences.json"
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="row-servers")
        # Only the serialized worker reads or mutates ownership. It also drains
        # shutdown work after an in-flight start even if Qt has already exited.
        self._worker_owned: dict[str, _OwnedRun] = {}
        self._pending: dict[str, tuple[str, Future[_Observation]]] = {}
        self._observed_owned: dict[str, _OwnedRun | None] = {}
        self.observed_records: dict[str, MobaEmbeddedServerLifecycleRecord | None] = {}
        self._closed = False
        self._startup_done = False
        self._window_count = 0
        self._poll = QTimer(self)
        self._poll.setInterval(40)
        self._poll.timeout.connect(self._collect)
        self._timers = {name: QTimer(self) for name in _SERVICES}
        for service, timer in self._timers.items():
            timer.setSingleShot(True)
            timer.setTimerType(Qt.TimerType.PreciseTimer)
            timer.timeout.connect(lambda name=service: self._expire(name))

    @classmethod
    def attach_window(
        cls, app: QCoreApplication, window: QObject,
    ) -> tuple[ServerLifecycleManager, Callable[[], None]]:
        path = data_dir() / "server-preferences.json"
        manager = next((child for child in app.children()
                        if isinstance(child, cls) and child._path == path and not child._closed), None)
        if manager is None:
            manager = cls(app)
            app.aboutToQuit.connect(manager.shutdown)
        manager._window_count += 1
        released = False

        def release() -> None:
            nonlocal released
            if released:
                return
            released = True
            manager._window_count -= 1
            if not manager._window_count and not manager._closed:
                manager.shutdown()
                manager.deleteLater()

        window.destroyed.connect(release)
        return manager, release

    def _settings(self) -> dict:
        try:
            settings = json.loads(self._path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return {}
        if not isinstance(settings, dict):
            raise ValueError("Invalid server preferences.")
        return settings

    def preferences(self, service: str) -> ServicePreferences:
        if service not in _SERVICES:
            raise ValueError("Unknown server control.")
        values = self._settings().get(service, {})
        if not isinstance(values, dict):
            raise ValueError(f"Invalid {service} preferences.")
        return ServicePreferences(values.get("auto_stop_seconds", DEFAULT_STOP_SECONDS), values.get("start_with_app", False))

    def save_preferences(self, service: str, prefs: ServicePreferences) -> None:
        if service not in _SERVICES or (service == "iperf" and prefs.start_with_app):
            raise ValueError("Only Cron supports starting with the application.")
        with exclusive_file_lock(self._path, timeout_seconds=0.25):
            settings = self._settings()
            settings[service] = asdict(prefs)
            write_json_atomic(self._path, settings, private=True)
        self._arm(service, prefs)

    def startup(self) -> None:
        if self._closed or self._startup_done:
            return
        self._startup_done = True
        try:
            if self.preferences("cron").start_with_app:
                self.start("cron")
        except _LIFECYCLE_ERRORS as error:
            self.changed.emit("cron", "stopped", str(error))

    def start(self, service: str) -> None:
        self._request(service, "start")

    def stop(self, service: str) -> None:
        self._request(service, "stop")

    def refresh(self, service: str) -> None:
        self._request(service, "refresh")

    def _request(self, service: str, operation: str, expected: MobaEmbeddedServerLifecycleRecord | None = None) -> None:
        if service not in _SERVICES:
            raise ValueError("Unknown server control.")
        if self._closed:
            return
        pending = self._pending.get(service)
        if pending and (operation == "refresh" or operation == pending[0]):
            return
        future = self._executor.submit(self._operate, service, operation, expected)
        self._pending[service] = (operation, future)
        self._poll.start()
        if operation != "refresh":
            self.changed.emit(service, "starting" if operation == "start" else "stopping", "")

    def _operate(self, service: str, operation: str, expected: MobaEmbeddedServerLifecycleRecord | None) -> _Observation:
        detail = ""
        try:
            record = load_moba_server_record(service)
            if operation == "start" and (record is None or not record.running):
                record = start_moba_server(build_moba_server_plan(service))
                self._worker_owned[service] = _OwnedRun(record, time.monotonic())
            elif operation in ("stop", "expire") and record is not None and record.running:
                if expected is None or expected == record:
                    record = stop_moba_server(service, expected_record=record)
        except _LIFECYCLE_ERRORS as error:
            detail = str(error)
            try:
                record = load_moba_server_record(service)
            except _LIFECYCLE_ERRORS:
                # Keep the last displayed record and ownership for cleanup.
                raise error from None
        owned = self._worker_owned.get(service)
        if owned is not None and record != owned.record:
            del self._worker_owned[service]
            owned = None
        return record, owned, detail

    def _collect(self) -> None:
        for service, request in list(self._pending.items()):
            _, future = request
            if self._pending.get(service) != request or not future.done():
                continue
            del self._pending[service]
            try:
                record, owned, detail = future.result()
            except Exception as error:
                # Exceptions crossing the worker boundary must never abort the
                # Qt signal handler. Preserve the last observed ownership.
                observed = self.observed_records.get(service)
                self.changed.emit(service, "running" if observed and observed.running else "stopped", str(error))
                continue
            self.observed_records[service] = record
            if owned != self._observed_owned.get(service):
                self._observed_owned[service] = owned
                try:
                    self._arm(service, self.preferences(service))
                except _LIFECYCLE_ERRORS as error:
                    detail = str(error)
                    self._arm(service, ServicePreferences())
            self.changed.emit(service, "running" if record and record.running else "stopped", detail)
        if not self._pending:
            self._poll.stop()

    def _arm(self, service: str, prefs: ServicePreferences) -> None:
        timer = self._timers[service]
        timer.stop()
        owned = self._observed_owned.get(service)
        if owned is not None and prefs.auto_stop_seconds is not None:
            remaining = owned.started_at + prefs.auto_stop_seconds - time.monotonic()
            timer.start(max(1, math.ceil(remaining * 1000)))

    def _expire(self, service: str) -> None:
        owned = self._observed_owned.get(service)
        if owned is not None:
            self._request(service, "expire", owned.record)

    def shutdown(self) -> None:
        if self._closed:
            return
        self._closed = True
        self._poll.stop()
        for timer in self._timers.values():
            timer.stop()
        if self._pending or any(self._observed_owned.values()):
            self._executor.submit(self._stop_owned)
        self._pending.clear()
        self._executor.shutdown(wait=False)

    def _stop_owned(self) -> None:
        for service, owned in self._worker_owned.items():
            try:
                stop_moba_server(service, expected_record=owned.record)
            except _LIFECYCLE_ERRORS as error:
                logging.getLogger(__name__).warning("Could not stop %s on application exit: %s", service, error)
        self._worker_owned.clear()

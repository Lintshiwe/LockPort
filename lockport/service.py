"""Main orchestration logic for the LockPort background service."""
from __future__ import annotations

import queue
import threading
import time
from threading import Event, Lock
from typing import List, Set

from .config import DEFAULT_CONFIG, LockPortConfig
from .device_locker import DeviceLocker
from .device_state import DeviceStateStore
from .logging_setup import configure_logging
from .usb_monitor import USBEvent, USBMonitor


class LockPortService:
    """Coordinates USB monitoring, locking, and PIN validation."""

    RECENT_UNLOCK_SECONDS = 10

    def __init__(
        self,
        config: LockPortConfig | None = None,
        *,
        console_log: bool | None = None,
    ) -> None:
        self.config = config or DEFAULT_CONFIG
        self.logger = configure_logging(force_console=console_log)
        self.device_locker = DeviceLocker()
        self._active_devices: Set[str] = set()
        self._active_lock = Lock()
        self._monitor: USBMonitor | None = None
        self._stop_event = Event()
        self._device_state_store = DeviceStateStore(self.config)
        self._event_queue: "queue.Queue[USBEvent]" = queue.Queue(maxsize=64)
        self._workers: List[threading.Thread] = []
        self._worker_count = 2

    def start(self) -> None:
        if not self._workers:
            self._start_workers()
        if self._monitor is None:
            self._monitor = USBMonitor(
                self._handle_usb_event, self.config.monitor_poll_seconds
            )
        self._monitor.start()
        self.logger.info("LockPort service started")

    def run(self, *, duration_seconds: float | None = None) -> None:
        """Start the service and block until stop() is invoked or timeout expires."""
        self.start()
        waited = self._stop_event.wait(timeout=duration_seconds)
        if duration_seconds is not None and not waited:
            self.logger.info(
                "LockPort service duration (%.1fs) elapsed; stopping", duration_seconds
            )
            self.stop()

    def stop(self) -> None:
        self.logger.info("Stopping LockPort service")
        self._stop_event.set()
        if self._monitor:
            self._monitor.stop()
        self._shutdown_workers()

    def _start_workers(self) -> None:
        for idx in range(self._worker_count):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"LockPortWorker-{idx}",
                daemon=True,
            )
            worker.start()
            self._workers.append(worker)
        self.logger.info("Started %s worker threads", len(self._workers))

    def _shutdown_workers(self) -> None:
        while not self._event_queue.empty():
            try:
                self._event_queue.get_nowait()
                self._event_queue.task_done()
            except queue.Empty:
                break
        for _ in self._workers:
            self._event_queue.put(
                USBEvent(instance_id="", drive_letter=None, volume_name=None, event_type="__stop__")
            )
        for worker in self._workers:
            worker.join(timeout=2.0)
        self._workers.clear()

    def _handle_usb_event(self, event: USBEvent) -> None:
        try:
            self._event_queue.put_nowait(event)
        except queue.Full:
            self.logger.warning("USB event queue full; dropping event: %s", event)

    def _worker_loop(self) -> None:
        while not self._stop_event.is_set():
            try:
                event = self._event_queue.get(timeout=0.5)
            except queue.Empty:
                continue

            if event.event_type == "__stop__":
                self._event_queue.task_done()
                break

            try:
                self._process_event(event)
            finally:
                self._event_queue.task_done()

    def _process_event(self, event: USBEvent) -> None:
        if not event.instance_id:
            self.logger.warning("Skipping device without instance ID: %s", event)
            return
        if event.event_type == "removal":
            self._handle_usb_removal(event)
            return

        state = self._device_state_store.get(event.instance_id)
        if state and state.status == "unlocked":
            elapsed = time.time() - state.updated_at
            if elapsed < self.RECENT_UNLOCK_SECONDS:
                self.logger.info(
                    "Skipping re-lock for %s; unlocked %.1fs ago",
                    event.instance_id,
                    elapsed,
                )
                return
            if event.synthetic:
                self.logger.info(
                    "Synthetic arrival for %s detected; preserving unlocked state",
                    event.instance_id,
                )
                return

        with self._active_lock:
            if event.instance_id in self._active_devices:
                self.logger.info("Device %s already processing", event.instance_id)
                return
            self._active_devices.add(event.instance_id)

        try:
            self._process_usb_event(event)
        finally:
            with self._active_lock:
                self._active_devices.discard(event.instance_id)

    def _process_usb_event(self, event: USBEvent) -> None:
        self.logger.info("Locking device %s", event.instance_id)
        lock_result = self.device_locker.disable(event.instance_id)
        self._record_device_state(
            event.instance_id,
            drive=event.drive_letter,
            volume=event.volume_name,
            status="locked",
        )
        if not lock_result.success:
            self.logger.error("Failed to disable device %s: %s", event.instance_id, lock_result.message)
            return

    def _handle_usb_removal(self, event: USBEvent) -> None:
        with self._active_lock:
            self._active_devices.discard(event.instance_id)

        self.logger.info("Device %s removed; locking associated port", event.instance_id)
        result = self.device_locker.disable(event.instance_id)
        if not result.success:
            self.logger.warning(
                "Failed to disable removed device %s: %s",
                event.instance_id,
                result.message,
            )
        self._record_device_state(
            event.instance_id,
            drive=event.drive_letter,
            volume=event.volume_name,
            status="removed",
        )

    def _record_device_state(
        self,
        instance_id: str,
        *,
        drive: str | None,
        volume: str | None,
        status: str,
    ) -> None:
        try:
            self._device_state_store.upsert(
                instance_id=instance_id,
                drive=drive,
                volume=volume,
                status=status,
            )
        except OSError as err:
            self.logger.error("Failed to persist device state: %s", err)

    @staticmethod
    def _format_device_name(event: USBEvent) -> str:
        label = event.volume_name or "Unnamed USB"
        port = event.drive_letter or "Unknown port"
        return f"{label} ({port})"

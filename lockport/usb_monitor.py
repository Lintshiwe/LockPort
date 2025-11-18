"""USB arrival monitoring built on top of Windows WMI."""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional

from .config import DEFAULT_CONFIG

try:  # pragma: no cover - imported lazily for Windows only
    import wmi  # type: ignore[import]
except ImportError:  # pragma: no cover - environment without dependency
    wmi = None

try:  # pragma: no cover - Windows-specific dependency
    import pythoncom  # type: ignore[import]
except ImportError:  # pragma: no cover
    pythoncom = None


logger = logging.getLogger("lockport.usb_monitor")


@dataclass(slots=True)
class USBEvent:
    instance_id: str
    drive_letter: Optional[str]
    volume_name: Optional[str]
    event_type: str  # "arrival" or "removal"
    synthetic: bool = False


class USBMonitor:
    """Background thread watching for USB mass-storage arrivals."""

    def __init__(
        self,
        callback: Callable[[USBEvent], None],
        poll_seconds: float | None = None,
    ) -> None:
        if wmi is None:
            raise RuntimeError(
                "wmi package is required. Please run 'pip install wmi pywin32'."
            )
        if pythoncom is None:
            raise RuntimeError(
                "pythoncom (pywin32) is required. Please run 'pip install pywin32'."
            )
        self._wmi: Any = wmi
        self.callback = callback
        self.poll_seconds = poll_seconds or DEFAULT_CONFIG.monitor_poll_seconds
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._drive_map: dict[str, str] = {}

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        logger.info("USB monitor started")

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=2.0)
            logger.info("USB monitor stopped")

    def _run_loop(self) -> None:
        pythoncom.CoInitializeEx(pythoncom.COINIT_MULTITHREADED)  # type: ignore[attr-defined]
        try:
            init_start = time.monotonic()
            conn: Any = self._wmi.WMI()
            watcher: Any = conn.Win32_VolumeChangeEvent.watch_for()
            logger.info(
                "USB monitor ready (%.2fs initialization)",
                time.monotonic() - init_start,
            )
            self._emit_existing_devices(conn)
            while not self._stop_event.is_set():
                try:
                    event = watcher(timeout_ms=int(self.poll_seconds * 1000))
                except wmi.x_wmi_timed_out:  # type: ignore[attr-defined]
                    continue
                except Exception as exc:  # pragma: no cover
                    logger.exception("WMI watcher failure: %s", exc)
                    continue

                try:
                    event_type = getattr(event, "EventType", None)
                    if event_type not in (2, 3):
                        continue
                    drive_letter = getattr(event, "DriveName", None)
                    volume_name = getattr(event, "Label", None)
                    instance_id = self._resolve_instance_id(drive_letter)
                    drive_key = drive_letter.upper() if drive_letter else None
                    event_name = "arrival" if event_type == 2 else "removal"
                    if event_name == "arrival":
                        if instance_id and drive_key:
                            self._drive_map[drive_key] = instance_id
                    else:
                        if drive_key:
                            if not instance_id:
                                instance_id = self._drive_map.get(drive_key, "")
                            self._drive_map.pop(drive_key, None)
                    usb_event = USBEvent(
                        instance_id=instance_id or "",
                        drive_letter=drive_letter,
                        volume_name=volume_name,
                        event_type=event_name,
                        synthetic=False,
                    )
                    logger.info(
                        "Detected USB %s: device=%s drive=%s label=%s",
                        usb_event.event_type,
                        usb_event.instance_id,
                        usb_event.drive_letter,
                        usb_event.volume_name,
                    )
                    self.callback(usb_event)
                except Exception as exc:
                    logger.exception("USB event handling failure: %s", exc)
        finally:
            pythoncom.CoUninitialize()  # type: ignore[attr-defined]

    def _emit_existing_devices(self, conn: Any) -> None:
        """Fire synthetic events for already-mounted removable drives."""
        try:
            current = conn.Win32_LogicalDisk(DriveType=2)
        except Exception as exc:  # pragma: no cover - defensive logging only
            logger.warning("Failed to enumerate existing USB devices: %s", exc)
            return

        for disk in current:
            drive_letter = getattr(disk, "DeviceID", None)
            volume_name = getattr(disk, "VolumeName", None)
            instance_id = self._resolve_instance_id(drive_letter)
            if not instance_id:
                continue
            usb_event = USBEvent(
                instance_id=instance_id,
                drive_letter=drive_letter,
                volume_name=volume_name,
                event_type="arrival",
                synthetic=True,
            )
            logger.info(
                "Detected pre-existing USB device: device=%s drive=%s label=%s",
                usb_event.instance_id,
                usb_event.drive_letter,
                usb_event.volume_name,
            )
            self.callback(usb_event)

    def _resolve_instance_id(self, drive_letter: Optional[str]) -> str:
        if not drive_letter:
            return ""
        conn: Any = self._wmi.WMI()
        logical_disk = conn.Win32_LogicalDisk(DeviceID=drive_letter)
        if not logical_disk:
            return ""
        associations = conn.AssociatorsOf(
            logical_disk[0].Path_,
            strAssocClass="Win32_LogicalDiskToPartition",
        )
        if not associations:
            return ""
        partition = associations[0]
        physical_disks = conn.AssociatorsOf(
            partition.Path_, strAssocClass="Win32_DiskDriveToDiskPartition"
        )
        if not physical_disks:
            return ""
        return getattr(physical_disks[0], "PNPDeviceID", "")

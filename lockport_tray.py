"""Tray helper that runs LockPort in the background with a visible taskbar icon."""
from __future__ import annotations

import argparse
import logging
import os
import sys
import threading
from typing import TYPE_CHECKING, Optional

from lockport.device_window import launch_device_window
from lockport.service import LockPortService

try:  # pragma: no cover - UI dependency checked at runtime
    import pystray
    from PIL import Image, ImageDraw, ImageFont
except ImportError as exc:  # pragma: no cover - surfaced to user
    _TRAY_IMPORT_ERROR: Optional[Exception] = exc
else:  # pragma: no cover - UI dependency checked at runtime
    _TRAY_IMPORT_ERROR = None

if TYPE_CHECKING:  # pragma: no cover - typing helpers only
    from PIL import Image as PILImage

LOGGER = logging.getLogger("lockport.tray")


class LockPortTrayApp:
    def __init__(self, *, console_log: bool = False) -> None:
        if _TRAY_IMPORT_ERROR:
            raise RuntimeError(
                "pystray and Pillow are required for the tray icon.\n"
                "Install them with 'pip install pystray Pillow'."
            ) from _TRAY_IMPORT_ERROR
        self.service = LockPortService(console_log=console_log)
        self.icon = pystray.Icon(
            "LockPort",
            self._build_image(),
            "LockPort Monitor",
            menu=pystray.Menu(
                pystray.MenuItem("Show Device Window", self._on_open_device_window),
                pystray.MenuItem("Stop Monitoring", self._on_stop),
            ),
        )
        self._service_thread = threading.Thread(target=self._run_service, daemon=True)
        self._window_lock = threading.Lock()
        self._window_active = False

    def _build_image(self) -> "PILImage":
        size = 64
        image = Image.new("RGBA", (size, size), (38, 50, 56, 255))
        draw = ImageDraw.Draw(image)
        draw.ellipse((6, 6, size - 6, size - 6), fill=(76, 175, 80, 255))
        font = ImageFont.load_default()
        text = "L"
        text_width, text_height = draw.textsize(text, font=font)
        draw.text(
            ((size - text_width) / 2, (size - text_height) / 2),
            text,
            font=font,
            fill="white",
        )
        return image

    def _run_service(self) -> None:
        try:
            self.service.run()
        except Exception as exc:  # pragma: no cover - defensive logging
            LOGGER.exception("LockPort service crashed: %s", exc)
            try:
                self.icon.notify("LockPort service stopped unexpectedly.")
            except Exception:
                pass
            finally:
                self.icon.stop()

    def start(self) -> None:
        self._service_thread.start()
        self.icon.run()
        self.service.stop()

    def _on_open_device_window(
        self,
        icon,
        _item,
    ) -> None:
        if self._window_active:
            self.icon.notify("Device window already open.")
            return

        def _launch() -> None:
            with self._window_lock:
                self._window_active = True
            try:
                launch_device_window(self.service.pin_manager)
            finally:
                with self._window_lock:
                    self._window_active = False

        threading.Thread(target=_launch, daemon=True).start()

    def _on_stop(self, icon, _item) -> None:
        self.service.stop()
        icon.stop()


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run LockPort with a taskbar icon")
    parser.add_argument(
        "--console-log",
        action="store_true",
        help="Mirror LockPort logs to this console while the tray icon is active.",
    )
    return parser


def _ensure_admin() -> None:
    if os.name != "nt":
        return
    try:
        import ctypes

        if ctypes.windll.shell32.IsUserAnAdmin():  # type: ignore[attr-defined]
            return
    except Exception:
        pass
    sys.stderr.write(
        "LockPort must run from an elevated PowerShell session so Windows allows\n"
        "usb devices to be disabled. Re-run powershell.exe as Administrator and try again.\n"
    )
    raise SystemExit(2)


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    _ensure_admin()
    app = LockPortTrayApp(console_log=args.console_log)
    app.start()


if __name__ == "__main__":
    main()

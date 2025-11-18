"""Entry point for running LockPort as a background service."""
from __future__ import annotations

import argparse
import signal
from typing import Sequence

from lockport.service import LockPortService


def _ensure_admin() -> None:
    """Exit early when the process is not elevated on Windows."""
    import os
    import sys

    if os.name != "nt":  # Non-Windows platforms skip the check.
        return

    try:
        import ctypes

        if ctypes.windll.shell32.IsUserAnAdmin():
            return
    except Exception:  # pragma: no cover - defensive fallback for ctypes issues
        pass

    sys.stderr.write(
        "LockPort must run from an elevated PowerShell session so Windows allows\n"
        "usb devices to be disabled. Re-run `powershell.exe` as Administrator,\n"
        " activate the virtual environment, and start lockport_service.py again.\n"
    )
    raise SystemExit(2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run the LockPort background service")
    parser.add_argument(
        "--console-log",
        action="store_true",
        help="Mirror log output to stdout (useful while testing interactively)",
    )
    parser.add_argument(
        "--duration",
        type=float,
        default=None,
        help="Auto-stop the service after N seconds (omit for indefinite run)",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    _ensure_admin()

    service = LockPortService(console_log=args.console_log)

    def handle_signal(signum: int, _frame: object) -> None:
        service.logger.info("Signal %s received, stopping service", signum)
        service.stop()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    if args.console_log:
        print("LockPort service running. Press Ctrl+C to stop.")

    try:
        service.run(duration_seconds=args.duration)
    finally:
        service.stop()


if __name__ == "__main__":
    main()

"""Command-line helper for administering LockPort."""
from __future__ import annotations

import argparse
import getpass
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Callable

from lockport.autostart import (
    autostart_status,
    disable_autostart,
    enable_autostart,
)
from lockport.device_state import DeviceStateStore
from lockport.device_window import launch_device_window
from lockport.pin_store import PinManager, PinValidationError


def cmd_status(_: argparse.Namespace, pin_manager: PinManager) -> int:
    status = pin_manager.get_status()
    print("Failed attempts:", status["failed_attempts"])
    if status["locked"]:
        print("Locked until:", status["lock_until"])
    else:
        print("Lockout: inactive")
    return 0


def cmd_reset_lockout(_: argparse.Namespace, pin_manager: PinManager) -> int:
    pin_manager.reset_lockout()
    print("Lockout counters cleared")
    return 0


def cmd_device_state(_: argparse.Namespace, pin_manager: PinManager) -> int:
    store = DeviceStateStore(pin_manager.config)
    states = store.list_states()
    if not states:
        print("No USB device activity recorded yet.")
        return 0
    for state in states:
        stamp = datetime.fromtimestamp(state.updated_at).isoformat(timespec="seconds")
        print(
            f"{state.instance_id}\t{state.status}\tdrive={state.drive or '-'}\tlabel={state.volume or '-'}\tupdated={stamp}"
        )
    return 0


def _start_background_monitor(console_log: bool) -> int:
    script_path = Path(__file__).resolve().with_name("lockport_tray.py")
    if not script_path.exists():
        print("lockport_service.py not found; cannot start background monitor.")
        return 1
    cmd = [sys.executable, str(script_path)]
    if console_log:
        cmd.append("--console-log")
    popen_kwargs: dict[str, object] = {
        "stdout": subprocess.DEVNULL,
        "stderr": subprocess.DEVNULL,
        "stdin": subprocess.DEVNULL,
    }
    if os.name == "nt":
        creationflags = 0
        for flag_name in ("CREATE_NEW_PROCESS_GROUP", "DETACHED_PROCESS"):
            creationflags |= int(getattr(subprocess, flag_name, 0))
        if creationflags:
            popen_kwargs["creationflags"] = creationflags
    else:
        popen_kwargs["start_new_session"] = True
    try:
        proc = subprocess.Popen(cmd, **popen_kwargs)  # type: ignore[arg-type]
    except OSError as exc:
        print(f"Failed to launch background monitor: {exc}")
        return 1
    stop_hint = "Task Manager or 'taskkill /PID {pid} /F'" if os.name == "nt" else "kill {pid}"
    print(f"Background monitor started (PID {proc.pid}). Stop it later via {stop_hint.format(pid=proc.pid)}.")
    return 0


def cmd_device_window(args: argparse.Namespace, pin_manager: PinManager) -> int:
    if getattr(args, "background_monitor", False):
        return _start_background_monitor(getattr(args, "console_log", False))
    launch_device_window(pin_manager)
    return 0


def cmd_autostart(args: argparse.Namespace, _: PinManager) -> int:
    if args.action == "enable":
        success = enable_autostart()
        print("Autostart task created." if success else "Failed to create autostart task (see logs).")
        return 0 if success else 1
    if args.action == "disable":
        success = disable_autostart()
        print("Autostart task removed." if success else "Failed to remove autostart task (see logs).")
        return 0 if success else 1
    print("Autostart status:", autostart_status())
    return 0


def cmd_set_pin(args: argparse.Namespace, pin_manager: PinManager) -> int:
    current_pin = args.current_pin
    if current_pin is None and not args.skip_current_check:
        current_pin = getpass.getpass("Current PIN: ")
    new_pin = getpass.getpass("New PIN: ")
    confirm_pin = getpass.getpass("Confirm PIN: ")
    if new_pin != confirm_pin:
        print("PIN entries do not match")
        return 1
    try:
        pin_manager.set_pin(new_pin, current_pin=current_pin)
    except PinValidationError as exc:
        print(f"Failed to set PIN: {exc}")
        return 1
    print("PIN updated successfully")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="LockPort administration CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("status", help="Show PIN status")
    subparsers.add_parser("reset-lockout", help="Clear lockout counters")
    subparsers.add_parser("device-state", help="List tracked USB devices")
    device_parser = subparsers.add_parser("device-window", help="Open the live device window or kick off the background monitor")
    device_parser.add_argument(
        "--background-monitor",
        action="store_true",
        help="Start the LockPort background monitor/service without opening the GUI",
    )
    device_parser.add_argument(
        "--console-log",
        action="store_true",
        help="Mirror service logs to this console while background monitor is running (Windows only).",
    )
    autostart_parser = subparsers.add_parser(
        "autostart", help="Manage the background scheduled task"
    )
    autostart_parser.add_argument(
        "action",
        choices=["enable", "disable", "status"],
        help="Enable, disable, or view autostart status",
    )

    set_pin_parser = subparsers.add_parser("set-pin", help="Change the stored PIN")
    set_pin_parser.add_argument("--current-pin", dest="current_pin", help="Current PIN")
    set_pin_parser.add_argument(
        "--skip-current-check",
        action="store_true",
        help="Skip current PIN verification (requires admin context)",
    )
    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()
    pin_manager = PinManager()

    commands: dict[str, Callable[[argparse.Namespace, PinManager], int]] = {
        "status": cmd_status,
        "reset-lockout": cmd_reset_lockout,
        "set-pin": cmd_set_pin,
        "device-state": cmd_device_state,
        "device-window": cmd_device_window,
        "autostart": cmd_autostart,
    }
    handler = commands[args.command]
    return handler(args, pin_manager)


if __name__ == "__main__":
    raise SystemExit(main())

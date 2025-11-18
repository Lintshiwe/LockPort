"""Tkinter window for viewing + controlling USB/Type-C device states."""
from __future__ import annotations

import base64
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk
from typing import Any, Dict, Optional

from .autostart import autostart_status, disable_autostart, enable_autostart
from .device_locker import DeviceLocker
from .device_state import DeviceState, DeviceStateStore
from .pin_store import PinLockedError, PinManager, PinValidationError
from .usb_monitor import USBEvent, USBMonitor
from .resources import asset_path, load_asset_bytes

REFRESH_SECONDS = 1.0
RECENT_UNLOCK_SECONDS = 10.0


def launch_device_window(pin_manager: PinManager) -> None:
    """Render a small control surface that can lock/unlock devices."""

    store = DeviceStateStore(pin_manager.config)
    locker = DeviceLocker()
    latest_states: Dict[str, DeviceState] = {}
    usb_events: "queue.Queue[USBEvent]" = queue.Queue()
    processing_devices: set[str] = set()
    refresh_job: str | None = None
    external_sync_job: str | None = None
    try:
        usb_monitor = USBMonitor(usb_events.put, pin_manager.config.monitor_poll_seconds)
        usb_monitor.start()
    except RuntimeError as exc:
        usb_monitor = None
        monitor_error = str(exc)
    else:
        monitor_error = ""

    root = tk.Tk()
    root.title("LockPort – Connected Devices")
    root.geometry("780x520")
    root.minsize(720, 480)
    root.resizable(True, True)

    def _apply_branding_icon(widget: tk.Tk) -> None:
        try:
            encoded = base64.b64encode(load_asset_bytes("app-logo-256.png")).decode(
                "ascii"
            )
            icon_photo = tk.PhotoImage(data=encoded)
            widget.iconphoto(True, icon_photo)
            widget._lockport_icon = icon_photo  # type: ignore[attr-defined]
            with asset_path("app-icon.ico") as ico_path:
                widget.iconbitmap(default=str(ico_path))
        except Exception:
            pass

    _apply_branding_icon(root)

    columns = ("Device", "Status", "Port", "Label", "Updated")
    tree = ttk.Treeview(root, columns=columns, show="headings", height=10)
    widths = (300, 90, 80, 180, 120)
    for col, width in zip(columns, widths):
        tree.heading(col, text=col)
        tree.column(col, width=width, anchor="w")
    tree.pack(fill=tk.BOTH, expand=True, padx=8, pady=(8, 4))

    pin_var = tk.StringVar()
    initial_status = "Select a device to manage it."
    if monitor_error:
        initial_status = f"USB monitor unavailable: {monitor_error}"
    status_var = tk.StringVar(value=initial_status)

    controls = tk.Frame(root)
    controls.pack(fill=tk.X, padx=8, pady=(0, 4))
    tk.Label(controls, text="PIN:").grid(row=0, column=0, sticky="e", padx=(0, 4))
    pin_entry = tk.Entry(controls, textvariable=pin_var, show="*")
    pin_entry.grid(row=0, column=1, padx=(0, 8))
    lock_btn = tk.Button(controls, text="Lock selected", width=14)
    lock_btn.grid(row=0, column=2, padx=(0, 8))
    unlock_btn = tk.Button(controls, text="Unlock selected", width=16)
    unlock_btn.grid(row=0, column=3)

    status_label = tk.Label(root, textvariable=status_var, anchor="w", fg="#37474f")
    status_label.pack(fill=tk.X, padx=8, pady=(0, 4))

    autostart_state_var = tk.StringVar(value="State: Checking…")
    autostart_choice_var = tk.StringVar(value="disable")
    autostart_syncing = False
    autostart_busy = False
    current_autostart_state: Optional[str] = None
    autostart_radios: list[tk.Radiobutton] = []

    def _autostart_enabled(state: str) -> bool:
        return state not in {"Unknown", "NotInstalled", "Disabled"}

    def _set_autostart_busy(busy: bool) -> None:
        nonlocal autostart_busy
        autostart_busy = busy
        widget_state = tk.DISABLED if busy else tk.NORMAL
        for radio in autostart_radios:
            radio.configure(state=widget_state)

    def _update_autostart_ui(state: Optional[str] = None) -> None:
        nonlocal autostart_syncing, current_autostart_state
        if state is not None:
            current_autostart_state = state
        if current_autostart_state is None:
            return
        autostart_state_var.set(f"State: {current_autostart_state}")
        autostart_syncing = True
        autostart_choice_var.set(
            "enable" if _autostart_enabled(current_autostart_state) else "disable"
        )
        autostart_syncing = False

    autostart_frame = tk.LabelFrame(root, text="Background monitor")
    autostart_frame.pack(fill=tk.X, padx=8, pady=(0, 8))
    autostart_frame.grid_columnconfigure(0, weight=1)
    autostart_frame.grid_columnconfigure(1, weight=1)

    tk.Label(
        autostart_frame,
        textvariable=autostart_state_var,
        anchor="w",
    ).grid(row=0, column=0, columnspan=2, sticky="w")

    def _apply_autostart_change(enable_choice: bool) -> None:
        def worker() -> None:
            success = enable_autostart() if enable_choice else disable_autostart()
            new_state = autostart_status() if success else None

            def finalize() -> None:
                _set_autostart_busy(False)
                if success and new_state is not None:
                    _update_autostart_ui(new_state)
                    status_var.set(
                        "Background monitoring {}.".format(
                            "enabled" if enable_choice else "disabled"
                        )
                    )
                else:
                    status_var.set(
                        "Failed to {} background monitoring; check logs.".format(
                            "enable" if enable_choice else "disable"
                        )
                    )
                    _update_autostart_ui()

            root.after(0, finalize)

        _set_autostart_busy(True)
        status_var.set("Updating background monitoring…")
        threading.Thread(target=worker, daemon=True).start()

    def _on_autostart_choice() -> None:
        if autostart_syncing or autostart_busy:
            return
        desired_enable = autostart_choice_var.get() == "enable"
        _apply_autostart_change(desired_enable)

    enable_radio = tk.Radiobutton(
        autostart_frame,
        text="Enable",
        value="enable",
        variable=autostart_choice_var,
        indicatoron=False,
        width=16,
        command=_on_autostart_choice,
    )
    enable_radio.grid(row=1, column=0, sticky="w", pady=(6, 0), padx=(0, 8))

    disable_radio = tk.Radiobutton(
        autostart_frame,
        text="Disable",
        value="disable",
        variable=autostart_choice_var,
        indicatoron=False,
        width=16,
        command=_on_autostart_choice,
    )
    disable_radio.grid(row=1, column=1, sticky="w", pady=(6, 0))

    autostart_radios.extend([enable_radio, disable_radio])

    def _initial_autostart_fetch() -> None:
        state = autostart_status()

        def finish() -> None:
            _update_autostart_ui(state)

        root.after(0, finish)

    threading.Thread(target=_initial_autostart_fetch, daemon=True).start()

    log_frame = tk.LabelFrame(root, text="Event log")
    log_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=(0, 8))
    log_text = tk.Text(log_frame, height=8, state="disabled", wrap="word")
    log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

    def _scroll_log(*args: Any) -> None:
        log_text.yview(*args)  # type: ignore[misc]

    log_scroll = tk.Scrollbar(log_frame, command=_scroll_log)
    log_scroll.pack(side=tk.RIGHT, fill=tk.Y)
    log_text.configure(yscrollcommand=log_scroll.set)

    def format_time(epoch: float) -> str:
        if not epoch:
            return "-"
        return time.strftime("%H:%M:%S", time.localtime(epoch))

    def device_label(event: USBEvent) -> str:
        label = event.volume_name or "Unnamed USB"
        port = event.drive_letter or "Unknown port"
        return f"{label} ({port})"

    def refresh() -> None:
        nonlocal latest_states, refresh_job
        states = sorted(store.list_states(), key=lambda s: s.updated_at, reverse=True)
        latest_states = {state.instance_id: state for state in states}
        selected = tree.focus()
        tree.delete(*tree.get_children())
        for state in states:
            status_color = "unlocked" if state.status == "unlocked" else "locked"
            tree.insert(
                "",
                "end",
                iid=state.instance_id,
                values=(
                    state.instance_id[:32],
                    state.status,
                    state.drive or "-",
                    state.volume or "-",
                    format_time(state.updated_at),
                ),
                tags=(status_color,),
            )
        tree.tag_configure("locked", foreground="#c62828")
        tree.tag_configure("unlocked", foreground="#2e7d32")
        if selected and tree.exists(selected):
            tree.selection_set(selected)
            tree.focus(selected)
        refresh_job = root.after(int(REFRESH_SECONDS * 1000), refresh)

    def refresh_now() -> None:
        nonlocal refresh_job
        if refresh_job is not None:
            try:
                root.after_cancel(refresh_job)
            except Exception:
                pass
            refresh_job = None
        refresh()

    def append_log(message: str) -> None:
        timestamp = time.strftime("%H:%M:%S")
        log_text.configure(state="normal")
        log_text.insert(tk.END, f"[{timestamp}] {message}\n")
        log_text.see(tk.END)
        log_text.configure(state="disabled")

    def _require_selection() -> Optional[DeviceState]:
        instance_id = tree.focus()
        if not instance_id:
            status_var.set("Select a device row first.")
            return None
        state = latest_states.get(instance_id)
        if not state:
            status_var.set("Device metadata unavailable; wait for refresh.")
            return None
        return state

    def _update_state(instance_id: str, status: str) -> None:
        state = latest_states.get(instance_id)
        store.upsert(
            instance_id=instance_id,
            drive=state.drive if state else None,
            volume=state.volume if state else None,
            status=status,
        )
        refresh_now()

    def _handle_usb_event(event: USBEvent) -> None:
        if not event.instance_id:
            status_var.set("Ignoring USB device without instance ID.")
            return
        if event.event_type == "arrival":
            _handle_arrival(event)
        else:
            _handle_removal(event)

    def _handle_arrival(event: USBEvent) -> None:
        if event.instance_id in processing_devices:
            return
        processing_devices.add(event.instance_id)
        display_name = device_label(event)
        existing_state = store.get(event.instance_id)
        if existing_state and existing_state.status == "unlocked":
            elapsed = time.time() - existing_state.updated_at
            if elapsed < RECENT_UNLOCK_SECONDS:
                status_var.set(
                    f"{display_name} already unlocked ({elapsed:.1f}s ago)."
                )
                append_log(
                    f"Ignored arrival for {display_name}; unlocked {elapsed:.1f}s ago."
                )
                refresh_now()
                processing_devices.discard(event.instance_id)
                return

        if event.synthetic:
            current_status = existing_state.status if existing_state else "unknown"
            status_var.set(
                f"Existing device detected: {display_name} (status {current_status})."
            )
            append_log(
                f"Synced existing device {display_name}; preserved status {current_status}."
            )
            refresh_now()
            processing_devices.discard(event.instance_id)
            return

        status_var.set(f"USB {display_name} detected; locking...")
        append_log(f"Arrival detected: {display_name}")
        lock_result = locker.disable(event.instance_id)
        store.upsert(
            instance_id=event.instance_id,
            drive=event.drive_letter,
            volume=event.volume_name,
            status="locked",
        )
        refresh_now()
        if not lock_result.success:
            status_var.set(f"Failed to lock {display_name}: {lock_result.message}")
            append_log(f"Failed to lock {display_name}: {lock_result.message}")
            processing_devices.discard(event.instance_id)
            return

        status_var.set(
            f"Device {display_name} locked. Enter PIN in this window to unlock."
        )
        append_log(
            f"Awaiting PIN entry for {display_name}; use Unlock button after typing PIN."
        )
        processing_devices.discard(event.instance_id)

    def _handle_removal(event: USBEvent) -> None:
        processing_devices.discard(event.instance_id)
        locker.disable(event.instance_id)
        store.upsert(
            instance_id=event.instance_id,
            drive=event.drive_letter,
            volume=event.volume_name,
            status="removed",
        )
        refresh_now()
        status_var.set(
            f"USB {device_label(event)} removed; port re-locked."
        )
        append_log(f"Removal detected: {device_label(event)}")

    def _poll_usb_queue() -> None:
        if usb_monitor is None:
            return
        try:
            event = usb_events.get_nowait()
        except queue.Empty:
            pass
        else:
            _handle_usb_event(event)
        finally:
            root.after(int(REFRESH_SECONDS * 1000), _poll_usb_queue)

    def handle_lock() -> None:
        state = _require_selection()
        if not state:
            return
        result = locker.disable(state.instance_id)
        if result.success:
            _update_state(state.instance_id, "locked")
            status_var.set(f"Device {state.instance_id[:18]} locked.")
            append_log(f"Manually locked {state.instance_id[:18]}")
        else:
            status_var.set(f"Failed to lock: {result.message}")
            append_log(f"Failed to lock {state.instance_id[:18]}: {result.message}")

    def handle_unlock() -> None:
        state = _require_selection()
        if not state:
            return
        pin = pin_var.get().strip()
        if not pin:
            cached_pin = pin_manager.get_cached_pin()
            if cached_pin:
                pin = cached_pin
                pin_var.set(pin)
        if not pin:
            status_var.set("Enter the admin PIN to unlock a device.")
            return
        try:
            pin_manager.verify_pin(pin)
        except PinLockedError as exc:
            status_var.set(f"PIN locked: {exc}")
            return
        except PinValidationError:
            status_var.set("Invalid PIN.")
            return

        result = locker.enable(state.instance_id)
        if result.success:
            _update_state(state.instance_id, "unlocked")
            pin_var.set("")
            status_var.set(f"Device {state.instance_id[:18]} unlocked.")
            append_log(f"Manually unlocked {state.instance_id[:18]}")
        else:
            if result.is_device_missing():
                _update_state(state.instance_id, "removed")
                status_var.set("Device disconnected before it could be unlocked.")
                append_log("Device disconnected before manual unlock completed")
            else:
                status_var.set(f"Failed to unlock: {result.message}")
                append_log(f"Failed to unlock {state.instance_id[:18]}: {result.message}")

    lock_btn.configure(command=handle_lock)
    unlock_btn.configure(command=handle_unlock)

    def sync_external_store() -> None:
        nonlocal external_sync_job
        store.reload()
        refresh_now()
        external_sync_job = root.after(int(REFRESH_SECONDS * 1000), sync_external_store)

    def on_close() -> None:
        if usb_monitor is not None:
            usb_monitor.stop()
        if refresh_job is not None:
            try:
                root.after_cancel(refresh_job)
            except Exception:
                pass
        if external_sync_job is not None:
            try:
                root.after_cancel(external_sync_job)
            except Exception:
                pass
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", on_close)
    if usb_monitor is not None:
        root.after(int(REFRESH_SECONDS * 1000), _poll_usb_queue)
    external_sync_job = root.after(int(REFRESH_SECONDS * 1000), sync_external_store)
    refresh_now()
    root.mainloop()

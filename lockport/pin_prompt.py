"""Simple Tkinter modal to request a PIN from the interactive user."""
from __future__ import annotations

import logging
import queue
import threading
from dataclasses import dataclass
from tkinter import BOTH, Button, Entry, Frame, Label, StringVar, Tk, Toplevel
from typing import Callable

from .config import DEFAULT_CONFIG


LOGGER = logging.getLogger("lockport.pin_prompt")


@dataclass(slots=True)
class PinPromptResult:
    pin: str | None
    cancelled: bool
    exit_requested: bool = False


class PinPrompt:
    """Blocking PIN prompt that always stays on top of other windows."""

    def __init__(self, timeout_seconds: int | None = None) -> None:
        self.timeout_seconds = timeout_seconds or DEFAULT_CONFIG.ui_timeout_seconds

    def request_pin(
        self,
        *,
        drive_label: str | None,
        attempts_remaining: int,
        external_pin_provider: Callable[[], str | None] | None = None,
        parent: Tk | None = None,
    ) -> PinPromptResult:
        if parent:
            return self._request_with_parent(
                parent,
                drive_label=drive_label,
                attempts_remaining=attempts_remaining,
                external_pin_provider=external_pin_provider,
            )
        return self._request_standalone(
            drive_label=drive_label,
            attempts_remaining=attempts_remaining,
            external_pin_provider=external_pin_provider,
        )

    def _build_dialog(
        self,
        window: Tk | Toplevel,
        *,
        drive_label: str | None,
        attempts_remaining: int,
        external_pin_provider: Callable[[], str | None] | None,
        finish: Callable[[PinPromptResult], None],
    ) -> None:
        window.title("LockPort - USB Unlock")
        try:
            window.attributes("-topmost", True)  # type: ignore[call-overload]
            window.lift()  # type: ignore[attr-defined]
        except Exception:
            pass
        window.resizable(False, False)

        message = f"USB drive {drive_label or ''} locked. Enter PIN.".strip()
        Label(window, text=message, padx=16, pady=12).pack(fill=BOTH)
        Label(window, text=f"Attempts remaining: {attempts_remaining}", padx=16).pack(fill=BOTH)

        pin_var = StringVar()
        entry = Entry(window, textvariable=pin_var, show="*", width=12, justify="center")
        entry.pack(padx=16, pady=(8, 16))
        entry.focus_set()

        def submit(*_: object) -> None:
            value = pin_var.get()
            finish(PinPromptResult(pin=value, cancelled=False))

        def correct() -> None:
            pin_var.set("")
            entry.focus_set()

        def on_timeout() -> None:
            finish(PinPromptResult(pin=None, cancelled=True))

        def on_exit() -> None:
            finish(PinPromptResult(pin=None, cancelled=True, exit_requested=True))

        btn_row = Frame(window)
        btn_row.pack(padx=16, pady=(0, 16))
        Button(btn_row, text="Correction", width=12, command=correct).pack(side="left", padx=4)
        Button(btn_row, text="Accept", width=12, command=submit).pack(side="left", padx=4)
        Button(btn_row, text="Exit", width=12, command=on_exit).pack(side="left", padx=4)

        window.bind("<Return>", submit)
        window.protocol("WM_DELETE_WINDOW", on_exit)
        window.after(self.timeout_seconds * 1000, on_timeout)

        def poll_external() -> None:
            if external_pin_provider:
                external_value = external_pin_provider()
                if external_value:
                    pin_var.set(external_value)
                    submit()
                    return
            window.after(500, poll_external)

        poll_external()

    def _request_with_parent(
        self,
        parent: Tk,
        *,
        drive_label: str | None,
        attempts_remaining: int,
        external_pin_provider: Callable[[], str | None] | None,
    ) -> PinPromptResult:
        immediate_pin = self._consume_external_pin(external_pin_provider)
        if immediate_pin:
            return PinPromptResult(pin=immediate_pin, cancelled=False)

        result_holder: list[PinPromptResult] = []
        dialog = Toplevel(parent)
        dialog.transient(parent)
        dialog.grab_set()

        def finish(result: PinPromptResult) -> None:
            if not result_holder:
                result_holder.append(result)
            dialog.destroy()

        self._build_dialog(
            dialog,
            drive_label=drive_label,
            attempts_remaining=attempts_remaining,
            external_pin_provider=external_pin_provider,
            finish=finish,
        )
        parent.wait_window(dialog)
        return result_holder[0] if result_holder else PinPromptResult(pin=None, cancelled=True)

    def _request_standalone(
        self,
        *,
        drive_label: str | None,
        attempts_remaining: int,
        external_pin_provider: Callable[[], str | None] | None,
    ) -> PinPromptResult:
        immediate_pin = self._consume_external_pin(external_pin_provider)
        if immediate_pin:
            return PinPromptResult(pin=immediate_pin, cancelled=False)

        result_queue: "queue.Queue[PinPromptResult]" = queue.Queue(maxsize=1)

        def _show() -> None:
            root = Tk()

            def finish(result: PinPromptResult) -> None:
                if result_queue.empty():
                    result_queue.put(result)
                root.destroy()

            self._build_dialog(
                root,
                drive_label=drive_label,
                attempts_remaining=attempts_remaining,
                external_pin_provider=external_pin_provider,
                finish=finish,
            )
            root.mainloop()

        thread = threading.Thread(target=_show, daemon=True)
        thread.start()
        try:
            return result_queue.get(timeout=self.timeout_seconds + 5)
        except queue.Empty:
            return PinPromptResult(pin=None, cancelled=True)
        finally:
            thread.join(timeout=1)

    @staticmethod
    def _consume_external_pin(
        provider: Callable[[], str | None] | None,
    ) -> str | None:
        if not provider:
            return None
        try:
            value = provider()
            if value:
                return value
        except Exception as exc:  # pragma: no cover - defensive
            LOGGER.warning("External PIN provider failed: %s", exc)
        return None

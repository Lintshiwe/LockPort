"""Helpers to disable/enable USB storage devices via PowerShell."""
from __future__ import annotations

import logging
import subprocess
import textwrap
from dataclasses import dataclass

logger = logging.getLogger("lockport.device_locker")


@dataclass(slots=True)
class DeviceActionResult:
    instance_id: str
    success: bool
    message: str

    def is_device_missing(self) -> bool:
        text = (self.message or "").lower()
        return any(keyword in text for keyword in ("devicenotfound", "not connected", "device is not connected"))


class DeviceLocker:
    """Wraps PowerShell commands (with pnputil fallback) to toggle USB devices."""

    def __init__(self, *, shell: str = "powershell", pnputil: str = "pnputil") -> None:
        self.shell = shell
        self.pnputil = pnputil

    def disable(self, instance_id: str) -> DeviceActionResult:
        if not instance_id:
            return DeviceActionResult(instance_id, False, "Empty instance id")
        command = textwrap.dedent(
            f"""
            $device = Get-PnpDevice -InstanceId '{instance_id}' -ErrorAction SilentlyContinue
            if ($null -eq $device) {{
              Write-Output 'DeviceNotFound'
              exit 1
            }}
            Disable-PnpDevice -InstanceId '{instance_id}' -Confirm:$false -ErrorAction Stop
            Write-Output 'Success'
            """
        )
        result = self._run_command(instance_id, command)
        if not result.success:
            logger.info("PowerShell disable failed for %s, trying pnputil", instance_id)
            return self._pnputil_action(instance_id, disable=True)
        return result

    def enable(self, instance_id: str) -> DeviceActionResult:
        if not instance_id:
            return DeviceActionResult(instance_id, False, "Empty instance id")
        command = textwrap.dedent(
            f"""
            $device = Get-PnpDevice -InstanceId '{instance_id}' -ErrorAction SilentlyContinue
            if ($null -eq $device) {{
              Write-Output 'DeviceNotFound'
              exit 1
            }}
            Enable-PnpDevice -InstanceId '{instance_id}' -Confirm:$false -ErrorAction Stop
            Write-Output 'Success'
            """
        )
        result = self._run_command(instance_id, command)
        if not result.success:
            logger.info("PowerShell enable failed for %s, trying pnputil", instance_id)
            return self._pnputil_action(instance_id, disable=False)
        return result

    def _run_command(self, instance_id: str, command: str) -> DeviceActionResult:
        try:
            completed = subprocess.run(
                [self.shell, "-NoProfile", "-Command", command],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as err:
            logger.error("PowerShell invocation failed: %s", err)
            return DeviceActionResult(instance_id, False, str(err))

        success = completed.returncode == 0 and "Success" in completed.stdout
        message = completed.stdout.strip() or completed.stderr.strip()
        if not success:
            logger.warning(
                "Device action failed (instance_id=%s, code=%s, output=%s)",
                instance_id,
                completed.returncode,
                message,
            )
        return DeviceActionResult(instance_id, success, message)

    def _pnputil_action(self, instance_id: str, *, disable: bool) -> DeviceActionResult:
        verb = "/disable-device" if disable else "/enable-device"
        try:
            completed = subprocess.run(
                [self.pnputil, verb, instance_id, "/force"],
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as err:
            logger.error("pnputil invocation failed: %s", err)
            return DeviceActionResult(instance_id, False, str(err))

        success = completed.returncode == 0
        message = completed.stdout.strip() or completed.stderr.strip()
        if not success:
            logger.warning(
                "pnputil action failed (instance_id=%s, code=%s, output=%s)",
                instance_id,
                completed.returncode,
                message,
            )
        return DeviceActionResult(instance_id, success, message)

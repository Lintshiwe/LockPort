"""Helpers for registering LockPort as a background scheduled task on Windows."""
from __future__ import annotations

import logging
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
LOGGER = logging.getLogger("lockport.autostart")
TASK_NAME = "LockPortBackground"


def _powershell(script: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
        text=True,
        capture_output=True,
        check=False,
    )


def enable_autostart() -> bool:
    """Create/overwrite a scheduled task that launches LockPort at logon."""
    pythonw = (Path(PROJECT_ROOT) / ".venv" / "Scripts" / "pythonw.exe")
    if not pythonw.exists():
        pythonw = Path(PROJECT_ROOT) / ".venv" / "Scripts" / "python.exe"
    script = (
        "$taskName = '{task}';"
        "$action = New-ScheduledTaskAction -Execute '{exe}' -Argument 'lockport_service.py' -WorkingDirectory '{cwd}';"
        "$trigger = New-ScheduledTaskTrigger -AtLogOn;"
        "Register-ScheduledTask -TaskName $taskName -Action $action -Trigger $trigger -RunLevel Highest -Force | Out-Null"
    ).format(task=TASK_NAME, exe=str(pythonw).replace("'", "''"), cwd=str(PROJECT_ROOT).replace("'", "''"))
    result = _powershell(script)
    if result.returncode != 0:
        LOGGER.error("Failed to register scheduled task: %s", result.stderr.strip())
        return False
    LOGGER.info("LockPort autostart task registered")
    return True


def disable_autostart() -> bool:
    script = "Unregister-ScheduledTask -TaskName '{task}' -Confirm:$false".format(task=TASK_NAME)
    result = _powershell(script)
    if result.returncode != 0:
        LOGGER.error("Failed to unregister task: %s", result.stderr.strip())
        return False
    LOGGER.info("LockPort autostart task removed")
    return True


def autostart_status() -> str:
    script = (
        "($task = Get-ScheduledTask -TaskName '{task}' -ErrorAction SilentlyContinue)"
        " ? $task.State : 'NotInstalled'"
    ).format(task=TASK_NAME)
    result = _powershell(script)
    if result.returncode != 0:
        return "Unknown"
    return result.stdout.strip() or "Unknown"

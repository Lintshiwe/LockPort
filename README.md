# LockPort

![LockPort logo](assets/branding/lockport-logo-256.png)

LockPort is a lightweight Windows background service that automatically locks newly inserted USB storage devices until a user enters the correct PIN. It is designed for small offices and kiosks that need a straightforward way to keep random flash drives from mounting without authorization.

## Features

- Watches USB arrivals via Windows WMI and disables devices immediately (removals automatically re-lock the port so reinserts are gated again).
- Pops up a topmost PIN dialog per device with Correction/Accept/Exit controls (Exit immediately stops the service) and shows the renamed drive label plus the port/drive letter that detected it. The last successful PIN entry is cached (DPAPI-protected) for a couple of minutes so other admin tools (like the device window) can reuse it without nagging the user again.
- Stores PINs using salted PBKDF2 hashes; default PIN is `0000` until changed.
- Includes a CLI helper to change the PIN, clear lockouts, or view status.
- Tracks the latest state (locked/unlocked) for every observed USB storage device.
- Logs all actions to `%ProgramData%/LockPort/lockport.log` with rotation.

## Project layout

```text
lockport/             # Core package (monitor, PIN manager, GUI, service)
lockport_service.py   # Entry point for the always-on monitor
lockport_tray.py      # Background monitor with a taskbar icon
lockport_cli.py       # Admin helper for setting/changing the PIN
requirements.txt      # Runtime dependencies (pywin32 + wmi)
README.md             # This file
```

## Quick start

1. **Create and activate a virtual environment** (PowerShell example):

   ```powershell
   py -3 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   ```

2. **Install dependencies**:

   ```powershell
   pip install -r requirements.txt
   ```

3. **Set a new PIN** (optional but recommended immediately):

   ```powershell
   python lockport_cli.py set-pin
   ```

4. **Run the service in the foreground** while testing (from an elevated PowerShell window so Windows lets LockPort disable devices):

   ```powershell
   python lockport_service.py --console-log --duration 120
   ```

   - `--console-log` mirrors log output to the terminal so you immediately see when the watcher is ready.
   - `--duration` is optional and auto-stops the service after N seconds (omit it for continuous monitoring).

When you are satisfied, register the service to run automatically at logon (requires an administrator account). One option is a Task Scheduler entry that launches `pythonw.exe lockport_service.py` with highest privileges and the `Start in` directory set to the project root. The snippet below can be adapted inside an elevated PowerShell:

```powershell
$workingDir = "C:\\Users\\<you>\\OneDrive\\Projects\\LockPort"
$pythonw = "$workingDir\\.venv\\Scripts\\pythonw.exe"
Register-ScheduledTask -TaskName "LockPort" -Action (New-ScheduledTaskAction -Execute $pythonw -Argument "lockport_service.py" -WorkingDirectory $workingDir) -Trigger (New-ScheduledTaskTrigger -AtLogOn) -RunLevel Highest -User "<AdminAccount>"
```

### Quickly launching an elevated shell

LockPort will now exit immediately if it is not running with administrator privileges. If you are working from Git Bash or another shell that cannot elevate, hop into an admin PowerShell first:

```powershell
Start-Process powershell -Verb RunAs
# inside the new window
Set-Location C:\Users\<you>\OneDrive\Projects\LockPort
.\.venv\Scripts\Activate.ps1
python lockport_service.py --console-log
```

Running this way ensures both `Disable-PnpDevice` and the `pnputil` fallback are allowed to actually turn off the USB device before the PIN prompt succeeds.

## CLI reference

- `python lockport_cli.py status` – shows failed attempt counts and lockout state.
- `python lockport_cli.py set-pin` – prompts for current and new PIN.
- `python lockport_cli.py reset-lockout` – clears lockout timer after an incident.
- `python lockport_cli.py device-state` – lists tracked USB devices with their last-known drive, label, and status.
- `python lockport_cli.py device-window` – opens a small Tkinter window showing live device states (run inside an interactive Windows session) and now provides Lock/Unlock buttons (unlocking requires the admin PIN).

  - If you unlocked a device moments ago in the main service dialog, the cached PIN is automatically reused here—just click **Unlock selected** without typing again.
  - Append `--background-monitor` to spin up the always-on monitor plus a taskbar tray icon that confirms LockPort is active; the tray menu includes **Show Device Window** and **Stop Monitoring** shortcuts. Add `--console-log` if you also want logs mirrored to the launching console.

- `python lockport_cli.py autostart <enable|disable|status>` – manage the scheduled task that launches `lockport_service.py` at logon with highest privileges so background monitoring is automatic.

> Tip: the service now enumerates any removable drives that were already connected when it started, so existing USB sticks also trigger the PIN prompt immediately.

- Append `--skip-current-check` to `set-pin` when running in an elevated admin session and the current PIN is unknown.

Device state snapshots are persisted at `%ProgramData%/LockPort/device_states.json`. The CLI simply surfaces this file so administrators can audit which ports/devices attempted to connect and whether they were unlocked.

## Testing

Run the focused unit tests (covers the PIN store logic) with:

```powershell
python -m pytest
```

## Notes & limitations

- Device disabling/enabling uses PowerShell `Disable-PnpDevice` / `Enable-PnpDevice` which require administrator privileges.
- On some hardware `Disable-PnpDevice` returns a generic failure; LockPort will automatically fall back to `pnputil /disable-device` / `pnputil /enable-device`, but these commands also require an elevated session.
- The Tkinter PIN prompt must run within an interactive desktop session; if the service is launched in Session 0 it will not be visible.
- The USB monitor uses WMI and currently targets mass-storage insert events (EventType `2`). Additional filtering or policy decisions (e.g., whitelists) can be added inside `lockport/service.py`.

## Branding assets

- Rebuild the app logo and favicon any time by running `python tools/generate_brand_assets.py` (requires `pip install -r requirements-dev.txt`).
- Outputs land in `assets/branding/` as high-resolution PNGs plus `lockport-favicon.ico` for the website/installer.
- Point PyInstaller’s `--icon` flag (or `lockport.wxs`) at the generated ICO to brand the binaries and MSI.

# LockPort MSI Packaging

This folder contains a minimal WiX/PowerShell toolchain for producing an MSI that installs
all end-user components (CLI/Device Window, tray helper, and background service) and
creates both Start Menu and Desktop shortcuts for the device window.

## Prerequisites

1. **Windows 10/11** with PowerShell 5.1+.
2. **Python** (same version used to develop LockPort). The existing `.venv` is reused.
3. Project dependencies installed: `pip install -r requirements.txt`.
4. `pyinstaller` available in the active environment:
   ```pwsh
   .\.venv\Scripts\Activate.ps1
   python -m pip install --upgrade pip pyinstaller
   ```
5. **WiX Toolset 3.11+** installed and `candle.exe` / `light.exe` added to your `PATH`.

## Building the installer

1. Activate the project virtual environment.
2. Run the build script (feel free to bump the semantic version):
   ```pwsh
   pwsh .\installer\build.ps1 -Version 1.2.0
   ```
3. The script performs the following:
   - Uses PyInstaller to create single-file executables for `lockport_cli.py`,
     `lockport_tray.py`, and `lockport_service.py`.
   - Copies those binaries into `installer\payload`.
   - Compiles the WiX source (`lockport.wxs`) into `LockPort-<version>.msi`
     under `installer\dist`.

## What the MSI installs

- Files placed in `Program Files\LockPort`:
  - `lockport-cli.exe` (CLI + device-window entry point)
  - `lockport-tray.exe` (system tray helper)
  - `lockport-service.exe` (background service runner)
- Start Menu shortcuts:
  - `LockPort Device Window` (launches `lockport-cli.exe device-window`)
  - `LockPort Tray` (launches the tray helper)
- Desktop shortcut for the device window (same target/arguments as above).

After installing, launch the Device Window, then optionally run the tray shortcut and/or
register autostart (e.g., `lockport-cli.exe autostart enable`).

## Customisation tips

- **Icons:** Replace `lockport-cli.exe` with an `.ico` in `lockport.wxs` for better branding.
- **License text:** Update `license.rtf` to include your real terms.
- **Versioning:** Pass `-Version` when running the script; WiX uses it for ProductVersion.
- **Additional files:** Drop them in `installer\payload` and add matching `<Component>`
  entries inside `lockport.wxs`.

## Troubleshooting

- If `candle.exe`/`light.exe` are not found, ensure the WiX bin directory is on `PATH` or
  edit `build.ps1` to point directly to the executables.
- PyInstaller outputs are cached in `installer\pyinstaller`. Delete the folder when
  switching Python versions or dependency sets.
- MSI builds require administrative privileges because the install scope is per-machine.

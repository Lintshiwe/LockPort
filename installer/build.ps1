param(
    [string]$Version = "1.0.0"
)

$ErrorActionPreference = "Stop"

$repoRoot = Resolve-Path (Join-Path $PSScriptRoot "..")
$python = if (Test-Path (Join-Path $repoRoot ".venv/Scripts/python.exe")) {
    Join-Path $repoRoot ".venv/Scripts/python.exe"
} else {
    "python"
}

Write-Host "Using Python: $python"

$pyInstallerArgs = @(
    "-m", "PyInstaller",
    "--clean",
    "--noconfirm",
    "--onefile"
)

$pyinstallerWork = Join-Path $PSScriptRoot "pyinstaller"
$payloadDir = Join-Path $PSScriptRoot "payload"
$objDir = Join-Path $PSScriptRoot "obj"
$distDir = Join-Path $PSScriptRoot "dist"

Remove-Item $pyinstallerWork -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $payloadDir -Recurse -Force -ErrorAction SilentlyContinue
Remove-Item $objDir -Recurse -Force -ErrorAction SilentlyContinue
New-Item -ItemType Directory -Path $pyinstallerWork | Out-Null
New-Item -ItemType Directory -Path $payloadDir | Out-Null
New-Item -ItemType Directory -Path $objDir | Out-Null
New-Item -ItemType Directory -Path $distDir -ErrorAction SilentlyContinue | Out-Null

function Invoke-PyInstallerBuild {
    param(
        [string]$EntryPoint,
        [string]$Name
    )

    $entryFull = Resolve-Path (Join-Path $repoRoot $EntryPoint)
    $args = @(
        $pyInstallerArgs,
        "--distpath", $payloadDir,
        "--workpath", $pyinstallerWork,
        "--specpath", $pyinstallerWork,
        "--name", $Name,
        $entryFull
    ) | ForEach-Object { $_ }
    Write-Host "Building $Name from $EntryPoint" -ForegroundColor Cyan
    & $python $args
}

Invoke-PyInstallerBuild -EntryPoint "lockport_cli.py" -Name "lockport-cli"
Invoke-PyInstallerBuild -EntryPoint "lockport_tray.py" -Name "lockport-tray"
Invoke-PyInstallerBuild -EntryPoint "lockport_service.py" -Name "lockport-service"

$wxsFile = Join-Path $PSScriptRoot "lockport.wxs"
$licenseFile = Resolve-Path (Join-Path $PSScriptRoot "license.rtf")
$wixObj = Join-Path $objDir "lockport.wixobj"
$msiPath = Join-Path $distDir ("LockPort-$Version.msi")

$candleArgs = @(
    "-dPayloadDir=$payloadDir",
    "-dLicenseFile=$licenseFile",
    "-dProductVersion=$Version",
    "-out", $wixObj,
    $wxsFile
)

$lightArgs = @(
    "-ext", "WixUIExtension",
    "-cultures:en-us",
    "-out", $msiPath,
    $wixObj
)

Write-Host "Running candle.exe" -ForegroundColor Cyan
candle.exe @candleArgs
Write-Host "Running light.exe" -ForegroundColor Cyan
light.exe @lightArgs

Write-Host "MSI created at $msiPath" -ForegroundColor Green

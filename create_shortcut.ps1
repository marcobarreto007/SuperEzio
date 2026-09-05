# Create a Windows desktop shortcut for the local SuperEzio launcher.

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$launchBat = Join-Path $ScriptDir "launch.bat"
if (-not (Test-Path -LiteralPath $launchBat)) {
    Write-Host "ERROR: launch.bat not found at $launchBat" -ForegroundColor Red
    exit 1
}

$desktop = [Environment]::GetFolderPath("Desktop")
$shortcutPath = Join-Path $desktop "SuperEzio.lnk"

$ws = New-Object -ComObject WScript.Shell
if (Test-Path -LiteralPath $shortcutPath) {
    Remove-Item -LiteralPath $shortcutPath -Force
}

$icoPath = Join-Path $ScriptDir "superezio.ico"
if (-not (Test-Path -LiteralPath $icoPath)) {
    $icoLocation = "cmd.exe,0"
} else {
    $icoLocation = "$icoPath,0"
}

$shortcut = $ws.CreateShortcut($shortcutPath)
$shortcut.TargetPath = $launchBat
$shortcut.WorkingDirectory = $ScriptDir
$shortcut.WindowStyle = 1
$shortcut.IconLocation = $icoLocation
$shortcut.Description = "SuperEzio - Quantitative AI Copilot"
$shortcut.Save()

if (Test-Path -LiteralPath $shortcutPath) {
    Write-Host "Shortcut created on Desktop:" -ForegroundColor Green
    Write-Host "  $shortcutPath"
} else {
    Write-Host "FAILED: Could not create shortcut" -ForegroundColor Red
    exit 1
}

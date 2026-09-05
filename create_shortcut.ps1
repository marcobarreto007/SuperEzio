# Create a Windows desktop shortcut for the local SuperEzio launcher.

$ErrorActionPreference = "Stop"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$launcherPath = Join-Path $ScriptDir "launcher.ps1"

if (-not (Test-Path -LiteralPath $launcherPath)) {
    Write-Host "ERROR: launcher.ps1 not found at $launcherPath" -ForegroundColor Red
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
    $icoPath = "powershell.exe,0"
} else {
    $icoPath = "$icoPath,0"
}

$shortcut = $ws.CreateShortcut($shortcutPath)
$shortcut.TargetPath = "powershell.exe"
$shortcut.Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$launcherPath`""
$shortcut.WorkingDirectory = $ScriptDir
$shortcut.WindowStyle = 1
$shortcut.IconLocation = $icoPath
$shortcut.Description = "SuperEzio - Quantitative AI Copilot"
$shortcut.Save()

if (Test-Path -LiteralPath $shortcutPath) {
    Write-Host "Shortcut created on Desktop:" -ForegroundColor Green
    Write-Host "  $shortcutPath"
} else {
    Write-Host "FAILED: Could not create shortcut" -ForegroundColor Red
    exit 1
}

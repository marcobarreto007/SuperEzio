# Install SuperEzio Watchdog as Windows Scheduled Task
# Run as Administrator: powershell -ExecutionPolicy Bypass -File runtime\install_watchdog.ps1

$ErrorActionPreference = 'Stop'

$root = 'C:\Users\marco\Desktop\SuperEzio Financeiro'
$taskName = 'SuperEzio_Watchdog'
$scriptPath = Join-Path $root 'runtime\watchdog_service.ps1'

Write-Host "=== Installing SuperEzio Watchdog Service ===" -ForegroundColor Cyan

# Check if script exists
if (-not (Test-Path $scriptPath)) {
    Write-Host "ERROR: Script not found: $scriptPath" -ForegroundColor Red
    exit 1
}

# Remove existing task if present
$existing = Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue
if ($existing) {
    Write-Host "Removing existing task..." -ForegroundColor Yellow
    Unregister-ScheduledTask -TaskName $taskName -Confirm:$false
}

# Create action
$action = New-ScheduledTaskAction `
    -Execute 'powershell.exe' `
    -Argument "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`"" `
    -WorkingDirectory $root

# Create trigger - start at boot
$triggerBoot = New-ScheduledTaskTrigger -AtStartup
$triggerLogon = New-ScheduledTaskTrigger -AtLogOn

# Create principal - run with highest privileges
$principal = New-ScheduledTaskPrincipal `
    -UserId 'SYSTEM' `
    -LogonType ServiceAccount `
    -RunLevel Highest

# Create settings
$settings = New-ScheduledTaskSettingsSet `
    -AllowStartIfOnBatteries `
    -DontStopIfGoingOnBatteries `
    -StartWhenAvailable `
    -RestartCount 3 `
    -RestartInterval (New-TimeSpan -Minutes 2)

# Register task
try {
    Register-ScheduledTask `
        -TaskName $taskName `
        -Action $action `
        -Trigger $triggerBoot, $triggerLogon `
        -Principal $principal `
        -Settings $settings `
        -Description 'SuperEzio Financeiro Watchdog - Monitors CEO (8082) and API (8002) health' `
        -ErrorAction Stop

    Write-Host "SUCCESS: Task '$taskName' installed" -ForegroundColor Green
    Write-Host "  - Runs at startup and logon" -ForegroundColor Green
    Write-Host "  - Auto-restart if crashed (3x with 2min delay)" -ForegroundColor Green
    Write-Host "  - Runs as SYSTEM (no user required)" -ForegroundColor Green
    Write-Host ""
    Write-Host "To verify:" -ForegroundColor Cyan
    Write-Host "  Get-ScheduledTask -TaskName '$taskName'" -ForegroundColor White
    Write-Host ""
    Write-Host "To uninstall:" -ForegroundColor Cyan
    Write-Host "  Unregister-ScheduledTask -TaskName '$taskName' -Confirm:`$false" -ForegroundColor White
    Write-Host ""
    Write-Host "To view logs:" -ForegroundColor Cyan
    Write-Host "  Get-Content '$root\runtime\logs\watchdog_service.log' -Wait" -ForegroundColor White

} catch {
    Write-Host "ERROR: Failed to register task: $_" -ForegroundColor Red
    exit 1
}

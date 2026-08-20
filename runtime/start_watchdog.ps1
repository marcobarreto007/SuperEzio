# RETIRED: the legacy watchdog lifecycle is intentionally fail-closed.
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
[Console]::Error.WriteLine("RETIRED: runtime/start_watchdog.ps1 is disabled. Start SuperEzio with '$root\start.ps1'.")
exit 2

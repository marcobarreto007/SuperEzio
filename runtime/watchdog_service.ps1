# RETIRED: the self-restarting watchdog service is intentionally fail-closed.
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
[Console]::Error.WriteLine("RETIRED: runtime/watchdog_service.ps1 is disabled. Use '$root\start.ps1' and '$root\stop.ps1'.")
exit 2

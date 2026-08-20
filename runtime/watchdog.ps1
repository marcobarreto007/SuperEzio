# RETIRED: the legacy watchdog could kill unrelated processes and bypass safety defaults.
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
[Console]::Error.WriteLine("RETIRED: runtime/watchdog.ps1 is disabled. Use '$root\start.ps1' and '$root\stop.ps1' for the official CEO :8080 / API :8002 lifecycle.")
exit 2

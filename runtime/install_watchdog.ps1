# RETIRED: no scheduled task may own the SuperEzio lifecycle.
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
[Console]::Error.WriteLine("RETIRED: runtime/install_watchdog.ps1 is disabled. Use '$root\start.ps1' and '$root\stop.ps1'.")
exit 2

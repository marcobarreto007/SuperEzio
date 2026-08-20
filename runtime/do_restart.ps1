# RETIRED: lifecycle ownership belongs exclusively to start.ps1 and stop.ps1.
$ErrorActionPreference = 'Continue'
$root = Split-Path -Parent $PSScriptRoot
[Console]::Error.WriteLine("RETIRED: runtime/do_restart.ps1 no longer manages SuperEzio. Use '$root\stop.ps1' followed by '$root\start.ps1'.")
exit 2

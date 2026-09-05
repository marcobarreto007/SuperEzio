# Elevated 3060 recovery. Do not touch llama-server :8080.
$ErrorActionPreference = "Continue"
$out = "C:\Users\marco\Desktop\SuperEzio\runtime\sre-3060-elevated-log.txt"
$inst = "PCI\VEN_10DE&DEV_2504&SUBSYS_397D1462&REV_A1\4&4FCAF60&0&0018"
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
"=== ELEVATED START $(Get-Date -Format o) IsAdmin=$isAdmin ===" | Out-File $out
function Snap([string]$Label) {
  "--- $Label ---" | Out-File -Append $out
  Get-PnpDevice -InstanceId $inst -ErrorAction SilentlyContinue | Select-Object Status, Problem, FriendlyName | Format-List | Out-File -Append $out
  nvidia-smi -L 2>&1 | Out-File -Append $out
}
Snap "BEFORE"

"=== ATTEMPT 1 disable/enable + scan ===" | Out-File -Append $out
$d1 = pnputil /disable-device "$inst" 2>&1
"disable: $d1" | Out-File -Append $out
Start-Sleep -Seconds 3
$e1 = pnputil /enable-device "$inst" 2>&1
"enable: $e1" | Out-File -Append $out
$s1 = pnputil /scan-devices 2>&1
"scan: $s1" | Out-File -Append $out
Start-Sleep -Seconds 5
Snap "AFTER ATTEMPT 1"

"=== ATTEMPT 2 restart + add-driver oem8.inf /install ===" | Out-File -Append $out
$r2 = pnputil /restart-device "$inst" 2>&1
"restart: $r2" | Out-File -Append $out
Start-Sleep -Seconds 3
$u2 = pnputil /add-driver "C:\Windows\INF\oem8.inf" /install 2>&1
"add-driver oem8.inf /install: $u2" | Out-File -Append $out
Start-Sleep -Seconds 8
Snap "AFTER ATTEMPT 2"

Get-CimInstance Win32_VideoController | Select-Object Name, Status, DriverVersion, ConfigManagerErrorCode | Format-List | Out-File -Append $out
"=== ELEVATED END $(Get-Date -Format o) ===" | Out-File -Append $out

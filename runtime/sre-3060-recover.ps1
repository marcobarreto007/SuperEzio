# Disposable PnP recovery for RTX 3060. Does not touch :8080 / llama-server.
$ErrorActionPreference = "Continue"
$out = "C:\Users\marco\Desktop\SuperEzio\runtime\sre-3060-recover-log.txt"
$inst = "PCI\VEN_10DE&DEV_2504&SUBSYS_397D1462&REV_A1\4&4FCAF60&0&0018"
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
"=== START $(Get-Date -Format o) IsAdmin=$isAdmin ===" | Out-File $out

function Snap {
    param([string]$Label)
    "--- $Label ---" | Out-File -Append $out
    Get-PnpDevice -InstanceId $inst -ErrorAction SilentlyContinue |
        Select-Object Status, Problem, FriendlyName, InstanceId |
        Format-List | Out-File -Append $out
    nvidia-smi -L 2>&1 | Out-File -Append $out
}

Snap "BEFORE"

"=== ATTEMPT 1 Disable/Enable + scan-devices ===" | Out-File -Append $out
try {
    Disable-PnpDevice -InstanceId $inst -Confirm:$false -ErrorAction Stop
    "Disable-PnpDevice: OK" | Out-File -Append $out
} catch {
    "Disable-PnpDevice: FAIL $($_.Exception.Message)" | Out-File -Append $out
}
Start-Sleep -Seconds 3
try {
    Enable-PnpDevice -InstanceId $inst -Confirm:$false -ErrorAction Stop
    "Enable-PnpDevice: OK" | Out-File -Append $out
} catch {
    "Enable-PnpDevice: FAIL $($_.Exception.Message)" | Out-File -Append $out
}
$scan1 = pnputil /scan-devices 2>&1
"pnputil /scan-devices: $scan1" | Out-File -Append $out
Start-Sleep -Seconds 5
Snap "AFTER ATTEMPT 1"

"=== ATTEMPT 2 restart-device + update-driver oem8.inf ===" | Out-File -Append $out
$rst = pnputil /restart-device "$inst" 2>&1
"pnputil /restart-device: $rst" | Out-File -Append $out
Start-Sleep -Seconds 4
$upd = pnputil /update-driver "C:\Windows\INF\oem8.inf" "$inst" 2>&1
"pnputil /update-driver oem8.inf: $upd" | Out-File -Append $out
Start-Sleep -Seconds 6
Snap "AFTER ATTEMPT 2"

"=== END $(Get-Date -Format o) ===" | Out-File -Append $out

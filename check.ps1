# SuperEzio CHECK script.
# Run once before start.ps1 to verify the buyer/demo machine.

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir

$global:Passes = 0
$global:Warns = 0
$global:Fails = 0
$global:FailMessages = @()

function Pass([string]$Msg) {
    Write-Host "  [PASS] $Msg" -ForegroundColor Green
    $global:Passes++
}

function Warn([string]$Msg) {
    Write-Host "  [WARN] $Msg" -ForegroundColor Yellow
    $global:Warns++
}

function Fail([string]$Msg, [string]$Fix) {
    Write-Host "  [FAIL] $Msg" -ForegroundColor Red
    $global:Fails++
    if ($Fix) {
        $global:FailMessages += "  -> FIX: $Fix"
    }
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  SuperEzio - System Check" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

$configPath = Join-Path $ScriptDir "config.ps1"
if (Test-Path $configPath) {
    . $configPath
} else {
    Fail "config.ps1 missing." "Restore the application installation."
    exit 1
}

Write-Host "--- Operating System ---" -ForegroundColor White
$os = Get-CimInstance Win32_OperatingSystem
$osName = $os.Caption
if ($osName -match "Windows 10|Windows 11") {
    Pass "Windows 10/11 detected: $osName"
} else {
    Warn "Non-Windows-10/11 OS: $osName. Tested on Windows 10/11."
}

$arch = $env:PROCESSOR_ARCHITECTURE
if ($arch -eq "AMD64" -or $arch -eq "ARM64") {
    Pass "64-bit: $arch"
} else {
    Fail "32-bit Windows. 64-bit required." "Use a 64-bit Windows machine."
}

Write-Host "--- Python ---" -ForegroundColor White
if ($PythonExe) {
    $pyVer = & $PythonExe --version 2>&1
    Pass "Python found: $pyVer ($PythonExe)"

    try {
        $null = & $PythonExe -m pip --version 2>&1
        if ($LASTEXITCODE -eq 0) {
            Pass "pip working"
        } else {
            Warn "pip check failed. Run: $PythonExe -m ensurepip --upgrade"
        }
    } catch {
        Warn "pip check failed. Run: $PythonExe -m ensurepip --upgrade"
    }

    try {
        $null = & $PythonExe -c "import agent_server" 2>&1
        if ($LASTEXITCODE -eq 0) {
            Pass "SuperEzio package importable"
        } else {
            Fail "SuperEzio package not importable." "Run: $PythonExe -m pip install -e ."
        }
    } catch {
        Fail "SuperEzio package not importable." "Run: $PythonExe -m pip install -e ."
    }
} else {
    Fail "Python 3.12+ not found." "Install Python 3.12.x 64-bit and add it to PATH."
}

Write-Host "--- Hardware ---" -ForegroundColor White
$totalRam = (Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory
$ramGB = [math]::Round($totalRam / 1GB)
if ($ramGB -ge 4) {
    Pass "RAM: ${ramGB} GB (cloud inference)"
} else {
    Warn "RAM: ${ramGB} GB. 4 GB+ recommended for the application."
}

$drive = (Get-Item $ScriptDir).PSDrive.Name
$freeBytes = (Get-PSDrive -Name $drive).Free
$diskGB = [math]::Round($freeBytes / 1GB)
if ($diskGB -ge 2) {
    Pass "Disk: ${diskGB} GB free"
} else {
    Fail "Disk: ${diskGB} GB free." "Free at least 2 GB for logs and local data."
}

Write-Host "--- Network ---" -ForegroundColor White
foreach ($port in @($ApiPort)) {
    $svc = "API"
    $owner = Get-SuperEzioPortOwner -Port $port
    if ($owner) {
        Fail "Port $port in use by PID $($owner.Pid) ($($owner.ProcessName)) [$svc]" "If SuperEzio is already running, this is expected. For a clean start, run stop.ps1 first."
    } else {
        Pass "Port $port free [$svc]"
    }
}

Write-Host "--- Configuration ---" -ForegroundColor White
if ((Test-Path $EnvFile) -or (Test-Path (Join-Path $ScriptDir ".env.local"))) {
    Pass "Local configuration file exists (provider credentials validated by the application)"
} elseif (Test-Path $EnvExampleFile) {
    Warn ".env missing. Copy .env.example to .env if you want external data/provider keys."
    Warn "Configure external model provider credentials before using the investment assistant."
} else {
    Fail ".env and .env.example missing." "Create a .env file from the documented template."
}

Write-Host "--- Python Packages ---" -ForegroundColor White
if ($PythonExe) {
    $missing = @()
    foreach ($dep in @("fastapi", "uvicorn", "langgraph", "yfinance", "openai", "pydantic", "httpx")) {
        try {
            $null = & $PythonExe -c "import $dep" 2>&1
            if ($LASTEXITCODE -ne 0) {
                $missing += $dep
            }
        } catch {
            $missing += $dep
        }
    }

    if ($missing.Count -eq 0) {
        Pass "All critical packages installed"
    } else {
        Fail "Missing packages: $($missing -join ', ')" "$PythonExe -m pip install -e ."
    }
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  CHECK COMPLETE" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Passed : $Passes" -ForegroundColor Green
Write-Host "  Warnings: $Warns" -ForegroundColor Yellow
$failColor = if ($Fails -eq 0) { "Green" } else { "Red" }
Write-Host "  Failed : $Fails" -ForegroundColor $failColor
Write-Host "============================================" -ForegroundColor Cyan

if ($global:FailMessages.Count -gt 0) {
    Write-Host ""
    Write-Host "HOW TO FIX:" -ForegroundColor Yellow
    foreach ($m in $global:FailMessages) {
        Write-Host $m -ForegroundColor White
    }
}

Write-Host ""
if ($Fails -eq 0) {
    Write-Host "All checks passed. Run: start.ps1" -ForegroundColor Green
    exit 0
}

Write-Host "Fix the $Fails failed check(s), then run check.ps1 again." -ForegroundColor Red
exit 1

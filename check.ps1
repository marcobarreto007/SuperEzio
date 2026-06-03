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
    $PythonExe = $null
    $LlamaServerPath = $null
    $ModelPath = Join-Path $ScriptDir "models"
    $CeoPort = 8082
    $ApiPort = 8002
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
    Fail "Python 3.11+ not found." "Install Python 3.12.x 64-bit and add it to PATH."
}

Write-Host "--- Hardware ---" -ForegroundColor White
$totalRam = (Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory
$ramGB = [math]::Round($totalRam / 1GB)
if ($ramGB -ge 48) {
    Pass "RAM: ${ramGB} GB"
} elseif ($ramGB -ge 32) {
    Warn "RAM: ${ramGB} GB. 48 GB+ recommended for the 80B model."
} else {
    Fail "RAM: ${ramGB} GB. 48 GB+ required for this kit." "Add RAM or use a smaller model."
}

if ($PythonExe) {
    try {
        $gpuAvailable = & $PythonExe -c "import torch; print(torch.cuda.is_available())" 2>&1
        if ($gpuAvailable -match "True") {
            $gpuName = & $PythonExe -c "import torch; print(torch.cuda.get_device_name(0))" 2>&1
            $vramRaw = & $PythonExe -c "import torch; print(torch.cuda.get_device_properties(0).total_memory // 1024 // 1024)" 2>&1
            $vramMB = [int]$vramRaw
            Pass "GPU: $gpuName (${vramMB} MB VRAM)"
        } else {
            Warn "No CUDA GPU detected. The model may run CPU-only."
        }
    } catch {
        Warn "Could not check GPU through torch."
    }
} else {
    Warn "GPU check skipped because Python was not found."
}

$drive = (Get-Item $ScriptDir).PSDrive.Name
$freeBytes = (Get-PSDrive -Name $drive).Free
$diskGB = [math]::Round($freeBytes / 1GB)
if ($diskGB -ge 60) {
    Pass "Disk: ${diskGB} GB free"
} elseif ($diskGB -ge 40) {
    Warn "Disk: ${diskGB} GB free. This is tight; model needs roughly 47 GB."
} else {
    Fail "Disk: ${diskGB} GB free." "Free space or use an external SSD."
}

Write-Host "--- llama.cpp ---" -ForegroundColor White
if ($LlamaServerPath) {
    Pass "llama-server: $LlamaServerPath"
    $verOut = ""
    try {
        $verOut = & $LlamaServerPath --version 2>&1 | Select-Object -First 1
    } catch {}

    if ($verOut) {
        Pass "llama-server runs"
    } else {
        Warn "llama-server found but version check failed."
    }

    $isCuda = ($LlamaServerPath -match "cuda|build-cuda") -or ($verOut -match "cuda")
    if ($isCuda) {
        Pass "CUDA-capable llama.cpp path/version"
    } else {
        Warn "Non-CUDA build detected. GPU acceleration may be unavailable."
    }
} else {
    Fail "llama-server.exe not found." "Set `$env:SUPEREZIO_LLAMA_SERVER_EXE or install llama.cpp."
}

Write-Host "--- Model ---" -ForegroundColor White
if ($ModelPath -and (Test-Path $ModelPath)) {
    $modelSizeGB = [math]::Round((Get-Item $ModelPath).Length / 1GB)
    Pass "Model: ${modelSizeGB} GB ($ModelPath)"
} else {
    if (-not (Test-Path $ModelsDir)) {
        New-Item -ItemType Directory -Force -Path $ModelsDir | Out-Null
    }
    Fail "Model not found." "Download the GGUF model to: $ModelsDir"
}

Write-Host "--- Network ---" -ForegroundColor White
foreach ($port in @($CeoPort, $ApiPort)) {
    $svc = if ($port -eq $CeoPort) { "CEO" } else { "API" }
    $owner = Get-SuperEzioPortOwner -Port $port
    if ($owner) {
        Fail "Port $port in use by PID $($owner.Pid) ($($owner.ProcessName)) [$svc]" "If SuperEzio is already running, this is expected. For a clean start, run stop.ps1 first."
    } else {
        Pass "Port $port free [$svc]"
    }
}

Write-Host "--- Configuration ---" -ForegroundColor White
if (Test-Path $EnvFile) {
    Pass ".env exists"
} elseif (Test-Path $EnvExampleFile) {
    Warn ".env missing. Copy .env.example to .env if you want external data/provider keys."
    Warn "The local CEO can run without cloud keys, but data/expert coverage may be reduced."
} else {
    Fail ".env and .env.example missing." "Create a .env file from the documented template."
}

Write-Host "--- Python Packages ---" -ForegroundColor White
if ($PythonExe) {
    $missing = @()
    foreach ($dep in @("fastapi", "uvicorn", "langgraph", "yfinance", "torch", "openai", "pydantic", "httpx")) {
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

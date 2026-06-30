# ============================================================================
# F51 MoE Selective Backward - Build and Test Script
# ============================================================================
#
# This script:
# 1. Applies the selective backward patch to llama.cpp
# 2. Builds with MoE optimizations enabled
# 3. Tests training with memory tracking
#
# Usage:
#   .\scripts\build_moe_fix.ps1 -LlamaPath "path\to\llama.cpp"
#
# ============================================================================

param(
    [Parameter(Mandatory=$false)]
    [string]$LlamaPath = "C:\Users\marco\Desktop\llama.cpp",

    [Parameter(Mandatory=$false)]
    [string]$Model = "models\bob_core_local.gguf",

    [Parameter(Mandatory=$false)]
    [string]$Dataset = "data\10K_finance.json",

    [Parameter(Mandatory=$false)]
    [switch]$SkipPatch,

    [Parameter(Mandatory=$false)]
    [switch]$SkipBuild,

    [Parameter(Mandatory=$false)]
    [switch]$Verbose
)

# ============================================================================
# Functions
# ============================================================================

function Write-Log {
    param([string]$Message, [string]$Level = "INFO")

    $timestamp = Get-Date -Format "HH:mm:ss"
    $color = switch ($Level) {
        "INFO"  { "Cyan" }
        "WARN"  { "Yellow" }
        "ERROR" { "Red" }
        "SUCCESS" { "Green" }
        default { "White" }
    }

    Write-Host "[$timestamp] " -NoNewline -ForegroundColor Gray
    Write-Host "[$Level] " -NoNewline -ForegroundColor $color
    Write-Host $Message
}

function Test-Prerequisites {
    Write-Log "Checking prerequisites..."

    # Check CUDA
    $nvcc = nvcc --version 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Log "✓ CUDA found" -Level "SUCCESS"
        if ($Verbose) {
            nvcc --version | Select-Object -First 3
        }
    } else {
        Write-Log "✗ CUDA not found" -Level "ERROR"
        return $false
    }

    # Check Python
    $python = python --version 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Log "✓ Python found: $python" -Level "SUCCESS"
    } else {
        Write-Log "✗ Python not found" -Level "ERROR"
        return $false
    }

    # Check CMake
    $cmake = cmake --version 2>$null
    if ($LASTEXITCODE -eq 0) {
        Write-Log "✓ CMake found" -Level "SUCCESS"
    } else {
        Write-Log "✗ CMake not found" -Level "ERROR"
        return $false
    }

    return $true
}

function Apply-Patch {
    param(
        [string]$LlamaPath,
        [string]$PatchPath
    )

    Write-Log "Applying selective backward patch..."

    $patchFile = Get-Item $PatchPath -ErrorAction SilentlyContinue
    if (-not $patchFile) {
        Write-Log "Patch file not found: $PatchPath" -Level "ERROR"
        return $false
    }

    Push-Location $LlamaPath

    # Check if patch command exists
    $patchCmd = Get-Command patch -ErrorAction SilentlyContinue

    if ($patchCmd) {
        # Use patch command
        Write-Log "Using patch command..."
        patch -p1 --dry-run --ignore-whitespace < $PatchPath
        if ($LASTEXITCODE -ne 0) {
            Write-Log "Patch dry-run failed. File may already be patched." -Level "WARN"
            return $true
        }

        patch -p1 --ignore-whitespace < $PatchPath
        if ($LASTEXITCODE -eq 0) {
            Write-Log "✓ Patch applied successfully" -Level "SUCCESS"
            Pop-Location
            return $true
        } else {
            Write-Log "✗ Patch failed with exit code $LASTEXITCODE" -Level "ERROR"
            Pop-Location
            return $false
        }
    } else {
        # Manual patch application (fallback)
        Write-Log "Patch command not found. Manual patch required." -Level "WARN"
        Write-Log "Please apply the changes manually from: $PatchPath"
        Pop-Location
        return $false
    }
}

function Build-llama-cpp {
    param([string]$LlamaPath)

    Write-Log "Building llama.cpp with MoE optimizations..."

    Push-Location $LlamaPath

    # Create build directory
    if (-not (Test-Path "build")) {
        New-Item -ItemType Directory -Path "build" -Force | Out-Null
    }

    Push-Location build

    # Configure with MoE flags
    Write-Log "Configuring CMake..."
    cmake .. `
        -DGGML_CUDA=ON `
        -DGGML_CUDA_FORCE_MMQ=OFF `
        -DGGML_USE_MOE_SELECTIVE_BACKWARD=ON `
        -DCMAKE_BUILD_TYPE=Release

    if ($LASTEXITCODE -ne 0) {
        Write-Log "✗ CMake configuration failed" -Level "ERROR"
        Pop-Location
        Pop-Location
        return $false
    }

    # Build
    Write-Log "Compiling..."
    cmake --build . --config Release -j

    if ($LASTEXITCODE -eq 0) {
        Write-Log "✓ Build successful" -Level "SUCCESS"
        Pop-Location
        Pop-Location
        return $true
    } else {
        Write-Log "✗ Build failed with exit code $LASTEXITCODE" -Level "ERROR"
        Pop-Location
        Pop-Location
        return $false
    }
}

function Test-MoE-Training {
    param(
        [string]$LlamaPath,
        [string]$Model,
        [string]$Dataset
    )

    Write-Log "Testing MoE training with memory tracking..."

    $trainExe = Join-Path $LlamaPath "build\bin\Release\train-text-from-scratch.exe"

    if (-not (Test-Path $trainExe)) {
        Write-Log "Train executable not found: $trainExe" -Level "WARN"
        $trainExe = Join-Path $LlamaPath "build\bin\train-text-from-scratch.exe"
    }

    if (-not (Test-Path $trainExe)) {
        Write-Log "✗ Train executable not found" -Level "ERROR"
        Write-Log "Please build llama.cpp first"
        return $false
    }

    # Test with minimal parameters
    $testArgs = @(
        "--model", $Model
        "--train-data", $Dataset
        "--vocab", "models\vocab_qwen.gguf"
        "--checkpoint", "test_checkpoint"
        "--output", "test_output.gguf"
        "--grad-accum", "1"
        "--grad-batch", "1"
        "--threads", "8"
        "--batch", "4"
        "--use-moe-selective-backward"
        "--moe-max-active-experts", "16"
        "--use-gradient-checkpointing"
        "--epochs", "1"
    )

    Write-Log "Running test training..."
    Write-Log "Command: $trainExe $($testArgs -join ' ')"

    $process = Start-Process -FilePath $trainExe -ArgumentList $testArgs `
        -NoNewWindow -PassThru -RedirectStandardOutput "test_stdout.log" `
        -RedirectStandardError "test_stderr.log"

    # Monitor for 30 seconds
    Write-Log "Monitoring training (30s)..."
    $timeout = 30
    $elapsed = 0

    while (-not $process.HasExited -and $elapsed -lt $timeout) {
        Start-Sleep -Seconds 5
        $elapsed += 5

        # Check memory usage
        if ($Verbose) {
            $gpus = Get-CimInstance Win32_VideoController | Where-Object { $_.Name -like "*NVIDIA*" }
            foreach ($gpu in $gpus) {
                Write-Log "GPU: $($gpu.Name), Memory: $($gpu.AdapterRAM / 1GB)GB"
            }
        }
    }

    if ($process.HasExited) {
        $exitCode = $process.ExitCode

        # Check logs
        $stderr = Get-Content "test_stderr.log" -Raw -ErrorAction SilentlyContinue
        $stdout = Get-Content "test_stdout.log" -Raw -ErrorAction SilentlyContinue

        if ($exitCode -eq 0) {
            Write-Log "✓ Test training completed successfully" -Level "SUCCESS"

            # Extract memory stats
            if ($stdout -match "MoE gradient memory: ([\d.]+) GB") {
                Write-Log "Gradient memory: $($matches[1]) GB" -Level "SUCCESS"
            }
        } else {
            Write-Log "✗ Test training failed with exit code $exitCode" -Level "ERROR"

            # Check for CUDA OOM
            if ($stderr -match "CUDA out of memory" -or $stderr -match "cuMemAlloc") {
                Write-Log "CUDA OOM detected. Patch may need adjustments." -Level "ERROR"
            }

            if ($Verbose) {
                Write-Log "STDERR:" -Level "WARN"
                Write-Log $stderr -Level "WARN"
            }
        }

        # Cleanup logs
        Remove-Item "test_stdout.log", "test_stderr.log" -ErrorAction SilentlyContinue
    } else {
        Write-Log "Test still running after ${timeout}s. Terminating..." -Level "WARN"
        $process.Kill()
    }

    return $true
}

# ============================================================================
# Main
# ============================================================================

Write-Log "========================================"
Write-Log "F51 MoE Selective Backward Build"
Write-Log "========================================"
Write-Log "llama.cpp path: $LlamaPath"
Write-Log "Model: $Model"
Write-Log "Dataset: $Dataset"
Write-Log "========================================"

# Check prerequisites
if (-not (Test-Prerequisites)) {
    Write-Log "Prerequisites check failed" -Level "ERROR"
    exit 1
}

# Get patch path
$patchPath = Join-Path $PSScriptRoot "..\patches\moe_selective_backward.patch"
$patchPath = Resolve-Path $patchPath -ErrorAction SilentlyContinue

if (-not $patchPath) {
    Write-Log "Patch file not found: $patchPath" -Level "ERROR"
    exit 1
}

# Apply patch
if (-not $SkipPatch) {
    if (-not (Apply-Patch -LlamaPath $LlamaPath -PatchPath $patchPath)) {
        Write-Log "Patch application failed" -Level "ERROR"
        exit 1
    }
} else {
    Write-Log "Skipping patch application (--skip-patch)"
}

# Build
if (-not $SkipBuild) {
    if (-not (Build-llama-cpp -LlamaPath $LlamaPath)) {
        Write-Log "Build failed" -Level "ERROR"
        exit 1
    }
} else {
    Write-Log "Skipping build (--skip-build)"
}

# Test
Write-Log "Running test training..."
Test-MoE-Training -LlamaPath $LlamaPath -Model $Model -Dataset $Dataset

Write-Log "========================================"
Write-Log "Build and test complete!"
Write-Log "========================================"

# Summary
Write-Log ""
Write-Log "Next steps:"
Write-Log "1. If test passed: Run full training with --use-moe-selective-backward"
Write-Log "2. If test failed: Check test_stderr.log for CUDA errors"
Write-Log "3. Monitor memory with nvidia-smi during training"
Write-Log ""
Write-Log "Training command example:"
Write-Log "  train-text-from-scratch.exe --model $Model --train-data $Dataset --use-moe-selective-backward --moe-max-active-experts 16 --use-gradient-checkpointing"

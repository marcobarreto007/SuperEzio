# SuperEzio cleanup preview for packaging.
# Default mode is preview only. Use -Apply only on a packaging copy, not on the
# working source tree.

param(
    [switch]$Apply,
    [switch]$DryRun,
    [switch]$RemoveGit,
    [switch]$RemoveF51Checkpoints,
    [switch]$RemoveEvidenceOutput
)

$ErrorActionPreference = "Continue"
$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $ScriptDir
$Root = (Resolve-Path -LiteralPath $ScriptDir).Path
$PreviewOnly = (-not $Apply) -or $DryRun

$script:ItemsTouched = 0
$script:SpaceMB = 0.0

function Test-UnderRoot {
    param([Parameter(Mandatory = $true)][string]$Path)
    $resolved = (Resolve-Path -LiteralPath $Path -ErrorAction Stop).Path
    return $resolved.StartsWith($Root, [System.StringComparison]::OrdinalIgnoreCase)
}

function Get-SizeMB {
    param([Parameter(Mandatory = $true)][string]$Path)
    try {
        if (Test-Path -LiteralPath $Path -PathType Leaf) {
            return [math]::Round((Get-Item -LiteralPath $Path).Length / 1MB, 1)
        }
        $sum = (Get-ChildItem -LiteralPath $Path -Recurse -File -ErrorAction SilentlyContinue |
            Measure-Object -Property Length -Sum).Sum
        if ($null -eq $sum) {
            $sum = 0
        }
        return [math]::Round($sum / 1MB, 1)
    } catch {
        return 0.0
    }
}

function Remove-PackageTarget {
    param(
        [Parameter(Mandatory = $true)][string]$RelativePath,
        [Parameter(Mandatory = $true)][string]$Label
    )

    $target = Join-Path $Root $RelativePath
    if (-not (Test-Path -LiteralPath $target)) {
        Write-Host "  [KEEP] $Label (not found)" -ForegroundColor Gray
        return
    }

    if (-not (Test-UnderRoot -Path $target)) {
        Write-Host "  [SKIP] $Label (outside project root)" -ForegroundColor Red
        return
    }

    $sizeMB = Get-SizeMB -Path $target
    if ($PreviewOnly) {
        Write-Host "  [DRY] Would remove: $Label (${sizeMB} MB)" -ForegroundColor Yellow
    } else {
        Remove-Item -LiteralPath $target -Recurse -Force -ErrorAction SilentlyContinue
        Write-Host "  [DEL] $Label (${sizeMB} MB)" -ForegroundColor Green
    }
    $script:ItemsTouched++
    $script:SpaceMB += $sizeMB
}

function Remove-FoundItems {
    param(
        $Items,
        [Parameter(Mandatory = $true)][string]$Label
    )

    $list = @($Items | Where-Object { $_ -and $_.FullName })
    if ($list.Count -eq 0) {
        Write-Host "  [KEEP] $Label (none found)" -ForegroundColor Gray
        return
    }

    $sizeMB = 0.0
    foreach ($item in $list) {
        if (Test-UnderRoot -Path $item.FullName) {
            $sizeMB += Get-SizeMB -Path $item.FullName
        }
    }

    if ($PreviewOnly) {
        Write-Host "  [DRY] Would remove: $Label ($($list.Count) item(s), ${sizeMB} MB)" -ForegroundColor Yellow
    } else {
        foreach ($item in $list) {
            if (Test-UnderRoot -Path $item.FullName) {
                Remove-Item -LiteralPath $item.FullName -Recurse -Force -ErrorAction SilentlyContinue
            }
        }
        Write-Host "  [DEL] $Label ($($list.Count) item(s), ${sizeMB} MB)" -ForegroundColor Green
    }
    $script:ItemsTouched += $list.Count
    $script:SpaceMB += $sizeMB
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  SuperEzio - Packaging Cleanup" -ForegroundColor Cyan
Write-Host "============================================" -ForegroundColor Cyan
if ($PreviewOnly) {
    Write-Host "  Mode: preview only. Add -Apply to delete." -ForegroundColor Yellow
} else {
    Write-Host "  Mode: APPLY. Deleting selected generated files." -ForegroundColor Red
}
Write-Host ""

Write-Host "--- Python caches ---" -ForegroundColor White
$pycacheDirs = Get-ChildItem -LiteralPath $Root -Recurse -Directory -Filter "__pycache__" -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch "\\\.venv\\" -and $_.FullName -notmatch "\\models\\" -and $_.FullName -notmatch "\\\.git\\" }
Remove-FoundItems -Items $pycacheDirs -Label "__pycache__ directories"

$pycFiles = Get-ChildItem -LiteralPath $Root -Recurse -File -Filter "*.pyc" -ErrorAction SilentlyContinue |
    Where-Object { $_.FullName -notmatch "\\\.venv\\" -and $_.FullName -notmatch "\\models\\" -and $_.FullName -notmatch "\\\.git\\" }
Remove-FoundItems -Items $pycFiles -Label ".pyc files"

Remove-PackageTarget ".ruff_cache" "ruff cache"
Remove-PackageTarget ".pytest_cache" "pytest cache"
Remove-PackageTarget ".playwright-cli" "playwright CLI cache"
Remove-PackageTarget ".playwright-mcp" "playwright MCP cache"

Write-Host "--- Build artifacts ---" -ForegroundColor White
$eggInfo = Get-ChildItem -LiteralPath $Root -Directory -Filter "*.egg-info" -ErrorAction SilentlyContinue
Remove-FoundItems -Items $eggInfo -Label "egg-info directories"
Remove-PackageTarget "build" "build directory"
Remove-PackageTarget "dist" "dist directory"

Write-Host "--- Runtime artifacts ---" -ForegroundColor White
Remove-PackageTarget "runtime\logs" "runtime logs"
Remove-PackageTarget "runtime\api_stderr.log" "API stderr"
Remove-PackageTarget "runtime\api_stdout.log" "API stdout"
Remove-PackageTarget "runtime\frontend_stderr.log" "frontend stderr"
Remove-PackageTarget "runtime\frontend_stdout.log" "frontend stdout"
Remove-PackageTarget "runtime\restart_log.txt" "restart log"
Remove-PackageTarget "reports" "reports directory"

if ($RemoveEvidenceOutput) {
    Remove-PackageTarget "output" "generated evidence/output directory"
} else {
    Write-Host "  [KEEP] output directory (evidence output kept; use -RemoveEvidenceOutput to remove)" -ForegroundColor Gray
}

if ($RemoveF51Checkpoints) {
    Remove-PackageTarget ".f51\checkpoints" "F51 checkpoints"
} else {
    Write-Host "  [KEEP] .f51 checkpoints (source-of-truth evidence kept)" -ForegroundColor Gray
}

Write-Host "--- Git metadata ---" -ForegroundColor White
if ($RemoveGit) {
    Remove-PackageTarget ".git" "git history"
    Remove-PackageTarget ".gitignore" ".gitignore"
    Remove-PackageTarget ".gitattributes" ".gitattributes"
    Remove-PackageTarget ".pre-commit-config.yaml" "pre-commit config"
} else {
    Write-Host "  [KEEP] git metadata (use -RemoveGit only on a copied package folder)" -ForegroundColor Gray
}

Write-Host "--- Security ---" -ForegroundColor White
$envReal = Join-Path $Root ".env"
if (Test-Path -LiteralPath $envReal) {
    $content = Get-Content -LiteralPath $envReal -Raw
    if ($content -match "sk-|AIza|hf_|CG-|API[_-]?KEY=.*[A-Za-z0-9]{12}") {
        Write-Host "  [WARN] .env may contain real keys. Do not distribute it." -ForegroundColor Red
        Write-Host "         Package .env.example instead." -ForegroundColor Yellow
    } else {
        Write-Host "  [OK] .env found; no obvious key pattern detected." -ForegroundColor Green
    }
} else {
    Write-Host "  [OK] .env not present in root." -ForegroundColor Green
}

Write-Host ""
Write-Host "============================================" -ForegroundColor Cyan
if ($PreviewOnly) {
    Write-Host "  PREVIEW COMPLETE - nothing removed" -ForegroundColor Yellow
} else {
    Write-Host "  CLEAN COMPLETE" -ForegroundColor Green
}
Write-Host "============================================" -ForegroundColor Cyan
Write-Host "  Items selected: $ItemsTouched" -ForegroundColor White
Write-Host "  Space total  : $([math]::Round($SpaceMB, 1)) MB" -ForegroundColor White
Write-Host "============================================" -ForegroundColor Cyan
Write-Host ""

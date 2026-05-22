# =============================================================================
# OPUS MISSION §12 — Zero Garbage Runtime v1 Verification
# =============================================================================
# Runs the contract + runtime + provider + trace test suites that gate the
# mission, plus ruff lint/format checks. Designed to be safe on a developer
# laptop: no real API calls (Finnhub tests are mocked), no real network I/O.
#
# Usage (from repo root):
#   pwsh -File scripts/verify_zero_garbage_runtime.ps1
#   pwsh -File scripts/verify_zero_garbage_runtime.ps1 -SkipLint
#   pwsh -File scripts/verify_zero_garbage_runtime.ps1 -StopOnFirstFailure:$false
#
# Exit codes:
#   0  all suites passed
#   1+ number of failing suites
# =============================================================================

[CmdletBinding()]
param(
    [switch]$SkipLint,
    [switch]$StopOnFirstFailure = $true
)

$ErrorActionPreference = 'Stop'
$repoRoot = Split-Path -Parent $PSScriptRoot
Set-Location $repoRoot

$env:PYTHONPATH = "src"

# ---- Secret hygiene guard (OPUS §0) -----------------------------------------
# Block obvious Finnhub key leaks BEFORE we run any test that could print it.
# Real Finnhub keys are 20+ lowercase alphanumerics ending in cv* or similar;
# we use a conservative pattern that matches the known repo key shape.
$leakPattern = '[a-z0-9]{18,}cv[a-z0-9]{2,}'
$tracked = @()
try {
    $tracked = git ls-files 2>$null
} catch {
    # git not available — skip leak guard silently
}
if ($tracked) {
    $leakHits = $tracked |
        Where-Object { $_ -notmatch '^(\.env(\..+)?|.*\.lock|.*\.pyc)$' } |
        Where-Object { Test-Path $_ } |
        ForEach-Object {
            $file = $_
            Select-String -Path $file -Pattern $leakPattern -CaseSensitive -SimpleMatch:$false -ErrorAction SilentlyContinue |
                ForEach-Object { [pscustomobject]@{ File = $file; Line = $_.LineNumber } }
        }
    if ($leakHits) {
        Write-Host "[X] SECRET LEAK GUARD: Finnhub-style key found in tracked files:" -ForegroundColor Red
        $leakHits | ForEach-Object { Write-Host "   $($_.File):$($_.Line)" -ForegroundColor Red }
        exit 99
    }
}

# ---- .env.example placeholder guard (OPUS §0) -------------------------------
# .env.example must exist, must declare FINNHUB_API_KEY=, and must NOT carry a
# real-looking value. Production env vars added by the pre-delivery audit are
# also asserted so the template stays current.
$envExample = Join-Path $repoRoot '.env.example'
if (-not (Test-Path $envExample)) {
    Write-Host "[X] .env.example missing." -ForegroundColor Red
    exit 98
}
$envText = Get-Content $envExample -Raw
$requiredKeys = @(
    'FINNHUB_API_KEY=',
    'SUPEREZIO_CEO_BASE_URL=',
    'SUPEREZIO_HOST=',
    'SUPEREZIO_PORT='
)
$missing = $requiredKeys | Where-Object { $envText -notmatch [regex]::Escape($_) }
if ($missing) {
    Write-Host "[X] .env.example missing required placeholders:" -ForegroundColor Red
    $missing | ForEach-Object { Write-Host "   $_" -ForegroundColor Red }
    exit 97
}
# Reject any FINNHUB_API_KEY line that smells like a real key (has 18+ chars after =).
if ($envText -match 'FINNHUB_API_KEY=\S{18,}') {
    Write-Host "[X] .env.example carries a real-looking FINNHUB_API_KEY value." -ForegroundColor Red
    exit 96
}

# ---- Boot smoke (OPUS §9) ---------------------------------------------------
# Imports agent_server.main without binding sockets. Catches ImportError
# landmines (e.g. the collect_experts regression) before the test suites run.
Write-Host ""
Write-Host "[>] Boot smoke (import agent_server.main)" -ForegroundColor Cyan
$bootProbe = "import importlib, sys; sys.path.insert(0, 'src'); importlib.import_module('agent_server.main'); print('[OK] agent_server.main importable')"
& python -c $bootProbe
if ($LASTEXITCODE -ne 0) {
    Write-Host "[X] Boot smoke failed (see traceback above)." -ForegroundColor Red
    exit 95
}

if ($env:FINNHUB_API_KEY) {
    Write-Host ""
    Write-Host "[>] Live DataHub price smoke (AAPL via Finnhub)" -ForegroundColor Cyan
    & python scripts/smoke_datahub_price.py
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[X] Live DataHub price smoke failed (check FINNHUB_API_KEY / network)." -ForegroundColor Red
        exit 94
    }
}

# ---- Suite definitions ------------------------------------------------------
$suites = @(
    @{ Name = 'collect_experts shim regression (Test L)';                 Cmd = 'python -m pytest tests/test_collect_experts_shim.py -x --tb=short' },
    @{ Name = 'Finnhub provider contract (Tests G, H)';                   Cmd = 'python -m pytest tests/test_finnhub_provider.py -x --tb=short' },
    @{ Name = 'Finnhub symbol normalization';                             Cmd = 'python -m pytest tests/test_finnhub_symbols.py -x --tb=short' },
    @{ Name = 'No-empty-response + §8 trace (Test K-strengthened)';       Cmd = 'python -m pytest tests/test_no_empty_response_and_trace.py -x --tb=short' },
    @{ Name = 'Market scan candidate gate (Tests D, E, F, I)';            Cmd = 'python -m pytest tests/test_market_scan_candidate_gate.py -x --tb=short' },
    @{ Name = 'Market scanner unit (universe + filters)';                 Cmd = 'python -m pytest tests/test_market_scanner.py -x --tb=short' },
    @{ Name = 'Agent market_scan loop (compliance + structure)';          Cmd = 'python -m pytest tests/test_agent_market_scan_loop.py -x --tb=short' },
    @{ Name = 'Complex finance contract (Tests A, B, C)';                 Cmd = 'python -m pytest tests/contracts/test_contract_complex_finance.py -x --tb=short' },
    @{ Name = 'Runtime Bob fixes (context leak, empty guard)';            Cmd = 'python -m pytest tests/test_runtime_bob_fixes.py -x --tb=short' },
    @{ Name = '/task/submit integration smoke';                           Cmd = 'python -m pytest tests/test_integration_runtime.py -k task_submit -x --tb=short' }
)

if (-not $SkipLint) {
    $suites += @{ Name = 'ruff check';          Cmd = 'python -m ruff check .' }
    $suites += @{ Name = 'ruff format --check'; Cmd = 'python -m ruff format --check .' }
}

# ---- Runner -----------------------------------------------------------------
$results = @()
$failures = 0
foreach ($s in $suites) {
    Write-Host ""
    Write-Host "[>] $($s.Name)" -ForegroundColor Cyan
    Write-Host "  $($s.Cmd)" -ForegroundColor DarkGray
    $started = Get-Date
    & cmd /c "$($s.Cmd) 2>&1" | Tee-Object -Variable suiteOutput | Out-Host
    $exit = $LASTEXITCODE
    $elapsed = (Get-Date) - $started
    $status = if ($exit -eq 0) { 'PASS' } else { 'FAIL' }
    if ($exit -ne 0) { $failures++ }
    $results += [pscustomobject]@{
        Suite   = $s.Name
        Status  = $status
        Exit    = $exit
        Elapsed = '{0:N1}s' -f $elapsed.TotalSeconds
    }
    if ($exit -ne 0 -and $StopOnFirstFailure) { break }
}

# ---- Summary ----------------------------------------------------------------
Write-Host ""
Write-Host "=============================================================" -ForegroundColor White
Write-Host " OPUS Pre-Delivery Gate - Verification Summary" -ForegroundColor White
Write-Host "=============================================================" -ForegroundColor White
$results | Format-Table -AutoSize | Out-String | Write-Host
if ($failures -eq 0) {
    Write-Host "[OK] All gates passed. System cleared for delivery." -ForegroundColor Green
    Write-Host "     Next: review DELIVERY.md for handoff checklist." -ForegroundColor DarkGray
    exit 0
} else {
    Write-Host "[X] $failures suite(s) failed - delivery BLOCKED." -ForegroundColor Red
    exit $failures
}

# Parent verification after P0-P5 parallel implementers.
# Does not invent Heart success. Live ranking empty is a real empty state.
$ErrorActionPreference = 'Continue'
$Root = Split-Path -Parent $PSScriptRoot
$Py = Join-Path $Root '.venv\Scripts\python.exe'
$env:PYTHONPATH = Join-Path $Root 'src'

Write-Output '===== pytest heart ====='
& $Py -m pytest (Join-Path $Root 'tests') -q --tb=line -k 'heart_'
Write-Output "pytest_exit=$LASTEXITCODE"

Write-Output '===== disk ====='
$heart = Join-Path $Root 'data\heart'
Write-Output ("data_heart_exists=" + (Test-Path $heart))
if (Test-Path $heart) {
  Get-ChildItem $heart -Recurse -File | ForEach-Object {
    Write-Output ("FILE {0} bytes={1}" -f $_.FullName.Substring($Root.Length), $_.Length)
  }
}

Write-Output '===== live ranking ====='
try {
  $r = Invoke-WebRequest -Uri 'http://127.0.0.1:8002/api/heart/ranking' -UseBasicParsing -TimeoutSec 15
  Write-Output ("ranking_status=" + $r.StatusCode)
  Write-Output $r.Content.Substring(0, [Math]::Min(800, $r.Content.Length))
} catch {
  Write-Output ("ranking_fail=" + $_.Exception.Message)
}

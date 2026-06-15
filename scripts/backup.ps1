# SuperEzio Backup — copia dados criticos para disco secundario
param(
    [string]$BackupDir = "D:\backups\superezio",
    [int]$KeepDays = 7
)

$ErrorActionPreference = "Stop"
$date = Get-Date -Format "yyyyMMdd-HHmm"
$dest = Join-Path $BackupDir $date
$root = Split-Path $PSScriptRoot -Parent

Write-Host "=== SuperEzio Backup ===" -ForegroundColor Green
Write-Host "Destino: $dest"

New-Item -ItemType Directory -Force -Path "$dest\data", "$dest\config", "$dest\.f51", "$dest\runtime" | Out-Null

$dirs = @(
    @{Src="data";     Exclude=@()},
    @{Src="config";   Exclude=@()},
    @{Src=".f51";     Exclude=@("cache")},
    @{Src="runtime";  Exclude=@("logs")}
)

foreach ($d in $dirs) {
    $srcPath = Join-Path $root $d.Src
    $dstPath = Join-Path $dest $d.Src
    Write-Host "  $($d.Src) ..." -NoNewline
    robocopy $srcPath $dstPath /MIR /NP /NFL /NDL /NJH /NJS | Out-Null
    Write-Host " OK" -ForegroundColor Green
}

# Verify integrity
Write-Host "`nVerificando integridade..."
$db = Join-Path $dest "data\investor.db"
if (Test-Path $db) {
    Write-Host "  investor.db: OK ($((Get-Item $db).Length) bytes)"
} else {
    Write-Host "  investor.db: MISSING" -ForegroundColor Red
}

$mem = Join-Path $dest "data\conversation_memory.jsonl"
if (Test-Path $mem) {
    $lines = (Get-Content $mem | Measure-Object).Count
    Write-Host "  conversation_memory.jsonl: $lines linhas"
} else {
    Write-Host "  conversation_memory.jsonl: MISSING" -ForegroundColor Red
}

# Rotation
$oldBackups = Get-ChildItem $BackupDir -Directory | 
    Where-Object { $_.Name -match "^\d{8}-\d{4}$" } |
    Sort-Object Name -Desc |
    Select-Object -Skip ($KeepDays * 24)
    
if ($oldBackups) {
    Write-Host "`nLimpando backups antigos ($($oldBackups.Count) pastas)..."
    $oldBackups | Remove-Item -Recurse -Force
}

Write-Host "`nBackup concluido: $date" -ForegroundColor Green

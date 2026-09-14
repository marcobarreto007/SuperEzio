# Cria o atalho na Area de Trabalho para matar e reiniciar os servidores do SuperEzio
param(
    [string]$DesktopPath = [Environment]::GetFolderPath("Desktop")
)

$ErrorActionPreference = "Stop"
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
$BatPath = Join-Path $ProjectRoot "scripts\restart_superezio.bat"
$IconPath = Join-Path $ProjectRoot "superezio.ico"
$ShortcutPath = Join-Path $DesktopPath "Reiniciar SuperEzio.lnk"

if (-not (Test-Path -LiteralPath $BatPath)) {
    throw "Script alvo nao encontrado: $BatPath"
}

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($ShortcutPath)
$shortcut.TargetPath = $BatPath
$shortcut.WorkingDirectory = $ProjectRoot
$shortcut.WindowStyle = 1
$shortcut.Description = "Mata e reinicia os servidores do SuperEzio (:8002) com um clique."

if (Test-Path -LiteralPath $IconPath) {
    $shortcut.IconLocation = "$IconPath,0"
}

$shortcut.Save()

if (Test-Path -LiteralPath $ShortcutPath) {
    Write-Host "Atalho criado com sucesso na Area de Trabalho!" -ForegroundColor Green
    Write-Host "  Atalho: $ShortcutPath" -ForegroundColor Cyan
    Write-Host "  Alvo:   $BatPath" -ForegroundColor DarkGray
    Write-Host "  Icone:  $IconPath" -ForegroundColor DarkGray
} else {
    Write-Host "[ERRO] Nao foi possivel criar o atalho." -ForegroundColor Red
    exit 1
}

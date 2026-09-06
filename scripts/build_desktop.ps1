param([switch]$SkipBackend)
$ErrorActionPreference = 'Stop'
$root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Push-Location $root
try {
    if (-not $SkipBackend) {
        python -m PyInstaller desktop/backend.spec --noconfirm --distpath dist/desktop-backend --workpath runtime/desktop-build
        if ($LASTEXITCODE -ne 0) { throw 'Backend build failed.' }
    }
    Push-Location (Join-Path $root 'desktop')
    try {
        $env:ELECTRON_MIRROR = 'https://npmmirror.com/mirrors/electron/'
        $env:ELECTRON_BUILDER_BINARIES_MIRROR = 'https://npmmirror.com/mirrors/electron-builder-binaries/'
        $env:CSC_IDENTITY_AUTO_DISCOVERY = 'false'
        npm.cmd ci --ignore-scripts --no-audit --no-fund
        if ($LASTEXITCODE -ne 0) { throw 'Node dependency install failed.' }
        node node_modules/electron/install.js
        if ($LASTEXITCODE -ne 0) { throw 'Electron runtime download failed.' }
        npm.cmd test
        if ($LASTEXITCODE -ne 0) { throw 'Desktop tests failed.' }
        npm.cmd run dist
        if ($LASTEXITCODE -ne 0) { throw 'Windows installer build failed.' }
    } finally { Pop-Location }
    Get-ChildItem (Join-Path $root 'dist/windows') -Filter '*.exe' | ForEach-Object {
        $hash = (Get-FileHash -LiteralPath $_.FullName -Algorithm SHA256).Hash.ToLowerInvariant()
        "$hash  $($_.Name)" | Set-Content -LiteralPath ($_.FullName + '.sha256') -Encoding ascii
    }
} finally { Pop-Location }

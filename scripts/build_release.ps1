param(
    [string]$OutputDirectory = ""
)

$ErrorActionPreference = "Stop"
$Root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path
if (-not $OutputDirectory) {
    $OutputDirectory = Join-Path $Root "dist\release"
}
$OutputDirectory = [System.IO.Path]::GetFullPath($OutputDirectory)

$allowedRoots = @(
    ".claude/agents/",
    ".claude/commands/",
    ".claude/skills/",
    ".f51/",
    "config/",
    "docs/",
    "frontend/",
    "models/",
    "scripts/",
    "src/",
    "templates/",
    "tests/"
)
$allowedData = @(
    "data/eval_questions.jsonl",
    "data/intent_golden.jsonl",
    "data/fraud_patterns/",
    "data/macro_dataset/"
)
$allowedTopFiles = @(
    ".env.example",
    "AGENTS.md",
    "CLAUDE.md",
    "DELIVERY.md",
    "LICENSE",
    "README.md",
    "README_FIRST.md",
    "ROADMAP.md",
    "check.ps1",
    "clean.ps1",
    "config.ps1",
    "create_shortcut.ps1",
    "launcher.ps1",
    "pyproject.toml",
    "pytest.ini",
    "requirements-lock.txt",
    "setup_superezio.bat",
    "start.ps1",
    "start_all.bat",
    "stop.ps1",
    "superezio_launcher.bat"
)
$deniedPrefixes = @(
    ".agent_bus/",
    ".claude/settings",
    ".f51/cache/",
    ".f51/checkpoints/",
    ".f51/partner/",
    ".f51/tmp/",
    ".git/",
    "data/man_at_work/",
    "journal/",
    "output/",
    "reports/",
    "runtime/"
)
$deniedNames = @(".env", ".env.local", ".env.local.bak", "credentials.json")

function Test-ReleasePath {
    param([Parameter(Mandatory = $true)][string]$Path)
    $normalized = $Path.Replace("\", "/")
    $lowered = $normalized.ToLowerInvariant()
    if ($deniedNames -contains $lowered) { return $false }
    foreach ($prefix in $deniedPrefixes) {
        if ($lowered.StartsWith($prefix)) { return $false }
    }
    if ($allowedTopFiles -contains $normalized) { return $true }
    foreach ($prefix in $allowedData) {
        if ($normalized -eq $prefix -or $normalized.StartsWith($prefix)) { return $true }
    }
    foreach ($prefix in $allowedRoots) {
        if ($normalized.StartsWith($prefix)) { return $true }
    }
    return $false
}

function Get-SuperEzioSHA256 {
    param([Parameter(Mandatory = $true)][string]$Path)
    $stream = [System.IO.File]::OpenRead($Path)
    try {
        $algorithm = [System.Security.Cryptography.SHA256]::Create()
        try {
            $bytes = $algorithm.ComputeHash($stream)
            return ([System.BitConverter]::ToString($bytes)).Replace("-", "").ToLowerInvariant()
        }
        finally {
            $algorithm.Dispose()
        }
    }
    finally {
        $stream.Dispose()
    }
}

Push-Location $Root
try {
    $commit = (& git rev-parse HEAD).Trim()
    if ($LASTEXITCODE -ne 0 -or -not $commit) {
        throw "A local Git HEAD is required to build an auditable release."
    }
    $commitDate = (& git show -s --format=%cI HEAD).Trim()
    $tracked = @(& git ls-files)
    if ($LASTEXITCODE -ne 0) { throw "Could not enumerate tracked files." }
    $releasePaths = @($tracked | Where-Object { Test-ReleasePath $_ } | Sort-Object -Unique)
    if ($releasePaths.Count -lt 100) {
        throw "Release allowlist selected too few files: $($releasePaths.Count)."
    }

    New-Item -ItemType Directory -Force -Path $OutputDirectory | Out-Null
    $tempBase = [System.IO.Path]::GetFullPath([System.IO.Path]::GetTempPath())
    $tempRoot = Join-Path $tempBase ("superezio-release-" + [guid]::NewGuid().ToString("N"))
    $resolvedTemp = [System.IO.Path]::GetFullPath($tempRoot)
    if (-not $resolvedTemp.StartsWith($tempBase, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Unsafe temporary release path."
    }
    New-Item -ItemType Directory -Path $resolvedTemp | Out-Null

    try {
        $sourceZip = Join-Path $resolvedTemp "source.zip"
        & git archive --format=zip --prefix="SuperEzio-V1/" -o $sourceZip HEAD -- @releasePaths
        if ($LASTEXITCODE -ne 0) { throw "git archive failed." }
        $expanded = Join-Path $resolvedTemp "expanded"
        Expand-Archive -LiteralPath $sourceZip -DestinationPath $expanded
        $productRoot = Join-Path $expanded "SuperEzio-V1"

        $productPrefix = $productRoot.TrimEnd("\") + "\"
        $entries = @(
            Get-ChildItem -LiteralPath $productRoot -File -Recurse | ForEach-Object {
                if (-not $_.FullName.StartsWith($productPrefix, [System.StringComparison]::OrdinalIgnoreCase)) {
                    throw "Release file escaped the staging root."
                }
                $relative = $_.FullName.Substring($productPrefix.Length).Replace("\", "/")
                [ordered]@{
                    path = $relative
                    bytes = $_.Length
                    sha256 = Get-SuperEzioSHA256 -Path $_.FullName
                }
            } | Sort-Object { $_.path }
        )
        $manifest = [ordered]@{
            schema_version = 1
            product = "SuperEzio-V1"
            source_commit = $commit
            source_commit_date = $commitDate
            file_count = $entries.Count
            safety_boundary = "research-only; no broker transport; no real-capital authorization"
            files = $entries
        }
        $manifestJson = $manifest | ConvertTo-Json -Depth 6
        $manifestPath = Join-Path $productRoot "RELEASE_MANIFEST.json"
        [System.IO.File]::WriteAllText($manifestPath, $manifestJson + "`n", [System.Text.UTF8Encoding]::new($false))

        $shortCommit = $commit.Substring(0, 12)
        $zipPath = Join-Path $OutputDirectory "SuperEzio-V1-$shortCommit.zip"
        if (Test-Path -LiteralPath $zipPath) { Remove-Item -LiteralPath $zipPath -Force }
        Compress-Archive -LiteralPath $productRoot -DestinationPath $zipPath -CompressionLevel Optimal
        $zipHash = Get-SuperEzioSHA256 -Path $zipPath
        $checksumPath = "$zipPath.sha256"
        [System.IO.File]::WriteAllText(
            $checksumPath,
            "$zipHash  $([System.IO.Path]::GetFileName($zipPath))`n",
            [System.Text.UTF8Encoding]::new($false)
        )
        Copy-Item -LiteralPath $manifestPath -Destination (Join-Path $OutputDirectory "RELEASE_MANIFEST.json") -Force
        Write-Output ([ordered]@{
            zip = $zipPath
            sha256 = $zipHash
            checksum = $checksumPath
            manifest = (Join-Path $OutputDirectory "RELEASE_MANIFEST.json")
            files = $entries.Count
            source_commit = $commit
        } | ConvertTo-Json -Compress)
    }
    finally {
        if (Test-Path -LiteralPath $resolvedTemp) {
            Remove-Item -LiteralPath $resolvedTemp -Recurse -Force
        }
    }
}
finally {
    Pop-Location
}

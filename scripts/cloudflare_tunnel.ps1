# SuperEzio — Cloudflare Tunnel setup helper (public deploy plan 2026-08-22).
# DISK ONLY: nothing here touches GitHub. The tunnel routes ONLY the API/UI
# on 127.0.0.1:8002. The local CEO llama-server (:8080) is NEVER exposed.
#
# Operator-only steps (require the Cloudflare account — run by the operator,
# not by agents):
#   1. winget install --id Cloudflare.cloudflared
#   2. cloudflared tunnel login                       (opens the dashboard)
#   3. cloudflared tunnel create superezio            (prints the tunnel UUID)
#   4. .\scripts\cloudflare_tunnel.ps1 -TunnelId <UUID>   (writes config.yml)
#   5. cloudflared tunnel run superezio               (foreground test)
#   6. cloudflared service install                    (Windows service, admin)

param(
    [Parameter(Mandatory = $true)]
    [string]$TunnelId
)

$ErrorActionPreference = "Stop"
$CloudflaredDir = Join-Path $env:USERPROFILE ".cloudflared"

if (-not (Get-Command cloudflared -ErrorAction SilentlyContinue)) {
    Write-Host "ERROR: cloudflared not found. Install it first:" -ForegroundColor Red
    Write-Host "  winget install --id Cloudflare.cloudflared" -ForegroundColor Yellow
    exit 1
}

if (-not (Test-Path (Join-Path $CloudflaredDir "$TunnelId.json"))) {
    Write-Host "ERROR: credential file $CloudflaredDir\$TunnelId.json not found." -ForegroundColor Red
    Write-Host "  Run 'cloudflared tunnel login' and 'cloudflared tunnel create superezio' first." -ForegroundColor Yellow
    exit 1
}

$config = @"
tunnel: $TunnelId
credentials-file: $CloudflaredDir\$TunnelId.json
ingress:
  - hostname: supereziorealtime.com
    service: http://127.0.0.1:8002
  - service: http_status:404
"@

$configPath = Join-Path $CloudflaredDir "config.yml"
Set-Content -Path $configPath -Value $config -Encoding UTF8
Write-Host "Wrote $configPath" -ForegroundColor Green
Write-Host ""
Write-Host "SAFETY CHECKS (mandatory before running the tunnel):" -ForegroundColor Cyan
Write-Host "  1. JWT fail-closed is ACTIVE locally (curl /auth/me must return 401)" -ForegroundColor Yellow
Write-Host "     python scripts/verify_public_gate.py --base-url http://127.0.0.1:8002" -ForegroundColor Yellow
Write-Host "  2. This config exposes ONLY 127.0.0.1:8002 — :8080 (CEO llama-server)" -ForegroundColor Yellow
Write-Host "     must never appear in the ingress." -ForegroundColor Yellow
Write-Host "  3. Next operator steps: 'cloudflared tunnel run superezio', then" -ForegroundColor Yellow
Write-Host "     'cloudflared tunnel route dns superezio supereziorealtime.com'." -ForegroundColor Yellow
Write-Host ""
Write-Host "ROLLBACK: 'cloudflared service uninstall' + remove the DNS CNAME in the" -ForegroundColor Cyan
Write-Host "Cloudflare dashboard. JWT stays active — never revert to dev mode." -ForegroundColor Cyan

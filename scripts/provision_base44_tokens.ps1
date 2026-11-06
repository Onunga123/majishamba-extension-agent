# Provision the demo API tokens a Base44 Superagent needs for Phase 3.
#
# Run this on the environment that owns the database you will demo against
# (your local dev DB, or a Render shell: `python manage.py shell`-adjacent
# `python manage.py generate_api_token …`). It creates ONE officer token and
# ONE supervisor token (the "second human" Phase 3 acceptance requires) and
# prints each raw token exactly once — paste them into Base44 encrypted secrets.
#
# Usage (PowerShell, Windows):
#   .\scripts\provision_base44_tokens.ps1 -OfficerUser jane.officer -SupervisorUser john.supervisor
#
# Required env: DJANGO_SETTINGS_MODULE=config.settings.development (local) or
# config/settings/production.py on Render.

param(
    [Parameter(Mandatory=$true)][string]$OfficerUser,
    [Parameter(Mandatory=$true)][string]$SupervisorUser,
    [int]$Days = 90
)

$ErrorActionPreference = "Stop"

Write-Host "Provisioning Base44 demo tokens (valid $Days days)..." -ForegroundColor Cyan
Write-Host "Paste each raw token into Base44 encrypted secrets (KACHIENG_API_TOKEN / KACHIENG_API_TOKEN_SUPERVISOR)." -ForegroundColor Cyan
Write-Host ""

Write-Host "=== Officer token (request advisories + read) ===" -ForegroundColor Green
python manage.py generate_api_token `
    --user $OfficerUser `
    --name "base44-demo-officer" `
    --scopes advisories:request advisories:read token:introspect `
    --days $Days

Write-Host ""
Write-Host "=== Supervisor token (second human: read + approve) ===" -ForegroundColor Green
python manage.py generate_api_token `
    --user $SupervisorUser `
    --name "base44-demo-supervisor" `
    --scopes advisories:request advisories:read approvals:record token:introspect `
    --days $Days

Write-Host ""
Write-Host "Done. The raw tokens above are shown ONCE; only their SHA-256 hash is stored." -ForegroundColor Yellow
Write-Host "Revoke later with: POST /api/v1/token/revoke/ (Bearer <the token>)." -ForegroundColor Yellow

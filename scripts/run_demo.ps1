# scripts/run_demo.ps1 — Windows PowerShell equivalent of `make demo`.
# Run from a fresh clone:
#   cd C:\path\to\majishamba-extension-agent
#   .\scripts\run_demo.ps1
#
# What it does:
#   1. Creates a Python venv at .venv\
#   2. Installs the project + dev deps
#   3. Applies migrations (SQLite by default — works without PostgreSQL)
#   4. Loads synthetic Kachieng Ward fixtures
#   5. Seeds the demo officer / supervisor / viewer
#   6. Pulls qwen2.5:7b-instruct via Ollama if installed (skipped gracefully otherwise)
#   7. Starts the Django dev server on http://127.0.0.1:8000
#
# Demo logins:
#   nyatike_officer    / majishamba-demo-2025  (extension_officer — can request + approve)
#   nyatike_supervisor / majishamba-demo-2025  (supervisor — can approve)
#   nyatike_viewer     / majishamba-demo-2025  (viewer — read-only)

$ErrorActionPreference = "Stop"

Write-Host "==> Step 1: Create venv" -ForegroundColor Cyan
if (-not (Test-Path .venv)) {
    python -m venv .venv
}
if (-not (Test-Path .venv\Scripts\python.exe)) {
    Write-Error "Failed to create venv at .venv\Scripts\python.exe"
    exit 1
}

Write-Host "==> Step 2: Install dependencies (this takes a few minutes)" -ForegroundColor Cyan
.venv\Scripts\python.exe -m pip install --upgrade pip --quiet
.venv\Scripts\python.exe -m pip install -e ".[dev]" --quiet
if ($LASTEXITCODE -ne 0) {
    Write-Error "pip install failed; check pyproject.toml"
    exit 1
}

Write-Host "==> Step 3: Apply migrations" -ForegroundColor Cyan
.venv\Scripts\python.exe manage.py migrate --noinput
if ($LASTEXITCODE -ne 0) { Write-Error "Migrations failed"; exit 1 }

Write-Host "==> Step 4: Load synthetic Kachieng fixtures + seed 14 clusters + demo users" -ForegroundColor Cyan
.venv\Scripts\python.exe manage.py loaddata `
    data\fixtures\migori_kachieng_clusters.json `
    data\fixtures\migori_kachieng_plots.json `
    data\fixtures\migori_crop_calendars.json `
    data\fixtures\nyatike_weather_signals.json `
    data\fixtures\migori_pest_alerts.json `
    data\fixtures\migori_market_prices.json `
    --ignorenonexistent
.venv\Scripts\python.exe manage.py seed_kachieng_clusters
.venv\Scripts\python.exe scripts\load_demo_data.py

Write-Host "==> Step 5: Ollama (optional)" -ForegroundColor Cyan
$ollamaCmd = Get-Command ollama -ErrorAction SilentlyContinue
if ($ollamaCmd) {
    Write-Host "    Ollama found. Ensuring service is running..."
    Start-Process -FilePath ollama -ArgumentList "serve" -NoNewWindow -RedirectStandardOutput $env:TEMP\ollama.log -RedirectStandardError $env:TEMP\ollama.err
    Start-Sleep -Seconds 2
    Write-Host "    Pulling qwen2.5:7b-instruct (first run takes several minutes)..."
    ollama pull qwen2.5:7b-instruct
} else {
    Write-Host "    Ollama not installed. The agent will use the deterministic fallback template." -ForegroundColor Yellow
    Write-Host "    Install Ollama from https://ollama.com to enable the open-weights model run."
}

Write-Host "==> Step 6: Start Django dev server" -ForegroundColor Cyan
Write-Host "    Open http://127.0.0.1:8000 and log in as nyatike_officer / majishamba-demo-2025" -ForegroundColor Green
$env:MAJISHAMBA_SKIP_OLLAMA = "0"  # Let the agent try Ollama in the demo
.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000

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
#   5. Seeds 14 Kachieng pilot clusters
#   6. Uses OpenRouter cloud inference when LLM_PROVIDER/OPENROUTER_API_KEY are configured;
#      Ollama remains an optional local alternative.
#   7. Starts the Django dev server on http://127.0.0.1:8000
#
# Synthetic demo accounts are NO LONGER seeded. To create a real officer for
# local testing, run:
#   .venv\Scripts\python.exe manage.py create_officer --username jdoe `
#       --full-name "John Doe" --role extension_officer --sub-county Nyatike --ward Kachieng
#   .venv\Scripts\python.exe manage.py changepassword jdoe

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

Write-Host "==> Step 4: Load synthetic Kachieng fixtures + seed 14 clusters" -ForegroundColor Cyan
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
Write-Host "    (Synthetic demo accounts are no longer seeded.)" -ForegroundColor Yellow
Write-Host "    To create a real officer for testing, run:" -ForegroundColor Yellow
Write-Host "      .venv\Scripts\python.exe manage.py create_officer --username jdoe --full-name 'John Doe' --role extension_officer" -ForegroundColor Yellow
Write-Host "      .venv\Scripts\python.exe manage.py changepassword jdoe" -ForegroundColor Yellow

Write-Host "==> Step 5: Select LLM provider" -ForegroundColor Cyan
$envFile = Join-Path (Get-Location) ".env"
if (-not (Test-Path $envFile)) {
    Copy-Item ".env.example" $envFile
    Write-Host "    Created .env from .env.example. Add OPENROUTER_API_KEY locally before starting the server." -ForegroundColor Yellow
}
$envText = Get-Content $envFile -Raw
$envProviderMatch = [regex]::Match($envText, '(?m)^\s*LLM_PROVIDER\s*=\s*([^\r\n#]+)')
$fileProvider = if ($envProviderMatch.Success) { $envProviderMatch.Groups[1].Value.Trim().Trim('"').Trim("'") } else { "" }
$provider = if ($env:LLM_PROVIDER) { $env:LLM_PROVIDER } elseif ($fileProvider) { $fileProvider } else { "openrouter" }
if ($provider -eq "openrouter" -and -not $env:OPENROUTER_API_KEY -and (Get-Content $envFile -Raw) -notmatch "OPENROUTER_API_KEY=(?!your_openrouter_api_key_here)[^\r\n]+") {
    $env:OPENROUTER_API_KEY = Read-Host "Enter OpenRouter API key for this session"
}
if ($provider -eq "openrouter" -and -not $env:OPENROUTER_API_KEY) {
    Write-Host "    OpenRouter selected but OPENROUTER_API_KEY is not set; the agent will use the deterministic fallback." -ForegroundColor Yellow
    Write-Host "    Set `$env:OPENROUTER_API_KEY in this session before starting the server to enable cloud inference." -ForegroundColor Yellow
}

Write-Host "    Provider: $provider" -ForegroundColor Green
Write-Host "    Cloud OpenRouter responses are recorded as llm_openrouter; failures remain fallback_template." -ForegroundColor DarkGray

Write-Host "==> Step 6: Ollama (optional local alternative)" -ForegroundColor Cyan
$ollamaCmd = Get-Command ollama -ErrorAction SilentlyContinue
if ($ollamaCmd -and $provider -eq "ollama") {
    Write-Host "    Ollama found. Ensuring service is running..."
    Start-Process -FilePath ollama -ArgumentList "serve" -NoNewWindow -RedirectStandardOutput $env:TEMP\ollama.log -RedirectStandardError $env:TEMP\ollama.err
    Start-Sleep -Seconds 2
    Write-Host "    Pulling qwen2.5:7b-instruct (first run takes several minutes)..."
    ollama pull qwen2.5:7b-instruct
} elseif ($provider -eq "ollama") {
    Write-Host "    Ollama not installed. The agent will use the deterministic fallback template." -ForegroundColor Yellow
    Write-Host "    Install Ollama from https://ollama.com and pull qwen2.5:7b-instruct to enable local inference."
}

Write-Host "==> Step 7: Start Django dev server" -ForegroundColor Cyan
Write-Host "    Open http://127.0.0.1:8000/accounts/login/ and sign in with your real officer account." -ForegroundColor Green
Write-Host "    (No synthetic demo accounts are seeded. Use 'create_officer' to make one.)" -ForegroundColor Yellow
$env:MAJISHAMBA_SKIP_OLLAMA = if ($provider -eq "ollama") { "0" } else { "1" }
.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000

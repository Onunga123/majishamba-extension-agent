#!/usr/bin/env bash
# scripts/setup_ollama.sh — pulls Qwen2.5-7B-Instruct via Ollama if available.
# Called by `make ollama`. Safe to run multiple times.
set -euo pipefail

if ! command -v ollama >/dev/null 2>&1; then
  echo "==> Ollama not installed. Install from https://ollama.com to enable the open-weights model run."
  echo "    The agent will use the deterministic fallback template."
  exit 0
fi

# Start ollama serve if not already running
if ! curl -s http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "==> Starting ollama serve..."
  ollama serve >/tmp/ollama.log 2>&1 &
  sleep 2
fi

echo "==> Pulling qwen2.5:7b-instruct (first run may take several minutes)..."
ollama pull qwen2.5:7b-instruct

echo "==> Done. Use OLLAMA_HOST=http://127.0.0.1:11434 and OLLAMA_MODEL=qwen2.5:7b-instruct."

"""Management command to diagnose LLM provider configuration.

Usage: python manage.py diagnose_llm
"""
from __future__ import annotations

import os
from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Diagnose LLM provider configuration and test the connection."

    def handle(self, *args, **options):
        self.stdout.write("=== LLM Provider Diagnostics ===")
        self.stdout.write("")

        from pathlib import Path
        env_path = Path(".env")
        if env_path.exists():
            self.stdout.write(f".env file: FOUND at {env_path.resolve()}")
            for line in env_path.read_text().splitlines():
                line = line.strip()
                if not line or line.startswith("#"):
                    continue
                key = line.split("=")[0]
                if "KEY" in key.upper() or "SECRET" in key.upper() or "PASSWORD" in key.upper():
                    val = line.split("=", 1)[1] if "=" in line else ""
                    self.stdout.write(f"  {key}={'[SET]' if val else '[EMPTY]'}")
                else:
                    self.stdout.write(f"  {line}")
        else:
            self.stdout.write(self.style.WARNING(".env file: NOT FOUND"))
        self.stdout.write("")

        self.stdout.write("Environment variables:")
        for var in ["LLM_PROVIDER", "OPENROUTER_API_KEY", "OPENROUTER_MODEL", "MAJISHAMBA_SKIP_OLLAMA"]:
            val = os.environ.get(var)
            if val is None:
                self.stdout.write(f"  {var}: (not set)")
            elif "KEY" in var.upper() or "SECRET" in var.upper():
                self.stdout.write(f"  {var}: {'[SET]' if val else '[EMPTY]'}")
            else:
                self.stdout.write(f"  {var}: {val}")
        self.stdout.write("")

        from apps.agents.llm_provider import get_llm_provider, is_openrouter_configured, provider_status
        provider = get_llm_provider()
        self.stdout.write(f"Active provider: {provider}")
        self.stdout.write(f"OpenRouter configured: {is_openrouter_configured()}")
        status = provider_status()
        self.stdout.write(f"OpenRouter model: {status.get('openrouter_model', '?')}")
        self.stdout.write("")

        if provider == "openrouter" and is_openrouter_configured():
            self.stdout.write("Making test call to OpenRouter...")
            from apps.agents.llm_provider import call_llm
            result = call_llm("Respond with the single word OK")
            if result:
                self.stdout.write(self.style.SUCCESS(f"  SUCCESS: model={result['model']}, elapsed={result['elapsed_s']}s"))
            else:
                self.stdout.write(self.style.ERROR("  FAILED: call_llm returned None"))
        else:
            self.stdout.write(self.style.WARNING("No LLM provider configured — will use deterministic template."))

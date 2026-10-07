"""Health/readiness endpoint for production monitoring.

GET /health/ returns JSON:
{
  "status": "ok" | "degraded",
  "database": "ok" | "error",
  "migrations_pending": false,
  "llm_provider": "openrouter" | "ollama" | "none",
  "weather_provider": "open_meteo",
  "version": "0.1.0"
}

Does NOT require authentication. Does NOT expose secrets.
"""
from __future__ import annotations

import json

from django.http import JsonResponse
from django.views import View


class HealthCheckView(View):
    """Lightweight health check for load balancers and monitoring."""

    def get(self, request):
        status = "ok"
        checks = {}

        # Database check
        try:
            from django.db import connection
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1")
                cursor.fetchone()
            checks["database"] = "ok"
        except Exception:
            checks["database"] = "error"
            status = "degraded"

        # Migrations check
        try:
            from django.core.management import call_command
            from io import StringIO
            out = StringIO()
            call_command("showmigrations", "--list", stdout=out, no_color=True)
            pending = "[ ]" in out.getvalue()
            checks["migrations_pending"] = pending
            if pending:
                status = "degraded"
        except Exception:
            checks["migrations_pending"] = "unknown"

        # LLM provider
        import os
        checks["llm_provider"] = os.environ.get("LLM_PROVIDER", "none")
        checks["weather_provider"] = os.environ.get("WEATHER_PROVIDER", "open_meteo")

        return JsonResponse({
            "status": status,
            **checks,
            "version": "0.1.0",
        })

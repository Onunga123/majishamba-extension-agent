"""Base Django settings for MajiShamba Extension Agent.

Defaults are tuned so the demo runs without PostgreSQL/PostGIS/Ollama.
Override via environment variables (see `env_bool`, `env_str`).
"""
from __future__ import annotations

import os
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent.parent

# Load .env file if it exists (for local dev — production uses real env vars).
# This ensures LLM_PROVIDER, OPENROUTER_API_KEY, etc. are available to the
# Django dev server without manual env var export.
_env_file = BASE_DIR / ".env"
if _env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_file)
    except ImportError:
        pass  # python-dotenv not installed — rely on real env vars


def env_bool(name: str, default: bool = False) -> bool:
    val = os.environ.get(name)
    if val is None:
        return default
    return val.lower() in {"1", "true", "yes", "on"}


def env_str(name: str, default: str) -> str:
    return os.environ.get(name, default)


def env_list(name: str, default: list[str]) -> list[str]:
    val = os.environ.get(name)
    if not val:
        return list(default)
    return [item.strip() for item in val.split(",") if item.strip()]


# --- Core identity ----------------------------------------------------------
SECRET_KEY = env_str(
    "MAJISHAMBA_SECRET_KEY",
    "django-insecure-change-me-in-production-please-use-a-real-secret-key",
)
DEBUG = env_bool("MAJISHAMBA_DEBUG", False)
ALLOWED_HOSTS = env_list("MAJISHAMBA_ALLOWED_HOSTS", ["127.0.0.1", "localhost", "0.0.0.0"])

# --- Apps -------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "django_htmx",
    # MajiShamba domain apps
    "apps.accounts",
    "apps.geography",
    "apps.governance",  # Provenance mixin (no models of its own, but used for app registry)
    "apps.clusters",
    "apps.plots",
    "apps.calendars",
    "apps.weather",
    "apps.pests",
    "apps.markets",
    "apps.advisories",
    "apps.approvals",
    "apps.tasks",
    "apps.audit",
    "apps.agents",
    "apps.mcp_tools",
    "apps.integrations",
    "apps.dashboard",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "apps.audit.middleware.AuditMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "apps.accounts.context_processors.active_officer",
                "apps.dashboard.context_processors.nav_badges",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# --- Database ---------------------------------------------------------------
# Demo default = SQLite (works everywhere). Set USE_POSTGRES=1 to switch.
if env_bool("USE_POSTGRES", False):
    DATABASES = {
        "default": {
            "ENGINE": env_str("MAJISHAMBA_DB_ENGINE", "django.contrib.gis.db.backends.postgis"
            if env_bool("USE_POSTGIS", False) else "django.db.backends.postgresql"),
            "NAME": env_str("MAJISHAMBA_DB_NAME", "majishamba"),
            "USER": env_str("MAJISHAMBA_DB_USER", "majishamba"),
            "PASSWORD": env_str("MAJISHAMBA_DB_PASSWORD", "majishamba"),
            "HOST": env_str("MAJISHAMBA_DB_HOST", "127.0.0.1"),
            "PORT": env_str("MAJISHAMBA_DB_PORT", "5432"),
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# --- Auth -------------------------------------------------------------------
AUTH_USER_MODEL = "accounts.User"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
     "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# --- I18N -------------------------------------------------------------------
LANGUAGE_CODE = "en"
TIME_ZONE = "Africa/Nairobi"
USE_I18N = True
USE_TZ = True

# --- Static -----------------------------------------------------------------
STATIC_URL = "static/"
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

LOGIN_URL = "/accounts/login/"
LOGIN_REDIRECT_URL = "/dashboard/"
LOGOUT_REDIRECT_URL = "/accounts/login/"

# --- Sessions ---------------------------------------------------------------
SESSION_COOKIE_AGE = 60 * 60 * 4
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_HTTPONLY = False  # templates need to read it for HTMX
CSRF_COOKIE_SAMESITE = "Lax"

# --- Logging (structured, no secrets) ---------------------------------------
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "format": "%(asctime)s %(name)s %(levelname)s %(message)s",
        },
    },
    "handlers": {
        "console": {"class": "logging.StreamHandler", "formatter": "json"},
    },
    "loggers": {
        "majishamba": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django": {"handlers": ["console"], "level": "INFO"},
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
}

# --- Kachieng AI Agent config (settings dict kept as MAJISHAMBA for backwards compat) ---
MAJISHAMBA = {
    # Open-weights model used for at least one full task per challenge requirement.
    "OLLAMA_HOST": env_str("OLLAMA_HOST", "http://127.0.0.1:11434"),
    "OLLAMA_MODEL": env_str("OLLAMA_MODEL", "qwen2.5:7b-instruct"),
    # If the model is unreachable, fall back to deterministic template.
    "FALLBACK_TO_TEMPLATE": env_bool("MAJISHAMBA_FALLBACK_TO_TEMPLATE", True),
    "MODEL_TIMEOUT_SECONDS": 120,
    # Borrowed MCP server config: official filesystem MCP server, restricted to docs/calendars.
    "BORROWED_FILESYSTEM_MCP_ROOT": str(BASE_DIR / "docs" / "calendars"),
    # Audit + approval policy
    "REQUIRE_OFFICER_APPROVAL": True,  # non-negotiable
    # Synthesis freshness thresholds (hours)
    "WEATHER_FRESH_HOURS": 24,
    "PEST_FRESH_HOURS": 7 * 24,
    "MARKET_FRESH_HOURS": 7 * 24,
    "CALENDAR_FRESH_DAYS": 365 * 2,
    # Sub-county/ward/county scope — pinned to the demo office.
    "DEFAULT_OFFICE": {
        "county": "Migori",
        "sub_county": "Nyatike",
        "ward": "Kachieng",
        "office_name": "Nyatike Sub-County Agricultural Office",
    },
    # DEMO MODE: gates the demo-only account selector on the login page.
    # Set DEMO_MODE=1 in dev to show "Choose a demo account" cards.
    # In production, DEMO_MODE=0 (the default) hides the cards and the
    # login page behaves like a normal Django login.
    "DEMO_MODE": env_bool("DEMO_MODE", default=False),
    # Map / basemap config.
    # DEFAULT: Stadia Maps Alidade Smooth (raster) — free for localhost/127.0.0.1
    # development without an API key. See https://docs.stadiamaps.com/free-tier/
    # For production, set KACHIENG_MAP_TILES to your own tile server or get a
    # Stadia Maps API key (https://stadiamaps.com/) and set KACHIENG_MAP_API_KEY.
    # The {api_key} placeholder in the tile URL is replaced at render time.
    "MAP_BASEMAP_TILES": env_str(
        "KACHIENG_MAP_TILES",
        "https://tiles.stadiamaps.com/tiles/alidade_smooth/{z}/{x}/{y}{r}.png",
    ),
    "MAP_BASEMAP_ATTRIBUTION": env_str(
        "KACHIENG_MAP_ATTRIBUTION",
        "© Stadia Maps © OpenMapTiles © OpenStreetMap contributors",
    ),
    "MAP_MAX_ZOOM": 20,
    "MAP_API_KEY": env_str("KACHIENG_MAP_API_KEY", ""),
    # --- LLM provider config ---
    # Default: none (falls back to deterministic template)
    # Set LLM_PROVIDER=openrouter to use OpenRouter (cloud, needs API key)
    # Set LLM_PROVIDER=ollama to use Ollama (local, needs Ollama installed)
    "LLM_PROVIDER": env_str("LLM_PROVIDER", "none"),
    "OPENROUTER_MODEL": env_str("OPENROUTER_MODEL", "google/gemma-4-31b-it:free"),
    "OPENROUTER_TIMEOUT_SECONDS": int(env_str("OPENROUTER_TIMEOUT_SECONDS", "60")),
    "OPENROUTER_MAX_OUTPUT_TOKENS": int(env_str("OPENROUTER_MAX_OUTPUT_TOKENS", "800")),
    # Ollama (optional, for judges/local use)
    "OLLAMA_HOST": env_str("OLLAMA_HOST", "http://127.0.0.1:11434"),
    "OLLAMA_MODEL": env_str("OLLAMA_MODEL", "qwen2.5:7b-instruct"),
    # --- Weather provider config ---
    # Default: Open-Meteo (free, no API key, CC-BY 4.0, 10k calls/day)
    "WEATHER_PROVIDER": env_str("WEATHER_PROVIDER", "open_meteo"),
    "OPEN_METEO_ENDPOINT": env_str("OPEN_METEO_ENDPOINT", "https://api.open-meteo.com/v1/forecast"),
    "WEATHER_REFRESH_HOURS": int(env_str("WEATHER_REFRESH_HOURS", "6")),  # refresh interval
    "WEATHER_REQUEST_TIMEOUT": int(env_str("WEATHER_REQUEST_TIMEOUT", "30")),  # HTTP timeout
    "WEATHER_DAILY_BUDGET": int(env_str("WEATHER_DAILY_BUDGET", "100")),  # max API calls per day
    "OPEN_METEO_ATTRIBUTION": "Forecast from Open-Meteo (CC-BY 4.0)",
}

# --- Caching / queues (demo falls back to local memory) ---------------------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "majishamba-default",
    }
}

RQ = {
    "AUTOCOMMIT": True,
    "DEFAULT_RESULT_TTL": 60 * 60 * 24,
}

# --- Security defaults (overridden by production) --------------------------
SECURE_BROWSER_XSS_FILTER = True
X_FRAME_OPTIONS = "DENY"

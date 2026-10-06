"""Production settings — hardened defaults for real pilots at the Nyatike office."""
from __future__ import annotations

import os

from .base import *  # noqa: F401,F403
from .base import env_bool, env_str

# --- Security (non-negotiable) -----------------------------------------------
DEBUG = env_bool("MAJISHAMBA_DEBUG", False)
SECRET_KEY = env_str("MAJISHAMBA_SECRET_KEY", "")
if not SECRET_KEY:
    raise RuntimeError("MAJISHAMBA_SECRET_KEY must be set in production")

ALLOWED_HOSTS = env_str("MAJISHAMBA_ALLOWED_HOSTS", "").split(",") if env_str("MAJISHAMBA_ALLOWED_HOSTS", "") else ["*"]

SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30  # 30 days
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# --- Demo mode OFF in production --------------------------------------------
MAJISHAMBA["DEMO_MODE"] = False  # Never show demo account cards in production
# DEMO_MODE env var is overridden here regardless of what it's set to.

# --- Static files -----------------------------------------------------------
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# --- Database (PostgreSQL + PostGIS) ---------------------------------------
DATABASES = {
    "default": {
        "ENGINE": env_str("MAJISHAMBA_DB_ENGINE", "django.contrib.gis.db.backends.postgis"
            if env_bool("USE_POSTGIS", False) else "django.db.backends.postgresql"),
        "NAME": env_str("MAJISHAMBA_DB_NAME", "majishamba"),
        "USER": env_str("MAJISHAMBA_DB_USER", "majishamba"),
        "PASSWORD": env_str("MAJISHAMBA_DB_PASSWORD", "majishamba"),
        "HOST": env_str("MAJISHAMBA_DB_HOST", "127.0.0.1"),
        "PORT": env_str("MAJISHAMBA_DB_PORT", "5432"),
        "CONN_MAX_AGE": 60,
    }
}

# --- Cache + queue (Valkey / Redis) -----------------------------------------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": env_str("REDIS_URL", "redis://127.0.0.1:6379/0"),
    }
}

RQ_QUEUES = {
    "default": {
        "HOST": os.environ.get("REDIS_HOST", "127.0.0.1"),
        "PORT": int(os.environ.get("REDIS_PORT", "6379")),
        "DB": 0,
        "ASYNC": True,
    }
}

# --- Logging (structured JSON) ----------------------------------------------
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
        "django": {"handlers": ["console"], "level": "WARNING"},
        "django.request": {"handlers": ["console"], "level": "ERROR", "propagate": False},
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
}

# --- Ollama (production: real model, longer timeout) ------------------------
MAJISHAMBA["OLLAMA_HOST"] = env_str("OLLAMA_HOST", "http://127.0.0.1:11434")
MAJISHAMBA["OLLAMA_MODEL"] = env_str("OLLAMA_MODEL", "qwen2.5:7b-instruct")
MAJISHAMBA["MODEL_TIMEOUT_SECONDS"] = 120

# --- Map (production: API key required) -------------------------------------
# In production, set KACHIENG_MAP_API_KEY to your Stadia Maps key.
# The tile URL includes {api_key} which is substituted server-side.
MAJISHAMBA["MAP_BASEMAP_TILES"] = env_str(
    "KACHIENG_MAP_TILES",
    "https://tiles.stadiamaps.com/tiles/alidade_smooth/{z}/{x}/{y}{r}.png",
)
MAJISHAMBA["MAP_API_KEY"] = env_str("KACHIENG_MAP_API_KEY", "")
MAJISHAMBA["MAP_MAX_ZOOM"] = 20

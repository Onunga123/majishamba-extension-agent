
"""Production settings for the MajiShamba Extension Agent demo."""
from __future__ import annotations

from .base import *  # noqa: F401,F403
from .base import env_bool, env_str

# --- Security ---------------------------------------------------------------
DEBUG = env_bool("MAJISHAMBA_DEBUG", False)

SECRET_KEY = env_str("MAJISHAMBA_SECRET_KEY", "")
if not SECRET_KEY:
    raise RuntimeError("MAJISHAMBA_SECRET_KEY must be set in production")

ALLOWED_HOSTS = (
    [host.strip() for host in env_str("MAJISHAMBA_ALLOWED_HOSTS", "").split(",")
     if host.strip()]
    or ["*"]
)

SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CONTENT_TYPE_NOSNIFF = True
X_FRAME_OPTIONS = "DENY"

# --- Demo mode --------------------------------------------------------------
# Keep the demo account selector disabled by default.
MAJISHAMBA["DEMO_MODE"] = False

# --- Static files -----------------------------------------------------------
STATICFILES_STORAGE = (
    "whitenoise.storage.CompressedManifestStaticFilesStorage"
)

# --- Database: SQLite by default, PostgreSQL optional -----------------------
# SQLite avoids requiring a separately hosted database for the demo.
# Render's local filesystem is ephemeral; SQLite data is not durable there.
if env_bool("USE_POSTGRES", False):
    DATABASES = {
        "default": {
            "ENGINE": env_str(
                "MAJISHAMBA_DB_ENGINE",
                "django.contrib.gis.db.backends.postgis"
                if env_bool("USE_POSTGIS", False)
                else "django.db.backends.postgresql",
            ),
            "NAME": env_str("MAJISHAMBA_DB_NAME", "majishamba"),
            "USER": env_str("MAJISHAMBA_DB_USER", "majishamba"),
            "PASSWORD": env_str("MAJISHAMBA_DB_PASSWORD", ""),
            "HOST": env_str("MAJISHAMBA_DB_HOST", "127.0.0.1"),
            "PORT": env_str("MAJISHAMBA_DB_PORT", "5432"),
            "CONN_MAX_AGE": 60,
        }
    }
else:
    DATABASES = {
        "default": {
            "ENGINE": "django.db.backends.sqlite3",
            "NAME": BASE_DIR / "db.sqlite3",
        }
    }

# --- Cache: in-memory, no external Redis/Valkey service ---------------------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "majishamba-production-demo",
    }
}

# --- Background jobs: execute inline for the demo ---------------------------
# No Redis queue or separate worker is required by this configuration.
RQ_QUEUES = {
    "default": {
        "HOST": "127.0.0.1",
        "PORT": 6379,
        "DB": 0,
        "ASYNC": False,
    }
}

RQ = {
    "AUTOCOMMIT": True,
    "DEFAULT_RESULT_TTL": 60 * 60 * 24,
}

# --- Logging ----------------------------------------------------------------
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
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
        },
    },
    "loggers": {
        "majishamba": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
        "django": {
            "handlers": ["console"],
            "level": "WARNING",
        },
        "django.request": {
            "handlers": ["console"],
            "level": "ERROR",
            "propagate": False,
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
}

# --- Ollama / LLM -----------------------------------------------------------
MAJISHAMBA["OLLAMA_HOST"] = env_str(
    "OLLAMA_HOST", "http://127.0.0.1:11434"
)
MAJISHAMBA["OLLAMA_MODEL"] = env_str(
    "OLLAMA_MODEL", "qwen2.5:7b-instruct"
)
MAJISHAMBA["MODEL_TIMEOUT_SECONDS"] = 120

# --- Map / basemap ----------------------------------------------------------
MAJISHAMBA["MAP_BASEMAP_TILES"] = env_str(
    "KACHIENG_MAP_TILES",
    "https://basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}.png",
)
MAJISHAMBA["MAP_API_KEY"] = env_str(
    "CARTO_BASEMAP_API_KEY",
    env_str("KACHIENG_MAP_API_KEY", ""),
)
MAJISHAMBA["MAP_BASEMAP_ATTRIBUTION"] = env_str(
    "KACHIENG_MAP_ATTRIBUTION",
    "© OpenStreetMap contributors © CARTO",
)
MAJISHAMBA["MAP_MAX_ZOOM"] = 20

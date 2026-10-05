"""Production settings — hardened defaults for real pilots at the Nyatike office."""
from __future__ import annotations

import os

from .base import *  # noqa: F401,F403
from .base import env_bool, env_str

DEBUG = env_bool("MAJISHAMBA_DEBUG", False)
SECRET_KEY = env_str("MAJISHAMBA_SECRET_KEY", "")
if not SECRET_KEY:
    raise RuntimeError("MAJISHAMBA_SECRET_KEY must be set in production")

SECURE_SSL_REDIRECT = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 60 * 60 * 24 * 30
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CONTENT_TYPE_NOSNIFF = True

# Manifest storage for production
STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Production expects PostgreSQL + Valkey/Redis + real Ollama host
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

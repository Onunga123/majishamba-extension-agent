"""Development settings — used by `make demo` and `pytest`."""
from __future__ import annotations

from .base import *  # noqa: F401,F403
from .base import BASE_DIR, env_bool

DEBUG = env_bool("MAJISHAMBA_DEBUG", True)

# Permissive for local dev
ALLOWED_HOSTS = ["*"]

# Django-RQ uses local-memory queue in dev (no Valkey/Redis requirement)
RQ_QUEUES = {
    "default": {
        "HOST": "127.0.0.1",
        "PORT": 6379,
        "DB": 0,
        "ASYNC": False,  # run inline for the demo
    }
}

# Tailwind / static — relax for dev
STATICFILES_STORAGE = "django.contrib.staticfiles.storage.StaticFilesStorage"

# DEMO_MODE: enables the demo-only account selector on the login page.
# Default ON in development so `make demo` shows the picker.
# Override with env var DEMO_MODE=0 to hide it (e.g. when running pytest
# against a non-demo deployment).
MAJISHAMBA["DEMO_MODE"] = env_bool("DEMO_MODE", default=True)

# Use a simpler logger formatter for tests so output is readable.
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {
        "console": {"class": "logging.StreamHandler"},
    },
    "loggers": {
        "majishamba": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "django": {"handlers": ["console"], "level": "WARNING"},
    },
    "root": {"handlers": ["console"], "level": "WARNING"},
}

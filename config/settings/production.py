```python
# --- Database (SQLite for demo; PostgreSQL optional) -------------------------
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
            "PASSWORD": env_str("MAJISHAMBA_DB_PASSWORD", "majishamba"),
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
```


FROM python:3.12-slim

# System dependencies for PostgreSQL support
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy project files before installing the package
COPY . .

# Install the project and its PostgreSQL driver
RUN pip install --no-cache-dir -e ".[postgres]" \
    && pip install --no-cache-dir gunicorn

# Collect static files while building the image.
# This temporary key is not used as the runtime secret.
RUN MAJISHAMBA_SECRET_KEY="build-only-not-for-runtime" \
    DJANGO_SETTINGS_MODULE=config.settings.production \
    python manage.py collectstatic --noinput

EXPOSE 8000

# Apply migrations before starting the web server
CMD ["sh", "-c", "DJANGO_SETTINGS_MODULE=config.settings.production python manage.py migrate --noinput && exec gunicorn config.wsgi:application --bind 0.0.0.0:8000 --workers 1 --timeout 120"]

FROM python:3.12-slim

# System dependencies for PostGIS + GDAL
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc gdal-bin libgdal-dev python3-gdal \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies
COPY pyproject.toml ./
RUN pip install --no-cache-dir -e ".[postgres]"

# Copy project
COPY . .

# Install gunicorn for production
RUN pip install --no-cache-dir gunicorn

EXPOSE 8000

CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "3", "--timeout", "120"]

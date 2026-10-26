```dockerfile
FROM python:3.12-slim

# System dependencies for PostgreSQL
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq-dev gcc \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy the project files before installing the package
COPY . .

# Install application dependencies and Gunicorn
RUN pip install --no-cache-dir -e ".[postgres]" \
    && pip install --no-cache-dir gunicorn

# Render provides the public HTTP port
EXPOSE 8000

# Start Django with Gunicorn
CMD ["gunicorn", "config.wsgi:application", "--bind", "0.0.0.0:8000", "--workers", "1", "--timeout", "120"]
```

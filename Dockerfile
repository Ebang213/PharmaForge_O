# ===========================================
# Stage 1: Build dependencies
# ===========================================
FROM python:3.11.9-slim-bookworm AS builder

WORKDIR /build

# Install build-time system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip && \
    pip install --no-cache-dir --prefix=/install -r requirements.txt

# ===========================================
# Stage 2: Production runtime
# ===========================================
FROM python:3.11.9-slim-bookworm

# Install only runtime dependencies (libpq for psycopg2, curl for healthcheck)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd --gid 1000 appuser && \
    useradd --uid 1000 --gid appuser --shell /bin/bash --create-home appuser

WORKDIR /code

# Copy installed Python packages from builder
COPY --from=builder /install /usr/local

# Copy application code (no .env, no secrets)
COPY ./app /code/app
COPY ./samples /code/samples
COPY ./alembic.ini /code/alembic.ini

# Create upload directory and set ownership
RUN mkdir -p /code/uploads && chown -R appuser:appuser /code

# Switch to non-root user
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --start-period=30s --retries=3 \
    CMD curl -f http://localhost:8000/api/health || exit 1

CMD ["gunicorn", "app.main:app", \
    "--workers", "4", \
    "--worker-class", "uvicorn.workers.UvicornWorker", \
    "--bind", "0.0.0.0:8000", \
    "--timeout", "120", \
    "--keep-alive", "5", \
    "--access-logfile", "-", \
    "--error-logfile", "-", \
    "--log-level", "info"]

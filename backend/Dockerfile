# TabSage backend — production image (Phase 9).
#
# Stateless about secrets: no provider key is ever baked in or set here. The
# user's key arrives per request in the X-Provider-Key header. Operators set
# only NON-SECRET env at deploy time (ENV, ALLOWED_ORIGINS, …).
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install dependencies first so this layer caches across code changes.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Application code (tests/scripts/.env excluded via .dockerignore).
COPY . .

# Run as a non-root user.
RUN useradd --create-home --uid 10001 appuser && chown -R appuser:appuser /app
USER appuser

# Production defaults (override at deploy time).
#   ENV=prod            → config.is_dev is False (no autoreload)
#   ALLOWED_ORIGINS     → MUST be set to the extension origin + any web origins
ENV ENV=prod \
    PORT=8000 \
    WEB_CONCURRENCY=1

EXPOSE 8000

# ⚠️ The default vector store AND the rate limiter are IN-MEMORY and
# PER-PROCESS. Run a SINGLE worker so sessions and rate limits stay coherent;
# concurrency still comes from the async worker's threadpool (the endpoints are
# sync `def`). To scale horizontally, move to a shared vector store
# (Postgres + pgvector) and a shared rate-limit store (Redis), then raise
# WEB_CONCURRENCY.
#
# gunicorn's access log records the request line + status only (no headers or
# bodies), so the provider key and page text are never logged.
CMD ["sh", "-c", "exec gunicorn main:app -k uvicorn.workers.UvicornWorker -w ${WEB_CONCURRENCY} -b 0.0.0.0:${PORT} --timeout 120 --access-logfile - --error-logfile -"]

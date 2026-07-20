##############################################################################
# Stage 1 — install dependencies only (cached layer)
##############################################################################
FROM python:3.12-slim AS deps

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Install system deps needed at runtime
# ca-certificates: required for DhanHQ WebSocket SSL verification
# curl: healthcheck
# libpq5: psycopg2 runtime
RUN apt-get update && apt-get install -y --no-install-recommends \
    ca-certificates \
    curl \
    libpq5 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

##############################################################################
# Stage 2 — final image (non-root, minimal)
##############################################################################
FROM deps AS final

# Create non-root user
RUN groupadd --gid 1001 appgroup && \
    useradd --uid 1001 --gid appgroup --no-create-home appuser

WORKDIR /app

# Copy application code
COPY --chown=appuser:appgroup . .

USER appuser

EXPOSE 8000

# Healthcheck built into image (also used by docker-compose)
HEALTHCHECK --interval=10s --timeout=5s --start-period=20s --retries=5 \
    CMD curl -sf http://localhost:8000/health || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1", "--log-level", "info"]

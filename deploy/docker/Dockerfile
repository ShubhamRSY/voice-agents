# ==============================================================
# Stage 1 — build environment
# ==============================================================
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

# Minimal build deps (avoid pulling in entire build-essential)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Install runtime deps first (layer caching)
COPY pyproject.toml README.md ./
COPY config/deps/requirements.txt config/deps/
RUN pip install --upgrade pip setuptools wheel && \
    pip install -r config/deps/requirements.txt && \
    pip install -e .

# ==============================================================
# Stage 2 — runtime image (minimal)
# ==============================================================
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    APP_HOST=0.0.0.0 \
    APP_PORT=8000 \
    PYTHONPATH=/app

WORKDIR /app

# Install only wget for healthcheck; ca-certificates already present
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder (match Python 3.12 path)
COPY --from=builder /usr/local/lib/python3.12/site-packages /usr/local/lib/python3.12/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin
COPY --from=builder /build/src /app/src
COPY --from=builder /build/config /app/config
COPY --from=builder /build/pyproject.toml /app/

# Application code only (no tests, docs, scripts)
COPY static ./static
COPY data ./data

RUN groupadd -r appgroup && \
    useradd -r -g appgroup -u 1000 appuser && \
    chown -R appuser:appgroup /app
USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD wget --no-verbose --tries=1 --spider http://127.0.0.1:8000/api/v1/health || exit 1

CMD ["gunicorn", \
     "-w", "4", \
     "-k", "uvicorn.workers.UvicornWorker", \
     "src.main:app", \
     "--bind", "0.0.0.0:8000", \
     "--max-requests", "10000", \
     "--max-requests-jitter", "1000", \
     "--timeout", "120", \
     "--graceful-timeout", "30"]

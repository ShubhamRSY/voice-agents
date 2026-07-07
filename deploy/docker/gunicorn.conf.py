"""
Gunicorn configuration for zero-downtime production deployment.

Features:
- Preload app for faster worker spawn
- Graceful worker reload with SIGHUP
- Max requests to prevent memory leaks
- Staggered worker restarts
"""

import multiprocessing
import os

# Socket binding
bind = f"0.0.0.0:{os.getenv('APP_PORT', '8000')}"

# Workers — 2-4x CPU cores for I/O-bound (uvicorn async workers)
workers = int(os.getenv("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2))
worker_class = "uvicorn.workers.UvicornWorker"
worker_connections = 1000

# Timeouts
timeout = int(os.getenv("GUNICORN_TIMEOUT", "120"))
graceful_timeout = int(os.getenv("GUNICORN_GRACEFUL_TIMEOUT", "30"))
keepalive = 5

# Max requests per worker — prevents memory bloat
max_requests = int(os.getenv("GUNICORN_MAX_REQUESTS", "10000"))
max_requests_jitter = int(os.getenv("GUNICORN_MAX_REQUESTS_JITTER", "1000"))

# Preload app for faster worker spawn
preload_app = True

# Logging
loglevel = os.getenv("LOG_LEVEL", "info").lower()
accesslog = "-"
errorlog = "-"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Zero-downtime reload support
# Send SIGHUP to gracefully reload workers without dropping connections
reload = False  # Use --reload flag for dev only


def when_ready(server):
    """Log startup info."""
    server.log.info("Gunicorn ready: workers=%d  worker_class=%s  timeout=%d",
                    workers, worker_class, timeout)


def on_exit(server):
    """Cleanup on shutdown."""
    server.log.info("Gunicorn shutting down")

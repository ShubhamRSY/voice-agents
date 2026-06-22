"""Middleware for rate limiting, tenant resolution, and request logging."""

import time
from collections import defaultdict

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from src.auth import decode_jwt

logger = structlog.get_logger()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Simple in-memory rate limiter (per-IP, per-tenant, per-endpoint)."""

    def __init__(self, app: ASGIApp, rpm: int = 60):
        super().__init__(app)
        self.rpm = rpm
        self._windows: dict[str, list[float]] = defaultdict(list)

    async def dispatch(self, request: Request, call_next) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        tenant_id = "public"
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            payload = decode_jwt(auth_header[7:])
            if payload:
                tenant_id = payload.get("tenant_id", "public")

        key = f"{tenant_id}:{client_ip}:{request.url.path}"

        now = time.time()
        window = self._windows[key]
        cutoff = now - 60
        while window and window[0] < cutoff:
            window.pop(0)

        if len(window) >= self.rpm:
            logger.warning("rate_limit_exceeded", key=key, count=len(window))
            return Response(status_code=429, content="Rate limit exceeded. Try again soon.")

        window.append(now)
        return await call_next(request)


class TenantMiddleware(BaseHTTPMiddleware):
    """Resolve tenant from JWT or subdomain and attach to request state."""

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next) -> Response:
        tenant_id = "default"
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            payload = decode_jwt(auth_header[7:])
            if payload:
                tenant_id = payload.get("tenant_id", "default")

        request.state.tenant_id = tenant_id
        return await call_next(request)

"""Middleware for rate limiting, tenant resolution, and request logging."""

import time
from collections import defaultdict
from collections.abc import Awaitable, Callable

import structlog
from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.types import ASGIApp

from src.cache import get_cache
from src.auth import decode_jwt

logger = structlog.get_logger()


class _SlidingWindowCounter:
    """In-memory sliding window rate counter with automatic cleanup."""

    def __init__(self):
        self._windows: dict[str, list[float]] = defaultdict(list)

    def allow(self, key: str, limit: int, window_sec: int = 60) -> bool:
        now = time.time()
        window = self._windows[key]
        cutoff = now - window_sec
        while window and window[0] < cutoff:
            window.pop(0)
        if len(window) >= limit:
            return False
        window.append(now)
        return True

    def cleanup(self, max_age: int = 120) -> int:
        now = time.time()
        cutoff = now - max_age
        count = 0
        for key in list(self._windows.keys()):
            self._windows[key] = [t for t in self._windows[key] if t >= cutoff]
            if not self._windows[key]:
                del self._windows[key]
                count += 1
        return count


_in_memory_limiter = _SlidingWindowCounter()


class RateLimitMiddleware(BaseHTTPMiddleware):
    """Rate limiter with Redis-backed sliding window, falling back to in-memory.

    Per-endpoint-group limits per IP and per tenant.
    """

    _ENDPOINT_LIMITS: dict[str, int] = {
        "/api/v1/chat": 30,
        "/api/v1/copilot": 20,
        "/api/v1/telephony": 15,
        "/api/v1/evaluation": 10,
        "/api/v1/rag": 30,
        "/api/v1/messaging": 20,
    }
    _DEFAULT_LIMIT = 60

    def __init__(self, app: ASGIApp, rpm: int = 60):
        super().__init__(app)
        self.cache = get_cache()
        self.rpm = rpm

    def _get_limit(self, path: str) -> int:
        for prefix, limit in self._ENDPOINT_LIMITS.items():
            if path.startswith(prefix):
                return limit
        return self._DEFAULT_LIMIT

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        client_ip = request.client.host if request.client else "unknown"
        tenant_id = "public"
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            payload = decode_jwt(auth_header[7:])
            if payload:
                tenant_id = payload.get("tenant_id", "public")

        endpoint_group = next((p for p in self._ENDPOINT_LIMITS if request.url.path.startswith(p)), "default")
        limit = self._get_limit(request.url.path)

        # Try Redis-backed sliding window
        client = getattr(self.cache, "_get_client", lambda: None)()
        if client:
            key = f"rate_limit:{tenant_id}:{client_ip}:{endpoint_group}"
            try:
                await client.zremrangebyscore(key, 0, time.time() - 60)
                request_count = await client.zcard(key)
                if request_count >= limit:
                    logger.warning("rate_limit_exceeded", key=key, limit=limit, count=request_count)
                    return Response(status_code=429, content="Rate limit exceeded. Try again soon.")
                await client.zadd(key, {str(time.time()): time.time()})
                await client.expire(key, 60)
            except Exception as exc:
                logger.warning("rate_limiter_redis_error", error=str(exc))
                # Fall through to in-memory
            else:
                return await call_next(request)

        # Fallback: in-memory sliding window
        key = f"{tenant_id}:{client_ip}:{endpoint_group}"
        if not _in_memory_limiter.allow(key, limit):
            logger.warning("rate_limit_exceeded_memory", key=key, limit=limit)
            return Response(status_code=429, content="Rate limit exceeded. Try again soon.")

        return await call_next(request)


class TenantMiddleware(BaseHTTPMiddleware):
    """Resolve tenant from JWT or subdomain and attach to request state."""

    def __init__(self, app: ASGIApp):
        super().__init__(app)

    async def dispatch(self, request: Request, call_next: Callable[[Request], Awaitable[Response]]) -> Response:
        tenant_id = "default"
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            payload = decode_jwt(auth_header[7:])
            if payload:
                tenant_id = payload.get("tenant_id", "default")

        request.state.tenant_id = tenant_id
        return await call_next(request)

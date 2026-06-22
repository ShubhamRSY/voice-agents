"""Redis caching layer for embeddings, LLM responses, and sessions."""

import hashlib
import json
import time
from typing import Any

import structlog

from src.config import get_settings

logger = structlog.get_logger()


class CacheBackend:
    def get(self, key: str) -> Any | None:
        return None

    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        pass

    def delete(self, key: str) -> None:
        pass

    def clear(self) -> None:
        pass


class MemoryCache(CacheBackend):
    def __init__(self):
        self._store: dict[str, tuple[Any, float]] = {}

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        value, expiry = entry
        if time.time() > expiry:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: Any, ttl: int = 300) -> None:
        self._store[key] = (value, time.time() + ttl)

    def delete(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()


class RedisCache(CacheBackend):
    def __init__(self, redis_url: str):
        self._redis_url = redis_url
        self._client = None

    def _get_client(self):
        if self._client is None:
            try:
                import redis.asyncio as aioredis
                self._client = aioredis.from_url(self._redis_url, decode_responses=True)
            except Exception as e:
                logger.warning("redis_unavailable_falling_back", error=str(e))
                return None
        return self._client

    async def get(self, key: str) -> Any | None:
        client = self._get_client()
        if not client:
            return None
        try:
            val = await client.get(key)
            return json.loads(val) if val else None
        except Exception:
            return None

    async def set(self, key: str, value: Any, ttl: int = 300) -> None:
        client = self._get_client()
        if not client:
            return
        try:
            await client.setex(key, ttl, json.dumps(value))
        except Exception:
            pass

    async def delete(self, key: str) -> None:
        client = self._get_client()
        if not client:
            return
        try:
            await client.delete(key)
        except Exception:
            pass

    async def clear(self) -> None:
        client = self._get_client()
        if not client:
            return
        try:
            await client.flushdb()
        except Exception:
            pass


def _cache_key(prefix: str, *parts: str) -> str:
    raw = ":".join(parts)
    return f"nexus:{prefix}:{hashlib.sha256(raw.encode()).hexdigest()[:16]}"


_cache: CacheBackend | None = None


def get_cache() -> CacheBackend:
    global _cache
    if _cache is not None:
        return _cache

    settings = get_settings()
    if settings.redis_url:
        try:
            _cache = RedisCache(settings.redis_url)
            logger.info("redis_cache_enabled", url=settings.redis_url)
        except Exception:
            _cache = MemoryCache()
            logger.info("memory_cache_fallback")
    else:
        _cache = MemoryCache()
        logger.info("memory_cache_enabled")
    return _cache


def cached(ttl: int = 300):
    """Decorator: cache async function results by args."""
    def decorator(func):
        async def wrapper(*args, **kwargs):
            cache = get_cache()
            key = _cache_key(func.__name__, *(str(a) for a in args), *(f"{k}={v}" for k, v in kwargs.items()))
            result = cache.get(key)
            if result is not None:
                return result
            result = await func(*args, **kwargs)
            cache.set(key, result, ttl)
            return result
        return wrapper
    return decorator


def invalidate_cache(prefix: str, *parts: str) -> None:
    """Remove a specific cache entry by prefix and parts."""
    key = _cache_key(prefix, *parts)
    get_cache().delete(key)


def clear_all_caches() -> None:
    get_cache().clear()
    logger.info("all_caches_cleared")

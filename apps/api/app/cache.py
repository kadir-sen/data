"""Redis caching layer for expensive metric queries."""

from __future__ import annotations

import hashlib
import json
import logging
from collections.abc import Callable
from functools import wraps
from typing import Any

import redis.asyncio as redis

from app.config import settings

logger = logging.getLogger(__name__)

_pool: redis.Redis | None = None


async def get_redis() -> redis.Redis:
    """Return a shared async Redis connection (lazy-init)."""
    global _pool  # noqa: PLW0603
    if _pool is None:
        _pool = redis.from_url(
            settings.redis_url,
            decode_responses=True,
            socket_connect_timeout=2,
        )
    return _pool


async def close_redis() -> None:
    global _pool  # noqa: PLW0603
    if _pool is not None:
        await _pool.aclose()
        _pool = None


def _make_key(prefix: str, args: tuple, kwargs: dict) -> str:
    """Deterministic cache key from function arguments."""
    raw = json.dumps({"a": [str(a) for a in args], "k": {k: str(v) for k, v in sorted(kwargs.items())}}, sort_keys=True)
    digest = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return f"case:{prefix}:{digest}"


def cached(prefix: str, ttl_seconds: int = 300) -> Callable:
    """Decorator that caches the JSON-serialisable return value in Redis.

    Falls back to direct execution when Redis is unavailable.
    """

    def decorator(fn: Callable) -> Callable:
        @wraps(fn)
        async def wrapper(*args: Any, **kwargs: Any) -> Any:
            key = _make_key(prefix, args, kwargs)
            try:
                r = await get_redis()
                hit = await r.get(key)
                if hit is not None:
                    return json.loads(hit)
            except Exception:
                logger.warning("Redis read failed for %s – computing fresh", key)

            result = await fn(*args, **kwargs)

            try:
                r = await get_redis()
                await r.set(key, json.dumps(result, default=str), ex=ttl_seconds)
            except Exception:
                logger.warning("Redis write failed for %s", key)

            return result

        return wrapper

    return decorator


async def invalidate_prefix(prefix: str) -> int:
    """Delete all keys matching `case:{prefix}:*`. Returns count deleted."""
    try:
        r = await get_redis()
        keys = []
        async for key in r.scan_iter(f"case:{prefix}:*", count=200):
            keys.append(key)
        if keys:
            return await r.delete(*keys)  # type: ignore[return-value]
    except Exception:
        logger.warning("Redis invalidation failed for prefix %s", prefix)
    return 0

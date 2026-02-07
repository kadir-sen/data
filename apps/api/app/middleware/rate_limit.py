"""Sliding-window rate limiter backed by Redis.

Falls back to an in-memory dict when Redis is unavailable so
the API stays functional in dev/test without a Redis process.
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint
from starlette.responses import JSONResponse

from app.cache import get_redis

logger = logging.getLogger(__name__)

# Defaults: 60 requests per 60-second window
DEFAULT_LIMIT = 60
DEFAULT_WINDOW = 60

# In-memory fallback (not shared across workers, but fine for dev)
_mem_store: dict[str, list[float]] = defaultdict(list)


def _client_key(request: Request) -> str:
    """Extract a rate-limit key from the request (IP-based)."""
    forwarded = request.headers.get("x-forwarded-for")
    ip = forwarded.split(",")[0].strip() if forwarded else (request.client.host if request.client else "unknown")
    return f"rl:{ip}"


class RateLimitMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, limit: int = DEFAULT_LIMIT, window: int = DEFAULT_WINDOW):
        super().__init__(app)
        self.limit = limit
        self.window = window

    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        # Skip rate limiting for docs and health endpoints
        if request.url.path in ("/docs", "/openapi.json", "/healthz", "/redoc", "/", "/obs/metrics"):
            return await call_next(request)

        key = _client_key(request)
        allowed, remaining, reset = await self._check(key)

        if not allowed:
            return JSONResponse(
                status_code=429,
                content={"detail": "Rate limit exceeded. Try again later."},
                headers={
                    "Retry-After": str(reset),
                    "X-RateLimit-Limit": str(self.limit),
                    "X-RateLimit-Remaining": "0",
                    "X-RateLimit-Reset": str(reset),
                },
            )

        response = await call_next(request)
        response.headers["X-RateLimit-Limit"] = str(self.limit)
        response.headers["X-RateLimit-Remaining"] = str(remaining)
        response.headers["X-RateLimit-Reset"] = str(reset)
        return response

    async def _check(self, key: str) -> tuple[bool, int, int]:
        """Returns (allowed, remaining, reset_seconds)."""
        try:
            return await self._check_redis(key)
        except Exception:
            return self._check_memory(key)

    async def _check_redis(self, key: str) -> tuple[bool, int, int]:
        r = await get_redis()
        now = time.time()
        window_start = now - self.window

        pipe = r.pipeline()
        pipe.zremrangebyscore(key, 0, window_start)
        pipe.zadd(key, {str(now): now})
        pipe.zcard(key)
        pipe.expire(key, self.window)
        results = await pipe.execute()

        count = results[2]
        remaining = max(0, self.limit - count)
        reset = self.window

        return count <= self.limit, remaining, reset

    def _check_memory(self, key: str) -> tuple[bool, int, int]:
        now = time.time()
        window_start = now - self.window

        # Prune old entries
        _mem_store[key] = [t for t in _mem_store[key] if t > window_start]
        _mem_store[key].append(now)

        count = len(_mem_store[key])
        remaining = max(0, self.limit - count)

        return count <= self.limit, remaining, self.window

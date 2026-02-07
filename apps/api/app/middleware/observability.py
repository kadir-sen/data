"""Middleware that records per-request observability metrics.

Counters:
  http_requests_total{method, path, status}   – request count
  http_errors_total{method, path, status}      – 4xx/5xx count

Histograms:
  http_request_duration_ms{method, path}       – latency distribution
"""

from __future__ import annotations

import time

from fastapi import Request, Response
from starlette.middleware.base import BaseHTTPMiddleware, RequestResponseEndpoint

from app.logging_config import get_logger
from app.observability import counter_inc, histogram_observe

logger = get_logger("app.middleware.observability")


def _normalise_path(path: str) -> str:
    """Collapse UUID / numeric segments to placeholders to avoid cardinality explosion."""
    import re
    path = re.sub(
        r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}",
        "{id}",
        path,
    )
    path = re.sub(r"/\d+", "/{id}", path)
    return path


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next: RequestResponseEndpoint) -> Response:
        start = time.perf_counter()
        method = request.method
        path = _normalise_path(request.url.path)

        try:
            response = await call_next(request)
        except Exception:
            counter_inc("http_requests_total", method=method, path=path, status="500")
            counter_inc("http_errors_total", method=method, path=path, status="500")
            raise

        duration_ms = (time.perf_counter() - start) * 1000
        status = str(response.status_code)

        counter_inc("http_requests_total", method=method, path=path, status=status)
        histogram_observe("http_request_duration_ms", duration_ms, method=method, path=path)

        if response.status_code >= 400:
            counter_inc("http_errors_total", method=method, path=path, status=status)

        # Structured log for slow requests (> 1s)
        if duration_ms > 1000:
            logger.warning(
                "slow_request",
                method=method,
                path=path,
                status_code=response.status_code,
                duration_ms=round(duration_ms, 1),
            )

        return response

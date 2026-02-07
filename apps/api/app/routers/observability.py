"""Observability endpoints — system metrics for monitoring & alerting.

GET /obs/metrics   → JSON snapshot of all counters, histograms, gauges
GET /obs/health    → deep health check (DB + Redis connectivity)
"""

from __future__ import annotations

from fastapi import APIRouter

from app.observability import snapshot

router = APIRouter(prefix="/obs", tags=["observability"])


@router.get(
    "/metrics",
    summary="Application metrics",
    description=(
        "Returns all in-process metrics: request counters, latency histograms, "
        "ingestion job durations, and failure counts. "
        "Suitable for scraping by Prometheus (via json_exporter) or direct consumption."
    ),
)
async def get_obs_metrics() -> dict:
    return snapshot()

"""Tests for the observability metrics system.

Verifies:
  1. Counter increment / get correctness.
  2. Histogram percentile calculations.
  3. Gauge set/inc operations.
  4. /obs/metrics endpoint returns expected structure.
  5. Metrics for a fixed dataset are deterministic.
"""

from __future__ import annotations

import pytest
from httpx import AsyncClient

from app.observability import (
    counter_get,
    counter_inc,
    gauge_get,
    gauge_inc,
    gauge_set,
    histogram_observe,
    histogram_summary,
    reset,
    snapshot,
)


@pytest.fixture(autouse=True)
def _reset():
    reset()
    yield
    reset()


# ── Counter tests ──────────────────────────────────────────────────

def test_counter_default_zero() -> None:
    assert counter_get("nonexistent") == 0


def test_counter_inc() -> None:
    counter_inc("req", method="GET", path="/health")
    counter_inc("req", method="GET", path="/health")
    counter_inc("req", method="POST", path="/items")

    assert counter_get("req", method="GET", path="/health") == 2
    assert counter_get("req", method="POST", path="/items") == 1


def test_counter_inc_by_value() -> None:
    counter_inc("bytes", value=100)
    counter_inc("bytes", value=50)
    assert counter_get("bytes") == 150


# ── Histogram tests ────────────────────────────────────────────────

def test_histogram_empty() -> None:
    summary = histogram_summary("latency")
    assert summary["count"] == 0
    assert summary["sum"] == 0


def test_histogram_fixed_dataset() -> None:
    """Known dataset produces deterministic percentiles."""
    # 100 values: 1, 2, 3, ..., 100
    for i in range(1, 101):
        histogram_observe("latency", float(i))

    s = histogram_summary("latency")
    assert s["count"] == 100
    assert s["sum"] == 5050.0
    assert s["avg"] == 50.5
    # p50 of 1..100 should be ~50.5
    assert 49.0 <= s["p50"] <= 51.0
    # p95 should be ~95.05
    assert 94.0 <= s["p95"] <= 96.0
    # p99 should be ~99.01
    assert 98.0 <= s["p99"] <= 100.0


def test_histogram_with_labels() -> None:
    histogram_observe("dur", 10.0, source="jira")
    histogram_observe("dur", 20.0, source="gitlab")
    histogram_observe("dur", 30.0, source="jira")

    jira = histogram_summary("dur", source="jira")
    assert jira["count"] == 2
    assert jira["sum"] == 40.0

    gitlab = histogram_summary("dur", source="gitlab")
    assert gitlab["count"] == 1
    assert gitlab["sum"] == 20.0


# ── Gauge tests ────────────────────────────────────────────────────

def test_gauge_set_and_get() -> None:
    gauge_set("active_conns", 5.0)
    assert gauge_get("active_conns") == 5.0
    gauge_set("active_conns", 3.0)
    assert gauge_get("active_conns") == 3.0


def test_gauge_inc() -> None:
    gauge_inc("queue_depth", 1.0)
    gauge_inc("queue_depth", 1.0)
    gauge_inc("queue_depth", -1.0)
    assert gauge_get("queue_depth") == 1.0


# ── Snapshot tests ─────────────────────────────────────────────────

def test_snapshot_structure() -> None:
    counter_inc("a")
    histogram_observe("b", 1.0)
    gauge_set("c", 42.0)

    s = snapshot()
    assert "_ts" in s
    assert "counters" in s
    assert "histograms" in s
    assert "gauges" in s
    assert "a" in s["counters"]
    assert "b" in s["histograms"]
    assert "c" in s["gauges"]


# ── Endpoint tests ─────────────────────────────────────────────────

async def test_obs_metrics_endpoint(client: AsyncClient) -> None:
    """GET /obs/metrics returns JSON with expected keys."""
    # Generate some metrics
    counter_inc("http_requests_total", method="GET", path="/healthz", status="200")
    histogram_observe("http_request_duration_ms", 5.0, method="GET", path="/healthz")

    resp = await client.get("/obs/metrics")
    assert resp.status_code == 200
    body = resp.json()
    assert "counters" in body
    assert "histograms" in body
    assert "gauges" in body
    assert "http_requests_total" in body["counters"]


async def test_obs_metrics_not_rate_limited(client: AsyncClient) -> None:
    """/obs/metrics should bypass rate limiting."""
    for _ in range(5):
        resp = await client.get("/obs/metrics")
        assert resp.status_code == 200


# ── Metric correctness for fixed dataset ───────────────────────────

def test_ingestion_metrics_for_fixed_dataset() -> None:
    """Simulate a fixed ingestion workload and verify all metric values."""
    # Simulate 10 jira events, 5 gitlab events, 2 jira duplicates
    for _ in range(10):
        counter_inc("ingestion_events_total", source="jira")
    for _ in range(5):
        counter_inc("ingestion_events_total", source="gitlab")
    for _ in range(2):
        counter_inc("ingestion_duplicates_total", source="jira")

    # Record ingestion durations
    jira_durations = [10.0, 15.0, 20.0, 12.0, 8.0]
    for d in jira_durations:
        histogram_observe("ingestion_duration_ms", d, source="jira")

    assert counter_get("ingestion_events_total", source="jira") == 10
    assert counter_get("ingestion_events_total", source="gitlab") == 5
    assert counter_get("ingestion_duplicates_total", source="jira") == 2

    jira_hist = histogram_summary("ingestion_duration_ms", source="jira")
    assert jira_hist["count"] == 5
    assert jira_hist["sum"] == 65.0
    assert jira_hist["avg"] == 13.0

    s = snapshot()
    assert s["counters"]["ingestion_events_total"]["source=jira"] == 10
    assert s["counters"]["ingestion_events_total"]["source=gitlab"] == 5

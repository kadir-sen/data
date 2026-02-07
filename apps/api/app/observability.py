"""In-process observability: counters, histograms, and gauges.

Thread-safe via threading.Lock (GIL + lock keeps things simple).
No external dependencies — works standalone and exposes a /obs/metrics endpoint.

Metric types
────────────
Counter   – monotonically increasing (requests, failures)
Histogram – tracks value distribution with percentiles (latency, duration)
Gauge     – point-in-time value (active connections, queue depth)
"""

from __future__ import annotations

import math
import threading
import time
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Any


_lock = threading.Lock()


# ── Counter ────────────────────────────────────────────────────────
@dataclass
class _Counter:
    value: float = 0.0


_counters: dict[str, dict[str, _Counter]] = defaultdict(dict)


def counter_inc(name: str, value: float = 1.0, **labels: str) -> None:
    """Increment a counter."""
    key = _label_key(labels)
    with _lock:
        bucket = _counters[name]
        if key not in bucket:
            bucket[key] = _Counter()
        bucket[key].value += value


def counter_get(name: str, **labels: str) -> float:
    key = _label_key(labels)
    with _lock:
        return _counters.get(name, {}).get(key, _Counter()).value


# ── Histogram ──────────────────────────────────────────────────────
@dataclass
class _Histogram:
    values: list[float] = field(default_factory=list)
    total: float = 0.0
    count: int = 0


_histograms: dict[str, dict[str, _Histogram]] = defaultdict(dict)


def histogram_observe(name: str, value: float, **labels: str) -> None:
    """Record an observation (e.g. latency in ms)."""
    key = _label_key(labels)
    with _lock:
        bucket = _histograms[name]
        if key not in bucket:
            bucket[key] = _Histogram()
        h = bucket[key]
        h.values.append(value)
        h.total += value
        h.count += 1


def histogram_summary(name: str, **labels: str) -> dict[str, float]:
    """Return count, sum, avg, p50, p95, p99 for a histogram."""
    key = _label_key(labels)
    with _lock:
        h = _histograms.get(name, {}).get(key, _Histogram())
        if h.count == 0:
            return {"count": 0, "sum": 0, "avg": 0, "p50": 0, "p95": 0, "p99": 0}
        sorted_vals = sorted(h.values)
        return {
            "count": h.count,
            "sum": round(h.total, 2),
            "avg": round(h.total / h.count, 2),
            "p50": _percentile(sorted_vals, 0.50),
            "p95": _percentile(sorted_vals, 0.95),
            "p99": _percentile(sorted_vals, 0.99),
        }


# ── Gauge ──────────────────────────────────────────────────────────
_gauges: dict[str, dict[str, float]] = defaultdict(dict)


def gauge_set(name: str, value: float, **labels: str) -> None:
    key = _label_key(labels)
    with _lock:
        _gauges[name][key] = value


def gauge_inc(name: str, value: float = 1.0, **labels: str) -> None:
    key = _label_key(labels)
    with _lock:
        _gauges[name][key] = _gauges[name].get(key, 0.0) + value


def gauge_get(name: str, **labels: str) -> float:
    key = _label_key(labels)
    with _lock:
        return _gauges.get(name, {}).get(key, 0.0)


# ── Snapshot (for /obs/metrics) ────────────────────────────────────
def snapshot() -> dict[str, Any]:
    """Return a JSON-serialisable snapshot of all metrics."""
    with _lock:
        out: dict[str, Any] = {"_ts": time.time()}

        out["counters"] = {}
        for name, buckets in _counters.items():
            out["counters"][name] = {k: c.value for k, c in buckets.items()}

        out["histograms"] = {}
        for name, buckets in _histograms.items():
            out["histograms"][name] = {}
            for k, h in buckets.items():
                if h.count == 0:
                    continue
                sorted_vals = sorted(h.values)
                out["histograms"][name][k] = {
                    "count": h.count,
                    "sum": round(h.total, 2),
                    "avg": round(h.total / h.count, 2),
                    "p50": _percentile(sorted_vals, 0.50),
                    "p95": _percentile(sorted_vals, 0.95),
                    "p99": _percentile(sorted_vals, 0.99),
                }

        out["gauges"] = {}
        for name, buckets in _gauges.items():
            out["gauges"][name] = dict(buckets)

        return out


def reset() -> None:
    """Clear all metrics (useful for tests)."""
    with _lock:
        _counters.clear()
        _histograms.clear()
        _gauges.clear()


# ── Helpers ────────────────────────────────────────────────────────
def _label_key(labels: dict[str, str]) -> str:
    if not labels:
        return ""
    return ",".join(f"{k}={v}" for k, v in sorted(labels.items()))


def _percentile(sorted_data: list[float], pct: float) -> float:
    if not sorted_data:
        return 0.0
    idx = pct * (len(sorted_data) - 1)
    lo = math.floor(idx)
    hi = math.ceil(idx)
    if lo == hi:
        return round(sorted_data[lo], 2)
    frac = idx - lo
    return round(sorted_data[lo] * (1 - frac) + sorted_data[hi] * frac, 2)

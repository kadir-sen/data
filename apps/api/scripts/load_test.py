#!/usr/bin/env python3
"""Load test for /obs/metrics and dashboard /metrics endpoints.

Usage:
    python scripts/load_test.py [--base-url http://localhost:8000] [--duration 30] [--concurrency 10]

Measures:
  - Requests per second (RPS)
  - Latency percentiles (p50, p95, p99)
  - Error rate
  - Total requests completed
"""

from __future__ import annotations

import argparse
import asyncio
import math
import statistics
import time
from dataclasses import dataclass, field

import httpx


@dataclass
class LoadTestResult:
    endpoint: str
    total_requests: int = 0
    total_errors: int = 0
    latencies_ms: list[float] = field(default_factory=list)
    duration_s: float = 0.0

    @property
    def rps(self) -> float:
        return self.total_requests / self.duration_s if self.duration_s > 0 else 0

    @property
    def error_rate(self) -> float:
        return self.total_errors / self.total_requests * 100 if self.total_requests > 0 else 0

    def percentile(self, pct: float) -> float:
        if not self.latencies_ms:
            return 0.0
        sorted_lats = sorted(self.latencies_ms)
        idx = pct * (len(sorted_lats) - 1)
        lo = math.floor(idx)
        hi = math.ceil(idx)
        if lo == hi:
            return sorted_lats[lo]
        frac = idx - lo
        return sorted_lats[lo] * (1 - frac) + sorted_lats[hi] * frac

    def report(self) -> str:
        lines = [
            f"\n{'=' * 60}",
            f"  Endpoint: {self.endpoint}",
            f"{'=' * 60}",
            f"  Duration:        {self.duration_s:.1f}s",
            f"  Total requests:  {self.total_requests}",
            f"  Total errors:    {self.total_errors}",
            f"  Error rate:      {self.error_rate:.1f}%",
            f"  RPS:             {self.rps:.1f}",
        ]
        if self.latencies_ms:
            lines.extend([
                f"  Avg latency:     {statistics.mean(self.latencies_ms):.1f}ms",
                f"  p50 latency:     {self.percentile(0.50):.1f}ms",
                f"  p95 latency:     {self.percentile(0.95):.1f}ms",
                f"  p99 latency:     {self.percentile(0.99):.1f}ms",
                f"  Min latency:     {min(self.latencies_ms):.1f}ms",
                f"  Max latency:     {max(self.latencies_ms):.1f}ms",
            ])
        lines.append(f"{'=' * 60}")
        return "\n".join(lines)


async def _worker(
    client: httpx.AsyncClient,
    url: str,
    result: LoadTestResult,
    stop_event: asyncio.Event,
) -> None:
    """Continuously hit the endpoint until the stop event fires."""
    while not stop_event.is_set():
        start = time.perf_counter()
        try:
            resp = await client.get(url)
            latency = (time.perf_counter() - start) * 1000
            result.total_requests += 1
            result.latencies_ms.append(latency)
            if resp.status_code >= 400:
                result.total_errors += 1
        except Exception:
            result.total_requests += 1
            result.total_errors += 1


async def run_load_test(
    base_url: str,
    endpoint: str,
    duration_s: int,
    concurrency: int,
) -> LoadTestResult:
    result = LoadTestResult(endpoint=endpoint)
    stop_event = asyncio.Event()

    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        # Warm up
        try:
            await client.get(endpoint)
        except Exception:
            pass

        wall_start = time.perf_counter()
        tasks = [
            asyncio.create_task(_worker(client, endpoint, result, stop_event))
            for _ in range(concurrency)
        ]

        await asyncio.sleep(duration_s)
        stop_event.set()

        await asyncio.gather(*tasks, return_exceptions=True)
        result.duration_s = time.perf_counter() - wall_start

    return result


async def main() -> None:
    parser = argparse.ArgumentParser(description="Load test for metrics endpoints")
    parser.add_argument("--base-url", default="http://localhost:8000")
    parser.add_argument("--duration", type=int, default=30, help="Duration in seconds")
    parser.add_argument("--concurrency", type=int, default=10, help="Concurrent workers")
    args = parser.parse_args()

    endpoints = [
        "/obs/metrics",
        "/metrics",
        "/healthz",
    ]

    print(f"Load test config: base_url={args.base_url}, duration={args.duration}s, "
          f"concurrency={args.concurrency}")
    print(f"Endpoints: {endpoints}")
    print()

    for ep in endpoints:
        print(f"Testing {ep} ...")
        result = await run_load_test(
            base_url=args.base_url,
            endpoint=ep,
            duration_s=args.duration,
            concurrency=args.concurrency,
        )
        print(result.report())

    print("\nLoad test complete.")


if __name__ == "__main__":
    asyncio.run(main())

"""End-to-end tests for /reports endpoints."""

import uuid
from datetime import date

from httpx import AsyncClient

from app.models.report import Report


async def test_list_reports_empty(client: AsyncClient) -> None:
    resp = await client.get("/reports")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0


async def test_create_report(client: AsyncClient) -> None:
    payload = {
        "period": "weekly",
        "period_start": "2025-01-06",
        "period_end": "2025-01-12",
        "title": "Week 2 Report",
        "summary": "Good week.",
        "metrics": {"velocity": 42, "burndown_remaining": 5},
    }
    resp = await client.post("/reports", json=payload)
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Week 2 Report"
    assert body["metrics"]["velocity"] == 42


async def test_list_with_period_filter(
    client: AsyncClient,
    seeded_report: Report,
) -> None:
    resp = await client.get("/reports", params={"period": "weekly"})
    body = resp.json()
    assert body["total"] >= 1

    resp = await client.get("/reports", params={"period": "daily"})
    body = resp.json()
    assert body["total"] == 0


async def test_get_latest_report(
    client: AsyncClient,
    seeded_report: Report,
) -> None:
    resp = await client.get("/reports/latest", params={"period": "weekly"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["title"] == "Sprint 42 Report"


async def test_get_latest_report_none(client: AsyncClient) -> None:
    resp = await client.get("/reports/latest", params={"period": "monthly"})
    assert resp.status_code == 200
    assert resp.json() is None


async def test_get_report_by_id(
    client: AsyncClient,
    seeded_report: Report,
) -> None:
    resp = await client.get(f"/reports/{seeded_report.id}")
    assert resp.status_code == 200
    assert resp.json()["title"] == "Sprint 42 Report"


async def test_update_report(
    client: AsyncClient,
    seeded_report: Report,
) -> None:
    resp = await client.patch(
        f"/reports/{seeded_report.id}",
        json={"summary": "Updated summary", "metrics": {"velocity": 50}},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["summary"] == "Updated summary"
    assert body["metrics"]["velocity"] == 50


async def test_delete_report(
    client: AsyncClient,
    seeded_report: Report,
) -> None:
    resp = await client.delete(f"/reports/{seeded_report.id}")
    assert resp.status_code == 204

    resp = await client.get(f"/reports/{seeded_report.id}")
    assert resp.status_code == 404


async def test_reports_pagination(client: AsyncClient) -> None:
    for i in range(4):
        await client.post("/reports", json={
            "period": "daily",
            "period_start": f"2025-01-{10 + i:02d}",
            "period_end": f"2025-01-{10 + i:02d}",
            "title": f"Daily {i}",
            "metrics": {},
        })

    resp = await client.get("/reports", params={"limit": 2, "offset": 0})
    body = resp.json()
    assert body["total"] == 4
    assert len(body["items"]) == 2

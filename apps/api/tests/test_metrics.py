"""End-to-end tests for /metrics endpoints."""

import uuid
from datetime import date, timedelta

from httpx import AsyncClient

from app.models.effort_log import EffortLog
from app.models.sprint import Sprint
from app.models.work_item import WorkItem


async def test_metrics_empty_db(client: AsyncClient) -> None:
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    body = resp.json()
    assert "charts" in body
    assert "tables" in body
    assert "summary" in body
    assert body["summary"]["total_work_items"] == 0


async def test_metrics_with_data(
    client: AsyncClient,
    seeded_sprint: Sprint,
    seeded_work_items: list[WorkItem],
    seeded_effort_logs: list[EffortLog],
) -> None:
    resp = await client.get("/metrics")
    assert resp.status_code == 200
    body = resp.json()

    # Charts should have velocity, effort_breakdown, status_distribution
    assert "velocity" in body["charts"]
    assert "effort_breakdown" in body["charts"]
    assert "status_distribution" in body["charts"]

    # Velocity should have 2 series (Committed, Completed)
    assert len(body["charts"]["velocity"]) == 2

    # Tables mirror charts
    assert "velocity" in body["tables"]
    assert "status_distribution" in body["tables"]

    # Summary KPIs
    assert body["summary"]["total_work_items"] == 5
    assert body["summary"]["done_work_items"] >= 1
    assert body["summary"]["velocity_avg"] >= 0
    assert body["summary"]["total_effort_hours"] > 0


async def test_metrics_with_burndown(
    client: AsyncClient,
    seeded_sprint: Sprint,
    seeded_work_items: list[WorkItem],
    sprint_id: uuid.UUID,
) -> None:
    resp = await client.get("/metrics", params={"sprint_id": str(sprint_id)})
    assert resp.status_code == 200
    body = resp.json()
    # Burndown should be present when sprint_id is given
    assert "burndown" in body["charts"]
    assert len(body["charts"]["burndown"]) == 2  # Ideal + Actual


async def test_velocity_endpoint(
    client: AsyncClient,
    seeded_sprint: Sprint,
    seeded_work_items: list[WorkItem],
) -> None:
    resp = await client.get("/metrics/velocity")
    assert resp.status_code == 200
    body = resp.json()
    assert "chart" in body
    assert "table" in body
    assert len(body["chart"]) == 2  # Committed + Completed series


async def test_burndown_endpoint(
    client: AsyncClient,
    seeded_sprint: Sprint,
    seeded_work_items: list[WorkItem],
    sprint_id: uuid.UUID,
) -> None:
    resp = await client.get(f"/metrics/burndown/{sprint_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert "chart" in body
    assert "table" in body
    # Should have data points for each day
    assert len(body["table"]) > 0


async def test_burndown_nonexistent_sprint(client: AsyncClient) -> None:
    resp = await client.get(f"/metrics/burndown/{uuid.uuid4()}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["table"] == []


async def test_sprint_dashboard(
    client: AsyncClient,
    seeded_sprint: Sprint,
    seeded_work_items: list[WorkItem],
    sprint_id: uuid.UUID,
) -> None:
    resp = await client.get(f"/metrics/sprint/{sprint_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sprint"]["name"] == "Sprint 42"
    assert "burndown" in body
    assert "velocity" in body
    assert "scope_change" in body
    assert "report" in body
    assert "cumulative_flow" in body
    assert "lead_cycle_time" in body
    assert "throughput" in body


async def test_sprint_dashboard_not_found(client: AsyncClient) -> None:
    resp = await client.get(f"/metrics/sprint/{uuid.uuid4()}")
    assert resp.status_code == 404


async def test_team_dashboard(
    client: AsyncClient,
    seeded_sprint: Sprint,
    seeded_work_items: list[WorkItem],
    seeded_person,
) -> None:
    today = date.today()
    resp = await client.get(
        "/metrics/team/Backend",
        params={"from": (today - timedelta(days=30)).isoformat(), "to": today.isoformat()},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["team_id"] == "Backend"
    assert "velocity" in body
    assert "cumulative_flow" in body
    assert "throughput" in body
    assert "due_date_risk" in body


async def test_team_dashboard_bad_dates(client: AsyncClient) -> None:
    resp = await client.get(
        "/metrics/team/Backend",
        params={"from": "2025-02-01", "to": "2025-01-01"},
    )
    assert resp.status_code == 400

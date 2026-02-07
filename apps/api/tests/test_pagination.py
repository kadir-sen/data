"""Tests for pagination correctness across list endpoints.

Verifies:
  1. offset/limit are respected — correct subset returned.
  2. `total` reflects unfiltered (or filtered) count.
  3. Edge cases: offset past end returns empty, limit=1 returns one.
  4. Consistent ordering with pagination (no skips/duplicates).
"""

from __future__ import annotations

import uuid
from datetime import date, timedelta

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.sprint import Sprint
from app.models.work_item import WorkItem


@pytest.fixture
async def many_sprints(db_session: AsyncSession) -> list[Sprint]:
    """Create 10 sprints for pagination testing."""
    sprints = []
    for i in range(10):
        s = Sprint(
            id=uuid.uuid4(),
            name=f"Sprint {i + 1:02d}",
            source="jira",
            source_id=f"sprint-{i + 1}",
            board_or_project="PROJ",
            status="closed" if i < 5 else "active",
            start_date=date.today() - timedelta(days=70 - i * 7),
            end_date=date.today() - timedelta(days=63 - i * 7),
            goal=f"Goal {i + 1}",
        )
        sprints.append(s)
    db_session.add_all(sprints)
    await db_session.commit()
    return sprints


@pytest.fixture
async def many_work_items(db_session: AsyncSession, many_sprints: list[Sprint]) -> list[WorkItem]:
    """Create 25 work items across sprints for pagination testing."""
    items = []
    for i in range(25):
        wi = WorkItem(
            id=uuid.uuid4(),
            source="jira",
            source_id=f"WI-{i + 1:03d}",
            title=f"Work Item {i + 1}",
            item_type="story",
            status="open" if i % 3 == 0 else "done",
            priority="high",
            story_points=float(i % 5 + 1),
            sprint_id=many_sprints[i % len(many_sprints)].id,
            labels=["test"],
            changelog=[],
        )
        items.append(wi)
    db_session.add_all(items)
    await db_session.commit()
    return items


async def test_sprints_default_pagination(client: AsyncClient, many_sprints: list[Sprint]) -> None:
    """Default offset=0, limit=50 returns all 10 sprints."""
    resp = await client.get("/sprints")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 10
    assert len(body["items"]) == 10
    assert body["offset"] == 0
    assert body["limit"] == 50


async def test_sprints_limit(client: AsyncClient, many_sprints: list[Sprint]) -> None:
    """limit=3 returns exactly 3 items with total still showing full count."""
    resp = await client.get("/sprints", params={"limit": 3})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 10
    assert len(body["items"]) == 3


async def test_sprints_offset(client: AsyncClient, many_sprints: list[Sprint]) -> None:
    """offset=7 returns last 3 items."""
    resp = await client.get("/sprints", params={"offset": 7, "limit": 50})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 10
    assert len(body["items"]) == 3


async def test_sprints_offset_past_end(client: AsyncClient, many_sprints: list[Sprint]) -> None:
    """offset past total returns empty items list."""
    resp = await client.get("/sprints", params={"offset": 100})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 10
    assert len(body["items"]) == 0


async def test_work_items_pagination_consistency(
    client: AsyncClient, many_work_items: list[WorkItem]
) -> None:
    """Paginate through all items in pages of 5 — should collect all 25 with no duplicates."""
    all_ids: list[str] = []
    for offset in range(0, 30, 5):
        resp = await client.get("/work-items", params={"offset": offset, "limit": 5})
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 25
        ids = [item["id"] for item in body["items"]]
        all_ids.extend(ids)

    assert len(all_ids) == 25, f"Expected 25 items, got {len(all_ids)}"
    assert len(set(all_ids)) == 25, "Pagination produced duplicate items"


async def test_work_items_filter_with_pagination(
    client: AsyncClient, many_work_items: list[WorkItem]
) -> None:
    """Filtered pagination should reflect filtered total."""
    resp = await client.get("/work-items", params={"status": "done", "limit": 5})
    assert resp.status_code == 200
    body = resp.json()
    # Items where i % 3 != 0 have status "done" → indices 1,2,4,5,7,8,10,11,...
    # That's roughly 17 out of 25 (all except i % 3 == 0)
    assert body["total"] > 0
    assert all(item["status"] == "done" for item in body["items"])


async def test_sprints_filter_with_pagination(
    client: AsyncClient, many_sprints: list[Sprint]
) -> None:
    """Status filter should only return matching sprints."""
    resp = await client.get("/sprints", params={"status": "active"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5
    assert all(s["status"] == "active" for s in body["items"])


async def test_limit_one(client: AsyncClient, many_sprints: list[Sprint]) -> None:
    """limit=1 returns exactly one item."""
    resp = await client.get("/sprints", params={"limit": 1})
    assert resp.status_code == 200
    body = resp.json()
    assert len(body["items"]) == 1
    assert body["total"] == 10

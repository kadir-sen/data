"""End-to-end tests for /work-items endpoints."""

import uuid

from httpx import AsyncClient

from app.models.person import Person
from app.models.sprint import Sprint
from app.models.work_item import WorkItem


async def test_list_work_items_empty(client: AsyncClient) -> None:
    resp = await client.get("/work-items")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0


async def test_create_work_item(
    client: AsyncClient,
    seeded_sprint: Sprint,
    seeded_person: Person,
) -> None:
    payload = {
        "source": "jira",
        "source_id": "PROJ-999",
        "title": "Implement caching",
        "item_type": "story",
        "status": "open",
        "priority": "high",
        "story_points": 8.0,
        "sprint_id": str(seeded_sprint.id),
        "assignee_id": str(seeded_person.id),
    }
    resp = await client.post("/work-items", json=payload)
    assert resp.status_code == 201
    body = resp.json()
    assert body["title"] == "Implement caching"
    assert body["story_points"] == 8.0


async def test_list_with_status_filter(
    client: AsyncClient,
    seeded_work_items: list[WorkItem],
) -> None:
    resp = await client.get("/work-items", params={"status": "done"})
    body = resp.json()
    assert body["total"] >= 1
    assert all(i["status"] == "done" for i in body["items"])


async def test_list_with_sprint_filter(
    client: AsyncClient,
    seeded_work_items: list[WorkItem],
    sprint_id: uuid.UUID,
) -> None:
    resp = await client.get("/work-items", params={"sprint_id": str(sprint_id)})
    body = resp.json()
    assert body["total"] == 5  # seeded_work_items has 5


async def test_list_with_assignee_filter(
    client: AsyncClient,
    seeded_work_items: list[WorkItem],
    person_id: uuid.UUID,
) -> None:
    resp = await client.get("/work-items", params={"assignee_id": str(person_id)})
    body = resp.json()
    assert body["total"] == 5


async def test_get_work_item(
    client: AsyncClient,
    seeded_work_items: list[WorkItem],
) -> None:
    item_id = seeded_work_items[0].id
    resp = await client.get(f"/work-items/{item_id}")
    assert resp.status_code == 200
    assert resp.json()["source_id"] == "PROJ-1"


async def test_update_work_item(
    client: AsyncClient,
    seeded_work_items: list[WorkItem],
) -> None:
    item_id = seeded_work_items[0].id
    resp = await client.patch(f"/work-items/{item_id}", json={"status": "done", "story_points": 13})
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "done"
    assert body["story_points"] == 13


async def test_delete_work_item(
    client: AsyncClient,
    seeded_work_items: list[WorkItem],
) -> None:
    item_id = seeded_work_items[0].id
    resp = await client.delete(f"/work-items/{item_id}")
    assert resp.status_code == 204

    resp = await client.get(f"/work-items/{item_id}")
    assert resp.status_code == 404


async def test_pagination_and_sorting(
    client: AsyncClient,
    seeded_work_items: list[WorkItem],
) -> None:
    resp = await client.get("/work-items", params={"limit": 2, "offset": 0, "sort_by": "status", "sort_order": "asc"})
    body = resp.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2

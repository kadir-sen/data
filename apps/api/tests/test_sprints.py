"""End-to-end tests for /sprints endpoints."""

import uuid

from httpx import AsyncClient

from app.models.sprint import Sprint


async def test_list_sprints_empty(client: AsyncClient) -> None:
    resp = await client.get("/sprints")
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0


async def test_create_sprint(client: AsyncClient) -> None:
    payload = {
        "name": "Sprint 50",
        "source": "jira",
        "source_id": "sprint-50",
        "status": "future",
        "start_date": "2025-03-01",
        "end_date": "2025-03-14",
        "goal": "Ship payments",
    }
    resp = await client.post("/sprints", json=payload)
    assert resp.status_code == 201
    body = resp.json()
    assert body["name"] == "Sprint 50"
    assert body["status"] == "future"
    assert "id" in body
    assert body["work_item_count"] == 0


async def test_list_sprints_with_filter(client: AsyncClient, seeded_sprint: Sprint) -> None:
    # Should find the active sprint
    resp = await client.get("/sprints", params={"status": "active"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] >= 1
    assert any(s["name"] == "Sprint 42" for s in body["items"])

    # Should not find a closed sprint
    resp = await client.get("/sprints", params={"status": "closed"})
    body = resp.json()
    assert not any(s["name"] == "Sprint 42" for s in body["items"])


async def test_get_sprint_by_id(client: AsyncClient, seeded_sprint: Sprint, sprint_id: uuid.UUID) -> None:
    resp = await client.get(f"/sprints/{sprint_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Sprint 42"
    assert body["status"] == "active"


async def test_get_sprint_not_found(client: AsyncClient) -> None:
    resp = await client.get(f"/sprints/{uuid.uuid4()}")
    assert resp.status_code == 404


async def test_update_sprint(client: AsyncClient, seeded_sprint: Sprint, sprint_id: uuid.UUID) -> None:
    resp = await client.patch(f"/sprints/{sprint_id}", json={"status": "closed"})
    assert resp.status_code == 200
    assert resp.json()["status"] == "closed"


async def test_delete_sprint(client: AsyncClient, seeded_sprint: Sprint, sprint_id: uuid.UUID) -> None:
    resp = await client.delete(f"/sprints/{sprint_id}")
    assert resp.status_code == 204

    resp = await client.get(f"/sprints/{sprint_id}")
    assert resp.status_code == 404


async def test_list_sprints_pagination(client: AsyncClient) -> None:
    # Create 5 sprints
    for i in range(5):
        await client.post("/sprints", json={
            "name": f"Sprint {i}",
            "source": "jira",
            "source_id": f"s-{i}",
            "status": "future",
        })

    resp = await client.get("/sprints", params={"limit": 2, "offset": 0})
    body = resp.json()
    assert body["total"] == 5
    assert len(body["items"]) == 2
    assert body["offset"] == 0
    assert body["limit"] == 2

    resp = await client.get("/sprints", params={"limit": 2, "offset": 4})
    body = resp.json()
    assert len(body["items"]) == 1


async def test_list_sprints_sorting(client: AsyncClient) -> None:
    await client.post("/sprints", json={
        "name": "Alpha",
        "source": "jira",
        "source_id": "s-alpha",
        "status": "future",
    })
    await client.post("/sprints", json={
        "name": "Zeta",
        "source": "jira",
        "source_id": "s-zeta",
        "status": "future",
    })

    resp = await client.get("/sprints", params={"sort_by": "name", "sort_order": "asc"})
    names = [s["name"] for s in resp.json()["items"]]
    assert names == sorted(names)

    resp = await client.get("/sprints", params={"sort_by": "name", "sort_order": "desc"})
    names = [s["name"] for s in resp.json()["items"]]
    assert names == sorted(names, reverse=True)

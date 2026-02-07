"""Comprehensive tests for /effort endpoints — RBAC, validations, CRUD."""

import uuid
from datetime import date, timedelta

from httpx import AsyncClient

from app.models.effort_log import EffortLog
from app.models.person import Person
from app.models.sprint import Sprint
from app.models.work_item import WorkItem


# ── POST /effort ──────────────────────────────────────────────────


async def test_create_effort_admin(
    client: AsyncClient,
    seeded_admin_person: Person,
) -> None:
    """Admin can create effort entries."""
    payload = {
        "day": date.today().isoformat(),
        "hours": 6.5,
        "category": "development",
        "description": "Worked on auth module",
    }
    resp = await client.post("/effort", json=payload)
    assert resp.status_code == 201
    body = resp.json()
    assert body["hours"] == 6.5
    assert body["category"] == "development"
    assert body["person_id"] == str(seeded_admin_person.id)
    assert body["locked"] is False


async def test_create_effort_member(
    member_client: AsyncClient,
    seeded_person: Person,
) -> None:
    """Member can create their own effort entries."""
    payload = {
        "day": date.today().isoformat(),
        "hours": 4.0,
        "category": "review",
        "description": "Code review",
    }
    resp = await member_client.post("/effort", json=payload)
    assert resp.status_code == 201
    body = resp.json()
    assert body["person_id"] == str(seeded_person.id)


async def test_create_effort_with_planned_hours(
    client: AsyncClient,
    seeded_admin_person: Person,
) -> None:
    """planned_hours field is accepted and returned."""
    payload = {
        "day": date.today().isoformat(),
        "hours": 6.0,
        "category": "development",
        "planned_hours": 8.0,
    }
    resp = await client.post("/effort", json=payload)
    assert resp.status_code == 201
    assert resp.json()["planned_hours"] == 8.0


async def test_create_effort_validates_max_hours(
    client: AsyncClient,
    seeded_admin_person: Person,
) -> None:
    """Cannot exceed 24h in one day."""
    day = date.today().isoformat()
    # First entry: 20h
    resp1 = await client.post("/effort", json={"day": day, "hours": 20.0, "category": "development"})
    assert resp1.status_code == 201

    # Second entry that would exceed 24h
    resp2 = await client.post("/effort", json={"day": day, "hours": 5.0, "category": "meeting"})
    assert resp2.status_code == 422
    assert "exceed" in resp2.json()["detail"].lower()


async def test_create_effort_validates_hours_range(
    client: AsyncClient,
    seeded_admin_person: Person,
) -> None:
    """Hours must be > 0 and <= 24."""
    resp = await client.post("/effort", json={
        "day": date.today().isoformat(),
        "hours": 0,
        "category": "development",
    })
    assert resp.status_code == 422  # Pydantic validation (gt=0)


async def test_create_effort_validates_category(
    client: AsyncClient,
    seeded_admin_person: Person,
) -> None:
    """Invalid category is rejected."""
    resp = await client.post("/effort", json={
        "day": date.today().isoformat(),
        "hours": 2.0,
        "category": "invalid_cat",
    })
    assert resp.status_code == 422


async def test_create_effort_no_person_linked(
    manager_client: AsyncClient,
) -> None:
    """If no Person is linked to the user, returns 404."""
    resp = await manager_client.post("/effort", json={
        "day": date.today().isoformat(),
        "hours": 2.0,
        "category": "meeting",
    })
    assert resp.status_code == 404
    assert "No Person record" in resp.json()["detail"]


# ── GET /effort/me ────────────────────────────────────────────────


async def test_get_my_effort(
    member_client: AsyncClient,
    seeded_person: Person,
    seeded_effort_logs: list[EffortLog],
) -> None:
    """Member can see their own effort."""
    today = date.today()
    resp = await member_client.get("/effort/me", params={
        "from": (today - timedelta(days=10)).isoformat(),
        "to": today.isoformat(),
    })
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 5  # 5 seeded entries


async def test_get_my_effort_date_range_filter(
    member_client: AsyncClient,
    seeded_person: Person,
    seeded_effort_logs: list[EffortLog],
) -> None:
    """Date range properly filters results."""
    today = date.today()
    resp = await member_client.get("/effort/me", params={
        "from": (today - timedelta(days=1)).isoformat(),
        "to": today.isoformat(),
    })
    assert resp.status_code == 200
    body = resp.json()
    assert len(body) == 2  # today and yesterday


# ── GET /effort/team/{team_id} — RBAC ────────────────────────────


async def test_team_effort_admin(
    client: AsyncClient,
    seeded_admin_person: Person,
    seeded_effort_logs: list[EffortLog],
) -> None:
    """Admin can view team effort (has wildcard permission)."""
    today = date.today()
    resp = await client.get("/effort/team/Backend", params={
        "from": (today - timedelta(days=10)).isoformat(),
        "to": today.isoformat(),
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["team_id"] == "Backend"
    assert body["total_hours"] > 0
    assert len(body["members"]) > 0
    assert len(body["by_day"]) > 0


async def test_team_effort_manager(
    manager_client: AsyncClient,
    seeded_manager_person: Person,
    seeded_effort_logs: list[EffortLog],
) -> None:
    """Manager can view team effort."""
    today = date.today()
    resp = await manager_client.get("/effort/team/Backend", params={
        "from": (today - timedelta(days=10)).isoformat(),
        "to": today.isoformat(),
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["total_hours"] > 0


async def test_team_effort_member_forbidden(
    member_client: AsyncClient,
    seeded_person: Person,
) -> None:
    """Member cannot view team effort (no effort:read_team permission)."""
    today = date.today()
    resp = await member_client.get("/effort/team/Backend", params={
        "from": (today - timedelta(days=10)).isoformat(),
        "to": today.isoformat(),
    })
    assert resp.status_code == 403


async def test_team_effort_unknown_team(
    client: AsyncClient,
    seeded_admin_person: Person,
) -> None:
    """Unknown team returns 404."""
    today = date.today()
    resp = await client.get("/effort/team/nonexistent", params={
        "from": (today - timedelta(days=10)).isoformat(),
        "to": today.isoformat(),
    })
    assert resp.status_code == 404


# ── GET /effort/sprint/{sprint_id} ───────────────────────────────


async def test_sprint_effort(
    client: AsyncClient,
    seeded_admin_person: Person,
    seeded_sprint: Sprint,
    seeded_effort_logs: list[EffortLog],
) -> None:
    """Sprint effort returns aggregated data."""
    resp = await client.get(f"/effort/sprint/{seeded_sprint.id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["sprint_name"] == "Sprint 42"
    assert body["total_effort_hours"] > 0
    assert body["items_total"] == 5
    assert body["items_done"] == 2  # done + closed


async def test_sprint_effort_not_found(
    client: AsyncClient,
    seeded_admin_person: Person,
) -> None:
    """Non-existent sprint returns 404."""
    resp = await client.get(f"/effort/sprint/{uuid.uuid4()}")
    assert resp.status_code == 404


# ── PUT /effort/{id} ─────────────────────────────────────────────


async def test_update_own_effort(
    member_client: AsyncClient,
    seeded_person: Person,
    seeded_effort_logs: list[EffortLog],
) -> None:
    """Member can update their own effort entry."""
    log_id = seeded_effort_logs[0].id
    resp = await member_client.put(f"/effort/{log_id}", json={"hours": 7.0})
    assert resp.status_code == 200
    assert resp.json()["hours"] == 7.0


async def test_update_validates_max_hours(
    member_client: AsyncClient,
    seeded_person: Person,
    seeded_effort_logs: list[EffortLog],
) -> None:
    """Update validates max hours per day."""
    log_id = seeded_effort_logs[0].id
    resp = await member_client.put(f"/effort/{log_id}", json={"hours": 24.5})
    assert resp.status_code == 422


async def test_update_nonexistent(
    client: AsyncClient,
    seeded_admin_person: Person,
) -> None:
    """Update non-existent entry returns 404."""
    resp = await client.put(f"/effort/{uuid.uuid4()}", json={"hours": 2.0})
    assert resp.status_code == 404


# ── DELETE /effort/{id} ──────────────────────────────────────────


async def test_delete_own_effort(
    member_client: AsyncClient,
    seeded_person: Person,
    seeded_effort_logs: list[EffortLog],
) -> None:
    """Member can delete their own effort entry."""
    log_id = seeded_effort_logs[0].id
    resp = await member_client.delete(f"/effort/{log_id}")
    assert resp.status_code == 204

    # Verify it's gone
    resp2 = await member_client.get(f"/effort/{log_id}")
    assert resp2.status_code == 404


async def test_delete_nonexistent(
    client: AsyncClient,
    seeded_admin_person: Person,
) -> None:
    """Delete non-existent entry returns 404."""
    resp = await client.delete(f"/effort/{uuid.uuid4()}")
    assert resp.status_code == 404


# ── GET /effort (paginated list) ─────────────────────────────────


async def test_list_effort_admin(
    client: AsyncClient,
    seeded_admin_person: Person,
    seeded_effort_logs: list[EffortLog],
) -> None:
    """Admin can list all effort entries."""
    resp = await client.get("/effort")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 5


async def test_list_effort_member_sees_only_own(
    member_client: AsyncClient,
    seeded_person: Person,
    seeded_effort_logs: list[EffortLog],
) -> None:
    """Member sees only their own effort entries in the paginated list."""
    resp = await member_client.get("/effort")
    assert resp.status_code == 200
    body = resp.json()
    # All 5 seeded logs belong to seeded_person (the member)
    assert body["total"] == 5
    for item in body["items"]:
        assert item["person_id"] == str(seeded_person.id)


async def test_list_effort_with_filters(
    client: AsyncClient,
    seeded_admin_person: Person,
    seeded_effort_logs: list[EffortLog],
) -> None:
    """Filtering by category works."""
    resp = await client.get("/effort", params={"category": "development"})
    body = resp.json()
    # Days 0, 2, 4 are development
    assert body["total"] == 3


# ── GET /effort/summary ──────────────────────────────────────────


async def test_effort_summary(
    client: AsyncClient,
    seeded_admin_person: Person,
    seeded_effort_logs: list[EffortLog],
) -> None:
    resp = await client.get("/effort/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert "categories" in body
    assert body["grand_total_hours"] > 0
    cats = {c["category"] for c in body["categories"]}
    assert "development" in cats


# ── Locked day tests ──────────────────────────────────────────────


async def test_locked_day_prevents_create(
    client: AsyncClient,
    seeded_admin_person: Person,
    db_session,
) -> None:
    """Cannot create effort on a locked day."""
    from sqlalchemy.ext.asyncio import AsyncSession

    session: AsyncSession = db_session
    locked_log = EffortLog(
        id=uuid.uuid4(),
        person_id=seeded_admin_person.id,
        day=date.today() - timedelta(days=30),
        hours=8.0,
        category="development",
        locked=True,
        source="manual",
    )
    session.add(locked_log)
    await session.commit()

    resp = await client.post("/effort", json={
        "day": (date.today() - timedelta(days=30)).isoformat(),
        "hours": 2.0,
        "category": "meeting",
    })
    assert resp.status_code == 409
    assert "locked" in resp.json()["detail"].lower()


async def test_locked_entry_prevents_update(
    client: AsyncClient,
    seeded_admin_person: Person,
    db_session,
) -> None:
    """Cannot update a locked effort entry."""
    from sqlalchemy.ext.asyncio import AsyncSession

    session: AsyncSession = db_session
    locked_log = EffortLog(
        id=uuid.uuid4(),
        person_id=seeded_admin_person.id,
        day=date.today() - timedelta(days=31),
        hours=8.0,
        category="development",
        locked=True,
        source="manual",
    )
    session.add(locked_log)
    await session.commit()

    resp = await client.put(f"/effort/{locked_log.id}", json={"hours": 4.0})
    assert resp.status_code == 409
    assert "locked" in resp.json()["detail"].lower()


async def test_locked_entry_prevents_delete(
    client: AsyncClient,
    seeded_admin_person: Person,
    db_session,
) -> None:
    """Cannot delete a locked effort entry."""
    from sqlalchemy.ext.asyncio import AsyncSession

    session: AsyncSession = db_session
    locked_log = EffortLog(
        id=uuid.uuid4(),
        person_id=seeded_admin_person.id,
        day=date.today() - timedelta(days=32),
        hours=8.0,
        category="development",
        locked=True,
        source="manual",
    )
    session.add(locked_log)
    await session.commit()

    resp = await client.delete(f"/effort/{locked_log.id}")
    assert resp.status_code == 409

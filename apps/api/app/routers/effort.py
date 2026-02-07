"""Effort / Timesheet endpoints.

POST   /effort              – log effort entry (auth required)
GET    /effort/me            – my effort (date range)
GET    /effort/team/{team}   – team aggregate (manager / admin)
GET    /effort/sprint/{id}   – sprint effort vs delivered work
GET    /effort               – list with filters (paginated)
GET    /effort/summary       – category breakdown
GET    /effort/{id}          – single entry
PUT    /effort/{id}          – update entry
DELETE /effort/{id}          – delete entry
"""

import uuid
from collections import defaultdict
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import log_event
from app.db import get_session
from app.models.effort_log import EffortLog
from app.models.work_item import WorkItem
from app.rbac import CurrentUser, get_current_user, require_permission
from app.repositories.effort_log import EffortLogRepo
from app.repositories.person import PersonRepo
from app.repositories.sprint import SprintRepo
from app.repositories.work_item import WorkItemRepo
from app.schemas.common import PaginatedResponse, SortOrder
from app.schemas.effort_log import (
    DaySummary,
    EffortLogCreate,
    EffortLogRead,
    EffortLogUpdate,
    SprintEffortResponse,
    TeamEffortResponse,
    TeamMemberEffort,
)

router = APIRouter(prefix="/effort", tags=["effort"])

MAX_HOURS_PER_DAY = 24.0


# ── Helpers ────────────────────────────────────────────────────────

async def _resolve_person(session: AsyncSession, user: CurrentUser):
    """Find the Person record linked to the authenticated user (by email)."""
    repo = PersonRepo(session)
    person = await repo.get_by_email(user.email)
    if not person:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No Person record linked to your account. Contact your admin.",
        )
    return person


# ── POST /effort ───────────────────────────────────────────────────

@router.post(
    "",
    response_model=EffortLogRead,
    status_code=status.HTTP_201_CREATED,
    summary="Log an effort entry",
    dependencies=[Depends(require_permission("effort:write"))],
)
async def create_effort(
    body: EffortLogCreate,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> EffortLogRead:
    person = await _resolve_person(session, user)
    repo = EffortLogRepo(session)

    # Locked-day check
    if await repo.has_locked_day(person.id, body.day):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Day {body.day} is locked and cannot be edited.",
        )

    # Max hours per day
    existing_hours = await repo.total_hours_for_day(person.id, body.day)
    if existing_hours + body.hours > MAX_HOURS_PER_DAY:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=(
                f"Adding {body.hours}h would exceed {MAX_HOURS_PER_DAY}h/day "
                f"(currently {existing_hours}h logged)."
            ),
        )

    entry = EffortLog(
        person_id=person.id,
        day=body.day,
        hours=body.hours,
        category=body.category,
        description=body.description,
        work_item_id=body.work_item_id,
        planned_hours=body.planned_hours,
        source=body.source,
        extra=body.extra,
    )
    await repo.create(entry)
    await log_event(
        session,
        action="effort.create",
        actor_id=uuid.UUID(user.id),
        resource_type="effort_log",
        resource_id=str(entry.id),
        detail=f"{body.hours}h on {body.day} [{body.category}]",
    )
    await repo.commit()
    return EffortLogRead.model_validate(entry)


# ── GET /effort/me ─────────────────────────────────────────────────

@router.get(
    "/me",
    response_model=list[EffortLogRead],
    summary="My effort logs (date range)",
    dependencies=[Depends(require_permission("effort:read"))],
)
async def get_my_effort(
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
    from_date: date = Query(..., alias="from", examples=["2025-01-01"]),
    to_date: date = Query(..., alias="to", examples=["2025-01-31"]),
) -> list[EffortLogRead]:
    person = await _resolve_person(session, user)
    repo = EffortLogRepo(session)
    entries = await repo.list_by_person_range(person.id, from_date, to_date)
    return [EffortLogRead.model_validate(e) for e in entries]


# ── GET /effort/team/{team_id} ─────────────────────────────────────

@router.get(
    "/team/{team_id}",
    response_model=TeamEffortResponse,
    summary="Team effort aggregate (manager / admin)",
    dependencies=[Depends(require_permission("effort:read_team"))],
)
async def get_team_effort(
    team_id: str,
    session: AsyncSession = Depends(get_session),
    from_date: date = Query(..., alias="from", examples=["2025-01-01"]),
    to_date: date = Query(..., alias="to", examples=["2025-01-31"]),
) -> TeamEffortResponse:
    person_repo = PersonRepo(session)
    members = await person_repo.list_by_team(team_id)
    if not members:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No team members found for team '{team_id}'.",
        )

    effort_repo = EffortLogRepo(session)
    person_ids = [m.id for m in members]
    logs = await effort_repo.list_by_person_ids_range(person_ids, from_date, to_date)

    # Aggregate
    total_hours = 0.0
    cat_totals: dict[str, float] = defaultdict(float)
    day_map: dict[date, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    member_map: dict[uuid.UUID, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    member_hours: dict[uuid.UUID, float] = defaultdict(float)
    person_name: dict[uuid.UUID, str] = {m.id: m.display_name for m in members}

    for log in logs:
        total_hours += log.hours
        cat_totals[log.category] += log.hours
        day_map[log.day][log.category] += log.hours
        member_map[log.person_id][log.category] += log.hours
        member_hours[log.person_id] += log.hours

    by_day = [
        DaySummary(
            day=d,
            total_hours=sum(cats.values()),
            by_category=dict(cats),
        )
        for d, cats in sorted(day_map.items())
    ]

    member_list = [
        TeamMemberEffort(
            person_id=pid,
            display_name=person_name.get(pid, "Unknown"),
            total_hours=member_hours[pid],
            by_category=dict(member_map[pid]),
        )
        for pid in sorted(member_hours, key=lambda p: member_hours[p], reverse=True)
    ]

    return TeamEffortResponse(
        team_id=team_id,
        from_date=from_date,
        to_date=to_date,
        total_hours=total_hours,
        by_category=dict(cat_totals),
        by_day=by_day,
        members=member_list,
    )


# ── GET /effort/sprint/{sprint_id} ────────────────────────────────

@router.get(
    "/sprint/{sprint_id}",
    response_model=SprintEffortResponse,
    summary="Sprint effort vs delivered work",
    dependencies=[Depends(require_permission("effort:read"))],
)
async def get_sprint_effort(
    sprint_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> SprintEffortResponse:
    sprint_repo = SprintRepo(session)
    sprint = await sprint_repo.get(sprint_id)
    if not sprint:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Sprint not found.",
        )

    wi_repo = WorkItemRepo(session)
    work_items: list[WorkItem] = await wi_repo.list_by_sprint(sprint_id)
    wi_ids = [wi.id for wi in work_items]

    effort_repo = EffortLogRepo(session)
    logs = await effort_repo.list_by_sprint_work_items(wi_ids)

    total_hours = 0.0
    cat_totals: dict[str, float] = defaultdict(float)
    for log in logs:
        total_hours += log.hours
        cat_totals[log.category] += log.hours

    total_sp = sum(wi.story_points or 0.0 for wi in work_items)
    done_count = sum(1 for wi in work_items if wi.status in ("done", "closed"))

    return SprintEffortResponse(
        sprint_id=sprint.id,
        sprint_name=sprint.name,
        total_effort_hours=total_hours,
        by_category=dict(cat_totals),
        total_story_points=total_sp if total_sp > 0 else None,
        items_done=done_count,
        items_total=len(work_items),
    )


# ── GET /effort (paginated list) ──────────────────────────────────

@router.get(
    "",
    response_model=PaginatedResponse[EffortLogRead],
    summary="List effort logs (paginated + filterable)",
    dependencies=[Depends(require_permission("effort:read"))],
)
async def list_effort_logs(
    user: CurrentUser = Depends(get_current_user),
    person_id: uuid.UUID | None = Query(None),
    work_item_id: uuid.UUID | None = Query(None),
    category: str | None = Query(None, examples=["development"]),
    source: str | None = Query(None, examples=["manual"]),
    day_from: date | None = Query(None, description="Start of date range (inclusive)"),
    day_to: date | None = Query(None, description="End of date range (inclusive)"),
    sort_by: str = Query("day", description="Column to sort by"),
    sort_order: SortOrder = Query(SortOrder.DESC),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> PaginatedResponse[EffortLogRead]:
    # Members can only see their own; managers/admins can see all
    if user.role == "member":
        person = await _resolve_person(session, user)
        person_id = person.id

    count_stmt = select(func.count(EffortLog.id))
    data_stmt = select(EffortLog)

    filters = []
    if person_id:
        filters.append(EffortLog.person_id == person_id)
    if work_item_id:
        filters.append(EffortLog.work_item_id == work_item_id)
    if category:
        filters.append(EffortLog.category == category)
    if source:
        filters.append(EffortLog.source == source)
    if day_from:
        filters.append(EffortLog.day >= day_from)
    if day_to:
        filters.append(EffortLog.day <= day_to)

    for f in filters:
        count_stmt = count_stmt.where(f)
        data_stmt = data_stmt.where(f)

    sort_col = getattr(EffortLog, sort_by, EffortLog.day)
    order = sort_col.asc() if sort_order == SortOrder.ASC else sort_col.desc()
    data_stmt = data_stmt.order_by(order.nullslast()).offset(offset).limit(limit)

    total_result = await session.execute(count_stmt)
    total = total_result.scalar_one()

    result = await session.execute(data_stmt)
    items = [EffortLogRead.model_validate(e) for e in result.scalars().all()]

    return PaginatedResponse(items=items, total=total, offset=offset, limit=limit)


# ── GET /effort/summary ───────────────────────────────────────────

@router.get(
    "/summary",
    summary="Effort summary by category",
    dependencies=[Depends(require_permission("effort:read"))],
)
async def effort_summary(
    person_id: uuid.UUID | None = Query(None),
    day_from: date | None = Query(None),
    day_to: date | None = Query(None),
    session: AsyncSession = Depends(get_session),
) -> dict:
    stmt = select(
        EffortLog.category,
        func.sum(EffortLog.hours).label("total_hours"),
        func.count(EffortLog.id).label("entry_count"),
    ).group_by(EffortLog.category)

    if person_id:
        stmt = stmt.where(EffortLog.person_id == person_id)
    if day_from:
        stmt = stmt.where(EffortLog.day >= day_from)
    if day_to:
        stmt = stmt.where(EffortLog.day <= day_to)

    result = await session.execute(stmt)
    rows = result.all()

    return {
        "categories": [
            {"category": r.category, "total_hours": float(r.total_hours), "entry_count": r.entry_count}
            for r in rows
        ],
        "grand_total_hours": sum(float(r.total_hours) for r in rows),
    }


# ── GET /effort/{log_id} ──────────────────────────────────────────

@router.get(
    "/{log_id}",
    response_model=EffortLogRead,
    summary="Get effort log by ID",
    dependencies=[Depends(require_permission("effort:read"))],
)
async def get_effort_log(
    log_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> EffortLogRead:
    log = await session.get(EffortLog, log_id)
    if not log:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Effort log not found")
    return EffortLogRead.model_validate(log)


# ── PUT /effort/{id} ──────────────────────────────────────────────

@router.put(
    "/{effort_id}",
    response_model=EffortLogRead,
    summary="Update an effort entry",
    dependencies=[Depends(require_permission("effort:write"))],
)
async def update_effort(
    effort_id: uuid.UUID,
    body: EffortLogUpdate,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> EffortLogRead:
    repo = EffortLogRepo(session)
    entry = await repo.get(effort_id)
    if not entry:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Effort entry not found.")

    # Only own entries (unless admin)
    person = await _resolve_person(session, user)
    if entry.person_id != person.id and user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot edit others' entries.")

    if entry.locked:
        raise HTTPException(status.HTTP_409_CONFLICT, "This entry is locked and cannot be edited.")

    # Validate max hours if hours are changing
    if body.hours is not None and body.hours != entry.hours:
        existing = await repo.total_hours_for_day(entry.person_id, entry.day)
        new_total = existing - entry.hours + body.hours
        if new_total > MAX_HOURS_PER_DAY:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Update would exceed {MAX_HOURS_PER_DAY}h/day ({new_total}h total).",
            )

    updates = body.model_dump(exclude_unset=True)
    await repo.update(entry, **updates)
    await log_event(
        session,
        action="effort.update",
        actor_id=uuid.UUID(user.id),
        resource_type="effort_log",
        resource_id=str(entry.id),
        detail=f"Updated fields: {list(updates.keys())}",
    )
    await repo.commit()
    return EffortLogRead.model_validate(entry)


# ── DELETE /effort/{id} ───────────────────────────────────────────

@router.delete(
    "/{effort_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Delete an effort entry",
    dependencies=[Depends(require_permission("effort:write"))],
)
async def delete_effort(
    effort_id: uuid.UUID,
    user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
) -> None:
    repo = EffortLogRepo(session)
    entry = await repo.get(effort_id)
    if not entry:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Effort entry not found.")

    person = await _resolve_person(session, user)
    if entry.person_id != person.id and user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Cannot delete others' entries.")

    if entry.locked:
        raise HTTPException(status.HTTP_409_CONFLICT, "This entry is locked and cannot be deleted.")

    await repo.delete(entry)
    await log_event(
        session,
        action="effort.delete",
        actor_id=uuid.UUID(user.id),
        resource_type="effort_log",
        resource_id=str(effort_id),
        detail=f"Deleted {entry.hours}h on {entry.day}",
    )
    await repo.commit()

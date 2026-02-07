"""Sprint endpoints — CRUD + filtered list with pagination & sorting."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.sprint import Sprint
from app.models.work_item import WorkItem
from app.schemas.common import PaginatedResponse, SortOrder
from app.schemas.sprint import SprintCreate, SprintRead, SprintUpdate

router = APIRouter(prefix="/sprints", tags=["sprints"])


def _sprint_to_read(sprint: Sprint, work_item_count: int = 0) -> SprintRead:
    return SprintRead(
        id=sprint.id,
        name=sprint.name,
        source=sprint.source,
        source_id=sprint.source_id,
        board_or_project=sprint.board_or_project,
        status=sprint.status,
        start_date=sprint.start_date,
        end_date=sprint.end_date,
        goal=sprint.goal,
        extra=sprint.extra,
        created_at=sprint.created_at,
        updated_at=sprint.updated_at,
        work_item_count=work_item_count,
    )


@router.get(
    "",
    response_model=PaginatedResponse[SprintRead],
    summary="List sprints",
    description="Filterable, paginated, sortable list of sprints.",
)
async def list_sprints(
    status: str | None = Query(None, description="Filter by status", examples=["active"]),
    source: str | None = Query(None, description="Filter by source", examples=["jira"]),
    sort_by: str = Query("start_date", description="Column to sort by"),
    sort_order: SortOrder = Query(SortOrder.DESC),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> PaginatedResponse[SprintRead]:
    # Count query
    count_stmt = select(func.count(Sprint.id))
    # Data query with work-item count sub-query
    wi_count = (
        select(func.count(WorkItem.id))
        .where(WorkItem.sprint_id == Sprint.id)
        .correlate(Sprint)
        .scalar_subquery()
    )
    data_stmt = select(Sprint, wi_count.label("wi_count"))

    # Apply filters
    if status:
        count_stmt = count_stmt.where(Sprint.status == status)
        data_stmt = data_stmt.where(Sprint.status == status)
    if source:
        count_stmt = count_stmt.where(Sprint.source == source)
        data_stmt = data_stmt.where(Sprint.source == source)

    # Sorting
    sort_col = getattr(Sprint, sort_by, Sprint.start_date)
    order = sort_col.asc() if sort_order == SortOrder.ASC else sort_col.desc()
    data_stmt = data_stmt.order_by(order.nullslast()).offset(offset).limit(limit)

    total_result = await session.execute(count_stmt)
    total = total_result.scalar_one()

    rows = await session.execute(data_stmt)
    items = [_sprint_to_read(sprint, wi_count or 0) for sprint, wi_count in rows.all()]

    return PaginatedResponse(items=items, total=total, offset=offset, limit=limit)


@router.get(
    "/{sprint_id}",
    response_model=SprintRead,
    summary="Get sprint by ID",
)
async def get_sprint(
    sprint_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> SprintRead:
    sprint = await session.get(Sprint, sprint_id)
    if not sprint:
        raise HTTPException(404, "Sprint not found")

    count_stmt = select(func.count(WorkItem.id)).where(WorkItem.sprint_id == sprint_id)
    result = await session.execute(count_stmt)
    wi_count = result.scalar_one()

    return _sprint_to_read(sprint, wi_count)


@router.post(
    "",
    response_model=SprintRead,
    status_code=201,
    summary="Create a sprint",
)
async def create_sprint(
    body: SprintCreate,
    session: AsyncSession = Depends(get_session),
) -> SprintRead:
    sprint = Sprint(**body.model_dump())
    session.add(sprint)
    await session.commit()
    await session.refresh(sprint)
    return _sprint_to_read(sprint)


@router.patch(
    "/{sprint_id}",
    response_model=SprintRead,
    summary="Update a sprint",
)
async def update_sprint(
    sprint_id: uuid.UUID,
    body: SprintUpdate,
    session: AsyncSession = Depends(get_session),
) -> SprintRead:
    sprint = await session.get(Sprint, sprint_id)
    if not sprint:
        raise HTTPException(404, "Sprint not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(sprint, field, value)

    await session.commit()
    await session.refresh(sprint)

    count_stmt = select(func.count(WorkItem.id)).where(WorkItem.sprint_id == sprint_id)
    result = await session.execute(count_stmt)
    wi_count = result.scalar_one()

    return _sprint_to_read(sprint, wi_count)


@router.delete(
    "/{sprint_id}",
    status_code=204,
    summary="Delete a sprint",
)
async def delete_sprint(
    sprint_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    sprint = await session.get(Sprint, sprint_id)
    if not sprint:
        raise HTTPException(404, "Sprint not found")
    await session.delete(sprint)
    await session.commit()

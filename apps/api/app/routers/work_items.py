"""WorkItem endpoints — CRUD + rich filtering, pagination & sorting."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.work_item import WorkItem
from app.schemas.common import PaginatedResponse, SortOrder
from app.schemas.work_item import WorkItemCreate, WorkItemRead, WorkItemUpdate

router = APIRouter(prefix="/work-items", tags=["work-items"])


@router.get(
    "",
    response_model=PaginatedResponse[WorkItemRead],
    summary="List work items",
    description="Filterable, paginated, sortable list of work items.",
)
async def list_work_items(
    status: str | None = Query(None, examples=["in_progress"]),
    item_type: str | None = Query(None, examples=["story"]),
    priority: str | None = Query(None, examples=["high"]),
    sprint_id: uuid.UUID | None = Query(None),
    assignee_id: uuid.UUID | None = Query(None),
    source: str | None = Query(None, examples=["jira"]),
    sort_by: str = Query("created_at", description="Column to sort by"),
    sort_order: SortOrder = Query(SortOrder.DESC),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> PaginatedResponse[WorkItemRead]:
    count_stmt = select(func.count(WorkItem.id))
    data_stmt = select(WorkItem)

    # Apply filters
    filters = []
    if status:
        filters.append(WorkItem.status == status)
    if item_type:
        filters.append(WorkItem.item_type == item_type)
    if priority:
        filters.append(WorkItem.priority == priority)
    if sprint_id:
        filters.append(WorkItem.sprint_id == sprint_id)
    if assignee_id:
        filters.append(WorkItem.assignee_id == assignee_id)
    if source:
        filters.append(WorkItem.source == source)

    for f in filters:
        count_stmt = count_stmt.where(f)
        data_stmt = data_stmt.where(f)

    # Sorting
    sort_col = getattr(WorkItem, sort_by, WorkItem.created_at)
    order = sort_col.asc() if sort_order == SortOrder.ASC else sort_col.desc()
    data_stmt = data_stmt.order_by(order.nullslast()).offset(offset).limit(limit)

    total_result = await session.execute(count_stmt)
    total = total_result.scalar_one()

    result = await session.execute(data_stmt)
    items = [WorkItemRead.model_validate(wi) for wi in result.scalars().all()]

    return PaginatedResponse(items=items, total=total, offset=offset, limit=limit)


@router.get(
    "/{item_id}",
    response_model=WorkItemRead,
    summary="Get work item by ID",
)
async def get_work_item(
    item_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> WorkItemRead:
    wi = await session.get(WorkItem, item_id)
    if not wi:
        raise HTTPException(404, "Work item not found")
    return WorkItemRead.model_validate(wi)


@router.post(
    "",
    response_model=WorkItemRead,
    status_code=201,
    summary="Create a work item",
)
async def create_work_item(
    body: WorkItemCreate,
    session: AsyncSession = Depends(get_session),
) -> WorkItemRead:
    wi = WorkItem(**body.model_dump())
    session.add(wi)
    await session.commit()
    await session.refresh(wi)
    return WorkItemRead.model_validate(wi)


@router.patch(
    "/{item_id}",
    response_model=WorkItemRead,
    summary="Update a work item",
)
async def update_work_item(
    item_id: uuid.UUID,
    body: WorkItemUpdate,
    session: AsyncSession = Depends(get_session),
) -> WorkItemRead:
    wi = await session.get(WorkItem, item_id)
    if not wi:
        raise HTTPException(404, "Work item not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(wi, field, value)

    await session.commit()
    await session.refresh(wi)
    return WorkItemRead.model_validate(wi)


@router.delete(
    "/{item_id}",
    status_code=204,
    summary="Delete a work item",
)
async def delete_work_item(
    item_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    wi = await session.get(WorkItem, item_id)
    if not wi:
        raise HTTPException(404, "Work item not found")
    await session.delete(wi)
    await session.commit()

"""Report endpoints — CRUD + period filtering."""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.models.report import Report
from app.schemas.common import PaginatedResponse, SortOrder
from app.schemas.report import ReportCreate, ReportRead, ReportUpdate

router = APIRouter(prefix="/reports", tags=["reports"])


@router.get(
    "",
    response_model=PaginatedResponse[ReportRead],
    summary="List reports",
    description="Filter by period type and date range. Paginated and sortable.",
)
async def list_reports(
    period: str | None = Query(None, examples=["weekly"]),
    start: date | None = Query(None, description="period_start >= this date"),
    end: date | None = Query(None, description="period_end <= this date"),
    sort_by: str = Query("period_start", description="Column to sort by"),
    sort_order: SortOrder = Query(SortOrder.DESC),
    offset: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    session: AsyncSession = Depends(get_session),
) -> PaginatedResponse[ReportRead]:
    count_stmt = select(func.count(Report.id))
    data_stmt = select(Report)

    filters = []
    if period:
        filters.append(Report.period == period)
    if start:
        filters.append(Report.period_start >= start)
    if end:
        filters.append(Report.period_end <= end)

    for f in filters:
        count_stmt = count_stmt.where(f)
        data_stmt = data_stmt.where(f)

    sort_col = getattr(Report, sort_by, Report.period_start)
    order = sort_col.asc() if sort_order == SortOrder.ASC else sort_col.desc()
    data_stmt = data_stmt.order_by(order.nullslast()).offset(offset).limit(limit)

    total_result = await session.execute(count_stmt)
    total = total_result.scalar_one()

    result = await session.execute(data_stmt)
    items = [ReportRead.model_validate(r) for r in result.scalars().all()]

    return PaginatedResponse(items=items, total=total, offset=offset, limit=limit)


@router.get(
    "/latest",
    response_model=ReportRead | None,
    summary="Get latest report for a period type",
)
async def get_latest_report(
    period: str = Query("weekly", examples=["weekly"]),
    session: AsyncSession = Depends(get_session),
) -> ReportRead | None:
    stmt = (
        select(Report)
        .where(Report.period == period)
        .order_by(Report.period_end.desc())
        .limit(1)
    )
    result = await session.execute(stmt)
    report = result.scalar_one_or_none()
    if not report:
        return None
    return ReportRead.model_validate(report)


@router.get(
    "/{report_id}",
    response_model=ReportRead,
    summary="Get report by ID",
)
async def get_report(
    report_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> ReportRead:
    report = await session.get(Report, report_id)
    if not report:
        raise HTTPException(404, "Report not found")
    return ReportRead.model_validate(report)


@router.post(
    "",
    response_model=ReportRead,
    status_code=201,
    summary="Create a report",
)
async def create_report(
    body: ReportCreate,
    session: AsyncSession = Depends(get_session),
) -> ReportRead:
    report = Report(**body.model_dump())
    session.add(report)
    await session.commit()
    await session.refresh(report)
    return ReportRead.model_validate(report)


@router.patch(
    "/{report_id}",
    response_model=ReportRead,
    summary="Update a report",
)
async def update_report(
    report_id: uuid.UUID,
    body: ReportUpdate,
    session: AsyncSession = Depends(get_session),
) -> ReportRead:
    report = await session.get(Report, report_id)
    if not report:
        raise HTTPException(404, "Report not found")

    for field, value in body.model_dump(exclude_unset=True).items():
        setattr(report, field, value)

    await session.commit()
    await session.refresh(report)
    return ReportRead.model_validate(report)


@router.delete(
    "/{report_id}",
    status_code=204,
    summary="Delete a report",
)
async def delete_report(
    report_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> None:
    report = await session.get(Report, report_id)
    if not report:
        raise HTTPException(404, "Report not found")
    await session.delete(report)
    await session.commit()

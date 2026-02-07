"""Metrics endpoints — chart-ready series + table-ready rows for dashboards.

Expensive queries are cached in Redis (5-minute TTL).
"""

import uuid
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.cache import cached
from app.db import get_session
from app.models.effort_log import EffortLog
from app.models.sprint import Sprint
from app.models.work_item import WorkItem
from app.schemas.metrics import (
    ChartSeries,
    MetricsResponse,
    SprintMetricsResponse,
    TableRow,
    TeamMetricsResponse,
)
from app.services.metrics import MetricsService

router = APIRouter(prefix="/metrics", tags=["metrics"])


# ---------------------------------------------------------------------------
# Helpers (cached heavy queries)
# ---------------------------------------------------------------------------

@cached("velocity", ttl_seconds=300)
async def _compute_velocity(session: AsyncSession) -> list[dict]:
    """Story-points committed vs completed per sprint."""
    committed = func.coalesce(func.sum(WorkItem.story_points), 0.0)
    completed = func.coalesce(
        func.sum(
            case(
                (WorkItem.status.in_(["done", "closed"]), WorkItem.story_points),
                else_=0.0,
            )
        ),
        0.0,
    )

    stmt = (
        select(
            Sprint.name,
            committed.label("committed"),
            completed.label("completed"),
        )
        .join(WorkItem, WorkItem.sprint_id == Sprint.id, isouter=True)
        .where(Sprint.status.in_(["active", "closed"]))
        .group_by(Sprint.id, Sprint.name, Sprint.start_date)
        .order_by(Sprint.start_date.asc().nullslast())
        .limit(20)
    )

    result = await session.execute(stmt)
    return [
        {
            "sprint_name": r.name,
            "committed": float(r.committed),
            "completed": float(r.completed),
        }
        for r in result.all()
    ]


@cached("burndown", ttl_seconds=300)
async def _compute_burndown(session: AsyncSession, sprint_id: str) -> list[dict]:
    """Approximate burndown: cumulative story points resolved per day."""
    sid = uuid.UUID(sprint_id)

    sprint_stmt = select(Sprint).where(Sprint.id == sid)
    sprint_result = await session.execute(sprint_stmt)
    sprint = sprint_result.scalar_one_or_none()
    if not sprint or not sprint.start_date or not sprint.end_date:
        return []

    total_stmt = select(func.coalesce(func.sum(WorkItem.story_points), 0.0)).where(
        WorkItem.sprint_id == sid
    )
    total_result = await session.execute(total_stmt)
    total_points = float(total_result.scalar_one())

    if total_points == 0:
        return []

    # Daily resolved points via resolved_at
    daily_stmt = (
        select(
            func.date(WorkItem.resolved_at).label("day"),
            func.sum(WorkItem.story_points).label("pts"),
        )
        .where(
            WorkItem.sprint_id == sid,
            WorkItem.resolved_at.isnot(None),
        )
        .group_by(func.date(WorkItem.resolved_at))
        .order_by(func.date(WorkItem.resolved_at))
    )
    daily_result = await session.execute(daily_stmt)
    daily_rows = daily_result.all()

    from datetime import timedelta

    days_total = (sprint.end_date - sprint.start_date).days or 1
    points: list[dict] = []
    cumulative_done = 0.0

    for i in range(days_total + 1):
        day = sprint.start_date + timedelta(days=i)
        day_str = day.isoformat()
        ideal = total_points - (total_points * i / days_total)

        for row in daily_rows:
            if str(row.day) == day_str:
                cumulative_done += float(row.pts or 0)

        points.append({
            "day": day_str,
            "ideal": round(ideal, 1),
            "actual": round(total_points - cumulative_done, 1),
        })

    return points


@cached("effort_breakdown", ttl_seconds=300)
async def _compute_effort_breakdown(session: AsyncSession) -> list[dict]:
    """Hours per effort category across all time."""
    stmt = (
        select(
            EffortLog.category,
            func.sum(EffortLog.hours).label("total_hours"),
        )
        .group_by(EffortLog.category)
        .order_by(func.sum(EffortLog.hours).desc())
    )
    result = await session.execute(stmt)
    return [
        {"category": r.category, "total_hours": float(r.total_hours)}
        for r in result.all()
    ]


@cached("status_distribution", ttl_seconds=300)
async def _compute_status_distribution(session: AsyncSession) -> list[dict]:
    """Work item count by status."""
    stmt = (
        select(
            WorkItem.status,
            func.count(WorkItem.id).label("count"),
        )
        .group_by(WorkItem.status)
        .order_by(func.count(WorkItem.id).desc())
    )
    result = await session.execute(stmt)
    return [{"status": r.status, "count": r.count} for r in result.all()]


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.get(
    "",
    response_model=MetricsResponse,
    summary="Dashboard metrics",
    description=(
        "Returns chart-ready series and table-ready rows for velocity, "
        "burndown, effort breakdown, and status distribution.  "
        "Results are cached for 5 minutes in Redis."
    ),
)
async def get_metrics(
    sprint_id: uuid.UUID | None = Query(None, description="Sprint ID for burndown chart"),
    session: AsyncSession = Depends(get_session),
) -> MetricsResponse:
    velocity_data = await _compute_velocity(session)
    effort_data = await _compute_effort_breakdown(session)
    status_data = await _compute_status_distribution(session)

    burndown_data: list[dict] = []
    if sprint_id:
        burndown_data = await _compute_burndown(session, str(sprint_id))

    # Build chart-ready series
    charts: dict[str, list[ChartSeries]] = {
        "velocity": [
            ChartSeries(
                name="Committed",
                data=[{"x": v["sprint_name"], "y": v["committed"]} for v in velocity_data],
            ),
            ChartSeries(
                name="Completed",
                data=[{"x": v["sprint_name"], "y": v["completed"]} for v in velocity_data],
            ),
        ],
        "effort_breakdown": [
            ChartSeries(
                name="Hours by Category",
                data=[{"x": e["category"], "y": e["total_hours"]} for e in effort_data],
            ),
        ],
        "status_distribution": [
            ChartSeries(
                name="Work Items by Status",
                data=[{"x": s["status"], "y": s["count"]} for s in status_data],
            ),
        ],
    }

    if burndown_data:
        charts["burndown"] = [
            ChartSeries(
                name="Ideal",
                data=[{"x": b["day"], "y": b["ideal"]} for b in burndown_data],
            ),
            ChartSeries(
                name="Actual",
                data=[{"x": b["day"], "y": b["actual"]} for b in burndown_data],
            ),
        ]

    # Build table-ready rows
    tables: dict[str, list[TableRow]] = {
        "velocity": [TableRow(values=v) for v in velocity_data],
        "effort_breakdown": [TableRow(values=e) for e in effort_data],
        "status_distribution": [TableRow(values=s) for s in status_data],
    }
    if burndown_data:
        tables["burndown"] = [TableRow(values=b) for b in burndown_data]

    # Summary KPIs
    avg_velocity = (
        sum(v["completed"] for v in velocity_data) / len(velocity_data)
        if velocity_data
        else 0
    )
    total_effort = sum(e["total_hours"] for e in effort_data)
    total_items = sum(s["count"] for s in status_data)
    done_items = sum(s["count"] for s in status_data if s["status"] in ("done", "closed"))

    summary = {
        "velocity_avg": round(avg_velocity, 1),
        "total_effort_hours": round(total_effort, 1),
        "total_work_items": total_items,
        "done_work_items": done_items,
        "completion_rate": round(done_items / total_items * 100, 1) if total_items else 0,
    }

    return MetricsResponse(charts=charts, tables=tables, summary=summary)


@router.get(
    "/velocity",
    summary="Velocity chart data",
    description="Committed vs completed story points per sprint (cached 5 min).",
)
async def get_velocity(
    session: AsyncSession = Depends(get_session),
) -> dict:
    data = await _compute_velocity(session)
    return {
        "chart": [
            ChartSeries(
                name="Committed",
                data=[{"x": v["sprint_name"], "y": v["committed"]} for v in data],
            ).model_dump(),
            ChartSeries(
                name="Completed",
                data=[{"x": v["sprint_name"], "y": v["completed"]} for v in data],
            ).model_dump(),
        ],
        "table": data,
    }


@router.get(
    "/burndown/{sprint_id}",
    summary="Burndown chart for a sprint",
    description="Ideal vs actual remaining story points per day (cached 5 min).",
)
async def get_burndown(
    sprint_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> dict:
    data = await _compute_burndown(session, str(sprint_id))
    return {
        "chart": [
            ChartSeries(
                name="Ideal",
                data=[{"x": b["day"], "y": b["ideal"]} for b in data],
            ).model_dump(),
            ChartSeries(
                name="Actual",
                data=[{"x": b["day"], "y": b["actual"]} for b in data],
            ).model_dump(),
        ],
        "table": data,
    }


# ---------------------------------------------------------------------------
# Full sprint & team dashboards (changelog-based computation)
# ---------------------------------------------------------------------------

@router.get(
    "/sprint/{sprint_id}",
    response_model=SprintMetricsResponse,
    summary="Full sprint dashboard",
    description=(
        "Burndown (from changelog status transitions + story points), "
        "velocity, scope change, done/not-done report, cumulative flow, "
        "lead/cycle time, and throughput for a single sprint."
    ),
)
async def get_sprint_metrics(
    sprint_id: uuid.UUID,
    session: AsyncSession = Depends(get_session),
) -> SprintMetricsResponse:
    svc = MetricsService(session)
    data = await svc.get_sprint_metrics(sprint_id)
    if not data:
        raise HTTPException(404, "Sprint not found")
    return SprintMetricsResponse(**data)


@router.get(
    "/team/{team_id}",
    response_model=TeamMetricsResponse,
    summary="Team dashboard metrics",
    description=(
        "Velocity history, cumulative flow, lead/cycle time, throughput, "
        "and due-date risk for a team over a date range."
    ),
)
async def get_team_metrics(
    team_id: str,
    from_date: date = Query(..., alias="from", description="Start date (YYYY-MM-DD)"),
    to_date: date = Query(..., alias="to", description="End date (YYYY-MM-DD)"),
    session: AsyncSession = Depends(get_session),
) -> TeamMetricsResponse:
    if from_date > to_date:
        raise HTTPException(400, "'from' must be <= 'to'")
    svc = MetricsService(session)
    data = await svc.get_team_metrics(team_id, from_date, to_date)
    return TeamMetricsResponse(**data)

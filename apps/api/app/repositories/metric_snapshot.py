"""Repository for metric_snapshot_daily and sprint_burndown_point records."""

import uuid
from datetime import date

from sqlalchemy import select

from app.models.metric_snapshot import MetricSnapshotDaily, SprintBurndownPoint
from app.repositories.base import BaseRepo


class MetricSnapshotRepo(BaseRepo[MetricSnapshotDaily]):
    model = MetricSnapshotDaily

    async def get_by_date_team_sprint(
        self, snapshot_date: date, team_id: str | None, sprint_id: uuid.UUID | None,
    ) -> MetricSnapshotDaily | None:
        stmt = select(MetricSnapshotDaily).where(
            MetricSnapshotDaily.date == snapshot_date,
            MetricSnapshotDaily.team_id == team_id,
            MetricSnapshotDaily.sprint_id == sprint_id,
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_sprint(
        self, sprint_id: uuid.UUID, *, start: date | None = None, end: date | None = None,
    ) -> list[MetricSnapshotDaily]:
        stmt = select(MetricSnapshotDaily).where(MetricSnapshotDaily.sprint_id == sprint_id)
        if start:
            stmt = stmt.where(MetricSnapshotDaily.date >= start)
        if end:
            stmt = stmt.where(MetricSnapshotDaily.date <= end)
        stmt = stmt.order_by(MetricSnapshotDaily.date)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_team(
        self, team_id: str, *, start: date | None = None, end: date | None = None,
    ) -> list[MetricSnapshotDaily]:
        stmt = select(MetricSnapshotDaily).where(MetricSnapshotDaily.team_id == team_id)
        if start:
            stmt = stmt.where(MetricSnapshotDaily.date >= start)
        if end:
            stmt = stmt.where(MetricSnapshotDaily.date <= end)
        stmt = stmt.order_by(MetricSnapshotDaily.date)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())


class SprintBurndownRepo(BaseRepo[SprintBurndownPoint]):
    model = SprintBurndownPoint

    async def list_by_sprint(self, sprint_id: uuid.UUID) -> list[SprintBurndownPoint]:
        stmt = (
            select(SprintBurndownPoint)
            .where(SprintBurndownPoint.sprint_id == sprint_id)
            .order_by(SprintBurndownPoint.date)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

"""Repository for report records."""

from datetime import date

from sqlalchemy import select

from app.models.report import Report
from app.repositories.base import BaseRepo


class ReportRepo(BaseRepo[Report]):
    model = Report

    async def get_latest(self, period: str) -> Report | None:
        stmt = (
            select(Report)
            .where(Report.period == period)
            .order_by(Report.period_end.desc())
            .limit(1)
        )
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_period(
        self, period: str, *, start: date | None = None, end: date | None = None
    ) -> list[Report]:
        stmt = select(Report).where(Report.period == period)
        if start:
            stmt = stmt.where(Report.period_start >= start)
        if end:
            stmt = stmt.where(Report.period_end <= end)
        stmt = stmt.order_by(Report.period_start.desc())
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

"""Repository for effort_log records."""

import uuid
from datetime import date

from sqlalchemy import func, select

from app.models.effort_log import EffortLog
from app.models.person import Person
from app.repositories.base import BaseRepo


class EffortLogRepo(BaseRepo[EffortLog]):
    model = EffortLog

    async def list_by_person_range(
        self, person_id: uuid.UUID, start: date, end: date
    ) -> list[EffortLog]:
        stmt = (
            select(EffortLog)
            .where(
                EffortLog.person_id == person_id,
                EffortLog.day >= start,
                EffortLog.day <= end,
            )
            .order_by(EffortLog.day)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def total_hours(self, person_id: uuid.UUID, start: date, end: date) -> float:
        stmt = (
            select(func.coalesce(func.sum(EffortLog.hours), 0.0))
            .where(
                EffortLog.person_id == person_id,
                EffortLog.day >= start,
                EffortLog.day <= end,
            )
        )
        result = await self.session.execute(stmt)
        return float(result.scalar_one())

    async def total_hours_for_day(self, person_id: uuid.UUID, day: date) -> float:
        """Sum of hours already logged by a person on a specific day."""
        stmt = (
            select(func.coalesce(func.sum(EffortLog.hours), 0.0))
            .where(EffortLog.person_id == person_id, EffortLog.day == day)
        )
        result = await self.session.execute(stmt)
        return float(result.scalar_one())

    async def has_locked_day(self, person_id: uuid.UUID, day: date) -> bool:
        """Check if any effort entry on this day is locked for the person."""
        stmt = (
            select(func.count())
            .where(
                EffortLog.person_id == person_id,
                EffortLog.day == day,
                EffortLog.locked.is_(True),
            )
        )
        result = await self.session.execute(stmt)
        return (result.scalar_one() or 0) > 0

    async def list_by_day(self, day: date) -> list[EffortLog]:
        stmt = select(EffortLog).where(EffortLog.day == day).order_by(EffortLog.person_id)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_team_range(
        self, team: str, start: date, end: date
    ) -> list[EffortLog]:
        """All effort logs for members of a given team within a date range."""
        stmt = (
            select(EffortLog)
            .join(Person, EffortLog.person_id == Person.id)
            .where(Person.team == team, EffortLog.day >= start, EffortLog.day <= end)
            .order_by(EffortLog.day, EffortLog.person_id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_person_ids_range(
        self, person_ids: list[uuid.UUID], start: date, end: date
    ) -> list[EffortLog]:
        """All effort logs for a set of persons within a date range."""
        if not person_ids:
            return []
        stmt = (
            select(EffortLog)
            .where(
                EffortLog.person_id.in_(person_ids),
                EffortLog.day >= start,
                EffortLog.day <= end,
            )
            .order_by(EffortLog.day, EffortLog.person_id)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_sprint_work_items(
        self, work_item_ids: list[uuid.UUID],
    ) -> list[EffortLog]:
        """All effort logs linked to the given work items."""
        if not work_item_ids:
            return []
        stmt = (
            select(EffortLog)
            .where(EffortLog.work_item_id.in_(work_item_ids))
            .order_by(EffortLog.day)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

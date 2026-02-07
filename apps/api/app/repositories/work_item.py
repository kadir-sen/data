"""Repository for work_item records."""

import uuid
from datetime import date

from sqlalchemy import select

from app.models.work_item import WorkItem
from app.repositories.base import BaseRepo


class WorkItemRepo(BaseRepo[WorkItem]):
    model = WorkItem

    async def get_by_source(self, source: str, source_id: str) -> WorkItem | None:
        stmt = select(WorkItem).where(WorkItem.source == source, WorkItem.source_id == source_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_sprint(self, sprint_id: uuid.UUID) -> list[WorkItem]:
        stmt = (
            select(WorkItem)
            .where(WorkItem.sprint_id == sprint_id)
            .order_by(WorkItem.status, WorkItem.due_date)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_assignee(
        self, assignee_id: uuid.UUID, *, status: str | None = None
    ) -> list[WorkItem]:
        stmt = select(WorkItem).where(WorkItem.assignee_id == assignee_id)
        if status:
            stmt = stmt.where(WorkItem.status == status)
        stmt = stmt.order_by(WorkItem.due_date)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_overdue(self, as_of: date | None = None) -> list[WorkItem]:
        ref = as_of or date.today()
        stmt = (
            select(WorkItem)
            .where(WorkItem.due_date < ref, WorkItem.status.notin_(["done", "closed"]))
            .order_by(WorkItem.due_date)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

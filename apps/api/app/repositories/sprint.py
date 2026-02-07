"""Repository for sprint records."""

from sqlalchemy import select

from app.models.sprint import Sprint
from app.repositories.base import BaseRepo


class SprintRepo(BaseRepo[Sprint]):
    model = Sprint

    async def get_by_source(self, source: str, source_id: str) -> Sprint | None:
        stmt = select(Sprint).where(Sprint.source == source, Sprint.source_id == source_id)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_active(self) -> list[Sprint]:
        stmt = (
            select(Sprint)
            .where(Sprint.status == "active")
            .order_by(Sprint.start_date.desc())
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

    async def list_by_status(self, status: str) -> list[Sprint]:
        stmt = select(Sprint).where(Sprint.status == status).order_by(Sprint.start_date)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

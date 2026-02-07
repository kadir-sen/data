"""Repository for person records."""

from sqlalchemy import select

from app.models.person import Person
from app.repositories.base import BaseRepo


class PersonRepo(BaseRepo[Person]):
    model = Person

    async def get_by_email(self, email: str) -> Person | None:
        stmt = select(Person).where(Person.email == email)
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def find_by_source_id(self, source: str, source_id: str) -> Person | None:
        """Look up a person by a source-specific ID stored in the JSONB source_ids column."""
        stmt = select(Person).where(Person.source_ids[source].astext == str(source_id))
        result = await self.session.execute(stmt)
        return result.scalar_one_or_none()

    async def list_by_team(self, team: str) -> list[Person]:
        stmt = select(Person).where(Person.team == team).order_by(Person.display_name)
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

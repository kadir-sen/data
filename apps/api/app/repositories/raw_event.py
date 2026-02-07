"""Repository for raw_event ingestion log."""

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.logging_config import Timer, get_logger
from app.models.raw_event import RawEvent
from app.observability import counter_inc, histogram_observe
from app.repositories.base import BaseRepo

logger = get_logger("app.repositories.raw_event")


class RawEventRepo(BaseRepo[RawEvent]):
    model = RawEvent

    async def upsert_by_hash(self, event: RawEvent) -> RawEvent:
        """Insert-or-skip using content_hash for idempotency."""
        with Timer() as t:
            stmt = (
                pg_insert(RawEvent)
                .values(
                    id=event.id,
                    source=event.source,
                    entity_type=event.entity_type,
                    entity_id=event.entity_id,
                    occurred_at=event.occurred_at,
                    content_hash=event.content_hash,
                    payload=event.payload,
                    error=event.error,
                )
                .on_conflict_do_nothing(index_elements=["content_hash"])
                .returning(RawEvent)
            )
            result = await self.session.execute(stmt)
            row = result.scalar_one_or_none()

        is_duplicate = row is None
        if is_duplicate:
            # Already existed — fetch the existing row
            existing = await self.session.execute(
                select(RawEvent).where(RawEvent.content_hash == event.content_hash)
            )
            counter_inc("ingestion_duplicates_total", source=event.source)
            logger.info(
                "ingestion.duplicate",
                source=event.source,
                entity_type=event.entity_type,
                entity_id=event.entity_id,
                content_hash=event.content_hash,
                duration_ms=round(t.ms, 1),
            )
            return existing.scalar_one()

        counter_inc("ingestion_events_total", source=event.source)
        histogram_observe("ingestion_duration_ms", t.ms, source=event.source)
        logger.info(
            "ingestion.created",
            source=event.source,
            entity_type=event.entity_type,
            entity_id=event.entity_id,
            content_hash=event.content_hash,
            duration_ms=round(t.ms, 1),
        )
        return row

    async def list_by_source(
        self, source: str, *, offset: int = 0, limit: int = 100
    ) -> list[RawEvent]:
        stmt = (
            select(RawEvent)
            .where(RawEvent.source == source)
            .order_by(RawEvent.occurred_at.desc())
            .offset(offset)
            .limit(limit)
        )
        result = await self.session.execute(stmt)
        return list(result.scalars().all())

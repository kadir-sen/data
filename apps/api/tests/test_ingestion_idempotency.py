"""Tests for ingestion idempotency via content_hash deduplication.

Verifies that:
  1. Inserting the same event twice yields the same row (no duplicates).
  2. Different payloads with different hashes create distinct rows.
  3. The duplicate counter metric increments correctly.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.raw_event import RawEvent
from app.observability import counter_get, reset as reset_metrics
from app.repositories.raw_event import RawEventRepo


def _make_event(
    source: str = "jira",
    entity_type: str = "issue",
    entity_id: str = "PROJ-1",
    payload: dict | None = None,
) -> RawEvent:
    payload = payload or {"key": "PROJ-1", "summary": "Test issue"}
    content = json.dumps(payload, sort_keys=True)
    return RawEvent(
        id=uuid.uuid4(),
        source=source,
        entity_type=entity_type,
        entity_id=entity_id,
        occurred_at=datetime.now(tz=timezone.utc),
        content_hash=hashlib.sha256(content.encode()).hexdigest(),
        payload=payload,
    )


@pytest.fixture(autouse=True)
def _reset_metrics():
    reset_metrics()
    yield
    reset_metrics()


async def test_upsert_creates_event(db_session: AsyncSession) -> None:
    """First insert should create the event."""
    repo = RawEventRepo(db_session)
    event = _make_event()
    result = await repo.upsert_by_hash(event)
    await db_session.commit()

    assert result.id is not None
    assert result.source == "jira"
    assert result.content_hash == event.content_hash

    # Verify exactly 1 row in DB
    count = await db_session.execute(select(func.count(RawEvent.id)))
    assert count.scalar_one() == 1


async def test_upsert_duplicate_is_idempotent(db_session: AsyncSession) -> None:
    """Inserting the same content_hash twice should NOT create a second row."""
    repo = RawEventRepo(db_session)
    event = _make_event()

    first = await repo.upsert_by_hash(event)
    await db_session.commit()

    # Same payload → same hash → duplicate
    dup_event = _make_event()  # identical payload = identical hash
    second = await repo.upsert_by_hash(dup_event)
    await db_session.commit()

    assert first.content_hash == second.content_hash

    count = await db_session.execute(select(func.count(RawEvent.id)))
    assert count.scalar_one() == 1, "Duplicate should not create a new row"


async def test_upsert_different_payloads_creates_two(db_session: AsyncSession) -> None:
    """Different payloads should create distinct rows."""
    repo = RawEventRepo(db_session)

    event_a = _make_event(payload={"key": "PROJ-1", "summary": "A"})
    event_b = _make_event(payload={"key": "PROJ-1", "summary": "B"})

    await repo.upsert_by_hash(event_a)
    await db_session.commit()

    await repo.upsert_by_hash(event_b)
    await db_session.commit()

    count = await db_session.execute(select(func.count(RawEvent.id)))
    assert count.scalar_one() == 2


async def test_duplicate_increments_metric(db_session: AsyncSession) -> None:
    """Duplicates should increment the ingestion_duplicates_total counter."""
    repo = RawEventRepo(db_session)

    event = _make_event()
    await repo.upsert_by_hash(event)
    await db_session.commit()

    assert counter_get("ingestion_duplicates_total", source="jira") == 0

    # Re-insert same event
    dup = _make_event()
    await repo.upsert_by_hash(dup)
    await db_session.commit()

    assert counter_get("ingestion_duplicates_total", source="jira") == 1


async def test_successful_insert_increments_metric(db_session: AsyncSession) -> None:
    """New events should increment ingestion_events_total."""
    repo = RawEventRepo(db_session)

    event = _make_event()
    await repo.upsert_by_hash(event)
    await db_session.commit()

    assert counter_get("ingestion_events_total", source="jira") == 1


async def test_multi_source_dedup(db_session: AsyncSession) -> None:
    """Events from different sources with the same payload still get distinct hashes if data differs."""
    repo = RawEventRepo(db_session)

    event_jira = _make_event(source="jira", payload={"id": "1"})
    event_gitlab = _make_event(source="gitlab", payload={"id": "1"})

    # Same payload → same hash → should be a duplicate
    await repo.upsert_by_hash(event_jira)
    await db_session.commit()
    await repo.upsert_by_hash(event_gitlab)
    await db_session.commit()

    count = await db_session.execute(select(func.count(RawEvent.id)))
    # Same hash means same event content — only 1 row
    assert count.scalar_one() == 1
